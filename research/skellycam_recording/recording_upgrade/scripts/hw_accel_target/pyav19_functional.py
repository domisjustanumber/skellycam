# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""FUNCTIONAL (no timing) hardware encode/decode matrix through PyAV 19.0.2 on Gerald, with the Intel UHD 770 present.

Adapted from scripts/gpu_encode/pyav_functional.py. Run from the repo root:
  uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/pyav19_functional.py
Options: --only h264_qsv,hevc_qsv  (subset of encoders)   --skip-decode   --frames 60
Writes results/hw_accel_target/functional_pyav19.json/.md; media under skellycam-raw/.../hw_accel_target/functional/.

Per encoder (see ENC):
  (c) format probe: open + encode 4 frames for each of yuyv422 / yuv422p / nv16 / nv12 / yuv420p (made from the real
      YUY2 1080p frames by PyAV reformat); records open/encode errors and the pix_fmt/profile ffprobe sees.
  (a) intra and (b) gop30 (max_b_frames=0) from 3 inputs, 60 frames, MKV:
      nv12 from yuy2_1080p, nv12 from decoded mjpeg_720p, nv12 from decoded mjpeg_1080p (CPU encoders use their
      own 4:2:0 / 4:2:2 planar format). Hardware encoders are tried with software frames ("sw") and, where a
      device type applies, with add_stream(..., hwaccel=HWAccel(type)) ("hwctx": PyAV builds the frames context
      and uploads). ffprobe -show_frames key_frame/pict_type checks every frame.
  native 4:2:2: intra MKV from yuyv422 or yuv422p if the format probe produced a 4:2:2 stream.
  (d) decode-back with PyAV's default software decoder: frame count, PSNR (Y and all planes, both sides
      converted to yuv444p by swscale) vs the frames that were fed.
  (e) containers: intra from yuy2_1080p into MKV, MP4 and (vp9/av1 only) WebM; ffprobe each.
  NVENC sessions: nvidia-smi encoder.stats.sessionCount is read while each hardware encoder is open (after 5 frames).
  Adapter: FFmpeg log lines (av.logging VERBOSE) are kept per test (MFT name, QSV implementation, errors).
Decode tests (each in a child process with a 60 s timeout; the mjpeg_cuvid CLI hung earlier):
  camera 4:2:2 JPEG and a 4:2:0 JPEG control through mjpeg (CPU), mjpeg_qsv (sw out / qsv hw out), mjpeg_cuvid,
  mjpeg + HWAccel(cuda/qsv/d3d11va/d3d12va/dxva2, no fallback); encoded h264/hevc/vp9/av1 files from the encode stage
  through <codec>_qsv, <codec>_cuvid and native + HWAccel(d3d11va/d3d12va/cuda/qsv, no fallback).
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
import traceback
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import (MEDIA, RESULTS, jpeg_bytes, jpeg_set_bytes, nvenc_sessions, nvidia_smi,  # noqa: E402
                    probe_frames, yuy2_bytes)

from av.codec.hwaccel import HWAccel, hwdevices_available  # noqa: E402
from av.video.frame import PictureType  # noqa: E402

OUT = MEDIA / "functional"
NFR = 60

# ---------------------------------------------------------------- FFmpeg log capture
LOG: list[str] = []


class _H(logging.Handler):
    def emit(self, rec):
        msg = rec.getMessage().strip()
        if msg:
            LOG.append(f"{rec.levelname[0]} {rec.name.replace('libav.', '')}: {msg}"[:300])


def log_setup():
    av.logging.set_level(av.logging.VERBOSE)
    lg = logging.getLogger("libav")
    lg.setLevel(logging.DEBUG)
    lg.addHandler(_H())
    lg.propagate = False


KEEP = ("mft", "adapter", "device", "impl", "intel", "nvidia", "error", "fail", "not supported", "unsupported",
        "invalid", "profile", "vendor", "session", "mfx", "vpl", "warning", "using", "selected", "driver", "d3d",
        "low_power", "lowpower", "format")


def take_log(limit: int = 40) -> list[str]:
    out = [ln for ln in LOG if ln[0] in "EWF" or any(k in ln.lower() for k in KEEP)]
    LOG.clear()
    seen, res = set(), []
    for ln in out:
        if ln not in seen:
            seen.add(ln)
            res.append(ln)
    return res[:limit]


# ---------------------------------------------------------------- inputs
def frame_from_bytes(buf: bytes, fmt: str, w: int, h: int) -> av.VideoFrame:
    f = av.VideoFrame(w, h, fmt)
    p = f.planes[0]
    row = w * 2
    if p.line_size == row:
        p.update(buf)
    else:
        a = np.frombuffer(buf, np.uint8).reshape(h, row)
        dst = np.frombuffer(p, np.uint8).reshape(h, p.line_size)
        dst[:, :row] = a
    return f


