"""
Extracts per-camera frame times from the slot headers of the newest ring frames (spec 2.3, A5)
and packages them as JSON-serializable performance data for the frontend.

Structured for direct ingestion into Perspective tables on the frontend:
  - camera_lifecycle_rows: one row per camera per frame (flat, for Perspective)
  - inter_camera_sync: one row per multi-frame (inter-camera synchronization)
"""
import logging
import time

import numpy as np

from skellycam.api.websocket.websocket_message_types import WebsocketMessageType
from skellycam.core.ipc.frame_ring import NO_SAMPLE_NS, FrameRead
from skellycam.core.types.type_overloads import CameraIdString

logger = logging.getLogger(__name__)

# TODO - this prob should live somewhere else, but its working fine enough here
def _ns_to_ms(ns: int | float) -> float:
    return float(ns) / 1e6


def _safe_duration_ms(start_ns: int | float, end_ns: int | float) -> float:
    if start_ns and end_ns:
        return _ns_to_ms(end_ns - start_ns)
    return -1.0


def extract_performance_data_from_frames(
    latest_frames: dict[CameraIdString, FrameRead],
    session_start_perf_ns: int,
) -> dict:
    """
    Extract per-camera frame times from the ring frames of one frame number (`arrival_ns`,
    `sample_ns` and `published_ns` of the slot headers).

    Returns a JSON-serializable dict structured for Perspective table ingestion.
    """
    if not latest_frames:
        raise ValueError("latest_frames must not be empty")

    frame_numbers: list[int] = []
    per_camera_rows: list[dict] = []
    grab_timestamps_ns: list[float] = []

    now_perf_ns = time.perf_counter_ns()
    timestamp_ms = _ns_to_ms(now_perf_ns - session_start_perf_ns)

    for camera_id, read in latest_frames.items():
        frame_numbers.append(read.frame_number)
        grab_timestamps_ns.append(float(read.arrival_ns))
        sample_ns = read.sample_ns if read.sample_ns != NO_SAMPLE_NS else 0

        row = {
            "timestamp_ms": round(timestamp_ms, 3),
            "frame_number": read.frame_number,
            "camera_id": str(camera_id),
            "sample_to_arrival_ms": round(_safe_duration_ms(sample_ns, read.arrival_ns), 4),
            "arrival_to_published_ms": round(_safe_duration_ms(read.arrival_ns, read.published_ns), 4),
            "arrival_from_start_ms": round(_ns_to_ms(read.arrival_ns - session_start_perf_ns), 3),
        }
        per_camera_rows.append(row)

    # Inter-camera sync metrics
    grab_range_ms = 0.0
    grab_stddev_ms = 0.0
    if len(grab_timestamps_ns) > 1:
        grab_arr = np.array(grab_timestamps_ns, dtype=np.float64)
        grab_range_ms = round(_ns_to_ms(float(np.max(grab_arr) - np.min(grab_arr))), 4)
        grab_stddev_ms = round(_ns_to_ms(float(np.std(grab_arr))), 4)

    unique_frame_numbers = set(frame_numbers)
    frame_number = frame_numbers[0] if len(unique_frame_numbers) == 1 else max(frame_numbers)

    return {
        "message_type": WebsocketMessageType.PERFORMANCE_DATA,
        "frame_number": frame_number,
        "timestamp_ms": round(timestamp_ms, 3),
        "camera_lifecycle_rows": per_camera_rows,
        "inter_camera_sync": {
            "timestamp_ms": round(timestamp_ms, 3),
            "frame_number": frame_number,
            "grab_range_ms": grab_range_ms,
            "grab_stddev_ms": grab_stddev_ms,
            "num_cameras": len(latest_frames),
        },
    }
