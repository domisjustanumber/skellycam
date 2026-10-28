# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyobjc-core>=10",
#   "pyobjc-framework-Cocoa>=10",
#   "pyobjc-framework-AVFoundation>=10",
#   "pyobjc-framework-CoreMedia>=10",
#   "pyobjc-framework-Quartz>=10",
#   "pyobjc-framework-libdispatch>=10",
#   "pillow>=10",
#   "simplejpeg>=1.7",
#   "psutil>=5.9",
# ]
# ///
"""UNVERIFIED DRAFT -- written on Windows, never run on macOS. The pyobjc call patterns (especially
CMBlockBufferCopyDataBytes output buffers and CMTime structs) are written from the API docs and pyobjc metadata
conventions and may need small fixes on first run; every fallback that fires is recorded in the output.

Question answered: can AVFoundation's AVCaptureVideoDataOutput hand us the camera's compressed MJPEG bytes
(CMSampleBuffer backed by a CMBlockBuffer, media subtype 'dmb1' / 'jpeg') instead of decoded CVPixelBuffers?

HARDWARE / PERMISSIONS
  macOS 12+ (13+ preferred), Apple silicon or Intel, one or more USB (UVC) cameras. Camera access must be granted to
  the app that launches the script (Terminal, iTerm2, VS Code, ...): System Settings > Privacy & Security > Camera.
  On first run macOS shows the permission prompt (the script asks once and waits up to 30 s); if access was denied,
  enable the terminal app there, QUIT and reopen it, and re-run. Over SSH there is no GUI prompt: run it once from a
  local terminal first. No sudo. Close other apps using the camera (FaceTime, Zoom, Photo Booth, browsers).

WHAT TO RUN (from the repo root)
  uv run --script research/usb_cameras/mjpeg/drafts/macos/avf_mjpeg_probe.py --list            # JSON to stdout
  uv run --script research/usb_cameras/mjpeg/drafts/macos/avf_mjpeg_probe.py --list-tsv
  uv run --script research/usb_cameras/mjpeg/drafts/macos/avf_mjpeg_probe.py --device 0 \
      --size 1280x720 --fps 30 --variant none   [--subtype dmb1] [--format-index N] [--seconds 10] [--warmup 2]
      --variant none  -> videoSettings = nil      --variant empty -> videoSettings = {} (empty dict)
  --device accepts an index into AVCaptureDevice.devicesWithMediaType_(video) order, a uniqueID, or a name substring.
  or run the whole matrix: bash research/usb_cameras/mjpeg/drafts/macos/run_macos_mjpeg.sh

WHAT IT WRITES
  --list:   research/usb_cameras/results/macos/<hostname>/mjpeg_avf_list/devices.json (+ the JSON on stdout)
  capture:  research/usb_cameras/results/macos/<hostname>/mjpeg_avf_videodataoutput/<label>/summary.json,
            frames.jsonl (+ sample_*.jpg with --keep-samples). Default label: <W>x<H>at<fps>_<subtype>_<variant>_<dev>.
            Raw run dir (meta.json, frames.jsonl, frames_0.bin) goes to --run-dir (default: a fresh dir under
            $MJPEG_SCRATCH or $TMPDIR/usb_cameras_mjpeg_scratch). summary.json has the same shape as the Windows
            backends (mjpeg_common.summarize_run). Compressed frames are stored and JPEG-validated; CVPixelBuffer
            frames are NOT copied (payload_bytes = CVPixelBufferGetDataSize) and summary has decoded_by_pipeline=true.
  Exit codes: 0 ok, 1 failure, 3 camera permission not granted, 4 no matching device/format.

PER-FRAME LOG (README schema + extras)
  host_arrival_ns       time.monotonic_ns() at the top of captureOutput:didOutputSampleBuffer:fromConnection:
  host_arrival_mach_ns  mach_absolute_time() * numer/denom (mach_timebase_info), same instant
  os_timestamp_ns       CMSampleBufferGetPresentationTimeStamp converted (CMSyncConvertTime) from the session's
                        synchronizationClock/masterClock to CMClockGetHostTimeClock, in ns, then shifted into the
                        time.monotonic_ns domain using the host-clock-minus-monotonic offset measured at start
                        (meta.backend_details.clock_offsets). Raw PTS value/timescale/flags/epoch are kept too.
  avf_subtype (sample format description media subtype FourCC), has_block_buffer, has_image_buffer,
  cv_pixel_format, hostclock_now_ns (CMClockGetTime(host clock) at arrival).
"""
from __future__ import annotations

