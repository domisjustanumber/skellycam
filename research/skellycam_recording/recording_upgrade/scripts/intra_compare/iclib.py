"""intra_compare: inputs, intra-only encode paths, decode-back checks and quality metrics (FUNCTIONAL, no timing).

Implementation under test: PyAV 19.0.2 (bundled FFmpeg 9.0.2), simplejpeg 1.9.0 (bundled libjpeg-turbo 3.1.2),
nvidia-nvimgcodec-cu12 0.10.0.9 (nvJPEG). Imported by sweep.py (PEP 723 header there).

Inputs (input classes; every conversion below is explicit, in numpy, so the reference is unambiguous):
  yuy2_1080p : corpus c930e_1080p_yuy2 + c922_1080p_yuy2, 8 + 8 real packed YUYV frames (limited range, as delivered).
  yuy2_720p  : the same 16 frames scaled 1920x1080 -> 1280x720 by PyAV swscale (yuyv422 -> yuyv422, default
               interpolation), exactly as scripts/hw_accel_target/benchlib.py:yuy2_frames_bytes does. DERIVED.
  mjpeg_720p : corpus c930e_720p_flash + c922_720p_flash, first 120 camera JPEGs each, decoded by PyAV 'mjpeg'
               (software) -> yuvj422p full range.
  mjpeg_1080p: corpus c930e_1080p + c922_1080p, all 19 + 19 camera JPEGs, decoded the same way.
Source domain = the range the input arrives in (YUY2: limited/tv; decoded JPEG: full/pc). Every metric is computed in
the source domain: decoded output samples are mapped to it in float (no rounding) before comparison.
  4:2:2 source planes: exact (unpacked YUYV, or the decoder's yuvj422p planes).
  4:2:0 chroma: vertical average of 4:2:2 chroma row pairs, rounded ((a+b+1)>>1), done once in the source domain.
  Range change (only where an encoder needs the other range): rounded and clipped, in numpy:
      lim->full  Y'=(Y-16)*255/219, C'=(C-128)*255/224+128 ; full->lim  Y'=Y*219/255+16, C'=(C-128)*224/255+128
  JPEG paths are fed full range (JFIF convention); H.264/HEVC paths are fed limited range (tv, what the bench feeds).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from scipy.ndimage import gaussian_filter

REPO = Path(__file__).resolve().parents[5]
STUDY = REPO / "research/skellycam_recording/recording_upgrade"
RESULTS = STUDY / "results/intra_compare"
RAWROOT = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109")
CORPUS = RAWROOT / "corpus"
MEDIA = RAWROOT / "intra_compare"
TEMP = Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/intra_compare")
FFPROBE = shutil.which("ffprobe") or "ffprobe"  # inspection only

INPUTS = {
    "yuy2_1080p": dict(kind="yuy2", sets=[("c930e_1080p_yuy2", 8), ("c922_1080p_yuy2", 8)], size=(1920, 1080)),
    "yuy2_720p": dict(kind="yuy2", sets=[("c930e_1080p_yuy2", 8), ("c922_1080p_yuy2", 8)], size=(1280, 720)),
    "mjpeg_720p": dict(kind="mjpeg", sets=[("c930e_720p_flash", 120), ("c922_720p_flash", 120)], size=(1280, 720)),
    "mjpeg_1080p": dict(kind="mjpeg", sets=[("c930e_1080p", 19), ("c922_1080p", 19)], size=(1920, 1080)),
}


# ------------------------------------------------------------------ plane helpers
def plane_array(frame: av.VideoFrame, i: int, w: int, h: int) -> np.ndarray:
    p = frame.planes[i]
    return np.frombuffer(p, np.uint8).reshape(-1, p.line_size)[:h, :w].copy()


def frame_from_planes(fmt: str, planes: list[np.ndarray], w: int, h: int) -> av.VideoFrame:
    """Fill a PyAV frame plane by plane, respecting line_size (planar yuv/yuvj formats, nv12, yuyv422)."""
    f = av.VideoFrame(w, h, fmt)
    for i, arr in enumerate(planes):
        p = f.planes[i]
        dst = np.frombuffer(p, np.uint8).reshape(-1, p.line_size)
        dst[: arr.shape[0], : arr.shape[1]] = arr
    return f


def yuyv_unpack(buf: bytes, w: int, h: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a = np.frombuffer(buf, np.uint8).reshape(h, w * 2)
    return a[:, 0::2].copy(), a[:, 1::4].copy(), a[:, 3::4].copy()


def yuyv_pack(y: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    h, w = y.shape
    out = np.empty((h, w * 2), np.uint8)
    out[:, 0::2] = y
    out[:, 1::4] = u
    out[:, 3::4] = v
    return out


def down420(c: np.ndarray) -> np.ndarray:
    return ((c[0::2].astype(np.uint16) + c[1::2].astype(np.uint16) + 1) >> 1).astype(np.uint8)


def nv12_array(y: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    h, w = y.shape
    uv = np.empty((h // 2, w), np.uint8)
    uv[:, 0::2] = u
    uv[:, 1::2] = v
    return np.vstack([y, uv])


def lim2full_f(y, c=False):
    return (y - 128.0) * 255.0 / 224.0 + 128.0 if c else (y - 16.0) * 255.0 / 219.0


def full2lim_f(y, c=False):
    return (y - 128.0) * 224.0 / 255.0 + 128.0 if c else y * 219.0 / 255.0 + 16.0


def to_u8(a) -> np.ndarray:
    return np.clip(np.rint(a), 0, 255).astype(np.uint8)


def map_range(planes, src: str, dst: str, as_float=False):
    """planes = (Y, U, V); src/dst in {'lim','full'}."""
    if src == dst:
        out = [p.astype(np.float32) for p in planes] if as_float else list(planes)
        return out
    fn = lim2full_f if (src, dst) == ("lim", "full") else full2lim_f
    out = [fn(planes[0].astype(np.float32)), fn(planes[1].astype(np.float32), True),
           fn(planes[2].astype(np.float32), True)]
    return out if as_float else [to_u8(p) for p in out]


# ------------------------------------------------------------------ inputs
class Src:
    """One source frame: 4:2:2 planes in the source domain + derived 4:2:0 chroma + camera JPEG bytes (mjpeg)."""

    def __init__(self, cam: str, idx: int, y, u, v, rng: str, jpeg: bytes | None):
        self.cam, self.idx, self.rng, self.jpeg = cam, idx, rng, jpeg
        self.y, self.u, self.v = y, u, v
        self.u420, self.v420 = down420(u), down420(v)
        self.h, self.w = y.shape


def load_input(name: str) -> list[Src]:
    cfg = INPUTS[name]
    w, h = cfg["size"]
    out: list[Src] = []
    for setname, n in cfg["sets"]:
        if cfg["kind"] == "yuy2":
            for i, p in enumerate(sorted((CORPUS / setname).glob("frame_*.yuy2"))[:n]):
                buf = p.read_bytes()
                if (w, h) != (1920, 1080):  # derived 720p: PyAV swscale yuyv422 -> yuyv422 scaled (benchlib.py)
                    f = frame_from_planes("yuyv422", [np.frombuffer(buf, np.uint8).reshape(1080, 3840)], 1920, 1080)
                    g = f.reformat(width=w, height=h, format="yuyv422")
                    buf = plane_array(g, 0, w * 2, h).tobytes()
                y, u, v = yuyv_unpack(buf, w, h)
                out.append(Src(setname, i, y, u, v, "lim", None))
        else:
            dec = av.CodecContext.create("mjpeg", "r")
            for i, p in enumerate(sorted((CORPUS / setname).glob("frame_*.jpg"))[:n]):
                jb = p.read_bytes()
                fr = list(dec.decode(av.Packet(jb)))
                assert len(fr) == 1 and fr[0].format.name == "yuvj422p", (setname, i, fr and fr[0].format.name)
                f = fr[0]
                out.append(Src(setname, i, plane_array(f, 0, w, h), plane_array(f, 1, w // 2, h),
                               plane_array(f, 2, w // 2, h), "full", jb))
    return out


# ------------------------------------------------------------------ metrics
def psnr_mse(mse: float) -> float:
    return 99.0 if mse <= 1e-10 else float(10 * np.log10(255.0 ** 2 / mse))


def ssim(a: np.ndarray, b: np.ndarray) -> float:
    """SSIM (Wang et al. 2004): Gaussian window sigma 1.5, radius 5 (truncate 3.5), K1 0.01, K2 0.03, L 255,
    population covariance, mean over the image with a 5-pixel border excluded. Same parameters as
    scikit-image structural_similarity(gaussian_weights=True, sigma=1.5, use_sample_covariance=False, data_range=255)."""
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    g = lambda x: gaussian_filter(x, 1.5, truncate=3.5, mode="reflect")  # noqa: E731
    ux, uy = g(a), g(b)
    uxx, uyy, uxy = g(a * a), g(b * b), g(a * b)
    vx, vy, vxy = uxx - ux * ux, uyy - uy * uy, uxy - ux * uy
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    s = ((2 * ux * uy + c1) * (2 * vxy + c2)) / ((ux * ux + uy * uy + c1) * (vx + vy + c2))
    return float(s[5:-5, 5:-5].mean())


def up422(c420: np.ndarray) -> np.ndarray:
    """4:2:0 -> 4:2:2 chroma for the 4:2:2-referenced metric: linear interpolation between row centres
    (rows of a vertically averaged pair sit between the two source rows), edge rows replicated."""
    c = c420.astype(np.float32)
    prev = np.vstack([c[:1], c[:-1]])
    nxt = np.vstack([c[1:], c[-1:]])
    out = np.empty((c.shape[0] * 2, c.shape[1]), np.float32)
    out[0::2] = 0.75 * c + 0.25 * prev
    out[1::2] = 0.75 * c + 0.25 * nxt
    return out


def metrics(src: Src, dec_planes, dec_rng: str, fed_planes=None, fed_rng: str | None = None) -> dict:
    """dec_planes: decoded (Y, U, V) uint8 at the output's chroma resolution, in dec_rng.
    psnr_y / ssim_y      : decoded Y mapped to the source domain vs the source Y (all paths comparable).
    psnr_yuv_422         : Y + chroma vs the 4:2:2 source planes (4:2:0 output chroma upsampled by up422) -> total loss,
                           including chroma subsampling; sample-count weighted MSE over the three planes.
    psnr_yuv_fed         : codec-only loss vs the frame actually fed, at its own chroma resolution and range."""
    Y, U, V = map_range(dec_planes, dec_rng, src.rng, as_float=True)
    sy = src.y.astype(np.float32)
    se_y = float(np.sum((Y - sy) ** 2))
    r = {"psnr_y": psnr_mse(se_y / sy.size), "ssim_y": ssim(sy, Y)}
    if U.shape != src.u.shape:
        U, V = up422(U), up422(V)
    se_c = float(np.sum((U - src.u) ** 2) + np.sum((V - src.v) ** 2))
    r["psnr_yuv_422"] = psnr_mse((se_y + se_c) / (sy.size + 2 * src.u.size))
    if fed_planes is not None:
        se = sum(float(np.sum((d.astype(np.float32) - f.astype(np.float32)) ** 2)) for d, f in zip(dec_planes, fed_planes))
        r["psnr_yuv_fed"] = psnr_mse(se / sum(f.size for f in fed_planes))
    return r


# ------------------------------------------------------------------ bitstream checks
def nal_types(data: bytes, codec: str) -> list[int]:
    """NAL unit types in an Annex B access unit (start codes 00 00 01 / 00 00 00 01)."""
    out, i, n = [], 0, len(data)
    while True:
        j = data.find(b"\x00\x00\x01", i)
        if j < 0 or j + 3 >= n:
            break
        b = data[j + 3]
        out.append(b & 0x1F if codec == "h264" else (b >> 1) & 0x3F)
        i = j + 3
    return out


def vcl_all_idr(types: list[int], codec: str) -> bool:
    if codec == "h264":
        vcl = [t for t in types if 1 <= t <= 5]
        return bool(vcl) and all(t == 5 for t in vcl)
    vcl = [t for t in types if t <= 31]
    return bool(vcl) and all(t in (19, 20) for t in vcl)


def stats_qp(pkt) -> float | None:
    """AV_PKT_DATA_QUALITY_STATS first 4 bytes = quality (QP * FF_QP2LAMBDA) when the encoder sets it."""
    try:
        for sd in pkt.iter_sidedata():
            raw = bytes(sd)
            if len(raw) >= 5:
                return int.from_bytes(raw[:4], "little") / 118.0
    except Exception:  # noqa: BLE001
        return None
    return None


def probe(path: Path) -> dict:
    """ffprobe inspection: stream fields incl. has_b_frames + per-frame key_frame/pict_type counts."""
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name,profile,pix_fmt,width,height,has_b_frames,color_range", "-of", "json",
                        str(path)], capture_output=True, text=True, timeout=120)
    info: dict = {}
    try:
        info.update(json.loads(r.stdout)["streams"][0])
    except Exception:  # noqa: BLE001
        info["probe_error"] = (r.stderr or r.stdout)[-300:]
        return info
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=key_frame,pict_type",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=120)
    rows = [ln.strip().rstrip(",").split(",") for ln in r.stdout.splitlines() if ln.strip()]
    info["ffprobe_frames"] = len(rows)
    info["ffprobe_key_frames"] = sum(1 for x in rows if x[0] == "1")
    types: dict = {}
    for x in rows:
        types[x[1] if len(x) > 1 else "?"] = types.get(x[1] if len(x) > 1 else "?", 0) + 1
    info["pict_types"] = types
    return info


# ------------------------------------------------------------------ encode paths
# path id -> dict(family, encoder, chroma, fed pix_fmt, fed range, knob name, coarse grid)
JPEG_Q = [50, 70, 80, 85, 90, 95, 98]
QP = [12, 16, 20, 24, 28, 32, 36]
PATHS: dict[str, dict] = {
    "jpeg_turbo_422": dict(family="jpeg", enc="simplejpeg", chroma="4:2:2", knob="quality", grid=JPEG_Q),
    "jpeg_turbo_420": dict(family="jpeg", enc="simplejpeg", chroma="4:2:0", knob="quality", grid=JPEG_Q),
    "ff_mjpeg_422": dict(family="jpeg", enc="mjpeg", chroma="4:2:2", fmt="yuvj422p", knob="qscale (qmin=qmax)",
                         grid=[1, 2, 3, 4, 6, 8, 12]),
    "ff_mjpeg_420": dict(family="jpeg", enc="mjpeg", chroma="4:2:0", fmt="yuvj420p", knob="qscale (qmin=qmax)",
                         grid=[1, 2, 3, 4, 6, 8, 12]),
    "mjpeg_qsv_422": dict(family="jpeg", enc="mjpeg_qsv", chroma="4:2:2", fmt="yuyv422", knob="global_quality",
                          grid=JPEG_Q),
    "mjpeg_qsv_420": dict(family="jpeg", enc="mjpeg_qsv", chroma="4:2:0", fmt="nv12", knob="global_quality",
                          grid=JPEG_Q),
    "nvjpeg_422": dict(family="jpeg", enc="nvjpeg", chroma="4:2:2", knob="quality", grid=JPEG_Q),
    "nvjpeg_420": dict(family="jpeg", enc="nvjpeg", chroma="4:2:0", knob="quality", grid=JPEG_Q),
    "h264_nvenc_420": dict(family="h264", enc="h264_nvenc", chroma="4:2:0", fmt="nv12", knob="qp (rc=constqp)", grid=QP),
    "hevc_nvenc_420": dict(family="hevc", enc="hevc_nvenc", chroma="4:2:0", fmt="nv12", knob="qp (rc=constqp)", grid=QP),
    "h264_qsv_420": dict(family="h264", enc="h264_qsv", chroma="4:2:0", fmt="nv12", knob="qp (CQP: +qscale, global_quality=qp*118)", grid=QP),
    "hevc_qsv_420": dict(family="hevc", enc="hevc_qsv", chroma="4:2:0", fmt="nv12", knob="qp (CQP: +qscale, global_quality=qp*118)", grid=QP),
    "hevc_qsv_422": dict(family="hevc", enc="hevc_qsv", chroma="4:2:2", fmt="yuyv422", knob="qp (CQP: +qscale, global_quality=qp*118)", grid=QP),
    "libx264_ultrafast_420": dict(family="h264", enc="libx264", chroma="4:2:0", fmt="yuv420p", knob="qp", grid=QP,
                                  preset="ultrafast"),
    "libx264_veryfast_420": dict(family="h264", enc="libx264", chroma="4:2:0", fmt="yuv420p", knob="qp", grid=QP,
                                 preset="veryfast"),
    "libx265_ultrafast_420": dict(family="hevc", enc="libx265", chroma="4:2:0", fmt="yuv420p", knob="qp", grid=QP,
                                  preset="ultrafast"),
}
# intra QP = knob: i_qfactor=1, i_qoffset=0 (FFmpeg default i_qfactor=-0.8 scales the intra QP; see NOTES.md)
IQ = {"i_qfactor": "1", "i_qoffset": "0"}


def codec_options(pid: str, value: int) -> dict:
    p = PATHS[pid]
    e = p["enc"]
    if e == "mjpeg":
        return {"qmin": str(value), "qmax": str(value)}
    if e == "mjpeg_qsv":
        return {"global_quality": str(value)}
    if e.endswith("_nvenc"):
        return {"preset": "p4", "tune": "ll", "rc": "constqp", "qp": str(value), **IQ}
    if e.endswith("_qsv"):
        return {"flags": "+qscale", "global_quality": str(value * 118), **IQ}
    if e == "libx264":
        return {"preset": p["preset"], "qp": str(value), **IQ}
    if e == "libx265":
        return {"preset": p["preset"], "qp": str(value), "x265-params": "log-level=error", **IQ}
    return {}


def gop_for(pid: str) -> int:
    return 0 if PATHS[pid]["enc"].endswith("_nvenc") else 1  # nvenc.c:1764-1766: gop_size 0 -> gopLength 1


def fed_planes(pid: str, s: Src):
    """(planes at the fed chroma resolution, fed range)."""
    p = PATHS[pid]
    rng = "full" if p["family"] == "jpeg" else "lim"
    if p["chroma"] == "4:2:2":
        planes = [s.y, s.u, s.v]
    else:
        planes = [s.y, s.u420, s.v420]
    return map_range(planes, s.rng, rng), rng


def rgb_from_src(s: Src) -> np.ndarray:
    """Exact float BT.601 (JFIF) YCbCr -> RGB of the 4:2:2 source (limited sources mapped to full range in float
    first), chroma replicated horizontally, rounded and clipped to uint8. Recomputing Y from this RGB with the JFIF
    forward matrix returns the source Y except for rounding and clipping (diag: nvjpeg_rgb_diag.json)."""
    y, u, v = map_range([s.y, s.u, s.v], s.rng, "full", as_float=True)
    cb = np.repeat(u, 2, axis=1) - 128.0
    cr = np.repeat(v, 2, axis=1) - 128.0
    rgb = np.stack([y + 1.402 * cr, y - 0.344136 * cb - 0.714136 * cr, y + 1.772 * cb], axis=-1)
    return to_u8(rgb)


def make_frame(pid: str, planes) -> av.VideoFrame:
    fmt = PATHS[pid]["fmt"]
    y, u, v = planes
    h, w = y.shape
    if fmt == "yuyv422":
        return frame_from_planes("yuyv422", [yuyv_pack(y, u, v)], w, h)
    if fmt == "nv12":
        return av.VideoFrame.from_ndarray(nv12_array(y, u, v), format="nv12")
    return frame_from_planes(fmt, [y, u, v], w, h)


def decode_jpeg(data: bytes, dec) -> tuple[list[np.ndarray], str]:
    fr = list(dec.decode(av.Packet(data)))
    assert len(fr) == 1, "jpeg decode gave %d frames" % len(fr)
    f = fr[0]
    w, h = f.width, f.height
    if f.format.name in ("yuvj422p", "yuv422p"):
        cw, ch = w // 2, h
    elif f.format.name in ("yuvj420p", "yuv420p"):
        cw, ch = w // 2, h // 2
    else:
        raise RuntimeError("unexpected decoded pix_fmt " + f.format.name)
    return [plane_array(f, 0, w, h), plane_array(f, 1, cw, ch), plane_array(f, 2, cw, ch)], f.format.name


_NV = {}


def nvjpeg_encode(pid: str, s: Src, q: int) -> bytes:
    """nvImageCodec 0.10.0.9 nvjpeg_cuda_encoder from host RGB (YUV input is not accepted: results/gpu_encode/
    nvimgcodec_jpeg.md). RGB made by PyAV swscale from the 4:2:2 source frame (BT.601, source range)."""
    from nvidia import nvimgcodec as nv  # noqa: PLC0415
    if "enc" not in _NV:
        _NV["enc"] = nv.Encoder(encoder_ids=["nvjpeg_cuda_encoder"])  # backend selector fails (gpu_encode notes)
        _NV["nv"] = nv
    rgb = rgb_from_src(s)  # exact float BT.601; PyAV swscale rgb24 capped PSNR-Y near 46.7 dB (nvjpeg_rgb_diag.json)
    css = _NV["nv"].ChromaSubsampling.CSS_422 if PATHS[pid]["chroma"] == "4:2:2" else _NV["nv"].ChromaSubsampling.CSS_420
    params = _NV["nv"].EncodeParams(quality_type=_NV["nv"].QualityType.QUALITY, quality_value=q, chroma_subsampling=css)
    cs = _NV["enc"].encode(np.ascontiguousarray(rgb), "jpeg", params=params)
    if cs is None:
        raise RuntimeError("nvimgcodec encode returned None")
    return bytes(cs)


def run_point(pid: str, srcs: list[Src], value: int, keep_media: Path | None = None) -> dict:
    """Encode every source frame at one knob value, decode back in software, verify intra, compute metrics."""
    p = PATHS[pid]
    rec: dict = {"path": pid, "encoder": p["enc"], "chroma": p["chroma"], "knob": p["knob"], "value": value,
                 "frames_in": len(srcs)}
    per: list[dict] = []
    if p["family"] == "jpeg":
        rec["fed_range"] = "full"
        dec = av.CodecContext.create("mjpeg", "r")
        cc = None
        if p["enc"] in ("mjpeg", "mjpeg_qsv"):
            cc = av.CodecContext.create(p["enc"], "w")
            cc.width, cc.height, cc.pix_fmt = srcs[0].w, srcs[0].h, p["fmt"]
            cc.time_base, cc.framerate = Fraction(1, 30), Fraction(30, 1)
            cc.gop_size = 1
            cc.options = codec_options(pid, value)
            cc.open()
            rec["options"] = codec_options(pid, value)
            rec["pix_fmt_fed"] = p["fmt"]
        elif p["enc"] == "simplejpeg":
            rec["options"] = {"quality": value, "fastdct": False, "planes": "Y,U,V " + p["chroma"]}
        else:
            rec["options"] = {"quality_type": "QUALITY", "quality_value": value,
                              "chroma_subsampling": "CSS_422" if p["chroma"] == "4:2:2" else "CSS_420",
                              "input": "host RGB24, exact float BT.601 from the 4:2:2 source (iclib.rgb_from_src)"}
        outs: list[bytes] = []
        pend: list[Src] = []
        for i, s in enumerate(srcs):
            planes, rng = fed_planes(pid, s)
            if p["enc"] == "simplejpeg":
                import simplejpeg  # noqa: PLC0415
                outs.append(simplejpeg.encode_jpeg_yuv_planes(*[np.ascontiguousarray(x) for x in planes],
                                                              quality=value, fastdct=False))
            elif p["enc"] == "nvjpeg":
                outs.append(nvjpeg_encode(pid, s, value))
            else:
                f = make_frame(pid, planes)
                f.pts = i
                outs += [bytes(k) for k in cc.encode(f)]
            pend.append((s, planes))
        if cc is not None:
            outs += [bytes(k) for k in cc.encode(None)]
        rec["packets"] = len(outs)
        dec_fmts = set()
        for (s, planes), data in zip(pend, outs):
            dp, fmtname = decode_jpeg(data, dec)
            dec_fmts.add(fmtname)
            m = metrics(s, dp, "full", None if p["enc"] == "nvjpeg" else planes, "full")
            m.update(cam=s.cam, idx=s.idx, bytes=len(data), sof=hex(data[data.find(b"\xff\xc0") + 1]) if b"\xff\xc0" in data else "no SOF0")
            per.append(m)
        rec["decoded_pix_fmts"] = sorted(dec_fmts)
        rec["decoded_frames"] = len(per)
        rec["all_intra"] = True  # every JPEG is an independent intra image (decoded one by one above)
        if keep_media is not None:
            keep_media.mkdir(parents=True, exist_ok=True)
            for k, data in enumerate(outs[:3]):
                (keep_media / f"{pid}_q{value}_{k:03d}.jpg").write_bytes(data)
    else:
        codec = p["family"]
        rec["fed_range"] = "lim"
        cc = av.CodecContext.create(p["enc"], "w")
        cc.width, cc.height, cc.pix_fmt = srcs[0].w, srcs[0].h, p["fmt"]
        cc.time_base, cc.framerate = Fraction(1, 30), Fraction(30, 1)
        cc.max_b_frames = 0
        cc.gop_size = gop_for(pid)
        cc.options = codec_options(pid, value)
        cc.open()
        rec.update(options=codec_options(pid, value), gop_size=gop_for(pid), max_b_frames=0, pix_fmt_fed=p["fmt"])
        pkts, fed = [], []
        for i, s in enumerate(srcs):
            planes, rng = fed_planes(pid, s)
            f = make_frame(pid, planes)
            f.pts = i
            pkts += list(cc.encode(f))
            fed.append(planes)
        pkts += list(cc.encode(None))
        datas = [bytes(k) for k in pkts]
        rec["packets"] = len(datas)
        rec["packet_keyflags"] = sum(1 for k in pkts if k.is_keyframe)
        qps = [stats_qp(k) for k in pkts]
        rec["stats_qp_values"] = sorted({q for q in qps if q is not None})
        types = [nal_types(d, codec) for d in datas]
        rec["all_vcl_idr"] = all(vcl_all_idr(t, codec) for t in types)
        rec["nal_type_sets"] = sorted({tuple(sorted(set(t))) for t in types})
        rec["param_sets_every_packet"] = all((7 in t and 8 in t) if codec == "h264" else (32 in t and 33 in t and 34 in t)
                                             for t in types)
        # decode-back from a file (raw Annex B elementary stream) with the PyAV software decoder
        TEMP.mkdir(parents=True, exist_ok=True)
        fd, tmpname = tempfile.mkstemp(suffix="." + codec, dir=TEMP)
        tmp = Path(tmpname)
        with open(fd, "wb") as fh:
            for d in datas:
                fh.write(d)
        dec_frames = []
        with av.open(str(tmp), format=codec) as ic:
            st = ic.streams.video[0]
            for fr in ic.decode(st):
                w, h = fr.width, fr.height
                if fr.format.name == "yuv420p":
                    cw, ch = w // 2, h // 2
                elif fr.format.name == "yuv422p":
                    cw, ch = w // 2, h
                else:
                    raise RuntimeError("unexpected decoded pix_fmt " + fr.format.name)
                dec_frames.append(([plane_array(fr, 0, w, h), plane_array(fr, 1, cw, ch), plane_array(fr, 2, cw, ch)],
                                   getattr(fr.pict_type, "name", str(fr.pict_type)), bool(fr.key_frame), fr.format.name))
            rec["decoder_has_b_frames"] = int(st.codec_context.has_b_frames)
            rec["decoder_profile"] = st.codec_context.profile
        rec["decoded_frames"] = len(dec_frames)
        rec["decoded_pict_types"] = sorted({d[1] for d in dec_frames})
        rec["decoded_all_key"] = all(d[2] for d in dec_frames)
        rec["decoded_pix_fmts"] = sorted({d[3] for d in dec_frames})
        rec["all_intra"] = (rec["all_vcl_idr"] and rec["decoded_all_key"] and rec["decoded_frames"] == len(srcs)
                            and rec["decoder_has_b_frames"] == 0)
        if keep_media is not None:
            keep_media.mkdir(parents=True, exist_ok=True)
            dst = keep_media / f"{pid}_qp{value}.{codec}"
            shutil.copyfile(tmp, dst)
            rec["ffprobe"] = probe(dst)
            rec["media"] = str(dst)
        tmp.unlink(missing_ok=True)
        for s, planes, d, data in zip(srcs, fed, dec_frames, datas):
            m = metrics(s, d[0], "lim", planes, "lim")
            m.update(cam=s.cam, idx=s.idx, bytes=len(data))
            per.append(m)
    rec["frames_ok"] = rec["decoded_frames"] == len(srcs)
    rec["per_frame"] = per
    rec.update(summarize(per))
    return rec


def summarize(per: list[dict]) -> dict:
    out = {}
    if not per:
        return out
    out["bytes_per_frame"] = round(float(np.mean([x["bytes"] for x in per])), 1)
    for k in ("psnr_y", "ssim_y", "psnr_yuv_422", "psnr_yuv_fed"):
        v = [x[k] for x in per if k in x]
        if v:
            out[k] = round(float(np.mean(v)), 5 if k == "ssim_y" else 3)
            out[k + "_min"] = round(float(np.min(v)), 5 if k == "ssim_y" else 3)
    return out
