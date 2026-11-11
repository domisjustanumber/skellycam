# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "psutil==7.2.2", "opencv-python-headless==4.12.0.88"]
# ///
# PEP 723 header + PyAV 19 interpreter fix added 2026-11-09 for the 23:00 bench queue (crash_resilience FINDINGS
# section 5: bench_repair.py:38 started writer_child.py with cc.VENV_PY = the PyAV 18 skellycam venv). The writer child
# now runs under sys.executable (this uv PyAV 19.0.2 environment); --methods selects repair methods (the queue omits
# the ffmpeg CLI rows: the CLI is not the implementation under test, HANDOFF section 1 item 5).
"""BENCH (run on a quiet machine): repair (remux to a finalized file) time per GB of unfinalized recording.

Builds unfinalized recordings of about --gb GB each by killing a writer before close (writer_child.py, mode
drained:N; MJPEG passthrough from c930e_720p_flash looped, ~57 KB/frame), for: mkv+fp, fmp4_every+fp, mp4 (plain,
expected unrepairable), rawidx. Then times each repair method on each, R times:
  ffmpeg_copy_mkv   ffmpeg -c copy -> .mkv          (CLI, ffmpeg 9.0.2 on PATH)
  ffmpeg_copy_mp4   ffmpeg -c copy -> .mp4 (+faststart not used)
  pyav_copy_mkv     common_cr.remux_pyav -> .mkv  (PyAV of the running interpreter: 19.0.2 under uv run --script)
  resumable_repair  resumable_recorder.ResumableRecorder._repair_segment (MKV inputs only)
Reported: seconds, seconds per GB of input, output frames (ffprobe), first-run vs repeat (the first read may come from
disk, repeats from the OS file cache - no cache drop is attempted; record free RAM).

usage:
  python bench_repair.py --gb 1 --repeats 3
  (smoke: --gb 0.02 --repeats 1 --out-name smoke)
writes results/crash_resilience/bench/repair[_<out-name>].json ; recordings under MEDIA/bench_tmp/repair (deleted
at the end unless --keep)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_cr as cc  # noqa: E402

AVG_JPEG = 56759  # corpus index.json bytes_median for c930e_720p_flash


def make_recording(c: str, n: int, d: Path) -> Path:
    out = cc.out_path(d, "mjpeg", c, f"drained{n}")
    cc.rm(out)
    pr = subprocess.Popen([sys.executable, str(cc.SCRIPTS / "writer_child.py"), "mjpeg", c, str(out), str(n),
                           f"drained:{n}"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    for line in pr.stdout:
        if line.strip() == "IDLE":
            pr.kill()
            break
    pr.wait()
    return out


def free_ram_mb():
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"], capture_output=True, text=True)
        return int(r.stdout.strip()) // 1024
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gb", type=float, default=1.0)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out-name", default="")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--methods", default="", help="comma list: only these repair methods (default all)")
    a = ap.parse_args()
    from resumable_recorder import ResumableRecorder
    n = max(30, int(a.gb * 1e9 / AVG_JPEG))
    d = cc.MEDIA / "bench_tmp" / "repair"
    d.mkdir(parents=True, exist_ok=True)
    cc.BENCH.mkdir(parents=True, exist_ok=True)
    res = {"env": cc.env_versions(), "writer_child_interpreter": sys.executable, "methods_arg": a.methods, "frames": n, "target_gb": a.gb, "free_ram_mb_start": free_ram_mb(),
           "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": []}
    out_json = cc.BENCH / f"repair{'_' + a.out_name if a.out_name else ''}.json"
    for c in ("mkv+fp", "fmp4_every+fp", "mp4", "rawidx"):
        src = make_recording(c, n, d)
        src_file = src / "frames.mjpeg" if c == "rawidx" else src
        fmt_in = "mjpeg" if c == "rawidx" else None
        gb = src_file.stat().st_size / 1e9
        methods = ["ffmpeg_copy_mkv", "ffmpeg_copy_mp4", "pyav_copy_mkv"] + (["resumable_repair"] if c.startswith("mkv") else [])
        if a.methods:
            methods = [m for m in methods if m in a.methods.split(",")]
        for m in methods:
            for r in range(a.repeats):
                dst = d / f"rep_{m}.{'mp4' if m.endswith('mp4') else 'mkv'}"
                cc.rm(dst)
                if m == "resumable_repair":
                    work = d / "seg_copy"
                    cc.rm(work)
                    work.mkdir()
                    seg = work / "seg_00000.mkv"
                    shutil.copyfile(src_file, seg)
                    rr = object.__new__(ResumableRecorder)
                    rr.payload = "mjpeg"
                    t0 = time.perf_counter()
                    nfr = rr._repair_segment(seg)
                    dt = time.perf_counter() - t0
                    frames = cc.ffprobe_count(str(seg))["frames"] if seg.exists() else 0
                    cc.rm(work)
                    extra = {"repair_returned_frames": nfr}
                else:
                    t0 = time.perf_counter()
                    if m.startswith("ffmpeg"):
                        info = cc.remux_ffmpeg(str(src_file), str(dst), fmt_in)
                    else:
                        info = cc.remux_pyav(str(src_file), str(dst), fmt_in)
                    dt = time.perf_counter() - t0
                    frames = cc.ffprobe_count(str(dst))["frames"] if dst.exists() and dst.stat().st_size else 0
                    extra = {"info": info}
                    cc.rm(dst)
                row = {"container": c, "method": m, "repeat": r, "input_gb": gb, "seconds": dt,
                       "seconds_per_gb": dt / gb if gb else None, "output_frames": frames, "input_frames_written": n, **extra}
                res["results"].append(row)
                print(c, m, r, round(dt, 3), frames, flush=True)
                out_json.write_text(json.dumps(res, indent=1, default=str))
        if not a.keep:
            cc.rm(src)
    res["free_ram_mb_end"] = free_ram_mb()
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    out_json.write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
