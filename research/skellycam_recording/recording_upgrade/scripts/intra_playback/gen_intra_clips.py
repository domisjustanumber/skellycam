# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""intra_playback clip generator (PyAV 19.0.2 only; FUNCTIONAL, no timing).

Clips for the question: can intra-only H.264/HEVC from the hardware encoders be played and scrubbed frame-exactly in
Electron 35/45 (and Chrome 156), compared with the JPEG-sequence path?

Every frame = a real corpus camera JPEG decoded with PyAV's mjpeg decoder, plus the chromium_sync_scrub 16-bit index
pattern (scripts/chromium_sync_scrub/gen_clips.py: 32 cells across the width, (bit, NOT bit) pairs, strip height =
cell width, white 255 / black 0 in RGB). The browser harness reads it back.

Per content (720p30 / 1080p30, CFR and VFR = real MF capture times incl. the 0.011 ms pair at frames 81/82):
  * h264_nvenc, hevc_nvenc, h264_qsv, hevc_qsv, all intra (NVENC gop_size=0, QSV gop_size=1, max_b_frames=0),
    from NV12 (limited range). Encoded ONCE into MP4 (+faststart, 1/90000); the identical packets are remuxed into
    fragmented MP4 (frag_keyframe+empty_moov+default_base_moof, 1/90000) and MKV (1/1000).
  * mjpeg_qsv 4:2:2 from YUYV (full range, as JPEG expects): written as (a) MKV (V_MJPEG) for <video>,
    (b) raw concatenated .mjpeg + index, both used by the JPEG path; the MKV index (byte offset of every JPEG inside
    the MKV) is the "recorder index" for the JPEG-in-MKV byte-range path.
  * camera bytes unmodified (c930e_720p_flash, first 300 frames) muxed into MKV + index: G1 + G9 byte-range check
    (the page compares the fetched range with the corpus file byte for byte).
