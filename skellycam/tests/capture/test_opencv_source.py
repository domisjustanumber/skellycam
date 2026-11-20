"""T-CAP-99 to T-CAP-104 and T-CAP-111: the rules of phase 3 for the OpenCV source, with the OpenCV fake [U23]
(specs/windows-capture.md, sections 7.5, 8, 9.5, 10.1, 11.3 and 14.1).

Each test runs the product `OpenCVSource` with the OpenCV fake (`OpenCVFakeFactory`) under the real
camera group manager, with THREAD workers and real time. The detection result of the fake has
`supported_modes = []`, as on Linux and macOS, so the whole-request check compares the requested
rates. These tests run on Windows, Linux and macOS (U20). Each takes about 4 to 10 s.
"""

import logging
import sys
import time

import pytest

from skellycam.tests.capture.capture_hardware import SLOW_REASON
from skellycam.tests.capture.capture_session import (
    CaptureApp, OpenCVFakeFactory, Spies, StateWatcher, capture_logs, recording_info_json, ready_app_steps)


class OpenCVApp:
    """A `CaptureApp` with `OpenCVFakeFactory`. Closes the app on exit."""

    def __init__(self, monkeypatch, count=1, **factory_args):
        self.factory = OpenCVFakeFactory(monkeypatch, count=count, **factory_args)
        self.app = CaptureApp(monkeypatch, self.factory)

    def __enter__(self):
        return self.app

    def __exit__(self, *exc):
        self.app.close()


def detail(response):
    return str(response.json().get("detail"))


@pytest.mark.parametrize("case", ["request 25", "reports 24", "reports no rate"])
def test_t_cap_99_floor_of_30_fps_with_opencv(monkeypatch, case):
    """T-CAP-99, sections 7.5 and 14.1 [U11, U23, agent 55, agent 59]: the OpenCV fake: (1) a request of
    25; (2) a request of 30, and OpenCV reports a real rate of 24 after the open; (3) a request of 30,
    and OpenCV reports no rate (0). (1) gets 422 and opens no camera; (2) fails, stage `set mode`,
    "no mode at 30 fps or more"; (3) reaches `ready` with no floor check; the rate check uses the
    requested rate, and `measured_fps` is within 3 % of 30 (ADR-PDD3 W2)."""
    reported = {"request 25": 30.0, "reports 24": 24.0, "reports no rate": 0.0}[case]
    with OpenCVApp(monkeypatch, reported_fps=reported, delivered_fps=30.0) as app:
        app.detect()
        camera_id = app.factory.camera_ids[0]
        response = app.apply([app.config(camera_id, framerate=25.0 if case == "request 25" else 30.0)])
        if case == "request 25":
            assert response.status_code == 422, response.text
            assert app.factory.opens[camera_id] == 0
            return
        assert response.status_code == 200, response.text
        app.wait_state(camera_id, "ready", "failed")
        status = app.status(camera_id)
        if case == "reports 24":
            assert status["failure"] == {"camera_id": camera_id, "stage": "set mode",
                                         "reason": "no mode at 30 fps or more"}
        else:
            assert status["state"] == "ready" and abs(status["measured_fps"] - 30.0) <= 0.9, status


def test_t_cap_100_one_rate_rule_on_requested_rates(monkeypatch):
    """T-CAP-100, section 7.5 [D18, U7, U23, agent 56]: two OpenCV fakes. (1) Requests of 30 and 60: 422,
    and no camera opens. (2) Both requests auto (-1), and after the open OpenCV reports 30 for one
    and 60 for the other: a warning only; both reach `ready`, and no camera is closed.

    The warning is a log record at WARNING that names both camera IDs, and an item of the kind
    `mixed_rate` in the `warnings` list of the apply response (ADR-PDD3 W3)."""
    with capture_logs() as logs, OpenCVApp(monkeypatch, count=2, per_camera={1: dict(reported_fps=60.0)}) as app:
        app.detect()
        first, second = app.factory.camera_ids
        refused = app.apply([app.config(first, framerate=30.0), app.config(second, framerate=60.0)])
        assert refused.status_code == 422, refused.text
        assert app.factory.opens == {first: 0, second: 0}
        response = app.apply([app.config(first, framerate=-1.0), app.config(second, framerate=-1.0)])
        assert response.status_code == 200, response.text
        for camera_id in (first, second):
            app.wait_state(camera_id, "ready")
        assert any(first in m and second in m for m in logs.messages(logging.WARNING)), "no warning names both cameras"
        items = [w for w in response.json()["warnings"] if w["kind"] == "mixed_rate"]
        assert len(items) == 1 and set(items[0]["camera_ids"]) == {first, second}, response.json()["warnings"]
        time.sleep(1.0)
        assert [app.state(cid) for cid in (first, second)] == ["ready", "ready"]
        assert app.factory.opens == {first: 1, second: 1}


