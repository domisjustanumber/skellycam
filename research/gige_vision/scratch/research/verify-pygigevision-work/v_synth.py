"""Synthetic GVSP sender tests for pyGigEVision (loopback, no camera)."""
import socket, struct, sys, time, threading, logging
logging.basicConfig(level=logging.ERROR)
from pyGigEVision import GVSPReceiver

def leader(bid, w, h, pf, ext):
    pl = struct.pack(">HHQIIIIIHH", 0, 0x0001, 123456789, pf, w, h, 0, 0, 0, 0)
    return hdr(bid, 0, 1, ext) + pl
def trailer(bid, pid, h, ext):
    return hdr(bid, pid, 2, ext) + struct.pack(">HHI", 0, 0x0001, h)
def data(bid, pid, ext, payload):
    return hdr(bid, pid, 3, ext) + payload
def hdr(bid, pid, ptype, ext):
    if ext:
        return struct.pack(">HHIQI", 0, 0, (0x80 | ptype) << 24, bid, pid)
    return struct.pack(">HHI", 0, bid & 0xFFFF, (ptype << 24) | pid)

def send_frame(s, dst, bid, w, h, pf, bpp, psize, ext, drop=(), pace_bps=None):
    hsz = 20 if ext else 8
    dsz = psize - hsz
    img = bytes(w * h * bpp)
    n = -(-len(img) // dsz)
    s.sendto(leader(bid, w, h, pf, ext), dst)
    t0 = time.perf_counter(); sent = 0
    for i in range(n):
        if i + 1 not in drop:
            s.sendto(data(bid, i + 1, ext, img[i*dsz:(i+1)*dsz]), dst)
        sent += psize
        if pace_bps:
            while time.perf_counter() - t0 < sent / pace_bps: pass
    s.sendto(trailer(bid, n + 1, h, ext), dst)
    return n

test = sys.argv[1]
if test == "ext":
    # extended-ID stream with block_id > 65535 and a dropped packet
    rx = GVSPReceiver(local_ip="127.0.0.1", camera_ip="127.0.0.1", packet_size=1500)
    rx.start()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); dst = ("127.0.0.1", rx.port)
    # first: ext frame, block 70000 lossless
    send_frame(s, dst, 70000, 320, 240, 0x01080001, 1, 1500, True)
    r = rx.get_frame_with_info(1.0); print("lossless ext block 70000 ->", None if r is None else r[1])
    send_frame(s, dst, 70001, 320, 240, 0x01080001, 1, 1500, True, drop={5})
    time.sleep(0.5)
    print("after gap in block 70001: receiver_thread_alive =", rx._thread.is_alive())
    send_frame(s, dst, 70002, 320, 240, 0x01080001, 1, 1500, True)
    print("next frame:", rx.get_frame_with_info(1.0))
elif test == "ext_small":
    # extended IDs, block_id <= 65535, one drop: capture the PACKETRESEND bytes
    lst = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); lst.bind(("127.0.0.2", 3956)); lst.settimeout(1)
    rx = GVSPReceiver(local_ip="127.0.0.1", camera_ip="127.0.0.2", packet_size=1500); rx.start()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); dst = ("127.0.0.1", rx.port)
    bid = 7
    hsz=20; dsz=1480; img_n = -(-320*240 // dsz)
    s.sendto(leader(bid, 320, 240, 0x01080001, True), dst)
    for i in range(img_n):
        if i + 1 != 5: s.sendto(data(bid, i+1, True, bytes(dsz)), dst)
    time.sleep(0.1)  # no trailer yet -> socket timeout -> gap check
    try:
        pkt, _ = lst.recvfrom(100); print("PACKETRESEND bytes:", pkt.hex(), "len", len(pkt), "flag byte=0x%02x" % pkt[1])
    except socket.timeout: print("no resend seen")
elif test == "big":
    rx = GVSPReceiver(local_ip="127.0.0.1", packet_size=9000)
    rx._sock.setsockopt(socket.SOL_SOCKET, 33, 64 << 20)
    rx.start()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); dst = ("127.0.0.1", rx.port)
    for bid, (w, h) in enumerate([(2048, 2048), (2048, 2049), (2448, 2048), (2592, 1944)], start=1):
        send_frame(s, dst, bid, w, h, 0x01080001, 1, 9000, False, pace_bps=500e6)
        r = rx.get_frame_with_info(1.0)
        print(f"{w}x{h} ({w*h} px):", "NO FRAME" if r is None else (r[0].shape, r[1]["complete"]))
elif test == "paced":
    rate = float(sys.argv[2])
    lst = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); lst.bind(("127.0.0.2", 3956)); lst.settimeout(0.05)
    cnt = {"req": 0, "cmds": 0}
    stop = threading.Event()
    def listen():
        while not stop.is_set():
            try: p, _ = lst.recvfrom(100)
            except socket.timeout: continue
            if len(p) >= 20 and struct.unpack(">H", p[2:4])[0] == 0x40:
                f, l = struct.unpack(">II", p[12:20]); cnt["req"] += l - f + 1; cnt["cmds"] += 1
    threading.Thread(target=listen, daemon=True).start()
    rx = GVSPReceiver(local_ip="127.0.0.1", camera_ip="127.0.0.2", packet_size=1500)
    rx._sock.setsockopt(socket.SOL_SOCKET, 33, 64 << 20)
    rx.start()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); dst = ("127.0.0.1", rx.port)
    tot = 0; comp = 0; N = 20
    for bid in range(1, N + 1):
        tot += send_frame(s, dst, bid, 1920, 1080, 0x01080001, 1, 1500, False, pace_bps=rate)
        r = rx.get_frame_with_info(1.0); comp += bool(r and r[1]["complete"])
    time.sleep(0.3); stop.set()
    print(f"rate={rate/1e6:.0f}MB/s frames={N} complete={comp} data_pkts_sent={tot} (none dropped) "
          f"resend_pkts_requested_on_wire={cnt['req']} ({100*cnt['req']/tot:.1f}%) cmds={cnt['cmds']} lib_stats={rx._resend_stats}")
