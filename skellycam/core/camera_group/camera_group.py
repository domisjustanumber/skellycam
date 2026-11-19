import logging

from skellycam.core.camera_group.camera_setup_failure import CameraSetupFailedException
import multiprocessing
from multiprocessing.sharedctypes import Synchronized
from dataclasses import dataclass, field

import numpy as np
from pydantic import BaseModel, ConfigDict

from skellycam.core.camera.camera_manager import CameraManager
from skellycam.core.camera.camera_worker import CameraState
from skellycam.core.camera.config.camera_config import CameraConfigs, CameraConfig, validate_camera_configs
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
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
from skellycam.core.camera_group.camera_status import CameraStatus

logger = logging.getLogger(__name__)


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
    _audio_recorder: AudioRecorder | None = None

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
            )
        except Exception as e:
            logger.error(f"Error creating camera group: {type(e).__name__} - {e}")
            global_kill_flag.value = True
            raise

        return cls(
            ipc=ipc,
            cameras=cameras,
            configs=camera_configs,
        )

    async def start(self) -> CameraConfigs:
        self.started = True
        logger.info(f"Starting camera group ID: {self.id} with cameras: {list(self.configs.keys())}")
        self.cameras.start()
        logger.debug("Awaiting extracted configs so we can create the frame rings...")
        extracted_configs: CameraConfigs = await await_extracted_configs(
            ipc=self.ipc, requested_configs=self.configs
        )
        sweep_stale_rings()
        self._open_rings(extracted_configs)
        self.configs = extracted_configs
        return extracted_configs

    def _open_rings(self, configs: CameraConfigs) -> None:
        """Create the ring of each camera in `configs`, attach a reader, and give the ring names to
        the camera processes (spec 7.1 and 7.3)."""
        for camera_id, ring in create_session_rings(configs).items():
            self.rings[camera_id] = ring
            self.ring_readers[camera_id] = FrameRingReader.attach(ring.name)
        self._update_ring_infos(configs)
        self.ipc.publish_shm_message(ring_infos=self.ring_infos)

    def _update_ring_infos(self, configs: CameraConfigs) -> None:
        self.ring_infos.update({camera_id: camera_ring_info(config, self.rings[camera_id])
                                for camera_id, config in configs.items()})

    def _close_rings(self, camera_ids: list[CameraIdString]) -> None:
        """Close the reader, then set `closed`, close and unlink the ring of each camera (spec 7.4).

        A writer that has not detached keeps the block: a POSIX mapping stays after an unlink, and
        Windows frees the block when its last handle closes (spec 7.7)."""
        for camera_id in camera_ids:
            self.ring_readers.pop(camera_id).close()
            self.rings.pop(camera_id).close_and_unlink()

    @property
    def camera_ids(self) -> list[CameraIdString]:
        return list(self.configs.keys())

    def read_latest_ring_frames(self) -> dict[CameraIdString, FrameRead] | None:
        """The ring frame of each camera at the newest frame number that all cameras have [A4]."""
        if not self.ring_readers or not self.cameras.all_ready:
            return None
        newest = {camera_id: reader.read_newest() for camera_id, reader in self.ring_readers.items()}
        if any(read.result is not ReadResult.OK for read in newest.values()):
            return None
        frame_number = min(read.frame_number for read in newest.values())
        reads = {camera_id: read if read.frame_number == frame_number
                 else self.ring_readers[camera_id].read(frame_number)
                 for camera_id, read in newest.items()}
        if any(read.result is not ReadResult.OK for read in reads.values()):
            return None
        return reads

    def get_latest_ring_payload(self) -> tuple[FrameNumberInt, MultiframeTimestampFloat, memoryview] | None:
        """A websocket message in the wire format of today, with the ring JPEG of each camera,
        untouched: no resize, no re-encode and no rotation (spec 2.3) [A4]."""
        reads = self.read_latest_ring_frames()
        if reads is None:
            return None
        frame_number = next(iter(reads.values())).frame_number
        header = np.zeros(1, dtype=FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE)
        header["message_type"] = MessageType.PAYLOAD_HEADER
        header["frame_number"] = frame_number
        header["number_of_cameras"] = len(reads)
        payload = bytearray(header.tobytes())
        for camera_id, read in reads.items():
            info = self.ring_infos[camera_id]
            frame_header = np.zeros(1, dtype=FRONTEND_FRAME_HEADER_DTYPE)
            frame_header["message_type"] = MessageType.FRAME_HEADER
            frame_header["frame_number"] = frame_number
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

    async def update_camera_settings(self, requested_configs: CameraConfigs) -> CameraConfigs:
        """Update camera settings and await the extracted configurations."""
        self.ipc.pubsub.topics[TopicTypes.UPDATE_CAMERA_SETTINGS].publish(
            UpdateCamerasSettingsMessage(requested_configs=requested_configs)
        )
        updated_configs = await await_extracted_configs(
            ipc=self.ipc, requested_configs=requested_configs
        )
        changed = {camera_id: config for camera_id, config in updated_configs.items()
                   if (config.resolution, config.framerate)
                   != (self.configs[camera_id].resolution, self.configs[camera_id].framerate)}
        if changed:
            # A new mode gets a new ring under a new name (spec 7.5).
            self._close_rings(list(changed))
            self._open_rings(changed)
        self._update_ring_infos(updated_configs)
        self.configs = updated_configs
        logger.info(f"Updated camera configs - {list(requested_configs.keys())}")
        return self.configs

    async def start_recording(self, recording_info: RecordingInfo) -> None:
        """Start recording for the camera group."""
        await self.cameras.pause(await_paused=True)
        logger.info("Publishing recording info message...")
        frame_count = max(
            status.frame_count.value
            for status in self.cameras.orchestrator.camera_statuses.values()
        )
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
        logger.info("Camera group unpaused - Recording successfully started.")
        logger.info(
            f"Started recording for camera group ID: {self.id} "
            f"with recording name: {recording_info.recording_name}"
        )

    async def stop_recording(self) -> tuple[RecordingInfo, RecordingTimestampsStats]:
        """Stop recording for the camera group."""
        logger.debug("Stopping recording for all cameras in orchestrator...")
        await self.cameras.pause(await_paused=True)

        # Stop audio before finalizing video
        if self._audio_recorder is not None:
            self._audio_recorder.stop()
            logger.info("Audio recording stopped.")
            self._audio_recorder = None

        frame_count = max(
            status.frame_count.value
            for status in self.cameras.orchestrator.camera_statuses.values()
        )
        self.cameras.orchestrator.first_recording_frame_number.value = -1
        self.cameras.orchestrator.last_recording_frame_number.value = frame_count + 3
        await self.cameras.unpause(await_unpaused=True)
        recording_info, timestamp_stats = await finalize_recording(ipc=self.ipc, cameras=self.cameras, camera_configs=self.configs)
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

        self.ipc.should_continue = False
        for ring in self.rings.values():
            ring.set_closed()
        self.cameras.close()

        try:
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
) -> tuple[RecordingInfo, RecordingTimestampsStats]:
    recording_finished_messages_by_camera: dict[CameraIdString, RecordingFinishedMessage | None] = {
        camera_id: None
        for camera_id in cameras.orchestrator.camera_statuses.keys()
    }
    recording_info: RecordingInfo | None = None

    while (
        any(
            not isinstance(response, RecordingFinishedMessage)
            for response in recording_finished_messages_by_camera.values()
        )
        and ipc.should_continue
    ):
        if not ipc.recording_finished_subscription.empty():
            recording_finished_message = ipc.recording_finished_subscription.get()
            if not isinstance(recording_finished_message, RecordingFinishedMessage):
                raise RuntimeError(
                    f"Received unexpected message type: {type(recording_finished_message)}"
                )

            if recording_finished_messages_by_camera[recording_finished_message.camera_id] is not None:
                raise RuntimeError(
                    f"Received multiple recording finished messages for camera "
                    f"{recording_finished_message.camera_id}."
                )

            logger.debug(
                f"Received recording finished message for camera {recording_finished_message.camera_id}."
            )
            recording_finished_messages_by_camera[recording_finished_message.camera_id] = (
                recording_finished_message
            )
            if recording_info is None:
                recording_info = recording_finished_message.recording_info
            elif recording_info != recording_finished_message.recording_info:
                raise RuntimeError(
                    f"Received multiple recording info messages with different recording names: "
                    f"{recording_info.recording_name} and "
                    f"{recording_finished_message.recording_info.recording_name}"
                )
        await await_100ms()

    if not all(
        isinstance(response, RecordingFinishedMessage)
        for response in recording_finished_messages_by_camera.values()
    ):
        raise RuntimeError("Not all cameras finished recording successfully.")

    recording_finalizer = RecordingFinalizer.create(
        recording_info=recording_info,
        camera_configs=camera_configs,
        frame_metadatas_by_camera={
            camera_id: message.frame_metadatas
            for camera_id, message in recording_finished_messages_by_camera.items()
        },
    )
    timestamp_stats = await recording_finalizer.finalize_recording()
    return recording_info, timestamp_stats
