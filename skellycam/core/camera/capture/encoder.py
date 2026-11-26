"""The JPEG encode at capture of a YUY2 or NV12 frame (specs/windows-capture.md, sections 13.2 and 22.2; the names of
ADR-3WCA items 6 and 7, which section 22.6 states).

Quick Sync (`mjpeg_qsv` through PyAV) where the check of the main process gave true, else `cv2.imencode`. Both at
quality 90 with the chroma of the source. The JPEG is always full range [V6]: Quick Sync takes its input as full
range, so a limited-range frame gets the range-expanding table first; `cv2` converts with the decided range.
"""

import logging
import sys
from collections import deque
from dataclasses import replace
from fractions import Fraction

import cv2
import numpy as np

from skellycam.core.ipc.frame_ring.decode import map_levels, raw_to_bgr

logger = logging.getLogger(__name__)

QUALITY = 90  # notes: Encoder settings, one setting for both encoders
ASYNC_DEPTH = 2  # Quick Sync holds one frame [notes: Encoder settings]
_SAMPLING = {"YUY2": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_422, "NV12": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_420}
_PIX_FMT = {"YUY2": "yuyv422", "NV12": "nv12"}
_LEVELS = np.arange(256, dtype=np.float64)
TO_FULL_Y = np.clip(np.rint((_LEVELS - 16) * 255 / 219), 0, 255).astype(np.uint8)  # the range-expanding table [V6]
TO_FULL_C = np.clip(np.rint(128 + (_LEVELS - 128) * 255 / 224), 0, 255).astype(np.uint8)


