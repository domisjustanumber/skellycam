"""Try opening an OpenPnP capture stream to see if the device is usable by Skellycam."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.openpnp.openpnp_helpers.format_selection import select_best_format
from skellycam.core.camera.openpnp_capture import OpenPnPCamera
from skellycam.core.camera.openpnp_capture.types import (
    OpenPnPCaptureAPIError,
    OpenPnPFormatInfo,
    OpenPnPProperty,
)

logger = logging.getLogger(__name__)


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


def _focus_caps(cam: OpenPnPCamera) -> tuple[bool, bool, int | None, int | None, int | None]:
    if not cam.supports_property(OpenPnPProperty.FOCUS):
        return False, False, None, None, None
    try:
        limits = cam.get_property_limits(OpenPnPProperty.FOCUS)
    except OpenPnPCaptureAPIError:
        return False, False, None, None, None
    st = cam.get_settings()
    auto_ok = st.focus_auto is not None
    return True, auto_ok, limits.min_value, limits.max_value, limits.default_value


def probe_openpnp_stream(
    device_index: int,
    formats: list[OpenPnPFormatInfo],
    *,
    preferred_config: CameraConfig | None = None,
) -> ProbeStreamOutcome:
    """
    Try ``Cap_openStream`` until one format works; optionally read focus capability while open.

    Failure usually means the device is exclusive-open elsewhere (browser, Teams, OBS, etc.).
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
        "Could not open capture stream — the camera may be in use by another application "
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