@pytest.mark.parametrize("reported", [30.0, 0.0], ids=["reports 30", "reports no rate"])
def test_t_cap_101_start_up_rate_check_only_with_a_reported_rate(monkeypatch, reported):
    """T-CAP-101, sections 10.1 and 14.1 [D22, D46, U23]: the OpenCV fake delivers 25 fps. (1) OpenCV
    reports 30. (2) OpenCV reports no rate: the check uses the requested rate (ADR-PDD3 W2). In both
    cases the camera fails, stage `rate check`, with the reason of 10.4 (declared 30.00, measured
    25 +/- 0.75)."""
    with OpenCVApp(monkeypatch, reported_fps=reported, delivered_fps=25.0) as app:
        app.detect()
        camera_id = app.factory.camera_ids[0]
        assert app.apply([app.config(camera_id)]).status_code == 200
        app.wait_state(camera_id, "ready", "failed")
        status = app.status(camera_id)
        assert status["state"] == "failed" and status["failure"]["stage"] == "rate check", status
        match = SLOW_REASON.match(status["failure"]["reason"])
        assert match and match.group(1) == "30.00" and abs(float(match.group(2)) - 25.0) <= 0.75


def test_t_cap_102_a_camera_that_cannot_open_fails_alone(monkeypatch, tmp_path):
    """T-CAP-102, sections 8.2, 8.3 and 14.1 [D23, D46, U23]: three OpenCV fakes; one cannot open. That
    camera is `failed` with stage `open`; the other two reach `ready` with preview; a record start
    returns 409 and names it."""
    with OpenCVApp(monkeypatch, count=3, fail_open=(2,)) as app:
        app.detect()
        response = app.apply([app.config(cid) for cid in app.factory.camera_ids])
        assert response.status_code == 200, response.text
        good, failed = app.factory.camera_ids[:2], app.factory.camera_ids[2]
        for camera_id in good:
            app.wait_state(camera_id, "ready")
        app.wait_state(failed, "failed")
        assert app.status(failed)["failure"]["stage"] == "open"
        assert response.json()["camera_failures"][failed]["stage"] == "open"
        for camera_id in good:
            grabs = app.factory.captures[camera_id].grabs
            app.wait(lambda: app.factory.captures[camera_id].grabs > grabs + 10, f"preview of {camera_id}")
        refused = app.record_start(tmp_path)
        assert refused.status_code == 409 and failed in detail(refused)


def test_t_cap_103_a_camera_that_stops_during_a_recording(monkeypatch, tmp_path):
    """T-CAP-103, sections 5.7, 8.2, 9.5 and 14.1 [D38, U4, U23]: two OpenCV fakes record; the grabs of
    one start to fail (as after an unplug). That camera is `dead` 2.0 to 2.25 s after its last ring
    frame; the other camera keeps recording to the stop; `dead_cameras` names it."""
    with OpenCVApp(monkeypatch, count=2) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        stopping, other = app.factory.camera_ids
        watcher = StateWatcher(app, stopping)
        try:
            assert app.record_start(tmp_path).status_code == 200
            app.wait(lambda: len(spies.of("record", stopping)) >= 30, "30 recorded frames")
            app.factory.captures[stopping].stop()
            app.wait(lambda: "dead" in watcher.first, "the camera is dead")
            last = spies.of("jpeg", stopping)[-1]["arrival_ns"]
            elapsed = (watcher.first["dead"] - last) / 1e9
            assert 2.0 <= elapsed <= 2.25, f"dead {elapsed:.3f} s after its last frame"
            dead_ns = watcher.first["dead"]
            app.wait(lambda: any(e["arrival_ns"] > dead_ns + 10**9 for e in spies.of("record", other)),
                     "the other camera records on")
            assert app.record_stop().status_code == 200
        finally:
            watcher.stop()
        assert [d["camera_id"] for d in recording_info_json(tmp_path)["dead_cameras"]] == [stopping]


