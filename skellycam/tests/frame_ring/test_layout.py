"""Frame ring layout and sizes: T-RING-01 to T-RING-04 (specs/frame-ring.md, sections 3 and 12)."""

import logging
import os
import struct
import time
import zlib

import numpy as np
import pytest

from skellycam.tests.frame_ring.ring_spec import (
    CAPTURE_ERROR,
    DECODE_ERROR,
    DHT_INSERTED,
    DISCONTINUITY,
    ERROR_MASK,
    NO_SOI_EOI,
    OVERSIZE,
    RING_HEADER_FIELDS,
    RING_HEADER_RESERVED,
    SLOT_HEADER_FIELDS,
    SLOT_HEADER_RESERVED,
    STRUCT_TO_NUMPY,
    TABLE_OFFSET,
    new_ring,
    open_raw,
    parse_ring_header,
    parse_slot_header,
    ring,
    slot_header_bytes,
    slot_payload_offset,
    synthetic_payload,
)


def _check_dtype(dtype, fields, size):
    assert dtype.itemsize == size
    for offset, code, name in fields:
        assert name in dtype.fields, name
        field_dtype, field_offset = dtype.fields[name][:2]
        assert field_offset == offset, name
        assert field_dtype == np.dtype(STRUCT_TO_NUMPY[code]), name


def _packed_test_buffer(fields, size):
    """A buffer with a distinct value in each field, packed from the spec table."""
    buf = bytearray(size)
    values = []
    for i, (offset, code, name) in enumerate(fields):
        width = struct.calcsize(code)
        value = name.encode().ljust(width, b"\0")[:width] if code.endswith("s") else i + 1
        struct.pack_into("<" + code, buf, offset, value)
        values.append(value)
    return bytes(buf), values


def test_t_ring_01_layout_matches_tables_3_3_and_3_4():
    """T-RING-01, sections 3.2, 3.3, 3.4, 3.9 and 4: each offset, size and type of tables 3.3 and
    3.4 in the numpy dtypes and the struct formats; the slot header is 64 bytes; `head` is at 128."""
    fr = ring()
    _check_dtype(fr.RING_HEADER_DTYPE, RING_HEADER_FIELDS, 4096)
    _check_dtype(fr.SLOT_HEADER_DTYPE, SLOT_HEADER_FIELDS, 64)
    assert fr.RING_HEADER_DTYPE.fields["head"][1] == 128
    assert fr.RING_HEADER_SIZE == 4096
    assert fr.SLOT_HEADER_SIZE == 64
    assert struct.calcsize(fr.RING_HEADER_FORMAT) == 4096
    assert struct.calcsize(fr.SLOT_HEADER_FORMAT) == 64
    assert fr.RING_HEADER_FORMAT.startswith("<") and fr.SLOT_HEADER_FORMAT.startswith("<")
    for fmt, fields, size in ((fr.RING_HEADER_FORMAT, RING_HEADER_FIELDS, 4096),
                              (fr.SLOT_HEADER_FORMAT, SLOT_HEADER_FIELDS, 64)):
        buf, values = _packed_test_buffer(fields, size)
        # Reserved bytes are pad bytes in the format: unpack gives the named fields in table order.
        assert list(struct.unpack(fmt, buf)) == values
    assert fr.MAGIC == b"SKR2"
    assert fr.LAYOUT_VERSION == 1
    assert int(fr.PixelFormat.JPEG) == 1 and int(fr.PixelFormat.BGR24) == 2
    expected_flags = dict(OVERSIZE=OVERSIZE, CAPTURE_ERROR=CAPTURE_ERROR, NO_SOI_EOI=NO_SOI_EOI,
                          DECODE_ERROR=DECODE_ERROR, DISCONTINUITY=DISCONTINUITY,
                          DHT_INSERTED=DHT_INSERTED)
    assert {flag.name: int(flag) for flag in fr.FrameFlag} == expected_flags
    assert int(fr.ERROR_FLAGS) == ERROR_MASK


