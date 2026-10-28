"""Experiment 2: does cv2.VideoCapture.retrieve(image=<preallocated view>) decode in place
into the recarray's image field (as opencv_get_frame.py assumes), and what happens when the
preallocated buffer has the wrong shape (e.g. after an in-place resolution change)?

No camera available to the agent, so this uses a file-backed VideoCapture (FFMPEG backend,
MJPG-encoded AVI written by cv2.VideoWriter). The DSHOW camera backend may behave differently;
that is recorded as an open question.

Run from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam:
    .venv\\Scripts\\python.exe <this file>
"""
import os
import sys
import time

import cv2
import numpy as np

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.types.frame_dtype_factories import create_frame_dtype

HERE = os.path.dirname(os.path.abspath(__file__))


def make_video(path, w, h, n=30):
    vw = cv2.VideoWriter(path, cv2.VideoWriter.fourcc(*"MJPG"), 30, (w, h))
    assert vw.isOpened(), "VideoWriter failed"
    for i in range(n):
        img = np.full((h, w, 3), 50 + i, dtype=np.uint8)
        cv2.putText(img, f"{i}", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 5, (255, 255, 255), 8)
        vw.write(img)
    vw.release()


def run(w, h):
    print(f"\n===== {w}x{h} =====")
    path = os.path.join(HERE, f"test_{w}x{h}_mjpg.avi")
    make_video(path, w, h)
    cap = cv2.VideoCapture(path)
    print(f"backend: {cap.getBackendName()}")

    cfg = CameraConfig(resolution=ImageResolution(height=h, width=w))
    rec = np.recarray(1, dtype=create_frame_dtype(cfg))
    view = rec.image[0]
    view[:] = 0
    ptr_before = view.__array_interface__["data"][0]
    assert cap.grab()
    ok, ret = cap.retrieve(image=view)
    print(f"retrieve ok={ok}; provided buffer now nonzero? {bool(view.any())}; "
          f"returned array shares memory with provided view? {np.shares_memory(ret, view)}; "
          f"provided data ptr unchanged? {view.__array_interface__['data'][0] == ptr_before}")

    # Timing: retrieve into preallocated view vs retrieve allocating new array
    t_into, t_alloc = [], []
    for _ in range(20):
        cap.grab()
        t0 = time.perf_counter_ns(); cap.retrieve(image=view); t_into.append(time.perf_counter_ns() - t0)
        cap.grab()
        t0 = time.perf_counter_ns(); cap.retrieve(); t_alloc.append(time.perf_counter_ns() - t0)
        if not cap.grab():
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    print(f"retrieve(image=view) median {np.median(t_into)/1e6:.3f} ms; retrieve() median {np.median(t_alloc)/1e6:.3f} ms "
          f"(file decode; not representative of DSHOW)")

    # Wrong-shape buffer (what happens if resolution changes but frame_rec_array is not rebuilt)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    small_cfg = CameraConfig(resolution=ImageResolution(height=480, width=640))
    small = np.recarray(1, dtype=create_frame_dtype(small_cfg))
    sview = small.image[0]
    sview[:] = 0
    cap.grab()
    ok, ret = cap.retrieve(image=sview)
    print(f"wrong-shape buffer (640x480 buffer, {w}x{h} stream): ok={ok}, returned shape={None if ret is None else ret.shape}, "
          f"provided buffer still all zero? {not sview.any()}, shares memory? {np.shares_memory(ret, sview) if ret is not None else None}")
    cap.release()


if __name__ == "__main__":
    print(sys.version)
    print("cv2", cv2.__version__)
    run(1280, 720)
    run(1920, 1080)
