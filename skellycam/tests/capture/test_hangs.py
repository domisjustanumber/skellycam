"""T-CAP-40, T-CAP-80, T-CAP-82, T-CAP-85, T-CAP-109 and T-CAP-110: a hung call, the hard end of a camera
process, the files message after a hang, a camera process that ends without unwinding, and the
first-frame limit (specs/windows-capture.md, sections 6.4, 6.6, 8.2 and 12).

These tests run PROCESS workers in real time: a hard end (`os._exit`) of a camera thread would end
the test process. The fake simulates a hung bounded call: it raises `CaptureFailure(..., hung=True)`
after `BOUNDED_CALL_LIMIT_S`, and a stuck thread stays (see `fake_source`). Each test takes 10 to 30 s.
T-CAP-40, T-CAP-82 and T-CAP-85 measure real gaps of 100 ms (U16): they have the marker `capture_timing`.
"""

import threading
import time

import pytest

from skellycam.tests.capture.capture_session import (
    SOURCE_MODULE, RingWatcher, StateWatcher, capture_app, column, product, ready_app_steps, recording_info,
    recording_info_json, ring_exists, video_frame_count, wait_exit)
from skellycam.tests.capture.fake_source import FakeScript

MODES = ((640, 480, 30, 1, "MJPG"), (320, 240, 30, 1, "MJPG"))


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


@pytest.mark.capture_timing
def test_t_cap_40_hang_in_open_ends_only_that_process(monkeypatch):
    """T-CAP-40, sections 6.6 and 8.2 [D10, agent 16]: a fake source in a real camera process hangs in
    `open` past the limit; a second camera streams. The failure arrives with stage `open`; the process
    exits within the limit plus 2 s; the main process cleans up only that camera; the second camera
    has no gap above 100 ms.

    The hang is at the reopen of a resolution change, so that the second camera streams in `ready`."""
    scripts = [FakeScript(modes=MODES, hang_at="open"), FakeScript(modes=MODES)]
    with capture_app(monkeypatch, scripts, workers="process") as app:
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
            assert watcher.failure["stage"] == "open"
            worker = watcher.worker
            exited = wait_exit(worker)
            hang_ns = log.hang_started_ns.value
            assert (exited - hang_ns) / 1e9 <= limit_s() + 2.0, f"exit {(exited - hang_ns) / 1e9:.2f} s after the hang"
            assert worker.worker.exitcode not in (0, None)
            time.sleep(1.0)
            thread.join(60)
            assert app.state(hung) == "failed"
            assert not ring_exists(old_ring)
            info = app.group.ring_infos.get(hung)
            assert info is None or not ring_exists(info.jpeg_ring_name)
            assert app.ring_name(streaming) == streaming_ring and app.worker(streaming).worker.pid == streaming_pid
            assert app.worker(streaming).is_alive() and app.state(streaming) == "ready"
        finally:
            watcher.stop()
            ring.stop()
        gap = ring.largest_gap_s(hang_ns - 10**9)
        assert gap <= 0.1, f"the streaming camera had a gap of {gap * 1000:.0f} ms"


@pytest.mark.capture_timing
def test_t_cap_82_hung_control_read_while_ready(monkeypatch):
    """T-CAP-82, sections 6.6, 8.2 and 11.4 [D10, D38, agent 60]: two fakes are `ready`; a control read
    of one hangs past its limit. That camera reports stage `streaming` and its process ends hard; the
    main process cleans up only it; the other camera has no gap above 100 ms.

    The periodic control read runs on the control thread of the camera process [U16], so the hung
    call does not hold the gate. The fake raises its failure from `set_controls` with stage `set
    controls`; the camera process reports `streaming` for a failure after the start-up (ADR-HP7D)."""
    scripts = [FakeScript(hang_at="set_controls"), FakeScript()]
    with capture_app(monkeypatch, scripts, workers="process") as app:
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
            assert watcher.failure["stage"] == "streaming"
            wait_exit(worker)
            assert worker.worker.exitcode not in (0, None), "the process did not end hard"
            hang_ns = log.hang_started_ns.value
            time.sleep(1.0)
            assert not ring_exists(hung_ring)
            assert app.ring_name(other) == other_ring and app.worker(other).worker.pid == other_pid
            assert app.worker(other).is_alive() and app.state(other) == "ready"
        finally:
            watcher.stop()
            ring.stop()
        gap = ring.largest_gap_s(hang_ns - 500_000_000)
        assert gap <= 0.1, f"the other camera had a gap of {gap * 1000:.0f} ms"


