"""Synthetic JPEG frames and an SOF parser for the recorder tests (specs/recorder.md, sections 6.4, 11, 12).

Synthetic images only. No camera frame and no recording goes into the repository: each test writes
its media to its pytest `tmp_path`. This file imports no code of `skellycam.core.take_recorder`, so it
is an independent check of the product.
"""

import struct
from dataclasses import dataclass

import cv2
import numpy as np

# Chroma layouts: the H/V sampling factors of each component (6.4, T-REC-34).
LAYOUTS = {
    "444": ((1, 1), (1, 1), (1, 1)),
    "422": ((2, 1), (1, 1), (1, 1)),
    "420": ((2, 2), (1, 1), (1, 1)),
    "440": ((1, 2), (1, 1), (1, 1)),
    "411": ((4, 1), (1, 1), (1, 1)),
    "grey": ((1, 1),),
}
CV2_SAMPLING = {
    "444": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444,
    "422": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_422,
    "420": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_420,
    "440": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_440,
    "411": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_411,
}
# The pixel format of an OpenCV JPEG of each layout, as FFmpeg names it (T-REC-34).
PYAV_PIX_FMT = {
    "444": "yuvj444p", "422": "yuvj422p", "420": "yuvj420p", "440": "yuvj440p", "411": "yuvj411p",
    "grey": "gray",
}

SOF_MARKERS = (0xC0, 0xC1, 0xC2)
APP0 = 0xE0
APP1 = 0xE1
APP14 = 0xEE
DHT = 0xC4
SOS = 0xDA


@dataclass(frozen=True)
class Sof:
    """The fields of an SOF segment that the layout compare uses (6.4): size and H/V factors."""

    marker: int
    width: int
    height: int
    factors: tuple  # ((h, v), ...) for each component, in SOF order
    component_ids: tuple
    table_selectors: tuple


def pattern(index, width, height, channels=3):
    """A moving test pattern: a gradient with a bright square whose place depends on `index`."""
    y, x = np.mgrid[0:height, 0:width]
    base = ((x * 255 // max(width - 1, 1) + y * 128 // max(height - 1, 1) + index * 7) % 256).astype(np.uint8)
    side = max(8, min(width, height) // 6)
    px = (index * 13) % max(width - side, 1)
    py = (index * 5) % max(height - side, 1)
    base[py:py + side, px:px + side] = 255 - (index % 64)
    if channels == 1:
        return base
    image = np.stack([base, np.roll(base, index % width, axis=1), 255 - base], axis=2)
    return np.ascontiguousarray(image)


def synthetic_jpeg(index, width=640, height=480, layout="422", quality=90):
    """A synthetic JPEG of `pattern(index)` with the chroma layout `layout` (a key of LAYOUTS)."""
    if layout == "grey":
        ok, encoded = cv2.imencode(".jpg", pattern(index, width, height, 1), [cv2.IMWRITE_JPEG_QUALITY, quality])
    else:
        params = [cv2.IMWRITE_JPEG_QUALITY, quality, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, CV2_SAMPLING[layout]]
        ok, encoded = cv2.imencode(".jpg", pattern(index, width, height), params)
    if not ok:
        raise RuntimeError("cv2.imencode failed")
    return encoded.tobytes()


def small_jpeg(index, width=320, height=240):
    """A small JPEG (about 2.3 kB at 320x240, 4:2:2): a smooth gradient that moves with `index`.

    The small-frame cases of T-REC-10 and T-REC-KILL use it: below about 4 KiB the muxer holds more
    than one block without `cluster_size_limit=1` (6.3, review B1)."""
    x = np.arange(width)
    row = ((x * 255 // max(width - 1, 1) + index * 7) % 256).astype(np.uint8)
    grey = np.broadcast_to(row, (height, width))
    image = np.ascontiguousarray(np.stack([grey, grey, grey], axis=2))
    params = [cv2.IMWRITE_JPEG_QUALITY, 10, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, CV2_SAMPLING["422"]]
    ok, encoded = cv2.imencode(".jpg", image, params)
    if not ok:
        raise RuntimeError("cv2.imencode failed")
    return encoded.tobytes()


def padded(payload, size):
    """`payload` with bytes after EOI up to `size` bytes. A reader accepts them (SFF-738); the
    recorder stores them unchanged (SFF-734). T-REC-36 uses it for frames of 600 kB."""
    return payload + bytes(max(0, size - len(payload)))


def segments(data):
    """The marker segments of a JPEG from SOI to the first SOS: a list of (marker, start, end).

    `start` is the offset of the 0xFF byte, `end` is the offset after the segment. The SOS item ends
    after its header; the entropy-coded data follows.
    """
    if data[:2] != b"\xff\xd8":
        raise ValueError("no SOI")
    out, pos = [], 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            raise ValueError(f"no marker at offset {pos}")
        marker = data[pos + 1]
        if marker == 0xFF:  # fill byte
            pos += 1
            continue
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        out.append((marker, pos, pos + 2 + length))
        if marker == SOS:
            return out
        pos += 2 + length
    raise ValueError("no SOS")


def parse_sof(data):
    """The SOF segment (FFC0, FFC1 or FFC2) of a JPEG as `Sof`, written from ITU-T T.81 B.2.2."""
    for marker, start, end in segments(data):
        if marker in SOF_MARKERS:
            body = data[start + 4:end]
            height, width = struct.unpack(">HH", body[1:5])
            count = body[5]
            ids, factors, tables = [], [], []
            for i in range(count):
                cid, hv, tq = body[6 + 3 * i:9 + 3 * i]
                ids.append(cid)
                factors.append((hv >> 4, hv & 0x0F))
                tables.append(tq)
            return Sof(marker, width, height, tuple(factors), tuple(ids), tuple(tables))
    raise ValueError("no SOF0, SOF1 or SOF2 segment")


def layout_name(sof):
    """The key of LAYOUTS whose factors equal those of `sof`, or None."""
    for name, factors in LAYOUTS.items():
        if factors == sof.factors:
            return name
    return None


def insert_segment(data, marker, payload):
    """`data` with one APPn (or other) segment inserted after SOI."""
    return data[:2] + bytes((0xFF, marker)) + struct.pack(">H", len(payload) + 2) + payload + data[2:]


def strip_dht(data):
    """`data` with each DHT segment before the first SOS removed (a camera that sends no DHT)."""
    out, last = [], 0
    for marker, start, end in segments(data):
        if marker == DHT:
            out.append(data[last:start])
            last = end
    out.append(data[last:])
    return b"".join(out)


def exif_segment():
    """A small APP1 EXIF payload with an orientation tag of 6 (a reader ignores it, SFF-738)."""
    tiff = b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 1) + struct.pack("<HHII", 0x0112, 3, 1, 6) + b"\x00" * 4
    return b"Exif\x00\x00" + tiff


def decode_bgr(data):
    """Decode with OpenCV. None when OpenCV cannot decode."""
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)


def decode_pyav(data):
    """Decode one JPEG with the PyAV MJPEG decoder: (pixel format name, Y plane as an array)."""
    import av

    codec = av.CodecContext.create("mjpeg", "r")
    frames = codec.decode(av.Packet(data)) + codec.decode(None)
    if len(frames) != 1:
        raise ValueError(f"{len(frames)} frames decoded")
    frame = frames[0]
    plane = frame.planes[0]
    y = np.frombuffer(bytes(plane), np.uint8).reshape(-1, plane.line_size)[: frame.height, : frame.width]
    return frame.format.name, y
