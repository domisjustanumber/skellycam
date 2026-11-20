"""The fields of the stop response, from the timing sidecars (specs/recorder.md, section 8.2)."""
import logging
import math
import statistics

from skellycam.core.take_recorder.sidecar import MISSING, read_strict

logger = logging.getLogger(__name__)


def duration_s(rows_per_camera) -> float | None:
    """SFF-728 with F-1: the largest `arrival_ns` of the last row that holds one, of each sidecar, as
    whole thousandths of a second (rounded half up). None when no row holds a time."""
    last = [next((r.arrival_ns for r in reversed(rows) if r.arrival_ns is not None), None) for rows in rows_per_camera]
    last = [ns for ns in last if ns is not None]
    return ((max(last) + 500_000) // 10**6) / 1000 if last else None


def _stats(values) -> dict:
    if not values:
        return {"median": math.nan, "mean": math.nan, "std": math.nan, "min": math.nan, "max": math.nan}
    return {"median": statistics.median(values), "mean": statistics.fmean(values), "std": statistics.pstdev(values),
            "min": min(values), "max": max(values)}


def _mean(values) -> float:
    return round(statistics.fmean(values), 2) if values else math.nan


def _per_frame(csv_paths):
    rows_per_camera = [read_strict(path).rows for path in csv_paths]
    times = [[None if r.flags & MISSING else r.arrival_ns for r in rows] for rows in rows_per_camera]
    rates, durations, ranges = [], [], []
    for k in range(max((len(t) for t in times), default=0)):
        live = [t[k] for t in times if k < len(t) and t[k] is not None]
        if live:
            ranges.append((max(live) - min(live)) / 1e6)
        # A pair whose time does not increase (two equal arrival times) has no rate.
        pairs = [(t[k - 1], t[k]) for t in times
                 if 0 < k < len(t) and t[k - 1] is not None and t[k] is not None and t[k] > t[k - 1]]
        if pairs:
            rates.append(statistics.fmean([1e9 / (b - a) for a, b in pairs]))
            durations.append(statistics.fmean([(b - a) / 1e6 for a, b in pairs]))
    return duration_s(rows_per_camera), rates, durations, ranges


def stop_response_fields(csv_paths, *, recording_name, recording_path, frame_count) -> dict:
    """Each field of `StopRecordingResponse`. A `missing` row is left out of each statistic. A value
    with no data is NaN (a float field that JSON gives as null); a fault is logged, never raised."""
    try:
        duration, rates, durations, ranges = _per_frame(csv_paths)
    except Exception:  # the stop request must not fail because of its statistics
        logger.exception("the stop statistics of %s could not be computed", recording_name)
        duration, rates, durations, ranges = None, [], [], []
    return {
        "recording_name": recording_name,
        "recording_path": str(recording_path),
        "number_of_cameras": len(csv_paths),
        "number_of_frames": frame_count,
        "total_duration_sec": math.nan if duration is None else duration,
        "mean_framerate": _mean(rates),
        "mean_inter_camera_sync_ms": _mean(ranges),
        "framerate_stats": _stats(rates),
        "frame_duration_stats": _stats(durations),
        "inter_camera_grab_range_ms_stats": _stats(ranges),
    }
