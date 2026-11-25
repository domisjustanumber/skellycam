"""The main process: T-TIM-18 (the Python call), T-TIM-19 (the websocket message and the preview steps) and T-TIM-21
(the removal of `performance_data`) (specs/capture-timings.md 6.2 to 6.5).
"""

import asyncio
import importlib
import queue
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from skellycam.tests.capture.capture_session import capture_app, ready_app_steps
from skellycam.tests.capture.fake_source import FakeScript
from skellycam.tests.capture_timings.loop_harness import MS, VClock, slow, timings
from skellycam.tests.capture_timings.test_statistics import assert_known_ids

SERVER_MODULE = "skellycam.api.websocket.websocket_server"


def camera_summary(camera_id, seq=0, group_id="g1"):
    return timings().build_summary(source="camera", camera_group_id=group_id, camera_id=camera_id,
                                   clock="perf_counter_ns", seq=seq, window_end_ns=10**12, window_ns=10**9,
                                   step_ids=["camera_wait"], windows={})


def real_manager():
    import multiprocessing

    from skellycam.core.camera_group.camera_group_manager import CameraGroupManager
    from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
    return CameraGroupManager(global_kill_flag=multiprocessing.Value("b", False),
                              worker_registry=MagicMock(spec=WorkerRegistry))


def stub_group(group_id, timings_by_camera, closing=False):
    cameras = SimpleNamespace(orchestrator=SimpleNamespace(camera_statuses={}), removed_statuses={})
    return SimpleNamespace(id=group_id, camera_timings=timings_by_camera, _closing=closing, cameras=cameras)


def test_t_tim_18_the_python_call(monkeypatch):
    """T-TIM-18: the newest summary of each camera of each open group; a summary older than 3 s (a fake main clock) and
    the summaries of a closed group are left out; a switch to off gives `summaries` [] at once; a watch thread that
    replaces `camera_timings` 10,000 times while the call reads gives no error."""
    module = timings()
    now = [100 * 10**9]
    monkeypatch.setattr(module, "main_clock_ns", lambda: now[0])
    manager = real_manager()
    a, b, c = camera_summary("a1b2", 4), camera_summary("c3d4", 9), camera_summary("e5f6", 1, "g2")
    manager.camera_groups = {
        "g1": stub_group("g1", {"a1b2": (a, now[0] - 1 * 10**9), "c3d4": (b, now[0] - 3 * 10**9 - 1)}),
        "g2": stub_group("g2", {"e5f6": (c, now[0])}, closing=True),
    }
    assert manager.capture_timings()["summaries"] == []  # off
    manager.set_log_capture_times(True)
    manager.camera_groups["g1"].camera_timings = {"a1b2": (a, now[0] - 1 * 10**9), "c3d4": (b, now[0] - 3 * 10**9 - 1)}
    body = manager.capture_timings()
    assert body == {"version": 1, "log_capture_times": True, "summaries": [a]}
    manager.set_log_capture_times(False)
    assert manager.capture_timings() == {"version": 1, "log_capture_times": False, "summaries": []}
    assert manager.camera_groups["g1"].camera_timings == {}  # the kept summaries go at once

    manager.set_log_capture_times(True)
    group = manager.camera_groups["g1"]
    stop = threading.Event()

    def watch():
        for k in range(10_000):
            group.camera_timings = {f"cam{j}": (camera_summary(f"cam{j}", k), now[0]) for j in range(k % 5)}
        stop.set()

    thread = threading.Thread(target=watch)
    thread.start()
    while not stop.is_set():
        manager.capture_timings()
    thread.join(10)


