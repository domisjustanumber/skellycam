import logging
import sys
import time
from dataclasses import dataclass, field
from collections.abc import Callable

from skellycam.core.camera.camera_worker import CameraWorker, CameraState
from skellycam.core.camera.capture.source import BOUNDED_CALL_LIMIT_S
from skellycam.core.camera.config.camera_config import CameraConfig, CameraConfigs
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.ipc.process_management.managed_worker import ManagedProcess
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes
from skellycam.core.types.type_overloads import CameraIdString

logger = logging.getLogger(__name__)


@dataclass
class CameraManager:
    ipc: CameraGroupIPC
    orchestrator: CameraOrchestrator
    camera_workers: dict[CameraIdString, CameraWorker]
    worker_registry: WorkerRegistry | None = None
    source_factory: Callable | None = None
    # The status of an unselected camera. The other camera processes keep it, so a camera that is
    # selected again joins their gate with it (8.3).
    removed_statuses: dict[CameraIdString, CameraStatus] = field(default_factory=dict)

    @property
    def all_ready(self) -> bool:
        return self.orchestrator.all_ready

    @classmethod
    def create(
        cls,
        *,
        ipc: CameraGroupIPC,
        worker_registry: WorkerRegistry,
        camera_configs: CameraConfigs,
        source_factory: Callable | None = None,
    ) -> "CameraManager":
        logger.info(f"Starting camera manager process with {len(camera_configs)} cameras")

        camera_statuses: dict[CameraIdString, CameraStatus] = {
            camera_id: CameraStatus() for camera_id in camera_configs.keys()
        }
        orchestrator = CameraOrchestrator.from_statuses(camera_statuses=camera_statuses)

        manager = cls(ipc=ipc, camera_workers={}, orchestrator=orchestrator, worker_registry=worker_registry,
                      source_factory=source_factory)
        for camera_id, camera_config in camera_configs.items():
            manager.camera_workers[camera_id] = manager._create_worker(camera_id, camera_config)
        return manager

    def _create_worker(self, camera_id: CameraIdString, config: CameraConfig) -> CameraWorker:
        topics = self.ipc.pubsub.topics
        return CameraWorker.create(
            camera_id=camera_id,
            ipc=self.ipc,
            worker_registry=self.worker_registry,
            orchestrator=self.orchestrator,
            config=config,
            update_camera_settings_subscription=topics[TopicTypes.UPDATE_CAMERA_SETTINGS].get_subscription(),
            shm_subscription=topics[TopicTypes.SHM_UPDATES].get_subscription(),
            recording_info_subscription=topics[TopicTypes.RECORDING_INFO].get_subscription(),
            source_factory=self.source_factory,
        )

    def restart_camera(self, camera_id: CameraIdString, config: CameraConfig) -> None:
        """"Apply again" for a `failed` or `dead` camera, or a camera selected again after an unselect: a new
        camera process with the same status (8.2, 8.3, D23)."""
        if camera_id in self.removed_statuses:
            self.orchestrator.camera_statuses[camera_id] = self.removed_statuses.pop(camera_id)
        else:
            # After a hang, the old process finishes its files for at most 5 s (U12) and still holds the device.
            worker = self.camera_workers[camera_id].worker
            worker.join(timeout=2 * BOUNDED_CALL_LIMIT_S)
            if worker.is_alive() and isinstance(worker, ManagedProcess):
                worker.kill()
                worker.join(timeout=BOUNDED_CALL_LIMIT_S)
        self.orchestrator.camera_statuses[camera_id].reset_for_start()
        self.camera_workers[camera_id] = self._create_worker(camera_id, config)
        self.camera_workers[camera_id].start()

    def remove_camera(self, camera_id: CameraIdString) -> None:
        """Unselect (8.3, agent 24): close the camera and remove it from the gate and the record check."""
        status = self.orchestrator.camera_statuses[camera_id]
        status.should_close.value = True
        worker = self.camera_workers.pop(camera_id)
        worker.worker.mark_stopping()
        worker.join(timeout=2 * BOUNDED_CALL_LIMIT_S)
        status.set_state("failed")  # not in the gate of the other camera processes, which keep this status
        self.removed_statuses[camera_id] = self.orchestrator.camera_statuses.pop(camera_id)

    def start(self) -> None:
        logger.info("Starting camera processes...")
        # On Windows, multiprocessing.spawn causes each child process to
        # re-import the full module tree. Spawning many children simultaneously
        # creates a file-locking race (PermissionError) because Windows holds
        # brief exclusive locks during file reads, and antivirus real-time
        # scanning amplifies the contention. Staggering spawns lets each child
        # finish its import phase before the next one starts.
        _SPAWN_STAGGER_SECONDS: float = 0.25 if sys.platform == "win32" else 0.0

        for status in self.orchestrator.camera_statuses.values():
            status.set_state("starting")  # each camera, so that no camera joins the gate before the others start
        for worker in self.camera_workers.values():
            if isinstance(worker.worker, ManagedProcess):  # threads do not import again
                time.sleep(_SPAWN_STAGGER_SECONDS)
            worker.start()

    async def pause_unpause(self, await_state: bool = True) -> None:
        if self.orchestrator.any_cameras_paused:
            await self.unpause(await_unpaused=await_state)
        else:
            await self.pause(await_paused=await_state)

    async def pause(self, await_paused: bool) -> None:
        await self._set_paused(paused=True, await_state=await_paused)

    async def unpause(self, await_unpaused: bool) -> None:
        await self._set_paused(paused=False, await_state=await_unpaused)

    async def _set_paused(self, paused: bool, await_state: bool) -> None:
        try:
            if not self.ipc.should_continue:
                raise RuntimeError("Cannot change camera state: camera group has stopped.")
            if paused:
                await self.orchestrator.pause(await_paused=await_state)
            else:
                await self.orchestrator.unpause(await_unpaused=await_state)
            if not self.ipc.should_continue:
                raise RuntimeError("Camera group stopped while changing camera state.")
        except (RuntimeError, TimeoutError):
            self.ipc.should_continue = False
            self.orchestrator.close()
            raise

    def close(self) -> None:
        logger.info("Closing camera manager and all camera processes...")
        self.ipc.should_continue = False
        self.orchestrator.close()

        # Mark all workers as intentionally terminated before shutdown
        # so the child monitor doesn't trigger a cascade kill
        for camera_worker in self.camera_workers.values():
            camera_worker.worker.mark_stopping()

        for camera_worker in self.camera_workers.values():
            camera_worker.worker.wait_for_recording_save()

        # Phase 1: Wait for all processes to exit on their own (parallel)
        for camera_worker in self.camera_workers.values():
            if camera_worker.worker.pid is not None:
                camera_worker.worker.join(timeout=3.0)

        # Phase 2: SIGTERM any stragglers (parallel)
        still_alive = [w for w in self.camera_workers.values() if w.worker.is_alive()]
        if still_alive:
            logger.warning(
                f"{len(still_alive)} camera process(es) didn't exit in time, sending SIGTERM"
            )
            for camera_worker in still_alive:
                camera_worker.worker.terminate()
            for camera_worker in still_alive:
                camera_worker.worker.join(timeout=3.0)

        # Phase 3: SIGKILL any remaining (parallel)
        still_alive = [w for w in self.camera_workers.values() if w.worker.is_alive()]
        if still_alive:
            logger.error(
                f"{len(still_alive)} camera process(es) didn't respond to SIGTERM, sending SIGKILL"
            )
            for camera_worker in still_alive:
                camera_worker.worker.kill()
            for camera_worker in still_alive:
                camera_worker.worker.join(timeout=2.0)

        zombies = [w for w in self.camera_workers.values() if w.worker.is_alive()]
        if zombies:
            raise RuntimeError(
                f"{len(zombies)} camera process(es) could not be killed: "
                f"{[w.camera_id for w in zombies]}"
            )

        # A forcibly stopped or never-started worker cannot acknowledge closure.
        # Only update these flags after confirming that every worker has exited.
        for status in self.orchestrator.camera_statuses.values():
            status.signal_closing()
            status.closed.value = True
        self.camera_workers.clear()
        logger.success("Camera manager closed all camera processes successfully.")

    def to_state(self) -> dict[CameraIdString, CameraState]:
        return {
            camera_id: self.camera_workers[camera_id].to_state()
            for camera_id in self.camera_workers
        }
