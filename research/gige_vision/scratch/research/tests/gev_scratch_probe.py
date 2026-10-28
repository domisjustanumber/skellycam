#!/usr/bin/env python3
"""
gev_scratch_probe.py -- a from-scratch, pure-Python (stdlib only) GigE Vision
client used to (a) size the "minimum protocol surface" for SkellyCam and
(b) probe a real camera's PTP / action-command / streaming capabilities.

It implements, with no vendor SDK and no Aravis:
  * GVCP DISCOVERY (unicast or broadcast) + parse of the 248-byte DISCOVERY_ACK
  * READREG / WRITEREG / READMEM / WRITEMEM with retries and PENDING_ACK
  * Control Channel Privilege (CCP @0x0A00) + heartbeat thread (timeout @0x0938)
  * GenICam XML fetch from the First URL register (@0x0200), "Local:" scheme, zip
  * A *toy* GenApi resolver (Integer/IntReg/MaskedIntReg/Command/Enumeration/
    Boolean + a whitelisted IntSwissKnife evaluator) -- deliberately partial,
    to show where the hard part is. If the official EMVA `genicam` wheel is
    installed (pip install genicam) it is used instead via genapi.AbstractPort.
  * Stream channel 0 setup (SCP0 @0x0D00 port, 0x0D04 packet size, 0x0D18 dest)
  * Optional test-packet probe (0x0D04 bit31 fire-test + bit30 do-not-fragment)
  * GVSP receive (standard + extended 64-bit IDs), out-of-order reassembly,
    missing-packet detection, PACKETRESEND_CMD
  * Read-only PTP/IEEE1588 + action-command bootstrap capability probe and
    timestamp latch (0x0934, 0x0954, 0x096C, 0x0974..0x097C, 0x0944..0x094C)

Register offsets follow the GigE Vision bootstrap map as implemented in Aravis
(src/arvgvcpprivate.h) and the Wireshark GVCP dissector (packet-gvcp.c).

Usage
  python -I gev_scratch_probe.py --target 192.168.1.50            # unicast
  python -I gev_scratch_probe.py --broadcast --iface 192.168.1.10 # discovery
  python -I gev_scratch_probe.py --target 127.0.0.1 --stream-seconds 3 --json out.json

Safety: the probe takes CCP control while streaming, writes only SCP0
destination/packet-size registers and AcquisitionStart/Stop, and releases
control on exit. It never writes persistent IP or user-set registers.
Exit code 0 = all mandatory checks passed.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import operator
import re
import socket
import struct
import sys
import threading
import time
import zipfile
import xml.etree.ElementTree as ET

GVCP_PORT = 3956
# --- GVCP commands (Wireshark packet-gvcp.c L177-L197; Aravis arvgvcpprivate.h)
DISCOVERY_CMD, DISCOVERY_ACK = 0x0002, 0x0003
FORCEIP_CMD = 0x0004
PACKETRESEND_CMD = 0x0040
READREG_CMD, READREG_ACK = 0x0080, 0x0081
WRITEREG_CMD, WRITEREG_ACK = 0x0082, 0x0083
READMEM_CMD, READMEM_ACK = 0x0084, 0x0085
WRITEMEM_CMD, WRITEMEM_ACK = 0x0086, 0x0087
PENDING_ACK = 0x0089
ACTION_CMD, ACTION_ACK = 0x0100, 0x0101
FLAG_ACK_REQUIRED = 0x01
FLAG_DISCOVERY_ALLOW_BROADCAST_ACK = 0x10
FLAG_EXTENDED_IDS = 0x10
FLAG_SCHEDULED_ACTION = 0x80
# --- bootstrap registers
REG_VERSION = 0x0000
REG_FIRST_URL = 0x0200
REG_N_STREAM_CHANNELS = 0x0904
REG_N_ACTION_SIGNALS = 0x0908
REG_GVCP_CAPABILITY = 0x0934
REG_HEARTBEAT_TIMEOUT = 0x0938
REG_TS_TICK_HIGH, REG_TS_TICK_LOW = 0x093C, 0x0940
REG_TS_CONTROL = 0x0944
REG_TS_VALUE_HIGH, REG_TS_VALUE_LOW = 0x0948, 0x094C
REG_GVCP_CONFIGURATION = 0x0954
REG_GVSP_CONFIGURATION = 0x0960
REG_IEEE1588_STATUS = 0x096C
REG_SCHED_ACTION_QUEUE = 0x0970
REG_IEEE1588_EXT_CAP = 0x0974
REG_IEEE1588_SUPPORTED_PROFILES = 0x0978
REG_IEEE1588_SELECTED_PROFILE = 0x097C
REG_CCP = 0x0A00
REG_SCP0_PORT = 0x0D00
REG_SCP0_PACKET_SIZE = 0x0D04
REG_SCP0_DEST = 0x0D18
CCP_CONTROL, CCP_EXCLUSIVE = 0x2, 0x1
SCPS_FIRE_TEST, SCPS_DO_NOT_FRAGMENT = 0x80000000, 0x40000000
# capability bits (Wireshark packet-gvcp.c hf_gvcp_capability_* masks)
CAP_BITS = {
    "user_defined_name": 0x80000000, "serial_number": 0x40000000, "heartbeat_disable": 0x20000000,
    "link_speed": 0x10000000, "ccp_application_port_ip": 0x08000000, "manifest_table": 0x04000000,
    "test_data": 0x02000000, "discovery_ack_delay": 0x01000000, "writable_discovery_ack_delay": 0x00800000,
    "extended_status_codes_v1_1": 0x00400000, "primary_application_switchover": 0x00200000,
    "unconditional_action": 0x00100000, "ieee1588": 0x00080000, "extended_status_codes_v2_0": 0x00040000,
    "scheduled_action": 0x00020000, "ieee1588_extended_capabilities": 0x00010000,
    "action": 0x00000040, "pending_ack": 0x00000020, "event_data": 0x00000010, "event": 0x00000008,
    "packet_resend": 0x00000004, "write_mem": 0x00000002, "concatenation": 0x00000001,
}
# --- GVSP
GVSP_LEADER, GVSP_TRAILER, GVSP_PAYLOAD, GVSP_ALLIN = 1, 2, 3, 4
PAYLOAD_TYPES = {1: "image (uncompressed, PFNC pixel format)", 2: "raw data", 3: "file", 4: "chunk data",
                 6: "JPEG", 7: "JPEG2000", 8: "H.264", 9: "multizone image", 10: "multipart", 11: "GenDC"}
IP_UDP = 20 + 8


class GvcpError(RuntimeError):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


# =========================================================================== GVCP
def _cmd(command, payload=b"", req_id=1, flags=FLAG_ACK_REQUIRED):
    return struct.pack(">BBHHH", 0x42, flags, command, len(payload), req_id) + payload


def parse_discovery_ack(p: bytes, src: str) -> dict:
    """Payload layout per Wireshark dissect_discovery_ack (packet-gvcp.c)."""
    def s(off, n):
        return p[off:off + n].split(b"\0", 1)[0].decode("ascii", "replace")
    ver = struct.unpack_from(">I", p, 0)[0]
    return dict(
        src=src, version=f"{ver >> 16}.{ver & 0xFFFF}",
        device_mode=hex(struct.unpack_from(">I", p, 4)[0]),
        mac=":".join(f"{b:02x}" for b in p[10:16]),
        ip_config_supported=hex(struct.unpack_from(">I", p, 16)[0]),
        ip_config_current=hex(struct.unpack_from(">I", p, 20)[0]),
        ip=socket.inet_ntoa(p[36:40]), mask=socket.inet_ntoa(p[52:56]), gateway=socket.inet_ntoa(p[68:72]),
        manufacturer=s(72, 32), model=s(104, 32), device_version=s(136, 32),
        manufacturer_info=s(168, 48), serial=s(216, 16), user_name=s(232, 16))


def discover(target=None, iface="0.0.0.0", timeout=1.0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind((iface, 0))
    sock.settimeout(0.1)
    dst = target or "255.255.255.255"
    sock.sendto(_cmd(DISCOVERY_CMD, b"", 0xFFFF, FLAG_ACK_REQUIRED | FLAG_DISCOVERY_ALLOW_BROADCAST_ACK),
                (dst, GVCP_PORT))
    found, t_end = [], time.time() + timeout
    while time.time() < t_end:
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        status, answer, length, ack_id = struct.unpack_from(">HHHH", data)
        if answer == DISCOVERY_ACK and status == 0:
            found.append(parse_discovery_ack(data[8:8 + length], addr[0]))
    sock.close()
    return found


class Gvcp:
    """Single-outstanding-request GVCP client (the spec requires one command in flight per channel)."""

    def __init__(self, ip, timeout=0.5, retries=3):
        self.ip, self.timeout, self.retries = ip, timeout, retries
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.connect((ip, GVCP_PORT))
        self.sock.settimeout(timeout)
        self.local_ip = self.sock.getsockname()[0]
        self.lock = threading.Lock()
        self.req_id = 0
        self.stats = dict(commands=0, retries=0, pending_acks=0)
        self._hb_stop = threading.Event()
        self._hb = None
        self.control_lost = False

    def _next_id(self):
        self.req_id = 1 if self.req_id >= 0xFFFF else self.req_id + 1  # 0 is invalid
        return self.req_id

    def transact(self, command, payload, expect):
        with self.lock:
            rid = self._next_id()
            pkt = _cmd(command, payload, rid)
            self.stats["commands"] += 1
            for attempt in range(self.retries):
                if attempt:
                    self.stats["retries"] += 1
                self.sock.send(pkt)
                deadline = time.time() + self.timeout
                while True:
                    try:
                        self.sock.settimeout(max(0.001, deadline - time.time()))
                        data = self.sock.recv(2048)
                    except socket.timeout:
                        break
                    status, answer, length, ack_id = struct.unpack_from(">HHHH", data)
                    if ack_id != rid:
                        continue  # stale ack from an earlier retry
                    if answer == PENDING_ACK:  # device asks us to wait longer
                        ms = struct.unpack_from(">HH", data, 8)[1]
                        self.stats["pending_acks"] += 1
                        deadline = time.time() + ms / 1000 + self.timeout
                        continue
                    if status != 0:
                        raise GvcpError(f"cmd 0x{command:04x} status 0x{status:04x}", status)
                    if answer != expect:
                        raise GvcpError(f"unexpected answer 0x{answer:04x}")
                    return data[8:8 + length]
            raise GvcpError(f"timeout on cmd 0x{command:04x}")

    def read_regs(self, *addrs):
        d = self.transact(READREG_CMD, b"".join(struct.pack(">I", a) for a in addrs), READREG_ACK)
        return list(struct.unpack(f">{len(addrs)}I", d[:4 * len(addrs)]))

    def read_reg(self, addr):
        return self.read_regs(addr)[0]

    def write_reg(self, addr, value):
        self.transact(WRITEREG_CMD, struct.pack(">II", addr, value & 0xFFFFFFFF), WRITEREG_ACK)

    def read_mem(self, addr, size, chunk=512):
        out = bytearray()
        while size > 0:
            n = min(chunk, size)
            n4 = (n + 3) & ~3  # READMEM count must be a multiple of 4
            d = self.transact(READMEM_CMD, struct.pack(">IHH", addr, 0, n4), READMEM_ACK)
            out += d[4:4 + n]
            addr += n
            size -= n
        return bytes(out)

    def write_mem(self, addr, data: bytes):
        for i in range(0, len(data), 512):
            self.transact(WRITEMEM_CMD, struct.pack(">I", addr + i) + data[i:i + 512], WRITEMEM_ACK)

    # -- control channel privilege + heartbeat
    def take_control(self, exclusive=False):
        self.write_reg(REG_CCP, CCP_CONTROL | (CCP_EXCLUSIVE if exclusive else 0))
        hb_ms = self.read_reg(REG_HEARTBEAT_TIMEOUT)
        period = max(0.05, hb_ms / 1000 / 3)  # Aravis uses a fixed 1 s; pyGigEVision 2 s

        def loop():
            while not self._hb_stop.wait(period):
                try:
                    if (self.read_reg(REG_CCP) & (CCP_CONTROL | CCP_EXCLUSIVE)) == 0:
                        self.control_lost = True
                except (GvcpError, OSError):
                    pass
        self._hb = threading.Thread(target=loop, daemon=True)
        self._hb.start()
        return hb_ms, period

    def release(self):
        self._hb_stop.set()
        if self._hb:
            self._hb.join(2)
        try:
            self.write_reg(REG_CCP, 0)
        except (GvcpError, OSError):
            pass
        self.sock.close()


def send_action(dest_ip, device_key, group_key, group_mask, scheduled_ticks=None, iface="0.0.0.0", wait=0.2):
    """ACTION_CMD (0x0100) payload per Wireshark dissect_action_cmd: device_key, group_key, group_mask
    [, 64-bit action time when header flag 0x80 is set]. Usually broadcast to all cameras."""
    payload = struct.pack(">III", device_key, group_key, group_mask)
    flags = FLAG_ACK_REQUIRED
    if scheduled_ticks is not None:
        payload += struct.pack(">Q", scheduled_ticks)
        flags |= FLAG_SCHEDULED_ACTION
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind((iface, 0))
    s.settimeout(0.05)
    s.sendto(_cmd(ACTION_CMD, payload, 1, flags), (dest_ip, GVCP_PORT))
    acks, t_end = [], time.time() + wait
    while time.time() < t_end:
        try:
            d, a = s.recvfrom(64)
            acks.append((a[0], struct.unpack_from(">HH", d)))
        except socket.timeout:
            pass
    s.close()
    return acks


# =========================================================================== GenICam XML
def parse_url(url: str):
    """'Local:[///]name.xml;ADDR;SIZE' (hex, optional 0x). Aravis fake camera uses Local:///."""
    m = re.match(r"(?i)local:(?:///)?([^;]+);(?:0x)?([0-9a-f]+);(?:0x)?([0-9a-f]+)", url.strip())
    if not m:
        return None
    return m.group(1), int(m.group(2), 16), int(m.group(3), 16)


