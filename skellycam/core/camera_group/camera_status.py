import json
import multiprocessing
from multiprocessing.sharedctypes import Synchronized
from dataclasses import dataclass, field
from typing import Any

# The camera states of specs/windows-capture.md, section 8.1. "recording" is `ready` with a recording that runs.
STATES = ("starting", "waiting", "failed", "checking", "too_slow", "ready", "recording", "dead")
GATE_STATES = ("checking", "too_slow", "ready")  # 5.2: only these hold the gate back
SETTLED_STATES = ("waiting", "failed", "checking", "too_slow", "ready", "dead")
INFO_SIZE = 16384


@dataclass
class CameraStatus:
    connected: Synchronized = field(default_factory=lambda: multiprocessing.Value("b", False))
    grabbing_frame: Synchronized = field(default_factory=lambda: multiprocessing.Value("b", False))
    closing: Synchronized = field(default_factory=lambda: multiprocessing.Value("b", False))
    closed: Synchronized = field(default_factory=lambda: multiprocessing.Value("b", False))
    recording_in_progress: Synchronized = field(default_factory=lambda: multiprocessing.Value("b", False))
    is_recording_frame: Synchronized = field(default_factory=lambda: multiprocessing.Value("b", False))
    should_pause: Synchronized = field(default_factory=lambda: multiprocessing.Value("b", False))
    should_close: Synchronized = field(default_factory=lambda: multiprocessing.Value("b", False))
    is_paused: Synchronized = field(default_factory=lambda: multiprocessing.Value("b", False))
    updating: Synchronized = field(default_factory=lambda: multiprocessing.Value("b", False))
    error: Synchronized = field(default_factory=lambda: multiprocessing.Value("b", False))

    frame_count: Synchronized = field(default_factory=lambda: multiprocessing.Value("q", -1))
    # Frames replaced in the waiting place since the first frame in the gate, as the stop line (5.2, 8.4).
    replaced_count: Synchronized = field(default_factory=lambda: multiprocessing.Value("q", 0))
    state_index: Synchronized = field(default_factory=lambda: multiprocessing.Value("b", -1))
    # JSON that only the camera process writes: failure, mode, measured_fps, controls, source (8.4).
    info: Any = field(default_factory=lambda: multiprocessing.Array("c", INFO_SIZE))
    # JSON that only the main process writes: the warning items of the recording that runs (11.3).
    warnings: Any = field(default_factory=lambda: multiprocessing.Array("c", INFO_SIZE))

    @property
    def state(self) -> str | None:
        index = self.state_index.value
        return STATES[index] if index >= 0 else None

    def set_state(self, state: str | None) -> None:
        self.state_index.value = -1 if state is None else STATES.index(state)

    @property
    def in_gate(self) -> bool:
        return self.state in GATE_STATES or self.state is None  # None: the phase 2 loop, which sets no state

    @property
    def ready(self) -> bool:
        if self.state is None:  # the phase 2 loop (opencv_camera_loop.py) and its tests
            return all([self.connected.value, not self.should_pause.value, not self.should_close.value,
                        not self.closing.value, not self.closed.value, not self.updating.value,
                        not self.error.value])
        return self.state == "ready" and not self.should_pause.value and not self.should_close.value

    def info_dict(self) -> dict:
        raw = self.info.value
        return json.loads(raw) if raw else {}

    def update_info(self, **fields) -> None:
        with self.info.get_lock():
            data = self.info_dict()
            data.update(fields)
            self.info.value = json.dumps(data).encode()[:INFO_SIZE - 1]

    def warning_items(self) -> list:
        raw = self.warnings.value
        return json.loads(raw) if raw else []

    def set_warning_items(self, items: list) -> None:
        self.warnings.value = json.dumps(items).encode()[:INFO_SIZE - 1]

    def reset_for_start(self) -> None:
        """A new camera process for "apply again" (8.3): the gate count stays (5.3), the rest starts again."""
        for flag in (self.connected, self.grabbing_frame, self.closing, self.closed, self.recording_in_progress,
                     self.is_recording_frame, self.should_pause, self.should_close, self.is_paused, self.updating,
                     self.error):
            flag.value = False
        self.info.value = b""
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
            "warnings": self.warning_items(),
            "controls": info.get("controls"),
        }