Quality: per encoder and resolution the quality parameter is chosen from a sweep on 30 frames so that Y-PSNR is
closest to --target-db (default 55.0 dB = what mjpeg_qsv gives at about the
cameras' own JPEG bytes per frame, measured in the smoke sweep). NVENC: rc=constqp qp; QSV H.264/HEVC: ICQ global_quality; mjpeg_qsv:
global_quality (JPEG quality 1-100). PSNR is computed on luma in limited-range units (full-range JPEG luma is mapped
16 + 219*y/255 for both reference and decode), SSIM = 8x8 box-window SSIM on the same luma.

Outputs: media under C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/intra_playback/
clips/ (manifest.json = chromium_sync_scrub harness format); text summary
research/skellycam_recording/recording_upgrade/results/intra_playback/clips_summary.json.

Run (repo root):  uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_playback/gen_intra_clips.py
  options: --only <content,...> --encoders <enc,...> --frames N (smoke) --target-db 42 --no-calibrate
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from av.video.frame import PictureType

REPO = Path(__file__).resolve().parents[5]
CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/intra_playback/clips")
RESULTS = REPO / "research/skellycam_recording/recording_upgrade/results/intra_playback"
FLASH_JSONL = REPO / ("research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture/"
                      "vid_046d_pid_0843_mi_00_8_39dec205_0_0000.frames.jsonl")
BITS, CELLS = 16, 32

# content -> (corpus set, nominal fps, frames, vfr)
CONTENTS = {
    "c720p30": ("c930e_720p_flash", 30, 600, False),   # 600 distinct real frames
    "c1080p30": ("c922_1080p", 30, 600, False),        # 19 real frames looped (pattern unique per frame)
    "vfr720p": ("c930e_720p_flash", 30, 891, True),     # all 891 frames at their real capture times
    "vfr1080p": ("c922_1080p", 30, 600, True),          # 19 frames looped, first 600 real capture times
}
HW = ["h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv"]
SWEEP = {  # quality parameter candidates (lower = better for qp/ICQ; higher = better for JPEG quality)
    "h264_nvenc": list(range(5, 45, 3)), "hevc_nvenc": list(range(5, 45, 3)),
    "h264_qsv": list(range(5, 45, 3)), "hevc_qsv": list(range(5, 45, 3)),
    "mjpeg_qsv": [50, 60, 70, 75, 80, 85, 90, 95],
}
MKV_FMP4 = {"movflags": "frag_keyframe+empty_moov+default_base_moof"}

LOG: list[str] = []


class _H(logging.Handler):
    def emit(self, r):  # keep FFmpeg log lines (RC mode, IdrInterval, errors)
        LOG.append(f"{r.name}: {r.getMessage()}")


def setup_log():
    av.logging.set_level(av.logging.VERBOSE)
    lg = logging.getLogger("libav")
    lg.setLevel(logging.DEBUG)
    lg.addHandler(_H())
    lg.propagate = False


def take_log(filt=("rate", "RateControl", "ICQ", "QP", "IdrInterval", "GopPicSize", "profile", "rror", "MFT", "device")):
    out = [l for l in LOG if any(f in l for f in filt)]
    LOG.clear()
    return out[:40]


# ---- frames --------------------------------------------------------------------------------------
def jpeg_bytes(cset: str) -> list[bytes]:
    return [f.read_bytes() for f in sorted((CORPUS / cset).glob("frame_*.jpg"))]


def decode_jpeg_rgb(b: bytes) -> np.ndarray:
    cc = av.CodecContext.create("mjpeg", "r")
    fr = list(cc.decode(av.Packet(b))) + list(cc.decode(None))
    return fr[0].to_ndarray(format="rgb24")


def burn_index(img: np.ndarray, k: int) -> np.ndarray:
    h, w = img.shape[:2]
    cw = w // CELLS
    out = img.copy()
    for b in range(BITS):
        bit = (k >> (BITS - 1 - b)) & 1
        for j, v in enumerate((bit, 1 - bit)):
            x0 = (2 * b + j) * cw
            out[0:cw, x0:x0 + cw] = 255 if v else 0
    return out


def read_index_y(y: np.ndarray) -> int | None:
    """Same rule as the browser (cell centres, pair must differ by > 64), on the luma plane."""
    w = y.shape[1]
    cw = w // CELLS
    row = y[cw // 2, :].astype(np.int32)
    v = 0
    for b in range(BITS):
        a, c = row[(2 * b) * cw + cw // 2], row[(2 * b + 1) * cw + cw // 2]
        if abs(a - c) <= 64:
            return None
        v = (v << 1) | (1 if a > c else 0)
    return v


class Frames:
    """Stamped RGB frames for one content; NV12 (limited) and YUYV (full) VideoFrames on demand."""

    def __init__(self, cset: str, n: int):
        self.src = [decode_jpeg_rgb(b) for b in jpeg_bytes(cset)]
        self.n = n
        self.h, self.w = self.src[0].shape[:2]

    def rgb(self, k: int) -> np.ndarray:
        return burn_index(self.src[k % len(self.src)], k)

    def frame(self, k: int, fmt: str) -> av.VideoFrame:
        vf = av.VideoFrame.from_ndarray(self.rgb(k), format="rgb24")
        rng = 2 if fmt in ("yuyv422", "yuvj422p") else 1  # JPEG = full range; H.264/HEVC = limited range
        g = vf.reformat(format=fmt, dst_color_range=rng)
        g.pict_type = PictureType.NONE
        return g


def luma_of(fr: av.VideoFrame) -> np.ndarray:
    """Y plane as uint8 HxW (handles nv12, yuv420p, yuvj422p, yuyv422)."""
    name = fr.format.name
    if name == "yuyv422":
        a = fr.to_ndarray()  # (h, w, 2)
        return a[:, :, 0].copy()
    p = fr.planes[0]
    a = np.frombuffer(p, np.uint8).reshape(p.height, p.line_size)[:, :fr.width]
    return a.copy()


def to_limited(y: np.ndarray, full: bool) -> np.ndarray:
    y = y.astype(np.float64)
    return 16.0 + y * 219.0 / 255.0 if full else y


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a - b) ** 2))
    return 99.0 if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def _box(x: np.ndarray, r: int = 8) -> np.ndarray:
    c = np.cumsum(np.cumsum(np.pad(x, ((1, 0), (1, 0))), 0), 1)
    return (c[r:, r:] - c[:-r, r:] - c[r:, :-r] + c[:-r, :-r]) / (r * r)


def ssim(a: np.ndarray, b: np.ndarray) -> float:
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    ma, mb = _box(a), _box(b)
    va, vb, cov = _box(a * a) - ma * ma, _box(b * b) - mb * mb, _box(a * b) - ma * mb
    s = ((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma * ma + mb * mb + c1) * (va + vb + c2))
    return float(s.mean())


