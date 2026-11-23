"""Part 2 of specs/camera-requests.md (one frame rate and the fall back to 30 fps): the tests T-REQ of step 4 with
the fake sources (2.4, 2.4a, 2.10).

Each test runs THREAD workers with the virtual clock of `capture_session`. The fixture `no_camera_auto_exposure`
of `conftest.py` is the spy of T-REQ-15 here too.
"""

import asyncio
import re
import sys
import threading

from skellycam.core.camera_group.camera_group import CameraGroup
from skellycam.tests.capture.capture_session import capture_app, capture_logs, ready_app_steps
from skellycam.tests.capture.fake_source import FakeScript
from skellycam.tests.capture.test_camera_requests import MODEL, auto, group_state, press

MODES = ((640, 480, 30, 1, "MJPG"), (640, 480, 60, 1, "MJPG"))
SLOW = 29.66  # the Kiyo Pro in its 60 fps mode (2.4); not slow at 30 fps, where the limit is 29.1
REQUEST_RUNS = "Another change of the cameras runs now. Send the request again when the cameras are ready."
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


class WatchGate:
    """Holds the rounds of the fall back watch of each group (`CameraGroup._watch_fall_back`) until `open_and_settle`.
    It records each fall back that a round starts: the watch thread calls `_fall_back_after_search` itself."""

    def __init__(self, monkeypatch):
        self.go, self.started, self.done, self.rounds = threading.Event(), threading.Event(), threading.Event(), 0
        watch, after = CameraGroup._watch_fall_back, CameraGroup._fall_back_after_search

        def gated(group):
            if self.go.is_set():
                watch(group)
                self.rounds += 1

        def tracked(group, *args):
            self.started.set()

            async def run():
                try:
                    await after(group, *args)
                finally:
                    self.done.set()
            return run()

        monkeypatch.setattr(CameraGroup, "_watch_fall_back", gated)
        monkeypatch.setattr(CameraGroup, "_fall_back_after_search", tracked)

    def open_and_settle(self, app):
        """Let the watch make two full rounds; then wait for the end of each fall back that a round started."""
        self.go.set()
        first = self.rounds
        app.wait(lambda: self.rounds >= first + 2, "two rounds of the fall back watch")
        if self.started.is_set():
            app.wait(self.done.is_set, "the end of the fall back that the watch started")


def on_loop(app, coroutine):
    """Run a coroutine on the event loop of the group (the loop of the test client) and give its result."""
    return asyncio.run_coroutine_threadsafe(coroutine, app.group._loop).result(timeout=60)


