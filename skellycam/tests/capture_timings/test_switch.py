"""The switch `log_capture_times`: T-TIM-04, T-TIM-07, T-TIM-08 (group part) and T-TIM-20 (specs/capture-timings.md 2).

The app tests run the real manager, router and camera loops with THREAD workers and the virtual clock of the
fake sources (`capture_session.capture_app`). No camera.
"""

import pytest

from skellycam.tests.capture.capture_session import capture_app, ready_app_steps
from skellycam.tests.capture.fake_source import FakeScript
from skellycam.tests.capture_timings.loop_harness import loop_module

OFF_BODY = {"version": 1, "log_capture_times": False, "summaries": []}


@pytest.fixture()
def sent(monkeypatch):
    """Each `DiagnosticsMessage` that a camera loop makes, in order."""
    from skellycam.core.ipc.pubsub.pubsub_topics import DiagnosticsMessage

    messages = []

    def recording(**fields):
        message = DiagnosticsMessage(**fields)
        messages.append(message)
        return message

    monkeypatch.setattr(loop_module(), "DiagnosticsMessage", recording)
    return messages


def statuses(app):
    return list(app.group.cameras.orchestrator.camera_statuses.values())


def test_t_tim_04_the_switch_is_off_by_default(monkeypatch):
    """T-TIM-04: a new manager has `log_capture_times` False; each status of a new group has False; `reset_for_start`
    keeps the value; `capture_timings()` gives `log_capture_times` false and `summaries` []."""
    from skellycam.core.camera_group.camera_status import CameraStatus

    status = CameraStatus()
    assert not status.log_capture_times.value
    status.log_capture_times.value = True
    status.reset_for_start()
    assert status.log_capture_times.value
    with capture_app(monkeypatch, [FakeScript()]) as app:
        assert app.manager.log_capture_times is False
        assert app.manager.capture_timings() == OFF_BODY
        ready_app_steps(app)
        assert all(not status.log_capture_times.value for status in statuses(app))
        app.wait_clock(2.5)
        assert app.manager.capture_timings() == OFF_BODY


def test_t_tim_07_a_change_while_the_cameras_run(monkeypatch, sent):
    """T-TIM-07: on, then off, then on, through `set_log_capture_times`; the summaries start and stop at the next
    publish of each camera; the main process drops its summaries at once at off; the fake source opens one time."""
    with capture_app(monkeypatch, [FakeScript()]) as app:
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        manager = app.manager

        manager.set_log_capture_times(True)
        assert manager.log_capture_times is True and all(status.log_capture_times.value for status in statuses(app))
        count = len(sent)
        app.wait(lambda: any(m.timings is not None for m in sent[count:]), "a summary after the change to on")
        first = next(i for i in range(count, len(sent)) if sent[i].timings is not None)
        assert sent[first - 1].timings is None  # the publish that applied the change started the window
        app.wait(lambda: manager.capture_timings()["summaries"], "a summary in the main process")
        body = manager.capture_timings()
        assert body["log_capture_times"] is True and [s["camera_id"] for s in body["summaries"]] == [camera_id]

        manager.set_log_capture_times(False)
        assert manager.capture_timings() == OFF_BODY  # at once
        count = len(sent)
        app.wait(lambda: len(sent) > count + 2, "two publishes after the change to off")
        assert all(m.timings is None for m in sent[count + 1:])
        assert manager.capture_timings() == OFF_BODY

        manager.set_log_capture_times(True)
        count = len(sent)
        app.wait(lambda: any(m.timings is not None for m in sent[count:]), "a summary after the change to on again")
        seqs = [m.timings["seq"] for m in sent if m.timings is not None]
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
        assert app.factory.logs[camera_id].opens.value == 1


def test_t_tim_08_a_group_made_after_a_change_to_on_starts_on(monkeypatch, sent):
    """T-TIM-08 (group part): a group made after a change to on starts on: its statuses hold True, and the publish at
    the end of the open carries a summary. `capture_timings()` gives it with the id of the group."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        app.manager.set_log_capture_times(True)
        ready_app_steps(app)
        assert all(status.log_capture_times.value for status in statuses(app))
        app.wait(lambda: len(app.manager.capture_timings()["summaries"]) == 2, "a summary of each camera")
        for camera_id in app.factory.camera_ids:
            first = next(m for m in sent if m.camera_id == camera_id)
            assert first.timings is not None and first.timings["seq"] == 0
        body = app.manager.capture_timings()
        assert {s["camera_group_id"] for s in body["summaries"]} == {app.group.id}
        assert {s["camera_id"] for s in body["summaries"]} == set(app.factory.camera_ids)


def test_t_tim_20_the_route(monkeypatch):
    """T-TIM-20: `POST /camera/timings` sets the switch and answers its value; a body with no boolean gets 422."""
    with capture_app(monkeypatch, [FakeScript()]) as app:
        response = app.client.post("/skellycam/camera/timings", json={"log_capture_times": True})
        assert response.status_code == 200 and response.json() == {"log_capture_times": True}
        assert app.manager.log_capture_times is True
        for body in ({}, {"log_capture_times": "yes"}, {"log_capture_times": None}, {"other": True}):
            assert app.client.post("/skellycam/camera/timings", json=body).status_code == 422, body
        assert app.manager.log_capture_times is True
        response = app.client.post("/skellycam/camera/timings", json={"log_capture_times": False})
        assert response.status_code == 200 and response.json() == {"log_capture_times": False}
        assert app.manager.log_capture_times is False
