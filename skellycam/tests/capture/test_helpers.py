"""Self-tests of the test helpers: the fake source, the clocks, the spies and the text helpers.

These tests pass before the product code of phase 3 exists. They give the fake stand-in names for
the product names of ADR-HP7D, with the rules of spec sections 4.3 and 7.5 written here. Thus a
failure of a T-CAP test comes from the product, not from a helper.
"""

import logging
import multiprocessing
import pickle
import threading
import time
from dataclasses import dataclass, replace
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from skellycam.core.ipc.frame_ring import NO_SAMPLE_NS, FrameRingCreator, FrameRingWriter, PixelFormat, check_jpeg
from skellycam.tests.capture import capture_session as cs
from skellycam.tests.capture.fake_source import (
    FakeLog, FakeScript, FakeSource, FakeSourceFactory, RealClock, VirtualClock, fake_link, spec_camera_id,
    synthetic_jpeg, with_comment)


# ---------------------------------------------------------------------------
# Stand-ins for the product names (ADR-HP7D)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StandInFrame:
    payload: object
    format: str
    arrival_ns: int
    sample_ns: int
    delivered_len: int
    driver_error: bool
    source_frame_number: int
    discontinuity: bool


@dataclass(frozen=True)
class StandInMode:
    width: int
    height: int
    fps_num: int
    fps_den: int
    format: str
    device_path: str


@dataclass(frozen=True)
class StandInNativeMode:
    width: int
    height: int
    fps_num: int
    fps_den: int
    format: str


@dataclass(frozen=True)
class StandInControlValue:
    present: bool
    auto: bool
    value: int | None


@dataclass(frozen=True)
class StandInSetting:
    auto: bool
    value: int | None


class StandInFailure(Exception):
    def __init__(self, stage, reason, *, hung=False):
        super().__init__(reason)
        self.stage, self.reason, self.hung = stage, reason, hung


class StandInPlace:
    """The rules of 4.3: newest wins, a replaced frame counts, its discontinuity moves on, and an
    error marker waits behind a frame that waits; `take` then raises at the next call [agent 66]."""

    def __init__(self):
        self._condition = threading.Condition()
        self._item = None
        self._error = None
        self.replaced = 0

    def put(self, frame):
        with self._condition:
            if self._item is not None:
                self.replaced += 1
                if self._item.discontinuity:
                    frame = replace(frame, discontinuity=True)
            self._item = frame
            self._condition.notify()

    def put_error(self, failure):
        with self._condition:
            self._error = failure
            self._condition.notify()

    def take(self, timeout_s):
        with self._condition:
            if self._item is None and self._error is None:
                self._condition.wait(timeout_s)
            item, self._item = self._item, None
            if item is None and self._error is not None:
                raise self._error
            return item


def stand_in_choose_mode(native, request):
    sized = [m for m in native if (m.width, m.height, m.format) == (request.width, request.height, "MJPG")]
    rate = request.framerate
    if rate in (-1, 0):
        thirty = [m for m in sized if abs(m.fps_num / m.fps_den - 30) < 0.5]
        return (thirty or sorted(sized, key=lambda m: -m.fps_num / m.fps_den))[0]
    near = [m for m in sized if abs(m.fps_num / m.fps_den - rate) <= 0.5]
    if not near:
        raise StandInFailure("set mode", "no such mode")
    return min(near, key=lambda m: abs(m.fps_num / m.fps_den - rate))


STAND_INS = SimpleNamespace(
    CapturedFrame=StandInFrame, OpenedMode=StandInMode, ControlValue=StandInControlValue,
    CaptureFailure=StandInFailure, WaitingPlace=StandInPlace, FIRST_FRAME_TIMEOUT_S=5.0,
    BOUNDED_CALL_LIMIT_S=5.0, NativeMode=StandInNativeMode, choose_mode=stand_in_choose_mode,
    NO_SAMPLE_NS=NO_SAMPLE_NS)


