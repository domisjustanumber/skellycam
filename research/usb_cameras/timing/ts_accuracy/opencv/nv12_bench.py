# /// script
# requires-python = ">=3.12"
# dependencies = ["opencv-contrib-python==4.12.*", "numpy"]
# ///
"""cv2.cvtColor NV12->BGR at 1280x720 (what OpenCV MSMF raw mode would need per frame). No camera."""
import json, statistics as st, time, sys
import cv2, numpy as np
src = np.random.default_rng(0).integers(0, 256, (720 * 3 // 2, 1280), dtype=np.uint8)
dst = np.empty((720, 1280, 3), np.uint8)
res = {}
for threads in (1, cv2.getNumThreads()):
    cv2.setNumThreads(threads)
    for _ in range(50): cv2.cvtColor(src, cv2.COLOR_YUV2BGR_NV12, dst=dst)
    ts = []
    for _ in range(500):
        t0 = time.perf_counter_ns(); cv2.cvtColor(src, cv2.COLOR_YUV2BGR_NV12, dst=dst); ts.append((time.perf_counter_ns() - t0) / 1e6)
    ts.sort(); res[f"cv2_threads_{threads}"] = {"p50_ms": round(st.median(ts), 3), "p95_ms": round(ts[int(0.95 * 499)], 3)}
print(json.dumps({"tool": "nv12_bench 1.0 (2026-11-09)", "cv2": cv2.__version__, **res}))
