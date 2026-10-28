"""
Throughput of SkellyCam's own video writers (unmodified, imported from the checkout) on synthetic camera-like
frames: PyavVideoWriter (libx264 crf18 preset fast, bgr24 input) and cv2.VideoWriter with the default
writer fourcc 'X264'.  1 stream and 5 concurrent streams (threads in one process).

Run:
    cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam
    .venv\\Scripts\\python.exe -I <scratch>\\bp_bench\\bench_skellycam_writers.py <out_dir>
"""
import json
import os
import sys
import threading
import time

REPO = r"C:\Users\Dom\GitHub\freemocap\skellycam"
sys.path.insert(0, REPO)
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from skellycam.core.recorders.videos.pyav_video_writer import PyavVideoWriter  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
TMP = os.path.join(OUT, "writer_tmp")
os.makedirs(TMP, exist_ok=True)
N = 300


def frames_for(h, w, seed):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base = np.stack([128 + 100 * np.sin(xx / 97.0) * np.cos(yy / 61.0),
                     128 + 90 * np.sin((xx + yy) / 151.0),
                     128 + 80 * np.cos(xx / 43.0 - yy / 77.0)], axis=-1)
    out = []
    for k in range(8):
        tex = cv2.GaussianBlur(rng.normal(0, 40, (h, w, 3)).astype(np.float32), (0, 0), 3)
        out.append(np.clip(np.roll(base, 8 * k, axis=1) + tex, 0, 255).astype(np.uint8))
    return out


def run_writer(kind, h, w, i, out, frames, barrier):
    if kind == "PyavVideoWriter_libx264_fast_crf18":
        p = os.path.join(TMP, f"pyav_{h}_{i}.mp4")
        wr = PyavVideoWriter(path=p, fps=60.0, width=w, height=h)
    else:
        p = os.path.join(TMP, f"cv2_{h}_{i}.mp4")
        wr = cv2.VideoWriter(p, cv2.VideoWriter.fourcc(*"X264"), 60, (w, h))
        if not wr.isOpened():
            out[i] = {"error": "cv2.VideoWriter X264 did not open"}
            barrier.wait()
            return
    barrier.wait()  # all streams start encoding together; frame synthesis is excluded from timing
    t0 = time.perf_counter()
    for k in range(N):
        wr.write(frames[k % 8])
    wr.release()
    dt = time.perf_counter() - t0
    out[i] = {"fps": N / dt, "bytes": os.path.getsize(p)}
    os.remove(p)


res = {}
for name, (h, w) in {"720p": (720, 1280), "1080p": (1080, 1920)}.items():
    res[name] = {}
    for kind in ("PyavVideoWriter_libx264_fast_crf18", "cv2_VideoWriter_X264"):
        for n in (1, 5):
            out = {}
            fr = [frames_for(h, w, i) for i in range(n)]
            barrier = threading.Barrier(n + 1)
            ths = [threading.Thread(target=run_writer, args=(kind, h, w, i, out, fr[i], barrier)) for i in range(n)]
            for t in ths: t.start()
            barrier.wait()
            t0 = time.perf_counter()
            for t in ths: t.join()
            wall = time.perf_counter() - t0
            ok = [v for v in out.values() if "fps" in v]
            res[name][f"{kind}_x{n}"] = {"aggregate_fps": len(ok) * N / wall if ok else None,
                                         "min_stream_fps": min(v["fps"] for v in ok) if ok else None,
                                         "per_stream": out}
            print(name, kind, n, res[name][f"{kind}_x{n}"]["aggregate_fps"], flush=True)
with open(os.path.join(OUT, "skellycam_writers.json"), "w") as f:
    json.dump(res, f, indent=2)
