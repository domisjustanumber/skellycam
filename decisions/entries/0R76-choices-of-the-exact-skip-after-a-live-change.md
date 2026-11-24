# 0R76 — Choices of the exact skip after a live change: the anchor, the replay of the taken frames, a slow fake set

**Status:** proposed, 2026-11-24 (agent; builds the decision of the user in
[ADR-53VB](53VB-decision-of-the-user-on-the-exact-skip-after-a-live-change.md)).

## Decision

1. **Anchor.** After a live change, skipped frame 1 is the first taken frame whose arrival time is later than
   `after_ns`: the time that the control thread reads just before it calls the set of the change
   ([`windows-capture.md`](../../specs/windows-capture.md) 10.2). This is the filter
   `arrival_ns <= check["after"]` of the code before this change. A frame that arrives during the set is a
   skipped frame. The rule says "taken", not "delivered": the loop does not know the arrival time of a frame
   that it did not take. A frame that the source replaced in the waiting place thus adds to the skip.
2. **Mechanism.** The loop keeps the source frame number and the arrival time of its last 1024 taken frames
   (`CameraLoop.recent_frames`). It clears them at each open, because the source frame numbers start again.
   When it reads the check signal, it makes the check and then gives it each kept frame whose arrival is
   later than `after_ns`, in order. Thus a frame that the loop took before it read the signal counts. 1024
   frames hold a set of 5 s (`BOUNDED_CALL_LIMIT_S`, the longest set) only up to about 204 fps. The signal
   and the control thread do not change.
3. **The search path is unchanged.** The check after an exposure search starts at the return time of the last
   set and gets no replay, so it skips 15 + k frames. Spec 10.2 says so. The user decides if it gets the rule.
4. **Test.** The fake source gets `live_set_delay_s`: a live change waits that long on the clock before it
   sets, outside the lock of the fake. `test_t_cap_31_the_skip_counts_the_frames_of_a_slow_set` uses 0.2 s
   (about 6 frames during the set). T-CAP-31 again has one exact window: the 16th frame from skipped frame 1.
   The test reads the anchor of the product (`spy_check_anchors`), not the time of the `set_controls` event of
   the fake: a forced step of the virtual clock can come between the two. It waits until the tracker has
   `too_slow`.

## Reason

1. The anchor is the time that the code already stored. A frame that arrives during the set comes after the
   change of the user, and the skip exists for such frames.
2. The replay needs no new field in the signal and no read of a loop field by the control thread. The arrival
   filter of item 1 stays the only rule.
3. With no virtual time in a set ([ADR-DC43](DC43-choices-of-fix-lane-5.md) item 1), only a set that waits on
   the clock makes k > 0 in a fixed way.

## Alternatives rejected

1. The first frame taken after the set returned: it skips the frames of the set, so the count depends on the
   time of the set.
2. The last taken `source_frame_number` sent with the signal (the suggestion of the review): a frame that
   arrived before `after_ns` but waited in the waiting place would count.
3. A buffer only while a change runs: a flag between two threads, for the same result.

## Open work

[open-work.md](../open-work.md)
