# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "scipy==1.16.2", "simplejpeg==1.9.0",
#                 "nvidia-nvimgcodec-cu12[nvjpeg]==0.10.0.9"]
# ///
"""Diagnostic (FUNCTIONAL): why nvJPEG's PSNR-Y saturates near 43 dB in the sweep.

On the 16 real YUY2 1080p frames and 8 decoded camera 1080p JPEGs:
  A. RGB step alone: source -> rgb24 (PyAV swscale, BT.601, source range) -> Y computed in float with the JFIF
     BT.601 full-range formula -> source domain; PSNR-Y vs source Y, mean signed Y error, share of clipped RGB samples.
  B. libjpeg-turbo from the same RGB (simplejpeg.encode_jpeg, colorspace RGB, 4:2:2, q 95 and 100).
  C. nvJPEG (nvjpeg_cuda_encoder) from the same RGB, CSS_422, q 95 and 100.
  D. libjpeg-turbo from YUV planes (the sweep's jpeg_turbo path), q 95 and 100.
B-D: decode with PyAV 'mjpeg' and report PSNR-Y and the mean signed Y error vs the source.
Writes results/intra_compare/nvjpeg_rgb_diag.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import av
import numpy as np
import simplejpeg

sys.path.insert(0, str(Path(__file__).parent))
import iclib  # noqa: E402
from nvidia import nvimgcodec as nv  # noqa: E402


def yerr(s, jb):
    dp, _ = iclib.decode_jpeg(jb, av.CodecContext.create("mjpeg", "r"))
    Y = iclib.map_range(dp, "full", s.rng, as_float=True)[0]
    d = Y - s.y.astype(np.float32)
    return iclib.psnr_mse(float(np.mean(d * d))), float(d.mean())


def main() -> None:
    enc = nv.Encoder(encoder_ids=["nvjpeg_cuda_encoder"])
    rows = []
    for inp in ("yuy2_1080p", "mjpeg_1080p"):
        srcs = iclib.load_input(inp)
        srcs = srcs if inp == "yuy2_1080p" else srcs[:4] + srcs[19:23]
        acc: dict = {}
        for s in srcs:
            fmt = "yuvj422p" if s.rng == "full" else "yuv422p"
            f = iclib.frame_from_planes(fmt, [s.y, s.u, s.v], s.w, s.h)
            rgb_sws = f.reformat(format="rgb24", src_color_range=2 if s.rng == "full" else 1).to_ndarray()
            rgb_np = iclib.rgb_from_src(s)
            for tag, rgb in (("sws", rgb_sws), ("np", rgb_np)):
                one(acc, s, rgb, tag, enc)
        row = {"input": inp, "frames": len(srcs)}
        row.update({k: round(float(np.mean(v)), 4) for k, v in acc.items()})
        rows.append(row)
        print(json.dumps(row, indent=1))
    (iclib.RESULTS / "nvjpeg_rgb_diag.json").write_text(json.dumps({"nvimgcodec": "0.10.0.9", "rows": rows}, indent=1))


def one(acc, s, rgb, tag, enc):
    """A-D for one RGB rendition (tag 'sws' = PyAV swscale, 'np' = iclib.rgb_from_src exact float BT.601)."""
    r, g, b = [rgb[..., i].astype(np.float32) for i in range(3)]
    yj = 0.299 * r + 0.587 * g + 0.114 * b
    y_src_dom = yj if s.rng == "full" else iclib.full2lim_f(yj)
    d = y_src_dom - s.y.astype(np.float32)
    acc.setdefault(tag + "_" + "A_rgb_step_psnr_y", []).append(iclib.psnr_mse(float(np.mean(d * d))))
    acc.setdefault(tag + "_" + "A_rgb_step_mean_y_err", []).append(float(d.mean()))
    acc.setdefault(tag + "_" + "A_clipped_rgb_share", []).append(float(np.mean((rgb == 0) | (rgb == 255))))
    for q in (95, 100):
        p, e = yerr(s, simplejpeg.encode_jpeg(np.ascontiguousarray(rgb), quality=q, colorspace="RGB",
                                              colorsubsampling="422"))
        acc.setdefault(tag + "_" + f"B_turbo_rgb_q{q}_psnr_y", []).append(p)
        acc.setdefault(tag + "_" + f"B_turbo_rgb_q{q}_mean_y_err", []).append(e)
        prm = nv.EncodeParams(quality_type=nv.QualityType.QUALITY, quality_value=q,
                              chroma_subsampling=nv.ChromaSubsampling.CSS_422)
        p, e = yerr(s, bytes(enc.encode(np.ascontiguousarray(rgb), "jpeg", params=prm)))
        acc.setdefault(tag + "_" + f"C_nvjpeg_rgb_q{q}_psnr_y", []).append(p)
        acc.setdefault(tag + "_" + f"C_nvjpeg_rgb_q{q}_mean_y_err", []).append(e)
        planes = iclib.map_range([s.y, s.u, s.v], s.rng, "full")
        p, e = yerr(s, simplejpeg.encode_jpeg_yuv_planes(*[np.ascontiguousarray(x) for x in planes], quality=q))
        acc.setdefault(tag + "_" + f"D_turbo_yuv_q{q}_psnr_y", []).append(p)
        acc.setdefault(tag + "_" + f"D_turbo_yuv_q{q}_mean_y_err", []).append(e)


if __name__ == "__main__":
    main()
