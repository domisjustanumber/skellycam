# /// script
# requires-python = "==3.12.13"
# dependencies = ["av==19.0.2"]
# ///
"""PyAV / FFmpeg DirectShow native-MJPEG capture and open/close cycles for the Windows suite.

The DirectShow half of W-MJPEG, W-CYC, W-MULTI, W-TS and W-CTRL-EFFECT. It mirrors the output schema of
``native/wincam.exe`` (capture -> frames.jsonl + frames.mjpeg + summary.json; cycle -> cycles.jsonl +
summary.json) so the test modules analyse both APIs with the same code.

    uv run --script pyav_ds.py capture --device <DS DevicePath | friendly name> --width 1280 --height 720 --fps 30
        (--frames N | --seconds S) --timeout-ms 5000 --out-dir D [--save none|all|every:K] [--graph-clock]
        [--engine pyav|ffmpeg] [--stop-file F]
    uv run --script pyav_ds.py cycle --device X --width W --height H --fps F --cycles K --frames N
        --timeout-ms T --out D [--alt-width W2 --alt-height H2 --alt-fps F2] [--gap-ms G]

Run it under tools/camlock.py like every camera command. Exit codes follow wincam: 0 ok, 2 usage, 3 device not
found, 4 camera failure (details in the JSON), 5 timeout (a stage did not return; the process exits without
waiting for the stuck FFmpeg call, which the OS then tears down).

How it opens the camera (borrowed from mjpeg/pyav/pyav_capture.py and prior_art/pyav_dshow_probe.py):
- ``av.open("video=@device_pnp_<DevicePath>", format="dshow", options={video_size, framerate, vcodec: mjpeg,
  rtbufsize})``. The ``@device_pnp_`` alternative name is unique even when friendly names collide. A plain
  friendly name is accepted too (``video=<name>``).
- ``vcodec=mjpeg`` is passed (what the ffmpeg CLI would use) but has no effect through PyAV (see below). The
  stream's codec is recorded: anything other than
  ``mjpeg`` is a silent format fallback (``format_fallback``; seen on the Kiyo on 10-25, and on 2026-11-06 on the
  C930e at 640x480@30, its pin's default format, where FFmpeg kept YUY2). ``capture`` treats a fallback as a
  failure (exit 4); ``cycle`` counts the open as ok (the camera streamed) and flags the row.
- PyAV CANNOT force MJPEG: FFmpeg dshow reads the wanted codec from AVFormatContext.video_codec_id, which only the
  ffmpeg CLI's input ``-vcodec`` sets; the ``vcodec`` option passed through PyAV is silently ignored (measured), so
  dshow takes the first caps entry matching size and rate. ``capture --engine ffmpeg`` runs the ffmpeg CLI with
  ``-vcodec mjpeg -c copy`` instead (same demuxer, packets copied) and writes the same files.
- Packets are only demuxed, never decoded (no decoder is opened by this script; FFmpeg's own
  avformat_find_stream_info may decode one frame internally to learn the pixel format).

Timing semantics:
- ``av.open`` returns only after FFmpeg has read at least one packet (avformat_find_stream_info), so the
  open already contains the camera's first frame. ``open_ms`` is the av.open duration. ``first_frame_ms`` is
  the time from the start of av.open to the first packet handed to us, so it equals ``open_to_first_frame_ms``
  (compare with wincam's ``open_to_first_frame_ms``, not its ``first_frame_ms``).
- ``qpc_ns`` is ``time.perf_counter_ns()`` when the packet reached Python (QueryPerformanceCounter based on
  Windows, the same clock as wincam's ``qpc_ns``). Reads block in a worker thread, so arrival times are not
  quantised by polling.
- ``pts`` is the FFmpeg packet pts (DirectShow IMediaSample start time + graph start, 100 ns units), or the
  graph clock at receipt with ``--graph-clock`` (use_video_device_timestamps=0).

Every FFmpeg call runs in a worker thread that owns the container; the main thread waits with the
``--timeout-ms`` bound and records a stage that does not return as ``timed_out``. FFmpeg log lines
(dshow errors such as "Could not run graph") are captured into the JSON.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import socket
import sys
import threading
import time
import datetime as _dt
from pathlib import Path
from typing import Any

SUITE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SUITE_DIR))
from common import jpegcheck  # noqa: E402

TOOL_VERSION = "pyav_ds 1.1 (2026-11-06)"
EXIT_OK, EXIT_USAGE, EXIT_NOT_FOUND, EXIT_CAMERA, EXIT_TIMEOUT = 0, 2, 3, 4, 5


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# --------------------------------------------------------------------------------------------- FFmpeg log capture
class _StderrCapture:
    """FFmpeg's own log goes to fd 2. PyAV's Python log callback takes the GIL inside FFmpeg threads and can
    deadlock the process (seen here: av.open never returned and no Python thread ran), so FFmpeg keeps its
    default C callback and fd 2 is redirected to a temp file that is read back per session and echoed to the real
    stderr at exit."""

    def __init__(self) -> None:
        self.path = None
        self.orig_fd = None
        self._crt = None
        self._crt_orig = -1

    def start(self) -> None:
        import tempfile
        try:
            fd, self.path = tempfile.mkstemp(prefix="pyav_ds_ffmpeg_", suffix=".log")
            sys.stderr.flush()
            self.orig_fd = os.dup(2)
            os.dup2(fd, 2)
            # PyAV's FFmpeg DLLs print through msvcrt.dll, whose fd table is separate from Python's UCRT one:
            # redirect its fd 2 as well (measured: os.dup2 alone captured nothing).
            if sys.platform == "win32":
                try:
                    import ctypes
                    import msvcrt as _pymsvcrt
                    crt = ctypes.CDLL("msvcrt")
                    self._crt = crt
                    self._crt_orig = crt._dup(2)
                    cfd = crt._open_osfhandle(ctypes.c_void_p(_pymsvcrt.get_osfhandle(fd)), 0)
                    crt._dup2(cfd, 2)
                except Exception:
                    self._crt = None
            os.close(fd)
        except Exception:
            self.path = None

    def flush(self, timeout_s: float = 0.5) -> bool:
        """Flush msvcrt's stdio buffers so the lines FFmpeg has printed reach the temp file.

        Root cause of the empty ``ffmpeg_log`` lists (W-MULTI 2026-11-06: 36 of 36 pyav_ds failures; analysis
        multi_topo.md B9): PyAV's FFmpeg DLLs import msvcrt.dll, and msvcrt buffers ``stderr`` once fd 2 is a file,
        so ``since()`` read the file before the C runtime wrote anything (measured: nothing before
        ``msvcrt.fflush(NULL)``, the 'moov atom not found' line right after it; selftest-log checks this). The C
        log callback stays (no GIL in FFmpeg threads). fflush takes the stream locks, so it runs in a helper thread
        with a bound: a stuck FFmpeg call must never block the main thread. Returns False if the flush did not
        return in time."""
        if self._crt is None:
            return True
        done = threading.Event()

        def _f() -> None:
            try:
                self._crt.fflush(None)
            except Exception:
                pass
            done.set()

        threading.Thread(target=_f, daemon=True).start()
        return done.wait(timeout_s)

    def offset(self) -> int:
        self.flush()
        try:
            return os.path.getsize(self.path) if self.path else 0
        except OSError:
            return 0

    def since(self, off: int) -> list[dict]:
        if not self.path:
            return []
        self.flush()
        try:
            with open(self.path, "rb") as f:
                f.seek(off)
                data = f.read(200_000)
        except OSError:
            return []
        lines = [ln.strip() for ln in data.decode("utf-8", "replace").splitlines() if ln.strip()]
        return [{"msg": ln[:400]} for ln in lines[-60:]]

    def stop(self) -> None:
        if self.orig_fd is None:
            return
        try:
            sys.stderr.flush()
            if self._crt is not None:
                self.flush()
                if self._crt_orig >= 0:
                    self._crt._dup2(self._crt_orig, 2)
            text = open(self.path, "rb").read() if self.path else b""
            os.dup2(self.orig_fd, 2)
            os.write(2, text[-200_000:])
            os.unlink(self.path)
        except Exception:
            pass
        self.orig_fd = None


LOGS = _StderrCapture()


def _setup_logging(av_mod) -> None:
    LOGS.start()
    try:
        av_mod.logging.restore_default_callback()
        av_mod.logging.set_libav_level(32)  # AV_LOG_INFO, printed by FFmpeg's C callback (no GIL)
    except Exception:
        pass


# --------------------------------------------------------------------------------------------- helpers
def device_url(dev: str) -> str:
    """'video=@device_pnp_<path>' for a DevicePath, 'video=<name>' for a friendly name, or as given."""
    if dev.startswith("video=") or dev.startswith("audio="):
        return dev
    if dev.startswith("@device_"):
        return "video=" + dev
    if dev.startswith("\\\\?\\") or dev.lower().startswith("\\\\?\\usb") or "#{" in dev:
        return "video=@device_pnp_" + dev
    return "video=" + dev


def fps_text(fps: str) -> str:
    """FFmpeg framerate string. Accepts '30', '7.5', '15/2', '10000000/1333333'."""
    return str(fps).strip()


def fps_value(fps: str) -> float:
    s = str(fps)
    if "/" in s:
        a, b = s.split("/", 1)
        return float(a) / float(b)
    return float(s)


def quick_jpeg(b: bytes) -> dict[str, Any]:
    """Cheap per-frame check (the test modules run the full common.jpegcheck on saved frames)."""
    soi = len(b) >= 2 and b[0] == 0xFF and b[1] == 0xD8
    tail = b[-4096:] if len(b) > 4096 else b
    k = tail.rfind(b"\xff\xd9")
    eoi_trailing = (len(tail) - (k + 2)) if k >= 0 else -1
    eoi = len(b) >= 2 and b[-2:] == b"\xff\xd9"
    sof = jpegcheck.parse_sof0(b[:4096] if len(b) > 4096 else b) if soi else None
    return {"soi": soi, "eoi": eoi, "eoi_trailing_bytes": eoi_trailing,
            "sof0_w": sof["w"] if sof else None, "sof0_h": sof["h"] if sof else None}


def classify_exc(exc: BaseException | None, logs: list[dict]) -> dict[str, Any]:
    """Error dict in wincam's shape: {stage, errno, message, class, reason}. Topology-aware classification
    (bandwidth_probable) is left to common.topology_model.classify_failure in the runner."""
    if exc is None:
        return {}
    eno = getattr(exc, "errno", None)
    msg = f"{type(exc).__name__}: {exc}"
    text = " ".join([msg] + [x["msg"] for x in logs]).lower()
    cls, reason = "other", ""
    if "could not find video device" in text or "could not enumerate" in text and "video" in text:
        cls, reason = "not_found", "FFmpeg dshow did not find the device"
    elif "already in use" in text or "device already in use" in text:
        cls, reason = "in_use", "dshow says the device may be in use by another application"
    elif "could not set video options" in text:
        cls, reason = "other", "the pin rejected the requested format (unsupported mode?)"
    elif eno == 5 or "input/output error" in text:
        cls, reason = "other", ("OSError(5)/EIO from FFmpeg dshow: ambiguous (bandwidth refusal at Run, or a slow "
                                "graph transition); classify with the topology")
    elif eno == 13 or "permission" in text or "access is denied" in text:
        cls, reason = "permission", "access denied"
    return {"errno": eno, "message": msg[:600], "class": cls, "reason": reason}


# --------------------------------------------------------------------------------------------- one open session
class Session:
    """One open -> frames -> close, executed by a worker thread that owns the container.

    Messages to the main thread: ('opened', info) | ('open_error', exc) | ('pkt', t_ns, bytes, pts, tb, dts)
    | ('read_error', exc) | ('closed', close_ms, close_exc). The worker stops by itself after ``max_frames``
    packets or ``max_seconds`` after the first packet, or when ``stop`` is set (checked after each packet)."""

    def __init__(self, av_mod, url: str, opts: dict, timeout_s: float, max_frames: int | None,
                 max_seconds: float | None, stop_file: str | None = None) -> None:
        self.av = av_mod
        self.stop_file = stop_file
        self.stopped_by_file = False
        self.url = url
        self.opts = opts
        self.timeout_s = timeout_s
        self.max_frames = max_frames
        self.max_seconds = max_seconds
        self.q: queue.Queue = queue.Queue()
        self.stop = threading.Event()
        self.t_open_start: int | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.t_open_start = time.perf_counter_ns()
        self.thread.start()

    def _run(self) -> None:
        av = self.av
        c = None
        try:
            c = av.open(self.url, format="dshow", options=self.opts, timeout=(self.timeout_s, self.timeout_s))
        except BaseException as e:  # noqa: BLE001 - every failure is a result
            self.q.put(("open_error", e, time.perf_counter_ns()))
            return
        t_opened = time.perf_counter_ns()
        try:
            s = c.streams.video[0]
            cc = s.codec_context
            info = {"codec": cc.name, "pix_fmt": cc.pix_fmt, "width": cc.width, "height": cc.height,
                    "time_base": str(s.time_base), "average_rate": str(s.average_rate),
                    "t_opened_ns": t_opened}
        except BaseException as e:  # noqa: BLE001
            info = {"stream_error": repr(e), "t_opened_ns": t_opened}
            s = None
        self.q.put(("opened", info, t_opened))
        n = 0
        t_first = None
        read_exc = None
        if s is not None:
            try:
                for pkt in c.demux(s):
                    t = time.perf_counter_ns()
                    if pkt.size == 0:
                        continue
                    if t_first is None:
                        t_first = t
                    tb = pkt.time_base
                    self.q.put(("pkt", t, bytes(pkt), pkt.pts, (tb.numerator, tb.denominator) if tb else None,
                                pkt.dts))
                    n += 1
                    if self.stop.is_set():
                        break
                    if self.max_frames is not None and n >= self.max_frames:
                        break
                    if self.max_seconds is not None and (t - t_first) / 1e9 >= self.max_seconds:
                        break
                    if self.stop_file and (n & 7) == 0 and os.path.exists(self.stop_file):
                        self.stopped_by_file = True
                        break
            except BaseException as e:  # noqa: BLE001
                read_exc = e
        if read_exc is not None:
            self.q.put(("read_error", read_exc, time.perf_counter_ns()))
        self.q.put(("stopping", None, time.perf_counter_ns()))
        t0 = time.perf_counter_ns()
        close_exc = None
        try:
            c.close()
        except BaseException as e:  # noqa: BLE001
            close_exc = e
        self.q.put(("closed", (time.perf_counter_ns() - t0) / 1e6, close_exc))

    def get(self, timeout_s: float):
        try:
            return self.q.get(timeout=timeout_s)
        except queue.Empty:
            return None


def run_session(av_mod, url: str, w: int, h: int, fps: str, timeout_s: float, max_frames: int | None,
                max_seconds: float | None, graph_clock: bool, rtbufsize: str, on_packet=None,
                stop_file: str | None = None) -> dict[str, Any]:
    """Open, stream, close with every stage bounded. Returns a result dict; result['hung'] means a stage did not
    return and the worker thread is stuck (the caller must exit).

    ``open_duration_ms`` is set on EVERY outcome (success, open error, open timeout): the time from the start of
    av.open to its return or to giving up. W-MULTI separates a fast bandwidth refusal (0.5-1.5 s) from a device
    that is not ready (3.7-10.4 s) by this duration (multi_topo.md verifier F5). ``format_fallback`` is True/False
    once the stream opened and None when it never opened (cyc_kiyo.md B6: every row says whether it was MJPEG)."""
    opts = {"video_size": f"{w}x{h}", "framerate": fps_text(fps), "vcodec": "mjpeg", "rtbufsize": rtbufsize}
    if graph_clock:
        opts["use_video_device_timestamps"] = "0"
    sess = Session(av_mod, url, opts, timeout_s, max_frames, max_seconds, stop_file=stop_file)
    r: dict[str, Any] = {"options": opts, "ok": False, "stage_failed": None, "timed_out": False, "hung": False,
                         "unreleasable": False, "frames": 0, "frames_ok": 0, "open_ms": None,
                         "open_duration_ms": None, "first_frame_ms": None, "open_to_first_frame_ms": None,
                         "close_ms": None, "stream": None, "codec": None, "pix_fmt": None, "codec_is_mjpeg": None,
                         "format_fallback": None, "mjpeg_ok": False, "error": None}
    t_start = time.perf_counter_ns()
    log_off = LOGS.offset()
    sess.start()
    # open (includes FFmpeg's stream probing, i.e. at least the first frame)
    m = sess.get(timeout_s + 1.0)
    if m is None:
        dur = (time.perf_counter_ns() - t_start) / 1e6
        r.update(stage_failed="open", timed_out=True, hung=True, unreleasable=True, open_duration_ms=dur,
                 error={"stage": "open", "class": "timeout", "reason": "av.open did not return within the timeout",
                        "open_duration_ms": dur, "ffmpeg_log": LOGS.since(log_off)})
        return r
    kind, payload, t_evt = m
    r["open_ms"] = (t_evt - t_start) / 1e6
    r["open_duration_ms"] = r["open_ms"]
    if kind == "open_error":
        logs = LOGS.since(log_off)
        e = classify_exc(payload, logs)
        e.update(stage="open", open_duration_ms=r["open_ms"], ffmpeg_log=logs[-30:])
        r.update(stage_failed="open", error=e)
        return r
    r["stream"] = payload
    codec = (payload or {}).get("codec")
    r["codec"] = codec
    r["pix_fmt"] = (payload or {}).get("pix_fmt")
    r["codec_is_mjpeg"] = codec == "mjpeg"
    r["format_fallback"] = codec is not None and codec != "mjpeg"
    cpu0 = time.process_time()
    t_first = t_last = None
    stop_sent = False
    deadline_per_pkt = timeout_s
    read_exc = None
    stopping_seen = False
    while True:
        m = sess.get(deadline_per_pkt)
        if m is None:
            stage = "first_frame" if r["frames"] == 0 else "streaming"
            r.update(stage_failed=stage, timed_out=True)
            r["error"] = {"stage": stage, "class": "timeout",
                          "reason": f"no packet for {timeout_s:.1f} s", "ffmpeg_log": LOGS.since(log_off)[-30:]}
            sess.stop.set()
            stop_sent = True
            break
        kind = m[0]
        if kind == "pkt":
            _, t, b, pts, tb, dts = m
            if t_first is None:
                t_first = t
                r["first_frame_ms"] = (t - t_start) / 1e6
                r["open_to_first_frame_ms"] = r["first_frame_ms"]
            t_last = t
            r["frames"] += 1
            chk = quick_jpeg(b)
            if chk["soi"] and chk["eoi_trailing_bytes"] >= 0 and chk["sof0_w"] == w and chk["sof0_h"] == h:
                r["frames_ok"] += 1
            if on_packet is not None:
                on_packet(r["frames"] - 1, t, b, pts, tb, dts, chk)
        elif kind == "read_error":
            read_exc = m[1]
        elif kind == "stopping":
            stopping_seen = True
            break
    r["cpu_s"] = time.process_time() - cpu0
    if t_first is not None and t_last is not None and r["frames"] > 1:
        r["duration_s"] = (t_last - t_first) / 1e9
        r["fps_measured"] = (r["frames"] - 1) / r["duration_s"] if r["duration_s"] > 0 else None
    # close
    m = None
    t_close_wait = time.perf_counter_ns()
    while True:
        m = sess.get(timeout_s + 1.0)
        if m is None or m[0] == "closed":
            break
        if m[0] == "read_error":
            read_exc = m[1]
    if m is None:
        r["unreleasable"] = True
        r["hung"] = True
        r["close_ms"] = (time.perf_counter_ns() - t_close_wait) / 1e6
        if r["error"] is None:
            r["error"] = {"stage": "close", "class": "timeout", "reason": "container.close() did not return"}
        r["stage_failed"] = r["stage_failed"] or "close"
        r["timed_out"] = True
        return r
    r["close_ms"] = m[1]
    if m[2] is not None:
        r["close_error"] = repr(m[2])
    if read_exc is not None and r["error"] is None:
        logs = LOGS.since(log_off)
        e = classify_exc(read_exc, logs)
        e.update(stage="streaming" if r["frames"] else "first_frame", ffmpeg_log=logs[-30:])
        r["error"] = e
        r["stage_failed"] = e["stage"]
    if r["error"] is None and not stop_sent and stopping_seen:
        if r["frames"] == 0:
            r["stage_failed"] = "first_frame"
            r["error"] = {"stage": "first_frame", "class": "other", "reason": "stream ended with zero packets"}
    if r["format_fallback"]:
        r["format_note"] = (f"silent format fallback: stream codec {codec!r}, not mjpeg, although vcodec=mjpeg was "
                            "requested (PyAV cannot set FFmpeg's video_codec_id, so dshow takes the first caps "
                            "entry matching size and rate; use --engine ffmpeg)")
    r["ok"] = r["error"] is None and r["frames"] > 0
    r["mjpeg_ok"] = bool(r["ok"] and r["codec_is_mjpeg"])
    if stop_file:
        r["stopped_by_stop_file"] = sess.stopped_by_file
    return r


# --------------------------------------------------------------------------------------------- subcommands
def parse_save(s: str) -> int:
    """0 = none, 1 = all, K = every K-th frame (frame 0 always saved when saving)."""
    s = (s or "none").lower()
    if s == "none":
        return 0
    if s == "all":
        return 1
    if s.startswith("every:"):
        return max(1, int(s.split(":", 1)[1]))
    raise ValueError(f"bad --save {s!r}")


def header(sub: str, a: argparse.Namespace) -> dict[str, Any]:
    return {"tool": "pyav_ds", "version": TOOL_VERSION, "subcommand": sub, "utc_started": utc_now(),
            "pid": os.getpid(), "argv": sys.argv, "hostname": socket.gethostname(), "timeout_ms": a.timeout_ms,
            "api": "ds", "backend": "pyav-dshow", "device": a.device, "url": device_url(a.device),
            "error": None}


def finish(doc: dict, rc: int, out_file: Path | None, hung: bool) -> None:
    doc["utc_finished"] = utc_now()
    doc["exit_code"] = rc
    text = json.dumps(doc, default=str)
    if out_file is not None:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    sys.stdout.write(text + "\n")
    sys.stdout.flush()
    LOGS.stop()  # echo FFmpeg's log to the real stderr (bounded flush) and remove the temp file
    if hung:
        os._exit(rc)  # a stuck FFmpeg call holds the graph; do not wait for it at interpreter exit
    sys.exit(rc)


#: GetProcessTimes / process_time tick on Windows (15.625 ms): CPU percentages are quantised by tick / window
CPU_TICK_S = 0.015625


def cmd_capture(a: argparse.Namespace, av_mod) -> None:
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    every = parse_save(a.save)
    doc = header("capture", a)
    doc["requested"] = {"subtype": "MJPG", "width": a.width, "height": a.height, "fps": a.fps,
                        "frames": a.frames, "seconds": a.seconds, "save": a.save, "graph_clock": a.graph_clock,
                        "engine": "pyav"}
    fj = (out / "frames.jsonl").open("w", encoding="utf-8", newline="\n")
    fm = (out / "frames.mjpeg").open("wb") if every else None
    counters = {"soi_eoi_ok": 0, "sof0_size_match": 0, "bytes_total": 0, "saved": 0, "pts_none": 0}

    def on_packet(seq, t, b, pts, tb, dts, chk):
        row = {"seq": seq, "qpc_ns": t, "pts": pts, "dts": dts, "time_base": f"{tb[0]}/{tb[1]}" if tb else None,
               "pts_ns": (int(pts * tb[0] * 1_000_000_000 // tb[1]) if (pts is not None and tb) else None),
               "bytes": len(b), **chk, "has_metadata": False}
        counters["bytes_total"] += len(b)
        if chk["soi"] and chk["eoi_trailing_bytes"] >= 0:
            counters["soi_eoi_ok"] += 1
        if chk["sof0_w"] == a.width and chk["sof0_h"] == a.height:
            counters["sof0_size_match"] += 1
        if pts is None:
            counters["pts_none"] += 1
        if fm is not None and seq % every == 0:
            row["mjpeg_offset"] = fm.tell()
            row["mjpeg_len"] = len(b)
            fm.write(b)
            counters["saved"] += 1
        fj.write(json.dumps(row) + "\n")
        fj.flush()

    r = run_session(av_mod, device_url(a.device), a.width, a.height, a.fps, a.timeout_ms / 1000.0,
                    a.frames, a.seconds, a.graph_clock, a.rtbufsize, on_packet,
                    stop_file=getattr(a, "stop_file", None))
    fj.close()
    if fm is not None:
        fm.close()
    win = r.get("duration_s")
    doc.update({"negotiated": r.get("stream"), "codec_is_mjpeg": r.get("codec_is_mjpeg"),
                "timings": {"open_ms": r["open_ms"], "open_duration_ms": r["open_duration_ms"],
                            "first_frame_ms": r["first_frame_ms"],
                            "open_to_first_frame_ms": r["open_to_first_frame_ms"], "close_ms": r["close_ms"]},
                "frames": {"total": r["frames"], "ok": r["frames_ok"], **counters},
                "fps_measured": r.get("fps_measured"), "duration_s": win,
                "cpu": {"process_cpu_s": r.get("cpu_s"),
                        "pct_of_one_core": (100.0 * r["cpu_s"] / win) if win else None,
                        "resolution_pct": (100.0 * CPU_TICK_S / win) if win else None,
                        "method": "time.process_time over the streaming window (whole Python process)"},
                "options": r["options"], "stage_failed": r["stage_failed"], "timed_out": r["timed_out"],
                "unreleasable": r["unreleasable"], "hung": r["hung"], "ok": r["ok"], "error": r["error"],
                "metadata": {"uvc_pts_present": False, "note": "DirectShow via FFmpeg exposes no UVC metadata"},
                "files": {"frames_jsonl": str(out / "frames.jsonl"),
                          "frames_mjpeg": str(out / "frames.mjpeg") if every else None}})
    if r.get("close_error"):
        doc["close_error"] = r["close_error"]
    doc["format_fallback"] = r.get("format_fallback")
    doc["pix_fmt"] = r.get("pix_fmt")
    if getattr(a, "stop_file", None):
        doc["stop_file"] = a.stop_file
        doc["stopped_by_stop_file"] = r.get("stopped_by_stop_file")
    if r.get("format_fallback") and r["ok"]:
        doc["ok"] = False
        doc["stage_failed"] = "format"
        doc["error"] = {"stage": "format", "class": "other", "reason": r.get("format_note")}
    rc = EXIT_OK
    if r["timed_out"] or r["hung"]:
        rc = EXIT_TIMEOUT
    elif r.get("format_fallback"):
        rc = EXIT_CAMERA
    elif not r["ok"]:
        rc = EXIT_NOT_FOUND if (r["error"] or {}).get("class") == "not_found" else EXIT_CAMERA
    finish(doc, rc, out / "summary.json", r["hung"])


# --------------------------------------------------------------------------------------------- FFmpeg CLI engine
def _process_times(p) -> tuple[float | None, float | None]:
    """(user+kernel CPU seconds, lifetime seconds) of an exited child, from GetProcessTimes on its handle."""
    if sys.platform != "win32":
        return None, None
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
        k32.GetProcessTimes.restype = wintypes.BOOL
        c, e, k, u = (ctypes.c_ulonglong() for _ in range(4))
        if not k32.GetProcessTimes(wintypes.HANDLE(int(p._handle)), ctypes.byref(c), ctypes.byref(e),
                                   ctypes.byref(k), ctypes.byref(u)):
            return None, None
        life = (e.value - c.value) / 1e7 if e.value >= c.value else None
        return (k.value + u.value) / 1e7, life
    except Exception:
        return None, None


def _run_with_cpu(argv: list[str], timeout_s: float) -> dict[str, Any]:
    """Run the ffmpeg CLI (a single process, no children) with a timeout and measure its CPU (H8: the ffmpeg
    route had no CPU figure). On timeout the process is killed (TerminateProcess); the whole helper also runs under
    the runner's timed_run tree kill."""
    import subprocess
    out: dict[str, Any] = {"rc": None, "stdout": "", "stderr": "", "timed_out": False, "killed": False,
                           "cpu_s": None, "lifetime_s": None, "spawn_epoch_s": None, "spawn_error": None,
                           "elapsed_ms": None}
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    t0 = time.perf_counter_ns()
    out["spawn_epoch_s"] = time.time()
    try:
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                             creationflags=flags)
    except Exception as e:  # noqa: BLE001
        out["spawn_error"] = f"{type(e).__name__}: {e}"
        return out
    so = se = b""
    try:
        so, se = p.communicate(timeout=max(1.0, timeout_s))
    except subprocess.TimeoutExpired:
        out["timed_out"] = True
        try:
            p.kill()
            out["killed"] = True
        except Exception:
            pass
        try:
            so, se = p.communicate(timeout=10)
        except Exception:  # noqa: BLE001
            pass
    out["elapsed_ms"] = (time.perf_counter_ns() - t0) / 1e6
    out["rc"] = p.poll()
    out["stdout"] = (so or b"").decode("utf-8", "replace")
    out["stderr"] = (se or b"").decode("utf-8", "replace")
    if out["rc"] is not None:
        out["cpu_s"], out["lifetime_s"] = _process_times(p)
    return out


