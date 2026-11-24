"""Camera states, start-up, live changes, recordings with warnings and dead cameras, and the group
rules (specs/windows-capture.md, sections 5.2, 5.7, 5.8, 7.5, 8 to 12).

T-CAP-13, 14, 19 to 21, 29 to 38, 42, 81, 83, 84, 86, 90, 91, 105, 107, 108, 112 and 113. Each test runs fake cameras
through the HTTP endpoints with THREAD workers and a virtual clock (`capture_session`). A
`StateTracker` keeps the state of each camera at each read of a fake, with the virtual time.
"""

import dataclasses
import json
import logging
import threading
import time

import pytest

from skellycam.tests.capture.capture_session import (
    Spies, camera_key_of, capture_app, capture_logs, numbers_in, one_camera, parse_relay, product, ready_app_steps,
    sfn_gaps, spy_check_anchors, stop_line_count, take_rows, too_slow_after_the_window_start)
from skellycam.tests.capture.fake_source import FakeScript

FRAME_NS = round(1e9 / 30)
MODES_30_60 = ((640, 480, 30, 1, "MJPG"), (640, 480, 60, 1, "MJPG"), (320, 240, 30, 1, "MJPG"))


def opens(app, camera_id):
    return app.factory.logs[camera_id].opens.value


def detail(response):
    return json.dumps(response.json().get("detail"))


# ---------------------------------------------------------------------------
# Start-up: warm-up, wait for the others, ready limit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("late_first_write", [False, True], ids=["as it comes", "late first write"])
def test_t_cap_13_warm_up_and_wait_for_the_others(monkeypatch, late_first_write):
    """T-CAP-13, sections 9.2 and 9.4 [D21, agent 51]: two fake cameras; one opens 3 s later. The first
    90 frames after read-back reach neither the ring nor the recorder; the first camera is `waiting`
    and paused until the second has passed its check; then both are `ready`.

    "late first write": each camera loop stops for 0.5 s after it sets `ready`, so its first ring write
    comes after the test sees `ready`. This is the order of the CI failures of d8989972d."""
    if late_first_write:
        status_class = product("skellycam.core.camera_group.camera_status").CameraStatus
        set_state = status_class.set_state

        def set_state_then_stop(self, state):
            set_state(self, state)
            if state == "ready":
                time.sleep(0.5)
        monkeypatch.setattr(status_class, "set_state", set_state_then_stop)
    with capture_app(monkeypatch, [FakeScript(), FakeScript(open_delay_s=3.0)], track=True) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        first, second = app.factory.camera_ids
        for camera_id in (first, second):
            # A camera is `ready` before its first ring write: wait for that write, then examine it.
            app.wait(lambda: spies.of("jpeg", camera_id), f"camera {camera_id}: the first ring write")
            start = app.factory.logs[camera_id].first_sfn_after_readback
            writes = spies.of("jpeg", camera_id)
            assert writes[0]["sfn"] >= start + 90, f"camera {camera_id}: a warm-up frame reached the ring"
        assert not spies.of("record")
        passed = min(t for t, s in app.tracker.states(second) if s in ("waiting", "ready"))
        waited = [t for t, s in app.tracker.states(first) if s == "waiting"]
        assert waited and waited[0] < passed, "the first camera was not `waiting` while the second started"
        early = [e for e in spies.of("jpeg", first) if e["arrival_ns"] < passed - FRAME_NS - 1_000_000]
        assert not early, "the first camera was not paused while it waited"


def test_t_cap_14_not_ready_in_15_s(monkeypatch):
    """T-CAP-14, section 9.3 [D21, agent 14, agent 48]: one fake with mode rate 30. Its first frame comes
    0.2 s after the first `ReadSample`; from then on it delivers 5 fps, so that 90 warm-up frames
    need 18 s. Failed, stage `warm-up`, reason "not ready in 15 s", at 15.0 to 15.5 s after the open.

    The failed camera stops reading, so the virtual clock stops at the time of the decision."""
    with one_camera(monkeypatch, FakeScript(first_frame_delay_s=0.2, rate=5.0)) as (app, camera_id, response):
        status = app.status(camera_id)
        assert status["state"] == "failed"
        assert status["failure"] == {"camera_id": camera_id, "stage": "warm-up", "reason": "not ready in 15 s",
                                     "code": "not-ready"}
        open_ns = next(t for name, t, _ in app.factory.logs[camera_id].events if name == "open")
        elapsed = (app.clock.now_ns() - open_ns) / 1e9
        assert 15.0 <= elapsed <= 15.5, f"failed {elapsed:.3f} s after the open"


# ---------------------------------------------------------------------------
# A failed camera: T-CAP-19 to T-CAP-21
# ---------------------------------------------------------------------------

def start_with_one_in_use(app):
    """The set-up of T-CAP-19: three fakes; the third is in use at its first open."""
    app.detect()
    response = app.apply([app.config(cid) for cid in app.factory.camera_ids])
    assert response.status_code == 200, response.text
    good, failed = app.factory.camera_ids[:2], app.factory.camera_ids[2]
    for camera_id in good:
        app.wait_state(camera_id, "ready")
    app.wait_state(failed, "failed")
    return response, good, failed


IN_USE_ONCE = [FakeScript(), FakeScript(), FakeScript(fail_opens=(1,))]


def test_t_cap_19_a_camera_in_use_fails_alone(monkeypatch, tmp_path):
    """T-CAP-19, sections 8.2, 8.3 and 12 [D13, D23]: three fakes; one is in use at open. That camera is
    `failed` with "in use by another program"; the other two reach `ready` with preview; a record
    start returns 409 and names it; after 60 s, its open count is still 1."""
    with capture_app(monkeypatch, IN_USE_ONCE) as app:
        spies = Spies(monkeypatch, app)
        response, good, failed = start_with_one_in_use(app)
        assert app.status(failed)["failure"] == {"camera_id": failed, "stage": "open",
                                                 "reason": "in use by another program", "code": "open-failed"}
        assert response.json()["camera_failures"][failed]["reason"] == "in use by another program"
        for camera_id in good:
            count = len(spies.of("jpeg", camera_id))
            app.wait(lambda: len(spies.of("jpeg", camera_id)) > count + 10, f"preview of {camera_id}")
        refused = app.record_start(tmp_path)
        assert refused.status_code == 409 and failed in detail(refused)
        app.wait_clock(60.0)
        assert opens(app, failed) == 1, "skellycam opened the failed camera again by itself"


