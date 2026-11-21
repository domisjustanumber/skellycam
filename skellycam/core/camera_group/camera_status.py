import json
import logging
import multiprocessing
from contextlib import contextmanager
from dataclasses import dataclass, field
from multiprocessing import parent_process
from typing import Any

logger = logging.getLogger(__name__)

# The camera states of specs/windows-capture.md, section 8.1. "recording" is `ready` with a recording that runs.
# `adjusting`: the exposure search runs (camera-requests.md 1.4); it is last so that the other indexes stay.
STATES = ("starting", "waiting", "failed", "checking", "too_slow", "ready", "recording", "dead", "adjusting")
GATE_STATES = ("checking", "too_slow", "ready", "adjusting")  # 5.2: only these hold the gate back
SETTLED_STATES = ("waiting", "failed", "checking", "too_slow", "ready", "dead")
INFO_SIZE = 16384
# A process that ends while it holds a lock of a shared object keeps that lock for ever. Thus each scalar of the
# status has no lock (one writer at a time; an aligned scalar is read and written whole), and each wait for the
# lock of a JSON array is bounded: after it, that one call goes on with no lock (unix-capture.md 4.10).
ARRAY_LOCK_WAIT_S = 0.5
ARRAYS = ("info", "warnings", "camera_warnings", "group_warnings")
MAIN_ONLY = ("owner", "holder_dead", "last_good", "pending_info", "lock_warned")  # never pickled to a camera process


