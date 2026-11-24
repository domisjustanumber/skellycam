# 2AQT — Decision of the user on the gap limit of the stall test with PROCESS workers (Q721)

**Status:** accepted, 2026-11-24 (user; the coordinator asked the question and relayed the answer).

## Decision

The user decided this item on 2026-11-24. The words of the user: "Q720, Q721 yes, push". This entry records
Q721.

1. **Q721.** "Move its 1 s gap limit to a pace test too, as Q672 did for thread workers? The blocking half keeps:
   no healthy camera is ended, both stay ready, and the loops keep passing." Yes.

The choices of the agent that build this item are in item 3 of
[ADR-7GC1](7GC1-choices-of-the-gate-on-the-test-clock-and-the-end-of-t-cap-05.md) (proposed).

## Reason

1. On CI (Linux, run 45493213866), `skellycam/tests/capture/test_stall_watch.py::test_the_watch_ends_no_healthy_camera_under_load[process]`
   failed with "AssertionError: {'e605': 1.067, '17ae': 1.049}" against the 1 s limit.
