#!/usr/bin/env python3
"""
gev_ptp_sync_test.py - stand-alone GigE Vision PTP / Action-Command test tool.

Pure Python standard library (3.8+). Works on Windows, macOS and Linux.
It talks raw GVCP (UDP/3956) to the cameras and only uses *bootstrap registers*
defined by the GigE Vision standard, so no GenICam XML / vendor SDK is needed.

Register addresses and bit masks are taken from (and cross-checked against):
  * Wireshark GVCP dissector  epan/dissectors/packet-gvcp.c @ 02dbbdbf
    https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c
  * Aravis src/arvgvcpprivate.h @ 482547a3
    https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h

Sub-commands
------------
  selftest                     offline: build ACTION_CMD packets, check layout,
                               optionally write a pcap (--pcap out.pcap) that
                               Wireshark/tshark can decode.
  discover [--iface IP]        broadcast GVCP DISCOVERY, list cameras.
  probe IP [IP ...]            read GEV version, capability bits (PTP, action,
                               scheduled action), tick frequency, PTP enable +
                               status, action-queue size.             (read-only)
  ptp IP [IP ...] --enable     take control, set IEEE1588 enable bit, poll the
                               PTP status until every camera is Master/Slave and
                               exactly one is Master (or a host grandmaster).
  latch IP [IP ...]            latch each camera's timestamp N times, report
                               camera-vs-host offset and camera-vs-camera offset
                               (coarse: limited by host<->camera round trip).
  action IP [IP ...]           program device/group key + mask via bootstrap
                               registers, then send a *scheduled* ACTION_CMD
                               (action_time = latched PTP time + delay) and an
                               intentionally *late* one; report ACTION_ACK status.

Exit code 0 = all checks passed, 1 = a check failed, 2 = usage / network error.

NOTE: to make an action command actually trigger an exposure you must ALSO set
the GenICam features TriggerSelector=FrameStart, TriggerMode=On,
TriggerSource=Action1 (Action0 on some vendors) - those are not bootstrap
registers.  Use the vendor viewer, or gentl_ptp_sync_test.py in this folder.
"""
from __future__ import annotations

import argparse
import json
import random
import socket
import struct
import sys
import threading
import time

GVCP_PORT = 3956
GVCP_KEY = 0x42

# GVCP command flags (packet-gvcp.c: hf_gvcp_acknowledge_required_flag 0x01,
# hf_gvcp_scheduledactioncommand_flag_v2_0 0x80; discovery broadcast-ack 0x10)
FLAG_ACK_REQUIRED = 0x01
FLAG_DISCOVERY_BROADCAST = 0x10
FLAG_SCHEDULED_ACTION = 0x80

CMD_DISCOVERY = 0x0002
CMD_READREG = 0x0080
CMD_WRITEREG = 0x0082
CMD_ACTION = 0x0100          # packet-gvcp.c: #define GVCP_ACTION_CMD (0x0100)
ACK_ACTION = 0x0101          # packet-gvcp.c: #define GVCP_ACTION_ACK (0x0101)

# Bootstrap registers
REG_VERSION = 0x0000
REG_NUM_ACTION_SIGNALS = 0x0908
REG_ACTION_DEVICE_KEY = 0x090C
REG_GVCP_CAPABILITY = 0x0934
REG_HEARTBEAT_TIMEOUT = 0x0938
REG_TICK_FREQ_HIGH = 0x093C
REG_TICK_FREQ_LOW = 0x0940
REG_TIMESTAMP_CONTROL = 0x0944      # 1 = reset, 2 = latch (arv-gev-bootstrap.xml)
REG_TIMESTAMP_VALUE_HIGH = 0x0948
REG_TIMESTAMP_VALUE_LOW = 0x094C
REG_GVCP_CONFIGURATION = 0x0954
REG_IEEE1588_STATUS = 0x096C
REG_SCHED_ACTION_QUEUE_SIZE = 0x0970
REG_CCP = 0x0A00


def REG_ACTION_GROUP_KEY(i: int) -> int:
    return 0x9800 + 0x10 * i


def REG_ACTION_GROUP_MASK(i: int) -> int:
    return 0x9804 + 0x10 * i


