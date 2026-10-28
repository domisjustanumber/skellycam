"""Verifier v3: how much Windows commit charge does one production-sized camera ring take, and when?

Creates CameraSharedMemoryRingBuffer.from_config (default 1 GiB) and reads system CommitTotal
(GetPerformanceInfo) before creation, after creation (no pages touched), and after one full lap of
put_frame (all pages touched). Also reports this process's private/working-set bytes.

Run from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam:
    .venv\\Scripts\\python.exe <this file>
"""
import ctypes
import ctypes.wintypes as wt
import multiprocessing
import multiprocessing.queues  # noqa
import time

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.camera.opencv.opencv_helpers.create_initial_frame_recarray import create_initial_frame_rec_array
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer


class PERFORMANCE_INFORMATION(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("CommitTotal", ctypes.c_size_t), ("CommitLimit", ctypes.c_size_t),
                ("CommitPeak", ctypes.c_size_t), ("PhysicalTotal", ctypes.c_size_t),
                ("PhysicalAvailable", ctypes.c_size_t), ("SystemCache", ctypes.c_size_t),
                ("KernelTotal", ctypes.c_size_t), ("KernelPaged", ctypes.c_size_t),
                ("KernelNonpaged", ctypes.c_size_t), ("PageSize", ctypes.c_size_t),
                ("HandleCount", wt.DWORD), ("ProcessCount", wt.DWORD), ("ThreadCount", wt.DWORD)]


def commit_mib():
    pi = PERFORMANCE_INFORMATION()
    pi.cb = ctypes.sizeof(pi)
    ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(pi), pi.cb)
    return pi.CommitTotal * pi.PageSize / 2 ** 20, pi.CommitLimit * pi.PageSize / 2 ** 20


if __name__ == "__main__":
    ipc = CameraGroupIPC.create(global_kill_flag=multiprocessing.Value("b", False),
                                heartbeat_timestamp=multiprocessing.Value("d", time.perf_counter()))
    cfg = CameraConfig(resolution=ImageResolution(height=720, width=1280))
    c0, lim = commit_mib()
    ring = CameraSharedMemoryRingBuffer.from_config(camera_config=cfg, timebase_mapping=ipc.timebase_mapping,
                                                    read_only=False)
    time.sleep(0.5)
    c1, _ = commit_mib()
    frame = create_initial_frame_rec_array(config=cfg, ipc=ipc)
    t0 = time.perf_counter()
    for _ in range(ring.ring_buffer_length):
        ring.put_frame(frame_rec_array=frame, overwrite=True)
    lap_s = time.perf_counter() - t0
    time.sleep(0.5)
    c2, _ = commit_mib()
    print(f"CommitLimit {lim:.0f} MiB")
    print(f"system CommitTotal delta after creating 1 ring (no pages touched): {c1 - c0:+.0f} MiB")
    print(f"system CommitTotal delta after one full put_frame lap ({ring.ring_buffer_length} frames, {lap_s:.2f} s): {c2 - c0:+.0f} MiB")
    ring.close_and_unlink()