def fetch_xml(g: Gvcp):
    raw = g.read_mem(REG_FIRST_URL, 512).split(b"\0", 1)[0].decode("ascii", "replace")
    parsed = parse_url(raw)
    if not parsed:
        raise GvcpError(f"unsupported URL scheme: {raw!r} (file:/http: need host-side lookup)")
    name, addr, size = parsed
    blob = g.read_mem(addr, size)
    if name.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            blob = z.read(z.namelist()[0])
    return raw, name, blob


# =========================================================================== toy GenApi
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.floordiv,
        ast.Mod: operator.mod, ast.LShift: operator.lshift, ast.RShift: operator.rshift,
        ast.BitAnd: operator.and_, ast.BitOr: operator.or_, ast.BitXor: operator.xor, ast.Pow: operator.pow}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
        ast.Gt: operator.gt, ast.GtE: operator.ge}


def translate_formula(f: str) -> str:
    """GenICam SwissKnife syntax -> Python expression subset. Supports arithmetic, bit ops,
    comparisons (= and <>), && || ! and ?: (single level). Functions (SGN, ABS, ...) unsupported."""
    f = " ".join(f.split())  # formulas are often multi-line in XML
    f = f.replace("&&", " and ").replace("||", " or ").replace("<>", "!=")
    f = re.sub(r"(?<![<>!=])=(?!=)", "==", f)
    f = re.sub(r"!(?!=)", " not ", f)
    f = f.replace("~", " ~")
    if "?" in f:
        m = re.fullmatch(r"\s*\(?(.+?)\)?\s*\?\s*(.+?)\s*:\s*(.+)\s*", f, re.S)
        if not m or "?" in m.group(2) or "?" in m.group(3):
            raise ValueError("nested ?:")
        f = f"(({m.group(2)}) if ({m.group(1)}) else ({m.group(3)}))"
    return f


