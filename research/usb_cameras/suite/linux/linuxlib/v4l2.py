"""V4L2 ABI (ctypes + fcntl ioctls) for the Linux suite. Stdlib only; LP64 Linux (x86_64 / aarch64).

Merged from research/usb_cameras/mjpeg/drafts/linux/v4l2_mmap_mjpeg.py (capture structs, ioctl numbers and their
hand-expanded reference values) and timing/linux/v4l2_uvc_timing.py (metadata format, UVCH block parser), plus
the extended-control API (VIDIOC_QUERY_EXT_CTRL / QUERYMENU / G_EXT_CTRLS / S_EXT_CTRLS) that the drafts lacked.

Struct layouts follow include/uapi/linux/videodev2.h (Linux 6.8 .. 7.4-rc1 share them: every change since 6.1 kept
the sizes). ``selftest()`` compares sizes, offsets and ioctl numbers with reference values; it runs on any OS
(ctypes only), the ioctls themselves only on Linux.

Nothing in this module opens a device at import time. ``Device`` opens one node; every method raises
``V4L2Error`` (an OSError with .stage and .errno_name) so callers can record the failing step and errno.
"""
from __future__ import annotations

import ctypes
import errno as _errno
import mmap
import os
import struct
import time
from fractions import Fraction
from typing import Any

try:  # Linux only; selftest() works without it
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

# ----------------------------------------------------------------------------------------- ioctl encoding
# asm-generic encoding (x86_64 and arm64): nr 8 bits @0, type 8 bits @8, size 14 bits @16, dir 2 bits @30.
_IOC_NONE, _IOC_WRITE, _IOC_READ = 0, 1, 2


def _IOC(d: int, t: str, nr: int, size: int) -> int:
    assert 0 <= size < (1 << 14)
    return (d << 30) | (size << 16) | (ord(t) << 8) | nr


def _IOR(t, nr, st): return _IOC(_IOC_READ, t, nr, ctypes.sizeof(st))
def _IOW(t, nr, st): return _IOC(_IOC_WRITE, t, nr, ctypes.sizeof(st))
def _IOWR(t, nr, st): return _IOC(_IOC_READ | _IOC_WRITE, t, nr, ctypes.sizeof(st))


u8, u16, u32, s32, s64, u64 = (ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint32, ctypes.c_int32, ctypes.c_int64,
                               ctypes.c_uint64)


# ----------------------------------------------------------------------------------------- structs (LP64)
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
                ("sizeimage", u32), ("colorspace", u32), ("priv", u32), ("flags", u32), ("ycbcr_enc", u32),
                ("quantization", u32), ("xfer_func", u32)]


class v4l2_meta_format(ctypes.Structure):
    # dataformat + buffersize (6.x adds width/height/bytesperline for line-based formats; all inside the union)
    _fields_ = [("dataformat", u32), ("buffersize", u32)]


class _fmt_union(ctypes.Union):
    # The kernel union also holds struct v4l2_window (pointers) -> 8-byte aligned on LP64: 'fmt' at offset 8.
    _fields_ = [("pix", v4l2_pix_format), ("meta", v4l2_meta_format), ("raw_data", u8 * 200), ("_align", u64)]


class v4l2_format(ctypes.Structure):
    _fields_ = [("type", u32), ("fmt", _fmt_union)]


class v4l2_captureparm(ctypes.Structure):
    _fields_ = [("capability", u32), ("capturemode", u32), ("timeperframe", v4l2_fract),
                ("extendedmode", u32), ("readbuffers", u32), ("reserved", u32 * 4)]


class _parm_union(ctypes.Union):
    _fields_ = [("capture", v4l2_captureparm), ("raw_data", u8 * 200)]


class v4l2_streamparm(ctypes.Structure):
    _fields_ = [("type", u32), ("parm", _parm_union)]


class v4l2_requestbuffers(ctypes.Structure):
    _fields_ = [("count", u32), ("type", u32), ("memory", u32), ("capabilities", u32),
                ("flags", u8), ("reserved", u8 * 3)]


class timeval(ctypes.Structure):  # LP64: long tv_sec; long tv_usec
    _fields_ = [("tv_sec", s64), ("tv_usec", s64)]


class v4l2_timecode(ctypes.Structure):
    _fields_ = [("type", u32), ("flags", u32), ("frames", u8), ("seconds", u8), ("minutes", u8), ("hours", u8),
                ("userbits", u8 * 4)]


