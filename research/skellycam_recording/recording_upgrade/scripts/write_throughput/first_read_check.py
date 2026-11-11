# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "psutil==7.2.2", "opencv-python==4.12.0.88"]
# ///
# PEP 723 header added 2026-11-09 for the 23:00 bench queue: runs under PyAV 19.0.2 via `uv run --script`
# (child processes started with sys.executable inherit this environment).
"""Follow-up to usability_27000 (files seq read 116 s vs random 0.05 s): is the first read of freshly written frame
files slow, and does MsMpEng.exe (Defender engine) CPU rise during it? Writes N corpus JPEGs as files, reads them all
twice in order, recording wall time and MsMpEng CPU seconds per pass; same for one append file. Media under
MEDIA/first_read (deleted). Added by the bench runner 2026-11-09.
Run (repo root): .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/first_read_check.py --frames 3000
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wt_common as W  # noqa: E402
from bench_write import msmpeng_cpu  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=3000)
    a = ap.parse_args()
    src = W.load_mjpeg_set("c930e_720p_flash")
    base = W.MEDIA / "first_read"
    shutil.rmtree(base, ignore_errors=True)
    (base / "files").mkdir(parents=True)
    paths = []
    for i in range(a.frames):
        p = base / "files" / f"frame_{i:06d}.jpg"
        p.write_bytes(src[i % len(src)])
        paths.append(p)
    blob = base / "append.mjpeg"
    with open(blob, "wb", buffering=0) as f:
        for i in range(a.frames):
            f.write(src[i % len(src)])
    res = dict(env=W.env_versions(), frames=a.frames, started=time.strftime("%Y-%m-%dT%H:%M:%S"), passes=[])
    for kind in ("files", "append"):
        for pas in (1, 2):
            m0, t0 = msmpeng_cpu(), time.perf_counter()
            tot = 0
            if kind == "files":
                for p in paths:
                    with open(p, "rb") as f:
                        tot += len(f.read())
            else:
                with open(blob, "rb") as f:
                    while chunk := f.read(1 << 20):
                        tot += len(chunk)
            dt, m1 = time.perf_counter() - t0, msmpeng_cpu()
            row = dict(kind=kind, pass_=pas, wall_s=dt, bytes=tot,
                       msmpeng_cpu_s=(m1 - m0) if isinstance(m0, float) and isinstance(m1, float) else None)
            res["passes"].append(row)
            print(row, flush=True)
    shutil.rmtree(base, ignore_errors=True)
    out = W.BENCH_RESULTS / "usability" / f"first_read_check_{a.frames}.json"
    out.write_text(json.dumps(res, indent=1, default=str))
    print("wrote", out)


if __name__ == "__main__":
    main()
