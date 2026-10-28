"""Hypothesis C2 follow-up: the same pixel ops as memcpybench.exe run_pixel, done from Python with OpenCV's native kernels
instead of a numpy strided expression (the fair "Python fix": native code called from Python).

  .venv\\Scripts\\python.exe research\\frame_ring_buffer\\cpp\\py_pixel_cv2.py <out.json> [rep_s=2] [reps=5]

ops (cv2.setNumThreads(1), preallocated dst, same 0.5 s warm-up + reps x rep_s timing as py_memcpy.run_pixel):
  cv2_cvtColor_BGR2RGB_then_flip0 : cv2.cvtColor(src, COLOR_BGR2RGB, dst=tmp); cv2.flip(tmp, 0, dst=dst)
  cv2_flip0                       : cv2.flip(src, 0, dst=dst)
  numpy_two_pass                  : np.copyto(tmp, src[..., ::-1]); np.copyto(dst, tmp[::-1])
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

pc = time.perf_counter_ns


def stats_ms(a):
    a = np.asarray(a, np.float64) / 1e6
    return {"n": int(a.size), "median_ms": float(np.median(a)), "mean_ms": float(a.mean()), "p99_ms": float(np.percentile(a, 99)),
            "min_ms": float(a.min()), "max_ms": float(a.max())}


def main():
    out = sys.argv[1]
    rep_s = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    reps = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    cv2.setNumThreads(1)
    rows = []
    for name, h, w in (("720p", 720, 1280), ("1080p", 1080, 1920)):
        src = (np.arange(h * w * 3, dtype=np.uint64) * 7 % 256).astype(np.uint8).reshape(h, w, 3)
        tmp = np.zeros_like(src)
        dst = np.zeros_like(src)
        ops = {
            "cv2_cvtColor_BGR2RGB_then_flip0": lambda: cv2.flip(cv2.cvtColor(src, cv2.COLOR_BGR2RGB, dst=tmp), 0, dst=dst),
            "cv2_flip0": lambda: cv2.flip(src, 0, dst=dst),
            "numpy_two_pass": lambda: (np.copyto(tmp, src[..., ::-1]), np.copyto(dst, tmp[::-1])),
        }
        for op, fn in ops.items():
            t_end = pc() + 500_000_000
            while pc() < t_end:
                fn()
            lat = []
            for _ in range(reps):
                dl = pc() + int(rep_s * 1e9)
                while pc() < dl:
                    a = pc(); fn(); lat.append(pc() - a)
            ok = int(dst[0, 0, 0] == (src[h - 1, 0, 0] if op == "cv2_flip0" else src[h - 1, 0, 2]))
            r = dict(lang="python", size=name, scenario="pixel_op", variant=op, threads=1, check=ok, opencv=cv2.__version__, lat=stats_ms(lat))
            rows.append(r)
            print(json.dumps(r), flush=True)
    Path(out).write_text(json.dumps(dict(tool="py_pixel_cv2", rows=rows)))


if __name__ == "__main__":
    main()
