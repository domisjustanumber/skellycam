"""P3 - lossless record path: decoupled per-camera recorder process with its own gated cursor on the SeqRing.

Topology (all spawned processes): 5 camera processes (FakeSensor 60 fps, latest-frame-wins, same model as the baseline
FakeCapture) each write frames into their own SeqRing; 5 recorder processes each consume THEIR camera's ring strictly
in order from a private cursor (cursor = last frame fully handed to the encoder). The camera loop never encodes.

Full-ring policies compared (what the camera does when the slot it needs still holds an unconsumed frame):
  overwrite : current SkellyCam policy (put_frame(overwrite=True), opencv_camera_loop.py L96): write anyway. The recorder
              detects a lapped slot (seq != 2k+2) and counts the lost frames itself - after the fact.
  block     : camera waits for the recorder; sensor ticks keep coming and are counted (FakeSensor.skipped) - explicit.
  drop      : camera skips the frame and increments ring_full_drops in the ring header - explicit.

Part A (sweep, synthetic recorder work): recorder "encode" = a 2 ms busy wait reading the slot view (stands in for an
async encoder hand-off), plus ONE injected stall of S ms on every recorder at t=3 s (all 5 at once, like a disk stall).
1920x1080, L in {16, 64, 172 (SkellyCam's 1 GiB default)}, S in {200, 1000, 2500, 3500} ms, 8 s per run.
Prediction: a stall of S ms is lossless iff S*60/1000 < L - (normal backlog); i.e. L=172 tolerates ~2.8 s.

Part B (real encoder): recorder = cv2.VideoWriter(fourcc 'X264') -> MSMF H.264 on this machine (same writer SkellyCam's
VideoRecorder uses), fed the slot VIEW (zero-copy hand-off; cursor advanced only after write() returns), L=172, policy
block, 1080p and 720p, 20 s, with one injected 1500 ms stall at t=8 s. Checks: recorder lag distribution (slots),
frames in file == frames produced, consecutive frame numbers, and decoded-content identity on every 10th frame
(each decoded frame must match synthetic frame (fn % 30) better than any other - catches slot reuse corruption).

Part ASYM (added 2026-10-28 by the REVISION stage, answers the priorities critic): the stall hits ONE recorder (camera 0)
only, as a single antivirus scan or encoder hiccup would. 1080p, L=172, busy recorder, 8 s, stall 1000 ms (fits the ring)
and 3500 ms (exceeds it). Policies: block, drop, and block_lockstep (block + a SkellyCam-style lockstep gate: a camera grabs
only when every camera's published count >= its own, camera_orchestrator.py L96-109). Reports, per run, whether every
camera recorded the same frame-number set over the common range, and the cross-camera spread of the sensor tick time of
recorded frame k (= how far apart in time the cameras' "frame k" were captured; < 16.7 ms means the multiframe is in sync).
Output: results/p3v_asymmetric_stall.json and .md (parts A/B files are not touched).

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam): .venv\\Scripts\\python.exe research\\frame_ring_buffer\\prototypes\\p3_lossless_record.py [A] [B] [ASYM]
"""
from __future__ import annotations

import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

N_CAMS = 5
FPS = 60.0


