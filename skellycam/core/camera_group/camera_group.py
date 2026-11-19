import logging
import threading
import time

from skellycam.core.camera_group.camera_setup_failure import CameraSetupFailedException
from multiprocessing.sharedctypes import Synchronized
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict

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
    RecordingFinishedMessage,
)
from skellycam.core.ipc.frame_ring import (
    CameraRingInfo,
    FrameRead,
    FrameRingCreator,
    FrameRingReader,
    ReadResult,
    camera_ring_info,
    create_session_rings,
    sweep_stale_rings,
)
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
from skellycam.core.recorders.recording_finalizer import RecordingFinalizer
from skellycam.core.recorders.audio.audio_recorder import AudioRecorder
from skellycam.core.recorders.videos.recording_info import RecordingInfo
from skellycam.core.timestamps.recording_timestamp_stats import RecordingTimestampsStats
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
from skellycam.utilities.wait_functions import await_100ms, await_10ms

logger = logging.getLogger(__name__)

WATCH_INTERVAL_S = 0.1
GIVE_UP_AFTER_EXIT_S = 1.0  # the files message of an ended camera process can still be in the queue


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
    capture_info: dict = field(default_factory=dict)
    _audio_recorder: AudioRecorder | None = None
    _ring_lock: Any = field(default_factory=threading.RLock)
    _stop_watch: Any = field(default_factory=threading.Event)

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

        A camera of the request that is not in the group is left out, as before phase 3.
        """
        statuses = self.cameras.orchestrator.camera_statuses
        restart, changed, removed = [], {}, []
        for camera_id, config in requested.items():
            if camera_id not in self.configs:
                continue
            worker = self.cameras.camera_workers.get(camera_id)
            if not config.use_this_camera:
                removed.append(camera_id)
            elif (statuses[camera_id].state in ("failed", "dead") or worker is None
                  or worker.worker.exitcode is not None):
                restart.append(camera_id)
            elif not same_config(config, self.configs[camera_id]):
                changed[camera_id] = config
        for camera_id in removed:
            self.cameras.remove_camera(camera_id)
            with self._ring_lock:
                self._close_rings([camera_id])
            del self.configs[camera_id]
        for camera_id in restart:
            with self._ring_lock:
                self._close_rings([camera_id])
            self.cameras.restart_camera(camera_id, requested[camera_id])
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
            while self.ipc.take_setup_failure() is not None:
                pass  # the status of each camera holds its failure; keep the pipe empty
            for camera_id in list(pending):
                worker = self.cameras.camera_workers.get(camera_id)
                if (statuses[camera_id].state in ("failed", "dead") or worker is None
                        or worker.worker.exitcode is not None):
                    pending.discard(camera_id)
            await await_10ms()
        return configs, warnings

    async def _await_settled(self, camera_ids: list) -> None:
        """Wait until each camera has passed its rate check or failed (9.1, 10.1)."""
        statuses = self.cameras.orchestrator.camera_statuses
        while self.ipc.should_continue:
            pending = [camera_id for camera_id in camera_ids if camera_id in statuses
                       and statuses[camera_id].state not in SETTLED_STATES
                       and self.cameras.camera_workers[camera_id].worker.exitcode is None]
            if not pending:
                return
            await await_10ms()

    def _failures(self, camera_ids: list) -> dict:
        statuses = self.cameras.orchestrator.camera_statuses
        return {camera_id: statuses[camera_id].info_dict().get("failure") for camera_id in camera_ids
                if camera_id in statuses and statuses[camera_id].state in ("failed", "dead")
                and statuses[camera_id].info_dict().get("failure")}

    def _watch_workers(self) -> None:
        """6.6: the main process cleans up only the camera whose process ended: its rings (D10)."""
        while not self._stop_watch.wait(WATCH_INTERVAL_S):
            for camera_id, worker in list(self.cameras.camera_workers.items()):
                if worker.worker.exitcode is not None and camera_id in self.rings:
                    logger.info(f"The process of camera {camera_id} ended; its rings close")
                    with self._ring_lock:
                        self._close_rings([camera_id])

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

    async def start_recording(self, recording_info: RecordingInfo) -> list:
        """Start recording for the camera group. Return the warnings of 11.3."""
        statuses = self.cameras.orchestrator.camera_statuses
        blocking = [f"camera {camera_id} is {status.serialize()['state']}"
                    for camera_id, status in list(statuses.items())
                    if status.state is not None and not status.ready]  # None: the phase 2 loop
        if blocking:  # a recording starts only when each selected camera is `ready` (8.3, agent 25)
            raise RequestRefused(409, "A recording needs each selected camera ready: " + "; ".join(blocking))
        warnings, self.capture_info = [], {}
        for camera_id, status in list(statuses.items()):
            info = status.info_dict()
            controls = info.get("controls") or {}
            # 3a sets exposure only; gain and focus come through the config from 3c (D30, D43)
            auto = [name for name in ("exposure",) if (controls.get(name) or {}).get("auto")]
            items = [dict(kind="auto_control", camera_ids=[camera_id], control=name,
                          text=f"Camera {camera_id}: {name} is in auto mode at the start of the recording")
                     for name in auto]
            status.set_warning_items(items)
            warnings += items
            # interim recording info of 11.6, until the capture info of phase 5
            self.capture_info[camera_id] = dict(
                source=info.get("source"), mode=info.get("mode"),
                controls_at_start={name: dict(auto=value["auto"], value=value["value"])
                                   for name, value in controls.items() if value.get("present")},
                auto_controls_at_start=auto, input_range=None)
        self.recording_ids = list(statuses)
        await self.cameras.pause(await_paused=True)
        logger.info("Publishing recording info message...")
        frame_count = self.cameras.orchestrator.largest_gate_count()
        self.cameras.orchestrator.last_recording_frame_number.value = -1
        self.cameras.orchestrator.first_recording_frame_number.value = frame_count + 3
        self.ipc.pubsub.topics[TopicTypes.RECORDING_INFO].publish(
            RecordingInfoMessage(recording_info=recording_info)
        )

        # Start audio recording if a microphone is selected
        if recording_info.mic_device_index >= 0:
            self._audio_recorder = AudioRecorder(
                audio_file_path=recording_info.audio_file_path,
                mic_device_index=recording_info.mic_device_index,
                timebase_mapping=self.ipc.timebase_mapping,
            )
            self._audio_recorder.start()
            logger.info(f"Audio recording started (mic device {recording_info.mic_device_index})")

        await await_10ms()
        await self.cameras.unpause(await_unpaused=True)
        for item in warnings:
            logger.warning(item["text"])
        logger.info(
            f"Started recording for camera group ID: {self.id} "
            f"with recording name: {recording_info.recording_name}"
        )
        return warnings

    async def stop_recording(self) -> tuple[RecordingInfo, RecordingTimestampsStats]:
        """Stop recording for the camera group."""
        logger.debug("Stopping recording for all cameras in orchestrator...")
        await self.cameras.pause(await_paused=True)

        # Stop audio before finalizing video
        if self._audio_recorder is not None:
            self._audio_recorder.stop()
            logger.info("Audio recording stopped.")
            self._audio_recorder = None

        frame_count = self.cameras.orchestrator.largest_gate_count()
        self.cameras.orchestrator.first_recording_frame_number.value = -1
        self.cameras.orchestrator.last_recording_frame_number.value = frame_count + 3
        await self.cameras.unpause(await_unpaused=True)
        try:
            recording_info, timestamp_stats = await finalize_recording(
                ipc=self.ipc, cameras=self.cameras, camera_configs=self.configs,
                recording_ids=self.recording_ids, capture_info=self.capture_info)
        finally:
            for status in list(self.cameras.orchestrator.camera_statuses.values()):
                status.set_warning_items([])
        logger.info(
            f"Stopped recording for camera group ID: {self.id} "
            f"with recording name: {recording_info.recording_name}"
        )
        return recording_info, timestamp_stats

    async def close(self) -> None:
        logger.debug("Closing camera group")

        if any(
            status.recording_in_progress.value
            for status in self.cameras.orchestrator.camera_statuses.values()
        ):
            logger.info("Recording in progress — stopping recording before closing cameras")
            try:
                await self.stop_recording()
            except Exception as e:
                logger.error(f"Error stopping recording during close: {type(e).__name__} - {e}")

        # Stop audio if still running (e.g. error during stop_recording)
        if self._audio_recorder is not None:
            try:
                self._audio_recorder.stop()
            except Exception as e:
                logger.error(f"Error stopping audio during close: {type(e).__name__} - {e}")
            self._audio_recorder = None

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


async def await_extracted_configs(
    ipc: CameraGroupIPC,
    requested_configs: CameraConfigs,
) -> CameraConfigs:
    updated_configs: dict[CameraIdString, CameraConfig | None] = {
        camera_id: None for camera_id in requested_configs.keys()
    }
    while (
        any(not isinstance(config, CameraConfig) for config in updated_configs.values())
        and ipc.should_continue
    ):
        if not ipc.extracted_config_subscription.empty():
            extracted_config_message = ipc.extracted_config_subscription.get()
            if not isinstance(extracted_config_message, DeviceExtractedConfigMessage):
                raise RuntimeError(
                    f"Received unexpected message type: {type(extracted_config_message)}"
                )
            updated_configs[
                extracted_config_message.extracted_config.camera_id
            ] = extracted_config_message.extracted_config
        await await_100ms()
        failure = ipc.take_setup_failure()  # a failure no longer stops the group (D23), so stop here
        if failure is not None:
            raise CameraSetupFailedException(str(failure))

    failure = ipc.take_setup_failure()
    if failure is not None:
        raise CameraSetupFailedException(str(failure))
    missing = [camera_id for camera_id, config in updated_configs.items() if config is None]
    if missing or not ipc.should_continue:
        raise CameraSetupFailedException(
            f"Camera group startup/update aborted; cameras without configurations: {missing}"
        )
    validate_camera_configs(updated_configs)

    return updated_configs


async def finalize_recording(
    ipc: CameraGroupIPC,
    cameras: CameraManager,
    camera_configs: CameraConfigs,
    recording_ids: list,
    capture_info: dict,
) -> tuple[RecordingInfo, RecordingTimestampsStats]:
    """Wait for the files of each recording camera. A camera process that ended without its files
    message is left out (interim U12, removed in phase 5). A dead camera is named in the recording info (5.7)."""
    messages: dict[CameraIdString, RecordingFinishedMessage] = {}
    pending, ended_since = set(recording_ids), {}
    while pending and ipc.should_continue:
        while not ipc.recording_finished_subscription.empty():
            message = ipc.recording_finished_subscription.get()
            if not isinstance(message, RecordingFinishedMessage):
                raise RuntimeError(f"Received unexpected message type: {type(message)}")
            if message.camera_id in messages:
                raise RuntimeError(f"Received multiple recording finished messages for camera {message.camera_id}.")
            messages[message.camera_id] = message
            pending.discard(message.camera_id)
        now = time.monotonic()
        for camera_id in list(pending):
            worker = cameras.camera_workers.get(camera_id)
            if worker is None or worker.worker.exitcode is not None:
                if now - ended_since.setdefault(camera_id, now) > GIVE_UP_AFTER_EXIT_S:
                    logger.error(f"Camera {camera_id} ended without finishing its recording files")
                    pending.discard(camera_id)
        await await_100ms()

    if not messages:
        raise RuntimeError("No camera finished its recording.")
    infos = {message.recording_info.recording_name for message in messages.values()}
    if len(infos) > 1:
        raise RuntimeError(f"Received recording finished messages of different recordings: {infos}")
    recording_info = next(iter(messages.values())).recording_info
    statuses = cameras.orchestrator.camera_statuses
    dead_cameras = []
    for camera_id in recording_ids:
        status = statuses.get(camera_id)
        if camera_id in messages and status is not None and status.state not in ("dead", "failed"):
            continue
        failure = (status.info_dict().get("failure") if status is not None else None) or {}
        last = messages[camera_id].frame_metadatas[-1].frame_number[0] if camera_id in messages else None
        dead_cameras.append(dict(camera_id=camera_id, last_frame_number=None if last is None else int(last),
                                 stage=failure.get("stage"), reason=failure.get("reason")))

    recording_finalizer = RecordingFinalizer.create(
        recording_info=recording_info,
        camera_configs={camera_id: camera_configs[camera_id] for camera_id in messages},
        frame_metadatas_by_camera={camera_id: message.frame_metadatas for camera_id, message in messages.items()},
        capture=capture_info,
        dead_cameras=dead_cameras,
    )
    timestamp_stats = await recording_finalizer.finalize_recording()
    return recording_info, timestamp_stats
