"""Frame rings: one shared-memory block per camera and pixel format (specs/frame-ring.md)."""
from skellycam.core.ipc.frame_ring.capture_check import check_jpeg
from skellycam.core.ipc.frame_ring.decode import (
    DecodeInput,
    DecodeStage,
    WaitingPlace,
    decode_jpeg,
    limit_libjpeg_warnings,
)
from skellycam.core.ipc.frame_ring.layout import (
    ERROR_FLAGS,
    LAYOUT_VERSION,
    MAGIC,
    NO_SAMPLE_NS,
    RING_HEADER_DTYPE,
    RING_HEADER_FORMAT,
    RING_HEADER_SIZE,
    SLOT_HEADER_DTYPE,
    SLOT_HEADER_FORMAT,
    SLOT_HEADER_SIZE,
    FrameFlag,
    PixelFormat,
    ring_total_size,
    rotation_to_cw_deg,
    slot_capacity,
    slot_count,
)
from skellycam.core.ipc.frame_ring.lifecycle import (
    CameraMode,
    CameraRingInfo,
    FrameRingCreator,
    camera_ring_info,
    create_session_rings,
    sweep_stale_rings,
)
from skellycam.core.ipc.frame_ring.reader import FrameRead, FrameRingReader, ReadResult
from skellycam.core.ipc.frame_ring.writer import FrameRingWriter