def vfr_times_s(n: int) -> list[float]:
    rows = [json.loads(l) for l in FLASH_JSONL.open()]
    t = [r["mf_sample_time_100ns"] for r in rows[:n]]
    return [(x - t[0]) / 1e7 for x in t]


# ---- encoders ------------------------------------------------------------------------------------
def enc_setup(name: str, q: int) -> tuple[str, int, dict]:
    """-> (input pix_fmt, gop_size, options)."""
    if name.endswith("_nvenc"):
        return "nv12", 0, {"preset": "p4", "rc": "constqp", "qp": str(q)}
    if name == "mjpeg_qsv":
        return "yuyv422", 1, {"global_quality": str(q)}
    return "nv12", 1, {"global_quality": str(q)}  # h264_qsv / hevc_qsv: ICQ


def open_cc(name: str, w: int, h: int, q: int, tb: Fraction, fps: int) -> av.CodecContext:
    fmt, gop, opts = enc_setup(name, q)
    cc = av.CodecContext.create(name, "w")
    cc.width, cc.height, cc.pix_fmt = w, h, fmt
    cc.time_base, cc.framerate = tb, Fraction(fps, 1)
    cc.max_b_frames, cc.gop_size = 0, gop
    cc.options = opts
    cc.open()
    return cc


def sw_decoder(name: str) -> str:
    return {"h264": "h264", "hevc": "hevc", "mjpeg": "mjpeg"}[name.split("_")[0]]


def quality_of(name: str, fr: Frames, ks: list[int], q: int) -> dict:
    """Encode frames ks standalone, decode with the software decoder, Y-PSNR/SSIM vs the fed luma."""
    fmt, _, _ = enc_setup(name, q)
    full = fmt == "yuyv422"
    cc = open_cc(name, fr.w, fr.h, q, Fraction(1, 30), 30)
    dec = av.CodecContext.create(sw_decoder(name), "r")
    refs, outs, nbytes = [], [], 0
    for i, k in enumerate(ks):
        f = fr.frame(k, fmt)
        f.pts = i
        refs.append(to_limited(luma_of(f), full))
        for p in cc.encode(f):
            nbytes += p.size
            outs += [to_limited(luma_of(d), full) for d in dec.decode(p)]
    for p in cc.encode(None):
        nbytes += p.size
        outs += [to_limited(luma_of(d), full) for d in dec.decode(p)]
    outs += [to_limited(luma_of(d), full) for d in dec.decode(None)]
    n = min(len(refs), len(outs))
    return {"q": q, "frames": n, "bytes_per_frame": nbytes / max(1, len(ks)),
            "y_psnr_db": round(float(np.mean([psnr(refs[i], outs[i]) for i in range(n)])), 2),
            "y_ssim": round(float(np.mean([ssim(refs[i], outs[i]) for i in range(0, n, 3)])), 4)}


def calibrate(name: str, fr: Frames, target: float) -> dict:
    ks = list(range(0, min(fr.n, 30)))
    sweep = []
    for q in SWEEP[name]:
        try:
            sweep.append(quality_of(name, fr, ks, q))
        except Exception as e:  # noqa: BLE001
            sweep.append({"q": q, "error": f"{type(e).__name__}: {e}"})
    ok = [s for s in sweep if "y_psnr_db" in s]
    best = min(ok, key=lambda s: abs(s["y_psnr_db"] - target)) if ok else None
    return {"target_y_psnr_db": target, "sweep": sweep, "chosen_q": best["q"] if best else None, "log": take_log()}


# ---- bitstream inspection ------------------------------------------------------------------------
def nal_types(pkt: bytes, codec: str, nls: int) -> list[int]:
    out, i = [], 0
    while i + nls <= len(pkt):
        ln = int.from_bytes(pkt[i:i + nls], "big")
        i += nls
        if ln <= 0 or i + ln > len(pkt):
            out.append(-1)  # not length-prefixed as expected
            break
        b0 = pkt[i]
        out.append(b0 & 0x1F if codec == "h264" else (b0 >> 1) & 0x3F)
        i += ln
    return out


