# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Functional matrix (no timing): source pixel format x intra codec config x container, via PyAV.

For every (source, config) it records:
  * path      : "native" (encoder lists the source pix_fmt), an exact numpy re-layout / re-tag that is
                reversible (e.g. yuyv422->yuv422p, bayer_rggb16le->gray16le, gray->yuv420p with neutral
                chroma), "swscale" (lossy libswscale conversion, only for non-lossless configs), or no path;
  * whether the encoder opened, the muxer accepted it, every packet is flagged keyframe,
  * decoded frames == fed frames byte-for-byte (sha256 of tight planes), and whether the ORIGINAL
    source bytes are recovered after inverting the re-layout,
  * bytes/frame (mean packet size; size is deterministic, not a timing number),
  * truncation: a copy cut at 50 % of its size is re-opened - frames decoded and the error.
No timing is measured here (other agents share the machine).

Pinned venv (PyAV 18.0.0):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/functional_matrix.py
Isolated PyAV 19.0.2 (PEP 723 header):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/functional_matrix.py
Options: --frames N (default 4, real YUY2 1080p frames), --only <substring of config id>, --sources a,b, --keep
Writes results/uncompressed_intra/functional_matrix_pyav<ver>.json; media written under
C:/Users/Dom/Documents/skellycam-raw/.../uncompressed_intra/functional/ and deleted unless --keep.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

import av
import av.logging
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uintra_frames as uf  # noqa: E402

RESULTS = Path(__file__).resolve().parents[2] / "results" / "uncompressed_intra"
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/functional") / f"pyav{av.__version__}"

# id, codec, container ext, options, gop, lossless-intended
CONFIGS: list[dict] = []


def cfg(id_, codec, ext, opts=None, gop=1, lossless=True, gpu=False):
    CONFIGS.append(dict(id=id_, codec=codec, ext=ext, opts=opts or {}, gop=gop, lossless=lossless, gpu=gpu))


for ext in ("mkv", "nut", "avi", "mov"):
    cfg(f"rawvideo.{ext}", "rawvideo", ext)
cfg("ffv1_l1_g1.mkv", "ffv1", "mkv", {"level": "1"})
cfg("ffv1_l1_gdefault.mkv", "ffv1", "mkv", {"level": "1"}, gop=None)
for ext in ("mkv", "nut", "avi"):
    cfg(f"ffv1_l3_s4_crc_g1.{ext}", "ffv1", ext, {"level": "3", "slices": "4", "slicecrc": "1"})
