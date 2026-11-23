"""T-REC-40 to T-REC-49: the connection tests (specs/recorder.md, sections 10 and 12.1).

They come with the connection commit, after step 3a of phase 3 is joined [R10], and use the shared
loop and the fake sources of the capture tests (`specs/windows-capture.md` section 16.1): THREAD
workers on a virtual clock, except T-REC-44, which needs a camera process that ends hard. The stall
limit of the recorder counts real time; the virtual clock moves the camera times. Synthetic JPEGs
only, in tmp folders. Each docstring gives the test and its pass criterion of section 12.2; the text
after it says how the test meets it. T-REC-38 and T-REC-39 are not used (12.6).
"""

import importlib
import logging
import math
import sys
import threading
import time

import pytest

from skellycam.tests.capture.capture_session import (
    CaptureApp, OpenCVFakeFactory, RingWatcher, Spies, StateWatcher, block_payloads, camera_key_of, capture_app,
    placeholders_to_the_stop, ready_app_steps, take_files, take_manifest, take_rows, take_warnings, wait_exit)
from skellycam.tests.capture.fake_source import FakeScript, FakeSource


def group_module():
    return importlib.import_module("skellycam.core.camera_group.camera_group")


def sidecar_flags():
    from skellycam.core.take_recorder import sidecar

    return sidecar


def ring_flags():
    from skellycam.core.ipc.frame_ring import FrameFlag

    return FrameFlag


def record_until(app, spies, count, camera_ids=None):
    for camera_id in camera_ids or app.factory.camera_ids:
        app.wait(lambda: len(spies.of("record", camera_id)) >= count, f"{count} recorded frames of {camera_id}")


def stop(app):
    stopped = app.record_stop()
    assert stopped.status_code == 200, stopped.text
    return stopped.json()[0]


class _Killed(BaseException):
    """The end of a held writer thread when the main process ends its camera (THREAD workers)."""


class WriterHold:
    """Holds the writer thread of one camera before its next row (the disk takes nothing). `stalled` is set
    when `give` of that camera raises `RecorderStalled`; `in_give` is true while its `give` waits.

    With `kill_flag` (the stop flag of the camera), a held writer thread ends as a killed process ends when
    the flag is set: its file handles close with no write, and the thread ends. A THREAD worker cannot be
    killed, so else the take level would complete the files while the writer thread lives (review item 15)."""

    def __init__(self, monkeypatch, camera_id):
        from skellycam.core.take_recorder import CameraTakeWriter, RecorderStalled

        self.camera_id = camera_id
        self.held, self.release, self.stalled = threading.Event(), threading.Event(), threading.Event()
        self.in_give = False
        self.kill_flag = None
        take, give = CameraTakeWriter._take, CameraTakeWriter.give
        hook = threading.excepthook
        hold = self

        def held_take(writer, item):
            if writer.spec.camera_id == hold.camera_id and hold.held.is_set():
                deadline = time.monotonic() + 120
                while not hold.release.wait(0.001) and time.monotonic() < deadline:
                    if hold.kill_flag is not None and hold.kill_flag.value:
                        writer._mkv.raw.close()
                        writer._csv.close()
                        raise _Killed()
            return take(writer, item)

        def quiet_kill(args):
            if not issubclass(args.exc_type, _Killed):
                hook(args)

        def watched_give(writer, frame):
            mine = writer.spec.camera_id == hold.camera_id
            if mine:
                hold.in_give = True
            try:
                return give(writer, frame)
            except RecorderStalled:
                if mine:
                    hold.stalled.set()
                raise
            finally:
                if mine:
                    hold.in_give = False

        monkeypatch.setattr(CameraTakeWriter, "_take", held_take)
        monkeypatch.setattr(CameraTakeWriter, "give", watched_give)
        monkeypatch.setattr(threading, "excepthook", quiet_kill)

    def start(self):
        self.release.clear()
        self.held.set()

    def stop(self):
        self.held.clear()
        self.release.set()


def wait_blocked_in_give(app, spies, hold):
    app.wait(lambda: hold.camera_id in spies.writers and spies.writers[hold.camera_id].queue.full() and hold.in_give,
             "the loop waits in `give` with a full queue")


def strip_dht(jpeg):
    """The JPEG with no DHT segment before SOS (a camera that sends no Huffman tables, ring 5.2)."""
    out, i = bytearray(jpeg[:2]), 2
    while jpeg[i + 1] != 0xDA:
        length = int.from_bytes(jpeg[i + 2:i + 4], "big")
        if jpeg[i + 1] != 0xC4:
            out += jpeg[i:i + 2 + length]
        i += 2 + length
    return bytes(out + jpeg[i:])


def test_t_rec_40_full_queue_waits_and_gives_gap_rows(monkeypatch, tmp_path):
    """T-REC-40 [D26, D27]: three fake cameras in the shared loop at 30 fps; the writer of one is held
    2 s. All three loops wait; after it, each camera's next row has `gap`; for each camera the sum of
    the gaps of `source_frame_number` equals the increase of `replaced_count`; equal rows."""
    # The queue is 0.2 s (6 items), so that a hold of 2 s makes `give` wait (a 3 s queue absorbs it, 5.2).
    # The hold is 2 s of the virtual clock: the test moves the clock while the loops wait.
    # `replaced_count` is the count of the source at each `give`.
    from skellycam.core.take_recorder import CameraTakeWriter

    monkeypatch.setattr(group_module(), "TAKE_QUEUE_SECONDS", 0.2)
    with capture_app(monkeypatch, [FakeScript(), FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        hold = WriterHold(monkeypatch, app.factory.camera_ids[0])
        replaced = {camera_id: [] for camera_id in app.factory.camera_ids}
        give = CameraTakeWriter.give

        def counting_give(writer, frame):
            replaced[writer.spec.camera_id].append(app.factory.sources[writer.spec.camera_id].replaced_count)
            return give(writer, frame)

        monkeypatch.setattr(CameraTakeWriter, "give", counting_give)
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 30)
        hold.start()
        wait_blocked_in_give(app, spies, hold)
        counts = {cid: len(spies.of("record", cid)) for cid in app.factory.camera_ids}
        hold_ns = app.clock.now_ns()
        app.clock.advance_to(hold_ns + 2 * 10**9)
        time.sleep(0.3)
        waited = {cid: len(spies.of("record", cid)) for cid in app.factory.camera_ids}
        assert all(waited[cid] - counts[cid] <= 1 for cid in counts), f"a loop did not wait: {counts} -> {waited}"
        hold.stop()
        app.wait(lambda: all(len(spies.of("record", cid)) > waited[cid] + 30 for cid in waited), "30 more rows")
        summary = stop(app)
    sidecar = sidecar_flags()
    for camera_id in app.factory.camera_ids:
        rows = take_rows(tmp_path, camera_id)
        assert len(rows) == summary["number_of_frames"], f"camera {camera_id}: {len(rows)} rows"
        records = spies.of("record", camera_id)
        assert [row.source_frame_number for row in rows] == [event["sfn"] for event in records]
        after = next(i for i, event in enumerate(records) if event["arrival_ns"] > hold_ns + 10**9)
        assert rows[after].flags & sidecar.GAP, f"camera {camera_id}: row {after} after the hold has no gap"
        gaps = sum(b.source_frame_number - a.source_frame_number - 1 for a, b in zip(rows, rows[1:]))
        assert gaps == replaced[camera_id][-1] - replaced[camera_id][0] > 0, camera_id


@pytest.mark.parametrize("bgr_ring", [False, True], ids=["no BGR ring", "BGR ring"])
def test_t_rec_41_no_decode_for_the_recorder(monkeypatch, tmp_path, bgr_ring):
    """T-REC-41 [D9, ring 8.2]: record with and without a BGR ring; count `cv2.imdecode` calls on the
    loop thread and on the decode thread. No decode for the recorder; one decode per frame on the
    decode thread only when a BGR ring exists."""
    # "One decode per frame": no frame is decoded two times, and each BGR ring write with an image has one
    # decode (the decode stage can skip a frame that a newer one replaced, ring 8.3).
    with capture_app(monkeypatch, [FakeScript(modes=((320, 240, 30, 1, "MJPG"),))]) as app:
        spies = Spies(monkeypatch, app)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, bgr_ring=bgr_ring)])
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 60)
        stop(app)
        app.client.delete("/skellycam/camera/group/close/all")
    decodes = spies.of("imdecode")
    assert all(event["thread"].startswith("decode ") for event in decodes), \
        f"a decode on another thread: {sorted({e['thread'] for e in decodes})}"
    if not bgr_ring:
        assert decodes == [], f"{len(decodes)} decodes with no BGR ring"
        return
    per_hash = {}
    for event in decodes:
        per_hash[event["hash"]] = per_hash.get(event["hash"], 0) + 1
    jpeg_hashes = {event["hash"] for event in spies.of("jpeg")}
    assert set(per_hash) <= jpeg_hashes and max(per_hash.values()) == 1, "a frame was decoded two times"
    bgr_writes = [event for event in spies.of("bgr") if event["hash"] is not None]
    assert len(decodes) == len(bgr_writes) >= 60, (len(decodes), len(bgr_writes))
    assert {event["hash"] for event in spies.of("record")} <= jpeg_hashes


