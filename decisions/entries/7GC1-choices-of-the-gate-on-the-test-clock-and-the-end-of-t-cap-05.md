# 7GC1 — Choices of fix lane 6: the gate on the test clock

**Status:** proposed, 2026-11-24 (agent; builds Q692 of
[ADR-B1DE](B1DE-decisions-of-the-user-on-the-share-level-and-the-test-clock.md)). The entry
[ADR-B7YV](B7YV-choices-of-fix-lane-6.md) is at its size limit, so these choices of the same lane are in this entry.

## Decision

1. **The gate on the test clock** (Q692). `VirtualClock.gate(blocked, shut)` of
   `skellycam/tests/capture/fake_source.py`: `shut` is a callable that is true while the gate of the loop stays
   shut. A participant in "gate" holds the time as in "run" while `shut()` is false, until its next probe. A `shut`
   that raises counts as an open gate. A gate with no `shut` counts as shut, as before. Each probe with a shut gate
   keeps its `shut` and tries to move the time, not only the first probe.
   `capture_session.install_gate_probe` gives `shut` as the product probe `should_grab_by_id` again, with no clock
   call. That probe only reads the shared status values of the group. The forced steps (`fallback_s` 50 ms, step
   10 ms) do not change, so a loop that does not come back does not stop the clock. Two self-tests in
   `test_helpers.py`. The 15 s ready limit of the product and the checks of T-CAP-86 do not change, and T-CAP-86
   stays blocking.

## Reason

1. Item 1: a shut gate is a real wait for another loop, but an open gate is not. The clock of the failed runs
   moved more than 99 % of the virtual time of the collection while a loop in "gate" could pass (evidence item 6).

## Evidence

Items 6 and later of [evidence/B7YV-fix-lane-6-evidence.md](../evidence/B7YV-fix-lane-6-evidence.md).

## Alternatives rejected

1. Item 1: each loop in "gate" holds the time. Two loops at a shut gate then wait for each other, and only the
   forced steps move the time.
2. Item 1: a patch of the 1 ms sleep of the loop, or a hook on the frame count of the status: each changes a
   product module or object. The gate opens by a frame count of another loop, not by a time.
3. Item 1: a longer ready limit, or fewer relay messages in T-CAP-86: Q692 keeps the limit and the checks.
