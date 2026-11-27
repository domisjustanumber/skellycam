# GV50 — Choices of the split of the slow-holder test

**Status:** absorbed into
[`specs/windows-capture.md#161-kinds`](../../specs/windows-capture.md#161-kinds),
[`skellycam/tests/capture/test_status_locks.py`](../../skellycam/tests/capture/test_status_locks.py),
2026-11-27 (commit to dom/ci-triage; was accepted, 2026-11-27 (user, [ADR-D2YZ](D2YZ-decisions-of-the-user-on-t-rec-36-t-prv-17-and-the-slow-holder-reading.md) item 3); was proposed,
2026-11-27 (agent; the CI triage lane reads Q917 (b) of
[ADR-N7ZR](N7ZR-decisions-of-the-user-on-the-test-workflow-and-the-slow-holder-test.md))).

## Decision

The lane reads "its timing-dependent check" of Q917 (b) as these checks. Both halves check one run (`one_run`).

1. **The `pace` half** (`test_a_live_but_slow_holder_waits_once_and_logs_one_line`): the first read waits about
   0.5 s; the second read of the stretch does not wait (under 0.2 s); the status is in the stretch after the second
   read; more than 100 reads in 3 s; exactly one error line.
2. **The blocking half** (`test_a_live_but_slow_holder_and_torn_json_never_raise`): the live holder is never marked
   dead (in the stretch and at the end); no torn JSON escapes 3 s of reads; the lock comes again at the end.
3. **The blocking half proves that it exercised a stretch:** a probe with no wait shows that the child holds the lock
   at the first read, and at least one error line shows that a stretch with no lock began. Else the blocking checks
   could pass with no stretch at all (a finding of the review of the lane).

## Reason

Each check of item 1 needs the main process to read within the hold of 1.5 s of the child: the failure on 2 cores in
WSL ("info" not in `no_lock` after the second read) and on macOS arm64 (two error lines) were of this kind. The checks
of items 2 and 3 do not depend on the pace once the first read comes within the hold.

## Open work

[open-work.md](../open-work.md)
