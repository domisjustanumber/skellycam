"""The capture interface (specs/windows-capture.md, section 4; names of ADR-HP7D item 6).

This module does not import `comtypes`. Each system can import it.
"""

import dataclasses
import threading
from dataclasses import dataclass
from functools import partial
from typing import Protocol

import numpy as np

from skellycam.core.camera.capture.failure_codes import default_code

FIRST_FRAME_TIMEOUT_S = 5.0
BOUNDED_CALL_LIMIT_S = 5.0


@dataclass(frozen=True)
class CapturedFrame:
    """One frame that `read_frame` gives (4.2)."""
    payload: bytes | np.ndarray
    format: str
    arrival_ns: int
    sample_ns: int
    delivered_len: int
    driver_error: bool
    source_frame_number: int
    discontinuity: bool


@dataclass(frozen=True)
class OpenedMode:
    width: int
    height: int
    fps_num: int
    fps_den: int
    format: str
    device_path: str


@dataclass(frozen=True)
class CaptureRequest:
    """A framerate of -1 or 0 means "auto" (7.5)."""
    camera_id: str
    width: int
    height: int
    framerate: float
    capture_fourcc: str = "MJPG"


@dataclass(frozen=True)
class ControlSetting:
    """One item of `changes` of `set_controls`. A value of None does not change the value."""
    auto: bool
    value: int | None


@dataclass(frozen=True)
class ControlValue:
    present: bool
    auto: bool
    value: int | None


ControlState = dict[str, ControlValue]


class CaptureFailure(Exception):
    """A failure of a source, with a stage of section 12 and a code of unix-capture.md 4.6.3."""

    def __init__(self, stage: str, reason: str, *, hung: bool = False, code: str | None = None):
        super().__init__(reason)
        self.stage, self.reason, self.hung = stage, reason, hung
        self.code = code or default_code(stage, hung)

    def __reduce__(self):
        # Exception pickles only `args`; keep the stage, `hung` and the code across a process boundary.
        return partial(CaptureFailure, hung=self.hung, code=self.code), (self.stage, self.reason)


class CaptureSource(Protocol):
    """The four calls of 4.1 and `replaced_count`."""

    def open(self, request: CaptureRequest) -> OpenedMode: ...

    def read_frame(self, timeout_s: float) -> CapturedFrame | None: ...

    def set_controls(self, changes: dict[str, ControlSetting]) -> ControlState: ...

    def close(self) -> None: ...

    @property
    def replaced_count(self) -> int: ...


class CaptureWaitingPlace:
    """The waiting place of 4.3: at most one frame, and the newest frame wins.

    A replaced frame counts in `replaced`, and its discontinuity moves to the frame that replaces
    it. An error marker waits behind a frame that waits: `take` gives the frame, and each later
    `take` raises the failure. A put waits only for the lock.
    """

    def __init__(self):
        self._condition = threading.Condition()
        self._frame: CapturedFrame | None = None
        self._error: CaptureFailure | None = None
        self.replaced = 0

    def put(self, frame: CapturedFrame) -> None:
        with self._condition:
            if self._frame is not None:
                self.replaced += 1
                if self._frame.discontinuity and not frame.discontinuity:
                    frame = dataclasses.replace(frame, discontinuity=True)
            self._frame = frame
            self._condition.notify()

    def put_error(self, failure: CaptureFailure) -> None:
        with self._condition:
            self._error = failure
            self._condition.notify()

    def take(self, timeout_s: float) -> CapturedFrame | None:
        """The frame that waits, or None after `timeout_s`. Raises the failure of an error marker."""
        with self._condition:
            self._condition.wait_for(lambda: self._frame is not None or self._error is not None, timeout_s)
            frame, self._frame = self._frame, None
            if frame is None and self._error is not None:
                raise self._error
            return frame
