"""The one writer of a frame ring (specs/frame-ring.md, sections 5.3 to 5.8 and 7.4)."""
import logging
import struct
import time
import zlib

from skellycam.core.ipc.frame_ring.layout import (
    CLOSED_OFFSET,
    COUNTERS_OFFSET,
    ERROR_FLAGS,
    HEAD_OFFSET,
    SLOT_HEADER_FORMAT,
    SLOT_HEADER_SIZE,
    FrameFlag,
    attach_ring,
    format_size,
)

logger = logging.getLogger(__name__)

LARGEST_PAYLOAD_LOG_INTERVAL_NS = 60 * 10 ** 9
WARN_FRACTION = 0.5

_SLOT_BODY = struct.Struct(SLOT_HEADER_FORMAT[:-1])  # bytes 0 to 59, without header_crc32
_U32 = struct.Struct("<I")
_I64 = struct.Struct("<q")
_COUNTERS = struct.Struct("<8Q")
# Index in the counters (table 3.3, offsets 192 to 255) of the counter of each flag.
_FRAMES_COMMITTED, _SKIPPED, _LARGEST = 0, 5, 7
_FLAG_COUNTERS = ((1, FrameFlag.OVERSIZE), (2, FrameFlag.CAPTURE_ERROR), (3, FrameFlag.NO_SOI_EOI),
                  (4, FrameFlag.DECODE_ERROR), (6, FrameFlag.DHT_INSERTED))


class FrameRingWriter:
    def __init__(self, name: str):
        self._shm, header = attach_ring(name)
        self._name = name
        self._buf = self._shm.buf
        self._slot_count = header["slot_count"]
        self._slot_capacity = header["slot_capacity"]
        self._table_offset = header["table_offset"]
        self._payload_offset = header["payload_offset"]
        self._counters = list(_COUNTERS.unpack_from(self._buf, COUNTERS_OFFSET))
        self._header = bytearray(SLOT_HEADER_SIZE)
        self._header_body = memoryview(self._header)[:_SLOT_BODY.size]
        self._last_rotation: int | None = None
        self._warned = False
        self._last_log_ns = time.perf_counter_ns()

    @classmethod
    def attach(cls, name: str) -> "FrameRingWriter":
        return cls(name)

    def write(self, payload: bytes, *, frame_number: int, arrival_ns: int, sample_ns: int,
              source_frame_number: int, flags: int, rotation_cw_deg: int,
              newer_frame_waiting: bool = False) -> None:
        """Write frame `frame_number` (steps W1 to W7 of 5.4). Never blocks or waits."""
        buf = self._buf
        if _U32.unpack_from(buf, CLOSED_OFFSET)[0]:
            return
        counters = self._counters
        if newer_frame_waiting:
            counters[_SKIPPED] += 1
            _COUNTERS.pack_into(buf, COUNTERS_OFFSET, *counters)
            return
        length = len(payload)
        if length > self._slot_capacity:
            flags |= FrameFlag.OVERSIZE
        if self._last_rotation is not None and (rotation_cw_deg - self._last_rotation) % 180:
            flags |= FrameFlag.DISCONTINUITY
        copy = not flags & ERROR_FLAGS
        crc = zlib.crc32(payload) if copy else 0  # W1
        slot = frame_number % self._slot_count
        header_at = self._table_offset + SLOT_HEADER_SIZE * slot
        # W2 before W3: the slot header no longer passes its CRC or holds the old number, so a
        # reader that copies a half-written payload rejects it.
        _I64.pack_into(buf, header_at, -1)
        if copy:
            payload_at = self._payload_offset + slot * self._slot_capacity
            buf[payload_at:payload_at + length] = payload  # W3, the one copy (5.7)
        published_ns = time.perf_counter_ns()
        _SLOT_BODY.pack_into(self._header, 0, frame_number, arrival_ns, sample_ns, published_ns,
                             source_frame_number, length, flags, crc, rotation_cw_deg)
        _U32.pack_into(self._header, _SLOT_BODY.size, zlib.crc32(self._header_body))  # W4
        buf[header_at:header_at + SLOT_HEADER_SIZE] = self._header  # W5
        _I64.pack_into(buf, HEAD_OFFSET, frame_number)  # W6
        counters[_FRAMES_COMMITTED] += 1  # W7
        for index, flag in _FLAG_COUNTERS:
            if flags & flag:
                counters[index] += 1
        if length > counters[_LARGEST]:
            counters[_LARGEST] = length
        _COUNTERS.pack_into(buf, COUNTERS_OFFSET, *counters)
        self._last_rotation = rotation_cw_deg
        if not self._warned and length > WARN_FRACTION * self._slot_capacity:
            self._warned = True
            logger.warning(f"Frame ring {self._name}: frame {frame_number} is {format_size(length)}, "
                           f"{length / self._slot_capacity:.2f} of its slot of "
                           f"{format_size(self._slot_capacity)} (warning limit {WARN_FRACTION:.2f})")
        if published_ns - self._last_log_ns >= LARGEST_PAYLOAD_LOG_INTERVAL_NS:
            self.log_largest_payload()

    def log_largest_payload(self) -> None:
        """Log the largest frame as a fraction of the slot (5.8)."""
        self._last_log_ns = time.perf_counter_ns()
        largest = self._counters[_LARGEST]
        logger.info(f"Frame ring {self._name}: largest frame {format_size(largest)} is "
                    f"{largest / self._slot_capacity:.2f} of its slot of {format_size(self._slot_capacity)}; "
                    f"{self._counters[1]} oversize")

    def close(self) -> None:
        if self._shm.buf is None:
            return
        if self._counters[_FRAMES_COMMITTED]:
            self.log_largest_payload()
        self._header_body.release()
        self._buf = None
        self._shm.close()
