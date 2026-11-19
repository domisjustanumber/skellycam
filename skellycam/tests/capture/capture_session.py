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
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from skellycam.tests.capture.fake_source import FakeSourceFactory, VirtualClock

LOOP_MODULE = "skellycam.core.camera.capture.camera_loop"
SOURCE_MODULE = "skellycam.core.camera.capture.source"
WAIT_TIMEOUT_S = 60.0
STATES = ("starting", "waiting", "failed", "checking", "too_slow", "ready", "recording", "dead")


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
    """Tell the virtual clock when a camera loop waits at the lockstep gate (5.2)."""
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator

    original = CameraOrchestrator.should_grab_by_id

    def should_grab_by_id(self, camera_id):
        result = original(self, camera_id)
        clock.gate(not result)
        return result

    monkeypatch.setattr(CameraOrchestrator, "should_grab_by_id", should_grab_by_id)


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
    """Class-level spies on the frame path (THREAD workers): JPEG and BGR ring writes, the old
    recorder, the hand-over to the decode stage and `cv2.imdecode`. Each event has a sequence
    number and a hash of its payload or image; `keep_payloads` also keeps each JPEG payload.
    `fail_jpeg_write(event)` can make a JPEG ring write raise."""

    def __init__(self, monkeypatch, app=None, keep_payloads=False):
        from skellycam.core.ipc.frame_ring import DecodeInput, FrameRingWriter
        from skellycam.core.ipc.frame_ring import decode as decode_module
        from skellycam.core.recorders.videos.video_recorder import VideoRecorder

        self.app = app
        self.keep_payloads = keep_payloads
        self.events = []
        self.fail_jpeg_write = None
        self._seq = 0
        self._lock = threading.Lock()
        spies = self
        write, record_frame = FrameRingWriter.write, VideoRecorder.record_frame
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

        def spy_record_frame(recorder, frame):
            image = frame.image[0]
            spies._add("record", camera=recorder.camera_id, frame_number=int(frame.frame_metadata.frame_number[0]),
                       arrival_ns=int(frame.frame_metadata.timestamps.post_frame_grab_ns[0]),
                       hash=digest(image))
            return record_frame(recorder, frame)

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
        monkeypatch.setattr(VideoRecorder, "record_frame", spy_record_frame)
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

    def __init__(self, monkeypatch, factory, *, workers="thread"):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import skellycam.api.http.cameras.camera_router as camera_router
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
        if isinstance(factory.on_read, StateTracker):
            factory.on_read.app = self
        self.kill = multiprocessing.Value("b", False)
        mode = WorkerMode.THREAD if workers == "thread" else WorkerMode.PROCESS
        self.registry = WorkerRegistry(global_kill_flag=self.kill, worker_mode=mode)
        self.manager = CameraGroupManager(global_kill_flag=self.kill, worker_registry=self.registry,
                                          source_factory=factory)
        self._router = camera_router
        monkeypatch.setattr(camera_router, "get_or_create_camera_group_manager", lambda app: self.manager)
        monkeypatch.setattr(camera_router, "detect_available_cameras",
                            lambda *args, **kwargs: self.factory.device_infos())
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

    def apply(self, configs):
        """POST /camera/group/apply. `configs`: CameraConfig objects or a dict by camera_id."""
        if not isinstance(configs, dict):
            configs = {config.camera_id: config for config in configs}
        body = {"camera_configs": {cid: config.model_dump(mode="json") for cid, config in configs.items()}}
        return self.client.post("/skellycam/camera/group/apply", json=body)

    def apply_all(self, **changes):
        response = self.apply([self.config(cid, **changes) for cid in self.factory.camera_ids])
        assert response.status_code == 200, response.text
        return response

    def record_start(self, directory, name="take"):
        return self.client.post("/skellycam/camera/group/all/record/start",
                                json={"recording_name": name, "recording_directory": str(directory)})

    def record_stop(self):
        return self.client.get("/skellycam/camera/group/all/record/stop")

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
def one_camera(monkeypatch, script, *, track=False, **config):
    """One fake camera, applied. Waits until it is `ready` or `failed`. Gives (app, camera_id, response)."""
    with capture_app(monkeypatch, [script], track=track) as app:
        app.detect()
        camera_id = app.factory.camera_ids[0]
        response = app.apply([app.config(camera_id, **config)])
        assert response.status_code == 200, response.text
        app.wait_state(camera_id, "ready", "failed")
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
                next_number += 1

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)
        self.reader.close()

    def largest_gap_s(self, from_ns=0, to_ns=None):
        times = [f[1] for f in self.frames if f[1] >= from_ns and (to_ns is None or f[1] <= to_ns)]
        return max((b - a for a, b in zip(times, times[1:])), default=0) / 1e9