def test_t_rec_42_cut_off_jpeg_gives_a_placeholder_row(monkeypatch, tmp_path):
    """T-REC-42 [R3, M1]: the fake delivers a cut-off JPEG during a take. A placeholder on a `missing`
    row; the previous image is not stored again; no decode call."""
    from skellycam.core.take_recorder import build_placeholder, parse_sof

    with capture_app(monkeypatch, [FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        source = app.factory.sources[camera_id]
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 10)
        source.cut_off_next()
        app.wait(lambda: source.cut_frames, "the cut-off frame")
        record_until(app, spies, 40)
        stop(app)
    sidecar = sidecar_flags()
    cut_sfn = source.cut_frames[0]
    write = [event for event in spies.of("jpeg") if event["sfn"] == cut_sfn]
    assert len(write) == 1 and write[0]["flags"] & ring_flags().NO_SOI_EOI
    assert spies.of("imdecode") == [], "a decode call"
    rows, blocks = take_rows(tmp_path, camera_id), block_payloads(tmp_path, camera_id)
    index = next(i for i, row in enumerate(rows) if row.source_frame_number == cut_sfn)
    row = rows[index]
    assert row.flags & sidecar.MISSING and row.byte_size == len(blocks[index])
    assert row.arrival_ns is not None and row.sample_ns is not None, "the times of the damaged frame are kept (7.2)"
    assert blocks[index] == build_placeholder(parse_sof(blocks[index - 1])), "the block is not the placeholder"
    assert blocks[index] != blocks[index - 1], "the previous image is stored again"
    assert sum(bool(r.flags & sidecar.MISSING) for r in rows) == 1


def test_t_rec_43_dead_camera_runs_to_the_end_of_the_take(monkeypatch, tmp_path):
    """T-REC-43 [R2, M1, D38]: three fakes record; one gives device removed at frame 300. That camera
    is `dead`; its process runs to the end of the take and writes placeholders; its MKV is closed
    normally; every CSV and MKV has the same rows and blocks; `camera_dead` in the manifest; no
    recording info JSON."""
    # The removal comes at the next frame after 60 recorded frames, not at source frame 300: the virtual
    # time runs ahead of the test (as in the old T-CAP-35). "Its process runs": its THREAD worker. "Dead" is
    # within 100 ms of the removal (the rule of the old T-CAP-35, review item 11).
    from skellycam.tests.take_recorder.ebml import walk_file

    with capture_app(monkeypatch, [FakeScript(), FakeScript(), FakeScript()], track=True) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        live, dead = app.factory.camera_ids[:2], app.factory.camera_ids[2]
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 60, [dead])
        source = app.factory.sources[dead]
        source.remove_now()
        app.wait(lambda: app.tracker.first(dead, "dead") is not None, "the camera is dead")
        t_dead = app.tracker.first(dead, "dead")
        removed_ns = app.factory.logs[dead].frames[source.removed_frame][0] + round(1e9 / 30)
        assert t_dead - removed_ns < 100_000_000, f"dead {(t_dead - removed_ns) / 1e9:.3f} s after the removal"
        for camera_id in live:
            app.wait(lambda: any(e["arrival_ns"] > t_dead + 10**9 for e in spies.of("record", camera_id)),
                     f"camera {camera_id} records after the dead camera")
        app.wait(lambda: len(spies.of("missing", dead)) >= 10, "placeholder rows of the dead camera")
        assert app.worker(dead).is_alive(), "the worker of the dead camera ended during the take"
        assert app.state(dead) == "dead"
        summary = stop(app)
    frame_count = summary["number_of_frames"]
    for camera_id in app.factory.camera_ids:
        assert len(take_rows(tmp_path, camera_id)) == frame_count, camera_id
        mkv = walk_file(take_files(tmp_path)[camera_id][0])
        assert len(mkv.blocks) == frame_count and mkv.has_cues, f"camera {camera_id}: the MKV is not closed normally"
    placeholders_to_the_stop(tmp_path, dead)
    folder = tmp_path / "take"
    assert sorted(p.name for p in folder.iterdir()) == [".processing.lock", "recording_manifest.json",
                                                        "synchronized_videos", "take_info.json"]
    info = (folder / "take_info.json").read_text(encoding="utf-8")
    assert '"skellyfileformat": "capture_info"' in info and "dead_cameras" not in info, "a recording info JSON"


@pytest.mark.capture_timing
def test_t_rec_44_hang_ends_the_process_and_the_take_level_completes_its_file(monkeypatch, tmp_path):
    """T-REC-44 [R4, M5]: a bounded call of one fake hangs during a take. The failure is reported; the
    process ends within 1 s of the report; the take level completes its short file after the join;
    the others record to the stop."""
    # PROCESS workers in real time: the hard end of a camera thread would end the test process. The hung
    # call is the periodic control read on the control thread [U16]. It replaces T-CAP-85 (section 14).
    # "Record to the stop": the other camera has no gap above 100 ms in its ring from the start of the take
    # to the stop (U16, decision G of the user, 2026-11-20); real time, so the marker `capture_timing`.
    scripts = [FakeScript(hang_at="set_controls"), FakeScript()]
    with capture_app(monkeypatch, scripts, workers="process") as app:
        ready_app_steps(app)
        hung, other = app.factory.camera_ids
        ring = RingWatcher(app.ring_name(other))
        watcher = StateWatcher(app, hung)
        try:
            worker = app.worker(hung)
            assert app.record_start(tmp_path).status_code == 200
            started_ns = time.perf_counter_ns()
            time.sleep(1.0)
            app.factory.logs[hung].arm_hang()
            app.wait(lambda: watcher.failure is not None, "the failure is reported")
            exited = wait_exit(worker)
            assert worker.worker.exitcode not in (0, None), "the process did not end hard"
            after_report = (exited - watcher.failure_ns) / 1e9
            assert after_report <= 1.0, f"the process ended {after_report:.2f} s after the report"
            app.wait(lambda: any(f[1] > exited + 2 * 10**9 for f in ring.frames), "the other camera records on")
            stop_ns = time.perf_counter_ns()
            summary = stop(app)
            largest, before = ring.largest_gap(started_ns, stop_ns)
            assert largest <= 0.1, f"the other camera had a gap of {largest * 1000:.0f} ms at {before}"
        finally:
            watcher.stop()
            ring.stop()
    frame_count = summary["number_of_frames"]
    sidecar = sidecar_flags()
    hung_rows, other_rows = take_rows(tmp_path, hung), take_rows(tmp_path, other)
    assert len(hung_rows) == len(other_rows) == frame_count
    assert not any(row.flags & sidecar.MISSING for row in other_rows), "the other camera did not record to the stop"
    blocks = len(block_payloads(tmp_path, hung))
    assert 0 < blocks < frame_count, "the file of the hung camera is not short"
    assert all(row.flags & sidecar.MISSING and row.byte_offset is None for row in hung_rows[blocks:])
    lines = take_files(tmp_path)[hung][1].read_text(encoding="utf-8").splitlines()
    assert lines[-2].startswith("# repair ") and lines[-1].startswith("# end "), lines[-2:]
    assert [w["detail"] for w in take_warnings(tmp_path, "camera_file_short")] == [f"blocks={blocks} rows={frame_count}"]
    dead = take_warnings(tmp_path, "camera_dead")
    assert [w["camera_key"] for w in dead] == [camera_key_of(tmp_path, hung)] and dead[0]["detail"].endswith("reason=hang")


def test_t_rec_45_stop_response_and_microphone_refusal_over_http(monkeypatch, tmp_path):
    """T-REC-45 [R5, C1]: start and stop a take over HTTP with fake sources (not port 53117); then a
    start request with `mic_device_index` 0. The stop response has each field of
    `StopRecordingResponse` with the values of 8.2; the second start gets HTTP 422 with the text of
    section 10 item 13."""
    # The test client of FastAPI calls the app in this process: no network port. The values of 8.2 are
    # the fields that `stop_stats` computes from the CSVs of the take (T-REC-27 checks them by hand).
    from skellycam.api.http.cameras.camera_router import StopRecordingResponse
    from skellycam.core.take_recorder.stop_stats import stop_response_fields

    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 60)
        summary = stop(app)
        refused = app.client.post("/skellycam/camera/group/all/record/start",
                                  json={"recording_name": "take2", "recording_directory": str(tmp_path),
                                        "mic_device_index": 0})
    assert set(summary) == set(StopRecordingResponse.model_fields), sorted(summary)
    paths = [tmp_path / "take" / item["timing"] for item in take_manifest(tmp_path)["cameras"]]
    expected = stop_response_fields(paths, recording_name="take", recording_path=tmp_path / "take",
                                    frame_count=len(take_rows(tmp_path, app.factory.camera_ids[0])))
    assert summary["number_of_frames"] >= 60 and summary["number_of_cameras"] == 2
    assert summary["total_duration_sec"] > 0, "the take start and the arrivals are on two clocks"
    assert all(row.arrival_ns >= 0 for cid in app.factory.camera_ids for row in take_rows(tmp_path, cid))

    def same(value, wanted):
        if isinstance(wanted, dict):
            return set(value) == set(wanted) and all(same(value[k], wanted[k]) for k in wanted)
        if isinstance(wanted, float):
            return (value is None and math.isnan(wanted)) or value == pytest.approx(wanted, rel=1e-12)
        return value == wanted

    for field, wanted in expected.items():
        assert same(summary[field], wanted), f"{field}: {summary[field]} != {wanted}"
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == "audio recording returns in step 5b; start again with no microphone"
    assert not (tmp_path / "take2").exists()


def test_t_rec_46_inserted_dht_is_in_the_ring_and_the_mkv(monkeypatch, tmp_path):
    """T-REC-46 [M6]: a fake sends a JPEG with no DHT. The ring slot and the MKV block hold the same
    bytes, with the inserted DHT; the row has no flag for it."""
    make_frame = FakeSource._make_frame

    def no_dht(source, k, arrival):
        frame = make_frame(source, k, arrival)
        payload = strip_dht(frame.payload)
        return type(frame)(**{**frame.__dict__, "payload": payload, "delivered_len": len(payload)})

    monkeypatch.setattr(FakeSource, "_make_frame", no_dht)
    with capture_app(monkeypatch, [FakeScript()]) as app:
        spies = Spies(monkeypatch, app, keep_payloads=True)
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 30)
        stop(app)
    sidecar = sidecar_flags()
    rows, blocks = take_rows(tmp_path, camera_id), block_payloads(tmp_path, camera_id)
    assert len(rows) == len(blocks) >= 30
    slots = {event["arrival_ns"]: event for event in spies.of("jpeg")}
    for row, block, given in zip(rows, blocks, spies.of("record", camera_id)):
        slot = slots[given["arrival_ns"]]
        assert slot["flags"] & ring_flags().DHT_INSERTED
        assert slot["payload"] == block, f"row {row.frame}: the ring slot and the MKV block differ"
        assert b"\xff\xc4" in block, "no DHT in the block"
        assert row.flags & ~(sidecar.GAP | sidecar.REPEAT) == 0, f"row {row.frame} has the flags {row.flags}"


