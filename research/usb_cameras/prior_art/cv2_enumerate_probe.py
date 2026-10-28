# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "cv2-enumerate-cameras==1.4.0",
#   "opencv-python-headless",
# ]
# ///
"""cv2_enumerate_cameras probe: identity info this helper gives for OpenCV backend indices.

(OpenCV itself is the baseline and is not investigated; this only records what the enumeration helper
exposes so OpenCV indices can be tied to a stable identity.)  No streaming; enumeration only.

RUN: uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/cv2_enumerate_probe.py
Linux/macOS: same command (Linux backend V4L2, macOS AVFoundation).
OUTPUT results/<platform>/<hostname>/prior_art_cv2_enumerate/result.json
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import socket
import sys
from importlib.metadata import version
from pathlib import Path

import cv2
from cv2_enumerate_cameras import enumerate_cameras

ROOT = Path(__file__).resolve().parent.parent
PLAT = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
APIS = {"windows": ["CAP_MSMF", "CAP_DSHOW"], "linux": ["CAP_V4L2"], "macos": ["CAP_AVFOUNDATION"]}[PLAT]

res = {"test": "prior_art_cv2_enumerate", "platform": PLAT, "hostname": socket.gethostname(),
       "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(),
       "command": "uv run --script research/usb_cameras/prior_art/cv2_enumerate_probe.py",
       "environment": {"os": platform.platform(), "python": sys.version, "opencv": cv2.__version__,
                       "cv2_enumerate_cameras": version("cv2-enumerate-cameras")},
       "by_api": {}}
for api in APIS:
    cams = []
    for c in enumerate_cameras(getattr(cv2, api)):
        cams.append({k: getattr(c, k, None) for k in ("index", "name", "path", "vid", "pid", "backend")})
    res["by_api"][api] = cams
out = (Path(os.environ["USBCAM_RESULTS_DIR"]) if os.environ.get("USBCAM_RESULTS_DIR") else ROOT / "results" / PLAT / socket.gethostname()) / "prior_art_cv2_enumerate"
out.mkdir(parents=True, exist_ok=True)
(out / "result.json").write_text(json.dumps(res, indent=2, default=str))
print(json.dumps(res, indent=1, default=str))
