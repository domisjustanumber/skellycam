# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""GF09 (functional only, NO timing): lossless / nearest-lossless intra on Quick Sync, and exactness of the
NVENC lossless settings that the timed items 35/56/57 used.

Parts (--part):
  qsv    h264_qsv / hevc_qsv, all-intra (gop_size=1), CQP at QP 0 / 1 / 4, low_power auto/on/off, hevc transform_skip,
         hevc profile rext. Inputs: NV12 1080p (from the C930e YUY2 frames), Bayer8 quad as NV12 (Y + neutral chroma),
         and for hevc_qsv also Bayer8 quad as VUYX (4:4:4) and the camera's own YUYV422 bytes.
  nvenc  h264_nvenc / hevc_nvenc with the bench's own config entries (functional_matrix.py:83-84: preset p1,
         tune lossless, gop 1 from cfg default at :53) and path chooser (functional_matrix.choose_path, as
         bench_intra.py:108), thread_count=1 (bench t1). Cases = bench_suite.py:57-61 group 'gpu' lossless cases
         (1080p and 720p) plus Bayer8 quad on both encoders (1080p).
         Decoders: PyAV software (libavcodec h264/hevc), h264_cuvid/hevc_cuvid, hwaccel cuda and d3d11va
         (allow_software_fallback=False).
Every case: 300 frames = the 8 corpus frames looped (as the bench), written to MKV in the GF09 media folder,
decoded back, compared per frame and per plane (max abs diff), ffprobe'd for profile / pix_fmt / level.
Media files are deleted after the check, except the ones named in KEEP (used by the Chromium check).

Run from the repo root:
  uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/gapfill/GF09/gf09_lossless_check.py --part qsv
  uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/gapfill/GF09/gf09_lossless_check.py --part nvenc
Writes results/uncompressed_intra/gapfill/GF09_rows_<part>_pyav19.0.2.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import av
import av.logging
import numpy as np

HERE = Path(__file__).resolve()
UI_SCRIPTS = HERE.parents[2]  # scripts/uncompressed_intra
sys.path.insert(0, str(UI_SCRIPTS))
import functional_matrix as fm  # noqa: E402  (read-only import: config list + exact path chooser)
import uintra_frames as uf  # noqa: E402

RESULTS = HERE.parents[4] / "results" / "uncompressed_intra" / "gapfill"
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/gapfill/GF09")
NFRAMES = 300
ONLY = ""
KEEP = {"nvenc__h264_nvenc__nv12_1080p__t1.mkv", "nvenc__hevc_nvenc__nv12_1080p__t1.mkv"}
FFPROBE = "ffprobe"


# ---------------------------------------------------------------- helpers
def ffprobe(path: Path) -> dict:
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                            "stream=codec_name,profile,pix_fmt,level,width,height,nb_read_packets,color_range",
                            "-of", "json", str(path)], capture_output=True, text=True, timeout=120)
        s = json.loads(r.stdout)["streams"][0]
        return s
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def canon(planes: list[np.ndarray], fmt: str, w: int, h: int) -> list[np.ndarray]:
    """Tight planes of `fmt` -> planar list of sample arrays [Y, U, V] (uint8, or uint16 sample values)."""
    if fmt in ("yuv420p", "yuvj420p", "yuv422p", "yuvj422p", "yuv444p", "yuvj444p"):
        return [p for p in planes]
    if fmt == "gray":
        return [planes[0]]
    if fmt == "nv12":
        return [planes[0], planes[1][:, 0::2], planes[1][:, 1::2]]
    if fmt == "p010le":
        y = planes[0].view("<u2") >> 6
        uv = planes[1].view("<u2") >> 6
        return [y, uv[:, 0::2], uv[:, 1::2]]
    if fmt in ("yuv420p10le", "yuv444p10le"):
        return [p.view("<u2") for p in planes]
    if fmt == "yuyv422":
        a = planes[0]
        return [a[:, 0::2], a[:, 1::4], a[:, 3::4]]
    if fmt == "vuyx":
        a = planes[0].reshape(h, w, 4)
        return [a[:, :, 2], a[:, :, 1], a[:, :, 0]]
    raise KeyError(fmt)


def read_frame(fr) -> tuple[str, list[np.ndarray]]:
    fmt = fr.format.name
    norm = fmt.replace("yuvj", "yuv")
    return norm, canon(uf.read_planes(fr, norm), norm, fr.width, fr.height)


