"""The Quick Sync check in a child process with a time limit (specs/windows-capture.md 22.7, Q879): T-CAP-166 to
T-CAP-173.

The tests that start a child are `capture_timing`, as the detection child tests are: a child start is slow under
load. They use the fake checks of `quick_sync_child_fakes`, which a `spawn` child imports by name. No test needs an
Intel GPU; T-CAP-171 runs the real encode in a child, and either answer passes.
"""

import logging
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import psutil
import pytest

from skellycam.tests.capture import quick_sync_child_fakes as fakes
from skellycam.tests.capture.capture_session import capture_app, capture_logs, product, ready_app_steps
from skellycam.tests.capture.fake_source import FakeScript

ENCODER_MODULE = "skellycam.core.camera.capture.encoder"
BOUNDED_MODULE = "skellycam.core.camera.capture.bounded"
W, H = 640, 480  # the size floor of 22.2 (Q887)
WINDOWS = sys.platform == "win32"


def descendants():
    return {p.pid for p in psutil.Process().children(recursive=True)}


def assert_no_new_child(before, wait_s=2.0):
    """22.7 item 5: no check child is left (a process listing)."""
    deadline = time.monotonic() + wait_s
    while (left := {pid for pid in descendants() - before if psutil.pid_exists(pid)}) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not left, f"a check child is still alive: {left}"


def quick_sync_lines(handler, level):
    return [message for levelno, message, _ in handler.records if levelno == level and "Quick Sync" in message]


def check(**kwargs):
    """`check_quick_sync` with the logs of this process. Gives (result, INFO lines, WARNING lines, seconds)."""
    encoder = product(ENCODER_MODULE)
    with capture_logs() as handler:
        t0 = time.perf_counter()
        result = encoder.check_quick_sync(**kwargs)
        seconds = time.perf_counter() - t0
    return result, quick_sync_lines(handler, logging.INFO), quick_sync_lines(handler, logging.WARNING), seconds


@pytest.mark.capture_timing  # a spawned child must answer within the 5 s limit; slow under load
def test_t_cap_166_a_check_that_gives_a_jpeg_works():
    """T-CAP-166, 22.7 items 2 and 4: a fake check that gives True. `works` True, `failure` null, both times above 0,
    no exit code; one INFO line, no WARNING line."""
    before = descendants()
    result, infos, warnings, _ = check(check=fakes.gives_true)
    assert result.works is True and result.failure is None and result.exit_code is None, result
    assert result.check_ms > 0 and result.encode_ms is not None and result.encode_ms >= 0, result
    assert result.check_ms >= result.encode_ms, result
    assert len(infos) == 1 and "works" in infos[0], infos
    assert not warnings, warnings
    assert_no_new_child(before)


@pytest.mark.capture_timing  # a spawned child must answer within the 5 s limit; slow under load
def test_t_cap_167_a_check_that_gives_no_jpeg():
    """T-CAP-167, 22.7 item 4: a fake check that gives False. `works` False, `failure` `no-jpeg`; no WARNING line."""
    result, infos, warnings, _ = check(check=fakes.gives_false)
    assert (result.works, result.failure, result.exit_code) == (False, "no-jpeg", None), result
    assert result.encode_ms is not None, result
    assert len(infos) == 1, infos
    assert not warnings, warnings


@pytest.mark.capture_timing  # real time: the limit of 1 s plus the kill
def test_t_cap_168_a_check_that_hangs_is_killed_at_the_limit():
    """T-CAP-168, 22.7 items 3 to 5: a fake check that hangs for 60 s, with a limit of 1 s. The call returns within
    1 s + 2 s with `timed-out`; one WARNING line with "time-out"; no child is left."""
    before = descendants()
    result, _, warnings, seconds = check(check=fakes.hangs, limit_s=1.0)
    assert seconds <= 1.0 + 2.0, f"the check returned after {seconds:.2f} s"
    assert (result.works, result.failure, result.encode_ms, result.exit_code) == (False, "timed-out", None, None), \
        result
    assert result.check_ms >= 1000.0, result
    assert len(warnings) == 1 and "time-out" in warnings[0] and "cv2.imencode is used" in warnings[0], warnings
    assert_no_new_child(before)


