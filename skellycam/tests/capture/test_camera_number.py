"""The camera number of a take on the server side (`specs/camera-requests.md` 8.1 [G7, H6]).

The UI sends the camera number (`camera_index`) and the name of the current detection with each apply
request. The server keeps them, also for a change that is live or that fails, and refuses an apply
that gives two selected cameras of the group the same number (HTTP 422). Fake sources on the virtual
clock; no real camera. T-REQ-61 (the take order) is in `skellycam/tests/take_recorder/test_connection.py`.
"""

from skellycam.tests.capture.capture_session import capture_app, ready_app_steps
from skellycam.tests.capture.fake_source import FakeScript


def numbers(response):
    return {cid: (config["camera_index"], config["camera_name"])
            for cid, config in response.json()["camera_configs"].items()}


def test_a_number_only_change_is_live_with_no_reopen(monkeypatch):
    """A changed number and name only: HTTP 200, the response holds the new values, and no camera opens
    again (`needs_reopen` ignores the number)."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        a, b = app.factory.camera_ids
        ready_app_steps(app, [app.config(a, camera_index=0), app.config(b, camera_index=1)])
        opens = {cid: app.factory.logs[cid].opens.value for cid in (a, b)}
        response = app.apply([app.config(a, camera_index=5, camera_name="New A")])
        assert response.status_code == 200, response.text
        assert numbers(response)[a] == (5, "New A")
        assert app.group.configs[a].camera_index == 5
        assert {cid: app.factory.logs[cid].opens.value for cid in (a, b)} == opens


def test_two_equal_numbers_in_one_request_get_422_and_no_kill_flag(monkeypatch):
    """The first apply gives both cameras the number 0: HTTP 422 with a text that names both cameras. The
    global kill flag stays off, and no group starts."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        a, b = app.factory.camera_ids
        app.detect()
        response = app.apply([app.config(a, camera_index=0), app.config(b, camera_index=0)])
        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert f"camera {a}" in detail and f"camera {b}" in detail and "camera number 0" in detail, detail
        assert not app.kill.value
        assert app.group_or_none() is None


def test_a_partial_apply_that_repeats_the_number_of_an_unnamed_camera_gets_422(monkeypatch):
    """The group holds A with 1 and B with 0. A request that names only B with 1 gets HTTP 422: A keeps
    its number 1. The group configs do not change."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        a, b = app.factory.camera_ids
        ready_app_steps(app, [app.config(a, camera_index=1), app.config(b, camera_index=0)])
        response = app.apply([app.config(b, camera_index=1)])
        assert response.status_code == 422, response.text
        assert f"camera {a}" in response.json()["detail"] and f"camera {b}" in response.json()["detail"]
        assert (app.group.configs[a].camera_index, app.group.configs[b].camera_index) == (1, 0)


def test_a_swap_of_two_numbers_in_one_apply_is_accepted(monkeypatch):
    """The group holds A with 0 and B with 1. One request gives A 1 and B 0: HTTP 200, and the group
    holds the swapped numbers."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        a, b = app.factory.camera_ids
        ready_app_steps(app, [app.config(a, camera_index=0), app.config(b, camera_index=1)])
        response = app.apply([app.config(a, camera_index=1), app.config(b, camera_index=0)])
        assert response.status_code == 200, response.text
        assert (numbers(response)[a][0], numbers(response)[b][0]) == (1, 0)
        assert (app.group.configs[a].camera_index, app.group.configs[b].camera_index) == (1, 0)


def test_a_failed_live_exposure_change_keeps_the_number_and_name_of_the_request(monkeypatch):
    """A request with a new number, a new name and a live exposure change that the fake refuses: the
    exposure stays -7 (T-CAP-90), and the config holds the number and the name of the request."""
    with capture_app(monkeypatch, [FakeScript(live_set_faults=("error",)), FakeScript()]) as app:
        a, b = app.factory.camera_ids
        ready_app_steps(app, [app.config(a, camera_index=0), app.config(b, camera_index=1)])
        response = app.apply([app.config(a, camera_index=4, camera_name="New A", exposure=-5)])
        assert response.status_code == 200, response.text
        assert [w["camera_ids"] for w in response.json()["warnings"] if w["kind"] == "control_change_failed"] == [[a]]
        assert response.json()["camera_configs"][a]["exposure"] == -7
        assert numbers(response)[a] == (4, "New A")
        assert (app.group.configs[a].camera_index, app.group.configs[a].camera_name) == (4, "New A")
