"""Camera shutdown must not depend on acknowledgements from dead workers."""

import asyncio
import logging
import multiprocessing
import time
from unittest.mock import Mock, call

import pytest

from skellycam.core.camera.camera_manager import CameraManager
from skellycam.core.camera.camera_worker import CameraWorker
from skellycam.core.camera_group.camera_group import CameraGroup
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
import skellycam.core.camera_group.camera_orchestrator as orchestrator_module
from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.ipc.process_management.managed_worker import ManagedWorker
from skellycam.core.ipc.pubsub.pubsub_manager import PubSubTopicManager
from skellycam.core.ipc.frame_ring import FrameRingCreator, FrameRingReader
from skellycam.core.types.type_overloads import TopicSubscriptionQueue


@pytest.fixture
def manager(monkeypatch):
    # Register the app's logging vocabulary without creating log files/handlers.
    for name in ("trace", "success"):
        monkeypatch.setattr(logging.Logger, name, logging.Logger.debug, raising=False)
    queue = Mock(spec=TopicSubscriptionQueue)
    ipc = CameraGroupIPC(
        group_id="shutdown-test",
        pubsub=Mock(spec=PubSubTopicManager),
        extracted_config_subscription=queue,
        recording_finished_subscription=queue,
        diagnostics_subscription=multiprocessing.Queue(),  # a Mock never reports empty: the close reads this queue
        global_kill_flag=multiprocessing.Value("b", False),
        heartbeat_timestamp=multiprocessing.Value("d", time.perf_counter()),
    )
    statuses = {name: CameraStatus() for name in ("camera1", "camera2")}
    for status in statuses.values():
        status.connected.value = True
        status.set_state("ready")  # a running camera of the shared loop (spec 8.1)
    return CameraManager(
        ipc=ipc,
        orchestrator=CameraOrchestrator.from_statuses(statuses),
        camera_workers={},
    )


@pytest.mark.parametrize("paused", [True, False], ids=["pause", "resume"])
@pytest.mark.parametrize("failure", ["error", "closed"])
async def test_state_change_aborts_on_camera_failure(manager, monkeypatch, paused, failure):
    for status in manager.orchestrator.camera_statuses.values():
        status.is_paused.value = not paused

    async def camera_dies_during_wait():
        getattr(manager.orchestrator.camera_statuses["camera2"], failure).value = True
        await asyncio.sleep(0)

    monkeypatch.setattr(orchestrator_module, "await_10ms", camera_dies_during_wait)
    action = manager.pause(True) if paused else manager.unpause(True)
    with pytest.raises(RuntimeError, match="cameras failed or closed.*camera2"):
        await asyncio.wait_for(action, timeout=1)
    assert manager.ipc.shutdown_camera_group_flag.value
    assert not manager.ipc.global_kill_flag.value
    assert all(s.should_close.value for s in manager.orchestrator.camera_statuses.values())


@pytest.mark.parametrize("paused", [True, False], ids=["pause", "resume"])
async def test_state_change_timeout_stops_group(manager, monkeypatch, paused):
    for status in manager.orchestrator.camera_statuses.values():
        status.is_paused.value = not paused
    monkeypatch.setattr(orchestrator_module, "CAMERA_STATE_TIMEOUT_SECONDS", 0.0)
    action = manager.pause(True) if paused else manager.unpause(True)
    with pytest.raises(TimeoutError, match="Timed out waiting for cameras"):
        await asyncio.wait_for(action, timeout=1)
    assert manager.ipc.shutdown_camera_group_flag.value
    assert not manager.ipc.global_kill_flag.value


@pytest.mark.parametrize("paused", [True, False], ids=["pause", "resume"])
async def test_state_change_completes_when_cameras_acknowledge(manager, monkeypatch, paused):
    for status in manager.orchestrator.camera_statuses.values():
        status.is_paused.value = not paused

    async def acknowledge():
        for status in manager.orchestrator.camera_statuses.values():
            status.is_paused.value = bool(status.should_pause.value)

    monkeypatch.setattr(orchestrator_module, "await_10ms", acknowledge)
    action = manager.pause(True) if paused else manager.unpause(True)
    await asyncio.wait_for(action, timeout=1)
    assert manager.ipc.should_continue
    assert all(bool(s.is_paused.value) == paused for s in manager.orchestrator.camera_statuses.values())


