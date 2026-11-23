"""T-UNX-27 and T-UNX-78, the shared part, and T-REQ-15 as far as it concerns the restore: the restore of the
controls at the close of a camera (specs/unix-capture.md 4.7; specs/camera-requests.md T-REQ-15).

`ControlRestore` of `capture/source.py` is the shared part: the "before" value and auto flag of each control
at the first read of an open, the controls that a set changed, the restore at the close, and the keys
`restore_ok` and `restore_failed`. The fake source uses it as each source does. The close orders of the
V4L2 source (T-UNX-27) and of the AVFoundation source (T-UNX-51) wait for steps 7a and 7b; the Media
Foundation source is in `test_media_foundation_source.py` (T-UNX-78).

Each test runs one fake camera through the HTTP endpoints with THREAD workers and the virtual clock.
"""

import logging

import pytest

from skellycam.tests.capture.capture_session import capture_logs, one_camera
from skellycam.tests.capture.fake_source import FakeScript

AUTO_BEFORE = (("exposure", True, True, -6), ("gain", True, False, 0), ("focus", True, True, 30))


def exposure_sets(log):
    """(clock ns, ControlSetting) of each exposure set of the fake, in order."""
    return [(t, detail["exposure"]) for name, t, detail in log.events if name == "set_controls" and "exposure" in detail]


def close_time(log):
    return [t for name, t, _ in log.events if name == "close"][-1]


def test_t_unx_78_fake_restore_at_the_close_is_on_by_default(monkeypatch):
    """T-UNX-78 and T-UNX-27 (shared part), T-REQ-15: a camera whose exposure was in auto before the open runs
    in MANUAL -7. At the close, the restore sets exposure back to auto with its value of before, after the
    last frame was taken, and reads it back; `restore_ok` true, `restore_failed` 0. No other set has
    `auto=True` for exposure. Gain was not changed: no restore set for it."""
    monkeypatch.delenv("SKELLYCAM_RESTORE_CONTROLS", raising=False)
    with one_camera(monkeypatch, FakeScript(controls=AUTO_BEFORE)) as (app, camera_id, _):
        assert app.state(camera_id) == "ready"
        source, log = app.factory.sources[camera_id], app.factory.logs[camera_id]
        app.wait_clock(1.0)
        app.client.delete("/skellycam/camera/group/close/all")
        app.wait(lambda: log.closes.value == 1, "the close")
    sets = exposure_sets(log)
    auto = [(t, s) for t, s in sets if s.auto]
    assert [(s.auto, s.value) for _, s in auto] == [(True, -6)], sets
    assert auto[0] == sets[-1] and auto[0][0] >= close_time(log)
    last_frame_ns = max(arrival for arrival, _ in log.frames.values())
    assert auto[0][0] >= last_frame_ns
    assert not [s for s in log.settings if "gain" in s]
    data = source.diagnostics()
    assert (data["restore_ok"], data["restore_failed"]) == (True, 0)
    assert (data["exposure_before"], data["exposure_before_auto"]) == (-6, True)
    assert source._controls["exposure"][1:] == [True, -6]  # read back: auto, value of before


def test_t_req_15_a_manual_camera_gets_no_auto_set_at_the_close(monkeypatch):
    """T-REQ-15: a camera whose exposure was manual (-6) before the open: the restore sets -6 with
    `auto=False`; no set with `auto=True` for exposure, also not at the close."""
    with one_camera(monkeypatch, FakeScript()) as (app, camera_id, _):
        log = app.factory.logs[camera_id]
        app.client.delete("/skellycam/camera/group/close/all")
        app.wait(lambda: log.closes.value == 1, "the close")
    sets = exposure_sets(log)
    assert not [s for _, s in sets if s.auto], sets
    assert (sets[-1][1].auto, sets[-1][1].value) == (False, -6) and sets[-1][0] >= close_time(log)


def test_t_unx_27_no_restore_with_the_setting_0(monkeypatch):
    """T-UNX-27 (shared part): with `SKELLYCAM_RESTORE_CONTROLS=0` the close sets no control."""
    monkeypatch.setenv("SKELLYCAM_RESTORE_CONTROLS", "0")
    with one_camera(monkeypatch, FakeScript(controls=AUTO_BEFORE)) as (app, camera_id, _):
        source, log = app.factory.sources[camera_id], app.factory.logs[camera_id]
        app.client.delete("/skellycam/camera/group/close/all")
        app.wait(lambda: log.closes.value == 1, "the close")
    assert not [t for t, _ in exposure_sets(log) if t >= close_time(log)]
    data = source.diagnostics()
    assert (data["restore_ok"], data["restore_failed"]) == (None, None)


