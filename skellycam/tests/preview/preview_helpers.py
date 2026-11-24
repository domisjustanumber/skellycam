"""Test-only helpers for the step 4a preview tests (specs/preview.md, section 9.1).

- Fake rings: real rings of the ring package in the test process, with synthetic payloads.
- A fake manager with `closing` and `camera_groups`.
- A spy reader, a stub reader and a slow send.
- A fake connection for the fake tests, and the test route with a websocket client for the ws tests.
- An independent parser of the camera message, written from table 3.2 of the spec. Do not import
  `CAMERA_FRAME_HEADER` into this file.

Each product module is imported inside a test or a helper call, so that a missing module makes the
test fail with `ModuleNotFoundError`, not error at collection. The names that the spec does not fix
are in ADR-24FZ.
"""

import asyncio
import contextlib
import importlib
import itertools
import json
import struct
import threading
import time
from collections import defaultdict
from types import SimpleNamespace

import anyio
import msgspec

from skellycam.tests.frame_ring.ring_spec import paced_payload, ring

PREVIEW_MODULE = "skellycam.api.websocket.preview_relay"
FRAMERATE_MODULE = "skellycam.core.recorders.framerate_tracker"

WIDTH, HEIGHT = 64, 48  # small rings: a JPEG slot of 8192 bytes (table 3.6 of the ring spec)
SLOT_CAPACITY = 8192
PAYLOAD_SIZE = 2000
OVERSIZE_PAYLOAD_SIZE = SLOT_CAPACITY + 808
PERIOD_NS = 33_333_333
WAIT_TIMEOUT_S = 10.0
CAMERA_INDEX_BASE = 50  # away from the camera indexes of the ring tests

_GENERATIONS = itertools.count(1)  # a new ring name for each fake ring of this process


def preview():
    """Import the preview module inside a test (a missing module fails the test)."""
    return importlib.import_module(PREVIEW_MODULE)


def framerate_tracker():
    return importlib.import_module(FRAMERATE_MODULE)


# ---------------------------------------------------------------------------
# Table 3.2: the camera message. (offset, struct code, name). Little-endian.
# ---------------------------------------------------------------------------

HEADER_SIZE = 48
MESSAGE_FIELDS = (
    (0, "B", "version"),
    (4, "I", "flags"),
    (8, "q", "frame_number"),
    (16, "q", "arrival_ns"),
    (24, "I", "rotation_cw_deg"),
    (28, "I", "jpeg_len"),
    (32, "16s", "camera_id_raw"),
)
RESERVED = (1, 4)
ERROR_MASK = 0x0F

# The example of section 3.2, byte for byte.
SPEC_EXAMPLE = bytes.fromhex(
    "01 00 00 00 30 00 00 00 02 01 00 00 00 00 00 00"
    "07 ca 9a 3b 00 00 00 00 5a 00 00 00 04 00 00 00"
    "61 31 62 32 00 00 00 00 00 00 00 00 00 00 00 00"
    "ff d8 ff d9")


def parse_camera_message(data):
    """The fields of one camera message, read at the offsets of table 3.2."""
    data = bytes(data)
    assert len(data) >= HEADER_SIZE, f"a camera message of {len(data)} bytes"
    fields = {name: struct.unpack_from("<" + code, data, offset)[0] for offset, code, name in MESSAGE_FIELDS}
    fields["reserved"] = data[RESERVED[0]:RESERVED[1]]
    fields["camera_id"] = fields["camera_id_raw"].rstrip(b"\0").decode("ascii", "replace")
    fields["jpeg"] = data[HEADER_SIZE:]
    fields["length"] = len(data)
    return SimpleNamespace(**fields)


def pack_message_for_test(*, version=1, flags=0, frame_number=0, arrival_ns=0, rotation_cw_deg=0, camera_id=b"",
                          jpeg=b""):
    """A camera message written at the offsets of table 3.2 (for the self-test of the parser)."""
    out = bytearray(HEADER_SIZE)
    values = dict(version=version, flags=flags, frame_number=frame_number, arrival_ns=arrival_ns,
                  rotation_cw_deg=rotation_cw_deg, jpeg_len=len(jpeg), camera_id_raw=camera_id.ljust(16, b"\0"))
    for offset, code, name in MESSAGE_FIELDS:
        struct.pack_into("<" + code, out, offset, values[name])
    return bytes(out) + jpeg


