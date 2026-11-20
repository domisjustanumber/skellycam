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


class WriterHold:
    """Holds the writer thread of one camera before its next row (the disk takes nothing). `stalled` is set
    when `give` of that camera raises `RecorderStalled`; `in_give` is true while its `give` waits."""

    def __init__(self, monkeypatch, camera_id):
        from skellycam.core.take_recorder import CameraTakeWriter, RecorderStalled

        self.camera_id = camera_id
        self.held, self.release, self.stalled = threading.Event(), threading.Event(), threading.Event()
        self.in_give = False
        take, give = CameraTakeWriter._take, CameraTakeWriter.give
        hold = self

        def held_take(writer, item):
            if writer.spec.camera_id == hold.camera_id and hold.held.is_set():
                hold.release.wait(120)
            return take(writer, item)

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
    # time runs ahead of the test (as in the old T-CAP-35). "Its process runs": its THREAD worker.
    from skellycam.tests.take_recorder.ebml import walk_file

    with capture_app(monkeypatch, [FakeScript(), FakeScript(), FakeScript()], track=True) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        live, dead = app.factory.camera_ids[:2], app.factory.camera_ids[2]
        assert app.record_start(tmp_path).status_code == 200
        record_until(app, spies, 60, [dead])
        app.factory.sources[dead].remove_now()
        app.wait(lambda: app.tracker.first(dead, "dead") is not None, "the camera is dead")
        t_dead = app.tracker.first(dead, "dead")
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


def test_t_rec_44_hang_ends_the_process_and_the_take_level_completes_its_file(monkeypatch, tmp_path):
    """T-REC-44 [R4, M5]: a bounded call of one fake hangs during a take. The failure is reported; the
    process ends within 1 s of the report; the take level completes its short file after the join;
    the others record to the stop."""
    # PROCESS workers in real time: the hard end of a camera thread would end the test process. The hung
    # call is the periodic control read on the control thread [U16]. It replaces T-CAP-85 (section 14).
    scripts = [FakeScript(hang_at="set_controls"), FakeScript()]
    with capture_app(monkeypatch, scripts, workers="process") as app:
        ready_app_steps(app)
        hung, other = app.factory.camera_ids
        ring = RingWatcher(app.ring_name(other))
        watcher = StateWatcher(app, hung)
        try:
            worker = app.worker(hung)
            assert app.record_start(tmp_path).status_code == 200
            time.sleep(1.0)
            app.factory.logs[hung].arm_hang()
            app.wait(lambda: watcher.failure is not None, "the failure is reported")
            exited = wait_exit(worker)
            assert worker.worker.exitcode not in (0, None), "the process did not end hard"
            after_report = (exited - watcher.failure_ns) / 1e9
            assert after_report <= 1.0, f"the process ended {after_report:.2f} s after the report"
            app.wait(lambda: any(f[1] > exited + 2 * 10**9 for f in ring.frames), "the other camera records on")
            summary = stop(app)
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
    # clock). Cases 2 and 3 use a stall limit of 1 s (real time, 5.3); each case has a queue of 0.2 s.
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
        # case 3
        hold.stalled.clear()
        assert app.record_start(tmp_path, name="take3").status_code == 200
        record_until(app, spies, len(spies.of("record", held_id)) + 30)
        hold.start()
        app.wait(lambda: app.group.ended_take is not None, "the take ends", timeout=60)
        stop(app)
        status = app.status(held_id)
        assert status["state"] == "failed" and status["failure"] == {
            "camera_id": held_id, "stage": "recording", "reason": "disk stall"}, status
        assert app.state(other) == "ready"
        key = camera_key_of(tmp_path, held_id, "take3")
        assert [w["camera_key"] for w in take_warnings(tmp_path, "camera_file_short", "take3")] == [key]
        assert take_warnings(tmp_path, "camera_dead", "take3")[0]["detail"].endswith("reason=disk stall")
        hold.stop()
        response = app.apply([app.config(cid) for cid in app.factory.camera_ids])
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
    fix, the pause timeout stopped the group, and the take stayed with the manifest `recording`."""
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