def test_t_ring_02_independent_parser_reads_what_the_writer_was_given(cleanup):
    """T-RING-02, sections 3.1 to 3.5, 5.4 and 7.1: a test-only struct parser (tables 3.3 and
    3.4) reads a block that the creator and the writer wrote. Each field equals the input."""
    camera_id = "camera-id-longer-than-16"
    utc_before, perf_before = time.time_ns(), time.perf_counter_ns()
    fr, creator, writer, _ = new_ring(cleanup, fps_num=30000, fps_den=1001, width=1280, height=720,
                                      camera_id=camera_id, camera_index=3, history_s=1.0)
    utc_after, perf_after = time.time_ns(), time.perf_counter_ns()
    payload = synthetic_payload(5, 54_321)
    t0 = time.perf_counter_ns()
    writer.write(payload, frame_number=0, arrival_ns=111, sample_ns=-(2 ** 63),
                 source_frame_number=-1, flags=0, rotation_cw_deg=90)
    writer.write(payload, frame_number=1, arrival_ns=222_000, sample_ns=221_000,
                 source_frame_number=77, flags=DHT_INSERTED, rotation_cw_deg=90)
    t1 = time.perf_counter_ns()
    shm = cleanup.handle(open_raw(creator.name))
    buf = shm.buf
    h = parse_ring_header(buf)
    slot_count = 30  # ceil(1.0 x 30000 / 1001) = 30
    capacity = 925_696  # table 3.6, 1280x720
    assert h["magic"] == b"SKR2"
    assert h["layout_version"] == 1
    assert h["header_size"] == 4096
    assert h["pixel_format"] == 1
    assert h["slot_count"] == slot_count
    assert h["slot_capacity"] == capacity
    assert h["table_offset"] == TABLE_OFFSET
    assert h["payload_offset"] == 8192
    assert h["total_size"] == 8192 + slot_count * capacity
    assert shm.size >= h["total_size"]  # sizes come from the header (3.1)
    assert (h["width"], h["height"], h["fps_num"], h["fps_den"]) == (1280, 720, 30000, 1001)
    assert h["camera_key"] == camera_id.encode()[:16]
    assert h["camera_index"] == 3
    assert h["creator_pid"] == os.getpid()
    assert utc_before <= h["utc_ns"] <= utc_after
    assert perf_before <= h["perf_ns"] <= perf_after
    assert h["utc_offset_s"] == time.localtime().tm_gmtoff
    assert h["closed"] == 0
    assert h["history_ms"] == 1000
    assert h["head"] == 1
    assert h["frames_committed"] == 2
    assert h["dht_inserted_count"] == 1
    assert h["largest_payload_len"] == len(payload)
    for name in ("oversize_count", "capture_error_count", "cut_off_count", "decode_error_count",
                 "skipped_count"):
        assert h[name] == 0, name
    for start, stop in RING_HEADER_RESERVED:
        assert bytes(buf[start:stop]) == bytes(stop - start), (start, stop)
    for k, (arrival, sample, source, flags) in enumerate(
            ((111, -(2 ** 63), -1, 0), (222_000, 221_000, 77, DHT_INSERTED))):
        s = parse_slot_header(buf, k)
        assert s["frame_number"] == k
        assert (s["arrival_ns"], s["sample_ns"], s["source_frame_number"]) == (arrival, sample, source)
        assert t0 <= s["published_ns"] <= t1
        assert s["payload_len"] == len(payload)
        assert s["flags"] == flags
        assert s["payload_crc32"] == zlib.crc32(payload)
        assert s["rotation_cw_deg"] == 90
        raw = slot_header_bytes(buf, k)
        for start, stop in SLOT_HEADER_RESERVED:
            assert raw[start:stop] == bytes(stop - start)
        assert s["header_crc32"] == zlib.crc32(raw[:60])
        start = slot_payload_offset(h, k)
        assert start % 4096 == 0  # 3.5: each JPEG slot starts on a 4 KiB boundary
        assert bytes(buf[start:start + len(payload)]) == payload
    for k in range(2, slot_count):
        assert parse_slot_header(buf, k)["frame_number"] == -1  # 7.1


@pytest.mark.parametrize(("width", "height", "jpeg", "bgr"), [
    (640, 480, 311_296, 921_600),
    (1280, 720, 925_696, 2_764_800),
    (1920, 1080, 2_080_768, 6_220_800),
    (3840, 2160, 8_298_496, 24_883_200),
])
def test_t_ring_03_slot_capacity(width, height, jpeg, bgr):
    """T-RING-03, section 3.6: the slot capacity formula gives the values of table 3.6."""
    fr = ring()
    assert fr.slot_capacity(fr.PixelFormat.JPEG, width, height) == jpeg
    assert fr.slot_capacity(fr.PixelFormat.BGR24, width, height) == bgr


@pytest.mark.parametrize(("width", "height", "fps", "n", "jpeg_total", "bgr_total"), [
    (1280, 720, 30, 30, 27_779_072, 82_952_192),
    (1280, 720, 60, 60, 55_549_952, 165_896_192),
    (1920, 1080, 30, 30, 62_431_232, 186_632_192),
    (1920, 1080, 60, 60, 124_854_272, 373_256_192),
])
def test_t_ring_04_slot_count_and_size_table_3_8(width, height, fps, n, jpeg_total, bgr_total):
    """T-RING-04, sections 3.7 and 3.8: history 1 s at 30 and 60 fps gives table 3.8."""
    fr = ring()
    assert fr.slot_count(1.0, fps) == n
    jpeg = fr.slot_capacity(fr.PixelFormat.JPEG, width, height)
    bgr = fr.slot_capacity(fr.PixelFormat.BGR24, width, height)
    assert fr.ring_total_size(n, jpeg) == jpeg_total
    assert fr.ring_total_size(n, bgr) == bgr_total


def test_t_ring_04_minimum_two_slots_and_payload_offset():
    """T-RING-04, sections 3.1, 3.7 and 3.8: history 0.01 s gives the minimum of 2 slots;
    `payload_offset` is 8,192 for N up to 64."""
    fr = ring()
    assert fr.slot_count(0.01, 30) == 2
    assert fr.slot_count(0.01, 60) == 2
    assert fr.ring_total_size(64, 4096) == 8192 + 64 * 4096
    assert fr.ring_total_size(65, 4096) == 12288 + 65 * 4096


@pytest.mark.parametrize("fps", [None, -1, 0])
def test_t_ring_04_unknown_fps_uses_60_and_logs(fps, caplog):
    """T-RING-04, section 3.7 [A11]: when capture reports no frame rate, skellycam uses 60 and
    logs it."""
    fr = ring()
    with caplog.at_level(logging.DEBUG):
        assert fr.slot_count(1.0, fps) == 60
    assert any("60" in record.getMessage() for record in caplog.records)


def test_t_ring_04_creator_header_matches_table_3_8(cleanup):
    """T-RING-04, sections 3.3 and 3.8: the creator writes the size of table 3.8 (720p30)."""
    _, creator, _, _ = new_ring(cleanup, fps_num=30, width=1280, height=720)
    shm = cleanup.handle(open_raw(creator.name))
    header = parse_ring_header(shm.buf)
    assert header["slot_count"] == 30
    assert header["total_size"] == 27_779_072
    assert creator.total_size == 27_779_072
