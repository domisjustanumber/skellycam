import logging
import time
from typing import Callable

import numpy as np

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.openpnp.openpnp_helpers.format_selection import select_best_format
from skellycam.core.camera.openpnp.openpnp_helpers.openpnp_apply_config import apply_camera_configuration
from openpnp_capture import OpenPnPCamera
from skellycam.core.camera_group.usb_bandwidth import UsbBandwidthContentionError
from skellycam.utilities.wait_functions import wait_1s, wait_10ms

logger = logging.getLogger(__name__)


class FailedToReadFrameFromCameraException(Exception):
    """Raised when the device accepts ``Cap_openStream`` but never delivers a decodeable frame."""

    _DEFAULT = (
        "Stream opened but no video frame arrived in time — the camera may be in use elsewhere, "
        "or this capture mode is not producing data. Close other apps using the camera "
        "(browser, Meetings, OBS, Camera app), then click refresh in Skellycam."
    )

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message if message else self._DEFAULT)


class FailedToOpenCameraException(Exception):
    pass


# After ``Cap_openStream`` succeeds, we poll until the first frame or this deadline elapses.
_DEFAULT_FIRST_FRAME_DEADLINE_S = 5.0
# Progress log interval while waiting (keep below deadline so users see activity).
_FIRST_FRAME_PROGRESS_LOG_INTERVAL_S = 2.0


def create_openpnp_camera(
    config: CameraConfig,
    retry_count: int = 2,
    *,
    parallel_peer_count: int = 0,
    first_frame_deadline_seconds: float | None = None,
    pre_open_sync: Callable[[], None] | None = None,
) -> tuple[OpenPnPCamera, CameraConfig]:
    cid = config.camera_id
    # When peers are streaming, a missing first frame is structural USB isochronous
    # bandwidth contention — re-trying takes ~10s/attempt and never recovers. Fail
    # fast (single attempt) so the user sees the "use a different USB port" guidance
    # within ~5s instead of ~30+. ``retry_count`` is still honoured for *enumeration*
    # / *open()* failures (transient), via the per-step ``attempts < retry_count`` checks.
    if parallel_peer_count >= 1:
        first_frame_retry_count = 0
    else:
        first_frame_retry_count = retry_count
    attempts = -1
    camera: OpenPnPCamera | None = None
    while attempts < retry_count and camera is None:
        attempts += 1
        try:
            devices = OpenPnPCamera.list_devices()
        except Exception as e:
            if attempts < retry_count:
                logger.warning(
                    f"[{cid}] Failed to enumerate cameras. Retrying... ({attempts + 1}/{retry_count}): {e}"
                )
                wait_1s()
                continue
            raise FailedToOpenCameraException(str(e)) from e

        idx = int(config.camera_index)
        if idx < 0 or idx >= len(devices):
            if attempts < retry_count:
                logger.warning(
                    f"[{cid}] Camera index {idx} out of range. Retrying... ({attempts + 1}/{retry_count})"
                )
                wait_1s()
                continue
            raise FailedToOpenCameraException(f"Camera index {idx} out of range (found {len(devices)} devices).")

        dev = devices[idx]
        try:
            chosen = select_best_format(dev.formats, config)
        except ValueError as e:
            if attempts < retry_count:
                logger.warning(
                    f"[{cid}] No usable format for device index {idx}. Retrying... ({attempts + 1}/{retry_count}): {e}"
                )
                wait_1s()
                continue
            raise FailedToOpenCameraException(str(e)) from e

        camera = OpenPnPCamera(
            idx,
            chosen.format_id,
            format_info=chosen,
            device_formats=dev.formats,
        )
        # Multi-camera startups synchronize ``Cap_openStream`` across every worker via a
        # barrier (see ``setup_openpnp_camera_loop._pre_open_sync``). Only the first attempt
        # rendezvous-waits; on retry the barrier is already broken so we proceed without it.
        if pre_open_sync is not None and attempts == 0:
            try:
                pre_open_sync()
            except Exception as sync_err:  # noqa: BLE001 - opportunistic sync; never fatal
                logger.warning(
                    f"[{cid}] pre-open sync raised {type(sync_err).__name__}: {sync_err}; "
                    "opening stream without sync."
                )
        try:
            camera.open()
        except Exception as e:
            camera.close()
            camera = None
            if attempts < retry_count:
                logger.warning(
                    f"[{cid}] Failed to open device index {idx}. Retrying... ({attempts + 1}/{retry_count}): {e}"
                )
                wait_1s()
                continue
            raise FailedToOpenCameraException(str(e)) from e

        scratch = np.zeros((chosen.height, chosen.width, 3), dtype=np.uint8)
        success = False
        if first_frame_deadline_seconds is not None:
            first_frame_deadline_s = float(first_frame_deadline_seconds)
        else:
            first_frame_deadline_s = _DEFAULT_FIRST_FRAME_DEADLINE_S
        deadline = time.perf_counter() + first_frame_deadline_s
        wait_started = time.perf_counter()
        last_progress_log = wait_started
        while time.perf_counter() < deadline:
            if camera.capture_frame_into(scratch):
                success = True
                break
            now = time.perf_counter()
            if now - last_progress_log >= _FIRST_FRAME_PROGRESS_LOG_INTERVAL_S:
                elapsed = now - wait_started
                logger.info(
                    f"[{cid}] Still waiting for first frame from device index {idx} "
                    f"({elapsed:.0f}s / {first_frame_deadline_s:.0f}s, parallel_peers={parallel_peer_count})..."
                )
                last_progress_log = now
            wait_10ms()

        if not success:
            camera.close()
            camera = None
            if attempts < first_frame_retry_count:
                logger.warning(
                    f"[{cid}] No first frame from device index {idx} within {first_frame_deadline_s:.0f}s "
                    f"(device: {dev.name!r}). Retrying... ({attempts + 1}/{first_frame_retry_count})"
                )
                wait_10ms()
                continue
            if parallel_peer_count >= 1:
                raise UsbBandwidthContentionError(
                    f"Camera {cid} (device index {idx}, {dev.name!r}) never delivered a first frame "
                    f"while {parallel_peer_count} other camera(s) were also starting. "
                    "This usually means USB isochronous bandwidth is exhausted on the shared host controller."
                )
            raise FailedToReadFrameFromCameraException()

    if camera is None or not camera.is_open():
        raise FailedToOpenCameraException(f"Failed to open camera {config.camera_index} after {retry_count} attempts.")

    extracted_config = apply_camera_configuration(camera=camera, prior_config=None, config=config)
    logger.info(f"Created OpenPnPCamera stream for Camera index: {config.camera_index}")
    return camera, extracted_config
