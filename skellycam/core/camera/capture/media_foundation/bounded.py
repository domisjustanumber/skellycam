"""Bounded calls (specs/windows-capture.md, section 6.6; ported from the prototype `pymf/bounded.py`).

A call runs on a new thread. The caller waits at most the limit. A call that does not return in
time is a hang: its thread stays (a daemon thread), `abandoned()` counts it, and the caller gets
`CaptureFailure(..., hung=True)`. ctypes releases the GIL in each foreign call, so a call that hangs
in a driver does not block the caller.

A function that calls a COM object must use its own reference (`com.ref`) and release it when it
returns. Then a hung call never uses an object that the caller released.
"""

import threading

from skellycam.core.camera.capture.media_foundation import com
from skellycam.core.camera.capture.source import BOUNDED_CALL_LIMIT_S, CaptureFailure

_abandoned = 0
_lock = threading.Lock()


def abandoned() -> int:
    """The count of calls that did not return in time. MFShutdown is allowed only at 0 (6.1)."""
    return _abandoned


def call(stage: str, what: str, function, on_late=None):
    """Return `function()`, or raise its exception, or raise a hung `CaptureFailure` after the limit.

    `on_late(value)` runs on the worker when `function` returns after the caller gave up, for
    example to shut down a source that came too late (6.2 step 3).
    """
    global _abandoned
    done = threading.Event()
    box = {}
    state = threading.Lock()

    def worker():
        joined = com.coinit_mta()  # each worker joins the MTA first (agent 43)
        try:
            try:
                result = ("value", function())
            except BaseException as error:  # noqa: BLE001 - given to the caller
                result = ("error", error)
            with state:
                late = "gave up" in box
                if not late:
                    box["result"] = result
            if late and on_late is not None and result[0] == "value":
                on_late(result[1])
            result = None  # release COM references here, on the worker
            done.set()
        finally:
            if joined:
                com.CoUninitialize()

    threading.Thread(target=worker, name=f"bounded: {what}", daemon=True).start()
    done.wait(BOUNDED_CALL_LIMIT_S)
    with state:
        if "result" not in box:
            box["gave up"] = True
            with _lock:
                _abandoned += 1
            raise CaptureFailure(stage, f"{what} did not return in {BOUNDED_CALL_LIMIT_S:g} s", hung=True)
    kind, value = box.pop("result")
    if kind == "error":
        raise value
    return value
