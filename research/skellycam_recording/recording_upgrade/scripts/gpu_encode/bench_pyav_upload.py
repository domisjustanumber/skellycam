# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "opencv-python==4.12.0.88"]
# ///
"""BENCHMARK (timing): numpy -> encoder-frame cost from Python, per call, single thread.

Steps timed separately (median / p99 ms over --iters calls after --warmup):
  from_ndarray_nv12      av.VideoFrame.from_ndarray(nv12 array)              (copy into an AVFrame)
  from_ndarray_bgr24     av.VideoFrame.from_ndarray(bgr24 array)             (skellycam frames are BGR today)
  reformat_bgr_to_nv12   frame.reformat(format="nv12")  (libswscale)
  cv2_bgr_to_i420        cv2.cvtColor(BGR2YUV_I420) + from_ndarray(yuv420p)  (if cv2 importable)
  encode_sw_<codec>      cc.encode(nv12 frame) with a software-frame encoder (driver uploads internally)
  encode_hwctx_<codec>   cc.encode(nv12 frame) with HWAccel(cuda|d3d12va): PyAV uploads via av_hwframe_transfer_data
BGR input = the NV12 corpus frame converted once by swscale (real camera content).

Run (repo root, quiet machine; PyAV 18 = skellycam venv, has cv2 4.12.0):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/bench_pyav_upload.py --iters 600
PyAV 19.0.2: uv run --script <same path> --iters 600
Smoke: ... --iters 10 --warmup 2 --smoke
Writes results/gpu_encode/bench/pyav_upload_<pyav>_<UTC>.json.
"""
from __future__ import annotations

import argparse
import sys
import time
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from benchlib import snapshot, write  # noqa: E402
from common import prepare_inputs  # noqa: E402

try:
    import cv2
except Exception:  # noqa: BLE001
    cv2 = None

SIZES = {"720p": ("nv12_720p", 1280, 720), "1080p": ("nv12_1080p", 1920, 1080)}


def stats(xs: list[float]) -> dict:
    xs = sorted(xs)
    return {"n": len(xs), "median_ms": round(1000 * xs[len(xs) // 2], 4), "p99_ms": round(1000 * xs[int(len(xs) * 0.99)], 4),
            "min_ms": round(1000 * xs[0], 4)}


def timeit(fn, iters: int, warmup: int) -> dict:
    for _ in range(warmup):
        fn()
    ts = []
    for _ in range(iters):
        a = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - a)
    return stats(ts)


def enc_ctx(codec: str, w: int, h: int, hw: str | None):
    kw = {}
    if hw:
        from av.codec.hwaccel import HWAccel  # noqa: PLC0415
        kw["hwaccel"] = HWAccel(hw)
    cc = av.CodecContext.create(codec, "w", **kw)
    cc.width, cc.height, cc.pix_fmt = w, h, "nv12"
    cc.time_base, cc.framerate, cc.max_b_frames = Fraction(1, 30), Fraction(30, 1), 0
    cc.gop_size = 15
    if "nvenc" in codec:
        cc.options = {"preset": "p4", "tune": "ll"}
    cc.open()
    return cc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=600)
    ap.add_argument("--warmup", type=int, default=30)
    ap.add_argument("--sizes", default="720p,1080p")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    inputs = prepare_inputs()
    out = {"bench": "pyav_upload", "pyav": av.__version__, "cv2": getattr(cv2, "__version__", None), "args": vars(a),
           "system_before": snapshot(), "results": {}}
    for size in a.sizes.split(","):
        key, w, h = SIZES[size]
        nv12 = np.frombuffer(Path(inputs[key]).read_bytes()[: w * h * 3 // 2], np.uint8).reshape(h * 3 // 2, w).copy()
        bgr = av.VideoFrame.from_ndarray(nv12, format="nv12").reformat(format="bgr24").to_ndarray().copy()
        r: dict = {}
        r["from_ndarray_nv12"] = timeit(lambda: av.VideoFrame.from_ndarray(nv12, format="nv12"), a.iters, a.warmup)
        r["from_ndarray_bgr24"] = timeit(lambda: av.VideoFrame.from_ndarray(bgr, format="bgr24"), a.iters, a.warmup)
        fb = av.VideoFrame.from_ndarray(bgr, format="bgr24")
        r["reformat_bgr_to_nv12"] = timeit(lambda: fb.reformat(format="nv12"), a.iters, a.warmup)
        if cv2 is not None:
            r["cv2_bgr_to_i420"] = timeit(lambda: av.VideoFrame.from_ndarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV_I420),
                                                                             format="yuv420p"), a.iters, a.warmup)
        for codec, hw in (("h264_nvenc", None), ("h264_nvenc", "cuda"), ("hevc_nvenc", None), ("hevc_nvenc", "cuda"),
                          ("h264_d3d12va", "d3d12va"), ("hevc_d3d12va", "d3d12va")):
            tag = f"encode_{'hwctx_' + hw if hw else 'sw'}_{codec}"
            try:
                cc = enc_ctx(codec, w, h, hw)
                frame = av.VideoFrame.from_ndarray(nv12, format="nv12")
                i = [0]

                def step():
                    frame.pts = i[0]
                    i[0] += 1
                    for _ in cc.encode(frame):
                        pass
                r[tag] = timeit(step, a.iters, a.warmup)
                cc.encode(None)
            except Exception as e:  # noqa: BLE001
                r[tag] = {"error": f"{type(e).__name__}: {e}"[:200]}
        out["results"][size] = r
        print(size, {k: v.get("median_ms", v.get("error")) for k, v in r.items()} if a.smoke else "done")
    out["system_after"] = snapshot()
    write(f"pyav_upload_{av.__version__}{'_smoke' if a.smoke else ''}", out)


if __name__ == "__main__":
    main()