def ffmpeg_session(device: str, w: int, h: int, fps: str, timeout_s: float, frames: int | None,
                   seconds: float | None, rtbufsize: str, out: Path, every: int, write_rows: bool = True
                   ) -> dict[str, Any]:
    """One ffmpeg CLI session: dshow with ``-vcodec mjpeg`` (the guaranteed-MJPEG DirectShow route), packets copied
    (no decode) to an MJPEG stream plus a framecrc list; rows written to ``out/frames.jsonl`` like ``capture``.

    Timings: ``open_to_first_frame_ms`` = first packet's wall clock (the input ``start:`` FFmpeg prints with
    ``-use_wallclock_as_timestamps``) minus the wall clock at spawn, so it INCLUDES the ffmpeg process start (about
    0.1 s more than PyAV's figure). ``open_duration_ms`` on an open failure = the process run time. CPU: ffmpeg's own
    user+kernel time (GetProcessTimes) over its lifetime (includes probe and close)."""
    import re
    import shutil
    out.mkdir(parents=True, exist_ok=True)
    r: dict[str, Any] = {"engine": "ffmpeg", "ok": False, "mjpeg_ok": False, "codec": None, "pix_fmt": None,
                         "codec_is_mjpeg": None, "format_fallback": None, "frames": 0, "frames_ok": 0,
                         "rows": [], "fps_measured": None, "duration_s": None, "error": None,
                         "stage_failed": None, "timed_out": False, "hung": False, "unreleasable": False,
                         "open_ms": None, "open_duration_ms": None, "first_frame_ms": None,
                         "open_to_first_frame_ms": None, "close_ms": None, "process_ms": None, "argv": None,
                         "cpu": {"pct_of_one_core": None, "process_cpu_s": None, "lifetime_s": None,
                                 "resolution_pct": None,
                                 "method": "GetProcessTimes(ffmpeg.exe) user+kernel over the process lifetime "
                                           "(includes process start, open/probe, close, and the harness's own "
                                           "framecrc checksums and two output files, so an upper bound for "
                                           "the dshow path)"}}
    exe = shutil.which("ffmpeg")
    if not exe:
        r.update(stage_failed="spawn", error={"stage": "spawn", "class": "other", "reason": "ffmpeg CLI not on PATH"})
        return r
    allf = out / "_all.mjpeg"
    crc = out / "framecrc.txt"
    # -use_wallclock_as_timestamps: pts = wall clock when FFmpeg reads each packet (arrival). The DirectShow sample
    # times are perfectly even (measured: interval std 0 on the C930e), so they cannot show the real frame rate.
    argv = [exe, "-hide_banner", "-nostats", "-y", "-f", "dshow", "-use_wallclock_as_timestamps", "1",
            "-rtbufsize", rtbufsize, "-vcodec", "mjpeg",
            "-video_size", f"{w}x{h}", "-framerate", fps_text(fps), "-i", device_url(device)]
    lim = ["-frames:v", str(frames)] if frames else ["-t", str(seconds)]
    argv += ["-map", "0:v"] + lim + ["-c", "copy", "-f", "mjpeg", str(allf)]
    argv += ["-map", "0:v"] + lim + ["-c", "copy", "-f", "framecrc", str(crc)]
    r["argv"] = argv
    dur = (seconds or 0) + (frames or 0) / max(1.0, fps_value(fps))
    pr = _run_with_cpu(argv, timeout_s=dur + 3 * timeout_s + 5)
    r["process_ms"] = pr["elapsed_ms"]
    se = pr.get("stderr") or ""
    if pr.get("spawn_error"):
        r.update(stage_failed="spawn", error={"stage": "spawn", "class": "other", "reason": pr["spawn_error"]})
        return r
    codec, pix = parse_ffmpeg_stream(se)
    r["codec"], r["pix_fmt"] = codec, pix
    r["codec_is_mjpeg"] = (codec == "mjpeg") if codec else None
    r["format_fallback"] = (codec != "mjpeg") if codec else None
    start = parse_ffmpeg_start(se)
    if start is not None and pr.get("spawn_epoch_s"):
        dt = (start - pr["spawn_epoch_s"]) * 1000.0
        if -1000.0 < dt < 120000.0:
            r["open_to_first_frame_ms"] = r["first_frame_ms"] = dt
    sizes, ptss, tb = [], [], None
    try:
        for line in crc.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("#tb"):
                mm = re.search(r"(\d+)/(\d+)", line)
                if mm:
                    tb = (int(mm.group(1)), int(mm.group(2)))
                continue
            if line.startswith("#") or not line.strip():
                continue
            parts = [x.strip() for x in line.split(",")]
            if len(parts) >= 5:
                ptss.append(int(parts[2]))
                sizes.append(int(parts[4]))
    except OSError:
        pass
    data = allf.read_bytes() if allf.exists() else b""
    rows, off = [], 0
    fm = (out / "frames.mjpeg").open("wb") if every else None
    counters = {"soi_eoi_ok": 0, "sof0_size_match": 0, "bytes_total": 0, "saved": 0}
    fj = (out / "frames.jsonl").open("w", encoding="utf-8", newline="\n") if write_rows else None
    try:
        for i, (n, pts) in enumerate(zip(sizes, ptss)):
            b = data[off:off + n]
            off += n
            chk = quick_jpeg(b)
            row = {"seq": i, "qpc_ns": None, "pts": pts, "time_base": f"{tb[0]}/{tb[1]}" if tb else None,
                   "pts_ns": int(pts * tb[0] * 1_000_000_000 // tb[1]) if tb else None, "bytes": len(b), **chk,
                   "has_metadata": False}
            counters["bytes_total"] += len(b)
            if chk["soi"] and chk["eoi_trailing_bytes"] >= 0:
                counters["soi_eoi_ok"] += 1
                if chk["sof0_w"] == w and chk["sof0_h"] == h:
                    r["frames_ok"] += 1
            if chk["sof0_w"] == w and chk["sof0_h"] == h:
                counters["sof0_size_match"] += 1
            if fm is not None and i % every == 0:
                row["mjpeg_offset"] = fm.tell()
                row["mjpeg_len"] = len(b)
                fm.write(b)
                counters["saved"] += 1
            if fj is not None:
                fj.write(json.dumps(row) + "\n")
            rows.append(row)
    finally:
        if fm is not None:
            fm.close()
        if fj is not None:
            fj.close()
    try:
        allf.unlink()
    except OSError:
        pass
    n = len(rows)
    r["rows"], r["frames"], r["counters"] = rows, n, counters
    if n > 2 and tb and rows[0]["pts_ns"] is not None and rows[-1]["pts_ns"] > rows[0]["pts_ns"]:
        r["duration_s"] = (rows[-1]["pts_ns"] - rows[0]["pts_ns"]) / 1e9
        r["fps_measured"] = (n - 1) / r["duration_s"]
    if pr.get("cpu_s") is not None and pr.get("lifetime_s"):
        r["cpu"].update(process_cpu_s=pr["cpu_s"], lifetime_s=pr["lifetime_s"],
                        pct_of_one_core=100.0 * pr["cpu_s"] / pr["lifetime_s"],
                        resolution_pct=100.0 * CPU_TICK_S / pr["lifetime_s"])
    r["timed_out"] = bool(pr.get("timed_out"))
    r["hung"] = r["unreleasable"] = pr.get("rc") is None  # ffmpeg.exe could not even be killed
    r["ok"] = (pr.get("rc") == 0 and not r["timed_out"] and n > 0 and codec == "mjpeg")
    r["mjpeg_ok"] = r["ok"]
    if not r["ok"]:
        tail = [ln for ln in se.splitlines() if ln.strip()][-12:]
        eno = 5 if ("I/O error" in se or "Input/output error" in se) else None
        cls = "timeout" if r["timed_out"] else ("not_found" if "Could not find video device" in se else "other")
        stage = "open" if n == 0 else "streaming"
        r["error"] = {"stage": stage, "errno": eno, "class": cls,
                      "reason": ("ffmpeg timed out" if r["timed_out"] else f"ffmpeg rc={pr.get('rc')} codec={codec}"),
                      "ffmpeg_log": [{"msg": x[:300]} for x in tail]}
        if n == 0:
            r["open_duration_ms"] = r["error"]["open_duration_ms"] = pr["elapsed_ms"]
        r["stage_failed"] = stage
    return r


def parse_ffmpeg_stream(stderr_text: str) -> tuple[str | None, str | None]:
    """(codec, pix_fmt) of input stream #0:0 from the ffmpeg CLI banner, e.g. 'Video: mjpeg (Baseline) (MJPG /
    0x47504A4D), yuvj422p(pc, ...), 1280x720' -> ('mjpeg', 'yuvj422p'); 'Video: rawvideo (YUY2 / 0x32595559),
    yuyv422, 640x480' -> ('rawvideo', 'yuyv422')."""
    import re
    m = re.search(r"Stream #0:0[^\n]*?Video: (\w+)([^\n]*)", stderr_text or "")
    if not m:
        return None, None
    rest = m.group(2)
    # drop the parenthesised profile/fourcc groups that precede the pixel format
    depth, buf = 0, []
    for ch in rest:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            buf.append(ch)
    parts = [x.strip() for x in "".join(buf).split(",") if x.strip()]
    pix = parts[0] if parts and re.fullmatch(r"[a-z0-9_]+", parts[0]) else None
    return m.group(1), pix


def parse_ffmpeg_start(stderr_text: str) -> float | None:
    """The input's ``start:`` seconds (first packet's timestamp; the wall clock with use_wallclock_as_timestamps)."""
    import re
    m = re.search(r"Input #0, dshow[^\n]*\n(?:[^\n]*\n){0,3}?\s*Duration:[^\n]*?start:\s*([0-9.]+)",
                  stderr_text or "")
    return float(m.group(1)) if m else None


def cmd_capture_ffmpeg_cli(a: argparse.Namespace) -> None:
    """``--engine ffmpeg``: the same DirectShow demuxer through the FFmpeg command-line tool, which CAN request MJPEG.

    PyAV cannot: FFmpeg's dshow demuxer takes the wanted codec from AVFormatContext.video_codec_id, which only the
    ffmpeg CLI's input ``-vcodec`` sets (PyAV exposes no way to set it before avformat_open_input, and no AVOption
    reaches it). Without it dshow takes the FIRST caps entry matching size and rate, so PyAV gets YUY2/NV12 whenever
    the camera offers a raw format at that size and rate (measured 2026-11-06: Kiyo at every size, C930e 160x120 and
    640x480@30, C922 160x90; W-MJPEG: 95 of 120 C922 and 96 of 119 C930e modes). Output here: packets copied (no
    decode) to an MJPEG stream plus a framecrc list (pts, size per packet), split into frames.jsonl rows with the
    same fields (``qpc_ns`` is null: the CLI gives no QPC; ``pts_ns`` is the wall clock when FFmpeg read the packet,
    rebased to the first packet)."""
    out = Path(a.out_dir)
    every = parse_save(a.save)
    doc = header("capture", a)
    doc["backend"] = "ffmpeg-cli-dshow"
    doc["requested"] = {"subtype": "MJPG", "width": a.width, "height": a.height, "fps": a.fps,
                        "frames": a.frames, "seconds": a.seconds, "save": a.save, "engine": "ffmpeg"}
    r = ffmpeg_session(a.device, a.width, a.height, a.fps, a.timeout_ms / 1000.0, a.frames, a.seconds,
                       a.rtbufsize, out, every)
    c = r.get("counters") or {"soi_eoi_ok": 0, "sof0_size_match": 0, "bytes_total": 0, "saved": 0}
    doc.update({"negotiated": {"codec": r["codec"], "pix_fmt": r["pix_fmt"], "width": a.width, "height": a.height},
                "codec_is_mjpeg": r["codec_is_mjpeg"], "format_fallback": r["format_fallback"],
                "pix_fmt": r["pix_fmt"],
                "timings": {"process_ms": r["process_ms"], "open_ms": None, "open_duration_ms": r["open_duration_ms"],
                            "first_frame_ms": r["first_frame_ms"],
                            "open_to_first_frame_ms": r["open_to_first_frame_ms"], "close_ms": None,
                            "note": "open_to_first_frame_ms includes the ffmpeg process start"},
                "frames": {"total": r["frames"], "ok": r["frames_ok"], **c},
                "fps_measured": r["fps_measured"],
                "fps_basis": "packet pts = wall clock at demux (use_wallclock_as_timestamps)",
                "duration_s": r["duration_s"], "cpu": r["cpu"],
                "stage_failed": r["stage_failed"], "timed_out": r["timed_out"], "unreleasable": r["unreleasable"],
                "hung": r["hung"], "ok": r["ok"], "error": r["error"], "ffmpeg_argv": r["argv"],
                "metadata": {"uvc_pts_present": False},
                "files": {"frames_jsonl": str(out / "frames.jsonl"),
                          "frames_mjpeg": str(out / "frames.mjpeg") if every else None}})
    rc = EXIT_OK if r["ok"] else (EXIT_TIMEOUT if r["timed_out"] else
                                  (EXIT_NOT_FOUND if (r["error"] or {}).get("class") == "not_found" else EXIT_CAMERA))
    finish(doc, rc, out / "summary.json", False)


def cmd_cycle(a: argparse.Namespace, av_mod) -> None:
    """Open/close cycles. Every row records the negotiated codec, ``format_fallback`` (True/False, None when the
    stream never opened) and ``mjpeg_ok`` (streamed AND MJPEG). ``ok`` keeps its meaning (opened and streamed) so
    W-CYC's open/close statistics are unchanged; a "negotiated MJPEG" criterion must use ``mjpeg_ok`` /
    ``summary.ok_mjpeg`` (cyc_kiyo.md B6). ``--engine ffmpeg`` cycles the ffmpeg CLI with ``-vcodec mjpeg`` (the
    guaranteed-MJPEG DirectShow route; one process per cycle, so open times include the process start)."""
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    doc = header("cycle", a)
    engine = getattr(a, "engine", "pyav") or "pyav"
    if engine == "ffmpeg":
        doc["backend"] = "ffmpeg-cli-dshow"
    modes = [(a.width, a.height, a.fps)]
    if a.alt_width and a.alt_height:
        modes.append((a.alt_width, a.alt_height, a.alt_fps or a.fps))
    doc["requested"] = {"mode": f"MJPG {a.width}x{a.height}@{a.fps}",
                        "alt_mode": (f"MJPG {modes[1][0]}x{modes[1][1]}@{modes[1][2]}" if len(modes) > 1 else None),
                        "cycles": a.cycles, "frames_per_cycle": a.frames, "gap_ms": a.gap_ms, "engine": engine}
    cj = (out / "cycles.jsonl").open("w", encoding="utf-8", newline="\n")
    rows = []
    hung = False
    for i in range(a.cycles):
        w, h, f = modes[i % len(modes)]
        t_utc = utc_now()
        if engine == "ffmpeg":
            r = ffmpeg_session(a.device, w, h, f, a.timeout_ms / 1000.0, a.frames, None, a.rtbufsize,
                               out / "_cycle_tmp", 0, write_rows=False)
        else:
            r = run_session(av_mod, device_url(a.device), w, h, f, a.timeout_ms / 1000.0, a.frames, None,
                            False, a.rtbufsize)
        err = r["error"] or {}
        row = {"i": i, "mode": f"MJPG {w}x{h}@{f}", "engine": engine, "ok": r["ok"],
               "mjpeg_ok": bool(r.get("mjpeg_ok")), "stage_failed": r["stage_failed"],
               "errno": err.get("errno"), "error": err.get("message") or err.get("reason"),
               "error_class": err.get("class"), "timed_out": r["timed_out"], "open_ms": r["open_ms"],
               "open_duration_ms": r.get("open_duration_ms"),
               "first_frame_ms": r["first_frame_ms"], "open_to_first_frame_ms": r["open_to_first_frame_ms"],
               "frames": r["frames"], "frames_ok": r["frames_ok"], "close_ms": r["close_ms"],
               "process_ms": r.get("process_ms"),
               "codec": r.get("codec"), "pix_fmt": r.get("pix_fmt"), "format_fallback": r.get("format_fallback"),
               "fps_measured": r.get("fps_measured"),
               "unreleasable": r["unreleasable"], "in_use_by_other": None, "utc": t_utc,
               "ffmpeg_log": err.get("ffmpeg_log", [])[-8:] if err else []}
        rows.append(row)
        cj.write(json.dumps(row, default=str) + "\n")
        cj.flush()
        if r["hung"]:
            hung = True
            break
        if a.gap_ms and i + 1 < a.cycles:
            time.sleep(a.gap_ms / 1000.0)
    cj.close()
    if engine == "ffmpeg":
        import shutil
        shutil.rmtree(out / "_cycle_tmp", ignore_errors=True)
    ok = sum(1 for r in rows if r["ok"])
    ok_mjpeg = sum(1 for r in rows if r["mjpeg_ok"])
    ff = sorted(r["open_to_first_frame_ms"] for r in rows if r["ok"] and r["open_to_first_frame_ms"] is not None)
    doc["summary"] = {"cycles_requested": a.cycles, "cycles_run": len(rows), "ok": ok, "failed": len(rows) - ok,
                      "ok_mjpeg": ok_mjpeg, "mjpeg_success_rate": ok_mjpeg / len(rows) if rows else None,
                      "timeouts": sum(1 for r in rows if r["timed_out"]),
                      "success_rate": ok / len(rows) if rows else None,
                      "open_to_first_frame_ms_p50": ff[len(ff) // 2] if ff else None,
                      "open_to_first_frame_ms_max": ff[-1] if ff else None,
                      "first_frame_within_2s": sum(1 for x in ff if x <= 2000.0),
                      "format_fallbacks": sum(1 for r in rows if r.get("format_fallback")),
                      "format_fallback_modes": sorted({r["mode"] for r in rows if r.get("format_fallback")}),
                      "engine": engine, "unreleasable": hung, "stopped_early": len(rows) < a.cycles}
    doc["files"] = {"cycles_jsonl": str(out / "cycles.jsonl")}
    rc = EXIT_TIMEOUT if hung else (EXIT_OK if ok == len(rows) else EXIT_CAMERA)
    finish(doc, rc, out / "summary.json", hung)


def cmd_selftest_log(av_mod, timeout_s: float = 10.0) -> None:
    """No camera: open a truncated MP4 through the same worker-thread pattern and check that FFmpeg's log line
    ('moov atom not found') reaches the captured log. Exit 0 when captured, 4 when not (B9 self-test)."""
    import tempfile
    doc: dict[str, Any] = {"tool": "pyav_ds", "version": TOOL_VERSION, "subcommand": "selftest-log",
                           "utc_started": utc_now(), "av_version": getattr(av_mod, "__version__", None),
                           "msvcrt_redirect": LOGS._crt is not None}
    fd, p = tempfile.mkstemp(prefix="pyav_ds_selftest_", suffix=".mp4")
    os.write(fd, b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")
    os.close(fd)
    off = LOGS.offset()
    res: dict[str, Any] = {}

    def work() -> None:
        try:
            av_mod.open(p)
            res["exc"] = None
        except BaseException as e:  # noqa: BLE001
            res["exc"] = repr(e)

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout_s)
    logs = LOGS.since(off)
    try:
        os.unlink(p)
    except OSError:
        pass
    doc.update({"open_returned": not t.is_alive(), "open_exception": res.get("exc"), "captured": logs,
                "ok": any("moov atom not found" in x["msg"] for x in logs)})
    finish(doc, EXIT_OK if doc["ok"] else EXIT_CAMERA, None, t.is_alive())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest-log", help="no camera: check that FFmpeg log lines are captured")
    for name in ("capture", "cycle"):
        p = sub.add_parser(name)
        p.add_argument("--device", required=True, help="DirectShow DevicePath (\\\\?\\usb#...) or friendly name")
        p.add_argument("--width", type=int, required=True)
        p.add_argument("--height", type=int, required=True)
        p.add_argument("--fps", required=True, help="30, 7.5, 15/2 or 10000000/1333333")
        p.add_argument("--timeout-ms", type=int, default=5000)
        p.add_argument("--rtbufsize", default="256M")
        p.add_argument("--engine", choices=["pyav", "ffmpeg"], default="pyav",
                       help="pyav (default) or the ffmpeg CLI, which can force MJPEG with -vcodec mjpeg")
        if name == "capture":
            g = p.add_mutually_exclusive_group(required=True)
            g.add_argument("--frames", type=int)
            g.add_argument("--seconds", type=float)
            p.add_argument("--out-dir", required=True)
            p.add_argument("--save", default="none")
            p.add_argument("--stop-file", dest="stop_file", default=None,
                           help="stop cleanly (normal close) as soon as this file exists (pyav engine; W-FMT-NOGRAB)")
            p.add_argument("--graph-clock", action="store_true",
                           help="use_video_device_timestamps=0 (pts = graph clock at receipt)")
        else:
            p.add_argument("--cycles", type=int, required=True)
            p.add_argument("--frames", type=int, default=30)
            p.add_argument("--out", required=True)
            p.add_argument("--alt-width", type=int)
            p.add_argument("--alt-height", type=int)
            p.add_argument("--alt-fps")
            p.add_argument("--gap-ms", type=int, default=0)
    try:
        a = ap.parse_args()
    except SystemExit as e:
        sys.exit(EXIT_USAGE if e.code not in (0, None) else 0)
    try:
        import av as av_mod  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"tool": "pyav_ds", "error": {"stage": "import", "message": repr(e), "class": "other"}}))
        sys.exit(EXIT_CAMERA)
    _setup_logging(av_mod)
    if a.cmd == "selftest-log":
        cmd_selftest_log(av_mod)
    elif a.cmd == "capture" and a.engine == "ffmpeg":
        cmd_capture_ffmpeg_cli(a)
    elif a.cmd == "capture":
        cmd_capture(a, av_mod)
    else:
        cmd_cycle(a, av_mod)


if __name__ == "__main__":
    main()
