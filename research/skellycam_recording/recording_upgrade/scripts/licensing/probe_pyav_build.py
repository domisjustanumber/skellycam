# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Licensing probe for an installed PyAV wheel (no timing).

Reports, as JSON:
  - PyAV version, FFmpeg version, per-library configure line and licence string
  - which bundled DLLs/shared objects ship in the wheel (av.libs / av/.dylibs / av.libs)
  - which licence-relevant encoders/decoders are present
  - a functional encode smoke test (8 tiny frames) per encoder, so "present" also means "opens"

Run with the skellycam venv (PyAV 18.0.0):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/licensing/probe_pyav_build.py --out <json>
Run with a newer PyAV in isolation:
  uv run --no-project --with av==19.0.2 python research/.../probe_pyav_build.py --out <json>
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import io
import json
import os
import pathlib
import platform
import sys

import av
import numpy as np  # noqa: F401  (PyAV depends on numpy for from_ndarray)

# Encoders whose licence status matters for G7 / distribution.
ENCODERS = [
    # royalty-free-claimed video
    ("libsvtav1", "yuv420p"), ("libaom-av1", "yuv420p"), ("librav1e", "yuv420p"),
    ("av1_nvenc", "yuv420p"), ("av1_qsv", "nv12"), ("av1_amf", "nv12"), ("av1_mf", "nv12"),
    ("libvpx", "yuv420p"), ("libvpx-vp9", "yuv420p"),
    ("ffv1", "yuv420p"), ("mjpeg", "yuvj422p"), ("libjxl", "rgb24"), ("libopenjpeg", "rgb24"),
    ("jpeg2000", "rgb24"), ("utvideo", "yuv422p"), ("magicyuv", "yuv422p"), ("huffyuv", "yuv422p"),
    ("ffvhuff", "yuv422p"), ("prores_ks", "yuv422p10le"), ("dnxhd", "yuv422p"),
    ("rawvideo", "yuv422p"), ("png", "rgb24"), ("libwebp", "yuv420p"),
    # patent-pool codecs
    ("libx264", "yuv420p"), ("libopenh264", "yuv420p"), ("h264_nvenc", "yuv420p"),
    ("h264_qsv", "nv12"), ("h264_amf", "nv12"), ("h264_mf", "nv12"),
    ("libx265", "yuv420p"), ("hevc_nvenc", "yuv420p"), ("hevc_qsv", "nv12"), ("hevc_amf", "nv12"),
    ("hevc_mf", "nv12"),
]
AUDIO_ENCODERS = ["libopus", "opus", "flac", "pcm_s16le", "aac", "libfdk_aac", "libmp3lame"]
DECODERS = ["libdav1d", "av1", "libaom-av1", "vp8", "vp9", "libvpx-vp9", "h264", "hevc", "mjpeg",
            "jpegxl", "libjxl", "jpeg2000", "libopenjpeg", "ffv1", "utvideo", "magicyuv", "prores",
            "dnxhd", "opus", "flac", "aac"]


def bundled_libs() -> list[str]:
    pkg = pathlib.Path(av.__file__).parent
    out = []
    for cand in [pkg.parent / "av.libs", pkg / ".dylibs", pkg.parent / "av.libs"]:
        if cand.is_dir():
            out += sorted(p.name for p in cand.iterdir())
    return sorted(set(out))


def wheel_license_files() -> list[str]:
    try:
        dist = md.distribution("av")
    except md.PackageNotFoundError:
        return []
    return sorted(str(f) for f in (dist.files or []) if "licen" in str(f).lower() or "copying" in str(f).lower())


def try_encode(name: str, pix_fmt: str) -> dict:
    """Encode 8 frames of 64x64 (or 256x256 for HW encoders) into an in-memory mkv."""
    try:
        codec = av.Codec(name, "w")
    except Exception as e:  # noqa: BLE001
        return {"present": False, "error": f"{type(e).__name__}: {e}"}
    res = {"present": True, "long_name": codec.long_name}
    w = h = 256
    last_err = None
    for fmt in ("matroska", "nut", "avi", "mov"):
        buf = io.BytesIO()
        try:
            with av.open(buf, "w", format=fmt) as c:
                s = c.add_stream(name, rate=30)
                s.width, s.height = w, h
                s.pix_fmt = pix_fmt
                n = 0
                for i in range(8):
                    img = np.full((h, w, 3), (i * 30) % 255, dtype=np.uint8)
                    fr = av.VideoFrame.from_ndarray(img, format="rgb24").reformat(format=pix_fmt)
                    fr.pts = i
                    for p in s.encode(fr):
                        c.mux(p); n += 1
                for p in s.encode():
                    c.mux(p); n += 1
            res.update(opens=True, container=fmt, packets=n, bytes=len(buf.getvalue()))
            return res
        except ValueError as e:  # container does not accept this codec -> try next container
            last_err = f"{fmt}: {e}"
            continue
        except Exception as e:  # noqa: BLE001
            res.update(opens=False, container=fmt, error=f"{type(e).__name__}: {e}"[:300])
            return res
    res.update(opens=False, error=f"no container accepted codec; last: {last_err}"[:300])
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    meta = {}
    try:
        import av._core as core
        meta = {k: {"version": v.get("version"), "license": v.get("license"),
                    "configuration": v.get("configuration")} for k, v in core.library_meta.items()}
    except Exception as e:  # noqa: BLE001
        meta = {"error": repr(e)}
    configs = {v.get("configuration") for v in meta.values() if isinstance(v, dict)}
    cfg = next(iter(configs)) if len(configs) == 1 else None
    flags = cfg.split() if cfg else []
    result = {
        "python": sys.version, "platform": platform.platform(),
        "pyav_version": av.__version__,
        "ffmpeg_version": getattr(av, "ffmpeg_version_info", None),
        "library_meta": meta,
        "configure_enable_flags": sorted(f for f in flags if f.startswith("--enable")),
        "has_enable_gpl": "--enable-gpl" in flags, "has_enable_nonfree": "--enable-nonfree" in flags,
        "has_enable_version3": "--enable-version3" in flags,
        "bundled_libs": bundled_libs(),
        "wheel_license_files": wheel_license_files(),
        "video_encoders": {n: try_encode(n, pf) for n, pf in ENCODERS},
        "audio_encoders_present": {n: (n in av.codecs_available) for n in AUDIO_ENCODERS},
        "decoders_present": {},
    }
    for d in DECODERS:
        try:
            av.Codec(d, "r"); result["decoders_present"][d] = True
        except Exception:  # noqa: BLE001
            result["decoders_present"][d] = False
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    print(json.dumps({k: result[k] for k in ("pyav_version", "ffmpeg_version", "has_enable_gpl",
                                            "has_enable_version3")}, indent=1))
    print("license strings:", {k: v.get("license") for k, v in meta.items() if isinstance(v, dict)})
    print("encoders opened:", [n for n, r in result["video_encoders"].items() if r.get("opens")])
    print("encoders present but failed:", {n: r.get("error") for n, r in result["video_encoders"].items()
                                           if r.get("present") and not r.get("opens")})


if __name__ == "__main__":
    main()
