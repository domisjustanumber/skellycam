"""T-PRV-25: the shared fixture of the camera message (specs/preview-4b.md 7.2, 7.4)."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "write_camera_message_fixture.py"
FIXTURE = ROOT / "skellycam-ui" / "src" / "services" / "server" / "preview" / "tests" / "camera-messages.json"
CASES = {"spec-example", "flagged", "oversize", "flags-0x30-rotation-270", "camera-id-16", "large-values"}


def test_t_prv_25_the_shared_fixture_is_the_output_of_the_tool():
    from skellycam.tests.preview.preview_helpers import SPEC_EXAMPLE, parse_camera_message

    before = FIXTURE.read_bytes() if FIXTURE.exists() else None
    run = subprocess.run([sys.executable, str(TOOL), "--check"], cwd=ROOT, capture_output=True, text=True)
    assert (FIXTURE.read_bytes() if FIXTURE.exists() else None) == before, "--check wrote the tracked file"
    assert run.returncode == 0, run.stdout + run.stderr

    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    assert {case["name"] for case in cases} == CASES
    for case in cases:
        given = case["input"]
        message = parse_camera_message(bytes.fromhex(case["message_hex"]))
        assert message.version == 1, case["name"]
        assert message.camera_id == given["camera_id"], case["name"]
        assert message.flags == given["flags"], case["name"]
        assert message.frame_number == int(given["frame_number"]), case["name"]
        assert message.arrival_ns == int(given["arrival_ns"]), case["name"]
        assert message.rotation_cw_deg == given["rotation_cw_deg"], case["name"]
        assert message.jpeg == bytes.fromhex(given["jpeg_hex"]), case["name"]
        assert message.jpeg_len == len(message.jpeg), case["name"]
    example = next(case for case in cases if case["name"] == "spec-example")
    assert bytes.fromhex(example["message_hex"]) == SPEC_EXAMPLE
