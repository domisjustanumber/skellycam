"""Verifier checks for the UI-tap map (skellycam @ 23ccbf20). Run:
C:/Users/Dom/GitHub/freemocap/skellycam/.venv/Scripts/python.exe uitap_verify_copies.py
"""
import io, sys, logging, time
logging.disable(logging.CRITICAL)
sys.path.insert(0, r"C:\Users\Dom\GitHub\freemocap\skellycam")
import numpy as np, cv2
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.types.frame_dtype_factories import create_frame_dtype
from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import ONE_GIGABYTE

# V1: ring slots per camera = 1 GiB // itemsize
for h, w in [(720, 1280), (1080, 1920)]:
    cfg = CameraConfig(camera_id="c0", camera_index=0, resolution=ImageResolution(height=h, width=w))
    dt = create_frame_dtype(cfg)
    print(f"V1 {w}x{h}: itemsize={dt.itemsize} B, image bytes={h*w*3}, slots per 1GiB={ONE_GIGABYTE // dt.itemsize}, "
          f"seconds of history @60fps={ONE_GIGABYTE // dt.itemsize / 60:.2f}")

# V2: BytesIO.write copies payload; getvalue() returns the internal buffer (no 2nd copy) on CPython 3.12?
payload = bytes(80 * 1024)
b = io.BytesIO(); b.write(b"\x82\x7f" + bytes(8)); b.write(payload)
v1 = b.getvalue(); v2 = b.getvalue()
print(f"V2 python {sys.version.split()[0]}: BytesIO.getvalue() returns same object twice (no copy on getvalue): {v1 is v2}")

# V3: memoryview slice of bytearray is a view (zero copy) and is accepted where BytesLike is accepted
ba = bytearray(b"abcdef"); mv = memoryview(ba)[:3]; ba[0] = ord("Z")
print(f"V3 memoryview(bytearray)[:n] is a view: {mv[0] == ord('Z')}")

# V4: cv2.imencode returns a numpy uint8 array; assigning it into bytearray slice without tobytes works
ok, j = cv2.imencode(".jpg", np.zeros((540, 960, 3), np.uint8), [int(cv2.IMWRITE_JPEG_QUALITY), 60])
buf = bytearray(len(j) + 10); buf[0:len(j)] = j.data  # buffer-protocol assignment, one memcpy
print(f"V4 imencode type={type(j).__name__} shape={j.shape}; bytearray[:]=ndarray.data works: {bytes(buf[:len(j)]) == j.tobytes()}")

# V5: cv2.resize from a view into a larger buffer (simulating an SHM slot view) does not require a prior copy
big = np.zeros((4, 1080, 1920, 3), np.uint8); view = big[2]
r = cv2.resize(view, (960, 540), interpolation=cv2.INTER_LINEAR)
print(f"V5 resize input is view of buffer: {np.shares_memory(view, big)}; output shares: {np.shares_memory(r, big)}")

# V6: cv2.rotate always returns a new full-size array
img = np.zeros((1080, 1920, 3), np.uint8)
rot = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
print(f"V6 rotate output shape={rot.shape}, shares memory with input: {np.shares_memory(rot, img)}")

# V7: cost of resize-then-rotate vs rotate-then-resize at 1080p (per camera)
N = 60
t0 = time.perf_counter_ns()
for _ in range(N): cv2.resize(cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE), (540, 960))
t1 = time.perf_counter_ns()
for _ in range(N): cv2.rotate(cv2.resize(img, (960, 540)), cv2.ROTATE_90_CLOCKWISE)
t2 = time.perf_counter_ns()
print(f"V7 1080p rotate->resize {(t1-t0)/N/1e6:.2f} ms vs resize->rotate {(t2-t1)/N/1e6:.2f} ms per camera")
