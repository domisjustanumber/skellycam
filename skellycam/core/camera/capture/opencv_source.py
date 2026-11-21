"""The OpenCV source (specs/windows-capture.md, sections 4.4 and 14; ADR-HP7D item 13).

A pull source for Linux and macOS, and on Windows while `SKELLYCAM_WINDOWS_CAPTURE=opencv` (14.2).
"""
import logging
import sys
import threading
import time
from fractions import Fraction

import cv2

from skellycam.core.camera.capture.source import (
    CapturedFrame,
    CaptureFailure,
    CaptureRequest,
    ControlSetting,
    empty_diagnostics,
    ControlState,
    ControlValue,
    OpenedMode,
)
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.camera.opencv.opencv_helpers.create_cv2_video_capture import (
    create_cv2_video_capture,
    opened_device_path,
)
from skellycam.core.camera.opencv.opencv_helpers.opencv_apply_config import (
    AUTO_EXPOSURE_SETTING,
    MANUAL_EXPOSURE_SETTING,
)
from skellycam.core.ipc.frame_ring import NO_SAMPLE_NS

logger = logging.getLogger(__name__)


class OpenCVSource:
    name = "opencv"

    def __init__(self, config: CameraConfig):
        self.config = config
        self._capture: cv2.VideoCapture | None = None
        self._grabs = 0
        self._exposure_auto = False
        # The control thread and the loop thread share one cv2.VideoCapture, which is not thread-safe (4.3).
        self._lock = threading.Lock()
        # The loop stamps the retrieve columns of the timing file from this (5.4, D41).
        self.retrieve_ns: tuple[int, int] | None = None

    def open(self, request: CaptureRequest) -> OpenedMode:
        config = self.config.model_copy(update=dict(
            resolution=ImageResolution(width=request.width, height=request.height),
            framerate=request.framerate, capture_fourcc=request.capture_fourcc))
        try:
            self._capture, opened = create_cv2_video_capture(config)
        except Exception as error:
            raise CaptureFailure("open", f"{type(error).__name__}: {error}") from error
        self._grabs = 0
        reported = self._capture.get(cv2.CAP_PROP_FPS)
        fps = Fraction(reported).limit_denominator(1001) if reported > 0 else Fraction(0)  # 0: no reported rate (D46)
        return OpenedMode(width=int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                          height=int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                          fps_num=fps.numerator, fps_den=fps.denominator, format="BGR",
                          device_path=opened_device_path(opened.camera_index))

    @property
    def searches(self) -> bool:
        """camera-requests.md 1.7: the exposure search runs on the OpenCV source of Windows only."""
        return sys.platform == "win32"

    def read_frame(self, timeout_s: float) -> CapturedFrame | None:
        deadline = time.perf_counter() + timeout_s
        while True:
            with self._lock:
                ok = image = None
                if self._capture.grab():
                    arrival_ns = time.perf_counter_ns()
                    pre_ns = time.perf_counter_ns()
                    ok, image = self._capture.retrieve()
                    post_ns = time.perf_counter_ns()
            if ok and image is not None:
                number, self._grabs = self._grabs, self._grabs + 1
                self.retrieve_ns = (pre_ns, post_ns)
                return CapturedFrame(payload=image, format="BGR", arrival_ns=arrival_ns, sample_ns=NO_SAMPLE_NS,
                                     delivered_len=0, driver_error=False, source_frame_number=number,
                                     discontinuity=False)
            if time.perf_counter() >= deadline:
                return None
            time.sleep(0.001)  # a failed grab can return at once; no spin (4.3)

    def set_controls(self, changes: dict[str, ControlSetting]) -> ControlState:
        with self._lock:
            return self._set_controls(changes)

    def _set_controls(self, changes: dict[str, ControlSetting]) -> ControlState:
        capture = self._capture
        for name, setting in changes.items():
            if name != "exposure":
                raise CaptureFailure("set controls", f"Camera {self.config.camera_id} has no {name} control",
                                     code="control-failed")
            if sys.platform in ("linux", "darwin"):  # camera-requests.md 1.7: the forced auto exposure, for now
                capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, AUTO_EXPOSURE_SETTING)
                self._exposure_auto = True
            elif setting.auto:
                capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, AUTO_EXPOSURE_SETTING)
                self._exposure_auto = True
            else:
                capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, MANUAL_EXPOSURE_SETTING)
                if setting.value is not None:
                    capture.set(cv2.CAP_PROP_EXPOSURE, float(setting.value))
                self._exposure_auto = False
        gain, focus = capture.get(cv2.CAP_PROP_GAIN), capture.get(cv2.CAP_PROP_FOCUS)
        # 11.5: a control that the camera lacks is absent; OpenCV reads -1 for it
        return {"exposure": ControlValue(present=True, auto=self._exposure_auto,
                                         value=int(capture.get(cv2.CAP_PROP_EXPOSURE))),
                "gain": ControlValue(present=gain != -1, auto=False, value=int(gain) if gain != -1 else None),
                "focus": ControlValue(present=focus != -1, auto=focus != -1 and bool(capture.get(cv2.CAP_PROP_AUTOFOCUS)),
                                      value=int(focus) if focus != -1 else None)}

    def close(self, restore: bool = True) -> None:
        """The OpenCV source has no restore (unix-capture.md 4.7): it cannot read the auto flag."""
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    @property
    def replaced_count(self) -> int:
        return 0  # a pull source keeps no waiting place (4.4)

    def diagnostics(self) -> dict:
        return empty_diagnostics("opencv")  # unix-capture.md 4.2 item 2: `backend`, null for each other key
