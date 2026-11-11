"""Verifier functional check (no timing): which codec does cv2.VideoWriter(CAP_MSMF) write for FOURCCs that
OpenCV's cap_msmf.cpp FourCC2GUID maps explicitly (HEVC, H265, MP4V, WMV3, MJPG) versus unmapped ones
(hev1, avc1, av01, mp4v), using the extension MSMF accepts (.mp4, or .wmv for WMV3).
10 synthetic gray 320x240 frames per clip; output codec checked with ffprobe.
Usage: <python> verify_msmf_fourcc_check.py <tmp media dir> <out.json>"""
import cv2, numpy as np, subprocess, sys, json, pathlib
d = pathlib.Path(sys.argv[1]); d.mkdir(parents=True, exist_ok=True)
res = {"cv2": cv2.__version__, "clips": {}}
for fcc, ext in [("HEVC", ".mp4"), ("H265", ".mp4"), ("MP4V", ".mp4"), ("MJPG", ".mp4"), ("WMV3", ".wmv"),
                 ("hev1", ".mp4"), ("avc1", ".mp4"), ("av01", ".mp4"), ("mp4v", ".mp4")]:
    fn = d / f"msmf_{fcc}{ext}"
    if fn.exists():
        fn.unlink()
    vw = cv2.VideoWriter(str(fn), cv2.CAP_MSMF, cv2.VideoWriter_fourcc(*fcc), 30.0, (320, 240))
    op = vw.isOpened()
    if op:
        for i in range(10):
            vw.write(np.full((240, 320, 3), i * 20, np.uint8))
    vw.release()
    codec = None
    if fn.exists():
        codec = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                                "-of", "csv=p=0", str(fn)], capture_output=True, text=True).stdout.strip() or None
    res["clips"][f"{fcc}{ext}"] = {"opened": op, "bytes": fn.stat().st_size if fn.exists() else 0, "ffprobe_codec": codec}
pathlib.Path(sys.argv[2]).write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps(res, indent=1))
