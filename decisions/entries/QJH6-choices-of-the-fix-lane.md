# QJH6 — Choices of the fix lane of 2026-11-21

**Status:** proposed, 2026-11-21 (agent; the items come from the supervisor, after reviews and real-camera runs).

## Decision

The fix lane makes small fixes. The supervisor gave each rule. The agent made these choices:

1. E. At an open, a camera in `AUTO` sets its held value inside the search values: the values -12 to -5
   that are in the exposure range of the camera, on its step grid. A held value that is not one of them
   is set at the nearest of them. When the range has no search value, the held value is set inside the
   range, as before ([`camera-requests.md`](../../specs/camera-requests.md) 1.3a).
2. F. The warning kind for a camera that cannot join a running group is `cameras_left_out`. The item is
   only in the `warnings` of the apply response that selects that camera, not in a status: the camera
   has no status in the group ([`windows-capture.md`](../../specs/windows-capture.md) 11.3).
3. G. Each scalar of `CameraStatus` is a shared Value with no lock. For a JSON array of `CameraStatus`
   (`info` and the three warning arrays, by name), one wait of at most 0.5 s and one error line come in
   each stretch with no lock; the next calls try with no wait. The main process stops the tries for a
   status only when its camera process has ended. `reset_for_start` always gives four new arrays, which
   go to the new process when it is spawned. A read gives the last good JSON after 3 torn reads. A
   main-process write of `info` with no lock stays in the main process until a write with the lock. The
   heartbeat value, the global kill flag, the group flags and the first frame of a take have no lock. The
   last frame is read and written with no lock, except in its two check-then-set blocks, which wait at
   most 0.5 s for its lock and then end the take (or the part of one camera) as an error, and in the read
   of each frame decision, which waits at most 1.5 s one time in each stretch with no lock. A failed read of
   the app state sets no kill flag ([`unix-capture.md`](../../specs/unix-capture.md) 4.10).
4. I. The opened mode of the OpenCV source (the `mode` of the status) has the FOURCC of `CAP_PROP_FOURCC`,
   or `BGR` when the backend gives 0 or a negative value
   ([`windows-capture.md`](../../specs/windows-capture.md) 14 (e)).
5. H. A record start that fails after `start_take` returned keeps `"ended_with_error"` and the summary
   of the earlier take, as a refusal before it does. Only a record start that succeeds drops that
   summary ([`recorder.md`](../../specs/recorder.md) 8.4). The state stays `"ended_with_error"` during a
   record start until it succeeds. `ended_take_summary.summary` gives a NaN statistic as null, as the stop
   response does. The UI shows the notice only for a take (its folder, else its name) that no notice
   showed yet ([`camera-requests.md`](../../specs/camera-requests.md) 8.4).

## Reason

1. E. A held value of -1 on a camera with the range -11 to -2 opened at -2 (a 250 ms exposure, 4 fps). The
   warm-up failed, so the camera never searched (a real-camera run).
2. F. Before, the apply answered 200 and left the camera out silently. The UI already closes all cameras
   and connects them again in this case, so the item is for the other consumers of the API.
3. G. A process that is killed while it holds the lock of a shared Value or Array keeps the lock for ever.
   A main-process read then waits for ever, also on the event loop (the state route and the websocket).
   One writer at a time sets each scalar, and an aligned scalar is read and written whole, so a scalar
   needs no lock. A JSON array needs its lock against a torn read. The review of the fix lane measured
   2.2 % torn reads with no lock for good after one slow holder, and a decode error in the websocket
   sender ended the app: thus no flag for good while the process lives, and readers that never raise. The
   second check of the fix lane found that a camera killed with the lock of the last frame stopped each
   other camera at its next frame, and that a restart could start on arrays with a lost lock. The read of
   each frame decision keeps the lock: with no lock there, the test of a slow stop (round 4: the main
   process busy for up to 1 s between its read of the gate count and its write) gave rows that differ.
4. I. The FOURCC in the config of `extract_config_from_cv2_capture` reached no reader: the opened mode does.
5. H. The supervisor found the earlier rule a fault: a failed start dropped a summary that no client had
   fetched, and logged "A new take starts" for a take that did not start.

## Alternatives rejected

1. F. The item in `group_warnings` of each running camera: it names a camera that is not on that row.
2. G. A new failure code for a lost lock: the end of the process already gives `process-ended`.
