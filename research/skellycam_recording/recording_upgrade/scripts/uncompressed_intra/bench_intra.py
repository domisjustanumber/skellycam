# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "psutil==7.2.2"]
# ///
"""TIMING BENCH (run only on a quiet machine): one intra codec config x one source x one thread setting.

Measures, for a single stream:
  * prep_ms_per_frame      numpy re-layout from the camera format to the encoder's pix_fmt (e.g. yuyv422->yuv422p)
  * encode: wall fps, process CPU seconds, CPU cores used per 30 fps stream (= cpu_s / (frames/30)),
            per-call latency percentiles (make_frame + encode + mux of whatever packets come out)
  * bytes/frame (mean packet size)
  * decode: wall fps and CPU of decoding the produced file with the same thread setting
Frames: the 8 real 1080p YUY2 frames (corpus c930e_1080p_yuy2) or 8 real 720p JPEGs decoded to YUY2
(c930e_720p_flash), LOOPED to --frames (default 300) - looping is stated in the JSON. Derived formats per
uintra_frames.py (nv12 = 4:2:0 average, bayer12 = 12-bit RGGB mosaic re-tagged as gray16le, bayer12_quad, ...).
Output file written to the media folder and deleted afterwards (disk write included, as in a recorder).

Pinned venv (PyAV 18.0.0):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_intra.py \
      --config ffv1_l3_s4_crc_g1.mkv --source yuyv422 --res 1080p --threads 1
PyAV 19.0.2 isolated: replace the interpreter with `uv run --script`.
--list prints the config ids. Writes results/uncompressed_intra/bench/<config>__<source>_<res>__t<threads>__pyav<ver>.json
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
import functional_matrix as fm  # noqa: E402  (config list, exact re-layout paths)
import uintra_frames as uf  # noqa: E402

BENCH = Path(__file__).resolve().parents[2] / "results" / "uncompressed_intra" / "bench"
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/bench_tmp")

# bench-only variants (slice count matters for FFV1 threading; presets for AV1/VP9)
fm.cfg("ffv1_l3_s16_crc_g1.mkv", "ffv1", "mkv", {"level": "3", "slices": "16", "slicecrc": "1"})
fm.cfg("ffv1_l3_s24_crc_g1.mkv", "ffv1", "mkv", {"level": "3", "slices": "24", "slicecrc": "1"})
fm.cfg("ffv1_l3_s24_crc_range_g1.mkv", "ffv1", "mkv", {"level": "3", "slices": "24", "slicecrc": "1", "coder": "range_tab"})
fm.cfg("libsvtav1_intra_crf30_p12.mkv", "libsvtav1", "mkv", {"preset": "12", "crf": "30", "svtav1-params": "keyint=1"}, lossless=False)
fm.cfg("libsvtav1_intra_lossless_p12.mkv", "libsvtav1", "mkv", {"preset": "12", "svtav1-params": "keyint=1:lossless=1"})
fm.cfg("rawvideo_yuv422p.nut", "rawvideo", "nut")
CONFIGS = {c["id"]: c for c in fm.CONFIGS}

SOURCES = {  # name -> (uintra_frames.derive key, note)
    "yuyv422": ("yuyv422", "real camera YUY2 (1080p) / JPEG-decoded YUY2 (720p)"),
    "nv12": ("nv12", "derived 4:2:0"),
    "gray": ("gray", "derived Y plane"),
    "p010le": ("p010le", "derived 10-bit"),
    "bayer8": ("bayer_rggb8", "derived 8-bit RGGB"),
    "bayer8_quad": ("bayer8_quad", "derived 8-bit RGGB de-interleaved to 4 planes"),
    "bayer12": ("bayer_rggb16le", "derived 12-bit RGGB in 16-bit LE"),
    "bayer12_quad": ("bayer16_quad", "derived 12-bit RGGB de-interleaved to 4 planes"),
    "raw12_packed": ("raw12_packed", "derived MIPI RAW12 packed bytes as gray8"),
}


def nvsmi() -> str:
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu",
                               "--format=csv,noheader"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"n/a: {e}"


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--source", default="yuyv422", choices=list(SOURCES))
    ap.add_argument("--res", default="1080p", choices=["1080p", "720p"])
    ap.add_argument("--threads", type=int, default=1, help="1 = single thread; 0 = libav auto (all cores)")
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--no-decode", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--reps", type=int, default=3, help="timed repetitions after one discarded warm-up run")
    ap.add_argument("--warmup-frames", type=int, default=20)
    a = ap.parse_args()
    if a.list:
        print("\n".join(CONFIGS))
        return
    c = CONFIGS[a.config]
    yuy, w, h = (uf.load_yuy2("c930e_1080p_yuy2", 8) if a.res == "1080p" else uf.load_jpeg_as_yuy2("c930e_720p_flash", 8))
    src_key = SOURCES[a.source][0]
    srcs = [uf.derive(src_key, f, w, h, idx=i) for i, f in enumerate(yuy)]
    planes0, src_fmt, fw, fh = srcs[0]
    enc = av.Codec(c["codec"], "w")
    enc_fmts = [f.name for f in (enc.video_formats or [])]
    if c["id"] == "rawvideo_yuv422p.nut":
        path = dict(target="yuv422p", method="numpy deinterleave", fwd=fm._f_yuyv_422p, inv=None)
    else:
        path = fm.choose_path(src_key, src_fmt, enc_fmts, c["lossless"], c["codec"], c["opts"])
    if path is None:
        raise SystemExit(f"no path from {src_fmt} for {c['id']}")
    # prep timing: numpy re-layout (or swscale) of the 8 unique frames, repeated
    t0 = time.perf_counter()
    reps = 5
    for _ in range(reps):
        fed = []
        for planes, fmt, _, _ in srcs:
            if path["fwd"] is not None:
                fed.append(path["fwd"](planes, fw, fh))
            else:
                fed.append(uf.read_planes(uf.make_frame(planes, fmt, fw, fh).reformat(format=path["target"]), path["target"]))
    prep_ms = (time.perf_counter() - t0) * 1000 / (reps * len(srcs))
    MEDIA.mkdir(parents=True, exist_ok=True)
    out = MEDIA / f"{a.config}__{a.source}_{a.res}__t{a.threads}.{c['ext']}"
    proc = psutil.Process()
    sys_cpu_before = psutil.cpu_percent(interval=0.5)
    res = dict(config=c["id"], codec=c["codec"], opts=c["opts"], gop=c["gop"], source=a.source, source_note=SOURCES[a.source][1],
               res=a.res, width=fw, height=fh, src_pix_fmt=src_fmt, target_pix_fmt=path["target"], path=path["method"],
               threads=a.threads, frames=a.frames, unique_frames=len(srcs), looped=a.frames > len(srcs),
               reps=a.reps, warmup_frames=a.warmup_frames, warmup_discarded=True,
               av_version=av.__version__, ffmpeg_version=getattr(av, "ffmpeg_version_info", "?"),
               library_versions={k: list(v) for k, v in getattr(av, "library_versions", {}).items()},
               numpy=np.__version__, python=sys.version.split()[0], machine=platform.node(), cpu_logical=psutil.cpu_count(),
               system_cpu_percent_before=sys_cpu_before, prep_ms_per_frame=round(prep_ms, 3))
    if c["gpu"]:
        res["nvidia_smi_before"] = nvsmi()

    def run_once(nframes: int) -> dict:
        lat = []
        nbytes = npk = 0
        psutil.cpu_percent(interval=None)
        with av.open(str(out), "w") as oc:
            st = oc.add_stream(c["codec"], rate=30, options=dict(c["opts"]))
            st.width, st.height, st.pix_fmt = fw, fh, path["target"]
            if c["gop"] is not None:
                st.codec_context.gop_size = c["gop"]
            st.codec_context.thread_count = a.threads
            if a.threads != 1:
                st.codec_context.thread_type = "AUTO"
            cpu0 = proc.cpu_times()
            t0 = time.perf_counter()
            for i in range(nframes):
                ts = time.perf_counter()
                fr = uf.make_frame(fed[i % len(fed)], path["target"], fw, fh)
                fr.pts, fr.time_base = i, Fraction(1, 30)
                for p in st.encode(fr):
                    nbytes += p.size
                    npk += 1
                    oc.mux(p)
                lat.append((time.perf_counter() - ts) * 1000)
            for p in st.encode(None):
                nbytes += p.size
                npk += 1
                oc.mux(p)
            enc_wall = time.perf_counter() - t0
            cpu1 = proc.cpu_times()
        enc_cpu = (cpu1.user - cpu0.user) + (cpu1.system - cpu0.system)
        r = dict(encode_wall_s=round(enc_wall, 4), encode_fps=round(nframes / enc_wall, 2), encode_cpu_s=round(enc_cpu, 4),
                 encode_cpu_cores_per_30fps_stream=round(enc_cpu / (nframes / 30), 3),
                 latency_p50=round(pct(lat, .5), 3), latency_p95=round(pct(lat, .95), 3), latency_p99=round(pct(lat, .99), 3),
                 latency_max=round(max(lat), 3), latency_mean=round(statistics.mean(lat), 3),
                 packets=npk, bytes_per_frame=round(nbytes / max(npk, 1), 1), file_bytes=out.stat().st_size,
                 system_cpu_percent_during_encode=psutil.cpu_percent(interval=None))
        if not a.no_decode:
            cpu0 = proc.cpu_times()
            t0 = time.perf_counter()
            n = 0
            with av.open(str(out)) as ic:
                vs = ic.streams.video[0]
                vs.codec_context.thread_count = a.threads
                if a.threads != 1:
                    vs.codec_context.thread_type = "AUTO"
                for _fr in ic.decode(vs):
                    n += 1
            dec_wall = time.perf_counter() - t0
            cpu1 = proc.cpu_times()
            r.update(decode_frames=n, decode_wall_s=round(dec_wall, 4), decode_fps=round(n / dec_wall, 2),
                     decode_cpu_s=round((cpu1.user - cpu0.user) + (cpu1.system - cpu0.system), 4))
        out.unlink()
        return r

    res["warmup"] = run_once(a.warmup_frames)  # discarded from the statistics
    reps = [run_once(a.frames) for _ in range(a.reps)]
    res["rep_results"] = reps

    def agg(k):
        xs = [r[k] for r in reps if r.get(k) is not None]
        return dict(median=round(statistics.median(xs), 3), min=min(xs), max=max(xs)) if xs else None

    stats = {k: agg(k) for k in ("encode_fps", "encode_cpu_cores_per_30fps_stream", "latency_p50", "latency_p99", "latency_max",
                                  "bytes_per_frame", "decode_fps", "system_cpu_percent_during_encode")}
    res["stats"] = stats
    # flat median fields (kept for bench_summary.py)
    res.update(encode_fps=stats["encode_fps"]["median"],
               encode_cpu_cores_per_30fps_stream=stats["encode_cpu_cores_per_30fps_stream"]["median"],
               encode_latency_ms=dict(p50=stats["latency_p50"]["median"], p99=stats["latency_p99"]["median"],
                                      max=stats["latency_max"]["median"]),
               bytes_per_frame=stats["bytes_per_frame"]["median"],
               decode_fps=stats["decode_fps"]["median"] if stats["decode_fps"] else None,
               decoder="libav default for codec (software unless the decoder is hw)")
    if c["gpu"]:
        res["nvidia_smi_after"] = nvsmi()
    res["system_cpu_percent_after"] = psutil.cpu_percent(interval=0.5)
    BENCH.mkdir(parents=True, exist_ok=True)
    jp = BENCH / f"{a.config}__{a.source}_{a.res}__t{a.threads}__pyav{av.__version__}{a.tag}.json"
    jp.write_text(json.dumps(res, indent=1))
    print(f"{a.config} {a.source} {a.res} t{a.threads}: enc {res['encode_fps']} fps, cpu/stream {res['encode_cpu_cores_per_30fps_stream']}, "
          f"{res['bytes_per_frame']/1000:.0f} KB/f, dec {res.get('decode_fps')} fps -> {jp.name}")


if __name__ == "__main__":
    main()
