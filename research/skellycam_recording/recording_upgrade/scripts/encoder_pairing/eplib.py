"""Shared code for T-S6 (encoder pairing): synthetic frames with a pixel barcode, the S1 64-byte sidecar record,
encoder adapters (passthrough, mjpeg_qsv, libjpeg-turbo worker pool with a reorder buffer), a pairing writer
(MKV, flush_packets=1, pts = write_index at a fixed 1/fps packet time base, record k written after mux(k+1)),
a verifier and a recovery routine.

Implementation under test: PyAV 19.0.2 (FFmpeg 9.0.2), numpy 2.5.4, simplejpeg 1.9.0 (libjpeg-turbo).
Research code, not skellycam code.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import queue
import struct
import time
import zlib
from collections import OrderedDict
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

FPS = 30
TB = Fraction(1, FPS)
DIMS = {"720p": (1280, 720), "1080p": (1920, 1080)}
QUALITY = {"720p": 95, "1080p": 94}  # target A, matched_settings.json (mjpeg_qsv_422 / jpeg_turbo_422 yuy2_*)
SCRATCH = Path(r"C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\f535e563-0d11-4407-af32-ec97af3fd139"
               r"\scratchpad\encoder_pairing")
RESULTS = Path(__file__).resolve().parents[2] / "results" / "encoder_pairing"
INT64_MIN = -(2 ** 63)

# ------------------------------------------------------------------ S1 sidecar record (SE section 8.1), 64 B
REC_BODY = "<qqqqQIIIII"  # arrival, sample, legacy, fitted, offset, size, jpeg_crc32, source_frame_number, write_index, flags
REC_FMT = REC_BODY + "I"  # + record_crc32 over bytes 0-59
REC_SIZE = struct.calcsize(REC_FMT)
assert REC_SIZE == 64 and struct.calcsize(REC_BODY) == 60
REC_DTYPE = np.dtype([("arrival_ns", "<i8"), ("sample_time_ns", "<i8"), ("legacy_ns", "<i8"), ("fitted_ns", "<i8"),
                      ("offset", "<u8"), ("size", "<u4"), ("jpeg_crc32", "<u4"), ("source_frame_number", "<u4"),
                      ("write_index", "<u4"), ("flags", "<u4"), ("record_crc32", "<u4")])
HDR_FMT = "<4sIIIIII16s20s"  # magic, version, header_size, record_size, width, height, fps, encoder, pad
HDR_SIZE = struct.calcsize(HDR_FMT)
assert HDR_SIZE == 64, HDR_SIZE
MAGIC = b"SKFR"
FLAG_GAP = 1           # source_frame_number != previous + 1
FLAG_OFFSET_LIVE = 2   # offset from st_size after the next mux (provisional; finalisation rebuilds)
FLAG_OFFSET_TAIL = 4   # last record: offset found by searching the tail after close()
FLAG_RECOVERED = 8     # offset rebuilt by recovery against a remuxed file


def pack_record(arrival, sample, legacy, offset, size, crc, sfn, wi, flags, fitted=INT64_MIN) -> bytes:
    body = struct.pack(REC_BODY, arrival, sample, legacy, fitted, offset, size, crc, sfn & 0xFFFFFFFF, wi, flags)
    return body + struct.pack("<I", zlib.crc32(body))


def read_sidecar(path: Path) -> dict:
    data = Path(path).read_bytes()
    out = {"bytes": len(data), "header_ok": False, "records": np.zeros(0, REC_DTYPE), "torn_tail_bytes": 0,
           "bad_crc_records": 0}
    if len(data) < HDR_SIZE:
        out["torn_tail_bytes"] = len(data)
        return out
    magic, ver, hs, rs, w, h, fps, enc, _ = struct.unpack(HDR_FMT, data[:HDR_SIZE])
    out.update(header_ok=magic == MAGIC, version=ver, width=w, height=h, fps=fps, encoder=enc.rstrip(b"\0").decode())
    body = data[hs:]
    n = len(body) // rs
    good = 0
    for i in range(n):
        raw = body[i * rs:(i + 1) * rs]
        if zlib.crc32(raw[:60]) != struct.unpack("<I", raw[60:64])[0]:
            break
        good += 1
    out["records"] = np.frombuffer(body[:good * rs], REC_DTYPE).copy()
    out["torn_tail_bytes"] = len(body) - n * rs
    out["bad_crc_records"] = n - good
    return out


# ------------------------------------------------------------------ deterministic fake capture times
T0 = 1_000_000_000_000


def truth_times(sfn: int, irregular: bool = False) -> tuple[int, int, int]:
    """(arrival_ns, sample_time_ns, legacy_ns) for a source frame number. Unique per sfn, never monotonic-by-call."""
    h = (sfn * 2654435761) & 0xFFFFFFFF
    jitter = (h % 4_000_001) - 2_000_000
    arrival = T0 + sfn * 33_333_333 + jitter
    if irregular:  # extra stalls: every 50th frame arrives 120 ms late, every 7th 9 ms early
        arrival += (120_000_000 if sfn % 50 == 49 else 0) - (9_000_000 if sfn % 7 == 3 else 0)
    sample = arrival - 5_000_000 - (h >> 22)
    legacy = arrival + 150_000 + (h % 997)
    return arrival, sample, legacy


# ------------------------------------------------------------------ barcode in the pixels
BAR_BITS = 48            # 32-bit id + 16-bit check
BAR_W, BAR_H, BAR_X0, BAR_Y0 = 20, 40, 40, 40


def _bits(ident: int) -> list[int]:
    ident &= 0xFFFFFFFF
    chk = zlib.crc32(struct.pack("<I", ident)) & 0xFFFF
    v = ident | (chk << 32)
    return [(v >> b) & 1 for b in range(BAR_BITS)]


def stamp_yuyv(buf: np.ndarray, w: int, ident: int) -> None:
    """Draw the barcode into a packed full-range YUYV array of shape (h, 2w)."""
    for b, bit in enumerate(_bits(ident)):
        x = BAR_X0 + b * BAR_W
        blk = buf[BAR_Y0:BAR_Y0 + BAR_H, 2 * x:2 * (x + BAR_W)]
        blk[:, 0::2] = 235 if bit else 20
        blk[:, 1::2] = 128


def read_barcode(y: np.ndarray) -> int | None:
    v = 0
    for b in range(BAR_BITS):
        x = BAR_X0 + b * BAR_W
        m = float(y[BAR_Y0 + 10:BAR_Y0 + BAR_H - 10, x + 5:x + BAR_W - 5].mean())
        if 70 < m < 185:
            return None  # ambiguous block
        v |= (1 if m >= 128 else 0) << b
    ident, chk = v & 0xFFFFFFFF, v >> 32
    return ident if (zlib.crc32(struct.pack("<I", ident)) & 0xFFFF) == chk else None


class FrameSource:
    """Synthetic full-range YUYV frames: a gradient + per-slot noise background, plus the barcode of the id."""

    def __init__(self, size: str, slots: int = 8, seed: int = 1):
        self.w, self.h = DIMS[size]
        rng = np.random.default_rng(seed)
        yy, xx = np.mgrid[0:self.h, 0:self.w]
        base_y = (40 + 170 * xx / self.w).astype(np.float32)
        u = (128 + 60 * np.sin(yy[:, 0::2] / 37.0)).astype(np.uint8)
        v = (128 + 60 * np.cos(xx[:, 0::2] / 53.0)).astype(np.uint8)
        self.ring = []
        for s in range(slots):
            y = np.clip(base_y + rng.normal(0, 2.0, base_y.shape) + 10 * np.sin((xx + 40 * s) / 30.0), 0, 255)
            a = np.empty((self.h, self.w * 2), np.uint8)
            a[:, 0::2] = y.astype(np.uint8)
            a[:, 1::4] = u
            a[:, 3::4] = v
            self.ring.append(a)

    def frame(self, ident: int) -> np.ndarray:
        a = self.ring[ident % len(self.ring)].copy()
        stamp_yuyv(a, self.w, ident)
        return a


def yuyv_planes(a: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (np.ascontiguousarray(a[:, 0::2]), np.ascontiguousarray(a[:, 1::4]), np.ascontiguousarray(a[:, 3::4]))


def av_frame_yuyv(a: np.ndarray, w: int, h: int) -> av.VideoFrame:
    f = av.VideoFrame(w, h, "yuyv422")
    p = f.planes[0]
    if p.line_size == 2 * w:
        p.update(a.tobytes())
    else:
        np.frombuffer(p, np.uint8).reshape(h, p.line_size)[:, :2 * w] = a
    f.color_range = 2  # full (JPEG) range, plan row 1.4 / hw_accel_target F2
    return f


_DEC: dict = {}


def decode_y(jpeg: bytes) -> np.ndarray:
    dec = _DEC.setdefault(os.getpid(), av.CodecContext.create("mjpeg", "r"))
    frames = list(dec.decode(av.Packet(jpeg)))
    f = frames[0]
    p = f.planes[0]
    return np.frombuffer(p, np.uint8).reshape(f.height, p.line_size)[:, :f.width]


# ------------------------------------------------------------------ encoder adapters
@dataclass
class Out:
    seq: int
    jpeg: bytes
    meta: dict
    late_calls: int | None = None  # encode() calls after its own (None = from flush)
    t_submit: float = 0.0
    t_out: float = 0.0


class PassthroughEnc:
    name = "passthrough"

    def __init__(self):
        self.pending: OrderedDict[int, tuple] = OrderedDict()

    def submit(self, seq: int, payload: bytes, meta: dict) -> list[Out]:
        t = time.perf_counter()
        return [Out(seq, payload, meta, 0, t, t)]

    def flush(self) -> list[Out]:
        return []

    def close(self):
        pass


class QsvEnc:
    """mjpeg_qsv through PyAV. Identity = frame.pts = seq (contiguous submit counter), time base 1/fps.
    Packets carry pts back (qsvenc.c:2117 -> 90 kHz -> :2669). The pending map holds the metadata until then."""

    def __init__(self, size: str, async_depth: int | None = None, pts_mode: str = "seq", tb: Fraction = TB):
        self.w, self.h = DIMS[size]
        self.name = "mjpeg_qsv" + ("" if async_depth is None else f"_ad{async_depth}")
        cc = av.CodecContext.create("mjpeg_qsv", "w")
        cc.width, cc.height, cc.pix_fmt = self.w, self.h, "yuyv422"
        cc.time_base, cc.framerate, cc.gop_size = tb, Fraction(FPS, 1), 1
        opts = {"global_quality": str(QUALITY[size])}
        if async_depth is not None:
            opts["async_depth"] = str(async_depth)
        cc.options = opts
        cc.color_range = 2
        cc.open()
        self.cc = cc
        self.pts_mode = pts_mode
        self.pending: OrderedDict[int, tuple] = OrderedDict()  # key -> (seq, meta, t_submit)
        self.calls = 0
        self.fifo_violations = 0   # packet key != oldest pending key
        self.unknown_pts = 0       # packet key not in pending

    def _key(self, seq: int, meta: dict) -> int:
        return seq if self.pts_mode == "seq" else (meta["sfn"] if self.pts_mode == "sfn" else meta["arrival_ns"])

    def _take(self, pk, cur_call: int | None) -> Out:
        key = pk.pts
        if self.pending and key != next(iter(self.pending)):
            self.fifo_violations += 1
        if key not in self.pending:
            self.unknown_pts += 1
            raise KeyError(f"packet pts {key} not pending (oldest {next(iter(self.pending), None)})")
        seq, meta, ts = self.pending.pop(key)
        return Out(seq, bytes(pk), meta, None if cur_call is None else cur_call - seq, ts, time.perf_counter())

    def submit(self, seq: int, a: np.ndarray, meta: dict) -> list[Out]:
        f = av_frame_yuyv(a, self.w, self.h)
        key = self._key(seq, meta)
        f.pts = key
        self.pending[key] = (seq, meta, time.perf_counter())
        pk = self.cc.encode(f)
        self.calls += 1
        return [self._take(p, seq) for p in pk]

    def flush(self) -> list[Out]:
        return [self._take(p, None) for p in self.cc.encode(None)]

    def close(self):
        self.cc = None


# ---- libjpeg-turbo worker pool
def _turbo_worker(wid: int, quality: int, task_q, result_q, fail_mod: int, jitter_ms: float, seed: int):
    import random

    import simplejpeg
    rnd = random.Random(seed + wid)
    parent = mp.parent_process()
    while True:
        try:
            item = task_q.get(timeout=0.5)
        except queue.Empty:
            if parent is not None and not parent.is_alive():
                # parent gone: nobody drains result_q, so don't block exit joining its feeder thread
                result_q.cancel_join_thread()
                task_q.cancel_join_thread()
                return
            continue
        if item is None:
            return
        seq, h, w2, buf = item
        a = np.frombuffer(buf, np.uint8).reshape(h, w2)
        if jitter_ms:
            time.sleep(rnd.random() * jitter_ms / 1000.0)
        if fail_mod and seq % fail_mod == fail_mod // 2:
            result_q.put((seq, None, wid, "injected failure"))
            continue
        try:
            jpg = simplejpeg.encode_jpeg_yuv_planes(*yuyv_planes(a), quality=quality, fastdct=False)
            result_q.put((seq, jpg, wid, None))
        except Exception as ex:  # noqa: BLE001
            result_q.put((seq, None, wid, repr(ex)[:200]))


class TurboPool:
    """N worker processes; results come back in any order. A reorder buffer keyed by seq releases them in seq order.
    A seq whose worker reports failure is released as a skip (no packet, no record). A seq missing for longer than
    `lost_timeout` (worker died) is also skipped."""

    def __init__(self, size: str, workers: int, max_in_flight: int | None = None, fail_mod: int = 0,
                 jitter_ms: float = 0.0, lost_timeout: float = 2.0, seed: int = 7):
        self.w, self.h = DIMS[size]
        self.name = f"turbo_w{workers}"
        ctx = mp.get_context("spawn")
        self.task_q, self.result_q = ctx.Queue(), ctx.Queue()
        self.procs = [ctx.Process(target=_turbo_worker, args=(i, QUALITY[size], self.task_q, self.result_q,
                                                               fail_mod, jitter_ms, seed), daemon=True)
                      for i in range(workers)]
        for p in self.procs:
            p.start()
        self.max_in_flight = max_in_flight or 2 * workers
        self.lost_timeout = lost_timeout
        self.pending: OrderedDict[int, tuple] = OrderedDict()   # seq -> (meta, t_submit), submit order
        self.reorder: dict[int, tuple] = {}                     # seq -> (jpeg|None, t_recv, err)
        self.next_seq: int | None = None
        # stats
        self.max_seen = -1
        self.out_of_order = 0
        self.received = 0
        self.max_held = 0
        self.max_held_bytes = 0
        self.max_in_flight_seen = 0
        self.hold_ms: list[float] = []
        self.skipped: list[tuple[int, str]] = []
        self.backpressure_waits = 0

    def worker_pids(self) -> list[int]:
        return [p.pid for p in self.procs]

    def warm(self, timeout: float = 30.0):
        """Wait until every worker has imported simplejpeg and encoded once (spawn start-up is slow)."""
        a = np.zeros((16, 32), np.uint8)
        for i in range(len(self.procs)):
            self.task_q.put((-1 - i, 16, 32, a.tobytes()))
        got = 0
        t_end = time.time() + timeout
        while got < len(self.procs) and time.time() < t_end:
            try:
                self.result_q.get(timeout=1.0)
                got += 1
            except queue.Empty:
                pass

    def _recv(self, block: bool, timeout: float = 0.2) -> bool:
        try:
            seq, jpg, wid, err = self.result_q.get(block, timeout) if block else self.result_q.get_nowait()
        except queue.Empty:
            return False
        if seq < 0:
            return True
        self.received += 1
        if seq < self.max_seen:
            self.out_of_order += 1
        self.max_seen = max(self.max_seen, seq)
        self.reorder[seq] = (jpg, time.perf_counter(), err)
        held = len(self.reorder)
        self.max_held = max(self.max_held, held)
        self.max_held_bytes = max(self.max_held_bytes, sum(len(v[0]) for v in self.reorder.values() if v[0]))
        return True

    def _release(self) -> list[Out]:
        out = []
        while self.pending:
            seq = next(iter(self.pending))
            if seq in self.reorder:
                jpg, t_recv, err = self.reorder.pop(seq)
                meta, ts = self.pending.pop(seq)
                now = time.perf_counter()
                self.hold_ms.append((now - t_recv) * 1000)
                if jpg is None:
                    self.skipped.append((seq, err))
                    continue
                out.append(Out(seq, jpg, meta, None, ts, now))
            elif time.perf_counter() - self.pending[seq][1] > self.lost_timeout:
                self.pending.pop(seq)
                self.skipped.append((seq, "lost (timeout)"))
            else:
                break
        return out

    def submit(self, seq: int, a: np.ndarray, meta: dict) -> list[Out]:
        out: list[Out] = []
        while len(self.pending) >= self.max_in_flight:  # backpressure: wait for the oldest
            self.backpressure_waits += 1
            self._recv(True)
            out += self._release()
        self.pending[seq] = (meta, time.perf_counter())
        self.max_in_flight_seen = max(self.max_in_flight_seen, len(self.pending))
        self.task_q.put((seq, a.shape[0], a.shape[1], a.tobytes()))
        while self._recv(False):
            pass
        return out + self._release()

    def flush(self) -> list[Out]:
        out: list[Out] = []
        while self.pending:
            self._recv(True)
            out += self._release()
        return out

    def close(self):
        for _ in self.procs:
            self.task_q.put(None)
        for p in self.procs:
            p.join(5)
            if p.is_alive():
                p.terminate()

    def stats(self) -> dict:
        hm = np.array(self.hold_ms) if self.hold_ms else np.zeros(1)
        return {"received": self.received, "out_of_order_arrivals": self.out_of_order,
                "reorder_max_held_frames": self.max_held, "reorder_max_held_bytes": self.max_held_bytes,
                "max_in_flight_frames": self.max_in_flight_seen, "max_in_flight_cap": self.max_in_flight,
                "hold_ms_p50": round(float(np.percentile(hm, 50)), 3),
                "hold_ms_p99": round(float(np.percentile(hm, 99)), 3), "hold_ms_max": round(float(hm.max()), 3),
                "frames_held_nonzero": int((hm > 0.05).sum()),
                "skipped": [[s, e] for s, e in self.skipped], "backpressure_waits": self.backpressure_waits}


# ------------------------------------------------------------------ the pairing writer
class PairingWriter:
    """Writer rule under test:
    - the encoder adapter releases (seq, jpeg, meta) strictly in seq order, meta taken from its pending map;
    - write_index = number of packets muxed so far; container pts = write_index at packet time base 1/fps;
    - the record for packet k is written after mux(k+1) returns (MKV holds one packet back, so frame k is then
      on disk, offset = st_size - size_k); the last record after close(), offset found in the tail.
    `hook(point, write_index)` lets the crash test kill the process at chosen points."""

    def __init__(self, stem: Path, w: int, h: int, encoder: str, hook=None, log=None):
        self.mkv = Path(str(stem) + ".mkv")
        self.skfr = Path(str(stem) + ".skfr")
        for p in (self.mkv, self.skfr):
            if p.exists():
                p.unlink()
        self.c = av.open(str(self.mkv), "w", format="matroska", options={"flush_packets": "1"})
        self.s = self.c.add_stream("mjpeg", rate=FPS)
        self.s.width, self.s.height, self.s.pix_fmt = w, h, "yuvj422p"
        self.s.time_base = TB
        self.c.start_encoding()
        self.side = open(self.skfr, "wb")
        self.side.write(struct.pack(HDR_FMT, MAGIC, 1, HDR_SIZE, REC_SIZE, w, h, FPS, encoder.encode()[:16], b""))
        self.side.flush()
        self.count = 0
        self.prev: dict | None = None
        self.last_seq: int | None = None
        self.last_sfn: int | None = None
        self.hook = hook or (lambda point, wi: None)
        self.log = log
        self.order_violations = 0

    def _emit(self, r: dict, offset: int, flag: int):
        rec = pack_record(r["arrival"], r["sample"], r["legacy"], offset, r["size"], r["crc"], r["sfn"], r["wi"],
                          r["flags"] | flag)
        if self.hook("mid_record", r["wi"]) == "torn":
            self.side.write(rec[:37])
            self.side.flush()
            os._exit(1)
        self.side.write(rec)
        self.side.flush()
        if self.log:
            self.log.write(f"R {r['seq']} {r['wi']}\n")
            self.log.flush()
        self.hook("after_record", r["wi"])

    def write(self, o: Out):
        if self.last_seq is not None and o.seq <= self.last_seq:
            self.order_violations += 1
            raise RuntimeError(f"seq {o.seq} after {self.last_seq}")
        wi = self.count
        self.hook("before_mux", wi)
        pkt = av.Packet(o.jpeg)
        pkt.stream = self.s
        pkt.time_base = TB
        pkt.pts = pkt.dts = wi
        pkt.is_keyframe = True
        self.c.mux(pkt)
        if self.log:
            self.log.write(f"M {o.seq} {wi}\n")
            self.log.flush()
        self.hook("after_mux", wi)
        if self.prev is not None:
            self._emit(self.prev, os.stat(self.mkv).st_size - self.prev["size"], FLAG_OFFSET_LIVE)
        sfn = o.meta["sfn"]
        flags = FLAG_GAP if (self.last_sfn is not None and sfn != self.last_sfn + 1) else 0
        self.prev = {"seq": o.seq, "wi": wi, "size": len(o.jpeg), "crc": zlib.crc32(o.jpeg), "sfn": sfn,
                     "arrival": o.meta["arrival_ns"], "sample": o.meta["sample_ns"], "legacy": o.meta["legacy_ns"],
                     "flags": flags, "jpeg": o.jpeg}
        self.count += 1
        self.last_seq, self.last_sfn = o.seq, sfn

    def close(self) -> dict:
        size_before = os.stat(self.mkv).st_size
        self.c.close()
        self.hook("after_container_close", self.count)
        if self.prev is not None:
            with open(self.mkv, "rb") as fh:
                fh.seek(size_before)
                tail = fh.read()
            idx = tail.find(self.prev["jpeg"])
            if idx < 0:
                raise RuntimeError("last JPEG not found in tail")
            self._emit(self.prev, size_before + idx, FLAG_OFFSET_TAIL)
        self.side.close()
        return {"packets": self.count}


def make_meta(sfn: int, irregular: bool = False) -> dict:
    a, s, l = truth_times(sfn, irregular)
    return {"sfn": sfn, "arrival_ns": a, "sample_ns": s, "legacy_ns": l}


# ------------------------------------------------------------------ verification
def scan_mkv(path: Path) -> list[dict]:
    """Demux every packet (works on unfinalised files): write index from pts, offset = pos + 4, CRC."""
    out = []
    try:
        with av.open(str(path)) as c:
            st = c.streams.video[0]
            tb = st.time_base
            for pk in c.demux(st):
                if pk.size == 0 or pk.pts is None:
                    continue
                b = bytes(pk)
                out.append({"wi": int(round(pk.pts * tb * FPS)), "pos": pk.pos, "size": pk.size,
                            "crc": zlib.crc32(b)})
    except Exception as ex:  # noqa: BLE001
        out.append({"error": f"{type(ex).__name__}: {ex}"[:200]})
    return out


def verify(stem: Path, irregular: bool = False, mkv: Path | None = None, skfr: Path | None = None) -> dict:
    mkv = mkv or Path(str(stem) + ".mkv")
    skfr = skfr or Path(str(stem) + ".skfr")
    sc = read_sidecar(skfr)
    recs = sc["records"]
    raw = mkv.read_bytes() if mkv.exists() else b""
    bad = []
    pts_ok = crc_ok = bar_ok = times_ok = wi_ok = 0
    for i, r in enumerate(recs):
        off, size = int(r["offset"]), int(r["size"])
        chunk = raw[off:off + size]
        problems = []
        if int(r["write_index"]) == i:
            wi_ok += 1
        else:
            problems.append("write_index")
        if len(chunk) == size and zlib.crc32(chunk) == int(r["jpeg_crc32"]):
            crc_ok += 1
            try:
                ident = read_barcode(decode_y(chunk))
            except Exception as ex:  # noqa: BLE001
                ident = f"decode error {ex}"
            if ident == int(r["source_frame_number"]):
                bar_ok += 1
            else:
                problems.append(f"barcode {ident} != sfn {int(r['source_frame_number'])}")
        else:
            problems.append("crc/offset")
        a, s, l = truth_times(int(r["source_frame_number"]), irregular)
        if (int(r["arrival_ns"]), int(r["sample_time_ns"]), int(r["legacy_ns"])) == (a, s, l):
            times_ok += 1
        else:
            problems.append("times")
        if problems:
            bad.append({"i": i, "problems": problems})
    pk = scan_mkv(mkv) if mkv.exists() else []
    scan_err = [p["error"] for p in pk if "error" in p]
    pk = [p for p in pk if "error" not in p]
    by_wi = {p["wi"]: p for p in pk}
    for i, r in enumerate(recs):
        p = by_wi.get(int(r["write_index"]))
        if p and p["crc"] == int(r["jpeg_crc32"]) and p["pos"] + 4 == int(r["offset"]):
            pts_ok += 1
    pts_seq = [p["wi"] for p in pk]
    n = len(recs)
    sfn = recs["source_frame_number"].astype(np.int64) if n else np.zeros(0, np.int64)
    return {"records": n, "torn_tail_bytes": sc["torn_tail_bytes"], "bad_crc_records": sc["bad_crc_records"],
            "pair_crc_ok": crc_ok, "pair_barcode_ok": bar_ok, "pair_times_ok": times_ok, "write_index_ok": wi_ok,
            "container_pts_offset_crc_ok": pts_ok,
            "mkv_packets": len(pk), "mkv_pts_in_order": pts_seq == list(range(len(pts_seq))),
            "mkv_packets_without_record": len(pk) - n if len(pk) >= n else -(n - len(pk)),
            "sfn_gaps": int((np.diff(sfn) != 1).sum()) if n > 1 else 0,
            "gap_flags": int(((recs["flags"] & FLAG_GAP) != 0).sum()) if n else 0,
            "all_pairs_ok": n > 0 and crc_ok == bar_ok == times_ok == wi_ok == n and not bad,
            "bad_examples": bad[:10], "scan_errors": scan_err}


# ------------------------------------------------------------------ recovery (crashed file -> remux -> rebuild)
def recover(stem: Path) -> dict:
    """What recovery must do: (1) truncate the sidecar to its CRC-valid records; (2) remux the MKV; (3) rebuild each
    record's offset against the remuxed file by write_index (= pts) and check CRC+size; (4) drop MKV packets that
    have no record (their times are unknown); (5) write the new sidecar."""
    src_mkv, src_skfr = Path(str(stem) + ".mkv"), Path(str(stem) + ".skfr")
    out_stem = Path(str(stem) + ".recovered")
    dst_mkv, dst_skfr = Path(str(out_stem) + ".mkv"), Path(str(out_stem) + ".skfr")
    for p in (dst_mkv, dst_skfr):
        if p.exists():
            p.unlink()
    sc = read_sidecar(src_skfr)
    recs = sc["records"]
    want = {int(r["write_index"]): r for r in recs}
    kept = dropped_no_record = mismatched = 0
    with av.open(str(src_mkv)) as ic, av.open(str(dst_mkv), "w", format="matroska") as oc:
        ist = ic.streams.video[0]
        ost = oc.add_stream("mjpeg", rate=FPS)
        ost.width, ost.height, ost.pix_fmt = ist.codec_context.width, ist.codec_context.height, "yuvj422p"
        ost.time_base = TB
        oc.start_encoding()
        for pk in ic.demux(ist):
            if pk.size == 0 or pk.pts is None:
                continue
            wi = int(round(pk.pts * ist.time_base * FPS))
            r = want.get(wi)
            b = bytes(pk)
            if r is None:
                dropped_no_record += 1
                continue
            if zlib.crc32(b) != int(r["jpeg_crc32"]) or len(b) != int(r["size"]):
                mismatched += 1
                continue
            np_ = av.Packet(b)
            np_.stream = ost
            np_.time_base = TB
            np_.pts = np_.dts = wi
            np_.is_keyframe = True
            oc.mux(np_)
            kept += 1
    # rebuild offsets by scanning the remuxed file
    scan = {p["wi"]: p for p in scan_mkv(dst_mkv) if "error" not in p}
    hdr = src_skfr.read_bytes()[:HDR_SIZE]
    with open(dst_skfr, "wb") as fh:
        fh.write(hdr)
        for r in recs:
            p = scan.get(int(r["write_index"]))
            if p is None:
                continue
            fh.write(pack_record(int(r["arrival_ns"]), int(r["sample_time_ns"]), int(r["legacy_ns"]), p["pos"] + 4,
                                 int(r["size"]), int(r["jpeg_crc32"]), int(r["source_frame_number"]),
                                 int(r["write_index"]), (int(r["flags"]) & ~(FLAG_OFFSET_LIVE | FLAG_OFFSET_TAIL))
                                 | FLAG_RECOVERED))
    return {"records_in": len(recs), "torn_tail_bytes_dropped": sc["torn_tail_bytes"], "packets_kept": kept,
            "packets_dropped_no_record": dropped_no_record, "packets_crc_mismatch": mismatched,
            "out_stem": str(out_stem)}
