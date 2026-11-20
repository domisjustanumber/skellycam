"""Hardware tests for Linux and macOS: T-CAP-92 to T-CAP-98, the counterparts of the Windows hardware
tests that do not depend on Media Foundation [U21] (specs/windows-capture.md, 16.1, 16.3 to 16.7).

They use the OpenCV source of section 14.1 under the shared loop, with the same switches as the
Windows tests (`SKELLYCAM_HARDWARE=1`, `SKELLYCAM_HARDWARE_DARK=1`, `SKELLYCAM_HARDWARE_UNPLUG=1`,
`SKELLYCAM_HARDWARE_RESULTS`). They are skipped on Windows. They run on the Ubuntu and Mac machines of
the user on his word, in phase 0 through the certify suite. They are not part of the 3a done list.

Where OpenCV cannot give what a Windows criterion needs, the criterion of D46 and 14.1 applies: no
rate check when OpenCV reports no rate (`measured_fps` null), the forced auto exposure on Linux, and
no device-removed event (an unplug shows as 2 s without a frame).
"""

import os
import sys
import time

import cv2
import numpy as np
import pytest

from skellycam.tests.capture.capture_hardware import (
    GOOD, LABELS, SLOW_REASON, hardware_app, kiyo_pro_rule, record_result)
from skellycam.tests.capture.capture_session import (
    RingWatcher, Spies, StateWatcher, capture_logs, placeholders_to_the_stop, sfn_gaps, stop_line_count, take_rows)

pytestmark = [pytest.mark.camera_hardware,
              pytest.mark.skipif(sys.platform == "win32", reason="Linux and macOS; Windows runs T-CAP-51 to T-CAP-60")]


def open_alone(app, label, **config):
    camera_id = app.camera_id(label)
    response = app.apply([app.config(camera_id, **config)])
    assert response.status_code == 200, response.text
    app.wait_state(camera_id, "ready", "failed", "dead")
    return camera_id, app.status(camera_id)


def opencv_app(monkeypatch, **args):
    return hardware_app(monkeypatch, source="opencv", **args)


@pytest.mark.parametrize("label", GOOD)
def test_t_cap_92_open_each_camera_with_opencv(monkeypatch, label):
    """T-CAP-92, counterpart of T-CAP-52, sections 14.1 and 10.1 [U21, D46]: open the C922, the C930e and
    the Kiyo Pro at 1280x720 30 through the OpenCV source, one at a time. Each reaches `ready`; for 300
    frames the ring JPEG decodes to a 1280x720 image; the rate check passed (`measured_fps` within 3 % of
    30), also when OpenCV reports no rate: the check then uses the requested rate (ADR-PDD3 W2). A THREAD
    worker for the spies."""
    with opencv_app(monkeypatch, workers="thread") as app:
        with kiyo_pro_rule(app, label, "T-CAP-92"):
            spies = Spies(monkeypatch, app, keep_payloads=True)
            camera_id, status = open_alone(app, label)
            assert status["state"] == "ready", status
            assert status["measured_fps"] is not None and abs(status["measured_fps"] - 30.0) <= 0.9
            app.wait(lambda: len(spies.of("jpeg", camera_id)) >= 300, "300 ring frames")
            for event in spies.of("jpeg", camera_id)[:300]:
                image = cv2.imdecode(np.frombuffer(event["payload"], np.uint8), cv2.IMREAD_COLOR)
                assert image is not None and image.shape == (720, 1280, 3)
            record_result("T-CAP-92", camera=label, platform=sys.platform, measured_fps=status["measured_fps"])


RATES_93 = [(label, 30.0) for label in LABELS] + [("C922", 60.0), ("Kiyo Pro", 60.0)]


