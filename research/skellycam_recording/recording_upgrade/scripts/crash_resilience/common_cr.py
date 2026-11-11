"""Shared helpers for the crash_resilience topic (goal G2).

Variant table (payload x container), corpus loading, and the three readers used to judge a damaged file:
ffprobe -count_frames, a PyAV decode loop, and a cv2.VideoCapture read loop, plus duration/seek checks and
the -c copy repair. No camera is touched: frames come from the shared real-camera corpus.

Runs with the skellycam venv (PyAV 18.0.0 / libavformat 62.12.102 = FFmpeg 8.1, OpenCV 4.12.0) and the ffmpeg/ffprobe
9.0.2 on PATH. Media outputs go under C:/Users/Dom/Documents/skellycam-raw/... (never the repo).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
STUDY = REPO / "research/skellycam_recording/recording_upgrade"
RES = STUDY / "results/crash_resilience"
BENCH = RES / "bench"
SCRIPTS = Path(__file__).resolve().parent
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience")
CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
TEMP = Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/crash_resilience")
VENV_PY = REPO / ".venv/Scripts/python.exe"
FPS = 30
DEFAULT_SET = "c930e_720p_flash"

# ---------------------------------------------------------------------------------------------- corpus
def load_jpegs(set_name: str = DEFAULT_SET, n: int = 150) -> list[bytes]:
    """The camera's own JPEG bytes; frames are looped (frame i = corpus frame i % count) if n > count."""
    idx = json.loads((CORPUS / "index.json").read_text())
    count = idx[set_name]["frames"]
    d = CORPUS / set_name
    base = [(d / f"frame_{i:06d}.jpg").read_bytes() for i in range(min(n, count))]
    return [base[i % len(base)] for i in range(n)]


def corpus_dims(set_name: str = DEFAULT_SET) -> tuple[int, int]:
    idx = json.loads((CORPUS / "index.json").read_text())
    return idx[set_name]["width"], idx[set_name]["height"]


