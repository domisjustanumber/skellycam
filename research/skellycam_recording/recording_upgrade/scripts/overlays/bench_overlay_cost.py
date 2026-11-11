# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6", "opencv-python==4.12.0.88", "msgspec==0.21.1", "psutil==7.2.2"]
# ///
# PEP 723 header added 2026-11-09 for the 23:00 bench queue (uv run --script; never the skellycam venv). No PyAV is
# imported here. The alpha_vp9_pipeline method pipes to the ffmpeg CLI, which is not the implementation under test
# (HANDOFF section 1 item 5): the queue leaves it out with --only.
"""BENCHMARK (run on a quiet machine, one bench at a time): per-frame cost of storing overlays as a separate layer
vs burning them into the image, plus bytes per hour.

Overlay cases (overlay_model.make_frames, deterministic):
  text      today's skellycam stamp only ("camera.id0.idx0.frN")
  skeleton  stamp + 33-point MediaPipe body (35 connections)
  charuco   stamp + 100-corner ChArUco board with per-corner labels + ArUco outlines + undetected list
  all       stamp + skeleton + charuco
Methods (each timed per frame with time.perf_counter_ns, single thread, file writes buffered, close() timed separately):
  sidecar_jsonl, sidecar_msgpack, sidecar_bin, sidecar_vtt   data-level sidecars (generate record + append)
  svg_per_frame, svg_single, ass                             render-level vector files (primitives + serialise + write)
  burnin_cv2                  cv2 drawing onto a decoded 8-bit BGR frame (copy of a real corpus frame), no codec
  burnin_cv2_jpeg_roundtrip   cv2.imdecode(camera JPEG) + burn-in + cv2.imencode(q=90): what burn-in costs when the
                              recording would otherwise store the camera's JPEG untouched (G1 passthrough)
  jpeg_roundtrip_only         cv2.imdecode + cv2.imencode(q=90) without drawing (baseline for the line above)
  alpha_render                rasterise the overlay to BGRA (two cv2 renders + matte), the input of an alpha video
  alpha_vp9_pipeline          alpha_render + piping BGRA to ffmpeg libvpx-vp9 yuva420p (wall time of the whole run / frames)
Resolutions: 1280x720 (corpus c930e_720p_flash) and 1920x1080 (corpus c930e_1080p; 19 frames, looped).

Output: research/skellycam_recording/recording_upgrade/results/overlays/bench/bench_overlay_cost_<UTC>.json
        (per method/case/res: median/p95/mean us per frame, close() us, bytes, bytes/frame, MB/hour at 30 fps)
Scratch files: <raw>/overlays/bench_scratch/ (deleted at the end unless --keep)

Run from repo root (full run ~10-20 min):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/bench_overlay_cost.py --frames 900 --repeats 3
Smoke test:
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/bench_overlay_cost.py --frames 20 --repeats 1 --smoke
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import overlay_model as M  # noqa: E402

RAW = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109")
SCR = RAW / "overlays" / "bench_scratch"
OUTDIR = HERE.parents[1] / "results" / "overlays" / "bench"
CORPUS = {(1280, 720): RAW / "corpus" / "c930e_720p_flash", (1920, 1080): RAW / "corpus" / "c930e_1080p"}


def stats(ns: list[int]) -> dict:
    us = sorted(x / 1000 for x in ns)
    return {"n": len(us), "median_us": round(us[len(us) // 2], 2), "p95_us": round(us[int(len(us) * 0.95) - 1 if len(us) > 1 else 0], 2),
            "mean_us": round(statistics.fmean(us), 2), "max_us": round(us[-1], 2)}


def nvsmi() -> str:
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu", "--format=csv,noheader"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return repr(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=900)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--smoke", action="store_true", help="tiny run; result file name gets _smoke")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--only", default="", help="comma list of methods to run (default all)")
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    SCR.mkdir(parents=True, exist_ok=True)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    res = {"script": "bench_overlay_cost.py", "utc": stamp, "args": vars(a), "host": platform.node(), "cpu": platform.processor(),
           "python": sys.version.split()[0], "opencv": cv2.__version__, "numpy": np.__version__, "nvidia_smi_before": nvsmi(),
           "cpu_count": os.cpu_count(), "results": []}
    try:
        import msgspec
        res["msgspec"] = msgspec.__version__
    except ImportError:
        pass

    def want(m):
        return not only or m in only

    for (w, h), cdir in CORPUS.items():
        jpgs = sorted(cdir.glob("frame_*.jpg"))
        jpeg_bytes = [p.read_bytes() for p in jpgs]
        decoded = [cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR) for b in jpeg_bytes]
        for kind in ("text", "skeleton", "charuco", "all"):
            frames = M.make_frames(a.frames, w, h, kind)
            hdr = M.header(w, h, 30.0, kind)
            prims_pre = None
            for rep in range(a.repeats):
                # ---- data-level sidecars
                for name, (Wr, _) in M.DATA_FORMATS.items():
                    meth = f"sidecar_{name}"
                    if not want(meth):
                        continue
                    p = SCR / f"{kind}_{h}{Wr.ext}"
                    wr = Wr(p, hdr)
                    t = []
                    for fd in frames:
                        t0 = time.perf_counter_ns()
                        wr.write(fd)
                        t.append(time.perf_counter_ns() - t0)
                    t0 = time.perf_counter_ns()
                    wr.close()
                    tc = time.perf_counter_ns() - t0
                    size = p.stat().st_size
                    res["results"].append({"method": meth, "kind": kind, "res": f"{w}x{h}", "rep": rep, **stats(t), "close_us": tc / 1000,
                                           "bytes": size, "bytes_per_frame": size / a.frames, "MB_per_hour_30fps": size / a.frames * 108000 / 1e6})
                # ---- render-level vector files (primitives are generated inside the timed region)
                for name, Wr in M.RENDER_FORMATS.items():
                    if not want(name):
                        continue
                    p = SCR / f"{kind}_{h}{Wr.ext}"
                    if p.is_dir():
                        shutil.rmtree(p)
                    wr = Wr(p, hdr)
                    t = []
                    for fd in frames:
                        t0 = time.perf_counter_ns()
                        wr.write(fd)
                        t.append(time.perf_counter_ns() - t0)
                    t0 = time.perf_counter_ns()
                    wr.close()
                    tc = time.perf_counter_ns() - t0
                    size = sum(f.stat().st_size for f in p.iterdir()) if p.is_dir() else p.stat().st_size
                    res["results"].append({"method": name, "kind": kind, "res": f"{w}x{h}", "rep": rep, **stats(t), "close_us": tc / 1000,
                                           "bytes": size, "bytes_per_frame": size / a.frames, "MB_per_hour_30fps": size / a.frames * 108000 / 1e6})
                # ---- burn-in
                if want("burnin_cv2"):
                    t = []
                    for i, fd in enumerate(frames):
                        img = decoded[i % len(decoded)].copy()  # copy outside the timed region
                        t0 = time.perf_counter_ns()
                        M.burn_in(img, M.primitives(fd, w, h))
                        t.append(time.perf_counter_ns() - t0)
                    res["results"].append({"method": "burnin_cv2", "kind": kind, "res": f"{w}x{h}", "rep": rep, **stats(t)})
                if want("burnin_cv2_jpeg_roundtrip"):
                    t, size = [], 0
                    for i, fd in enumerate(frames):
                        b = jpeg_bytes[i % len(jpeg_bytes)]
                        t0 = time.perf_counter_ns()
                        img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
                        M.burn_in(img, M.primitives(fd, w, h))
                        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
                        t.append(time.perf_counter_ns() - t0)
                        size += len(enc)
                    res["results"].append({"method": "burnin_cv2_jpeg_roundtrip", "kind": kind, "res": f"{w}x{h}", "rep": rep, **stats(t),
                                           "out_jpeg_bytes_per_frame": size / a.frames,
                                           "camera_jpeg_bytes_per_frame": statistics.fmean(len(jpeg_bytes[i % len(jpeg_bytes)]) for i in range(a.frames))})
                if want("alpha_render"):
                    t = []
                    for fd in frames:
                        t0 = time.perf_counter_ns()
                        M.render_rgba(M.primitives(fd, w, h), w, h)
                        t.append(time.perf_counter_ns() - t0)
                    res["results"].append({"method": "alpha_render", "kind": kind, "res": f"{w}x{h}", "rep": rep, **stats(t)})
                if want("alpha_vp9_pipeline"):
                    p = SCR / f"{kind}_{h}_alpha.webm"
                    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{w}x{h}", "-r", "30",
                           "-i", "-", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-crf", "32", "-b:v", "0", "-deadline", "realtime",
                           "-cpu-used", "8", "-row-mt", "1", "-auto-alt-ref", "0", "-g", "30", str(p)]
                    t0 = time.perf_counter_ns()
                    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
                    for fd in frames:
                        pr.stdin.write(M.render_rgba(M.primitives(fd, w, h), w, h).tobytes())
                    pr.stdin.close()
                    rc = pr.wait()
                    wall = time.perf_counter_ns() - t0
                    size = p.stat().st_size if p.exists() else 0
                    res["results"].append({"method": "alpha_vp9_pipeline", "kind": kind, "res": f"{w}x{h}", "rep": rep, "rc": rc,
                                           "wall_us_per_frame": wall / 1000 / a.frames, "bytes": size, "bytes_per_frame": size / a.frames,
                                           "MB_per_hour_30fps": size / a.frames * 108000 / 1e6})
            print(f"{w}x{h} {kind} done", flush=True)
        if want("jpeg_roundtrip_only"):
            for rep in range(a.repeats):
                t = []
                for i in range(a.frames):
                    b = jpeg_bytes[i % len(jpeg_bytes)]
                    t0 = time.perf_counter_ns()
                    img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
                    cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    t.append(time.perf_counter_ns() - t0)
                res["results"].append({"method": "jpeg_roundtrip_only", "kind": "-", "res": f"{w}x{h}", "rep": rep, **stats(t)})
    res["nvidia_smi_after"] = nvsmi()
    out = OUTDIR / f"bench_overlay_cost_{stamp}{'_smoke' if a.smoke else ''}.json"
    out.write_text(json.dumps(res, indent=1))
    if not a.keep:
        shutil.rmtree(SCR, ignore_errors=True)
    # compact table: median of per-rep medians
    agg = {}
    for r in res["results"]:
        k = (r["res"], r["kind"], r["method"])
        agg.setdefault(k, []).append(r.get("median_us", r.get("wall_us_per_frame")))
    print("| res | kind | method | median us/frame (median of reps) |\n|---|---|---|---|")
    for k, v in sorted(agg.items()):
        print(f"| {k[0]} | {k[1]} | {k[2]} | {statistics.median(v):.1f} |")
    print("wrote", out)


if __name__ == "__main__":
    main()
