"""Experiment 1: write-path copy semantics and costs in SkellyCam's SharedMemoryRingBuffer.

Run from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam:
    .venv\\Scripts\\python.exe <this file>
Uses the real skellycam classes (no source modified).
"""
import copy as copymod
import time
import tracemalloc

import numpy as np

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.camera.opencv.opencv_helpers.create_initial_frame_recarray import create_initial_frame_rec_array
from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import ONE_GIGABYTE
from skellycam.core.ipc.shared_memory.shared_memory_number import SharedMemoryNumber
from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
from skellycam.core.types.numpy_record_dtypes import FRAME_METADATA_DTYPE


def _make_ipc():
    import multiprocessing
    from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
    return CameraGroupIPC.create(global_kill_flag=multiprocessing.Value("b", False),
                                 heartbeat_timestamp=multiprocessing.Value("d", time.perf_counter()))


def bench(fn, n):
    ts = []
    for _ in range(n):
        t0 = time.perf_counter_ns()
        fn()
        ts.append(time.perf_counter_ns() - t0)
    a = np.array(ts) / 1e6
    return float(np.median(a)), float(np.percentile(a, 95))


def run(h, w):
    print(f"\n===== {w}x{h}x3 BGR uint8 =====")
    cfg = CameraConfig(resolution=ImageResolution(height=h, width=w))
    ipc = _make_ipc()
    tb = ipc.timebase_mapping
    ring = CameraSharedMemoryRingBuffer.from_config(camera_config=cfg, timebase_mapping=tb, read_only=False)
    try:
        frame = create_initial_frame_rec_array(config=cfg, ipc=ipc)
        dt = ring.dtype
        img_bytes = h * w * 3
        print(f"FRAME_METADATA_DTYPE.itemsize = {FRAME_METADATA_DTYPE.itemsize} B")
        print(f"frame dtype itemsize = {dt.itemsize} B (image {img_bytes} B, overhead {dt.itemsize - img_bytes} B)")
        print(f"ring_buffer_length = {ring.ring_buffer_length} slots (= {ONE_GIGABYTE} // {dt.itemsize})")
        print(f"shm segment size = {ring.ring_shm.size} B; seconds of history at 60fps = {ring.ring_buffer_length / 60:.2f}")
        print(f"image field offset in record = {dt.fields['image'][1]} B")

        # 1. Is copy.copy(recarray) a deep data copy?
        c = copymod.copy(frame)
        print(f"copy.copy(frame) shares memory with frame? {np.shares_memory(c, frame)}  (False => full data copy)")

        # 2. Does slot assignment (buffer[i] = recarray shape (1,)) write the whole record?
        frame.image[0][:] = 7
        frame.frame_metadata.frame_number[0] = 12345
        ring.put_frame(frame_rec_array=frame, overwrite=True)
        slot = ring.ring_shm.buffer[0]
        print(f"after put: slot0.frame_number={int(slot.frame_metadata.frame_number)}, "
              f"slot0.image all==7? {bool((ring.ring_shm.buffer.image[0] == 7).all())}")
        print(f"slot view shares memory with shm.buf: {np.shares_memory(ring.ring_shm.buffer, np.frombuffer(ring.ring_shm.shm.buf, dtype=np.uint8))}")

        # 3. Is the image view passed to cap.retrieve contiguous (so cv2 can write into it)?
        v = frame.image[0]
        print(f"frame.image[0]: shape={v.shape} C_CONTIGUOUS={v.flags['C_CONTIGUOUS']} WRITEABLE={v.flags['WRITEABLE']} "
              f"shares_memory(frame)={np.shares_memory(v, frame)}")

        # 4. Temporary allocation during put_data (tracemalloc peak)
        tracemalloc.start()
        tracemalloc.reset_peak()
        ring.put_frame(frame_rec_array=frame, overwrite=True)
        cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f"tracemalloc peak during one put_frame = {peak} B ({peak / dt.itemsize:.3f} x record size)")

        # 5. Timings
        n = 300
        med, p95 = bench(lambda: ring.put_frame(frame_rec_array=frame, overwrite=True), n)
        print(f"put_frame (copy.copy + slot assign + index update): median {med:.3f} ms, p95 {p95:.3f} ms")
        med_c, p95_c = bench(lambda: copymod.copy(frame), n)
        print(f"copy.copy(frame) alone:                              median {med_c:.3f} ms, p95 {p95_c:.3f} ms")
        idx = [0]

        def single_copy():
            idx[0] += 1
            np.copyto(ring.ring_shm.buffer[idx[0] % ring.ring_buffer_length: idx[0] % ring.ring_buffer_length + 1], frame)
        med_s, p95_s = bench(single_copy, n)
        print(f"single np.copyto(frame -> slot) (hypothetical):      median {med_s:.3f} ms, p95 {p95_s:.3f} ms")

        med_r, p95_r = bench(lambda: ring.get_data_by_index(index=ring.last_written_index.value), n)
        print(f"get_data_by_index(latest) with rec_array=None:       median {med_r:.3f} ms, p95 {p95_r:.3f} ms")
    finally:
        ring.close_and_unlink()


def number_costs():
    print("\n===== SharedMemoryNumber costs =====")
    num = SharedMemoryNumber.create(initial_value=0, read_only=False)
    try:
        def setv():
            num.value = 5
        def getv():
            return num.value
        n = 20000
        t0 = time.perf_counter_ns()
        for _ in range(n):
            setv()
        t1 = time.perf_counter_ns()
        for _ in range(n):
            getv()
        t2 = time.perf_counter_ns()
        print(f"SharedMemoryNumber.value set: {(t1 - t0) / n / 1e3:.2f} us; get: {(t2 - t1) / n / 1e3:.2f} us")
    finally:
        num.unlink_and_close()


def sleep_costs():
    print("\n===== time.sleep resolution (wait_10us / wait_1ms) =====")
    from skellycam.utilities.wait_functions import wait_10us, wait_1ms
    for name, fn, n in (("wait_10us", wait_10us, 2000), ("wait_1ms", wait_1ms, 500)):
        ts = []
        for _ in range(n):
            t0 = time.perf_counter_ns()
            fn()
            ts.append(time.perf_counter_ns() - t0)
        a = np.array(ts) / 1e3
        print(f"{name}: median {np.median(a):.1f} us, p95 {np.percentile(a, 95):.1f} us, max {a.max():.1f} us")


if __name__ == "__main__":
    import sys
    print(sys.version)
    print("numpy", np.__version__)
    run(720, 1280)
    run(1080, 1920)
    number_costs()
    sleep_costs()
