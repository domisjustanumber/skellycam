"""Capture check of a JPEG frame (specs/frame-ring.md, section 5.2)."""
from skellycam.core.ipc.frame_ring.layout import FrameFlag

EOI_WINDOW = 4096

# ITU-T T.81 Annex K.3 (tables K.3 to K.6) as one DHT segment: luminance DC, luminance AC,
# chrominance DC, chrominance AC. 420 bytes: FF C4, length 418, then 4 x (Tc/Th, 16 counts, values).
STANDARD_DHT = bytes.fromhex(
    "ffc401a2"
    "00" "00010501010101010100000000000000" "000102030405060708090a0b"
    "10" "0002010303020403050504040000017d"
    "01020300041105122131410613516107227114328191a1082342b1c11552d1f0"
    "2433627282090a161718191a25262728292a3435363738393a434445464748494a"
    "535455565758595a636465666768696a737475767778797a838485868788898a"
    "92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7"
    "c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9fa"
    "01" "00030101010101010101010000000000" "000102030405060708090a0b"
    "11" "00020102040403040705040400010277"
    "000102031104052131061241510761711322328108144291a1b1c109233352f0"
    "156272d10a162434e125f11718191a262728292a35363738393a434445464748"
    "494a535455565758595a636465666768696a737475767778797a828384858687"
    "88898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3"
    "c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8"
    "f9fa"
)


def check_jpeg(payload: bytes, *, delivered_len: int, driver_error: bool) -> tuple[bytes, int]:
    """Validate one frame at capture (rules 1 to 6 of 5.2). Return the payload and its flags.

    The payload is the same object, except after a DHT insertion (the one permitted copy, 5.7).
    """
    flags = FrameFlag.CAPTURE_ERROR if driver_error else FrameFlag(0)
    n = len(payload)
    walk = _walk_to_sos(payload) if n == delivered_len and payload[:2] == b"\xff\xd8" else None
    eoi = payload.rfind(b"\xff\xd9", max(0, n - EOI_WINDOW))
    if walk is None or eoi < 0 or payload[eoi + 2:].strip(b"\x00\xff"):
        return payload, flags | FrameFlag.NO_SOI_EOI
    sos, has_dht = walk
    if flags or has_dht:
        return payload, flags
    view = memoryview(payload)
    return b"".join((view[:sos], STANDARD_DHT, view[sos:])), flags | FrameFlag.DHT_INSERTED


def _walk_to_sos(payload: bytes) -> tuple[int, bool] | None:
    """Step through the marker segments from SOI to the first SOS (rule 4).

    Return the offset of SOS and whether a DHT segment came before it, or None when a segment does
    not fit in the payload.
    """
    i, n, has_dht = 2, len(payload), False
    while i + 4 <= n and payload[i] == 0xFF:
        marker = payload[i + 1]
        if marker == 0xFF:  # a fill byte before a marker
            i += 1
            continue
        end = i + 2 + int.from_bytes(payload[i + 2:i + 4], "big")
        if end > n:
            return None
        if marker == 0xDA:
            return i, has_dht
        has_dht |= marker == 0xC4
        i = end
    return None
