# FTC3 — Fixes of the second capture CI run and of the first hardware run of step 3a

**Status:** proposed, 2026-11-20 (agent; waits for the user).

## Decision

The second run of `.github/workflows/capture.yml` (6d496aa24) failed T-CAP-86 on Linux, T-CAP-108 on
macOS and T-CAP-85 in the macOS timing step. The first hardware run found four more faults. An agent
made these choices. The user decides them.

1. **T-CAP-108, test.** A forced step of `VirtualClock` moved the time to the earliest wake time.
   When the live loops were busy for 50 ms of real time, that was the end of the 2 s close of the dead
   camera, so the live cameras showed a gap of 1967 ms. A forced step is now 10 ms at most. The
   product order is correct: the check "dead before the close" of the test passed on macOS, and the
   test runs THREAD workers on each system.
2. **T-CAP-86, test (probable cause).** While the reopened camera held, the test thread was not a
   participant of the clock. When it did not run, the two other loops moved the virtual time alone,
   past the 15 s ready limit. The test thread now joins the clock before the reopen and leaves it when
   the held camera runs again. The test prints the virtual times of the reopen for the next CI log.
3. **T-CAP-85, macOS (probable cause: the product on a slow machine).** The interim recorder encodes in
   the camera loop. On the macOS runner the other camera replaced 147 and 286 frames, against 27 and
   26 on Windows. The 100 ms limit (U16) stays, and the test fails on that runner. Its message now
   gives the place of the gap, the frames that the test could not read and the replaced count. The
   user can choose: (a) the promise holds only on a machine that records at the full rate; (b) the
   macOS timing step can fail until the recorder of phase 5 leaves the loop; (c) keep the step red.
4. **Timing files, product.** The multi-frame timing file and the statistics files give no value for a
   column that the camera files leave out (D41): `nan` in the CSV (the marker of that file for no
   value), null in the JSON and `nan` in the text report. The stage total of the text report adds
   only the stages with a value.
5. **`measured_fps` after `too_slow`, product.** The early decision of 10.2 now sets `measured_fps` to
   the rate of the window up to the decision: (s - s_a) / (t - t_a), with the late frame, or with the
   last delivered frame and the time of the decision. The deadline rule puts it below the limit.
6. **Virtual cameras, product.** Media Foundation detection marks a camera virtual when its name holds
   "virtual" (the old rule), or its link starts with `\\?\root#` or `\\?\swd#vcamdevapi#`. Each other
   link stays real. If the user accepts, the words "its friendly name contains virtual" of 7.1 must
   change.
7. **T-CAP-51, test.** The test counts the cameras that are not virtual and that have a label of the
   harness. The other criteria do not change.

Not changed, for the user: T-CAP-60 checks `mean_framerate`, the mean of 1/interval, which read 30.6
(limit 30.3) while the rate by elapsed time was 29.98. The proposal is to check the rate by elapsed
time.

## Reason

- Items 1, 2 and 7: the test was the faulty side. Each criterion stays.
- Item 3: the gap is a product limit of the old recorder, not of the hang isolation. A smaller test
  does not change the product.
- Items 4 and 5: a file or a status must not show a number that nobody measured.
- Item 6: the four NDI cameras of the development machine have links in the media class under the
  root of software devices, with no USB IDs and no modes. The four real cameras have USB links with
  vendor and product IDs. A built-in camera has a bus link (`pci#`, `acpi#`, `display#` or `usb#`).

## Evidence

- Item 1: an 80 ms sleep in each frame of the live loops during the close gives 1967 ms on the
  development machine, as on macOS. With the fix the gap is below 100 ms. A self-test in
  `test_helpers.py` checks the step.
- Item 2: a 1 s sleep of the test thread before the collection gives "not ready in 15 s", as on Linux.
  With the fix the camera holds for 0.8 s of virtual time.
- Item 3: the counts come from the stop lines of the two CI cases and of the same test on Windows.
  The ring holds 1 s, so a frame is lost to the test only after a stall of the watcher of 1 s.
- Item 4: without the fix, the new fake-source test reads -1003633 ms. It checks the absence of a
  value, so the clock value of the machine does not change the result.

## Alternatives rejected

- Item 1: a longer `fallback_s`. A slow machine can pass any value.
- Item 3: `xfail` or a larger limit. They hide a product limit.
- Item 4: a redesign of the files. The recorder of phase 5 replaces them.
- Item 6: each `swd#` link. A sensor group of the frame server can join real cameras under that root
  (not verified). An empty `supported_modes`: a real camera can fail to give its list.

## Open work

See [open-work.md](../open-work.md).
