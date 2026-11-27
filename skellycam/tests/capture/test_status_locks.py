"""The JSON arrays of `CameraStatus` (unix-capture.md 4.10): a camera process that holds a lock of its status, slow
or killed, never blocks the main process for more than ARRAY_LOCK_WAIT_S for one call, and torn JSON of a read with
no lock never escapes a reader (review of the fix lane, `torn.py`)."""
import asyncio
import json
import multiprocessing
import time

import pytest

from skellycam.core.camera_group import camera_status
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.capture_timings import PreviewTimings, TimingControl
from skellycam.tests.capture import status_children
from skellycam.tests.frame_ring import ring_children
from skellycam.tests.pace import one_run

SPAWN = multiprocessing.get_context("spawn")


def start(target, *args):
    process = SPAWN.Process(target=target, args=args, daemon=True)
    process.start()
    return process


def read_for(status, seconds):
    """Read the status for `seconds`; return the number of reads (a raise fails the test)."""
    reads, end = 0, time.monotonic() + seconds
    while time.monotonic() < end:
        status.info_dict()
        status.serialize()
        reads += 1
    return reads


def _slow_holder_run(monkeypatch, locked):
    """One run of the slow-holder test, as data: a live child holds the lock of `info` for 1.5 s, then writes `info`
    (with its lock, or with no lock); the main process reads it (Q917 [ADR-N7ZR])."""
    from unittest.mock import Mock

    log = Mock()
    monkeypatch.setattr(camera_status, "logger", log)
    status, go, stop = CameraStatus(), SPAWN.Event(), SPAWN.Event()
    child = start(status_children.hold_then_write, status, go, stop, 1.5, locked)
    status.owner = child
    try:
        assert go.wait(60), "the child holds the lock"
        lock = status.info.get_lock()
        held_at_start = not lock.acquire(False)  # a probe with no wait: the child still holds the lock
        if not held_at_start:
            lock.release()
        started = time.monotonic()
        status.info_dict()
        first_wait = time.monotonic() - started
        started = time.monotonic()
        status.info_dict()
        second_wait = time.monotonic() - started
        dead_in_stretch, in_stretch = status.holder_dead, "info" in status.no_lock
        reads = read_for(status, 3.0)  # a JSONDecodeError that escapes fails the test here
        return dict(held_at_start=held_at_start, first_wait=first_wait, second_wait=second_wait,
                    dead_in_stretch=dead_in_stretch,
                    in_stretch=in_stretch, reads=reads, dead_at_end=status.holder_dead,
                    stretch_at_end="info" in status.no_lock, errors=log.error.call_count)
    finally:
        stop.set()
        child.join(30)


@pytest.mark.capture_timing
@pytest.mark.parametrize("locked", [True, False], ids=["writes with the lock", "writes with no lock"])
def test_a_live_but_slow_holder_and_torn_json_never_raise(monkeypatch, locked):
    """A live child holds the lock of `info` for 1.5 s, then writes `info` (with its lock, or with no lock). The
    status does not stop the tries for good (the child is alive); no JSONDecodeError escapes over many reads; the
    later reads take the lock again. The run must exercise a stretch: the child holds the lock at the first read,
    and one stretch with no lock begins (at least one error line). The checks that depend on the pace (the first
    read waits 0.5 s and logs one line, the next reads of that stretch do not wait (F4 of the review), the count of
    reads) are `test_a_live_but_slow_holder_waits_once_and_logs_one_line` (Q917 [ADR-N7ZR], the reading of the lane
    in [ADR-GV50])."""
    run = one_run(f"slow holder {locked}", lambda: _slow_holder_run(monkeypatch, locked))
    # the run exercised a stretch: the child held the lock at the first read, and one stretch with no lock began
    assert run["held_at_start"], "the child did not hold the lock at the first read"
    assert run["errors"] >= 1, "no stretch with no lock began"
    assert not run["dead_in_stretch"] and not run["dead_at_end"]
    assert not run["stretch_at_end"]  # the lock came again


