import logging
import multiprocessing
import time
from dataclasses import dataclass
from multiprocessing.sharedctypes import Synchronized

import numpy as np

from skellycam.core.camera_group.camera_status import CameraStatus
from skellycam.core.types.type_overloads import CameraIdString, SharedValue
from skellycam.utilities.wait_functions import await_10ms

logger = logging.getLogger(__name__)

CAMERA_STATE_TIMEOUT_SECONDS = 10.0
FRAME_LOCK_WAIT_S = 0.5  # the two check-then-set blocks of the last frame wait this long for its lock (unix 4.10)
# The read of each frame decision waits this long for that lock, once in each stretch with no lock: longer than a
# busy end of a take holds it (round 4: up to 1 s), shorter than the in-process stall rule of 2 s (W 9.5).
FRAME_READ_WAIT_S = 1.5


@dataclass
class CameraOrchestrator:
    camera_statuses: dict[CameraIdString, CameraStatus]
    first_recording_frame_number: SharedValue  # no lock: the main process is its one writer
    last_recording_frame_number: Synchronized
    frame_lock_lost: bool = False  # per process: the lock of the last frame did not come in FRAME_READ_WAIT_S

    @property
    def last_frame(self) -> int:
        """The last frame of the take, read and written with no lock (one aligned 8-byte value). The two
        check-then-set blocks and the read of each frame decision take the lock, with a bounded wait: a camera
        killed while it held the lock keeps it for ever (unix-capture.md 4.10)."""
        return self.last_recording_frame_number.get_obj().value

    @last_frame.setter
    def last_frame(self, value: int) -> None:
        self.last_recording_frame_number.get_obj().value = value

    @property
    def camera_ids(self) -> list[CameraIdString]:
        return list(self.camera_statuses.keys())

    @classmethod
    def from_statuses(cls, camera_statuses: dict[CameraIdString, CameraStatus]) -> 'CameraOrchestrator':
        return cls(camera_statuses=camera_statuses,
                   first_recording_frame_number=multiprocessing.Value("q", -1, lock=False),
                   last_recording_frame_number=multiprocessing.Value("q", -1))

    @property
    def gate_statuses(self) -> dict[CameraIdString, CameraStatus]:
        """The cameras that hold the gate back (5.2): `checking`, `too_slow`, `ready` and `recording`."""
        return {camera_id: status for camera_id, status in list(self.camera_statuses.items()) if status.in_gate}

    @property
    def all_ready(self) -> bool:
        return all([status.ready for status in list(self.camera_statuses.values())])

    def largest_gate_count(self) -> int:
        """A camera that joins the gate starts with the largest gate count of the group (5.2)."""
        return max((status.frame_count.value for status in self.gate_statuses.values()), default=-1)

    @property
    def all_cameras_paused(self):
        return all([status.is_paused.value for status in self.camera_statuses.values()])

    @property
    def any_cameras_alive(self) -> bool:
        return any([not status.closed.value for status in self.camera_statuses.values()])


    @property
    def camera_frame_counts(self) -> dict[CameraIdString, int]:
        return {camera_id: status.frame_count.value for camera_id, status in self.camera_statuses.items()}


    async def pause(self, await_paused: bool = True) -> None:
        logger.info("Pausing all cameras...")
        for status in self.gate_statuses.values():
            status.should_pause.value = True

        if await_paused:
            logger.info("Waiting for all cameras to pause...")
            await self._await_pause_state(paused=True)
            logger.trace("All cameras paused.")

    async def unpause(self, await_unpaused: bool = True) -> None:
        logger.info("Unpausing all cameras...")
        for status in self.camera_statuses.values():
            status.should_pause.value = False

        if await_unpaused:
            logger.info("Waiting for all cameras to unpause...")
            await self._await_pause_state(paused=False)
            logger.trace("All cameras unpaused.")

    async def _await_pause_state(self, paused: bool) -> None:
        action = "pause" if paused else "resume"
        deadline = time.monotonic() + CAMERA_STATE_TIMEOUT_SECONDS
        while True:
            unavailable = [
                camera_id for camera_id, status in self.gate_statuses.items()
                if status.error.value or status.closing.value
                or status.closed.value or status.should_close.value
            ]
            if unavailable:
                raise RuntimeError(f"Cannot {action}: cameras failed or closed: {unavailable}")
            pending = [
                camera_id for camera_id, status in self.gate_statuses.items()
                if bool(status.is_paused.value) != paused
            ]
            if not pending:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for cameras to {action}: {pending}")
            await await_10ms()

    def should_record_frame_number(self, frame_number: int | np.integer) -> tuple[bool, bool]:
        """(record, finish). A take records the group frames first to last - 1. With no take (first is -1)
        no frame is recorded: a stale last frame must not record again (open work, T-CAP-85 case 2)."""
        first, last = self.first_recording_frame_number.value, self._decision_last_frame()
        if first == -1:
            return False, False
        if last != -1 and frame_number >= last:
            return False, True
        return frame_number >= first, False

    def _decision_last_frame(self) -> int:
        """The last frame under its lock: the end of a take holds that lock from its read of the gate count to its
        write of the last frame, so no camera decides a new frame between them (round 4 of the fixes; the + 2
        margin covers one frame, not a busy main process). The first wait of a stretch with no lock is
        FRAME_READ_WAIT_S; the next reads try with no wait until the lock comes again, then read with no lock."""
        lock = self.last_recording_frame_number.get_lock()
        if not lock.acquire(timeout=0 if self.frame_lock_lost else FRAME_READ_WAIT_S):
            if not self.frame_lock_lost:
                logger.error(f"No lock of the last frame of the take in {FRAME_READ_WAIT_S:g} s; the frame decisions go "
                             f"on with no lock")
            self.frame_lock_lost = True
            return self.last_frame
        try:
            self.frame_lock_lost = False
            return self.last_frame
        finally:
            lock.release()

    def take_frame_count(self) -> int:
        """The group frames of the take that the stop ended (recorder.md 7.6): first to last - 1."""
        return self.last_frame - self.first_recording_frame_number.value

    def should_grab_by_id(self, camera_id: CameraIdString) -> bool:
        if not camera_id in self.camera_statuses:
            raise ValueError(f"Camera ID {camera_id} not found in orchestrator: {self.camera_statuses.keys()}")

        statuses = list(self.camera_statuses.values())
        states = [status.state for status in statuses]
        if "waiting" in states and "starting" not in states:
            return False  # the waiting cameras join now; they all start with the same gate count (9.4)
        gate = self.gate_statuses
        if any(status.should_pause.value for status in gate.values()):
            return False
        own = self.camera_statuses[camera_id].frame_count.value
        return all(own <= status.frame_count.value for status in gate.values())

    def close(self):
        """Signal closure; CameraManager owns bounded worker joins and escalation."""
        for status in self.camera_statuses.values():
            status.should_close.value = True
        logger.info("Requested closure of all cameras.")