def test_t_cap_20_apply_again_reopens_only_the_failed_camera(monkeypatch):
    """T-CAP-20, sections 8.2 and 8.3 [D23, D25, Z7F3]: after T-CAP-19: (0) apply the same configs, then a changed
    exposure of a good camera, with no retry list: the failed camera stays `failed` and is not opened again;
    (1) apply the same configs again with the failed camera in `retry_camera_ids`;
    (2) fail the camera again and apply it with a changed exposure; (3) apply a request that gives all
    three cameras the rate 60. (1) and (2): only the failed camera opens again, in (2) with the new
    exposure; the ring names and the process IDs of the others do not change. (3): each camera reopens
    at 60.

    The camera fails again at its second open, the reopen of (1). With THREAD workers, the "process"
    of a camera is its worker object; the test compares the object and its `pid`."""
    scripts = [FakeScript(modes=MODES_30_60), FakeScript(modes=MODES_30_60),
               FakeScript(modes=MODES_30_60, fail_opens=(1, 2))]
    with capture_app(monkeypatch, scripts) as app:
        _, good, failed = start_with_one_in_use(app)
        before = {cid: (app.ring_name(cid), app.worker(cid), app.worker(cid).worker.pid) for cid in good}

        def others_unchanged():
            for camera_id in good:
                assert opens(app, camera_id) == 1
                ring, worker, pid = before[camera_id]
                assert app.ring_name(camera_id) == ring
                assert app.worker(camera_id) is worker and worker.worker.pid == pid

        # (0) [Z7F3]: a live settings change never restarts a camera: with no retry list the failed camera stays
        assert app.apply([app.config(cid) for cid in app.factory.camera_ids]).status_code == 200
        response = app.apply([app.config(good[0], exposure=-8), app.config(good[1]), app.config(failed)])
        assert response.status_code == 200, response.text
        app.wait(lambda: app.status(good[0])["controls"]["exposure"]["value"] == -8, "the live change")
        app.wait_clock(5.0)
        assert app.state(failed) == "failed" and opens(app, failed) == 1
        others_unchanged()
        assert app.apply([app.config(cid) for cid in app.factory.camera_ids], retry=[failed]).status_code == 200  # (1)
        app.wait(lambda: opens(app, failed) == 2, "the failed camera opens again")
        app.wait_state(failed, "failed")
        others_unchanged()
        configs = [app.config(cid) for cid in good] + [app.config(failed, exposure=-6)]
        assert app.apply(configs, retry=[failed]).status_code == 200  # (2)
        app.wait_state(failed, "ready")
        assert opens(app, failed) == 3
        settings = [s["exposure"] for s in app.factory.logs[failed].settings if "exposure" in s]
        assert settings[-1].value == -6, "the reopen did not use the new exposure"
        others_unchanged()
        assert app.apply([app.config(cid, framerate=60.0) for cid in app.factory.camera_ids]).status_code == 200  # (3)
        for camera_id in app.factory.camera_ids:
            app.wait(lambda: app.state(camera_id) == "ready" and app.status(camera_id)["mode"]["fps_num"] == 60,
                     f"camera {camera_id} at 60")
        assert [opens(app, cid) for cid in app.factory.camera_ids] == [2, 2, 4]


def test_a_plain_apply_reports_a_failed_camera_that_it_leaves_alone(monkeypatch):
    """windows-capture.md 8.3 [Z7F3] (review finding 1, 10): an apply that names a failed camera but not in
    `retry_camera_ids` leaves it alone and says so: its failure is in `camera_failures`, and one warning
    `camera_not_retried` names `retry_camera_ids`. A later rate pick gives its stored config the new rate, with no
    open, so the group keeps one rate."""
    scripts = [FakeScript(modes=MODES_30_60), FakeScript(modes=MODES_30_60), FakeScript(modes=MODES_30_60, fail_opens=(1,))]
    with capture_app(monkeypatch, scripts) as app:
        _, good, failed = start_with_one_in_use(app)
        response = app.apply([app.config(cid) for cid in good] + [app.config(failed, exposure=-9)])
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["camera_failures"][failed]["reason"] == "in use by another program", body
        items = [w for w in body["warnings"] if w["kind"] == "camera_not_retried"]
        assert [w["camera_ids"] for w in items] == [[failed]] and "retry_camera_ids" in items[0]["text"], body["warnings"]
        response = app.apply([app.config(cid, framerate=60.0) for cid in app.factory.camera_ids])
        assert response.status_code == 200, response.text
        assert app.group.configs[failed].framerate == 60.0
        app.wait_clock(3.0)
        assert app.state(failed) == "failed" and opens(app, failed) == 1


def test_t_cap_21_unselect_the_failed_camera(monkeypatch, tmp_path):
    """T-CAP-21, sections 8.2 and 8.3 [D23, agent 24]: after T-CAP-19, apply with `use_this_camera:
    false` for the failed camera. The camera leaves the group; a record start succeeds with two
    cameras."""
    with capture_app(monkeypatch, IN_USE_ONCE) as app:
        _, good, failed = start_with_one_in_use(app)
        configs = [app.config(cid) for cid in good] + [app.config(failed, use_this_camera=False)]
        assert app.apply(configs).status_code == 200
        app.wait(lambda: failed not in app.group.configs, "the camera leaves the group")
        started = app.record_start(tmp_path)
        assert started.status_code == 200, started.text
        assert started.json()["started"] is True
        assert app.record_stop().status_code == 200


# ---------------------------------------------------------------------------
# One rate per group, live changes, checks: T-CAP-29 to T-CAP-33
# ---------------------------------------------------------------------------

def test_t_cap_29_one_mode_rate_per_group(monkeypatch):
    """T-CAP-29, section 7.5 [D18, U7]: group of two with mode rates 30 and 60; group of two with -1 that
    both give 30. The first apply fails and opens no camera; the second opens both."""
    with capture_app(monkeypatch, [FakeScript(modes=MODES_30_60), FakeScript(modes=MODES_30_60)]) as app:
        app.detect()
        first, second = app.factory.camera_ids
        refused = app.apply([app.config(first, framerate=30.0), app.config(second, framerate=60.0)])
        assert refused.status_code == 422, refused.text
        assert opens(app, first) == opens(app, second) == 0
        response = app.apply([app.config(first, framerate=-1.0), app.config(second, framerate=-1.0)])
        assert response.status_code == 200, response.text
        for camera_id in (first, second):
            app.wait_state(camera_id, "ready")
            assert app.status(camera_id)["mode"]["fps_num"] == 30


