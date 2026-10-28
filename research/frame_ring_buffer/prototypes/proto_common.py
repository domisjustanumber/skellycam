"""Shared helpers for the PROTOTYPE benchmarks (prototype code, NOT SkellyCam code).

Re-uses the baseline helpers (synthetic frames, stats, env capture) from ../baseline/bench_common.py so that
content, statistics and environment blocks are identical to the baseline runs.

SeqRing is the prototype ring buffer used by most prototypes. It is deliberately small and self-contained:

  one multiprocessing.shared_memory block =
      [ header   : 4096 B  -> int64 head (last published k) at +0, gated-reader cursors at +64*(1+i)  (own cache line each)
        slot meta: L x 64 B -> per slot int64[8] = seq, frame_number, tick_ns, published_ns, nbytes, aux0, aux1, aux2
        payload  : L x slot_bytes (each slot rounded up to 4096 B) ]

Write protocol for frame k (single writer per ring):
     seq[k%L] = 2k+1  (odd = write in progress)  ->  write payload (in place, e.g. decode/copy into slot view)
     -> meta fields -> seq[k%L] = 2k+2 (even = stable for frame k) -> head = k
Read protocol (any number of readers, no locks):
     k = head ; s1 = seq[k%L] ; require s1 == 2k+2 ; use a VIEW of the payload ; s2 = seq[k%L] ; accept iff s2 == s1
     (if the writer lapped the slot during use, s2 != s1 and the result is discarded = "detected torn read").
Gating (lossless readers, e.g. the recorder): each gated reader owns cursor[i] = last k it has fully consumed.
     Before writing frame k the writer requires min(cursor) >= k - L (slot k%L no longer holds an unconsumed frame).
     policy "block": writer waits (spin/sleep) - the sensor keeps ticking, so lost sensor frames are COUNTED upstream;
     policy "drop":  writer skips frame k and increments header ring_full_drops (explicit accounting);
     policy "overwrite": no gating (the current SkellyCam policy) - a lapped recorder sees a frame-number gap.

Memory ordering: the int64 stores are 8-byte aligned numpy scalar stores (single MOV on x86-64). x86-64 TSO keeps
store->store and load->load order, and each Python statement is a separate C call, so the compiler cannot reorder
across them. This is the standard x86 seqlock argument; it is NOT portable to weakly ordered CPUs (ARM) without
explicit fences - that is a real argument for a tiny native helper (see README).
"""
from __future__ import annotations

import json
import os
import sys
import time
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "baseline"))
import bench_common as bc  # noqa: E402  (baseline helpers: synthetic_frames, stats_ms, env_summary, SIZES, SCRATCH_TMP)

import sys as _fp_sys; _fp_sys.path.insert(0, str(Path(__file__).resolve().parents[1])); from fp_paths import results_dir as _results_dir  # noqa: E402,E702
RESULTS = _results_dir(HERE)
RESULTS.mkdir(exist_ok=True)
# Large temporary files (videos) go here; each script records their sizes in its JSON, then deletes them.
# (bench_common.SCRATCH_TMP points at the 2026-10-25 session's scratch folder; the study now uses this fixed folder.)
SCRATCH_TMP = Path(os.environ.get("PROTO_SCRATCH_TMP",
                                  r"C:\Users\Dom\AppData\Local\Temp\skellycam_frame_pipeline_tmp\bench_tmp"))
SCRATCH_TMP.mkdir(parents=True, exist_ok=True)
SIZES = bc.SIZES
stats_ms = bc.stats_ms
synthetic_frames = bc.synthetic_frames

HDR = 4096
META_W = 8  # int64 fields per slot
F_SEQ, F_FN, F_TICK, F_PUB, F_NBYTES, F_AUX0, F_AUX1, F_AUX2 = range(8)
H_HEAD = 0          # int64 index into header int64 view
H_DROPS = 1         # ring_full_drops (policy "drop")
H_BLOCK_NS = 2      # total ns the writer spent blocked (policy "block")
H_BLOCK_EVENTS = 3
CURSOR_BASE = 8     # cursor i at int64 index 8*(1+i)  (64 B apart)
MAX_CURSORS = 8


def _round4k(n: int) -> int:
    return (n + 4095) // 4096 * 4096


