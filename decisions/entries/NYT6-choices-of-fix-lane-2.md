# NYT6 — Choices of fix lane 2

**Status:** proposed, 2026-11-21 (agent; the supervisor gave the items, after real-camera runs).

## Decision

The user decided the rule of item 1 (Q522: "re-measure a borderline value"). The supervisor gave the other
items. The agent chose these details:

1. A value of the exposure search that misses the rate by not more than 10 % (`measured >= 0.90 x r`) is
   measured again one time. The second window starts at the frame that ended the first, with no new set and no
   frames to settle; it keeps the brightness of the first window and decides. The limit of 20 s stays
   ([`camera-requests.md`](../../specs/camera-requests.md) 1.3 item 2.7).
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
6. The "before" values and the changed names of the controls live in the shared JSON array `controls_before` of
   `CameraStatus`. The source writes it before the first set of each newly changed control; a restore with no
   failure clears it; at the first read of an open, a record that is not empty replaces the values that the camera
   reads. "Apply again" keeps it; `CameraGroupManager.restore_records` keeps it to the next group, in memory. The
   camera process finds it through `RESTORE_RECORDS` of `capture/source.py` (`unix-capture.md` 4.7).

## Reason

1. 28.1 fps is 6.3 % below 30 fps; 56.5 fps (the C922 at -6, 60 fps mode) is 5.8 % below 60 fps. A slow value
   (15 fps, or 29.7 fps at 60 fps) is far outside 10 %, so it costs no repeat. One repeat of 30 frames keeps the
   cost low.
2. A camera killed inside that lock made each new camera process wait 1.5 s at its first frame. Each later take of
   such a group still ends with the lock error until the cameras are closed and opened again (4.10).
4. Before, the clamp changed the value with no word. The main process does the clamp, as it does `start_failure`.
5. One dead camera made the group not alive while the others recorded. No code or UI component reads `alive`.
6. A camera process that a kill or a failed loop ended got no restore: the camera stayed in manual exposure, and
   the next open read that value as "before" (real cameras). The main process makes and keeps the status, so the
   record survives the camera process with no new channel. 4.7 [U] forbids an open only to restore, so the close
   of the next open restores.

## Consequences

1. Each repeat adds about 1.0 s at 30 fps and 0.5 s at 60 fps. A lab search of 7 values took about 16 s, so more
   than about three borderline values can pass 20 s (`timed-out`). If camera runs show this, the user must decide
   a new limit. One repeat may be too few for the Kiyo Pro at -8 (a miss in four of five opens): T-REQ-23 and
   T-REQ-26 must record the repeats.
6. A group close does not restore a camera whose process ended. The record is not on disk: a restart of the app
   loses it, and the next app reads the manual value as "before".

## Evidence

1. The fake timeline `simulate` of `skellycam/tests/capture/test_exposure_search.py` (T-REQ-77), 30 fps, 8
   values, no set time: 10.67 s with no borderline value; 11.69 s with one value at 28.1 fps for 40 frames, then
   30 fps (kept); 11.72 s with one value always at 28.1 fps (dropped); 10.73 s with one value at 25 fps (no
   repeat); 18.82 s with each value at 28.1 fps. At 60 fps: 5.33 s, and 5.87 s with one value at 56.5 fps.

## Alternatives rejected

1. Two or more repeats, or a longer first window for each value: each costs time near the limit of 20 s.
6. A restore at the group close in a short process that opens the camera: 4.7 [U] forbids it, and a wedged
   camera (the Kiyo Pro) can hang the open. A file on disk for the record: a new format for a rare case.
