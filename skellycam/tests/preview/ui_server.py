"""The server of the step 4b UI tests (specs/preview-4b.md 7.2). No camera. Never port 53117.

Run from the repository root: `uv run python -m skellycam.tests.preview.ui_server [options]`.

It calls `configure_logging` as `skellycam/__main__.py` does, and runs uvicorn with the product
websocket router (`SKELLYCAM_ROUTERS`), compression off [A9], and a manager patched in at each import
site of `get_or_create_camera_group_manager`, as the `app` fixture of `skellycam/tests/conftest.py`
does. It binds 127.0.0.1 on a port that the system chooses.

Modes (`--mode`):

- `fake` (the default): the fake manager of `preview_helpers.py` with a scripted `app_state`, fake
  rings in this process, and the writers in a second process with the barcode JPEGs of
  `barcode_jpegs.py`. `--cameras` is a JSON list of `{"id", "number", "index", "name"}`: `number`
  (1 to 8) is the camera number of the barcode, `index` and `name` go into `configs` of `app_state`.
- `capture`: a real `CameraGroupManager` and `CameraGroup` with THREAD workers, the real clock and
  the fake sources of `skellycam/tests/capture/`, as `capture_app` of `capture_session.py` makes them.
  Each frame of a fake source is a barcode JPEG of its camera (number = list position + 1).
  `--cameras` is a JSON list of `{"name", "script": {FakeScript fields}}`. Its `app_state` is the real
  `to_state_dict`.

Protocol: each line that the server writes for the test starts with `@ui_server ` and holds one JSON
object. Other lines of stdout and stderr are logs. The first such line is
`{"event": "started", "port": <port>, "cameras": [{"id", "number", "name"}]}`. Then the server reads
one JSON command for each line of stdin, `{"cmd": <name>, ...}`, and writes one reply line for it,
`{"ok": true, ...}` or `{"ok": false, "error": <text>}`. At the end it writes `{"event": "stopped"}`.
The commands are in `COMMANDS` (common) and in the `handle` method of each mode.
"""

import argparse
import asyncio
import contextlib
import faulthandler
import http.client
import itertools
import json
import multiprocessing
import os
import queue
import socket
import sys
import tempfile
import threading
import time
import traceback
import weakref
from pathlib import Path

PREFIX = "@ui_server "
HOST = "127.0.0.1"
PRODUCT_PORT = 53117
WRITER_TIMEOUT_S = 180.0  # the writer makes 60 JPEGs for each new camera; 1080p takes seconds
RING_INDEX_BASE = 70  # the camera_index of a fake ring (the ring name); away from the other tests
STATES = ("starting", "waiting", "failed", "checking", "too_slow", "ready", "recording", "dead")

_print_lock = threading.Lock()


def emit(obj):
    with _print_lock:
        sys.stdout.write(PREFIX + json.dumps(obj) + "\n")
        sys.stdout.flush()


def now_ms():
    """Wall time in ms: the test side compares it with `Date.now()` on the same machine."""
    return time.time() * 1000.0


def free_socket():
    """A socket bound to 127.0.0.1 on a port that the system chooses, never 53117."""
    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((HOST, 0))
        if sock.getsockname()[1] != PRODUCT_PORT:
            return sock
        sock.close()


# ---------------------------------------------------------------------------
# The writers of the fake rings: a second process (6.2, as the script of ADR-HDC9)
# ---------------------------------------------------------------------------

