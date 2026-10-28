"""P2 - zero-copy reads: numpy views on SeqRing slots + per-slot sequence (seqlock) validation.

Part A - torn-read safety (adversarial). One spawned writer writes UNTHROTTLED into a SeqRing of length L at 1280x720.
Frame k's image is entirely the byte value (k % 251) (copied from a 251-image pool), so any mix of two frames is
detectable. The parent reads continuously for RUN_A_S per config with one of three reader styles:
  copy_fncheck   : the CURRENT SkellyCam pattern (get_data_by_index, ring_buffer_shared_memory.py L175-202): check
                   head-k < L, read frame_number, np.copyto the pixels out, accept iff frame_number == k. (Emulated on
                   SeqRing so it can share the harness; the real class was shown to tear in the verified code map W20.)
  seqlock_copy   : s1=seq; np.copyto pixels out; s2=seq; accept iff s1==s2==2k+2
  seqlock_view   : s1=seq; cv2.resize(VIEW of slot, 0.5, dst=prealloc) (= the UI use, no copy out); s2=seq; accept iff stable
and two target patterns: latest (k = head) and oldest (k = head-(L-1), the slot the writer overwrites next).
"silent tear" = accepted but the pixels are from >1 frame (checked on 9 sampled rows of the copy / resized result).

Part B - read cost with 5 spawned 60 fps writers (1080p and 720p), cold read of the newest frame right after it is
published, RUN_B_S per style, styles interleaved 5 rounds: seqlock_copy (1 copy out), seqlock_view (acquire+validate,
0 copies), seqlock_view_resize (view -> resize into prealloc -> validate), plus a 5-camera multiframe of each.

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam): .venv\\Scripts\\python.exe research\\frame_ring_buffer\\prototypes\\p2_seqlock_read.py
"""
from __future__ import annotations

import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

RUN_A_S = float(os.environ.get("P2_RUN_A_S", "10"))
RUN_B_S = float(os.environ.get("P2_RUN_B_S", "2"))
POOL = 251
ROWS = None


def adversarial_writer(spec, h, w, ready_q, stop_evt, out_q):
    import proto_common as pcm
    ring = pcm.SeqRing.attach(spec)
    pool = np.empty((POOL, h, w, 3), np.uint8)
    for p in range(POOL):
        pool[p] = p
    k = 0
    ready_q.put(1)
    t0 = time.perf_counter()
    while not stop_evt.is_set():
        s = ring.begin(k)
        np.copyto(ring.image_view(s, (h, w, 3)), pool[k % POOL])
        ring.commit(k, s, frame_number=k, tick_ns=0)
        k += 1
    out_q.put(dict(frames=k, fps=k / (time.perf_counter() - t0)))
    ring.close()


def paced_writer(spec, cam, h, w, fps, ready_q, stop_evt):
    import proto_common as pcm
    ring = pcm.SeqRing.attach(spec)
    frames = pcm.synthetic_frames(h, w, n=30, seed=cam, noise=8)
    sensor = pcm.FakeSensor(fps, seed=cam)
    ready_q.put(cam)
    k = 0
    while not stop_evt.is_set():
        tick, t_ns = sensor.grab()
        s = ring.begin(k)
        np.copyto(ring.image_view(s, (h, w, 3)), frames[k % 30])
        ring.commit(k, s, frame_number=k, tick_ns=t_ns)
        k += 1
    ring.close()


def torn(arr, rows):
    """True if the sampled rows of arr are not all one value."""
    v = arr[rows]
    return bool(v.min() != v.max())


