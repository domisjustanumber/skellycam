"""The fake capture source of the phase 3 tests (specs/windows-capture.md, sections 4.4 and 16.1).

`FakeSource` has the four calls of section 4.1 and `replaced_count`. A `FakeScript` gives the
native modes, the arrival times, the controls and the faults of one camera. Each frame is a
synthetic JPEG that `cv2.imencode` makes at test time. A JPEG comment segment holds the source frame
number, so each payload is different. No camera and no camera frame is used.

The fake uses the product names of `skellycam.core.camera.capture` (ADR-HP7D). It puts each frame
into `CaptureWaitingPlace` (4.3), and it chooses its mode with `modes.choose_mode` (7.5). Thus a
test with the fake checks the product rules, not rules of the fake. The self-tests give stand-in
names with `types=`.

What the fake does itself, as each source does inside its `open` (section 6): the wait for the
first frame (`FIRST_FRAME_TIMEOUT_S`) and the time limit of a hung call (`BOUNDED_CALL_LIMIT_S`).
A hung call raises `CaptureFailure(..., hung=True)` after the limit, and a stuck thread stays, as
after a bounded call that does not return.

Clocks:

- `RealClock`: `time.perf_counter_ns`. A delivery thread puts each frame at its arrival time.
- `VirtualClock`: virtual time for camera loops that run as threads of one process. A read moves
  the time. The fake puts the frames that are due when the time moves.
"""

import contextlib
import hashlib
import importlib
import multiprocessing
import os
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from types import SimpleNamespace

import cv2
import numpy as np

from skellycam.core.camera.capture.failure_codes import WEDGE_CODES

HOLD_LIMIT_S = 60.0  # a held call continues after this time, so that a failed test cannot hang
MEDIA_FOUNDATION_VIDEO_GUID = "{e5323777-f976-4f5b-9b55-b94699c46e44}"


def product_types():
    """The product names that the fake uses (ADR-HP7D). A missing product module raises here."""
    source = importlib.import_module("skellycam.core.camera.capture.source")
    modes = importlib.import_module("skellycam.core.camera.capture.modes")
    ring = importlib.import_module("skellycam.core.ipc.frame_ring")
    return SimpleNamespace(
        CapturedFrame=source.CapturedFrame, OpenedMode=source.OpenedMode,
        ControlValue=source.ControlValue, CaptureFailure=source.CaptureFailure,
        WaitingPlace=source.CaptureWaitingPlace, FIRST_FRAME_TIMEOUT_S=source.FIRST_FRAME_TIMEOUT_S,
        BOUNDED_CALL_LIMIT_S=source.BOUNDED_CALL_LIMIT_S, NativeMode=modes.NativeMode,
        choose_mode=modes.choose_mode, NO_SAMPLE_NS=ring.NO_SAMPLE_NS, empty_diagnostics=source.empty_diagnostics,
        ControlRestore=source.ControlRestore)


def spec_camera_id(link):
    """The `camera_id` rule of 7.2, written from the spec: SHA-256 of the lower-case link, the first
    2 bytes as 4 hex digits."""
    return format(int.from_bytes(hashlib.sha256(link.lower().encode()).digest()[:2], "big"), "04x")


def fake_link(index):
    """A Media Foundation symbolic link of the form that 7.1 parses, for a fake device."""
    return (rf"\\?\usb#vid_feed&pid_{index:04x}&mi_00#7&fake{index:04x}&0&0000#"
            rf"{MEDIA_FOUNDATION_VIDEO_GUID}\global")


# ---------------------------------------------------------------------------
# Clocks
# ---------------------------------------------------------------------------

class RealClock:
    virtual = False

    @staticmethod
    def now_ns():
        return time.perf_counter_ns()

    def wait_until(self, wake_ns):
        delay = (wake_ns - time.perf_counter_ns()) / 1e9
        if delay > 0:
            time.sleep(delay)

    @contextlib.contextmanager
    def blocked(self):
        yield

    def gate(self, blocked):
        pass

    def leave(self):
        pass


