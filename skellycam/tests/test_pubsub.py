"""Tests for the PubSub IPC system — topic management, publish/subscribe, type safety."""
import queue
import time

import numpy as np
import pytest
from beartype.roar import BeartypeCallHintParamViolation

from skellycam.core.ipc.pubsub.pubsub_abcs import TopicMessageABC, PubSubTopicABC
from skellycam.core.ipc.pubsub.pubsub_manager import (
    PubSubTopicManager,
    TopicTypes,
)
from skellycam.core.ipc.pubsub.pubsub_topics import (
    UpdateCamerasSettingsMessage,
    DeviceExtractedConfigMessage,
    RecordingInfoMessage,
    RecordingFinishedMessage,
    FramerateMessage,
    SetShmMessage,
)
from skellycam.core.camera.config.camera_config import CameraConfig, DEFAULT_CAMERA_ID
from skellycam.core.take_recorder import CameraTakeSpec
from skellycam.core.recorders.framerate_tracker import CurrentFramerate


# multiprocessing.Queue.put() hands data to a background feeder thread,
# so queue.empty() can race and return True immediately after put().
# Always use queue.get(timeout=...) instead of checking empty() first.
GET_TIMEOUT: float = 2.0


def take_spec(camera_id: str) -> CameraTakeSpec:
    """A camera spec of a take, as the record start sends it (recorder.md section 10 item 5)."""
    from pathlib import Path

    return CameraTakeSpec(camera_id=camera_id, mkv_path=Path(f"{camera_id}.mkv"), csv_path=Path(f"{camera_id}.csv"),
                          header=(), take_start_host_ns=0, num=30, den=1, width=640, height=480, layout=None,
                          queue_size=90, stall_limit_s=10.0)


# ---------------------------------------------------------------------------
# PubSubTopicManager
# ---------------------------------------------------------------------------

class TestPubSubTopicManager:
    def test_has_all_topic_types(self, manager) -> None:
        for topic_type in TopicTypes:
            assert topic_type in manager.topics

    def test_subscribe_returns_queue(self, manager) -> None:
        sub = manager.get_subscription(TopicTypes.FRAMERATE)
        assert sub is not None
        assert hasattr(sub, "get")
        assert hasattr(sub, "put")

    def test_subscribe_unknown_topic_raises(self, manager) -> None:
        with pytest.raises(BeartypeCallHintParamViolation, match="TopicTypes"):
            manager.get_subscription("not_a_real_topic")  # type: ignore[arg-type]

    def test_close_clears_topics(self, manager) -> None:
        manager.get_subscription(TopicTypes.FRAMERATE)
        manager.close()
        assert len(manager.topics) == 0


# ---------------------------------------------------------------------------
# Publish / Subscribe Integration
# ---------------------------------------------------------------------------

class TestPubSubPublishSubscribe:
    def test_publish_delivers_to_subscriber(self, manager) -> None:
        sub = manager.get_subscription(TopicTypes.UPDATE_CAMERA_SETTINGS)

        configs = {DEFAULT_CAMERA_ID: CameraConfig()}
        msg = UpdateCamerasSettingsMessage(requested_configs=configs)
        manager.topics[TopicTypes.UPDATE_CAMERA_SETTINGS].publish(msg)

        # Use get(timeout=) instead of checking empty() — the feeder thread
        # may not have flushed the data to the pipe yet when empty() is called.
        received = sub.get(timeout=GET_TIMEOUT)
        assert isinstance(received, UpdateCamerasSettingsMessage)
        assert DEFAULT_CAMERA_ID in received.requested_configs

    def test_publish_delivers_to_multiple_subscribers(self, manager) -> None:
        sub1 = manager.get_subscription(TopicTypes.EXTRACTED_CONFIG)
        sub2 = manager.get_subscription(TopicTypes.EXTRACTED_CONFIG)

        config = CameraConfig(camera_id="test_cam", camera_index=0)
        msg = DeviceExtractedConfigMessage(extracted_config=config)
        manager.topics[TopicTypes.EXTRACTED_CONFIG].publish(msg)

        r1 = sub1.get(timeout=GET_TIMEOUT)
        r2 = sub2.get(timeout=GET_TIMEOUT)
        assert r1.extracted_config.camera_id == "test_cam"
        assert r2.extracted_config.camera_id == "test_cam"

    def test_publish_wrong_type_raises(self, manager) -> None:
        manager.get_subscription(TopicTypes.FRAMERATE)

        wrong_msg = UpdateCamerasSettingsMessage(
            requested_configs={DEFAULT_CAMERA_ID: CameraConfig()}
        )
        with pytest.raises(TypeError, match="Expected"):
            manager.topics[TopicTypes.FRAMERATE].publish(wrong_msg)

    def test_publish_preserves_pending_messages_in_order(self, manager) -> None:
        subscribers = [manager.get_subscription(TopicTypes.RECORDING_INFO) for _ in range(2)]
        camera_ids = [format(index, "04x") for index in range(100)]
        messages = [RecordingInfoMessage(take_specs={camera_id: take_spec(camera_id)}) for camera_id in camera_ids]
        # Publish a burst without waiting for the multiprocessing feeder thread.
        for message in messages:
            manager.topics[TopicTypes.RECORDING_INFO].publish(message, print_log=False)
        for subscriber in subscribers:
            received = [next(iter(subscriber.get(timeout=GET_TIMEOUT).take_specs)) for _ in messages]
            assert received == camera_ids
            with pytest.raises(queue.Empty):
                subscriber.get(timeout=0.1)


# ---------------------------------------------------------------------------
# FramerateMessage
# ---------------------------------------------------------------------------

class TestFramerateMessage:
    def test_framerate_message_roundtrip(self) -> None:
        durations = np.array([33.0, 34.0, 33.5, 32.5, 33.0])
        fr = CurrentFramerate.from_durations_ms(
            durations_ms=durations,
            framerate_source="test",
        )
        msg = FramerateMessage(current_framerate=fr)
        assert msg.current_framerate.mean_frames_per_second > 0
        assert msg.current_framerate.framerate_source == "test"


# ---------------------------------------------------------------------------
# RecordingInfoMessage
# ---------------------------------------------------------------------------

class TestRecordingInfoMessage:
    def test_recording_info_message(self) -> None:
        msg = RecordingInfoMessage(take_specs={"a1b2": take_spec("a1b2")})
        assert msg.take_specs["a1b2"].camera_id == "a1b2"


@pytest.fixture
def manager(logging_runtime):
    manager = PubSubTopicManager()
    yield manager
    manager.close()