def writer_main(commands, replies, width, height, fps, target_bytes):
    """Paced writes to each active ring, all rings at one frame number at a time (6.2). Commands are
    tuples; each gets one reply on `replies`."""
    from skellycam.core.ipc.frame_ring import FrameFlag, FrameRingWriter, PixelFormat, slot_capacity
    from skellycam.tests.preview.barcode_jpegs import make_jpegs

    oversize_payload = bytes(slot_capacity(PixelFormat.JPEG, width, height) + 1)
    jpegs = {}
    cams = {}  # camera id -> state
    written = {}
    period = 1.0 / fps
    next_t = time.perf_counter()
    while True:
        while True:
            try:
                cmd = commands.get_nowait()
            except queue.Empty:
                break
            op, args = cmd[0], cmd[1:]
            if op == "quit":
                for cam in cams.values():
                    cam["writer"].close()
                replies.put(("ok", None))
                return
            if op == "add":
                camera_id, ring_name, number, active = args
                if number not in jpegs:
                    jpegs[number] = make_jpegs(number, width, height, target_bytes)
                cams[camera_id] = dict(writer=FrameRingWriter.attach(ring_name), number=number, k=0, active=active,
                                       flagged=0, oversize=0, skip=0)
                written.setdefault(camera_id, 0)
            elif op == "remove":
                cams.pop(args[0])["writer"].close()
            elif op == "restart":
                cam = cams[args[0]]
                cam["writer"].close()
                cam["writer"] = FrameRingWriter.attach(args[1])
                cam["k"] = 0
            elif op == "start_all":
                for cam in cams.values():
                    cam["active"], cam["k"] = True, 0
                next_t = time.perf_counter()
            elif op == "active":
                cams[args[0]]["active"] = args[1]
            elif op in ("flagged", "oversize", "skip"):
                cams[args[0]][op] += args[1]
            elif op == "fps":
                period = 1.0 / args[0]
            elif op == "written":
                replies.put(("ok", dict(written)))
                continue
            replies.put(("ok", None))
        arrival = time.perf_counter_ns()
        for camera_id, cam in cams.items():
            if not cam["active"]:
                continue
            writer = cam["writer"]
            if cam["skip"]:
                cam["skip"] -= 1  # a ring skip: this frame number is skipped, the next one follows at once
                writer.write(None, frame_number=cam["k"], arrival_ns=arrival, sample_ns=arrival,
                             source_frame_number=cam["k"], flags=0, rotation_cw_deg=0, newer_frame_waiting=True)
                cam["k"] += 1
            k, flags = cam["k"], 0
            payload = jpegs[cam["number"]][k % len(jpegs[cam["number"]])]
            if cam["oversize"]:
                cam["oversize"] -= 1
                payload = oversize_payload  # larger than the slot: the ring sets OVERSIZE and keeps no payload
            elif cam["flagged"]:
                cam["flagged"] -= 1
                flags = FrameFlag.NO_SOI_EOI
            writer.write(payload, frame_number=k, arrival_ns=arrival, sample_ns=arrival, source_frame_number=k,
                         flags=int(flags), rotation_cw_deg=0)
            cam["k"] = k + 1
            written[camera_id] += 1
        next_t += period
        delay = next_t - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        elif delay < -1.0:
            next_t = time.perf_counter()  # far behind (a long JPEG make): start the pace again


# ---------------------------------------------------------------------------
# The observer of the server: sends, ready messages and not_shown_count for each connection
# ---------------------------------------------------------------------------

class Connections:
    """One record for each websocket connection, in the order of the connections (1, 2, ...). Each
    record has, for each camera: the start time of each send of a camera message (`sent`, ms), the
    receipt time of each ready message (`ready`, ms), the send-to-ready time of each ready message
    (`send_to_ready_ms`), and the last `not_shown_count` that the connection sent."""

    def __init__(self):
        self.records = {}
        self._numbers = itertools.count(1)
        self.servers = weakref.WeakSet()  # the WebsocketServer of each connection, to close it

    def new(self):
        number = next(self._numbers)
        record = self.records[number] = dict(opened=now_ms(), cameras={}, not_shown={})
        return record

    @staticmethod
    def camera(record, camera_id):
        return record["cameras"].setdefault(camera_id, dict(sent=[], ready=[], send_to_ready_ms=[], pending=None))

    def counts(self, since=0.0, until=float("inf")):
        out = {}
        for number, record in self.records.items():
            out[str(number)] = {"opened": record["opened"], "cameras": {
                camera_id: {
                    "sent": [t for t in c["sent"] if since <= t <= until],
                    "ready": [t for t in c["ready"] if since <= t <= until],
                    "send_to_ready_ms": [d for t, d in c["send_to_ready_ms"] if since <= t <= until],
                } for camera_id, c in record["cameras"].items()}}
        return out


