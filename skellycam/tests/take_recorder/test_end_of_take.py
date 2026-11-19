"""T-REC-21 to T-REC-25 and T-REC-30: a disk stall, a write error, a dead camera, a killed camera
process, equal row counts, and a camera file with no block.

specs/recorder.md, sections 5.3, 5.4, 7.3 to 7.6 and 8.1. The kill and stall tests run the camera
level in a child process (`child_writer.py`, 12.2). In each test, the test itself plays the main
process of 8.1: it tells each camera to end, waits, joins, then calls `finish`.
"""

import errno
import statistics
import threading
import time

import pytest

from skellycam.tests.take_recorder import ebml, jpeg_tools, sidecar_check
from skellycam.tests.take_recorder.rec_api import (
    DEAD_REASON, WRITER, Frames, Run, camera_key, camera_label, dead_take, hand_stop_fields, rec, simple_take, take_camera,
    warnings_of)

STALL_LIMIT_S = 1.0  # scaled down by 10 (12.1)
QUEUE_S = 0.3
MARGIN_S = 5.0  # 5.3 item 4 [C6, agent 25]


def child_config(run, camera_id, **extra):
    camera = next(c for c in run.cameras if c.camera_id == camera_id)
    return {"mode": "writer", "spec": run.take.camera_spec(camera_id), "width": camera.width, "height": camera.height,
            "layout": "422", "root": str(run.folder), "rules": [], **extra}


def child_payload(k, width=640, height=480):
    """The bytes of frame k of a child writer (child_writer.frame_payload)."""
    return jpeg_tools.synthetic_jpeg(k, width, height, "422")


def check_short_pair(run, camera_id, frame_count, payload_of):
    """7.4: the MKV is cut after its last block with a row; the CSV keeps its good rows; `missing`
    rows with empty byte fields and no times reach the frame count; `# repair` then `# end`; no fit
    line; each kept block parses and equals the frame given. Returns n, the number of kept blocks."""
    data = run.mkv(camera_id).read_bytes()
    mkv = ebml.walk(data)
    sidecar = sidecar_check.read(run.csv(camera_id))
    assert sidecar.bad_row is None and sidecar.torn_bytes == 0
    assert len(sidecar.rows) == frame_count
    with_bytes = [r for r in sidecar.rows if r.byte_offset is not None]
    n = len(with_bytes)
    assert [r.frame for r in with_bytes] == list(range(n)), "the rows with a block come first"
    assert len(mkv.blocks) == n, "the MKV keeps exactly the blocks that have a row"
    if n:
        assert len(data) == mkv.blocks[-1].end, "the MKV is cut after block n - 1"
    else:
        assert mkv.doc_type == "matroska" and mkv.tracks and not mkv.clusters
    assert mkv.cut_at is None and all(c.crc_ok is not False for c in mkv.clusters)
    for row, block in zip(with_bytes, mkv.blocks, strict=True):
        assert (row.byte_offset, row.byte_size) == (block.payload_offset, block.payload_size)
        assert data[block.payload_offset:block.payload_offset + block.payload_size] == payload_of(row.frame)
    for row in sidecar.rows[n:]:
        assert row.missing and row.byte_offset is None and row.byte_size is None
        assert (row.source_frame_number, row.arrival_ns, row.sample_ns) == (None, None, None)
    assert sidecar.footer_words() == ["repair", "end"]
    repair = sidecar.footer[0][1]
    assert list(repair) == ["cut_bytes", "media_cut_bytes", "repair_writer"] and repair["repair_writer"] == WRITER
    assert sidecar.end["rows"] == frame_count and sidecar.end["missing"] == sum(1 for r in sidecar.rows if r.missing)
    assert b"# fit" not in run.csv(camera_id).read_bytes()
    return n


def check_finished_pair(run, camera_id, frame_count):
    sidecar = sidecar_check.read(run.csv(camera_id))
    mkv = ebml.walk_file(run.mkv(camera_id))
    assert len(sidecar.rows) == frame_count and len(mkv.blocks) == frame_count
    assert sidecar.footer_words() == ["end"] and mkv.has_cues, "a normal end with its index"
    assert all(r.byte_offset is not None for r in sidecar.rows)
    return sidecar