import argparse
import ctypes
import json
import re
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))  # drafts/macos -> mjpeg/
import mjpeg_common as mc  # noqa: E402

TEST = "mjpeg_avf_videodataoutput"
BACKEND = "avf-videodataoutput"
COMPRESSED_SUBTYPES = {"dmb1", "jpeg", "mjpa", "mjpb", "avc1", "hvc1"}
JPEG_SUBTYPES = {"dmb1", "jpeg", "mjpa", "mjpb"}

if sys.platform != "darwin":
    raise SystemExit("error: macOS only (AVFoundation via pyobjc)")

import objc  # noqa: E402
import AVFoundation as AVF  # noqa: E402
import CoreMedia as CM  # noqa: E402
from Foundation import NSObject, NSRunLoop, NSDate  # noqa: E402

try:
    import Quartz as CV  # CoreVideo functions (CVPixelBufferGet*) are exposed by pyobjc-framework-Quartz
except ImportError:  # pragma: no cover
    CV = None
try:
    import dispatch  # pyobjc-framework-libdispatch (pyobjc >= 9)
except ImportError:  # pragma: no cover
    import libdispatch as dispatch  # older module name
try:
    from CoreFoundation import CFEqual
except ImportError:  # pragma: no cover
    CFEqual = None


# ---------------------------------------------------------------- clocks
class _TB(ctypes.Structure):
    _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]


_libsys = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
_libsys.mach_absolute_time.restype = ctypes.c_uint64
_libsys.mach_timebase_info.argtypes = [ctypes.POINTER(_TB)]
_TBI = _TB()
_libsys.mach_timebase_info(ctypes.byref(_TBI))


def mach_ns() -> int:
    return _libsys.mach_absolute_time() * _TBI.numer // _TBI.denom


def cmtime(t) -> dict | None:
    if t is None:
        return None
    try:
        return {"value": int(t.value), "timescale": int(t.timescale), "flags": int(t.flags), "epoch": int(t.epoch)}
    except Exception:  # struct may come back as a tuple in some pyobjc versions
        v, ts, fl, ep = t
        return {"value": int(v), "timescale": int(ts), "flags": int(fl), "epoch": int(ep)}


def cmtime_ns(t) -> int | None:
    d = cmtime(t)
    if not d or not (d["flags"] & 1) or d["timescale"] <= 0:  # kCMTimeFlags_Valid
        return None
    return d["value"] * 1_000_000_000 // d["timescale"]


HOST_CLOCK = CM.CMClockGetHostTimeClock()


