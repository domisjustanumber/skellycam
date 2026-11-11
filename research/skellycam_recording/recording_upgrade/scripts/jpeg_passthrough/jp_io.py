"""Writers and readers for the jpeg_passthrough tests (no timing is measured here).

Writers put camera JPEG bytes into containers WITHOUT decode/re-encode:
  pyav    : av.Packet(jpeg_bytes) muxed into a PyAV output stream (default setup: add_mux_stream, no codec context)
  ffmpeg  : ffmpeg CLI, -f image2pipe -framerate R -i pipe:0 -c:v copy (CFR reference)
  python  : raw concatenated .mjpeg + binary index sidecar; folder of .jpg files + timestamps CSV

Readers report: ffprobe stream facts, PyAV packet SHA-256 + pts, ffmpeg -c:v copy -f image2 extraction SHA-256,
cv2.VideoCapture (CAP_FFMPEG, CAP_ANY, CAP_MSMF) counts/props/POS_MSEC/seek, FreeMoCap's VideoHelper.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

import jp_common as C

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# name -> (ffmpeg/PyAV format name, extension, muxer options[, stream time_base: None = muxer default, "rate" = 1/fps, "us" = 1/1e6])
CONTAINERS: dict[str, tuple] = {
    "mkv": ("matroska", ".mkv", {}),
    "webm": ("webm", ".webm", {}),
    "mp4": ("mp4", ".mp4", {}),
    "fmp4_1s": ("mp4", ".mp4", {"movflags": "frag_keyframe+empty_moov+default_base_moof", "min_frag_duration": "1000000"}),
    "fmp4_perframe": ("mp4", ".mp4", {"movflags": "frag_keyframe+empty_moov+default_base_moof"}),
    "mov": ("mov", ".mov", {}),
    "avi": ("avi", ".avi", {}),
    "nut": ("nut", ".nut", {}),
    "mjpeg_raw_mux": ("mjpeg", ".mjpeg", {}),
    # PyAV-only variants with an explicit stream time_base (ffmpeg CLI writer skipped for these)
    "avi_tb_rate": ("avi", ".avi", {}, "rate"),
    "mp4_tb_us": ("mp4", ".mp4", {}, "us"),
    "mov_tb_us": ("mov", ".mov", {}, "us"),
    "nut_tb_us": ("nut", ".nut", {}, "us"),
    # added 2026-11-09 for the 23:00 mux bench (jpeg_passthrough FINDINGS section 5, change 2): fMP4 at 1/1e6
    "fmp4_1s_tb_us": ("mp4", ".mp4", {"movflags": "frag_keyframe+empty_moov+default_base_moof", "min_frag_duration": "1000000"}, "us"),
    "fmp4_perframe_tb_us": ("mp4", ".mp4", {"movflags": "frag_keyframe+empty_moov+default_base_moof"}, "us"),
}
PY_CONTAINERS = ["raw_sidecar", "jpg_folder"]
IDX_REC = struct.Struct("<QIq")  # offset u64, size u32, pts_ns i64


def out_path(dirpath: Path, container: str, writer: str) -> Path:
    if container == "jpg_folder":
        return dirpath / f"{writer}_{container}" / "frame_%06d.jpg"
    if container == "raw_sidecar":
        return dirpath / f"{writer}_{container}.mjpeg"
    return dirpath / f"{writer}_{container}{CONTAINERS[container][1]}"


# ----------------------------------------------------------------------------------------------------- writers
def pyav_write(path: Path, container: str, frames: list[bytes], w: int, h: int, pts_us: list[int] | None,
               rate: int = 30, setup: str = "mux_stream", keyframe: bool = True) -> dict:
    """pts_us None -> CFR (pts = index, time_base 1/rate). Otherwise VFR: packet time_base 1/1e6, pts in us."""
    import av
    fmt, _, opts = CONTAINERS[container][:3]
    stream_tb = CONTAINERS[container][3] if len(CONTAINERS[container]) > 3 else None
    path.parent.mkdir(parents=True, exist_ok=True)
    res = {"writer": "pyav", "setup": setup, "container": container, "keyframe_flag": keyframe,
           "mode": "cfr" if pts_us is None else "vfr", "ok": False}
    c = None
    tmpl = None
    try:
        c = av.open(str(path), "w", format=fmt, options=dict(opts))
        if setup == "mux_stream":
            st = c.add_mux_stream("mjpeg", rate=rate, width=w, height=h)
        elif setup == "mux_stream_nodims":
            st = c.add_mux_stream("mjpeg", rate=rate)
        elif setup == "encoder_ctx":
            st = c.add_stream("mjpeg", rate=rate)
            st.width, st.height = w, h
            st.pix_fmt = "yuvj422p"
        elif setup == "encoder_ctx_420":
            st = c.add_stream("mjpeg", rate=rate)
            st.width, st.height = w, h
            st.pix_fmt = "yuvj420p"
        elif setup == "template":
            tmp = Path(tempfile.mkdtemp(dir=C.TEMP)) / "t.jpg"
            tmp.write_bytes(frames[0])
            tmpl = av.open(str(tmp))
            st = c.add_stream_from_template(tmpl.streams.video[0])
        else:
            raise ValueError(setup)
        if stream_tb == "rate":
            st.time_base = Fraction(1, rate)
        elif stream_tb == "us":
            st.time_base = Fraction(1, 1_000_000)
        res["stream_time_base_requested"] = str(st.time_base) if stream_tb else None
        pkt_tb = Fraction(1, rate) if pts_us is None else Fraction(1, 1_000_000)
        n = 0
        for k, fb in enumerate(frames):
            pkt = av.Packet(fb)
            pkt.stream = st
            pkt.time_base = pkt_tb
            pkt.pts = pkt.dts = k if pts_us is None else pts_us[k]
            pkt.is_keyframe = keyframe
            c.mux(pkt)
            n += 1
            if k == 0:
                res["stream_time_base_after_first_mux"] = str(st.time_base)
        res["packets_muxed"] = n
        c.close()
        c = None
        res["ok"] = True
    except Exception as e:  # noqa: BLE001 - record the exact error
        res["error"] = f"{type(e).__name__}: {e}"
        try:
            if c is not None:
                c.close()
        except Exception as e2:  # noqa: BLE001
            res["close_error"] = f"{type(e2).__name__}: {e2}"
    finally:
        if tmpl is not None:
            tmpl.close()
    res["bytes"] = path.stat().st_size if path.exists() else None
    return res


def ffmpeg_write(path: Path, container: str, frames: list[bytes], rate: int = 30) -> dict:
    fmt, _, opts = CONTAINERS[container][:3]
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-f", "image2pipe", "-framerate", str(rate), "-i", "pipe:0",
           "-c:v", "copy", "-f", fmt]
    for k, v in opts.items():
        cmd += [f"-{k}", v]
    cmd.append(str(path))
    p = subprocess.run(cmd, input=b"".join(frames), capture_output=True)
    err = p.stderr.decode("utf8", "replace")
    warn = [ln for ln in err.splitlines() if any(t in ln.lower() for t in ("error", "warn", "invalid", "non monoton", "not supported", "could not"))]
    return {"writer": "ffmpeg", "container": container, "mode": "cfr", "ok": p.returncode == 0 and path.exists(),
            "returncode": p.returncode, "cmd": " ".join(cmd[:-1] + ["<out>"]), "stderr_flags": warn[:8],
            "bytes": path.stat().st_size if path.exists() else None}


def python_write(path: Path, container: str, frames: list[bytes], pts_ns: list[int]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if container == "raw_sidecar":
        off = 0
        with open(path, "wb") as f, open(path.with_suffix(".idx"), "wb") as fi:
            for fb, t in zip(frames, pts_ns):
                f.write(fb)
                fi.write(IDX_REC.pack(off, len(fb), t))
                off += len(fb)
        return {"writer": "python", "container": container, "mode": "vfr", "ok": True, "bytes": off,
                "sidecar_bytes": path.with_suffix(".idx").stat().st_size}
    if container == "jpg_folder":
        d = path.parent
        for k, fb in enumerate(frames):
            (d / f"frame_{k:06d}.jpg").write_bytes(fb)
        with open(d / "timestamps.csv", "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["frame_number", "pts_ns"])
            wr.writerows(enumerate(pts_ns))
        return {"writer": "python", "container": container, "mode": "vfr", "ok": True, "bytes": sum(map(len, frames)),
                "files": len(frames) + 1}
    raise ValueError(container)


def read_sidecar(path: Path) -> tuple[list[bytes], list[int]]:
    data = path.read_bytes()
    idx = path.with_suffix(".idx").read_bytes()
    frames, pts = [], []
    for i in range(len(idx) // IDX_REC.size):
        off, size, t = IDX_REC.unpack_from(idx, i * IDX_REC.size)
        frames.append(data[off:off + size])
        pts.append(t)
    return frames, pts


# ----------------------------------------------------------------------------------------------------- readers
def ffprobe(path: Path, is_pattern: bool = False) -> dict:
    cmd = [FFPROBE, "-v", "error", "-count_packets", "-show_streams", "-show_format",
           "-show_entries", "packet=pts,pts_time,dts,flags,size", "-of", "json"]
    if is_pattern:
        cmd += ["-f", "image2"]
    cmd.append(str(path))
    p = subprocess.run(cmd, capture_output=True)
    out = {"returncode": p.returncode, "stderr": p.stderr.decode("utf8", "replace").strip()[:400]}
    if p.returncode != 0:
        return out
    j = json.loads(p.stdout)
    vs = [s for s in j.get("streams", []) if s.get("codec_type") == "video"]
    if vs:
        s = vs[0]
        out.update({k: s.get(k) for k in ("codec_name", "codec_tag_string", "width", "height", "pix_fmt", "r_frame_rate",
                                          "avg_frame_rate", "time_base", "nb_frames", "nb_read_packets", "duration")})
    out["format_name"] = j.get("format", {}).get("format_name")
    out["format_duration"] = j.get("format", {}).get("duration")
    pk = [x for x in j.get("packets", []) if int(x.get("size", 0)) > 0]
    out["packets_nonempty"] = len(pk)
    out["packets_empty"] = len(j.get("packets", [])) - len(pk)
    out["pts_time"] = [float(x["pts_time"]) if x.get("pts_time") not in (None, "N/A") else None for x in pk]
    out["keyframe_flags"] = sum(1 for x in pk if "K" in x.get("flags", ""))
    return out


def pyav_demux(path: Path, is_pattern: bool = False, decode: bool = True) -> dict:
    import av
    out = {"ok": False}
    try:
        kw = {"format": "image2"} if is_pattern else {}
        with av.open(str(path), **kw) as c:
            st = c.streams.video[0]
            out["codec"] = st.codec_context.name if st.codec_context else None
            out["time_base"] = str(st.time_base)
            out["frames_hdr"] = st.frames
            shas, pts, kf, empty, dec_err, dec_n = [], [], 0, 0, [], 0
            for pkt in c.demux(st):
                if pkt.size == 0:
                    empty += 1 if pkt.dts is not None else 0
                    continue
                b = bytes(pkt)
                shas.append(C.sha(b))
                pts.append(None if pkt.pts is None else float(pkt.pts * pkt.time_base))
                kf += 1 if pkt.is_keyframe else 0
                if decode:
                    try:
                        dec_n += len(pkt.decode())
                    except Exception as e:  # noqa: BLE001
                        dec_err.append(f"{len(shas)-1}: {type(e).__name__}: {e}"[:160])
            out.update({"ok": True, "shas": shas, "pts_s": pts, "keyframes": kf, "empty_packets": empty,
                        "decoded_frames": dec_n, "decode_errors": dec_err[:5], "decode_error_count": len(dec_err)})
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"[:300]
    return out


def pyav_seek(path: Path, targets: list[int], pts_ref: list[float]) -> list[dict]:
    """Seek to the pts of input frame k (backward=True, keyframe seek), decode one frame, compare its pts."""
    import av
    res = []
    try:
        with av.open(str(path)) as c:
            st = c.streams.video[0]
            for k in targets:
                tgt = int(round(pts_ref[k] / st.time_base)) if st.time_base else None
                try:
                    c.seek(tgt, stream=st, backward=True, any_frame=False)
                    fr = next(c.decode(st))
                    got = float(fr.pts * st.time_base) if fr.pts is not None else None
                    res.append({"k": k, "target_s": pts_ref[k], "got_s": got,
                                "exact": got is not None and abs(got - pts_ref[k]) < float(st.time_base) / 2 + 1e-9})
                except Exception as e:  # noqa: BLE001
                    res.append({"k": k, "error": f"{type(e).__name__}: {e}"[:160]})
    except Exception as e:  # noqa: BLE001
        res.append({"error": f"{type(e).__name__}: {e}"[:200]})
    return res


def ffmpeg_extract(path: Path, is_pattern: bool = False, bsf: str | None = None) -> dict:
    d = Path(tempfile.mkdtemp(dir=C.TEMP, prefix="extract_"))
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y"]
    if is_pattern:
        cmd += ["-f", "image2"]
    cmd += ["-i", str(path), "-c:v", "copy"]
    if bsf:
        cmd += ["-bsf:v", bsf]
    cmd += ["-f", "image2", str(d / "%06d.jpg")]
    p = subprocess.run(cmd, capture_output=True)
    files = sorted(d.glob("*.jpg"))
    datas = [f.read_bytes() for f in files]
    shutil.rmtree(d, ignore_errors=True)
    err = p.stderr.decode("utf8", "replace")
    return {"returncode": p.returncode, "n": len(datas), "shas": [C.sha(x) for x in datas], "first": datas[0] if datas else None,
            "stderr_flags": [ln for ln in err.splitlines() if any(t in ln.lower() for t in ("error", "warn", "invalid", "auto-inserting"))][:6]}


def _fh(fr) -> str:
    return hashlib.sha1(fr.tobytes()).hexdigest()


def cv2_read(path: Path, backend_name: str, input_frames: list[bytes] | None = None, seek: bool = True) -> dict:
    import cv2
    import numpy as np
    be = {"FFMPEG": cv2.CAP_FFMPEG, "ANY": cv2.CAP_ANY, "MSMF": cv2.CAP_MSMF, "IMAGES": cv2.CAP_IMAGES}[backend_name]
    out = {"backend_req": backend_name}
    cap = cv2.VideoCapture(str(path), be)
    out["opened"] = bool(cap.isOpened())
    if not out["opened"]:
        return out
    try:
        out["backend"] = cap.getBackendName()
    except Exception:  # noqa: BLE001
        out["backend"] = "?"
    fc = int(cap.get(cv2.CAP_PROP_FOURCC))
    out.update({"frame_count_prop": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), "fps_prop": cap.get(cv2.CAP_PROP_FPS),
                "fourcc": "".join(chr((fc >> 8 * i) & 0xFF) for i in range(4)) if fc > 0 else str(fc),
                "w": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), "h": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))})
    hashes, msec, frames_kept = [], [], {}
    keep = set()
    if input_frames is not None:
        n_in = len(input_frames)
        keep = {0, n_in // 2, n_in - 1}
    k = 0
    while True:
        ok, fr = cap.read()
        if not ok or fr is None:
            break
        hashes.append(_fh(fr))
        msec.append(cap.get(cv2.CAP_PROP_POS_MSEC))
        if k in keep:
            frames_kept[k] = fr
        k += 1
        if k > 20000:
            break
    out["frames_read"] = len(hashes)
    out["_hashes"] = hashes
    out["pos_msec"] = msec
    out["unique_frame_hashes"] = len(set(hashes))
    # decoded frame k vs cv2.imdecode of input JPEG k (and k-1, k+1): mean abs diff
    if input_frames is not None and frames_kept:
        cmp = {}
        for kk, fr in frames_kept.items():
            row = {}
            for j in (kk - 1, kk, kk + 1):
                if 0 <= j < len(input_frames):
                    ref = cv2.imdecode(np.frombuffer(input_frames[j], np.uint8), cv2.IMREAD_COLOR)
                    if ref is not None and ref.shape == fr.shape:
                        row[str(j - kk)] = round(float(np.abs(ref.astype(np.int16) - fr.astype(np.int16)).mean()), 4)
            cmp[str(kk)] = row
        out["mad_vs_imdecode_input_offsets"] = cmp
    if seek and len(hashes) > 3:
        n = len(hashes)
        targets = [0, 1, 2, n // 3, n // 2, n - 2, n - 1, 5, n // 2, 3]
        sk = []
        for t in targets:
            okset = cap.set(cv2.CAP_PROP_POS_FRAMES, t)
            ok, fr = cap.read()
            h = _fh(fr) if ok and fr is not None else None
            got = hashes.index(h) if h in hashes else -1
            sk.append({"k": t, "set_ok": bool(okset), "read_ok": bool(ok), "match": h == hashes[t], "got_index": got})
        out["seek"] = sk
        out["seek_exact"] = sum(s["match"] for s in sk)
        out["seek_total"] = len(sk)
    cap.release()
    return out


_VH = None


def freemocap_videohelper():
    """Import FreeMoCap's real VideoHelper (read-only repo) without importing the whole freemocap package."""
    global _VH
    if _VH is None:
        p = Path("C:/Users/Dom/GitHub/freemocap/freemocap/freemocap/core/pipeline/posthoc/video_group_helper.py")
        spec = importlib.util.spec_from_file_location("fmc_video_group_helper", p)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["fmc_video_group_helper"] = mod
        spec.loader.exec_module(mod)
        _VH = mod.VideoHelper
    return _VH


def freemocap_read(path: Path, ref_hashes: list[str] | None) -> dict:
    out = {}
    try:
        VH = freemocap_videohelper()
        vh = VH.from_video_path(path)
        md = vh.metadata
        out.update({"frame_count": md.frame_count, "fps": md.fps, "fourcc": md.fourcc, "w": md.width, "h": md.height})
        reads = []
        n = md.frame_count
        for t in [0, 1, n // 2, n - 1]:
            try:
                fr = vh.read_frame_number(t)
                h = _fh(fr)
                reads.append({"k": t, "ok": True, "match_cv2_sequential": (ref_hashes is not None and t < len(ref_hashes) and h == ref_hashes[t])})
            except Exception as e:  # noqa: BLE001
                reads.append({"k": t, "ok": False, "error": f"{type(e).__name__}: {e}"[:160]})
        out["reads"] = reads
        vh.video_reader.release()
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"[:300]
    return out
