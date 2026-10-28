#!/usr/bin/env python3
"""
udp_multicam_threads_benchmark.py -- N simulated GigE cameras (one paced sender
*process* each, ~1 Gbit/s by default) streaming into ONE Python process that runs
N receiver *threads* (one socket per camera), i.e. what a pure-Python multi-camera
GVSP client inside SkellyCam would look like. Measures whether the GIL lets one
process keep up. Stdlib only; self-contained.

  python -I udp_multicam_threads_benchmark.py --cams 1,2,4 --sizes 1472,8972
  (Linux, to exceed net.core.rmem_max without sysctl: --force-rcvbuf, needs CAP_NET_ADMIN)
"""
import argparse
import multiprocessing as mp
import os
import platform
import socket
import struct
import sys
import threading
import time

HDR = struct.Struct(">HHI")
END_MAGIC = 0xFFFF


# sender() copied verbatim from udp_recv_benchmark.py so spawned children can import it under -I
def sender(host, port, result_q, size, rate_mbps, seconds, sender_idx=0, send_end=True):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
    except OSError:
        pass
    dst = (host, port)
    buf = bytearray(size)
    pack_into = HDR.pack_into
    send = sock.sendto
    batch = 16
    pps = (rate_mbps * 1e6 / 8 / size) if rate_mbps > 0 else 0.0
    batch_dt = batch / pps if pps else 0.0
    sent = 0
    errors = 0
    seq = 0
    t0 = time.perf_counter()
    t_end = t0 + seconds
    next_t = t0
    while True:
        now = time.perf_counter()
        if now >= t_end:
            break
        if batch_dt:
            while now < next_t:          # busy-wait pacing (sleep() is too coarse)
                now = time.perf_counter()
            next_t += batch_dt
        for _ in range(batch):
            pid = seq & 0xFFFFFF
            block = ((sender_idx << 12) | (seq >> 24)) & 0xFFFF
            pack_into(buf, 0, 0, block, (0x03 << 24) | pid)  # 0x03 = GVSP payload packet
            try:
                send(buf, dst)
                sent += 1
            except OSError:
                errors += 1
            seq += 1
    t1 = time.perf_counter()
    if send_end:
        time.sleep(0.3)
        end = bytearray(8)
        HDR.pack_into(end, 0, END_MAGIC, 0, 0)
        for _ in range(50):
            try:
                send(end, dst)
            except OSError:
                pass
            time.sleep(0.002)
    sock.close()
    result_q.put(dict(sent=sent, send_errors=errors, send_seconds=t1 - t0))




def rx_thread(sock, size, out, idx):
    payload = size - 8
    frame = bytearray(payload * 256)
    fmv = memoryview(frame)
    scratch = bytearray(65536)
    smv = memoryview(scratch)
    n = 0
    sock.settimeout(2.0)
    while True:
        try:
            k = sock.recv_into(scratch)
        except socket.timeout:
            break
        status, block, fmt_pid = HDR.unpack_from(scratch, 0)
        if status == 0xFFFF:
            break
        off = ((fmt_pid & 0xFFFFFF) % 256) * payload
        fmv[off:off + k - 8] = smv[8:k]
        n += 1
    out[idx] = n


def run(n_cams, size, rate, seconds, rcvbuf, force):
    socks = []
    for _ in range(n_cams):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        opt = getattr(socket, "SO_RCVBUFFORCE", 33) if force else socket.SO_RCVBUF
        try:
            s.setsockopt(socket.SOL_SOCKET, opt, rcvbuf)
        except OSError:
            pass
        s.bind(("127.0.0.1", 0))
        socks.append(s)
    actual = socks[0].getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
    out = [0] * n_cams
    threads = [threading.Thread(target=rx_thread, args=(s, size, out, i)) for i, s in enumerate(socks)]
    for t in threads:
        t.start()
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    c0 = time.process_time()
    w0 = time.perf_counter()
    procs = [ctx.Process(target=sender, args=("127.0.0.1", s.getsockname()[1], q, size, rate, seconds, i, True))
             for i, s in enumerate(socks)]
    for p in procs:
        p.start()
    res = [q.get(timeout=seconds + 30) for _ in procs]
    for p in procs:
        p.join()
    for t in threads:
        t.join()
    cpu = (time.process_time() - c0) / (time.perf_counter() - w0)
    for s in socks:
        s.close()
    sent = sum(r["sent"] for r in res)
    recv = sum(out)
    return dict(cams=n_cams, size=size, sent=sent, recv=recv, drop_pct=round(100 * (1 - recv / sent), 3),
                agg_kpps=round(sent / seconds / 1e3, 1), proc_cpu_cores=round(cpu, 2), rcvbuf=actual)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cams", default="1,2,4")
    ap.add_argument("--sizes", default="1472,8972")
    ap.add_argument("--rate", type=float, default=1000, help="Mbit/s per camera")
    ap.add_argument("--seconds", type=float, default=3)
    ap.add_argument("--rcvbuf", type=int, default=16 << 20)
    ap.add_argument("--force-rcvbuf", action="store_true")
    a = ap.parse_args()
    gil = getattr(sys, "_is_gil_enabled", lambda: True)()
    print(f"python {sys.version.split()[0]} GIL={'on' if gil else 'off'} | {platform.platform()} | cpus={os.cpu_count()}")
    print(f"{'cams':>4} {'size':>5} | {'sent':>9} {'recv':>9} {'drop%':>7} | {'agg kpps':>8} {'cpu cores':>9} | rcvbuf")
    for size in [int(x) for x in a.sizes.split(",")]:
        for n in [int(x) for x in a.cams.split(",")]:
            r = run(n, size, a.rate, a.seconds, a.rcvbuf, a.force_rcvbuf)
            print(f"{r['cams']:>4} {r['size']:>5} | {r['sent']:>9,} {r['recv']:>9,} {r['drop_pct']:>7.2f} | "
                  f"{r['agg_kpps']:>8} {r['proc_cpu_cores']:>9} | {r['rcvbuf']}", flush=True)


if __name__ == "__main__":
    main()