class VirtualClock:
    """Virtual time for the camera loops of one process (THREAD workers).

    Each thread that waits on the clock is a participant. The time moves to the earliest wake time
    of the waiting participants when each live participant waits: in `wait_until`, in `blocked`, or
    at the lockstep gate (`gate`, which `capture_session.install_gate_probe` calls). A participant
    that does other work for `fallback_s` of real time does not stop the clock: the time then moves
    one step, to the earliest wake time but at most `forced_step_s`. Thus a loop that waits in another
    way (for example a paused loop) only slows the test, and a loop that is slow on a busy machine
    does not let the time jump to a far wake time, for example the end of a 2 s close (CI run of
    6d496aa24, macOS, T-CAP-108).
    """
    virtual = True
    START_NS = 1_000_000_000_000

    def __init__(self, fallback_s=0.05, forced_step_s=0.01):
        self._now = self.START_NS
        self._condition = threading.Condition()
        self._states = {}  # thread ident -> "run" | "gate" | "hold" | ("wait", wake_ns)
        self._threads = {}
        self._changed = time.monotonic()
        self.fallback_s = fallback_s
        self.forced_step_ns = round(forced_step_s * 1e9)

    def now_ns(self):
        return self._now

    def wait_until(self, wake_ns):
        with self._condition:
            me = self._join()
            self._set(me, ("wait", wake_ns))
            while self._now < wake_ns:
                self._advance()
                if self._now >= wake_ns:
                    break
                self._condition.wait(0.002)
                if time.monotonic() - self._changed > self.fallback_s:
                    self._advance(force=True)
            self._set(me, "run")

    @contextlib.contextmanager
    def blocked(self):
        """A wait with no wake time, for example a held call."""
        with self._condition:
            me = self._join()
            self._set(me, "hold")
            self._advance()
        try:
            yield
        finally:
            with self._condition:
                self._set(me, "run")

    def gate(self, blocked):
        me = threading.get_ident()
        with self._condition:
            if me not in self._states:
                return
            state = "gate" if blocked else "run"
            if self._states[me] != state:
                self._set(me, state)
                if blocked:
                    self._advance()

    def leave(self):
        with self._condition:
            self._states.pop(threading.get_ident(), None)
            self._advance()

    def give_work(self, thread, put):
        """`put()` gives work to `thread`, a thread that does not wait on the clock (the control thread of a
        camera loop). The time does not move until that thread waits for its next work (`idle_if`). Else the
        time runs on while the work waits for the GIL: on a CI runner a few ms of real time were more than 1 s
        of virtual time, and the exposure search passed its limit of 20 s (CI run 45278395951).
        Only a thread with no state or the state "idle" goes to "run". A thread that waits on the clock (for
        example in the fake hang of a set) keeps its wait, so the time still moves to its wake time."""
        with self._condition:
            self._threads[thread.ident] = thread
            if self._states.get(thread.ident) in (None, "idle"):
                self._set(thread.ident, "run")
            put()

    def idle_if(self, no_work):
        """The thread of `give_work` waits for its next work: when `no_work()` is true, its state is "idle", and
        the time can move."""
        with self._condition:
            me = self._join()
            if self._states.get(me) == "run" and no_work():
                self._set(me, "idle")
                self._advance()

    def advance_to(self, t_ns):
        """Move the time from a test thread that is not a participant."""
        with self._condition:
            if t_ns > self._now:
                self._now = t_ns
                self._changed = time.monotonic()
                self._condition.notify_all()

    def _join(self):
        thread = threading.current_thread()
        self._threads[thread.ident] = thread
        return thread.ident

    def _set(self, me, state):
        self._states[me] = state
        self._changed = time.monotonic()

    def _advance(self, force=False):
        for ident in [i for i in self._states if not self._threads[i].is_alive()]:
            del self._states[ident]
        waits = [state[1] for state in self._states.values() if isinstance(state, tuple)]
        if not waits or (not force and "run" in self._states.values()):
            return
        target = min(waits)
        if force:
            target = min(target, self._now + self.forced_step_ns)
        if target > self._now:
            self._now = target
            self._changed = time.monotonic()
            self._condition.notify_all()


# ---------------------------------------------------------------------------
# Script and shared record of one fake camera
# ---------------------------------------------------------------------------

