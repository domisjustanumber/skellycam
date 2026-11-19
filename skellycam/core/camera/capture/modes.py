"""Modes and rates (specs/windows-capture.md, sections 7.3 and 7.5; names of ADR-HP7D item 8).

Pure functions.
"""

import json
import math
from dataclasses import dataclass
from fractions import Fraction

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
    if not near and sized and not any(at_floor(m.fps) for m in sized):
        raise CaptureFailure("set mode", NO_FLOOR_MODE)  # U11: the size has no mode at the floor at all
    if not near:
        listed = json.dumps([mode.model_dump() for mode in supported_modes(native)])
        raise CaptureFailure("set mode", f"no {request.capture_fourcc} mode at {request.width}x{request.height} "
                                         f"near {request.framerate:g} fps; the camera has {listed}")
    chosen = min(near, key=lambda m: abs(m.fps - request.framerate))  # a tie: the first in the list (D15)
    if not at_floor(chosen.fps):
        raise CaptureFailure("set mode", NO_FLOOR_MODE)
    return chosen


def mode_fraction(rate: float) -> tuple[int, int]:
    """`fps_num`, `fps_den` of a rate of `supported_modes`: its rounded 29.97 is 30000/1001 (7.3, U15)."""
    if rates_equal(rate, FLOOR_FPS):
        return 30000, 1001
    fraction = Fraction(rate).limit_denominator(1001)
    return fraction.numerator, fraction.denominator


def native_from_supported(supported: list[CaptureMode]) -> list[NativeMode]:
    """The MJPG modes that `supported_modes` describes, for the mode choice of the whole-request check (7.5)."""
    return [NativeMode(mode.width, mode.height, *mode_fraction(rate), "MJPG")
            for mode in supported for rate in mode.framerates]


def _fps_text(rate: float) -> str:
    return f"{rate:.2f}".rstrip("0").rstrip(".")


def _cameras_text(camera_ids: list[str]) -> str:
    if len(camera_ids) == 1:
        return f"camera {camera_ids[0]}"
    return f"cameras {', '.join(camera_ids[:-1])} and {camera_ids[-1]}"


def rate_groups(rates: dict[str, float]) -> list[tuple[float, list[str]]]:
    """The camera IDs of each different rate (D17 tolerance), lowest rate first."""
    groups: list[tuple[float, list[str]]] = []
    for camera_id, rate in sorted(rates.items(), key=lambda item: item[1]):
        if groups and rates_equal(groups[-1][0], rate):
            groups[-1][1].append(camera_id)
        else:
            groups.append((rate, [camera_id]))
    return groups


def group_rate_problem(rates: dict[str, float]) -> str | None:
    """The one-rate rule (D18, U15): None, or the reason to refuse the request."""
    groups = rate_groups(rates)
    if all(same_rate_class(groups[0][0], rate) for rate, _ in groups):
        return None
    listed = "; ".join(f"{_cameras_text(ids)} at {_fps_text(rate)} fps" for rate, ids in groups)
    return f"all cameras of a group must have one frame rate: {listed}"


def mixed_rate_text(rates: dict[str, float]) -> str | None:
    """The warning text of a group with more than one rate (U15), or None when all rates are equal."""
    groups = rate_groups(rates)
    if len(groups) == 1:
        return None
    (low, low_ids), higher = groups[0], groups[1:]
    run = "runs" if len(low_ids) == 1 else "run"
    text = ("C" + _cameras_text(low_ids)[1:] + f" {run} at {_fps_text(low)} fps, "
            + ", ".join(f"{_cameras_text(ids)} at {_fps_text(rate)} fps" for rate, ids in higher)
            + f". The group runs at {_fps_text(low)} fps.")
    for rate, ids in higher:
        skip = "skips" if len(ids) == 1 else "skip"
        if same_rate_class(low, rate):
            how_often = f"one frame about every {round(1 / (rate - low))} s"
        else:
            how_often = f"about {round(rate - low)} frames per second"
        text += (f" C{_cameras_text(ids)[1:]} {skip} {how_often}; each skipped frame is counted and is "
                 f"missing from the recording.")
    return text
