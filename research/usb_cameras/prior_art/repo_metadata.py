# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Maintenance snapshot for every library/project in the prior-art survey.

Uses the GitHub REST API through the `gh` CLI (must be logged in: `gh auth status`) plus the public
PyPI and crates.io JSON APIs.  No camera access.

RUN:  uv run --script research/usb_cameras/prior_art/repo_metadata.py
OUTPUT: results/<platform>/<hostname>/prior_art_repo_metadata/result.json

For each GitHub repo: license (SPDX), archived flag, stars, default-branch last commit date, latest
GitHub release (tag + date) or newest tag, number of commits on the default branch since 2025-01-01
(counted via the Link header of the commits API), open-issue count.  For each package: latest version
and upload time on PyPI / crates.io.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAT = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
SINCE = "2025-01-01T00:00:00Z"

REPOS = [
    "libuvc/libuvc", "pupil-labs/libuvc", "pupil-labs/pyuvc", "openpnp/openpnp-capture", "l1npengtul/nokhwa",
    "GStreamer/gstreamer", "FFmpeg/FFmpeg", "PyAV-Org/PyAV", "tiagocoutinho/linuxpy", "antmicro/pyrav4l2",
    "andreaschiavinato/python_grabber", "pywinrt/pywinrt", "ronaldoussoren/pyobjc", "libcamera-org/libcamera",
    "luxonis/depthai-core", "obsproject/obs-studio", "obsproject/libdshowcapture", "libsdl-org/SDL",
    "lukehugh/cv2_enumerate_cameras", "saki4510t/UVCCamera", "raymanfx/libv4l-rs", "mulimoen/libuvc-rs", "kevinmehall/nusb", "realsenseai/librealsense",
    "libusb/libusb", "pyusb/pyusb", "soyersoyer/cameractrls",
    "jtfrey/uvc-util", "freemocap/freemocap", "freemocap/skellycam", "pupil-labs/pupil", "lambdaloop/anipose",
    "CMU-Perceptual-Computing-Lab/openpose", "mprib/caliscope", "perfanalytics/pose2sim", "zju3dv/EasyMocap",
    "opencv/opencv", "qt/qtmultimedia", "ArduCAM/ArduCAM_USB_Camera_Shield", "jacksonliam/mjpg-streamer",
]
PYPI = ["pupil-labs-uvc", "pygrabber", "linuxpy", "v4l2-python3", "v4l2py", "av", "winrt-Windows.Media.Capture",
        "pyobjc-framework-AVFoundation", "depthai", "cv2-enumerate-cameras", "gstreamer-bundle", "PySDL3",
        "libusb-package", "pyusb", "imageio-ffmpeg", "opencv-python", "PySide6-Essentials", "pyrav4l2", "libusb1"]
CRATES = ["nokhwa", "v4l", "uvc", "rusb", "nusb", "windows", "objc2-av-foundation"]


def gh(path: str, include_headers: bool = False):
    cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json"] + (["-i"] if include_headers else []) + [path]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        return None, p.stderr.strip() or p.stdout.strip()
    if include_headers:
        head, _, body = p.stdout.partition("\r\n\r\n") if "\r\n\r\n" in p.stdout else p.stdout.partition("\n\n")
        return (head, body), None
    return json.loads(p.stdout), None


def count_commits(repo: str, branch: str) -> int | None:
    r, err = gh(f"repos/{repo}/commits?sha={branch}&since={SINCE}&per_page=1", include_headers=True)
    if r is None:
        return None
    head, body = r
    m = re.search(r'[?&]page=(\d+)>; rel="last"', head)
    if m:
        return int(m.group(1))
    try:
        return len(json.loads(body))
    except json.JSONDecodeError:
        return None


def repo_info(repo: str) -> dict:
    r, err = gh(f"repos/{repo}")
    if r is None:
        return {"repo": repo, "error": err}
    br = r.get("default_branch")
    info = {"repo": r["full_name"], "html_url": r["html_url"], "license": (r.get("license") or {}).get("spdx_id"),
            "archived": r["archived"], "stars": r["stargazers_count"], "language": r.get("language"),
            "default_branch": br, "pushed_at": r["pushed_at"], "open_issues": r["open_issues_count"]}
    c, _ = gh(f"repos/{r['full_name']}/commits?sha={br}&per_page=1")
    if c:
        info["last_commit_date"] = c[0]["commit"]["committer"]["date"]
        info["last_commit_sha"] = c[0]["sha"]
    rel, _ = gh(f"repos/{r['full_name']}/releases?per_page=1")
    if rel:
        info["latest_release"] = {"tag": rel[0]["tag_name"], "published_at": rel[0]["published_at"]}
    else:
        info["latest_release"] = None  # no GitHub releases; tags API order is not chronological, so not reported
    info[f"commits_since_{SINCE[:10]}"] = count_commits(r["full_name"], br)
    return info


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "skellycam-research (prior_art survey)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}


def main() -> int:
    res = {"test": "prior_art_repo_metadata", "platform": PLAT, "hostname": socket.gethostname(),
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(),
           "command": "uv run --script research/usb_cameras/prior_art/repo_metadata.py",
           "environment": {"os": platform.platform(), "python": sys.version}, "cameras": [],
           "github": [], "pypi": [], "crates": []}
    for r in REPOS:
        print("github", r, file=sys.stderr)
        res["github"].append(repo_info(r))
    for p in PYPI:
        d = get_json(f"https://pypi.org/pypi/{p}/json")
        if "info" in d:
            files = d.get("urls") or []
            res["pypi"].append({"package": p, "version": d["info"]["version"],
                                "upload_time": files[0]["upload_time"] if files else None,
                                "license": d["info"].get("license_expression") or (d["info"].get("license") or "")[:60],
                                "wheel_tags": sorted({f["filename"].rsplit("-", 1)[-1].removesuffix(".whl")
                                                      for f in files if f["filename"].endswith(".whl")})})
        else:
            res["pypi"].append({"package": p, "error": d.get("error")})
    for c in CRATES:
        d = get_json(f"https://crates.io/api/v1/crates/{c}")
        if "crate" in d:
            cr = d["crate"]
            res["crates"].append({"crate": c, "max_version": cr.get("max_stable_version") or cr.get("max_version"),
                                  "updated_at": cr.get("updated_at"), "downloads": cr.get("downloads"),
                                  "repository": cr.get("repository")})
        else:
            res["crates"].append({"crate": c, "error": d.get("errors") or d.get("error")})
    out = (Path(os.environ["USBCAM_RESULTS_DIR"]) if os.environ.get("USBCAM_RESULTS_DIR") else ROOT / "results" / PLAT / socket.gethostname()) / "prior_art_repo_metadata"
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(res, indent=2))
    print("wrote", out / "result.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
