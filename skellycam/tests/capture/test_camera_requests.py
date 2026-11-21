"""Part 1 of specs/camera-requests.md (exposure): the tests T-REQ of code step 3 with the fake sources.

Each test runs THREAD workers with the virtual clock of `capture_session`, unless it says else. The fixture
`no_camera_auto_exposure` is the spy of T-REQ-15: no exposure set of a test in this file has `auto=True`,
except the restore at the close.
"""

import cv2
import pytest

from skellycam.tests.capture.capture_session import capture_app, ready_app_steps
from skellycam.tests.capture.fake_source import FakeScript

pytestmark = pytest.mark.usefixtures("no_camera_auto_exposure")


def exposure_sets(app, camera_id):
    """(auto, value) of each exposure set of the fake, in order."""
    return [(s["exposure"].auto, s["exposure"].value) for s in app.factory.logs[camera_id].settings if "exposure" in s]


# ---------------------------------------------------------------------------
# 1.1, 1.5: the config and the modes (T-REQ-14, T-REQ-15)
# ---------------------------------------------------------------------------

def test_t_req_14_default_config_and_the_mode_values():
    """T-REQ-14, 1.5 [G1, G6, H7]: the default of `CameraConfig()` is `AUTO`, -7, `exposure_found_at_fps` None;
    `RECOMMEND` is read as `AUTO`; each other mode value is refused."""
    from pydantic import ValidationError

    from skellycam.core.camera.config.camera_config import CameraConfig

    config = CameraConfig()
    assert (config.exposure_mode, config.exposure, config.exposure_found_at_fps) == ("AUTO", -7, None)
    assert CameraConfig(exposure_mode="RECOMMEND").exposure_mode == "AUTO"
    assert CameraConfig(exposure_mode="MANUAL").exposure_mode == "MANUAL"
    with pytest.raises(ValidationError):
        CameraConfig(exposure_mode="CAMERA")


def test_t_req_14_same_config_ignores_the_found_rate_number_and_name():
    """T-REQ-14, 1.5 [H6, AC5B]: `same_config` ignores `exposure_found_at_fps`, `camera_index` and
    `camera_name`; for `AUTO` it ignores `exposure` (the held value of the server)."""
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera_group.camera_group import same_config

    current = CameraConfig(camera_id="a1", camera_index=0, camera_name="one", exposure_mode="AUTO", exposure=-9,
                           exposure_found_at_fps=30.0, framerate=30.0)
    request = current.model_copy(update=dict(camera_index=3, camera_name="three", exposure_found_at_fps=None,
                                             exposure=-7))
    assert same_config(request, current)
    assert not same_config(request.model_copy(update=dict(exposure_mode="MANUAL")), current)
    assert not same_config(request.model_copy(update=dict(framerate=60.0)), current)


