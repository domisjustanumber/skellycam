"""
Verifier probe for the SkellyCam -> FreeMoCap handoff map (installed skellycam @777b058c).
Run: C:/Users/Dom/GitHub/freemocap/freemocap/.venv/Scripts/python.exe -I <this file>
Checks:
 A. put_data's `copy(data)` (ring_buffer_shared_memory.py L132) is a full extra frame copy before the SHM store.
 B. read_only=True on recreate is only a Python flag: the mapping is still writable from that process.
 C. get_data_by_index lets a reader read the slot the writer will overwrite NEXT (head - index == len-1).
 D. A zero-copy view of a SHM slot exists and cv2.resize / cv2.imencode accept it directly.
"""
import time
from copy import copy
import numpy as np
import cv2
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import SharedMemoryRingBuffer


def bench(fn, n=200):
    fn()
    t = []
    for _ in range(n):
        t0 = time.perf_counter(); fn(); t.append((time.perf_counter() - t0) * 1e3)
    return f"median={np.median(t):.3f}ms p95={np.percentile(t, 95):.3f}ms"


for (w, h) in [(1280, 720), (1920, 1080)]:
    print(f"\n=== {w}x{h} BGR ===")
    cfg = CameraConfig(camera_id="0", resolution=ImageResolution(width=w, height=h), color_channels=3)
    writer = CameraSharedMemoryRingBuffer.from_config(camera_config=cfg, timebase_mapping=TimebaseMapping(), read_only=False)
    try:
        frame = np.recarray(1, dtype=writer.dtype)
        frame.image[0][:] = 7
        # A. copy(data) is a separate full-size buffer
        c = copy(frame)
        print("A. copy(frame) shares memory with frame:", np.shares_memory(c, frame), "| nbytes:", c.nbytes)
        print("A. put_frame (copy(data) + slot store):", bench(lambda: writer.put_frame(frame, overwrite=True)))
        slot = writer.ring_shm.buffer[0:1]
        print("A. single np.copyto(frame -> slot) only:", bench(lambda: np.copyto(slot, frame)))

        # B. read_only flag does not protect the mapping
        ro = CameraSharedMemoryRingBuffer.recreate(dto=writer.to_dto(), read_only=True)
        before = int(writer.ring_shm.buffer[0].image[0, 0, 0])
        ro.ring_shm.buffer[0].image[0, 0, 0] = 123
        after = int(writer.ring_shm.buffer[0].image[0, 0, 0])
        print(f"B. write through read_only=True mapping succeeded: before={before} after={after}")

        # D. zero-copy view of a slot, consumable by cv2
        view = ro.ring_shm.buffer[0].image  # no np.copyto
        print("D. slot image view shares memory with SHM:", np.shares_memory(view, ro.ring_shm.buffer), "| writeable flag:", view.flags.writeable)
        small = cv2.resize(view, (w // 2, h // 2), interpolation=cv2.INTER_LINEAR)
        ok, jpg = cv2.imencode('.jpg', small, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
        print("D. cv2.resize+imencode on SHM view ok:", ok, "| jpeg bytes:", len(jpg))
        print("D. resize(view)->imencode, no SHM copy:", bench(lambda: cv2.imencode('.jpg', cv2.resize(view, (w // 2, h // 2)), [int(cv2.IMWRITE_JPEG_QUALITY), 60]), n=50))
        ro.close()
    finally:
        writer.close_and_unlink()

# C. off-by-one: the oldest index get_data_by_index accepts maps to the slot the writer writes next
dt = np.dtype([('v', np.int64)])
ring = SharedMemoryRingBuffer.create(example_data=np.recarray(1, dtype=dt), read_only=False, ring_buffer_length=5)
try:
    for i in range(10):
        d = np.recarray(1, dtype=dt); d.v = i
        ring.put_data(d, overwrite_allowed=True)
    head = ring.last_written_index.value
    L = ring.ring_buffer_length
    oldest_ok = head - (L - 1)
    r = ring.get_data_by_index(index=oldest_ok)
    print(f"\nC. head={head} len={L}: get_data_by_index({oldest_ok}) accepted, value={int(r.v[0])}; "
          f"its slot={oldest_ok % L}, next write slot={(head + 1) % L} -> same slot: {oldest_ok % L == (head + 1) % L}")
    try:
        ring.get_data_by_index(index=head - L)
    except IndexError as e:
        print("C. get_data_by_index(head-len) raises IndexError:", str(e)[:80])
finally:
    ring.close_and_unlink()