def tag_of(message):
    """The tag of the fake ring that wrote the JPEG of a camera message (None for a header-only one)."""
    return int.from_bytes(message.jpeg[:2], "little") if message.jpeg_len else None


def ready_text(camera_id):
    """The ready message of section 4.1."""
    return json.dumps({"message_type": "camera_ready", "camera_id": camera_id})


# ---------------------------------------------------------------------------
# Fake rings (9.1)
# ---------------------------------------------------------------------------

class FakeRing:
    """A real JPEG ring in the test process with its writer. Payloads and times are a function of
    the frame number and of `tag`, so a test can tell the frames of two rings apart."""

    def __init__(self, cleanup, camera_id, camera_index=CAMERA_INDEX_BASE, *, fps=30, history_s=1.0, tag=0,
                 arrival_base=1_000_000_000, period_ns=PERIOD_NS):
        fr = ring()
        self.cleanup = cleanup
        self.camera_id = camera_id
        self.tag = tag
        self.arrival_base = arrival_base + tag * 10 ** 12
        self.period_ns = period_ns
        self.creator = cleanup.own(fr.FrameRingCreator.create(
            camera_id=camera_id, camera_index=camera_index, pixel_format=fr.PixelFormat.JPEG, width=WIDTH,
            height=HEIGHT, fps_num=fps, fps_den=1, history_s=history_s, generation=next(_GENERATIONS)))
        self.writer = cleanup.handle(fr.FrameRingWriter.attach(self.creator.name))
        self.written = {}  # frame number -> time.monotonic() after its commit
        self.skipped = {}  # frame number written with newer_frame_waiting=True -> time.monotonic()
        self.last = -1
        self._lock = threading.Lock()

    @property
    def name(self):
        return self.creator.name

    def reader(self):
        """A new reader of this ring. The test cleanup closes it."""
        return self.cleanup.handle(ring().FrameRingReader.attach(self.creator.name))

    def payload(self, k):
        return self.tag.to_bytes(2, "little") + paced_payload(k, PAYLOAD_SIZE)

    def arrival(self, k):
        return self.arrival_base + k * self.period_ns

    def write(self, k, *, payload=None, flags=0, rotation=0, source_frame_number=None, arrival_ns=None,
              newer_frame_waiting=False):
        arrival_ns = self.arrival(k) if arrival_ns is None else arrival_ns
        self.writer.write(self.payload(k) if payload is None else payload, frame_number=k, arrival_ns=arrival_ns,
                          sample_ns=arrival_ns - 1000, source_frame_number=k if source_frame_number is None
                          else source_frame_number, flags=flags, rotation_cw_deg=rotation,
                          newer_frame_waiting=newer_frame_waiting)
        with self._lock:
            if newer_frame_waiting:
                self.skipped[k] = time.monotonic()
            else:
                self.written[k] = time.monotonic()
                self.last = k

    def write_range(self, first, last, **kwargs):
        for k in range(first, last + 1):
            self.write(k, **kwargs)

    def written_between(self, t0, t1):
        with self._lock:
            return [k for k, t in self.written.items() if t0 <= t <= t1]

    def set_closed(self):
        self.creator.set_closed()


