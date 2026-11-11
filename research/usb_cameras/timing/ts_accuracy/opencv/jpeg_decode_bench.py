# /// script
# requires-python = ">=3.12"
# dependencies = ["opencv-contrib-python==4.12.*", "numpy", "simplejpeg", "av", "psutil"]
# ///
"""Cost of decoding real 720p camera JPEGs in Python (no camera opened).

    uv run --script jpeg_decode_bench.py --out D/decode_bench.json JPEG [JPEG ...]

For each file: cv2.imdecode(IMREAD_COLOR) -> BGR, simplejpeg.decode_jpeg(colorspace BGR) (bundled libjpeg-turbo),
PyAV/FFmpeg mjpeg decoder -> bgr24 ndarray. Single thread: 300 decodes after 20 warm-ups, per-call ms p50/p95.
Then N threads (default 4, one per camera) decoding concurrently for 5 s: aggregate decodes/s and per-call p50,
plus process CPU% (psutil) during that window. cv2/simplejpeg release the GIL during decode.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics as st
import threading
import time
from pathlib import Path

import av
import cv2
import numpy as np
import psutil
import simplejpeg

ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument("--out", required=True)
ap.add_argument("--threads", type=int, default=4)
ap.add_argument("--n", type=int, default=300)
a = ap.parse_args()


def dec_cv2(b: bytes):
    return cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)


def dec_simplejpeg(b: bytes):
    return simplejpeg.decode_jpeg(b, colorspace="BGR")


class PyAVDec:
    def __init__(self):
        self.ctx = av.CodecContext.create("mjpeg", "r")

    def __call__(self, b: bytes):
        out = None
        for fr in self.ctx.decode(av.Packet(b)):
            out = fr.to_ndarray(format="bgr24")
        return out


def q(xs):
    s = sorted(xs)
    return {"p50": round(st.median(s), 3), "p95": round(s[int(0.95 * (len(s) - 1))], 3), "min": round(s[0], 3)}


res = {"tool": "jpeg_decode_bench 1.0 (2026-11-09)", "cv2": cv2.__version__, "simplejpeg": simplejpeg.__version__,
       "av": av.__version__, "cpu": platform.processor(), "logical_cpus": os.cpu_count(),
       "machine_cpu_pct_before": psutil.cpu_percent(interval=1.0), "files": []}
for f in a.files:
    b = Path(f).read_bytes()
    entry = {"file": f, "bytes": len(b)}
    for name, mk in (("cv2.imdecode", lambda: dec_cv2), ("simplejpeg", lambda: dec_simplejpeg), ("pyav_mjpeg", PyAVDec)):
        fn = mk()
        img = fn(b)
        entry.setdefault("shape", list(img.shape))
        for _ in range(20):
            fn(b)
        ts = []
        for _ in range(a.n):
            t0 = time.perf_counter_ns(); fn(b); ts.append((time.perf_counter_ns() - t0) / 1e6)
        entry[name] = {"single_thread_ms": q(ts)}
        # concurrent: a.threads threads, each its own decoder instance
        stop = threading.Event(); counts = [0] * a.threads; lat: list[list[float]] = [[] for _ in range(a.threads)]

        def worker(i):
            d = mk()
            while not stop.is_set():
                t0 = time.perf_counter_ns(); d(b); lat[i].append((time.perf_counter_ns() - t0) / 1e6); counts[i] += 1
        p = psutil.Process(); p.cpu_percent(None)
        ths = [threading.Thread(target=worker, args=(i,)) for i in range(a.threads)]
        t0 = time.perf_counter()
        for t in ths: t.start()
        time.sleep(5.0); stop.set()
        for t in ths: t.join()
        dt = time.perf_counter() - t0
        cpu = p.cpu_percent(None)
        entry[name][f"{a.threads}_threads"] = {"decodes_per_s_total": round(sum(counts) / dt, 1),
                                               "per_call_ms": q([x for l in lat for x in l]),
                                               "process_cpu_pct_of_one_core": round(cpu, 1)}
    res["files"].append(entry)
    print(json.dumps(entry))
res["machine_cpu_pct_after"] = psutil.cpu_percent(interval=1.0)
Path(a.out).parent.mkdir(parents=True, exist_ok=True)
Path(a.out).write_text(json.dumps(res, indent=1))