def clock_offsets(n: int = 9) -> dict:
    """host clock (CMClockGetHostTimeClock) vs time.monotonic_ns vs mach_absolute_time, tightest of n samples."""
    best = None
    for _ in range(n):
        a = time.monotonic_ns()
        h = cmtime_ns(CM.CMClockGetTime(HOST_CLOCK))
        m = mach_ns()
        b = time.monotonic_ns()
        if h is None:
            continue
        if best is None or (b - a) < best["bracket_ns"]:
            best = {"bracket_ns": b - a, "monotonic_mid_ns": (a + b) // 2, "hostclock_ns": h, "mach_ns": m}
    if best:
        best["hostclock_minus_monotonic_ns"] = best["hostclock_ns"] - best["monotonic_mid_ns"]
        best["mach_minus_monotonic_ns"] = best["mach_ns"] - best["monotonic_mid_ns"]
        best["hostclock_minus_mach_ns"] = best["hostclock_ns"] - best["mach_ns"]
    return best or {"error": "CMClockGetTime(host) returned invalid time"}


# ---------------------------------------------------------------- helpers
def fourcc(v) -> str:
    try:
        v = int(v)
    except Exception:
        return str(v)
    s = bytes([(v >> 24) & 255, (v >> 16) & 255, (v >> 8) & 255, v & 255])
    return s.decode("latin-1") if all(32 <= c < 127 for c in s) else f"0x{v:08x}"


def js(o, depth=0):
    """NSDictionary/NSArray/NSNumber/NSString -> JSON-able python."""
    if depth > 6:
        return str(o)
    if o is None or isinstance(o, (bool, int, float)):
        return o
    if isinstance(o, str):
        return str(o)
    if hasattr(o, "keys"):
        return {str(k): js(o[k], depth + 1) for k in o.keys()}
    if isinstance(o, (list, tuple)) or hasattr(o, "count") and hasattr(o, "objectAtIndex_"):
        return [js(x, depth + 1) for x in o]
    try:
        return int(o) if float(o).is_integer() else float(o)
    except Exception:
        return str(o)


def call(obj, name, *args, default=None):
    f = getattr(obj, name, None)
    if f is None:
        return default
    try:
        return f(*args)
    except Exception as e:
        return f"error: {e!r}"


def auth_status() -> int:
    return int(AVF.AVCaptureDevice.authorizationStatusForMediaType_(AVF.AVMediaTypeVideo))


AUTH_NAMES = {0: "notDetermined", 1: "restricted", 2: "denied", 3: "authorized"}


def ensure_camera_permission() -> dict:
    st = auth_status()
    info = {"initial": AUTH_NAMES.get(st, st)}
    if st == 0:
        done = threading.Event()
        res = {}

        def handler(granted):
            res["granted"] = bool(granted)
            done.set()

        AVF.AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVF.AVMediaTypeVideo, handler)
        t_end = time.monotonic() + 30
        while not done.is_set() and time.monotonic() < t_end:
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
        info["request_result"] = res.get("granted", "timeout (no answer within 30 s)")
        st = auth_status()
    info["final"] = AUTH_NAMES.get(st, st)
    if st != 3:
        print(
            f"ERROR: camera access is '{AUTH_NAMES.get(st, st)}' for this process.\n"
            "  Grant it to the app that runs this script (Terminal / iTerm2 / VS Code ...):\n"
            "  System Settings > Privacy & Security > Camera > enable it, then QUIT and reopen that app and re-run.\n"
            "  (Over SSH there is no prompt; run once from a local terminal. 'restricted' = MDM/parental policy.)",
            file=sys.stderr)
        raise SystemExit(3)
    return info


def all_devices() -> list:
    devs = list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeVideo) or [])
    return devs


def discovery_devices() -> list[str] | str:
    names = ["AVCaptureDeviceTypeExternal", "AVCaptureDeviceTypeExternalUnknown", "AVCaptureDeviceTypeBuiltInWideAngleCamera",
             "AVCaptureDeviceTypeContinuityCamera", "AVCaptureDeviceTypeDeskViewCamera"]
    types = [getattr(AVF, n) for n in names if hasattr(AVF, n)]
    try:
        ds = AVF.AVCaptureDeviceDiscoverySession.discoverySessionWithDeviceTypes_mediaType_position_(types, AVF.AVMediaTypeVideo, 0)
        return [str(d.uniqueID()) for d in ds.devices()]
    except Exception as e:
        return f"error: {e!r}"


def describe_format(i: int, f) -> dict:
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
                       "min_frame_duration": cmtime(r.minFrameDuration()), "max_frame_duration": cmtime(r.maxFrameDuration())})
    ext = None
    try:
        e = CM.CMFormatDescriptionGetExtensions(fd)
        ext = {k: v for k, v in (js(e) or {}).items() if k in ("FormatName", "Depth", "FullRangeVideo", "CVPixelAspectRatio", "Version", "RevisionLevel")}
    except Exception as ex:
        ext = f"error: {ex!r}"
    return {"index": i, "media_type": str(f.mediaType()), "subtype": fourcc(sub), "subtype_int": int(sub), "width": w, "height": h,
            "frame_rate_ranges": ranges, "extensions": ext, "description": str(f)[:300]}


def describe_device(i: int, d) -> dict:
    return {"index": i, "uniqueID": str(d.uniqueID()), "modelID": str(call(d, "modelID")), "localizedName": str(d.localizedName()),
            "manufacturer": str(call(d, "manufacturer")), "transportType": fourcc(call(d, "transportType", default=0)),
            "deviceType": str(call(d, "deviceType")), "connected": bool(call(d, "isConnected", default=True)),
            "formats": [describe_format(j, f) for j, f in enumerate(d.formats() or [])]}


def pick_device(spec: str, devs: list):
    if re.fullmatch(r"\d+", spec) and int(spec) < len(devs):
        return int(spec), devs[int(spec)]
    for i, d in enumerate(devs):
        if str(d.uniqueID()) == spec:
            return i, d
    for i, d in enumerate(devs):
        if spec.lower() in str(d.localizedName()).lower():
            return i, d
    return None, None


