"""Uncompressed frames, JPEG parsing and a fake Quick Sync encoder for the step 3b tests
(specs/windows-capture.md, section 13; specs/frame-ring.md, section 8.7).

- `synthetic_raw(format, width, height, outside=0.0)`: a YUY2 `(h, w, 2)` or NV12 `(h * 3 / 2, w)`
  uint8 frame, made in code. Its Y values are in 16 to 235, except a share `outside` of them, which
  is 4. Thus a test sets the share of the range rule of 13.3 exactly: 0 gives a limited-range frame,
  more than 0.01 a frame that the rule must call full range. No camera frame is used.
- `jpeg_chroma(jpeg)` and `jpeg_quant_tables(jpeg)` read the SOF and DQT segments. `Q90_TABLES` are
  the tables of a `cv2.imencode` JPEG at quality 90.
- `FakeQuickSyncEncoder` and `QuickSyncFake`: the Quick Sync check and encoder of the product module
  `capture.encoder` (ADR-3WCA) replaced in this process (THREAD workers). No Intel GPU is needed.
"""

import importlib
import struct
import threading

import cv2
import numpy as np

ENCODER_MODULE = "skellycam.core.camera.capture.encoder"
RAW_FORMATS = ("YUY2", "NV12")
OUTSIDE_VALUE = 4  # a Y value below 16
QUICK_SYNC_MARK = b"fake quick sync"
_TO_BGR = {"YUY2": cv2.COLOR_YUV2BGR_YUY2, "NV12": cv2.COLOR_YUV2BGR_NV12}


# ---------------------------------------------------------------------------
# Synthetic YUY2 and NV12 frames
# ---------------------------------------------------------------------------

