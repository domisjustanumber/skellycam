# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyobjc-core>=10.3; sys_platform == 'darwin'",
#   "pyobjc-framework-AVFoundation>=10.3; sys_platform == 'darwin'",
#   "pyobjc-framework-CoreMedia>=10.3; sys_platform == 'darwin'",
#   "pyobjc-framework-libdispatch>=10.3; sys_platform == 'darwin'",
# ]
# ///
"""macOS DRAFT -- UNVERIFIED until the user runs it.  AVFoundation via pyobjc: can we get the camera's own
MJPEG bytes (no decode) and what timestamps come with each frame?

WHY: Apple documents for AVCaptureVideoDataOutput.videoSettings: "To receive samples in their device-native
format, set this value to an empty dictionary" (developer.apple.com/documentation/avfoundation/
avcapturevideodataoutput/videosettings, read 2026-10-25).  UVC MJPEG camera formats usually show up in
AVFoundation with media subtype 'dmb1' (kCMVideoCodecType_JPEG_OpenDML).  Whether an empty videoSettings dict
then delivers *compressed* 'dmb1' CMSampleBuffers for UVC cameras is NOT documented -- this test checks it.

WHAT TO RUN (repo root, normal user, no sudo):
    uv run --script research/usb_cameras/prior_art/drafts/macos/avf_native_mjpeg_probe.py --seconds 5
  options: --width 1280 --height 720 --fps 30 --only <substring of name/uniqueID>
HARDWARE: one or more UVC webcams that offer MJPEG.  PERMISSIONS: the terminal app needs Camera access
(System Settings > Privacy & Security > Camera); the first run may pop up a prompt -- accept and rerun.

WHAT IT WRITES: results/macos/<hostname>/prior_art_avf_native/result.json  (+ frames_<n>.jsonl, sample_<n>.jpg)
  per device: uniqueID, modelID, localizedName, manufacturer, list of formats with media subtype fourcc,
  the format chosen, the media subtype of delivered sample buffers, whether the bytes are a JPEG (SOI/EOI),
  sizes, and per-frame: PTS (CMSampleBuffer presentation time, in host-time-clock seconds), host arrival
  (CMClockGetTime(CMClockGetHostTimeClock())) and the output-timestamp delta.
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

ROOT = Path(__file__).resolve().parents[3]


def fourcc(v: int) -> str:
    s = "".join(chr((v >> (8 * (3 - i))) & 0xFF) for i in range(4))
    return s if s.isprintable() else hex(v)


def main() -> int:
    if sys.platform != "darwin":
        print("macOS only")
        return 2
    import AVFoundation as AVF
    import CoreMedia as CM
    import libdispatch
    import objc
    from Foundation import NSDate, NSObject, NSRunLoop

    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=5)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    host = socket.gethostname().split(".")[0]
    out = ROOT / "results" / "macos" / host / "prior_art_avf_native"
    out.mkdir(parents=True, exist_ok=True)

    auth = AVF.AVCaptureDevice.authorizationStatusForMediaType_(AVF.AVMediaTypeVideo)
    if auth == 0:  # not determined -> ask
        ev = threading.Event()
        AVF.AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVF.AVMediaTypeVideo, lambda ok: ev.set())
        t0 = time.time()
        while not ev.is_set() and time.time() - t0 < 60:
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.2))
        auth = AVF.AVCaptureDevice.authorizationStatusForMediaType_(AVF.AVMediaTypeVideo)

    types = [AVF.AVCaptureDeviceTypeExternal] if hasattr(AVF, "AVCaptureDeviceTypeExternal") else \
        [AVF.AVCaptureDeviceTypeExternalUnknown]
    disc = AVF.AVCaptureDeviceDiscoverySession.discoverySessionWithDeviceTypes_mediaType_position_(
        types, AVF.AVMediaTypeVideo, AVF.AVCaptureDevicePositionUnspecified)
    devices = list(disc.devices())
    res = {"test": "prior_art_avf_native_mjpeg_probe", "platform": "macos", "hostname": host,
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(),
           "command": "uv run --script research/usb_cameras/prior_art/drafts/macos/avf_native_mjpeg_probe.py " + " ".join(sys.argv[1:]),
           "environment": {"os": platform.platform(), "mac_ver": platform.mac_ver()[0], "python": sys.version,
                           "pyobjc": objc.__version__},
           "camera_authorization_status": int(auth), "settings": vars(a), "cameras": []}

    class Delegate(NSObject):
        def init(self):
            self = objc.super(Delegate, self).init()
            self.frames = []
            self.sample = None
            self.subtypes = set()
            return self

        def captureOutput_didOutputSampleBuffer_fromConnection_(self, output, sbuf, conn):
            now = CM.CMClockGetTime(CM.CMClockGetHostTimeClock())
            pts = CM.CMSampleBufferGetPresentationTimeStamp(sbuf)
            fd = CM.CMSampleBufferGetFormatDescription(sbuf)
            st = fourcc(CM.CMFormatDescriptionGetMediaSubType(fd)) if fd else None
            self.subtypes.add(st)
            bb = CM.CMSampleBufferGetDataBuffer(sbuf)
            n = 0
            is_jpeg = None
            if bb is not None:
                n = CM.CMBlockBufferGetDataLength(bb)
                err, data = CM.CMBlockBufferCopyDataBytes(bb, 0, n, None)
                if err == 0 and data:
                    data = bytes(data)
                    is_jpeg = data[:2] == b"\xff\xd8" and data.rstrip(b"\x00")[-2:] == b"\xff\xd9"
                    if is_jpeg and self.sample is None and len(self.frames) > 10:
                        self.sample = data
            self.frames.append({
                "seq": len(self.frames),
                "host_arrival_ns": int(CM.CMTimeGetSeconds(now) * 1e9),
                "os_timestamp_ns": int(CM.CMTimeGetSeconds(pts) * 1e9) if pts.flags & 1 else None,
                "os_timestamp_source": "CMSampleBufferGetPresentationTimeStamp (host time clock)",
                "payload_bytes": int(n), "is_valid_jpeg": is_jpeg, "media_subtype": st,
                "has_image_buffer": CM.CMSampleBufferGetImageBuffer(sbuf) is not None,
            })

        def captureOutput_didDropSampleBuffer_fromConnection_(self, output, sbuf, conn):
            self.frames.append({"dropped": True, "host_arrival_ns": int(time.monotonic_ns())})

    for i, dev in enumerate(devices):
        info = {"index": i, "uniqueID": str(dev.uniqueID()), "modelID": str(dev.modelID()),
                "localizedName": str(dev.localizedName()), "manufacturer": str(dev.manufacturer()),
                "formats": []}
        for f in dev.formats():
            fdsc = f.formatDescription()
            dims = CM.CMVideoFormatDescriptionGetDimensions(fdsc)
            rates = [(r.minFrameRate(), r.maxFrameRate()) for r in f.videoSupportedFrameRateRanges()]
            info["formats"].append({"subtype": fourcc(CM.CMFormatDescriptionGetMediaSubType(fdsc)),
                                    "w": dims.width, "h": dims.height, "fps_ranges": rates})
        if a.only and a.only.lower() not in (info["uniqueID"] + info["localizedName"]).lower():
            res["cameras"].append(info)
            continue
        # pick a compressed-looking format (dmb1 / jpeg) at the requested size, else any at that size
        cand = [f for f in dev.formats()
                if (lambda d: d.width == a.width and d.height == a.height)(
                    CM.CMVideoFormatDescriptionGetDimensions(f.formatDescription()))]
        mj = [f for f in cand if fourcc(CM.CMFormatDescriptionGetMediaSubType(f.formatDescription())) in ("dmb1", "jpeg", "MJPG")]
        chosen = (mj or cand or [None])[0]
        if chosen is None:
            info["skipped"] = "no format at requested size"
            res["cameras"].append(info)
            continue
        info["chosen_subtype"] = fourcc(CM.CMFormatDescriptionGetMediaSubType(chosen.formatDescription()))
        session = AVF.AVCaptureSession.alloc().init()
        inp, err = AVF.AVCaptureDeviceInput.deviceInputWithDevice_error_(dev, None)
        if inp is None:
            info["error"] = f"deviceInput: {err}"
            res["cameras"].append(info)
            continue
        session.addInput_(inp)
        outp = AVF.AVCaptureVideoDataOutput.alloc().init()
        outp.setVideoSettings_({})  # documented: empty dict => device-native format
        outp.setAlwaysDiscardsLateVideoFrames_(False)
        info["available_codec_types"] = [str(x) for x in (outp.availableVideoCodecTypes() or [])]
        info["available_cvpixel_formats"] = [fourcc(int(x)) for x in (outp.availableVideoCVPixelFormatTypes() or [])]
        delegate = Delegate.alloc().init()
        q = libdispatch.dispatch_queue_create(b"probe", None)
        outp.setSampleBufferDelegate_queue_(delegate, q)
        if not session.canAddOutput_(outp):
            info["error"] = "canAddOutput_ false"
            res["cameras"].append(info)
            continue
        session.addOutput_(outp)
        ok, err = dev.lockForConfiguration_(None)
        if ok:
            dev.setActiveFormat_(chosen)
            dur = CM.CMTimeMake(1000, int(a.fps * 1000))
            try:
                dev.setActiveVideoMinFrameDuration_(dur)
                dev.setActiveVideoMaxFrameDuration_(dur)
            except Exception as e:  # noqa: BLE001
                info["frame_duration_error"] = repr(e)
        session.startRunning()
        if ok:
            dev.unlockForConfiguration()
        info["video_settings_after_start"] = {str(k): str(v) for k, v in (outp.videoSettings() or {}).items()}
        t_end = time.time() + a.seconds
        while time.time() < t_end:
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
        session.stopRunning()
        frames = [f for f in delegate.frames if not f.get("dropped")]
        info["n_frames"] = len(frames)
        info["n_dropped_callbacks"] = sum(1 for f in delegate.frames if f.get("dropped"))
        info["delivered_media_subtypes"] = sorted(str(s) for s in delegate.subtypes)
        info["n_valid_jpeg"] = sum(1 for f in frames if f["is_valid_jpeg"])
        info["has_image_buffer_any"] = any(f["has_image_buffer"] for f in frames)
        f2 = [f for f in frames[5:] if f["os_timestamp_ns"]]
        if len(f2) > 3:
            q3 = lambda v: [round(v[0], 3), round(v[len(v) // 2], 3), round(v[-1], 3)]  # noqa: E731
            info["stats"] = {
                "fps_by_arrival": (len(f2) - 1) / ((f2[-1]["host_arrival_ns"] - f2[0]["host_arrival_ns"]) / 1e9),
                "arrival_interval_ms": q3(sorted((b["host_arrival_ns"] - x["host_arrival_ns"]) / 1e6 for x, b in zip(f2, f2[1:]))),
                "pts_interval_ms": q3(sorted((b["os_timestamp_ns"] - x["os_timestamp_ns"]) / 1e6 for x, b in zip(f2, f2[1:]))),
                "arrival_minus_pts_ms": q3(sorted((x["host_arrival_ns"] - x["os_timestamp_ns"]) / 1e6 for x in f2)),
            }
        with open(out / f"frames_{i}.jsonl", "w") as fh:
            for f in frames:
                f["camera_key"] = info["uniqueID"]
                f["backend"] = "avfoundation-pyobjc"
                fh.write(json.dumps(f) + "\n")
        if delegate.sample:
            (out / f"sample_{i}.jpg").write_bytes(delegate.sample)
        res["cameras"].append(info)
    (out / "result.json").write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=1, default=str)[:4000])
    print("wrote", out / "result.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
