# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "numpy==2.2.6",
#   "opencv-python==4.12.0.88",
#   "simplejpeg==1.9.0",
#   "PyTurboJPEG==2.6.1",
#   "av==19.0.2",
# ]
# ///
# 2026-11-09: av pin changed 18.0.0 -> 19.0.2 for the 23:00 queue (HANDOFF section 1 item 5: PyAV 19.0.2 only).
"""BENCHMARK (run on a quiet machine only): CPU cost of decoding the cameras' own JPEGs in Python.

Why: if skellycam records the camera JPEG bytes (G1), the live UI / FreeMoCap realtime still need pixels, so
each frame is decoded once in Python. Prior numbers (frame_ring_buffer p8: imdecode 9.09 ms / simplejpeg 5.82 ms
median at 1080p) used synthetic q90 JPEGs (~540 KB at 1080p) under a 5-camera load; real camera JPEGs are
57-192 KB. This measures each library on the real corpus, one call at a time, plus reduced-size decodes
(what a UI preview needs) and an N-thread aggregate (does the library release the GIL?).

Methods: cv2.imdecode (full, IMREAD_REDUCED_COLOR_2), simplejpeg.decode_jpeg (BGR; default and fastdct+fastupsample;
min_height=360 reduced), PyTurboJPEG (BGR full; scaling 1/2), PyAV libavcodec mjpeg (to bgr24; to native yuv
planes = decode only). libjpeg-turbo DLL for PyTurboJPEG: libjpeg-turbo 3.2.0 official build
(https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.2.0/libjpeg-turbo-3.2.0-vc-x64.exe,
sha256 662761d8ba8dae04aec74023ebaeceb856c2b56b9b59cfd180759d26300dda42), extracted with 7-Zip, never installed;
pass its bin/turbojpeg.dll with --turbojpeg-dll (the method is skipped if missing).

Full run (about 10-15 min; writes results/python_integration/bench/jpeg_decode_<tag>.json):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/python_integration/bench_jpeg_decode.py --tag quiet1 --turbojpeg-dll <path>/bin/turbojpeg.dll
Smoke test (seconds; do not report its numbers):
  uv run --script ... --tag smoke --quick --turbojpeg-dll <path>/bin/turbojpeg.dll
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import threading
import time
from pathlib import Path

import numpy as np

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
OUT = Path(__file__).resolve().parents[2] / "results/python_integration/bench"
SETS = {"c930e_720p_flash": 300, "c922_720p_flash": 300, "c930e_1080p": 19, "c922_1080p": 19, "generic_1080p": 11}


def build_methods(tj_dll: str | None):
    import av
    import cv2
    import simplejpeg
    m = {}
    m["cv2_imdecode_bgr"] = lambda b: cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
    m["cv2_imdecode_reduced2_bgr"] = lambda b: cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_REDUCED_COLOR_2)
    # strict=False: simplejpeg 1.9.0's default strict=True rejects the generic camera's frames
    # ("Corrupt JPEG data: 534 extraneous bytes before marker 0xd9"); cv2 and PyTurboJPEG accept them.
    m["simplejpeg_bgr"] = lambda b: simplejpeg.decode_jpeg(b, colorspace="BGR", strict=False)
    m["simplejpeg_bgr_fast"] = lambda b: simplejpeg.decode_jpeg(b, colorspace="BGR", fastdct=True, fastupsample=True,
                                                                 strict=False)
    m["simplejpeg_bgr_min_h360"] = lambda b: simplejpeg.decode_jpeg(b, colorspace="BGR", min_height=360, strict=False)
    bufs = threading.local()

    def sj_into(b):  # decode straight into a preallocated array (stand-in for a shared-memory slot)
        h, w, _, _ = simplejpeg.decode_jpeg_header(b)
        buf = getattr(bufs, "a", None)
        if buf is None or buf.shape != (h, w, 3):
            buf = bufs.a = np.empty((h, w, 3), np.uint8)
        return simplejpeg.decode_jpeg(b, colorspace="BGR", buffer=buf, strict=False)
    m["simplejpeg_bgr_into_buffer"] = sj_into
    if tj_dll and Path(tj_dll).exists():
        from turbojpeg import TJPF_BGR, TurboJPEG
        tj = TurboJPEG(lib_path=tj_dll)
        m["turbojpeg_bgr"] = lambda b: tj.decode(b, pixel_format=TJPF_BGR)
        m["turbojpeg_bgr_scale_1_2"] = lambda b: tj.decode(b, pixel_format=TJPF_BGR, scaling_factor=(1, 2))
    local = threading.local()

    def _ctx():
        c = getattr(local, "ctx", None)
        if c is None:
            c = av.CodecContext.create("mjpeg", "r")
            c.thread_count = 1
            local.ctx = c
        return c

    def pyav_bgr(b):
        frames = _ctx().decode(av.Packet(b))
        return frames[0].to_ndarray(format="bgr24")

    def pyav_native(b):
        frames = _ctx().decode(av.Packet(b))
        f = frames[0]
        return [np.frombuffer(p, np.uint8) for p in f.planes]  # decode only, no colour conversion

    m["pyav_mjpeg_bgr24"] = pyav_bgr
    m["pyav_mjpeg_native_yuv"] = pyav_native
    return m


def time_calls(fn, frames, passes, warmup):
    for b in frames[:warmup]:
        fn(b)
    t = []
    pc = time.perf_counter_ns
    for _ in range(passes):
        for b in frames:
            s = pc()
            fn(b)
            t.append(pc() - s)
    return t


def summarize_ns(t):
    a = np.array(t, dtype=np.float64) / 1e6
    return {"n": int(a.size), "median_ms": round(float(np.median(a)), 4), "mean_ms": round(float(a.mean()), 4),
            "p90_ms": round(float(np.percentile(a, 90)), 4), "p99_ms": round(float(np.percentile(a, 99)), 4),
            "min_ms": round(float(a.min()), 4), "max_ms": round(float(a.max()), 4)}


def threaded_throughput(fn, frames, n_threads, seconds):
    stop = time.perf_counter() + seconds
    counts = [0] * n_threads

    def work(k):
        i = k
        while time.perf_counter() < stop:
            fn(frames[i % len(frames)])
            counts[k] += 1
            i += 1
    th = [threading.Thread(target=work, args=(k,)) for k in range(n_threads)]
    t0 = time.perf_counter()
    for x in th:
        x.start()
    for x in th:
        x.join()
    el = time.perf_counter() - t0
    return {"threads": n_threads, "decodes": sum(counts), "elapsed_s": round(el, 3),
            "decodes_per_s": round(sum(counts) / el, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--turbojpeg-dll", default=None)
    ap.add_argument("--quick", action="store_true", help="smoke test: few frames, 1 pass, short threaded runs")
    ap.add_argument("--passes", type=int, default=5)
    ap.add_argument("--threads", default="1,5")
    ap.add_argument("--thread-seconds", type=float, default=5.0)
    args = ap.parse_args()
    import av
    import cv2
    import simplejpeg
    cv2.setNumThreads(1)
    methods = build_methods(args.turbojpeg_dll)
    env = {"python": sys.version.split()[0], "platform": platform.platform(), "cpu_count": os.cpu_count(),
           "processor": platform.processor(), "numpy": np.__version__, "opencv": cv2.__version__,
           "simplejpeg": simplejpeg.__version__, "av": av.__version__,
           "turbojpeg_dll": args.turbojpeg_dll, "quick": args.quick, "cv2_num_threads": cv2.getNumThreads(),
           "started_unix": time.time()}
    try:
        import importlib.metadata as md
        env["PyTurboJPEG"] = md.version("PyTurboJPEG")
    except Exception:  # noqa: BLE001
        env["PyTurboJPEG"] = None
    res = {"env": env, "sets": {}}
    for name, nmax in SETS.items():
        files = sorted((CORPUS / name).glob("frame_*.jpg"))[: (10 if args.quick else nmax)]
        frames = [f.read_bytes() for f in files]
        ref = cv2.imdecode(np.frombuffer(frames[0], np.uint8), cv2.IMREAD_COLOR)
        sres = {"frames": len(frames), "jpeg_bytes_median": int(statistics.median(len(b) for b in frames)),
                "shape": list(ref.shape), "methods": {}}
        for mname, fn in methods.items():
            try:
                out = fn(frames[0])
                info = {}
                if isinstance(out, np.ndarray):
                    info["out_shape"] = list(out.shape)
                    if out.shape == ref.shape:
                        info["max_abs_diff_vs_cv2"] = int(np.abs(out.astype(np.int16) - ref.astype(np.int16)).max())
                t = time_calls(fn, frames, 1 if args.quick else args.passes, 3 if args.quick else 20)
                info["single_call"] = summarize_ns(t)
                info["threaded"] = [threaded_throughput(fn, frames, int(k), 0.5 if args.quick else args.thread_seconds)
                                    for k in args.threads.split(",")]
            except Exception as e:  # noqa: BLE001
                info = {"error": repr(e)[:300]}
            sres["methods"][mname] = info
            print(name, mname, info.get("single_call", info.get("error")), flush=True)
        res["sets"][name] = sres
    env["finished_unix"] = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"jpeg_decode_{args.tag}.json"
    p.write_text(json.dumps(res, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
