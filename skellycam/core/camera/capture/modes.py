"""Modes and rates (specs/windows-capture.md, sections 7.3 and 7.5; names of ADR-HP7D item 8).

Pure functions.
"""

import json
import math
from dataclasses import dataclass

from pydantic import BaseModel

from skellycam.core.camera.capture.source import CaptureFailure, CaptureRequest

FLOOR_FPS = 30000 / 1001  # U11: 29.97 counts as 30
NO_FLOOR_MODE = "no mode at 30 fps or more"


class CaptureMode(BaseModel):
    """One item of `CameraDeviceInfo.supported_modes` (7.3): one MJPG size and its rates.

    `detect_cameras_devices.py` imports it from here (ADR-HP7D item 3).
    """
    width: int
    height: int
    framerates: list[float]


@dataclass(frozen=True)
class NativeMode:
    """One native media type of a camera."""
    width: int
    height: int
    fps_num: int
    fps_den: int
    format: str

    @property
    def fps(self) -> float:
        return self.fps_num / self.fps_den


def rates_equal(a: float, b: float) -> bool:
    """D17: a relative tolerance of 0.0001."""
    return math.isclose(a, b, rel_tol=1e-4)


def at_floor(fps: float) -> bool:
    """True when `fps` is 29.97 or more (U11). The rounded 29.97 of `supported_modes` also counts."""
    return fps > FLOOR_FPS or rates_equal(fps, FLOOR_FPS)


def same_rate_class(a: float, b: float) -> bool:
    """The one-rate rule (D18): equal rates, or 29.97 and 30, which are one rate class (U15)."""
    return rates_equal(a, b) or all(rates_equal(r, 30.0) or rates_equal(r, FLOOR_FPS) for r in (a, b))


def auto_rate(rates: list[float]) -> float | None:
    """D16, U11: of the rates of one size, 30, else 29.97, else the highest. None if none is at the floor."""
    usable = [r for r in rates if at_floor(r)]
    if not usable:
        return None
    thirty = [r for r in usable if rates_equal(r, 30.0)] or [r for r in usable if rates_equal(r, FLOOR_FPS)]
    return thirty[0] if thirty else max(usable)


def supported_modes(native: list[NativeMode]) -> list[CaptureMode]:
    """The `supported_modes` of 7.3: MJPG only, one entry for each size, rates at the floor or above."""
    rates: dict[tuple[int, int], set[float]] = {}
    for mode in native:
        if mode.format == "MJPG" and at_floor(mode.fps):
            rates.setdefault((mode.width, mode.height), set()).add(round(mode.fps, 2))
    sizes = sorted(rates, key=lambda size: (-size[0] * size[1], -size[0]))
    return [CaptureMode(width=w, height=h, framerates=sorted(rates[w, h])) for w, h in sizes]


def choose_mode(native: list[NativeMode], request: CaptureRequest) -> NativeMode:
    """The mode choice of 7.5. Raises `CaptureFailure` with stage "set mode"."""
    sized = [m for m in native
             if (m.width, m.height, m.format) == (request.width, request.height, request.capture_fourcc)]
    if request.framerate in (-1, 0):
        rate = auto_rate([m.fps for m in sized])
        if rate is None:
            raise CaptureFailure("set mode", NO_FLOOR_MODE)
        return next(m for m in sized if m.fps == rate)
    near = [m for m in sized if abs(m.fps - request.framerate) <= 0.5]
    if not near:
        listed = json.dumps([mode.model_dump() for mode in supported_modes(native)])
        raise CaptureFailure("set mode", f"no {request.capture_fourcc} mode at {request.width}x{request.height} "
                                         f"near {request.framerate:g} fps; the camera has {listed}")
    chosen = min(near, key=lambda m: abs(m.fps - request.framerate))  # a tie: the first in the list (D15)
    if not at_floor(chosen.fps):
        raise CaptureFailure("set mode", NO_FLOOR_MODE)
    return chosen
