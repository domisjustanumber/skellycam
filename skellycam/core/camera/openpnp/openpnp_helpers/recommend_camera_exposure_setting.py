import enum
import logging
from typing import List, Tuple

import numpy as np
from tabulate import tabulate

from skellycam.core.camera.openpnp_capture import OpenPnPCamera, OpenPnPCaptureAPIError, OpenPnPProperty

logger = logging.getLogger(__name__)

NUMBER_OF_FRAMES_TO_SETTLE = 10
TARGET_BRIGHTNESS = 127.5


class ExposureModes(enum.Enum):
    """Exposure policy names stored on :class:`CameraConfig` as ``exposure_mode``."""

    AUTO = enum.auto()
    MANUAL = enum.auto()
    RECOMMEND = enum.auto()


def _exposure_test_grid(camera: OpenPnPCamera) -> List[int]:
    if not camera.supports_property(OpenPnPProperty.EXPOSURE):
        raise OpenPnPCaptureAPIError("Camera does not report an exposure property")
    limits = camera.get_property_limits(OpenPnPProperty.EXPOSURE)
    span = limits.max_value - limits.min_value
    if span <= 0:
        return [limits.min_value]
    steps = min(20, span + 1)
    step = max(1, span // steps)
    return list(range(limits.min_value, limits.max_value + 1, step))


def capture_frame_with_exposure(
    camera: OpenPnPCamera,
    *,
    use_manual: bool,
    exposure_setting: int | None = None,
) -> float:
    """Apply exposure mode, wait for settle captures, return mean brightness (BGR buffer)."""
    if use_manual:
        camera.set_auto_exposure(False)
        if exposure_setting is not None:
            camera.set_exposure(int(exposure_setting))
    else:
        camera.set_auto_exposure(True)

    scratch = np.zeros((camera.format.height, camera.format.width, 3), dtype=np.uint8)
    for _ in range(NUMBER_OF_FRAMES_TO_SETTLE):
        _blocking_capture(camera, scratch)
    _blocking_capture(camera, scratch)
    return float(np.mean(scratch))


def _blocking_capture(camera: OpenPnPCamera, scratch: np.ndarray) -> None:
    import time

    for _ in range(500):
        if camera.capture_frame_into(scratch):
            return
        time.sleep(0.002)
    raise RuntimeError("Timed out waiting for a frame while adjusting exposure")


def find_optimal_exposure_setting(camera: OpenPnPCamera, exposure_settings: List[int]) -> int:
    logger.debug(
        "Starting search for optimal exposure (brightness closest to %.1f)", TARGET_BRIGHTNESS
    )
    differences: List[Tuple[str, float, float]] = []
    for setting in exposure_settings:
        manual_brightness = capture_frame_with_exposure(
            camera, use_manual=True, exposure_setting=setting
        )
        difference = np.abs(TARGET_BRIGHTNESS - manual_brightness)
        differences.append((f"{setting}", manual_brightness, difference))

    best_setting = min(differences, key=lambda x: x[2])
    annotated_differences = [
        (row[0], row[1], f" {'>>   ' if row == best_setting else ''}{row[2]:.2f}") for row in differences
    ]
    headers = ["  Exposure Setting", "Brightness", "Difference from Target (127.5)"]
    table = tabulate(annotated_differences, headers=headers, floatfmt=".2f", colalign=("center", "center", "right"))
    logger.debug(table.replace("\n", "\n\t"))
    return int(best_setting[0])


def get_recommended_openpnp_exposure(camera: OpenPnPCamera, offset_from_midrange: int = -1) -> int:
    exposure_settings = _exposure_test_grid(camera)
    try:
        midrange_exposure = find_optimal_exposure_setting(camera=camera, exposure_settings=exposure_settings)
        recommended_exposure = midrange_exposure + offset_from_midrange
        logger.debug(
            "Mid-range exposure: %s, recommended (with offset %s): %s",
            midrange_exposure,
            offset_from_midrange,
            recommended_exposure,
        )
    except Exception:
        logger.exception("An error occurred during exposure optimization")
        raise
    return int(recommended_exposure)