# Capability bits (register 0x0934) - packet-gvcp.c hf_gvcp_capability_*
CAP_ACTION = 0x00000040
CAP_SCHEDULED_ACTION = 0x00020000
CAP_IEEE1588 = 0x00080000
CAP_UNCONDITIONAL_ACTION = 0x00100000
# Configuration bits (register 0x0954)
CFG_IEEE1588_ENABLE = 0x00080000
CFG_UNCONDITIONAL_ACTION_ENABLE = 0x00000008
# CCP
CCP_EXCLUSIVE = 0x1
CCP_CONTROL = 0x2

# IEEE1588 status (0x096C low 4 bits); SFNC 2.8 sec 27.3.5: values 1..9
PTP_STATES = {
    1: "Initializing", 2: "Faulty", 3: "Disabled", 4: "Listening",
    5: "PreMaster", 6: "Master", 7: "Passive", 8: "Uncalibrated", 9: "Slave",
}

GEV_STATUS = {
    0x0000: "SUCCESS", 0x8001: "NOT_IMPLEMENTED", 0x8002: "INVALID_PARAMETER",
    0x8003: "INVALID_ADDRESS", 0x8004: "WRITE_PROTECT", 0x8005: "BAD_ALIGNMENT",
    0x8006: "ACCESS_DENIED", 0x8007: "BUSY", 0x8013: "NO_REF_TIME",
    0x8015: "OVERFLOW", 0x8016: "ACTION_LATE", 0x8FFF: "ERROR",
}


class GvcpError(Exception):
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


# --------------------------------------------------------------------------
# Packet builders (pure functions, unit-tested by `selftest`)
# --------------------------------------------------------------------------
def gvcp_header(flags: int, cmd: int, length: int, req_id: int) -> bytes:
    # Aravis ArvGvcpHeader: packet_type(u8) packet_flags(u8) command(u16) size(u16) id(u16)
    return struct.pack(">BBHHH", GVCP_KEY, flags, cmd, length, req_id)


def build_action_cmd(device_key: int, group_key: int, group_mask: int,
                     action_time: int | None = None, req_id: int = 1,
                     ack_required: bool = True) -> bytes:
    """GVCP ACTION_CMD.  Layout per packet-gvcp.c dissect_action_cmd():
    device_key(u32) group_key(u32) group_mask(u32) [action_time(u64) if flag 0x80]."""
    flags = FLAG_ACK_REQUIRED if ack_required else 0
    payload = struct.pack(">III", device_key & 0xFFFFFFFF, group_key & 0xFFFFFFFF,
                          group_mask & 0xFFFFFFFF)
    if action_time is not None:
        flags |= FLAG_SCHEDULED_ACTION
        payload += struct.pack(">Q", action_time & 0xFFFFFFFFFFFFFFFF)
    return gvcp_header(flags, CMD_ACTION, len(payload), req_id) + payload


def parse_ack(data: bytes):
    if len(data) < 8:
        raise GvcpError("short ack (%d bytes)" % len(data))
    status, ack_cmd, length, ack_id = struct.unpack(">HHHH", data[:8])
    return status, ack_cmd, length, ack_id, data[8:8 + length]


