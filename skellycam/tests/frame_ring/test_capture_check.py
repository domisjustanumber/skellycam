"""Capture check and cut-off frames: T-RING-17, 18, 19 (specs/frame-ring.md, sections 4, 5.2,
6.3, 6.6 and 12).

The synthetic JPEGs come from `cv2.imencode` on a generated image (ring_spec.synthetic_jpeg).
Restart markers come from the documented flag `cv2.IMWRITE_JPEG_RST_INTERVAL`.
"""

import dataclasses
import inspect
from multiprocessing import shared_memory

import cv2
import numpy as np
import pytest

from skellycam.tests.frame_ring.ring_spec import (
    CAPTURE_ERROR,
    DHT_INSERTED,
    ERROR_MASK,
    NO_SOI_EOI,
    jpeg_segments,
    dht_tables,
    new_ring,
    open_raw,
    parse_ring_header,
    ring,
    sampling_of,
    strip_dht,
    synthetic_jpeg,
    write_kwargs,
)

VARIANTS = [("420", 0), ("420", 8), ("422", 0), ("422", 8)]
VARIANT_IDS = ["420", "420-restart", "422", "422-restart"]


def _check(payload, delivered_len=None, driver_error=False):
    fr = ring()
    return fr.check_jpeg(payload, delivered_len=len(payload) if delivered_len is None else delivered_len,
                         driver_error=driver_error)


def _cases():
    jpeg = synthetic_jpeg()
    eoi = len(jpeg) - 2
    small = synthetic_jpeg(width=160, height=120)
    assert len(small) < 60_000
    huge_app = b"\xff\xd8\xff\xe0\xff\xff" + small[2:]  # an APP0 length that goes past the end
    return {
        "valid": (jpeg, None, False, 0),
        "no SOI": (b"\x00\x00" + jpeg[2:], None, False, NO_SOI_EOI),
        "no EOI": (jpeg[:eoi], None, False, NO_SOI_EOI),
        "length mismatch": (jpeg, len(jpeg) + 100, False, NO_SOI_EOI),
        "driver error": (jpeg, None, True, CAPTURE_ERROR),
        "byte after EOI not 00 or FF": (jpeg + b"\x00\x41", None, False, NO_SOI_EOI),
        "EOI not in the final 4096 bytes": (jpeg + bytes(4097), None, False, NO_SOI_EOI),
        "segment length past the end": (huge_app, None, False, NO_SOI_EOI),
        "1 KiB of 00 after EOI": (jpeg + bytes(1024), None, False, 0),
        "1 KiB of FF after EOI": (jpeg + b"\xff" * 1024, None, False, 0),
        "601 junk bytes before EOI": (jpeg[:eoi] + bytes(range(1, 255)) * 2 + bytes(range(1, 94)) + jpeg[eoi:],
                                      None, False, 0),
    }


@pytest.mark.parametrize("case", list(_cases()))
def test_t_ring_17_capture_check(case):
    """T-RING-17, section 5.2 [A18]: synthetic JPEGs with no SOI, no EOI, a length mismatch, a
    driver error, 1 KiB of `00` and of `FF` after EOI, and 601 junk bytes before EOI. Flags per
    5.2; the last three are accepted unflagged. The other rules of 5.2.2 and 5.2.4 are checked
    too."""
    payload, delivered_len, driver_error, expected = _cases()[case]
    if case == "601 junk bytes before EOI":
        assert len(payload) - len(synthetic_jpeg()) == 601
    out, flags = _check(payload, delivered_len, driver_error)
    assert flags & (ERROR_MASK | DHT_INSERTED) == expected, hex(flags)
    assert out is payload  # these frames have DHT, so no copy (5.7)


