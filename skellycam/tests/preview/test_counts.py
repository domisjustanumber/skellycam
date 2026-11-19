"""State and counts for the UI: T-PRV-22 and T-PRV-24 (specs/preview.md, sections 5.2 and 6).

Fake tests.
"""

import asyncio
import json
import subprocess
import sys

import pytest

from skellycam.tests.preview.preview_helpers import (
    CAMERA_INDEX_BASE, OVERSIZE_PAYLOAD_SIZE, PERIOD_NS, FakeConnection, FakeRing, PacedWriter, framerate_tracker,
    manager_with, running_relay)

CAM1, CAM2 = "a1b2", "c3d4"
OVERSIZE_FRAMES = (3, 4, 5)
SKIPPED_FRAME = 10
DURATION_MAXLEN = 1000  # the duration deque of ServerFramerateCalculator (ADR-24FZ)


def script_ring_1(k):
    """`source_frame_number` in steps of 2, three oversize frames and one skipped write."""
    kwargs = {"source_frame_number": 2 * k}
    if k in OVERSIZE_FRAMES:
        kwargs["payload"] = b"\0" * OVERSIZE_PAYLOAD_SIZE
    if k == SKIPPED_FRAME:
        kwargs["newer_frame_waiting"] = True
    return kwargs


def expected_not_shown(connection, update_index, fake_ring):
    """(last sent - first sent + 1) - the frames sent - the skipped writes between the first and the last
    sent frame, over the camera messages before the event `update_index`."""
    frames = [m.frame_number for _, kind, m in connection.events[:update_index]
              if kind == "camera" and m.camera_id == fake_ring.camera_id]
    if not frames:
        return 0
    first, last = frames[0], frames[-1]
    skipped = len([k for k in fake_ring.skipped if first < k < last])
    return (last - first + 1) - len(frames) - skipped


@pytest.mark.parametrize("answers", [True, False], ids=["client answers", "client never answers"])
async def test_t_prv_22_framerate_update(cleanup, writers, answers):
    """T-PRV-22, sections 6.1 to 6.3 [A3, A7, A8, agent 19, agent 20]. Ring 1: `arrival_ns` in steps of
    33,333,333 ns and `source_frame_number` in steps of 2; three frames flagged `OVERSIZE`; one write
    skipped with `newer_frame_waiting=True`. Ring 2: `arrival_ns` in steps of 33,333,333 ns and
    `source_frame_number` -1. Two runs of 1.1 s: the fake client answers at once; the fake client never
    answers.

    3 or more `framerate_update` messages for the group in each run;
    `delivered_framerate.mean_frames_per_second` is 60.0 ± 0.5 for ring 1 and 30.0 ± 0.5 for ring 2, in
    both runs; `oversize_count` is 3; `ring_skipped_count` is 1 [A8]; for ring 1, `not_shown_count`
    equals (last sent − first sent + 1) − the frames sent − the skipped writes between the first and
    the last sent frame; no `backend_framerate` key.

    `delivered_framerate` can be `null` while the calculator has fewer than 2 durations (6.2): each
    value that is not `null` must be in range, and the last message must have one. The counts are
    those of the last message. Section 6.2 also drops `frontend_framerate`."""
    ring_1 = FakeRing(cleanup, CAM1, CAMERA_INDEX_BASE, tag=1, period_ns=PERIOD_NS)
    ring_2 = FakeRing(cleanup, CAM2, CAMERA_INDEX_BASE + 1, tag=2, period_ns=PERIOD_NS)
    connection = FakeConnection(answer=True if answers else frozenset())
    async with running_relay(manager_with({CAM1: ring_1.reader(), CAM2: ring_2.reader()}), connection):
        writers.append(PacedWriter(ring_1, script=script_ring_1).start_task())
        writers.append(PacedWriter(ring_2, script=lambda k: {"source_frame_number": -1}).start_task())
        await asyncio.sleep(1.1)
        for writer in writers:
            writer.stop()
    updates = [(i, m) for i, (_, kind, m) in enumerate(connection.events)
               if kind == "json" and m.get("message_type") == "framerate_update" and m.get("camera_group_id") == "g1"]
    assert len(updates) >= 3, f"{len(updates)} framerate_update messages in 1.1 s"
    for _, update in updates:
        assert "backend_framerate" not in update and "frontend_framerate" not in update
    for cid, rate in ((CAM1, 60.0), (CAM2, 30.0)):
        values = [u["cameras"][cid]["delivered_framerate"] for _, u in updates if cid in u.get("cameras", {})]
        assert values and values[-1] is not None, f"camera {cid}: no frame rate in the last message"
        for value in values:
            if value is not None:
                assert value["mean_frames_per_second"] == pytest.approx(rate, abs=0.5), (cid, value)
    last_index, last = updates[-1]
    assert last["cameras"][CAM1]["oversize_count"] == 3
    assert last["cameras"][CAM1]["ring_skipped_count"] == 1
    assert (last["cameras"][CAM2]["oversize_count"], last["cameras"][CAM2]["ring_skipped_count"]) == (0, 0)
    assert last["cameras"][CAM1]["not_shown_count"] == expected_not_shown(connection, last_index, ring_1)


