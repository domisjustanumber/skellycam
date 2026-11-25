"""The per-camera preview message and its sender (specs/preview.md, step 4a).

Step 4a gives the sender no route. Step 4b connects it to the websocket endpoint (spec section 10).
"""
import asyncio
import contextlib
import json
import logging
import struct
import time
from collections.abc import Awaitable, Callable  # noqa: TC003 — beartype checks annotations at runtime
from dataclasses import dataclass
from typing import TYPE_CHECKING, no_type_check

from skellycam.api.websocket.websocket_message_types import WebsocketMessageType
from skellycam.core.capture_timings import OFF_SET
from skellycam.core.ipc.frame_ring import FrameRead, ReadResult
from skellycam.core.recorders.framerate_tracker import ServerFramerateCalculator

if TYPE_CHECKING:
    from skellycam.core.camera_group.camera_group_manager import CameraGroupManager

logger = logging.getLogger(__name__)

CAMERA_FRAME_VERSION: int = 1
CAMERA_FRAME_HEADER = struct.Struct("<B3xIqqII16s")

PASS_INTERVAL_S = 0.01
TICK_INTERVAL_S = 0.25
SAFETY_NET_S = 1.0
_SENT_RESULTS = (ReadResult.OK, ReadResult.FLAGGED, ReadResult.OVERSIZE)


def _camera_id_bytes(camera_id: str) -> bytes:
    raw = camera_id.encode("ascii")  # UnicodeEncodeError is a ValueError
    if len(raw) > 16:
        raise ValueError(f"camera id {camera_id} is longer than 16 bytes")
    return raw


def pack_camera_frame(camera_id: str, read: FrameRead) -> bytes:
    """The camera message of `read` (3.2). `read.result` is OK, FLAGGED or OVERSIZE.
    Raises ValueError for a camera id that is not ASCII or longer than 16 bytes."""
    jpeg = read.payload if read.result is ReadResult.OK else b""
    return CAMERA_FRAME_HEADER.pack(CAMERA_FRAME_VERSION, read.flags, read.frame_number, read.arrival_ns,
                                    read.rotation_cw_deg, len(jpeg), _camera_id_bytes(camera_id)) + jpeg


def _feed(rate: ServerFramerateCalculator, read: FrameRead) -> None:
    # The OpenCV loop before phase 3 writes source_frame_number -1 (6.3).
    rate.update(read.frame_number if read.source_frame_number == -1 else read.source_frame_number, read.arrival_ns)


@dataclass
class _CameraState:
    """The state of one camera for one connection (4.2)."""
    reader: object
    rate: ServerFramerateCalculator
    last_tried: int = -1
    last_sent: int = -1
    ready: bool = True
    sent_at: float = 0.0
    skipped_at_send: int = 0
    not_shown: int = 0
    bad_id_logged: bool = False


