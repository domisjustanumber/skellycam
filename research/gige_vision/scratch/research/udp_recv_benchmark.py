#!/usr/bin/env python3
"""
udp_recv_benchmark.py -- can a pure-Python UDP receive loop keep up with a
GigE Vision (GVSP) stream?

Stand-alone, stdlib only (Python >= 3.9). Runs a paced UDP *sender* process and
a *receiver* process over loopback (or any address you give it) and reports the
achieved receive throughput and drop rate for GVSP-like datagrams.

GVSP-like framing: every datagram starts with an 8-byte header
    status:u16 | block_id:u16 | packet_format:u8 | packet_id:u24
(the "standard id" layout of the GigE Vision streaming protocol); the receiver
parses it with struct.unpack_from and copies the payload into a pre-allocated
per-frame bytearray at offset packet_id * payload_size, i.e. it does the minimum
work a real GVSP reassembler has to do.

Datagram sizes default to the UDP payload sizes for MTU 1500 and MTU 9000:
    1500 - 20 (IPv4) - 8 (UDP) = 1472 bytes
    9000 - 20 - 8              = 8972 bytes

Receiver strategies:
    recvfrom  : data, addr = sock.recvfrom(N)       -> new bytes object per packet
    recv_into : n = sock.recv_into(scratch)          -> one copy into frame buffer

Usage examples:
    python -I udp_recv_benchmark.py                          # default matrix
    python -I udp_recv_benchmark.py --rates 1000 --sizes 1472 --seconds 5
    python -I udp_recv_benchmark.py --rates 1000,2500,0     # 0 = unpaced (max)
    python -I udp_recv_benchmark.py --rcvbuf 0              # leave OS default

Caveats: loopback has no NIC, no interrupt coalescing and no wire; it measures
the Python/syscall cost per datagram, not real-NIC behaviour. Results on a real
camera link will usually be WORSE (IRQ handling, NIC ring sizes, other traffic).
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import platform
import socket
import struct
import sys
import time

HDR = struct.Struct(">HHI")  # status, block_id, (format<<24 | packet_id)
END_MAGIC = 0xFFFF            # status value used for end-of-test markers
PACKETS_PER_FRAME = 256       # arbitrary "frame" size used for reassembly


def wire_pps(link_mbps: float, udp_payload: int) -> float:
    """Packets/s at line rate for a given UDP payload on Ethernet.
    On-wire bytes = UDP payload + 8 UDP + 20 IPv4 + 14 Eth hdr + 4 FCS + 8 preamble + 12 IFG."""
    on_wire = udp_payload + 8 + 20 + 14 + 4 + 8 + 12
    return link_mbps * 1e6 / 8 / on_wire


# --------------------------------------------------------------------------- receiver
def receiver(host, port_q, result_q, size, mode, rcvbuf, idle_timeout, force=False):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    requested = rcvbuf
    if rcvbuf > 0:
        try:
            # Linux: SO_RCVBUFFORCE (33) ignores net.core.rmem_max but needs CAP_NET_ADMIN
            opt = getattr(socket, "SO_RCVBUFFORCE", 33) if force else socket.SO_RCVBUF
            sock.setsockopt(socket.SOL_SOCKET, opt, rcvbuf)
        except OSError as e:  # macOS refuses > kern.ipc.maxsockbuf with ENOBUFS
            requested = f"{rcvbuf} (refused: {e})"
    actual = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
    sock.bind((host, 0))
    sock.settimeout(idle_timeout)
    port_q.put(sock.getsockname()[1])

    payload = size - HDR.size
    frame = bytearray(payload * PACKETS_PER_FRAME)
    fmv = memoryview(frame)
    scratch = bytearray(65536)
    smv = memoryview(scratch)
    unpack = HDR.unpack_from

    n = 0
    nbytes = 0
    t_first = None
    t_last = None
    max_seq = -1
    end_seen = False
    perf = time.perf_counter
    c_first = None
    try:
        if mode == "recv_into":
            recv_into = sock.recv_into
            while True:
                try:
                    k = recv_into(scratch)
                except socket.timeout:
                    break
                status, block, fmt_pid = unpack(scratch, 0)
                if status == END_MAGIC:
                    end_seen = True
                    break
                pid = fmt_pid & 0xFFFFFF
                off = (pid % PACKETS_PER_FRAME) * payload
                fmv[off:off + k - 8] = smv[8:k]
                t_last = perf()
                if t_first is None:
                    t_first = t_last
                    c_first = time.process_time()
                n += 1
                nbytes += k
                seq = (block << 24) | pid
                if seq > max_seq:
                    max_seq = seq
        else:
            recvfrom = sock.recvfrom
            while True:
                try:
                    data, _ = recvfrom(65536)
                except socket.timeout:
                    break
                status, block, fmt_pid = unpack(data, 0)
                if status == END_MAGIC:
                    end_seen = True
                    break
                pid = fmt_pid & 0xFFFFFF
                off = (pid % PACKETS_PER_FRAME) * payload
                frame[off:off + len(data) - 8] = data[8:]
                t_last = perf()
                if t_first is None:
                    t_first = t_last
                    c_first = time.process_time()
                n += 1
                nbytes += len(data)
                seq = (block << 24) | pid
                if seq > max_seq:
                    max_seq = seq
    finally:
        sock.close()
    c_used = (time.process_time() - c_first) if c_first is not None else 0.0
    dt = (t_last - t_first) if (t_first is not None and t_last is not None) else 0.0
    result_q.put(dict(received=n, bytes=nbytes, recv_seconds=dt, end_seen=end_seen,
                      cpu_seconds=c_used,
                      rcvbuf_requested=requested, rcvbuf_actual=actual))


# --------------------------------------------------------------------------- sender
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


# --------------------------------------------------------------------------- driver
def run_one(host, size, rate_mbps, seconds, mode, rcvbuf, n_senders=1, force=False):
    ctx = mp.get_context("spawn")
    port_q, rq, sq = ctx.Queue(), ctx.Queue(), ctx.Queue()
    r = ctx.Process(target=receiver, args=(host, port_q, rq, size, mode, rcvbuf, 2.0, force))
    r.start()
    port = port_q.get(timeout=20)
    senders = []
    for i in range(n_senders):
        # only the last-finishing sender would be safe to send END; we let sender 0
        # send END after a grace period that exceeds the others' runtime
        s = ctx.Process(target=sender, args=(host, port, sq, size, rate_mbps / n_senders,
                                             seconds, i, i == 0))
        s.start()
        senders.append(s)
    parts = [sq.get(timeout=seconds + 30) for _ in senders]
    rres = rq.get(timeout=seconds + 30)
    for s in senders:
        s.join()
    r.join()
    sres = dict(sent=sum(p["sent"] for p in parts), send_errors=sum(p["send_errors"] for p in parts),
                send_seconds=max(p["send_seconds"] for p in parts))
    sent = sres["sent"]
    recv = rres["received"]
    drop = (1 - recv / sent) if sent else float("nan")
    send_mbps = sent * size * 8 / sres["send_seconds"] / 1e6 if sres["send_seconds"] else 0
    recv_mbps = rres["bytes"] * 8 / rres["recv_seconds"] / 1e6 if rres["recv_seconds"] else 0
    return dict(size=size, target_mbps=rate_mbps, mode=mode, seconds=seconds,
                sent=sent, received=recv, drop_pct=round(100 * drop, 3),
                send_mbps=round(send_mbps, 1), recv_mbps=round(recv_mbps, 1),
                send_kpps=round(sent / sres["send_seconds"] / 1e3, 1) if sres["send_seconds"] else 0,
                recv_kpps=round(recv / rres["recv_seconds"] / 1e3, 1) if rres["recv_seconds"] else 0,
                send_errors=sres["send_errors"], senders=n_senders,
                rx_cpu_pct=round(100 * rres["cpu_seconds"] / rres["recv_seconds"], 1) if rres["recv_seconds"] else 0,
                rcvbuf_requested=rres["rcvbuf_requested"], rcvbuf_actual=rres["rcvbuf_actual"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--sizes", default="1472,8972", help="UDP payload sizes (bytes)")
    ap.add_argument("--rates", default="1000,0", help="target Mbit/s per run; 0 = unpaced/max")
    ap.add_argument("--modes", default="recvfrom,recv_into")
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--rcvbuf", type=int, default=16 * 1024 * 1024,
                    help="SO_RCVBUF to request (0 = OS default)")
    ap.add_argument("--force-rcvbuf", action="store_true",
                    help="Linux only: use SO_RCVBUFFORCE (needs CAP_NET_ADMIN) to exceed net.core.rmem_max")
    ap.add_argument("--senders", type=int, default=1,
                    help="parallel sender processes (a single Python sender tops out ~150-250 kpps)")
    ap.add_argument("--json", help="also write results to this JSON file")
    a = ap.parse_args()

    print(f"python {sys.version.split()[0]} | {platform.platform()} | cpus={os.cpu_count()}")
    print("Line-rate reference (GVSP over UDP, full Ethernet framing overhead):")
    for link in (1000, 2500, 10000):
        print(f"  {link/1000:>4g} GbE: MTU1500 {wire_pps(link, 1472):>9,.0f} pps | "
              f"MTU9000 {wire_pps(link, 8972):>8,.0f} pps")
    rows = []
    hdr = (f"{'size':>5} {'target':>7} {'mode':>9} | {'sent':>9} {'recv':>9} {'drop%':>7} | "
           f"{'tx Mb/s':>8} {'rx Mb/s':>8} {'rx kpps':>8} {'rxCPU%':>6} | rcvbuf(actual)")
    print(hdr)
    print("-" * len(hdr))
    for size in [int(x) for x in a.sizes.split(",")]:
        for rate in [float(x) for x in a.rates.split(",")]:
            for mode in a.modes.split(","):
                res = run_one(a.host, size, rate, a.seconds, mode, a.rcvbuf, a.senders, a.force_rcvbuf)
                rows.append(res)
                tgt = "max" if rate == 0 else f"{rate:g}"
                print(f"{size:>5} {tgt:>7} {mode:>9} | {res['sent']:>9,} {res['received']:>9,} "
                      f"{res['drop_pct']:>7.2f} | {res['send_mbps']:>8.0f} {res['recv_mbps']:>8.0f} "
                      f"{res['recv_kpps']:>8.1f} {res['rx_cpu_pct']:>6.0f} | {res['rcvbuf_actual']}", flush=True)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(dict(python=sys.version, platform=platform.platform(), rows=rows), f, indent=1)


if __name__ == "__main__":
    main()
