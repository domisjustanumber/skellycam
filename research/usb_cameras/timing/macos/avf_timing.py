# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyobjc-core==10.3.1",
#   "pyobjc-framework-AVFoundation==10.3.1",
#   "pyobjc-framework-CoreMedia==10.3.1",
#   "pyobjc-framework-Quartz==10.3.1",
#   "pyobjc-framework-libdispatch==10.3.1",
# ]
# ///
"""macOS: per-frame AVFoundation timestamps vs host clock, in the shared per-frame schema.

DRAFT -- written on Windows, NOT YET RUN. Please run it and send back results/macos/<hostname>/timing/.

What it does
  * opens an AVCaptureDevice (UVC webcam) with AVCaptureVideoDataOutput, picks the format closest to WxH@fps,
    optionally locks exposure (AVCaptureExposureModeLocked; custom duration needs exposureModeCustom which most UVC
    cameras on macOS do not support -- recorded in session.json),
  * per frame logs host_arrival_ns = CMClockGetTime(CMClockGetHostTimeClock()) in the delegate callback,
    os_timestamp_ns = CMSampleBufferGetPresentationTimeStamp converted to host-clock ns (the capture session's
    synchronizationClock is the host time clock; this is checked and recorded), the decode/output timestamps and
    duration, and every sample-buffer attachment key present (CoreMediaIO may attach e.g. host-time / sequence
    attachments; the UVC PTS/SCR are not exposed by AVFoundation as far as documented -- this test checks),
  * no MJPEG passthrough: AVCaptureVideoDataOutput delivers decoded pixel buffers (MJPEG native extraction on macOS
    needs libusb/libuvc, see the libusb phase).
Run:
    uv run --script research/usb_cameras/timing/macos/avf_timing.py --list
    uv run --script research/usb_cameras/timing/macos/avf_timing.py --device-index 0 --size 1280x720 --fps 30 --seconds 30 [--lock-exposure]
    then: uv run --script research/usb_cameras/tools/analyze_frames.py results/macos/<host>/timing/<run>/*.frames.jsonl
Needs: camera permission for the terminal app (System Settings > Privacy & Security > Camera); first run may prompt.
Writes results/macos/<hostname>/timing/<utc>/<key>.frames.jsonl + <key>.session.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import socket
import sys
import threading
import time
from pathlib import Path

import AVFoundation as AVF
import CoreMedia as CM
import libdispatch
import objc
from Foundation import NSObject, NSRunLoop, NSDate

HOST_CLOCK = CM.CMClockGetHostTimeClock()


def cmtime_ns(t) -> int | None:
    # CMTime is (value, timescale, flags, epoch); flags & 1 == valid
    try:
        value, timescale, flags = t.value, t.timescale, t.flags
    except AttributeError:
        value, timescale, flags = t[0], t[1], t[2]
    if not (flags & 1) or timescale == 0:
        return None
    return int(value * 1_000_000_000 // timescale)


def host_now_ns() -> int:
    return cmtime_ns(CM.CMClockGetTime(HOST_CLOCK))


class Delegate(NSObject):
    def initWithWriter_key_(self, writer, key):
        self = objc.super(Delegate, self).init()
        self.writer, self.key, self.seq, self.attr_keys = writer, key, 0, {}
        return self

    def captureOutput_didOutputSampleBuffer_fromConnection_(self, output, sbuf, conn):
        t_arr = host_now_ns()
        pts = cmtime_ns(CM.CMSampleBufferGetPresentationTimeStamp(sbuf))
        dts = cmtime_ns(CM.CMSampleBufferGetDecodeTimeStamp(sbuf))
        dur = cmtime_ns(CM.CMSampleBufferGetDuration(sbuf))
        att = CM.CMCopyDictionaryOfAttachments(None, sbuf, 1)  # kCMAttachmentMode_ShouldPropagate
        attrs = {}
        if att:
            for k in att.keys():
                v = att[k]
                try:
                    json.dumps(v); attrs[str(k)] = v
                except TypeError:
                    attrs[str(k)] = str(v)[:200]
                self.attr_keys[str(k)] = self.attr_keys.get(str(k), 0) + 1
        rec = {"camera_key": self.key, "backend": "avfoundation-videodataoutput", "seq": self.seq, "host_arrival_ns": t_arr,
               "os_timestamp_ns": pts, "os_timestamp_source": "CMSampleBuffer presentation timestamp (host time clock)",
               "decode_timestamp_ns": dts, "duration_ns": dur,
               "uvc_pts": None, "uvc_scr_stc": None, "uvc_scr_sof": None, "device_clock_hz": None,
               "payload_bytes": CM.CMSampleBufferGetTotalSampleSize(sbuf), "is_valid_jpeg": None, "attachments": attrs}
        self.writer(rec)
        self.seq += 1

    def captureOutput_didDropSampleBuffer_fromConnection_(self, output, sbuf, conn):
        self.writer({"camera_key": self.key, "dropped": True, "host_arrival_ns": host_now_ns()})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--device-index", type=int, default=0)
    ap.add_argument("--size", default="1280x720"); ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--lock-exposure", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    if sys.platform != "darwin":
        print("this script is for macOS", file=sys.stderr); return 2
    types = [AVF.AVCaptureDeviceTypeExternal] if hasattr(AVF, "AVCaptureDeviceTypeExternal") else [AVF.AVCaptureDeviceTypeExternalUnknown]
    types.append(AVF.AVCaptureDeviceTypeBuiltInWideAngleCamera)
    disc = AVF.AVCaptureDeviceDiscoverySession.discoverySessionWithDeviceTypes_mediaType_position_(types, AVF.AVMediaTypeVideo, 0)
    devs = list(disc.devices())
    if a.list:
        print(json.dumps([{"index": i, "name": d.localizedName(), "uniqueID": d.uniqueID(), "modelID": d.modelID()} for i, d in enumerate(devs)], indent=2))
        return 0
    dev = devs[a.device_index]
    W, H = map(int, a.size.lower().split("x"))
    host = socket.gethostname()
    root = Path(__file__).resolve().parents[2]
    out = Path(a.out) if a.out else root / "results" / "macos" / host / "timing" / dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=True)
    key = f"{dev.modelID()}|{dev.uniqueID()}".replace("/", "_")
    safe = "".join(c if c.isalnum() else "_" for c in key)
    ses = {"test": "avf_timing", "platform": "macos", "hostname": host, "utc_started": dt.datetime.utcnow().isoformat() + "Z",
           "command": " ".join(sys.argv), "environment": {"macos": platform.mac_ver()[0], "python": platform.python_version(), "pyobjc": objc.__version__},
           "device": {"name": dev.localizedName(), "uniqueID": dev.uniqueID(), "modelID": dev.modelID()}}
    # choose format
    best = None
    for f in dev.formats():
        dims = CM.CMVideoFormatDescriptionGetDimensions(f.formatDescription())
        sub = CM.CMFormatDescriptionGetMediaSubType(f.formatDescription())
        for r in f.videoSupportedFrameRateRanges():
            if dims.width == W and dims.height == H and r.minFrameRate() <= a.fps <= r.maxFrameRate():
                best = best or (f, sub)
    ok, err = dev.lockForConfiguration_(None)
    if best:
        dev.setActiveFormat_(best[0])
        ses["format_subtype"] = best[1].to_bytes(4, "big").decode(errors="replace") if isinstance(best[1], int) else str(best[1])
    dur = CM.CMTimeMake(1000, int(a.fps * 1000))
    try:
        dev.setActiveVideoMinFrameDuration_(dur); dev.setActiveVideoMaxFrameDuration_(dur)
    except Exception as e:  # noqa: BLE001
        ses["frame_duration_error"] = str(e)
    if a.lock_exposure:
        ses["exposure_locked_supported"] = bool(dev.isExposureModeSupported_(AVF.AVCaptureExposureModeLocked))
        ses["exposure_custom_supported"] = bool(dev.isExposureModeSupported_(AVF.AVCaptureExposureModeCustom))
        if ses["exposure_locked_supported"]:
            dev.setExposureMode_(AVF.AVCaptureExposureModeLocked)
    session = AVF.AVCaptureSession.alloc().init()
    inp, err = AVF.AVCaptureDeviceInput.deviceInputWithDevice_error_(dev, None)
    session.addInput_(inp)
    outp = AVF.AVCaptureVideoDataOutput.alloc().init()
    outp.setAlwaysDiscardsLateVideoFrames_(False)
    lock = threading.Lock()
    fl = (out / f"{safe}.frames.jsonl").open("w")

    def writer(rec):
        with lock:
            fl.write(json.dumps(rec) + "\n")
    dlg = Delegate.alloc().initWithWriter_key_(writer, key)
    q = libdispatch.dispatch_queue_create(b"avf_timing", None)
    outp.setSampleBufferDelegate_queue_(dlg, q)
    session.addOutput_(outp)
    dev.unlockForConfiguration()
    try:
        clk = session.synchronizationClock()
        ses["session_clock_is_host_clock"] = bool(clk == HOST_CLOCK) if clk is not None else None
    except Exception as e:  # noqa: BLE001
        ses["session_clock_error"] = str(e)
    session.startRunning()
    t_end = time.monotonic() + a.seconds
    while time.monotonic() < t_end:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.2))
    session.stopRunning()
    time.sleep(0.3)
    with lock:
        fl.close()
    ses["frames"] = dlg.seq; ses["attachment_key_counts"] = dlg.attr_keys
    (out / f"{safe}.session.json").write_text(json.dumps(ses, indent=2, default=str))
    print(json.dumps({"out": str(out), "frames": dlg.seq}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
