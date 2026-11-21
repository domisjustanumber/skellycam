# NYT6 — Choices of fix lane 2

**Status:** proposed, 2026-11-21 (agent; the items come from the supervisor, after real-camera runs).

## Decision

Fix lane 2 makes small fixes. The supervisor gave each item. The user decided item 1 (Q522: "re-measure a
borderline value"). The agent made these choices:

1. Borderline value of the exposure search. A value that does not keep the rate, and whose measured rate is not
   more than 10 % below the mode rate (`measured >= 0.90 x r`), is measured again one time. The second window
   starts at the frame that ended the first window, with no new set and no frames to settle. The trial keeps
   the brightness of the first window, and the second window decides. A second miss drops the value. The limit
   of 20 s stays ([`camera-requests.md`](../../specs/camera-requests.md) 1.3 item 2.7).
2. Frame decision outside a take. `should_record_frame_number` reads the first frame of the take before the lock
   of the last frame. When it is -1, the decision gives "no record, no finish" and takes no lock
   ([`unix-capture.md`](../../specs/unix-capture.md) 4.10). The supervisor gave this rule; it is here because no
   other entry holds it.
3. Two texts of [`unix-capture.md`](../../specs/unix-capture.md) 4.10 now state what the code does: a call that
   finds the camera process ended logs one more line, and a write error of `abandon()` replaces the error text of
   a camera that ends its part of the take alone (a correction that the supervisor found).
4. Clamp warning. The clamp of a `MANUAL` exposure above -5 gives the warning kind `exposure_clamped`, control
   `exposure`, with the text `Camera <id>: manual exposure <value> is above the limit -5. The exposure is -5.`
   The main process owns it: it is in the response of the apply request and in `group_warnings` of the camera,
   and it clears at the next apply request of the user. The UI row shows the plain line "The longest manual
   exposure is -5. The camera uses -5." ([`camera-requests.md`](../../specs/camera-requests.md) 1.1, 1.5, 1.8).
5. Meaning of `alive`. `alive` of a group in the state is true while the group runs and at least one selected
   camera lives: its camera process runs, and it is not `failed` or `dead`, not closing and not closed. A
   camera in `starting` lives ([`camera-requests.md`](../../specs/camera-requests.md) 1.5). The supervisor
   suggested this meaning; the specs were silent.

## Reason

1. 28.1 fps is 6.3 % below 30 fps, and 56.5 fps (the C922 at -6 in its 60 fps mode) is 5.8 % below 60 fps: a
   margin of 10 % includes these readings. A slow value at 15 fps or 29.7 fps at 60 fps is far outside it, so the
   search measures it one time, as before. One repeat keeps the cost low. A second window that starts at the
   last frame needs no new set and no new frames to settle, so it costs 30 frames.
2. A camera process killed while it held the lock of the last frame made each new camera process wait 1.5 s at
   its first frame, also outside a take. Outside a take the last frame has no use. A take still cannot end
   normally after such a kill: each later take of the group ends with the error of the lock until the cameras
   are closed and opened again (4.10).
4. Before, the clamp changed the value with no word. The main process does the clamp, so it owns the item, as
   it owns `start_failure`. The row line has no camera value, so it needs no translation with a number.
5. Before, one dead camera made the group not alive while the other cameras still recorded. No code and no UI
   reads `alive` to decide (the UI type has it, and no component uses it), so the change affects only the
   clients of the API.

## Consequences

1. Each repeat adds about 1.0 s at 30 fps and about 0.5 s at 60 fps. On the lab cameras a search of 7 values
   took about 16 s, so a search with more than about three borderline values can pass 20 s and fail with
   `timed-out`. The agent did not change the limit. If camera runs show such failures, the user must decide a
   new limit. One repeat may not be enough for the Kiyo Pro at -8 (a miss in four of five opens): the camera
   runs T-REQ-23 and T-REQ-26 must record how often a value is measured again.

## Evidence

1. The fake-camera timeline of `skellycam/tests/capture/test_exposure_search.py` (`simulate`, T-REQ-77), 30 fps,
   8 values: 10.67 s with no borderline value; 11.69 s with one value at 28.1 fps for 40 frames, then 30 fps (kept
   at the repeat); 11.72 s with one value at 28.1 fps for each frame (dropped after the repeat); 10.73 s with one
   value at 25 fps (no repeat); 18.82 s with each of the 8 values at 28.1 fps (each measured two times; no time
   for set calls). At 60 fps: 5.33 s, and 5.87 s with one value at 56.5 fps.

## Alternatives rejected

1. Two or more repeats: each repeat adds 1 s at 30 fps, and the search is near its limit of 20 s on the lab
   cameras.
2. A longer first window for each value: it adds time to each value, also to a value that clearly keeps the
   rate.
