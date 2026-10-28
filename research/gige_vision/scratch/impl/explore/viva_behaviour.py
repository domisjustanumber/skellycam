import threading, time
import viva_genicam as vg
from viva_genicam.testing import FakeGigeCamera
fakes = [FakeGigeCamera(width=320, height=240, fps=30, bind_ip=f"127.0.0.{i+1}") for i in range(1)]
for f in fakes: f.start()
infos = [f.device_info() for f in fakes]
print("infos", infos)
print("discover all", vg.discover(timeout_ms=800, all=True))
cams = [vg.connect_gige(i) for i in infos]
c = cams[0]
for name in ("NoSuchFeature",):
    try: c.get(name)
    except Exception as e: print("missing ->", type(e).__name__, e)
try: c.set_enum("TriggerSource", "Action1")
except Exception as e: print("set_enum bad ->", type(e).__name__, e)
print("version reg", c.read_register(0x0000, 4).hex())
print("TriggerMode", c.get("TriggerMode"), "AcqFR", c.get("AcquisitionFrameRate"))
c.set("AcquisitionFrameRate", "15"); print("AcqFR now", c.get("AcquisitionFrameRate"))
try: c.execute("TimestampLatch"); print("latched GevTimestampValue", c.get("GevTimestampValue"))
except Exception as e: print("latch err", type(e).__name__, e)
for to in (5, 50, 200):
    t0 = time.perf_counter(); r = vg.send_action(0x42, 1, 1, destination="127.0.0.1", timeout_ms=to); print("send_action timeout", to, "->", r, f"{(time.perf_counter()-t0)*1e3:.1f} ms")
t0 = time.perf_counter(); r = vg.send_action(0x42, 1, 1, scheduled_time=123, destination="127.0.0.255", timeout_ms=50); print("bcast 127.0.0.255", r, f"{(time.perf_counter()-t0)*1e3:.1f} ms")
streams = [cm.stream(deliver_incomplete=True) for cm in cams]
res = {}
def rd(i, st):
    with st as frames:
        out = []
        t_end = time.time() + 2
        while time.time() < t_end:
            fr = frames.next_frame(timeout_ms=500)
            if fr is None: break
            out.append((fr.block_id, fr.ts_dev, fr.status.value))
        res[i] = (out[:3], len(out), frames.stats())
ths = [threading.Thread(target=rd, args=(i, st)) for i, st in enumerate(streams)]
for t in ths: t.start()
for t in ths: t.join()
for i, (first, n, stats) in res.items(): print("cam", i, "n", n, first, "lost", stats.frames_lost, "fps", round(stats.avg_fps, 1))
try:
    with cams[0].stream() as fr:
        x = fr.next_frame(timeout_ms=10)
        print("short timeout ->", x)
except Exception as e: print("next_frame timeout raises", type(e).__name__, e)
for cm in cams: cm.close()
for f in fakes: print("actions", f.actions()); f.stop()
