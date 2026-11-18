"""A reader of a frame ring (specs/frame-ring.md, section 6).

A reader copies the slot header and the payload out, then checks the CRC-32 values of its private
copy. It never writes to the block, and `head` is only a hint.
"""
import enum
import struct
import zlib
from dataclasses import dataclass

from skellycam.core.ipc.frame_ring.layout import (
    CLOSED_OFFSET,
    ERROR_FLAGS,
    HEAD_OFFSET,
    SLOT_HEADER_FORMAT,
    SLOT_HEADER_SIZE,
    FrameFlag,
    attach_ring,
)

_SLOT = struct.Struct(SLOT_HEADER_FORMAT)
_CRC_END = SLOT_HEADER_SIZE - 4
_U32 = struct.Struct("<I")
_I64 = struct.Struct("<q")


class ReadResult(enum.Enum):
    OK = enum.auto()
    NOT_YET_WRITTEN = enum.auto()
    LAPPED = enum.auto()
    MISSING = enum.auto()
    CORRUPT = enum.auto()
    OVERSIZE = enum.auto()
    FLAGGED = enum.auto()
    CLOSED = enum.auto()


@dataclass(frozen=True)
class FrameRead:
    result: ReadResult
    frame_number: int
    arrival_ns: int
    sample_ns: int
    published_ns: int
    source_frame_number: int
    flags: int
    rotation_cw_deg: int
    payload_len: int
    payload: bytes | None


def _no_frame(result: ReadResult, frame_number: int) -> FrameRead:
    return FrameRead(result, frame_number, 0, 0, 0, 0, 0, 0, 0, None)


class FrameRingReader:
    def __init__(self, name: str):
        self._shm, header = attach_ring(name)
        self._view = self._shm.buf.toreadonly()
        self._slot_count = header["slot_count"]
        self._slot_capacity = header["slot_capacity"]
        self._table_offset = header["table_offset"]
        self._payload_offset = header["payload_offset"]
        self.failed_checks = 0

    @classmethod
    def attach(cls, name: str) -> "FrameRingReader":
        return cls(name)

    def read(self, frame_number: int) -> FrameRead:
        """Read frame `frame_number` (steps R1 to R13 of 6.2, retry rule of 6.4)."""
        view = self._view
        if _U32.unpack_from(view, CLOSED_OFFSET)[0]:  # R1
            return _no_frame(ReadResult.CLOSED, frame_number)
        head = _I64.unpack_from(view, HEAD_OFFSET)[0]
        if head < 0 or frame_number > head:  # R2
            return _no_frame(ReadResult.NOT_YET_WRITTEN, frame_number)
        if head - frame_number >= self._slot_count:  # R3
            return _no_frame(ReadResult.LAPPED, frame_number)
        slot = frame_number % self._slot_count
        header_at = self._table_offset + SLOT_HEADER_SIZE * slot
        payload_at = self._payload_offset + slot * self._slot_capacity
        first_header = None
        for _ in range(2):
            header = view[header_at:header_at + SLOT_HEADER_SIZE].tobytes()  # R4
            fields = _SLOT.unpack(header)
            number, payload_len, flags, payload_crc, _, header_crc = fields[0], *fields[5:]
            if number == -1:  # R5, before the CRC check: the writer is in this slot, or died in it [A58]
                return _no_frame(ReadResult.LAPPED, frame_number)
            if zlib.crc32(header[:_CRC_END]) == header_crc:  # R5
                if 0 <= number < frame_number:  # R6
                    return _no_frame(ReadResult.MISSING, frame_number)
                if number != frame_number:  # R7
                    return _no_frame(ReadResult.LAPPED, frame_number)
                if flags & FrameFlag.OVERSIZE:  # R8
                    return _header_only(ReadResult.OVERSIZE, fields)
                if flags & ERROR_FLAGS:  # R9
                    return _header_only(ReadResult.FLAGGED, fields)
                if payload_len <= self._slot_capacity:  # R10
                    payload = view[payload_at:payload_at + payload_len].tobytes()  # R11
                    if zlib.crc32(payload) == payload_crc:  # R12
                        return FrameRead(ReadResult.OK, *fields[:5], flags, fields[8], payload_len, payload)  # R13
            self.failed_checks += 1
            if first_header is None:
                first_header = header
            elif header == first_header:
                # The writer did not touch the slot between the two copies: the stored bytes are bad.
                return _no_frame(ReadResult.CORRUPT, frame_number)
        return _no_frame(ReadResult.LAPPED, frame_number)

    def read_newest(self) -> FrameRead:
        """Section 6.5: read `head`; on `LAPPED`, read `head` again one more time."""
        read = self.read(_I64.unpack_from(self._view, HEAD_OFFSET)[0])
        if read.result is ReadResult.LAPPED:
            read = self.read(_I64.unpack_from(self._view, HEAD_OFFSET)[0])
        return read

    def read_nearest(self, t_ns: int) -> FrameRead:
        """Section 6.5: the frame whose `arrival_ns` is nearest to `t_ns` (perf_counter_ns clock)."""
        view = self._view
        head = _I64.unpack_from(view, HEAD_OFFSET)[0]
        if _U32.unpack_from(view, CLOSED_OFFSET)[0]:
            return _no_frame(ReadResult.CLOSED, head)
        if head < 0:
            return _no_frame(ReadResult.NOT_YET_WRITTEN, head)
        table = view[self._table_offset:self._table_offset + SLOT_HEADER_SIZE * self._slot_count].tobytes()
        oldest = max(0, head - self._slot_count + 1)
        best = arrival = None
        for offset in range(0, len(table), SLOT_HEADER_SIZE):
            row = _SLOT.unpack_from(table, offset)
            if row[0] < oldest or zlib.crc32(table[offset:offset + _CRC_END]) != row[9]:
                continue
            key = (abs(row[1] - t_ns), row[0])  # a tie goes to the lower frame number
            if best is None or key < best:
                best, arrival = key, row[1]
        if best is None:
            return _no_frame(ReadResult.LAPPED, head)
        number = best[1]
        read = self.read(number)
        if read.result is ReadResult.OK and read.arrival_ns != arrival:
            return _no_frame(ReadResult.LAPPED, number)
        return read

    def close(self) -> None:
        """Release the view before `close()`: an open view makes `close()` raise `BufferError`."""
        self._view.release()
        self._shm.close()


def _header_only(result: ReadResult, fields: tuple) -> FrameRead:
    return FrameRead(result, *fields[:5], fields[6], fields[8], fields[5], None)
