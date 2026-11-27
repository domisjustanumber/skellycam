# AR6Z — Decisions of the user on the last choices of the size floor (Q903, Q904)

**Status:** absorbed into
[`specs/windows-capture.md#222-rules-of-step-3b`](../../specs/windows-capture.md#222-rules-of-step-3b),
[`specs/windows-capture.md#223-test-list-of-the-encode-at-capture`](../../specs/windows-capture.md#223-test-list-of-the-encode-at-capture),
2026-11-27 (commit to dom/jpeg-encode-tests; was accepted, 2026-11-27 (user, relayed by the supervisor)).

## Decision

The words of the user: "Q903 agree. Q904 agree".

1. **Q903.** Items 7 to 12 of [ADR-YQN1](YQN1-choices-of-the-size-floor.md) are accepted: the tests use
   640x480 and 1280x720 in place of sizes below the floor, and T-RING-40 runs at 640x360 and 100 fps; the
   Quick Sync fallback is kept by camera ID for the app run, through a status flag that is only set to
   True; the two refusal texts ("the requested size WxH is below the smallest size 640x360" and
   "camera X has no mode of 640x360 or more at 30 fps"); the note shows when the width is below 1280 or
   the height is below 720; the Quick Sync test frame is 1280x720.
2. **Q904.** The user checks the tile resize by hand in the real app when he can, and reports a failure.
   This is an action of the user, with no rule.

## Reason

- The user decided both items.
