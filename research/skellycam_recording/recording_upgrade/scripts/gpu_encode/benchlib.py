"""Helpers for gpu_encode benchmarks: nvidia-smi sampler, system snapshot, JSON writer.

All benchmark scripts write one JSON per run into results/gpu_encode/bench/ (name includes a UTC stamp).
They must be run one at a time on a quiet machine (see NOTES.md, Benchmark manifest).
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
import time
from pathlib import Path

from common import BENCH, FFMPEG, run

QUERY = ("timestamp,encoder.stats.sessionCount,encoder.stats.averageFps,utilization.gpu,utilization.encoder,"
         "utilization.decoder,clocks.video,power.draw")


class GpuSampler:
    """Polls nvidia-smi every `period` s in a background thread (nvidia-smi -lms keeps one process)."""

    def __init__(self, period_ms: int = 500):
        self.period_ms = period_ms
        self.rows: list[str] = []
        self._p: subprocess.Popen | None = None
        self._t: threading.Thread | None = None

    def __enter__(self):
        try:
            self._p = subprocess.Popen(["nvidia-smi", f"--query-gpu={QUERY}", "--format=csv,noheader,nounits",
                                        f"-lms={self.period_ms}"], stdout=subprocess.PIPE, text=True)
            self._t = threading.Thread(target=self._read, daemon=True)
            self._t.start()
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
        out = {"samples": len(self.rows)}
        for c, v in vals.items():
            if v:
                out[c] = {"mean": round(sum(v) / len(v), 2), "max": max(v)}
        return out


def snapshot() -> dict:
    s = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "machine": platform.node(),
         "cpu_count": os.cpu_count(), "python": platform.python_version()}
    try:
        s["ffmpeg"] = run([FFMPEG, "-hide_banner", "-version"]).stdout.splitlines()[0]
    except Exception:  # noqa: BLE001
        pass
    try:
        s["nvidia_smi"] = run(["nvidia-smi", "--query-gpu=name,driver_version,encoder.stats.sessionCount,"
                               "utilization.gpu,utilization.encoder", "--format=csv,noheader"]).stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    try:
        import psutil  # noqa: PLC0415
        s["cpu_percent_1s_before"] = psutil.cpu_percent(interval=1.0)
    except Exception:  # noqa: BLE001
        pass
    return s


def write(name: str, data: dict) -> Path:
    BENCH.mkdir(parents=True, exist_ok=True)
    p = BENCH / f"{name}_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    p.write_text(json.dumps(data, indent=1))
    print("wrote", p)
    return p