def load_inputs() -> dict[str, list[av.VideoFrame]]:
    """Source frames in their camera format: yuyv422 (YUY2 sets) and yuvj422p (CPU mjpeg decode of corpus JPEGs)."""
    src: dict[str, list[av.VideoFrame]] = {}
    for name in ("yuy2_1080p",):
        src[name] = [frame_from_bytes(b, "yuyv422", 1920, 1080) for b in yuy2_bytes(name)]
    for name in ("mjpeg_720p", "mjpeg_1080p"):
        cc = av.CodecContext.create("mjpeg", "r")
        fr = []
        for b in jpeg_bytes(name):
            fr += list(cc.decode(av.Packet(b)))
        fr += list(cc.decode(None))
        src[name] = fr
    return src


def conv(frames: list[av.VideoFrame], fmt: str) -> list[av.VideoFrame]:
    return [f if f.format.name == fmt else f.reformat(format=fmt) for f in frames]


def frame_range(f: av.VideoFrame) -> int:
    """1 = MPEG/limited, 2 = JPEG/full: the frame's tag, else implied by a yuvj* format, else limited."""
    r = int(f.color_range or 0)
    return r if r in (1, 2) else (2 if f.format.name.startswith("yuvj") else 1)


def planes444(f: av.VideoFrame) -> np.ndarray:
    """Chroma-upsample to yuv444p WITHOUT any range conversion (src and dst range set to the frame's own range),
    so PSNR compares raw sample values. (v1 of this script let swscale convert range; PyAV 19 reformat converts
    only when the source is untagged yuvj, which made PSNR of some MJPEG rows wrong; see NOTES_functional.md.)"""
    r = frame_range(f)
    g = f.reformat(format="yuv444p", src_color_range=r, dst_color_range=r)
    out = []
    for p in g.planes:
        out.append(np.frombuffer(p, np.uint8).reshape(p.height, p.line_size)[:, :p.width])
    return np.stack(out)


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return 99.0 if mse == 0 else round(10 * np.log10(255.0 ** 2 / mse), 2)


# ---------------------------------------------------------------- encoder table
# name: dict(hw=device type for hwctx mode or None, opts=codec options, intra_gop, cpu=bool, webm=bool)
ENC: dict[str, dict] = {
    "h264_qsv": dict(hw="qsv", opts={}, intra_gop=1),
    "hevc_qsv": dict(hw="qsv", opts={}, intra_gop=1),
    "av1_qsv": dict(hw="qsv", opts={}, intra_gop=1, webm=True),
    "vp9_qsv": dict(hw="qsv", opts={}, intra_gop=1, webm=True),
    "mjpeg_qsv": dict(hw="qsv", opts={}, intra_gop=1),
    "h264_nvenc": dict(hw="cuda", opts={"preset": "p4"}, intra_gop=0),
    "hevc_nvenc": dict(hw="cuda", opts={"preset": "p4"}, intra_gop=0),
    "av1_nvenc": dict(hw="cuda", opts={"preset": "p4"}, intra_gop=0, webm=True),
    "h264_d3d12va": dict(hw="d3d12va", opts={}, intra_gop=1, hw_only=True, ext="mp4"),
    "hevc_d3d12va": dict(hw="d3d12va", opts={}, intra_gop=1, hw_only=True, ext="mp4"),
    "av1_d3d12va": dict(hw="d3d12va", opts={}, intra_gop=1, hw_only=True, webm=True, ext="mp4"),
    "h264_mf": dict(hw=None, opts={"hw_encoding": "1"}, intra_gop=1),
    "hevc_mf": dict(hw=None, opts={"hw_encoding": "1"}, intra_gop=1),
    "av1_mf": dict(hw=None, opts={"hw_encoding": "1"}, intra_gop=1, webm=True),
    "h264_amf": dict(hw="amf", opts={}, intra_gop=1),
    "hevc_amf": dict(hw="amf", opts={}, intra_gop=1),
    "av1_amf": dict(hw="amf", opts={}, intra_gop=1, webm=True),
    # CPU software baselines (royalty-free / intra references)
    "libsvtav1": dict(hw=None, opts={"preset": "10"}, intra_gop=1, cpu=True, webm=True, fmt420="yuv420p"),
    "libvpx-vp9": dict(hw=None, opts={"deadline": "realtime", "cpu-used": "8"}, intra_gop=1, cpu=True, webm=True,
                       fmt420="yuv420p", fmt422="yuv422p"),
    "mjpeg": dict(hw=None, opts={}, intra_gop=1, cpu=True, fmt420="yuvj420p", fmt422="yuvj422p"),
    "ffv1": dict(hw=None, opts={"level": "3", "slices": "16"}, intra_gop=1, cpu=True, fmt420="yuv420p",
                 fmt422="yuv422p"),
}
PROBE_FMTS = ["yuyv422", "yuv422p", "nv16", "nv12", "yuv420p"]
CHROMA = {"yuyv422": "4:2:2", "yuv422p": "4:2:2", "yuvj422p": "4:2:2", "nv16": "4:2:2", "nv12": "4:2:0",
          "yuv420p": "4:2:0", "yuvj420p": "4:2:0"}


