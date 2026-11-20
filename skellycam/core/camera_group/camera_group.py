import asyncio
import logging
import queue
import threading
import time
from fractions import Fraction
from pathlib import Path

from skellycam.core.camera_group.camera_setup_failure import CameraSetupFailedException
from multiprocessing.sharedctypes import Synchronized
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from skellycam import __version__
from skellycam.core.camera.camera_manager import CameraManager
from skellycam.core.camera.camera_worker import CameraState
from skellycam.core.camera.capture.camera_loop import needs_reopen
from skellycam.core.camera.config.camera_config import CameraConfigs, CameraConfig, validate_camera_configs
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_status import SETTLED_STATES
from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes
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
MICROPHONE_REFUSED = "audio recording returns in step 5b; start again with no microphone"  # recorder.md 10 item 13
WRITER = f"skellycam {__version__.lstrip('v')}"  # SFF-712


class RequestRefused(Exception):
    """A request that the whole-request check refuses (8.3): 422 by its content, 409 by the camera states."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


def same_config(requested: CameraConfig, current: CameraConfig) -> bool:
    """The same config in an apply request has no effect (8.3). "Auto" matches the mode rate (D17)."""
    update = {}
    if requested.framerate in (-1, 0):
        update["framerate"] = current.framerate
    if requested.exposure_mode == "RECOMMEND":  # the stored config holds the result of the search (11.1)
        update.update(exposure_mode=current.exposure_mode, exposure=current.exposure)
    elif requested.exposure_mode == "AUTO":
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
    recording_in_progress: bool
    paused: bool


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
    take_error: tuple | None = None  # (text, camera_id) of the first stall or write error of the take (5.3, 5.4)
    _end_lock: Any = field(default_factory=asyncio.Lock)
    _ring_lock: Any = field(default_factory=threading.RLock)
    _stop_watch: Any = field(default_factory=threading.Event)
    _loop: Any = None  # the event loop of `start`: a ring reader is closed only on it (ADR-BM73)

    @property
    def id(self) -> CameraGroupIdString:
        return self.ipc.group_id

    @property
    def alive(self) -> bool:
        return (
            self.ipc.should_continue
            and bool(self.cameras.camera_workers)
            and all(
                status.connected.value and not status.closed.value
                and not status.closing.value and not status.error.value
                for status in self.cameras.orchestrator.camera_statuses.values()
            )
            and all(worker.is_alive() for worker in self.cameras.camera_workers.values())
        )

    @classmethod
    def create(
        cls,
        *,
        camera_configs: CameraConfigs,
        heartbeat_timestamp: Synchronized,
        global_kill_flag: Synchronized,
        worker_registry: WorkerRegistry,
        source_factory: Callable | None = None,
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
            )
        except Exception as e:
            logger.error(f"Error creating camera group: {type(e).__name__} - {e}")
            global_kill_flag.value = True
            raise

        return cls(
            ipc=ipc,
            cameras=cameras,
            configs=dict(camera_configs),
        )

    async def start(self) -> dict:
        """Start each camera. Return the failure object of each camera that failed (8.4, section 12)."""
        self.started = True
        self._loop = asyncio.get_running_loop()
        logger.info(f"Starting camera group ID: {self.id} with cameras: {list(self.configs.keys())}")
        self.cameras.start()
        threading.Thread(target=self._watch_workers, name=f"camera group {self.id} watch", daemon=True).start()
        configs, _ = await self._await_results(list(self.configs))
        if not self.ipc.should_continue:
            raise CameraSetupFailedException("Camera group startup aborted")
        sweep_stale_rings()
        with self._ring_lock:
            self._open_rings(configs)
        self.configs.update(configs)
        await self._await_settled(list(self.configs))
        return self._failures(list(self.configs))

    async def apply(self, requested: CameraConfigs) -> tuple[dict, list]:
        """Apply a checked request to each camera on its own (8.3, U10). Return the failures and the warnings.

        A camera that was unselected and is selected again starts again (8.3). Each other camera of the
        request that is not in the group is left out, as before phase 3: the other camera processes have
        no status for it, so it cannot join their gate.
        """
        statuses = self.cameras.orchestrator.camera_statuses
        restart, changed, removed = [], {}, []
        for camera_id, config in requested.items():
            if camera_id not in self.configs:
                if config.use_this_camera and camera_id in self.cameras.removed_statuses:
                    self.configs[camera_id] = config
                    restart.append(camera_id)
                continue
            worker = self.cameras.camera_workers.get(camera_id)
            if not config.use_this_camera:
                removed.append(camera_id)
            elif (statuses[camera_id].state in ("failed", "dead") or worker is None
                  or worker.worker.exitcode is not None):
                restart.append(camera_id)
            elif not same_config(config, self.configs[camera_id]):
                changed[camera_id] = config
        # The joins of a camera process take seconds: not on the event loop, which serves the preview.
        for camera_id in removed:
            await asyncio.to_thread(self.cameras.remove_camera, camera_id)
            with self._ring_lock:
                self._close_rings([camera_id])
            del self.configs[camera_id]
        for camera_id in restart:
            with self._ring_lock:
                self._close_rings([camera_id])
            await asyncio.to_thread(self.cameras.restart_camera, camera_id, requested[camera_id])
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
        logger.info(f"Applied camera configs - {list(requested.keys())}")
        return self._failures(reopened), warnings

    async def update_camera_settings(self, requested_configs: CameraConfigs) -> CameraConfigs:
        await self.apply(requested_configs)
        return self.configs

    async def _await_results(self, camera_ids: list) -> tuple[CameraConfigs, list]:
        """Wait until each camera published its config after the read-back (9.1 step 6), or failed."""
        pending, configs, warnings = set(camera_ids), {}, []
        statuses = self.cameras.orchestrator.camera_statuses
        subscription = self.ipc.extracted_config_subscription
        while pending and self.ipc.should_continue:
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
        """Wait until each camera has passed its rate check or failed (9.1, 10.1)."""
        statuses = self.cameras.orchestrator.camera_statuses
        while self.ipc.should_continue:
            for camera_id in camera_ids:
                worker = self.cameras.camera_workers.get(camera_id)
                if worker is not None and worker.worker.exitcode is not None:
                    self._mark_ended(camera_id, worker)
            pending = [camera_id for camera_id in camera_ids if camera_id in statuses
                       and statuses[camera_id].state not in SETTLED_STATES]
            if not pending:
                return
            await await_10ms()

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
            except Exception as error:
                logger.exception(f"Camera group {self.id}: the watch could not read the camera queues: {error}")
            for camera_id, worker in list(self.cameras.camera_workers.items()):
                try:
                    self._watch_camera(camera_id, worker)
                except Exception as error:
                    logger.exception(f"Camera group {self.id}: the watch of camera {camera_id} failed: {error}")

    def _watch_camera(self, camera_id: CameraIdString, worker) -> None:
        if worker.worker.exitcode is None:
            return
        self._mark_ended(camera_id, worker)
        ring = self.rings.get(camera_id)
        if ring is not None:
            # The readers are read on the event loop (the relay), so they are closed there too (ADR-BM73).
            self._loop.call_soon_threadsafe(self._close_ended_ring, camera_id, ring)

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
        status.update_info(failure=dict(camera_id=camera_id, stage=stage, reason=reason))
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

    def read_latest_ring_frames(self) -> dict[CameraIdString, FrameRead] | None:
        """The newest frame of each camera that has one to show (interim relay of 5.8, U13)."""
        statuses = self.cameras.orchestrator.camera_statuses
        with self._ring_lock:
            reads = {}
            for camera_id, reader in self.ring_readers.items():
                status = statuses.get(camera_id)
                if status is None or not status.in_gate:  # agent 54: no frame to show, for example `starting`
                    continue
                read = reader.read_newest()
                if read.result is ReadResult.OK:
                    reads[camera_id] = read
            return reads or None

    def get_latest_ring_payload(self) -> tuple[FrameNumberInt, MultiframeTimestampFloat, memoryview] | None:
        """A websocket message in the wire format of today, with the ring JPEG of each camera,
        untouched: no resize, no re-encode and no rotation (spec 2.3) [A4]. Interim (5.8): the
        newest frame of each camera on its own; the message header has the largest frame number."""
        with self._ring_lock:
            reads = self.read_latest_ring_frames()
            if reads is None:
                return None
            infos = {camera_id: self.ring_infos[camera_id] for camera_id in reads}
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
        return frame_number, timestamp, memoryview(payload).toreadonly()

    async def pause_unpause(self, await_state_change: bool = True) -> None:
        await self.cameras.pause_unpause(await_state_change)

    async def start_recording(self, recording_info: RecordingInfo, devices: dict | None = None) -> list:
        """Start a take (recorder.md section 10 items 3 to 5, 13). Return the warnings of 11.3."""
        statuses = self.cameras.orchestrator.camera_statuses
        if recording_info.mic_device_index >= 0:
            raise RequestRefused(422, MICROPHONE_REFUSED)  # [C1]
        blocking = [f"camera {camera_id} is {status.serialize()['state']}"
                    for camera_id, status in list(statuses.items())
                    if not status.ready]
        if blocking or self.take is not None:  # a recording starts only when each selected camera is `ready` (8.3)
            raise RequestRefused(409, "A recording needs each selected camera ready: " + "; ".join(blocking or ["a recording runs"]))
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
        self.recording_ids = list(statuses)
        self.ended_take = self.take_error = None
        self.finished.clear()  # a late message of an earlier take
        await self.cameras.pause(await_paused=True)  # each camera gives the layout of its last good frame
        try:
            cameras = [self._take_camera(camera_id, (devices or {}).get(camera_id)) for camera_id in self.recording_ids]
            try:
                take = await asyncio.to_thread(start_take, folder, recording_info.recording_name, cameras, writer=WRITER,
                                               queue_seconds=TAKE_QUEUE_SECONDS, stall_limit_s=TAKE_STALL_LIMIT_S)
            except ValueError as error:  # a bad name, a FAT disk (D3), a camera that the format refuses
                raise RequestRefused(422, str(error))
            orchestrator = self.cameras.orchestrator
            orchestrator.last_recording_frame_number.value = -1
            orchestrator.first_recording_frame_number.value = orchestrator.largest_gate_count() + 3  # [M7, review B4]
            self.take = take
            self.ipc.pubsub.topics[TopicTypes.RECORDING_INFO].publish(RecordingInfoMessage(
                take_specs={camera_id: take.camera_spec(camera_id) for camera_id in self.recording_ids}))
            await self._await_writers()
        except BaseException:
            for status in list(statuses.values()):
                status.set_warning_items([])
            if self.take is not None:
                # A camera with a writer ends it at its next frame; the folder stays `recording` (step 5c).
                self.cameras.orchestrator.last_recording_frame_number.value = (
                    self.cameras.orchestrator.first_recording_frame_number.value)
                self.take = None
            await self.cameras.unpause(await_unpaused=True)
            raise
        await self.cameras.unpause(await_unpaused=True)
        for item in warnings:
            logger.warning(item["text"])
        logger.info(f"Started recording for camera group ID: {self.id} with recording name: "
                    f"{recording_info.recording_name}")
        return warnings

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
            pending = [camera_id for camera_id in self.recording_ids
                       if not statuses[camera_id].recording_in_progress.value and statuses[camera_id].in_gate]
            if not pending:
                return
            if time.monotonic() >= deadline or not self.ipc.should_continue:
                raise RuntimeError(f"Cameras did not start their take writer: {pending}")
            await await_10ms()

    async def stop_recording(self) -> TakeSummary:
        """Stop the take (recorder.md 8.1). After a take that an error ended, return its summary once."""
        async with self._end_lock:  # one end at a time: a second stop waits, then gets the 409
            if self.take is None:
                if self.ended_take is None:
                    raise RequestRefused(409, "No recording runs")
                summary, self.ended_take = self.ended_take, None
                return summary
            return await self._end_take()

    async def _end_after_error(self) -> None:
        """A stall or a write error ends the take at once for every camera (5.3, 5.4) [C5]."""
        async with self._end_lock:
            if self.take is not None:
                self.ended_take = await self._end_take()

    async def _end_take(self) -> TakeSummary:
        """8.1, under `_end_lock`: set the last frame, wait for each camera (D1), then `Take.finish`."""
        take = self.take
        orchestrator = self.cameras.orchestrator
        statuses = orchestrator.camera_statuses
        try:
            # After an error, a stalled camera does not pause and holds the gate, so no camera passes the last frame.
            paused = self.take_error is None
            if paused:
                try:
                    await orchestrator.pause(await_paused=True)
                except (RuntimeError, TimeoutError) as error:
                    # A camera that waits in `give` cannot pause (5.3): end as after an error, with no pause.
                    logger.warning(f"The stop could not pause the cameras ({error}); it ends the take with no pause")
                    paused = False
                    await orchestrator.unpause(await_unpaused=False)
            count = orchestrator.largest_gate_count()
            if count == -1:  # no camera left in the gate: the take ends after the latest group frame
                count = max(statuses[camera_id].frame_count.value for camera_id in self.recording_ids if camera_id in statuses) - 2
            orchestrator.last_recording_frame_number.value = count + 3
            if paused:
                await self.cameras.unpause(await_unpaused=True)
            frame_count = orchestrator.take_frame_count()
            results, dead = await asyncio.to_thread(self._collect_results)
            error, error_camera = self.take_error or (None, None)
            summary = await asyncio.to_thread(
                take.finish, [results.get(camera_id) for camera_id in self.recording_ids], frame_count=frame_count,
                ended_by_error=error, dead_cameras=dead, error_camera=error_camera)
        finally:
            self.take = self.take_error = None
            orchestrator.first_recording_frame_number.value = -1
            orchestrator.last_recording_frame_number.value = -1
            for status in list(statuses.values()):
                status.set_warning_items([])
        logger.info(f"Stopped recording for camera group ID: {self.id} with recording name: {take.rec}")
        return summary

    def _collect_results(self) -> tuple[dict, dict]:
        """8.1 step 4: wait for the result of each camera while its writer makes progress [C6DE D1]. A camera
        whose writer stays stuck has its process ended and is `failed` (5.3 item 6). The files of a camera are
        touched only after its result came or its process was joined [review B2]."""
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
                        dead[camera_id] = "hang" if info.get("hung") else f"exit code {exitcode}"
                        pending.discard(camera_id)
                elif status is None or now - max(status.writer_progress_at.value, started) > TAKE_STALL_LIMIT_S + STALL_MARGIN_S:
                    stuck.append(camera_id)
                    pending.discard(camera_id)
                    if self.take_error is None:
                        self.take_error = (f"disk stall on camera {camera_id}", camera_id)
            if pending:
                time.sleep(WATCH_INTERVAL_S)
        for camera_id in stuck:
            self._end_stuck_camera(camera_id)
            dead[camera_id] = "disk stall"
        for camera_id in results:
            status = statuses.get(camera_id)
            if camera_id not in dead and status is not None and status.state in ("dead", "failed"):
                dead[camera_id] = ((status.info_dict().get("failure") or {}).get("reason")) or status.state
        return results, dead

    def _end_stuck_camera(self, camera_id: CameraIdString) -> None:
        """5.3 item 6 [C6]: end the process (terminate, then join); the camera is `failed`, stage `recording`."""
        status, worker = self.cameras.orchestrator.camera_statuses[camera_id], self.cameras.camera_workers.get(camera_id)
        status.recording_in_progress.value = False  # the take level completes its files after the join (7.4)
        status.should_close.value = True
        if worker is not None:
            worker.worker.terminate()
            worker.join(timeout=BOUNDED_JOIN_S)
        status.update_info(failure=dict(camera_id=camera_id, stage="recording", reason="disk stall"))
        status.set_state("failed")
        logger.error(f"Camera {camera_id} failed during recording: disk stall")

    async def close(self) -> None:
        logger.debug("Closing camera group")

        if self.take is not None:  # the take, not the status flags: a hard-ended process leaves its flag set
            logger.info("Recording in progress — stopping recording before closing cameras")
            try:
                await self.stop_recording()
            except Exception as e:
                logger.error(f"Error stopping recording during close: {type(e).__name__} - {e}")

        self._stop_watch.set()
        self.ipc.should_continue = False
        with self._ring_lock:
            for ring in self.rings.values():
                ring.set_closed()
        self.cameras.close()

        try:
            with self._ring_lock:
                self._close_rings(list(self.rings))
        except Exception as e:
            logger.error(f"Error closing the frame rings: {type(e).__name__} - {e}")
        logger.success("Frame rings closed and unlinked.")

        logger.success("Camera group closed successfully.")

    def to_state(self) -> CameraGroupState:
        orchestrator = self.cameras.orchestrator
        return CameraGroupState(
            id=self.id,
            configs=self.configs,
            cameras={
                camera_id: worker.to_state()
                for camera_id, worker in self.cameras.camera_workers.items()
            },
            alive=self.alive,
            recording_in_progress=orchestrator.all_cameras_recording,
            paused=orchestrator.any_cameras_paused,
        )
