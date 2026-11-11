"""Crash check for the alpha-video overlay layers: cut each file at 50 % and count decodable frames (ffmpeg).
The VP9-alpha layer is decoded with -c:v libvpx-vp9 (the decoder that keeps alpha); frames whose alpha survived are
counted by checking that the decoded alpha plane is not all-opaque.

Run from repo root (after make_test_media.py):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/alpha_truncation.py
"""
import json
import subprocess
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/overlays/media")
OUT = MEDIA / "truncated"
RES = HERE.parents[1] / "results" / "overlays"
W, H = 1280, 720
res = {}
for name, dec in (("overlay_vp9alpha.webm", ["-c:v", "libvpx-vp9"]), ("overlay_png.mov", []), ("overlay_qtrle.mov", [])):
    d = (MEDIA / name).read_bytes()
    t = OUT / f"trunc50_{name}"
    t.write_bytes(d[: len(d) // 2])
    r = subprocess.run(["ffmpeg", "-v", "error", *dec, "-i", str(t), "-f", "rawvideo", "-pix_fmt", "bgra", "-"], capture_output=True)
    n = len(r.stdout) // (W * H * 4)
    alpha_ok = 0
    for i in range(n):
        a = np.frombuffer(r.stdout, np.uint8, W * H * 4, i * W * H * 4).reshape(H, W, 4)[..., 3]
        alpha_ok += int((a < 8).mean() > 0.5)
    res[name] = {"bytes_full": len(d), "bytes_cut": len(d) // 2, "rc": r.returncode, "frames_decoded": n, "frames_with_transparency": alpha_ok,
                 "stderr_tail": r.stderr.decode("utf-8", "replace")[-300:]}
(RES / "alpha_truncation.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
