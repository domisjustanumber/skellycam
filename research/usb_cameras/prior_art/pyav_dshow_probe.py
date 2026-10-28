# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "av==19.0.2",
#   "pillow>=10",
# ]
# ///
"""PyAV / FFmpeg libavdevice probe: raw MJPEG packets (no decode), device identity, packet timestamps.

Windows: dshow input.  Linux: v4l2 input (-input_format mjpeg).  macOS: avfoundation (note: FFmpeg's
avfoundation device only offers raw pixel formats, see notes; the script records what happens).

WHAT IT ANSWERS
  * Can PyAV hand us the camera's JPEG bytes as demuxed packets without decoding? (SOI/EOI check,
    Pillow decode of every 15th packet, codec name of the stream.)
  * Can a camera be opened by its unique device path (dshow "Alternative name" / v4l2 by-id path)?
  * What do packet PTS values look like vs host arrival time? On Windows the dshow pts is in 100 ns
    units of the DirectShow graph reference clock (IMediaSample::GetTime + graph start time; see
    libavdevice/dshow_pin.c).  We record both, plus pts with use_video_device_timestamps=0.

RUN (shared Windows machine, under camlock):
  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/pyav_dshow_probe.py --seconds 6
  options: --wallclock (use_video_device_timestamps=0), --only <substring>, --width/--height/--fps
Linux:   uv run --script research/usb_cameras/prior_art/pyav_dshow_probe.py --seconds 6   (needs r/w on /dev/video*)
macOS:   uv run --script research/usb_cameras/prior_art/pyav_dshow_probe.py --seconds 6   (camera permission for the terminal)

OUTPUT results/<platform>/<hostname>/prior_art_pyav_<fmt>[-wallclock]/result.json + frames_<tag>.jsonl
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import io
import json
import os
import platform
import re
import socket
import sys
import time
from pathlib import Path

import av
import av.logging

ROOT = Path(__file__).resolve().parent.parent
PLAT = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
HOST = socket.gethostname()
FMT = {"windows": "dshow", "macos": "avfoundation"}.get(PLAT, "v4l2")


def list_dshow() -> list[dict]:
    """Parse FFmpeg's -list_devices output (captured from the av log)."""
    lines = []
    av.logging.set_level(av.logging.INFO)  # PyAV>=13 drops FFmpeg logs unless a level is set
    with av.logging.Capture(True) as logs:
        try:
            av.open("dummy", format="dshow", options={"list_devices": "true"})
        except Exception:  # noqa: BLE001  (dshow always errors after listing)
            pass
    # FFmpeg emits each line in several fragments; join before splitting
    lines = "".join(msg for _lvl, _name, msg in logs).splitlines()
    devs, cur = [], None
    for ln in lines:
        m = re.match(r'\s*"(.+)" \((video|audio|none)\)', ln)
        if m:
            cur = {"name": m.group(1), "kind": m.group(2)}
            devs.append(cur)
            continue
        m = re.match(r'\s*Alternative name "(.+)"', ln)
        if m and cur is not None:
            cur["alternative_name"] = m.group(1)
    av.logging.set_level(None)
    return devs


def list_v4l2() -> list[dict]:
    devs = []
    for p in sorted(glob.glob("/dev/v4l/by-id/*-video-index0")) or sorted(glob.glob("/dev/video*")):
        devs.append({"name": p, "kind": "video", "alternative_name": p, "resolves_to": os.path.realpath(p)})
    return devs


def list_avf() -> list[dict]:
    lines = []
    av.logging.set_level(av.logging.INFO)
    with av.logging.Capture(True) as logs:
        try:
            av.open("", format="avfoundation", options={"list_devices": "true"})
        except Exception:  # noqa: BLE001
            pass
    # FFmpeg emits each line in several fragments; join before splitting
    lines = "".join(msg for _lvl, _name, msg in logs).splitlines()
    devs, video = [], False
    for ln in lines:
        if "video devices" in ln:
            video = True
        elif "audio devices" in ln:
            video = False
        m = re.search(r"\[(\d+)\] (.+)", ln)
        if video and m:
            devs.append({"name": m.group(2), "kind": "video", "alternative_name": m.group(1)})
    return devs