@pytest.mark.recorder_slow
def test_t_rec_21_disk_stall_ends_the_take(tmp_path, runs, children):
    """T-REC-21 [C5, C6, M5, review B2, review S8]: camera A writes in a child process; its MKV file
    object blocks forever; the stall limit is scaled down. Camera B writes in this process. `give` of
    A raises `RecorderStalled` at the limit (±10 %); A gets no `give` after it; the take ends for both;
    B ends normally with placeholders to the frame count; A's process is ended no later than the time
    of its end message plus the limit plus the margin; A's result is `"disk stall"`; A's files are
    completed as a short file only after the join; the manifest has `take_error` "disk stall on
    camera <id>", `camera_dead` and `camera_file_short`."""
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)], start_writers=False,
              queue_seconds=QUEUE_S, stall_limit_s=STALL_LIMIT_S)
    runs.append(run)
    run.start_writer("ff00")
    child = children(child_config(run, "0a1b"))
    child.expect("started")
    child.send("give", k_from=0, k_to=20)
    for k in range(20):
        child.expect("gave")
        run.give("ff00", k)
    child.send("arm", rule={"kind": ".mkv", "action": "hold", "match": camera_label("0a1b")})
    child.expect("armed")
    child.send("give", k_from=20, k_to=200)
    stalled = child.expect("stalled", timeout=30.0)
    assert STALL_LIMIT_S * 0.9 <= stalled["waited_s"] <= STALL_LIMIT_S * 1.1
    given_a = stalled["k"]  # frames 0 to k - 1 were given; frame k was not written
    after = [e for e in child.history if e["event"] == "gave" and e["k"] >= given_a]
    assert after == [], "A gets no give after RecorderStalled"
    for k in range(20, given_a):
        run.give("ff00", k)
    frame_count = given_a + 5
    told = time.monotonic()
    child.send("end", frame_count=frame_count)
    run.end(frame_count, ["ff00"])
    result_a = child.expect("result", timeout=STALL_LIMIT_S + MARGIN_S)
    assert result_a["error"] == "disk stall" and result_a["files_closed"] is False
    assert result_a["end_s"] <= STALL_LIMIT_S * 1.1
    child.terminate_and_join()
    assert time.monotonic() - told <= STALL_LIMIT_S + MARGIN_S
    result_b = run.results["ff00"]
    assert result_b.error is None and result_b.files_closed and result_b.rows == frame_count
    rec_result = rec().CameraTakeResult(**{k: v for k, v in result_a.items() if k not in ("event", "end_s")})
    run.take.finish([rec_result, result_b], frame_count=frame_count, ended_by_error="disk stall on camera 0a1b",
                    dead_cameras={"0a1b": "disk stall"})
    b_rows = check_finished_pair(run, "ff00", frame_count).rows
    assert all(r.missing and r.arrival_ns is None for r in b_rows[given_a:]) and not any(r.missing for r in b_rows[:given_a])
    n = check_short_pair(run, "0a1b", frame_count, child_payload)
    manifest = run.manifest()
    assert [w["detail"] for w in warnings_of(manifest, "take_error")] == ["disk stall on camera 0a1b"]
    assert warnings_of(manifest, "take_error")[0]["camera_key"] in (camera_key("0a1b"), None)
    dead = warnings_of(manifest, "camera_dead")
    assert [(w["camera_key"], w["detail"]) for w in dead] == [(camera_key("0a1b"), f"last_frame={n - 1 if n else 'none'} reason=disk stall")]
    short = warnings_of(manifest, "camera_file_short")
    assert [(w["camera_key"], w["detail"]) for w in short] == [(camera_key("0a1b"), f"blocks={n} rows={frame_count}")]
    assert manifest["state"] == "finished"