@pytest.mark.parametrize("case", ["AUTO config", "MANUAL config on Linux"])
def test_t_cap_104_auto_exposure_warning_once_per_camera_per_recording(monkeypatch, tmp_path, case):
    """T-CAP-104, sections 11.3 and 14.1 [D37, U23]: two OpenCV fakes, two recordings. Each record start
    gives the `auto_control` warning for `exposure` one time for each camera. Case 1: the config asks
    for `AUTO` (each system). Case 2: the config asks for `MANUAL`, and the OpenCV source forces auto
    exposure on Linux (14.1); Linux only."""
    if case == "MANUAL config on Linux" and not sys.platform.startswith("linux"):
        pytest.skip("the OpenCV source forces auto exposure on Linux only (14.1)")
    mode = "AUTO" if case == "AUTO config" else "MANUAL"
    with OpenCVApp(monkeypatch, count=2) as app:
        ready_app_steps(app, [app.config(cid, exposure_mode=mode) for cid in app.factory.camera_ids])
        for take in ("take1", "take2"):
            started = app.record_start(tmp_path, name=take)
            assert started.status_code == 200, started.text
            items = [w for w in started.json()["warnings"] if w["kind"] == "auto_control" and w["control"] == "exposure"]
            named = [cid for item in items for cid in item["camera_ids"]]
            assert sorted(named) == sorted(app.factory.camera_ids), f"{take}: {named}"
            time.sleep(1.0)
            assert app.record_stop().status_code == 200


def test_t_cap_111_one_opencv_call_at_a_time(monkeypatch):
    """T-CAP-111, sections 4.3 and 14.1 [U16, ADR-PDD3]: the loop thread reads frames while the control
    thread reads the controls, on one `OpenCVSource`. `cv2.VideoCapture` is not thread-safe, so no two
    calls on the capture overlap. The stand-in capture counts the calls that run at one time."""
    import threading

    import cv2
    import numpy as np

    from skellycam.core.camera.capture import opencv_source
    from skellycam.core.camera.capture.source import CaptureRequest
    from skellycam.core.camera.config.camera_config import CameraConfig

    class CountingCapture:
        def __init__(self):
            self.inside = self.most = 0
            self.lock = threading.Lock()

        def _call(self, result):
            with self.lock:
                self.inside += 1
                self.most = max(self.most, self.inside)
            time.sleep(0.001)
            with self.lock:
                self.inside -= 1
            return result

        def grab(self):
            return self._call(True)

        def retrieve(self):
            return self._call((True, np.zeros((4, 4, 3), np.uint8)))

        def get(self, prop):
            return self._call({cv2.CAP_PROP_FPS: 30.0, cv2.CAP_PROP_FRAME_WIDTH: 4.0,
                               cv2.CAP_PROP_FRAME_HEIGHT: 4.0}.get(prop, 0.0))

        def set(self, prop, value):
            return self._call(True)

        def release(self):
            pass

    capture = CountingCapture()
    monkeypatch.setattr(opencv_source, "create_cv2_video_capture", lambda config: (capture, config))
    source = opencv_source.OpenCVSource(CameraConfig(camera_id="a1b2", camera_index=0))
    source.open(CaptureRequest(camera_id="a1b2", width=4, height=4, framerate=30.0))
    stop = threading.Event()

    def read_controls():
        while not stop.is_set():
            source.set_controls({})

    controls = threading.Thread(target=read_controls, daemon=True)
    controls.start()
    try:
        for _ in range(300):
            assert source.read_frame(0.1) is not None
    finally:
        stop.set()
        controls.join(5)
        source.close()
    assert capture.most == 1, f"{capture.most} calls on the capture ran at one time"
