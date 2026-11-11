"""Bench-protocol quiet check (read-only): 10 s typeperf total CPU, top-10 instantaneous CPU processes (psutil, 2 s),
nvidia-smi encoder sessions + GPU utilization, free disk on C:, Defender real-time status (Get-MpComputerStatus).
Output: results/write_throughput/bench/sysinfo/quiet_<ts>[_tag].json. Added by the bench runner 2026-11-09.
Run (repo root): .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/quiet_check.py [--tag x]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wt_common as W  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    import psutil
    tp = subprocess.run(["typeperf", r"\Processor(_Total)\% Processor Time", "-si", "1", "-sc", "10"],
                        capture_output=True, text=True).stdout
    vals = []
    for row in csv.reader(io.StringIO(tp)):
        if len(row) == 2:
            try:
                vals.append(float(row[1]))
            except ValueError:
                pass
    procs = list(psutil.process_iter(["name", "pid"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except Exception:  # noqa: BLE001
            pass
    time.sleep(2.0)
    top = []
    for p in procs:
        try:
            top.append((round(p.cpu_percent(None), 1), p.info["name"], p.info["pid"]))
        except Exception:  # noqa: BLE001
            pass
    top = [t for t in sorted(top, reverse=True) if t[1] != "System Idle Process"][:10]
    nv = subprocess.run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu", "--format=csv"],
                        capture_output=True, text=True).stdout.strip()
    dfd = subprocess.run(["pwsh", "-NoProfile", "-Command",
                          "Get-MpComputerStatus | Select-Object RealTimeProtectionEnabled,OnAccessProtectionEnabled,"
                          "AMRunningMode | ConvertTo-Json"], capture_output=True, text=True).stdout
    try:
        dfd = json.loads(dfd)
    except Exception:  # noqa: BLE001
        pass
    res = dict(timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"), typeperf_total_cpu_pct=vals,
               typeperf_avg=sum(vals) / len(vals) if vals else None, top10_cpu_pct_of_one_cpu_2s=top,
               logical_cpus=psutil.cpu_count(), nvidia_smi=nv, free_bytes_C=shutil.disk_usage("C:/").free,
               defender=dfd)
    out = W.BENCH_RESULTS / "sysinfo" / f"quiet_{time.strftime('%Y%m%dT%H%M%S')}{a.tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(dict(avg=res["typeperf_avg"], top=top[:5], nv=nv, free_gb=res["free_bytes_C"] / 1e9)))
    print("wrote", out)


if __name__ == "__main__":
    main()
