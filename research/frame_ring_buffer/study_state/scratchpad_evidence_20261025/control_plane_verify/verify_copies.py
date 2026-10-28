"""Verifier checks (read-only use of skellycam). Run from C:/Users/Dom/GitHub/freemocap/skellycam:
   .venv/Scripts/python.exe -u <this file>
V1: does copy(frame.frame_metadata) (video_recorder.py L108) copy only metadata or the whole frame record?
V2: SharedMemoryRingBuffer.put_data (copy + slot assign) vs a single np.copyto, both into ROTATING slots (fair cache conditions)
V3: is camera_loop_update_checks beartype-wrapped (raises BeartypeCallHintParamViolation on wrong-typed arg)?
V4: does cv2.VideoCapture.retrieve(image=buf) write into the caller's buffer (FFMPEG file backend)?
"""
import os, sys, time, tempfile
from copy import copy
import numpy as np

def timeit(fn, n):
    t0 = time.perf_counter_ns()
    for _ in range(n):
        fn()
    return (time.perf_counter_ns() - t0) / n

def main():
    from skellycam.core.types.numpy_record_dtypes import FRAME_METADATA_DTYPE
    from skellycam.core.types.frame_dtype_factories import create_frame_dtype
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera.config.image_resolution import ImageResolution
    from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import SharedMemoryRingBuffer
    print(f"numpy {np.__version__}; FRAME_METADATA_DTYPE.itemsize={FRAME_METADATA_DTYPE.itemsize}")

    # V1
    cfg = CameraConfig(resolution=ImageResolution(width=1920, height=1080))
    fdt = create_frame_dtype(cfg)
    frame = np.recarray(1, dtype=fdt)
    md = copy(frame.frame_metadata)
    print(f"V1 frame itemsize={fdt.itemsize}; copy(frame.frame_metadata): type={type(md).__name__} nbytes={md.nbytes} "
          f"shares_memory_with_frame={np.shares_memory(md, frame)} owns_data={md.flags.owndata}")

    # V2
    for (w, h) in ((1280, 720), (1920, 1080)):
        cfg = CameraConfig(resolution=ImageResolution(width=w, height=h))
        fdt = create_frame_dtype(cfg)
        frame = np.recarray(1, dtype=fdt); frame.image[0] = 7
        L = 32
        rb = SharedMemoryRingBuffer.create(example_data=frame, read_only=False, ring_buffer_length=L)
        buf = rb.ring_shm.buffer
        for i in range(L):  # pre-fault all pages
            np.copyto(buf[i:i+1], frame)
        n = 400
        put = timeit(lambda: rb.put_data(frame, overwrite_allowed=True), n)
        k = [0]
        def single():
            i = k[0] % L; k[0] += 1
            np.copyto(buf[i:i+1], frame)
        one = timeit(single, n)
        cp = timeit(lambda: copy(frame), n)
        k[0] = 0
        def assign_only():
            i = k[0] % L; k[0] += 1
            buf[i] = frame
        asg = timeit(assign_only, n)
        print(f"V2 {w}x{h} itemsize {fdt.itemsize/1e6:.2f} MB: put_data {put/1e6:.3f} ms | copy(frame) {cp/1e6:.3f} ms | "
              f"buf[i]=frame (no copy()) {asg/1e6:.3f} ms | np.copyto rotating slot {one/1e6:.3f} ms")
        rb.close_and_unlink()

    # V3
    from skellycam.core.camera.opencv.opencv_helpers.camera_loop_update_checks import camera_loop_update_checks
    try:
        camera_loop_update_checks(config="not a config", cv2_video_capture=None, frame_rec_array=None, ipc=None,
                                  orchestrator=None, recording_info_subscription=None, self_status=None,
                                  update_camera_settings_subscription=None, video_recorder=None)
        print("V3 no exception")
    except Exception as e:
        print(f"V3 camera_loop_update_checks raised {type(e).__module__}.{type(e).__name__}")

    # V4
    import cv2
    path = os.path.join(tempfile.gettempdir(), "skc_verify_v4.avi")
    vw = cv2.VideoWriter(path, cv2.VideoWriter.fourcc(*"MJPG"), 30, (640, 480))
    for i in range(5):
        vw.write(np.full((480, 640, 3), 40 * i, np.uint8))
    vw.release()
    cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG)
    rec = np.recarray(1, dtype=np.dtype([("frame_metadata", FRAME_METADATA_DTYPE), ("image", np.uint8, (480, 640, 3))], align=True))
    rec.image[0] = 255
    target = rec.image[0]
    cap.grab()
    ok, out = cap.retrieve(image=target)
    print(f"V4 retrieve ok={ok}; target C-contig={target.flags.c_contiguous}; returned shares memory with recarray slot="
          f"{np.shares_memory(out, rec)}; slot modified={(rec.image[0] != 255).any()}")
    cap.release(); os.remove(path)

if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)
