"""Shared pieces for the write_throughput topic (goal G5): corpus payloads, recording writers, readers.

Writers (all take already-compressed per-frame payloads; nothing is encoded here):
    files      one file per frame: open / write / close  (opts: fsync, subdir_every)
    append     one raw append file (.mjpeg / .ffv1raw), unbuffered write per frame (opts: fsync_every_s)
    mkv        PyAV packet passthrough into Matroska (opts: flush_packets, cluster_time_limit)
    fmp4       PyAV packet passthrough into fragmented MP4 (opts: frag = frame | 1s | hybrid)
    mkvseg     PyAV packet passthrough into a new Matroska file every segment_s seconds (manual rotation)
Every writer also appends a fixed 32-byte record per frame to a sidecar index (<camN>.idx), written
with one unbuffered write per frame so it survives a process kill:
    struct '<qqqq' = frame_index, tick_ns (producer clock), byte offset in the append file (-1 otherwise), size

Media paths: payload caches and recordings go under MEDIA (outside the repo; frames show the room).
"""
from __future__ import annotations

import io
import json
import os
import struct
import time
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
STUDY = REPO / "research/skellycam_recording/recording_upgrade"
RESULTS = STUDY / "results/write_throughput"
BENCH_RESULTS = RESULTS / "bench"
RAW = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109")
CORPUS = RAW / "corpus"
MEDIA = RAW / "write_throughput"

IDX_REC = struct.Struct("<qqqq")
US = Fraction(1, 1_000_000)

# Load profiles: (width, height, fps, [corpus sets assigned to cameras round-robin])
PROFILES = {
    "720p30": (1280, 720, 30, ["c930e_720p_flash", "c922_720p_flash"]),
    "720p60": (1280, 720, 60, ["c922_720p60"]),
    "1080p30": (1920, 1080, 30, ["c922_1080p", "c930e_1080p"]),
    # no 1080p60 capture exists in the corpus: the 1080p30 frames are sent at 60 fps
    "1080p60": (1920, 1080, 60, ["c922_1080p", "c930e_1080p"]),
}

WRITER_VARIANTS = {
    # name: (writer kind, opts)
    "files": ("files", {}),
    "files_subdirs": ("files", {"subdir_every": 1000}),
    "files_fsync": ("files", {"fsync": True}),
    "files_subdirs_fsync": ("files", {"fsync": True, "subdir_every": 1000}),
    "append": ("append", {}),
    "append_fsync1s": ("append", {"fsync_every_s": 1.0}),
    "mkv": ("mkv", {}),
    "mkv_flush": ("mkv", {"flush_packets": 1}),
    "mkv_flush_cluster1": ("mkv", {"flush_packets": 1, "cluster_size_limit": 1}),
    "fmp4_frame": ("fmp4", {"frag": "frame"}),
    "fmp4_1s": ("fmp4", {"frag": "1s"}),
    "fmp4_frame_flush": ("fmp4", {"frag": "frame", "flush_packets": 1}),
    "fmp4_1s_flush": ("fmp4", {"frag": "1s", "flush_packets": 1}),
    "fmp4_hybrid": ("fmp4", {"frag": "hybrid"}),
    "mkvseg10": ("mkvseg", {"segment_s": 10.0}),
}


# --------------------------------------------------------------------------------------------- payloads
def load_mjpeg_set(name: str, limit: int | None = None) -> list[bytes]:
    d = CORPUS / name
    files = sorted(d.glob("frame_*.jpg"))
    if limit:
        files = files[:limit]
    if not files:
        raise FileNotFoundError(f"no frames in {d}")
    return [f.read_bytes() for f in files]


def _ffv1_cache_paths(res: str):
    MEDIA.mkdir(parents=True, exist_ok=True)
    base = MEDIA / "payload_cache" / f"ffv1_{res}"
    base.parent.mkdir(parents=True, exist_ok=True)
    return base.with_suffix(".bin"), base.with_suffix(".json")