@pytest.mark.parametrize(("label", "rate"), RATES_93, ids=[f"{l} {r:g}" for l, r in RATES_93])
def test_t_cap_93_each_rate_at_720p_with_opencv(monkeypatch, label, rate):
    """T-CAP-93, counterpart of T-CAP-54, sections 10.1 and 16.3 [U21, D46, D49]: each camera at 1280x720:
    30 on each camera, 60 on the C922 and the Kiyo Pro. For each rate: the state, the measured rate and
    the failure are recorded; a rate-check failure gives the reason of 10.4. No pass value."""
    with opencv_app(monkeypatch) as app:
        with kiyo_pro_rule(app, label, "T-CAP-93"):
            camera_id, status = open_alone(app, label, framerate=rate)
            record_result("T-CAP-93", camera=label, platform=sys.platform, rate=rate, state=status["state"],
                          measured_fps=status.get("measured_fps"), failure=status.get("failure"))
            if status["failure"] and status["failure"]["stage"] == "rate check":
                assert SLOW_REASON.match(status["failure"]["reason"]), status["failure"]


def test_t_cap_94_generic_camera_with_opencv(monkeypatch):
    """T-CAP-94, counterpart of T-CAP-53, section 10.1 [U21, D24, D46]: open the generic camera at 1280x720
    30 through the OpenCV source: `failed`, stage `rate check`, the reason of 10.4 with a measured rate
    within 0.5 fps of 25.76. With no reported rate, the check uses the requested rate (ADR-PDD3 W2)."""
    with opencv_app(monkeypatch) as app:
        camera_id, status = open_alone(app, "generic")
        record_result("T-CAP-94", platform=sys.platform, status=status)
        assert status["failure"]["stage"] == "rate check", status
        match = SLOW_REASON.match(status["failure"]["reason"])
        assert match and match.group(1) == "30.00" and abs(float(match.group(2)) - 25.76) <= 0.5


@pytest.mark.skipif(os.environ.get("SKELLYCAM_HARDWARE_UNPLUG") != "1", reason="needs a person to unplug: SKELLYCAM_HARDWARE_UNPLUG=1")
def test_t_cap_95_unplug_during_a_recording_with_opencv(monkeypatch, tmp_path):
    """T-CAP-95, counterpart of T-CAP-58, sections 5.7, 8.2 and 9.5 [U21, D38, U4]: record with the C922 and
    the C930e; the user unplugs the C922 at 20 s. OpenCV gives no device-removed event, so the C922 is
    `dead` 2.0 to 2.5 s after its last ring frame (the stall rule); the C930e records to the stop; changed
    by step 5a: the manifest has `camera_dead` for the C922, and its file has placeholders to the stop."""
    with opencv_app(monkeypatch) as app:
        c922, c930e = app.camera_id("C922"), app.camera_id("C930e")
        assert app.apply([app.config(c922), app.config(c930e)]).status_code == 200
        for camera_id in (c922, c930e):
            app.wait_state(camera_id, "ready")
        ring = RingWatcher(app.ring_name(c922))
        watcher = StateWatcher(app, c922)
        try:
            assert app.record_start(tmp_path).status_code == 200
            print("\nT-CAP-95: unplug the C922 in 20 s", flush=True)
            app.wait(lambda: "dead" in watcher.first, "the C922 is unplugged", timeout=120)
            elapsed = (watcher.first["dead"] - ring.frames[-1][1]) / 1e9
            assert 2.0 <= elapsed <= 2.5, f"dead {elapsed:.3f} s after its last frame"
            time.sleep(10)
            assert app.state(c930e) == "recording"
            assert app.record_stop().status_code == 200
        finally:
            watcher.stop()
            ring.stop()
        dead, rows = placeholders_to_the_stop(tmp_path, c922)
        record_result("T-CAP-95", platform=sys.platform, dead=dead, rows=len(rows), seconds_after_last_frame=elapsed)


