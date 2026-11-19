"""The full mode list (step 3b by V1), the gain and focus controls, white balance and the power line
frequency, and the deletion of the OpenCV source on Windows (step 3c) (specs/windows-capture.md,
sections 7.4, 11, 14 and 16).

T-CAP-71 (step 3b) and T-CAP-72 to T-CAP-76, T-CAP-107 and T-CAP-108 (step 3c). All run on Windows,
Linux and macOS, except T-CAP-76: it runs on Windows only, after the last commit of phase 3 (16.1,
16.7). The session tests run fake cameras through the HTTP endpoints with THREAD workers
(`capture_session`). T-CAP-107 and T-CAP-108 use the product `OpenCVSource` with the OpenCV fake, in
real time (V5).
"""

import importlib
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import pytest

from skellycam.tests.capture.capture_session import (
    CaptureApp, OpenCVFakeFactory, Spies, capture_app, product, ready_app_steps, recording_info_json)
from skellycam.tests.capture.fake_source import FakeScript
from skellycam.tests.capture.test_detection_and_modes import NATIVE_25

MODES_MODULE = "skellycam.core.camera.capture.modes"
REPO_ROOT = Path(__file__).resolve().parents[3]


def opens(app, camera_id):
    return app.factory.logs[camera_id].opens.value


def detail(response):
    return json.dumps(response.json().get("detail"))


# ---------------------------------------------------------------------------
# T-CAP-71: capture_modes (7.4)
# ---------------------------------------------------------------------------

# The native types of T-CAP-25, and two more: the criterion names RAW, and 7.4 lists native NV12.
NATIVE_71 = NATIVE_25 + ((800, 600, 30, 1, "NV12"), (640, 480, 30, 1, "RAW"))


def _mode(width, height, fps_num, fps_den, fmt, framerate, reason=None):
    uncompressed = fmt in ("YUY2", "NV12", "RAW")
    return {"width": width, "height": height, "fps_num": fps_num, "fps_den": fps_den, "framerate": framerate,
            "format": fmt, "uncompressed": uncompressed, "selectable": reason is None, "reason": reason}


LOW, NEVER = "below 30 fps", "never opened"
EXPECTED_71 = [
    _mode(1920, 1080, 24, 1, "MJPG", 24.0, LOW),
    _mode(1920, 1080, 10000000, 333333, "MJPG", 30.0),
    _mode(1920, 1080, 30, 1, "H264", 30.0, NEVER),
    _mode(1280, 720, 10, 1, "YUY2", 10.0, LOW),
    _mode(1280, 720, 30, 1, "MJPG", 30.0),
    _mode(1280, 720, 60, 1, "MJPG", 60.0),
    _mode(960, 540, 30, 1, "H264", 30.0, NEVER),
    _mode(800, 600, 30, 1, "YUY2", 30.0),
    _mode(800, 600, 30, 1, "NV12", 30.0),
    _mode(640, 480, 15, 2, "MJPG", 7.5, LOW),
    _mode(640, 480, 30000, 1001, "MJPG", 29.97),
    _mode(640, 480, 30, 1, "MJPG", 30.0),
    _mode(640, 480, 30, 1, "YUY2", 30.0),
    _mode(640, 480, 30, 1, "RAW", 30.0, NEVER),
    _mode(480, 640, 30, 1, "MJPG", 30.0),
    _mode(320, 240, 15, 2, "MJPG", 7.5, LOW),
    _mode(320, 240, 24, 1, "MJPG", 24.0, LOW),
]