class PacedWriter:
    """Writes frames `first`, `first + 1`, ... to a fake ring at `fps`, in a thread (`start_thread`)
    or as a task of the running event loop (`start_task`). `script(k)` gives extra write arguments for
    frame k. A frame with `newer_frame_waiting=True` is followed at once by the next frame, in the same
    step. After `stop_after`, the writer writes nothing more. When a test then makes `stop_after` larger, the writer
    continues at `fps` from that time (T-PRV-54)."""

    def __init__(self, ring_, fps=30, first=None, stop_after=None, script=None):
        self.ring = ring_
        self.period = 1.0 / fps
        self.next_k = ring_.last + 1 if first is None else first
        self.stop_after = stop_after
        self.script = script or (lambda k: {})
        self._stop = threading.Event()
        self._thread = None
        self._task = None

    def step(self):
        """Write the next frame. Return False when the writer is past `stop_after`."""
        while True:
            k = self.next_k
            if self.stop_after is not None and k > self.stop_after:
                return False
            kwargs = self.script(k)
            self.ring.write(k, **kwargs)
            self.next_k = k + 1
            if not kwargs.get("newer_frame_waiting"):
                return True

    def start_thread(self):
        def run():
            next_t = time.perf_counter()
            while not self._stop.is_set():
                if not self.step():
                    self._stop.wait(0.005)
                    next_t = time.perf_counter()
                    continue
                next_t += self.period
                delay = next_t - time.perf_counter()
                if delay > 0:
                    self._stop.wait(delay)
        self._thread = threading.Thread(target=run, daemon=True, name=f"paced-writer-{self.ring.camera_id}")
        self._thread.start()
        return self

    def start_task(self):
        async def run():
            loop = asyncio.get_running_loop()
            next_t = loop.time()
            while not self._stop.is_set():
                if not self.step():
                    await asyncio.sleep(0.005)
                    next_t = loop.time()
                    continue
                next_t += self.period
                await asyncio.sleep(max(0.0, next_t - loop.time()))
        self._task = asyncio.get_running_loop().create_task(run())
        return self

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)
        if self._task is not None:
            self._task.cancel()


# ---------------------------------------------------------------------------
# Fake manager, spy reader, stub reader (9.1)
# ---------------------------------------------------------------------------

class FakeGroup:
    def __init__(self, group_id, ring_readers=None):
        self.id = group_id
        self.ring_readers = dict(ring_readers or {})


class FakeManager:
    """An object with `closing` and `camera_groups`, as the sender uses `CameraGroupManager` (section 7).
    Each change is a plain dict operation. `remove_reader` removes, then closes, as `_close_rings`
    does."""

    def __init__(self, *groups):
        self.closing = False
        self.camera_groups = {group.id: group for group in groups}

    def group(self, group_id="g1"):
        return self.camera_groups[group_id]

    def add_reader(self, camera_id, reader, group_id="g1"):
        self.camera_groups[group_id].ring_readers[camera_id] = reader

    def remove_reader(self, camera_id, group_id="g1"):
        self.camera_groups[group_id].ring_readers.pop(camera_id).close()

    def replace_reader(self, camera_id, reader, group_id="g1"):
        """A new ring under the same camera id: the old reader leaves and is closed first."""
        self.remove_reader(camera_id, group_id)
        self.add_reader(camera_id, reader, group_id)

    def remove_group(self, group_id):
        """The group leaves, and each of its readers is removed, then closed."""
        group = self.camera_groups.pop(group_id)
        for camera_id in list(group.ring_readers):
            group.ring_readers.pop(camera_id).close()


def manager_with(readers, group_id="g1"):
    """A fake manager with one group of {camera_id: reader}."""
    return FakeManager(FakeGroup(group_id, readers))


class ReadThroughClosedReader(AssertionError):
    pass


class SpyReader:
    """A reader that records each call with its time. After `close()`, each call is recorded in
    `after_close` and raises: "the closed reader raises if it is read" (T-PRV-20)."""

    def __init__(self, reader):
        self._reader = reader
        self.calls = []  # (time.monotonic(), method, frame number or None)
        self.after_close = []
        self.closed = False

    def _note(self, method, k=None):
        if self.closed:
            self.after_close.append((method, k))
            raise ReadThroughClosedReader(f"{method}({k}) through a closed reader")
        self.calls.append((time.monotonic(), method, k))

    def read(self, k):
        self._note("read", k)
        return self._reader.read(k)

    def read_newest(self):
        self._note("read_newest")
        return self._reader.read_newest()

    @property
    def oversize_count(self):
        self._note("oversize_count")
        return self._reader.oversize_count

    @property
    def skipped_count(self):
        self._note("skipped_count")
        return self._reader.skipped_count

    @property
    def failed_checks(self):
        return self._reader.failed_checks

    def close(self):
        self.closed = True
        self._reader.close()

    def reads_of(self, k, method="read", since=0.0):
        return [c for c in self.calls if c[1] == method and c[2] == k and c[0] >= since]

    def read_calls(self, since=0.0):
        return [c for c in self.calls if c[1] in ("read", "read_newest") and c[0] >= since]


