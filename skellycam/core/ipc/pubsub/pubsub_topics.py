from dataclasses import dataclass
from typing import Type

from skellylogs import LogRecordModel, get_websocket_log_queue

from skellycam.core.camera.config.camera_config import CameraConfig, CameraConfigs
from skellycam.core.ipc.frame_ring import CameraRingInfo
from skellycam.core.ipc.pubsub.pubsub_abcs import TopicMessageABC, PubSubTopicABC
from skellycam.core.recorders.framerate_tracker import CurrentFramerate
from skellycam.core.take_recorder import CameraTakeResult, CameraTakeSpec
from skellycam.core.types.type_overloads import TopicPublicationQueue, CameraIdString

@dataclass
class DeviceExtractedConfigMessage(TopicMessageABC):
    extracted_config: CameraConfig
    control_change_failed: str | None = None  # the text of a failed live change (11.2, U14)


@dataclass
class UpdateCamerasSettingsMessage(TopicMessageABC):
    requested_configs: CameraConfigs


@dataclass
class SetShmMessage(TopicMessageABC):
    ring_infos: dict[CameraIdString, CameraRingInfo]

@dataclass
class RecordingInfoMessage(TopicMessageABC):
    """The start of a take: the camera spec of each camera (recorder.md section 10 item 5)."""
    take_specs: dict[CameraIdString, CameraTakeSpec]


@dataclass
class RecordingFinishedMessage(TopicMessageABC):
    """The result of a camera writer at the end of a take, or the error that ends the take (recorder.md 5.3,
    5.4): `result` is None and `error` holds the text."""
    camera_id: CameraIdString
    result: CameraTakeResult | None = None
    error: str | None = None

@dataclass
class DiagnosticsMessage(TopicMessageABC):
    """The diagnostics of one camera (unix-capture.md 4.2 item 2): one time per second, at the end of the open,
    at a failure and at the close. The main process keeps the newest of each camera."""
    camera_id: CameraIdString
    diagnostics: dict


@dataclass
class FramerateMessage(TopicMessageABC):
    current_framerate: CurrentFramerate


@dataclass
class UpdateCamerasSettingsTopic(PubSubTopicABC):
    message_type: Type[UpdateCamerasSettingsMessage] = UpdateCamerasSettingsMessage


@dataclass
class DeviceExtractedConfigTopic(PubSubTopicABC):
    message_type: Type[DeviceExtractedConfigMessage] = DeviceExtractedConfigMessage


@dataclass
class SetShmTopic(PubSubTopicABC):
    message_type: Type[SetShmMessage] = SetShmMessage



@dataclass
class RecordingInfoTopic(PubSubTopicABC):
    message_type: Type[RecordingInfoMessage] = RecordingInfoMessage


@dataclass
class RecordingFinishedTopic(PubSubTopicABC):
    message_type: Type[RecordingFinishedMessage] = RecordingFinishedMessage


@dataclass
class DiagnosticsTopic(PubSubTopicABC):
    message_type: Type[DiagnosticsMessage] = DiagnosticsMessage


@dataclass
class FramerateTopic(PubSubTopicABC):
    message_type: Type[FramerateMessage] = FramerateMessage


@dataclass
class LogsTopic(PubSubTopicABC):
    message_type: Type[LogRecordModel] = LogRecordModel
    publication: TopicPublicationQueue = None

    def __post_init__(self) -> None:
        if self.publication is None:
            self.publication = get_websocket_log_queue()