# --------------------------------------------------------------------------
# Minimal GVCP client
# --------------------------------------------------------------------------
class Gvcp:
    def __init__(self, ip: str, iface: str = "", timeout: float = 0.5, retries: int = 3):
        self.ip = ip
        self.timeout = timeout
        self.retries = retries
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((iface, 0))
        self.sock.settimeout(timeout)
        self._id = random.randint(1, 0xFFF0)
        self._lock = threading.Lock()
        self._hb_stop = threading.Event()
        self._hb = None
        self.have_control = False

    def close(self):
        self._hb_stop.set()
        if self._hb:
            self._hb.join(2)
        if self.have_control:
            try:
                self.write_reg(REG_CCP, 0)
            except Exception:
                pass
        self.sock.close()

    def _next_id(self) -> int:
        self._id = (self._id % 0xFFFF) + 1
        return self._id

    def transact(self, flags: int, cmd: int, payload: bytes = b"") -> bytes:
        with self._lock:
            req = self._next_id()
            pkt = gvcp_header(flags | FLAG_ACK_REQUIRED, cmd, len(payload), req) + payload
            for _ in range(self.retries):
                self.sock.sendto(pkt, (self.ip, GVCP_PORT))
                deadline = time.monotonic() + self.timeout
                while time.monotonic() < deadline:
                    try:
                        data, _ = self.sock.recvfrom(2048)
                    except socket.timeout:
                        break
                    status, ack_cmd, length, ack_id, body = parse_ack(data)
                    if ack_id != req:
                        continue
                    if ack_cmd == 0x0089:  # PENDING_ACK: extend deadline
                        deadline = time.monotonic() + struct.unpack(">HH", body[:4])[1] / 1000.0 + self.timeout
                        continue
                    if status != 0:
                        raise GvcpError("%s: cmd 0x%04x -> status 0x%04x %s" % (
                            self.ip, cmd, status, GEV_STATUS.get(status, "?")), status)
                    return body
            raise GvcpError("%s: no ack for cmd 0x%04x" % (self.ip, cmd))

    def read_regs(self, *addrs: int):
        """Multi-address READREG; falls back to one READREG per address when the
        device returns fewer values (e.g. the Aravis fake camera only answers
        the first address - see arvgvfakecamera.c READ_REGISTER_CMD handler)."""
        body = self.transact(0, CMD_READREG, b"".join(struct.pack(">I", a) for a in addrs))
        if len(body) >= 4 * len(addrs):
            return list(struct.unpack(">%dI" % len(addrs), body[:4 * len(addrs)]))
        out = []
        for a in addrs:
            b = self.transact(0, CMD_READREG, struct.pack(">I", a))
            out.append(struct.unpack(">I", b[:4])[0])
        return out

    def read_reg(self, addr: int) -> int:
        return self.read_regs(addr)[0]

    def write_reg(self, addr: int, value: int):
        self.transact(0, CMD_WRITEREG, struct.pack(">II", addr, value & 0xFFFFFFFF))

    def take_control(self):
        self.write_reg(REG_CCP, CCP_CONTROL)
        self.have_control = True
        try:
            hb_ms = self.read_reg(REG_HEARTBEAT_TIMEOUT) or 3000
        except GvcpError:
            hb_ms = 3000
        period = max(0.2, hb_ms / 1000.0 / 3.0)

        def beat():
            while not self._hb_stop.wait(period):
                try:
                    self.read_reg(REG_CCP)
                except Exception:
                    pass
        self._hb = threading.Thread(target=beat, daemon=True)
        self._hb.start()

    # ---- timestamp helpers -------------------------------------------------
    def tick_frequency(self) -> int:
        hi, lo = self.read_regs(REG_TICK_FREQ_HIGH, REG_TICK_FREQ_LOW)
        return (hi << 32) | lo

    def latch(self):
        """Return (host_before_ns, host_after_ns, camera_ticks)."""
        t0 = time.time_ns()
        self.write_reg(REG_TIMESTAMP_CONTROL, 2)
        t1 = time.time_ns()
        hi, lo = self.read_regs(REG_TIMESTAMP_VALUE_HIGH, REG_TIMESTAMP_VALUE_LOW)
        return t0, t1, (hi << 32) | lo


