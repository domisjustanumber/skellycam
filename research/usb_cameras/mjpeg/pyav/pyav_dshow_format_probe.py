# /// script
# requires-python = ">=3.10"
# dependencies = ["av>=12"]
# ///
"""Which format does FFmpeg's dshow input actually connect when asked for vcodec=mjpeg?

  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/mjpeg/pyav/pyav_dshow_format_probe.py \
      --cam kiyo --mode 1280x720@30 --mode 1280x720@60 --mode 1920x1080@30 --mode 640x480@30 [--extra key=value] [--no-vcodec] --label kiyo

For each mode: opens with options {vcodec: mjpeg, video_size, framerate} (+ extras), captures FFmpeg's
own log at DEBUG level during open, reads 20 packets, and records stream codec/pix_fmt, packet sizes and
whether packets start with FF D8. Writes results/windows/<host>/mjpeg_pyav_dshow_format_probe/<label>.json
"""
import argparse
import json
import platform
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import av
import av.logging

ap = argparse.ArgumentParser()
ap.add_argument("--device", default=None, help="FFmpeg dshow URL, e.g. 'video=@device_pnp_...'")
ap.add_argument("--cam", default=None, help="test-camera key (mjpeg_common.WINDOWS_CAMERAS); resolved to its @device_pnp_ alternative name")
ap.add_argument("--no-vcodec", action="store_true", help="omit vcodec=mjpeg (let FFmpeg pick the pin's default format)")
ap.add_argument("--mode", action="append", required=True)
ap.add_argument("--extra", action="append", default=[])
ap.add_argument("--label", required=True)
a = ap.parse_args()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mjpeg_common as mc  # noqa: E402
if a.cam:
    a.device = "video=" + mc.dshow_alt_name(a.cam)
if not a.device:
    raise SystemExit("give --device or --cam")
res = []
for m in a.mode:
    size, fps = m.split("@")
    opts = {"video_size": size, "framerate": fps, "rtbufsize": "256M"}
    if not a.no_vcodec:
        opts["vcodec"] = "mjpeg"
    for kv in a.extra:
        k, v = kv.split("=", 1)
        opts[k] = v
    entry = {"mode": m, "options": opts}
    av.logging.set_level(av.logging.DEBUG)
    with av.logging.Capture() as logs:
        try:
            c = av.open(a.device, format="dshow", options=opts)
            s = c.streams.video[0]
            entry.update({"codec": s.codec_context.name, "pix_fmt": s.codec_context.pix_fmt, "size": [s.codec_context.width, s.codec_context.height], "rate": str(s.average_rate)})
            sizes, ffd8 = [], 0
            for i, p in enumerate(c.demux(s)):
                b = bytes(p)
                if not b:
                    continue
                sizes.append(len(b))
                ffd8 += b[:2] == b"\xff\xd8"
                if len(sizes) >= 20:
                    break
            entry.update({"packet_sizes": sizes, "packets_starting_ffd8": ffd8})
            c.close()
        except Exception as e:
            entry["error"] = repr(e)
    av.logging.set_level(av.logging.ERROR)
    lines = "".join(l[2] for l in logs).splitlines()
    entry["ffmpeg_log_dshow"] = [l for l in lines if any(k in l.lower() for k in ("format", "pin", "mjpeg", "yuyv", "codec", "could", "set", "selected", "video_size", "connect", "fourcc", "compression"))][:80]
    res.append(entry)
    print(m, entry.get("codec"), entry.get("pix_fmt"), entry.get("packets_starting_ffd8"), entry.get("error"))
host = socket.gethostname()
out = Path(__file__).resolve().parents[2] / "results" / "windows" / host / "mjpeg_pyav_dshow_format_probe"
out.mkdir(parents=True, exist_ok=True)
(out / f"{a.label}.json").write_text(json.dumps({"test": "mjpeg_pyav_dshow_format_probe", "platform": "windows", "hostname": host,
                                                 "utc_started": datetime.now(timezone.utc).isoformat(), "command": sys.argv,
                                                 "environment": {"os": platform.platform(), "av": av.__version__, "ffmpeg": {k: str(v) for k, v in av.library_versions.items()}},
                                                 "device": a.device, "results": res}, indent=1))
print("wrote", out / f"{a.label}.json")
