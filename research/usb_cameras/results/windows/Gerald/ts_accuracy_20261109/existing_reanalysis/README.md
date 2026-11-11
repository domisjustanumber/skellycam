# Tier-0 timestamp accuracy: re-analysis of existing data

2026-11-09, Gerald. No camera was opened, and no existing result file or snapshot was changed. Scripts are in [`timing/ts_accuracy/`](../../../../../timing/ts_accuracy/). Paths below are relative to `research/usb_cameras/` unless they start with `C:/`.

Labels: **measured** = a file in this folder supports it; **inferred** = reasoning only.

## 1. What data exists

| Data | Per-frame flash ground truth (GT)? | Camera clock? | Used for |
| --- | --- | --- | --- |
| `results/windows/Gerald/timing/flash_run1_repositioned` (2026-10-25, C922 + C930e, MF, 30 s) | **Yes.** It is the only flash run whose raw MJPEG still exists (`C:/Users/Dom/Documents/skellycam-raw/...`) | PTS/SCR | §2, §5 |
| `timing/rerun_20261027/flash/*` (2026-10-28, 9 runs: C922 with the C930e or the generic camera) | **No.** The MJPEG was deleted with its scratchpad; only the stored aggregates remain | PTS/SCR (C922, C930e); none for the generic camera | §3 (camera clock), §5 (aggregates) |
| `C:/Users/Dom/Documents/skellycam-raw/results/windows/Gerald/suite_20261106T*/W-TS` (wincam MF and DirectShow, 4 cameras) | No | C922 and Kiyo (MF only) | §3, §4 |
| Any OpenCV/DirectShow stamps of the kind skellycam writes | **None** with GT or a camera clock | — | not scorable |

There is no LED or sync-rig data with real cameras. `rig_anchor_selftest` is synthetic.

## 2. Per-frame flash GT (one run, two cameras)

`flash_gt_perframe.json`. GT frames: C922 n = 85 (6.5–29.5 s), C930e n = 95 (0.06–27.6 s; 4 frames before 3 s). Each error is stamp minus GT exposure start of the ROI rows. Std, p95 and max are taken after removing the mean. The frame-selection reference is `seq_env`, which uses no device timestamp. A second GT, which selects frames with PTS (tier 1, used only for selection), changes the stds by ≤ 30 µs.

| Method (tier 0 unless marked) | C922 offset ms | std µs | p95 µs | max µs | C930e offset ms | std µs | p95 µs | max µs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (i) MF sample time, raw | 54.4 | 4784 | 8186 | 8567 | 57.9 | 5155 | 7949 | 23387 |
| (ii) MF QPC arrival, raw | 59.5 | 4713 | 7684 | 9095 | 60.5 | 5089 | 7915 | 21451 |
| (iii) lattice on sample time, least squares | 54.3 | 607 | 1396 | 1883 | 59.3 | 2790 | 4932 | 5563 |
| (iii) lattice on sample time, robust lower envelope, whole run | 46.6 | 564 | 1327 | 1626 | 48.5 | **2007** | 3528 | 4262 |
| (iii) lattice on sample time, P from whole run, offset from 10 s centred window | 46.6 | 564 | 1323 | 1626 | 49.1 | 668 | 1185 | 2391 |
| (iv) lattice on arrival, least squares | 59.6 | 564 | 1299 | 1605 | 62.0 | 2712 | 4793 | 5419 |
| (iv) lattice on arrival, robust lower envelope, whole run | 52.2 | 564 | 1297 | 1610 | 51.9 | 536 | 1085 | 1310 |
| (iv) lattice on arrival, P from whole run, offset from 10 s centred window | 52.2 | 561 | 1298 | 1589 | 52.0 | 519 | 1107 | 1361 |
| (iv) lattice on arrival, causal (trailing 10 s window, expanding P) | 52.3 | 565 | 1258 | 1557 | 48.8 | 3322 | 6247 | 9561 |
| (v) tier 1 ref: PTS mapped to the arrival envelope | 52.1 | 564 | 1249 | 1658 | 51.9 | 536 | 1081 | 1309 |
| (v) tier 1 ref: PTS via SCR (lsq) | 19.1 | 630 | 1386 | 1838 | 20.9 | 564 | 1250 | 1901 |