def build_ffv1_payload(res: str) -> dict:
    """FFV1 (version 3, intra only, yuv422p) packets made from the real YUY2 camera frames.

    1080p: the 2 x 8 YUY2 frames as captured (yuyv422 -> yuv422p, lossless repack).
    720p : the same frames scaled to 1280x720 by libswscale (PyAV VideoFrame.reformat, default bicubic).
    The encoder output is muxed into a template MKV (MEDIA/payload_cache/ffv1_<res>_template.mkv) and the
    payload packets are demuxed back from it. Passthrough writers create their stream with
    add_stream_from_template(<template stream>) so the FFV1 configuration record (extradata) is carried;
    PyAV 18 add_stream('ffv1') re-opens an encoder and writes ITS OWN extradata, which made the
    passthrough packets undecodable (functional finding, see NOTES.md).
    """
    import av
    import numpy as np

    binp, jsp = _ffv1_cache_paths(res)
    tmpl = binp.with_name(f"ffv1_{res}_template.mkv")
    if not (binp.exists() and jsp.exists() and tmpl.exists()):
        w, h = (1920, 1080) if res == "1080p" else (1280, 720)
        srcs = []
        for s in ("c930e_1080p_yuy2", "c922_1080p_yuy2"):
            srcs += sorted((CORPUS / s).glob("frame_*.yuy2"))
        with av.open(str(tmpl), "w", format="matroska") as oc:
            st = oc.add_stream("ffv1", rate=30)
            st.width, st.height, st.pix_fmt = w, h, "yuv422p"
            st.codec_context.options = {"level": "3", "slices": "16", "slicecrc": "1", "g": "1", "context": "0",
                                        "coder": "1"}
            for i, f in enumerate(srcs):
                a = np.frombuffer(f.read_bytes(), np.uint8).reshape(1080, 1920, 2)
                fr = av.VideoFrame.from_ndarray(a, format="yuyv422").reformat(width=w, height=h, format="yuv422p")
                fr.pts = i
                oc.mux(st.encode(fr))
            oc.mux(st.encode(None))
        pkts, _, err, _ = av_packets(tmpl)
        assert err is None and len(pkts) == len(srcs), err
        offs, o = [], 0
        for p in pkts:
            offs.append((o, len(p)))
            o += len(p)
        binp.write_bytes(b"".join(pkts))
        jsp.write_text(json.dumps(dict(packets=offs, w=w, h=h, pix_fmt="yuv422p", template=str(tmpl),
                                       source="corpus c930e_1080p_yuy2 + c922_1080p_yuy2", av=av.__version__)))
    meta = json.loads(jsp.read_text())
    blob = binp.read_bytes()
    pk = [blob[o:o + n] for o, n in meta["packets"]]
    return dict(packets=pk, template=str(tmpl), w=meta["w"], h=meta["h"], pix_fmt=meta["pix_fmt"], codec="ffv1")


def payload_for(profile: str, payload: str, cam: int, limit: int | None = None) -> dict:
    w, h, fps, sets = PROFILES[profile]
    if payload == "mjpeg":
        name = sets[cam % len(sets)]
        return dict(packets=load_mjpeg_set(name, limit), template=None, w=w, h=h, pix_fmt="yuvj422p",
                    codec="mjpeg", source=name)
    if payload == "ffv1":
        p = build_ffv1_payload("1080p" if h == 1080 else "720p")
        p["source"] = "ffv1 from yuy2 corpus"
        return p
    raise ValueError(payload)


# --------------------------------------------------------------------------------------------- writers
class _Idx:
    def __init__(self, path: Path, enabled: bool = True):
        self.f = open(path, "wb", buffering=0) if enabled else None

    def add(self, fi: int, tick_ns: int, off: int, n: int):
        if self.f is not None:
            self.f.write(IDX_REC.pack(fi, tick_ns, off, n))

    def close(self):
        if self.f is not None:
            self.f.close()