def test_t_rec_47_row_0_is_group_frame_gate_count_plus_3(monkeypatch, tmp_path):
    """T-REC-47 [review B4, M7]: two fakes start a take at gate count 100. Row 0 of each camera is
    group frame 103."""
    # The virtual time runs ahead of the test, so the take starts at a gate count L of 100 or more: the
    # largest gate count of the cameras when the record start has paused them. Row 0 is group frame L + 3.
    from skellycam.core.camera.camera_manager import CameraManager

    paused = []
    pause = CameraManager.pause

    async def watched_pause(manager, await_paused):
        await pause(manager, await_paused)
        paused.append(max(status.frame_count.value for status in manager.orchestrator.camera_statuses.values()))

    monkeypatch.setattr(CameraManager, "pause", watched_pause)
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        statuses = app.group.cameras.orchestrator.camera_statuses
        app.wait(lambda: min(status.frame_count.value for status in statuses.values()) >= 100, "gate count 100")
        assert app.record_start(tmp_path).status_code == 200
        gate_count = paused[0]
        record_until(app, spies, 10)
        stop(app)
    assert gate_count >= 100
    for camera_id in app.factory.camera_ids:
        first = spies.of("record", camera_id)[0]
        assert first["frame_number"] == gate_count + 3, f"camera {camera_id}: row 0 is group frame {first['frame_number']}"
        assert take_rows(tmp_path, camera_id)[0].source_frame_number == first["sfn"]


def test_t_rec_48_stall_watch_stall_end_and_failed_state(monkeypatch, tmp_path):
    """T-REC-48 [agent 32, C5, C6]: two OpenCV fakes record; the writer of one is held 3 s; then a fake
    writer is held past the stall limit and then released; then held for good. Case 1: neither camera
    is marked `dead`, also the one that waited at the gate (5.2); case 2: the take ends with
    `take_error`, the camera stays `ready`; case 3: the camera is `failed`, stage `recording`, reason
    "disk stall", and "apply again" reopens it."""
    # Case 1 holds the writer while the loops wait 3 s of the virtual clock (the stall watch counts that
    # clock). Then each grab fails for 100 ms: a read of the OpenCV source with no time left still grabs once,
    # so with no failed grab a watch that counts from the last arrival would not fire either (review item
    # 14). Cases 2 and 3 use a stall limit of 1 s (real time, 5.3); each case has a queue of 0.2 s.
    module = group_module()
    monkeypatch.setattr(module, "TAKE_QUEUE_SECONDS", 0.2)
    app = CaptureApp(monkeypatch, OpenCVFakeFactory(monkeypatch, count=2))
    hold = None
    try:
        spies = Spies(monkeypatch, app)
        held_id, other = app.factory.camera_ids
        hold = WriterHold(monkeypatch, held_id)
        ready_app_steps(app)
        watchers = {cid: StateWatcher(app, cid) for cid in app.factory.camera_ids}
        # case 1
        assert app.record_start(tmp_path, name="take1").status_code == 200
        record_until(app, spies, 30)
        hold.start()
        wait_blocked_in_give(app, spies, hold)
        app.clock.advance_to(app.clock.now_ns() + 3 * 10**9)
        time.sleep(0.5)
        for capture in app.factory.captures.values():
            capture.fail_until_ns = app.clock.now_ns() + 100_000_000
        hold.stop()
        count = len(spies.of("record", held_id))
        app.wait(lambda: len(spies.of("record", held_id)) > count + 30, "the take goes on")
        stop(app)
        for watcher in watchers.values():
            watcher.stop()
        assert all("dead" not in watcher.first for watcher in watchers.values()), \
            {cid: watcher.first for cid, watcher in watchers.items()}
        assert len(take_rows(tmp_path, held_id, "take1")) == len(take_rows(tmp_path, other, "take1"))
        # case 2
        monkeypatch.setattr(module, "TAKE_STALL_LIMIT_S", 1.0)
        assert app.record_start(tmp_path, name="take2").status_code == 200
        record_until(app, spies, len(spies.of("record", held_id)) + 30)
        hold.start()
        app.wait(lambda: hold.stalled.is_set(), "`give` raises RecorderStalled")
        hold.stop()
        app.wait(lambda: app.group.ended_take is not None, "the take ends")
        summary = stop(app)
        errors = take_warnings(tmp_path, "take_error", "take2")
        assert [w["detail"] for w in errors] == [f"disk stall on camera {held_id}"], errors
        assert errors[0]["camera_key"] == camera_key_of(tmp_path, held_id, "take2")
        assert app.state(held_id) == "ready" and app.state(other) == "ready"
        assert summary["number_of_frames"] == len(take_rows(tmp_path, held_id, "take2"))
        # case 3: the writer of the held camera ends as its process would end at the kill of 5.3 item 6
        hold.stalled.clear()
        hold.kill_flag = app.group.cameras.orchestrator.camera_statuses[held_id].should_close
        assert app.record_start(tmp_path, name="take3").status_code == 200
        record_until(app, spies, len(spies.of("record", held_id)) + 30)
        writer_thread = spies.writers[held_id]._thread
        hold.start()
        app.wait(lambda: app.group.ended_take is not None, "the take ends", timeout=60)
        frame_count = stop(app)["number_of_frames"]
        assert not writer_thread.is_alive(), "the take level completed the files while the writer thread lived"
        assert [len(take_rows(tmp_path, cid, "take3")) for cid in (held_id, other)] == [frame_count] * 2
        status = app.status(held_id)
        assert status["state"] == "failed" and status["failure"] == {
            "camera_id": held_id, "stage": "recording", "reason": "disk stall", "code": "disk-stall"}, status
        assert app.state(other) == "ready"
        key = camera_key_of(tmp_path, held_id, "take3")
        assert [w["camera_key"] for w in take_warnings(tmp_path, "camera_file_short", "take3")] == [key]
        assert take_warnings(tmp_path, "camera_dead", "take3")[0]["detail"].endswith("reason=disk stall")
        hold.stop()
        response = app.apply([app.config(cid) for cid in app.factory.camera_ids], retry=app.factory.camera_ids)
        assert response.status_code == 200, response.text
        app.wait_state(held_id, "ready")
    finally:
        if hold is not None:
            hold.stop()
        app.close()


def test_t_rec_49_playback_list_marks_new_takes(tmp_path):
    """T-REC-49 [C7]: list the playback recordings with one old recording and one new take; ask for
    the videos of the new take. Both are listed; the new take has `needs_new_player: true`; the old
    video list endpoint gives HTTP 409 with the mark text for it; no endpoint of the take folder
    itself is blocked."""
    # The old recording is an H.264 MP4 of the old writer; the new take comes from the take recorder with
    # synthetic JPEGs. "Not blocked": the timestamps endpoint of the new take does not give 409.
    import numpy as np
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from skellycam.api.http.playback.playback_router import NEEDS_NEW_PLAYER, playback_router
    from skellycam.core.take_recorder import CameraTakeWriter, start_take
    from skellycam.tests.capture.fake_source import synthetic_jpeg
    from skellycam.tests.old_video_writer import PyavVideoWriter
    from skellycam.tests.take_recorder.rec_api import recorder_frame, take_camera

    old = tmp_path / "old_rec" / "synchronized_videos"
    old.mkdir(parents=True)
    writer = PyavVideoWriter(path=str(old / "old_rec.cam0.mp4"), fps=30.0, width=64, height=48)
    for _ in range(2):
        writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    writer.release()
    cameras = [take_camera("0a1b", layout=None), take_camera("ff00", os_index=1, layout=None)]
    take = start_take(tmp_path / "new_take", "new_take", cameras, writer="skellycam 2.0.0")
    results = []
    for camera_id in ("0a1b", "ff00"):
        camera_writer = CameraTakeWriter.start(take.camera_spec(camera_id))
        for k in range(3):
            camera_writer.give(recorder_frame(synthetic_jpeg(640, 480), k,
                                              arrival_ns=take.take_start_host_ns + k * 33_333_333))
        results.append(camera_writer.end(3))
    take.finish(results, frame_count=3)
    app = FastAPI()
    app.include_router(playback_router, prefix="/skellycam")
    client = TestClient(app)
    params = {"recording_parent_directory": str(tmp_path)}
    listed = client.get("/skellycam/playback/recordings", params=params)
    assert listed.status_code == 200, listed.text
    entries = {entry["name"]: entry for entry in listed.json()}
    assert set(entries) == {"old_rec", "new_take"}
    assert entries["new_take"]["needs_new_player"] is True and entries["new_take"]["video_count"] == 2
    assert all(entries["new_take"][k] is None for k in ("total_frames", "duration_seconds", "fps"))
    assert entries["old_rec"]["needs_new_player"] is False and entries["old_rec"]["video_count"] == 1
    videos = client.get("/skellycam/playback/new_take/videos", params=params)
    assert videos.status_code == 409 and videos.json()["detail"] == NEEDS_NEW_PLAYER, videos.text
    mkv = take_files(tmp_path, "new_take")["0a1b"][0].name
    stream = client.get(f"/skellycam/playback/new_take/videos/{mkv}", params=params)
    assert stream.status_code == 409 and stream.json()["detail"] == NEEDS_NEW_PLAYER, stream.text
    assert client.get("/skellycam/playback/old_rec/videos", params=params).status_code == 200
    assert client.get("/skellycam/playback/new_take/timestamps", params=params).status_code != 409


# ---------------------------------------------------------------------------
# Faults of the independent review of the connection (2026-11-20)
# ---------------------------------------------------------------------------

def stop_in_thread(app):
    result = []
    thread = threading.Thread(target=lambda: result.append(app.record_stop()), daemon=True)
    thread.start()
    return thread, result


@pytest.mark.parametrize("error", ["stall in give", "write error at the end"])
def test_an_error_during_the_stop_gives_take_error(monkeypatch, tmp_path, error):
    """Review fault 2 [C5, recorder.md 5.3, 5.4]: a stall or a write error that comes while the stop runs.
    The stop response is 200, and the manifest has `take_error` with the text of 5.3 or 5.4 and the key
    of that camera. Before the fix, the stop finished the take with no error, and the error end that the
    watch started found no take."""
    from skellycam.core.take_recorder import CameraTakeWriter

    module = group_module()
    monkeypatch.setattr(module, "TAKE_QUEUE_SECONDS", 0.2)
    monkeypatch.setattr(module, "TAKE_STALL_LIMIT_S", 1.0)
    stall = error == "stall in give"
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        failing = app.factory.camera_ids[0]
        hold = WriterHold(monkeypatch, failing)
        if not stall:
            finish = CameraTakeWriter._finish

            def failing_finish(writer, frame_count):
                if writer.spec.camera_id == failing:
                    raise OSError("test: the disk is full")
                return finish(writer, frame_count)

            monkeypatch.setattr(CameraTakeWriter, "_finish", failing_finish)
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 30)
        if stall:
            hold.start()
            wait_blocked_in_give(app, spies, hold)
        thread, result = stop_in_thread(app)
        if stall:
            app.wait(lambda: hold.stalled.is_set(), "`give` raises RecorderStalled")
            hold.stop()
        thread.join(60)
        assert result and result[0].status_code == 200, result and result[0].text
        assert app.state(failing) == "ready" and app.group.take is None
    errors = take_warnings(tmp_path, "take_error")
    expected = f"disk stall on camera {failing}" if stall else "test: the disk is full"
    assert [w["detail"] for w in errors] == [expected], errors
    assert errors[0]["camera_key"] == camera_key_of(tmp_path, failing)


