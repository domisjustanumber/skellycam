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
# status has no lock (one writer at a time; an aligned scalar is read and written whole), and the wait for the
# lock of a JSON array is bounded: one wait of ARRAY_LOCK_WAIT_S for each stretch with no lock, then tries with no
# wait until the lock comes again; a call with no lock goes on with no lock (unix-capture.md 4.10).
ARRAY_LOCK_WAIT_S = 0.5
ARRAYS = ("info", "warnings", "camera_warnings", "group_warnings")
MAIN_ONLY = ("owner", "holder_dead", "last_good", "pending_info", "no_lock")  # never pickled to a camera process

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
    # ended while the lock of an array did not come, the last good JSON of each array, the fields that the main
    # process could not write into `info` with no lock, and the arrays in a stretch with no lock.
    owner: Any = None
    holder_dead: bool = False
    last_good: dict = field(default_factory=dict)
    pending_info: dict = field(default_factory=dict)
    no_lock: set = field(default_factory=set)

    def __getstate__(self) -> dict:
        return {name: value for name, value in self.__dict__.items() if name not in MAIN_ONLY}

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state, owner=None, holder_dead=False, last_good={}, pending_info={}, no_lock=set())

    @contextmanager
    def _array_lock(self, name: str):
        """True with the lock of the array `name`; False with no lock: this call goes on with no lock. The first
        call of a stretch with no lock waits ARRAY_LOCK_WAIT_S and logs one line; the next calls try with no wait
        until the lock comes again. An ended process of the camera stops the tries until `reset_for_start`."""
        lock = getattr(self, name).get_lock()
        if not self.holder_dead and lock.acquire(timeout=0 if name in self.no_lock else ARRAY_LOCK_WAIT_S):
            self.no_lock.discard(name)
            try:
                yield True
            finally:
                lock.release()
            return
        if not self.holder_dead:
            alive = None if self.owner is None else self.owner.is_alive()
            new, self.holder_dead = name not in self.no_lock, alive is False
            self.no_lock.add(name)
            if new or self.holder_dead:
                state = {None: "not known here", True: "alive", False: "ended"}[alive]
                logger.error(f"No lock of the status array {name} of {getattr(self.owner, 'name', 'a camera')} in "
                             f"{ARRAY_LOCK_WAIT_S:g} s; the camera process is {state}; the calls go on with no lock")
        yield False

    def _json(self, name: str, empty, raw: bytes | None = None):
        """The JSON of the array `name`. A read with no lock can see torn JSON: it reads again up to 3 times, then
        gives the last good value of this process, or `empty`. It never raises."""
        for _ in range(3):
            if raw is None:
                with self._array_lock(name):
                    raw = getattr(self, name).get_obj().value
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
        with self._array_lock("info") as locked:
            if not locked and parent_process() is None:
                # The main process with no lock: a write could lose or tear a write of the camera. Its fields stay
                # in this process (`info_dict` shows them) until a write with the lock.
                self.pending_info.update(fields)
                return
            data = self._json("info", {}, raw=self.info.get_obj().value)
            # What is left (a rare case): a field kept back here while a live camera held the lock for one call
            # replaces a newer value of the camera at this write. `reset_for_start` clears it with the new arrays.
            data.update(self.pending_info)
            data.update(fields)
            self.pending_info.clear()
            self.info.get_obj().value = self.last_good["info"] = json.dumps(data).encode()[:INFO_SIZE - 1]

    # The warning arrays go by name, not by object: `reset_for_start` gives new array objects.
    def warning_items(self, name: str = "warnings") -> list:
        return self._json(name, [])

    def set_warning_items(self, items: list, name: str = "warnings") -> None:
        with self._array_lock(name):  # one writer process for each warning array: a write with no lock loses nothing
            getattr(self, name).get_obj().value = json.dumps(items).encode()[:INFO_SIZE - 1]

    def replace_warning_items(self, name: str, kinds: tuple, items: list) -> None:
        """Drop the items of `kinds` from the array `name` (`camera_warnings` or `group_warnings`), then add `items`."""
        kept = [item for item in self.warning_items(name) if item.get("kind") not in kinds]
        self.set_warning_items(kept + items, name)

    def reset_for_start(self) -> None:
        """A new camera process for "apply again" (8.3): the gate count stays (5.3), the rest starts again."""
        for flag in (self.connected, self.grabbing_frame, self.closing, self.closed, self.recording_in_progress,
                     self.is_recording_frame, self.should_pause, self.should_close, self.is_paused, self.updating,
                     self.error, self.search_requested):
            flag.value = False
        # Always new arrays (unix-capture.md 4.10): the old process is joined or killed by now, and it can have ended
        # while it held a lock. The new process gets them when it is spawned. The old arrays have no writer left, so
        # the warning items of the camera and the group are read with no lock.
        kept = {name: self._json(name, [], raw=getattr(self, name).get_obj().value)
                for name in ("camera_warnings", "group_warnings")}
        for name in ARRAYS:
            setattr(self, name, multiprocessing.Array("c", INFO_SIZE))
        self.holder_dead = False
        self.no_lock.clear()
        self.pending_info.clear()
        self.last_good.clear()
        for name, items in kept.items():
            self.set_warning_items(items, name)
        self.diagnostics = {}
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
            "warnings": self.warning_items() + self.warning_items("camera_warnings")
                        + self.warning_items("group_warnings"),  # camera-requests.md 1.5 [AC5B]
            "exposure_search": ({**info["exposure_search"], "count": self.search_count.value}
                                if info.get("exposure_search") else None),
            "controls": info.get("controls"),
            "diagnostics": self.diagnostics,
        }
