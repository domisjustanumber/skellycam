"""Try opening an OpenPnP capture stream to see if the device is usable by Skellycam."""

from __future__ import annotations

import logging

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.openpnp.openpnp_helpers.format_selection import select_best_format
from skellycam.core.camera.openpnp_capture import OpenPnPCamera
from skellycam.core.camera.openpnp_capture.types import OpenPnPCaptureAPIError, OpenPnPFormatInfo

logger = logging.getLogger(__name__)


def _formats_to_try(formats: list[OpenPnPFormatInfo], config: CameraConfig) -> list[OpenPnPFormatInfo]:
    """Prefer the format Skellycam would pick for ``config``, then try remaining formats once each."""
    if not formats:
        return []
    ordered: list[OpenPnPFormatInfo] = []
    seen: set[int] = set()
    try:
        best = select_best_format(formats, config)
        ordered.append(best)
        seen.add(best.format_id)
    except ValueError:
        pass
    for f in formats:
        if f.format_id not in seen:
            seen.add(f.format_id)
            ordered.append(f)
    return ordered


def probe_openpnp_stream_available(
    device_index: int,
    formats: list[OpenPnPFormatInfo],
    *,
    preferred_config: CameraConfig | None = None,
) -> tuple[bool, str | None]:
    """
    Return whether ``Cap_openStream`` succeeds for at least one format.

    Failure usually means the device is exclusive-open elsewhere (browser, Teams, OBS, etc.).
    """
    if not formats:
        return False, "No video formats reported for this device."

    config = preferred_config or CameraConfig()
    last_err: str | None = None
    for fmt in _formats_to_try(formats, config):
        cam = OpenPnPCamera(
            device_index,
            fmt.format_id,
            format_info=fmt,
            device_formats=formats,
        )
        try:
            cam.open()
            logger.debug(
                "Stream probe OK for device_index=%s format_id=%s (%sx%s %s)",
                device_index,
                fmt.format_id,
                fmt.width,
                fmt.height,
                fmt.fourcc_str,
            )
            return True, None
        except OpenPnPCaptureAPIError as e:
            last_err = str(e)
            logger.debug(
                "Stream probe failed device_index=%s format_id=%s: %s",
                device_index,
                fmt.format_id,
                e,
            )
        finally:
            cam.close()

    hint = (
        "Could not open capture stream — the camera may be in use by another application "
        "(browser tab, video chat, OBS, Windows Camera app, etc.)."
    )
    if last_err:
        return False, f"{hint} ({last_err})"
    return False, hint