def test_a_stop_whose_pause_times_out_ends_the_take(monkeypatch, tmp_path):
    """Review fault 5 [recorder.md 5.3, 8.1]: the writer of one camera is held while the stop pauses the
    cameras, and the pause limit ends before the stall limit. The stop ends the take as after an error,
    with no pause: 200, the manifest is `finished` with `take_error`, and the group runs on. Before the
    fix, the pause timeout stopped the group, and the take stayed with the manifest `recording`. Since S11 of
    the third review the stop does not pause at all; the test keeps the outcome."""
    import skellycam.core.camera_group.camera_orchestrator as orchestrator_module

    module = group_module()
    monkeypatch.setattr(module, "TAKE_QUEUE_SECONDS", 0.2)
    monkeypatch.setattr(module, "TAKE_STALL_LIMIT_S", 3.0)
    monkeypatch.setattr(orchestrator_module, "CAMERA_STATE_TIMEOUT_SECONDS", 0.5)
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        held = app.factory.camera_ids[0]
        hold = WriterHold(monkeypatch, held)
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 30)
        hold.start()
        wait_blocked_in_give(app, spies, hold)
        thread, result = stop_in_thread(app)
        app.wait(lambda: hold.stalled.is_set(), "`give` raises RecorderStalled")
        hold.stop()
        thread.join(60)
        assert result and result[0].status_code == 200, result and result[0].text
        frame_count = result[0].json()[0]["number_of_frames"]
        assert app.group.take is None and app.group.ipc.should_continue
        assert all(app.state(cid) == "ready" for cid in app.factory.camera_ids)
    assert take_manifest(tmp_path)["state"] == "finished"
    assert [w["detail"] for w in take_warnings(tmp_path, "take_error")] == [f"disk stall on camera {held}"]
    assert all(len(take_rows(tmp_path, cid)) == frame_count for cid in app.factory.camera_ids)


def test_two_stops_at_once_and_a_lost_error_end(monkeypatch, tmp_path):
    """Review fault 7: (1) two stop requests at once give one summary and one 409 "No recording runs", not
    an HTTP 500; (2) an exception of the error end is logged, and a later stop gets 409."""
    from skellycam.core.take_recorder import Take
    from skellycam.tests.capture.capture_session import capture_logs

    module = group_module()
    monkeypatch.setattr(module, "TAKE_QUEUE_SECONDS", 0.2)
    monkeypatch.setattr(module, "TAKE_STALL_LIMIT_S", 1.0)
    finish = Take.finish
    mode = {"slow": True, "fail": False}

    def watched_finish(take, *args, **kwargs):
        if mode["fail"]:
            raise RuntimeError("test: the finish fails")
        if mode["slow"]:
            time.sleep(0.5)  # the second stop arrives while the first one runs
        return finish(take, *args, **kwargs)

    monkeypatch.setattr(Take, "finish", watched_finish)
    with capture_logs() as logs, capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        held = app.factory.camera_ids[0]
        hold = WriterHold(monkeypatch, held)
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 30)
        stops = [stop_in_thread(app) for _ in range(2)]
        for thread, _ in stops:
            thread.join(60)
        responses = sorted((result[0] for _, result in stops), key=lambda r: r.status_code)
        assert [r.status_code for r in responses] == [200, 409], [r.text for r in responses]
        assert responses[1].json()["detail"] == "No recording runs"
        # (2)
        mode.update(slow=False, fail=True)
        assert app.record_start(tmp_path, name="take2").status_code == 200
        record_until(app, spies, len(spies.of("record", held)) + 30)
        hold.start()
        app.wait(lambda: hold.stalled.is_set(), "`give` raises RecorderStalled")
        hold.stop()
        app.wait(lambda: any("test: the finish fails" in m for m in logs.messages(logging.ERROR)), "the logged error end")
        app.wait(lambda: app.group.take is None, "the take ends")
        late = app.record_stop()
        assert late.status_code == 409 and late.json()["detail"] == "No recording runs", late.text


def test_a_camera_that_ends_with_no_last_frame_leaves_its_files_to_the_take_level(monkeypatch, tmp_path):
    """Review fault 3 [R2, recorder.md 7.4, 7.6]: the loop of one camera ends during a take with no last frame
    (its stop flag, as when the group closes with no stop). It does not finish its pair with its own row
    count: the take level completes it at the stop, so each sidecar has the frame count of the take and
    the manifest has no `take_error`."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        closing, other = app.factory.camera_ids
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 30)
        worker = app.worker(closing)
        app.group.cameras.orchestrator.camera_statuses[closing].should_close.value = True
        app.wait(lambda: not worker.is_alive(), "the loop of the camera ends")
        record_until(app, spies, len(spies.of("record", other)) + 30, [other])
        summary = stop(app)
    frame_count = summary["number_of_frames"]
    assert [len(take_rows(tmp_path, cid)) for cid in (closing, other)] == [frame_count, frame_count]
    assert take_warnings(tmp_path, "take_error") == []
    lines = take_files(tmp_path)[closing][1].read_text(encoding="utf-8").splitlines()
    assert lines[-2].startswith("# repair "), "the take level did not complete the pair (7.4)"


def test_a_writer_that_cannot_start_fails_the_record_start(monkeypatch, tmp_path):
    """Review fault 9 and decision D of the user (2026-11-20): the camera writer of one camera cannot open its
    files. The record start fails with the error text of that camera (not 200 with a take that runs with
    no writer); the take folder is finished at once with zero rows and a `take_error`; the camera stays
    `ready` (not `dead` with the reason "exit code 0"), and a later take starts."""
    from skellycam.core.take_recorder import CameraTakeWriter

    start = CameraTakeWriter.start.__func__
    refuse = {"on": True}
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        failing = app.factory.camera_ids[0]

        def refusing_start(cls, spec, **kwargs):
            if refuse["on"] and spec.camera_id == failing:
                raise OSError("test: the disk refuses the file")
            return start(cls, spec, **kwargs)

        monkeypatch.setattr(CameraTakeWriter, "start", classmethod(refusing_start))
        ready_app_steps(app)
        response = app.record_start(tmp_path)
        assert response.status_code == 500, response.text
        detail = response.json()["detail"]
        assert f"camera {failing}" in detail and "test: the disk refuses the file" in detail, detail
        assert app.group.take is None
        assert all(app.state(cid) == "ready" for cid in app.factory.camera_ids), \
            {cid: app.status(cid) for cid in app.factory.camera_ids}
        refuse["on"] = False
        assert app.record_start(tmp_path, name="take2").status_code == 200
        stop(app)
    manifest = take_manifest(tmp_path)
    assert manifest["state"] == "finished"
    assert all(take_rows(tmp_path, cid) == [] for cid in app.factory.camera_ids)
    errors = take_warnings(tmp_path, "take_error")
    assert len(errors) == 1 and "test: the disk refuses the file" in errors[0]["detail"], errors
    assert take_warnings(tmp_path, "camera_dead") == []


def test_stall_watch_of_a_push_source_counts_from_the_end_of_the_wait(monkeypatch, tmp_path):
    """Decision E of the user (2026-11-20, recorder.md 5.2 and 10 item 10): the 2 s stall watch of each source
    counts from the later of the last frame and the end of the last wait. Two push fakes record; the writer of
    one is held 3 s of the clock, and its source gives its next frame 4 s after its last frame, 1 s after
    the hold. No camera is `dead`: counted from the last frame alone, the watch fires (checked by hand)."""
    monkeypatch.setattr(group_module(), "TAKE_QUEUE_SECONDS", 0.2)
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        held, other = app.factory.camera_ids
        hold = WriterHold(monkeypatch, held)
        ready_app_steps(app)
        watchers = {cid: StateWatcher(app, cid) for cid in app.factory.camera_ids}
        try:
            assert app.record_start(tmp_path).status_code == 200
            record_until(app, spies, 30)
            hold.start()
            wait_blocked_in_give(app, spies, hold)
            app.factory.sources[held].slow_period(rate=0.25, seconds=1.0)  # one interval of 4 s
            app.clock.advance_to(app.clock.now_ns() + 3 * 10**9)
            time.sleep(0.3)
            hold.stop()
            count = len(spies.of("record", held))
            app.wait(lambda: len(spies.of("record", held)) > count + 3, "the take goes on")
            stop(app)
        finally:
            for watcher in watchers.values():
                watcher.stop()
    assert all("dead" not in watcher.first for watcher in watchers.values()), \
        {cid: watcher.first for cid, watcher in watchers.items()}


def test_an_exit_during_a_take_leaves_finished_camera_files(monkeypatch, tmp_path):
    """Second review of the connection fixes, R1 (b): the camera loops end during a take with no stop and no
    take level to follow (the group stops, as at an exit of the app). Each camera finishes its own pair with
    each frame that it gave and its `# end` line. Third review, L: the first camera that ends sets the last
    frame, so the pairs have equal rows (a camera pads with placeholders to it)."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 30)
        workers = [app.worker(cid) for cid in app.factory.camera_ids]
        app.group.ipc.should_continue = False
        for worker in workers:
            app.wait(lambda: not worker.is_alive(), "the loop ends")
        app.group.take = None  # no stop: the take level does not follow (the close then stops no take)
    from skellycam.core.take_recorder.sidecar import MISSING

    counts = []
    for camera_id in app.factory.camera_ids:
        assert take_files(tmp_path)[camera_id][1].read_text(encoding="utf-8").splitlines()[-1].startswith("# end ")
        rows = take_rows(tmp_path, camera_id)
        real = [row for row in rows if not row.flags & MISSING]
        assert len(real) == len(spies.of("record", camera_id)) >= 30, (len(real), camera_id)
        assert all(row.flags & MISSING for row in rows[len(real):]), "a placeholder before a frame"
        counts.append(len(rows))
    assert counts[0] == counts[1], counts


