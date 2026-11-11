# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "psutil==7.2.2"]
# ///
"""BENCHMARK (timing): N concurrent encode streams through PyAV 19.0.2 (adapted from gpu_encode/bench_pyav_concurrent.py).

One thread + one CodecContext per stream (PyAV releases the GIL in avcodec_send_frame). Each stream builds its
input every iteration like a camera loop: --source nv12 (VideoFrame.from_ndarray of NV12 made from real YUY2
frames) or mjpeg_cpu (per-stream CPU mjpeg decode of real camera JPEGs + reformat to nv12) or mjpeg_qsv.
Packets are discarded (bytes counted).
Modes: unpaced (as fast as possible) and paced (each stream at --fps; late = encode call returned after the next
frame was due). Reports per N: streams opened, first open error (session limit), aggregate fps, per-stream fps
min/median, encode-call latency p50/p99, late frames, process CPU s and CPU ms per frame, nvidia-smi samples.
--limit-probe M: before the timed runs, open up to M encoders one by one (each encodes 2 frames and stays open)
and record how many opened and the first error text (the actual session limit on this machine).
Background load (10 s typeperf, top processes, nvidia-smi sessions) recorded before the first run.

Run from the repo root on a QUIET machine, one bench at a time:
  uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_concurrent.py \
      --codec h264_qsv --size 1080p --streams 1,4,8,16 --frames 600 --mode unpaced,paced --gop intra --limit-probe 32
Smoke (numbers discarded): --streams 1,2 --frames 10 --mode unpaced --limit-probe 3 --outdir <scratchpad> --no-bg
Writes results/hw_accel_target/bench/concurrent_<codec>_<size>_<source>_<UTC>.json
"""
from __future__ import annotations

import argparse
import statistics
import sys
import threading
import time
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from av.video.frame import PictureType
import psutil

sys.path.insert(0, str(Path(__file__).parent))
import benchlib  # noqa: E402
from benchlib import GpuSampler, background_load, jpeg_list, nv12_arrays, snapshot  # noqa: E402
from common import nvenc_sessions  # noqa: E402

DIMS = {"720p": (1280, 720), "1080p": (1920, 1080)}
OPTS = {"nvenc": {"preset": "p4", "tune": "ll"}, "_mf": {"hw_encoding": "1"}}


def make_ctx(codec: str, w: int, h: int, gop: str):
    kw = {}
    if "d3d12va" in codec:
        from av.codec.hwaccel import HWAccel  # noqa: PLC0415
        kw["hwaccel"] = HWAccel("d3d12va")
    cc = av.CodecContext.create(codec, "w", **kw)
    cc.width, cc.height, cc.pix_fmt = w, h, "nv12"
    cc.time_base = Fraction(1, 30)
    cc.framerate = Fraction(30, 1)
    cc.max_b_frames = 0
    cc.gop_size = (0 if "nvenc" in codec else 1) if gop == "intra" else 30
    for k, v in OPTS.items():
        if k in codec:
            cc.options = dict(v)
    cc.open()
    return cc


class Feed:
    def __init__(self, source: str, size: str, shared):
        self.source, self.shared, self.i = source, shared, 0
        if source.startswith("mjpeg"):
            self.dec = av.CodecContext.create({"mjpeg_cpu": "mjpeg", "mjpeg_qsv": "mjpeg_qsv"}[source], "r")
            self.pending: list = []

    def next(self) -> av.VideoFrame:
        k = self.i % len(self.shared)
        self.i += 1
        if self.source == "nv12":
            return av.VideoFrame.from_ndarray(self.shared[k], format="nv12")
        while not self.pending:
            self.pending += list(self.dec.decode(av.Packet(self.shared[k])))
            k = self.i % len(self.shared)
            self.i += 1
        f = self.pending.pop(0)
        # full-range JPEG samples -> limited-range NV12 (PyAV keeps full range unless told; see NOTES_functional)
        g = f if f.format.name == "nv12" else f.reformat(format="nv12", dst_color_range=1)
        # decoded MJPEG frames carry pict_type=I and reformat() copies it; encoders would then make every
        # frame a keyframe (measured: functional_pyav19.md, stage gop_pictreset). Reset so gop30 is real.
        g.pict_type = PictureType.NONE
        return g


def worker(cc, feed, n, fps, paced, res, barrier):
    lat, nbytes, late = [], 0, 0
    try:
        for i in range(5):  # warm-up, untimed
            f = feed.next()
            f.pts = i
            cc.encode(f)
    except Exception as e:  # noqa: BLE001
        res.append({"error": f"{type(e).__name__}: {e}"[:200]})
        barrier.wait()
        return
    barrier.wait()
    t0 = time.perf_counter()
    err = None
    for i in range(n):
        if paced:
            d = t0 + i / fps - time.perf_counter()
            if d > 0:
                time.sleep(d)
        try:
            f = feed.next()
            f.pts = i + 5
            a = time.perf_counter()
            for p in cc.encode(f):
                nbytes += p.size
            b = time.perf_counter()
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"[:200]
            break
        lat.append(b - a)
        if paced and b > t0 + (i + 1) / fps:
            late += 1
    try:
        for p in cc.encode(None):
            nbytes += p.size
    except Exception:  # noqa: BLE001
        pass
    res.append({"frames": len(lat), "seconds": time.perf_counter() - t0, "bytes": nbytes, "late": late,
                "lat": lat, "error": err})


