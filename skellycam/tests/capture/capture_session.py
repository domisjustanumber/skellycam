"""A camera session with fake sources for the phase 3 tests (specs/windows-capture.md, section 16).

`CaptureApp` is a FastAPI app with the camera router and the real `CameraGroupManager`, which gets
the `source_factory` of ADR-HP7D. The tests call `/camera/detect`, `/camera/group/apply` and the
record endpoints, as a consumer does.

- THREAD workers with a `VirtualClock`: the camera loops are threads of this process. The shared
  loop reads the time through `camera_loop.perf_counter_ns` (ADR-HP7D), which the app replaces with
  the virtual clock. The spies see each frame. No test sleeps for the virtual seconds.
- PROCESS workers with the real clock: the tests of a hard end (`os._exit`) and of process CPU.

Each product module is imported in the test or in `CaptureApp`, so that a missing module makes
the test fail with `ModuleNotFoundError`, not error at collection.
"""

import contextlib
import hashlib
import importlib
import json
import logging
import multiprocessing
import queue
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from skellycam.tests.capture.fake_source import FakeSourceFactory, VirtualClock

LOOP_MODULE = "skellycam.core.camera.capture.camera_loop"
SOURCE_MODULE = "skellycam.core.camera.capture.source"
WAIT_TIMEOUT_S = 60.0
STATES = ("starting", "waiting", "failed", "checking", "too_slow", "ready", "recording", "dead", "adjusting")


def product(name):
    """Import a product module inside a test (a missing module fails the test)."""
    return importlib.import_module(name)


def digest(data):
    if isinstance(data, np.ndarray):
        data = np.ascontiguousarray(data).tobytes()
    return hashlib.blake2b(bytes(data), digest_size=12).hexdigest()


def quiet_logging(monkeypatch):
    """The set-up of the ring tests: the log queue of the app and the extra log levels."""
    import skellylogs.handlers.websocket_log_queue_handler as log_queue_module

    monkeypatch.setattr(log_queue_module, "WEBSOCKET_LOG_QUEUE", multiprocessing.Queue(maxsize=1000))
    monkeypatch.setattr(logging.Logger, "trace", logging.Logger.debug, raising=False)
    monkeypatch.setattr(logging.Logger, "success", logging.Logger.info, raising=False)


def install_gate_probe(monkeypatch, clock):
    """Tell the virtual clock when a camera loop waits at the lockstep gate (5.2), and how the clock can see that the
    gate is still shut: the same probe again, with no clock call [ADR-7GC1]."""
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator

    original = CameraOrchestrator.should_grab_by_id

    def should_grab_by_id(self, camera_id):
        result = original(self, camera_id)
        clock.gate(not result, shut=lambda: not original(self, camera_id))
        return result

    monkeypatch.setattr(CameraOrchestrator, "should_grab_by_id", should_grab_by_id)


class ClockQueue(queue.Queue):
    """The request queue of the control thread of a camera loop on a `VirtualClock`. A request (a set of the
    exposure search, a live change) stops the time until the control thread waits for its next request, so
    that the set takes no virtual time, whatever the real time of the hand-over between the threads. A read
    of the controls after the timeout of `get` does not stop the time, as before."""

    def attach(self, clock, consumer):
        self.clock, self.consumer = clock, consumer

    def put(self, item, block=True, timeout=None):
        self.clock.give_work(self.consumer, lambda: super(ClockQueue, self).put(item, block, timeout))

    def get(self, block=True, timeout=None):
        if block and threading.current_thread() is self.consumer:
            self.clock.idle_if(self.empty)
        return super().get(block, timeout)


def install_control_clock(monkeypatch, clock, loop_module):
    """Give the request queue of each control thread to the virtual clock (`ClockQueue`). The control thread
    can already wait in a plain `get` of the queue: the next request wakes it as before. The attributes come
    before the class, so a `get` of the started thread never finds a `ClockQueue` with no clock."""
    original = loop_module._ControlThread.__init__

    def init(self, loop):
        original(self, loop)
        ClockQueue.attach(self.requests, clock, self.thread)
        self.requests.__class__ = ClockQueue

    monkeypatch.setattr(loop_module._ControlThread, "__init__", init)


