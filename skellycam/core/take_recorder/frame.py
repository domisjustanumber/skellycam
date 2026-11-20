"""The input of the camera writer (specs/recorder.md, section 4.1)."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RecorderFrame:
    payload: bytes  # the same object that the ring gets: never copied (5.1)
    frame_number: int
    arrival_ns: int
    sample_ns: int  # NO_SAMPLE_NS of the ring package gives an empty CSV field
    source_frame_number: int
    flags: int  # ring flags; a bit of the error mask 0x0F makes the row `missing` (7.2)
    delivered_len: int
    rotation_cw_deg: int
