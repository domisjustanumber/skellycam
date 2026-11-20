"""Record twice on live file-backed cameras on the shared loop, using real finalization and playback.

A camera that fails during a recording is `dead`; the other cameras record on, and the stop returns
the recording with the dead camera in `dead_cameras` (specs/windows-capture.md, D38 and U4).
T-CAP-35 and T-CAP-103 check that case.
"""

import asyncio
import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np
import pytest

from skellycam.core.recorders.videos.recording_info import RecordingInfo
from skellycam.core.recorders.videos.video_associations import VideoAssociations
from skellycam.core.timestamps.recording_timing_reader import (
    TimingFileKind,
    read_recording_timing,
    recorded_camera_timing_path,
    recorded_multiframe_timing_path,
)
from skellycam.tests.reference_recordings.datasets import TEST, acquire
from skellycam.tests.reference_recordings.test_concurrent_camera_replay import Replay, wait_until


def fingerprint(folder):
    return {path.relative_to(folder): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.rglob("*") if path.is_file()}


def assert_saved_frames(video_path, source_path, sfns):
    """Check every saved frame against the frame of the original video at its source frame number."""
    assert sfns and sfns == list(range(sfns[0], sfns[0] + len(sfns))), "the recorded video frames are not contiguous"
    saved = cv2.VideoCapture(str(video_path))
    source = cv2.VideoCapture(str(source_path))
    try:
        assert saved.isOpened() and source.isOpened()
        for _ in range(sfns[0]):
            assert source.grab()
        for number in sfns:
            ok, actual = saved.read()
            source_ok, expected = source.read()
            assert ok and source_ok, f"Missing saved frame of video frame {number}: {video_path}"
            assert actual.shape == expected.shape
            # The whole image: the shared loop stamps no text (U2).
            difference = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
            assert float(difference.mean()) < 8, (video_path, number)
        assert not saved.read()[0], f"Unexpected extra frames: {video_path}"
    finally:
        saved.release()
        source.release()


def recorded_numbers(info, camera_id):
    """The `connection_frame_number` of each row of the timing file of a camera."""
    timing_path = recorded_camera_timing_path(recording_folder=Path(info.full_recording_path), camera_id=camera_id)
    assert timing_path is not None
    with timing_path.open(newline="") as stream:
        return [int(row["connection_frame_number"]) for row in csv.DictReader(stream)]


def assert_completed_recording(info, configs, first, last, stats, replay, client):
    folder = Path(info.full_recording_path)
    numbers = list(range(first, last))
    assert stats.recording_info == info
    assert stats.number_of_cameras == 3
    assert stats.number_of_frames == len(numbers)
    metadata = json.loads(Path(info.recording_info_path).read_text())
    assert metadata["recording_uuid"] == info.recording_uuid
    assert set(metadata["camera_configs"]) == set(configs)
    associations = VideoAssociations.from_recording_folder(recording_folder=folder)
    assert associations is not None
    videos = associations.resolve_paths(video_folder=Path(info.videos_folder))
    assert set(videos) == set(configs)
    expected_playback_times = {}
    for camera_id, video in videos.items():
        assert video == Path(info.video_file_path_from_camera_config(configs[camera_id])).resolve()
        assert_saved_frames(video, replay.paths[camera_id], replay.recorded_sfns(camera_id, first, last))
        timing_path = recorded_camera_timing_path(recording_folder=folder, camera_id=camera_id)
        assert timing_path is not None
        timing = read_recording_timing(path=timing_path, kind=TimingFileKind.CAMERA)
        assert list(timing) == list(range(len(numbers)))
        expected_playback_times[video.name] = list(timing.values())
        assert recorded_numbers(info, camera_id) == numbers
    multiframe_path = recorded_multiframe_timing_path(recording_folder=folder)
    assert multiframe_path is not None
    multiframe = read_recording_timing(path=multiframe_path, kind=TimingFileKind.MULTIFRAME)
    assert list(multiframe) == list(range(len(numbers)))
    np.testing.assert_allclose(list(multiframe.values()), np.mean(list(expected_playback_times.values()), axis=0))
    assert Path(info.timestamp_stats_text_file_path).stat().st_size > 0
    assert json.loads(Path(info.timestamp_stats_json_file_path).read_text())["number_of_frames"] == len(numbers)

    params = {"recording_parent_directory": info.recording_directory}
    base = f"/skellycam/playback/{info.recording_name}"
    response = client.get(f"{base}/videos", params=params)
    assert response.status_code == 200, response.text
    assert {item["filename"] for item in response.json()} == set(expected_playback_times)
    response = client.get(f"{base}/timestamps", params=params)
    assert response.status_code == 200, response.text
    assert response.json() == {"timestamps": expected_playback_times, "warnings": []}
    video = videos["0"]
    response = client.get(f"{base}/videos/{video.name}", params=params)
    assert response.status_code == 200, response.text
    assert response.content == video.read_bytes()


@pytest.mark.real_data
async def test_recording_lifecycle(monkeypatch, client):
    paths = acquire(TEST)
    root = Path.home() / "freemocap_data" / "testing" / "skellycam"
    root.mkdir(parents=True, exist_ok=True)
    warning = root / "FILES_IN_THIS_FOLDER_GET_DELETED_AUTOMATICALLY_DO_NOT_PUT_ANYTHING_YOU_CARE_ABOUT_HERE.txt"
    warning.write_text("Disposable SkellyCam test outputs. Source and prepared recordings are kept elsewhere.\n")
    replay = Replay(monkeypatch, paths)
    with TemporaryDirectory(prefix="recording-lifecycle-", dir=root) as temporary:
        async with replay.running() as group:
            orchestrator = group.cameras.orchestrator
            workers = tuple(group.cameras.camera_workers.values())
            await wait_until(lambda: replay.fewest() >= 10, replay.problems, "initial frames")
            first_snapshot = None
            first_folder = None
            previous_last = -1
            for session in range(2):
                info = RecordingInfo(recording_name=f"session-{session}", recording_directory=temporary)
                await asyncio.wait_for(group.start_recording(info), timeout=10)
                first = orchestrator.first_recording_frame_number.value
                assert first > previous_last
                await wait_until(lambda: replay.fewest() >= first + 15, replay.problems, "recorded frames")
                returned_info, stats = await asyncio.wait_for(group.stop_recording(), timeout=30)
                assert returned_info == info
                last = orchestrator.last_recording_frame_number.value
                assert group.alive
                assert not any(status.recording_in_progress.value for status in orchestrator.camera_statuses.values())
                # Demonstrate capture continues after stop before pausing for slow validation.
                before = replay.fewest()
                await wait_until(lambda: replay.fewest() >= before + 3, replay.problems, "capture after stop")
                await group.cameras.pause(await_paused=True)
                assert_completed_recording(info, group.configs, first, last, stats, replay, client)
                assert tuple(group.cameras.camera_workers.values()) == workers
                assert all(worker.is_alive() for worker in workers)
                await group.cameras.unpause(await_unpaused=True)  # a record start needs each camera ready (8.3)
                previous_last = last
                if session == 0:
                    first_folder = Path(info.full_recording_path)
                    first_snapshot = fingerprint(first_folder)
                else:
                    assert fingerprint(first_folder) == first_snapshot
    assert not Path(temporary).exists()
