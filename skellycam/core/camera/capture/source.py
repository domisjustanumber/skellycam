"""The capture interface (specs/windows-capture.md, section 4; names of ADR-HP7D item 6).

This module does not import `comtypes`. Each system can import it.
"""

import dataclasses
import logging
import os
import threading
from collections import deque
from dataclasses import dataclass
from functools import partial
from typing import Protocol

import numpy as np

from skellycam.core.camera.capture.failure_codes import default_code

logger = logging.getLogger(__name__)
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
    """The four calls of 4.1, `replaced_count` and `diagnostics()` (unix-capture.md 4.2 item 2)."""

    def open(self, request: CaptureRequest) -> OpenedMode: ...

    def read_frame(self, timeout_s: float) -> CapturedFrame | None: ...

    def set_controls(self, changes: dict[str, ControlSetting]) -> ControlState: ...

    def close(self, restore: bool = True) -> None: ...
    # `restore=False`: the loop failed (unix-capture.md 4.7): no set and no read-back at the close

    @property
    def replaced_count(self) -> int: ...

    def diagnostics(self) -> dict: ...

    def exposure_range(self) -> tuple[int, int, int] | None: ...
    # (min, max, step) of the exposure control, on each source, read before the first set of the open; None: not known. The exposure
    # search tries only the values in it (camera-requests.md 1.3 item 1). Optional: the loop uses getattr.


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


# ----- diagnostics (specs/unix-capture.md 4.6) -----

CONTROL_NAMES = ("exposure", "gain", "focus", "white_balance", "power_line")
_CONTROL_FIELDS = ("present", "min", "max", "step", "default", "auto_supported", "native_id", "value", "auto", "set_rc",
                   "get_rc", "before", "before_auto", "route_proven")
HASH_COUNT = 30  # D-11
# The keys of the shared loop (4.2 item 3): D-10 and D-11.
LOOP_KEYS = ("decoded_by_skellycam", "encoded_by_skellycam",
             *(f"sha256_{i:02d}" for i in range(HASH_COUNT)), *(f"sha256_frame_{i:02d}" for i in range(HASH_COUNT)),
             "sha256_trigger", "dht_inserted", "dqt_sha256", "dqt_distinct", "dht_present")
SOURCE_KEYS = (
    "backend",
    "requested_fourcc", "granted_fourcc", "requested_w", "requested_h", "granted_w", "granted_h", "requested_fps_num",
    "requested_fps_den", "granted_fps_num", "granted_fps_den", "delivered", "video_settings",
    "bytesused_equals_payload",  # D-1
    "clock", "tstamp_src", "ts_conversion", "sample_time_kept", "sample_minus_arrival_p5_ms",
    "sample_minus_arrival_p50_ms", "sample_minus_arrival_p95_ms", "later_than_arrival", "frame_log",  # D-2
    "frames", "sequence_available", "sequence_gaps", "sequence_lost", "discontinuity_flags", "error_flag_frames",
    "zero_bytes", "drops_reported", "poll_timeouts", "format_changes", "long_intervals",
    "long_intervals_with_seq_gap",  # D-3
    *(f"{c}_{f}" for c in CONTROL_NAMES for f in _CONTROL_FIELDS),
    "exposure_unit", "exposure_native_at_m7", "control_path", "ae_off_ok", "af_off_ok", "ae_back_on_after_s",
    "restore_ok", "restore_failed",  # D-4
    "fail_code", "native_code", "native_domain", "call", "fail_stage", "failed_calls", "busy_call",  # D-5
    "t_enumerate_ms", "t_open_ms", "t_set_mode_ms", "t_buffers_ms", "t_stream_on_ms", "t_first_frame_ms",
    "t_controls_ms", "t_close_ms",  # D-6
    "id_source", "has_serial",  # D-7
    "access", "tcc", "center_stage", "portrait", "studio_light", "reactions", "edge_light",  # D-8
    "usb_alt",  # D-9
    "kernel", "driver", "nodrop_param", "clock_param", "hwtimestamps_param", "buffers_requested", "buffers_granted",
    "interval_types", "nodes_seen", "nodes_skipped_meta", "modes_listed", "mjpg_sizes",  # Linux
    "macos", "subtypes", "notifications_seen", "sync_clock_is_host",  # macOS
)
DIAGNOSTIC_KEYS = SOURCE_KEYS + LOOP_KEYS
# The subset of `CameraStatus.serialize()` and `app_state` (4.2 item 2): no `frame_log`, no hash.
COUNTER_KEYS = ("backend", "frames", "sequence_gaps", "sequence_lost", "discontinuity_flags", "error_flag_frames",
                "zero_bytes", "drops_reported", "poll_timeouts", "format_changes", "long_intervals",
                "long_intervals_with_seq_gap", "later_than_arrival", "decoded_by_skellycam", "encoded_by_skellycam",
                "dht_inserted", "restore_ok", "restore_failed", "fail_code")
FRAME_LOG_ROWS = 64
DIFFERENCES_KEPT = 256


def empty_diagnostics(backend: str | None = None) -> dict:
    """Every source key, null (4.6.1)."""
    return {**dict.fromkeys(SOURCE_KEYS), "backend": backend}


RESTORE_SETTING = "SKELLYCAM_RESTORE_CONTROLS"  # "0" turns the restore off, for a debug run only (4.7)
# 4.7 [NYT6]: camera_id -> the keeper of the shared record of the "before" values (the status of the camera, which
# the camera process puts here), with `restore_record()` and `set_restore_record(record)`. The record survives the
# camera process.
RESTORE_RECORDS: dict = {}