def compare(dec: list[np.ndarray], ref: list[np.ndarray], data_planes: int) -> dict:
    out = {"max_abs": [], "shape_ok": True}
    for i, r in enumerate(ref):
        if i >= len(dec) or dec[i].shape != r.shape:
            out["shape_ok"] = False
            out["max_abs"].append(None)
            continue
        out["max_abs"].append(int(np.max(np.abs(dec[i].astype(np.int32) - r.astype(np.int32)))))
    d = out["max_abs"]
    out["exact_data"] = out["shape_ok"] and all(x == 0 for x in d[:data_planes])
    out["exact_all"] = out["shape_ok"] and all(x == 0 for x in d)
    if out["shape_ok"]:
        peak = 1023.0 if ref[0].dtype == np.uint16 else 255.0
        mse = float(np.mean((dec[0].astype(np.float64) - ref[0].astype(np.float64)) ** 2))
        out["psnr_y"] = 99.0 if mse == 0 else round(10 * np.log10(peak * peak / mse), 3)
    return out


def summarize(per: list[dict], n_expected: int) -> dict:
    s = {"frames_decoded": len(per), "frames_expected": n_expected}
    if not per:
        return s
    s["frames_exact_data"] = sum(1 for p in per if p["exact_data"])
    s["frames_exact_all_planes"] = sum(1 for p in per if p["exact_all"])
    nplanes = len(per[0]["max_abs"])
    s["max_abs_per_plane"] = [max((p["max_abs"][i] for p in per if p["max_abs"][i] is not None), default=None)
                              for i in range(nplanes)]
    ps = [p["psnr_y"] for p in per if "psnr_y" in p]
    if ps and s["frames_exact_data"] < len(per):
        s["psnr_y_min"] = min(ps)
        s["psnr_y_mean"] = round(float(np.mean([min(x, 99.0) for x in ps])), 3)
    return s


def libav_lines(cap, levels=av.logging.VERBOSE, grep=None) -> list[str]:
    out = []
    for lvl, name, msg in cap:
        if lvl <= levels:
            m = msg.strip()
            if not grep or any(g in m for g in grep):
                out.append(f"{name}: {m}")
    return out


def demux_info(path: Path) -> dict:
    with av.open(str(path)) as c:
        vs = c.streams.video[0]
        kf = []
        sizes = []
        for p in c.demux(vs):
            if p.size:
                kf.append(bool(p.is_keyframe))
                sizes.append(p.size)
        return {"packets": len(kf), "keyframe_packets": sum(kf), "packet_bytes_mean": round(float(np.mean(sizes)), 1),
                "coded_profile_pyav": vs.codec_context.profile,
                "extradata_len": len(vs.codec_context.extradata or b"")}


def decode_sw(path: Path) -> tuple[list, str | None, str | None]:
    """Default libav software decoder. Returns (frames as (fmt, planes)), decoder name, error)."""
    res, err, name = [], None, None
    try:
        with av.open(str(path)) as c:
            vs = c.streams.video[0]
            vs.codec_context.thread_count = 1
            name = vs.codec_context.name
            for fr in c.decode(vs):
                res.append(read_frame(fr))
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:300]}"
    return res, name, err


def decode_cuvid(path: Path, codec: str) -> tuple[list, str | None, str | None, list[str]]:
    res, err = [], None
    logs: list[str] = []
    try:
        with av.logging.Capture() as cap:
            try:
                with av.open(str(path)) as c:
                    vs = c.streams.video[0]
                    ctx = av.CodecContext.create(codec, "r")
                    ctx.extradata = vs.codec_context.extradata
                    ctx.width, ctx.height = vs.codec_context.width, vs.codec_context.height
                    for p in c.demux(vs):
                        if not p.size:
                            continue  # demux ends with an empty packet; flush exactly once below
                        for fr in ctx.decode(p):
                            res.append(read_frame(fr))
                    for fr in ctx.decode(None):
                        res.append(read_frame(fr))
            finally:
                logs = libav_lines(cap, av.logging.WARNING)[:8]
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:300]}"
    return res, codec, err, logs


def decode_hwaccel(path: Path, dev: str) -> tuple[list, str | None, str | None, list[str]]:
    from av.codec.hwaccel import HWAccel
    res, err, info = [], None, None
    logs: list[str] = []
    try:
        with av.logging.Capture() as cap:
            try:
                with av.open(str(path), hwaccel=HWAccel(dev, allow_software_fallback=False)) as c:
                    vs = c.streams.video[0]
                    for fr in c.decode(vs):
                        res.append(read_frame(fr))
                    info = f"{vs.codec_context.name} is_hwaccel={getattr(vs.codec_context, 'is_hwaccel', '?')}"
            finally:
                logs = libav_lines(cap, av.logging.WARNING)[:8]
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:300]}"
    return res, info, err, logs


