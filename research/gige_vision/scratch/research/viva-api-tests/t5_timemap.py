"""Why is Frame.ts_host constant? Inspect the fake's timestamp latch and map_dev_ts."""
import time
import viva_genicam as vg
from viva_genicam.testing import FakeGigeCamera

with FakeGigeCamera(width=320, height=240, fps=30) as fake:
    cam = vg.connect_gige(fake.device_info())
    vals = []
    for _ in range(5):
        cam.execute("TimestampLatch")
        cam.invalidate("GevTimestampValue")
        vals.append((cam.get_integer("GevTimestampValue"), time.time()))
        time.sleep(0.05)
    print("latched GevTimestampValue (ticks, host time):", vals)
    print("fake register peek 0x20068:", fake.peek(0x20068, 8).hex())
    cam.time_calibrate(samples=8, interval_ms=20)
    for t in (0, 10**9, 10**10, vals[-1][0], vals[-1][0] + 10**9):
        print(f"map_dev_ts({t}) = {cam.map_dev_ts(t)}")
    with cam.stream() as frames:
        for _ in range(3):
            fr = frames.next_frame(timeout_ms=3000)
            cam.execute("TimestampLatch"); cam.invalidate("GevTimestampValue")
            print(f"frame ts_dev {fr.ts_dev}  ts_host {fr.ts_host}  latched-now {cam.get_integer('GevTimestampValue')}  host now {time.time():.6f}")
    cam.close()