class _buf_m(ctypes.Union):
    _fields_ = [("offset", u32), ("userptr", u64), ("planes", u64), ("fd", s32)]


class _buf_req(ctypes.Union):
    _fields_ = [("request_fd", s32), ("reserved", u32)]


class v4l2_buffer(ctypes.Structure):
    _fields_ = [("index", u32), ("type", u32), ("bytesused", u32), ("flags", u32), ("field", u32),
                ("timestamp", timeval), ("timecode", v4l2_timecode), ("sequence", u32), ("memory", u32),
                ("m", _buf_m), ("length", u32), ("reserved2", u32), ("r", _buf_req)]


class v4l2_queryctrl(ctypes.Structure):
    _fields_ = [("id", u32), ("type", u32), ("name", ctypes.c_char * 32), ("minimum", s32), ("maximum", s32),
                ("step", s32), ("default_value", s32), ("flags", u32), ("reserved", u32 * 2)]


class v4l2_query_ext_ctrl(ctypes.Structure):
    _fields_ = [("id", u32), ("type", u32), ("name", ctypes.c_char * 32), ("minimum", s64), ("maximum", s64),
                ("step", u64), ("default_value", s64), ("flags", u32), ("elem_size", u32), ("elems", u32),
                ("nr_of_dims", u32), ("dims", u32 * 4), ("reserved", u32 * 32)]


class _qmenu_u(ctypes.Union):
    _pack_ = 1
    _fields_ = [("name", ctypes.c_char * 32), ("value", s64)]


class v4l2_querymenu(ctypes.Structure):  # __attribute__((packed))
    _pack_ = 1
    _fields_ = [("id", u32), ("index", u32), ("u", _qmenu_u), ("reserved", u32)]


class _ext_ctrl_u(ctypes.Union):
    _pack_ = 1
    _fields_ = [("value", s32), ("value64", s64), ("ptr", u64)]


class v4l2_ext_control(ctypes.Structure):  # __attribute__((packed))
    _pack_ = 1
    _fields_ = [("id", u32), ("size", u32), ("reserved2", u32), ("u", _ext_ctrl_u)]


class v4l2_ext_controls(ctypes.Structure):
    _fields_ = [("which", u32), ("count", u32), ("error_idx", u32), ("request_fd", s32), ("reserved", u32),
                ("controls", u64)]  # struct v4l2_ext_control * (8-byte aligned on LP64)


class v4l2_control(ctypes.Structure):
    _fields_ = [("id", u32), ("value", s32)]


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
VIDIOC_QUERYMENU = _IOWR("V", 37, v4l2_querymenu)
VIDIOC_TRY_FMT = _IOWR("V", 64, v4l2_format)
VIDIOC_G_EXT_CTRLS = _IOWR("V", 71, v4l2_ext_controls)
VIDIOC_S_EXT_CTRLS = _IOWR("V", 72, v4l2_ext_controls)
VIDIOC_ENUM_FRAMESIZES = _IOWR("V", 74, v4l2_frmsizeenum)
VIDIOC_ENUM_FRAMEINTERVALS = _IOWR("V", 75, v4l2_frmivalenum)
VIDIOC_QUERY_EXT_CTRL = _IOWR("V", 103, v4l2_query_ext_ctrl)

