"""T-UNX-75 and the risk guard of the main-process stall watch (specs/unix-capture.md 4.10;
specs/windows-capture.md 9.5; ADR-AC5B items 1 and 11).

The shared loop adds one to `CameraStatus.alive_count` at each pass, and a wait of the loop in the recorder
adds one at least each 0.5 s. The watch thread of the group ends a camera whose counter did not change for
2.5 s in a watched state: the limit of 2 s (ADR-22EJ item 14, Q850) plus a head start of 0.5 s for the
in-process rule of W 9.5, which thus decides when frames stop (Q863 [ADR-3RJJ]; Q874 [ADR-EQ3K]). These tests check that it ends a camera that cannot run a loop pass, and that it
ends no healthy camera: a `waiting` camera, the internal pause of a record start, a wait in the recorder, a
slow close of a reopen, the OpenCV fake (a pull source), and cameras under a load of the main process.

T-UNX-18 and T-UNX-45 (the in-process stall rule of W 9.5 with the V4L2 and AVFoundation fakes) wait for
steps 7a and 7b; T-CAP-36 checks that rule with the fake source.

Each test has the marker `capture_timing`. Most run in real time; T-UNX-109 runs on the virtual clock of
`capture_session`.
"""

import asyncio
import importlib
import threading
import time
from types import SimpleNamespace

import psutil
import pytest

from skellycam.tests.capture.capture_session import (
    CaptureApp, OpenCVFakeFactory, RingWatcher, Spies, StateWatcher, capture_app, ready_app_steps, wait_exit)
from skellycam.tests.capture.fake_source import FakeScript
from skellycam.tests.pace import bound, one_run

pytestmark = pytest.mark.capture_timing


def status_of(app, camera_id):
    return app.group.cameras.orchestrator.camera_statuses[camera_id]


class AliveWatcher:
    """Polls `alive_count` of one camera each 2 ms; `last_change` is the `perf_counter` time of its last change,
    `max_gap` the longest time with no change."""

    def __init__(self, status):
        self.status, self.last_change, self.count = status, time.perf_counter(), status.alive_count.value
        self.max_gap = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            count = self.status.alive_count.value
            if count != self.count:
                now = time.perf_counter()
                self.max_gap = max(self.max_gap, now - self.last_change)
                self.count, self.last_change = count, now
            time.sleep(0.002)

    def stop(self):
        self._stop.set()
        self._thread.join(5)


def no_camera_ended(watchers):
    return {cid: w.first for cid, w in watchers.items() if "dead" in w.first or "failed" in w.first or w.failure}


