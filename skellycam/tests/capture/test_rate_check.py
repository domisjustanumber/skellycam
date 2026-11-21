"""T-CAP-15 to T-CAP-18: the start-up rate check (specs/windows-capture.md, section 10.1).

Each test runs one fake camera through the HTTP endpoints with THREAD workers and a virtual clock.
The fake records the arrival time of each frame, so the expected rate comes from the script.
With instant controls, the first frame after the read-back is source frame 1, so warm-up frame k is
source frame k (the tests check this).
"""

import statistics

import pytest

from skellycam.tests.capture.capture_session import one_camera, slow_text
from skellycam.tests.capture.fake_source import FakeScript


def window_rate(log, first=6, last=90):
    """The rate formula of 10.1 over the delivered frames `first` to `last`."""
    t_first, t_last = log.frames[first][0], log.frames[last][0]
    return (last - first) / ((t_last - t_first) / 1e9)


def grid_pattern(counts):
    """Frame intervals on the 16 ms grid, spread evenly: {interval_ms: count}."""
    total, debt, sequence = sum(counts.values()), {k: 0.0 for k in counts}, []
    for _ in range(total):
        for k in counts:
            debt[k] += counts[k] / total
        k = max(debt, key=debt.get)
        debt[k] -= 1
        sequence.append(k)
    return tuple(sequence)


GENERIC = grid_pattern({32: 56, 48: 43, 16: 1})  # 10.5: the generic camera
GOOD = grid_pattern({32: 92, 48: 8})
JITTER_MS = (31, 36, 33, 30, 35, 34, 32, 33.5, 31.5)


def test_t_cap_15_rate_over_delivered_frames_6_to_90(monkeypatch):
    """T-CAP-15, section 10.1 [D22, agent 26]: a fake with scripted arrival times; the loop misses
    frames 40 to 45. The start-up rate equals `(n - 1) / (t_90 - t_6)` over the delivered frames 6 to
    90, to 0.001 fps.

    The arrival times jitter, so that a window of other frames gives another rate. The fake puts
    frames 40 to 46 together at the time of frame 46, so the loop takes 46 and misses 40 to 45.
    `measured_fps` of the status is the result of the check (8.4); it is not rounded (ADR-HP7D)."""
    with one_camera(monkeypatch, FakeScript(intervals_ms=JITTER_MS, burst=(40, 46))) as (app, camera_id, _):
        log = app.factory.logs[camera_id]
        assert log.first_sfn_after_readback == 1
        assert 46 in log.taken and not set(range(40, 46)) & set(log.taken), "the loop must miss frames 40 to 45"
        assert app.state(camera_id) == "ready"
        expected = window_rate(log)
        assert abs(app.status(camera_id)["measured_fps"] - expected) <= 0.001


@pytest.mark.parametrize(("rate", "passes"), [(29.2, True), (29.0, False), (30.8, True), (31.0, False)])
def test_t_cap_16_limit_of_3_percent(monkeypatch, rate, passes):
    """T-CAP-16, section 10.1 [D22]: each fake camera in its own group: fakes at 29.2, 29.0, 30.8 and
    31.0 fps with mode rate 30. 29.2 and 30.8 pass; 29.0 and 31.0 fail."""
    with one_camera(monkeypatch, FakeScript(rate=rate)) as (app, camera_id, response):
        status = app.status(camera_id)
        if passes:
            assert status["state"] == "ready", status
        else:
            assert status["state"] == "failed", status
            assert status["failure"]["stage"] == "rate check"
            assert response.json()["camera_failures"][camera_id]["stage"] == "rate check"


def test_t_cap_16_auto_rate_checks_against_the_mode_rate(monkeypatch):
    """T-CAP-16, section 10.1 [D22]: a fake with no 30 at the size, whose auto rate (-1) gives mode
    rate 60, and that delivers 60 fps. The auto case passes against 60, not against 30."""
    script = FakeScript(modes=((640, 480, 60, 1, "MJPG"), (1280, 720, 30, 1, "MJPG")))
    with one_camera(monkeypatch, script, framerate=-1.0) as (app, camera_id, response):
        status = app.status(camera_id)
        assert status["state"] == "ready", status
        assert (status["mode"]["fps_num"], status["mode"]["fps_den"]) == (60, 1)
        assert status["measured_fps"] == pytest.approx(60.0, rel=1e-3)
        assert response.json()["camera_configs"][camera_id]["framerate"] == 60.0


@pytest.mark.parametrize(("pattern", "passes"), [(GENERIC, False), (GOOD, True)], ids=["generic", "good"])
def test_t_cap_17_elapsed_time_rate_not_the_median(monkeypatch, pattern, passes):
    """T-CAP-17, sections 10.1 and 10.5 [D22, D24]: arrival times on a 16 ms grid: 56 % 32 ms and
    43 % 48 ms (generic camera; 1 % 16 ms), 92 % 32 ms and 8 % 48 ms (good camera). The generic
    pattern fails, the good pattern passes; a median of the same intervals gives above 29.1 fps for
    the generic pattern (proves the pattern)."""
    with one_camera(monkeypatch, FakeScript(intervals_ms=pattern)) as (app, camera_id, _):
        log = app.factory.logs[camera_id]
        intervals = [log.frames[k + 1][0] - log.frames[k][0] for k in range(6, 90)]
        assert all(i % 16_000_000 == 0 for i in intervals), "the arrival times are on the 16 ms grid"
        if passes:
            assert app.state(camera_id) == "ready"
        else:
            assert 1e9 / statistics.median(intervals) > 29.1, "a median rule would pass this camera"
            status = app.status(camera_id)
            assert status["state"] == "failed" and status["failure"]["stage"] == "rate check", status


def test_t_cap_18_reason_of_a_slow_camera(monkeypatch):
    """T-CAP-18, sections 10.4 and 12 [D25]: the generic pattern of T-CAP-17 at start. The reason is
    the text of 10.4 with 30.00 and the measured rate, the light hint first."""
    with one_camera(monkeypatch, FakeScript(intervals_ms=GENERIC)) as (app, camera_id, response):
        expected = slow_text(30.0, window_rate(app.factory.logs[camera_id]))
        assert app.status(camera_id)["failure"] == {"camera_id": camera_id, "stage": "rate check", "reason": expected,
                                                    "code": "rate-low"}
        assert response.json()["camera_failures"][camera_id]["reason"] == expected
