import contextlib
import logging
import multiprocessing
import os
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from collections.abc import Callable

import cv2
from pydantic import BaseModel

from skellycam.core.camera.capture import restore_store as restore_store_module, source, warning_pipe
from skellycam.core.camera.capture.camera_loop import camera_loop
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
from skellycam.core.ipc.frame_ring import limit_libjpeg_warnings
from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes
from skellycam.core.ipc.process_management.managed_worker import ManagedProcess, ManagedWorker
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
from skellycam.core.types.type_overloads import CameraIdString, TopicSubscriptionQueue

logger = logging.getLogger(__name__)

CAPTURE_SOURCES = ("opencv", "media_foundation")
# unix-capture.md 4.12 [HQE5]: the reason of the code `start-method-fork`.
START_METHOD_REASON = ("the host program must call multiprocessing.set_start_method('spawn') before it creates a "
                       "multiprocessing object")


def start_method() -> str:
    """The start method that a camera process gets now (4.12): the method of the default context."""
    return multiprocessing.get_start_method()


def select_capture_source() -> str:
    """The source on Windows while phase 3 is built (14.2, D8): `SKELLYCAM_WINDOWS_CAPTURE`, default `opencv`.

    Other systems always use OpenCV (14.1).
    """
    if sys.platform != "win32":
        return "opencv"
    value = os.environ.get("SKELLYCAM_WINDOWS_CAPTURE") or "opencv"
    if value not in CAPTURE_SOURCES:
        raise ValueError(f"SKELLYCAM_WINDOWS_CAPTURE must be one of {', '.join(CAPTURE_SOURCES)}, not {value!r}")
    return value


def create_capture_source(config: CameraConfig):
    """The source of 14.2 when the group has no `source_factory` (ADR-HP7D item 10)."""
    if select_capture_source() == "media_foundation":
        # Windows only, and it can load comtypes (U18): import it only when it is chosen.
        from skellycam.core.camera.capture.media_foundation.source import MediaFoundationSource
        return MediaFoundationSource()
    from skellycam.core.camera.capture.opencv_source import OpenCVSource
    return OpenCVSource(config)


@contextlib.contextmanager
def media_foundation_process(used: bool):
    """6.1: COM and Media Foundation start one time before the first call. They shut down only when no
    bounded call was abandoned; else the process ends hard (6.6)."""
    if not used:
        yield
        return
    from skellycam.core.camera.capture.media_foundation import bounded, com
    com.startup()
    try:
        yield
    finally:
        if bounded.abandoned() == 0:
            com.shutdown()


def camera_worker_method(
    camera_id: CameraIdString,
    config: CameraConfig,
    ipc: CameraGroupIPC,
    orchestrator: CameraOrchestrator,
    update_camera_settings_subscription: TopicSubscriptionQueue,
    shm_subscription: TopicSubscriptionQueue,
    recording_info_subscription: TopicSubscriptionQueue,
    source_factory: Callable | None = None,
    restore_store=None,
    restore_identity: dict | None = None,
) -> None:
    """The target of each camera process (section 3): the shared loop with the chosen source."""
    logger.trace(f"Camera {camera_id} worker started")
    cv2.setNumThreads(1)  # ring 8.2, with or without a BGR ring (ADR-467Z item 3)
    limit_libjpeg_warnings()  # ring 8.9; on Windows the main process gives the pipe (5.6)
    status = orchestrator.camera_statuses[camera_id]
    # unix-capture.md 4.7 [NYT6]: the restore record lives in the status, so it survives this process
    # 4.7.1 [HQE5]: each write of the record also writes the restore file of the camera (an empty record removes it)

    def set_restore_record(record: dict) -> None:
        status.set_restore_record(record)
        restore_store_module.write_entry(restore_store, restore_identity, record)

    keeper = SimpleNamespace(restore_record=status.restore_record, set_restore_record=set_restore_record)
    source.RESTORE_RECORDS[camera_id] = keeper
    try:
        with media_foundation_process(source_factory is None and select_capture_source() == "media_foundation"):
            camera_loop(source_factory or create_capture_source, config, ipc, orchestrator, update_camera_settings_subscription, shm_subscription,
                        recording_info_subscription)
    finally:
        if source.RESTORE_RECORDS.get(camera_id) is keeper:  # THREAD workers share the dict: not a later run's
            del source.RESTORE_RECORDS[camera_id]
        status.signal_closing()
        status.closed.value = True
        logger.debug(f"Camera {camera_id} process completed")


