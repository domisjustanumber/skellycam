"""TIMING BENCH (quiet machine only): cost of demosaicing a 1080p RGGB frame before storage.

Methods: libswscale via PyAV frame.reformat (bayer_rggb16le -> rgb48le, bayer_rggb8 -> rgb24) and OpenCV
cvtColor COLOR_BayerBG2BGR / _EA / _VNG (BayerBG is the OpenCV code that matches an RGGB sensor layout here -
see bayer_debayer_check.json: it is the code whose output keeps the CFA samples / has the high PSNR).
Mosaics derived from the 8 real YUY2 1080p frames (uintra_frames.derive), looped.

  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_debayer.py --frames 120
Writes results/uncompressed_intra/bench/debayer__pyav<ver>_cv<ver>.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import av
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uintra_frames as uf  # noqa: E402

BENCH = Path(__file__).resolve().parents[2] / "results" / "uncompressed_intra" / "bench"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=120)
    ap.add_argument("--cv-threads", type=int, default=-1, help="cv2.setNumThreads value (-1 = OpenCV default)")
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    if a.cv_threads >= 0:
        cv2.setNumThreads(a.cv_threads)
    yuy, w, h = uf.load_yuy2("c930e_1080p_yuy2", 8)
    m8 = [uf.derive("bayer_rggb8", f, w, h)[0][0] for f in yuy]
    m12 = [uf.derive("bayer_rggb16le", f, w, h, idx=i)[0][0].view("<u2").reshape(h, w) for i, f in enumerate(yuy)]

    def sws(bits):
        if bits == 8:
            return lambda i: uf.read_planes(uf.make_frame([m8[i]], "bayer_rggb8", w, h).reformat(format="rgb24"), "rgb24")
        return lambda i: uf.read_planes(uf.make_frame([uf.to_u8_rows(m12[i])], "bayer_rggb16le", w, h).reformat(format="rgb48le"), "rgb48le")

    def cvm(code, bits):
        src = m8 if bits == 8 else m12
        return lambda i: cv2.cvtColor(src[i], getattr(cv2, code))

    methods = [("swscale_bilinear", b, sws(b)) for b in (8, 12)]
    for code in ("COLOR_BayerBG2BGR", "COLOR_BayerBG2BGR_EA", "COLOR_BayerBG2BGR_VNG"):
        for b in (8, 12):
            methods.append((code, b, cvm(code, b)))
    results = []
    for name, bits, fn in methods:
        r = {"method": name, "bits": bits, "frames": a.frames}
        try:
            for i in range(len(yuy)):
                fn(i)  # warm-up, discarded
            ms = []
            for _ in range(a.reps):
                t0 = time.perf_counter()
                for i in range(a.frames):
                    fn(i % len(yuy))
                ms.append((time.perf_counter() - t0) * 1000 / a.frames)
            r.update(reps=a.reps, ms_per_frame=round(statistics.median(ms), 3), ms_min=round(min(ms), 3), ms_max=round(max(ms), 3))
        except Exception as e:  # noqa: BLE001
            r["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        results.append(r)
        print(json.dumps(r), flush=True)
    BENCH.mkdir(parents=True, exist_ok=True)
    p = BENCH / f"debayer__pyav{av.__version__}_cv{cv2.__version__}.json"
    p.write_text(json.dumps({"bench": "debayer", "versions": {"av": av.__version__, "cv2": cv2.__version__,
                             "cv2_threads": cv2.getNumThreads(), "numpy": np.__version__, "python": sys.version.split()[0]}, "results": results}, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
