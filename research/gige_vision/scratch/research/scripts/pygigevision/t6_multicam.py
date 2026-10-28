"""Two fake cameras, two GVSPReceivers (threads) in one Python process."""
import sys, time, socket, struct, os
sys.path.insert(0, "/src")
from pyGigEVision import discover, GVCPClient, GVSPReceiver
from pyGigEVision.standard import REG_SC_DEST_ADDR, REG_SC_HOST_PORT, REG_SC_PACKET_SIZE, SC_PACKET_SIZE_MASK
W, H, FPS, PKT, SECS = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]), 4
cams = sorted(discover(timeout=1.0), key=lambda c: c["serial"]); print("discovered:", [(c["serial"], c["ip"], c["interface_ip"]) for c in cams])
rigs = []
for cam in cams:
    c = GVCPClient(cam["ip"], local_ip=cam["interface_ip"]); c.connect()
    c.write_reg(0x100, W); c.write_reg(0x104, H); c.write_reg(0x128, 17301505); c.write_reg(0x138, int(1e6 / FPS))
    rx = GVSPReceiver(local_ip=cam["interface_ip"], camera_ip=cam["ip"], packet_size=PKT, max_queue=2000)
    rx._sock.setsockopt(socket.SOL_SOCKET, 33, 33554432)  # SO_RCVBUFFORCE test-only
    rx.start()
    c.write_reg(REG_SC_DEST_ADDR, struct.unpack(">I", socket.inet_aton(cam["interface_ip"]))[0]); c.write_reg(REG_SC_HOST_PORT, rx.port)
    c.write_reg(REG_SC_PACKET_SIZE, (c.read_reg(REG_SC_PACKET_SIZE) & ~SC_PACKET_SIZE_MASK) | PKT)
    rigs.append((cam, c, rx))
c0 = os.times(); t0 = time.time()
for _, c, _ in rigs: c.write_reg(0x124, 1)
time.sleep(SECS)
c1 = os.times()
for _, c, _ in rigs: c.write_reg(0x124, 0)
for cam, c, rx in rigs:
    rx.stop(); fr = []
    while (r := rx.get_frame_with_info(timeout=0.01)) is not None: fr.append(r[1])
    comp = sum(i["complete"] for i in fr)
    ts = [i["timestamp"] for i in fr]
    print(f"{cam['serial']}: frames={len(fr)} complete={comp} fps={len(fr)/SECS:.1f} first_ts={ts[0] if ts else None}")
    rx.close(); c.disconnect()
cpu = (c1.user - c0.user) + (c1.system - c0.system)
print(f"{W}x{H}@{FPS} pkt={PKT} x{len(rigs)} cams: process cpu {100*cpu/SECS:.0f}% of one core")
