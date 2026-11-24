"""T-CAP-40, T-CAP-80, T-CAP-82, T-CAP-109 and T-CAP-110: a hung call, the hard end of a camera process,
the files of a take after a hang, a camera process that ends without unwinding, and the first-frame
limit (specs/windows-capture.md, sections 6.4, 6.6, 8.2 and 12). T-CAP-85 is replaced by T-REC-44
(specs/recorder.md section 14), in `skellycam/tests/take_recorder/test_connection.py`.

These tests run PROCESS workers in real time: a hard end (`os._exit`) of a camera thread would end
the test process. The fake simulates a hung bounded call: it raises `CaptureFailure(..., hung=True)`
after `BOUNDED_CALL_LIMIT_S`, and a stuck thread stays (see `fake_source`). Each test takes 10 to 30 s.
T-CAP-40 and T-CAP-82 measure real gaps of 100 ms (U16): they have the marker `capture_timing`. Each is a blocking
test and a `pace` test on one run (16.1; Q669 of the user [ADR-F4N7]).
"""

import threading
import time

import pytest

from skellycam.tests.capture.capture_session import (
    SOURCE_MODULE, RingWatcher, StateWatcher, camera_key_of, capture_app, product, ready_app_steps, ring_exists,
    take_rows, take_warnings, wait_exit)
from skellycam.tests.capture.fake_source import FakeScript
from skellycam.tests.pace import bound, one_run

MODES = ((640, 480, 30, 1, "MJPG"), (320, 240, 30, 1, "MJPG"))
FRAME_S = 1 / 30  # the nominal gap between two frames of one camera (16.1) [ADR-B7YV]


def limit_s():
    return product(SOURCE_MODULE).BOUNDED_CALL_LIMIT_S


def apply_in_thread(app, configs):
    result = []
    thread = threading.Thread(target=lambda: result.append(app.apply(configs)), daemon=True)
    thread.start()
    return thread, result


def test_t_cap_80_first_frame_limit_without_a_hard_end(monkeypatch):
    """T-CAP-80, sections 6.4 and 9.3 [D10, agent 14]: a fake whose first frame comes 6 s after the first
    `ReadSample`. Failed, stage `first frame`, 5.0 to 5.25 s after the first `ReadSample`; the close
    runs with its bounded steps; the process does not end hard (exit code 0).

    The 5 s wait is in the open of each source (6.4); the fake does it as a source does. The test
    checks how the loop and the process handle the failure."""
    with capture_app(monkeypatch, [FakeScript(first_frame_delay_s=6.0)], workers="process") as app:
        app.detect()
        camera_id = app.factory.camera_ids[0]
        watcher = StateWatcher(app, camera_id)
        try:
            thread, result = apply_in_thread(app, [app.config(camera_id)])
            app.wait(lambda: "failed" in watcher.first, "the camera fails")
            log = app.factory.logs[camera_id]
            elapsed = (watcher.first["failed"] - log.first_read_sample_ns.value) / 1e9
            assert 5.0 <= elapsed <= 5.25, f"failed {elapsed:.3f} s after the first ReadSample"
            assert watcher.failure["stage"] == "first frame"
            worker = watcher.worker
            wait_exit(worker)
            assert log.closes.value == 1, "the close did not run"
            assert worker.worker.exitcode == 0, f"exit code {worker.worker.exitcode}: a hard end"
            thread.join(60)
            assert result and result[0].status_code == 200
        finally:
            watcher.stop()


def _t_cap_40_run():
    """The run of T-CAP-40: the hang in `open` at the reopen of a resolution change, while a second camera streams.
    Gives the facts that the blocking test and the `pace` test check (no live object)."""
    scripts = [FakeScript(modes=MODES, hang_at="open"), FakeScript(modes=MODES)]
    with pytest.MonkeyPatch.context() as monkeypatch, capture_app(monkeypatch, scripts, workers="process") as app:
        ready_app_steps(app)
        hung, streaming = app.factory.camera_ids
        old_ring, streaming_ring = app.ring_name(hung), app.ring_name(streaming)
        streaming_pid = app.worker(streaming).worker.pid
        ring = RingWatcher(streaming_ring)
        watcher = StateWatcher(app, hung)
        log = app.factory.logs[hung]
        try:
            log.arm_hang()
            thread, _ = apply_in_thread(app, [app.config(hung, width=320, height=240), app.config(streaming)])
            app.wait(lambda: log.hang_started_ns.value > 0, "the hang starts")
            app.wait(lambda: watcher.failure is not None, "the failure arrives")
            stage = watcher.failure["stage"]
            worker = watcher.worker
            exited = wait_exit(worker)
            hang_ns = log.hang_started_ns.value
            exitcode = worker.worker.exitcode
            time.sleep(1.0)
            thread.join(60)
            info = app.group.ring_infos.get(hung)
            facts = dict(stage=stage, exit_s=(exited - hang_ns) / 1e9, exitcode=exitcode, state=app.state(hung),
                         old_ring=ring_exists(old_ring),
                         new_ring=info is not None and ring_exists(info.jpeg_ring_name),
                         same_streaming=(app.ring_name(streaming), app.worker(streaming).worker.pid)
                         == (streaming_ring, streaming_pid),
                         streaming=(app.worker(streaming).is_alive(), app.state(streaming)))
        finally:
            watcher.stop()
            ring.stop()
        facts["gap_s"] = ring.largest_gap_s(hang_ns - 10**9)
    return facts


