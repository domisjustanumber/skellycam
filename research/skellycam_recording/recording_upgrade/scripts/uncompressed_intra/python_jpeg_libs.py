# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "numpy==2.2.6",
#   "simplejpeg==1.9.0",
#   "PyTurboJPEG==2.6.1",
#   "imagecodecs==2026.10.10",
#   "opencv-python==5.0.0.93",
# ]
# ///
"""Functional test (no timing) of Python-side still-image encoders for per-frame intra storage of
uncompressed camera formats: can each one take the camera's YUV planes / Bayer data directly (no RGB
conversion), what JPEG subsampling comes out, and are the lossless modes bit-exact?

  * simplejpeg.encode_jpeg_yuv_planes (libjpeg-turbo, raw YUV planes in)
  * PyTurboJPEG TurboJPEG.encode_from_yuv (needs an external turbojpeg DLL; --turbojpeg-dll)
  * cv2.imencode (BGR/gray in only -> needs YUV->BGR) incl. 4:2:2 sampling flag, .jxl/.jp2/.png/.tiff writers
  * imagecodecs: jpeg8 (libjpeg-turbo, incl. lossless SOF3 at 12 bit), ljpeg, jpegls, jpeg2k (reversible),
    jpegxl (lossless + lossy), png, qoi

Isolated (exact pins in the PEP 723 header; the skellycam venv is not touched):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/python_jpeg_libs.py \
      --turbojpeg-dll "C:/Program Files/Audacity/turbojpeg.dll"
Pinned venv (only OpenCV 4.12 is present there; the other libs are reported missing):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/python_jpeg_libs.py
Writes results/uncompressed_intra/python_jpeg_libs_<tag>.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uintra_frames as uf  # noqa: E402

RESULTS = Path(__file__).resolve().parents[2] / "results" / "uncompressed_intra"


def sof_info(b: bytes) -> dict:
    """Parse the first SOFn: marker, precision, dims, per-component sampling factors."""
    pos = 2
    while pos + 4 <= len(b):
        if b[pos] != 0xFF:
            return {"error": f"bad marker at {pos}"}
        m = b[pos + 1]
        ln = struct.unpack(">H", b[pos + 2 : pos + 4])[0]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            p, hh, ww, nc = b[pos + 4], *struct.unpack(">HH", b[pos + 5 : pos + 9]), b[pos + 9]
            comps = [f"{b[pos + 11 + 3 * i] >> 4}x{b[pos + 11 + 3 * i] & 15}" for i in range(nc)]
            return {"sof": hex(0xFF00 | m), "precision": p, "w": ww, "h": hh, "sampling": comps}
        pos += 2 + ln
    return {"error": "no SOF"}


def sha(a) -> str:
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def psnr(a, b, peak=255.0):
    d = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return float("inf") if d == 0 else round(float(10 * np.log10(peak**2 / d)), 2)


def run(name, fn, out):
    try:
        out[name] = fn()
    except Exception as e:  # noqa: BLE001
        out[name] = {"error": f"{type(e).__name__}: {e}"}
    print(f"{name:40s} {json.dumps(out[name])[:200]}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turbojpeg-dll", default=None)
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    yuy, w, h = uf.load_yuy2("c930e_1080p_yuy2", 1)
    yuyv = yuy[0]
    y, u, v = uf.yuyv_split(yuyv)
    i420 = uf.derive("yuv420p", yuyv, w, h)[0]
    m12 = uf.derive("bayer_rggb16le", yuyv, w, h)[0][0].view("<u2")
    m8 = uf.derive("bayer_rggb8", yuyv, w, h)[0][0]
    rgb = uf.yuyv_to_rgb24(yuyv)
    res: dict = {"versions": {"python": sys.version, "numpy": np.__version__}, "tests": {}}
    T = res["tests"]
    mods = {}
    for m in ("simplejpeg", "turbojpeg", "imagecodecs", "cv2"):
        try:
            mods[m] = importlib.import_module(m)
            res["versions"][m] = getattr(mods[m], "__version__", "?")
        except Exception as e:  # noqa: BLE001
            res["versions"][m] = f"not importable: {e}"

    if "simplejpeg" in mods:
        sj = mods["simplejpeg"]

        def sj_422():
            b = sj.encode_jpeg_yuv_planes(y, u, v, quality=90)
            d = sj.decode_jpeg(b, colorspace="RGB")
            r = {**sof_info(b), "bytes": len(b), "psnr_rgb_vs_numpy_bt601_limited_rgb": psnr(d, rgb)}
            if "imagecodecs" in mods:  # decode without colour conversion: compare Y samples directly
                ycc = mods["imagecodecs"].jpeg8_decode(b, colorspace="YCbCr", outcolorspace="YCbCr")
                r["psnr_Y_plane_vs_input_Y"] = psnr(ycc[:, :, 0], y)
            return r

        def sj_420():
            b = sj.encode_jpeg_yuv_planes(*i420, quality=90)
            return {**sof_info(b), "bytes": len(b)}

        def sj_gray():
            b = sj.encode_jpeg_yuv_planes(y, None, None, quality=90)
            return {**sof_info(b), "bytes": len(b)}

        def sj_nv12_direct():
            nv = uf.derive("nv12", yuyv, w, h)[0]
            return sj.encode_jpeg_yuv_planes(nv[0], nv[1], None, quality=90)

        run("simplejpeg.yuv_planes_422_from_yuy2", sj_422, T)
        run("simplejpeg.yuv_planes_420_from_nv12", sj_420, T)
        run("simplejpeg.yuv_planes_gray", sj_gray, T)
        run("simplejpeg.nv12_interleaved_uv", sj_nv12_direct, T)

    if "turbojpeg" in mods:
        tjm = mods["turbojpeg"]

        def tj_422():
            tj = tjm.TurboJPEG(a.turbojpeg_dll) if a.turbojpeg_dll else tjm.TurboJPEG()
            buf = np.concatenate([y.ravel(), u.ravel(), v.ravel()])
            b = tj.encode_from_yuv(buf, h, w, quality=90, jpeg_subsample=tjm.TJSAMP_422)
            return {**sof_info(b), "bytes": len(b), "dll": a.turbojpeg_dll or "auto"}

        def tj_no_dll():
            tjm.TurboJPEG()
            return {"found": True}

        run("turbojpeg.auto_locate_library", tj_no_dll, T)
        if a.turbojpeg_dll:
            run("turbojpeg.encode_from_yuv_422", tj_422, T)

    if "cv2" in mods:
        cv2 = mods["cv2"]
        res["versions"]["cv2"] = cv2.__version__

        def cv_422():
            bgr = cv2.cvtColor(yuyv.reshape(h, w, 2), cv2.COLOR_YUV2BGR_YUY2)
            ok, b = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 90,
                                               cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_422])
            return {**sof_info(b.tobytes()), "bytes": int(b.size), "ok": bool(ok), "input": "BGR (cvtColor YUV2BGR_YUY2 first)"}

        def cv_yuyv_direct():
            ok, b = cv2.imencode(".jpg", yuyv.reshape(h, w, 2))
            return {"ok": bool(ok), "note": "2-channel array passed straight in", **(sof_info(b.tobytes()) if ok else {})}

        def cv_writers():
            out = {}
            for ext in (".jxl", ".jp2", ".png", ".tiff", ".webp", ".avif", ".pgm"):
                try:
                    out[ext] = bool(cv2.haveImageWriter("x" + ext))
                except Exception as e:  # noqa: BLE001
                    out[ext] = f"{type(e).__name__}: {e}"
            return out

        def cv_png16():
            ok, b = cv2.imencode(".png", m12)
            d = cv2.imdecode(b, cv2.IMREAD_UNCHANGED)
            return {"ok": bool(ok), "bytes": int(b.size), "bit_exact": sha(d) == sha(m12), "dtype": str(d.dtype)}

        def cv_jxl_lossless16():
            ok, b = cv2.imencode(".jxl", m12, [cv2.IMWRITE_JPEGXL_DISTANCE, 0])
            d = cv2.imdecode(b, cv2.IMREAD_UNCHANGED)
            return {"ok": bool(ok), "bytes": int(b.size), "bit_exact": sha(d) == sha(m12)}

        run("cv2.imencode_jpg_422_via_bgr", cv_422, T)
        run("cv2.imencode_yuyv_direct", cv_yuyv_direct, T)
        run("cv2.have_image_writer", cv_writers, T)
        run("cv2.png_bayer12_in_u16", cv_png16, T)
        run("cv2.jxl_lossless_bayer12", cv_jxl_lossless16, T)

    if "imagecodecs" in mods:
        ic = mods["imagecodecs"]
        res["versions"]["imagecodecs_libs"] = ic.version()

        def lossless(enc, dec, data, **kw):
            def f():
                b = enc(data, **kw)
                d = dec(b)
                return {"bytes": len(b), "bit_exact": sha(np.asarray(d).astype(data.dtype)) == sha(data) and np.asarray(d).shape == data.shape,
                        **({"sof": sof_info(bytes(b))} if bytes(b[:2]) == b"\xff\xd8" else {})}
            return f

        run("imagecodecs.jpeg8_lossless_sof3_bayer12", lossless(ic.jpeg8_encode, ic.jpeg8_decode, m12, lossless=True, bitspersample=12), T)
        run("imagecodecs.jpeg8_lossless_sof3_bayer8", lossless(ic.jpeg8_encode, ic.jpeg8_decode, m8, lossless=True), T)
        run("imagecodecs.ljpeg_bayer12", lossless(ic.ljpeg_encode, ic.ljpeg_decode, m12, bitspersample=12), T)
        run("imagecodecs.jpegls_bayer12", lossless(ic.jpegls_encode, ic.jpegls_decode, m12, level=0), T)
        run("imagecodecs.jpeg2k_reversible_bayer12", lossless(ic.jpeg2k_encode, ic.jpeg2k_decode, m12, level=0, reversible=True, bitspersample=12), T)
        run("imagecodecs.jpegxl_lossless_bayer12_e1", lossless(ic.jpegxl_encode, ic.jpegxl_decode, m12, lossless=True, effort=1, bitspersample=12), T)
        run("imagecodecs.jpegxl_lossless_bayer12_e3", lossless(ic.jpegxl_encode, ic.jpegxl_decode, m12, lossless=True, effort=3, bitspersample=12), T)
        run("imagecodecs.jpegxl_lossless_gray8_e1", lossless(ic.jpegxl_encode, ic.jpegxl_decode, y, lossless=True, effort=1), T)
        run("imagecodecs.png_bayer12", lossless(ic.png_encode, ic.png_decode, m12), T)
        run("imagecodecs.jpegls_gray8", lossless(ic.jpegls_encode, ic.jpegls_decode, y, level=0), T)

        def jxl_lossy_rgb():
            b = ic.jpegxl_encode(rgb, distance=1.0, effort=1)
            return {"bytes": len(b), "psnr_rgb": psnr(ic.jpegxl_decode(b), rgb)}

        def jpeg8_ycbcr_in():
            # can libjpeg-turbo via imagecodecs take YCbCr samples directly? (interleaved 4:4:4 only)
            ycc = np.stack([y, np.repeat(u, 2, axis=1), np.repeat(v, 2, axis=1)], axis=-1)
            b = ic.jpeg8_encode(ycc, level=90, colorspace="YCbCr", outcolorspace="YCbCr", subsampling="422")
            return {"bytes": len(b), **sof_info(bytes(b))}

        def jpeg8_rgb_422():
            b = ic.jpeg8_encode(rgb, level=90, subsampling="422")
            return {"bytes": len(b), **sof_info(bytes(b))}

        run("imagecodecs.jpegxl_lossy_rgb_d1_e1", jxl_lossy_rgb, T)
        run("imagecodecs.jpeg8_from_ycbcr444_interleaved", jpeg8_ycbcr_in, T)
        run("imagecodecs.jpeg8_from_rgb_422", jpeg8_rgb_422, T)

    tag = a.tag or ("uv" if "simplejpeg" in mods else "venv")
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"python_jpeg_libs_{tag}.json"
    out.write_text(json.dumps(res, indent=1, default=str))
    print("wrote", out)


if __name__ == "__main__":
    main()
