import contextlib
import logging
import os
import sys
from dataclasses import dataclass
from collections.abc import Callable

import cv2
from pydantic import BaseModel

from skellycam.core.camera.capture import warning_pipe
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
) -> None:
    """The target of each camera process (section 3): the shared loop with the chosen source."""
    logger.trace(f"Camera {camera_id} worker started")
    cv2.setNumThreads(1)  # ring 8.2, with or without a BGR ring (ADR-467Z item 3)
    limit_libjpeg_warnings()  # ring 8.9; on Windows the main process gives the pipe (5.6)
    status = orchestrator.camera_statuses[camera_id]
    try:
        with media_foundation_process(source_factory is None and select_capture_source() == "media_foundation"):
            camera_loop(source_factory or create_capture_source, config, ipc, orchestrator, update_camera_settings_subscription, shm_subscription,
                        recording_info_subscription)
    finally:
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
            ),
        )
        worker.protect_recording(status.recording_in_progress)
        return cls(
            camera_id=camera_id,
            ipc=ipc,
            orchestrator=orchestrator,
            worker=worker,
        )

    def start(self) -> None:
        self.orchestrator.camera_statuses[self.camera_id].set_state("starting")
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
