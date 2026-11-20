"""Tests of the fixes of the independent review of the 5a recorder code (ADR-T24F).

Each test names the review item. Synthetic frames only; each test writes to its pytest `tmp_path`.
"""

import errno
import json
import math
import sys
import threading
import time
import tracemalloc

import pytest

from skellycam.tests.take_recorder import ebml, jpeg_tools, sidecar_check
from skellycam.tests.take_recorder.rec_api import (
    T0, Frames, Run, camera_key, camera_label, rec, rec_module, recorder_frame, simple_take, take_camera, warnings_of)


def strip_end_line(path):
    """The sidecar as a killed camera process leaves it: no `# end` line."""
    data = path.read_bytes()
    path.write_bytes(data[:data.rindex(b"# end")])


def test_item_1_a_short_write_of_the_camera_file_is_completed(tmp_path, runs, monkeypatch):
    """Item 1: the file object returns a short count one time. Each byte is still written, so each
    row points at the bytes of its frame and each block parses."""
    mkv_module = rec_module("mkv")
    real_open = open

    class ShortOnce:
        calls = 0

        def __init__(self, real):
            self._real = real

        def write(self, data):
            ShortOnce.calls += 1
            if ShortOnce.calls == 4:
                return self._real.write(bytes(data)[:len(data) // 2])
            return self._real.write(data)

        def __getattr__(self, name):
            return getattr(self._real, name)

    monkeypatch.setattr(mkv_module, "open", lambda *a, **k: ShortOnce(real_open(*a, **k)), raising=False)
    frames = Frames(320, 240)
    run = Run(tmp_path / "take", [take_camera("0a1b", width=320, height=240, layout=rec().parse_sof(frames(0))),
                                  take_camera("ff00", width=320, height=240, layout=rec().parse_sof(frames(0)),
                                              os_index=1)], frames=frames)
    runs.append(run)
    for k in range(8):
        run.give("0a1b", k)
        run.give("ff00", k)
    run.finish(8)
    assert ShortOnce.calls > 4
    data = run.mkv("0a1b").read_bytes()
    rows = sidecar_check.read(run.csv("0a1b")).rows
    assert [data[r.byte_offset:r.byte_offset + r.byte_size] for r in rows] == [frames(k) for k in range(8)]
    assert len(ebml.walk(data).blocks) == 8


@pytest.mark.parametrize("case", ["no_files", "torn_header"])
def test_item_2_a_camera_that_ended_in_start(tmp_path, runs, case):
    """Item 2: camera A's process ended inside `start` (no files, or a cut MKV header and a cut CSV
    header). `finish` writes A's CSV again from its header with `missing` rows, writes a camera file
    with no block, gives `camera_file_short` with `blocks=0`, and finishes camera B and the take."""
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)], start_writers=False)
    runs.append(run)
    run.start_writer("ff00")
    spec = run.take.camera_spec("0a1b")
    if case == "torn_header":
        run.mkv("0a1b").write_bytes(b"\x1a\x45\xdf")
        lines = [f"# {key}={value}\n".encode() for key, value in spec.header]
        run.csv("0a1b").write_bytes(b"".join(lines[:3]) + lines[3][:5])
    for k in range(6):
        run.give("ff00", k)
    run.end(6, ["ff00"])
    summary = run.take.finish([None, run.results["ff00"]], frame_count=6, dead_cameras={"0a1b": "exit code 9"})
    mkv = ebml.walk_file(run.mkv("0a1b"))
    assert mkv.doc_type == "matroska" and mkv.tracks and mkv.blocks == []
    sidecar = sidecar_check.read(run.csv("0a1b"))
    assert sidecar.header == {key: str(value) for key, value in spec.header}
    assert len(sidecar.rows) == 6 and all(r.missing and r.byte_offset is None for r in sidecar.rows)
    assert sidecar.footer_words() == ["repair", "end"]
    manifest = run.manifest()
    assert manifest["state"] == "finished"
    assert [w["detail"] for w in warnings_of(manifest, "camera_file_short")] == ["blocks=0 rows=6"]
    assert len(sidecar_check.read(run.csv("ff00")).rows) == 6
    assert summary.stop_response["number_of_frames"] == 6


