"""P6 - UI tap: server-side build of the 5-camera UI payload, current pattern vs prototypes.

5 spawned writer processes publish at 60 fps (FakeSensor) into SeqRings whose slots hold a full SkellyCam frame record
(632 B frame_metadata + HxWx3 image, dtype from skellycam create_frame_dtype when available) AND the camera's q90 JPEG
bytes in a second byte ring (what an MJPEG-passthrough camera path would publish). The parent runs an asyncio loop
shaped like WebsocketServer._frontend_image_relay (await 10 ms, build, instant ack - no browser), 10 s per variant,
recording "event-loop blocked" = build time minus time awaited on the thread pool (the loop also serves HTTP control).
(A heartbeat task/thread was tried and rejected: any extra loop wake-up on Windows makes asyncio fire the relay's 10 ms
timer early, because timers within the 15.6 ms monotonic clock resolution are treated as due.)

  cur_copy_real        [S] np.copyto each slot into a private recarray (= get_latest_multiframe) + REAL
                           skellycam create_frontend_payload (resize 0.5, imencode q60, tobytes, assemble, slice copy);
                           no new-frame check (if_newer_than is ignored today)
  view_real            [S] recarray VIEWS on the slots (0 copies out) + REAL create_frontend_payload + seqlock validate
  view_proto               views -> cv2.resize(dst=preallocated, 0.5) -> cv2.imencode q60 -> assemble into a
                           per-connection buffer via memoryview (no tobytes, no final slice copy) -> validate;
                           latest-frame-wins: skip the build if no camera has a new frame
  view_proto_640x360       same, target 640x360 (display-size downscale before encode)
  view_proto_threads       view_proto with the 5 per-camera resize+encode jobs in a ThreadPoolExecutor(5), awaited
                           (event loop not blocked; cv2 releases the GIL)
  view_proto_threads_poll2ms   same, but the relay polls every 2 ms instead of 10 ms (finer latest-wins sampling)
  view_simplejpeg      [B] view_proto with simplejpeg.encode_jpeg (libjpeg-turbo; stand-in for PyTurboJPEG, whose DLL is
                           not installed here) instead of cv2.imencode
  jpeg_forward             MJPEG passthrough: assemble the cameras' own JPEG bytes, no decode, no encode (full res)
  jpeg_reduced_reencode    MJPEG passthrough: cv2.imdecode(IMREAD_REDUCED_COLOR_2) of the camera JPEG -> imencode q60
  jpeg_reduced_reencode_threads   same, 5 jobs in a ThreadPoolExecutor(5)

Run: .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\prototypes\\p6_ui_path.py    (variants [S])
     benchmarks\\frame_pipeline\\.venv-bench\\Scripts\\python.exe benchmarks\\frame_pipeline\\prototypes\\p6_ui_path.py   (variant [B] + cross-checks)
     .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\prototypes\\p6_ui_path.py --summarize
"""
from __future__ import annotations

import asyncio
import multiprocessing as mp
import multiprocessing.queues  # noqa: F401
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

N_CAMS = 5
FPS = 60.0
RUN_S = float(os.environ.get("P6_RUN_S", "10"))
META = 632
JPEG_SLOT = 1 << 20


def have(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def writer(spec, jspec, cam, h, w, ready_q, stop):
    import cv2
    import proto_common as pcm
    ring = pcm.SeqRing.attach(spec)
    jring = pcm.SeqRing.attach(jspec)
    frames = pcm.synthetic_frames(h, w, n=30, seed=cam, noise=8)
    jpegs = [cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1] for f in frames]
    n = h * w * 3
    sensor = pcm.FakeSensor(FPS, seed=cam)
    ready_q.put(cam)
    k = 0
    while not stop.is_set():
        tick, t = sensor.grab()
        s = ring.begin(k)
        np.copyto(ring.payload[s, META:META + n].reshape(h, w, 3), frames[tick % 30])
        ring.commit(k, s, frame_number=k, tick_ns=t)
        j = jpegs[tick % 30]
        s2 = jring.begin(k)
        jring.bytes_view(s2, j.size)[:] = j
        jring.commit(k, s2, frame_number=k, tick_ns=t, nbytes=j.size)
        k += 1
    ring.close(); jring.close()


