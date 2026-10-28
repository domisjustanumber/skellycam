"""Shared helpers for the baseline frame-pipeline benchmarks.

Everything SkellyCam-specific is imported from the real `skellycam` package (HEAD 23ccbf20).
Nothing in the skellycam source tree is modified; any instrumentation is done by
wrapping objects inside the benchmark process only.
"""
from __future__ import annotations

import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
import sys as _fp_sys; _fp_sys.path.insert(0, str(Path(__file__).resolve().parents[1])); from fp_paths import results_dir as _results_dir  # noqa: E402,E702
RESULTS = _results_dir(HERE)
RESULTS.mkdir(exist_ok=True)
SCRATCH_TMP = Path(tempfile.gettempdir()) / "skellycam_frame_pipeline_tmp" / "bench_tmp"  # same root as prototypes/ and cpp/
SCRATCH_TMP.mkdir(parents=True, exist_ok=True)

SIZES = {"720p": (720, 1280), "1080p": (1080, 1920)}  # (height, width), BGR uint8 x3


def make_config(cam_idx: int, height: int, width: int, framerate: float = 60.0, **kw):
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera.config.image_resolution import ImageResolution
    return CameraConfig(camera_id=str(cam_idx), camera_index=cam_idx,
                        resolution=ImageResolution(height=height, width=width),
                        framerate=framerate, **kw)


def make_frame_recarray(config, timebase_mapping=None) -> np.recarray:
    """Same construction as skellycam create_initial_frame_rec_array (which needs a CameraGroupIPC)."""
    from skellycam.core.types.frame_dtype_factories import create_frame_dtype
    from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
    tbm = timebase_mapping or TimebaseMapping()
    fr = np.recarray(1, dtype=create_frame_dtype(config))
    fr.frame_metadata.camera_info[0] = config.to_frame_camera_info()
    fr.frame_metadata.frame_number[0] = -1
    fr.frame_metadata.timebase_mapping[0] = tbm.to_numpy_record_array()
    fr.image[0] = np.zeros((config.resolution.height, config.resolution.width, 3), np.uint8) + config.camera_index
    return fr


def synthetic_frames(height: int, width: int, n: int = 60, seed: int = 0, noise: int = 8) -> np.ndarray:
    """n distinct BGR frames: moving diagonal gradient + moving box + uniform noise (+-noise).
    Moderately compressible, closer to a real scene than pure noise or a flat image."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width]
    out = np.empty((n, height, width, 3), np.uint8)
    for i in range(n):
        g = ((xx + yy + 8 * i) % 256).astype(np.int16)
        img = np.stack([g, (g * 2) % 256, 255 - g], axis=-1)
        bx = (i * width // n) % (width - width // 6)
        img[height // 3: height // 3 + height // 4, bx: bx + width // 6] = (40, 200, 90)
        if noise:
            img = img + rng.integers(-noise, noise + 1, img.shape, dtype=np.int16)
        out[i] = np.clip(img, 0, 255).astype(np.uint8)
    return out


def stats_ms(samples_ns) -> dict:
    a = np.asarray(samples_ns, dtype=np.float64) / 1e6
    if a.size == 0:
        return {"n": 0}
    return {"n": int(a.size), "median_ms": float(np.median(a)), "mean_ms": float(a.mean()),
            "p99_ms": float(np.percentile(a, 99)), "min_ms": float(a.min()), "max_ms": float(a.max())}


def write_json(name: str, obj) -> Path:
    p = RESULTS / name
    p.write_text(json.dumps(obj, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    return p


def write_text(name: str, text: str) -> Path:
    p = RESULTS / name
    p.write_text(text, encoding="utf-8")
    return p


def env_summary() -> dict:
    import cv2
    d = {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
         "numpy": np.__version__, "opencv": cv2.__version__, "cpu_count": os.cpu_count(),
         "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        import psutil
        d["psutil"] = psutil.__version__
        d["ram_total_gb"] = psutil.virtual_memory().total / 1e9
        d["system_cpu_pct_1s_before_run"] = psutil.cpu_percent(interval=1.0)
        others = []
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if p.info["name"] and p.info["name"].lower().startswith("python") and p.pid != os.getpid():
                    others.append(" ".join(p.info["cmdline"] or [])[:160])
            except Exception:
                pass
        d["other_python_processes_at_start"] = others
    except Exception:
        pass
    try:
        d["skellycam_head"] = subprocess.check_output(
            ["git", "-C", str(HERE.parents[2]), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        pass
    return d
