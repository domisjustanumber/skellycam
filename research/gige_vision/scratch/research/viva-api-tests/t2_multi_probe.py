"""Which bind addresses let several FakeGigeCameras run and be discovered at once?"""
import sys, time
import viva_genicam as vg
from viva_genicam.testing import FakeGigeCamera

ips = sys.argv[1:] or ["127.0.0.1", "127.0.0.2", "127.0.0.3"]
fakes = []
for ip in ips:
    f = FakeGigeCamera(width=320, height=240, fps=30, bind_ip=ip)
    try:
        f.start(); fakes.append(f); print("started", f)
    except Exception as e:
        print("start", ip, "ERR", type(e).__name__, e)
for kw in ({"all": True}, {}):
    print("discover", kw, vg.discover(timeout_ms=600, **kw))
for ip in ips:
    try:
        print("discover iface", ip, vg.discover(timeout_ms=400, iface=ip))
    except Exception as e:
        print("discover iface", ip, "ERR", type(e).__name__, e)
for f in fakes:
    try:
        print("device_info", f.ip, f.device_info(timeout_ms=800))
    except Exception as e:
        print("device_info", f.ip, "ERR", type(e).__name__, e)
for f in fakes:
    f.stop()