@pytest.mark.capture_timing
def test_t_cap_40_hang_in_open_ends_only_that_process():
    """T-CAP-40, sections 6.6 and 8.2 [D10, agent 16]: a fake source in a real camera process hangs in
    `open` past the limit; a second camera streams. The failure arrives with stage `open`; the process
    exits; the main process cleans up only that camera; the second camera streams on.

    The hang is at the reopen of a resolution change, so that the second camera streams in `ready`. Blocking: the
    exit within 10 times the limit and no gap above 1 s (a camera that the hang holds stops for the 5 s of the
    limit); `test_t_cap_40_the_exit_and_the_gap_are_within_their_tolerance` holds the bounds of the spec (16.1)
    [ADR-F4N7]."""
    facts = one_run("T-CAP-40", _t_cap_40_run)
    assert facts["stage"] == "open"
    assert facts["exit_s"] <= 10 * limit_s(), f"exit {facts['exit_s']:.2f} s after the hang"
    assert facts["exitcode"] not in (0, None)
    assert facts["state"] == "failed"
    assert not facts["old_ring"] and not facts["new_ring"]
    assert facts["same_streaming"] and facts["streaming"] == (True, "ready"), facts
    assert facts["gap_s"] <= 1.0, f"the streaming camera had a gap of {facts['gap_s'] * 1000:.0f} ms"


@pytest.mark.pace  # Q669: only the bounds of time; their tolerances grow by the margin on a hosted runner
@pytest.mark.capture_timing
def test_t_cap_40_the_exit_and_the_gap_are_within_their_tolerance():
    """T-CAP-40, the bounds of time: the process exits within the limit plus 2 s (times the margin) after the hang
    starts, and the streaming camera has no gap above 100 ms. The nominal gap is one frame period (1/30 s); the
    margin multiplies the 67 ms past it [ADR-B7YV]. A CI run on macOS: 167 ms (CI run 45401541234)."""
    facts = one_run("T-CAP-40", _t_cap_40_run)
    assert facts["exit_s"] <= bound(limit_s(), limit_s() + 2.0), f"exit {facts['exit_s']:.2f} s after the hang"
    assert facts["gap_s"] <= bound(FRAME_S, 0.1), f"the streaming camera had a gap of {facts['gap_s'] * 1000:.0f} ms"


def _t_cap_82_run():
    """The run of T-CAP-82: the periodic control read of one camera hangs while both are `ready`. Gives the facts
    that the blocking test and the `pace` test check (no live object)."""
    scripts = [FakeScript(hang_at="set_controls"), FakeScript()]
    with pytest.MonkeyPatch.context() as monkeypatch, capture_app(monkeypatch, scripts, workers="process") as app:
        ready_app_steps(app)
        hung, other = app.factory.camera_ids
        hung_ring, other_ring = app.ring_name(hung), app.ring_name(other)
        other_pid = app.worker(other).worker.pid
        ring = RingWatcher(other_ring)
        watcher = StateWatcher(app, hung)
        log = app.factory.logs[hung]
        try:
            worker = app.worker(hung)
            log.arm_hang()
            app.wait(lambda: log.hang_started_ns.value > 0, "the periodic control read hangs")
            app.wait(lambda: watcher.failure is not None, "the failure arrives")
            stage = watcher.failure["stage"]
            wait_exit(worker)
            exitcode = worker.worker.exitcode
            hang_ns = log.hang_started_ns.value
            time.sleep(1.0)
            facts = dict(stage=stage, exitcode=exitcode, hung_ring=ring_exists(hung_ring),
                         same_other=(app.ring_name(other), app.worker(other).worker.pid) == (other_ring, other_pid),
                         other=(app.worker(other).is_alive(), app.state(other)))
        finally:
            watcher.stop()
            ring.stop()
        facts["gap_s"] = ring.largest_gap_s(hang_ns - 500_000_000)
    return facts


