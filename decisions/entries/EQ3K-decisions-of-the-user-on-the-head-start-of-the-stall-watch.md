# EQ3K — Decisions of the user on the head start of the stall watch and its reason text (Q874, Q875)

**Status:** absorbed into [`specs/unix-capture.md#410-main-process-stall-watch-u`](../../specs/unix-capture.md#410-main-process-stall-watch-u),
[`specs/unix-capture.md#65-shared-and-windows-tests-step-7s`](../../specs/unix-capture.md#65-shared-and-windows-tests-step-7s),
[`specs/windows-capture.md#95-stall-watch`](../../specs/windows-capture.md#95-stall-watch),
[`skellycam/tests/capture/test_stall_watch.py`](../../skellycam/tests/capture/test_stall_watch.py),
2026-11-26 (commit to dom/answers-q842; was accepted, 2026-11-26 (user; the coordinator asked the questions and relayed the answers; commit to
dom/answers-q842)).

## Decision

The user answered on 2026-11-26: "agree to all Q864-Q881". This entry records the two answers of the stall watch.
The other answers are recorded on their own branches.

1. **Q874 (a).** The head start of 0.5 s is accepted as built: the main-process watch trips after 2.5 s with no
   loop pass; the in-process rule `no frame for 2 s` of [`windows-capture.md`](../../specs/windows-capture.md) 9.5
   does not change and decides when frames stop. This accepts items 3, 4 and 9 of
   [ADR-4PPS](4PPS-choices-of-the-answers-lane-of-q842-to-q856.md), which move here as items 3 to 5 below.
2. **Q875.** The trip reason text "no loop pass for 2.5 s" stays. The stable key is the code `stalled`.
3. **The test bounds of the watch** (`unix-capture.md` 4.10 and T-UNX-75). A suspended camera ends 2.5 to
   3.0 s after its last loop pass, and the third camera has no gap longer than 3.0 s: the trip (2.5 s) plus the
   margin of 0.5 s of the old test. The fake-clock test of the limit (`test_f2_the_watch_trips_after_the_head_start`)
   trips nothing at 2.0 s, the deadline of the in-process rule, nor at 2.4 s, and trips at 2.5 s. A second
   fake-clock test (`test_f2_the_in_process_rule_decides_in_the_head_start`) sets `dead` with the in-process
   failure at 2.05 s, after a round of the watch just past 2.0 s: the watch then never trips and never ends the process. The trip reason is
   "no loop pass for 2.5 s".
4. **The order of the two stall rules** (Q863, `unix-capture.md` 4.10, `windows-capture.md` 9.5). The rule of the user is
   "the watch counts from the later of the last loop pass and the last frame arrival". In the code the last loop
   pass is never earlier than the last arrival (the counter goes up at the start of each pass, after the arrival
   and the waits of the pass before), so that rule alone gives the same instant as the in-process rule, and the
   race stays. Thus the watch also gives the in-process rule a stated head start of 0.5 s: it trips after 2.5 s
   with no loop pass (`STALL_HEAD_START_S` beside `STALL_WATCH_S` in `camera_group.py`). In the head start the
   camera process wakes, puts one setup failure, writes `info` and sets `dead`; this takes ms. No status field is
   added, and no clock of the camera process is read by the main process. A hung loop is `stalled` at most 2.6 s
   after its last pass (0.1 s round, then 2.5 s), and its process ends at most 1 s later. The cost when the watch
   trips, from the code: both rules give `dead` `stalled`, and neither restores (`stalled` is in `WEDGE_CODES`); on
   Windows `terminate` ends the process at once, so the camera does not finish its take files (the take level
   completes them, `recorder.md` 7.4) and its close diagnostics are lost; on POSIX the SIGTERM handler only sets the
   stop flag, and the `kill` after 1 s cuts off only an end that takes longer. Rejected: a published last arrival
   time that the watch compares with its own clock (a new shared field, a clock read across processes, and the
   virtual clock of the tests differs from the clock of the watch); a head start of 1 s (the 3 s of option (c),
   which the user did not choose).
5. **The lock waits against the watch** (checked again for Q863). A first lock wait of a frame decision
   (`FRAME_READ_WAIT_S` 1.5 s) and a first status-array lock wait (`ARRAY_LOCK_WAIT_S` 0.5 s) in one pass give
   2.0 s with no loop pass. That is not longer than the limit of 2 s of 4.10, and the watch trips only at 2.5 s, so
   they trip nothing. The open-work item goes.

## Reason

The user gave no reason other than the answers. The agent gave these with the items:

- Item 3: The bounds keep the margin of 0.5 s of the old test.
- Item 4: Q863 asks for an order that is certain. A head start makes the in-process rule decide whenever its camera
   process can run for 0.5 s; a process that cannot is hung for the watch too. It is one constant, with no new
   shared state.
- Item 5: The open-work item assumed a trip at 2 s.

## Open work

[open-work.md](../open-work.md)
