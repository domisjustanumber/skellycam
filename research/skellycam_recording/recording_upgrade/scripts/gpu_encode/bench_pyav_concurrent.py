# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "psutil==7.2.2"]
# ///
"""BENCHMARK (timing): N concurrent hardware encode streams from Python (PyAV), one thread + encoder per stream.

Per stream: its own CodecContext (h264_nvenc / hevc_nvenc with sw frames; h264_d3d12va / hevc_d3d12va via
HWAccel('d3d12va')), frames built from numpy NV12 each iteration (VideoFrame.from_ndarray, like a camera
loop would), packets discarded (bytes counted). PyAV releases the GIL in avcodec_send_frame.
Modes: unpaced (as fast as possible) and paced (each stream at --fps; counts late frames = encode call
returned after the next frame's due time).
Reports per N: streams opened, open errors (session limit), aggregate fps, per-stream fps min/median,
encode() call latency p50/p99, process CPU (psutil, 100 = 1 core), nvidia-smi samples.

Run (repo root, quiet machine; PyAV 18 = skellycam venv):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/bench_pyav_concurrent.py --codec h264_nvenc --size 1080p --streams 1,2,4,8,12,16 --frames 600 --mode unpaced,paced
Smoke: ... --codec h264_nvenc --size 720p --streams 1,2 --frames 20 --mode unpaced --smoke
PyAV 19.0.2 (isolated): uv run --script <same path> <same args>
Writes results/gpu_encode/bench/pyav_concurrent_<codec>_<size>_<UTC>.json.
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

sys.path.insert(0, str(Path(__file__).parent))
from benchlib import GpuSampler, snapshot, write  # noqa: E402
from common import prepare_inputs  # noqa: E402

SIZES = {"720p": ("nv12_720p", 1280, 720), "1080p": ("nv12_1080p", 1920, 1080)}


def load(size: str) -> list[np.ndarray]:
    key, w, h = SIZES[size]
    raw = Path(prepare_inputs()[key]).read_bytes()
    fs = w * h * 3 // 2
    return [np.frombuffer(raw[i * fs:(i + 1) * fs], np.uint8).reshape(h * 3 // 2, w) for i in range(len(raw) // fs)]


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
    if gop == "intra":
        cc.gop_size = 0 if "nvenc" in codec else 1
    else:
        cc.gop_size = 15
    if "nvenc" in codec:
        cc.options = {"preset": "p4", "tune": "ll"}
    cc.open()
    return cc


def worker(cc, frames, n, fps, paced, res, barrier):
    lat, nbytes, late = [], 0, 0
    barrier.wait()
    t0 = time.perf_counter()
    for i in range(n):
        if paced:
            due = t0 + i / fps
            d = due - time.perf_counter()
            if d > 0:
                time.sleep(d)
        f = av.VideoFrame.from_ndarray(frames[i % len(frames)], format="nv12")
        f.pts = i
        a = time.perf_counter()
        for p in cc.encode(f):
            nbytes += p.size
        b = time.perf_counter()
        lat.append(b - a)
        if paced and b > t0 + (i + 1) / fps:
            late += 1
    for p in cc.encode(None):
        nbytes += p.size
    res.append({"frames": n, "seconds": time.perf_counter() - t0, "bytes": nbytes, "late": late, "lat": lat})


def run_n(codec, size, gop, n_streams, n_frames, fps, paced, frames):
    _, w, h = SIZES[size]
    ctxs, open_err = [], None
    for _ in range(n_streams):
        try:
            ctxs.append(make_ctx(codec, w, h, gop))
        except Exception as e:  # noqa: BLE001
            open_err = f"{type(e).__name__}: {e}"[:200]
            break
    res: list[dict] = []
    barrier = threading.Barrier(len(ctxs) + 1) if ctxs else None
    ths = [threading.Thread(target=worker, args=(c, frames, n_frames, fps, paced, res, barrier)) for c in ctxs]
    try:
        import psutil  # noqa: PLC0415
        proc = psutil.Process()
        proc.cpu_percent(None)
    except Exception:  # noqa: BLE001
        proc = None
    for t in ths:
        t.start()
    with GpuSampler() as gs:
        if barrier:
            barrier.wait()
        t0 = time.perf_counter()
        for t in ths:
            t.join()
        wall = time.perf_counter() - t0
    out = {"codec": codec, "size": size, "gop": gop, "paced": paced, "requested": n_streams, "opened": len(ctxs),
           "open_error": open_err, "wall_s": round(wall, 3), "gpu": gs.summary()}
    if proc:
        out["process_cpu_percent"] = proc.cpu_percent(None)
    if res:
        per = [r["frames"] / r["seconds"] for r in res]
        lat = sorted(x for r in res for x in r["lat"])
        out.update(aggregate_fps=round(sum(r["frames"] for r in res) / wall, 2), per_stream_fps_min=round(min(per), 2),
                   per_stream_fps_median=round(statistics.median(per), 2),
                   encode_ms_p50=round(1000 * lat[len(lat) // 2], 3), encode_ms_p99=round(1000 * lat[int(len(lat) * 0.99)], 3),
                   late_frames=sum(r["late"] for r in res), mbit_s_per_stream=round(
                       statistics.median(8 * r["bytes"] / r["seconds"] / 1e6 for r in res), 2))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codec", default="h264_nvenc")
    ap.add_argument("--size", default="1080p")
    ap.add_argument("--gop", default="intra,gop15")
    ap.add_argument("--streams", default="1,2,4,8,12,16")
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--mode", default="unpaced,paced")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    frames = load(a.size)
    out = {"bench": "pyav_concurrent", "pyav": av.__version__, "args": vars(a), "system_before": snapshot(), "runs": []}
    for gop in a.gop.split(","):
        for mode in a.mode.split(","):
            for n in map(int, a.streams.split(",")):
                r = run_n(a.codec, a.size, gop, n, a.frames, a.fps, mode == "paced", frames)
                print({k: v for k, v in r.items() if k != "gpu"})
                out["runs"].append(r)
    out["system_after"] = snapshot()
    write(f"pyav_concurrent_{a.codec}_{a.size}{'_smoke' if a.smoke else ''}", out)


if __name__ == "__main__":
    main()