def install_loop_clock(monkeypatch, clock):
    """Q673 [ADR-F4N7]: each camera loop thread (a THREAD worker) is a participant of the virtual clock from its
    start (`VirtualClock.expect`), as the control thread is for a request (`ClockQueue`) [ADR-DC43]. Else the time
    moves on before the new loop waits on the clock for the first time.

    The start of a group (`CameraManager.start`) expects each loop thread of the group before it starts the first.
    Else the first loop runs the time alone, through its open and warm-up, until the main thread starts the next
    worker: a main thread that lost the CPU for 2 ms or more between two starts gave a second camera that opened 3 s
    of virtual time after the first (T-CAP-91 on CI, "1 frames replaced in 100 s") [ADR-R394]."""
    from skellycam.core.camera.camera_manager import CameraManager
    from skellycam.core.camera.camera_worker import CameraWorker
    from skellycam.core.ipc.process_management.managed_worker import ManagedThread

    start_group = CameraManager.start

    def start_group_on_the_clock(manager):
        threads = [worker.worker._thread for worker in manager.camera_workers.values()
                   if isinstance(worker.worker, ManagedThread)]
        for thread in threads:
            clock.expect(thread)
        try:
            start_group(manager)
        finally:
            for thread in threads:
                if thread.ident is None:
                    clock.forget(thread)  # not started: a close stopped the loop of starts, or a start raised

    monkeypatch.setattr(CameraManager, "start", start_group_on_the_clock)
    start = CameraWorker.start

    def start_on_the_clock(worker):
        thread = worker.worker._thread if isinstance(worker.worker, ManagedThread) else None
        if thread is not None:
            clock.expect(thread)
        try:
            start(worker)
        except BaseException:
            if thread is not None:
                clock.forget(thread)
            raise
        if thread is not None and not thread.is_alive() and thread.ident is None:
            clock.forget(thread)  # the start returned with no thread (a start that the product refused)

    monkeypatch.setattr(CameraWorker, "start", start_on_the_clock)


def spy_check_anchors(monkeypatch):
    """The `after` time of each check that the loop feeds (windows-capture.md 10.2) [ADR-0R76]: after a live
    change, the time that the control thread read just before the set; after a search, the time that the loop
    read just before it sent the last set. The virtual clock can take a forced step while the control thread
    runs, so the `set_controls` event of the fake can come later than this anchor."""
    from skellycam.core.camera.capture.camera_loop import CameraLoop

    anchors = []
    feed_check = CameraLoop._feed_check

    def feed(self, sfn, arrival_ns):
        if self.check is not None and (not anchors or anchors[-1] != self.check["after"]):
            anchors.append(self.check["after"])
        return feed_check(self, sfn, arrival_ns)

    monkeypatch.setattr(CameraLoop, "_feed_check", feed)
    return anchors


def too_slow_after_the_window_start(app, camera_id, anchors, not_before):
    """T-CAP-31, T-REQ-99: the exact window of 10.2 [ADR-53VB, ADR-JWZ1]. Skipped frame 1 is the first frame whose
    arrival is after the anchor of the last check (`spy_check_anchors`). The anchor is not later than the last
    `set_controls` event of the fake with an exposure, and not earlier than `not_before` (a time that the anchor
    cannot come before; each test gives its own). The window starts at the 16th frame from skipped frame 1, at
    t_a. `too_slow` comes at t_a + 59 / (0.97 x 30) s, within +/-25 ms, after `checking`. Gives (t_a, the time of
    `too_slow`)."""
    log = app.factory.logs[camera_id]
    t_set = [t for name, t, d in log.events if name == "set_controls" and d.get("exposure")][-1]
    t_change = anchors[-1]
    assert not_before <= t_change <= t_set, (not_before, t_change, t_set)
    first_after = min(k for k, (arrival, _) in log.frames.items() if arrival > t_change)
    t_a = log.frames[first_after + 15][0]
    # The tracker writes a state at the next read of the fake, so it can be later than `wait_state`
    app.wait(lambda: app.tracker.first(camera_id, "too_slow") is not None, "the tracker sees too_slow")
    t_slow = app.tracker.first(camera_id, "too_slow")
    assert app.tracker.first(camera_id, "checking", t_change) < t_slow
    expected = t_a + round(59 / (0.97 * 30) * 1e9)
    assert abs(t_slow - expected) <= 25_000_000, f"too_slow {(t_slow - t_a) / 1e9:.4f} s after t_a"
    return t_a, t_slow


