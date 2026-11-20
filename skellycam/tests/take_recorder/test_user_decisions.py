"""Tests of the decisions D1 and D3 of the user (2026-11-20, ADR-C6DE).

D1: a stall is no progress of the writer for the stall limit, not a total time. D3: a take folder
on a file system with a 4 GiB file size limit is refused. Synthetic frames only.
"""

import logging
import sys
import time
from pathlib import Path

import pytest

from skellycam.tests.take_recorder import sidecar_check
from skellycam.tests.take_recorder.rec_api import Frames, Run, rec, rec_module, run_in_thread, take_camera

LIMIT_S = 0.5


def small_run(tmp_path, runs, **kwargs):
    frames = Frames(320, 240)
    camera = take_camera("0a1b", width=320, height=240, layout=rec().parse_sof(frames(0)))
    run = Run(tmp_path / "take", [camera], frames=frames, queue_seconds=0.3, stall_limit_s=LIMIT_S, **kwargs)
    runs.append(run)
    return run


def test_d1_a_slow_disk_ends_the_take_normally(tmp_path, runs, disk):
    """D1: each MKV write takes 0.17 s, so the drain of a full queue (9 items) takes about 3 times the
    stall limit. The writer makes progress at each write, so no `give` raises, `end` waits for the
    writer, and the files are complete with no `disk stall`."""
    def slow(handle, data):
        if handle.kind == ".mkv":
            time.sleep(0.17)

    run = small_run(tmp_path, runs)
    disk.after_write = slow
    for k in range(30):
        run.give("0a1b", k)
    started = time.monotonic()
    result = run.end(30)["0a1b"]
    took = time.monotonic() - started
    assert took > 2 * LIMIT_S, "the end of a full queue took longer than the stall limit"
    assert result.error is None and result.files_closed and result.rows == 30
    run.finish(30)
    sidecar = sidecar_check.read(run.csv("0a1b"))
    assert len(sidecar.rows) == 30 and sidecar.footer_words() == ["end"]
    assert run.manifest()["warnings"] == []


def test_d1_a_stopped_disk_gives_disk_stall_at_the_limit(tmp_path, runs, disk):
    """D1: the writer is held (no progress). A `give` on the full queue raises `RecorderStalled` at
    the stall limit, and `end` returns `disk stall` at the stall limit."""
    run = small_run(tmp_path, runs)
    rule = disk.hold(".mkv")
    writer, k = run.writers["0a1b"], 0
    while not writer.queue.full():
        run.give("0a1b", k)
        k += 1
        if k == 3:
            assert disk.wait_holding(rule, 10.0)
    started = time.monotonic()
    thread, box = run_in_thread(run.give, "0a1b", k)
    thread.join(10.0)
    waited = time.monotonic() - started
    assert isinstance(box.get("error"), rec().RecorderStalled)
    assert 0.9 * LIMIT_S <= waited <= 1.5 * LIMIT_S
    started = time.monotonic()
    result = run.end(k)["0a1b"]
    assert result.error == "disk stall" and not result.files_closed
    assert time.monotonic() - started <= 1.5 * LIMIT_S


@pytest.mark.recorder_slow
def test_d1_the_scaled_10_s_stall_case(tmp_path, runs, children):
    """D1 with T-REC-STALL: the 10 s case scaled by 10 (a stall of 1.0 s, a queue of 0.3 s, a limit of
    1.0 s). The queue fills, `give` waits about 0.7 s, no frame is lost and the rows are equal. The
    15 s case is the short form of T-REC-STALL."""
    from skellycam.tests.take_recorder.test_benchmarks import paced_take, stall_pass_parts

    out = paced_take(tmp_path, runs, children, groups=[(2, 1280, 720, (30, 1))], seconds=6.0, stall=(0, 30, 1.0),
                     queue_seconds=0.3, stall_limit_s=1.0)
    stall_pass_parts(out, 1.0, 0.3, 1.0)


REFUSED = ["FAT32", "FAT", "FAT16", "vfat", "msdos"]  # Windows, Windows, Windows, Linux, macOS names
ACCEPTED = ["exFAT", "exfat", "NTFS", "ReFS", "ext4", "btrfs", "apfs", "hfs", "fuseblk"]


@pytest.mark.parametrize("name", REFUSED)
def test_d3_a_fat_folder_is_refused(tmp_path, monkeypatch, name):
    """D3: a take folder on a FAT file system is refused before any write, with a text that names the
    file system and the 4 GiB limit."""
    folder_files = rec_module("folder_files")
    monkeypatch.setattr(folder_files, "file_system", lambda path: name)
    with pytest.raises(ValueError, match="4 GiB") as raised:
        rec().start_take(tmp_path / "take", "take", [take_camera("0a1b")], writer="skellycam 2.0.0")
    assert "FAT" in str(raised.value) and "Choose a folder on another disk" in str(raised.value)
    assert not (tmp_path / "take").exists()


@pytest.mark.parametrize("name", [*ACCEPTED, None])
def test_d3_other_file_systems_are_accepted(tmp_path, runs, monkeypatch, caplog, name):
    """D3: exFAT and the other file systems are accepted. An unknown file system is accepted with one
    warning in the log."""
    folder_files = rec_module("folder_files")
    monkeypatch.setattr(folder_files, "file_system", lambda path: name)
    with caplog.at_level(logging.WARNING):
        run = Run(tmp_path / "take", [take_camera("0a1b")])
    runs.append(run)
    warned = [r for r in caplog.records if r.name.startswith("skellycam.core.take_recorder") and "file system" in r.message]
    assert len(warned) == (1 if name is None else 0)
    run.give("0a1b", 0)
    run.finish(1)
    assert run.manifest()["state"] == "finished"


MOUNTINFO = "\n".join([
    "22 1 8:2 / / rw,relatime shared:1 - ext4 /dev/sda2 rw",
    "40 22 8:17 / /media/usb rw,relatime shared:20 - vfat /dev/sdb1 rw,fmask=0022",
    "41 22 8:33 / /media/my\\040disk rw,relatime shared:21 - exfat /dev/sdc1 rw",
])


@pytest.mark.parametrize(("path", "expected"), [
    ("/home/user/takes", "ext4"), ("/media/usb/takes/t1", "vfat"), ("/media/usb", "vfat"),
    ("/media/my disk/takes", "exfat"), ("/media/usb2/takes", "ext4"),
])
def test_d3_linux_mountinfo(path, expected):
    """D3 on Linux: the type of the longest mount point that holds the path, with the octal escapes of
    /proc/self/mountinfo."""
    from pathlib import PurePosixPath

    folder_files = rec_module("folder_files")
    assert folder_files.linux_file_system(PurePosixPath(path), MOUNTINFO) == expected


def test_d3_the_temp_folder_of_this_system_is_not_refused(tmp_path):
    """D3: a real check of the temp folder of this system. It is not refused; on Windows and Linux its
    file system is found."""
    folder_files = rec_module("folder_files")
    folder_files.check_file_system(tmp_path / "take")
    name = folder_files.file_system(Path(tmp_path))
    if sys.platform in ("win32", "linux"):
        assert name is not None and name.lower() not in folder_files.FAT_NAMES
