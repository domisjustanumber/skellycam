"""Throwaway benchmark of the SkellyCam UI-tap server path (skellycam @ 23ccbf20).

Measures, per multiframe of N cameras:
  A. SharedMemoryRingBuffer.get_data_by_index copy (np.copyto from SHM slot into cached recarray)
  B. create_frontend_payload (resize 0.5 + JPEG q60 + packaging) end-to-end
  C. stage breakdown: cv2.resize, cv2.imencode, jpeg.tobytes, bytearray slice
  D. zlib (permessage-deflate default level) on the final payload
  E. whether bytearray[:n] is a copy, and actual asyncio.sleep(0.01) duration on this OS
Run:  C:\\Users\\Dom\\GitHub\\freemocap\\skellycam\\.venv\\Scripts\\python.exe ui_tap_bench.py
"""
import asyncio
import sys
import time
import zlib

import cv2
import numpy as np

sys.path.insert(0, r"C:\Users\Dom\GitHub\freemocap\skellycam")
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import SharedMemoryRingBuffer
from skellycam.core.types.frame_dtype_factories import create_frame_dtype
from skellycam.core.types.frontend_payload_bytearray import create_frontend_payload, JPEG_ENCODING_PARAMETERS

N_CAMS = 5
ITERS = 60


def synthetic_image(h: int, w: int, seed: int) -> np.ndarray:
    """Smooth gradient + moderate noise: compresses more like a real scene than pure noise."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    base = np.stack([(xx * 255 // w), (yy * 255 // h), ((xx + yy) * 255 // (w + h))], axis=-1).astype(np.int16)
    noise = rng.integers(-12, 12, size=(h, w, 3), dtype=np.int16)
    return np.clip(base + noise, 0, 255).astype(np.uint8)


def ms(t0: int, t1: int, n: int) -> float:
    return (t1 - t0) / 1e6 / n


def bench(h: int, w: int) -> None:
    shms, caches = {}, {}
    for i in range(N_CAMS):
        cid = f"cam{i}"
        cfg = CameraConfig(camera_id=cid, camera_index=i, resolution=ImageResolution(height=h, width=w))
        dt = create_frame_dtype(cfg)
        frame = np.recarray(1, dtype=dt)
        frame.frame_metadata.camera_info[0] = cfg.to_frame_camera_info()
        frame.frame_metadata.frame_number[0] = 0
        frame.frame_metadata.timestamps.pre_frame_grab_ns[0] = 1
        frame.frame_metadata.timestamps.post_frame_grab_ns[0] = 2
        frame.image[0] = synthetic_image(h, w, i)
        rb = SharedMemoryRingBuffer.create(example_data=frame, read_only=False, ring_buffer_length=4)
        rb.put_data(frame, overwrite_allowed=True)
        shms[cid] = rb
        caches[cid] = None

    # A. SHM -> process-local recarray copy (what get_latest_multiframe does via get_data_by_index)
    for cid, rb in shms.items():
        caches[cid] = rb.get_data_by_index(index=0, rec_array=caches[cid])
    t0 = time.perf_counter_ns()
    for _ in range(ITERS):
        for cid, rb in shms.items():
            caches[cid] = rb.get_data_by_index(index=0, rec_array=caches[cid])
    t1 = time.perf_counter_ns()
    a_ms = ms(t0, t1, ITERS)
    shares = np.shares_memory(caches["cam0"].image, shms["cam0"].ring_shm.buffer)

    # B. full create_frontend_payload
    create_frontend_payload(latest_frames=caches)
    t0 = time.perf_counter_ns()
    for _ in range(ITERS):
        fn, ts, payload = create_frontend_payload(latest_frames=caches)
    t1 = time.perf_counter_ns()
    b_ms = ms(t0, t1, ITERS)

    # C. stage breakdown for one camera image
    img = caches["cam0"].image[0]
    rw, rh = int(w * 0.5), int(h * 0.5)
    t0 = time.perf_counter_ns()
    for _ in range(ITERS):
        r = cv2.resize(img, (rw, rh), interpolation=cv2.INTER_LINEAR)
    t1 = time.perf_counter_ns()
    for _ in range(ITERS):
        ok, j = cv2.imencode(".jpg", r, JPEG_ENCODING_PARAMETERS)
    t2 = time.perf_counter_ns()
    for _ in range(ITERS):
        jb = j.tobytes()
    t3 = time.perf_counter_ns()
    for _ in range(ITERS):
        sl = payload[:len(payload)]
    t4 = time.perf_counter_ns()

    # D. permessage-deflate cost (zlib default level, raw deflate wbits=-15 like websockets)
    t5 = time.perf_counter_ns()
    for _ in range(10):
        enc = zlib.compressobj(wbits=-15)
        z = enc.compress(bytes(payload)) + enc.flush(zlib.Z_SYNC_FLUSH)
    t6 = time.perf_counter_ns()

    print(f"--- {N_CAMS} cams @ {w}x{h} BGR (raw frame {h*w*3/1e6:.2f} MB) ---")
    print(f"A  SHM->local copy (get_data_by_index, {N_CAMS} cams): {a_ms:.2f} ms/multiframe; shares_memory={shares}")
    print(f"B  create_frontend_payload ({N_CAMS} cams):            {b_ms:.2f} ms/multiframe -> max {1000/b_ms:.0f} payloads/s")
    print(f"   payload size: {len(payload)/1024:.1f} KiB; type={type(payload).__name__}")
    print(f"C  per camera: resize {ms(t0,t1,ITERS):.2f} ms, imencode q60 {ms(t1,t2,ITERS):.2f} ms, "
          f"tobytes {ms(t2,t3,ITERS)*1000:.1f} us, payload[:n] slice {ms(t3,t4,ITERS)*1000:.1f} us")
    print(f"D  zlib deflate on payload: {ms(t5,t6,10):.2f} ms, {len(payload)} -> {len(z)} bytes")
    for rb in shms.values():
        rb.close_and_unlink()


def copy_checks() -> None:
    ba = bytearray(b"abcdef")
    sl = ba[:3]
    ba[0] = ord("Z")
    print(f"E1 bytearray[:n] is a copy: {sl[0] != ord('Z')} (slice type {type(sl).__name__})")


async def sleep_check() -> None:
    durs = []
    for _ in range(100):
        t0 = time.perf_counter()
        await asyncio.sleep(0.01)
        durs.append((time.perf_counter() - t0) * 1000)
    durs = np.array(durs)
    print(f"E2 asyncio.sleep(0.01) on {sys.platform} ({type(asyncio.get_running_loop()).__name__}): "
          f"mean {durs.mean():.2f} ms, p50 {np.median(durs):.2f} ms, max {durs.max():.2f} ms")


if __name__ == "__main__":
    print(f"cv2 {cv2.__version__}, numpy {np.__version__}, threads cv2={cv2.getNumThreads()}")
    copy_checks()
    asyncio.run(sleep_check())
    bench(720, 1280)
    bench(1080, 1920)