#: x86_64 reference values. The first block comes from v4l2_mmap_mjpeg.py (given + hand-expanded there); the
#: extended-control values were expanded by hand from the macros above and the struct sizes in REF_SIZES.
REF_IOCTLS = {
    "VIDIOC_QUERYCAP": 0x80685600, "VIDIOC_ENUM_FMT": 0xC0405602, "VIDIOC_G_FMT": 0xC0D05604,
    "VIDIOC_S_FMT": 0xC0D05605, "VIDIOC_REQBUFS": 0xC0145608, "VIDIOC_QUERYBUF": 0xC0585609,
    "VIDIOC_QBUF": 0xC058560F, "VIDIOC_DQBUF": 0xC0585611, "VIDIOC_STREAMON": 0x40045612,
    "VIDIOC_STREAMOFF": 0x40045613, "VIDIOC_G_PARM": 0xC0CC5615, "VIDIOC_S_PARM": 0xC0CC5616,
    "VIDIOC_G_CTRL": 0xC008561B, "VIDIOC_S_CTRL": 0xC008561C, "VIDIOC_QUERYCTRL": 0xC0445624,
    "VIDIOC_QUERYMENU": 0xC02C5625, "VIDIOC_TRY_FMT": 0xC0D05640, "VIDIOC_G_EXT_CTRLS": 0xC0205647,
    "VIDIOC_S_EXT_CTRLS": 0xC0205648, "VIDIOC_ENUM_FRAMESIZES": 0xC02C564A,
    "VIDIOC_ENUM_FRAMEINTERVALS": 0xC034564B, "VIDIOC_QUERY_EXT_CTRL": 0xC0E85667,
}
REF_SIZES = {
    "v4l2_capability": 104, "v4l2_fmtdesc": 64, "v4l2_frmsizeenum": 44, "v4l2_frmivalenum": 52,
    "v4l2_pix_format": 48, "v4l2_format": 208, "v4l2_captureparm": 40, "v4l2_streamparm": 204,
    "v4l2_requestbuffers": 20, "timeval": 16, "v4l2_timecode": 16, "v4l2_buffer": 88, "v4l2_control": 8,
    "v4l2_queryctrl": 68, "v4l2_query_ext_ctrl": 232, "v4l2_querymenu": 44, "v4l2_ext_control": 20,
    "v4l2_ext_controls": 32,
}
REF_OFFSETS = {
    ("v4l2_buffer", "timestamp"): 24, ("v4l2_buffer", "sequence"): 56, ("v4l2_buffer", "m"): 64,
    ("v4l2_buffer", "length"): 72, ("v4l2_format", "fmt"): 8, ("v4l2_streamparm", "parm"): 4,
    ("v4l2_frmivalenum", "u"): 20, ("v4l2_frmsizeenum", "u"): 12, ("v4l2_query_ext_ctrl", "minimum"): 40,
    ("v4l2_query_ext_ctrl", "flags"): 72, ("v4l2_query_ext_ctrl", "dims"): 88, ("v4l2_ext_control", "u"): 12,
    ("v4l2_ext_controls", "controls"): 24, ("v4l2_querymenu", "reserved"): 40,
}

# ----------------------------------------------------------------------------------------- constants
BUF_TYPE_VIDEO_CAPTURE = 1
BUF_TYPE_META_CAPTURE = 13
MEMORY_MMAP = 1
FIELD_ANY = 0
CAP_VIDEO_CAPTURE = 0x00000001
CAP_META_CAPTURE = 0x00800000
CAP_STREAMING = 0x04000000
CAP_DEVICE_CAPS = 0x80000000
CAP_TIMEPERFRAME = 0x1000
FMT_FLAG_COMPRESSED = 0x0001
FRMSIZE_TYPE_DISCRETE, FRMSIZE_TYPE_CONTINUOUS, FRMSIZE_TYPE_STEPWISE = 1, 2, 3
FRMIVAL_TYPE_DISCRETE = 1

BUF_FLAG_ERROR = 0x40
BUF_FLAG_TIMESTAMP_MASK = 0x0000E000
BUF_FLAG_TSTAMP_SRC_MASK = 0x00070000
TS_TYPES = {0x0000: "UNKNOWN", 0x2000: "MONOTONIC", 0x4000: "COPY"}
TS_SRCS = {0x00000: "EOF", 0x10000: "SOE"}
BUF_FLAGS = {"MAPPED": 0x1, "QUEUED": 0x2, "DONE": 0x4, "KEYFRAME": 0x8, "ERROR": 0x40, "TIMECODE": 0x100,
             "PREPARED": 0x400, "LAST": 0x100000}

CTRL_FLAG_NEXT_CTRL = 0x80000000
CTRL_FLAG_NEXT_COMPOUND = 0x40000000
CTRL_WHICH_CUR_VAL = 0
CTRL_WHICH_DEF_VAL = 0x0F000000
CTRL_TYPES = {1: "integer", 2: "boolean", 3: "menu", 4: "button", 5: "integer64", 6: "ctrl_class", 7: "string",
              8: "bitmask", 9: "integer_menu"}
