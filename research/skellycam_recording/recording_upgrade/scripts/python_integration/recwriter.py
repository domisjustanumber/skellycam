"""Prototype RecordingWriter / RecordingReader for skellycam (python_integration topic, 2026-11-09).

Goal (G1, G2, G9): store each camera's own JPEG bytes without transcoding, with real per-frame
presentation times, in a container that stays readable after a crash, plus a per-frame sidecar
that holds the exact nanosecond timestamps (containers round them).

Files written for stem S:
    S.mkv | S.mp4 | S.avi     the JPEG packets, unmodified, PTS = timestamp - t0 in the container time base
    S.frames.bin              fixed 64-byte header + one 48-byte record per frame, appended and flushed per frame
                              (record CRC32 detects a torn last record after a crash)
    S.frames.csv              the same data as text, appended and flushed per frame
    S.recording.json          manifest; state "recording" while open, "closed" after close(), "recovered" after recover()

Only stdlib + numpy + PyAV. Tested with the skellycam venv (PyAV 18.0.0). Not skellycam code.
"""
from __future__ import annotations

import json
import os
import queue
import struct
import threading
import time
import zlib
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

MAGIC = b"SKCAMFR1"
HEADER_FMT = "<8sIIII4sIIq20x"  # magic, version, header_size, width, height, codec fourcc, tb_num, tb_den, t0_ns, pad
HEADER_SIZE = struct.calcsize(HEADER_FMT)
assert HEADER_SIZE == 64, HEADER_SIZE
RECORD_BODY_FMT = "<qqqIIIII"  # frame_number, timestamp_ns, pts, size, packet_crc32, flags, write_index, reserved
RECORD_FMT = RECORD_BODY_FMT + "I"  # + record_crc32 over the body
RECORD_SIZE = struct.calcsize(RECORD_FMT)
assert RECORD_SIZE == 48, RECORD_SIZE
RECORD_DTYPE = np.dtype([
    ("frame_number", "<i8"), ("timestamp_ns", "<i8"), ("pts", "<i8"), ("size", "<u4"),
    ("packet_crc32", "<u4"), ("flags", "<u4"), ("write_index", "<u4"), ("reserved", "<u4"), ("record_crc32", "<u4"),
])
assert RECORD_DTYPE.itemsize == RECORD_SIZE

FLAG_PTS_ADJUSTED = 1  # container PTS bumped by 1 tick to stay strictly increasing (timestamp_ns is still exact)
FLAG_FRAME_GAP = 2     # frame_number is not previous + 1 (a drop upstream); recorded, not an error

CONTAINERS = {
    # name: (ffmpeg format, extension, muxer options)
    "mkv": ("matroska", "mkv", {}),
    "mp4f": ("mp4", "mp4", {"movflags": "frag_keyframe+empty_moov+default_base_moof"}),
    "avi": ("avi", "avi", {}),
}
CSV_HEADER = "frame_number,timestamp_ns,pts,pts_time_base,size,packet_crc32,flags,write_index\n"


def _atomic_write_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1), encoding="utf-8")
    os.replace(tmp, path)