def test_t_req_14_the_apply_request_reads_recommend_as_auto_and_refuses_other_modes(monkeypatch):
    """T-REQ-14 [G6]: an apply request with `RECOMMEND` stores `AUTO`; `CAMERA` gets 422. A same config with
    another `camera_index` and `camera_name` makes no set call, and the new number and name are stored."""
    with capture_app(monkeypatch, [FakeScript()]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        bad = app.config(camera_id).model_dump(mode="json")
        bad["exposure_mode"] = "CAMERA"
        refused = app.client.post("/skellycam/camera/group/apply", json={"camera_configs": {camera_id: bad}})
        assert refused.status_code == 422, refused.text
        ready_app_steps(app)
        settings = len(app.factory.logs[camera_id].settings)
        same = app.apply([app.config(camera_id, camera_index=4, camera_name="renamed", exposure_found_at_fps=30.0)])
        assert same.status_code == 200, same.text
        stored = app.group.configs[camera_id]
        assert (stored.camera_index, stored.camera_name) == (4, "renamed")
        assert not [s for s in app.factory.logs[camera_id].settings[settings:] if s]
        body = app.config(camera_id).model_dump(mode="json")
        body["exposure_mode"] = "RECOMMEND"
        response = app.client.post("/skellycam/camera/group/apply", json={"camera_configs": {camera_id: body}})
        assert response.status_code == 200, response.text
        assert response.json()["camera_configs"][camera_id]["exposure_mode"] == "AUTO"


def test_t_req_15_an_auto_open_sets_its_held_value_as_a_manual_value(monkeypatch):
    """T-REQ-15, 1.3a [A7, G1]: a camera in `AUTO` held at -9 sets -9 with `auto=False` at the open (9.1 step 5).
    The camera's own auto exposure is never requested (the spy of this file)."""
    with capture_app(monkeypatch, [FakeScript()]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        response = app.apply([app.config(camera_id, exposure_mode="AUTO", exposure=-9, exposure_found_at_fps=30.0)])
        assert response.status_code == 200, response.text
        assert exposure_sets(app, camera_id)[0] == (False, -9)
        assert response.json()["camera_configs"][camera_id]["exposure_mode"] == "AUTO"


# ---------------------------------------------------------------------------
# 1.7: the OpenCV exposure on each system
# ---------------------------------------------------------------------------

def _capture():
    """A stand-in `cv2.VideoCapture` (the beartype check of the product wants the type) that keeps each call."""
    from unittest.mock import Mock

    capture = Mock(spec=cv2.VideoCapture)
    capture.get.side_effect = lambda prop: -8.0 if prop == cv2.CAP_PROP_EXPOSURE else -1
    return capture


@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
@pytest.mark.parametrize("mode", ["MANUAL", "AUTO"])
def test_t_req_21_opencv_apply_exposure_on_each_system(monkeypatch, platform, mode):
    """T-REQ-21 (1), 1.7 [Q11, K2, AC5B]: on Linux and macOS `_apply_exposure` sets the camera's auto exposure for
    `MANUAL` and `AUTO`. On Windows `AUTO` makes no exposure call (the loop sets the held value, then searches),
    and `MANUAL` sets the manual value."""
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera.opencv.opencv_helpers import opencv_apply_config as module

    monkeypatch.setattr(module.sys, "platform", platform)
    capture = _capture()
    module._apply_exposure(capture, CameraConfig(exposure_mode=mode, exposure=-8))
    calls = [c.args for c in capture.set.call_args_list]
    if platform != "win32":
        assert calls == [(cv2.CAP_PROP_AUTO_EXPOSURE, module.AUTO_EXPOSURE_SETTING)]
    elif mode == "AUTO":
        assert calls == []
    else:
        assert calls == [(cv2.CAP_PROP_AUTO_EXPOSURE, module.MANUAL_EXPOSURE_SETTING),
                                 (cv2.CAP_PROP_EXPOSURE, -8.0)]


@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
def test_opencv_source_forces_auto_exposure_on_linux_and_macos_only(monkeypatch, platform):
    """1.7 [AC5B]: the OpenCV source sets the camera's auto exposure on Linux and macOS for each set; on Windows a
    manual set stays manual. It searches only on Windows."""
    from skellycam.core.camera.capture import opencv_source
    from skellycam.core.camera.capture.source import ControlSetting
    from skellycam.core.camera.config.camera_config import CameraConfig

    monkeypatch.setattr(opencv_source.sys, "platform", platform)
    source = opencv_source.OpenCVSource(CameraConfig())
    source._capture = _capture()
    readback = source.set_controls({"exposure": ControlSetting(auto=False, value=-8)})
    assert readback["exposure"].auto is (platform != "win32")
    assert source.searches is (platform == "win32")


# ---------------------------------------------------------------------------
# 1.3b, 1.4: the search at an open (T-REQ-06, 12, 18, 19, 42 to 47, 62 to 65, 68, 74)
# ---------------------------------------------------------------------------

MODEL = ((-12, 10), (-11, 20), (-10, 40), (-9, 70), (-8, 110), (-7, 150), (-6, 190), (-5, 230))  # T-REQ-01
SEARCH = [(False, value) for value in range(-12, -4)]
SLOW_TEXT = "Camera is slow. Try adding more light"


def auto(app, camera_id, **changes):
    return app.config(camera_id, **{"exposure_mode": "AUTO", **changes})


def group_state(app):
    return next(iter(app.manager.to_state_dict()["camera_groups"].values()))


def run_of_states(app, camera_id):
    """The states of the tracker, with each run of one state as one item."""
    states = [state for _, state in app.tracker.states(camera_id)]
    return [state for i, state in enumerate(states) if i == 0 or states[i - 1] != state]


def open_sets(app, camera_id):
    """The first exposure set of each open, from the events of the fake."""
    firsts, opened = [], False
    for name, _, detail in app.factory.logs[camera_id].events:
        if name == "open":
            opened = True
        elif name == "set_controls" and opened and "exposure" in detail:
            firsts.append((detail["exposure"].auto, detail["exposure"].value))
            opened = False
    return firsts


def search_sets_after(app, camera_id, index):
    return [(s["exposure"].auto, s["exposure"].value) for s in app.factory.logs[camera_id].settings[index:]
            if "exposure" in s]


def test_t_req_06_a_connect_in_auto_answers_in_adjusting_and_searches(monkeypatch):
    """T-REQ-06, 1.3b [G1, G2, B1, H1, B20]: one set of -7 at step 5; no start-up rate check; the states
    `starting`, `waiting`, `adjusting`, `checking`, `ready`; the apply answers when the camera is `adjusting`
    (the fake holds its frames after the first set of the search), with -7 and `exposure_found_at_fps` None;
    then the sets -12 to -5, then -9; open count 1; the ring gets frames during the search; the live state holds
    `AUTO`, -9, 30 and `exposure_search.count` 1."""
    from skellycam.tests.capture.capture_session import Spies

    with capture_app(monkeypatch, [FakeScript(brightness=MODEL, hold_first_change=True)], track=True) as app:
        spies = Spies(monkeypatch, app)
        camera_id = app.factory.camera_ids[0]
        app.detect()
        response = app.apply([auto(app, camera_id)])
        assert response.status_code == 200, response.text
        assert app.state(camera_id) == "adjusting"
        config = response.json()["camera_configs"][camera_id]
        assert (config["exposure_mode"], config["exposure"], config["exposure_found_at_fps"]) == ("AUTO", -7, None)
        assert app.status(camera_id)["exposure_search"]["state"] == "running"
        app.factory.sources[camera_id].release()
        app.wait_state(camera_id, "ready")
        assert exposure_sets(app, camera_id) == [(False, -7)] + SEARCH + [(False, -9)]
        assert app.factory.logs[camera_id].opens.value == 1
        assert run_of_states(app, camera_id) == ["starting", "waiting", "adjusting", "checking", "ready"]
        sets = [t for name, t, detail in app.factory.logs[camera_id].events if name == "set_controls" and detail]
        assert any(sets[1] < e["arrival_ns"] < sets[-1] for e in spies.of("jpeg")), "no ring frame in the search"
        state = group_state(app)
        held = state["configs"][camera_id]
        assert (held["exposure_mode"], held["exposure"], held["exposure_found_at_fps"]) == ("AUTO", -9, 30.0)
        search = state["cameras"][camera_id]["status"]["exposure_search"]
        assert (search["state"], search["chosen"], search["count"], search["reason"]) == ("done", -9, 1, None)


def test_t_req_12_and_74_each_open_sets_the_held_value_then_searches(monkeypatch):
    """T-REQ-12 and T-REQ-74, 1.3a [A8, G1], 1.5 [B20]: a connect, a reopen by a size change, a reopen by a rate
    change (the requests hold `exposure` -5), "apply again" after a failed open, and an unselect and a reselect.
    Each open sets the held value -9 first, then searches; each ends with -9 found at its mode rate;
    `exposure_search.count` is 1 to 5; a new group starts at 1."""
    modes = ((640, 480, 30, 1, "MJPG"), (320, 240, 30, 1, "MJPG"), (640, 480, 60, 1, "MJPG"))
    script = FakeScript(modes=modes, brightness=MODEL, fail_opens=(4,))
    with capture_app(monkeypatch, [script]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()

        def step(config, count, rate):
            response = app.apply([config])
            assert response.status_code == 200, response.text
            app.wait_state(camera_id, "ready")
            held = group_state(app)["configs"][camera_id]
            search = app.status(camera_id)["exposure_search"]
            assert (held["exposure"], held["exposure_found_at_fps"], search["count"]) == (-9, rate, count), held

        held = dict(exposure=-9, exposure_found_at_fps=30.0)
        step(auto(app, camera_id, **held), 1, 30.0)
        step(auto(app, camera_id, width=320, height=240, exposure=-5), 2, 30.0)
        step(auto(app, camera_id, framerate=60.0, exposure=-5), 3, 60.0)
        failed = app.apply([auto(app, camera_id, exposure=-5)])
        assert failed.status_code == 200 and camera_id in failed.json()["camera_failures"], failed.text
        step(auto(app, camera_id, exposure=-9, exposure_found_at_fps=60.0), 4, 30.0)
        assert app.apply([auto(app, camera_id, use_this_camera=False)]).status_code == 200
        step(auto(app, camera_id, exposure=-9), 5, 30.0)
        assert open_sets(app, camera_id) == [(False, -9)] * 5  # open 4 failed before its set
        app.client.delete("/skellycam/camera/group/close/all")
        step(auto(app, camera_id, **held), 1, 30.0)


def test_t_req_19_the_server_reason_of_a_slow_camera_in_manual(monkeypatch):
    """T-REQ-19 (the `MANUAL` cameras), 1.5a [G3, H5, B8]: a camera in `MANUAL` that fails the start-up rate check
    at 60 fps gets the reason `declared 60.00 fps, measured ... fps. Camera is slow. Try adding more light`, to the
    character, with no ` Or choose 30 fps.`. T-CAP-18 holds the case at 30 fps."""
    import re

    with capture_app(monkeypatch, [FakeScript(modes=((640, 480, 60, 1, "MJPG"),), rate=51.5)]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([app.config(camera_id)]).status_code == 200
        app.wait_state(camera_id, "failed")
        failure = app.status(camera_id)["failure"]
        assert re.fullmatch(r"declared 60\.00 fps, measured \d+\.\d\d fps\. " + re.escape(SLOW_TEXT), failure["reason"])
        assert failure["code"] == "rate-low"


def test_t_req_44_a_failed_search_at_an_open_keeps_the_camera(monkeypatch):
    """T-REQ-44 and T-REQ-19 (the `AUTO` camera), 1.3b [H3], 1.5a: the generic camera (25.76 fps at each value)
    in `AUTO` held at -7 found at 30: no `failed` state and no start-up reason; the search fails with
    `exposure_search_failed`; the last set is -7; `exposure_found_at_fps` stays 30; the check gives `too_slow`;
    the camera keeps its preview."""
    with capture_app(monkeypatch, [FakeScript(rate=25.76, brightness=MODEL)]) as app:
        generic = app.factory.camera_ids[0]
        app.detect()
        response = app.apply([auto(app, generic, exposure=-7, exposure_found_at_fps=30.0)])
        assert response.status_code == 200 and not response.json()["camera_failures"], response.text
        app.wait_state(generic, "too_slow", "failed")
        status = app.status(generic)
        assert status["state"] == "too_slow" and status["failure"] is None, status
        assert status["exposure_search"]["reason"] == "no-value-kept-rate"
        assert exposure_sets(app, generic)[-1] == (False, -7)
        assert group_state(app)["configs"][generic]["exposure_found_at_fps"] == 30.0
        items = [w for w in status["warnings"] if w["kind"] == "exposure_search_failed"]
        assert items == [{"kind": "exposure_search_failed", "camera_ids": [generic], "control": "exposure",
                          "text": f"Camera {generic}: the exposure search failed: no exposure from -12 to -5 keeps "
                                  f"30 fps. The exposure is -7 again."}]
        assert generic in (app.group.read_latest_ring_frames() or {})


def test_t_req_42_cameras_that_open_together_search_together(monkeypatch, tmp_path):
    """T-REQ-42, 1.3b [G2, B1, H1]: three fakes in `AUTO`, one opens 1 s later. No camera is `adjusting` before
    the last leaves `starting`; the apply answers with the three in `adjusting`; a record start gets 409 that
    names each camera and `adjusting`; `exposure_search.state` is `running`; the live state holds the three
    results after the searches."""
    brighter = tuple((value, min(gray + 40, 255)) for value, gray in MODEL)
    scripts = [FakeScript(brightness=MODEL, hold_first_change=True),
               FakeScript(brightness=brighter, hold_first_change=True),
               FakeScript(brightness=MODEL, hold_first_change=True, open_delay_s=1.0)]
    with capture_app(monkeypatch, scripts, track=True) as app:
        ids = app.factory.camera_ids
        app.detect()
        response = app.apply([auto(app, camera_id) for camera_id in ids])
        assert response.status_code == 200, response.text
        assert [app.state(camera_id) for camera_id in ids] == ["adjusting"] * 3
        assert all(app.status(camera_id)["exposure_search"]["state"] == "running" for camera_id in ids)
        last_waiting = app.tracker.first(ids[2], "waiting")
        assert all(app.tracker.first(camera_id, "adjusting") >= last_waiting for camera_id in ids)
        refused = app.record_start(tmp_path)
        assert refused.status_code == 409, refused.text
        assert all(f"camera {camera_id} is adjusting" in refused.text for camera_id in ids), refused.text
        for camera_id in ids:
            app.factory.sources[camera_id].release()
        for camera_id in ids:
            app.wait_state(camera_id, "ready")
        configs = group_state(app)["configs"]
        assert [configs[camera_id]["exposure"] for camera_id in ids] == [-9, -10, -9]


def test_t_req_43_a_reselected_camera_searches_alone(monkeypatch, tmp_path):
    """T-REQ-43, 1.3b [H2]: three fakes `ready` in `AUTO`; the third is unselected, then selected again. Only the
    third camera searches; the two others get no set call and stay `ready`; a record start during the search
    gets 409 that names the third camera."""
    scripts = [FakeScript(brightness=MODEL), FakeScript(brightness=MODEL),
               FakeScript(brightness=MODEL, hold_first_change=True)]
    with capture_app(monkeypatch, scripts) as app:
        ids = app.factory.camera_ids
        app.detect()
        assert app.apply([auto(app, camera_id) for camera_id in ids]).status_code == 200
        app.factory.sources[ids[2]].release()
        for camera_id in ids:
            app.wait_state(camera_id, "ready")
        assert app.apply([auto(app, ids[2], use_this_camera=False)]).status_code == 200
        before = {camera_id: len(app.factory.logs[camera_id].settings) for camera_id in ids[:2]}
        response = app.apply([auto(app, ids[2])])
        assert response.status_code == 200 and app.state(ids[2]) == "adjusting", response.text
        refused = app.record_start(tmp_path)
        assert refused.status_code == 409 and f"camera {ids[2]} is adjusting" in refused.text, refused.text
        app.factory.sources[ids[2]].release()
        app.wait_state(ids[2], "ready")
        for camera_id in ids[:2]:
            assert not [s for s in app.factory.logs[camera_id].settings[before[camera_id]:] if s]
            assert app.state(camera_id) == "ready"


def test_t_req_45_manual_never_searches(monkeypatch):
    """T-REQ-45, 1.3b [G1]: one fake in `MANUAL -6`: a connect and a reopen by a rate change. No search; one set
    of -6 at each open; the start-up rate check judges each open; `waiting`, then `ready`."""
    modes = ((640, 480, 30, 1, "MJPG"), (640, 480, 60, 1, "MJPG"))
    with capture_app(monkeypatch, [FakeScript(modes=modes)], track=True) as app:
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, exposure=-6)])
        assert app.apply([app.config(camera_id, exposure=-6, framerate=60.0)]).status_code == 200
        app.wait_state(camera_id, "ready")
        assert open_sets(app, camera_id) == [(False, -6), (False, -6)]
        assert set(exposure_sets(app, camera_id)) == {(False, -6)}  # also the restore at the close of the reopen
        assert "adjusting" not in run_of_states(app, camera_id)
        status = app.status(camera_id)
        assert status["exposure_search"] is None and status["measured_fps"], status


def test_t_req_46_the_ready_limit_ends_at_the_warm_up(monkeypatch):
    """T-REQ-46, 1.3b [B3]: the warm-up ends about 4 s after the open, and the search takes about 13 s (-9 kept,
    each other value slow). The camera does not fail with "not ready in 15 s"; the search ends with -9."""
    slow = tuple((value, 15.0) for value in range(-12, -4) if value != -9)
    script = FakeScript(brightness=MODEL, rate_by_exposure=slow, open_delay_s=1.0)
    with capture_app(monkeypatch, [script]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([auto(app, camera_id, exposure=-9)]).status_code == 200
        app.wait_state(camera_id, "ready", "failed", "too_slow")
        status = app.status(camera_id)
        assert status["state"] == "ready" and status["failure"] is None, status
        assert status["exposure_search"]["chosen"] == -9


def test_t_req_47_the_state_route_gives_the_live_state(monkeypatch):
    """T-REQ-47, 1.5 [H1, B15, K1]: a client with no websocket reads `GET /camera/group/state` from the apply to
    the end of the check. Each body equals `to_state_dict()` of the same read; the camera is `adjusting` with
    `exposure_search.state` `running`, then `ready`; the last read holds -9 and 30; no body has `paused`."""
    import json

    with capture_app(monkeypatch, [FakeScript(brightness=MODEL, hold_first_change=True)]) as app:
        camera_id = app.factory.camera_ids[0]
        hooked = []
        to_state_dict = app.manager.to_state_dict

        def hook():
            hooked.append(to_state_dict())
            return hooked[-1]

        monkeypatch.setattr(app.manager, "to_state_dict", hook)
        app.detect()
        assert app.apply([auto(app, camera_id)]).status_code == 200
        bodies = []

        def read():
            response = app.client.get("/skellycam/camera/group/state")
            assert response.status_code == 200, response.text
            bodies.append(response.json())
            assert json.loads(json.dumps(hooked[-1], default=str)) == bodies[-1]
            return next(iter(bodies[-1]["camera_groups"].values()))

        first = read()["cameras"][camera_id]["status"]
        assert (first["state"], first["exposure_search"]["state"]) == ("adjusting", "running")
        app.factory.sources[camera_id].release()
        app.wait(lambda: read()["cameras"][camera_id]["status"]["state"] == "ready", "ready in the state route")
        last = next(iter(bodies[-1]["camera_groups"].values()))["configs"][camera_id]
        assert (last["exposure"], last["exposure_found_at_fps"]) == (-9, 30.0)
        assert '"paused":' not in json.dumps(bodies)


def test_t_req_62_an_unselect_and_a_close_during_a_search(monkeypatch):
    """T-REQ-62, 1.9 [H3]: two fakes `adjusting` at an open. The unselected camera closes, its search stops with
    the reason `camera-closed`, and it gets no set of its old value: only the restore of the close. The other
    search goes on until the group closes, with no set of its own after that."""
    scripts = [FakeScript(brightness=MODEL, hold_first_change=True) for _ in range(2)]
    with capture_app(monkeypatch, scripts) as app:
        first, second = app.factory.camera_ids
        app.detect()
        assert app.apply([auto(app, first), auto(app, second)]).status_code == 200
        app.factory.sources[first].release()
        response = app.apply([auto(app, first, use_this_camera=False)])
        assert response.status_code == 200, response.text
        removed = app.group.cameras.removed_statuses[first].serialize()["exposure_search"]
        assert (removed["state"], removed["reason"]) == ("failed", "camera-closed")
        app.factory.sources[second].release()
        app.wait(lambda: len(exposure_sets(app, second)) >= 4, "the search of the other camera runs")
        assert app.state(second) == "adjusting"
        app.client.delete("/skellycam/camera/group/close/all")
    for camera_id in (first, second):
        log = app.factory.logs[camera_id]
        close = [t for name, t, _ in log.events if name == "close"][-1]
        sets = [(t, d["exposure"]) for name, t, d in log.events if name == "set_controls" and "exposure" in d]
        assert all(t >= close or s.value in range(-12, -4) for t, s in sets[1:]), sets
        assert not [s for t, s in sets if t >= close and s.value == -7], "the search set its old value"


def test_t_req_63_a_hung_set_of_the_search_ends_the_camera_with_no_restore(monkeypatch):
    """T-REQ-63, 1.3 item 7: a set call of the search hangs. The camera dies by 6.6, and no restore set comes."""
    script = FakeScript(brightness=MODEL, hold_first_change=True, hang_at="set_controls")
    with capture_app(monkeypatch, [script]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([auto(app, camera_id)]).status_code == 200
        log = app.factory.logs[camera_id]
        log.arm_hang()
        app.factory.sources[camera_id].release()
        app.wait_state(camera_id, "dead")
        app.wait(lambda: app.status(camera_id)["closed"], "the camera ends")
        assert app.status(camera_id)["failure"]["code"] == "hung", app.status(camera_id)["failure"]
    names = log.names()
    assert "set_controls" not in names[names.index("hang") + 1:], "a set came after the hang"


def test_t_req_64_no_control_read_during_a_search(monkeypatch):
    """T-REQ-64, 1.3 [A4]: the read each second (`set_controls({})`) waits while the search runs, and comes again
    after it. The fake holds its frames for 1.5 s (real time) after the first set of the search."""
    import time

    with capture_app(monkeypatch, [FakeScript(brightness=MODEL, hold_first_change=True)]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([auto(app, camera_id)]).status_code == 200
        time.sleep(1.5)
        app.factory.sources[camera_id].release()
        app.wait_state(camera_id, "ready")
        settings = app.factory.logs[camera_id].settings
        app.wait(lambda: not settings[-1], "a read after the search")
        first = next(i for i, s in enumerate(settings) if s.get("exposure") and s["exposure"].value == -12)
        last = next(i for i, s in enumerate(settings) if i > first and s.get("exposure") and s["exposure"].value == -5)
        assert all(settings[first:last + 2]), "a control read came during the search"  # + 2: the set of the result


def test_t_req_65_a_frame_that_waits_at_the_gate_gives_no_early_decision(monkeypatch):
    """T-REQ-65, 1.3, 10.2 agent 88: two push fakes at 30 fps search at the same time; B delivers 15 fps at -6 and
    -5. The trials of A keep the rate at each value."""
    scripts = [FakeScript(brightness=MODEL), FakeScript(brightness=MODEL, rate_by_exposure=((-6, 15.0), (-5, 15.0)))]
    with capture_app(monkeypatch, scripts) as app:
        a, b = app.factory.camera_ids
        app.detect()
        assert app.apply([auto(app, a), auto(app, b)]).status_code == 200
        app.wait(lambda: app.status(a)["exposure_search"]["state"] == "done"
                 and app.status(b)["exposure_search"]["state"] == "done", "the two searches end")
        assert [t["kept_rate"] for t in app.status(a)["exposure_search"]["trials"]] == [True] * 8
        assert [t["kept_rate"] for t in app.status(b)["exposure_search"]["trials"]][-2:] == [False, False]


def test_t_req_18_a_camera_removed_during_its_search(monkeypatch):
    """T-REQ-18 (at an open), 1.9: two fakes search; one gives device removed during its search. That camera is
    `dead`, with no restore set; the other ends its search."""
    scripts = [FakeScript(brightness=MODEL), FakeScript(brightness=MODEL, removed_after_frame=150)]
    with capture_app(monkeypatch, scripts) as app:
        good, removed = app.factory.camera_ids
        app.detect()
        assert app.apply([auto(app, good), auto(app, removed)]).status_code == 200
        app.wait_state(removed, "dead")
        app.wait_state(good, "ready")
        log = app.factory.logs[removed]
        app.wait(lambda: log.closes.value == 1, "the close of the removed camera")
        close = [t for name, t, _ in log.events if name == "close"][-1]
        assert not [d for name, t, d in log.events if name == "set_controls" and d and t >= close]
        assert app.status(good)["exposure_search"]["state"] == "done"


def test_t_req_68_add_light_stays_until_the_next_exposure_change(monkeypatch, tmp_path):
    """T-REQ-68 (the parts of code step 3), 1.5 [AC5B]: a search at an open ends with `add_light`. The item stays
    after an apply with the same config and after a record start and stop; it goes after an apply with
    `MANUAL -7`."""
    dark = tuple((value, 50 - 5 * (-5 - value)) for value in range(-12, -4))
    with capture_app(monkeypatch, [FakeScript(brightness=dark)]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([auto(app, camera_id)]).status_code == 200
        app.wait_state(camera_id, "ready")

        def kinds():
            return [w["kind"] for w in app.status(camera_id)["warnings"]]

        item = next(w for w in app.status(camera_id)["warnings"] if w["kind"] == "add_light")
        assert item["text"].startswith(f"Camera {camera_id}: add light. At 30 fps the brightest exposure")
        assert app.apply([auto(app, camera_id)]).status_code == 200
        assert app.record_start(tmp_path).status_code == 200
        assert app.record_stop().status_code == 200
        assert kinds() == ["add_light"]
        assert app.apply([app.config(camera_id)]).status_code == 200
        app.wait_state(camera_id, "ready")
        assert kinds() == []


# ---------------------------------------------------------------------------
# 1.2 (c), 1.5: the search on request (T-REQ-01, 02, 04, 05, 10, 11, 13, 16, 17, 22, 66, 69, 72)
# ---------------------------------------------------------------------------

def press(app, camera_ids=None):
    """POST /camera/group/exposure/auto: the button (no body), or "Search again" (`camera_ids`)."""
    body = None if camera_ids is None else {"camera_ids": list(camera_ids)}
    return app.client.post("/skellycam/camera/group/exposure/auto", json=body)


def ready_manual(app, **changes):
    ready_app_steps(app, [app.config(camera_id, **changes) for camera_id in app.factory.camera_ids])


def test_t_req_01_a_switch_to_auto_searches_on_the_open_stream(monkeypatch):
    """T-REQ-01, 1.2 (c), 1.3: one fake `ready` in `MANUAL -7`; apply `AUTO`. The response has the camera in
    `adjusting`; the fake gets the sets -12 to -5 in order, then -9; the config holds `AUTO`, -9, 30; no
    `add_light`; the states `adjusting`, `checking`, `ready`."""
    with capture_app(monkeypatch, [FakeScript(brightness=MODEL, hold_first_change=True)], track=True) as app:
        camera_id = app.factory.camera_ids[0]
        ready_manual(app)
        response = app.apply([auto(app, camera_id, exposure=-7)])
        assert response.status_code == 200 and app.state(camera_id) == "adjusting", response.text
        app.factory.sources[camera_id].release()
        app.wait_state(camera_id, "ready")
        assert exposure_sets(app, camera_id) == [(False, -7)] + SEARCH + [(False, -9)]
        held = group_state(app)["configs"][camera_id]
        assert (held["exposure_mode"], held["exposure"], held["exposure_found_at_fps"]) == ("AUTO", -9, 30.0)
        assert not app.status(camera_id)["warnings"]
        assert run_of_states(app, camera_id)[-4:] == ["ready", "adjusting", "checking", "ready"]


def test_t_req_02_the_button_searches_with_no_reopen(monkeypatch):
    """T-REQ-02, 1.3 [E7]: -6 and -5 at 15 fps; press the button. The open count stays 1; the ring name does not
    change; the ring gets frames during the search; `ready`, `adjusting`, `checking`, `ready`; the result is -9;
    the trials of -6 and -5 have `kept_rate` false. The response has the configs and the results."""
    from skellycam.tests.capture.capture_session import Spies

    script = FakeScript(brightness=MODEL, rate_by_exposure=((-6, 15.0), (-5, 15.0)))
    with capture_app(monkeypatch, [script], track=True) as app:
        spies = Spies(monkeypatch, app)
        camera_id = app.factory.camera_ids[0]
        ready_manual(app)
        ring = app.ring_name(camera_id)
        response = press(app)
        assert response.status_code == 200, response.text
        body = response.json()
        result = body["results"][camera_id]
        assert (result["state"], result["chosen"], result["count"]) == ("done", -9, 1)
        assert [t["kept_rate"] for t in result["trials"]][-2:] == [False, False]
        config = body["camera_configs"][camera_id]
        assert (config["exposure_mode"], config["exposure"], config["exposure_found_at_fps"]) == ("AUTO", -9, 30.0)
        assert body["camera_failures"] == {} and body["warnings"] == []
        app.wait_state(camera_id, "ready")
        assert app.factory.logs[camera_id].opens.value == 1 and app.ring_name(camera_id) == ring
        sets = [t for name, t, detail in app.factory.logs[camera_id].events if name == "set_controls" and detail]
        assert any(sets[1] < e["arrival_ns"] < sets[-1] for e in spies.of("jpeg")), "no ring frame in the search"
        assert run_of_states(app, camera_id)[-4:] == ["ready", "adjusting", "checking", "ready"]


def test_t_req_04_add_light_in_the_response_and_the_status(monkeypatch):
    """T-REQ-04, 1.3 item 5 [Q6]: brightness 50 at -5, darker below; press the button. The result is -6 with
    `add_light`; the response and the status `warnings` hold `add_light`; the camera is `ready`."""
    dark = tuple((value, 50 - 5 * (-5 - value)) for value in range(-12, -4))
    with capture_app(monkeypatch, [FakeScript(brightness=dark)]) as app:
        camera_id = app.factory.camera_ids[0]
        ready_manual(app)
        response = press(app)
        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["results"][camera_id]["chosen"], body["results"][camera_id]["add_light"]) == (-6, True)
        assert [w["kind"] for w in body["warnings"]] == ["add_light"]
        app.wait_state(camera_id, "ready")
        assert body["warnings"][0] in app.status(camera_id)["warnings"]


def test_t_req_05_a_failed_search_sets_the_old_manual_value_again(monkeypatch):
    """T-REQ-05, 1.3 item 6: the camera slows to 25.76 fps after it is `ready` in `MANUAL -7`; press the button.
    The search fails; the last set is `MANUAL -7`; the config is `MANUAL -7` again; `exposure_search_failed` with
    its text; the check gives `too_slow`, and the camera keeps its preview."""
    script = FakeScript(brightness=MODEL, rate_windows=((6.0, 1000.0, 25.76),))
    with capture_app(monkeypatch, [script]) as app:
        camera_id = app.factory.camera_ids[0]
        ready_manual(app)
        app.wait(lambda: app.clock.now_ns() > app.clock.START_NS + 6.5e9, "the camera is slow")
        response = press(app)
        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["results"][camera_id]["state"], body["results"][camera_id]["reason"]) == (
            "failed", "no-value-kept-rate")
        assert exposure_sets(app, camera_id)[-1] == (False, -7)
        config = body["camera_configs"][camera_id]
        assert (config["exposure_mode"], config["exposure"]) == ("MANUAL", -7)
        assert [w["kind"] for w in body["warnings"]] == ["exposure_search_failed"]
        assert body["warnings"][0]["text"].endswith("keeps 30 fps. The exposure is -7 again.")
        app.wait_state(camera_id, "too_slow")
        assert camera_id in (app.group.read_latest_ring_frames() or {})


def test_t_req_10_a_switch_of_one_camera_leaves_the_others(monkeypatch, tmp_path):
    """T-REQ-10, 1.2, 1.4: two fakes `ready` in `MANUAL`; apply B with `AUTO` only. During the search of B a record
    start gets 409 that names B and `adjusting`, and an apply that changes the size of B gets 409. Only B
    searches; A gets no set call; the rings of A and B get frames during the search."""
    from skellycam.tests.capture.capture_session import Spies

    modes = ((640, 480, 30, 1, "MJPG"), (320, 240, 30, 1, "MJPG"))
    scripts = [FakeScript(modes=modes), FakeScript(modes=modes, brightness=MODEL, hold_first_change=True)]
    with capture_app(monkeypatch, scripts) as app:
        spies = Spies(monkeypatch, app)
        a, b = app.factory.camera_ids
        ready_manual(app)
        before = len(app.factory.logs[a].settings)
        assert app.apply([auto(app, b)]).status_code == 200
        assert app.state(b) == "adjusting"
        refused = app.record_start(tmp_path)
        assert refused.status_code == 409 and f"camera {b} is adjusting" in refused.text, refused.text
        assert app.apply([auto(app, b, width=320, height=240)]).status_code == 409
        app.factory.sources[b].release()
        app.wait_state(b, "ready")
        assert not [s for s in app.factory.logs[a].settings[before:] if s]
        sets = [t for name, t, detail in app.factory.logs[b].events if name == "set_controls" and detail]
        for camera_id in (a, b):
            assert any(sets[1] < e["arrival_ns"] < sets[-1] for e in spies.of("jpeg", camera_id)), camera_id


def test_t_req_11_no_search_during_a_take(monkeypatch, tmp_path):
    """T-REQ-11, 1.1 [E3, G4], 1.5 [D36]: a recording runs with two fakes. The button, "Search again" for one
    camera and an apply with `AUTO` for one camera each get 409; the fakes get no set call; the configs do not
    change."""
    with capture_app(monkeypatch, [FakeScript(brightness=MODEL), FakeScript(brightness=MODEL)]) as app:
        a, b = app.factory.camera_ids
        ready_manual(app)
        configs = dict(app.group.configs)
        before = {camera_id: len(app.factory.logs[camera_id].settings) for camera_id in (a, b)}
        assert app.record_start(tmp_path).status_code == 200
        try:
            assert press(app).status_code == 409
            assert press(app, [a]).status_code == 409
            assert app.apply([auto(app, a)]).status_code == 409
            for camera_id in (a, b):
                assert not [s for s in app.factory.logs[camera_id].settings[before[camera_id]:] if s]
            assert app.group.configs == configs
        finally:
            assert app.record_stop().status_code == 200


def test_t_req_13_and_22_the_button_and_search_again(monkeypatch):
    """T-REQ-13 and T-REQ-22, 1.2 (c), 1.5 [B20]: three fakes `ready`, two in `MANUAL` and one in `AUTO`. "Search
    again" for one camera searches only that camera; a camera ID that is not selected gets 422. The button
    searches each camera one time, each ends in `AUTO` with its own value, the response has `results` for the
    three, a second press while it runs gets 409, and each `exposure_search.count` is one more than before."""
    import threading

    models = [MODEL, tuple((value, min(gray + 40, 255)) for value, gray in MODEL), MODEL]
    with capture_app(monkeypatch, [FakeScript(brightness=model) for model in models]) as app:
        ids = app.factory.camera_ids
        app.detect()
        assert app.apply([app.config(ids[0]), app.config(ids[1]), auto(app, ids[2])]).status_code == 200
        for camera_id in ids:
            app.wait_state(camera_id, "ready")
        before = {camera_id: len(app.factory.logs[camera_id].settings) for camera_id in ids}
        again = press(app, [ids[0]])
        assert again.status_code == 200 and list(again.json()["results"]) == [ids[0]], again.text
        assert all(not [s for s in app.factory.logs[c].settings[before[c]:] if s] for c in ids[1:])
        assert press(app, ["ffff"]).status_code == 422
        app.wait_state(ids[0], "ready")
        counts = {camera_id: (app.status(camera_id)["exposure_search"] or {"count": 0})["count"] for camera_id in ids}
        responses = []
        thread = threading.Thread(target=lambda: responses.append(press(app)))
        thread.start()
        app.wait(lambda: any(app.state(camera_id) == "adjusting" for camera_id in ids), "a search runs")
        second = press(app)
        thread.join(60)
        assert second.status_code == 409, second.text
        body = responses[0].json()
        assert responses[0].status_code == 200 and sorted(body["results"]) == sorted(ids), body
        configs = body["camera_configs"]
        assert [configs[c]["exposure_mode"] for c in ids] == ["AUTO"] * 3
        assert [configs[c]["exposure"] for c in ids] == [-9, -10, -9]
        assert [body["results"][c]["count"] for c in ids] == [counts[c] + 1 for c in ids]


def test_t_req_16_a_switch_to_manual_is_a_live_set(monkeypatch):
    """T-REQ-16, 1.3a, 11.2: `ready` in `AUTO` held at -9 found at 30; apply `MANUAL -7`. One live set of -7; no
    search; `checking`, then `ready`; `exposure_found_at_fps` is None."""
    with capture_app(monkeypatch, [FakeScript(brightness=MODEL)], track=True) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([auto(app, camera_id, exposure=-9, exposure_found_at_fps=30.0)]).status_code == 200
        app.wait_state(camera_id, "ready")
        count = len(exposure_sets(app, camera_id))
        response = app.apply([app.config(camera_id, exposure=-7, exposure_found_at_fps=30.0)])
        assert response.status_code == 200, response.text
        app.wait_state(camera_id, "ready")
        assert exposure_sets(app, camera_id)[count:] == [(False, -7)]
        config = response.json()["camera_configs"][camera_id]
        assert (config["exposure_mode"], config["exposure"], config["exposure_found_at_fps"]) == ("MANUAL", -7, None)
        assert run_of_states(app, camera_id)[-3:] == ["ready", "checking", "ready"]


def test_t_req_17_failed_sets_and_the_limit_with_the_loop(monkeypatch):
    """T-REQ-17, 1.3 item 6, 1.5: the set of -9 returns an error; then the set of -9 reads back -8; then each
    value is slow so that the search passes 20 s. Each search fails with `set-failed`, `readback-differs`,
    `timed-out` and the text of 1.5; the last set is the old setting; the camera stays open."""
    faults = (None, None, None, "error", None, None, None, None, "readback:-8")
    with capture_app(monkeypatch, [FakeScript(brightness=MODEL, live_set_faults=faults)]) as app:
        camera_id = app.factory.camera_ids[0]
        ready_manual(app)
        texts = {"set-failed": "the camera refused exposure -9 (the camera refused the value)",
                 "readback-differs": "exposure -9 read back as -8", "timed-out": "it took more than 20 s"}
        for reason in ("set-failed", "readback-differs", "timed-out"):
            if reason == "timed-out":
                app.factory.sources[camera_id].slow_period(rate=5.0, seconds=60.0)
            response = press(app)
            assert response.status_code == 200, response.text
            body = response.json()
            assert (body["results"][camera_id]["state"], body["results"][camera_id]["reason"]) == ("failed", reason)
            assert body["warnings"][0]["text"] == (f"Camera {camera_id}: the exposure search failed: {texts[reason]}. "
                                                   f"The exposure is -7 again.")
            assert exposure_sets(app, camera_id)[-1] == (False, -7)
            app.wait_state(camera_id, "ready", "too_slow")


def test_t_req_66_no_search_while_a_camera_starts(monkeypatch):
    """T-REQ-66, 1.5: one fake held in `starting`, and one in `waiting`. The button and "Search again" get 409;
    the detail names the camera and its state."""
    import threading

    scripts = [FakeScript(hold_opens=(1,)), FakeScript()]
    with capture_app(monkeypatch, scripts) as app:
        held, other = app.factory.camera_ids
        app.detect()
        thread = threading.Thread(target=lambda: app.apply([app.config(held), app.config(other)]))
        thread.start()
        try:
            app.wait(lambda: app.group_or_none() is not None and app.state(other) == "waiting", "one camera waits")
            for camera_ids in (None, [other]):
                refused = press(app, camera_ids)
                assert refused.status_code == 409, refused.text
                assert f"camera {held} is starting" in refused.text and f"camera {other} is waiting" in refused.text
        finally:
            app.factory.sources[held].release()
            thread.join(60)


def test_t_req_69_the_button_skips_a_camera_that_does_not_stream(monkeypatch):
    """T-REQ-69, 1.9: three fakes, one `ready`, one `failed`, one `dead`; press the button. Only the `ready` camera
    searches; the response names the two others as "not streaming"."""
    scripts = [FakeScript(brightness=MODEL), FakeScript(fail_opens=(1,)), FakeScript()]
    with capture_app(monkeypatch, scripts) as app:
        good, failed, dead = app.factory.camera_ids
        app.detect()
        assert app.apply([app.config(camera_id) for camera_id in (good, failed, dead)]).status_code == 200
        app.wait_state(good, "ready")
        app.factory.sources[dead].stop_now()
        app.wait_state(dead, "dead")
        response = press(app)
        assert response.status_code == 200, response.text
        body = response.json()
        assert list(body["results"]) == [good]
        assert sorted(body["not_streaming"]) == sorted([failed, dead])


def test_t_req_72_the_manager_call_and_the_route_give_the_same_response(monkeypatch):
    """T-REQ-72, 1.5 [B18]: `await CameraGroupManager.search_exposure(camera_ids=None)` with no HTTP request, then
    `POST /camera/group/exposure/auto` on a second group with the same fakes. The two responses are equal, apart
    from the measured rates; the count moves in the same way."""
    def strip(body):
        for result in body["results"].values():
            for trial in result["trials"]:
                trial.pop("measured_fps")
        return body

    bodies = []
    for via in ("manager", "route"):
        with capture_app(monkeypatch, [FakeScript(brightness=MODEL)]) as app:
            ready_manual(app)
            if via == "manager":
                body = app.client.portal.call(app.manager.search_exposure)
                body = __import__("json").loads(__import__("json").dumps(body, default=lambda o: o.model_dump(mode="json")))
            else:
                response = press(app)
                assert response.status_code == 200, response.text
                body = response.json()
            bodies.append(strip(body))
    first, second = bodies
    for body in bodies:
        body.pop("group_id", None)
        for config in body["camera_configs"].values():
            config.pop("camera_name", None)
    assert first == second


def test_t_req_21_the_opencv_source_of_linux_and_macos_does_not_search(monkeypatch):
    """T-REQ-21 (1), 1.7 [Q11, K2]: the OpenCV fake as on Linux and macOS (`OpenCVSource.searches` false; the unit
    test above checks it by the platform). A connect in `AUTO` runs no search, and the camera is never `adjusting`;
    the button and "Search again" get 422 with the text of 1.5."""
    from skellycam.core.camera.capture import opencv_source
    from skellycam.tests.capture.capture_session import CaptureApp, OpenCVFakeFactory

    monkeypatch.setattr(opencv_source.OpenCVSource, "searches", property(lambda source: False))
    factory = OpenCVFakeFactory(monkeypatch)
    app = CaptureApp(monkeypatch, factory)
    try:
        camera_id = factory.camera_ids[0]
        app.detect()
        assert app.apply([app.config(camera_id, exposure_mode="AUTO")]).status_code == 200
        app.wait_state(camera_id, "ready", "failed")
        assert app.state(camera_id) == "ready" and app.status(camera_id)["exposure_search"] is None
        for camera_ids in (None, [camera_id]):
            refused = press(app, camera_ids)
            assert refused.status_code == 422, refused.text
            assert "the exposure search does not run on the OpenCV source of this system" in refused.text
    finally:
        app.close()