@pytest.mark.capture_timing
def test_t_cap_82_hung_control_read_while_ready():
    """T-CAP-82, sections 6.6, 8.2 and 11.4 [D10, D38, agent 60]: two fakes are `ready`; a control read
    of one hangs past its limit. That camera reports stage `streaming` and its process ends hard; the
    main process cleans up only it; the other camera streams on.

    The periodic control read runs on the control thread of the camera process [U16], so the hung
    call does not hold the gate. The fake raises its failure from `set_controls` with stage `set
    controls`; the camera process reports `streaming` for a failure after the start-up (ADR-HP7D). Blocking: no gap
    above 1 s (a hung read on the loop thread holds the gate for the 5 s of the limit);
    `test_t_cap_82_the_other_camera_has_no_gap_above_100_ms` holds the limit of U16 (16.1) [ADR-F4N7]."""
    facts = one_run("T-CAP-82", _t_cap_82_run)
    assert facts["stage"] == "streaming"
    assert facts["exitcode"] not in (0, None), "the process did not end hard"
    assert not facts["hung_ring"]
    assert facts["same_other"] and facts["other"] == (True, "ready"), facts
    assert facts["gap_s"] <= 1.0, f"the other camera had a gap of {facts['gap_s'] * 1000:.0f} ms"


@pytest.mark.pace  # Q669: U16, no gap above 100 ms: strict on a real machine; on CI it warns, it does not block
@pytest.mark.capture_timing
def test_t_cap_82_the_other_camera_has_no_gap_above_100_ms():
    """T-CAP-82, the bound of time of U16: the other camera has no gap above 100 ms. The nominal gap is one frame
    period (1/30 s); the margin multiplies the 67 ms past it [ADR-B7YV]. A CI run on macOS: 200 ms (CI run
    45401541234)."""
    facts = one_run("T-CAP-82", _t_cap_82_run)
    assert facts["gap_s"] <= bound(FRAME_S, 0.1), f"the other camera had a gap of {facts['gap_s'] * 1000:.0f} ms"


@pytest.mark.parametrize("state", ["starting", "recording"])
def test_t_cap_109_a_camera_process_that_ends_without_unwinding(monkeypatch, tmp_path, state):
    """T-CAP-109, sections 6.6 and 8.2 [D10, ADR-PDD3]: the process of one camera ends with `os._exit(3)`, as
    after a native crash: (1) in `starting`, at the open; (2) in `recording`, at frame 300. The camera
    gets `failed` (1) or `dead` (2) with the reason "camera process ended (exit code 3)"; (1) the apply
    response names the failure, and the other camera reaches `ready`; (2) the other camera records on,
    and the stop of the recording returns 200; the manifest has `camera_dead` for the camera with the
    exit code, and its files are completed to the frame count of the take (recorder.md 7.4) [M5, M8]."""
    ending = FakeScript(exit_at="open") if state == "starting" else FakeScript(exit_at="frame:300")
    with capture_app(monkeypatch, [ending, FakeScript()], workers="process") as app:
        app.detect()
        ended, other = app.factory.camera_ids
        response = app.apply([app.config(ended), app.config(other)])
        assert response.status_code == 200, response.text
        reason = "camera process ended (exit code 3)"
        if state == "starting":
            assert response.json()["camera_failures"][ended] == {"camera_id": ended, "stage": "open", "reason": reason,
                                                                  "code": "process-ended"}
            app.wait_state(other, "ready")
            assert app.state(ended) == "failed"
            return
        app.wait_state(ended, "ready")
        app.wait_state(other, "ready")
        ring = RingWatcher(app.ring_name(other))
        try:
            assert app.record_start(tmp_path).status_code == 200
            app.wait_state(ended, "dead")
            assert app.status(ended)["failure"] == {"camera_id": ended, "stage": "streaming", "reason": reason,
                                                      "code": "process-ended"}
            count = len(ring.frames)
            app.wait(lambda: len(ring.frames) > count + 30, "the other camera records on")
            stopped = app.record_stop()
            assert stopped.status_code == 200, stopped.text
        finally:
            ring.stop()
        frame_count = stopped.json()[0]["number_of_frames"]
    dead = take_warnings(tmp_path, "camera_dead")
    assert [w["camera_key"] for w in dead] == [camera_key_of(tmp_path, ended)], dead
    assert dead[0]["detail"].endswith("reason=exit code 3"), dead
    assert [len(take_rows(tmp_path, cid)) for cid in (ended, other)] == [frame_count, frame_count]


