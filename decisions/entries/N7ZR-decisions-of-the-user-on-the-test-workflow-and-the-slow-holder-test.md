# N7ZR — Decisions of the user on the test workflow and the slow-holder test

**Status:** absorbed into
[`specs/windows-capture.md#161-kinds`](../../specs/windows-capture.md#161-kinds),
[`skellycam/tests/capture/test_status_locks.py`](../../skellycam/tests/capture/test_status_locks.py),
[`skellycam/tests/test_pace_marker.py`](../../skellycam/tests/test_pace_marker.py),
2026-11-27 (commit to dom/ci-triage; was accepted, 2026-11-27 (user, Q917 (a) and (b))).

## Decision

The user wrote on 2026-11-27: "agree to all" (Q910 to Q921). These are Q917 (a) and (b).

1. **Q917 (a).** [ADR-QF7V](QF7V-choices-of-the-test-workflow-on-dom-integration.md) is accepted: how `test.yml`
   runs on a push to `dom/integration`.
2. **Q917 (b).** In `test_status_locks.py::test_a_live_but_slow_holder_and_torn_json_never_raise`, the checks that
   depend on the pace move to the `pace` test `test_a_live_but_slow_holder_waits_once_and_logs_one_line`, by the rule
   of Q619 and as Q905: the first read waits 0.5 s, the second read of the stretch does not wait, the status is in
   the stretch after the second read, more than 100 reads in 3 s, one error line. These need the main process to read
   within the hold of 1.5 s of the child. The blocking test keeps: the status never marks the live holder dead, no
   torn JSON escapes a read, and the lock comes again at the end. Both halves check one run (`one_run`).

## Reason

The words of the user, above. The test failed 1 of 20 on 2 cores in WSL ([ADR-4CAF](4CAF-choices-of-the-close-of-the-queues-of-a-group.md)
evidence item 13) and on macOS arm64 with two error lines (CI run 45925313532, the blocking step "Run the real-time
gap tests", variant "writes with the lock").