def ring_exists(name):
    from skellycam.tests.frame_ring.ring_spec import open_raw

    try:
        shm = open_raw(name)
    except FileNotFoundError:
        return False
    shm.close()
    return True


def read_csv(path):
    """A timing CSV as (header, rows of strings)."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    return header, [line.split(",") for line in lines[1:] if line]


def column(path, name):
    header, rows = read_csv(path)
    index = header.index(name)
    return [row[index] for row in rows]


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
    """The reason of a slow camera, 10.4."""
    return (f"declared {declared:.2f} fps, measured {measured:.2f} fps. Add light or shorten the exposure, "
            f"or choose a rate that the camera reaches.")


# ---------------------------------------------------------------------------
# The OpenCV fake under the shared loop (14.1, T-CAP-39, T-CAP-44, T-CAP-87)
# ---------------------------------------------------------------------------

JPEG_Q90 = [int(cv2.IMWRITE_JPEG_QUALITY), 90]


def opencv_fake_class():
    from skellycam.tests.frame_ring.ring_session import FakeCapture

    class OpenCVFake(FakeCapture):
        """`FakeCapture` of the ring tests with a reported rate and late grabs. It keeps the hash of
        each image it gives and of the q90 JPEG of that image."""

        def __init__(self, width, height, reported_fps=30.0, late_grabs=(), late_s=0.0):
            super().__init__(width, height, 30.0)
            self.reported_fps = reported_fps
            self.late_grabs, self.late_s = late_grabs, late_s
            self.grabs = 0
            self.jpeg_hashes, self.image_hashes = set(), set()

        def get(self, prop_id):
            if prop_id == cv2.CAP_PROP_FPS:
                return float(self.reported_fps)
            return super().get(prop_id)

        def grab(self):
            if self.grabs in self.late_grabs:
                time.sleep(self.late_s)
            ok = super().grab()
            if ok:
                self.grabs += 1
                self._remember(self._pending)
            return ok

        def read(self, image=None):
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
    `opencv_source.create_cv2_video_capture` with the OpenCV fake (ADR-HP7D). Real time."""

    def __init__(self, monkeypatch, count=1, width=640, height=480, **fake_args):
        from skellycam.tests.capture.fake_source import FakeScript, fake_link, spec_camera_id

        opencv_source = product("skellycam.core.camera.capture.opencv_source")
        self.clock, self.on_read = None, None
        self.scripts = [FakeScript(modes=((width, height, 30, 1, "MJPG"),)) for _ in range(count)]
        self.links = [fake_link(index) for index in range(count)]
        self.camera_ids = [spec_camera_id(link) for link in self.links]
        self.opens = {camera_id: 0 for camera_id in self.camera_ids}
        self.captures = {}
        self._fake_class, self._fake_args = opencv_fake_class(), fake_args
        self._source_class = opencv_source.OpenCVSource
        monkeypatch.setattr(opencv_source, "create_cv2_video_capture", self._create)

    def _create(self, config):
        self.opens[config.camera_id] += 1
        capture = self._fake_class(config.resolution.width, config.resolution.height, **self._fake_args)
        self.captures[config.camera_id] = capture
        return capture, config

    def __call__(self, config):
        return self._source_class(config)

    def device_infos(self):
        from skellycam.tests.capture.fake_source import FakeSourceFactory

        infos = FakeSourceFactory.device_infos(self)
        return infos


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


def recording_info(directory, name="take"):
    from skellycam.core.recorders.videos.recording_info import RecordingInfo

    return RecordingInfo(recording_name=name, recording_directory=str(directory))


def recording_info_json(directory, name="take"):
    return json.loads(Path(recording_info(directory, name).recording_info_path).read_text(encoding="utf-8"))


def video_frame_count(directory, camera_id, name="take"):
    """The frames that OpenCV reads from the video of one camera (0 when no file is readable)."""
    videos = [p for p in Path(recording_info(directory, name).videos_folder).iterdir() if camera_id in p.name]
    assert len(videos) == 1, f"videos of camera {camera_id}: {videos}"
    capture = cv2.VideoCapture(str(videos[0]))
    count = 0
    while capture.read()[0]:
        count += 1
    capture.release()
    return count


class StateWatcher:
    """Polls the status of one camera every 2 ms in a thread (any worker mode). Keeps the first
    `perf_counter_ns` time of each state, the first time of a failure object, and the last worker
    object of the camera."""

    def __init__(self, app, camera_id):
        self.app, self.camera_id = app, camera_id
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
                    now = time.perf_counter_ns()
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
