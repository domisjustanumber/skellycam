"""Longer clips for the Chromium decode/seek benchmarks (run on a quiet machine; see NOTES.md bench manifest).

Sources (real camera JPEGs from the shared corpus, decoded with OpenCV, index pattern stamped as in make_clips.py):
  720p : c930e_720p_flash frames 0..299 (300 real, consecutive frames = 10 s at 30 fps; no looping)
  1080p: c922_1080p frames 0..18 LOOPED to 300 frames (only 19 frames exist; looping stated in the manifest)
Encodes (GOP 30 unless 'intra'): AV1 (SVT-AV1), VP9, VP8, H.264, HEVC; MP4 for AV1/H.264/HEVC, WebM for VP8/VP9,
plus elementary streams (IVF / Annex B with AUD) for the WebCodecs throughput test.
Output: <media>/bench/*.{mp4,webm,ivf,h264,hevc} and <media>/bench/bench_manifest.json

Run: .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/make_bench_clips.py [--quick]
  --quick: 60 frames only (smoke test)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
OUT = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_codecs/bench")
BLOCK, NBITS = 40, 10
FPS = 30


def stamp(img: np.ndarray, idx: int) -> None:
    img[0:BLOCK, 0:BLOCK] = 255
    img[0:BLOCK, BLOCK:2 * BLOCK] = 0
    for b in range(NBITS):
        x0 = (2 + b) * BLOCK
        img[0:BLOCK, x0:x0 + BLOCK] = 255 if (idx >> (NBITS - 1 - b)) & 1 else 0


def vf(pf: str) -> list[str]:
    return ["-vf", f"scale=out_color_matrix=bt709:out_range=tv,format={pf}", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]


ENC = {
    "av1_g30": (["-c:v", "libsvtav1", "-preset", "8", "-crf", "35", "-g", "30", *vf("yuv420p")], "mp4", "ivf", "av01.0.08M.08"),
    "av1_intra": (["-c:v", "libsvtav1", "-preset", "8", "-crf", "35", "-g", "1", *vf("yuv420p")], "mp4", "ivf", "av01.0.08M.08"),
    "vp9_g30": (["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "32", "-b:v", "0", "-g", "30", *vf("yuv420p")], "webm", "ivf", "vp09.00.40.08"),
    "vp9_intra": (["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "32", "-b:v", "0", "-g", "1", *vf("yuv420p")], "webm", "ivf", "vp09.00.40.08"),
    "vp8_g30": (["-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8", "-crf", "10", "-b:v", "6M", "-g", "30", *vf("yuv420p")], "webm", "ivf", "vp8"),
    "h264_g30": (["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-g", "30", "-x264-params", "aud=1", *vf("yuv420p")], "mp4", "h264", "avc1.640028"),
    "h264_intra": (["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-g", "1", "-x264-params", "aud=1", *vf("yuv420p")], "mp4", "h264", "avc1.640028"),
    "hevc_g30": (["-c:v", "libx265", "-preset", "veryfast", "-crf", "28", "-g", "30", "-x265-params", "aud=1:log-level=error", *vf("yuv420p")], "mp4", "hevc", "hvc1.1.6.L120.B0"),
}


def main() -> None:
    quick = "--quick" in sys.argv
    n = 60 if quick else 300
    OUT.mkdir(parents=True, exist_ok=True)
    clips = []
    for res, src_set, nsrc in [("720p", "c930e_720p_flash", 891), ("1080p", "c922_1080p", 19)]:
        raw = OUT / f"master_{res}.raw"
        w = h = None
        with open(raw, "wb") as f:
            for i in range(n):
                img = cv2.imdecode(np.frombuffer((CORPUS / src_set / f"frame_{i % nsrc:06d}.jpg").read_bytes(), np.uint8), cv2.IMREAD_COLOR)
                h, w = img.shape[:2]
                stamp(img, i)
                f.write(img.tobytes())
        src = ["-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", str(raw)]
        for eid, (args, cont, es, cstr) in ENC.items():
            if res == "1080p" and eid not in ("av1_g30", "vp9_g30", "h264_g30", "av1_intra"):
                continue
            base = OUT / f"{eid}_{res}"
            extra = ["-tag:v", "hvc1"] if eid.startswith("hevc") else []
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *src, *args, *extra, "-movflags", "+faststart", str(base) + f".{cont}"], check=True)
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(base) + f".{cont}", "-map", "0:v:0", "-c", "copy", "-f", es, str(base) + f".{es}"], check=True)
            clips.append({"id": f"{eid}_{res}", "file": f"bench/{base.name}.{cont}", "es": f"bench/{base.name}.{es}", "codec": cstr,
                          "w": w, "h": h, "frames": n, "fps": FPS, "source": src_set,
                          "looped": nsrc < n, "source_frames": nsrc})
            print(clips[-1]["id"])
        raw.unlink()
    (OUT / "bench_manifest.json").write_text(json.dumps({"block": BLOCK, "nbits": NBITS, "quick": quick, "clips": clips}, indent=1))


if __name__ == "__main__":
    main()
