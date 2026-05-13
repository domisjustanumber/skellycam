"""Try opening an OpenPnP capture stream to see if the device is usable by Skellycam."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.openpnp.openpnp_helpers.format_selection import select_best_format
from skellycam.utilities.wait_functions import wait_10ms
from openpnp_capture import OpenPnPCamera
from openpnp_capture.types import (
    OpenPnPCaptureAPIError,
    OpenPnPFormatInfo,
    OpenPnPProperty,
)

logger = logging.getLogger(__name__)

# ``Cap_openStream`` can succeed on some stacks while no frames ever arrive (device in use
# elsewhere, wedged graph, etc.). Match ``create_openpnp_camera`` semantics with a shorter
# budget so detection stays responsive.
_PROBE_FIRST_FRAME_DEADLINE_S = 2.0


def _first_frame_arrived_within_deadline(cam: Any, fmt: OpenPnPFormatInfo) -> bool:
    scratch = np.zeros((fmt.height, fmt.width, 3), dtype=np.uint8)
    deadline = time.perf_counter() + _PROBE_FIRST_FRAME_DEADLINE_S
    while time.perf_counter() < deadline:
        if cam.capture_frame_into(scratch):
            return True
        wait_10ms()
    return False


@dataclass(frozen=True, slots=True)
class ProbeStreamOutcome:
    """Result of probing whether a capture stream opens, plus discovered focus caps."""

    stream_available: bool
    stream_unavailable_reason: str | None = None
    supports_focus_manual: bool = False
    focus_auto_supported: bool = False
    focus_min: int | None = None
    focus_max: int | None = None
    focus_default: int | None = None


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


def _maybe_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _focus_caps(cam: Any) -> tuple[bool, bool, int | None, int | None, int | None]:
    if not cam.supports_property(OpenPnPProperty.FOCUS):
        return False, False, None, None, None
    try:
        limits = cam.get_property_limits(OpenPnPProperty.FOCUS)
    except OpenPnPCaptureAPIError:
        return False, False, None, None, None
    st = cam.get_settings()
    auto_ok = st.focus_auto is not None
    return (
        True,
        auto_ok,
        _maybe_int(limits.min_value),
        _maybe_int(limits.max_value),
        _maybe_int(limits.default_value),
    )


def probe_openpnp_stream(
    device_index: int,
    formats: list[OpenPnPFormatInfo],
    *,
    preferred_config: CameraConfig | None = None,
) -> ProbeStreamOutcome:
    """
    Try ``Cap_openStream`` until one format yields at least one decoded frame; optionally read
    focus capability while open.

    Failure usually means the device is exclusive-open elsewhere (browser, Teams, OBS, etc.),
    or the stream graph never starts even though ``open()`` returned.
    """
    if not formats:
        return ProbeStreamOutcome(False, "No video formats reported for this device.")

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
            if not _first_frame_arrived_within_deadline(cam, fmt):
                last_err = (
                    f"Opened device_index={device_index} format_id={fmt.format_id} but no frame "
                    f"within {_PROBE_FIRST_FRAME_DEADLINE_S:.0f}s — often another app owns the "
                    "camera or the driver produced an empty graph."
                )
                logger.debug("%s", last_err)
                continue
            logger.debug(
                "Stream probe OK for device_index=%s format_id=%s (%sx%s %s)",
                device_index,
                fmt.format_id,
                fmt.width,
                fmt.height,
                fmt.fourcc_str,
            )
            sup_manual, sup_auto, fmin, fmax, fdfl = _focus_caps(cam)
            return ProbeStreamOutcome(
                stream_available=True,
                stream_unavailable_reason=None,
                supports_focus_manual=sup_manual,
                focus_auto_supported=sup_auto,
                focus_min=fmin,
                focus_max=fmax,
                focus_default=fdfl,
            )
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
        "Could not start a working capture stream (open failed or no frames arrived). "
        "The camera may be in use by another application "
        "(browser tab, video chat, OBS, Windows Camera app, etc.)."
    )
    if last_err:
        return ProbeStreamOutcome(False, f"{hint} ({last_err})")
    return ProbeStreamOutcome(False, hint)


def probe_openpnp_stream_available(
    device_index: int,
    formats: list[OpenPnPFormatInfo],
    *,
    preferred_config: CameraConfig | None = None,
) -> tuple[bool, str | None]:
    """Back-compat wrapper returning ``(ok, reason)`` only."""
    r = probe_openpnp_stream(device_index, formats, preferred_config=preferred_config)
    return r.stream_available, r.stream_unavailable_reason
