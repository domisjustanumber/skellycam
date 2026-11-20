"""The text report of the recording statistics when the stage times do not add up to a positive time.

With a source that does not stamp the retrieve (Media Foundation, the fake source), two stage times
are a clock value with a minus sign and a clock value. Their sum can be zero or negative. The report
must then give 0.0 %, not a beartype error that makes the record stop return HTTP 500 (CI run of
d8989972d). The test sets the medians, so it does not depend on the clock of the machine.
"""

import numpy as np
import pytest

from skellycam.core.recorders.videos.recording_info import RecordingInfo
from skellycam.core.timestamps.numpy_timestamps.calculate_timestamps_numpy import calculate_statistics
from skellycam.core.timestamps.recording_timestamp_stats import RecordingTimestampsStats

STAGES = ("during_frame_grab_ms", "idle_before_retrieve_ms", "during_frame_retrieve_ms",
          "idle_before_copy_to_camera_shm_ms", "during_copy_to_camera_shm_ms",
          "idle_before_frame_record_ms", "during_frame_record_ms")


def stats_with_stage_medians(tmp_path, stage_ms):
    def of(value):
        return calculate_statistics(data=np.array([value, value], dtype=np.float64), axis=0)

    fields = {name: of(value) for name, value in zip(STAGES, stage_ms, strict=True)}
    return RecordingTimestampsStats(
        recording_info=RecordingInfo(recording_name="stats", recording_directory=str(tmp_path)),
        number_of_cameras=2, number_of_frames=2, total_duration_sec=1.0, framerate_stats=of(30.0),
        frame_duration_stats=of(33.3), inter_camera_grab_range_ms=of(0.0), idle_before_frame_grab_ms=of(0.0),
        total_frame_processing_time_ms=of(0.0), total_camera_idle_time_ms=of(0.0), **fields)


@pytest.mark.parametrize("stage_ms", [
    pytest.param((0.0,) * 7, id="all zero"),
    pytest.param((0.0, -5000.0, 0.0, 4999.0, 0.1, 0.1, 0.1), id="negative sum"),
])
def test_report_with_no_positive_stage_total(tmp_path, stage_ms):
    report = str(stats_with_stage_medians(tmp_path, stage_ms))
    assert "0.0%" in report
