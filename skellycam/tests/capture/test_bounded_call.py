"""T-UNX-26, the shared part: the generic bounded call of `capture/bounded.py` with a limit argument
(specs/unix-capture.md 4.1; specs/windows-capture.md 3, 6.6).

The V4L2 source of step 7a calls it with the limit of 11 s for A-13; its fake (`STREAMOFF` and `S_FMT`)
waits for that step. Here the generic call runs plain functions that hang or are slow. The Media
Foundation wrapper runs the generic call and joins the MTA in each worker: that test runs on Windows only,
in a fresh process, as `test_media_foundation_com.py` does.
"""

import subprocess
import sys
import threading
import time

import pytest

from skellycam.tests.capture.capture_session import product

BOUNDED_MODULE = "skellycam.core.camera.capture.bounded"


@pytest.mark.capture_timing  # real time: the limits of 5 s and 11 s
def test_t_unx_26_generic_bounded_call_with_a_limit():
    """T-UNX-26: a close step that hangs (default limit 5 s); a slow call of 8 s with the limit of 11 s; a
    call that hangs with the limit of 11 s. `hung`, stage `close`, at 5 s; the slow call returns its value;
    the hung call gives `hung` at 11 s. The three calls run at the same time; each hung call counts in
    `abandoned()`."""
    bounded, source = product(BOUNDED_MODULE), product("skellycam.core.camera.capture.source")
    assert bounded.DEFAULT_LIMIT_S == 5.0 and bounded.SLOW_CALL_LIMIT_S == 11.0
    never = threading.Event()
    before = bounded.abandoned()
    results = {}

    def run(name, *args, **kwargs):
        t0 = time.perf_counter()
        try:
            results[name] = ("value", bounded.call(*args, **kwargs), time.perf_counter() - t0)
        except source.CaptureFailure as failure:
            results[name] = ("failure", failure, time.perf_counter() - t0)

    threads = [threading.Thread(target=run, args=("streamoff", "close", "STREAMOFF", never.wait)),
               threading.Thread(target=run, args=("slow s-fmt", "set mode", "S_FMT", lambda: time.sleep(8.0) or 7),
                                kwargs=dict(limit_s=bounded.SLOW_CALL_LIMIT_S)),
               threading.Thread(target=run, args=("hung s-fmt", "set mode", "S_FMT", never.wait),
                                kwargs=dict(limit_s=bounded.SLOW_CALL_LIMIT_S))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    kind, failure, took = results["streamoff"]
    assert kind == "failure" and (failure.stage, failure.code, failure.hung) == ("close", "hung", True)
    assert failure.reason == "STREAMOFF did not return in 5 s"
    assert 5.0 <= took <= 5.5, took
    assert results["slow s-fmt"][:2] == ("value", 7) and 8.0 <= results["slow s-fmt"][2] < 11.0
    kind, failure, took = results["hung s-fmt"]
    assert kind == "failure" and (failure.stage, failure.code) == ("set mode", "hung")
    assert failure.reason == "S_FMT did not return in 11 s"
    assert 11.0 <= took <= 11.5, took
    assert bounded.abandoned() - before == 2


def test_a_bounded_call_gives_the_value_or_the_error_of_the_function():
    """6.6: a call that returns in time gives its value; its exception reaches the caller unchanged; a
    function that returns after the caller gave up runs `on_late` with its value on the worker."""
    bounded, source = product(BOUNDED_MODULE), product("skellycam.core.camera.capture.source")
    assert bounded.call("open", "a quick call", lambda: 3) == 3
    with pytest.raises(source.CaptureFailure) as error:
        bounded.call("open", "a failing call", lambda: (_ for _ in ()).throw(
            source.CaptureFailure("open", "camera not found", code="not-found")))
    assert error.value.code == "not-found"
    late = threading.Event()
    with pytest.raises(source.CaptureFailure):
        bounded.call("open", "a late call", lambda: time.sleep(0.3) or 9, on_late=lambda value: late.set(),
                     limit_s=0.1)
    assert late.wait(2.0)


MTA_CHILD = """
import ctypes
from skellycam.core.camera.capture.media_foundation import bounded

def apartment():
    kind, qualifier = ctypes.c_int(), ctypes.c_int()
    assert ctypes.WinDLL("ole32.dll").CoGetApartmentType(ctypes.byref(kind), ctypes.byref(qualifier)) == 0
    return kind.value

print("APTTYPE", bounded.call("open", "the apartment", apartment))
try:
    bounded.call("open", "a hang", lambda: __import__("time").sleep(2), limit_s=0.2)
except Exception as error:
    print("HUNG", error.code, error.reason)
print("ABANDONED", bounded.abandoned())
"""


@pytest.mark.skipif(sys.platform != "win32", reason="the media_foundation package is Windows only (U18)")
def test_the_media_foundation_wrapper_joins_the_mta_and_takes_a_limit():
    """W 6.6: the wrapper of `media_foundation/bounded.py` runs the generic call; each worker is in the MTA
    (APTTYPE_MTA = 1); the limit argument reaches the generic call; `abandoned()` counts the hung call."""
    process = subprocess.run([sys.executable, "-c", MTA_CHILD], capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stderr[-2000:]
    assert "APTTYPE 1" in process.stdout, process.stdout
    assert "HUNG hung a hang did not return in 0.2 s" in process.stdout, process.stdout
    assert "ABANDONED 1" in process.stdout, process.stdout
