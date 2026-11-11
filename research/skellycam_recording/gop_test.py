"""Encode a short moving 720p clip through skellycam's two writer paths, for checking GOP structure with ffprobe.

Uses skellycam's own codec resolution (resolve_writer_fourcc("X264")) and PyavVideoWriter, so the files are what a
recording would contain on this machine. No camera is used. Videos are rebuildable: write them to a temp folder.

Run (from the repo root):
    .venv\\Scripts\\python.exe research\\skellycam_recording\\gop_test.py <out_dir> [fps=30] [--no-pyav]
Then:
    ffprobe -v error -select_streams v:0 -show_entries stream=profile,has_b_frames,r_frame_rate,bit_rate -of default=nw=1 <file>
    ffprobe -v error -select_streams v:0 -show_entries frame=pict_type,key_frame -of csv=p=0 <file>
"""
import sys
from pathlib import Path

import cv2
import numpy as np

from skellycam.core.recorders.videos.fourcc_codec_helpers import resolve_writer_fourcc
from skellycam.core.recorders.videos.pyav_video_writer import PyavVideoWriter

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
FPS = float(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else 30.0
W, H, N = 1280, 720, 300
yy, xx = np.mgrid[0:H, 0:W]


def frame(i: int) -> np.ndarray:
    f = np.zeros((H, W, 3), np.uint8)
    f[..., 0] = (xx + 4 * i) % 256
    f[..., 1] = (yy + 2 * i) % 256
    f[..., 2] = ((xx + yy) // 4 + i) % 256
    cv2.circle(f, (100 + 3 * i, 360), 60, (255, 255, 255), -1)
    return f


fourcc = resolve_writer_fourcc("X264", (W, H))
cv2_path = out / f"cv2_{fourcc}_{int(FPS)}fps.mp4"
w = cv2.VideoWriter(str(cv2_path), cv2.VideoWriter.fourcc(*fourcc), FPS, (W, H))
print("resolved fourcc", fourcc, "| cv2 backend", w.getBackendName(), "|", cv2_path)
for i in range(N):
    w.write(frame(i))
w.release()

if "--no-pyav" not in sys.argv:
    pyav_path = out / f"pyav_libx264_{int(FPS)}fps.mp4"
    p = PyavVideoWriter(str(pyav_path), FPS, W, H)
    for i in range(N):
        p.write(frame(i))
    p.release()
    print("pyav |", pyav_path)