class CameraState(BaseModel):
    """Serializable representation of a camera process state."""
    pid: int
    name: str
    alive: bool
    status: dict
    error: str | None = None


@dataclass
class CameraWorker:
    camera_id: CameraIdString
    worker: ManagedWorker
    ipc: CameraGroupIPC
    orchestrator: CameraOrchestrator

    @classmethod
    def create(
        cls,
        *,
        camera_id: CameraIdString,
        ipc: CameraGroupIPC,
        worker_registry: WorkerRegistry,
        config: CameraConfig,
        orchestrator: CameraOrchestrator,
        update_camera_settings_subscription: TopicSubscriptionQueue,
        shm_subscription: TopicSubscriptionQueue,
        recording_info_subscription: TopicSubscriptionQueue,
        source_factory: Callable | None = None,
        restore_store=None,
        restore_identity: dict | None = None,
    ) -> "CameraWorker":
        status = orchestrator.camera_statuses[camera_id]
        worker = worker_registry.create_worker(
            # The flag of this camera only: a camera that fails or ends hard does not stop the group (D10, D23).
            shutdown_flag=status.should_close,
            worker_mode=worker_registry.worker_mode,
            daemon=False,  # Normal interpreter exit must wait for video finalization.
            target=camera_worker_method,
            name=f"Camera{config.camera_index}-{camera_id}-Worker",
            log_queue=ipc.pubsub.topics[TopicTypes.LOGS].publication,
            kwargs=dict(
                camera_id=camera_id,
                ipc=ipc,
                config=config,
                orchestrator=orchestrator,
                update_camera_settings_subscription=update_camera_settings_subscription,
                shm_subscription=shm_subscription,
                recording_info_subscription=recording_info_subscription,
                source_factory=source_factory,
                restore_store=restore_store,
                restore_identity=restore_identity,
            ),
        )
        worker.protect_recording(status.recording_in_progress, status.writer_progress_at)
        return cls(
            camera_id=camera_id,
            ipc=ipc,
            orchestrator=orchestrator,
            worker=worker,
        )

    def start(self) -> None:
        status = self.orchestrator.camera_statuses[self.camera_id]
        status.set_state("starting")
        if isinstance(self.worker, ManagedProcess) and start_method() == "fork":
            # unix-capture.md 4.12 [HQE5]: a forked camera process can deadlock at its start (a library of the main
            # process waits for threads that the fork did not copy); refuse it with the fix of the host.
            status.update_info(failure=dict(camera_id=self.camera_id, stage="open", reason=START_METHOD_REASON,
                                            code="start-method-fork"))
            status.set_state("failed")
            logger.error(f"Camera {self.camera_id} failed during open: {START_METHOD_REASON}")
            return
        on_windows = sys.platform == "win32" and isinstance(self.worker, ManagedProcess)
        with warning_pipe.child_stderr_pipe(self.camera_id) if on_windows else contextlib.nullcontext():
            self.worker.start()

    def is_alive(self) -> bool:
        return self.worker.is_alive()

    def join(self, timeout: float | None = None) -> None:
        self.worker.join(timeout=timeout)

    def to_state(self) -> CameraState:
        return CameraState(
            pid=self.worker.pid or -1,
            name=self.worker.name,
            alive=self.worker.is_alive(),
            status=self.orchestrator.camera_statuses[self.camera_id].serialize(),
        )
