"""Part 2 of specs/camera-requests.md (one frame rate and the fall back to 30 fps): the tests T-REQ of step 4 with
the fake sources (2.4, 2.4a, 2.10).

Each test runs THREAD workers with the virtual clock of `capture_session`. The fixture `no_camera_auto_exposure`
of `conftest.py` is the spy of T-REQ-15 here too.
"""

import re
import time

from skellycam.tests.capture.capture_session import capture_app, ready_app_steps
from skellycam.tests.capture.fake_source import FakeScript
from skellycam.tests.capture.test_camera_requests import MODEL, auto, group_state, press

MODES = ((640, 480, 30, 1, "MJPG"), (640, 480, 60, 1, "MJPG"))
SLOW = 29.66  # the Kiyo Pro in its 60 fps mode (2.4); not slow at 30 fps, where the limit is 29.1
FALLBACK_TEXT = r"The group runs at 30 fps\. Camera {} measured {} fps in its 60 fps mode at exposure {}\."


def opens(app, camera_id):
    return app.factory.logs[camera_id].opens.value


def rate(app, camera_id):
    mode = app.status(camera_id)["mode"]
    return mode["fps_num"] / mode["fps_den"]


def fallback_items(app, camera_id):
    return [item for item in app.status(camera_id)["warnings"] if item["kind"] == "rate_fallback"]


def response_items(response):
    return [item for item in response.json()["warnings"] if item["kind"] == "rate_fallback"]


def released(app, camera_ids):
    """End the hold of `hold_first_change` of the current open of each camera: each open has a new fake source."""
    for camera_id in camera_ids:
        app.factory.sources[camera_id].release()
    return True


def wait_ready_at(app, camera_ids, fps):
    for camera_id in camera_ids:
        app.wait(lambda: released(app, camera_ids) and app.state(camera_id) == "ready" and rate(app, camera_id) == fps,
                 f"camera {camera_id} ready at {fps} fps")


def test_t_req_30_each_camera_keeps_60(monkeypatch):
    """T-REQ-30, 2.3, 2.4: three fakes `ready` at 30 in `MANUAL -7` deliver 60 in their 60 mode; apply 60. Each camera
    reopens one time; the group rate is 60; no `rate_fallback`; each is `ready`."""
    with capture_app(monkeypatch, [FakeScript(modes=MODES) for _ in range(3)]) as app:
        ready_app_steps(app)
        ids = app.factory.camera_ids
        response = app.apply_all(framerate=60.0)
        assert not response.json()["camera_failures"] and not response_items(response), response.text
        wait_ready_at(app, ids, 60)
        assert [opens(app, camera_id) for camera_id in ids] == [2, 2, 2]
        assert not any(fallback_items(app, camera_id) for camera_id in ids)


def test_t_req_31_a_slow_camera_in_manual_falls_the_group_back(monkeypatch):
    """T-REQ-31 and T-REQ-68 (the part of `rate_fallback`), 2.4, 2.4a: one of three fakes delivers 29.66 fps in its 60
    mode. Each camera reopens two times (60, then 30); the response has the configs at 30 and one `rate_fallback`
    item for that camera with "29.66"; `camera_failures` is empty; each is `ready`. The item survives the "apply
    again" of the fall back, and the next apply request of the user clears it."""
    scripts = [FakeScript(modes=MODES), FakeScript(modes=MODES), FakeScript(modes=MODES, rate=SLOW)]
    with capture_app(monkeypatch, scripts) as app:
        ready_app_steps(app)
        ids, slow = app.factory.camera_ids, app.factory.camera_ids[2]
        response = app.apply_all(framerate=60.0)
        body = response.json()
        assert body["camera_failures"] == {}, response.text
        assert {camera_id: config["framerate"] for camera_id, config in body["camera_configs"].items()} == dict.fromkeys(ids, 30.0)
        items = response_items(response)
        assert [item["camera_ids"] for item in items] == [[slow]], items
        assert re.fullmatch(FALLBACK_TEXT.format(slow, "29.66", "-7"), items[0]["text"]), items
        wait_ready_at(app, ids, 30)
        assert [opens(app, camera_id) for camera_id in ids] == [3, 3, 3]
        assert fallback_items(app, slow) == items  # the "apply again" of the slow camera kept it
        assert not fallback_items(app, ids[0]) and not fallback_items(app, ids[1])
        app.apply_all()  # a new apply request of the user (the same configs)
        assert not fallback_items(app, slow)


