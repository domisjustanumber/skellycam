# 3RJJ — Decision of the user on the order of the two stall rules (Q863)

**Status:** absorbed into [`specs/unix-capture.md#410-main-process-stall-watch-u`](../../specs/unix-capture.md#410-main-process-stall-watch-u),
[`specs/windows-capture.md#95-stall-watch`](../../specs/windows-capture.md#95-stall-watch),
[`skellycam/tests/capture/test_stall_watch.py`](../../skellycam/tests/capture/test_stall_watch.py),
2026-11-26 (commit to dom/answers-q842; was accepted, 2026-11-26 (user; the coordinator asked the question and relayed the answer; commit to
dom/answers-q842)).

## Decision

The user answered Q863 on 2026-11-26. The words of the user: "(b)". The question: "What to do about F6 at 2 s:
(a) F6 accepts either reason text; (b) keep F6 strict and change the code so the order is fixed: the main-process
watch counts from the later of the last loop pass and the last frame arrival, spec and test first; (c) go back to
3 s."

1. **Q863 (b).** The limit of 2 s of Q850 stays. The test F6 stays strict: when frames stop, the in-process rule
   of [`windows-capture.md`](../../specs/windows-capture.md) 9.5 (`no frame for 2 s`) ends the camera, never the
   main-process watch of [`unix-capture.md`](../../specs/unix-capture.md) 4.10. The code makes this order
   certain: the watch counts from the later of the last loop pass and the last frame arrival. The spec and the
   tests change first, then the code.

The details that build this item are item 4 of
[ADR-4PPS](4PPS-choices-of-the-answers-lane-of-q842-to-q856.md) (proposed).

## Reason

The user gave no reason other than the answer. The agent gave this with the question: with both limits at 2 s, F6
had a margin of tens of ms, and a race that the watch wins once turns a blocking CI job red.

## Open work

[open-work.md](../open-work.md)
