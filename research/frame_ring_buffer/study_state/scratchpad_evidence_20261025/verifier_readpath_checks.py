r"""Verifier checks for the SkellyCam read-path map (does not modify repo).
Run: C:\Users\Dom\GitHub\freemocap\skellycam\.venv\Scripts\python.exe verifier_readpath_checks.py
"""
import os
import tempfile
import time
from copy import copy

import cv2
import numpy as np

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
from skellycam.core.types.frame_dtype_factories import create_frame_dtype
from skellycam.core.types.numpy_record_dtypes import FRAME_METADATA_DTYPE


def stats(ts):
    a = np.array(ts) / 1e6
    return f"median {np.median(a):.3f} ms p95 {np.percentile(a, 95):.3f} ms (n={len(a)})"


print("numpy", np.__version__, "cv2", cv2.__version__)
print(f"[A] FRAME_METADATA_DTYPE.itemsize = {FRAME_METADATA_DTYPE.itemsize} bytes")

for (w, h) in [(1280, 720), (1920, 1080)]:
    cfg = CameraConfig(camera_id="0", camera_index=0, resolution={"width": w, "height": h})
    tb = TimebaseMapping()
    ring = CameraSharedMemoryRingBuffer.from_config(camera_config=cfg, timebase_mapping=tb, read_only=False)
    try:
        fr = np.recarray(1, dtype=create_frame_dtype(cfg))
        fr.image[0] = np.random.randint(0, 255, fr.image[0].shape, dtype=np.uint8)
        fr.frame_metadata.frame_number[0] = 0
        md = copy(fr.frame_metadata)
        print(f"[B {w}x{h}] copy(frame.frame_metadata): shares_memory={np.shares_memory(md, fr)} nbytes={md.nbytes}")
        # put_data cost (copy.copy + slot assignment) vs a single np.copyto into the slot
        put_ts, copyto_ts = [], []
        L = ring.ring_buffer_length
        for i in range(200):
            t = time.perf_counter_ns(); ring.put_frame(fr, overwrite=True); put_ts.append(time.perf_counter_ns() - t)
        for i in range(200):
            t = time.perf_counter_ns(); np.copyto(ring.ring_shm.buffer[i % L:i % L + 1], fr); copyto_ts.append(time.perf_counter_ns() - t)
        print(f"[C {w}x{h}] put_frame (copy.copy + slot assign + index update): {stats(put_ts)}")
        print(f"[C {w}x{h}] single np.copyto into slot (1 copy):              {stats(copyto_ts)}")
        # Is the SHM numpy view writeable even for a read_only=True handle?
        ro = CameraSharedMemoryRingBuffer.recreate(dto=ring.to_dto(), read_only=True)
        print(f"[D {w}x{h}] read_only=True handle: ring_shm.buffer.flags.writeable = {ro.ring_shm.buffer.flags.writeable}")
        # get_data_by_index result before/after the slot is overwritten (copy, not view)
        target = ring.last_written_index.value
        out = ro.get_data_by_index(index=target)
        before = int(out.frame_metadata.frame_number[0])
        fr2 = fr.copy(); fr2.frame_metadata.frame_number[0] = 999
        for _ in range(L):
            ring.put_frame(fr2, overwrite=True)
        print(f"[E {w}x{h}] reader copy frame_number after writer lapped slot: before={before} after={int(out.frame_metadata.frame_number[0])} (unchanged => private copy)")
        try:
            ro.get_data_by_index(index=target)
            print(f"[E {w}x{h}] stale index read after lap: no error")
        except IndexError as e:
            print(f"[E {w}x{h}] stale index read after lap: IndexError ({str(e)[:60]}...)")
        ro.close()
    finally:
        ring.close_and_unlink()

# [F] Does VideoCapture.retrieve(image=prealloc) decode into the caller's buffer? (file source / FFMPEG backend, NOT DSHOW)
p = os.path.join(tempfile.gettempdir(), "_verifier_retrieve_probe.avi")
vw = cv2.VideoWriter(p, cv2.VideoWriter.fourcc(*"MJPG"), 30.0, (1280, 720))
for i in range(5):
    vw.write(np.full((720, 1280, 3), 40 * i, np.uint8))
vw.release()
cap = cv2.VideoCapture(p, cv2.CAP_FFMPEG)
cfg = CameraConfig(camera_id="0", camera_index=0, resolution={"width": 1280, "height": 720})
fr = np.recarray(1, dtype=create_frame_dtype(cfg))
fr.image[0] = 7
cap.grab(); cap.grab()
ok, ret = cap.retrieve(image=fr.image[0])
print(f"[F] backend={cap.getBackendName()} retrieve ok={ok}; returned shares memory with recarray image={np.shares_memory(ret, fr)}; "
      f"recarray image updated in place={int(fr.image[0].mean()) != 7} (mean={fr.image[0].mean():.1f})")
cap.release(); os.remove(p)
