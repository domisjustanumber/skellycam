# Checking the method of flash_run1_repositioned (method and circularity)

The data is `results/windows/Gerald/timing/flash_run1_repositioned/` (C930e and C922, 1280x720@30 MJPEG, E = 2^-7 s, 30 s).
No camera was opened for this check. The harness is `timing/scripts/flash_verify_method.py`. It imports
`flash_analyze.py` and `tools/analyze_frames.py` as they are, and their sha256 hashes are stored in the output.
The output is `verify_method.json` and `verify_method.log` in the same results directory.

```
uv run --script research/usb_cameras/timing/scripts/flash_verify_method.py \
  --display research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/display_m0 \
  --capture research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture \
  --mjpeg-dir <scratchpad>/runs/flash1/capture --out .../flash_run1_repositioned/verify_method.json
```
The step A numbers reproduce `flash_analysis.json` exactly.

## 1. What the ground truth is

- **There is no displayed QPC timecode.** `flash_timecode.exe` shows a full-screen black/white sequence (a seeded PRNG
  that holds each level for 2 to 6 refreshes). For each present it logs DXGI `GetFrameStatistics`: 468 stats samples
  for 2160 presents. The vblank times are a linear fit `t = a + P*SyncRefreshCount` (residual 10 us std, P = 16.680 ms).
  Each present is placed on the refresh `present_count + (PresentRefreshCount - PresentCount)`, taken from the most
  recent earlier stats sample. A glitch between two stats samples cannot be seen. The log showed `refresh_glitches=0`
  and one `disjoint` at the start.
- Per camera frame, the GT is the **exposure start of the auto-ROI pixels**. The ROI is the 3x6 decoded-pixel block
  that flickers most. The frame must have exactly one display transition T inside the window [X_ref+d0, X_ref+d0+E].
  Then w = T - E(1-f) for a rising edge and w = T - E*f for a falling edge, where f = yn^gamma is the linearised
  brightness. Frames with f outside 0.08 to 0.92 are dropped. The result is n = 96 (C930e) and n = 80 (C922) of
  about 886 frames.
- **Relation to photons.** The GT assumes an instantaneous step at vblank, so these effects are not modelled: display
  scan-out position of the ROI, LCD rise/fall response, camera rolling-shutter row, exposure start vs midpoint
  (E/2 = 3.9 ms), and any constant DWM composition delay. Independent flip on this rotated, non-primary monitor was
  never verified (no PresentMon). Each effect is a per-camera, per-ROI constant that ends up in the "offset".
  Measured size: the same camera and the same timestamp give a GT offset that varies by **35 ms across image blocks**:
  - C922: -78.6 to -43.2 ms.
  - C930e: -76.9 to -41.1 ms.
  - A fit of offset = a + 31 ms*row_frac + 19..25 ms*col_frac leaves 0.5 to 1.2 ms. This data cannot separate the
    rolling-shutter part from the scan-out part.
- **Is the GT independent of the timestamps it judges?** Mostly, but not completely.
  - w uses only T, E and the pixels.
  - The judged timestamps enter in two places: (a) choosing which frames and which transition count, through the
    reference source's window; (b) gamma, which is tuned to minimise the reference source's own error std.
  - `flash_analyze` sets the reference to the best-scoring source (`uvc_pts_via_scr_lsq_envelope` for both cameras).
    So that source is scored on a GT tuned to it, which is why its vs-GT std equals its own fit.
  - Rebuilding the GT with a reference that uses **no device timestamp** (frame index + host-arrival lower envelope,
    `seq_periodic_env`) and a fixed a-priori gamma of 2.2 changes little. That is the non-circular number in the
    table below.
  - The selection does matter when the reference is poor. A GT selected by `host_arrival` yields gross outliers: PTS
    std 3.4 ms but MAD 0.53 ms (C930e).
- **GT model error dominates the 0.5 ms.** With the independent GT, the error of PTS-mapped depends strongly on f.
  The correlation is -0.76 / -0.85 for rising edges and +0.64 / +0.85 for falling edges (C930e / C922). The mean
  error goes from +180 to -1000 us (rising) and from -180 to +550 us (falling) across the range of f, with
  opposite-signed rising/falling means. A timestamp error cannot cause this pattern; it comes from the brightness model.
  - The noise that is independent between blocks (w_A - w_B for the same frame) is only about 135 us per block.
  - Fitting PTS directly to the GT (deliberately circular, best possible line) still leaves 0.49 ms (C930e) and
    0.59 ms (C922).
  - So **about 0.5 ms is the floor of the method on this real data**, not the error of the timestamps. The ~75 us
    synthetic floor in `selftest_flash_analyze.json` comes from a world that matches the model exactly (step display,
    pure power-law tone curve, exact E), so it does not carry over.
- The beat between camera and display limits which frames can be GT frames. For the C922, the beat with 59.951 Hz is
  20.4 s, and 79 of 86 GT frames fall between 6 and 18 s. The GT covers only part of the run.

## 2. How `uvc_pts_mapped_direct` and the SCR variants are mapped

- `uvc_pts_mapped_direct` = `lower_envelope_fit(pts, host_arrival)`: one line (free offset and slope) per camera,
  fitted to host arrival over the **whole 30 s run**. The GT is not used, so the score is not circular. But the fit
  is **non-causal** (it looks back from the end of the run).
- `uvc_pts_via_scr_*_envelope` maps PTS to device SOF through a 32-frame STC/SOF window, then maps SOF to host
  through a whole-run lower envelope of host arrival against device SOF. The same caveat applies.
  - The C922 device SOF runs at 884 per host-second, i.e. the counter is broken (`UVC_QUIRK_INVALID_DEVICE_SOF`).
    It is linear, so the mapping survives.
