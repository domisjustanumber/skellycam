"""The watch thread of `CameraGroup` (specs/windows-capture.md, section 6.6) and the ring readers of the
interim relay (5.8). F8 of the review of the 3a code (ADR-BM73).

- An error in one pass of the watch does not end the watch: it marks a later ended process and reads
  the queues of the camera processes.
- A ring reader is closed only on the event loop. The watch thread hands the close to the loop, so a
  close cannot come in the middle of a relay read. The interim relay of this branch also holds
  `_ring_lock` for its walk and each read, and copies each payload; a reader that reads with no lock
  on the loop (the preview relay of step 4a) needs the hand-off.

The group is made without `create`: no camera process and no shared memory. The stand-ins have only
the fields that the watch and the relay read.
"""

import asyncio
import logging
import queue
import threading
import time
from types import SimpleNamespace

import pytest

from skellycam.core.camera_group.camera_group import CameraGroup
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.ipc.frame_ring import FrameRingCreator, ReadResult
from skellycam.core.ipc.frame_ring.reader import FrameRead

WAIT_S = 10.0


def wait_for(predicate, what):
    deadline = time.monotonic() + WAIT_S
    while not predicate():
        assert time.monotonic() < deadline, f"timed out: {what}"
        time.sleep(0.005)


def bare_group(workers, statuses, loop=None):
    group = CameraGroup.__new__(CameraGroup)  # no camera process, no ring
    group.ipc = SimpleNamespace(group_id="g1", take_setup_failure=lambda: None,
                                recording_finished_subscription=queue.Queue(), diagnostics_subscription=queue.Queue())
    group.cameras = SimpleNamespace(camera_workers=workers, orchestrator=SimpleNamespace(camera_statuses=statuses))
    group.configs, group.rings, group.ring_infos, group.ring_readers, group.finished = {}, {}, {}, {}, []
    group.camera_diagnostics, group._passes, group.stall_watch, group._closing = {}, {}, True, False
    group._ring_lock, group._stop_watch, group._loop = threading.RLock(), threading.Event(), loop
    return group


def ended_worker(exitcode=3):
    return SimpleNamespace(worker=SimpleNamespace(exitcode=exitcode))


def status_in(state):
    status = CameraStatus()
    status.set_state(state)
    return status


class StandInRing(FrameRingCreator):
    """A ring with no shared memory (beartype checks the type). It counts its unlinks."""

    def __init__(self):  # no super().__init__: no shared memory
        self.unlinks = 0

    def close_and_unlink(self):
        self.unlinks += 1


class BrokenWorker:
    """A worker whose exit code cannot be read: each watch pass raises for this camera."""

    @property
    def worker(self):
        raise RuntimeError("test: the worker cannot be read")


def test_an_error_in_one_pass_does_not_stop_the_watch(caplog):
    """A camera whose worker raises and a queue read that raises once: the watch logs each error at
    ERROR with the camera ID, marks the ended process of the other camera `dead`, and still reads a
    result message that comes after the errors."""
    statuses = {"aaaa": status_in("ready"), "bbbb": status_in("ready")}
    group = bare_group({"aaaa": BrokenWorker(), "bbbb": ended_worker()}, statuses)
    reads = []

    def take_setup_failure():
        reads.append(1)
        if len(reads) == 1:
            raise OSError("test: the queue read fails once")
    group.ipc.take_setup_failure = take_setup_failure
    watch = threading.Thread(target=group._watch_workers, daemon=True)
    with caplog.at_level(logging.ERROR):
        watch.start()
        try:
            wait_for(lambda: statuses["bbbb"].state == "dead", "the ended process is marked")
            wait_for(lambda: len(reads) >= 3, "later passes read the queues")
            from skellycam.core.ipc.pubsub.pubsub_topics import RecordingFinishedMessage

            message = RecordingFinishedMessage(camera_id="aaaa")  # the result message of a camera writer (step 5a)
            group.ipc.recording_finished_subscription.put(message)
            wait_for(lambda: message in group.finished, "the result message is read")
            assert watch.is_alive(), "the watch thread ended"
        finally:
            group._stop_watch.set()
            watch.join(5)
    assert statuses["aaaa"].state == "ready"
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any("camera aaaa" in text for text in errors), errors
    assert any("camera queues" in text for text in errors), errors


class SlowReader:
    """A ring reader whose read takes time. It records a close that comes during a read."""

    def __init__(self):
        self.inside, self.closed, self.closed_inside, self.close_thread = threading.Event(), False, False, None

    def read_newest(self):
        self.inside.set()
        time.sleep(0.3)  # the watch thread sees the ended process during this read
        self.closed_inside = self.closed
        self.inside.clear()
        return FrameRead(ReadResult.OK, 7, 1_000, 0, 0, 7, 0, 0, 3, b"jpg")

    def close(self):
        self.closed, self.close_thread = True, threading.get_ident()