class RecordingWriter:
    """Write (jpeg_bytes, frame_number, timestamp_ns) packets for one camera. Not thread-safe; one owner thread."""

    def __init__(self, stem: str | Path, width: int, height: int, container: str = "mkv",
                 nominal_fps: int = 30, pix_fmt: str = "yuvj422p", fsync_every: int = 0,
                 time_base: Fraction = Fraction(1, 1_000_000), pts_mode: str = "real"):
        """pts_mode="real": PTS = timestamp - t0 (VFR, true timing in the file).
        pts_mode="index": PTS = write_index / nominal_fps (CFR file; exact timestamps live only in the sidecar)."""
        fmt, ext, opts = CONTAINERS[container]
        self.stem = Path(stem)
        self.stem.parent.mkdir(parents=True, exist_ok=True)
        self.video_path = self.stem.with_name(self.stem.name + f".{ext}")
        self.bin_path = self.stem.with_name(self.stem.name + ".frames.bin")
        self.csv_path = self.stem.with_name(self.stem.name + ".frames.csv")
        self.manifest_path = self.stem.with_name(self.stem.name + ".recording.json")
        for p in (self.video_path, self.bin_path, self.csv_path):
            if p.exists():
                raise FileExistsError(f"refusing to overwrite {p}")
        self.width, self.height, self.container_name = width, height, container
        if pts_mode not in ("real", "index"):
            raise ValueError(pts_mode)
        self.pts_mode, self.nominal_fps = pts_mode, nominal_fps
        if pts_mode == "index":
            time_base = Fraction(1, nominal_fps)
        self.fsync_every = fsync_every
        self._manifest = {"state": "recording", "container": container, "video": self.video_path.name,
                          "sidecar": self.bin_path.name, "csv": self.csv_path.name, "width": width,
                          "height": height, "codec": "mjpeg", "pid": os.getpid(), "pts_mode": pts_mode,
                          "started_unix_ns": time.time_ns(), "writer": "recwriter.py prototype v1"}
        _atomic_write_json(self.manifest_path, self._manifest)

        self._c = av.open(str(self.video_path), "w", format=fmt, options=opts)
        self._s = self._c.add_stream("mjpeg", rate=nominal_fps)
        self._s.width, self._s.height, self._s.pix_fmt = width, height, pix_fmt
        self._s.time_base = time_base
        self._c.start_encoding()          # writes the header; the muxer may replace the time base (MKV -> 1/1000)
        self.tb: Fraction = self._s.time_base
        self._bin = open(self.bin_path, "wb")
        self._csv = open(self.csv_path, "w", encoding="utf-8", newline="")
        self._csv.write(CSV_HEADER)
        self._t0_ns: int | None = None
        self._last_pts = -1
        self._last_fn: int | None = None
        self.count = 0
        self._manifest["time_base"] = f"{self.tb.numerator}/{self.tb.denominator}"
        _atomic_write_json(self.manifest_path, self._manifest)

    def _pts(self, timestamp_ns: int) -> int:
        # exact integer arithmetic: (t - t0) ns -> ticks of tb, rounded half up
        num = (timestamp_ns - self._t0_ns) * self.tb.denominator
        den = self.tb.numerator * 1_000_000_000
        return (2 * num + den) // (2 * den)

    def _pts_index(self, i: int) -> int:
        # i / nominal_fps seconds in ticks of the (muxer-chosen) time base
        num = i * self.tb.denominator
        den = self.nominal_fps * self.tb.numerator
        return (2 * num + den) // (2 * den)

    def write(self, jpeg_bytes: bytes, frame_number: int, timestamp_ns: int) -> int:
        if self._t0_ns is None:
            self._t0_ns = int(timestamp_ns)
            self._bin.write(struct.pack(HEADER_FMT, MAGIC, 1, HEADER_SIZE, self.width, self.height, b"MJPG",
                                        self.tb.numerator, self.tb.denominator, self._t0_ns))
            self._manifest["t0_ns"] = self._t0_ns
            _atomic_write_json(self.manifest_path, self._manifest)
        flags = 0
        if self.pts_mode == "index":
            pts = self._pts_index(self.count)
        else:
            pts = self._pts(int(timestamp_ns))
        if pts <= self._last_pts:
            pts, flags = self._last_pts + 1, flags | FLAG_PTS_ADJUSTED
        if self._last_fn is not None and frame_number != self._last_fn + 1:
            flags |= FLAG_FRAME_GAP
        pkt = av.Packet(jpeg_bytes)
        pkt.stream = self._s
        pkt.time_base = self.tb
        pkt.pts = pkt.dts = pts
        pkt.is_keyframe = True
        self._c.mux(pkt)  # PyAV releases the GIL around av_interleaved_write_frame
        crc = zlib.crc32(jpeg_bytes)
        body = struct.pack(RECORD_BODY_FMT, int(frame_number), int(timestamp_ns), pts, len(jpeg_bytes), crc, flags,
                           self.count, 0)
        self._bin.write(body + struct.pack("<I", zlib.crc32(body)))
        self._bin.flush()
        self._csv.write(f"{frame_number},{timestamp_ns},{pts},{self.tb.numerator}/{self.tb.denominator},"
                        f"{len(jpeg_bytes)},{crc},{flags},{self.count}\n")
        self._csv.flush()
        self.count += 1
        if self.fsync_every and self.count % self.fsync_every == 0:
            os.fsync(self._bin.fileno())
        self._last_pts, self._last_fn = pts, frame_number
        return pts

    def close(self) -> dict:
        self._c.close()  # writes Cues / moov-less fragments end / AVI index
        self._bin.close()
        self._csv.close()
        self._manifest.update(state="closed", frames=self.count, closed_unix_ns=time.time_ns())
        _atomic_write_json(self.manifest_path, self._manifest)
        return dict(self._manifest)