@pytest.mark.parametrize("case", ["late writer", "unpause timeout"])
def test_a_failed_start_waits_for_a_late_writer_before_it_finishes_the_folder(monkeypatch, tmp_path, case):
    """Second review, R8 (a) and (b), decision D: the writer of one camera opens its files at once but returns
    2 s after the take spec, past the start limit (1 s here). The record start fails, and the take folder is finished only after that
    camera ended its late writer: `finish` never completes the files of a live writer. With an unpause limit
    of 0.5 s, the camera that still opens its files cannot unpause in time: the folder is still finished,
    and the group runs on (before, the unpause timeout stopped the group and the manifest stayed
    `recording`)."""
    import skellycam.core.camera_group.camera_orchestrator as orchestrator_module
    from skellycam.core.take_recorder import CameraTakeWriter, Take

    monkeypatch.setattr(group_module(), "TAKE_START_LIMIT_S", 1.0)
    if case == "unpause timeout":
        monkeypatch.setattr(orchestrator_module, "CAMERA_STATE_TIMEOUT_SECONDS", 0.5)
    start, end, finish = CameraTakeWriter.start.__func__, CameraTakeWriter.end, Take.finish
    times = {}
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        slow = app.factory.camera_ids[0]

        def slow_start(cls, spec, **kwargs):
            writer = start(cls, spec, **kwargs)
            if spec.camera_id == slow and spec.csv_path.parent.parent.name == "take":
                time.sleep(2.0)  # a slow start after the open (disk, antivirus, network share)
            return writer

        def timed_end(writer, frame_count):
            if writer.spec.camera_id == slow:
                time.sleep(0.5)  # and a slow end: a finish that does not wait for it overlaps it
            result = end(writer, frame_count)
            times.setdefault(writer.spec.camera_id, time.monotonic())
            return result

        def timed_finish(take, *args, **kwargs):
            times.setdefault("finish", time.monotonic())
            return finish(take, *args, **kwargs)

        monkeypatch.setattr(CameraTakeWriter, "start", classmethod(slow_start))
        monkeypatch.setattr(CameraTakeWriter, "end", timed_end)
        monkeypatch.setattr(Take, "finish", timed_finish)
        ready_app_steps(app)
        response = app.record_start(tmp_path)
        assert response.status_code == 500, response.text
        assert app.group.ipc.should_continue and app.group.take is None
        assert take_manifest(tmp_path)["state"] == "finished"
        app.wait(lambda: not app.group.cameras.orchestrator.camera_statuses[slow].recording_in_progress.value,
                 "the late writer ends")
        assert times.get(slow, math.inf) < times["finish"], "finish completed the files of a live writer"
        app.wait(lambda: all(app.state(cid) == "ready" for cid in app.factory.camera_ids), "both cameras ready")
        assert app.record_start(tmp_path, name="take2").status_code == 200
        stop(app)
    assert all(take_rows(tmp_path, cid) == [] for cid in app.factory.camera_ids)


def test_a_stop_whose_unpause_fails_still_finishes_the_take(monkeypatch, tmp_path):
    """Second review, R8 (c): the stop paused the cameras, then one camera cannot unpause within the limit
    (0.5 s here; its loop is held 2 s). The stop still finishes the take: 200, the manifest is `finished`,
    and the group runs on. Before, the unpause timeout stopped the group, and the take ended with no finish.
    Since S11 of the third review the stop does not pause or unpause; the test keeps the outcome."""
    import types

    import skellycam.core.camera_group.camera_orchestrator as orchestrator_module

    loop_module = importlib.import_module("skellycam.core.camera.capture.camera_loop")
    monkeypatch.setattr(orchestrator_module, "CAMERA_STATE_TIMEOUT_SECONDS", 0.5)
    hold = {"on": False}
    real_sleep = time.sleep
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        held = app.factory.camera_ids[0]

        def held_sleep(seconds):
            if hold["on"] and seconds == 0.05 and held in threading.current_thread().name:
                hold["on"] = False
                real_sleep(2.0)  # paused, and held: it cannot unpause in time
            real_sleep(seconds)

        names = {name: getattr(time, name) for name in dir(time) if not name.startswith("_")}
        monkeypatch.setattr(loop_module, "time", types.SimpleNamespace(**{**names, "sleep": held_sleep}))
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 30)
        hold["on"] = True
        stopped = app.record_stop()
        assert stopped.status_code == 200, stopped.text
        assert app.group.ipc.should_continue and app.group.take is None
    assert take_manifest(tmp_path)["state"] == "finished"
    frame_count = stopped.json()[0]["number_of_frames"]
    assert all(len(take_rows(tmp_path, cid)) == frame_count for cid in app.factory.camera_ids)


# ---------------------------------------------------------------------------
# Third review of the connection fixes (2026-11-20)
# ---------------------------------------------------------------------------

def held_paused_sleep(monkeypatch, camera_id):
    """Hold the paused loop of one camera 1 s at its next paused sleep, when `hold["on"]` is set. Not 2 s: the
    main-process stall watch ends a camera with no loop pass for 2 s (unix-capture.md 4.10)."""
    import types

    loop_module = importlib.import_module("skellycam.core.camera.capture.camera_loop")
    hold, real_sleep = {"on": False}, time.sleep

    def held_sleep(seconds):
        if hold["on"] and seconds == 0.05 and camera_id in threading.current_thread().name:
            hold["on"] = False
            real_sleep(1.0)
        real_sleep(seconds)

    names = {name: getattr(time, name) for name in dir(time) if not name.startswith("_")}
    monkeypatch.setattr(loop_module, "time", types.SimpleNamespace(**{**names, "sleep": held_sleep}))
    return hold


def test_a_start_whose_last_unpause_times_out_keeps_the_take(monkeypatch, tmp_path):
    """Third review, S1: each writer started, then one camera cannot unpause within the limit (0.5 s here).
    The record start gives 200 and the take runs on: the group is not stopped, and the stop finishes the
    take with equal rows. Before, the unpause timeout stopped the group while the take stayed set, and a
    later stop gave number_of_frames -1."""
    import skellycam.core.camera_group.camera_orchestrator as orchestrator_module
    from skellycam.core.take_recorder import CameraTakeWriter

    monkeypatch.setattr(orchestrator_module, "CAMERA_STATE_TIMEOUT_SECONDS", 0.5)
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        held = app.factory.camera_ids[0]
        hold = held_paused_sleep(monkeypatch, held)
        start = CameraTakeWriter.start.__func__

        def arming_start(cls, spec, **kwargs):
            writer = start(cls, spec, **kwargs)
            if spec.camera_id == held:
                hold["on"] = True  # its next paused sleep is long: it cannot unpause in time
            return writer

        monkeypatch.setattr(CameraTakeWriter, "start", classmethod(arming_start))
        ready_app_steps(app)
        response = app.record_start(tmp_path)
        assert response.status_code == 200, response.text
        assert app.group.ipc.should_continue and app.group.take is not None
        record_until(app, spies, 30)
        summary = stop(app)
    assert take_manifest(tmp_path)["state"] == "finished" and summary["number_of_frames"] > 0
    assert all(len(take_rows(tmp_path, cid)) == summary["number_of_frames"] for cid in app.factory.camera_ids)


def test_a_take_whose_cameras_died_before_its_first_frame_has_no_negative_count(monkeypatch, tmp_path):
    """Third review, S1 (second part): every camera dies before the first frame of the take. The stop gives a
    frame count of 0, not a negative one: the last frame is at least the first frame."""
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator

    largest, far = CameraOrchestrator.largest_gate_count, {"on": False}

    def far_first(orchestrator):  # the record start puts the first frame 1000 group frames ahead
        return largest(orchestrator) + (1000 if far["on"] else 0)

    monkeypatch.setattr(CameraOrchestrator, "largest_gate_count", far_first)
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        ready_app_steps(app)
        far["on"] = True
        assert app.record_start(tmp_path).status_code == 200
        far["on"] = False
        for camera_id in app.factory.camera_ids:
            app.factory.sources[camera_id].remove_now()
        for camera_id in app.factory.camera_ids:
            app.wait_state(camera_id, "dead")
        summary = stop(app)
    assert summary["number_of_frames"] == 0
    assert all(take_rows(tmp_path, cid) == [] for cid in app.factory.camera_ids)


def test_a_start_that_fails_before_its_specs_went_out_ends_no_camera(monkeypatch, tmp_path):
    """Third review, S2: the take spec of the second camera cannot be built, so no spec goes out. The record
    start fails at once; it does not wait for the cameras (none got a spec), and no camera ends as "disk
    stall". The folder is finished (D)."""
    from skellycam.core.take_recorder import Take

    module = group_module()
    monkeypatch.setattr(module, "TAKE_STALL_LIMIT_S", 1.0)
    monkeypatch.setattr(module, "STALL_MARGIN_S", 0.5)
    camera_spec, calls = Take.camera_spec, {"n": 0}

    def failing_spec(take, camera_id):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("test: the spec fails")
        return camera_spec(take, camera_id)

    monkeypatch.setattr(Take, "camera_spec", failing_spec)
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        ready_app_steps(app)
        started = time.monotonic()
        response = app.record_start(tmp_path)
        took = time.monotonic() - started
        assert response.status_code == 500 and "test: the spec fails" in response.text, response.text
        time.sleep(0.5)
        assert all(app.state(cid) == "ready" for cid in app.factory.camera_ids), \
            {cid: app.status(cid) for cid in app.factory.camera_ids}
        assert not app.group.to_state().recording_in_progress
    assert took < 1.0, f"the failed start waited {took:.1f} s"
    assert take_manifest(tmp_path)["state"] == "finished"


