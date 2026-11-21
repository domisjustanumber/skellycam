"""T-UNX-75 and the risk guard of the main-process stall watch (specs/unix-capture.md 4.10;
specs/windows-capture.md 9.5; ADR-AC5B items 1 and 11).

The shared loop adds one to `CameraStatus.alive_count` at each pass, and a wait of the loop in the recorder
adds one at least each 0.5 s. The watch thread of the group ends a camera whose counter did not change for
2 s in a watched state. These tests check that it ends a camera that cannot run a loop pass, and that it
ends no healthy camera: a `waiting` camera, the internal pause of a record start, a wait in the recorder, a
slow close of a reopen, the OpenCV fake (a pull source), and cameras under a load of the main process.

T-UNX-18 and T-UNX-45 (the in-process stall rule of W 9.5 with the V4L2 and AVFoundation fakes) wait for
steps 7a and 7b; T-CAP-36 checks that rule with the fake source.

Each test runs in real time and has the marker `capture_timing`.
"""

import asyncio
import threading
import time

import psutil
import pytest

from skellycam.tests.capture.capture_session import (
    CaptureApp, OpenCVFakeFactory, RingWatcher, Spies, StateWatcher, capture_app, ready_app_steps, wait_exit)
from skellycam.tests.capture.fake_source import FakeScript

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
    `suspend()`), so it runs no loop pass. The main process removes it from the gate and ends it 2.0 to
    2.5 s after its last loop pass: `dead`, `stalled`. The third camera has no gap longer than 2.5 s; the
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
        assert 2.0 <= took <= 2.5, f"dead {took:.3f} s after the last loop pass"
        assert app.status(stalled)["failure"] == {"camera_id": stalled, "stage": "streaming",
                                                  "reason": "no loop pass for 2 s", "code": "stalled"}
        assert app.state(second) == "ready" and app.state(third) == "ready"
        gap = ring.largest_gap_s()
        assert gap <= 2.5, f"the third camera had a gap of {gap:.2f} s"


def test_t_unx_75_waiting_pause_and_a_slow_reopen_trip_nothing(monkeypatch):
    """T-UNX-75: in real camera processes, two cameras are `waiting` for 4 s while the third opens; then the
    internal pause of a record start holds each camera for 4 s; then a size change reopens one camera whose
    close takes 3 s. No camera ends; no failure."""
    scripts = [FakeScript(modes=((640, 480, 30, 1, "MJPG"), (320, 240, 30, 1, "MJPG")), close_delay_s=3.0),
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
        response = app.apply([app.config(reopened, width=320, height=240)] +
                             [app.config(cid) for cid in app.factory.camera_ids[1:]])
        assert response.status_code == 200, response.text
        app.wait_state(reopened, "ready")
        assert app.status(reopened)["mode"]["width"] == 320
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


@pytest.mark.parametrize("workers", ["thread", "process"])
def test_the_watch_ends_no_healthy_camera_under_load(monkeypatch, workers):
    """The risk guard: two fake cameras stream for 12 s on the real clock while four threads of the main
    process run Python with no pause (they hold the GIL in turns with the watch thread and, with THREAD
    workers, with the camera loops: then a loop makes only about 5 passes each second). No camera ends;
    each camera keeps its loop passes, with no pause near the limit of 2 s."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript()], workers=workers, virtual=False) as app:
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
        assert not no_camera_ended(watchers), no_camera_ended(watchers)
        assert all(app.state(cid) == "ready" for cid in counts)
        passes = {cid: status_of(app, cid).alive_count.value - counts[cid] for cid in counts}
        assert all(value > 30 for value in passes.values()), passes
        gaps = {cid: round(watcher.max_gap, 3) for cid, watcher in alive.items()}
        assert all(gap < 1.0 for gap in gaps.values()), gaps
