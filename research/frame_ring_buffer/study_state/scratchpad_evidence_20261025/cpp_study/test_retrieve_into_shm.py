"""
Does cv2.VideoCapture.retrieve(image=<view into multiprocessing.shared_memory>) decode IN PLACE
(no reallocation), so the local frame_rec_array + put_data copies can be skipped?
Run: C:\\Users\\Dom\\GitHub\\freemocap\\skellycam\\.venv\\Scripts\\python.exe test_retrieve_into_shm.py > test_retrieve_into_shm.out.txt
Uses a synthetic MJPG .avi (no camera needed). Backends tried: CAP_MSMF, CAP_FFMPEG.
Also times: (a) current path = retrieve into local recarray + SharedMemoryRingBuffer.put_data
            (b) proposed path = retrieve straight into the ring slot view
"""
import os
import time
import tempfile
import statistics as st
from multiprocessing import shared_memory

import numpy as np
import cv2

from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import SharedMemoryRingBuffer
from skellycam.core.types.numpy_record_dtypes import FRAME_METADATA_DTYPE

H, W = 720, 1280
N = 240
path = os.path.join(tempfile.gettempdir(), "retrieve_test_720p.avi")
vw = cv2.VideoWriter(path, cv2.VideoWriter.fourcc(*"MJPG"), 60, (W, H))
rng = np.random.default_rng(0)
base = cv2.GaussianBlur(rng.integers(0, 255, (H, W, 3), dtype=np.uint8), (15, 15), 5)
for i in range(N):
    f = base.copy()
    cv2.putText(f, str(i), (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 4, (255, 255, 255), 8)
    vw.write(f)
vw.release()

dt = np.dtype([("frame_metadata", FRAME_METADATA_DTYPE), ("image", np.uint8, (H, W, 3))], align=True)

for (backend_name, backend), prefault in [(b, pf) for b in (("CAP_MSMF", cv2.CAP_MSMF), ("CAP_FFMPEG", cv2.CAP_FFMPEG)) for pf in (False, True)]:
    cap = cv2.VideoCapture(path, backend)
    print(f"\n=== backend {backend_name}: opened={cap.isOpened()} prefault_ring={prefault} ===")
    if not cap.isOpened():
        continue
    # --- in-place check on a raw SharedMemory view
    shm = shared_memory.SharedMemory(create=True, size=H * W * 3)
    view = np.ndarray((H, W, 3), dtype=np.uint8, buffer=shm.buf)
    ptr_before = view.ctypes.data
    cap.grab()
    ok, out = cap.retrieve(image=view)
    print("retrieve ok:", ok, "| returned array is the shm view object:", out is view,
          "| shares memory with shm:", np.shares_memory(out, view),
          "| data ptr unchanged:", out.ctypes.data == ptr_before,
          "| shm non-zero after decode:", bool(view.any()))
    del out, view
    shm.close(); shm.unlink()

    # --- timing: current path vs proposed path, using SkellyCam's own ring buffer class
    example = np.recarray(1, dtype=dt)
    ring = SharedMemoryRingBuffer.create(example_data=example, read_only=False)
    L = ring.ring_buffer_length
    if prefault:
        t0 = time.perf_counter_ns(); ring.ring_shm.buffer.image[:] = 0
        print(f"prefault (first touch) of whole 1 GiB ring: {(time.perf_counter_ns()-t0)/1e6:.1f} ms")
    local = np.recarray(1, dtype=dt)
    cur, prop, k = [], [], 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    for i in range(N - 2):
        if not cap.grab():
            break
        if i % 2 == 0:
            t0 = time.perf_counter_ns()
            cap.retrieve(image=local.image[0])
            t1 = time.perf_counter_ns()
            ring.put_data(local, overwrite_allowed=True)
            t2 = time.perf_counter_ns()
            cur.append((t1 - t0, t2 - t1))
        else:
            slot = ring.ring_shm.buffer.image[(ring.last_written_index.value + 1) % L]
            t0 = time.perf_counter_ns()
            ok, o = cap.retrieve(image=slot)
            t1 = time.perf_counter_ns()
            ring.last_written_index.value = ring.last_written_index.value + 1  # publish (metadata write omitted)
            t2 = time.perf_counter_ns()
            assert np.shares_memory(o, ring.ring_shm.buffer), "retrieve reallocated!"
            prop.append((t1 - t0, t2 - t1))
    f = lambda xs, j: st.median([x[j] for x in xs]) / 1e3
    print(f"current : retrieve->local {f(cur,0):8.1f} us + put_data {f(cur,1):8.1f} us = {f(cur,0)+f(cur,1):8.1f} us  (n={len(cur)})")
    print(f"proposed: retrieve->slot  {f(prop,0):8.1f} us + publish  {f(prop,1):8.1f} us = {f(prop,0)+f(prop,1):8.1f} us  (n={len(prop)})")
    ring.close_and_unlink()
    cap.release()
os.remove(path)
