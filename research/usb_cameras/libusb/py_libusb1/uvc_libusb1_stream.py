# /// script
# requires-python = ">=3.10"
# dependencies = ["libusb1==3.4.0", "pillow>=10"]
# ///
"""From-scratch, pure-Python UVC MJPEG streamer over libusb (python-libusb1 async isochronous I/O).

No libuvc, no OpenCV: descriptor parsing, PROBE/COMMIT negotiation, application-chosen alt
setting (bandwidth), payload-header parsing (FID/EOF/PTS/SCR incl. 11-bit SOF), MJPEG frame
assembly and the research per-frame log schema are all implemented here (~one file).

Run (repo root; on the shared Windows box wrap camera access in camlock):
  # enumerate + parse descriptors + try to open (no streaming):
  uv run --script research/usb_cameras/tools/camlock.py -- \
      uv run --script research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py --list
  # stream (camera must be on WinUSB/libusbK on Windows; udev rule on Linux; root on macOS):
  uv run --script research/usb_cameras/tools/camlock.py -- \
      uv run --script research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py \
      --vid 046d --pid 0843 --width 1280 --height 720 --fps 30 --seconds 10 \
      [--alt N | --min-packet-bytes B | --bandwidth-factor F] [--exposure-abs 100] [--wb-temp 4000]
      [--packets-per-transfer N (default 32, rounded up to a multiple of 8 on high speed)] [--transfers T (default 8)]
      [--decode-check (Pillow full decode of every frame after streaming)] [--raw-dump FILE]
Writes results/<platform>/<hostname>/py_libusb1_<list|stream>/ result.json (+ frames.jsonl,
a few JPEGs with --save-jpeg K). result.json "measurements" also has per-callback cost (callback_mean_us,
callback_busy_fraction) and iso packet counts. Phase-2 matrix: run_phase2_matrix.sh (same directory).
2026-10-25 fix: python-libusb1 3.4.0 USBDeviceHandle is not a context manager -> contextlib.closing().

Host clock: time.perf_counter_ns() (QueryPerformanceCounter on Windows, CLOCK_MONOTONIC on
Linux, mach_absolute_time on macOS), taken at entry of each transfer-completion callback.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import importlib.metadata as md
import json
import platform
import socket
import struct
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import usb1

PLAT = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system(), platform.system().lower())
RESULTS = Path(__file__).resolve().parents[2] / "results"

# ---- UVC constants (UVC 1.5 spec, appendix A) ------------------------------------------
CC_VIDEO = 0x0E
SC_VIDEOCONTROL, SC_VIDEOSTREAMING = 0x01, 0x02
CS_INTERFACE = 0x24
VC_HEADER, VC_INPUT_TERMINAL, VC_PROCESSING_UNIT = 0x01, 0x02, 0x05
VS_INPUT_HEADER, VS_FORMAT_MJPEG, VS_FRAME_MJPEG = 0x01, 0x06, 0x07
SET_CUR, GET_CUR, GET_MIN, GET_MAX, GET_DEF = 0x01, 0x81, 0x82, 0x83, 0x87
VS_PROBE_CONTROL, VS_COMMIT_CONTROL = 0x01, 0x02
CT_AE_MODE_CONTROL, CT_EXPOSURE_TIME_ABSOLUTE_CONTROL = 0x02, 0x04
PU_WB_TEMPERATURE_CONTROL, PU_WB_TEMPERATURE_AUTO_CONTROL = 0x0A, 0x0B
REQ_OUT = usb1.TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_OUT  # 0x21
REQ_IN = usb1.TYPE_CLASS | usb1.RECIPIENT_INTERFACE | usb1.ENDPOINT_IN  # 0xA1
HDR_FID, HDR_EOF, HDR_PTS, HDR_SCR, HDR_ERR = 0x01, 0x02, 0x04, 0x08, 0x40


# ---- descriptor model --------------------------------------------------------------------
@dataclass
class FrameDesc:
    index: int
    width: int
    height: int
    max_frame_bytes: int
    default_interval: int
    intervals: list[int]


@dataclass
class AltSetting:
    alt: int
    ep: int
    ep_type: int
    w_max_packet_size: int
    bytes_per_interval: int
    b_interval: int


@dataclass
class UvcInfo:
    vc_if: int = -1
    vs_if: int = -1
    bcd_uvc: int = 0
    clock_hz: int = 0
    camera_terminal_id: int = 0
    processing_unit_id: int = 0
    vs_endpoint: int = 0
    mjpeg_format_index: int = 0
    frames: list[FrameDesc] = field(default_factory=list)
    alts: list[AltSetting] = field(default_factory=list)


def parse_uvc(dev: usb1.USBDevice) -> UvcInfo | None:
    info = UvcInfo()
    for setting in dev.iterSettings():
        if setting.getClass() != CC_VIDEO:
            continue
        sub, num, alt = setting.getSubClass(), setting.getNumber(), setting.getAlternateSetting()
        extra = setting.getExtra()
        if sub == SC_VIDEOCONTROL and alt == 0:
            info.vc_if = num
            for d in extra:
                if len(d) < 3 or d[1] != CS_INTERFACE:
                    continue
                if d[2] == VC_HEADER and len(d) >= 12:
                    info.bcd_uvc, _total, info.clock_hz = struct.unpack_from("<HHI", d, 3)
                elif d[2] == VC_INPUT_TERMINAL and len(d) >= 8 and struct.unpack_from("<H", d, 4)[0] == 0x0201:
                    info.camera_terminal_id = d[3]
                elif d[2] == VC_PROCESSING_UNIT:
                    info.processing_unit_id = d[3]
        elif sub == SC_VIDEOSTREAMING:
            if info.vs_if not in (-1, num):
                continue  # first VS interface only
            info.vs_if = num
            if alt == 0:
                cur_fmt = None
                for d in extra:
                    if len(d) < 3 or d[1] != CS_INTERFACE:
                        continue
                    if d[2] == VS_INPUT_HEADER and len(d) >= 7:
                        info.vs_endpoint = d[6]
                    elif d[2] == VS_FORMAT_MJPEG:
                        cur_fmt = d[3]
                        info.mjpeg_format_index = info.mjpeg_format_index or cur_fmt
                    elif d[2] in (0x04, 0x10, 0x0C):  # other formats end the MJPEG frame list
                        cur_fmt = None
                    elif d[2] == VS_FRAME_MJPEG and cur_fmt == info.mjpeg_format_index and len(d) >= 26:
                        (idx,) = struct.unpack_from("<B", d, 3)
                        w, h = struct.unpack_from("<HH", d, 5)
                        maxbuf, defint = struct.unpack_from("<II", d, 17)
                        n = d[25]
                        ints = list(struct.unpack_from(f"<{n}I", d, 26)) if n else list(struct.unpack_from("<III", d, 26))
                        info.frames.append(FrameDesc(idx, w, h, maxbuf, defint, ints))
            for ep in setting.iterEndpoints():
                mps = ep.getMaxPacketSize()
                bpi = (mps & 0x7FF) * (((mps >> 11) & 3) + 1)
                for x in ep.getExtra():  # SuperSpeed endpoint companion (type 0x30)
                    if len(x) >= 6 and x[1] == 0x30:
                        bpi = struct.unpack_from("<H", x, 4)[0]
                info.alts.append(AltSetting(alt, ep.getAddress(), ep.getAttributes() & 3, mps, bpi, ep.getInterval()))
    return info if info.vc_if >= 0 and info.vs_if >= 0 else None


# ---- probe/commit ------------------------------------------------------------------------
PROBE_FIELDS = ["bmHint", "bFormatIndex", "bFrameIndex", "dwFrameInterval", "wKeyFrameRate", "wPFrameRate",
                "wCompQuality", "wCompWindowSize", "wDelay", "dwMaxVideoFrameSize", "dwMaxPayloadTransferSize",
                "dwClockFrequency", "bmFramingInfo", "bPreferredVersion", "bMinVersion", "bMaxVersion"]
PROBE_FMT = "<HBBIHHHHHII" + "IBBBB"


def probe_len(bcd: int) -> int:
    return 26 if bcd < 0x0110 else (34 if bcd < 0x0150 else 48)


def pack_probe(p: dict, n: int) -> bytes:
    b = bytearray(n)
    struct.pack_into("<HBBIHHHHHII", b, 0, *(p.get(k, 0) for k in PROBE_FIELDS[:11]))
    if n >= 34:
        struct.pack_into("<IBBBB", b, 26, *(p.get(k, 0) for k in PROBE_FIELDS[11:]))
    return bytes(b)


def unpack_probe(b: bytes) -> dict:
    vals = list(struct.unpack_from("<HBBIHHHHHII", b, 0))
    d = dict(zip(PROBE_FIELDS[:11], vals))
    if len(b) >= 34:
        d.update(zip(PROBE_FIELDS[11:], struct.unpack_from("<IBBBB", b, 26)))
    d["raw_len"] = len(b)
    return d


def negotiate(h: usb1.USBDeviceHandle, info: UvcInfo, fd: FrameDesc, interval: int) -> tuple[dict, dict, dict]:
    n = probe_len(info.bcd_uvc)
    req = {"bmHint": 1, "bFormatIndex": info.mjpeg_format_index, "bFrameIndex": fd.index, "dwFrameInterval": interval}
    wv = lambda sel: sel << 8  # noqa: E731
    h.controlWrite(REQ_OUT, SET_CUR, wv(VS_PROBE_CONTROL), info.vs_if, pack_probe(req, n), 1000)
    probe = unpack_probe(h.controlRead(REQ_IN, GET_CUR, wv(VS_PROBE_CONTROL), info.vs_if, n, 1000))
    h.controlWrite(REQ_OUT, SET_CUR, wv(VS_COMMIT_CONTROL), info.vs_if, pack_probe(probe, n), 1000)
    try:
        commit = unpack_probe(h.controlRead(REQ_IN, GET_CUR, wv(VS_COMMIT_CONTROL), info.vs_if, n, 1000))
    except usb1.USBError as e:
        commit = {"error": repr(e)}
    return req, probe, commit


def set_ctrl(h, info: UvcInfo, unit: int, selector: int, fmt: str, value: int) -> dict:
    data = struct.pack(fmt, value)
    out = {"unit": unit, "selector": selector, "requested": value}
    try:
        h.controlWrite(REQ_OUT, SET_CUR, selector << 8, (unit << 8) | info.vc_if, data, 1000)
        out["set"] = "OK"
    except usb1.USBError as e:
        out["set"] = repr(e)
    try:
        out["readback"] = struct.unpack(fmt, h.controlRead(REQ_IN, GET_CUR, selector << 8, (unit << 8) | info.vc_if, len(data), 1000))[0]
    except usb1.USBError as e:
        out["readback"] = repr(e)
    return out


def choose_alt(info: UvcInfo, need: int, force_alt: int | None) -> AltSetting | None:
    iso = sorted((a for a in info.alts if a.ep_type == 1 and a.ep == info.vs_endpoint), key=lambda a: a.bytes_per_interval)
    if force_alt:
        return next((a for a in iso if a.alt == force_alt), None)
    return next((a for a in iso if a.bytes_per_interval >= need), None)


# ---- streaming ---------------------------------------------------------------------------
class Assembler:
    """libuvc-equivalent frame assembly from payloads (FID toggle or EOF closes a frame)."""

    def __init__(self, on_frame, max_frame: int):
        self.on_frame, self.max_frame = on_frame, max_frame
        self.buf = bytearray()
        self.fid = -1
        self.reset_meta()
        self.err_total = 0

    def reset_meta(self):
        self.m = {"pts": None, "scr_stc_first": None, "scr_sof_first": None, "scr_stc_last": None, "scr_sof_last": None,
                  "host_first_payload_ns": None, "host_last_payload_ns": None, "first_payload_packet_idx": None,
                  "last_payload_packet_idx": None, "payload_count": 0, "error_payload_count": 0}

    def close(self, by_eof: bool):
        self.on_frame(bytes(self.buf), dict(self.m, closed_by_eof=by_eof, fid=self.fid))
        self.buf.clear()
        self.reset_meta()

    def payload(self, p, host_ns: int, pkt_idx: int):
        n = len(p)
        if n < 2:
            return
        hl, bfh = p[0], p[1]
        if hl < 2 or hl > n:
            return
        if bfh & HDR_ERR:
            self.m["error_payload_count"] += 1
            self.err_total += 1
            return
        fid = bfh & HDR_FID
        if fid != self.fid:
            if self.buf:
                self.close(by_eof=False)
            else:
                self.reset_meta()
            self.fid = fid
        off = 2
        if bfh & HDR_PTS and hl >= off + 4:
            self.m["pts"] = int.from_bytes(p[off:off + 4], "little")
            off += 4
        if bfh & HDR_SCR and hl >= off + 6:
            stc = int.from_bytes(p[off:off + 4], "little")
            sof = int.from_bytes(p[off + 4:off + 6], "little") & 0x7FF
            if self.m["scr_stc_first"] is None:
                self.m["scr_stc_first"], self.m["scr_sof_first"] = stc, sof
            self.m["scr_stc_last"], self.m["scr_sof_last"] = stc, sof
        if n > hl:
            if not self.buf:
                self.m["host_first_payload_ns"], self.m["first_payload_packet_idx"] = host_ns, pkt_idx
            self.m["host_last_payload_ns"], self.m["last_payload_packet_idx"] = host_ns, pkt_idx
            self.m["payload_count"] += 1
            self.buf += p[hl:]
            if len(self.buf) > self.max_frame:
                del self.buf[self.max_frame:]
        if bfh & HDR_EOF and self.buf:
            self.close(by_eof=True)


def jpeg_ok(b: bytes) -> bool:
    return len(b) > 4 and b[:2] == b"\xff\xd8" and b"\xff\xd9" in b[-64:]


def stream(a, ctx: usb1.USBContext, dev: usb1.USBDevice, info: UvcInfo, out: Path, res: dict) -> int:
    fd = next((f for f in info.frames if f.width == a.width and f.height == a.height), None)
    if fd is None:
        res["error"] = f"no MJPEG {a.width}x{a.height}; have {[(f.width, f.height) for f in info.frames]}"
        return 4
    want = int(round(1e7 / a.fps))
    interval = min(fd.intervals, key=lambda i: abs(i - want)) if fd.intervals else fd.default_interval
    try:
        h = dev.open()
    except usb1.USBError as e:
        res["error"] = f"no accessible device: open failed: {e!r}"
        print(res["error"], file=sys.stderr)
        return 3
    with contextlib.closing(h):
        try:
            h.setAutoDetachKernelDriver(True)
        except usb1.USBError:
            pass  # LIBUSB_ERROR_NOT_SUPPORTED on Windows
        for itf in (info.vc_if, info.vs_if):
            try:
                h.claimInterface(itf)
            except usb1.USBError as e:
                res["error"] = f"no accessible device: claimInterface({itf}) failed: {e!r}"
                print(res["error"], file=sys.stderr)
                return 3
        ctrls = {}
        if a.exposure_abs and info.camera_terminal_id:
            ctrls["ae_mode"] = set_ctrl(h, info, info.camera_terminal_id, CT_AE_MODE_CONTROL, "<B", 1)
            ctrls["exposure_abs"] = set_ctrl(h, info, info.camera_terminal_id, CT_EXPOSURE_TIME_ABSOLUTE_CONTROL, "<I", a.exposure_abs)
        if a.wb_temp and info.processing_unit_id:
            ctrls["wb_auto"] = set_ctrl(h, info, info.processing_unit_id, PU_WB_TEMPERATURE_AUTO_CONTROL, "<B", 0)
            ctrls["wb_temp"] = set_ctrl(h, info, info.processing_unit_id, PU_WB_TEMPERATURE_CONTROL, "<H", a.wb_temp)
        res["controls"] = ctrls
        req, probe, commit = negotiate(h, info, fd, interval)
        res["negotiation"] = {"request": req, "probe": probe, "commit": commit}
        need = probe["dwMaxPayloadTransferSize"]
        speed_hs = dev.getDeviceSpeed() >= usb1.SPEED_HIGH
        if a.min_packet_bytes:
            need = a.min_packet_bytes
        if a.bandwidth_factor:
            b = a.width * a.height / 8 * a.bandwidth_factor * (1e7 / probe["dwFrameInterval"] + 1) / 1000
            need = int(b / 8 + 12) if speed_hs else int(b + 12)
        alt = choose_alt(info, need, a.alt)
        if alt is None:
            res["error"] = f"no iso alt setting with >= {need} bytes/interval (force_alt={a.alt})"
            return 5
        h.setInterfaceAltSetting(info.vs_if, alt.alt)
        ppt = a.packets_per_transfer or 32
        if speed_hs:  # WinUSB needs whole 1 ms frames: multiple of 8 microframes (bInterval=1)
            ppt = max(8, (ppt + 7) // 8 * 8)
        res["iso"] = {"altsetting": alt.alt, "bytes_per_packet": alt.bytes_per_interval, "packets_per_transfer": ppt,
                      "transfers": a.transfers, "need_bytes": need, "endpoint": alt.ep}

        key = a.camera_key or (f"usb:{dev.getVendorID():04x}:{dev.getProductID():04x}:port:"
                               f"{dev.getBusNumber()}-{'.'.join(map(str, dev.getPortNumberList()))}")
        stats = {"frames": 0, "jpeg_ok": 0, "bytes": 0, "saved": 0, "first": None, "last": None, "xfer_err": 0, "pkt_err": 0,
                 "cb_n": 0, "cb_ns": 0, "cb_max_ns": 0, "pkt_n": 0, "pkt_nonempty": 0, "iso_bytes": 0}
        kept: list[bytes] = []  # frames retained for the post-stream full decode check / raw dump
        jl = (out / "frames.jsonl").open("w")
        seq = [0]

        def on_frame(data: bytes, m: dict):
            arr = time.perf_counter_ns()
            seq[0] += 1
            ok = jpeg_ok(data)
            stats["frames"] += 1
            stats["jpeg_ok"] += ok
            stats["bytes"] += len(data)
            stats["first"] = stats["first"] or arr
            stats["last"] = arr
            jl.write(json.dumps({
                "camera_key": key, "backend": "py-libusb1", "seq": seq[0], "host_arrival_ns": arr,
                "os_timestamp_ns": m["host_last_payload_ns"],
                "os_timestamp_source": "perf_counter_ns at completion callback of the transfer carrying the closing payload",
                "uvc_pts": m["pts"], "uvc_scr_stc": m["scr_stc_last"], "uvc_scr_sof": m["scr_sof_last"],
                "device_clock_hz": info.clock_hz, "payload_bytes": len(data), "is_valid_jpeg": ok, "jpeg_check": "soi_eoi_only",
                **{k: m[k] for k in ("scr_stc_first", "scr_sof_first", "host_first_payload_ns", "host_last_payload_ns",
                                     "first_payload_packet_idx", "last_payload_packet_idx", "payload_count",
                                     "error_payload_count", "closed_by_eof", "fid")},
                "packets_per_transfer": ppt,
            }) + "\n")
            if a.decode_check or a.raw_dump:
                kept.append(data)
            if ok and stats["saved"] < a.save_jpeg:
                (out / f"frame_{seq[0]:05d}.jpg").write_bytes(data)
                stats["saved"] += 1

        asm = Assembler(on_frame, max(probe["dwMaxVideoFrameSize"], fd.max_frame_bytes))
        running = [True]

        def cb(t: usb1.USBTransfer):
            host_ns = time.perf_counter_ns()
            st = t.getStatus()
            if st == usb1.TRANSFER_COMPLETED:
                for i, (pst, buf) in enumerate(t.iterISO()):
                    stats["pkt_n"] += 1
                    if len(buf) > 0:
                        stats["pkt_nonempty"] += 1
                        stats["iso_bytes"] += len(buf)
                    if pst:
                        stats["pkt_err"] += 1
                        asm.m["error_payload_count"] += 1
                        continue
                    asm.payload(buf, host_ns, i)
            elif st not in (usb1.TRANSFER_CANCELLED,):
                stats["xfer_err"] += 1
            if running[0] and st != usb1.TRANSFER_CANCELLED and st != usb1.TRANSFER_NO_DEVICE:
                t.submit()
            dt_ns = time.perf_counter_ns() - host_ns
            stats["cb_n"] += 1
            stats["cb_ns"] += dt_ns
            stats["cb_max_ns"] = max(stats["cb_max_ns"], dt_ns)

        transfers = []
        for _ in range(a.transfers):
            t = h.getTransfer(iso_packets=ppt)
            t.setIsochronous(alt.ep, ppt * alt.bytes_per_interval, callback=cb, timeout=5000)
            transfers.append(t)
        cpu0, t0 = time.process_time(), time.perf_counter()
        for t in transfers:
            t.submit()
        while time.perf_counter() - t0 < a.seconds:
            ctx.handleEventsTimeout(tv=0.1)
        running[0] = False
        for t in transfers:
            try:
                t.cancel()
            except usb1.USBError:
                pass
        t_end = time.perf_counter() + 2
        while any(t.isSubmitted() for t in transfers) and time.perf_counter() < t_end:
            ctx.handleEventsTimeout(tv=0.1)
        cpu = time.process_time() - cpu0
        h.setInterfaceAltSetting(info.vs_if, 0)
        jl.close()
        dur = (stats["last"] - stats["first"]) / 1e9 if stats["frames"] > 1 else 0
        res["measurements"] = {
            "frames": stats["frames"], "jpeg_soi_eoi_ok": stats["jpeg_ok"], "seconds": a.seconds,
            "fps_from_arrivals": (stats["frames"] - 1) / dur if dur else 0, "mean_frame_bytes": stats["bytes"] / max(1, stats["frames"]),
            "transfer_errors": stats["xfer_err"], "iso_packet_errors": stats["pkt_err"], "uvc_error_payloads": asm.err_total,
            "process_cpu_s": cpu, "cpu_fraction_of_one_core": cpu / a.seconds, "saved_jpegs": stats["saved"],
            "callbacks": stats["cb_n"], "callback_mean_us": stats["cb_ns"] / max(1, stats["cb_n"]) / 1e3,
            "callback_max_us": stats["cb_max_ns"] / 1e3,
            "callback_busy_fraction": stats["cb_ns"] / 1e9 / a.seconds,
            "iso_packets": stats["pkt_n"], "iso_packets_nonempty": stats["pkt_nonempty"], "iso_bytes": stats["iso_bytes"],
            "iso_packets_per_s": stats["pkt_n"] / a.seconds,
            "frames_jsonl": str(out / "frames.jsonl"),
        }
        if a.decode_check:
            from io import BytesIO
            from PIL import Image
            ok_n, bad = 0, []
            for i, b in enumerate(kept):
                try:
                    with Image.open(BytesIO(b)) as im:
                        im.load()
                        if im.size == (a.width, a.height):
                            ok_n += 1
                        else:
                            bad.append((i + 1, f"size {im.size}"))
                except Exception as e:  # noqa: BLE001
                    bad.append((i + 1, repr(e)[:120]))
            res["measurements"]["pillow_full_decode_ok"] = ok_n
            res["measurements"]["pillow_full_decode_checked"] = len(kept)
            res["measurements"]["pillow_decode_failures_first10"] = bad[:10]
        if a.raw_dump:
            a.raw_dump.parent.mkdir(parents=True, exist_ok=True)
            with a.raw_dump.open("wb") as f:  # 4-byte LE length prefix per frame
                for b in kept:
                    f.write(len(b).to_bytes(4, "little"))
                    f.write(b)
            res["measurements"]["raw_dump"] = str(a.raw_dump)
    return 0


def list_devices(ctx: usb1.USBContext, res: dict, try_open: bool) -> int:
    n_open = 0
    for dev in ctx.getDeviceIterator(skip_on_error=True):
        info = parse_uvc(dev)
        if info is None:
            continue
        cam = {"vid": f"{dev.getVendorID():04x}", "pid": f"{dev.getProductID():04x}", "bus": dev.getBusNumber(),
               "port_path": f"{dev.getBusNumber()}-{'.'.join(map(str, dev.getPortNumberList()))}",
               "address": dev.getDeviceAddress(), "speed": dev.getDeviceSpeed(), "bcdUVC": f"{info.bcd_uvc:04x}",
               "dwClockFrequency": info.clock_hz, "vc_if": info.vc_if, "vs_if": info.vs_if, "vs_endpoint": info.vs_endpoint,
               "camera_terminal_id": info.camera_terminal_id, "processing_unit_id": info.processing_unit_id,
               "mjpeg_frames": [(f.width, f.height, [round(1e7 / i, 2) for i in f.intervals]) for f in info.frames],
               "alts": [vars(x) for x in info.alts]}
        if try_open:
            try:
                with contextlib.closing(dev.open()) as h:
                    cam["open"] = "OK"
                    n_open += 1
                    try:
                        cam["serial"] = h.getSerialNumber()
                    except usb1.USBError as e:
                        cam["serial"] = repr(e)
            except usb1.USBError as e:
                cam["open"] = repr(e)
        res["cameras"].append(cam)
    print(json.dumps(res["cameras"], indent=1))
    if try_open and n_open == 0:
        print("no accessible device: no UVC device could be opened by libusb", file=sys.stderr)
        return 3
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="enumerate+parse UVC descriptors and try to open")
    ap.add_argument("--no-open", action="store_true", help="with --list: do not even try libusb_open")
    ap.add_argument("--vid", type=lambda s: int(s, 16))
    ap.add_argument("--pid", type=lambda s: int(s, 16))
    ap.add_argument("--port-path", help="bus-p.p.p as printed by --list")
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--alt", type=int, help="force this bAlternateSetting")
    ap.add_argument("--min-packet-bytes", type=int)
    ap.add_argument("--bandwidth-factor", type=float)
    ap.add_argument("--packets-per-transfer", type=int)
    ap.add_argument("--transfers", type=int, default=8)
    ap.add_argument("--exposure-abs", type=int, help="CT exposure time absolute (100us units), sets AE manual")
    ap.add_argument("--wb-temp", type=int, help="PU white balance temperature (K), sets WB manual")
    ap.add_argument("--save-jpeg", type=int, default=0)
    ap.add_argument("--camera-key")
    ap.add_argument("--decode-check", action="store_true", help="after streaming, fully decode every frame with Pillow")
    ap.add_argument("--raw-dump", type=Path, help="write all frames (u32 LE length + bytes) to this file after streaming")
    ap.add_argument("--out-dir", type=Path)
    a = ap.parse_args()

    host = socket.gethostname()
    out = a.out_dir or (RESULTS / PLAT / host / ("py_libusb1_list" if a.list else "py_libusb1_stream"))
    out.mkdir(parents=True, exist_ok=True)
    res = {"test": "py_libusb1_" + ("list" if a.list else "stream"), "platform": PLAT, "hostname": host,
           "utc_started": _dt.datetime.now(_dt.timezone.utc).isoformat(), "command": " ".join(sys.argv),
           "environment": {"python": sys.version, "os": platform.platform(), "libusb1": md.version("libusb1"),
                           "libusb": ".".join(map(str, tuple(usb1.getVersion())[:4]))},
           "host_clock": "time.perf_counter_ns", "cameras": []}
    rc = 0
    with usb1.USBContext() as ctx:
        if a.list:
            rc = list_devices(ctx, res, try_open=not a.no_open)
        else:
            cands = []
            for dev in ctx.getDeviceIterator(skip_on_error=True):
                if a.vid is not None and dev.getVendorID() != a.vid:
                    continue
                if a.pid is not None and dev.getProductID() != a.pid:
                    continue
                pp = f"{dev.getBusNumber()}-{'.'.join(map(str, dev.getPortNumberList()))}"
                if a.port_path and pp != a.port_path:
                    continue
                info = parse_uvc(dev)
                if info:
                    cands.append((dev, info))
            if len(cands) <= a.index:
                res["error"] = "no matching UVC device"
                rc = 3
            else:
                dev, info = cands[a.index]
                res["cameras"].append({"vid": f"{dev.getVendorID():04x}", "pid": f"{dev.getProductID():04x}",
                                       "port_path": f"{dev.getBusNumber()}-{'.'.join(map(str, dev.getPortNumberList()))}",
                                       "bcdUVC": f"{info.bcd_uvc:04x}", "dwClockFrequency": info.clock_hz,
                                       "alts": [vars(x) for x in info.alts]})
                rc = stream(a, ctx, dev, info, out, res)
    res["exit_code"] = rc
    (out / "result.json").write_text(json.dumps(res, indent=2, default=str))
    print(f"wrote {out / 'result.json'} (exit {rc})", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
