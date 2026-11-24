# B1DE — Decisions of the user on the share level on CI and the test clock of T-CAP-86 (Q690, Q692)

**Status:** accepted, 2026-11-24 (user; the coordinator asked the questions and relayed the answers).

## Decision

The user decided these items on 2026-11-24. The words of the user: "Q690-Q692 yes". This entry records Q690 and
Q692.

1. **Q690.** "Make the CI level for a share of frames a fixed 40 %, not a value that follows the margin
   setting?" Yes. [`preview.md`](../../specs/preview.md) 9.1 states it.
2. **Q692.** "Have an agent propose a fix of the test clock for T-CAP-86, proved by 2-core runs, and leave the
   test blocking meanwhile?" Yes.

The choices of the agent that build these items are in [ADR-B7YV](B7YV-choices-of-fix-lane-6.md) (proposed) and,
for Q692, in [ADR-7GC1](7GC1-choices-of-the-gate-on-the-test-clock-and-the-end-of-t-cap-05.md) (proposed).

## Reason

1. Before Q690, the level of a share of frames was `bound(1.0, 0.8)` of `skellycam/tests/pace.py`. That gives
   40 % only when `SKELLYCAM_PACE_MARGIN` is 3. At a margin of 5 or more, the level is 0 or less, and the share
   check always passes.
2. Q692: T-CAP-86 failed on 2 cores in WSL with a cause in the test clock, not in the product
   ([ADR-B7YV](B7YV-choices-of-fix-lane-6.md) evidence item 3).