def test_t_req_32_a_search_with_no_value_at_60_falls_the_group_back(monkeypatch):
    """T-REQ-32 (first case), 2.4 [H4, B17, G1]: three fakes `ready` at 30 in `AUTO`; one delivers 29.66 fps at each
    value. Apply 60: the response has the three at 60 in `adjusting`; the search of the slow camera fails, and the one
    fall back starts with no new request; each camera reopens at 30 and searches again; the live state has the
    configs at 30 found at 30, and the slow camera has one `rate_fallback` item."""
    scripts = [FakeScript(modes=MODES, brightness=MODEL, hold_first_change=True) for _ in range(2)]
    scripts.append(FakeScript(modes=MODES, brightness=MODEL, rate=SLOW, hold_first_change=True))
    with capture_app(monkeypatch, scripts) as app:
        ids, slow = app.factory.camera_ids, app.factory.camera_ids[2]
        app.detect()
        assert app.apply([auto(app, camera_id) for camera_id in ids]).status_code == 200
        wait_ready_at(app, ids, 30)
        response = app.apply([auto(app, camera_id, framerate=60.0) for camera_id in ids])
        assert response.status_code == 200, response.text
        assert [app.state(camera_id) for camera_id in ids] == ["adjusting"] * 3
        assert all(config["framerate"] == 60.0 for config in response.json()["camera_configs"].values())
        assert not response_items(response)
        app.wait(lambda: released(app, ids) and fallback_items(app, slow), "the fall back writes rate_fallback")
        wait_ready_at(app, ids, 30)
        app.wait(lambda: all(group_state(app)["configs"][camera_id]["exposure_found_at_fps"] == 30.0 for camera_id in ids),
                 "the held values found at 30")
        items = fallback_items(app, slow)
        assert len(items) == 1 and items[0]["camera_ids"] == [slow], items
        assert re.fullmatch(FALLBACK_TEXT.format(slow, r"\d+\.\d\d", r"-\d+"), items[0]["text"]), items
        assert [opens(app, camera_id) for camera_id in ids] == [3, 3, 3]
        assert [app.status(camera_id)["exposure_search"]["count"] for camera_id in ids] == [3, 3, 3]


