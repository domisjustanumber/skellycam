import socket, struct, sys, time, multiprocessing as mp
SECS = 5.0
def hdr(bid, pid, ptype): return struct.pack(">HHI", 0, bid & 0xFFFF, (ptype << 24) | pid)
def sender(port, w, h, fps):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); dst = ("127.0.0.1", port)
    dsz = 1492; n = -(-w*h // dsz); chunk = bytes(dsz)
    lead = struct.pack(">HHQIIIIIHH", 0, 1, 0, 0x01080001, w, h, 0, 0, 0, 0)
    t0 = time.perf_counter(); bid = 0
    while time.perf_counter() - t0 < SECS + 0.5:
        bid = bid % 65535 + 1
        s.sendto(hdr(bid, 0, 1) + lead, dst)
        for i in range(1, n + 1): s.sendto(hdr(bid, i, 3) + chunk, dst)
        s.sendto(hdr(bid, n + 1, 2) + struct.pack(">HHI", 0, 1, h), dst)
        nxt = t0 + bid / fps
        while time.perf_counter() < nxt: time.sleep(0.0005)
def make_rx():
    from pyGigEVision import GVSPReceiver
    rx = GVSPReceiver(local_ip="127.0.0.1", packet_size=1500, max_queue=1000)
    rx._sock.setsockopt(socket.SOL_SOCKET, 33, 64 << 20); return rx
def drain(rxs):
    for r in rxs: r.start()
    t0 = time.time(); res = [[0, 0] for _ in rxs]
    while time.time() - t0 < SECS:
        for k, r in enumerate(rxs):
            x = r.get_frame_with_info(0.001)
            while x is not None:
                res[k][0] += 1; res[k][1] += x[1]["complete"]; x = r.get_frame_with_info(0)
    return res
def rx_proc(q, portq):
    rx = make_rx(); portq.put(rx.port); c0 = time.process_time(); r = drain([rx]); q.put((r[0], time.process_time() - c0))
if __name__ == "__main__":
    mode, w, h, fps = sys.argv[1], 1920, 1080, 100
    if mode == "one":
        rxs = [make_rx(), make_rx()]
        ps = [mp.Process(target=sender, args=(r.port, w, h, fps)) for r in rxs]
        for p in ps: p.start()
        c0 = time.process_time(); res = drain(rxs); cpu = time.process_time() - c0
        print(f"ONE process, 2 receivers: {[(a/SECS, b/SECS) for a,b in res]} (fps, complete fps); rx-process CPU {100*cpu/SECS:.0f}%")
    else:
        q = mp.Queue(); pq = mp.Queue()
        rps = [mp.Process(target=rx_proc, args=(q, pq)) for _ in range(2)]
        for p in rps: p.start()
        ports = [pq.get(), pq.get()]
        ps = [mp.Process(target=sender, args=(pt, w, h, fps)) for pt in ports]
        for p in ps: p.start()
        out = [q.get(), q.get()]
        print(f"TWO processes: {[(a/SECS, b/SECS, f'{100*c/SECS:.0f}% cpu') for (a,b),c in out]} (fps, complete fps)")