def test_t_cap_30_live_exposure_change_and_resolution_reopen(monkeypatch):
    """T-CAP-30, sections 8.2 and 11.2 [D31]: change the exposure, then the resolution, of one camera of
    two. Exposure: no reopen, same ring name, state `checking`; resolution: only that camera reopens,
    new rings, warm-up and rate check again; the other camera keeps its preview."""
    with capture_app(monkeypatch, [FakeScript(modes=MODES_30_60), FakeScript(modes=MODES_30_60)], track=True) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        changed, other = app.factory.camera_ids
        ring = app.ring_name(changed)
        t_exposure = app.clock.now_ns()
        assert app.apply([app.config(changed, exposure=-6), app.config(other)]).status_code == 200
        app.wait(lambda: app.tracker.first(changed, "checking", t_exposure) is not None, "state checking")
        app.wait_state(changed, "ready")
        assert opens(app, changed) == 1 and app.ring_name(changed) == ring
        t_resize = app.clock.now_ns()
        assert app.apply([app.config(changed, width=320, height=240), app.config(other)]).status_code == 200
        app.wait(lambda: app.ring_name(changed) != ring and app.state(changed) == "ready", "the reopen")
        t_starting = app.tracker.first(changed, "starting", t_resize)
        assert t_starting is not None
        # The tracker samples on a fake read; the wait above reads the status directly (review item 8)
        app.wait(lambda: app.tracker.first(changed, "ready", t_starting) is not None, "the tracker sees ready")
        t_ready = app.tracker.first(changed, "ready", t_starting)
        assert (opens(app, changed), opens(app, other)) == (2, 1)
        # `ready` can come before the first JPEG reaches the new ring (review item 8)
        app.wait(lambda: any(e["ring"] == app.ring_name(changed) for e in spies.of("jpeg", changed)),
                 "a frame in the new ring")
        new_ring = [e for e in spies.of("jpeg", changed) if e["ring"] == app.ring_name(changed)]
        assert new_ring[0]["sfn"] >= app.factory.logs[changed].first_sfn_after_readback + 90, "no warm-up after the reopen"
        assert app.status(changed)["measured_fps"] is not None
        assert [e for e in spies.of("jpeg", other) if t_starting <= e["arrival_ns"] <= t_ready], \
            "the other camera had no preview while the camera reopened"


def test_t_cap_31_the_skip_counts_the_frames_of_a_slow_set(monkeypatch):
    """T-CAP-31, 10.2 [ADR-53VB]: the live set takes 0.2 s of clock time, so about 6 frames arrive during the set,
    and the loop takes them before it reads the result of the change. The skip counts them: the window starts
    at the 16th frame after the start of the set, as with a set that takes no time."""
    script = FakeScript(rate_after_change=(20.0,), live_set_delay_s=0.2)
    with one_camera(monkeypatch, script, track=True) as (app, camera_id, _):
        anchors = spy_check_anchors(monkeypatch)
        assert app.apply([app.config(camera_id, exposure=-6)]).status_code == 200
        app.wait_state(camera_id, "too_slow")
        log = app.factory.logs[camera_id]
        t_set = [t for name, t, d in log.events if name == "set_controls" and d.get("exposure")][-1]
        during = [k for k, (arrival, _) in log.frames.items() if t_set < arrival <= t_set + 200_000_000]
        assert len(during) >= 5, during  # frames came during the set
        too_slow_after_the_window_start(app, camera_id, anchors)


def test_t_cap_31_too_slow_after_a_live_change(monkeypatch, tmp_path):
    """T-CAP-31, section 10.2 [D32, D33]: after a live change, the fake goes to 20 fps; after a later
    change, to 30 fps. State `checking`, then `too_slow` at t_a + 59 / (0.97 x 30) s = t_a + 2.0275 s,
    within +/-25 ms, where t_a is the arrival of the first frame of the window; this is before the
    window could end at 20 fps (t_a + 2.95 s); preview continues; record start returns 409; the next
    change at 30 fps gives `ready`.

    The window starts at the 16th frame that the fake delivers after the change (skip 15): skipped frame 1 is
    the first frame whose arrival is after the time read just before the set (10.2) [ADR-53VB]."""
    script = FakeScript(rate_after_change=(20.0, 30.0))
    with one_camera(monkeypatch, script, track=True) as (app, camera_id, _):
        spies = Spies(monkeypatch, app)
        anchors = spy_check_anchors(monkeypatch)
        assert app.apply([app.config(camera_id, exposure=-6)]).status_code == 200
        app.wait_state(camera_id, "too_slow")
        t_a, t_slow = too_slow_after_the_window_start(app, camera_id, anchors)
        assert t_slow < t_a + round(59 / 20 * 1e9)
        app.wait(lambda: any(e["arrival_ns"] > t_slow for e in spies.of("jpeg")), "preview after too_slow")
        refused = app.record_start(tmp_path)
        assert refused.status_code == 409 and camera_id in detail(refused)
        assert app.apply([app.config(camera_id, exposure=-5)]).status_code == 200
        app.wait_state(camera_id, "ready")


def test_measured_fps_after_too_slow_is_the_rate_of_the_check(monkeypatch):
    """Sections 8.4 and 10.2, first hardware run of 3a: after a live change, the fake goes to 20 fps, and the
    early decision gives `too_slow`. `measured_fps` is then the rate of the check (the delivered frames of
    the window over its time up to the decision), not the 30 fps of the earlier check."""
    with one_camera(monkeypatch, FakeScript(rate_after_change=(20.0,))) as (app, camera_id, _):
        assert abs(app.status(camera_id)["measured_fps"] - 30.0) <= 0.9
        assert app.apply([app.config(camera_id, exposure=-6)]).status_code == 200
        app.wait_state(camera_id, "too_slow")
        measured = app.status(camera_id)["measured_fps"]
        assert measured < 0.97 * 30 and abs(measured - 20.0) <= 1.0, f"measured_fps {measured}"


def test_t_cap_32_no_recording_while_checking(monkeypatch, tmp_path):
    """T-CAP-32, sections 8.3 and 10.2 [D33]: start a recording while a camera is `checking`. 409, the
    detail names the camera and `checking`.

    The fake holds its first read after the change, so the check cannot end before the request."""
    with capture_app(monkeypatch, [FakeScript(hold_after_change=True), FakeScript()]) as app:
        ready_app_steps(app)
        checking, other = app.factory.camera_ids
        assert app.apply([app.config(checking, exposure=-6), app.config(other)]).status_code == 200
        source = app.factory.sources[checking]
        assert source.holding.wait(30)
        try:
            assert app.state(checking) == "checking"
            refused = app.record_start(tmp_path)
            assert refused.status_code == 409
            assert checking in detail(refused) and "checking" in detail(refused)
        finally:
            source.release()
        app.wait_state(checking, "ready")