@pytest.mark.pace  # Q917: the waits and the counts need the main process to read within the hold of 1.5 s
@pytest.mark.capture_timing
@pytest.mark.parametrize("locked", [True, False], ids=["writes with the lock", "writes with no lock"])
def test_a_live_but_slow_holder_waits_once_and_logs_one_line(monkeypatch, locked):
    """The `pace` half of the slow-holder test (Q917 [ADR-N7ZR]): the first main-process read goes on with no lock
    after 0.5 s and logs one line; the next read of that stretch does not wait (F4 of the review); more than 100 reads
    in 3 s. CI runs: WSL on 2 cores, 1 of 20 ("info" not in `no_lock` after the second read, evidence item 13 of
    ADR-4CAF); macOS arm64, two error lines (CI run 45925313532)."""
    run = one_run(f"slow holder {locked}", lambda: _slow_holder_run(monkeypatch, locked))
    assert run["first_wait"] >= camera_status.ARRAY_LOCK_WAIT_S - 0.05
    assert run["second_wait"] < 0.2, "a second wait in one stretch with no lock"
    assert run["in_stretch"]
    assert run["reads"] > 100
    assert run["errors"] == 1


def test_a_torn_info_gives_the_last_good_value():
    """A half-written `info` (a read with no lock): the reader gives the last good value of this process, or {}."""
    status = CameraStatus()
    status.info.get_obj().value = b'{"mode": {"wid'
    assert status.info_dict() == {} and status.warning_items() == []
    status.update_info(mode={"width": 640})
    assert status.info_dict() == {"mode": {"width": 640}}
    status.info.get_obj().value = b'{"mode": {"wid'
    assert status.info_dict() == {"mode": {"width": 640}}
    assert status.serialize()["mode"] == {"width": 640}


async def test_the_app_state_sender_does_not_set_the_kill_flag_on_torn_json(monkeypatch):
    """A torn `info` in the state that the websocket sends: the sender sends the state, and the kill flag (which ends
    the whole app, also during a take) stays clear."""
    from unittest.mock import Mock

    from starlette.websockets import WebSocketState

    from skellycam.api.websocket import websocket_server as server_module

    status = CameraStatus()
    status.update_info(mode={"width": 640})
    status.info.get_obj().value = b'{"mode": {"wid'
    server = object.__new__(server_module.WebsocketServer)
    sent, calls = [], []

    def to_state_dict():
        calls.append(1)
        server._websocket_should_continue = len(calls) < 2
        return {"camera_groups": {"g": {"cameras": {"c": {"status": status.serialize()}}}}}

    async def send(message):
        sent.append(message)

    server.global_kill_flag = multiprocessing.Value("b", False)
    server._cgm = Mock(to_state_dict=to_state_dict, camera_groups={}, capture_timings=capture_timings_off)
    server._preview_timings = PreviewTimings()  # the capture timings message after each state check
    server._websocket_should_continue, server.ws_tasks = True, []
    server.websocket = Mock(client_state=WebSocketState.CONNECTED)
    monkeypatch.setattr(server, "_send_msgspec_json", send)
    monkeypatch.setattr(server, "_send_text", send)  # the capture timings message (capture-timings.md 6.4)
    await server._app_state_sender()
    assert not server.global_kill_flag.value
    assert sent and sent[0]["state"]["camera_groups"]["g"]["cameras"]["c"]["status"]["mode"] == {"width": 640}