def at_30(app):
    return {camera_id: config.model_copy(update=dict(framerate=30.0)) for camera_id, config in app.group.configs.items()}


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
        app.wait_state(slow, "failed")  # also slow at 30: it is "applied again" at 60 (its retry list [Z7F3])
        response = app.apply([app.config(cid, framerate=60.0) for cid in ids], retry=[slow])
        assert response.status_code == 200, response.text
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
    no status has a `rate_fallback` item. The watch makes no round until the search ended, so the watch is still armed
    by the request at 60 when the button is pressed, at each thread timing: only the button stops it."""
    script = FakeScript(modes=MODES, brightness=MODEL, rate_after_change=(60.0,) * 9 + (SLOW,) * 8)
    gate = WatchGate(monkeypatch)
    with capture_app(monkeypatch, [script]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([auto(app, camera_id, framerate=60.0)]).status_code == 200
        wait_ready_at(app, [camera_id], 60)
        response = press(app)
        assert response.status_code == 200, response.text
        assert response.json()["results"][camera_id]["reason"] == "no-value-kept-rate", response.text
        app.wait_state(camera_id, "too_slow")
        gate.open_and_settle(app)
        assert not gate.started.is_set() and opens(app, camera_id) == 1 and rate(app, camera_id) == 60
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


def test_t_req_91_no_fall_back_during_a_take(monkeypatch, tmp_path):
    """T-REQ-91, 2.4a item 9: the search at 60 keeps no value, but the check passes (`ready`), so a take can start. The
    watch makes no round until the take runs. The take keeps running at 60 with no new open and no `rate_fallback`
    item; a call of `fall_back` during the take does nothing and logs why; the record start cleared the watch."""
    script = FakeScript(modes=MODES, brightness=MODEL, rate_after_change=(SLOW,) * 8 + (60.0,) * 20)
    gate = WatchGate(monkeypatch)
    with capture_logs() as logs, capture_app(monkeypatch, [script]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([app.config(camera_id)]).status_code == 200
        wait_ready_at(app, [camera_id], 30)
        assert app.apply([auto(app, camera_id, framerate=60.0)]).status_code == 200
        app.wait(lambda: app.state(camera_id) in ("ready", "too_slow"), "the search and the check at 60")
        assert app.state(camera_id) == "ready"
        assert app.status(camera_id)["exposure_search"]["reason"] == "no-value-kept-rate"
        assert app.record_start(tmp_path).status_code == 200
        assert app.group.fall_back_armed is None
        gate.open_and_settle(app)
        assert on_loop(app, app.group.fall_back(at_30(app), {camera_id: (SLOW, -7, 60.0)})) == ({}, [])
        assert app.group.take is not None and opens(app, camera_id) == 2 and rate(app, camera_id) == 60
        assert not fallback_items(app, camera_id)
        assert any("does not run during a take" in message for message in logs.messages()), logs.messages()
        assert app.record_stop().status_code == 200


def test_t_req_92_a_request_of_the_user_replaces_a_waiting_fall_back(monkeypatch):
    """T-REQ-92, 2.4a item 7: the fall back that the search at 60 starts waits on the event loop until a request of the
    user (`MANUAL -9` at 30) has answered. The fall back then does not run (the log tells why); the camera runs the
    request of the user; no status has a `rate_fallback` item."""
    entered, user_done, finished = threading.Event(), threading.Event(), threading.Event()
    after = CameraGroup._fall_back_after_search

    def held_back(group, *args):
        entered.set()

        async def run():
            while not user_done.is_set():
                await asyncio.sleep(0.01)
            try:
                await after(group, *args)
            finally:
                finished.set()
        return run()

    monkeypatch.setattr(CameraGroup, "_fall_back_after_search", held_back)
    with capture_logs() as logs, capture_app(monkeypatch, [FakeScript(modes=MODES, brightness=MODEL, rate=SLOW)]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([auto(app, camera_id)]).status_code == 200
        wait_ready_at(app, [camera_id], 30)
        assert app.apply([auto(app, camera_id, framerate=60.0)]).status_code == 200
        app.wait(entered.is_set, "the watch starts the fall back")
        response = app.apply([app.config(camera_id, exposure_mode="MANUAL", exposure=-9)])
        assert response.status_code == 200, response.text
        user_done.set()
        app.wait(finished.is_set, "the waiting fall back ends")
        wait_ready_at(app, [camera_id], 30)
        config = group_state(app)["configs"][camera_id]
        assert (config["exposure_mode"], config["exposure"], config["framerate"]) == ("MANUAL", -9, 30.0)
        assert not fallback_items(app, camera_id)
        assert any("a later request of the user replaced" in message for message in logs.messages()), logs.messages()


def test_t_req_93_no_request_of_the_user_while_a_fall_back_runs(monkeypatch):
    """T-REQ-93, 2.4a item 7 and 1.5: the apply of the fall back waits until a request of the user (`MANUAL -9` at 30)
    has answered. That request gets 409 with the reason of 2.4a; the camera then runs the configs of the fall back, with
    its `rate_fallback` item; a new request of the user clears the item."""
    entered, user_done = threading.Event(), threading.Event()
    apply = CameraGroup.apply

    async def held_apply(group, requested, retry=()):
        frame = sys._getframe()
        while frame is not None and frame.f_code.co_name != "fall_back":
            frame = frame.f_back
        if frame is not None:  # the apply of the fall back
            entered.set()
            while not user_done.is_set():
                await asyncio.sleep(0.01)
        return await apply(group, requested, retry)

    monkeypatch.setattr(CameraGroup, "apply", held_apply)
    with capture_app(monkeypatch, [FakeScript(modes=MODES, brightness=MODEL, rate=SLOW)]) as app:
        camera_id = app.factory.camera_ids[0]
        app.detect()
        assert app.apply([auto(app, camera_id)]).status_code == 200
        wait_ready_at(app, [camera_id], 30)
        assert app.apply([auto(app, camera_id, framerate=60.0)]).status_code == 200
        app.wait(entered.is_set, "the fall back runs its apply")
        refused = app.apply([app.config(camera_id, exposure_mode="MANUAL", exposure=-9)])
        user_done.set()
        assert refused.status_code == 409, refused.text
        assert REQUEST_RUNS in refused.text
        wait_ready_at(app, [camera_id], 30)
        assert group_state(app)["configs"][camera_id]["exposure_mode"] == "AUTO"
        assert len(fallback_items(app, camera_id)) == 1
        assert app.apply([auto(app, camera_id)]).status_code == 200
        assert not fallback_items(app, camera_id)


def test_t_req_94_the_texts_of_the_fall_back(monkeypatch):
    """T-REQ-94, 2.4a item 4: the text of a search with no measured rate, of a `set mode` failure, of a camera whose
    mode rate at the failure was 60 while it now runs at 30, and of a measured rate with no exposure value."""
    with capture_app(monkeypatch, [FakeScript(modes=MODES)]) as app:
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        texts = [on_loop(app, app.group.fall_back(at_30(app), {camera_id: facts}))[1][0]["text"]
                 for facts in ((None, -7, 60.0), (None, None, None), (SLOW, -7, 60.0), (SLOW, None, 60.0))]
        assert texts == [f"The group runs at 30 fps. Camera {camera_id} found no exposure that keeps 60 fps.",
                         f"The group runs at 30 fps. Camera {camera_id} could not set its 60 fps mode.",
                         f"The group runs at 30 fps. Camera {camera_id} measured 29.66 fps in its 60 fps mode at "
                         f"exposure -7.",
                         f"The group runs at 30 fps. Camera {camera_id} measured 29.66 fps in its 60 fps mode."]
        assert opens(app, camera_id) == 1  # the configs did not change: no reopen


def test_t_req_96_no_second_change_while_a_request_runs(monkeypatch):
    """T-REQ-96, 2.4a item 7: the apply of a request at 60 waits after it returned (B failed at 60). During the wait, a
    request at 30 with -9, the button and "Search again" get 409 with the reason of 2.4a. Then the first request falls
    back: both cameras run at 30 with -7, and B has one `rate_fallback` item."""
    held_now, user_done = threading.Event(), threading.Event()
    apply = CameraGroup.apply

    async def held(group, requested, retry=()):
        result = await apply(group, requested, retry)
        if any(abs(config.framerate - 60) <= 0.5 for config in requested.values()):
            held_now.set()
            while not user_done.is_set():
                await asyncio.sleep(0.01)
        return result

    monkeypatch.setattr(CameraGroup, "apply", held)
    with capture_app(monkeypatch, [FakeScript(modes=MODES), FakeScript(modes=MODES, rate=SLOW)]) as app:
        ready_app_steps(app)
        a, b = app.factory.camera_ids
        first = {}
        thread = threading.Thread(target=lambda: first.setdefault("response", app.apply_all(framerate=60.0)))
        thread.start()
        try:
            app.wait(held_now.is_set, "the apply at 60 returned")
            refused = [app.apply([app.config(camera_id, exposure=-9) for camera_id in (a, b)]), press(app), press(app, [a])]
        finally:
            user_done.set()
            thread.join(60)
        assert [response.status_code for response in refused] == [409, 409, 409], [r.text for r in refused]
        assert all(REQUEST_RUNS in response.text for response in refused), [r.text for r in refused]
        assert [item["camera_ids"] for item in response_items(first["response"])] == [[b]]
        wait_ready_at(app, [a, b], 30)
        configs = group_state(app)["configs"]
        assert [configs[camera_id]["exposure"] for camera_id in (a, b)] == [-7, -7]
        assert len(fallback_items(app, b)) == 1


def test_t_req_97_no_request_for_a_failed_camera_while_the_others_start(monkeypatch):
    """T-REQ-97, 2.4a item 7: the reopen of A at 60 waits in its open, so B fails at 60 while A is `starting`. A request
    for B alone at 30 with -9 gets 409. After the release of A, the first request falls back: A and B run at 30 and are
    `ready`; no camera is `dead`."""
    scripts = [FakeScript(modes=MODES, hold_opens=(2,)), FakeScript(modes=MODES, rate=SLOW)]
    with capture_app(monkeypatch, scripts) as app:
        ready_app_steps(app)
        a, b = app.factory.camera_ids
        first = {}
        thread = threading.Thread(target=lambda: first.setdefault("response", app.apply_all(framerate=60.0)))
        thread.start()
        try:
            app.wait(lambda: app.state(b) == "failed" and app.state(a) == "starting", "B failed at 60 while A starts")
            refused = app.apply([app.config(b, framerate=30.0, exposure=-9)])
        finally:
            app.factory.sources[a].release()
            thread.join(60)
        assert refused.status_code == 409 and REQUEST_RUNS in refused.text, refused.text
        assert first["response"].status_code == 200, first["response"].text
        wait_ready_at(app, [a, b], 30)
        assert not any(app.state(camera_id) == "dead" for camera_id in (a, b))
