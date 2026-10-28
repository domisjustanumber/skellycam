r"""Break down SharedMemoryRingBuffer.put_data cost (ring_buffer_shared_memory.py:132).
Run: C:\Users\Dom\GitHub\freemocap\skellycam\.venv\Scripts\python.exe verifier_put_breakdown.py"""
import time
from copy import copy
import numpy as np
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
from skellycam.core.types.frame_dtype_factories import create_frame_dtype

def t(fn, n=200):
    ts = []
    for i in range(n):
        a = time.perf_counter_ns(); fn(i); ts.append(time.perf_counter_ns() - a)
    a = np.array(ts) / 1e6
    return f"median {np.median(a):.3f} ms p95 {np.percentile(a, 95):.3f} ms"

for (w, h) in [(1280, 720), (1920, 1080)]:
    cfg = CameraConfig(camera_id="0", camera_index=0, resolution={"width": w, "height": h})
    ring = CameraSharedMemoryRingBuffer.from_config(camera_config=cfg, timebase_mapping=TimebaseMapping(), read_only=False)
    buf = ring.ring_shm.buffer; L = ring.ring_buffer_length
    fr = np.recarray(1, dtype=create_frame_dtype(cfg)); fr.image[0] = 1
    pre = copy(fr)
    try:
        print(f"--- {w}x{h}")
        print("copy.copy(recarray) alone                :", t(lambda i: copy(fr)))
        print("buf[slot] = pre_copied (as line 132)     :", t(lambda i: buf.__setitem__(i % L, pre)))
        print("buf[slot] = fr[0]  (record scalar)       :", t(lambda i: buf.__setitem__(i % L, fr[0])))
        print("buf[slot:slot+1] = fr  (array slice)     :", t(lambda i: buf.__setitem__(slice(i % L, i % L + 1), fr)))
        print("np.copyto(buf[slot:slot+1], fr)          :", t(lambda i: np.copyto(buf[i % L:i % L + 1], fr)))
        print("buf.image[slot] = fr.image[0] (pixels)   :", t(lambda i: buf.image.__setitem__(i % L, fr.image[0])))
        print("last_written_index.value read+write      :", t(lambda i: setattr(ring.last_written_index, 'value', ring.last_written_index.value + 1)))
        print("full put_frame                           :", t(lambda i: ring.put_frame(fr, overwrite=True)))
    finally:
        ring.close_and_unlink()
