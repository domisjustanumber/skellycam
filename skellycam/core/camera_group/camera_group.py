import asyncio
import logging
import os
import queue
import threading
import time
from fractions import Fraction
from pathlib import Path

from skellycam.core.camera_group.camera_setup_failure import CameraSetupFailedException
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, TypeAdapter

from skellycam import __version__
from skellycam.core import capture_timings
from skellycam.core.camera.camera_manager import CameraManager
from skellycam.core.camera.camera_worker import CameraState
from skellycam.core.camera.capture.failure_codes import WEDGE_CODES
from skellycam.core.camera.capture.source import COUNTER_KEYS
from skellycam.core.camera.capture.camera_loop import needs_reopen
from skellycam.core.camera.config.camera_config import CameraConfigs, CameraConfig, validate_camera_configs
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_orchestrator import FRAME_LOCK_WAIT_S
from skellycam.core.camera_group.camera_status import SETTLED_STATES
from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes, close_camera_group_pubsub_manager
from skellycam.core.ipc.pubsub.pubsub_topics import (
    DeviceExtractedConfigMessage,
    UpdateCamerasSettingsMessage,
    RecordingInfoMessage,
)
from skellycam.core.take_recorder import JpegLayout, Take, TakeCamera, TakeSummary, start_take
from skellycam.core.ipc.frame_ring import (
    CameraRingInfo,
    FrameRead,
    FrameRingCreator,
    FrameRingReader,
    ReadResult,
    camera_ring_info,
    create_session_rings,
    rotation_to_cw_deg,
    sweep_stale_rings,
)
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
from skellycam.core.recorders.videos.recording_info import RecordingInfo
from skellycam.core.types.frontend_payload_bytearray import (
    FRONTEND_FRAME_HEADER_DTYPE,
    FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE,
    MessageType,
)
from skellycam.core.types.type_overloads import (
    CameraIdString,
    CameraGroupIdString,
    FrameNumberInt,
    MultiframeTimestampFloat,
    SharedValue,
)
from skellycam.utilities.wait_functions import await_10ms

logger = logging.getLogger(__name__)

WATCH_INTERVAL_S = 0.1
BOUNDED_JOIN_S = 10.0  # the join of an ended or terminated camera process
GIVE_UP_AFTER_EXIT_S = 1.0  # the result message of an ended camera process can still be in the queue
TAKE_QUEUE_SECONDS = 3.0  # recorder.md 5.1; starting value [C6DE D2]
TAKE_STALL_LIMIT_S = 10.0  # recorder.md 5.3; starting value [C6DE D2]
STALL_MARGIN_S = 5.0  # recorder.md 5.3 item 4 [agent 25]
TAKE_START_LIMIT_S = 10.0  # each camera starts its writer within this time of the take spec
# The parent waits this long for a camera process at the start, as sfn26 549217112. The camera process has its own
# limit of 15 s (9.3); this one ends a wait on a camera process that does not answer at all.
PARENT_WAIT_LIMIT_S = 30.0
# The endpoint of the exposure search waits for its worst case (camera-requests.md 1.3b) [GEH0]: the limit of 20 s of a
# search, the last set (a bounded call of 5 s, 6.6) and one more set of the held value after a failed last set (5 s),
# with a margin of 5 s.
SEARCH_WAIT_LIMIT_S = 20.0 + 2 * 5.0 + 5.0
# The main-process stall watch (unix-capture.md 4.10): the states it watches, its limit, the wait before a kill.
WATCHED_STATES = ("waiting", "adjusting", "checking", "too_slow", "ready")
# camera-requests.md 1.3b [H1, AC5B]: the apply waits for a camera in AUTO until it is in one of these states.
AUTO_SETTLED_STATES = ("adjusting", "ready", "too_slow", "failed", "dead")
STALL_WATCH_S = 2.0  # the 2 s of the in-process rule (W 9.5) too (ADR-22EJ item 14, Q850)
# Q863, Q874 [ADR-3RJJ, ADR-EQ3K]: the last loop pass is never before the last arrival, so the in-process rule fires at
# most STALL_WATCH_S after it; this head start lets that rule set `dead` first, and the watch decides only a hang.
STALL_HEAD_START_S = 0.5
STALL_REASON = f"no loop pass for {STALL_WATCH_S + STALL_HEAD_START_S:g} s"
KILL_AFTER_S = 1.0
STALL_WATCH_SETTING = "SKELLYCAM_STALL_WATCH"  # "0" turns the watch off; read when a group is made
REQUEST_RUNS = "Another change of the cameras runs now. Send the request again when the cameras are ready."  # 2.4a 7
MICROPHONE_REFUSED = "audio recording returns in step 5b; start again with no microphone"  # recorder.md 10 item 13
WRITER = f"skellycam {__version__.lstrip('v')}"  # SFF-712