def test_t_tim_18_the_watch_keeps_the_newest_summary(monkeypatch):
    """T-TIM-18 (the watch thread, 6.2): `_take_diagnostics` keeps the newest summary of each camera with its time of
    receipt, in a new dict at each change; a message with `timings` None drops the camera's summary."""
    from skellycam.core.camera_group.camera_group import CameraGroup
    from skellycam.core.camera_group.camera_status import CameraStatus
    from skellycam.core.ipc.pubsub.pubsub_topics import DiagnosticsMessage

    monkeypatch.setattr(timings(), "main_clock_ns", lambda: 7)
    messages = queue.Queue()
    group = SimpleNamespace(ipc=SimpleNamespace(diagnostics_subscription=messages), camera_diagnostics={},
                            camera_timings={}, cameras=SimpleNamespace(orchestrator=SimpleNamespace(
                                camera_statuses={"a1b2": CameraStatus(), "c3d4": CameraStatus()})))
    first, second = camera_summary("a1b2", 0), camera_summary("a1b2", 1)
    messages.put(DiagnosticsMessage(camera_id="a1b2", diagnostics={}, timings=first))
    messages.put(DiagnosticsMessage(camera_id="c3d4", diagnostics={}, timings=camera_summary("c3d4")))
    messages.put(DiagnosticsMessage(camera_id="a1b2", diagnostics={}, timings=second))
    CameraGroup._take_diagnostics(group)
    kept = group.camera_timings
    assert kept["a1b2"] == (second, 7) and set(kept) == {"a1b2", "c3d4"}
    messages.put(DiagnosticsMessage(camera_id="c3d4", diagnostics={}))
    CameraGroup._take_diagnostics(group)
    assert set(group.camera_timings) == {"a1b2"} and kept is not group.camera_timings and "c3d4" in kept


class FakeWebsocket:
    """The websocket of a connection: each send takes `send_ns` of virtual time."""

    def __init__(self, clock, send_ns):
        from starlette.websockets import WebSocketState
        self.clock, self.send_ns, self.sent = clock, send_ns, []
        self.client_state = WebSocketState.CONNECTED

    async def send_bytes(self, data):
        self.clock.advance(self.send_ns)
        self.sent.append(data)


def bare_server(preview_timings, websocket):
    """A `WebsocketServer` with only its send path (its `__init__` needs a FastAPI app)."""
    server_class = importlib.import_module(SERVER_MODULE).WebsocketServer
    server = server_class.__new__(server_class)
    server.websocket, server._send_lock, server._preview_timings = websocket, asyncio.Lock(), preview_timings
    return server


def test_t_tim_19_the_send_lock_wait_is_not_in_preview_send():
    """T-TIM-19 (interim relay): `preview_send` is the send after the send lock; `published_to_send` ends at the
    start of that send, for each camera of the group message."""
    module = timings()

    async def scenario():
        clock = VClock()
        preview = module.PreviewTimings(clock.now)
        preview.summaries(True, [])  # on: the window starts
        server = bare_server(preview, FakeWebsocket(clock, 130_000))
        preview.steps.pending["g1"] = [("a1b2", clock.now() - 1 * MS), ("c3d4", clock.now() - 2 * MS)]
        await server._send_lock.acquire()
        task = asyncio.create_task(server._send_bytes(b"group message", preview_group="g1"))
        await asyncio.sleep(0)
        clock.advance(50 * MS)  # the wait for the send lock
        server._send_lock.release()
        await task
        return preview.summaries(True, ["g1"])

    summaries = {s["camera_id"]: s for s in asyncio.run(scenario())}
    assert set(summaries) == {"a1b2", "c3d4", None}
    group = summaries[None]
    assert group["steps"]["preview_send"] == dict(kind="work", cadence="frame", where="main_process", n=1,
                                                  p50_ms=0.13, p95_ms=0.13, max_ms=0.13)
    assert summaries["a1b2"]["delays"]["published_to_send"]["max_ms"] == 51.0
    assert summaries["c3d4"]["delays"]["published_to_send"]["max_ms"] == 52.0
    for summary in summaries.values():
        assert summary["source"] == "preview" and summary["camera_group_id"] == "g1"
        assert_known_ids(summary)


