"""Shared plumbing for the macOS suite's child processes (stdlib only).

Every camera call runs in a child process. The runner kills the child (procutil) when its outer timeout passes;
in addition each child arms its own deadline here, so a hang in a blocking framework call (startRunning, an IOKit
request without a timeout) still ends with a JSON line on stdout saying what was in progress (exit code 5).

Exit codes (same as wincam): 0 ok, 2 usage, 3 device not found, 4 camera failure (details in JSON), 5 timeout.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from typing import Any, Callable

EXIT_OK, EXIT_USAGE, EXIT_NOT_FOUND, EXIT_CAMERA, EXIT_TIMEOUT = 0, 2, 3, 4, 5

_print_lock = threading.Lock()
_emitted = False


def _json_default(o: Any):
    if isinstance(o, (bytes, bytearray)):
        return {"bytes_len": len(o), "head_hex": bytes(o[:32]).hex()}
    try:
        return int(o)
    except Exception:
        pass
    try:
        return float(o)
    except Exception:
        return str(o)


def emit(obj: dict) -> None:
    """Print the single result JSON object (one line) exactly once."""
    global _emitted
    with _print_lock:
        if _emitted:
            return
        _emitted = True
        sys.stdout.write(json.dumps(obj, default=_json_default) + "\n")
        sys.stdout.flush()


class Deadline:
    """Hard deadline: after ``seconds`` print ``partial()`` (+ timed_out) and os._exit(5)."""

    def __init__(self, seconds: float, partial: Callable[[], dict]):
        self.seconds = float(seconds)
        self.partial = partial
        self._t = threading.Timer(self.seconds, self._fire)
        self._t.daemon = True

    def start(self) -> "Deadline":
        if self.seconds > 0:
            self._t.start()
        return self

    def cancel(self) -> None:
        self._t.cancel()

    def _fire(self) -> None:
        try:
            p = dict(self.partial() or {})
        except Exception as e:  # never let the watchdog die silently
            p = {"partial_error": repr(e)}
        p.update(ok=False, timed_out=True, error_class="timeout", exit_code=EXIT_TIMEOUT,
                 error=p.get("error") or f"child deadline of {self.seconds:.0f} s passed (in progress: "
                                            f"{p.get('in_progress')})")
        emit(p)
        os._exit(EXIT_TIMEOUT)


# --------------------------------------------------------------------------------------------- clocks
class _TB(ctypes.Structure):
    _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]


_mach = None
_tb = None
if sys.platform == "darwin":
    try:
        _mach = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        _mach.mach_absolute_time.restype = ctypes.c_uint64
        _mach.mach_timebase_info.argtypes = [ctypes.POINTER(_TB)]
        _tb = _TB()
        _mach.mach_timebase_info(ctypes.byref(_tb))
    except OSError:
        _mach = None


def mach_ns() -> int:
    """mach_absolute_time in ns (the host-time clock that CMClockGetHostTimeClock is built on). On other OSes,
    time.monotonic_ns (tests only)."""
    if _mach is not None and _tb is not None and _tb.denom:
        return _mach.mach_absolute_time() * _tb.numer // _tb.denom
    return time.monotonic_ns()


def mach_timebase() -> tuple[int, int] | None:
    return (_tb.numer, _tb.denom) if _tb is not None else None


def touch(path: str | os.PathLike | None, payload: dict | None = None) -> None:
    """Write a small JSON marker file (atomic rename), used for hold / ready / stop handshakes with the runner."""
    if not path:
        return
    p = os.fspath(path)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload or {}, f, default=_json_default)
    os.replace(tmp, p)


def hold(hold_ms: float, marker: str | None = None, release: str | None = None, cap_ms: float | None = None,
         idle: Callable[[float], None] | None = None, info: dict | None = None) -> dict:
    """Keep whatever the caller holds (an AVCaptureDevice, an IOKit plug-in) for at least ``hold_ms``, so the runner
    can sample the granted alt and try a third-process open meanwhile (M-FMT-NOGRAB).

    Writes ``marker`` ({mach_ns, pid, hold_ms}) when the hold starts. Ends when hold_ms has passed AND (no
    ``release`` file given, or it exists), or when ``cap_ms`` (default hold_ms + 60 s) passes. ``idle(seconds)``
    replaces time.sleep (e.g. a run-loop pump). Returns {hold_start_mach_ns, hold_end_mach_ns, held_ms,
    released_by: timer|release_file|cap}."""
    hold_ms = max(0.0, float(hold_ms or 0))
    cap_ms = float(cap_ms) if cap_ms else hold_ms + 60_000.0
    t0 = mach_ns()
    touch(marker, {"mach_ns": t0, "pid": os.getpid(), "hold_ms": hold_ms, **(info or {})})
    wait = idle or time.sleep
    released_by = "timer"
    while True:
        el = (mach_ns() - t0) / 1e6
        if el >= cap_ms:
            released_by = "cap"
            break
        if el >= hold_ms:
            if not release:
                break
            if os.path.exists(release):
                released_by = "release_file"
                break
        wait(0.02)
    t1 = mach_ns()
    return {"hold_start_mach_ns": t0, "hold_end_mach_ns": t1, "held_ms": round((t1 - t0) / 1e6, 1),
            "released_by": released_by, "hold_ms_requested": hold_ms}


def parse_kv_list(text: str | None) -> list[tuple[str, int]]:
    """'a=1,b=-2' -> [('a', 1), ('b', -2)]"""
    out = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        out.append((k.strip(), int(v.strip(), 0)))
    return out


def parse_schedule(text: str | None) -> list[dict]:
    """'2000:ep0:exposure_time_absolute=100;4000:avf:exposure=locked' -> [{'t_ms', 'kind', 'name', 'value'}].
    Kinds: ep0 (UVC SET_CUR + readback), avf (AVFoundation mode), probe (ioreg_alt | ep0_getif | ep0_commit),
    mark (a label only)."""
    out = []
    for part in (text or "").split(";"):
        part = part.strip()
        if not part:
            continue
        t, _, rest = part.partition(":")
        kind, _, spec = rest.partition(":")
        name, _, value = spec.partition("=")
        out.append({"t_ms": float(t), "kind": kind.strip(), "name": name.strip(),
                    "value": value.strip() if value != "" else None})
    return sorted(out, key=lambda e: e["t_ms"])