CTRL_FLAGS = {"disabled": 0x1, "grabbed": 0x2, "read_only": 0x4, "update": 0x8, "inactive": 0x10, "slider": 0x20,
              "write_only": 0x40, "volatile": 0x80, "has_payload": 0x100, "execute_on_write": 0x200,
              "modify_layout": 0x400, "dynamic_array": 0x800}

CID_BASE = 0x00980900
CID_CAMERA_BASE = 0x009A0900
#: control ids by stable short name (display names changed between kernels: always match by id)
CID = {
    "brightness": CID_BASE + 0, "contrast": CID_BASE + 1, "saturation": CID_BASE + 2, "hue": CID_BASE + 3,
    "white_balance_automatic": CID_BASE + 12, "red_balance": CID_BASE + 14, "blue_balance": CID_BASE + 15,
    "gamma": CID_BASE + 16, "gain": CID_BASE + 19, "power_line_frequency": CID_BASE + 24,
    "hue_auto": CID_BASE + 25, "white_balance_temperature": CID_BASE + 26, "sharpness": CID_BASE + 27,
    "backlight_compensation": CID_BASE + 28,
    "auto_exposure": CID_CAMERA_BASE + 1, "exposure_time_absolute": CID_CAMERA_BASE + 2,
    "exposure_dynamic_framerate": CID_CAMERA_BASE + 3, "pan_relative": CID_CAMERA_BASE + 4,
    "tilt_relative": CID_CAMERA_BASE + 5, "pan_absolute": CID_CAMERA_BASE + 8, "tilt_absolute": CID_CAMERA_BASE + 9,
    "focus_absolute": CID_CAMERA_BASE + 10, "focus_relative": CID_CAMERA_BASE + 11,
    "focus_automatic_continuous": CID_CAMERA_BASE + 12, "zoom_absolute": CID_CAMERA_BASE + 13,
    "zoom_relative": CID_CAMERA_BASE + 14, "zoom_continuous": CID_CAMERA_BASE + 15, "privacy": CID_CAMERA_BASE + 16,
    "iris_absolute": CID_CAMERA_BASE + 17, "iris_relative": CID_CAMERA_BASE + 18,
    "pan_speed": CID_CAMERA_BASE + 32, "tilt_speed": CID_CAMERA_BASE + 33,
}
CID_NAME = {v: k for k, v in CID.items()}
EXPOSURE_AUTO, EXPOSURE_MANUAL, EXPOSURE_SHUTTER_PRIORITY, EXPOSURE_APERTURE_PRIORITY = 0, 1, 2, 3

UVC_STREAM_EOF, UVC_STREAM_PTS, UVC_STREAM_SCR, UVC_STREAM_ERR = 0x02, 0x04, 0x08, 0x40


def fourcc(s: str) -> int:
    return ord(s[0]) | (ord(s[1]) << 8) | (ord(s[2]) << 16) | (ord(s[3]) << 24)


def fourcc_str(v: int) -> str:
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4))


PIX_FMT_MJPEG = fourcc("MJPG")
PIX_FMT_JPEG = fourcc("JPEG")
META_FMT_UVC = fourcc("UVCH")
META_FMT_UVC_MSXU_1_5 = fourcc("UVCM")


def errno_name(e: int | None) -> str | None:
    if e is None:
        return None
    return _errno.errorcode.get(e, str(e))


def decode_buf_flags(f: int) -> dict[str, Any]:
    return {"names": [n for n, b in BUF_FLAGS.items() if f & b],
            "ts_type": TS_TYPES.get(f & BUF_FLAG_TIMESTAMP_MASK, f"0x{f & BUF_FLAG_TIMESTAMP_MASK:x}"),
            "ts_src": TS_SRCS.get(f & BUF_FLAG_TSTAMP_SRC_MASK, f"0x{f & BUF_FLAG_TSTAMP_SRC_MASK:x}"),
            "error": bool(f & BUF_FLAG_ERROR)}


def decode_ctrl_flags(f: int) -> list[str]:
    return [n for n, b in CTRL_FLAGS.items() if f & b]


