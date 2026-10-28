"""Throwaway probe for the SkellyCam ring-buffer READ paths (does not modify repo).

Run:  C:\\Users\\Dom\\GitHub\\freemocap\\skellycam\\.venv\\Scripts\\python.exe read_path_probe.py
"""
import sys
import time
from copy import copy

import numpy as np
import cv2

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
from skellycam.core.ipc.shared_memory.camera_group_shared_memory import (
    CameraGroupSharedMemory, _frame_recarray_cache)
from skellycam.core.types.frame_dtype_factories import create_frame_dtype
from skellycam.core.types.frontend_payload_bytearray import create_frontend_payload
from skellycam.core.camera.opencv.opencv_helpers.create_initial_frame_recarray import create_initial_frame_rec_array


def timeit(fn, n):
    ts = []
    for _ in range(n):
        t = time.perf_counter_ns(); fn(); ts.append(time.perf_counter_ns() - t)
    a = np.array(ts) / 1e6
    return f"median {np.median(a):.3f} ms  p95 {np.percentile(a, 95):.3f} ms  (n={n})"


class _IPC:  # minimal stand-in for CameraGroupIPC used by create_initial_frame_rec_array
    timebase_mapping = TimebaseMapping()


def run(width, height, n_cams=5):
    print(f"\n===== {n_cams} cameras @ {width}x{height} BGR =====")
    configs = {str(i): CameraConfig(camera_id=str(i), camera_index=i,
                                    resolution={"width": width, "height": height})
               for i in range(n_cams)}
    tb = TimebaseMapping()
    # main/server process side: created read_only=True like camera_group.py:112-116
    group = CameraGroupSharedMemory.create(camera_configs=configs, timebase_mapping=tb, read_only=True)
    # camera-process side: recreated read_only=False like setup_opencv_camera_loop.py:54-55
    writers = {cid: type(shm).recreate(dto=shm.to_dto(), read_only=False) for cid, shm in group.camera_shms.items()}
    try:
        any_shm = next(iter(group.camera_shms.values()))
        dt = create_frame_dtype(configs["0"])
        print(f"frame dtype itemsize = {dt.itemsize} bytes; image bytes = {width*height*3}; "
              f"metadata+pad = {dt.itemsize - width*height*3}")
        print(f"ring_buffer_length per camera = {any_shm.ring_buffer_length} slots "
              f"({any_shm.ring_buffer_length / 60:.2f} s of headroom at 60 fps); "
              f"shm bytes per camera = {any_shm.ring_shm.size}")

        # mirrors create_initial_frame_recarray.py:8-19 (beartype rejects a stand-in IPC object)
        frames = {}
        for cid, cfg in configs.items():
            fr = np.recarray(1, dtype=create_frame_dtype(cfg))
            fr.frame_metadata.camera_info[0] = cfg.to_frame_camera_info()
            fr.frame_metadata.frame_number[0] = -1
            fr.frame_metadata.timebase_mapping[0] = tb.to_numpy_record_array()
            frames[cid] = fr
        for cid, f in frames.items():
            f.image[0] = np.random.randint(0, 255, f.image[0].shape, dtype=np.uint8)

        # --- producer-side copy count (context only) ---
        f0 = frames["0"]
        c = copy(f0)
        print(f"copy.copy(recarray) shares memory with source? {np.shares_memory(c, f0)} "
              f"(False => put_data() line 132 allocates+copies once, then slot assignment copies again)")

        # write 3 frames per camera with frame numbers 0..2 (mimics camera loop)
        for fn in range(3):
            for cid, f in frames.items():
                f.frame_metadata.frame_number[0] = fn
                writers[cid].put_frame(f, overwrite=True)

        # --- READ: get_latest_multiframe returns private copies, not shm views ---
        lm = group.get_latest_multiframe()
        shm_slot = group.camera_shms["0"].ring_shm.buffer
        print(f"get_latest_multiframe() result shares memory with SHM ring? "
              f"{np.shares_memory(lm['0'], shm_slot)}")
        lm_ids_1 = {cid: id(r) for cid, r in lm.items()}
        lm2 = group.get_latest_multiframe()
        print(f"get_latest_multiframe() reuses the same destination recarrays on 2nd call? "
              f"{all(id(r) == lm_ids_1[cid] for cid, r in lm2.items())}")

        # --- READ: get_images_by_frame_number cache behaviour ---
        r1 = group.get_images_by_frame_number(frame_number=1)
        r2 = group.get_images_by_frame_number(frame_number=1)
        print(f"get_images_by_frame_number: module cache populated after calls? {len(_frame_recarray_cache)} entries; "
              f"same destination arrays reused across calls? {all(r1[c_] is r2[c_] for c_ in r1)}")

        # --- Recorder input: frame.image[0] is a view of the camera's local recarray ---
        img = f0.image[0]
        print(f"VideoRecorder input frame.image[0]: shares memory with camera-local recarray? "
              f"{np.shares_memory(img, f0)}; C-contiguous? {img.flags['C_CONTIGUOUS']}; "
              f"shares memory with SHM? {np.shares_memory(img, shm_slot)}")

        # --- frontend payload: bytearray slice copies ---
        fn_, ts_, payload = create_frontend_payload(latest_frames=lm)
        import skellycam.core.types.frontend_payload_bytearray as fpb
        same = (payload is fpb._reusable_bytes_payload)
        print(f"create_frontend_payload returns the reusable buffer itself? {same} "
              f"(False => bytearray[:n] slice made a new copy of {len(payload)} bytes)")

        # --- timings of the read paths ---
        print("get_latest_multiframe (5x np.copyto from SHM):      ", timeit(group.get_latest_multiframe, 200))
        print("get_images_by_frame_number (alloc + 5x copyto):     ",
              timeit(lambda: group.get_images_by_frame_number(frame_number=2), 200))
        print("create_frontend_payload (resize 0.5 + JPEG q60 x5): ",
              timeit(lambda: create_frontend_payload(latest_frames=lm), 50))
        print("single-camera np.copyto of one frame slot:          ",
              timeit(lambda: np.copyto(lm['0'], group.camera_shms['0'].ring_shm.buffer[2]), 200))
    finally:
        for w in writers.values():
            w.close()
        group.unlink_and_close()


if __name__ == "__main__":
    print(sys.version)
    print("numpy", np.__version__, "cv2", cv2.__version__)
    run(1280, 720)
    run(1920, 1080)