@pytest.mark.capture_timing  # a spawned child must answer within the 5 s limit; slow under load
@pytest.mark.parametrize("fake, code", [(fakes.exits_3, 3)] + (
    [(fakes.exits_access_violation, fakes.ACCESS_VIOLATION)] if WINDOWS else []))
def test_t_cap_169_a_check_that_crashes_its_child(fake, code):
    """T-CAP-169, 22.7 items 4 and 5: a fake check that ends its process with `os._exit(3)`, and on Windows with the
    code of an access violation. `crashed` with the exit code; one WARNING line with "crashed" and the code; no child
    is left."""
    before = descendants()
    result, _, warnings, _ = check(check=fake)
    assert (result.works, result.failure, result.encode_ms, result.exit_code) == (False, "crashed", None, code), result
    assert len(warnings) == 1 and "crashed" in warnings[0] and str(code) in warnings[0], warnings
    assert "cv2.imencode is used" in warnings[0], warnings
    assert_no_new_child(before)


@pytest.mark.capture_timing  # a spawned child must answer within the 5 s limit; slow under load
def test_t_cap_170_an_encode_that_raises_and_an_error_of_the_child_call():
    """T-CAP-170, 22.7 item 4: a fake check that raises `RuntimeError` is the answer of the check (no WARNING line);
    a check that cannot reach the child (a lambda does not pickle) is an error of the child call: one WARNING line
    with "error" and the class."""
    result, infos, warnings, _ = check(check=fakes.raises)
    assert (result.works, result.failure, result.exit_code) == (False, "RuntimeError", None), result
    assert result.encode_ms is not None, result
    assert len(infos) == 1 and "RuntimeError" in infos[0], infos
    assert not warnings, warnings
    before = descendants()
    result, _, warnings, _ = check(check=lambda: True)
    assert result.works is False and result.failure not in (None, "no-jpeg", "timed-out", "crashed"), result
    assert result.failure.isidentifier(), f"`failure` must be a class name: {result.failure!r}"
    assert len(warnings) == 1 and "error" in warnings[0] and result.failure in warnings[0], warnings
    assert_no_new_child(before)


@pytest.mark.capture_timing  # the real encode in a child: about 1 s on the development machine
def test_t_cap_171_the_encode_never_runs_in_the_main_process(monkeypatch):
    """T-CAP-171, 22.7 item 2: `quick_sync_works()` with the encode of the main process replaced by a recorder gives
    a bool, and the recorder never runs: the child takes the encode from its own import. On macOS (a patched
    `sys.platform`) it gives False and makes no child call."""
    encoder = product(ENCODER_MODULE)
    calls = []
    monkeypatch.setattr(encoder, "_encode_test_frame", lambda: calls.append("main") or True)
    assert isinstance(encoder.quick_sync_works(), bool)
    assert not calls, "the encode of the check ran in the main process"
    result = encoder.check_quick_sync()
    assert result.encode_ms is not None or result.failure in ("timed-out", "crashed"), result
    assert not calls, "the encode of the check ran in the main process"
    bounded = product(BOUNDED_MODULE)
    monkeypatch.setattr(bounded, "in_child", lambda *args, **kwargs: calls.append("child"))
    monkeypatch.setattr(sys, "platform", "darwin")
    assert encoder.quick_sync_works() is False
    monkeypatch.undo()
    assert not calls, "a check child started on macOS"


def raw_camera():
    return FakeScript(modes=((W, H, 30, 1, "MJPG"), (W, H, 30, 1, "YUY2")))