def sha(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


# ---------------------------------------------------------------------------------------------- variants
# payload -> encoder settings (None = MJPEG passthrough, packets are the camera's bytes)
PAYLOADS = {
    "mjpeg": None,
    "ffv1": {"codec": "ffv1", "pix_fmt": "yuv422p", "gop": 1, "options": {"level": "3", "slicecrc": "1", "slices": "4"}},
    "av1": {"codec": "libsvtav1", "pix_fmt": "yuv420p", "gop": 30, "options": {"preset": "10", "crf": "35"}},
    "h264nv": {"codec": "h264_nvenc", "pix_fmt": "yuv420p", "gop": 30, "options": {"preset": "p4", "bf": "0", "rc": "vbr", "cq": "23"}},
}

# container id -> (libavformat format, extension, format options, kind)
# kind: file | segment | rawidx | folder
CONTAINERS = {
    "mkv": ("matroska", "mkv", {}, "file"),
    "mkv_cl0": ("matroska", "mkv", {"cluster_size_limit": "0", "cluster_time_limit": "0"}, "file"),
    "mkv_resv": ("matroska", "mkv", {"reserve_index_space": "262144"}, "file"),
    "webm": ("webm", "webm", {}, "file"),
    "webm_cl0": ("webm", "webm", {"cluster_size_limit": "0", "cluster_time_limit": "0"}, "file"),
    "fmp4_kf": ("mp4", "mp4", {"movflags": "frag_keyframe+empty_moov+default_base_moof"}, "file"),
    "fmp4_every": ("mp4", "mp4", {"movflags": "frag_every_frame+empty_moov+default_base_moof"}, "file"),
    "fmp4_1s": ("mp4", "mp4", {"movflags": "empty_moov+default_base_moof", "frag_duration": "1000000"}, "file"),
    "mp4": ("mp4", "mp4", {}, "file"),
    "seg_mkv": ("segment", "mkv", {"segment_format": "matroska", "segment_time": "1", "reset_timestamps": "0",
                                   "segment_list_type": "csv"}, "segment"),
    "seg_mp4": ("segment", "mp4", {"segment_format": "mp4", "segment_time": "1", "reset_timestamps": "0",
                                   "segment_list_type": "csv"}, "segment"),
    "nut": ("nut", "nut", {}, "file"),
    "avi": ("avi", "avi", {}, "file"),
    "ivf": ("ivf", "ivf", {}, "file"),
    "rawidx": (None, "mjpeg", {}, "rawidx"),
    "folder": (None, "jpg", {}, "folder"),
}

def spec(c: str):
    """Container spec; a '+fp' suffix adds the AVFormatContext option flush_packets=1 (avio_flush after every packet,
    instead of the file protocol's 256 KiB write buffer)."""
    if c.endswith("+fp"):
        fmt, ext, opts, kind = CONTAINERS[c[:-3]]
        return fmt, ext, {**opts, "flush_packets": "1"}, kind
    return CONTAINERS[c]


# which combos to attempt. Combos that a muxer refuses are still attempted where marked "try" so the refusal is evidence.
def combos() -> list[tuple[str, str]]:
    out = []
    for p in PAYLOADS:
        for c in CONTAINERS:
            if c in ("rawidx", "folder") and p != "mjpeg":
                continue
            if c in ("ivf",) and p != "av1":
                continue
            if c.startswith("webm") and p not in ("av1", "mjpeg"):  # mjpeg tried once to record the refusal
                continue
            if c == "webm_cl0" and p != "av1":
                continue
            out.append((p, c))
            if CONTAINERS[c][3] in ("file", "segment"):
                out.append((p, c + "+fp"))
    return out


def variant_id(p: str, c: str) -> str:
    return f"{p}__{c}"


def out_path(base_dir: Path, p: str, c: str, tag: str) -> Path:
    """File path (or directory for segment/folder/rawidx kinds) of one recording."""
    fmt, ext, opts, kind = spec(c)
    stem = f"{variant_id(p, c).replace('+', '_')}__{tag}"
    if kind == "file":
        return base_dir / f"{stem}.{ext}"
    return base_dir / stem  # directory


# ---------------------------------------------------------------------------------------------- raw .mjpeg + index format
IDX_REC = struct.Struct("<qQIIq")  # frame_number, offset, size, crc32(jpeg), capture_ns  (32 bytes)


def read_rawidx(d: Path) -> dict:
    """Recover a raw .mjpeg + .idx pair. Index records are trusted only if their CRC matches the data;
    without (or beyond) the index, frames are found by scanning SOI..EOI."""
    data = (d / "frames.mjpeg").read_bytes() if (d / "frames.mjpeg").exists() else b""
    idxb = (d / "frames.idx").read_bytes() if (d / "frames.idx").exists() else b""
    n_idx = len(idxb) // IDX_REC.size
    good_idx = 0
    end_good = 0
    for k in range(n_idx):
        fn, off, size, crc, ts = IDX_REC.unpack_from(idxb, k * IDX_REC.size)
        if off + size <= len(data) and zlib.crc32(data[off:off + size]) == crc and fn == k:
            good_idx += 1
            end_good = off + size
        else:
            break
    # scan the rest for complete JPEGs (SOI ... EOI). Camera JPEGs here are baseline with no embedded thumbnails.
    scanned = 0
    pos = end_good
    while True:
        s = data.find(b"\xff\xd8", pos)
        if s < 0:
            break
        e = data.find(b"\xff\xd9", s + 2)
        if e < 0:
            break
        scanned += 1
        pos = e + 2
    return {"index_records": n_idx, "index_records_crc_ok": good_idx, "extra_complete_jpegs_after_index": scanned,
            "frames_recoverable": good_idx + scanned, "partial_index_bytes": len(idxb) % IDX_REC.size}


# ---------------------------------------------------------------------------------------------- readers
def _run(cmd, timeout=300):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
    return r.returncode, r.stdout, r.stderr


def ffprobe_count(path: str, fmt: str | None = None) -> dict:
    cmd = ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
           "-show_entries", "stream=nb_read_frames,nb_frames,duration:format=duration,format_name", "-of", "json"]
    if fmt:
        cmd += ["-f", fmt]
    cmd.append(path)
    try:
        rc, out, err = _run(cmd)
    except subprocess.TimeoutExpired:
        return {"rc": "timeout", "frames": 0}
    res = {"rc": rc, "stderr": err.strip()[:300]}
    try:
        j = json.loads(out) if out.strip() else {}
        st = (j.get("streams") or [{}])[0]
        res["frames"] = int(st.get("nb_read_frames", 0) or 0)
        res["stream_duration"] = st.get("duration")
        res["format_duration"] = (j.get("format") or {}).get("duration")
        res["header_nb_frames"] = st.get("nb_frames")
    except Exception as e:  # noqa
        res["frames"] = 0
        res["parse_error"] = repr(e)[:200]
    return res


def ffprobe_packets(path: str, fmt: str | None = None) -> list[dict]:
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pos,size,pts,flags", "-of", "json"]
    if fmt:
        cmd += ["-f", fmt]
    cmd.append(path)
    rc, out, err = _run(cmd)
    try:
        return json.loads(out).get("packets", [])
    except Exception:
        return []


