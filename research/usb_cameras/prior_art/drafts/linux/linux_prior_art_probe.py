# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "linuxpy==0.25.0; sys_platform == 'linux'",
# ]
# ///
"""Linux DRAFT -- UNVERIFIED until the user runs it.  Prior-art checks for the Linux stack.

WHAT TO RUN (repo root):
    uv run --script research/usb_cameras/prior_art/drafts/linux/linux_prior_art_probe.py --seconds 5
  optional, as root (changes a GLOBAL uvcvideo parameter for the duration of one capture, then restores it):
    sudo -E $(which uv) run --script research/usb_cameras/prior_art/drafts/linux/linux_prior_art_probe.py --seconds 5 --try-hwtimestamps
HARDWARE: UVC webcams with MJPEG.  PERMISSIONS: r/w on /dev/video* (user in group 'video').  Optional tools
used if installed: libcamera's `cam` (package libcamera-tools), `gst-device-monitor-1.0` (gstreamer1.0-tools),
`v4l2-ctl` (v4l-utils).

WHAT IT CHECKS (source citations in research/usb_cameras/prior_art/SURVEY.md):
  1. uvcvideo module parameters quirks / hwtimestamps / clock / nodrop: current values and whether THIS user
     can write them (they are mode 0644 = root-only; quirks is read at probe time, hwtimestamps per buffer).
  2. Per camera (/dev/v4l/by-id/*-video-index0): linuxpy MJPEG capture -> are frames JPEG bytes (SOI/EOI)?
     V4L2 buffer timestamp (uvcvideo: CLOCK_MONOTONIC, taken when the first payload of the frame arrives;
     V4L2_BUF_FLAG_TSTAMP_SRC_SOE) vs host arrival CLOCK_MONOTONIC.
  3. Is there a metadata node (video-index1) and does it report the UVC metadata format 'UVCH'?
  4. With --try-hwtimestamps (root): the same capture with uvcvideo hwtimestamps=1 (PTS/SCR clock recovery).
  5. `cam -l` (libcamera UVC pipeline handler camera IDs) and `gst-device-monitor-1.0 Video/Source` output
     (GStreamer v4l2 device-provider identity properties), if those tools exist.
WRITES: results/linux/<hostname>/prior_art_linux/result.json (+ frames_<cam>[_hw].jsonl)
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PARAMS = Path("/sys/module/uvcvideo/parameters")


def params() -> dict:
    d = {}
    for name in ("quirks", "hwtimestamps", "clock", "nodrop", "timeout"):
        p = PARAMS / name
        if p.exists():
            try:
                d[name] = {"value": p.read_text().strip(), "mode": oct(p.stat().st_mode & 0o777),
                           "writable_by_this_user": os.access(p, os.W_OK)}
            except OSError as e:
                d[name] = {"error": repr(e)}
    return d


def run(cmd: list[str], timeout=30) -> dict:
    if not shutil.which(cmd[0]):
        return {"cmd": cmd, "available": False}
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"cmd": cmd, "available": True, "rc": p.returncode, "stdout": p.stdout[-20000:], "stderr": p.stderr[-4000:]}
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "available": True, "error": "timeout"}


def capture(path: str, a, out: Path, suffix: str) -> dict:
    from linuxpy.video.device import BufferType, Device, VideoCapture

    r = {"device": path, "resolves_to": os.path.realpath(path)}
    frames = []
    try:
        with Device(path) as cam:
            r["card"] = cam.info.card
            r["bus_info"] = cam.info.bus_info
            r["driver"] = cam.info.driver
            cam.set_format(BufferType.VIDEO_CAPTURE, a.width, a.height, "MJPG")
            try:
                cam.set_fps(BufferType.VIDEO_CAPTURE, a.fps)
            except Exception as e:  # noqa: BLE001
                r["set_fps_error"] = repr(e)
            fmt = cam.get_format(BufferType.VIDEO_CAPTURE)
            r["negotiated"] = {"w": fmt.width, "h": fmt.height, "fmt": str(fmt.pixel_format)}
            t_end = time.monotonic() + a.seconds
            with VideoCapture(cam) as stream:
                for fr in stream:
                    host = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
                    data = bytes(fr)
                    ok = data[:2] == b"\xff\xd8" and data.rstrip(b"\x00")[-2:] == b"\xff\xd9"
                    frames.append({"camera_key": path, "backend": "linuxpy-v4l2", "seq": fr.frame_nb,
                                   "host_arrival_ns": host, "os_timestamp_ns": int(round(fr.timestamp * 1e9)),
                                   "os_timestamp_source": "v4l2_buffer.timestamp (uvcvideo; hwtimestamps=%s)" % suffix,
                                   "uvc_pts": None, "uvc_scr_stc": None, "uvc_scr_sof": None,
                                   "device_clock_hz": None, "payload_bytes": len(data), "is_valid_jpeg": ok,
                                   "v4l2_flags": int(fr.flags)})
                    if time.monotonic() > t_end:
                        break
    except Exception as e:  # noqa: BLE001
        r["error"] = repr(e)
    tag = re.sub(r"\W+", "_", Path(path).name)[:60]
    with open(out / f"frames_{tag}_{suffix}.jsonl", "w") as f:
        for x in frames:
            f.write(json.dumps(x) + "\n")
    f2 = frames[5:]
    if len(f2) > 3:
        q = lambda v: [round(v[0], 3), round(v[len(v) // 2], 3), round(v[-1], 3)]  # noqa: E731
        r["stats"] = {
            "n_frames": len(frames), "n_valid_jpeg": sum(x["is_valid_jpeg"] for x in frames),
            "fps_by_arrival": (len(f2) - 1) / ((f2[-1]["host_arrival_ns"] - f2[0]["host_arrival_ns"]) / 1e9),
            "arrival_interval_ms": q(sorted((b["host_arrival_ns"] - x["host_arrival_ns"]) / 1e6 for x, b in zip(f2, f2[1:]))),
            "ts_interval_ms": q(sorted((b["os_timestamp_ns"] - x["os_timestamp_ns"]) / 1e6 for x, b in zip(f2, f2[1:]))),
            "arrival_minus_ts_ms": q(sorted((x["host_arrival_ns"] - x["os_timestamp_ns"]) / 1e6 for x in f2)),
        }
    r["frames_file"] = f"frames_{tag}_{suffix}.jsonl"
    return r


def meta_format(path: str) -> dict:
    from linuxpy.video.device import BufferType, Device
    try:
        with Device(path) as d:
            caps = str(getattr(d.info, "device_capabilities", None) or d.info.raw_capabilities.device_caps)
            try:
                f = d.get_format(BufferType.META_CAPTURE)
                fmt = str(getattr(f, "pixel_format", f))
            except Exception as e:  # noqa: BLE001
                fmt = f"get_format error: {e!r}"
            return {"node": path, "resolves_to": os.path.realpath(path), "device_caps": caps, "meta_format": fmt}
    except Exception as e:  # noqa: BLE001
        return {"node": path, "error": repr(e)}


def main() -> int:
    if not sys.platform.startswith("linux"):
        print("Linux only")
        return 2
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=5)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--try-hwtimestamps", action="store_true", help="root only: set uvcvideo hwtimestamps=1 temporarily")
    a = ap.parse_args()
    host = socket.gethostname()
    out = ROOT / "results" / "linux" / host / "prior_art_linux"
    out.mkdir(parents=True, exist_ok=True)
    try:
        from importlib.metadata import version
        lpv = version("linuxpy")
    except Exception:  # noqa: BLE001
        lpv = None
    res = {"test": "prior_art_linux_probe", "platform": "linux", "hostname": host,
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(),
           "command": "uv run --script research/usb_cameras/prior_art/drafts/linux/linux_prior_art_probe.py " + " ".join(sys.argv[1:]),
           "environment": {"os": platform.platform(), "kernel": platform.release(), "python": sys.version,
                           "linuxpy": lpv, "euid": os.geteuid()},
           "uvcvideo_params": params(), "cameras": [], "metadata_nodes": []}
    vids = sorted(glob.glob("/dev/v4l/by-id/*-video-index0"))
    res["by_id"] = {p: os.path.realpath(p) for p in sorted(glob.glob("/dev/v4l/by-id/*"))}
    res["by_path"] = {p: os.path.realpath(p) for p in sorted(glob.glob("/dev/v4l/by-path/*"))}
    for p in sorted(glob.glob("/dev/v4l/by-id/*-video-index1")):
        res["metadata_nodes"].append(meta_format(p))
    for v in vids:
        res["cameras"].append(capture(v, a, out, "default"))
    if a.try_hwtimestamps:
        p = PARAMS / "hwtimestamps"
        old = p.read_text().strip()
        try:
            p.write_text("1")
            res["hwtimestamps_set_to"] = p.read_text().strip()
            res["cameras_hwtimestamps"] = [capture(v, a, out, "hw") for v in vids]
        except OSError as e:
            res["hwtimestamps_error"] = repr(e)
        finally:
            try:
                p.write_text(old)
            except OSError:
                pass
            res["hwtimestamps_restored_to"] = p.read_text().strip()
    res["libcamera_cam_list"] = run(["cam", "-l"])
    res["gst_device_monitor"] = run(["gst-device-monitor-1.0", "Video/Source"], timeout=20)
    res["v4l2_ctl_list"] = run(["v4l2-ctl", "--list-devices"])
    (out / "result.json").write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps({k: v for k, v in res.items() if k not in ("gst_device_monitor",)}, indent=1, default=str)[:5000])
    print("wrote", out / "result.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