@dataclass
class SidecarData:
    header: dict
    records: np.ndarray        # RECORD_DTYPE, only records whose CRC checks
    torn_tail_bytes: int       # bytes after the last whole record (a crash mid-record)
    bad_crc_records: int       # whole-size records whose CRC failed (stops at the first)


def read_sidecar(path: str | Path) -> SidecarData:
    data = Path(path).read_bytes()
    if len(data) < HEADER_SIZE:
        return SidecarData({}, np.zeros(0, RECORD_DTYPE), len(data), 0)
    magic, ver, hs, w, h, fourcc, tbn, tbd, t0 = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    if magic != MAGIC:
        raise ValueError(f"bad sidecar magic {magic!r}")
    body = data[hs:]
    n = len(body) // RECORD_SIZE
    recs = np.frombuffer(body[: n * RECORD_SIZE], dtype=RECORD_DTYPE).copy()
    good = 0
    for i in range(n):
        raw = body[i * RECORD_SIZE: (i + 1) * RECORD_SIZE]
        if zlib.crc32(raw[:-4]) != struct.unpack("<I", raw[-4:])[0]:
            break
        good += 1
    hdr = {"version": ver, "width": w, "height": h, "fourcc": fourcc.decode(), "time_base": Fraction(tbn, tbd),
           "t0_ns": t0}
    return SidecarData(hdr, recs[:good], len(body) - n * RECORD_SIZE, n - good)


class RecordingReader:
    """Packet-level reader: yields (index, jpeg_bytes, pts) from the container, no decode."""

    def __init__(self, video_path: str | Path):
        self.video_path = Path(video_path)

    def packets(self):
        with av.open(str(self.video_path)) as c:
            s = c.streams.video[0]
            i = 0
            try:
                for p in c.demux(s):
                    if p.size == 0:
                        continue
                    yield i, bytes(p), p.pts, s.time_base
                    i += 1
            except (av.error.InvalidDataError, av.error.EOFError, OSError) as e:  # truncated tail
                self.last_error = repr(e)

    def decode_bgr(self, max_frames: int | None = None):
        """Decode with PyAV (libavcodec mjpeg) for the UI or analysis."""
        with av.open(str(self.video_path)) as c:
            for i, f in enumerate(c.decode(video=0)):
                if max_frames is not None and i >= max_frames:
                    break
                yield i, f.to_ndarray(format="bgr24")