JUMP_CHILD = """
import json, time
from skellycam.core.recorders.framerate_tracker import ServerFramerateCalculator
calc = ServerFramerateCalculator(source_name="test")
calc.update(0, 1_000_000_000)
start = time.perf_counter()
calc.update(10 ** 9, 1_000_000_000 + 10 ** 9 * 33_333_333)
elapsed = time.perf_counter() - start
framerate = calc.current_framerate
print(json.dumps({"elapsed_s": elapsed, "window": framerate.calculation_window_size,
                  "fps": framerate.mean_frames_per_second}))
"""


@pytest.mark.parametrize("case", ["clear", "jump", "reader counts"])
def test_t_prv_24_calculator_and_reader_counts(cleanup, case):
    """T-PRV-24, sections 5.2 and 6.3 [A5, A8, agent 19]: `ServerFramerateCalculator`: update, `clear()`,
    update; also one update with a jump of 10^9 frames. `oversize_count` of a ring after two oversize
    frames; `skipped_count` of a ring after three writes with `newer_frame_waiting=True`.

    After `clear()`, one update gives one exact interval; the jump returns at once and keeps at most
    `maxlen` durations; `oversize_count` is 2; `skipped_count` is 3.

    The jump runs in a child process with a time limit, so that an unbounded loop cannot hang the test
    run. The two properties are read-only (5.2)."""
    if case == "clear":
        calc = framerate_tracker().ServerFramerateCalculator(source_name="test")
        for k in range(5):
            calc.update(k, 1_000_000_000 + k * 20_000_000)
        calc.clear()
        assert calc.current_framerate is None
        calc.update(7, 1_000_000_000 + 4 * 20_000_000 + 3 * PERIOD_NS)
        framerate = calc.current_framerate
        assert framerate is not None, "clear() did not keep the last observation"
        assert framerate.calculation_window_size == 3
        assert framerate.mean_frame_duration_ms == pytest.approx(PERIOD_NS / 1e6, rel=1e-9)
    elif case == "jump":
        framerate_tracker().ServerFramerateCalculator  # noqa: B018 - the name must exist in this module
        try:
            child = subprocess.run([sys.executable, "-c", JUMP_CHILD], capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            pytest.fail("update() with a jump of 10^9 frames did not return within 30 s")
        assert child.returncode == 0, child.stderr[-2000:]
        result = json.loads(child.stdout.strip().splitlines()[-1])
        assert result["elapsed_s"] < 1.0, result
        assert 2 <= result["window"] <= DURATION_MAXLEN, result
        assert result["fps"] == pytest.approx(30.0, rel=1e-6)
    else:
        fake_ring = FakeRing(cleanup, CAM1)
        reader = fake_ring.reader()
        fake_ring.write(0, payload=b"\0" * OVERSIZE_PAYLOAD_SIZE)
        fake_ring.write(1)
        fake_ring.write(2, payload=b"\0" * OVERSIZE_PAYLOAD_SIZE)
        for k in (3, 4, 5):
            fake_ring.write(k, newer_frame_waiting=True)
        assert reader.oversize_count == 2
        assert reader.skipped_count == 3
        with pytest.raises(AttributeError):
            reader.oversize_count = 0
        with pytest.raises(AttributeError):
            reader.skipped_count = 0