@pytest.mark.capture_timing
def test_a_dead_holder_then_a_restart_with_new_arrays():
    """A child takes the lock of `info` and is killed. One read waits 0.5 s, sees that the process ended, and then
    no call waits for that status. The failure that the main process writes stays in the main process (the shared
    array keeps its content). `reset_for_start` (a restart with a new process) gives new arrays, keeps the warning
    items of the camera and the group, and a new process writes the new `info` with its lock."""
    status, held = CameraStatus(), SPAWN.Event()
    status.update_info(mode={"width": 640})
    status.set_warning_items([{"kind": "start_failure"}], "group_warnings")
    holder = start(ring_children.hold_lock_forever, status.info, held)
    status.owner = holder
    try:
        assert held.wait(60), "the child holds the lock"
        holder.kill()
        holder.join(30)
        assert status.serialize()["mode"] == {"width": 640}
        assert status.holder_dead
        started = time.monotonic()
        status.update_info(failure={"code": "process-ended"})
        assert status.info_dict()["failure"] == {"code": "process-ended"}
        assert time.monotonic() - started < 0.4  # no second wait
        assert json.loads(status.info.get_obj().value) == {"mode": {"width": 640}}
        old = status.info
        status.reset_for_start()
        assert status.info is not old and not status.holder_dead and status.info_dict() == {}
        assert status.warning_items("group_warnings") == [{"kind": "start_failure"}]
        done = SPAWN.Event()
        writer = start(status_children.write_info, status, done)
        assert done.wait(60)
        writer.join(30)
        assert status.info_dict() == {"mode": {"width": 320}}
    finally:
        if holder.is_alive():
            holder.kill()


@pytest.mark.capture_timing
def test_a_killed_reader_of_the_heartbeat_does_not_stop_the_heartbeat():
    """unix-capture.md 4.10: the heartbeat value, the kill flag and the group flags have no lock. A camera process
    killed while it reads the heartbeat (each loop pass reads it) leaves no lock, and the heartbeat thread beats on."""
    from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
    from skellycam.core.ipc.process_management.managed_worker import WorkerMode
    from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry

    flags = [f.default_factory() for f in __import__("dataclasses").fields(CameraGroupIPC)
             if f.name in ("should_pause", "shutdown_camera_group_flag")]
    assert len(flags) == 2 and not [flag for flag in flags if hasattr(flag, "get_lock")]
    registry = WorkerRegistry(global_kill_flag=multiprocessing.Value("b", False, lock=False),
                              worker_mode=WorkerMode.THREAD)
    heartbeat = registry.heartbeat_timestamp
    assert not hasattr(heartbeat, "get_lock")
    reading = SPAWN.Event()
    reader = start(status_children.read_heartbeat_forever, heartbeat, reading)
    try:
        assert reading.wait(60)
        time.sleep(0.2)
        reader.kill()
        reader.join(30)
        registry._start_heartbeat_writer()
        before = heartbeat.value
        deadline = time.monotonic() + 5
        while heartbeat.value == before and time.monotonic() < deadline:
            time.sleep(0.05)
        assert heartbeat.value > before, "the heartbeat thread stopped"
    finally:
        registry._stop_threads()
        if reader.is_alive():
            reader.kill()


def kill_holder(array):
    """A child that takes the lock of `array` and is killed (the experiments of the second review)."""
    held = SPAWN.Event()
    holder = start(ring_children.hold_lock_forever, array, held)
    assert held.wait(60), "the child holds the lock"
    holder.kill()
    holder.join(30)
    return holder


@pytest.mark.capture_timing
def test_experiment_1_a_restart_right_after_a_dead_holder_of_camera_warnings_gives_new_arrays():
    """F2 of the second review: the old process was killed while it held the lock of `camera_warnings`, and no read
    found that before `reset_for_start`. The restart gives new arrays (ARRAYS); each later `serialize` of the new
    process takes no wait."""
    from types import SimpleNamespace

    status = CameraStatus()
    status.set_warning_items([{"kind": "no_manual_exposure"}], "camera_warnings")
    olds = [getattr(status, name) for name in camera_status.ARRAYS]
    status.owner = kill_holder(status.camera_warnings)
    started = time.monotonic()
    status.reset_for_start()
    assert time.monotonic() - started < 0.4
    assert all(getattr(status, name) is not old for name, old in zip(camera_status.ARRAYS, olds))
    assert status.warning_items("camera_warnings") == [{"kind": "no_manual_exposure"}]
    status.owner = SimpleNamespace(is_alive=lambda: True, name="new process")
    for _ in range(3):
        started = time.monotonic()
        status.serialize()
        assert time.monotonic() - started < 0.2


