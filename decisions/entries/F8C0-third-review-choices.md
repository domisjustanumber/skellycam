# F8C0 — Choices of the fixes of the third review of the recorder connection

**Status:** proposed, 2026-11-20 (agent).

## Decision

An agent fixed the findings of the third review of the connection of the take recorder and applied
L and M of [ADR-JMS0](JMS0-review-decisions.md). It continues
[ADR-P5VE](P5VE-review-fix-choices.md). The agent made these choices. The user decides them.

1. S1: when the last unpause of a record start times out, the start logs it and the take runs on (each
   writer started). The last frame of a stop is at least the first frame of the take.
2. S2: the take specs are built before the take is set. A failed start whose specs did not go out
   waits for no camera.
3. S3: the app state has `recording_in_progress` true until the stop request fetched the stored
   summary of an error end. A failed start does not store a summary.
4. S7: `start_recording` holds the end lock of the group, as the stop and the error end do.
5. With no take level (the group stops, or the main process is gone), the first camera that ends
   sets the last frame two group frames after the latest group frame, at least the first frame, under
   the lock of that shared value. Each camera ends its writer with that frame count.
6. L: the heartbeat writer is the thread `WorkerRegistry-Heartbeat` (once a second, not the event
   loop). It starts with the first worker, so a test registry also beats. A blocked event loop does
   not stop it. Only a C call that holds the GIL for 10 s, or a jump of `time.perf_counter` (for
   example after a sleep of the computer), could stop it; neither is tested.
7. S4: `close_camera_groups_before_exit` closes each group (a running take ends through the take
   level) in the shutdown endpoint and at the lifespan end, before the kill flag. Ctrl-C reaches the
   lifespan end through uvicorn. No new limit: the limits of the stop and the close apply. Worst case
   for N stuck cameras: 15 s with no writer progress, 20 s of terminate, kill and joins for each, 10 s
   of the take lock, 15 s of the save wait for each, 8 s of joins: about 140 s for 3 cameras; a few
   seconds when the disk works.
8. S5: a camera process ignores SIGINT; SIGTERM still sets its stop flag. The delivery of Ctrl-C on
   Linux and macOS (the process group) is not tested.
9. S8: `abandon` returns the text of a write error; the loop sends it, and the take level ends the
   take with it (recorder.md 5.4).
10. S11: the stop does not pause the cameras. It sets the last frame two group frames after the
    largest gate count. The pause cost one source frame of a push source before row N − 2.
11. M: `mean_framerate` is, for each camera, the group frames from its first to its last row with an
    arrival time, divided by the time between them; the mean over the cameras, rounded to 2
    decimals; NaN (JSON null) with no camera of two such rows. `framerate_stats` and
    `frame_duration_stats` stay, as rates and durations of each frame. With a delivery grid of 16 ms,
    the intervals are 16, 33 or 50 ms: the rates of `framerate_stats` are 60, 30 or 20, so its median
    is the camera rate, its mean is too high, its max shows the grid, and its std the jitter.
    `frame_duration_stats.mean` agrees with `mean_framerate`, and its max is the longest gap. No field
    goes; the user can decide to drop `framerate_stats`.
12. S12: a 4xx is one WARNING line with no traceback; a 5xx stays ERROR with its traceback.
13. S9: the index is over its limit of 14,000 characters until the user decides to raise it. A module
    log needs the approval of the user (`AGENTS.md` section 5), and these entries name root files.