def test_t_cap_33_no_change_during_a_recording(monkeypatch, tmp_path):
    """T-CAP-33, sections 8.3 and 11.2 [D36]: apply a change during a recording. 409; the camera config
    and the ring name do not change."""
    with capture_app(monkeypatch, [FakeScript()]) as app:
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        config, ring = app.group.configs[camera_id], app.ring_name(camera_id)
        settings = len(app.factory.logs[camera_id].settings)
        assert app.record_start(tmp_path).status_code == 200
        try:
            refused = app.apply([app.config(camera_id, exposure=-5)])
            assert refused.status_code == 409, refused.text
            assert app.group.configs[camera_id] == config and app.ring_name(camera_id) == ring
            assert not [s for s in app.factory.logs[camera_id].settings[settings:] if s]
        finally:
            assert app.record_stop().status_code == 200


# ---------------------------------------------------------------------------
# Recordings: auto warning, dead camera, stall, slow camera (T-CAP-34 to T-CAP-37)
# ---------------------------------------------------------------------------

def test_t_cap_34_auto_exposure_at_record_start(monkeypatch, tmp_path):
    """T-CAP-34, sections 11.3 and 11.6 [D37, agent 33], changed by step 5a (recorder.md section 14) and by
    camera-requests.md 1.10 (16.2): the fake reports its exposure in auto (a script value), with the config in
    `MANUAL`. The recording starts; the response `warnings` holds the camera, `exposure` and the text of 11.3;
    the status shows the same item; the log has the text; the capture info has `controls.exposure_us.auto`
    true."""
    with capture_logs() as logs, capture_app(monkeypatch, [FakeScript(reports_auto=("exposure",))]) as app:
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id)])
        text = f"Camera {camera_id}: exposure is in auto mode at the start of the recording"
        item = {"kind": "auto_control", "camera_ids": [camera_id], "control": "exposure", "text": text}
        started = app.record_start(tmp_path)
        assert started.status_code == 200, started.text
        assert started.json() == {"started": True, "warnings": [item]}
        status = app.status(camera_id)
        assert item in status["warnings"] and status["controls"]["exposure"]["auto"] is True
        assert any(text in message for message in logs.messages(logging.WARNING))
        assert app.record_stop().status_code == 200
        info = json.loads((tmp_path / "take" / "take_info.json").read_text(encoding="utf-8"))
        assert info["skellyfileformat"] == "capture_info"
        assert info["camera_configs"][camera_key_of(tmp_path, camera_id)]["controls"]["exposure_us"]["auto"] is True


def test_t_cap_36_dead_after_2_s_without_a_frame(monkeypatch):
    """T-CAP-36, sections 9.5 and 6.7 [D38]: one fake stops delivering at frame 100. `dead` between 2.0
    and 2.25 s after its last arrival, not before.

    The fake stops after `ready` (as in T-CAP-81), so that the camera cannot be `dead` before the test
    sees `ready`. The dead camera stops reading, so the virtual clock stops at the time of the decision."""
    with one_camera(monkeypatch, FakeScript()) as (app, camera_id, _):
        app.factory.sources[camera_id].stop_now()
        app.wait_state(camera_id, "dead")
        frames = app.factory.logs[camera_id].frames
        elapsed = (app.clock.now_ns() - frames[max(frames)][0]) / 1e9
        assert 2.0 <= elapsed <= 2.25, f"dead {elapsed:.3f} s after the last arrival"


def test_t_cap_37_slow_camera_during_a_recording(monkeypatch, tmp_path):
    """T-CAP-37, section 10.3 [D39, agent 28]: during a recording, one fake goes to 27 fps for 5 s, then
    back to 30. One warning with the camera and the rate; the recording continues; a later slow period
    gives one more warning.

    The warned rate is the rate of the first block below the limit: from 27 to 29.1 fps."""
    with capture_logs() as logs, capture_app(monkeypatch, [FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        source = app.factory.sources[camera_id]
        assert app.record_start(tmp_path).status_code == 200

        def slow_warnings():
            return [m for m in logs.messages(logging.WARNING)
                    if camera_id in m and any(26.9 <= n < 29.1 for n in numbers_in(m))]

        for period in (1, 2):
            source.slow_period(rate=27.0, seconds=5.0)
            app.wait(lambda: source.slow_finished_ns is not None, f"slow period {period}")
            app.wait_clock(5.0, "normal rate after the slow period")
            assert len(slow_warnings()) == period, slow_warnings()
        count = len(spies.of("record"))
        app.wait(lambda: len(spies.of("record")) > count + 30, "the recording continues")
        assert app.record_stop().status_code == 200


# ---------------------------------------------------------------------------
# T-CAP-38: failure object and its queue
# ---------------------------------------------------------------------------

def test_t_cap_38_failure_object_first_failure_and_order():
    """T-CAP-38, section 12 [D40, U9, agent 35]: two failures of one camera, then a group shutdown. The
    object has `camera_id`, `stage`, `reason`; the text is `Camera {id} failed during {stage}:
    {reason}`; the first failure stays; it is in the queue before the flag changes."""
    import multiprocessing
    import time

    from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
    from skellycam.core.camera_group.camera_setup_failure import CameraSetupFailure
    from skellycam.core.ipc.pubsub.pubsub_manager import PubSubTopicManager

    ipc = CameraGroupIPC(group_id="t-cap-38", pubsub=PubSubTopicManager(topics={}),
                         extracted_config_subscription=multiprocessing.Queue(),
                         recording_finished_subscription=multiprocessing.Queue(),
                         diagnostics_subscription=multiprocessing.Queue(),
                         global_kill_flag=multiprocessing.Value("b", False),
                         heartbeat_timestamp=multiprocessing.Value("d", time.perf_counter()))
    first = CameraSetupFailure(camera_id="a1b2", stage="open", reason="in use by another program")
    second = CameraSetupFailure(camera_id="a1b2", stage="close", reason="close did not return in 5 s")
    assert dataclasses.asdict(first) == {"camera_id": "a1b2", "stage": "open", "reason": "in use by another program"}
    assert str(first) == "Camera a1b2 failed during open: in use by another program"
    seen = []

    def watch():
        while not ipc.shutdown_camera_group_flag.value:
            time.sleep(0.0001)
        seen.append(ipc.take_setup_failure())

    watcher = threading.Thread(target=watch)
    watcher.start()
    ipc.report_setup_failure(first)
    assert not ipc.shutdown_camera_group_flag.value, "a start failure must not shut down the group [D23]"
    ipc.report_setup_failure(second)
    ipc.should_continue = False  # the group shutdown
    watcher.join(5)
    assert seen == [first]
    assert ipc.take_setup_failure() is None, "the second failure of the camera was kept"


# ---------------------------------------------------------------------------
# T-CAP-42: current control values in auto mode
# ---------------------------------------------------------------------------

def test_t_cap_42_status_shows_values_that_change_in_auto(monkeypatch):
    """T-CAP-42, sections 8.4 and 11.4 [D30, agent 31], changed by camera-requests.md 1.10 (16.2): the fake
    reports its exposure in auto with no set through the config (`MANUAL -7`); the fake changes its exposure
    to -5, its gain from 0 to 4 and its focus from 30 to 40. Within 2 s, the status shows `exposure` with
    `auto: true` and `value: -5`, and the new gain and focus values.

    Real time: the control thread of U16 sleeps in real time between its reads (4.3)."""
    with capture_app(monkeypatch, [FakeScript(reports_auto=("exposure",))], track=True, virtual=False) as app:
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id)])
        source = app.factory.sources[camera_id]
        t_drift = time.perf_counter_ns()
        source.drift(exposure=-5, gain=4, focus=40)

        def shown():
            for t, cid, _, controls in app.tracker.history:
                if cid == camera_id and t >= t_drift and controls and controls["exposure"] == \
                        {"present": True, "auto": True, "value": -5} and controls["gain"]["value"] == 4 \
                        and controls["focus"]["value"] == 40:
                    return t
            return None

        app.wait(lambda: shown() is not None, "the new values in the status")
        assert (shown() - t_drift) / 1e9 <= 2.0