def mono_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def cstr(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("utf-8", "replace")


# ----------------------------------------------------------------------------------------- UVCH metadata
def parse_uvc_meta(data: bytes) -> tuple[list[dict], dict]:
    """Parse a V4L2_META_FMT_UVC buffer: blocks of ``struct uvc_meta_buf {u64 ns; u16 sof; u8 length; u8 flags;
    u8 buf[]}`` (packed). For UVCH the kernel copies only the standard header part, so a block is 12 + len_std - 2
    bytes with len_std = 2 + 4*PTS + 6*SCR. Copied from timing/linux/v4l2_uvc_timing.py (parse_uvc_meta)."""
    blocks: list[dict] = []
    anomalies: dict[str, int] = {"length_ne_std": 0, "truncated": 0}
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


# ----------------------------------------------------------------------------------------- errors + device
class V4L2Error(OSError):
    """OSError carrying the step that failed (``stage``) and the errno name."""

    def __init__(self, stage: str, e: OSError | int, detail: str | None = None):
        code = e if isinstance(e, int) else (e.errno or 0)
        super().__init__(code, f"{stage}: {errno_name(code)}" + (f" ({detail})" if detail else ""))
        self.stage = stage
        self.errno_name = errno_name(code)

    def as_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "errno": self.errno, "errno_name": self.errno_name, "message": str(self)}


def require_linux64() -> None:
    if fcntl is None:
        raise RuntimeError("V4L2 needs Linux (fcntl)")
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        raise RuntimeError("32-bit userspace is not supported (struct layouts are LP64-only)")


def xioctl(fd: int, req: int, arg: Any, stage: str) -> Any:
    while True:
        try:
            return fcntl.ioctl(fd, req, arg, True)
        except InterruptedError:
            continue
        except OSError as e:
            raise V4L2Error(stage, e) from None


class MmapQueue:
    """REQBUFS + QUERYBUF + mmap + QBUF all buffers of one queue."""

    def __init__(self, fd: int, buf_type: int, count: int, stage: str = "reqbufs"):
        self.fd, self.type = fd, buf_type
        rb = v4l2_requestbuffers(count=count, type=buf_type, memory=MEMORY_MMAP)
        xioctl(fd, VIDIOC_REQBUFS, rb, stage)
        self.granted = rb.count
        self.capabilities = rb.capabilities
        self.maps: list[mmap.mmap] = []
        self.lengths: list[int] = []
        try:
            for i in range(rb.count):
                b = v4l2_buffer(index=i, type=buf_type, memory=MEMORY_MMAP)
                xioctl(fd, VIDIOC_QUERYBUF, b, "querybuf")
                try:
                    self.maps.append(mmap.mmap(fd, b.length, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE,
                                               offset=b.m.offset))
                except OSError as e:
                    raise V4L2Error("mmap", e) from None
                self.lengths.append(b.length)
            for i in range(rb.count):
                self.qbuf(i)
        except BaseException:
            self.close(streamoff=False)
            raise

    def qbuf(self, index: int) -> None:
        b = v4l2_buffer(index=index, type=self.type, memory=MEMORY_MMAP)
        xioctl(self.fd, VIDIOC_QBUF, b, "qbuf")

    def dqbuf(self) -> v4l2_buffer | None:
        b = v4l2_buffer(type=self.type, memory=MEMORY_MMAP)
        try:
            fcntl.ioctl(self.fd, VIDIOC_DQBUF, b, True)
        except InterruptedError:
            return None
        except OSError as e:
            if e.errno == _errno.EAGAIN:
                return None
            raise V4L2Error("dqbuf", e) from None
        return b

    def streamon(self, stage: str = "streamon") -> None:
        xioctl(self.fd, VIDIOC_STREAMON, ctypes.c_int(self.type), stage)

    def streamoff(self) -> None:
        xioctl(self.fd, VIDIOC_STREAMOFF, ctypes.c_int(self.type), "streamoff")

    def close(self, streamoff: bool = True) -> dict[str, Any]:
        """STREAMOFF, munmap, REQBUFS(0). Errors are returned, not raised (close must always complete)."""
        errs: dict[str, Any] = {}
        if streamoff:
            try:
                self.streamoff()
            except OSError as e:
                errs["streamoff"] = errno_name(e.errno)
        for m in self.maps:
            try:
                m.close()
            except (BufferError, ValueError) as e:
                errs["munmap"] = repr(e)
        self.maps = []
        try:
            fcntl.ioctl(self.fd, VIDIOC_REQBUFS, v4l2_requestbuffers(count=0, type=self.type, memory=MEMORY_MMAP),
                        True)
        except OSError as e:
            errs["reqbufs0"] = errno_name(e.errno)
        return errs