def ticks_to_ns(ticks: int, freq: int) -> int:
    if freq <= 0:
        return ticks
    return (ticks // freq) * 1_000_000_000 + (ticks % freq) * 1_000_000_000 // freq


# --------------------------------------------------------------------------
# Sub-commands
# --------------------------------------------------------------------------
def cmd_selftest(args) -> int:
    ok = True
    p = build_action_cmd(0x12345678, 0x1, 0xFFFFFFFF, None, req_id=0x0102)
    exp = bytes.fromhex("42 01 0100 000c 0102 12345678 00000001 ffffffff".replace(" ", ""))
    ok &= _check("unscheduled ACTION_CMD bytes", p == exp, p.hex())
    p2 = build_action_cmd(0x12345678, 0x1, 0x1, 0x0000_01E2_3F5A_1000, req_id=0x0103)
    exp2 = bytes.fromhex("42810100001401031234567800000001000000010000" "01e23f5a1000")
    ok &= _check("scheduled ACTION_CMD bytes", p2 == exp2, p2.hex())
    ok &= _check("scheduled flag 0x80 set", p2[1] & 0x80 == 0x80)
    ok &= _check("length field == 20", struct.unpack(">H", p2[4:6])[0] == 20)
    ok &= _check("ticks_to_ns 125MHz", ticks_to_ns(125_000_000, 125_000_000) == 1_000_000_000)
    if args.pcap:
        _write_pcap(args.pcap, [p, p2])
        print("wrote", args.pcap, "(decode with: tshark -r FILE -V -Y gvcp)")
    return 0 if ok else 1


def _write_pcap(path: str, gvcp_payloads):
    """Write a classic pcap (LINKTYPE_RAW=101, IPv4/UDP) - no external deps."""
    def csum(b):
        if len(b) % 2:
            b += b"\0"
        s = sum(struct.unpack(">%dH" % (len(b) // 2), b))
        while s >> 16:
            s = (s & 0xFFFF) + (s >> 16)
        return (~s) & 0xFFFF
    with open(path, "wb") as f:
        f.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 101))
        for i, pl in enumerate(gvcp_payloads):
            udp = struct.pack(">HHHH", 50000, GVCP_PORT, 8 + len(pl), 0) + pl
            src, dst = socket.inet_aton("192.168.1.10"), socket.inet_aton("192.168.1.255")
            ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), i, 0, 64, 17, 0, src, dst)
            ip = ip[:10] + struct.pack(">H", csum(ip)) + ip[12:]
            pkt = ip + udp
            f.write(struct.pack("<IIII", 1_700_000_000 + i, 0, len(pkt), len(pkt)) + pkt)


def _check(name, cond, detail=""):
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))
    return bool(cond)


def cmd_discover(args) -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind((args.iface, 0))
    s.settimeout(0.3)
    pkt = gvcp_header(FLAG_ACK_REQUIRED | FLAG_DISCOVERY_BROADCAST, CMD_DISCOVERY, 0, 0xFFFF)
    for dst in (args.broadcast, "255.255.255.255"):
        try:
            s.sendto(pkt, (dst, GVCP_PORT))
        except OSError as e:
            print("send to %s failed: %s" % (dst, e))
    found = {}
    end = time.monotonic() + args.timeout
    while time.monotonic() < end:
        try:
            data, (src, _) = s.recvfrom(2048)
        except socket.timeout:
            continue
        if len(data) < 8 + 0xF8:
            continue
        pl = data[8:]
        maj, mnr = struct.unpack(">HH", pl[0:4])
        cur_ip = socket.inet_ntoa(pl[0x24:0x28])

        def txt(o, n):
            return pl[o:o + n].split(b"\0")[0].decode("ascii", "replace")
        found[src] = dict(ip=cur_ip, src=src, gev="%d.%d" % (maj, mnr),
                          manufacturer=txt(0x48, 32), model=txt(0x68, 32),
                          serial=txt(0xD8, 16), user_name=txt(0xE8, 16))
    for d in found.values():
        print(json.dumps(d))
    if not found:
        print("no GigE Vision device answered (firewall? wrong --iface?)")
        return 1
    return 0


def _probe_one(ip, iface):
    g = Gvcp(ip, iface)
    try:
        r = {"ip": ip}
        ver = g.read_reg(REG_VERSION)
        r["gev_version"] = "%d.%d" % (ver >> 16, ver & 0xFFFF)
        cap = g.read_reg(REG_GVCP_CAPABILITY)
        r["capability_raw"] = "0x%08x" % cap
        r["cap_action"] = bool(cap & CAP_ACTION)
        r["cap_scheduled_action"] = bool(cap & CAP_SCHEDULED_ACTION)
        r["cap_ieee1588"] = bool(cap & CAP_IEEE1588)
        r["cap_unconditional_action"] = bool(cap & CAP_UNCONDITIONAL_ACTION)
        r["tick_frequency_hz"] = g.tick_frequency()
        cfg = g.read_reg(REG_GVCP_CONFIGURATION)
        r["config_raw"] = "0x%08x" % cfg
        r["ptp_enabled"] = bool(cfg & CFG_IEEE1588_ENABLE)
        for key, reg in (("ptp_status", REG_IEEE1588_STATUS),
                         ("num_action_signals", REG_NUM_ACTION_SIGNALS),
                         ("scheduled_action_queue_size", REG_SCHED_ACTION_QUEUE_SIZE)):
            try:
                v = g.read_reg(reg)
                r[key] = PTP_STATES.get(v & 0xF, "raw=0x%x" % v) if key == "ptp_status" else v
            except GvcpError as e:
                r[key] = "unreadable (%s)" % GEV_STATUS.get(e.status, e)
        return r
    finally:
        g.close()


