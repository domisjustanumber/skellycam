"""Test helpers of the capture timings tests (specs/capture-timings.md 10.1). No camera and no real wait.

- `VClock`: a virtual clock. A read gives the time; only `advance` moves it. The camera loop reads it through
  `camera_loop.perf_counter_ns`, so each bracket reads it through its `TimingControl`.
- `ScriptSource`: a pull source that moves the clock by a scripted time in each read. With `copy_ns` it also
  writes the callback step `camera_sample_copy`, as a Media Foundation fake (the real bracket is tested on the
  real source with the stand-ins of `mf_standins.py`).
- `make_loop`: a real `CameraLoop` with stub IPC, gate and ring, driven by the test thread with `_pass()`.
- `slow`: wrap a function so that each call moves the clock by a fixed time.

Each product module is imported inside a helper call, so that a missing module fails the test, not the
collection.
"""

import importlib
import multiprocessing
import queue
import threading
from types import SimpleNamespace

import numpy as np

from skellycam.tests.capture.fake_source import synthetic_jpeg, with_comment

CAMERA_ID = "a1b2"
GROUP_ID = "g1"
START_NS = 10**12
MS = 1_000_000


def timings():
    return importlib.import_module("skellycam.core.capture_timings")


def loop_module():
    return importlib.import_module("skellycam.core.camera.capture.camera_loop")


class VClock:
    """Virtual time in nanoseconds. Only `advance` moves it."""

    def __init__(self, start=START_NS):
        self.t = start
        self._lock = threading.Lock()

    def now(self):
        return self.t

    def advance(self, ns):
        with self._lock:
            self.t += ns


def slow(clock, function, ns):
    """`function` with `ns` of virtual time in each call."""
    def wrapped(*args, **kwargs):
        clock.advance(ns)
        return function(*args, **kwargs)
    return wrapped


def count_reads(monkeypatch):
    """The thread ident of each call of `TimingControl.clock()` (5.1: only a bracket calls it)."""
    control = timings().TimingControl
    calls = []
    original = control.clock

    def clock(self):
        calls.append(threading.get_ident())
        return original(self)

    monkeypatch.setattr(control, "clock", clock)
    return calls


JPEG = synthetic_jpeg(64, 48)


class ScriptSource:
    """A pull source. Each read moves the clock by `read_ns` and gives a frame; `empty` is a list of the read
    calls (0 is the first) that give no frame. `copy_ns`: the fake callback copy of each frame."""

    name = "fake"
    searches = False

    def __init__(self, clock, *, read_ns=30 * MS, empty=(), copy_ns=None, bgr=False, diagnostics=None,
                 timing_steps=None, on_read=None):
        self.clock, self.read_ns, self.empty, self.copy_ns, self.bgr = clock, read_ns, set(empty), copy_ns, bgr
        self.reads = self.frames = 0
        self.extra_diagnostics = diagnostics or {}
        self.diagnostics_ns = 0
        self.on_read = on_read
        if timing_steps is not None:
            self.timing_steps = timing_steps
        self.closed = False

    def open(self, request):
        from skellycam.core.camera.capture.source import OpenedMode
        return OpenedMode(width=64, height=48, fps_num=30, fps_den=1, format="MJPG", device_path="fake")

    def set_controls(self, changes):
        from skellycam.core.camera.capture.source import ControlValue
        value = changes["exposure"].value if "exposure" in changes else -7
        return {"exposure": ControlValue(present=True, auto=False, value=value)}

    def exposure_range(self):
        return None

    def read_frame(self, timeout_s):
        from skellycam.core.camera.capture.source import CapturedFrame
        from skellycam.core.ipc.frame_ring import NO_SAMPLE_NS

        call, self.reads = self.reads, self.reads + 1
        if self.on_read is not None:
            self.on_read(self, call)
        self.clock.advance(self.read_ns)
        if call in self.empty:
            return None
        number, self.frames = self.frames, self.frames + 1
        if self.copy_ns is not None:  # the callback of a push source: its own bracket and its own StepSet
            steps = self.timing_set
            on = steps.control.on
            if on:
                t0 = steps.control.clock()
            self.clock.advance(self.copy_ns)
            if on:
                steps.add("camera_sample_copy", steps.control.clock() - t0)
        if self.bgr:
            payload, fmt, length = np.full((48, 64, 3), 128, np.uint8), "BGR", 0
        else:
            payload = with_comment(JPEG, number)
            fmt, length = "MJPG", len(payload)
        return CapturedFrame(payload=payload, format=fmt, arrival_ns=self.clock.now(), sample_ns=NO_SAMPLE_NS,
                             delivered_len=length, driver_error=False, source_frame_number=number,
                             discontinuity=False)

    def diagnostics(self):
        from skellycam.core.camera.capture.source import empty_diagnostics
        self.clock.advance(self.diagnostics_ns)
        return {**empty_diagnostics("fake"), **self.extra_diagnostics}

    @property
    def replaced_count(self):
        return 0

    def close(self, restore=True):
        self.closed = True


class FakeRing:
    """A JPEG or BGR ring writer: each write moves the clock by `write_ns`."""

    def __init__(self, clock, write_ns=0, name="ring", shape=(48, 64, 3)):
        self.clock, self.write_ns, self.name, self.shape = clock, write_ns, name, shape
        self.writes = []
        self._counters = [0] * 8

    def write(self, payload, **fields):
        self.clock.advance(self.write_ns)
        self.writes.append(fields)

    def set_skipped_count(self, count):
        pass

    def close(self):
        pass


