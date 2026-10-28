#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Linux V4L2 / uvcvideo capture-time test: buffer timestamps + UVC metadata node (PTS/SCR) per frame.

STATUS: UNVERIFIED DRAFT. Written on a Windows machine and never run. Struct sizes and ioctl numbers are
checked by `--self-test` (runs on any OS, opens nothing); everything that touches a device is unrun.

WHAT TO RUN (from the repo root):
    uv run --script research/usb_cameras/timing/linux/v4l2_uvc_timing.py --self-test
    uv run --script research/usb_cameras/timing/linux/v4l2_uvc_timing.py --list
    uv run --script research/usb_cameras/timing/linux/v4l2_uvc_timing.py --device /dev/video0 --size 1280x720 --fps 30 --seconds 30
    # several cameras at once (one capture thread each):
    uv run --script research/usb_cameras/timing/linux/v4l2_uvc_timing.py --device /dev/video0 --device /dev/video2 --seconds 30
    # fixed exposure (V4L2_CID_EXPOSURE_ABSOLUTE is in 100 us units: 100 -> 10 ms) and white balance:
    uv run --script research/usb_cameras/timing/linux/v4l2_uvc_timing.py --device /dev/video0 --exposure-abs 100 --wb-k 4500
  or use timing/linux/run_linux_timing.sh, which runs this for every UVC camera and then analyze_frames.py.

HARDWARE: one or more UVC cameras that offer MJPEG, driven by the in-kernel `uvcvideo` driver.
  64-bit Linux on x86_64 or aarch64 only (the V4L2 structs below are the LP64 layouts; refused elsewhere).
  Linux >= 4.16 for the metadata node (V4L2_META_FMT_UVC); semantics below follow Linux v6.12.
PERMISSIONS: read/write access to /dev/videoN and to its metadata node (user in group `video`, or a local
  logind seat ACL). No root needed. Changing the uvcvideo `hwtimestamps` parameter needs root and is NOT done
  here (run_linux_timing.sh can do it with `sudo -n`). Never prompts; fails with a message instead.