# ---------------------------------------------------------------------------
# T-CAP-81, T-CAP-83, T-CAP-84: dead without recording; floor of 30 fps; whole request
# ---------------------------------------------------------------------------

def test_t_cap_81_dead_without_recording_is_treated_as_failed(monkeypatch, tmp_path):
    """T-CAP-81, sections 8.2 and 8.3 [U6, D38]: two fakes, no recording; one stops delivering. It is
    `dead` and treated as `failed`: a record start returns 409; an apply reopens only it."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        ready_app_steps(app)
        alive, dying = app.factory.camera_ids
        app.factory.sources[dying].stop_now()
        app.wait_state(dying, "dead")
        refused = app.record_start(tmp_path)
        assert refused.status_code == 409 and dying in detail(refused)
        assert app.apply([app.config(cid) for cid in app.factory.camera_ids], retry=[dying]).status_code == 200
        app.wait_state(dying, "ready")
        assert (opens(app, alive), opens(app, dying)) == (1, 2)


def test_t_req_79_the_group_stays_alive_while_one_selected_camera_lives(monkeypatch):
    """T-REQ-79, camera-requests.md 1.5 [NYT6]: `alive` of the state is true while at least one selected camera lives. One of
    two fakes dies: the group stays alive, also after the end of its camera process. Both dead: not alive."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        ready_app_steps(app)
        living, dying = app.factory.camera_ids

        def alive():
            response = app.client.get("/skellycam/camera/group/state")
            assert response.status_code == 200, response.text
            return response.json()["camera_groups"][app.group.id]["alive"]

        assert alive()
        app.factory.sources[dying].stop_now()
        app.wait_state(dying, "dead")
        app.wait(lambda: not app.worker(dying).is_alive(), "the end of the dead camera")
        assert alive()
        app.factory.sources[living].stop_now()
        app.wait_state(living, "dead")
        assert not alive()


FLOOR_CASES = {
    "25": (FakeScript(modes=((640, 480, 30, 1, "MJPG"),)), 25.0, "refused"),
    "only 15 and 24 detected": (FakeScript(modes=((640, 480, 15, 1, "MJPG"), (640, 480, 24, 1, "MJPG"))), 30.0, "refused"),
    "30 detected, 24 at the open": (FakeScript(modes=((640, 480, 24, 1, "MJPG"),),
                                              detected_modes=((640, 480, 30, 1, "MJPG"),)), 30.0, "set mode"),
    "29.97": (FakeScript(modes=((640, 480, 30000, 1001, "MJPG"),)), 29.97, "29.97"),
    "auto with 29.97 and 60": (FakeScript(modes=((640, 480, 30000, 1001, "MJPG"), (640, 480, 60, 1, "MJPG"))), -1.0, "29.97"),
}


@pytest.mark.parametrize("case", list(FLOOR_CASES))
def test_t_cap_83_floor_of_30_fps(monkeypatch, case):
    """T-CAP-83, section 7.5 [U11, agent 55, agent 57, agent 58]: each fake camera in its own group:
    (1) a request of 25; (2) a request of 30 for a camera whose detection data has only 15 and 24 at
    the size; (3) the same, but the detection data shows 30 and the open finds only 24; (4) a request
    of 29.97 where the camera has 29.97; (5) auto for a camera with 29.97 and 60 at the size. (1) and
    (2) get 422 and change nothing; (3) fails, stage `set mode`, "no mode at 30 fps or more"; (4)
    opens at 29.97; (5) opens at 29.97."""
    script, framerate, outcome = FLOOR_CASES[case]
    with capture_app(monkeypatch, [script]) as app:
        app.detect()
        camera_id = app.factory.camera_ids[0]
        response = app.apply([app.config(camera_id, framerate=framerate)])
        if outcome == "refused":
            assert response.status_code == 422, response.text
            assert opens(app, camera_id) == 0 and not app.manager.camera_groups
            return
        assert response.status_code == 200, response.text
        app.wait_state(camera_id, "ready", "failed")
        status = app.status(camera_id)
        if outcome == "set mode":
            assert status["state"] == "failed"
            assert status["failure"] == {"camera_id": camera_id, "stage": "set mode",
                                         "reason": "no mode at 30 fps or more", "code": "below-floor"}
        else:
            assert status["state"] == "ready"
            assert (status["mode"]["fps_num"], status["mode"]["fps_den"]) == (30000, 1001)


