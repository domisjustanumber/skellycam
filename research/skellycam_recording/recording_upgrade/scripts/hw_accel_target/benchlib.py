"""Helpers for hw_accel_target benchmarks (adapted from scripts/gpu_encode/benchlib.py).

Adds the background-load record required for the 23:00 run (HANDOFF.md section 5):
  - 10 s `typeperf "\\Processor(_Total)\\% Processor Time" -si 1 -sc 10` (mean/max),
  - top processes by CPU seconds used during those same 10 s (psutil),
  - nvidia-smi encoder.stats.sessionCount / utilization.gpu,
  - flag `load_over_15pct` when the typeperf mean is above 15 %.
Every benchmark writes one JSON per run into results/hw_accel_target/bench/ (UTC stamp in the name).
Run benchmarks one at a time on a quiet machine.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
import time
from pathlib import Path

import av
import numpy as np

from common import BENCH, CORPUS, YUY2_SETS, run

QUERY = ("timestamp,encoder.stats.sessionCount,encoder.stats.averageFps,utilization.gpu,utilization.encoder,"
         "utilization.decoder,clocks.video,power.draw")


class GpuSampler:
    """Polls nvidia-smi every `period_ms` in a background thread (one nvidia-smi -lms process)."""

    def __init__(self, period_ms: int = 500):
        self.period_ms = period_ms
        self.rows: list[str] = []
        self._p: subprocess.Popen | None = None

    def __enter__(self):
        try:
            self._p = subprocess.Popen(["nvidia-smi", f"--query-gpu={QUERY}", "--format=csv,noheader,nounits",
                                        f"-lms={self.period_ms}"], stdout=subprocess.PIPE, text=True)
            threading.Thread(target=self._read, daemon=True).start()
        except Exception:  # noqa: BLE001
            self._p = None
        return self

    def _read(self):
        assert self._p and self._p.stdout
        for ln in self._p.stdout:
            self.rows.append(ln.strip())

    def __exit__(self, *a):
        if self._p:
            self._p.terminate()
            try:
                self._p.wait(timeout=5)
            except Exception:  # noqa: BLE001
                self._p.kill()

    def summary(self) -> dict:
        cols = QUERY.split(",")
        vals: dict[str, list[float]] = {c: [] for c in cols[1:]}
        for r in self.rows:
            parts = [p.strip() for p in r.split(",")]
            if len(parts) != len(cols):
                continue
            for c, v in zip(cols[1:], parts[1:]):
                try:
                    vals[c].append(float(v))
                except ValueError:
                    pass
        out: dict = {"samples": len(self.rows)}
        for c, v in vals.items():
            if v:
                out[c] = {"mean": round(sum(v) / len(v), 2), "max": max(v)}
        return out


def background_load(seconds: int = 10) -> dict:
    """10 s typeperf total CPU + top processes over the same window + nvidia-smi encoder sessions."""
    out: dict = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        import psutil  # noqa: PLC0415
        t0 = {}
        for p in psutil.process_iter(["pid", "name"]):
            try:
                ct = p.cpu_times()
                t0[p.pid] = (p.info["name"], ct.user + ct.system)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        psutil = None
    try:
        r = run(["typeperf", r"\Processor(_Total)\% Processor Time", "-si", "1", "-sc", str(seconds)],
                timeout=seconds + 30)
        vals = []
        for ln in r.stdout.splitlines():
            parts = ln.strip().split('","')
            if len(parts) == 2:
                try:
                    vals.append(float(parts[1].strip('"')))
                except ValueError:
                    pass
        out["typeperf_cpu_total_pct"] = {"samples": vals, "mean": round(float(np.mean(vals)), 2) if vals else None,
                                         "max": max(vals) if vals else None}
        out["load_over_15pct"] = bool(vals) and float(np.mean(vals)) > 15.0
    except Exception as e:  # noqa: BLE001
        out["typeperf_error"] = repr(e)
    if psutil:
        rows = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                ct = p.cpu_times()
                if p.pid in t0 and p.pid != 0:  # pid 0 = System Idle Process
                    rows.append((round(ct.user + ct.system - t0[p.pid][1], 2), p.pid, p.info["name"]))
            except Exception:  # noqa: BLE001
                pass
        rows.sort(reverse=True)
        out["top_processes_cpu_s_in_window"] = [{"cpu_s": c, "pid": pid, "name": n} for c, pid, n in rows[:12]]
    try:
        out["nvidia_smi"] = run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu,"
                                 "utilization.encoder", "--format=csv,noheader"], timeout=20).stdout.strip()
    except Exception as e:  # noqa: BLE001
        out["nvidia_smi_error"] = repr(e)
    return out


def snapshot() -> dict:
    s = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "machine": platform.node(),
         "cpu_count": os.cpu_count(), "python": platform.python_version(), "pyav": av.__version__,
         "libavcodec": ".".join(map(str, av.library_versions["libavcodec"]))}
    try:
        s["nvidia_smi"] = run(["nvidia-smi", "--query-gpu=name,driver_version,encoder.stats.sessionCount,"
                               "utilization.gpu,utilization.encoder", "--format=csv,noheader"]).stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    try:
        r = run(["powershell", "-NoProfile", "-Command",
                 "Get-PnpDevice -Class Display | ForEach-Object { \"$($_.Status)|$($_.Present)|$($_.FriendlyName)\" }"],
                timeout=30)
        s["display_devices"] = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001
        pass
    return s


def write(name: str, data: dict) -> Path:
    BENCH.mkdir(parents=True, exist_ok=True)
    p = BENCH / f"{name}_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    p.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    print("wrote", p)
    return p


# ---------------------------------------------------------------- inputs (PyAV only)
def yuy2_frames_bytes(size: str) -> list[bytes]:
    """Real YUY2 1080p frames (both corpus sets, 16 frames). 720p = the same frames scaled by PyAV swscale
    (yuyv422 1920x1080 -> yuyv422 1280x720, default interpolation); labelled 'derived' in results."""
    raws = []
    for setname in YUY2_SETS.values():
        raws += [p.read_bytes() for p in sorted((CORPUS / setname).glob("frame_*.yuy2"))]
    if size == "1080p":
        return raws
    out = []
    for b in raws:
        f = frame_from_packed(b, "yuyv422", 1920, 1080).reformat(width=1280, height=720, format="yuyv422")
        out.append(packed_bytes(f))
    return out


def frame_from_packed(buf: bytes, fmt: str, w: int, h: int) -> av.VideoFrame:
    f = av.VideoFrame(w, h, fmt)
    p = f.planes[0]
    row = w * 2
    if p.line_size == row:
        p.update(buf)
    else:
        dst = np.frombuffer(p, np.uint8).reshape(h, p.line_size)
        dst[:, :row] = np.frombuffer(buf, np.uint8).reshape(h, row)
    return f


def packed_bytes(f: av.VideoFrame) -> bytes:
    p = f.planes[0]
    row = f.width * 2
    return np.frombuffer(p, np.uint8).reshape(f.height, p.line_size)[:, :row].tobytes()


def nv12_arrays(size: str) -> list[np.ndarray]:
    """NV12 numpy arrays (H*3/2, W) converted by PyAV swscale from the YUY2 frames above."""
    w, h = (1920, 1080) if size == "1080p" else (1280, 720)
    out = []
    for b in yuy2_frames_bytes(size):
        g = frame_from_packed(b, "yuyv422", w, h).reformat(format="nv12")
        y = np.frombuffer(g.planes[0], np.uint8).reshape(h, g.planes[0].line_size)[:, :w]
        uv = np.frombuffer(g.planes[1], np.uint8).reshape(h // 2, g.planes[1].line_size)[:, :w]
        out.append(np.ascontiguousarray(np.vstack([y, uv])))
    return out


def jpeg_list(size: str) -> list[bytes]:
    """Real camera 4:2:2 JPEG bytes: 720p c930e_720p_flash (first 120), 1080p c930e_1080p + c922_1080p (38)."""
    if size == "720p":
        return [p.read_bytes() for p in sorted((CORPUS / "c930e_720p_flash").glob("frame_*.jpg"))[:120]]
    return [p.read_bytes() for s in ("c930e_1080p", "c922_1080p") for p in sorted((CORPUS / s).glob("frame_*.jpg"))]