class ControlRestore:
    """The restore of the controls at the close (unix-capture.md 4.7), for one open of one camera.

    The source gives each read-back to `read` (the first one is the "before" state, taken before any set),
    each `changes` to `changed` before it sets them, the read-back after each set to `after_set`, and calls
    `restore` in its close, before the stream stops. `restore` sets each changed control back to its "before" value and auto flag (the one set that
    may turn the camera's own auto exposure on again), and reads it back. A failed restore is logged and
    counted; the close goes on. A hung call raises (6.6)."""

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.before: ControlState | None = None
        self.names: set[str] = set()
        self.ok: bool | None = None
        self.failed: int | None = None
        self._keeper = RESTORE_RECORDS.get(camera_id)
        self._set: dict[str, list] = {}  # name -> [auto, value] that this app set last (4.7) [NYT6]

    def read(self, state: ControlState) -> None:
        if self.before is not None:
            return
        self.before = dict(state)
        record = self._keeper.restore_record() if self._keeper is not None else None
        if not record:
            return
        # An earlier open got no restore (4.7) [NYT6]: a control that still holds the value that this app set last
        # takes its "before" value from the record; the record drops each other control.
        for name in record.get("names", ()):
            got, last, before = state.get(name), record.get("set", {}).get(name), record.get("before", {}).get(name)
            if got is not None and last is not None and before is not None and got.auto == last[0] and (
                    got.auto or got.value == last[1]):
                self.before[name] = ControlValue(*before)
                self.names.add(name)
                self._set[name] = last
        self._save()

    def changed(self, changes: dict) -> None:
        """Before the set (4.7): the record holds the names and the values that this app asks for."""
        asked = {name: [setting.auto, setting.value] for name, setting in changes.items()}
        if set(changes) <= self.names and all(self._set.get(name) == value for name, value in asked.items()):
            return
        self.names.update(changes)
        self._set.update(asked)
        self._save()

    def after_set(self, state: ControlState) -> None:
        """The read-back after a set: the value that the camera took is the value that this app set last."""
        took = {name: [state[name].auto, state[name].value] for name in self.names if name in state}
        if any(self._set.get(name) != value for name, value in took.items()):
            self._set.update(took)
            self._save()

    def _save(self) -> None:
        if self._keeper is None or self.before is None:
            return
        before = {name: [value.present, value.auto, value.value] for name, value in self.before.items()
                  if name in self.names}
        self._keeper.set_restore_record(
            dict(before=before, names=sorted(self.names), set=self._set) if self.names else {})

    def restore(self, set_controls) -> None:
        """`set_controls(changes) -> ControlState` sets the changes and reads the controls back."""
        if os.environ.get(RESTORE_SETTING) == "0" or not self.before:
            return
        failed = 0
        for name in sorted(self.names):
            before = self.before.get(name)
            if before is None or not before.present:
                continue
            try:
                got = set_controls({name: ControlSetting(auto=before.auto, value=before.value)}).get(name)
                problem = None if got is not None and got.auto == before.auto and (
                    before.auto or got.value == before.value) else f"it read back {got}"
            except CaptureFailure as failure:
                if failure.hung:
                    raise
                problem = failure.reason
            if problem is not None:
                failed += 1
                logger.warning(f"Camera {self.camera_id}: the restore of {name} at the close failed: {problem}")
        self.ok, self.failed = failed == 0, failed
        if self.ok and self._keeper is not None:
            self._keeper.set_restore_record({})  # the camera holds its own values again

    def fill(self, diagnostics: dict) -> None:
        diagnostics.update(restore_ok=self.ok, restore_failed=self.failed)
        for name, value in (self.before or {}).items():
            if name in CONTROL_NAMES:
                diagnostics.update({f"{name}_before": value.value, f"{name}_before_auto": value.auto})


class FrameLog:
    """D-2 and D-3 of the frames of one open: `frame_log` (the last 64 rows), the sample-minus-arrival
    percentiles of the last 256 differences, and `later_than_arrival`. The percentiles run only in `fill`."""

    def __init__(self, period_ns: int | None = None):
        self.rows = deque(maxlen=FRAME_LOG_ROWS)
        self.differences = deque(maxlen=DIFFERENCES_KEPT)
        self.later_than_arrival = 0
        self.period_ns, self.last_arrival_ns, self.long_intervals = period_ns, None, 0  # D-3: over 1.5 periods

    def add(self, source_frame_number: int, sequence: int | None, raw_ts_ns: int | None, arrival_ns: int,
            bytesused: int) -> None:
        self.rows.append([source_frame_number, sequence, raw_ts_ns, arrival_ns, bytesused])
        if self.period_ns and self.last_arrival_ns is not None:
            self.long_intervals += arrival_ns - self.last_arrival_ns > 1.5 * self.period_ns
        self.last_arrival_ns = arrival_ns
        if raw_ts_ns is not None:
            self.differences.append(raw_ts_ns - arrival_ns)
            self.later_than_arrival += raw_ts_ns > arrival_ns

    def fill(self, diagnostics: dict) -> None:
        diagnostics["frame_log"] = [list(row) for row in list(self.rows)]
        diagnostics["later_than_arrival"] = self.later_than_arrival
        if self.period_ns:
            diagnostics["long_intervals"] = self.long_intervals
        values = sorted(self.differences)
        for p in (5, 50, 95):
            diagnostics[f"sample_minus_arrival_p{p}_ms"] = (
                values[min(len(values) - 1, len(values) * p // 100)] / 1e6 if values else None)
