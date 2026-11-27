# P3EZ — Decision of the user on the give-wait check of the short stall test

**Status:** absorbed into
[`specs/recorder.md#121-kinds-markers-workflow-and-parity`](../../specs/recorder.md#121-kinds-markers-workflow-and-parity),
[`specs/windows-capture.md#161-kinds`](../../specs/windows-capture.md#161-kinds),
[`skellycam/tests/take_recorder/test_benchmarks.py`](../../skellycam/tests/take_recorder/test_benchmarks.py),
[`skellycam/tests/test_pace_marker.py`](../../skellycam/tests/test_pace_marker.py),
2026-11-27 (commit to dom/ci-triage; was accepted, 2026-11-27 (user, Q905)).

## Decision

The user wrote on 2026-11-27: "Q905 agree".

1. **Q905.** In the short CI form of T-REC-STALL (`test_t_rec_stall_short_pass_parts`), the check "no `give`
   wait" of the stall of 0.5 s (scaled by 10) moves to a `pace` test, by the rule of Q619:
   `test_t_rec_stall_short_has_no_give_wait`. The other three checks stay blocking: no lost frame, equal rows and
   finished files. `recorder.md` 12.1 states it; the list test of the marker (`test_pace_marker.py`) names both
   halves.

## Reason

The words of the user, above. CI run 45912461163 (windows-2025) failed the check with `waits [5, 5]`: the writers
of both cameras waited, also the camera with no stall, so the cause was the runner. The test passed in 58 runs on
the development machine at 8c95e992b and at 292529fa9, 12 of them on 2 cores with two busy loops.
