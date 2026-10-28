"""Verification script for skellycam-arch research notes.

Runs read-only against the skellycam repo (imports its modules, writes nothing there).
Usage: python skellycam_arch_verify.py <path-to-skellycam-repo>
"""
import sys
import time

repo = sys.argv[1]
sys.path.insert(0, repo)

import numpy as np
import cv2

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.types.frame_dtype_factories import create_frame_dtype
from skellycam.core.types.numpy_record_dtypes import FRAME_LIFECYCLE_TIMESTAMPS_DTYPE, FRAME_METADATA_DTYPE
from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import ONE_GIGABYTE

print("cv2", cv2.__version__, "numpy", np.__version__)

# 1. frame dtype for 3-channel and 1-channel configs
for ch in (3, 1):
    cfg = CameraConfig(resolution=ImageResolution(height=48, width=64), color_channels=ch)
    dt = create_frame_dtype(cfg)
    print(f"[1] color_channels={ch}: image subdtype={dt['image'].base} shape={dt['image'].shape}; "
          f"CameraConfig.image_shape={cfg.image_shape}")

# 2. lifecycle timestamp fields (all perf_counter_ns int64)
print("[2] FRAME_LIFECYCLE_TIMESTAMPS_DTYPE fields:", FRAME_LIFECYCLE_TIMESTAMPS_DTYPE.names)
print("[2] FRAME_METADATA_DTYPE fields:", FRAME_METADATA_DTYPE.names)

# 3. Ring buffer depth (1 GiB default) for typical GigE sensor sizes, BGR uint8
for (w, h) in [(1280, 720), (1920, 1200), (2448, 2048), (4096, 3000)]:
    cfg = CameraConfig(resolution=ImageResolution(height=h, width=w))
    itemsize = create_frame_dtype(cfg).itemsize
    print(f"[3] {w}x{h} BGR frame itemsize={itemsize/1e6:.2f} MB -> ring length={ONE_GIGABYTE // itemsize} frames")

# 4. In-place debayer into the recarray image view (no extra copy)
cfg = CameraConfig(resolution=ImageResolution(height=480, width=640))
rec = np.recarray(1, dtype=create_frame_dtype(cfg))
bayer = np.random.randint(0, 255, (480, 640), dtype=np.uint8)
target = rec.image[0]
out = cv2.cvtColor(bayer, cv2.COLOR_BayerBG2BGR, dst=target)
print("[4] cvtColor dst is recarray view:", out is target or np.shares_memory(out, rec), "shape", out.shape)
t0 = time.perf_counter_ns()
for _ in range(50):
    cv2.cvtColor(bayer, cv2.COLOR_BayerBG2BGR, dst=target)
print(f"[4] 640x480 debayer mean {(time.perf_counter_ns()-t0)/50/1e3:.1f} us")
big = np.random.randint(0, 255, (2048, 2448), dtype=np.uint8)
big_dst = np.empty((2048, 2448, 3), np.uint8)
t0 = time.perf_counter_ns()
for _ in range(20):
    cv2.cvtColor(big, cv2.COLOR_BayerBG2BGR, dst=big_dst)
print(f"[4] 2448x2048 debayer mean {(time.perf_counter_ns()-t0)/20/1e6:.2f} ms")

# 5. GenICam PFNC BayerRG8 (R at pixel (0,0)) -> which OpenCV code yields red?
h, w = 8, 8
mosaic = np.zeros((h, w), np.uint8)
mosaic[0::2, 0::2] = 255  # R sites for a "RGGB" (PFNC BayerRG) layout; scene is pure red
results = {}
for name in ["COLOR_BayerRG2BGR", "COLOR_BayerBG2BGR", "COLOR_BayerGR2BGR", "COLOR_BayerGB2BGR"]:
    bgr = cv2.cvtColor(mosaic, getattr(cv2, name))
    results[name] = tuple(int(v) for v in bgr[3, 3])
print("[5] pure-red RGGB mosaic, centre pixel BGR by OpenCV code:", results)
