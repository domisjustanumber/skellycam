"""Is copy(data) in SharedMemoryRingBuffer.put_data (ring_buffer_shared_memory.py:132) a full-frame copy? Run with skellycam venv python."""
import sys, time, logging
from copy import copy
logging.disable(logging.CRITICAL)
sys.path.insert(0, r"C:\Users\Dom\GitHub\freemocap\skellycam")
import numpy as np
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.types.frame_dtype_factories import create_frame_dtype
cfg = CameraConfig(camera_id="c0", camera_index=0, resolution=ImageResolution(height=1080, width=1920))
f = np.recarray(1, dtype=create_frame_dtype(cfg)); f.image[0] = 7
c = copy(f)
print(f"copy(recarray) shares memory with source: {np.shares_memory(c, f)}; nbytes={c.nbytes}")
N=60; t0=time.perf_counter_ns()
for _ in range(N): c = copy(f)
print(f"copy(recarray) 1080p: {(time.perf_counter_ns()-t0)/N/1e6:.2f} ms per frame")
