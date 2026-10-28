#!/usr/bin/env python3
"""
gvsp_pcap_report.py - stand-alone (stdlib only, Python >= 3.8) GigE Vision stream analyser.

Purpose: answer "what is my GigE Vision camera actually sending?" (raw vs compressed payload,
pixel format, packet size, block-id mode, timestamps, packet loss / resend) from a packet
capture, on any OS, without needing a GigE Vision SDK in Python.

How to use on a machine that has a real GigE Vision camera:
  1. Start a capture on the NIC the camera is attached to (Wireshark GUI, or
       Linux/macOS:  sudo tcpdump -i <iface> -w gev.pcap udp
       Windows:      "C:\\Program Files\\Wireshark\\dumpcap.exe" -i <iface> -w gev.pcapng -f udp )
     NOTE: on Windows, vendor filter drivers (e.g. eBUS Universal Pro, pylon GigE filter driver)
     may hide GVSP packets from Npcap; if the report shows 0 GVSP packets, disable the
     filter driver for that NIC (or use the vendor's "socket driver" mode) while capturing.
  2. Stream from the camera with ANY software (vendor viewer, Aravis, Harvester...) for a few seconds.
     Try each pixel format / compression mode you care about (e.g. BayerRG8, BayerRG12p,
     vendor "lossless compression", JPEG).
  3. Stop the capture and run:   python3 gvsp_pcap_report.py gev.pcap   (pcap or pcapng)

Field layouts follow Aravis src/arvgvspprivate.h and Wireshark epan/dissectors/packet-gvsp.c.
"""
import struct
import sys
from collections import Counter, defaultdict

GVCP_PORT = 3956
PAYLOAD_TYPES = {
    0x0000: "NO_DATA", 0x0001: "IMAGE", 0x0002: "RAW_DATA", 0x0003: "FILE", 0x0004: "CHUNK_DATA",
    0x0005: "EXTENDED_CHUNK_DATA(deprecated)", 0x0006: "JPEG", 0x0007: "JPEG2000", 0x0008: "H264",
    0x0009: "MULTIZONE_IMAGE", 0x000A: "MULTIPART", 0x000B: "GENDC_CONTAINER", 0x000C: "GENDC_COMPONENT_DATA",
}
COMPRESSED_PAYLOADS = {0x0006, 0x0007, 0x0008}
FORMATS = {1: "LEADER", 2: "TRAILER", 3: "PAYLOAD", 4: "ALL_IN", 5: "H264", 6: "MULTIZONE", 7: "MULTIPART", 8: "GENDC"}
PIXEL_FORMATS = {  # PFNC codes (subset), see Aravis src/arvenums.h / Wireshark packet-gvsp.c
    0x01080001: "Mono8", 0x01100003: "Mono10", 0x010A0046: "Mono10p", 0x01100005: "Mono12",
    0x010C0047: "Mono12p", 0x010C0006: "Mono12Packed(GEV)", 0x01100007: "Mono16",
    0x01080008: "BayerGR8", 0x01080009: "BayerRG8", 0x0108000A: "BayerGB8", 0x0108000B: "BayerBG8",
    0x01100010: "BayerGR12", 0x01100011: "BayerRG12", 0x01100012: "BayerGB12", 0x01100013: "BayerBG12",
    0x010C0057: "BayerGR12p", 0x010C0059: "BayerRG12p", 0x010C0055: "BayerGB12p", 0x010C0053: "BayerBG12p",
    0x0110000D: "BayerRG10", 0x010A0058: "BayerRG10p", 0x0110002F: "BayerRG16",
    0x02180014: "RGB8", 0x02180015: "BGR8", 0x0210001F: "YUV422_8_UYVY", 0x02100032: "YUV422_8", 0x0210003B: "YCbCr422_8",
}


