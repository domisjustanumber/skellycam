# P5VE — Choices of the fixes of the connection review

**Status:** proposed, 2026-11-20 (agent).

## Decision

An agent fixed the faults of the independent review of the connection of the take recorder
([ADR-YNM2](YNM2-connection-of-the-take-recorder-to-the-shared-loop.md)) and applied the decisions of
the user in [ADR-JMS0](JMS0-review-decisions.md). The agent made
these choices. The user decides them.

1. The app state has `recording_in_progress` = `CameraGroup.take is not None`: false while the
   cameras start and when each camera failed, true while a take runs, also when each camera died in
   it. `CameraOrchestrator.all_cameras_recording` (its only caller was `to_state`) goes.
2. The main process clears `recording_in_progress` of a camera whose process ended, in `_mark_ended`
   (before its state check: a hung camera is already `dead`) and after the join in `_collect_results`.
3. `CameraGroup.take_error` keeps the first error of a take: the text of the camera message, the
   `error` of a result ("disk stall" gives "disk stall on camera `<id>`"), or "disk stall on camera
   `<id>`" for a camera with no result past the limit of recorder.md 5.3 item 4. `finish` gets it.
4. A stop whose pause times out or fails ends the take as after an error, with no pause. It does not
   stop the group. It clears the pause flags first.
5. `stop_recording` holds the end lock while it reads the take. The error end sets `ended_take`
   under the same lock. An exception of the error end is logged from its future.
6. `CameraTakeWriter.abandon` writes each queued item and the row of the last block, then closes
   both files with no padding and no `# end` line, and returns no result. The loop calls it when its
   take has no last frame and the group runs (the take goes on); the take level completes the pair
   after the join (recorder.md 4.3, 7.4). When the group does not run (`should_continue` false: the
   group stops, the global kill flag, no heartbeat of the main process), the loop calls `end` with
   the rows that it gave.
7. A stuck camera whose process runs after `terminate` and the join gets `kill`. When it runs after
   that, `Take.finish` gets it in `running_cameras` and does not complete its files. The manifest
   stays `recording`, with null summary values and a `take_error` "camera `<id>`: its process still
   runs after a kill; its files are not completed".
8. A camera writer that cannot start keeps its camera running. The loop writes the text "camera
   `<id>`: the take writer did not start: `<error>`" in the status info (`writer_failure`). The record
   start waits until each camera started its writer or failed, then fails with HTTP 500 and that
   text. The folder of D gets `take_error` "the record start failed: `<text>`". Before `finish`, the
   failed start waits for each camera with a writer or in the gate (its result or its refusal), and it
   unpauses with no wait. A camera that gets its take spec when the first frame is −1 or a last frame
   is set refuses it ("camera `<id>`: the take ended before its writer started"). A stop whose
   unpause fails logs it and ends the take.
9. The `detail` of `camera_gap` is `row=<k> from=<a> to=<b>`, for the first gap row k of the camera;
   a and b are the source frame numbers of rows k − 1 and k. SFF-727 allows a text for people, so
   the format does not change.
10. `wait_for_recording_save` ends after 15 s (`RECORDING_SAVE_LIMIT_S`) with no progress of the
    camera writer (`CameraStatus.writer_progress_at`), counted from the later of the start of the wait
    and the last progress [C6DE D1]: the stall limit of a take (10 s) plus the margin of recorder.md
    5.3 item 4 (5 s). Then it logs an error and returns.
11. Tests: in THREAD mode, a held writer thread ends as a killed process ends when its camera's stop
    flag is set (T-REC-48 case 3). The OpenCV fake has `fail_until_ns` on the virtual clock (T-REC-48
    case 1). The take start of a THREAD test reads the virtual clock.
12. E needed no code change: the loop already counted from the later of the last arrival and the
    last wait for each source. The text "pull source only" was in recorder.md 5.2, 10 item 10 and
    16 item 32. Section 9.5 of `windows-capture.md` had no such limit; it gets a note.
13. Items 1, 4, 8 and 10 of YNM2 are now A, E, C and D, and B of JMS0. D replaces "the folder stays
    `recording`" of YNM2 item 8.
14. Each camera process gets the union of the member statuses and the removed statuses
    (`CameraManager._create_worker`). A removed status is `failed`, so it is not in the gate.
15. H is in the loop only (`RECOMMEND_MAX_EXPOSURE`, `RECOMMEND_OFFSET` in `camera_loop.py`). The
    old helper `recommend_camera_exposure_setting.py` and its `MAX_EXPOSURE` (-4) do not change. The
    search still runs at the open, and the mode names do not change (a limit of the task: a later task
    moves the search to the running stream).
16. The 100 ms watch of a killed process (review item 16) is from step 3a. It is not changed.
17. K: the 14,551 hits of gitleaks over the history were of the rule `generic-api-key` only, all under
    `research/`, and were classified one by one: USB device identifiers, synthetic test keys, a file
    hash, sample keys; no credential. The three tables of `.gitleaks.toml` (keys of gitleaks 8.30.1,
    the version of `secrets.yml`): the Windows camera key shape; the rig anchor self-test and its
    synthetic keys; three research notes and their sample keys, codec paths and a file hash, with
    `condition = "AND"` where a table has paths and regexes. A folder named after a
    machine is `[^/]+`, so that no machine name is in a tracked file. An independent run of gitleaks
    8.30.1 over the history with this file gave 0 hits.

## Reason

- Items 2 to 8: each fault of the reviews, with the smallest change in the code that has the fault.
- Item 10: the stop gives up on a writer at that limit; the exit of the app waits no longer.
