# HQE5 — Choices of fix lane 4: spawn on Linux, the skip guard, the slow stop, pace tests, the restore file, the take rate

**Status:** proposed, 2026-11-23 (agent; the supervisor gave the items after CI run 45214740615, a real-camera run
and a review).

## Decision

The decisions of the user are in
[ADR-81RE](81RE-decisions-of-the-user-on-the-restore-file-the-take-rate-and-pace-tests.md). Q-A, Q-B and Q-C go to
the user with the review.

1. **Start method** ([`unix-capture.md`](../../specs/unix-capture.md) 4.12; the route is the decision of the user
   in [ADR-T34M](T34M-decision-of-the-user-on-the-start-method-of-camera-processes.md)). The check is in
   `CameraWorker.start`: `failed`, stage `open`, code `start-method-fork`, a reason that names
   `set_start_method('spawn')`; on each system, not only Linux. `forkserver` starts (its children come from a
   clean server process). The root `conftest.py` sets `spawn` first. `retired` keeps two generations; certify's
   `_ChildSession` reads the sentinel. Not: only a warning (a forked camera never answers).
2. **Skip guard** (4.11). `SKELLYCAM_NO_SKIP`; run reports and collect reports. Not: a minimum test count.
3. **Slow stop** ([`recorder.md`](../../specs/recorder.md) 8.1, 12.1). A fault of the test: a camera at the gate
   during the hold of the last-frame lock loses frames of its push source, a true gap on the last row. The test
   allows a `camera_gap` on the last row only and blocks. Not: no lock in a frame decision below the last frame.
4. **Pace tests (Q-C)** ([`windows-capture.md`](../../specs/windows-capture.md) 16.1). A `pace` test holds only
   its bounds of time; its other checks block. Steps: `-m "... and not pace"` blocks; the pace step has
   `continue-on-error`, `SKELLYCAM_PACE_MARGIN: "3"`, a warning and the job summary. The margin multiplies the
   tolerance only. Not: `xfail(strict=False)` on CI (it shows only as an `x`). Not: a skip on CI.
5. **Restore file (Q-A)** (4.7.1). `camera_restore/<key>.json` in the data folder of the app. The key is an
   HMAC-SHA-256 of the stable identity input (Media Foundation link, AVFoundation unique ID, the Linux USB
   interface in sysfs) with a salt in `.salt`. The camera process writes and removes its file; the main process
   reads, checks the USB IDs and the form, and removes what it drops. Only the server of the app gives a folder.
   Not: one file for all cameras (read, change, write by two processes). Not: a plain SHA-256 (the same name on
   each machine; a short serial number can be found by a search). Not: `/dev/video<n>` as input (its number
   changes). Not: an age limit of 30 days (the value rule is the guard). Not: the main process as the writer (a
   kill between a set and its poll loses the write).
6. **Take rate (Q-B)** (recorder.md 8.2). `mean_framerate` is ΣF_i / ΣT_i; F_i is the row index span of the rows
   with a time. Q609 does not change B2 of
   [ADR-TFD7](TFD7-search-limit-stop-rate-median-role-flag-and-restore-after-a-failed-loop.md): B2 named no field,
   and it applies to `framerate_stats`, the figures of each interval. Thus no entry supersedes TFD7.
   Not: the mean of F_i / T_i (a camera killed after two frames 1 ms apart gave 1000 fps). Not: the count of
   timed rows minus 1 (a camera with `missing` rows reads low). Not: the median over the cameras.

## Reason

1. A fork of a process with threads can deadlock in each library with threads (the evidence: PyAV and FFmpeg).
2. Run 44676423645 skipped all of `test_connection.py` with a module skip.
3. A real gap is not a fault; a red workflow must mean a real fault (Q619).
4. The pace failures on hosted runners had no product fault (fix lanes 1 to 3).
5. Q608; the camera process sets the controls, so it writes at the moment of the set.
6. Q609; ΣF / ΣT weighs each camera by its time.

## Evidence

[evidence/HQE5-fix-lane-4-evidence.md](../evidence/HQE5-fix-lane-4-evidence.md).

## Open work

[open-work.md](../open-work.md)