def codec_string_and_desc(codec: str, ed: bytes, tag: str) -> tuple[str, str]:
    if codec == "h264":
        if len(ed) >= 4 and ed[0] == 1:
            return f"avc1.{ed[1]:02X}{ed[2]:02X}{ed[3]:02X}", ed.hex()
        raise ValueError("no avcC")
    if codec == "hevc":  # ISO/IEC 14496-15 Annex E codec string from hvcC
        if len(ed) < 23 or ed[0] != 1:
            raise ValueError("no hvcC")
        ps, tier, pidc = ed[1] >> 6, (ed[1] >> 5) & 1, ed[1] & 0x1F
        compat = int.from_bytes(ed[2:6], "big")
        rev = int(f"{compat:032b}"[::-1], 2)
        cons = list(ed[6:12])
        while cons and cons[-1] == 0:
            cons.pop()
        lvl = ed[12]
        prefix = tag if tag in ("hvc1", "hev1") else "hvc1"
        s = f"{prefix}.{['', 'A', 'B', 'C'][ps]}{pidc}.{rev:X}.{'H' if tier else 'L'}{lvl}"
        s += "".join(f".{c:02X}" for c in cons)
        return s, ed.hex()
    raise ValueError(codec)


def demux_index(path: Path, codec: str | None) -> dict:
    data = path.read_bytes()
    rows = []
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        tb = s.time_base
        cc = s.codec_context
        ed = bytes(cc.extradata) if cc.extradata else b""
        tag = s.codec_tag if hasattr(s, "codec_tag") else ""
        nls = 4
        if codec == "h264" and len(ed) > 4 and ed[0] == 1:
            nls = (ed[4] & 3) + 1
        if codec == "hevc" and len(ed) > 21 and ed[0] == 1:
            nls = (ed[21] & 3) + 1
        for p in c.demux(s):
            if p.size == 0:
                continue
            pb = bytes(p)
            pos = p.pos
            exact_at_pos = pos is not None and pos >= 0 and data[pos:pos + p.size] == pb
            off = pos if exact_at_pos else None
            if off is None:
                lo = max(0, (pos or 0) - 256)
                f = data.find(pb, lo, lo + p.size + 4096)
                off = f if f >= 0 else None
            r = {"pts": p.pts, "dts": p.dts, "key": bool(p.is_keyframe), "offset": off, "size": p.size,
                 "pos_exact": exact_at_pos, "pos_delta": (off - pos) if (off is not None and pos is not None) else None}
            if codec in ("h264", "hevc"):
                r["nal"] = nal_types(pb, codec, nls)
            rows.append(r)
    rows.sort(key=lambda r: r["pts"])
    res = {"time_base": str(tb), "tb_num": tb.numerator, "tb_den": tb.denominator, "codec_tag": tag,
           "extradata_hex": ed.hex(), "nal_length_size": nls, "rows": rows,
           "decode_order_equals_pts_order": all((a["dts"] if a["dts"] is not None else a["pts"]) <= (b["dts"] if b["dts"] is not None else b["pts"])
                                             for a, b in zip(rows, rows[1:])),
           "dts_none_count": sum(r["dts"] is None for r in rows),
           "all_offsets_found": all(r["offset"] is not None for r in rows),
           "pos_exact_count": sum(r["pos_exact"] for r in rows),
           "pos_delta_hist": {str(k): v for k, v in _hist([r["pos_delta"] for r in rows]).items()}}
    if codec in ("h264", "hevc"):
        idr = {5} if codec == "h264" else {19, 20}
        irap = {5} if codec == "h264" else set(range(16, 24))
        vcl = set(range(1, 6)) if codec == "h264" else set(range(0, 32))
        res["nal_check"] = {
            "frames": len(rows),
            "frames_with_idr": sum(1 for r in rows if idr & set(r["nal"])),
            "frames_with_non_irap_vcl": sum(1 for r in rows if (vcl - irap) & set(r["nal"])),
            "frames_flagged_key": sum(r["key"] for r in rows),
            "nal_type_hist": {str(k): v for k, v in _hist([t for r in rows for t in r["nal"]]).items()},
            "first_frame_nal": rows[0]["nal"] if rows else None,
        }
    return res


def _hist(xs):
    h = {}
    for x in xs:
        h[x] = h.get(x, 0) + 1
    return dict(sorted(h.items(), key=lambda kv: (kv[0] is None, kv[0] if kv[0] is not None else 0)))