class LogCapture(logging.Handler):
    """Keeps each log record of this process (THREAD workers)."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        try:
            self.records.append((record.levelno, record.getMessage(), record.exc_info is not None))
        except Exception:
            pass

    def messages(self, level=logging.DEBUG):
        return [message for levelno, message, _ in self.records if levelno >= level]

    def tracebacks(self):
        return [message for _, message, has_traceback in self.records if has_traceback or "Traceback" in message]


@contextlib.contextmanager
def capture_logs():
    handler = LogCapture()
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


class Spies:
    """Class-level spies on the frame path (THREAD workers): JPEG and BGR ring writes, the camera
    writer of a take (`record` for `give`, `missing` for `give_missing`), the hand-over to the decode
    stage and `cv2.imdecode`. Each event has a sequence number and a hash of its payload or image;
    `keep_payloads` also keeps each JPEG payload. `writers` holds the camera writer of each camera.
    `fail_jpeg_write(event)` can make a JPEG ring write raise."""

    def __init__(self, monkeypatch, app=None, keep_payloads=False):
        from skellycam.core.ipc.frame_ring import DecodeInput, FrameRingWriter
        from skellycam.core.ipc.frame_ring import decode as decode_module
        from skellycam.core.take_recorder import CameraTakeWriter

        self.app = app
        self.keep_payloads = keep_payloads
        self.events = []
        self.writers = {}
        self.fail_jpeg_write = None
        self._seq = 0
        self._lock = threading.Lock()
        spies = self
        write, give, give_missing = FrameRingWriter.write, CameraTakeWriter.give, CameraTakeWriter.give_missing
        start = CameraTakeWriter.start.__func__
        put, imdecode = decode_module.WaitingPlace.put, cv2.imdecode

        def spy_write(writer, payload, **kwargs):
            kind = "bgr" if isinstance(payload, np.ndarray) or payload is None else "jpeg"
            event = spies._add(kind, camera=spies._camera_of_ring(writer.name), ring=writer.name,
                               frame_number=kwargs["frame_number"], arrival_ns=kwargs["arrival_ns"],
                               sample_ns=kwargs["sample_ns"], sfn=kwargs["source_frame_number"],
                               flags=int(kwargs["flags"]),
                               hash=None if payload is None else digest(payload),
                               payload=payload if spies.keep_payloads and kind == "jpeg" else None)
            if kind == "jpeg" and spies.fail_jpeg_write is not None and spies.fail_jpeg_write(event):
                event["raised"] = True
                raise RuntimeError("test: this ring write fails")
            return write(writer, payload, **kwargs)

        def spy_start(cls, spec, **kwargs):
            writer = start(cls, spec, **kwargs)
            spies.writers[spec.camera_id] = writer
            return writer

        def spy_give(writer, frame):
            spies._add("record", camera=writer.spec.camera_id, frame_number=frame.frame_number,
                       arrival_ns=frame.arrival_ns, sample_ns=frame.sample_ns, sfn=frame.source_frame_number,
                       flags=int(frame.flags), hash=digest(frame.payload),
                       payload=frame.payload if spies.keep_payloads else None)
            return give(writer, frame)

        def spy_give_missing(writer):
            spies._add("missing", camera=writer.spec.camera_id)
            return give_missing(writer)

        def spy_put(place, item):
            if isinstance(item, DecodeInput):
                spies._add("bgr_put", source=item.source, frame_number=item.frame_number,
                           arrival_ns=item.arrival_ns, sfn=item.source_frame_number, flags=int(item.flags),
                           hash=digest(item.payload))
            return put(place, item)

        def spy_imdecode(buffer, flags):
            spies._add("imdecode", hash=digest(buffer))
            return imdecode(buffer, flags)

        monkeypatch.setattr(FrameRingWriter, "write", spy_write)
        monkeypatch.setattr(CameraTakeWriter, "start", classmethod(spy_start))
        monkeypatch.setattr(CameraTakeWriter, "give", spy_give)
        monkeypatch.setattr(CameraTakeWriter, "give_missing", spy_give_missing)
        monkeypatch.setattr(decode_module.WaitingPlace, "put", spy_put)
        monkeypatch.setattr(cv2, "imdecode", spy_imdecode)
        self.original_imdecode = imdecode

    def _add(self, kind, **fields):
        with self._lock:
            self._seq += 1
            event = dict(seq=self._seq, kind=kind, thread=threading.current_thread().name, **fields)
            self.events.append(event)
        return event

    def _camera_of_ring(self, name):
        group = self.app.group_or_none() if self.app is not None else None
        if group is None:
            return None
        for camera_id, info in list(group.ring_infos.items()):
            if name in (info.jpeg_ring_name, info.bgr_ring_name):
                return camera_id
        return None

    def of(self, kind, camera=None):
        return [e for e in list(self.events) if e["kind"] == kind and (camera is None or e.get("camera") == camera)]

    def decode_image(self, jpeg):
        return self.original_imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)


class StateTracker:
    """The `on_read` hook of the fakes (THREAD workers): on each read of a fake, it keeps
    (clock ns, camera_id, state, controls) when the state or the controls of a camera changed."""

    def __init__(self):
        self.app = None
        self.history = []
        self._last = {}

    def __call__(self, source, now_ns):
        group = self.app.group_or_none() if self.app is not None else None
        if group is None:
            return
        for camera_id, status in list(group.cameras.orchestrator.camera_statuses.items()):
            try:
                serialized = status.serialize()
            except Exception:
                continue
            key = (serialized.get("state"), json.dumps(serialized.get("controls"), sort_keys=True))
            if self._last.get(camera_id) != key:
                self._last[camera_id] = key
                self.history.append((now_ns, camera_id, key[0], serialized.get("controls")))

    def states(self, camera_id):
        return [(t, state) for t, cid, state, _ in self.history if cid == camera_id]

    def first(self, camera_id, state, after_ns=0):
        for t, cid, s, _ in self.history:
            if cid == camera_id and s == state and t >= after_ns:
                return t
        return None


class CaptureApp:
    """The real manager and router with fake sources. Use `capture_app()`."""

    def __init__(self, monkeypatch, factory, *, workers="thread", restore_store=None):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import skellycam.api.http.cameras.camera_router as camera_router
        import skellycam.core.camera_group.camera_group_manager as manager_module
        from skellycam.core.camera_group.camera_group_manager import CameraGroupManager
        from skellycam.core.ipc.process_management.managed_worker import WorkerMode
        from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry

        loop_module = product(LOOP_MODULE)
        product(SOURCE_MODULE)
        quiet_logging(monkeypatch)
        self.factory = factory
        self.clock = factory.clock
        if self.clock is not None and self.clock.virtual:
            monkeypatch.setattr(loop_module, "perf_counter_ns", self.clock.now_ns)
            install_gate_probe(monkeypatch, self.clock)
            install_control_clock(monkeypatch, self.clock, loop_module)
            install_loop_clock(monkeypatch, self.clock)
            # A dead camera waits on the group frames in real time (recorder.md 10 item 7): not on the clock.
            missing_until_end = loop_module.CameraLoop._missing_until_end

            def leave_clock_first(loop):
                self.clock.leave()
                return missing_until_end(loop)

            monkeypatch.setattr(loop_module.CameraLoop, "_missing_until_end", leave_clock_first)
            # The take start reads the host clock of the arrivals (SFF-774): the virtual clock, else each CSV
            # time is negative (review item 15: total_duration_sec was -343355).
            group_module = product("skellycam.core.camera_group.camera_group")
            start_take = group_module.start_take

            def start_take_on_the_clock(*args, **kwargs):
                return start_take(*args, clock=(self.clock.now_ns, time.time_ns), **kwargs)

            monkeypatch.setattr(group_module, "start_take", start_take_on_the_clock)
        if isinstance(factory.on_read, StateTracker):
            factory.on_read.app = self
        self.kill = multiprocessing.Value("b", False)
        mode = WorkerMode.THREAD if workers == "thread" else WorkerMode.PROCESS
        self.registry = WorkerRegistry(global_kill_flag=self.kill, worker_mode=mode)
        # unix-capture.md 4.7.1: a folder of restore files only when the test gives one (never the folder of the app)
        self.manager = CameraGroupManager(global_kill_flag=self.kill, worker_registry=self.registry,
                                          source_factory=factory, restore_store=restore_store)
        self._router = camera_router
        monkeypatch.setattr(camera_router, "get_or_create_camera_group_manager", lambda app: self.manager)
        monkeypatch.setattr(camera_router, "detect_available_cameras",
                            lambda *args, **kwargs: self.factory.device_infos())
        # An apply with no detection result detects first (ADR-PDD3 W5): the fakes, never a real camera.
        self.detections = 0

        def detect_in_apply(*args, **kwargs):
            self.detections += 1
            return self.factory.device_infos()

        monkeypatch.setattr(manager_module, "detect_available_cameras", detect_in_apply)
        app = FastAPI()
        app.include_router(camera_router.camera_router, prefix="/skellycam")
        self.client = TestClient(app, raise_server_exceptions=False)
        self.client.__enter__()

    # ----- endpoints -----

    def detect(self):
        response = self.client.post("/skellycam/camera/detect")
        assert response.status_code == 200, response.text
        return response.json()

    def config(self, camera_id, **changes):
        """A config for a fake camera: its first mode, MANUAL -7, unless `changes` says else."""
        from skellycam.core.camera.config.camera_config import CameraConfig
        from skellycam.core.camera.config.image_resolution import ImageResolution

        index = self.factory.camera_ids.index(camera_id)
        width, height, fps_num, fps_den, _ = self.factory.scripts[index].modes[0]
        values = dict(camera_id=camera_id, camera_index=index,
                      resolution=ImageResolution(width=width, height=height),
                      framerate=round(fps_num / fps_den, 2), exposure_mode="MANUAL", exposure=-7)
        if "width" in changes:
            values["resolution"] = ImageResolution(width=changes.pop("width"), height=changes.pop("height"))
        values.update(changes)
        return CameraConfig(**values)

    def apply(self, configs, retry=()):
        """POST /camera/group/apply. `configs`: CameraConfig objects or a dict by camera_id. `retry`: the IDs of
        `retry_camera_ids`, the failed or dead cameras that the request opens again (windows-capture.md 8.3)."""
        if not isinstance(configs, dict):
            configs = {config.camera_id: config for config in configs}
        body = {"camera_configs": {cid: config.model_dump(mode="json") for cid, config in configs.items()},
                "retry_camera_ids": list(retry)}
        return self.client.post("/skellycam/camera/group/apply", json=body)

    def apply_all(self, **changes):
        response = self.apply([self.config(cid, **changes) for cid in self.factory.camera_ids])
        assert response.status_code == 200, response.text
        return response

    def record_start(self, directory, name="take"):
        return self.client.post("/skellycam/camera/group/all/record/start",
                                json={"recording_name": name, "recording_directory": str(directory)})

    def record_stop(self):
        return self.client.post("/skellycam/camera/group/all/record/stop")

    # ----- state -----

    def group_or_none(self):
        groups = list(self.manager.camera_groups.values())
        return groups[0] if groups else None

    @property
    def group(self):
        group = self.group_or_none()
        assert group is not None, "no camera group"
        return group

    def status(self, camera_id):
        return self.group.cameras.orchestrator.camera_statuses[camera_id].serialize()

    def state(self, camera_id):
        return self.status(camera_id).get("state")

    def ring_name(self, camera_id):
        return self.group.ring_infos[camera_id].jpeg_ring_name

    def worker(self, camera_id):
        return self.group.cameras.camera_workers[camera_id]

    def wait(self, predicate, what, timeout=WAIT_TIMEOUT_S):
        deadline = time.monotonic() + timeout
        while True:
            try:
                if predicate():
                    return
            except (KeyError, AssertionError):
                pass
            assert time.monotonic() < deadline, f"timed out: {what}"
            time.sleep(0.005)

    def wait_state(self, camera_id, *states, timeout=WAIT_TIMEOUT_S):
        self.wait(lambda: self.state(camera_id) in states, f"camera {camera_id} in {states}", timeout)

    def wait_clock(self, seconds, what="virtual time"):
        """Wait (real time) until the virtual clock moved `seconds` from now."""
        target = self.clock.now_ns() + round(seconds * 1e9)
        self.wait(lambda: self.clock.now_ns() >= target, what)

    def close(self):
        try:
            self.client.delete("/skellycam/camera/group/close/all")
        finally:
            try:
                self.registry.shutdown_all()
            finally:
                self.client.__exit__(None, None, None)


@contextlib.contextmanager
def capture_app(monkeypatch, scripts, *, workers="thread", virtual=None, track=False, **factory_args):
    """A `CaptureApp` with one fake camera for each script. THREAD workers use a VirtualClock
    unless `virtual=False`. `track=True` gives a StateTracker as `app.tracker`."""
    if virtual is None:
        virtual = workers == "thread"
    tracker = StateTracker() if track else None
    on_read = tracker if track else factory_args.pop("on_read", None)
    factory = FakeSourceFactory(list(scripts), clock=VirtualClock() if virtual else None, on_read=on_read,
                                **factory_args)
    app = CaptureApp(monkeypatch, factory, workers=workers)
    app.tracker = tracker
    try:
        yield app
    finally:
        app.close()


@contextlib.contextmanager
def one_camera(monkeypatch, script, *, track=False, until=("ready", "failed"), **config):
    """One fake camera, applied. Waits until it is in a state of `until` (`ready` or `failed`). Gives (app,
    camera_id, response). A camera that fails during streaming soon after `ready` must also wait for `dead`:
    on the virtual clock its time in `ready` can be shorter than one poll of `wait_state`."""
    with capture_app(monkeypatch, [script], track=track) as app:
        app.detect()
        camera_id = app.factory.camera_ids[0]
        response = app.apply([app.config(camera_id, **config)])
        assert response.status_code == 200, response.text
        app.wait_state(camera_id, *until)
        yield app, camera_id, response


def ready_app_steps(app, configs=None):
    """Detect, apply and wait until each camera is `ready`. Returns the apply response."""
    app.detect()
    response = app.apply(configs or [app.config(cid) for cid in app.factory.camera_ids])
    assert response.status_code == 200, response.text
    for camera_id in app.factory.camera_ids:
        app.wait_state(camera_id, "ready")
    return response


# ---------------------------------------------------------------------------
# Rings, files and texts
# ---------------------------------------------------------------------------

class RingWatcher:
    """Reads each frame of one JPEG ring in a thread (any worker mode) and keeps
    (frame_number, arrival_ns, source_frame_number, sample_ns)."""

    def __init__(self, name):
        from skellycam.core.ipc.frame_ring import FrameRingReader, ReadResult

        self._result = ReadResult
        self.reader = FrameRingReader.attach(name)
        self.frames = []
        self.skipped = []  # (frame_number, result) of each frame that the watcher could not read, for example LAPPED
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        ok, not_yet = self._result.OK, self._result.NOT_YET_WRITTEN
        newest = self.reader.read_newest()
        next_number = newest.frame_number + 1 if newest.result is ok else 0
        while not self._stop.is_set():
            read = self.reader.read(next_number)
            if read.result is ok:
                self.frames.append((read.frame_number, read.arrival_ns, read.source_frame_number, read.sample_ns))
                next_number += 1
            elif read.result is not_yet:
                time.sleep(0.002)
            elif read.result is self._result.CLOSED:
                return
            else:
                self.skipped.append((next_number, read.result.name))
                next_number += 1

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)
        self.reader.close()

    def largest_gap_s(self, from_ns=0, to_ns=None):
        return self.largest_gap(from_ns, to_ns)[0]

    def largest_gap(self, from_ns=0, to_ns=None):
        """(gap in s, arrival_ns of the frame before the gap) of the largest gap between read frames."""
        times = [f[1] for f in self.frames if f[1] >= from_ns and (to_ns is None or f[1] <= to_ns)]
        return max(((b - a) / 1e9, a) for a, b in zip(times, times[1:])) if len(times) > 1 else (0.0, None)


def ring_exists(name):
    from skellycam.tests.frame_ring.ring_spec import open_raw

    try:
        shm = open_raw(name)
    except FileNotFoundError:
        return False
    shm.close()
    return True


def sfn_gaps(sfns):
    """The sum of the gaps of `source_frame_number` between consecutive taken frames (5.2)."""
    return sum(b - a - 1 for a, b in zip(sfns, sfns[1:]))


def numbers_in(text):
    import re

    return [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", text)]


def stop_line_count(messages, camera_id):
    """The count of the stop line of 5.2 (ADR-HP7D): the camera ID, then `replaced`, then the count."""
    import re

    pattern = re.compile(rf"\b{re.escape(camera_id)}\b.*?\breplaced\b\D*(\d+)", re.IGNORECASE)
    counts = [int(match.group(1)) for message in messages if (match := pattern.search(message))]
    assert len(counts) == 1, f"{len(counts)} stop lines with the replaced count for camera {camera_id}"
    return counts[0]


def slow_text(declared, measured):
    """The reason of a slow camera, 10.4 and camera-requests.md 1.5a."""
    return f"declared {declared:.2f} fps, measured {measured:.2f} fps. Camera is slow. Try adding more light"


# ---------------------------------------------------------------------------
# The OpenCV fake under the shared loop (14.1, T-CAP-39, T-CAP-44, T-CAP-87)
# ---------------------------------------------------------------------------

JPEG_Q90 = [int(cv2.IMWRITE_JPEG_QUALITY), 90]


def opencv_fake_class():
    from skellycam.tests.frame_ring.ring_session import FakeCapture

    class OpenCVFake(FakeCapture):
        """`FakeCapture` of the ring tests with a reported rate, a delivered rate, late grabs and a
        stop (`stop()`: each later grab fails, as after an unplug). It keeps the hash of each image it
        gives and of the q90 JPEG of that image.

        With a `clock`, a grab waits on that clock, not in real time: frame k comes one period after
        frame k - 1, or at once when the loop is later than that. Each grab fails before `fail_until_ns` of
        that clock (a gap of the camera)."""

        def __init__(self, width, height, reported_fps=30.0, delivered_fps=None, late_grabs=(), late_s=0.0,
                     clock=None):
            if delivered_fps is None:
                delivered_fps = reported_fps if reported_fps > 0 else 30.0
            super().__init__(width, height, delivered_fps)
            self.clock, self._period_ns, self._due = clock, round(1e9 / delivered_fps), None
            self.reported_fps = reported_fps
            self.stopped = False
            self.fail_until_ns = 0
            self.late_grabs, self.late_s = late_grabs, late_s
            self.grabs = 0
            self.jpeg_hashes, self.image_hashes = set(), set()

        def get(self, prop_id):
            if prop_id == cv2.CAP_PROP_FPS:
                return float(self.reported_fps)
            return super().get(prop_id)

        def stop(self):
            self.stopped = True

        def grab(self):
            if self.clock is not None:
                return self._grab_on_clock()
            if self.stopped:
                time.sleep(0.01)
                return False
            if self.grabs in self.late_grabs:
                time.sleep(self.late_s)
            ok = super().grab()
            if ok:
                self.grabs += 1
                self._remember(self._pending)
            return ok

        def _grab_on_clock(self):
            clock = self.clock
            if self.stopped:
                clock.wait_until(clock.now_ns() + 10_000_000)
                return False
            if clock.now_ns() < self.fail_until_ns:
                clock.wait_until(min(clock.now_ns() + 10_000_000, self.fail_until_ns))
                return False
            if self.grabs in self.late_grabs:
                clock.wait_until(clock.now_ns() + round(self.late_s * 1e9))
            now = clock.now_ns()
            self._due = now if self._due is None else max(self._due + self._period_ns, now)
            clock.wait_until(self._due)
            self._mock._frame_count += 1
            self._pending = self._mock._generate_frame()
            self.grabs += 1
            self._remember(self._pending)
            return True

        def read(self, image=None):
            if self.stopped:
                time.sleep(0.01)
                return False, None
            ok, frame = super().read(image)
            if ok:
                self.grabs += 1
                self._remember(frame)
            return ok, frame

        def _remember(self, image):
            self.image_hashes.add(digest(image))
            self.jpeg_hashes.add(digest(cv2.imencode(".jpg", image, JPEG_Q90)[1].tobytes()))

    return OpenCVFake


class OpenCVFakeFactory:
    """A `source_factory` (ADR-HP7D) that gives the product `OpenCVSource`. The tests replace
    `opencv_source.create_cv2_video_capture` with the OpenCV fake (ADR-HP7D). A `VirtualClock`
    (THREAD workers only): the OpenCV source stamps the arrival itself with `time.perf_counter_ns`, so
    the factory replaces the `time` name of `opencv_source` with that clock (ADR-BM73). Thus the rate
    check measures the rate of the fake, not the speed of the machine.

    Its detection result has `supported_modes = []`, as `cv2_enumerate_cameras` gives on Linux and
    macOS, so the whole-request check compares the requested rates (7.5, ADR-HP7D item 2).
    `fake_args` go to each OpenCV fake; `per_camera` gives other arguments to camera i;
    `fail_open` holds the indexes of cameras whose open fails."""

    def __init__(self, monkeypatch, count=1, width=640, height=480, per_camera=None, fail_open=(), **fake_args):
        from skellycam.tests.capture.fake_source import FakeScript, fake_link, spec_camera_id

        opencv_source = product("skellycam.core.camera.capture.opencv_source")
        self.clock, self.on_read = VirtualClock(), None
        clock = self.clock
        monkeypatch.setattr(opencv_source, "time", SimpleNamespace(
            perf_counter_ns=clock.now_ns, perf_counter=lambda: clock.now_ns() / 1e9,
            sleep=lambda seconds: clock.wait_until(clock.now_ns() + round(seconds * 1e9))))
        self.scripts = [FakeScript(modes=((width, height, 30, 1, "MJPG"),)) for _ in range(count)]
        self.links = [fake_link(index) for index in range(count)]
        self.camera_ids = [spec_camera_id(link) for link in self.links]
        self.opens = {camera_id: 0 for camera_id in self.camera_ids}
        self.captures = {}
        self._fake_class, self._fake_args = opencv_fake_class(), fake_args
        self._per_camera, self._fail_open = per_camera or {}, fail_open
        self._source_class = opencv_source.OpenCVSource
        monkeypatch.setattr(opencv_source, "create_cv2_video_capture", self._create)

    def _create(self, config):
        self.opens[config.camera_id] += 1
        index = self.camera_ids.index(config.camera_id)
        if index in self._fail_open:
            raise RuntimeError(f"the fake camera {config.camera_id} cannot open")
        args = {**self._fake_args, **self._per_camera.get(index, {})}
        capture = self._fake_class(config.resolution.width, config.resolution.height, clock=self.clock, **args)
        self.captures[config.camera_id] = capture
        return capture, config

    def __call__(self, config):
        return self._source_class(config)

    def device_infos(self):
        from skellycam.core.device_detection.detect_cameras_devices import CameraDeviceInfo

        product("skellycam.core.camera.capture.modes")
        return [CameraDeviceInfo(index=index, name=f"Fake OpenCV camera {index}", vendor_id=0xFEED, product_id=index,
                                 path=link, supported_modes=[]) for index, link in enumerate(self.links)]


# ---------------------------------------------------------------------------
# The interim relay (5.8) and the recording files
# ---------------------------------------------------------------------------

def parse_relay(message):
    """A relay message in the wire format of `frontend_payload_bytearray.py`:
    (frame number of the message header, {camera_id: frame number of its frame header})."""
    from skellycam.core.types.frontend_payload_bytearray import (
        FRONTEND_FRAME_HEADER_DTYPE, FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE)

    data = bytes(message)
    header = np.frombuffer(data[:FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE.itemsize], FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE)[0]
    offset, frames = FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE.itemsize, {}
    for _ in range(int(header["number_of_cameras"])):
        frame = np.frombuffer(data[offset:offset + FRONTEND_FRAME_HEADER_DTYPE.itemsize], FRONTEND_FRAME_HEADER_DTYPE)[0]
        offset += FRONTEND_FRAME_HEADER_DTYPE.itemsize + int(frame["jpeg_string_length"])
        frames[frame["camera_id"].decode("ascii")] = int(frame["frame_number"])
    return int(header["frame_number"]), frames


def take_manifest(directory, name="take"):
    """The manifest of a take of the take recorder (recorder.md 6.6)."""
    return json.loads((Path(directory) / name / "recording_manifest.json").read_text(encoding="utf-8"))


def take_files(directory, name="take"):
    """{camera_id: (camera file, timing sidecar)} of a take. The camera key starts with the camera ID (6.2)."""
    folder = Path(directory) / name
    return {item["camera_key"][:4]: (folder / item["video"], folder / item["timing"])
            for item in take_manifest(directory, name)["cameras"]}


def take_rows(directory, camera_id, name="take"):
    """The rows of the timing sidecar of one camera (recorder.md 6.5), by the strict read of the product."""
    from skellycam.core.take_recorder.sidecar import read_strict

    return read_strict(take_files(directory, name)[camera_id][1]).rows


def take_warnings(directory, code, name="take"):
    return [w for w in take_manifest(directory, name)["warnings"] if w["code"] == code]


def camera_key_of(directory, camera_id, name="take"):
    return next(item["camera_key"] for item in take_manifest(directory, name)["cameras"]
                if item["camera_key"].startswith(camera_id))


def placeholders_to_the_stop(directory, camera_id, name="take"):
    """A camera that died during a take (recorder.md 7.3): one `camera_dead` warning that names its last row
    with an image, and `missing` rows with a placeholder block from there to the end of the take.
    Returns (the warning, the rows)."""
    from skellycam.core.take_recorder.sidecar import MISSING

    rows = take_rows(directory, camera_id, name)
    key = camera_key_of(directory, camera_id, name)
    dead = [w for w in take_warnings(directory, "camera_dead", name) if w["camera_key"] == key]
    assert len(dead) == 1, dead
    last = max((row.frame for row in rows if not row.flags & MISSING), default=None)
    assert dead[0]["detail"].startswith(f"last_frame={'none' if last is None else last} "), dead
    after = rows[(last + 1) if last is not None else 0:]
    assert after and all(row.flags & MISSING and row.byte_size for row in after), "no placeholders to the stop"
    assert len(block_payloads(directory, camera_id, name)) == len(rows), "the file is not closed with a block per row"
    return dead[0], rows


def block_payloads(directory, camera_id, name="take"):
    """The payload of each complete block of the camera file of one camera (the walker of the recorder tests)."""
    from skellycam.tests.take_recorder.ebml import payloads

    return payloads(take_files(directory, name)[camera_id][0])


class StateWatcher:
    """Polls the status of one camera every 2 ms in a thread (any worker mode). Keeps the first
    `perf_counter_ns` time of each state (the virtual time with a `VirtualClock`), the first time of a
    failure object, and the last worker object of the camera."""

    def __init__(self, app, camera_id):
        self.app, self.camera_id = app, camera_id
        clock = getattr(app, "clock", None)
        virtual = clock is not None and clock.virtual
        self._now_ns = clock.now_ns if virtual else time.perf_counter_ns
        self.first = {}
        self.failure_ns, self.failure = None, None
        self.worker = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                group = self.app.group_or_none()
                if group is not None:
                    worker = group.cameras.camera_workers.get(self.camera_id)
                    if worker is not None:
                        self.worker = worker
                    status = group.cameras.orchestrator.camera_statuses[self.camera_id].serialize()
                    now = self._now_ns()
                    self.first.setdefault(status.get("state"), now)
                    if status.get("failure") and self.failure_ns is None:
                        self.failure_ns, self.failure = now, status["failure"]
            except Exception:
                pass
            time.sleep(0.002)

    def stop(self):
        self._stop.set()
        self._thread.join(5)


def wait_exit(worker, timeout=WAIT_TIMEOUT_S):
    """Wait until a camera worker ends. Returns the `perf_counter_ns` time when it was seen ended."""
    deadline = time.monotonic() + timeout
    while worker.is_alive():
        assert time.monotonic() < deadline, f"the worker {worker.camera_id} did not end"
        time.sleep(0.002)
    return time.perf_counter_ns()