**Measured:**
- Raw MF stamps score 4.7–5.2 ms std. That is the 16 ms delivery grid, since 16/√12 = 4.62 ms. The p95 is 7.7–8.2 ms. The C930e max of 21–23 ms is its start-up latency step (+22.8 ms in the first ~2 s).
- The best tier-0 lattice scores 0.52–0.56 ms std, 1.1–1.3 ms p95 and 1.3–1.6 ms max. That equals tier-1 PTS (0.54–0.56 ms) and the method floor (~0.5 ms, [VERIFY_method.md](../../../../../timing/VERIFY_method.md) §1). So the true error of the best tier-0 fit is **≤ ~0.55 ms**, an upper bound, and about **9×** better than raw.
- **The estimator matters on the C930e.** With a plain least-squares slope, the start-up latency step pulls the slope and gives 2.7–2.8 ms. The robust whole-run envelope fit on *sample time* settled on a slope about 290 ppm off and gives 2.0 ms. The arrival fit and the two-stage fit (long-window P, windowed offset) reach the floor. On the C922 every variant gives 0.56–0.61 ms.
- Causal fits are fine on the C922 (0.57–0.75 ms) and poor on the C930e (2.4–3.4 ms, still 2.4–3.0 ms after 3 s), because the first seconds are what the slope is learned from.

**Window length** (std µs, two-stage fit with q = 0.02):

| | 2 s | 5 s | 10 s | 20 s | whole run |
| --- | --- | --- | --- | --- | --- |
| C922 arrival, centred / causal | 564 / 566 | 559 / 563 | 561 / 565 | 561 / 566 | 564 |
| C922 sample time, centred / causal | 563 / 581 | 563 / 744 | 564 / 745 | 565 / 731 | 564 |
| C930e arrival, centred / causal | 2263 / 3062 | 1339 / 2995 | 519 / 3322 | 486 / 3427 | 536 |
| C930e sample time, centred / causal | 2223 / 2594 | 1546 / 2676 | 668 / 2596 | 1018 / 2351 | 2007 |

Windows of 10 s or more, or the whole run, fitted offline, are needed when a camera has a latency step at start-up. Full refits of the slope inside short windows are worse; see `summarize.log` T2.

**Envelope quantile** (q = 0, 0.02, 0.05, 0.10): the std does not change, but the constant offset moves by 1.3–1.6 ms (C922) and 2.6–6.1 ms (C930e) between q = 0 and q = 0.10 (`summarize.log` T3). Every camera must use the same q, or q becomes an inter-camera bias.

## 3. Camera-clock reference (random error only; constant bias unmeasured)

`camera_clock_scores.json`, 46 entries. The camera clock is read through the tier-1 registry value, which is currently set on Gerald. It is used here **only as a measuring reference**, never as part of a tier-0 method. The slope is fixed per camera at the median rate over all its runs, so it does not depend on the run's own host stamps:
- C922 STC: −1.6 ppm vs nominal.
- C922 PTS: −0.2 ppm.
- C930e PTS: +39.9 ppm. The GT-derived rate in VERIFY §5 is +35 ppm.
- Kiyo: one run only.

Per-run envelope slopes scatter by up to 50 ppm (296 ppm for the fragile estimator), so a per-run reference would add up to ~0.7 ms of slope error. Stats cover frames from 3 s onward. Values are the median [min–max] over runs of std in µs.

| Camera / reference (runs) | series | raw | LSQ lattice | robust whole run | 2-stage, 2 s | 2-stage, 10 s | 2-stage, 20 s | causal 10 s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C922 / STC (12) | sample time | 4611 [4604–4659] | 51 [5–499] | 17 [2–517] | 18 [9–659] | 17 [7–660] | 17 [6–666] | 240 [186–570] |
| C922 / STC (12) | arrival | 4934 [4596–5017] | 53 [3–208] | 43 [2–355] | 710 [30–927] | 345 [17–587] | 133 [11–420] | 489 [52–722] |
| C930e / PTS (8) | sample time | 4654 [4618–4721] | 107 [13–2862] | 96 [44–1971] | 448 [191–742] | 211 [123–440] | 100 [32–972] | 335 [201–3376] |
| C930e / PTS (8) | arrival | 4664 [4640–4730] | 90 [20–2817] | 53 [1–300] | 432 [227–714] | 145 [74–309] | 60 [42–204] | 340 [225–4107] |
| Kiyo / PTS (1) | sample time | 4627 | 1637 | 1652 | 1729 | 1660 | 1665 | 1639 |
| Kiyo / PTS (1) | arrival | 4643 | 1876 | 1648 | 1739 | 1658 | 1633 | 6018 |

