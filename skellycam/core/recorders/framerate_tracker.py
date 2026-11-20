# skellycam/core/recorders/framerate_tracker.py
import itertools
from collections import deque
from dataclasses import dataclass

import msgspec
import numpy as np

MAX_FRAMERATE_TRACKER_WINDOW = 1000
FRAMERATE_UPDATE_INTERVAL = 1.0


class CurrentFramerate(msgspec.Struct):
    mean_frame_duration_ms: float
    mean_frames_per_second: float
    frame_duration_max: float
    frame_duration_min: float
    frame_duration_mean: float
    frame_duration_stddev: float
    frame_duration_median: float
    frame_duration_coefficient_of_variation: float
    calculation_window_size: int
    framerate_source: str = ""

    @classmethod
    def from_durations_ms(cls, durations_ms: np.ndarray, framerate_source: str) -> "CurrentFramerate":
        """Compute framerate statistics from an array of frame durations in milliseconds."""
        if len(durations_ms) < 1:
            raise ValueError(f"Need at least 1 duration to compute framerate, got {len(durations_ms)}")
        mean_dur = float(np.nanmean(durations_ms))
        if mean_dur <= 0:
            raise ValueError(f"Mean frame duration is non-positive ({mean_dur}), cannot compute framerate")
        std_dur = float(np.nanstd(durations_ms))
        return cls(
            mean_frame_duration_ms=mean_dur,
            mean_frames_per_second=1e3 / mean_dur,
            frame_duration_max=float(np.nanmax(durations_ms)),
            frame_duration_min=float(np.nanmin(durations_ms)),
            frame_duration_mean=mean_dur,
            frame_duration_stddev=std_dur,
            frame_duration_median=float(np.nanmedian(durations_ms)),
            frame_duration_coefficient_of_variation=std_dur / mean_dur,
            calculation_window_size=len(durations_ms),
            framerate_source=framerate_source,
        )


class ServerFramerateCalculator:
    """Compute true camera capture framerate from (frame_number, capture_timestamp_ns) pairs.

    frame_number increments by 1 for every camera capture at the hardware level.
    capture_timestamp_ns is perf_counter_ns at the moment of camera grab.
    When the websocket skips frames due to backpressure, frame_number jumps
    but we can still compute the true per-frame duration from the gap.
    """

    def __init__(self, source_name: str, max_observations: int = 200):
        self._source_name: str = source_name
        self._observations: deque[tuple[int, float]] = deque(maxlen=max_observations)
        self._per_frame_durations_ms: deque[float] = deque(maxlen=1000)

    def update(self, frame_number: int|np.integer, capture_timestamp_ns: int|float) -> None:
        if self._observations:
            prev_fn, prev_ts = self._observations[-1]
            frame_delta = frame_number - prev_fn
            if frame_delta > 0:
                per_frame_ns = (capture_timestamp_ns - prev_ts) / frame_delta
                per_frame_ms = per_frame_ns / 1e6
                # One duration entry per actual frame captured; at most maxlen, so a large jump is no long loop
                self._per_frame_durations_ms.extend(
                    itertools.repeat(per_frame_ms, min(frame_delta, self._per_frame_durations_ms.maxlen)))
        self._observations.append((frame_number, capture_timestamp_ns))

    @property
    def current_framerate(self) -> CurrentFramerate | None:
        if len(self._per_frame_durations_ms) < 2:
            return None
        durations = np.array(self._per_frame_durations_ms)
        return CurrentFramerate.from_durations_ms(
            durations_ms=durations,
            framerate_source=self._source_name,
        )

    def clear(self) -> None:
        """Reset accumulated durations. Keep the last observation, so the next update() gives one interval."""
        while len(self._observations) > 1:
            self._observations.popleft()
        self._per_frame_durations_ms.clear()


@dataclass
class FramerateTrackers:
    backend: CurrentFramerate
    frontend: CurrentFramerate


@dataclass
class FramerateTracker:
    frame_durations_ns: deque[float]
    framerate_source: str
    _last_timestamp_ns: float | None

    @classmethod
    def create(cls, framerate_source: str, recency_window_size: int = MAX_FRAMERATE_TRACKER_WINDOW) -> "FramerateTracker":
        return cls(
            frame_durations_ns=deque(maxlen=recency_window_size),
            framerate_source=framerate_source,
            _last_timestamp_ns=None,
        )

    def update(self, timestamp_ns: int) -> None:
        if self._last_timestamp_ns is not None:
            self.frame_durations_ns.append(timestamp_ns - self._last_timestamp_ns)
        self._last_timestamp_ns = timestamp_ns

    def clear(self) -> None:
        self.frame_durations_ns.clear()
        self._last_timestamp_ns = None

    @property
    def has_data(self) -> bool:
        return len(self.frame_durations_ns) >= 1

    @property
    def current_framerate(self) -> CurrentFramerate:
        if not self.has_data:
            raise ValueError(f"No frame durations recorded yet for '{self.framerate_source}'")
        durations_ms = np.array(self.frame_durations_ns) / 1e6
        return CurrentFramerate.from_durations_ms(
            durations_ms=durations_ms,
            framerate_source=self.framerate_source,
        )

    def to_string_list(self) -> list[str]:
        current = self.current_framerate
        return [
            f"Mean Frame Duration (ms): {current.mean_frame_duration_ms:.2f}",
            f"Mean FPS: {current.mean_frames_per_second:.2f}",
            f"Min Frame Duration (ms): {current.frame_duration_min:.2f}",
            f"Max Frame Duration (ms): {current.frame_duration_max:.2f}",
            f"Median Frame Duration (ms): {current.frame_duration_median:.2f}",
            f"Frame Duration StdDev (ms): {current.frame_duration_stddev:.2f}",
        ]

    def __str__(self) -> str:
        return "\n".join(self.to_string_list())
