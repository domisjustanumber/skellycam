# YNM2 — Connection of the take recorder to the shared loop

**Status:** proposed, 2026-11-20 (agent; the user approved the connection code on 2026-11-20).

## Decision

The connection commit of [`specs/recorder.md`](../../specs/recorder.md) section 10 joins the take
recorder of step 5a to the shared loop of step 3a. It removes the interim rules U4, U5 and U12
([ADR-QKX1](QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md)) by the decisions R1 to R5
([ADR-VPF8](VPF8-phase-5-recorder-decisions.md)), M1 to M5, C1, C5 to C7
([ADR-J3QP](J3QP-missing-frames-as-black-placeholders-and-the-end-of-a-take.md)) and D1 to D3
([ADR-C6DE](C6DE-stall-as-no-progress-limits-and-no-fat-disk.md)). It makes the edits of section 14
of the recorder spec in [`specs/windows-capture.md`](../../specs/windows-capture.md) as dated notes.
An agent made these choices, which the specs do not fix. The user decides them.

Shared loop and camera process:

1. The frame count of a take is `last_recording_frame_number − first_recording_frame_number`. The
   orchestrator records the group frames first to last − 1; the "+ 1" of recorder.md 7.6 would add a
   row with no frame. `should_record_frame_number` records no
   frame when the first frame is −1, so a stale last frame does not record again.
2. The loop publishes the SOF layout of its last good frame in the status info (`layout`) when it
   pauses. Each take starts paused, so the take level reads it for `TakeCamera.layout` (10 item 3).
3. The shared value of progress is `CameraStatus.writer_progress_at` (a `time.monotonic()` double).
   `CameraTakeWriter.start` gets it as `progress` and writes it at each progress (D1).
4. The stall watch counts from the later of the last arrival and the end of the last wait of the loop
   at the gate or in `give`, for each source: a push source gets frames during the wait anyway.
5. After `RecorderStalled` or `RecorderWriteError`, the loop sends a `RecordingFinishedMessage` with
   the error text and no result. The text of a stall is "disk stall on camera `<id>`". The text of a
   write error is the error text of the writer.
6. A camera process that ends hard after a hang sets `hung` in its status info first. The take level
   gives the `camera_dead` reason "hang"; for another ended process, "exit code `<n>`"; for a dead
   camera with a result, the reason of its failure object.
7. With no camera left in the gate, the stop sets the last frame from the largest gate count of the
   cameras of the take, and the loop of a dead camera pads to that frame.

Main process:

8. The record start waits, paused, until each camera in the gate started its writer (at most 10 s),
   then unpauses. A start that fails after `start_take` sets the last frame to the first frame, so
   each started writer ends at once; the folder stays `recording` (step 5c).
9. A take folder that holds files gives 409 before `start_take`. Each `ValueError` of `start_take`
   (name, FAT disk, camera) gives 422 with its text.
10. A take that an error ended is ended by the watch of the group at once. The next stop request
    returns its stop response. A stop with no take gives 409 "No recording runs".
11. The stop after an error does not pause the cameras: a stalled camera cannot pause, and it holds
    the gate, so no camera passes the last frame.
12. Before it ends the process of a stuck camera, the main process clears its recording flag and sets
    its stop flag. The recording-save guard of the worker would wait for ever, and a THREAD worker ends
    by the stop flag.
13. The close of the group stops a take only when `CameraGroup.take` is set, not when a status flag is
    set: a process that ended hard leaves its flag set.
14. `TakeCamera` facts: the mode of the status (or the requested rate, or 30 for "auto", when OpenCV
    reports no rate); `requested` from the stored config (the mode rate, D17; `MANUAL` after
    `RECOMMEND`); `backend` from the source name; the device facts of the last detection.

Playback, deletions and tests:

15. The mark text of a new take is "needs the new player". The list entry of a new take has the size of
    its media folder and the folder time.
16. Deleted with the old writer: `calculate_timestamps_numpy.py` and `create_initial_frame_recarray.py`
    (no other caller); the write paths and `create_temp` of `RecordingInfo`; the tasks
    `test-recording-safety` and `test-recording-lifecycle`; the tests of the deleted code. The H.264
    writer moves to `skellycam/tests/old_video_writer.py`: the reader tests make old recordings with it.
17. Capture tests: T-CAP-07, T-CAP-34, T-CAP-39, T-CAP-58, T-CAP-95, T-CAP-103, T-CAP-108, T-CAP-109
    and T-CAP-110 change to the files of the take recorder; T-CAP-09, T-CAP-10, T-CAP-35 and T-CAP-85
    are deleted for T-REC-41 to T-REC-44; the multi-frame timing test goes with the old files. A new
    test covers a stop after a hang, then the close. T-RING-47 drops its check of the recorder buffer.
18. The index cells of this log are shorter: the merge of the recorder branch put the index over its
    limit.

## Reason

- Items 1, 7 and 13: no row for a frame that was not recorded, and no second take after a stop.
- Items 2, 3 and 5: the smallest shared values that sections 4.2, 5.3 and 6.4 need.
- Items 8, 10 and 11: row 0 is one group frame for every camera; the app keeps running (5.3).
- Item 12: the files of the new recorder survive a hard stop.

## Evidence

- Item 13 and the fault "Record requested before video_recorder was created" of the open work:
  `test_record_stop_after_a_hang_then_close`, `test_no_recording_after_the_take_ended`.
- The hardware finding B1 of the first 3a run (the unstamped retrieve stage in the old statistics)
  goes with the old statistics files.

## Alternatives rejected

- Item 1: the "+ 1" of 7.6 with an extra placeholder row. It fabricates a row.
- Item 10: keep the take open until the stop request. A stall would hold the disk and the gate.

## Open work

See [open-work.md](../open-work.md).
