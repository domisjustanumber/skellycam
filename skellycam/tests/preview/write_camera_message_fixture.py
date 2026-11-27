"""Write the shared fixture of the camera message (specs/preview-4b.md 7.2, T-PRV-25).

The file `skellycam-ui/src/services/server/preview/tests/camera-messages.json` holds one case for each row of 7.2.
Each case has its input fields (64-bit values as decimal strings) and the message of the real `pack_camera_frame`
as hex. The Python test T-PRV-25 and the TypeScript test T-PRV-32 read the same file. The JPEG bytes are synthetic.

- `uv run python skellycam/tests/preview/write_camera_message_fixture.py` writes the file.
- `uv run python skellycam/tests/preview/write_camera_message_fixture.py --check` compares the tracked file with a new output, writes
  nothing, and ends with exit code 1 when they differ.

It imports `skellycam`, so it is here and not in `tools/` (Q964).
"""

import argparse
import json
import sys
from pathlib import Path

from skellycam.api.websocket.preview_relay import pack_camera_frame
from skellycam.core.ipc.frame_ring import FrameRead, ReadResult

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "skellycam-ui" / "src" / "services" / "server" / "preview" / "tests" / "camera-messages.json"

# name, camera id, result, flags, frame number, arrival ns, rotation, JPEG (synthetic bytes, not a camera frame)
CASES = (
    ("spec-example", "a1b2", "OK", 0x30, 258, 1_000_000_007, 90, bytes.fromhex("ffd8ffd9")),
    ("flagged", "a1b2", "FLAGGED", 0x04, 7, 2_000_000_000, 0, b""),
    ("oversize", "c3c6", "OVERSIZE", 0x01, 8, 2_033_333_333, 180, b""),
    ("flags-0x30-rotation-270", "0a1b", "OK", 0x30, 9, 3_000_000_000, 270, bytes.fromhex("ffd8ffe000104a464946ffd9")),
    ("camera-id-16", "abcdefghijklmnop", "OK", 0, 10, 4_000_000_000, 0, bytes.fromhex("ffd80102ffd9")),
    ("large-values", "f976", "OK", 0, 2**53 + 1, 2**63 - 1, 0, bytes.fromhex("ffd8ffd9")),
)


def build() -> str:
    cases = []
    for name, camera_id, result, flags, frame_number, arrival_ns, rotation, jpeg in CASES:
        read = FrameRead(ReadResult[result], frame_number, arrival_ns, 0, 0, frame_number, flags, rotation,
                         len(jpeg), jpeg if jpeg else None)
        cases.append({
            "name": name,
            "input": {"camera_id": camera_id, "result": result, "flags": flags, "frame_number": str(frame_number),
                      "arrival_ns": str(arrival_ns), "rotation_cw_deg": rotation, "jpeg_hex": jpeg.hex()},
            "message_hex": pack_camera_frame(camera_id, read).hex(),
        })
    return json.dumps({"source": "skellycam/tests/preview/write_camera_message_fixture.py", "cases": cases}, indent=2) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the tracked file; write nothing")
    args = parser.parse_args(argv)
    text = build()
    if args.check:
        if not FIXTURE.exists() or FIXTURE.read_bytes() != text.encode("utf-8"):
            print(f"{FIXTURE.relative_to(ROOT).as_posix()} is not the output of this tool; run it without --check")
            return 1
        return 0
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_bytes(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
