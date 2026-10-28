"""Lossless GVSP sender paced at ~RATE bytes/s; count PACKETRESEND requests the pyGigEVision receiver emits.
No packets are dropped by the sender, so every resend request is spurious."""
import sys, time, socket, struct, threading
sys.path.insert(0, "/src")
from pyGigEVision import GVSPReceiver
W, H, NFRAMES, RATE, PAY = 1920, 1080, 20, float(sys.argv[1]) if len(sys.argv) > 1 else 110e6, 1464
CAM = "127.0.0.1"
gvcp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); gvcp.bind((CAM, 3956)); gvcp.settimeout(0.2)
req = {"n_cmds": 0, "n_pkts": 0}; stop = threading.Event()
def listen():
    while not stop.is_set():
        try: d, _ = gvcp.recvfrom(2048)
        except OSError: continue
        if len(d) >= 20 and struct.unpack(">H", d[2:4])[0] == 0x0040:
            _, _, first, last = struct.unpack(">HHII", d[8:20]); req["n_cmds"] += 1; req["n_pkts"] += last - first + 1
threading.Thread(target=listen, daemon=True).start()
rx = GVSPReceiver(local_ip=CAM, camera_ip=CAM, packet_size=1500, max_queue=100)
rx._sock.setsockopt(socket.SOL_SOCKET, 33, 33554432)  # SO_RCVBUFFORCE: rule out kernel drops
rx.start()
tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
img = bytes(range(256)) * (W * H // 256 + 1); img = img[:W * H]
npk = -(-len(img) // PAY)
def hdr(bid, fmt, pid): return struct.pack(">HHI", 0, bid, (fmt << 24) | pid)
t_frame = time.perf_counter()
for bid in range(1, NFRAMES + 1):
    t0 = time.perf_counter(); sent = 0
    leader = struct.pack(">HHQIIIIIHH", 0, 1, int(time.time_ns()), 0x01080001, W, H, 0, 0, 0, 0)
    tx.sendto(hdr(bid, 1, 0) + leader, (CAM, rx.port))
    for i in range(npk):
        chunk = img[i * PAY:(i + 1) * PAY]
        tx.sendto(hdr(bid, 3, i + 1) + chunk, (CAM, rx.port)); sent += len(chunk) + 36
        while time.perf_counter() - t0 < sent / RATE: pass   # pace to RATE bytes/s
    tx.sendto(hdr(bid, 2, npk + 1) + struct.pack(">HHI", 0, 1, H), (CAM, rx.port))
    t_frame += 1 / 30
    while time.perf_counter() < t_frame: time.sleep(0.001)
time.sleep(0.5); rx.stop(); stop.set()
frames = []
while (r := rx.get_frame_with_info(timeout=0.01)) is not None: frames.append(r[1])
print(f"rate={RATE/1e6:.0f}MB/s frame_tx_time~{len(img)/RATE*1000:.1f}ms packets/frame={npk} frames_sent={NFRAMES} received={len(frames)} complete={sum(f['complete'] for f in frames)}")
print(f"spurious PACKETRESEND commands={req['n_cmds']} packets_requested={req['n_pkts']} ({req['n_pkts']/(npk*NFRAMES)*100:.1f}% of all packets sent); receiver stats={rx._resend_stats}")