cfg("ffv1_l3_s4_crc_range_g1.mkv", "ffv1", "mkv", {"level": "3", "slices": "4", "slicecrc": "1", "coder": "range_tab"})
cfg("ffv1_l3_s16_crc_range_g1.mkv", "ffv1", "mkv", {"level": "3", "slices": "16", "slicecrc": "1", "coder": "range_tab"})
cfg("ffv1_l4_experimental_s4_crc_g1.mkv", "ffv1", "mkv", {"level": "4", "slices": "4", "slicecrc": "1", "strict": "experimental"})
cfg("ffvhuff_median.nut", "ffvhuff", "nut", {"pred": "median"})
cfg("huffyuv.avi", "huffyuv", "avi")
cfg("utvideo_median.avi", "utvideo", "avi", {"pred": "median"})
cfg("magicyuv_median.avi", "magicyuv", "avi", {"pred": "median"})
cfg("jpegls.nut", "jpegls", "nut")
cfg("jpeg2000_dwt53.mkv", "jpeg2000", "mkv", {"pred": "dwt53"})
cfg("png.nut", "png", "nut")
cfg("mjpeg_q2.mkv", "mjpeg", "mkv", {"qmin": "2", "qmax": "2", "strict": "unofficial"}, lossless=False)
cfg("libsvtav1_intra_crf30_p10.mkv", "libsvtav1", "mkv", {"preset": "10", "crf": "30", "svtav1-params": "keyint=1"}, lossless=False)
cfg("libsvtav1_intra_lossless.mkv", "libsvtav1", "mkv", {"preset": "10", "svtav1-params": "keyint=1:lossless=1"})
cfg("libvpx-vp9_intra_lossless.webm", "libvpx-vp9", "webm", {"lossless": "1", "deadline": "realtime", "cpu-used": "8", "row-mt": "1"})
cfg("libvpx-vp9_intra_crf30.webm", "libvpx-vp9", "webm", {"crf": "30", "b": "0", "deadline": "realtime", "cpu-used": "8", "row-mt": "1"}, lossless=False)
cfg("prores_ks_hq.mov", "prores_ks", "mov", {"profile": "3"}, lossless=False)
cfg("dnxhd_dnxhr_hq.mov", "dnxhd", "mov", {"profile": "dnxhr_hq"}, lossless=False)
cfg("libx264_intra_qp0.mkv", "libx264", "mkv", {"qp": "0", "preset": "ultrafast"})
cfg("libx264_intra_crf18.mp4", "libx264", "mp4", {"crf": "18", "preset": "ultrafast"}, lossless=False)
cfg("libx265_intra_lossless.mkv", "libx265", "mkv", {"preset": "ultrafast", "x265-params": "lossless=1:keyint=1:log-level=error"})
cfg("h264_nvenc_intra_lossless.mkv", "h264_nvenc", "mkv", {"preset": "p1", "tune": "lossless"}, gpu=True)
cfg("hevc_nvenc_intra_lossless.mkv", "hevc_nvenc", "mkv", {"preset": "p1", "tune": "lossless"}, gpu=True)
cfg("hevc_nvenc_intra_cq.mp4", "hevc_nvenc", "mp4", {"preset": "p1", "rc": "constqp", "qp": "24"}, lossless=False, gpu=True)
cfg("av1_nvenc_intra.mp4", "av1_nvenc", "mp4", {"preset": "p1"}, lossless=False, gpu=True)
cfg("hevc_qsv_intra.mp4", "hevc_qsv", "mp4", {}, lossless=False, gpu=True)
cfg("av1_qsv_intra.mp4", "av1_qsv", "mp4", {}, lossless=False, gpu=True)
cfg("av1_amf_intra.mp4", "av1_amf", "mp4", {}, lossless=False, gpu=True)
cfg("av1_mf_intra.mp4", "av1_mf", "mp4", {}, lossless=False, gpu=True)

HW_FMTS = {"cuda", "d3d11", "qsv", "vaapi", "d3d12", "dxva2_vld", "videotoolbox", "vulkan"}


# ---- exact (reversible) re-layouts. Each: name -> (target pix_fmt, forward(planes,w,h)->planes, inverse) ----
def _neutral(rows, cols, val, bytes_per=1):
    if bytes_per == 1:
        return np.full((rows, cols), val, np.uint8)
    return uf.to_u8_rows(np.full((rows, cols), val, np.uint16))


def _f_yuyv_422p(p, w, h):
    return list(uf.yuyv_split(p[0]))


def _i_yuyv_422p(p, w, h):
    return [uf.planar422_to_yuyv(*p)]


def _f_uyvy_422p(p, w, h):
    a = p[0]
    return [a[:, 1::2].copy(), a[:, 0::4].copy(), a[:, 2::4].copy()]


def _i_uyvy_422p(p, w, h):
    y, u, v = p
    o = np.empty((h, w * 2), np.uint8)
    o[:, 1::2], o[:, 0::4], o[:, 2::4] = y, u, v
    return [o]


def _f_yuyv_nv16(p, w, h):
    y, u, v = uf.yuyv_split(p[0])
    uv = np.empty((h, w), np.uint8)
    uv[:, 0::2], uv[:, 1::2] = u, v
    return [y, uv]


def _i_yuyv_nv16(p, w, h):
    return [uf.planar422_to_yuyv(p[0], p[1][:, 0::2], p[1][:, 1::2])]


