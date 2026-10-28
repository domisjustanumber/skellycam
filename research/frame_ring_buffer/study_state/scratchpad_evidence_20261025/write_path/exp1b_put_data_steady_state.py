"""Experiment 1b: separate first-lap (page-fault) cost from steady-state cost of
SharedMemoryRingBuffer.put_data, and decompose it.

Run from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam:
    .venv\\Scripts\\python.exe <this file>
"""
import copy as copymod
import multiprocessing
import time

import numpy as np

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.camera.opencv.opencv_helpers.create_initial_frame_recarray import create_initial_frame_rec_array
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer


def stats(ts):
    a = np.array(ts) / 1e6
    return f"median {np.median(a):.3f} ms, p95 {np.percentile(a, 95):.3f} ms, max {a.max():.3f} ms"


def run(h, w):
    print(f"\n===== {w}x{h}x3 =====")
    ipc = CameraGroupIPC.create(global_kill_flag=multiprocessing.Value("b", False),
                                heartbeat_timestamp=multiprocessing.Value("d", time.perf_counter()))
    cfg = CameraConfig(resolution=ImageResolution(height=h, width=w))
    ring = CameraSharedMemoryRingBuffer.from_config(camera_config=cfg, timebase_mapping=ipc.timebase_mapping,
                                                    read_only=False)
    L = ring.ring_buffer_length
    frame = create_initial_frame_rec_array(config=cfg, ipc=ipc)
    try:
        # First lap: every slot is touched for the first time (page faults on fresh shm pages)
        first = []
        for _ in range(L):
            t0 = time.perf_counter_ns()
            ring.put_frame(frame_rec_array=frame, overwrite=True)
            first.append(time.perf_counter_ns() - t0)
        print(f"put_frame FIRST LAP ({L} writes, fresh pages): {stats(first)}")
        steady = []
        for _ in range(L):
            t0 = time.perf_counter_ns()
            ring.put_frame(frame_rec_array=frame, overwrite=True)
            steady.append(time.perf_counter_ns() - t0)
        print(f"put_frame STEADY (2nd lap):                   {stats(steady)}")

        # Decomposition, steady state (slots already touched)
        buf = ring.ring_shm.buffer
        parts = {"copy.copy(frame)": [], "buffer[i] = tmp (slot assign)": [], "last_written_index.value = i": [],
                 "dtype check + read last_written_index": [], "np.copyto(buf[i:i+1], frame) (single copy)": []}
        i = ring.last_written_index.value
        for _ in range(L):
            i += 1
            s = i % L
            t0 = time.perf_counter_ns(); tmp = copymod.copy(frame); t1 = time.perf_counter_ns()
            buf[s] = tmp; t2 = time.perf_counter_ns()
            ring.last_written_index.value = i; t3 = time.perf_counter_ns()
            _ = frame.dtype != ring.dtype; _ = ring.last_written_index.value; t4 = time.perf_counter_ns()
            np.copyto(buf[s:s + 1], frame); t5 = time.perf_counter_ns()
            parts["copy.copy(frame)"].append(t1 - t0)
            parts["buffer[i] = tmp (slot assign)"].append(t2 - t1)
            parts["last_written_index.value = i"].append(t3 - t2)
            parts["dtype check + read last_written_index"].append(t4 - t3)
            parts["np.copyto(buf[i:i+1], frame) (single copy)"].append(t5 - t4)
        for k, v in parts.items():
            print(f"  {k:45s} {stats(v)}")
        tmp = copymod.copy(frame)
        print(f"  check: buf[s]=tmp leaves slot independent of tmp? {not np.shares_memory(buf[s:s+1], tmp)}")
    finally:
        ring.close_and_unlink()


if __name__ == "__main__":
    run(720, 1280)
    run(1080, 1920)
