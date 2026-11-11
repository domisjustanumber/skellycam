# /// script
# requires-python = ">=3.12"
# dependencies = ["opencv-python==5.0.0.93", "numpy==2.3.4"]
# ///
"""Revise-step functional check (no timing): which videoio backend and codec does skellycam's writer call
pattern produce? skellycam calls cv2.VideoWriter(path, fourcc, fps, size) with NO apiPreference (CAP_ANY)
(skellycam/core/recorders/videos/video_recorder.py:125-130, fourcc_codec_helpers.py:121-126), default FOURCC
'X264' -> '.mp4' (camera_config.py:29, fourcc_codec_helpers.py:58). Also tries the H264/avc1 fallbacks.
10 synthetic gray 320x240 frames per clip; codec checked with ffprobe (inspection only).
Usage: <python> cv2_default_backend_check.py <tmp media dir> <out.json>"""
import cv2, numpy as np, subprocess, sys, json, pathlib
d = pathlib.Path(sys.argv[1]); d.mkdir(parents=True, exist_ok=True)
res = {"cv2": cv2.__version__, "api_preference": "none (CAP_ANY)", "clips": {}}
for fcc in ["X264", "H264", "avc1"]:
    fn = d / f"default_{fcc}.mp4"
    if fn.exists():
        fn.unlink()
    vw = cv2.VideoWriter(str(fn), cv2.VideoWriter_fourcc(*fcc), 30.0, (320, 240))
    op = vw.isOpened()
    backend = None
    if op:
        try:
            backend = vw.getBackendName()
        except Exception as e:  # noqa: BLE001
            backend = f"error: {e}"
        for i in range(10):
            vw.write(np.full((240, 320, 3), i * 20, np.uint8))
    vw.release()
    codec = None
    if fn.exists() and fn.stat().st_size > 0:
        codec = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=codec_name", "-of", "csv=p=0", str(fn)],
                               capture_output=True, text=True).stdout.strip() or None
    res["clips"][f"{fcc}.mp4"] = {"opened": op, "backend": backend,
                                  "bytes": fn.stat().st_size if fn.exists() else 0, "ffprobe_codec": codec}
pathlib.Path(sys.argv[2]).write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps(res, indent=1))