def check_decodes(path: Path, refs: list[list[np.ndarray]], data_planes: int, decoders: list[str], codec_id: str) -> dict:
    out = {}
    for d in decoders:
        logs: list[str] = []
        if d == "sw":
            frames, name, err = decode_sw(path)
        elif d == "cuvid":
            frames, name, err, logs = decode_cuvid(path, f"{codec_id}_cuvid")
        else:
            frames, name, err, logs = decode_hwaccel(path, d)
        per = [compare(pl, refs[i], data_planes) for i, (_f, pl) in enumerate(frames[:len(refs)])]
        s = summarize(per, len(refs))
        s.update(decoder=name, error=err, decoded_pix_fmt=frames[0][0] if frames else None)
        if logs:
            s["libav_log"] = logs
        nonexact = [i for i, p in enumerate(per) if not p["exact_data"]]
        if nonexact:
            s["first_nonexact_frames"] = nonexact[:10]
        out[d] = s
    return out


def encode(path: Path, codec: str, pix: str, w: int, h: int, opts: dict, gop: int | None, fed: list[list[np.ndarray]],
           threads: int | None, verbose: bool) -> dict:
    r: dict = {"opened": False}
    if path.exists():
        path.unlink()
    with av.logging.Capture() as cap:
        old = av.logging.get_level()
        if verbose:
            av.logging.set_level(av.logging.VERBOSE)
        try:
            with av.open(str(path), "w") as oc:
                st = oc.add_stream(codec, rate=30, options=dict(opts))
                st.width, st.height, st.pix_fmt = w, h, pix
                if gop is not None:
                    st.codec_context.gop_size = gop
                if threads is not None:
                    st.codec_context.thread_count = threads
                n = 0
                for i in range(NFRAMES):
                    fr = uf.make_frame(fed[i % len(fed)], pix, w, h)
                    fr.pts, fr.time_base = i, Fraction(1, 30)
                    for p in st.encode(fr):
                        oc.mux(p)
                        n += 1
                    r["opened"] = True
                for p in st.encode(None):
                    oc.mux(p)
                    n += 1
                r["packets_written"] = n
            r["stage"] = "ok"
        except Exception as e:  # noqa: BLE001
            r["stage"] = "failed"
            r["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        finally:
            av.logging.set_level(old)
            r["libav_warnings"] = libav_lines(cap, av.logging.WARNING)[:10]
            if verbose:
                r["libav_param_dump"] = libav_lines(cap, av.logging.VERBOSE, grep=(
                    "profile:", "RateControlMethod", "QPI", "VDENC", "TransformSkip", "GopPicSize", "ratecontrol",
                    "ChromaFormat", "FourCC", "LowPower", "Using the"))[:24]
    return r


def run_case(row: dict, path: Path, codec: str, pix: str, w: int, h: int, opts: dict, gop, fed, refs, data_planes,
             decoders, codec_id, threads=None, verbose=False) -> dict | None:
    if ONLY and ONLY not in row["id"]:
        return None
    row.update(encode(path, codec, pix, w, h, opts, gop, fed, threads, verbose))
    if row.get("stage") == "ok":
        row["file_bytes"] = path.stat().st_size
        row["ffprobe"] = ffprobe(path)
        row.update(demux_info(path))
        row["decode"] = check_decodes(path, refs, data_planes, decoders, codec_id)
        sw = row["decode"].get("sw", {})
        print(f"  {row['id']}: ok {row['ffprobe'].get('profile')} {row['ffprobe'].get('pix_fmt')} "
              f"sw exact {sw.get('frames_exact_data')}/{NFRAMES} maxabs {sw.get('max_abs_per_plane')} "
              f"psnr_min {sw.get('psnr_y_min', '-')} kf {row.get('keyframe_packets')}/{row.get('packets')}", flush=True)
        for d in decoders[1:]:
            x = row["decode"][d]
            print(f"     {d}: {x.get('decoder')} exact {x.get('frames_exact_data')}/{x.get('frames_decoded')} "
                  f"{x.get('decoded_pix_fmt')} err={x.get('error')}", flush=True)
    else:
        print(f"  {row['id']}: FAILED {row.get('error')} | {row.get('libav_warnings')[:3]}", flush=True)
    if path.exists() and path.name not in KEEP:
        path.unlink()
    return row


def neutral(rows: int, cols: int) -> np.ndarray:
    return np.full((rows, cols), 128, np.uint8)


# ---------------------------------------------------------------- QSV
def qsv_inputs(yuy: list[np.ndarray], w: int, h: int) -> dict:
    """name -> (pix_fmt fed, fed planes list, reference canonical planes list (per unique frame), data planes)."""
    out = {}
    nv12 = [uf.derive("nv12", f, w, h, i)[0] for i, f in enumerate(yuy)]
    out["nv12"] = ("nv12", nv12, [canon(p, "nv12", w, h) for p in nv12], 3)
    quad = [uf.derive("bayer8_quad", f, w, h, i)[0][0] for i, f in enumerate(yuy)]
    q_nv12 = [[q, neutral(h // 2, w)] for q in quad]
    out["bayer8_quad_as_nv12"] = ("nv12", q_nv12, [canon(p, "nv12", w, h) for p in q_nv12], 1)
    out["bayer8_quad_as_vuyx"] = ("vuyx", None, None, 1)  # built lazily (hevc only)
    q_vuyx = []
    for q in quad:
        a = np.empty((h, w, 4), np.uint8)
        a[:, :, 0] = 128  # V
        a[:, :, 1] = 128  # U
        a[:, :, 2] = q    # Y
        a[:, :, 3] = 0    # X
        q_vuyx.append([a.reshape(h, w * 4)])
    out["bayer8_quad_as_vuyx"] = ("vuyx", q_vuyx, [canon(p, "vuyx", w, h) for p in q_vuyx], 1)
    yv = [[f.copy()] for f in yuy]
    out["yuyv422"] = ("yuyv422", yv, [canon(p, "yuyv422", w, h) for p in yv], 3)
    return out


def cqp(qp: int, **extra) -> dict:
    # CQP via the qscale flag (qsvenc.c:576,592-594); quant = global_quality / FF_QP2LAMBDA (qsvenc.c:923), 118 per QP.
    # i_qfactor/i_qoffset pinned (K3; QPI = quant*|i_qfactor| + i_qoffset, qsvenc.c:929).
    d = {"flags": "+qscale", "global_quality": str(qp * 118), "i_qfactor": "1", "i_qoffset": "0"}
    d.update({k: str(v) for k, v in extra.items()})
    return d


QSV_CONFIGS = [
    # (id, encoders, options)
    ("cqp_qp0", ("h264_qsv", "hevc_qsv"), cqp(0)),
    ("cqp_qp1", ("h264_qsv", "hevc_qsv"), cqp(1)),
    ("cqp_qp1_lp1", ("h264_qsv", "hevc_qsv"), cqp(1, low_power=1)),
    ("cqp_qp1_lp0", ("h264_qsv", "hevc_qsv"), cqp(1, low_power=0)),
    ("cqp_qp1_ts1", ("hevc_qsv",), cqp(1, transform_skip=1)),
    ("cqp_qp4_ts1", ("hevc_qsv",), cqp(4, transform_skip=1)),
    ("cqp_qp1_rext", ("hevc_qsv",), cqp(1, profile="rext")),
]
QSV_INPUTS = {"h264_qsv": ("nv12", "bayer8_quad_as_nv12"),
              "hevc_qsv": ("nv12", "bayer8_quad_as_nv12", "bayer8_quad_as_vuyx", "yuyv422")}


def part_qsv() -> dict:
    yuy, w, h = uf.load_yuy2("c930e_1080p_yuy2", 8)
    inputs = qsv_inputs(yuy, w, h)
    rows = []
    for cid, encs, opts in QSV_CONFIGS:
        for enc in encs:
            for iname in QSV_INPUTS[enc]:
                if cid == "cqp_qp1_rext" and iname not in ("nv12",):
                    continue  # rext is already implied for vuyx / yuyv422 inputs
                pix, fed, refs1, dp = inputs[iname]
                refs = [refs1[i % len(refs1)] for i in range(NFRAMES)]
                row = {"part": "qsv", "id": f"{enc}__{cid}__{iname}", "encoder": enc, "config": cid,
                       "options": opts, "gop_size": 1, "input": iname, "pix_fmt_fed": pix, "data_planes": dp}
                path = MEDIA / f"qsv__{enc}__{cid}__{iname}.mkv"
                r = run_case(row, path, enc, pix, w, h, opts, 1, fed, refs, dp, ["sw"], enc.split("_")[0], verbose=True)
                if r:
                    rows.append(r)
    return {"rows": rows, "source": "corpus c930e_1080p_yuy2, 8 frames looped to 300"}


# ---------------------------------------------------------------- NVENC
NVENC_CASES = [  # (config id, bench source name, res) - bench_suite.py:57-61 lossless cases + Bayer8 quad
    ("h264_nvenc_intra_lossless.mkv", "nv12", "1080p"),
    ("h264_nvenc_intra_lossless.mkv", "gray", "1080p"),
    ("hevc_nvenc_intra_lossless.mkv", "nv12", "1080p"),
    ("hevc_nvenc_intra_lossless.mkv", "p010le", "1080p"),
    ("hevc_nvenc_intra_lossless.mkv", "bayer8", "1080p"),
    ("h264_nvenc_intra_lossless.mkv", "bayer8_quad", "1080p"),
    ("hevc_nvenc_intra_lossless.mkv", "bayer8_quad", "1080p"),
    ("h264_nvenc_intra_lossless.mkv", "nv12", "720p"),
    ("h264_nvenc_intra_lossless.mkv", "gray", "720p"),
    ("hevc_nvenc_intra_lossless.mkv", "nv12", "720p"),
    ("hevc_nvenc_intra_lossless.mkv", "p010le", "720p"),
    ("hevc_nvenc_intra_lossless.mkv", "bayer8", "720p"),
]
BENCH_SOURCES = {"nv12": "nv12", "gray": "gray", "p010le": "p010le", "bayer8": "bayer_rggb8", "bayer8_quad": "bayer8_quad"}


def part_nvenc() -> dict:
    cfgs = {c["id"]: c for c in fm.CONFIGS}
    cache = {}
    rows = []
    for cid, src, res in NVENC_CASES:
        c = cfgs[cid]
        if res not in cache:
            cache[res] = uf.load_yuy2("c930e_1080p_yuy2", 8) if res == "1080p" else uf.load_jpeg_as_yuy2("c930e_720p_flash", 8)
        yuy, w, h = cache[res]
        key = BENCH_SOURCES[src]
        srcs = [uf.derive(key, f, w, h, idx=i) for i, f in enumerate(yuy)]  # as bench_intra.py:101
        _p0, src_fmt, fw, fh = srcs[0]
        enc_fmts = [f.name for f in (av.Codec(c["codec"], "w").video_formats or [])]
        path_ = fm.choose_path(key, src_fmt, enc_fmts, c["lossless"], c["codec"], c["opts"])
        fed = [path_["fwd"](pl, fw, fh) for pl, _fmt, _, _ in srcs]
        tgt = path_["target"]
        refs1 = [canon(p, tgt, fw, fh) for p in fed]
        data_planes = 1 if (src in ("gray", "bayer8", "bayer8_quad")) else 3
        refs = [refs1[i % len(refs1)] for i in range(NFRAMES)]
        row = {"part": "nvenc", "id": f"{c['codec']}__{src}_{res}", "encoder": c["codec"], "config": cid,
               "options": c["opts"], "gop_size": c["gop"], "threads": 1, "input": src, "res": res,
               "src_pix_fmt": src_fmt, "pix_fmt_fed": tgt, "path": path_["method"], "data_planes": data_planes,
               "bench_file_stem": f"{cid}__{src}_{res}"}
        path = MEDIA / f"nvenc__{c['codec']}__{src}_{res}__t1.mkv"
        r = run_case(row, path, c["codec"], tgt, fw, fh, c["opts"], c["gop"], fed, refs, data_planes,
                     ["sw", "cuvid", "cuda", "d3d11va"], c["codec"].split("_")[0], threads=1)
        if r:
            rows.append(r)
    return {"rows": rows, "source": "corpus c930e_1080p_yuy2 (1080p) / c930e_720p_flash decoded (720p), 8 frames looped to 300"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=["qsv", "nvenc"])
    ap.add_argument("--frames", type=int, default=300, help="smoke runs only; the result file is tagged")
    ap.add_argument("--only", default="", help="substring filter on case ids (smoke runs)")
    a = ap.parse_args()
    global NFRAMES, ONLY
    NFRAMES, ONLY = a.frames, a.only
    MEDIA.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    head = {"av_version": av.__version__, "library_versions": {k: list(v) for k, v in av.library_versions.items()},
            "numpy": np.__version__, "python": sys.version.split()[0], "frames": NFRAMES,
            "note": "functional only; no timing recorded", "script": str(HERE.relative_to(HERE.parents[5]))}
    try:
        head["nvidia_smi_before"] = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,encoder.stats.sessionCount",
                                                    "--format=csv,noheader"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:  # noqa: BLE001
        head["nvidia_smi_before"] = str(e)
    body = part_qsv() if a.part == "qsv" else part_nvenc()
    head.update(body)
    tag = "" if (NFRAMES == 300 and not ONLY) else "_smoke"
    out = RESULTS / f"GF09_rows_{a.part}_pyav19.0.2{tag}.json"
    out.write_text(json.dumps(head, indent=1, default=str))
    print("wrote", out)


if __name__ == "__main__":
    main()
