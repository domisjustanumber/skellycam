# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "psutil==7.2.2", "opencv-python==4.12.0.88"]
# ///
# PEP 723 header added 2026-11-09 for the 23:00 bench queue: runs under PyAV 19.0.2 via `uv run --script`
# (child processes started with sys.executable inherit this environment).
"""Run a named set of bench_write.py cells one after another (resumable), then summarize.

Each cell is a separate bench_write.py process; its JSON goes to results/write_throughput/bench/<set>/<cell>.json.
Cells whose JSON already exists are skipped (re-run with --force). Run on a quiet machine, one set at a time.

Sets (cells, approximate minutes at the default durations):
  core      thread model, camera MJPEG: {files, files_subdirs, files_fsync, append, append_fsync1s, mkv_flush,
            fmp4_frame_flush, mkvseg10} x {1,4,8,16} cams x {720p30,1080p30,1080p60}, 30 s                 (96, ~70)
  models    {files, append, mkv_flush} x {inloop, inloop_lockstep, thread, process, process_shared} x {4,16}
            cams, 1080p60, 60 s                                                                         (30, ~40)
  variants  {mkv, mkv_flush_cluster1, fmp4_frame, fmp4_1s, fmp4_1s_flush, fmp4_hybrid, files_subdirs_fsync}
            x {4,16} cams, 1080p60, thread, 30 s                                                        (14, ~10)
  intra     FFV1 1080p payload: {files, append, mkv_flush, fmp4_frame_flush} x {1,4,8,16} cams, 1080p30,
            thread, 30 s                                                                                (16, ~12)
  long      {files, append, mkv_flush} x 16 cams x 1080p60, thread, 600 s (SSD cache, Defender)        (3, ~33)
  repeat    {files, mkv_flush} x 16 cams x 1080p60 thread 60 s, 3 repetitions (run-to-run spread)      (6, ~8)
  smoke     2 tiny cells (2 s) to check the toolchain                                                   (2, ~1)

Example (repo root):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/run_matrix.py --set core
"""
from __future__ import annotations

import argparse
import itertools
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wt_common as W  # noqa: E402

CORE_WRITERS = ["files", "files_subdirs", "files_fsync", "append", "append_fsync1s", "mkv_flush", "fmp4_frame_flush",
                "mkvseg10"]


def cells(name: str):
    """Yield dicts of bench_write.py arguments."""
    if name == "core":
        for p, c, w in itertools.product(["720p30", "1080p30", "1080p60"], [1, 4, 8, 16], CORE_WRITERS):
            yield dict(writer=w, cams=c, profile=p, model="thread", duration=30)
    elif name == "models":
        for c, w, m in itertools.product([4, 16], ["files", "append", "mkv_flush"],
                                         ["inloop", "inloop_lockstep", "thread", "process", "process_shared"]):
            yield dict(writer=w, cams=c, profile="1080p60", model=m, duration=60)
    elif name == "variants":
        for c, w in itertools.product([4, 16], ["mkv", "mkv_flush_cluster1", "fmp4_frame", "fmp4_1s", "fmp4_1s_flush",
                                                "fmp4_hybrid", "files_subdirs_fsync"]):
            yield dict(writer=w, cams=c, profile="1080p60", model="thread", duration=30)
    elif name == "intra":
        for c, w in itertools.product([1, 4, 8, 16], ["files", "append", "mkv_flush", "fmp4_frame_flush"]):
            yield dict(writer=w, cams=c, profile="1080p30", model="thread", duration=30, payload="ffv1")
    elif name == "long":
        for w in ["files", "append", "mkv_flush"]:
            yield dict(writer=w, cams=16, profile="1080p60", model="thread", duration=600)
    elif name == "repeat":
        for r, w in itertools.product([1, 2, 3], ["files", "mkv_flush"]):
            yield dict(writer=w, cams=16, profile="1080p60", model="thread", duration=60, rep=r)
    elif name == "smoke":
        yield dict(writer="files", cams=2, profile="720p30", model="thread", duration=2)
        yield dict(writer="mkv", cams=2, profile="720p30", model="process", duration=2)
    else:
        raise SystemExit(f"unknown set {name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--duration-scale", type=float, default=1.0, help="multiply every cell's duration")
    # added by the bench runner 2026-11-09 to fit the 35-minute wall-time cap (subset + repetitions)
    ap.add_argument("--duration", type=int, default=None, help="override every cell's duration (s)")
    ap.add_argument("--writers", default=None, help="comma list: keep only these writers")
    ap.add_argument("--cams", default=None, help="comma list: keep only these camera counts")
    ap.add_argument("--profiles", default=None, help="comma list: keep only these profiles")
    ap.add_argument("--models", default=None, help="comma list: keep only these models")
    ap.add_argument("--reps", type=int, default=None, help="run every kept cell this many times (rep1..repN)")
    ap.add_argument("--outdir-name", default=None, help="results subfolder (default: the set name)")
    a = ap.parse_args()
    outdir = W.BENCH_RESULTS / (a.outdir_name or a.set)
    outdir.mkdir(parents=True, exist_ok=True)
    log = outdir / "run_log.txt"
    todo = list(cells(a.set))
    keep = lambda v, opt: opt is None or str(v) in opt.split(",")  # noqa: E731
    todo = [c for c in todo if keep(c["writer"], a.writers) and keep(c["cams"], a.cams)
            and keep(c["profile"], a.profiles) and keep(c["model"], a.models)]
    if a.duration is not None:
        for c in todo:
            c["duration"] = a.duration
    if a.reps:
        # interleave repetitions (rep1 of every cell, then rep2, ...) so slow drift shows up as spread
        todo = [dict(c, rep=r) for r in range(1, a.reps + 1) for c in todo]
    for i, c in enumerate(todo):
        dur = max(1, int(c["duration"] * a.duration_scale))
        payload = c.get("payload", "mjpeg")
        cell = f"{c['writer']}__{c['cams']}cam__{c['profile']}__{payload}__{c['model']}__{dur}s" + (
            f"__rep{c['rep']}" if "rep" in c else "")
        jo = outdir / f"{cell}.json"
        if jo.exists() and not a.force:
            continue
        cmd = [sys.executable, str(HERE / "bench_write.py"), "--writer", c["writer"], "--cams", str(c["cams"]),
               "--profile", c["profile"], "--model", c["model"], "--duration", str(dur), "--payload", payload,
               "--json-out", str(jo)]
        t = time.perf_counter()
        p = subprocess.run(cmd, capture_output=True, text=True)
        with open(log, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} [{i + 1}/{len(todo)}] rc={p.returncode} "
                    f"{time.perf_counter() - t:.0f}s {cell}\n")
            if p.returncode:
                f.write(p.stdout[-2000:] + "\n" + p.stderr[-4000:] + "\n")
        print(f"[{i + 1}/{len(todo)}] rc={p.returncode} {cell}", flush=True)
    subprocess.run([sys.executable, str(HERE / "summarize_bench.py")])


if __name__ == "__main__":
    main()
