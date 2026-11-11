"""Make small intra-only sample files (8 real YUY2 1080p frames, or derived formats) for the cheap
Chromium playback check (chromium_check/main.js). Uses the ffmpeg CLI on PATH (9.0.2).

  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/make_chromium_samples.py
Writes media to C:/Users/Dom/Documents/skellycam-raw/.../uncompressed_intra/chromium_samples/ and a manifest.json there.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uintra_frames as uf  # noqa: E402

MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/chromium_samples")

# name, source, input pix_fmt, ffmpeg args, kind (video|image), mime for canPlayType
SAMPLES = [
    ("mjpeg_422.avi", "yuyv422", "yuyv422", ["-c:v", "mjpeg", "-q:v", "2", "-pix_fmt", "yuvj422p"], "video", "video/x-msvideo"),
    ("mjpeg_422.mkv", "yuyv422", "yuyv422", ["-c:v", "mjpeg", "-q:v", "2", "-pix_fmt", "yuvj422p"], "video", "video/x-matroska"),
    ("ffv1_422.mkv", "yuyv422", "yuyv422", ["-c:v", "ffv1", "-level", "3", "-g", "1", "-pix_fmt", "yuv422p"], "video", "video/x-matroska"),
    ("rawvideo_yuyv.mkv", "yuyv422", "yuyv422", ["-c:v", "rawvideo"], "video", "video/x-matroska"),
    ("vp9_lossless_444.webm", "yuyv422", "yuyv422",
     ["-c:v", "libvpx-vp9", "-lossless", "1", "-g", "1", "-deadline", "realtime", "-cpu-used", "8", "-pix_fmt", "yuv444p"], "video", 'video/webm; codecs="vp09.01.40.08.03"'),
    ("vp9_lossless_422.webm", "yuyv422", "yuyv422",
     ["-c:v", "libvpx-vp9", "-lossless", "1", "-g", "1", "-deadline", "realtime", "-cpu-used", "8", "-pix_fmt", "yuv422p"], "video", 'video/webm; codecs="vp09.01.40.08.02"'),
    ("vp9_intra_420_crf30.webm", "nv12", "nv12",
     ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-g", "1", "-deadline", "realtime", "-cpu-used", "8", "-pix_fmt", "yuv420p"], "video", 'video/webm; codecs="vp09.00.40.08"'),
    ("av1_svt_intra_420.mp4", "nv12", "nv12",
     ["-c:v", "libsvtav1", "-preset", "10", "-crf", "30", "-svtav1-params", "keyint=1", "-pix_fmt", "yuv420p"], "video", 'video/mp4; codecs="av01.0.08M.08"'),
    ("av1_svt_intra_420.webm", "nv12", "nv12",
     ["-c:v", "libsvtav1", "-preset", "10", "-crf", "30", "-svtav1-params", "keyint=1", "-pix_fmt", "yuv420p"], "video", 'video/webm; codecs="av01.0.08M.08"'),
    ("av1_svt_lossless_420.mp4", "nv12", "nv12",
     ["-c:v", "libsvtav1", "-preset", "10", "-svtav1-params", "keyint=1:lossless=1", "-pix_fmt", "yuv420p"], "video", 'video/mp4; codecs="av01.0.08M.08"'),
    ("av1_aom_lossless_422.mp4", "yuyv422", "yuyv422",
     ["-c:v", "libaom-av1", "-usage", "allintra", "-cpu-used", "8", "-crf", "0", "-aom-params", "lossless=1", "-pix_fmt", "yuv422p"], "video", 'video/mp4; codecs="av01.2.08M.08.0.100"'),
    ("av1_aom_lossless_444.mp4", "yuyv422", "yuyv422",
     ["-c:v", "libaom-av1", "-usage", "allintra", "-cpu-used", "8", "-crf", "0", "-aom-params", "lossless=1", "-pix_fmt", "yuv444p"], "video", 'video/mp4; codecs="av01.1.08H.08.0.000"'),
    ("av1_aom_lossless_gray12_bayer.mp4", "bayer_rggb16le", "gray12le",
     ["-c:v", "libaom-av1", "-usage", "allintra", "-cpu-used", "8", "-crf", "0", "-aom-params", "lossless=1"], "video", 'video/mp4; codecs="av01.2.08M.12.1.110"'),
    ("h264_intra_420.mp4", "nv12", "nv12", ["-c:v", "libx264", "-g", "1", "-crf", "18", "-pix_fmt", "yuv420p"], "video", 'video/mp4; codecs="avc1.640028"'),
    ("h264_intra_lossless_420.mp4", "nv12", "nv12", ["-c:v", "libx264", "-g", "1", "-qp", "0", "-pix_fmt", "yuv420p"], "video", 'video/mp4; codecs="avc1.F40028"'),
    ("h264_intra_422.mp4", "yuyv422", "yuyv422", ["-c:v", "libx264", "-g", "1", "-crf", "18", "-pix_fmt", "yuv422p"], "video", 'video/mp4; codecs="avc1.7A0028"'),
    ("hevc_intra_420.mp4", "nv12", "nv12", ["-c:v", "libx265", "-x265-params", "keyint=1:log-level=error", "-crf", "20", "-pix_fmt", "yuv420p", "-tag:v", "hvc1"], "video", 'video/mp4; codecs="hvc1.1.6.L120.90"'),
    ("prores_hq.mov", "yuyv422", "yuyv422", ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"], "video", "video/quicktime"),
    ("jxl_lossless_gray16_bayer.jxl", "bayer_rggb16le", "gray16le", ["-c:v", "libjxl", "-distance", "0", "-effort", "1", "-frames:v", "1"], "image", "image/jxl"),
    ("jxl_lossy_rgb.jxl", "rgb24", "rgb24", ["-c:v", "libjxl", "-distance", "1", "-effort", "3", "-frames:v", "1"], "image", "image/jxl"),
    ("j2k_lossless_gray16.jp2", "gray16le", "gray16le", ["-c:v", "libopenjpeg", "-frames:v", "1"], "image", "image/jp2"),
    ("png16_bayer.png", "bayer_rggb16le", "gray16le", ["-c:v", "png", "-pix_fmt", "gray16be", "-frames:v", "1"], "image", "image/png"),
    ("jpeg_422.jpg", "yuyv422", "yuyv422", ["-c:v", "mjpeg", "-q:v", "2", "-pix_fmt", "yuvj422p", "-frames:v", "1"], "image", "image/jpeg"),
    ("avif_intra_420.avif", "nv12", "nv12", ["-c:v", "libaom-av1", "-still-picture", "1", "-crf", "30", "-cpu-used", "8", "-pix_fmt", "yuv420p", "-frames:v", "1"], "image", "image/avif"),
    ("webp_lossless.webp", "rgb24", "rgb24", ["-c:v", "libwebp", "-lossless", "1", "-frames:v", "1"], "image", "image/webp"),
]


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    yuy, w, h = uf.load_yuy2("c930e_1080p_yuy2", 8)
    inputs: dict = {}
    manifest = []
    for name, src, in_fmt, args, kind, mime in SAMPLES:
        if src not in inputs:
            frames = [uf.derive(src, f, w, h, idx=i) for i, f in enumerate(yuy)]
            p = MEDIA / f"in_{src}.raw"
            p.write_bytes(b"".join(b"".join(pl.tobytes() for pl in fr[0]) for fr in frames))
            inputs[src] = (p, frames[0][2], frames[0][3])
        p, fw, fh = inputs[src]
        out = MEDIA / name
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", in_fmt,
               "-s", f"{fw}x{fh}", "-r", "30", "-i", str(p), *args, str(out)]
        e = subprocess.run(cmd, capture_output=True, text=True)
        ok = e.returncode == 0 and out.exists() and out.stat().st_size > 0
        manifest.append(dict(name=name, path=str(out), kind=kind, mime=mime, made=ok, error=None if ok else e.stderr[-300:],
                             cmd=" ".join(cmd)))
        print(name, "ok" if ok else "FAIL " + e.stderr[-200:])
    for p, *_ in inputs.values():
        p.unlink()
    (MEDIA / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print("wrote", MEDIA / "manifest.json")


if __name__ == "__main__":
    main()