def test_t_cap_71_capture_modes_json():
    """T-CAP-71, section 7.4, step 3b [V1, D4, D14, U8, U11, agent 19, agent 53]: build `capture_modes` from the native
    types of T-CAP-25. The JSON of 7.4: MJPG and YUY2 both listed, MJPG first; H.264 and RAW
    `selectable: false` with "never opened"; modes below 29.97 fps `selectable: false` with "below
    30 fps"; synthesized NV12 left out.

    Two types are added to those of T-CAP-25: a RAW type (the criterion names RAW) and a native NV12
    type. Where 7.4 does not fix the list, it follows ADR-3WCA: an exact duplicate is listed one time;
    for one size, the rounded rates ascend; for one size and rounded rate, MJPG comes first, then the
    other formats in the order of the native list."""
    modes = product(MODES_MODULE)
    result = modes.capture_modes([modes.NativeMode(*m) for m in NATIVE_71])
    dumped = [mode.model_dump() for mode in result]
    assert dumped == EXPECTED_71
    assert json.dumps(dumped) == json.dumps(EXPECTED_71)


# ---------------------------------------------------------------------------
# T-CAP-72 to T-CAP-75: gain, focus, white balance, power line frequency (11.5)
# ---------------------------------------------------------------------------

def _live_change(app, camera_id, **changes):
    """Apply a live change; wait for `checking`, then for the end of the check."""
    t_change = app.clock.now_ns()
    response = app.apply([app.config(camera_id, **changes)])
    assert response.status_code == 200, response.text
    app.wait(lambda: app.tracker.first(camera_id, "checking", t_change) is not None, f"checking after {changes}")
    app.wait_state(camera_id, "ready")
    return response


def _settings_of(app, camera_id, name):
    return [changes[name] for changes in app.factory.logs[camera_id].settings if name in changes]


def test_t_cap_72_gain_and_focus_live(monkeypatch):
    """T-CAP-72, sections 11.2 and 11.5 [D31, D43, agent 30]: set gain and focus, manual and auto, live.
    Each value is set and read back; no reopen; state `checking`.

    The changes in order: gain 4, focus 40, gain auto, focus auto. Each is a new apply request with
    the config of 11.5 (`gain`, `gain_auto`, `focus`, `focus_auto`). "Read back": the status shows the
    value and the auto flag that were set."""
    script = FakeScript(controls=(("exposure", True, False, -6), ("gain", True, False, 0), ("focus", True, False, 30)))
    with capture_app(monkeypatch, [script], track=True) as app:
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app)
        ring = app.ring_name(camera_id)
        steps = [
            (dict(gain=4), "gain", False, 4),
            (dict(gain=4, focus=40), "focus", False, 40),
            (dict(gain=None, gain_auto=True, focus=40), "gain", True, None),
            (dict(gain=None, gain_auto=True, focus=None, focus_auto=True), "focus", True, None),
        ]
        for changes, name, auto, value in steps:
            _live_change(app, camera_id, **changes)
            setting = _settings_of(app, camera_id, name)[-1]
            assert setting.auto is auto and (value is None or setting.value == value), (name, setting)
            shown = app.status(camera_id)["controls"][name]
            assert shown["present"] is True and shown["auto"] is auto, (name, shown)
            if value is not None:
                assert shown["value"] == value, (name, shown)
        assert opens(app, camera_id) == 1 and app.ring_name(camera_id) == ring


def test_t_cap_73_a_control_that_the_camera_lacks(monkeypatch):
    """T-CAP-73, sections 8.4 and 11.5 [D43, agent 48]: a fake without focus; config with `focus: 40`.
    Status `present: false`; the set returns the error text of 11.5.

    The request with `focus: 40` is a live change of the running camera, so the main process knows
    from the status that the control is absent: HTTP 422 with `Camera {camera_id} has no focus
    control`, and the camera does not change (8.3, U10)."""
    script = FakeScript(controls=(("exposure", True, False, -6), ("gain", True, False, 0), ("focus", False, False, None)))
    with capture_app(monkeypatch, [script]) as app:
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app)
        assert app.status(camera_id)["controls"]["focus"]["present"] is False
        ring = app.ring_name(camera_id)
        refused = app.apply([app.config(camera_id, focus=40)])
        assert refused.status_code == 422, refused.text
        assert f"Camera {camera_id} has no focus control" in detail(refused)
        assert app.state(camera_id) == "ready" and app.ring_name(camera_id) == ring
        assert not _settings_of(app, camera_id, "focus"), "the fake got a focus set"


