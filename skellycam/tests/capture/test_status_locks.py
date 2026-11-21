"""The JSON arrays of `CameraStatus` (unix-capture.md 4.10): a camera process that holds a lock of its status, slow
or killed, never blocks the main process for more than ARRAY_LOCK_WAIT_S for one call, and torn JSON of a read with
no lock never escapes a reader (review of the fix lane, `torn.py`)."""
import json
import multiprocessing
import time

import pytest

from skellycam.core.camera_group import camera_status
from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.tests.capture import status_children
from skellycam.tests.frame_ring import ring_children

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


@pytest.mark.capture_timing
@pytest.mark.parametrize("locked", [True, False], ids=["writes with the lock", "writes with no lock"])
def test_a_live_but_slow_holder_and_torn_json_never_raise(locked):
    """A live child holds the lock of `info` for 0.6 s, then writes `info` (with its lock, or with no lock). The
    first main-process read goes on with no lock after 0.5 s; the status does not stop waiting for good (the child
    is alive); no JSONDecodeError escapes over many reads; the later reads take the lock again."""
    status, go, stop = CameraStatus(), SPAWN.Event(), SPAWN.Event()
    child = start(status_children.hold_then_write, status, go, stop, 0.6, locked)
    status.owner = child
    try:
        assert go.wait(60), "the child holds the lock"
        started = time.monotonic()
        status.info_dict()
        assert time.monotonic() - started >= camera_status.ARRAY_LOCK_WAIT_S - 0.05
        assert not status.holder_dead and status.lock_warned
        assert read_for(status, 3.0) > 100
        assert not status.holder_dead and not status.lock_warned  # the lock came again
    finally:
        stop.set()
        child.join(30)


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
    server._cgm = Mock(to_state_dict=to_state_dict)
    server._websocket_should_continue, server.ws_tasks = True, []
    server.websocket = Mock(client_state=WebSocketState.CONNECTED)
    monkeypatch.setattr(server, "_send_msgspec_json", send)
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
    status.set_warning_items([{"kind": "start_failure"}], status.group_warnings)
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
        assert status.warning_items(status.group_warnings) == [{"kind": "start_failure"}]
        done = SPAWN.Event()
        writer = start(status_children.write_info, status, done)
        assert done.wait(60)
        writer.join(30)
        assert status.info_dict() == {"mode": {"width": 320}}
    finally:
        if holder.is_alive():
            holder.kill()
