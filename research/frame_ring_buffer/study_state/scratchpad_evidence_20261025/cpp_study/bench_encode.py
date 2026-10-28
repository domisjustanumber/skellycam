r"""Per-frame encode cost + output size for the two writers SkellyCam uses
(cv2.VideoWriter MJPG, and PyavVideoWriter libx264 crf18 preset fast = skellycam/core/recorders/videos/pyav_video_writer.py).
Synthetic content: blurred noise texture translated 3 px/frame + frame counter (NOT representative of real scenes -> sizes are indicative only).
Run: C:\Users\Dom\GitHub\freemocap\skellycam\.venv\Scripts\python.exe bench_encode.py > bench_encode.out.txt"""
import os, time, tempfile, statistics as st
import numpy as np, cv2
from skellycam.core.recorders.videos.pyav_video_writer import PyavVideoWriter
N = 180
for label, (h, w) in {"720p": (720, 1280), "1080p": (1080, 1920)}.items():
    rng = np.random.default_rng(0)
    tex = cv2.GaussianBlur(rng.integers(0, 255, (h, w + 3 * N, 3), dtype=np.uint8), (9, 9), 3)
    frames = []
    for i in range(N):
        f = np.ascontiguousarray(tex[:, 3 * i:3 * i + w])
        cv2.putText(f, str(i), (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 4, (255, 255, 255), 8)
        frames.append(f)
    for name in ("cv2 MJPG", "pyav libx264 crf18 fast"):
        p = os.path.join(tempfile.gettempdir(), f"enc_{label}.{'avi' if 'MJPG' in name else 'mp4'}")
        wr = cv2.VideoWriter(p, cv2.VideoWriter.fourcc(*"MJPG"), 60, (w, h)) if "MJPG" in name else PyavVideoWriter(p, 60.0, w, h)
        ts = []
        for f in frames:
            t0 = time.perf_counter_ns(); wr.write(f); ts.append(time.perf_counter_ns() - t0)
        t0 = time.perf_counter_ns(); wr.release(); flush = (time.perf_counter_ns() - t0) / 1e6
        sz = os.path.getsize(p); os.remove(p)
        tot = (sum(ts) / 1e6 + flush)
        print(f"{label} {name:<26s} median write {st.median(ts)/1e3:8.1f} us | total wall incl. flush {tot/N:6.2f} ms/frame "
              f"(= {1000/(tot/N):6.1f} fps single stream) | {sz/N/1e3:7.1f} KB/frame -> x5 cams x60fps = {sz/N*300/1e6:6.1f} MB/s")

# --- cv2.VideoWriter with 'X264' fourcc (what resolve_writer_fourcc('X264', ...) returns on this machine)
for label, (h, w) in {"720p": (720, 1280), "1080p": (1080, 1920)}.items():
    rng = np.random.default_rng(0)
    tex = cv2.GaussianBlur(rng.integers(0, 255, (h, w + 3 * N, 3), dtype=np.uint8), (9, 9), 3)
    frames = [np.ascontiguousarray(tex[:, 3 * i:3 * i + w]) for i in range(N)]
    p = os.path.join(tempfile.gettempdir(), f"enc_{label}_x264.mp4")
    wr = cv2.VideoWriter(p, cv2.VideoWriter.fourcc(*"X264"), 60, (w, h))
    ts = []
    for f in frames:
        t0 = time.perf_counter_ns(); wr.write(f); ts.append(time.perf_counter_ns() - t0)
    t0 = time.perf_counter_ns(); wr.release(); flush = (time.perf_counter_ns() - t0) / 1e6
    sz = os.path.getsize(p); os.remove(p); tot = sum(ts) / 1e6 + flush
    print(f"{label} cv2 'X264' fourcc            median write {st.median(ts)/1e3:8.1f} us | total wall incl. flush {tot/N:6.2f} ms/frame | {sz/N/1e3:7.1f} KB/frame")