def request(width=640, height=480, framerate=30.0):
    return SimpleNamespace(camera_id="0", width=width, height=height, framerate=framerate, capture_fourcc="MJPG")


def virtual_source(script=None, **kwargs):
    clock = kwargs.pop("clock", None) or VirtualClock()
    return FakeSource(script or FakeScript(), clock=clock, types=STAND_INS, **kwargs), clock


# ---------------------------------------------------------------------------
# Clocks
# ---------------------------------------------------------------------------

def test_virtual_clock_moves_at_once_for_one_waiting_thread():
    clock = VirtualClock()
    start = time.monotonic()
    clock.wait_until(clock.now_ns() + 10 * 10**9)
    assert clock.now_ns() == VirtualClock.START_NS + 10 * 10**9
    assert time.monotonic() - start < 1.0


def test_virtual_clock_waits_for_each_participant_and_counts_the_gate_as_waiting():
    clock = VirtualClock(fallback_s=10.0)
    order = []
    gate_open = threading.Event()

    def reader(name, step_ms, rounds):
        for _ in range(rounds):
            clock.wait_until(clock.now_ns() + step_ms * 10**6)
            order.append((name, clock.now_ns()))
        if name == "a":
            clock.gate(True)  # waits at the gate: the clock may move for b
            gate_open.wait(5)
            clock.gate(False)
            clock.leave()
        else:
            clock.leave()
            gate_open.set()

    threads = [threading.Thread(target=reader, args=("a", 30, 2)), threading.Thread(target=reader, args=("b", 20, 6))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert not any(thread.is_alive() for thread in threads)
    times = [t for _, t in order]
    assert times == sorted(times), "the clock moved back or a wait returned early"
    assert ("b", VirtualClock.START_NS + 120 * 10**6) in order


def test_virtual_clock_fallback_moves_when_a_participant_does_other_work():
    clock = VirtualClock(fallback_s=0.05)
    busy = threading.Event()
    done = threading.Event()

    def other():
        clock.wait_until(clock.now_ns())  # joins, then does other work without the clock
        busy.set()
        done.wait(5)
        clock.leave()

    thread = threading.Thread(target=other)
    thread.start()
    busy.wait(5)
    start = time.monotonic()
    clock.wait_until(clock.now_ns() + 10**9)
    assert time.monotonic() - start < 2.0
    done.set()
    thread.join(5)


def test_real_clock_waits_real_time():
    clock = RealClock()
    t0 = time.perf_counter()
    clock.wait_until(clock.now_ns() + 50_000_000)
    assert 0.045 <= time.perf_counter() - t0 < 0.5


# ---------------------------------------------------------------------------
# The fake source with virtual time
# ---------------------------------------------------------------------------

def test_fake_open_gives_the_mode_and_the_first_frame():
    source, clock = virtual_source(FakeScript(modes=((640, 480, 30, 1, "MJPG"), (1280, 720, 30, 1, "MJPG"))))
    opened = source.open(request(1280, 720))
    assert (opened.width, opened.height, opened.fps_num, opened.fps_den, opened.format) == (1280, 720, 30, 1, "MJPG")
    assert opened.device_path == source.link
    frame = source.read_frame(1.0)
    assert frame.source_frame_number == 0
    assert frame.arrival_ns == source.log.first_read_sample_ns.value
    image = cv2.imdecode(np.frombuffer(frame.payload, np.uint8), cv2.IMREAD_COLOR)
    assert image.shape == (720, 1280, 3)
    assert source.log.names()[:3] == ["open", "read_sample", "first_frame"]


def test_fake_frames_follow_the_rate_with_unique_valid_jpegs():
    source, clock = virtual_source(FakeScript(rate=25.0))
    source.open(request())
    frames = [source.read_frame(1.0) for _ in range(50)]
    t0 = frames[0].arrival_ns
    assert [f.source_frame_number for f in frames] == list(range(50))
    for k, frame in enumerate(frames):
        assert abs(frame.arrival_ns - (t0 + k * 40_000_000)) <= k  # integer rounding of 1/25 s
        assert frame.sample_ns == frame.arrival_ns - 4_000_000
        assert frame.delivered_len == len(frame.payload)
        assert check_jpeg(frame.payload, delivered_len=len(frame.payload), driver_error=False)[1] == 0
    assert len({f.payload for f in frames}) == 50
    assert clock.now_ns() == frames[-1].arrival_ns


def test_fake_newest_wins_and_counts_replaced_frames():
    source, clock = virtual_source(FakeScript())
    source.open(request())
    clock.advance_to(source.log.frames[0][0] + 4 * 33_333_333 + 1)
    frame = source.read_frame(1.0)
    assert frame.source_frame_number == 4
    assert source.replaced_count == 4
    assert source.read_frame(1.0).source_frame_number == 5


def test_fake_interval_pattern_drop_burst_stall_and_no_sample_time():
    script = FakeScript(intervals_ms=(32, 48), drop_before_frames=(5,), burst=(8, 9), stop_after_frame=12,
                        sample_offset_ms=None)
    source, clock = virtual_source(script)
    source.open(request())
    frames = []
    while True:
        frame = source.read_frame(2.0)
        if frame is None:
            break
        frames.append(frame)
    numbers = [f.source_frame_number for f in frames]
    assert numbers == [0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12], "frame 8 is replaced in the burst"
    arrivals = {f.source_frame_number: f.arrival_ns for f in frames}
    assert arrivals[1] - arrivals[0] == 32_000_000 and arrivals[2] - arrivals[1] == 48_000_000
    assert arrivals[5] - arrivals[4] == 32_000_000 + 48_000_000, "the dropped frame keeps its place in time"
    assert [f.discontinuity for f in frames if f.source_frame_number == 5] == [True]
    assert all(f.sample_ns == NO_SAMPLE_NS for f in frames)
    assert source.replaced_count == 1
    assert clock.now_ns() == arrivals[12] + 2 * 10**9, "the last read waited its full timeout"


def test_fake_device_removed_raises_in_read_frame():
    source, clock = virtual_source(FakeScript(removed_after_frame=3))
    source.open(request())
    numbers = []
    with pytest.raises(StandInFailure) as failure:
        for _ in range(10):
            numbers.append(source.read_frame(1.0).source_frame_number)
    assert numbers == [0, 1, 2, 3]
    assert failure.value.reason == "device removed"
    assert source.removed_frame == 3


def test_fake_discontinuity_moves_to_the_replacing_frame():
    source, clock = virtual_source(FakeScript(discontinuity_frames=(4,), burst=(4, 5)))
    source.open(request())
    numbers = [(f.source_frame_number, f.discontinuity) for f in (source.read_frame(1.0) for _ in range(6))]
    assert (5, True) in numbers and all(n != 4 for n, _ in numbers)


def test_fake_grid_stop_time_rate_window_and_drop():
    clock = VirtualClock()
    clock.advance_to(VirtualClock.START_NS + 1_234_000_000)
    script = FakeScript(align_ms=100.0, stop_at_s=3.0, rate_windows=((2.0, 2.5, 60.0),), drop_at_window_end=True)
    source, _ = virtual_source(script, clock=clock)
    source.open(request())
    frames = []
    while (frame := source.read_frame(2.5)) is not None:
        frames.append(frame)
    seconds = [(f.arrival_ns - VirtualClock.START_NS) / 1e9 for f in frames]
    assert seconds[0] == pytest.approx(1.3), "frame 0 is on the 100 ms grid"
    assert seconds[-1] <= 3.0 < seconds[-1] + 1 / 30
    fast = [b - a for a, b in zip(seconds, seconds[1:]) if 2.0 <= a < 2.5]
    assert fast and all(d == pytest.approx(1 / 60, abs=1e-6) for d in fast)
    dropped = [f for f in frames if f.discontinuity]
    assert len(dropped) == 1 and (dropped[0].arrival_ns - VirtualClock.START_NS) / 1e9 == pytest.approx(2.5 + 1 / 15, abs=1e-6)
    assert all(abs(x * 30 - round(x * 30)) < 1e-4 for x in seconds if x > 2.5), "back on the 30 fps grid"


def test_stand_in_error_marker_waits_behind_a_frame():
    place = StandInPlace()
    frame = StandInFrame(b"", "MJPG", 1, 1, 0, False, 7, False)
    place.put(frame)
    place.put_error(StandInFailure("streaming", "device removed"))
    assert place.take(0.0) is frame
    with pytest.raises(StandInFailure):
        place.take(0.0)


def test_fake_first_frame_timeout_after_five_seconds():
    source, clock = virtual_source(FakeScript(first_frame_delay_s=6.0))
    with pytest.raises(StandInFailure) as failure:
        source.open(request())
    assert failure.value.stage == "first frame"
    assert clock.now_ns() - source.log.first_read_sample_ns.value == 5 * 10**9


def test_fake_open_failure_on_listed_opens_only():
    source, clock = virtual_source(FakeScript(fail_opens=(1,)))
    with pytest.raises(StandInFailure) as failure:
        source.open(request())
    assert (failure.value.stage, failure.value.reason) == ("open", "in use by another program")
    source.open(request())
    assert source.log.opens.value == 2


def test_fake_controls_set_read_back_reset_and_live_faults():
    script = FakeScript(reset_on_stream=(("exposure", -5),), live_set_faults=(None, "error", "readback:-6"),
                        rate_after_change=(20.0,), controls=(("exposure", True, False, -6), ("focus", False, False, 0)))
    source, clock = virtual_source(script)
    source.open(request())
    assert source.set_controls({})["exposure"] == StandInControlValue(True, False, -5), "reset at stream start"
    state = source.set_controls({"exposure": StandInSetting(False, -7)})
    assert state["exposure"].value == -7 and state["focus"] == StandInControlValue(False, False, None)
    assert source.log.first_sfn_after_readback == 1
    with pytest.raises(StandInFailure, match="no focus control"):
        source.set_controls({"focus": StandInSetting(False, 40)})
    for _ in range(95):
        source.read_frame(1.0)
    source.set_controls({"exposure": StandInSetting(False, -6)})  # live change 1: no fault, 20 fps
    a, b = source.read_frame(1.0), source.read_frame(1.0)
    assert b.arrival_ns - a.arrival_ns == 50_000_000
    with pytest.raises(StandInFailure):
        source.set_controls({"exposure": StandInSetting(False, -5)})  # live change 2: error
    assert source.set_controls({})["exposure"].value == -6, "a refused set changes nothing"
    assert source.set_controls({"exposure": StandInSetting(False, -5)})["exposure"].value == -6  # live change 3


def test_fake_brightness_follows_the_exposure():
    source, clock = virtual_source(FakeScript(brightness=((-7, 64), (-6, 128))))
    source.open(request())
    source.read_frame(1.0)  # frame 0 came at the open, before the set
    source.set_controls({"exposure": StandInSetting(False, -7)})
    dark = source.read_frame(1.0)
    source.set_controls({"exposure": StandInSetting(False, -6)})
    bright = source.read_frame(1.0)
    means = [cv2.imdecode(np.frombuffer(f.payload, np.uint8), cv2.IMREAD_COLOR).mean() for f in (dark, bright)]
    assert abs(means[0] - 64) < 2 and abs(means[1] - 128) < 2


def test_fake_hang_raises_after_the_limit_and_leaves_a_stuck_thread():
    source, clock = virtual_source(FakeScript(hang_at="open", hang_armed=True))
    before = threading.active_count()
    with pytest.raises(StandInFailure) as failure:
        source.open(request())
    assert failure.value.hung and failure.value.stage == "open"
    assert clock.now_ns() - VirtualClock.START_NS == 5 * 10**9
    assert source.log.hang_started_ns.value > 0
    assert threading.active_count() == before + 1


def test_fake_hold_waits_until_release_without_stopping_virtual_time():
    source, clock = virtual_source(FakeScript(hold_opens=(1,)))
    result = []
    thread = threading.Thread(target=lambda: result.append(source.open(request())))
    thread.start()
    assert source.holding.wait(5)
    other = threading.Thread(target=lambda: clock.wait_until(clock.now_ns() + 10**9))
    other.start()
    other.join(5)
    assert not other.is_alive(), "a held fake must not stop the clock"
    source.release()
    thread.join(5)
    assert result and result[0].width == 640


def test_fake_triggers_slow_period_cut_off_remove_and_drift():
    source, clock = virtual_source(FakeScript())
    source.open(request())
    source.read_frame(1.0)
    source.slow_period(rate=27.0, seconds=1.0)
    frames = [source.read_frame(1.0) for _ in range(40)]
    intervals = [b.arrival_ns - a.arrival_ns for a, b in zip(frames, frames[1:])]
    assert intervals[0] == round(1e9 / 27) and intervals[-1] == round(1e9 / 30)
    assert source.slow_finished_ns is not None
    source.cut_off_next()
    cut = source.read_frame(1.0)
    assert check_jpeg(cut.payload, delivered_len=len(cut.payload), driver_error=False)[1] != 0
    source.drift(exposure=-5)
    assert source.set_controls({})["exposure"].value == -5
    source.remove_now()
    source.read_frame(1.0)
    with pytest.raises(StandInFailure):
        source.read_frame(1.0)


# ---------------------------------------------------------------------------
# The fake source with real time, the factory and a camera process
# ---------------------------------------------------------------------------

def test_fake_real_time_delivery_thread():
    source = FakeSource(FakeScript(rate=50.0), clock=RealClock(), types=STAND_INS)
    source.open(request())
    frames = [source.read_frame(1.0) for _ in range(10)]
    t0 = time.perf_counter()
    assert all(f is not None for f in frames)
    span = (frames[-1].arrival_ns - frames[0].arrival_ns) / 1e9
    assert abs(span - 9 / 50) < 0.002
    source.stop_now()
    while source.read_frame(0.05) is not None:
        pass
    t0 = time.perf_counter()
    assert source.read_frame(0.2) is None
    assert 0.18 <= time.perf_counter() - t0 < 0.5
    source.close()
    assert source.log.closes.value == 1


def test_factory_ids_links_and_device_infos_follow_the_spec_hash():
    factory = FakeSourceFactory([FakeScript(), FakeScript()], types=STAND_INS, clock=VirtualClock())
    assert factory.links == [fake_link(0), fake_link(1)]
    assert factory.camera_ids == [spec_camera_id(fake_link(0)), spec_camera_id(fake_link(1))]
    assert spec_camera_id(fake_link(0).upper()) == factory.camera_ids[0]
    source = factory(SimpleNamespace(camera_id=factory.camera_ids[1]))
    assert source.link == fake_link(1) and factory.sources[factory.camera_ids[1]] is source


def _child_opens(factory, camera_id, frames):
    source = factory(SimpleNamespace(camera_id=camera_id))
    source.open(request())
    frames.value = sum(source.read_frame(1.0) is not None for _ in range(5))
    source.close()


def test_factory_works_in_a_spawned_camera_process():
    factory = FakeSourceFactory([FakeScript(rate=60.0)], types=STAND_INS)
    context = multiprocessing.get_context("spawn")
    frames = multiprocessing.Value("i", 0)
    process = context.Process(target=_child_opens, args=(factory, factory.camera_ids[0], frames))
    process.start()
    process.join(60)
    assert process.exitcode == 0
    log = factory.logs[factory.camera_ids[0]]
    assert (log.opens.value, log.closes.value, frames.value) == (1, 1, 5)
    assert log.first_read_sample_ns.value > 0


def test_factory_state_drops_live_sources_for_pickling():
    factory = FakeSourceFactory([FakeScript()], types=STAND_INS)
    factory(SimpleNamespace(camera_id=factory.camera_ids[0]))
    assert factory.__getstate__()["sources"] == {}
    with pytest.raises(RuntimeError):  # a Value is pickled only when a process starts
        pickle.dumps(FakeLog())


# ---------------------------------------------------------------------------
# JPEGs, spies, ring watcher and text helpers
# ---------------------------------------------------------------------------

def test_synthetic_jpeg_with_comment_is_a_valid_q90_jpeg():
    base = synthetic_jpeg(320, 240)
    jpeg = with_comment(base, 12)
    assert check_jpeg(jpeg, delivered_len=len(jpeg), driver_error=False)[1] == 0
    decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert np.array_equal(decoded, cv2.imdecode(np.frombuffer(base, np.uint8), cv2.IMREAD_COLOR))


def test_spies_see_ring_writes_and_decodes(monkeypatch):
    spies = cs.Spies(monkeypatch, keep_payloads=True)
    creator = FrameRingCreator.create(camera_id="0", camera_index=0, pixel_format=PixelFormat.JPEG, width=320,
                                      height=240, fps_num=30, fps_den=1)
    writer = FrameRingWriter.attach(creator.name)
    try:
        jpeg = with_comment(synthetic_jpeg(320, 240), 1)
        writer.write(jpeg, frame_number=0, arrival_ns=5, sample_ns=4, source_frame_number=1, flags=0,
                     rotation_cw_deg=0)
        spies.fail_jpeg_write = lambda event: event["frame_number"] == 1
        with pytest.raises(RuntimeError):
            writer.write(jpeg, frame_number=1, arrival_ns=6, sample_ns=5, source_frame_number=2, flags=0,
                         rotation_cw_deg=0)
        spies.fail_jpeg_write = None
        cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        watcher = cs.RingWatcher(creator.name)
        writer.write(jpeg, frame_number=1, arrival_ns=40_000_000, sample_ns=5, source_frame_number=2, flags=0,
                     rotation_cw_deg=0)
        time.sleep(0.1)
        watcher.stop()
    finally:
        writer.close()
        creator.close_and_unlink()
    writes = spies.of("jpeg")
    assert [w["frame_number"] for w in writes] == [0, 1, 1] and writes[1].get("raised")
    assert writes[0]["payload"] == jpeg and writes[0]["hash"] == spies.of("imdecode")[0]["hash"]
    assert watcher.frames == [(1, 40_000_000, 2, 5)]
    assert not cs.ring_exists(creator.name)


def test_text_helpers():
    assert cs.sfn_gaps([3, 4, 6, 10]) == 4
    assert cs.stop_line_count(["camera ab12: 3 frames replaced", "Camera ab12 replaced 7 frames since"], "ab12") == 7
    with pytest.raises(AssertionError):
        cs.stop_line_count(["nothing"], "ab12")
    assert cs.numbers_in("rate 27.40 fps for a1b2") == [27.40, 1.0, 2.0]
    assert cs.slow_text(30, 25.756) == ("declared 30.00 fps, measured 25.76 fps. Add light or shorten the exposure, "
                                        "or choose a rate that the camera reaches.")


def test_log_capture_keeps_records_of_other_threads():
    with cs.capture_logs() as logs:
        thread = threading.Thread(target=lambda: logging.getLogger("x.y").warning("from a thread"))
        thread.start()
        thread.join()
    assert "from a thread" in logs.messages(logging.WARNING)