@dataclass
class FakeScript:
    """The behaviour of one fake camera. Frame numbers are source frame numbers (from 0 at each open)."""
    modes: tuple = ((640, 480, 30, 1, "MJPG"),)  # native types in list order: (w, h, fps_num, fps_den, format)
    detected_modes: tuple | None = None  # the native types that detection sees; None: `modes`
    rate: float | None = None  # delivered frames per second; None: the rate of the opened mode
    intervals_ms: tuple = ()  # a cycled pattern of frame intervals; it replaces `rate`
    first_frame_delay_s: float = 0.0  # from the first ReadSample (in the open) to frame 0
    open_delay_s: float = 0.0  # the open waits this long before it starts the stream
    hold_opens: tuple = ()  # open numbers (from 1) that wait after the first frame until release()
    fail_opens: tuple = ()  # open numbers (from 1) that raise `open_failure`
    open_failure: tuple = ("open", "in use by another program")
    stop_after_frame: int | None = None  # a stall: no frame after this frame
    removed_after_frame: int | None = None  # device removed after this frame
    removed_code: str = "device-removed"  # the code of that error; "stream-error": a source error that is no wedge
    drop_before_frames: tuple = ()  # the camera drops the frame before each; the next has the attribute
    discontinuity_frames: tuple = ()  # frames with the discontinuity attribute and no drop
    burst: tuple | None = None  # (first, last): put together at the arrival time of `last`
    cut_off_frames: tuple = ()  # frames whose JPEG has no EOI
    sample_offset_ms: float | None = -4.0  # sample time = arrival + offset; None: no sample time
    controls: tuple = (("exposure", True, False, -6), ("gain", True, False, 0), ("focus", True, True, 30))
    reset_on_stream: tuple = ()  # (name, value): the camera sets this when the stream starts (C930e)
    keeps_controls: bool = False  # the camera keeps its control values from one open to the next (THREAD workers)
    reopen_shift: tuple = ()  # (name, delta): with keeps_controls, a later open reads a manual value moved by delta (C930e)
    reports_auto: tuple = ()  # control names that read back auto whatever the set (a camera in its own auto)
    live_set_faults: tuple = ()  # for the n-th live change: None, "error" or "readback:<value>"
    rate_after_change: tuple = ()  # the delivered rate after the n-th live change
    hold_after_change: bool = False  # the first read after a live change waits until release()
    hold_first_change: bool = False  # as hold_after_change, for the first live change of each open only
    live_set_delay_s: float = 0.0  # a live change waits this long (clock time) before it sets: frames arrive meanwhile
    rate_by_exposure: tuple = ()  # (exposure, rate) pairs: the delivered rate at that exposure value
    exposure_range: tuple | None = (-13, 0)  # (min, max) or (min, max, step) of the camera; None: no range
    out_of_range: str = "refuse"  # an exposure set outside the range: "refuse" (an error) or "clamp" (to the range)
    reported_range: bool = True  # False: `exposure_range()` gives None (as OpenCV), but the camera keeps its range
    raise_on_set: tuple = ()  # (value, n): the n-th exposure set of that value raises a RuntimeError (no CaptureFailure)
    brightness: tuple = ()  # (exposure, mean gray) pairs: the image follows the exposure
    hang_at: str | None = None  # "open", "set_controls" or "close": hangs when the hang is armed
    hang_armed: bool = False  # armed from the start; else FakeLog.arm_hang()
    align_ms: float | None = None  # frame 0 comes at the next multiple of this on the clock (a common grid)
    stop_at_s: float | None = None  # no frame after this clock time (s from VirtualClock.START_NS)
    rate_windows: tuple = ()  # (from_s, to_s, rate): the delivered rate between two clock times
    drop_at_window_end: bool = False  # the camera drops one frame when a rate window ends
    close_delay_s: float = 0.0  # the close of the source takes this long (clock time)
    exit_at: str | None = None  # "open", "close" or "frame:<n>": the camera process ends there with os._exit(3)
    on_arm: str | None = None  # after FakeLog.arm(), at the next frame: "stall", "exit" (os._exit(3)) or "remove"
    name: str | None = None  # the friendly name in the detection result; None: "Fake camera <index>"
    product_id: int | None = None  # the USB product ID in the detection result; None: the index (4.7.1 tests)
    no_dht: bool = False  # each JPEG has no DHT segment, as many UVC cameras send it
    diagnostics: dict | None = None  # keys that `diagnostics()` adds to the null source keys and `frames`


class FakeLog:
    """What a fake camera did. The `multiprocessing.Value` fields are also valid in the main process
    when the fake runs in a camera process. The lists are valid only in the process of the fake."""

    def __init__(self):
        self.opens = multiprocessing.Value("i", 0)
        self.closes = multiprocessing.Value("i", 0)
        self.first_read_sample_ns = multiprocessing.Value("q", 0)
        self.hang_started_ns = multiprocessing.Value("q", 0)
        self.hang_armed = multiprocessing.Value("b", 0)
        self.armed = multiprocessing.Value("b", 0)  # the event of `FakeScript.on_arm`
        self.events = []  # (name, clock ns, detail)
        self.settings = []  # each `changes` of set_controls, in order
        self.frames = {}  # frame number -> (arrival_ns, sample_ns), of the last open
        self.history = []  # `frames` of each open, in order
        self.taken = []  # frame numbers that read_frame returned, of the last open
        self.first_sfn_after_readback = None  # the next frame number at the first set with changes
        self.device_controls = None  # the controls that a camera with `keeps_controls` keeps between opens

    def arm_hang(self):
        self.hang_armed.value = 1

    def arm(self):
        """The event of `FakeScript.on_arm` comes at the next frame (also in a camera process)."""
        self.armed.value = 1

    def names(self):
        return [event[0] for event in self.events]