def test_a_second_start_waits_for_the_finish_of_a_failed_start(monkeypatch, tmp_path):
    """Third review, S7: a second record start comes while the first start, which failed, finishes its folder
    (slow here: 1 s). It waits for that finish, then records normally: the finish of the first start does
    not reset the first and last frames of the second take."""
    from skellycam.core.take_recorder import CameraTakeWriter, Take

    start, finish = CameraTakeWriter.start.__func__, Take.finish
    finishing = threading.Event()

    def refusing_start(cls, spec, **kwargs):
        if spec.csv_path.parent.parent.name == "take":
            raise OSError("test: the disk refuses the file")
        return start(cls, spec, **kwargs)

    def slow_finish(take, *args, **kwargs):
        if take.rec == "take":
            finishing.set()
            time.sleep(1.0)
        return finish(take, *args, **kwargs)

    monkeypatch.setattr(CameraTakeWriter, "start", classmethod(refusing_start))
    monkeypatch.setattr(Take, "finish", slow_finish)
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        first = []
        thread = threading.Thread(target=lambda: first.append(app.record_start(tmp_path)), daemon=True)
        thread.start()
        assert finishing.wait(30), "the first start did not reach its finish"
        second = app.record_start(tmp_path, name="take2")
        thread.join(30)
        assert first[0].status_code == 500 and second.status_code == 200, (first[0].text, second.text)
        count = len(spies.of("record", app.factory.camera_ids[0]))
        record_until(app, spies, count + 30)
        summary = stop(app)
    assert summary["number_of_frames"] >= 30
    assert all(len(take_rows(tmp_path, cid, "take2")) == summary["number_of_frames"] for cid in app.factory.camera_ids)


def test_a_write_error_while_abandon_drains_reaches_the_take_level(monkeypatch, tmp_path):
    """Third review, S8 [recorder.md 5.4]: one camera ends alone during a take (its stop flag) with frames in
    its queue, and a write of its writer fails while `abandon` writes them. The take level gets the error:
    the manifest has `take_error` with its text and the key of that camera."""
    from skellycam.core.take_recorder import CameraTakeWriter

    monkeypatch.setattr(group_module(), "TAKE_QUEUE_SECONDS", 1.0)
    take_item, failing = CameraTakeWriter._take, {"on": False}
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        closing, other = app.factory.camera_ids

        def slow_take(writer, item):
            if writer.spec.camera_id == closing:
                time.sleep(0.03)  # a slow disk: the queue holds frames
                if failing["on"]:
                    raise OSError("test: the disk is full")
            return take_item(writer, item)

        monkeypatch.setattr(CameraTakeWriter, "_take", slow_take)
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 60)
        assert spies.writers[closing].queue.qsize() > 0, "no frame in the queue"
        worker = app.worker(closing)
        failing["on"] = True
        app.group.cameras.orchestrator.camera_statuses[closing].should_close.value = True
        app.wait(lambda: not worker.is_alive(), "the loop ends")
        app.wait(lambda: app.group.take is None, "the take ends for every camera (5.4)")
        stop(app)
    errors = take_warnings(tmp_path, "take_error")
    assert [w["detail"] for w in errors] == ["test: the disk is full"], errors
    assert errors[0]["camera_key"] == camera_key_of(tmp_path, closing)


@pytest.mark.parametrize("workers", ["thread", "process"])
def test_the_shutdown_endpoint_finishes_a_running_take(monkeypatch, tmp_path, workers):
    """Third review, S4: GET /shutdown during a take. The take level stops the take (recorder.md 8.1) and the
    groups close before the kill flag is set: the manifest is `finished`, and each camera has the frame
    count of the take. Before, /shutdown only set the kill flag: the manifest stayed `recording`.
    Round 4, item 4: the endpoint answers at once (the Electron app waits 5 s at most) and the close runs in
    the background, then sets the kill flag; here the finish of the take is made 2 s slow."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import skellycam.core.camera_group.camera_group_manager as manager_module
    from skellycam.api.http.app.shutdown import shutdown_router
    from skellycam.core.take_recorder import Take

    finish = Take.finish

    def slow_finish(take, *args, **kwargs):
        time.sleep(2.0)
        return finish(take, *args, **kwargs)

    monkeypatch.setattr(Take, "finish", slow_finish)
    monkeypatch.setattr(logging.Logger, "api", logging.Logger.info, raising=False)  # a level of the app logger
    with capture_app(monkeypatch, [FakeScript(), FakeScript()], workers=workers) as app:
        ready_app_steps(app)
        monkeypatch.setattr(manager_module, "_CAMERA_GROUP_MANAGER", app.manager)
        server = FastAPI()
        server.state.global_kill_flag = app.kill
        server.include_router(shutdown_router, prefix="/skellycam")
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(1.0)
        with TestClient(server) as client:  # its event loop runs the close in the background
            started = time.monotonic()
            response = client.get("/skellycam/shutdown")
            answered = time.monotonic() - started
            app.wait(lambda: app.kill.value, "the close ends, then the kill flag")
        assert response.status_code == 200, response.text
        assert answered < 1.0, f"the shutdown endpoint answered after {answered:.1f} s"
        assert not app.manager.camera_groups
    manifest = take_manifest(tmp_path)
    assert manifest["state"] == "finished"
    counts = [len(take_rows(tmp_path, cid)) for cid in app.factory.camera_ids]
    assert counts[0] == counts[1] > 0, counts


@pytest.mark.parametrize("workers", ["thread", "process"])
def test_the_cameras_end_their_take_10_s_after_the_server_died(monkeypatch, tmp_path, workers):
    """Decision L of the user (2026-11-20, recorder.md 9): the main process writes no heartbeat during a take
    (as when it dies). Each camera process notices it within about 10 s, finishes its pair with the rows of
    one last group frame (equal rows, `# end`) and ends. The take level does not run, so the manifest stays
    `recording` (step 5c)."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()], workers=workers, virtual=False) as app:
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(1.0)
        workers_ = [app.worker(cid) for cid in app.factory.camera_ids]
        # A dead main process: no heartbeat, and no take level (round 4: a live one ends the take itself).
        monkeypatch.setattr(group_module().CameraGroup, "_take_finished", lambda group: None)
        app.registry._heartbeat_stop.set()  # the heartbeat writer of the main process stops
        stopped = time.monotonic()
        for worker in workers_:
            app.wait(lambda: not worker.is_alive(), "the camera ends", timeout=30)
        took = time.monotonic() - stopped
        app.group.take = None  # no take level: the main process is "dead"
    assert 9.0 <= took <= 14.0, f"the cameras ended {took:.1f} s after the last heartbeat"
    rows = []
    for camera_id in app.factory.camera_ids:
        lines = take_files(tmp_path)[camera_id][1].read_text(encoding="utf-8").splitlines()
        assert lines[-1].startswith("# end "), lines[-1]
        rows.append(sum(1 for line in lines if line[:1].isdigit()))
    assert rows[0] == rows[1] > 0, rows
    assert take_manifest(tmp_path)["state"] == "recording"


def test_a_busy_main_process_does_not_look_dead(monkeypatch, tmp_path):
    """Decision L of the user: the event loop of the main process is blocked 5 s during a take (a long
    synchronous call). The heartbeat comes from its own thread, so no camera ends, and the take goes on."""
    import asyncio

    with capture_app(monkeypatch, [FakeScript(), FakeScript()], workers="process") as app:
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200

        async def busy():
            time.sleep(5.0)

        asyncio.run_coroutine_threadsafe(busy(), app.group._loop).result(30)
        time.sleep(1.0)
        assert all(app.worker(cid).is_alive() for cid in app.factory.camera_ids)
        summary = stop(app)
    assert all(len(take_rows(tmp_path, cid)) == summary["number_of_frames"] > 150 for cid in app.factory.camera_ids)


def test_the_stop_costs_no_source_frame_before_the_last_rows(monkeypatch, tmp_path):
    """Third review, S11 (real-camera run of 2026-11-20: a `camera_gap` at row N - 2 in 6 of 7 takes): row
    N - 2 is the first group frame after the unpause of the stop. A paused camera does not read, and the
    waiting place of a push source replaces each frame that comes during the pause (5.2), so that row had
    `gap`. Here the pause of the stop takes 200 ms (on the real cameras: the pause wait plus the 50 ms sleep
    of a paused loop). Two push fakes in real time: no row of the last 5 has `gap`."""
    import asyncio

    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator

    pause = CameraOrchestrator.pause

    async def slow_pause(orchestrator, await_paused=True):
        await pause(orchestrator, await_paused=await_paused)
        await asyncio.sleep(0.2)

    monkeypatch.setattr(CameraOrchestrator, "pause", slow_pause)
    sidecar = sidecar_flags()
    with capture_app(monkeypatch, [FakeScript(), FakeScript()], virtual=False) as app:
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(2.0)
        summary = stop(app)
    for camera_id in app.factory.camera_ids:
        rows = take_rows(tmp_path, camera_id)
        assert len(rows) == summary["number_of_frames"]
        gaps = [row.frame for row in rows[-5:] if row.flags & sidecar.GAP]
        assert gaps == [], f"camera {camera_id}: gap rows {gaps} of {len(rows)}"


# ---------------------------------------------------------------------------
# Fix round 4 (2026-11-20)
# ---------------------------------------------------------------------------

def _slow_stop_take(monkeypatch, tmp_path, fps, delay):
    """Round 4, item 1: the main process is busy for `delay` between the read of the largest gate count and the write
    of the last frame (real time). Gives the stop summary, the row count of each sidecar and the manifest warnings."""
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator

    largest = CameraOrchestrator.largest_gate_count

    def slow_largest(orchestrator):
        value = largest(orchestrator)
        if sys._getframe(1).f_code.co_name == "_end_take":
            time.sleep(delay)
        return value

    monkeypatch.setattr(CameraOrchestrator, "largest_gate_count", slow_largest)
    modes = ((640, 480, fps, 1, "MJPG"),)
    with capture_app(monkeypatch, [FakeScript(modes=modes), FakeScript(modes=modes)], virtual=False) as app:
        ready_app_steps(app, [app.config(cid, framerate=float(fps)) for cid in app.factory.camera_ids])
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(1.0)
        summary = stop(app)
    counts = [len(take_rows(tmp_path, cid)) for cid in app.factory.camera_ids]
    return summary, counts, take_manifest(tmp_path)["warnings"]


@pytest.mark.capture_timing  # real time: a stop that comes late under load moves the last frame (recorder.md 12.1)
@pytest.mark.parametrize("fps", [30, 60])
@pytest.mark.parametrize("delay", [0.05, 0.2, 1.0])
def test_a_slow_stop_ends_each_camera_at_the_last_frame(monkeypatch, tmp_path, fps, delay):
    """Round 4, item 1: the stop reads and writes the last frame under its lock, so no camera decides a new frame
    between them: each sidecar has `number_of_frames` rows, and no warning other than `camera_gap` (a gap depends on
    the pace: `test_a_slow_stop_has_a_gap_only_on_the_last_row`). Blocking (16.1)."""
    summary, counts, warnings = _slow_stop_take(monkeypatch, tmp_path, fps, delay)
    assert counts == [summary["number_of_frames"]] * len(counts), (counts, summary["number_of_frames"])
    assert [w for w in warnings if w["code"] != "camera_gap"] == [], warnings