def eval_formula(expr: str, variables: dict):
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name):
            return variables[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            return _BIN[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            return {ast.USub: lambda: -v, ast.UAdd: lambda: v, ast.Not: lambda: int(not v),
                    ast.Invert: lambda: ~v}[type(n.op)]()
        if isinstance(n, ast.BoolOp):
            vals = [ev(x) for x in n.values]
            return int(all(vals)) if isinstance(n.op, ast.And) else int(any(vals))
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in _CMP:
            return int(_CMP[type(n.ops[0])](ev(n.left), ev(n.comparators[0])))
        if isinstance(n, ast.IfExp):
            return ev(n.body) if ev(n.test) else ev(n.orelse)
        raise ValueError(f"unsupported syntax {type(n).__name__}")
    return ev(ast.parse(translate_formula(expr), mode="eval"))


class ToyNodeMap:
    """Deliberately minimal GenApi: enough for Width/Height/PixelFormat/AcquisitionStart on simple XMLs.
    Missing on purpose: pIsAvailable/pIsLocked, selectors, caching/pInvalidator, Float Converter
    (FormulaTo/From), StructReg, pAddress/pIndex/IntSwissKnife-addressed registers, multiple ports,
    chunk/event adapters, schema validation, namespaces/Extension, TLParamsLocked semantics ..."""

    def __init__(self, xml_bytes: bytes, port: Gvcp):
        root = ET.fromstring(xml_bytes)
        self.nodes = {}
        self._collect(root)
        self.port = port
        self.unsupported = set()

    def _collect(self, e):
        for ch in e:
            tag = ch.tag.split("}")[-1]
            if tag == "Group":
                self._collect(ch)
            elif ch.get("Name"):
                self.nodes[ch.get("Name")] = (tag, ch)

    @staticmethod
    def _t(e, name):
        x = e.find(f"{{*}}{name}") if e.tag.startswith("{") else e.find(name)
        return None if x is None else x.text.strip()

    def _int(self, s):
        return int(s, 0)

    def get(self, name):
        tag, e = self.nodes[name]
        t = lambda k: self._t(e, k)
        if tag in ("IntReg", "MaskedIntReg"):
            addr = self._int(t("Address"))
            ln = int(t("Length"))
            raw = self.port.read_mem(addr, ln)
            big = (t("Endianess") or "LittleEndian") == "BigEndian"
            v = int.from_bytes(raw, "big" if big else "little")
            if tag == "MaskedIntReg":
                # GenApi bit numbering: for BigEndian registers bit 0 is the MSB of the register,
                # e.g. Hikrobot IEEE1588Status_Reg @0x096C LSB=31 MSB=28 == mask 0x0000000F (Wireshark).
                nbits = 8 * ln
                if t("Bit") is not None:
                    b = int(t("Bit"))
                    return (v >> ((nbits - 1 - b) if big else b)) & 1
                lsb, msb = int(t("LSB")), int(t("MSB"))
                shift, width = ((nbits - 1 - lsb), lsb - msb + 1) if big else (lsb, msb - lsb + 1)
                return (v >> shift) & ((1 << width) - 1)
            if (t("Sign") or "Unsigned") == "Signed" and v >> (8 * ln - 1):
                v -= 1 << (8 * ln)
            return v
        if tag in ("Integer", "Boolean", "Enumeration", "Command"):
            if t("pValue"):
                return self.get(t("pValue"))
            if t("Value"):
                return self._int(t("Value"))
        if tag == "IntSwissKnife":
            vars_ = {}
            for pv in e:
                if pv.tag.split("}")[-1] == "pVariable":
                    vars_[pv.get("Name")] = self.get(pv.text.strip())
            return eval_formula(t("Formula"), vars_)
        self.unsupported.add(tag)
        raise NotImplementedError(f"toy GenApi cannot evaluate <{tag}> {name}")

    def set(self, name, value):
        tag, e = self.nodes[name]
        t = lambda k: self._t(e, k)
        if tag == "IntReg":
            ln = int(t("Length"))
            big = (t("Endianess") or "LittleEndian") == "BigEndian"
            self.port.write_mem(self._int(t("Address")), int(value).to_bytes(ln, "big" if big else "little"))
            return
        if tag == "Command":
            return self.set(t("pValue"), self._int(t("CommandValue")))
        if tag in ("Integer", "Enumeration", "Boolean") and t("pValue"):
            if tag == "Enumeration" and isinstance(value, str):
                for ent in e:
                    if ent.get("Name") == value:
                        value = self._int(self._t(ent, "Value"))
            return self.set(t("pValue"), value)
        self.unsupported.add(tag)
        raise NotImplementedError(f"toy GenApi cannot write <{tag}> {name}")


_KEEPALIVE = []


def official_nodemap(xml_bytes: bytes, g: Gvcp):
    """Use the EMVA reference GenApi (pip install genicam) through AbstractPort,
    mirroring harvesters/_private/core/port.py ConcretePort."""
    from genicam.genapi import NodeMap, AbstractPort, EAccessMode  # type: ignore

    class GvcpPort(AbstractPort):
        def __init__(self):
            super().__init__()

        def is_open(self):
            return True

        def read(self, address, length):
            return g.read_mem(address, length)

        def write(self, address, value):
            g.write_mem(address, bytes(value))

        def open(self, _):
            pass

        def close(self):
            pass

        def get_access_mode(self):
            return EAccessMode.RW

    nm = NodeMap()
    nm.load_xml_from_string(xml_bytes.decode("utf-8", "replace"))
    port = GvcpPort()
    nm.connect(port, "Device")
    _KEEPALIVE.append(port)  # NodeMap.__setattr__ maps attributes to features, so keep the port here
    return nm


# =========================================================================== GVSP
class Frame:
    __slots__ = ("block_id", "buf", "got", "n_expected", "leader", "trailer", "t0", "resend_sent", "payload")


def receive_stream(g: Gvcp, sock: socket.socket, seconds: float, packet_size: int, payload_size: int,
                   resend: bool = True, initial_timeout=0.02):
    """Minimal GVSP reassembler: places each data packet at (packet_id-1)*chunk in a preallocated buffer,
    tracks received ids, and on trailer (or timeout) requests PACKETRESEND for gaps."""
    frames = {}
    done = []
    stats = dict(packets=0, bytes=0, leaders=0, trailers=0, data=0, extended_id_packets=0, resend_cmds=0,
                 frames_complete=0, frames_incomplete=0, missing_packets=0, out_of_order=0, other=0,
                 payload_types={}, pixel_formats={}, timestamps=[])
    scratch = bytearray(65536)
    smv = memoryview(scratch)
    t_end = time.time() + seconds
    last_pid = {}
    sock.settimeout(0.05)
    resend_id = 0x8000

    def close(fr, reason):
        miss = [i for i in range(1, fr.n_expected + 1) if not fr.got[i]] if fr.n_expected else []
        if resend and miss and fr.resend_sent == 0 and reason == "trailer":
            # group consecutive missing ids into ranges -> one PACKETRESEND each (Aravis does the same)
            ranges, start = [], miss[0]
            for a, b in zip(miss, miss[1:] + [None]):
                if b != a + 1:
                    ranges.append((start, a))
                    start = b
            for first, last in ranges:
                nonlocal_resend(fr.block_id, first, last)
            fr.resend_sent = len(ranges)
            return False  # keep frame open a little longer for resent packets
        stats["missing_packets"] += len(miss)
        stats["frames_complete" if not miss else "frames_incomplete"] += 1
        done.append(dict(block_id=fr.block_id, missing=len(miss), leader=fr.leader))
        return True

    def nonlocal_resend(block_id, first, last):
        nonlocal resend_id
        resend_id = resend_id + 1 if resend_id < 0xFFFF else 1
        if block_id > 0xFFFF:  # extended ids
            payload = struct.pack(">IIIQ", 0, first, last, block_id)
            flags = FLAG_EXTENDED_IDS
        else:
            payload = struct.pack(">HHII", 0, block_id, first & 0xFFFFFF, last & 0xFFFFFF)
            flags = 0  # resend is fire-and-forget (no ack flag), as in Aravis
        sock.sendto(_cmd(PACKETRESEND_CMD, payload, resend_id, flags), (g.ip, GVCP_PORT))
        stats["resend_cmds"] += 1

    while time.time() < t_end:
        try:
            n = sock.recv_into(scratch)
        except socket.timeout:
            n = 0
        now = time.time()
        if n:
            stats["packets"] += 1
            stats["bytes"] += n
            status, w1, infos = struct.unpack_from(">HHI", scratch, 0)
            ext = bool(infos & 0x80000000)
            ctype = (infos >> 24) & 0x7F
            if ext:
                block_id, pid = struct.unpack_from(">QI", scratch, 8)
                hdr = 20
                stats["extended_id_packets"] += 1
            else:
                block_id, pid, hdr = w1, infos & 0xFFFFFF, 8
            chunk = packet_size - IP_UDP - hdr
            fr = frames.get(block_id)
            if fr is None:
                fr = frames[block_id] = Frame()
                fr.block_id, fr.leader, fr.trailer, fr.t0, fr.resend_sent = block_id, None, None, now, 0
                fr.n_expected = (payload_size + chunk - 1) // chunk
                fr.buf = bytearray(fr.n_expected * chunk)
                fr.got = bytearray(fr.n_expected + 2)
            if pid < last_pid.get(block_id, -1):
                stats["out_of_order"] += 1
            last_pid[block_id] = pid
            if ctype == GVSP_LEADER:
                stats["leaders"] += 1
                _, ptype, ts_hi, ts_lo = struct.unpack_from(">HHII", scratch, hdr)
                ptype &= 0x3FFF  # 0x4000 = extended chunk flag
                info = dict(payload_type=ptype, payload_type_name=PAYLOAD_TYPES.get(ptype, hex(ptype)),
                            timestamp_ticks=(ts_hi << 32) | ts_lo)
                if ptype == 1:
                    pf, w, h = struct.unpack_from(">III", scratch, hdr + 12)
                    info.update(pixel_format=hex(pf), width=w, height=h,
                                bits_per_pixel=(pf >> 16) & 0xFF)
                    stats["pixel_formats"][hex(pf)] = stats["pixel_formats"].get(hex(pf), 0) + 1
                stats["payload_types"][info["payload_type_name"]] = \
                    stats["payload_types"].get(info["payload_type_name"], 0) + 1
                if len(stats["timestamps"]) < 1000:
                    stats["timestamps"].append(info["timestamp_ticks"])
                fr.leader = info
            elif ctype == GVSP_PAYLOAD:
                stats["data"] += 1
                if 1 <= pid <= fr.n_expected:
                    off = (pid - 1) * chunk
                    ln = min(n - hdr, len(fr.buf) - off)
                    fr.buf[off:off + ln] = smv[hdr:hdr + ln]
                    fr.got[pid] = 1
            elif ctype == GVSP_TRAILER:
                stats["trailers"] += 1
                fr.trailer = now
                if close(fr, "trailer"):
                    del frames[block_id]
                continue
            else:
                stats["other"] += 1
        # timeouts: frames waiting on resends, or whose trailer was lost
        for bid in list(frames):
            fr = frames[bid]
            if (fr.trailer and now - fr.trailer > 0.05) or now - fr.t0 > 1.0:
                fr.resend_sent = max(fr.resend_sent, 1)
                close(fr, "timeout")
                del frames[bid]
    stats["frames_seen"] = len(done)
    return stats, done


# =========================================================================== main probe
def udp_rcvbuf_errors():
    """Linux only: kernel counter of UDP datagrams dropped because a socket receive buffer was full."""
    try:
        with open("/proc/net/snmp") as f:
            lines = [l.split() for l in f if l.startswith("Udp:")]
        return int(lines[1][lines[0].index("RcvbufErrors")])
    except (OSError, ValueError, IndexError):
        return None


def bits(v, table):
    return sorted(k for k, m in table.items() if v & m)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", help="camera IP for unicast discovery/control")
    ap.add_argument("--broadcast", action="store_true", help="broadcast discovery on --iface")
    ap.add_argument("--iface", default="0.0.0.0", help="local interface IP for discovery")
    ap.add_argument("--stream-seconds", type=float, default=0.0, help="0 = do not stream")
    ap.add_argument("--packet-size", type=int, default=0, help="SCPS packet size (0 = keep camera value)")
    ap.add_argument("--test-packet", action="store_true", help="probe packet size with fire-test + DF bit")
    ap.add_argument("--no-resend", action="store_true")
    ap.add_argument("--rcvbuf", type=int, default=16 << 20, help="GVSP socket SO_RCVBUF request")
    ap.add_argument("--force-rcvbuf", action="store_true",
                    help="Linux: SO_RCVBUFFORCE (CAP_NET_ADMIN) to bypass net.core.rmem_max")
    ap.add_argument("--official-genapi", action="store_true", help="require the `genicam` wheel")
    ap.add_argument("--json", help="write results to JSON")
    ap.add_argument("--action", metavar="DEVKEY:GROUPKEY:GROUPMASK",
                    help="send ONE unconditional ACTION_CMD (hex ok) to --target and report ACKs. "
                         "Only has an effect if the camera was configured (ActionDeviceKey/ActionGroupKey/"
                         "ActionGroupMask + TriggerSource=Action1)")
    a = ap.parse_args()
    R = dict(ok=[], fail=[], skipped=[])

    def check(name, cond, detail=""):
        (R["ok"] if cond else R["fail"]).append(f"{name} {detail}".strip())
        print(("  PASS " if cond else "  FAIL ") + name, detail)

    print("== discovery")
    devs = discover(a.target if not a.broadcast else None, a.iface)
    for d in devs:
        print("  ", d)
    R["devices"] = devs
    check("discovery found >=1 device", bool(devs))
    if not devs:
        return finish(R, a)
    ip = a.target or devs[0]["ip"]

    g = Gvcp(ip)
    print("== bootstrap registers")
    ver = g.read_reg(REG_VERSION)
    cap = g.read_reg(REG_GVCP_CAPABILITY)
    hb = g.read_reg(REG_HEARTBEAT_TIMEOUT)
    nsc = g.read_reg(REG_N_STREAM_CHANNELS)
    tick = (g.read_reg(REG_TS_TICK_HIGH) << 32) | g.read_reg(REG_TS_TICK_LOW)
    R["bootstrap"] = dict(version=f"{ver >> 16}.{ver & 0xFFFF}", capability=hex(cap),
                          capability_bits=bits(cap, CAP_BITS), heartbeat_timeout_ms=hb,
                          n_stream_channels=nsc, timestamp_tick_hz=tick)
    print("  ", R["bootstrap"])
    check("READREG works", True)

    print("== PTP / IEEE 1588 / action capability (read-only)")
    ptp = dict(ieee1588_supported=bool(cap & CAP_BITS["ieee1588"]),
               scheduled_action_supported=bool(cap & CAP_BITS["scheduled_action"]),
               action_supported=bool(cap & CAP_BITS["action"]))
    try:
        cfg = g.read_reg(REG_GVCP_CONFIGURATION)
        ptp["gvcp_configuration"] = hex(cfg)
        ptp["ieee1588_enabled"] = bool(cfg & 0x00080000)
    except GvcpError as e:
        ptp["gvcp_configuration_error"] = str(e)
    if ptp["ieee1588_supported"]:
        for nm, reg in [("ieee1588_status", REG_IEEE1588_STATUS), ("ext_cap", REG_IEEE1588_EXT_CAP),
                        ("supported_profiles", REG_IEEE1588_SUPPORTED_PROFILES),
                        ("selected_profile", REG_IEEE1588_SELECTED_PROFILE)]:
            try:
                ptp[nm] = hex(g.read_reg(reg))
            except GvcpError as e:
                ptp[nm] = f"error {e}"
        if "ieee1588_status" in ptp and ptp["ieee1588_status"].startswith("0x"):
            st = int(ptp["ieee1588_status"], 16) & 0xF
            ptp["clock_state"] = {1: "Initializing", 2: "Faulty", 3: "Disabled", 4: "Listening",
                                  5: "PreMaster", 6: "Master", 7: "Passive", 8: "Uncalibrated",
                                  9: "Slave"}.get(st, f"state {st}")
    if ptp["action_supported"]:
        try:
            ptp["n_action_signals"] = g.read_reg(REG_N_ACTION_SIGNALS)
        except GvcpError as e:
            ptp["n_action_signals"] = f"error {e}"
    if ptp["scheduled_action_supported"]:
        try:
            ptp["scheduled_action_queue"] = g.read_reg(REG_SCHED_ACTION_QUEUE)
        except GvcpError as e:
            ptp["scheduled_action_queue"] = f"error {e}"
    R["ptp"] = ptp
    print("  ", ptp)

    print("== GenICam XML")
    url, name, xml = fetch_xml(g)
    R["xml"] = dict(url=url, name=name, bytes=len(xml))
    print(f"   url={url!r} -> {len(xml)} bytes")
    check("XML fetched via READMEM", xml.lstrip().startswith(b"<?xml") or b"<RegisterDescription" in xml[:4096])

    print("== control channel privilege + heartbeat")
    hb_ms, period = g.take_control()
    ccp = g.read_reg(REG_CCP)
    check("CCP control acquired", bool(ccp & CCP_CONTROL), f"(CCP=0x{ccp:x}, hb={hb_ms} ms, period={period:.2f}s)")

    # timestamp latch: write TimestampControl.latch then read value (needs control)
    try:
        g.write_reg(REG_TS_CONTROL, 0x2)
        ts = (g.read_reg(REG_TS_VALUE_HIGH) << 32) | g.read_reg(REG_TS_VALUE_LOW)
        R["ptp"]["latched_timestamp_ticks"] = ts
        R["ptp"]["host_time_at_latch_ns"] = time.time_ns()
        print(f"   latched device timestamp = {ts} ticks ({ts / tick if tick else float('nan'):.6f} s)")
    except GvcpError as e:
        R["skipped"].append(f"timestamp latch: {e}")

    nm, which = None, None
    try:
        nm = official_nodemap(xml, g)
        which = "official EMVA genicam"
    except ImportError:
        if a.official_genapi:
            check("official genicam wheel importable", False)
    except Exception as e:  # noqa
        print("   official GenApi failed:", e)
    toy = ToyNodeMap(xml, g)
    R["genapi_backend"] = which or "toy"
    print("== GenApi features via", R["genapi_backend"])
    feats = {}
    for f in ("Width", "Height", "PixelFormat", "PayloadSize", "GevIEEE1588", "PtpEnable",
              "GevIEEE1588Status", "PtpStatus", "ActionDeviceKey", "GevTimestampTickFrequency"):
        try:
            if nm is not None:
                node = nm.get_node(f)
                feats[f] = str(node.value) if node is not None else None
            else:
                feats[f] = toy.get(f) if f in toy.nodes else None
        except Exception as e:  # noqa
            feats[f] = f"<{type(e).__name__}: {e}>"
    R["features"] = feats
    print("  ", feats)
    if "Width" in toy.nodes:
        try:
            tw = toy.get("Width")
            check("toy GenApi reads Width", isinstance(tw, int), f"= {tw}")
        except NotImplementedError as e:
            R["skipped"].append(str(e))

    if a.stream_seconds > 0:
        print("== stream channel 0 + GVSP")
        host_ip = g.local_ip
        ssock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            opt = getattr(socket, "SO_RCVBUFFORCE", 33) if a.force_rcvbuf else socket.SO_RCVBUF
            ssock.setsockopt(socket.SOL_SOCKET, opt, a.rcvbuf)
        except OSError as e:
            print("   SO_RCVBUF request failed:", e)
        R["stream_rcvbuf_actual"] = ssock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        ssock.bind((host_ip, 0))
        port = ssock.getsockname()[1]
        g.write_reg(REG_SCP0_DEST, struct.unpack(">I", socket.inet_aton(host_ip))[0])
        g.write_reg(REG_SCP0_PORT, port)
        scps = g.read_reg(REG_SCP0_PACKET_SIZE)
        if a.packet_size:
            g.write_reg(REG_SCP0_PACKET_SIZE, (scps & ~0xFFFF) | a.packet_size)
            scps = g.read_reg(REG_SCP0_PACKET_SIZE)
        packet_size = scps & 0xFFFF
        R["packet_size"] = packet_size
        if a.test_packet:
            g.write_reg(REG_SCP0_PACKET_SIZE, SCPS_FIRE_TEST | SCPS_DO_NOT_FRAGMENT | packet_size)
            ssock.settimeout(0.5)
            try:
                d = ssock.recv(65536)
                R["test_packet_bytes"] = len(d)
                check("test packet received", len(d) + IP_UDP == packet_size, f"({len(d)} + 28 vs {packet_size})")
            except socket.timeout:
                R["skipped"].append("test packet: none received (device may not implement fire-test)")
            g.write_reg(REG_SCP0_PACKET_SIZE, scps & ~SCPS_FIRE_TEST)
        try:
            payload = int(feats.get("PayloadSize")) if str(feats.get("PayloadSize", "")).isdigit() else None
        except (TypeError, ValueError):
            payload = None
        if payload is None:
            w, h = int(feats["Width"]), int(feats["Height"])
            payload = w * h * 4
        start = (lambda: nm.get_node("AcquisitionStart").execute()) if nm else (lambda: toy.set("AcquisitionStart", 1))
        stop = (lambda: nm.get_node("AcquisitionStop").execute()) if nm else (lambda: toy.set("AcquisitionStop", 0))
        err0 = udp_rcvbuf_errors()
        start()
        t0 = time.time()
        stats, frames = receive_stream(g, ssock, a.stream_seconds, packet_size, payload, resend=not a.no_resend)
        dt = time.time() - t0
        stop()
        ssock.close()
        ts = stats.pop("timestamps")
        if len(ts) > 1 and tick:
            d = [(b - a_) / tick for a_, b in zip(ts, ts[1:])]
            stats["device_frame_interval_s_mean"] = sum(d) / len(d)
        stats["throughput_mbps"] = round(stats["bytes"] * 8 / dt / 1e6, 2)
        err1 = udp_rcvbuf_errors()
        stats["kernel_udp_rcvbuf_errors_delta"] = (err1 - err0) if err0 is not None and err1 is not None else None
        stats["rcvbuf_actual"] = R["stream_rcvbuf_actual"]
        R["stream"] = stats
        R["first_frames"] = frames[:3]
        print("  ", {k: v for k, v in stats.items()})
        check("received GVSP leader+trailer", stats["leaders"] > 0 and stats["trailers"] > 0)
        check("frames reassembled", stats["frames_complete"] + stats["frames_incomplete"] > 0,
              f"(complete={stats['frames_complete']} incomplete={stats['frames_incomplete']} "
              f"missing_pkts={stats['missing_packets']} resend_cmds={stats['resend_cmds']})")
    if a.action:
        dk, gk, gm = (int(x, 0) for x in a.action.split(":"))
        acks = send_action(ip, dk, gk, gm)
        R["action_acks"] = acks
        print("== ACTION_CMD acks:", acks or "none (device lacks action support or keys mismatch)")
    g.release()
    R["gvcp_stats"] = g.stats
    R["toy_genapi_unsupported_tags_hit"] = sorted(toy.unsupported)
    return finish(R, a)


def finish(R, a):
    print(f"== {len(R['ok'])} passed, {len(R['fail'])} failed, {len(R['skipped'])} skipped")
    for s in R["skipped"]:
        print("   skipped:", s)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(R, f, indent=1, default=str)
    return 0 if not R["fail"] else 1


if __name__ == "__main__":
    sys.exit(main())
