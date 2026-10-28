"""Throwaway benchmark: per-frame cost of the SkellyCam disk-write path (VideoRecorder.record_frame ->
cv2.VideoWriter.write), which runs synchronously inside each camera's grab loop
(opencv_camera_loop.py:96-105). Measures 1 writer and N concurrent writer processes.

Run: C:\\Users\\Dom\\GitHub\\freemocap\\skellycam\\.venv\\Scripts\\python.exe recorder_write_bench.py
"""
import multiprocessing as mp
import os
import sys
import tempfile
import time

import cv2
import numpy as np

N_FRAMES = 300


def make_frames(w, h, n=60):
    # semi-natural content: gradient + moving rectangle + mild noise (not worst-case white noise)
    rng = np.random.default_rng(0)
    base = np.dstack([np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1))] * 3)
    out = []
    for i in range(n):
        f = base.copy()
        x = (i * 17) % (w - 200)
        cv2.rectangle(f, (x, 100), (x + 200, 300), (0, 0, 255), -1)
        f = cv2.add(f, rng.integers(0, 12, f.shape, dtype=np.uint8))
        out.append(f)
    return out


def writer_job(args):
    fourcc, w, h, tag = args
    from skellycam.core.recorders.videos.fourcc_codec_helpers import resolve_writer_fourcc, FOURCC_TO_EXTENSION
    working = resolve_writer_fourcc(requested_fourcc=fourcc, frame_size=(w, h))
    ext = FOURCC_TO_EXTENSION.get(working, "avi")
    path = os.path.join(tempfile.gettempdir(), f"_skc_bench_{tag}_{os.getpid()}.{ext}")
    if working == "X264_PYAV":
        from skellycam.core.recorders.videos.pyav_video_writer import PyavVideoWriter
        vw = PyavVideoWriter(path=path, fps=60, width=w, height=h)
    else:
        vw = cv2.VideoWriter(path, cv2.VideoWriter.fourcc(*working), 60.0, (w, h))
    frames = make_frames(w, h)
    ts = []
    t_all = time.perf_counter()
    for i in range(N_FRAMES):
        t = time.perf_counter_ns()
        vw.write(frames[i % len(frames)])
        ts.append(time.perf_counter_ns() - t)
    t_rel = time.perf_counter_ns()
    vw.release()
    rel_ms = (time.perf_counter_ns() - t_rel) / 1e6
    wall = time.perf_counter() - t_all
    size = os.path.getsize(path)
    os.remove(path)
    a = np.array(ts) / 1e6
    return dict(working=working, median=float(np.median(a)), p95=float(np.percentile(a, 95)),
                p99=float(np.percentile(a, 99)), max=float(a.max()), fps=N_FRAMES / wall, release_ms=rel_ms,
                size_mb=size / 1e6)


def main():
    print(sys.version, "cv2", cv2.__version__, "cpus", os.cpu_count())
    for (w, h) in [(1280, 720), (1920, 1080)]:
        for n_proc in [1, 5]:
            with mp.get_context("spawn").Pool(n_proc) as pool:
                res = pool.map(writer_job, [("X264", w, h, f"{w}x{h}_{k}") for k in range(n_proc)])
            for k, r in enumerate(res):
                print(f"{w}x{h} writers={n_proc} #{k}: codec={r['working']} write() median {r['median']:.2f} ms "
                      f"p95 {r['p95']:.2f} p99 {r['p99']:.2f} max {r['max']:.2f} ms | sustained {r['fps']:.1f} fps "
                      f"| release {r['release_ms']:.1f} ms | {r['size_mb']:.1f} MB/{N_FRAMES} frames")


if __name__ == "__main__":
    main()
