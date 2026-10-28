"""Verifier v4: per-frame cost of the synchronous disk-write call used by VideoRecorder.record_frame
(cv2.VideoWriter.write with the default writer fourcc 'X264' -> .mp4), single process and 5 processes
in parallel (one per simulated camera, like production camera workers).

Content: synthetic moving gradient + per-frame noise patch + putText (not representative of real
camera content; real scenes may encode faster or slower). 240 frames per writer, first 20 discarded.

Run from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam:
    .venv\\Scripts\\python.exe <this file>
"""
import multiprocessing as mp
import os
import sys
import tempfile
import time

import cv2
import numpy as np

N = 240
SKIP = 20


def make_frames(w, h, n=60):
    rng = np.random.default_rng(0)
    base = np.zeros((h, w, 3), np.uint8)
    xs = np.linspace(0, 255, w, dtype=np.float32)
    frames = []
    for i in range(n):
        f = base.copy()
        f[:, :, 0] = ((xs + i * 4) % 256).astype(np.uint8)[None, :]
        f[:, :, 1] = ((xs[::-1] + i * 2) % 256).astype(np.uint8)[None, :]
        f[h // 3:h // 3 + 200, w // 3:w // 3 + 300] = rng.integers(0, 255, (200, 300, 3), np.uint8)
        cv2.putText(f, f"frame {i}", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 4)
        frames.append(f)
    return frames


def writer_job(args):
    w, h, fourcc, tag = args
    frames = make_frames(w, h)
    path = os.path.join(tempfile.gettempdir(), f"_verify_enc_{tag}_{os.getpid()}.mp4")
    vw = cv2.VideoWriter(path, cv2.VideoWriter.fourcc(*fourcc), 60.0, (w, h))
    if not vw.isOpened():
        return (tag, None, "writer did not open")
    ts = []
    for i in range(N):
        t0 = time.perf_counter_ns()
        vw.write(frames[i % len(frames)])
        ts.append(time.perf_counter_ns() - t0)
    be = vw.getBackendName()
    vw.release()
    try:
        os.remove(path)
    except OSError:
        pass
    a = np.array(ts[SKIP:]) / 1e6
    return (tag, (float(np.median(a)), float(np.percentile(a, 95)), float(a.max())), be)


if __name__ == "__main__":
    print(sys.version)
    print("cv2", cv2.__version__)
    for (w, h) in ((1280, 720), (1920, 1080)):
        tag, r, be = writer_job((w, h, "X264", "single"))
        print(f"backend={be}"); print(f"{w}x{h} X264 single process: write() median {r[0]:.2f} ms, p95 {r[1]:.2f} ms, max {r[2]:.2f} ms")
        with mp.get_context("spawn").Pool(5) as pool:
            res = pool.map(writer_job, [(w, h, "X264", f"p{k}") for k in range(5)])
        meds = [r[1][0] for r in res]
        p95s = [r[1][1] for r in res]
        print(f"{w}x{h} X264 5 processes in parallel: per-process write() medians {[round(m, 2) for m in meds]} ms, "
              f"p95s {[round(p, 2) for p in p95s]} ms")
