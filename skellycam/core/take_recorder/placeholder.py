"""The SOF parse and the hand-built black placeholder JPEG (specs/recorder.md, section 6.4)."""
import math
from dataclasses import dataclass

SOF_MARKERS = (0xC0, 0xC1, 0xC2)
SOS = 0xDA


@dataclass(frozen=True)
class JpegLayout:
    width: int
    height: int
    factors: tuple  # ((h, v), ...) for each component, in SOF order


def parse_sof(payload: bytes) -> JpegLayout:
    """The size and the H/V factors of the SOF segment (FFC0, FFC1 or FFC2) before the first SOS."""
    if payload[:2] != b"\xff\xd8":
        raise ValueError("no SOI")
    i, n = 2, len(payload)
    while i + 4 <= n and payload[i] == 0xFF:
        marker = payload[i + 1]
        if marker == 0xFF:  # a fill byte before a marker
            i += 1
            continue
        length = int.from_bytes(payload[i + 2:i + 4], "big")
        end = i + 2 + length
        if marker == SOS or length < 2 or end > n:
            break
        if marker in SOF_MARKERS:
            body = payload[i + 4:end]
            if len(body) < 6 or len(body) < 6 + 3 * body[5]:
                break
            factors = tuple((body[7 + 3 * c] >> 4, body[7 + 3 * c] & 0x0F) for c in range(body[5]))
            layout = JpegLayout(int.from_bytes(body[3:5], "big"), int.from_bytes(body[1:3], "big"), factors)
            if layout.width and layout.height and factors and all(1 <= f <= 4 for hv in factors for f in hv):
                return layout
            break
        i = end
    raise ValueError("no SOF0, SOF1 or SOF2 segment before the first SOS")


def can_build(layout: JpegLayout) -> bool:
    """At most 3 components, and at most 10 blocks in one MCU (ITU-T T.81 B.2.3)."""
    return 1 <= len(layout.factors) <= 3 and sum(h * v for h, v in layout.factors) <= 10


def build_placeholder(layout: JpegLayout) -> bytes:
    """A flat black baseline JPEG with the size and factors of `layout`, built with no encoder.

    One DQT of 1s; DC codes `0` (category 0) and `10` (category 11); AC code `0` (EOB). The first Y
    block has the DC difference -1024 (Y = 0), each other block 0. Thus each block costs 2 bits.
    """
    if not can_build(layout):
        raise ValueError(f"a placeholder cannot be built for the factors {layout.factors}")
    width, height, factors = layout.width, layout.height, layout.factors
    count = len(factors)
    if count == 1:  # one component: one block for each MCU
        blocks = math.ceil(width / 8) * math.ceil(height / 8)
    else:
        h_max, v_max = max(h for h, _ in factors), max(v for _, v in factors)
        mcus = math.ceil(width / (8 * h_max)) * math.ceil(height / (8 * v_max))
        blocks = mcus * sum(h * v for h, v in factors)
    # First block: DC code 10, then -1024 in 11 bits (1023 = 0b01111111111), then EOB 0.
    bits = (0b10011111111110 << (2 * (blocks - 1)))
    length = 14 + 2 * (blocks - 1)
    pad = -length % 8
    entropy = ((bits << pad) | ((1 << pad) - 1)).to_bytes((length + pad) // 8, "big").replace(b"\xff", b"\xff\x00")

    def segment(marker, body):
        return bytes((0xFF, marker)) + (len(body) + 2).to_bytes(2, "big") + body

    sof = bytes((8,)) + height.to_bytes(2, "big") + width.to_bytes(2, "big") + bytes((count,))
    sof += b"".join(bytes((c + 1, (h << 4) | v, 0)) for c, (h, v) in enumerate(factors))
    sos = bytes((count,)) + b"".join(bytes((c + 1, 0x00)) for c in range(count)) + bytes((0, 63, 0))
    return b"".join((
        b"\xff\xd8",
        segment(0xDB, b"\x00" + b"\x01" * 64),
        segment(0xC0, sof),
        segment(0xC4, b"\x00" + bytes((1, 1) + (0,) * 14) + b"\x00\x0b"),
        segment(0xC4, b"\x10" + bytes((1,) + (0,) * 15) + b"\x00"),
        segment(SOS, sos),
        entropy,
        b"\xff\xd9",
    ))
