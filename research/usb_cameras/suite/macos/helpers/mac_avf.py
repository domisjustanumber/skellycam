# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pyobjc-core==13.0; sys_platform == 'darwin'",
#   "pyobjc-framework-Cocoa==13.0; sys_platform == 'darwin'",
#   "pyobjc-framework-AVFoundation==13.0; sys_platform == 'darwin'",
#   "pyobjc-framework-CoreMedia==13.0; sys_platform == 'darwin'",
#   "pyobjc-framework-Quartz==13.0; sys_platform == 'darwin'",
#   "pyobjc-framework-libdispatch==13.0; sys_platform == 'darwin'",
#   "numpy>=2.0",
#   "pillow>=11.0",
#   "simplejpeg>=1.8",
# ]
# ///
"""AVFoundation worker for the macOS suite (child process; one camera operation per invocation).

UNTESTED: written on Windows from the AVFoundation / CoreMedia / CoreVideo headers and the repo's macOS drafts
(mjpeg/drafts/macos/avf_mjpeg_probe.py, timing/macos/avf_timing.py, bandwidth/macos/avf_multi_open.py), which
were never run either. Every PyObjC call that could differ between versions is guarded and its failure recorded.

Run by the suite runner with the runner's interpreter (its PEP 723 environment has these dependencies) or
standalone with ``uv run --script mac_avf.py <cmd> ...``. Prints ONE JSON object on stdout; per-frame data go to
``--out-dir``/frames.jsonl (and cycles.jsonl), raw frames to ``--raw-dir`` (outside the repo).

Subcommands:
  list      AVCaptureDeviceDiscoverySession (+ deprecated devicesWithMediaType) devices; ``--repeat N``
            enumerations in this process. Opens nothing; no camera permission expected to be needed.
  formats   every AVCaptureDevice.format: mediaSubType FourCC, size, frame-rate ranges with exact CMTimes. No
            session is created. ``--hold-ms N`` keeps the AVCaptureDevice object for N ms after listing (writing
            ``--hold-marker``, waiting for ``--release-file``), so M-FMT-NOGRAB can sample the alt and try a
            third-process open meanwhile.
  ctrl-avf  AVFoundation control flags (is*ModeSupported, current modes); ``--exercise`` locks and sets each
            supported exposure/focus/WB mode, reads it back and restores.
  fx        system video-effect flags per device (Center Stage, Portrait, Studio Light, Background Replacement,
            Reactions) and per format; ``--stream-seconds S`` samples the *Active flags while streaming.
  tcc       AVCaptureDevice authorizationStatus; ``--request`` asks (GUI prompt; needs a local terminal).
  capture   one session: chosen format + frame duration (exact CMTime from the range), videoSettings variant
            nil | empty | dmb1 | jpeg4cc | dmb1_sized; per-frame PTS/host time/CMIO sequence number/subtype/
            bytes/JPEG checks/metrics; runtime-error, interruption and disconnect notifications; ``--schedule``
            of ep0 / AVFoundation / probe actions; ``--controls-before`` ep0 sets before start;
            ``--ready-file`` (written at the first frame, or when the first-frame wait ends) and ``--stop-file``
            (stop early once it exists) let the runner stream in the background (M-FMT-NOGRAB).
  cycle     K in-process cycles: re-fetch device -> input -> session -> start -> first frame -> N frames -> stop.
  multi     several cameras in one process, started together or staggered.

Facts relied on (macos.md + verifiers): uniqueID = hex(locationID<<32 | VID<<16 | PID); the configuration lock is
held across startRunning() so the session preset does not replace activeFormat; frame durations must be the
range's exact CMTime; sample timestamps are on the session's synchronizationClock (documented), equal to host
time only by assumption (logged: CFEqual + port clock rate); a process without Camera permission gets zero
frames and no error; the Edge Light (26.2+) is not exposed by any device property.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SUITE_DIR = HERE.parents[1]
for _p in (str(SUITE_DIR), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import childutil  # noqa: E402
from common import jpegcheck  # noqa: E402

JPEG_SUBTYPES = {"dmb1", "jpeg", "mjpa", "mjpb"}
VARIANTS = ("nil", "empty", "dmb1", "jpeg4cc", "dmb1_sized", "chromium")
FOURCC_DMB1, FOURCC_JPEG = 0x646D6231, 0x6A706567
CMIO_INVALID_SEQ = 0xFFFFFFFFFFFFFFFF  # kCMIOInvalidSequenceNumber (CMIOSampleBuffer.h)
EXPOSURE_MODES = {0: "locked", 1: "auto_expose", 2: "continuous_auto_exposure", 3: "custom"}
FOCUS_MODES = {0: "locked", 1: "auto_focus", 2: "continuous_auto_focus"}
WB_MODES = {0: "locked", 1: "auto_white_balance", 2: "continuous_auto_white_balance"}
AUTH = {0: "notDetermined", 1: "restricted", 2: "denied", 3: "authorized"}

FW: dict[str, Any] = {}


# ============================================================================================ framework loading
def load_frameworks() -> dict:
    """Import PyObjC lazily (so --help works anywhere). Returns FW with modules and a few C helpers."""
    if FW:
        return FW
    import objc  # noqa: F401
    import AVFoundation as AVF
    import CoreMedia as CM
    import Foundation
    try:
        import dispatch
    except ImportError:  # older module name, still supported in pyobjc 13 (verifier M38)
        import libdispatch as dispatch  # type: ignore
    try:
        from CoreFoundation import CFEqual
    except ImportError:
        CFEqual = None
    FW.update(objc=objc, AVF=AVF, CM=CM, Foundation=Foundation, dispatch=dispatch, CFEqual=CFEqual)
    FW["HOST"] = CM.CMClockGetHostTimeClock()
    # ctypes access to CoreMedia / CoreVideo / CoreMediaIO C functions (avoids PyObjC buffer conventions)
    try:
        cm = ctypes.CDLL("/System/Library/Frameworks/CoreMedia.framework/CoreMedia")
        cm.CMBlockBufferGetDataLength.argtypes = [ctypes.c_void_p]
        cm.CMBlockBufferGetDataLength.restype = ctypes.c_size_t
        cm.CMBlockBufferCopyDataBytes.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p]
        cm.CMBlockBufferCopyDataBytes.restype = ctypes.c_int32
        FW["cm_c"] = cm
    except OSError as e:
        FW["cm_c_error"] = repr(e)
    try:
        cv = ctypes.CDLL("/System/Library/Frameworks/CoreVideo.framework/CoreVideo")
        for fn, res, args in [("CVPixelBufferLockBaseAddress", ctypes.c_int32, [ctypes.c_void_p, ctypes.c_uint64]),
                              ("CVPixelBufferUnlockBaseAddress", ctypes.c_int32, [ctypes.c_void_p, ctypes.c_uint64]),
                              ("CVPixelBufferGetPixelFormatType", ctypes.c_uint32, [ctypes.c_void_p]),
                              ("CVPixelBufferGetWidth", ctypes.c_size_t, [ctypes.c_void_p]),
                              ("CVPixelBufferGetHeight", ctypes.c_size_t, [ctypes.c_void_p]),
                              ("CVPixelBufferGetDataSize", ctypes.c_size_t, [ctypes.c_void_p]),
                              ("CVPixelBufferIsPlanar", ctypes.c_uint8, [ctypes.c_void_p]),
                              ("CVPixelBufferGetBaseAddress", ctypes.c_void_p, [ctypes.c_void_p]),
                              ("CVPixelBufferGetBytesPerRow", ctypes.c_size_t, [ctypes.c_void_p]),
                              ("CVPixelBufferGetBaseAddressOfPlane", ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_size_t]),
                              ("CVPixelBufferGetBytesPerRowOfPlane", ctypes.c_size_t, [ctypes.c_void_p, ctypes.c_size_t]),
                              ("CVPixelBufferGetWidthOfPlane", ctypes.c_size_t, [ctypes.c_void_p, ctypes.c_size_t]),
                              ("CVPixelBufferGetHeightOfPlane", ctypes.c_size_t, [ctypes.c_void_p, ctypes.c_size_t])]:
            f = getattr(cv, fn)
            f.restype, f.argtypes = res, args
        FW["cv_c"] = cv
    except OSError as e:
        FW["cv_c_error"] = repr(e)
    try:
        cmio = ctypes.CDLL("/System/Library/Frameworks/CoreMediaIO.framework/CoreMediaIO")
        cmio.CMIOSampleBufferGetSequenceNumber.argtypes = [ctypes.c_void_p]
        cmio.CMIOSampleBufferGetSequenceNumber.restype = ctypes.c_uint64
        cmio.CMIOSampleBufferGetDiscontinuityFlags.argtypes = [ctypes.c_void_p]
        cmio.CMIOSampleBufferGetDiscontinuityFlags.restype = ctypes.c_uint32
        FW["cmio_c"] = cmio
    except (OSError, AttributeError) as e:
        FW["cmio_c_error"] = repr(e)
    return FW


def ptr_of(o: Any) -> int | None:
    """Raw pointer of a PyObjC CF/ObjC proxy."""
    if o is None:
        return None
    for attr in ("__c_void_p__",):
        f = getattr(o, attr, None)
        if f is not None:
            try:
                return f().value
            except Exception:
                pass
    p = getattr(o, "__pointer__", None)
    if isinstance(p, int):
        return p
    try:
        return FW["objc"].pyobjc_id(o)
    except Exception:
        return None


# ============================================================================================ small helpers
def fourcc(v: Any) -> str:
    try:
        v = int(v)
    except Exception:
        return str(v)
    b = bytes([(v >> 24) & 255, (v >> 16) & 255, (v >> 8) & 255, v & 255])
    return b.decode("latin-1") if all(32 <= c < 127 for c in b) else f"0x{v:08x}"


def cmtime(t: Any) -> dict | None:
    if t is None:
        return None
    try:
        return {"value": int(t.value), "timescale": int(t.timescale), "flags": int(t.flags), "epoch": int(t.epoch)}
    except Exception:
        try:
            v, ts, fl, ep = t
            return {"value": int(v), "timescale": int(ts), "flags": int(fl), "epoch": int(ep)}
        except Exception:
            return None


def cmtime_ns(t: Any) -> int | None:
    d = cmtime(t)
    if not d or not (d["flags"] & 1) or d["timescale"] <= 0:
        return None
    return d["value"] * 1_000_000_000 // d["timescale"]


def host_ns() -> int | None:
    return cmtime_ns(FW["CM"].CMClockGetTime(FW["HOST"]))


def js(o: Any, depth: int = 0) -> Any:
    if depth > 6:
        return str(o)
    if o is None or isinstance(o, (bool, int, float)):
        return o
    if isinstance(o, str):
        return str(o)
    if hasattr(o, "keys"):
        try:
            return {str(k): js(o[k], depth + 1) for k in o.keys()}
        except Exception:
            return str(o)
    if isinstance(o, (list, tuple)) or (hasattr(o, "count") and hasattr(o, "objectAtIndex_")):
        try:
            return [js(x, depth + 1) for x in o]
        except Exception:
            return str(o)
    try:
        f = float(o)
        return int(f) if f.is_integer() else f
    except Exception:
        return str(o)[:300]


def call(obj: Any, *names: str, args: tuple = (), default: Any = None) -> Any:
    """First existing selector among names, called with args; errors returned as 'error: ...' strings."""
    for n in names:
        f = getattr(obj, n, None)
        if f is None:
            continue
        try:
            return f(*args)
        except Exception as e:
            return f"error: {e!r}"
    return default


def nserror(err: Any, depth: int = 0) -> dict | None:
    """NSError -> {domain, code, code_hex, description, underlying (chain), iokit_codes}."""
    if err is None or depth > 5:
        return None
    try:
        code = int(err.code())
        d = {"domain": str(err.domain()), "code": code, "code_hex": f"0x{code & 0xFFFFFFFF:08X}",
             "description": str(err.localizedDescription())}
        ui = err.userInfo()
        und = ui.get("NSUnderlyingError") if ui is not None else None
        d["underlying"] = nserror(und, depth + 1) if und is not None else None
        codes = [code]
        u = d["underlying"]
        while u:
            codes.append(u["code"])
            u = u.get("underlying")
        d["iokit_codes"] = [f"0x{c & 0xFFFFFFFF:08X}" for c in codes if (c & 0xFFFFFFFF) >> 24 == 0xE0]
        d["all_codes"] = codes
        return d
    except Exception as e:
        return {"repr": str(err)[:300], "parse_error": repr(e)}


def cpu_now() -> float:
    try:
        import resource
        r = resource.getrusage(resource.RUSAGE_SELF)
        return r.ru_utime + r.ru_stime
    except ImportError:  # not on macOS (tests)
        return time.process_time()


# ============================================================================================ devices
def discovery_types() -> list:
    AVF = FW["AVF"]
    names = ["AVCaptureDeviceTypeExternal", "AVCaptureDeviceTypeExternalUnknown",
             "AVCaptureDeviceTypeBuiltInWideAngleCamera", "AVCaptureDeviceTypeContinuityCamera",
             "AVCaptureDeviceTypeDeskViewCamera"]
    return [getattr(AVF, n) for n in names if hasattr(AVF, n)]


def discover() -> tuple[list, str | None]:
    AVF = FW["AVF"]
    try:
        ds = AVF.AVCaptureDeviceDiscoverySession.discoverySessionWithDeviceTypes_mediaType_position_(
            discovery_types(), AVF.AVMediaTypeVideo, getattr(AVF, "AVCaptureDevicePositionUnspecified", 0))
        return list(ds.devices() or []), None
    except Exception as e:
        return [], repr(e)


def legacy_devices() -> tuple[list, str | None]:
    AVF = FW["AVF"]
    try:
        return list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeVideo) or []), None
    except Exception as e:
        return [], repr(e)


def find_device(spec: str):
    AVF = FW["AVF"]
    try:
        d = AVF.AVCaptureDevice.deviceWithUniqueID_(spec)
        if d is not None:
            return d
    except Exception:
        pass
    devs, _ = discover()
    if re.fullmatch(r"\d+", spec or "") and int(spec) < len(devs):
        return devs[int(spec)]
    for d in devs:
        if str(d.uniqueID()).lower() == str(spec).lower():
            return d
    for d in devs:
        if str(spec).lower() in str(d.localizedName()).lower():
            return d
    return None


def describe_format(i: int, f: Any) -> dict:
    CM = FW["CM"]
    fd = f.formatDescription()
    sub = CM.CMFormatDescriptionGetMediaSubType(fd)
    dims = CM.CMVideoFormatDescriptionGetDimensions(fd)
    try:
        w, h = int(dims.width), int(dims.height)
    except AttributeError:
        w, h = int(dims[0]), int(dims[1])
    ranges = []
    for r in f.videoSupportedFrameRateRanges() or []:
        ranges.append({"min_fps": float(r.minFrameRate()), "max_fps": float(r.maxFrameRate()),
                       "min_frame_duration": cmtime(r.minFrameDuration()),
                       "max_frame_duration": cmtime(r.maxFrameDuration())})
    out = {"index": i, "subtype": fourcc(sub), "subtype_int": int(sub), "w": w, "h": h, "ranges": ranges,
           "discrete": all(abs(r["min_fps"] - r["max_fps"]) < 1e-3 for r in ranges) if ranges else None,
           "media_type": str(call(f, "mediaType")), "description": str(f)[:240]}
    try:
        ext = js(CM.CMFormatDescriptionGetExtensions(fd)) or {}
        out["extensions"] = {k: v for k, v in ext.items() if k in ("FormatName", "Depth", "FullRangeVideo", "Version")}
    except Exception as e:
        out["extensions"] = f"error: {e!r}"
    for prop in ("isReactionEffectsSupported", "reactionEffectsSupported", "isCenterStageSupported",
                 "isPortraitEffectSupported", "isStudioLightSupported", "isBackgroundReplacementSupported",
                 "isVideoHDRSupported"):
        v = call(f, prop)
        if v is not None and not isinstance(v, str):
            out[prop] = bool(v)
    return out


def describe_device(i: int, d: Any, formats: bool = False) -> dict:
    from mac_ioreg import parse_unique_id, parse_model_id
    tt = call(d, "transportType", default=0)
    uid = str(d.uniqueID())
    out = {"order": i, "unique_id": uid, "model_id": str(call(d, "modelID")), "name": str(d.localizedName()),
           "manufacturer": str(call(d, "manufacturer")), "transport": fourcc(tt) if isinstance(tt, int) else str(tt),
           "device_type": str(call(d, "deviceType")), "connected": call(d, "isConnected"),
           "suspended": call(d, "isSuspended"), "in_use_by_other_app": call(d, "isInUseByAnotherApplication"),
           "uid_parsed": parse_unique_id(uid), "model_parsed": parse_model_id(str(call(d, "modelID")))}
    out["is_usb"] = out["transport"].strip() == "usb" or out["uid_parsed"] is not None
    if formats:
        out["formats"] = [describe_format(j, f) for j, f in enumerate(d.formats() or [])]
        try:
            out["active_format"] = describe_format(-1, d.activeFormat())
        except Exception as e:
            out["active_format"] = f"error: {e!r}"
    return out


def pick_range(fdesc: dict, fps: float | None):
    """Index of the frame-rate range for fps (closest max_fps when fps is None or not exact) and which end."""
    rs = fdesc["ranges"]
    if not rs:
        return None, None
    if fps is None:
        i = max(range(len(rs)), key=lambda k: rs[k]["max_fps"])
        return i, "min_frame_duration"
    for i, r in enumerate(rs):
        if abs(r["max_fps"] - fps) < 0.01:
            return i, "min_frame_duration"
        if abs(r["min_fps"] - fps) < 0.01:
            return i, "max_frame_duration"
    for i, r in enumerate(rs):
        if r["min_fps"] - 0.01 <= fps <= r["max_fps"] + 0.01:
            return i, "computed"
    return None, None


# ============================================================================================ sample processing
def block_bytes(sbuf: Any, bb: Any, stats: dict) -> bytes | None:
    """Copy the CMBlockBuffer's bytes. ctypes on CoreMedia first, then the PyObjC conventions of the draft."""
    cm = FW.get("cm_c")
    p = ptr_of(bb)
    if cm is not None and p:
        try:
            n = int(cm.CMBlockBufferGetDataLength(p))
            buf = ctypes.create_string_buffer(max(1, n))
            st = cm.CMBlockBufferCopyDataBytes(p, 0, n, buf)
            if st == 0:
                stats.setdefault("copy_method", "ctypes CMBlockBufferCopyDataBytes")
                return buf.raw[:n]
            stats.setdefault("copy_failures", []).append(f"ctypes status {st}")
        except Exception as e:
            stats.setdefault("copy_failures", []).append(f"ctypes: {e!r}")
    CM = FW["CM"]
    try:
        n = int(CM.CMBlockBufferGetDataLength(bb))
        r = CM.CMBlockBufferCopyDataBytes(bb, 0, n, None)
        if isinstance(r, tuple) and len(r) == 2 and r[0] == 0 and r[1] is not None:
            stats.setdefault("copy_method", "pyobjc CMBlockBufferCopyDataBytes(None)")
            return bytes(r[1])[:n]
        buf = bytearray(n)
        r = CM.CMBlockBufferCopyDataBytes(bb, 0, n, buf)
        st = r[0] if isinstance(r, tuple) else r
        if st == 0:
            stats.setdefault("copy_method", "pyobjc CMBlockBufferCopyDataBytes(bytearray)")
            return bytes(r[1]) if isinstance(r, tuple) and isinstance(r[1], (bytes, bytearray)) else bytes(buf)
    except Exception as e:
        if len(stats.setdefault("copy_failures", [])) < 5:
            stats["copy_failures"].append(f"pyobjc: {e!r}")
    return None


