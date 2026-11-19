"""Test-only helpers for the frame ring tests (specs/frame-ring.md).

The layout tables in this file come from sections 3.3 and 3.4 of the spec, not from the
implementation. Thus the parser and the raw writer here are an independent check of the
implementation. Do not import the layout of `skellycam.core.ipc.frame_ring` into this file.
"""

import importlib
import os
import struct
import time
import zlib
from multiprocessing import shared_memory

import cv2
import numpy as np

RING_MODULE = "skellycam.core.ipc.frame_ring"

# SKELLYCAM_RING_FULL=1 gives the durations of the spec. The default is a short run.
FULL = os.environ.get("SKELLYCAM_RING_FULL", "") == "1"
LAP_SECONDS = 60.0 if FULL else 2.0  # T-RING-08, per slot count
KILL_TRIALS = 100  # T-RING-11, maximum trials; the test stops at the first hit after trial 3
TIMING_SECONDS = 10.0 if FULL else 2.0  # T-RING-12 and T-RING-23, per phase
IDLE_SECONDS = 5.0 if FULL else 2.0  # T-RING-31

WAIT_TIMEOUT_S = 30.0


def ring():
    """Import the ring package inside a test, so that a missing package fails the test."""
    return importlib.import_module(RING_MODULE)


# ---------------------------------------------------------------------------
# Tables 3.3 and 3.4: (offset, struct code, name). Little-endian (3.2).
# ---------------------------------------------------------------------------

RING_HEADER_SIZE = 4096
SLOT_HEADER_SIZE = 64
TABLE_OFFSET = 4096
MAGIC = b"SKR2"
LAYOUT_VERSION = 1

RING_HEADER_FIELDS = (
    (0, "4s", "magic"),
    (4, "I", "layout_version"),
    (8, "I", "header_size"),
    (12, "I", "pixel_format"),
    (16, "I", "slot_count"),
    (20, "I", "slot_capacity"),
    (24, "Q", "table_offset"),
    (32, "Q", "payload_offset"),
    (40, "Q", "total_size"),
    (48, "I", "width"),
    (52, "I", "height"),
    (56, "I", "fps_num"),
    (60, "I", "fps_den"),
    (64, "16s", "camera_key"),
    (80, "I", "camera_index"),
    (84, "I", "creator_pid"),
    (88, "q", "utc_ns"),
    (96, "q", "perf_ns"),
    (104, "i", "utc_offset_s"),
    (108, "I", "closed"),
    (112, "I", "history_ms"),
    (128, "q", "head"),
    (192, "Q", "frames_committed"),
    (200, "Q", "oversize_count"),
    (208, "Q", "capture_error_count"),
    (216, "Q", "cut_off_count"),
    (224, "Q", "decode_error_count"),
    (232, "Q", "skipped_count"),
    (240, "Q", "dht_inserted_count"),
    (248, "Q", "largest_payload_len"),
)
RING_HEADER_RESERVED = ((116, 128), (136, 192), (256, 4096))

SLOT_HEADER_FIELDS = (
    (0, "q", "frame_number"),
    (8, "q", "arrival_ns"),
    (16, "q", "sample_ns"),
    (24, "q", "published_ns"),
    (32, "q", "source_frame_number"),
    (40, "I", "payload_len"),
    (44, "I", "flags"),
    (48, "I", "payload_crc32"),
    (52, "I", "rotation_cw_deg"),
    (60, "I", "header_crc32"),
)
SLOT_HEADER_RESERVED = ((56, 60),)

# Section 4.
OVERSIZE = 0x01
CAPTURE_ERROR = 0x02
NO_SOI_EOI = 0x04
DECODE_ERROR = 0x08
DISCONTINUITY = 0x10
DHT_INSERTED = 0x20
ERROR_MASK = 0x0F

PIXEL_FORMAT_JPEG = 1
PIXEL_FORMAT_BGR24 = 2

STRUCT_TO_NUMPY = {"4s": "S4", "16s": "S16", "I": "<u4", "Q": "<u8", "q": "<i8", "i": "<i4"}


