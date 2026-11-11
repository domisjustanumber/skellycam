# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "numpy==2.2.6",
#   "nvidia-nvimgcodec-cu12[all]==0.9.0.20",
# ]
# ///
"""BENCHMARK (quiet machine only): nvJPEG decode of the cameras' own JPEGs from Python via NVIDIA nvImageCodec.

nvImageCodec is NVIDIA's Python binding that dispatches JPEG to nvJPEG (GPU). Measures, on the real corpus:
  gpu_single : Decoder.decode(bytes) one frame per call, result left on the GPU (synchronised by __cuda_array_interface__ access)
  gpu_to_host: the same plus .cpu() -> numpy (what a CPU consumer such as the shm ring or cv2 would need)
  gpu_batch5 : Decoder.decode([5 frames]) one call per multiframe (5 cameras)
Records nvidia-smi encoder/decoder session counts and utilisation before/after (Parsec/Sunshine may use the GPU).
nvimgcodec 0.9.0.20 was chosen over 0.10.0.9 because 0.10.0.9 was published 2026-11-03 (<2 weeks old).

Full run (~5 min; writes results/python_integration/bench/nvjpeg_decode_<tag>.json):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/python_integration/bench_nvjpeg_decode.py --tag quiet1
Smoke test (do not report its numbers):
  uv run --script ... --tag smoke --quick
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
OUT = Path(__file__).resolve().parents[2] / "results/python_integration/bench"
SETS = {"c930e_720p_flash": 300, "c922_720p_flash": 300, "c930e_1080p": 19, "c922_1080p": 19, "generic_1080p": 11}


def smi() -> str:
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,encoder.stats.sessionCount,"
                               "utilization.gpu,utilization.decoder,memory.used", "--format=csv,noheader"],
                              capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return repr(e)


def stats(t):
    a = np.array(t, dtype=np.float64) / 1e6
    return {"n": int(a.size), "median_ms": round(float(np.median(a)), 4), "mean_ms": round(float(a.mean()), 4),
            "p90_ms": round(float(np.percentile(a, 90)), 4), "p99_ms": round(float(np.percentile(a, 99)), 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--passes", type=int, default=5)
    args = ap.parse_args()
    from nvidia import nvimgcodec
    import importlib.metadata as md
    res = {"env": {"python": sys.version.split()[0], "platform": platform.platform(),
                   "nvimgcodec": md.version("nvidia-nvimgcodec-cu12"), "quick": args.quick,
                   "nvidia_smi_before": smi(), "started_unix": time.time()}, "sets": {}}
    dec = nvimgcodec.Decoder()
    pc = time.perf_counter_ns
    for name, nmax in SETS.items():
        frames = [f.read_bytes() for f in sorted((CORPUS / name).glob("frame_*.jpg"))[: (10 if args.quick else nmax)]]
        r = {"frames": len(frames)}
        try:
            img = dec.decode(frames[0])
            host = np.asarray(img.cpu())
            r["out_shape"] = list(host.shape)
            r["backend_note"] = str(getattr(img, "buffer_kind", ""))
            for _ in range(3 if args.quick else 20):
                np.asarray(dec.decode(frames[0]).cpu())
            g, h = [], []
            for _ in range(1 if args.quick else args.passes):
                for b in frames:
                    s = pc()
                    im = dec.decode(b)
                    _ = im.__cuda_array_interface__  # forces the decode to be complete for this image
                    g.append(pc() - s)
                    s = pc()
                    np.asarray(dec.decode(b).cpu())
                    h.append(pc() - s)
            r["gpu_single"], r["gpu_to_host"] = stats(g), stats(h)
            bt = []
            batch = [frames[i % len(frames)] for i in range(5)]
            for _ in range(5 if args.quick else 100):
                s = pc()
                out = dec.decode(batch)
                for im in out:
                    _ = im.__cuda_array_interface__
                bt.append(pc() - s)
            r["gpu_batch5"] = stats(bt)
        except Exception as e:  # noqa: BLE001
            r["error"] = repr(e)[:300]
        res["sets"][name] = r
        print(name, {k: r.get(k) for k in ("out_shape", "gpu_single", "error")}, flush=True)
    res["env"]["nvidia_smi_after"] = smi()
    res["env"]["finished_unix"] = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"nvjpeg_decode_{args.tag}.json"
    p.write_text(json.dumps(res, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