class PreviewRelay:
    """Sends the camera messages of one websocket connection (sections 4 to 7)."""

    @no_type_check  # beartype: the tests give a fake manager with the same attributes (ADR-24FZ)
    def __init__(self, camera_group_manager: "CameraGroupManager",
                 send_bytes: Callable[[bytes], Awaitable[None]],
                 send_json: Callable[[object], Awaitable[None]], step_set=None) -> None:
        # `step_set`: the preview steps of the connection (capture-timings.md 6.5); None measures nothing
        self._steps = OFF_SET if step_set is None else step_set
        self._manager = camera_group_manager
        self._send_bytes = send_bytes
        self._send_json = send_json
        self._cameras: dict[str, _CameraState] = {}
        self._wake = asyncio.Event()

    async def run(self) -> None:
        """Passes (4.3) and ticks (6.2, 6.3) until the task is cancelled."""
        next_tick = time.monotonic()
        while True:
            self._wake.clear()
            if not self._manager.closing:
                await self._pass()
            if not self._manager.closing and time.monotonic() >= next_tick:
                next_tick = time.monotonic() + TICK_INTERVAL_S
                await self._tick()
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(PASS_INTERVAL_S):
                    await self._wake.wait()

    def handle_text(self, text: str) -> bool:
        """A ready message (4.1): mark the camera ready, wake `run`, return True. Else False."""
        try:
            data = json.loads(text)
        except ValueError:
            return False
        if not isinstance(data, dict) or data.get("message_type") != "camera_ready":
            return False
        camera_id = data.get("camera_id")
        if not isinstance(camera_id, str):
            logger.warning(f"Preview: a camera_ready message with no valid camera_id: {text[:200]}")
            return True
        state = self._cameras.get(camera_id)  # an unknown camera can be removed while the message travels
        if state is not None and not state.ready:
            state.ready = True
            self._wake.set()
        return True

    def _state(self, camera_id: str, reader: object) -> _CameraState:
        """Step 1 of 4.3: the state of the camera, with the new-ring rule of 4.2."""
        state = self._cameras.get(camera_id)
        if state is None:
            state = self._cameras[camera_id] = _CameraState(reader, ServerFramerateCalculator(source_name=camera_id))
        elif state.reader is not reader:
            state.reader = reader
            state.last_tried = state.last_sent = -1
            state.skipped_at_send = 0
        return state

    async def _pass(self) -> None:
        # Copies of the dicts, and a new look-up of each reader: CameraGroup can change them during each await (5.1).
        for group in list(self._manager.camera_groups.values()):
            for camera_id in list(group.ring_readers):
                if self._manager.closing:
                    return
                reader = group.ring_readers.get(camera_id)
                if reader is None:
                    continue
                state = self._state(camera_id, reader)
                if not state.ready and time.monotonic() - state.sent_at < SAFETY_NET_S:
                    continue
                try:
                    _camera_id_bytes(camera_id)
                except ValueError:
                    if not state.bad_id_logged:
                        state.bad_id_logged = True
                        logger.error(f"Preview: camera id {camera_id} is not ASCII or is longer than 16 bytes; "
                                     f"no camera message for it")
                    continue
                steps = self._steps
                control = steps.control
                on = control.on
                if on:
                    t0 = control.clock()
                read = self._newest_unsent(state, reader)
                if read is None:
                    continue
                if on:
                    t1 = control.clock()
                    steps.add((group.id, camera_id, "preview_ring_read"), t1 - t0)
                message = pack_camera_frame(camera_id, read)
                if on:
                    t2 = control.clock()
                    steps.add((group.id, camera_id, "preview_pack"), t2 - t1)
                skipped = reader.skipped_count
                if state.last_sent >= 0:
                    state.not_shown += (read.frame_number - state.last_sent - 1) - (skipped - state.skipped_at_send)
                state.skipped_at_send = skipped
                state.last_sent = read.frame_number
                state.ready = False
                state.sent_at = time.monotonic()
                _feed(state.rate, read)
                if on:
                    t3 = control.clock()
                    steps.add((group.id, camera_id, "published_to_send"), t3 - read.published_ns)
                await self._send_bytes(message)
                if on:
                    steps.add((group.id, camera_id, "preview_send"), control.clock() - t3)
        present = {camera_id for group in self._manager.camera_groups.values() for camera_id in group.ring_readers}
        for camera_id in self._cameras.keys() - present:
            del self._cameras[camera_id]

    @staticmethod
    def _newest_unsent(state: _CameraState, reader: object) -> FrameRead | None:
        """Steps 4 to 7 of 4.3: the newest frame to send, or None. A camera with no new frame costs no copy."""
        check = reader.read(state.last_tried + 2)
        if check.result is ReadResult.CLOSED:
            return None
        if check.result is ReadResult.NOT_YET_WRITTEN:
            read = reader.read(state.last_tried + 1)
            if read.result in (ReadResult.NOT_YET_WRITTEN, ReadResult.CLOSED):
                return None
        else:
            read = reader.read_newest()
        if read.result is not ReadResult.LAPPED:
            state.last_tried = read.frame_number
        if read.result in _SENT_RESULTS and read.frame_number > state.last_sent:
            return read
        return None

    async def _tick(self) -> None:
        """6.2 and 6.3: read each camera first, then send. No read after the first send (5.1)."""
        messages = []
        for group in self._manager.camera_groups.values():
            cameras = {}
            for camera_id, reader in group.ring_readers.items():
                state = self._state(camera_id, reader)
                newest = reader.read_newest()
                if newest.result in _SENT_RESULTS:
                    _feed(state.rate, newest)
                cameras[camera_id] = {
                    "delivered_framerate": state.rate.current_framerate,
                    "not_shown_count": state.not_shown,
                    "ring_skipped_count": reader.skipped_count,
                    "oversize_count": reader.oversize_count,
                }
                state.rate.clear()
            if cameras:
                messages.append({"message_type": WebsocketMessageType.FRAMERATE_UPDATE,
                                 "camera_group_id": group.id, "cameras": cameras})
        for message in messages:
            await self._send_json(message)