def is_jpeg(b: bytes) -> bool:
    return b[:2] == b"\xff\xd8" and b.rstrip(b"\x00")[-2:] == b"\xff\xd9"


def probe(dev: dict, a, od: Path) -> dict:
    sel = dev.get("alternative_name") or dev["name"]
    if FMT == "dshow":
        url = f"video={sel}"
        opts = {"vcodec": "mjpeg", "video_size": f"{a.width}x{a.height}", "framerate": str(a.fps),
                "rtbufsize": "200M"}
        if a.wallclock:
            opts["use_video_device_timestamps"] = "0"
    elif FMT == "v4l2":
        url = sel
        opts = {"input_format": "mjpeg", "video_size": f"{a.width}x{a.height}", "framerate": str(a.fps)}
    else:
        url = f"{sel}:none"
        opts = {"video_size": f"{a.width}x{a.height}", "framerate": str(a.fps)}
    entry = {"device": dev, "url": url, "options": opts}
    tag = re.sub(r"\W+", "_", (re.search(r"vid_[0-9a-f]{4}&pid_[0-9a-f]{4}", sel, re.I) or [dev["name"]])[0])[:40]
    av.logging.set_level(av.logging.VERBOSE)
    try:
        with av.logging.Capture(True) as logs:
            t_open0 = time.perf_counter_ns()
            c = av.open(url, format=FMT, options=opts)
            t_open1 = time.perf_counter_ns()
    except Exception as e:  # noqa: BLE001
        entry["error"] = f"open failed: {e!r}"
        return entry
    finally:
        av.logging.set_level(None)
    entry["open_log"] = [ln for ln in "".join(m for _l, _n, m in logs).splitlines()
                         if ln.strip() and "passing through packet" not in ln][:60]
    s = c.streams.video[0]
    entry.update({"open_ms": (t_open1 - t_open0) / 1e6, "codec": s.codec_context.name,
                  "time_base": str(s.time_base), "stream_w_h": [s.codec_context.width, s.codec_context.height],
                  "average_rate": str(s.average_rate)})
    frames, sample, n_dec_ok, n_dec_fail = [], None, 0, 0
    t_end = time.monotonic() + a.seconds
    try:
        for pkt in c.demux(s):
            host = time.perf_counter_ns()
            if pkt.size == 0:
                continue
            data = bytes(pkt)
            ok = is_jpeg(data)
            seq = len(frames)
            if ok and seq % 15 == 0:
                try:
                    from PIL import Image
                    Image.open(io.BytesIO(data)).load()
                    n_dec_ok += 1
                except Exception:  # noqa: BLE001
                    ok = False
                    n_dec_fail += 1
            if sample is None and ok and seq >= 10:
                sample = data
            pts_ns = int(pkt.pts * s.time_base * 1_000_000_000) if pkt.pts is not None else None
            frames.append({
                "camera_key": sel, "backend": f"pyav-{FMT}", "seq": seq, "host_arrival_ns": host,
                "os_timestamp_ns": pts_ns,
                "os_timestamp_source": (f"{FMT} packet pts*time_base"
                                        + (" (graph clock, wallclock mode)" if a.wallclock else "")),
                "uvc_pts": None, "uvc_scr_stc": None, "uvc_scr_sof": None, "device_clock_hz": None,
                "payload_bytes": pkt.size, "is_valid_jpeg": ok, "pkt_pts": pkt.pts,
            })
            if time.monotonic() > t_end:
                break
    except Exception as e:  # noqa: BLE001
        entry["error"] = f"demux: {e!r}"
    c.close()
    with open(od / f"frames_{tag}.jsonl", "w") as f:
        for fr in frames:
            f.write(json.dumps(fr) + "\n")
    if sample:
        (od / f"sample_{tag}.jpg").write_bytes(sample)
    st = {}
    fr = frames[5:]
    if len(fr) > 3:
        arr = [x["host_arrival_ns"] for x in fr]
        d_arr = sorted((b - a_) / 1e6 for a_, b in zip(arr, arr[1:]))
        pts = [x["os_timestamp_ns"] for x in fr if x["os_timestamp_ns"] is not None]
        d_pts = sorted((b - a_) / 1e6 for a_, b in zip(pts, pts[1:]))
        off = sorted((x["host_arrival_ns"] - x["os_timestamp_ns"]) / 1e6 for x in fr if x["os_timestamp_ns"] is not None)
        q = lambda v: [round(v[0], 3), round(v[len(v) // 2], 3), round(v[-1], 3)] if v else None  # noqa: E731
        st = {"fps_by_arrival": (len(arr) - 1) / ((arr[-1] - arr[0]) / 1e9),
              "arrival_interval_ms_min_med_max": q(d_arr),
              "pts_interval_ms_min_med_max": q(d_pts),
              "host_arrival_minus_pts_ms_min_med_max (only meaningful if same clock)": q(off),
              "arrival_minus_pts_spread_ms": round(off[-1] - off[0], 3) if off else None}
    entry.update({"n_packets": len(frames), "n_valid_jpeg": sum(x["is_valid_jpeg"] for x in frames),
                  "n_pillow_ok": n_dec_ok, "n_pillow_fail": n_dec_fail, "stats": st,
                  "frames_file": f"frames_{tag}.jsonl", "sample_file": f"sample_{tag}.jpg" if sample else None})
    return entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=6)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--only", default=None)
    ap.add_argument("--wallclock", action="store_true", help="dshow: use_video_device_timestamps=0")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--tag", default="", help="suffix for the result directory")
    ap.add_argument("--list-options", action="store_true", help="dshow: dump FFmpeg list_options per USB camera")
    ap.add_argument("--device", action="append", default=[],
                    help="use only this device selector (dshow alternative name / v4l2 path), repeatable. Skips "
                         "FFmpeg list_devices, which on dshow binds every capture filter to classify its pins")
    a = ap.parse_args()
    name = f"prior_art_pyav_{FMT}" + ("-wallclock" if a.wallclock else "") + (f"-{a.tag}" if a.tag else "")
    # USBCAM_RESULTS_DIR (optional) redirects output so a rerun does not overwrite cited results
    base = Path(os.environ["USBCAM_RESULTS_DIR"]) if os.environ.get("USBCAM_RESULTS_DIR") else ROOT / "results" / PLAT / HOST
    od = base / name
    od.mkdir(parents=True, exist_ok=True)
    if a.device:
        devs = [{"name": d, "kind": "video", "alternative_name": d, "explicit": True} for d in a.device]
    else:
        devs = {"dshow": list_dshow, "v4l2": list_v4l2, "avfoundation": list_avf}[FMT]()
    res = {"test": "prior_art_pyav_probe", "platform": PLAT, "hostname": HOST,
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(),
           "command": " ".join(["uv run --script"] + sys.argv),
           "environment": {"os": platform.platform(), "python": sys.version, "pyav": av.__version__,
                           "ffmpeg_libs": {k: str(v) for k, v in av.library_versions.items()}},
           "settings": {"width": a.width, "height": a.height, "fps": a.fps, "seconds": a.seconds,
                        "exposure": "not controlled (camera auto)"},
           "listed_devices": devs, "cameras": []}
    if a.list_options and FMT == "dshow":
        res["list_options"] = {}
        for d in devs:
            if d["kind"] != "video" or not re.search(r"usb#vid_", d.get("alternative_name", ""), re.I):
                continue
            av.logging.set_level(av.logging.INFO)
            with av.logging.Capture(True) as logs:
                try:
                    av.open(f"video={d['alternative_name']}", format="dshow", options={"list_options": "true"})
                except Exception:  # noqa: BLE001
                    pass
            av.logging.set_level(None)
            res["list_options"][d["name"]] = "".join(m for _l, _n, m in logs).splitlines()
        a.list_only = True
    if not a.list_only:
        cams = [d for d in devs if d["kind"] == "video"]
        if FMT == "dshow":  # physical USB cameras only
            cams = [d for d in cams if re.search(r"usb#vid_", d.get("alternative_name", ""), re.I)]
        if a.only:
            cams = [d for d in cams if a.only.lower() in json.dumps(d).lower()]
        for d in cams:
            res["cameras"].append(probe(d, a, od))
    (od / "result.json").write_text(json.dumps(res, indent=2))
    for cam in res["cameras"]:
        print({k: v for k, v in cam.items() if k not in ("device",)})
    print("wrote", od / "result.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
