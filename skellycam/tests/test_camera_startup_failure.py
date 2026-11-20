"""Startup aborts must preserve the worker error across the process boundary.

Two tests of the phase 2 helper `await_extracted_configs` are retired with it (ADR-037V): a camera
process that ends with no final state gets `failed` with its exit code (T-CAP-109), and the apply
response gives the config that each camera read back (T-CAP-41)."""
import asyncio
import multiprocessing
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC

from skellycam.core.camera_group.camera_setup_failure import CameraSetupFailure, CameraSetupFailedException
from skellycam.core.ipc.pubsub.pubsub_manager import PubSubTopicManager
from skellycam.core.camera_group.camera_group_manager import CameraGroupManager
from skellycam.core.camera_group.camera_group import CameraGroup
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry


@pytest.fixture
def ipc():
    value = CameraGroupIPC(
        group_id='test', pubsub=PubSubTopicManager(topics={}),
        extracted_config_subscription=multiprocessing.Queue(),
        recording_finished_subscription=multiprocessing.Queue(),
        global_kill_flag=multiprocessing.Value('b', False),
        heartbeat_timestamp=multiprocessing.Value('d', time.perf_counter()),
    )
    yield value
    value.setup_failures.close()
    value.extracted_config_subscription.close()
    value.extracted_config_subscription.join_thread()
    value.recording_finished_subscription.close()
    value.recording_finished_subscription.join_thread()


def _worker_reports_failure(ipc):
    # spec 12: camera_id, stage, reason; the reason of an exception is `{type}: {message}`
    ipc.report_setup_failure(CameraSetupFailure('1622', 'opening camera', 'FailedToOpenCameraException: access denied'))
    ipc.report_setup_failure(CameraSetupFailure('sibling', 'shared memory', 'RuntimeError: group stopped'))


def test_spawned_worker_failure_survives_shutdown(ipc):
    process = multiprocessing.Process(target=_worker_reports_failure, args=(ipc,))
    process.start()
    try:
        process.join(15)
        assert process.exitcode == 0
        assert not ipc.global_kill_flag.value
        # the first failure stays (spec 12); the main process reads it after the worker ended
        assert str(ipc.take_setup_failure()) == 'Camera 1622 failed during opening camera: FailedToOpenCameraException: access denied'
    finally:
        if process.is_alive():
            process.terminate()
            process.join()


def test_failed_group_cleanup_preserves_failure_and_allows_retry():
    registry = Mock(spec=WorkerRegistry)
    registry.heartbeat_timestamp = multiprocessing.Value('d', time.perf_counter())
    manager = CameraGroupManager(global_kill_flag=multiprocessing.Value('b', False), worker_registry=registry)
    failed = Mock(spec=CameraGroup, id='failed', ipc=Mock())
    failed.ipc.pubsub.get_subscription.return_value = multiprocessing.Queue()
    failure = CameraSetupFailedException('Camera 1622 failed opening: access denied')
    failed.start = AsyncMock(side_effect=failure)
    failed.close = AsyncMock()
    healthy = Mock(spec=CameraGroup, id='retry', ipc=Mock(), camera_ids=['1622'])
    healthy.ipc.pubsub.get_subscription.return_value = multiprocessing.Queue()
    healthy.start = AsyncMock()
    configs = {'1622': CameraConfig(camera_id='1622', camera_index=0)}
    try:
        with patch.object(CameraGroup, 'create', side_effect=[failed, healthy]):
            with pytest.raises(CameraSetupFailedException) as caught:
                asyncio.run(manager.create_and_start_camera_group(configs))
            assert caught.value is failure
            failed.close.assert_awaited_once()
            assert not manager.camera_groups
            assert not manager.camera_group_framerate_subscriptions
            assert asyncio.run(manager.create_and_start_camera_group(configs)) is healthy
    finally:
        failed.ipc.pubsub.get_subscription.return_value.close()
        healthy.ipc.pubsub.get_subscription.return_value.close()


def test_worker_setup_reports_original_open_error(monkeypatch):
    """The shared loop with the OpenCV source: an open that raises gives the camera `failed`, stage
    `open`, with the type and the text of the original error in the apply response (spec 12). The
    application does not stop (D23)."""
    import skellycam.core.camera.capture.opencv_source as opencv_source
    from skellycam.core.camera.opencv.opencv_helpers.create_cv2_video_capture import FailedToOpenCameraException
    from skellycam.tests.capture.capture_session import CaptureApp, OpenCVFakeFactory

    def refuse(config):
        raise FailedToOpenCameraException('camera access denied')

    factory = OpenCVFakeFactory(monkeypatch)
    monkeypatch.setattr(opencv_source, 'create_cv2_video_capture', refuse)
    app = CaptureApp(monkeypatch, factory)
    try:
        app.detect()
        camera_id = factory.camera_ids[0]
        response = app.apply([app.config(camera_id)])
        assert response.status_code == 200, response.text
        app.wait_state(camera_id, 'failed')
        failure = {'camera_id': camera_id, 'stage': 'open', 'reason': 'FailedToOpenCameraException: camera access denied'}
        assert response.json()['camera_failures'][camera_id] == failure
        assert app.status(camera_id)['failure'] == failure
        assert not app.kill.value
    finally:
        app.close()


def test_exhausted_open_retries_report_device_backend_and_release_capture():
    from skellycam.core.camera.opencv.opencv_helpers.create_cv2_video_capture import create_cv2_video_capture, FailedToOpenCameraException
    from skellycam.core.camera.determine_backend import OpenCVBackend
    class ClosedCapture:
        release = Mock()

        def __init__(self, *args):
            pass

        def isOpened(self):
            return False

    with patch('skellycam.core.camera.opencv.opencv_helpers.create_cv2_video_capture.cv2.VideoCapture', ClosedCapture), \
         patch('skellycam.core.camera.opencv.opencv_helpers.create_cv2_video_capture.determine_opencv_camera_backend',
               return_value=OpenCVBackend(1200, 'AVFOUNDATION')):
        with pytest.raises(FailedToOpenCameraException, match='1622.*index 0.*AVFOUNDATION.*1 attempts'):
            create_cv2_video_capture(CameraConfig(camera_id='1622', camera_index=0), retry_count=0)
    ClosedCapture.release.assert_called_once()


def test_verbose_failure_is_bounded_and_does_not_block_shutdown(ipc):
    ipc.report_setup_failure(CameraSetupFailure('1622', 'opening camera', 'RuntimeError: ' + '💀' * 100000))
    failure = ipc.take_setup_failure()
    assert failure.camera_id == '1622'
    assert failure.reason.startswith('RuntimeError: ') and len(failure.reason.encode('utf-8')) <= 2048
    # spec 12, D23: a start failure does not set the shutdown flag; the other cameras stay open
    assert not ipc.shutdown_camera_group_flag.value
    assert not ipc.global_kill_flag.value
