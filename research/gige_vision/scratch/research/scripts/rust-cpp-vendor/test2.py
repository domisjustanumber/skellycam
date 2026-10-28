import traceback
import viva_genicam as vg
cams = vg.discover(timeout_ms=800)
cam = vg.connect_gige(cams[0])
with cam.stream() as frames:
    for fr in frames:
        print("viva Frame attrs:", [a for a in dir(fr) if not a.startswith("_")])
        for a in ("timestamp", "ts_dev", "ts_host", "block_id", "frame_id", "pixel_format"):
            if hasattr(fr, a):
                v = getattr(fr, a); print("  ", a, "=", v() if callable(v) else v)
        break
print("send_action doc:", vg.send_action.__doc__)
try:
    print("send_action ->", vg.send_action(1, 1, 0xFFFFFFFF, destination="127.0.0.1", timeout_ms=300))
except Exception:
    traceback.print_exc()
try:
    import viva_genicam.testing as t
    print("testing module:", [n for n in dir(t) if not n.startswith("_")])
except Exception as e:
    print("no testing module", e)
import telegenic
cam = telegenic.Camera("127.0.0.1"); cam.connect()
print("tele Camera attrs:", [a for a in dir(cam) if not a.startswith("_")])
fr = cam.snap(timeout=5.0)
print("tele Frame attrs:", [a for a in dir(fr) if not a.startswith("_")])
print("tele frame:", fr.width, fr.height, fr.pixel_format, len(fr.data()))
for a in ("timestamp", "block_id"):
    if hasattr(fr, a):
        v = getattr(fr, a); print("  ", a, "=", v() if callable(v) else v)
