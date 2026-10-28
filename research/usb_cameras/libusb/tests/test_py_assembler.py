# /// script
# requires-python = ">=3.10"
# dependencies = ["libusb1==3.4.0"]
# ///
"""Hardware-free unit test of py_libusb1/uvc_libusb1_stream.py: payload-header parsing + frame
assembly (same synthetic stream as tests/test_payload_timing.c), PROBE pack/unpack round trip, and
alt-setting choice. Run:
    uv run --script research/usb_cameras/libusb/tests/test_py_assembler.py [out.json]
"""
import importlib.util
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("uvcs", HERE.parent / "py_libusb1" / "uvc_libusb1_stream.py")
m = importlib.util.module_from_spec(spec)
sys.modules["uvcs"] = m
spec.loader.exec_module(m)

checks = []


def check(name, cond):
    checks.append({"check": name, "pass": bool(cond)})
    if not cond:
        print("FAIL", name, file=sys.stderr)


def mk(bfh, pts=0, stc=0, sof=0, data=b""):
    h = bytearray([0, bfh])
    if bfh & m.HDR_PTS:
        h += struct.pack("<I", pts)
    if bfh & m.HDR_SCR:
        h += struct.pack("<IH", stc, sof)
    h[0] = len(h)
    return bytes(h) + data


frames = []
asm = m.Assembler(lambda d, meta: frames.append((d, meta)), 1 << 16)
P = m.HDR_PTS | m.HDR_SCR
D = b"\xff\xd8" + b"\xab" * 98
asm.payload(mk(0 | P, 111, 2000, 0x123, D), 1000, 3)
asm.payload(mk(0 | P, 111, 2100, 0x124, b"\xab" * 100), 1000, 4)
asm.payload(mk(0 | P | m.HDR_EOF, 111, 2200, 0x125, b"\xab" * 48 + b"\xff\xd9"), 2000, 5)
check("A_emitted", len(frames) == 1)
d, a = frames[0]
check("A_bytes_250", len(d) == 250)
check("A_jpeg_ok", m.jpeg_ok(d))
check("A_pts", a["pts"] == 111)
check("A_scr", (a["scr_stc_first"], a["scr_sof_first"], a["scr_stc_last"], a["scr_sof_last"]) == (2000, 0x123, 2200, 0x125))
check("A_host", (a["host_first_payload_ns"], a["host_last_payload_ns"]) == (1000, 2000))
check("A_idx", (a["first_payload_packet_idx"], a["last_payload_packet_idx"]) == (3, 5))
check("A_eof", a["closed_by_eof"] is True and a["payload_count"] == 3)
asm.payload(mk(0 | P, 111, 9999, 0x7FF), 2500, 0)  # idle header-only payload, old FID
asm.payload(mk(1 | P, 222, 3000, 0xF810, b"\x01" * 300), 3000, 1)
asm.payload(mk(1 | m.HDR_ERR, data=b"\x00" * 10), 3000, 2)
asm.payload(mk(1 | P, 222, 3100, 0x0011, b"\x01" * 300), 4000, 7)
asm.payload(mk(0 | P, 333, 4000, 0x0020, b"\x02" * 100), 5000, 2)
check("B_emitted", len(frames) == 2)
d, b = frames[1]
check("B_bytes_600", len(d) == 600)
check("B_no_stale_scr", b["scr_stc_first"] == 3000)
check("B_sof_masked", b["scr_sof_first"] == 0x10 and b["scr_sof_last"] == 0x11)
check("B_fid_toggle", b["closed_by_eof"] is False and b["fid"] == 1)
check("B_err", b["error_payload_count"] == 1)
asm.payload(mk(0 | P | m.HDR_EOF, 333, 4100, 0x21, b"\x02" * 20), 6000, 9)
d, c = frames[2]
check("C_bytes_120", len(d) == 120 and c["scr_stc_first"] == 4000 and c["host_first_payload_ns"] == 5000)

# PROBE round trip, UVC 1.0 (26 bytes) and 1.1 (34 bytes)
p = {"bmHint": 1, "bFormatIndex": 2, "bFrameIndex": 3, "dwFrameInterval": 333333, "dwMaxVideoFrameSize": 1843200,
     "dwMaxPayloadTransferSize": 3072, "dwClockFrequency": 30000000, "bmFramingInfo": 3}
for n in (26, 34):
    b = m.pack_probe(p, n)
    u = m.unpack_probe(b)
    check(f"probe_len_{n}", len(b) == n and m.probe_len(0x0100) == 26 and m.probe_len(0x0110) == 34 and m.probe_len(0x0150) == 48)
    check(f"probe_roundtrip_{n}", all(u[k] == p[k] for k in ("bFormatIndex", "bFrameIndex", "dwFrameInterval", "dwMaxVideoFrameSize", "dwMaxPayloadTransferSize")))
    if n == 34:
        check("probe_roundtrip_34_clock", u["dwClockFrequency"] == 30000000 and u["bmFramingInfo"] == 3)

# alt choice on the C930e's measured alt table (results/windows/Gerald/py_libusb1_list)
info = m.UvcInfo(vs_endpoint=0x81)
for alt, bpi in [(1, 192), (2, 384), (3, 512), (4, 640), (5, 800), (6, 944), (7, 1280), (8, 1600), (9, 1984), (10, 2688), (11, 3072)]:
    info.alts.append(m.AltSetting(alt, 0x81, 1, 0, bpi, 1))
check("alt_for_3072", m.choose_alt(info, 3072, None).alt == 11)
check("alt_for_900", m.choose_alt(info, 900, None).alt == 6)
check("alt_forced_3", m.choose_alt(info, 3072, 3).alt == 3)
check("alt_none_too_big", m.choose_alt(info, 5000, None) is None)

res = {"test": "py_libusb1_unit", "cameras": [], "checks": checks,
       "passed": sum(c["pass"] for c in checks), "failed": sum(not c["pass"] for c in checks)}
if len(sys.argv) > 1:
    Path(sys.argv[1]).parent.mkdir(parents=True, exist_ok=True)
    Path(sys.argv[1]).write_text(json.dumps(res, indent=1))
print(f"passed={res['passed']} failed={res['failed']}")
sys.exit(1 if res["failed"] else 0)