WRITES research/usb_cameras/results/linux/<hostname>/timing/v4l2_uvc_timing/[<tag>/]
    session.json                 test, platform, hostname, utc_started, command, environment, cameras (+ per-camera
                                 negotiated mode, control read-back, metadata pairing, counters, raw meta samples)
    <camera_key>.frames.jsonl    one line per frame, README "Per-frame log schema" + extras (below)
    <camera_key>.sample.jpg      one payload (frame #30) so the MJPEG can be checked by eye / decoder
  Override with --out-dir. --tag adds a sub-directory (run_linux_timing.sh uses it per run).

PER-FRAME FIELDS (README schema): camera_key, backend="v4l2", seq (= v4l2_buffer.sequence), host_arrival_ns
  (CLOCK_MONOTONIC right after VIDIOC_DQBUF returns), os_timestamp_ns (= v4l2_buffer.timestamp in ns, us
  resolution), os_timestamp_source, uvc_pts, uvc_scr_stc, uvc_scr_sof, device_clock_hz (VC header
  dwClockFrequency from sysfs `descriptors`), payload_bytes, is_valid_jpeg (SOI at start + EOI in the last 64 bytes;
  markers only, NOT decoded).
  Extras used by tools/analyze_frames.py: uvc_eof_pts / uvc_eof_scr_stc / uvc_eof_scr_sof (LAST metadata block of
  the frame), uvc_host_sof / uvc_host_sof_ns (first block: host USB frame number + CLOCK_MONOTONIC ns, sampled
  together by the kernel), uvc_eof_host_sof / uvc_eof_host_sof_ns (last block), meta_buf_timestamp_ns (timestamp
  of the paired metadata buffer, see below). Other extras: v4l2_* (raw flags, decoded timestamp type/source),
  meta_* (block count, header flags), jpeg_soi / jpeg_eoi, hwts_mapped.

KERNEL SEMANTICS (Linux v6.12 drivers/media/usb/uvc/uvc_video.c, uvc_queue.c, include/uapi/linux/uvcvideo.h):
  * Buffer timestamp: uvc_video_decode_start() sets vb2 timestamp = uvc_video_get_time() (ktime_get(), i.e.
    CLOCK_MONOTONIC, unless module param clock=CLOCK_REALTIME) when the FID toggles, i.e. while processing the URB
    that holds the FIRST payload of the frame. uvc_queue_init() sets timestamp_flags = TIMESTAMP_MONOTONIC |
    TSTAMP_SRC_SOE. So it is "start of exposure" in name only: it is the host time the first bytes of the frame
    were processed (URB completion granularity), after the sensor has already exposed and the device has started
    sending. The flag is decoded per buffer and recorded anyway.
  * hwtimestamps: if /sys/module/uvcvideo/parameters/hwtimestamps is 1, uvc_buffer_finish() (vb2 buf_finish, runs at
    DQBUF) calls uvc_video_clock_update(), which REPLACES the video buffer timestamp with the frame's UVC PTS mapped
    to host time via the SCR (STC,SOF) and (host SOF, host time) sample ring. It can leave the SOE time in place
    (too few samples / no PTS). The metadata queue has no buf_finish op, and uvc_video_next_buffers() copied the
    video timestamp into the metadata buffer when the frame completed, so the METADATA buffer keeps the SOE host
    time. We log both; hwts_mapped = (video ts != metadata ts) when hwtimestamps=1. [verify on the target kernel]
  * Metadata node: a second /dev/videoM per streaming interface (uvc_meta_register()), same bus_info, device_caps
    V4L2_CAP_META_CAPTURE. Format V4L2_META_FMT_UVC ('UVCH'). uvc_video_decode_meta() appends one block per payload
    header that carries an SCR different from the previous one (headers without SCR are skipped for UVCH):
        struct uvc_meta_buf { __u64 ns; __u16 sof; __u8 length; __u8 flags; __u8 buf[]; } __packed;
    ns  = uvc_video_get_time() and sof = usb_get_current_frame_number() sampled together with IRQs off,
    length = bHeaderLength (mem[0]), flags = bmHeaderInfo (mem[1]), buf = header bytes from offset 2:
    PTS (u32 LE) if flags & UVC_STREAM_PTS (0x04), then SCR (STC u32 LE + SOF u16 LE, 11 bits) if flags & 0x08.
    For UVCH the kernel copies only the standard part, so each block occupies 10 + len_std bytes with
    len_std = 2 + 4*PTS + 6*SCR (bytesused += length + sizeof(ns) + sizeof(sof), with length forced to len_std).
    The stored `length` field is the device's bHeaderLength and may be larger (vendor header bytes); we step by
    len_std and count mismatches. uvc_video_next_buffers() gives the metadata buffer the video buffer's sequence and
    timestamp, so the two are matched by sequence.
"""
from __future__ import annotations

import argparse
import ctypes as C
import datetime as dt
import errno
import glob
import json
import mmap
import os
import platform
import re
import select
import shlex
import signal
import socket
import struct
import sys
import threading
import time
from pathlib import Path

try:
    import fcntl  # Linux only; --self-test works without it
except ImportError:  # pragma: no cover
    fcntl = None

TEST_NAME = "v4l2_uvc_timing"
HERE = Path(__file__).resolve().parent
RESEARCH_ROOT = HERE.parent.parent          # research/usb_cameras
STATUS = "UNVERIFIED (draft, never run)"

# ===================================================================================== V4L2 ABI (videodev2.h)
# asm-generic ioctl encoding (x86_64 and arm64): nr 8 bits @0, type 8 bits @8, size 14 bits @16, dir 2 bits @30.
_IOC_NONE, _IOC_WRITE, _IOC_READ = 0, 1, 2


def _IOC(d: int, t: str, nr: int, size: int) -> int:
    assert 0 <= size < (1 << 14)
    return (d << 30) | (size << 16) | (ord(t) << 8) | nr


def _IOR(t, nr, st): return _IOC(_IOC_READ, t, nr, C.sizeof(st))
def _IOW(t, nr, st): return _IOC(_IOC_WRITE, t, nr, C.sizeof(st))
def _IOWR(t, nr, st): return _IOC(_IOC_READ | _IOC_WRITE, t, nr, C.sizeof(st))


u8, u16, u32, s32, u64, s64 = C.c_uint8, C.c_uint16, C.c_uint32, C.c_int32, C.c_uint64, C.c_int64


class v4l2_capability(C.Structure):
    _fields_ = [("driver", u8 * 16), ("card", u8 * 32), ("bus_info", u8 * 32), ("version", u32),
                ("capabilities", u32), ("device_caps", u32), ("reserved", u32 * 3)]


class v4l2_fmtdesc(C.Structure):
    _fields_ = [("index", u32), ("type", u32), ("flags", u32), ("description", u8 * 32), ("pixelformat", u32),
                ("mbus_code", u32), ("reserved", u32 * 3)]


class v4l2_pix_format(C.Structure):
    _fields_ = [("width", u32), ("height", u32), ("pixelformat", u32), ("field", u32), ("bytesperline", u32),
                ("sizeimage", u32), ("colorspace", u32), ("priv", u32), ("flags", u32), ("ycbcr_enc", u32),
                ("quantization", u32), ("xfer_func", u32)]


class v4l2_meta_format(C.Structure):
    # v6.12 has dataformat, buffersize (+ width/height/bytesperline for line-based formats); all inside the
    # 200-byte union, we only use the first two.
    _fields_ = [("dataformat", u32), ("buffersize", u32)]


class _v4l2_format_union(C.Union):
    # The kernel union contains struct v4l2_window (has pointers) -> 8-byte aligned on LP64; _align reproduces that.
    _fields_ = [("pix", v4l2_pix_format), ("meta", v4l2_meta_format), ("raw_data", u8 * 200), ("_align", u64)]


class v4l2_format(C.Structure):
    _fields_ = [("type", u32), ("fmt", _v4l2_format_union)]


class v4l2_requestbuffers(C.Structure):
    _fields_ = [("count", u32), ("type", u32), ("memory", u32), ("capabilities", u32), ("flags", u8),
                ("reserved", u8 * 3)]


class timeval64(C.Structure):   # struct timeval on LP64: two longs
    _fields_ = [("tv_sec", s64), ("tv_usec", s64)]


class v4l2_timecode(C.Structure):
    _fields_ = [("type", u32), ("flags", u32), ("frames", u8), ("seconds", u8), ("minutes", u8), ("hours", u8),
                ("userbits", u8 * 4)]


class _v4l2_buffer_m(C.Union):
    _fields_ = [("offset", u32), ("userptr", u64), ("planes", u64), ("fd", s32)]


class _v4l2_buffer_req(C.Union):
    _fields_ = [("request_fd", s32), ("reserved", u32)]


class v4l2_buffer(C.Structure):
    _fields_ = [("index", u32), ("type", u32), ("bytesused", u32), ("flags", u32), ("field", u32),
                ("timestamp", timeval64), ("timecode", v4l2_timecode), ("sequence", u32), ("memory", u32),
                ("m", _v4l2_buffer_m), ("length", u32), ("reserved2", u32), ("r", _v4l2_buffer_req)]


class v4l2_fract(C.Structure):
    _fields_ = [("numerator", u32), ("denominator", u32)]


class v4l2_captureparm(C.Structure):
    _fields_ = [("capability", u32), ("capturemode", u32), ("timeperframe", v4l2_fract), ("extendedmode", u32),
                ("readbuffers", u32), ("reserved", u32 * 4)]


class _v4l2_streamparm_union(C.Union):
    _fields_ = [("capture", v4l2_captureparm), ("raw_data", u8 * 200)]


class v4l2_streamparm(C.Structure):
    _fields_ = [("type", u32), ("parm", _v4l2_streamparm_union)]


class v4l2_control(C.Structure):
    _fields_ = [("id", u32), ("value", s32)]


class v4l2_queryctrl(C.Structure):
    _fields_ = [("id", u32), ("type", u32), ("name", u8 * 32), ("minimum", s32), ("maximum", s32), ("step", s32),
                ("default_value", s32), ("flags", u32), ("reserved", u32 * 2)]


class v4l2_frmsize_discrete(C.Structure):
    _fields_ = [("width", u32), ("height", u32)]


class v4l2_frmsize_stepwise(C.Structure):
    _fields_ = [("min_width", u32), ("max_width", u32), ("step_width", u32), ("min_height", u32),
                ("max_height", u32), ("step_height", u32)]


class _frmsize_union(C.Union):
    _fields_ = [("discrete", v4l2_frmsize_discrete), ("stepwise", v4l2_frmsize_stepwise)]


class v4l2_frmsizeenum(C.Structure):
    _fields_ = [("index", u32), ("pixel_format", u32), ("type", u32), ("u", _frmsize_union), ("reserved", u32 * 2)]


class v4l2_frmival_stepwise(C.Structure):
    _fields_ = [("min", v4l2_fract), ("max", v4l2_fract), ("step", v4l2_fract)]


class _frmival_union(C.Union):
    _fields_ = [("discrete", v4l2_fract), ("stepwise", v4l2_frmival_stepwise)]


class v4l2_frmivalenum(C.Structure):
    _fields_ = [("index", u32), ("pixel_format", u32), ("width", u32), ("height", u32), ("type", u32),
                ("u", _frmival_union), ("reserved", u32 * 2)]


class _c_int(C.Structure):
    _fields_ = [("v", C.c_int)]


VIDIOC_QUERYCAP = _IOR("V", 0, v4l2_capability)
VIDIOC_ENUM_FMT = _IOWR("V", 2, v4l2_fmtdesc)
VIDIOC_G_FMT = _IOWR("V", 4, v4l2_format)
VIDIOC_S_FMT = _IOWR("V", 5, v4l2_format)
VIDIOC_REQBUFS = _IOWR("V", 8, v4l2_requestbuffers)
VIDIOC_QUERYBUF = _IOWR("V", 9, v4l2_buffer)
VIDIOC_QBUF = _IOWR("V", 15, v4l2_buffer)
VIDIOC_DQBUF = _IOWR("V", 17, v4l2_buffer)
VIDIOC_STREAMON = _IOW("V", 18, _c_int)
VIDIOC_STREAMOFF = _IOW("V", 19, _c_int)
VIDIOC_G_PARM = _IOWR("V", 21, v4l2_streamparm)
VIDIOC_S_PARM = _IOWR("V", 22, v4l2_streamparm)
VIDIOC_G_CTRL = _IOWR("V", 27, v4l2_control)
VIDIOC_S_CTRL = _IOWR("V", 28, v4l2_control)
VIDIOC_QUERYCTRL = _IOWR("V", 36, v4l2_queryctrl)
VIDIOC_ENUM_FRAMESIZES = _IOWR("V", 74, v4l2_frmsizeenum)
VIDIOC_ENUM_FRAMEINTERVALS = _IOWR("V", 75, v4l2_frmivalenum)

# values a 64-bit Linux build of videodev2.h produces (checked in --self-test)
EXPECTED_IOCTLS = {
    "VIDIOC_QUERYCAP": 0x80685600, "VIDIOC_ENUM_FMT": 0xC0405602, "VIDIOC_G_FMT": 0xC0D05604,
    "VIDIOC_S_FMT": 0xC0D05605, "VIDIOC_REQBUFS": 0xC0145608, "VIDIOC_QUERYBUF": 0xC0585609,
    "VIDIOC_QBUF": 0xC058560F, "VIDIOC_DQBUF": 0xC0585611, "VIDIOC_STREAMON": 0x40045612,
    "VIDIOC_STREAMOFF": 0x40045613, "VIDIOC_G_PARM": 0xC0CC5615, "VIDIOC_S_PARM": 0xC0CC5616,
    "VIDIOC_G_CTRL": 0xC008561B, "VIDIOC_S_CTRL": 0xC008561C, "VIDIOC_QUERYCTRL": 0xC0445624,
    "VIDIOC_ENUM_FRAMESIZES": 0xC02C564A, "VIDIOC_ENUM_FRAMEINTERVALS": 0xC034564B,
}
EXPECTED_SIZES = {
    v4l2_capability: 104, v4l2_fmtdesc: 64, v4l2_pix_format: 48, v4l2_format: 208, v4l2_requestbuffers: 20,
    v4l2_buffer: 88, v4l2_streamparm: 204, v4l2_captureparm: 40, v4l2_control: 8, v4l2_queryctrl: 68,
    v4l2_frmsizeenum: 44, v4l2_frmivalenum: 52, v4l2_timecode: 16,
}
EXPECTED_OFFSETS = {  # v4l2_buffer on LP64
    "index": 0, "type": 4, "bytesused": 8, "flags": 12, "field": 16, "timestamp": 24, "timecode": 40,
    "sequence": 56, "memory": 60, "m": 64, "length": 72, "reserved2": 76, "r": 80,
}

V4L2_BUF_TYPE_VIDEO_CAPTURE = 1
V4L2_BUF_TYPE_META_CAPTURE = 13
V4L2_MEMORY_MMAP = 1
V4L2_FIELD_ANY = 0
V4L2_CAP_VIDEO_CAPTURE = 0x00000001
V4L2_CAP_META_CAPTURE = 0x00800000
V4L2_CAP_STREAMING = 0x04000000
V4L2_CAP_DEVICE_CAPS = 0x80000000
V4L2_CAP_TIMEPERFRAME = 0x1000
V4L2_FRMSIZE_TYPE_DISCRETE = 1
V4L2_FRMIVAL_TYPE_DISCRETE = 1

V4L2_BUF_FLAG_ERROR = 0x00000040
V4L2_BUF_FLAG_TIMESTAMP_MASK = 0x0000E000
V4L2_BUF_FLAG_TIMESTAMP_UNKNOWN = 0x00000000
V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC = 0x00002000
V4L2_BUF_FLAG_TIMESTAMP_COPY = 0x00004000
V4L2_BUF_FLAG_TSTAMP_SRC_MASK = 0x00070000
V4L2_BUF_FLAG_TSTAMP_SRC_EOF = 0x00000000
V4L2_BUF_FLAG_TSTAMP_SRC_SOE = 0x00010000

# control ids (v4l2-controls.h)
V4L2_CID_BASE = 0x00980900
V4L2_CID_CAMERA_CLASS_BASE = 0x009A0900
CONTROLS = {
    "exposure_auto": V4L2_CID_CAMERA_CLASS_BASE + 1,           # menu: 0 auto, 1 manual, 2 shutter prio, 3 aperture prio
    "exposure_absolute": V4L2_CID_CAMERA_CLASS_BASE + 2,       # 100 us units
    "exposure_auto_priority": V4L2_CID_CAMERA_CLASS_BASE + 3,  # 1 = camera may lower the frame rate in low light
    "white_balance_automatic": V4L2_CID_BASE + 12,
    "white_balance_temperature": V4L2_CID_BASE + 26,
    "gain": V4L2_CID_BASE + 19,
    "power_line_frequency": V4L2_CID_BASE + 24,
    "backlight_compensation": V4L2_CID_BASE + 28,
}
V4L2_EXPOSURE_MANUAL = 1


def fourcc(s: str) -> int:
    b = s.encode("ascii")
    assert len(b) == 4
    return struct.unpack("<I", b)[0]


def fourcc_str(v: int) -> str:
    return struct.pack("<I", v).decode("latin1")


V4L2_PIX_FMT_MJPEG = fourcc("MJPG")
V4L2_META_FMT_UVC = fourcc("UVCH")

# UVC payload header bmHeaderInfo bits (UVC 1.5 sec 2.4.3.3; include/linux/usb/uvc.h UVC_STREAM_*)
UVC_STREAM_FID, UVC_STREAM_EOF, UVC_STREAM_PTS, UVC_STREAM_SCR = 0x01, 0x02, 0x04, 0x08
UVC_STREAM_ERR, UVC_STREAM_EOH = 0x40, 0x80


def _cstr(arr) -> str:
    return bytes(arr).split(b"\0", 1)[0].decode("utf-8", errors="replace")


class V4L2Error(OSError):
    def __init__(self, what: str, e: OSError):
        super().__init__(e.errno, f"{what}: {os.strerror(e.errno) if e.errno else e} (errno {errno.errorcode.get(e.errno, e.errno)})")
        self.what = what


def xioctl(fd: int, req: int, arg, what: str):
    while True:
        try:
            return fcntl.ioctl(fd, req, arg)
        except InterruptedError:
            continue
        except OSError as e:
            raise V4L2Error(what, e) from None


# ===================================================================================== UVC metadata parsing
def parse_uvc_meta(data: bytes) -> tuple[list[dict], dict]:
    """Parse a V4L2_META_FMT_UVC buffer into its uvc_meta_buf blocks (see module docstring for the layout)."""
    blocks: list[dict] = []
    anomalies = {"length_ne_std": 0, "truncated": 0}
    off, n = 0, len(data)
    while off + 12 <= n:
        ns, sof, length, flags = struct.unpack_from("<QHBB", data, off)
        has_pts, has_scr = bool(flags & UVC_STREAM_PTS), bool(flags & UVC_STREAM_SCR)
        len_std = 2 + (4 if has_pts else 0) + (6 if has_scr else 0)
        stride = 10 + len_std
        if off + stride > n:
            anomalies["truncated"] += 1
            break
        p = off + 12
        pts = stc = dev_sof = None
        if has_pts:
            pts = struct.unpack_from("<I", data, p)[0]
            p += 4
        if has_scr:
            stc, sof_raw = struct.unpack_from("<IH", data, p)
            dev_sof = sof_raw & 0x7FF
        if length != len_std:
            anomalies["length_ne_std"] += 1
        blocks.append({"ns": ns, "host_sof": sof, "header_length": length, "flags": flags, "pts": pts, "stc": stc,
                       "dev_sof": dev_sof})
        off += stride
    if off != n and not anomalies["truncated"]:
        anomalies["trailing_bytes"] = n - off
    return blocks, anomalies


# ===================================================================================== sysfs / identity
def _rd(p: Path) -> str | None:
    try:
        return p.read_text(errors="replace").strip()
    except OSError:
        return None


def node_number(name: str) -> int:
    m = re.search(r"(\d+)$", name)
    return int(m.group(1)) if m else -1


def usb_device_dir(video_sysfs: Path) -> Path | None:
    try:
        p = (video_sysfs / "device").resolve()       # .../3-1.4/3-1.4:1.0 (VideoControl interface)
    except OSError:
        return None
    for cand in (p, *p.parents):
        if (cand / "idVendor").exists():
            return cand
    return None


def pci_controller(usb_dir: Path) -> str | None:
    for i, part in enumerate(usb_dir.parts):
        if re.fullmatch(r"usb\d+", part) and i > 0:
            return usb_dir.parts[i - 1]
    return None


def vc_header(usb_dir: Path, vc_ifnum: int | None) -> dict:
    """bcdUVC and dwClockFrequency from the VC_HEADER of the camera's VideoControl interface (sysfs `descriptors` =
    18-byte device descriptor followed by the raw configuration descriptor(s))."""
    try:
        raw = (usb_dir / "descriptors").read_bytes()
    except OSError as e:
        return {"error": f"read descriptors: {e}"}
    i, cur_if, cls, sub = 18, None, None, None
    while i + 2 <= len(raw):
        ln, typ = raw[i], raw[i + 1]
        if ln < 2:
            break
        d = raw[i:i + ln]
        if typ == 4 and ln >= 9:
            cur_if, cls, sub = d[2], d[5], d[6]
        elif (typ == 0x24 and cls == 0x0E and sub == 0x01 and ln >= 12 and d[2] == 0x01
              and (vc_ifnum is None or cur_if == vc_ifnum)):
            bcd = struct.unpack_from("<H", d, 3)[0]
            return {"bcdUVC": f"{bcd >> 8:x}.{bcd & 0xFF:02x}", "dwClockFrequency": struct.unpack_from("<I", d, 7)[0],
                    "vc_interface": cur_if}
        i += ln
    return {"error": "VC_HEADER not found"}


PLACEHOLDER_SERIALS = {"0", "00", "000", "0000", "00000000", "000000000000", "0000000000000000", "1", "01", "0001",
                       "0123456789", "123456789", "1234567890", "12345678", "123456", "0123456789abcdef",
                       "sn0001", "sn12345678", "none", "null", "default", "serial", "unknown", "n/a", "na", "123",
                       "200901010001"}


def serial_usable(s: str | None) -> bool:
    """Mirrors research/usb_cameras/naming/camera_identity.py serial_is_usable() (copied: this file is stand-alone)."""
    if not s or not s.strip():
        return False
    if not all(0x20 < ord(c) <= 0x7F and c != "," for c in s):
        return False
    s = s.strip()
    return s.lower() not in PLACEHOLDER_SERIALS and len(set(s)) > 1


def assign_camera_keys(cams: list[dict]) -> None:
    """key = <vid>:<pid>:sn=<serial> if the serial is usable and unique, else <vid>:<pid>:port=pci-<ctrl>/<ports>
    (scheme of naming/camera_identity.py derive()). Non-USB nodes fall back to v4l2 bus_info."""
    for c in cams:
        vid, pid, sn = (c.get("vid") or "????").lower(), (c.get("pid") or "????").lower(), c.get("serial")
        same = [o for o in cams if (o.get("vid") or "").lower() == vid and (o.get("pid") or "").lower() == pid
                and o.get("serial") == sn]
        if c.get("vid") is None:
            c["camera_key"], c["camera_key_kind"] = f"v4l2:{c.get('bus_info')}", "bus_info"
        elif serial_usable(sn) and len(same) == 1:
            c["camera_key"], c["camera_key_kind"] = f"{vid}:{pid}:sn={sn.strip()}", "serial"
        else:
            c["camera_key"], c["camera_key_kind"] = f"{vid}:{pid}:port={c.get('port_path')}", "port"
        if c.get("stream_index", 0):  # second streaming interface of one USB device
            c["camera_key"] += f":vs{c['stream_index']}"


def safe_name(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9._=-]+", "_", key).strip("_")


# ===================================================================================== enumeration
def querycap(path: str) -> dict:
    try:
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    except OSError as e:
        return {"error": f"open {path}: {e.strerror}" + (" (add your user to group 'video' or use a local seat)"
                                                          if e.errno in (errno.EACCES, errno.EPERM) else "")}
    try:
        cap = v4l2_capability()
        xioctl(fd, VIDIOC_QUERYCAP, cap, "VIDIOC_QUERYCAP")
        dcaps = cap.device_caps if cap.capabilities & V4L2_CAP_DEVICE_CAPS else cap.capabilities
        v = cap.version
        out = {"driver": _cstr(cap.driver), "card": _cstr(cap.card), "bus_info": _cstr(cap.bus_info),
               "driver_version": f"{v >> 16}.{(v >> 8) & 0xFF}.{v & 0xFF}", "capabilities": f"0x{cap.capabilities:08x}",
               "device_caps": f"0x{dcaps:08x}", "is_capture": bool(dcaps & V4L2_CAP_VIDEO_CAPTURE),
               "is_meta": bool(dcaps & V4L2_CAP_META_CAPTURE), "has_streaming": bool(dcaps & V4L2_CAP_STREAMING)}
        if out["is_capture"]:
            out["formats"] = enum_formats(fd, V4L2_BUF_TYPE_VIDEO_CAPTURE)
            if "MJPG" in out["formats"]:
                out["mjpeg_modes"] = enum_modes(fd, V4L2_PIX_FMT_MJPEG)
        if out["is_meta"]:
            out["formats"] = enum_formats(fd, V4L2_BUF_TYPE_META_CAPTURE)
        return out
    except OSError as e:
        return {"error": str(e)}
    finally:
        os.close(fd)


def enum_formats(fd: int, buf_type: int) -> list[str]:
    out = []
    for i in range(64):
        d = v4l2_fmtdesc(index=i, type=buf_type)
        try:
            xioctl(fd, VIDIOC_ENUM_FMT, d, "VIDIOC_ENUM_FMT")
        except OSError:
            break
        out.append(fourcc_str(d.pixelformat))
    return out


def enum_modes(fd: int, pixfmt: int) -> list[dict]:
    modes = []
    for i in range(256):
        fs = v4l2_frmsizeenum(index=i, pixel_format=pixfmt)
        try:
            xioctl(fd, VIDIOC_ENUM_FRAMESIZES, fs, "VIDIOC_ENUM_FRAMESIZES")
        except OSError:
            break
        if fs.type != V4L2_FRMSIZE_TYPE_DISCRETE:
            sw = fs.u.stepwise
            modes.append({"stepwise": [sw.min_width, sw.max_width, sw.min_height, sw.max_height]})
            break
        w, h = fs.u.discrete.width, fs.u.discrete.height
        fps = []
        for j in range(64):
            fi = v4l2_frmivalenum(index=j, pixel_format=pixfmt, width=w, height=h)
            try:
                xioctl(fd, VIDIOC_ENUM_FRAMEINTERVALS, fi, "VIDIOC_ENUM_FRAMEINTERVALS")
            except OSError:
                break
            if fi.type == V4L2_FRMIVAL_TYPE_DISCRETE and fi.u.discrete.numerator:
                fps.append(round(fi.u.discrete.denominator / fi.u.discrete.numerator, 3))
            else:
                fps.append("stepwise")
                break
        modes.append({"size": f"{w}x{h}", "fps": fps})
    return modes


def enumerate_nodes() -> list[dict]:
    nodes = []
    for s in sorted(glob.glob("/sys/class/video4linux/video*"), key=lambda p: node_number(p)):
        vs = Path(s)
        dev = f"/dev/{vs.name}"
        n = {"device": dev, "sysfs_name": _rd(vs / "name"), "sysfs_index": _rd(vs / "index")}
        try:
            n["sysfs_parent"] = str((vs / "device").resolve())
        except OSError:
            n["sysfs_parent"] = None
        n.update(querycap(dev))
        ud = usb_device_dir(vs)
        if ud is not None:
            n["usb_dir"] = str(ud)
            n["vid"], n["pid"] = _rd(ud / "idVendor"), _rd(ud / "idProduct")
            n["serial"], n["product"], n["manufacturer"] = _rd(ud / "serial"), _rd(ud / "product"), _rd(ud / "manufacturer")
            n["usb_speed_mbps"], n["busnum"], n["devnum"] = _rd(ud / "speed"), _rd(ud / "busnum"), _rd(ud / "devnum")
            n["sysfs_usb_name"] = ud.name
            n["pci_controller"] = pci_controller(ud)
            n["port_path"] = f"pci-{n['pci_controller'] or '?'}/{ud.name.split('-', 1)[1]}" if "-" in ud.name else None
            ifn = _rd(vs / "device" / "bInterfaceNumber")
            n["vc_interface"] = int(ifn, 16) if ifn else None
            n["uvc_vc_header"] = vc_header(ud, n["vc_interface"])
        nodes.append(n)
    return nodes


def uvc_cameras(nodes: list[dict]) -> list[dict]:
    """UVC capture nodes, each with its paired metadata node (same driver + bus_info, device_caps META_CAPTURE).
    One USB device with several streaming interfaces has several (video, meta) pairs with one bus_info; uvcvideo
    registers each stream's metadata node right after its video node (uvc_register_video -> uvc_meta_register), so
    pairs are formed in node-number order."""
    groups: dict[tuple, list[dict]] = {}
    for n in nodes:
        if n.get("driver") == "uvcvideo":
            groups.setdefault((n["driver"], n.get("bus_info")), []).append(n)
    cams = []
    for _, g in groups.items():
        caps = sorted([n for n in g if n.get("is_capture")], key=lambda n: node_number(n["device"]))
        metas = sorted([n for n in g if n.get("is_meta")], key=lambda n: node_number(n["device"]))
        used: set[str] = set()
        for k, c in enumerate(caps):
            c = dict(c)
            c["stream_index"] = k
            if len(metas) == len(caps):
                m = metas[k]
                method = "bus_info" if len(caps) == 1 else "bus_info+node_order"
            else:
                m = next((x for x in metas if node_number(x["device"]) > node_number(c["device"])
                          and x["device"] not in used), None)
                method = f"bus_info+next_higher_node ({len(caps)} capture vs {len(metas)} meta nodes)"
            if m is not None:
                used.add(m["device"])
                c["meta_node"] = m["device"]
                c["meta_formats"] = m.get("formats")
                c["meta_pairing"] = method
                c["meta_same_sysfs_parent"] = (m.get("sysfs_parent") == c.get("sysfs_parent"))
                c["meta_supports_uvch"] = "UVCH" in (m.get("formats") or [])
            else:
                c["meta_node"] = None
                c["meta_pairing"] = "no metadata node with this bus_info (kernel < 4.16?)"
            cams.append(c)
    assign_camera_keys(cams)
    return cams


# ===================================================================================== environment
def uvc_params() -> dict:
    out = {}
    for p in sorted(glob.glob("/sys/module/uvcvideo/parameters/*")):
        out[os.path.basename(p)] = _rd(Path(p))
    return out


def environment() -> dict:
    osr = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                osr[k] = v.strip('"')
    except OSError:
        pass
    cpu = None
    try:
        cpu = next((l.split(":", 1)[1].strip() for l in Path("/proc/cpuinfo").read_text().splitlines()
                    if l.lower().startswith(("model name", "hardware", "cpu model"))), None)
    except OSError:
        pass
    params = uvc_params()
    try:
        groups = [g for g in os.getgroups()]
    except OSError:
        groups = []
    return {"os": platform.platform(), "kernel_release": platform.release(), "kernel_version": platform.version(),
            "machine": platform.machine(), "distro": osr.get("PRETTY_NAME"), "python": platform.python_version(),
            "cpu": cpu, "cpu_count": os.cpu_count(),
            "clocksource": _rd(Path("/sys/devices/system/clocksource/clocksource0/current_clocksource")),
            "uvcvideo_module_loaded": Path("/sys/module/uvcvideo").exists(),
            "uvcvideo_version": _rd(Path("/sys/module/uvcvideo/version")),
            "uvcvideo_params": params,
            "uvcvideo_hwtimestamps": params.get("hwtimestamps"),
            "uvcvideo_clock": params.get("clock"),
            "euid": os.geteuid() if hasattr(os, "geteuid") else None, "groups": groups,
            "deps": "stdlib only (ctypes/fcntl/mmap/struct)"}


def hwts_on(env: dict) -> bool:
    return (env.get("uvcvideo_hwtimestamps") or "0").strip() in ("1", "Y", "y")


def clock_is_realtime(env: dict) -> bool:
    return "REALTIME" in (env.get("uvcvideo_clock") or "").upper()


# ===================================================================================== capture
def mono_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def ts_ns(tv: timeval64) -> int:
    return int(tv.tv_sec) * 1_000_000_000 + int(tv.tv_usec) * 1000


def decode_ts_flags(flags: int) -> tuple[str, str]:
    t = flags & V4L2_BUF_FLAG_TIMESTAMP_MASK
    ttype = {V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC: "monotonic", V4L2_BUF_FLAG_TIMESTAMP_COPY: "copy",
             V4L2_BUF_FLAG_TIMESTAMP_UNKNOWN: "unknown"}.get(t, f"0x{t:x}")
    s = flags & V4L2_BUF_FLAG_TSTAMP_SRC_MASK
    tsrc = {V4L2_BUF_FLAG_TSTAMP_SRC_SOE: "soe", V4L2_BUF_FLAG_TSTAMP_SRC_EOF: "eof"}.get(s, f"0x{s:x}")
    return ttype, tsrc


class MmapQueue:
    def __init__(self, fd: int, buf_type: int, count: int, what: str):
        self.fd, self.type, self.what = fd, buf_type, what
        rb = v4l2_requestbuffers(count=count, type=buf_type, memory=V4L2_MEMORY_MMAP)
        xioctl(fd, VIDIOC_REQBUFS, rb, f"{what} VIDIOC_REQBUFS")
        if rb.count < 2:
            raise RuntimeError(f"{what}: driver granted only {rb.count} buffers")
        self.maps: list[mmap.mmap] = []
        self.lengths: list[int] = []
        for i in range(rb.count):
            b = v4l2_buffer(index=i, type=buf_type, memory=V4L2_MEMORY_MMAP)
            xioctl(fd, VIDIOC_QUERYBUF, b, f"{what} VIDIOC_QUERYBUF")
            self.maps.append(mmap.mmap(fd, b.length, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE,
                                       offset=b.m.offset))
            self.lengths.append(b.length)
        for i in range(rb.count):
            self.qbuf(i)
        self.count = rb.count

    def qbuf(self, index: int) -> None:
        b = v4l2_buffer(index=index, type=self.type, memory=V4L2_MEMORY_MMAP)
        xioctl(self.fd, VIDIOC_QBUF, b, f"{self.what} VIDIOC_QBUF")

    def dqbuf(self) -> tuple[v4l2_buffer, int] | None:
        b = v4l2_buffer(type=self.type, memory=V4L2_MEMORY_MMAP)
        try:
            fcntl.ioctl(self.fd, VIDIOC_DQBUF, b)
        except InterruptedError:
            return None
        except OSError as e:
            if e.errno == errno.EAGAIN:
                return None
            raise V4L2Error(f"{self.what} VIDIOC_DQBUF", e) from None
        return b, mono_ns()

    def streamon(self) -> None:
        xioctl(self.fd, VIDIOC_STREAMON, struct.pack("i", self.type), f"{self.what} VIDIOC_STREAMON")

    def close(self) -> None:
        try:
            fcntl.ioctl(self.fd, VIDIOC_STREAMOFF, struct.pack("i", self.type))
        except OSError:
            pass
        for m in self.maps:
            try:
                m.close()
            except (BufferError, ValueError):
                pass
        self.maps = []
        try:
            fcntl.ioctl(self.fd, VIDIOC_REQBUFS, v4l2_requestbuffers(count=0, type=self.type, memory=V4L2_MEMORY_MMAP))
        except OSError:
            pass


def query_control(fd: int, name: str, cid: int) -> dict:
    q = v4l2_queryctrl(id=cid)
    try:
        xioctl(fd, VIDIOC_QUERYCTRL, q, "VIDIOC_QUERYCTRL")
    except OSError as e:
        return {"present": False, "query_error": str(e)}
    out = {"present": True, "id": f"0x{cid:08x}", "name": _cstr(q.name), "min": q.minimum, "max": q.maximum,
           "step": q.step, "default": q.default_value, "flags": f"0x{q.flags:x}"}
    c = v4l2_control(id=cid)
    try:
        xioctl(fd, VIDIOC_G_CTRL, c, "VIDIOC_G_CTRL")
        out["value"] = c.value
    except OSError as e:
        out["get_error"] = str(e)
    return out


def set_control(fd: int, cid: int, value: int) -> str | None:
    try:
        xioctl(fd, VIDIOC_S_CTRL, v4l2_control(id=cid, value=value), "VIDIOC_S_CTRL")
        return None
    except OSError as e:
        return str(e)


def read_controls(fd: int) -> dict:
    return {k: query_control(fd, k, cid) for k, cid in CONTROLS.items()}


class CameraCapture:
    def __init__(self, cam: dict, args, env: dict, out_dir: Path):
        self.cam, self.args, self.env, self.out_dir = cam, args, env, out_dir
        self.key = cam["camera_key"]
        self.fname = safe_name(self.key)
        self.res: dict = {"camera_key": self.key, "device": cam["device"], "meta_node": cam.get("meta_node"),
                          "frames_file": f"{self.fname}.frames.jsonl", "error": None, "warnings": []}
        self.vfd = self.mfd = None
        self.vq: MmapQueue | None = None
        self.mq: MmapQueue | None = None
        hdr = cam.get("uvc_vc_header") or {}
        self.device_clock_hz = hdr.get("dwClockFrequency") or None
        self.hwts = hwts_on(env)
        self.realtime = clock_is_realtime(env)

    # ------------------------------------------------------------------ setup (main thread)
    def setup(self) -> None:
        a, cam, r = self.args, self.cam, self.res
        if not cam.get("is_capture"):
            raise RuntimeError(f"{cam['device']} is not a video capture node (device_caps {cam.get('device_caps')})")
        if not cam.get("has_streaming"):
            raise RuntimeError(f"{cam['device']} does not support streaming I/O")
        try:
            self.vfd = os.open(cam["device"], os.O_RDWR | os.O_NONBLOCK)
        except OSError as e:
            hint = " - add your user to group 'video' (then log in again)" if e.errno in (errno.EACCES, errno.EPERM) else ""
            raise RuntimeError(f"cannot open {cam['device']}: {e.strerror}{hint}") from None
        fd = self.vfd
        r["controls_initial"] = read_controls(fd)
        # format
        f = v4l2_format(type=V4L2_BUF_TYPE_VIDEO_CAPTURE)
        f.fmt.pix.width, f.fmt.pix.height = a.width, a.height
        f.fmt.pix.pixelformat, f.fmt.pix.field = V4L2_PIX_FMT_MJPEG, V4L2_FIELD_ANY
        try:
            xioctl(fd, VIDIOC_S_FMT, f, "VIDIOC_S_FMT")
        except OSError as e:
            if e.errno == errno.EBUSY:
                raise RuntimeError(f"{cam['device']} is busy (another program is streaming it; try `fuser {cam['device']}`)") from None
            raise
        p = f.fmt.pix
        r["format"] = {"pixelformat": fourcc_str(p.pixelformat), "width": p.width, "height": p.height,
                       "bytesperline": p.bytesperline, "sizeimage": p.sizeimage, "field": p.field,
                       "colorspace": p.colorspace}
        if p.pixelformat != V4L2_PIX_FMT_MJPEG:
            raise RuntimeError(f"{cam['device']}: driver returned {fourcc_str(p.pixelformat)} instead of MJPG "
                               f"(formats offered: {cam.get('formats')})")
        if (p.width, p.height) != (a.width, a.height):
            sizes = [m.get("size") for m in cam.get("mjpeg_modes") or []]
            raise RuntimeError(f"{cam['device']}: {a.width}x{a.height} MJPEG not offered, driver chose {p.width}x{p.height}. "
                               f"MJPEG sizes: {sizes}")
        # frame rate
        sp = v4l2_streamparm(type=V4L2_BUF_TYPE_VIDEO_CAPTURE)
        sp.parm.capture.timeperframe.numerator = 1000
        sp.parm.capture.timeperframe.denominator = int(round(a.fps * 1000))
        xioctl(fd, VIDIOC_S_PARM, sp, "VIDIOC_S_PARM")
        tpf = sp.parm.capture.timeperframe
        got_fps = tpf.denominator / tpf.numerator if tpf.numerator else None
        r["streamparm"] = {"timeperframe": [tpf.numerator, tpf.denominator], "fps": got_fps,
                           "capability_timeperframe": bool(sp.parm.capture.capability & V4L2_CAP_TIMEPERFRAME)}
        if got_fps is None or abs(got_fps - a.fps) / a.fps > 0.01:
            r["warnings"].append(f"requested {a.fps} fps, driver set {got_fps}")
        # controls (after S_FMT/S_PARM, before streaming)
        sets = {}
        if a.exposure_abs is not None:
            sets["exposure_auto"] = (CONTROLS["exposure_auto"], V4L2_EXPOSURE_MANUAL)
            sets["exposure_auto_priority"] = (CONTROLS["exposure_auto_priority"], 0)
            sets["exposure_absolute"] = (CONTROLS["exposure_absolute"], a.exposure_abs)
            if got_fps and a.exposure_abs * 100e-6 > 1.0 / got_fps:
                r["warnings"].append(f"exposure {a.exposure_abs * 0.1:.1f} ms is longer than the frame period "
                                     f"{1000 / got_fps:.1f} ms; the camera will lower its frame rate")
        if a.wb_k is not None:
            sets["white_balance_automatic"] = (CONTROLS["white_balance_automatic"], 0)
            sets["white_balance_temperature"] = (CONTROLS["white_balance_temperature"], a.wb_k)
        r["control_sets"] = {}
        for name, (cid, val) in sets.items():  # dict order = the order that matters (auto off first)
            err = set_control(fd, cid, val)
            r["control_sets"][name] = {"requested": val, "error": err}
            if err:
                r["warnings"].append(f"set {name}={val}: {err}")
        r["controls_after_set"] = read_controls(fd)
        if (r["controls_after_set"].get("exposure_auto_priority") or {}).get("value") == 1:
            r["warnings"].append("exposure_auto_priority=1: the camera may lower the frame rate in low light "
                                 "(pass --exposure-abs to lock exposure and clear it)")
        # metadata node (non-fatal)
        if cam.get("meta_node") and not a.no_meta:
            try:
                self._setup_meta(cam["meta_node"])
            except (OSError, RuntimeError) as e:
                r["meta_error"] = str(e)
                r["warnings"].append(f"metadata disabled: {e}")
                if self.mfd is not None:
                    if self.mq:
                        self.mq.close()
                        self.mq = None
                    os.close(self.mfd)
                    self.mfd = None
        elif not cam.get("meta_node"):
            r["meta_error"] = "no metadata node paired with this camera"
        # video buffers last (REQBUFS locks the format)
        self.vq = MmapQueue(fd, V4L2_BUF_TYPE_VIDEO_CAPTURE, a.buffers, "video")
        r["video_buffers"] = {"count": self.vq.count, "length": self.vq.lengths[0]}

    def _setup_meta(self, node: str) -> None:
        try:
            self.mfd = os.open(node, os.O_RDWR | os.O_NONBLOCK)
        except OSError as e:
            raise RuntimeError(f"cannot open metadata node {node}: {e.strerror}") from None
        f = v4l2_format(type=V4L2_BUF_TYPE_META_CAPTURE)
        f.fmt.meta.dataformat = V4L2_META_FMT_UVC
        xioctl(self.mfd, VIDIOC_S_FMT, f, "meta VIDIOC_S_FMT")
        if f.fmt.meta.dataformat != V4L2_META_FMT_UVC:
            raise RuntimeError(f"metadata node {node} kept format {fourcc_str(f.fmt.meta.dataformat)}, not UVCH")
        self.res["meta_format"] = {"dataformat": fourcc_str(f.fmt.meta.dataformat), "buffersize": f.fmt.meta.buffersize}
        self.mq = MmapQueue(self.mfd, V4L2_BUF_TYPE_META_CAPTURE, self.args.buffers, "meta")
        self.res["meta_buffers"] = {"count": self.mq.count, "length": self.mq.lengths[0]}

    # ------------------------------------------------------------------ capture loop (own thread)
    def run(self, barrier: threading.Barrier, stop: threading.Event) -> None:
        r = self.res
        c = {"frames": 0, "frames_with_meta": 0, "video_error_flag": 0, "seq_missing": 0, "invalid_jpeg": 0,
             "meta_buffers": 0, "meta_empty": 0, "meta_error_flag": 0, "meta_orphans": 0, "meta_blocks_total": 0,
             "meta_length_ne_std": 0, "meta_truncated": 0, "hwts_mapped": 0, "hwts_not_mapped": 0,
             "poll_timeouts": 0, "poll_err_events": 0}
        ts_kinds: dict[str, int] = {}
        r["counters"], r["timestamp_flag_kinds"], r["meta_raw_samples"] = c, ts_kinds, []
        pending: dict[int, dict] = {}       # seq -> frame row awaiting its metadata
        meta_by_seq: dict[int, dict] = {}   # seq -> parsed metadata awaiting its frame
        last_seq = None
        sample_saved = False
        out = open(self.out_dir / r["frames_file"], "w", buffering=1 << 20)
        try:
            try:
                barrier.wait(timeout=15)
            except threading.BrokenBarrierError:
                r["warnings"].append("start barrier broken (another camera failed); starting anyway")
            if self.mq:
                self.mq.streamon()          # meta first so the first frames already have a metadata buffer
            try:
                self.vq.streamon()
            except OSError as e:
                if e.errno == errno.ENOSPC:
                    raise RuntimeError("VIDIOC_STREAMON: ENOSPC - not enough USB bandwidth for this mode "
                                       "(too many cameras on one bus/root port)") from None
                raise
            t0 = mono_ns()
            r["streamon_monotonic_ns"] = t0
            deadline = t0 + int(self.args.seconds * 1e9)
            last_frame_t = t0
            poller = select.poll()
            poller.register(self.vfd, select.POLLIN | select.POLLPRI)
            if self.mq:
                poller.register(self.mfd, select.POLLIN)
            mfd_err = 0

            def emit(row: dict) -> None:
                out.write(json.dumps(row, separators=(",", ":")) + "\n")

            def attach(row: dict, m: dict | None) -> dict:
                if m is not None:
                    row.update(m["fields"])
                    c["frames_with_meta"] += 1
                    if self.hwts:
                        mapped = row["os_timestamp_ns"] != row["meta_buf_timestamp_ns"]
                        row["hwts_mapped"] = mapped
                        c["hwts_mapped" if mapped else "hwts_not_mapped"] += 1
                return row

            while not stop.is_set():
                now = mono_ns()
                if now >= deadline:
                    break
                evs = poller.poll(500)
                if not evs:
                    c["poll_timeouts"] += 1
                    if mono_ns() - last_frame_t > 5e9:
                        raise RuntimeError("no frames for 5 s after STREAMON")
                    continue
                for fd, ev in evs:
                    if ev & (select.POLLERR | select.POLLHUP | select.POLLNVAL):
                        c["poll_err_events"] += 1
                    if fd == self.mfd:
                        if ev & select.POLLERR and not ev & select.POLLIN:
                            mfd_err += 1
                            if mfd_err > 200:   # vb2 poll keeps returning EPOLLERR: give up on metadata
                                poller.unregister(self.mfd)
                                r["warnings"].append("metadata fd returned POLLERR repeatedly; metadata stopped")
                            continue
                        while (got := self.mq.dqbuf()) is not None:
                            b, _t = got
                            c["meta_buffers"] += 1
                            used = b.bytesused
                            data = self.mq.maps[b.index][:used] if used else b""
                            self.mq.qbuf(b.index)
                            if not used:
                                c["meta_empty"] += 1
                            if b.flags & V4L2_BUF_FLAG_ERROR:
                                c["meta_error_flag"] += 1
                            if len(r["meta_raw_samples"]) < 4 and used:
                                r["meta_raw_samples"].append({"sequence": b.sequence, "bytesused": used,
                                                              "hex": data[:256].hex()})
                            blocks, an = parse_uvc_meta(data)
                            c["meta_blocks_total"] += len(blocks)
                            c["meta_length_ne_std"] += an["length_ne_std"]
                            c["meta_truncated"] += an["truncated"]
                            m = {"fields": self._meta_fields(b, blocks)}
                            seq = b.sequence
                            if seq in pending:
                                emit(attach(pending.pop(seq), m))
                            else:
                                meta_by_seq[seq] = m
                    elif fd == self.vfd:
                        if ev & select.POLLERR and not ev & select.POLLIN:
                            if not self.vq.dqbuf():
                                continue
                        while (got := self.vq.dqbuf()) is not None:
                            b, t_host = got
                            last_frame_t = t_host
                            mm = self.vq.maps[b.index]
                            used = b.bytesused
                            soi = used >= 2 and mm[0:2] == b"\xff\xd8"
                            eoi = used >= 2 and b"\xff\xd9" in mm[max(0, used - 64):used]
                            if not sample_saved and c["frames"] >= 30 and soi and eoi:
                                (self.out_dir / f"{self.fname}.sample.jpg").write_bytes(mm[:used])
                                r["sample_jpeg"] = f"{self.fname}.sample.jpg"
                                sample_saved = True
                            self.vq.qbuf(b.index)
                            row = self._frame_row(b, t_host, used, soi, eoi)
                            ts_kinds[row["v4l2_ts_kind"]] = ts_kinds.get(row["v4l2_ts_kind"], 0) + 1
                            c["frames"] += 1
                            if b.flags & V4L2_BUF_FLAG_ERROR:
                                c["video_error_flag"] += 1
                            if not (soi and eoi):
                                c["invalid_jpeg"] += 1
                            if last_seq is not None and b.sequence > last_seq + 1:
                                c["seq_missing"] += b.sequence - last_seq - 1
                            last_seq = b.sequence
                            if self.mq is None:
                                emit(row)
                            elif b.sequence in meta_by_seq:
                                emit(attach(row, meta_by_seq.pop(b.sequence)))
                            else:
                                pending[b.sequence] = row
                # flush frames whose metadata will not come; drop metadata whose frame was not seen
                if pending:
                    now = mono_ns()
                    newest_meta = max(meta_by_seq) if meta_by_seq else -1
                    for s in sorted(pending):
                        if now - pending[s]["host_arrival_ns"] > 300e6 or s < newest_meta or len(pending) > 8:
                            emit(attach(pending.pop(s), None))
                if meta_by_seq and last_seq is not None:
                    for s in [s for s in meta_by_seq if s < last_seq - 16]:
                        del meta_by_seq[s]
                        c["meta_orphans"] += 1
            r["capture_seconds"] = (mono_ns() - t0) / 1e9
            for s in sorted(pending):
                emit(attach(pending.pop(s), meta_by_seq.pop(s, None)))
            c["meta_orphans"] += len(meta_by_seq)
            if c["frames"] == 0:
                r["error"] = "no frames captured"
        except Exception as e:  # noqa: BLE001 - recorded in the session JSON
            r["error"] = f"{type(e).__name__}: {e}"
            for s in sorted(pending):
                emit(attach(pending.pop(s), None))
        finally:
            out.close()
            self.close()
            r["controls_final"] = None
            if self.vfd is not None:
                pass

    def _frame_row(self, b: v4l2_buffer, t_host: int, used: int, soi: bool, eoi: bool) -> dict:
        ttype, tsrc = decode_ts_flags(b.flags)
        raw = ts_ns(b.timestamp)
        row = {"camera_key": self.key, "backend": "v4l2", "seq": b.sequence, "host_arrival_ns": t_host}
        if self.realtime:
            off = time.clock_gettime_ns(time.CLOCK_REALTIME) - mono_ns()
            row["os_timestamp_ns"] = raw - off
            row["realtime_minus_monotonic_ns_at_arrival"] = off
            src = f"v4l2_buffer_{tsrc}_uvc_clock_realtime_converted"
        else:
            row["os_timestamp_ns"] = raw
            src = f"v4l2_buffer_{tsrc}"
        if self.hwts:
            src += "_hwtimestamps1"   # value may be the SCR-mapped PTS (see hwts_mapped)
        kind = f"{ttype}/{tsrc}"
        row.update({"os_timestamp_source": src, "uvc_pts": None, "uvc_scr_stc": None, "uvc_scr_sof": None,
                    "device_clock_hz": self.device_clock_hz, "payload_bytes": used, "is_valid_jpeg": bool(soi and eoi),
                    "jpeg_soi": soi, "jpeg_eoi": eoi, "v4l2_index": b.index, "v4l2_flags": b.flags,
                    "v4l2_ts_type": ttype, "v4l2_ts_src": tsrc, "v4l2_ts_kind": kind,
                    "v4l2_buf_error": bool(b.flags & V4L2_BUF_FLAG_ERROR),
                    "v4l2_ts_sec": int(b.timestamp.tv_sec), "v4l2_ts_usec": int(b.timestamp.tv_usec)})
        return row

    def _meta_fields(self, b: v4l2_buffer, blocks: list[dict]) -> dict:
        conv = 0
        if self.realtime:
            conv = time.clock_gettime_ns(time.CLOCK_REALTIME) - mono_ns()
        f = {"meta_seq": b.sequence, "meta_bytesused": b.bytesused, "meta_blocks": len(blocks),
             "meta_buf_error": bool(b.flags & V4L2_BUF_FLAG_ERROR),
             "meta_buf_timestamp_ns": ts_ns(b.timestamp) - conv}
        if blocks:
            first, last = blocks[0], blocks[-1]
            first_pts = next((x["pts"] for x in blocks if x["pts"] is not None), None)
            f.update({"uvc_pts": first_pts, "uvc_scr_stc": first["stc"], "uvc_scr_sof": first["dev_sof"],
                      "uvc_host_sof": first["host_sof"], "uvc_host_sof_ns": first["ns"] - conv,
                      "uvc_eof_pts": last["pts"], "uvc_eof_scr_stc": last["stc"], "uvc_eof_scr_sof": last["dev_sof"],
                      "uvc_eof_host_sof": last["host_sof"], "uvc_eof_host_sof_ns": last["ns"] - conv,
                      "meta_first_flags": first["flags"], "meta_last_flags": last["flags"],
                      "meta_first_header_length": first["header_length"],
                      "meta_eof_bit_seen": any(x["flags"] & UVC_STREAM_EOF for x in blocks),
                      "meta_err_bit_seen": any(x["flags"] & UVC_STREAM_ERR for x in blocks)})
        return f

    def close(self) -> None:
        if self.vq:
            try:
                self.res["controls_final"] = read_controls(self.vfd)
            except OSError:
                pass
            self.vq.close()   # STREAMOFF video first
            self.vq = None
        if self.mq:
            self.mq.close()
            self.mq = None
        for attr in ("vfd", "mfd"):
            fd = getattr(self, attr)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
                setattr(self, attr, None)


# ===================================================================================== self-test
def self_test() -> int:
    ok = True
    for st, size in EXPECTED_SIZES.items():
        if C.sizeof(st) != size:
            print(f"FAIL sizeof({st.__name__}) = {C.sizeof(st)} != {size}")
            ok = False
    for name, off in EXPECTED_OFFSETS.items():
        got = getattr(v4l2_buffer, name).offset
        if got != off:
            print(f"FAIL offsetof(v4l2_buffer.{name}) = {got} != {off}")
            ok = False
    if v4l2_format.fmt.offset != 8:
        print(f"FAIL offsetof(v4l2_format.fmt) = {v4l2_format.fmt.offset} != 8")
        ok = False
    if v4l2_streamparm.parm.offset != 4 or v4l2_captureparm.timeperframe.offset != 8:
        print("FAIL v4l2_streamparm layout")
        ok = False
    g = globals()
    for name, val in EXPECTED_IOCTLS.items():
        if g[name] != val:
            print(f"FAIL {name} = 0x{g[name]:08x} != 0x{val:08x}")
            ok = False
    if fourcc("UVCH") != 0x48435655 or fourcc("MJPG") != 0x47504A4D:
        print("FAIL fourcc")
        ok = False
    # synthetic metadata buffer: block 1 PTS+SCR (bHeaderLength 12), block 2 SCR only, block 3 PTS+SCR with a
    # 16-byte vendor header (length field 16, but only the 12 standard bytes are stored)
    def blk(ns, sof, length, flags, pts=None, stc=None, dsof=None):
        b = struct.pack("<QHBB", ns, sof, length, flags)
        if pts is not None:
            b += struct.pack("<I", pts)
        if stc is not None:
            b += struct.pack("<IH", stc, dsof)
        return b
    data = (blk(1000, 0x1234, 12, 0x0C | 0x80, pts=0xAABBCCDD, stc=0x11223344, dsof=0x0FFF)
            + blk(2000, 0x1235, 8, 0x08 | 0x80, stc=0x11223355, dsof=0x0123)
            + blk(3000, 0x1236, 16, 0x0E | 0x80, pts=0xAABBCCDD, stc=0x11223366, dsof=0x0124))
    bl, an = parse_uvc_meta(data)
    exp = [(1000, 0x1234, 0xAABBCCDD, 0x11223344, 0x07FF), (2000, 0x1235, None, 0x11223355, 0x0123),
           (3000, 0x1236, 0xAABBCCDD, 0x11223366, 0x0124)]
    got = [(x["ns"], x["host_sof"], x["pts"], x["stc"], x["dev_sof"]) for x in bl]
    if got != exp or an["length_ne_std"] != 1 or an["truncated"]:
        print(f"FAIL parse_uvc_meta: {got} {an}")
        ok = False
    bl2, an2 = parse_uvc_meta(data[:-3])
    if len(bl2) != 2 or an2["truncated"] != 1:
        print(f"FAIL parse_uvc_meta truncated: {bl2} {an2}")
        ok = False
    if decode_ts_flags(0x2000 | 0x10000) != ("monotonic", "soe") or decode_ts_flags(0x4000) != ("copy", "eof"):
        print("FAIL decode_ts_flags")
        ok = False
    cams = [{"vid": "046d", "pid": "085c", "serial": "ABC123", "port_path": "pci-x/1"},
            {"vid": "046d", "pid": "085c", "serial": "0000", "port_path": "pci-x/2"},
            {"vid": "1532", "pid": "0e05", "serial": "S1", "port_path": "pci-x/3"},
            {"vid": "1532", "pid": "0e05", "serial": "S1", "port_path": "pci-x/4"}]
    assign_camera_keys(cams)
    keys = [x["camera_key"] for x in cams]
    if keys != ["046d:085c:sn=ABC123", "046d:085c:port=pci-x/2", "1532:0e05:port=pci-x/3", "1532:0e05:port=pci-x/4"]:
        print(f"FAIL camera keys {keys}")
        ok = False
    print("self-test", "OK" if ok else "FAILED", f"(python {platform.python_version()}, {platform.machine()})")
    return 0 if ok else 1


# ===================================================================================== main
def parse_size(s: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d+)[xX](\d+)", s.strip())
    if not m:
        raise argparse.ArgumentTypeError(f"--size must look like 1280x720, got {s!r}")
    return int(m.group(1)), int(m.group(2))


def platform_check() -> str | None:
    if not sys.platform.startswith("linux"):
        return f"this test is for Linux (sys.platform={sys.platform}); only --self-test runs elsewhere"
    if fcntl is None:
        return "fcntl module not available"
    m = platform.machine().lower()
    if m not in ("x86_64", "amd64", "aarch64", "arm64") or C.sizeof(C.c_long) != 8:
        return f"unsupported machine {platform.machine()} (c_long={C.sizeof(C.c_long)} bytes); structs are for LP64 x86_64/aarch64"
    if not hasattr(time, "clock_gettime_ns"):
        return "time.clock_gettime_ns not available"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="V4L2/uvcvideo per-frame timing capture (UNVERIFIED draft)")
    ap.add_argument("--device", action="append", default=[], help="/dev/videoN capture node (repeat for several cameras)")
    ap.add_argument("--size", type=parse_size, default=(1280, 720), help="WxH, default 1280x720")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--exposure-abs", type=int, default=None,
                    help="V4L2_CID_EXPOSURE_ABSOLUTE in 100 us units (sets exposure_auto=1 manual, auto_priority=0)")
    ap.add_argument("--wb-k", type=int, default=None, help="white balance temperature in K (sets auto WB off)")
    ap.add_argument("--buffers", type=int, default=8, help="mmap buffers per queue (video and metadata)")
    ap.add_argument("--no-meta", action="store_true", help="do not stream the metadata node")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--tag", default=None, help="sub-directory under the test result dir")
    ap.add_argument("--list", action="store_true", help="print UVC cameras + metadata pairing as JSON and exit")
    ap.add_argument("--list-out", type=Path, default=None, help="with --list: also write the JSON to this file")
    ap.add_argument("--self-test", action="store_true", help="check struct sizes / ioctl numbers / parser (any OS)")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    err = platform_check()
    if err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    if a.seconds <= 0 or a.fps <= 0 or a.buffers < 2:
        print("error: --seconds and --fps must be > 0 and --buffers >= 2", file=sys.stderr)
        return 2
    a.width, a.height = a.size
    host = socket.gethostname().split(".")[0]
    env = environment()
    if not env["uvcvideo_module_loaded"]:
        print("warning: uvcvideo module not loaded (/sys/module/uvcvideo missing)", file=sys.stderr)
    nodes = enumerate_nodes()
    cams = uvc_cameras(nodes)
    if a.list:
        doc = {"test": f"{TEST_NAME}.list", "status": STATUS, "platform": "linux", "hostname": host,
               "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(),
               "command": " ".join(shlex.quote(x) for x in sys.argv), "environment": env,
               "cameras": [{k: c.get(k) for k in ("device", "camera_key", "camera_key_kind", "card", "bus_info",
                                                  "vid", "pid", "serial", "product", "usb_speed_mbps", "port_path",
                                                  "meta_node", "meta_pairing", "meta_formats", "meta_supports_uvch",
                                                  "meta_same_sysfs_parent", "formats", "mjpeg_modes",
                                                  "uvc_vc_header", "error")}
                           for c in cams],
               "all_v4l2_nodes": nodes}
        txt = json.dumps(doc, indent=1, default=str)
        if a.list_out:
            a.list_out.parent.mkdir(parents=True, exist_ok=True)
            a.list_out.write_text(txt)
        print(txt)
        return 0
    if not a.device:
        print("error: pass --device /dev/videoN (repeatable), or --list to see cameras", file=sys.stderr)
        return 2
    selected = []
    for d in a.device:
        real = os.path.realpath(d)
        c = next((x for x in cams if x["device"] == real), None)
        if c is None:
            n = next((x for x in nodes if x["device"] == real), None)
            if n is None:
                print(f"error: {d} ({real}) is not a V4L2 device in /sys/class/video4linux", file=sys.stderr)
            elif n.get("error"):
                print(f"error: {d}: {n['error']}", file=sys.stderr)
            elif n.get("is_meta"):
                print(f"error: {d} is a metadata node; pass the video capture node", file=sys.stderr)
            else:
                print(f"error: {d} is not a uvcvideo capture node (driver={n.get('driver')})", file=sys.stderr)
            return 2
        if any(s["device"] == real for s in selected):
            print(f"error: {d} given twice", file=sys.stderr)
            return 2
        selected.append(c)
    out_dir = a.out_dir or (RESEARCH_ROOT / "results" / "linux" / host / "timing" / TEST_NAME)
    if a.tag:
        out_dir = out_dir / safe_name(a.tag)
    out_dir.mkdir(parents=True, exist_ok=True)
    session = {"test": TEST_NAME, "status": STATUS, "platform": "linux", "hostname": host,
               "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(),
               "command": " ".join(shlex.quote(x) for x in sys.argv), "environment": env,
               "args": {"devices": a.device, "width": a.width, "height": a.height, "fps": a.fps, "seconds": a.seconds,
                        "exposure_abs": a.exposure_abs, "wb_k": a.wb_k, "buffers": a.buffers, "no_meta": a.no_meta,
                        "tag": a.tag},
               "host_clock": "CLOCK_MONOTONIC (time.clock_gettime_ns)",
               "notes": [
                   "is_valid_jpeg = SOI at start and EOI within the last 64 bytes; payload is not decoded",
                   "v4l2_buffer.timestamp has microsecond resolution (struct timeval); metadata ns fields are ns",
                   "host_arrival_ns is taken in Python after DQBUF returns: includes poll wake-up and GIL latency",
                   "hwtimestamps=1: os_timestamp_ns may be the kernel's SCR-mapped PTS; meta_buf_timestamp_ns keeps the SOE "
                   "host time; hwts_mapped tells which (UNVERIFIED assumption, see module docstring)",
                   "uvc_* fields come from the first/last metadata block of the frame; blocks exist only for headers "
                   "whose SCR changed (uvc_video_decode_meta), so 'first block' is the first SCR-bearing header",
               ],
               "cameras": []}
    if clock_is_realtime(env):
        session["notes"].append("uvcvideo clock=CLOCK_REALTIME: kernel timestamps converted to CLOCK_MONOTONIC with "
                                "the offset sampled at dequeue (realtime_minus_monotonic_ns_at_arrival)")
    if hwts_on(env):
        session["notes"].append("uvcvideo hwtimestamps=1 during this run")
    caps = []
    for c in selected:
        cc = CameraCapture(c, a, env, out_dir)
        try:
            cc.setup()
            caps.append(cc)
        except Exception as e:  # noqa: BLE001
            cc.res["error"] = f"setup: {type(e).__name__}: {e}"
            cc.close()
            print(f"error: {c['device']}: {cc.res['error']}", file=sys.stderr)
        session["cameras"].append({**{k: c.get(k) for k in ("device", "camera_key", "camera_key_kind", "card",
                                                             "bus_info", "vid", "pid", "serial", "product",
                                                             "manufacturer", "usb_speed_mbps", "sysfs_usb_name",
                                                             "port_path", "meta_node", "meta_pairing", "meta_formats",
                                                             "meta_supports_uvch", "uvc_vc_header", "mjpeg_modes")},
                                   "capture": cc.res})
    stop = threading.Event()

    def on_signal(signum, _frame):
        stop.set()
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    threads = []
    if caps:
        barrier = threading.Barrier(len(caps))
        for cc in caps:
            t = threading.Thread(target=cc.run, args=(barrier, stop), name=cc.key, daemon=True)
            threads.append(t)
            t.start()
        print(f"capturing {len(caps)} camera(s) for {a.seconds:.0f} s at {a.width}x{a.height}@{a.fps:g} MJPEG "
              f"(hwtimestamps={env.get('uvcvideo_hwtimestamps')}, clock={env.get('uvcvideo_clock')}) ...", file=sys.stderr)
        for t in threads:
            while t.is_alive():
                t.join(0.5)
    session["utc_finished"] = dt.datetime.now(dt.timezone.utc).isoformat()
    (out_dir / "session.json").write_text(json.dumps(session, indent=1, default=str))
    rc = 0
    for cam in session["cameras"]:
        r = cam["capture"]
        cnt = r.get("counters") or {}
        print(f"{cam['device']} {cam['camera_key']}: frames={cnt.get('frames', 0)} with_meta={cnt.get('frames_with_meta', 0)} "
              f"seq_missing={cnt.get('seq_missing', 0)} ts={r.get('timestamp_flag_kinds')} "
              f"error={r.get('error')}", file=sys.stderr)
        for w in r.get("warnings", []):
            print(f"   warning: {w}", file=sys.stderr)
        if r.get("error"):
            rc = 1
    print(f"wrote {out_dir / 'session.json'}", file=sys.stderr)
    print(str(out_dir))   # stdout: result directory (used by run_linux_timing.sh)
    return rc


if __name__ == "__main__":
    sys.exit(main())
