# N2VE — Decisions of the user on the CI triage (Q882 to Q884) and the stall watch code (Q890 to Q892)

**Status:** absorbed into
[`specs/certify.md#44-native-jpeg-u-a`](../../specs/certify.md#44-native-jpeg-u-a),
[`specs/windows-capture.md#161-kinds`](../../specs/windows-capture.md#161-kinds),
[`specs/unix-capture.md#410-main-process-stall-watch-u`](../../specs/unix-capture.md#410-main-process-stall-watch-u),
[`skellycam/tests/certify/test_certify_report_shape.py`](../../skellycam/tests/certify/test_certify_report_shape.py),
2026-11-26 (commit to dom/ci-triage; was accepted, 2026-11-26 (user, Q882 to Q884, Q890 to Q892)).

## Decision

The user wrote on 2026-11-26: "agree to all Q882-Q887" and "agree to all Q890-Q892". Q882 to Q884 are the
questions of the CI triage lane ([ADR-2HW5](2HW5-choices-of-the-ci-triage-of-the-first-test-run-on-dom-integration.md)).
Q890 to Q892 are on the code of the answers lane
([ADR-4PPS](4PPS-choices-of-the-answers-lane-of-q842-to-q856.md)).

1. **Q882.** Accept the fix of the race of the certify ring watch. After the wait of the open step and before the
   judge of the open, certify attaches a ring watch to each camera whose ring exists and that has none. A camera
   that is `ready` goes on to the next steps also with no ring watch; then `native-jpeg:source-equals-ring` is
   `not-run` with `ring-lapped`. The sentence is in `certify.md` 4.4; T-CERT-151 tests it.
2. **Q883.** Accept the test choices of the lane: ring readers in tests hold the virtual clock while they are
   behind, with T-CERT-151 as the guard of the race that one hold hides; T-REC-41 waits for 60 decoded frames;
   T-RING-38 waits for `ready` or `dead`.
3. **Q884.** The tests with the markers `ring_slow` and `capture_timing` stay in the blocking step of CI. Only
   `pace` is not blocking.
4. **Q890.** Push `dom/integration` (8c95e992b) to the fork, with no PR. The push is done; this item records it.
5. **Q891.** Items 10 to 12 of ADR-4PPS are accepted (`unix-capture.md` 4.10):
   - The count at the attach: `_wait_pass` sets `last_arrival` at the attach of the rings, and the loop adds one to
     `alive_count` just after it, so the count comes after the start of the in-process clock (also on the open of
     a reopen).
   - The order in `_fail`: the failure goes into `info` first, then on the queue of the setup failures, then the
     state. The rule of section 12 (the failure object before the state) holds.
   - The longest pass with no count: a pass in a take can hold the first frame-decision wait (1.5 s), the read and
     the first attempt of `give` (0.5 s), about 2.03 s at 30 fps, below the trip of 2.5 s. This corrects item 5 of
     [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md).
6. **Q892.** A later small test lane writes the full stall-watch test: a real camera loop, a fake camera whose
   frames stop after a reopen, and the watch on the same clock. Low priority (open work).

## Reason

The words of the user, above. The lanes gave each recommendation with its evidence in ADR-2HW5 and ADR-4PPS.

## Open work

[open-work.md](../open-work.md)