@pytest.mark.capture_timing
@pytest.mark.parametrize("close_s", [1.0, 8.0], ids=["file closes in 1 s", "file closes in 8 s"])
def test_t_cap_85_hang_during_a_recording(monkeypatch, tmp_path, close_s):
    """T-CAP-85, section 6.6 [U12]: during a recording, a bounded call of one fake hangs. Case 1: the
    recorder of that camera needs 1 s to close its file. Case 2: it needs 8 s. The failure is reported;
    case 1: the file is finished, and the process ends hard within 1.5 s of the report; case 2: the
    process ends hard 5.0 to 5.5 s after the report; in both cases the other cameras keep recording,
    with no gap above 100 ms [U16].

    The hung call is the periodic control read on the control thread [U16]. The report time is the
    time when the main process first sees the failure in the status."""
    scripts = [FakeScript(hang_at="set_controls", recorder_close_delay_s=close_s), FakeScript()]
    with capture_app(monkeypatch, scripts, workers="process") as app:
        ready_app_steps(app)
        hung, other = app.factory.camera_ids
        ring = RingWatcher(app.ring_name(other))
        watcher = StateWatcher(app, hung)
        try:
            worker = app.worker(hung)
            assert app.record_start(tmp_path).status_code == 200
            time.sleep(1.0)
            armed_ns = time.perf_counter_ns()
            app.factory.logs[hung].arm_hang()
            app.wait(lambda: watcher.failure is not None, "the failure is reported")
            exited = wait_exit(worker)
            after_report = (exited - watcher.failure_ns) / 1e9
            assert worker.worker.exitcode not in (0, None), "the process did not end hard"
            if close_s == 1.0:
                assert after_report <= 1.5, f"hard end {after_report:.2f} s after the report"
            else:
                assert 5.0 <= after_report <= 5.5, f"hard end {after_report:.2f} s after the report"
            app.wait(lambda: any(f[1] > exited + 2 * 10**9 for f in ring.frames), "the other camera records on")
            assert app.record_stop().status_code == 200
        finally:
            watcher.stop()
            ring.stop()
        gap = ring.largest_gap_s(armed_ns, exited + 10**9)
        assert gap <= 0.1, f"the other camera had a gap of {gap * 1000:.0f} ms"
        other_frames = video_frame_count(tmp_path, other)
        if close_s == 1.0:
            hung_frames = video_frame_count(tmp_path, hung)
            assert 0 < hung_frames < other_frames, "the file of the hung camera is not finished"
        else:
            assert other_frames > 0


@pytest.mark.parametrize("state", ["starting", "recording"])
def test_t_cap_109_a_camera_process_that_ends_without_unwinding(monkeypatch, tmp_path, state):
    """T-CAP-109, sections 6.6 and 8.2 [D10, ADR-PDD3]: the process of one camera ends with `os._exit(3)`, as
    after a native crash: (1) in `starting`, at the open; (2) in `recording`, at frame 300. The camera
    gets `failed` (1) or `dead` (2) with the reason "camera process ended (exit code 3)"; (1) the apply
    response names the failure, and the other camera reaches `ready`; (2) the other camera records on,
    and the stop of the recording returns 200 and names the camera in `dead_cameras`."""
    ending = FakeScript(exit_at="open") if state == "starting" else FakeScript(exit_at="frame:300")
    with capture_app(monkeypatch, [ending, FakeScript()], workers="process") as app:
        app.detect()
        ended, other = app.factory.camera_ids
        response = app.apply([app.config(ended), app.config(other)])
        assert response.status_code == 200, response.text
        reason = "camera process ended (exit code 3)"
        if state == "starting":
            assert response.json()["camera_failures"][ended] == {"camera_id": ended, "stage": "open", "reason": reason}
            app.wait_state(other, "ready")
            assert app.state(ended) == "failed"
            return
        app.wait_state(ended, "ready")
        app.wait_state(other, "ready")
        ring = RingWatcher(app.ring_name(other))
        try:
            assert app.record_start(tmp_path).status_code == 200
            app.wait_state(ended, "dead")
            assert app.status(ended)["failure"] == {"camera_id": ended, "stage": "streaming", "reason": reason}
            count = len(ring.frames)
            app.wait(lambda: len(ring.frames) > count + 30, "the other camera records on")
            stopped = app.record_stop()
            assert stopped.status_code == 200, stopped.text
        finally:
            ring.stop()
        assert [d["camera_id"] for d in recording_info_json(tmp_path)["dead_cameras"]] == [ended]


def test_t_cap_110_files_message_after_a_hang(monkeypatch, tmp_path):
    """T-CAP-110, section 6.6 [U12, ADR-PDD3]: during a recording of 10 s, the control read of one fake
    hangs. Its files message is larger than a pipe buffer (64 KiB). The message still reaches the main
    process before the hard end: the recording info names the camera in `dead_cameras` with the
    `last_frame_number` of the last row of its timing file, not null."""
    import numpy as np

    from skellycam.core.camera.config.camera_config import CameraConfig

    scripts = [FakeScript(hang_at="set_controls"), FakeScript()]
    with capture_app(monkeypatch, scripts, workers="process") as app:
        ready_app_steps(app)
        hung, other = app.factory.camera_ids
        worker = app.worker(hung)
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(10.0)
        app.factory.logs[hung].arm_hang()
        app.wait_state(hung, "dead")
        wait_exit(worker)
        assert worker.worker.exitcode not in (0, None), "the process did not end hard"
        assert app.record_stop().status_code == 200
    rows = column(recording_info(tmp_path).camera_timestamps_file_path_from_camera_id(hung), "connection_frame_number")
    dead = [d for d in recording_info_json(tmp_path)["dead_cameras"] if d["camera_id"] == hung]
    assert len(dead) == 1 and dead[0]["last_frame_number"] == int(rows[-1]), dead
    # each item of the message is the metadata of one recorded frame; its pickle is larger than its dtype
    one_row = np.dtype(product("skellycam.core.types.frame_dtype_factories").create_frame_dtype(
        CameraConfig(camera_id="a1b2", camera_index=0)))["frame_metadata"].itemsize
    assert len(rows) * one_row > 65536, f"{len(rows)} rows of {one_row} bytes fit in one pipe buffer"