def _cut_cases(jpeg):
    """Cuts at each 1 % of the length and at len - 1; each also zero-filled to full length."""
    cuts = sorted({len(jpeg) * p // 100 for p in range(100)} | {len(jpeg) - 1})
    for cut in cuts:
        yield f"cut {cut}", jpeg[:cut], cut  # the driver reports the cut length: the length rule does not help
        yield f"cut {cut} zero-filled", jpeg[:cut] + bytes(len(jpeg) - cut), len(jpeg)


@pytest.mark.parametrize(("sampling", "restart"), VARIANTS, ids=VARIANT_IDS)
def test_t_ring_18_cut_off_frame_never_reaches_a_reader_unflagged(cleanup, sampling, restart):
    """T-RING-18 (critical), sections 4, 5.2, 5.6, 6.2 (R9) and 6.3: synthetic JPEGs (4:2:0 and
    4:2:2, with and without restart markers) cut at each 1 % of their length and at len - 1, and
    also cut and zero-filled back to full length. Each goes through check, write and read. Each
    reads `FLAGGED` with `NO_SOI_EOI` and `payload = None`, by number, newest and nearest."""
    fr = ring()
    jpeg = synthetic_jpeg(sampling, restart)
    assert sampling_of(jpeg) == {"420": 0x22, "422": 0x21}[sampling]
    has_restart = any(bytes([0xFF, 0xD0 + n]) in jpeg[jpeg_segments(jpeg)[-1][2]:] for n in range(8))
    assert has_restart == bool(restart)
    _, creator, writer, reader = new_ring(cleanup, fps_num=2)
    count = 0
    for label, payload, delivered_len in _cut_cases(jpeg):
        checked, flags = fr.check_jpeg(payload, delivered_len=delivered_len, driver_error=False)
        assert flags & NO_SOI_EOI, label
        writer.write(checked, **write_kwargs(count, flags=flags))
        for read in (reader.read(count), reader.read_newest(),
                     reader.read_nearest(write_kwargs(count)["arrival_ns"])):
            assert read.result == fr.ReadResult.FLAGGED, (label, read.result)
            assert read.flags & NO_SOI_EOI, label
            assert read.payload is None, label
        count += 1
    assert count == 2 * len({len(jpeg) * p // 100 for p in range(100)} | {len(jpeg) - 1})
    header = parse_ring_header(cleanup.handle(open_raw(creator.name)).buf)
    assert header["cut_off_count"] == count


READ_CALLS = {"read", "read_newest", "read_nearest"}
LEAKY_TYPES = (bytes, bytearray, memoryview, np.ndarray, shared_memory.SharedMemory)


def test_t_ring_18_reader_api_has_no_call_that_returns_a_flagged_payload(cleanup):
    """T-RING-18 (critical), sections 4, 6.3 and 6.6: the reader API has no call that returns a
    flagged payload.

    The public surface of `FrameRingReader` is checked: each public callable is `attach`,
    `close` or one of the lookups of 6.5, and each lookup returns no payload for a flagged frame.
    No public attribute holds bytes or a view of the block. A new public call must be added to
    READ_CALLS here, with its own flagged-frame check. `FrameRead` has the fields of 6.6 and is
    frozen.
    """
    fr = ring()
    _, _, writer, reader = new_ring(cleanup, fps_num=4)
    jpeg = synthetic_jpeg()
    cut, flags = fr.check_jpeg(jpeg[: len(jpeg) // 2], delivered_len=len(jpeg) // 2, driver_error=False)
    writer.write(cut, **write_kwargs(0, flags=flags))
    calls = {"read": (0,), "read_newest": (), "read_nearest": (write_kwargs(0)["arrival_ns"],)}
    for name in dir(reader):
        if name.startswith("_"):
            continue
        value = getattr(reader, name)
        if callable(value):
            assert name in READ_CALLS | {"attach", "close"}, f"unreviewed public call: {name}"
        else:
            assert not isinstance(value, LEAKY_TYPES), f"public attribute {name} exposes bytes"
    for name in READ_CALLS:
        read = getattr(reader, name)(*calls[name])
        assert read.result == fr.ReadResult.FLAGGED, name
        assert read.payload is None, name
        for field in dataclasses.fields(read):
            if field.name != "payload":
                assert not isinstance(getattr(read, field.name), LEAKY_TYPES), field.name
    assert [field.name for field in dataclasses.fields(fr.FrameRead)] == [
        "result", "frame_number", "arrival_ns", "sample_ns", "published_ns", "source_frame_number",
        "flags", "rotation_cw_deg", "payload_len", "payload"]
    assert fr.FrameRead.__dataclass_params__.frozen
    assert {member.name for member in fr.ReadResult} == {
        "OK", "NOT_YET_WRITTEN", "LAPPED", "MISSING", "CORRUPT", "OVERSIZE", "FLAGGED", "CLOSED"}
    assert inspect.isclass(fr.FrameRingReader)


def test_t_ring_19_huffman_tables_inserted(cleanup):
    """T-RING-19, sections 5.2 (step 6) [A19] and 5.7: strip the DHT segments from a synthetic
    JPEG. The standard tables (ITU-T T.81 Annex K.3) are inserted as one 420-byte segment
    immediately before SOS; the frame decodes with cv2 to the pixels of the original;
    `DHT_INSERTED` and the counter are set."""
    fr = ring()
    original = synthetic_jpeg("420", 0)
    stripped = strip_dht(original)
    assert all(marker != 0xC4 for marker, _, _ in jpeg_segments(stripped))
    out, flags = fr.check_jpeg(stripped, delivered_len=len(stripped), driver_error=False)
    assert flags & DHT_INSERTED
    assert not flags & ERROR_MASK
    sos = jpeg_segments(stripped)[-1][1]
    assert len(out) == len(stripped) + 420
    assert out[:sos] == stripped[:sos] and out[sos + 420:] == stripped[sos:]
    assert out[sos:sos + 2] == b"\xff\xc4" and int.from_bytes(out[sos + 2:sos + 4], "big") == 418
    # cv2 (libjpeg) writes the Annex K tables, one per DHT segment: the same four tables.
    expected_tables = set()
    for marker, start, end in jpeg_segments(original):
        if marker == 0xC4:
            expected_tables |= dht_tables(original, start, end)
    assert dht_tables(out, sos, sos + 420) == expected_tables
    decoded = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)
    reference = cv2.imdecode(np.frombuffer(original, np.uint8), cv2.IMREAD_COLOR)
    np.testing.assert_array_equal(decoded, reference)
    _, creator, writer, reader = new_ring(cleanup, fps_num=4)
    writer.write(out, **write_kwargs(0, flags=flags))
    read = reader.read(0)
    assert read.result == fr.ReadResult.OK and read.payload == out and read.flags & DHT_INSERTED
    assert parse_ring_header(cleanup.handle(open_raw(creator.name)).buf)["dht_inserted_count"] == 1


def test_t_ring_19_frame_with_dht_is_the_same_object():
    """T-RING-19, sections 5.2 and 5.7: a frame that has DHT is the same object (no copy)."""
    jpeg = synthetic_jpeg("422", 8)
    out, flags = _check(jpeg)
    assert out is jpeg
    assert not flags & (DHT_INSERTED | ERROR_MASK)
