"""Requests at the shutdown of the server (specs/recorder.md 9.1 items 7 and 8, Q935).

A record start that comes while the close of the groups runs gets 409, not 500. An apply, an exposure search or a
detection that the 5 s limit of uvicorn cancels leaves nothing after the close of the lifespan end: no group, no
camera worker, no frame ring that a reader can attach. THREAD workers on the virtual clock, fake sources (as
`test_take_end_cancel.py`); the cancel is made on the event loop of the app, as uvicorn makes it.
"""

import asyncio
import threading
import time

import pytest

from skellycam.tests.capture.capture_session import capture_app, ready_app_steps
from skellycam.tests.capture.fake_source import FakeScript
from skellycam.tests.capture.test_camera_requests import MODEL
from skellycam.tests.take_recorder.test_connection import group_module
from skellycam.tests.take_recorder.test_take_end_cancel import _cancel_when, _close_as_the_lifespan


def test_a_record_start_during_the_close_of_the_groups_gets_409(monkeypatch, tmp_path):
    """The background close of `/shutdown` runs (here: its close of the cameras is slow); a record start comes. The
    answer is 409 with the refusal text of 9.1 item 7, and no take folder is made."""
    module = group_module()
    closing = threading.Event()
    close_cameras = module.CameraGroup._close_cameras

    def slow_close_cameras(group):
        closing.set()
        time.sleep(1.5)
        return close_cameras(group)

    monkeypatch.setattr(module.CameraGroup, "_close_cameras", slow_close_cameras)
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        ready_app_steps(app)
        close = app.client.portal.start_task_soon(app.manager.close_all_camera_groups)
        assert closing.wait(30), "the close did not reach the cameras"
        response = app.record_start(tmp_path)
        close.result(60)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "The cameras close: no recording starts", response.text
    assert not (tmp_path / "take").exists()


def _nothing_left(app, names):
    """After the close of the lifespan end: no group, no live camera worker, no ring that a reader can attach."""
    from skellycam.core.ipc.frame_ring import FrameRingReader

    app.wait(lambda: not app.registry.alive_workers, "each camera worker ended", timeout=30)
    attachable = []
    for name in names:
        try:
            reader = FrameRingReader.attach(name)
        except Exception:
            continue
        attachable.append(name)
        reader.close()
    return {"groups": list(app.manager.camera_groups), "rings": attachable}


@pytest.mark.parametrize("workers", [
    "process",
    pytest.param("thread", marks=pytest.mark.xfail(strict=True, raises=RuntimeError, reason=(
        "9.1 item 8: a close of a group whose start loop stopped early joins a THREAD worker that never started "
        "(`ManagedThread.join` has no guard; `ManagedProcess.join` has one). A question for the user."))),
])
def test_a_cancelled_apply_leaves_nothing_after_the_close(monkeypatch, workers):
    """An apply that the limit cancels while the group starts its camera workers (the start loop waits between two
    workers, as the 0.25 s step of camera processes on Windows), then the close of the lifespan end. The close stops
    the start loop; the camera worker that did not start is not joined."""
    from skellycam.core.camera.camera_worker import CameraWorker

    starting = threading.Event()
    start = CameraWorker.start

    def slow_start(worker):
        starting.set()
        time.sleep(0.5)  # in the start loop, under the life lock of the group
        return start(worker)

    monkeypatch.setattr(CameraWorker, "start", slow_start)
    with capture_app(monkeypatch, [FakeScript(), FakeScript()], workers=workers) as app:
        app.detect()
        configs = {cid: app.config(cid) for cid in app.factory.camera_ids}
        ended = app.client.portal.call(_cancel_when, lambda: app.manager.create_or_update_camera_group(configs),
                                       starting.is_set)
        names = [name for group in app.manager.camera_groups.values() for info in group.ring_infos.values()
                 for name in (info.jpeg_ring_name, info.bgr_ring_name) if name]
        _close_as_the_lifespan(app)
        left = _nothing_left(app, names)
    assert ended == "cancelled"
    assert left == {"groups": [], "rings": []}, left


def test_a_cancelled_exposure_search_leaves_nothing_after_the_close(monkeypatch):
    """An exposure search that the limit cancels while the cameras search, then the close of the lifespan end. The
    search flag of the manager is clear."""
    with capture_app(monkeypatch, [FakeScript(brightness=MODEL), FakeScript(brightness=MODEL)]) as app:
        ready_app_steps(app)
        group = app.group
        names = [name for info in group.ring_infos.values() for name in (info.jpeg_ring_name, info.bgr_ring_name)
                 if name]
        module, searching_loop = group_module(), threading.Event()

        async def slow_wait():  # the wait of the search loop of the group: the cancel lands in it
            searching_loop.set()
            await asyncio.sleep(0.05)

        monkeypatch.setattr(module, "await_10ms", slow_wait)
        ended = app.client.portal.call(_cancel_when, app.manager.search_exposure, searching_loop.is_set)
        searching = app.manager.searching
        _close_as_the_lifespan(app)
        left = _nothing_left(app, names)
    assert ended == "cancelled"
    assert (searching, left) == (False, {"groups": [], "rings": []}), (searching, left)


def test_a_cancelled_detection_leaves_nothing_after_the_close(monkeypatch):
    """A detection that the limit cancels in its thread, then the close of the lifespan end: no group starts later."""
    import skellycam.core.camera_group.camera_group_manager as manager_module

    detecting = threading.Event()
    with capture_app(monkeypatch, [FakeScript()]) as app:
        fake_detect = manager_module.detect_available_cameras

        def slow_detect(*args, **kwargs):
            detecting.set()
            time.sleep(1.0)
            return fake_detect(*args, **kwargs)

        monkeypatch.setattr(manager_module, "detect_available_cameras", slow_detect)
        configs = {cid: app.config(cid) for cid in app.factory.camera_ids}
        ended = app.client.portal.call(_cancel_when, lambda: app.manager.create_or_update_camera_group(configs),
                                       detecting.is_set)
        _close_as_the_lifespan(app)
        time.sleep(1.5)  # the detection thread ends; nothing may start a group after it
        left = _nothing_left(app, [])
    assert ended == "cancelled"
    assert left == {"groups": [], "rings": []}, left
