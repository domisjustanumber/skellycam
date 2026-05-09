"""Python-facing types for the openpnp-capture wrapper (no ctypes beyond module boundaries)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class OpenPnPCaptureError(RuntimeError):
    """Base error for openpnp-capture wrapper failures."""


class OpenPnPCaptureLibraryNotFoundError(OpenPnPCaptureError):
    """The native openpnp-capture shared library could not be loaded."""


class OpenPnPCaptureAPIError(OpenPnPCaptureError):
    """A Cap_* call returned CAPRESULT_ERR or another failure code."""

    def __init__(self, message: str, *, result_code: int | None = None) -> None:
        super().__init__(message)
        self.result_code = result_code


class OpenPnPProperty(IntEnum):
    """Mirrors CAPPROPID_* from openpnp-capture.h."""

    EXPOSURE = 1
    FOCUS = 2
    ZOOM = 3
    WHITEBALANCE = 4
    GAIN = 5
    BRIGHTNESS = 6
    CONTRAST = 7
    SATURATION = 8
    GAMMA = 9
    HUE = 10
    SHARPNESS = 11
    BACKLIGHTCOMP = 12
    POWERLINEFREQ = 13


@dataclass(frozen=True, slots=True)
class OpenPnPFormatInfo:
    """One negotiated pixel format / resolution / FPS tuple for a device."""

    format_id: int
    width: int
    height: int
    fps: float
    fourcc_str: str
    bpp: int


@dataclass(frozen=True, slots=True)
class OpenPnPDeviceInfo:
    """One enumerated capture device."""

    index: int
    name: str
    unique_id: str | None
    formats: list[OpenPnPFormatInfo]


@dataclass(frozen=True, slots=True)
class OpenPnPPropertyLimits:
    min_value: int
    max_value: int
    default_value: int


@dataclass(frozen=True, slots=True)
class OpenPnPCameraSettings:
    """Snapshot of readable camera controls (unsupported props may be None)."""

    exposure: int | None
    exposure_auto: bool | None
    focus: int | None
    focus_auto: bool | None
    zoom: int | None
    zoom_auto: bool | None
    white_balance: int | None
    gain: int | None
    brightness: int | None
    contrast: int | None
    saturation: int | None
    gamma: int | None
    hue: int | None
    sharpness: int | None
    backlight_comp: int | None
    powerline_freq: int | None
