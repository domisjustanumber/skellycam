# D2YZ — Decisions of the user on T-REC-36, T-PRV-17 and the slow-holder reading

**Status:** absorbed into
[`specs/recorder.md#122-test-list`](../../specs/recorder.md#122-test-list),
[`specs/preview.md#91-kinds-and-helpers`](../../specs/preview.md#91-kinds-and-helpers),
[`specs/preview.md#92-test-list`](../../specs/preview.md#92-test-list),
[`specs/windows-capture.md#161-kinds`](../../specs/windows-capture.md#161-kinds),
[`skellycam/tests/take_recorder/test_queue_and_writer.py`](../../skellycam/tests/take_recorder/test_queue_and_writer.py),
[`skellycam/tests/preview/test_ws_flow.py`](../../skellycam/tests/preview/test_ws_flow.py),
[`skellycam/tests/test_pace_marker.py`](../../skellycam/tests/test_pace_marker.py),
2026-11-27 (commit to dom/ci-triage; was accepted, 2026-11-27 (user, Q922, Q923 and ADR-GV50)).

## Decision

The user wrote on 2026-11-27: "yes to all".

1. **Q922.** The check "no `give` wait" of T-REC-36 moves to a `pace` test (`test_t_rec_36_has_no_give_wait`), as
   Q905. No lost frame and the row and block counts stay blocking
   (`test_t_rec_36_1080p60_frames_of_600_kb_for_30_s`). The CI lane also tries the runner's D: drive for the temp
   folder of the Windows recorder job (open work).
2. **Q923.** The count of T-PRV-17, "15 messages of B within 1 s after A's reader is removed", moves to a `pace`
   test (`test_t_prv_17_b_gets_15_messages_within_1_s`), as T-PRV-16 (Q669). The rest stays blocking: no message
   for the removed camera, no warning, the relay still running. The `pace` half counts the frames of B written after
   the removal. T-PRV-17 is in the list of `preview.md` 9.1. What the blocking half asserts about B is a choice of
   the lane ([ADR-SKZ8](SKZ8-choices-of-the-blocking-half-of-t-prv-17.md), proposed).
3. **ADR-GV50** is accepted: the reading of the lane of Q917 (b).

## Reason

The words of the user, above. The failures: T-REC-36 on windows-2025 (CI run 45924771549, 76 waits, no lost frame);
T-PRV-17 on macOS arm64 (CI run 45925313532, 10 of 15 in 1 s, every other check passed).
