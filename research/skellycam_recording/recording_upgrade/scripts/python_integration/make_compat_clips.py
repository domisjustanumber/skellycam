"""Make short test clips in the codec/container combinations FreeMoCap might be handed (functional only).

Source: the first 120 frames of the real c930e_720p_flash corpus (camera JPEGs), decoded with PyAV, with a
16-bit frame-index barcode painted over the top 40 rows (16 blocks x 80 px, white = 1) so a reader's frame
identity can be checked after lossy coding. Encoded with the skellycam venv's PyAV 18.0.0 (its bundled FFmpeg).
Each clip is CFR 30 fps unless the name says vfr. Writes clips + manifest.json under the raw media folder.

Run (repo root):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/python_integration/make_compat_clips.py
"""
from __future__ import annotations

import json
import shutil
import sys
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
OUT = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/compat")
N = 120
GOP = 30

# name: (container format, extension, codec, pix_fmt, codec options, gop, extra muxer options, pts mode)
VARIANTS = {
    "mjpeg_mkv": ("matroska", "mkv", "mjpeg", "yuvj422p", {"qmin": "2", "qmax": "4"}, 1, {}, "cfr"),
    "mjpeg_mkv_vfr": ("matroska", "mkv", "mjpeg", "yuvj422p", {"qmin": "2", "qmax": "4"}, 1, {}, "vfr"),
    "mjpeg_avi": ("avi", "avi", "mjpeg", "yuvj422p", {"qmin": "2", "qmax": "4"}, 1, {}, "cfr"),
    "mjpeg_mp4frag_vfr": ("mp4", "mp4", "mjpeg", "yuvj422p", {"qmin": "2", "qmax": "4"}, 1,
                          {"movflags": "frag_keyframe+empty_moov+default_base_moof"}, "vfr"),
    "ffv1_mkv": ("matroska", "mkv", "ffv1", "yuv422p", {"level": "3", "slices": "4", "slicecrc": "1"}, 1, {}, "cfr"),
    "ffv1_avi": ("avi", "avi", "ffv1", "yuv422p", {"level": "3", "slices": "4", "slicecrc": "1"}, 1, {}, "cfr"),
    "vp9_webm": ("webm", "webm", "libvpx-vp9", "yuv420p", {"crf": "30", "b": "0", "deadline": "realtime", "cpu-used": "8"}, GOP, {}, "cfr"),
    "vp9_mkv": ("matroska", "mkv", "libvpx-vp9", "yuv420p", {"crf": "30", "b": "0", "deadline": "realtime", "cpu-used": "8"}, GOP, {}, "cfr"),
    "vp9_mp4": ("mp4", "mp4", "libvpx-vp9", "yuv420p", {"crf": "30", "b": "0", "deadline": "realtime", "cpu-used": "8"}, GOP, {}, "cfr"),
    "vp9_intra_webm": ("webm", "webm", "libvpx-vp9", "yuv420p", {"crf": "30", "b": "0", "deadline": "realtime", "cpu-used": "8"}, 1, {}, "cfr"),
    "av1svt_webm": ("webm", "webm", "libsvtav1", "yuv420p", {"crf": "35", "preset": "10"}, GOP, {}, "cfr"),
    "av1svt_mkv": ("matroska", "mkv", "libsvtav1", "yuv420p", {"crf": "35", "preset": "10"}, GOP, {}, "cfr"),
    "av1svt_mp4": ("mp4", "mp4", "libsvtav1", "yuv420p", {"crf": "35", "preset": "10"}, GOP, {}, "cfr"),
    "av1svt_mp4_vfr": ("mp4", "mp4", "libsvtav1", "yuv420p", {"crf": "35", "preset": "10"}, GOP, {}, "vfr"),
    "av1nvenc_mp4": ("mp4", "mp4", "av1_nvenc", "yuv420p", {"preset": "p4", "cq": "30"}, GOP, {}, "cfr"),
    "h264_x264_mp4": ("mp4", "mp4", "libx264", "yuv420p", {"crf": "18", "preset": "fast"}, GOP, {}, "cfr"),
}


def barcode(img: np.ndarray, idx: int) -> None:
    for bit in range(16):
        img[0:40, bit * 80:(bit + 1) * 80] = 255 if (idx >> bit) & 1 else 0


def vfr_pts_ms(i: int) -> int:
    # 30 fps lattice with deterministic jitter and one 2-frame-long gap after frame 60 (a "drop")
    return round(i * 1000 / 30) + ((i * 37) % 7 - 3) + (67 if i > 60 else 0)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    files = sorted((CORPUS / "c930e_720p_flash").glob("frame_*.jpg"))[:N]
    src = []
    for i, f in enumerate(files):
        with av.open(str(f)) as c:
            fr = next(c.decode(video=0))
        rgb = fr.to_ndarray(format="rgb24")
        barcode(rgb, i)
        src.append(rgb)
    manifest = {"pyav": av.__version__, "libavcodec": av.library_versions["libavcodec"], "frames": N,
                "barcode": "16 blocks x 80 px in rows 0-39, white=1, LSB left", "clips": {}}
    for name, (fmt, ext, codec, pix, opts, gop, mux_opts, mode) in VARIANTS.items():
        path = OUT / f"{name}.{ext}"
        entry = {"path": str(path), "container": fmt, "codec": codec, "pix_fmt": pix, "gop": gop, "pts": mode,
                 "frames": N}
        try:
            with av.open(str(path), "w", format=fmt, options=mux_opts) as c:
                s = c.add_stream(codec, rate=30)
                s.width, s.height, s.pix_fmt = 1280, 720, pix
                s.codec_context.gop_size = gop
                if gop == 1:
                    s.codec_context.max_b_frames = 0
                s.options = opts
                tb = Fraction(1, 1000) if mode == "vfr" else Fraction(1, 30)
                s.codec_context.time_base = tb
                for i, rgb in enumerate(src):
                    vf = av.VideoFrame.from_ndarray(rgb, format="rgb24").reformat(format=pix)
                    vf.pts = vfr_pts_ms(i) if mode == "vfr" else i
                    vf.time_base = tb
                    for p in s.encode(vf):
                        c.mux(p)
                for p in s.encode():
                    c.mux(p)
            entry["ok"] = True
            entry["bytes"] = path.stat().st_size
        except Exception as e:  # noqa: BLE001
            entry["ok"] = False
            entry["error"] = repr(e)[:300]
            if path.exists():
                path.unlink()
        if mode == "vfr":
            entry["vfr_pts_ms"] = [vfr_pts_ms(i) for i in range(N)]
        manifest["clips"][name] = entry
        print(name, entry.get("ok"), entry.get("error", entry.get("bytes")))
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