def test_t_tim_19_the_interim_relay_measures_its_reads_and_its_group_message(monkeypatch):
    """T-TIM-19 (interim relay, real group): `get_latest_frontend_payloads(step_set=...)` measures `preview_ring_read`
    for each camera and `preview_pack` for the group; with the send, one `"preview"` summary for each camera and one
    with `camera_id` null."""
    module = timings()
    with capture_app(monkeypatch, [FakeScript(), FakeScript()]) as app:
        ready_app_steps(app)
        app.wait(lambda: len(app.group.read_latest_ring_frames() or {}) == 2, "a frame of each camera")
        group_id = app.group.id

        async def scenario():
            preview = module.PreviewTimings()
            preview.summaries(True, [])
            server = bare_server(preview, FakeWebsocket(VClock(), 0))
            payloads = app.manager.get_latest_frontend_payloads(if_newer_than={}, step_set=preview.steps)
            for camera_group_id, (_, _, payload) in payloads.items():
                await server._send_bytes(payload, preview_group=camera_group_id)
            return preview.summaries(True, [group_id])

        summaries = {s["camera_id"]: s for s in asyncio.run(scenario())}
    assert set(summaries) == set(app.factory.camera_ids) | {None}
    for camera_id in app.factory.camera_ids:
        camera = summaries[camera_id]
        assert camera["steps"]["preview_ring_read"]["n"] == 1 and camera["delays"]["published_to_send"]["n"] == 1
        assert camera["delays"]["published_to_send"]["max_ms"] >= 0
    group = summaries[None]
    assert set(group["steps"]) == {"preview_pack", "preview_send"}
    assert group["steps"]["preview_pack"]["n"] == 1 and group["steps"]["preview_send"]["n"] == 1


async def test_t_tim_19_the_per_camera_preview_sender():
    """T-TIM-19 (`PreviewRelay`): one `"preview"` summary for each camera with `preview_ring_read`, `preview_pack`,
    `preview_send` and `published_to_send`."""
    from skellycam.core.ipc.frame_ring import ReadResult
    from skellycam.tests.preview.preview_helpers import StubReader, frame_read, manager_with, preview

    module = timings()
    clock = VClock()
    measured = module.PreviewTimings(clock.now)
    measured.summaries(True, [])
    read = frame_read(ReadResult.OK, 0, arrival_ns=clock.now() - 4_000_001, payload=b"\xff\xd8\xff\xd9")
    reader = StubReader({0: [read]})
    reader.read = slow(clock, reader.read, 80_000)
    sent = []

    async def send_bytes(data):
        clock.advance(130_000)
        sent.append(data)

    async def send_json(data):
        pass

    relay = preview().PreviewRelay(manager_with({"a1b2": reader}), send_bytes, send_json, step_set=measured.steps)
    await relay._pass()
    assert len(sent) == 1
    summaries = measured.summaries(True, ["g1"])
    assert [s["camera_id"] for s in summaries] == ["a1b2"]
    steps, delays = summaries[0]["steps"], summaries[0]["delays"]
    assert set(steps) == {"preview_ring_read", "preview_pack", "preview_send"}
    assert (steps["preview_ring_read"]["max_ms"], steps["preview_send"]["max_ms"]) == (0.16, 0.13)
    assert delays["published_to_send"]["max_ms"] == 4.16
    assert_known_ids(summaries[0])


def receive_json_within(ws, timeout_s=10.0):
    """`ws.receive_json` with a bound: the client of the test has no timeout of its own."""
    result = []
    thread = threading.Thread(target=lambda: result.append(ws.receive_json(mode="text")), daemon=True)
    thread.start()
    thread.join(timeout_s)
    assert result, f"no message in {timeout_s} s"
    return result[0]


def test_t_tim_19_the_websocket_message(client, mock_camera_group_manager, monkeypatch):
    """T-TIM-19 (message): `capture_timings` messages with the fields of 6.1 at the patched interval; when off, the
    message of 6.4."""
    server = importlib.import_module(SERVER_MODULE)
    monkeypatch.setattr(server, "CAPTURE_TIMINGS_INTERVAL_S", 0.05)
    summary = camera_summary("a1b2", 3)
    mock_camera_group_manager.capture_timings.return_value = {"version": 1, "log_capture_times": True,
                                                              "summaries": [summary]}

    def next_timings(ws):
        for _ in range(50):
            data = receive_json_within(ws)
            if data.get("message_type") == "capture_timings":
                return data
        pytest.fail("no capture_timings message")

    with client.websocket_connect("/skellycam/websocket/connect") as ws:
        on = next_timings(ws)
        assert on == {"message_type": "capture_timings", "version": 1, "log_capture_times": True,
                      "summaries": [summary]}
        assert set(on["summaries"][0]) == {"source", "camera_group_id", "camera_id", "clock", "seq", "window_end_ns",
                                           "window_s", "steps", "delays"}
        mock_camera_group_manager.capture_timings.return_value = {"version": 1, "log_capture_times": False,
                                                                  "summaries": []}
        for _ in range(3):
            message = next_timings(ws)
            if not message["log_capture_times"]:
                break
        assert message == {"message_type": "capture_timings", "version": 1, "log_capture_times": False,
                           "summaries": []}


