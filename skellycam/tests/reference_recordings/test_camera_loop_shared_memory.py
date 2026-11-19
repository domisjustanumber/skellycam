"""Real video -> production camera worker/loop -> frame ring, read by a separate reader."""

from contextlib import ExitStack, nullcontext
import logging
import multiprocessing
from multiprocessing import shared_memory
import time

import cv2
import numpy as np
import pytest

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
import skellycam.core.camera.opencv.opencv_camera_loop as loop_module
import skellycam.core.camera.opencv.opencv_camera_worker_method as worker_module
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.ipc.pubsub.pubsub_manager import PubSubTopicManager
from skellycam.core.ipc.frame_ring import FrameRingCreator, FrameRingReader, FrameRingWriter, PixelFormat, ReadResult
from skellycam.core.types.frame_dtype_factories import create_frame_dtype
from skellycam.tests.reference_recordings.datasets import TEST, acquire


@pytest.fixture(scope="module")
def test_videos():
    return acquire(TEST)


@pytest.mark.real_data
@pytest.mark.parametrize("camera_index", [0, 1, 2])
@pytest.mark.parametrize("ending", ["requested-stop", "eof-failure"])
def test_video_camera_loop_publishes_frames_and_cleans_up(test_videos, camera_index, ending, monkeypatch):
    monkeypatch.setattr(logging.Logger, "trace", logging.Logger.debug, raising=False)

    def forbid_hardware_reopen(*args, **kwargs):
        pytest.fail("File replay unexpectedly attempted to reopen a physical camera")

    monkeypatch.setattr(loop_module, "create_cv2_video_capture", forbid_hardware_reopen)
    names = []
    with ExitStack() as cleanup:
        capture = cv2.VideoCapture(str(test_videos[camera_index]), cv2.CAP_FFMPEG)
        cleanup.callback(capture.release)
        baseline = cv2.VideoCapture(str(test_videos[camera_index]), cv2.CAP_FFMPEG)
        cleanup.callback(baseline.release)
        assert capture.isOpened() and baseline.isOpened()
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        assert (width, height) == (720, 1280)
        config = CameraConfig(
            camera_id=f"reference-camera-{camera_index}", camera_index=camera_index,
            resolution=ImageResolution(width=width, height=height),
        )
        frame = np.zeros(1, dtype=create_frame_dtype(config)).view(np.recarray)
        frame.frame_metadata.camera_info = config.to_frame_camera_info()[0]
        frame.frame_metadata.frame_number[0] = -1
        owner = FrameRingCreator.create(  # 4 slots
            camera_id=config.camera_id, camera_index=camera_index, pixel_format=PixelFormat.JPEG,
            width=width, height=height, fps_num=4, fps_den=1,
        )
        cleanup.callback(owner.close_and_unlink)
        names.append(owner.name)
        writer = FrameRingWriter.attach(owner.name)
        cleanup.callback(writer.close)
        reader = FrameRingReader.attach(owner.name)
        cleanup.callback(reader.close)
        updates = multiprocessing.Queue()
        cleanup.callback(updates.close)
        recording = multiprocessing.Queue()
        cleanup.callback(recording.close)
        ipc = CameraGroupIPC(
            group_id="reference-loop", pubsub=PubSubTopicManager(topics={}),
            extracted_config_subscription=updates, recording_finished_subscription=recording,
            global_kill_flag=multiprocessing.Value("b", False),
            heartbeat_timestamp=multiprocessing.Value("d", time.perf_counter()),
        )
        status = CameraStatus()
        status.connected.value = True
        orchestrator = CameraOrchestrator.from_statuses({config.camera_id: status})
        received = []
        paused_ticks = 0
        write = writer.write

        def publish_and_observe(payload, **kwargs):
            write(payload, **kwargs)
            number = len(received)
            read = reader.read(number)
            assert read.result is ReadResult.OK
            assert read.frame_number == kwargs["frame_number"] == number
            assert read.payload == payload
            ok, expected = baseline.read()
            assert ok, f"Baseline ended before published frame {number}"
            # The production capture helper overlays text within the first 80 rows. JPEG q90 (spec 2.3).
            actual = cv2.imdecode(np.frombuffer(read.payload, np.uint8), cv2.IMREAD_COLOR)
            assert float(np.abs(actual[80:].astype(np.int16) - expected[80:].astype(np.int16)).mean()) < 8
            stamps = frame.frame_metadata.timestamps
            assert read.arrival_ns == stamps.post_frame_grab_ns[0]
            assert 0 < stamps.pre_frame_grab_ns[0] <= stamps.post_frame_grab_ns[0]
            assert stamps.post_frame_grab_ns[0] <= stamps.pre_frame_retrieve_ns[0]
            assert stamps.pre_frame_retrieve_ns[0] <= stamps.post_frame_retrieve_ns[0]
            assert stamps.post_frame_retrieve_ns[0] <= stamps.pre_copy_to_camera_shm_ns[0]
            received.append(number)
            if number == 10:
                status.should_pause.value = True
            if number == TEST.frames - 1 and ending == "requested-stop":
                status.should_close.value = True

        def observe_pause_and_resume():
            nonlocal paused_ticks
            assert status.is_paused.value
            assert received == list(range(11))
            assert reader.read_newest().frame_number == 10
            assert int(capture.get(cv2.CAP_PROP_POS_FRAMES)) == 11
            paused_ticks += 1
            if paused_ticks == 3:
                status.should_pause.value = False

        def file_setup(**kwargs):
            assert kwargs["config"] is config
            return writer, config, capture, frame, None  # no BGR ring

        # Replace hardware setup and add synchronous observation/control hooks.
        # Capture, loop, orchestration, shared-memory copies and cleanup stay real.
        monkeypatch.setattr(worker_module, "setup_opencv_camera_loop", file_setup)
        monkeypatch.setattr(writer, "write", publish_and_observe)
        monkeypatch.setattr(loop_module, "wait_1ms", observe_pause_and_resume)
        outcome = (
            pytest.raises(RuntimeError, match="failed to capture a frame after 30 attempts")
            if ending == "eof-failure" else nullcontext()
        )
        with outcome:
            worker_module.opencv_camera_worker_method(
                camera_id=config.camera_id, config=config, ipc=ipc, orchestrator=orchestrator,
                update_camera_settings_subscription=updates, shm_subscription=updates,
                recording_info_subscription=recording,
            )
        assert received == list(range(TEST.frames))
        assert paused_ticks == 3
        assert not baseline.read()[0]
        assert reader.read_newest().frame_number == TEST.frames - 1
        assert reader.read(0).result is ReadResult.LAPPED
        assert status.closed.value and not status.connected.value
        assert bool(status.error.value) == (ending == "eof-failure")
        assert ipc.shutdown_camera_group_flag.value and not ipc.global_kill_flag.value
        assert not capture.isOpened()  # Production worker released it, before fallback cleanup.
        assert writer._shm.buf is None  # the production loop closed its ring handle
    assert not baseline.isOpened()
    for name in names:
        try:
            leaked = shared_memory.SharedMemory(name=name)
        except FileNotFoundError:
            continue
        leaked.close()
        pytest.fail(f"Shared-memory allocation leaked: {name}")
