"""Frame ring writer and reader in one process: T-RING-05, 06, 07, 10, 15, 16, 20, 21, 22, 24
(specs/frame-ring.md, sections 4 to 6 and 12)."""

import logging
import re
import tracemalloc

import pytest

from skellycam.tests.frame_ring.ring_spec import (
    CAPTURE_ERROR,
    DECODE_ERROR,
    DISCONTINUITY,
    NO_SOI_EOI,
    OVERSIZE,
    arrival_for,
    new_ring,
    open_raw,
    parse_ring_header,
    parse_slot_header,
    ring,
    slot_payload_offset,
    synthetic_payload,
    write_kwargs,
)

JPEG_640_SLOT = 311_296  # table 3.6


@pytest.mark.ring_portable
def test_t_ring_05_round_trip(cleanup):
    """T-RING-05, sections 5.4, 6.2 and 6.6: synthetic payloads of 0, 1, random and
    `slot_capacity` bytes. Each read is `OK` with identical bytes."""
    fr, _, writer, reader = new_ring(cleanup, fps_num=8)
    sizes = [0, 1, 12_345, 200_003, JPEG_640_SLOT]
    for k, size in enumerate(sizes):
        payload = synthetic_payload(k, size)
        writer.write(payload, **write_kwargs(k, rotation=180))
        read = reader.read(k)
        assert read.result == fr.ReadResult.OK, (k, size)
        assert type(read.payload) is bytes
        assert read.payload == payload
        assert read.payload_len == size
        assert read.frame_number == k
        assert read.arrival_ns == arrival_for(k)
        assert read.sample_ns == arrival_for(k) - 1000
        assert read.source_frame_number == k
        assert read.flags == 0
        assert read.rotation_cw_deg == 180


@pytest.mark.ring_portable
def test_t_ring_06_oversize(cleanup):
    """T-RING-06, sections 5.6 and 6.2 (R8): a payload of `slot_capacity + 1` bytes. The slot
    bytes stay unchanged, `OVERSIZE` is set, the counter is 1, and the reader gets `OVERSIZE`
    with no payload."""
    fr, creator, writer, reader = new_ring(cleanup, fps_num=8)
    shm = cleanup.handle(open_raw(creator.name))
    header = parse_ring_header(shm.buf)
    start = slot_payload_offset(header, 0)
    before = bytes(shm.buf[start:start + JPEG_640_SLOT])
    payload = synthetic_payload(0, JPEG_640_SLOT + 1)
    writer.write(payload, **write_kwargs(0))
    assert bytes(shm.buf[start:start + JPEG_640_SLOT]) == before
    slot = parse_slot_header(shm.buf, 0)
    assert slot["flags"] & OVERSIZE
    assert slot["payload_len"] == JPEG_640_SLOT + 1
    assert slot["payload_crc32"] == 0
    header = parse_ring_header(shm.buf)
    assert header["oversize_count"] == 1
    assert header["frames_committed"] == 1
    assert header["head"] == 0
    assert header["largest_payload_len"] == JPEG_640_SLOT + 1
    read = reader.read(0)
    assert read.result == fr.ReadResult.OVERSIZE
    assert read.payload is None


@pytest.mark.ring_portable
def test_t_ring_07_read_results(cleanup):
    """T-RING-07, sections 6.2 and 6.3: empty ring, `k > head`, `head - k >= N`, a skipped
    number and a closed ring give `NOT_YET_WRITTEN`, `NOT_YET_WRITTEN`, `LAPPED`, `MISSING` and
    `CLOSED`."""
    fr, creator, writer, reader = new_ring(cleanup, fps_num=4)  # N = 4
    assert reader.read(0).result == fr.ReadResult.NOT_YET_WRITTEN
    for k in range(6):
        writer.write(synthetic_payload(k, 1000), **write_kwargs(k))
    assert reader.read(6).result == fr.ReadResult.NOT_YET_WRITTEN
    assert reader.read(1).result == fr.ReadResult.LAPPED  # head 5 - 1 >= 4
    writer.write(synthetic_payload(6, 1000), newer_frame_waiting=True, **write_kwargs(6))
    writer.write(synthetic_payload(7, 1000), **write_kwargs(7))
    read = reader.read(6)  # slot 2 still holds frame 2
    assert read.result == fr.ReadResult.MISSING
    assert read.payload is None
    creator.set_closed()
    read = reader.read(7)
    assert read.result == fr.ReadResult.CLOSED
    assert read.payload is None


@pytest.mark.ring_portable
def test_t_ring_07_slot_being_written_is_lapped(cleanup):
    """T-RING-07, sections 6.2 and 6.4 [A58]: a committed frame whose slot header then holds
    `frame_number = -1` (writer step W2, or a writer killed in mid-write) reads as `LAPPED`, not
    `CORRUPT`, although the header CRC fails on both copies."""
    fr, creator, writer, reader = new_ring(cleanup, fps_num=8)
    writer.write(synthetic_payload(0, 50_000), **write_kwargs(0))
    shm = cleanup.handle(open_raw(creator.name))
    shm.buf[4096:4104] = (-1).to_bytes(8, "little", signed=True)  # slot 0, frame_number
    read = reader.read(0)
    assert read.result == fr.ReadResult.LAPPED
    assert read.payload is None