def pick_format(dev, w, h, fps, subtype: str | None, index: int | None):
    fmts = list(dev.formats() or [])
    descs = [describe_format(i, f) for i, f in enumerate(fmts)]
    if index is not None:
        return (fmts[index], descs[index], descs) if 0 <= index < len(fmts) else (None, None, descs)
    cands = [d for d in descs if d["width"] == w and d["height"] == h
             and any(r["min_fps"] - 0.01 <= fps <= r["max_fps"] + 0.01 for r in d["frame_rate_ranges"])]
    if subtype:
        cands = [d for d in cands if d["subtype"] == subtype]
    pref = {"dmb1": 0, "jpeg": 1}
    cands.sort(key=lambda d: (pref.get(d["subtype"], 2 if d["subtype"] in COMPRESSED_SUBTYPES else 3), d["index"]))
    if not cands:
        return None, None, descs
    return fmts[cands[0]["index"]], cands[0], descs


def frame_duration(fdesc: dict, fps: float):
    for r in fdesc["frame_rate_ranges"]:
        if abs(r["max_fps"] - fps) < 0.01 and r["min_frame_duration"]:
            m = r["min_frame_duration"]
            return CM.CMTimeMake(m["value"], m["timescale"]), "exact range minFrameDuration"
        if abs(r["min_fps"] - fps) < 0.01 and r["max_frame_duration"]:
            m = r["max_frame_duration"]
            return CM.CMTimeMake(m["value"], m["timescale"]), "exact range maxFrameDuration"
    return CM.CMTimeMake(1_000_000, int(round(fps * 1_000_000))), "CMTimeMake(1e6, fps*1e6)"


COPY_METHOD: dict = {"used": None, "failures": []}


def block_bytes(bb) -> bytes | None:
    n = int(CM.CMBlockBufferGetDataLength(bb))
    attempts = []
    # 1) pyobjc output-buffer convention: pass None, get (status, bytes) back
    try:
        r = CM.CMBlockBufferCopyDataBytes(bb, 0, n, None)
        if isinstance(r, tuple) and len(r) == 2 and r[0] == 0 and r[1] is not None:
            COPY_METHOD["used"] = COPY_METHOD["used"] or "CMBlockBufferCopyDataBytes(bb,0,n,None)->(st,bytes)"
            return bytes(r[1])[:n]
        attempts.append(f"copy(None) -> {type(r).__name__} {str(r)[:80]}")
    except Exception as e:
        attempts.append(f"copy(None): {e!r}")
    # 2) caller-supplied writable buffer
    try:
        buf = bytearray(n)
        r = CM.CMBlockBufferCopyDataBytes(bb, 0, n, buf)
        st = r[0] if isinstance(r, tuple) else r
        if st == 0:
            if isinstance(r, tuple) and r[1] is not None and not isinstance(r[1], bytearray):
                buf = bytes(r[1])
            COPY_METHOD["used"] = COPY_METHOD["used"] or "CMBlockBufferCopyDataBytes(bb,0,n,bytearray)"
            return bytes(buf)
        attempts.append(f"copy(bytearray) status {st}")
    except Exception as e:
        attempts.append(f"copy(bytearray): {e!r}")
    # 3) contiguous data pointer
    try:
        r = CM.CMBlockBufferGetDataPointer(bb, 0, None, None, None)
        st, len_at, total, ptr = r
        if st == 0 and ptr is not None and len_at >= n:
            COPY_METHOD["used"] = COPY_METHOD["used"] or "CMBlockBufferGetDataPointer(...).as_buffer"
            return bytes(ptr.as_buffer(n))
        attempts.append(f"getdatapointer st={st} len_at={len_at} total={total}")
    except Exception as e:
        attempts.append(f"getdatapointer: {e!r}")
    if len(COPY_METHOD["failures"]) < 5:
        COPY_METHOD["failures"].append(attempts)
    return None


# ---------------------------------------------------------------- delegate
try:
    _PROTO = [objc.protocolNamed("AVCaptureVideoDataOutputSampleBufferDelegate")]
except Exception:  # pragma: no cover
    _PROTO = []