def test_t_unx_27_a_failed_restore_is_logged_and_the_close_goes_on(monkeypatch):
    """T-UNX-27 (shared part): the restore set fails: `restore_ok` false, `restore_failed` 1, one log line;
    the close goes on (the stream stops, and the camera process ends normally)."""
    script = FakeScript(controls=AUTO_BEFORE, live_set_faults=("error",))  # the first set after the start: the restore
    with capture_logs() as logs, one_camera(monkeypatch, script) as (app, camera_id, _):
        source, log = app.factory.sources[camera_id], app.factory.logs[camera_id]
        worker = app.worker(camera_id)
        app.client.delete("/skellycam/camera/group/close/all")
        app.wait(lambda: not worker.is_alive(), "the camera ends")
    data = source.diagnostics()
    assert (data["restore_ok"], data["restore_failed"]) == (False, 1)
    assert source._stop.is_set() and log.closes.value == 1
    lines = [m for m in logs.messages(logging.WARNING) if "restore" in m and camera_id in m]
    assert len(lines) == 1 and "exposure" in lines[0], lines


def test_f7_no_restore_when_the_loop_failed(monkeypatch):
    """F7: the in-process stall rule (W 9.5) ends a camera whose exposure the open changed; it sets no error of
    the source. The close of that camera sets no control: a possibly wedged camera gets no set and no
    read-back."""
    with one_camera(monkeypatch, FakeScript(controls=AUTO_BEFORE)) as (app, camera_id, _):
        source, log = app.factory.sources[camera_id], app.factory.logs[camera_id]
        source.stop_now()
        app.wait_state(camera_id, "dead")
        app.wait(lambda: log.closes.value == 1, "the close of the dead camera")
    assert not [t for t, _ in exposure_sets(log) if t >= close_time(log)]
    assert source.diagnostics()["restore_ok"] is None


@pytest.mark.parametrize("failure, script, restored", [
    ("rate-low", dict(rate=25.0), True),  # the start-up rate check of a camera in MANUAL
    ("not-ready", dict(), True),  # the ready limit of W 9.3 (2 s here) ends the warm-up
    ("stalled", dict(), False),  # the stall rule of W 9.5: a wedge
    ("stream-error", dict(removed_after_frame=150, removed_code="stream-error"), True),  # a source error, no wedge
    ("device-removed", dict(removed_after_frame=150), False),  # a wedge
])
def test_t_unx_95_a_camera_whose_loop_failed_is_restored_unless_it_is_wedged(monkeypatch, failure, script, restored):
    """T-UNX-95, unix-capture.md 4.7 [Z7F3] (a decision of the user of 2026-11-21): the open set the exposure (auto -6
    before it, MANUAL -7 after it); then the loop fails. A failure that is not a wedge (`rate-low`, `not-ready`) gets
    the restore at the close: auto -6 again, `restore_ok` true. A wedge (`stalled`) gets no set at the close."""
    if failure == "not-ready":
        from skellycam.core.camera.capture import camera_loop
        monkeypatch.setattr(camera_loop, "READY_LIMIT_NS", 2_000_000_000)  # 2 s: the warm-up of 90 frames needs 3 s
    with one_camera(monkeypatch, FakeScript(controls=AUTO_BEFORE, **script)) as (app, camera_id, _):
        source, log = app.factory.sources[camera_id], app.factory.logs[camera_id]
        if failure == "stalled":
            source.stop_now()
        if failure in ("stalled", "stream-error", "device-removed"):
            app.wait_state(camera_id, "dead")
        app.wait(lambda: log.closes.value == 1, "the close")
        assert app.status(camera_id)["failure"]["code"] == failure
    after_close = [s for t, s in exposure_sets(log) if t >= close_time(log)]
    if restored:
        assert [(s.auto, s.value) for s in after_close] == [(True, -6)]
        assert source.diagnostics()["restore_ok"] is True
    else:
        assert after_close == [] and source.diagnostics()["restore_ok"] is None