def pixel_info(ib: Any) -> dict:
    cv = FW.get("cv_c")
    p = ptr_of(ib)
    if cv is None or not p:
        return {}
    try:
        return {"cv_fmt": fourcc(cv.CVPixelBufferGetPixelFormatType(p)), "w": int(cv.CVPixelBufferGetWidth(p)),
                "h": int(cv.CVPixelBufferGetHeight(p)), "bytes": int(cv.CVPixelBufferGetDataSize(p)),
                "planar": bool(cv.CVPixelBufferIsPlanar(p))}
    except Exception as e:
        return {"pixel_info_error": repr(e)}


def pixel_metrics(ib: Any, step: int = 4) -> dict | None:
    """Mean luma, R/B ratio (from mean Cb/Cr or BGRA) and normalised Laplacian sharpness of a CVPixelBuffer
    (420v/420f/2vuy/yuvs/BGRA). Used when AVFoundation hands decoded pixels instead of JPEG bytes."""
    import numpy as np
    cv = FW.get("cv_c")
    p = ptr_of(ib)
    if cv is None or not p:
        return None
    if cv.CVPixelBufferLockBaseAddress(p, 1) != 0:
        return {"error": "lock failed"}
    try:
        fmt = fourcc(cv.CVPixelBufferGetPixelFormatType(p))
        w, h = int(cv.CVPixelBufferGetWidth(p)), int(cv.CVPixelBufferGetHeight(p))
        if cv.CVPixelBufferIsPlanar(p):
            def plane(i):
                base = cv.CVPixelBufferGetBaseAddressOfPlane(p, i)
                bpr = cv.CVPixelBufferGetBytesPerRowOfPlane(p, i)
                ph = cv.CVPixelBufferGetHeightOfPlane(p, i)
                pw = cv.CVPixelBufferGetWidthOfPlane(p, i)
                a = np.frombuffer(ctypes.string_at(base, bpr * ph), np.uint8).reshape(ph, bpr)
                return a, pw
            y, _ = plane(0)
            y = y[:, :w].astype(np.float32)
            uv, pw = plane(1)
            uv = uv[:, :pw * 2].astype(np.float32)
            cb, cr = uv[:, 0::2], uv[:, 1::2]
        else:
            base = cv.CVPixelBufferGetBaseAddress(p)
            bpr = cv.CVPixelBufferGetBytesPerRow(p)
            a = np.frombuffer(ctypes.string_at(base, bpr * h), np.uint8).reshape(h, bpr)
            if fmt == "2vuy":
                row = a[:, :w * 2].astype(np.float32)
                y, cb, cr = row[:, 1::2], row[:, 0::4], row[:, 2::4]
            elif fmt in ("yuvs", "yuv2"):
                row = a[:, :w * 2].astype(np.float32)
                y, cb, cr = row[:, 0::2], row[:, 1::4], row[:, 3::4]
            elif fmt == "BGRA":
                px = a[:, :w * 4].reshape(h, w, 4).astype(np.float32)
                b, g, r = px[..., 0], px[..., 1], px[..., 2]
                y = 0.299 * r + 0.587 * g + 0.114 * b
                return {"luma": float(y[::step, ::step].mean()), "rb": float(r.mean() / max(b.mean(), 1e-6)),
                        "sharp": _sharp(y), "fmt": fmt}
            else:
                return {"error": f"unsupported pixel format {fmt}"}
        ym, cbm, crm = float(y[::step, ::step].mean()), float(cb.mean()), float(cr.mean())
        rmean = ym + 1.402 * (crm - 128.0)
        bmean = ym + 1.772 * (cbm - 128.0)
        return {"luma": ym, "rb": float(rmean / max(bmean, 1e-6)), "sharp": _sharp(y), "fmt": fmt}
    except Exception as e:
        return {"error": repr(e)}
    finally:
        cv.CVPixelBufferUnlockBaseAddress(p, 1)


