"""Hardware tests of step 3c: T-CAP-77 to T-CAP-79 (specs/windows-capture.md, sections 2.3, 7.4, 11 and
16.3).

Each test has the marker `camera_hardware` and runs only with `SKELLYCAM_HARDWARE=1`, on the word of
the user, on the Windows development machine (16.7: no counterpart on Linux and macOS until phase 7,
reason e). Lights on. T-CAP-77 is a test of D49: it records results and has no pass value (16.3).
T-CAP-79 also needs `SKELLYCAM_HARDWARE_PROTOTYPE_MODES` (ADR-3WCA).
"""

import json
import os
import sys
import time
from pathlib import Path

import pytest

from skellycam.tests.capture.capture_hardware import GOOD, LABELS, hardware_app, kiyo_pro_rule, record_result
from skellycam.tests.capture.capture_session import StateWatcher, recording_info_json

pytestmark = [pytest.mark.camera_hardware,
              pytest.mark.skipif(sys.platform != "win32", reason="the step 3c cameras run on Windows")]

PROTOTYPE_MODES = os.environ.get("SKELLYCAM_HARDWARE_PROTOTYPE_MODES")


def mean_gray(app, camera_id, frames=30, timeout_s=10.0):
    """The mean gray level of `frames` new JPEG ring frames of the camera."""
    import cv2
    import numpy as np

    from skellycam.core.ipc.frame_ring import FrameRingReader, ReadResult

    reader = FrameRingReader.attach(app.ring_name(camera_id))
    seen, means = set(), []
    deadline = time.monotonic() + timeout_s
    try:
        while len(means) < frames and time.monotonic() < deadline:
            read = reader.read_newest()
            if read.result is ReadResult.OK and read.frame_number not in seen:
                seen.add(read.frame_number)
                means.append(float(cv2.imdecode(np.frombuffer(read.payload, np.uint8), cv2.IMREAD_GRAYSCALE).mean()))
            time.sleep(0.01)
    finally:
        reader.close()
    assert len(means) == frames, f"{len(means)} ring frames in {timeout_s} s"
    return sum(means) / frames


def open_alone(app, camera_id, **config):
    response = app.apply([app.config(camera_id, **config)])
    assert response.status_code == 200, response.text
    app.wait_state(camera_id, "ready", "failed", "dead")
    return app.status(camera_id)


def live_change(app, camera_id, **config):
    """A live change; returns the status after its rate check (10.2)."""
    watcher = StateWatcher(app, camera_id)
    try:
        response = app.apply([app.config(camera_id, **config)])
        assert response.status_code == 200, response.text
        app.wait(lambda: "checking" in watcher.first, f"checking after {config}")
        app.wait(lambda: app.state(camera_id) in ("ready", "too_slow"), f"the check after {config}")
    finally:
        watcher.stop()
    return response, app.status(camera_id)


@pytest.mark.parametrize("label", GOOD)
def test_t_cap_77_auto_values_and_the_image_after_manual(monkeypatch, label):
    """T-CAP-77, sections 11.4 and 16.3 [D49, D30]: with auto exposure and auto focus on, read the
    reported values; set manual with those values; compare the mean image before and after. For each
    camera: whether the reported values are true, and the image difference, are recorded.

    "Mean image": the mean gray level of 30 ring frames, 3 s after `ready` and 2 s after the rate
    check of the change. No pass value (16.3)."""
    with hardware_app(monkeypatch) as app:
        with kiyo_pro_rule(app, label, "T-CAP-77"):
            camera_id = app.camera_id(label)
            status = open_alone(app, camera_id, exposure_mode="AUTO", focus_auto=True)
            if status["state"] != "ready":
                record_result("T-CAP-77", camera=label, state=status["state"], failure=status.get("failure"))
                return
            time.sleep(3.0)
            reported = app.status(camera_id)["controls"]
            before = mean_gray(app, camera_id)
            changes = dict(exposure_mode="MANUAL", exposure=reported["exposure"]["value"])
            if reported["focus"]["present"]:
                changes.update(focus=reported["focus"]["value"], focus_auto=False)
            response, after_status = live_change(app, camera_id, **changes)
            time.sleep(2.0)
            after = mean_gray(app, camera_id)
            read_back = app.status(camera_id)["controls"]
            record_result("T-CAP-77", camera=label, reported=reported, read_back_after_manual=read_back,
                          values_kept={name: read_back[name]["value"] == reported[name]["value"]
                                       for name in ("exposure", "focus") if reported[name]["present"]},
                          state_after=after_status["state"], warnings=response.json().get("warnings"),
                          mean_gray_before=before, mean_gray_after=after, difference=after - before)


