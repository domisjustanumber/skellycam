# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "numpy==2.2.6",
#   "psutil==7.2.2",
#   "simplejpeg==1.9.0",
#   "imagecodecs==2026.10.10",
#   "opencv-python==5.0.0.93",
# ]
# ///
"""TIMING BENCH (quiet machine only): Python still-image encoders as per-frame intra writers, 1080p.

Cases (input -> encoder; conversion cost included in the timed call):
  simplejpeg_yuv422_q90      real YUY2 -> numpy split to Y/U/V planes -> simplejpeg.encode_jpeg_yuv_planes (4:2:2)
  simplejpeg_yuv420_q90      derived NV12 -> planes -> simplejpeg (4:2:0)
  cv2_yuy2_to_bgr_jpg422_q90 real YUY2 -> cv2.cvtColor(YUV2BGR_YUY2) -> cv2.imencode .jpg (sampling 4:2:2)
  cv2_png_bayer12            12-bit mosaic (uint16) -> cv2.imencode .png (lossless)
  ic_jpeg8_lossless_bayer12  imagecodecs.jpeg8_encode lossless=True bitspersample=12 (libjpeg-turbo SOF3)
  ic_ljpeg_bayer12           imagecodecs.ljpeg_encode (lossless JPEG)
  ic_jpegls_bayer12          imagecodecs.jpegls_encode level=0 (CharLS, lossless)
  ic_jpeg2k_rev_bayer12      imagecodecs.jpeg2k_encode reversible (OpenJPEG, lossless)
  ic_jpegxl_e1_bayer12       imagecodecs.jpegxl_encode lossless effort=1 (libjxl)
  ic_jpegxl_e1_bayer12_quad  same on the de-interleaved (4-plane tiled) mosaic
  ic_jpegxl_d1_e1_rgb        imagecodecs.jpegxl_encode distance=1 effort=1 on BT.601 RGB (lossy)
Each case is run with every --workers value (ThreadPoolExecutor over frames: measures whether the library
releases the GIL and scales). The 8 real frames are looped to --frames.

  uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_py_still.py --frames 120 --workers 1,4,8
Writes results/uncompressed_intra/bench/py_still__<tag>.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uintra_frames as uf  # noqa: E402

BENCH = Path(__file__).resolve().parents[2] / "results" / "uncompressed_intra" / "bench"


def build_cases(yuy, w, h):
    import cv2
    import imagecodecs as ic
    import simplejpeg as sj

    nv = [uf.derive("yuv420p", f, w, h)[0] for f in yuy]
    m12 = [uf.derive("bayer_rggb16le", f, w, h, idx=i)[0][0].view("<u2").reshape(h, w) for i, f in enumerate(yuy)]
    q12 = [uf.quad_from_mosaic(m) for m in m12]
    rgb = [uf.yuyv_to_rgb24(f) for f in yuy]

    def sj422(i):
        y, u, v = uf.yuyv_split(yuy[i])
        return sj.encode_jpeg_yuv_planes(y, u, v, quality=90)

    def cvjpg(i):
        bgr = cv2.cvtColor(yuy[i].reshape(h, w, 2), cv2.COLOR_YUV2BGR_YUY2)
        return cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 90, cv2.IMWRITE_JPEG_SAMPLING_FACTOR,
                                          cv2.IMWRITE_JPEG_SAMPLING_FACTOR_422])[1].tobytes()

    enc = {
        "simplejpeg_yuv422_q90": (sj422, lambda b: sj.decode_jpeg(b)),
        "simplejpeg_yuv420_q90": (lambda i: sj.encode_jpeg_yuv_planes(*nv[i], quality=90), lambda b: sj.decode_jpeg(b)),
        "cv2_yuy2_to_bgr_jpg422_q90": (cvjpg, lambda b: cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)),
        "cv2_png_bayer12": (lambda i: cv2.imencode(".png", m12[i])[1].tobytes(),
                            lambda b: cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_UNCHANGED)),
        "ic_jpeg8_lossless_bayer12": (lambda i: ic.jpeg8_encode(m12[i], lossless=True, bitspersample=12), ic.jpeg8_decode),
        "ic_ljpeg_bayer12": (lambda i: ic.ljpeg_encode(m12[i], bitspersample=12), ic.ljpeg_decode),
        "ic_jpegls_bayer12": (lambda i: ic.jpegls_encode(m12[i], level=0), ic.jpegls_decode),
        "ic_jpeg2k_rev_bayer12": (lambda i: ic.jpeg2k_encode(m12[i], level=0, reversible=True, bitspersample=12), ic.jpeg2k_decode),
        "ic_jpegxl_e1_bayer12": (lambda i: ic.jpegxl_encode(m12[i], lossless=True, effort=1, bitspersample=12), ic.jpegxl_decode),
        "ic_jpegxl_e1_bayer12_quad": (lambda i: ic.jpegxl_encode(q12[i], lossless=True, effort=1, bitspersample=12), ic.jpegxl_decode),
        "ic_jpegxl_d1_e1_rgb": (lambda i: ic.jpegxl_encode(rgb[i], distance=1.0, effort=1), ic.jpegxl_decode),
    }
    return enc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=120)
    ap.add_argument("--workers", default="1,4,8")
    ap.add_argument("--only", default="")
    ap.add_argument("--tag", default="")
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    yuy, w, h = uf.load_yuy2("c930e_1080p_yuy2", 8)
    vers = {"python": sys.version.split()[0], "numpy": np.__version__}
    for m in ("simplejpeg", "imagecodecs", "cv2"):
        try:
            vers[m] = __import__(m).__version__
        except Exception as e:  # noqa: BLE001
            vers[m] = f"missing: {e}"
    cases = build_cases(yuy, w, h)
    proc = psutil.Process()
    results = []
    psutil.cpu_percent(interval=None)
    for name, (enc, dec) in cases.items():
        if a.only and a.only not in name:
            continue
        for nw in [int(x) for x in a.workers.split(",")]:
            r = {"case": name, "workers": nw, "frames": a.frames, "looped_unique_frames": len(yuy)}
            try:
                def one_pass():
                    c0, t0 = proc.cpu_times(), time.perf_counter()
                    if nw == 1:
                        o = [enc(i % len(yuy)) for i in range(a.frames)]
                    else:
                        with ThreadPoolExecutor(nw) as ex:
                            o = list(ex.map(lambda i: enc(i % len(yuy)), range(a.frames)))
                    wall = time.perf_counter() - t0
                    c1 = proc.cpu_times()
                    return o, a.frames / wall, (c1.user - c0.user) + (c1.system - c0.system)
                for i in range(len(yuy)):
                    enc(i)  # warm-up pass over the unique frames, discarded
                reps = [one_pass() for _ in range(a.reps)]
                outs = reps[0][0]
                fps = [x[1] for x in reps]
                cores = [x[2] / (a.frames / 30) for x in reps]
                r.update(reps=a.reps, encode_fps=round(statistics.median(fps), 2), encode_fps_min=round(min(fps), 2),
                         encode_fps_max=round(max(fps), 2), cpu_cores_per_30fps_stream=round(statistics.median(cores), 3),
                         cpu_cores_min=round(min(cores), 3), cpu_cores_max=round(max(cores), 3),
                         bytes_per_frame=round(sum(len(o) for o in outs[: len(yuy)]) / len(yuy), 1))
                if nw == 1:
                    dfps = []
                    for _ in range(a.reps):
                        t0 = time.perf_counter()
                        for i in range(min(a.frames, 60)):
                            dec(outs[i % len(yuy)])
                        dfps.append(min(a.frames, 60) / (time.perf_counter() - t0))
                    r["decode_fps"] = round(statistics.median(dfps), 2)
                    r["decode_fps_min_max"] = [round(min(dfps), 2), round(max(dfps), 2)]
            except Exception as e:  # noqa: BLE001
                r["error"] = f"{type(e).__name__}: {e}"
            results.append(r)
            print(json.dumps(r), flush=True)
    BENCH.mkdir(parents=True, exist_ok=True)
    p = BENCH / f"py_still__{a.tag or 'uv'}.json"
    p.write_text(json.dumps({"bench": "py_still", "versions": vers, "width": w, "height": h,
                             "system_cpu_percent_during": psutil.cpu_percent(interval=None), "machine": __import__("platform").node(), "results": results}, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