CONNECTIONS = Connections()


def install_observer():
    """Replace `PreviewRelay` with a subclass that counts, before `websocket_server` imports it. It uses
    only the interface of 4a: the constructor and `handle_text`. It passes each keyword of the constructor on (the
    `step_set` and the `send_lock` of capture-timings.md 6.5)."""
    from skellycam.api.websocket import preview_relay
    from skellycam.api.websocket.websocket_message_types import WebsocketMessageType

    base = preview_relay.PreviewRelay

    class CountingRelay(base):
        def __init__(self, manager, send_bytes, send_json, **kwargs):
            record = CONNECTIONS.new()
            self._record = record

            async def counted_bytes(data):
                camera_id = bytes(data[32:48]).rstrip(b"\0").decode("ascii", "replace")
                camera = CONNECTIONS.camera(record, camera_id)
                camera["sent"].append(now_ms())
                camera["pending"] = time.perf_counter()
                await send_bytes(data)

            async def counted_json(data):
                if isinstance(data, dict) and data.get("message_type") == WebsocketMessageType.FRAMERATE_UPDATE:
                    for camera_id, values in (data.get("cameras") or {}).items():
                        record["not_shown"][camera_id] = values.get("not_shown_count")
                await send_json(data)

            super().__init__(manager, counted_bytes, counted_json, **kwargs)

        def handle_text(self, text):
            result = super().handle_text(text)
            if result:
                with contextlib.suppress(ValueError, AttributeError, TypeError):
                    camera = CONNECTIONS.camera(self._record, json.loads(text)["camera_id"])
                    camera["ready"].append(now_ms())
                    if camera["pending"] is not None:
                        camera["send_to_ready_ms"].append((now_ms(), (time.perf_counter() - camera["pending"]) * 1e3))
                        camera["pending"] = None
            return result

    preview_relay.PreviewRelay = CountingRelay
    from skellycam.api.websocket import websocket_server
    if hasattr(websocket_server, "PreviewRelay"):
        websocket_server.PreviewRelay = CountingRelay
    original_init = websocket_server.WebsocketServer.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        CONNECTIONS.servers.add(self)

    websocket_server.WebsocketServer.__init__ = init


async def close_connections():
    from starlette.websockets import WebSocketState

    closed = 0
    for server in list(CONNECTIONS.servers):
        websocket = server.websocket
        if websocket.client_state != WebSocketState.CONNECTED:
            continue
        async with getattr(server, "_send_lock", None) or contextlib.nullcontext():
            with contextlib.suppress(RuntimeError, OSError):
                await websocket.close(code=1012)
                closed += 1
    return closed


def patch_manager(manager):
    """As the `app` fixture: each import site of `get_or_create_camera_group_manager` gives `manager`."""
    import skellycam.api.http.cameras.camera_router as camera_router
    import skellycam.api.websocket.websocket_server as websocket_server

    camera_router.get_or_create_camera_group_manager = lambda app: manager
    websocket_server.get_or_create_camera_group_manager = lambda app: manager


def build_app(kill_flag):
    from fastapi import FastAPI

    import skellycam
    from skellycam.api.routers import SKELLYCAM_ROUTERS

    app = FastAPI()
    app.state.global_kill_flag = kill_flag
    for router in SKELLYCAM_ROUTERS:
        app.include_router(router, prefix=f"/{skellycam.__package_name__}")
    return app


# ---------------------------------------------------------------------------
# Mode "fake": fake rings, a scripted app_state
# ---------------------------------------------------------------------------

