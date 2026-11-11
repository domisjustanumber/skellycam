# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "opencv-python==4.12.0.88"]
# ///
# PEP 723 header added 2026-11-09 for the 23:00 bench queue: runs under PyAV 19.0.2 via `uv run --script`
# (replaces the skellycam-venv / PyAV 18 command of the old manifest; python_integration FINDINGS section 5).
"""BENCHMARK (quiet machine only): cost of the prototype recorder (recwriter.py) in the skellycam venv.

Phases (all on real camera JPEGs from the corpus, looped; files go to the raw media folder and are deleted):
  A write_cost   per-call RecordingWriter.write() time for mkv / mp4f (real PTS) / avi (index PTS), plus a
                 folder-of-JPEGs baseline (one file per frame + the same sidecar), at 720p (c922) and 1080p (c922,
                 19 frames looped), N frames each, unthreaded, flush per frame (fsync off and fsync every 30).
  B threaded     5 cameras x paced 30 and 60 fps for D seconds: the "camera loop" thread only calls
                 RecorderThread.submit(); reports submit() cost, max queue depth, drops, and whether every file
                 round-trips byte-exact afterwards.
  C open_cost    time to open (cv2 CAP_FFMPEG, PyAV) and read CAP_PROP_FRAME_COUNT on a long file
                 (default 18,000 frames = 10 min at 30 fps, 720p) for mkv vs mp4f: fragmented MP4 has to walk
                 every fragment at open, MKV uses Cues.

Full run (~15-25 min; ~3 GB temporary disk):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/python_integration/bench_recwriter.py --tag quiet1
Smoke test (seconds; do not report its numbers):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/python_integration/bench_recwriter.py --tag smoke --quick
Writes research/skellycam_recording/recording_upgrade/results/python_integration/bench/recwriter_<tag>.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import struct
import sys
import threading
import time
import zlib
from pathlib import Path

import av
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import recwriter as rw  # noqa: E402

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
TMP = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/bench_tmp")
OUT = Path(__file__).resolve().parents[2] / "results/python_integration/bench"


def stats(t):
    a = np.array(t, dtype=np.float64) / 1e6
    return {"n": int(a.size), "median_ms": round(float(np.median(a)), 4), "mean_ms": round(float(a.mean()), 4),
            "p99_ms": round(float(np.percentile(a, 99)), 4), "p999_ms": round(float(np.percentile(a, 99.9)), 4),
            "max_ms": round(float(a.max()), 4)}


class FolderWriter:
    """Baseline: one .jpg file per frame + the same binary sidecar record."""

    def __init__(self, stem: Path, fsync_every=0):
        self.dir = stem.with_name(stem.name + ".jpgdir")
        self.dir.mkdir(parents=True)
        self.bin = open(stem.with_name(stem.name + ".frames.bin"), "wb")
        self.count, self.fsync_every = 0, fsync_every

    def write(self, b, fn, ts):
        with open(self.dir / f"frame_{self.count:08d}.jpg", "wb") as f:
            f.write(b)
        body = struct.pack(rw.RECORD_BODY_FMT, fn, ts, self.count, len(b), zlib.crc32(b), 0, self.count, 0)
        self.bin.write(body + struct.pack("<I", zlib.crc32(body)))
        self.bin.flush()
        self.count += 1
        if self.fsync_every and self.count % self.fsync_every == 0:
            os.fsync(self.bin.fileno())

    def close(self):
        self.bin.close()


def load(name, n):
    fr = [f.read_bytes() for f in sorted((CORPUS / name).glob("frame_*.jpg"))]
    return [fr[i % len(fr)] for i in range(n)]


def phase_a(quick):
    res = {}
    n = 60 if quick else 3000
    for label, name, w, h in [("720p", "c922_720p_flash", 1280, 720), ("1080p", "c922_1080p", 1920, 1080)]:
        frames = load(name, n)
        for kind in ["mkv", "mp4f", "avi", "folder"]:
            for fsync_every in (0, 30):
                d = TMP / f"a_{label}_{kind}_{fsync_every}"
                shutil.rmtree(d, ignore_errors=True)
                d.mkdir(parents=True)
                stem = d / "cam"
                if kind == "folder":
                    wr = FolderWriter(stem, fsync_every)
                else:
                    wr = rw.RecordingWriter(stem, w, h, container=kind, pts_mode="index" if kind == "avi" else "real",
                                            fsync_every=fsync_every)
                t = []
                pc = time.perf_counter_ns
                t0 = pc()
                for i, b in enumerate(frames):
                    s = pc()
                    wr.write(b, i, t0 + i * 33_333_333)
                    t.append(pc() - s)
                s = pc()
                wr.close()
                close_ms = (pc() - s) / 1e6
                res[f"{label}/{kind}/fsync{fsync_every}"] = {"write": stats(t), "close_ms": round(close_ms, 3),
                                                            "frames": n}
                shutil.rmtree(d, ignore_errors=True)
                print("A", label, kind, fsync_every, res[f"{label}/{kind}/fsync{fsync_every}"]["write"], flush=True)
    return res


def phase_b(quick):
    res = {}
    dur = 2.0 if quick else 60.0
    frames = load("c922_720p_flash", 893)
    for fps in (30, 60):
        d = TMP / f"b_{fps}"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        recs = [rw.RecorderThread(rw.RecordingWriter(d / f"cam{k}", 1280, 720, container="mkv"), maxsize=256,
                                  policy="drop") for k in range(5)]
        sub = [[] for _ in range(5)]
        period = 1e9 / fps
        pc = time.perf_counter_ns
        t0 = pc()
        i = 0
        lateness = []
        while pc() - t0 < dur * 1e9:
            target = t0 + int(i * period)
            while pc() < target:
                time.sleep(0.0005)
            lateness.append(pc() - target)
            for k in range(5):  # one lockstep "multiframe": every camera submits frame i
                s = pc()
                recs[k].submit(frames[i % len(frames)], i, pc())
                sub[k].append(pc() - s)
            i += 1
        mans = [r.stop() for r in recs]
        ok = []
        for k in range(5):
            pk = list(rw.RecordingReader(d / f"cam{k}.mkv").packets())
            ok.append(len(pk) == mans[k]["frames"] and all(b == frames[j % len(frames)] for j, (_, b, _, _) in enumerate(pk)))
        res[f"5cam_{fps}fps"] = {"multiframes": i, "submit": stats([x for s in sub for x in s]),
                                 "producer_lateness": stats(lateness),
                                 "dropped": [m["dropped"] for m in mans], "max_queue_depth": [m["max_queue_depth"] for m in mans],
                                 "frames_written": [m["frames"] for m in mans], "all_bytes_exact": all(ok),
                                 "thread_errors": [m["thread_error"] for m in mans]}
        print("B", fps, res[f"5cam_{fps}fps"]["submit"], res[f"5cam_{fps}fps"]["dropped"], flush=True)
        shutil.rmtree(d, ignore_errors=True)
    return res


def phase_c(quick):
    res = {}
    n = 300 if quick else 18000
    frames = load("c922_720p_flash", n)
    for kind in ("mkv", "mp4f"):
        d = TMP / f"c_{kind}"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        wr = rw.RecordingWriter(d / "long", 1280, 720, container=kind)
        t0 = 10**13
        for i, b in enumerate(frames):
            wr.write(b, i, t0 + i * 33_333_333)
        wr.close()
        path = wr.video_path
        r = {"frames": n, "bytes": path.stat().st_size}
        for rep in range(3):
            s = time.perf_counter_ns()
            cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
            cnt = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            ok, _ = cap.read()
            r.setdefault("cv2_open_count_first_read_ms", []).append(round((time.perf_counter_ns() - s) / 1e6, 2))
            s = time.perf_counter_ns()
            cap.set(cv2.CAP_PROP_POS_FRAMES, n // 2)
            ok2, _ = cap.read()
            r.setdefault("cv2_seek_mid_ms", []).append(round((time.perf_counter_ns() - s) / 1e6, 2))
            cap.release()
            s = time.perf_counter_ns()
            with av.open(str(path)) as c:
                next(c.demux(c.streams.video[0]))
            r.setdefault("pyav_open_first_packet_ms", []).append(round((time.perf_counter_ns() - s) / 1e6, 2))
        r["cv2_frame_count_prop"] = cnt
        res[kind] = r
        print("C", kind, r, flush=True)
        shutil.rmtree(d, ignore_errors=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--phases", default="a,b,c")
    args = ap.parse_args()
    shutil.rmtree(TMP, ignore_errors=True)
    out = {"env": {"python": sys.version.split()[0], "platform": platform.platform(), "av": av.__version__,
                   "opencv": cv2.__version__, "quick": args.quick, "target_disk": str(TMP),
                   "free_bytes_start": shutil.disk_usage("C:/").free, "started_unix": time.time()}}
    ph = args.phases.split(",")
    if "a" in ph:
        out["a_write_cost"] = phase_a(args.quick)
    if "b" in ph:
        out["b_threaded"] = phase_b(args.quick)
    if "c" in ph:
        out["c_open_cost"] = phase_c(args.quick)
    out["env"]["finished_unix"] = time.time()
    shutil.rmtree(TMP, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"recwriter_{args.tag}.json"
    p.write_text(json.dumps(out, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
