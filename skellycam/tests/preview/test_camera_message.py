"""The camera message: T-PRV-01 and T-PRV-03 (specs/preview.md, section 3).

Fake tests. The independent parser of `preview_helpers` reads each message at the offsets of
table 3.2.
"""

import struct

import pytest

from skellycam.tests.frame_ring.ring_spec import ring
from skellycam.tests.preview.preview_helpers import (
    HEADER_SIZE, MESSAGE_FIELDS, OVERSIZE_PAYLOAD_SIZE, SPEC_EXAMPLE, FakeConnection, FakeRing, frame_read,
    manager_with, parse_camera_message, preview, running_relay, wait_for)


@pytest.mark.parametrize("case", ["example", "flagged", "oversize", "layout"])
def test_t_prv_01_pack_camera_frame(case):
    """T-PRV-01, sections 3.2, 3.3 and 7: `pack_camera_frame` for the example of 3.2; a `FLAGGED` read
    with flags 0x04 and one with `OVERSIZE`; `CAMERA_FRAME_HEADER.size` and the offset of each field.

    The example gives the bytes of 3.2, byte for byte; the flagged messages are 48 bytes with
    `jpeg_len` 0 and the ring flags; size 48; offsets of table 3.2."""
    pr = preview()
    fr = ring()
    if case == "example":
        read = frame_read(fr.ReadResult.OK, 258, arrival_ns=1_000_000_007, flags=0x30, rotation=90,
                          payload=b"\xff\xd8\xff\xd9", source_frame_number=516)
        message = pr.pack_camera_frame("a1b2", read)
        assert type(message) is bytes, "one bytes object for each message (7, agent 25)"
        assert message == SPEC_EXAMPLE
    elif case in ("flagged", "oversize"):
        result, flags = (fr.ReadResult.FLAGGED, 0x04) if case == "flagged" else (fr.ReadResult.OVERSIZE, 0x01)
        read = frame_read(result, 7, arrival_ns=5_000_000_000, flags=flags, rotation=180,
                          payload_len=OVERSIZE_PAYLOAD_SIZE if case == "oversize" else 0)
        message = pr.pack_camera_frame("a1b2", read)
        assert len(message) == HEADER_SIZE
        parsed = parse_camera_message(message)
        assert parsed.jpeg_len == 0 and parsed.jpeg == b""
        assert parsed.flags == flags
        assert (parsed.version, parsed.frame_number, parsed.arrival_ns, parsed.rotation_cw_deg, parsed.camera_id) == (
            1, 7, 5_000_000_000, 180, "a1b2")
    else:
        assert pr.CAMERA_FRAME_VERSION == 1
        assert isinstance(pr.CAMERA_FRAME_HEADER, struct.Struct)
        assert pr.CAMERA_FRAME_HEADER.format == "<B3xIqqII16s"
        assert pr.CAMERA_FRAME_HEADER.size == HEADER_SIZE
        values = {"version": 0xA1, "flags": 0xA2A3A4A5, "frame_number": 0x0B0C0D0E0F101112,
                  "arrival_ns": 0x2122232425262728, "rotation_cw_deg": 0xB1B2B3B4, "jpeg_len": 0xC1C2C3C4,
                  "camera_id_raw": b"0123456789abcdef"}
        packed = pr.CAMERA_FRAME_HEADER.pack(*(values[name] for _, _, name in MESSAGE_FIELDS))
        assert packed[1:4] == b"\0\0\0", "reserved bytes 1 to 3"
        for offset, code, name in MESSAGE_FIELDS:
            assert struct.unpack_from("<" + code, packed, offset)[0] == values[name], f"offset of {name}"


FLAG_CASES = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x30, 0x14]


@pytest.mark.parametrize("flags", FLAG_CASES, ids=[f"0x{f:02x}" for f in FLAG_CASES])
async def test_t_prv_03_flags_and_header_only_messages(cleanup, flags):
    """T-PRV-03, sections 3.3 and 5.3: a frame with each flag bit 0x01 to 0x20, and with 0x30 and 0x14,
    through the sender. Each message has the 32 bits of the slot; 0x10, 0x20 and 0x30 carry the JPEG;
    each frame with a bit of 0x0F has `jpeg_len` 0 and no bytes after the header.

    The flags go to the ring writer as the capture check gives them. The writer sets no other bit
    here (constant rotation)."""
    fr = ring()
    a = FakeRing(cleanup, "a1b2")
    slot_reader = a.reader()
    connection = FakeConnection(answer=True)
    async with running_relay(manager_with({"a1b2": a.reader()}), connection):
        a.write(0, flags=flags)
        await wait_for(lambda: connection.camera("a1b2"), "one camera message")
    message = connection.camera("a1b2")[0]
    slot = slot_reader.read(0)
    assert message.frame_number == 0
    assert message.flags == slot.flags == flags
    if flags & 0x0F:
        assert slot.result in (fr.ReadResult.FLAGGED, fr.ReadResult.OVERSIZE)
        assert message.jpeg_len == 0 and message.jpeg == b"" and message.length == HEADER_SIZE
    else:
        assert slot.result is fr.ReadResult.OK
        assert message.jpeg_len == len(a.payload(0)) and message.jpeg == a.payload(0)