def cmd_probe(args) -> int:
    rc = 0
    for ip in args.ips:
        try:
            print(json.dumps(_probe_one(ip, args.iface)))
        except (GvcpError, OSError) as e:
            print(json.dumps({"ip": ip, "error": str(e)}))
            rc = 2
    return rc


def cmd_ptp(args) -> int:
    cams = [Gvcp(ip, args.iface) for ip in args.ips]
    try:
        for g in cams:
            cap = g.read_reg(REG_GVCP_CAPABILITY)
            if not cap & CAP_IEEE1588:
                print("%s: capability register says IEEE1588 NOT supported" % g.ip)
                return 1
            if args.enable:
                g.take_control()
                cfg = g.read_reg(REG_GVCP_CONFIGURATION)
                g.write_reg(REG_GVCP_CONFIGURATION, cfg | CFG_IEEE1588_ENABLE)
                print("%s: IEEE1588 enable bit set" % g.ip)
        t_start = time.monotonic()
        while True:
            states = {g.ip: PTP_STATES.get(g.read_reg(REG_IEEE1588_STATUS) & 0xF, "?") for g in cams}
            el = time.monotonic() - t_start
            print("t=%5.1fs %s" % (el, json.dumps(states)))
            n_master = sum(1 for s in states.values() if s == "Master")
            settled = all(s in ("Master", "Slave") for s in states.values())
            if settled and (n_master == 1 or (n_master == 0 and args.external_master)):
                print("PTP settled after %.1fs: %d camera master(s)" % (el, n_master))
                return 0
            if el > args.timeout:
                print("PTP did NOT settle within %.0fs" % args.timeout)
                return 1
            time.sleep(1.0)
    finally:
        for g in cams:
            g.close()