def _sharp(y) -> float:
    y = y[::2, ::2]
    lap = (-4 * y[1:-1, 1:-1] + y[:-2, 1:-1] + y[2:, 1:-1] + y[1:-1, :-2] + y[1:-1, 2:])
    m = float(y.mean())
    return float(lap.var() / max(m * m, 1e-6))


def jpeg_metrics(b: bytes) -> dict | None:
    try:
        from common import imgmetrics
        return {"luma": imgmetrics.luma_mean(b), "rb": imgmetrics.rb_ratio(b), "sharp": imgmetrics.sharpness(b, draft_scale=2)}
    except Exception as e:
        return {"error": repr(e)}


def cmio_seq(sbuf: Any) -> tuple[int | None, int | None]:
    c = FW.get("cmio_c")
    p = ptr_of(sbuf)
    if c is None or not p:
        return None, None
    try:
        seq = int(c.CMIOSampleBufferGetSequenceNumber(p))
        disc = int(c.CMIOSampleBufferGetDiscontinuityFlags(p))
    except Exception:
        return None, None
    # kCMIOInvalidSequenceNumber = ~0ULL: the buffer carries no CMIO sequence attachment (AVFoundation may strip it).
    # Reporting it as a number would make "sequence number present" true and every frame look identical.
    return (None if seq == CMIO_INVALID_SEQ else seq), disc


class Recorder:
    """Per-camera sample processing (called on the AVFoundation delegate queue)."""

    def __init__(self, out_dir: Path | None, raw_dir: Path | None, save: str = "none", jpeg_check: str = "all",
                 metrics_every: int = 0, keep_rows: bool = True, label: str = "", max_save_bytes: int = 400_000_000):
        self.lock = threading.Lock()
        self.first = threading.Event()
        self.count = 0
        self.rows: list[dict] = []
        self.keep_rows = keep_rows
        self.kinds = {"block": 0, "image": 0, "none": 0}
        self.subtypes: dict[str, int] = {}
        self.cv_formats: dict[str, int] = {}
        self.dropped: list[dict] = []
        self.errors: list[str] = []
        self.stats: dict[str, Any] = {}
        self.jpeg_check = jpeg_check
        self.metrics_every = int(metrics_every)
        self.session_clock = None
        self.label = label
        self.t_first_host = None
        self.out_dir, self.raw_dir = out_dir, raw_dir
        self.save_mode, self.save_k = (save.split(":") + ["1"])[:2] if ":" in save else (save, "1")
        self.save_k = int(self.save_k or 1)
        self.max_save_bytes = max_save_bytes
        self.saved_bytes = 0
        self.fp_jsonl = open(out_dir / "frames.jsonl", "a", encoding="utf-8") if out_dir else None
        self.fp_raw = None
        if raw_dir and self.save_mode != "none":
            raw_dir.mkdir(parents=True, exist_ok=True)
            self.fp_raw = open(raw_dir / "frames.mjpeg", "ab")

    def on_sample(self, sbuf: Any) -> None:
        CM = FW["CM"]
        t_host = host_ns()
        t_mach = childutil.mach_ns()
        row: dict[str, Any] = {"seq": self.count, "host_ns": t_host, "mach_ns": t_mach}
        try:
            fd = CM.CMSampleBufferGetFormatDescription(sbuf)
            sub = fourcc(CM.CMFormatDescriptionGetMediaSubType(fd)) if fd is not None else None
            pts = CM.CMSampleBufferGetPresentationTimeStamp(sbuf)
            row["pts"] = cmtime(pts)
            row["pts_ns"] = cmtime_ns(pts)
            if self.session_clock is not None and row["pts_ns"] is not None:
                try:
                    row["pts_host_ns"] = cmtime_ns(CM.CMSyncConvertTime(pts, self.session_clock, FW["HOST"]))
                except Exception:
                    row["pts_host_ns"] = None
            row["dur_ns"] = cmtime_ns(CM.CMSampleBufferGetDuration(sbuf))
            row["subtype"] = sub
            row["cmio_seq"], row["cmio_disc"] = cmio_seq(sbuf)
            bb = CM.CMSampleBufferGetDataBuffer(sbuf)
            ib = CM.CMSampleBufferGetImageBuffer(sbuf)
            payload = None
            if bb is not None:
                row["kind"] = "block"
                payload = block_bytes(sbuf, bb, self.stats)
                row["bytes"] = len(payload) if payload is not None else None
            elif ib is not None:
                row["kind"] = "image"
                row.update(pixel_info(ib))
            else:
                row["kind"] = "none"
            if payload:
                do_strict = self.jpeg_check == "all" or (self.jpeg_check.startswith("every:")
                                                         and self.count % int(self.jpeg_check.split(":")[1]) == 0)
                chk = jpegcheck.check_jpeg(payload, decode=do_strict)
                row.update({k: chk.get(k) for k in ("soi", "eoi", "sof0_w", "sof0_h", "header_sha1", "lenient_ok",
                                                     "strict_ok", "extra_bytes_before_eoi", "marker_ok")})
                if self.fp_raw is not None and self._want_save() and self.saved_bytes + len(payload) <= self.max_save_bytes:
                    row["raw_offset"] = self.saved_bytes
                    self.fp_raw.write(payload)
                    self.saved_bytes += len(payload)
            if self.metrics_every and self.count % self.metrics_every == 0:
                if payload and row.get("soi"):
                    row["metrics"] = jpeg_metrics(payload)
                elif ib is not None:
                    row["metrics"] = pixel_metrics(ib)
            if self.count < 3:
                try:
                    att = CM.CMCopyDictionaryOfAttachments(None, sbuf, 1)
                    row["attachments"] = js(att) if att is not None else None
                except Exception as e:
                    row["attachments"] = f"error: {e!r}"
        except Exception as e:
            if len(self.errors) < 20:
                self.errors.append(f"sample {self.count}: {e!r}")
        with self.lock:
            k = row.get("kind") or "none"
            self.kinds[k] = self.kinds.get(k, 0) + 1
            if row.get("subtype"):
                self.subtypes[row["subtype"]] = self.subtypes.get(row["subtype"], 0) + 1
            if row.get("cv_fmt"):
                self.cv_formats[row["cv_fmt"]] = self.cv_formats.get(row["cv_fmt"], 0) + 1
            if self.keep_rows:
                self.rows.append(row)
            if self.fp_jsonl is not None:
                self.fp_jsonl.write(json.dumps(row, default=str) + "\n")
            self.count += 1
            if self.t_first_host is None:
                self.t_first_host = t_host
                self.first.set()

    def _want_save(self) -> bool:
        if self.save_mode == "all":
            return True
        if self.save_mode == "every":
            return self.count % max(1, self.save_k) == 0
        if self.save_mode == "first":
            return self.count < self.save_k
        return False

    def on_drop(self, sbuf: Any) -> None:
        reason = None
        try:
            CM = FW["CM"]
            r = CM.CMGetAttachment(sbuf, CM.kCMSampleBufferAttachmentKey_DroppedFrameReason, None)
            reason = str(r[0] if isinstance(r, tuple) else r)
        except Exception as e:
            reason = f"? {e!r}"
        with self.lock:
            if len(self.dropped) < 10000:
                self.dropped.append({"host_ns": host_ns(), "reason": reason})

    def close(self) -> None:
        with self.lock:
            for f in (self.fp_jsonl, self.fp_raw):
                try:
                    if f:
                        f.close()
                except Exception:
                    pass
            self.fp_jsonl = self.fp_raw = None


