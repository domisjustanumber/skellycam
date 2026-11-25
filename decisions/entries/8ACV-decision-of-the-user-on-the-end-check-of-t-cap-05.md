# 8ACV — Decision of the user on the end check of T-CAP-05 (Q696)

**Status:** accepted, 2026-11-24 (user; the coordinator asked the question and relayed the answer).

## Decision

The user decided this item on 2026-11-24. The words of the user: "Q696 yes".

1. **Q696.** "Change its end check from 'equal ring frame counts' to 'ring counts differ by at most one, and the
   last frames of all cameras arrive within 1 ms of each other'? The check of the replaced-frame count stays as
   it is. Then the clock fix and this change land together, with an independent review." Yes.

The choices of the agent that build this item are in
[ADR-7GC1](7GC1-choices-of-the-gate-on-the-test-clock-and-the-end-of-t-cap-05.md) (proposed).

## Reason

1. The context of the question: with the clock fix of Q692
   ([ADR-B1DE](B1DE-decisions-of-the-user-on-the-share-level-and-the-test-clock.md)), T-CAP-05 failed at each run:
   "ring frame counts differ: {'e605': 1109, '17ae': 1109, '4a36': 1110}"
   ([evidence item 6](../evidence/B7YV-fix-lane-6-evidence.md)).
