# N2VE — Decisions of the user on the CI triage, Q882 to Q884

**Status:** absorbed into
[`specs/certify.md#44-native-jpeg-u-a`](../../specs/certify.md#44-native-jpeg-u-a),
[`specs/windows-capture.md#161-kinds`](../../specs/windows-capture.md#161-kinds),
[`skellycam/tests/certify/test_certify_report_shape.py`](../../skellycam/tests/certify/test_certify_report_shape.py),
2026-11-26 (commit to dom/ci-triage; was accepted, 2026-11-26 (user, Q882 to Q884)).

## Decision

The user wrote on 2026-11-26: "agree to all Q882-Q887". These are Q882 to Q884, the questions of the CI triage
lane ([ADR-2HW5](2HW5-choices-of-the-ci-triage-of-the-first-test-run-on-dom-integration.md)).

1. **Q882.** Accept the fix of the race of the certify ring watch. After the wait of the open step and before the
   judge of the open, certify attaches a ring watch to each camera whose ring exists and that has none. A camera
   that is `ready` goes on to the next steps also with no ring watch; then `native-jpeg:source-equals-ring` is
   `not-run` with `ring-lapped`. The sentence is in `certify.md` 4.4; T-CERT-151 tests it.
2. **Q883.** Accept the test choices of the lane: ring readers in tests hold the virtual clock while they are
   behind, with T-CERT-151 as the guard of the race that one hold hides; T-REC-41 waits for 60 decoded frames;
   T-RING-38 waits for `ready` or `dead`.
3. **Q884.** The tests with the markers `ring_slow` and `capture_timing` stay in the blocking step of CI. Only
   `pace` is not blocking.

## Reason

The words of the user, above. The lane gave each recommendation with its evidence in ADR-2HW5.