def test_a_ring_reader_is_closed_only_on_the_event_loop():
    """The relay reads a ring on the event loop while the process of that camera ends. The watch thread
    sees the end during the read. The reader is not closed during the read; the relay message is
    complete; then the loop closes the reader and unlinks the ring, one time."""
    reader, ring = SlowReader(), StandInRing()
    worker = SimpleNamespace(worker=SimpleNamespace(exitcode=None))
    statuses = {"aaaa": status_in("ready")}

    async def scenario():
        group = bare_group({"aaaa": worker}, statuses, loop=asyncio.get_running_loop())
        group.rings["aaaa"], group.ring_readers["aaaa"] = ring, reader
        group.ring_infos["aaaa"] = SimpleNamespace(camera_index=0, mode=SimpleNamespace(width=4, height=4))
        watch = threading.Thread(target=group._watch_workers, daemon=True)
        watch.start()
        try:
            def end_during_read():
                reader.inside.wait(WAIT_S)
                worker.worker.exitcode = 3  # the process ends while the relay reads
            threading.Thread(target=end_during_read, daemon=True).start()
            payload = group.get_latest_ring_payload()  # on the event loop, as the websocket relay
            assert payload is not None and payload[0] == 7
            assert not reader.closed_inside, "the reader was closed during a read"
            for _ in range(200):
                await asyncio.sleep(0.01)
                if ring.unlinks:
                    break
            assert reader.closed and ring.unlinks == 1
            assert reader.close_thread == threading.get_ident(), "the reader was not closed on the event loop"
            assert "aaaa" not in group.ring_readers and "aaaa" not in group.rings
            await asyncio.sleep(0.3)  # later passes find no ring to close
            assert ring.unlinks == 1
        finally:
            group._stop_watch.set()
            watch.join(5)

    asyncio.run(scenario())


def test_a_late_close_leaves_the_ring_of_a_restart_open():
    """The loop runs the close after a restart gave the camera a new ring: the new ring stays open."""
    old_ring, new_ring = StandInRing(), StandInRing()
    group = bare_group({}, {})
    group.rings["aaaa"] = new_ring
    group._close_ended_ring("aaaa", old_ring)
    assert group.rings["aaaa"] is new_ring and new_ring.unlinks == 0


class UnendingWorker:
    """A camera process that `terminate` and `kill` do not end, for example one stuck in the kernel."""

    def __init__(self):
        self.calls = []
        self.worker = SimpleNamespace(terminate=lambda: self.calls.append("terminate"),
                                      kill=lambda: self.calls.append("kill"), exitcode=None)

    def join(self, timeout=None):
        self.calls.append("join")

    def is_alive(self):
        return True


def test_a_stuck_camera_whose_process_does_not_end_is_killed_and_reported(monkeypatch):
    """Review fault 6 [recorder.md 5.3 item 6, 8.1 step 4, review B2]: after `terminate` and the join, a process
    that still runs gets `kill`. When it still runs after that, the main process reports it, so that the
    take level does not touch its files."""
    import skellycam.core.camera_group.camera_group as module

    monkeypatch.setattr(module, "BOUNDED_JOIN_S", 0.01)
    worker = UnendingWorker()
    status = status_in("recording")
    group = bare_group({"cam0": worker}, {"cam0": status})
    assert group._end_stuck_camera("cam0") is False
    assert worker.calls == ["terminate", "join", "kill", "join"]
    assert status.state == "failed" and status.info_dict()["failure"]["reason"] == "disk stall"
    assert status.info_dict()["failure"]["code"] == "disk-stall"


@pytest.mark.parametrize("case", ["cameras starting", "every camera failed", "every camera died in a take"])
def test_the_app_state_says_a_recording_runs_while_a_take_runs(case):
    """NEW-A and the second review, R3: the app state has `recording_in_progress` true while a take runs, also
    when every camera died during it (the UI then shows Stop, not a Start that gets 409), and false with
    no take, also while the cameras start or when each camera failed."""
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator

    state = {"cameras starting": "starting", "every camera failed": "failed"}.get(case, "dead")
    statuses = {"cam0": status_in(state), "cam1": status_in(state)}
    group = bare_group({}, statuses)
    group.cameras.orchestrator = CameraOrchestrator.from_statuses(statuses)
    group.ipc.running = True
    group.take = object() if case == "every camera died in a take" else None
    assert group.to_state().recording_in_progress is (case == "every camera died in a take")
