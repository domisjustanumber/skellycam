# HQE5 — Choices of fix lane 4: spawn on Linux, the skip guard, the slow stop, pace tests, the restore file, the take rate

**Status:** proposed, 2026-11-23 (agent; the supervisor gave the items after CI run 45214740615 and a real-camera
run).

## Decision

The decisions of the user that these choices build are in
[ADR-81RE](81RE-decisions-of-the-user-on-the-restore-file-the-take-rate-and-pace-tests.md). The questions Q-A, Q-B
and Q-C go to the user with the review of this work.

1. **Camera processes start with `spawn` on each system** ([`unix-capture.md`](../../specs/unix-capture.md) 4.12).
   `skellycam/__init__.py` sets the start method `spawn` when no start method is set, before any shared object is
   made. A host program that set a start method keeps it. `CameraStatus.retired` keeps each array that
   `reset_for_start` replaced, because a spawned camera process opens each shared array by its name while it
   starts.
   Not: `fork` with `gc.freeze()` before each start (it stops this one deadlock, not the next library with
   threads). Not: a `spawn` context object in each product call (37 calls; the log queue of `skellylogs` uses the
   default context).
2. **The skip guard** (unix-capture.md 4.11). `SKELLYCAM_NO_SKIP` holds test paths. A skip under one of them
   fails the run (`skellycam/tests/skip_guard.py`, root `conftest.py`). The recorder workflow sets it to
   `test_connection.py`. The capture and recorder workflows also run on each push to `dom/integration`.
   Not: a minimum count of passed tests (it changes with each new test).
3. **The slow stop** ([`recorder.md`](../../specs/recorder.md) 8.1 step 1, 12.1). The fault is in the test, not in
   the product. While the stop holds the lock of the last frame, a camera that decides a frame waits, and a camera
   at the gate reads no frame, so a push source loses frames. The gap is true and can come only on the last row of
   a camera. The test accepts a `camera_gap` on the last row only, and no other warning.
   Not: no lock in the decision of a frame below the last frame (the protocol of round 4 changes, for a hold that
   is microseconds long outside a test).
4. **Pace tests (Q-C)** ([`windows-capture.md`](../../specs/windows-capture.md) 16.1). The marker `pace`. Each
   workflow runs `-m "... and not pace"` in its blocking step and `-m "... pace ..."` in a step with
   `continue-on-error: true`, `if: ${{ !cancelled() }}`, `SKELLYCAM_PACE_MARGIN: "3"`, a warning annotation and the
   summary lines in the job summary. `skellycam/tests/pace.py` gives `margin()`; a test multiplies the tolerance of
   each bound, never the nominal value. The marked tests: T-UNX-26, T-UNX-76 (two tests), the hanging restore of
   F7, T-RING-12, T-RING-23 and the slow stop. The entries of fix lanes 1 to 3 name them as pace failures of a
   runner. A test of item 1 has no marker.
   Not: `xfail(strict=False)` when `GITHUB_ACTIONS` is set (a failure shows only as an `x` in the log, not on the
   run page). Not: a skip on CI (no report at all).
5. **The restore file (Q-A)** (unix-capture.md 4.7.1). One file `<key>.json` for each camera in `camera_restore`
   of the data folder of the app (the folder of `camera_checks.json` and of the logs, from
   `get_default_skellycam_base_folder_path()`). The key is the SHA-256 (hex) of the input of the `camera_id`
   hash. The form: `version` 1, `key`, `vendor_id`, `product_id`, `written_utc`, `record`. The camera process
   writes it at each write of the record (temporary file, then `os.replace`) and removes it when the record is
   empty. The main process reads it at a group creation for a camera with no record in memory, and removes each
   entry that it drops. An entry is used only when its camera has the same USB IDs and, with two or more detected
   cameras of that model, a stable identity (serial number, `id-path`, `unique-id`, `mf-link` or a Media
   Foundation link). A damaged file is logged one time and removed. A write error never fails an open. No age
   limit. Only the server of the app gives a folder; certify and the tests give none.
   Not: one file for all cameras (two camera processes would read, change and write one file). Not: the
   `camera_id` or the link as the name (a link can hold a serial number). Not: an age limit of 30 days (it drops
   a valid entry; the value rule is the guard). Not: the main process as the writer (it sees a set only at its
   next poll, and a kill in that time loses the write).
6. **The take rate (Q-B)** (recorder.md 8.2). `mean_framerate` is ΣF_i / ΣT_i over the cameras: F_i is the row
   index of the last row with a time minus the row index of the first, T_i the time between their arrivals. The
   name stays; the API description says that it is the rate of the take, and that `framerate_stats` holds the
   figures of each frame interval.
   Not: the mean of F_i / T_i (a camera killed after two frames 1 ms apart gave 1000 fps for itself). Not: the
   count of rows with a time minus 1 for F_i (a camera with `missing` rows in a running group would read low).
   Not: the median over the cameras (with two cameras it is the mean).

## Reason

1. A fork of a process with threads can deadlock in each library with threads. The deadlock of the evidence (PyAV and FFmpeg) is one case.
2. The green recorder run of 2026-11-20 (run 44676423645) skipped each test of `test_connection.py`: the file was
   the placeholder of the connection commit, with a module skip. The connection tests first ran on Linux on
   2026-11-23.
3. A real gap is not a fault; a red workflow must mean a real fault (Q619).
4. The failures of the pace tests on hosted runners had no product fault (the entries of fix lanes 1 to 3).
5. Q608; the camera process sets the controls, so it writes at the moment of the set.
6. Q609; ΣF / ΣT weighs each camera by its time.

## Evidence

The CI logs, the reproduction under WSL and the stack of the hung camera process are in
[evidence/HQE5-fix-lane-4-evidence.md](../evidence/HQE5-fix-lane-4-evidence.md).

## Open work

[open-work.md](../open-work.md)
