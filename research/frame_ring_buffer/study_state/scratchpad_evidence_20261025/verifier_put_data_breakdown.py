"""
Breaks down SharedMemoryRingBuffer.put_data (ring_buffer_shared_memory.py L118-133, installed skellycam @777b058c):
    self.ring_shm.buffer[index % len] = copy(data)
Run: C:/Users/Dom/GitHub/freemocap/freemocap/.venv/Scripts/python.exe -I <this file>
"""
import time
from copy import copy
import numpy as np
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer


def bench(fn, n=200):
    fn()
    t = []
    for _ in range(n):
        t0 = time.perf_counter(); fn(); t.append((time.perf_counter() - t0) * 1e3)
    return f"median={np.median(t):.3f}ms p95={np.percentile(t, 95):.3f}ms"


for (w, h) in [(1280, 720), (1920, 1080)]:
    print(f"\n=== {w}x{h} BGR ===")
    cfg = CameraConfig(camera_id="0", resolution=ImageResolution(width=w, height=h), color_channels=3)
    rb = CameraSharedMemoryRingBuffer.from_config(camera_config=cfg, timebase_mapping=TimebaseMapping(), read_only=False)
    try:
        frame = np.recarray(1, dtype=rb.dtype)
        frame.image[0][:] = 7
        buf = rb.ring_shm.buffer
        print("copy(frame) alone:                       ", bench(lambda: copy(frame)))
        print("buf[0] = frame   (structured item assign):", bench(lambda: buf.__setitem__(0, frame)))
        print("buf[0] = copy(frame)  (what put_data does):", bench(lambda: buf.__setitem__(0, copy(frame))))
        print("np.copyto(buf[0:1], frame):              ", bench(lambda: np.copyto(buf[0:1], frame)))
        print("buf[0:1] = frame  (slice assign):        ", bench(lambda: buf.__setitem__(slice(0, 1), frame)))
        print("full put_frame(overwrite=True):          ", bench(lambda: rb.put_frame(frame, overwrite=True)))
    finally:
        rb.close_and_unlink()
