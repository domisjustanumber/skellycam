"""The decode stage of a BGR ring and its waiting place (specs/frame-ring.md, section 8)."""
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

from skellycam.core.ipc.frame_ring.layout import ERROR_FLAGS, FrameFlag
from skellycam.core.ipc.frame_ring.writer import FrameRingWriter

logger = logging.getLogger(__name__)

TAKE_TIMEOUT_S = 0.1  # 8.3: at least 100 ms; only for the shutdown check
WARNING_INTERVAL_S = 60.0  # 8.9: one log line per different line per minute at most
_YUV_TO_BGR = {"YUY2": cv2.COLOR_YUV2BGR_YUY2, "NV12": cv2.COLOR_YUV2BGR_NV12}  # ADR-467Z item 4


@dataclass(frozen=True)
class DecodeInput:
    """One frame for the decode thread, with the numbers and times of its JPEG frame (8.6).

    `source` is "JPEG" (`payload` is `bytes`), "BGR" (`(h, w, 3)` uint8), "YUY2" (`(h, w, 2)`
    uint8) or "NV12" (`(h * 3 // 2, w)` uint8). `flags` are the flags of the JPEG frame.
    """
    payload: bytes | np.ndarray
    source: str
    frame_number: int
    arrival_ns: int
    sample_ns: int
    source_frame_number: int
    flags: int
    rotation_cw_deg: int


class WaitingPlace:
    """Holds one frame at most (8.3). A new frame replaces a frame that waits, and the replaced
    frame counts in `skipped`. The capture thread never waits longer than the time to take the lock."""

    def __init__(self):
        self._condition = threading.Condition()
        self._item: DecodeInput | None = None
        self.skipped = 0

    def put(self, item: DecodeInput) -> None:
        with self._condition:
            if self._item is not None:
                self.skipped += 1
            self._item = item
            self._condition.notify()

    def take(self, timeout_s: float) -> DecodeInput | None:
        """The frame that waits, or `None` after `timeout_s`."""
        with self._condition:
            if self._item is None:
                self._condition.wait(timeout_s)
            item, self._item = self._item, None
            return item


def decode_jpeg(payload: bytes) -> np.ndarray | None:
    """Step 3 of 8.4."""
    return cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)


class DecodeStage:
    """The one decode thread of a camera and the only writer of its BGR ring (8.2).

    `stop()` stops and joins the thread. Call it after the last `put`. It drops a frame that
    waits and counts it as skipped (ADR-467Z item 2). It does not close the writer.
    """

    def __init__(self, writer: FrameRingWriter, *, decode=decode_jpeg):
        self.waiting_place = WaitingPlace()
        self._writer = writer
        self._decode = decode
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"decode {writer.name}", daemon=True)
        self.decoded = 0  # JPEG decodes, `decoded_by_skellycam` (unix-capture.md D-10)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._thread.is_alive():
            self._thread.join()
        if self.waiting_place.take(0.0) is not None:
            self.waiting_place.skipped += 1
        self._writer.set_skipped_count(self.waiting_place.skipped)
        logger.info(f"BGR ring {self._writer.name}: {self._writer._counters[0]} frames committed, "
                    f"{self.waiting_place.skipped} skipped, {self._writer._counters[4]} decode errors")

    def _run(self) -> None:
        place, writer = self.waiting_place, self._writer
        while not self._stopping.is_set():
            item = place.take(TAKE_TIMEOUT_S)
            if item is None:
                continue
            flags = item.flags
            bgr = None
            if not flags & ERROR_FLAGS:  # 8.4 step 2: a flagged frame never reaches the decoder
                try:
                    bgr = self._to_bgr(item)
                except Exception as error:
                    # debug only: decode_error_count records each failure (8.5), and a log line per frame floods
                    logger.debug(f"Decode of frame {item.frame_number} for {writer.name} failed: {error}")
                if bgr is None or bgr.shape != writer.shape:  # 8.4 step 4
                    flags |= FrameFlag.DECODE_ERROR
                    bgr = None
            try:
                writer.write(bgr, frame_number=item.frame_number, arrival_ns=item.arrival_ns,
                             sample_ns=item.sample_ns, source_frame_number=item.source_frame_number,
                             flags=flags, rotation_cw_deg=item.rotation_cw_deg)
                writer.set_skipped_count(place.skipped)
            except Exception:
                logger.exception(f"BGR ring write of frame {item.frame_number} for {writer.name} failed")

    def _to_bgr(self, item: DecodeInput) -> np.ndarray | None:
        if item.source == "JPEG":
            self.decoded += 1
            return self._decode(item.payload)
        if item.source == "BGR":  # 8.7 and 8.8: a new array that the writer copies into the slot
            return item.payload
        return cv2.cvtColor(item.payload, _YUV_TO_BGR[item.source])


_libjpeg_lock = threading.Lock()
_libjpeg_limited = False


def limit_libjpeg_warnings() -> None:
    """Limit the libjpeg warnings on descriptor 2 (8.9). The camera process calls it at start.

    The log level of OpenCV 5.1.0 does not control these lines. Thus descriptor 2 goes to a pipe,
    and a thread forwards each different line to the log one time per minute at most, as
    `<line> (count <n>)`. `sys.stderr` stays on the old descriptor 2, so that the output of
    Python is not limited. A second call does nothing.

    Windows: no redirect here. The OpenCV wheel has its own C runtime with its own copy of the
    descriptor 2 handle. A redirect would close that handle, and libjpeg would then write to a
    closed handle, which the OS can give again to another object (ADR-E817). Instead, the main
    process gives the camera process a pipe as its standard error before OpenCV loads, and limits
    the lines (`skellycam/core/camera/capture/warning_pipe.py`, D42).
    """
    global _libjpeg_limited
    with _libjpeg_lock:
        if _libjpeg_limited:
            return
        _libjpeg_limited = True
        if sys.platform == "win32":
            logger.debug("libjpeg warnings: on Windows, the main process limits them (warning_pipe, D42)")
            return
        sys.stderr.flush()
        old_stderr = os.dup(2)
        read_fd, write_fd = os.pipe()
        os.dup2(write_fd, 2)
        os.close(write_fd)
        sys.stderr = open(old_stderr, "w", buffering=1, errors="backslashreplace")
        threading.Thread(target=_forward_lines, args=(read_fd,), name="libjpeg warnings", daemon=True).start()


def _forward_lines(read_fd: int) -> None:
    """Block on the pipe (8.10). Log a line at its first time, then one time per minute at most."""
    last_logged: dict[str, float] = {}
    counts: dict[str, int] = {}
    with open(read_fd, encoding="utf-8", errors="replace") as pipe:  # UTF-8 on each OS (ADR-PDD3 W7)
        for line in pipe:
            line = line.rstrip()
            if not line:
                continue
            counts[line] = counts.get(line, 0) + 1
            now = time.monotonic()
            if now - last_logged.get(line, -WARNING_INTERVAL_S) >= WARNING_INTERVAL_S:
                logger.warning(f"{line} (count {counts[line]})")
                last_logged[line] = now
                counts[line] = 0
