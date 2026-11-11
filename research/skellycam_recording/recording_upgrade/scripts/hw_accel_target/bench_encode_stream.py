# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "psutil==7.2.2"]
# ///
"""BENCHMARK (timing): single-stream encode fps and CPU cost per frame through PyAV 19.0.2.

One stream, one thread, unpaced (as fast as possible), packets discarded (bytes counted; no file I/O).
The timed loop includes building the input frame from camera-like bytes each iteration:
  nv12        : VideoFrame.from_ndarray(NV12 array)                         (NV12 made from real YUY2 frames)
  yuy2        : YUY2 bytes -> yuyv422 VideoFrame -> reformat to encoder fmt  (swscale in the loop)
  yuy2native  : YUY2 bytes -> yuyv422 VideoFrame fed directly                (only encoders taking yuyv422)
  mjpeg_cpu   : camera JPEG bytes -> PyAV 'mjpeg' CPU decode -> reformat to encoder fmt
  mjpeg_qsv   : camera JPEG bytes -> 'mjpeg_qsv' decode (Intel iGPU) -> reformat if needed
  mjpeg_cuvid : camera JPEG bytes -> 'mjpeg_cuvid' (expected to fail on 4:2:2, recorded)
Encoder 'none' = source pipeline only (decode/convert cost). --native422 adds runs that feed 4:2:2 planar
(yuv422p / yuvj422p) to CPU encoders that take it (mjpeg, ffv1, libvpx-vp9).
Per run: open_s, frames, wall_s, fps, process CPU s (psutil user+system, all threads), cpu_ms_per_frame,
cpu_cores (= cpu_s / wall_s), bytes_per_frame, nvidia-smi samples. Median over --reps.
Background load (10 s typeperf, top processes, nvidia-smi sessions) is recorded before the first run.

Run from the repo root on a QUIET machine, one bench at a time:
  uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_encode_stream.py \
      --encoders h264_qsv,hevc_qsv --sizes 720p,1080p --sources nv12,yuy2,mjpeg_cpu,mjpeg_qsv --gops intra,gop30 \
      --frames 600 --reps 3 --label qsv
Smoke (numbers discarded): add --frames 10 --reps 1 --outdir <scratchpad dir>
Writes results/hw_accel_target/bench/encode_stream_<label>_<UTC>.json
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from av.video.frame import PictureType
import psutil

sys.path.insert(0, str(Path(__file__).parent))
import benchlib  # noqa: E402
from benchlib import GpuSampler, background_load, frame_from_packed, jpeg_list, nv12_arrays, snapshot, \
    yuy2_frames_bytes  # noqa: E402

DIMS = {"720p": (1280, 720), "1080p": (1920, 1080)}
# encoder -> (default 4:2:0 fmt, 4:2:2 fmt or None, options, intra gop, hw device for hwctx or None)
ENC = {
    "h264_qsv": ("nv12", None, {}, 1, None),
    "hevc_qsv": ("nv12", None, {}, 1, None),
    "vp9_qsv": ("nv12", None, {}, 1, None),
    "av1_qsv": ("nv12", None, {}, 1, None),
    "mjpeg_qsv": ("nv12", None, {}, 1, None),
    "h264_nvenc": ("nv12", None, {"preset": "p4", "tune": "ll"}, 0, None),
    "hevc_nvenc": ("nv12", None, {"preset": "p4", "tune": "ll"}, 0, None),
    "h264_mf": ("nv12", None, {"hw_encoding": "1"}, 1, None),
    "hevc_mf": ("nv12", None, {"hw_encoding": "1"}, 1, None),
    "h264_d3d12va": ("nv12", None, {}, 1, "d3d12va"),
    "hevc_d3d12va": ("nv12", None, {}, 1, "d3d12va"),
    "libsvtav1": ("yuv420p", None, {"preset": "10"}, 1, None),
    "libvpx-vp9": ("yuv420p", "yuv422p", {"deadline": "realtime", "cpu-used": "8", "row-mt": "1"}, 1, None),
    "mjpeg": ("yuvj420p", "yuvj422p", {}, 1, None),
    "ffv1": ("yuv420p", "yuv422p", {"level": "3", "slices": "16"}, 1, None),
    "none": ("nv12", "yuv422p", {}, 1, None),
}


def make_enc(name: str, w: int, h: int, fmt: str, gop: str):
    if name == "none":
        return None
    f420, f422, opts, igop, hw = ENC[name]
    kw = {}
    if hw:
        from av.codec.hwaccel import HWAccel  # noqa: PLC0415
        kw["hwaccel"] = HWAccel(hw)
    cc = av.CodecContext.create(name, "w", **kw)
    cc.width, cc.height, cc.pix_fmt = w, h, fmt
    cc.time_base = Fraction(1, 30)
    cc.framerate = Fraction(30, 1)
    cc.max_b_frames = 0
    cc.gop_size = igop if gop == "intra" else 30
    cc.options = dict(opts)
    cc.open()
    return cc


class Source:
    """Produces one VideoFrame per call in `fmt`, doing the per-frame work a camera loop would do."""

    def __init__(self, kind: str, size: str, fmt: str):
        self.kind, self.fmt = kind, fmt
        self.w, self.h = DIMS[size]
        self.i = 0
        if kind == "nv12":
            self.data = nv12_arrays(size)
        elif kind in ("yuy2", "yuy2native"):
            self.data = yuy2_frames_bytes(size)
        else:
            self.data = jpeg_list(size)
            dec = {"mjpeg_cpu": "mjpeg", "mjpeg_qsv": "mjpeg_qsv", "mjpeg_cuvid": "mjpeg_cuvid"}[kind]
            self.dec = av.CodecContext.create(dec, "r")
            self.pending: list = []

    def next(self) -> av.VideoFrame:
        k = self.i % len(self.data)
        self.i += 1
        if self.kind == "nv12":
            return av.VideoFrame.from_ndarray(self.data[k], format="nv12")
        if self.kind in ("yuy2", "yuy2native"):
            f = frame_from_packed(self.data[k], "yuyv422", self.w, self.h)
            return f if self.fmt == "yuyv422" else f.reformat(format=self.fmt)
        while not self.pending:
            self.pending += list(self.dec.decode(av.Packet(self.data[k])))
            if not self.pending:
                k = self.i % len(self.data)
                self.i += 1
        f = self.pending.pop(0)
        if f.format.name == self.fmt:
            g = f
        elif self.fmt.startswith("yuvj"):
            g = f.reformat(format=self.fmt)
        else:  # full-range JPEG samples -> limited range (PyAV keeps full range unless told; see NOTES_functional)
            g = f.reformat(format=self.fmt, dst_color_range=1)
        # decoded MJPEG frames carry pict_type=I and reformat() copies it; encoders would then make every
        # frame a keyframe (measured: functional_pyav19.md, stage gop_pictreset). Reset so gop30 is real.
        g.pict_type = PictureType.NONE
        return g


def one_run(enc: str, size: str, src_kind: str, fmt: str, gop: str, n: int) -> dict:
    w, h = DIMS[size]
    rec: dict = {"encoder": enc, "size": size, "source": src_kind, "pix_fmt": fmt, "gop": gop, "frames": n}
    try:
        src = Source(src_kind, size, fmt)
        t = time.perf_counter()
        cc = make_enc(enc, w, h, fmt, gop)
        rec["open_s"] = round(time.perf_counter() - t, 4)
        # warm-up (untimed): 10 frames through the full pipeline
        for i in range(10):
            f = src.next()
            f.pts = i
            if cc:
                cc.encode(f)
        proc = psutil.Process()
        nbytes, frames_out = 0, 0
        with GpuSampler() as gs:
            c0 = proc.cpu_times()
            t0 = time.perf_counter()
            for i in range(10, 10 + n):
                f = src.next()
                f.pts = i
                if cc:
                    for p in cc.encode(f):
                        nbytes += p.size
                        frames_out += 1
            if cc:
                for p in cc.encode(None):
                    nbytes += p.size
                    frames_out += 1
            wall = time.perf_counter() - t0
            c1 = proc.cpu_times()
        cpu = (c1.user - c0.user) + (c1.system - c0.system)
        rec.update(ok=True, wall_s=round(wall, 4), fps=round(n / wall, 2), cpu_s=round(cpu, 4),
                   cpu_ms_per_frame=round(1000 * cpu / n, 3), cpu_cores=round(cpu / wall, 3),
                   bytes_per_frame=round(nbytes / max(frames_out, 1)), packets=frames_out, gpu=gs.summary())
    except Exception as e:  # noqa: BLE001
        rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--encoders", required=True)
    ap.add_argument("--sizes", default="720p,1080p")
    ap.add_argument("--sources", default="nv12,yuy2,mjpeg_cpu")
    ap.add_argument("--gops", default="intra,gop30")
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--native422", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("--outdir", default="")
    ap.add_argument("--no-bg", action="store_true", help="skip the 10 s background-load record (smoke only)")
    a = ap.parse_args()
    if a.outdir:
        benchlib.BENCH = Path(a.outdir)
    out = {"bench": "encode_stream", "args": vars(a), "system_before": snapshot(),
           "background_load_before": None if a.no_bg else background_load(), "runs": [], "summary": []}
    for enc in a.encoders.split(","):
        f420, f422 = ENC[enc][0], ENC[enc][1]
        for size in a.sizes.split(","):
            for src in a.sources.split(","):
                fmts = []
                if src == "yuy2native":
                    fmts = ["yuyv422"]
                else:
                    # 4:2:2 runs only from 4:2:2 sources (NV12 and mjpeg_qsv output are 4:2:0; upsampling would be meaningless)
                    fmts = [f420] + ([f422] if a.native422 and f422 and src not in ("nv12", "mjpeg_qsv") else [])
                for fmt in fmts:
                    for gop in (a.gops.split(",") if enc != "none" else ["intra"]):
                        reps = [one_run(enc, size, src, fmt, gop, a.frames) for _ in range(a.reps)]
                        out["runs"] += reps
                        good = [r for r in reps if r.get("ok")]
                        s = {"encoder": enc, "size": size, "source": src, "pix_fmt": fmt, "gop": gop,
                             "reps_ok": len(good)}
                        if good:
                            s.update(fps_median=statistics.median(r["fps"] for r in good),
                                     cpu_ms_per_frame_median=statistics.median(r["cpu_ms_per_frame"] for r in good),
                                     cpu_cores_median=statistics.median(r["cpu_cores"] for r in good),
                                     bytes_per_frame_median=statistics.median(r["bytes_per_frame"] for r in good))
                        else:
                            s["error"] = reps[0].get("error")
                        out["summary"].append(s)
                        print(s)
    out["system_after"] = snapshot()
    benchlib.write(f"encode_stream_{a.label or 'run'}", out)


if __name__ == "__main__":
    main()
