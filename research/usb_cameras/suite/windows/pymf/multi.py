"""``pymf multi``: several cameras streaming from ONE Python process, one async source reader per camera on its own
thread: the way skellycam's camera process would use a pure-Python MF backend (CAPTURE_AND_RECORDING_PLAN.md 3.2
package 1.3; W-PYMF-ALL de-risks it).

Threading model:
- main thread (MTA): starts one camera thread per camera (all at once), waits for the open phase (bounded), then
  keeps the session clock: part length, CPU timeline (GetProcessTimes), the intruder thread; sets the stop event
  and joins every thread against a deadline.
- camera thread ``pymf-cam-<label>`` (MTA), one per camera: mf.open_session (enumerate -> activate -> async reader
  with converters off -> explicit native type -> first ReadSample, each step a bounded call) -> mf.wait_first
  (bounded from the last progress) -> watches its own stream (error, stall > --timeout-ms, end) and runs its
  control schedule on its own IMFMediaSource (IAMCameraControl / IAMVideoProcAmp, IKsControl fallback; read before,
  set, read back in one bounded call) -> restores what it changed -> mf.close_session (stop reads -> Flush ->
  reader release -> interface release -> Shutdown, each bounded). A camera that fails (first-sample timeout,
  0x8007001F, stall, error) is closed AT ONCE by its own thread and never re-opened in the session; the others go
  on. This is the Kiyo Pro rule: the session stops using it the moment it shows a fault.
- samples arrive on MF work-queue threads in mf.ReaderCallback -> ``multi_sample``: per-frame record appended to
  memory (framerec.REC), the cheap integrity bits (SOI/EOI/SOF size), and the few JPEGs to keep (samples, control
  windows) queued. The camera thread flushes the records to ``<label>/frames.bin`` every 0.5 s, and the writer
  thread writes the queued JPEGs: no file I/O inside a callback.
- intruder thread (in-use part only): runs the spec's second-opener commands at their times, each with a hard
  timeout that kills its whole process tree (common.procutil).

Every camera call is bounded (bounded.call); a hung call is abandoned, recorded (``unreleasable`` / timed-out
control) and the CLI ends the process with os._exit (cli.finish), as for capture. The CLI's watchdog and the
suite's camcmd timeout are the backstops.

Spec (JSON file, ``pymf multi --spec FILE``)::

    {"seconds": 600,                        # streaming length after the open phase
     "cameras": [{"label": "c922_046d-085c_ab12", "device": "<MF symlink>" | "url": "<file URL, offline tests>",
                  "width": 1280, "height": 720, "fps": 30, "subtype": "MJPG", "is_kiyo": false,
                  "samples": 4,             # JPEGs kept: the first frame + evenly spread over the part
                  "controls": [{"at_s": 120, "control": "exposure", "delta": -2, "flags": "manual"},
                               {"at_s": 300, "control": "exposure", "value": "start", "flags": "manual"}],
                  "window": {"pre": 5, "post": 60},  # frames kept around each control set (for the luma check)
                  "restore": true}],        # put changed controls back to their first-read value and mode
     "intruders": [{"label": "wincam_capture", "at_s": 14, "timeout_s": 40, "target": "<label>",
                    "argv": ["...wincam.exe", "capture", ...]}],
     "tail_s": 3}                           # streaming kept after the last intruder ended

Control values: ``delta`` = steps from the value read just before the set (the other direction when out of range);
``value`` = an integer, "start" (the value read before this camera's first set) or "default".
"""
from __future__ import annotations

import collections
import json
import subprocess
import sys
import threading
import time
import traceback
from ctypes import byref, c_void_p
from pathlib import Path
from typing import Any

from . import bounded
from . import com as C
from . import framerec as FR
from . import mf
from . import parse as P

MASK = 0xFFFFFFFF
SAVE_QUEUE_MAX = 4000
REC_FLUSH_S = 0.5
PARTIAL_EVERY_S = 1.0
CPU_TIMELINE_S = 10.0
DEFAULT_WINDOW = {"pre": 5, "post": 60}
DEFAULT_SAMPLES = 4
DEFAULT_TAIL_S = 3.0


def qpc() -> int:
    return time.perf_counter_ns()


