# /// script
# requires-python = "==3.12.13"
# dependencies = [
#   "av==19.0.2",
#   "cv2-enumerate-cameras==1.4.0",
# ]
# ///
"""Repeated device enumeration through PyAV/FFmpeg dshow and OpenCV (cv2_enumerate_cameras), for W-ID.

    uv run --python 3.12 --script enum_apis.py pyav   --repeats 20
    uv run --python 3.12 --script enum_apis.py ffmpeg --repeats 20 [--ffmpeg ffmpeg]
    uv run --python 3.12 --script enum_apis.py opencv --repeats 20

Prints one JSON object: {"api", "versions", "runs": [{"i", "elapsed_ms", "devices": [{"index", "name", "path"}],
"error"}]}. ``path`` is the FFmpeg "Alternative name" (@device_pnp_\\\\?\\usb#...) for dshow, and the MF symbolic
link / DirectShow DevicePath for OpenCV's CAP_MSMF / CAP_DSHOW lists.

What each one touches (the suite still runs this under camlock with a timeout):
  * FFmpeg dshow ``list_devices`` enumerates CLSID_VideoInputDeviceCategory and prints each device with its media
    type, which FFmpeg >= 5 obtains by binding the capture filter (IMoniker::BindToObject) and walking its pins: a
    KS filter open, no streaming. PyAV 19.0.2 bundles FFmpeg 9.0.2 (same code path as the CLI).
  * cv2_enumerate_cameras 1.4.0 (Windows): MFEnumDeviceSources + attribute reads, and ICreateDevEnum + property-bag
    reads (FriendlyName, DevicePath); its native module imports MFEnumDeviceSources/MFCreateAttributes/
    CoCreateInstance only (checked 2026-11-06), and RERUN_20261027 lists it as enumeration-only. The OpenCV index is
    the position in these lists, which is what VideoCapture(index, CAP_MSMF / CAP_DSHOW) opens.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time


def _parse_dshow_lines(text: str) -> list[dict]:
    devs, cur = [], None
    for line in text.splitlines():
        m = re.search(r'"(.+)"\s+\((video|audio|none)\)\s*$', line.strip()) or \
            re.search(r'^\s*(?:\[[^\]]*\]\s*)?"(.+)"\s*$', line)
        if m and "Alternative name" not in line:
            kind = m.group(2) if m.lastindex and m.lastindex >= 2 else None
            cur = {"index": None, "name": m.group(1), "kind": kind, "path": None}
            devs.append(cur)
            continue
        m = re.search(r'Alternative name\s+"(.+)"', line)
        if m and cur is not None:
            cur["path"] = m.group(1)
    vids = [d for d in devs if d.get("kind") in (None, "video")]
    for i, d in enumerate(vids):
        d["index"] = i
    return vids


def run_pyav(repeats: int) -> dict:
    import av
    import av.logging
    out = {"api": "pyav_dshow", "versions": {"av": av.__version__,
                                             "libavdevice": str(av.library_versions.get("libavdevice"))},
           "runs": []}
    av.logging.set_level(av.logging.INFO)
    for i in range(repeats):
        t0 = time.perf_counter()
        err = None
        with av.logging.Capture(local=False) as logs:
            try:
                av.open("dummy", format="dshow", options={"list_devices": "true"})
            except Exception as e:  # list_devices always ends with an error ("Immediate exit requested" / EIO)
                err = f"{type(e).__name__}: {e}"
        ms = (time.perf_counter() - t0) * 1000
        text = "".join(m for (_lvl, name, m) in logs if name == "dshow")
        out["runs"].append({"i": i, "elapsed_ms": round(ms, 2), "devices": _parse_dshow_lines(text),
                            "expected_exit": err})
    return out


def run_ffmpeg(repeats: int, exe: str) -> dict:
    out = {"api": "ffmpeg_cli_dshow", "versions": {}, "runs": []}
    try:
        v = subprocess.run([exe, "-hide_banner", "-version"], capture_output=True, text=True, timeout=30)
        out["versions"]["ffmpeg"] = (v.stdout.splitlines() or [""])[0]
    except Exception as e:  # noqa: BLE001
        out["versions"]["error"] = repr(e)
    for i in range(repeats):
        t0 = time.perf_counter()
        try:
            r = subprocess.run([exe, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                               capture_output=True, text=True, errors="replace", timeout=30)
            text, err = r.stderr, None
        except Exception as e:  # noqa: BLE001
            text, err = "", repr(e)
        ms = (time.perf_counter() - t0) * 1000
        out["runs"].append({"i": i, "elapsed_ms": round(ms, 2),
                            "devices": _parse_dshow_lines(text),  # FFmpeg 9 prefixes lines '[in#0 @ ...]'
                            "error": err})
    return out


def run_opencv(repeats: int) -> dict:
    import cv2_enumerate_cameras as ce
    from cv2_enumerate_cameras import enumerate_cameras
    try:
        from importlib.metadata import version
        ver = version("cv2-enumerate-cameras")
    except Exception:  # noqa: BLE001
        ver = getattr(ce, "__version__", None)
    out = {"api": "opencv", "versions": {"cv2_enumerate_cameras": ver}, "runs": []}
    msmf, dshow = 1400, 700  # cv2.CAP_MSMF / cv2.CAP_DSHOW (cv2 itself is not needed)
    for i in range(repeats):
        row = {"i": i}
        for name, api in (("CAP_MSMF", msmf), ("CAP_DSHOW", dshow)):
            t0 = time.perf_counter()
            try:
                lst = [{"index": c.index, "name": c.name, "path": c.path,
                        "vid": None if c.vid is None else f"{c.vid:04x}",
                        "pid": None if c.pid is None else f"{c.pid:04x}"} for c in enumerate_cameras(api)]
                e = None
            except Exception as ex:  # noqa: BLE001
                lst, e = [], repr(ex)
            row[name] = {"elapsed_ms": round((time.perf_counter() - t0) * 1000, 2), "devices": lst, "error": e}
        out["runs"].append(row)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("api", choices=["pyav", "ffmpeg", "opencv"])
    ap.add_argument("--repeats", type=int, default=20)
    ap.add_argument("--ffmpeg", default="ffmpeg")
    a = ap.parse_args(argv)
    if a.api == "pyav":
        doc = run_pyav(a.repeats)
    elif a.api == "ffmpeg":
        doc = run_ffmpeg(a.repeats, a.ffmpeg)
    else:
        doc = run_opencv(a.repeats)
    print(json.dumps(doc, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
