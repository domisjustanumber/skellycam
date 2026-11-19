"""Wire format of the websocket image message. The interim relay fills it with ring JPEGs (spec 2.3)."""
import numpy as np


class MessageType:
    PAYLOAD_HEADER = 0
    FRAME_HEADER = 1
    PAYLOAD_FOOTER = 2


FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE = np.dtype(
    [
        (
            "message_type",
            "<u1",
        ),  # 1 byte: 0 = payload_header, 1 = frame_header, 2 = payload_footer
        ("frame_number", "<i8"),  # 8 bytes, little-endian int64
        ("number_of_cameras", "<i4"),  # 4 bytes, little-endian int32
    ],
    align=True,
)

FRONTEND_FRAME_HEADER_DTYPE = np.dtype(
    [
        (
            "message_type",
            "<u1",
        ),  # 1 byte: 0 = payload_header, 1 = frame_header, 2 = payload_footer
        ("frame_number", "<i8"),  # 8 bytes, little-endian int64
        ("camera_id", "S16"),  # 16 bytes fixed-length camera ID
        ("camera_index", "<i4"),  # 4 bytes, little-endian int32
        ("image_width", "<i4"),  # 4 bytes, little-endian int32
        ("image_height", "<i4"),  # 4 bytes, little-endian int32
        ("color_channels", "<i4"),  # 4 bytes, little-endian int32
        (
            "jpeg_string_length",
            "<i4",
        ),  # 4 bytes, length of the JPEG string, little-endian int32
    ],
    align=True,
)
