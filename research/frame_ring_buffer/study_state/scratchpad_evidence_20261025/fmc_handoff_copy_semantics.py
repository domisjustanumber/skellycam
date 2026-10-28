"""
Throwaway probe of the skellycam ring-buffer read paths that FreeMoCap calls
(installed copy: freemocap/.venv site-packages skellycam @777b058c).
Run with:  C:/Users/Dom/GitHub/freemocap/freemocap/.venv/Scripts/python.exe <this file>
Checks:
 1. ring length per camera (1 GiB / itemsize) for 1280x720x3 and 1920x1080x3
 2. get_data_by_index(rec_array=...) returns caller's buffer, NOT a view of SHM (np.shares_memory)
 3. frame_recarray.image[0] is a view of the caller's local buffer (no extra copy)
 4. cv2.rotate produces a new array (copy)
 5. CameraGroupSharedMemory.get_images_by_frame_number() allocates new recarrays every call
    (module-level _frame_recarray_cache is never populated)
 6. timing of get_data_by_index (one full-frame memcpy) and create_frontend_payload (UI path)
"""
import time, sys
import numpy as np, cv2
import skellycam, os
print("skellycam from:", os.path.dirname(skellycam.__file__))
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
from skellycam.core.ipc.shared_memory.camera_group_shared_memory import CameraGroupSharedMemory
from skellycam.core.ipc.shared_memory import camera_group_shared_memory as cgsm_mod
from skellycam.core.types.frontend_payload_bytearray import create_frontend_payload

N_ITERS = 200

def bench(fn, n=N_ITERS):
    fn()
    t = []
    for _ in range(n):
        t0 = time.perf_counter(); fn(); t.append((time.perf_counter() - t0) * 1e3)
    t = np.array(t)
    return f"median={np.median(t):.3f}ms p95={np.percentile(t,95):.3f}ms"

for (w, h) in [(1280, 720), (1920, 1080)]:
    print(f"\n=== {w}x{h} BGR (3ch) ===")
    cfg = CameraConfig(camera_id="0", resolution=ImageResolution(width=w, height=h), color_channels=3)
    tbm = TimebaseMapping()
    writer = CameraSharedMemoryRingBuffer.from_config(camera_config=cfg, timebase_mapping=tbm, read_only=False)
    try:
        itemsize = writer.dtype.itemsize
        print(f"frame itemsize={itemsize} bytes ({itemsize/2**20:.2f} MiB); ring_buffer_length={writer.ring_buffer_length} slots;"
              f" window at 60fps={writer.ring_buffer_length/60:.2f}s; 5 cams SHM={5*writer.ring_buffer_length*itemsize/2**30:.2f} GiB")
        # write a few frames like the camera loop does (opencv_camera_loop.py L96: overwrite=True)
        frame = np.recarray(1, dtype=writer.dtype)
        for i in range(5):
            frame.frame_metadata.frame_number[0] = i
            frame.image[0][:] = i
            writer.put_frame(frame, overwrite=True)
        # reader attaches by name (as CameraNode does: camera_node.py L155-158)
        reader = CameraSharedMemoryRingBuffer.recreate(dto=writer.to_dto(), read_only=False)
        out = reader.get_data_by_index(index=4, rec_array=None)
        slot = reader.ring_shm.buffer[4 % reader.ring_buffer_length]
        print("get_data_by_index result shares memory with SHM slot:", np.shares_memory(out, reader.ring_shm.buffer))
        out2 = reader.get_data_by_index(index=3, rec_array=out)
        print("get_data_by_index(rec_array=out) returns same object:", out2 is out, "| image value now", int(out2.image[0][0,0,0]))
        img_view = out2.image[0]
        print("frame_recarray.image[0] shares memory with local recarray:", np.shares_memory(img_view, out2))
        rot = cv2.rotate(img_view, cv2.ROTATE_90_CLOCKWISE)
        print("cv2.rotate output shares memory with input:", np.shares_memory(rot, img_view))
        print("last_read_index after get_data_by_index:", reader.last_read_index.value, "(unchanged => reader invisible to writer's overwrite check)")
        print("get_data_by_index (1 full-frame memcpy, reused buffer):", bench(lambda: reader.get_data_by_index(index=4, rec_array=out)))
        print("cv2.rotate 90:", bench(lambda: cv2.rotate(img_view, cv2.ROTATE_90_CLOCKWISE)))

        # Group-level (main-process UI path): get_images_by_frame_number
        grp = CameraGroupSharedMemory(camera_shms={"0": reader}, camera_configs={"0": cfg}, read_only=True)
        a = grp.get_images_by_frame_number(frame_number=4)
        b = grp.get_images_by_frame_number(frame_number=4)
        print("get_images_by_frame_number returns new recarray each call:", a["0"] is not b["0"],
              "| module _frame_recarray_cache size:", len(cgsm_mod._frame_recarray_cache))
        print("get_images_by_frame_number (alloc + memcpy):", bench(lambda: grp.get_images_by_frame_number(frame_number=4)))
        frames = grp.get_images_by_frame_number(frame_number=4)
        frames["0"].image[0][:] = np.random.randint(0, 255, size=frames["0"].image[0].shape, dtype=np.uint8)
        fnum, ts, payload = create_frontend_payload(latest_frames=frames)
        print(f"create_frontend_payload: payload {len(payload)} bytes; type {type(payload).__name__};",
              "shares memory with module buffer:",
              np.shares_memory(np.frombuffer(payload, np.uint8), np.frombuffer(sys.modules['skellycam.core.types.frontend_payload_bytearray']._reusable_bytes_payload, np.uint8)))
        print("create_frontend_payload (rotate?+resize 0.5+JPEG q60+copies), random-noise image (worst case):", bench(lambda: create_frontend_payload(latest_frames=frames), n=50))
        reader.close()
    finally:
        writer.close_and_unlink()