class SeqRing:
    def __init__(self, shm: shared_memory.SharedMemory, length: int, slot_bytes: int, owner: bool):
        self.shm = shm
        self.L = length
        self.slot_bytes = slot_bytes
        self.slot_stride = _round4k(slot_bytes)
        self.owner = owner
        buf = shm.buf
        self.hdr = np.ndarray((HDR // 8,), np.int64, buf, 0)
        self.meta = np.ndarray((length, META_W), np.int64, buf, HDR)
        off = HDR + _round4k(length * META_W * 8)
        self.payload = np.ndarray((length, self.slot_stride), np.uint8, buf, off)

    # ---------------- creation / attach ----------------
    @classmethod
    def create(cls, length: int, slot_bytes: int, prefault: bool = True) -> "SeqRing":
        size = HDR + _round4k(length * META_W * 8) + length * _round4k(slot_bytes)
        shm = shared_memory.SharedMemory(create=True, size=size)
        r = cls(shm, length, slot_bytes, owner=True)
        r.hdr[:] = 0
        r.hdr[H_HEAD] = -1
        for i in range(MAX_CURSORS):
            r.hdr[CURSOR_BASE * (1 + i)] = -1
        r.meta[:] = 0
        r.meta[:, F_SEQ] = 0
        if prefault:
            r.payload[:] = 0  # touch every page once so first-lap page faults are not on the hot path
        return r

    def spec(self) -> dict:
        return dict(name=self.shm.name, length=self.L, slot_bytes=self.slot_bytes)

    @classmethod
    def attach(cls, spec: dict) -> "SeqRing":
        shm = shared_memory.SharedMemory(name=spec["name"])
        return cls(shm, spec["length"], spec["slot_bytes"], owner=False)

    def close(self):
        # drop numpy views before closing the mapping
        self.hdr = self.meta = self.payload = None
        try:
            self.shm.close()
        except Exception:
            pass
        if self.owner:
            try:
                self.shm.unlink()
            except Exception:
                pass

    # ---------------- views ----------------
    def image_view(self, slot: int, shape) -> np.ndarray:
        n = int(np.prod(shape))
        return self.payload[slot, :n].reshape(shape)

    def bytes_view(self, slot: int, nbytes: int) -> np.ndarray:
        return self.payload[slot, :nbytes]

    # ---------------- writer ----------------
    @property
    def head(self) -> int:
        return int(self.hdr[H_HEAD])

    def cursor(self, i: int) -> int:
        return int(self.hdr[CURSOR_BASE * (1 + i)])

    def set_cursor(self, i: int, k: int):
        self.hdr[CURSOR_BASE * (1 + i)] = k

    def can_write(self, k: int, n_gated: int) -> bool:
        if n_gated == 0:
            return True
        lim = k - self.L
        for i in range(n_gated):
            if self.hdr[CURSOR_BASE * (1 + i)] < lim:
                return False
        return True

    def begin(self, k: int) -> int:
        s = k % self.L
        self.meta[s, F_SEQ] = 2 * k + 1
        return s

    def commit(self, k: int, s: int, frame_number: int, tick_ns: int, nbytes: int = 0, aux0: int = 0):
        m = self.meta[s]
        m[F_FN] = frame_number
        m[F_TICK] = tick_ns
        m[F_NBYTES] = nbytes
        m[F_AUX0] = aux0
        m[F_PUB] = time.perf_counter_ns()
        self.meta[s, F_SEQ] = 2 * k + 2
        self.hdr[H_HEAD] = k

    # ---------------- reader ----------------
    def seq_for(self, k: int) -> int:
        return int(self.meta[k % self.L, F_SEQ])

    def stable(self, k: int, s1: int) -> bool:
        return s1 == 2 * k + 2 and int(self.meta[k % self.L, F_SEQ]) == s1


def write_json(name: str, obj) -> Path:
    p = RESULTS / name
    p.write_text(json.dumps(obj, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    return p


def write_text(name: str, text: str) -> Path:
    p = RESULTS / name
    p.write_text(text, encoding="utf-8")
    return p


def env_summary() -> dict:
    d = bc.env_summary()
    try:
        import av
        d["av"] = av.__version__
    except Exception:
        pass
    try:
        import simplejpeg
        d["simplejpeg"] = simplejpeg.__version__
    except Exception:
        d["simplejpeg"] = None
    return d


def sleep_until(t_ns: int):
    """Same pacing primitive as the baseline FakeCapture/content_writer: coarse sleep, then spin."""
    while True:
        rem = t_ns - time.perf_counter_ns()
        if rem <= 0:
            return
        if rem > 2_000_000:
            time.sleep((rem - 1_500_000) / 1e9)


class FakeSensor:
    """Free-running 60 fps sensor with latest-frame-wins semantics - identical model to baseline FakeCapture
    (bench_e_e2e.py): grab() blocks until the next tick if the loop is early; if the loop is late the skipped
    ticks are counted as sensor frames never grabbed."""

    def __init__(self, fps: float, seed: int):
        self.period = int(1e9 / fps)
        rng = np.random.default_rng(seed)
        self.t0 = time.perf_counter_ns() + int(rng.integers(0, self.period))
        self.last_tick = -1
        self.skipped = 0

    def grab(self):
        now = time.perf_counter_ns()
        tick = (now - self.t0) // self.period
        if tick <= self.last_tick:
            tick = self.last_tick + 1
            sleep_until(self.t0 + tick * self.period)
            skipped = 0
        else:
            skipped = tick - self.last_tick - 1
        if self.last_tick >= 0:
            self.skipped += skipped
        self.last_tick = tick
        return int(tick), int(self.t0 + tick * self.period)


def cpu_sampler(pids, stop_evt, out: list, interval=1.0):
    """Sample psutil cpu_percent for a list of pids + system, every interval s (run in a thread)."""
    import psutil
    procs = []
    for p in pids:
        try:
            pp = psutil.Process(p)
            pp.cpu_percent(None)
            procs.append(pp)
        except Exception:
            pass
    psutil.cpu_percent(None)
    while not stop_evt.wait(interval):
        row = {"t": time.perf_counter(), "system": psutil.cpu_percent(None)}
        for pp in procs:
            try:
                row[str(pp.pid)] = pp.cpu_percent(None)
            except Exception:
                pass
        out.append(row)


def summarize_cpu(samples, skip_first=1):
    if len(samples) <= skip_first:
        return None
    s = samples[skip_first:]
    keys = [k for k in s[0] if k != "t"]
    m = {k: float(np.mean([r.get(k, 0.0) for r in s])) for k in keys}
    m["sum_processes"] = float(sum(v for k, v in m.items() if k != "system"))
    return m


def count_video_frames(path) -> int:
    import cv2
    cap = cv2.VideoCapture(str(path))
    n = 0
    while cap.grab():
        n += 1
    cap.release()
    return n
