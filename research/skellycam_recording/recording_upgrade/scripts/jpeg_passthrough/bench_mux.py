# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "psutil==7.2.2"]
# ///
# PEP 723 header added 2026-11-09 for the 23:00 bench queue: runs under PyAV 19.0.2 via `uv run --script`
# (child processes started with sys.executable inherit this environment).
"""BENCHMARK (run only on a quiet machine): per-container mux cost of camera JPEG passthrough, 1 camera per process.

For each (container, resolution, rep) a fresh worker process preloads real camera JPEGs into RAM (720p: c930e_720p_flash,
891 frames looped; 1080p: c922_1080p, 19 frames looped), then writes N frames with VFR timestamps (real c930e_720p_flash
intervals, looped) as fast as possible and reports:
  cpu_us_per_frame_mux   process CPU (time.process_time, user+sys) in the mux loop / N
  wall_us_per_frame_mux  wall time in the mux loop / N
  cpu_ms_close, wall_ms_close  container close (trailer / index write), optional fsync
Baselines: pkt_only (av.Packet creation + attribute sets, no mux), raw_sidecar (python write + 20-byte index record),
jpg_folder (one file per frame, open/write/close).
Output files go to --dir (default C:/Users/Dom/Documents/skellycam-raw/.../jpeg_passthrough/bench_tmp) and are deleted.

Run (repo root, ~10 min with defaults):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_mux.py
Options: --containers a,b  --res 720p,1080p  --frames 3000  --reps 5  --fsync  --tag name
Writes research/skellycam_recording/recording_upgrade/results/jpeg_passthrough/bench/bench_mux_<tag>_<UTC time>.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402
import jp_io as io  # noqa: E402

DEFAULT_CONTAINERS = ["pkt_only", "mkv", "mp4", "fmp4_1s", "fmp4_perframe", "mov", "avi_tb_rate", "nut", "mjpeg_raw_mux",
                      "raw_sidecar", "jpg_folder"]
RES = {"720p": ("c930e_720p_flash", 1280, 720), "1080p": ("c922_1080p", 1920, 1080)}


def worker(container: str, res: str, n: int, outdir: Path, fsync: bool) -> dict:
    name, w, h = RES[res]
    frames = C.load_looped(name, n)
    ts = C.jitter_timestamps_ns(n)
    us = [t // 1000 for t in ts]
    outdir.mkdir(parents=True, exist_ok=True)
    r = {"container": container, "res": res, "frames": n, "payload_bytes": sum(map(len, frames)), "pid": os.getpid()}
    if container in ("raw_sidecar", "jpg_folder"):
        c0, t0 = time.process_time(), time.perf_counter()
        if container == "raw_sidecar":
            p = outdir / "bench.mjpeg"
            f = open(p, "wb")  # noqa: SIM115
            fi = open(p.with_suffix(".idx"), "wb")  # noqa: SIM115
            off = 0
            for fb, t in zip(frames, ts):
                f.write(fb)
                fi.write(io.IDX_REC.pack(off, len(fb), t))
                off += len(fb)
        else:
            d = outdir / "frames"
            d.mkdir(exist_ok=True)
            for k, fb in enumerate(frames):
                with open(d / f"frame_{k:06d}.jpg", "wb") as fo:
                    fo.write(fb)
        c1, t1 = time.process_time(), time.perf_counter()
        if container == "raw_sidecar":
            if fsync:
                f.flush()
                os.fsync(f.fileno())
                fi.flush()
                os.fsync(fi.fileno())
            f.close()
            fi.close()
        c2, t2 = time.process_time(), time.perf_counter()
    else:
        import av
        if container == "pkt_only":
            st = None
            c = None
        else:
            fmt, _, opts = io.CONTAINERS[container][:3]
            stb = io.CONTAINERS[container][3] if len(io.CONTAINERS[container]) > 3 else None
            p = outdir / f"bench{io.CONTAINERS[container][1]}"
            c = av.open(str(p), "w", format=fmt, options=dict(opts))  # native avio (a Python file object would route writes through Python)
            st = c.add_mux_stream("mjpeg", rate=30, width=w, height=h)
            if stb == "rate":
                st.time_base = Fraction(1, 30)
            elif stb == "us":  # added 2026-11-09 (FINDINGS section 5, change 2): explicit 1/1e6 stream time base
                st.time_base = Fraction(1, 1_000_000)
        cfr = container == "avi_tb_rate"
        tb = Fraction(1, 30) if cfr else Fraction(1, 1_000_000)
        c0, t0 = time.process_time(), time.perf_counter()
        for k, fb in enumerate(frames):
            pkt = av.Packet(fb)
            pkt.time_base = tb
            pkt.pts = pkt.dts = k if cfr else us[k]
            pkt.is_keyframe = True
            if c is not None:
                pkt.stream = st
                c.mux(pkt)
        c1, t1 = time.process_time(), time.perf_counter()
        if c is not None:
            c.close()
            if fsync:  # FlushFileBuffers needs a writable handle: reopen r+b after close
                with open(p, "r+b") as fobj:
                    os.fsync(fobj.fileno())
        c2, t2 = time.process_time(), time.perf_counter()
    r.update({"cpu_us_per_frame_mux": 1e6 * (c1 - c0) / n, "wall_us_per_frame_mux": 1e6 * (t1 - t0) / n,
              "cpu_ms_close": 1e3 * (c2 - c1), "wall_ms_close": 1e3 * (t2 - t1),
              "bytes_on_disk": sum(f.stat().st_size for f in outdir.rglob("*") if f.is_file())})
    shutil.rmtree(outdir, ignore_errors=True)
    return r


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        _, _, cont, res, n, outdir, fs = sys.argv
        print("RESULT " + json.dumps(worker(cont, res, int(n), Path(outdir), fs == "1")))
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--containers", default=",".join(DEFAULT_CONTAINERS))
    ap.add_argument("--res", default="720p,1080p")
    ap.add_argument("--frames", type=int, default=3000)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--fsync", action="store_true")
    ap.add_argument("--dir", default=str(C.MEDIA / "bench_tmp"))
    ap.add_argument("--tag", default="default")
    a = ap.parse_args()
    import av
    meta = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "python": sys.version, "pyav": av.__version__,
            "pyav_ffmpeg_libs": {k: ".".join(map(str, v)) for k, v in av.library_versions.items()},
            "machine": platform.node(), "cpu_count": os.cpu_count(), "args": vars(a),
            "note": "1 camera per process; worker processes run sequentially; output dir on C:"}
    try:
        import psutil
        meta["cpu_percent_before_1s"] = psutil.cpu_percent(interval=1.0)
    except Exception:  # noqa: BLE001
        pass
    runs = []
    for res in a.res.split(","):
        for cont in a.containers.split(","):
            for rep in range(a.reps):
                od = Path(a.dir) / f"{cont}_{res}_{rep}"
                p = subprocess.run([sys.executable, __file__, "--worker", cont, res, str(a.frames), str(od), "1" if a.fsync else "0"],
                                   capture_output=True, text=True)
                line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT ")), None)
                if line is None:
                    runs.append({"container": cont, "res": res, "rep": rep, "error": p.stderr[-400:]})
                    print(cont, res, rep, "ERROR", p.stderr[-200:], flush=True)
                    continue
                r = json.loads(line[7:])
                r["rep"] = rep
                runs.append(r)
                print(f"{res} {cont} rep{rep}: cpu {r['cpu_us_per_frame_mux']:.1f} us/frame, wall {r['wall_us_per_frame_mux']:.1f} us/frame, close {r['wall_ms_close']:.1f} ms", flush=True)
    summary = {}
    for res in a.res.split(","):
        for cont in a.containers.split(","):
            rs = [r for r in runs if r.get("res") == res and r.get("container") == cont and "error" not in r]
            if rs:
                summary[f"{res}|{cont}"] = {k: {"median": statistics.median(r[k] for r in rs), "min": min(r[k] for r in rs), "max": max(r[k] for r in rs)}
                                            for k in ("cpu_us_per_frame_mux", "wall_us_per_frame_mux", "cpu_ms_close", "wall_ms_close")}
                summary[f"{res}|{cont}"]["reps"] = len(rs)
                summary[f"{res}|{cont}"]["bytes_on_disk"] = rs[0]["bytes_on_disk"]
                summary[f"{res}|{cont}"]["payload_bytes"] = rs[0]["payload_bytes"]
    out = C.BENCH_RESULTS / f"bench_mux_{a.tag}_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    C.write_json(out, {"meta": meta, "summary": summary, "runs": runs})
    print("wrote", out)


if __name__ == "__main__":
    main()
