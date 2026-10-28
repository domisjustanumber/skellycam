#!/usr/bin/env python3
"""
gvsp_capture_report.py - what is a GigE Vision camera actually streaming? Raw or compressed?

Standard library only (Python >= 3.9); keep gev_common.py next to this file.
Optional: --control viva uses viva-genicam (pip install viva-genicam) to start acquisition when the
camera's AcquisitionStart command is too complex for the built-in mini GenICam resolver.

Two ways to run it:

  A. LIVE (this script streams from the camera itself)
       python gvsp_capture_report.py --ip 169.254.1.10 --seconds 5
     Takes control, points stream channel 0 at this host (SCDA/SCP registers), optionally sets the
     packet size (--packet-size 8192 for jumbo frames) and 64-bit block ids, executes AcquisitionStart
     (resolved from the camera's GenICam XML), receives GVSP with a large SO_RCVBUF, requests missing
     packets with PACKETRESEND, then stops and restores every register it touched.
     --save-frame DIR writes the first complete frame (.raw + .json, and .pgm for 8-bit Mono/Bayer).

  B. PCAP (any software streams; you capture the packets)
       Wireshark / dumpcap / tcpdump on the camera NIC while a vendor viewer streams, e.g.
         Linux/macOS: sudo tcpdump -i <nic> -s 128 -w gev.pcap udp
         Windows:     "C:\\Program Files\\Wireshark\\dumpcap.exe" -i <nic> -s 128 -w gev.pcapng -f udp
       (-s 128 keeps only the headers - enough for this report and keeps files small.)
       python gvsp_capture_report.py --pcap gev.pcapng

Both report, per stream: payload types, pixel formats (PFNC names, custom/vendor formats flagged),
image size, packet size and jumbo frames, extended-ID (64-bit block id) usage, complete / incomplete /
lost frames, resend requests and resent packets, device timestamp deltas and frame rate, and an explicit
verdict: UNCOMPRESSED / COMPRESSED / LIKELY-COMPRESSED / VENDOR-SPECIFIC / CONTAINER / UNKNOWN.
Live mode also reports the effective socket receive buffer and warns when the OS capped it.

Exit code: 0 = no FAIL, 1 = a check failed (e.g. fewer than --min-complete of the frames complete),
2 = nothing to analyse / bad arguments.

DRAFT: verified only against software-emulated cameras (Aravis arv-fake-gv-camera-0.8, viva-genicam
FakeGigeCamera) and synthetic captures. See README.md.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import sys
import time
from collections import Counter
from typing import Any, Optional

try:
    from . import gev_common as gev  # imported as part of a package (e.g. hardware_tests.<script>)
except ImportError:  # run directly: python gvsp_capture_report.py
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gev_common as gev  # type: ignore[no-redef]

GVCP_NAMES = {0x0002: "DISCOVERY", 0x0004: "FORCEIP", 0x0040: "PACKETRESEND", 0x0080: "READREG", 0x0082: "WRITEREG",
              0x0084: "READMEM", 0x0086: "WRITEMEM", 0x0100: "ACTION"}


# =============================================================================
# Reporting shared by both modes
# =============================================================================
def report_stream(name: str, s: dict[str, Any], rep: gev.Reporter, args: argparse.Namespace,
                  gev_major: Optional[int] = None) -> None:
    print(f"\n=== {name}")
    print(f"  packets {s['packets']}  formats {s['packet_formats']}  status codes {s['status_codes']}")
    print(f"  frames: seen {s['frames_seen']}, complete {s['frames_complete']}, incomplete {s['frames_incomplete']}, "
          f"trailer missing {s['frames_trailer_missing']}, never seen (block-id gaps) {s['block_id_gaps']}, "
          f"missing packets {s['missing_packets_total']}")
    for pf in s["pixel_formats"]:
        cv = f" (OpenCV: {pf['opencv_bayer_code']})" if pf["opencv_bayer_code"] else ""
        print(f"  image: {pf['pixel_format']} {pf['width']}x{pf['height']} x{pf['frames']} leaders{cv}")
    if s.get("leader_timestamp_delta_ticks"):
        d = s["leader_timestamp_delta_ticks"]
        print(f"  leader timestamp deltas (ticks): min {d['min']:.0f} median {d['median']:.0f} p95 {d['p95']:.0f} "
              f"max {d['max']:.0f}; first timestamp {s['leader_timestamp_first']}")
    rep.check("GVSP leader + trailer packets", s["packet_formats"].get("LEADER", 0) > 0
              and s["packet_formats"].get("TRAILER", 0) > 0, f"{s['packet_formats']}", name)
    total = s["frames_seen"] + s["block_id_gaps"]
    ok = s["frames_complete"] >= 1 and s["completeness"] >= args.min_complete
    rep.add("frames complete", gev.PASS if ok else gev.FAIL,
            f"{s['frames_complete']}/{total} ({100 * s['completeness']:.1f} %; limit {100 * args.min_complete:.0f} %)"
            + ("" if s["frames_complete"] else " - NO complete frame"), name)
    rep.add("compression verdict", gev.INFO, f"{s['compression_verdict']}: {'; '.join(s['compression_reasons'])}", name)
    common = s["payload_packet_ip_size_most_common"] or s["max_ip_packet_size"]
    rep.add("packet size", gev.INFO, f"payload packets {common} B IP datagrams (max {s['max_ip_packet_size']}) -> "
            f"{'jumbo frames' if s['jumbo_frames'] else 'standard 1500 MTU'}", name)
    ei = s["extended_ids_used"]
    rep.add("extended ids (64-bit block ids)", gev.WARN if (gev_major or 0) >= 3 and not ei else gev.INFO,
            f"{'used' if ei else 'not used'} ({s['extended_id_packets']}/{s['packets']} packets)"
            + (" - GEV 3.x devices are expected to use extended ids" if (gev_major or 0) >= 3 and not ei else ""), name)
    if s["resend_ranges_requested"] or s["resent_packets_received"]:
        req, rec = s["resend_packets_requested"], s["resend_packets_recovered"]
        st = gev.WARN if req and rec < req else gev.INFO
        rep.add("packet resend", st, f"{req} packet(s) in {s['resend_ranges_requested']} range(s) requested, {rec} "
                f"recovered; {s['resent_packets_received']} packet(s) carried the resend marker, "
                f"{s['late_packets_after_close']} arrived after their frame was closed", name)
    if "leader_timestamp_monotonic" in s:
        fps = s.get("device_fps_from_timestamps")
        rep.add("device timestamps", gev.INFO if s["leader_timestamp_monotonic"] else gev.WARN,
                ("increasing" if s["leader_timestamp_monotonic"] else "NOT monotonic")
                + (f"; device frame rate {fps:.2f} fps" if fps else "")
                + (f"; host arrival rate {s['host_fps']:.2f} fps" if s.get("host_fps") else ""), name)
    elif s["frames_seen"]:
        rep.add("device timestamps", gev.INFO, "fewer than 3 leaders with timestamps", name)


# =============================================================================
# PCAP mode
# =============================================================================
def run_pcap(args: argparse.Namespace, rep: gev.Reporter, out: dict[str, Any]) -> int:
    if not os.path.isfile(args.pcap):
        print(f"no such file: {args.pcap}")
        return 2
    flows: dict[tuple[str, int, str, int], gev.GvspAnalyzer] = {}
    gvcp_cmds: Counter[str] = Counter()
    fragments = 0
    truncated = 0
    n = 0
    for ts, lt, frame, orig in gev.iter_capture(args.pcap):
        n += 1
        if orig > len(frame):
            truncated += 1
        u = gev.extract_udp(lt, frame)
        if u is None:
            continue
        if u.fragment:
            fragments += 1
            if not u.payload:
                continue
        if gev.GVCP_PORT in (u.sport, u.dport):
            if u.dport == gev.GVCP_PORT and len(u.payload) >= 8 and u.payload[0] == gev.GVCP_KEY:
                cmd = struct.unpack(">H", u.payload[2:4])[0]
                gvcp_cmds[GVCP_NAMES.get(cmd, f"0x{cmd:04X}")] += 1
            continue
        key = (u.src, u.sport, u.dst, u.dport)
        a = flows.get(key)
        if a is None:
            a = flows[key] = gev.GvspAnalyzer()
        a.feed(u.payload, len(u.payload), ts, ip_size=u.ip_total_len, wire_len=u.udp_payload_len)
    out["capture"] = {"file": args.pcap, "frames": n, "truncated_frames": truncated, "ip_fragments": fragments,
                      "gvcp_commands_seen": dict(gvcp_cmds)}
    print(f"read {n} captured frames from {args.pcap} ({truncated} truncated by snaplen, {fragments} IP fragments)")
    if gvcp_cmds:
        print(f"GVCP commands host->camera: {dict(gvcp_cmds)}")
    if fragments:
        rep.add("IP fragmentation", gev.WARN, f"{fragments} fragmented datagrams: the stream packet size is larger "
                "than the path MTU (enable jumbo frames on the NIC/switch or lower GevSCPSPacketSize)")
    streams = {}
    ignored = 0
    for (src, sport, dst, dport), a in flows.items():
        a.finish()
        has_leader = any(L["payload_type"] in gev.PAYLOAD_TYPES or L["payload_type"] >= 0x8000
                         for L in a.leaders if "payload_type" in L)
        if not (has_leader and a.formats.get("TRAILER", 0)):
            ignored += 1
            continue
        s = a.summary(tick_hz=args.tick_hz)
        name = f"GVSP {src}:{sport} -> {dst}:{dport}"
        streams[name] = s
        report_stream(name, s, rep, args)
    if ignored:
        print(f"\n({ignored} other UDP flow(s) did not look like GVSP and were ignored)")
    out["streams"] = streams
    if not streams:
        rep.add("GVSP stream found", gev.FAIL, "no GVSP stream (leader + trailer) in the capture. Was the capture "
                "running on the camera NIC while streaming? On Windows, vendor filter drivers can hide GVSP from "
                "Npcap - switch the vendor tool to its socket driver while capturing.")
        return 2
    if not args.tick_hz:
        print("\nnote: timestamp tick frequency unknown in pcap mode (pass --tick-hz; 1000000000 when PTP is on)")
    return -1


# =============================================================================
# LIVE mode
# =============================================================================
class StdlibControl:
    """Camera control through gev_common.GvcpClient + the mini GenICam resolver."""

    def __init__(self, ip: str, iface: str, rep: gev.Reporter) -> None:
        self.name = "stdlib GVCP"
        self.client = gev.GvcpClient(ip, local_ip=iface)
        self.local_ip = self.client.local_ip
        self.rep = rep
        self.genapi: Optional[gev.MiniGenApi] = None
        self.locked = False

    def read_reg(self, addr: int) -> int:
        return self.client.read_reg(addr)

    def read_reg_opt(self, addr: int) -> Optional[int]:
        return self.client.read_reg_opt(addr)[0]

    def write_reg(self, addr: int, value: int) -> None:
        self.client.write_reg(addr, value, restore=True)

    def prepare(self) -> None:
        x = gev.fetch_genicam_xml(self.client)
        if x["xml"] is None:
            raise gev.GenApiUnsupported(f"cannot get the GenICam XML: {x['error']}")
        self.genapi = gev.MiniGenApi(x["xml"], self.client)
        for cmd in ("AcquisitionStart", "AcquisitionStop"):
            if not self.genapi.has(cmd):
                raise gev.GenApiUnsupported(f"XML has no {cmd}")
        self.client.take_control()

    def start(self) -> None:
        assert self.genapi is not None
        if self.genapi.has("TLParamsLocked"):
            try:
                self.genapi.set_int("TLParamsLocked", 1)
                self.locked = True
            except (gev.GenApiUnsupported, gev.GvcpError) as e:
                print(f"  (TLParamsLocked not set: {e})")
        self.genapi.execute("AcquisitionStart")

    def stop(self) -> None:
        if self.genapi is None:
            return
        try:
            self.genapi.execute("AcquisitionStop")
        finally:
            if self.locked:
                try:
                    self.genapi.set_int("TLParamsLocked", 0)
                except (gev.GenApiUnsupported, gev.GvcpError):
                    pass

    def close(self) -> list[str]:
        if self.client.control_lost:
            self.rep.add("camera control", gev.FAIL, "control was lost during the capture (heartbeat timeout: network "
                         "glitch, another application, or the host was too busy)", self.client.ip)
        return self.client.close()


class VivaControl:
    """Camera control through viva-genicam (full GenApi). Only control - GVSP is still received here."""

    def __init__(self, ip: str, iface: str, rep: gev.Reporter) -> None:
        try:
            import viva_genicam as vg  # noqa: PLC0415
        except ImportError as e:
            raise SystemExit("--control viva needs viva-genicam: pip install viva-genicam") from e
        self.name = "viva-genicam"
        infos = [d for d in vg.discover(timeout_ms=1000, iface=iface or None, all=ip.startswith("127."))
                 if d.ip == ip]
        if not infos:
            raise gev.GvcpError(f"viva-genicam did not discover {ip}")
        self.cam = vg.connect_gige(infos[0], iface=iface or None)
        self.local_ip = iface or gev.local_ip_towards(ip)
        self._restore: list[tuple[int, int]] = []

    def read_reg(self, addr: int) -> int:
        return int.from_bytes(self.cam.read_register(addr, 4), "big")

    def read_reg_opt(self, addr: int) -> Optional[int]:
        try:
            return self.read_reg(addr)
        except Exception:  # noqa: BLE001 - viva raises its own error types
            return None

    def write_reg(self, addr: int, value: int) -> None:
        old = self.read_reg_opt(addr)
        if old is not None and addr not in [a for a, _ in self._restore]:
            self._restore.append((addr, old))
        self.cam.write_register(addr, (value & 0xFFFFFFFF).to_bytes(4, "big"))

    def prepare(self) -> None:
        pass

    def start(self) -> None:
        self.cam.acquisition_start()

    def stop(self) -> None:
        self.cam.acquisition_stop()

    def close(self) -> list[str]:
        problems = []
        for addr, v in reversed(self._restore):
            try:
                self.cam.write_register(addr, v.to_bytes(4, "big"))
            except Exception as e:  # noqa: BLE001
                problems.append(f"restore 0x{addr:04X}: {e}")
        self.cam.close()
        return problems


def save_frame(path_dir: str, leader: dict[str, Any], packets: dict[int, bytes], ip: str) -> list[str]:
    os.makedirs(path_dir, exist_ok=True)
    data = b"".join(packets[k] for k in sorted(packets))
    base = os.path.join(path_dir, f"frame_{ip.replace('.', '_')}_{leader.get('pixel_format_name', 'unknown')}")
    files = [base + ".raw", base + ".json"]
    with open(base + ".raw", "wb") as f:
        f.write(data)
    meta = {k: v for k, v in leader.items() if k != "t_host"}
    meta["bytes"] = len(data)
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    w, h = leader.get("size_x", 0), leader.get("size_y", 0)
    if leader.get("pixel_format") and gev.pfnc_bits_per_pixel(leader["pixel_format"]) == 8 and \
            not leader.get("padding_x") and len(data) >= w * h > 0 and leader["pixel_format"] >> 24 == 0x01:
        with open(base + ".pgm", "wb") as f:
            f.write(f"P5 {w} {h} 255\n".encode() + data[:w * h])
        files.append(base + ".pgm")
    return files


def run_live(args: argparse.Namespace, rep: gev.Reporter, out: dict[str, Any]) -> int:
    ip = args.ip
    if not ip:
        devs = gev.discover_devices(iface_ips=[args.iface] if args.iface else None)
        if len(devs) != 1:
            print(f"found {len(devs)} cameras: {[d['control_ip'] for d in devs]} - pass --ip to choose one")
            return 2
        ip = devs[0]["control_ip"]
    probe = gev.GvcpClient(ip, local_ip=args.iface)
    try:
        ver = probe.read_reg(gev.REG_VERSION)
        cap = probe.read_reg(gev.REG_GVCP_CAPABILITY)
        tick = probe.tick_frequency()
    except gev.GvcpError as e:
        rep.add("camera reachable", gev.FAIL, str(e), ip)
        probe.close()
        return 2
    probe.close()
    major = ver >> 16
    out["camera"] = {"ip": ip, "gev_version": f"{major}.{ver & 0xFFFF}", "capability": f"0x{cap:08X}", "tick_hz": tick}
    rep.add("camera reachable", gev.PASS, f"GEV {major}.{ver & 0xFFFF}, tick {tick} Hz, packet resend "
            f"{'supported' if cap & gev.CAP['packet_resend'] else 'NOT supported'}", ip)
    try:
        ctl: Any = VivaControl(ip, args.iface, rep) if args.control == "viva" else StdlibControl(ip, args.iface, rep)
    except Exception as e:  # noqa: BLE001 - viva-genicam raises its own error types
        rep.add("take control", gev.FAIL, f"{args.control}: {type(e).__name__}: {e}", ip)
        return 1
    sock: Optional[socket.socket] = None
    started = False
    try:
        try:
            ctl.prepare()
        except gev.GenApiUnsupported as e:
            rep.add("start acquisition", gev.SKIP, f"{e}. Rerun with --control viva (pip install viva-genicam), or use "
                    "--pcap with a vendor viewer streaming", ip)
            return 2
        sock, rinfo = gev.open_udp_receiver(ctl.local_ip, args.port, args.rcvbuf, args.force_rcvbuf)
        out["socket"] = rinfo
        rep.add("socket receive buffer", gev.WARN if rinfo["capped"] else gev.PASS,
                f"requested {rinfo['requested']} B via {rinfo['method']}, OS reports {rinfo['effective']} B "
                f"(default {rinfo['os_default']} B)" + (f" - CAPPED, {gev.rcvbuf_hint()}" if rinfo["capped"] else ""), ip)
        port = sock.getsockname()[1]
        ctl.write_reg(gev.reg_sc_dest_address(0), struct.unpack(">I", socket.inet_aton(ctl.local_ip))[0])
        ctl.write_reg(gev.reg_sc_port(0), port)
        scps = ctl.read_reg(gev.reg_sc_packet_size(0))
        if args.packet_size:
            ctl.write_reg(gev.reg_sc_packet_size(0), (scps & 0xFFFF0000 & ~gev.SCPS_FIRE_TEST) | gev.SCPS_DO_NOT_FRAGMENT
                          | args.packet_size)
            scps = ctl.read_reg(gev.reg_sc_packet_size(0))
            if scps & 0xFFFF != args.packet_size:
                rep.add("packet size", gev.WARN, f"asked for {args.packet_size}, camera uses {scps & 0xFFFF}", ip)
        out["scps"] = scps & 0xFFFF
        if args.test_packet:
            ctl.write_reg(gev.reg_sc_packet_size(0), scps | gev.SCPS_FIRE_TEST | gev.SCPS_DO_NOT_FRAGMENT)
            sock.settimeout(0.5)
            try:
                d = sock.recv(65536)
                ok = len(d) + gev.IP_UDP_OVERHEAD == scps & 0xFFFF
                rep.add("test packet (do-not-fragment)", gev.PASS if ok else gev.WARN,
                        f"received {len(d) + gev.IP_UDP_OVERHEAD} B for packet size {scps & 0xFFFF}", ip)
            except socket.timeout:
                big = scps & 0xFFFF > 1500
                rep.add("test packet (do-not-fragment)", gev.WARN if big else gev.SKIP,
                        "no test packet arrived: either the camera does not implement the fire-test bit, or"
                        + (" a packet this large cannot pass - enable jumbo frames (MTU 9000) on the NIC and switch, "
                           "or use a smaller --packet-size" if big else " something blocks it (firewall?)"), ip)
            ctl.write_reg(gev.reg_sc_packet_size(0), scps & ~gev.SCPS_FIRE_TEST)
        if args.extended_ids or major >= 3:
            gcfg = ctl.read_reg_opt(gev.REG_GVSP_CONFIGURATION)
            if gcfg is not None and not gcfg & gev.GVSP_CONFIG_64BIT_BLOCK_ID:
                try:
                    ctl.write_reg(gev.REG_GVSP_CONFIGURATION, gcfg | gev.GVSP_CONFIG_64BIT_BLOCK_ID)
                except gev.GvcpError as e:
                    rep.add("enable extended ids", gev.WARN, str(e), ip)
        sc_src_port = ctl.read_reg_opt(gev.reg_sc_source_port(0))
        if sc_src_port:
            try:  # firewall traversal: lets a stateful firewall treat the stream as a reply
                sock.sendto(b"\0\0\0\0", (ip, sc_src_port & 0xFFFF))
            except OSError:
                pass
        resend = not args.no_resend and bool(cap & gev.CAP["packet_resend"])
        err0 = gev.linux_udp_rcvbuf_errors()
        print(f"  streaming to {ctl.local_ip}:{port} for {args.seconds:.1f} s (control via {ctl.name}, resend "
              f"{'on' if resend else 'off'}) ...")
        ctl.start()
        started = True
        a = gev.GvspAnalyzer()
        stats = receive(sock, a, ip, args, resend, ctl, out)
        ctl.stop()
        started = False
        drain_until = time.monotonic() + 0.3
        stats_tail = receive(sock, a, ip, args, resend, ctl, out, until=drain_until)
        a.finish()
        err1 = gev.linux_udp_rcvbuf_errors()
        s = a.summary(tick_hz=tick)
        s["receive"] = {"foreign_datagrams": stats["foreign"] + stats_tail["foreign"],
                        "wall_s": stats["wall_s"], "mbit_s": a.bytes * 8 / stats["wall_s"] / 1e6 if stats["wall_s"] else 0}
        if err0 is not None and err1 is not None:
            s["receive"]["linux_udp_rcvbuf_errors_delta"] = err1 - err0
            if err1 - err0:
                rep.add("kernel receive-buffer drops", gev.WARN, f"{err1 - err0} UDP datagrams dropped by the kernel "
                        f"(socket buffer full) - {gev.rcvbuf_hint()}", ip)
        out["stream"] = s
        report_stream(f"GVSP {ip} -> {ctl.local_ip}:{port} ({s['receive']['mbit_s']:.0f} Mbit/s)", s, rep, args, major)
        if s["frames_seen"] == 0:
            print("  hint: no packets arrived. Check the host firewall (allow inbound UDP for this Python, see README), "
                  "that --iface is the camera NIC, and that the camera accepted AcquisitionStart.")
        return -1
    except gev.GvcpError as e:
        rep.add("live capture", gev.FAIL, str(e), ip)
        return 1
    finally:
        if started:
            try:
                ctl.stop()
            except Exception:  # noqa: BLE001
                pass
        for p in ctl.close():
            rep.add("restore registers", gev.WARN, p, ip)
        if sock is not None:
            sock.close()


def receive(sock: socket.socket, a: gev.GvspAnalyzer, ip: str, args: argparse.Namespace, resend: bool, ctl: Any,
            out: dict[str, Any], until: Optional[float] = None) -> dict[str, Any]:
    scratch = bytearray(65536)
    mv = memoryview(scratch)
    sock.settimeout(0.02)
    t_start = time.monotonic()
    t_end = until if until is not None else t_start + args.seconds
    foreign = 0
    last_check = t_start
    resend_id = 0x7000
    grace = args.resend_wait if resend else 0.02
    want_frame = bool(args.save_frame) and "saved_frame" not in out
    frame_bid: Optional[int] = None
    frame_pkts: dict[int, bytes] = {}
    while True:
        now = time.monotonic()
        if now >= t_end:
            break
        try:
            n, addr = sock.recvfrom_into(scratch)
        except socket.timeout:
            n, addr = 0, ("", 0)
        except OSError:
            continue
        now = time.monotonic()
        if n:
            if addr[0] != ip:
                foreign += 1
                continue
            hdr = a.feed(scratch, n, now)
            if hdr is not None:
                _, bid, fmt, pid, ei, _, hl = hdr
                if want_frame:
                    if frame_bid is None and fmt == gev.FMT_LEADER:
                        frame_bid, frame_pkts = bid, {}
                    if bid == frame_bid and fmt not in (gev.FMT_LEADER, gev.FMT_TRAILER):
                        frame_pkts[pid] = bytes(mv[hl:n])
                    if bid == frame_bid and fmt == gev.FMT_TRAILER:
                        blk = a.open.get(bid)
                        if blk is not None and blk.leader and not a.missing_ids(bid):
                            out["saved_frame"] = save_frame(args.save_frame, blk.leader, frame_pkts, ip)
                            print(f"  saved first complete frame: {out['saved_frame']}")
                            want_frame = False
                        else:
                            frame_bid = None
                if resend and fmt == gev.FMT_TRAILER:
                    blk = a.open.get(bid)
                    missing = a.missing_ids(bid)
                    if blk is not None and missing and not blk.resend_ranges:
                        ranges = a.ranges(missing)[:64]
                        for first, last in ranges:
                            resend_id = resend_id + 1 if resend_id < 0xFFFF else 1
                            try:
                                sock.sendto(gev.build_packetresend(bid, first, last, resend_id, extended_ids=ei),
                                            (ip, gev.GVCP_PORT))
                            except OSError:
                                pass
                        a.mark_resend_requested(bid, ranges)
        if now - last_check >= 0.01:
            for bid in a.due_for_close(now, grace, 1.0):
                a.close(bid)
            last_check = now
    return {"foreign": foreign, "wall_s": time.monotonic() - t_start}


# =============================================================================
def selftest_extra(rep: gev.Reporter) -> None:
    import tempfile  # noqa: PLC0415
    frames = [gev.synth_gvsp_frame(b, b * 1000, 0x01080009, 32, 16, 256, drop={1} if b == 2 else None)
              for b in (1, 2, 3)]
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "s.pcap")
        gev.write_pcap(path, [("10.0.0.2", 20202, "10.0.0.1", 40000, p) for fr in frames for p in fr]
                       + [("10.0.0.1", 53, "10.0.0.9", 53, b"\x12\x34not-gvsp")])
        ns = argparse.Namespace(pcap=path, tick_hz=1000, min_complete=0.99)
        r = gev.Reporter("pcap-mode", quiet=True)
        o: dict[str, Any] = {}
        run_pcap(ns, r, o)
        names = list(o.get("streams", {}))
        s = o["streams"][names[0]] if names else {}
        rep.check("pcap mode: one GVSP stream, non-GVSP flow ignored", len(names) == 1, str(names))
        rep.check("pcap mode: completeness check FAILS when a frame is incomplete (2/3)",
                  any(x.name == "frames complete" and x.status == gev.FAIL for x in r.results)
                  and s.get("frames_complete") == 2)
        files = save_frame(tmp, {"pixel_format": 0x01080001, "pixel_format_name": "Mono8", "size_x": 4, "size_y": 2},
                           {1: b"\x01\x02\x03\x04", 2: b"\x05\x06\x07\x08"}, "10.0.0.2")
        with open(files[-1], "rb") as f:
            rep.check("save_frame writes a PGM for Mono8", f.read() == b"P5 4 2 255\n\x01\x02\x03\x04\x05\x06\x07\x08")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--pcap", help="analyse this pcap/pcapng capture instead of streaming")
    src.add_argument("--ip", help="camera IP for live capture (default: the only camera discovered)")
    ap.add_argument("--iface", default="", help="local IPv4 address of the NIC facing the camera")
    ap.add_argument("--seconds", type=float, default=5.0, help="live capture duration (default 5 s)")
    ap.add_argument("--packet-size", type=int, default=0, help="set GevSCPSPacketSize, e.g. 1500 or 8192 (default: keep)")
    ap.add_argument("--test-packet", action="store_true", help="send a fire-test packet first (checks jumbo/MTU path)")
    ap.add_argument("--extended-ids", action="store_true", help="enable 64-bit block ids (automatic for GEV 3.x)")
    ap.add_argument("--no-resend", action="store_true", help="never send PACKETRESEND")
    ap.add_argument("--resend-wait", type=float, default=0.05, help="seconds to wait for resent packets (default 0.05)")
    ap.add_argument("--rcvbuf", type=int, default=32 << 20, help="SO_RCVBUF request in bytes (default 32 MiB)")
    ap.add_argument("--force-rcvbuf", action="store_true", help="Linux: SO_RCVBUFFORCE (root / CAP_NET_ADMIN)")
    ap.add_argument("--port", type=int, default=0, help="fixed local UDP port for the stream (default: any)")
    ap.add_argument("--control", choices=["stdlib", "viva"], default="stdlib",
                    help="how to start acquisition: built-in mini GenICam resolver, or viva-genicam")
    ap.add_argument("--save-frame", metavar="DIR", help="save the first complete frame (.raw/.json/.pgm)")
    ap.add_argument("--tick-hz", type=int, default=0, help="pcap mode: device tick frequency for timestamp deltas")
    ap.add_argument("--min-complete", type=float, default=0.99, help="PASS threshold for complete frames (default 0.99)")
    ap.add_argument("--json", metavar="PATH", help="write the full report to JSON")
    ap.add_argument("--selftest", action="store_true", help="run offline checks and exit")
    args = ap.parse_args(argv)
    if args.selftest:
        return gev.selftest_main(selftest_extra, title="gvsp_capture_report selftest")
    rep = gev.Reporter("gvsp_capture_report")
    out: dict[str, Any] = {"tool": "gvsp_capture_report", "host": gev.host_info(), "args": vars(args)}
    rc = run_pcap(args, rep, out) if args.pcap else run_live(args, rep, out)
    rep.print_summary()
    out["checks"] = rep.as_list()
    if args.json:
        gev.write_json(args.json, out)
    return rc if rc >= 0 else rep.exit_code()


if __name__ == "__main__":
    sys.exit(main())