def scripted_manager(width, height, fps):
    """The fake manager of `preview_helpers.py` with a `to_state_dict` that gives a scripted `app_state`.
    It is also a `CameraGroupManager`, for the beartype check of `WebsocketServer.__init__`."""
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera.config.image_resolution import ImageResolution
    from skellycam.core.camera_group.camera_group_manager import CameraGroupManager
    from skellycam.tests.preview.preview_helpers import FakeGroup, FakeManager

    class ScriptedManager(FakeManager, CameraGroupManager):
        def __init__(self):
            FakeManager.__init__(self, FakeGroup("g1"))
            self.scripted = {}  # camera id -> {"index", "name", "state", "replaced_count"}

        def __repr__(self):
            return f"ScriptedManager({list(self.scripted)})"

        def to_state_dict(self):
            if not self.scripted:
                return {"camera_groups": {}}
            configs = {camera_id: CameraConfig(camera_id=camera_id, camera_index=s["index"], camera_name=s["name"],
                                               resolution=ImageResolution(width=width, height=height),
                                               framerate=float(fps)).model_dump(mode="json")
                       for camera_id, s in self.scripted.items()}
            cameras = {camera_id: {"pid": os.getpid(), "name": f"fake ring {camera_id}", "alive": True, "status": {
                "state": s["state"], "replaced_count": s["replaced_count"], "failure": None, "warnings": [],
                "measured_fps": None, "mode": None, "exposure_search": None}} for camera_id, s in self.scripted.items()}
            # ADR-NYT6 (camera-requests.md 1.5): alive while at least one camera lives (not `failed` or `dead`)
            alive = any(s["state"] not in ("failed", "dead") for s in self.scripted.values())
            return {"camera_groups": {"g1": {"id": "g1", "configs": configs, "cameras": cameras, "alive": alive,
                                             "recording_in_progress": False, "take_state": "none",
                                             "ended_take_summary": None}}}

    return ScriptedManager()