def roundup(value, multiple):
    return -(-value // multiple) * multiple


def expected_jpeg_slot_capacity(width, height):
    """Table 3.6, JPEG row."""
    return roundup(int(2 * (2048 + 0.5 * width * height)), 4096)


def expected_payload_offset(slot_count):
    """Section 3.1."""
    return roundup(RING_HEADER_SIZE + SLOT_HEADER_SIZE * slot_count, 4096)


def unpack_fields(fields, buf, base=0):
    return {name: struct.unpack_from("<" + code, buf, base + offset)[0] for offset, code, name in fields}


def parse_ring_header(buf):
    return unpack_fields(RING_HEADER_FIELDS, buf)


def parse_slot_header(buf, slot):
    return unpack_fields(SLOT_HEADER_FIELDS, buf, TABLE_OFFSET + SLOT_HEADER_SIZE * slot)


def slot_header_bytes(buf, slot):
    start = TABLE_OFFSET + SLOT_HEADER_SIZE * slot
    return bytes(buf[start:start + SLOT_HEADER_SIZE])


def slot_payload_offset(header, slot):
    return header["payload_offset"] + slot * header["slot_capacity"]


def pack_slot_header(*, frame_number, arrival_ns, sample_ns, published_ns, source_frame_number,
                     payload_len, flags, payload_crc32, rotation_cw_deg):
    """Pack 64 bytes per table 3.4, with `header_crc32` over bytes 0 to 59."""
    out = bytearray(SLOT_HEADER_SIZE)
    values = dict(frame_number=frame_number, arrival_ns=arrival_ns, sample_ns=sample_ns,
                  published_ns=published_ns, source_frame_number=source_frame_number,
                  payload_len=payload_len, flags=flags, payload_crc32=payload_crc32,
                  rotation_cw_deg=rotation_cw_deg)
    for offset, code, name in SLOT_HEADER_FIELDS[:-1]:
        struct.pack_into("<" + code, out, offset, values[name])
    struct.pack_into("<I", out, 60, zlib.crc32(bytes(out[:60])))
    return bytes(out)


def open_raw(name):
    """Attach to a ring by name with the standard library only. The caller closes it."""
    return shared_memory.SharedMemory(name=name, create=False, track=False)


def raw_header(name):
    shm = open_raw(name)
    try:
        return parse_ring_header(shm.buf)
    finally:
        shm.close()


def raw_head(shm):
    return struct.unpack_from("<q", shm.buf, 128)[0]


def ring_exists(name):
    try:
        shm = open_raw(name)
    except FileNotFoundError:
        return False
    shm.close()
    return True


class RawRing:
    """A test-only ring block, written from the spec tables (T-RING-09, T-RING-10).

    It can break the writer rules of section 5.4 on purpose.
    """

    def __init__(self, slot_count, slot_capacity, width=640, height=480, pixel_format=PIXEL_FORMAT_JPEG):
        self.slot_count = slot_count
        self.slot_capacity = slot_capacity
        self.payload_offset = expected_payload_offset(slot_count)
        self.total_size = self.payload_offset + slot_count * slot_capacity
        self.shm = shared_memory.SharedMemory(create=True, size=self.total_size)
        self.name = self.shm.name
        buf = self.shm.buf
        values = dict(magic=MAGIC, layout_version=LAYOUT_VERSION, header_size=RING_HEADER_SIZE,
                      pixel_format=pixel_format, slot_count=slot_count, slot_capacity=slot_capacity,
                      table_offset=TABLE_OFFSET, payload_offset=self.payload_offset,
                      total_size=self.total_size, width=width, height=height, fps_num=30, fps_den=1,
                      camera_key=b"raw-test", camera_index=0, creator_pid=os.getpid(), utc_ns=0,
                      perf_ns=0, utc_offset_s=0, closed=0, history_ms=1000, head=-1)
        for offset, code, name in RING_HEADER_FIELDS:
            struct.pack_into("<" + code, buf, offset, values.get(name, 0))
        for slot in range(slot_count):
            struct.pack_into("<q", buf, TABLE_OFFSET + SLOT_HEADER_SIZE * slot, -1)

    def header_for(self, k, payload, flags=0):
        return pack_slot_header(frame_number=k, arrival_ns=arrival_for(k), sample_ns=-(2 ** 63),
                                published_ns=arrival_for(k) + 1, source_frame_number=k,
                                payload_len=len(payload), flags=flags,
                                payload_crc32=0 if flags & ERROR_MASK else zlib.crc32(payload),
                                rotation_cw_deg=0)

    def write_header(self, k, header):
        start = TABLE_OFFSET + SLOT_HEADER_SIZE * (k % self.slot_count)
        self.shm.buf[start:start + SLOT_HEADER_SIZE] = header

    def mark_writing(self, k):
        struct.pack_into("<q", self.shm.buf, TABLE_OFFSET + SLOT_HEADER_SIZE * (k % self.slot_count), -1)

    def write_payload(self, k, payload, start=0, stop=None):
        stop = len(payload) if stop is None else stop
        base = self.payload_offset + (k % self.slot_count) * self.slot_capacity
        self.shm.buf[base + start:base + stop] = payload[start:stop]

    def set_head(self, k):
        struct.pack_into("<q", self.shm.buf, 128, k)

    def commit(self, k, payload):
        """A correct commit, in the order W2 to W6 of section 5.4."""
        self.mark_writing(k)
        self.write_payload(k, payload)
        self.write_header(k, self.header_for(k, payload))
        self.set_head(k)

    def flip_bit(self, offset, bit=0):
        self.shm.buf[offset] ^= 1 << bit

    def close_and_unlink(self):
        self.shm.close()
        try:
            self.shm.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Synthetic payloads: bytes that are a function of the frame number (section 12).
# ---------------------------------------------------------------------------

def arrival_for(k):
    return 1_000_000_000 + k * 16_666_666


def write_kwargs(k, flags=0, rotation=0):
    """The per-frame items of table 5.1 that the writer takes, after the capture check."""
    return dict(frame_number=k, arrival_ns=arrival_for(k), sample_ns=arrival_for(k) - 1000,
                source_frame_number=k, flags=flags, rotation_cw_deg=rotation)


def new_ring(cleanup, *, fps_num=30, fps_den=1, width=640, height=480, history_s=1.0,
             camera_id="cam0", camera_index=0, generation=0, bgr=False):
    """Create a JPEG ring (a BGR ring if `bgr`), attach a writer and a reader. This uses the API of
    the proposed entry (the 2a tests' API), never the layout of the implementation."""
    fr = ring()
    creator = cleanup.own(fr.FrameRingCreator.create(
        camera_id=camera_id, camera_index=camera_index,
        pixel_format=fr.PixelFormat.BGR24 if bgr else fr.PixelFormat.JPEG,
        width=width, height=height, fps_num=fps_num, fps_den=fps_den, history_s=history_s,
        generation=generation))
    writer = cleanup.handle(fr.FrameRingWriter.attach(creator.name))
    reader = cleanup.handle(fr.FrameRingReader.attach(creator.name))
    return fr, creator, writer, reader


def synthetic_payload(k, size):
    if size == 0:
        return b""
    return np.random.default_rng(k).integers(0, 256, size, dtype=np.uint8).tobytes()


def paced_payload(k, size):
    """Synthetic payload for paced writers: 16 bodies, the last 8 bytes are k."""
    return synthetic_payload(k % 16, size)[:-8] + k.to_bytes(8, "little")


_BODIES = {}


def lap_payload(k, base_size):
    """Fast synthetic payload for unthrottled writers: 8 bytes of k, then one of 7 bodies.

    7 is coprime to the slot counts 2, 8 and 60. Thus frames k and k + N never share a body, and
    a torn copy of two frames is never equal to a correct payload.
    """
    key = (k % 7, base_size)
    if key not in _BODIES:
        _BODIES[key] = synthetic_payload(10_000 + k % 7, base_size + (k % 7) * 4099)
    return k.to_bytes(8, "little") + _BODIES[key]


# ---------------------------------------------------------------------------
# Synthetic JPEGs (section 12): made here with cv2.imencode from a generated image.
# ---------------------------------------------------------------------------

def synthetic_image(width=640, height=480, seed=1):
    rng = np.random.default_rng(seed)
    ramp = (np.add.outer(np.arange(height), np.arange(width)) % 256).astype(np.uint8)
    image = np.dstack([ramp, ramp[::-1], np.full_like(ramp, 90)])
    return image ^ rng.integers(0, 32, image.shape, dtype=np.uint8)


def synthetic_jpeg(sampling="420", restart_interval=0, width=640, height=480, seed=1):
    """`cv2.IMWRITE_JPEG_RST_INTERVAL` is the documented OpenCV flag for restart markers."""
    factor = {"420": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_420, "422": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_422}[sampling]
    ok, encoded = cv2.imencode(".jpg", synthetic_image(width, height, seed), [
        cv2.IMWRITE_JPEG_QUALITY, 90,
        cv2.IMWRITE_JPEG_SAMPLING_FACTOR, factor,
        cv2.IMWRITE_JPEG_RST_INTERVAL, restart_interval,
    ])
    assert ok
    return encoded.tobytes()


def jpeg_segments(data):
    """Walk the marker segments from SOI to the first SOS. Return (marker, start, end) tuples."""
    assert data[:2] == b"\xff\xd8"
    segments = []
    i = 2
    while True:
        assert data[i] == 0xFF, f"no marker at {i}"
        marker = data[i + 1]
        length = int.from_bytes(data[i + 2:i + 4], "big")
        segments.append((marker, i, i + 2 + length))
        if marker == 0xDA:
            return segments
        i += 2 + length


def strip_dht(data):
    """Remove each DHT segment (FF C4) before the first SOS."""
    out = bytearray(data[:2])
    last = 2
    for marker, start, end in jpeg_segments(data):
        if marker == 0xC4:
            out += data[last:start]
            last = end
    out += data[last:]
    return bytes(out)


def dht_tables(data, start, end):
    """Return the set of (class/id byte, counts, values) of one DHT segment."""
    tables = set()
    i = start + 4
    while i < end:
        tc_th = data[i]
        counts = data[i + 1:i + 17]
        n = sum(counts)
        tables.add((tc_th, bytes(counts), bytes(data[i + 17:i + 17 + n])))
        i += 17 + n
    assert i == end
    return tables


def sampling_of(data):
    """Return the sampling byte of the first component in SOF0, for example 0x22 for 4:2:0."""
    for marker, start, _ in jpeg_segments(data):
        if marker == 0xC0:
            return data[start + 11]
    raise AssertionError("no SOF0")


# ---------------------------------------------------------------------------
# Step 2b: the BGR ring and the decode stage (section 8). The names of the decode stage are those
# of the proposed entry ADR-5MYA.
# ---------------------------------------------------------------------------

def bgr_size(width=640, height=480):
    """Table 3.6, BGR24 row: exactly width x height x 3."""
    return width * height * 3


def as_bgr(payload, shape):
    """The first `h x w x 3` bytes of a synthetic payload as the array that a BGR writer takes
    (5.1): shape `(h, w, 3)`, uint8, C-contiguous. No copy."""
    return np.frombuffer(payload, np.uint8, count=shape[0] * shape[1] * shape[2]).reshape(shape)


def ring_payload(maker, k, size, shape=None):
    """`maker(k, size)` for a JPEG ring; for a BGR ring (`shape` given), that payload as an array."""
    payload = maker(k, size)
    return payload if shape is None else as_bgr(payload, shape)


def as_bytes(payload):
    """The bytes of a JPEG payload (`bytes`) or of a BGR payload (`ndarray`), for a comparison."""
    return payload.tobytes() if isinstance(payload, np.ndarray) else payload


def bgr_payload(k, width=640, height=480):
    """Synthetic BGR frame k (a function of k), as the array that a BGR writer takes."""
    return as_bgr(synthetic_payload(k, bgr_size(width, height)), (height, width, 3))


def junk_before_eoi(jpeg, count):
    """A synthetic JPEG with `count` junk bytes inserted before its EOI marker (the bytes of the
    generic camera at 1920x1080, N:299-300). The bytes are 01 to FE, so no marker is made."""
    eoi = len(jpeg) - 2
    assert jpeg[eoi:] == b"\xff\xd9"
    junk = (bytes(range(1, 255)) * (count // 254 + 1))[:count]
    return jpeg[:eoi] + junk + jpeg[eoi:]


def wait_committed(shm, count, timeout=WAIT_TIMEOUT_S):
    """Wait until `frames_committed` of a ring is at least `count`. Return the ring header."""
    deadline = time.monotonic() + timeout
    while True:
        header = parse_ring_header(shm.buf)
        if header["frames_committed"] >= count:
            return header
        assert time.monotonic() < deadline, f"frames_committed {header['frames_committed']} < {count}"
        time.sleep(0.001)


def committed_frame_numbers(shm):
    """The frame numbers in the slot headers of a ring whose header CRC passes (-1 left out)."""
    header = parse_ring_header(shm.buf)
    numbers = []
    for slot in range(header["slot_count"]):
        raw = slot_header_bytes(shm.buf, slot)
        fields = parse_slot_header(shm.buf, slot)
        if fields["frame_number"] >= 0 and zlib.crc32(raw[:60]) == fields["header_crc32"]:
            numbers.append(fields["frame_number"])
    return sorted(numbers)


def decode_input(payload, source, k, flags=0, rotation=0):
    """A frame for the waiting place (ADR-5MYA): the payload, its source and the numbers and times
    of the JPEG frame k (table 5.1)."""
    return ring().DecodeInput(payload=payload, source=source, **write_kwargs(k, flags, rotation))


def start_stage(stages, writer, decode=None):
    """Make and start a decode stage on a BGR ring writer (ADR-5MYA). The `stages` fixture stops
    it, also when the test fails."""
    fr = ring()
    stage = fr.DecodeStage(writer) if decode is None else fr.DecodeStage(writer, decode=decode)
    stages.append(stage)
    stage.start()
    return stage


def attach_slow_writer(name, sleep_s=0.1):
    """A writer of ring `name` whose each write sleeps `sleep_s` first: a slow BGR stage
    (T-RING-38, T-RING-47). It is a subclass of `FrameRingWriter`, so that a type check of the
    product code accepts it."""
    base = ring().FrameRingWriter

    class SlowWriter(base):
        def write(self, payload, **kwargs):
            time.sleep(sleep_s)
            return super().write(payload, **kwargs)

    return SlowWriter.attach(name)
