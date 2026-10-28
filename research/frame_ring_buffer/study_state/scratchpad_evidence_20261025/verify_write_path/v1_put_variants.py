"""Verifier experiment v1: write-path costs measured with cold destination slots.

Each variant gets its own full lap(s) through a production-sized ring (1 GiB default), after one
warm-up lap that faults in every page, so the destination slot is never cache-warm.

Variants:
  A  put_frame (production: copy.copy + slot assign + index store, beartype-wrapped)
  B  buffer[i] = data            (assign without copy.copy)
  C  np.copyto(buffer[i:i+1], data)
  D  buffer.image[i] only (np.copyto of image field) - lower bound for a pixels-only copy
Also: beartype overhead of put_frame / should_grab_by_id, should_grab_by_id cost for 5 cameras,
and PyAV from_ndarray copy semantics.

Run from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam:
    .venv\\Scripts\\python.exe <this file>
"""
import copy as copymod
import multiprocessing
import multiprocessing.queues  # noqa
import sys
import time

import numpy as np

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.camera.opencv.opencv_helpers.create_initial_frame_recarray import create_initial_frame_rec_array
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import SharedMemoryRingBuffer
from skellycam.core.types.numpy_record_dtypes import FRAME_METADATA_DTYPE, FRAME_CAMERA_INFO_DTYPE


def st(ts):
    a = np.array(ts) / 1e6
    return f"median {np.median(a):.3f} ms  p95 {np.percentile(a, 95):.3f} ms"


def run(h, w, ipc):
    print(f"\n===== {w}x{h}x3 =====")
    cfg = CameraConfig(resolution=ImageResolution(height=h, width=w))
    ring = CameraSharedMemoryRingBuffer.from_config(camera_config=cfg, timebase_mapping=ipc.timebase_mapping,
                                                    read_only=False)
    L = ring.ring_buffer_length
    dt = ring.dtype
    print(f"record itemsize {dt.itemsize} B; metadata {FRAME_METADATA_DTYPE.itemsize} B "
          f"(camera_info {FRAME_CAMERA_INFO_DTYPE.itemsize} B); image offset {dt.fields['image'][1]}; slots {L}; "
          f"shm size {ring.ring_shm.size} B")
    frame = create_initial_frame_rec_array(config=cfg, ipc=ipc)
    buf = ring.ring_shm.buffer
    try:
        # warm-up lap: fault every page in
        for _ in range(L):
            ring.put_frame(frame_rec_array=frame, overwrite=True)
        res = {k: [] for k in "ABCD"}
        i = ring.last_written_index.value
        for k in "ABCD":
            for _ in range(L):
                i += 1
                s = i % L
                frame.image[0][:16, :16] = i % 255  # touch source like a fresh decode would (small)
                t0 = time.perf_counter_ns()
                if k == "A":
                    ring.put_frame(frame_rec_array=frame, overwrite=True)
                elif k == "B":
                    buf[s] = frame
                elif k == "C":
                    np.copyto(buf[s:s + 1], frame)
                else:
                    np.copyto(buf.image[s], frame.image[0])
                res[k].append(time.perf_counter_ns() - t0)
            if k == "A":
                i = ring.last_written_index.value
        names = {"A": "put_frame (production)", "B": "buffer[s] = frame (no copy.copy)",
                 "C": "np.copyto(buffer[s:s+1], frame)", "D": "np.copyto(buffer.image[s], image) only"}
        for k in "ABCD":
            print(f"  {names[k]:40s} {st(res[k])}")
        # equivalence check of B vs production
        frame.image[0][:] = 77
        frame.frame_metadata.frame_number[0] = 4242
        buf[0] = frame
        print(f"  B equivalence: slot0 image==77 {bool((buf.image[0] == 77).all())}, fn={int(buf.frame_metadata.frame_number[0])}, "
              f"shares_memory(slot, frame)={np.shares_memory(buf[0:1], frame)}")
        # beartype overhead on put_frame
        pf = CameraSharedMemoryRingBuffer.put_frame
        print(f"  put_frame has __wrapped__ (beartype)? {hasattr(pf, '__wrapped__')}")
    finally:
        ring.close_and_unlink()


def beartype_overhead():
    print("\n===== beartype wrapper overhead (wrapped vs __wrapped__) =====")
    statuses = {f"cam{i}": CameraStatus() for i in range(5)}
    for s in statuses.values():
        s.connected.value = True
        s.frame_count.value = 10
    orch = CameraOrchestrator.from_statuses(statuses)
    f = CameraOrchestrator.should_grab_by_id
    print(f"should_grab_by_id wrapped? {hasattr(f, '__wrapped__')}")
    n = 20000
    t0 = time.perf_counter_ns()
    for _ in range(n):
        orch.should_grab_by_id(camera_id="cam0")
    t1 = time.perf_counter_ns()
    raw = getattr(f, "__wrapped__", f)
    for _ in range(n):
        raw(orch, camera_id="cam0")
    t2 = time.perf_counter_ns()
    print(f"should_grab_by_id (5 cams): wrapped {(t1 - t0) / n / 1e3:.2f} us/call; unwrapped {(t2 - t1) / n / 1e3:.2f} us/call")
    t0 = time.perf_counter_ns()
    for _ in range(n):
        _ = statuses["cam0"].connected.value
    t1 = time.perf_counter_ns()
    print(f"one multiprocessing.Value('b').value read: {(t1 - t0) / n / 1e3:.3f} us")


def pyav_copy():
    print("\n===== PyAV VideoFrame.from_ndarray copy semantics =====")
    try:
        import av
    except Exception as e:
        print(f"av not importable: {e}")
        return
    img = np.full((720, 1280, 3), 10, dtype=np.uint8)
    fr = av.VideoFrame.from_ndarray(img, format="bgr24")
    img[:] = 200
    back = fr.to_ndarray(format="bgr24")
    print(f"av {av.__version__}: after mutating source, frame still holds old pixels? {bool((back == 10).all())} "
          f"(True => from_ndarray copied the input)")


if __name__ == "__main__":
    print(sys.version)
    print("numpy", np.__version__)
    ipc = CameraGroupIPC.create(global_kill_flag=multiprocessing.Value("b", False),
                                heartbeat_timestamp=multiprocessing.Value("d", time.perf_counter()))
    run(720, 1280, ipc)
    run(1080, 1920, ipc)
    beartype_overhead()
    pyav_copy()