_DELEGATE_CLASS = None
_OBSERVER_CLASS = None


def delegate_class():
    global _DELEGATE_CLASS
    if _DELEGATE_CLASS is not None:
        return _DELEGATE_CLASS
    objc, Foundation = FW["objc"], FW["Foundation"]
    try:
        protos = [objc.protocolNamed("AVCaptureVideoDataOutputSampleBufferDelegate")]
    except Exception:
        protos = []

    class SkellySuiteSampleDelegate(Foundation.NSObject, protocols=protos):
        def captureOutput_didOutputSampleBuffer_fromConnection_(self, output, sbuf, conn):
            rec = getattr(self, "_rec", None)
            if rec is not None:
                rec.on_sample(sbuf)

        def captureOutput_didDropSampleBuffer_fromConnection_(self, output, sbuf, conn):
            rec = getattr(self, "_rec", None)
            if rec is not None:
                rec.on_drop(sbuf)

    _DELEGATE_CLASS = SkellySuiteSampleDelegate
    return _DELEGATE_CLASS


def observer_class():
    global _OBSERVER_CLASS
    if _OBSERVER_CLASS is not None:
        return _OBSERVER_CLASS
    Foundation = FW["Foundation"]

    class SkellySuiteObserver(Foundation.NSObject):
        def onNote_(self, note):
            sink = getattr(self, "_sink", None)
            if sink is None:
                return
            AVF = FW["AVF"]
            rec = {"name": str(note.name()), "host_ns": host_ns()}
            try:
                ui = note.userInfo()
                if ui is not None:
                    err = ui.get(AVF.AVCaptureSessionErrorKey) if hasattr(AVF, "AVCaptureSessionErrorKey") else None
                    if err is not None:
                        rec["error"] = nserror(err)
                    reason = ui.get("AVCaptureSessionInterruptionReasonKey")
                    if reason is not None:
                        rec["interruption_reason"] = js(reason)
            except Exception as e:
                rec["userinfo_error"] = repr(e)
            sink.append(rec)

    _OBSERVER_CLASS = SkellySuiteObserver
    return _OBSERVER_CLASS


def observe(session: Any, device: Any, sink: list) -> Any:
    AVF, Foundation = FW["AVF"], FW["Foundation"]
    obs = observer_class().alloc().init()
    obs._sink = sink
    nc = Foundation.NSNotificationCenter.defaultCenter()
    for n in ("AVCaptureSessionRuntimeErrorNotification", "AVCaptureSessionWasInterruptedNotification",
              "AVCaptureSessionInterruptionEndedNotification", "AVCaptureSessionDidStartRunningNotification",
              "AVCaptureSessionDidStopRunningNotification"):
        if hasattr(AVF, n):
            nc.addObserver_selector_name_object_(obs, "onNote:", getattr(AVF, n), session)
    for n in ("AVCaptureDeviceWasDisconnectedNotification",):
        if hasattr(AVF, n):
            nc.addObserver_selector_name_object_(obs, "onNote:", getattr(AVF, n), device)
    return obs


def unobserve(obs: Any) -> None:
    try:
        FW["Foundation"].NSNotificationCenter.defaultCenter().removeObserver_(obs)
    except Exception:
        pass


def pump(seconds: float, until: threading.Event | None = None, step: float = 0.02) -> bool:
    Foundation = FW["Foundation"]
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if until is not None and until.is_set():
            return True
        Foundation.NSRunLoop.currentRunLoop().runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(step))
    return bool(until.is_set()) if until is not None else True


def video_settings(variant: str, fdesc: dict) -> Any:
    try:
        import Quartz
        key = getattr(Quartz, "kCVPixelBufferPixelFormatTypeKey", "PixelFormatType")
        wkey = getattr(Quartz, "kCVPixelBufferWidthKey", "Width")
        hkey = getattr(Quartz, "kCVPixelBufferHeightKey", "Height")
    except Exception:
        key, wkey, hkey = "PixelFormatType", "Width", "Height"
    if variant == "nil":
        return None
    if variant == "empty":
        return {}
    if variant == "dmb1":
        return {key: FOURCC_DMB1}
    if variant == "jpeg4cc":
        return {key: FOURCC_JPEG}
    if variant == "dmb1_sized":  # Chromium also passes the size
        return {key: FOURCC_DMB1, wkey: fdesc["w"], hkey: fdesc["h"]}
    if variant == "chromium":
        # Chromium video_capture_device_avfoundation_mac.mm setCaptureHeight:width:frameRate: for an MJPEG format:
        # {Width, Height, PixelFormatType = kCMVideoCodecType_JPEG_OpenDML, AVVideoScalingModeKey = ResizeAspectFill}
        try:
            AVF = FW["AVF"]
            skey = getattr(AVF, "AVVideoScalingModeKey", "AVVideoScalingModeKey")
            sval = getattr(AVF, "AVVideoScalingModeResizeAspectFill", "AVVideoScalingModeResizeAspectFill")
        except Exception:
            skey, sval = "AVVideoScalingModeKey", "AVVideoScalingModeResizeAspectFill"
        return {key: FOURCC_DMB1, wkey: fdesc["w"], hkey: fdesc["h"], skey: sval}
    raise ValueError(variant)