def camera(spec, cam, h, w, policy, run_s, ready_q, go_evt, out_q, lock_name=None):
    import proto_common as pcm
    ring = pcm.SeqRing.attach(spec)
    cnt_shm = cnt = None
    if lock_name:
        from multiprocessing import shared_memory as _shm
        cnt_shm = _shm.SharedMemory(name=lock_name)
        cnt = np.ndarray((N_CAMS,), np.int64, buffer=cnt_shm.buf)
    frames = pcm.synthetic_frames(h, w, n=30, seed=cam, noise=8)
    ready_q.put(cam)
    go_evt.wait()
    sensor = pcm.FakeSensor(FPS, seed=cam)
    gated = 0 if policy == "overwrite" else 1
    k = 0
    blocked_ns = 0
    block_events = 0
    drops = 0
    produced = 0
    t_end = time.perf_counter_ns() + int(run_s * 1e9)
    pub_lat = []
    while time.perf_counter_ns() < t_end:
        if cnt is not None:
            while int(cnt.min()) < k and time.perf_counter_ns() < t_end:
                time.sleep(1e-5)
        tick, t_tick = sensor.grab()
        if not ring.can_write(k, gated):
            if policy == "drop":
                drops += 1
                ring.hdr[pcm.H_DROPS] = drops
                continue
            b0 = time.perf_counter_ns(); block_events += 1
            while not ring.can_write(k, gated):
                time.sleep(0.0002)
            blocked_ns += time.perf_counter_ns() - b0
        t0 = time.perf_counter_ns()
        s = ring.begin(k)
        np.copyto(ring.image_view(s, (h, w, 3)), frames[tick % 30])
        ring.commit(k, s, frame_number=k, tick_ns=t_tick, aux0=tick)
        pub_lat.append(time.perf_counter_ns() - t0)
        k += 1
        produced += 1
        if cnt is not None:
            cnt[cam] = k
    if cnt is not None:
        cnt[cam] = 1 << 60
        del cnt
        cnt_shm.close()
    ring.hdr[pcm.H_BLOCK_NS] = blocked_ns
    out_q.put(dict(cam=cam, produced=produced, sensor_skipped=sensor.skipped, ring_full_drops=drops,
                   blocked_s=blocked_ns / 1e9, block_events=block_events, publish=pcm.stats_ms(pub_lat)))
    ring.close()


def recorder(spec, cam, h, w, policy, mode, stall_at_s, stall_ms, video_path, ready_q, go_evt, stop_evt, out_q):
    import cv2
    import proto_common as pcm
    ring = pcm.SeqRing.attach(spec)
    vw = None
    if mode == "msmf":
        vw = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"X264"), FPS, (w, h))
        backend = vw.getBackendName()
    else:
        backend = "busy2ms"
    ready_q.put(cam)
    go_evt.wait()
    t_start = time.perf_counter()
    stalled = False
    nxt = 0
    consumed = 0
    lost_lapped = 0
    lags = []
    write_lat = []
    tick_to_written = []
    fns = []
    ticks = []
    tick_ns_l = []
    gated = policy != "overwrite"
    max_lag = 0
    while True:
        if not stalled and time.perf_counter() - t_start >= stall_at_s:
            stalled = True
            time.sleep(stall_ms / 1000)
        hd = ring.head
        if nxt > hd:
            if stop_evt.is_set() and ring.head < nxt:
                break
            time.sleep(0.0005)
            continue
        lag = hd - nxt + 1
        max_lag = max(max_lag, lag)
        lags.append(lag)
        sl = nxt % ring.L
        s1 = int(ring.meta[sl, pcm.F_SEQ])
        if s1 != 2 * nxt + 2:
            # lapped (overwrite policy): frame nxt is gone. Jump to the oldest frame that is still stable.
            new = max(nxt + 1, ring.head - ring.L + 2)
            lost_lapped += new - nxt
            nxt = new
            continue
        view = ring.image_view(sl, (h, w, 3))
        t0 = time.perf_counter_ns()
        if vw is not None:
            vw.write(view)
        else:
            busy_end = t0 + 2_000_000
            acc = 0
            while time.perf_counter_ns() < busy_end:
                acc += int(view[0, 0, 0])
        t1 = time.perf_counter_ns()
        if not gated and int(ring.meta[sl, pcm.F_SEQ]) != s1:
            lost_lapped += 1  # overwritten while being encoded -> encoded data is torn; count as lost
        else:
            fns.append(int(ring.meta[sl, pcm.F_FN]))
            ticks.append(int(ring.meta[sl, pcm.F_AUX0]))
            tick_ns_l.append(int(ring.meta[sl, pcm.F_TICK]))
            tick_to_written.append(t1 - int(ring.meta[sl, pcm.F_TICK]))
        write_lat.append(t1 - t0)
        consumed += 1
        if gated:
            ring.set_cursor(0, nxt)
        nxt += 1
    rel_s = 0.0
    if vw is not None:
        r0 = time.perf_counter(); vw.release(); rel_s = time.perf_counter() - r0
    fns_a = np.asarray(fns)
    out_q.put(dict(cam=cam, backend=backend, consumed=consumed, recorded=len(fns), lost_lapped=lost_lapped,
                   consecutive=bool(len(fns) < 2 or np.all(np.diff(fns_a) == 1)), max_lag_slots=max_lag,
                   lag_p99_slots=float(np.percentile(lags, 99)) if lags else 0, lag_median_slots=float(np.median(lags)) if lags else 0,
                   write=pcm.stats_ms(write_lat), tick_to_written=pcm.stats_ms(tick_to_written), release_s=rel_s,
                   fns_first_last=(int(fns_a[0]), int(fns_a[-1])) if len(fns) else None,
                   ticks=ticks if vw is not None else None,
                   fns=fns if os.environ.get("P3_KEEP_FNS") == "1" else None,
                   tick_ns=tick_ns_l if os.environ.get("P3_KEEP_FNS") == "1" else None))
    ring.close()