def test_t_cap_84_whole_request_check_then_each_camera_alone(monkeypatch):
    """T-CAP-84, section 8.3 [U10]: three fakes run at 30 fps: (1) a request asks one for 60; (2) a
    request changes the size of two cameras, and the open of one fails in the fake. (1) gets 422, and
    all three keep running at 30 with unchanged rings; (2) the failing camera is `failed`, the other
    has the new size, and the third is not touched."""
    scripts = [FakeScript(modes=MODES_30_60), FakeScript(modes=MODES_30_60, fail_opens=(2,)), FakeScript(modes=MODES_30_60)]
    with capture_app(monkeypatch, scripts) as app:
        ready_app_steps(app)
        resized, failing, untouched = app.factory.camera_ids
        rings = {cid: app.ring_name(cid) for cid in app.factory.camera_ids}
        refused = app.apply([app.config(resized, framerate=60.0), app.config(failing), app.config(untouched)])
        assert refused.status_code == 422, refused.text
        for camera_id in app.factory.camera_ids:
            assert app.state(camera_id) == "ready" and app.status(camera_id)["mode"]["fps_num"] == 30
            assert app.ring_name(camera_id) == rings[camera_id] and opens(app, camera_id) == 1
        configs = [app.config(resized, width=320, height=240), app.config(failing, width=320, height=240),
                   app.config(untouched)]
        assert app.apply(configs).status_code == 200
        app.wait_state(failing, "failed")
        app.wait(lambda: app.state(resized) == "ready" and app.status(resized)["mode"]["width"] == 320, "new size")
        assert app.state(untouched) == "ready"
        assert app.ring_name(untouched) == rings[untouched] and opens(app, untouched) == 1


# ---------------------------------------------------------------------------
# T-CAP-86: the interim relay during a reopen
# ---------------------------------------------------------------------------

def test_t_cap_86_relay_sends_each_camera_on_its_own(monkeypatch):
    """T-CAP-86, section 5.8 [U13, agent 54]: three fakes with preview; reopen one camera by a change of
    its resolution. Capture relay messages during the reopen. Each message holds the newest frame of
    each camera that has one; the frames of the other two cameras keep advancing while the third is
    `starting`; the third comes back after `ready`.

    The reopened fake holds after its first frame, so the camera stays in `starting` while the test
    reads the relay. The test thread joins the virtual clock from before the reopen until the held
    camera runs again. Else the other two loops run the virtual time on alone while the test thread
    does not run, and the held camera passes its 15 s ready limit (CI runs of d8989972d, macOS, and
    6d496aa24, Linux)."""
    scripts = [FakeScript(modes=MODES_30_60), FakeScript(modes=MODES_30_60), FakeScript(modes=MODES_30_60, hold_opens=(2,))]
    with capture_app(monkeypatch, scripts) as app:
        ready_app_steps(app)
        a, b, reopened = app.factory.camera_ids
        result = []
        configs = [app.config(a), app.config(b), app.config(reopened, width=320, height=240)]
        thread = threading.Thread(target=lambda: result.append(app.apply(configs)))
        app.clock.wait_until(app.clock.now_ns())  # join the clock: the time moves only when this thread waits on it
        source = None
        try:
            thread.start()
            app.wait(lambda: reopened in app.factory.sources and app.factory.sources[reopened].holding.is_set(),
                     "the reopened camera holds in `starting`")
            source = app.factory.sources[reopened]
            assert app.state(reopened) == "starting"
            messages = []
            _collect_one_frame_apart(app, messages, 20)
            for header, frames in messages:
                assert reopened not in frames and {a, b} <= set(frames), frames
                assert header == max(frames.values())
            for camera_id in (a, b):
                assert messages[-1][1][camera_id] > messages[0][1][camera_id], f"camera {camera_id} did not advance"
        finally:
            if source is not None:
                source.release()
                app.wait(lambda: not source.holding.is_set(), "the held camera runs again")
            app.clock.leave()
            thread.join(60)
        assert result and result[0].status_code == 200
        # The virtual times of the reopen (s from the open), for the CI log if the next wait fails.
        events = [(name, t) for name, t, _ in app.factory.logs[reopened].events]
        open_ns = [t for name, t in events if name == "open"][-1]
        print("T-CAP-86 reopen:", [(name, round((t - open_ns) / 1e9, 3)) for name, t in events if t >= open_ns])
        app.wait_state(reopened, "ready")
        after = []
        app.wait(lambda: _collect(app, after) and reopened in after[-1][1], "the reopened camera in the relay")


def _collect_one_frame_apart(app, messages, count):
    """Collect relay messages one frame of virtual time apart. The caller has joined the clock, so the
    virtual time does not run on while a poll builds a payload."""
    for _ in range(50 * count):
        if _collect(app, messages) >= count:
            return
        app.clock.wait_until(app.clock.now_ns() + FRAME_NS)
    raise AssertionError(f"{len(messages)} relay messages, not {count}")


def _collect(app, messages):
    payload = app.group.get_latest_ring_payload()
    if payload is not None:
        message = parse_relay(payload[2])
        if not messages or message != messages[-1]:
            messages.append(message)
    return len(messages)


# ---------------------------------------------------------------------------
# T-CAP-90, T-CAP-91: failed live change; rate class 30
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fault", ["error", "readback:-6"], ids=["set error", "wrong read-back"])
def test_t_cap_90_failed_live_change_keeps_the_camera_running(monkeypatch, fault):
    """T-CAP-90, sections 8.2, 8.3 and 11.2 [U14, agent 64]: a camera is `ready` with `MANUAL -7`. (1) A
    live exposure change to -5: the fake set call returns an error. (2) The same change: the set
    returns success, but the read-back is -6. In both cases: the camera stays `ready` with exposure -7
    and the same ring name; the apply response has a `control_change_failed` item for that camera; no
    other camera changes.

    "Exposure -7" is the exposure of the camera config."""
    with capture_app(monkeypatch, [FakeScript(live_set_faults=(fault,)), FakeScript()], track=True) as app:
        ready_app_steps(app)
        changed, other = app.factory.camera_ids
        rings = {cid: app.ring_name(cid) for cid in app.factory.camera_ids}
        other_config = app.group.configs[other]
        t_change = app.clock.now_ns()
        response = app.apply([app.config(changed, exposure=-5), app.config(other)])
        assert response.status_code == 200, response.text
        items = [w for w in response.json()["warnings"] if w["kind"] == "control_change_failed"]
        assert len(items) == 1 and items[0]["camera_ids"] == [changed] and items[0]["text"]
        assert response.json()["camera_configs"][changed]["exposure"] == -7
        assert app.group.configs[changed].exposure == -7
        app.wait_clock(3.0)
        assert app.state(changed) == "ready"
        assert not [s for t, s in app.tracker.states(changed) if t > t_change and s != "ready"]
        assert {cid: app.ring_name(cid) for cid in app.factory.camera_ids} == rings
        assert app.group.configs[other] == other_config and opens(app, other) == opens(app, changed) == 1