def test_t_cap_172_the_manager_checks_one_time_and_only_for_an_accepted_raw_request(monkeypatch):
    """T-CAP-172, 22.7 items 7 and 8: with `check_quick_sync` replaced by a counter that gives `timed-out`: an MJPG
    request and a refused YUY2 request (422, the one-rate rule) make no call; the accepted YUY2 request makes one
    call; a second accepted YUY2 request makes none; the status flag `quick_sync` of the camera is False."""
    encoder = product(ENCODER_MODULE)
    calls = []

    def counted(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(works=False, failure="timed-out", check_ms=5000.0, encode_ms=None, exit_code=None)

    expected = 0 if sys.platform == "darwin" else 1  # macOS: no check and no call (22.7 item 2)
    scripts = [raw_camera(), FakeScript(modes=((W, H, 30, 1, "MJPG"), (W, H, 60, 1, "MJPG")))]
    with capture_app(monkeypatch, scripts, full_modes=True) as app:
        monkeypatch.setattr(encoder, "check_quick_sync", counted)
        raw, mjpg = app.factory.camera_ids
        ready_app_steps(app, [app.config(raw), app.config(mjpg)])
        assert not calls, "an MJPG request ran the Quick Sync check"
        refused = app.apply([app.config(raw, capture_fourcc="YUY2"), app.config(mjpg, framerate=60.0)])
        assert refused.status_code == 422, refused.text
        assert not calls, "a refused request ran the Quick Sync check"
        response = app.apply([app.config(raw, capture_fourcc="YUY2"), app.config(mjpg)])
        assert response.status_code == 200, response.text
        app.wait_state(raw, "ready")
        assert len(calls) == expected, calls
        response = app.apply([app.config(raw, capture_fourcc="YUY2", exposure=-8), app.config(mjpg)])
        assert response.status_code == 200, response.text
        app.wait_state(raw, "ready")
        assert len(calls) == expected, "a second check ran in one app run"
        assert app.manager.quick_sync is False
        assert app.group.cameras.orchestrator.camera_statuses[raw].quick_sync.value == 0


def test_t_cap_174_two_raw_requests_at_once_start_one_check(monkeypatch):
    """T-CAP-174, 22.7 item 8: a group of two MJPG cameras runs; two YUY2 requests come at the same time, the second
    while the check of the first still runs. Only one check starts; the second request waits for its answer."""
    encoder = product(ENCODER_MODULE)
    calls, go = [], threading.Event()

    def slow_check():
        calls.append(threading.get_ident())
        go.wait(30)
        return False

    with capture_app(monkeypatch, [raw_camera(), raw_camera()], full_modes=True) as app:
        first, second = app.factory.camera_ids
        ready_app_steps(app, [app.config(first), app.config(second)])
        monkeypatch.setattr(encoder, "quick_sync_works", slow_check)
        out = {}
        threads = [threading.Thread(target=lambda key=key, raw=raw, other=other: out.setdefault(key, app.apply(
            [app.config(raw, capture_fourcc="YUY2"), app.config(other)])))
            for key, raw, other in (("a", first, second), ("b", second, first))]
        threads[0].start()
        try:
            app.wait(lambda: len(calls) == 1, "the check of the first request runs")
            threads[1].start()
            deadline = time.monotonic() + 2.0  # time for the second request to reach its check
            while len(calls) < 2 and time.monotonic() < deadline:
                time.sleep(0.02)
        finally:
            go.set()
            for thread in threads:
                if thread.is_alive() or thread.ident is not None:
                    thread.join(60)
        assert len(calls) == 1, f"{len(calls)} Quick Sync checks started in one app run"
        assert {out["a"].status_code, out["b"].status_code} <= {200, 409}, (out["a"].text, out["b"].text)
        assert app.manager.quick_sync is False


@pytest.mark.capture_timing  # real time: the join of 5 s after the answer, then the kill
def test_t_cap_175_a_child_that_answers_and_then_hangs_at_exit():
    """T-CAP-175, 22.7 items 2 and 5: the child gives a good answer and then does not end. `check_ms` is the time to
    the answer (well under the join of 5 s); the call kills the child, and no child is left."""
    before = descendants()
    result, _, _, seconds = check(check=fakes.answers_then_hangs_at_exit)
    assert result.works is True and result.failure is None, result  # the behaviour of today: a question for Dom
    assert result.check_ms < 4000.0, f"check_ms {result.check_ms:.0f} is not the time to the answer"
    assert seconds >= 4.5, f"the call did not wait for the exit of the child ({seconds:.2f} s)"
    assert_no_new_child(before)


@pytest.mark.capture_timing  # a new interpreter imports the app: a few seconds under load
def test_t_cap_173_the_app_import_starts_no_check_child():
    """T-CAP-173, 22.7 item 6: a new interpreter imports `skellycam.app`; no child process of it exists after the
    import."""
    code = ("import psutil, skellycam.app; "
            "print(len(psutil.Process().children(recursive=True)))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "0", out.stdout
