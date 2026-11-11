# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "psutil==7.2.2", "opencv-python==4.12.0.88"]
# ///
# PEP 723 header added 2026-11-09 for the 23:00 bench queue: runs under PyAV 19.0.2 via `uv run --script`
# (same pins as run_matrix.py; never the skellycam venv).
"""After-recording usability costs (goal G5): folder of JPEGs vs one file.

For each format it builds an N-frame single-camera recording from the corpus (looped), then measures:
  build_s            unpaced write of N frames by one writer (upper bound of one writer, no camera pacing)
  open_meta_s        open + metadata only (folder: nothing to open; containers: av.open + stream info)
  frame_table_s      time to know every frame's location (folder: scandir + sort; append: read .idx;
                     containers: demux every packet header via PyAV = full file pass)
  seq_read_s         read the payload bytes of all N frames in order
  random_read_s      read K random frames by index (containers: seek + demux to the exact pts), with a
                     correctness check against the expected payload bytes (wrong = functional failure)
  first_image_s      bytes -> decoded BGR image for frame 0 (cv2.imdecode for files/append; PyAV for containers)
  copy_*_s           copy the recording on the same volume: shutil.copytree / shutil.copy2 (CopyFile2), and
                     robocopy /E /MT:8 if --robocopy; then the copy is deleted (delete time recorded)
  delete_s           delete the original
All reads are WARM-cache (the file was just written; the OS standby list cannot be flushed without admin).
Media: --out-dir (default MEDIA/usability), deleted at the end. Result JSON: --json-out
(default results/write_throughput/bench/usability/usability_<N>.json).

Example (1-hour-equivalent single camera at 30 fps = 108000 frames, ~6.1 GB per format):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/bench_usability.py --frames 108000 --robocopy
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wt_common as W  # noqa: E402


def alloc_bytes(paths):
    return sum((p.stat().st_size + 4095) // 4096 * 4096 for p in paths)


def tree_files(d: Path):
    return [p for p in d.rglob("*") if p.is_file()]


def timed(fn):
    t = time.perf_counter()
    r = fn()
    return time.perf_counter() - t, r


def build(fmt: str, d: Path, src: list[bytes], n: int):
    pl = dict(packets=src, codec="mjpeg", w=1280, h=720, pix_fmt="yuvj422p", template=None)
    wr = W.make_writer(fmt, d, 0, pl, 30)
    period = int(1e9 / 30)
    for i in range(n):
        wr.write(i, src[i % len(src)], i * period)
    wr.close()


def measure(fmt: str, d: Path, src: list[bytes], n: int, k: int, seed: int) -> dict:
    import av
    import cv2
    import numpy as np
    kind = W.WRITER_VARIANTS[fmt][0]
    r = {}
    rnd = random.Random(seed)
    picks = [rnd.randrange(n) for _ in range(k)]
    if kind == "files":
        root = d / "cam00"
        r["open_meta_s"] = 0.0

        def table():
            out = []
            stack = [root]
            while stack:
                for e in os.scandir(stack.pop()):
                    if e.is_dir():
                        stack.append(e.path)
                    elif e.name.startswith("frame_"):
                        out.append(e.path)
            out.sort(key=lambda p: os.path.basename(p))
            return out
        r["frame_table_s"], paths = timed(table)
        r["frames_found"] = len(paths)

        def seq():
            tot = 0
            for p in paths:
                with open(p, "rb") as f:
                    tot += len(f.read())
            return tot
        r["seq_read_s"], r["seq_bytes"] = timed(seq)

        def rand():
            bad = 0
            for i in picks:
                with open(paths[i], "rb") as f:
                    bad += f.read() != src[i % len(src)]
            return bad
        r["random_read_s"], r["random_wrong"] = timed(rand)
        r["first_image_s"], _ = timed(lambda: cv2.imdecode(np.frombuffer(open(paths[0], "rb").read(), np.uint8),
                                                           cv2.IMREAD_COLOR))
        return r
    if kind == "append":
        blob = d / "cam00.mjpeg"
        r["open_meta_s"] = 0.0
        r["frame_table_s"], recs = timed(lambda: W.read_idx(d / "cam00.idx"))
        r["frames_found"] = len(recs)

        def seq():
            tot = 0
            with open(blob, "rb") as f:
                for (_, _, o, m) in recs:
                    tot += len(f.read(m))
            return tot
        r["seq_read_s"], r["seq_bytes"] = timed(seq)

        def rand():
            bad = 0
            with open(blob, "rb") as f:
                for i in picks:
                    _, _, o, m = recs[i]
                    f.seek(o)
                    bad += f.read(m) != src[i % len(src)]
            return bad
        r["random_read_s"], r["random_wrong"] = timed(rand)

        def first():
            with open(blob, "rb") as f:
                f.seek(recs[0][2])
                return cv2.imdecode(np.frombuffer(f.read(recs[0][3]), np.uint8), cv2.IMREAD_COLOR)
        r["first_image_s"], _ = timed(first)
        return r
    files = sorted(p for p in d.iterdir() if p.name.startswith("cam00") and p.suffix in (".mkv", ".mp4"))
    path = files[0]

    def meta():
        with av.open(str(path)) as c:
            st = c.streams.video[0]
            return dict(stream_frames=st.frames, duration=float(c.duration / 1e6) if c.duration else None)
    r["open_meta_s"], r["meta"] = timed(meta)

    def table():
        pts = []
        with av.open(str(path)) as c:
            st = c.streams.video[0]
            tb = st.time_base
            for p in c.demux(st):
                if p.size:
                    pts.append(p.pts)
        return pts, tb
    r["frame_table_s"], (pts, tb) = timed(table)
    r["frames_found"] = len(pts)

    def seq():
        tot = 0
        with av.open(str(path)) as c:
            for p in c.demux(c.streams.video[0]):
                tot += p.size
        return tot
    r["seq_read_s"], r["seq_bytes"] = timed(seq)

    def rand():
        bad = 0
        with av.open(str(path)) as c:
            st = c.streams.video[0]
            for i in picks:
                target = pts[i]
                c.seek(target, stream=st, backward=True, any_frame=False)
                got = None
                for p in c.demux(st):
                    if p.pts is None or p.size == 0:
                        continue
                    if p.pts >= target:
                        got = bytes(p) if p.pts == target else None
                        break
                bad += got != src[i % len(src)]
        return bad
    r["random_read_s"], r["random_wrong"] = timed(rand)

    def first():
        with av.open(str(path)) as c:
            for fr in c.decode(video=0):
                return fr.to_ndarray(format="bgr24")
    r["first_image_s"], _ = timed(first)
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", type=int, default=108000)
    ap.add_argument("--set", default="c930e_720p_flash")
    ap.add_argument("--formats", default="files,files_subdirs,append,mkv_flush,fmp4_frame_flush")
    ap.add_argument("--random-reads", type=int, default=1000)
    ap.add_argument("--robocopy", action="store_true")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--out-dir", default=str(W.MEDIA / "usability"))
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args()
    src = W.load_mjpeg_set(a.set)
    base = Path(a.out_dir)
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)
    est = sum(len(s) for s in src) / len(src) * a.frames
    if shutil.disk_usage(base).free < 3 * est + 50e9:
        raise SystemExit("not enough free space")
    res = dict(env=W.env_versions(), frames=a.frames, set=a.set, payload_bytes_est=est, warm_cache=True,
               started=time.strftime("%Y-%m-%dT%H:%M:%S"), formats={})
    for fmt in a.formats.split(","):
        d = base / fmt
        row = {}
        row["build_s"], _ = timed(lambda: build(fmt, d, src, a.frames))
        allf = tree_files(d)
        row["files"] = len(allf)
        row["bytes"] = sum(p.stat().st_size for p in allf)
        row["alloc_bytes_4k_clusters"] = alloc_bytes(allf)
        row.update(measure(fmt, d, src, a.frames, a.random_reads, a.seed))
        # copies on the same volume
        dst = base / f"{fmt}_copy"
        if W.WRITER_VARIANTS[fmt][0] == "files":
            row["copy_python_s"], _ = timed(lambda: shutil.copytree(d, dst))
            row["copy_python_method"] = "shutil.copytree (per-file shutil.copy2 -> CopyFile2)"
        else:
            def cp():
                dst.mkdir()
                for p in allf:
                    shutil.copy2(p, dst / p.name)
            row["copy_python_s"], _ = timed(cp)
            row["copy_python_method"] = "shutil.copy2 per file (CopyFile2)"
        row["copy_verified_files"] = len(tree_files(dst))
        row["delete_copy_s"], _ = timed(lambda: shutil.rmtree(dst))
        if a.robocopy:
            dst2 = base / f"{fmt}_robocopy"

            def rc():
                return subprocess.run(["robocopy", str(d), str(dst2), "/E", "/MT:8", "/NFL", "/NDL", "/NJH", "/NJS",
                                       "/NP", "/R:0", "/W:0"], capture_output=True, text=True).returncode
            row["copy_robocopy_mt8_s"], row["robocopy_rc"] = timed(rc)
            row["robocopy_verified_files"] = len(tree_files(dst2))
            row["delete_robocopy_copy_s"], _ = timed(lambda: shutil.rmtree(dst2))
        row["delete_s"], _ = timed(lambda: shutil.rmtree(d))
        res["formats"][fmt] = row
        print(fmt, json.dumps({k: v for k, v in row.items() if k in ("files", "frames_found", "random_wrong",
                                                                     "copy_verified_files")}), flush=True)
    shutil.rmtree(base, ignore_errors=True)
    jo = Path(a.json_out) if a.json_out else W.BENCH_RESULTS / "usability" / f"usability_{a.frames}.json"
    jo.parent.mkdir(parents=True, exist_ok=True)
    jo.write_text(json.dumps(res, indent=1, default=str))
    print("wrote", jo)


if __name__ == "__main__":
    main()
