"""Real file-backed OpenCV capture through the OpenCV source of the shared loop (`OpenCVSource.read_frame`)."""

import time
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from skellycam.core.camera.capture.source import CaptureRequest
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.types.frame_dtype_factories import create_frame_dtype
from skellycam.tests.reference_recordings.datasets import SAMPLE, TEST, acquire


def frame_buffer(width, height):
    config = CameraConfig(camera_id="replay", camera_index=0,
                          resolution=ImageResolution(width=width, height=height))
    frame = np.zeros(1, dtype=create_frame_dtype(config)).view(np.recarray)
    frame.frame_metadata.camera_info = config.to_frame_camera_info()[0]
    frame.frame_metadata.frame_number[0] = -1
    return frame


def open_source(monkeypatch, capture):
    """The product `OpenCVSource`, opened on `capture` in place of a camera."""
    import skellycam.core.camera.capture.opencv_source as opencv_source

    monkeypatch.setattr(opencv_source, "create_cv2_video_capture", lambda config: (capture, config))
    source = opencv_source.OpenCVSource(CameraConfig(camera_id="replay", camera_index=0))
    source.open(CaptureRequest(camera_id="replay", width=720, height=1280, framerate=30.0))
    return source


@pytest.fixture(scope="module", params=[TEST, pytest.param(SAMPLE, marks=pytest.mark.sample_data)],
                ids=["test-222", "sample-1108"])
def reference(request):
    dataset = request.param
    return dataset, acquire(dataset)


@pytest.mark.real_data
@pytest.mark.parametrize("camera_index", [0, 1, 2], ids=["camera1", "camera2", "camera3"])
def test_capture_matches_video_frames_and_stops_at_eof(reference, camera_index, monkeypatch):
    dataset, paths = reference
    path = paths[camera_index]
    capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    baseline = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    try:
        assert capture.isOpened() and baseline.isOpened()
        width, height = int(baseline.get(cv2.CAP_PROP_FRAME_WIDTH)), int(baseline.get(cv2.CAP_PROP_FRAME_HEIGHT))
        assert (width, height) == (720, 1280)
        source = open_source(monkeypatch, capture)
        previous_end = 0
        for index in range(dataset.frames):
            expected_ok, expected = baseline.read()
            assert expected_ok, f"Reference decode stopped at frame {index}"
            start = time.perf_counter_ns()
            frame = source.read_frame(1.0)
            end = time.perf_counter_ns()
            assert frame is not None, f"Capture stopped at frame {index}"
            assert frame.source_frame_number == index and frame.format == "BGR"
            assert frame.payload.shape == expected.shape
            assert frame.payload.dtype == np.uint8
            # The whole image, exactly: the source stamps no text (U2).
            np.testing.assert_array_equal(frame.payload, expected)
            pre_retrieve, post_retrieve = source.retrieve_ns
            assert previous_end <= start <= frame.arrival_ns <= pre_retrieve <= post_retrieve <= end
            previous_end = end
        assert not baseline.read()[0], "Recording contains more frames than declared"
        for _ in range(2):
            assert source.read_frame(0.01) is None
        capture.release()
        assert source.read_frame(0.01) is None  # a read after the release of the capture
        source.close()
    finally:
        capture.release()
        baseline.release()
        assert not capture.isOpened() and not baseline.isOpened()


@pytest.mark.parametrize("grab_succeeds", [False, True], ids=["grab-fails", "retrieve-fails"])
def test_failed_capture_does_not_advance_frame(grab_succeeds, monkeypatch):
    capture = Mock(spec=cv2.VideoCapture)
    capture.get.return_value = 30.0
    capture.grab.return_value = grab_succeeds
    capture.retrieve.return_value = (False, None)
    source = open_source(monkeypatch, capture)
    try:
        assert source.read_frame(0.01) is None
        assert bool(capture.retrieve.call_count) == grab_succeeds
        capture.grab.return_value = True
        capture.retrieve.return_value = (True, np.full((48, 64, 3), 123, np.uint8))
        frame = source.read_frame(0.01)
        assert frame.source_frame_number == 0, "a failed read counted as a frame"
        assert np.all(frame.payload == 123)
    finally:
        source.close()