def frame_read(result, k, *, arrival_ns=0, source_frame_number=0, flags=0, rotation=0, payload=None,
               payload_len=None):
    """A `FrameRead` of the ring package, made by hand."""
    fr = ring()
    if payload_len is None:
        payload_len = len(payload) if payload is not None else 0
    return fr.FrameRead(result, k, arrival_ns, arrival_ns - 1000 if arrival_ns else 0, arrival_ns + 1 if arrival_ns
                        else 0, source_frame_number, flags, rotation, payload_len, payload)


class StubReader:
    """A reader with scripted results, for results that a real ring gives only by chance (9.1).

    `script` maps a frame number to a list of results, one for each call of `read(k)`; the last item
    stays. A frame number with no script gives `NOT_YET_WRITTEN`. `read_newest` gives `newest`, by
    default `NOT_YET_WRITTEN` with no frame."""

    def __init__(self, script, newest=None, oversize_count=0, skipped_count=0):
        self.script = {k: list(results) for k, results in script.items()}
        self.newest = newest
        self.oversize_count = oversize_count
        self.skipped_count = skipped_count
        self.failed_checks = 0
        self.calls = []

    def read(self, k):
        self.calls.append(("read", k))
        results = self.script.get(k)
        if not results:
            return frame_read(ring().ReadResult.NOT_YET_WRITTEN, k)
        return results.pop(0) if len(results) > 1 else results[0]

    def read_newest(self):
        self.calls.append(("read_newest", None))
        return self.newest if self.newest is not None else frame_read(ring().ReadResult.NOT_YET_WRITTEN, -1)

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Fake connection for the fake tests: fake sends, a slow send, a fake client
# ---------------------------------------------------------------------------

class SlowGate:
    """Makes the next send wait on an `asyncio.Event` that the test controls (9.1). While the send
    waits, other coroutines run."""

    def __init__(self):
        self.armed = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    def arm(self):
        self.armed = True

    async def pass_through(self):
        if self.armed:
            self.armed = False
            self.entered.set()
            await self.release.wait()


def wire_json(data):
    """The JSON that the client gets: `msgspec.json`, as `WebsocketServer._send_msgspec_json`."""
    return json.loads(msgspec.json.encode(data))


class FakeConnection:
    """Fake `send_bytes` and `send_json` of one connection. Each send is an event
    (time.monotonic(), "camera" or "json", parsed message), in send order.

    `answer` is the set of camera ids for which the fake client answers at once: after the send
    returns, the event loop calls `relay.handle_text` with the ready message (`call_soon`). `True`
    means each camera."""

    def __init__(self, answer=frozenset()):
        self.answer = answer
        self.relay = None
        self.events = []
        self.bytes_gate = SlowGate()
        self.json_gate = SlowGate()

    async def send_bytes(self, data):
        assert isinstance(data, bytes | bytearray | memoryview), type(data)
        await self.bytes_gate.pass_through()
        message = parse_camera_message(data)
        self.events.append((time.monotonic(), "camera", message))
        if self.answer is True or message.camera_id in self.answer:
            asyncio.get_running_loop().call_soon(self.relay.handle_text, ready_text(message.camera_id))

    async def send_json(self, data):
        await self.json_gate.pass_through()
        self.events.append((time.monotonic(), "json", wire_json(data)))

    def camera(self, camera_id=None, since=0.0):
        return [m for t, kind, m in self.events if kind == "camera" and t >= since
                and (camera_id is None or m.camera_id == camera_id)]

    def camera_times(self, camera_id):
        return [t for t, kind, m in self.events if kind == "camera" and m.camera_id == camera_id]

    def json(self, message_type=None, since=0.0):
        return [m for t, kind, m in self.events if kind == "json" and t >= since
                and (message_type is None or m.get("message_type") == message_type)]

    def count_since(self, since):
        return len([e for e in self.events if e[0] >= since])


@contextlib.asynccontextmanager
async def running_relay(manager, connection):
    """Make a `PreviewRelay` on the fake connection and run it as a task. On exit, the task must
    still run; it is cancelled and awaited."""
    relay = preview().PreviewRelay(manager, connection.send_bytes, connection.send_json)
    connection.relay = relay
    task = asyncio.get_running_loop().create_task(relay.run())
    try:
        yield relay, task
        if task.done():
            task.result()  # raise its exception
            raise AssertionError("PreviewRelay.run ended before the task was cancelled")
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def wait_for(condition, what, timeout=WAIT_TIMEOUT_S):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, f"timed out: {what}"
        await asyncio.sleep(0.005)