def read_packets(path):
    """Yield (ts_seconds, linktype, frame_bytes) from a pcap or pcapng file."""
    with open(path, "rb") as f:
        data = f.read()
    magic = data[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d"):
        le = magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1")
        nano = magic in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
        e = "<" if le else ">"
        linktype = struct.unpack(e + "I", data[20:24])[0]
        off = 24
        while off + 16 <= len(data):
            sec, frac, incl, _orig = struct.unpack(e + "IIII", data[off:off + 16])
            off += 16
            yield sec + frac / (1e9 if nano else 1e6), linktype, data[off:off + incl]
            off += incl
    elif magic == b"\x0a\x0d\x0d\x0a":
        off = 0
        e = "<"
        if_links, if_res = [], []
        while off + 12 <= len(data):
            btype = struct.unpack(e + "I", data[off:off + 4])[0]
            if btype == 0x0A0D0D0A:
                bom = data[off + 8:off + 12]
                e = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">"
                if_links, if_res = [], []
            blen = struct.unpack(e + "I", data[off + 4:off + 8])[0]
            body = data[off + 8:off + blen - 4]
            if btype == 1:  # IDB
                if_links.append(struct.unpack(e + "H", body[0:2])[0])
                res = 1e-6
                o = 8
                while o + 4 <= len(body):
                    code, ln = struct.unpack(e + "HH", body[o:o + 4])
                    if code == 0:
                        break
                    if code == 9:
                        v = body[o + 4]
                        res = 2.0 ** -(v & 0x7F) if v & 0x80 else 10.0 ** -v
                    o += 4 + ((ln + 3) & ~3)
                if_res.append(res)
            elif btype == 6:  # EPB
                ifid, th, tl, cap, _orig = struct.unpack(e + "IIIII", body[:20])
                yield ((th << 32) | tl) * if_res[ifid], if_links[ifid], body[20:20 + cap]
            elif btype == 3:  # SPB
                yield 0.0, if_links[0], body[4:]
            off += blen
    else:
        raise SystemExit("unrecognised capture format (need pcap or pcapng)")


def udp_of(linktype, frame):
    """Return (src_ip, src_port, dst_ip, dst_port, payload) for IPv4/UDP, else None."""
    if linktype == 1:  # Ethernet
        etype, off = struct.unpack(">H", frame[12:14])[0], 14
        while etype in (0x8100, 0x88A8):
            etype, off = struct.unpack(">H", frame[off + 2:off + 4])[0], off + 4
        if etype != 0x0800:
            return None
    elif linktype == 113:  # Linux cooked
        if struct.unpack(">H", frame[14:16])[0] != 0x0800:
            return None
        off = 16
    elif linktype == 276:  # Linux cooked v2
        if struct.unpack(">H", frame[0:2])[0] != 0x0800:
            return None
        off = 20
    elif linktype in (0, 108):  # BSD loopback
        off = 4
    elif linktype == 101:  # raw IP
        off = 0
    else:
        return None
    ip = frame[off:]
    if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 17:
        return None
    ihl = (ip[0] & 0x0F) * 4
    if struct.unpack(">H", ip[6:8])[0] & 0x1FFF or struct.unpack(">H", ip[6:8])[0] & 0x2000:
        return None  # fragmented datagram: GVSP should never be fragmented (SCPS 'do not fragment')
    sport, dport, ulen = struct.unpack(">HHH", ip[ihl:ihl + 6])
    src = ".".join(map(str, ip[12:16]))
    dst = ".".join(map(str, ip[16:20]))
    return src, sport, dst, dport, ip[ihl + 8:ihl + ulen], struct.unpack(">H", ip[2:4])[0]


def parse_gvsp(p):
    """Parse a GVSP header; return dict or None if it does not look like GVSP."""
    if len(p) < 8:
        return None
    status = struct.unpack(">H", p[0:2])[0]
    if not (status in (0x0000, 0x0100, 0x8FFF) or 0x8001 <= status <= 0x8017):
        return None
    fmt_byte = p[4]
    ei = bool(fmt_byte & 0x80)
    fmt = fmt_byte & 0x7F
    if fmt not in FORMATS:
        return None
    if ei:
        if len(p) < 20:
            return None
        block = struct.unpack(">Q", p[8:16])[0]
        pid = struct.unpack(">I", p[16:20])[0]
        hdr = 20
    else:
        block = struct.unpack(">H", p[2:4])[0]
        pid = struct.unpack(">I", p[4:8])[0] & 0x00FFFFFF
        hdr = 8
    return {"status": status, "ei": ei, "fmt": fmt, "block": block, "pid": pid, "data": p[hdr:]}


def main(path):
    streams = defaultdict(lambda: {"pkts": 0, "fmt": Counter(), "status": Counter(), "ip_len": Counter(),
                                   "leaders": [], "ei": set(), "payload_bytes": 0, "blocks": set(),
                                   "trailers": 0})
    gvcp = Counter()
    for ts, lt, frame in read_packets(path):
        u = udp_of(lt, frame)
        if u is None:
            continue
        src, sport, dst, dport, payload, ip_len = u
        if GVCP_PORT in (sport, dport):
            if dport == GVCP_PORT and len(payload) >= 4 and payload[0] == 0x42:
                gvcp[struct.unpack(">H", payload[2:4])[0]] += 1
            continue
        g = parse_gvsp(payload)
        if g is None:
            continue
        if g["fmt"] == 1 and len(g["data"]) >= 4:
            if struct.unpack(">H", g["data"][2:4])[0] & 0x3FFF not in PAYLOAD_TYPES:
                continue  # same leader sanity check as Wireshark's heuristic
        s = streams[(src, sport, dst, dport)]
        s["pkts"] += 1
        s["fmt"][FORMATS[g["fmt"]]] += 1
        s["status"][g["status"]] += 1
        s["ei"].add(g["ei"])
        s["blocks"].add(g["block"])
        if g["fmt"] == 3:
            s["ip_len"][ip_len] += 1
            s["payload_bytes"] += len(g["data"])
        elif g["fmt"] == 2:
            s["trailers"] += 1
        elif g["fmt"] == 1:
            d = g["data"]
            ptype_raw = struct.unpack(">H", d[2:4])[0]
            ptype = ptype_raw & 0x3FFF
            info = {"t_cap": ts, "block": g["block"], "ptype": ptype, "chunk_bit": bool(ptype_raw & 0x4000)}
            if ptype == 0x0008:  # H.264 leader has no timestamp at offset 4 (Wireshark dissect_h264_leader)
                info["payload_size"] = struct.unpack(">Q", d[4:12])[0]
            elif len(d) >= 12:
                info["ts"] = struct.unpack(">Q", d[4:12])[0]
            if ptype in (0x0001, 0x0005, 0x0009) and len(d) >= 36:
                pf, sx, sy, ox, oy = struct.unpack(">IIIII", d[12:32])
                info.update(pf=pf, sx=sx, sy=sy, ox=ox, oy=oy)
            if ptype in (0x0006, 0x0007) and len(d) >= 32:  # JPEG/JPEG2000 leader (Wireshark dissect_jpeg_leader)
                info["payload_size"] = struct.unpack(">Q", d[12:20])[0]
                info["tick_freq"] = struct.unpack(">Q", d[20:28])[0]
                info["data_format"] = struct.unpack(">I", d[28:32])[0]
            s["leaders"].append(info)

    if not streams:
        print("No GVSP packets found. Check the capture interface / vendor filter driver.")
    for (src, sport, dst, dport), s in streams.items():
        print(f"=== GVSP stream {src}:{sport} -> {dst}:{dport} ===")
        print(f"packets: {s['pkts']}  by format: {dict(s['fmt'])}")
        print(f"status codes: { {hex(k): v for k, v in s['status'].items()} }  (0x100 = resent packet, >=0x8000 = error)")
        print(f"extended-ID (EI, 64-bit block id) mode: {sorted(s['ei'])}")
        if s["ip_len"]:
            common = s["ip_len"].most_common(1)[0][0]
            print(f"payload packet IP length (== GevSCPSPacketSize): {common}  -> jumbo frames: {'yes' if common > 1500 else 'no'}")
        ptypes = Counter(PAYLOAD_TYPES.get(L['ptype'], hex(L['ptype'])) for L in s["leaders"])
        print(f"leader payload types: {dict(ptypes)}")
        pfs = Counter((PIXEL_FORMATS.get(L['pf'], f"0x{L['pf']:08X}"), L['sx'], L['sy']) for L in s["leaders"] if 'pf' in L)
        for (pf, sx, sy), n in pfs.items():
            custom = " (bit31 set: VENDOR-SPECIFIC/custom pixel format)" if pf.startswith("0x") and int(pf, 16) & 0x80000000 else ""
            print(f"  image leaders: {n} x {pf} {sx}x{sy}{custom}")
            if not pf.startswith("0x"):
                bpp = (int([k for k, v in PIXEL_FORMATS.items() if v == pf][0]) >> 16 & 0xFF) / 8
                print(f"    uncompressed size would be {sx * sy * bpp:.0f} B/frame")
        verdict = "COMPRESSED (standard GVSP compressed payload type)" if any(L['ptype'] in COMPRESSED_PAYLOADS for L in s['leaders']) else "no standard compressed payload type seen"
        print(f"compression verdict: {verdict}")
        n_frames = max(1, s["trailers"])
        print(f"avg payload bytes per block (from payload packets): {s['payload_bytes'] / n_frames:.0f}")
        tss = [L["ts"] for L in s["leaders"] if "ts" in L]
        if len(tss) >= 3:
            d = [b - a for a, b in zip(tss, tss[1:])]
            d.sort()
            print(f"leader timestamp deltas (device ticks): min {d[0]} median {d[len(d) // 2]} max {d[-1]}")
            print(f"first leader timestamp: {tss[0]} (0x{tss[0]:016X}); if PTP-synced, tick = 1 ns and value ~ TAI/PTP epoch ns")
        blocks = sorted(s["blocks"])
        print(f"distinct block ids: {len(blocks)} (first {blocks[0]}, last {blocks[-1]})")
    if gvcp:
        names = {0x0002: "DISCOVERY", 0x0004: "BYE", 0x0040: "PACKETRESEND", 0x0080: "READREG", 0x0082: "WRITEREG",
                 0x0084: "READMEM", 0x0086: "WRITEMEM", 0x0100: "ACTION"}
        print("=== GVCP commands (host -> device:3956) ===")
        print({names.get(k, hex(k)): v for k, v in sorted(gvcp.items())})


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