def utc_now() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ============================================================================================================ writer
class Writer(threading.Thread):
    """Writes queued (path, bytes) jobs. put() never blocks a callback: a full queue drops and counts the job."""

    def __init__(self, maxsize: int = SAVE_QUEUE_MAX):
        super().__init__(name="pymf-writer", daemon=True)
        import queue
        self._queue_mod = queue
        self.q = queue.Queue(maxsize)
        self.mu = threading.Lock()
        self.queued = self.written = self.dropped = self.errors = 0

    def put(self, path: Path, data: bytes) -> bool:
        try:
            self.q.put_nowait((path, data))
        except self._queue_mod.Full:
            with self.mu:
                self.dropped += 1
            return False
        with self.mu:
            self.queued += 1
        return True

    def run(self) -> None:
        while True:
            item = self.q.get()
            if item is None:
                return
            path, data = item
            try:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).write_bytes(data)
                with self.mu:
                    self.written += 1
            except OSError:
                with self.mu:
                    self.errors += 1

    def stop(self, timeout_s: float) -> bool:
        try:
            self.q.put(None, timeout=timeout_s)
        except self._queue_mod.Full:
            return False
        self.join(timeout_s)
        return not self.is_alive()

    def stats(self) -> dict:
        with self.mu:
            return {"queued": self.queued, "written": self.written, "dropped": self.dropped, "errors": self.errors,
                    "queue_max": self.q.maxsize}


# ============================================================================================================ samples
class CamState(mf.StreamState):
    """mf.StreamState plus what multi_sample needs; the shared counters keep their mf meaning."""

    def __init__(self, label: str, w: int, h: int, out_dir: Path, writer: Writer, pre: int):
        super().__init__(w, h, 0)
        self.sample_fn = multi_sample
        self.label = label
        self.dir = out_dir
        self.writer = writer
        self.recs = bytearray()
        self.ring: collections.deque = collections.deque(maxlen=max(1, pre))
        self.want_sample = True                 # the first frame is always kept
        self.sample_seqs: list[int] = []
        self.capture_until = -1
        self.capture_dir: Path | None = None
        self.window_saved = 0
        self.size_min: int | None = None
        self.size_max = 0


def multi_sample(st: CamState, arr: int, flags: int, ts: int, s) -> None:
    """Per sample, on an MF work-queue thread, under st.mu: record, integrity bits, JPEG copies to keep."""
    seq = st.frames
    st.frames += 1
    if not st.first_ns:
        st.first_ns = arr
    st.last_ns = arr
    stime, sdur = C.LONGLONG(), C.LONGLONG()
    hst = s.GetSampleTime(byref(stime)) & MASK
    s.GetSampleDuration(byref(sdur))
    _h, disc = C.get_uint32(s, C.MFSampleExtension_Discontinuity)
    data = b""
    braw = c_void_p()
    if not s.ConvertToContiguousBuffer(byref(braw)) & 0x80000000:
        buf = C.own(braw, C.IMFMediaBuffer)
        _hl, data = C.lock_bytes(buf)
        C.release(buf)
    ji = P.jpeg_info(data)
    n = len(data)
    st.bytes += n
    st.size_min = n if st.size_min is None else min(st.size_min, n)
    st.size_max = max(st.size_max, n)
    eoiok = ji["eoi"] or ji["eoi_trailing"] >= 0
    sizeok = ji["sof_w"] == st.req_w and ji["sof_h"] == st.req_h
    bits = 0
    if ji["soi"]:
        bits |= FR.BIT_SOI
    if eoiok:
        bits |= FR.BIT_EOI
    if sizeok:
        bits |= FR.BIT_SIZE
        st.sof_match += 1
    if disc:
        bits |= FR.BIT_DISC
        st.discont += 1
    if ji["eoi_trailing"] > 0:
        bits |= FR.BIT_TRAIL
    if ji["soi"] and eoiok:
        st.soi_eoi += 1
    if ji["soi"] and eoiok and sizeok:
        st.ok_frames += 1
    if st.want_sample and n:
        if st.writer.put(st.dir / "samples" / f"f{seq:07d}.jpg", data):
            st.sample_seqs.append(seq)
            bits |= FR.BIT_SAVED
        st.want_sample = False
    if st.capture_dir is not None and seq < st.capture_until and n:
        if st.writer.put(st.capture_dir / f"f{seq:07d}.jpg", data):
            st.window_saved += 1
            bits |= FR.BIT_SAVED
    st.ring.append((seq, arr, data))
    st.recs += FR.pack(seq, arr, stime.value if not hst else None, sdur.value, n, flags, bits, ji["sof_w"],
                       ji["sof_h"])


