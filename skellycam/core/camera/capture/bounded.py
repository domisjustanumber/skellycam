"""Bounded calls (specs/windows-capture.md, section 6.6; specs/unix-capture.md 4.1). No COM.

A call runs on a new thread. The caller waits at most the limit. A call that does not return in
time is a hang: its thread stays (a daemon thread), `abandoned()` counts it, and the caller gets
`CaptureFailure(..., hung=True)`. ctypes releases the GIL in each foreign call, so a call that hangs
in a driver does not block the caller.

`in_worker` is a context manager that the worker enters before the function and leaves after it released
the result, for example the MTA of Media Foundation (`media_foundation/bounded.py`).
"""

import contextlib
import logging
import multiprocessing
import threading
import time

from skellycam.core.camera.capture.source import BOUNDED_CALL_LIMIT_S, CaptureFailure

logger = logging.getLogger(__name__)
DEFAULT_LIMIT_S = BOUNDED_CALL_LIMIT_S
SLOW_CALL_LIMIT_S = 11.0  # unix-capture.md A-13: a slow camera call, for example S_FMT
_abandoned = 0
_lock = threading.Lock()


def abandoned() -> int:
    """The count of calls that did not return in time. MFShutdown is allowed only at 0 (6.1)."""
    return _abandoned


def call(stage: str, what: str, function, on_late=None, *, limit_s: float = DEFAULT_LIMIT_S,
         in_worker=contextlib.nullcontext):
    """Return `function()`, or raise its exception, or raise a hung `CaptureFailure` after `limit_s`.

    `on_late(value)` runs on the worker when `function` returns after the caller gave up, for
    example to shut down a source that came too late (6.2 step 3).
    """
    global _abandoned
    done = threading.Event()
    box = {}
    state = threading.Lock()

    def worker():
        with in_worker():
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
            result = None  # release the references here, on the worker
            done.set()

    t0 = time.perf_counter_ns()
    threading.Thread(target=worker, name=f"bounded: {what}", daemon=True).start()
    done.wait(limit_s)
    ms = (time.perf_counter_ns() - t0) / 1e6
    with state:
        if "result" not in box:
            box["gave up"] = True
            with _lock:
                _abandoned += 1
            logger.error(f"{stage}: {what}: no return in {ms:.1f} ms (hung)")
            raise CaptureFailure(stage, f"{what} did not return in {limit_s:g} s", hung=True)
    kind, value = box.pop("result")
    if kind == "error":
        # section 12: the diagnostics of each step (its native code in the reason, and its time) go to the log
        logger.warning(f"{stage}: {what}: {getattr(value, 'reason', None) or repr(value)} after {ms:.1f} ms")
        raise value
    logger.debug(f"{stage}: {what}: ok in {ms:.1f} ms")
    return value


def in_child(stage: str, what: str, target, args=(), *, limit_s: float, name: str, times: dict | None = None):
    """The bounded child call of the detection (windows-capture.md 7.1) and of the Quick Sync check (22.7 item 1).

    Run `target(*args, sender)` in a new `spawn` child and return the first message `(kind, value)` whose kind is not
    "alive". Each message must come within `limit_s`. A child with no message in time is killed: `CaptureFailure`
    with the code `hung`. A child that ends with no message gives `CaptureFailure` with the code `process-ended` and
    its exit code in `exit_code`. The call joins the child at its end, and kills a child that is still alive.
    `times["answer"]` gets the `time.perf_counter()` of the answer, the kill or the end, before that join (22.7 item 2).
    """
    times = {} if times is None else times
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=target, args=(*args, sender), name=name, daemon=True)
    try:
        try:
            child.start()
        finally:
            sender.close()
        while True:
            if not receiver.poll(limit_s):
                times["answer"] = time.perf_counter()
                child.kill()
                raise CaptureFailure(stage, f"{what} did not answer in {limit_s:g} s", code="hung")
            try:
                kind, value = receiver.recv()
            except EOFError:
                times["answer"] = time.perf_counter()
                child.join(DEFAULT_LIMIT_S)  # the pipe can close before the exit code is known
                failure = CaptureFailure(stage, f"{what} ended with code {child.exitcode}", code="process-ended")
                failure.exit_code = child.exitcode
                raise failure from None
            if kind != "alive":
                times["answer"] = time.perf_counter()
                return kind, value
    finally:
        receiver.close()
        # pid None: the start failed. On Windows the process exists before the pickling of the target fails; it has
        # no handle here and ends by itself when its pipe closes (within about 2 s, T-CAP-170).
        if child.pid is not None:
            child.join(DEFAULT_LIMIT_S)
            if child.is_alive():
                child.kill()
                child.join(DEFAULT_LIMIT_S)
