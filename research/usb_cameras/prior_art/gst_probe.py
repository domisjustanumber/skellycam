# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   "gstreamer-bundle==1.28.7; sys_platform != 'linux'",
#   "pillow>=10",
# ]
# ///
"""GStreamer (official PyPI wheels) probe: device identity + raw MJPEG passthrough + buffer timestamps.

WHAT IT ANSWERS
  * Which device-identity properties GStreamer's device providers expose (per OS provider).
  * Whether a <src> ! image/jpeg ! appsink pipeline hands the application the camera's own JPEG
    bytes (no decode/re-encode): checks SOI/EOI, decodes a sample with Pillow, records size.
  * What the buffer PTS means: compares PTS (converted to pipeline-clock absolute time) with the
    host time at which appsink delivered the buffer.

RUN (Windows shared machine -- always under camlock):
  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/gst_probe.py --list
  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/gst_probe.py --capture --source mfvideosrc --seconds 6
  (sources: mfvideosrc | ksvideosrc | dshowvideosrc on Windows; v4l2src on Linux; avfvideosrc on macOS)

  The PyPI wheels (gstreamer-bundle) exist only for Windows and macOS (1.28.x). On Linux install the
  distro packages (gstreamer1.0-plugins-good, python3-gi) and run with the system python:
     python3 research/usb_cameras/prior_art/gst_probe.py --capture --source v4l2src
  1.28.8's gstreamer-plugins wheel lacks a cp39-abi3 win_amd64 build, hence the 1.28.7 pin.

OUTPUT
  results/<platform>/<hostname>/prior_art_gst_<list|capture-SOURCE>/result.json
  + frames_<cam>.jsonl (README per-frame schema) + one sample_<cam>.jpg per camera.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import platform
import re
import socket
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstApp", "1.0")
from gi.repository import Gst, GstApp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PLAT = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
HOST = socket.gethostname()


def out_dir(name: str) -> Path:
    # USBCAM_RESULTS_DIR (optional) redirects output so a rerun does not overwrite cited results
    base = Path(os.environ["USBCAM_RESULTS_DIR"]) if os.environ.get("USBCAM_RESULTS_DIR") else ROOT / "results" / PLAT / HOST
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def struct_to_dict(s) -> dict:
    if s is None:
        return {}
    d = {}
    for i in range(s.n_fields()):
        k = s.nth_field_name(i)
        v = s.get_value(k)
        try:
            json.dumps(v)
            d[k] = v
        except TypeError:
            d[k] = str(v)
    return d


def list_devices() -> list[dict]:
    mon = Gst.DeviceMonitor.new()
    mon.add_filter("Video/Source", None)
    mon.start()
    devs = []
    for dev in mon.get_devices():
        props = struct_to_dict(dev.get_properties())
        caps = dev.get_caps()
        caps_names = sorted({caps.get_structure(i).get_name() for i in range(caps.get_size())}) if caps else []
        jpeg_modes = []
        if caps:
            for i in range(caps.get_size()):
                st = caps.get_structure(i)
                if st.get_name() == "image/jpeg":
                    jpeg_modes.append(st.to_string())
        el = dev.create_element(None)
        factory = el.get_factory().get_name() if el else None
        devs.append({
            "display_name": dev.get_display_name(),
            "device_class": dev.get_device_class(),
            "element_factory": factory,
            "properties": props,
            "caps_media_types": caps_names,
            "jpeg_caps_sample": jpeg_modes[:6],
            "n_jpeg_caps": len(jpeg_modes),
        })
    mon.stop()
    return devs


def cam_key(dev: dict) -> str:
    p = dev["properties"]
    return str(p.get("device.path") or p.get("device.strid") or p.get("api.v4l2.path") or dev["display_name"])


USB_RE = re.compile(r"vid_([0-9a-f]{4})&pid_([0-9a-f]{4})", re.I)


def explicit_devices(paths: list[str], names: list[str]) -> list[dict]:
    """Build device entries without Gst.DeviceMonitor. The monitor's providers open every camera to
    read caps; this lets a run touch only the listed cameras (e.g. to keep an excluded camera closed)."""
    devs = [{"display_name": p, "properties": {"device.path": p}, "n_jpeg_caps": None, "explicit": True}
            for p in paths]
    devs += [{"display_name": n, "properties": {}, "n_jpeg_caps": None, "explicit": True} for n in names]
    return devs


def capture(source: str, seconds: float, width: int, height: int, fps: int, only: str | None,
            paths: list[str] | None = None, names: list[str] | None = None) -> dict:
    if paths or names:
        devs = explicit_devices(paths or [], names or [])
    else:
        devs = [d for d in list_devices() if d["element_factory"] == source]
    if only:
        devs = [d for d in devs if only.lower() in cam_key(d).lower() or only.lower() in d["display_name"].lower()]
    # only devices that advertise image/jpeg caps (skips virtual cameras); explicit devices are kept
    devs = [d for d in devs if d.get("explicit") or d["n_jpeg_caps"] > 0]
    od = out_dir(f"prior_art_gst_capture-{source}")
    results = []
    for dev in devs:
        key = cam_key(dev)
        m = USB_RE.search(key)
        tag = f"{m.group(1)}_{m.group(2)}".lower() if m else re.sub(r"\W+", "_", dev["display_name"])[:32]
        props = dev["properties"]
        # properties are set programmatically: gst-launch syntax would eat the backslashes in
        # Windows device paths
        if source == "mfvideosrc":
            src_props = {"device-path": key}
        elif source in ("dshowvideosrc", "ksvideosrc") and dev.get("explicit") and props.get("device.path"):
            src_props = {"device-path": props["device.path"]}
        elif source in ("dshowvideosrc", "ksvideosrc"):
            src_props = {"device-name": dev["display_name"]}
        elif source == "v4l2src":
            src_props = {"device": props.get("api.v4l2.path") or props.get("device.path")}
        elif source == "avfvideosrc":
            src_props = {"device-index": int(props.get("device.index", 0))}
        else:
            src_props = {}
        desc = (f"{source} name=src ! image/jpeg,width={width},height={height},framerate={fps}/1 "
                f"! appsink name=sink emit-signals=false sync=false max-buffers=200 drop=false")
        entry = {"camera_key": key, "display_name": dev["display_name"], "pipeline": desc, "src_props": src_props}
        try:
            pipe = Gst.parse_launch(desc)
            src_el = pipe.get_by_name("src")
            for k, v in src_props.items():
                src_el.set_property(k, v)
        except Exception as e:  # noqa: BLE001
            entry["error"] = f"parse_launch: {e}"
            results.append(entry)
            continue
        sink = pipe.get_by_name("sink")
        ret = pipe.set_state(Gst.State.PLAYING)
        frames = []
        t_end = time.monotonic() + seconds
        first_jpeg = None
        n_valid = 0
        n_decoded = 0
        n_decode_fail = 0
        neg_caps = None
        n_meta = 0
        clock = None
        base_time = None
        while time.monotonic() < t_end:
            sample = sink.try_pull_sample(Gst.SECOND // 2)
            if sample is None:
                msg = pipe.get_bus().pop_filtered(Gst.MessageType.ERROR)
                if msg:
                    err, dbg = msg.parse_error()
                    entry["error"] = f"{err.message} | {dbg}"
                    break
                continue
            host_ns = time.perf_counter_ns()
            if clock is None:
                clock = pipe.get_clock()
                base_time = pipe.get_base_time()
            clk_now = clock.get_time()
            buf = sample.get_buffer()
            if neg_caps is None:
                neg_caps = sample.get_caps().to_string()
            ok, info = buf.map(Gst.MapFlags.READ)
            data = bytes(info.data)
            buf.unmap(info)
            soi = data[:2] == b"\xff\xd8"
            eoi = data.rstrip(b"\x00")[-2:] == b"\xff\xd9"
            valid = bool(soi and eoi)
            seq = len(frames)
            decoded = None
            if valid and seq % 15 == 0:
                try:
                    from PIL import Image
                    im = Image.open(io.BytesIO(data))
                    im.load()
                    decoded = True
                    n_decoded += 1
                except Exception:  # noqa: BLE001
                    decoded = False
                    n_decode_fail += 1
            n_valid += valid
            if first_jpeg is None and valid and seq >= 10:
                first_jpeg = data
            # reference timestamp metas (if any element attaches them)
            metas = []
            try:
                it = buf.iterate_meta() if hasattr(buf, "iterate_meta") else []
                for meta in it:
                    metas.append(str(meta))
            except Exception:  # noqa: BLE001
                pass
            n_meta += len(metas)
            pts = buf.pts if buf.pts != Gst.CLOCK_TIME_NONE else None
            # pts (running time) -> absolute pipeline clock -> host perf_counter domain
            os_ts = None
            if pts is not None:
                abs_clock = base_time + pts
                os_ts = host_ns - (clk_now - abs_clock)
            frames.append({
                "camera_key": key,
                "backend": f"gst-{source}",
                "seq": seq,
                "host_arrival_ns": host_ns,
                "os_timestamp_ns": os_ts,
                "os_timestamp_source": "GstBuffer.pts (running time) + base_time, mapped via pipeline clock",
                "uvc_pts": None, "uvc_scr_stc": None, "uvc_scr_sof": None, "device_clock_hz": None,
                "payload_bytes": len(data),
                "is_valid_jpeg": valid if decoded is None else (valid and decoded),
                "gst_pts_ns": pts,
                "gst_dts_ns": buf.dts if buf.dts != Gst.CLOCK_TIME_NONE else None,
                "gst_duration_ns": buf.duration if buf.duration != Gst.CLOCK_TIME_NONE else None,
                "gst_offset": buf.offset,
                "n_metas": len(metas),
            })
        readback = {}
        for pname in ("device-path", "device-name", "device-index"):
            try:
                readback[pname] = src_el.get_property(pname)
            except Exception:  # noqa: BLE001
                pass
        entry["src_readback_while_playing"] = readback
        pipe.set_state(Gst.State.NULL)
        with open(od / f"frames_{tag}.jsonl", "w") as f:
            for fr in frames:
                f.write(json.dumps(fr) + "\n")
        if first_jpeg:
            (od / f"sample_{tag}.jpg").write_bytes(first_jpeg)
        stats = {}
        if len(frames) > 2:
            arr = [fr["host_arrival_ns"] for fr in frames]
            dts_ = [(b - a) / 1e6 for a, b in zip(arr, arr[1:])]
            lat = [(fr["host_arrival_ns"] - fr["os_timestamp_ns"]) / 1e6 for fr in frames if fr["os_timestamp_ns"]]
            ptsd = [(b["gst_pts_ns"] - a["gst_pts_ns"]) / 1e6 for a, b in zip(frames, frames[1:]) if a["gst_pts_ns"] and b["gst_pts_ns"]]
            span = (arr[-1] - arr[0]) / 1e9
            stats = {
                "fps_by_arrival": (len(arr) - 1) / span if span else None,
                "arrival_interval_ms_min_med_max": [min(dts_), sorted(dts_)[len(dts_) // 2], max(dts_)],
                "pts_interval_ms_min_med_max": [min(ptsd), sorted(ptsd)[len(ptsd) // 2], max(ptsd)] if ptsd else None,
                "arrival_minus_pts_ms_min_med_max": [min(lat), sorted(lat)[len(lat) // 2], max(lat)] if lat else None,
                "payload_bytes_min_med_max": sorted(fr["payload_bytes"] for fr in frames)[:: max(1, len(frames) // 2)][:3],
            }
        entry.update({
            "set_state_return": str(ret),
            "negotiated_caps": neg_caps,
            "n_frames": len(frames),
            "n_valid_soi_eoi": n_valid,
            "n_pillow_decoded_ok": n_decoded,
            "n_pillow_decode_fail": n_decode_fail,
            "n_buffer_metas_total": n_meta,
            "stats": stats,
            "frames_file": f"frames_{tag}.jsonl",
            "sample_file": f"sample_{tag}.jpg" if first_jpeg else None,
        })
        results.append(entry)
    return {"devices_tested": results, "settings": {"width": width, "height": height, "fps": fps,
            "seconds": seconds, "exposure": "not controlled (camera auto)"}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--source", default={"windows": "mfvideosrc", "macos": "avfvideosrc"}.get(PLAT, "v4l2src"))
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--only", default=None, help="substring of device path/name")
    ap.add_argument("--device-path", action="append", default=[],
                    help="capture only this device path (repeatable); skips Gst.DeviceMonitor, which opens every camera")
    ap.add_argument("--device-name", action="append", default=[],
                    help="capture only this device name (repeatable, ks/dshow); skips Gst.DeviceMonitor")
    a = ap.parse_args()
    Gst.init(None)
    res = {
        "test": "prior_art_gst_probe",
        "platform": PLAT,
        "hostname": HOST,
        "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(),
        "command": " ".join([Path(sys.executable).name] + sys.argv),
        "environment": {"os": platform.platform(), "python": sys.version, "gstreamer": Gst.version_string()},
    }
    if a.capture:
        res.update(capture(a.source, a.seconds, a.width, a.height, a.fps, a.only, a.device_path, a.device_name))
        name = f"prior_art_gst_capture-{a.source}"
    else:
        res["devices"] = list_devices()
        name = "prior_art_gst_list"
    p = out_dir(name) / "result.json"
    p.write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=1, default=str)[:6000])
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
