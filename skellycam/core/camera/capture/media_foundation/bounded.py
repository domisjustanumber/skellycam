"""Bounded calls of Media Foundation (specs/windows-capture.md, section 6.6; ported from the prototype
`pymf/bounded.py`): the generic call of `capture/bounded.py`, with each worker in the MTA (agent 43).

A function that calls a COM object must use its own reference (`com.ref`) and release it when it
returns. Then a hung call never uses an object that the caller released.
"""

import contextlib

from skellycam.core.camera.capture import bounded
from skellycam.core.camera.capture.media_foundation import com

abandoned = bounded.abandoned


@contextlib.contextmanager
def _in_mta():
    joined = com.coinit_mta()  # each worker joins the MTA first (agent 43)
    try:
        yield
    finally:
        if joined:
            com.CoUninitialize()


def call(stage: str, what: str, function, on_late=None, *, limit_s: float = bounded.DEFAULT_LIMIT_S):
    """`capture.bounded.call` in the MTA. The COM references of the result are released on the worker."""
    return bounded.call(stage, what, function, on_late, limit_s=limit_s, in_worker=_in_mta)