class FakeRingsMode:
    def __init__(self, args):
        self.width, self.height, self.fps = args.width, args.height, args.fps
        self.target_bytes = args.target_bytes or None
        self.initial = json.loads(args.cameras)
        self.manager = scripted_manager(self.width, self.height, self.fps)
        self.creators = {}
        self.numbers = {}
        self._generations = itertools.count(1)
        context = multiprocessing.get_context("spawn")
        self.commands, self.replies = context.Queue(), context.Queue()
        self.process = context.Process(target=writer_main, name="ui-server-writers", daemon=True, args=(
            self.commands, self.replies, self.width, self.height, self.fps, self.target_bytes))

    async def writer(self, *cmd, timeout=WRITER_TIMEOUT_S):
        self.commands.put(cmd)
        status, value = await asyncio.to_thread(self.replies.get, True, timeout)
        assert status == "ok", status
        return value

    def _ring(self, camera_id):
        from skellycam.core.ipc.frame_ring import FrameRingCreator, FrameRingReader, PixelFormat

        creator = FrameRingCreator.create(camera_id=camera_id, camera_index=RING_INDEX_BASE + self.numbers[camera_id],
                                          pixel_format=PixelFormat.JPEG, width=self.width, height=self.height,
                                          fps_num=self.fps, fps_den=1, history_s=1.0,
                                          generation=next(self._generations))
        return creator, FrameRingReader.attach(creator.name)

    async def start(self):
        self.process.start()
        for camera in self.initial:
            await self.add(camera, active=False)
        await self.writer("start_all")

    def camera_list(self):
        return [{"id": camera_id, "number": self.numbers[camera_id], "name": s["name"]}
                for camera_id, s in self.manager.scripted.items()]

    async def add(self, cmd, active=True):
        camera_id = cmd["camera"] if "camera" in cmd else cmd["id"]
        assert camera_id not in self.creators, f"camera {camera_id} exists"
        number = int(cmd.get("number", len(self.creators) + 1))
        assert 1 <= number <= 8, "a camera number is 1 to 8"
        self.numbers[camera_id] = number
        creator, reader = self._ring(camera_id)
        self.creators[camera_id] = creator
        await self.writer("add", camera_id, creator.name, number, active)
        self.manager.add_reader(camera_id, reader)
        self.manager.scripted[camera_id] = dict(index=int(cmd.get("index", 90 + number)),
                                                name=cmd.get("name", f"ring camera {number}"),
                                                state=cmd.get("state", "ready"), replaced_count=0)
        return {}

    async def remove(self, camera_id):
        self.manager.scripted.pop(camera_id)
        self.manager.remove_reader(camera_id)
        await self.writer("remove", camera_id)
        self.creators.pop(camera_id).close_and_unlink()

    async def restart(self, camera_id):
        """A new ring under the same camera id, from frame 0 (4a 4.4)."""
        old = self.creators[camera_id]
        creator, reader = self._ring(camera_id)
        self.creators[camera_id] = creator
        self.manager.replace_reader(camera_id, reader)
        await self.writer("restart", camera_id, creator.name)
        old.close_and_unlink()

    async def handle(self, cmd):
        name, camera_id = cmd["cmd"], cmd.get("camera")
        if name == "add":
            return await self.add(cmd)
        if name == "remove":
            return await self.remove(camera_id) or {}
        if name == "restart":
            return await self.restart(camera_id) or {}
        if name == "set_state":
            assert cmd["state"] in STATES, cmd["state"]
            self.manager.scripted[camera_id]["state"] = cmd["state"]
            return {}
        if name == "set_replaced":
            self.manager.scripted[camera_id]["replaced_count"] = int(cmd["count"])
            return {}
        if name in ("flagged", "oversize", "ring_skip"):
            await self.writer("skip" if name == "ring_skip" else name, camera_id, int(cmd.get("count", 1)))
            return {}
        if name in ("stop_writer", "start_writer"):
            await self.writer("active", camera_id, name == "start_writer")
            return {}
        if name == "set_fps":
            await self.writer("fps", float(cmd["fps"]))
            return {}
        if name == "written":
            return {"written": await self.writer("written")}
        raise KeyError(f"unknown command {name}")

    async def close(self):
        if self.process.is_alive():
            with contextlib.suppress(Exception):
                await self.writer("quit", timeout=10)
        print("ui_server stop: the writers answered quit", file=sys.stderr, flush=True)
        self.process.join(10)
        print(f"ui_server stop: the writer process joined (alive {self.process.is_alive()})", file=sys.stderr, flush=True)
        for camera_id in list(self.manager.group().ring_readers):
            self.manager.remove_reader(camera_id)
        for creator in self.creators.values():
            creator.close_and_unlink()


# ---------------------------------------------------------------------------
# Mode "capture": the real CameraGroupManager and CameraGroup with fake sources
# ---------------------------------------------------------------------------

def _tuples(value):
    return tuple(_tuples(v) for v in value) if isinstance(value, list) else value