def raw_shape(fmt: str, width: int, height: int) -> tuple:
    """13.2: YUY2 `(height, width, 2)`, NV12 `(height * 3 / 2, width)`."""
    return (height, width, 2) if fmt == "YUY2" else (height * 3 // 2, width)


def y_outside(raw: np.ndarray, fmt: str) -> tuple[int, int]:
    """13.3: (the Y values outside 16 to 235, all Y values) of one raw frame."""
    y = raw[..., 0] if fmt == "YUY2" else raw[: raw.shape[0] * 2 // 3]
    return int(np.count_nonzero((y < 16) | (y > 235))), int(y.size)


def cv2_jpeg(raw: np.ndarray, fmt: str, full_range: bool, quality: int = QUALITY) -> tuple[bytes, np.ndarray]:
    """(the JPEG, the BGR image that it encodes): the conversion with the decided range, then `cv2.imencode`."""
    bgr = raw_to_bgr(raw, fmt, full_range)
    params = [int(cv2.IMWRITE_JPEG_QUALITY), quality, int(cv2.IMWRITE_JPEG_SAMPLING_FACTOR), int(_SAMPLING[fmt])]
    return cv2.imencode(".jpg", bgr, params)[1].tobytes(), bgr


class QuickSyncEncoder:
    """`mjpeg_qsv` of PyAV at `async_depth` 2: `encode(raw)` gives the JPEGs that came out, in input order."""

    def __init__(self, fmt: str, width: int, height: int, quality: int):
        import av  # only where Quick Sync is used

        self._av, self.format, self.width, self.height = av, fmt, width, height
        context = av.CodecContext.create("mjpeg_qsv", "w")
        context.width, context.height, context.pix_fmt = width, height, _PIX_FMT[fmt]
        context.time_base = Fraction(1, 30)
        context.options = {"global_quality": str(quality), "async_depth": str(ASYNC_DEPTH)}
        context.color_range = 2  # full range in (MPEG range is 1)
        context.open()
        self._context, self._pts = context, 0

    def encode(self, raw: np.ndarray) -> list[bytes]:
        if raw.shape != raw_shape(self.format, self.width, self.height):
            raise ValueError(f"a raw frame of shape {raw.shape}")
        frame = self._av.VideoFrame.from_ndarray(raw, format=_PIX_FMT[self.format])  # a new frame: the encoder holds one
        frame.color_range, frame.pts = 2, self._pts
        self._pts += 1
        return [bytes(packet) for packet in self._context.encode(frame)]

    def flush(self) -> list[bytes]:
        return [bytes(packet) for packet in self._context.encode(None)]

    def close(self) -> None:
        self._context = None


def open_quick_sync_encoder(format: str, width: int, height: int, *, quality: int) -> QuickSyncEncoder:  # noqa: A002
    """ADR-3WCA item 7. Raises when Quick Sync does not open."""
    return QuickSyncEncoder(format, width, height, quality)


def quick_sync_works() -> bool:
    """The central check of 13.2 (ADR-3WCA item 6): encode one small test frame. Never on macOS [notes: JPEG
    encoder]. Any error gives False."""
    if sys.platform == "darwin":
        return False
    try:
        encoder = open_quick_sync_encoder("NV12", 320, 240, quality=QUALITY)
        try:
            jpegs = encoder.encode(np.full(raw_shape("NV12", 320, 240), 128, np.uint8)) + encoder.flush()
        finally:
            encoder.close()
    except Exception as error:  # no Intel GPU, no driver, a build of FFmpeg with no QSV
        logger.info(f"Quick Sync JPEG encoder not available ({type(error).__name__}: {error}); cv2.imencode is used")
        return False
    works = bool(jpegs) and jpegs[0][:2] == b"\xff\xd8"
    logger.info(f"Quick Sync JPEG encoder {'works' if works else 'gave no JPEG; cv2.imencode is used'}")
    return works


class FrameEncoder:
    """The encode of one open of a camera in YUY2 or NV12 (13.2, 22.2 [V3]).

    `feed(frame)` gives the frames whose JPEG is ready, in the order of the source: (frame, JPEG, BGR image or None).
    A raw frame of the wrong length is not encoded; its JPEG is `b""` (the loop flags it). Quick Sync holds a frame,
    so a frame can come out one call later. When Quick Sync fails, `cv2.imencode` encodes the held frames again from
    their raw frames and each later frame; the first frame out after the event gets the discontinuity [ring 4]. A
    call that gives no JPEG while more than `ASYNC_DEPTH` frames wait is a failure too (Q878): else the camera would
    publish nothing and hold the lockstep gate of each other camera. The queue only grows in a call with no JPEG, so
    it never holds more than `ASYNC_DEPTH` + 1 frames behind a held frame."""

    def __init__(self, fmt: str, width: int, height: int, full_range: bool, quick_sync: bool):
        self.format, self.width, self.height, self.full_range = fmt, width, height, full_range
        self.fallbacks = 0
        self.error: str | None = None  # the text of the last Quick Sync failure
        self._queue: deque[list] = deque()  # [frame, JPEG or None, BGR or None], in source order
        self.quick_sync = open_quick_sync_encoder(fmt, width, height, quality=QUALITY) if quick_sync else None

    @property
    def name(self) -> str:
        """The status field `jpeg_encoder` (22.2 [V3])."""
        return "quick_sync" if self.quick_sync is not None else "cv2"

    def feed(self, frame) -> list[tuple]:
        raw = frame.payload
        good = raw.shape == raw_shape(self.format, self.width, self.height)
        entry = [frame, None if good else b"", None]
        self._queue.append(entry)
        if good and self.quick_sync is None:
            entry[1], entry[2] = cv2_jpeg(raw, self.format, self.full_range)
        elif self.quick_sync is not None:
            jpegs = []
            try:
                if good:
                    jpegs = self.quick_sync.encode(raw if self.full_range else map_levels(raw, self.format, TO_FULL_Y,
                                                                                         TO_FULL_C))
            except Exception as error:
                self._fall_back(error)
            else:
                for jpeg, held in zip(jpegs, [e for e in self._queue if e[1] is None]):
                    held[1] = jpeg
                # Q878: more than its depth held and none given back. A short frame behind a held frame counts too
                # [ZEK6 16]: else frames of the wrong length could pile up behind it.
                if not jpegs and len(self._queue) > ASYNC_DEPTH and self._queue[0][1] is None:
                    self._fall_back(RuntimeError(f"no JPEG came out for {len(self._queue)} frames"))
        ready = []
        while self._queue and self._queue[0][1] is not None:
            ready.append(tuple(self._queue.popleft()))
        return ready

    def _fall_back(self, error: Exception) -> None:
        self.fallbacks += 1
        self.error = f"{type(error).__name__}: {error}"
        self.close()
        for entry in self._queue:
            if entry[1] is None:
                entry[1], entry[2] = cv2_jpeg(entry[0].payload, self.format, self.full_range)
        self._queue[0][0] = replace(self._queue[0][0], discontinuity=True)

    def close(self) -> None:
        """Frames that the encoder still holds are dropped: the loop gave them no frame number yet."""
        encoder, self.quick_sync = self.quick_sync, None
        if encoder is not None:
            try:
                encoder.close()
            except Exception as error:  # a failed device; the close goes on
                logger.debug(f"Quick Sync encoder close: {type(error).__name__}: {error}")