def encode(name: str, frames_src: list[av.VideoFrame], fmt: str, variant: str, mode: str, ext: str, tag: str,
           n: int, mid_probe: bool = True, decode_back: bool = True, reset_pict: bool = False) -> dict:
    cfg = ENC[name]
    dst = OUT / f"{name}__{tag}.{ext}"
    rec: dict = {"encoder": name, "tag": tag, "pix_fmt_in": fmt, "variant": variant, "mode": mode, "container": ext,
                 "frames_requested": n, "pict_type_reset": reset_pict,
                 "input_pict_type": str(frames_src[0].pict_type) if frames_src else None}
    if name not in av.codecs_available:
        rec.update(ok=False, error="not in av.codecs_available")
        return rec
    frames = conv(frames_src, fmt)
    w, h = frames[0].width, frames[0].height
    y0 = np.frombuffer(frames[0].planes[0], np.uint8).reshape(h, frames[0].planes[0].line_size)[:, :frames[0].planes[0].width]
    rec["fed_frame0"] = {"format": frames[0].format.name, "color_range_tag": int(frames[0].color_range or 0),
                         "plane0_min": int(y0.min()), "plane0_max": int(y0.max())}
    LOG.clear()
    fed: list[av.VideoFrame] = []
    try:
        if dst.exists():
            dst.unlink()
        with av.open(str(dst), "w") as c:
            kw = {"hwaccel": HWAccel(cfg["hw"])} if mode == "hwctx" else {}
            s = c.add_stream(name, rate=30, options=dict(cfg["opts"]), **kw)
            s.width, s.height, s.pix_fmt = w, h, fmt
            s.codec_context.gop_size = cfg["intra_gop"] if variant == "intra" else 30
            s.codec_context.max_b_frames = 0
            npk = 0
            for i in range(n):
                vf = frames[i % len(frames)]
                vf = vf.reformat(format=fmt)  # fresh copy so pts can be set
                vf.pts = i
                if reset_pict:  # decoded MJPEG frames carry pict_type=I; reformat() copies it; encoders obey it
                    vf.pict_type = PictureType.NONE
                for p in s.encode(vf):
                    c.mux(p)
                    npk += 1
                fed.append(frames[i % len(frames)])  # the converted frame actually fed (PSNR reference)
                if mid_probe and i == 5 and not cfg.get("cpu"):
                    rec["nvenc_sessions_while_open"] = nvenc_sessions()
            for p in s.encode(None):
                c.mux(p)
                npk += 1
            rec["packets_muxed"] = npk
            rec["codec_ctx_pix_fmt"] = s.codec_context.pix_fmt
        rec["ok"] = dst.exists() and dst.stat().st_size > 0 and npk > 0
        rec["bytes"] = dst.stat().st_size if dst.exists() else 0
    except Exception as e:  # noqa: BLE001
        rec["ok"] = False
        rec["error"] = f"{type(e).__name__}: {e}"[:400]
        rec["frames_fed_before_error"] = len(fed)
    rec["log"] = take_log()
    if rec.get("ok"):
        rec["probe"] = probe_frames(dst)
        if decode_back:
            rec["decode_back"] = decode_back_check(dst, fed)
    elif dst.exists() and dst.stat().st_size == 0:
        dst.unlink()
    return rec


def decode_back_check(path: Path, fed: list[av.VideoFrame]) -> dict:
    d: dict = {}
    try:
        with av.open(str(path)) as c:
            st = c.streams.video[0]
            d["decoder"] = st.codec_context.name
            ps_y, ps_all, fmts, k = [], [], set(), 0
            for f in c.decode(st):
                fmts.add(f.format.name)
                if k < len(fed):
                    a, b = planes444(f), planes444(fed[k])
                    ps_y.append(psnr(a[0], b[0]))
                    ps_all.append(psnr(a, b))
                k += 1
        d.update(frames=k, frames_fed=len(fed), out_formats=sorted(fmts))
        if ps_y:
            d.update(psnr_y_min=min(ps_y), psnr_y_mean=round(float(np.mean(ps_y)), 2),
                     psnr_all_min=min(ps_all), psnr_all_mean=round(float(np.mean(ps_all)), 2))
    except Exception as e:  # noqa: BLE001
        d["error"] = f"{type(e).__name__}: {e}"[:300]
    return d