class Builder:
    def __init__(self, rings, jrings, h, w, variant):
        import cv2
        self.cv2 = cv2
        self.rings, self.jrings, self.h, self.w, self.v = rings, jrings, h, w, variant
        self.n = h * w * 3
        tw, th = (640, 360) if variant == "view_proto_640x360" else (w // 2, h // 2)
        self.tw, self.th = tw, th
        self.small = [np.empty((th, tw, 3), np.uint8) for _ in rings]
        self.out = [bytearray(16 << 20), bytearray(16 << 20)]  # double-buffered per-connection payload buffers
        self.flip = 0
        self.last_heads = [-1] * len(rings)
        self.pool = ThreadPoolExecutor(len(rings)) if ("_threads" in variant) else None
        self.rec = None
        if variant in ("cur_copy_real", "view_real"):
            import bench_common as bc
            from skellycam.core.types.frame_dtype_factories import create_frame_dtype
            from skellycam.core.types.frontend_payload_bytearray import create_frontend_payload
            self.cfp = create_frontend_payload
            self.cfgs = [bc.make_config(i, h, w) for i in range(len(rings))]
            self.dtype = create_frame_dtype(self.cfgs[0])
            assert self.dtype.itemsize == META + self.n, (self.dtype.itemsize, META + self.n)
            self.priv = {str(i): bc.make_frame_recarray(self.cfgs[i]) for i in range(len(rings))}
            # metadata template so the views carry valid camera_info
            for i, r in enumerate(rings):
                for s in range(r.L):
                    r.payload[s, :META] = self.priv[str(i)].view(np.uint8)[:META]
        if variant == "view_simplejpeg":
            import simplejpeg
            self.sj = simplejpeg
        self.copies = 0
        self.awaited_ns = 0

    def heads(self):
        return [r.head for r in self.rings]

    def _acquire(self):
        rs = self.jrings if self.v.startswith("jpeg_") else self.rings
        ks = [r.head for r in rs]
        seqs = [int(r.meta[k % r.L, 0]) for r, k in zip(rs, ks)]
        return ks, seqs

    def _valid(self, ks, seqs):
        return all(s == 2 * k + 2 and int(r.meta[k % r.L, 0]) == s for r, k, s in zip(self.rings, ks, seqs))

    def _img(self, i, k):
        r = self.rings[i]
        return r.payload[k % r.L, META:META + self.n].reshape(self.h, self.w, 3)

    def _encode_one(self, i, k):
        cv2 = self.cv2
        if self.v.startswith("jpeg_"):
            jr = self.jrings[i]
            sl = k % jr.L
            jb = jr.bytes_view(sl, int(jr.meta[sl, 4]))
            if self.v == "jpeg_forward":  # (the camera's own bytes, zero-copy view)
                return jb
            red = cv2.imdecode(jb, cv2.IMREAD_REDUCED_COLOR_2)
            return cv2.imencode(".jpg", red, [int(cv2.IMWRITE_JPEG_QUALITY), 60])[1]
        cv2.resize(self._img(i, k), (self.tw, self.th), dst=self.small[i], interpolation=cv2.INTER_LINEAR)
        if self.v == "view_simplejpeg":
            return self.sj.encode_jpeg(self.small[i], quality=60, colorspace="BGR")
        return cv2.imencode(".jpg", self.small[i], [int(cv2.IMWRITE_JPEG_QUALITY), 60])[1]

    async def build(self, loop):
        """returns (payload_len or None if skipped, valid, distinct)"""
        v = self.v
        if v in ("cur_copy_real", "view_real"):
            ks = self.heads()
            k = min(ks)  # latest complete multiframe = min(last_written_index) as in camera_group_shared_memory.py L33-35
            seqs = [int(r.meta[k % r.L, 0]) for r in self.rings]
            frames = {}
            for i, r in enumerate(self.rings):
                slot = r.payload[k % r.L, :META + self.n]
                recv = np.ndarray((1,), dtype=self.dtype, buffer=slot).view(np.recarray)
                if v == "cur_copy_real":
                    np.copyto(self.priv[str(i)], recv)  # get_data_by_index's np.copyto into a reused recarray
                    frames[str(i)] = self.priv[str(i)]
                else:
                    frames[str(i)] = recv
            fn, ts, payload = self.cfp(frames, None)
            valid = all(s == 2 * k + 2 and int(r.meta[k % r.L, 0]) == s for r, s in zip(self.rings, seqs))
            distinct = k != self.last_heads[0]
            self.last_heads = [k] * len(self.rings)
            return len(payload), valid, distinct
        ks, seqs = self._acquire()
        if any(k <= lk for k, lk in zip(ks, self.last_heads)):
            return None, True, False  # latest-frame-wins: build only when EVERY camera has a newer frame (<= 60/s)
        if self.pool is not None:
            t_aw = time.perf_counter_ns()
            parts = await asyncio.gather(*[loop.run_in_executor(self.pool, self._encode_one, i, k) for i, k in enumerate(ks)])
            self.awaited_ns = time.perf_counter_ns() - t_aw
        else:
            parts = [self._encode_one(i, k) for i, k in enumerate(ks)]
        rs = self.jrings if v.startswith("jpeg_") else self.rings
        valid = all(s == 2 * k + 2 and int(r.meta[k % r.L, 0]) == s for r, k, s in zip(rs, ks, seqs))
        buf = self.out[self.flip]
        self.flip ^= 1
        mv = memoryview(buf)
        pos = 24
        for p in parts:
            b = memoryview(p).cast("B") if not isinstance(p, (bytes, bytearray)) else memoryview(p)
            mv[pos:pos + 56] = b"\0" * 56
            pos += 56
            mv[pos:pos + len(b)] = b
            pos += len(b)
        mv[pos:pos + 24] = b"\0" * 24
        pos += 24
        self.last_heads = ks
        return pos, valid, True


async def run_variant(rings, jrings, h, w, variant):
    import proto_common as pcm
    b = Builder(rings, jrings, h, w, variant)
    loop = asyncio.get_running_loop()
    build_ns, sizes, blocked_ns = [], [], []
    n_pay = n_distinct = n_skip = n_invalid = 0
    t_end = time.perf_counter() + RUN_S
    t0 = time.perf_counter()
    cpu0 = time.process_time()
    poll_s = 0.002 if variant.endswith("_poll2ms") else 0.01
    while time.perf_counter() < t_end:
        await asyncio.sleep(poll_s)
        a = time.perf_counter_ns()
        size, valid, distinct = await b.build(loop)
        e = time.perf_counter_ns()
        if size is None:
            n_skip += 1
            continue
        build_ns.append(e - a); sizes.append(size); blocked_ns.append(e - a - b.awaited_ns)
        n_pay += 1
        n_distinct += int(distinct)
        n_invalid += int(not valid)
    el = time.perf_counter() - t0
    cpu = time.process_time() - cpu0
    if b.pool:
        b.pool.shutdown()
    return dict(variant=variant, payloads_per_s=n_pay / el, distinct_per_s=n_distinct / el, skipped_no_new_frame=n_skip,
                invalid_seqlock=n_invalid, build=pcm.stats_ms(build_ns), payload_kb_median=float(np.median(sizes)) / 1e3 if sizes else None,
                loop_blocked=pcm.stats_ms(blocked_ns), main_cpu_pct=100 * cpu / el)


COPIES = {"cur_copy_real": "5 full frames out of shm + 5 resize outputs (alloc) + JPEG x3 (tobytes, assemble, slice)",
          "view_real": "0 out of shm; 5 resize outputs (alloc); JPEG x3",
          "view_proto": "0 out of shm; resize into preallocated dst; JPEG x1 (assemble)",
          "view_proto_640x360": "same as view_proto", "view_proto_threads": "same as view_proto",
          "view_proto_threads_poll2ms": "same as view_proto",
          "view_simplejpeg": "same as view_proto", "jpeg_forward": "0 pixel copies; camera JPEG x1 (assemble)",
          "jpeg_reduced_reencode": "0 full-res frames; reduced decode + encode; JPEG x1",
          "jpeg_reduced_reencode_threads": "same as jpeg_reduced_reencode"}


def main():
    import proto_common as pcm
    if "--summarize" in sys.argv:
        return summarize()
    sk, sj = have("skellycam"), have("simplejpeg")
    tag = "skellycamvenv" if sk else "benchvenv"
    variants = (["cur_copy_real", "view_real"] if sk else []) + ["view_proto", "view_proto_640x360", "view_proto_threads", "view_proto_threads_poll2ms"] + \
               (["view_simplejpeg"] if sj else []) + ["jpeg_forward", "jpeg_reduced_reencode", "jpeg_reduced_reencode_threads"]
    if not sk:
        variants = ["view_proto", "view_simplejpeg"]
    ctx = mp.get_context("spawn")
    out = dict(env=pcm.env_summary(), run_s=RUN_S, rows=[])
    for size_name in ("1080p", "720p"):
        h, w = pcm.SIZES[size_name]
        L = (1024 ** 3) // (META + h * w * 3)
        rings = [pcm.SeqRing.create(L, META + h * w * 3, prefault=True) for _ in range(N_CAMS)]
        jrings = [pcm.SeqRing.create(256, JPEG_SLOT, prefault=True) for _ in range(N_CAMS)]
        rq, stop = ctx.Queue(), ctx.Event()
        procs = [ctx.Process(target=writer, args=(rings[i].spec(), jrings[i].spec(), i, h, w, rq, stop)) for i in range(N_CAMS)]
        for p in procs:
            p.start()
        for _ in procs:
            rq.get(timeout=120)
        time.sleep(2.0)
        for v in variants:
            r = asyncio.run(run_variant(rings, jrings, h, w, v))
            r.update(size=size_name, venv=tag, copies=COPIES[v])
            out["rows"].append(r)
            pcm.write_json(os.environ.get("P6_OUT", f"p6_ui_{tag}") + ".json", out)  # P6_OUT: REVISION-stage repeats (2026-10-28)
            print(f"{size_name} {v}: {r['payloads_per_s']:.1f} payloads/s ({r['distinct_per_s']:.1f} distinct), build {r['build']['median_ms']:.2f}/"
                  f"{r['build']['p99_ms']:.2f} ms, loop blocked p99 {r['loop_blocked']['p99_ms']:.2f} max {r['loop_blocked']['max_ms']:.2f} ms, "
                  f"{r['payload_kb_median']:.0f} KB, invalid {r['invalid_seqlock']}, cpu {r['main_cpu_pct']:.0f}%", flush=True)
        stop.set()
        for p in procs:
            p.join(30)
        for r in rings + jrings:
            r.close()
    sys.stdout.flush()
    os._exit(0)


def summarize():
    import json
    import proto_common as pcm
    rows = []
    for tag in ("skellycamvenv", "benchvenv"):
        p = pcm.RESULTS / f"p6_ui_{tag}.json"
        if p.exists():
            rows += json.loads(p.read_text())["rows"]
    L = ["# P6 - UI tap server-side build (5 cameras, 60 fps writers, relay-shaped 10 ms loop, instant ack, no browser)", "",
         f"{RUN_S}s per variant. `event-loop blocked` = build time minus time spent awaiting the thread pool "
         "(the loop also serves HTTP recording start/stop). CPU = main process only.", "",
         "| size | variant | venv | payloads/s | distinct/s | build median / p99 ms | event-loop blocked per payload median / p99 / max ms | payload KB | seqlock invalid | main CPU % | copies |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['size']} | {r['variant']} | {r['venv']} | {r['payloads_per_s']:.1f} | {r['distinct_per_s']:.1f} | "
                 f"{r['build']['median_ms']:.2f} / {r['build']['p99_ms']:.2f} | {r['loop_blocked']['median_ms']:.2f} / {r['loop_blocked']['p99_ms']:.2f} / {r['loop_blocked']['max_ms']:.2f} | "
                 f"{r['payload_kb_median']:.0f} | {r['invalid_seqlock']} | {r['main_cpu_pct']:.0f} | {r['copies']} |")
    L += ["", "Baseline (baseline/results/d_ui.md, idle 20261027 re-run, real SkellyCam ring + get_latest_multiframe + create_frontend_payload): "
          "1080p 46.0 payloads/s, total 9.39 ms median / 17.43 p99, main CPU 106%; 720p 60.5 payloads/s, 4.70 ms. FreeMoCap by-number path 1080p 41.7/s, 12.87 ms. "
          "No-sleep maximum: 1080p 110.3 payloads/s (60.0 distinct), 8.84 ms.",
          "Note: jpeg_forward payload size reflects the synthetic q90 JPEGs (~540 KB at 1080p); real cameras measured ~160-167 KB/frame "
          "(research: c922 720p60, C930e 1080p30)."]
    pcm.write_text("p6_ui_path.md", "\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