class Gate:
    """The gate and the take frame rule of the orchestrator. `script`: a list of (granted, ns) for the next
    passes; an empty script grants with no time. `record`: True while the take records each frame."""

    def __init__(self, clock, status):
        self.clock = clock
        self.camera_statuses = {CAMERA_ID: status}
        self.script = []
        self.record = False
        self.recorded = 0  # the frames of the take: its frame count at the end
        self.finish_next = False
        self.first_recording_frame_number = SimpleNamespace(value=-1)
        self.last_recording_frame_number = multiprocessing.Value("q", -1)
        self.last_frame = -1

    def should_grab_by_id(self, camera_id):
        granted, ns = self.script.pop(0) if self.script else (True, 0)
        self.clock.advance(ns)
        return granted

    def should_record_frame_number(self, frame_number):
        finish, self.finish_next = self.finish_next, False
        self.recorded += self.record
        return self.record, finish

    def largest_gate_count(self):
        return -1

    def take_frame_count(self):
        return self.recorded


class Topic:
    def __init__(self):
        self.messages = []
        self.subscriptions = ()

    def publish(self, message, print_log=False):
        self.messages.append(message)


class StubCapture:
    """A `cv2.VideoCapture` for the real OpenCV source: `grab` and `retrieve` take scripted virtual times."""

    def __init__(self, clock, grab_ns, retrieve_ns):
        self.clock, self.grab_ns, self.retrieve_ns = clock, grab_ns, retrieve_ns

    def grab(self):
        self.clock.advance(self.grab_ns)
        return True

    def retrieve(self):
        self.clock.advance(self.retrieve_ns)
        return True, np.full((48, 64, 3), 128, np.uint8)

    def release(self):
        pass


def opencv_source(monkeypatch, clock, grab_ns=20 * MS, retrieve_ns=5 * MS):
    """The real `OpenCVSource` on a `StubCapture`, with its module time on the virtual clock."""
    import time

    from skellycam.core.camera.capture import opencv_source as module
    from skellycam.core.camera.config.camera_config import CameraConfig

    monkeypatch.setattr(module, "time", SimpleNamespace(perf_counter_ns=clock.now, perf_counter=lambda: clock.now() / 1e9,
                                                        sleep=time.sleep))
    source = module.OpenCVSource(CameraConfig(camera_id=CAMERA_ID, camera_index=0))
    source._capture = StubCapture(clock, grab_ns, retrieve_ns)
    return source


def make_loop(monkeypatch, clock, source, *, bgr_ring=False, state="ready", ring_ns=0, config=None, on=False):
    """A real `CameraLoop` in the state `state`, with `source` as its open source, a fake JPEG ring and stub IPC.
    `on`: the switch is on when the loop starts. `loop.diagnostics` holds each `DiagnosticsMessage`. Nothing runs
    until the test calls the loop."""
    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera_group.camera_status import CameraStatus
    from skellycam.core.ipc.pubsub.pubsub_manager import TopicTypes

    module = loop_module()
    monkeypatch.setattr(module, "perf_counter_ns", clock.now)
    status = CameraStatus()
    status.log_capture_times.value = on
    gate = Gate(clock, status)
    topics = {name: Topic() for name in (TopicTypes.DIAGNOSTICS, TopicTypes.RECORDING_FINISHED,
                                         TopicTypes.EXTRACTED_CONFIG)}
    ipc = SimpleNamespace(group_id=GROUP_ID, should_continue=True, running=True,
                          pubsub=SimpleNamespace(topics=topics), report_setup_failure=lambda report: None)
    config = config or CameraConfig(camera_id=CAMERA_ID, camera_index=0, exposure_mode="MANUAL", exposure=-7,
                                    bgr_ring=bgr_ring)
    loop = module.CameraLoop(lambda _config: source, config, ipc, gate, queue.Queue(), queue.Queue(), queue.Queue())
    loop.gate, loop.diagnostics = gate, topics[TopicTypes.DIAGNOSTICS].messages
    loop.finished = topics[TopicTypes.RECORDING_FINISHED].messages
    loop.source = loop._new_source(config)
    loop.ring_writer = FakeRing(clock, ring_ns)
    loop.started, loop.stage = True, "streaming"
    loop.last_arrival = clock.now()
    loop.next_diagnostics_ns = clock.now() + module.DIAGNOSTICS_INTERVAL_NS
    status.set_state(state)
    return loop


def switch_on(loop):
    """The switch goes on, and the loop applies it at a publish (2 item 4): the first window starts."""
    loop.status.log_capture_times.value = True
    loop._publish_diagnostics()


def frames(loop, count):
    """`count` frames through the loop; each pass that gives no frame also counts as a pass."""
    start = loop.gate_count
    passes = 0
    while loop.gate_count < start + count:
        loop._pass()
        passes += 1
        assert passes < 10 * count + 10, "the loop takes no frame"


def summary(loop):
    """End the window with a publish of the loop thread; the summary of that publish."""
    loop._publish_diagnostics()
    return loop.diagnostics[-1].timings


def take_spec(tmp_path, queue_size=90, camera_id=CAMERA_ID):
    from skellycam.core.take_recorder.take import CameraTakeSpec
    return CameraTakeSpec(camera_id=camera_id, mkv_path=tmp_path / f"{camera_id}.mkv",
                          csv_path=tmp_path / f"{camera_id}.csv", header=(), take_start_host_ns=0, num=30, den=1,
                          width=64, height=48, layout=None, queue_size=queue_size, stall_limit_s=10.0)


def start_take(loop, tmp_path, **kwargs):
    """A take that records each frame from now (recorder.md 10 item 5), with a real camera writer."""
    loop.gate.first_recording_frame_number.value = loop.gate_count + 1
    loop._start_take(take_spec(tmp_path, **kwargs))
    assert loop.take_writer is not None, loop.status.info_dict().get("writer_failure")
    loop.gate.record = True


def end_take(loop):
    loop.gate.record = False
    loop.gate.last_frame = loop.gate_count
    loop._end_take()
