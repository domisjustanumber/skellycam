"""The signal handler of the server for a second Ctrl-C (specs/recorder.md 9.1 item 9, Q934, Q977 [ADR-F7BK]).

No process and no real time: a fake uvicorn server, a fake clock and a fake start of the forced exit. These checks
block (Q619): the drop of a repeat within `SECOND_CTRL_C_AFTER_S`, the abort after it, the kill flag, the start of
the forced exit, and the forced-exit thread that ends the process when it still runs.
"""

import signal
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
    server, flag, started = FakeServer(), SimpleNamespace(value=False), []
    handler = skellycam_main.abort_on_a_second_ctrl_c(server, flag, clock=lambda: now[0],
                                                      start_forced_exit=lambda: started.append(now[0]))
    return server, flag, started, handler


def test_the_numbers_of_the_spec():
    assert (skellycam_main.SECOND_CTRL_C_AFTER_S, skellycam_main.FORCED_EXIT_AFTER_S) == (1.0, 5.0)


@pytest.mark.parametrize("second", CTRL_C_SIGNALS)
@pytest.mark.parametrize("first", CTRL_C_SIGNALS + [signal.SIGTERM])
def test_a_repeat_within_1_s_is_dropped(first, second):
    now = [100.0]
    server, flag, started, handler = make(now)
    handler(first, None)
    now[0] += 0.1
    handler(second, None)
    assert (server.got, server.force_exit, flag.value, started) == ([first], False, False, [])


@pytest.mark.parametrize("second", CTRL_C_SIGNALS)
@pytest.mark.parametrize("first", CTRL_C_SIGNALS + [signal.SIGTERM])
def test_a_second_ctrl_c_1_s_after_the_first_aborts(first, second):
    now = [100.0]
    server, flag, started, handler = make(now)
    handler(first, None)
    assert (server.force_exit, flag.value, started) == (False, False, [])
    now[0] += 1.0
    handler(second, None)
    assert (server.got, server.force_exit, flag.value, started) == ([first, second], True, True, [101.0])
    now[0] += 3.0
    handler(second, None)  # a third press: no second forced-exit thread
    assert started == [101.0]


def test_a_second_sigterm_is_no_abort():
    now = [100.0]
    server, flag, started, handler = make(now)
    handler(signal.SIGINT, None)
    now[0] += 2.0
    handler(signal.SIGTERM, None)
    assert (server.got, server.force_exit, flag.value, started) == ([signal.SIGINT, signal.SIGTERM], False, False, [])


def test_the_forced_exit_ends_the_process_when_it_still_runs(monkeypatch):
    events = []
    monkeypatch.setattr(skellycam_main.time, "sleep", lambda seconds: events.append(("sleep", seconds)))
    monkeypatch.setattr(skellycam_main.os, "_exit", lambda code: events.append(("exit", code)))
    skellycam_main._forced_exit_after(skellycam_main.FORCED_EXIT_AFTER_S)
    assert events == [("sleep", 5.0), ("exit", 1)]