# ---------------------------------------------------------------------------
# Synthetic JPEGs
# ---------------------------------------------------------------------------

_JPEG_CACHE = {}


def synthetic_jpeg(width, height, gray=None):
    """A q90 JPEG of a fixed pattern, or of one gray value. Made in code; no camera image."""
    key = (width, height, gray)
    if key not in _JPEG_CACHE:
        if gray is None:
            x = np.linspace(0, 255, width, dtype=np.float32)
            y = np.linspace(0, 255, height, dtype=np.float32)[:, None]
            image = np.stack([np.broadcast_to(x, (height, width)), np.broadcast_to(y, (height, width)),
                              np.full((height, width), 128, np.float32)], axis=2).astype(np.uint8)
        else:
            image = np.full((height, width, 3), gray, np.uint8)
        _JPEG_CACHE[key] = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1].tobytes()
    return _JPEG_CACHE[key]


def without_dht(jpeg):
    """The JPEG with each DHT segment before SOS removed (a decoder then needs the standard tables)."""
    parts, i = [jpeg[:2]], 2
    while jpeg[i + 1] != 0xDA:
        end = i + 2 + int.from_bytes(jpeg[i + 2:i + 4], "big")
        if jpeg[i + 1] != 0xC4:
            parts.append(jpeg[i:end])
        i = end
    return b"".join(parts) + jpeg[i:]


def with_comment(jpeg, frame_number):
    """Insert a JPEG comment segment (COM) after SOI. It makes each payload different."""
    text = f"fake frame {frame_number}".encode()
    return jpeg[:2] + b"\xff\xfe" + struct.pack(">H", len(text) + 2) + text + jpeg[2:]


# ---------------------------------------------------------------------------
# The fake source
# ---------------------------------------------------------------------------

