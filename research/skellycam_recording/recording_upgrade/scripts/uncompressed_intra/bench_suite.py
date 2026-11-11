# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# PEP 723 header (standard library only) added 2026-11-09 so the 23:00 queue runs this with `uv run --script`.
"""TIMING SUITE DRIVER (quiet machine only): runs bench_intra.py cases one at a time, each in its own process.

  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_suite.py --group core_1080p
Groups: core_1080p, core_720p, bayer, gpu, pyav19 (runs bench_intra.py under `uv run --script` = PyAV 19.0.2).
Options: --frames N (default 300; codecs listed in SLOW get --slow-frames, default 90), --force (re-run cases whose
JSON already exists), --dry-run (print the commands only). Each case writes
results/uncompressed_intra/bench/<config>__<source>_<res>__t<threads>__pyav<ver>.json; afterwards run bench_summary.py.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
BENCH = HERE.parents[1] / "results" / "uncompressed_intra" / "bench"
VENV_PY = REPO / ".venv" / "Scripts" / "python.exe"

SLOW = {"jpeg2000_dwt53.mkv", "libx265_intra_lossless.mkv", "libvpx-vp9_intra_lossless.webm", "libvpx-vp9_intra_crf30.webm",
        "libsvtav1_intra_crf30_p10.mkv", "libsvtav1_intra_lossless.mkv", "libsvtav1_intra_lossless_p12.mkv", "jpegls.nut",
        "png.nut", "prores_ks_hq.mov"}
CORE = ["rawvideo.nut", "rawvideo.mkv", "ffv1_l1_g1.mkv", "ffv1_l3_s4_crc_g1.mkv", "ffv1_l3_s16_crc_g1.mkv",
        "ffv1_l3_s24_crc_g1.mkv", "ffv1_l3_s4_crc_range_g1.mkv", "ffv1_l3_s24_crc_range_g1.mkv", "ffvhuff_median.nut",
        "utvideo_median.avi", "magicyuv_median.avi", "jpeg2000_dwt53.mkv", "mjpeg_q2.mkv", "libsvtav1_intra_crf30_p10.mkv",
        "libsvtav1_intra_crf30_p12.mkv", "libvpx-vp9_intra_lossless.webm", "libvpx-vp9_intra_crf30.webm",
        "libx264_intra_qp0.mkv", "libx264_intra_crf18.mp4", "libx265_intra_lossless.mkv", "prores_ks_hq.mov", "dnxhd_dnxhr_hq.mov"]
CORE_720 = ["rawvideo.nut", "ffv1_l3_s4_crc_g1.mkv", "ffv1_l3_s24_crc_g1.mkv", "ffv1_l3_s24_crc_range_g1.mkv", "utvideo_median.avi",
            "magicyuv_median.avi", "mjpeg_q2.mkv", "libsvtav1_intra_crf30_p12.mkv", "libvpx-vp9_intra_lossless.webm",
            "libx264_intra_qp0.mkv"]
BAYER = ["rawvideo.nut", "ffv1_l3_s4_crc_g1.mkv", "ffv1_l3_s24_crc_g1.mkv", "ffv1_l3_s24_crc_range_g1.mkv", "ffvhuff_median.nut",
         "jpegls.nut", "jpeg2000_dwt53.mkv", "libx265_intra_lossless.mkv"]


def cases(group: str):
    if group == "core_1080p":
        for src in ("yuyv422", "nv12"):
            for c in CORE + (["rawvideo_yuv422p.nut"] if src == "yuyv422" else ["libsvtav1_intra_lossless_p12.mkv"]):
                for t in (1, 0):
                    yield ("venv", c, src, "1080p", t)
    elif group == "core_720p":
        for src in ("yuyv422", "nv12"):
            for c in CORE_720:
                for t in (1, 0):
                    yield ("venv", c, src, "720p", t)
    elif group == "bayer":
        for src in ("bayer12", "bayer12_quad", "bayer8", "bayer8_quad", "raw12_packed"):
            for c in BAYER:
                for t in (1, 0):
                    yield ("venv", c, src, "1080p", t)
    elif group == "gpu":
        for res in ("1080p", "720p"):
            for c, src in (("h264_nvenc_intra_lossless.mkv", "nv12"), ("hevc_nvenc_intra_lossless.mkv", "nv12"),
                           ("hevc_nvenc_intra_lossless.mkv", "p010le"), ("hevc_nvenc_intra_cq.mp4", "nv12"),
                           ("h264_nvenc_intra_lossless.mkv", "gray"), ("hevc_nvenc_intra_lossless.mkv", "bayer8")):
                yield ("venv", c, src, res, 1)
    elif group == "pyav19":
        for c, src in (("rawvideo.nut", "yuyv422"), ("ffv1_l3_s4_crc_g1.mkv", "yuyv422"), ("ffv1_l3_s24_crc_g1.mkv", "yuyv422"),
                       ("mjpeg_q2.mkv", "yuyv422"), ("libsvtav1_intra_crf30_p12.mkv", "nv12"),
                       ("ffv1_l4_experimental_s4_crc_g1.mkv", "bayer12"), ("ffv1_l3_s4_crc_g1.mkv", "bayer12_quad")):
            for t in (1, 0):
                yield ("uv", c, src, "1080p", t)
    else:
        raise SystemExit(f"unknown group {group}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True)
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--slow-frames", type=int, default=90)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--warmup-frames", type=int, default=20)
    ap.add_argument("--slow-warmup-frames", type=int, default=8)
    ap.add_argument("--sources", default="", help="comma list: only these sources")
    ap.add_argument("--configs", default="", help="comma list: only these config ids")
    ap.add_argument("--skip-configs", default="", help="comma list: drop these config ids")
    ap.add_argument("--interp", default="", choices=["", "uv"], help="uv: run every case under `uv run --script` (bench_intra.py PEP 723 header = PyAV 19.0.2) instead of the group default (added 2026-11-09)")
    ap.add_argument("--tag", default="", help="suffix passed to bench_intra.py --tag (result name ...__pyav<ver><tag>.json); the existence check uses it too, so tagged runs neither skip on nor overwrite untagged files (added 2026-11-09)")
    a = ap.parse_args()
    script = HERE / "bench_intra.py"
    todo = list(cases(a.group))
    if a.sources:
        todo = [x for x in todo if x[2] in a.sources.split(",")]
    if a.configs:
        todo = [x for x in todo if x[1] in a.configs.split(",")]
    if a.skip_configs:
        todo = [x for x in todo if x[1] not in a.skip_configs.split(",")]
    for i, (interp, c, src, res, t) in enumerate(todo, 1):
        interp = a.interp or interp
        ver = "19.0.2" if interp == "uv" else "18.0.0"
        jp = BENCH / f"{c}__{src}_{res}__t{t}__pyav{ver}{a.tag}.json"
        if jp.exists() and not a.force:
            print(f"[{i}/{len(todo)}] skip (exists) {jp.name}")
            continue
        n = a.slow_frames if c in SLOW else a.frames
        wu = a.slow_warmup_frames if c in SLOW else a.warmup_frames
        base = ["uv", "run", "--script", str(script)] if interp == "uv" else [str(VENV_PY), str(script)]
        cmd = base + ["--config", c, "--source", src, "--res", res, "--threads", str(t), "--frames", str(n), "--reps", str(a.reps), "--warmup-frames", str(wu)] + (["--tag", a.tag] if a.tag else [])
        print(f"[{i}/{len(todo)}]", " ".join(cmd), flush=True)
        if not a.dry_run:
            r = subprocess.run(cmd, cwd=REPO)
            if r.returncode != 0:
                print(f"  FAILED rc={r.returncode}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
