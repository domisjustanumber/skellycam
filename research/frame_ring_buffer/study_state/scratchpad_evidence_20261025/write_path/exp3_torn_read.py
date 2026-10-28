"""Experiment 3: can a reader observe a torn frame from SharedMemoryRingBuffer?

A writer process (like a camera worker: recreate(read_only=False), put_data(overwrite_allowed=True))
writes 1280x720 frames as fast as it can. Each frame's image is filled with (frame_number % 251)
and frame_metadata.frame_number = frame_number. A reader in the parent (like CameraGroup:
created read_only=True, reads with get_data_by_index) reads frames and classifies each read:
  ok           - frame_number == requested index and every pixel == index % 251
  fn_mismatch  - frame_number != requested index (the post-read check used by
                 camera_group_shared_memory.py would catch this)
  torn_silent  - frame_number == requested index but pixels are not uniform / wrong value
                 (NOT caught by any check in the code)

Run from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam:
    .venv\\Scripts\\python.exe <this file>
"""
import multiprocessing
import multiprocessing.queues  # skellycam type_overloads needs this pre-imported in spawned children
import time

import numpy as np

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import SharedMemoryRingBuffer
from skellycam.core.types.frame_dtype_factories import create_frame_dtype

W, H = 1280, 720
DURATION_S = 4.0


def writer(dto, stop):
    ring = SharedMemoryRingBuffer.recreate(dto=dto, read_only=False)
    frame = np.recarray(1, dtype=ring.dtype)
    fn = 0
    while not stop.value:
        frame.frame_metadata.frame_number[0] = fn
        frame.image[0][:] = fn % 251
        ring.put_data(frame, overwrite_allowed=True)
        fn += 1
    ring.close()


def trial(ring_len, mode):
    cfg = CameraConfig(resolution=ImageResolution(height=H, width=W))
    example = np.recarray(1, dtype=create_frame_dtype(cfg))
    ring = SharedMemoryRingBuffer.create(example_data=example, read_only=True, ring_buffer_length=ring_len)
    stop = multiprocessing.Value("b", False)
    p = multiprocessing.Process(target=writer, args=(ring.to_dto(), stop))
    p.start()
    try:
        t_wait = time.perf_counter() + 60
        while ring.last_written_index.value < ring_len:
            if not p.is_alive() or time.perf_counter() > t_wait:
                raise RuntimeError(f"writer not producing: alive={p.is_alive()} exitcode={p.exitcode} "
                                   f"last_written_index={ring.last_written_index.value}")
            time.sleep(0.01)
        counts = {"ok": 0, "fn_mismatch": 0, "torn_silent": 0, "index_error": 0}
        rec = np.recarray(1, dtype=ring.dtype)
        t_end = time.perf_counter() + DURATION_S
        while time.perf_counter() < t_end:
            w = ring.last_written_index.value
            idx = w if mode == "latest" else w - (ring_len - 1)
            try:
                ring.get_data_by_index(index=idx, rec_array=rec)
            except IndexError:
                counts["index_error"] += 1
                continue
            fn = int(rec.frame_metadata.frame_number[0])
            img = rec.image[0]
            expected = idx % 251
            if fn != idx:
                counts["fn_mismatch"] += 1
            elif not (img.min() == img.max() == expected):
                counts["torn_silent"] += 1
            else:
                counts["ok"] += 1
        writes = ring.last_written_index.value
    finally:
        stop.value = True
        p.join()
        ring.close_and_unlink()
    print(f"ring_len={ring_len:4d} read={mode:7s} writer_frames={writes:6d} "
          f"({writes / DURATION_S:.0f}/s approx) results={counts}")


if __name__ == "__main__":
    trial(2, "oldest")
    trial(2, "latest")
    trial(8, "oldest")
    trial(388, "latest")