class Device:
    """One open V4L2 node (O_RDWR | O_NONBLOCK by default)."""

    def __init__(self, path: str, readonly: bool = False):
        require_linux64()
        self.path = path
        try:
            self.fd = os.open(path, (os.O_RDONLY if readonly else os.O_RDWR) | os.O_NONBLOCK)
        except OSError as e:
            raise V4L2Error("open", e) from None

    def close(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            finally:
                self.fd = None

    def __enter__(self) -> "Device":
        return self

    def __exit__(self, *a) -> None:
        self.close()

    # ---- identity
    def querycap(self) -> dict[str, Any]:
        cap = v4l2_capability()
        xioctl(self.fd, VIDIOC_QUERYCAP, cap, "querycap")
        caps = cap.device_caps if cap.capabilities & CAP_DEVICE_CAPS else cap.capabilities
        return {"driver": cstr(cap.driver), "card": cstr(cap.card), "bus_info": cstr(cap.bus_info),
                "version": f"{cap.version >> 16}.{(cap.version >> 8) & 0xFF}.{cap.version & 0xFF}",
                "capabilities": f"0x{cap.capabilities:08x}", "device_caps": f"0x{caps:08x}",
                "is_capture": bool(caps & CAP_VIDEO_CAPTURE), "is_meta": bool(caps & CAP_META_CAPTURE),
                "streaming": bool(caps & CAP_STREAMING)}

    # ---- formats (descriptor based: no USB traffic)
    def enum_formats(self, buf_type: int = BUF_TYPE_VIDEO_CAPTURE) -> list[dict[str, Any]]:
        out, i = [], 0
        while True:
            fd_ = v4l2_fmtdesc(index=i, type=buf_type)
            try:
                fcntl.ioctl(self.fd, VIDIOC_ENUM_FMT, fd_, True)
            except OSError:
                break
            out.append({"fourcc": fourcc_str(fd_.pixelformat), "pixelformat": fd_.pixelformat,
                        "description": cstr(fd_.description), "compressed": bool(fd_.flags & FMT_FLAG_COMPRESSED),
                        "flags": fd_.flags})
            i += 1
        return out

    def enum_intervals(self, pixfmt: int, w: int, h: int) -> list[dict[str, Any]]:
        res, k = [], 0
        while True:
            fi = v4l2_frmivalenum(index=k, pixel_format=pixfmt, width=w, height=h)
            try:
                fcntl.ioctl(self.fd, VIDIOC_ENUM_FRAMEINTERVALS, fi, True)
            except OSError:
                break
            if fi.type == FRMIVAL_TYPE_DISCRETE:
                d = fi.u.discrete
                res.append({"type": "discrete", "num": d.numerator, "den": d.denominator,
                            "fps": round(d.denominator / d.numerator, 3) if d.numerator else None})
            else:
                s = fi.u.stepwise
                res.append({"type": "continuous" if fi.type == 2 else "stepwise",
                            "min": [s.min.numerator, s.min.denominator], "max": [s.max.numerator, s.max.denominator],
                            "step": [s.step.numerator, s.step.denominator]})
                break
            k += 1
        return res

    def list_modes(self) -> list[dict[str, Any]]:
        """Every capture format with its frame sizes and intervals (ENUM_FMT/FRAMESIZES/FRAMEINTERVALS)."""
        fmts = self.enum_formats()
        for f in fmts:
            f["sizes"] = []
            j = 0
            while True:
                fs = v4l2_frmsizeenum(index=j, pixel_format=f["pixelformat"])
                try:
                    fcntl.ioctl(self.fd, VIDIOC_ENUM_FRAMESIZES, fs, True)
                except OSError:
                    break
                if fs.type == FRMSIZE_TYPE_DISCRETE:
                    w, h = fs.u.discrete.width, fs.u.discrete.height
                    f["sizes"].append({"type": "discrete", "w": w, "h": h,
                                       "intervals": self.enum_intervals(f["pixelformat"], w, h)})
                else:
                    sw = fs.u.stepwise
                    f["sizes"].append({"type": "continuous" if fs.type == FRMSIZE_TYPE_CONTINUOUS else "stepwise",
                                       "min": [sw.min_width, sw.min_height], "max": [sw.max_width, sw.max_height],
                                       "step": [sw.step_width, sw.step_height],
                                       "intervals_at_max": self.enum_intervals(f["pixelformat"], sw.max_width,
                                                                               sw.max_height)})
                    break
                j += 1
        return fmts

    # ---- format / rate (S_FMT sends a UVC PROBE to the camera)
    def s_fmt(self, fourcc_text: str, w: int, h: int) -> dict[str, Any]:
        f = v4l2_format(type=BUF_TYPE_VIDEO_CAPTURE)
        f.fmt.pix.width, f.fmt.pix.height = w, h
        f.fmt.pix.pixelformat, f.fmt.pix.field = fourcc(fourcc_text), FIELD_ANY
        xioctl(self.fd, VIDIOC_S_FMT, f, "s_fmt")
        p = f.fmt.pix
        return {"fourcc": fourcc_str(p.pixelformat), "width": p.width, "height": p.height,
                "sizeimage": p.sizeimage, "bytesperline": p.bytesperline, "field": p.field,
                "colorspace": p.colorspace}

    def g_fmt(self) -> dict[str, Any]:
        f = v4l2_format(type=BUF_TYPE_VIDEO_CAPTURE)
        xioctl(self.fd, VIDIOC_G_FMT, f, "g_fmt")
        p = f.fmt.pix
        return {"fourcc": fourcc_str(p.pixelformat), "width": p.width, "height": p.height, "sizeimage": p.sizeimage}

    def s_parm(self, fps: float) -> dict[str, Any]:
        sp = v4l2_streamparm(type=BUF_TYPE_VIDEO_CAPTURE)
        tpf = Fraction(1) / Fraction(fps).limit_denominator(1001000)
        sp.parm.capture.timeperframe.numerator = tpf.numerator
        sp.parm.capture.timeperframe.denominator = tpf.denominator
        xioctl(self.fd, VIDIOC_S_PARM, sp, "s_parm")
        t = sp.parm.capture.timeperframe
        return {"requested": [tpf.numerator, tpf.denominator], "returned": [t.numerator, t.denominator],
                "fps": (t.denominator / t.numerator) if t.numerator else None,
                "cap_timeperframe": bool(sp.parm.capture.capability & CAP_TIMEPERFRAME)}

    # ---- metadata node
    def s_meta_fmt(self, dataformat: int = META_FMT_UVC, buffersize: int | None = None) -> dict[str, Any]:
        f = v4l2_format(type=BUF_TYPE_META_CAPTURE)
        f.fmt.meta.dataformat = dataformat
        if buffersize:
            f.fmt.meta.buffersize = buffersize
        xioctl(self.fd, VIDIOC_S_FMT, f, "meta_s_fmt")
        return {"dataformat": fourcc_str(f.fmt.meta.dataformat), "buffersize": f.fmt.meta.buffersize,
                "requested_buffersize": buffersize}

    # ---- controls (QUERY_EXT_CTRL makes uvcvideo send GET_INFO/MIN/MAX/RES/DEF to the camera on first use)
    def _ctrl_record(self, q: "v4l2_query_ext_ctrl", menus: bool) -> dict[str, Any]:
        c = {"id": q.id, "id_hex": f"0x{q.id:08x}", "name": cstr(q.name), "short": CID_NAME.get(q.id),
             "type": CTRL_TYPES.get(q.type, q.type), "min": q.minimum, "max": q.maximum, "step": q.step,
             "default": q.default_value, "flags": decode_ctrl_flags(q.flags), "flags_raw": q.flags,
             "elem_size": q.elem_size, "elems": q.elems}
        if menus and q.type in (3, 9):
            c["menu"] = self.query_menu(q.id, q.minimum, q.maximum, integer=q.type == 9)
        return c

    def query_ext_ctrls(self, menus: bool = True, out: list | None = None, progress=None) -> list[dict[str, Any]]:
        """Full NEXT_CTRL | NEXT_COMPOUND walk. ``out`` (optional) is filled in place, so a caller's watchdog can
        emit the controls found so far; ``progress(n)`` is called before each query (re-arms a per-query watchdog).

        A query that fails with anything but EINVAL (e.g. EPIPE/ETIMEDOUT/EIO from a camera that stopped answering
        its GET_INFO/MIN/MAX: the Kiyo symptom) hides the id of the failing control, so the walk cannot continue
        with NEXT_CTRL from it. The remaining standard ids (CID table) above the last good id are then queried one
        by one, and the NEXT walk resumes from the highest one that answered (to reach driver/XU-mapped ids)."""
        out = out if out is not None else []
        cid = 0
        seen: set[int] = set()
        fallback_done = False
        while True:
            if progress:
                progress(len(out))
            q = v4l2_query_ext_ctrl(id=cid | CTRL_FLAG_NEXT_CTRL | CTRL_FLAG_NEXT_COMPOUND)
            try:
                fcntl.ioctl(self.fd, VIDIOC_QUERY_EXT_CTRL, q, True)
            except OSError as e:
                if e.errno == _errno.EINVAL:
                    break
                out.append({"id": None, "after_id": f"0x{cid:08x}", "query_errno": errno_name(e.errno)})
                if fallback_done:
                    break
                fallback_done = True
                resume = None
                for k in sorted(v for v in CID.values() if v > cid and v not in seen):
                    if progress:
                        progress(len(out))
                    q1 = v4l2_query_ext_ctrl(id=k)
                    try:
                        fcntl.ioctl(self.fd, VIDIOC_QUERY_EXT_CTRL, q1, True)
                    except OSError as e1:
                        if e1.errno != _errno.EINVAL:  # EINVAL = the camera has no such control
                            out.append({"id": None, "probe_id": f"0x{k:08x}", "short": CID_NAME.get(k),
                                        "query_errno": errno_name(e1.errno), "fallback": True})
                        continue
                    seen.add(q1.id)
                    rec = self._ctrl_record(q1, menus)
                    rec["fallback"] = True
                    out.append(rec)
                    resume = q1.id
                if resume is None:
                    break
                cid = resume
                continue
            if q.id in seen:
                if q.id <= cid:
                    break
                cid = q.id   # already found by the fallback scan: skip it, keep walking
                continue
            seen.add(q.id)
            cid = q.id
            out.append(self._ctrl_record(q, menus))
        return out

    def query_menu(self, cid: int, lo: int, hi: int, integer: bool = False) -> list[dict[str, Any]]:
        items = []
        for i in range(max(0, lo), min(hi, lo + 64) + 1):
            m = v4l2_querymenu(id=cid, index=i)
            try:
                fcntl.ioctl(self.fd, VIDIOC_QUERYMENU, m, True)
            except OSError:
                continue  # EINVAL = index not supported (gaps are normal)
            items.append({"index": i, "value": m.u.value} if integer else {"index": i, "name": cstr(m.u.name)})
        return items

    def get_ctrl(self, cid: int, int64: bool = False) -> int:
        c = v4l2_ext_control(id=cid)
        cs = v4l2_ext_controls(which=CTRL_WHICH_CUR_VAL, count=1, controls=ctypes.addressof(c))
        xioctl(self.fd, VIDIOC_G_EXT_CTRLS, cs, "g_ext_ctrls")
        return int(c.u.value64) if int64 else int(c.u.value)

    def set_ctrl(self, cid: int, value: int, int64: bool = False) -> None:
        c = v4l2_ext_control(id=cid)
        if int64:
            c.u.value64 = int(value)
        else:
            c.u.value = int(value)
        cs = v4l2_ext_controls(which=CTRL_WHICH_CUR_VAL, count=1, controls=ctypes.addressof(c))
        xioctl(self.fd, VIDIOC_S_EXT_CTRLS, cs, "s_ext_ctrls")


# ----------------------------------------------------------------------------------------- self-test
def selftest() -> dict[str, Any]:
    """Compare struct sizes, offsets and ioctl numbers with the reference tables. Runs on any OS."""
    bad = []
    g = globals()
    for name, want in REF_SIZES.items():
        got = ctypes.sizeof(g[name])
        if got != want:
            bad.append(f"sizeof({name})={got} != {want}")
    for (sname, field), want in REF_OFFSETS.items():
        got = getattr(g[sname], field).offset
        if got != want:
            bad.append(f"offsetof({sname}.{field})={got} != {want}")
    for name, want in REF_IOCTLS.items():
        if g[name] != want:
            bad.append(f"{name}=0x{g[name]:08x} != 0x{want:08x}")
    if PIX_FMT_MJPEG != 0x47504A4D or META_FMT_UVC != 0x48435655:
        bad.append("fourcc encoding")
    return {"ok": not bad, "problems": bad}
