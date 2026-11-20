import hashlib
import logging

import cv2

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.determine_backend import determine_opencv_camera_backend
from skellycam.core.camera.opencv.opencv_helpers.opencv_apply_config import apply_camera_configuration
from skellycam.utilities.wait_functions import wait_1s


class FailedToReadFrameFromCameraException(Exception):
    pass


class FailedToOpenCameraException(Exception):
    pass


logger = logging.getLogger(__name__)

# Minimum buffer size to reduce stale-frame latency.
# USB cameras deliver frames into an OS driver ring buffer (typically 2-4 frames deep).
# When our grab() loop falls behind, a larger buffer means we dequeue frames that were
# captured tens of milliseconds ago, making our grab timestamps a poor proxy for actual
# capture time. Setting this to 1 ensures grab() always returns the most recent frame
# the driver has available.
# NOTE: Not all backends honor this (MSMF ignores it). DSHOW on Windows does respect it.
_PREFERRED_BUFFER_SIZE = 1


MEDIA_FOUNDATION_VIDEO_INTERFACE = "#{e5323777-f976-4f5b-9b55-b94699c46e44}\\global"


def directshow_index(camera_id: str) -> int:
    """U1 (specs/windows-capture.md, 14.2): the DirectShow device whose device instance part (the part of
    the link before the interface class GUID) is that of the Media Foundation link of `camera_id` (7.2).

    shortcut: assumes that the Media Foundation link is `<instance part>#{video GUID}\\global` [NV];
    T-CAP-88 checks it on the cameras.
    """
    from cv2_enumerate_cameras import enumerate_cameras

    for camera in enumerate_cameras(cv2.CAP_DSHOW):
        link = camera.path.lower().split("#{")[0] + MEDIA_FOUNDATION_VIDEO_INTERFACE
        if format(int.from_bytes(hashlib.sha256(link.encode()).digest()[:2], "big"), "04x") == camera_id:
            return camera.index
    raise FailedToOpenCameraException(f"Camera {camera_id}: camera not found")


def opened_device_path(camera_index: int) -> str:
    """The device path of `OpenedMode` (4.1) for an OpenCV capture: the DirectShow device path of the
    opened index on Windows (U1), else the index."""
    if determine_opencv_camera_backend().id != cv2.CAP_DSHOW:
        return str(camera_index)
    from cv2_enumerate_cameras import enumerate_cameras

    return next((c.path for c in enumerate_cameras(cv2.CAP_DSHOW) if c.index == camera_index), str(camera_index))


def create_cv2_video_capture(config: CameraConfig, retry_count: int = 5) -> tuple[cv2.VideoCapture, CameraConfig]:
    cap_backend = determine_opencv_camera_backend()
    if cap_backend.id == cv2.CAP_DSHOW:  # Windows: detection is Media Foundation (D11), so find the device by its link
        config = config.model_copy(update=dict(camera_index=directshow_index(config.camera_id)))
    attempts = -1
    capture: cv2.VideoCapture | None = None
    while attempts < retry_count and capture is None:
        attempts += 1
        capture = cv2.VideoCapture(int(config.camera_index), cap_backend.id)
        if not capture.isOpened():
            if attempts < retry_count:
                logger.warning(
                    f"Failed to open camera {config.camera_index}. Retrying... ({attempts + 1}/{retry_count})")
                capture.release()
                wait_1s()
                capture = None
                continue
            capture.release()
            raise FailedToOpenCameraException(
                f"Camera {config.camera_id} (index {config.camera_index}, backend {cap_backend.name}) "
                f"could not open after {attempts + 1} attempts."
            )

        # Set fourcc, resolution, and framerate before the first read() so that the V4L2
        # driver negotiates the correct pixel format, frame size, and frame interval when
        # streaming begins.  Without this, the driver may default to a lower framerate
        # (e.g. 15fps instead of 30fps) or a format the camera cannot deliver, causing
        # select() timeouts or degraded performance.
        if config.capture_fourcc:
            capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*config.capture_fourcc))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.resolution.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.resolution.height)
        if config.framerate > 0:
            capture.set(cv2.CAP_PROP_FPS, config.framerate)

        # Minimize the driver-side frame buffer to reduce stale-frame latency.
        # This makes grab() timestamps a tighter proxy for actual frame capture time.
        if not capture.set(cv2.CAP_PROP_BUFFERSIZE, _PREFERRED_BUFFER_SIZE):
            logger.debug(
                f"Camera {config.camera_index}: backend did not accept "
                f"CAP_PROP_BUFFERSIZE={_PREFERRED_BUFFER_SIZE} (this is normal for some backends)"
            )
        else:
            actual = capture.get(cv2.CAP_PROP_BUFFERSIZE)
            logger.debug(f"Camera {config.camera_index}: buffer size set to {int(actual)}")

        success, image = capture.read()

        if not success or image is None:
            if attempts < retry_count:
                logger.warning(
                    f"Failed to read frame from camera {config.camera_index}. Retrying... ({attempts + 1}/{retry_count})")
                capture.release()
                wait_1s()
                capture = None
                continue
            capture.release()
            raise FailedToReadFrameFromCameraException(
                f"Camera {config.camera_id} (index {config.camera_index}) opened but "
                f"could not read a frame after {attempts + 1} attempts."
            )
    if not isinstance(capture, cv2.VideoCapture) or not capture.isOpened():
        raise FailedToOpenCameraException(f"Failed to open camera {config.camera_index} after {retry_count} attempts.")
    extracted_config = apply_camera_configuration(cv2_vid_capture=capture,
                                                  prior_config=None,
                                                  config=config)
    logger.info(f"Created `cv2.VideoCapture` object for Camera: {config.camera_index}")
    return capture, extracted_config
