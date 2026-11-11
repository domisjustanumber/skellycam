# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2"]
# ///
"""Probe which intra/lossless-relevant encoders and decoders a PyAV build exposes, and the pixel
formats each encoder accepts natively (codec.video_formats = the encoder's AVCodec pix_fmts list).

Run with the pinned skellycam venv (PyAV 18.0.0):
    .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/probe_pyav_caps.py
Run isolated against PyAV 19.0.2 (the PEP 723 header pins it; the venv is not touched):
    uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/probe_pyav_caps.py

Writes results/uncompressed_intra/pyav_caps_<av version>.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import av

OUT = Path(__file__).resolve().parents[2] / "results" / "uncompressed_intra"

ENCODERS = [
    "rawvideo", "ffv1", "ffvhuff", "huffyuv", "utvideo", "magicyuv", "mjpeg", "ljpeg", "jpegls",
    "jpeg2000", "libopenjpeg", "libjxl", "libsvtav1", "libaom-av1", "librav1e", "libvpx-vp9",
    "prores_ks", "dnxhd", "libx264", "libx265", "h264_nvenc", "hevc_nvenc", "av1_nvenc",
    "h264_qsv", "hevc_qsv", "av1_qsv", "av1_amf", "av1_mf", "png", "qoi", "libwebp", "v210",
    "cfhd", "libsvtjpegxs", "libx264rgb",
]
DECODERS = [
    "rawvideo", "ffv1", "ffvhuff", "huffyuv", "utvideo", "magicyuv", "mjpeg", "jpeg2000",
    "libopenjpeg", "libjxl", "jpegxl", "libdav1d", "av1", "vp9", "libvpx-vp9", "prores", "dnxhd",
    "h264", "hevc", "jpegls", "ljpeg", "png", "qoi", "jpegxs", "libsvtjpegxs",
]
CONTAINERS = ["matroska", "nut", "avi", "mov", "mp4", "webm", "ivf", "image2", "image2pipe", "rawvideo"]
PIXFMTS = [
    "nv12", "nv21", "nv16", "yuyv422", "uyvy422", "yvyu422", "gray", "gray10le", "gray12le", "gray16le",
    "bayer_rggb8", "bayer_bggr8", "bayer_gbrg8", "bayer_grbg8", "bayer_rggb16le", "bayer_bggr16le",
    "rgb24", "bgr24", "yuv420p", "yuv422p", "yuv444p", "p010le", "p012le", "p016le", "y210le", "y212le",
]


def main() -> None:
    res: dict = {
        "av_version": av.__version__,
        "library_versions": {k: list(v) for k, v in av.library_versions.items()},
        "python": sys.version,
        "encoders": {},
        "decoders": {},
        "containers_available": {},
        "pix_fmts_known": {},
    }
    for name in ENCODERS:
        try:
            c = av.Codec(name, "w")
            fmts = [f.name for f in (c.video_formats or [])]
            res["encoders"][name] = {"available": True, "long_name": c.long_name, "video_formats": fmts}
        except Exception as e:  # noqa: BLE001 - recording the failure is the point
            res["encoders"][name] = {"available": False, "error": f"{type(e).__name__}: {e}"}
    for name in DECODERS:
        try:
            c = av.Codec(name, "r")
            res["decoders"][name] = {"available": True, "long_name": c.long_name}
        except Exception as e:  # noqa: BLE001
            res["decoders"][name] = {"available": False, "error": f"{type(e).__name__}: {e}"}
    fa = set(av.formats_available)
    for name in CONTAINERS:
        res["containers_available"][name] = name in fa
    for p in PIXFMTS:
        try:
            av.VideoFormat(p)
            res["pix_fmts_known"][p] = True
        except Exception as e:  # noqa: BLE001
            res["pix_fmts_known"][p] = f"{type(e).__name__}: {e}"
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"pyav_caps_{av.__version__}.json"
    out.write_text(json.dumps(res, indent=1))
    avail = [k for k, v in res["encoders"].items() if v["available"]]
    missing = [k for k, v in res["encoders"].items() if not v["available"]]
    print(f"PyAV {av.__version__} libavcodec {av.library_versions['libavcodec']}")
    print("encoders available:", avail)
    print("encoders missing:", missing)
    print("decoders missing:", [k for k, v in res["decoders"].items() if not v["available"]])
    print("wrote", out)


if __name__ == "__main__":
    main()
