"""Verify pyGigEVision against arv-fake-gv-camera-0.8: XML url parse, SO_RCVBUF, pixel formats."""
import argparse, socket, struct, time, sys
import pyGigEVision
from pyGigEVision import discover, GVCPClient, GVSPReceiver
from pyGigEVision.genicam import parse_first_url, fetch_genicam_xml
FMT = {"Mono8": 0x01080001, "Mono16": 0x01100007, "BayerRG8": 0x01080009, "RGB8": 0x02180014}
ap = argparse.ArgumentParser()
ap.add_argument("--fmt", default="Mono8"); ap.add_argument("--w", type=int, default=640)
ap.add_argument("--h", type=int, default=480); ap.add_argument("--fps", type=float, default=30)
ap.add_argument("--force", type=int, default=0); ap.add_argument("--secs", type=float, default=3)
a = ap.parse_args()
cams = discover(timeout=1.0)
print("discovered:", [(c.get("ip"), c.get("model")) for c in cams])
ip = cams[0]["ip"]
c = GVCPClient(ip); c.connect()
raw = c.read_mem(0x200, 512)
print("FIRST_URL:", raw.split(b"\0")[0], "-> parse_first_url:", parse_first_url(raw))
xml, fn = fetch_genicam_xml(c)
print(f"fetch_genicam_xml: {len(xml)} bytes, nonzero={sum(1 for b in xml if b)}, head={xml[:20]!r}")
fn2, addr, size = parse_first_url(raw)
xml2 = c.read_mem(int("10000", 16), size)
print(f"manual hex read: head={xml2[:40]!r}")
tf = (c.read_reg(0x093C) << 32) | c.read_reg(0x0940)
print("tick freq (0x093C/0x0940):", tf)
rx = GVSPReceiver(local_ip="", camera_ip=ip, packet_size=1500)
print("SO_RCVBUF after lib init:", rx._sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF))
if a.force:
    rx._sock.setsockopt(socket.SOL_SOCKET, 33, a.force)  # SO_RCVBUFFORCE
    print("SO_RCVBUF after FORCE:", rx._sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF))
rx.start()
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect((ip, 3956)); lip = s.getsockname()[0]; s.close()
c.write_reg(0x100, a.w); c.write_reg(0x104, a.h); c.write_reg(0x128, FMT[a.fmt])
c.write_reg(0x138, int(1e6 / a.fps))
c.write_reg(0xD18, struct.unpack(">I", socket.inet_aton(lip))[0]); c.write_reg(0xD00, rx.port)
c.write_reg(0xD04, 1500)
c.write_reg(0x124, 1)
t0 = time.time(); n = comp = 0; ts = []; shapes = set()
while time.time() - t0 < a.secs:
    r = rx.get_frame_with_info(timeout=0.5)
    if r is None: continue
    f, info = r; n += 1; comp += info["complete"]; ts.append(info["timestamp"]); shapes.add((f.shape, str(f.dtype), f.nbytes))
c.write_reg(0x124, 0)
rx.stop()
d = [b - a_ for a_, b in zip(ts, ts[1:])]
print(f"fmt={a.fmt} {a.w}x{a.h}@{a.fps}: frames={n} complete={comp} shapes={shapes} expected_bytes={a.w*a.h*(3 if a.fmt=='RGB8' else 2 if a.fmt=='Mono16' else 1)}")
print("timestamp deltas (first 3):", d[:3], "resend_stats:", rx._resend_stats)
c.disconnect()