@pytest.mark.pace  # Q619: a busy machine gives gaps in any row (a Windows run under load: row=1, row=7, row=26)
@pytest.mark.capture_timing
@pytest.mark.parametrize("fps", [30, 60])
@pytest.mark.parametrize("delay", [0.05, 0.2, 1.0])
def test_a_slow_stop_has_a_gap_only_on_the_last_row(monkeypatch, tmp_path, fps, delay):
    """Fix lane 4 [HQE5] (recorder.md 8.1 step 1): a camera that waits at the gate during the hold of the stop loses the
    frames of its push source, so the last row of a camera can have `gap` (the Windows runner: `row=30 from=125
    to=131`). On a machine at its normal pace that is the only `camera_gap`."""
    summary, _, warnings = _slow_stop_take(monkeypatch, tmp_path, fps, delay)
    last_row = f"row={summary['number_of_frames'] - 1} "
    assert [w for w in warnings if w["code"] == "camera_gap" and not w["detail"].startswith(last_row)] == [], warnings


def test_the_stop_keeps_a_last_frame_that_a_camera_set(monkeypatch, tmp_path):
    """Round 4, item 1: a camera set the last frame of the take before the stop (the end with no take level).
    The stop keeps it: number_of_frames is that last frame minus the first frame."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()], virtual=False) as app:
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(0.5)
        orchestrator = app.group.cameras.orchestrator
        last = orchestrator.largest_gate_count() + 10
        orchestrator.last_recording_frame_number.value = last
        expected = last - orchestrator.first_recording_frame_number.value
        summary = stop(app)
    assert summary["number_of_frames"] == expected
    assert all(len(take_rows(tmp_path, cid)) == expected for cid in app.factory.camera_ids)


@pytest.mark.parametrize("during_take", [True, False], ids=["during a take", "no take"])
def test_a_lost_heartbeat_ends_only_the_cameras(monkeypatch, tmp_path, during_take):
    """Round 4, item 3, decision L of the user: the heartbeat thread of a live main process stalls 12 s. Each
    camera process ends its own loop (no global kill flag), finishes its files and releases its camera; its
    status says "lost the server's heartbeat". The app stays up; a running take ends with a `take_error` and
    is not left running in the group; "apply again" opens the cameras again."""
    armed = {"on": False}

    class StallingEvent(threading.Event):
        def wait(self, timeout=None):
            if armed["on"] and threading.current_thread().name == "WorkerRegistry-Heartbeat":
                armed["on"] = False
                time.sleep(12.0)  # a long GIL hold, a debugger pause or a resume from sleep
            return super().wait(timeout)

    with capture_app(monkeypatch, [FakeScript(), FakeScript()], workers="process") as app:
        app.registry._heartbeat_stop = StallingEvent()
        ready_app_steps(app)
        if during_take:
            assert app.record_start(tmp_path).status_code == 200
        time.sleep(1.0)
        workers = [app.worker(cid) for cid in app.factory.camera_ids]
        armed["on"] = True
        for worker in workers:
            app.wait(lambda: not worker.is_alive(), "the camera ends", timeout=40)
        assert not app.kill.value, "the lost heartbeat set the global kill flag"
        for camera_id in app.factory.camera_ids:
            status = app.status(camera_id)
            assert status["state"] == "dead" and status["failure"]["reason"] == "lost the server's heartbeat", status
            assert app.factory.logs[camera_id].closes.value >= 1, f"camera {camera_id} was not released"
        app.wait(lambda: time.perf_counter() - app.registry.heartbeat_timestamp.value < 2.0, "the heartbeat beats again")
        if during_take:
            app.wait(lambda: app.group.take is None, "the take ends in the group")
            assert app.record_stop().status_code == 200  # the stored summary of the error end
        response = app.apply([app.config(cid) for cid in app.factory.camera_ids], retry=app.factory.camera_ids)
        assert response.status_code == 200, response.text
        for camera_id in app.factory.camera_ids:
            app.wait_state(camera_id, "ready")
    if during_take:
        manifest = take_manifest(tmp_path)
        assert manifest["state"] == "finished"
        assert any("lost the server's heartbeat" in (w["detail"] or "") for w in take_warnings(tmp_path, "take_error"))
        counts = [len(take_rows(tmp_path, cid)) for cid in app.factory.camera_ids]
        assert counts[0] == counts[1] > 0, counts


def test_a_start_after_an_error_end_logs_the_unfetched_summary(monkeypatch, tmp_path):
    """Round 4, item 7: a record start while the summary of an error end waits for its stop request does not
    discard it silently: a WARNING names the take."""
    from skellycam.tests.capture.capture_session import capture_logs

    module = group_module()
    monkeypatch.setattr(module, "TAKE_QUEUE_SECONDS", 0.2)
    monkeypatch.setattr(module, "TAKE_STALL_LIMIT_S", 1.0)
    with capture_logs() as logs, capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        hold = WriterHold(monkeypatch, app.factory.camera_ids[0])
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 30)
        hold.start()
        app.wait(lambda: hold.stalled.is_set(), "`give` raises RecorderStalled")
        hold.stop()
        app.wait(lambda: app.group.ended_take is not None, "the error end")
        assert app.record_start(tmp_path, name="take2").status_code == 200
        stop(app)
    assert any("summary" in m and "take" in m for m in logs.messages(logging.WARNING)), logs.messages(logging.WARNING)


# ---------------------------------------------------------------------------
# Fix round 5 (2026-11-20)
# ---------------------------------------------------------------------------

def stalling_heartbeat(app):
    """Replace the stop event of the heartbeat writer: when `armed["on"]` is set, its next wait sleeps 12 s."""
    armed = {"on": False}

    class StallingEvent(threading.Event):
        def wait(self, timeout=None):
            if armed["on"] and threading.current_thread().name == "WorkerRegistry-Heartbeat":
                armed["on"] = False
                time.sleep(12.0)  # a long GIL hold, a debugger pause or a resume from sleep
            return super().wait(timeout)

    app.registry._heartbeat_stop = StallingEvent()
    return armed


def heartbeat_age(app):
    return time.perf_counter() - app.registry.heartbeat_timestamp.value


def test_a_request_while_the_heartbeat_is_stale_does_not_stop_the_group(monkeypatch, tmp_path):
    """Round 5, item 1: the main process serves a request while its heartbeat is stale (the cameras ended on
    it). The main process reads only the flags of the group, not the heartbeat: an apply works or reports
    each failure in its response. After the heartbeat beats again, an apply opens the cameras again. (The
    pause case went with the public pause route, ADR-V8RS.)"""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()], virtual=False) as app:
        armed = stalling_heartbeat(app)
        ready_app_steps(app)
        time.sleep(1.0)
        armed["on"] = True
        for camera_id in app.factory.camera_ids:
            app.wait_state(camera_id, "dead", timeout=30)
        assert heartbeat_age(app) > 10.0
        response = app.apply([app.config(cid) for cid in app.factory.camera_ids], retry=app.factory.camera_ids)
        assert response.status_code == 200, response.text
        failures = response.json()["camera_failures"]
        for camera_id in app.factory.camera_ids:  # each camera opened in the stale window is reported
            if app.state(camera_id) == "failed":
                assert failures[camera_id]["reason"] == "lost the server's heartbeat", failures
        assert not app.group.ipc.shutdown_camera_group_flag.value, "the request stopped the group for good"
        app.wait(lambda: heartbeat_age(app) < 2.0, "the heartbeat beats again")
        response = app.apply([app.config(cid) for cid in app.factory.camera_ids], retry=app.factory.camera_ids)
        assert response.status_code == 200, response.text
        for camera_id in app.factory.camera_ids:
            app.wait_state(camera_id, "ready")


def test_a_camera_that_loses_the_heartbeat_at_its_start_is_failed(monkeypatch, tmp_path):
    """Round 5, item 4 (windows-capture.md 8.2, 12): a camera whose start-up sees a stale heartbeat ends as
    `failed` after its close, with the reason "lost the server's heartbeat", and the apply response names it."""
    from skellycam.core.camera_group import camera_group_ipc

    stale = {"on": False}
    check = camera_group_ipc.check_main_process_heartbeat
    monkeypatch.setattr(camera_group_ipc, "check_main_process_heartbeat",
                        lambda **kwargs: False if stale["on"] else check(**kwargs))
    with capture_app(monkeypatch, [FakeScript()], virtual=False) as app:
        app.detect()
        camera_id = app.factory.camera_ids[0]
        stale["on"] = True
        response = app.apply([app.config(camera_id)])
        stale["on"] = False
        assert response.status_code == 200, response.text
        assert response.json()["camera_failures"][camera_id]["reason"] == "lost the server's heartbeat"
        status = app.status(camera_id)
        assert status["state"] == "failed" and status["closed"], status


def test_a_heartbeat_that_comes_back_at_once_still_ends_the_camera_with_its_reason(monkeypatch, tmp_path):
    """Round 5, item 3: the loop of a camera leaves on a stale heartbeat, and the heartbeat is fresh again at
    the next read. The end decides from the other reasons (no stop flag, no group or kill flag), not from a
    second read of the clock: the camera still gets the reason "lost the server's heartbeat"."""
    from skellycam.core.camera_group import camera_group_ipc

    stale = {"left": 0}
    check = camera_group_ipc.check_main_process_heartbeat

    def once_stale(**kwargs):
        if stale["left"] > 0 and threading.current_thread().name.startswith("Camera"):
            stale["left"] -= 1
            return False
        return check(**kwargs)

    monkeypatch.setattr(camera_group_ipc, "check_main_process_heartbeat", once_stale)
    with capture_app(monkeypatch, [FakeScript()], virtual=False) as app:
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        stale["left"] = 1  # one stale read: the loop test sees it, any later read is fresh
        app.wait_state(camera_id, "dead", timeout=30)
        assert app.status(camera_id)["failure"]["reason"] == "lost the server's heartbeat"


def test_a_second_shutdown_request_starts_no_second_close(monkeypatch, tmp_path):
    """Round 5, item 5: two shutdown requests during a take (the finish is 2 s slow). The second answers with no
    new close, and no ERROR line says "No recording runs": a 409 of the stop in a close is no error."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import skellycam.core.camera_group.camera_group_manager as manager_module
    from skellycam.api.http.app.shutdown import shutdown_router
    from skellycam.core.take_recorder import Take
    from skellycam.tests.capture.capture_session import capture_logs

    finish = Take.finish

    def slow_finish(take, *args, **kwargs):
        time.sleep(2.0)
        return finish(take, *args, **kwargs)

    monkeypatch.setattr(Take, "finish", slow_finish)
    monkeypatch.setattr(logging.Logger, "api", logging.Logger.info, raising=False)
    with capture_logs() as logs, capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        ready_app_steps(app)
        monkeypatch.setattr(manager_module, "_CAMERA_GROUP_MANAGER", app.manager)
        server = FastAPI()
        server.state.global_kill_flag = app.kill
        server.include_router(shutdown_router, prefix="/skellycam")
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(1.0)
        with TestClient(server) as client:
            assert client.get("/skellycam/shutdown").status_code == 200
            task = server.state.shutdown_task
            assert client.get("/skellycam/shutdown").status_code == 200
            assert server.state.shutdown_task is task, "a second close task"
            app.wait(lambda: app.kill.value, "the kill flag")
    assert take_manifest(tmp_path)["state"] == "finished"
    assert not [m for m in logs.messages(logging.ERROR) if "No recording runs" in m]