@pytest.mark.capture_timing
def test_experiment_2_a_restart_right_after_a_dead_holder_of_info_lets_the_main_process_write():
    """F2: the old process was killed while it held the lock of `info`. After the restart, a main-process write
    (`writer_failure=None` of a record start) goes into the shared array, not into the kept-back fields, so the
    refusal that the new camera writes later is seen."""
    from types import SimpleNamespace

    status = CameraStatus()
    old = status.info
    status.owner = kill_holder(status.info)
    status.reset_for_start()
    assert status.info is not old
    status.owner = SimpleNamespace(is_alive=lambda: True, name="new process")
    status.update_info(writer_failure=None)
    assert status.pending_info == {} and json.loads(status.info.get_obj().value) == {"writer_failure": None}
    status.info.get_obj().value = b'{"writer_failure": "camera c1: the take writer did not start"}'
    assert status.info_dict()["writer_failure"] == "camera c1: the take writer did not start"


def test_experiment_3_a_swap_of_the_arrays_during_a_read_raises_nothing():
    """F3: the swap of `reset_for_start` comes while a read holds the lock of the old array. The read releases the
    lock that it took (not the lock of the new array), reads the array by name, and raises nothing; the old lock is
    free and the new lock was never taken."""
    import contextlib

    status = CameraStatus()
    status.set_warning_items([{"kind": "add_light"}], "camera_warnings")
    old = status.camera_warnings
    take_lock = status._array_lock

    @contextlib.contextmanager
    def swap_inside(name):
        with take_lock(name) as locked:
            assert locked
            setattr(status, name, multiprocessing.Array("c", camera_status.INFO_SIZE))  # the swap, inside the window
            yield locked

    status._array_lock = swap_inside
    assert status.warning_items("camera_warnings") == []  # the new array, read by name
    del status._array_lock
    assert old.get_lock().acquire(timeout=0) and status.camera_warnings.get_lock().acquire(timeout=0)


@pytest.mark.capture_timing
def test_experiment_4_a_dead_holder_of_the_last_frame_blocks_no_frame_decision():
    """F1: a camera killed while it held the lock of the last frame of the take. The decision of each frame
    (`should_record_frame_number`, in each camera process) waits at most FRAME_READ_WAIT_S one time, then reads
    with no lock and no wait until the lock comes again."""
    from skellycam.core.camera_group.camera_orchestrator import FRAME_READ_WAIT_S, CameraOrchestrator

    orchestrator = CameraOrchestrator.from_statuses({})
    kill_holder(orchestrator.last_recording_frame_number)
    orchestrator.first_recording_frame_number.value = 3
    started = time.monotonic()
    assert orchestrator.should_record_frame_number(5) == (True, False)
    assert time.monotonic() - started < FRAME_READ_WAIT_S + 0.5
    started = time.monotonic()
    orchestrator.last_frame = 5
    assert orchestrator.should_record_frame_number(5) == (False, True)
    assert orchestrator.take_frame_count() == 2
    assert time.monotonic() - started < 0.2


def test_t_unx_93_a_frame_decision_outside_a_take_never_touches_the_last_frame_lock():
    """T-UNX-93, unix-capture.md 4.10 [NYT6]: with no take (first is -1), a frame decision reads no last frame and takes no
    lock. A holder that keeps the lock (a camera killed inside it) makes no wait, and no stretch with no lock starts."""
    import threading

    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator

    orchestrator = CameraOrchestrator.from_statuses({})
    held, release = threading.Event(), threading.Event()

    def hold():
        with orchestrator.last_recording_frame_number.get_lock():
            held.set()
            release.wait(10)

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    try:
        assert held.wait(5)
        started = time.monotonic()
        assert orchestrator.should_record_frame_number(5) == (False, False)
        assert time.monotonic() - started < 0.2
        assert not orchestrator.frame_lock_lost
    finally:
        release.set()
        holder.join(5)