- **A mapping without hindsight is worse.**
  - C930e: for the first 2 s of the stream, even the *minimum* arrival latency is 22.9 ms higher. After that the
    per-second minimum wanders by 0 to 4 ms.
  - C930e, `lower_envelope_fit` on the first half only, judged on the second half: 3.6 ms std (+1000 ppm slope).
  - C930e, causal (fit on frames 0..i only): 2.7 ms.
  - A robust causal fit (per-second minima, start-up chunks rejected) gives 0.61 ms for C930e and 0.60 ms for C922.
  - C922: plain causal 0.59 ms; first-half holdout 1.13 ms (n = 16).
- PTS at the **nominal clock with only an offset** (no fitted slope) scores 0.55 / 0.59 ms. The fitted slope is not
  what makes PTS score well.

## 3. Std after offset removal: is the comparison fair?

- Only a per-source median offset is removed against the GT, the same way for every source; no slope is fitted
  against the GT. In that sense the comparison of host_arrival with PTS is fair. The PTS line was fitted to host
  arrival, not to the GT.
- **It does not test whether PTS tracks exposure.** It tests whether a source is regular. A pure frame counter
  (`seq_periodic_env`) does the same:

| (independent GT, gamma 2.2, E 7.8125) | C930e std / MAD (us) | C922 std / MAD (us) |
| --- | --- | --- |
| uvc_pts_mapped_direct (whole run) | 531 / 531 | 589 / 501 |
| uvc_pts_via_scr_lsq_envelope | 561 / 485 | 666 / 553 |
| seq_periodic_env (no device timestamp) | 531 / 531 | 584 / 320 |
| pts_nominal_clock (offset only) | 552 / 569 | 589 / 501 |
| pts_chunkmin_robust_causal (online) | 612 / 553 | 597 / 514 |
| host_arrival | 5063 / 5651 | 4657 / 5388 |
| os_timestamp (MF) | 5129 / 5781 | 4752 / 6077 |

  The C930e PTS sits 2.2 us from a perfect periodic clock, so it is identical to `seq_periodic_env`. The C922 PTS
  alternates by about ±0.27 ms, and the counter scores better on MAD (320 vs 501 us). That suggests the alternation
  is not real exposure timing, but it is within the GT floor.
- The gamma used matters more than the source. With gamma 1.0, every PTS source scores 1.7 ms; with 3.0 they score
  1.05 to 1.22 ms (independent GT; corrected 2026-10-28; was 1.05 to 1.18 ms, which left out the C922 SCR variants at 1.22 ms).
- The `per_frame` numbers for host_arrival (2.5 ms) are biased by self-selection: frames whose window misses the
  transition are dropped. The synthetic test shows the same effect, recovering 2.38 ms for an injected 4.6 ms. The
  claim correctly used the `vs_ground_truth` numbers (4.50 / 4.66 ms).

## 4. The periodic-fit residual in analyze_frames

This is regularity only: each source is fitted to a + P*n built from itself. A perfectly periodic source scores 0
whatever its offset or accuracy. For example, the C930e PTS scores 2.2 us and the C922 PTS 137 us, yet both are
equal against the GT. For the C930e the periodogram locks onto the wrong period for host_arrival and os_timestamp
(32.42 fps, 69 "skipped" slots), so those residuals (5.1 ms) and `drops_est` = 27 to 30 are artefacts. Missing
frames are better judged from PTS slots, which show 0 gaps and slot == seq for both cameras.

## 5. Units and clock domains

- QPC runs at 10 MHz, so ns = ticks*100 exactly. The display, MF sample time (100 ns) and arrival time are all QPC.
  This checks out.
- **dwClockFrequency was not read from the descriptors.** The nominal clock is guessed as the nearest round
  frequency: 30 MHz for the C930e and 300 MHz for the C922 (`nominal_assumed: true`).
- The GT gives an independent PTS rate: 30,001,037 Hz (C930e, +35 ppm) and 299,998,822 Hz (C922, -3.9 ppm). The
  arrival envelope differs from it by +28 ppm (C930e, 0.84 ms over 30 s) and -4 ppm (C922).
- The C930e `device_vs_host_ppm = +393` in `frames_analysis.json` is wrong: the OLS fit is biased by the 21 ms
  start-up latency regime. STC - PTS also steps from 51 to 31 ms in the first ~5 s.
- At 300 MHz the C922 PTS wraps every 14.3 s. The unwrap handles this because the steps are 1e7 << 2^31.

## 6. Cross-camera agreement ("offsets agree to 0.02 ms")

- The numbers quoted (-52.08 / -52.10) are the coarse correlation offsets, searched on a **0.02 ms grid**.
- The GT median offsets differ by 0.064 ms, CI95 [-0.11, 0.26] (flash_analyze GT; corrected 2026-10-28; was [-0.10, 0.27]), or by 0.19 ms, CI95 [-0.04, 0.32]
  (independent GT).
- host_arrival also agrees (0.10 ms, but CI95 of about ±2.5 ms), so this agreement does not single out the best
  source.
- The per-camera offset moves by 35 ms with ROI position (section 1), and the two auto-ROIs sit at different
  image rows and columns (C930e row 0.93 col 0.27; C922 row 0.62 col 0.98). The near-zero difference is therefore a
  property of where the ROIs happen to be, not a measured sync accuracy.
- The online mapping gives a different cross-camera offset: -0.30 ms (robust causal) or +4.1 ms (plain causal
  envelope).
- One 30 s run with one pair of cameras of the same family cannot support "best source for multi-camera sync".
  Measuring that needs a light source with no scan-out (LED), or both cameras imaging the same screen patch on the
  same sensor rows, plus repeated runs.