def pyav_read(path: str, fmt: str | None = None, ref_shas: list[str] | None = None, seek_test: bool = True) -> dict:
    """Decode every frame until EOF or the first exception. For MJPEG also count packets byte-identical to the
    camera's JPEG at the same index."""
    import av
    res = {"frames": 0, "packets": 0, "byte_exact": None, "error": None}
    pts_list = []
    try:
        with av.open(path, format=fmt, options={}) as c:
            st = c.streams.video[0]
            res["container_duration_s"] = (c.duration / 1e6) if c.duration else None
            res["stream_frames_header"] = st.frames
            res["stream_duration_s"] = float(st.duration * st.time_base) if st.duration and st.time_base else None
            exact = 0
            for pkt in c.demux(st):
                if pkt.size == 0:
                    for fr in pkt.decode():
                        res["frames"] += 1
                    continue
                if ref_shas is not None:
                    i = res["packets"]
                    if i < len(ref_shas) and sha(bytes(pkt)) == ref_shas[i]:
                        exact += 1
                res["packets"] += 1
                for fr in pkt.decode():
                    res["frames"] += 1
                    pts_list.append(fr.pts)
            if ref_shas is not None:
                res["byte_exact"] = exact
    except Exception as e:
        res["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    if seek_test and len(pts_list) >= 4:
        res["seek"] = pyav_seek(path, fmt, pts_list)
    return res


def pyav_seek(path: str, fmt: str | None, pts_list: list) -> dict:
    """Seek to the middle decoded frame (backward to keyframe) and decode one frame. ok = a frame at or before the
    target and no exception; exact = that frame IS the target (true for intra-only payloads)."""
    import av
    tgt = sorted(p for p in pts_list if p is not None)[len(pts_list) // 2]
    try:
        with av.open(path, format=fmt) as c:
            st = c.streams.video[0]
            c.seek(int(tgt), stream=st, backward=True, any_frame=False)
            for fr in c.decode(st):
                return {"ok": fr.pts is not None and fr.pts <= tgt, "target_pts": int(tgt), "got_pts": fr.pts,
                        "exact": fr.pts == tgt}
            return {"ok": False, "target_pts": int(tgt), "got_pts": None}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}


def cv2_read(path: str) -> dict:
    import cv2
    res = {"frames": 0}
    cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG)
    res["opened"] = bool(cap.isOpened())
    if not res["opened"]:
        return res
    res["prop_frame_count"] = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    while True:
        ok, _ = cap.read()
        if not ok:
            break
        res["frames"] += 1
    cap.release()
    if res["frames"] >= 4:
        cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG)
        tgt = res["frames"] // 2
        okset = cap.set(cv2.CAP_PROP_POS_FRAMES, tgt)
        ok, _ = cap.read()
        res["seek"] = {"set_ok": bool(okset), "read_ok": bool(ok), "target": tgt,
                       "pos_after": cap.get(cv2.CAP_PROP_POS_FRAMES)}
        cap.release()
    return res


def remux_ffmpeg(src: str, dst: str, fmt_in: str | None = None) -> dict:
    """Repair = -c copy remux into a finalized file. Output container from dst extension."""
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if fmt_in:
        cmd += ["-f", fmt_in]
    cmd += ["-i", src, "-map", "0:v:0", "-c", "copy", dst]
    try:
        rc, out, err = _run(cmd)
    except subprocess.TimeoutExpired:
        return {"rc": "timeout"}
    return {"rc": rc, "stderr": err.strip()[:300], "bytes": os.path.getsize(dst) if os.path.exists(dst) else 0}


def remux_pyav(src: str, dst: str, fmt_in: str | None = None) -> dict:
    """PyAV -c copy remux that stops at the first demux error (the Python-side repair)."""
    import av
    n = 0
    err = None
    try:
        with av.open(src, format=fmt_in) as ic, av.open(dst, "w") as oc:
            ist = ic.streams.video[0]
            ost = oc.add_stream_from_template(ist, opaque=True)  # opaque: AV1 template (decoder libdav1d) fails otherwise
            try:
                for pkt in ic.demux(ist):
                    if pkt.dts is None and pkt.pts is None:
                        continue
                    if pkt.size == 0:
                        continue
                    pkt.stream = ost
                    oc.mux(pkt)
                    n += 1
            except Exception as e:
                err = f"{type(e).__name__}: {str(e)[:160]}"
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:160]}"
    return {"packets": n, "error": err, "bytes": os.path.getsize(dst) if os.path.exists(dst) else 0}


# ---------------------------------------------------------------------------------------------- multi-file kinds
def segment_files(d: Path, ext: str) -> list[Path]:
    return sorted(d.glob(f"seg_*.{ext}"))


def folder_files(d: Path) -> list[Path]:
    return sorted(d.glob("frame_*.jpg"))


