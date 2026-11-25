# 2SX2 — The user accepts the choices of fix lane 7, the fix of the pubsub leak and a look at the T-UNX-98 thread

**Status:** accepted, 2026-11-25 (user; the supervisor asked the four questions and the coordinator relayed the
answer; commit to dom/fix-lane-7).

## Decision

The user decided these items on 2026-11-25. The words of the user: "yes to all". The questions, as the supervisor
asked them:

1. "Do you accept the R394 choices (the macOS condition and the two clock rules)? The new clock rule changes a lane 6
   choice that is still only proposed (B7YV item 8)." Yes. [ADR-R394](R394-choices-of-fix-lane-7.md) is accepted
   (items 1 and 3; item 2 is a finding). The second clock rule of item 3 (no forced step while an expected thread is
   not started) replaces the words "until then only forced steps move the time" of item 8 of
   [ADR-B7YV](B7YV-choices-of-fix-lane-6.md) (proposed). The other parts of B7YV item 8 stay proposed.
2. "Do you approve fixing the pubsub leak in product code, with a spec item and a test first?" Yes. The leak is item 2
   of ADR-R394. The work starts with a spec item and a test. The design of item 4 of ADR-R394 is the start of that
   work; the spec item decides it.
3. "Should someone look into the T-UNX-98 stuck thread?" Yes: an agent finds why
   `test_t_unx_98_two_cameras_of_one_model_keep_their_own_entries[other usb ids]` sometimes leaves a camera loop
   thread that does not end (evidence item 5 of ADR-R394).
4. "Should I commit lane 7 and merge it into dom/integration?" Yes.

## Reason

1. The choices of ADR-R394 rest on its evidence: the macOS jobs found no runner, and the two clock rules fix the
   cause of the failure of T-CAP-91 on CI.
2. The leak grows with each camera group, also in a long run of the server.
3. The stuck thread holds the end of the pytest process, so a CI job does not end before its time limit.

## Open work

[open-work.md](../open-work.md)
