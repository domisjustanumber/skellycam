# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "scipy==1.16.2", "simplejpeg==1.9.0",
#                 "nvidia-nvimgcodec-cu12[nvjpeg]==0.10.0.9"]
# ///
"""FUNCTIONAL rate-quality sweep of intra-only encode paths (no timing is recorded or reported).

For each (path, input class, knob value): encode every source frame, decode back with the PyAV 19.0.2 software
decoder, verify intra-only (H.264/HEVC: every VCL NAL is IDR, decoder has_b_frames == 0, every decoded frame is a
key frame, frame count matches), and compute bytes/frame, PSNR-Y, SSIM-Y, PSNR-YUV (vs the 4:2:2 source and vs the
frame fed). Details of inputs, ranges and metrics: iclib.py docstrings.

Run from the repo root (resumable: points already in the raw JSON are skipped):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/sweep.py \
      --paths jpeg_turbo_422,jpeg_turbo_420 --inputs yuy2_1080p,yuy2_720p,mjpeg_720p,mjpeg_1080p
  --values 26,27  (override the coarse grid; used for the refine pass)   --keep-media (save samples for ffprobe)
Writes results/intra_compare/raw/<path>__<input>.json; sample media to skellycam-raw/.../intra_compare/samples/.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

import av
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import iclib  # noqa: E402


def nvsmi() -> str:
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu,utilization.encoder",
                               "--format=csv,noheader"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"nvidia-smi failed: {e!r}"


def versions() -> dict:
    v = {"python": platform.python_version(), "pyav": av.__version__,
         "libavcodec": ".".join(map(str, av.library_versions["libavcodec"])), "numpy": np.__version__}
    try:
        import scipy  # noqa: PLC0415
        v["scipy"] = scipy.__version__
    except Exception:  # noqa: BLE001
        pass
    try:
        import simplejpeg  # noqa: PLC0415
        v["simplejpeg"] = simplejpeg.__version__
        v["simplejpeg_libjpeg_turbo"] = "3.1.2 (string 'libjpeg-turbo version 3.1.2 (build 20251010)' in _jpeg.pyd)"
    except Exception:  # noqa: BLE001
        pass
    try:
        from importlib.metadata import version  # noqa: PLC0415
        v["nvidia-nvimgcodec-cu12"] = version("nvidia-nvimgcodec-cu12")
    except Exception:  # noqa: BLE001
        pass
    return v


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", required=True)
    ap.add_argument("--inputs", default="yuy2_1080p,yuy2_720p,mjpeg_720p,mjpeg_1080p")
    ap.add_argument("--values", default="")
    ap.add_argument("--keep-media", action="store_true")
    ap.add_argument("--label", default="coarse")
    a = ap.parse_args()
    raw = iclib.RESULTS / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for inp in a.inputs.split(","):
        srcs = iclib.load_input(inp)
        for pid in a.paths.split(","):
            out = raw / f"{pid}__{inp}.json"
            doc = json.loads(out.read_text()) if out.exists() else {"path": pid, "input": inp, "points": [], "runs": []}
            have = {pt["value"] for pt in doc["points"] if pt.get("ok")}
            values = [int(x) for x in a.values.split(",")] if a.values else iclib.PATHS[pid]["grid"]
            todo = [v for v in values if v not in have]
            if not todo:
                continue
            run = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "label": a.label, "values": todo,
                   "versions": versions(), "nvidia_smi_before": nvsmi(), "machine": platform.node()}
            mid = values[len(values) // 2]
            for v in todo:
                try:
                    keep = (iclib.MEDIA / "samples" / inp) if (a.keep_media and v == mid) else None
                    rec = iclib.run_point(pid, srcs, v, keep)
                    rec["ok"] = True
                except Exception as e:  # noqa: BLE001
                    rec = {"path": pid, "value": v, "ok": False, "error": f"{type(e).__name__}: {e}"[:400],
                           "trace": traceback.format_exc()[-1200:]}
                rec["label"] = a.label
                doc["points"] = [p for p in doc["points"] if p["value"] != v] + [rec]
                print(pid, inp, v, {k: rec.get(k) for k in ("ok", "bytes_per_frame", "psnr_y", "ssim_y", "all_intra",
                                                            "frames_ok", "error")}, flush=True)
            run["nvidia_smi_after"] = nvsmi()
            doc["runs"].append(run)
            doc["points"].sort(key=lambda p: p["value"])
            out.write_text(json.dumps(doc, indent=0, default=str))


if __name__ == "__main__":
    main()