@pytest.mark.capture_timing
def test_a_shutdown_during_a_take_ends_each_camera_process_within_its_bound(monkeypatch, tmp_path):
    """Fix lane D: `/shutdown` during a take of three cameras with PROCESS workers and fake sources. Each camera
    process has ended, and the kill flag is set, within 3 s of the request (measured 2026-11-21: 0.27 s to
    0.29 s, also with a diagnostics dict of 600 `frame_log` rows). A real camera can add the time of its own
    close steps."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import skellycam.core.camera_group.camera_group_manager as manager_module
    from skellycam.api.http.app.shutdown import shutdown_router

    monkeypatch.setattr(logging.Logger, "api", logging.Logger.info, raising=False)
    with capture_app(monkeypatch, [FakeScript() for _ in range(3)], workers="process") as app:
        ready_app_steps(app)
        monkeypatch.setattr(manager_module, "_CAMERA_GROUP_MANAGER", app.manager)
        server = FastAPI()
        server.state.global_kill_flag = app.kill
        server.include_router(shutdown_router, prefix="/skellycam")
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(1.0)
        processes = [worker.worker for worker in app.group.cameras.camera_workers.values()]
        with TestClient(server) as client:
            assert client.get("/skellycam/shutdown").status_code == 200
            app.wait(lambda: app.kill.value and not any(p.is_alive() for p in processes), "the end", timeout=3.0)
    assert take_manifest(tmp_path)["state"] == "finished"


def test_the_kill_flag_is_set_when_the_close_before_exit_fails(monkeypatch):
    """Round 5, item 7: the background close of the shutdown endpoint raises; its `finally` still sets the kill
    flag, so the app ends."""
    import multiprocessing

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import skellycam.api.http.app.shutdown as shutdown_module

    async def failing_close():
        raise RuntimeError("test: the close fails")

    monkeypatch.setattr(shutdown_module, "close_camera_groups_before_exit", failing_close)
    monkeypatch.setattr(logging.Logger, "api", logging.Logger.info, raising=False)
    server = FastAPI()
    server.state.global_kill_flag = multiprocessing.Value("b", False)
    server.include_router(shutdown_module.shutdown_router, prefix="/skellycam")
    with TestClient(server) as client:
        assert client.get("/skellycam/shutdown").status_code == 200
        deadline = time.monotonic() + 10
        while not server.state.global_kill_flag.value and time.monotonic() < deadline:
            time.sleep(0.01)
    assert server.state.global_kill_flag.value


def test_a_failed_start_keeps_the_unfetched_summary(monkeypatch, tmp_path):
    """Round 5, item 6: after an error end, a record start that fails (a bad name: 422) keeps the stored
    summary: the next stop returns it."""
    module = group_module()
    monkeypatch.setattr(module, "TAKE_QUEUE_SECONDS", 0.2)
    monkeypatch.setattr(module, "TAKE_STALL_LIMIT_S", 1.0)
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        hold = WriterHold(monkeypatch, app.factory.camera_ids[0])
        ready_app_steps(app)
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 30)
        hold.start()
        app.wait(lambda: hold.stalled.is_set(), "`give` raises RecorderStalled")
        hold.stop()
        app.wait(lambda: app.group.ended_take is not None, "the error end")
        assert app.record_start(tmp_path, name="bad/name").status_code == 422
        stopped = app.record_stop()
        assert stopped.status_code == 200 and stopped.json()[0]["recording_name"] == "take", stopped.text


def live_state(app):
    """The group of the live state, as the state route and the `app_state` message give it."""
    return next(iter(app.manager.to_state_dict()["camera_groups"].values()))


def end_by_a_stall(monkeypatch, app, name="take"):
    """Start a take of two fakes, then hold the writer of the first camera past the stall limit; return its ID."""
    module = group_module()
    monkeypatch.setattr(module, "TAKE_QUEUE_SECONDS", 0.2)
    monkeypatch.setattr(module, "TAKE_STALL_LIMIT_S", 1.0)
    spies = Spies(monkeypatch, app)
    held = app.factory.camera_ids[0]
    hold = WriterHold(monkeypatch, held)
    ready_app_steps(app)
    assert app.record_start(app.directory, name=name).status_code == 200
    assert (live_state(app)["take_state"], live_state(app)["recording_in_progress"]) == ("recording", True)
    record_until(app, spies, 30)
    hold.start()
    app.wait(lambda: hold.stalled.is_set(), "`give` raises RecorderStalled")
    hold.stop()
    app.wait(lambda: live_state(app)["take_state"] == "ended_with_error", "the error end")
    return held


def test_t_rec_50_the_live_state_of_a_take_that_an_error_ended(monkeypatch, tmp_path):
    """T-REC-50 (recorder.md 8.4): a stall ends the take. The live state has `take_state` "ended_with_error",
    `recording_in_progress` false and `ended_take_summary` with the error text, the camera and the stop fields, as
    JSON; the stop request returns that summary once, and the state is then "none". A new take gives "recording",
    then "none"."""
    import json

    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        app.directory = tmp_path
        held = end_by_a_stall(monkeypatch, app)
        state = live_state(app)
        assert not state["recording_in_progress"]
        ended = state["ended_take_summary"]
        assert (ended["take_error"], ended["camera_id"]) == (f"disk stall on camera {held}", held), ended
        assert ended["summary"]["recording_name"] == "take" and "number_of_frames" in ended["summary"]
        json.dumps(state, allow_nan=False)  # the route and the websocket send it as JSON
        stopped = app.record_stop()
        assert stopped.status_code == 200 and stopped.json()[0]["recording_name"] == "take", stopped.text
        assert (live_state(app)["take_state"], live_state(app)["ended_take_summary"]) == ("none", None)
        assert app.record_stop().status_code == 409
        assert app.record_start(tmp_path, name="take2").status_code == 200
        assert live_state(app)["take_state"] == "recording"
        assert app.record_stop().status_code == 200
        assert live_state(app)["take_state"] == "none"


def test_t_rec_51_ended_with_error_stays_until_a_record_start_that_succeeds(monkeypatch, tmp_path):
    """T-REC-51 (recorder.md 8.4; a stall in place of the write error: the same take level end): no stop request.
    A record start refused with 409, and a record start that fails after `start_take` (a 500 of the writer wait,
    fix lane H), keep "ended_with_error" and the summary. A record start that succeeds gives "recording" and no
    summary; its stop ends the new take normally."""
    module = group_module()
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        app.directory = tmp_path
        end_by_a_stall(monkeypatch, app)
        assert app.record_start(tmp_path).status_code == 409  # the take folder holds files
        assert live_state(app)["take_state"] == "ended_with_error"
        await_writers = module.CameraGroup._await_writers

        during = []

        async def no_writer(group):
            during.append(group.to_state().take_state)
            raise RuntimeError("test: no writer started")

        monkeypatch.setattr(module.CameraGroup, "_await_writers", no_writer)
        assert app.record_start(tmp_path, name="failed").status_code == 500
        assert during == ["ended_with_error"]  # also during the start: the UI shows no old take again
        state = live_state(app)
        assert state["take_state"] == "ended_with_error"
        assert state["ended_take_summary"]["summary"]["recording_name"] == "take"
        monkeypatch.setattr(module.CameraGroup, "_await_writers", await_writers)
        assert app.record_start(tmp_path, name="take2").status_code == 200
        assert (live_state(app)["take_state"], live_state(app)["ended_take_summary"]) == ("recording", None)
        stopped = app.record_stop()
        assert stopped.status_code == 200 and stopped.json()[0]["recording_name"] == "take2", stopped.text
        assert live_state(app)["take_state"] == "none"


def test_t_req_61_take_orders_the_cameras_by_the_camera_index_of_the_request(monkeypatch, tmp_path):
    """T-REQ-61 [G7, H6] (`specs/camera-requests.md` 8.3): two fakes; the apply request gives camera A
    `camera_index` 2 and camera B `camera_index` 0; the source order is A, then B. Start a take. The
    configs of the response keep 2 and 0; in the manifest, B has `group_position` 0 and A has 1."""
    # The timing sidecar of each camera holds the same `group_position` (recorder.md 6.5).
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        camera_a, camera_b = app.factory.camera_ids
        response = ready_app_steps(app, [app.config(camera_a, camera_index=2), app.config(camera_b, camera_index=0)])
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 10)
        stop(app)
    configs = response.json()["camera_configs"]
    assert (configs[camera_a]["camera_index"], configs[camera_b]["camera_index"]) == (2, 0)
    positions = {item["camera_key"][:4]: item["group_position"] for item in take_manifest(tmp_path)["cameras"]}
    assert positions == {camera_b: 0, camera_a: 1}, positions
    for camera_id, (_, timing) in take_files(tmp_path).items():
        header = timing.read_text(encoding="utf-8").splitlines()
        assert f"# group_position={positions[camera_id]}" in header, camera_id
