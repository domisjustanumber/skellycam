"""Block layout of a frame ring (specs/frame-ring.md, sections 3 and 4)."""
import enum
import logging
import math
import struct
from multiprocessing import shared_memory

import numpy as np

from skellycam.core.camera.config.image_rotation_types import RotationTypes

logger = logging.getLogger(__name__)

MAGIC = b"SKR2"
LAYOUT_VERSION = 1
RING_HEADER_SIZE = 4096
SLOT_HEADER_SIZE = 64
TABLE_OFFSET = RING_HEADER_SIZE
PAGE_SIZE = 4096
FALLBACK_FPS = 60
NO_SAMPLE_NS = -2 ** 63  # INT64_MIN: `sample_ns` when capture gives no sample time (table 3.4)


class PixelFormat(enum.IntEnum):
    JPEG = 1
    BGR24 = 2


class FrameFlag(enum.IntFlag):
    OVERSIZE = 0x01
    CAPTURE_ERROR = 0x02
    NO_SOI_EOI = 0x04
    DECODE_ERROR = 0x08
    DISCONTINUITY = 0x10
    DHT_INSERTED = 0x20


ERROR_FLAGS = 0x0F

# (name, struct code, offset) of tables 3.3 and 3.4. Gaps are reserved bytes.
_RING_HEADER_FIELDS = (
    ("magic", "4s", 0), ("layout_version", "I", 4), ("header_size", "I", 8),
    ("pixel_format", "I", 12), ("slot_count", "I", 16), ("slot_capacity", "I", 20),
    ("table_offset", "Q", 24), ("payload_offset", "Q", 32), ("total_size", "Q", 40),
    ("width", "I", 48), ("height", "I", 52), ("fps_num", "I", 56), ("fps_den", "I", 60),
    ("camera_key", "16s", 64), ("camera_index", "I", 80), ("creator_pid", "I", 84),
    ("utc_ns", "q", 88), ("perf_ns", "q", 96), ("utc_offset_s", "i", 104), ("closed", "I", 108),
    ("history_ms", "I", 112), ("head", "q", 128), ("frames_committed", "Q", 192),
    ("oversize_count", "Q", 200), ("capture_error_count", "Q", 208), ("cut_off_count", "Q", 216),
    ("decode_error_count", "Q", 224), ("skipped_count", "Q", 232), ("dht_inserted_count", "Q", 240),
    ("largest_payload_len", "Q", 248),
)
_SLOT_HEADER_FIELDS = (
    ("frame_number", "q", 0), ("arrival_ns", "q", 8), ("sample_ns", "q", 16),
    ("published_ns", "q", 24), ("source_frame_number", "q", 32), ("payload_len", "I", 40),
    ("flags", "I", 44), ("payload_crc32", "I", 48), ("rotation_cw_deg", "I", 52),
    ("header_crc32", "I", 60),
)
_NUMPY_TYPES = {"4s": "S4", "16s": "S16", "I": "<u4", "i": "<i4", "Q": "<u8", "q": "<i8"}


def _layout(fields: tuple, size: int) -> tuple[np.dtype, str]:
    """The numpy dtype and the little-endian struct format of one header table."""
    fmt, end = "<", 0
    for _, code, offset in fields:
        fmt += (f"{offset - end}x" if offset > end else "") + code
        end = offset + struct.calcsize(code)
    dtype = np.dtype({"names": [name for name, _, _ in fields],
                      "formats": [_NUMPY_TYPES[code] for _, code, _ in fields],
                      "offsets": [offset for _, _, offset in fields],
                      "itemsize": size})
    return dtype, fmt + (f"{size - end}x" if size > end else "")


RING_HEADER_DTYPE, RING_HEADER_FORMAT = _layout(_RING_HEADER_FIELDS, RING_HEADER_SIZE)
SLOT_HEADER_DTYPE, SLOT_HEADER_FORMAT = _layout(_SLOT_HEADER_FIELDS, SLOT_HEADER_SIZE)

CLOSED_OFFSET = RING_HEADER_DTYPE.fields["closed"][1]
HEAD_OFFSET = RING_HEADER_DTYPE.fields["head"][1]
COUNTERS_OFFSET = RING_HEADER_DTYPE.fields["frames_committed"][1]  # 8 u64, to largest_payload_len


def slot_capacity(pixel_format: PixelFormat, width: int, height: int) -> int:
    """Table 3.6."""
    if pixel_format == PixelFormat.BGR24:
        return width * height * 3
    return _roundup(2 * 2048 + width * height, PAGE_SIZE)


def slot_count(history_s: float, fps: float | int | None) -> int:
    """Section 3.7: max(2, ceil(history_s x fps)), with 60 when capture reports no frame rate."""
    if fps is None or fps <= 0:
        logger.info(f"No frame rate reported ({fps}): the slot count uses {FALLBACK_FPS} fps")
        fps = FALLBACK_FPS
    return max(2, math.ceil(history_s * fps))


def payload_offset(slot_count: int) -> int:
    return _roundup(RING_HEADER_SIZE + SLOT_HEADER_SIZE * slot_count, PAGE_SIZE)


def ring_total_size(slot_count: int, slot_capacity: int) -> int:
    """Section 3.8."""
    return payload_offset(slot_count) + slot_count * slot_capacity


_ROTATION_CW_DEG = {
    RotationTypes.NO_ROTATION: 0,
    RotationTypes.CLOCKWISE_90: 90,
    RotationTypes.ROTATE_180: 180,
    RotationTypes.COUNTERCLOCKWISE_90: 270,
}


def rotation_to_cw_deg(rotation: RotationTypes) -> int:
    """Section 3.4: the config enum to degrees clockwise."""
    return _ROTATION_CW_DEG[rotation]


def attach_ring(name: str) -> tuple[shared_memory.SharedMemory, dict]:
    """Open a ring by name, check `magic` and `layout_version` (3.9), and read its header one time.

    `track=False`: the exit of this process must never unlink the ring (6.1, 7.6).
    """
    shm = shared_memory.SharedMemory(name=name, create=False, track=False)
    header = dict(zip(RING_HEADER_DTYPE.names, struct.unpack_from(RING_HEADER_FORMAT, shm.buf)))
    if header["magic"] != MAGIC or header["layout_version"] != LAYOUT_VERSION:
        shm.close()
        raise ValueError(f"Ring {name}: magic {header['magic']!r} and layout_version "
                         f"{header['layout_version']} are not {MAGIC!r} and {LAYOUT_VERSION}")
    return shm, header


def format_size(n: int) -> str:
    """ADR-9G2W item 16: a size in bytes and MiB."""
    return f"{n:,} bytes ({n / 2 ** 20:.1f} MiB)"


def _roundup(value: int, multiple: int) -> int:
    return -(-value // multiple) * multiple