def main_fmt(name: str, src_kind: str) -> str:
    cfg = ENC[name]
    if cfg.get("cpu"):
        return cfg["fmt420"]
    return "nv12"


def run_encoder(name: str, src: dict[str, list[av.VideoFrame]], n: int) -> list[dict]:
    cfg = ENC[name]
    recs: list[dict] = []
    modes = ["hwctx"] if cfg.get("hw_only") else (["sw"] + (["hwctx"] if cfg["hw"] else []))
    # (c) format probe, 4 frames, sw mode (hwctx for hw_only). d3d12va: MP4 (its MKV header write fails, see below)
    mext = cfg.get("ext", "mkv")
    fmt_ok422 = None
    for fmt in PROBE_FMTS + ([cfg["fmt422"]] if cfg.get("fmt422") and cfg["fmt422"] not in PROBE_FMTS else []):
        r = encode(name, src["yuy2_1080p"], fmt, "intra", modes[0], mext, f"fmtprobe_{fmt}", 4, mid_probe=False,
                   decode_back=False)
        r["stage"] = "format_probe"
        r["chroma_in"] = CHROMA.get(fmt)
        recs.append(r)
        pf = (r.get("probe") or {}).get("pix_fmt") or ""
        if r.get("ok") and "422" in pf and fmt_ok422 is None:
            fmt_ok422 = fmt
        print(f"  fmtprobe {fmt:8s} {'OK ' + pf if r.get('ok') else 'FAIL ' + r.get('error', '')[:90]}")
    if not any(r.get("ok") for r in recs):
        # nothing opens: keep one main-matrix attempt per mode for the error text, then stop
        for mode in modes:
            r = encode(name, src["yuy2_1080p"], main_fmt(name, "yuy2"), "intra", mode, mext,
                       f"yuy2_1080p_intra_{mode}", 4)
            r["stage"] = "main"
            recs.append(r)
            print(f"  main {mode} FAIL {r.get('error', '')[:120]}")
        return recs
    # (a)(b) main matrix
    for inp in ("yuy2_1080p", "mjpeg_720p", "mjpeg_1080p"):
        for variant in ("intra", "gop30"):
            for mode in modes:
                if mode == "hwctx" and inp != "yuy2_1080p" and not cfg.get("hw_only"):
                    continue
                r = encode(name, src[inp], main_fmt(name, inp), variant, mode, mext, f"{inp}_{variant}_{mode}", n)
                r["stage"] = "main"
                r["input"] = inp
                recs.append(r)
                p = r.get("probe", {})
                db = r.get("decode_back", {})
                print(f"  {inp:11s} {variant:5s} {mode:5s} {'OK' if r.get('ok') else 'FAIL'} "
                      f"{p.get('pict_types', '')} key={p.get('ffprobe_key_frames')} "
                      f"psnrY={db.get('psnr_y_mean')} sess={r.get('nvenc_sessions_while_open')} {r.get('error', '')[:100]}")
    # native 4:2:2
    if fmt_ok422 or cfg.get("fmt422"):
        f422 = cfg.get("fmt422") or fmt_ok422
        for inp in ("yuy2_1080p", "mjpeg_720p"):
            r = encode(name, src[inp], f422, "intra", modes[0], mext, f"{inp}_intra_native422_{f422}", n)
            r["stage"] = "native422"
            r["input"] = inp
            recs.append(r)
            print(f"  native422 {inp} {f422} {'OK' if r.get('ok') else 'FAIL'} {r.get('probe', {}).get('pix_fmt')} "
                  f"psnrY={r.get('decode_back', {}).get('psnr_y_mean')} {r.get('error', '')[:100]}")
    # (e) containers
    exts = (["mkv"] if mext == "mp4" else ["mp4"]) + (["webm"] if cfg.get("webm") else [])
    for ext in exts:
        r = encode(name, src["yuy2_1080p"], main_fmt(name, "yuy2"), "intra", modes[-1] if cfg.get("hw_only") else "sw",
                   ext, f"yuy2_1080p_intra_container", 30)
        r["stage"] = "container"
        recs.append(r)
        print(f"  container {ext} {'OK' if r.get('ok') else 'FAIL'} {r.get('probe', {}).get('format_name')} "
              f"{r.get('error', '')[:100]}")
    return recs


