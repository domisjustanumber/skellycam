"""Send one lossless Mono8 frame of WxH (standard IDs); report whether pyGigEVision delivers it."""
import sys, time, socket, struct
sys.path.insert(0, "/src")
from pyGigEVision import GVSPReceiver
CAM = "127.0.0.1"; PAY = 8964
for W, H in [(2048, 2048), (2448, 2048), (2592, 1944)]:
    rx = GVSPReceiver(local_ip=CAM, camera_ip="", packet_size=9000)  # camera_ip="" disables resends
    rx._sock.setsockopt(socket.SOL_SOCKET, 33, 33554432); rx.start()
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    hdr = lambda bid, fmt, pid: struct.pack(">HHI", 0, bid, (fmt << 24) | pid)
    img = bytes(W * H); npk = -(-len(img) // PAY)
    tx.sendto(hdr(1, 1, 0) + struct.pack(">HHQIIIIIHH", 0, 1, 1, 0x01080001, W, H, 0, 0, 0, 0), (CAM, rx.port))
    for i in range(npk):
        tx.sendto(hdr(1, 3, i + 1) + img[i * PAY:(i + 1) * PAY], (CAM, rx.port))
    tx.sendto(hdr(1, 2, npk + 1) + struct.pack(">HHI", 0, 1, H), (CAM, rx.port))
    r = rx.get_frame_with_info(timeout=1.0)
    print(f"{W}x{H} ({W*H/1e6:.1f} MP): delivered={'yes ' + str(r[0].shape) if r else 'NO (frame silently dropped)'}")
    rx.close()
