# 81RE — Decisions of the user on the restore file, the take rate and the pace tests (Q608, Q609, Q619)

**Status:** absorbed into
[`specs/unix-capture.md#471-the-restore-record-on-disk-u-q608`](../../specs/unix-capture.md#471-the-restore-record-on-disk-u-q608),
[`specs/recorder.md#82-the-stop-response-r5`](../../specs/recorder.md#82-the-stop-response-r5),
[`specs/windows-capture.md#161-kinds`](../../specs/windows-capture.md#161-kinds),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-23 (user; the supervisor asked the questions and relayed the answers)).

## Decision

The user decided these items on 2026-11-23. The words of the user: "Q607-Q609 agree" and "Q619 agree". Q607 was
the push of a branch, not a decision of this log. The questions that the user agreed to:

1. **Q608.** "Keep the restore record on disk: The server writes each camera's "before" settings to a small file
   when it sets a control, and removes the entry after a successful restore. A new server reads the file. This makes
   the restore survive a server kill or a crash. Yes?"
   [`unix-capture.md`](../../specs/unix-capture.md) 4.7.1 states it.
2. **Q609.** "Frame rate statistic: The headline rate of a take becomes frames divided by elapsed time. The median
   stays only for the per-frame interval figures. Yes?" [`recorder.md`](../../specs/recorder.md) 8.2 states it.
3. **Q619.** "Timing tests on CI: Tests that depend on pace or wall-clock limits get a marker. On GitHub runners
   they run with wide margins and a failure there is reported but does not turn the workflow red; on a real
   machine they run strict. Yes?" The principle, which the user agreed to: "A red workflow should mean a real
   fault". [`windows-capture.md`](../../specs/windows-capture.md) 16.1 states it.

The choices of the agent that build these items are in [ADR-HQE5](HQE5-choices-of-fix-lane-4.md) (proposed).

## Reason

1. A real-camera run of 2026-11-23: after a kill of the whole server, a new server took the manual value of this
   app as the camera's own value, and three cameras stayed in manual exposure.
2. The same run: `framerate_stats.median` read 31.24 for a take at 30.02 fps, because the arrival times fall on a
   grid of 16 ms.
3. CI runs on hosted runners failed on tests whose limits of time do not hold on a slow runner, with no fault of
   the product.

## Open work

[open-work.md](../open-work.md)
