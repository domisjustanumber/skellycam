"""Shared paths, input preparation and probes for the hw_accel_target topic (recording-upgrade study).

Adapted from scripts/gpu_encode/common.py. Differences: every conversion and decode is done by PyAV 19.0.2
(its bundled FFmpeg 9.0.2 swscale / mjpeg decoder), not by the ffmpeg CLI; the CLI (ffprobe) is used only to
inspect outputs. No camera is opened; inputs come from the real-camera corpus:
  yuy2_1080p   : corpus c930e_1080p_yuy2 frame_000000..7 (packed YUYV 4:2:2 straight from the camera), 8 frames.
  yuy2b_1080p  : corpus c922_1080p_yuy2 frames 0..7 (second camera).
  mjpeg_720p   : corpus c930e_720p_flash frame_000000..059.jpg (4:2:2 baseline JPEG with DHT), unmodified bytes.
  mjpeg_1080p  : corpus c930e_1080p frame_000000..018.jpg, unmodified bytes.
Derived formats (nv12, yuv420p, yuv422p, nv16, ...) are made in memory with VideoFrame.reformat().
Media (they show the room) live outside the repo under MEDIA.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
STUDY = REPO / "research/skellycam_recording/recording_upgrade"
RESULTS = STUDY / "results/hw_accel_target"
BENCH = RESULTS / "bench"
RAWROOT = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109")
CORPUS = RAWROOT / "corpus"
MEDIA = RAWROOT / "hw_accel_target"

FFPROBE = shutil.which("ffprobe") or "ffprobe"  # inspection only

YUY2_SETS = {"yuy2_1080p": "c930e_1080p_yuy2", "yuy2b_1080p": "c922_1080p_yuy2"}
MJPEG_SETS = {"mjpeg_720p": ("c930e_720p_flash", 60), "mjpeg_1080p": ("c930e_1080p", 19)}


def run(cmd: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


def nvidia_smi() -> str:
    try:
        r = run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu",
                 "--format=csv,noheader"], timeout=20)
        return r.stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"nvidia-smi failed: {e!r}"


def nvenc_sessions() -> int | None:
    try:
        r = run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount", "--format=csv,noheader"], timeout=20)
        return int(r.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return None


def yuy2_bytes(name: str) -> list[bytes]:
    frames = sorted((CORPUS / YUY2_SETS[name]).glob("frame_*.yuy2"))
    return [p.read_bytes() for p in frames]


def jpeg_bytes(name: str) -> list[bytes]:
    setname, n = MJPEG_SETS[name]
    return [p.read_bytes() for p in sorted((CORPUS / setname).glob("frame_*.jpg"))[:n]]


def jpeg_set_bytes(setname: str, n: int) -> list[bytes]:
    return [p.read_bytes() for p in sorted((CORPUS / setname).glob("frame_*.jpg"))[:n]]


def probe_frames(path: Path) -> dict:
    """ffprobe (inspection): stream codec/profile/pix_fmt + per-frame key_frame and pict_type."""
    info: dict = {}
    r = run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name,profile,pix_fmt,width,height,color_range:format=format_name", "-of", "json",
             str(path)])
    try:
        j = json.loads(r.stdout)
        s = j["streams"][0]
        info.update({k: s.get(k) for k in ("codec_name", "profile", "pix_fmt", "width", "height", "color_range")})
        info["format_name"] = j.get("format", {}).get("format_name")
    except Exception:  # noqa: BLE001
        info["probe_error"] = (r.stderr or r.stdout).strip()[-400:]
        return info
    r = run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=key_frame,pict_type",
             "-of", "csv=p=0", str(path)])
    rows = [ln.strip().rstrip(",") for ln in r.stdout.splitlines() if ln.strip()]
    keys, types = 0, {}
    for row in rows:
        parts = row.split(",")
        if parts and parts[0] == "1":
            keys += 1
        t = parts[1] if len(parts) > 1 else "?"
        types[t] = types.get(t, 0) + 1
    info["ffprobe_frames"] = len(rows)
    info["ffprobe_key_frames"] = keys
    info["pict_types"] = types
    info["all_key"] = bool(rows) and keys == len(rows)
    if r.stderr.strip():
        info["ffprobe_stderr"] = r.stderr.strip()[-300:]
    return info