class CaptureFakesMode:
    def __init__(self, args):
        import skellycam.api.http.cameras.camera_router as camera_router
        import skellycam.core.camera_group.camera_group_manager as manager_module
        from skellycam.core.camera_group.camera_group_manager import CameraGroupManager
        from skellycam.core.ipc.process_management.managed_worker import WorkerMode
        from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
        from skellycam.tests.capture.fake_source import FakeScript, FakeSource, FakeSourceFactory
        from skellycam.tests.preview.barcode_jpegs import make_jpegs

        self.specs = json.loads(args.cameras)
        scripts = [FakeScript(**{"name": spec.get("name"), **{k: _tuples(v) for k, v in spec.get("script", {}).items()}})
                   for spec in self.specs]
        self.factory = FakeSourceFactory(scripts)  # no clock: the real clock (RealClock) for each source
        self.kill = args.kill_flag
        self.registry = WorkerRegistry(global_kill_flag=self.kill, worker_mode=WorkerMode.THREAD)
        self.manager = CameraGroupManager(global_kill_flag=self.kill, worker_registry=self.registry,
                                          source_factory=self.factory, restore_store=None)
        camera_router.detect_available_cameras = lambda *a, **k: self.factory.device_infos()
        manager_module.detect_available_cameras = lambda *a, **k: self.factory.device_infos()
        # Each frame of a fake source is a barcode JPEG of its camera, at the size of its mode.
        jpegs = {}
        make_frame = FakeSource._make_frame
        factory = self.factory

        def barcode_frame(source, k, arrival):
            import dataclasses

            frame = make_frame(source, k, arrival)
            number = factory.camera_ids.index(source.camera_id) + 1
            key = (number, source._mode.width, source._mode.height)
            if key not in jpegs:
                jpegs[key] = make_jpegs(number, source._mode.width, source._mode.height)
            payload = jpegs[key][k % len(jpegs[key])]
            return dataclasses.replace(frame, payload=payload, delivered_len=len(payload))

        FakeSource._make_frame = barcode_frame
        self.port = None
        self.applies = []

    def _post(self, path, body=None):
        connection = http.client.HTTPConnection(HOST, self.port, timeout=120)
        try:
            connection.request("POST", path, body=json.dumps(body or {}), headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        finally:
            connection.close()

    def _config(self, index):
        from skellycam.core.camera.config.camera_config import CameraConfig
        from skellycam.core.camera.config.image_resolution import ImageResolution

        width, height, fps_num, fps_den, _ = self.factory.scripts[index].modes[0]
        return CameraConfig(camera_id=self.factory.camera_ids[index], camera_index=index,
                            camera_name=self.factory.scripts[index].name or f"Fake camera {index}",
                            resolution=ImageResolution(width=width, height=height),
                            framerate=round(fps_num / fps_den, 2), exposure_mode="MANUAL", exposure=-7)

    async def start(self):
        status, text = await asyncio.to_thread(self._post, "/skellycam/camera/detect")
        assert status == 200, text

    def camera_list(self):
        return [{"id": camera_id, "number": i + 1, "name": self.factory.scripts[i].name or f"Fake camera {i}"}
                for i, camera_id in enumerate(self.factory.camera_ids)]

    def _states(self):
        """The state of each camera and the `alive` flag of each group, from the real `to_state_dict`."""
        out, alive = {}, {}
        for group_id, group in self.manager.to_state_dict()["camera_groups"].items():
            alive[group_id] = group["alive"]
            for camera_id, camera in group["cameras"].items():
                out[camera_id] = (camera.get("status") or {}).get("state")
        return out, alive

    async def handle(self, cmd):
        name = cmd["cmd"]
        if name == "apply":
            ids = self.factory.camera_ids
            body = {"camera_configs": {ids[i]: self._config(i).model_dump(mode="json") for i, camera_id in
                                       enumerate(ids) if camera_id in cmd.get("cameras", ids)},
                    "retry_camera_ids": list(cmd.get("retry", []))}
            number = len(self.applies)
            self.applies.append(None)

            def run():  # an open can hold (`hold_opens`): the reply does not wait for the apply
                self.applies[number] = self._post("/skellycam/camera/group/apply", body)

            threading.Thread(target=run, daemon=True, name=f"ui-server-apply-{number}").start()
            return {"apply": number}
        if name == "release":
            self.factory.sources[cmd["camera"]].release()
            return {}
        if name == "stall":
            self.factory.sources[cmd["camera"]].stop_now()
            return {}
        if name == "states":
            states, alive = self._states()
            return {"states": states, "alive": alive, "at": now_ms(),
                    "applies": [None if a is None else {"status": a[0], "text": a[1][:2000]} for a in self.applies]}
        raise KeyError(f"unknown command {name}")

    async def close(self):
        for source in list(self.factory.sources.values()):
            source.release()
        with contextlib.suppress(Exception):
            await self.manager.close_all_camera_groups()
        await asyncio.to_thread(self.registry.shutdown_all)


# ---------------------------------------------------------------------------
# The command loop
# ---------------------------------------------------------------------------

async def loop_cpu_s():
    return time.thread_time()  # this coroutine runs on the event-loop thread


async def dispatch(mode, cmd, stop):
    name = cmd.get("cmd")
    if name == "ping":
        return {}
    if name == "counts":
        return {"now": now_ms(), "connections": CONNECTIONS.counts(float(cmd.get("since", 0.0)),
                                                                   float(cmd.get("until", float("inf"))))}
    if name == "not_shown":
        return {"connections": {str(n): dict(r["not_shown"]) for n, r in CONNECTIONS.records.items()}}
    if name == "close_connections":
        return {"closed": await close_connections()}
    if name == "loop_cpu":
        return {"loop_thread_cpu_s": await loop_cpu_s(), "at": now_ms()}
    if name == "stop":
        asyncio.get_running_loop().call_later(0.05, stop.set)
        return {}
    return await mode.handle(cmd)


def read_commands(loop, mode, stop):
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        cmd = None
        try:
            cmd = json.loads(line)
            reply = asyncio.run_coroutine_threadsafe(dispatch(mode, cmd, stop), loop).result()
            emit({"ok": True, **reply})
        except Exception as error:  # the test gets the error as a reply; the server stays up
            emit({"ok": False, "error": f"{error!r}", "trace": traceback.format_exc()[-2000:]})
        if stop.is_set() or (isinstance(cmd, dict) and cmd.get("cmd") == "stop"):
            return
    loop.call_soon_threadsafe(stop.set)  # stdin closed: the test ended


async def serve(args):
    import uvicorn

    install_observer()
    args.kill_flag = multiprocessing.Value("b", False)
    mode = CaptureFakesMode(args) if args.mode == "capture" else FakeRingsMode(args)
    patch_manager(mode.manager)
    app = build_app(args.kill_flag)
    sock = free_socket()
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app=app, log_level="warning", ws_per_message_deflate=False))
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        if serving.done():
            serving.result()
        await asyncio.sleep(0.02)
    mode.port = port
    stop = asyncio.Event()
    try:
        await mode.start()
        emit({"event": "started", "port": port, "cameras": mode.camera_list(), "mode": args.mode})
        threading.Thread(target=read_commands, args=(asyncio.get_running_loop(), mode, stop), daemon=True,
                         name="ui-server-commands").start()
        await stop.wait()
    finally:
        # the time of each step of the stop on stderr, and the stacks of each thread when the stop takes more than
        # 8 s (Q896: the test kills a server whose stop takes more than 20 s and logs its last output lines)
        faulthandler.dump_traceback_later(8, file=sys.stderr)
        started = time.monotonic()

        def step(name):
            print(f"ui_server stop: {name} at {(time.monotonic() - started) * 1000:.0f} ms", file=sys.stderr, flush=True)

        with contextlib.suppress(Exception):
            await close_connections()
        step("connections closed")
        server.should_exit = True
        await serving
        step("uvicorn ended")
        await mode.close()
        step("mode closed")
        faulthandler.cancel_dump_traceback_later()
        emit({"event": "stopped"})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("fake", "capture"), default="fake")
    parser.add_argument("--cameras", default="[]", help="a JSON list of cameras (see the module docstring)")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--target-bytes", type=int, default=0, help="the JPEG size; 0: no target (640 x 360)")
    args = parser.parse_args(argv)

    from skellycam.utilities.utf8_console import utf8_console

    utf8_console()
    from skellylogs import configure_logging

    from skellycam import LOG_LEVEL

    # As skellycam/__main__.py, but the log file goes to a temporary folder, not to the folder of the app.
    log_dir = Path(tempfile.mkdtemp(prefix="skellycam-ui-server-"))
    configure_logging(level=LOG_LEVEL, log_file_path=str(log_dir / "ui_server.log"))
    code = 0
    try:
        asyncio.run(serve(args))
    except BaseException:  # the test reads the trace in the output
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    # As skellycam/__main__.py: the port and the rings are closed; the exit does not wait for the feeder
    # thread of the log queue, which nobody reads at the end.
    os._exit(code)


if __name__ == "__main__":
    if multiprocessing.get_start_method(allow_none=True) != "spawn":
        multiprocessing.set_start_method("spawn", force=True)
    main()
