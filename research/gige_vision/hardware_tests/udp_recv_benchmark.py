#!/usr/bin/env python3
"""
udp_recv_benchmark.py - can this host (NIC + OS socket buffers + Python) receive a GigE Vision stream?

Standard library only (Python >= 3.9); keep gev_common.py next to this file. No camera needed.

Sends GVSP-like UDP datagrams (8-byte GVSP header + payload) at a paced rate and measures how many a
pure-Python receive loop gets, the receive CPU cost, and the effective socket receive buffer. The receiver
does the minimum a GVSP reassembler must do: parse the header and copy the payload into a frame buffer.

Roles:
  local (default)  sender and receiver processes on this machine (loopback or --host) - measures the
                   Python/syscall cost per packet, not the NIC
  receiver         run on the CAPTURE PC:   python udp_recv_benchmark.py --role receiver --port 50000
  sender           run on ANOTHER PC on the camera switch:
                   python udp_recv_benchmark.py --role sender --target <capture PC IP> --port 50000 \\
                          --rates 1000 --sizes 8972 --seconds 5
                   This is the realistic test: real NIC, switch, interrupt load, MTU/jumbo configuration.
                   Add --max-runs N --json rx.json on the receiver to stop after N runs and save results.

Datagram sizes default to the UDP payload sizes for MTU 1500 and MTU 9000 (1472 and 8972 bytes).
1 GbE at line rate is ~81,000 packets/s with MTU 1500 and ~13,800 with jumbo frames.

Examples:
  python udp_recv_benchmark.py                                  # local matrix: 1472/8972 B x 1000 Mbit/s/max
  python udp_recv_benchmark.py --rates 1000,2500 --sizes 8972 --seconds 5 --json bench.json
  python udp_recv_benchmark.py --rcvbuf 0                       # OS default buffer, to see why it matters

Exit code: 0 = every paced run lost <= --max-drop-pct, 1 = more loss, 2 = bad arguments.

DRAFT: verified on Windows and in Linux Docker over loopback only. See README.md.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import platform
import socket
import struct
import sys
import time
from typing import Any, Optional

try:
    from . import gev_common as gev  # imported as part of a package (e.g. hardware_tests.<script>)
except ImportError:  # run directly (also how spawned child processes import this file)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gev_common as gev  # type: ignore[no-redef]

HDR = struct.Struct(">HHI")  # GVSP standard header: status, block_id, (format << 24 | packet_id)
END = struct.Struct(">HHIQ")  # end marker: status 0xFFFF, 0, 0, packets sent
END_MAGIC = 0xFFFF
PACKETS_PER_FRAME = 256


def wire_pps(link_mbps: gev.Number, udp_payload: int) -> float:
    """Packets/s at line rate: UDP payload + 8 UDP + 20 IPv4 + 14 Ethernet + 4 FCS + 8 preamble + 12 gap."""
    return float(link_mbps * 1e6 / 8 / (udp_payload + 8 + 20 + 14 + 4 + 8 + 12))


# =============================================================================================== receiver
def receive_loop(sock: socket.socket, size: int, idle_timeout: gev.Number, first_timeout: gev.Number) -> dict[str, Any]:
    payload = max(1, size - HDR.size)
    frame = bytearray(payload * PACKETS_PER_FRAME)
    fmv = memoryview(frame)
    scratch = bytearray(65536)
    smv = memoryview(scratch)
    unpack = HDR.unpack_from
    n = nbytes = 0
    sent_reported = 0
    end_seen = 0
    t_first = t_last = None
    c_first = 0.0
    perf = time.perf_counter
    sock.settimeout(first_timeout)
    recv_into = sock.recv_into
    while True:
        try:
            k = recv_into(scratch)
        except socket.timeout:
            break
        except OSError:
            continue
        if k < 8:
            continue
        status, block, fmt_pid = unpack(scratch, 0)
        if status == END_MAGIC:
            if t_first is None:
                continue  # stray end markers of an earlier run
            if k >= END.size:
                sent_reported = END.unpack_from(scratch, 0)[3]
            end_seen += 1
            if end_seen >= 3:
                break
            continue
        if t_first is None:
            t_first = perf()
            c_first = time.process_time()
            sock.settimeout(idle_timeout)
        off = ((fmt_pid & 0xFFFFFF) % PACKETS_PER_FRAME) * payload
        ln = min(k - 8, payload)
        fmv[off:off + ln] = smv[8:8 + ln]
        t_last = perf()
        n += 1
        nbytes += k
    cpu = (time.process_time() - c_first) if t_first is not None else 0.0
    dt = (t_last - t_first) if t_first is not None and t_last is not None else 0.0
    return {"received": n, "bytes": nbytes, "recv_seconds": dt, "cpu_seconds": cpu, "sent_reported": sent_reported,
            "end_seen": end_seen > 0}


def receiver_proc(host: str, port_q: Any, result_q: Any, size: int, rcvbuf: int, force: bool) -> None:
    sock, info = gev.open_udp_receiver(host, 0, rcvbuf, force)
    port_q.put(sock.getsockname()[1])
    err0 = gev.linux_udp_rcvbuf_errors()
    r = receive_loop(sock, size, 2.0, 30.0)
    err1 = gev.linux_udp_rcvbuf_errors()
    sock.close()
    r["rcvbuf"] = info
    r["linux_rcvbuf_errors"] = (err1 - err0) if err0 is not None and err1 is not None else None
    result_q.put(r)


# =============================================================================================== sender
def send_loop(host: str, port: int, size: int, rate_mbps: gev.Number, seconds: gev.Number, sender_idx: int = 0,
              send_end: bool = True) -> dict[str, Any]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 << 20)
    except OSError:
        pass
    dst = (host, port)
    buf = bytearray(size)
    pack_into = HDR.pack_into
    send = sock.sendto
    batch = 16
    pps = (rate_mbps * 1e6 / 8 / size) if rate_mbps > 0 else 0.0
    batch_dt = batch / pps if pps else 0.0
    sent = errors = seq = 0
    t0 = time.perf_counter()
    t_end = t0 + seconds
    next_t = t0
    while True:
        now = time.perf_counter()
        if now >= t_end:
            break
        if batch_dt:
            while now < next_t:  # busy-wait pacing; sleep() is far too coarse at these rates
                now = time.perf_counter()
            next_t += batch_dt
        for _ in range(batch):
            pack_into(buf, 0, 0, ((sender_idx << 12) | (seq >> 24)) & 0xFFFF, (0x03 << 24) | (seq & 0xFFFFFF))
            try:
                send(buf, dst)
                sent += 1
            except OSError:
                errors += 1
            seq += 1
    t1 = time.perf_counter()
    if send_end:
        time.sleep(0.3)
        for _ in range(20):
            try:
                send(END.pack(END_MAGIC, 0, 0, sent), dst)
            except OSError:
                pass
            time.sleep(0.005)
    sock.close()
    return {"sent": sent, "send_errors": errors, "send_seconds": t1 - t0}


def sender_proc(host: str, port: int, result_q: Any, size: int, rate_mbps: gev.Number, seconds: gev.Number,
                sender_idx: int, send_end: bool) -> None:
    result_q.put(send_loop(host, port, size, rate_mbps, seconds, sender_idx, send_end))


# =============================================================================================== driver
def summarise(size: int, rate: gev.Number, sent: int, send_s: gev.Number, r: dict[str, Any], senders: int) -> dict[str, Any]:
    recv = r["received"]
    drop = (1 - recv / sent) if sent else float("nan")
    return {"size": size, "target_mbps": rate, "senders": senders, "sent": sent, "received": recv,
            "drop_pct": round(100 * drop, 3), "send_mbps": round(sent * size * 8 / send_s / 1e6, 1) if send_s else 0,
            "recv_mbps": round(r["bytes"] * 8 / r["recv_seconds"] / 1e6, 1) if r["recv_seconds"] else 0,
            "recv_kpps": round(recv / r["recv_seconds"] / 1e3, 1) if r["recv_seconds"] else 0,
            "rx_cpu_pct": round(100 * r["cpu_seconds"] / r["recv_seconds"], 1) if r["recv_seconds"] else 0,
            "rcvbuf": r.get("rcvbuf"), "linux_rcvbuf_errors": r.get("linux_rcvbuf_errors")}


def run_local(host: str, size: int, rate: gev.Number, seconds: gev.Number, rcvbuf: int, senders: int,
              force: bool) -> dict[str, Any]:
    ctx = mp.get_context("spawn")
    port_q, rq, sq = ctx.Queue(), ctx.Queue(), ctx.Queue()
    r = ctx.Process(target=receiver_proc, args=(host, port_q, rq, size, rcvbuf, force))
    r.start()
    port = port_q.get(timeout=30)
    procs = []
    for i in range(senders):
        p = ctx.Process(target=sender_proc, args=(host, port, sq, size, rate / senders, seconds, i, i == 0))
        p.start()
        procs.append(p)
    parts = [sq.get(timeout=seconds + 60) for _ in procs]
    res = rq.get(timeout=seconds + 60)
    for p in procs:
        p.join()
    r.join()
    sent = sum(p["sent"] for p in parts)
    return summarise(size, rate, sent, max(p["send_seconds"] for p in parts), res, senders)


ROW_HDR = (f"{'size':>5} {'target':>7} | {'sent':>9} {'recv':>9} {'drop%':>7} | {'tx Mb/s':>8} {'rx Mb/s':>8} "
           f"{'rx kpps':>8} {'rxCPU%':>6} | rcvbuf")


def print_row(row: dict[str, Any]) -> None:
    tgt = "max" if not row["target_mbps"] else f"{row['target_mbps']:g}"
    rb = row.get("rcvbuf") or {}
    print(f"{row['size']:>5} {tgt:>7} | {row['sent']:>9,} {row['received']:>9,} {row['drop_pct']:>7.2f} | "
          f"{row['send_mbps']:>8.0f} {row['recv_mbps']:>8.0f} {row['recv_kpps']:>8.1f} {row['rx_cpu_pct']:>6.0f} | "
          f"{rb.get('effective', '?')}{' CAPPED' if rb.get('capped') else ''}", flush=True)


def judge(rows: list[dict[str, Any]], args: argparse.Namespace, rep: gev.Reporter) -> None:
    for row in rows:
        name = f"{row['size']} B @ {'max' if not row['target_mbps'] else str(row['target_mbps']) + ' Mbit/s'}"
        rb = row.get("rcvbuf") or {}
        if rb.get("capped"):
            rep.add("socket receive buffer", gev.WARN, f"requested {rb['requested']} B, got {rb['effective']} B - "
                    f"{gev.rcvbuf_hint()}", name)
        if row.get("linux_rcvbuf_errors"):
            rep.add("kernel receive-buffer drops", gev.WARN, f"{row['linux_rcvbuf_errors']} datagrams", name)
        if not row["target_mbps"]:
            rep.add("unpaced (max) throughput", gev.INFO, f"{row['recv_kpps']} kpps received, {row['drop_pct']} % "
                    "lost with the sender running flat out (Python sender limit, not a pass/fail test)", name)
            continue
        need = wire_pps(row["target_mbps"], row["size"]) / 1e3
        ok = row["sent"] > 0 and row["drop_pct"] <= args.max_drop_pct
        rep.add("paced receive", gev.PASS if ok else gev.FAIL,
                f"lost {row['drop_pct']} % (limit {args.max_drop_pct} %), received {row['recv_kpps']} kpps "
                f"(a {row['target_mbps']:g} Mbit/s link carries at most {need:.1f} kpps of this size), receive CPU "
                f"{row['rx_cpu_pct']} % of one core", name)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--role", choices=["local", "receiver", "sender"], default="local")
    ap.add_argument("--host", default="127.0.0.1", help="local role: address the receiver binds and the sender targets")
    ap.add_argument("--bind", default="0.0.0.0", help="receiver role: local address to bind")
    ap.add_argument("--target", default="", help="sender role: the receiver PC's IP address")
    ap.add_argument("--port", type=int, default=50000, help="receiver/sender roles: UDP port (default 50000)")
    ap.add_argument("--sizes", default="1472,8972", help="UDP payload sizes in bytes (comma separated)")
    ap.add_argument("--rates", default="1000,0", help="target Mbit/s per run, 0 = unpaced/max (comma separated)")
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--rcvbuf", type=int, default=32 << 20, help="SO_RCVBUF request (0 = OS default)")
    ap.add_argument("--force-rcvbuf", action="store_true", help="Linux: SO_RCVBUFFORCE (root / CAP_NET_ADMIN)")
    ap.add_argument("--senders", type=int, default=1, help="local role: parallel sender processes")
    ap.add_argument("--max-runs", type=int, default=0, help="receiver role: exit after this many runs (0 = Ctrl+C)")
    ap.add_argument("--max-drop-pct", type=float, default=0.1, help="PASS limit for paced runs (default 0.1 %%)")
    ap.add_argument("--json", metavar="PATH")
    ap.add_argument("--selftest", action="store_true", help="run offline checks and exit")
    args = ap.parse_args(argv)
    if args.selftest:
        return gev.selftest_main(selftest_extra, title="udp_recv_benchmark selftest")
    sizes = [int(x) for x in args.sizes.split(",") if x]
    rates = [float(x) for x in args.rates.split(",") if x]
    print(f"python {sys.version.split()[0]} | {platform.platform()} | cpus={os.cpu_count()} | role={args.role}")
    print("line rate reference (full Ethernet framing):")
    for link in (1000, 2500, 5000, 10000):
        print(f"  {link / 1000:>4g} GbE: MTU1500 {wire_pps(link, 1472):>9,.0f} pps | MTU9000 {wire_pps(link, 8972):>8,.0f} pps")
    rep = gev.Reporter("udp_recv_benchmark")
    rows: list[dict[str, Any]] = []
    if args.role == "sender":
        if not args.target:
            print("--role sender needs --target <receiver IP>")
            return 2
        for size in sizes:
            for rate in rates:
                r = send_loop(args.target, args.port, size, rate, args.seconds)
                print(f"sent {r['sent']:,} x {size} B in {r['send_seconds']:.2f} s "
                      f"({r['sent'] * size * 8 / r['send_seconds'] / 1e6:.0f} Mbit/s, {r['send_errors']} send errors)")
                time.sleep(1.0)
        return 0
    if args.role == "receiver":
        size = max(sizes)
        sock, info = gev.open_udp_receiver(args.bind, args.port, args.rcvbuf, args.force_rcvbuf)
        print(f"receiver on {args.bind}:{args.port}, SO_RCVBUF requested {info['requested']} -> {info['effective']} B"
              f"{' (CAPPED: ' + gev.rcvbuf_hint() + ')' if info['capped'] else ''}. Waiting for a sender "
              "(Ctrl+C to stop) ...")
        try:
            while True:
                err0 = gev.linux_udp_rcvbuf_errors()
                r = receive_loop(sock, size, 2.0, 3600.0)
                if not r["received"]:  # idle, or stray end markers of the previous run
                    continue
                err1 = gev.linux_udp_rcvbuf_errors()
                r["rcvbuf"] = info
                r["linux_rcvbuf_errors"] = (err1 - err0) if err0 is not None and err1 is not None else None
                sent = r["sent_reported"] or r["received"]
                row = summarise(round(r["bytes"] / r["received"]), 0.0, sent, r["recv_seconds"] or 1.0, r, 1)
                row["target_mbps"] = round(row["recv_mbps"])
                print(ROW_HDR)
                print_row(row)
                rows.append(row)
                if args.json:
                    gev.write_json(args.json, {"tool": "udp_recv_benchmark", "role": "receiver", "host": gev.host_info(),
                                               "rows": rows})
                if args.max_runs and len(rows) >= args.max_runs:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            sock.close()
        judge(rows, args, rep)
        rep.print_summary()
        return rep.exit_code()
    print(ROW_HDR)
    print("-" * len(ROW_HDR))
    for size in sizes:
        for rate in rates:
            row = run_local(args.host, size, rate, args.seconds, args.rcvbuf, args.senders, args.force_rcvbuf)
            rows.append(row)
            print_row(row)
    judge(rows, args, rep)
    rep.print_summary()
    if args.json:
        gev.write_json(args.json, {"tool": "udp_recv_benchmark", "role": "local", "host": gev.host_info(),
                                   "args": vars(args), "rows": rows, "checks": rep.as_list()})
    return rep.exit_code()


def selftest_extra(rep: gev.Reporter) -> None:
    buf = bytearray(16)
    HDR.pack_into(buf, 0, 0, 0x0123, (0x03 << 24) | 0x000456)
    h = gev.parse_gvsp_header(buf, len(buf))
    rep.check("benchmark datagrams carry a valid GVSP payload header", h is not None and h[1:4] == (0x0123, 3, 0x456))
    rep.check("line-rate arithmetic (1 GbE MTU1500 = 81,274 pps)", round(wire_pps(1000, 1472)) == 81274)


if __name__ == "__main__":
    sys.exit(main())