class Delegate(NSObject, protocols=_PROTO):
    def initWithWriter_(self, writer):
        self = objc.super(Delegate, self).init()
        if self is None:
            return None
        self.writer = writer
        self.lock = threading.Lock()
        self.seq = 0
        self.dropped = []
        self.session_clock = None
        self.key = ""
        self.errors = []
        self.subtypes = {}
        self.kinds = {"block": 0, "image": 0, "neither": 0}
        return self

    def captureOutput_didOutputSampleBuffer_fromConnection_(self, output, sbuf, conn):
        t_mono = time.monotonic_ns()
        t_mach = mach_ns()
        try:
            host_now = cmtime_ns(CM.CMClockGetTime(HOST_CLOCK))
            fd = CM.CMSampleBufferGetFormatDescription(sbuf)
            sub = fourcc(CM.CMFormatDescriptionGetMediaSubType(fd)) if fd is not None else None
            bb = CM.CMSampleBufferGetDataBuffer(sbuf)
            ib = CM.CMSampleBufferGetImageBuffer(sbuf)
            pts = CM.CMSampleBufferGetPresentationTimeStamp(sbuf)
            pts_ns = cmtime_ns(pts)
            pts_host_ns, conv = None, None
            if self.session_clock is not None and pts_ns is not None:
                try:
                    pts_host_ns = cmtime_ns(CM.CMSyncConvertTime(pts, self.session_clock, HOST_CLOCK))
                    conv = "CMSyncConvertTime(session clock -> host time clock)"
                except Exception as e:
                    conv = f"CMSyncConvertTime failed ({e!r}); using raw PTS as host time"
            if pts_host_ns is None and pts_ns is not None:
                pts_host_ns, conv = pts_ns, conv or "raw PTS (session clock not yet known; assumed host time clock)"
            payload, nbytes, cvfmt, cvwh = b"", 0, None, None
            if bb is not None:
                self.kinds["block"] += 1
                b = block_bytes(bb)
                if b is not None:
                    payload, nbytes = b, len(b)
                else:
                    nbytes = int(CM.CMBlockBufferGetDataLength(bb))
            elif ib is not None:
                self.kinds["image"] += 1
                if CV is not None:
                    cvfmt = fourcc(CV.CVPixelBufferGetPixelFormatType(ib))
                    cvwh = [int(CV.CVPixelBufferGetWidth(ib)), int(CV.CVPixelBufferGetHeight(ib))]
                    nbytes = int(CV.CVPixelBufferGetDataSize(ib))
            else:
                self.kinds["neither"] += 1
            self.subtypes[sub] = self.subtypes.get(sub, 0) + 1
            off = META_OFFSETS.get("hostclock_minus_monotonic_ns")
            row = {"camera_key": self.key, "backend": BACKEND, "seq": self.seq, "host_arrival_ns": t_mono,
                   "os_timestamp_ns": (pts_host_ns - off) if (pts_host_ns is not None and off is not None) else None,
                   "os_timestamp_source": f"CMSampleBuffer PTS; {conv}; shifted to time.monotonic_ns domain by start offset",
                   "uvc_pts": None, "uvc_scr_stc": None, "uvc_scr_sof": None, "device_clock_hz": None,
                   "payload_bytes": nbytes, "is_valid_jpeg": None,
                   "host_arrival_mach_ns": t_mach, "hostclock_now_ns": host_now, "pts_raw": cmtime(pts), "pts_host_ns": pts_host_ns,
                   "dts_raw": cmtime(CM.CMSampleBufferGetDecodeTimeStamp(sbuf)), "duration_raw": cmtime(CM.CMSampleBufferGetDuration(sbuf)),
                   "avf_subtype": sub, "has_block_buffer": bb is not None, "has_image_buffer": ib is not None,
                   "payload_copied": len(payload) > 0, "cv_pixel_format": cvfmt, "cv_wh": cvwh}
            with self.lock:
                self.writer.add(0, row, payload)
                self.seq += 1
        except Exception as e:
            if len(self.errors) < 20:
                self.errors.append(f"delegate: {e!r}")

    def captureOutput_didDropSampleBuffer_fromConnection_(self, output, sbuf, conn):
        reason = None
        try:
            r = CM.CMGetAttachment(sbuf, CM.kCMSampleBufferAttachmentKey_DroppedFrameReason, None)
            reason = str(r[0] if isinstance(r, tuple) else r)
        except Exception as e:
            reason = f"? {e!r}"
        if len(self.dropped) < 10000:
            self.dropped.append({"host_arrival_ns": time.monotonic_ns(), "reason": reason})