# ============================================================================================ session building
class Stream:
    """One AVCaptureSession for one device and format. Build -> start -> stop -> teardown, timing every step."""

    def __init__(self, dev: Any, fmt_index: int | None, fps: float | None, variant: str, rec: Recorder,
                 queue_name: str = "skellycam.suite"):
        self.dev, self.fmt_index, self.fps, self.variant, self.rec = dev, fmt_index, fps, variant, rec
        self.queue_name = queue_name
        self.session = self.output = self.input = self.obs = None
        self.notes: list[dict] = []
        self.info: dict[str, Any] = {"variant": variant, "timings_ms": {}}
        self.stage = "init"
        self.locked = False

    def _t(self, name: str, t0: float) -> None:
        self.info["timings_ms"][name] = round((time.perf_counter() - t0) * 1000, 3)

    def build(self) -> bool:
        AVF, dispatch = FW["AVF"], FW["dispatch"]
        dev = self.dev
        fmts = list(dev.formats() or [])
        if self.fmt_index is None:
            self.fmt_index = fmts.index(dev.activeFormat()) if dev.activeFormat() in fmts else 0
        if not (0 <= self.fmt_index < len(fmts)):
            self.info["error"], self.stage = f"format index {self.fmt_index} out of range ({len(fmts)})", "format"
            return False
        fmt = fmts[self.fmt_index]
        fdesc = describe_format(self.fmt_index, fmt)
        self.info["requested_format"] = fdesc
        ri, end = pick_range(fdesc, self.fps)
        self.stage = "input"
        t0 = time.perf_counter()
        inp, err = AVF.AVCaptureDeviceInput.deviceInputWithDevice_error_(dev, None)
        self._t("input", t0)
        if inp is None:
            self.info["error"] = nserror(err) or "deviceInputWithDevice returned nil"
            return False
        self.input = inp
        self.stage = "configure"
        t0 = time.perf_counter()
        s = AVF.AVCaptureSession.alloc().init()
        self.session = s
        self.obs = observe(s, dev, self.notes)
        s.beginConfiguration()
        if not s.canAddInput_(inp):
            s.commitConfiguration()
            self.info["error"], self.stage = "session cannot add input (camera in use?)", "add_input"
            return False
        s.addInput_(inp)
        out = AVF.AVCaptureVideoDataOutput.alloc().init()
        self.output = out
        settings = video_settings(self.variant, fdesc)
        self.info["video_settings_set"] = js(settings) if settings is not None else "nil"
        try:
            out.setVideoSettings_(settings)
            self.info["video_settings_accepted"] = True
        except Exception as e:
            self.info["video_settings_accepted"] = False
            self.info["video_settings_error"] = repr(e)[:400]
        self.info["video_settings_readback"] = js(call(out, "videoSettings"))
        out.setAlwaysDiscardsLateVideoFrames_(False)
        d = delegate_class().alloc().init()
        d._rec = self.rec
        self._delegate = d
        q = dispatch.dispatch_queue_create(self.queue_name.encode(), None)
        out.setSampleBufferDelegate_queue_(d, q)
        if not s.canAddOutput_(out):
            s.commitConfiguration()
            self.info["error"], self.stage = "session cannot add AVCaptureVideoDataOutput", "add_output"
            return False
        s.addOutput_(out)
        self.info["available_cv_formats"] = [fourcc(x) for x in (call(out, "availableVideoCVPixelFormatTypes") or [])
                                             if not isinstance(x, str)]
        self.info["available_codec_types"] = [str(x) for x in (call(out, "availableVideoCodecTypes") or [])]
        ok, lerr = dev.lockForConfiguration_(None)
        self.locked = bool(ok)
        if not ok:
            s.commitConfiguration()
            self.info["error"], self.stage = {"lockForConfiguration": nserror(lerr)}, "lock"
            return False
        try:
            dev.setActiveFormat_(fmt)
            if ri is not None:
                rng = list(fmt.videoSupportedFrameRateRanges())[ri]
                if end == "max_frame_duration":
                    dur = rng.maxFrameDuration()
                elif end == "min_frame_duration":
                    dur = rng.minFrameDuration()
                else:
                    dur = FW["CM"].CMTimeMake(1_000_000, int(round(self.fps * 1_000_000)))
                dev.setActiveVideoMinFrameDuration_(dur)
                dev.setActiveVideoMaxFrameDuration_(dur)
                self.info["frame_duration_set"] = cmtime(dur)
                self.info["frame_duration_how"] = end
        except Exception as e:
            self.info["set_format_error"] = repr(e)[:400]
        s.commitConfiguration()
        self._t("configure", t0)
        self.info["session_preset_before_start"] = str(call(s, "sessionPreset"))
        return True

    def start(self) -> bool:
        self.stage = "start"
        t0 = time.perf_counter()
        self.info["host_ns_start_call"] = host_ns()
        try:
            self.session.startRunning()  # lock still held: activeFormat survives the preset (macos.md 3)
        except Exception as e:
            self.info["error"] = f"startRunning raised {e!r}"
        self._t("start", t0)
        if self.locked:
            try:
                self.dev.unlockForConfiguration()
            except Exception:
                pass
            self.locked = False
        self.info["running_after_start"] = bool(call(self.session, "isRunning"))
        self.info["session_preset_after_start"] = str(call(self.session, "sessionPreset"))
        try:
            act = describe_format(-1, self.dev.activeFormat())
            req = self.info.get("requested_format") or {}
            self.info["active_format_after_start"] = act
            self.info["active_format_matches"] = (act["subtype"], act["w"], act["h"]) == (req.get("subtype"), req.get("w"), req.get("h"))
            self.info["active_min_frame_duration"] = cmtime(self.dev.activeVideoMinFrameDuration())
        except Exception as e:
            self.info["active_format_error"] = repr(e)
        self.info["clocks"] = self.clocks()
        self.rec.session_clock = self.info["clocks"].pop("_sync", None)
        return "error" not in self.info

    def clocks(self) -> dict:
        CM, CFEqual = FW["CM"], FW["CFEqual"]
        out: dict[str, Any] = {}
        sync = call(self.session, "synchronizationClock")
        out["sync_api"] = "synchronizationClock"
        if sync is None or isinstance(sync, str):
            sync = call(self.session, "masterClock")
            out["sync_api"] = "masterClock"
        if isinstance(sync, str):
            out["sync_error"], sync = sync, None
        out["_sync"] = sync
        out["sync_is_none"] = sync is None
        if sync is not None:
            try:
                out["sync_is_host_clock"] = bool(CFEqual(sync, FW["HOST"])) if CFEqual else None
                out["sync_minus_host_ns"] = cmtime_ns(CM.CMClockGetTime(sync)) - host_ns()
            except Exception as e:
                out["sync_error"] = repr(e)
        try:
            ports = [p for p in (self.input.ports() or []) if str(call(p, "mediaType")) == str(FW["AVF"].AVMediaTypeVideo)]
            pc = call(ports[0], "clock") if ports else None
            if pc is not None and not isinstance(pc, str):
                out["port_clock_is_host_clock"] = bool(CFEqual(pc, FW["HOST"])) if CFEqual else None
                out["port_minus_host_ns_start"] = cmtime_ns(CM.CMClockGetTime(pc)) - host_ns()
                try:
                    out["port_rate_vs_host"] = float(CM.CMSyncGetRelativeRate(pc, FW["HOST"]))
                except Exception as e:
                    out["port_rate_error"] = repr(e)
                self._port_clock = pc
            else:
                out["port_clock"] = None if pc is None else pc
        except Exception as e:
            out["port_clock_error"] = repr(e)
        return out

    def port_clock_end(self) -> dict:
        pc = getattr(self, "_port_clock", None)
        if pc is None:
            return {}
        CM = FW["CM"]
        try:
            return {"port_minus_host_ns_end": cmtime_ns(CM.CMClockGetTime(pc)) - host_ns(),
                    "port_rate_vs_host_end": float(CM.CMSyncGetRelativeRate(pc, FW["HOST"]))}
        except Exception as e:
            return {"port_clock_end_error": repr(e)}

    def stop(self) -> None:
        self.stage = "stop"
        if self.session is None:
            return
        t0 = time.perf_counter()
        try:
            self.info.update(self.port_clock_end())
            self.session.stopRunning()
        except Exception as e:
            self.info["stop_error"] = repr(e)
        self._t("stop", t0)

    def teardown(self) -> None:
        self.stage = "teardown"
        if self.locked:
            try:
                self.dev.unlockForConfiguration()
            except Exception:
                pass
        try:
            if self.output is not None:
                self.output.setSampleBufferDelegate_queue_(None, None)
            if self.session is not None:
                for o in list(self.session.outputs() or []):
                    self.session.removeOutput_(o)
                for i in list(self.session.inputs() or []):
                    self.session.removeInput_(i)
        except Exception as e:
            self.info["teardown_error"] = repr(e)
        if self.obs is not None:
            unobserve(self.obs)
        self.session = self.output = self.input = self.obs = None


# ============================================================================================ ep0 + schedule
class Scheduler:
    """Runs --schedule actions relative to the first frame on a worker thread (ep0 calls can block)."""

    def __init__(self, events: list[dict], dev: Any, ep0_args: dict | None, probe_ctx: dict):
        self.events, self.dev, self.ep0_args, self.probe_ctx = events, dev, ep0_args, probe_ctx
        self.done: list[dict] = []
        self.ep0 = None
        self.ep0_info = None
        self._lock = threading.Lock()

    def ensure_ep0(self):
        if self.ep0 is None and self.ep0_args:
            import mac_ep0
            a = self.ep0_args
            self.ep0 = mac_ep0.Ep0Session(int(a["location"], 0) if isinstance(a["location"], str) else a["location"],
                                          a.get("vid"), a.get("pid"), a.get("backend", "iokit-intf"),
                                          a.get("vc_if"), a.get("entities"), a.get("timeout_ms", 500),
                                          allow_seize=bool(a.get("allow_seize")))
            self.ep0_info = self.ep0.setup()
        return self.ep0

    def run_one(self, ev: dict) -> dict:
        rec = dict(ev)
        rec["host_ns_before"] = host_ns()
        try:
            if ev["kind"] == "ep0":
                s = self.ensure_ep0()
                if s is None or not (self.ep0_info or {}).get("ok"):
                    rec["result"] = {"ok": False, "error": "ep0 not available", "setup": self.ep0_info}
                else:
                    rec["result"] = s.controls().set_cur(ev["name"], int(ev["value"], 0))
            elif ev["kind"] == "ep0get":
                s = self.ensure_ep0()
                rec["result"] = s.controls().get_cur(ev["name"]) if s is not None and (self.ep0_info or {}).get("ok") \
                    else {"ok": False, "error": "ep0 not available"}
            elif ev["kind"] == "avf":
                rec["result"] = set_avf_mode(self.dev, ev["name"], ev["value"])
            elif ev["kind"] == "probe":
                rec["result"] = run_probe(ev["name"], self.probe_ctx, self)
            else:
                rec["result"] = {"ok": True, "note": "mark"}
        except Exception as e:
            rec["result"] = {"ok": False, "error": repr(e)}
        rec["host_ns_after"] = host_ns()
        with self._lock:
            self.done.append(rec)
        return rec

    def run(self, t_first_host: int, stop: threading.Event) -> None:
        for ev in self.events:
            target = t_first_host + int(ev["t_ms"] * 1e6)
            while not stop.is_set():
                now = host_ns() or 0
                if now >= target:
                    break
                time.sleep(min(0.01, (target - now) / 1e9))
            if stop.is_set():
                return
            self.run_one(ev)


def set_avf_mode(dev: Any, which: str, value: str) -> dict:
    tables = {"exposure": ("setExposureMode_", "exposureMode", "isExposureModeSupported_", EXPOSURE_MODES),
              "focus": ("setFocusMode_", "focusMode", "isFocusModeSupported_", FOCUS_MODES),
              "wb": ("setWhiteBalanceMode_", "whiteBalanceMode", "isWhiteBalanceModeSupported_", WB_MODES)}
    if which not in tables:
        return {"ok": False, "error": f"unknown avf control {which}"}
    setter, getter, supp, names = tables[which]
    inv = {v: k for k, v in names.items()}
    aliases = {"auto": names.get(2), "continuous": names.get(2), "once": names.get(1), "locked": "locked"}
    mode = inv.get(aliases.get(value, value)) if not str(value).isdigit() else int(value)
    if mode is None:
        return {"ok": False, "error": f"unknown mode {value}"}
    out = {"control": which, "mode": mode, "mode_name": names.get(mode), "before": call(dev, getter)}
    sup = call(dev, supp, args=(mode,))
    out["supported"] = sup if isinstance(sup, str) else bool(sup)
    if sup is not True and not (isinstance(sup, (int, bool)) and sup):
        out["ok"] = False
        return out
    ok, err = dev.lockForConfiguration_(None)
    if not ok:
        return {**out, "ok": False, "error": nserror(err)}
    try:
        getattr(dev, setter)(mode)
        out["ok"] = True
    except Exception as e:
        out.update(ok=False, error=repr(e))
    finally:
        dev.unlockForConfiguration()
    out["readback"] = call(dev, getter)
    out["readback_matches"] = out["readback"] == mode
    return out


