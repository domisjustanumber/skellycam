"""The barcode JPEGs of the step 4b UI tests (specs/preview-4b.md 7.2): noise and the barcode of
`skellycam-ui/src/player/tests/fixtures/jpeg.ts`, made with `cv2.imencode`.

The barcode: 16 cells in one row, the camera number in 4 bits, then the frame number modulo 60 in 12
bits, most significant bit first. The layout is the 256 x 128 design of `jpeg.ts` (`CELL`, `BARCODE_Y`),
scaled to the image size, as `bench.ts` of the player draws it. A one cell is `#ebebeb`, a zero cell
`#141414`. The camera numbers are 1 to 8, never 0, so a black tile does not read as a frame.

The JPEGs are synthetic and stay in memory. Never write one into the repository.
"""

import functools

import cv2
import numpy as np

# jpeg.ts: IMAGE_WIDTH, IMAGE_HEIGHT, CELL, BARCODE_Y, CAMERA_BITS, POSITION_BITS
DESIGN_WIDTH, DESIGN_HEIGHT = 256, 128
CELL = 16
BARCODE_Y = 32
CAMERA_BITS, POSITION_BITS = 4, 12
CYCLE = 60  # the frame number of the barcode is modulo 60
ONE, ZERO = 235, 20  # the gray value of a one cell and of a zero cell
QUALITY = 90
COMPONENT_SIZE = (640, 360)
BENCH_SIZE = (1920, 1080)
BENCH_TARGET_BYTES = 190_000  # near the mean 1080p JPEG of the C922 (192,382 B) [player 12.2]


def barcode_bits(camera, position):
    """`barcodeBits` of jpeg.ts."""
    return ([(camera >> i) & 1 for i in range(CAMERA_BITS - 1, -1, -1)]
            + [(position >> i) & 1 for i in range(POSITION_BITS - 1, -1, -1)])


def _cell_box(i, width, height):
    sx, sy = width / DESIGN_WIDTH, height / DESIGN_HEIGHT
    x0, y0 = int(np.floor(i * CELL * sx)), int(np.floor(BARCODE_Y * sy))
    return x0, y0, x0 + int(np.ceil(CELL * sx)), y0 + int(np.ceil(CELL * sy))


@functools.cache
def _pattern(width, height):
    y, x = np.mgrid[0:height, 0:width]
    return (((x * 7 + y * 13) % 17) - 8).astype(np.float32)


def barcode_image(camera, position, width, height, amplitude=24.0, seed=1):
    """A BGR image: smooth noise (a random value for each 8 x 8 cell, so the JPEG size follows
    `amplitude`) with the barcode row."""
    rng = np.random.default_rng(seed)
    cells = (rng.random((-(-height // 8), -(-width // 8)), dtype=np.float32) - 0.5) * amplitude
    noise = np.repeat(np.repeat(cells, 8, axis=0), 8, axis=1)[:height, :width]
    noise = noise + _pattern(width, height) * (amplitude / 64)
    image = np.stack([110 + noise, 120 + noise, 128 + noise], axis=2)
    image = np.clip(image, 0, 255).astype(np.uint8)
    for i, bit in enumerate(barcode_bits(camera, position)):
        x0, y0, x1, y1 = _cell_box(i, width, height)
        image[y0:y1, x0:x1] = ONE if bit else ZERO
    return image


def encode(image):
    ok, data = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), QUALITY])
    assert ok, "cv2.imencode failed"
    return data.tobytes()


def read_barcode(jpeg, width, height):
    """(camera, position) at the centre of each cell of a decoded JPEG: the self-check of `make_jpegs`."""
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
    assert image is not None and image.shape == (height, width), "the JPEG does not decode to its size"
    bits = []
    for i in range(CAMERA_BITS + POSITION_BITS):
        x0, y0, x1, y1 = _cell_box(i, width, height)
        bits.append(1 if image[(y0 + y1) // 2, (x0 + x1) // 2] > 128 else 0)
    value = int("".join(map(str, bits)), 2)
    return value >> POSITION_BITS, value & (2 ** POSITION_BITS - 1)


@functools.cache
def amplitude_for(width, height, target_bytes):
    """The noise amplitude that gives JPEGs of about `target_bytes` (within 10 %), as `bench.ts` finds it."""
    amplitude = 24.0
    for _ in range(8):
        size = len(encode(barcode_image(1, 0, width, height, amplitude)))
        if abs(size - target_bytes) < target_bytes * 0.1:
            break
        amplitude *= (target_bytes / size) ** 0.5
    return amplitude


def make_jpegs(camera, width, height, target_bytes=None, count=CYCLE):
    """`count` distinct JPEGs of one camera, one for each frame number modulo 60. Each one is checked to
    decode and to hold its barcode before a run (6.2)."""
    assert 1 <= camera <= 8, f"camera number {camera}: 1 to 8, never 0"
    amplitude = amplitude_for(width, height, target_bytes) if target_bytes else 24.0
    jpegs = []
    for position in range(count):
        jpeg = encode(barcode_image(camera, position, width, height, amplitude, seed=camera * 1000 + position))
        assert read_barcode(jpeg, width, height) == (camera, position), f"barcode of camera {camera} frame {position}"
        jpegs.append(jpeg)
    return jpegs
