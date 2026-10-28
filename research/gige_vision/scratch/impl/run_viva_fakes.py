"""Test helper (not shipped): run N viva-genicam FakeGigeCameras on 127.0.0.1..127.0.0.N for --seconds."""
import argparse, sys, time
from viva_genicam.testing import FakeGigeCamera
ap = argparse.ArgumentParser()
ap.add_argument("-n", type=int, default=1)
ap.add_argument("--seconds", type=float, default=60)
ap.add_argument("--pixel-format", default="BayerRG8")
ap.add_argument("--width", type=int, default=640)
ap.add_argument("--height", type=int, default=480)
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--base", default="127.0.0.")
ap.add_argument("--drop", default="", help="block:packet,block:packet")
ap.add_argument("--ips", default="", help="comma list of bind IPs (overrides -n/--base)")
a = ap.parse_args()
drop = [tuple(int(x) for x in d.split(":")) for d in a.drop.split(",") if d] or None
fakes = []
ips = a.ips.split(",") if a.ips else [f"{a.base}{i + 1}" for i in range(a.n)]
for ip in ips:
    f = FakeGigeCamera(width=a.width, height=a.height, fps=a.fps, bind_ip=ip, pixel_format=a.pixel_format, drop_packets=drop)
    f.start(); fakes.append(f)
    print("fake up", f.ip, f.port, flush=True)
print("READY", flush=True)
try:
    time.sleep(a.seconds)
finally:
    for f in fakes:
        print("fake", f.ip, "actions", f.actions(), "blocks_sent", f.blocks_sent(), "writes", f.writes(), flush=True)
        f.stop()
