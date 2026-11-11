# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "scipy==1.16.2"]
# ///
"""FUNCTIONAL check of the quality knobs used by sweep.py (PyAV 19.0.2), 3 intra frames of real YUY2 1080p.

1. H.264/HEVC (h264/hevc_nvenc constqp, h264/hevc_qsv CQP, libx264, libx265) at QP 25, with FFmpeg's default
   i_qfactor (-0.8) and with i_qfactor=1, i_qoffset=0: bytes per packet and the encoder's quality-stats side data
   (AV_PKT_DATA_QUALITY_STATS, quality/FF_QP2LAMBDA; nvenc reports frameAvgQP-1, nvenc.c:2646-2647).
2. FFmpeg 'mjpeg': global_quality+qscale flag as codec options vs qmin=qmax clamping.
3. mjpeg_qsv: global_quality 50 vs 90.
Writes results/intra_compare/knob_check.json.
"""
from __future__ import annotations

import json
import sys
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import iclib  # noqa: E402


def enc(name, fmt, frame, opts, gop=1, n=3):
    cc = av.CodecContext.create(name, "w")
    cc.width, cc.height, cc.pix_fmt = frame.width, frame.height, fmt
    cc.time_base, cc.framerate = Fraction(1, 30), Fraction(30, 1)
    cc.max_b_frames, cc.gop_size = 0, gop
    cc.options = dict(opts)
    cc.open()
    out = []
    for i in range(n):
        frame.pts = i
        out += list(cc.encode(frame))
    out += list(cc.encode(None))
    return [{"bytes": p.size, "key": bool(p.is_keyframe), "stats_q_over_118": iclib.stats_qp(p)} for p in out]


def main() -> None:
    s = iclib.load_input("yuy2_1080p")[0]
    lim420 = iclib.map_range([s.y, s.u420, s.v420], "lim", "lim")
    nv12 = av.VideoFrame.from_ndarray(iclib.nv12_array(*lim420), format="nv12")
    yuv420 = iclib.frame_from_planes("yuv420p", lim420, s.w, s.h)
    full = iclib.map_range([s.y, s.u, s.v], "lim", "full")
    rep: dict = {"pyav": av.__version__, "source": f"{s.cam} frame {s.idx}", "iqfactor": [], "mjpeg": [], "mjpeg_qsv": []}
    cases = [("h264_nvenc", nv12, "nv12", {"preset": "p4", "tune": "ll", "rc": "constqp", "qp": "25"}, 0),
             ("hevc_nvenc", nv12, "nv12", {"preset": "p4", "tune": "ll", "rc": "constqp", "qp": "25"}, 0),
             ("h264_qsv", nv12, "nv12", {"flags": "+qscale", "global_quality": str(25 * 118)}, 1),
             ("hevc_qsv", nv12, "nv12", {"flags": "+qscale", "global_quality": str(25 * 118)}, 1),
             ("libx264", yuv420, "yuv420p", {"preset": "veryfast", "qp": "25"}, 1),
             ("libx265", yuv420, "yuv420p", {"preset": "ultrafast", "qp": "25", "x265-params": "log-level=error"}, 1)]
    for name, fr, fmt, base, gop in cases:
        for extra in ({}, {"i_qfactor": "1", "i_qoffset": "0"}):
            try:
                rep["iqfactor"].append({"encoder": name, "options": {**base, **extra}, "packets": enc(name, fmt, fr, {**base, **extra}, gop)})
            except Exception as e:  # noqa: BLE001
                rep["iqfactor"].append({"encoder": name, "options": {**base, **extra}, "error": f"{type(e).__name__}: {e}"[:300]})
    fj = iclib.frame_from_planes("yuvj422p", full, s.w, s.h)
    for opts in ({"flags": "+qscale", "global_quality": str(2 * 118)}, {"flags": "+qscale", "global_quality": str(12 * 118)},
                 {"qmin": "2", "qmax": "2"}, {"qmin": "12", "qmax": "12"}, {}):
        rep["mjpeg"].append({"options": opts, "packets": enc("mjpeg", "yuvj422p", fj, opts)})
    fy = iclib.frame_from_planes("yuyv422", [iclib.yuyv_pack(*full)], s.w, s.h)
    for q in (50, 90):
        rep["mjpeg_qsv"].append({"options": {"global_quality": str(q)}, "packets": enc("mjpeg_qsv", "yuyv422", fy, {"global_quality": str(q)})})
    (iclib.RESULTS / "knob_check.json").write_text(json.dumps(rep, indent=1))
    for k in ("iqfactor", "mjpeg", "mjpeg_qsv"):
        for r in rep[k]:
            print(k, r.get("encoder", ""), r["options"], [(p["bytes"], p["stats_q_over_118"]) for p in r.get("packets", [])][:1], r.get("error", ""))


if __name__ == "__main__":
    main()
