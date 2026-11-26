# ZT5F — The user accepts the choices of fix lane 8 and its merge

**Status:** done, 2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-25 (user; the supervisor asked the four questions and the coordinator relayed the
answer; commit to dom/fix-lane-8)).

## Decision

The user decided these items on 2026-11-25. The words of the user: "yes to all". The questions, as the supervisor
asked them:

1. "Do you accept the leak-fix choices (ADR-4CAF), including the private queue names and dropping the 100 ms wait?"
   Yes. [ADR-4CAF](4CAF-choices-of-the-close-of-the-queues-of-a-group.md) is accepted.
2. "Do you accept the gate-probe choice (ADR-JC4X)?" Yes.
   [ADR-JC4X](JC4X-choices-of-the-gate-probe-of-a-second-app-on-the-test-clock.md) is accepted.
3. "Should the `test_status_locks` test move to `pace`, or stay as it is?" Not decided: the question gives two
   options, and the answer "yes" chooses neither. The test does not change. The question stays in
   [open-work.md](../open-work.md).
4. "Should I merge lane 8 into `dom/integration`, and push? `dom/integration` is still unpushed, so CI has seen
   neither lane." Yes: the supervisor merges lane 8 into `dom/integration` and pushes it.

## Reason

1. Items 1 and 2 rest on the evidence of the two entries
   ([evidence/4CAF-fix-lane-8-evidence.md](../evidence/4CAF-fix-lane-8-evidence.md)).
2. Item 3: an agent does not choose one of two options for the user.

## Open work

[open-work.md](../open-work.md)