def test_t_unx_75_a_suspended_camera_process_ends_as_stalled(monkeypatch):
    """T-UNX-75: three fake cameras in real camera processes; the process of one is suspended (`psutil`
    `suspend()`), so it runs no loop pass. The main process removes it from the gate and ends it 2.5 to
    3.0 s after its last loop pass: `dead`, `stalled`. The third camera has no gap longer than 3.0 s; the
    second stays `ready`."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript(), FakeScript()], workers="process") as app:
        ready_app_steps(app)
        stalled, second, third = app.factory.camera_ids
        ring = RingWatcher(app.ring_name(third))
        alive = AliveWatcher(status_of(app, stalled))
        worker = app.worker(stalled)
        process = psutil.Process(worker.worker.pid)
        try:
            time.sleep(1.0)
            process.suspend()
            app.wait_state(stalled, "dead", timeout=10)
            dead_at = time.perf_counter()
            took = dead_at - alive.last_change
            wait_exit(worker, timeout=5)
            time.sleep(1.0)
        finally:
            alive.stop()
            ring.stop()
            if process.is_running():
                process.resume()
        assert 2.5 <= took <= 3.0, f"dead {took:.3f} s after the last loop pass"
        assert app.status(stalled)["failure"] == {"camera_id": stalled, "stage": "streaming",
                                                  "reason": "no loop pass for 2.5 s", "code": "stalled"}
        assert app.state(second) == "ready" and app.state(third) == "ready"
        gap = ring.largest_gap_s()
        assert gap <= 3.0, f"the third camera had a gap of {gap:.2f} s"


def test_t_unx_75_waiting_pause_and_a_slow_reopen_trip_nothing(monkeypatch):
    """T-UNX-75: in real camera processes, two cameras are `waiting` for 4 s while the third opens; then the
    internal pause of a record start holds each camera for 4 s; then a size change reopens one camera whose
    close takes 3 s. No camera ends; no failure."""
    scripts = [FakeScript(modes=((640, 480, 30, 1, "MJPG"), (1280, 720, 30, 1, "MJPG")), close_delay_s=3.0),
               FakeScript(), FakeScript(open_delay_s=4.0)]
    with capture_app(monkeypatch, scripts, workers="process") as app:
        reopened = app.factory.camera_ids[0]
        app.detect()
        watchers = {cid: StateWatcher(app, cid) for cid in app.factory.camera_ids}  # they wait for the group
        response = app.apply([app.config(cid) for cid in app.factory.camera_ids])
        assert response.status_code == 200, response.text
        for camera_id in app.factory.camera_ids:
            app.wait_state(camera_id, "ready")
        assert all("waiting" in watchers[cid].first for cid in app.factory.camera_ids[:2]), \
            {cid: w.first for cid, w in watchers.items()}
        orchestrator = app.group.cameras.orchestrator
        asyncio.run(orchestrator.pause(await_paused=True))
        time.sleep(4.0)
        asyncio.run(orchestrator.unpause(await_unpaused=True))
        response = app.apply([app.config(reopened, width=1280, height=720)] +
                             [app.config(cid) for cid in app.factory.camera_ids[1:]])
        assert response.status_code == 200, response.text
        app.wait_state(reopened, "ready")
        assert app.status(reopened)["mode"]["width"] == 1280
        time.sleep(1.0)
        for watcher in watchers.values():
            watcher.stop()
    assert not no_camera_ended(watchers), no_camera_ended(watchers)


def test_t_unx_75_recorder_waits_trip_nothing(monkeypatch, tmp_path):
    """T-UNX-75: the writer of one camera is held for 4 s under the stall limit: its loop waits in `give`
    and trips nothing. Then, with a stall limit of 1 s, the writer is held for good: the take ends by the
    rule of recorder.md 5.3 (`disk stall`), not by this watch: no camera is `dead` with `stalled`."""
    from skellycam.tests.take_recorder.test_connection import WriterHold, record_until, stop, wait_blocked_in_give

    import skellycam.core.camera_group.camera_group as group_module

    monkeypatch.setattr(group_module, "TAKE_QUEUE_SECONDS", 0.2)
    app = CaptureApp(monkeypatch, OpenCVFakeFactory(monkeypatch, count=2))
    hold = None
    try:
        spies = Spies(monkeypatch, app)
        held_id, other = app.factory.camera_ids
        hold = WriterHold(monkeypatch, held_id)
        ready_app_steps(app)
        watchers = {cid: StateWatcher(app, cid) for cid in app.factory.camera_ids}
        assert app.record_start(tmp_path, name="take1").status_code == 200
        record_until(app, spies, 30)
        hold.start()
        wait_blocked_in_give(app, spies, hold)
        time.sleep(4.0)
        hold.stop()
        count = len(spies.of("record", held_id))
        app.wait(lambda: len(spies.of("record", held_id)) > count + 30, "the take goes on")
        stop(app)
        assert not no_camera_ended(watchers), no_camera_ended(watchers)
        monkeypatch.setattr(group_module, "TAKE_STALL_LIMIT_S", 1.0)
        assert app.record_start(tmp_path, name="take2").status_code == 200
        record_until(app, spies, len(spies.of("record", held_id)) + 30)
        hold.start()
        app.wait(lambda: hold.stalled.is_set(), "`give` raises RecorderStalled")
        hold.stop()
        app.wait(lambda: app.group.ended_take is not None, "the take ends")
        time.sleep(3.0)
        for watcher in watchers.values():
            watcher.stop()
        assert not no_camera_ended(watchers), no_camera_ended(watchers)
        assert app.state(held_id) == "ready" and app.state(other) == "ready"
    finally:
        if hold is not None:
            hold.stop()
        app.close()


def test_t_unx_75_the_opencv_fake_streams_10_s(monkeypatch):
    """T-UNX-75: the OpenCV source (a pull source) streams for 10 s with the watch on: no camera ends."""
    app = CaptureApp(monkeypatch, OpenCVFakeFactory(monkeypatch, count=2))
    try:
        ready_app_steps(app)
        watchers = {cid: StateWatcher(app, cid) for cid in app.factory.camera_ids}
        counts = {cid: status_of(app, cid).alive_count.value for cid in app.factory.camera_ids}
        time.sleep(10.0)
        for watcher in watchers.values():
            watcher.stop()
        assert not no_camera_ended(watchers), no_camera_ended(watchers)
        assert all(status_of(app, cid).alive_count.value > counts[cid] + 100 for cid in counts)
    finally:
        app.close()


def busy(stop):
    while not stop.is_set():
        sum(i * i for i in range(10_000))


def _under_load_run(workers):
    """The run of the risk guard under load: two fake cameras stream for 12 s on the real clock while four threads of
    the main process run Python with no pause. Gives the facts that the blocking test and the `pace` test check."""
    with pytest.MonkeyPatch.context() as monkeypatch, capture_app(monkeypatch, [FakeScript(), FakeScript()], workers=workers, virtual=False) as app:
        ready_app_steps(app)
        watchers = {cid: StateWatcher(app, cid) for cid in app.factory.camera_ids}
        counts = {cid: status_of(app, cid).alive_count.value for cid in app.factory.camera_ids}
        alive = {cid: AliveWatcher(status_of(app, cid)) for cid in app.factory.camera_ids}
        stop = threading.Event()
        load = [threading.Thread(target=busy, args=(stop,), daemon=True) for _ in range(4)]
        for thread in load:
            thread.start()
        try:
            time.sleep(12.0)
        finally:
            stop.set()
            for thread in load:
                thread.join(5)
        time.sleep(0.5)
        for watcher in [*watchers.values(), *alive.values()]:
            watcher.stop()
        return dict(ended=no_camera_ended(watchers), states={cid: app.state(cid) for cid in counts},
                    passes={cid: status_of(app, cid).alive_count.value - counts[cid] for cid in counts},
                    gaps={cid: round(watcher.max_gap, 3) for cid, watcher in alive.items()})


@pytest.mark.parametrize("workers", ["thread", "process"])
def test_the_watch_ends_no_healthy_camera_under_load(workers):
    """The risk guard: two fake cameras stream for 12 s on the real clock while four threads of the main
    process run Python with no pause (they hold the GIL in turns with the watch thread and, with THREAD
    workers, with the camera loops: then a loop makes only about 5 passes each second). No camera ends;
    each camera keeps its loop passes, with no pause near the limit of 2 s. The bound on the pause is in
    `test_the_loop_passes_have_no_pause_above_1_s_under_load`, with THREAD workers (Q672) [ADR-F4N7] and with
    PROCESS workers (Q721) [ADR-2AQT]. On the CI runners it was 0.78 s to 1.20 s with THREAD workers (CI runs
    45401541234 and 45412934839), and 1.067 s with PROCESS workers (CI run 45493213866)."""
    facts = one_run(("under load", workers), lambda: _under_load_run(workers))
    assert not facts["ended"], facts["ended"]
    assert all(state == "ready" for state in facts["states"].values()), facts["states"]
    assert all(value > 30 for value in facts["passes"].values()), facts["passes"]


@pytest.mark.pace  # Q672, Q721: the pause of the loop passes under a load of the main process depends on the pace
@pytest.mark.parametrize("workers", ["thread", "process"])
def test_the_loop_passes_have_no_pause_above_1_s_under_load(workers):
    """The risk guard, the bound of time: no pause of the loop passes of 1 s or more, with THREAD workers (Q672) and
    with PROCESS workers (Q721) [ADR-2AQT]. The nominal pause is one frame period (1/30 s); the margin multiplies
    the part past it [ADR-B7YV]."""
    facts = one_run(("under load", workers), lambda: _under_load_run(workers))
    assert all(gap < bound(1 / 30, 1.0) for gap in facts["gaps"].values()), facts["gaps"]


# ---------------------------------------------------------------------------
# Review round of 2026-11-20 (F1, F2, F5, F6, F9)
# ---------------------------------------------------------------------------

def stalled_forever():
    while True:
        time.sleep(1)


def test_f1_a_tripped_camera_with_a_take_ends_within_1_s():
    """F1 (the experiment `end_process_delay.py`): `ManagedProcess.terminate` first waits for the save of a take
    while `recording_in_progress` is set (15 s). The watch clears it and marks the stop as intended, so the
    process ends within about 1 s, and the registry logs no crash.

    [ADR-DC43] item 3: the product stays as unix-capture.md 4.10 states it: `terminate`, then `kill` after 1 s, with
    no wait for the end. On POSIX the SIGTERM handler of a camera process only sets the stop flag, and SIGKILL does
    not wait for the end. Thus the test joins for at most 1 s after `_end_process` and measures up to the end. The
    bound of 2 s stays."""
    from skellycam.core.camera_group.camera_group import CameraGroup
    from skellycam.core.camera_group.camera_status import CameraStatus
    from skellycam.core.ipc.process_management.managed_worker import ManagedProcess

    status = CameraStatus()
    status.recording_in_progress.value = True
    worker = ManagedProcess(target=stalled_forever, name="cam", shutdown_flag=status.should_close, log_queue=None)
    worker.protect_recording(status.recording_in_progress, status.writer_progress_at)
    worker.start()
    time.sleep(1.0)
    t0 = time.monotonic()
    CameraGroup._end_process(SimpleNamespace(worker=worker, join=worker.join, is_alive=worker.is_alive), status)
    # On POSIX the SIGTERM handler of the camera process only sets the stop flag: `kill` after 1 s ends this
    # process, and SIGKILL does not wait for the end. Thus wait for the end, and measure up to it (CI run
    # 45278395951, ubuntu-24.04: `is_alive()` just after the kill).
    worker.join(timeout=1.0)
    took = time.monotonic() - t0
    assert not worker.is_alive() and took < 2.0, f"ended {took:.1f} s after the trip"
    assert worker.intentionally_terminated and not status.recording_in_progress.value


def test_f1_a_trip_during_a_take(monkeypatch, tmp_path):
    """F1, F5: the process of one camera is suspended during a take. It ends within about 1 s of the trip; the
    stop answers in normal time; the take finishes with that camera's rows marked missing to the stop (the take
    level completes the files of an ended process, recorder.md 7.4), and its
    `camera_dead` warning gives the reason of the watch, not an exit code."""
    from skellycam.core.camera_group.camera_group import STALL_REASON

    with capture_app(monkeypatch, [FakeScript(), FakeScript()], workers="process") as app:
        ready_app_steps(app)
        stalled = app.factory.camera_ids[0]
        worker = app.worker(stalled)
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(1.5)
        process = psutil.Process(worker.worker.pid)
        process.suspend()
        try:
            app.wait_state(stalled, "dead", timeout=10)
            tripped = time.perf_counter_ns()
            ended = wait_exit(worker, timeout=10)
        finally:
            if process.is_running():
                process.resume()
        assert (ended - tripped) / 1e9 < 1.5, f"the process ended {(ended - tripped) / 1e9:.1f} s after the trip"
        time.sleep(1.5)  # the other camera records on: rows of the dead camera to the stop
        t0 = time.monotonic()
        stopped = app.record_stop()
        assert stopped.status_code == 200, stopped.text
        assert time.monotonic() - t0 < 10.0
    from skellycam.core.take_recorder.sidecar import MISSING
    from skellycam.tests.capture.capture_session import camera_key_of, take_rows, take_warnings

    frame_count = stopped.json()[0]["number_of_frames"]
    rows = take_rows(tmp_path, stalled)
    last = max(row.frame for row in rows if not row.flags & MISSING)
    assert len(rows) == frame_count and rows[last + 1:] and all(row.flags & MISSING for row in rows[last + 1:])
    dead = [w for w in take_warnings(tmp_path, "camera_dead") if w["camera_key"] == camera_key_of(tmp_path, stalled)]
    assert len(dead) == 1, dead
    dead = dead[0]
    assert dead["detail"].endswith(f"reason={STALL_REASON}"), dead


@pytest.mark.parametrize("trial", range(2))
def test_f6_the_in_process_rule_wins_when_frames_stop(monkeypatch, trial):
    """F6 (the experiment `test_race_scratch.py`): three cameras whose frames stop, in real camera processes.
    The in-process rule of W 9.5 (2 s) ends each one, never the main-process watch (Q863 [ADR-3RJJ]): the watch counts
    from its first round that sees the last loop pass, which comes after the last arrival, and waits 2 s plus a head
    start of 0.5 s. The in-process rule finishes the files and closes the camera; the watch kills it."""
    scripts = [FakeScript(stop_after_frame=n) for n in (200, 215, 230)]
    with capture_app(monkeypatch, scripts, workers="process") as app:
        ready_app_steps(app)
        for camera_id in app.factory.camera_ids:
            app.wait_state(camera_id, "dead", timeout=30)
        reasons = [(app.status(cid)["failure"]["reason"], app.status(cid)["failure"]["code"])
                   for cid in app.factory.camera_ids]
    assert reasons == [("no frame for 2 s", "stalled")] * 3, reasons


class FakeMonotonic:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


def watch_group(monkeypatch, state="ready"):
    import skellycam.core.camera_group.camera_group as group_module
    from skellycam.tests.capture.test_group_watch import bare_group, status_in

    clock = FakeMonotonic()
    monkeypatch.setattr(group_module, "time", SimpleNamespace(monotonic=clock.monotonic))
    ended = []
    monkeypatch.setattr(group_module.CameraGroup, "_end_process", staticmethod(lambda worker, status: ended.append(1)))
    status = status_in(state)
    worker = SimpleNamespace(worker=SimpleNamespace(exitcode=None))
    group = bare_group({"cam0": worker}, {"cam0": status})
    return group, status, worker, clock, ended


def step(group, worker, clock, seconds):
    clock.now += seconds
    thread = threading.Thread(target=group._watch_passes, args=("cam0", worker), daemon=True)
    thread.start()
    thread.join(1.0)
    assert not thread.is_alive(), "the watch blocked"


def test_f2_the_watch_trips_after_the_head_start(monkeypatch):
    """F2 (ii), Q863 [ADR-3RJJ]: no loop pass for 2.0 s (the deadline of the in-process rule of W 9.5) trips nothing,
    nor 2.4 s; 2.5 s (the limit of 2 s of Q850 plus the head start of 0.5 s, Q874 [ADR-EQ3K]) trips, with the
    reason and the code of 4.10."""
    group, status, worker, clock, ended = watch_group(monkeypatch)
    step(group, worker, clock, 0)
    step(group, worker, clock, 2.0)
    assert status.state == "ready" and not ended
    step(group, worker, clock, 0.4)
    assert status.state == "ready" and not ended
    step(group, worker, clock, 0.1)
    assert status.state == "dead" and ended
    assert status.info_dict()["failure"] == {"camera_id": "cam0", "stage": "streaming",
                                             "reason": "no loop pass for 2.5 s", "code": "stalled"}


def test_f2_the_in_process_rule_decides_in_the_head_start(monkeypatch):
    """Q863 [ADR-3RJJ]: the watch runs a round each 0.1 s while the frames stop. The in-process rule fires at its
    deadline (2 s after the last loop pass at the latest) and sets the failure, then `dead`, 50 ms later. No round
    of the watch trips before it, and none after it: the camera keeps the failure of the in-process rule, and the
    watch ends no process."""
    group, status, worker, clock, ended = watch_group(monkeypatch)
    step(group, worker, clock, 0)
    for _ in range(20):  # the rounds up to 2.0 s
        step(group, worker, clock, 0.1)
    step(group, worker, clock, 0.02)  # a round just past the deadline of the in-process rule
    assert status.state == "ready" and not ended
    clock.now += 0.03
    failure = {"camera_id": "cam0", "stage": "streaming", "reason": "no frame for 2 s", "code": "stalled"}
    status.update_info(failure=failure)
    status.set_state("dead")
    for _ in range(20):
        step(group, worker, clock, 0.1)
    assert not ended and status.state == "dead"
    assert status.info_dict()["failure"] == failure


@pytest.mark.parametrize("case", ["paused", "watch off", "closing"])
def test_f2_f9_the_watch_is_off_while_paused_when_set_off_and_in_a_close(monkeypatch, case):
    """F2 (i), (iii), F9: the internal record-start pause (`should_pause`), `SKELLYCAM_STALL_WATCH=0` (read when
    the group is made) and a close (`closing`) turn the watch off."""
    group, status, worker, clock, ended = watch_group(monkeypatch)
    if case == "paused":
        status.should_pause.value = True
    elif case == "watch off":
        group.stall_watch = False
    else:
        status.closing.value = True
    for _ in range(5):
        step(group, worker, clock, 1.0)
    assert status.state == "ready" and not ended


def test_f2_the_counter_and_the_other_scalars_of_the_status_have_no_lock():
    """The experiment `suspend_lock.py`: a camera process suspended or ended inside `alive_count += 1` kept the
    lock of the counter (0 of 200 tries on this machine, but possible). Each scalar of the status now has no lock
    (fix lane G), so no read of the main process can wait for it."""
    import dataclasses

    from skellycam.core.camera_group.camera_status import ARRAYS, CameraStatus

    status = CameraStatus()
    scalars = [f.name for f in dataclasses.fields(status) if f.name not in (
        *ARRAYS, "diagnostics", "owner", "holder_dead", "last_good", "pending_info", "no_lock")]
    assert "alive_count" in scalars and "state_index" in scalars
    assert not [name for name in scalars if hasattr(getattr(status, name), "get_lock")]


def test_f2_the_setting_turns_the_watch_off_and_is_logged(monkeypatch):
    """F2 (iii): with `SKELLYCAM_STALL_WATCH=0` the group has the watch off, and its start logs that."""
    from skellycam.tests.capture.capture_session import capture_logs

    monkeypatch.setenv("SKELLYCAM_STALL_WATCH", "0")
    with capture_logs() as logs, capture_app(monkeypatch, [FakeScript()]) as app:
        ready_app_steps(app)
        assert app.group.stall_watch is False
    assert any("stall watch is off" in message for message in logs.messages())


def test_f9_the_watch_is_off_in_a_close_from_the_group_flag(monkeypatch):
    """F9: the group flag ends the cameras (no `close()`), and the close of the source takes 4 s: the watch does
    not end the camera in its close."""
    with capture_app(monkeypatch, [FakeScript(close_delay_s=4.0)], virtual=False) as app:
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        app.group.ipc.should_continue = False
        time.sleep(5.0)
        assert (app.status(camera_id)["failure"] or {}).get("code") != "stalled", app.status(camera_id)


class TimedCounter:
    """Stands in for `alive_count`: keeps the `time.perf_counter_ns()` of each add."""

    def __init__(self):
        self._value, self.adds = 0, []

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value
        self.adds.append(time.perf_counter_ns())


def test_the_count_comes_after_the_start_of_the_in_process_clock_at_the_attach():
    """unix-capture.md 4.10, ADR-4PPS item 10: the first pass in `waiting` after an open (also the open of a reopen,
    which runs inside a pass) sets `last_arrival` at the attach of the rings, after the count of its pass. The loop
    then adds one more to the counter before its read, so the watch counts from a point after the start of the clock
    of the in-process rule, and the head start of Q874 stays whole. A test of the loop alone: the watch is in
    `test_f2_*`."""
    from skellycam.core.camera.capture.camera_loop import CameraLoop
    from skellycam.core.camera_group.camera_status import CameraStatus

    class Read(Exception):
        pass

    loop = CameraLoop.__new__(CameraLoop)
    loop.status = CameraStatus()
    loop.status.alive_count = counter = TimedCounter()
    loop.ring_writer = None
    loop._attach_rings = lambda: setattr(loop, "ring_writer", object())

    def read():
        raise Read(loop.last_arrival, list(counter.adds))

    loop._read = read
    with pytest.raises(Read) as raised:
        loop._wait_pass()
    clock_start, adds = raised.value.args
    assert adds and adds[-1] >= clock_start, (clock_start, adds)


def test_fail_writes_the_failure_into_info_before_the_put():
    """unix-capture.md 4.10, ADR-4PPS item 11: the watch stops when `info` holds the failure, and the put on the queue
    of the setup failures can wait (its lock, the pipe). Thus `_fail` writes `info` first, then puts, then sets
    `dead` (the failure object before the state, section 12)."""
    from skellycam.core.camera.capture.camera_loop import CameraLoop
    from skellycam.core.camera.capture.source import CaptureFailure
    from skellycam.core.camera_group.camera_status import CameraStatus

    loop = CameraLoop.__new__(CameraLoop)
    loop.status = CameraStatus()
    loop.status.set_state("ready")
    loop._failure_lock, loop.failed, loop.started, loop.camera_id = threading.Lock(), False, True, "cam0"
    loop._publish_diagnostics = lambda: None
    seen = []
    loop.ipc = SimpleNamespace(report_setup_failure=lambda report: seen.append(
        (loop.status.info_dict().get("failure"), loop.status.state)))
    loop._fail(CaptureFailure("streaming", "no frame for 2 s", code="stalled"))
    assert len(seen) == 1
    failure, state = seen[0]
    assert failure is not None and failure["code"] == "stalled", seen
    assert state == "ready", "the state comes after the put"
    assert loop.status.state == "dead"


def test_f3_a_reopen_closes_the_source_in_starting(monkeypatch):
    """F3: a live change on the control thread can set `checking` while the reopen stops that thread. The
    reopen sets `starting` again after the stop, so the watch is off during the close of the source."""
    from skellycam.core.camera.capture.camera_loop import CameraLoop
    from skellycam.core.camera_group.camera_status import CameraStatus

    loop = CameraLoop.__new__(CameraLoop)
    loop.status = CameraStatus()
    loop.status.set_state("ready")
    seen = []
    loop._stop_control = lambda: loop.status.set_state("checking")  # the control thread ends a live change
    loop._close_rings = loop._add_replaced = lambda: None
    loop._start_up = lambda: None
    loop._retire = lambda role: None  # capture-timings 5.1: no timing reader on a hand-built loop
    loop.source = SimpleNamespace(close=lambda: seen.append(loop.status.state))
    loop.search = None  # no exposure search runs (camera-requests.md 1.3)
    from skellycam.core.camera.config.camera_config import CameraConfig

    loop._reopen(CameraConfig(camera_id="aaaa", camera_index=0, exposure_mode="MANUAL", exposure=-7))
    assert seen == ["starting"]


def watch_on_the_clock(monkeypatch, clock):
    """The watch thread of each new group on the virtual clock of the camera loops (Q892): each round waits 0.1 s of
    clock time (`_stop_watch.wait` in that thread), and the watch reads the clock time (`time.monotonic` of the group
    module, in that thread only). Gives the clock times of the reads of the watch."""
    import skellycam.core.camera_group.camera_group as group_module

    reads = []

    def in_watch():
        name = threading.current_thread().name
        return name.startswith("camera group ") and name.endswith(" watch")  # the thread of `CameraGroup`

    class ClockTime:
        def __getattr__(self, name):
            return getattr(time, name)

        def monotonic(self):
            if not in_watch():
                return time.monotonic()
            reads.append(clock.now_ns() / 1e9)
            return reads[-1]

    class ClockEvent(threading.Event):
        def wait(self, timeout=None):
            if timeout is None or not in_watch():
                return super().wait(timeout)
            clock.wait_until(clock.now_ns() + round(timeout * 1e9))
            return self.is_set()

    watch_workers = group_module.CameraGroup._watch_workers

    def watch(group):
        stop, group._stop_watch = group._stop_watch, ClockEvent()
        if stop.is_set():
            group._stop_watch.set()
        try:
            watch_workers(group)
        finally:
            clock.leave()

    monkeypatch.setattr(group_module, "time", ClockTime())
    monkeypatch.setattr(group_module.CameraGroup, "_watch_workers", watch)
    return reads


def test_t_unx_109_frames_that_stop_after_a_reopen_end_by_the_in_process_rule(monkeypatch):
    """T-UNX-109, Q892 [ADR-N2VE]: a real camera loop (a THREAD worker on the virtual clock), a fake camera whose
    frames stop at its first read in `waiting` after the open of a reopen, and the watch of the group on the same
    clock. That first pass in `waiting` attaches the new rings, starts the clock of the in-process rule there and then
    adds one to the counter, so the in-process rule (`no frame for 2 s`) ends the camera, not the watch (`no loop pass
    for 2.5 s`) (4.10). The attach takes 0.6 s of clock time here: without the count after it (4PPS item 10) the
    watch would count from before the attach and trip first."""
    stop = {}

    def stop_in_waiting(source, now_ns):  # the read of the camera loop thread
        app = stop.get("app")
        if app is None or "at" in stop or source.log.opens.value != 2:
            return
        if app.group.cameras.orchestrator.camera_statuses[source.camera_id].state == "waiting":
            stop["at"] = now_ns / 1e9
            source.stop_now()

    import skellycam.core.camera_group.camera_group as group_module

    trips = []  # a trip of the watch ends the process; with THREAD workers the loop can still write its failure later
    end_process = group_module.CameraGroup._end_process
    monkeypatch.setattr(group_module.CameraGroup, "_end_process",
                        staticmethod(lambda worker, status: (trips.append(1), end_process(worker, status))))
    modes = ((640, 480, 30, 1, "MJPG"), (1280, 720, 30, 1, "MJPG"))
    with capture_app(monkeypatch, [FakeScript(modes=modes)], on_read=stop_in_waiting) as app:
        reads = watch_on_the_clock(monkeypatch, app.clock)
        loop_module = importlib.import_module("skellycam.core.camera.capture.camera_loop")
        attach = loop_module.CameraLoop._attach_rings

        def slow_attach(loop):  # 4PPS item 10: an attach that takes clock time, so the count after it matters
            attach(loop)
            if loop.ring_writer is not None:
                app.clock.wait_until(app.clock.now_ns() + 600_000_000)

        monkeypatch.setattr(loop_module.CameraLoop, "_attach_rings", slow_attach)
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        stop["app"] = app
        response = app.apply([app.config(camera_id, width=1280, height=720)])
        assert response.status_code == 200, response.text
        app.wait_state(camera_id, "dead", "failed", timeout=30)
        failure = app.status(camera_id)["failure"]
    assert "at" in stop, "no read in `waiting` after the reopen"
    assert not trips, "the watch tripped: it decided, not the in-process rule"
    assert failure == {"camera_id": camera_id, "stage": "streaming", "reason": "no frame for 2 s",
                       "code": "stalled"}, failure
    rounds = [t for t in reads if stop["at"] <= t <= stop["at"] + 2.0]
    assert len(rounds) >= 15, f"the watch made {len(rounds)} rounds on the clock in the 2 s after the stop"