@pytest.mark.parametrize("next_open", ["apply again", "a new group", "a camera that rounds"])
def test_t_unx_91_the_values_of_before_survive_a_camera_with_no_restore(monkeypatch, next_open):
    """T-UNX-91, unix-capture.md 4.7 [NYT6]: a camera that keeps its controls between opens (a real camera) was in auto -6. Its
    first open sets MANUAL -7; its loop fails, so it gets no restore and stays at manual -7. The next open ("apply
    again", or a new group after a group close) reads manual -7, but its "before" values stay auto -6, and its
    close restores auto -6. [Z7F3]: a camera that rounds (the C930e) reads manual -6 at the next open, one step from
    -7; its close also restores auto -6."""
    rounds = next_open == "a camera that rounds"
    script = FakeScript(controls=AUTO_BEFORE, keeps_controls=True, reopen_shift=(("exposure", 1),) if rounds else ())
    with one_camera(monkeypatch, script) as (app, camera_id, _):
        log = app.factory.logs[camera_id]
        app.factory.sources[camera_id].stop_now()
        app.wait_state(camera_id, "dead")
        app.wait(lambda: log.closes.value == 1, "the close of the dead camera")
        assert log.device_controls["exposure"][1:] == [False, -7]  # no restore: the value of this app stays
        if next_open == "a new group":
            app.client.delete("/skellycam/camera/group/close/all")
            assert log.device_controls["exposure"][1:] == [False, -7]  # a group close opens no camera
        assert app.apply([app.config(camera_id)], retry=[camera_id]).status_code == 200
        app.wait_state(camera_id, "ready")
        source = app.factory.sources[camera_id]
        app.client.delete("/skellycam/camera/group/close/all")
        app.wait(lambda: log.closes.value == 2, "the close")
    assert log.device_controls["exposure"][1:] == [True, -6]
    data = source.diagnostics()
    assert (data["exposure_before"], data["exposure_before_auto"], data["restore_ok"]) == (-6, True, True)


def test_t_unx_91_an_open_that_takes_the_record_one_step_away_still_runs_the_rate_check(monkeypatch):
    """T-UNX-91, unix-capture.md 4.7 [Z7F3]: an open that used the record one step away still runs the normal rate
    check. The first open sets MANUAL -7 and stalls (no restore); the camera rounds and reads manual -6 at the next
    open, so that open takes the record (auto -6 before). The camera is now slow (25 fps): the start-up rate check
    of that open fails it with `rate-low`, and its close restores auto -6."""
    script = FakeScript(controls=AUTO_BEFORE, keeps_controls=True, reopen_shift=(("exposure", 1),))
    with one_camera(monkeypatch, script) as (app, camera_id, _):
        log = app.factory.logs[camera_id]
        app.factory.sources[camera_id].stop_now()
        app.wait_state(camera_id, "dead")
        app.wait(lambda: log.closes.value == 1, "the close of the dead camera")
        script.rate = 25.0  # the next open delivers 25 fps in its 30 fps mode
        assert app.apply([app.config(camera_id)], retry=[camera_id]).status_code == 200
        app.wait_state(camera_id, "failed")
        app.wait(lambda: log.closes.value == 2, "the close")
        source = app.factory.sources[camera_id]
        assert app.status(camera_id)["failure"]["code"] == "rate-low"
    assert log.device_controls["exposure"][1:] == [True, -6]
    data = source.diagnostics()
    assert (data["exposure_before"], data["exposure_before_auto"], data["restore_ok"]) == (-6, True, True)


def test_a_lost_heartbeat_still_restores_the_controls_at_the_close(monkeypatch):
    """unix-capture.md 4.7 (fix lane C): a lost heartbeat of the server is no camera fault. The camera is `dead`
    with its reason, and its close restores the exposure of before (auto, -6)."""
    import threading

    from skellycam.core.camera_group import camera_group_ipc

    stale = {"on": False}
    check = camera_group_ipc.check_main_process_heartbeat

    def stale_in_the_camera(**kwargs):
        if stale["on"] and threading.current_thread().name.startswith("Camera"):
            return False
        return check(**kwargs)

    monkeypatch.setattr(camera_group_ipc, "check_main_process_heartbeat", stale_in_the_camera)
    with one_camera(monkeypatch, FakeScript(controls=AUTO_BEFORE)) as (app, camera_id, _):
        source, log = app.factory.sources[camera_id], app.factory.logs[camera_id]
        stale["on"] = True
        app.wait_state(camera_id, "dead", timeout=30)
        app.wait(lambda: log.closes.value == 1, "the close")
        stale["on"] = False
        assert app.status(camera_id)["failure"]["reason"] == "lost the server's heartbeat"
    auto = [s for t, s in exposure_sets(log) if t >= close_time(log) and s.auto]
    assert [(s.auto, s.value) for s in auto] == [(True, -6)]
    assert source.diagnostics()["restore_ok"] is True


def test_an_end_by_another_base_exception_is_not_a_lost_heartbeat(monkeypatch):
    """Fix lane I: a loop that a BaseException other than an `Exception` ends (here `KeyboardInterrupt` in a pass) is
    not labelled "lost the server's heartbeat"."""
    import importlib

    loop_module = importlib.import_module("skellycam.core.camera.capture.camera_loop")
    with one_camera(monkeypatch, FakeScript()) as (app, camera_id, _):
        def interrupted(loop):
            raise KeyboardInterrupt("test")

        monkeypatch.setattr(loop_module.CameraLoop, "_pass", interrupted)
        app.wait(lambda: app.status(camera_id)["closed"], "the loop ends")
        assert (app.status(camera_id)["failure"] or {}).get("reason") != "lost the server's heartbeat"