def run_probe(name: str, ctx: dict, sched: Scheduler | None = None) -> dict:
    if name == "ioreg_alt":
        import mac_ioreg
        loc = ctx.get("location")
        if loc is None:
            return {"ok": False, "error": "no location"}
        return {"ok": True, **mac_ioreg.read_interface_alts(int(loc, 0) if isinstance(loc, str) else loc)}
    if name in ("ep0_getif", "ep0_commit", "ep0_stream_state"):
        if sched is None or sched.ensure_ep0() is None or not (sched.ep0_info or {}).get("ok"):
            return {"ok": False, "error": "ep0 not available (needs --ep0)"}
        return {"ok": True, "streams": sched.ep0.stream_state(ctx.get("vs_ifs") or [])}
    return {"ok": False, "error": f"unknown probe {name}"}


# ============================================================================================ commands
def cmd_list(a) -> dict:
    out: dict[str, Any] = {"ok": True, "runs": []}
    for k in range(max(1, a.repeat)):
        t0 = time.perf_counter()
        devs, err = discover()
        ms = round((time.perf_counter() - t0) * 1000, 3)
        out["runs"].append({"i": k, "elapsed_ms": ms, "error": err,
                            "devices": [describe_device(i, d) for i, d in enumerate(devs)]})
    t0 = time.perf_counter()
    legacy, lerr = legacy_devices()
    out["legacy"] = {"elapsed_ms": round((time.perf_counter() - t0) * 1000, 3), "error": lerr,
                     "devices": [describe_device(i, d) for i, d in enumerate(legacy)]}
    out["devices"] = out["runs"][0]["devices"] if out["runs"] else []
    out["authorization"] = AUTH.get(int(FW["AVF"].AVCaptureDevice.authorizationStatusForMediaType_(FW["AVF"].AVMediaTypeVideo)))
    return out


def cmd_formats(a) -> dict:
    t_find = time.perf_counter()
    m_start = childutil.mach_ns()
    dev = find_device(a.device)
    if dev is None:
        return {"ok": False, "error": f"device {a.device!r} not found", "exit_code": childutil.EXIT_NOT_FOUND}
    find_ms = round((time.perf_counter() - t_find) * 1000, 3)
    t0 = time.perf_counter()
    d = describe_device(0, dev, formats=True)
    out = {"ok": True, "device": d, "find_ms": find_ms, "list_ms": round((time.perf_counter() - t0) * 1000, 3),
           "list_start_mach_ns": m_start, "list_end_mach_ns": childutil.mach_ns(), "session_created": False}
    if a.hold_ms:
        # keep `dev` referenced for the hold; nothing else is called on it (no lock, no session)
        out["hold"] = childutil.hold(a.hold_ms, a.hold_marker, a.release_file, a.hold_cap_ms,
                                     idle=lambda sec: pump(sec), info={"cmd": "formats"})
        out["in_use_by_other_app_after_hold"] = call(dev, "isInUseByAnotherApplication")
    return out


def avf_flags(dev: Any) -> dict:
    out: dict[str, Any] = {}
    for key, supp, names in (("exposure", "isExposureModeSupported_", EXPOSURE_MODES),
                             ("focus", "isFocusModeSupported_", FOCUS_MODES),
                             ("wb", "isWhiteBalanceModeSupported_", WB_MODES)):
        out[f"{key}_modes_supported"] = {n: (lambda v: v if isinstance(v, str) else bool(v))(call(dev, supp, args=(m,)))
                                         for m, n in names.items()}
    for getter in ("exposureMode", "focusMode", "whiteBalanceMode", "isExposurePointOfInterestSupported",
                   "isFocusPointOfInterestSupported", "isAdjustingExposure", "isAdjustingFocus",
                   "isAdjustingWhiteBalance", "hasFlash", "hasTorch", "isLockingFocusWithCustomLensPositionSupported",
                   "isLockingWhiteBalanceWithCustomDeviceGainsSupported", "exposureDuration", "ISO", "lensPosition",
                   "deviceWhiteBalanceGains", "minExposureTargetBias", "maxExposureTargetBias",
                   "isVideoHDREnabled", "automaticallyAdjustsVideoHDREnabled"):
        v = call(dev, getter)
        if v is not None:
            out[getter] = js(v) if not isinstance(v, str) else v
    return out


def cmd_ctrl_avf(a) -> dict:
    dev = find_device(a.device)
    if dev is None:
        return {"ok": False, "error": f"device {a.device!r} not found", "exit_code": childutil.EXIT_NOT_FOUND}
    out = {"ok": True, "device": describe_device(0, dev), "flags": avf_flags(dev)}
    if a.set_modes:
        # restore path (M-CTRL-EFFECT finally): 'exposure=2,wb=2,focus=2' -> lock, set, unlock, read back
        sets = []
        for part in a.set_modes.split(","):
            which, _, val = part.strip().partition("=")
            if which:
                sets.append(set_avf_mode(dev, which.strip(), val.strip()))
        out["set_modes"] = sets
        out["ok"] = all(x.get("ok") for x in sets) if sets else True
        out["flags_after"] = avf_flags(dev)
    if a.exercise:
        ex = []
        for which, getter, names, key in (("exposure", "exposureMode", EXPOSURE_MODES, "exposure_modes_supported"),
                                          ("focus", "focusMode", FOCUS_MODES, "focus_modes_supported"),
                                          ("wb", "whiteBalanceMode", WB_MODES, "wb_modes_supported")):
            orig = call(dev, getter)
            for m, n in names.items():
                if out["flags"][key].get(n) is True:
                    ex.append(set_avf_mode(dev, which, str(m)))
            if isinstance(orig, int):
                r = set_avf_mode(dev, which, str(orig))
                r["restore"] = True
                ex.append(r)
        out["exercise"] = ex
    return out


def cmd_tcc(a) -> dict:
    AVF = FW["AVF"]
    st = int(AVF.AVCaptureDevice.authorizationStatusForMediaType_(AVF.AVMediaTypeVideo))
    out: dict[str, Any] = {"ok": True, "video": AUTH.get(st, st)}
    try:
        sa = int(AVF.AVCaptureDevice.authorizationStatusForMediaType_(AVF.AVMediaTypeAudio))
        out["audio"] = AUTH.get(sa, sa)
    except Exception:
        pass
    if a.request and st == 0:
        done = threading.Event()
        res: dict = {}

        def handler(granted):
            res["granted"] = bool(granted)
            done.set()

        AVF.AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVF.AVMediaTypeVideo, handler)
        pump(30.0, done)
        out["request_result"] = res.get("granted", "no answer within 30 s")
        st = int(AVF.AVCaptureDevice.authorizationStatusForMediaType_(AVF.AVMediaTypeVideo))
        out["video_after"] = AUTH.get(st, st)
    out["responsible_app_hint"] = {k: os.environ.get(k) for k in ("TERM_PROGRAM", "__CFBundleIdentifier",
                                                                  "SSH_CONNECTION") if os.environ.get(k)}
    return out


FX_INSTANCE = ("isCenterStageActive", "isPortraitEffectActive", "isStudioLightActive", "isBackgroundReplacementActive",
               "reactionEffectsInProgress", "canPerformReactionEffects", "availableReactionTypes",
               "isCenterStageEnabled")
FX_CLASS = ("isCenterStageEnabled", "centerStageControlMode", "isPortraitEffectEnabled", "isStudioLightEnabled",
            "reactionEffectsEnabled", "reactionEffectGesturesEnabled", "isBackgroundReplacementEnabled",
            "preferredMicrophoneMode", "activeMicrophoneMode")


def fx_flags(dev: Any) -> dict:
    out = {}
    for n in FX_INSTANCE:
        v = call(dev, n)
        if v is not None:
            out[n] = js(v) if not isinstance(v, str) else v
    return out


def cmd_fx(a) -> dict:
    AVF = FW["AVF"]
    devs = [find_device(a.device)] if a.device else discover()[0]
    out: dict[str, Any] = {"ok": True, "class_properties": {}, "devices": [],
                           "edge_light": "not exposed by any AVCaptureDevice property (macOS 26.2+); the operator "
                                         "must confirm it is off"}
    for n in FX_CLASS:
        v = call(AVF.AVCaptureDevice, n)
        if v is not None:
            out["class_properties"][n] = js(v) if not isinstance(v, str) else v
    for d in devs:
        if d is None:
            continue
        rec = {"device": describe_device(0, d), "flags_idle": fx_flags(d),
               "format_support": [{k: v for k, v in describe_format(i, f).items()
                                   if k.startswith("is") or k.startswith("reaction") or k in ("subtype", "w", "h")}
                                  for i, f in enumerate(d.formats() or [])]}
        if a.stream_seconds > 0:
            r = Recorder(None, None, keep_rows=False, jpeg_check="none")
            st = Stream(d, None, None, "nil", r)
            samples = []
            try:
                if st.build() and st.start():
                    end = time.monotonic() + a.stream_seconds
                    while time.monotonic() < end:
                        pump(0.5)
                        samples.append({"t_s": round(a.stream_seconds - (end - time.monotonic()), 2), **fx_flags(d)})
            finally:
                st.stop()
                st.teardown()
                r.close()
            rec["flags_streaming"] = samples
            rec["frames_while_sampling"] = r.count
        out["devices"].append(rec)
    return out