@pytest.mark.parametrize("outcome", ["already-dead", "kill-needed", "unkillable", "not-started"])
def test_close_reaches_worker_shutdown_despite_stale_status(manager, monkeypatch, outcome):
    def forbidden_status_wait():
        pytest.fail("Shutdown waited for a dead camera to acknowledge closure")

    # Fail promptly if the old unbounded status wait is reintroduced.
    monkeypatch.setattr(orchestrator_module, "wait_100ms", forbidden_status_wait, raising=False)
    worker = Mock(spec=ManagedWorker)
    worker.pid = None if outcome == "not-started" else 123
    worker.is_alive.return_value = outcome in ("kill-needed", "unkillable")
    if outcome == "kill-needed":
        def killed():
            worker.is_alive.return_value = False
        worker.kill.side_effect = killed
    manager.camera_workers["camera1"] = CameraWorker(
        camera_id="camera1", worker=worker, ipc=manager.ipc,
        orchestrator=manager.orchestrator,
    )
    # Deliberately leave closed=False: an abrupt exit cannot update it.
    if outcome == "unkillable":
        with pytest.raises(RuntimeError, match="could not be killed"):
            manager.close()
        assert manager.camera_workers
    else:
        manager.close()
        assert not manager.camera_workers
        assert all(s.closed.value for s in manager.orchestrator.camera_statuses.values())
        group = CameraGroup(ipc=manager.ipc, configs={}, cameras=manager)
        assert not group.alive
        assert not group.to_state().alive
    assert manager.ipc.shutdown_camera_group_flag.value
    worker.mark_stopping.assert_called_once()
    if outcome in ("kill-needed", "unkillable"):
        worker.terminate.assert_called_once()
        worker.kill.assert_called_once()
        assert worker.join.call_args_list == [call(timeout=3.0), call(timeout=3.0), call(timeout=2.0)]
    else:
        worker.terminate.assert_not_called()
        worker.kill.assert_not_called()
        assert worker.join.call_count == int(outcome == "already-dead")


async def test_group_close_after_recording_failure_releases_shared_memory(manager):
    manager.ipc.should_continue = False
    status = manager.orchestrator.camera_statuses["camera1"]
    status.recording_in_progress.value = True
    status.signal_error()
    ring, reader = Mock(spec=FrameRingCreator), Mock(spec=FrameRingReader)
    group = CameraGroup(ipc=manager.ipc, configs={}, cameras=manager,
                        rings={"camera1": ring}, ring_readers={"camera1": reader})
    await asyncio.wait_for(group.close(), timeout=1)
    ring.set_closed.assert_called_once()
    reader.close.assert_called_once()
    ring.close_and_unlink.assert_called_once()
    assert status.error.value
    assert not manager.ipc.global_kill_flag.value


@pytest.mark.parametrize("paused", [False, True])
def test_stopped_group_is_not_reported_alive_with_lingering_workers(manager, paused):
    worker = Mock(spec=CameraWorker)
    worker.is_alive.return_value = True
    worker.to_state.return_value = {
        "pid": 123, "name": "lingering-camera", "alive": True, "status": {},
    }
    manager.camera_workers["camera1"] = worker
    for status in manager.orchestrator.camera_statuses.values():
        status.should_pause.value = paused
        status.is_paused.value = paused
    group = CameraGroup(ipc=manager.ipc, configs={}, cameras=manager)
    assert group.alive
    assert group.to_state().alive
    manager.ipc.should_continue = False
    assert not group.alive
    assert not group.to_state().alive


class SlowSpawnWorker:
    """A fake camera worker whose start takes 0.2 s, as the spawn stagger on Windows."""

    def __init__(self):
        self.started = False
        self.worker = Mock(spec=ManagedWorker, pid=None)
        self.worker.is_alive.return_value = False

    def start(self):
        time.sleep(0.2)
        self.started = True