def test_t_cap_91_rate_class_30(monkeypatch):
    """T-CAP-91, section 7.5 [U15, agent 63]: one group: a fake at 30000/1001 and a fake at 30/1; run for a
    simulated 100 s. Then a request that adds a camera at 60. The apply response has one `mixed_rate`
    item with the camera IDs, "29.97 fps", "30 fps" and "about every 33 s"; the log has the text; the
    group rate is 29.97; the `replaced_count` of the 30 fps camera is 3 (+/-1); the request with 60
    gets 422.

    The 100 s start at the first frame that the 30 fps camera takes in the gate (5.2). A probe reads
    `replaced_count` of that fake at each of its reads. The group rate is the rate of the gate frames
    of each camera in the same 100 s."""
    scripts = [FakeScript(modes=((640, 480, 30000, 1001, "MJPG"),)), FakeScript(modes=((640, 480, 30, 1, "MJPG"),)),
               FakeScript(modes=((640, 480, 60, 1, "MJPG"),))]
    samples = []

    def probe(source, now_ns):
        if source.camera_id == fast:
            samples.append((now_ns, source.replaced_count))

    with capture_logs() as logs, capture_app(monkeypatch, scripts, on_read=probe) as app:
        spies = Spies(monkeypatch, app)
        app.detect()
        slow, fast, sixty = app.factory.camera_ids
        response = app.apply([app.config(slow), app.config(fast)])
        assert response.status_code == 200, response.text
        items = [w for w in response.json()["warnings"] if w["kind"] == "mixed_rate"]
        assert len(items) == 1
        assert set(items[0]["camera_ids"]) == {slow, fast}
        for part in (slow, fast, "29.97 fps", "30 fps", "about every 33 s"):
            assert part in items[0]["text"], part
        assert any(items[0]["text"] in message for message in logs.messages(logging.WARNING))
        refused = app.apply([app.config(slow), app.config(fast), app.config(sixty)])
        assert refused.status_code == 422, refused.text
        app.wait(lambda: spies.of("jpeg", fast), "the first gate frame")
        t0 = spies.of("jpeg", fast)[0]["arrival_ns"]
        t1 = t0 + 100 * 10**9
        app.wait(lambda: samples and samples[-1][0] > t1, "100 simulated seconds")
        replaced = next(r for t, r in samples if t > t1) - next(r for t, r in samples if t > t0)
        assert 2 <= replaced <= 4, f"{replaced} frames replaced in 100 s"
        for camera_id in (slow, fast):
            arrivals = [e["arrival_ns"] for e in spies.of("jpeg", camera_id) if t0 <= e["arrival_ns"] <= t1]
            rate = (len(arrivals) - 1) / ((arrivals[-1] - arrivals[0]) / 1e9)
            assert abs(rate - 30000 / 1001) < 0.01, f"camera {camera_id}: gate rate {rate:.4f}"


# ---------------------------------------------------------------------------
# T-CAP-105, T-CAP-107, T-CAP-108, T-CAP-112, T-CAP-113: the corrections of the 3a review (ADR-PDD3, ADR-6EKB)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("detected", [True, False], ids=["detection result", "no detection result"])
def test_t_cap_105_a_virtual_camera_is_refused(monkeypatch, detected):
    """T-CAP-105, sections 7.1 and 8.3 [ADR-PDD3 W5]: detection shows a virtual camera with
    `virtual: true`; a request that names it gets 422, and no camera opens. With no detection result,
    the apply request detects first, so the refusal holds."""
    scripts = [FakeScript(name="Fake Virtual Camera"), FakeScript()]
    with capture_app(monkeypatch, scripts) as app:
        virtual, real = app.factory.camera_ids
        if detected:
            shown = {camera["camera_id"]: camera for camera in app.detect()["cameras"]}
            assert shown[virtual]["virtual"] is True and shown[real]["virtual"] is False
        response = app.apply([app.config(virtual), app.config(real)])
        assert response.status_code == 422, response.text
        assert virtual in detail(response) and "virtual" in detail(response)
        assert (opens(app, virtual), opens(app, real)) == (0, 0) and not app.manager.camera_groups
        assert app.detections == (0 if detected else 1)


def test_t_cap_107_replaced_count_in_the_status(monkeypatch):
    """T-CAP-107, sections 5.2 and 8.4 [ADR-PDD3 W4]: two fakes on one 100 ms grid; one delivers 60 fps
    from 8 s to 12 s of the clock. While it runs, the status of that camera shows a `replaced_count`
    above 0; at the end, the status shows the count of its stop line, which equals the sum of the gaps
    of `source_frame_number` from its first frame in the gate."""
    grid = dict(align_ms=100.0, stop_at_s=16.005)
    scripts = [FakeScript(**grid), FakeScript(rate_windows=((8.0, 11.995, 60.0),), drop_at_window_end=True, **grid)]
    with capture_logs() as logs, capture_app(monkeypatch, scripts) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        assert app.clock.now_ns() < app.clock.START_NS + 75 * 10**8, "the start-up took past 7.5 s of the clock"
        fast = app.factory.camera_ids[1]
        app.wait(lambda: app.status(fast)["replaced_count"] > 0, "a replaced frame in the status")
        app.wait(lambda: stop_line_count(logs.messages(), fast) >= 0, "the stop line")
        count = stop_line_count(logs.messages(), fast)
        assert app.status(fast)["replaced_count"] == count == sfn_gaps([e["sfn"] for e in spies.of("jpeg", fast)])
        assert count >= 100, count


