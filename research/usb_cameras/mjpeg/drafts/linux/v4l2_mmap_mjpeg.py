# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "simplejpeg>=1.7", "psutil>=5.9"]
# ///
"""UNVERIFIED DRAFT -- written on Windows, never run on Linux. Only --selftest (struct sizes + ioctl numbers)
has been executed (on Windows x64). Treat every result as suspect until the first Linux run is reviewed.

Pure-Python V4L2 mmap capture of native MJPEG (raw ioctls via fcntl + ctypes; no linuxpy, no OpenCV, no FFmpeg).

HARDWARE / PERMISSIONS
  64-bit Linux (x86_64 or aarch64), one or more UVC cameras that offer MJPG. No sudo: the user must be able to
  open /dev/videoN read-write, i.e. be in the 'video' group (check: `id -nG | grep -w video`;
  fix: `sudo usermod -aG video $USER`, then log out and back in). No system packages needed (v4l-utils optional).
  Nothing else may hold the camera open (close browsers / Cheese / OBS).

WHAT TO RUN (from the repo root)
  uv run --script research/usb_cameras/mjpeg/drafts/linux/v4l2_mmap_mjpeg.py --selftest
  uv run --script research/usb_cameras/mjpeg/drafts/linux/v4l2_mmap_mjpeg.py --list          # JSON to stdout
  uv run --script research/usb_cameras/mjpeg/drafts/linux/v4l2_mmap_mjpeg.py \
      --device /dev/video0 [--device /dev/video2 ...] --size 1280x720 --fps 30 --seconds 10 --warmup 2 \
      [--exposure-abs 78] [--manual-wb 4500] [--label NAME] [--run-dir DIR] [--keep-samples 1]
  or run the whole matrix: bash research/usb_cameras/mjpeg/drafts/linux/run_linux_mjpeg.sh

WHAT IT WRITES
  --list:   research/usb_cameras/results/linux/<hostname>/mjpeg_v4l2_list/devices.json (+ the JSON on stdout)
  capture:  research/usb_cameras/results/linux/<hostname>/mjpeg_v4l2_mmap/<label>/summary.json + frames.jsonl
            (+ sample_*.jpg with --keep-samples). Default label: <W>x<H>at<fps>_<videoN>[+<videoM>...].
            The raw run dir (meta.json, frames.jsonl, frames_<i>.bin) goes to --run-dir, default a fresh dir
            under $MJPEG_SCRATCH or <tmp>/usb_cameras_mjpeg_scratch. summary.json has the same shape as the
            Windows backends (mjpeg_common.summarize_run): fps achieved vs requested, % valid JPEG (SOI/EOI +
            Pillow + libjpeg-turbo decode), payload sizes, process CPU %, decoded_by_pipeline (always False
            here: bytes are copied straight out of the mmap'd V4L2 buffer, nothing decodes them during capture).
  Exit code: 0 ok, 2 = driver substituted a non-MJPEG pixelformat (silent_format_fallback=true; that camera is
  not streamed unless --capture-anyway), 1 = other failure.

PER-FRAME LOG (README schema + extras)
  host_arrival_ns  time.clock_gettime_ns(CLOCK_MONOTONIC) right after VIDIOC_DQBUF returns
  os_timestamp_ns  v4l2_buffer.timestamp (struct timeval) -> ns. With V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC this is
                   CLOCK_MONOTONIC (same clock as host_arrival_ns). uvcvideo stamps at start of exposure/first
                   USB packet (TSTAMP_SRC_SOE) unless uvcvideo hwtimestamps=1 (then SCR-derived). If the flag is
                   not MONOTONIC the raw value is still logged; meta.backend_details has the realtime-monotonic
                   offset for converting.
  v4l2_sequence, v4l2_flags (raw) + v4l2_flags_decoded (names), v4l2_ts_type, v4l2_ts_src, v4l2_error,
  bytesused (== payload_bytes), v4l2_index (mmap buffer index).

STRUCT LAYOUTS follow include/uapi/linux/videodev2.h as of Linux v6.8 (struct v4l2_requestbuffers with
'flags'+'reserved[3]' (v6.1+; same size as the older reserved[1]), v4l2_fmtdesc with 'mbus_code' (v5.8+; same
size), v4l2_buffer with request_fd (v4.20+; same size)). Layouts are for 64-bit (LP64) userspace; aarch64 and
x86_64 are identical. 32-bit userspace is NOT supported (timeval/pointer sizes differ) and is refused at runtime.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
import select
import sys
import threading
import time
from fractions import Fraction
from pathlib import Path

try:  # guarded so --selftest runs on Windows (ctypes layout check only)
    import fcntl
    import mmap
except ImportError:  # pragma: no cover
    fcntl = None

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))  # drafts/linux -> mjpeg/
import mjpeg_common as mc  # noqa: E402

TEST = "mjpeg_v4l2_mmap"
BACKEND = "v4l2-mmap-python"

# ---------------------------------------------------------------- ioctl encoding (include/uapi/asm-generic/ioctl.h)
# x86_64 and arm64 both use the asm-generic encoding: nr 8 bits, type 8, size 14, dir 2; WRITE=1, READ=2.
_IOC_NRBITS, _IOC_TYPEBITS, _IOC_SIZEBITS = 8, 8, 14
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS
_IOC_NONE, _IOC_WRITE, _IOC_READ = 0, 1, 2


def _IOC(d: int, t: str, nr: int, size: int) -> int:
    assert size < (1 << _IOC_SIZEBITS)
    return (d << _IOC_DIRSHIFT) | (ord(t) << _IOC_TYPESHIFT) | (nr << _IOC_NRSHIFT) | (size << _IOC_SIZESHIFT)


def _IOR(t, nr, st): return _IOC(_IOC_READ, t, nr, ctypes.sizeof(st))
def _IOW(t, nr, st): return _IOC(_IOC_WRITE, t, nr, ctypes.sizeof(st))
def _IOWR(t, nr, st): return _IOC(_IOC_READ | _IOC_WRITE, t, nr, ctypes.sizeof(st))


# ---------------------------------------------------------------- structs (linux/videodev2.h, LP64)
# Fixed-width ctypes only: c_long is 4 bytes on Windows, so 'long'/'unsigned long'/pointers are spelled c_int64 /
# c_uint64 explicitly (target is LP64 Linux where they are 8 bytes, 8-aligned).
u8, u32, s32, s64, u64 = ctypes.c_uint8, ctypes.c_uint32, ctypes.c_int32, ctypes.c_int64, ctypes.c_uint64


class v4l2_capability(ctypes.Structure):
    _fields_ = [("driver", ctypes.c_char * 16), ("card", ctypes.c_char * 32), ("bus_info", ctypes.c_char * 32),
                ("version", u32), ("capabilities", u32), ("device_caps", u32), ("reserved", u32 * 3)]


class v4l2_fmtdesc(ctypes.Structure):
    _fields_ = [("index", u32), ("type", u32), ("flags", u32), ("description", ctypes.c_char * 32),
                ("pixelformat", u32), ("mbus_code", u32), ("reserved", u32 * 3)]


class v4l2_frmsize_discrete(ctypes.Structure):
    _fields_ = [("width", u32), ("height", u32)]


class v4l2_frmsize_stepwise(ctypes.Structure):
    _fields_ = [("min_width", u32), ("max_width", u32), ("step_width", u32),
                ("min_height", u32), ("max_height", u32), ("step_height", u32)]


class _frmsize_u(ctypes.Union):
    _fields_ = [("discrete", v4l2_frmsize_discrete), ("stepwise", v4l2_frmsize_stepwise)]


class v4l2_frmsizeenum(ctypes.Structure):
    _fields_ = [("index", u32), ("pixel_format", u32), ("type", u32), ("u", _frmsize_u), ("reserved", u32 * 2)]


class v4l2_fract(ctypes.Structure):
    _fields_ = [("numerator", u32), ("denominator", u32)]


class v4l2_frmival_stepwise(ctypes.Structure):
    _fields_ = [("min", v4l2_fract), ("max", v4l2_fract), ("step", v4l2_fract)]


class _frmival_u(ctypes.Union):
    _fields_ = [("discrete", v4l2_fract), ("stepwise", v4l2_frmival_stepwise)]


class v4l2_frmivalenum(ctypes.Structure):
    _fields_ = [("index", u32), ("pixel_format", u32), ("width", u32), ("height", u32), ("type", u32),
                ("u", _frmival_u), ("reserved", u32 * 2)]


class v4l2_pix_format(ctypes.Structure):
    _fields_ = [("width", u32), ("height", u32), ("pixelformat", u32), ("field", u32), ("bytesperline", u32),
                ("sizeimage", u32), ("colorspace", u32), ("priv", u32), ("flags", u32),
                ("ycbcr_enc", u32),  # union { ycbcr_enc; hsv_enc; }
                ("quantization", u32), ("xfer_func", u32)]


class _fmt_union(ctypes.Union):
    # Kernel union also holds struct v4l2_window, which contains pointers -> the union is 8-byte aligned on LP64,
    # so 'fmt' starts at offset 8 (not 4) and sizeof(v4l2_format) == 208. '_align' reproduces that.
    _fields_ = [("pix", v4l2_pix_format), ("raw_data", u8 * 200), ("_align", u64)]


class v4l2_format(ctypes.Structure):
    _fields_ = [("type", u32), ("fmt", _fmt_union)]


class v4l2_captureparm(ctypes.Structure):
    _fields_ = [("capability", u32), ("capturemode", u32), ("timeperframe", v4l2_fract),
                ("extendedmode", u32), ("readbuffers", u32), ("reserved", u32 * 4)]


class _parm_union(ctypes.Union):  # capture / output / raw_data[200]; all 4-byte aligned -> sizeof 204
    _fields_ = [("capture", v4l2_captureparm), ("raw_data", u8 * 200)]


class v4l2_streamparm(ctypes.Structure):
    _fields_ = [("type", u32), ("parm", _parm_union)]


class v4l2_requestbuffers(ctypes.Structure):
    _fields_ = [("count", u32), ("type", u32), ("memory", u32), ("capabilities", u32),
                ("flags", u8), ("reserved", u8 * 3)]


class timeval(ctypes.Structure):  # struct timeval on LP64: long tv_sec; long tv_usec
    _fields_ = [("tv_sec", s64), ("tv_usec", s64)]


class v4l2_timecode(ctypes.Structure):
    _fields_ = [("type", u32), ("flags", u32), ("frames", u8), ("seconds", u8), ("minutes", u8), ("hours", u8),
                ("userbits", u8 * 4)]


class _buf_m(ctypes.Union):  # union { __u32 offset; unsigned long userptr; struct v4l2_plane *planes; __s32 fd; }
    _fields_ = [("offset", u32), ("userptr", u64), ("planes", u64), ("fd", s32)]


class _buf_req(ctypes.Union):  # union { __s32 request_fd; __u32 reserved; }
    _fields_ = [("request_fd", s32), ("reserved", u32)]


class v4l2_buffer(ctypes.Structure):
    # offsets on LP64: index 0, type 4, bytesused 8, flags 12, field 16, (pad) timestamp 24, timecode 40,
    # sequence 56, memory 60, m 64, length 72, reserved2 76, request_fd 80, (tail pad) -> sizeof 88
    _fields_ = [("index", u32), ("type", u32), ("bytesused", u32), ("flags", u32), ("field", u32),
                ("timestamp", timeval), ("timecode", v4l2_timecode), ("sequence", u32), ("memory", u32),
                ("m", _buf_m), ("length", u32), ("reserved2", u32), ("r", _buf_req)]


class v4l2_control(ctypes.Structure):
    _fields_ = [("id", u32), ("value", s32)]


class v4l2_queryctrl(ctypes.Structure):
    _fields_ = [("id", u32), ("type", u32), ("name", ctypes.c_char * 32), ("minimum", s32), ("maximum", s32),
                ("step", s32), ("default_value", s32), ("flags", u32), ("reserved", u32 * 2)]


VIDIOC_QUERYCAP = _IOR("V", 0, v4l2_capability)
VIDIOC_ENUM_FMT = _IOWR("V", 2, v4l2_fmtdesc)
VIDIOC_G_FMT = _IOWR("V", 4, v4l2_format)
VIDIOC_S_FMT = _IOWR("V", 5, v4l2_format)
VIDIOC_REQBUFS = _IOWR("V", 8, v4l2_requestbuffers)
VIDIOC_QUERYBUF = _IOWR("V", 9, v4l2_buffer)
VIDIOC_QBUF = _IOWR("V", 15, v4l2_buffer)
VIDIOC_DQBUF = _IOWR("V", 17, v4l2_buffer)
VIDIOC_STREAMON = _IOW("V", 18, ctypes.c_int)
VIDIOC_STREAMOFF = _IOW("V", 19, ctypes.c_int)
VIDIOC_G_PARM = _IOWR("V", 21, v4l2_streamparm)
VIDIOC_S_PARM = _IOWR("V", 22, v4l2_streamparm)
VIDIOC_G_CTRL = _IOWR("V", 27, v4l2_control)
VIDIOC_S_CTRL = _IOWR("V", 28, v4l2_control)
VIDIOC_QUERYCTRL = _IOWR("V", 36, v4l2_queryctrl)
VIDIOC_ENUM_FRAMESIZES = _IOWR("V", 74, v4l2_frmsizeenum)
VIDIOC_ENUM_FRAMEINTERVALS = _IOWR("V", 75, v4l2_frmivalenum)

# Reference values for x86_64 (from the brief / well-known header expansions). The first 8 were given as known;
# the rest are hand-expanded from the macros and should match any 64-bit Linux.
KNOWN_IOCTLS = {
    "VIDIOC_QUERYCAP": 0x80685600, "VIDIOC_S_FMT": 0xC0D05605, "VIDIOC_REQBUFS": 0xC0145608,
    "VIDIOC_QUERYBUF": 0xC0585609, "VIDIOC_QBUF": 0xC058560F, "VIDIOC_DQBUF": 0xC0585611,
    "VIDIOC_STREAMON": 0x40045612, "VIDIOC_S_PARM": 0xC0CC5616,
}
DERIVED_IOCTLS = {
    "VIDIOC_ENUM_FMT": 0xC0405602, "VIDIOC_G_FMT": 0xC0D05604, "VIDIOC_STREAMOFF": 0x40045613,
    "VIDIOC_G_PARM": 0xC0CC5615, "VIDIOC_G_CTRL": 0xC008561B, "VIDIOC_S_CTRL": 0xC008561C,
    "VIDIOC_QUERYCTRL": 0xC0445624, "VIDIOC_ENUM_FRAMESIZES": 0xC02C564A, "VIDIOC_ENUM_FRAMEINTERVALS": 0xC034564B,
}
KNOWN_SIZES = {
    "v4l2_capability": 104, "v4l2_fmtdesc": 64, "v4l2_frmsizeenum": 44, "v4l2_frmivalenum": 52,
    "v4l2_pix_format": 48, "v4l2_format": 208, "v4l2_captureparm": 40, "v4l2_streamparm": 204,
    "v4l2_requestbuffers": 20, "timeval": 16, "v4l2_timecode": 16, "v4l2_buffer": 88, "v4l2_control": 8,
    "v4l2_queryctrl": 68,
}
KNOWN_OFFSETS = {
    ("v4l2_buffer", "timestamp"): 24, ("v4l2_buffer", "timecode"): 40, ("v4l2_buffer", "sequence"): 56,
    ("v4l2_buffer", "memory"): 60, ("v4l2_buffer", "m"): 64, ("v4l2_buffer", "length"): 72,
    ("v4l2_buffer", "r"): 80, ("v4l2_format", "fmt"): 8, ("v4l2_streamparm", "parm"): 4,
    ("v4l2_captureparm", "timeperframe"): 8, ("v4l2_frmivalenum", "u"): 20, ("v4l2_frmsizeenum", "u"): 12,
}

V4L2_BUF_TYPE_VIDEO_CAPTURE = 1
V4L2_MEMORY_MMAP = 1
V4L2_FIELD_ANY = 0
V4L2_CAP_VIDEO_CAPTURE = 0x00000001
V4L2_CAP_STREAMING = 0x04000000
V4L2_CAP_DEVICE_CAPS = 0x80000000
V4L2_CAP_TIMEPERFRAME = 0x1000
V4L2_FMT_FLAG_COMPRESSED = 0x0001
V4L2_FRMSIZE_TYPE_DISCRETE, V4L2_FRMSIZE_TYPE_CONTINUOUS, V4L2_FRMSIZE_TYPE_STEPWISE = 1, 2, 3
V4L2_FRMIVAL_TYPE_DISCRETE = 1
V4L2_CTRL_FLAG_DISABLED = 0x0001

BUF_FLAGS = {  # name -> bit (videodev2.h)
    "MAPPED": 0x1, "QUEUED": 0x2, "DONE": 0x4, "KEYFRAME": 0x8, "PFRAME": 0x10, "BFRAME": 0x20, "ERROR": 0x40,
    "IN_REQUEST": 0x80, "TIMECODE": 0x100, "M2M_HOLD_CAPTURE_BUF": 0x200, "PREPARED": 0x400,
    "NO_CACHE_INVALIDATE": 0x800, "NO_CACHE_CLEAN": 0x1000, "LAST": 0x100000, "REQUEST_FD": 0x800000,
}
V4L2_BUF_FLAG_ERROR = 0x40
V4L2_BUF_FLAG_TIMESTAMP_MASK = 0x0000E000
TS_TYPES = {0x0000: "TIMESTAMP_UNKNOWN", 0x2000: "TIMESTAMP_MONOTONIC", 0x4000: "TIMESTAMP_COPY"}
V4L2_BUF_FLAG_TSTAMP_SRC_MASK = 0x00070000
TS_SRCS = {0x00000: "TSTAMP_SRC_EOF", 0x10000: "TSTAMP_SRC_SOE"}

V4L2_CID_BASE = 0x00980900
V4L2_CID_AUTO_WHITE_BALANCE = V4L2_CID_BASE + 12
V4L2_CID_WHITE_BALANCE_TEMPERATURE = V4L2_CID_BASE + 26
V4L2_CID_CAMERA_CLASS_BASE = 0x009A0900
V4L2_CID_EXPOSURE_AUTO = V4L2_CID_CAMERA_CLASS_BASE + 1          # menu: 0 AUTO, 1 MANUAL, 2 SHUTTER_PRIO, 3 APERTURE_PRIO
V4L2_CID_EXPOSURE_ABSOLUTE = V4L2_CID_CAMERA_CLASS_BASE + 2      # units of 100 us
V4L2_CID_EXPOSURE_AUTO_PRIORITY = V4L2_CID_CAMERA_CLASS_BASE + 3  # 1 = camera may lower fps to lengthen exposure
V4L2_EXPOSURE_MANUAL = 1
CTRLS = {"exposure_auto": V4L2_CID_EXPOSURE_AUTO, "exposure_absolute": V4L2_CID_EXPOSURE_ABSOLUTE,
         "exposure_auto_priority": V4L2_CID_EXPOSURE_AUTO_PRIORITY, "white_balance_auto": V4L2_CID_AUTO_WHITE_BALANCE,
         "white_balance_temperature": V4L2_CID_WHITE_BALANCE_TEMPERATURE}


def fourcc(s: str) -> int:
    return ord(s[0]) | (ord(s[1]) << 8) | (ord(s[2]) << 16) | (ord(s[3]) << 24)


def fourcc_str(v: int) -> str:
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4))


V4L2_PIX_FMT_MJPEG = fourcc("MJPG")
V4L2_PIX_FMT_JPEG = fourcc("JPEG")


def decode_flags(f: int) -> dict:
    return {"names": [n for n, b in BUF_FLAGS.items() if f & b],
            "ts_type": TS_TYPES.get(f & V4L2_BUF_FLAG_TIMESTAMP_MASK, f"0x{f & V4L2_BUF_FLAG_TIMESTAMP_MASK:x}"),
            "ts_src": TS_SRCS.get(f & V4L2_BUF_FLAG_TSTAMP_SRC_MASK, f"0x{f & V4L2_BUF_FLAG_TSTAMP_SRC_MASK:x}"),
            "error": bool(f & V4L2_BUF_FLAG_ERROR)}


# ---------------------------------------------------------------- selftest (runs anywhere ctypes does)
def selftest() -> int:
    ok = True
    print(f"python {sys.version.split()[0]} on {sys.platform}; sizeof(void*)={ctypes.sizeof(ctypes.c_void_p)} "
          f"sizeof(c_long)={ctypes.sizeof(ctypes.c_long)} (irrelevant: layouts use fixed-width types)")
    print("struct sizes (target: 64-bit Linux):")
    for name, want in KNOWN_SIZES.items():
        got = ctypes.sizeof(globals()[name])
        ok &= got == want
        print(f"  {name:22s} {got:4d}  expected {want:4d}  {'OK' if got == want else 'MISMATCH'}")
    print("field offsets:")
    for (sname, field), want in KNOWN_OFFSETS.items():
        got = getattr(globals()[sname], field).offset
        ok &= got == want
        print(f"  {sname + '.' + field:28s} {got:4d}  expected {want:4d}  {'OK' if got == want else 'MISMATCH'}")
    print("ioctl numbers (given x86_64 values):")
    for name, want in KNOWN_IOCTLS.items():
        got = globals()[name]
        ok &= got == want
        print(f"  {name:28s} 0x{got:08x}  expected 0x{want:08x}  {'OK' if got == want else 'MISMATCH'}")
    print("ioctl numbers (hand-expanded reference values):")
    for name, want in DERIVED_IOCTLS.items():
        got = globals()[name]
        ok &= got == want
        print(f"  {name:28s} 0x{got:08x}  expected 0x{want:08x}  {'OK' if got == want else 'MISMATCH'}")
    ok &= fourcc_str(V4L2_PIX_FMT_MJPEG) == "MJPG" and V4L2_PIX_FMT_MJPEG == 0x47504A4D
    print(f"V4L2_PIX_FMT_MJPEG = 0x{V4L2_PIX_FMT_MJPEG:08x} ('{fourcc_str(V4L2_PIX_FMT_MJPEG)}')  expected 0x47504a4d")
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------------------------------------------------------------- helpers
def require_linux64():
    if fcntl is None or not sys.platform.startswith("linux"):
        raise SystemExit("error: capture/list need Linux (fcntl + V4L2). Only --selftest runs elsewhere.")
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        raise SystemExit("error: 32-bit userspace is not supported (struct layouts are LP64-only)")


def xioctl(fd: int, req: int, arg):
    while True:
        try:
            return fcntl.ioctl(fd, req, arg, True)
        except InterruptedError:
            continue


def mono_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def cstr(b: bytes) -> str:
    return b.decode("utf-8", "replace")


def read_text(p: Path) -> str | None:
    try:
        return p.read_text().strip()
    except OSError:
        return None


def uvcvideo_params() -> dict:
    d = Path("/sys/module/uvcvideo/parameters")
    if not d.is_dir():
        return {"error": f"{d} missing (uvcvideo not loaded?)"}
    return {p.name: read_text(p) for p in sorted(d.iterdir())}


def sysfs_info(dev_path: str) -> dict:
    """USB topology for /dev/videoN: /sys/class/video4linux/videoN/device -> USB interface dir; its parent is the
    USB device (idVendor, idProduct, serial, speed, busnum/devpath = physical port)."""
    name = Path(dev_path).name
    base = Path("/sys/class/video4linux") / name
    out: dict = {"v4l_name": read_text(base / "name"), "v4l_index": read_text(base / "index")}
    try:
        intf = (base / "device").resolve(strict=True)
    except OSError as e:
        out["error"] = repr(e)
        return out
    out["device_symlink_resolved"] = str(intf)
    out["bInterfaceNumber"] = read_text(intf / "bInterfaceNumber")
    out["interface_driver"] = os.path.basename(os.path.realpath(intf / "driver")) if (intf / "driver").exists() else None
    usbdev = intf.parent
    out["usb_device_path"] = str(usbdev)
    out["usb_port"] = usbdev.name  # e.g. "1-2.3" = bus 1, root port 2, hub port 3
    for k in ("idVendor", "idProduct", "bcdDevice", "serial", "manufacturer", "product", "speed", "busnum", "devnum",
              "devpath", "version", "bMaxPower", "removable"):
        out[k] = read_text(usbdev / k)
    return out


def camera_key(si: dict, card: str) -> str:
    if si.get("idVendor"):
        return f"usb-{si['idVendor']}:{si['idProduct']}-{si.get('serial') or 'noserial'}@{si.get('usb_port')}"
    return card


def query_ctrl(fd: int, cid: int) -> dict | None:
    q = v4l2_queryctrl(id=cid)
    try:
        xioctl(fd, VIDIOC_QUERYCTRL, q)
    except OSError as e:
        return {"error": errno.errorcode.get(e.errno, str(e.errno))}
    return {"name": cstr(q.name), "type": q.type, "min": q.minimum, "max": q.maximum, "step": q.step,
            "default": q.default_value, "flags": q.flags}


def get_ctrl(fd: int, cid: int):
    c = v4l2_control(id=cid)
    try:
        xioctl(fd, VIDIOC_G_CTRL, c)
        return c.value
    except OSError as e:
        return f"error {errno.errorcode.get(e.errno, e.errno)}"


def set_ctrl(fd: int, cid: int, val: int):
    c = v4l2_control(id=cid, value=val)
    try:
        xioctl(fd, VIDIOC_S_CTRL, c)
        return {"requested": val, "result": "ok", "driver_returned": c.value}
    except OSError as e:
        return {"requested": val, "result": f"error {errno.errorcode.get(e.errno, e.errno)}"}


def read_ctrls(fd: int) -> dict:
    return {k: get_ctrl(fd, cid) for k, cid in CTRLS.items()}


def enum_device(path: str) -> dict:
    fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    try:
        cap = v4l2_capability()
        xioctl(fd, VIDIOC_QUERYCAP, cap)
        caps = cap.device_caps if cap.capabilities & V4L2_CAP_DEVICE_CAPS else cap.capabilities
        out = {"path": path, "driver": cstr(cap.driver), "card": cstr(cap.card), "bus_info": cstr(cap.bus_info),
               "kernel_version": f"{cap.version >> 16}.{(cap.version >> 8) & 0xFF}.{cap.version & 0xFF}",
               "device_caps": f"0x{caps:08x}", "video_capture": bool(caps & V4L2_CAP_VIDEO_CAPTURE),
               "streaming": bool(caps & V4L2_CAP_STREAMING), "sysfs": sysfs_info(path), "formats": []}
        if not out["video_capture"]:
            return out  # e.g. the uvcvideo metadata node
        i = 0
        while True:
            fdesc = v4l2_fmtdesc(index=i, type=V4L2_BUF_TYPE_VIDEO_CAPTURE)
            try:
                xioctl(fd, VIDIOC_ENUM_FMT, fdesc)
            except OSError:
                break
            f = {"fourcc": fourcc_str(fdesc.pixelformat), "description": cstr(fdesc.description),
                 "compressed": bool(fdesc.flags & V4L2_FMT_FLAG_COMPRESSED), "sizes": []}
            j = 0
            while True:
                fs = v4l2_frmsizeenum(index=j, pixel_format=fdesc.pixelformat)
                try:
                    xioctl(fd, VIDIOC_ENUM_FRAMESIZES, fs)
                except OSError:
                    break
                if fs.type == V4L2_FRMSIZE_TYPE_DISCRETE:
                    w, h = fs.u.discrete.width, fs.u.discrete.height
                    f["sizes"].append({"w": w, "h": h, "intervals": enum_intervals(fd, fdesc.pixelformat, w, h)})
                else:
                    sw = fs.u.stepwise
                    f["sizes"].append({"type": "continuous" if fs.type == V4L2_FRMSIZE_TYPE_CONTINUOUS else "stepwise",
                                       "min": [sw.min_width, sw.min_height], "max": [sw.max_width, sw.max_height],
                                       "step": [sw.step_width, sw.step_height],
                                       "intervals_at_max": enum_intervals(fd, fdesc.pixelformat, sw.max_width, sw.max_height)})
                    break  # only index 0 is valid for non-discrete
                j += 1
            out["formats"].append(f)
            i += 1
        out["mjpeg_modes"] = mjpeg_modes(out)
        return out
    finally:
        os.close(fd)


def enum_intervals(fd: int, pixfmt: int, w: int, h: int) -> list:
    res = []
    k = 0
    while True:
        fi = v4l2_frmivalenum(index=k, pixel_format=pixfmt, width=w, height=h)
        try:
            xioctl(fd, VIDIOC_ENUM_FRAMEINTERVALS, fi)
        except OSError:
            break
        if fi.type == V4L2_FRMIVAL_TYPE_DISCRETE:
            d = fi.u.discrete
            res.append({"num": d.numerator, "den": d.denominator, "fps": round(d.denominator / d.numerator, 3) if d.numerator else None})
        else:
            s = fi.u.stepwise
            res.append({"type": "stepwise/continuous", "min": [s.min.numerator, s.min.denominator],
                        "max": [s.max.numerator, s.max.denominator], "step": [s.step.numerator, s.step.denominator]})
            break
        k += 1
    return res


def mjpeg_modes(dev: dict) -> list:
    modes = []
    for f in dev.get("formats", []):
        if f["fourcc"] != "MJPG":
            continue
        for s in f["sizes"]:
            for iv in s.get("intervals", []):
                if iv.get("fps"):
                    modes.append((s["w"], s["h"], iv["fps"]))
    return sorted(set(modes), key=lambda m: (m[0] * m[1], m[2]))


def list_all() -> list[dict]:
    nodes = sorted(Path("/dev").glob("video*"), key=lambda p: int(p.name[5:]) if p.name[5:].isdigit() else 1 << 30)
    out = []
    for n in nodes:
        try:
            out.append(enum_device(str(n)))
        except OSError as e:
            out.append({"path": str(n), "error": f"{errno.errorcode.get(e.errno, e.errno)}: {e.strerror}"})
    return out


def cpu_clock_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_PROCESS_CPUTIME_ID)


# ---------------------------------------------------------------- capture
class Capture:
    def __init__(self, idx: int, path: str, w: int, h: int, fps: float, nbuf: int, writer: mc.RunWriter,
                 lock: threading.Lock, exposure_abs: int | None, manual_wb: int | None, capture_anyway: bool):
        self.idx, self.path, self.writer, self.lock = idx, path, writer, lock
        self.stop = threading.Event()
        self.maps: list = []
        self.streaming = False
        self.errors: list[str] = []
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self.flag_counts: dict[str, int] = {}
        try:
            self._configure(w, h, fps, nbuf, exposure_abs, manual_wb, capture_anyway)
        except BaseException:  # don't leak the fd / mmaps of a camera that failed to configure
            for m in self.maps:
                m.close()
            os.close(self.fd)
            raise

    def _configure(self, w, h, fps, nbuf, exposure_abs, manual_wb, capture_anyway):
        cap = v4l2_capability()
        xioctl(self.fd, VIDIOC_QUERYCAP, cap)
        si = sysfs_info(self.path)
        self.card = cstr(cap.card)
        self.key = camera_key(si, self.card)
        self.info: dict = {"idx": self.idx, "name": f"{self.card} ({self.path})", "camera_key": self.key, "device": self.path,
                           "driver": cstr(cap.driver), "card": self.card, "bus_info": cstr(cap.bus_info), "sysfs": si}
        # --- format: request MJPG, then believe only what S_FMT wrote back
        f = v4l2_format(type=V4L2_BUF_TYPE_VIDEO_CAPTURE)
        f.fmt.pix.width, f.fmt.pix.height = w, h
        f.fmt.pix.pixelformat, f.fmt.pix.field = V4L2_PIX_FMT_MJPEG, V4L2_FIELD_ANY
        xioctl(self.fd, VIDIOC_S_FMT, f)
        g = v4l2_format(type=V4L2_BUF_TYPE_VIDEO_CAPTURE)
        xioctl(self.fd, VIDIOC_G_FMT, g)
        p = f.fmt.pix
        self.got_fourcc = fourcc_str(p.pixelformat)
        self.info["format"] = {"requested": {"fourcc": "MJPG", "width": w, "height": h},
                               "s_fmt_returned": {"fourcc": self.got_fourcc, "width": p.width, "height": p.height,
                                                  "field": p.field, "bytesperline": p.bytesperline,
                                                  "sizeimage": p.sizeimage, "colorspace": p.colorspace},
                               "g_fmt": {"fourcc": fourcc_str(g.fmt.pix.pixelformat), "width": g.fmt.pix.width,
                                         "height": g.fmt.pix.height}}
        self.info["silent_format_fallback"] = p.pixelformat != V4L2_PIX_FMT_MJPEG
        self.info["size_fallback"] = (p.width, p.height) != (w, h)
        self.payload_is_jpeg = p.pixelformat in (V4L2_PIX_FMT_MJPEG, V4L2_PIX_FMT_JPEG)
        self.info["payload_is_jpeg"] = self.payload_is_jpeg
        self.refused = self.info["silent_format_fallback"] and not (self.payload_is_jpeg or capture_anyway)
        self.info["refused"] = self.refused
        if self.refused:
            self.errors.append(f"{self.path}: driver substituted pixelformat {self.got_fourcc} for MJPG; not streaming (use --capture-anyway to record it)")
        # --- frame rate
        sp = v4l2_streamparm(type=V4L2_BUF_TYPE_VIDEO_CAPTURE)
        tpf = Fraction(1) / Fraction(fps).limit_denominator(1001000)
        sp.parm.capture.timeperframe.numerator, sp.parm.capture.timeperframe.denominator = tpf.numerator, tpf.denominator
        try:
            xioctl(self.fd, VIDIOC_S_PARM, sp)
            s_parm_err = None
        except OSError as e:
            s_parm_err = errno.errorcode.get(e.errno, str(e.errno))
        gp = v4l2_streamparm(type=V4L2_BUF_TYPE_VIDEO_CAPTURE)
        try:
            xioctl(self.fd, VIDIOC_G_PARM, gp)
        except OSError:
            pass
        t1, t2 = sp.parm.capture.timeperframe, gp.parm.capture.timeperframe
        self.info["frame_rate"] = {"requested_fps": fps, "requested_timeperframe": [tpf.numerator, tpf.denominator],
                                   "s_parm_error": s_parm_err, "s_parm_returned": [t1.numerator, t1.denominator],
                                   "g_parm": [t2.numerator, t2.denominator],
                                   "driver_fps": (t2.denominator / t2.numerator) if t2.numerator else None,
                                   "cap_timeperframe": bool(gp.parm.capture.capability & V4L2_CAP_TIMEPERFRAME)}
        # --- optional manual exposure / white balance
        ctl: dict = {"query": {k: query_ctrl(self.fd, cid) for k, cid in CTRLS.items()}, "before": read_ctrls(self.fd)}
        applied: dict = {}
        if exposure_abs is not None:
            # order matters on UVC: EXPOSURE_ABSOLUTE is read-only (EACCES/EBUSY) until EXPOSURE_AUTO=MANUAL
            applied["exposure_auto"] = set_ctrl(self.fd, V4L2_CID_EXPOSURE_AUTO, V4L2_EXPOSURE_MANUAL)
            applied["exposure_absolute"] = set_ctrl(self.fd, V4L2_CID_EXPOSURE_ABSOLUTE, exposure_abs)
            applied["exposure_auto_priority"] = set_ctrl(self.fd, V4L2_CID_EXPOSURE_AUTO_PRIORITY, 0)
        if manual_wb is not None:
            applied["white_balance_auto"] = set_ctrl(self.fd, V4L2_CID_AUTO_WHITE_BALANCE, 0)
            applied["white_balance_temperature"] = set_ctrl(self.fd, V4L2_CID_WHITE_BALANCE_TEMPERATURE, manual_wb)
        ctl["requested"] = {"exposure_absolute_100us": exposure_abs, "white_balance_temperature_k": manual_wb}
        ctl["applied"] = applied
        ctl["after_apply"] = read_ctrls(self.fd)
        self.info["controls"] = ctl
        if self.refused:
            return
        # --- buffers
        rb = v4l2_requestbuffers(count=nbuf, type=V4L2_BUF_TYPE_VIDEO_CAPTURE, memory=V4L2_MEMORY_MMAP)
        xioctl(self.fd, VIDIOC_REQBUFS, rb)
        self.info["buffers"] = {"requested": nbuf, "granted": rb.count, "reqbufs_capabilities": f"0x{rb.capabilities:x}", "lengths": []}
        for i in range(rb.count):
            b = v4l2_buffer(index=i, type=V4L2_BUF_TYPE_VIDEO_CAPTURE, memory=V4L2_MEMORY_MMAP)
            xioctl(self.fd, VIDIOC_QUERYBUF, b)
            self.maps.append(mmap.mmap(self.fd, b.length, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=b.m.offset))
            self.info["buffers"]["lengths"].append(b.length)
            xioctl(self.fd, VIDIOC_QBUF, b)

    def run(self):
        if self.refused:
            return
        seq = 0
        try:
            xioctl(self.fd, VIDIOC_STREAMON, ctypes.c_int(V4L2_BUF_TYPE_VIDEO_CAPTURE))
            self.streaming = True
            self.info["streamon_host_ns"] = mono_ns()
            timeouts = 0
            while not self.stop.is_set():
                r, _, _ = select.select([self.fd], [], [], 1.0)
                if not r:
                    timeouts += 1
                    continue
                b = v4l2_buffer(type=V4L2_BUF_TYPE_VIDEO_CAPTURE, memory=V4L2_MEMORY_MMAP)
                try:
                    xioctl(self.fd, VIDIOC_DQBUF, b)
                except OSError as e:
                    if e.errno == errno.EAGAIN:
                        continue
                    raise
                arrival = mono_ns()
                n = b.bytesused
                data = self.maps[b.index][:n]  # slicing an mmap copies -> bytes; buffer can be requeued at once
                xioctl(self.fd, VIDIOC_QBUF, b)
                fl = decode_flags(b.flags)
                k = f"{fl['ts_type']}|{fl['ts_src']}|error={fl['error']}"
                self.flag_counts[k] = self.flag_counts.get(k, 0) + 1
                ts_ns = b.timestamp.tv_sec * 1_000_000_000 + b.timestamp.tv_usec * 1000
                mono = fl["ts_type"] == "TIMESTAMP_MONOTONIC"
                row = {"camera_key": self.key, "backend": BACKEND, "seq": seq, "host_arrival_ns": arrival,
                       "os_timestamp_ns": ts_ns,
                       "os_timestamp_source": f"v4l2_buffer.timestamp {fl['ts_type']} {fl['ts_src']}"
                                              + ("" if mono else " (NOT CLOCK_MONOTONIC: not comparable to host_arrival_ns)"),
                       "uvc_pts": None, "uvc_scr_stc": None, "uvc_scr_sof": None, "device_clock_hz": None,
                       "payload_bytes": n, "is_valid_jpeg": None,
                       "v4l2_sequence": b.sequence, "v4l2_index": b.index, "v4l2_flags": b.flags,
                       "v4l2_flags_decoded": fl["names"], "v4l2_ts_type": fl["ts_type"], "v4l2_ts_src": fl["ts_src"],
                       "v4l2_error": fl["error"], "v4l2_field": b.field, "bytesused": n}
                with self.lock:
                    self.writer.add(self.idx, row, data)
                seq += 1
            self.info["select_timeouts_1s"] = timeouts
        except Exception as e:  # recorded, not raised: other cameras keep going
            self.errors.append(f"{self.path}: capture error after {seq} frames: {e!r}")
        finally:
            self.info["frames"] = seq
            self.info["v4l2_flag_counts"] = getattr(self, "flag_counts", {})

    def close(self):
        try:
            self.info["controls"]["readback_after_capture"] = read_ctrls(self.fd)
        except Exception as e:
            self.info["controls"]["readback_after_capture"] = repr(e)
        if self.streaming:
            try:
                xioctl(self.fd, VIDIOC_STREAMOFF, ctypes.c_int(V4L2_BUF_TYPE_VIDEO_CAPTURE))
            except OSError as e:
                self.errors.append(f"{self.path}: STREAMOFF {e!r}")
        for m in self.maps:
            m.close()
        if self.maps:
            try:
                xioctl(self.fd, VIDIOC_REQBUFS, v4l2_requestbuffers(count=0, type=V4L2_BUF_TYPE_VIDEO_CAPTURE, memory=V4L2_MEMORY_MMAP))
            except OSError:
                pass
        os.close(self.fd)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="print/verify struct sizes and ioctl numbers; no device access")
    ap.add_argument("--list", action="store_true", help="enumerate /dev/video* formats/sizes/intervals as JSON on stdout")
    ap.add_argument("--list-tsv", action="store_true", help="one line per MJPEG capture node: path, card, has_1280x720@30, max mode WxH, max fps, camera_key")
    ap.add_argument("--device", action="append", default=[], help="/dev/videoN (repeatable: one thread per camera)")
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--warmup", type=float, default=2)
    ap.add_argument("--buffers", type=int, default=6)
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--keep-samples", type=int, default=0)
    ap.add_argument("--root", default=None, help="results root (default results/<platform>/<host>); the runners pass a fresh mjpeg_run_<UTC stamp> dir")
    ap.add_argument("--exposure-abs", type=int, default=None, help="manual exposure, V4L2_CID_EXPOSURE_ABSOLUTE units (100 us), e.g. 78 = 7.8 ms")
    ap.add_argument("--manual-wb", type=int, default=None, help="manual white balance temperature in K, e.g. 4500")
    ap.add_argument("--capture-anyway", action="store_true", help="stream even if the driver substituted a non-JPEG format")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    require_linux64()
    if selftest_quiet() != 0:
        raise SystemExit("error: struct layout self-check failed; run --selftest")

    if a.list or a.list_tsv:
        devs = list_all()
        if a.list_tsv:
            for d in devs:
                modes = [tuple(m) for m in d.get("mjpeg_modes", [])]
                if not modes:
                    continue
                mx = modes[-1]
                has720 = any(m[0] == 1280 and m[1] == 720 and abs(m[2] - 30) < 0.5 for m in modes)
                key = camera_key(d.get("sysfs", {}), d.get("card", ""))
                print("\t".join([d["path"], d.get("card", "").replace("\t", " "), "1" if has720 else "0",
                                 f"{mx[0]}x{mx[1]}", f"{mx[2]:g}", key]))
            return 0
        doc = {"test": "mjpeg_v4l2_list", "platform": mc.plat(), "hostname": mc.HOST, "utc_started": mc.utc_now(),
               "command": sys.argv, "environment": {**mc.environment(), "kernel": os.uname().release},
               "uvcvideo_parameters": uvcvideo_params(), "devices": devs}
        out = mc.results_dir("mjpeg_v4l2_list", root=a.root)
        (out / "devices.json").write_text(json.dumps(doc, indent=1))
        print(json.dumps(doc, indent=1))
        print(f"wrote {out / 'devices.json'}", file=sys.stderr)
        return 0

    if not a.device:
        raise SystemExit("error: give --device /dev/videoN (see --list)")
    W, H = map(int, a.size.lower().split("x"))
    run_dir = Path(a.run_dir) if a.run_dir else Path(__import__("tempfile").mkdtemp(prefix="v4l2_mmap_", dir=mc.scratch_root()))
    writer = mc.RunWriter(run_dir)
    lock = threading.Lock()
    started = mc.utc_now()
    clock_pair = {"realtime_ns": time.clock_gettime_ns(time.CLOCK_REALTIME), "monotonic_ns": mono_ns()}
    clock_pair["realtime_minus_monotonic_ns"] = clock_pair["realtime_ns"] - clock_pair["monotonic_ns"]
    errors: list[str] = []
    caps: list[Capture] = []
    for i, d in enumerate(a.device):
        try:
            caps.append(Capture(i, d, W, H, a.fps, a.buffers, writer, lock, a.exposure_abs, a.manual_wb, a.capture_anyway))
        except OSError as e:
            errors.append(f"{d}: open/configure failed: {errno.errorcode.get(e.errno, e.errno)} {e.strerror}"
                          + (" (camera busy: another process has it open)" if e.errno == errno.EBUSY else "")
                          + (" (permission: add yourself to the 'video' group)" if e.errno == errno.EACCES else ""))
    threads = [threading.Thread(target=c.run, daemon=True, name=c.path) for c in caps]
    for t in threads:
        t.start()
    time.sleep(a.warmup)
    cpu = mc.CpuWindow()
    cpu.start()
    c0 = cpu_clock_ns()
    w0 = mono_ns()
    time.sleep(a.seconds)
    w1 = mono_ns()
    c1 = cpu_clock_ns()
    cpu_res = cpu.stop()
    wall = (w1 - w0) / 1e9
    cpu_res.update({"method": "CLOCK_PROCESS_CPUTIME_ID (precise, all threads) + psutil cpu_times (tick-sampled)",
                    "process_cpu_s_clock": (c1 - c0) / 1e9,
                    "process_cpu_pct_of_one_core": 100.0 * (c1 - c0) / 1e9 / wall if wall else None})
    for c in caps:
        c.stop.set()
    for t in threads:
        t.join(5)
    for c in caps:
        c.close()
        errors += c.errors
    fallback = any(c.info["silent_format_fallback"] for c in caps)
    streamed = [c for c in caps if not c.refused]
    payload_is_jpeg = all(c.payload_is_jpeg for c in streamed) if streamed else False
    meta = {"backend": BACKEND, "utc_started": started, "command": sys.argv,
            "environment": {**mc.environment(), "kernel": os.uname().release},
            "requested": {"subtype": "MJPG", "width": W, "height": H, "fps": a.fps},
            "decoded_by_pipeline": False,
            "decode_evidence": "VIDIOC_S_FMT returned pixelformat (per camera: format.s_fmt_returned); payload = mmap buffer[:bytesused] "
                               "copied as bytes; no decoder is linked or called during capture (validation decodes happen afterwards in summarize_run)",
            "delivered_codecs": [c.got_fourcc for c in caps],
            "silent_format_fallback": fallback,
            "payload_is_jpeg": payload_is_jpeg,
            "cpu": cpu_res, "cameras": [c.info for c in caps], "errors": errors,
            "controls": {c.path: c.info["controls"] for c in caps},
            "backend_details": {"struct_sizes": {n: ctypes.sizeof(globals()[n]) for n in KNOWN_SIZES},
                                "uvcvideo_parameters": uvcvideo_params(), "clock_pair_at_start": clock_pair,
                                "host_clock": "time.clock_gettime_ns(CLOCK_MONOTONIC)", "buffers": a.buffers,
                                "header_revision": "include/uapi/linux/videodev2.h (Linux v6.8), LP64"},
            "notes": "UNVERIFIED draft backend (drafted on Windows). uvcvideo stamps buffers with ktime_get_ns() at the first "
                     "USB packet of the frame (TSTAMP_SRC_SOE) unless hwtimestamps=1."}
    writer.flush(meta, w0, w1)
    if not a.label:
        a.label = f"{W}x{H}at{a.fps:g}_" + "+".join(Path(d).name for d in a.device)
    out = mc.results_dir(TEST, a.label, root=a.root)
    s = mc.summarize_run(run_dir, out, test=TEST, command=sys.argv, keep_samples=a.keep_samples, payload_is_jpeg=payload_is_jpeg)
    print(mc.brief(s))
    for e in errors:
        print("error:", e, file=sys.stderr)
    print("wrote", out / "summary.json")
    if fallback:  # includes refused cameras and MJPG->JPEG relabels
        return 2
    if not caps or not any(c.info.get("frames") for c in streamed):
        return 1
    return 0


def selftest_quiet() -> int:
    bad = [n for n, v in KNOWN_SIZES.items() if ctypes.sizeof(globals()[n]) != v]
    bad += [n for n, v in {**KNOWN_IOCTLS, **DERIVED_IOCTLS}.items() if globals()[n] != v]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