def test_t_rec_22_write_error_gives_a_short_pair(tmp_path, runs, disk, monkeypatch):
    """T-REC-22 [C5, C6, M5, review]: the MKV file object of camera A raises `OSError(ENOSPC)` from
    frame 50 on; the container close then raises. No exception leaves the writer thread; the next
    `give` raises `RecorderWriteError`; `end` returns with the error and `files_closed`; the take level
    completes a short pair for A; B is a normal finished pair; the manifest has `take_error` with the
    error text and `camera_file_short`, and no `camera_dead`."""
    module = rec()
    escaped = []
    monkeypatch.setattr(threading, "excepthook", lambda args: escaped.append(args))
    run = simple_take(tmp_path / "take", runs, frames=50, finish=False)
    disk.fail(".mkv", errno_code=errno.ENOSPC, match=camera_label("0a1b"))
    k = 50
    with pytest.raises(module.RecorderWriteError):
        while k < 400:
            run.give("0a1b", k)
            run.give("ff00", k)
            k += 1
            time.sleep(0.002)
    frame_count = k  # frame k of A raised and was not written; B did not get it
    run.end(frame_count)
    result_a, result_b = run.results["0a1b"], run.results["ff00"]
    assert escaped == [], "no exception leaves the writer thread"
    assert result_a.files_closed and isinstance(result_a.error, str) and result_a.error not in ("", "disk stall")
    assert result_b.error is None and result_b.files_closed
    run.take.finish([result_a, result_b], frame_count=frame_count, ended_by_error=result_a.error)
    n = check_short_pair(run, "0a1b", frame_count, run.frames)
    assert n < frame_count
    check_finished_pair(run, "ff00", frame_count)
    manifest = run.manifest()
    assert [w["detail"] for w in warnings_of(manifest, "take_error")] == [result_a.error]
    assert [w["detail"] for w in warnings_of(manifest, "camera_file_short")] == [f"blocks={n} rows={frame_count}"]
    assert warnings_of(manifest, "camera_dead") == []
    assert manifest["state"] == "finished"


@pytest.mark.parametrize(("case", "last_frame", "missing"), [(1, "299", 300), (2, "296", 303), (3, "none", 600)])
def test_t_rec_23_dead_camera_writes_placeholders_to_the_end(tmp_path, runs, case, last_frame, missing):
    """T-REC-23 [R2, M1, M3, M8, F-5]: camera B dies at row 300 of 600: `give_missing` for rows 300 to
    549, then `end(600)`. Case 2: rows 297 to 299 of B are damaged first. Case 3: B dies before its
    first frame. B's CSV has 600 rows; the dead rows are `missing` with empty times and placeholder
    byte fields; B's MKV has 600 blocks and a normal end; `camera_dead` with `last_frame`; the stop
    statistics leave out the `missing` rows."""
    run = dead_take(tmp_path / "take", runs, case=case)
    death = 0 if case == 3 else 300
    sidecar = check_finished_pair(run, "ff00", 600)
    data = run.mkv("ff00").read_bytes()
    for row in sidecar.rows[death:]:
        assert row.missing and (row.source_frame_number, row.arrival_ns, row.sample_ns) == (None, None, None)
        assert int(jpeg_tools.decode_pyav(data[row.byte_offset:row.byte_offset + row.byte_size])[1].max()) == 0
    assert sidecar.end["missing"] == missing
    result = run.results["ff00"]
    assert result.missing_rows == missing and result.rows == 600 and result.blocks == 600
    assert result.last_real_row == (None if last_frame == "none" else int(last_frame))
    manifest = run.manifest()
    dead = warnings_of(manifest, "camera_dead")
    assert [(w["camera_key"], w["detail"]) for w in dead] == [(camera_key("ff00"), f"last_frame={last_frame} reason={DEAD_REASON}")]
    assert manifest["summary"]["cameras"][1]["missing"] == missing
    rows = [[(r.arrival_ns, r.missing) for r in sidecar_check.read(run.csv(c)).rows] for c in ("0a1b", "ff00")]
    rates, durations, ranges = hand_stop_fields(rows)
    response = run.summary.stop_response
    assert response["mean_framerate"] == pytest.approx(round(statistics.fmean(rates), 2), abs=1e-9)
    assert response["mean_inter_camera_sync_ms"] == pytest.approx(round(statistics.fmean(ranges), 2), abs=1e-9)
    assert response["frame_duration_stats"]["max"] == pytest.approx(max(durations), abs=1e-9)


