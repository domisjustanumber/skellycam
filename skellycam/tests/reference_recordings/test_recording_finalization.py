"""Decode every accepted frame after a close of the group during a recording (the shared loop).

A camera that fails during a recording is `dead`, and its files are finished while the other cameras
record on (specs/windows-capture.md, D38 and U4). T-CAP-35 and T-CAP-103 check that case.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from skellycam.core.recorders.videos.recording_info import RecordingInfo
from skellycam.tests.reference_recordings.datasets import TEST, acquire
from skellycam.tests.reference_recordings.test_concurrent_camera_replay import Replay, wait_until
from skellycam.tests.reference_recordings.test_recording_lifecycle import assert_saved_frames, recorded_numbers


@pytest.mark.real_data
async def test_recorded_videos_are_finalized(monkeypatch):
    root = Path.home() / "freemocap_data" / "testing" / "skellycam"
    root.mkdir(parents=True, exist_ok=True)
    warning = root / "FILES_IN_THIS_FOLDER_GET_DELETED_AUTOMATICALLY_DO_NOT_PUT_ANYTHING_YOU_CARE_ABOUT_HERE.txt"
    warning.write_text("Disposable SkellyCam test outputs. Source and prepared recordings are kept elsewhere.\n")
    replay = Replay(monkeypatch, acquire(TEST))
    # A fresh directory prevents old files from satisfying assertions. It is
    # removed on both success and failure, after the harness joins every worker.
    with TemporaryDirectory(prefix="recording-finalization-", dir=root) as temporary:
        info = RecordingInfo(recording_name="replay", recording_directory=temporary)
        async with replay.running() as group:
            await wait_until(lambda: replay.fewest() >= 1, replay.problems, "each camera ready")
            await group.start_recording(info)
            await wait_until(lambda: min(map(len, replay.recorded.values())) >= 30, replay.problems,
                             "recorded frames")
        # The close stopped the recording and finished the files of each camera.
        for camera_id, config in replay.configs.items():
            assert recorded_numbers(info, camera_id) == [number for number, _ in replay.recorded[camera_id]]
            assert_saved_frames(info.video_file_path_from_camera_config(config), replay.paths[camera_id],
                                replay.recorded_sfns(camera_id))
    assert not Path(temporary).exists()