class RequestRefused(Exception):
    """A request that the whole-request check refuses (8.3): 422 by its content, 409 by the camera states."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


def same_config(requested: CameraConfig, current: CameraConfig) -> bool:
    """The same config in an apply request has no effect (8.3). "Auto" matches the mode rate (D17). The found rate,
    the number and the name are not compared; in `AUTO` the server holds the value (camera-requests.md 1.5)."""
    update = dict(exposure_found_at_fps=current.exposure_found_at_fps, camera_index=current.camera_index,
                  camera_name=current.camera_name)
    if requested.framerate in (-1, 0):
        update["framerate"] = current.framerate
    if requested.exposure_mode == "AUTO":
        update["exposure"] = current.exposure
    return requested.model_copy(update=update) == current


class CameraGroupState(BaseModel):
    """Serializable representation of a camera group state."""
    model_config = ConfigDict(
        validate_assignment=True,
        frozen=True,
    )
    id: CameraGroupIdString
    configs: dict[CameraIdString, CameraConfig]
    cameras: dict[CameraIdString, CameraState]
    alive: bool
    recording_in_progress: bool  # only for `take_state` "recording" (recorder.md 8.4)
    take_state: str = "none"  # "none", "recording" or "ended_with_error" (recorder.md 8.4)
    ended_take_summary: dict | None = None  # take_error, camera_id and summary while "ended_with_error"


@dataclass
class CameraGroup:
    ipc: CameraGroupIPC
    configs: CameraConfigs
    cameras: CameraManager
    rings: dict[CameraIdString, FrameRingCreator] = field(default_factory=dict)
    ring_infos: dict[CameraIdString, CameraRingInfo] = field(default_factory=dict)
    ring_readers: dict[CameraIdString, FrameRingReader] = field(default_factory=dict)
    started: bool = False
    recording_ids: list = field(default_factory=list)
    finished: list = field(default_factory=list)  # the result messages that the watch took from their queue
    take: Take | None = None  # the take that runs
    ended_take: TakeSummary | None = None  # a take that an error ended; the next stop request returns it
    ended_take_summary: dict | None = None  # the live state of that take (recorder.md 8.4)
    take_error: tuple | None = None  # (text, camera_id) of the first stall or write error of the take (5.3, 5.4)
    camera_diagnostics: dict = field(default_factory=dict)  # the newest diagnostics of each camera (unix 4.2 item 2)
    # capture-timings.md 6.2: camera_id: (newest summary, main-process clock at its receipt). The watch thread replaces
    # the whole dict at each change; a reader reads the attribute one time.
    camera_timings: dict = field(default_factory=dict)
    _passes: dict = field(default_factory=dict)  # camera_id: (alive_count, time.monotonic() of its last change)
    _adopted: dict = field(default_factory=dict)  # camera_id: the search count whose held value is in `configs`
    # (configs at 30 fps, search counts before the request, request count) after an apply request at 60 fps
    # (camera-requests.md 2.4a items 5 and 7)
    fall_back_armed: tuple | None = None
    request_count: int = 0  # one more at each apply request of the user (2.4a item 7)
    # A user apply with its start-up fall back, or a fall back, runs: an apply, a record start and a search get 409 (2.4a 7)
    request_runs: bool = False
    stall_watch: bool = True
    _closing: bool = False  # `close` runs: the watch thread reads the queues but watches no camera (F4)
    _end_lock: Any = field(default_factory=asyncio.Lock)
    _ring_lock: Any = field(default_factory=threading.RLock)
    _life_lock: Any = field(default_factory=threading.Lock)  # a spawn and a close of camera processes, one at a time
    _cameras_closed: bool = False
    _stop_watch: Any = field(default_factory=threading.Event)
    _watch_thread: Any = None  # the watch reads the queues; the close of the queues waits for its end (5.9)
    _loop: Any = None  # the event loop of `start`: a ring reader is closed only on it (ADR-BM73)

    @property
    def take_busy(self) -> bool:
        """A record start, a stop or an error end runs (it holds the lock of the take)."""
        return self._end_lock.locked()

    @property
    def id(self) -> CameraGroupIdString:
        return self.ipc.group_id

    @property
    def alive(self) -> bool:
        """The group runs and at least one selected camera lives: its process runs, and it is not `failed` or `dead`,
        not closing and not closed (camera-requests.md 1.5) [NYT6]."""
        statuses = self.cameras.orchestrator.camera_statuses
        return self.ipc.running and any(
            worker.is_alive() and (status := statuses.get(camera_id)) is not None
            and status.state not in ("failed", "dead") and not status.closed.value
            and not status.closing.value and not status.error.value
            for camera_id, worker in list(self.cameras.camera_workers.items()))

    @classmethod
    def create(
        cls,
        *,
        camera_configs: CameraConfigs,
        heartbeat_timestamp: SharedValue,
        global_kill_flag: SharedValue,
        worker_registry: WorkerRegistry,
        source_factory: Callable | None = None,
        restore_records: dict | None = None,
        restore_store=None,
        restore_identities: dict | None = None,
    ) -> "CameraGroup":
        try:
            validate_camera_configs(camera_configs)
            ipc = CameraGroupIPC.create(
                global_kill_flag=global_kill_flag,
                heartbeat_timestamp=heartbeat_timestamp,
            )

            cameras = CameraManager.create(
                ipc=ipc,
                worker_registry=worker_registry,
                camera_configs=camera_configs,
                source_factory=source_factory,
                restore_records=restore_records,
                restore_store=restore_store,
                restore_identities=restore_identities,
            )
        except Exception as e:
            logger.error(f"Error creating camera group: {type(e).__name__} - {e}")
            global_kill_flag.value = True
            raise

        return cls(
            ipc=ipc,
            cameras=cameras,
            configs=dict(camera_configs),
            stall_watch=os.environ.get(STALL_WATCH_SETTING) != "0",
        )

    async def start(self) -> dict:
        """Start each camera. Return the failure object of each camera that failed (8.4, section 12)."""
        self.started = True
        self._loop = asyncio.get_running_loop()
        if not self.stall_watch:
            logger.warning(f"The main-process stall watch is off ({STALL_WATCH_SETTING}=0)")
        logger.info(f"Starting camera group ID: {self.id} with cameras: {list(self.configs.keys())}")
        await asyncio.to_thread(self._spawn, self.cameras.start)  # seconds: not on the loop (sfn26 a4d610f62)
        self._watch_thread = threading.Thread(target=self._watch_workers, name=f"camera group {self.id} watch",
                                              daemon=True)
        self._watch_thread.start()
        configs, _ = await self._await_results(list(self.configs))
        if not self.ipc.running:
            raise CameraSetupFailedException("Camera group startup aborted")
        sweep_stale_rings()
        with self._ring_lock:
            self._open_rings(configs)
        self.configs.update(configs)
        await self._await_settled(list(self.configs))
        return self._failures(list(self.configs))

    async def apply(self, requested: CameraConfigs, retry=()) -> tuple[dict, list]:
        """Apply a checked request to each camera on its own (8.3, U10). Return the failures and the warnings.

        A `failed` or `dead` camera, or one whose process ended, starts again only when `retry` (the request's
        `retry_camera_ids`) names it; else the request leaves it as it is (8.3) [Z7F3].
        A camera that was unselected and is selected again starts again (8.3). Each other selected camera of
        the request that is not in the group is left out, as before phase 3: the other camera processes have
        no status for it, so it cannot join their gate. The warnings then have one `cameras_left_out` item.
        """
        statuses = self.cameras.orchestrator.camera_statuses
        restart, changed, removed, left_out, left = [], {}, [], [], []
        for camera_id, config in requested.items():
            if camera_id not in self.configs:
                if config.use_this_camera and camera_id in self.cameras.removed_statuses:
                    self.configs[camera_id] = config
                    restart.append(camera_id)
                elif config.use_this_camera:
                    left_out.append(camera_id)
                continue
            worker = self.cameras.camera_workers.get(camera_id)
            if not config.use_this_camera:
                removed.append(camera_id)
            elif (statuses[camera_id].state in ("failed", "dead") or worker is None
                  or worker.worker.exitcode is not None):
                if camera_id in retry:  # a live settings change never restarts a camera [Z7F3]
                    restart.append(camera_id)
                else:  # left alone; it keeps one rate with the group (the next retry sends its config)
                    left.append(camera_id)
                    self.configs[camera_id] = self.configs[camera_id].model_copy(update=dict(framerate=config.framerate))
            elif not same_config(config, self.configs[camera_id]):
                changed[camera_id] = config
            else:  # no effect on the camera; the number and the name of the request are kept (camera-requests.md 1.5)
                self.configs[camera_id] = self.configs[camera_id].model_copy(
                    update=dict(camera_index=config.camera_index, camera_name=config.camera_name))
        # The joins of a camera process take seconds: not on the event loop, which serves the preview.
        for camera_id in removed:
            await asyncio.to_thread(self._spawn, self.cameras.remove_camera, camera_id)
            with self._ring_lock:
                self._close_rings([camera_id])
            del self.configs[camera_id]
        for camera_id in restart:
            with self._ring_lock:
                self._close_rings([camera_id])
            await asyncio.to_thread(self._spawn, self.cameras.restart_camera, camera_id, requested[camera_id])
        if changed:
            self.ipc.pubsub.topics[TopicTypes.UPDATE_CAMERA_SETTINGS].publish(
                UpdateCamerasSettingsMessage(requested_configs=changed))
        reopened = restart + [camera_id for camera_id, config in changed.items()
                              if needs_reopen(config, self.configs[camera_id])]
        configs, warnings = await self._await_results(restart + list(changed))
        new_rings = {camera_id: config for camera_id, config in configs.items() if camera_id in reopened}
        with self._ring_lock:
            self._close_rings(list(new_rings))  # a new mode gets a new ring under a new name (ring 7.5)
            self._open_rings(new_rings)
        self.configs.update(configs)
        await self._await_settled(list(new_rings))
        if left_out:  # windows-capture.md 11.3
            text = (f"{'Camera' if len(left_out) == 1 else 'Cameras'} {', '.join(left_out)} cannot join a running "
                    f"group: close the cameras and open them again")
            warnings.append(dict(kind="cameras_left_out", camera_ids=left_out, text=text))
            logger.warning(text)
        if left:  # 8.3 [Z7F3]: the answer names each failed camera that the request did not open again
            text = (f"{'Camera' if len(left) == 1 else 'Cameras'} {', '.join(left)} failed and did not open again: "
                    f"name {'it' if len(left) == 1 else 'them'} in retry_camera_ids to open {'it' if len(left) == 1 else 'them'} again")
            warnings.append(dict(kind="camera_not_retried", camera_ids=left, text=text))
            logger.warning(text)
        logger.info(f"Applied camera configs - {list(requested.keys())}")
        return self._failures(reopened + left), warnings

    async def update_camera_settings(self, requested_configs: CameraConfigs) -> CameraConfigs:
        await self.apply(requested_configs)
        return self.configs

    async def _await_results(self, camera_ids: list) -> tuple[CameraConfigs, list]:
        """Wait until each camera published its config after the read-back (9.1 step 6), or failed."""
        pending, configs, warnings = set(camera_ids), {}, []
        statuses = self.cameras.orchestrator.camera_statuses
        subscription = self.ipc.extracted_config_subscription
        deadline = time.monotonic() + PARENT_WAIT_LIMIT_S
        while pending and self.ipc.running:
            if time.monotonic() >= deadline:
                self._give_up(pending, "open")
                break
            while not subscription.empty():
                message: DeviceExtractedConfigMessage = subscription.get()
                camera_id = message.extracted_config.camera_id
                if camera_id in pending:
                    pending.discard(camera_id)
                    configs[camera_id] = message.extracted_config
                    if message.control_change_failed:
                        warnings.append(dict(kind="control_change_failed", camera_ids=[camera_id],
                                             control="exposure", text=message.control_change_failed))
            for camera_id in list(pending):
                worker = self.cameras.camera_workers.get(camera_id)
                if worker is not None and worker.worker.exitcode is not None:
                    self._mark_ended(camera_id, worker)
                if worker is None or statuses[camera_id].state in ("failed", "dead"):
                    pending.discard(camera_id)
            await await_10ms()
        return configs, warnings

    async def _await_settled(self, camera_ids: list) -> None:
        """Wait until each camera has passed its rate check or failed (9.1, 10.1). A camera in `AUTO` waits until it
        is `adjusting` or later: the apply does not wait for the search (camera-requests.md 1.3b) [H1]."""
        statuses = self.cameras.orchestrator.camera_statuses
        deadline = time.monotonic() + PARENT_WAIT_LIMIT_S
        while self.ipc.running:
            for camera_id in camera_ids:
                worker = self.cameras.camera_workers.get(camera_id)
                if worker is not None and worker.worker.exitcode is not None:
                    self._mark_ended(camera_id, worker)
            pending = [camera_id for camera_id in camera_ids if camera_id in statuses
                       and statuses[camera_id].state not in (AUTO_SETTLED_STATES if camera_id in self.configs
                                                             and self.configs[camera_id].exposure_mode == "AUTO"
                                                             else SETTLED_STATES)]
            if not pending:
                return
            if time.monotonic() >= deadline:
                self._give_up(pending, "warm-up")
                return
            await await_10ms()

    def _spawn(self, call: Callable, *args) -> None:
        """A start, restart or unselect of camera processes, never during a close; none after a close."""
        with self._life_lock:
            if self.ipc.running:
                call(*args)

    def _close_cameras(self) -> None:
        """A second close waits for the first, then has nothing to do. A close that raised can run again."""
        with self._life_lock:
            if not self._cameras_closed:
                self.cameras.close()
                self._cameras_closed = True

    def _give_up(self, camera_ids, stage: str, limit_s: float = PARENT_WAIT_LIMIT_S) -> None:
        """A camera process that gives no answer within `limit_s` is `failed`, and it must close."""
        reason = f"no answer from the camera process in {limit_s:g} s"
        for camera_id in list(camera_ids):
            status = self.cameras.orchestrator.camera_statuses.get(camera_id)
            if status is None:
                continue
            status.should_close.value = True
            code = "open-failed" if stage == "open" else "not-ready"
            status.update_info(failure=dict(camera_id=camera_id, stage=stage, reason=reason, code=code))
            self._note_failure(camera_id, code)
            status.set_state("failed")
            logger.error(f"Camera {camera_id} failed during {stage}: {reason}")

    def _failures(self, camera_ids: list) -> dict:
        statuses = self.cameras.orchestrator.camera_statuses
        return {camera_id: statuses[camera_id].info_dict().get("failure") for camera_id in camera_ids
                if camera_id in statuses and statuses[camera_id].state in ("failed", "dead")
                and statuses[camera_id].info_dict().get("failure")}

    def _watch_workers(self) -> None:
        """6.6: the main process cleans up only the camera whose process ended: its state and rings (D10).

        It also reads the queues that the camera processes write, so that no write waits on a full pipe.
        An error in one step is logged, and the watch continues: else no later ended process is marked and
        no queue is read (ADR-BM73).
        """
        while not self._stop_watch.wait(WATCH_INTERVAL_S):
            try:
                while self.ipc.take_setup_failure() is not None:
                    pass  # the status of each camera holds its failure
                self._take_finished()
                self._take_diagnostics()
                self._watch_fall_back()
            except Exception as error:
                logger.exception(f"Camera group {self.id}: the watch could not read the camera queues: {error}")
            for camera_id, worker in list(self.cameras.camera_workers.items()):
                if self._closing:
                    break
                try:
                    self._watch_camera(camera_id, worker)
                except Exception as error:
                    logger.exception(f"Camera group {self.id}: the watch of camera {camera_id} failed: {error}")

    def _watch_camera(self, camera_id: CameraIdString, worker) -> None:
        if worker.worker.exitcode is None:
            self._watch_passes(camera_id, worker)
            return
        self._mark_ended(camera_id, worker)
        ring = self.rings.get(camera_id)
        if ring is not None:
            # The readers are read on the event loop (the relay), so they are closed there too (ADR-BM73).
            self._loop.call_soon_threadsafe(self._close_ended_ring, camera_id, ring)

    def _watch_passes(self, camera_id: CameraIdString, worker) -> None:
        """unix-capture.md 4.10: a live camera process whose loop made no pass for 2.5 s (2 s and the head start of
        the in-process rule) in a watched state, with no failure and no close, leaves the gate as `dead` with the code
        `stalled`, and its process ends."""
        status = self.cameras.orchestrator.camera_statuses.get(camera_id)
        if status is None:
            return
        # The counter has no lock: a process suspended or ended inside `alive_count += 1` kept it (review of 2026-11-20).
        count, now = status.alive_count.value, time.monotonic()
        watched = (self.stall_watch and status.state in WATCHED_STATES and not status.should_pause.value
                   and not status.should_close.value and not status.closing.value
                   and not status.info_dict().get("failure"))
        seen = self._passes.get(camera_id)
        if not watched or seen is None or seen[0] != count:
            self._passes[camera_id] = (count, now)
            return
        if now - seen[1] < STALL_WATCH_S + STALL_HEAD_START_S:
            return
        del self._passes[camera_id]
        status.should_close.value = True
        status.update_info(failure=dict(camera_id=camera_id, stage="streaming", reason=STALL_REASON, code="stalled"))
        self._note_failure(camera_id, "stalled")
        status.set_state("dead")  # out of the gate (5.2)
        logger.error(f"Camera {camera_id} failed during streaming: {STALL_REASON}")
        threading.Thread(target=self._end_process, args=(worker, status), name=f"end camera {camera_id}",
                         daemon=True).start()

    @staticmethod
    def _end_process(worker, status) -> None:
        """Terminate, then kill after 1 s (4.10). Off the watch thread, so the watch of the others goes on. As
        `_end_stuck_camera`: `terminate` waits for no save of a take, and the registry logs no crash."""
        status.recording_in_progress.value = False  # the take level completes its files after the end (7.4)
        worker.worker.mark_stopping()
        worker.worker.terminate()
        worker.join(timeout=KILL_AFTER_S)
        if worker.is_alive():
            worker.worker.kill()

    def _close_ended_ring(self, camera_id: CameraIdString, ring: FrameRingCreator) -> None:
        """On the event loop: close the rings of a camera whose process ended, if the camera still has that
        ring. A restart before this call gives a new ring, which stays open."""
        with self._ring_lock:
            if self.rings.get(camera_id) is not ring:
                return
            logger.info(f"The process of camera {camera_id} ended; its rings close")
            self._close_rings([camera_id])

    def _mark_ended(self, camera_id: CameraIdString, worker) -> None:
        """A camera process that ended with no final state (a native crash, a kill, an error before the loop)
        gets one, so that the gate and the waits of the group do not wait for it (8.2)."""
        status = self.cameras.orchestrator.camera_statuses.get(camera_id)
        if status is None or self.cameras.camera_workers.get(camera_id) is not worker:
            return
        status.recording_in_progress.value = False  # an ended process cannot clear it; else each apply gets 409 (D36)
        if status.state in ("failed", "dead"):
            return
        stage, state = ("open", "failed") if status.state in ("starting", None) else ("streaming", "dead")
        reason = f"camera process ended (exit code {worker.worker.exitcode})"
        status.update_info(failure=dict(camera_id=camera_id, stage=stage, reason=reason, code="process-ended"))
        self._note_failure(camera_id, "process-ended")
        status.set_state(state)
        logger.warning(f"Camera {camera_id} failed during {stage}: {reason}")

    def _take_finished(self) -> None:
        """Move each message of the camera writers from its queue to `finished`. A stall or a write error of one
        camera ends the take for every camera (recorder.md 5.3, 5.4) [C5]."""
        while True:
            try:
                message = self.ipc.recording_finished_subscription.get_nowait()
            except queue.Empty:
                return
            if message.result is None and message.error is not None:
                if self.take is not None and self.take_error is None:
                    self.take_error = (message.error, message.camera_id)
                    logger.error(f"The take ends: {message.error}")
                    future = asyncio.run_coroutine_threadsafe(self._end_after_error(), self._loop)
                    future.add_done_callback(self._log_failed_end)
            else:
                self.finished.append(message)

    def _take_diagnostics(self) -> None:
        """Keep the newest diagnostics of each camera; the status gets the counter subset (unix-capture.md 4.2)."""
        statuses = self.cameras.orchestrator.camera_statuses
        while True:
            try:
                message = self.ipc.diagnostics_subscription.get_nowait()
            except queue.Empty:
                return
            self.camera_diagnostics[message.camera_id] = message.diagnostics
            summary, kept = getattr(message, "timings", None), self.camera_timings
            if summary is not None:
                self.camera_timings = {**kept, message.camera_id: (summary, capture_timings.main_clock_ns())}
            elif message.camera_id in kept:
                self.camera_timings = {key: value for key, value in kept.items() if key != message.camera_id}
            status = statuses.get(message.camera_id)
            if status is not None:
                status.diagnostics = {key: message.diagnostics.get(key) for key in COUNTER_KEYS}

    def _note_failure(self, camera_id: CameraIdString, code: str) -> None:
        """A failure that the main process sets also goes into the kept diagnostics (F10)."""
        self.camera_diagnostics[camera_id] = {**self.camera_diagnostics.get(camera_id, {}), "fail_code": code}
        status = self.cameras.orchestrator.camera_statuses.get(camera_id)
        if status is not None:
            status.diagnostics = {**status.diagnostics, "fail_code": code}

    def diagnostics(self, camera_id: CameraIdString) -> dict:
        """The newest full diagnostics dict of a camera; `{}` before its first message (unix-capture.md 4.2)."""
        return self.camera_diagnostics.get(camera_id, {})

    @staticmethod
    def _log_failed_end(future) -> None:
        """`run_coroutine_threadsafe` keeps an exception in its future; nothing else would see it."""
        error = None if future.cancelled() else future.exception()
        if error is not None:
            logger.error(f"The end of the take after an error failed: {error!r}", exc_info=error)

    def _open_rings(self, configs: CameraConfigs) -> None:
        """Create the ring of each camera in `configs`, attach a reader, and give the ring names to
        the camera processes (spec 7.1 and 7.3)."""
        if not configs:
            return
        for camera_id, ring in create_session_rings(configs).items():
            self.rings[camera_id] = ring
            self.ring_readers[camera_id] = FrameRingReader.attach(ring.name)
            self.ring_infos[camera_id] = camera_ring_info(configs[camera_id], ring)
        self.ipc.publish_shm_message(ring_infos=dict(self.ring_infos))

    def _close_rings(self, camera_ids: list) -> None:
        """Close the reader, then set `closed`, close and unlink the ring of each camera (spec 7.4).

        A writer that has not detached keeps the block: a POSIX mapping stays after an unlink, and
        Windows frees the block when its last handle closes (spec 7.7)."""
        for camera_id in camera_ids:
            reader, ring = self.ring_readers.pop(camera_id, None), self.rings.pop(camera_id, None)
            self.ring_infos.pop(camera_id, None)
            if reader is not None:
                reader.close()
            if ring is not None:
                ring.close_and_unlink()

    @property
    def camera_ids(self) -> list[CameraIdString]:
        return list(self.configs.keys())

    def read_latest_ring_frames(self, step_set=None) -> dict[CameraIdString, FrameRead] | None:
        """The newest frame of each camera that has one to show (interim relay of 5.8, U13). `step_set`: the
        preview steps of a connection (capture-timings.md 6.5); None measures nothing."""
        statuses = self.cameras.orchestrator.camera_statuses
        on = step_set is not None and step_set.control.on
        with self._ring_lock:
            reads = {}
            for camera_id, reader in self.ring_readers.items():
                status = statuses.get(camera_id)
                if status is None or not status.in_gate:  # agent 54: no frame to show, for example `starting`
                    continue
                if on:
                    t0 = step_set.control.clock()
                read = reader.read_newest()
                if on:
                    step_set.add((self.id, camera_id, "preview_ring_read"), step_set.control.clock() - t0)
                if read.result is ReadResult.OK:
                    reads[camera_id] = read
            return reads or None

    def get_latest_ring_payload(self, step_set=None) -> tuple[FrameNumberInt, MultiframeTimestampFloat, memoryview] | None:
        """A websocket message in the wire format of today, with the ring JPEG of each camera,
        untouched: no resize, no re-encode and no rotation (spec 2.3) [A4]. Interim (5.8): the
        newest frame of each camera on its own; the message header has the largest frame number.
        `step_set`: the preview steps of a connection; the build of the message is `preview_pack`, and the
        `published_ns` of each camera waits in `pending` for the send (capture-timings.md 6.5)."""
        with self._ring_lock:
            reads = self.read_latest_ring_frames(step_set)
            if reads is None:
                return None
            infos = {camera_id: self.ring_infos[camera_id] for camera_id in reads}
        on = step_set is not None and step_set.control.on
        if on:
            t0 = step_set.control.clock()
        frame_number = max(read.frame_number for read in reads.values())
        header = np.zeros(1, dtype=FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE)
        header["message_type"] = MessageType.PAYLOAD_HEADER
        header["frame_number"] = frame_number
        header["number_of_cameras"] = len(reads)
        payload = bytearray(header.tobytes())
        for camera_id, read in reads.items():
            info = infos[camera_id]
            frame_header = np.zeros(1, dtype=FRONTEND_FRAME_HEADER_DTYPE)
            frame_header["message_type"] = MessageType.FRAME_HEADER
            frame_header["frame_number"] = read.frame_number
            frame_header["camera_id"] = camera_id.encode("ascii")
            frame_header["camera_index"] = info.camera_index
            frame_header["image_width"] = info.mode.width
            frame_header["image_height"] = info.mode.height
            frame_header["color_channels"] = 3
            frame_header["jpeg_string_length"] = read.payload_len
            payload += frame_header.tobytes()
            payload += read.payload
        header["message_type"] = MessageType.PAYLOAD_FOOTER
        payload += header.tobytes()
        timestamp = float(np.mean([read.arrival_ns for read in reads.values()]))
        message = memoryview(payload).toreadonly()
        if on:
            step_set.add((self.id, None, "preview_pack"), step_set.control.clock() - t0)
            step_set.pending[self.id] = [(camera_id, read.published_ns) for camera_id, read in reads.items()]
        return frame_number, timestamp, message

    async def start_recording(self, recording_info: RecordingInfo, devices: dict | None = None) -> list:
        """Start a take (recorder.md section 10 items 3 to 5, 13). Return the warnings of 11.3. One start, stop or
        error end at a time: a second start waits for the finish of a failed start (ADR-P5VE)."""
        async with self._end_lock:
            return await self._start_recording(recording_info, devices)

    async def _start_recording(self, recording_info: RecordingInfo, devices: dict | None) -> list:
        statuses = self.cameras.orchestrator.camera_statuses
        if recording_info.mic_device_index >= 0:
            raise RequestRefused(422, MICROPHONE_REFUSED)  # [C1]
        blocking = [f"camera {camera_id} is {'adjusting' if status.search_requested.value else status.serialize()['state']}"
                    for camera_id, status in list(statuses.items())
                    if not status.ready or status.search_requested.value]  # a search that is asked for (1.5)
        if blocking or self.take is not None:  # a recording starts only when each selected camera is `ready` (8.3)
            raise RequestRefused(409, "A recording needs each selected camera ready: " + "; ".join(blocking or ["a recording runs"]))
        if self.request_runs:
            raise RequestRefused(409, REQUEST_RUNS)
        self.fall_back_armed = None  # camera-requests.md 2.4a item 9: a rate change never disturbs a recording
        folder = Path(recording_info.recording_directory) / recording_info.recording_name
        if folder.is_dir() and any(folder.iterdir()):
            raise RequestRefused(409, f"The take folder holds files: {folder}")  # [agent 16]
        warnings = []
        for camera_id, status in list(statuses.items()):
            controls = status.info_dict().get("controls") or {}
            # 3a sets exposure only; gain and focus come through the config from 3c (D30, D43)
            auto = [name for name in ("exposure",) if (controls.get(name) or {}).get("auto")]
            items = [dict(kind="auto_control", camera_ids=[camera_id], control=name,
                          text=f"Camera {camera_id}: exposure is in auto mode at the start of the recording")
                     for name in auto]
            status.set_warning_items(items)
            warnings += items
        # The take order (group_position) is the order of the request's camera_index (camera-requests.md 8.1)
        self.recording_ids = sorted(statuses, key=lambda camera_id: self.configs[camera_id].camera_index)
        self.take_error = None
        self.finished.clear()  # a late message of an earlier take
        await self.cameras.pause(await_paused=True)  # each camera gives the layout of its last good frame
        orchestrator = self.cameras.orchestrator
        take, sent = None, False
        try:
            cameras = [self._take_camera(camera_id, (devices or {}).get(camera_id)) for camera_id in self.recording_ids]
            try:
                take = await asyncio.to_thread(start_take, folder, recording_info.recording_name, cameras, writer=WRITER,
                                               queue_seconds=TAKE_QUEUE_SECONDS, stall_limit_s=TAKE_STALL_LIMIT_S)
            except ValueError as error:  # a bad name, a FAT disk (D3), a camera that the format refuses
                raise RequestRefused(422, str(error))
            specs = {camera_id: take.camera_spec(camera_id) for camera_id in self.recording_ids}  # before any goes out
            orchestrator.last_frame = -1
            orchestrator.first_recording_frame_number.value = orchestrator.largest_gate_count() + 3  # [M7, review B4]
            self.take = take
            for camera_id in self.recording_ids:
                statuses[camera_id].update_info(writer_failure=None)
            sent = True  # from here, a camera can have a writer
            self.ipc.pubsub.topics[TopicTypes.RECORDING_INFO].publish(RecordingInfoMessage(take_specs=specs))
            await self._await_writers()
        except BaseException as error:
            for status in list(statuses.values()):
                status.set_warning_items([])
            self.take = None
            try:
                if sent:
                    # Each camera with a writer ends it at its next frame, with no row; a camera that gets its take
                    # spec from now on refuses it (`CameraLoop._start_take`).
                    orchestrator.last_frame = orchestrator.first_recording_frame_number.value
                # No wait: a camera that still opens its files cannot unpause in time, and the group runs on.
                await orchestrator.unpause(await_unpaused=False)
            finally:
                if take is not None:
                    await self._finish_failed_start(take, error, wait=sent)
            raise
        if self.ended_take is not None:  # its files and manifest are finished; only the stop response goes (8.4)
            logger.warning(f"A new take starts: the summary of the take "
                           f"{self.ended_take.stop_response.get('recording_name')} that an error ended was not "
                           f"fetched by a stop request")
            self.ended_take = self.ended_take_summary = None
        try:
            await orchestrator.unpause(await_unpaused=True)
        except (RuntimeError, TimeoutError) as error:  # each writer started: the take runs on
            logger.warning(f"The record start could not unpause each camera in time ({error}); the take runs on")
        for item in warnings:
            logger.warning(item["text"])
        logger.info(f"Started recording for camera group ID: {self.id} with recording name: "
                    f"{recording_info.recording_name}")
        return warnings

    async def _finish_failed_start(self, take: Take, error: BaseException, wait: bool) -> None:
        """Decision D of the user (2026-11-20): a record start that fails finishes the take folder at once, with
        zero rows and a `take_error`. It waits first for each camera that has a writer or can still start one
        (in the gate): its result, or its refusal (`writer_failure`). Thus no live writer has its files
        completed (8.1 step 4). With `wait` false, no take spec went out, so no camera is waited for."""
        orchestrator, ids = self.cameras.orchestrator, self.recording_ids
        statuses = orchestrator.camera_statuses
        try:
            self.recording_ids = [camera_id for camera_id in ids if wait and (
                statuses[camera_id].recording_in_progress.value or statuses[camera_id].in_gate)]
            results, dead, running = await asyncio.to_thread(self._collect_results)
            await asyncio.to_thread(take.finish, [results.get(camera_id) for camera_id in ids], frame_count=0,
                                    ended_by_error=f"the record start failed: {error}", dead_cameras=dead,
                                    running_cameras=running)
        except Exception as finish_error:
            logger.exception(f"The take folder of the failed record start could not be finished: {finish_error!r}")
        finally:
            self.recording_ids = ids
            orchestrator.first_recording_frame_number.value = -1
            orchestrator.last_frame = -1

    def _take_camera(self, camera_id: CameraIdString, device) -> TakeCamera:
        """The take facts of one camera (recorder.md 4.2, 6.7) from its config, status and detection."""
        config, info = self.configs[camera_id], self.cameras.orchestrator.camera_statuses[camera_id].info_dict()
        mode, layout, controls = info.get("mode") or {}, info.get("layout"), info.get("controls") or {}
        if mode.get("fps_num"):
            rate = (mode["fps_num"], mode["fps_den"])
        else:  # OpenCV reports no rate: the requested rate, or 30 for "auto" (ADR-PDD3 W2)
            fraction = Fraction(config.framerate if config.framerate > 0 else 30).limit_denominator(1001)
            rate = (fraction.numerator, fraction.denominator)
        source = info.get("source")
        backend = ((device.backend_name if device is not None and device.backend_name else "opencv").lower()
                   if source == "opencv" else "media_foundation" if source is None else source)
        return TakeCamera(
            camera_id=camera_id, nominal_rate=rate, width=mode.get("width", config.resolution.width),
            height=mode.get("height", config.resolution.height), rotation_cw_deg=rotation_to_cw_deg(config.rotation),
            capture_format=config.capture_fourcc,
            layout=JpegLayout(layout["width"], layout["height"], tuple(map(tuple, layout["factors"]))) if layout else None,
            os_name=device.name if device is not None else None,
            vendor_id=f"{device.vendor_id:04x}" if device is not None and device.vendor_id is not None else None,
            product_id=f"{device.product_id:04x}" if device is not None and device.product_id is not None else None,
            backend=backend, os_index=device.index if device is not None else config.camera_index,
            requested=dict(width=config.resolution.width, height=config.resolution.height,
                           framerate=config.framerate, capture_format=config.capture_fourcc,
                           exposure_mode=config.exposure_mode.lower()),
            controls={name: (value["value"], value["auto"]) for name, value in controls.items() if value.get("present")})

    async def _await_writers(self) -> None:
        """Wait, paused, until each live camera of the take started its writer: row 0 is then one agreed group
        frame for every camera (recorder.md 10 item 4)."""
        statuses = self.cameras.orchestrator.camera_statuses
        deadline = time.monotonic() + TAKE_START_LIMIT_S
        while True:
            failures = [statuses[camera_id].info_dict().get("writer_failure") for camera_id in self.recording_ids]
            pending = [camera_id for camera_id, failure in zip(self.recording_ids, failures)
                       if not failure and not statuses[camera_id].recording_in_progress.value
                       and statuses[camera_id].in_gate]
            if not pending:
                if any(failures):
                    raise RuntimeError("; ".join(failure for failure in failures if failure))
                return
            if time.monotonic() >= deadline or not self.ipc.running:
                raise RuntimeError(f"Cameras did not start their take writer: {pending}")
            await await_10ms()

    async def stop_recording(self) -> TakeSummary:
        """Stop the take (recorder.md 8.1). After a take that an error ended, return its summary once."""
        async with self._end_lock:  # one end at a time: a second stop waits, then gets the 409
            if self.take is None:
                if self.ended_take is None:
                    raise RequestRefused(409, "No recording runs")
                summary, self.ended_take, self.ended_take_summary = self.ended_take, None, None
                return summary
            return await self._end_take()

    async def _end_after_error(self) -> None:
        """A stall or a write error ends the take at once for every camera (5.3, 5.4) [C5]."""
        async with self._end_lock:
            if self.take is not None:
                error, camera_id = self.take_error or (None, None)  # `_end_take` clears it
                summary = await self._end_take()
                self.ended_take, self.ended_take_summary = summary, dict(  # JSON gives a NaN statistic as null
                    take_error=error, camera_id=camera_id,
                    summary=TypeAdapter(dict).dump_python(summary.stop_response, mode="json"))

    async def _end_take(self) -> TakeSummary:
        """8.1, under `_end_lock`: set the last frame, wait for each camera (D1), then `Take.finish`."""
        take = self.take
        orchestrator = self.cameras.orchestrator
        statuses = orchestrator.camera_statuses
        try:
            # No pause (S11, ADR-F8C0): a paused camera does not read, and the waiting place of a push source
            # replaces each frame that comes in the pause, so the first frame after it had `gap`. The gate lets a
            # camera hold one frame more than the largest count, so the take ends two group frames after it.
            # The read of the gate count and the write of the last frame are under the lock of the last frame: a
            # camera reads that value with its lock, so it decides no new frame between them. A last frame that a
            # camera set first (the end with no take level) stays.
            # The wait for that lock is bounded (unix-capture.md 4.10): a camera killed while it held the lock keeps it
            # for ever. With no lock in FRAME_LOCK_WAIT_S the take ends as an error; the values go with no lock.
            last, lock = orchestrator.last_recording_frame_number.get_obj(), orchestrator.last_recording_frame_number.get_lock()
            locked = lock.acquire(timeout=FRAME_LOCK_WAIT_S)
            try:
                if not locked and self.take_error is None:
                    self.take_error = (f"no lock of the last frame of the take in {FRAME_LOCK_WAIT_S:g} s", None)
                    logger.error(f"The take ends: {self.take_error[0]}")
                if last.value == -1:
                    count = orchestrator.largest_gate_count()
                    if count == -1:  # no camera left in the gate: the take ends after the latest group frame
                        count = max(statuses[camera_id].frame_count.value for camera_id in self.recording_ids
                                    if camera_id in statuses) - 1
                    # At least the first frame: when no camera reached it, the take has no row, not a negative count.
                    last.value = max(count + 2, orchestrator.first_recording_frame_number.value)
            finally:
                if locked:
                    lock.release()
            # A guard: a camera that is still paused records to the last frame. No wait.
            await orchestrator.unpause(await_unpaused=False)
            frame_count = last.value - orchestrator.first_recording_frame_number.value  # recorder.md 7.6
            results, dead, running = await asyncio.to_thread(self._collect_results)
            error, error_camera = self.take_error or (None, None)
            summary = await asyncio.to_thread(
                take.finish, [results.get(camera_id) for camera_id in self.recording_ids], frame_count=frame_count,
                ended_by_error=error, dead_cameras=dead, error_camera=error_camera, running_cameras=running)
        finally:
            self.take = self.take_error = None
            orchestrator.first_recording_frame_number.value = -1
            orchestrator.last_frame = -1  # the take ended: no camera decides on it
            for status in list(statuses.values()):
                status.set_warning_items([])
        logger.info(f"Stopped recording for camera group ID: {self.id} with recording name: {take.rec}")
        return summary

    def _collect_results(self) -> tuple[dict, dict, set]:
        """8.1 step 4: wait for the result of each camera while its writer makes progress [C6DE D1]. A camera
        whose writer stays stuck has its process ended and is `failed` (5.3 item 6). The files of a camera are
        touched only after its result came or its process was joined [review B2]: the third item holds each
        camera whose process still runs after a kill."""
        statuses, workers = self.cameras.orchestrator.camera_statuses, self.cameras.camera_workers
        pending, results, dead, ended_since = set(self.recording_ids), {}, {}, {}
        started = time.monotonic()
        stuck = []
        while pending:
            self._take_finished()
            for message in [m for m in self.finished if m.result is not None]:
                self.finished.remove(message)
                if message.camera_id in pending:
                    results[message.camera_id] = message.result
                    pending.discard(message.camera_id)
                    if message.result.error == "disk stall":
                        stuck.append(message.camera_id)
                    if message.result.error is not None and self.take_error is None:  # an error during the stop
                        self.take_error = (f"disk stall on camera {message.camera_id}" if message.result.error
                                           == "disk stall" else message.result.error, message.camera_id)
            now = time.monotonic()
            for camera_id in list(pending):
                worker, status = workers.get(camera_id), statuses.get(camera_id)
                if worker is None or worker.worker.exitcode is not None:
                    if now - ended_since.setdefault(camera_id, now) > GIVE_UP_AFTER_EXIT_S:
                        if worker is not None:
                            worker.join(timeout=BOUNDED_JOIN_S)
                        if status is not None:
                            status.recording_in_progress.value = False  # a process that ended hard left it set
                        info = status.info_dict() if status is not None else {}
                        exitcode = None if worker is None else worker.worker.exitcode
                        failure = info.get("failure") or {}
                        dead[camera_id] = ("hang" if info.get("hung") else failure.get("reason")
                                           if failure.get("code") == "stalled" else f"exit code {exitcode}")
                        pending.discard(camera_id)
                elif status is None or now - max(status.writer_progress_at.value, started) > TAKE_STALL_LIMIT_S + STALL_MARGIN_S:
                    stuck.append(camera_id)
                    pending.discard(camera_id)
                    if self.take_error is None:
                        self.take_error = (f"disk stall on camera {camera_id}", camera_id)
                elif not status.recording_in_progress.value and status.info_dict().get("writer_failure"):
                    pending.discard(camera_id)  # its writer did not start: no result, and no file of its own
            if pending:
                time.sleep(WATCH_INTERVAL_S)
        running = set()
        for camera_id in stuck:
            if not self._end_stuck_camera(camera_id):
                running.add(camera_id)
            dead[camera_id] = "disk stall"
        for camera_id in results:
            status = statuses.get(camera_id)
            if camera_id not in dead and status is not None and status.state in ("dead", "failed"):
                dead[camera_id] = ((status.info_dict().get("failure") or {}).get("reason")) or status.state
        return results, dead, running

    def _end_stuck_camera(self, camera_id: CameraIdString) -> bool:
        """5.3 item 6 [C6]: end the process (terminate, join, and kill when it still runs); the camera is `failed`,
        stage `recording`. Return False when the process still runs: the take level must not touch its files."""
        status, worker = self.cameras.orchestrator.camera_statuses[camera_id], self.cameras.camera_workers.get(camera_id)
        status.recording_in_progress.value = False  # the take level completes its files after the join (7.4)
        status.should_close.value = True
        ended = True
        if worker is not None:
            worker.worker.terminate()
            worker.join(timeout=BOUNDED_JOIN_S)
            if worker.is_alive():
                worker.worker.kill()
                worker.join(timeout=BOUNDED_JOIN_S)
                ended = not worker.is_alive()
            if not ended:
                logger.error(f"The process of camera {camera_id} still runs after a kill; its files stay as they are")
        status.update_info(failure=dict(camera_id=camera_id, stage="recording", reason="disk stall", code="disk-stall"))
        self._note_failure(camera_id, "disk-stall")
        status.set_state("failed")
        logger.error(f"Camera {camera_id} failed during recording: disk stall")
        return ended

    async def close(self) -> None:
        logger.debug("Closing camera group")

        if self.take is not None:  # the take, not the status flags: a hard-ended process leaves its flag set
            logger.info("Recording in progress — stopping recording before closing cameras")
            try:
                await self.stop_recording()
            except RequestRefused as e:  # a stop or a close that ran at the same time ended the take first
                logger.info(f"The close found no take to stop: {e.detail}")
            except Exception as e:
                logger.error(f"Error stopping recording during close: {type(e).__name__} - {e}")

        self._closing = True  # the watch thread goes on reading the queues: each close dict arrives (F4)
        self.ipc.should_continue = False
        with self._ring_lock:
            for ring in self.rings.values():
                ring.set_closed()
        try:
            await asyncio.to_thread(self._close_cameras)  # the joins take seconds: not on the loop
        finally:
            self._stop_watch.set()
            self._take_diagnostics()  # a dict that came after the last round of the watch

        try:
            with self._ring_lock:
                self._close_rings(list(self.rings))
        except Exception as e:
            logger.error(f"Error closing the frame rings: {type(e).__name__} - {e}")
        logger.success("Frame rings closed and unlinked.")

        # windows-capture.md 5.9: the queues close last, when no camera writes and the watch reads no more
        watch = self._watch_thread
        if watch is not None:
            await asyncio.to_thread(watch.join, 2.0)
        if watch is None or not watch.is_alive():
            close_camera_group_pubsub_manager(self.id)
            self.ipc.setup_failures.close()
        else:
            logger.error(f"Camera group {self.id}: the watch did not end in 2 s; its queues stay open")
        logger.success("Camera group closed successfully.")

    def add_group_warning(self, item: dict) -> None:
        """An item of the main process (`start_failure`; `rate_fallback` of step 4) in the status of each camera that
        it names (camera-requests.md 1.5) [AC5B]."""
        statuses = self.cameras.orchestrator.camera_statuses
        for camera_id in item["camera_ids"]:
            if camera_id in statuses:
                statuses[camera_id].replace_warning_items("group_warnings", (item["kind"],), [item])

    def clear_group_warnings(self) -> None:
        """At each apply request of the user (camera-requests.md 1.5); the fall back of step 4 must not call it."""
        for status in list(self.cameras.orchestrator.camera_statuses.values()):
            status.set_warning_items([], "group_warnings")

    def mode_rate(self, camera_id: CameraIdString) -> float | None:
        """The rate of the opened mode of a camera, or None before a mode is open."""
        mode = self.cameras.orchestrator.camera_statuses[camera_id].info_dict().get("mode") or {}
        return mode["fps_num"] / mode["fps_den"] if mode.get("fps_num") else None

    async def fall_back(self, configs: CameraConfigs, slow: dict) -> tuple[dict, list]:
        """The one fall back of the group to 30 fps (camera-requests.md 2.4, 2.4a) [ADR-1T0S]: one `rate_fallback` item
        in the status of each camera of `slow`, then an apply of `configs`. `slow`: camera_id: (measured fps, exposure,
        mode rate), read when the failure was seen; the mode rate is None for a `set mode` failure. Return the failures
        and the warnings of that apply, after the items. Never during a take, a record start or a close (2.4a item 9)."""
        if self._closing or self.take is not None or self.take_busy:
            logger.warning(f"The fall back of camera group {self.id} to 30 fps does not run during a take, a record start "
                           f"or a close")
            return {}, []
        runs, self.request_runs = self.request_runs, True  # inside a user apply (the start-up path) it is set already
        try:
            items = []
            for camera_id, (measured, exposure, fps) in slow.items():
                text = f"The group runs at 30 fps. Camera {camera_id} " + (
                    "could not set its 60 fps mode." if fps is None else f"found no exposure that keeps {fps:g} fps."
                    if measured is None else f"measured {measured:.2f} fps in its {fps:g} fps mode"
                    + ("." if exposure is None else f" at exposure {exposure:g}."))
                items.append(dict(kind="rate_fallback", camera_ids=[camera_id], text=text))
                logger.warning(text)
                self.add_group_warning(items[-1])
            statuses = self.cameras.orchestrator.camera_statuses  # [Z7F3]: never a camera with a wedge code now
            retry = [camera_id for camera_id in slow if camera_id in statuses
                     and (statuses[camera_id].info_dict().get("failure") or {}).get("code") not in WEDGE_CODES]
            failures, warnings = await self.apply(configs, retry=retry)  # 2.4a item 3: only the cameras that failed
            return failures, items + warnings
        finally:
            self.request_runs = runs

    def _watch_fall_back(self) -> None:
        """camera-requests.md 2.4a item 5 [ADR-1T0S]: after an apply request at 60 fps, a camera in `AUTO` whose search
        of that request (`held.count`) found no value that keeps the rate, or whose check after it failed, starts the
        fall back. The watch stops when no camera starts, waits, searches or checks."""
        armed = self.fall_back_armed
        if armed is None or self._closing:
            return
        configs, counts, request = armed
        statuses = self.cameras.orchestrator.camera_statuses
        slow = {}
        for camera_id, status in list(statuses.items()):
            info, config = status.info_dict(), self.configs.get(camera_id)
            held = info.get("held") or {}
            if config is None or config.exposure_mode != "AUTO" or held.get("count", 0) <= counts.get(camera_id, 0):
                continue
            search = info.get("exposure_search") or {}
            if search.get("state") == "failed" and search.get("reason") == "no-value-kept-rate":
                best = max(search.get("trials") or [{}], key=lambda trial: trial.get("measured_fps") or 0)
                # [B7]: the trial with the highest rate
                slow[camera_id] = (best.get("measured_fps"), best.get("value"), self.mode_rate(camera_id) or config.framerate)
            elif status.state == "too_slow":
                slow[camera_id] = (info.get("measured_fps"), held.get("exposure"), self.mode_rate(camera_id) or config.framerate)
        busy = any(status.state in ("starting", "waiting", "adjusting", "checking") for status in list(statuses.values()))
        if (slow or not busy) and self.fall_back_armed is armed:  # an apply request of the user can have replaced it
            self.fall_back_armed = None
            if slow:
                asyncio.run_coroutine_threadsafe(self._fall_back_after_search(configs, slow, request), self._loop)

    async def _fall_back_after_search(self, configs: CameraConfigs, slow: dict, request: int) -> None:
        """On the event loop, as `_end_after_error`; no response carries the result, so the log gets a failure. The check
        of the request count and the flag of `fall_back` come with no wait between them (2.4a item 7)."""
        try:
            if request != self.request_count or self.request_runs:
                logger.warning(f"The fall back of camera group {self.id} to 30 fps does not run: a later request of the "
                               f"user replaced the request at 60 fps, or runs now")
            else:
                await self.fall_back(configs, slow)
        except Exception as error:
            logger.exception(f"The fall back of camera group {self.id} to 30 fps failed: {error!r}")

    async def search_exposure(self, camera_ids: list) -> dict:
        """camera-requests.md 1.5: each camera of `camera_ids` (checked by the manager) searches on its open stream;
        return when each search has ended, within SEARCH_WAIT_LIMIT_S. The response of the endpoint. A camera whose
        process is alive and still `adjusting` at the limit is not marked `failed`: its result comes in the live state."""
        statuses = self.cameras.orchestrator.camera_statuses
        counts = {camera_id: statuses[camera_id].search_count.value for camera_id in camera_ids}
        for camera_id in camera_ids:
            statuses[camera_id].search_requested.value = True
        deadline = time.monotonic() + SEARCH_WAIT_LIMIT_S

        def ended(camera_id):
            status = statuses[camera_id]
            search = status.serialize()["exposure_search"] or {}
            return status.state in ("failed", "dead") or (not status.search_requested.value and (
                status.search_count.value == counts[camera_id] or search.get("state") != "running"))

        while self.ipc.running and not all(ended(camera_id) for camera_id in camera_ids):
            for camera_id in camera_ids:
                worker = self.cameras.camera_workers.get(camera_id)
                if worker is not None and worker.worker.exitcode is not None:
                    self._mark_ended(camera_id, worker)
            if time.monotonic() >= deadline:
                self._give_up([camera_id for camera_id in camera_ids if not ended(camera_id)
                               and statuses[camera_id].state != "adjusting"], "streaming", SEARCH_WAIT_LIMIT_S)
                break
            await await_10ms()
        self.adopt_search_results()
        searched = [camera_id for camera_id in camera_ids if statuses[camera_id].search_count.value > counts[camera_id]]
        return dict(
            camera_configs={camera_id: config.model_dump(mode="json") for camera_id, config in self.configs.items()},
            results={camera_id: statuses[camera_id].serialize()["exposure_search"] for camera_id in searched},
            camera_failures=self._failures(camera_ids),
            warnings=[item for camera_id in searched for item in statuses[camera_id].warning_items(
                "camera_warnings") if item["kind"] in ("add_light", "exposure_search_failed")])

    def adopt_search_results(self) -> None:
        """Copy the held value of each ended search into `configs`, once for each search (camera-requests.md 1.3b):
        the camera process writes it into its status (`held`), with the search count."""
        for camera_id, status in list(self.cameras.orchestrator.camera_statuses.items()):
            held = status.info_dict().get("held")
            if held and camera_id in self.configs and held["count"] != self._adopted.get(camera_id):
                self._adopted[camera_id] = held.pop("count")
                self.configs[camera_id] = self.configs[camera_id].model_copy(update=held)
                # the camera left the clamped MANUAL value (camera-requests.md 1.5) [NYT6]
                status.replace_warning_items("group_warnings", ("exposure_clamped",), [])

    def to_state(self) -> CameraGroupState:
        self.adopt_search_results()
        # "ended_with_error" stays during a record start, until it succeeds (recorder.md 8.4)
        take_state = "ended_with_error" if self.ended_take is not None else "none" if self.take is None else "recording"
        return CameraGroupState(
            id=self.id,
            configs=self.configs,
            cameras={
                camera_id: worker.to_state()
                for camera_id, worker in list(self.cameras.camera_workers.items())
            },
            alive=self.alive,
            recording_in_progress=take_state == "recording",  # also when each camera died during the take
            take_state=take_state,
            ended_take_summary=self.ended_take_summary if take_state == "ended_with_error" else None,
        )
