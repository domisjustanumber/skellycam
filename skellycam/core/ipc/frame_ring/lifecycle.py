"""Creation, naming, close and cleanup of the frame rings (specs/frame-ring.md, section 7)."""
import logging
import os
import struct
import sys
import time
from dataclasses import dataclass
from fractions import Fraction
from multiprocessing import shared_memory

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.ipc.frame_ring.layout import (
    CLOSED_OFFSET,
    LAYOUT_VERSION,
    MAGIC,
    RING_HEADER_DTYPE,
    RING_HEADER_FORMAT,
    RING_HEADER_SIZE,
    SLOT_HEADER_SIZE,
    TABLE_OFFSET,
    PixelFormat,
    format_size,
    payload_offset,
    ring_total_size,
    rotation_to_cw_deg,
    slot_capacity,
    slot_count,
)

logger = logging.getLogger(__name__)

NAME_PREFIX = "skc"
LINUX_SHM_DIR = "/dev/shm"
CREATOR_PID_OFFSET = RING_HEADER_DTYPE.fields["creator_pid"][1]

UNCOMPRESSED_FORMATS = ("YUY2", "NV12", "RAW")
UNSELECTABLE_FORMATS = ("H264", "RAW")

# The next generation of each camera index in this process. It never resets, so a name is never
# used again while the app runs (A54).
_next_generation: dict[int, int] = {}


@dataclass(frozen=True)
class CameraMode:
    """One capture mode (section 9). In 2a, the mode list holds only the opened mode [A47]."""
    width: int
    height: int
    fps_num: int
    fps_den: int
    format: str
    uncompressed: bool
    selectable: bool


@dataclass(frozen=True)
class CameraRingInfo:
    """What a consumer needs to read the rings of one camera (sections 7.3 and 9) [A34, A46]."""
    camera_id: str
    camera_index: int
    mode: CameraMode
    jpeg_ring_name: str
    bgr_ring_name: str | None
    rotation_cw_deg: int


def camera_ring_info(config: CameraConfig, creator: "FrameRingCreator") -> CameraRingInfo:
    fps = _fps_fraction(config.framerate)
    fourcc = config.capture_fourcc
    mode = CameraMode(width=config.resolution.width, height=config.resolution.height,
                      fps_num=fps.numerator, fps_den=fps.denominator, format=fourcc,
                      uncompressed=fourcc in UNCOMPRESSED_FORMATS,
                      selectable=fourcc not in UNSELECTABLE_FORMATS)
    return CameraRingInfo(camera_id=config.camera_id, camera_index=config.camera_index, mode=mode,
                          jpeg_ring_name=creator.name, bgr_ring_name=None,
                          rotation_cw_deg=rotation_to_cw_deg(config.rotation))


def _fps_fraction(framerate: float) -> Fraction:
    """The frame rate as a fraction; 0 when capture reports none (fps_num = 0 means unknown, A52)."""
    return Fraction(framerate).limit_denominator(1001) if framerate > 0 else Fraction(0)


class FrameRingCreator:
    """Creates a ring, sets `closed` and unlinks it. Only the main skellycam process creates rings (A32)."""

    def __init__(self, shm: shared_memory.SharedMemory, total_size: int):
        self._shm = shm
        self.name = shm.name
        self.total_size = total_size

    @classmethod
    def create(cls, *, camera_id: str, camera_index: int, pixel_format: PixelFormat, width: int,
               height: int, fps_num: int, fps_den: int, history_s: float = 1.0,
               generation: int = 0) -> "FrameRingCreator":
        """Allocate the block and write its static header (7.1). The payload area stays untouched."""
        if fps_num <= 0 or fps_den <= 0:
            fps_num, fps_den = 0, 1  # "unknown" (A52)
        count = slot_count(history_s, fps_num / fps_den if fps_num else None)
        capacity = slot_capacity(pixel_format, width, height)
        total = ring_total_size(count, capacity)
        letter = "J" if pixel_format == PixelFormat.JPEG else "B"
        name = f"{NAME_PREFIX}{os.getpid():x}_{camera_index}_{letter}{generation}"
        shm = shared_memory.SharedMemory(name=name, create=True, size=total)
        utc_ns, perf_ns = time.time_ns(), time.perf_counter_ns()
        struct.pack_into(RING_HEADER_FORMAT, shm.buf, 0, MAGIC, LAYOUT_VERSION, RING_HEADER_SIZE,
                         pixel_format, count, capacity, TABLE_OFFSET, payload_offset(count), total,
                         width, height, fps_num, fps_den, camera_id.encode("ascii", "replace")[:16],
                         camera_index, os.getpid(), utc_ns, perf_ns, time.localtime().tm_gmtoff, 0,
                         round(history_s * 1000), -1, *[0] * 8)
        for slot in range(count):
            struct.pack_into("<q", shm.buf, TABLE_OFFSET + SLOT_HEADER_SIZE * slot, -1)
        return cls(shm, total)

    def set_closed(self) -> None:
        """The single `closed` store of the creator (7.4)."""
        struct.pack_into("<I", self._shm.buf, CLOSED_OFFSET, 1)

    def close_and_unlink(self) -> None:
        self.set_closed()
        self._shm.close()
        self._shm.unlink()