**Measured:**
- Against the camera's own frame clock, a whole-run tier-0 lattice usually tracks within 0.02–0.15 ms. Its worst runs reach 0.35–0.5 ms, plus the C930e outliers explained in §2.
- Arrival-based windowed fits wander by 0.3–0.7 ms, because the minimum arrival latency drifts over tens of seconds (consistent with the 50 ppm envelope-slope scatter). On the C922, sample time is the steadier source. On the C930e, arrival is.
- The C922 PTS alternates (cadence residual 120–166 µs), which puts a ~0.12 ms floor on every C922/PTS score. Its STC is 2 µs regular.
- **The Kiyo's own cadence is irregular** (PTS lattice residual 1.64 ms; the PTS counts in 1 ms units, which adds about 0.29 ms of that). No lattice can follow it: tier 0 reaches only 1.6–1.9 ms, about a 2.8× improvement. Whether the PTS marks exposure is unknown (windows_results_20261106 §4).

## 4. Drops, frame rates, DirectShow

**Measured:**
- **No run has a real drop** according to the camera clock (C922, C930e: 0 missing slots in 20 MF runs). So only false positives can be scored. Tier-0 slotting gave **0 false drops** on the C922 and C930e in all 20 runs.
- **False drops seen elsewhere:**
  - On the generic camera, MF sample time gives one false "drop" at frame 0 in 3 of 4 runs: the first interval is 80 ms while arrival shows a normal interval.
  - On the Kiyo, MF arrival gives 2 false drops from start-up bursts (62 ms then 1 ms). A late-delivery rule (a long interval followed by a short one) removed 2 of the original 4.
  - True-positive drop detection is **untested**.
- **Frame rate.** The generic camera runs at 25.76 fps. The lattice fitted P = 38.82 ms from host stamps alone, with no dependence on the other cameras' rates. Nothing in the method assumes a common frame rate.
- **DirectShow (wincam ds), regularity only, no reference:**
  - DS arrival lies on the same grid as MF: the residual to its own lattice is 4.60–4.64 ms on the C922, C930e and generic camera.
  - DS pts are synthesized (residual 0, or 0.19 / 2.9 ms on the C930e, which had one real 65 ms gap).
  - The Kiyo DS capture (10 detected gaps, residual 4.9 ms) was the YUY2 fallback.
- **OpenCV/DShow, and how skellycam stamps frames today, has no data in this study.** A lattice on DS arrival stamps would *probably* reach a similar class to MF arrival. That is **inferred**: it assumes DS delivery latency behaves like MF's, which is untested. OpenCV's post-retrieve stamp also includes the MJPEG decode.

## 5. Inter-camera constant bias (not removed by any tier-0 fit)

| Comparison | Source | Value (ms) | File |
| --- | --- | --- | --- |
| C930e − C922, flash_run1, auto ROIs (rows 0.93 / 0.62) | raw arrival / raw sample time | +0.97 [CI −0.45, 2.37] / +3.49 [2.08, 4.97] | `flash_gt_perframe.json` `inter_camera` |
| same | robust lattice on arrival / PTS (tier 1) | −0.30 [−0.46, −0.14] / −0.18 | same |
| same, corrected to the middle row (readout 31 / 30 ms) | arrival lattice / raw arrival | +8.9 / +10.2 | same |
| C930e − C922, 6 valid re-run runs, auto ROI | raw arrival | 4.4, 10.4, 18.3, 24.6, 27.1, 30.7 (mean 19.2, sd 10.2) | `existing_gt_aggregates.json` |
| same | seq_envelope (arrival lattice) | 5.6–33.8 (mean 18.5, sd 11.2) | same |
| C930e − C922, fixed row 0.5 (1 run, exp-7_e) | arrival / arrival lattice | +12.8 / +13.2 | same |
| generic − C922, fixed ROI (2 runs) | arrival / arrival lattice / **MF sample time** | −7.1, −7.7 / −4.1, −5.6 / **−33.4, −33.9** | same |
| GT-free: MF arrival − MF sample time (median per run) | — | C922 0.23–0.80, C930e 0.18–0.65, Kiyo 0.61, **generic 32.2–32.5** | `camera_clock_scores.json` / `summarize.log` T6 |

