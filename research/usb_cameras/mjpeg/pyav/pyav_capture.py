# /// script
# requires-python = ">=3.10"
# dependencies = ["av>=12", "psutil>=5.9", "pillow>=10", "simplejpeg>=1.7"]
# ///
"""PyAV/FFmpeg MJPEG passthrough capture: demux packets from the camera, never decode.

Windows (dshow):
  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/mjpeg/pyav/pyav_capture.py \
      --input-format dshow --device "video=c922 Pro Stream Webcam" --size 1280x720 --fps 30 --seconds 10 --run-dir <scratch dir>
  (repeat --device for multiple cameras; each is opened in its own thread.)
  Add --dshow-graph-clock to set use_video_device_timestamps=0 (pts = DirectShow graph clock at receipt).
Linux (v4l2):   --input-format v4l2 --device /dev/video0      (input_format=mjpeg is passed automatically)
macOS (avfoundation): --input-format avfoundation --device "0"  (see mjpeg/drafts/macos for the passthrough question)

Then: uv run --script research/usb_cameras/mjpeg/summarize.py <run dir> --test mjpeg_pyav_dshow --label <label>

Records per packet: host_arrival_ns (time.perf_counter_ns == QPC on Windows / CLOCK_MONOTONIC on Linux),
packet pts/dts/time_base, payload bytes. Proof of no-decode: we only iterate container.demux(); the
stream's codec is reported, and no decoder is ever opened (codec_context is never .decode()d).
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mjpeg_common as mc  # noqa: E402

import av  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--input-format", default={"win32": "dshow", "darwin": "avfoundation"}.get(sys.platform, "v4l2"))
ap.add_argument("--device", action="append", required=True)
ap.add_argument("--size", default="1280x720")
ap.add_argument("--fps", type=float, default=30)
ap.add_argument("--seconds", type=float, default=10)
ap.add_argument("--warmup", type=float, default=2)
ap.add_argument("--run-dir", required=True)
ap.add_argument("--dshow-graph-clock", action="store_true")
ap.add_argument("--option", action="append", default=[], help="extra FFmpeg input option key=value")
a = ap.parse_args()

W, H = map(int, a.size.lower().split("x"))
writer = mc.RunWriter(Path(a.run_dir))
stop = threading.Event()
cams_meta: list[dict] = []
errors: list[str] = []


def options_for() -> dict:
    o = {"video_size": f"{W}x{H}", "framerate": f"{a.fps:g}"}
    if a.input_format == "dshow":
        o.update({"vcodec": "mjpeg", "rtbufsize": "512M"})
        if a.dshow_graph_clock:
            o["use_video_device_timestamps"] = "0"
    elif a.input_format == "v4l2":
        o.update({"input_format": "mjpeg", "timestamps": "abs"})
    elif a.input_format == "avfoundation":
        pass  # avfoundation has no compressed-passthrough option; see drafts/macos
    for kv in a.option:
        k, v = kv.split("=", 1)
        o[k] = v
    return o


def reader(idx: int, dev: str, ready: threading.Event):
    opts = options_for()
    t_open = time.perf_counter_ns()
    try:
        c = av.open(dev, format=a.input_format, options=opts)
    except Exception as e:
        errors.append(f"{dev}: open failed: {e!r}")
        ready.set()
        return
    s = c.streams.video[0]
    tb = s.time_base
    info = {"idx": idx, "name": dev, "options": opts, "codec": s.codec_context.name, "pix_fmt": s.codec_context.pix_fmt, "stream_time_base": str(tb),
            "stream_size": [s.codec_context.width, s.codec_context.height], "stream_rate": str(s.average_rate),
            "open_ms": (time.perf_counter_ns() - t_open) / 1e6}
    cams_meta.append(info)
    ready.set()
    seq = 0
    try:
        for pkt in c.demux(s):
            t = time.perf_counter_ns()
            if pkt.size == 0:
                continue
            b = bytes(pkt)
            pts = pkt.pts
            ts_ns = int(pts * tb * 1_000_000_000) if pts is not None else None
            writer.add(idx, {"camera_key": dev, "backend": f"pyav-{a.input_format}", "seq": seq, "host_arrival_ns": t,
                             "os_timestamp_ns": ts_ns,
                             "os_timestamp_source": f"FFmpeg {a.input_format} packet pts*time_base" + (" (dshow graph clock at receipt)" if a.dshow_graph_clock else " (dshow: IMediaSample time + graph start_time, ref clock 100ns)" if a.input_format == "dshow" else ""),
                             "uvc_pts": None, "uvc_scr_stc": None, "uvc_scr_sof": None, "device_clock_hz": None,
                             "payload_bytes": len(b), "is_valid_jpeg": None, "pkt_pts": pts, "pkt_dts": pkt.dts,
                             "pkt_is_keyframe": pkt.is_keyframe}, b)
            seq += 1
            if stop.is_set():
                break
    except Exception as e:
        errors.append(f"{dev}: demux error: {e!r}")
    finally:
        info["frames"] = seq
        c.close()


started = mc.utc_now()
threads = []
for i, d in enumerate(a.device):
    ev = threading.Event()
    th = threading.Thread(target=reader, args=(i, d, ev), daemon=True)
    th.start()
    ev.wait(30)
    threads.append(th)
time.sleep(a.warmup)
cpu = mc.CpuWindow({"frameserver": mc.frameserver_pid()})
cpu.start()
w0 = time.perf_counter_ns()
time.sleep(a.seconds)
w1 = time.perf_counter_ns()
cpu_res = cpu.stop()
stop.set()
for th in threads:
    th.join(10)
cams_meta.sort(key=lambda m: m["idx"])
meta = {"backend": f"pyav-{a.input_format}", "utc_started": started, "command": sys.argv, "environment": mc.environment(),
        "requested": {"subtype": "MJPG", "width": W, "height": H, "fps": a.fps},
        "decoded_by_pipeline": False,
        "delivered_codecs": [m.get("codec") for m in cams_meta],
        "silent_format_fallback": any(m.get("codec") != "mjpeg" for m in cams_meta) if a.input_format != "avfoundation" else None,
        "decode_evidence": "only container.demux() is called; packets are passed through as bytes; stream codec reported per camera (codec != mjpeg means FFmpeg/the device delivered a different format than requested WITHOUT raising an error)",
        "cpu": cpu_res, "cameras": cams_meta, "errors": errors}
writer.flush(meta, w0, w1)
print(json.dumps({"cameras": [{k: m.get(k) for k in ("name", "codec", "pix_fmt", "frames", "stream_size", "stream_time_base")} for m in cams_meta], "cpu": cpu_res, "errors": errors}))