class FilesWriter:
    def __init__(self, out: Path, cam: int, codec: str, w: int, h: int, fps: int, fsync=False, subdir_every=0,
                 sidecar=True, **_):
        self.dir = out / f"cam{cam:02d}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ext = ".jpg" if codec == "mjpeg" else f".{codec}"
        self.fsync, self.sub = fsync, subdir_every
        self._made = set()
        self.idx = _Idx(out / f"cam{cam:02d}.idx", sidecar)
        self.bytes = 0
        self.files = 0

    def write(self, fi: int, data, tick_ns: int):
        d = self.dir
        if self.sub:
            k = fi // self.sub
            d = self.dir / f"{k:04d}"
            if k not in self._made:
                d.mkdir(exist_ok=True)
                self._made.add(k)
        with open(d / f"frame_{fi:06d}{self.ext}", "wb", buffering=0) as f:
            f.write(data)
            if self.fsync:
                os.fsync(f.fileno())
        self.idx.add(fi, tick_ns, -1, len(data))
        self.bytes += len(data)
        self.files += 1

    def close(self):
        self.idx.close()
        return dict(bytes=self.bytes, files=self.files + (1 if self.idx.f else 0) + len(self._made))


class AppendWriter:
    def __init__(self, out: Path, cam: int, codec: str, w: int, h: int, fps: int, fsync_every_s=0.0, sidecar=True,
                 **_):
        out.mkdir(parents=True, exist_ok=True)
        ext = ".mjpeg" if codec == "mjpeg" else f".{codec}raw"
        self.f = open(out / f"cam{cam:02d}{ext}", "wb", buffering=0)
        self.idx = _Idx(out / f"cam{cam:02d}.idx", True)  # the index is the only frame table: always on
        self.every = fsync_every_s
        self.last_sync = time.perf_counter()
        self.off = 0
        self.fsyncs = 0

    def write(self, fi: int, data, tick_ns: int):
        n = len(data)
        self.f.write(data)
        self.idx.add(fi, tick_ns, self.off, n)
        self.off += n
        if self.every:
            t = time.perf_counter()
            if t - self.last_sync >= self.every:
                os.fsync(self.f.fileno())
                os.fsync(self.idx.f.fileno())
                self.last_sync = t
                self.fsyncs += 1

    def close(self):
        if self.every:
            os.fsync(self.f.fileno())
        self.f.close()
        self.idx.close()
        return dict(bytes=self.off, files=2, fsyncs=self.fsyncs)


def _open_av(path: Path, fmt: str, codec: str, w: int, h: int, fps: int, template: str | None, options: dict):
    """Output container + a stream with no encoder attached (pure packet passthrough).

    MJPEG: add_mux_stream (codec parameters only; the JPEG carries its own tables).
    FFV1 : add_stream_from_template from the payload's template MKV (carries the extradata).
    """
    import av
    c = av.open(str(path), "w", format=fmt, options={k: str(v) for k, v in options.items()})
    if template:
        ic = av.open(template)
        st = c.add_stream_from_template(ic.streams.video[0])
        ic.close()
    else:
        st = c.add_mux_stream(codec, rate=fps, width=w, height=h)
    return c, st