def run_n(a, n_streams, paced, gop, shared) -> dict:
    w, h = DIMS[a.size]
    ctxs, open_err = [], None
    for _ in range(n_streams):
        try:
            ctxs.append(make_ctx(a.codec, w, h, gop))
        except Exception as e:  # noqa: BLE001
            open_err = f"{type(e).__name__}: {e}"[:200]
            break
    sess_open = nvenc_sessions()
    res: list[dict] = []
    barrier = threading.Barrier(len(ctxs) + 1)
    ths = [threading.Thread(target=worker, args=(c, Feed(a.source, a.size, shared), a.frames, a.fps, paced, res,
                                                 barrier)) for c in ctxs]
    proc = psutil.Process()
    for t in ths:
        t.start()
    with GpuSampler() as gs:
        barrier.wait()
        c0 = proc.cpu_times()
        t0 = time.perf_counter()
        for t in ths:
            t.join()
        wall = time.perf_counter() - t0
        c1 = proc.cpu_times()
    cpu = (c1.user - c0.user) + (c1.system - c0.system)
    out = {"codec": a.codec, "size": a.size, "source": a.source, "gop": gop, "paced": paced,
           "requested": n_streams, "opened": len(ctxs), "open_error": open_err, "nvenc_sessions_after_open": sess_open,
           "wall_s": round(wall, 3), "process_cpu_s": round(cpu, 3), "gpu": gs.summary(),
           "stream_errors": [r["error"] for r in res if r.get("error")]}
    good = [r for r in res if r.get("frames")]
    if good:
        tot = sum(r["frames"] for r in good)
        per = [r["frames"] / r["seconds"] for r in good]
        lat = sorted(x for r in good for x in r["lat"])
        out.update(total_frames=tot, aggregate_fps=round(tot / wall, 2), per_stream_fps_min=round(min(per), 2),
                   per_stream_fps_median=round(statistics.median(per), 2),
                   cpu_ms_per_frame=round(1000 * cpu / tot, 3), cpu_cores=round(cpu / wall, 3),
                   encode_ms_p50=round(1000 * lat[len(lat) // 2], 3),
                   encode_ms_p99=round(1000 * lat[min(len(lat) - 1, int(len(lat) * 0.99))], 3),
                   late_frames=sum(r["late"] for r in good),
                   mbit_s_per_stream_at_30fps=round(statistics.median(8 * r["bytes"] / r["frames"] * 30 / 1e6
                                                                      for r in good), 2))
    del ctxs
    return out


def limit_probe(a, shared, m: int) -> dict:
    w, h = DIMS[a.size]
    ctxs, err = [], None
    before = nvenc_sessions()
    for i in range(m):
        try:
            cc = make_ctx(a.codec, w, h, "intra")
            for j in range(2):
                f = av.VideoFrame.from_ndarray(shared[j % len(shared)], format="nv12") if a.source == "nv12" else \
                    av.VideoFrame.from_ndarray(nv12_arrays(a.size)[0], format="nv12")
                f.pts = j
                cc.encode(f)
            ctxs.append(cc)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"[:300]
            break
    peak = nvenc_sessions()
    out = {"max_tried": m, "opened": len(ctxs), "first_error": err, "nvenc_sessions_before": before,
           "nvenc_sessions_at_peak": peak}
    del ctxs
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codec", default="h264_qsv")
    ap.add_argument("--size", default="1080p")
    ap.add_argument("--source", default="nv12", choices=["nv12", "mjpeg_cpu", "mjpeg_qsv"])
    ap.add_argument("--gop", default="intra")
    ap.add_argument("--streams", default="1,4,8,16")
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--mode", default="unpaced,paced")
    ap.add_argument("--limit-probe", type=int, default=0)
    ap.add_argument("--outdir", default="")
    ap.add_argument("--no-bg", action="store_true")
    a = ap.parse_args()
    if a.outdir:
        benchlib.BENCH = Path(a.outdir)
    shared = nv12_arrays(a.size) if a.source == "nv12" else jpeg_list(a.size)
    out = {"bench": "concurrent", "args": vars(a), "system_before": snapshot(),
           "background_load_before": None if a.no_bg else background_load(), "runs": []}
    if a.limit_probe:
        out["limit_probe"] = limit_probe(a, nv12_arrays(a.size), a.limit_probe)
        print("limit_probe", out["limit_probe"])
    for gop in a.gop.split(","):
        for mode in a.mode.split(","):
            for n in map(int, a.streams.split(",")):
                r = run_n(a, n, mode == "paced", gop, shared)
                print({k: v for k, v in r.items() if k != "gpu"})
                out["runs"].append(r)
    out["system_after"] = snapshot()
    benchlib.write(f"concurrent_{a.codec}_{a.size}_{a.source}", out)


if __name__ == "__main__":
    main()