# 20 kill points (12.2): (place, row or frame). "csv_before": the child ends before it writes row r
# (between the mux of block r + 1 and the write of row r). "csv_partial": it ends during the write of
# row r. "mkv_partial": it ends during the next MKV write after frame g was given (during a mux).
KILL_POINTS_24 = ([("csv_before", r) for r in (0, 1, 2, 7, 15, 23, 31)]
                  + [("csv_partial", r) for r in (1, 3, 8, 16, 24, 30)]
                  + [("mkv_partial", g) for g in (0, 1, 2, 10, 19, 27, 35)])


@pytest.mark.recorder_slow
@pytest.mark.parametrize(("place", "point"), KILL_POINTS_24, ids=[f"{p}_{n}" for p, n in KILL_POINTS_24])
def test_t_rec_24_killed_camera_process_gives_a_short_file(tmp_path, runs, children, place, point):
    """T-REC-24 [R4, M5, C2, SFF-794, SFF-795, F-2, F-4]: camera B writes in a child process and ends
    with `os._exit` at one of 20 kill points. The take ends 100 frames later. `finish` runs only after
    the join; B's MKV is cut after its last block with a row; the CSV keeps each good row; `missing`
    rows with empty byte fields reach the frame count; `# repair` then `# end`; no fit line; each
    row's bytes equal the frame given; each kept block parses; `camera_dead` and `camera_file_short`."""
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)], start_writers=False)
    runs.append(run)
    run.start_writer("0a1b")
    label = camera_label("ff00")
    rules = []
    if place == "csv_before":
        rules = [{"kind": ".csv", "action": "exit", "before": True, "after": point, "row_only": True, "match": label}]
    elif place == "csv_partial":
        rules = [{"kind": ".csv", "action": "exit", "partial": True, "after": point, "row_only": True, "match": label}]
    child = children(child_config(run, "ff00", rules=rules))
    child.expect("started")
    if place == "mkv_partial":
        child.send("give", k_from=0, k_to=point + 1)
        for _ in range(point + 1):
            child.expect("gave")
        child.send("arm", rule={"kind": ".mkv", "action": "exit", "partial": True, "match": label})
        child.expect("armed")
        child.send("give", k_from=point + 1, k_to=40)
    else:
        child.send("give", k_from=0, k_to=40)
    code = child.wait(60)
    assert code == 9, f"the child must end at the kill point, not with {code}"
    frame_count = 40 + 100
    for k in range(frame_count):
        run.give("0a1b", k)
    run.end(frame_count, ["0a1b"])
    run.take.finish([run.results["0a1b"], None], frame_count=frame_count, dead_cameras={"ff00": "exit code 9"})
    n = check_short_pair(run, "ff00", frame_count, child_payload)
    check_finished_pair(run, "0a1b", frame_count)
    if place == "csv_before":
        assert n == point
    elif place == "csv_partial":
        assert n == point
    manifest = run.manifest()
    assert [w["detail"] for w in warnings_of(manifest, "camera_dead")] == [
        f"last_frame={n - 1 if n else 'none'} reason=exit code 9"]
    assert [w["detail"] for w in warnings_of(manifest, "camera_file_short")] == [f"blocks={n} rows={frame_count}"]


MIXES_25 = {
    "all_live": {},
    "one_dead_at_10": {"c3d4": ("dead", 10)},
    "one_short_at_20_one_dead_at_30": {"ff00": ("short", 20), "c3d4": ("dead", 30)},
    "all_dead": {"0a1b": ("dead", 0), "ff00": ("dead", 10), "c3d4": ("dead", 25)},
}