def create_session_rings(camera_configs: dict[str, CameraConfig],
                         history_s: float = 1.0) -> dict[str, FrameRingCreator]:
    """Create the JPEG ring of each camera (7.1, 7.8).

    Log the sizes, check the free space of /dev/shm on Linux, then allocate. On a failure, unlink
    the rings already made and raise `MemoryError` with the total size.
    """
    plans = {}
    for camera_id, config in camera_configs.items():
        fps = _fps_fraction(config.framerate)
        width, height = config.resolution.width, config.resolution.height
        size = ring_total_size(slot_count(history_s, float(fps) or None),
                               slot_capacity(PixelFormat.JPEG, width, height))
        plans[camera_id] = (config.camera_index, width, height, fps, size)
    total = sum(plan[-1] for plan in plans.values())
    logger.info(f"Frame rings: total shared memory {format_size(total)} for {len(plans)} cameras; "
                + "; ".join(f"camera {camera_id} JPEG ring {format_size(plan[-1])}"
                            for camera_id, plan in plans.items()))
    failure = f"Cannot allocate the frame rings: total {format_size(total)}"
    if sys.platform.startswith("linux"):
        stat = os.statvfs(LINUX_SHM_DIR)
        free = stat.f_bavail * stat.f_frsize
        if free < total:
            raise MemoryError(f"{failure}, but {LINUX_SHM_DIR} has {format_size(free)} free")
    creators = {}
    try:
        for camera_id, (camera_index, width, height, fps, _) in plans.items():
            generation = _next_generation.get(camera_index, 0)
            _next_generation[camera_index] = generation + 1
            creators[camera_id] = FrameRingCreator.create(
                camera_id=camera_id, camera_index=camera_index, pixel_format=PixelFormat.JPEG,
                width=width, height=height, fps_num=fps.numerator, fps_den=fps.denominator,
                history_s=history_s, generation=generation)
    except OSError as error:
        for creator in creators.values():
            creator.close_and_unlink()
        raise MemoryError(f"{failure}: {error}") from error
    return creators


def sweep_stale_rings() -> list[str]:
    """Linux: unlink each /dev/shm/skc* ring whose creator process is not alive (7.7, A37).

    Return the names that it unlinked. Other OSes have nothing to sweep.
    """
    if not sys.platform.startswith("linux"):
        return []
    removed = []
    for name in os.listdir(LINUX_SHM_DIR):
        if not name.startswith(NAME_PREFIX):
            continue
        try:
            shm = shared_memory.SharedMemory(name=name, create=False, track=False)
        except FileNotFoundError:
            continue
        try:
            is_ring = shm.size >= RING_HEADER_SIZE and struct.unpack_from("<4s", shm.buf)[0] == MAGIC
            creator_pid = struct.unpack_from("<I", shm.buf, CREATOR_PID_OFFSET)[0] if is_ring else 0
        finally:
            shm.close()
        if is_ring and not _pid_alive(creator_pid):
            shm.unlink()
            removed.append(name)
            logger.info(f"Unlinked the stale frame ring {name} of process {creator_pid}")
    return removed


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # alive, owned by another user
        pass
    return True