def test_item_2_one_camera_fault_does_not_stop_the_others(tmp_path, runs):
    """Item 2: the completion of camera A raises (its camera file is not Matroska). The fault is a
    `take_error` of A; camera B, the manifest and the stop response are still finished."""
    run = simple_take(tmp_path / "take", runs, frames=5, finish=False)
    run.end(5)
    run.mkv("0a1b").write_bytes(b"\x1a\x45\xdf\xa3\x80\xec\x80")  # an EBML header, then no Segment
    strip_end_line(run.csv("0a1b"))
    summary = run.take.finish([run.results["0a1b"], run.results["ff00"]], frame_count=5)
    manifest = run.manifest()
    assert manifest["state"] == "finished"
    errors = warnings_of(manifest, "take_error")
    assert [w["camera_key"] for w in errors] == [camera_key("0a1b")]
    assert sidecar_check.read(run.csv("ff00")).footer_words() == ["end"]
    assert summary.stop_response["number_of_cameras"] == 2


def test_item_3_completion_memory_does_not_grow_with_the_file(tmp_path, runs):
    """Item 3: the completion of a 40 MB camera file uses far less memory than the file size."""
    base = Frames(640, 480)
    payloads = [jpeg_tools.padded(base(k), 1_000_000) for k in range(4)]
    run = Run(tmp_path / "take", [take_camera("0a1b")], frames=lambda k: payloads[k % 4])
    runs.append(run)
    for k in range(40):
        run.give("0a1b", k)
    run.end(40)
    strip_end_line(run.csv("0a1b"))
    size = run.mkv("0a1b").stat().st_size
    assert size > 39_000_000
    completion = rec_module("completion")
    tracemalloc.start()
    try:
        kept = completion.complete_pair(run.mkv("0a1b"), run.csv("0a1b"), 40, "skellycam 2.0.0",
                                        run.take.camera_spec("0a1b").header)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert kept == 40
    assert peak < 8_000_000, f"the completion of a {size} byte file used {peak} bytes"


@pytest.mark.parametrize("case", ["held", "released"])
def test_item_4_a_reader_holds_the_manifest_open(tmp_path, runs, case):
    """Item 4: a reader holds the manifest open during `finish` (on Windows the replace then fails).
    `finish` tries again until the lock timeout; then it logs, leaves no `.tmp` file and still gives
    the stop response. A reader that closes in time does not stop the write."""
    run = simple_take(tmp_path / "take", runs, frames=3, finish=False, lock_timeout_s=1.0)
    run.end(3)
    reader = open(run.folder / "recording_manifest.json", "rb")  # noqa: SIM115 - closed below
    if case == "released":
        threading.Timer(0.3, reader.close).start()
    try:
        summary = run.take.finish([run.results["0a1b"], run.results["ff00"]], frame_count=3)
    finally:
        time.sleep(0.4 if case == "released" else 0)
        reader.close()
    assert summary.stop_response["number_of_frames"] == 3
    assert not list(run.folder.glob("*.tmp"))
    state = run.manifest()["state"]
    if case == "released" or sys.platform != "win32":
        assert state == "finished"
    else:
        assert state == "recording"


def test_item_5_a_short_sof_segment(tmp_path, runs):
    """Item 5: `parse_sof` raises ValueError (not IndexError) for an SOF segment that is too short. A
    frame with no readable SOF is stored as a placeholder on a `missing` row; the take goes on."""
    short = b"\xff\xd8\xff\xc0\x00\x02" + bytes(100) + b"\xff\xd9"
    with pytest.raises(ValueError):
        rec().parse_sof(short)
    with pytest.raises(ValueError):
        rec().parse_sof(b"\xff\xd8\xff\xc0\x00\x05\x08\x00\x10\xff\xd9")
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)])
    runs.append(run)
    for k in range(4):
        run.give("0a1b", k, payload=short if k == 1 else None)
        run.give("ff00", k)
    run.finish(4)
    rows = sidecar_check.read(run.csv("0a1b")).rows
    assert [r.missing for r in rows] == [False, True, False, False]
    data = run.mkv("0a1b").read_bytes()
    assert int(jpeg_tools.decode_pyav(data[rows[1].byte_offset:rows[1].byte_offset + rows[1].byte_size])[1].max()) == 0
    assert run.results["0a1b"].error is None