**Measured:**
- The per-camera constant offset differs between models by **several ms up to ~30 ms**, and it is not stable across runs (C930e − C922 sd 10 ms over 6 runs).
- **The generic camera's MF sample time is stamped ~32 ms (one frame) earlier relative to arrival than on the Logitech cameras or the Kiyo.** This needs no GT. Mixing raw MF sample times across models therefore adds a one-frame inter-camera bias. Arrival-based stamps and lattices do not have this shift.

**Not measured:** the true C930e − C922 bias. The flash method cannot separate it from the ROI's screen position (display scan-out, up to 16.7 ms), the ROI's rolling-shutter row (~31 ms per frame height), the C930e's unconfirmed exposure (REPORT finding 11), and exposure-start vs mid-exposure (E/2). The run-to-run spread is about as large as the effect. An LED rig is needed (REPORT next step 7).

## 6. Caveats

- **Sample size.** Per-frame GT covers one 30 s run, two cameras, and 85/95 GT frames. The C922 GT frames all fall at 6.5–29.5 s, because of the camera–display beat. The 10-28 aggregates come from 6 valid runs (exp-7_d excluded: display glitches) with ~10–200 GT frames each. Several C930e GTs are low quality (corr 0.79–0.86, impulse r² 0.78–0.88).
- **GT floor.** About 0.5 ms (brightness model, gamma, LCD response), so sub-0.55 ms differences are not resolvable. Frame selection with `seq_env` is mildly favourable to the tier-0 arrival lattice. The PTS-selected GT gives the same numbers within 30 µs.
- **Display scan-out and rolling shutter.** The GT is the exposure start of the ROI's rows at the screen position the ROI sees. Scan-out (portrait monitor, up to one refresh) and the rolling-shutter row end up in each camera's constant offset. That is why absolute offsets and inter-camera biases are confounded (§5).
- **Exposure.** E is the nominal 2^-7 s. The C930e manual exposure is often not applied. With auto exposure, E changes, which moves exposure start against every host stamp (C922 offset ≈ −1.14 × exposure change, REPORT finding 12). No tier-0 fit can see that.
- **Camera-clock scores** give only the random part. They depend on the per-camera fixed slope (error ≤ ~5–10 ppm, ≤ 0.15 ms over ±15 s, inferred from the GT check), and they inherit the C922 PTS alternation and the Kiyo's 1 ms PTS units. With per-run envelope slopes, the robust arrival whole-run fit would score ~0 by construction (flagged `degenerate` in the JSON).
- **Conditions.** Every run is 30 s, at 1280x720 MJPEG @30 (generic 25.76 fps), in a dark room with manual exposure. Longer recordings should make whole-run slopes better, not worse (inferred).

## 7. Commands (from the skellycam repo root)

```
uv run --script research/usb_cameras/timing/ts_accuracy/score_vs_flash_gt.py --run research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned --mjpeg-dir C:/Users/Dom/Documents/skellycam-raw/research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture --out research/usb_cameras/results/windows/Gerald/ts_accuracy_20261109/existing_reanalysis/flash_gt_perframe.json
uv run --script research/usb_cameras/timing/ts_accuracy/score_vs_camera_clock.py --manifest research/usb_cameras/timing/ts_accuracy/manifest_camera_clock.json --out research/usb_cameras/results/windows/Gerald/ts_accuracy_20261109/existing_reanalysis/camera_clock_scores.json
uv run --script research/usb_cameras/timing/ts_accuracy/collect_existing_gt.py --flash-root research/usb_cameras/results/windows/Gerald/timing/rerun_20261027/flash --out research/usb_cameras/results/windows/Gerald/ts_accuracy_20261109/existing_reanalysis/existing_gt_aggregates.json
uv run --script research/usb_cameras/timing/ts_accuracy/summarize.py --dir research/usb_cameras/results/windows/Gerald/ts_accuracy_20261109/existing_reanalysis
```

`score_vs_flash_gt.py` needs OpenCV to decode the MJPEG, and it reuses `timing/scripts/flash_analyze.py`, `flash_libuvc_scr.py` and `tools/analyze_frames.py` unchanged (sha256 is in the JSON). The other scripts use numpy only. The camera-clock run takes ~6 min. Logs: `*.log` in this folder.