def test_t_cap_108_a_dying_camera_does_not_hold_the_others(monkeypatch, tmp_path):
    """T-CAP-108, sections 6.7 and 8.2 [D38, ADR-PDD3]: three fakes record; one gives device removed,
    and its close takes 2 s. That camera is `dead` before its close ends; the two live cameras record
    on with no gap above 100 ms between their recorded frames (the limit of T-CAP-82).

    Changed by step 5a [M1, recorder.md 10 item 7]: the process of the dead camera writes placeholders
    to the end of the take and closes its source after it, so the test sees the close after the stop. The
    stop response returns before the close ends (review item 12): the close of the dying fake also waits
    until the stop response returned, at most 10 s, so a stop that waits for the close returns after it."""
    from skellycam.tests.capture.fake_source import FakeSource

    scripts = [FakeScript(), FakeScript(), FakeScript(close_delay_s=2.0)]
    stopped, close_ended = threading.Event(), threading.Event()
    close = FakeSource.close

    def slow_close(source, restore=True):
        if source.script.close_delay_s:
            with source.clock.blocked():
                stopped.wait(10)
            close(source, restore)
            close_ended.set()
        else:
            close(source, restore)

    monkeypatch.setattr(FakeSource, "close", slow_close)
    with capture_app(monkeypatch, scripts, track=True) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        live, dying = app.factory.camera_ids[:2], app.factory.camera_ids[2]
        assert app.record_start(tmp_path).status_code == 200
        app.wait(lambda: len(spies.of("record", dying)) >= 60, "60 recorded frames")
        app.factory.sources[dying].remove_now()
        app.wait(lambda: app.tracker.first(dying, "dead") is not None, "the camera is dead")
        t_dead = app.tracker.first(dying, "dead")
        for camera_id in live:
            app.wait(lambda: any(e["arrival_ns"] > t_dead + 3 * 10**9 for e in spies.of("record", camera_id)),
                     f"camera {camera_id} records 3 s after the dead camera")
        assert app.record_stop().status_code == 200
        assert not close_ended.is_set(), "the stop response came after the slow close"
        stopped.set()
        events = app.factory.logs[dying].events
        app.wait(lambda: any(name == "close" for name, _, _ in events), "the close of the dead camera")
        close_ns = next(t for name, t, _ in events if name == "close")
        assert t_dead <= close_ns, "the camera became dead only after its close"
        for camera_id in live:
            times = [e["arrival_ns"] for e in spies.of("record", camera_id)]
            gap = max(b - a for a, b in zip(times, times[1:])) / 1e9
            assert gap <= 0.1, f"camera {camera_id} had a gap of {gap * 1000:.0f} ms"


def test_t_cap_112_first_frame_seen_after_warm_up_frame_90(monkeypatch):
    """T-CAP-112, section 10.1 [D22, agent 26]: frames 2 to 95 arrive together, 94 ms after frame 1, so the
    first warm-up frame that the loop sees in the window is frame 95. The window waits for one more
    frame: the camera is `ready` with a measured rate within 3 % of 30, not a failure of an empty
    window."""
    intervals = (100 / 3,) + (1.0,) * 94 + (100 / 3,) * 3000
    with one_camera(monkeypatch, FakeScript(intervals_ms=intervals, burst=(2, 95))) as (app, camera_id, _):
        status = app.status(camera_id)
        assert status["state"] == "ready" and status["failure"] is None, status
        assert abs(status["measured_fps"] - 30.0) <= 0.9, status


def test_t_cap_113_a_frame_that_waits_at_the_gate_is_not_too_slow(monkeypatch):
    """T-CAP-113, sections 5.2 and 10.2 [D32, ADR-PDD3]: two fakes are `ready`; the second delivers 1.6 fps
    for 12 s, so the first waits at the gate and takes one frame each 0.625 s. No gate round falls
    between the arrival of frame s_a + 59 and the early deadline, so a decision at the deadline would
    be false. A live exposure change of
    the first: its frames arrive at 30 fps, so frame s_a + 59 arrives in time, also when the loop
    takes it after the early deadline. The check ends `ready`, not `too_slow`."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()], track=True) as app:
        ready_app_steps(app)
        changed, slow = app.factory.camera_ids
        app.factory.sources[slow].slow_period(rate=1.6, seconds=12.0)
        app.wait_clock(1.0, "the slow period starts")
        response = app.apply([app.config(changed, exposure=-6), app.config(slow)])
        assert response.status_code == 200, response.text
        app.wait(lambda: app.state(changed) in ("ready", "too_slow")
                 and app.tracker.first(changed, "checking") is not None, "the end of the check")
        assert app.state(changed) == "ready", app.status(changed)
        assert abs(app.status(changed)["measured_fps"] - 30.0) <= 0.9


@pytest.mark.capture_timing  # real time, process workers: rows 100 ms apart at most; load moves them (review item 8)
def test_a_camera_selected_again_shares_the_gate_with_a_restarted_camera(monkeypatch, tmp_path):
    """Suspected fault NEW-B (coordinator, 2026-11-20), sections 5.2 and 8.3: each camera process gets the
    status table of the group as it was at its own start. Camera A is unselected; camera B is killed and
    started again ("apply again"), so the table of B has no A; then A is selected again. In a take, A has
    a gap of 500 ms (its source); B must wait for A at the gate, so that row k of both cameras is one
    moment: the arrivals of a row differ by at most 100 ms, except at the gap, where the gate lets B take
    one frame before A (5.2). PROCESS workers: THREAD workers share one table."""
    from skellycam.core.take_recorder.sidecar import MISSING

    gap_after_frame_299 = FakeScript(intervals_ms=(1000 / 30,) * 299 + (500.0,))  # 10 s after each open
    with capture_app(monkeypatch, [gap_after_frame_299, FakeScript()], workers="process") as app:
        ready_app_steps(app)
        a, b = app.factory.camera_ids
        response = app.apply([app.config(a, use_this_camera=False), app.config(b)])
        assert response.status_code == 200, response.text
        app.worker(b).worker.kill()
        app.wait_state(b, "dead")
        response = app.apply([app.config(b)], retry=[b])
        assert response.status_code == 200, response.text
        app.wait_state(b, "ready")
        response = app.apply([app.config(a), app.config(b)])
        assert response.status_code == 200, response.text
        reopened = time.monotonic()
        app.wait_state(a, "ready")
        app.wait_state(b, "ready")
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(max(0.0, reopened + 12.0 - time.monotonic()))  # past the gap of A at 10 s
        stopped = app.record_stop()
        assert stopped.status_code == 200, stopped.text
    rows = {cid: take_rows(tmp_path, cid) for cid in (a, b)}
    assert len(rows[a]) == len(rows[b]) == stopped.json()[0]["number_of_frames"] > 200
    apart = [(ra.frame, round((rb.arrival_ns - ra.arrival_ns) / 1e6)) for ra, rb in zip(rows[a], rows[b])
             if not (ra.flags | rb.flags) & MISSING and abs(ra.arrival_ns - rb.arrival_ns) > 100_000_000]
    assert len(apart) <= 1, f"{len(apart)} rows of the two cameras differ by more than 100 ms: {apart[:5]}"