# ============================================================================================================ camera
class Shared:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.t_all_ns: int | None = None


class Cam:
    """One camera of the session: its spec, state, session and the records its thread produces."""

    def __init__(self, spec: dict, out_dir: Path, writer: Writer, timeout_ms: int, seconds: float):
        self.spec = spec
        self.label = str(spec["label"])
        self.device = spec.get("device") or ""
        self.url = spec.get("url") or ""
        self.is_kiyo = bool(spec.get("is_kiyo"))
        self.mode = {"subtype": spec.get("subtype") or "MJPG", "w": int(spec["width"]), "h": int(spec["height"]),
                     "fps": float(spec["fps"])}
        self.dir = Path(out_dir) / self.label
        self.window = {**DEFAULT_WINDOW, **(spec.get("window") or {})}
        self.st = CamState(self.label, self.mode["w"], self.mode["h"], self.dir, writer, int(self.window["pre"]))
        self.s = mf.Session()
        self.writer = writer
        self.timeout_ms = timeout_ms
        self.seconds = seconds
        self.n_samples = max(1, int(spec.get("samples", DEFAULT_SAMPLES)))
        self.ctl_plan = sorted((dict(c) for c in spec.get("controls") or []), key=lambda c: float(c["at_s"]))
        self.restore = spec.get("restore", True) is not False
        self.opened = threading.Event()
        self.done = threading.Event()
        self.thread: threading.Thread | None = None
        self.stage = "created"
        self.open_ok = False
        self.closed_by: str | None = None
        self.t_start_ns = self.t_fail_ns = self.close_start_ns = self.close_end_ns = 0
        self.controls: list[dict] = []
        self.ctl_start: dict[str, tuple] = {}
        self.ctl_hung = False
        self.restores: list[dict] = []
        self.restore_skipped: str | None = None
        self.exc: str | None = None
        self.frames_file = None
        self.rec_bytes = 0

    # ---------------------------------------------------------------- thread
    def main(self, sh: Shared) -> None:
        C.coinit_mta()
        try:
            self._body(sh)
        except BaseException:  # noqa: BLE001 - recorded; never kills the session
            self.exc = traceback.format_exc(limit=8)
        finally:
            self._flush()
            if self.frames_file is not None:
                try:
                    self.frames_file.close()
                except OSError:
                    pass
            self.opened.set()
            self.done.set()

    def _body(self, sh: Shared) -> None:
        s, st, T = self.s, self.st, self.timeout_ms
        self.dir.mkdir(parents=True, exist_ok=True)
        self.frames_file = open(self.dir / "frames.bin", "wb")
        self.t_start_ns = qpc()
        self.stage = "opening"
        ok = mf.open_session(s, self.url or self.device, self.mode, st, T, url=bool(self.url))
        if ok:
            self.stage = "first_sample"
            ok = mf.wait_first(s, T)
        self.open_ok = ok
        self.opened.set()
        if ok:
            self.stage = "streaming"
            ok = self._stream(sh)
        if not ok:
            self.t_fail_ns = qpc()
            if self.closed_by is None:
                self.closed_by = "failure"
        if self.controls or self.ctl_start:
            if not self.restore:
                self.restore_skipped = "restore off in the spec"
            elif self.ctl_hung:
                self.restore_skipped = "a control call timed out: the source is not touched again"
            elif not ok:
                self.restore_skipped = (f"camera failed ({FR.fault_kind(s.error(), s.unreleasable)}): the session "
                                        "stops using it")
            else:
                self.stage = "restore"
                self._restore()
        self.stage = "closing"
        self.close_start_ns = qpc()
        mf.close_session(s, T)
        self.close_end_ns = qpc()
        self._flush()
        self.stage = "unreleasable" if s.unreleasable else "closed"
        self._partial()

    def _stream(self, sh: Shared) -> bool:
        s, st, T = self.s, self.st, self.timeout_ms
        next_flush = next_partial = 0
        due_samples: list[float] | None = None
        ctl = list(self.ctl_plan)
        while True:
            if sh.stop.is_set():
                self.closed_by = "stop"
                return True
            now = qpc()
            with st.mu:
                err, eos, prog = st.err, st.eos, st.progress_ns
            if err is not None:
                s.fail("streaming", err, False)
                return False
            if eos:
                if self.url:                          # a file source ends: normal (offline self-test)
                    self.closed_by = "end_of_file"
                    return True
                s.fail("streaming", P.MF_E_END_OF_STREAM, False)
                return False
            if (now - prog) / 1e6 > T:
                s.fail("streaming", P.E_FAIL, True)
                return False
            if sh.t_all_ns is not None:
                el = (now - sh.t_all_ns) / 1e9
                if due_samples is None:
                    k = self.n_samples
                    due_samples = [self.seconds * i / k for i in range(1, k)]
                while due_samples and el >= due_samples[0]:
                    due_samples.pop(0)
                    with st.mu:
                        st.want_sample = True
                if ctl and not self.ctl_hung and el >= float(ctl[0]["at_s"]):
                    self.controls.append(self.control(ctl.pop(0), len(self.controls)))
            if now >= next_flush:
                self._flush()
                next_flush = now + int(REC_FLUSH_S * 1e9)
            if now >= next_partial:
                self._partial()
                next_partial = now + int(PARTIAL_EVERY_S * 1e9)
            st.ev_sample.wait(0.05)
            st.ev_sample.clear()

    def _flush(self) -> None:
        st = self.st
        with st.mu:
            b = bytes(st.recs)
            del st.recs[:]
        if b and self.frames_file is not None:
            try:
                self.frames_file.write(b)
                self.frames_file.flush()
                self.rec_bytes += len(b)
            except (OSError, ValueError):
                pass

    def _partial(self) -> None:
        st = self.st
        with st.mu:
            frames, prog = st.frames, st.progress_ns
        rec = {"stage": self.stage, "frames": frames, "is_kiyo": self.is_kiyo,
               "progress_age_ms": round((qpc() - prog) / 1e6, 1) if prog else None}
        with mf.PARTIAL_LOCK:
            mf.PARTIAL.setdefault("cameras", {})[self.label] = rec

    # ---------------------------------------------------------------- controls
    def _drop_ctl_refs(self) -> None:
        """After a control call timed out: hand the session a fresh, empty interface dict, so close_session does not
        Release the interfaces under the hung call (the abandoned closure keeps the old dict, and its references,
        alive: a deliberate leak, as wincam's abandoned threads)."""
        self.ctl_hung = True
        self.s.ctl = {"cc": None, "pa": None, "ks": None}

    def control(self, item: dict, idx: int) -> dict:
        """One scheduled set while the reader streams: keep the frames around it, read / set / read back in ONE bounded
        call on the camera's own IMFMediaSource interfaces, note the frame indices at the set's start and return."""
        st, c = self.st, self.s.ctl
        d = P.find_ctl(str(item.get("control") or ""))
        rec: dict[str, Any] = {"i": idx, "at_s": float(item["at_s"]), "control": item.get("control"),
                               "request": {k: item.get(k) for k in ("delta", "value", "flags") if k in item}}
        if d is None:
            rec.update(supported=False, reason="unknown control name")
            return rec
        rec["key"] = P.ctl_key(d)
        if (c.get("cc") if d[0] == 0 else c.get("pa")) is None and c.get("ks") is None:
            rec.update(supported=False, reason="no IAMCameraControl / IAMVideoProcAmp / IKsControl on the source")
            return rec
        post = int(self.window["post"])
        wdir = self.dir / f"ctl{idx}_{d[2]}"
        with st.mu:
            pre = list(st.ring)
            s0 = st.frames
            st.capture_dir, st.capture_until = wdir, s0 + post
        for seq, _arr, data in pre:
            if data:
                self.writer.put(wdir / f"f{seq:07d}.jpg", data)
        rec["window"] = {"dir": str(wdir), "pre_seqs": [p[0] for p in pre], "until_seq": s0 + post}
        flags = 1 if str(item.get("flags") or "manual") == "auto" else 2
        start = self.ctl_start
        key = rec["key"]

        def f(ctl):
            out: dict[str, Any] = {}
            before = mf.read_ctl(c, d, False)
            out["before"] = _ctl_brief(before)
            if not before["supported"] or not before["has_value"]:
                out["supported"] = bool(before["supported"])
                return out
            out["supported"] = True
            if key not in start:
                start[key] = (before["via"], before["val"], before["flags"])
            v, why = FR.choose_control_value(item, before, start.get(key))
            out["value_rule"] = why
            if v is None:
                return out
            out["set_value"], out["set_flags"] = v, flags
            out["qpc_set_start_ns"] = qpc()
            hs = mf.set_ctl(c, d, before["via"], v, flags)
            out["qpc_set_return_ns"] = qpc()
            out["hr_set"], out["hr_set_name"] = P.hr_hex(hs), P.hr_name(hs)
            after = mf.read_ctl(c, d, False)
            out["after"] = _ctl_brief(after)
            out["matches"] = (not P.failed(hs)) and after["has_value"] and (
                bool(after["flags"] & 1) if flags & 1 else (after["val"] == v and bool(after["flags"] & 2)))
            return out
        rec["seq_at_set_start"] = s0
        t0 = qpc()
        r = bounded.call(self.timeout_ms, f)
        rec["call_ms"] = (qpc() - t0) / 1e6
        with st.mu:
            rec["seq_at_set_return"] = st.frames
        rec["timed_out"] = r.timed_out
        if r.timed_out:
            self._drop_ctl_refs()
            rec["reason"] = "control call did not return within --timeout-ms (abandoned)"
            return rec
        if r.exc:
            rec["python_exception"] = r.exc[-600:]
        rec.update(r.value or {})
        return rec

    def _restore(self) -> None:
        for key, (via, val, flg) in list(self.ctl_start.items()):
            d = P.find_ctl(key)
            if d is None:
                continue
            t0 = qpc()
            r, hung = mf.restore_one(self.s.ctl, d, via, val, flg, self.timeout_ms)
            r["call_ms"] = (qpc() - t0) / 1e6
            r["ok"] = (not hung and r.get("readback_flags") == flg and
                       (bool(flg & 1) or r.get("readback_value") == val))
            self.restores.append(r)
            if hung:
                self._drop_ctl_refs()
                break

    # ---------------------------------------------------------------- record
    def record(self, sh: Shared, t_session_ns: int, t_stop_ns: int | None) -> dict:
        s, st = self.s, self.st
        err = s.error()
        kind = FR.fault_kind(err, s.unreleasable)
        if not self.done.is_set():
            kind = "unreleasable"
        with st.mu:
            fr = {"total": st.frames, "ok": st.ok_frames, "soi_eoi_ok": st.soi_eoi, "sof0_size_match": st.sof_match,
                  "stream_ticks": st.ticks, "null_samples": st.nulls, "discontinuities": st.discont,
                  "bytes_total": st.bytes, "bytes_min": st.size_min, "bytes_max": st.size_max,
                  "reader_flag_counts": dict(st.flag_counts), "samples_kept": list(st.sample_seqs),
                  "window_frames_kept": st.window_saved}
            first, last, cb = st.first_ns, st.last_ns, st.callback_ns_total
            cb_exc = st.err_exc
        span = (last - first) / 1e9 if fr["total"] > 1 else 0.0
        rel = lambda t: round((t - t_session_ns) / 1e6, 3) if t else None  # noqa: E731
        stopped = self.closed_by == "stop"
        out = {"label": self.label, "device": self.device or None, "url": self.url or None, "is_kiyo": self.is_kiyo,
               "mode": P.mode_str(self.mode["subtype"], self.mode["w"], self.mode["h"], self.mode["fps"]),
               "requested": dict(self.mode), "open_ok": self.open_ok, "closed_by": self.closed_by,
               "stage": self.stage if self.done.is_set() else f"hung in {self.stage}",
               "ok": bool(self.open_ok and self.closed_by in ("stop", "end_of_file") and not s.stage_failed
                          and self.done.is_set()),
               "error": err, "fault_kind": kind, "kiyo_pro_fault": bool(self.is_kiyo and FR.is_kiyo_fault(kind)),
               "unreleasable": bool(s.unreleasable or not self.done.is_set()),
               "negotiated": s.negotiated, "steps": s.steps,
               "timings": {"enumerate_ms": s.enumerate_ms, "activate_ms": s.activate_ms, "reader_ms": s.reader_ms,
                           "settype_ms": s.settype_ms, "first_frame_ms": s.first_frame_ms,
                           "open_to_first_frame_ms": s.open_to_first_ms, "flush_ms": s.flush_ms,
                           "reader_release_ms": s.reader_release_ms, "shutdown_ms": s.shutdown_ms,
                           "shutdown_object_ms": s.shutdown_object_ms, "close_ms": s.close_ms,
                           "open_start_after_session_start_ms": rel(self.t_start_ns),
                           "first_sample_after_session_start_ms": rel(first),
                           "failed_after_session_start_ms": rel(self.t_fail_ns),
                           "close_start_after_session_start_ms": rel(self.close_start_ns),
                           "stop_to_released_ms": (round((self.close_end_ns - t_stop_ns) / 1e6, 3)
                                                   if stopped and t_stop_ns and self.close_end_ns else None)},
               "first_sample_qpc_ns": first or None, "last_sample_qpc_ns": last or None,
               "frames": fr, "duration_s": span, "fps_measured": (fr["total"] - 1) / span if span > 0 else 0.0,
               "callback_s": cb / 1e9, "controls": self.controls, "restore": self.restores,
               "restore_skipped": self.restore_skipped,
               "files": {"frames_bin": str(self.dir / "frames.bin"), "frames_bin_bytes": self.rec_bytes,
                         "samples_dir": str(self.dir / "samples")}}
        if cb_exc:
            out["callback_exception"] = cb_exc
        if self.exc:
            out["thread_exception"] = self.exc
        return out


