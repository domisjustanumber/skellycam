"""GEV 2.x extended-ID (64-bit block_id) packets with one dropped data packet; block_id > 0xFFFF."""
import sys, time, socket, struct
sys.path.insert(0, "/src")
from pyGigEVision import GVSPReceiver
CAM = "127.0.0.1"; W, H, PAY = 64, 64, 1024
rx = GVSPReceiver(local_ip=CAM, camera_ip=CAM, packet_size=PAY + 20)
rx.start()
tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
def hdr(bid, fmt, pid):  # status, flags, EI|format, reserved, block_id64, packet_id32
    return struct.pack(">HHBBHQI", 0, 0, 0x80 | fmt, 0, 0, bid, pid)
img = bytes(W * H); npk = -(-len(img) // PAY)
for bid, drop in [(5, None), (70000, None), (70001, 2)]:
    tx.sendto(hdr(bid, 1, 0) + struct.pack(">HHQIIIIIHH", 0, 1, 123, 0x01080001, W, H, 0, 0, 0, 0), (CAM, rx.port))
    for i in range(npk):
        if i + 1 == drop: continue
        tx.sendto(hdr(bid, 3, i + 1) + img[i * PAY:(i + 1) * PAY], (CAM, rx.port))
    time.sleep(0.15)  # let gap check run (> initial_packet_timeout)
    tx.sendto(hdr(bid, 2, npk + 1) + struct.pack(">HHI", 0, 1, H), (CAM, rx.port))
    time.sleep(0.1)
    r = rx.get_frame_with_info(timeout=0.5)
    print(f"block_id={bid} drop={drop} -> frame={'yes' if r else 'NO'} info={r[1] if r else None} receiver_thread_alive={rx._thread.is_alive()}")
