# TFD7 — Search limit, median stop rate, role flag, no restart at a live change, restore after a failed loop

**Status:** absorbed into
[`specs/camera-requests.md#13-the-search`](../../specs/camera-requests.md#13-the-search),
[`specs/recorder.md#82-the-stop-response-r5`](../../specs/recorder.md#82-the-stop-response-r5),
[`specs/certify.md#191-the-first-code-u`](../../specs/certify.md#191-the-first-code-u),
[`specs/windows-capture.md#83-what-each-state-allows`](../../specs/windows-capture.md#83-what-each-state-allows),
[`specs/unix-capture.md#47-restore-of-the-controls-at-the-close-u`](../../specs/unix-capture.md#47-restore-of-the-controls-at-the-close-u),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-21 (user; the items B1, B2, B7, B8 and B9 of a sheet of open choices, to which
the user answered "agree to all"; commit to dom/accept-choices)).

## Decision

The user decided these items on 2026-11-21. No other entry holds them. Items 2 to 5 are decided, not built.
open-work.md does not list them: the read path is full.

1. **The limit of the exposure search stays 20 s** (B1; [`camera-requests.md`](../../specs/camera-requests.md)
   1.3 item 2.7). The user does not raise it now.
2. **The frame-rate statistic of the stop response becomes a median, not a mean** (B2;
   [`recorder.md`](../../specs/recorder.md) 8.2). The sheet does not name the field. The work that builds this
   item names it. Decided, not built.
3. **An explicit role flag replaces the `parent_process()` guards** (B7; question 5 of
   [ADR-X8XE](X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md)). `managed_worker` sets the flag in
   each camera process, and the guards read it. Then certify drops the workaround of item 5 of ADR-X8XE (item 10
   of [ADR-VG5F](VG5F-choices-of-the-first-certify-code.md)). Decided, not built.
4. **A live change of the settings never restarts a failed camera** (B8). Today it does. Decided, not built.
5. **A camera whose capture failed for a reason other than a hang gets its own settings back at the close**
   (B9). Today the close does not restore it. Decided, not built.

## Reason

1. On the lab cameras a search takes 9 to 11 s. On the fake timeline, a search where each value is measured two
   times takes about 19 s ([ADR-NYT6](NYT6-choices-of-fix-lane-2.md), evidence 1).
2. One time, after a camera process was killed, the statistic gave a mean of 136 fps. A few wrong intervals do
   not move a median.
3. Certify must clear the parent mark of its session child, because the guards read the parent of the process. A
   flag tells the role directly.
4. Without this rule, certify cannot fully keep a wedged camera safe (ADR-X8XE, "Open work").
5. Without it, the camera keeps the settings of this app after the app closes it.

## Evidence

5. `skellycam/core/camera/capture/camera_loop.py`: the close calls
   `self.source.close(restore=not self.failed or self.lost_heartbeat)`, so a failed loop gets no restore. The
   author of the certify code found it.