def pictreset_stage(name: str, src, n: int) -> list[dict]:
    """gop30 from decoded MJPEG with frame.pict_type reset to NONE before encode (the main matrix feeds the
    decoder's frames as they come, pict_type=I)."""
    cfg = ENC[name]
    mode = "hwctx" if cfg.get("hw_only") else "sw"
    recs = []
    for inp in ("mjpeg_720p", "mjpeg_1080p"):
        r = encode(name, src[inp], main_fmt(name, inp), "gop30", mode, cfg.get("ext", "mkv"),
                   f"{inp}_gop30_{mode}_pictreset", n, reset_pict=True)
        r["stage"] = "gop_pictreset"
        r["input"] = inp
        recs.append(r)
        print(f"  pictreset {inp} {'OK' if r.get('ok') else 'FAIL'} {r.get('probe', {}).get('pict_types')} "
              f"psnrY={r.get('decode_back', {}).get('psnr_y_mean')} {r.get('error', '')[:100]}")
    return recs


def d3d12_adapter_probe(src) -> list[dict]:
    """Which DXGI adapter does each d3d12va encoder use? Try device indices 0..3 explicitly."""
    out = []
    for name in ("h264_d3d12va", "hevc_d3d12va", "av1_d3d12va"):
        for dev in ("0", "1", "2", "3"):
            cfg = ENC[name]
            dst = OUT / f"{name}__adapter{dev}.mp4"
            rec = {"encoder": name, "device": dev, "stage": "d3d12_adapter"}
            frames = conv(src["yuy2_1080p"], "nv12")
            LOG.clear()
            try:
                with av.open(str(dst), "w") as c:
                    s = c.add_stream(name, rate=30, hwaccel=HWAccel("d3d12va", device=dev))
                    s.width, s.height, s.pix_fmt = 1920, 1080, "nv12"
                    s.codec_context.gop_size = 1
                    s.codec_context.max_b_frames = 0
                    for i in range(8):
                        vf = frames[i].reformat(format="nv12")
                        vf.pts = i
                        for p in s.encode(vf):
                            c.mux(p)
                        if i == 5:
                            rec["nvenc_sessions_while_open"] = nvenc_sessions()
                    for p in s.encode(None):
                        c.mux(p)
                rec["ok"] = True
                rec["probe"] = probe_frames(dst)
            except Exception as e:  # noqa: BLE001
                rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
            rec["log"] = take_log(25)
            out.append(rec)
            print(f"  d3d12 {name} dev{dev} {'OK' if rec['ok'] else 'FAIL'} sess={rec.get('nvenc_sessions_while_open')}"
                  f" {rec.get('error', '')[:100]}")
    return out


# ---------------------------------------------------------------- decode tests (child processes)
def child_decode(spec: dict) -> dict:
    """spec: kind=jpeg|file, decoder name or 'native', hw (device type or None), fallback(bool), hw_out(bool)."""
    log_setup()
    res: dict = dict(spec)
    try:
        if spec["kind"] == "jpeg":
            pkts = [av.Packet(b) for b in json_bytes(spec)]
            kw = {}
            if spec.get("hw"):
                kw["hwaccel"] = HWAccel(spec["hw"], allow_software_fallback=spec.get("fallback", False),
                                        is_hw_owned=spec.get("hw_out", False))
            dec = spec["decoder"] if spec["decoder"] != "native" else "mjpeg"
            cc = av.CodecContext.create(dec, "r", **kw)
            frames = []
            for p in pkts:
                frames += list(cc.decode(p))
            frames += list(cc.decode(None))
        else:
            kw = {}
            if spec.get("hw"):
                kw["hwaccel"] = HWAccel(spec["hw"], allow_software_fallback=spec.get("fallback", False),
                                        is_hw_owned=spec.get("hw_out", False))
            # explicit decoder: open the container WITHOUT hwaccel (else av.open checks the stream's default
            # decoder, e.g. libdav1d, and raises) and attach the hwaccel to our own CodecContext only
            c = av.open(spec["path"], **(kw if spec["decoder"] == "native" else {}))
            st = c.streams.video[0]
            if spec["decoder"] != "native":
                cc = av.CodecContext.create(spec["decoder"], "r", **kw)
                cc.extradata = st.codec_context.extradata
                frames = []
                for pk in c.demux(st):
                    if pk.size == 0:
                        continue
                    frames += list(cc.decode(pk))
                frames += list(cc.decode(None))
            else:
                frames = list(c.decode(st))
                cc = st.codec_context
            c.close()
        res["frames"] = len(frames)
        res["out_formats"] = sorted({f.format.name for f in frames})
        res["codec_ctx"] = cc.name
        if spec.get("hw"):
            # does this decoder declare a hw config for the requested device type? If not, PyAV decodes in
            # software without raising (observed for mjpeg + qsv/d3d11va/d3d12va/dxva2).
            hc = [str(h.device_type).split(".")[-1] for h in (av.Codec(cc.name, "r").hardware_configs or [])]
            res["decoder_hw_configs"] = hc
            res["decoder_has_hw_config_for_device"] = spec["hw"] in hc
        # PSNR vs CPU decode of the same input (first 10 frames)
        ref = cpu_ref(spec)
        ps, psa = [], []
        for f, r in zip(frames[:10], ref[:10]):
            try:
                g = f if f.format.name not in ("cuda", "qsv", "d3d11", "d3d12", "dxva2_vld") else None
                if g is None:
                    break
                a, b = planes444(g), planes444(r)
                ps.append(psnr(a[0], b[0]))
                psa.append(psnr(a, b))
            except Exception as e:  # noqa: BLE001
                res["psnr_error"] = f"{type(e).__name__}: {e}"[:200]
                break
        if ps:
            res.update(psnr_y_vs_cpu_min=min(ps), psnr_all_vs_cpu_min=min(psa))
        res["ok"] = len(frames) > 0
    except Exception as e:  # noqa: BLE001
        res.update(ok=False, error=f"{type(e).__name__}: {e}"[:400])
    res["log"] = take_log(20)
    return res