def ffprobe(path: Path) -> dict:
    """Inspection only (ffmpeg CLI on PATH): key_frame/pict_type of every frame + stream fields."""
    try:
        fr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                             "frame=key_frame,pict_type", "-of", "csv=p=0", str(path)],
                            capture_output=True, text=True, timeout=300).stdout.split()
        st = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                             "stream=codec_name,codec_tag_string,profile,pix_fmt,color_range,has_b_frames,width,height,nb_frames",
                             "-of", "json", str(path)], capture_output=True, text=True, timeout=120).stdout
        return {"frames": len(fr), "key_frames": sum(1 for l in fr if l.startswith("1")),
                "pict_types": _hist([l.split(",")[1] if "," in l else l for l in fr]),
                "stream": json.loads(st)["streams"][0] if st else None}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def decode_check(path: Path, full: bool, ref_lumas: dict[int, np.ndarray]) -> dict:
    """Software-decode the whole file: index pattern on every frame; Y-PSNR/SSIM on the sampled frames."""
    ok = bad = unread = 0
    ps, ss = [], []
    with av.open(str(path)) as c:
        for k, fr in enumerate(c.decode(video=0)):
            y = luma_of(fr)
            idx = read_index_y(y)
            if idx is None:
                unread += 1
            elif idx == k:
                ok += 1
            else:
                bad += 1
            if k in ref_lumas:
                yl = to_limited(y, full)
                ps.append(psnr(ref_lumas[k], yl))
                ss.append(ssim(ref_lumas[k], yl))
    return {"decoded": ok + bad + unread, "pattern_ok": ok, "pattern_wrong": bad, "pattern_unreadable": unread,
            "y_psnr_db_mean": round(float(np.mean(ps)), 2) if ps else None,
            "y_psnr_db_min": round(float(np.min(ps)), 2) if ps else None,
            "y_ssim_mean": round(float(np.mean(ss)), 4) if ss else None, "quality_frames": len(ps)}


def nvsmi() -> str:
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu,utilization.decoder",
                               "--format=csv,noheader"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"error {e}"


# ---- writers -------------------------------------------------------------------------------------
def encode_mp4(path: Path, name: str, q: int, fr: Frames, times: list[float], fps: int, ref_ks: set[int]):
    tb = Fraction(1, 90000)
    fmt, gop, opts = enc_setup(name, q)
    refs = {}
    nv = {"before": nvsmi()}
    with av.open(str(path), "w", format="mp4", options={"movflags": "+faststart"}) as out:
        st = out.add_stream(name, rate=fps)
        st.width, st.height, st.pix_fmt = fr.w, fr.h, fmt
        st.time_base = tb
        cc = st.codec_context
        cc.time_base = tb
        cc.max_b_frames, cc.gop_size = 0, gop
        cc.options = opts
        prev = -1
        for k in range(fr.n):
            pts = int(round(times[k] / tb))
            pts = max(pts, prev + 1)
            prev = pts
            f = fr.frame(k, fmt)
            f.pts, f.time_base = pts, tb
            if k in ref_ks:
                refs[k] = to_limited(luma_of(f), False)
            for p in st.encode(f):
                out.mux(p)
            if k == 5:
                nv["while_open"] = nvsmi()
        for p in st.encode(None):
            out.mux(p)
    nv["after"] = nvsmi()
    return refs, nv


def remux(src: Path, dst: Path, fmt: str, opts: dict, tb_out: Fraction) -> dict:
    adjusted = 0
    with av.open(str(src)) as inp, av.open(str(dst), "w", format=fmt, options=opts) as out:
        ist = inp.streams.video[0]
        ost = out.add_stream_from_template(ist)
        ost.time_base = tb_out
        prev = -1
        for p in inp.demux(ist):
            if p.size == 0:
                continue
            t = int(round(float(p.pts * p.time_base) / tb_out))
            if t <= prev:
                t, adjusted = prev + 1, adjusted + 1
            prev = t
            p.stream = ost
            p.time_base = tb_out
            p.pts = p.dts = t
            out.mux(p)
    return {"pts_adjusted_for_monotonic": adjusted}


