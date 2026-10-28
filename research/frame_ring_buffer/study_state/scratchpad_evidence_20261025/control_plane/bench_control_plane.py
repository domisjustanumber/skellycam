"""
Throwaway micro-benchmark for the SkellyCam control plane (read-only use of skellycam modules).

Measures, on this machine:
  A. cost of a multiprocessing.Value(lock=True) .value read vs RawValue read
  B. cost of CameraGroupIPC.should_continue (3 Synchronized reads + perf_counter)
  C. cost of multiprocessing.Queue.empty() on an empty queue
  D. cost of CameraOrchestrator.should_grab_by_id() for N=5 cameras
  E. cost of camera_loop_update_checks() with empty queues (the per-iteration control poll)
  F. real duration of wait_10us() and wait_1ms() (time.sleep(1e-5) / time.sleep(1e-3))
  G. size/time to pickle a RecordingFinishedMessage for 10 min @ 60 fps (36000 frames)
  H. SharedMemoryRingBuffer.put_data cost vs a single np.copyto into the slot (1080p BGR)

Run:
  C:/Users/Dom/GitHub/freemocap/skellycam/.venv/Scripts/python.exe bench_control_plane.py
(from the C:/Users/Dom/GitHub/freemocap/skellycam directory so skellycam is importable)
"""
import multiprocessing
import pickle
import platform
import statistics
import sys
import time
from copy import copy

import numpy as np


def timeit(fn, n):
    t0 = time.perf_counter_ns()
    for _ in range(n):
        fn()
    return (time.perf_counter_ns() - t0) / n


def main():
    print(f"python {sys.version.split()[0]} on {platform.platform()}  numpy {np.__version__}")
    from skellycam.core.camera_group.camera_status import CameraStatus
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
    from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
    from skellycam.core.camera.opencv.opencv_helpers.camera_loop_update_checks import camera_loop_update_checks
    from skellycam.core.ipc.pubsub.pubsub_topics import RecordingFinishedMessage
    from skellycam.core.types.numpy_record_dtypes import FRAME_METADATA_DTYPE
    from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import SharedMemoryRingBuffer
    from skellycam.core.recorders.videos.recording_info import RecordingInfo

    N = 200_000
    # A
    v = multiprocessing.Value("b", False)
    rv = multiprocessing.RawValue("b", False)
    print(f"A. Value(lock=True).value read : {timeit(lambda: v.value, N):8.0f} ns")
    print(f"A. RawValue.value read         : {timeit(lambda: rv.value, N):8.0f} ns")

    # B
    kill = multiprocessing.Value("b", False)
    hb = multiprocessing.Value("d", time.perf_counter())
    ipc = CameraGroupIPC.create(global_kill_flag=kill, heartbeat_timestamp=hb)
    print(f"B. ipc.should_continue          : {timeit(lambda: ipc.should_continue, N):8.0f} ns")

    # C
    q = multiprocessing.Queue()
    print(f"C. mp.Queue.empty() (empty)     : {timeit(lambda: q.empty(), N):8.0f} ns")

    # D
    for ncam in (1, 5):
        statuses = {f"cam{i}": CameraStatus() for i in range(ncam)}
        for s in statuses.values():
            s.connected.value = True
            s.frame_count.value = 10
        orch = CameraOrchestrator.from_statuses(statuses)
        assert orch.should_grab_by_id("cam0")
        print(f"D. should_grab_by_id ({ncam} cams)    : {timeit(lambda: orch.should_grab_by_id('cam0'), 50_000):8.0f} ns")

    # E  (5 cams, empty subscription queues; beartype is active package-wide so real-typed args are passed)
    status0 = statuses["cam0"]
    rec_q = multiprocessing.Queue()
    upd_q = multiprocessing.Queue()

    import cv2
    from skellycam.core.camera.config.camera_config import CameraConfig as _CC
    _cfg = _CC()
    _cap = cv2.VideoCapture()  # unopened; only touched when an update message is present
    _fra = np.recarray(1, dtype=FRAME_METADATA_DTYPE)  # only touched when an update message is present

    def _checks():
        camera_loop_update_checks(config=_cfg, cv2_video_capture=_cap, frame_rec_array=_fra, ipc=ipc,
                                  orchestrator=orch, recording_info_subscription=rec_q, self_status=status0,
                                  update_camera_settings_subscription=upd_q, video_recorder=None, framerate=None)

    print(f"E. camera_loop_update_checks    : {timeit(_checks, 50_000):8.0f} ns")

    def _full_poll():  # everything the camera loop evaluates per iteration before grab (5 cams)
        _ = ipc.should_continue
        _checks()
        _ = status0.should_close.value
        _ = status0.is_paused.value
        _ = orch.should_grab_by_id("cam0")

    print(f"E. full pre-grab control poll   : {timeit(_full_poll, 50_000):8.0f} ns  (5 cams)")

    # F
    for name, dur in (("wait_10us", 1e-5), ("wait_1ms", 1e-3)):
        samples = []
        for _ in range(2000):
            t0 = time.perf_counter_ns()
            time.sleep(dur)
            samples.append((time.perf_counter_ns() - t0) / 1e3)
        print(f"F. {name:9s} requested {dur*1e6:7.1f} us -> median {statistics.median(samples):8.1f} us, "
              f"p99 {sorted(samples)[int(0.99*len(samples))]:8.1f} us")

    # G
    print(f"G. FRAME_METADATA_DTYPE.itemsize = {FRAME_METADATA_DTYPE.itemsize} bytes")
    n_frames = 36_000
    base = np.recarray(1, dtype=FRAME_METADATA_DTYPE)
    base.camera_info.camera_id[0] = "0"
    mds = []
    for i in range(n_frames):
        md = copy(base)
        md.frame_number[0] = i
        mds.append(md)
    ri = RecordingInfo(recording_name="bench", recording_directory="C:/tmp", mic_device_index=-1)
    t0 = time.perf_counter()
    msg = RecordingFinishedMessage(recording_info=ri, frame_metadatas=mds)
    t1 = time.perf_counter()
    blob = pickle.dumps(msg, protocol=pickle.HIGHEST_PROTOCOL)
    t2 = time.perf_counter()
    pickle.loads(blob)
    t3 = time.perf_counter()
    print(f"G. RecordingFinishedMessage({n_frames} frames): __post_init__ {1e3*(t1-t0):.0f} ms, "
          f"pickle {1e3*(t2-t1):.0f} ms, {len(blob)/1e6:.1f} MB, unpickle {1e3*(t3-t2):.0f} ms")

    # H
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.types.frame_dtype_factories import create_frame_dtype
    from skellycam.core.camera.config.image_resolution import ImageResolution
    cfg = CameraConfig(resolution=ImageResolution(width=1920, height=1080))
    fdt = create_frame_dtype(cfg)
    frame = np.recarray(1, dtype=fdt)
    frame.image[0] = 7
    rb = SharedMemoryRingBuffer.create(example_data=frame, read_only=False, ring_buffer_length=8)
    put = timeit(lambda: rb.put_data(frame, overwrite_allowed=True), 300)
    direct = timeit(lambda: np.copyto(rb.ring_shm.buffer[3:4], frame), 300)
    cp = timeit(lambda: copy(frame), 300)
    print(f"H. 1080p frame itemsize {fdt.itemsize/1e6:.2f} MB: put_data {put/1e6:.3f} ms, "
          f"copy(frame) alone {cp/1e6:.3f} ms, single np.copyto into slot {direct/1e6:.3f} ms")
    rb.close_and_unlink()
    ipc.pubsub.close()


if __name__ == "__main__":
    main()
