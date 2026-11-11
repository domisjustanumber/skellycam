# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Licensing probe for an installed opencv-python wheel (no timing).

Reports, as JSON:
  - cv2 version, Video I/O section of cv2.getBuildInformation()
  - bundled opencv_videoio_ffmpeg*.dll / libavcodec files, and the FFmpeg configure line and
    licence string embedded in that DLL (scanned as bytes; no execution beyond import cv2)
  - functional VideoWriter test per FOURCC through CAP_FFMPEG (and CAP_MSMF on Windows):
    does the writer open and does the file read back with the expected frame count.

Usage (skellycam venv, OpenCV 4.12):
  .venv/Scripts/python.exe <this> --out <json> --tmp <dir for tiny test videos>
Newer OpenCV in isolation:
  uv run --no-project --python 3.12 --with opencv-python==5.0.0.93 python -I <this> --out <json> --tmp <dir>
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import cv2
import numpy as np

FOURCCS = [("avc1", ".mp4"), ("H264", ".mp4"), ("X264", ".mkv"), ("hev1", ".mp4"), ("HEVC", ".mkv"),
           ("AV01", ".mkv"), ("av01", ".mp4"), ("VP80", ".webm"), ("VP90", ".webm"), ("FFV1", ".mkv"),
           ("MJPG", ".avi"), ("MJPG", ".mkv"), ("HFYU", ".avi"), ("XVID", ".avi"), ("mp4v", ".mp4")]


def scan_dll(path: pathlib.Path) -> dict:
    data = path.read_bytes()
    cfg = re.findall(rb"--(?:enable|disable|prefix|arch|target-os|cross-prefix|extra-)[\x20-\x7e]{0,4000}", data)
    longest = max(cfg, key=len).decode("ascii", "replace") if cfg else None
    lic = sorted({m.decode("ascii", "replace") for m in re.findall(
        rb"(?:LGPL|GPL) version [0-9] or later|nonfree and unredistributable", data)})
    libs = sorted({m.decode() for m in re.findall(rb"lib(?:x264|x265|openh264|vpx|aom|dav1d|svtav1|SvtAv1Enc|openjpeg|jxl)", data)})
    return {"file": path.name, "size": len(data), "configure": longest, "license_strings": lic,
            "external_lib_name_strings": libs}


def writer_test(tmp: pathlib.Path, api: int, api_name: str) -> dict:
    out = {}
    h, w = 240, 320
    for fourcc, ext in FOURCCS:
        fn = tmp / f"cv_{api_name}_{fourcc}{ext}"
        if fn.exists():
            fn.unlink()
        vw = cv2.VideoWriter(str(fn), api, cv2.VideoWriter_fourcc(*fourcc), 30.0, (w, h))
        opened = vw.isOpened()
        if opened:
            for i in range(10):
                vw.write(np.full((h, w, 3), i * 20, np.uint8))
        vw.release()
        nread = None
        if opened and fn.exists():
            cap = cv2.VideoCapture(str(fn), cv2.CAP_FFMPEG)
            nread = 0
            while cap.isOpened():
                ok, _ = cap.read()
                if not ok:
                    break
                nread += 1
            cap.release()
        codec = None
        if opened and fn.exists() and shutil.which("ffprobe"):
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=codec_name", "-of", "csv=p=0", str(fn)], capture_output=True, text=True)
            codec = r.stdout.strip() or None
        out[f"{fourcc}{ext}"] = {"opened": opened, "bytes": fn.stat().st_size if fn.exists() else 0,
                                 "frames_read_back": nread, "ffprobe_codec": codec}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tmp", required=True)
    a = ap.parse_args()
    tmp = pathlib.Path(a.tmp) / f"opencv_{cv2.__version__}"
    tmp.mkdir(parents=True, exist_ok=True)
    pkg = pathlib.Path(cv2.__file__).parent
    bi = cv2.getBuildInformation()
    vio = bi[bi.find("Video I/O:"):]
    vio = vio[:vio.find("\n\n")] if "\n\n" in vio else vio[:2000]
    dlls = [p for p in pkg.rglob("*") if re.search(r"(videoio_ffmpeg|avcodec|avformat)", p.name, re.I)
            and p.suffix.lower() in (".dll", ".so", ".dylib") or re.search(r"\.so\.\d", p.name)]
    dlls = [p for p in dlls if re.search(r"(videoio_ffmpeg|avcodec|avformat)", p.name, re.I)]
    res = {
        "python": sys.version, "cv2_version": cv2.__version__, "cv2_path": str(pkg),
        "video_io_build_info": vio,
        "bundled_ffmpeg_files": [scan_dll(p) for p in dlls],
        "license_files_in_pkg": sorted(p.name for p in pkg.glob("LICENSE*")),
        "writer_ffmpeg": writer_test(tmp, cv2.CAP_FFMPEG, "ffmpeg"),
    }
    if os.name == "nt":
        res["writer_msmf"] = writer_test(tmp, cv2.CAP_MSMF, "msmf")
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("cv2", cv2.__version__)
    print(vio)
    for d in res["bundled_ffmpeg_files"]:
        print(d["file"], d["license_strings"], d["external_lib_name_strings"])
        print("  configure:", (d["configure"] or "")[:1500])
    for k in [k for k in res if k.startswith("writer_")]:
        print(k, {f: (v["opened"], v["frames_read_back"], v["ffprobe_codec"]) for f, v in res[k].items()})


if __name__ == "__main__":
    main()