def write_jpeg_seq(cdir: Path, name: str, q: int, fr: Frames, times: list[float], fps: int, ref_ks: set[int]):
    """mjpeg_qsv 4:2:2: -> clip.mjpeg (+index) and mjpeg_qsv422.mkv; returns refs, packets meta."""
    cc = open_cc(name, fr.w, fr.h, q, Fraction(1, 1000), fps)
    pk, refs = [], {}
    for k in range(fr.n):
        f = fr.frame(k, "yuyv422")
        f.pts = k
        if k in ref_ks:
            refs[k] = to_limited(luma_of(f), True)
        pk += [bytes(p) for p in cc.encode(f)]
    pk += [bytes(p) for p in cc.encode(None)]
    assert len(pk) == fr.n, (len(pk), fr.n)
    jdir = cdir / "jpeg_qsv422"
    jdir.mkdir(parents=True, exist_ok=True)
    offs, sizes, blob = [], [], bytearray()
    for b in pk:
        offs.append(len(blob)); sizes.append(len(b)); blob += b
    (jdir / "clip.mjpeg").write_bytes(bytes(blob))
    mkv = cdir / "mjpeg_qsv422.mkv"
    tb = Fraction(1, 1000)
    adjusted, prev = 0, -1
    with av.open(str(mkv), "w", format="matroska") as out:
        st = out.add_mux_stream("mjpeg", rate=fps, width=fr.w, height=fr.h)
        for k, b in enumerate(pk):
            t = int(round(times[k] / tb))
            if t <= prev:
                t, adjusted = prev + 1, adjusted + 1
            prev = t
            p = av.Packet(b)
            p.stream, p.time_base = st, tb
            p.pts = p.dts = t
            p.is_keyframe = True
            out.mux(p)
    return refs, pk, offs, sizes, mkv, adjusted


def check_jpegs(pk: list[bytes]) -> dict:
    ok = bad = unread = 0
    fmts = set()
    for k, b in enumerate(pk):
        cc = av.CodecContext.create("mjpeg", "r")
        frs = list(cc.decode(av.Packet(b))) + list(cc.decode(None))
        fmts.add(frs[0].format.name)
        idx = read_index_y(luma_of(frs[0]))
        ok += idx == k
        bad += idx is not None and idx != k
        unread += idx is None
    return {"jpegs": len(pk), "pattern_ok": ok, "pattern_wrong": bad, "pattern_unreadable": unread,
            "decoded_formats": sorted(fmts), "sof0_baseline": sum(1 for b in pk if b"\xff\xc0" in b[:2000])}


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text)
    for _ in range(50):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.1)
    raise RuntimeError(f"could not replace {path}")