@pytest.mark.parametrize("label", LABELS)
def test_t_cap_78_gain_focus_white_balance_power_line_frequency(monkeypatch, tmp_path, label):
    """T-CAP-78, sections 11.5 and 11.6 [D43, D44]: set and read back gain and focus; read white balance
    and power line frequency, on four cameras. Each control that a camera has reads back the set
    value; absent ones show `present: false`; the read-only values are recorded.

    The set value differs from the current value: 0, or 1 for gain and 10 for focus when the current
    value is 0. The read-only values come from the recording info of a take of 1 s (11.6). A camera
    that does not reach `ready` (the generic camera fails the rate check, D24) gives its status
    and failure as a result, with no check of the values."""
    with hardware_app(monkeypatch) as app:
        with kiyo_pro_rule(app, label, "T-CAP-78"):
            camera_id = app.camera_id(label)
            status = open_alone(app, camera_id)
            if status["state"] != "ready":
                record_result("T-CAP-78", camera=label, state=status["state"], failure=status.get("failure"),
                              controls=status.get("controls"))
                return
            controls = status["controls"]
            targets = {name: (0 if controls[name]["value"] != 0 else step)
                       for name, step in (("gain", 1), ("focus", 10)) if controls[name]["present"]}
            changes = dict(targets)
            changes.update({f"{name}_auto": False for name in targets})
            if targets:
                _, status = live_change(app, camera_id, **changes)
            shown = status["controls"]
            assert app.record_start(tmp_path).status_code == 200
            time.sleep(1.0)
            assert app.record_stop().status_code == 200
            capture = recording_info_json(tmp_path)["capture"][camera_id]
            record_result("T-CAP-78", camera=label, targets=targets, controls=shown,
                          white_balance=capture.get("white_balance"),
                          power_line_frequency=capture.get("power_line_frequency"))
            for name, value in targets.items():
                assert shown[name]["value"] == value and shown[name]["auto"] is False, (name, shown[name])
            for name in ("gain", "focus"):
                assert name in targets or shown[name]["present"] is False, (name, shown[name])
            assert "white_balance" in capture and "power_line_frequency" in capture, capture


@pytest.mark.skipif(not PROTOTYPE_MODES, reason="needs the descriptor list of the prototype: "
                                                "SKELLYCAM_HARDWARE_PROTOTYPE_MODES (ADR-3WCA)")
def test_t_cap_79_capture_modes_agree_with_the_prototype(monkeypatch):
    """T-CAP-79, sections 2.3 item 3 and 7.4 [D14]: detect the four cameras. `capture_modes` agrees with
    the descriptor list of the prototype for each camera.

    The descriptor list is a JSON file outside the repository (`SKELLYCAM_HARDWARE_PROTOTYPE_MODES`):
    for each camera label, the native types of the prototype as `flag_types` of its `parse.py` gives
    them (`subtype`, `width`, `height`, `fps_num`, `fps_den`, `flags`). A type with a flag is a
    synthesized NV12 type, which 7.4 leaves out. "Agrees": the same set of (width, height, fps_num,
    fps_den, format)."""
    reference = json.loads(Path(PROTOTYPE_MODES).read_text(encoding="utf-8"))
    with hardware_app(monkeypatch) as app:
        assert sorted(app.devices) == sorted(LABELS), f"connected: {sorted(app.devices)}"
        differences = {}
        for label in LABELS:
            listed = {(m["width"], m["height"], m["fps_num"], m["fps_den"], m["format"])
                      for m in app.devices[label]["capture_modes"]}
            expected = {(t["width"], t["height"], t["fps_num"], t["fps_den"], t["subtype"])
                        for t in reference[label] if not t.get("flags")}
            if listed != expected:
                differences[label] = dict(only_listed=sorted(listed - expected), only_prototype=sorted(expected - listed))
        record_result("T-CAP-79", differences=differences)
        assert not differences, differences
