# /// script
# requires-python = "==3.12.*"
# dependencies = ["jpeglib==1.0.2", "numpy==2.2.6", "PyTurboJPEG==2.6.1"]
# ///
"""BENCHMARK (run only on a quiet machine): per-frame cost of lossless JPEG rotation (tj3Transform via ctypes, options 0,
the call skellycam-rust jpeg_transform.rs makes) on real camera JPEGs, single thread, one process.

Run (repo root):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_rotate.py ^
     --lib C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/jpeg_passthrough/ljt321/bin/turbojpeg.dll
  (libjpeg-turbo 3.2.1: https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.2.1/libjpeg-turbo-3.2.1-vc-x64.exe,
   extract with "C:/Program Files/7-Zip/7z.exe" x -o<dir> <exe>)
Options: --frames 1000 (per set/op) --reps 5
Writes research/skellycam_recording/recording_upgrade/results/jpeg_passthrough/bench/bench_rotate_<UTC time>.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import rotate_check as R  # noqa: E402  (reuses its ctypes tj3Transform wrapper; rotate_check imports jpeglib + turbojpeg)

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
OUT = Path(__file__).resolve().parents[2] / "results/jpeg_passthrough/bench"
SETS = {"720p": "c930e_720p_flash", "1080p": "c922_1080p"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", required=True)
    ap.add_argument("--frames", type=int, default=1000)
    ap.add_argument("--reps", type=int, default=5)
    a = ap.parse_args()
    tj = R.TJ(a.lib)
    res = {"meta": {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "lib": a.lib, "cpu_count": os.cpu_count(),
                    "args": vars(a), "python": sys.version,
                    "lib_sha256": __import__("hashlib").sha256(Path(a.lib).read_bytes()).hexdigest(),
                    "platform": __import__("platform").platform()}, "summary": {}, "runs": []}
    for res_name, s in SETS.items():
        base = [f.read_bytes() for f in sorted((CORPUS / s).glob("frame_*.jpg"))]
        frames = [base[i % len(base)] for i in range(a.frames)]
        for op in ("rot90", "rot180", "rot270"):
            cpu, wall = [], []
            for rep in range(a.reps):
                c0, t0 = time.process_time(), time.perf_counter()
                for fb in frames:
                    out, err = tj.transform(fb, R.TJXOP[op], 0)
                    if out is None:
                        raise RuntimeError(err)
                c1, t1 = time.process_time(), time.perf_counter()
                cpu.append(1e6 * (c1 - c0) / len(frames))
                wall.append(1e6 * (t1 - t0) / len(frames))
                res["runs"].append({"res": res_name, "op": op, "rep": rep, "cpu_us_per_frame": cpu[-1], "wall_us_per_frame": wall[-1]})
            res["summary"][f"{res_name}|{op}"] = {"cpu_us_per_frame_median": statistics.median(cpu), "wall_us_per_frame_median": statistics.median(wall),
                                                  "wall_min": min(wall), "wall_max": max(wall), "reps": a.reps}
            print(res_name, op, res["summary"][f"{res_name}|{op}"], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"bench_rotate_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    p.write_text(json.dumps(res, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