class FakeSource:
    """A push source with a script (section 4.4). See the module docstring."""

    def __init__(self, script, *, camera_id="0", link="", clock=None, types=None, log=None, on_read=None):
        self.script = script
        self.camera_id = camera_id
        self.link = link or fake_link(0)
        self.clock = clock or RealClock()
        self.types = types or product_types()
        self.log = log or FakeLog()
        self.on_read = on_read
        self._lock = threading.RLock()
        self._place = None
        self._thread = None
        self._stop = threading.Event()
        self._released = threading.Event()
        self.holding = threading.Event()
        self._opened = False
        self._ended = False
        self._error_code = None  # the code of the stream error of the source (removed_after_frame)
        self._mode = None
        self._rate = None
        self._upcoming = deque()  # (frame number, arrival_ns), made ahead of delivery
        self._next_sfn = 0
        self._last_arrival = 0
        self._interval_index = 0
        self._controls = {}
        self._live_changes = 0
        self._hold_next_read = False
        self._cut_next = False
        self._remove_after = script.removed_after_frame
        self._stop_after = script.stop_after_frame
        self._slow = None  # [rate, seconds, start_ns or None]
        self._drops = set(script.drop_before_frames)  # frames after a camera drop
        self._drop_next = False
        self._in_window = False
        self._base_ns = getattr(self.clock, "START_NS", 0)
        self._stop_ns = None if script.stop_at_s is None else self._base_ns + round(script.stop_at_s * 1e9)
        self.slow_finished_ns = None
        self.cut_frames = []
        self.removed_frame = None
        self._restore = None  # the product `ControlRestore` of the open (unix-capture.md 4.7)
        self.t_close_ms = None

    # ----- the capture interface (4.1) -----

    def open(self, request):
        types = self.types
        with self._lock:
            self.log.opens.value += 1
            number = self.log.opens.value
            self._event("open", request)
        if self.script.open_delay_s:
            self._wait(self.script.open_delay_s)
        if self.script.exit_at == "open":
            os._exit(3)  # a camera process that ends without unwinding (a native crash)
        self._maybe_hang("open", "open")
        if number in self.script.fail_opens:
            raise types.CaptureFailure(*self.script.open_failure)
        mode = types.choose_mode([types.NativeMode(*m) for m in self.script.modes], request)
        with self._lock:
            self._mode = mode
            self._rate = self.script.rate or mode.fps_num / mode.fps_den
            self._place = types.WaitingPlace()
            self._stop.clear()
            self._ended, self._error_code = False, None
            self._upcoming.clear()
            self._next_sfn = 0
            self._interval_index = 0
            self._live_changes = 0
            self.log.frames, self.log.taken = {}, []
            self.log.history.append(self.log.frames)
            self.log.first_sfn_after_readback = None
            kept = self.log.device_controls if self.script.keeps_controls else None
            self._controls = kept or {name: [present, auto, value] for name, present, auto, value in self.script.controls}
            if self.script.keeps_controls:
                self.log.device_controls = self._controls
            for name, delta in self.script.reopen_shift if kept else ():
                if not self._controls[name][1]:
                    self._controls[name][2] += delta
            for name, value in self.script.reset_on_stream:
                self._controls[name][2] = value
            restore = getattr(types, "ControlRestore", None)  # the stand-ins of the self-tests have none
            self._restore = restore(self.camera_id) if restore is not None else None
            t0 = self.clock.now_ns()
            self.log.first_read_sample_ns.value = t0
            self._event("read_sample", None)
            self._last_arrival = t0 + round(self.script.first_frame_delay_s * 1e9)
            if self.script.align_ms:
                grid = round(self.script.align_ms * 1e6)
                self._last_arrival = self._base_ns + -(-(self._last_arrival - self._base_ns) // grid) * grid
            self._upcoming.append((0, self._last_arrival))
        if self.script.first_frame_delay_s > types.FIRST_FRAME_TIMEOUT_S:
            self._wait(types.FIRST_FRAME_TIMEOUT_S)
            self._event("first_frame_timeout", None)
            raise types.CaptureFailure("first frame", f"no frame in {types.FIRST_FRAME_TIMEOUT_S:g} s")
        if not self.clock.virtual:
            self._thread = threading.Thread(target=self._deliver_loop, name=f"fake {self.camera_id}", daemon=True)
            self._thread.start()
        self._wait_first_frame()
        self._opened = True
        self._event("first_frame", None)
        if number in self.script.hold_opens:
            self._hold()
        return types.OpenedMode(width=mode.width, height=mode.height, fps_num=mode.fps_num,
                                fps_den=mode.fps_den, format=mode.format, device_path=self.link)

    def read_frame(self, timeout_s):
        if self.on_read is not None:
            self.on_read(self, self.clock.now_ns())
        if self._hold_next_read:
            self._hold_next_read = False
            self._hold()
        if not self.clock.virtual:
            return self._take(timeout_s)
        self._deliver_until(self.clock.now_ns())
        frame = self._take(0.0)
        if frame is not None:
            return frame
        wake = self.clock.now_ns() + round(timeout_s * 1e9)
        due = self._next_due()
        if due is not None:
            wake = min(wake, due)
        self.clock.wait_until(wake)
        self._deliver_until(self.clock.now_ns())
        return self._take(0.0)

    def set_controls(self, changes):
        types = self.types
        self._event("set_controls", dict(changes))
        self.log.settings.append(dict(changes))
        self._maybe_hang("set_controls", "set controls")
        start = self.log.first_sfn_after_readback
        if (self.script.live_set_delay_s and changes and start is not None and self.log.taken
                and self.log.taken[-1] >= start + 90):  # the rule of `live` below; the wait is outside the lock
            self._wait(self.script.live_set_delay_s)
        with self._lock:
            if self.clock.virtual and self._opened:
                self._deliver_until(self.clock.now_ns())
            start = self.log.first_sfn_after_readback
            live = bool(changes) and start is not None and self.log.taken and self.log.taken[-1] >= start + 90
            fault = None
            if live:
                self._live_changes += 1
                faults = self.script.live_set_faults
                fault = faults[self._live_changes - 1] if self._live_changes <= len(faults) else None
            if self._restore is not None:
                exposure = self.exposure_range()
                self._restore.read(self._read_back(), {"exposure": (exposure or (0, 0, None))[2]},
                                   {"exposure": exposure[:2]} if exposure else None)
                self._restore.changed(changes)
            if fault == "error":
                raise types.CaptureFailure("set controls", "the camera refused the value")
            low, high = (self.script.exposure_range or (None, None))[:2]
            setting = changes.get("exposure")
            if setting is not None and setting.value is not None and self.script.raise_on_set:
                self._value_sets = getattr(self, "_value_sets", {})
                self._value_sets[setting.value] = self._value_sets.get(setting.value, 0) + 1
                if (setting.value, self._value_sets[setting.value]) in self.script.raise_on_set:
                    raise RuntimeError(f"the driver call for exposure {setting.value} raised")
            if low is not None and setting is not None and setting.value is not None and not low <= setting.value <= high:
                if self.script.out_of_range == "refuse":
                    raise types.CaptureFailure("set controls", f"exposure {setting.value} is out of range")
                changes = {**changes, "exposure": type(setting)(auto=setting.auto, value=min(max(setting.value, low), high))}
            for name, setting in changes.items():
                control = self._controls.get(name)
                if control is None or not control[0]:
                    raise types.CaptureFailure("set controls", f"no {name} control")
                control[1] = bool(setting.auto)
                if setting.value is not None:
                    control[2] = int(setting.value)
                if fault and fault.startswith("readback:"):
                    control[2] = int(fault.split(":", 1)[1])
            if live:
                rates = self.script.rate_after_change
                if self._live_changes <= len(rates):
                    self._rate = rates[self._live_changes - 1]
                    self._interval_index = 0
                self._hold_next_read = self.script.hold_after_change or (
                    self.script.hold_first_change and self._live_changes == 1)
            if changes and start is None:
                self.log.first_sfn_after_readback = self._next_sfn
            state = self._read_back()
            if self._restore is not None:
                self._restore.after_set(state)
            return state

    def close(self, restore=True):
        self._event("close", None)
        t0 = time.perf_counter_ns()
        with self._lock:
            self.log.closes.value += 1
        if self.script.exit_at == "close":
            os._exit(3)  # a camera process that ends in its close (a native crash)
        self._maybe_hang("close", "close")
        # the restore of 4.7, before the stream stops; never after a wedge (as Media Foundation) [Z7F3]
        if restore and self._restore is not None and self._opened and (
                not self._ended or self._error_code not in WEDGE_CODES):
            self._restore.restore(self.set_controls)
        if self.script.close_delay_s:
            self._wait(self.script.close_delay_s)
        self._stop.set()
        self._released.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)
        self._opened = False
        self.t_close_ms = (time.perf_counter_ns() - t0) / 1e6
        self.clock.leave()

    def diagnostics(self):
        """The null source keys of unix-capture.md 4.6.2, `frames`, and the keys of the script."""
        data = {**self.types.empty_diagnostics(), "frames": len(self.log.taken), "t_close_ms": self.t_close_ms}
        if self._restore is not None:
            self._restore.fill(data)
        return {**data, **(self.script.diagnostics or {})}

    def exposure_range(self):
        """(min, max, step) or None, as each product source (the step is 1 when the script gives none)."""
        if self.script.exposure_range is None or not self.script.reported_range:
            return None
        low, high, *step = self.script.exposure_range
        return (low, high, step[0] if step else 1)

    @property
    def replaced_count(self):
        if self._place is None:
            return 0
        if self.clock.virtual and self._opened:
            self._deliver_until(self.clock.now_ns())
        return self._place.replaced

    # ----- triggers for tests in one process -----

    def release(self):
        """End a hold (`hold_opens`, `hold_after_change`)."""
        self._released.set()

    def slow_period(self, rate, seconds):
        """Deliver `rate` frames per second for `seconds` (clock time) from the next frame."""
        with self._lock:
            self._slow = [rate, seconds, None]
            self.slow_finished_ns = None

    def cut_off_next(self):
        with self._lock:
            self._cut_next = True

    def remove_now(self):
        """Device removed after the next frame."""
        with self._lock:
            self._remove_after = self._next_sfn

    def stop_now(self):
        """A stall: no frame from the next one."""
        with self._lock:
            self._stop_after = self._next_sfn - 1

    def drift(self, **values):
        """The camera changes control values by itself, as in an auto mode."""
        with self._lock:
            for name, value in values.items():
                self._controls[name][2] = value

    # ----- internals -----

    def _event(self, name, detail):
        self.log.events.append((name, self.clock.now_ns(), detail))

    def _wait(self, seconds):
        self.clock.wait_until(self.clock.now_ns() + round(seconds * 1e9))

    def _hold(self):
        self._event("hold", None)
        self.holding.set()
        with self.clock.blocked():
            self._released.wait(HOLD_LIMIT_S)
        self._released.clear()
        self.holding.clear()
        self._event("released", None)

    def _maybe_hang(self, call, stage):
        if self.script.hang_at != call or not (self.script.hang_armed or self.log.hang_armed.value):
            return
        self.log.hang_armed.value = 0
        self.log.hang_started_ns.value = time.perf_counter_ns()
        self._event("hang", call)
        threading.Thread(target=threading.Event().wait, name="stuck call", daemon=True).start()
        limit = self.types.BOUNDED_CALL_LIMIT_S
        self._wait(limit)
        raise self.types.CaptureFailure(stage, f"{call} did not return in {limit:g} s", hung=True)

    def _read_back(self):
        value_type = self.types.ControlValue
        return {name: value_type(present=present, auto=(auto or name in self.script.reports_auto) if present else False,
                                 value=value if present else None)
                for name, (present, auto, value) in self._controls.items()}

    def _interval_ns(self, previous_arrival):
        if self.script.rate_windows:
            clock_s = (previous_arrival - self._base_ns) / 1e9
            for start, end, rate in self.script.rate_windows:
                if start <= clock_s < end:
                    self._in_window = True
                    return round(1e9 / rate)
            if self._in_window:
                self._in_window = False
                if self.script.drop_at_window_end:
                    self._drop_next = True
                    return 2 * round(1e9 / self._rate)
        if self._slow is not None:
            rate, seconds, start = self._slow
            if start is None:
                self._slow[2] = start = previous_arrival
            if previous_arrival < start + round(seconds * 1e9):
                return round(1e9 / rate)
            self._slow = None
            self.slow_finished_ns = previous_arrival
        by_exposure = dict(self.script.rate_by_exposure)
        if self._controls.get("exposure", [0, 0, None])[2] in by_exposure:
            return round(1e9 / by_exposure[self._controls["exposure"][2]])
        if self.script.intervals_ms:
            value = self.script.intervals_ms[self._interval_index % len(self.script.intervals_ms)]
            self._interval_index += 1
            return round(value * 1e6)
        return round(1e9 / self._rate)

    def _arrival(self, sfn):
        """The arrival time of frame `sfn`. Makes the schedule up to that frame."""
        while self._upcoming[-1][0] < sfn:
            k, arrival = self._upcoming[-1]
            arrival += self._interval_ns(arrival)
            if k + 1 in self.script.drop_before_frames:
                arrival += self._interval_ns(arrival)  # the dropped frame's place in time
            if self._drop_next:
                self._drop_next = False
                self._drops.add(k + 1)
            self._upcoming.append((k + 1, arrival))
        for k, arrival in self._upcoming:
            if k == sfn:
                return arrival
        raise AssertionError(f"frame {sfn} is not in the schedule")

    def _due(self, sfn):
        burst = self.script.burst
        if burst and burst[0] <= sfn <= burst[1]:
            return self._arrival(burst[1])
        return self._arrival(sfn)

    def _next_due(self):
        with self._lock:
            if self._ended or (self._stop_after is not None and self._next_sfn > self._stop_after):
                return None
            due = self._due(self._next_sfn)
            return None if self._stop_ns is not None and due > self._stop_ns else due

    def _deliver_until(self, t_ns):
        types = self.types
        with self._lock:
            while not self._ended and self._place is not None:
                k = self._next_sfn
                if self.script.on_arm and self.log.armed.value:
                    self.log.armed.value = 0
                    if self.script.on_arm == "exit":
                        os._exit(3)  # a camera process that ends without unwinding (a native crash)
                    if self.script.on_arm == "stall":
                        self._stop_after = k - 1
                    else:  # "remove": the error of `removed_code` before frame k
                        self._remove_after = k - 1
                if self._stop_after is not None and k > self._stop_after:
                    return
                if self._due(k) > t_ns or (self._stop_ns is not None and self._due(k) > self._stop_ns):
                    return
                if self._remove_after is not None and k > self._remove_after:
                    # the device goes away between frame k - 1 and the time of frame k
                    self.removed_frame = k - 1
                    self._ended = True
                    error = types.CaptureFailure("streaming", "device removed" if self.script.removed_code
                                                 == "device-removed" else "E_FAIL")
                    error.code = self._error_code = self.script.removed_code  # the stand-ins take no `code`
                    self._place.put_error(error)
                    return
                arrival = self._arrival(k)
                while self._upcoming and self._upcoming[0][0] < k:
                    self._upcoming.popleft()
                if self.script.exit_at == f"frame:{k}":
                    os._exit(3)  # a camera process that ends without unwinding (a native crash)
                frame = self._make_frame(k, arrival)
                self.log.frames[k] = (arrival, frame.sample_ns)
                self._next_sfn = k + 1
                self._place.put(frame)

    def _make_frame(self, k, arrival):
        types = self.types
        width, height = self._mode.width, self._mode.height
        jpeg = synthetic_jpeg(width, height, self._gray())
        payload = with_comment(without_dht(jpeg) if self.script.no_dht else jpeg, k)
        if k in self.script.cut_off_frames or self._cut_next:
            self._cut_next = False
            self.cut_frames.append(k)
            payload = payload[: len(payload) // 2]
        offset = self.script.sample_offset_ms
        sample = types.NO_SAMPLE_NS if offset is None else arrival + round(offset * 1e6)
        return types.CapturedFrame(
            payload=payload, format=self._mode.format, arrival_ns=arrival, sample_ns=sample,
            delivered_len=len(payload), driver_error=False, source_frame_number=k,
            discontinuity=k in self._drops or k in self.script.discontinuity_frames)

    def _gray(self):
        if not self.script.brightness:
            return None
        exposure = self._controls["exposure"][2]
        return min(self.script.brightness, key=lambda pair: abs(pair[0] - exposure))[1]

    def _take(self, timeout_s):
        frame = self._place.take(timeout_s)
        if frame is not None:
            self.log.taken.append(frame.source_frame_number)
        return frame

    def _wait_first_frame(self):
        if self.clock.virtual:
            self.clock.wait_until(self._due(0))
            self._deliver_until(self.clock.now_ns())
            return
        while 0 not in self.log.frames and not self._stop.is_set():
            time.sleep(0.001)

    def _deliver_loop(self):
        while not self._stop.is_set():
            due = self._next_due()
            if due is None:
                self._stop.wait(0.05)
                continue
            delay = (due - time.perf_counter_ns()) / 1e9
            if delay > 0 and self._stop.wait(delay):
                return
            self._deliver_until(time.perf_counter_ns())


# ---------------------------------------------------------------------------
# A fake Media Foundation enumeration for detection (7.1)
# ---------------------------------------------------------------------------

@dataclass
class FakeDetectionBackend:
    """The `backend` of `detect_media_foundation_cameras` (ADR-HP7D). It can be pickled for the
    detection child. `devices()` gives (friendly name, symbolic link) pairs; `native_modes(link)`
    gives the native types of a link. The call for `hang_link` does not return."""
    devices_and_modes: tuple  # ((name, link, modes), ...) with modes as in FakeScript.modes
    hang_link: str | None = None

    def devices(self):
        return [(name, link) for name, link, _ in self.devices_and_modes]

    def native_modes(self, link):
        if link == self.hang_link:
            threading.Event().wait()
        modes = importlib.import_module("skellycam.core.camera.capture.modes")
        for _, device_link, native in self.devices_and_modes:
            if device_link == link:
                return [modes.NativeMode(*m) for m in native]
        raise KeyError(link)


# ---------------------------------------------------------------------------
# The source factory of a camera group
# ---------------------------------------------------------------------------

@dataclass
class FakeSourceFactory:
    """The `source_factory` of `CameraGroupManager` (ADR-HP7D): `factory(config)` gives a new
    FakeSource for the camera of `config`. Camera i has the link `fake_link(i)` and the
    `camera_id` of 7.2. It can be pickled for camera processes when `clock` and `on_read` are None."""
    scripts: list
    clock: object = None
    types: object = None
    on_read: object = None
    logs: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)

    def __post_init__(self):
        self.links = [fake_link(index) for index in range(len(self.scripts))]
        self.camera_ids = [spec_camera_id(link) for link in self.links]
        self.by_id = dict(zip(self.camera_ids, range(len(self.scripts))))
        self.logs = {camera_id: FakeLog() for camera_id in self.camera_ids}

    def __getstate__(self):
        state = dict(self.__dict__)
        state["sources"] = {}
        return state

    def __call__(self, config):
        index = self.by_id[config.camera_id]
        source = FakeSource(self.scripts[index], camera_id=config.camera_id, link=self.links[index],
                            clock=self.clock or RealClock(), types=self.types, log=self.logs[config.camera_id],
                            on_read=self.on_read)
        self.sources[config.camera_id] = source
        return source

    def device_infos(self):
        """The detection result of the fake cameras (7.1, 7.3), built with the product names."""
        from skellycam.core.device_detection.detect_cameras_devices import CameraDeviceInfo

        modes = importlib.import_module("skellycam.core.camera.capture.modes")
        infos = []
        for index, script in enumerate(self.scripts):
            native = [modes.NativeMode(*m) for m in (script.detected_modes or script.modes)]
            infos.append(CameraDeviceInfo(index=index, name=script.name or f"Fake camera {index}", vendor_id=0xFEED,
                                          product_id=index if script.product_id is None else script.product_id,
                                          path=self.links[index],
                                          supported_modes=modes.supported_modes(native), modes_read=True,
                                          virtual="virtual" in (script.name or "").lower()))
        return infos
