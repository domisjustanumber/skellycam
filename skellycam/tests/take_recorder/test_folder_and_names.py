"""T-REC-01 to T-REC-03: the take folder, the refusals of start_take, keys and labels.

specs/recorder.md, sections 4.2, 6.1 and 6.2.
"""

import re

import pytest

from skellycam.tests.take_recorder import sidecar_check
from skellycam.tests.take_recorder.rec_api import (
    MEDIA, WRITER, Run, camera_key, camera_label, fixed_clock, rec, simple_take, snapshot, take_camera, tree)


def test_t_rec_01_exact_files_of_the_take_folder(tmp_path, runs):
    """T-REC-01 [SFF-716, SFF-719, SFF-722, R5]: two cameras, 100 frames each. The take folder holds
    exactly the files and folders of 6.1, with their exact names, and nothing else: no MP4, no WAV,
    no `timestamps/` folder, no other CSV, no statistics file, no recording info JSON, no
    `synchronized_videos_README.md`, no `.tmp` file."""
    run = simple_take(tmp_path / "take", runs)
    labels = [camera_label("0a1b"), camera_label("ff00")]
    expected = sorted([".processing.lock", "recording_manifest.json", "take_info.json", f"{MEDIA}/"]
                      + [f"{MEDIA}/take.{label}.{ext}" for label in labels for ext in ("mkv", "csv")])
    assert tree(run.folder) == expected


BAD_NAMES = ["", "a" * 129, ".", "a.b", *[f"a{c}b" for c in '/\\:*?"<>|'], "a\x01b", "a\x7fb", " a",
             "CON", "con", "com1", "LPT9", "nul", "Aux"]


@pytest.mark.parametrize("name", BAD_NAMES, ids=lambda n: repr(n)[:20])
def test_t_rec_02_refuses_a_bad_recording_name(tmp_path, name):
    """T-REC-02 [SFF-715]: each bad `<rec>` raises `ValueError` before any write. No file or
    folder is created or changed."""
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        rec().start_take(tmp_path / "take", name, [take_camera("0a1b")], writer=WRITER, clock=fixed_clock())
    assert snapshot(tmp_path) == before


def test_t_rec_02_accepts_a_name_of_128_bytes(tmp_path, runs):
    """T-REC-02 [SFF-715]: the limit is 128 bytes of UTF-8 (a check that the refusal is not too wide)."""
    name = "é" * 64  # 128 bytes
    run = Run(tmp_path / "take", [take_camera("0a1b")], name=name)
    runs.append(run)
    run.give("0a1b", 0)
    run.finish(1)
    assert run.manifest()["recording_name"] == name and run.csv("0a1b").is_file()


def test_t_rec_02_refuses_a_folder_that_holds_a_file(tmp_path):
    """T-REC-02 [SFF-719, agent 16]: the take folder must not exist or must be empty."""
    folder = tmp_path / "take"
    folder.mkdir()
    (folder / "other.txt").write_bytes(b"x")
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        rec().start_take(folder, "take", [take_camera("0a1b")], writer=WRITER, clock=fixed_clock())
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(("rate", "capture_format"), [
    ((1001, 1), "MJPG"),  # above 1000 frames per second [SFF-736]
    ((0, 1), "MJPG"),  # num outside 1 to 2^20 [SFF-750]
    ((2**20 + 1, 2**20), "MJPG"),
    ((30, 2**20 + 1), "MJPG"),
    ((30, 0), "MJPG"),
    ((30, 1), "H264"),  # [SFF-734]
], ids=["1001_1", "0_1", "num_2^20+1", "den_2^20+1", "den_0", "h264"])
def test_t_rec_02_refuses_a_bad_rate_or_h264(tmp_path, rate, capture_format):
    """T-REC-02 [SFF-736, SFF-750, SFF-734]: each raises `ValueError`; no file or folder is made.
    The second camera is good, so the refusal is for the one bad camera."""
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        cameras = [take_camera("0a1b"), take_camera("ff00", rate=rate, capture_format=capture_format)]
        rec().start_take(tmp_path / "take", "take", cameras, writer=WRITER, clock=fixed_clock())
    assert snapshot(tmp_path) == before


def test_t_rec_03_keys_labels_and_manifest_cameras(tmp_path, runs):
    """T-REC-03 [R8, C3, SFF-720, SFF-723, F-6]: `camera_key` and `camera_label` follow 6.2; the
    label starts with `camera_id` and has the form of SFF-753; the file names use the label; the
    manifest `cameras` items are in the order of `group_position` with the exact paths;
    `key_origin` is `"provisional"`."""
    run = simple_take(tmp_path / "take", runs, frames=3)
    manifest, info = run.manifest(), run.info()
    for position, camera_id in enumerate(("0a1b", "ff00")):
        key, label = camera_key(camera_id), camera_label(camera_id)
        assert re.fullmatch(r"[0-9a-f]{16}", key) and label == key[:6] and label.startswith(camera_id)
        assert re.fullmatch(r"[0-9a-f]{6,8}", label)  # SFF-753 form
        item = manifest["cameras"][position]
        assert item == {"camera_key": key, "camera_label": label, "group_position": position,
                        "video": f"{MEDIA}/take.{label}.mkv", "timing": f"{MEDIA}/take.{label}.csv",
                        "calibration_camera": None}
        assert run.mkv(camera_id).is_file() and run.csv(camera_id).is_file()
        header = sidecar_check.read(run.csv(camera_id)).header
        assert (header["camera_key"], header["camera_label"], header["group_position"]) == (key, label, str(position))
        assert info["camera_configs"][key]["key_origin"] == "provisional"
        assert info["camera_configs"][key]["camera_label"] == label
    assert list(info["camera_configs"]) == [camera_key("0a1b"), camera_key("ff00")]