@dataclass
class CameraStatus:
    connected: Any = field(default_factory=lambda: multiprocessing.Value("b", False, lock=False))
    grabbing_frame: Any = field(default_factory=lambda: multiprocessing.Value("b", False, lock=False))
    closing: Any = field(default_factory=lambda: multiprocessing.Value("b", False, lock=False))
    closed: Any = field(default_factory=lambda: multiprocessing.Value("b", False, lock=False))
    recording_in_progress: Any = field(default_factory=lambda: multiprocessing.Value("b", False, lock=False))
    is_recording_frame: Any = field(default_factory=lambda: multiprocessing.Value("b", False, lock=False))
    should_pause: Any = field(default_factory=lambda: multiprocessing.Value("b", False, lock=False))
    should_close: Any = field(default_factory=lambda: multiprocessing.Value("b", False, lock=False))
    is_paused: Any = field(default_factory=lambda: multiprocessing.Value("b", False, lock=False))
    updating: Any = field(default_factory=lambda: multiprocessing.Value("b", False, lock=False))
    error: Any = field(default_factory=lambda: multiprocessing.Value("b", False, lock=False))

    frame_count: Any = field(default_factory=lambda: multiprocessing.Value("q", -1, lock=False))
    # Frames replaced in the waiting place since the first frame in the gate, as the stop line (5.2, 8.4).
    replaced_count: Any = field(default_factory=lambda: multiprocessing.Value("q", 0, lock=False))
    # The time.monotonic() of the last progress of the camera writer of a take [C6DE D1] (recorder.md 5.3).
    writer_progress_at: Any = field(default_factory=lambda: multiprocessing.Value("d", 0.0, lock=False))
    state_index: Any = field(default_factory=lambda: multiprocessing.Value("b", -1, lock=False))
    # One more at each pass of the shared loop and at least each 0.5 s of a wait in the recorder: the signal of
    # the main-process stall watch (unix-capture.md 4.10).
    alive_count: Any = field(default_factory=lambda: multiprocessing.Value("q", 0, lock=False))
    # JSON that the camera process writes: failure, mode, measured_fps, controls, source (8.4), layout, hung
    # (recorder.md 6.4, 7.4). The main process writes `failure` only after the camera process ended, or when
    # the stall watch ends the process (unix-capture.md 4.10).
    info: Any = field(default_factory=lambda: multiprocessing.Array("c", INFO_SIZE))
    # JSON that only the main process writes: the warning items of the recording that runs (11.3).
    warnings: Any = field(default_factory=lambda: multiprocessing.Array("c", INFO_SIZE))
    # camera-requests.md 1.5 [AC5B]: the items of the camera process (`add_light`, `exposure_search_failed`,
    # `no_manual_exposure`) and of the main process (`rate_fallback`, `start_failure`). Neither a record start, a
    # stop nor "apply again" clears them.
    camera_warnings: Any = field(default_factory=lambda: multiprocessing.Array("c", INFO_SIZE))
    group_warnings: Any = field(default_factory=lambda: multiprocessing.Array("c", INFO_SIZE))
    # camera-requests.md 1.5 [B20, FC1C]: the searches since the group started; the camera process adds one.
    search_count: Any = field(default_factory=lambda: multiprocessing.Value("q", 0, lock=False))
    # camera-requests.md 1.2 (c): the main process asks for a search on the open stream; the camera process clears it.
    search_requested: Any = field(default_factory=lambda: multiprocessing.Value("b", False, lock=False))
    # The main process only: the counter subset of the newest diagnostics of the camera (unix-capture.md 4.2 item 2).
    diagnostics: dict = field(default_factory=dict)
    # Per process, and never pickled: the worker of the camera (the main process sets it), whether that process
    # ended while the lock of an array did not come, the last good JSON of each array, and the fields that the
    # main process could not write into `info` with no lock.
    owner: Any = None
    holder_dead: bool = False
    last_good: dict = field(default_factory=dict)
    pending_info: dict = field(default_factory=dict)
    lock_warned: bool = False

    def __getstate__(self) -> dict:
        return {name: value for name, value in self.__dict__.items() if name not in MAIN_ONLY}

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state, owner=None, holder_dead=False, last_good={}, pending_info={}, lock_warned=False)

    @contextmanager
    def _array_lock(self, array):
        """True with the lock of `array`; False when it did not come in ARRAY_LOCK_WAIT_S: this call only goes on
        with no lock. Only an ended process of the camera stops the wait for good (until `reset_for_start`)."""
        lock = array.get_lock()
        if not self.holder_dead and lock.acquire(timeout=ARRAY_LOCK_WAIT_S):
            self.lock_warned = False
            try:
                yield True
            finally:
                lock.release()
            return
        alive = None if self.owner is None else self.owner.is_alive()
        if not self.holder_dead and (alive is False or not self.lock_warned):
            self.holder_dead, self.lock_warned = alive is False, True
            state = {None: "not known here", True: "alive", False: "ended"}[alive]
            logger.error(f"No lock of a status array of {getattr(self.owner, 'name', 'a camera')} in "
                         f"{ARRAY_LOCK_WAIT_S:g} s; the camera process is {state}; the call goes on with no lock")
        yield False

    def _json(self, name: str, empty, raw: bytes | None = None):
        """The JSON of the array `name`. A read with no lock can see torn JSON: it reads again up to 3 times, then
        gives the last good value of this process, or `empty`. It never raises."""
        array = getattr(self, name)
        for _ in range(3):
            if raw is None:
                with self._array_lock(array):
                    raw = array.get_obj().value
            try:
                value = json.loads(raw) if raw else empty
            except ValueError:  # JSONDecodeError, UnicodeDecodeError
                raw = None
                continue
            self.last_good[name] = raw
            return value
        try:
            return json.loads(self.last_good.get(name) or b"null") or empty
        except ValueError:  # a write cut at INFO_SIZE
            return empty

    @property
    def state(self) -> str | None:
        index = self.state_index.value
        return STATES[index] if index >= 0 else None

    def set_state(self, state: str | None) -> None:
        self.state_index.value = -1 if state is None else STATES.index(state)

    @property
    def in_gate(self) -> bool:
        return self.state in GATE_STATES

    @property
    def ready(self) -> bool:
        return self.state == "ready" and not self.should_pause.value and not self.should_close.value

    def info_dict(self) -> dict:
        return {**self._json("info", {}), **self.pending_info}

    def update_info(self, **fields) -> None:
        with self._array_lock(self.info) as locked:
            if not locked and parent_process() is None:
                # The main process with no lock: a write could lose or tear a write of the camera. Its fields stay
                # in this process (`info_dict` shows them) until a write with the lock.
                self.pending_info.update(fields)
                return
            data = self._json("info", {}, raw=self.info.get_obj().value)
            data.update(self.pending_info)
            data.update(fields)
            self.pending_info.clear()
            self.info.get_obj().value = self.last_good["info"] = json.dumps(data).encode()[:INFO_SIZE - 1]

    def _name(self, array) -> str:
        return "warnings" if array is None else next(name for name in ARRAYS if getattr(self, name) is array)

    def warning_items(self, array=None) -> list:
        return self._json(self._name(array), [])

    def set_warning_items(self, items: list, array=None) -> None:
        array = getattr(self, self._name(array))
        with self._array_lock(array):  # one writer process for each warning array: a write with no lock loses nothing
            array.get_obj().value = json.dumps(items).encode()[:INFO_SIZE - 1]

    def replace_warning_items(self, array, kinds: tuple, items: list) -> None:
        """Drop the items of `kinds` from `array` (`camera_warnings` or `group_warnings`), then add `items`."""
        kept = [item for item in self.warning_items(array) if item.get("kind") not in kinds]
        self.set_warning_items(kept + items, array)

    def reset_for_start(self) -> None:
        """A new camera process for "apply again" (8.3): the gate count stays (5.3), the rest starts again."""
        for flag in (self.connected, self.grabbing_frame, self.closing, self.closed, self.recording_in_progress,
                     self.is_recording_frame, self.should_pause, self.should_close, self.is_paused, self.updating,
                     self.error, self.search_requested):
            flag.value = False
        if self.holder_dead:  # the old process ended with a lock: the new process gets new arrays (unix 4.10)
            kept = {name: self.warning_items(getattr(self, name)) for name in ("camera_warnings", "group_warnings")}
            for name in ARRAYS:
                setattr(self, name, multiprocessing.Array("c", INFO_SIZE))
            for name, items in kept.items():
                self.set_warning_items(items, getattr(self, name))
            self.holder_dead = False
        with self._array_lock(self.info):
            self.info.get_obj().value = b""
        self.pending_info.clear()
        self.last_good.clear()
        self.diagnostics = {}
        self.set_warning_items([])
        self.set_state("starting")

    def signal_error(self):
        self.error.value = True
        self.connected.value = False
        self.grabbing_frame.value = False
        self.is_paused.value = False
        self.should_pause.value = False

    def signal_closing(self):
        self.closing.value = True
        self.grabbing_frame.value = False
        self.is_paused.value = False
        self.should_pause.value = False
        self.connected.value = False
        self.updating.value = False
        self.recording_in_progress.value = False
        self.is_recording_frame.value = False

    def serialize(self):
        info = self.info_dict()
        state = self.state
        if state == "ready" and self.recording_in_progress.value:
            state = "recording"
        return {
            "connected": self.connected.value,
            "closed": self.closed.value,
            "recording_in_progress": self.recording_in_progress.value,
            "is_paused": self.is_paused.value,
            "error": self.error.value,
            "replaced_count": self.replaced_count.value,
            "state": state,
            "failure": info.get("failure"),
            "mode": info.get("mode"),
            "measured_fps": info.get("measured_fps"),
            "warnings": self.warning_items() + self.warning_items(self.camera_warnings)
                        + self.warning_items(self.group_warnings),  # camera-requests.md 1.5 [AC5B]
            "exposure_search": ({**info["exposure_search"], "count": self.search_count.value}
                                if info.get("exposure_search") else None),
            "controls": info.get("controls"),
            "diagnostics": self.diagnostics,
        }
