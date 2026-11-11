"""Prototype: a resumable, crash-tolerant per-camera recorder (goal G2). Python + PyAV only.

'Resumable' here means:
  1. Whatever was written before a crash stays playable without a repair step by common readers (each segment is a
     Matroska file written with flush_packets=1, so at most the open cluster - one frame for intra payloads - is lost
     on a process kill).
  2. On restart, the recorder detects the unfinished session from its journal, repairs only the last (open) segment by
     a -c copy remux of its readable packets, reconciles the timestamp sidecar with what the video really holds, and
     records which frame numbers were lost.
  3. Recording then continues in a NEW segment of the same session with continuous frame numbers and timestamps on the
     same session clock (pts = capture time - session t0, in ms), so the crash shows up as a time gap, not as a
     renumbering.

On-disk layout of one camera's session directory:
  manifest.jsonl   append-only journal, one JSON object per line, flushed + fsynced at segment boundaries
                   {"type":"session","t0_ns":...,"payload":...,"width":..,"height":..}
                   {"type":"segment_open","seg":k,"file":"seg_0000k.mkv","first_frame":F}
                   {"type":"segment_closed","seg":k,"frames":n,"last_frame":L,"recovered":bool}
                   {"type":"resume","lost_frames":[...],"next_frame":F}
                   {"type":"session_closed","frames":N}
  seg_00000.mkv    MJPEG passthrough (camera JPEG bytes, byte-exact) or FFV1, Matroska, flush_packets=1
  timestamps.bin   32-byte records <q frame_number, q capture_ns, i seg, I crc32(of the first 20 bytes), q reserved>,
                   appended and flushed per frame (fsync policy configurable)
"""
from __future__ import annotations

import json
import os
import struct
import zlib
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av

TS_REC = struct.Struct("<qqiIq")


def _ts_pack(fn: int, ns: int, seg: int) -> bytes:
    head = struct.pack("<qqi", fn, ns, seg)
    return TS_REC.pack(fn, ns, seg, zlib.crc32(head), 0)


