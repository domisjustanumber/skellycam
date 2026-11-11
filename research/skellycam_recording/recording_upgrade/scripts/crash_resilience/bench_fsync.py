# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "psutil==7.2.2", "opencv-python-headless==4.12.0.88"]
# ///
# PEP 723 header added 2026-11-09 for the 23:00 bench queue: runs under PyAV 19.0.2 via `uv run --script`
# (child processes started with sys.executable inherit this environment).
"""BENCH (run on a quiet machine): cost of durability policies when appending camera frames + timestamp records.

Per policy: append N camera JPEGs (c930e_720p_flash, ~57 KB, corpus looped) to one data file plus one 72-byte
timestamp record per frame to a sidecar, paced as fast as possible (throughput) - and per-frame latency of the
write+durability step.
  none            Python buffered writes only
  flush           flush() data + sidecar after every frame (survives a process kill)
  fsync_every_K   flush every frame, os.fsync (Windows: _commit -> FlushFileBuffers) data + sidecar every K frames,
                  K in 1, 10, 30, 300
  sidecar_fsync_1 flush data every frame, fsync ONLY the small sidecar every frame
  mkv_fp_fsync_K  PyAV Matroska writer over a Python file object, flush_packets=1, os.fsync every K frames (K 1, 30)
Reported: wall s, CPU s, per-frame latency p50/p99/max (us), MB/s.

usage:
  python bench_fsync.py --frames 3000 --repeats 3
  (smoke: --frames 30 --repeats 1 --out-name smoke)
writes results/crash_resilience/bench/fsync[_<out-name>].json ; data files under MEDIA/bench_tmp (deleted)
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import struct
import sys
import time
import zlib
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_cr as cc  # noqa: E402

REC = struct.Struct("<8qII")


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def run_policy(policy: str, jp: list[bytes], d: Path) -> dict:
    data_p = d / "data.bin"
    side_p = d / "side.bin"
    for p in (data_p, side_p, d / "data.mkv"):
        cc.rm(p)
    lat = []
    t0w = time.perf_counter()
    t0c = time.process_time()
    if policy.startswith("mkv_fp_fsync_"):
        import av
        k = int(policy.rsplit("_", 1)[1])
        f = open(d / "data.mkv", "wb")
        side = open(side_p, "wb")
        c = av.open(f, "w", format="matroska", options={"flush_packets": "1"})
        st = c.add_stream("mjpeg", rate=cc.FPS)
        w, h = cc.corpus_dims()
        st.width, st.height, st.pix_fmt = w, h, "yuvj422p"
        for i, b in enumerate(jp):
            t = time.perf_counter_ns()
            pk = av.Packet(b)
            pk.stream = st
            pk.time_base = Fraction(1, 1000)
            pk.pts = pk.dts = round(i * 1000 / cc.FPS)
            pk.is_keyframe = True
            c.mux(pk)
            side.write(REC.pack(i, *([t] * 7), 0, 0))
            side.flush()
            if (i + 1) % k == 0:
                f.flush()
                os.fsync(f.fileno())
                os.fsync(side.fileno())
            lat.append(time.perf_counter_ns() - t)
        c.close()
        f.close()
        side.close()
        size = (d / "data.mkv").stat().st_size
    else:
        k = int(policy.rsplit("_", 1)[1]) if policy.startswith("fsync_every_") else None
        fd = open(data_p, "wb")
        fs = open(side_p, "wb")
        for i, b in enumerate(jp):
            t = time.perf_counter_ns()
            fd.write(b)
            body = struct.pack("<8q", i, *([t] * 7))
            fs.write(REC.pack(i, *([t] * 7), zlib.crc32(body), 0x53435453))
            if policy != "none":
                fd.flush()
                fs.flush()
            if k and (i + 1) % k == 0:
                os.fsync(fd.fileno())
                os.fsync(fs.fileno())
            if policy == "sidecar_fsync_1":
                os.fsync(fs.fileno())
            lat.append(time.perf_counter_ns() - t)
        fd.close()
        fs.close()
        size = data_p.stat().st_size
    wall = time.perf_counter() - t0w
    cpu = time.process_time() - t0c
    for p in (data_p, side_p, d / "data.mkv"):
        cc.rm(p)
    return {"wall_s": wall, "cpu_s": cpu, "bytes": size, "MB_per_s": size / wall / 1e6,
            "lat_us_p50": pct(lat, 0.5) / 1e3, "lat_us_p99": pct(lat, 0.99) / 1e3, "lat_us_max": max(lat) / 1e3}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=3000)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out-name", default="")
    a = ap.parse_args()
    cc.BENCH.mkdir(parents=True, exist_ok=True)
    d = cc.MEDIA / "bench_tmp" / "fsync"
    d.mkdir(parents=True, exist_ok=True)
    base = cc.load_jpegs(cc.DEFAULT_SET, 891)
    jp = [base[i % len(base)] for i in range(a.frames)]
    policies = ["none", "flush", "fsync_every_1", "fsync_every_10", "fsync_every_30", "fsync_every_300",
                "sidecar_fsync_1", "mkv_fp_fsync_1", "mkv_fp_fsync_30"]
    res = {"env": cc.env_versions(), "frames": a.frames, "repeats": a.repeats, "drive": "C:",
           "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": []}
    out = cc.BENCH / f"fsync{'_' + a.out_name if a.out_name else ''}.json"
    for pol in policies:
        reps = [run_policy(pol, jp, d) for _ in range(a.repeats)]
        row = {"policy": pol, "repeats": reps}
        for k in ("wall_s", "cpu_s", "MB_per_s", "lat_us_p50", "lat_us_p99", "lat_us_max"):
            row[k + "_median"] = statistics.median(r[k] for r in reps)
        res["results"].append(row)
        print(pol, {k: round(v, 2) for k, v in row.items() if k.endswith("_median")}, flush=True)
        out.write_text(json.dumps(res, indent=1))
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
