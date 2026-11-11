"""Bayer: store raw vs debayer first - functional / information-loss check (no timing).

Input: 12-bit and 8-bit RGGB mosaics derived from a real YUY2 1080p frame (uintra_frames.derive).
Demosaic methods: libswscale (PyAV frame.reformat bayer_* -> rgb48le / rgb24) and OpenCV cvtColor
(bilinear, EA = edge-aware, VNG). For each:
  * are the original CFA samples still present at their sites in the RGB output (mosaic recoverable)?
  * if the RGB result is then converted to 8-bit yuv420p (what a typical video encoder is fed), how far is
    the re-sampled mosaic from the original (max abs error, PSNR on the 12-/8-bit scale)?
  * FFV1 (level 3, g=1) bytes/frame for the debayered RGB vs the raw mosaic.
Run (pinned venv: PyAV 18.0.0, OpenCV 4.12.0):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bayer_debayer_check.py
Writes results/uncompressed_intra/bayer_debayer_check.json
"""
from __future__ import annotations

import io
import json
import sys
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uintra_frames as uf  # noqa: E402

RESULTS = Path(__file__).resolve().parents[2] / "results" / "uncompressed_intra"


def mosaic_of(rgb: np.ndarray) -> np.ndarray:
    """Re-sample an RGGB mosaic from an (h, w, 3) RGB image."""
    return uf.bayer8_from_rgb(rgb) if rgb.dtype == np.uint8 else _m16(rgb)


def _m16(rgb):
    h, w, _ = rgb.shape
    m = np.empty((h, w), rgb.dtype)
    m[0::2, 0::2] = rgb[0::2, 0::2, 0]
    m[0::2, 1::2] = rgb[0::2, 1::2, 1]
    m[1::2, 0::2] = rgb[1::2, 0::2, 1]
    m[1::2, 1::2] = rgb[1::2, 1::2, 2]
    return m


def psnr(a, b, peak):
    d = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return float("inf") if d == 0 else round(float(10 * np.log10(peak**2 / d)), 2)


def ffv1_bytes(planes, pix_fmt, w, h) -> int:
    buf = io.BytesIO()
    with av.open(buf, "w", format="matroska") as oc:
        st = oc.add_stream("ffv1", rate=30, options={"level": "3", "slices": "4", "slicecrc": "1"})
        st.width, st.height, st.pix_fmt = w, h, pix_fmt
        st.codec_context.gop_size = 1
        fr = uf.make_frame(planes, pix_fmt, w, h)
        fr.pts, fr.time_base = 0, Fraction(1, 30)
        n = 0
        for p in list(st.encode(fr)) + list(st.encode(None)):
            n += p.size
            oc.mux(p)
    return n


def via_yuv420p8(rgb: np.ndarray, bits: int) -> np.ndarray:
    """RGB -> 8-bit yuv420p (swscale) -> back to RGB at the original bit depth (as a viewer would)."""
    h, w, _ = rgb.shape
    if bits == 8:
        fr = uf.make_frame([rgb.reshape(h, w * 3)], "rgb24", w, h)
        back = fr.reformat(format="yuv420p").reformat(format="rgb24")
        return uf.read_planes(back, "rgb24")[0].reshape(h, w, 3)
    rgb16 = (rgb.astype(np.uint16) << (16 - bits))
    fr = uf.make_frame([uf.to_u8_rows(rgb16.reshape(h, w * 3))], "rgb48le", w, h)
    back = fr.reformat(format="yuv420p").reformat(format="rgb48le")
    out = uf.read_planes(back, "rgb48le")[0].view("<u2").reshape(h, w, 3)
    return (out >> (16 - bits)).astype(np.uint16)


