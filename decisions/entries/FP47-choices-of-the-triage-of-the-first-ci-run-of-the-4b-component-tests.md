# FP47 — Choices of the triage of the first CI run of the 4b component tests

**Status:** proposed, 2026-11-27 (agent: the CI triage lane of the preview 4b tests, Q912).

## Decision

The first CI run of the 4b component tests (run 45947082026 on 67151ce86) failed T-PRV-43 on ubuntu-24.04, and
T-PRV-43, T-PRV-47, T-PRV-48 and T-PRV-49 on windows-2025. Each failure is a fault of the test harness, not of the
product. The fix changes no check and no limit.

1. **The cause.** The harness window is 1400 x 1000, and the grid of the page `preview` is 1380 pixels wide. A
   runner screen is smaller. Windows cuts a larger window to the screen: the rightmost tile is outside the window,
   and the observer reads no image of its own camera there (CI: "camera 2 frame 0" for each capture of c3). Under
   xvfb, the part of the window past the right edge of the screen is not drawn: the cells of the low bits of the
   frame number of the rightmost tile stay still (CI: the frame of c3 changes in 6.8 % of the captures; four
   still bits give 6.25 %). The failing tile is always the rightmost one: c3 (T-PRV-43), r1 (T-PRV-47), A
   (T-PRV-48), h1 (T-PRV-49).
2. **The fix.** The harness window fits the work area of the screen, at most 1400 x 1000; the grid and the viewer of
   the page `preview` fit the window. `PLAYER_HARNESS_MAX_WINDOW=<width>x<height>` gives the screen of a runner on a
   larger one, for a local check. The launch line of the harness gives the inner size of the window, so that a CI
   log shows it. Spec 7.2 of [`specs/preview-4b.md`](../../specs/preview-4b.md) states it.
3. **Not a product fault.** No product code changes. Two mutations of `PreviewTiles` (the rightmost tile gets no
   update; it gets updates only one eighth of the time) make T-PRV-43 fail with the fix at a 1036 x 780 window.

## Reason

Q912: fix a fault of the test harness in a lane with a review, with no looser check.

## Evidence

- A local reproduction (Windows test machine, Electron 45.3.4): with the window set to 1036 x 780 (the window that a
  1024 x 768 screen allows), T-PRV-43's c3 reads "camera 2 frame 0" in each of 59 captures, as on the Windows runner;
  at 1400 x 1000 each tile changes in 59 of 59 captures.
- With the fix, T-PRV-43, T-PRV-47, T-PRV-48 and T-PRV-49 pass at the screen size, at 1036 x 780 and at 1280 x 1024.
- Not verified: the screen sizes of the runners (1024 x 768 on Windows, the xvfb default of 1280 x 1024 on Linux)
  are inferred from the failure signatures; the inner size in the launch line shows them on the next CI run. The
  xvfb case (a window past the screen edge that is not drawn) did not reproduce on the test machine, which has a
  GPU.

## Open work

See [open-work.md](../open-work.md).
