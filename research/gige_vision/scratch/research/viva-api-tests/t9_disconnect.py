"""What the application sees when the camera vanishes mid-stream."""
import time
import viva_genicam as vg
from viva_genicam.testing import FakeGigeCamera

fake = FakeGigeCamera(width=320, height=240, fps=30)
fake.start()
cam = vg.connect_gige(fake.device_info())
frames = cam.stream()
frames.__enter__()
print("first frame", frames.next_frame(timeout_ms=3000).block_id)
fake.stop()
t0 = time.perf_counter()
for i in range(8):
    t = time.perf_counter()
    try:
        fr = frames.next_frame(timeout_ms=1000)
        print(f"  [{time.perf_counter() - t0:5.2f}s] next_frame -> {fr if fr is None else fr.block_id}")
        if fr is None:
            break
    except Exception as e:
        print(f"  [{time.perf_counter() - t0:5.2f}s] next_frame -> {type(e).__name__}: {e} (call took {time.perf_counter() - t:.2f}s)")
    print(f"      control_state {cam.control_state}")
t = time.perf_counter()
try:
    frames.__exit__(None, None, None)
    print(f"stream exit ok in {time.perf_counter() - t:.2f}s")
except Exception as e:
    print(f"stream exit -> {type(e).__name__}: {e} after {time.perf_counter() - t:.2f}s")
t = time.perf_counter()
cam.close()
print(f"cam.close() took {time.perf_counter() - t:.2f}s")
