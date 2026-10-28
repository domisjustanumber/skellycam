"""
Where does the CPU time go when 5 BGR streams are encoded from Python?  Compares colour-conversion strategies
feeding NVENC / libx264 through PyAV, 5 encoder threads in one process (like one recorder process for 5 cams).

Run:
    cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam
    .venv\\Scripts\\python.exe -I <scratch>\\bp_bench\\bench_encode_conversion.py <out_dir>
"""
import json
import os
import statistics
import sys
import threading
import time
from fractions import Fraction

import av
import cv2
import numpy as np

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
SIZES = {"720p": (720, 1280), "1080p": (1080, 1920)}
N_FRAMES = 600


def frames_for(h, w, seed):
    """8 camera-like frames with independent noise/texture so every frame is a real P-frame to encode."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base = np.stack([128 + 100 * np.sin(xx / 97.0) * np.cos(yy / 61.0),
                     128 + 90 * np.sin((xx + yy) / 151.0),
                     128 + 80 * np.cos(xx / 43.0 - yy / 77.0)], axis=-1)
    out = []
    for k in range(8):
        tex = cv2.GaussianBlur(rng.normal(0, 40, (h, w, 3)).astype(np.float32), (0, 0), 3)
        noise = rng.normal(0, 3, (h, w, 3)).astype(np.float32)
        out.append(np.clip(np.roll(base, 8 * k, axis=1) + tex + noise, 0, 255).astype(np.uint8))
    return out


def conv_cost(h, w):
    f = frames_for(h, w, 0)[0]
    i420 = np.empty((h * 3 // 2, w), np.uint8)
    bgra = np.empty((h, w, 4), np.uint8)
    res = {}
    for name, fn in {
        "cv2_cvtColor_BGR2YUV_I420_into_prealloc": lambda: cv2.cvtColor(f, cv2.COLOR_BGR2YUV_I420, dst=i420),
        "cv2_cvtColor_BGR2BGRA_into_prealloc": lambda: cv2.cvtColor(f, cv2.COLOR_BGR2BGRA, dst=bgra),
        "pyav_from_ndarray_bgr24_reformat_nv12": lambda: av.VideoFrame.from_ndarray(f, format="bgr24").reformat(format="nv12"),
        "pyav_from_ndarray_yuv420p_only": lambda: av.VideoFrame.from_ndarray(i420, format="yuv420p"),
    }.items():
        for _ in range(5):
            fn()
        ts = []
        for _ in range(200):
            t0 = time.perf_counter(); fn(); ts.append(time.perf_counter() - t0)
        res[name] = {"median_ms": statistics.median(ts) * 1e3}
    return res


def stream(codec, h, w, strategy, opts, out, idx):
    frames = frames_for(h, w, idx)
    cc = av.CodecContext.create(codec, "w")
    cc.width, cc.height = w, h
    cc.time_base, cc.framerate = Fraction(1, 60), Fraction(60, 1)
    cc.pix_fmt = {"cv2_i420": "yuv420p", "cv2_bgra": "bgra", "pyav_reformat": "nv12"}[strategy]
    cc.options = opts
    cc.open()
    i420 = np.empty((h * 3 // 2, w), np.uint8)
    bgra = np.empty((h, w, 4), np.uint8)
    nbytes, tconv = 0, 0.0
    t0 = time.perf_counter()
    for i in range(N_FRAMES):
        f = frames[i % 8]
        tc = time.perf_counter()
        if strategy == "cv2_i420":
            cv2.cvtColor(f, cv2.COLOR_BGR2YUV_I420, dst=i420)
            vf = av.VideoFrame.from_ndarray(i420, format="yuv420p")
        elif strategy == "cv2_bgra":  # NVENC accepts BGRA/BGR0 and converts on the GPU
            cv2.cvtColor(f, cv2.COLOR_BGR2BGRA, dst=bgra)
            vf = av.VideoFrame.from_ndarray(bgra, format="bgra")
        else:
            vf = av.VideoFrame.from_ndarray(f, format="bgr24").reformat(format="nv12")
        tconv += time.perf_counter() - tc
        vf.pts = i
        for p in cc.encode(vf):
            nbytes += p.size
    for p in cc.encode(None):
        nbytes += p.size
    dt = time.perf_counter() - t0
    out[idx] = {"fps": N_FRAMES / dt, "conv_ms": tconv / N_FRAMES * 1e3, "KB_per_frame": nbytes / N_FRAMES / 1e3,
                "Mbps_at_60fps": nbytes / N_FRAMES * 60 * 8 / 1e6}


def main():
    cv2.setNumThreads(1)
    res = {}
    configs = [
        ("h264_nvenc", "pyav_reformat", {"preset": "p1", "tune": "ll", "rc": "vbr", "cq": "23"}),
        ("h264_nvenc", "cv2_i420", {"preset": "p1", "tune": "ll", "rc": "vbr", "cq": "23"}),
        ("h264_nvenc", "cv2_bgra", {"preset": "p1", "tune": "ll", "rc": "vbr", "cq": "23"}),
        ("hevc_nvenc", "cv2_i420", {"preset": "p1", "tune": "ll", "rc": "vbr", "cq": "25"}),
        ("libx264", "cv2_i420", {"preset": "ultrafast", "crf": "23", "threads": "4"}),
    ]
    for rname, (h, w) in SIZES.items():
        res[rname] = {"conversion_single_frame": conv_cost(h, w)}
        for codec, strat, opts in configs:
            out = {}
            ths = [threading.Thread(target=stream, args=(codec, h, w, strat, opts, out, i)) for i in range(5)]
            t0 = time.perf_counter()
            for t in ths: t.start()
            for t in ths: t.join()
            wall = time.perf_counter() - t0
            key = f"{codec}_{strat}_x5"
            res[rname][key] = {"aggregate_fps": 5 * N_FRAMES / wall,
                               "min_stream_fps": min(v["fps"] for v in out.values()),
                               "per_stream": out}
            print(rname, key, round(res[rname][key]["aggregate_fps"], 1),
                  "min", round(res[rname][key]["min_stream_fps"], 1),
                  "conv_ms", round(statistics.mean(v["conv_ms"] for v in out.values()), 2),
                  "Mbps", round(statistics.mean(v["Mbps_at_60fps"] for v in out.values()), 1), flush=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "encode_conversion.json"), "w") as f:
        json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