def main() -> None:
    yuy, w, h = uf.load_yuy2("c930e_1080p_yuy2", 1)
    m12 = uf.derive("bayer_rggb16le", yuy[0], w, h)[0][0].view("<u2").reshape(h, w)
    m8 = uf.derive("bayer_rggb8", yuy[0], w, h)[0][0]
    res = {"versions": {"av": av.__version__, "ffmpeg": getattr(av, "ffmpeg_version_info", "?"), "cv2": cv2.__version__,
                        "numpy": np.__version__}, "frame": "c930e_1080p_yuy2 frame 0, derived RGGB", "methods": {}}
    raw_ffv1 = {"bayer12_as_gray16le": ffv1_bytes([uf.to_u8_rows(m12)], "gray16le", w, h),
                "bayer12_quad_as_gray16le": ffv1_bytes([uf.to_u8_rows(uf.quad_from_mosaic(m12))], "gray16le", w, h),
                "bayer8_as_gray": ffv1_bytes([m8], "gray", w, h),
                "bayer8_quad_as_gray": ffv1_bytes([uf.quad_from_mosaic(m8)], "gray", w, h)}
    res["raw_mosaic_ffv1_bytes"] = raw_ffv1
    res["raw_bytes"] = {"bayer12_in_16bit": m12.nbytes, "bayer12_packed_raw12": m12.size * 3 // 2, "bayer8": m8.nbytes}

    def swscale(bits):
        if bits == 12:
            fr = uf.make_frame([uf.to_u8_rows(m12)], "bayer_rggb16le", w, h).reformat(format="rgb48le")
            return uf.read_planes(fr, "rgb48le")[0].view("<u2").reshape(h, w, 3)
        fr = uf.make_frame([m8], "bayer_rggb8", w, h).reformat(format="rgb24")
        return uf.read_planes(fr, "rgb24")[0].reshape(h, w, 3)

    def cvdm(code_name):
        def f(bits):
            src = m12 if bits == 12 else m8
            bgr = cv2.cvtColor(src, getattr(cv2, code_name))
            return bgr[:, :, ::-1].copy()
        return f

    methods = {"swscale_bilinear": swscale}
    # OpenCV names Bayer patterns by the 2nd-row/2nd-column 2x2 block; probe both candidate codes for RGGB
    for base in ("COLOR_BayerRG2BGR", "COLOR_BayerBG2BGR"):
        for suf in ("", "_EA", "_VNG"):
            methods[f"cv2_{base[6:]}{suf}"] = cvdm(base + suf)
    for name, fn in methods.items():
        for bits in (12, 8):
            key = f"{name}_{bits}bit"
            try:
                rgb = fn(bits)
            except Exception as e:  # noqa: BLE001
                res["methods"][key] = {"error": f"{type(e).__name__}: {e}"}
                continue
            src = m12 if bits == 12 else m8
            if bits == 12 and rgb.max() > 4095:  # swscale output is 16-bit scaled; bring back to 12-bit scale
                rgb_s = (rgb >> 4).astype(np.uint16)
                scale_note = "rgb48le output >> 4 to compare on the 12-bit scale"
            else:
                rgb_s, scale_note = rgb, None
            remos = mosaic_of(rgb_s)
            r = {"cfa_samples_preserved_exactly": bool(np.array_equal(remos, src)),
                 "cfa_max_abs_err": int(np.max(np.abs(remos.astype(np.int32) - src.astype(np.int32)))),
                 "scale_note": scale_note}
            r["ffv1_bytes_rgb"] = (ffv1_bytes([uf.to_u8_rows(c) for c in (rgb_s[:, :, 1], rgb_s[:, :, 2], rgb_s[:, :, 0])],
                                              "gbrp12le", w, h) if bits == 12 else
                                   ffv1_bytes([np.dstack([rgb_s[:, :, ::-1], np.zeros((h, w), np.uint8)]).reshape(h, w * 4)],
                                              "bgr0", w, h))  # FFV1 has no 8-bit gbrp; bgr0 is its 8-bit RGB format
            v = via_yuv420p8(rgb_s, bits)
            rm2 = mosaic_of(v)
            r["after_yuv420p8_cfa_max_abs_err"] = int(np.max(np.abs(rm2.astype(np.int32) - src.astype(np.int32))))
            r["after_yuv420p8_cfa_psnr"] = psnr(rm2, src, 4095 if bits == 12 else 255)
            res["methods"][key] = r
            print(f"{key:34s} {json.dumps(r)}")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "bayer_debayer_check.json").write_text(json.dumps(res, indent=1))
    print("raw mosaic FFV1 bytes:", raw_ffv1)
    print("wrote", RESULTS / "bayer_debayer_check.json")


if __name__ == "__main__":
    main()
