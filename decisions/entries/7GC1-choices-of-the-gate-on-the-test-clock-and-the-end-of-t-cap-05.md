# 7GC1 — Choices of fix lane 6: the gate on the test clock and the end check of T-CAP-05

**Status:** proposed, 2026-11-24 (agent; builds Q692 of
[ADR-B1DE](B1DE-decisions-of-the-user-on-the-share-level-and-the-test-clock.md) and Q696 of
[ADR-8ACV](8ACV-decision-of-the-user-on-the-end-check-of-t-cap-05.md)). The entry
[ADR-B7YV](B7YV-choices-of-fix-lane-6.md) is at its size limit, so these choices of the same lane are in this entry.

## Decision

1. **The gate on the test clock** (Q692). `VirtualClock.gate(blocked, shut)` of
   `skellycam/tests/capture/fake_source.py`: `shut` is a callable that is true while the gate of the loop stays
   shut. A participant in "gate" holds the time as in "run" while `shut()` is false, until its next probe. A `shut`
   that raises counts as an open gate. A gate with no `shut` counts as shut, as before. Each probe with a shut gate
   keeps its `shut` and tries to move the time, not only the first probe.
   `capture_session.install_gate_probe` gives `shut` as the product probe `should_grab_by_id` again, with no clock
   call. `shut` runs under the lock of the clock, so it must not block, take a lock or call the clock. That probe
   only reads the shared status values of the group, and they have no lock (`lock=False`). The forced steps (`fallback_s` 50 ms, step
   10 ms) do not change, so a loop that does not come back does not stop the clock. Two self-tests in
   `test_helpers.py`. The 15 s ready limit of the product and the checks of T-CAP-86 do not change, and T-CAP-86
   stays blocking.
2. **The end check of T-CAP-05** (Q696). The last frame of a ring is the JPEG ring write of that camera with the
   largest `arrival_ns` (the spy of `FrameRingWriter.write` in `Spies`). The check: the largest ring frame count
   minus the smallest is 1 or less, and the largest last-frame `arrival_ns` minus the smallest is less than
   1,000,000 ns. The check of the last frames that the fakes deliver (`FakeLog.frames`) stays before it, as a check
   of the script. The check of at least 600 ring frames, the replaced-count check and the check of 200 or more
   replaced frames of the fast camera do not change.
3. **The stall test with PROCESS workers** (Q721 of
   [ADR-2AQT](2AQT-decision-of-the-user-on-the-gap-of-the-stall-test-with-process-workers.md)). The `pace` test
   `test_the_loop_passes_have_no_pause_above_1_s_under_load` takes the parameter `workers` ("thread", "process"). It
   uses the same run as the blocking test (`one_run`) and the same bound for each kind: `bound(1 / 30, 1.0)`. The
   blocking test keeps the same three checks for each kind. The test names do not change.

## Reason

1. Item 1: a shut gate is a real wait for another loop, but an open gate is not. The clock of the failed runs
   moved more than 99 % of the virtual time of the collection while a loop in "gate" could pass (evidence item 6).
2. Item 2: Q696 asks for the last frames of all cameras. The rings hold the frames that the product took, so their
   last frames show that the gate ended on one round. The last frames of the fakes show only the script.

## Evidence

Items 6 and later of [evidence/B7YV-fix-lane-6-evidence.md](../evidence/B7YV-fix-lane-6-evidence.md).

## Alternatives rejected

1. Item 1: each loop in "gate" holds the time. Two loops at a shut gate then wait for each other, and only the
   forced steps move the time.
2. Item 1: a patch of the 1 ms sleep of the loop, or a hook on the frame count of the status: each changes a
   product module or object. The gate opens by a frame count of another loop, not by a time.
3. Item 1: a longer ready limit, or fewer relay messages in T-CAP-86: Q692 keeps the limit and the checks.
4. Item 2: the last frames of the fakes in place of the last ring frames: they do not change when the gate takes
   a wrong last frame.
