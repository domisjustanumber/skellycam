"""Shared paths and input preparation for the gpu_encode topic (recording-upgrade study).

Inputs are derived from the real-camera corpus (no camera is touched):
  nv12_1080p.yuv  : c930e_1080p_yuy2 frames 0-7 (camera's own packed YUYV 4:2:2), converted to NV12 by
                    ffmpeg swscale (yuyv422 -> nv12, default bicubic chroma), 8 frames.
  nv12_720p.yuv   : c930e_720p_flash frame_000000..000059.jpg decoded by ffmpeg's mjpeg decoder
                    (yuvj422p) and converted to NV12 by swscale, 60 frames.
  yuv420p_1080p.yuv, yuv422p10_1080p.yuv, bgr0_1080p.yuv: same 8 YUY2 frames converted by swscale
                    (used for ffv1_vulkan / prores_ks_vulkan, which do not take NV12).
  bayer_rggb16le_1080p.yuv: synthetic RGGB mosaic sampled from bgr0_1080p (R/G/G/B sites, 8-bit value << 8);
                    a stand-in for a 16-bit Bayer camera, not real sensor data.
  mjpeg_720p.mjpeg / mjpeg_1080p.mjpeg: corpus JPEG bytes concatenated unmodified (c930e_720p_flash
                    frames 0-59, c922_1080p frames 0-18).
Media (they show the room) live outside the repo under MEDIA.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
STUDY = REPO / "research/skellycam_recording/recording_upgrade"
RESULTS = STUDY / "results/gpu_encode"
BENCH = RESULTS / "bench"
RAWROOT = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109")
CORPUS = RAWROOT / "corpus"
MEDIA = RAWROOT / "gpu_encode"
INPUTS = MEDIA / "inputs"

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

INPUT_SPECS = {
    # name: (pix_fmt, width, height, frames)
    "nv12_1080p": ("nv12", 1920, 1080, 8),
    "nv12_720p": ("nv12", 1280, 720, 60),
    "yuv420p_1080p": ("yuv420p", 1920, 1080, 8),
    "yuv422p10le_1080p": ("yuv422p10le", 1920, 1080, 8),
    "bgr0_1080p": ("bgr0", 1920, 1080, 8),
    "bayer_rggb16le_1080p": ("bayer_rggb16le", 1920, 1080, 8),
}


def run(cmd: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


def nvidia_smi() -> str:
    try:
        r = run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu,driver_version",
                 "--format=csv,noheader"], timeout=20)
        return r.stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"nvidia-smi failed: {e!r}"


def prepare_inputs() -> dict[str, Path]:
    INPUTS.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    # concatenated YUY2 (8 frames)
    yuy2 = INPUTS / "c930e_1080p_yuy2_8f.yuy2"
    if not yuy2.exists():
        frames = sorted((CORPUS / "c930e_1080p_yuy2").glob("frame_*.yuy2"))
        with open(yuy2, "wb") as f:
            for p in frames:
                f.write(p.read_bytes())
    for name, (pf, w, h, n) in INPUT_SPECS.items():
        dst = INPUTS / f"{name}.yuv"
        out[name] = dst
        if dst.exists():
            continue
        if name.startswith("bayer"):
            continue  # derived from bgr0 below
        if name == "nv12_720p":
            src = ["-framerate", "30", "-start_number", "0", "-i", str(CORPUS / "c930e_720p_flash/frame_%06d.jpg"),
                   "-frames:v", str(n)]
        else:
            src = ["-f", "rawvideo", "-pix_fmt", "yuyv422", "-s", "1920x1080", "-framerate", "30", "-i", str(yuy2)]
        r = run([FFMPEG, "-hide_banner", "-v", "error", "-y", *src, "-pix_fmt", pf, "-f", "rawvideo", str(dst)])
        if r.returncode != 0:
            raise RuntimeError(f"input prep failed for {name}: {r.stderr}")
    bayer = INPUTS / "bayer_rggb16le_1080p.yuv"
    out["bayer_rggb16le_1080p"] = bayer
    if not bayer.exists():
        import numpy as np  # noqa: PLC0415
        rgb = np.fromfile(out["bgr0_1080p"], np.uint8).reshape(-1, 1080, 1920, 4)
        m = np.zeros(rgb.shape[:3], np.uint16)
        m[:, 0::2, 0::2] = rgb[:, 0::2, 0::2, 2].astype(np.uint16) << 8  # R
        m[:, 0::2, 1::2] = rgb[:, 0::2, 1::2, 1].astype(np.uint16) << 8  # G
        m[:, 1::2, 0::2] = rgb[:, 1::2, 0::2, 1].astype(np.uint16) << 8  # G
        m[:, 1::2, 1::2] = rgb[:, 1::2, 1::2, 0].astype(np.uint16) << 8  # B
        m.astype("<u2").tofile(bayer)
    for name, (setname, n) in {"mjpeg_720p": ("c930e_720p_flash", 60), "mjpeg_1080p": ("c922_1080p", 19)}.items():
        dst = INPUTS / f"{name}.mjpeg"
        out[name] = dst
        if not dst.exists():
            frames = sorted((CORPUS / setname).glob("frame_*.jpg"))[:n]
            with open(dst, "wb") as f:
                for p in frames:
                    f.write(p.read_bytes())
    return out


def probe_stream(path: Path) -> dict:
    """ffprobe: codec, pix_fmt, packet count, keyframe-flagged packets, per-frame pict_type counts."""
    info: dict = {}
    r = run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name,profile,pix_fmt,width,height", "-of", "json", str(path)])
    try:
        s = json.loads(r.stdout)["streams"][0]
        info.update({k: s.get(k) for k in ("codec_name", "profile", "pix_fmt", "width", "height")})
    except Exception:  # noqa: BLE001
        info["probe_error"] = r.stderr.strip()[-400:]
        return info
    r = run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=flags", "-of", "csv=p=0",
             str(path)])
    flags = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    info["packets"] = len(flags)
    info["key_packets"] = sum(1 for f in flags if f.startswith("K"))
    r = run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pict_type", "-of",
             "csv=p=0", str(path)])
    types = [ln.strip().rstrip(",") for ln in r.stdout.splitlines() if ln.strip()]
    counts: dict[str, int] = {}
    for t in types:
        counts[t] = counts.get(t, 0) + 1
    info["decoded_frames"] = len(types)
    info["pict_types"] = counts
    info["decode_stderr"] = r.stderr.strip()[-300:]
    return info
