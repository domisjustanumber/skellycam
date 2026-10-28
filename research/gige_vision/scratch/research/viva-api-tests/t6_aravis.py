"""viva-genicam against Aravis' arv-fake-gv-camera-0.8 (started separately with `-i lo`)."""
import sys, time
import viva_genicam as vg

print("viva", vg.__version__)
infos = vg.discover(timeout_ms=1000, all=True)
print("discover(all=True):", infos)
info = next(i for i in infos if i.ip == "127.0.0.1")
cam = vg.connect_gige(info)
print("control_state", cam.control_state, "skipped nodes", len(cam.skipped()), cam.skipped()[:3])
names = cam.nodes()
print("n nodes", len(names))
interesting = [n for n in names if any(k in n for k in ("Ptp", "1588", "Timestamp", "Action", "Trigger", "GevSC", "Pixel"))]
print("interesting nodes:", interesting)
for f in ["DeviceVendorName", "DeviceModelName", "DeviceSerialNumber", "DeviceID", "Width", "Height", "PixelFormat",
          "AcquisitionFrameRate", "GevTimestampTickFrequency", "GevSCPSPacketSize", "GevSCPD", "TriggerSource", "PtpEnable", "GevIEEE1588"]:
    try:
        print(f"  {f} = {cam.get(f)!r}")
    except Exception as e:
        print(f"  {f} ERR {type(e).__name__}: {e}")
for en in ("PixelFormat", "TriggerSource", "TriggerSelector"):
    try:
        print(f"  {en} entries {cam.enum_entries(en)} available {cam.available_enum_entries(en)}")
    except Exception as e:
        print(f"  {en} entries ERR {type(e).__name__}: {e}")
u32 = lambda b: int.from_bytes(b, "big")
ver = u32(cam.read_register(0x0000)); cap = u32(cam.read_register(0x0934))
print(f"Version 0x{ver:08x}; capability 0x{cap:08x} 1588={bool(cap & 0x80000)} sched={bool(cap & 0x20000)} action={bool(cap & 0x40)}")
tf = (u32(cam.read_register(0x093C)) << 32) | u32(cam.read_register(0x0940))
print("bootstrap tick freq", tf)

for pf in [p for p in cam.available_enum_entries("PixelFormat")]:
    cam.set_enum("PixelFormat", pf)
    with cam.stream() as frames:
        fr = frames.next_frame(timeout_ms=5000)
        try:
            a = fr.to_numpy(); s = (a.shape, str(a.dtype))
        except Exception as e:
            s = f"to_numpy ERR {type(e).__name__}: {e}"
        try:
            r = fr.to_rgb8().shape
        except Exception as e:
            r = f"to_rgb8 ERR {type(e).__name__}"
        print(f"  PixelFormat {pf}: frame.pixel_format={fr.pixel_format} code=0x{fr.pixel_format_code:08x} to_numpy={s} to_rgb8={r}")
cam.set_enum("PixelFormat", cam.available_enum_entries("PixelFormat")[0])

n = 0; t = time.perf_counter(); bids = []; ts = []
with cam.stream() as frames:
    for fr in frames:
        bids.append(fr.block_id); ts.append(fr.ts_dev); n += 1
        if n >= 100:
            break
    st = frames.stats()
dt = time.perf_counter() - t
print(f"100 frames in {dt:.2f}s ({n / dt:.1f} fps) block ids {bids[0]}..{bids[-1]} ts_dev first {ts[:3]} deltas {[ts[i + 1] - ts[i] for i in range(3)]}")
print("stats:", st)
try:
    cam.time_calibrate()
    with cam.stream() as frames:
        fr = frames.next_frame(timeout_ms=3000)
    print("after time_calibrate: ts_dev", fr.ts_dev, "ts_host", fr.ts_host, "now", time.time())
except Exception as e:
    print("time_calibrate ERR", type(e).__name__, e)
print("send_action to Aravis fake:", vg.send_action(1, 1, 1, destination="127.0.0.1", timeout_ms=300))
cam.close()