def test_t_cap_74_white_balance_and_power_line_frequency_in_the_recording_info(monkeypatch, tmp_path):
    """T-CAP-74, sections 11.5 and 11.6 [D43, D44, agent 32]: record with white balance and power line
    frequency values in the fake. Both are in the recording info; the fake gets no set call for either.

    The control names are those of the recording info of 11.6: `white_balance` and
    `power_line_frequency`."""
    controls = (("exposure", True, False, -6), ("gain", True, False, 0), ("focus", True, True, 30),
                ("white_balance", True, True, 4600), ("power_line_frequency", True, False, 2))
    with capture_app(monkeypatch, [FakeScript(controls=controls)]) as app:
        spies = Spies(monkeypatch, app)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        app.wait(lambda: len(spies.of("record", camera_id)) >= 30, "30 recorded frames")
        assert app.record_stop().status_code == 200
        capture = recording_info_json(tmp_path)["capture"][camera_id]
        assert capture["white_balance"] == {"auto": True, "value": 4600}
        assert capture["power_line_frequency"] == 2
        for name in ("white_balance", "power_line_frequency"):
            assert not _settings_of(app, camera_id, name), f"the fake got a set call for {name}"


def test_t_cap_75_status_shows_gain_and_focus_values_in_auto(monkeypatch):
    """T-CAP-75, sections 8.4 and 11.4 [D30, D43]: gain and focus in auto; the fake changes their values.
    The status shows the new values with `auto: true`.

    Real time: the control thread of U16 sleeps in real time between its reads (4.3), as in T-CAP-42."""
    with capture_app(monkeypatch, [FakeScript()], track=True, virtual=False) as app:
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, gain_auto=True, focus_auto=True)])
        app.factory.sources[camera_id].drift(gain=7, focus=45)

        def shown():
            controls = app.status(camera_id)["controls"]
            return (controls["gain"] == {"present": True, "auto": True, "value": 7}
                    and controls["focus"] == {"present": True, "auto": True, "value": 45})

        app.wait(shown, "the new gain and focus values with auto: true")


# ---------------------------------------------------------------------------
# T-CAP-107, T-CAP-108: controls with the OpenCV source (11.5, 14.1, V5)
# ---------------------------------------------------------------------------

def test_t_cap_107_opencv_gain_and_focus(monkeypatch):
    """T-CAP-107, sections 11.5 and 14.1 [V5, U14]: the OpenCV fake: (1) config with gain 4 and focus 40;
    (2) a live change to gain 6, and the fake reads back 5. (1) the fake gets `CAP_PROP_GAIN` 4 and
    `CAP_PROP_FOCUS` 40, and the status shows 4 and 40; (2) the camera stays `ready` with the same
    ring, the config keeps gain 4, and the apply response has a `control_change_failed` item for it.

    Real time: about 5 s."""
    factory = OpenCVFakeFactory(monkeypatch, misread=((cv2.CAP_PROP_GAIN, 6, 5),))
    app = CaptureApp(monkeypatch, factory)
    try:
        camera_id = factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, gain=4, focus=40)])
        sets = factory.captures[camera_id].sets
        assert (cv2.CAP_PROP_GAIN, 4.0) in sets and (cv2.CAP_PROP_FOCUS, 40.0) in sets, sets
        controls = app.status(camera_id)["controls"]
        assert (controls["gain"]["value"], controls["focus"]["value"]) == (4, 40), controls
        ring = app.ring_name(camera_id)
        response = app.apply([app.config(camera_id, gain=6, focus=40)])
        assert response.status_code == 200, response.text
        items = [w for w in response.json()["warnings"] if w["kind"] == "control_change_failed"]
        assert len(items) == 1 and items[0]["camera_ids"] == [camera_id], items
        assert response.json()["camera_configs"][camera_id]["gain"] == 4 and app.group.configs[camera_id].gain == 4
        time.sleep(1.0)
        assert app.state(camera_id) == "ready" and app.ring_name(camera_id) == ring
        assert factory.opens[camera_id] == 1
    finally:
        app.close()


