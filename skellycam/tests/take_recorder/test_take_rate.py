"""The rate of a take in the stop response (specs/recorder.md 8.2; a decision of the user of 2026-11-23, Q609).

`mean_framerate` is the rate of the take: frames divided by the elapsed time. For each camera, F is the group frames
from its first to its last row that is not `missing`, and T is the time between the arrival times of these two
rows; the group value is the sum of F over the sum of T. The median stays only in the figures of each frame
interval (`framerate_stats`, `frame_duration_stats`).
"""

import math

import pytest

from skellycam.tests.take_recorder.rec_api import rec_module
from skellycam.tests.take_recorder.test_review_fixes import write_sidecar

GRID_NS = 16_000_000  # the arrival times of a generic camera fall on a grid of about 16 ms


def fields_of(tmp_path, cameras):
    stop_stats = rec_module("stop_stats")
    paths = []
    for index, rows in enumerate(cameras):
        path = tmp_path / f"c{index}.csv"
        write_sidecar(path, rows)
        paths.append(path)
    return stop_stats.stop_response_fields(paths, recording_name="t", recording_path=tmp_path,
                                           frame_count=max(len(rows) for rows in cameras))


def test_the_take_rate_on_a_16_ms_grid_is_the_rate_of_the_take(tmp_path):
    """Q609 (the real-camera run of 2026-11-23: `framerate_stats.median` 31.24 for a take at 30.02 fps): two
    cameras deliver 30.02 frames/s for 30 s, and each arrival time falls on the 16 ms grid. `mean_framerate` is
    30.02 to 0.02; the median of the rates of each frame is not the rate of the take (its intervals are 16, 32 or
    48 ms). This test passes with the rule of before too: both cameras have the same length."""
    period_ns = 1e9 / 30.02
    cameras = [[((round((k * period_ns + offset) / GRID_NS) * GRID_NS), False) for k in range(901)]
               for offset in (0, 5_000_000)]
    fields = fields_of(tmp_path, cameras)
    assert fields["mean_framerate"] == pytest.approx(30.02, abs=0.02)
    assert fields["framerate_stats"]["median"] == pytest.approx(31.25, abs=0.01)  # a figure of each interval


def test_a_camera_killed_after_its_first_frames_does_not_make_the_take_rate(tmp_path):
    """Q609 and B2 of ADR-TFD7 (one run gave 136 fps after a killed camera): camera 0 records 300 frames at 30 fps
    (10 s). Camera 1 gives two frames 1 ms apart, then its process is killed: each later row is `missing`.
    Before, the group value was the mean of the rates of the cameras: (30 + 1000) / 2 = 515 fps. Now it is the
    sum of the frames over the sum of the times: (300 + 1) / (10.0 + 0.001) s, about 30.1 fps."""
    period = 1e9 / 30
    live = [(round(k * period), False) for k in range(301)]
    killed = [(0, False), (1_000_000, False)] + [(None, True)] * 299
    fields = fields_of(tmp_path, [live, killed])
    assert 29.9 <= fields["mean_framerate"] <= 30.2, fields["mean_framerate"]


def test_a_long_gap_of_one_camera_lowers_the_take_rate_to_its_frames_over_its_time(tmp_path):
    """Q609: one camera stalls 5 s in the middle of a take of 10 s at 30 fps (its row after the stall has the late
    arrival time). The rate of the take is its frames over its elapsed time: 150 frames in 10 s, 15 fps; a value
    of each frame interval does not hide the stall. One camera: this test passes with the rule of before too."""
    period = 1e9 / 30
    rows = [(round(k * period), False) for k in range(76)]
    rows += [(round(5e9 + k * period), False) for k in range(76, 151)]
    fields = fields_of(tmp_path, [rows])
    assert fields["mean_framerate"] == pytest.approx(150 / ((5e9 + 150 * period) / 1e9), abs=0.01)
    assert not math.isnan(fields["frame_duration_stats"]["max"])