def read_any(target: Path, c: str, ref_shas: list[str] | None, seek_test: bool = True) -> dict:
    """Run all three readers against one recording of container kind c. Multi-file kinds are summed per file."""
    fmt, ext, opts, kind = spec(c)
    if kind == "file":
        p = str(target)
        if not target.exists():
            return {"ffprobe": {"frames": 0}, "pyav": {"frames": 0, "error": "missing"}, "cv2": {"frames": 0}}
        return {"ffprobe": ffprobe_count(p), "pyav": pyav_read(p, None, ref_shas, seek_test), "cv2": cv2_read(p)}
    if kind == "segment":
        files = segment_files(target, ext)
        agg = {"ffprobe": {"frames": 0, "per_file": []}, "pyav": {"frames": 0, "byte_exact": 0 if ref_shas else None,
               "per_file": []}, "cv2": {"frames": 0, "per_file": []}, "n_files": len(files)}
        offset = 0
        for f in files:
            fp = ffprobe_count(str(f))
            pa = pyav_read(str(f), None, ref_shas[offset:] if ref_shas else None, seek_test=False)
            cv = cv2_read(str(f))
            agg["ffprobe"]["frames"] += fp["frames"]
            agg["ffprobe"]["per_file"].append(fp["frames"])
            agg["pyav"]["frames"] += pa["frames"]
            agg["pyav"]["per_file"].append(pa["frames"] if not pa["error"] else f"{pa['frames']} ({pa['error'][:60]})")
            if ref_shas and pa.get("byte_exact") is not None:
                agg["pyav"]["byte_exact"] += pa["byte_exact"]
            agg["cv2"]["frames"] += cv["frames"]
            agg["cv2"]["per_file"].append(cv["frames"])
            offset += pa["packets"]
        lst = target / "list.csv"
        agg["segment_list_lines"] = len(lst.read_text().splitlines()) if lst.exists() else None
        return agg
    if kind == "rawidx":
        rr = read_rawidx(target)
        p = str(target / "frames.mjpeg")
        out = {"rawidx_parser": rr}
        if os.path.exists(p) and os.path.getsize(p) > 0:
            out["ffprobe"] = ffprobe_count(p, "mjpeg")
            out["pyav"] = pyav_read(p, "mjpeg", ref_shas, seek_test)
            out["cv2"] = cv2_read(p)
        else:
            out.update({"ffprobe": {"frames": 0}, "pyav": {"frames": 0}, "cv2": {"frames": 0}})
        return out
    if kind == "folder":
        import cv2
        import numpy as np
        files = folder_files(target)
        complete = sum(1 for f in files if f.read_bytes()[-2:] == b"\xff\xd9")
        imread_ok = 0
        exact = 0
        for i, f in enumerate(files):
            b = f.read_bytes()
            if ref_shas and i < len(ref_shas) and sha(b) == ref_shas[i]:
                exact += 1
            im = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR) if b else None
            if im is not None:
                imread_ok += 1
        pat = str(target / "frame_%06d.jpg")
        return {"n_files": len(files), "files_ending_EOI": complete, "byte_exact": exact if ref_shas else None,
                "cv2_imdecode_ok": imread_ok,
                "ffprobe": ffprobe_count(pat, "image2") if files else {"frames": 0},
                "pyav": pyav_read(pat, "image2", None, seek_test=False) if files else {"frames": 0},
                "cv2": cv2_read(pat) if files else {"frames": 0}}
    raise ValueError(kind)


def summarize_read(r: dict) -> dict:
    """Flatten read_any() output to the numbers the tables use."""
    s = {"ffprobe": r.get("ffprobe", {}).get("frames", 0), "pyav": r.get("pyav", {}).get("frames", 0),
         "cv2": r.get("cv2", {}).get("frames", 0), "pyav_err": (r.get("pyav", {}).get("error") or "")[:80],
         "byte_exact": r.get("pyav", {}).get("byte_exact", r.get("byte_exact"))}
    if "rawidx_parser" in r:
        s["rawidx"] = r["rawidx_parser"]["frames_recoverable"]
    if "files_ending_EOI" in r:
        s["folder_complete"] = r["files_ending_EOI"]
        s["byte_exact"] = r.get("byte_exact")
    sk = r.get("pyav", {}).get("seek")
    s["pyav_seek"] = None if sk is None else bool(sk.get("ok"))
    ck = r.get("cv2", {}).get("seek")
    s["cv2_seek"] = None if ck is None else bool(ck.get("read_ok"))
    s["dur"] = r.get("ffprobe", {}).get("format_duration")
    return s


def rm(p: Path):
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    elif p.exists():
        p.unlink()


def nvidia_smi() -> str:
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu",
                               "--format=csv,noheader"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:  # noqa
        return f"nvidia-smi failed: {e!r}"


def env_versions() -> dict:
    import av
    import cv2
    ff = subprocess.run(["ffmpeg", "-hide_banner", "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    return {"python": sys.version.split()[0], "pyav": av.__version__, "libav": {k: ".".join(map(str, v)) for k, v in
            av.library_versions.items()}, "opencv": cv2.__version__, "ffmpeg_cli": ff}
