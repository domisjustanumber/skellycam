# P5VE — Choices of the fixes of the connection review

**Status:** superseded by [P98T](P98T-step-5a-choices-of-the-recorder-and-its-connection.md), 2026-11-20 (commit to dom/integration; was accepted, 2026-11-20 (user, through the review sheets of 2026-11-20); was proposed, 2026-11-20 (agent)).

## Decision

An agent fixed the faults of the reviews of the connection of the take recorder
([ADR-YNM2](YNM2-connection-of-the-take-recorder-to-the-shared-loop.md)) and applied the decisions of
the user in [ADR-JMS0](JMS0-review-decisions.md). The agent made these choices, except the items marked "task
limit set by the supervisor". The user decides them. [ADR-F8C0](F8C0-third-review-choices.md) holds
the choices of the third review.

1. The app state has `recording_in_progress` true while `CameraGroup.take` is set, also when each
   camera died in it, and while a stored summary of an error end waits for its stop request (F8C0).
   It is false while the cameras start and when each camera failed. `all_cameras_recording` goes.
2. The main process clears `recording_in_progress` of a camera whose process ended, in `_mark_ended`
   (before its state check: a hung camera is already `dead`) and after the join in `_collect_results`.
3. `CameraGroup.take_error` keeps the first error of a take: the text of the camera message, the
   `error` of a result ("disk stall" gives "disk stall on camera `<id>`"), or "disk stall on camera
   `<id>`" for a camera with no result past the limit of recorder.md 5.3 item 4. `finish` gets it.
4. (Gone: the stop does not pause the cameras, [ADR-82AA](82AA-stop-last-frame-survivor-files-and-stuck-writer-limit.md) item 1.)
5. `stop_recording` holds the end lock while it reads the take. The error end sets `ended_take`
   under the same lock. An exception of the error end is logged from its future.
6. `CameraTakeWriter.abandon` writes each queued item and the row of the last block, closes both files
   with no padding and no `# end` line, and returns the text of a write error or None. The loop calls
   it when its take has no last frame and the group runs; the take level completes the pair after the
   join (recorder.md 4.3, 7.4). When the group does not run, see F8C0 item 5.
7. A stuck camera whose process runs after `terminate` and the join gets `kill`. When it runs after
   that, `Take.finish` gets it in `running_cameras` and does not complete its files. The manifest
   stays `recording`, with null summary values and a `take_error` that names the camera. Accepted by the user: [ADR-82AA](82AA-stop-last-frame-survivor-files-and-stuck-writer-limit.md) item 2.
8. A camera writer that cannot start keeps its camera running, with the text "camera `<id>`: the take
   writer did not start: `<error>`" in its status info (`writer_failure`). The record start waits
   until each camera started its writer or failed, then fails with HTTP 500 and that text. The folder
   of D gets `take_error` "the record start failed: `<text>`". Before `finish`, the failed start waits
   for each camera with a writer or in the gate (its result or its refusal), and it unpauses with no
   wait. A camera that gets its take spec when the first frame is −1 or a last frame is set refuses
   it.
9. The `detail` of `camera_gap` is `row=<k> from=<a> to=<b>`, for the first gap row k of the camera;
   a and b are the source frame numbers of rows k − 1 and k. SFF-727 allows a text for people.
10. `wait_for_recording_save` ends after 15 s (`RECORDING_SAVE_LIMIT_S`) with no progress of the
    camera writer (`CameraStatus.writer_progress_at`), counted from the later of the start of the wait
    and the last progress [C6DE D1]: the stall limit (10 s) plus the margin of recorder.md 5.3 item 4. Accepted by the user: [ADR-82AA](82AA-stop-last-frame-survivor-files-and-stuck-writer-limit.md) item 3.
11. Tests: in THREAD mode, a held writer thread ends as a killed process ends when its camera's stop
    flag is set. The OpenCV fake has `fail_until_ns` on the virtual clock. The take start of a THREAD
    test reads the virtual clock.
12. E needed no code change. The "pull source only" text was in recorder.md 5.2, 10 item 10 and 16
    item 32.
13. Items 1, 4, 8 and 10 of YNM2 are now A, E, C and D, and B of JMS0.
14. Each camera process gets the union of the member statuses and the removed statuses
    (`CameraManager._create_worker`). A removed status is `failed`, so it is not in the gate.
15. H is in the loop only (`RECOMMEND_MAX_EXPOSURE`, `RECOMMEND_OFFSET`); the old helper keeps -4.
    Task limit set by the supervisor: the search still runs at the open, and the mode names stay.
16. The 100 ms watch of a killed process (review item 16) is from step 3a. It is not changed.
17. K. Task limit set by the supervisor: the three tables of `.gitleaks.toml` (the Windows camera key
    shape; the rig anchor self-test and its synthetic keys; three research notes with their sample
    keys, codec paths and a file hash; `condition = "AND"` where a table has paths and regexes) and
    `[^/]+` for a folder named after a machine. Facts: the 14,551 hits of the history were of the rule
    `generic-api-key`, all under `research/`; an independent run of gitleaks 8.30.1 with this file
    gave 0 hits.
18. I: an entry of `ALLOWED_LINES` is keyed by path and line number, and holds the SHA-256 of the
    exact line text with no line end, and a reason. A finding passes only when the hash matches. A
    term of `.private-terms` is still reported on an allowed line.

## Reason

- Items 2 to 8: each fault of the reviews, with the smallest change in the code that has the fault.
- Item 10: the stop gives up on a writer at that limit; the exit of the app waits no longer.