@pytest.mark.skipif(os.environ.get("SKELLYCAM_HARDWARE_DARK") != "1", reason="needs a dark room: SKELLYCAM_HARDWARE_DARK=1")
@pytest.mark.parametrize("label", LABELS)
def test_t_cap_96_dark_room_with_opencv(monkeypatch, label):
    """T-CAP-96, counterpart of T-CAP-55, section 16.3 [U21, D49]: each camera opened in a dark room with
    auto exposure, through the OpenCV source. For each camera: state, measured rate and reason are
    recorded; no traceback. A THREAD worker for the log records."""
    with capture_logs() as logs, opencv_app(monkeypatch, workers="thread") as app:
        with kiyo_pro_rule(app, label, "T-CAP-96"):
            camera_id, status = open_alone(app, label, exposure_mode="AUTO")
            record_result("T-CAP-96", camera=label, platform=sys.platform, state=status["state"],
                          measured_fps=status.get("measured_fps"), failure=status.get("failure"))
    assert not logs.tracebacks(), logs.tracebacks()


@pytest.mark.parametrize("label", GOOD)
def test_t_cap_97_exposure_steps_with_opencv(monkeypatch, label):
    """T-CAP-97, counterpart of T-CAP-57, sections 10.2, 11.2 and 14.1 [U21, D32, D46]: open at MANUAL -8;
    exposure steps -7, -6, -5, -4 while open. Each change gives `checking`, then `ready` or `too_slow`;
    with no reported rate, the check uses the requested rate (ADR-PDD3 W2). The states, rates and read-back values are recorded. There is no predicted state: table 10.5 holds
    Media Foundation values, and on Linux the OpenCV source forces auto exposure (14.1)."""
    with opencv_app(monkeypatch) as app:
        with kiyo_pro_rule(app, label, "T-CAP-97"):
            camera_id, status = open_alone(app, label, exposure=-8)
            assert status["state"] == "ready", status
            for exposure in (-7, -6, -5, -4):
                watcher = StateWatcher(app, camera_id)
                try:
                    assert app.apply([app.config(camera_id, exposure=exposure)]).status_code == 200
                    app.wait(lambda: "checking" in watcher.first, f"checking at {exposure}")
                    app.wait(lambda: app.state(camera_id) in ("ready", "too_slow"), f"the check at {exposure}")
                finally:
                    watcher.stop()
                status = app.status(camera_id)
                record_result("T-CAP-97", camera=label, platform=sys.platform, exposure=exposure, state=status["state"],
                              measured_fps=status["measured_fps"], controls=status.get("controls"))


def test_t_cap_98_comparison_run_with_opencv(monkeypatch, tmp_path):
    """T-CAP-98, counterpart of T-CAP-60, section 16.4 [U21, D48, U3]: the C922, the C930e and the Kiyo Pro
    at 1280x720 30 fps through the OpenCV source in the shared loop, lockstep, one recording of 60 s.
    Equal frame counts across cameras; a group rate from 29.7 to 30.3; for each camera, the gaps of
    `source_frame_number` equal its replaced count of the stop line (for a pull source both are 0).
    The reference run with the OpenCV loop of today is a separate run in a second worktree. A THREAD
    worker for the spies."""
    with capture_logs() as logs, opencv_app(monkeypatch, workers="thread") as app:
        spies = Spies(monkeypatch, app)
        ids = [app.camera_id(label) for label in GOOD]
        assert app.apply([app.config(cid) for cid in ids]).status_code == 200
        for camera_id in ids:
            app.wait_state(camera_id, "ready")
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(60.0)
        stopped = app.record_stop()
        assert stopped.status_code == 200, stopped.text
        app.client.delete("/skellycam/camera/group/close/all")
        summary = stopped.json()[0]
        counts = {cid: len(take_rows(tmp_path, cid)) for cid in ids}
        replaced = {cid: (stop_line_count(logs.messages(), cid), sfn_gaps([e["sfn"] for e in spies.of("jpeg", cid)]))
                    for cid in ids}
        record_result("T-CAP-98", platform=sys.platform, counts=counts, summary=summary, replaced_and_gaps=replaced)
        assert len(set(counts.values())) == 1, counts
        assert 29.7 <= summary["mean_framerate"] <= 30.3, summary
        assert all(count == gaps for count, gaps in replaced.values()), replaced