async def test_a_state_read_that_raises_once_does_not_end_the_app_state_sender(monkeypatch):
    """F3 of the second review: a state read that raises (for example during the swap of the arrays) is logged; the
    sender goes on, and the next tick sends a state. The kill flag stays clear."""
    from unittest.mock import Mock

    from starlette.websockets import WebSocketState

    from skellycam.api.websocket import websocket_server as server_module

    server = object.__new__(server_module.WebsocketServer)
    sent, calls = [], []

    def to_state_dict():
        calls.append(1)
        if len(calls) == 1:
            raise StopIteration("test: a read during a swap")
        server._websocket_should_continue = False
        return {"camera_groups": {}}

    async def send(message):
        sent.append(message)

    monkeypatch.setattr(server_module, "logger", Mock())
    server.global_kill_flag = multiprocessing.Value("b", False)
    server._cgm = Mock(to_state_dict=to_state_dict, camera_groups={}, capture_timings=capture_timings_off)
    server._preview_timings = PreviewTimings()  # the capture timings message after each state check
    server._websocket_should_continue, server.ws_tasks = True, []
    server.websocket = Mock(client_state=WebSocketState.CONNECTED)
    monkeypatch.setattr(server, "_send_msgspec_json", send)
    monkeypatch.setattr(server, "_send_text", send)  # the capture timings message (capture-timings.md 6.4)
    await asyncio.wait_for(server._app_state_sender(), timeout=10)
    assert not server.global_kill_flag.value
    assert len(calls) == 2 and sent and sent[0]["state"] == {"camera_groups": {}}


def capture_timings_off():
    return {"version": 1, "log_capture_times": False, "summaries": []}


def test_the_camera_end_with_no_take_level_waits_at_most_its_bound_for_the_last_frame_lock():
    """F1: a camera that ends while the group stops (no take level follows) sets the last frame under its lock. With
    a holder that keeps the lock, it waits at most FRAME_LOCK_WAIT_S, then ends its part of the take alone with a
    clear reason (`abandon`, and a result message with the error)."""
    import threading
    from types import SimpleNamespace
    from unittest.mock import Mock

    from skellycam.core.camera.capture.camera_loop import CameraLoop
    from skellycam.core.camera_group.camera_orchestrator import FRAME_LOCK_WAIT_S, CameraOrchestrator
    from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes

    orchestrator = CameraOrchestrator.from_statuses({})
    orchestrator.first_recording_frame_number.value = 3
    writer, topic = Mock(), Mock()
    writer.abandon.return_value = None
    topics = {TopicTypes.RECORDING_FINISHED: topic}
    loop = SimpleNamespace(take_writer=writer, orchestrator=orchestrator, camera_id="c1", gate_count=10,
                           ipc=SimpleNamespace(should_continue=False, pubsub=SimpleNamespace(topics=topics)),
                           status=SimpleNamespace(recording_in_progress=SimpleNamespace(value=True)),
                           timing=TimingControl(time.perf_counter_ns), _retire=lambda role: None)
    held, release = threading.Event(), threading.Event()

    def hold():
        with orchestrator.last_recording_frame_number.get_lock():
            held.set()
            release.wait(10)

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    try:
        assert held.wait(5)
        started = time.monotonic()
        CameraLoop._end_take(loop)
        assert time.monotonic() - started < FRAME_LOCK_WAIT_S + 0.5
    finally:
        release.set()
        holder.join(5)
    writer.abandon.assert_called_once()
    writer.end.assert_not_called()
    message = topic.publish.call_args.args[0]
    assert message.error == f"camera c1: no lock of the last frame of the take in {FRAME_LOCK_WAIT_S:g} s"
    assert orchestrator.last_frame == -1 and loop.status.recording_in_progress.value is False
