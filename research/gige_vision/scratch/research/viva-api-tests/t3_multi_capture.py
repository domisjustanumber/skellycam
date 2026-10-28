"""N fakes at once: 100 frames from each in parallel threads, then action commands.

usage: t3_multi_capture.py IP [IP ...]   (one FakeGigeCamera per host IPv4 address)
"""
import sys, threading, time
import numpy as np
import viva_genicam as vg
from viva_genicam.testing import FakeGigeCamera

ips = sys.argv[1:]
fmts = ["Mono8", "BayerRG8", "RGB8", "Mono16"]
fakes = [FakeGigeCamera(width=640, height=480, fps=30, bind_ip=ip, pixel_format=fmts[i % len(fmts)]) for i, ip in enumerate(ips)]
for f in fakes:
    f.start()
infos = vg.discover(timeout_ms=800, all=True)
print("discovered", [i.ip for i in infos])
by_ip = {i.ip: i for i in infos}
cams = {ip: vg.connect_gige(by_ip[ip]) for ip in ips}
for ip, cam in cams.items():
    print(ip, "PixelFormat", cam.get("PixelFormat"), "SensorType", cam.get("SensorType"), "control", cam.control_state)

results = {}
def grab(ip, cam, n=100):
    out = {"block_ids": [], "ts_dev": [], "shapes": set(), "recv": []}
    with cam.stream() as frames:
        for fr in frames:
            out["recv"].append(time.perf_counter())
            out["block_ids"].append(fr.block_id); out["ts_dev"].append(fr.ts_dev)
            out["shapes"].add((fr.pixel_format, fr.to_numpy().shape, str(fr.to_numpy().dtype)))
            if len(out["block_ids"]) >= n:
                break
        out["stats"] = frames.stats()
    results[ip] = out

t0 = time.perf_counter()
threads = [threading.Thread(target=grab, args=(ip, cam)) for ip, cam in cams.items()]
for t in threads: t.start()
for t in threads: t.join(60)
dt = time.perf_counter() - t0
for ip, r in results.items():
    s = r["stats"]
    print(f"{ip}: {len(r['block_ids'])} frames in {dt:.2f}s; first/last block {r['block_ids'][0]}/{r['block_ids'][-1]}; "
          f"shapes {r['shapes']}; complete {s.frames_complete} lost {s.frames_lost} backpressure {s.frames_backpressure} "
          f"avg_fps {s.avg_fps:.1f} resend_req {s.resend_requested}")

# ---- action commands ----
K = (FakeGigeCamera.DEVICE_KEY, FakeGigeCamera.GROUP_KEY, FakeGigeCamera.GROUP_MASK)
print("fake action keys device=0x%x group=0x%x mask=0x%x" % K)
for dest in ["255.255.255.255"] + ips:
    before = [f.actions() for f in fakes]
    try:
        r = vg.send_action(*K, destination=dest, timeout_ms=300)
    except Exception as e:
        r = f"ERR {type(e).__name__}: {e}"
    after = [f.actions() for f in fakes]
    print(f"send_action(dest={dest}) -> {r}; fake.actions() deltas {[a-b for a, b in zip(after, before)]}")
# scheduled: 50 ms in the future in the fakes' 1 GHz tick clock (fake does not check the time)
cam0 = cams[ips[0]]
cam0.execute("TimestampLatch"); now_ticks = cam0.get_integer("GevTimestampValue")
print("latched device ticks", now_ticks)
for dest in ips:
    r = vg.send_action(*K, scheduled_time=now_ticks + 50_000_000, destination=dest, timeout_ms=300)
    print(f"scheduled send_action(dest={dest}) -> {r}")
r = vg.send_action(0x1, 0x1, 0x1, destination=ips[0], timeout_ms=300)
print("wrong device key ->", r)
print("fake actions totals", [f.actions() for f in fakes])
try:
    vg.send_action(*K, destination="not-an-ip")
except Exception as e:
    print("bad destination ->", type(e).__name__, e)
for c in cams.values(): c.close()
for f in fakes: f.stop()
