# NYT6 — Choices of fix lane 2

**Status:** proposed, 2026-11-21 (agent; the supervisor gave the items, after real-camera runs).

## Decision

The user decided the rule of item 1 (Q522: "re-measure a borderline value"). The supervisor gave the other
items. The agent chose these details:

1. A value of the exposure search that misses the rate by not more than 10 % (`measured >= 0.90 x r`) is
   measured again one time: the window grows to 60 intervals from frame a, with no new set, and its whole rate
   decides. The trial records the first rate in `first_fps` (null with no repeat). The limit of 20 s stays
   ([`camera-requests.md`](../../specs/camera-requests.md) 1.3 item 2.7, 1.5).
2. With no take (first frame -1), a frame decision takes no lock of the last frame
   ([`unix-capture.md`](../../specs/unix-capture.md) 4.10).
3. Two texts of 4.10 now state the code: a call that finds the camera process ended logs one more line, and a
   write error of `abandon()` replaces the lock error text.
4. The clamp of a `MANUAL` exposure above -5 gives the warning kind `exposure_clamped` (control `exposure`), text
   `Camera <id>: manual exposure <value> is above the limit -5. The exposure is -5.` The main process owns it, in
   the apply response and in `group_warnings`; the next apply request of the user clears it. The UI row shows "The
   longest manual exposure is -5. The camera uses -5." (`camera-requests.md` 1.1, 1.5, 1.8).
5. `alive` of a group is true while the group runs and at least one selected camera lives: its process runs,
   and it is not `failed`, `dead`, closing or closed (`camera-requests.md` 1.5). The specs were silent.
6. The "before" values, the changed names and the value that this app set last (asked before the set, read back
   after it) live in the shared JSON array `controls_before` of `CameraStatus`. A restore with no failure clears it.
   At the first read of an open, a control that still holds the value that this app set last takes its "before"
   value from the record; the record drops the other controls. A close that raises still keeps the records. "Apply again" keeps it; `CameraGroupManager.restore_records` keeps it to the next group, in memory. The
   camera process finds it through `RESTORE_RECORDS` of `capture/source.py` (`unix-capture.md` 4.7).
7. The exit of `skellycam/__main__.py` has no fixed wait of 1 s before `WorkerRegistry.shutdown_all()`.

## Reason

1. 28.1 fps is 6.3 % below 30 fps; 56.5 fps (the C922 at -6, 60 fps mode) is 5.8 % below 60 fps. A slow value
   (15 fps, or 29.7 fps at 60 fps) is far outside 10 %, so it costs no repeat. One repeat of 30 frames keeps the
   cost low. The window of 60 intervals gives a truly slow value almost no second chance (T-REQ-80).
2. A camera killed inside that lock made each new camera process wait 1.5 s at its first frame. Each later take of
   such a group still ends with the lock error until the cameras are closed and opened again (4.10).
4. Before, the clamp changed the value with no word. The main process does the clamp, as it does `start_failure`.
5. One dead camera made the group not alive while the others recorded. No code or UI component reads `alive`.
6. A camera process that a kill or a failed loop ended got no restore: the camera stayed in manual exposure, and
   the next open read that value as "before" (real cameras). The main process makes and keeps the status, so the
   record survives the camera process with no new channel. 4.7 [U] forbids an open only to restore, so the close
   of the next open restores.
7. Nothing reads the wait: `uvicorn.Server.serve()` (0.54.0) returns only after its `shutdown()` (connections
   closed, tasks done, lifespan end), so `should_exit` had no reader; `shutdown_all()` sets the kill flag and
   waits for each worker itself.

## Consequences

1. Each repeat adds about 1.0 s at 30 fps and 0.5 s at 60 fps. A lab search of 7 values took about 16 s, so more
   than about three borderline values can pass 20 s (`timed-out`). If camera runs show this, the user must decide
   a new limit. A window that missed two frames (28.1 fps over 30 intervals) is about 29.0 fps over 60 and is
   dropped; only a late frame is forgiven. T-REQ-23 and T-REQ-26 record `first_fps`.
6. A group close does not restore a camera whose process ended. The record is not on disk: a restart of the app
   loses it. Another unit of the same model in the same USB port (no serial number), or a value that another program
   set to exactly the last value of this app, still takes the record. A torn record reads as no record.

## Evidence

1. The fake timeline `simulate` of `skellycam/tests/capture/test_exposure_search.py` (T-REQ-77), 30 fps, 8
   values, no set time: 10.67 s with no borderline value; 11.67 s with one late frame at -8 (kept); 11.75 s with
   one value always at 28.1 fps (dropped); 10.73 s with one value at 25 fps; 19.11 s with each value at 28.1 fps.
   At 60 fps: 5.33 s, and 5.87 s with one value at 56.5 fps. T-REQ-80 (600 seeded runs, the jitter of the review):
   29.0 fps kept 11.3 % with no repeat, 11.8 % with this repeat, 23.8 % when a second window decides alone.

## Alternatives rejected

1. Two or more repeats, or a longer first window for each value: each costs time near the limit of 20 s. A
   second window that decides alone: it about doubles the chance to keep a slow value (T-REQ-80).
6. A restore at the group close in a short process that opens the camera: 4.7 [U] forbids it, and a wedged
   camera (the Kiyo Pro) can hang the open. A file on disk for the record: a new format for a rare case.
