"""Large clips for the serving/seek test (does seeking work when the server/protocol has no Range support?).

Small clips (<12 MB) can be buffered whole by the media stack, which hides missing Range support. These clips are
~100+ MB. Source: c930e_720p_flash frames 0..599 (600 real consecutive frames, 20 s @ 30 fps, no looping), index
pattern stamped as in make_clips.py (frames 0..59 are therefore pixel-identical to the small-clip master).
Encode: VP9 lossless 4:4:4 (libvpx-vp9 -lossless 1, GOP 30), muxed with -c copy into
  big_vp9ll__webm.webm, big_vp9ll__mp4_faststart.mp4 (moov first), big_vp9ll__mp4_moovend.mp4 (moov at end).
Output: <media>/big/*, manifest.json gains "big_clips".
Run: .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/make_big_clips.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_codecs")
N = 600
BLOCK, NBITS = 40, 10


def stamp(img: np.ndarray, idx: int) -> None:
    img[0:BLOCK, 0:BLOCK] = 255
    img[0:BLOCK, BLOCK:2 * BLOCK] = 0
    for b in range(NBITS):
        x0 = (2 + b) * BLOCK
        img[0:BLOCK, x0:x0 + BLOCK] = 255 if (idx >> (NBITS - 1 - b)) & 1 else 0


def main() -> None:
    out = MEDIA / "big"
    out.mkdir(exist_ok=True)
    raw = out / "master.raw"
    with open(raw, "wb") as f:
        for i in range(N):
            img = cv2.imdecode(np.frombuffer((CORPUS / "c930e_720p_flash" / f"frame_{i:06d}.jpg").read_bytes(), np.uint8), cv2.IMREAD_COLOR)
            stamp(img, i)
            f.write(img.tobytes())
    inter = out / "big_vp9ll.mkv"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "1280x720", "-r", "30", "-i", str(raw),
                    "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-lossless", "1", "-g", "30",
                    "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv444p", "-colorspace", "bt709", "-color_range", "tv", str(inter)], check=True)
    raw.unlink()
    clips = []
    for cid, args, name in [("big_vp9ll__webm", ["-f", "webm"], "big_vp9ll__webm.webm"),
                            ("big_vp9ll__mp4_faststart", ["-f", "mp4", "-movflags", "+faststart"], "big_vp9ll__mp4_faststart.mp4"),
                            ("big_vp9ll__mp4_moovend", ["-f", "mp4"], "big_vp9ll__mp4_moovend.mp4")]:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(inter), "-c", "copy", *args, str(out / name)], check=True)
        clips.append({"id": cid, "codec": "vp9_lossless_444", "container": cid.split("__")[1], "file": f"big/{name}",
                      "bytes": (out / name).stat().st_size, "frames": N})
        print(cid, clips[-1]["bytes"])
    man = json.loads((MEDIA / "manifest.json").read_text())
    man["big_clips"] = clips
    (MEDIA / "manifest.json").write_text(json.dumps(man))


if __name__ == "__main__":
    main()
