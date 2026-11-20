# P5VE — Choices of the fixes of the connection review

**Status:** proposed, 2026-11-20 (agent).

## Decision

An agent fixed the faults of the independent review of the connection of the take recorder
([ADR-YNM2](YNM2-connection-of-the-take-recorder-to-the-shared-loop.md)) and applied the decisions of
the user in [ADR-JMS0](JMS0-connection-review-decisions.md). The agent made
these choices. The user decides them.

1. `CameraOrchestrator.all_cameras_recording` is false when no camera is in the gate. Its only
   caller is `CameraGroup.to_state`. The record start waits on the flag of each camera, not on the
   property.
2. The main process clears `recording_in_progress` of a camera whose process ended, in `_mark_ended`
   (before its state check: a hung camera is already `dead`) and after the join in `_collect_results`.
3. `CameraGroup.take_error` keeps the first error of a take: the text of the camera message, the
   `error` of a result ("disk stall" gives "disk stall on camera `<id>`"), or "disk stall on camera
   `<id>`" for a camera with no result past the limit of recorder.md 5.3 item 4. `finish` gets it.
4. A stop whose pause times out or fails ends the take as after an error, with no pause. It does not
   stop the group. It clears the pause flags first.
5. `stop_recording` holds the end lock while it reads the take. The error end sets `ended_take`
   under the same lock. An exception of the error end is logged from its future.
6. `CameraTakeWriter.abandon` ends the writer thread with no end of the files and returns no result.
   The loop calls it when its take has no last frame. The take level completes the pair after the
   join (recorder.md 4.3, 7.4).
7. A stuck camera whose process runs after `terminate` and the join gets `kill`. When it runs after
   that, `Take.finish` gets it in `running_cameras` and does not complete its files. The row check
   then adds a `take_error`, and the manifest is `finished`.
8. A camera writer that cannot start keeps its camera running. The loop writes the text "camera
   `<id>`: the take writer did not start: `<error>`" in the status info (`writer_failure`). The record
   start waits until each camera started its writer or failed, then fails with HTTP 500 and that
   text. The folder of D gets `take_error` "the record start failed: `<text>`". The cameras that end
   a writer are the cameras with a writer before the unpause; a camera that starts its writer later
   is not waited for.
9. The `detail` of `camera_gap` is `row=<k> from=<a> to=<b>`, for the first gap row k of the camera;
   a and b are the source frame numbers of rows k − 1 and k. SFF-727 allows a text for people, so
   the format does not change.
10. `wait_for_recording_save` waits at most 15 s (`RECORDING_SAVE_LIMIT_S`) from its start: the
    stall limit of a take (10 s) plus the margin of recorder.md 5.3 item 4 (5 s). Then it logs an
    error and returns.
11. Tests: in THREAD mode, a held writer thread ends as a killed process ends when its camera's stop
    flag is set (T-REC-48 case 3). The OpenCV fake has `fail_until_ns` on the virtual clock (T-REC-48
    case 1). The take start of a THREAD test reads the virtual clock.
12. E needed no code change: the loop already counted from the later of the last arrival and the
    last wait for each source. The text "pull source only" was in recorder.md 5.2, 10 item 10 and
    16 item 32. Section 9.5 of `windows-capture.md` had no such limit; it gets a note.
13. Items 1, 4, 8 and 10 of YNM2 are now A, E, D and B of JMS0. D replaces "the folder stays
    `recording`" of YNM2 item 8.
14. Each camera process gets the union of the member statuses and the removed statuses
    (`CameraManager._create_worker`). A removed status is `failed`, so it is not in the gate.
15. H is in the loop only (`RECOMMEND_MAX_EXPOSURE`, `RECOMMEND_OFFSET` in `camera_loop.py`). The
    old helper `recommend_camera_exposure_setting.py` and its `MAX_EXPOSURE` (-4) do not change.
16. The 100 ms watch of a killed process (review item 16) is from step 3a. It is not changed.

## Reason

- Items 2 to 8: each fault of the review, with the smallest change in the code that has the fault.
- Item 10: the stop already gives up on a writer at that limit; the exit of the app waits no longer.

## Evidence

The tests of each item are named in the commit messages of the branch. Run:
`uv run pytest skellycam/tests/capture skellycam/tests/take_recorder`.
