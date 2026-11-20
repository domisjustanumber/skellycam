"""The shutdown save protection: a camera with an open take writer delays the forced end of its process
(`ManagedWorker.protect_recording`, `wait_for_recording_save`). Two tests come back from the test file that
the connection commit deleted with the old writer (review item 13); the third checks the time limit of the
wait (ADR-P5VE)."""

import logging
import multiprocessing
import threading
import time
from unittest.mock import Mock, patch

from skellycam.core.camera.camera_worker import CameraWorker
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.ipc.process_management import managed_worker
from skellycam.core.ipc.process_management.managed_worker import ManagedWorker, WorkerMode
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes
from skellycam.core.types.type_overloads import TopicSubscriptionQueue


def test_server_shutdown_waits_for_video_saves():
    application_stop = multiprocessing.Value("b", False)
    registry = WorkerRegistry(global_kill_flag=application_stop, worker_mode=WorkerMode.THREAD)
    worker = Mock()
    worker.pid = None
    worker.is_alive.return_value = False
    waiting = threading.Event()
    finished = threading.Event()

    def finish_save():
        waiting.set()
        assert finished.wait(10), "Test did not release finalization"

    worker.wait_for_recording_save.side_effect = finish_save
    registry._workers.append(worker)
    with patch("skellycam.core.ipc.process_management.worker_registry.os.kill") as terminate_server:
        registry.start_heartbeat()
        try:
            application_stop.value = True
            assert waiting.wait(5)
            terminate_server.assert_not_called()
            finished.set()
            deadline = time.monotonic() + 5
            while not terminate_server.called and time.monotonic() < deadline:
                time.sleep(0.005)
            terminate_server.assert_called_once()
        finally:
            finished.set()
            registry.shutdown_all()


def test_camera_worker_registers_save_protection():
    status = CameraStatus()
    orchestrator = CameraOrchestrator.from_statuses({"camera": status})
    ipc = Mock(spec=CameraGroupIPC)
    ipc.pubsub = Mock()
    ipc.pubsub.topics = {TopicTypes.LOGS: Mock()}
    ipc.shutdown_camera_group_flag = multiprocessing.Value("b", False)
    registry = Mock(spec=WorkerRegistry)
    registry.worker_mode = WorkerMode.PROCESS
    worker = Mock(spec=ManagedWorker)
    registry.create_worker.return_value = worker
    queue = Mock(spec=TopicSubscriptionQueue)
    CameraWorker.create(
        camera_id="camera", ipc=ipc, worker_registry=registry,
        config=CameraConfig(camera_id="camera", camera_index=0), orchestrator=orchestrator,
        update_camera_settings_subscription=queue, shm_subscription=queue,
        recording_info_subscription=queue,
    )
    worker.protect_recording.assert_called_once_with(status.recording_in_progress)
    assert registry.create_worker.call_args.kwargs["daemon"] is False


class StuckOnItsDisk(ManagedWorker):
    """A camera process that stays alive with its recording flag set, as one stuck on its disk."""

    def start(self): ...
    def is_alive(self): return True
    def join(self, timeout=None): time.sleep(timeout or 0)
    @property
    def pid(self): return 1
    @property
    def exitcode(self): return None
    def terminate(self): ...
    def kill(self): ...


def test_the_wait_for_a_recording_save_has_a_time_limit(monkeypatch, caplog):
    """A camera stuck on its disk does not hang the exit of the app: the wait ends at its limit, with an
    error log line."""
    monkeypatch.setattr(managed_worker, "RECORDING_SAVE_LIMIT_S", 0.3)
    flag = multiprocessing.Value("b", True)
    worker = StuckOnItsDisk(name="stuck", shutdown_flag=multiprocessing.Value("b", False))
    worker.protect_recording(flag)
    started = time.monotonic()
    with caplog.at_level(logging.ERROR):
        worker.wait_for_recording_save()
    assert 0.3 <= time.monotonic() - started < 5.0
    assert any("stuck" in record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR)