def write_sidecar(path, rows):
    """A sidecar written by the test: (arrival_ns or None, missing) for each row."""
    lines = [b"# skellyfileformat=video_timing\n", (",".join(sidecar_check.COLUMNS) + "\n").encode()]
    for k, (arrival, missing) in enumerate(rows):
        lines.append(sidecar_check.make_row(k, None if arrival is None else k, arrival, None,
                                            sidecar_check.MISSING if missing else 0, 10 * k, 10))
    path.write_bytes(b"".join(lines))


def test_item_6_and_11_stop_statistics_never_fail(tmp_path):
    """Items 6 and 11: two rows of one camera with the same `arrival_ns` give no ZeroDivisionError; a
    sidecar that cannot be read gives NaN statistics, not an exception; a take with no time gives a
    `total_duration_sec` that `StopRecordingResponse` accepts."""
    from skellycam.api.http.cameras.camera_router import StopRecordingResponse

    stop_stats = rec_module("stop_stats")
    equal = tmp_path / "equal.csv"
    write_sidecar(equal, [(1000, False), (1000, False), (34_001_000, False)])
    fields = stop_stats.stop_response_fields([equal], recording_name="t", recording_path=tmp_path, frame_count=3)
    assert fields["framerate_stats"]["max"] == pytest.approx(1e9 / 34_000_000)
    absent = stop_stats.stop_response_fields([tmp_path / "absent.csv"], recording_name="t", recording_path=tmp_path,
                                             frame_count=3)
    assert math.isnan(absent["mean_framerate"]) and math.isnan(absent["total_duration_sec"])
    no_time = tmp_path / "no_time.csv"
    write_sidecar(no_time, [(None, True), (None, True)])
    fields = stop_stats.stop_response_fields([no_time], recording_name="t", recording_path=tmp_path, frame_count=2)
    assert math.isnan(fields["total_duration_sec"])
    StopRecordingResponse(**fields)


def test_item_7_frame_number_must_increase(tmp_path, runs):
    """Item 7 (spec 4.1): a frame whose `frame_number` does not increase raises ValueError and is not
    queued; the writer goes on."""
    run = Run(tmp_path / "take", [take_camera("0a1b")])
    runs.append(run)
    run.give("0a1b", 0)
    writer = run.writers["0a1b"]
    with pytest.raises(ValueError):
        writer.give(recorder_frame(run.frames(0), 0, arrival_ns=T0 + 2_000_000))
    run.give("0a1b", 1)
    run.finish(2)
    assert len(sidecar_check.read(run.csv("0a1b")).rows) == 2 and run.results["0a1b"].error is None


def test_item_8_the_caller_names_the_camera_of_the_error(tmp_path, runs):
    """Item 8 (F-5): `error_camera` gives the `camera_key` of `take_error` also when no result holds
    the error (a camera process that the main process ended)."""
    run = simple_take(tmp_path / "take", runs, frames=3, finish=False)
    run.end(3)
    run.take.finish([run.results["0a1b"], run.results["ff00"]], frame_count=3,
                    ended_by_error="disk stall on camera ff00", error_camera="ff00")
    assert [w["camera_key"] for w in warnings_of(run.manifest(), "take_error")] == [camera_key("ff00")]


def test_item_9_a_second_finish_keeps_camera_file_short(tmp_path, runs):
    """Item 9: `finish` runs again (the first run was killed after the completion). The pair that the
    first run completed keeps its `camera_file_short` warning."""
    run = simple_take(tmp_path / "take", runs, frames=5, finish=False)
    run.end(5)
    strip_end_line(run.csv("0a1b"))
    results = [run.results["0a1b"], run.results["ff00"]]
    run.take.finish(results, frame_count=5)
    first = warnings_of(run.manifest(), "camera_file_short")
    run.take.finish(results, frame_count=5)
    assert warnings_of(run.manifest(), "camera_file_short") == first == [
        {"code": "camera_file_short", "source": "skellycam", "camera_key": camera_key("0a1b"), "detail": "blocks=5 rows=5"}]


def patch_lock(monkeypatch, error_number):
    def refuse(*args):
        raise OSError(error_number, "refused")

    if sys.platform == "win32":
        import msvcrt

        monkeypatch.setattr(msvcrt, "locking", refuse)
    else:
        import fcntl

        monkeypatch.setattr(fcntl, "flock", refuse)