@pytest.mark.capture_timing  # real time: a take of 10 s
def test_t_cap_110_files_after_a_hang(monkeypatch, tmp_path):
    """T-CAP-110, section 6.6 [ADR-PDD3], changed by step 5a [R4, M5, M8]: during a recording of 10 s, the
    control read of one fake hangs; its process ends at once. After the stop, the take level completed its
    files: the manifest names the camera in `camera_dead` with the reason "hang" and the `last_frame` of
    the last row of its sidecar with a block, not `none`; `camera_file_short` names it; its sidecar has
    the frame count of the take. Before step 5a the camera process sent a files message of more than a
    pipe buffer before its hard end (U12).

    The last row with a block is not before the row of the frame count that the test reads when it arms the hang
    (Q671): each frame that the camera took before the arm is in its file. No fixed count of rows: on a slow CI
    runner the last row with a block was 188 after 10 s (CI run 45401541234, macOS) [ADR-F4N7]."""
    from skellycam.core.take_recorder.sidecar import MISSING

    scripts = [FakeScript(hang_at="set_controls"), FakeScript()]
    with capture_app(monkeypatch, scripts, workers="process") as app:
        ready_app_steps(app)
        hung, other = app.factory.camera_ids
        worker = app.worker(hung)
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(10.0)
        orchestrator = app.group.cameras.orchestrator
        armed_row = orchestrator.camera_statuses[hung].frame_count.value - orchestrator.first_recording_frame_number.value
        app.factory.logs[hung].arm_hang()
        app.wait_state(hung, "dead")
        wait_exit(worker)
        assert worker.worker.exitcode not in (0, None), "the process did not end hard"
        stopped = app.record_stop()
        assert stopped.status_code == 200, stopped.text
    frame_count = stopped.json()[0]["number_of_frames"]
    rows = take_rows(tmp_path, hung)
    assert len(rows) == frame_count == len(take_rows(tmp_path, other))
    last = max(row.frame for row in rows if row.byte_offset is not None and not row.flags & MISSING)
    key = camera_key_of(tmp_path, hung)
    dead = [w for w in take_warnings(tmp_path, "camera_dead") if w["camera_key"] == key]
    assert len(dead) == 1 and dead[0]["detail"] == f"last_frame={last} reason=hang", dead
    assert armed_row > 0 and last >= armed_row, f"the last row with a block is {last}; the row at the arm was {armed_row}"
    assert [w["camera_key"] for w in take_warnings(tmp_path, "camera_file_short")] == [key]


def test_record_stop_after_a_hang_then_close(monkeypatch, tmp_path):
    """Open work of phase 3, found after the 3a hardware run: after a hang during a recording and a record
    stop, the close of the group gave "Record requested before video_recorder was created" in the other
    camera (T-CAP-85 case 2). The close stopped the take a second time, because the process that ended
    hard left its recording flag set, and the second stop set a last frame that recorded again. Now the
    close stops only a take that runs, and no frame is recorded with no take
    (`test_no_recording_after_the_take_ended`). The other camera ends with no failure."""
    scripts = [FakeScript(hang_at="set_controls"), FakeScript()]
    with capture_app(monkeypatch, scripts, workers="process") as app:
        ready_app_steps(app)
        hung, other = app.factory.camera_ids
        worker = app.worker(hung)
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(1.0)
        app.factory.logs[hung].arm_hang()
        wait_exit(worker)
        assert app.record_stop().status_code == 200
        status = app.group.cameras.orchestrator.camera_statuses[other]
        app.client.delete("/skellycam/camera/group/close/all")
        assert status.info_dict().get("failure") is None, status.info_dict().get("failure")
        assert not app.group_or_none() or app.group.take is None


@pytest.mark.parametrize("end", ["hang", "crash"])
def test_apply_and_a_new_take_after_a_hard_end_during_a_take(monkeypatch, tmp_path, end):
    """Review fault 1 of the connection (2026-11-20): a camera process that ends hard during a take (a hang,
    or `os._exit(3)` as after a native crash) left its recording flag set, so each later apply and record
    start got 409 "A recording runs" (D36). After the stop, an apply that unselects that camera is
    accepted, and a new take of the other camera starts and stops."""
    ending = FakeScript(hang_at="set_controls") if end == "hang" else FakeScript(exit_at="frame:300")
    with capture_app(monkeypatch, [ending, FakeScript()], workers="process") as app:
        ready_app_steps(app)
        ended, other = app.factory.camera_ids
        worker = app.worker(ended)
        assert app.record_start(tmp_path).status_code == 200
        if end == "hang":
            time.sleep(1.0)
            app.factory.logs[ended].arm_hang()
        wait_exit(worker)
        stopped = app.record_stop()
        assert stopped.status_code == 200, stopped.text
        response = app.apply([app.config(ended, use_this_camera=False), app.config(other)])
        assert response.status_code == 200, response.text
        app.wait_state(other, "ready")
        started = app.record_start(tmp_path, name="take2")
        assert started.status_code == 200, started.text
        time.sleep(0.5)
        stopped = app.record_stop()
        assert stopped.status_code == 200, stopped.text
    assert len(take_rows(tmp_path, other, "take2")) == stopped.json()[0]["number_of_frames"] > 0
