"""CPU fakes prove the event-loop boundaries of a camera group without camera hardware.

Adapted from sfn26 (a4d610f62 and the bounded wait of 549217112) to the shared loop: the spawn and the close of
the camera processes run off the event loop, which serves the preview, and each wait of the parent for its camera
processes has a time limit.
"""
import asyncio
import queue
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from skellycam.core.camera.camera_manager import CameraManager
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera_group import camera_group as group_module
from skellycam.core.camera_group.camera_group import CameraGroup
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_setup_failure import CameraSetupFailedException
from skellycam.core.camera_group.camera_status import CameraStatus


@pytest.fixture
def group(monkeypatch):
    ipc = Mock(spec=CameraGroupIPC)
    ipc.group_id = "camera-startup"
    ipc.should_continue = True
    ipc.extracted_config_subscription = Mock(empty=Mock(return_value=True))
    ipc.diagnostics_subscription = queue.Queue()  # the close reads it (unix-capture.md 4.2 item 2)
    ipc.setup_failures = Mock()  # the close closes it (windows-capture.md 5.9)
    cameras = Mock(spec=CameraManager)
    cameras.camera_workers = {}
    cameras.orchestrator = SimpleNamespace(camera_statuses={})
    config = CameraConfig(camera_id="c1", camera_index=0)
    monkeypatch.setattr(group_module, "logger", Mock())
    monkeypatch.setattr(CameraGroup, "_watch_workers", lambda self: None)
    return CameraGroup(ipc=ipc, cameras=cameras, configs={config.camera_id: config})


async def run_while_blocked(blocking: Mock, call):
    """Run `call` while `blocking` waits on a thread; return the thread of `blocking` and whether the event loop
    ran other work meanwhile."""
    entered, release, threads = Event(), Event(), []

    def gate(*args, **kwargs):
        threads.append(get_ident())
        entered.set()
        assert release.wait(3)

    blocking.side_effect = gate
    task = asyncio.create_task(call())
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        await asyncio.wait_for(asyncio.sleep(0), timeout=0.1)  # the loop still serves other work
        responsive = not task.done()
    finally:
        release.set()
    return task, threads[0], responsive


async def test_the_spawn_of_the_camera_processes_runs_off_the_event_loop(group):
    async def start():
        return await group.start()

    task, thread, responsive = await run_while_blocked(group.cameras.start, start)
    group.ipc.running = False  # the start stops after the spawn: no ring is made (the main process reads `running`)
    with pytest.raises(CameraSetupFailedException):
        await task
    assert thread != get_ident() and responsive


async def test_the_close_of_the_camera_processes_runs_off_the_event_loop(group):
    task, thread, responsive = await run_while_blocked(group.cameras.close, group.close)
    await task
    assert thread != get_ident() and responsive
    group.cameras.close.assert_called_once()


def waiting_camera(group, state):
    status = CameraStatus()
    status.set_state(state)
    group.cameras.orchestrator.camera_statuses["c1"] = status
    group.cameras.camera_workers["c1"] = SimpleNamespace(worker=SimpleNamespace(exitcode=None))
    return status


async def test_the_config_wait_has_a_time_limit(group, monkeypatch):
    status = waiting_camera(group, "starting")
    monkeypatch.setattr(group_module, "PARENT_WAIT_LIMIT_S", 0.0)
    configs, _ = await asyncio.wait_for(group._await_results(["c1"]), timeout=2)
    assert configs == {}
    assert status.state == "failed" and status.should_close.value
    assert status.info_dict()["failure"]["stage"] == "open"
    assert "no answer" in status.info_dict()["failure"]["reason"]


async def test_the_wait_for_the_rate_check_has_a_time_limit(group, monkeypatch):
    status = waiting_camera(group, "starting")
    monkeypatch.setattr(group_module, "PARENT_WAIT_LIMIT_S", 0.0)
    await asyncio.wait_for(group._await_settled(["c1"]), timeout=2)
    assert status.state == "failed" and status.info_dict()["failure"]["stage"] == "warm-up"