def _ctl_brief(r: dict) -> dict:
    return {"supported": r.get("supported"), "via": r.get("via") or None, "value": r.get("val") if r.get("has_value")
            else None, "flags": r.get("flags") if r.get("has_value") else None,
            "flags_names": P.flags_names(r.get("flags") or 0) if r.get("has_value") else None,
            "min": r.get("mn"), "max": r.get("mx"), "step": r.get("step"), "default": r.get("def")}


# ============================================================================================================ intruders
def run_cmd(argv: list[str], timeout_s: float) -> dict:
    """A second-opener command with a hard timeout that kills its whole process tree (common.procutil when the suite
    is next to pymf, else Popen + taskkill /T /F)."""
    suite = Path(__file__).resolve().parents[2]
    if str(suite) not in sys.path:
        sys.path.append(str(suite))
    try:
        from common import procutil  # noqa: PLC0415
        r = procutil.run([str(a) for a in argv], timeout_s=timeout_s)
        return {k: r.get(k) for k in ("rc", "stdout", "stderr", "elapsed_s", "timed_out", "killed", "spawn_error")}
    except ImportError:
        pass
    t0 = time.monotonic()
    try:
        p = subprocess.Popen([str(a) for a in argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        return {"rc": None, "stdout": "", "stderr": "", "elapsed_s": 0.0, "timed_out": False, "killed": False,
                "spawn_error": repr(e)}
    try:
        out, err = p.communicate(timeout=timeout_s)
        to = False
    except subprocess.TimeoutExpired:
        to = True
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, timeout=30)
        out, err = p.communicate(timeout=30)
    return {"rc": p.returncode, "stdout": out.decode("utf-8", "replace"), "stderr": err.decode("utf-8", "replace"),
            "elapsed_s": round(time.monotonic() - t0, 3), "timed_out": to, "killed": to, "spawn_error": None}


def _json_of(text: str) -> dict | None:
    t = (text or "").strip()
    if not t:
        return None
    try:
        v = json.loads(t)
        return v if isinstance(v, dict) else None
    except ValueError:
        pass
    i = t.find("{")
    if i >= 0:
        try:
            v = json.loads(t[i:])
            return v if isinstance(v, dict) else None
        except ValueError:
            return None
    return None


def intruder_loop(items: list[dict], sh: Shared, out: list[dict], done: threading.Event) -> None:
    try:
        for it in sorted(items, key=lambda x: float(x.get("at_s", 0))):
            due = sh.t_all_ns + int(float(it.get("at_s", 0)) * 1e9)
            while qpc() < due and not sh.stop.is_set():
                time.sleep(0.02)
            rec: dict[str, Any] = {"label": it.get("label"), "target": it.get("target"), "at_s": it.get("at_s"),
                                   "argv": [str(a) for a in it.get("argv") or []]}
            if qpc() < due:
                rec["skipped"] = "the session stopped before this intruder was due"
                out.append(rec)
                continue
            q0 = qpc()
            rec["utc_started"] = utc_now()
            rec["start_after_t_all_s"] = round((q0 - sh.t_all_ns) / 1e9, 3)
            r = run_cmd(rec["argv"], float(it.get("timeout_s", 40)))
            q1 = qpc()
            rec.update(qpc_start_ns=q0, qpc_end_ns=q1, end_after_t_all_s=round((q1 - sh.t_all_ns) / 1e9, 3),
                       rc=r.get("rc"), elapsed_s=r.get("elapsed_s"), timed_out=r.get("timed_out"),
                       killed=r.get("killed"), spawn_error=r.get("spawn_error"),
                       stderr_tail=(r.get("stderr") or "")[-1500:])
            j = _json_of(r.get("stdout") or "")
            if j is not None and len(json.dumps(j, default=str)) <= 65536:
                rec["stdout_json"] = j
            elif j is not None:
                rec["stdout_json"] = {k: j.get(k) for k in ("tool", "subcommand", "ok", "exit_code", "error",
                                                            "frames", "steps", "devices", "monitor")}
            else:
                rec["stdout_tail"] = (r.get("stdout") or "")[-1500:]
            out.append(rec)
    except BaseException:  # noqa: BLE001
        out.append({"intruder_thread_exception": traceback.format_exc(limit=6)})
    finally:
        done.set()


# ============================================================================================================ session
watchdog_ms = FR.watchdog_ms


def run(spec: dict, out_dir: Path, timeout_ms: int) -> tuple[dict, int]:
    """The whole session. Returns (JSON body without the CLI header, exit code)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seconds = float(spec.get("seconds", 0))
    cam_specs = spec.get("cameras") or []
    labels = [str(c.get("label")) for c in cam_specs]
    j: dict[str, Any] = {"api": "mf", "out_dir": str(out_dir), "seconds_requested": seconds,
                         "timeout_ms": timeout_ms, "spec": spec,
                         "frames_format": {"struct": FR.REC.format, "size": FR.REC.size, "fields": list(FR.FIELDS),
                                           "bits": FR.BITS, "no_time": FR.NO_TIME, "file": "<out_dir>/<label>/frames.bin"},
                         "threading": "one camera thread per camera (open, watch, controls, restore, close; every "
                                      "camera call bounded), samples on MF work-queue threads (ReaderCallback), one "
                                      "JPEG writer thread, one intruder thread"}
    if not cam_specs or len(set(labels)) != len(labels):
        j["error"] = {"class": "usage", "reason": "spec needs cameras with distinct labels"}
        j["ok"] = False
        return j, 2
    writer = Writer()
    writer.start()
    sh = Shared()
    cams = [Cam(c, out_dir, writer, timeout_ms, seconds) for c in cam_specs]
    t_session = qpc()
    j["utc_session_start"] = utc_now()
    for cam in cams:
        cam.thread = threading.Thread(target=cam.main, args=(sh,), name=f"pymf-cam-{cam.label}", daemon=True)
        cam.thread.start()
    mf.set_stage("multi_open")
    # open phase: every camera opens at once; each step is bounded by timeout_ms, first sample likewise
    deadline = t_session + int((8 * timeout_ms + 5000) * 1e6)
    for cam in cams:
        cam.opened.wait(max(0.0, (deadline - qpc()) / 1e9))
    sh.t_all_ns = qpc()
    open_hung = [c.label for c in cams if not c.opened.is_set()]
    mf.set_stage("multi_streaming")
    cu0, ck0 = C.proc_cpu_s()
    intr_out: list[dict] = []
    intr_done = threading.Event()
    items = spec.get("intruders") or []
    intr_cap_s = sum(float(i.get("timeout_s", 40)) for i in items) + 10.0
    if items:
        threading.Thread(target=intruder_loop, args=(items, sh, intr_out, intr_done), name="pymf-intruders",
                         daemon=True).start()
    else:
        intr_done.set()
    tail_s = float(spec.get("tail_s", DEFAULT_TAIL_S))
    timeline: list[dict] = []
    t_tl, cu_tl = sh.t_all_ns, cu0 + ck0
    while True:
        now = qpc()
        el = (now - sh.t_all_ns) / 1e9
        if all(c.done.is_set() for c in cams):
            break
        if el >= seconds and intr_done.is_set():
            last_end = max([r.get("end_after_t_all_s") or 0.0 for r in intr_out] or [0.0])
            if not items or el >= last_end + tail_s:
                break
        if el >= seconds + intr_cap_s:
            break
        if (now - t_tl) / 1e9 >= CPU_TIMELINE_S:
            u, k = C.proc_cpu_s()
            timeline.append({"t_s": round(el, 1), "pct_of_one_core": round(100.0 * ((u + k) - cu_tl) /
                                                                             ((now - t_tl) / 1e9), 2)})
            t_tl, cu_tl = now, u + k
        time.sleep(0.1)
    sh.stop.set()
    t_stop = qpc()
    cu1, ck1 = C.proc_cpu_s()
    mf.set_stage("multi_close")
    n_ctl = max([len(c.ctl_plan) for c in cams] or [0])
    close_deadline = t_stop + int((timeout_ms * (8 + 2 * n_ctl) + 5000) * 1e6)
    for cam in cams:
        cam.done.wait(max(0.0, (close_deadline - qpc()) / 1e9))
    t_released = qpc()
    if items:
        intr_done.wait(max(0.0, (sh.t_all_ns + int((seconds + intr_cap_s) * 1e9) - qpc()) / 1e9))
    writer_ok = writer.stop(10.0)
    win = (t_stop - sh.t_all_ns) / 1e9
    recs = [c.record(sh, t_session, t_stop) for c in cams]
    hung = [c.label for c in cams if not c.done.is_set()]
    j.update({
        "session": {"t_session_start_qpc_ns": t_session, "t_all_qpc_ns": sh.t_all_ns, "t_stop_qpc_ns": t_stop,
                    "open_phase_ms": round((sh.t_all_ns - t_session) / 1e6, 3), "streaming_window_s": round(win, 3),
                    "stop_to_all_released_ms": round((t_released - t_stop) / 1e6, 3) if not hung else None,
                    "open_phase_hung": open_hung},
        "cpu": {"user_s": cu1 - cu0, "kernel_s": ck1 - ck0, "window_s": win,
                "pct_of_one_core": 100.0 * ((cu1 - cu0) + (ck1 - ck0)) / win if win > 0 else None,
                "method": "GetProcessTimes of this process over the streaming window (all cameras, callbacks, "
                          "writer, main loop)", "timeline": timeline,
                "callback_s_total": sum(r["callback_s"] for r in recs)},
        "cameras": recs, "intruders": intr_out, "writer": {**writer.stats(), "stopped": writer_ok},
        "release": {"all_released": not hung and not any(r["unreleasable"] for r in recs),
                    "hung_camera_threads": hung,
                    "max_stop_to_released_ms": max([r["timings"]["stop_to_released_ms"] or 0.0 for r in recs] or [0.0])},
    })
    kf = [r for r in recs if r["kiyo_pro_fault"]]
    j["kiyo_pro_fault"] = ({"label": kf[0]["label"], "kind": kf[0]["fault_kind"], "error": kf[0]["error"],
                            "device": kf[0]["device"],
                            "note": "the session closed the Kiyo Pro's reader at the fault and never re-opened it"}
                           if kf else None)
    failed = [r["label"] for r in recs if not r["ok"]]
    j["failed_cameras"] = failed
    j["ok"] = not failed
    rc = 5 if (hung or any(r["unreleasable"] for r in recs)) else (4 if failed else 0)
    j["error"] = None if rc == 0 else {
        "class": "timeout" if rc == 5 else "camera_failure",
        "reason": (f"unreleasable / hung camera thread: {hung or [r['label'] for r in recs if r['unreleasable']]}"
                   if rc == 5 else f"camera(s) failed: {failed}")}
    return j, rc