def part_a():
    import cv2
    import proto_common as pcm
    h, w = pcm.SIZES["720p"]
    rows = np.linspace(0, h - 1, 9).astype(int)
    rows_half = np.linspace(0, h // 2 - 1, 9).astype(int)
    ctx = mp.get_context("spawn")
    out = []
    for L in (2, 8, 388):
        for pattern in ("latest", "oldest"):
            for style in ("copy_fncheck", "seqlock_copy", "seqlock_view"):
                ring = pcm.SeqRing.create(L, h * w * 3, prefault=True)
                ready_q, out_q, stop = ctx.Queue(), ctx.Queue(), ctx.Event()
                p = ctx.Process(target=adversarial_writer, args=(ring.spec(), h, w, ready_q, stop, out_q))
                p.start(); ready_q.get(timeout=120)
                while ring.head < L + 2:
                    time.sleep(0.001)
                dst = np.empty((h, w, 3), np.uint8)
                small = np.empty((h // 2, w // 2, 3), np.uint8)
                c = dict(reads=0, accepted=0, rejected_stale=0, rejected_seq=0, rejected_fn=0, silent_tears=0,
                         accepted_value_wrong=0)
                lat = []
                t_end = time.perf_counter() + RUN_A_S
                while time.perf_counter() < t_end:
                    hd = ring.head
                    k = hd if pattern == "latest" else hd - (L - 1)
                    if k < 0:
                        continue
                    sl = k % L
                    c["reads"] += 1
                    t0 = time.perf_counter_ns()
                    if style == "copy_fncheck":
                        if ring.head - k >= L:
                            c["rejected_stale"] += 1; continue
                        fn = int(ring.meta[sl, pcm.F_FN])         # metadata read first (record order)
                        np.copyto(dst, ring.image_view(sl, (h, w, 3)))
                        if fn != k:
                            c["rejected_fn"] += 1; continue
                        res, rr = dst, rows
                    else:
                        s1 = int(ring.meta[sl, pcm.F_SEQ])
                        if s1 != 2 * k + 2:
                            c["rejected_seq"] += 1; continue
                        if style == "seqlock_copy":
                            np.copyto(dst, ring.image_view(sl, (h, w, 3))); res, rr = dst, rows
                        else:
                            cv2.resize(ring.image_view(sl, (h, w, 3)), (w // 2, h // 2), dst=small,
                                       interpolation=cv2.INTER_NEAREST); res, rr = small, rows_half
                        if int(ring.meta[sl, pcm.F_SEQ]) != s1:
                            c["rejected_seq"] += 1; continue
                    lat.append(time.perf_counter_ns() - t0)
                    c["accepted"] += 1
                    if torn(res, rr):
                        c["silent_tears"] += 1
                    elif int(res[0, 0, 0]) != k % POOL:
                        c["accepted_value_wrong"] += 1
                stop.set()
                wr = out_q.get(timeout=60)
                p.join(30)
                ring.close()
                row = dict(L=L, pattern=pattern, style=style, writer_fps=wr["fps"], **c, accepted_latency=pcm.stats_ms(lat))
                out.append(row)
                print(f"A L={L} {pattern} {style}: writer {wr['fps']:.0f} fps, reads {c['reads']}, accepted {c['accepted']}, "
                      f"silent tears {c['silent_tears']}, wrong-frame accepted {c['accepted_value_wrong']}, "
                      f"rejected seq/fn/stale {c['rejected_seq']}/{c['rejected_fn']}/{c['rejected_stale']}", flush=True)
    return out


def part_b():
    import cv2
    import proto_common as pcm
    ctx = mp.get_context("spawn")
    out = []
    for size_name in ("1080p", "720p"):
        h, w = pcm.SIZES[size_name]
        L = (1024 ** 3) // (632 + h * w * 3)
        rings = [pcm.SeqRing.create(L, h * w * 3, prefault=True) for _ in range(5)]
        ready_q, stop = ctx.Queue(), ctx.Event()
        procs = [ctx.Process(target=paced_writer, args=(rings[i].spec(), i, h, w, 60.0, ready_q, stop)) for i in range(5)]
        for p in procs:
            p.start()
        for _ in procs:
            ready_q.get(timeout=120)
        time.sleep(2.0)
        dst = np.empty((h, w, 3), np.uint8)
        dsts = [np.empty((h, w, 3), np.uint8) for _ in range(5)]
        smalls = [np.empty((h // 2, w // 2, 3), np.uint8) for _ in range(5)]
        styles = ["seqlock_copy", "seqlock_view", "seqlock_view_resize", "multi5_seqlock_copy", "multi5_seqlock_view",
                  "multi5_seqlock_view_resize"]
        samples = {s: [] for s in styles}
        fails = {s: 0 for s in styles}
        r0 = rings[0]
        for rnd in range(5):
            for st in styles:
                t_end = time.perf_counter() + RUN_B_S
                last = r0.head
                while time.perf_counter() < t_end:
                    hd = r0.head
                    if hd == last:
                        continue  # wait for a new frame -> cold read
                    last = hd
                    t0 = time.perf_counter_ns()
                    targets = [(r0, hd)] if not st.startswith("multi5") else [(r, r.head) for r in rings]
                    ok = True
                    for j, (r, k) in enumerate(targets):
                        sl = k % r.L
                        s1 = int(r.meta[sl, pcm.F_SEQ])
                        v = r.image_view(sl, (h, w, 3))
                        if st.endswith("copy"):
                            np.copyto(dsts[j] if st.startswith("multi5") else dst, v)
                        elif st.endswith("resize"):
                            cv2.resize(v, (w // 2, h // 2), dst=smalls[j], interpolation=cv2.INTER_LINEAR)
                        if not (s1 == 2 * k + 2 and int(r.meta[sl, pcm.F_SEQ]) == s1):
                            ok = False
                    samples[st].append(time.perf_counter_ns() - t0)
                    if not ok:
                        fails[st] += 1
        stop.set()
        for p in procs:
            p.join(30)
        for r in rings:
            r.close()
        for st in styles:
            row = dict(size=size_name, style=st, validation_failures=fails[st], **pcm.stats_ms(samples[st]))
            out.append(row)
            print(f"B {size_name} {st}: median {row['median_ms']:.4f} ms p99 {row['p99_ms']:.4f} n {row['n']} fails {fails[st]}", flush=True)
    return out


def main():
    import cv2
    import proto_common as pcm
    cv2.setNumThreads(1)
    env = pcm.env_summary()
    a = part_a()
    pcm.write_json("p2_seqlock_read.json", dict(env=env, part_a=a))
    b = part_b()
    pcm.write_json("p2_seqlock_read.json", dict(env=env, part_a=a, part_b=b, run_a_s=RUN_A_S, run_b_s=RUN_B_S))
    L = ["# P2 - zero-copy seqlock reads", "",
         f"## A. Torn-read safety, adversarial unthrottled writer, 720p, {RUN_A_S}s per row (reader in parent process)", "",
         "| L slots | target | reader | writer fps | reads | accepted | SILENT TEARS (accepted, mixed pixels) | accepted but wrong frame | rejected (seq / fn / stale) | accepted-read latency median ms |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for r in a:
        L.append(f"| {r['L']} | {r['pattern']} | {r['style']} | {r['writer_fps']:.0f} | {r['reads']} | {r['accepted']} | {r['silent_tears']} | "
                 f"{r['accepted_value_wrong']} | {r['rejected_seq']} / {r['rejected_fn']} / {r['rejected_stale']} | {r['accepted_latency'].get('median_ms', float('nan')):.3f} |")
    L += ["", f"## B. Cold read cost, 5 spawned writers at 60 fps, newest frame, 5 interleaved rounds x {RUN_B_S}s per style", "",
          "| size | style | full-frame copies | median ms | p99 ms | max ms | n | validation failures |", "|---|---|---|---|---|---|---|---|"]
    ncopies = {"seqlock_copy": 1, "seqlock_view": 0, "seqlock_view_resize": 0, "multi5_seqlock_copy": 5, "multi5_seqlock_view": 0,
               "multi5_seqlock_view_resize": 0}
    for r in b:
        L.append(f"| {r['size']} | {r['style']} | {ncopies[r['style']]} | {r['median_ms']:.4f} | {r['p99_ms']:.4f} | {r['max_ms']:.4f} | {r['n']} | {r['validation_failures']} |")
    L += ["", "Baseline for comparison (baseline/results/b_read.md, idle 20261027 re-run, real SkellyCam, cold medians): 1080p by_index_reused 0.4226 ms "
          "(p99 0.5007), view_no_copy 0.0165 ms, multiframe_latest (5 cams) 2.3533 ms (p99 7.2891), multiframe_by_number 6.6275 ms; "
          "720p by_index_reused 0.2150 ms, multiframe_latest 1.0629 ms."]
    pcm.write_text("p2_seqlock_read.md", "\n".join(L) + "\n")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
