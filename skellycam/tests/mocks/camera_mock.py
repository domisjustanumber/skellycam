import logging
import time

import cv2
import numpy as np

from skellycam.core.camera.openpnp_capture.types import OpenPnPFormatInfo, OpenPnPCameraSettings, OpenPnPProperty, OpenPnPPropertyLimits

logger = logging.getLogger(__name__)


class MockOpenPnPCamera:
    """Test double matching :class:`OpenPnPCamera` for frame/property behaviour."""

    def __init__(self, index: int = 0) -> None:
        self._device_index = index
        self._opened = False
        self._frame_count = 0
        self._width = 640
        self._height = 480
        self._fps = 30.0
        self._exposure = -5
        self._auto_exposure = False
        self._focus = 120
        self._auto_focus = False
        self._zoom = 0
        self._last_frame_time = time.time()
        self._start_time = time.time()
        self._format_info = OpenPnPFormatInfo(
            format_id=0,
            width=self._width,
            height=self._height,
            fps=self._fps,
            fourcc_str="MJPG",
            bpp=24,
        )
        self._device_formats = [self._format_info]

    @property
    def device_index(self) -> int:
        return self._device_index

    @property
    def format(self) -> OpenPnPFormatInfo:
        return self._format_info

    @property
    def fourcc(self) -> str:
        return self._format_info.fourcc_str

    @property
    def device_formats(self) -> list[OpenPnPFormatInfo]:
        return list(self._device_formats)

    def open(self) -> None:
        self._opened = True

    def close(self) -> None:
        self._opened = False

    def is_open(self) -> bool:
        return self._opened

    def has_new_frame(self) -> bool:
        return self._opened

    def stream_frame_count(self) -> int:
        return self._frame_count

    def capture_frame_into(self, buffer: np.ndarray) -> bool:
        if not self._opened:
            return False
        target_interval = 1.0 / max(self._fps, 1.0)
        now = time.time()
        elapsed = now - self._last_frame_time
        if elapsed < target_interval:
            time.sleep(target_interval - elapsed)
        self._last_frame_time = time.time()
        self._frame_count += 1

        if buffer.shape != (self._height, self._width, 3):
            raise ValueError(f"Expected buffer {(self._height, self._width, 3)}, got {buffer.shape}")
        frame = self._generate_frame()
        buffer[:] = frame
        return True

    def _generate_frame(self) -> np.ndarray:
        frame = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1
        color = (255, 255, 255)
        thickness = 2
        line_height = 30
        start_x = 10
        start_y = 40
        info_lines = [
            f"Frame: {self._frame_count}",
            f"Time: {time.time() - self._start_time:.3f}s",
            f"FPS: {self._fps:.1f}",
            f"Res: {self._width}x{self._height}",
            f"Exp: {self._exposure}",
            "Mock OpenPnPCamera",
        ]
        for i, line in enumerate(info_lines):
            y = start_y + (i * line_height)
            cv2.putText(frame, line, (start_x, y), font, font_scale, color, thickness, cv2.LINE_AA)
        return frame

    def supports_property(self, prop: OpenPnPProperty) -> bool:
        return prop in {
            OpenPnPProperty.EXPOSURE,
            OpenPnPProperty.FOCUS,
            OpenPnPProperty.ZOOM,
        }

    def get_property_limits(self, prop: OpenPnPProperty) -> OpenPnPPropertyLimits:
        if prop == OpenPnPProperty.EXPOSURE:
            return OpenPnPPropertyLimits(-12, 0, -6)
        if prop == OpenPnPProperty.FOCUS:
            return OpenPnPPropertyLimits(0, 255, 128)
        if prop == OpenPnPProperty.ZOOM:
            return OpenPnPPropertyLimits(0, 100, 0)
        raise RuntimeError(f"unsupported {prop}")

    def set_exposure(self, value: int) -> None:
        self._exposure = int(value)

    def set_auto_exposure(self, enabled: bool) -> None:
        self._auto_exposure = bool(enabled)

    def set_focus(self, value: int) -> None:
        self._focus = int(value)

    def set_auto_focus(self, enabled: bool) -> None:
        self._auto_focus = bool(enabled)

    def set_zoom(self, value: int) -> None:
        self._zoom = int(value)

    def get_settings(self) -> OpenPnPCameraSettings:
        return OpenPnPCameraSettings(
            exposure=self._exposure,
            exposure_auto=self._auto_exposure,
            focus=self._focus,
            focus_auto=self._auto_focus,
            zoom=self._zoom,
            zoom_auto=False,
            white_balance=None,
            gain=None,
            brightness=None,
            contrast=None,
            saturation=None,
            gamma=None,
            hue=None,
            sharpness=None,
            backlight_comp=None,
            powerline_freq=None,
        )

    def reopen_stream(self, format_id: int, format_info: OpenPnPFormatInfo) -> None:
        self.close()
        self._format_info = format_info
        self._width = format_info.width
        self._height = format_info.height
        self._fps = format_info.fps
        self._device_formats = [format_info]
        self.open()
