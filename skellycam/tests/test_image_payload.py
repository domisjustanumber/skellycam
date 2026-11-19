"""The wire format of the websocket image message stays as it is until phase 4 (spec 2.1 and 2.3, A4).

The interim relay fills it with the ring JPEG of each camera. The UI parser reads these offsets.
"""

from skellycam.core.types.frontend_payload_bytearray import (
    FRONTEND_FRAME_HEADER_DTYPE, FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE, MessageType,
)


def _offsets(dtype):
    return {name: offset for name, (_, offset) in dtype.fields.items()}


def test_wire_format_is_unchanged() -> None:
    assert (MessageType.PAYLOAD_HEADER, MessageType.FRAME_HEADER, MessageType.PAYLOAD_FOOTER) == (0, 1, 2)
    assert FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE.itemsize == 24
    assert _offsets(FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE) == {
        "message_type": 0, "frame_number": 8, "number_of_cameras": 16}
    assert FRONTEND_FRAME_HEADER_DTYPE.itemsize == 56
    assert _offsets(FRONTEND_FRAME_HEADER_DTYPE) == {
        "message_type": 0, "frame_number": 8, "camera_id": 16, "camera_index": 32, "image_width": 36,
        "image_height": 40, "color_channels": 44, "jpeg_string_length": 48}