def test_item_10_the_lock_retries_only_a_busy_lock(tmp_path, monkeypatch):
    """Item 10: a lock that another program holds is tried again until the timeout; each other error
    is reported at once."""
    folder_files = rec_module("folder_files")
    path = tmp_path / ".processing.lock"
    path.write_bytes(b"")
    patch_lock(monkeypatch, errno.EBADF)
    started = time.monotonic()
    with pytest.raises(OSError) as raised, folder_files.take_lock(path, 5.0):
        pass
    assert not isinstance(raised.value, TimeoutError) and time.monotonic() - started < 1.0
    patch_lock(monkeypatch, errno.EACCES)
    started = time.monotonic()
    with pytest.raises(TimeoutError), folder_files.take_lock(path, 0.3):
        pass
    assert time.monotonic() - started >= 0.3


def test_item_12a_the_end_deadline_stops_the_writer_thread(tmp_path, runs, disk):
    """Item 12a: `end` cannot put its marker (the writer is held and the queue is full). After the
    writer is released, its non-daemon thread ends, so the camera process can end."""
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)], queue_seconds=0.3,
              stall_limit_s=0.5)
    runs.append(run)
    rule = disk.hold(".mkv", match=camera_label("0a1b"))
    writer, k = run.writers["0a1b"], 0
    while not writer.queue.full():
        run.give("0a1b", k)
        k += 1
        if k == 3:
            assert disk.wait_holding(rule, 10.0)
    result = run.end(k, ["0a1b"])["0a1b"]
    assert result.error == "disk stall"
    rule.release.set()
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and any(t.name == "take-writer-0a1b" for t in threading.enumerate()):
        time.sleep(0.02)
    assert not any(t.name == "take-writer-0a1b" for t in threading.enumerate())


def test_item_12b_the_manifest_keeps_the_summary_members_of_freemocap(tmp_path, runs):
    """Item 12b: `summary.calibration` and `summary.processing_runs` that another program wrote during
    the take stay after `finish`."""
    run = simple_take(tmp_path / "take", runs, frames=3, finish=False)
    path = run.folder / "recording_manifest.json"
    manifest = run.manifest()
    manifest["summary"]["calibration"] = {"calibration_uuid": "1" * 32, "source_take_uuid": None}
    manifest["summary"]["processing_runs"] = [{"run_id": "r1", "origin": "posthoc", "recorded_at": "2026-11-20T10:00:00Z"}]
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    run.finish(3)
    summary = run.manifest()["summary"]
    assert summary["calibration"] == manifest["summary"]["calibration"]
    assert summary["processing_runs"] == manifest["summary"]["processing_runs"]


def test_finish_does_not_touch_the_files_of_a_camera_whose_process_runs(tmp_path):
    """Review fault 6 of the connection [8.1 step 4, review B2]: `finish` with `running_cameras` leaves the
    files of that camera as they are; the other camera is finished."""
    from skellycam.core.take_recorder import CameraTakeWriter, start_take
    from skellycam.tests.capture.fake_source import synthetic_jpeg
    from skellycam.tests.take_recorder.rec_api import recorder_frame, take_camera

    take = start_take(tmp_path / "take", "take", [take_camera("0a1b", layout=None),
                                                  take_camera("ff00", os_index=1, layout=None)],
                      writer="skellycam 2.0.0")
    writers = [CameraTakeWriter.start(take.camera_spec(camera_id)) for camera_id in ("0a1b", "ff00")]
    for k in range(3):
        for writer in writers:
            writer.give(recorder_frame(synthetic_jpeg(640, 480), k, arrival_ns=take.take_start_host_ns + k * 33_333_333))
    result = writers[0].end(3)
    writers[1].abandon()  # its files as a process left them that still runs
    running = [writers[1].spec.mkv_path, writers[1].spec.csv_path]
    before = [path.read_bytes() for path in running]
    take.finish([result, None], frame_count=3, running_cameras={"ff00"})
    assert [path.read_bytes() for path in running] == before
    assert writers[0].spec.csv_path.read_text(encoding="utf-8").splitlines()[-1].startswith("# end ")