def _f_nv12_420p(p, w, h):
    return [p[0], p[1][:, 0::2].copy(), p[1][:, 1::2].copy()]


def _i_nv12_420p(p, w, h):
    uv = np.empty((h // 2, w), np.uint8)
    uv[:, 0::2], uv[:, 1::2] = p[1], p[2]
    return [p[0], uv]


def _f_420p_nv12(p, w, h):
    return _i_nv12_420p(p, w, h)


def _i_420p_nv12(p, w, h):
    return _f_nv12_420p(p, w, h)


def _f_gray_to_yuv(sub, val, bpp):
    def f(p, w, h):
        cr, cc = (h // 2, w // 2) if sub == "420" else (h, w // 2) if sub == "422" else (h, w)
        return [p[0], _neutral(cr, cc, val, bpp), _neutral(cr, cc, val, bpp)]
    return f


def _i_take_y(p, w, h):
    return [p[0]]


def _f_p010_420p10(p, w, h):
    y = p[0].view("<u2") >> 6
    uv = p[1].view("<u2") >> 6
    return [uf.to_u8_rows(y), uf.to_u8_rows(uv[:, 0::2].copy()), uf.to_u8_rows(uv[:, 1::2].copy())]


def _i_p010_420p10(p, w, h):
    y = p[0].view("<u2") << 6
    u, v = p[1].view("<u2"), p[2].view("<u2")
    uv = np.empty((h // 2, w), np.uint16)
    uv[:, 0::2], uv[:, 1::2] = u << 6, v << 6
    return [uf.to_u8_rows(y), uf.to_u8_rows(uv)]


def _f_rgb_gbrp(order):
    def f(p, w, h):
        a = p[0].reshape(h, w, 3)
        r, g, b = (a[:, :, 0], a[:, :, 1], a[:, :, 2]) if order == "rgb" else (a[:, :, 2], a[:, :, 1], a[:, :, 0])
        return [g.copy(), b.copy(), r.copy()]
    return f


def _i_rgb_gbrp(order):
    def f(p, w, h):
        g, b, r = p
        a = np.stack([r, g, b] if order == "rgb" else [b, g, r], axis=-1)
        return [a.reshape(h, w * 3)]
    return f


def _f_rgb_bgr0(order):
    def f(p, w, h):
        a = p[0].reshape(h, w, 3)
        if order == "rgb":
            a = a[:, :, ::-1]
        o = np.zeros((h, w, 4), np.uint8)
        o[:, :, :3] = a
        return [o.reshape(h, w * 4)]
    return f


def _i_rgb_bgr0(order):
    def f(p, w, h):
        a = p[0].reshape(h, w, 4)[:, :, :3]
        if order == "rgb":
            a = a[:, :, ::-1]
        return [np.ascontiguousarray(a).reshape(h, w * 3)]
    return f


def _f_swap3(p, w, h):
    return [np.ascontiguousarray(p[0].reshape(h, w, 3)[:, :, ::-1]).reshape(h, w * 3)]


def _ident(p, w, h):
    return [a.copy() for a in p]


# source pix_fmt -> ordered candidate exact paths: (target, method label, fwd, inv)
EXACT = {
    "yuyv422": [("yuv422p", "numpy deinterleave", _f_yuyv_422p, _i_yuyv_422p),
                ("nv16", "numpy deinterleave", _f_yuyv_nv16, _i_yuyv_nv16)],
    "uyvy422": [("yuv422p", "numpy deinterleave", _f_uyvy_422p, _i_uyvy_422p)],
    "nv12": [("yuv420p", "numpy deinterleave", _f_nv12_420p, _i_nv12_420p)],
    "yuv420p": [("nv12", "numpy interleave", _f_420p_nv12, _i_420p_nv12)],
    "gray": [("yuv420p", "Y + neutral chroma", _f_gray_to_yuv("420", 128, 1), _i_take_y),
             ("yuv444p", "Y + neutral chroma", _f_gray_to_yuv("444", 128, 1), _i_take_y)],
    "gray16le": [("gray12le", "re-tag (values <4096)", _ident, _ident),
                 ("yuv420p12le", "Y + neutral chroma", _f_gray_to_yuv("420", 2048, 2), _i_take_y),
                 ("yuv444p16le", "Y + neutral chroma", _f_gray_to_yuv("444", 2048, 2), _i_take_y)],
    "p010le": [("yuv420p10le", "numpy shift+deinterleave", _f_p010_420p10, _i_p010_420p10)],
    "rgb24": [("gbrp", "numpy planarize", _f_rgb_gbrp("rgb"), _i_rgb_gbrp("rgb")),
              ("bgr24", "numpy swap", _f_swap3, _f_swap3),
              ("bgr0", "numpy pad", _f_rgb_bgr0("rgb"), _i_rgb_bgr0("rgb"))],
    "bgr24": [("gbrp", "numpy planarize", _f_rgb_gbrp("bgr"), _i_rgb_gbrp("bgr")),
              ("rgb24", "numpy swap", _f_swap3, _f_swap3),
              ("bgr0", "numpy pad", _f_rgb_bgr0("bgr"), _i_rgb_bgr0("bgr"))],
    "bayer_rggb8": [("gray", "re-tag as gray", _ident, _ident),
                    ("yuv420p", "mosaic as Y + neutral chroma", _f_gray_to_yuv("420", 128, 1), _i_take_y),
                    ("yuv444p", "mosaic as Y + neutral chroma", _f_gray_to_yuv("444", 128, 1), _i_take_y)],
    "bayer_rggb16le": [("gray16le", "re-tag as gray16le", _ident, _ident),
                       ("gray12le", "re-tag as gray12le", _ident, _ident),
                       ("yuv420p12le", "mosaic as Y + neutral chroma", _f_gray_to_yuv("420", 2048, 2), _i_take_y),
                       ("yuv444p16le", "mosaic as Y + neutral chroma", _f_gray_to_yuv("444", 2048, 2), _i_take_y)],
}
# gray (8-bit) data that is really packed RAW10/12 bytes behaves like gray
EXACT_ALIASES = {"raw12_packed": "gray", "raw10_packed": "gray", "bayer16_quad": "gray16le", "bayer8_quad": "gray"}


def tight_hash(planes) -> str:
    h = hashlib.sha256()
    for a in planes:
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def psnr(a: np.ndarray, b: np.ndarray) -> float | None:
    if a.shape != b.shape:
        return None
    d = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return float("inf") if d == 0 else float(10 * np.log10(255.0**2 / d))


def choose_path(src_key: str, src_fmt: str, enc_fmts: list[str], lossless: bool, codec: str, opts: dict | None = None):
    if codec == "ffv1" and src_fmt.startswith("bayer") and (opts or {}).get("level") != "4":
        enc_fmts = [f for f in enc_fmts if not f.startswith("bayer")]  # native Bayer needs FFV1 v4 (experimental)
    if codec == "rawvideo" or src_fmt in enc_fmts:
        return dict(target=src_fmt, method="native", fwd=_ident, inv=_ident)
    key = src_fmt if src_key not in EXACT_ALIASES else EXACT_ALIASES[src_key]
    for tgt, label, f, i in EXACT.get(key, []):
        if tgt in enc_fmts:
            return dict(target=tgt, method=label, fwd=f, inv=i)
    if lossless or src_fmt.startswith("bayer") or src_key in EXACT_ALIASES:
        return None
    sw = [f for f in enc_fmts if f not in HW_FMTS]
    if not sw:
        return None
    pref = [f for f in ("yuv422p", "nv16", "yuv420p", "nv12", "yuv422p10le", "yuv420p10le", "p010le") if f in sw]
    return dict(target=(pref or sw)[0], method="swscale (lossy)", fwd=None, inv=None)


def rm(p: Path) -> None:
    """Delete, tolerating a handle PyAV left open after a failed write_header (Windows)."""
    import gc

    for _ in range(2):
        try:
            p.unlink(missing_ok=True)
            return
        except PermissionError:
            gc.collect()
    print(f"  (could not delete {p}; left in media dir)")


def nvsmi() -> str:
    try:
        return subprocess.run(
            ["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"nvidia-smi failed: {e}"


def decode_file(path: Path, target: str, w: int, h: int, expect: int):
    """Return (list of decoded tight planes, keyframe flags, decoded pix_fmt, error string)."""
    planes, keys, dec_fmt, err = [], [], None, None
    try:
        with av.open(str(path)) as c:
            s = c.streams.video[0]
            for pkt in c.demux(s):
                if pkt.size:
                    keys.append(bool(pkt.is_keyframe))
                for fr in pkt.decode():
                    dec_fmt = fr.format.name
                    norm = dec_fmt.replace("yuvj", "yuv")
                    if norm == target:
                        planes.append(uf.read_planes(fr, target))
                    elif target.startswith("gray") and norm.startswith("yuv") and norm in uf.PLANES:
                        planes.append(uf.read_planes(fr, norm)[:1])  # monochrome decoded as yuv: compare luma
                    else:
                        planes.append(uf.read_planes(fr.reformat(format=target), target))
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    return planes, keys, dec_fmt, err


def run_one(c: dict, src_key: str, srcs, w0: int, h0: int, keep: bool) -> dict:
    r = dict(config=c["id"], codec=c["codec"], container=c["ext"], source=src_key, lossless_intended=c["lossless"])
    try:
        enc = av.Codec(c["codec"], "w")
    except Exception as e:  # noqa: BLE001
        r.update(stage="codec_lookup", error=f"{type(e).__name__}: {e}")
        return r
    enc_fmts = [f.name for f in (enc.video_formats or [])]
    planes0, src_fmt, w, h = srcs[0]
    path = choose_path(src_key, src_fmt, enc_fmts, c["lossless"], c["codec"], c["opts"])
    if path is None:
        r.update(stage="no_path", error=f"no {'exact ' if c['lossless'] else ''}path from {src_fmt} to {enc_fmts}")
        return r
    r.update(target_pix_fmt=path["target"], path=path["method"], src_pix_fmt=src_fmt)
    fed = []
    for planes, fmt, _, _ in srcs:
        if path["fwd"] is not None:
            fed.append(path["fwd"](planes, w, h))
        else:
            fr = uf.make_frame(planes, fmt, w, h).reformat(format=path["target"])
            fed.append(uf.read_planes(fr, path["target"]))
    MEDIA.mkdir(parents=True, exist_ok=True)
    out = MEDIA / f"{src_key}__{c['id']}"
    if out.exists():
        rm(out)
    if c["gpu"]:
        r["nvidia_smi_before"] = nvsmi()
    stage = "open_container"
    logs = None
    try:
        with av.logging.Capture() as logs, av.open(str(out), "w") as oc:
            stage = "add_stream"
            st = oc.add_stream(c["codec"], rate=30, options=dict(c["opts"]))
            st.width, st.height, st.pix_fmt = w, h, path["target"]
            if c["gop"] is not None:
                st.codec_context.gop_size = c["gop"]
            stage = "encode"
            for i, pl in enumerate(fed):
                fr = uf.make_frame(pl, path["target"], w, h)
                fr.pts = i
                fr.time_base = Fraction(1, 30)
                for pkt in st.encode(fr):
                    oc.mux(pkt)
            for pkt in st.encode(None):
                oc.mux(pkt)
            stage = "close"
    except Exception as e:  # noqa: BLE001
        r.update(stage=stage, error=f"{type(e).__name__}: {e}")
        r["libav_log"] = [f"{x[1]}: {x[2].strip()}" for x in (logs or []) if x[0] <= av.logging.WARNING][-6:]
        if c["gpu"]:
            r["nvidia_smi_after"] = nvsmi()
        if out.exists() and not keep:
            rm(out)
        return r
    if c["gpu"]:
        r["nvidia_smi_after"] = nvsmi()
    size = out.stat().st_size
    dec, keys, dec_fmt, derr = decode_file(out, path["target"], w, h, len(fed))
    r.update(stage="done", file_bytes=size, frames_fed=len(fed), frames_decoded=len(dec), decoded_pix_fmt=dec_fmt,
             all_keyframes=bool(keys) and all(keys), keyframe_flags=keys, decode_error=derr)
    try:
        with av.open(str(out)) as cc:
            r["codec_tag"] = cc.streams.video[0].codec_context.codec_tag
            r["packet_bytes_mean"] = float(np.mean([p.size for p in cc.demux(cc.streams.video[0]) if p.size]))
    except Exception as e:  # noqa: BLE001
        r["packet_bytes_mean"] = None
        r["probe_error"] = str(e)
    if dec and len(dec) == len(fed):
        r["bit_exact_vs_fed"] = all(tight_hash(a) == tight_hash(b) for a, b in zip(dec, fed))
        if path["inv"] is not None:
            r["bit_exact_vs_source"] = all(
                tight_hash(path["inv"](d, w, h)) == tight_hash(s[0]) for d, s in zip(dec, srcs))
        r["psnr_plane0_min"] = min(psnr(d[0], f[0]) for d, f in zip(dec, fed)) if not r["bit_exact_vs_fed"] else "inf"
        if "16" in path["target"] or "10" in path["target"] or "12" in path["target"]:
            r["psnr_note"] = "plane0 PSNR computed on raw bytes (not meaningful for >8-bit)"
    # truncation: cut at 50 %
    tr = out.with_name(out.name + ".trunc50" + out.suffix)
    with open(out, "rb") as fsrc, open(tr, "wb") as fdst:
        fdst.write(fsrc.read(size // 2))
    tdec, _, _, terr = decode_file(tr, path["target"], w, h, len(fed))
    r["trunc50_frames_decoded"] = len(tdec)
    r["trunc50_error"] = terr
    r["trunc50_frames_exact"] = sum(tight_hash(a) == tight_hash(b) for a, b in zip(tdec, fed))
    rm(tr)
    if not keep:
        rm(out)
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=4)
    ap.add_argument("--only", default="")
    ap.add_argument("--sources", default=",".join(uf.SOURCES))
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--yuy2-set", default="c930e_1080p_yuy2")
    ap.add_argument("--tag", default="")
    ap.add_argument("--no-noise", action="store_true", help="zero the synthetic low bits of >8-bit derived sources")
    a = ap.parse_args()
    av.logging.set_level(av.logging.WARNING)
    yuy, w, h = uf.load_yuy2(a.yuy2_set, a.frames)
    results = []
    for src_key in a.sources.split(","):
        srcs = [uf.derive(src_key, f, w, h, idx=i, noise=not a.no_noise) for i, f in enumerate(yuy)]
        for c in CONFIGS:
            if a.only and a.only not in c["id"]:
                continue
            r = run_one(c, src_key, srcs, w, h, a.keep)
            results.append(r)
            flag = r.get("bit_exact_vs_fed")
            print(f"{src_key:15s} {c['id']:34s} {r.get('stage'):12s} {r.get('path','')[:22]:22s} "
                  f"exact={flag} keys={r.get('all_keyframes')} B/f={r.get('packet_bytes_mean')} "
                  f"trunc={r.get('trunc50_frames_decoded')} {(r.get('error') or r.get('decode_error') or '')[:80]}",
                  flush=True)
    out = RESULTS / f"functional_matrix_pyav{av.__version__}{a.tag}.json"
    meta = dict(av_version=av.__version__, library_versions={k: list(v) for k, v in av.library_versions.items()},
                numpy=np.__version__, yuy2_set=a.yuy2_set, frames=a.frames, width=w, height=h, noise=not a.no_noise,
                note="no timing measured")
    RESULTS.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(meta=meta, results=results), indent=1, default=str))
    print("wrote", out)


if __name__ == "__main__":
    main()
