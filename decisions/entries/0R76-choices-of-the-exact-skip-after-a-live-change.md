# 0R76 — Choices of the exact skip after a live change and after a search: anchors, replay, limits, fake sets

**Status:** proposed, 2026-11-24 (agent; builds the decisions of the user in
[ADR-53VB](53VB-decision-of-the-user-on-the-exact-skip-after-a-live-change.md) and
[ADR-JWZ1](JWZ1-decision-of-the-user-on-the-exact-skip-after-a-search.md)).

## Decision

1. **Anchor of a live change.** Skipped frame 1 is the first taken frame whose arrival time is later than
   `after_ns`: the time that the control thread reads just before it calls the set
   ([`windows-capture.md`](../../specs/windows-capture.md) 10.2). This is the filter
   `arrival_ns <= check["after"]` of the code before. A frame that arrives during the set is skipped. The rule
   says "taken", not "delivered": the loop does not know the arrival time of a frame that it did not take, so a
   frame that the source replaced in the waiting place adds to the skip.
2. **Mechanism.** The loop keeps the source frame number and the arrival time of its last 1024 taken frames
   (`CameraLoop.recent_frames`) and clears them at each open. `CameraLoop._start_check` makes the check, sets
   `checking` and gives the check each kept frame whose arrival is later than the anchor, in order. A frame that
   the loop took before it read the result thus counts. 1024 frames hold a set of 5 s (`BOUNDED_CALL_LIMIT_S`)
   only up to about 204 fps, and the 6 s of `FINAL_SET_LIMIT_NS` only up to about 170 fps. When the kept frames
   already hold the whole window, the check decides in that call, so `checking` lasts no time.
3. **Search, a last set that answers** (ADR-JWZ1). The anchor is `search_final_ns`: the time that the loop reads
   just before it sends the last set to the control thread. The last set is the set of the result, or the held
   value again after a failure. A set of the held value that answers is "an answered set" under ADR-JWZ1: this
   reading is mine. `_end_search` sets `self.search` to None first, so a frame taken during the search (which
   `_feed_check` ignored) counts once, in the replay. T-REQ-99 tests it.
4. **Search, a last set with no answer.** When the last set gives no answer in `FINAL_SET_LIMIT_NS`, the anchor is
   the time that the loop reads when that limit runs out, as before ADR-JWZ1, so no frame from before it counts.
   ADR-JWZ1 does not cover this path. T-REQ-100 tests it.
5. **Known limit.** The search anchor is read on the loop thread before the request is queued. When the control
   thread is busy, for example with a trial set that still runs at the time-out of the search, frames at the old
   exposure arrive between that read and the real call. They land in the skip, and in the window when the delay
   is longer than 15 frames. The mechanism stays.
6. **Tests.** The fake gets `live_set_delay_s` (each live change) and `live_set_delays` (the n-th one): the set
   waits that long on the clock, outside the lock of the fake. The tests read the anchor of the product
   (`spy_check_anchors`), because a forced step of the virtual clock can come between it and the `set_controls`
   event of the fake. They wait until the tracker has `too_slow`. The lower bound of the anchor is the frame
   that ended the last trial (T-REQ-99), and the clock before the apply request (T-CAP-31): the second bound is
   honest but weak, because the request takes real time while the virtual clock runs.

## Reason

1. The anchor is the time that the code already stored. A frame that arrives during the set comes after the
   change of the user, and the skip exists for such frames.
2. The replay needs no new field in the signal and no read of a loop field by the control thread.
3. The control thread reads no time before a search set, and the reply holds only the return time; a new field
   changes each reader of the reply. The loop reads its time just before the request; the call comes at once
   only when the control thread is idle (item 5). On the virtual clock, with an idle control thread, the two
   times are equal.
4. With no answer, the frames before the time-out are frames of the last trial's exposure. A reviewer's run with
   that anchor got `ready` at 30 fps although the camera then ran at 20 fps.
5. With no virtual time in a set ([ADR-DC43](DC43-choices-of-fix-lane-5.md) item 1), only a set that waits on
   the clock makes k > 0 in a fixed way.

## Alternatives rejected

1. The first frame taken after the set returned: the count depends on the time of the set.
2. The last taken `source_frame_number` sent with the signal (the suggestion of the review): a frame that
   arrived before `after_ns` but waited in the waiting place would count.
3. A buffer only while a change runs: a flag between two threads, for the same result.
4. For the search, the return time of the last set: it does not count the frames of that set.

## Open work

[open-work.md](../open-work.md)