@pytest.mark.parametrize("mix", list(MIXES_25))
def test_t_rec_25_equal_rows_in_every_mix(tmp_path, runs, disk, mix):
    """T-REC-25 [R2, M1, M5, SFF-754]: mixes of live, dead and short cameras. Each CSV has the frame
    count of the take as its number of rows; each MKV has one block for each row, except the short
    file. The short file comes from a write error (the second case of M5)."""
    module = rec()
    ids = ("0a1b", "ff00", "c3d4")
    run = Run(tmp_path / "take", [take_camera(c, os_index=i) for i, c in enumerate(ids)])
    runs.append(run)
    plan, frame_count, broken = MIXES_25[mix], 50, set()
    for k in range(frame_count):
        for camera_id in ids:
            kind, at = plan.get(camera_id, ("live", None))
            if camera_id in broken:
                continue
            if kind == "dead" and k >= at:
                run.give_missing(camera_id)
                continue
            if kind == "short" and k == at:
                disk.fail(".mkv", errno_code=errno.EIO, match=camera_label(camera_id))
            try:
                run.give(camera_id, k)
            except module.RecorderWriteError:
                broken.add(camera_id)
    shorts = [c for c, (kind, _) in plan.items() if kind == "short"]
    for camera_id in shorts:  # the error can come after the last give: wait for it
        deadline = time.monotonic() + 10
        while camera_id not in broken and time.monotonic() < deadline:
            try:
                run.give_missing(camera_id)
            except module.RecorderWriteError:
                broken.add(camera_id)
        assert camera_id in broken
    run.end(frame_count)
    dead = {c: DEAD_REASON for c, (kind, _) in plan.items() if kind == "dead"}
    run.finish(frame_count, dead_cameras=dead or None,
               ended_by_error=run.results[shorts[0]].error if shorts else None)
    for camera_id in ids:
        sidecar = sidecar_check.read(run.csv(camera_id))
        assert len(sidecar.rows) == frame_count
        blocks = len(ebml.walk_file(run.mkv(camera_id)).blocks)
        if camera_id in shorts:
            assert blocks == sum(1 for r in sidecar.rows if r.byte_offset is not None) < frame_count
        else:
            assert blocks == frame_count


@pytest.mark.recorder_slow
def test_t_rec_30_killed_before_the_first_block(tmp_path, runs, children):
    """T-REC-30 [F-2, review S5]: camera A's process is killed before its first block reaches the
    file. The MKV holds only the header of 6.3 (the EBML header, the Segment and the Tracks, and no
    block); the CSV holds only `missing` rows with empty byte fields; `camera_file_short` with
    `blocks=0`; `stored_px` comes from the mode size."""
    run = Run(tmp_path / "take", [take_camera("0a1b", width=800, height=600, layout=None),
                                  take_camera("ff00", os_index=1)], start_writers=False, frames=Frames(640, 480))
    runs.append(run)
    run.start_writer("ff00")
    child = children(child_config(run, "0a1b"))
    child.expect("started")
    assert child.kill() != 0
    frame_count = 12
    for k in range(frame_count):
        run.give("ff00", k)
    run.end(frame_count, ["ff00"])
    run.take.finish([None, run.results["ff00"]], frame_count=frame_count, dead_cameras={"0a1b": "exit code 1"})
    mkv = ebml.walk_file(run.mkv("0a1b"))
    assert mkv.doc_type == "matroska" and mkv.segment_data_start is not None and mkv.tracks
    assert mkv.blocks == [] and mkv.clusters == []
    sidecar = sidecar_check.read(run.csv("0a1b"))
    assert len(sidecar.rows) == frame_count
    assert all(r.missing and r.byte_offset is None and r.byte_size is None and r.arrival_ns is None for r in sidecar.rows)
    assert sidecar.footer_words() == ["repair", "end"]
    manifest = run.manifest()
    assert [w["detail"] for w in warnings_of(manifest, "camera_file_short")] == [f"blocks=0 rows={frame_count}"]
    assert manifest["summary"]["cameras"][0]["stored_px"] == "800x600"