class AVWriter:
    """Packet passthrough via PyAV. Timestamps: pts = (tick_ns - first_tick_ns) in the stream time base."""

    def __init__(self, out: Path, cam: int, codec: str, w: int, h: int, fps: int, kind="mkv", frag="1s",
                 flush_packets=None, cluster_time_limit=None, cluster_size_limit=None, segment_s=0.0, template=None, sidecar=True, **_):
        out.mkdir(parents=True, exist_ok=True)
        self.out, self.cam, self.codec, self.w, self.h, self.fps = out, cam, codec, w, h, fps
        self.template = template
        self.kind = kind
        self.opts = {}
        if kind in ("mkv", "mkvseg"):
            self.fmt, self.ext = "matroska", ".mkv"
            if flush_packets is not None:
                self.opts["flush_packets"] = flush_packets
            if cluster_time_limit is not None:
                self.opts["cluster_time_limit"] = cluster_time_limit
            if cluster_size_limit is not None:
                self.opts["cluster_size_limit"] = cluster_size_limit
        elif kind == "fmp4":
            self.fmt, self.ext = "mp4", ".mp4"
            self.opts["video_track_timescale"] = 90000
            if frag == "frame":
                self.opts["movflags"] = "frag_keyframe+empty_moov+default_base_moof"
            elif frag == "1s":
                self.opts["movflags"] = "empty_moov+default_base_moof"
                self.opts["frag_duration"] = 1_000_000
            elif frag == "hybrid":
                self.opts["movflags"] = "hybrid_fragmented"
            else:
                raise ValueError(frag)
            if flush_packets is not None:
                self.opts["flush_packets"] = flush_packets
        else:
            raise ValueError(kind)
        self.segment_ns = int(segment_s * 1e9) if kind == "mkvseg" else 0
        self.seg = 0
        self.seg_start = None
        self.first = None
        self.idx = _Idx(out / f"cam{cam:02d}.idx", sidecar)
        self.bytes = 0
        self.files = 0
        self.c = None
        self._open()

    def _open(self):
        name = f"cam{self.cam:02d}" + (f"_seg{self.seg:04d}" if self.kind == "mkvseg" else "") + self.ext
        self.c, self.st = _open_av(self.out / name, self.fmt, self.codec, self.w, self.h, self.fps, self.template,
                                   self.opts)
        self.files += 1

    def write(self, fi: int, data, tick_ns: int):
        import av
        if self.first is None:
            self.first = tick_ns
            self.seg_start = tick_ns
        if self.segment_ns and tick_ns - self.seg_start >= self.segment_ns:
            self.c.close()
            self.seg += 1
            self.seg_start = tick_ns
            self._open()
        pkt = av.Packet(data)
        pkt.stream = self.st
        # packet clock = microseconds; PyAV rescales to the muxer's stream time base when muxing
        pkt.time_base = US
        pkt.pts = pkt.dts = (tick_ns - self.first) // 1000
        pkt.is_keyframe = True
        self.c.mux(pkt)
        self.idx.add(fi, tick_ns, -1, len(data))
        self.bytes += len(data)

    def close(self):
        self.c.close()
        self.idx.close()
        return dict(bytes=self.bytes, files=self.files + (1 if self.idx.f else 0))


def make_writer(variant: str, out: Path, cam: int, payload: dict, fps: int, sidecar=True):
    kind, opts = WRITER_VARIANTS[variant]
    common = dict(codec=payload["codec"], w=payload["w"], h=payload["h"], fps=fps, sidecar=sidecar)
    if kind == "files":
        return FilesWriter(out, cam, **common, **opts)
    if kind == "append":
        return AppendWriter(out, cam, **common, **opts)
    return AVWriter(out, cam, kind=kind, template=payload.get("template"), **common, **opts)


# --------------------------------------------------------------------------------------------- readers
def read_idx(path: Path) -> list[tuple]:
    b = path.read_bytes()
    n = len(b) // IDX_REC.size  # a torn last record is ignored
    return [IDX_REC.unpack_from(b, i * IDX_REC.size) for i in range(n)]


def av_packets(path: Path, max_packets: int | None = None) -> tuple[list[bytes], list[int], str | None, object]:
    """Demux all packets of stream 0: (payloads, pts, error or None, time_base)."""
    import av
    out, pts, err, tb = [], [], None, None
    try:
        with av.open(str(path)) as c:
            st = c.streams.video[0]
            tb = st.time_base
            for p in c.demux(st):
                if p.size == 0:
                    continue
                out.append(bytes(p))
                pts.append(p.pts)
                if max_packets and len(out) >= max_packets:
                    break
    except Exception as e:  # noqa: BLE001 - we record the error text as a functional result
        err = f"{type(e).__name__}: {e}"
    return out, pts, err, tb


def env_versions() -> dict:
    import platform
    import sys
    d = dict(python=sys.version.split()[0], platform=platform.platform(), machine=platform.node())
    try:
        import av
        d["av"] = av.__version__
        d["libavformat"] = av.library_versions.get("libavformat")
        d["libavcodec"] = av.library_versions.get("libavcodec")
    except Exception as e:  # noqa: BLE001
        d["av"] = repr(e)
    for m in ("numpy", "cv2", "psutil"):
        try:
            d[m] = __import__(m).__version__
        except Exception:  # noqa: BLE001
            d[m] = None
    return d


def pct(a, qs=(50, 99, 99.9, 100)):
    import numpy as np
    if len(a) == 0:
        return {f"p{q}": None for q in qs}
    v = np.percentile(np.asarray(a, dtype=np.float64), qs)
    return {("max" if q == 100 else f"p{q}"): float(x) for q, x in zip(qs, v)}