WHITE_BALANCE_CASES = {
    "a value": ({cv2.CAP_PROP_WB_TEMPERATURE: 4600, cv2.CAP_PROP_AUTO_WB: 1}, {"auto": True, "value": 4600}),
    "no value": ({}, None),
}


@pytest.mark.parametrize("case", list(WHITE_BALANCE_CASES))
def test_t_cap_108_opencv_white_balance_and_power_line_frequency(monkeypatch, tmp_path, case):
    """T-CAP-108, sections 11.5, 11.6 and 14.1 [V5]: the OpenCV fake records: (1) the fake gives
    `CAP_PROP_WB_TEMPERATURE` 4600 and `CAP_PROP_AUTO_WB` 1; (2) it gives no white balance value.
    (1) `white_balance` is {"auto": true, "value": 4600}; (2) it is null; in both, `power_line_frequency`
    is null (OpenCV has no property for it); the fake gets no set call for white balance.

    "No value": `CAP_PROP_WB_TEMPERATURE` reads 0 (ADR-3WCA). Real time: about 5 s."""
    properties, expected = WHITE_BALANCE_CASES[case]
    factory = OpenCVFakeFactory(monkeypatch, properties=properties)
    app = CaptureApp(monkeypatch, factory)
    try:
        spies = Spies(monkeypatch, app)
        camera_id = factory.camera_ids[0]
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        app.wait(lambda: len(spies.of("record", camera_id)) >= 30, "30 recorded frames")
        assert app.record_stop().status_code == 200
        capture = recording_info_json(tmp_path)["capture"][camera_id]
        assert capture["white_balance"] == expected
        assert capture["power_line_frequency"] is None
        white_balance = (cv2.CAP_PROP_WB_TEMPERATURE, cv2.CAP_PROP_AUTO_WB)
        assert not [s for s in factory.captures[camera_id].sets if s[0] in white_balance]
    finally:
        app.close()


# ---------------------------------------------------------------------------
# T-CAP-76: the OpenCV source is gone on Windows (14.2)
# ---------------------------------------------------------------------------

HISTORY = ("decisions/", "specs/")  # the history documents (ADR-3WCA)
GONE = ("SKELLYCAM_WINDOWS_CAPTURE", "check_framerate_reset", "draw_doubled_text")


@pytest.mark.skip(reason="T-CAP-76 comes in the last commit of phase 3 and runs only after it (16.1); "
                         "that commit removes this mark")
@pytest.mark.skipif(sys.platform != "win32", reason="the OpenCV source is deleted on Windows only (14.2, 16.7 c)")
def test_t_cap_76_opencv_source_is_gone_on_windows():
    """T-CAP-76, sections 14.2 and 2.3 item 4 [D8, U2]: import the OpenCV source on Windows; search for
    `SKELLYCAM_WINDOWS_CAPTURE`, `check_framerate_reset`, `draw_doubled_text`. The import fails on
    Windows; no name is left outside history documents.

    The search reads the tracked files. The history documents are the files under `decisions/` and
    `specs/` (ADR-3WCA). This file names the three names, so the search leaves it out."""
    with pytest.raises(ImportError):
        importlib.import_module("skellycam.core.camera.capture.opencv_source")
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.split()
    me = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()
    left = []
    for path in tracked:
        if path.startswith(HISTORY) or path == me:
            continue
        try:
            text = (REPO_ROOT / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        left += [f"{path}: {name}" for name in GONE if name in text]
    assert not left, left
