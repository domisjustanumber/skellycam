# Q2NY — Choices of code step 2 (the shared parts of the capture specs)

**Status:** proposed, 2026-11-20 (supervisor and agent).

## Decision

Code step 2 builds the shared parts of [`unix-capture.md`](../../specs/unix-capture.md) 4.2. The specs
state each choice below.

Choices of the supervisor (review of the step):

1. The main-process stall watch (4.10) trips after 3 s, not 2 s: the in-process rule of
   [`windows-capture.md`](../../specs/windows-capture.md) 9.5 (2 s) must come first, because it finishes
   the files and closes the camera, and the watch kills the process. The user decided against this item on
   2026-11-26: the watch trips after 2 s, item 14 of
   [ADR-22EJ](22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md) (Q850 of
   [ADR-88HQ](88HQ-decisions-of-the-user-on-q842-to-q856.md)). With the head start of 0.5 s for the in-process
   rule, the watch trips after 2.5 s with no loop pass (Q874 of
   [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md)). The other items stay proposed.
2. The watch is off while `should_pause` is set (the record start opens the files on the loop thread).
   `SKELLYCAM_STALL_WATCH=0` turns it off; the group reads it when it is made, and logs it at its start.
3. A pull source whose read or control call blocks longer than the limit ends the camera, by design.
4. The OpenCV source has no restore of the controls at the close: it cannot read the auto flag.

Choices of the agent:

5. The diagnostics go on their own topic `TopicTypes.DIAGNOSTICS` with `DiagnosticsMessage`, not on
   `TopicTypes.RECORDING_FINISHED`. This replaces the channel of items 2 and 12 of
   [ADR-AC5B](AC5B-choices-of-the-third-consistency-check.md).
6. The watch thread reads the queues also during the close of the group, but watches no camera then. A
   camera process waits at most 1 s for its close dict to reach the pipe, then exits. A closed group keeps
   its last dicts in `CameraGroupManager.diagnostics()`.
7. The watch reads `alive_count` with no lock. On a trip it clears `recording_in_progress` and marks the
   stop as intended before `terminate`. The loop sets `closing` at the start of each close; a reopen sets
   `starting` again after the control thread stops.
8. The `camera_dead` warning of a camera that the watch ended gives the reason of the watch, not the exit
   code.
9. The loop closes a camera whose loop failed with `close(restore=False)`: no restore set. A source skips
   the restore after a stream error, and does no close step after a hang.
10. A failure with no code that is hung gets `hung`; `start stream` counts as a stage before streaming; a
    failed control call sets no `fail_code` of Media Foundation.
11. A failure that the main process sets also sets `fail_code` in the dict that it keeps.

## Reason

Each choice keeps a healthy camera running, keeps the diagnostics of a close, or makes the code follow
the specs with the smallest change.

## Evidence

Experiments of the review (scratch scripts, now tests in `skellycam/tests/capture/`): a trip during a take
waited 15.1 s in `wait_for_recording_save`; 4 of 4 close dicts were lost; the in-process rule won 24 of 24
races at 2 s against the watch at 2 s; a suspended camera process held a `Value` lock in 0 of 200 tries.
Tests: `test_stall_watch.py`, `test_diagnostics.py`, `test_restore.py`, `test_media_foundation_source.py`.
