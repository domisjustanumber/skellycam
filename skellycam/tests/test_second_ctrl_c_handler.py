"""The signal handler of the server for a second Ctrl-C (specs/recorder.md 9.1 item 9, Q934, Q977 [ADR-F7BK]).

No process and no real time: a fake uvicorn server, a fake clock and a fake trigger of the forced exit. These checks
block (Q619): only Ctrl-C and Ctrl-Break are presses; a press within `SECOND_CTRL_C_AFTER_S` of the last press is
dropped, also when a key repeats for longer; a press after that is the abort, with the kill flag and one trigger of
the forced exit; a first press after a SIGTERM is no abort; the forced-exit thread ends the process after its event.
"""

import signal
import threading
from types import SimpleNamespace

import pytest

import skellycam.__main__ as skellycam_main

SIGBREAK = getattr(signal, "SIGBREAK", None)
CTRL_C_SIGNALS = [signal.SIGINT] + ([SIGBREAK] if SIGBREAK is not None else [])


class FakeServer:
    """The parts of `uvicorn.Server` that the handler uses."""

    def __init__(self):
        self.should_exit = self.force_exit = False
        self.got = []

    def handle_exit(self, sig, frame):
        self.got.append(sig)
        self.should_exit = True


def make(now):
    server, flag, triggered = FakeServer(), SimpleNamespace(value=False), []
    handler = skellycam_main.abort_on_a_second_ctrl_c(server, flag, clock=lambda: now[0],
                                                      forced_exit=lambda: triggered.append(now[0]))
    return server, flag, triggered, handler


def state(server, flag, triggered):
    return server.got, server.force_exit, flag.value, triggered


def test_the_numbers_of_the_spec():
    assert (skellycam_main.SECOND_CTRL_C_AFTER_S, skellycam_main.FORCED_EXIT_AFTER_S) == (1.0, 5.0)


@pytest.mark.parametrize("second", CTRL_C_SIGNALS)
@pytest.mark.parametrize("first", CTRL_C_SIGNALS)
def test_a_repeat_within_1_s_is_dropped(first, second):
    now = [100.0]
    server, flag, triggered, handler = make(now)
    handler(first, None)
    now[0] += 0.1
    handler(second, None)
    assert state(server, flag, triggered) == ([first], False, False, [])


@pytest.mark.parametrize("second", CTRL_C_SIGNALS)
@pytest.mark.parametrize("first", CTRL_C_SIGNALS)
def test_a_second_ctrl_c_1_s_after_the_first_aborts(first, second):
    now = [100.0]
    server, flag, triggered, handler = make(now)
    handler(first, None)
    assert state(server, flag, triggered) == ([first], False, False, [])
    now[0] += 1.0
    handler(second, None)
    assert state(server, flag, triggered) == ([first, second], True, True, [101.0])
    now[0] += 3.0
    handler(second, None)  # a third press: no second trigger
    assert triggered == [101.0]


def test_a_key_that_repeats_for_longer_than_1_s_never_aborts():
    """The 1 s counts from the last press, also a dropped one."""
    now = [0.0]
    server, flag, triggered, handler = make(now)
    for at in (0.0, 0.5, 1.0, 1.5):
        now[0] = at
        handler(signal.SIGINT, None)
    assert state(server, flag, triggered) == ([signal.SIGINT], False, False, [])
    now[0] = 2.6
    handler(signal.SIGINT, None)
    assert state(server, flag, triggered) == ([signal.SIGINT, signal.SIGINT], True, True, [2.6])


@pytest.mark.parametrize("press", CTRL_C_SIGNALS)
def test_a_sigterm_and_then_one_ctrl_c_is_no_abort(press):
    """A SIGTERM (the monitor after /shutdown, a fault, from outside) is no first press; the first press after it does
    not reach uvicorn, which would take it as `force_exit`. A second press 1 s later is the abort."""
    now = [100.0]
    server, flag, triggered, handler = make(now)
    handler(signal.SIGTERM, None)
    now[0] += 1.0
    handler(press, None)
    assert state(server, flag, triggered) == ([signal.SIGTERM], False, False, [])
    now[0] += 1.0
    handler(press, None)
    assert state(server, flag, triggered) == ([signal.SIGTERM, press], True, True, [102.0])


def test_a_second_sigterm_is_no_abort():
    now = [100.0]
    server, flag, triggered, handler = make(now)
    handler(signal.SIGINT, None)
    now[0] += 2.0
    handler(signal.SIGTERM, None)
    assert state(server, flag, triggered) == ([signal.SIGINT, signal.SIGTERM], False, False, [])


def test_the_forced_exit_ends_the_process_after_its_event(monkeypatch):
    events = []
    monkeypatch.setattr(skellycam_main.time, "sleep", lambda seconds: events.append(("sleep", seconds)))
    monkeypatch.setattr(skellycam_main.os, "_exit", lambda code: events.append(("exit", code)))
    abort = threading.Event()
    abort.set()
    skellycam_main._forced_exit_after(abort, skellycam_main.FORCED_EXIT_AFTER_S)
    assert events == [("sleep", 5.0), ("exit", 1)]


def test_the_handler_starts_no_thread():
    """9.1 item 9: a signal handler that starts a thread can block on a lock of `threading` that the main thread
    holds, so the abort only calls the trigger (in the product: `Event.set`)."""
    now = [100.0]
    server, flag, triggered, handler = make(now)
    before = threading.active_count()
    handler(signal.SIGINT, None)
    now[0] += 2.0
    handler(signal.SIGINT, None)
    assert triggered == [102.0] and threading.active_count() == before
