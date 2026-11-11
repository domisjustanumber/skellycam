# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""BENCH (quiet machine only, PyAV 19.0.2): cost of the low-delay encoder settings that remove encoder hold-back
(crash_resilience FINDINGS 2.5). Added by VERIFY_method (2026-11-09); no manifest id existed for this question.

Configs (all 1280x720 yuv420p, GOP 30, decoded c930e_720p_flash camera JPEGs with pict_type cleared):
  svt_ra       libsvtav1 preset 10 crf 35 (defaults: random access)
  svt_ld       libsvtav1 preset 10 crf 35 svtav1-params=pred-struct=1 (low delay; the SVT log reports CQP, not CRF)
  nvenc        h264_nvenc p4 bf 0 rc vbr cq 23
  nvenc_d0     same + delay=0
Per config:
  paced    --paced frames fed at 30 fps: per-encode()-call latency p50/p99/max (ms), packets held before drain
  unpaced  --frames fed as fast as possible: wall s, CPU s, fps
  quality  bytes of the unpaced output, mean / min Y-PSNR (dB) of the decoded output vs the encoder input
usage: uv run --script bench_lowdelay_pyav19.py [--frames 600] [--paced 300] [--repeats 3] [--out <json>]
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

import numpy as np

SCR = Path("C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/crash_resilience")
sys.path.insert(0, str(SCR))
import common_cr as cc  # noqa: E402

OUT = SCR.parents[1] / "results" / "crash_resilience" / "bench" / "lowdelay_pyav19.json"
CONFIGS = {
    "svt_ra": ("libsvtav1", {"preset": "10", "crf": "35"}, "libdav1d"),
    "svt_ld": ("libsvtav1", {"preset": "10", "crf": "35", "svtav1-params": "pred-struct=1"}, "libdav1d"),
    "nvenc": ("h264_nvenc", {"preset": "p4", "bf": "0", "rc": "vbr", "cq": "23"}, "h264"),
    "nvenc_d0": ("h264_nvenc", {"preset": "p4", "bf": "0", "rc": "vbr", "cq": "23", "delay": "0"}, "h264"),
}


def load_frames(n: int):
    import av
    from av.video.frame import PictureType
    jp = cc.load_jpegs(cc.DEFAULT_SET, min(n, 891))
    dec = av.CodecContext.create("mjpeg", "r")
    frames = []
    for b in jp:
        f2 = dec.decode(av.Packet(b))[0].reformat(format="yuv420p")
        f2.pict_type = PictureType.NONE
        frames.append(f2)
    return [frames[i % len(frames)] for i in range(n)]


def make_enc(codec: str, opts: dict):
    import av
    w, h = cc.corpus_dims()
    enc = av.CodecContext.create(codec, "w")
    enc.width, enc.height, enc.pix_fmt = w, h, "yuv420p"
    enc.time_base = Fraction(1, cc.FPS)
    enc.framerate = Fraction(cc.FPS, 1)
    enc.gop_size = 30
    enc.options = dict(opts)
    return enc


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def paced(codec, opts, frames):
    enc = make_enc(codec, opts)
    lat, got = [], 0
    t0 = time.perf_counter()
    for i, f in enumerate(frames):
        dt = t0 + i / cc.FPS - time.perf_counter()
        if dt > 0:
            time.sleep(dt)
        f.pts = i
        a = time.perf_counter()
        got += len(enc.encode(f))
        lat.append((time.perf_counter() - a) * 1e3)
    held = len(frames) - got
    enc.encode(None)
    return {"frames": len(frames), "held_before_drain": held, "encode_call_ms_p50": pct(lat, 0.5),
            "encode_call_ms_p99": pct(lat, 0.99), "encode_call_ms_max": max(lat)}


def unpaced(codec, opts, frames):
    enc = make_enc(codec, opts)
    pk = []
    a, c = time.perf_counter(), time.process_time()
    for i, f in enumerate(frames):
        f.pts = i
        pk += [(bytes(p), p.pts) for p in enc.encode(f)]
    pk += [(bytes(p), p.pts) for p in enc.encode(None)]
    wall, cpu = time.perf_counter() - a, time.process_time() - c
    return {"wall_s": wall, "cpu_s": cpu, "fps": len(frames) / wall, "packets": len(pk),
            "bytes": sum(len(b) for b, _ in pk)}, pk


def psnr(pk, dec_name, frames):
    import av
    dec = av.CodecContext.create(dec_name, "r")
    out = []
    for b, pts in pk:
        p = av.Packet(b)
        p.pts = pts
        out += dec.decode(p)
    out += dec.decode(None)
    out.sort(key=lambda f: f.pts if f.pts is not None else 0)
    h = frames[0].height
    vals = []
    for f, ref in zip(out, frames):
        y1 = f.reformat(format="yuv420p").to_ndarray()[:h].astype(np.float64)
        y0 = ref.to_ndarray()[:h].astype(np.float64)
        mse = float(np.mean((y1 - y0) ** 2))
        vals.append(99.0 if mse == 0 else 10 * math.log10(255 ** 2 / mse))
    return {"decoded": len(out), "y_psnr_mean_db": float(np.mean(vals)) if vals else None,
            "y_psnr_min_db": float(np.min(vals)) if vals else None}


def main():
    import av
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--paced", type=int, default=300)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--configs", default=",".join(CONFIGS))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    frames = load_frames(max(a.frames, a.paced))
    res = {"env": {"pyav": av.__version__, "libav": {k: ".".join(map(str, v)) for k, v in av.library_versions.items()},
                   "corpus_set": cc.DEFAULT_SET},
           "nvidia_smi_before": cc.nvidia_smi(), "args": vars(a), "runs": []}
    for name in a.configs.split(","):
        codec, opts, dname = CONFIGS[name]
        for rep in range(a.repeats):
            r = {"config": name, "codec": codec, "options": opts, "repeat": rep}
            try:
                r["paced"] = paced(codec, opts, frames[:a.paced])
                r["unpaced"], pk = unpaced(codec, opts, frames[:a.frames])
                if rep == 0:
                    r["quality"] = psnr(pk, dname, frames[:a.frames])
            except Exception as e:
                r["error"] = repr(e)
            res["runs"].append(r)
            print(json.dumps(r), flush=True)
    res["nvidia_smi_after"] = cc.nvidia_smi()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