def test_t_tim_21_performance_data_goes():
    """T-TIM-21: `WebsocketMessageType` has `CAPTURE_TIMINGS` and no `PERFORMANCE_DATA`; the module `performance_data`
    does not import; the manager has no `get_latest_performance_data`; `test_websocket_internals.py` still imports and
    keeps `TestServerFramerateCalculator`."""
    from skellycam.api.websocket.websocket_message_types import WebsocketMessageType
    from skellycam.core.camera_group.camera_group_manager import CameraGroupManager

    assert WebsocketMessageType.CAPTURE_TIMINGS.value == "capture_timings"
    assert not hasattr(WebsocketMessageType, "PERFORMANCE_DATA")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("skellycam.api.websocket.performance_data")
    assert not hasattr(CameraGroupManager, "get_latest_performance_data")
    internals = importlib.import_module("skellycam.tests.test_websocket_internals")
    assert hasattr(internals, "TestServerFramerateCalculator")
    assert not hasattr(internals, "TestPerformanceDataHelpers") and not hasattr(internals, "TestExtractPerformanceData")


async def test_t_tim_19_a_timings_message_that_cannot_be_built_does_not_end_the_app(monkeypatch, caplog):
    """6.4: a `capture_timings()` that raises is logged one time; the state sender goes on and sends each state; the
    kill flag stays clear (a fault of the timings never ends the app, also during a take)."""
    import multiprocessing
    from unittest.mock import Mock

    from starlette.websockets import WebSocketState

    server_module = importlib.import_module(SERVER_MODULE)
    monkeypatch.setattr(server_module, "CAPTURE_TIMINGS_INTERVAL_S", 0.0)
    server = object.__new__(server_module.WebsocketServer)
    sent, calls = [], []

    def to_state_dict():
        calls.append(1)
        server._websocket_should_continue = len(calls) < 3
        return {"camera_groups": {"n": len(calls)}}

    def capture_timings():
        raise RuntimeError("test: a timings fault")

    async def send(message):
        sent.append(message)

    server.global_kill_flag = multiprocessing.Value("b", False)
    server._cgm = Mock(to_state_dict=to_state_dict, camera_groups={}, capture_timings=capture_timings)
    server._preview_timings = timings().PreviewTimings()
    server._websocket_should_continue, server.ws_tasks = True, []
    server.websocket = Mock(client_state=WebSocketState.CONNECTED)
    monkeypatch.setattr(server, "_send_msgspec_json", send)
    monkeypatch.setattr(server, "_send_text", send)
    await asyncio.wait_for(server._app_state_sender(), timeout=10)
    assert not server.global_kill_flag.value
    assert len(calls) == 3 and [m["state"]["camera_groups"]["n"] for m in sent] == [1, 2, 3]
    assert len([r for r in caplog.records if "capture timings message could not be built" in r.getMessage()]) == 1


def test_t_tim_19_the_keys_of_a_group_that_is_gone_go():
    """6.5: the preview keys and the `seq` of a group that is no longer open go at the next window."""
    module = timings()
    clock = VClock()
    preview = module.PreviewTimings(clock.now)
    preview.summaries(True, ["g1", "g2"])
    for group_id in ("g1", "g2"):
        preview.steps.add((group_id, None, "preview_send"), 1000)
    assert {s["camera_group_id"] for s in preview.summaries(True, ["g1", "g2"])} == {"g1", "g2"}
    preview.steps.add(("g2", None, "preview_send"), 1000)
    assert [s["camera_group_id"] for s in preview.summaries(True, ["g1"])] == ["g1"]
    assert {key[0] for key in preview.steps.samples} == {"g1"}
    assert {key[0] for key in preview._seq} == {"g1"}