def raw_shape(fmt, width, height):
    """The shape of a raw frame, as `DecodeInput` expects (ring 8.7, spec 13.2)."""
    return (height, width, 2) if fmt == "YUY2" else (height * 3 // 2, width)


_RAW_CACHE = {}


def synthetic_raw(fmt, width, height, outside=0.0):
    """A new raw frame (a copy of a cached frame). See the module docstring."""
    key = (fmt, width, height, outside)
    if key not in _RAW_CACHE:
        x = np.linspace(40, 200, width)
        y_plane = np.broadcast_to(x, (height, width)).astype(np.uint8).copy()
        count = round(outside * width * height)
        y_plane.reshape(-1)[:count] = OUTSIDE_VALUE
        chroma = np.where(np.arange(width) % 2 == 0, 100, 156).astype(np.uint8)  # U, V alternate
        if fmt == "YUY2":
            frame = np.stack([y_plane, np.broadcast_to(chroma, (height, width))], axis=2)
        elif fmt == "NV12":
            frame = np.concatenate([y_plane, np.broadcast_to(chroma, (height // 2, width))], axis=0)
        else:
            raise ValueError(f"not a raw format: {fmt}")
        _RAW_CACHE[key] = np.ascontiguousarray(frame)
    return _RAW_CACHE[key].copy()


def y_values(raw, fmt):
    if fmt == "YUY2":
        return raw[:, :, 0]
    return raw[: raw.shape[0] * 2 // 3]


def share_outside(raw, fmt):
    """The share of Y values outside 16 to 235 (13.3)."""
    y = y_values(raw, fmt)
    return float(np.count_nonzero((y < 16) | (y > 235))) / y.size


def to_bgr(raw, fmt):
    """The default OpenCV conversion (ADR-467Z item 4)."""
    return cv2.cvtColor(raw, _TO_BGR[fmt])


# ---------------------------------------------------------------------------
# JPEG segments
# ---------------------------------------------------------------------------

def _segments(jpeg):
    """(marker, body) of each segment from SOI to the first SOS."""
    data = bytes(jpeg)
    assert data[:2] == b"\xff\xd8", "no SOI"
    offset = 2
    while offset + 4 <= len(data):
        assert data[offset] == 0xFF, f"no marker at byte {offset}"
        marker = data[offset + 1]
        length = struct.unpack(">H", data[offset + 2: offset + 4])[0]
        yield marker, data[offset + 4: offset + 2 + length]
        if marker == 0xDA:
            return
        offset += 2 + length


def jpeg_sampling(jpeg):
    """(H, V) of each component of the frame header (SOF0, SOF1 or SOF2)."""
    for marker, body in _segments(jpeg):
        if marker in (0xC0, 0xC1, 0xC2):
            count = body[5]
            return [(body[7 + 3 * k] >> 4, body[7 + 3 * k] & 0x0F) for k in range(count)]
    raise AssertionError("no frame header")


def jpeg_chroma(jpeg):
    """The chroma layout of a 3-component JPEG: "4:4:4", "4:2:2", "4:2:0" or the raw factors."""
    sampling = jpeg_sampling(jpeg)
    names = {((1, 1), (1, 1), (1, 1)): "4:4:4", ((2, 1), (1, 1), (1, 1)): "4:2:2",
             ((2, 2), (1, 1), (1, 1)): "4:2:0"}
    return names.get(tuple(sampling), str(sampling))


def jpeg_quant_tables(jpeg):
    """{table id: the 64 (or 128) bytes of the table} of each DQT segment."""
    tables = {}
    for marker, body in _segments(jpeg):
        if marker != 0xDB:
            continue
        offset = 0
        while offset < len(body):
            precision, table_id = body[offset] >> 4, body[offset] & 0x0F
            size = 128 if precision else 64
            tables[table_id] = body[offset + 1: offset + 1 + size]
            offset += 1 + size
    return tables


def _q90_tables():
    image = np.zeros((16, 16, 3), np.uint8)
    return jpeg_quant_tables(cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1].tobytes())


Q90_TABLES = _q90_tables()


def with_mark(jpeg, text):
    """Insert a JPEG comment segment (COM) after SOI."""
    return jpeg[:2] + b"\xff\xfe" + struct.pack(">H", len(text) + 2) + text + jpeg[2:]


def is_quick_sync_jpeg(payload):
    return payload is not None and QUICK_SYNC_MARK in bytes(payload)[:64]


# ---------------------------------------------------------------------------
# The fake Quick Sync encoder
# ---------------------------------------------------------------------------

class FakeQuickSyncEncoder:
    """A stand-in for the Quick Sync encoder of 13.2 (ADR-3WCA). It holds one frame, as Quick Sync at
    `async_depth` 2 [notes: Encoder settings]: `encode(raw)` gives the JPEG of the frame before it,
    and `flush()` gives the JPEG of the held frame. Each JPEG is a q90 `cv2.imencode` JPEG of the
    frame with a comment segment that holds `QUICK_SYNC_MARK` and the input number.

    `encode` raises `RuntimeError` at the first call for which the `fail_when` of its owner gives
    true. After that, `flush()` also raises, as a failed device does: the held frame must be encoded
    again from its raw frame (13.2). `encode` raises `ValueError` for a frame of the wrong shape,
    after it records the shape."""

    def __init__(self, owner, fmt, width, height, quality):
        self.owner, self.format, self.width, self.height, self.quality = owner, fmt, width, height, quality
        self.shapes = []  # the shape of each input, also of a refused input
        self.accepted = 0  # inputs that the encoder took
        self.outputs = 0  # JPEGs that came out
        self.failed = False
        self.closed = False
        self._held = None

    def encode(self, raw):
        self.shapes.append(tuple(np.shape(raw)))
        if self.owner.should_fail():
            self.failed = True
            raise RuntimeError("fake Quick Sync encoder: the device failed")
        if tuple(np.shape(raw)) != raw_shape(self.format, self.width, self.height):
            raise ValueError(f"fake Quick Sync encoder: a frame of shape {np.shape(raw)}")
        out = self.flush()
        self._held = (self.accepted, raw)
        self.accepted += 1
        return out

    def flush(self):
        if self.failed:
            raise RuntimeError("fake Quick Sync encoder: the device failed")
        if self._held is None:
            return []
        number, raw = self._held
        self._held = None
        jpeg = cv2.imencode(".jpg", to_bgr(raw, self.format), [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1].tobytes()
        self.outputs += 1
        return [with_mark(jpeg, QUICK_SYNC_MARK + b" %d" % number)]

    def close(self):
        self.closed = True


class QuickSyncFake:
    """Replaces `quick_sync_works` (the central check of 13.2) and `open_quick_sync_encoder` of the
    product module `capture.encoder` (ADR-3WCA), with `monkeypatch`. `module` is the product module;
    a self-test gives a stand-in.

    - `available`: the result of the check. `checks`: the number of check calls.
    - `encoders`: each `FakeQuickSyncEncoder` that the product opened, in order.
    - `fail_when`: a callable with no argument; the first `encode` call for which it gives true raises.
      `failures` counts the raised failures."""

    def __init__(self, monkeypatch, available=True, module=None):
        self.module = module or importlib.import_module(ENCODER_MODULE)
        self.available = available
        self.checks = 0
        self.encoders = []
        self.fail_when = None
        self.failures = 0
        self._lock = threading.Lock()
        monkeypatch.setattr(self.module, "quick_sync_works", self._check)
        monkeypatch.setattr(self.module, "open_quick_sync_encoder", self._open)

    def _check(self):
        with self._lock:
            self.checks += 1
        return self.available

    def _open(self, fmt, width, height, *, quality):
        assert self.available, "the product opened a Quick Sync encoder after a check that gave False"
        encoder = FakeQuickSyncEncoder(self, fmt, width, height, quality)
        with self._lock:
            self.encoders.append(encoder)
        return encoder

    def should_fail(self):
        with self._lock:
            if self.fail_when is not None and self.failures == 0 and self.fail_when():
                self.failures += 1
                return True
        return False
