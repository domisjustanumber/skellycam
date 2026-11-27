"""Modes and rates (specs/windows-capture.md, sections 7.3 to 7.5 and 22.2; names of ADR-HP7D item 8).

Pure functions.
"""

import dataclasses
import json
import math
from dataclasses import dataclass
from fractions import Fraction

from pydantic import BaseModel

from skellycam.core.camera.capture.source import CaptureFailure, CaptureRequest

FLOOR_FPS = 30000 / 1001  # U11: 29.97 counts as 30
NO_FLOOR_MODE = "no mode at 30 fps or more"
NO_SIZE_MODE = "no mode of 640x360 or more"  # 22.2 [YQN1 3]
NO_USABLE_MODE = "has no mode of 640x360 or more at 30 fps"  # 22.2 [YQN1 9]: each mode is below a floor


def small_request_text(width: int, height: int) -> str:
    """22.2 [YQN1 9]: the whole-request check of a requested size below the floor."""
    return f"the requested size {width}x{height} is below the smallest size 640x360"
RAW_FORMATS = ("YUY2", "NV12")  # 13.1: the uncompressed formats that skellycam opens
RAW_ORDER = ("YUY2", "NV12")  # 22.2 [N72V 1, Q845]: the raw mode that an MJPG request opens when the size has no MJPG
UNCOMPRESSED = ("YUY2", "NV12", "RAW")  # 7.4
NEVER_OPENED = ("H264", "RAW")  # 7.4 [D4, U8]


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


class CaptureModeEntry(BaseModel):
    """One item of `CameraDeviceInfo.capture_modes` (7.4, 22.2 [V1, 3WCA 1]), with the fields in the order of its JSON."""
    width: int
    height: int
    fps_num: int
    fps_den: int
    framerate: float
    format: str
    uncompressed: bool
    selectable: bool
    reason: str | None


def rates_equal(a: float, b: float) -> bool:
    """D17: a relative tolerance of 0.0001."""
    return math.isclose(a, b, rel_tol=1e-4)


def at_floor(fps: float) -> bool:
    """True when `fps` is 29.97 or more (U11). The rounded 29.97 of `supported_modes` also counts."""
    return fps > FLOOR_FPS or rates_equal(fps, FLOOR_FPS)


def size_at_floor(width: int, height: int) -> bool:
    """22.2 [U Q887, Q888]: a mode below 640 wide or 360 high is ignored, as a mode below 30 fps is (640x480 and 640x360
    pass). The one place of the rule on the server [YQN1 1]; the UI has the same two numbers (`resolution-floor.ts`)."""
    return width >= 640 and height >= 360


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
        if mode.format == "MJPG" and at_floor(mode.fps) and size_at_floor(mode.width, mode.height):
            rates.setdefault((mode.width, mode.height), set()).add(round(mode.fps, 2))
    sizes = sorted(rates, key=lambda size: (-size[0] * size[1], -size[0]))
    return [CaptureMode(width=w, height=h, framerates=sorted(rates[w, h])) for w, h in sizes]


def _synthesized(native: list[NativeMode], index: int) -> bool:
    """7.4 [agent 19]: an NV12 type immediately before an MJPG type of the same size and rate; Media Foundation made it."""
    mode = native[index]
    after = native[index + 1] if index + 1 < len(native) else None
    return (mode.format == "NV12" and after is not None and after.format == "MJPG"
            and (after.width, after.height, after.fps_num, after.fps_den)
            == (mode.width, mode.height, mode.fps_num, mode.fps_den))


def capture_modes(native: list[NativeMode]) -> list[CaptureModeEntry]:
    """The full mode list of 7.4 and 22.2 [3WCA 2]: an exact duplicate once; sizes as 7.3; for one size the rounded
    rates ascend; for one size and rounded rate MJPG first, then the native list order. No synthesized NV12."""
    kept: dict[NativeMode, int] = {}
    for index, mode in enumerate(native):
        if mode not in kept and not _synthesized(native, index):
            kept[mode] = index
    order = sorted(kept, key=lambda m: (-m.width * m.height, -m.width, round(m.fps, 2), m.format != "MJPG", kept[m]))
    return [CaptureModeEntry(width=m.width, height=m.height, fps_num=m.fps_num, fps_den=m.fps_den,
                             framerate=round(m.fps, 2), format=m.format, uncompressed=m.format in UNCOMPRESSED,
                             selectable=_reason(m) is None, reason=_reason(m))
            for m in order]


def _reason(mode: NativeMode) -> str | None:
    """7.4: why a mode of `capture_modes` is not selectable; the size before the rate [YQN1 2]."""
    if mode.format in NEVER_OPENED:
        return "never opened"
    if not size_at_floor(mode.width, mode.height):
        return "below 640x360"
    return None if at_floor(mode.fps) else "below 30 fps"


def native_from_capture_modes(entries: list[CaptureModeEntry]) -> list[NativeMode]:
    """The native types that `capture_modes` lists, for the whole-request check (7.5 [agent 20], 22.2 [N72V 3])."""
    return [NativeMode(e.width, e.height, e.fps_num, e.fps_den, e.format) for e in entries]


def choose_mode(native: list[NativeMode], request: CaptureRequest) -> NativeMode:
    """The mode choice of 7.5, with the raw-mode open of 22.2 [Q807]. Never a synthesized NV12 type (13.1).
    Raises `CaptureFailure` with stage "set mode"."""
    if not size_at_floor(request.width, request.height):
        raise CaptureFailure("set mode", NO_SIZE_MODE, code="below-floor")  # 22.2 [YQN1 3]
    native = [m for k, m in enumerate(native) if not _synthesized(native, k)]
    if request.capture_fourcc == "MJPG":
        at_size = [m for m in native if (m.width, m.height) == (request.width, request.height) and at_floor(m.fps)]
        if not any(m.format == "MJPG" for m in at_size):
            raw = next((fmt for fmt in RAW_ORDER if any(m.format == fmt for m in at_size)), None)
            if raw is not None:  # Q807: no MJPG mode at the floor at this size, but a raw mode there
                request = dataclasses.replace(request, capture_fourcc=raw)
    sized = [m for m in native
             if (m.width, m.height, m.format) == (request.width, request.height, request.capture_fourcc)]
    if request.framerate in (-1, 0):
        rate = auto_rate([m.fps for m in sized])
        if rate is None:
            raise CaptureFailure("set mode", NO_FLOOR_MODE, code="below-floor")
        return next(m for m in sized if m.fps == rate)
    near = [m for m in sized if abs(m.fps - request.framerate) <= 0.5]
    if not near and sized and not any(at_floor(m.fps) for m in sized):
        raise CaptureFailure("set mode", NO_FLOOR_MODE, code="below-floor")  # U11: the size has no mode at the floor at all
    if not near:
        listed = json.dumps([mode.model_dump() for mode in supported_modes(native)])
        raise CaptureFailure("set mode", f"no {request.capture_fourcc} mode at {request.width}x{request.height} "
                                         f"near {request.framerate:g} fps; the camera has {listed}", code="no-mode")
    chosen = min(near, key=lambda m: abs(m.fps - request.framerate))  # a tie: the first in the list (D15)
    if not at_floor(chosen.fps):
        raise CaptureFailure("set mode", NO_FLOOR_MODE, code="below-floor")
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