def cmd_latch(args) -> int:
    cams = [Gvcp(ip, args.iface) for ip in args.ips]
    try:
        freqs = {g.ip: g.tick_frequency() for g in cams}
        print("tick frequencies:", json.dumps(freqs))
        rows = []
        for _ in range(args.rounds):
            row = {}
            for g in cams:
                t0, t1, ticks = g.latch()
                cam_ns = ticks_to_ns(ticks, freqs[g.ip])
                row[g.ip] = (cam_ns - (t0 + t1) // 2, t1 - t0, cam_ns)
            rows.append(row)
        ref = cams[0].ip
        dead = [g.ip for g in cams if all(r[g.ip][2] == 0 for r in rows)]
        if dead:
            print("timestamp latch returned 0 every time on %s -> latch not implemented" % dead)
            return 1
        print("per-camera: median(camera_ns - host_midpoint_ns), median RTT")
        for g in cams:
            offs = sorted(r[g.ip][0] for r in rows)
            rtts = sorted(r[g.ip][1] for r in rows)
            print("  %-15s offset=%+.6f s  rtt=%.1f us  last_cam_time=%d ns" % (
                g.ip, offs[len(offs) // 2] / 1e9, rtts[len(rtts) // 2] / 1e3, rows[-1][g.ip][2]))
        ok = True
        for g in cams[1:]:
            d = sorted(r[g.ip][0] - r[ref][0] for r in rows)
            med = d[len(d) // 2]
            bound = max(r[g.ip][1] + r[ref][1] for r in rows)
            print("  %s vs %s: median clock difference %+d ns (resolution ~ +/-%d ns from RTT)" % (
                g.ip, ref, med, bound // 2))
            if abs(med) > args.max_diff_us * 1000:
                ok = False
        print("RESULT:", "clocks agree within %d us" % args.max_diff_us if ok else "clocks DIFFER")
        return 0 if ok else 1
    finally:
        for g in cams:
            g.close()


def cmd_action(args) -> int:
    cams = [Gvcp(ip, args.iface) for ip in args.ips]
    rc = 0
    try:
        for g in cams:
            cap = g.read_reg(REG_GVCP_CAPABILITY)
            print("%s: action=%s scheduled=%s ieee1588=%s" % (
                g.ip, bool(cap & CAP_ACTION), bool(cap & CAP_SCHEDULED_ACTION), bool(cap & CAP_IEEE1588)))
            g.take_control()
            g.write_reg(REG_ACTION_DEVICE_KEY, args.device_key)
            g.write_reg(REG_ACTION_GROUP_KEY(args.action_index), args.group_key)
            g.write_reg(REG_ACTION_GROUP_MASK(args.action_index), args.group_mask)
        freq = cams[0].tick_frequency()
        _, _, now_ticks = cams[0].latch()
        delay_ticks = args.delay_ms * freq // 1000
        tests = [("scheduled (+%d ms)" % args.delay_ms, now_ticks + delay_ticks),
                 ("late (-1 s)", max(1, now_ticks - freq)),
                 ("unscheduled", None)]
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind((args.iface, 0))
        s.settimeout(0.3)
        for name, t in tests:
            req = random.randint(1, 0xFFFF)
            pkt = build_action_cmd(args.device_key, args.group_key, args.group_mask, t, req_id=req)
            s.sendto(pkt, (args.dest, GVCP_PORT))
            acks = {}
            end = time.monotonic() + 1.0
            while time.monotonic() < end:
                try:
                    data, (src, _) = s.recvfrom(2048)
                except socket.timeout:
                    continue
                try:
                    status, ack_cmd, _, ack_id, _ = parse_ack(data)
                except GvcpError:
                    continue
                if ack_cmd == ACK_ACTION and ack_id == req:
                    acks[src] = "0x%04x %s" % (status, GEV_STATUS.get(status, "?"))
            print("%-22s action_time=%s acks=%s" % (name, t, json.dumps(acks)))
            missing = [g.ip for g in cams if g.ip not in acks]
            if missing:
                print("   no ACTION_ACK from", missing)
                rc = 1
        return rc
    finally:
        for g in cams:
            g.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default="", help="local IPv4 address of the NIC facing the cameras")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("selftest"); p.add_argument("--pcap")
    p = sp.add_parser("discover"); p.add_argument("--broadcast", default="255.255.255.255")
    p.add_argument("--timeout", type=float, default=2.0)
    p = sp.add_parser("probe"); p.add_argument("ips", nargs="+")
    p = sp.add_parser("ptp"); p.add_argument("ips", nargs="+")
    p.add_argument("--enable", action="store_true")
    p.add_argument("--timeout", type=float, default=60)
    p.add_argument("--external-master", action="store_true",
                   help="accept all-Slave (host/grandmaster such as ptp4l is master)")
    p = sp.add_parser("latch"); p.add_argument("ips", nargs="+")
    p.add_argument("--rounds", type=int, default=50)
    p.add_argument("--max-diff-us", type=int, default=1000)
    p = sp.add_parser("action"); p.add_argument("ips", nargs="+")
    p.add_argument("--dest", default="255.255.255.255", help="broadcast or unicast IP for ACTION_CMD")
    p.add_argument("--device-key", type=lambda x: int(x, 0), default=0x12345678)
    p.add_argument("--group-key", type=lambda x: int(x, 0), default=1)
    p.add_argument("--group-mask", type=lambda x: int(x, 0), default=1)
    p.add_argument("--action-index", type=int, default=0, help="0 => Action1 group key/mask registers")
    p.add_argument("--delay-ms", type=int, default=500)
    args = ap.parse_args(argv)
    try:
        return {"selftest": cmd_selftest, "discover": cmd_discover, "probe": cmd_probe,
                "ptp": cmd_ptp, "latch": cmd_latch, "action": cmd_action}[args.cmd](args)
    except (GvcpError, OSError) as e:
        print("ERROR:", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
