# 25VS — Decisions of the user on later opens after a fallback and on the size floor (Q886 to Q889)

**Status:** absorbed into
[`specs/windows-capture.md#75-mode-choice-auto-rate-group-rate`](../../specs/windows-capture.md#75-mode-choice-auto-rate-group-rate),
[`specs/windows-capture.md#222-rules-of-step-3b`](../../specs/windows-capture.md#222-rules-of-step-3b),
[`specs/unix-capture.md#13-non-goals`](../../specs/unix-capture.md#13-non-goals),
[`specs/unix-capture.md#3-what-stays-and-what-is-shared`](../../specs/unix-capture.md#3-what-stays-and-what-is-shared),
[`specs/camera-requests.md#21-the-rule`](../../specs/camera-requests.md#21-the-rule),
2026-11-26 (commit to dom/jpeg-encode-tests; was accepted, 2026-11-26 (user, relayed by the supervisor)).

## Decision

The words of the user on 2026-11-26: "Q887 - 640x480 is the minimum resolution we'll use, ideally 720p.
As with frame rates lower than 30, also ignore frame rates lower than 640x480. Otherwise agree to all
Q882-Q887", then "Q888 640x360 would be allowed too, and user prompted that hand and face tracking will
be limited by resolution. Q889 yes".

1. **Q886.** After one Quick Sync fallback, each later open of that camera in the same app run uses
   OpenCV (`cv2.imencode`), until the app restarts.
2. **Q887.** The choices of
   [ADR-ZEK6](ZEK6-choices-of-the-jpeg-encode-at-capture-code.md) that the supervisor listed are
   accepted (items 2, 3, 4, 5, 7, 8, 10, 11, 13, 14 and 16), except the Quick Sync test frame of
   320x240: the test frame is at least 640x480, ideally 720p (an agent chose 1280x720,
   [ADR-YQN1](YQN1-choices-of-the-size-floor.md) item 12). 640x480 is the smallest size that skellycam
   uses; 720p is the ideal. As modes below 30 fps are ignored, modes of a size below 640x480 are ignored too (the
   supervisor reads "frame rates lower than 640x480" as "modes of a size below 640x480").
3. **Q888.** 640x360 is allowed too. When the user picks a size below 1280x720, the user is told that
   hand and face tracking will be limited by the resolution. The supervisor read the floor as two
   bounds: a mode passes when its width is 640 or more and its height is 360 or more. The user
   confirmed this reading with Q898
   ([ADR-Y2RN](Y2RN-decisions-of-the-user-on-the-size-floor-review-and-certify-quick-runs.md)).
4. **Q889.** The size floor applies everywhere the 30 fps floor does: each OS, both capture paths
   (native and OpenCV), and the mode list that the UI offers.

## Reason

- The user decided each item.