META_OFFSETS: dict = {}


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--list-tsv", action="store_true", help="index, uniqueID, name, compressed subtypes, has 1280x720@30 (any subtype)")
    ap.add_argument("--device", default="0")
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--subtype", default=None, help="force a format media subtype, e.g. dmb1, jpeg, 420v, yuvs, 2vuy")
    ap.add_argument("--format-index", type=int, default=None)
    ap.add_argument("--variant", choices=["none", "empty"], default="none", help="videoSettings = nil (none) or {} (empty)")
    ap.add_argument("--discard-late", action="store_true", help="alwaysDiscardsLateVideoFrames=True (default False: count every frame)")
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--warmup", type=float, default=2)
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--keep-samples", type=int, default=0)
    ap.add_argument("--root", default=None, help="results root (default results/<platform>/<host>); the runners pass a fresh mjpeg_run_<UTC stamp> dir")
    a = ap.parse_args()

    perm = ensure_camera_permission()
    devs = all_devices()
    if a.list or a.list_tsv:
        desc = [describe_device(i, d) for i, d in enumerate(devs)]
        if a.list_tsv:
            for d in desc:
                comp = sorted({f["subtype"] for f in d["formats"] if f["subtype"] in COMPRESSED_SUBTYPES})
                has720 = any(f["width"] == 1280 and f["height"] == 720 and any(r["min_fps"] - .01 <= 30 <= r["max_fps"] + .01 for r in f["frame_rate_ranges"]) for f in d["formats"])
                print("\t".join([str(d["index"]), d["uniqueID"], d["localizedName"].replace("\t", " "), ",".join(comp) or "-", "1" if has720 else "0"]))
            return 0
        doc = {"test": "mjpeg_avf_list", "platform": mc.plat(), "hostname": mc.HOST, "utc_started": mc.utc_now(), "command": sys.argv,
               "environment": mc.environment(("pyobjc-framework-AVFoundation", "pyobjc-framework-CoreMedia")), "camera_permission": perm,
               "device_order_note": "index = AVCaptureDevice.devicesWithMediaType_(video) order. FFmpeg's avfoundation indices may differ "
                                    "(newer FFmpeg uses AVCaptureDeviceDiscoverySession); compare names with `ffmpeg -f avfoundation -list_devices true -i \"\"`.",
               "discovery_session_order": discovery_devices(), "devices": desc}
        out = mc.results_dir("mjpeg_avf_list", root=a.root)
        (out / "devices.json").write_text(json.dumps(doc, indent=1))
        print(json.dumps(doc, indent=1))
        print(f"wrote {out / 'devices.json'}", file=sys.stderr)
        return 0

    W, H = map(int, a.size.lower().split("x"))
    di, dev = pick_device(a.device, devs)
    if dev is None:
        print(f"ERROR: no video device matches {a.device!r}; have: {[str(d.localizedName()) for d in devs]}", file=sys.stderr)
        return 4
    fmt, fdesc, all_fmts = pick_format(dev, W, H, a.fps, a.subtype, a.format_index)
    if fmt is None:
        print(f"ERROR: {dev.localizedName()} has no format {W}x{H}@{a.fps:g}" + (f" subtype {a.subtype}" if a.subtype else "")
              + f"; formats: {[(f['subtype'], f['width'], f['height'], [r['max_fps'] for r in f['frame_rate_ranges']]) for f in all_fmts]}", file=sys.stderr)
        return 4
    devslug = re.sub(r"[^A-Za-z0-9]+", "", str(dev.localizedName()))[:24] or f"dev{di}"
    run_dir = Path(a.run_dir) if a.run_dir else Path(__import__("tempfile").mkdtemp(prefix="avf_", dir=mc.scratch_root()))
    writer = mc.RunWriter(run_dir)
    errors: list[str] = []
    started = mc.utc_now()
    META_OFFSETS.update(clock_offsets())

    delegate = Delegate.alloc().initWithWriter_(writer)
    delegate.key = str(dev.uniqueID())
    session = AVF.AVCaptureSession.alloc().init()
    inp, err = AVF.AVCaptureDeviceInput.deviceInputWithDevice_error_(dev, None)
    if inp is None:
        print(f"ERROR: AVCaptureDeviceInput failed: {err}", file=sys.stderr)
        return 1
    session.beginConfiguration()
    if not session.canAddInput_(inp):
        print("ERROR: session cannot add input (camera in use?)", file=sys.stderr)
        return 1
    session.addInput_(inp)
    out = AVF.AVCaptureVideoDataOutput.alloc().init()
    settings_value = None if a.variant == "none" else {}
    out.setVideoSettings_(settings_value)
    out.setAlwaysDiscardsLateVideoFrames_(bool(a.discard_late))
    queue = dispatch.dispatch_queue_create(b"org.freemocap.avf_mjpeg_probe", None)
    out.setSampleBufferDelegate_queue_(delegate, queue)
    if not session.canAddOutput_(out):
        print("ERROR: session cannot add AVCaptureVideoDataOutput", file=sys.stderr)
        return 1
    session.addOutput_(out)
    ok, lerr = dev.lockForConfiguration_(None)
    if not ok:
        print(f"ERROR: lockForConfiguration failed: {lerr}", file=sys.stderr)
        return 1
    dur, dur_how = frame_duration(fdesc, a.fps)
    try:
        dev.setActiveFormat_(fmt)
        dev.setActiveVideoMinFrameDuration_(dur)
        dev.setActiveVideoMaxFrameDuration_(dur)
    except Exception as e:  # NSInvalidArgumentException if duration not supported
        errors.append(f"set format/duration: {e!r}")
    session.commitConfiguration()
    output_info = {"videoSettings_set": "nil" if settings_value is None else "{} (empty NSDictionary)",
                   "videoSettings_readback": js(out.videoSettings()),
                   "availableVideoCVPixelFormatTypes": [fourcc(x) for x in (out.availableVideoCVPixelFormatTypes() or [])],
                   "availableVideoCodecTypes": [str(x) for x in (call(out, "availableVideoCodecTypes") or [])],
                   "alwaysDiscardsLateVideoFrames": bool(out.alwaysDiscardsLateVideoFrames())}
    session.startRunning()  # started while still holding the lock -> activeFormat is not reset by the session preset
    dev.unlockForConfiguration()
    sync = call(session, "synchronizationClock") or call(session, "masterClock")
    if isinstance(sync, str):
        sync = None
    delegate.session_clock = sync
    sync_info = {"api": "synchronizationClock" if hasattr(session, "synchronizationClock") else "masterClock",
                 "is_none": sync is None}
    if sync is not None:
        try:
            sync_info["CFEqual_to_host_time_clock"] = bool(CFEqual(sync, HOST_CLOCK)) if CFEqual else None
            a0 = time.monotonic_ns()
            sync_info["session_clock_now_ns"] = cmtime_ns(CM.CMClockGetTime(sync)) if hasattr(CM, "CMClockGetTime") else None
            sync_info["host_clock_now_ns"] = cmtime_ns(CM.CMClockGetTime(HOST_CLOCK))
            sync_info["sampled_at_monotonic_ns"] = a0
            if sync_info["session_clock_now_ns"] is not None and sync_info["host_clock_now_ns"] is not None:
                sync_info["session_minus_host_ns"] = sync_info["session_clock_now_ns"] - sync_info["host_clock_now_ns"]
        except Exception as e:
            sync_info["error"] = repr(e)
    active = describe_format(-1, dev.activeFormat())

    def pump(seconds):
        t_end = time.monotonic() + seconds
        while time.monotonic() < t_end:
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))

    pump(a.warmup)
    cpu = mc.CpuWindow()
    cpu.start()
    c0 = time.clock_gettime_ns(time.CLOCK_PROCESS_CPUTIME_ID)
    w0 = time.monotonic_ns()
    pump(a.seconds)
    w1 = time.monotonic_ns()
    c1 = time.clock_gettime_ns(time.CLOCK_PROCESS_CPUTIME_ID)
    cpu_res = cpu.stop()
    wall = (w1 - w0) / 1e9
    cpu_res.update({"method": "CLOCK_PROCESS_CPUTIME_ID (precise) + psutil cpu_times", "process_cpu_s_clock": (c1 - c0) / 1e9,
                    "process_cpu_pct_of_one_core": 100.0 * (c1 - c0) / 1e9 / wall if wall else None})
    session.stopRunning()
    out.setSampleBufferDelegate_queue_(None, None)  # no more callbacks touch writer after this
    pump(0.3)
    with delegate.lock:
        rows = list(writer.rows)
    errors += delegate.errors
    win = [r for r in rows if w0 <= r["host_arrival_ns"] <= w1]
    n_block = sum(1 for r in rows if r["has_block_buffer"])
    n_img = sum(1 for r in rows if r["has_image_buffer"])
    jpeg_sub = active["subtype"] in JPEG_SUBTYPES
    payload_is_jpeg = bool(rows) and n_block == len(rows) and all(r["payload_copied"] for r in rows) \
        and all(r["avf_subtype"] in JPEG_SUBTYPES for r in rows)
    if not rows:
        decoded, evidence = None, "no frames delivered"
    elif n_block == len(rows):
        decoded, evidence = False, "every CMSampleBuffer carried a CMBlockBuffer (compressed payload); no CVPixelBuffer was produced"
    elif n_img and active["subtype"] in COMPRESSED_SUBTYPES:
        decoded, evidence = True, (f"active device format subtype is '{active['subtype']}' (compressed) but samples arrived as CVPixelBuffers "
                                   f"({sorted({r['cv_pixel_format'] for r in rows if r['cv_pixel_format']})}): AVFoundation decoded them")
    else:
        decoded, evidence = None, (f"samples arrived as CVPixelBuffers and the device format subtype is '{active['subtype']}' (uncompressed as "
                                   "presented by AVFoundation). Whether the USB wire format was MJPEG (decoded inside CoreMediaIO) cannot "
                                   "be told from here; compare with the camera's UVC descriptors")
    cam = {"idx": 0, "name": str(dev.localizedName()), "camera_key": str(dev.uniqueID()), "avf_index": di, "uniqueID": str(dev.uniqueID()),
           "modelID": str(call(dev, "modelID")), "transportType": fourcc(call(dev, "transportType", default=0)),
           "chosen_format": fdesc, "active_format_after_start": active, "frame_duration_set": cmtime(dur), "frame_duration_how": dur_how,
           "output": output_info, "sample_kinds": dict(delegate.kinds), "sample_subtypes": dict(delegate.subtypes),
           "dropped_frames": len(delegate.dropped), "dropped_reasons": sorted({d["reason"] for d in delegate.dropped}),
           "frames": len(rows)}
    meta = {"backend": BACKEND, "utc_started": started, "command": sys.argv,
            "environment": mc.environment(("pyobjc-framework-AVFoundation", "pyobjc-framework-CoreMedia")),
            "requested": {"subtype": fdesc["subtype"], "width": W, "height": H, "fps": a.fps, "variant": a.variant},
            "decoded_by_pipeline": decoded, "decode_evidence": evidence,
            "delivered_codecs": sorted(k for k in delegate.subtypes if k),
            "silent_format_fallback": (jpeg_sub and n_img > 0) if rows else None,
            "payload_is_jpeg": payload_is_jpeg,
            "cpu": cpu_res, "cameras": [cam], "errors": errors,
            "backend_details": {"camera_permission": perm, "clock_offsets": dict(META_OFFSETS), "session_clock": sync_info,
                                "mach_timebase": [_TBI.numer, _TBI.denom], "block_copy_method": COPY_METHOD,
                                "frames_in_window": len(win), "all_formats": all_fmts,
                                "dropped_first": delegate.dropped[:50]},
            "notes": "UNVERIFIED draft backend (drafted on Windows). os_timestamp_ns = PTS converted to the host time clock, minus "
                     "(host clock - time.monotonic_ns) measured at start."}
    with delegate.lock:
        writer.flush(meta, w0, w1)
    label = a.label or f"{W}x{H}at{a.fps:g}_{fdesc['subtype']}_{a.variant}_{devslug}"
    outdir = mc.results_dir(TEST, label, root=a.root)
    s = mc.summarize_run(run_dir, outdir, test=TEST, command=sys.argv, keep_samples=a.keep_samples, payload_is_jpeg=payload_is_jpeg)
    print(mc.brief(s))
    print(json.dumps({"variant": a.variant, "format_subtype": fdesc["subtype"], "sample_kinds": cam["sample_kinds"],
                      "sample_subtypes": cam["sample_subtypes"], "decoded_by_pipeline": decoded,
                      "availableVideoCodecTypes": output_info["availableVideoCodecTypes"], "errors": errors}))
    print("wrote", outdir / "summary.json")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