def verify_video(path, h, w, cam, n_expected, ticks):
    """Decode the file; every 10th decoded frame n must best-match synthetic frame (ticks[n] % 30) - the content the
    camera put into the slot for that frame - by a clear margin. Catches slot reuse / torn hand-offs."""
    import cv2
    import proto_common as pcm
    frames = pcm.synthetic_frames(h, w, n=30, seed=cam, noise=8)
    small = np.stack([cv2.resize(f, (w // 8, h // 8), interpolation=cv2.INTER_AREA).astype(np.int16) for f in frames])
    cap = cv2.VideoCapture(str(path))
    n = 0
    bad = 0
    checked = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        if n % 10 == 0 and ticks is not None and n < len(ticks):
            s = cv2.resize(img, (w // 8, h // 8), interpolation=cv2.INTER_AREA).astype(np.int16)
            d = np.abs(small - s).mean(axis=(1, 2, 3))
            want = ticks[n] % 30
            o = np.sort(d)
            checked += 1
            if not (int(np.argmin(d)) == want and o[0] < 0.7 * o[1]):
                bad += 1
        n += 1
    cap.release()
    return dict(decoded_frames=n, expected=n_expected, content_checked=checked, content_mismatch=bad,
                bytes=Path(path).stat().st_size)


def run(size_name, L, policy, mode, stall_ms, stall_at_s, run_s, stall_only_cam0=False, lockstep=False):
    import proto_common as pcm
    h, w = pcm.SIZES[size_name]
    ctx = mp.get_context("spawn")
    from multiprocessing import shared_memory as _shm
    cnt_shm = _shm.SharedMemory(create=True, size=8 * N_CAMS) if lockstep else None
    if cnt_shm is not None:
        np.ndarray((N_CAMS,), np.int64, buffer=cnt_shm.buf)[:] = 0
    rings = [pcm.SeqRing.create(L, h * w * 3, prefault=True) for _ in range(N_CAMS)]
    ready_q, out_cam, out_rec = ctx.Queue(), ctx.Queue(), ctx.Queue()
    go, stop = ctx.Event(), ctx.Event()
    vids = [pcm.SCRATCH_TMP / f"p3_{size_name}_{L}_{policy}_{mode}_cam{i}.mp4" for i in range(N_CAMS)]
    cams = [ctx.Process(target=camera, args=(rings[i].spec(), i, h, w, policy, run_s, ready_q, go, out_cam,
                                             cnt_shm.name if cnt_shm else None)) for i in range(N_CAMS)]
    recs = [ctx.Process(target=recorder, args=(rings[i].spec(), i, h, w, policy, mode, stall_at_s,
                                               (stall_ms if (i == 0 or not stall_only_cam0) else 0), vids[i],
                                               ready_q, go, stop, out_rec)) for i in range(N_CAMS)]
    for p in cams + recs:
        p.start()
    for _ in cams + recs:
        ready_q.get(timeout=300)
    cpu_samples = []
    import threading
    cpu_stop = threading.Event()
    th = threading.Thread(target=pcm.cpu_sampler, args=([p.pid for p in cams + recs], cpu_stop, cpu_samples), daemon=True)
    th.start()
    go.set()
    cres = sorted([out_cam.get(timeout=run_s + 120) for _ in cams], key=lambda r: r["cam"])
    stop.set()
    rres = sorted([out_rec.get(timeout=300) for _ in recs], key=lambda r: r["cam"])
    cpu_stop.set()
    for p in cams + recs:
        p.join(30)
    for r in rings:
        r.close()
    if cnt_shm is not None:
        cnt_shm.close()
        cnt_shm.unlink()
    sync = None
    if all(r.get("fns") is not None for r in rres):
        n = min(len(r["fns"]) for r in rres)
        same_set = all(r["fns"][:n] == rres[0]["fns"][:n] for r in rres)
        T = np.array([r["tick_ns"][:n] for r in rres], np.int64)
        spr = T.max(0) - T.min(0)
        sync = dict(common_frames=n, recorded_per_cam=[len(r["fns"]) for r in rres], same_frame_numbers_over_common_range=bool(same_set),
                    tick_spread=pcm.stats_ms(spr), frames_with_tick_spread_ge_1_period=int((spr >= 1e9 / FPS).sum()))
        for r in rres:
            r.pop("fns", None)
            r.pop("tick_ns", None)
    cpu = pcm.summarize_cpu(cpu_samples)
    files = []
    if mode == "msmf":
        for i, v in enumerate(vids):
            files.append(verify_video(v, h, w, i, cres[i]["produced"], rres[i].get("ticks")))
    for r in rres:
        r.pop("ticks", None)
    for v in vids:
        if v.exists():
            v.unlink()
    lost_total = sum(r["lost_lapped"] for r in rres)
    return dict(size=size_name, L=L, policy=policy, mode=mode, stall_ms=stall_ms, stall_at_s=stall_at_s, run_s=run_s,
                stall_only_cam0=stall_only_cam0, lockstep=lockstep, sync=sync,
                ring_seconds_at_60fps=L / FPS, cameras=cres, recorders=rres, files=files, cpu=cpu,
                produced_total=sum(c["produced"] for c in cres), recorded_total=sum(r["recorded"] for r in rres),
                recorder_lost_total=lost_total, ring_full_drops_total=sum(c["ring_full_drops"] for c in cres),
                sensor_skipped_total=sum(c["sensor_skipped"] for c in cres),
                blocked_s_max=max(c["blocked_s"] for c in cres), max_lag_slots=max(r["max_lag_slots"] for r in rres),
                all_consecutive=all(r["consecutive"] for r in rres),
                lossless_on_disk_path=(lost_total == 0 and all(r["consecutive"] for r in rres)
                                       and sum(r["recorded"] for r in rres) == sum(c["produced"] for c in cres)))


def main():
    import proto_common as pcm
    if "ASYM" in sys.argv[1:]:
        return main_asym()
    parts = [a for a in sys.argv[1:] if a in ("A", "B")] or ["A", "B"]
    out_path = "p3_lossless_record.json"
    prev = {}
    if (pcm.RESULTS / out_path).exists():
        import json
        prev = json.loads((pcm.RESULTS / out_path).read_text())
    out = dict(env=pcm.env_summary(), part_a=prev.get("part_a", []), part_b=prev.get("part_b", []))
    if "A" in parts:
        out["part_a"] = []
        for L in (16, 64, 172):
            for stall in (200, 1000, 2500, 3500):
                for pol in ("overwrite", "block", "drop"):
                    r = run("1080p", L, pol, "busy", stall, 3.0, 8.0)
                    out["part_a"].append(r)
                    pcm.write_json(out_path, out)
                    print(f"A L={L} stall={stall} {pol}: produced {r['produced_total']} recorded {r['recorded_total']} "
                          f"recorder_lost {r['recorder_lost_total']} ring_full_drops {r['ring_full_drops_total']} "
                          f"sensor_skipped {r['sensor_skipped_total']} blocked_max {r['blocked_s_max']:.2f}s maxlag {r['max_lag_slots']} "
                          f"consecutive {r['all_consecutive']}", flush=True)
    if "B" in parts:
        out["part_b"] = []
        for size_name in ("1080p", "720p"):
            L = 172 if size_name == "1080p" else 388
            r = run(size_name, L, "block", "msmf", 1500, 8.0, 20.0)
            out["part_b"].append(r)
            pcm.write_json(out_path, out)
            print(f"B {size_name} L={L}: produced {r['produced_total']} recorded {r['recorded_total']} lost {r['recorder_lost_total']} "
                  f"sensor_skipped {r['sensor_skipped_total']} maxlag {r['max_lag_slots']} files "
                  f"{[(f['decoded_frames'], f['expected'], f['content_mismatch']) for f in r['files']]} cpu {r['cpu'] and r['cpu']['sum_processes']:.0f}%",
                  flush=True)
    write_md(out)
    sys.stdout.flush()
    os._exit(0)


def main_asym():
    import proto_common as pcm
    os.environ["P3_KEEP_FNS"] = "1"
    out = dict(env=pcm.env_summary(), rows=[])
    for stall in (1000, 3500):
        for pol, lock in (("block", False), ("drop", False), ("block", True)):
            r = run("1080p", 172, pol, "busy", stall, 3.0, 8.0, stall_only_cam0=True, lockstep=lock)
            out["rows"].append(r)
            pcm.write_json("p3v_asymmetric_stall.json", out)
            sy = r["sync"]
            print(f"ASYM stall={stall} {pol}{'+lockstep' if lock else ''}: produced {[c['produced'] for c in r['cameras']]} "
                  f"recorded {sy['recorded_per_cam']} drops {r['ring_full_drops_total']} sensor_skipped {[c['sensor_skipped'] for c in r['cameras']]} "
                  f"same_set {sy['same_frame_numbers_over_common_range']} tick spread med/p99/max {sy['tick_spread']['median_ms']:.1f}/"
                  f"{sy['tick_spread']['p99_ms']:.1f}/{sy['tick_spread']['max_ms']:.1f} ms, frames >=1 period {sy['frames_with_tick_spread_ge_1_period']}", flush=True)
    L = ["# P3 ASYM - one recorder (camera 0) stalls, the other 4 do not: 1080p, L=172 (2.87 s), 2 ms busy recorders, stall at t=3 s, 8 s runs", "",
         "`tick spread` = per recorded frame number k, max - min over the 5 cameras of the sensor tick time of frame k. A spread >= 16.7 ms "
         "means the cameras' frame k were captured at least one frame period apart (the multiframe is out of sync, although every "
         "frame count check would pass).", "",
         "| stall ms (cam 0 only) | policy | lockstep gate | produced per cam | recorded per cam | ring-full drops | sensor skipped per cam | same frame numbers (common range) | tick spread median / p99 / max ms | frames with spread >= 1 period | recorder lost |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in out["rows"]:
        sy = r["sync"]
        L.append(f"| {r['stall_ms']} | {r['policy']} | {r['lockstep']} | {[c['produced'] for c in r['cameras']]} | {sy['recorded_per_cam']} | "
                 f"{r['ring_full_drops_total']} | {[c['sensor_skipped'] for c in r['cameras']]} | {sy['same_frame_numbers_over_common_range']} | "
                 f"{sy['tick_spread']['median_ms']:.1f} / {sy['tick_spread']['p99_ms']:.1f} / {sy['tick_spread']['max_ms']:.1f} | "
                 f"{sy['frames_with_tick_spread_ge_1_period']} | {r['recorder_lost_total']} |")
    pcm.write_text("p3v_asymmetric_stall.md", "\n".join(L) + "\n")
    print("\n".join(L))
    sys.stdout.flush()
    os._exit(0)


def write_md(out):
    import proto_common as pcm
    L = ["# P3 - lossless record path (decoupled recorder, gated cursor) vs current overwrite policy", "",
         "## A. Stall-tolerance sweep: 5 cameras 1080p @60 fps, 5 recorders (2 ms synthetic work), one simultaneous stall at t=3 s, 8 s runs", "",
         "Totals over 5 cameras. `recorder lost` = frames the recorder never got (lapped; overwrite policy). `ring-full drops` = frames the "
         "camera explicitly skipped (drop policy). `sensor skipped` = sensor ticks never grabbed (includes block-policy back-pressure; "
         "~0-5 per run is scheduler noise).", "",
         "| L (s @60) | stall ms | policy | produced | recorded | recorder lost (silent today) | ring-full drops (explicit) | sensor skipped | max blocked s | max lag slots | consecutive | lossless after ring |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in out.get("part_a", []):
        L.append(f"| {r['L']} ({r['ring_seconds_at_60fps']:.2f}) | {r['stall_ms']} | {r['policy']} | {r['produced_total']} | {r['recorded_total']} | "
                 f"{r['recorder_lost_total']} | {r['ring_full_drops_total']} | {r['sensor_skipped_total']} | {r['blocked_s_max']:.2f} | "
                 f"{r['max_lag_slots']} | {r['all_consecutive']} | {r['lossless_on_disk_path']} |")
    L += ["", "## B. Real encoder (cv2 'X264' -> MSMF H.264) as a decoupled recorder, block policy, 20 s, one 1500 ms stall at t=8 s", "",
          "| size | L | produced | recorded | lost | sensor skipped | max lag slots | lag p99 (worst cam) | write() median / p99 / max ms (worst cam) | tick->written median / p99 ms | files decoded == produced | content mismatches (checked) | release s | CPU sum % (cams+recorders) |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in out.get("part_b", []):
        wr = max(r["recorders"], key=lambda x: x["write"]["p99_ms"])
        tw = max(r["recorders"], key=lambda x: x["tick_to_written"]["p99_ms"])
        files_ok = all(f["decoded_frames"] == f["expected"] for f in r["files"])
        L.append(f"| {r['size']} | {r['L']} | {r['produced_total']} | {r['recorded_total']} | {r['recorder_lost_total']} | {r['sensor_skipped_total']} | "
                 f"{r['max_lag_slots']} | {max(x['lag_p99_slots'] for x in r['recorders']):.0f} | {wr['write']['median_ms']:.2f} / {wr['write']['p99_ms']:.2f} / {wr['write']['max_ms']:.2f} | "
                 f"{tw['tick_to_written']['median_ms']:.1f} / {tw['tick_to_written']['p99_ms']:.1f} | {files_ok} "
                 f"({[f['decoded_frames'] for f in r['files']]}) | {sum(f['content_mismatch'] for f in r['files'])} of {sum(f['content_checked'] for f in r['files'])} | "
                 f"{max(x['release_s'] for x in r['recorders']):.2f} | {r['cpu']['sum_processes'] if r['cpu'] else float('nan'):.0f} |")
    pcm.write_text("p3_lossless_record.md", "\n".join(L) + "\n")


if __name__ == "__main__":
    main()