# ---------------------------------------------------------------------------
# The test route and the websocket client (ws tests)
# ---------------------------------------------------------------------------

ROUTE = "/preview"


def preview_app(manager, relay_class=None):
    """A FastAPI app with one websocket route, wired as 4b will wire `WebsocketServer` (9.1).

    It accepts, makes a `PreviewRelay` with the send functions of the websocket (one send lock, as
    `WebsocketServer`), starts `run` as a task, and gives each text message to `handle_text`. When the
    client disconnects, it cancels the `run` task and waits for its end. `app.state.run_tasks` holds
    each `run` task; `app.state.errors` each exception of `run` or `handle_text`."""
    from fastapi import FastAPI, WebSocket

    relay_class = relay_class or preview().PreviewRelay
    app = FastAPI()
    app.state.run_tasks = []
    app.state.errors = []

    def note_end(task):
        if not task.cancelled() and task.exception() is not None:
            app.state.errors.append(task.exception())

    @app.websocket(ROUTE)
    async def route(websocket: WebSocket):
        await websocket.accept()
        lock = asyncio.Lock()

        async def send_bytes(data):
            async with lock:
                await websocket.send_bytes(data)

        async def send_json(data):
            async with lock:
                await websocket.send_text(msgspec.json.encode(data).decode("utf-8"))

        relay = relay_class(manager, send_bytes, send_json)
        task = asyncio.get_running_loop().create_task(relay.run())
        task.add_done_callback(note_end)
        app.state.run_tasks.append(task)
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("text") is not None:
                    try:
                        relay.handle_text(message["text"])
                    except Exception as error:
                        app.state.errors.append(error)
                        raise
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return app


class WsClient:
    """One test websocket client. It records each camera message (parsed) and each JSON message with
    the time it was taken from the socket, and answers at once for the cameras in `answer`
    (`True` = each camera)."""

    def __init__(self, session, answer=frozenset()):
        self.session = session
        self.answer = answer
        self.camera = defaultdict(list)  # camera id -> [(time, message)]
        self.json = []  # [(time, object)]
        self.order = []  # [(time, camera id)] in arrival order

    def receive(self, timeout):
        """The next message, or None after `timeout` seconds."""
        stream = self.session._send_rx

        async def get():
            with anyio.move_on_after(timeout):
                return await stream.receive()
            return None
        return self.session.portal.call(get)

    def poll(self, timeout=0.005):
        message = self.receive(timeout)
        if message is None:
            return None
        now = time.monotonic()
        assert message["type"] == "websocket.send", f"the server ended the connection: {message}"
        if message.get("bytes") is not None:
            parsed = parse_camera_message(message["bytes"])
            self.camera[parsed.camera_id].append((now, parsed))
            self.order.append((now, parsed.camera_id))
            if self.answer is True or parsed.camera_id in self.answer:
                self.session.send_text(ready_text(parsed.camera_id))
            return parsed
        self.json.append((now, json.loads(message["text"])))
        return self.json[-1][1]

    def send_ready(self, camera_id):
        self.session.send_text(ready_text(camera_id))

    def frames(self, camera_id, since=0.0, until=float("inf")):
        return [m.frame_number for t, m in self.camera[camera_id] if since <= t <= until]

    def times(self, camera_id):
        return [t for t, _ in self.camera[camera_id]]

    def first(self, camera_id):
        return self.camera[camera_id][0] if self.camera[camera_id] else None


def pump(clients, duration=None, until=None, timeout=WAIT_TIMEOUT_S, what="a condition"):
    """Read the messages of each client for `duration` seconds, or until `until()` is true (it must
    become true within `timeout`)."""
    clients = clients if isinstance(clients, list | tuple) else [clients]
    start = time.monotonic()
    end = start + (duration if duration is not None else timeout)
    while time.monotonic() < end:
        for client in clients:
            client.poll(0.002 if len(clients) > 1 else 0.005)
        if until is not None and until():
            return
    assert until is None, f"timed out: {what}"


def run_errors(app):
    """The exceptions of `run` and `handle_text` in the test route."""
    return list(app.state.errors)
