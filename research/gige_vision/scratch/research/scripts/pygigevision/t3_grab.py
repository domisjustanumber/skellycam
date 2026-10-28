"""Grab frames from aravis fake GV camera using pyGigEVision only (registers hand-mapped from its XML)."""
import sys, time, socket, struct, argparse, logging
sys.path.insert(0, "/src")
import numpy as np
from pyGigEVision import discover, GVCPClient, GVSPReceiver
from pyGigEVision.standard import REG_SC_DEST_ADDR, REG_SC_HOST_PORT, REG_SC_PACKET_SIZE, SC_PACKET_SIZE_MASK, REG_CCP, REG_HEARTBEAT_TIMEOUT
logging.basicConfig(level=logging.WARNING)
# Fake camera registers (from its GenICam XML, see fake_camera.xml)
REG_WIDTH, REG_HEIGHT, REG_PIXFMT, REG_ACQ_CMD, REG_FRAME_PERIOD_US = 0x100, 0x104, 0x128, 0x124, 0x138
PIXFMT = {"Mono8": 17301505, "Mono16": 17825799, "BayerRG8": 17301513, "RGB8": 35127316}
# GigE Vision bootstrap timestamp regs (offsets from aravis arvgvcpprivate.h; not defined in pyGigEVision)
REG_TICK_HI, REG_TICK_LO = 0x093C, 0x0940
ap = argparse.ArgumentParser()
ap.add_argument("--fmt", default="Mono8"); ap.add_argument("--w", type=int, default=640); ap.add_argument("--h", type=int, default=480)
ap.add_argument("--fps", type=float, default=30); ap.add_argument("--secs", type=float, default=3); ap.add_argument("--pkt", type=int, default=1500); ap.add_argument("--force-rcvbuf", type=int, default=0); ap.add_argument("--serial", default=""); ap.add_argument("--ip", default="")
a = ap.parse_args()
cams = discover(timeout=1.0) if not a.ip else [{"ip": a.ip, "interface_ip": a.ip, "serial": "explicit"}]
print("discovered:", [(c["serial"], c["ip"]) for c in cams])
cam = next(c for c in cams if (not a.serial or c["serial"] == a.serial))
print("using", cam["serial"], cam["ip"])
ip = cam["ip"]
c = GVCPClient(ip); c.connect(); c.write_reg(REG_HEARTBEAT_TIMEOUT, 3000)
try:
    tick = (c.read_reg(REG_TICK_HI) << 32) | c.read_reg(REG_TICK_LO)
except Exception as e:
    tick = f"ERR {e}"
print("tick_frequency register:", tick)
c.write_reg(REG_WIDTH, a.w); c.write_reg(REG_HEIGHT, a.h); c.write_reg(REG_PIXFMT, PIXFMT[a.fmt])
c.write_reg(REG_FRAME_PERIOD_US, int(1e6 / a.fps))
print("readback w,h,fmt,period_us:", c.read_reg(REG_WIDTH), c.read_reg(REG_HEIGHT), hex(c.read_reg(REG_PIXFMT)), c.read_reg(REG_FRAME_PERIOD_US))
rx = GVSPReceiver(local_ip=cam["interface_ip"], camera_ip=ip, packet_size=a.pkt, max_queue=1000)
if a.force_rcvbuf:
    rx._sock.setsockopt(socket.SOL_SOCKET, 33, a.force_rcvbuf)  # SO_RCVBUFFORCE (Linux, needs CAP_NET_ADMIN) - TEST-ONLY PATCH
print("receiver SO_RCVBUF effective:", rx._sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF))
rx.start()
c.write_reg(REG_SC_DEST_ADDR, struct.unpack(">I", socket.inet_aton(cam["interface_ip"]))[0])
c.write_reg(REG_SC_HOST_PORT, rx.port)
c.write_reg(REG_SC_PACKET_SIZE, (c.read_reg(REG_SC_PACKET_SIZE) & ~SC_PACKET_SIZE_MASK) | (a.pkt & SC_PACKET_SIZE_MASK))
import os
cpu0 = os.times(); t0 = time.time(); c.write_reg(REG_ACQ_CMD, 1)
frames = []
while time.time() - t0 < a.secs:
    r = rx.get_frame_with_info(timeout=1.0)
    if r: frames.append((time.time(), r[0], r[1]))
cpu1 = os.times(); c.write_reg(REG_ACQ_CMD, 0)
rx.stop(); rx.close(); c.disconnect()
n = len(frames); comp = sum(f[2]["complete"] for f in frames)
cpu = (cpu1.user - cpu0.user) + (cpu1.system - cpu0.system)
print(f"PYGEV cpu_seconds={cpu:.2f} over {a.secs}s wall -> {100*cpu/a.secs:.0f}% of one core; MB/s complete={comp*a.w*a.h*{'Mono8':1,'Mono16':2,'BayerRG8':1,'RGB8':3}[a.fmt]/a.secs/1e6:.1f}")
print(f"fmt={a.fmt} {a.w}x{a.h} req_fps={a.fps} frames={n} complete={comp} achieved_fps={n/a.secs:.1f} resend_stats={rx._resend_stats}")
if frames:
    f0 = frames[0]; arr, info = f0[1], f0[2]
    print("first frame: shape", arr.shape, "dtype", arr.dtype, "nbytes", arr.nbytes, "info", info)
    print("expected bytes for fmt:", {"Mono8":1,"Mono16":2,"BayerRG8":1,"RGB8":3}[a.fmt]*a.w*a.h)
    print("pixel stats min/max/mean:", arr.min(), arr.max(), float(arr.mean()))
    ts = np.array([f[2]["timestamp"] for f in frames], dtype=np.int64)
    if len(ts) > 2:
        d = np.diff(ts)
        print("leader timestamp first:", ts[0], " host time.time_ns at receive:", int(frames[0][0]*1e9), " diffs (ticks) median/min/max:", int(np.median(d)), d.min(), d.max())
    bids = [f[2]["block_id"] for f in frames]; print("block_ids first..last:", bids[:5], "...", bids[-3:])
    missing = [f[2]["missing_packets"] for f in frames]; print("missing_packets max:", max(missing))
