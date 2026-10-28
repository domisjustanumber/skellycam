# /// script
# requires-python = ">=3.10"
# dependencies = ["pyobjc-core>=10", "pyobjc-framework-AVFoundation>=10", "pyobjc-framework-CoreMedia>=10", "pyobjc-framework-libdispatch>=10"]
# ///
"""macOS: open N UVC cameras at once through AVFoundation and record which start / fail / degrade.
Goal 3 (USB bandwidth) DRAFT -- unverified until run. The macOS analogue of bandwidth/mf_multi_open.cpp on Windows.

WHAT TO RUN (from the repo root, as your normal user; the first run triggers the macOS camera-permission prompt
for your terminal app -- allow it, then re-run):
  uv run --script research/usb_cameras/bandwidth/macos/avf_multi_open.py --list
  uv run --script research/usb_cameras/bandwidth/macos/avf_multi_open.py --size 1280x720 --fps 30 --seconds 8 --ramp
      [--match <substring of device uniqueID or name> ...]
HARDWARE: >=2 UVC cameras behind ONE USB 2.0 hub (otherwise nothing shares bandwidth).
WHAT IT RECORDS (results/macos/<hostname>/bw_avf_multi/<utc>.json): each device's uniqueID (on macOS this encodes the
USB locationID + VID + PID, used to tell which cameras share a hub), every format, then for k = 1..N cameras
streaming simultaneously: per camera the chosen format, frames delivered, fps, dropped-frame callbacks, and any
AVCaptureSessionRuntimeError (NSError code/description). AVFoundation exposes no alt-setting/bandwidth control, so
this shows the OS default behaviour only. Compare with bandwidth/libuvc_forced_alt/run_forced_alt.sh (needs sudo on macOS).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import socket
import sys
import time
from pathlib import Path

if sys.platform != "darwin":
    sys.exit("macOS only")

import objc  # noqa: E402
import AVFoundation as AVF  # noqa: E402
import CoreMedia  # noqa: E402
from Foundation import NSObject, NSRunLoop, NSDate, NSNotificationCenter  # noqa: E402
import dispatch  # noqa: E402  (pyobjc-framework-libdispatch)


def devices():
    types = [AVF.AVCaptureDeviceTypeExternal] if hasattr(AVF, "AVCaptureDeviceTypeExternal") else [AVF.AVCaptureDeviceTypeExternalUnknown]
    ds = AVF.AVCaptureDeviceDiscoverySession.discoverySessionWithDeviceTypes_mediaType_position_(
        types, AVF.AVMediaTypeVideo, AVF.AVCaptureDevicePositionUnspecified)
    return list(ds.devices())


def fmt_info(f) -> dict:
    desc = f.formatDescription()
    dims = CoreMedia.CMVideoFormatDescriptionGetDimensions(desc)
    sub = CoreMedia.CMFormatDescriptionGetMediaSubType(desc)
    fourcc = sub.to_bytes(4, "big").decode("ascii", "replace") if isinstance(sub, int) else str(sub)
    rates = [(r.minFrameRate(), r.maxFrameRate()) for r in f.videoSupportedFrameRateRanges()]
    return {"fourcc": fourcc, "width": dims.width, "height": dims.height, "fps_ranges": rates}


class Counter(NSObject):
    def init(self):
        self = objc.super(Counter, self).init()
        self.frames = 0
        self.dropped = 0
        self.t_first = None
        self.t_last = None
        return self

    def captureOutput_didOutputSampleBuffer_fromConnection_(self, out, sb, conn):
        t = time.monotonic()
        if self.t_first is None:
            self.t_first = t
        else:
            self.frames += 1
        self.t_last = t

    def captureOutput_didDropSampleBuffer_fromConnection_(self, out, sb, conn):
        self.dropped += 1


class ErrWatcher(NSObject):
    def init(self):
        self = objc.super(ErrWatcher, self).init()
        self.errors = []
        return self

    def onError_(self, note):
        err = note.userInfo().get(AVF.AVCaptureSessionErrorKey) if note.userInfo() else None
        self.errors.append({"t": time.monotonic(), "code": int(err.code()) if err else None,
                            "domain": str(err.domain()) if err else None, "desc": str(err.localizedDescription()) if err else None})


def open_stream(dev, w: int, h: int, fps: float):
    rec = {"uniqueID": str(dev.uniqueID()), "name": str(dev.localizedName()), "error": None}
    best = None
    for f in dev.formats():
        i = fmt_info(f)
        if i["width"] == w and i["height"] == h and any(lo - 0.01 <= fps <= hi + 0.01 for lo, hi in i["fps_ranges"]):
            best = (f, i)
            break
    if best is None:
        rec["error"] = "no matching format"
        return None, rec
    sess = AVF.AVCaptureSession.alloc().init()
    inp, err = AVF.AVCaptureDeviceInput.deviceInputWithDevice_error_(dev, None)
    if inp is None:
        rec["error"] = f"deviceInput: {err}"
        return None, rec
    sess.beginConfiguration()
    sess.addInput_(inp)
    out = AVF.AVCaptureVideoDataOutput.alloc().init()
    out.setAlwaysDiscardsLateVideoFrames_(True)
    cnt = Counter.alloc().init()
    q = dispatch.dispatch_queue_create(b"skellycam.bw", None)
    out.setSampleBufferDelegate_queue_(cnt, q)
    sess.addOutput_(out)
    sess.commitConfiguration()
    ok, err = dev.lockForConfiguration_(None)
    if ok:
        dev.setActiveFormat_(best[0])
        dur = CoreMedia.CMTimeMake(1000, int(round(fps * 1000)))
        dev.setActiveVideoMinFrameDuration_(dur)
        dev.setActiveVideoMaxFrameDuration_(dur)
        dev.unlockForConfiguration()
    rec["format"] = best[1]
    w_ = ErrWatcher.alloc().init()
    NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(w_, "onError:", AVF.AVCaptureSessionRuntimeErrorNotification, sess)
    return (sess, cnt, w_), rec


def run_k(devs, w, h, fps, seconds):
    handles, recs = [], []
    for d in devs:
        hnd, rec = open_stream(d, w, h, fps)
        recs.append(rec)
        handles.append(hnd)
    for hnd in handles:
        if hnd:
            hnd[0].startRunning()
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(1.0))  # stagger: deterministic order
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))
    for hnd, rec in zip(handles, recs):
        if not hnd:
            continue
        sess, cnt, wat = hnd
        rec["running"] = bool(sess.isRunning())
        sess.stopRunning()
        rec["frames"] = cnt.frames
        rec["dropped_callbacks"] = cnt.dropped
        rec["fps"] = round(cnt.frames / (cnt.t_last - cnt.t_first), 3) if cnt.t_first and cnt.t_last and cnt.t_last > cnt.t_first else 0.0
        rec["runtime_errors"] = wat.errors
    return recs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--seconds", type=float, default=8)
    ap.add_argument("--ramp", action="store_true", help="run k=1..N cameras (default: only all N)")
    ap.add_argument("--match", action="append")
    a = ap.parse_args()
    devs = devices()
    if a.match:
        devs = [d for d in devs if any(m.lower() in (str(d.uniqueID()) + str(d.localizedName())).lower() for m in a.match)]
    doc = {"test": "bw_avf_multi", "platform": "macos", "hostname": socket.gethostname(),
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(), "command": " ".join(sys.argv),
           "environment": {"os": platform.platform(), "mac_ver": platform.mac_ver()[0], "python": platform.python_version()},
           "cameras": [{"uniqueID": str(d.uniqueID()), "name": str(d.localizedName()), "modelID": str(d.modelID()),
                        "formats": [fmt_info(f) for f in d.formats()]} for d in devs]}
    for c in doc["cameras"]:
        print(c["uniqueID"], c["name"], c["modelID"], len(c["formats"]), "formats")
    if not a.list:
        w, h = (int(x) for x in a.size.split("x"))
        doc["runs"] = []
        for k in (range(1, len(devs) + 1) if a.ramp else [len(devs)]):
            recs = run_k(devs[:k], w, h, a.fps, a.seconds)
            doc["runs"].append({"k": k, "cameras": recs})
            print(f"k={k}: " + ", ".join(f"{r['name']} fps={r.get('fps')} err={r.get('error') or r.get('runtime_errors')}" for r in recs))
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(__file__).resolve().parents[2] / "results" / "macos" / socket.gethostname() / "bw_avf_multi" / f"{'list' if a.list else 'run'}_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, default=str))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