def json_bytes(spec: dict) -> list[bytes]:
    if spec.get("jpeg420"):
        return [Path(p).read_bytes() for p in spec["jpeg420"]]
    return jpeg_set_bytes(spec["set"], spec["n"])


def cpu_ref(spec: dict) -> list[av.VideoFrame]:
    if spec["kind"] == "jpeg":
        cc = av.CodecContext.create("mjpeg", "r")
        fr = []
        for b in json_bytes(spec):
            fr += list(cc.decode(av.Packet(b)))
        return fr + list(cc.decode(None))
    with av.open(spec["path"]) as c:
        return list(c.decode(c.streams.video[0]))


def run_child(spec: dict, timeout: float = 60) -> dict:
    try:
        r = subprocess.run([sys.executable, __file__, "--child", json.dumps(spec)], capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        line = [ln for ln in r.stdout.splitlines() if ln.startswith("CHILD_RESULT ")]
        if line:
            return json.loads(line[-1][len("CHILD_RESULT "):])
        return dict(spec, ok=False, error=f"child exit {r.returncode}", stderr_tail=r.stderr[-600:])
    except subprocess.TimeoutExpired:
        return dict(spec, ok=False, error=f"TIMEOUT after {timeout}s (child killed)")


def make_jpeg420(src) -> list[str]:
    """4:2:0 JPEG control: PyAV mjpeg encoder (yuvj420p, q~3) on decoded 1080p camera frames."""
    d = OUT / "jpeg420_control"
    d.mkdir(parents=True, exist_ok=True)
    cc = av.CodecContext.create("mjpeg", "w")
    cc.width, cc.height, cc.pix_fmt = 1920, 1080, "yuvj420p"
    cc.time_base = Fraction(1, 30)
    cc.qmin = cc.qmax = 3
    paths = []
    for i, f in enumerate(src["mjpeg_1080p"][:10]):
        g = f.reformat(format="yuvj420p")
        g.pts = i
        for p in cc.encode(g):
            q = d / f"j420_{i:03d}.jpg"
            q.write_bytes(bytes(p))
            paths.append(str(q))
    for p in cc.encode(None):
        q = d / f"j420_{len(paths):03d}.jpg"
        q.write_bytes(bytes(p))
        paths.append(str(q))
    return paths


def decode_matrix(src, enc_recs: list[dict]) -> list[dict]:
    out = []
    j420 = make_jpeg420(src)
    jpeg_inputs = [dict(set="c930e_720p_flash", n=10, label="camera 720p 4:2:2"),
                   dict(set="c930e_1080p", n=10, label="camera 1080p 4:2:2"),
                   dict(set="c922_1080p", n=10, label="camera c922 1080p 4:2:2"),
                   dict(set="", n=len(j420), jpeg420=j420, label="control 1080p 4:2:0 (PyAV mjpeg)")]
    jpeg_decoders = [("native", None, False), ("mjpeg_qsv", None, False), ("mjpeg_qsv", "qsv", True),
                     ("mjpeg_cuvid", None, False), ("native", "cuda", False), ("native", "qsv", False),
                     ("native", "d3d11va", False), ("native", "d3d12va", False), ("native", "dxva2", False)]
    for ji in jpeg_inputs:
        for dec, hw, hw_out in jpeg_decoders:
            spec = dict(kind="jpeg", decoder=dec, hw=hw, hw_out=hw_out, fallback=False, **ji)
            r = run_child(spec)
            r.pop("jpeg420", None)
            out.append(r)
            print(f"  dec {ji['label']:32s} {dec:11s} hw={hw} {'OK' if r.get('ok') else 'FAIL'} "
                  f"{r.get('out_formats', '')} psnrY={r.get('psnr_y_vs_cpu_min')} {r.get('error', '')[:100]}")
    # encoded files from the encode stage: pick one intra + one gop30 per codec family
    picks: dict[str, str] = {}
    for r in enc_recs:
        if r.get("stage") == "main" and r.get("ok") and r.get("input") == "yuy2_1080p" and r.get("mode") == "sw":
            cn = r.get("probe", {}).get("codec_name")
            key = f"{cn}_{r['variant']}"
            if cn in ("h264", "hevc", "vp9", "av1") and key not in picks:
                picks[key] = str(OUT / f"{r['encoder']}__{r['tag']}.{r['container']}")
    for r in enc_recs:  # hevc 4:2:2 if produced
        if r.get("stage") == "native422" and r.get("ok") and r.get("probe", {}).get("codec_name") == "hevc":
            picks.setdefault("hevc422_intra", str(OUT / f"{r['encoder']}__{r['tag']}.{r['container']}"))
    for key, path in sorted(picks.items()):
        cn = key.split("_")[0].replace("hevc422", "hevc")
        decs = [(f"{cn}_qsv", None), (f"{cn}_cuvid", None), ("native", "d3d11va"), ("native", "d3d12va"),
                ("native", "cuda"), ("native", "qsv"), ("native", "dxva2")]
        for dec, hw in decs:
            spec = dict(kind="file", path=path, decoder=dec, hw=hw, fallback=False, label=key)
            r = run_child(spec)
            out.append(r)
            print(f"  dec {key:16s} {dec:12s} hw={hw} {'OK' if r.get('ok') else 'FAIL'} {r.get('out_formats', '')} "
                  f"psnrY={r.get('psnr_y_vs_cpu_min')} {r.get('error', '')[:100]}")
    return out


# ---------------------------------------------------------------- report
def write_md(rep: dict) -> None:
    L = ["# PyAV 19.0.2 functional hardware encode/decode matrix (hw_accel_target, Gerald, UHD 770 present)", "",
         f"Generated by `scripts/hw_accel_target/pyav19_functional.py` at {rep['utc']}. Functional only, no timing.",
         "", f"- libavcodec {rep['libavcodec']}; hwdevices_available {rep['hwdevices_available']}",
         f"- nvidia-smi (sessions, util) before `{rep['nvidia_smi_before']}` after `{rep['nvidia_smi_after']}`",
         f"- media: `{OUT}`", "", "## Format probe (4 frames from real YUY2 1080p, PyAV reformat to pix_fmt_in)", "",
         "| encoder | pix_fmt_in | chroma in | ok | output pix_fmt / profile | error |", "|---|---|---|---|---|---|"]
    for r in rep["encode"]:
        if r.get("stage") != "format_probe":
            continue
        p = r.get("probe", {})
        L.append(f"| {r['encoder']} | {r['pix_fmt_in']} | {r.get('chroma_in')} | {'yes' if r.get('ok') else 'NO'} | "
                 f"{p.get('pix_fmt', '')} / {p.get('profile', '')} | {r.get('error', '').replace('|', '/')[:160]} |")
    L += ["", "## Main matrix (60 frames; MKV, d3d12va MP4) + native 4:2:2 + containers + gop_pictreset", "",
          "| encoder | stage | input | pix_fmt_in | variant | mode | ext | ok | frames (ffprobe) | key frames | pict_types | codec/profile/pix_fmt | NVENC sess while open | decode-back frames | PSNR Y mean/min | PSNR all mean | error |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep["encode"]:
        if r.get("stage") == "format_probe":
            continue
        p, d = r.get("probe", {}), r.get("decode_back", {})
        L.append(f"| {r['encoder']} | {r.get('stage')} | {r.get('input', 'yuy2_1080p')} | {r['pix_fmt_in']} | "
                 f"{r['variant']} | {r['mode']} | {r['container']} | {'yes' if r.get('ok') else 'NO'} | "
                 f"{p.get('ffprobe_frames', '')} | {p.get('ffprobe_key_frames', '')} | {p.get('pict_types', '')} | "
                 f"{p.get('codec_name', '')}/{p.get('profile', '')}/{p.get('pix_fmt', '')} | "
                 f"{r.get('nvenc_sessions_while_open', '')} | {d.get('frames', '')} | "
                 f"{d.get('psnr_y_mean', '')}/{d.get('psnr_y_min', '')} | {d.get('psnr_all_mean', '')} | "
                 f"{(r.get('error') or d.get('error') or p.get('probe_error') or '').replace('|', '/')[:160]} |")
    if rep.get("d3d12_adapter"):
        L += ["", "## D3D12VA adapter index probe (8 frames, intra, MP4)", "",
              "| encoder | device | ok | NVENC sess while open | codec/pix_fmt | error |", "|---|---|---|---|---|---|"]
        for r in rep["d3d12_adapter"]:
            p = r.get("probe", {})
            L.append(f"| {r['encoder']} | {r['device']} | {'yes' if r.get('ok') else 'NO'} | "
                     f"{r.get('nvenc_sessions_while_open', '')} | {p.get('codec_name', '')}/{p.get('pix_fmt', '')} | "
                     f"{r.get('error', '').replace('|', '/')[:160]} |")
    if rep.get("decode"):
        L += ["", "## Decode tests (child process per test, 60 s timeout, allow_software_fallback=False)", "",
              "| input | decoder | hwaccel | decoder has hw config for device | ok | frames | output formats | PSNR Y vs CPU decode (min) | PSNR all (min) | error |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for r in rep["decode"]:
            L.append(f"| {r.get('label')} | {r.get('decoder')} | {r.get('hw') or ''}{' (hw out)' if r.get('hw_out') else ''} | "
                     f"{r.get('decoder_has_hw_config_for_device', '')} | "
                     f"{'yes' if r.get('ok') else 'NO'} | {r.get('frames', '')} | {r.get('out_formats', '')} | "
                     f"{r.get('psnr_y_vs_cpu_min', '')} | {r.get('psnr_all_vs_cpu_min', '')} | "
                     f"{r.get('error', '').replace('|', '/')[:160]} |")
    L += ["", "## FFmpeg log excerpts (first lines kept per test, for adapter/MFT/implementation identification)", ""]
    for r in rep["encode"] + rep.get("d3d12_adapter", []):
        if r.get("log") and r.get("stage") in ("main", "d3d12_adapter") and (
                r.get("tag", "").startswith("yuy2_1080p_intra") or r.get("stage") == "d3d12_adapter"):
            L.append(f"- `{r['encoder']}` {r.get('tag', r.get('device'))} {r.get('mode', '')}:")
            for ln in r["log"][:12]:
                L.append(f"  - `{ln.replace('`', '')}`")
    (RESULTS / "functional_pyav19.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--skip-decode", action="store_true")
    ap.add_argument("--frames", type=int, default=NFR)
    ap.add_argument("--child", default="")
    ap.add_argument("--tag", default="", help="suffix for result file names (subset runs)")
    ap.add_argument("--stage", default="all", choices=["all", "pictreset", "decode"])
    a = ap.parse_args()
    if a.child:
        print("CHILD_RESULT " + json.dumps(child_decode(json.loads(a.child))))
        return
    log_setup()
    OUT.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    src = load_inputs()
    names = [n for n in ENC if not a.only or n in a.only.split(",")]
    if a.stage == "decode":  # decode matrix only, reusing the encode records/files of the main run
        prev = json.loads((RESULTS / "functional_pyav19.json").read_text(encoding="utf-8"))
        rep = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "encode": [],
               "decode": decode_matrix(src, prev["encode"]), "nvidia_smi_per_encoder": {}}
        (RESULTS / f"functional_pyav19_{a.tag or 'decode'}.json").write_text(json.dumps(rep, indent=1, default=str),
                                                                             encoding="utf-8")
        print("done")
        return
    rep = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "pyav": av.__version__,
           "libavcodec": ".".join(map(str, av.library_versions["libavcodec"])),
           "hwdevices_available": list(hwdevices_available()), "python": sys.version,
           "input_formats": {k: [v[0].format.name, v[0].width, v[0].height, len(v),
                                 str(getattr(v[0], "color_range", ""))] for k, v in src.items()},
           "encoder_advertised_formats": {n: [f.name for f in (av.Codec(n, "w").video_formats or [])]
                                          for n in names if n in av.codecs_available},
           "mjpeg_decoder_hw_configs": [str(h.device_type) for h in av.Codec("mjpeg", "r").hardware_configs],
           "nvidia_smi_before": nvidia_smi(), "encode": [], "nvidia_smi_per_encoder": {}}
    for n in names:
        print(n)
        before = nvidia_smi()
        rep["encode"] += run_encoder(n, src, a.frames) if a.stage == "all" else pictreset_stage(n, src, a.frames)
        rep["nvidia_smi_per_encoder"][n] = {"before": before, "after": nvidia_smi()}
    if a.stage == "all" and (not a.only or "d3d12" in a.only):
        rep["d3d12_adapter"] = d3d12_adapter_probe(src)
    if not a.skip_decode and a.stage == "all":
        rep["decode"] = decode_matrix(src, rep["encode"])
    rep["nvidia_smi_after"] = nvidia_smi()
    sfx = f"_{a.tag}" if a.tag else ""
    (RESULTS / f"functional_pyav19{sfx}.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    if not sfx:
        write_md(rep)
    print("done")


if __name__ == "__main__":
    main()