def video_entry(content, cset, fps, vfr, fr, key, path, codec, enc, q, ix, extra) -> dict:
    cs, desc = codec_string_and_desc(codec, bytes.fromhex(ix["extradata_hex"]), ix["codec_tag"])
    rows = ix["rows"]
    return {
        "kind": "video", "content": content, "corpus_set": cset, "distinct_source_frames": len(fr.src), "vfr": vfr,
        "nominal_fps": fps, "frames": len(rows), "frames_encoded": fr.n, "width": fr.w, "height": fr.h,
        "codec": enc, "container": "mkv" if path.suffix == ".mkv" else "mp4",
        "fragmented": "_frag" in path.name, "gop": 1, "quality_param": q,
        "url": f"/media/clips/{key}", "bytes": path.stat().st_size,
        "codec_string": cs, "description_hex": desc, "codec_tag": ix["codec_tag"],
        "time_base": ix["time_base"], "decode_order_equals_pts_order": ix["decode_order_equals_pts_order"],
        "all_offsets_found": ix["all_offsets_found"], "pos_exact_count": ix["pos_exact_count"],
        "pos_delta_hist": ix["pos_delta_hist"],
        "keyframes": [i for i, r in enumerate(rows) if r["key"]],
        "pts_s": [r["pts"] * ix["tb_num"] / ix["tb_den"] for r in rows],
        "offsets": [r["offset"] for r in rows], "sizes": [r["size"] for r in rows],
        "nal_check": ix.get("nal_check"), **extra,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--encoders", default=",".join(HW + ["mjpeg_qsv", "camera_mkv"]))
    ap.add_argument("--frames", type=int, default=0)
    ap.add_argument("--target-db", type=float, default=55.0)
    ap.add_argument("--no-calibrate", action="store_true")
    ap.add_argument("--media", default="", help="override the media folder (smoke tests: scratchpad)")
    ap.add_argument("--results", default="", help="override the text results folder (smoke tests)")
    a = ap.parse_args()
    global MEDIA, RESULTS
    if a.media:
        MEDIA = Path(a.media)
    if a.results:
        RESULTS = Path(a.results)
    setup_log()
    MEDIA.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    man_path = MEDIA / "manifest.json"
    manifest = json.loads(man_path.read_text()) if man_path.exists() else {"clips": {}, "calibration": {}}
    manifest.setdefault("calibration", {})
    manifest["generator"] = {"python": sys.version.split()[0], "pyav": av.__version__,
                             "libav": {k: ".".join(map(str, v)) for k, v in av.library_versions.items()},
                             "platform": platform.platform(), "target_y_psnr_db": a.target_db,
                             "pattern": f"{BITS} bits MSB first, (bit, NOT bit) cell pairs, {CELLS} cells, strip height = cell width"}
    encs = [x for x in a.encoders.split(",") if x]
    only = [x for x in a.only.split(",") if x]
    calib_cache: dict[tuple[str, int], dict] = {}
    for content, (cset, fps, n, vfr) in CONTENTS.items():
        if only and content not in only:
            continue
        if a.frames:
            n = min(n, a.frames)
        fr = Frames(cset, n)
        assert all(read_index_y(luma_of(fr.frame(k, "nv12"))) == k for k in range(0, min(n, 40)))
        times = vfr_times_s(n) if vfr else [k / fps for k in range(n)]
        cdir = MEDIA / content
        cdir.mkdir(exist_ok=True)
        ref_ks = set(range(0, n, 10))
        for enc in encs:
            if enc == "camera_mkv":
                continue
            ck = (enc, fr.h)
            if ck not in calib_cache:
                if a.no_calibrate:
                    calib_cache[ck] = {"chosen_q": {"mjpeg_qsv": 90}.get(enc, 23), "note": "no calibration"}
                else:
                    calib_cache[ck] = calibrate(enc, fr, a.target_db)
                manifest["calibration"][f"{enc}|{fr.h}p|{cset}"] = calib_cache[ck]
                print("calibrated", enc, fr.h, calib_cache[ck]["chosen_q"],
                      [(s.get("q"), s.get("y_psnr_db"), round(s.get("bytes_per_frame", 0))) for s in calib_cache[ck].get("sweep", [])], flush=True)
            q = calib_cache[ck]["chosen_q"]
            if enc == "mjpeg_qsv":
                refs, pk, offs, sizes, mkv, adj = write_jpeg_seq(cdir, enc, q, fr, times, fps, ref_ks)
                jc = check_jpegs(pk)
                dq = decode_check(mkv, True, refs)
                common = {"kind": "mjpeg", "content": content, "corpus_set": cset, "distinct_source_frames": len(fr.src),
                          "vfr": vfr, "nominal_fps": fps, "frames": n, "width": fr.w, "height": fr.h,
                          "codec": "mjpeg_qsv 4:2:2 (yuyv422 full range in)", "quality_param": q,
                          "pts_s": times, "keyframes": list(range(n)), "gop": 1, "jpeg_check": jc, "decode_check": dq}
                manifest["clips"][f"{content}/jpeg_seq"] = {**common, "url": f"/media/clips/{content}/jpeg_qsv422/clip.mjpeg",
                                                            "bytes": sum(sizes), "offsets": offs, "sizes": sizes}
                ix = demux_index(mkv, None)
                same = all(r["size"] == s for r, s in zip(ix["rows"], sizes))
                manifest["clips"][f"{content}/jpeg_in_mkv"] = {
                    **common, "url": f"/media/clips/{content}/mjpeg_qsv422.mkv", "bytes": mkv.stat().st_size,
                    "offsets": [r["offset"] for r in ix["rows"]], "sizes": [r["size"] for r in ix["rows"]],
                    "mkv_index": {k: ix[k] for k in ("time_base", "all_offsets_found", "pos_exact_count", "pos_delta_hist")},
                    "sizes_equal_jpeg_seq": same, "pts_adjusted_for_monotonic": adj, "ffprobe": ffprobe(mkv)}
                # the same MKV as a <video> source (expected not to play: chromium_codecs NOTES section 2)
                manifest["clips"][f"{content}/mjpeg_qsv422.mkv"] = {
                    **{k: v for k, v in common.items() if k not in ("kind",)}, "kind": "video", "container": "mkv",
                    "url": f"/media/clips/{content}/mjpeg_qsv422.mkv", "codec_string": "mjpeg", "description_hex": "",
                    "bytes": mkv.stat().st_size, "pts_s": [r["pts"] * ix["tb_num"] / ix["tb_den"] for r in ix["rows"]],
                    "offsets": [r["offset"] for r in ix["rows"]], "sizes": [r["size"] for r in ix["rows"]],
                    "video_only_expect_fail": True}
                print(content, "jpeg", jc, dq, flush=True)
                atomic_write(man_path, json.dumps(manifest))
                continue
            codec = enc.split("_")[0]
            base = f"{enc}_intra"
            mp4 = cdir / f"{base}.mp4"
            try:
                refs, nv = encode_mp4(mp4, enc, q, fr, times, fps, ref_ks)
            except Exception as e:  # noqa: BLE001
                print("ENCODE FAIL", content, enc, e, take_log(), flush=True)
                manifest["clips"][f"{content}/{base}.mp4"] = {"kind": "error", "error": f"{type(e).__name__}: {e}"}
                continue
            enc_log = take_log()
            frag = cdir / f"{base}_frag.mp4"
            mkv = cdir / f"{base}.mkv"
            rf = remux(mp4, frag, "mp4", MKV_FMP4, Fraction(1, 90000))
            rm = remux(mp4, mkv, "matroska", {}, Fraction(1, 1000))
            dq = decode_check(mp4, False, refs)
            for path, extra in [(mp4, {"mux": "+faststart"}), (frag, {"mux": MKV_FMP4["movflags"], **rf}), (mkv, {"mux": "matroska", **rm})]:
                ix = demux_index(path, codec)
                key = f"{content}/{path.name}"
                e = video_entry(content, cset, fps, vfr, fr, key, path, codec, enc, q, ix,
                                {"mux_flags": extra, "ffprobe": ffprobe(path), "nvidia_smi": nv, "encoder_log": enc_log,
                                 "decode_check_mp4": dq if path == mp4 else "same packets as mp4"})
                manifest["clips"][key] = e
                print(key, e["frames"], "frames", e["bytes"], "B", e["codec_string"], "keys", len(e["keyframes"]),
                      "nal", e["nal_check"], "offsets", e["all_offsets_found"], flush=True)
            print("  decode", dq, flush=True)
            atomic_write(man_path, json.dumps(manifest))
        if "camera_mkv" in encs and content == "c720p30":
            jb = jpeg_bytes(cset)[:300 if not a.frames else a.frames]
            mkv = cdir / "camera_bytes.mkv"
            tb = Fraction(1, 1000)
            with av.open(str(mkv), "w", format="matroska") as out:
                st = out.add_mux_stream("mjpeg", rate=fps, width=fr.w, height=fr.h)
                for k, b in enumerate(jb):
                    p = av.Packet(b)
                    p.stream, p.time_base = st, tb
                    p.pts = p.dts = int(round(k / fps / tb))
                    p.is_keyframe = True
                    out.mux(p)
            ix = demux_index(mkv, None)
            manifest["clips"][f"{content}/camera_bytes_mkv"] = {
                "kind": "camera_mkv", "content": content, "corpus_set": cset, "frames": len(jb), "width": fr.w, "height": fr.h,
                "url": f"/media/clips/{content}/camera_bytes.mkv", "corpus_url_pattern": f"/corpus/{cset}/frame_%06d.jpg",
                "bytes": mkv.stat().st_size, "offsets": [r["offset"] for r in ix["rows"]], "sizes": [r["size"] for r in ix["rows"]],
                "sizes_equal_corpus": [r["size"] for r in ix["rows"]] == [len(b) for b in jb],
                "mkv_index": {k: ix[k] for k in ("time_base", "all_offsets_found", "pos_exact_count", "pos_delta_hist")}}
            print("camera mkv", manifest["clips"][f"{content}/camera_bytes_mkv"]["mkv_index"], flush=True)
            atomic_write(man_path, json.dumps(manifest))
    summary = {k: {kk: v for kk, v in c.items() if kk not in ("pts_s", "offsets", "sizes", "keyframes", "description_hex")}
               | {"keyframe_count": len(c.get("keyframes", []))} for k, c in manifest["clips"].items()}
    (RESULTS / "clips_summary.json").write_text(json.dumps({"generator": manifest["generator"],
                                                            "calibration": manifest["calibration"], "clips": summary}, indent=1))


if __name__ == "__main__":
    main()
