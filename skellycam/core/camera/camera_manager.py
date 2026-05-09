import logging
import sys
import time
from dataclasses import dataclass
from skellycam.core.camera.camera_worker import CameraWorker, CameraState
from skellycam.core.camera.config.camera_config import CameraConfigs
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes
from skellycam.core.types.type_overloads import CameraIdString

logger = logging.getLogger(__name__)


@dataclass
class CameraManager:
    ipc: CameraGroupIPC
    orchestrator: CameraOrchestrator
    camera_workers: dict[CameraIdString, CameraWorker]

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
    ) -> "CameraManager":
        logger.info(f"Starting camera manager process with {len(camera_configs)} cameras")

        camera_statuses: dict[CameraIdString, CameraStatus] = {
            camera_id: CameraStatus() for camera_id in camera_configs.keys()
        }
        orchestrator = CameraOrchestrator.from_statuses(camera_statuses=camera_statuses)

        camera_workers = {
            camera_id: CameraWorker.create(
                camera_id=camera_id,
                ipc=ipc,
                worker_registry=worker_registry,
                orchestrator=orchestrator,
                config=camera_config,
                update_camera_settings_subscription=ipc.pubsub.topics[
                    TopicTypes.UPDATE_CAMERA_SETTINGS
                ].get_subscription(),
                shm_subscription=ipc.pubsub.topics[
                    TopicTypes.SHM_UPDATES
                ].get_subscription(),
                recording_info_subscription=ipc.pubsub.topics[
                    TopicTypes.RECORDING_INFO
                ].get_subscription(),
            )
            for camera_id, camera_config in camera_configs.items()
        }

        return cls(
            ipc=ipc,
            camera_workers=camera_workers,
            orchestrator=orchestrator,
        )

    def start(self) -> None:
        """Start every worker in ``camera_index`` order with optional stagger.

        :class:`CameraGroup` uses sequential startup instead (one worker at a time until extracted config).
        This method remains for callers that own a :class:`CameraManager` directly.
        """
        logger.info("Starting camera processes...")
        # On Windows, multiprocessing.spawn causes each child process to
        # re-import the full module tree. Spawning many children simultaneously
        # creates a file-locking race (PermissionError) because Windows holds
        # brief exclusive locks during file reads, and antivirus real-time
        # scanning amplifies the contention. Staggering spawns lets each child
        # finish its import phase before the next one starts.
        # Multiple USB devices opening in parallel often starve the later index;
        # start lower indices first and use a slightly longer gap when several cameras run.
        n = len(self.camera_workers)
        if sys.platform == "win32":
            # Spawning + USB open contention: give each prior camera time to claim bandwidth before the next worker runs.
            stagger_s = 1.0 if n > 1 else 0.25
        elif n > 1:
            stagger_s = 0.25
        else:
            stagger_s = 0.0

        ordered = sorted(self.camera_workers.values(), key=lambda w: w.config.camera_index)
        for worker in ordered:
            if stagger_s > 0:
                time.sleep(stagger_s)
            worker.start()

    async def pause_unpause(self, await_state: bool = True) -> None:
        if self.orchestrator.any_cameras_paused:
            await self.unpause(await_unpaused=await_state)
        else:
            await self.pause(await_paused=await_state)

    async def pause(self, await_paused: bool) -> None:
        await self.orchestrator.pause(await_paused=await_paused)

    async def unpause(self, await_unpaused: bool) -> None:
        await self.orchestrator.unpause(await_unpaused=await_unpaused)

    def close(self) -> None:
        logger.info("Closing camera manager and all camera processes...")
        self.ipc.should_continue = False

        # Before workers observe should_close and exit, mark intentional shutdown so the child
        # monitor never treats a fast non-zero exit as a fatal crash (would set global_kill_flag).
        for camera_worker in self.camera_workers.values():
            camera_worker.worker._intentionally_terminated = True

        self.orchestrator.close()

        # Phase 1: Wait for all processes to exit on their own (parallel)
        for camera_worker in self.camera_workers.values():
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

        self.camera_workers.clear()
        logger.success("Camera manager closed all camera processes successfully.")

    def to_state(self) -> dict[CameraIdString, CameraState]:
        return {
            camera_id: self.camera_workers[camera_id].to_state()
            for camera_id in self.camera_workers
        }