@pytest.mark.ring_portable
@pytest.mark.parametrize("where", ["payload", "header"])
def test_t_ring_10_bit_flip_after_commit_is_corrupt(cleanup, where):
    """T-RING-10, sections 6.2 and 6.4: one payload bit flipped after the commit, and separately
    one header bit. Both give `CORRUPT` (two identical bad copies)."""
    fr, creator, writer, reader = new_ring(cleanup, fps_num=8)
    writer.write(synthetic_payload(0, 50_000), **write_kwargs(0))
    assert reader.read(0).result == fr.ReadResult.OK
    shm = cleanup.handle(open_raw(creator.name))
    header = parse_ring_header(shm.buf)
    offset = slot_payload_offset(header, 0) + 12_345 if where == "payload" else 4096 + 9  # arrival_ns
    shm.buf[offset] ^= 0x10
    read = reader.read(0)
    assert read.result == fr.ReadResult.CORRUPT
    assert read.payload is None


def test_t_ring_15_writer_one_copy(cleanup):
    """T-RING-15, section 5.7 [A25]: `tracemalloc` over 1,000 synthetic writes with preallocated
    payloads. No allocation of 1 KiB or more in the write path; under 1 KiB in total per frame.

    tracemalloc cannot sum short-lived blocks. The test checks the peak above the start of each
    write (this catches each block of 1 KiB or more) and the memory that stays after 1,000 writes.
    """
    _, _, writer, _ = new_ring(cleanup, fps_num=60)
    payloads = [synthetic_payload(k, 200_000 + k) for k in range(8)]
    arguments = [write_kwargs(k) for k in range(1010)]
    for k in range(10):  # warm-up: first-touch pages, caches
        writer.write(payloads[k % 8], **arguments[k])
    worst = 0
    tracemalloc.start()
    try:
        start = tracemalloc.get_traced_memory()[0]
        for k in range(10, 1010):
            payload = payloads[k % 8]
            kwargs = arguments[k]
            tracemalloc.reset_peak()
            before = tracemalloc.get_traced_memory()[0]
            writer.write(payload, **kwargs)
            worst = max(worst, tracemalloc.get_traced_memory()[1] - before)
        kept = tracemalloc.get_traced_memory()[0] - start
    finally:
        tracemalloc.stop()
    assert worst < 1024, f"one write allocated {worst} bytes at its peak"
    assert kept < 1000 * 1024, f"{kept} bytes stay after 1,000 writes"


def test_t_ring_16_reader_one_copy(cleanup):
    """T-RING-16, sections 6.2 (R11) and 6.6: `tracemalloc` over 1,000 reads. One allocation of
    about `payload_len` per read; the returned object is that allocation."""
    fr, _, writer, reader = new_ring(cleanup, fps_num=60)
    size = 200_000
    for k in range(60):
        writer.write(synthetic_payload(k, size), **write_kwargs(k))
    for k in range(10):
        reader.read(k)  # warm-up
    tracemalloc.start()
    try:
        for i in range(1000):
            k = i % 60
            tracemalloc.reset_peak()
            before = tracemalloc.get_traced_memory()[0]
            read = reader.read(k)
            current, peak = tracemalloc.get_traced_memory()
            assert read.result == fr.ReadResult.OK
            assert type(read.payload) is bytes and len(read.payload) == size
            assert tracemalloc.get_object_traceback(read.payload) is not None
            assert current - before >= size  # the returned object is the allocation that stays
            assert peak - before <= size + 4096, f"read {i} peaked at {peak - before} bytes"
            del read
    finally:
        tracemalloc.stop()


@pytest.mark.parametrize("flag", [CAPTURE_ERROR, NO_SOI_EOI, DECODE_ERROR, OVERSIZE],
                         ids=["CAPTURE_ERROR", "NO_SOI_EOI", "DECODE_ERROR", "OVERSIZE"])
def test_t_ring_20_error_flag_rule_for_each_lookup(cleanup, flag):
    """T-RING-20, sections 4, 5.6, 6.2 (R8, R9) and 6.5: frames with each error flag, read by
    number, newest and nearest. No lookup returns a payload for them."""
    fr, creator, writer, reader = new_ring(cleanup, fps_num=8)
    writer.write(synthetic_payload(0, 1000), **write_kwargs(0))
    if flag == OVERSIZE:
        writer.write(synthetic_payload(1, JPEG_640_SLOT + 1), **write_kwargs(1))
        expected = fr.ReadResult.OVERSIZE
    else:
        writer.write(synthetic_payload(1, 1000), **write_kwargs(1, flags=flag))
        expected = fr.ReadResult.FLAGGED
    for read in (reader.read(1), reader.read_newest(), reader.read_nearest(arrival_for(1))):
        assert read.result == expected
        assert read.payload is None
        assert read.frame_number == 1
        assert read.flags & flag
    shm = cleanup.handle(open_raw(creator.name))
    header = parse_ring_header(shm.buf)
    start = slot_payload_offset(header, 1)
    assert bytes(shm.buf[start:start + 1000]) == bytes(1000)  # the writer did not copy it (5.6)
    assert parse_slot_header(shm.buf, 1)["payload_crc32"] == 0
    counter = {CAPTURE_ERROR: "capture_error_count", NO_SOI_EOI: "cut_off_count",
               DECODE_ERROR: "decode_error_count", OVERSIZE: "oversize_count"}[flag]
    assert header[counter] == 1