def test_t_unx_92_a_record_applies_only_to_controls_that_still_hold_the_value_of_this_app(monkeypatch):
    """T-UNX-92, unix-capture.md 4.7 [NYT6] (the experiment `stale.py` of the review): the camera starts in auto -6;
    open 1 sets manual -7 and is killed. (a) The camera still holds -7: open 2 takes auto -6 of the record as its
    "before" value. (b) Another program set manual -3 meanwhile: open 2 drops the record and restores -3. (c) A record
    replaces "before" only for its names: a gain in its `before` that is not in `names` stays as read."""
    from types import SimpleNamespace

    from skellycam.core.camera.capture import source
    from skellycam.core.camera.capture.source import ControlRestore, ControlSetting, ControlValue

    store = {}
    monkeypatch.setitem(source.RESTORE_RECORDS, "cam", SimpleNamespace(
        restore_record=lambda: store.get("r", {}), set_restore_record=lambda r: store.__setitem__("r", r)))
    device = {}

    def set_controls(changes):
        for name, setting in changes.items():
            device[name] = ControlValue(True, setting.auto, setting.value)
        return dict(device)

    def open_and_set(value):
        restore = ControlRestore("cam")
        restore.read(dict(device))
        restore.changed({"exposure": ControlSetting(False, value)})
        set_controls({"exposure": ControlSetting(False, value)})
        return restore

    for other_program, expected in ((None, ControlValue(True, True, -6)), (-3, ControlValue(True, False, -3))):
        store.clear()
        device.update(exposure=ControlValue(True, True, -6), gain=ControlValue(True, False, 0))
        open_and_set(-7)  # killed: no restore
        if other_program is not None:
            device["exposure"] = ControlValue(True, False, other_program)
        open_and_set(-8).restore(set_controls)
        assert device["exposure"] == expected, other_program
        assert store["r"] == {}

    store["r"] = dict(before={"exposure": [True, True, -6], "gain": [True, False, 99]}, names=["exposure"],
                      set={"exposure": [False, -7]})
    device.update(exposure=ControlValue(True, False, -7), gain=ControlValue(True, False, 0))
    restore = ControlRestore("cam")
    restore.read(dict(device))
    assert restore.before["exposure"] == ControlValue(True, True, -6) and restore.before["gain"] == ControlValue(True, False, 0)


@pytest.mark.parametrize("read, steps, takes_record", [
    (-6, {"exposure": 1}, True), (-8, {"exposure": 1}, True),  # (d) one step: a camera that rounds at a new open (C930e)
    (-6, None, False), (-6, {"exposure": 0}, False),  # (d) no step known: the same value is needed
    (-5, {"exposure": 1}, False), (-9, {"exposure": 1}, False),  # (e) two steps: another program set it
])
def test_t_unx_92_a_camera_that_rounds_at_a_new_open_keeps_the_record(monkeypatch, read, steps, takes_record):
    """T-UNX-92 (d), (e), unix-capture.md 4.7 [Z7F3]: open 1 set manual -7 and got no restore. At open 2 the camera
    reads manual `read`. Within one step of the control's own step the record still applies (the "before" value is
    auto -6 of the record); else the record drops the control, and the "before" value is the value that the camera
    reads. The auto flag must always be the same."""
    from types import SimpleNamespace

    from skellycam.core.camera.capture import source
    from skellycam.core.camera.capture.source import ControlRestore, ControlValue

    store = {"r": dict(before={"exposure": [True, True, -6]}, names=["exposure"], set={"exposure": [False, -7]})}
    monkeypatch.setitem(source.RESTORE_RECORDS, "cam", SimpleNamespace(
        restore_record=lambda: store.get("r", {}), set_restore_record=lambda r: store.__setitem__("r", r)))
    restore = ControlRestore("cam")
    restore.read({"exposure": ControlValue(True, False, read)}, steps)
    expected = ControlValue(True, True, -6) if takes_record else ControlValue(True, False, read)
    assert restore.before["exposure"] == expected
    assert bool(store["r"]) == takes_record
    store["r"] = dict(before={"exposure": [True, True, -6]}, names=["exposure"], set={"exposure": [False, -7]})
    auto = ControlRestore("cam")
    auto.read({"exposure": ControlValue(True, True, -7)}, steps)  # the same value, but the camera is in auto again
    assert auto.before["exposure"] == ControlValue(True, True, -7)