def test_t_req_32_a_failed_check_after_the_search_falls_the_group_back(monkeypatch):
    """T-REQ-32 (second case), 2.4 [B7, F2, Q10]: the camera keeps 60 fps at -7 in its search, then delivers 29.66 fps
    in the check of 10.2. The one fall back starts when the check fails; the camera runs at 30."""
    others = tuple((value, SLOW) for value in range(-12, -4) if value != -7)
    script = FakeScript(modes=MODES, brightness=MODEL, rate_by_exposure=others, rate_after_change=(60.0,) * 8 + (SLOW,))
    with capture_app(monkeypatch, [script]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([auto(app, camera_id)]).status_code == 200
        wait_ready_at(app, [camera_id], 30)
        assert app.apply([auto(app, camera_id, framerate=60.0)]).status_code == 200
        app.wait(lambda: fallback_items(app, camera_id), "the fall back writes rate_fallback")
        wait_ready_at(app, [camera_id], 30)
        items = fallback_items(app, camera_id)
        assert re.fullmatch(FALLBACK_TEXT.format(camera_id, r"29\.\d\d", "-7"), items[0]["text"]), items
        assert opens(app, camera_id) == 3


def test_t_req_33_a_failure_at_the_open_gives_no_fall_back(monkeypatch):
    """T-REQ-33, 2.4: one of three fakes is in use at the reopen. No fall back; that camera is `failed`, stage `open`;
    the two others run at 60."""
    scripts = [FakeScript(modes=MODES), FakeScript(modes=MODES), FakeScript(modes=MODES, fail_opens=(2,))]
    with capture_app(monkeypatch, scripts) as app:
        ready_app_steps(app)
        ids, failing = app.factory.camera_ids, app.factory.camera_ids[2]
        response = app.apply_all(framerate=60.0)
        assert response.json()["camera_failures"][failing]["stage"] == "open", response.text
        assert not response_items(response)
        wait_ready_at(app, ids[:2], 60)
        assert app.state(failing) == "failed" and not fallback_items(app, failing)


def test_t_req_34_a_camera_that_also_fails_at_30_stays_failed(monkeypatch):
    """T-REQ-34, 2.4: as T-REQ-31, and the slow fake also fails at 30. One fall back only; that camera is `failed`,
    stage `rate check`, at 30; the others run at 30."""
    scripts = [FakeScript(modes=MODES), FakeScript(modes=MODES), FakeScript(modes=MODES, rate=25.76)]
    with capture_app(monkeypatch, scripts) as app:
        ids, slow = app.factory.camera_ids, app.factory.camera_ids[2]
        app.detect()
        app.apply_all()
        wait_ready_at(app, ids[:2], 30)
        app.wait_state(slow, "failed")  # also slow at 30: it is "applied again" at 60
        response = app.apply_all(framerate=60.0)
        failure = response.json()["camera_failures"][slow]
        assert failure["stage"] == "rate check" and failure["reason"].startswith("declared 30.00 fps"), failure
        assert [item["camera_ids"] for item in response_items(response)] == [[slow]]
        wait_ready_at(app, ids[:2], 30)
        assert app.state(slow) == "failed"
        assert [opens(app, camera_id) for camera_id in ids] == [3, 3, 3]


def test_t_req_35_a_new_group_at_60_falls_back(monkeypatch):
    """T-REQ-35, 2.4: a new group connects at 60 in `MANUAL -7`; one fake delivers 29.66 at 60. The group runs at 30;
    the response has `rate_fallback`."""
    scripts = [FakeScript(modes=MODES), FakeScript(modes=MODES, rate=SLOW)]
    with capture_app(monkeypatch, scripts) as app:
        ids = app.factory.camera_ids
        app.detect()
        response = app.apply_all(framerate=60.0)
        assert response.json()["camera_failures"] == {}, response.text
        assert all(config["framerate"] == 30.0 for config in response.json()["camera_configs"].values())
        assert [item["camera_ids"] for item in response_items(response)] == [[ids[1]]]
        wait_ready_at(app, ids, 30)


def test_t_req_36_no_rate_change_during_a_take(monkeypatch, tmp_path):
    """T-REQ-36, 2.7 [F4, D36]: a recording runs at 30; apply 60. 409; nothing reopens."""
    with capture_app(monkeypatch, [FakeScript(modes=MODES) for _ in range(2)]) as app:
        ready_app_steps(app)
        ids = app.factory.camera_ids
        assert app.record_start(tmp_path).status_code == 200
        refused = app.apply([app.config(camera_id, framerate=60.0) for camera_id in ids])
        assert refused.status_code == 409, refused.text
        assert [opens(app, camera_id) for camera_id in ids] == [1, 1]
        assert app.record_stop().status_code == 200


def test_t_req_37_no_rate_change_while_a_camera_adjusts(monkeypatch):
    """T-REQ-37, 2.7 [agent 45]: a camera is `adjusting`; apply 60. 409; the detail names the camera and
    `adjusting`."""
    with capture_app(monkeypatch, [FakeScript(modes=MODES, brightness=MODEL, hold_first_change=True)]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([auto(app, camera_id)]).status_code == 200
        assert app.state(camera_id) == "adjusting"
        refused = app.apply([auto(app, camera_id, framerate=60.0)])
        assert refused.status_code == 409 and f"camera {camera_id} is adjusting" in refused.text, refused.text
        app.factory.sources[camera_id].release()
        app.wait_state(camera_id, "ready")
        assert opens(app, camera_id) == 1


def test_t_req_41_auto_searches_at_60_before_its_check(monkeypatch):
    """T-REQ-41, 2.3 [G1, H1]: a fake in `AUTO` held at -7 found at 30 delivers 60 at -7 and 30 at each other value;
    apply 60. The apply answers with the camera `adjusting` at 60; the search gives -7, found at 60; the check passes;
    the camera is `ready` at 60."""
    others = tuple((value, 30.0) for value in range(-12, -4) if value != -7)
    script = FakeScript(modes=MODES, brightness=MODEL, rate_by_exposure=others + ((-7, 60.0),), hold_first_change=True)
    with capture_app(monkeypatch, [script]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([auto(app, camera_id, exposure=-7, exposure_found_at_fps=30.0)]).status_code == 200
        wait_ready_at(app, [camera_id], 30)
        response = app.apply([auto(app, camera_id, framerate=60.0)])
        assert response.status_code == 200 and app.state(camera_id) == "adjusting", response.text
        assert response.json()["camera_configs"][camera_id]["framerate"] == 60.0
        wait_ready_at(app, [camera_id], 60)
        held = group_state(app)["configs"][camera_id]
        assert (held["exposure"], held["exposure_found_at_fps"]) == (-7, 60.0)
        assert not fallback_items(app, camera_id)


def test_t_req_84_a_search_on_request_at_60_gives_no_fall_back(monkeypatch):
    """T-REQ-84, 2.4a item 5: a fake in `AUTO` is `ready` at 60; then it delivers 29.66 fps after each later set; press
    the button. The search fails with `no-value-kept-rate`; no fall back: the camera stays at 60 with no new open, and
    no status has a `rate_fallback` item."""
    script = FakeScript(modes=MODES, brightness=MODEL, rate_after_change=(60.0,) * 9 + (SLOW,) * 8)
    with capture_app(monkeypatch, [script]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([auto(app, camera_id, framerate=60.0)]).status_code == 200
        wait_ready_at(app, [camera_id], 60)
        response = press(app)
        assert response.status_code == 200, response.text
        assert response.json()["results"][camera_id]["reason"] == "no-value-kept-rate", response.text
        app.wait_state(camera_id, "too_slow")
        time.sleep(0.5)  # five rounds of the watch of the group (WATCH_INTERVAL_S)
        assert opens(app, camera_id) == 1 and rate(app, camera_id) == 60
        assert app.state(camera_id) == "too_slow" and not fallback_items(app, camera_id)


def test_t_req_85_the_cameras_that_the_request_does_not_name_fall_back_too(monkeypatch):
    """T-REQ-85, 2.4a item 2: A and B run at 60; C (29.66 fps) was unselected and is selected again by a request that
    names only C, at 60. One fall back: A, B and C run at 30 and are `ready`; only C has a `rate_fallback` item."""
    scripts = [FakeScript(modes=MODES), FakeScript(modes=MODES), FakeScript(modes=MODES, rate=SLOW)]
    with capture_app(monkeypatch, scripts) as app:
        ready_app_steps(app)
        a, b, c = app.factory.camera_ids
        assert app.apply([app.config(c, use_this_camera=False)]).status_code == 200
        assert app.apply([app.config(a, framerate=60.0), app.config(b, framerate=60.0)]).status_code == 200
        wait_ready_at(app, [a, b], 60)
        response = app.apply([app.config(c, framerate=60.0)])
        assert response.status_code == 200 and response.json()["camera_failures"] == {}, response.text
        assert [item["camera_ids"] for item in response_items(response)] == [[c]]
        wait_ready_at(app, [a, b, c], 30)
        assert not fallback_items(app, a) and not fallback_items(app, b) and len(fallback_items(app, c)) == 1


def test_t_req_86_a_failure_at_set_mode_falls_back_with_its_own_text(monkeypatch):
    """T-REQ-86, 2.4a item 4: the detection lists 60 fps, but the source has 30 fps only; connect at 60. The apply
    answers with the config at 30 and the text of a camera with no measured rate; the camera is `ready`."""
    script = FakeScript(modes=((640, 480, 30, 1, "MJPG"),), detected_modes=MODES)
    with capture_app(monkeypatch, [script]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        response = app.apply([app.config(camera_id, framerate=60.0)])
        body = response.json()
        assert response.status_code == 200 and body["camera_failures"] == {}, response.text
        assert body["camera_configs"][camera_id]["framerate"] == 30.0
        assert [item["text"] for item in response_items(response)] == [
            f"The group runs at 30 fps. Camera {camera_id} could not set its 60 fps mode."]
        wait_ready_at(app, [camera_id], 30)