def test_t_ring_21_rotation_mapping():
    """T-RING-21, section 3.4 [A9]: the config enum maps to `rotation_cw_deg` as a Python int."""
    from skellycam.core.camera.config.image_rotation_types import RotationTypes

    fr = ring()
    expected = {RotationTypes.NO_ROTATION: 0, RotationTypes.CLOCKWISE_90: 90,
                RotationTypes.ROTATE_180: 180, RotationTypes.COUNTERCLOCKWISE_90: 270}
    for rotation, degrees in expected.items():
        value = fr.rotation_to_cw_deg(rotation)
        assert type(value) is int and value == degrees


def test_t_ring_21_rotation_changes_and_discontinuity(cleanup):
    """T-RING-21, sections 4 and 7.5: rotation changes 0 to 180, 0 to 90 and 90 to 270.
    The values are 0/90/180/270 as Python int; `DISCONTINUITY` is only on the 0 to 90 change."""
    fr, _, writer, reader = new_ring(cleanup, fps_num=8)
    rotations = [0, 180, 0, 90, 270, 270]
    for k, rotation in enumerate(rotations):
        writer.write(synthetic_payload(k, 1000), **write_kwargs(k, rotation=rotation))
    for k, rotation in enumerate(rotations):
        read = reader.read(k)
        assert read.result == fr.ReadResult.OK
        assert type(read.rotation_cw_deg) is int and read.rotation_cw_deg == rotation
        assert bool(read.flags & DISCONTINUITY) == (k == 3), k


def test_t_ring_22_self_check(cleanup, caplog):
    """T-RING-22, section 5.8 [A24]: frames at 20 %, 51 % and 60 % of the slot. One warning at
    the 51 % frame; a periodic log line with the fraction; the counters match."""
    _, creator, writer, _ = new_ring(cleanup, fps_num=8)
    sizes = [int(JPEG_640_SLOT * f) for f in (0.20, 0.51, 0.60)]
    warnings_after = []
    with caplog.at_level(logging.DEBUG):
        for k, size in enumerate(sizes):
            writer.write(synthetic_payload(k, size), **write_kwargs(k))
            warnings_after.append(sum(r.levelno == logging.WARNING for r in caplog.records))
        caplog.clear()
        writer.log_largest_payload()
    assert warnings_after == [0, 1, 1]
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert re.search(r"0\.60\b|60(\.0)? ?%", messages), messages
    header = parse_ring_header(cleanup.handle(open_raw(creator.name)).buf)
    assert header["largest_payload_len"] == sizes[2]
    assert header["frames_committed"] == 3
    assert header["oversize_count"] == 0


def test_t_ring_24_skipped_write(cleanup):
    """T-RING-24, sections 5.3 [A23] and 6.2 (R6): the capture layer reports a newer frame
    waiting. `skipped_count` goes up, and a reader gets `MISSING` for that number."""
    fr, creator, writer, reader = new_ring(cleanup, fps_num=4)
    for k in range(6):
        writer.write(synthetic_payload(k, 1000), **write_kwargs(k))
    writer.write(synthetic_payload(6, 1000), newer_frame_waiting=True, **write_kwargs(6))
    writer.write(synthetic_payload(7, 1000), **write_kwargs(7))
    header = parse_ring_header(cleanup.handle(open_raw(creator.name)).buf)
    assert header["skipped_count"] == 1
    assert header["frames_committed"] == 7
    assert header["head"] == 7
    assert reader.read(6).result == fr.ReadResult.MISSING
    assert reader.read(7).result == fr.ReadResult.OK


@pytest.mark.ring_portable
def test_t_ring_07_closed_ring_stops_the_writer(cleanup):
    """T-RING-07 group, section 7.4 [A35]: after `closed = 1`, the writer stops writing."""
    _, creator, writer, _ = new_ring(cleanup, fps_num=4)
    writer.write(synthetic_payload(0, 1000), **write_kwargs(0))
    creator.set_closed()
    writer.write(synthetic_payload(1, 1000), **write_kwargs(1))
    header = parse_ring_header(cleanup.handle(open_raw(creator.name)).buf)
    assert header["closed"] == 1
    assert header["head"] == 0
    assert header["frames_committed"] == 1