def recover(stem: str | Path, remux: bool = True) -> dict:
    """Startup recovery for a stem whose manifest still says "recording".

    Reconciles the container packets with the sidecar records (by index, checking size and CRC), and
    optionally remuxes the good prefix into S.recovered.<ext> so the file gets a proper index/duration.
    """
    stem = Path(stem)
    man_path = stem.with_name(stem.name + ".recording.json")
    man = json.loads(man_path.read_text(encoding="utf-8"))
    video = stem.with_name(man["video"])
    side = read_sidecar(stem.with_name(man["sidecar"]))
    rdr = RecordingReader(video)
    pk = list(rdr.packets())
    n_match = 0
    first_mismatch = None
    for (i, b, pts, tb), r in zip(pk, side.records):
        if len(b) != int(r["size"]) or zlib.crc32(b) != int(r["packet_crc32"]) or pts != int(r["pts"]):
            first_mismatch = {"index": i, "packet_bytes": len(b), "sidecar_bytes": int(r["size"]),
                              "crc_equal": zlib.crc32(b) == int(r["packet_crc32"]), "pts": pts,
                              "sidecar_pts": int(r["pts"])}
            break
        n_match += 1
    report = {"stem": str(stem), "manifest_state": man.get("state"), "container_packets": len(pk),
              "sidecar_records": int(len(side.records)), "sidecar_torn_tail_bytes": side.torn_tail_bytes,
              "sidecar_bad_crc_records": side.bad_crc_records, "matched_prefix": n_match,
              "first_mismatch": first_mismatch,
              "reader_error": getattr(rdr, "last_error", None)}
    if remux and n_match:
        fmt, ext, opts = CONTAINERS[man["container"]]
        out = stem.with_name(stem.name + f".recovered.{ext}")
        if out.exists():
            out.unlink()
        with av.open(str(video)) as src, av.open(str(out), "w", format=fmt, options=opts) as dst:
            s_in = src.streams.video[0]
            s_out = dst.add_stream_from_template(s_in)
            k = 0
            try:
                for p in src.demux(s_in):
                    if p.size == 0:
                        continue
                    if k >= n_match:
                        break
                    p.stream = s_out
                    dst.mux(p)
                    k += 1
            except (av.error.InvalidDataError, av.error.EOFError, OSError):
                pass
        report["recovered_file"] = out.name
        report["recovered_packets"] = k
    man.update(state="recovered", recovered_unix_ns=time.time_ns(), recovery=report)
    _atomic_write_json(man_path, man)
    return report


def find_unfinished(folder: str | Path) -> list[Path]:
    """Scan a recording folder (recursively) for manifests left in state "recording"."""
    out = []
    for m in Path(folder).rglob("*.recording.json"):
        try:
            if json.loads(m.read_text(encoding="utf-8")).get("state") == "recording":
                out.append(m.with_name(m.name[: -len(".recording.json")]))
        except (OSError, json.JSONDecodeError):
            out.append(m.with_name(m.name[: -len(".recording.json")]))
    return out


class RecorderThread:
    """Keeps container writes out of the lockstep camera loop: the loop only enqueues a bytes reference.

    policy="drop": a full queue drops the frame and counts it (explicit, like the ring-buffer study's drop policy);
    policy="block": the loop waits (back-pressure; the ring-buffer study showed this stalls the sensor instead).
    """

    def __init__(self, writer: RecordingWriter, maxsize: int = 256, policy: str = "drop"):
        self.writer, self.policy = writer, policy
        self.q: queue.Queue = queue.Queue(maxsize=maxsize)
        self.dropped = 0
        self.max_depth = 0
        self.error: BaseException | None = None
        self._t = threading.Thread(target=self._run, name=f"rec-{writer.stem.name}", daemon=True)
        self._t.start()

    def submit(self, jpeg_bytes: bytes, frame_number: int, timestamp_ns: int) -> bool:
        item = (jpeg_bytes, frame_number, timestamp_ns)
        if self.policy == "block":
            self.q.put(item)
        else:
            try:
                self.q.put_nowait(item)
            except queue.Full:
                self.dropped += 1
                return False
        d = self.q.qsize()
        if d > self.max_depth:
            self.max_depth = d
        return True

    def _run(self):
        while True:
            item = self.q.get()
            if item is None:
                break
            try:
                self.writer.write(*item)
            except BaseException as e:  # keep draining so the producer never blocks forever
                self.error = e

    def stop(self) -> dict:
        self.q.put(None)
        self._t.join()
        man = self.writer.close()
        man.update(dropped=self.dropped, max_queue_depth=self.max_depth, thread_error=repr(self.error))
        return man