async def test_a_close_during_the_spawn_waits_for_it_and_no_camera_starts_after_it(manager):
    """Fix lane A: the close waits for the spawn loop (no "dictionary changed size during iteration", no orphan),
    and the spawn loop stops at the close."""
    workers = {f"camera{number}": SlowSpawnWorker() for number in range(4)}
    manager.camera_workers.update(workers)
    group = CameraGroup(ipc=manager.ipc, configs={}, cameras=manager)
    spawn = asyncio.create_task(asyncio.to_thread(group._spawn, manager.start))
    await asyncio.sleep(0.3)  # the second camera starts
    await asyncio.wait_for(group.close(), timeout=5)
    await asyncio.wait_for(spawn, timeout=1)  # no error
    assert 1 <= sum(worker.started for worker in workers.values()) < 4
    assert not manager.camera_workers


async def test_two_closes_at_once_close_the_camera_processes_one_time(manager):
    """Fix lane A: a second close waits for the first, then returns."""
    worker = Mock(spec=ManagedWorker, pid=123)
    worker.is_alive.return_value = False
    worker.join.side_effect = lambda timeout: time.sleep(0.2)
    manager.camera_workers["camera1"] = CameraWorker(camera_id="camera1", worker=worker, ipc=manager.ipc,
                                                     orchestrator=manager.orchestrator)
    group = CameraGroup(ipc=manager.ipc, configs={}, cameras=manager)
    await asyncio.wait_for(asyncio.gather(group.close(), group.close()), timeout=5)
    worker.mark_stopping.assert_called_once()
    assert not manager.camera_workers


def test_a_restart_after_an_unselect_joins_the_old_process_first(manager, monkeypatch):
    """Fix lane I: "apply again" of an unselected camera joins its old process (and kills it when it still runs)
    before `reset_for_start` clears the stop flag; else an old loop could go on."""
    from skellycam.core.ipc.process_management.managed_worker import ManagedProcess

    old = Mock(spec=ManagedProcess)
    status = manager.orchestrator.camera_statuses["camera1"]
    flags_at_join = []
    old.join.side_effect = lambda timeout: flags_at_join.append(bool(status.should_close.value))
    old.is_alive.return_value = True
    manager.camera_workers["camera1"] = CameraWorker(camera_id="camera1", worker=old, ipc=manager.ipc,
                                                     orchestrator=manager.orchestrator)
    manager.remove_camera("camera1")
    new = Mock(spec=CameraWorker)
    monkeypatch.setattr(manager, "_create_worker", lambda camera_id, config: new)
    from skellycam.core.camera.config.camera_config import CameraConfig

    manager.restart_camera("camera1", CameraConfig(camera_id="camera1", camera_index=0))
    assert flags_at_join == [True, True, True]  # the join of the unselect, then the restart: join, kill, join
    old.kill.assert_called_once()
    new.start.assert_called_once()
    assert not status.should_close.value and "camera1" not in manager.removed_workers


async def test_the_end_of_a_take_waits_at_most_its_bound_for_the_lock_of_the_last_frame(manager, monkeypatch):
    """unix-capture.md 4.10: another holder keeps the lock of the last frame (as a camera process killed inside
    its locked read). The end of the take does not block the event loop: after FRAME_LOCK_WAIT_S it ends the take as
    an error with that reason."""
    import threading

    from skellycam.core.camera_group import camera_group as group_module

    group = CameraGroup(ipc=manager.ipc, configs={}, cameras=manager)
    from skellycam.core.take_recorder import TakeSummary

    take = Mock(rec="take")
    group.take, group.recording_ids = take, ["camera1"]
    take.finish.return_value = TakeSummary(stop_response={}, results=[], warnings=[])
    monkeypatch.setattr(group, "_collect_results", lambda: ({}, {}, set()))
    held, release = threading.Event(), threading.Event()

    def hold():
        with manager.orchestrator.last_recording_frame_number.get_lock():
            held.set()
            release.wait(10)

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    try:
        assert held.wait(5)
        await asyncio.wait_for(group._end_take(), timeout=group_module.FRAME_LOCK_WAIT_S + 2.0)
    finally:
        release.set()
        holder.join(5)
    error = take.finish.call_args.kwargs["ended_by_error"]
    assert error == f"no lock of the last frame of the take in {group_module.FRAME_LOCK_WAIT_S:g} s"
    assert group.take is None