def _capture_summary(rec: Recorder, st: Stream, t_wall: float, cpu0: float, extra: dict) -> dict:
    rows = rec.rows
    n = len(rows)
    blocks = [r for r in rows if r.get("kind") == "block"]
    # every block buffer that was checked (soi is a bool once check_jpeg ran); validity fractions use this set as
    # the denominator so corrupt frames without SOI count as invalid
    jp = [r for r in blocks if r.get("soi") is not None]
    jp_soi = [r for r in jp if r.get("soi") is True]
    req = (st.info.get("requested_format") or {})

    def frac(key, pred=lambda v: v is True, subset=None):
        s = subset if subset is not None else jp
        vals = [r.get(key) for r in s if r.get(key) is not None]
        return (sum(1 for v in vals if pred(v)) / len(vals)) if vals else None

    hs = [r["host_ns"] for r in rows if r.get("host_ns")]
    fps = (len(hs) - 1) / ((hs[-1] - hs[0]) / 1e9) if len(hs) > 2 and hs[-1] > hs[0] else None
    sha = sorted({r.get("header_sha1") for r in jp if r.get("header_sha1")})
    out = {
        "frames": n, "fps_measured": round(fps, 3) if fps else None,
        "sample_kinds": dict(rec.kinds), "sample_subtypes": dict(rec.subtypes), "cv_pixel_formats": dict(rec.cv_formats),
        # JPEG bytes = every sample is a checked block buffer and most of them start with SOI (a block buffer of
        # uncompressed pixels, e.g. 2vuy, is NOT JPEG even though it was checked)
        "is_jpeg": (bool(jp) and len(jp) == n and len(jp_soi) >= 0.5 * len(jp)) if n else None,
        "soi_fraction": (len(jp_soi) / len(jp)) if jp else None,
        "jpeg": {"n_checked": len(jp), "n_soi": len(jp_soi),
                 "soi_eoi_fraction": frac("eoi", subset=jp_soi) if jp_soi else None,
                 "strict_valid_fraction": frac("strict_ok"), "lenient_valid_fraction": frac("lenient_ok"),
                 "sof_match_fraction": (sum(1 for r in jp if (r.get("sof0_w"), r.get("sof0_h")) == (req.get("w"), req.get("h")))
                                        / len(jp)) if jp else None,
                 "header_sha1_set": sha[:8], "n_header_sha1": len(sha),
                 "extra_bytes_before_eoi_max": max((r.get("extra_bytes_before_eoi") or 0 for r in jp), default=None),
                 "bytes_median": sorted(r["bytes"] for r in jp if r.get("bytes"))[len(jp) // 2] if jp else None},
        "dropped_callbacks": len(rec.dropped), "dropped_reasons": sorted({str(d.get("reason")) for d in rec.dropped})[:10],
        "first_frame_ms": round((rec.t_first_host - st.info["host_ns_start_call"]) / 1e6, 3)
        if rec.t_first_host and st.info.get("host_ns_start_call") else None,
        "cmio_seq_present": any(r.get("cmio_seq") for r in rows),
        "delegate_errors": rec.errors, "copy": {k: v for k, v in rec.stats.items()},
        "cpu": {"process_cpu_s": round(cpu_now() - cpu0, 4), "wall_s": round(t_wall, 3),
                "pct_one_core": round(100 * (cpu_now() - cpu0) / t_wall, 2) if t_wall > 0 else None},
        "notifications": st.notes, "runtime_errors": [x for x in st.notes if "RuntimeError" in x["name"]],
        "interruptions": [x for x in st.notes if "Interrupt" in x["name"]],
        "disconnected": any("Disconnected" in x["name"] for x in st.notes),
        "stream": st.info,
    }
    out.update(extra)
    return out


def _ep0_args(a) -> dict | None:
    if not a.ep0_location:
        return None
    ent = None
    if a.ep0_entities:
        try:
            d = json.loads(Path(a.ep0_entities).read_text(encoding="utf-8"))
            ent = d.get("entities", d)
        except Exception:
            ent = None
    return {"location": a.ep0_location, "vid": a.vid, "pid": a.pid, "backend": a.ep0_backend,
            "vc_if": a.vc_if, "entities": ent, "timeout_ms": 500, "allow_seize": a.ep0_allow_seize}


def cmd_capture(a, state: dict) -> dict:
    dev = find_device(a.device)
    if dev is None:
        return {"ok": False, "error": f"device {a.device!r} not found", "exit_code": childutil.EXIT_NOT_FOUND}
    out_dir = Path(a.out_dir) if a.out_dir else None
    raw_dir = Path(a.raw_dir) if a.raw_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    rec = Recorder(out_dir, raw_dir, a.save, a.jpeg_check, a.metrics_every)
    st = Stream(dev, a.format_index, a.fps, a.variant, rec)
    state["stream"] = st.info
    events = childutil.parse_schedule(a.schedule)
    sched = Scheduler(events, dev, _ep0_args(a), {"location": a.ep0_location or a.location,
                                                  "vs_ifs": [int(x) for x in (a.vs_if or "").split(",") if x.strip()]})
    before = []
    if a.controls_before:
        for name, val in childutil.parse_kv_list(a.controls_before):
            before.append(sched.run_one({"t_ms": -1, "kind": "ep0", "name": name, "value": str(val)}))
    state["in_progress"] = "build"
    cpu0 = cpu_now()
    t_start = time.monotonic()
    stop = threading.Event()
    readback_after: list[dict] = []
    try:
        if not st.build():
            return {"ok": False, "stage_failed": st.stage, "error": st.info.get("error"), "stream": st.info,
                    "frames": 0, "notifications": st.notes,
                    "runtime_errors": [x for x in st.notes if "RuntimeError" in x["name"]],
                    "controls_before": before, "ep0_setup": sched.ep0_info,
                    "error_class": "open", "exit_code": childutil.EXIT_CAMERA}
        state["in_progress"] = "startRunning"
        st.start()
        state["in_progress"] = "first frame"
        got = pump(a.first_frame_timeout_s, rec.first)
        childutil.touch(a.ready_file, {"mach_ns": childutil.mach_ns(), "first_frame": bool(got)})
        thr = None
        if got and events:
            thr = threading.Thread(target=sched.run, args=(rec.t_first_host, stop), daemon=True)
            thr.start()
        state["in_progress"] = "streaming"
        if got:
            if a.frames:
                end = time.monotonic() + a.seconds_cap
                while rec.count < a.frames and time.monotonic() < end:
                    pump(0.05)
            elif a.stop_file:
                end = time.monotonic() + a.seconds
                while time.monotonic() < end and not os.path.exists(a.stop_file):
                    pump(0.1)
                state["stopped_by"] = "stop_file" if os.path.exists(a.stop_file) else "seconds"
            else:
                pump(a.seconds)
        if before and got:
            for b in before:
                if b.get("kind") == "ep0":
                    readback_after.append(sched.run_one({"t_ms": -1, "kind": "ep0get", "name": b["name"]}))
        stop.set()
        if thr is not None:
            thr.join(timeout=5.0)
    finally:
        state["in_progress"] = "stopRunning"
        st.stop()
        st.teardown()
        rec.close()
        if sched.ep0 is not None:
            sched.ep0.close()
    t_wall = time.monotonic() - t_start
    summ = _capture_summary(rec, st, t_wall, cpu0, {
        "schedule_events": sched.done, "controls_before": before, "controls_readback_after_start":
            readback_after, "ep0_setup": sched.ep0_info})
    summ["ok"] = rec.count > 0 and (not a.frames or rec.count >= a.frames)
    if state.get("stopped_by"):
        summ["stopped_by"] = state["stopped_by"]
    if not rec.count:
        summ["stage_failed"] = "first_frame"
        summ["error_class"] = "zero_frames"
        summ["exit_code"] = childutil.EXIT_CAMERA
    if out_dir:
        summ["frames_jsonl"] = str(out_dir / "frames.jsonl")
        (out_dir / "summary.json").write_text(json.dumps(summ, default=str, indent=1), encoding="utf-8")
    if raw_dir and rec.saved_bytes:
        summ["raw_frames"] = str(raw_dir / "frames.mjpeg")
    return summ


def cmd_cycle(a, state: dict) -> dict:
    out_dir = Path(a.out_dir) if a.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    jsonl = (out_dir / "cycles.jsonl").open("a", encoding="utf-8") if out_dir else None
    objc = FW["objc"]
    cur: dict[str, Any] = {}
    state["cycles_done"] = rows
    state["current_cycle"] = cur

    def write(row):
        rows.append(row)
        if jsonl:
            jsonl.write(json.dumps(row, default=str) + "\n")
            jsonl.flush()

    # per-cycle watchdog: a hung cycle is written as a row, then the child exits 5 (runner records it)
    def hang():
        row = dict(cur)
        row.update(ok=False, stage_failed="timeout", timed_out=True, hung=True,
                   note=f"cycle exceeded {a.cycle_timeout_s:.0f} s in stage {cur.get('stage')}")
        write(row)
        if jsonl:
            jsonl.close()
        childutil.emit({"ok": False, "timed_out": True, "error_class": "timeout", "cycles": len(rows),
                        "rows_tail": rows[-3:], "exit_code": childutil.EXIT_TIMEOUT})
        os._exit(childutil.EXIT_TIMEOUT)

    for i in range(a.cycles):
        use_alt = a.alt_format_index is not None and i % 2 == 1
        fi = a.alt_format_index if use_alt else a.format_index
        fps = a.alt_fps if use_alt and a.alt_fps else a.fps
        cur.clear()
        cur.update(i=i, mode={"format_index": fi, "fps": fps}, stage="find")
        timer = threading.Timer(a.cycle_timeout_s, hang)
        timer.daemon = True
        timer.start()
        row: dict[str, Any] = {"i": i, "mode": {"format_index": fi, "fps": fps}, "utc": time.time()}
        with objc.autorelease_pool():
            t0 = time.perf_counter()
            dev = find_device(a.device)
            row["find_ms"] = round((time.perf_counter() - t0) * 1000, 3)
            if dev is None:
                row.update(ok=False, stage_failed="find", error="device not found")
            else:
                rec = Recorder(None, None, keep_rows=False, jpeg_check="none")
                st = Stream(dev, fi, fps, a.variant, rec, queue_name=f"skellycam.cycle.{i}")
                try:
                    cur["stage"] = "build"
                    h_open = host_ns()
                    built = st.build()
                    row.update({f"{k}_ms": v for k, v in st.info["timings_ms"].items()})
                    if not built:
                        row.update(ok=False, stage_failed=st.stage, error=st.info.get("error"))
                    else:
                        cur["stage"] = "start"
                        st.start()
                        row["start_ms"] = st.info["timings_ms"].get("start")
                        cur["stage"] = "first_frame"
                        got = pump(a.timeout_ms / 1000.0, rec.first)
                        row["first_frame_ms"] = round((rec.t_first_host - st.info["host_ns_start_call"]) / 1e6, 3) \
                            if got and rec.t_first_host else None
                        # same meaning as wincam: first_frame_ms is start -> first sample; open_to_first_frame_ms
                        # adds the device input + session configuration time
                        row["open_to_first_frame_ms"] = (round((rec.t_first_host - h_open) / 1e6, 3)
                                                         if got and rec.t_first_host and h_open else None)
                        if got:
                            cur["stage"] = "frames"
                            end = time.monotonic() + max(2.0, a.frames / max(1.0, fps or 30.0) * 3)
                            while rec.count < a.frames + 1 and time.monotonic() < end:
                                pump(0.02)
                        row["frames"] = rec.count
                        row["active_format_matches"] = st.info.get("active_format_matches")
                        row["sample_subtypes"] = dict(rec.subtypes)
                        ok = bool(got) and rec.count >= a.frames
                        row["ok"] = ok
                        if not got:
                            row["stage_failed"] = "first_frame"
                        elif not ok:
                            row["stage_failed"] = "frames"
                finally:
                    cur["stage"] = "stop"
                    st.stop()
                    row["close_ms"] = st.info["timings_ms"].get("stop")
                    st.teardown()
                    rec.close()
                errs = [x for x in st.notes if "RuntimeError" in x["name"]]
                if errs:
                    row["runtime_errors"] = errs
                    e = errs[0].get("error") or {}
                    row["code"] = e.get("code")
                    row["code_hex"] = e.get("code_hex")
                    row["iokit_codes"] = e.get("iokit_codes")
                if isinstance(row.get("error"), dict):
                    row["code"] = row["error"].get("code")
        timer.cancel()
        write(row)
        if a.gap_ms:
            pump(a.gap_ms / 1000.0)
    if jsonl:
        jsonl.close()
    n_ok = sum(1 for r in rows if r.get("ok"))
    return {"ok": n_ok == len(rows), "cycles": len(rows), "n_ok": n_ok, "rows": rows if not out_dir else rows[-5:],
            "cycles_jsonl": str(out_dir / "cycles.jsonl") if out_dir else None}


def cmd_multi(a, state: dict) -> dict:
    specs = []
    for part in a.devices.split(","):
        if not part.strip():
            continue
        uid, _, rest = part.partition("@")
        fi, _, fps = rest.partition("/")
        specs.append({"uid": uid.strip(), "format_index": int(fi) if fi else None, "fps": float(fps) if fps else None})
    streams = []
    for s in specs:
        dev = find_device(s["uid"])
        rec = Recorder(None, None, keep_rows=True, jpeg_check="none")
        st = Stream(dev, s["format_index"], s["fps"], a.variant, rec, queue_name=f"skellycam.multi.{len(streams)}") \
            if dev is not None else None
        streams.append({"spec": s, "dev": dev, "rec": rec, "st": st, "built": False})
    for x in streams:
        if x["st"] is not None:
            x["built"] = x["st"].build()
    try:
        for x in streams:
            if x["built"]:
                x["st"].start()
                if a.stagger_ms:
                    pump(a.stagger_ms / 1000.0)
        pump(a.seconds)
    finally:
        for x in streams:
            if x["st"] is not None:
                x["st"].stop()
                x["st"].teardown()
            x["rec"].close()
    cams = []
    for x in streams:
        st, rec = x["st"], x["rec"]
        hs = [r["host_ns"] for r in rec.rows if r.get("host_ns")]
        cams.append({"unique_id": x["spec"]["uid"], "found": x["dev"] is not None, "built": x["built"],
                     "frames": rec.count, "first_frame_ms": round((rec.t_first_host - st.info["host_ns_start_call"]) / 1e6, 3)
                     if st and rec.t_first_host and st.info.get("host_ns_start_call") else None,
                     "fps": round((len(hs) - 1) / ((hs[-1] - hs[0]) / 1e9), 3) if len(hs) > 2 and hs[-1] > hs[0] else None,
                     "runtime_errors": [n for n in (st.notes if st else []) if "RuntimeError" in n["name"]],
                     "notifications": st.notes if st else [], "error": (st.info.get("error") if st else "not found"),
                     "stage": st.stage if st else "find"})
    return {"ok": all(c["frames"] > 0 for c in cams), "cameras": cams}


# ============================================================================================ main
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="AVFoundation worker for the macOS suite (see module docstring)")
    ap.add_argument("cmd", choices=["list", "formats", "ctrl-avf", "fx", "tcc", "capture", "cycle", "multi"])
    ap.add_argument("--device", default=None, help="uniqueID (preferred), index or name substring")
    ap.add_argument("--devices", default="", help="multi: uid@format_index/fps,uid2@...")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--exercise", action="store_true")
    ap.add_argument("--set-modes", default="", help="ctrl-avf: exposure=N,wb=N,focus=N (mode numbers or names)")
    ap.add_argument("--request", action="store_true")
    ap.add_argument("--stream-seconds", type=float, default=0.0)
    ap.add_argument("--format-index", type=int, default=None)
    ap.add_argument("--fps", type=float, default=None)
    ap.add_argument("--variant", choices=VARIANTS, default="nil")
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--frames", type=int, default=0, help="capture: stop after N frames (cap --seconds-cap)")
    ap.add_argument("--seconds-cap", type=float, default=30.0)
    ap.add_argument("--first-frame-timeout-s", type=float, default=5.0)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--raw-dir", default=None)
    ap.add_argument("--save", default="none", help="none | all | every:K | first:N (raw dir)")
    ap.add_argument("--jpeg-check", default="all", help="all | every:K | none (strict decode)")
    ap.add_argument("--metrics-every", type=int, default=0)
    ap.add_argument("--schedule", default="")
    ap.add_argument("--controls-before", default="")
    ap.add_argument("--ep0-location", default=None)
    ap.add_argument("--ep0-backend", default="iokit-intf")
    ap.add_argument("--ep0-allow-seize", action="store_true",
                    help="required with --ep0-backend libusb (WARNING: libusb on darwin seizes USB devices)")
    ap.add_argument("--ep0-entities", default=None)
    ap.add_argument("--location", default=None, help="locationID for ioreg probes")
    ap.add_argument("--vid")
    ap.add_argument("--pid")
    ap.add_argument("--vc-if", type=int, default=None)
    ap.add_argument("--vs-if", default="")
    ap.add_argument("--cycles", type=int, default=10)
    ap.add_argument("--timeout-ms", type=int, default=5000, help="cycle: first-frame timeout")
    ap.add_argument("--cycle-timeout-s", type=float, default=30.0)
    ap.add_argument("--alt-format-index", type=int, default=None)
    ap.add_argument("--alt-fps", type=float, default=None)
    ap.add_argument("--gap-ms", type=float, default=0.0)
    ap.add_argument("--stagger-ms", type=float, default=0.0)
    ap.add_argument("--deadline-s", type=float, default=120.0)
    ap.add_argument("--hold-ms", type=float, default=0.0, help="formats: keep the device object N ms after listing")
    ap.add_argument("--hold-marker", default=None, help="formats: file written when the hold starts")
    ap.add_argument("--release-file", default=None, help="formats: the hold ends once this file exists")
    ap.add_argument("--hold-cap-ms", type=float, default=None, help="formats: hard end of the hold (hold + 60 s)")
    ap.add_argument("--ready-file", default=None, help="capture: written at the first frame (or first-frame timeout)")
    ap.add_argument("--stop-file", default=None, help="capture: stop streaming once this file exists")
    return ap


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    state: dict[str, Any] = {"cmd": a.cmd, "device": a.device, "in_progress": "load frameworks",
                             "host_ns_child_start": childutil.mach_ns()}
    if sys.platform != "darwin":
        childutil.emit({**state, "ok": False, "error": "macOS only (AVFoundation)", "exit_code": childutil.EXIT_USAGE})
        return childutil.EXIT_USAGE
    dl = childutil.Deadline(a.deadline_s, lambda: {k: v for k, v in state.items() if k != "current_cycle"}
                            | {"current_cycle": dict(state.get("current_cycle") or {})}).start()
    t0 = time.time()
    try:
        load_frameworks()
        state["in_progress"] = a.cmd
        fn = {"list": lambda: cmd_list(a), "formats": lambda: cmd_formats(a), "ctrl-avf": lambda: cmd_ctrl_avf(a),
              "fx": lambda: cmd_fx(a), "tcc": lambda: cmd_tcc(a), "capture": lambda: cmd_capture(a, state),
              "cycle": lambda: cmd_cycle(a, state), "multi": lambda: cmd_multi(a, state)}[a.cmd]
        res = fn()
    except Exception as e:
        import traceback
        res = {"ok": False, "error": f"{type(e).__name__}: {e}", "error_class": "exception",
               "traceback": traceback.format_exc()[-2000:], "exit_code": childutil.EXIT_CAMERA}
    dl.cancel()
    res = dict(res)
    res.setdefault("exit_code", childutil.EXIT_OK if res.get("ok") else childutil.EXIT_CAMERA)
    res.update(cmd=a.cmd, elapsed_s=round(time.time() - t0, 3), host_ns_child_start=state["host_ns_child_start"],
               frameworks={k: v for k, v in FW.items() if k.endswith("_error")},
               pyobjc=getattr(FW.get("objc"), "__version__", None))
    childutil.emit(res)
    return int(res["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
