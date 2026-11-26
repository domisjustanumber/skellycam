"""T-TIM-07 and T-TIM-16 again with PROCESS workers (specs/capture-timings.md 2 item 4, 6.2): the shared scalar reaches
each spawned camera process, and the summaries cross the pipe of the diagnostics once per second of real time.

Timed: real camera processes publish once per second of real time. Not in the quick run (ADR-BM73).
"""

import time

import pytest

from skellycam.tests.capture.capture_session import capture_app, ready_app_steps
from skellycam.tests.capture.fake_source import FakeScript


@pytest.mark.capture_timing
def test_t_tim_07_the_switch_with_process_workers(monkeypatch):
    """With PROCESS workers: on gives a summary of each camera in about 1 s, with `seq` + 1 for each new summary;
    off gives `summaries` [] at once and the camera processes send no summary after their next publish."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()], workers="process") as app:
        ready_app_steps(app)
        manager = app.manager
        manager.set_log_capture_times(True)
        app.wait(lambda: len(manager.capture_timings()["summaries"]) == 2, "a summary of each camera", timeout=5)
        first = {s["camera_id"]: s["seq"] for s in manager.capture_timings()["summaries"]}
        time.sleep(2.5)
        later = {s["camera_id"]: s for s in manager.capture_timings()["summaries"]}
        for camera_id, seq in first.items():
            assert later[camera_id]["seq"] >= seq + 1
            assert 0.9 <= later[camera_id]["window_s"] <= 1.1
            assert later[camera_id]["steps"]["camera_wait"]["n"] > 0
        manager.set_log_capture_times(False)
        assert manager.capture_timings()["summaries"] == []
        time.sleep(2.5)
        assert app.group.camera_timings == {}