def read_timestamps(path: Path) -> list[tuple[int, int, int]]:
    """Valid records up to the first torn / zero-filled / CRC-failing one."""
    out = []
    if not path.exists():
        return out
    b = path.read_bytes()
    for k in range(len(b) // TS_REC.size):
        fn, ns, seg, crc, _ = TS_REC.unpack_from(b, k * TS_REC.size)
        if zlib.crc32(struct.pack("<qqi", fn, ns, seg)) != crc:
            break
        out.append((fn, ns, seg))
    return out


def read_manifest(path: Path) -> list[dict]:
    """Parsed journal lines; a torn last line (crash mid-write) is ignored."""
    recs = []
    if not path.exists():
        return recs
    for line in path.read_bytes().split(b"\n"):
        if not line.strip():
            continue
        try:
            recs.append(json.loads(line))
        except Exception:
            break
    return recs


@dataclass
class RecoveryReport:
    was_incomplete: bool
    repaired_segment: str | None
    frames_in_repaired_segment: int
    timestamps_valid: int
    timestamps_dropped: int
    lost_frames: list[int]
    next_frame: int


class ResumableRecorder:
    def __init__(self, session_dir: Path, payload: str = "mjpeg", width: int = 1280, height: int = 720,
                 segment_seconds: float = 60.0, fsync_every: int = 0):
        self.dir = Path(session_dir)
        self.payload = payload
        self.w, self.h = width, height
        self.segment_ns = int(segment_seconds * 1e9)
        self.fsync_every = fsync_every  # 0 = flush only (survives process kill, not power loss)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.mpath = self.dir / "manifest.jsonl"
        self.tpath = self.dir / "timestamps.bin"
        self.report: RecoveryReport | None = None
        self._open_or_resume()

    # ------------------------------------------------------------------------------------------------ journal
    def _journal(self, rec: dict, sync: bool = True):
        with open(self.mpath, "ab") as f:
            f.write((json.dumps(rec) + "\n").encode())
            f.flush()
            if sync:
                os.fsync(f.fileno())

    # ------------------------------------------------------------------------------------------------ recovery
    def _open_or_resume(self):
        recs = read_manifest(self.mpath)
        self.container = None
        self.stream = None
        self.seg = -1
        self.seg_frames = 0
        if not recs:
            self.t0_ns = None
            self.next_frame = 0
            self.report = RecoveryReport(False, None, 0, 0, 0, [], 0)
        else:
            sess = recs[0]
            assert sess["type"] == "session"
            self.t0_ns = sess["t0_ns"]
            self.payload = sess["payload"]
            self.w, self.h = sess["width"], sess["height"]
            if recs[-1]["type"] == "session_closed":
                raise RuntimeError("session already closed; start a new session directory")
            # drop a torn last journal line so new records start on a clean line
            raw = self.mpath.read_bytes()
            good = 0
            for line in raw.split(b"\n")[:len(recs)]:
                good += len(line) + 1
            good = min(good, len(raw))
            if good < len(raw):
                with open(self.mpath, "r+b") as f:
                    f.truncate(good)
            if not self.mpath.read_bytes().endswith(b"\n"):
                with open(self.mpath, "ab") as f:
                    f.write(b"\n")
            self.report = self._recover(recs)
            self.next_frame = self.report.next_frame
            # never reuse a segment index that exists in the journal OR on disk
            on_disk = [int(f.stem.split("_")[1]) for f in self.dir.glob("seg_*.mkv") if f.stem.split("_")[1].isdigit()]
            self.seg = max([r["seg"] for r in read_manifest(self.mpath) if r["type"] == "segment_open"] + on_disk + [-1])
        self.tfile = open(self.tpath, "ab")
        self._since_sync = 0

    def _recover(self, recs: list[dict]) -> RecoveryReport:
        opened = {r["seg"]: r for r in recs if r["type"] == "segment_open"}
        closed = {r["seg"]: r for r in recs if r["type"] == "segment_closed"}
        ts_all = read_timestamps(self.tpath)
        # orphan segment files (their segment_open line was lost, e.g. torn by a power cut): adopt them. Their first
        # frame number comes from the sidecar (each record carries its segment index), else follows the previous one.
        for f in sorted(self.dir.glob("seg_*.mkv")):
            try:
                k = int(f.stem.split("_")[1])
            except ValueError:
                continue
            if k in opened:
                continue
            fr = [t[0] for t in ts_all if t[2] == k]
            prev_last = max([c["last_frame"] for c in closed.values()] + [-1])
            first = min(fr) if fr else prev_last + 1
            opened[k] = {"type": "segment_open", "seg": k, "file": f.name, "first_frame": first, "adopted": True}
            self._journal(opened[k])
        open_segs = sorted(set(opened) - set(closed))
        repaired = None
        n_rep = 0
        frames_in_video: list[int] = []
        # frame numbers present in closed segments come from the journal
        for k, c in sorted(closed.items()):
            frames_in_video += list(range(opened[k]["first_frame"], c["last_frame"] + 1)) if c["frames"] else []
        for k in open_segs:
            seg_path = self.dir / opened[k]["file"]
            n_rep = self._repair_segment(seg_path)
            first = opened[k]["first_frame"]
            frames_in_video += list(range(first, first + n_rep))
            repaired = seg_path.name
            self._journal({"type": "segment_closed", "seg": k, "frames": n_rep,
                           "last_frame": first + n_rep - 1, "recovered": True})
        # reconcile the timestamp sidecar: keep only valid records whose frame is really in the video
        ts = ts_all
        in_video = set(frames_in_video)
        keep = [t for t in ts if t[0] in in_video]
        dropped = [t[0] for t in ts if t[0] not in in_video]
        raw_records = (self.tpath.stat().st_size // TS_REC.size) if self.tpath.exists() else 0
        with open(self.tpath, "wb") as f:
            for fn, ns, sg in keep:
                f.write(_ts_pack(fn, ns, sg))
            f.flush()
            os.fsync(f.fileno())
        have_ts = {t[0] for t in keep}
        lost = sorted(set(dropped) | {fn for fn in in_video if fn not in have_ts})  # frames lacking either half
        next_frame = (max([t[0] for t in ts] + frames_in_video) + 1) if (ts or frames_in_video) else 0
        rep = RecoveryReport(True, repaired, n_rep, len(keep), raw_records - len(keep), lost, next_frame)
        self._journal({"type": "resume", "lost_frames": lost, "next_frame": next_frame,
                       "timestamps_dropped": raw_records - len(keep)})
        return rep

    def _repair_segment(self, seg_path: Path) -> int:
        """-c copy the readable packets of an unfinished segment into a finalized file and swap it in."""
        if not seg_path.exists() or seg_path.stat().st_size == 0:
            if seg_path.exists():
                seg_path.unlink()
            return 0
        tmp = seg_path.with_suffix(".repair.mkv")
        n = 0
        try:
            with av.open(str(seg_path)) as ic:
                ist = ic.streams.video[0]
                with av.open(str(tmp), "w", format="matroska") as oc:
                    ost = oc.add_stream_from_template(ist, opaque=True)  # opaque: AV1 template (decoder libdav1d) fails otherwise
                    try:
                        for pkt in ic.demux(ist):
                            if pkt.size == 0 or pkt.pts is None:
                                continue
                            if self.payload == "mjpeg":
                                b = bytes(pkt)
                                if not (b[:2] == b"\xff\xd8" and b[-2:] == b"\xff\xd9"):
                                    break  # torn last JPEG
                            pkt.stream = ost
                            oc.mux(pkt)
                            n += 1
                    except (av.error.InvalidDataError, av.error.EOFError):
                        pass
        except (av.error.InvalidDataError, av.error.EOFError):
            n = 0  # header itself is gone
        if n == 0:
            tmp.unlink(missing_ok=True)
            seg_path.unlink()
            return 0
        crashed = seg_path.with_suffix(".crashed.mkv")
        os.replace(seg_path, crashed)
        os.replace(tmp, seg_path)
        crashed.unlink()
        return n

    # ------------------------------------------------------------------------------------------------ writing
    def _open_segment(self, first_frame: int, capture_ns: int):
        self.seg += 1
        name = f"seg_{self.seg:05d}.mkv"
        self._journal({"type": "segment_open", "seg": self.seg, "file": name, "first_frame": first_frame,
                       "first_capture_ns": capture_ns})
        self.container = av.open(str(self.dir / name), "w", format="matroska", options={"flush_packets": "1"})
        if self.payload == "mjpeg":
            st = self.container.add_stream("mjpeg", rate=30)
            st.pix_fmt = "yuvj422p"
        else:
            st = self.container.add_stream("ffv1", rate=30)
            st.pix_fmt = "yuv422p"
            st.codec_context.gop_size = 1
            st.options = {"level": "3", "slicecrc": "1", "slices": "4"}
            st.codec_context.time_base = Fraction(1, 1000)
        st.width, st.height = self.w, self.h
        self.stream = st
        self.seg_first_frame = first_frame
        self.seg_first_ns = capture_ns
        self.seg_frames = 0

    def _close_segment(self):
        if self.container is None:
            return
        if self.payload != "mjpeg":
            for p in self.stream.encode(None):
                self.container.mux(p)
        self.container.close()
        self._journal({"type": "segment_closed", "seg": self.seg, "frames": self.seg_frames,
                       "last_frame": self.seg_first_frame + self.seg_frames - 1, "recovered": False})
        self.container = None

    def write(self, data, capture_ns: int) -> int:
        """data: JPEG bytes (mjpeg) or an av.VideoFrame (ffv1). Returns the frame number assigned."""
        if self.t0_ns is None:
            self.t0_ns = capture_ns
            self._journal({"type": "session", "t0_ns": capture_ns, "payload": self.payload, "width": self.w,
                           "height": self.h, "pts_unit": "ms since t0_ns"})
        if self.container is None or capture_ns - self.seg_first_ns >= self.segment_ns:
            self._close_segment()
            self._open_segment(self.next_frame, capture_ns)
        fn = self.next_frame
        pts_ms = (capture_ns - self.t0_ns) // 1_000_000
        if self.payload == "mjpeg":
            pkt = av.Packet(data)
            pkt.stream = self.stream
            pkt.time_base = Fraction(1, 1000)
            pkt.pts = pkt.dts = pts_ms
            pkt.is_keyframe = True
            self.container.mux(pkt)
        else:
            data.pts = pts_ms
            data.time_base = Fraction(1, 1000)
            for p in self.stream.encode(data):
                self.container.mux(p)
        self.tfile.write(_ts_pack(fn, capture_ns, self.seg))
        self.tfile.flush()
        self._since_sync += 1
        if self.fsync_every and self._since_sync >= self.fsync_every:
            os.fsync(self.tfile.fileno())
            self._since_sync = 0
        self.next_frame += 1
        self.seg_frames += 1
        return fn

    def close(self):
        self._close_segment()
        self.tfile.flush()
        os.fsync(self.tfile.fileno())
        self.tfile.close()
        self._journal({"type": "session_closed", "frames": self.next_frame})


def join_session(session_dir: Path, out_path: Path) -> dict:
    """Finalize a session for single-file playback: -c copy every segment, in order, into one MKV keeping the
    session-clock pts (crash gaps stay visible as time gaps)."""
    session_dir = Path(session_dir)
    recs = read_manifest(session_dir / "manifest.jsonl")
    segs = [r["file"] for r in recs if r["type"] == "segment_open" and (session_dir / r["file"]).exists()]
    n = 0
    last = -1
    mono = True
    with av.open(str(out_path), "w", format="matroska") as oc:
        ost = None
        for s in segs:
            with av.open(str(session_dir / s)) as ic:
                ist = ic.streams.video[0]
                if ost is None:
                    ost = oc.add_stream_from_template(ist, opaque=True)  # opaque: AV1 template (decoder libdav1d) fails otherwise
                for pkt in ic.demux(ist):
                    if pkt.size == 0 or pkt.pts is None:
                        continue
                    if pkt.pts <= last:
                        mono = False
                    last = pkt.pts
                    pkt.stream = ost
                    oc.mux(pkt)
                    n += 1
    return {"segments": len(segs), "packets": n, "pts_monotonic": mono}
