"""Bounded calls: run a blocking camera call on a worker thread and wait for it with a deadline (wincam ``timed()``).

A call that does not return in time is recorded as ``timed_out``; its thread is abandoned (daemon thread) and
``ABANDONED`` is incremented. The abandoned thread keeps alive only what its closure references itself: a closure
that calls a COM object must take its OWN reference first (``mf.ref``, wincam's by-value ComPtr capture) and release
it when the call returns, because ``com.release`` NULLs the caller's shared wrapper in place and the caller's later
cleanup (close_session, a dropped device list) would otherwise free the object under the hung call. A process with an abandoned thread must not run MFShutdown /
CoUninitialize or interpreter finalisation (they can block on the hung object), so the CLI ends such a process with
``os._exit`` (cli.finish), exactly where wincam calls TerminateProcess.

ctypes releases the GIL around every foreign call, so a COM call blocked inside a driver never blocks the waiting
thread. Each worker joins the MTA first (wincam's helper threads do the same).
"""
from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from . import com

ABANDONED = 0
_lock = threading.Lock()


@dataclass
class CallCtl:
    """Passed to the bounded function; ``abandoned`` turns True when the caller gave up waiting (the function may
    check it after a slow call to clean up after itself, e.g. shut down a source it activated too late)."""
    abandoned: bool = False


@dataclass
class Timed:
    timed_out: bool = False
    ms: float = 0.0
    value: Any = None
    exc: str | None = None            # an exception raised inside the call (traceback text), None normally
    ctl: CallCtl = field(default_factory=CallCtl)


def abandoned_threads() -> int:
    with _lock:
        return ABANDONED


def call(timeout_ms: float, fn: Callable[[CallCtl], Any]) -> Timed:
    """Run ``fn(ctl)`` on a fresh MTA thread; wait at most ``timeout_ms``. Never raises."""
    global ABANDONED
    t = Timed()
    done = threading.Event()
    box: dict = {}
    mu = threading.Lock()

    def worker() -> None:
        ci = com.coinit_mta()
        v, exc = None, None
        try:
            v = fn(t.ctl)
        except BaseException:  # noqa: BLE001 - recorded, never propagated into the MF thread pool
            exc = traceback.format_exc(limit=6)
        with mu:
            if t.ctl.abandoned:
                v = None          # drop COM references here, on the worker, as wincam does
            else:
                box["v"], box["exc"] = v, exc
        v = None
        done.set()
        if ci in (0, 1):
            com.CoUninitialize()

    t0 = time.perf_counter_ns()
    th = threading.Thread(target=worker, name="pymf-bounded", daemon=True)
    th.start()
    ok = done.wait(max(0.0, timeout_ms) / 1000.0)
    t.ms = (time.perf_counter_ns() - t0) / 1e6
    with mu:
        if not ok and "v" not in box and "exc" not in box:
            t.ctl.abandoned = True
            t.timed_out = True
            with _lock:
                ABANDONED += 1
            return t
        t.value, t.exc = box.get("v"), box.get("exc")
    return t
