import time

import numpy as np
from skellycam.core.camera.openpnp_capture import OpenPnPFormatInfo, OpenPnPProperty
from skellycam.tests.mocks.camera_mock import MockOpenPnPCamera


class TestMockOpenPnPCamera:
    def test_initialization(self) -> None:
        cam = MockOpenPnPCamera()
        cam.open()
        assert cam.is_open()
        assert cam.format.fps == 30.0
        assert cam.format.width == 640
        assert cam.format.height == 480
        cam.close()
        assert not cam.is_open()

    def test_blocking_behavior(self) -> None:
        fps = 60.0
        cam = MockOpenPnPCamera()
        cam._fps = fps  # type: ignore[attr-defined]
        cam._format_info = OpenPnPFormatInfo(0, 640, 480, fps, "MJPG", 24)
        cam.open()
        num_frames = 10
        start_time = time.time()
        buf = np.zeros((480, 640, 3), dtype=np.uint8)
        for _ in range(num_frames):
            assert cam.capture_frame_into(buf)
        elapsed = time.time() - start_time
        expected_duration = num_frames / fps
        assert elapsed >= expected_duration * 0.95
        assert elapsed <= expected_duration * 1.5
        cam.close()

    def test_frame_content(self) -> None:
        cam = MockOpenPnPCamera()
        cam.open()
        buf = np.zeros((480, 640, 3), dtype=np.uint8)
        assert cam.capture_frame_into(buf)
        assert buf.dtype == np.uint8
        assert np.sum(buf) > 0
        cam.close()

    def test_exposure_properties(self) -> None:
        cam = MockOpenPnPCamera()
        cam.open()
        assert cam.supports_property(OpenPnPProperty.EXPOSURE)
        cam.set_auto_exposure(False)
        cam.set_exposure(-9)
        assert cam.get_settings().exposure == -9
        cam.close()

    def test_capture_after_close(self) -> None:
        cam = MockOpenPnPCamera()
        cam.open()
        cam.close()
        buf = np.zeros((480, 640, 3), dtype=np.uint8)
        assert not cam.capture_frame_into(buf)
