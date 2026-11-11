# G-TS analysis: W-TS on Gerald, suite_20261106T224912Z (run 2)

Scope: test W-TS, 23:51:07–23:55:20Z (18:51–18:55 local). Each camera was captured for 30 s through MF and 30 s through DirectShow, at MJPG 1280x720@30, the default in-scope mode for all four cameras. Sources:

- result: `W-TS.json`, `suite_log.txt` lines 930–952
- raw: `C:/Users/Dom/Documents/skellycam-raw/results/windows/Gerald/suite_20261106T224912Z/W-TS/<cam>/<api>/frames.jsonl` and `summary.json`
- code: `suite/windows/tests/w_ts.py`, `suite/common/tsanalysis.py`, `suite/common/rating.py`
- run 1: `../suite_20261106T181941Z/analysis/ts.md`, including its verifier notes

No camera was opened and no suite or result file was changed. I re-ran `w_ts.py --reanalyse` on this run with `--out` pointing into the session scratchpad. It reproduces every rating (`rating_changes: []`, tally `{'partial': 3, 'no': 8, 'untested': 17}`), so the current code is the code that produced this run.

Labels used below:

- **measured**: a named file and field supports it.
- **measured (offline)**: I recomputed it from `frames.jsonl` with a throwaway script.
- **inferred**: reasoning only.

## 1. Short answer

- **Cell count.** There are 28 G-TS cells: 3 `partial`, 8 `no`, 17 `untested` (measured: suite_log line 952).
- **All three `partial` cells are the C922's tier-1 device clock:** `mf`, `mf:uvc_pts` and `mf:uvc_scr_stc`.
- **All eight `no` cells are host timestamps:**
  - `mf:mf_sample_time` for every camera: 16 ms grid;
  - `ds:pyav_pts` for every camera: synthesized.
- **The 17 `untested` cells split as follows:**

| # | Cells | Cause | By design or artefact |
| --- | --- | --- | --- |
| 8 | `mf:frame_index_fit` and `ds:frame_index_fit`, all 4 cameras | `rating.rate_ts(None, None, False)` is hard-wired (w_ts.py:337). The frame-index model can only be scored against a ground truth (flash/rig), and none was run. The fit itself did run; see section 3.4. | By design (plan §3: partial or better needs ground truth or self-consistent device timestamps) |
| 6 | Aggregate `ds` for C922, Kiyo, generic, C930e; aggregate `mf` for generic, C930e | Best-of with `_ORDER` = yes 3 > partial 2 > untested 1 > no 0 (w_ts.py:57, :436). The untested frame-index route outranks the measured `no` of the native stamp. | By design (run 1 verifier V3.1; plan §4 names the frame-index fit as the tier-0 Windows route). Every cell carries `aggregate_note` and has its per-source column. |
| 2 | Kiyo `mf:uvc_pts`, Kiyo `mf:uvc_scr_stc` | `device_ts_self_consistent = false` → `rating.py:182–183` returns untested "device timestamps not self-consistent" (the run 1 B4 fix). | The **camera property is real**: PTS is in 1 kHz units against a 30 MHz `dwClockFrequency`, and the frame cadence jitters 1.6 ms rms. **For the PTS, the criterion is a harness design issue**: the cadence jitter is real and host-visible, so the PTS is a correct timestamp of an irregular stream (H1, section 4). For the STC, `untested` is a fair result. |
| 1 | Kiyo aggregate `mf` | Best-of over {uvc_pts untested, uvc_scr_stc untested, mf_sample_time no, frame_index_fit untested}. `max()` keeps the first untested source, `uvc_pts`, so summary.md shows "(tier 1)". | By design; follows from the two rows above |

So no cell in this run is wrong in the way the C930e `ds:pyav_pts` cell and the five mis-slotted fits were wrong in run 1. The one disputable rating is the Kiyo `mf:uvc_pts` cell (H1).

The blank cells in summary.md are generic and C930e `mf:uvc_pts` / `mf:uvc_scr_stc`. They are blank because those cameras carry no metadata (`fields.uvc_pts = 0`, `uvc_scr_stc = 0`), so `rate_sources` creates no such source (w_ts.py:281, :301). That is the expected tier-0 result, but the table shows nothing rather than "n/a (tier 0)" (H8).

## 2. Every G-TS cell

Each verdict has these criteria, from rating.py:163–173:

- (a) causal error ≤ 0.5 ms vs ground truth;
- (b) drops detectable;
- (c) tier 0;
- (d) not synthesized and not on a host grid (grid ≥ 4 ms counts as bad);
- (e) device timestamps monotonic and self-consistent.

The decision rule: `no` if (d) fails. Otherwise `untested` if (e) is false. Otherwise `partial` if (e) is true. Otherwise `untested` with "no ground truth and no device timestamps evaluated".

All fields cited are under `W-TS.json → verdicts["G-TS|<key>|<cell>"]`.

| Camera | Cell | Rating | Deciding criterion (JSON field) | Real or artefact |
| --- | --- | --- | --- | --- |
| C922 | mf | partial (tier 1) | best = `uvc_pts`; `source_ratings` {uvc_pts partial, uvc_scr_stc partial, mf_sample_time no, frame_index_fit untested} | real (plan §3: tier 1 + self-consistent, no GT) |
| C922 | mf:uvc_pts | partial (tier 1) | (e) true: `detail.monotonic = true`, `pts_step_std_ms = 0.289` < 1, `pts_units.match = true` (300 MHz, −7.06 ppm); (c) false (tier 1) | real |
| C922 | mf:uvc_scr_stc | partial (tier 1) | (e) true: `detail.stc_vs_sequence_residual_std_ms = 0.0022` < 1, `units.match = true` (−7.51 ppm) | real |
| C922 | mf:mf_sample_time | **no** | (d) false: `evidence.host_grid_ms = 16.0` (`measurements…mf.grid_sample_time.on_grid_fraction = 1.0`, phase 0.9999) | real |
| C922 | mf:frame_index_fit | untested | `criteria[0]` "measured" null; `detail.causal_residual_ms.std = 4.61`, `slotting = sequence`, 0 skipped | by design (no GT) |
| C922 | ds | untested | best-of: `source_ratings` {pyav_pts no, frame_index_fit untested} | by design (V3.1) |
| C922 | ds:pyav_pts | **no** | (d) false: `detail.synthesized = true`; `interval_std_ms = 0.0`, `modal_share = 1.0`, 1 distinct interval (33.3333 ms) while arrival std 4.42 ms | real |
| C922 | ds:frame_index_fit | untested | no GT; std 4.59 ms, sequence, 0 skipped | by design |
| Kiyo | mf | untested (tier 1) | best-of: all device sources untested, `mf_sample_time` no | by design |
| Kiyo | mf:uvc_pts | untested (tier 1) | (e) false: `pts_units.units_match = false` (fits 1000.075 Hz vs `dwClockFrequency` 3e7), `pts_step_std_ms = 2.64` ≥ 1; note "PTS not in the descriptor's units" | camera property real; criterion disputable (H1) |
| Kiyo | mf:uvc_scr_stc | untested (tier 1) | (e) false: `stc_vs_sequence_residual_std_ms = 1.66` ≥ 1 (tsanalysis.py:803); units match 30 MHz (+79.5 ppm), `stc_step_gcd_ms = 1.0` | real (STC does not track the host-visible cadence; section 3.3) |
| Kiyo | mf:mf_sample_time | **no** | `host_grid_ms = 16.0` (on-grid 0.9978, phase 0.9937) | real |
| Kiyo | mf:frame_index_fit | untested | no GT; std 5.01 ms, `slotting = "sequence (incremental rejected)"` (4 long gaps offset by bunched frames; PTS shows 0 drops) | by design; the rejection is correct |
| Kiyo | ds | untested | best-of {pyav_pts no, frame_index_fit untested} | by design |
| Kiyo | ds:pyav_pts | **no** | `synthesized = true` (1 distinct interval 33.3383 ms, arrival std 12.33 ms) | real, but measured on a **YUY2 fallback stream** (`apis.ds.capture_ok = false`, `capture_error.reason` "silent format fallback: stream codec 'rawvideo'"); the verdict does not say so (H5) |
| Kiyo | ds:frame_index_fit | untested | no GT; `slotting = incremental`, `slots_skipped = 9`, `fit_unreliable = true` ("skipped + duplicate slots (9) > 1% of 892") | by design; the unreliable flag comes from **one start-up stall** (frame 0→1 = 349.95 ms), not from a bad fit (H4) |
| generic | mf | untested | best-of {mf_sample_time no, frame_index_fit untested} | by design |
| generic | mf:mf_sample_time | **no** | `host_grid_ms = 16.0` (on-grid 1.0, phase 0.9999) | real |
| generic | mf:frame_index_fit | untested | no GT; std 4.63 ms, 17.146 fps, sequence, 0 skipped | by design; fit is now correct (run 1: 30.72 fps, 159 phantom skips) |
| generic | ds | untested | best-of {pyav_pts no, frame_index_fit untested} | by design |
| generic | ds:pyav_pts | **no** | `synthesized = true`, two reasons: 1 distinct interval (33.3383 ms) and drift vs arrival **+428.4 ms/s** | real |
| generic | ds:frame_index_fit | untested | no GT; std 4.58 ms, 17.146 fps, sequence, 0 skipped | by design; fit correct |
| C930e | mf | untested | best-of {mf_sample_time no, frame_index_fit untested} | by design |
| C930e | mf:mf_sample_time | **no** | `host_grid_ms = 16.0` (on-grid 0.9989, phase 0.9999) | real |
| C930e | mf:frame_index_fit | untested | no GT; std 4.66 ms, 30.0224 fps, sequence, 0 skipped | by design |
| C930e | ds | untested | best-of {pyav_pts no, frame_index_fit untested} | by design |
| C930e | ds:pyav_pts | **no** | `synthesized = true` via `modal_share = 0.979` ≥ 0.9 (3 distinct intervals) | real; **fixed since run 1** (was untested, B3) |
| C930e | ds:frame_index_fit | untested | no GT; `slotting = incremental`, `slots_skipped = 1` (a real 65.34 ms gap at frame 247), std 4.66 ms | by design; fit correct (run 1: 31/35 phantom skip/duplicate slots) |

## 3. Quantitative findings

### 3.1 Which timestamp fields exist; the tier split

Measured from `measurements.cameras.*.apis.*.fields` and `pts_matches_tier1_flag`:

| Camera (metadata flag) | MF frames | MF PTS / STC / SOF / EOF STC | DS frames | DS pts |
| --- | --- | --- | --- | --- |
| C922 (ON) | 901 | 901 / 901 / 901 / 901 | 902 | synthesized, 33.3333 ms |
| Kiyo (ON) | 902 | 902 / 902 / 902 (always 0) / 902 (= first STC) | 892 (YUY2 fallback) | synthesized, 33.3383 ms |
| generic (OFF) | 516 | 0 | 516 | synthesized, 33.3383 ms |
| C930e (OFF) | 902 | 0 | 902 | ≈ synthesized: 33.3333, plus 18 × 33.3283, plus one 56.37 ms step |

- `pts_matches_tier1_flag = true` for all four cameras. The tier split is exact.
- In run 1 the Kiyo had 0 frames, so its presence could not be judged. Now it is confirmed on 902 frames (measured).

### 3.2 The 16 ms grid: every host timestamp, both controllers, both APIs

- **MF sample time is on an exact 16.0 ms grid for all four cameras.** Measured, `grid_sample_time`: `known_step = 16ms`, phase concentration 0.9937–0.9999, on-grid 0.9978–1.0.
- **The Kiyo is on the same grid.** It is SuperSpeed on the Thunderbolt xHCI, and the grid now holds on its full 30 s run (run 1 had only the 8 s selftest). 128 × 125 µs = 16 ms holds at SuperSpeed too, which fits the hypothesis in `docs/windows_timer_resolution.md` (inferred).
- **QPC arrival is on the grid in both APIs.** Phase concentration: 0.989–0.995 in MF; 0.959 (Kiyo DS) to 0.999 in DS. So frames are *delivered* on 16 ms ticks; the grid is not only in the stamp.
- **Interval clusters (MF sample time):**
  - C922 32.0 ms (91.7 %) / 48.0 ms (8.3 %);
  - C930e 32.0 / 48.0 (91.8 / 8.2 %);
  - generic 48.0 / 64.0 (35.3 / 64.5 %);
  - Kiyo 16.0 / 32.0 / 48.0 (3.6 / 84.6 / 11.9 %).
- **Frame-index residuals:**
  - every camera except the Kiyo: 4.58–4.66 ms (= 16/√12 = 4.62 ms, pure quantisation);
  - Kiyo: 5.0 ms.
- **Run 1 comparison:** identical grid (phase ≥ 0.999 on 16 ms, ≤ 0.005 on 15.625 ms). Nothing changed.

### 3.3 Device clocks (tier 1)

**C922.** Measured from `apis.mf.device_clock_fit`, `pts_vs_sequence` and `uvc_scr`.

| Quantity | Run 2 | Run 1 |
| --- | --- | --- |
| PTS rate vs `dwClockFrequency` 300 MHz | −7.06 ppm (1σ ±17.7) | −2.05 ppm |
| STC rate | −7.51 ppm (±17.8) | −1.90 ppm (offline) |
| PTS step std | 0.289 ms | 0.587 ms |
| PTS vs ideal frame clock (residual std) | 0.145 ms | 0.347 ms |
| First-payload STC vs ideal frame clock | **0.0022 ms** (range ±0.007) | 0.002 ms |
| EOF STC vs ideal frame clock | 0.228 ms | 0.18 ms |
| STC − PTS | 32.98 ± 0.14 ms (one frame period) | 33.06 ± 0.35 ms |
| Transfer (EOF STC − first STC) | 7.07 ± 0.23 ms; 6.14 SOF counts | 6.99 ± 0.18 ms; 6.05 |
| SOF rate (time reference = STC) | **884.07/s**, steps 29 (478) / 30 (421) | 884/s, 29 (480) / 30 (421) |
| Drops (PTS) | 0 | 0 |
| Frame 0 SCR | not stale (`first_frame_stc_step_ticks` 9,999,000 = 33.33 ms) | — |

- Both device clocks agree with zero offset from QPC within 1σ. Neither run can see a C922 rate error.
- PTS jitter halved since run 1. Cause unknown; scene or exposure is possible (inferred).
- **PTS jitter is stamp noise, not frame timing (measured offline):**
  - the PTS residual is uncorrelated with the sample-time residual (r = −0.15);
  - sample-time residual std 4.601 ms = pure quantisation, i.e. the C922 cadence jitter is ≈ 0;
  - so the first-payload STC is the C922's true frame clock, and PTS adds about 0.15 ms rms on top.
- **SOF.** The C922's SOF is invalid, as in run 1: Linux `UVC_QUIRK_INVALID_DEVICE_SOF`, confirmed by run 1's verifier. The new SOF check (`uvc_scr.sof.ok = false`, note "SOF advances 884/s") flags it automatically.

**Kiyo.** First full-run capture, at plug-in age 199.7 min (23:52:11Z vs LastArrival 20:32:29Z). That is about 11 min before its first unanswered control poll (00:03:01Z, 210.5 min).

- **PTS is a 1 kHz millisecond counter.**
  - `pts_units.freq_hz_est = 1000.075 Hz` against `dwClockFrequency` 30,000,000 (`units_match = false`);
  - steps 27–40 ticks, median 33, step std 2.64 ms;
  - vs ideal frame clock 1.64 ms rms;
  - monotonic, 0 drops (measured).
  - This confirms the 8 s selftest (1001.19 Hz) on 902 frames.
- **STC is in 30 MHz units but moves in whole milliseconds.**
  - `units.freq_hz_est = 30,002,386` (+79.5 ppm, 1σ ±25.7);
  - `step_gcd_ticks = 30000`;
  - 1.66 ms rms vs ideal frame clock.
  - The absolute values are not multiples of 30,000 (offset), only the steps are (measured offline).
- **PTS and STC share one oscillator.** Fitted STC Hz / fitted PTS Hz = 30,002,386 / 1000.0756 = 30,000.1 (offline). Both run about +75–80 ppm fast against QPC, which is about 3σ.
  - The harness note "STC ticks per PTS tick 29997.7: no common offset" divides *nominal* STC Hz by *fitted* PTS Hz. The 75 ppm difference it shows is that mismatch, not a second clock (H2).
- **SOF is always 0.** EOF SCR = first-payload SCR in 902/902 frames, so no transfer time can be measured. `transfer_ms` is nevertheless stored as stats of zeros (H3).
- **Frame 0 SCR is stale.** It is 357 ms older than frame 1 (`first_frame_stc_step_ticks` 10,710,000), exactly as in the selftest. Skipping frame 0 (`skipped_first = 1`) is justified (measured).
- **The Kiyo's frame cadence really jitters, and PTS tracks it. STC does not.** Measured offline, residuals against an ideal frame clock:
  - Sample-time residual std is 4.900 ms. That equals √(4.62² + 1.61²) = 4.89: 16 ms quantisation plus the 1.61 ms PTS jitter.
  - Corr(PTS residual, sample-time residual) = **+0.342**. If PTS were exact, quantisation noise would cap this at 1.61/4.89 = 0.33. The measured value sits at that ceiling.
  - The 32 sample-time intervals of 16 ms coincide with PTS steps averaging 29.5 ms. The 48 ms intervals coincide with 36.0 ms PTS steps.
  - The STC residual is uncorrelated with sample time (r = −0.11) and anti-correlated with PTS (r = −0.32). STC − PTS × 30000 has 2.66 ms rms detrended.
  - So the Kiyo's PTS is a correct (1 ms-quantised, ±0.29 ms) stamp of a stream whose period itself varies by ±1.6 ms rms. The STC is latched at a point that does not follow the exposure.
- **Consequences:**
  - A constant-period frame-index model cannot reach 0.5 ms on the Kiyo: its floor is the 1.6 ms cadence jitter (inferred, strong).
  - The PTS is the Kiyo's only route to ≤ 0.5 ms (subject to the rig run).
  - `untested` for `mf:uvc_pts` follows the plan's wording, but it hides the Kiyo's best timestamp (H1).
- **Tier-0 cadence-jitter estimate from sample time** (√(σ² − 16²/12), measured offline; ±0.2 ms for the Kiyo, about ±0.8 ms near zero):

  | Camera | Estimate |
  | --- | --- |
  | C922 | 0.00 ms |
  | generic | 0.00 ms |
  | C930e | 0.45 ms (consistent with 0) |
  | Kiyo | 1.64 ms |

  This is a cheap tier-0 detector for cameras where the frame-index model will fail.

### 3.4 Frame-index fit with the fixed slotting

Measured from `apis.*.frame_index_fit_arrival.causal`. Run 1 numbers are from run 1 ts.md §3.7 and its verifier V1.

| Cell | Run 2: fps / slotting / skipped+dup / causal std | Run 1 |
| --- | --- | --- |
| C922 MF | 29.99979 / sequence / 0 / 4.61 ms | 29.99994 / 0 / 4.60 |
| C922 DS | 30.00002 / sequence / 0 / 4.59 ms | 30.00006 / 0 / 4.61 |
| Kiyo MF | 30.0208 / sequence (incremental rejected, 4 gaps) / 0 / 5.01 ms | no frames |
| Kiyo DS | 30.0193 / incremental / 9 / 5.04 ms, `fit_unreliable` | no frames |
| generic MF | **17.1460** / sequence / 0 / 4.63 ms | 30.724 (real 25.70) / 159+8 / 9.42 |
| generic DS | **17.1461** / sequence / 0 / 4.58 ms | 29.577 / 136+20 / 9.74 |
| C930e MF | 30.0224 / sequence / 0 / 4.66 ms | 30.0220 / 0 / 4.71 |
| C930e DS | 30.0227 / incremental / 1 (real gap) / 4.66 ms | 29.923 / 31+35 / 9.64 |

- **The B2 fix works.** Every fit now matches the measured sample-time period:
  - generic 58.32 ms (`drops_sample_time.period_ms` 58.335);
  - Kiyo 33.31 ms;
  - C930e 33.31 ms.
- Residuals are back to the quantisation floor everywhere except the Kiyo, whose extra 2.7 ms² is its cadence jitter (§3.3).
- **Kiyo MF.** Incremental slotting found 4 long arrival gaps (max 80.7 ms), offset by bunched frames (min interval 0.24 ms). It correctly rejected them: PTS shows 0 drops.
- **Kiyo DS.** The 9 skipped slots are one start-up stall: frame 0 → 1 = 349.95 ms (measured offline). This explains the frame count, 892 vs 902 in MF. `fit_unreliable` fires on that single gap (H4).
- **C930e DS.** The single skipped slot is a real 1-frame gap at frame 247: arrival interval 65.34 ms.
- `rate_vs_nominal_ppm` (camera vs nominal 30 fps):
  - C922 −7;
  - C930e +746;
  - Kiyo +693;
  - generic −428,465 (17.15 fps).
- The C930e matches run 1 (+730–746 ppm). The Kiyo's frame period is 33.31 PTS-ms, so it runs about 620 ppm fast even in its own clock (inferred).

### 3.5 Synthesized DirectShow pts

Measured from `apis.ds.pts_synthesized`. Drift is the least-squares slope of (arrival − pts) against arrival.

| Camera | pts step | Drift vs arrival | Run 1 drift (verifier V2) |
| --- | --- | --- | --- |
| C922 | 33.3333 ms, all 901 | +0.0006 ms/s | −0.001 |
| Kiyo (YUY2 fallback) | 33.3383 ms, all 891 | −0.72 ms/s | no frames |
| generic | 33.3383 ms, all 515 | **+428.4 ms/s** | +143.2 |
| C930e | 33.3333 (882); 18 × 33.3283; one 56.3722 at frame 247 | −0.34 ms/s | −0.70 (327 corrections) |

- **The generic's drift tripled** because it ran at 17.15 fps instead of 25.70 (§3.7). (33.3383/58.32 − 1 = −428 ms/s of pts per second of arrival.)
- **The C930e's DS pts are not a pure counter.**
  - At the frame-247 gap the pts jumped 56.37 ms: one period plus 23 ms. The drop is partly visible in pts.
  - The −0.34 ms/s drift is the camera's −0.75 ms/s rate error, partly cancelled by that +9 ms arrival-minus-pts step at 27 % of the run. 9 ms × 6 × 0.27 × 0.73 / 30 s ≈ +0.36 ms/s (inferred).
  - The corrections fell from 327 to 18 between runs. The cause is in the DS graph, not the camera (inferred).
- **Kiyo.** `arrival_minus_pts_ms` sits at 342.8 ms for the whole run: the 350 ms start-up stall shifted every arrival against a counter that kept counting.
- `drops_pts` is now `None` with the note "pts synthesized from a counter" on all four cameras (B7 fix). The C930e's 56.37 ms jump at frame 247 shows that note is slightly too strong (H7).

### 3.6 Arrival minus MF sample time: bimodal, reported per mode

Measured from `apis.mf.arrival_minus_sample_time_ms.modes`:

| Camera | ~0.4–0.6 ms mode | ~16.4 ms mode | ~32.5 ms mode | Run 1 (verifier V5) |
| --- | --- | --- | --- | --- |
| C922 | 58.4 % (0.45 ms) | 41.6 % | — | 58 / 42 / — |
| C930e | 79.9 % (0.39 ms) | 20.1 % | — | 79 / 21 / — |
| Kiyo | 95.9 % (0.57 ms) | 2.9 % | 1.1 % | — |
| generic | — | 8.9 % | 90.9 % | — / 7 / 92 |

- Each mode is tight (std 0.24–0.35 ms). Arrival = sample time + 0.4–0.6 ms + k × 16 ms.
- The shares reproduce run 1 within 2 points for the three cameras both runs measured, so they are a stable per-camera property.
- The generic camera is always one or two grid ticks late, i.e. 16–32 ms of extra delivery latency at tier 0 (measured).
- The registry value does not decide the sub-ms share: C922 (ON) 58 %, C930e (OFF) 80 %, Kiyo (ON) 96 % (measured).

### 3.7 Changes from run 1, and why

| Change | Cause |
| --- | --- |
| C930e `ds:pyav_pts` untested → **no** | fix B3 (modal share / ≤ 3 distinct intervals, tsanalysis.py:552–600) |
| New `mf:uvc_scr_stc` cells (C922 partial, Kiyo untested): STC−PTS, transfer time, SOF rate | fix B5 (tsanalysis.py:750–850) |
| Generic and C930e DS frame-index fits correct (9.4–9.7 ms → 4.58–4.66 ms; no phantom slots) | fix B2 (slot_frames, tsanalysis.py:267–333) |
| Kiyo PTS cell untested instead of the misleading partial it would have had | fix B4 (rating.py:182–183) |
| `drops_detectable` from period vs grid; DS drop count `None` when synthesized; start-up interval separated | fix B7 |
| `ambiguous_with_period` false on all arrival grids | fix B8 (tsanalysis.py:234) |
| Arrival-minus-sample reported per mode; drift by least squares | verifier V5, V2 |
| Aggregate rule unchanged, now with `aggregate_note` | by design (V3.1) |
| Kiyo cells measured (6 cells, 902 MF frames) | camera: replugged 15:32 local, streamed at 200 min plug-in age |
| Generic 25.70 → **17.15 fps** (MF, DS and W-MJPEG 17.146 fps) | camera/scene. In the same run W-CYC `opencv_inproc` measured 17.19 fps and `opencv_skellycam` 25.7 fps (W-CYC.json `…/4c4a…/variants/*/final/fps_measured_p50`), and W-CTRL-EFFECT restored `exposure=auto` before W-TS (suite_log 709–792). So the rate follows the exposure mode: auto exposure in an evening-lit room gives 17.15 fps, and a fixed exposure gives 25.7 (REPORT finding 6). Inferred, strong. |
| C922 PTS jitter 0.35 → 0.145 ms rms | camera; cause not identified (inferred) |
| C930e DS pts corrections 327 → 18, plus one DS frame gap | DS graph / camera; not a harness change |

## 4. Remaining harness issues

| ID | Severity | File:line | Issue | Fix |
| --- | --- | --- | --- | --- |
| H1 | medium (changes a rating) | w_ts.py:270 (`step_std_ms < 1.0`); tsanalysis.py:803 (`rstd < 1.0`) | "Self-consistent" is implemented as "regular against an ideal frame clock", which mixes up cadence jitter with stamp error. The Kiyo PTS fails it even though its 1.6 ms deviations are real and host-visible (corr +0.342 at the 0.33 ceiling; sample-time variance = quantisation + PTS variance). A units mismatch is also folded in. | Define self-consistency as: monotonic; fitted rate within tolerance of the host (using the *fitted* units); and the residual vs host explained by the host grid, i.e. var(host residual) ≈ grid²/12 + var(device residual), with the device residual positively correlated with the host residual. Report the `dwClockFrequency` mismatch as a separate flagged defect ("partial, PTS in 1 kHz units"). The Kiyo STC (r = −0.11 vs host) would still fail. Needs a plan §3 decision before changing ratings. |
| H2 | low | tsanalysis.py:823–829 | `pts_stc_rate_ratio = hz / p_hz` uses the *nominal* STC Hz with a *fitted* PTS Hz. Kiyo shows 29997.7 (true 30000.1); C922 shows 1.0000075 (true ≈ 1.0000005). The note "no common offset" is wrong for the Kiyo: the ratio is an exact 30000. | Use `f_est / p_hz`. When the ratio is near an integer, compute `STC − PTS × ratio` (Kiyo: 2.66 ms rms detrended). |
| H3 | low | tsanalysis.py:832–836 | When EOF SCR = first SCR in every frame (Kiyo), `transfer_ms` and `transfer_sof_counts` are stored as stats of zeros (mean 0.0). That reads like a 0 ms transfer. | Set them to `None` when `all(eof == first)`; keep the note. |
| H4 | low | tsanalysis.py:402 (`skipped + dup > 1 % of N`) | One start-up stall (Kiyo DS frame 0 → 1 = 349.95 ms, 9 slots) marks a correct fit `fit_unreliable`. | Exclude interval 0 from the slot count, as `_drops_measured` does (w_ts.py:131–133), or count gap *events* (> 2 % of N) rather than skipped slots. |
| H5 | low | w_ts.py:430–458 (capture_error copied only when there are no rows, :455–457) | Kiyo DS cells were rated from a capture with `capture_ok = false` (silent rawvideo/YUY2 fallback, rc 4). Neither `ds:pyav_pts` nor `ds:frame_index_fit` shows that. | Copy `capture_ok` / `capture_error` into every cell's evidence and append "(format fallback: YUY2)" to the note, or recapture with `--engine ffmpeg`. |
| H6 | low | w_ts.py:146 → tsanalysis.py:521–526 | On a 16 ms-gridded sample time, a 16 ms interval (real cadence jitter) rounds to k = 0 and is counted as a duplicate: Kiyo `drops_sample_time.duplicates = 32`, while PTS shows 0. At 30 fps the `_detectable` margin is 33.3 vs 32 ms, so one jittery camera breaks the slot rounding. | On gridded series, count a duplicate only for identical timestamps (k = max(1, round(Δt/p)) when Δt ≥ grid). Make `drops_detectable` require p > 2 × grid + 3σ of cadence jitter. |
| H7 | low | w_ts.py:222 | "pts synthesized from a counter: drops cannot be seen in them" is not quite right for the C930e: its pts jumped 56.37 ms at the frame-247 gap. | Reword to "drops are not reliably visible", and record pts intervals > 1.5 × modal as `pts_jumps`. |
| H8 | low (presentation) | summary rendering (no source when `uvc_pts_present` is false or `n_stc` = 0, w_ts.py:281, :301) | The generic and C930e `mf:uvc_pts` / `mf:uvc_scr_stc` cells are blank. | Emit an `n/a (no UVC metadata: tier 0)` cell. |
| H9 | low | w_ts.py:304 | The STC "drops detectable" criterion is `vs_sequence.slotting is not None`, which is always true once regularity ran; it does not test detectability. | Use `regularity.step_gcd_ms < period/2` and the PTS drop result. |
| H10 | cosmetic | tsanalysis.py:604–635 | On a drifting series (generic `arrival_minus_pts_ms`), every group falls below `min_share`: `modes = []`, `minor_share = 1.0`. | Skip `modes_report` when the series is synthesized or drifts more than 5 ms/s; report the drift only. |

Not bugs (checked):

- The aggregate best-of rule (by design).
- `frame_index_fit` always untested (no GT).
- Kiyo frame 0 skip (stale SCR confirmed: 357 ms).
- SOF time reference = STC for the C922 and arrival for the Kiyo (tsanalysis.py:843–849).
- `pts_matches_tier1_flag = None` for 0 frames (B6 fix). Not exercised: every camera delivered frames.

## 5. What this run says about the plan's G-TS questions

1. **Tier 0 on Windows: every host timestamp fails.**
   - MF sample time, MF/DS QPC arrival and DS pts are all on a 16 ms grid or synthesized. That holds on both controllers, at HS and SS, with and without metadata.
   - The only tier-0 candidate is the frame-index model. Its floor is the camera's cadence jitter:
     - ≈ 0 for the C922, generic and C930e (sample-time variance equals quantisation);
     - 1.6 ms for the Kiyo. That fails 0.5 ms before any rig run.
2. **Tier 1 is camera-specific.**
   - C922: STC is a 2 µs frame clock and PTS is 0.15 ms rms, both at 300 MHz and in descriptor units. SOF is invalid.
   - Kiyo: PTS is a 1 kHz counter (descriptor wrong) that does track the irregular cadence. STC is in 1 ms steps and does not track it. SOF is 0. Frame 0 SCR is stale.
   - A tier-1 implementation needs per-camera validation: units vs fitted rate, a SOF check, a frame-0 skip, and a host-correlation check to pick PTS vs STC.
3. **Drops.**
   - The PTS route sees drops on both tier-1 cameras: 0 drops measured.
   - Sample-time drops are usable at 30 fps on regular cameras, but give phantom duplicates on the jittery Kiyo (H6).
   - DS pts are not usable for drops.
4. **Still needed:**
   - the flash/rig run (`W-TS --flash`), to score PTS, first-payload STC and the frame-index model;
   - a decision on H1 (what "self-consistent" means in plan §3);
   - a Kiyo DS capture with `--engine ffmpeg`, to get MJPEG rather than the YUY2 fallback.


## Verifier notes

Adversarial check, 2026-11-06. No camera was opened and no suite or result file was changed. Scripts are in the session scratchpad (`tsv/v1.py` … `v6.py`). They read `W-TS.json` and the raw `frames.jsonl`. I re-ran `w_ts.py --reanalyse --out <scratchpad>`: the tally is `{partial 3, no 8, untested 17}` with `rating_changes: []`, so TS2 is confirmed. "From frame 30" below means frames 0–29 are excluded, as the causal fit excludes them.

### V1. Verdicts on the findings

| ID | Verdict | Note (measured unless marked) |
| --- | --- | --- |
| TS1, TS2, TS3, TS7, TS14, TS16, TS18 | confirmed | All counts, shares and fields recomputed. |
| TS4 | confirmed | MF QPC phase 0.989–0.995, DS QPC 0.959–0.999. As the analyst says, the Kiyo is the exception to the 4.62 ms floor. |
| TS5 | confirmed | One addition: the 6.14 "SOF counts" of transfer time are counted on the C922's invalid 884/s SOF. That is about 6.9 ms, consistent with the 7.07 ms STC figure. |
| TS6 | **weakened** | See V2.1. The C922 PTS "jitter" is a deterministic even/odd alternation. The correlation test is invalid. The conclusion that the STC is the clean frame clock rests on the STC's 2.2 µs regularity alone. |
| TS8 | confirmed, one correction | PTS steps are 27–**43** ticks (`device_clock_fit.whole_run.pts_period_ticks.max = 43`), not 27–40. Plug-in ages are correct: first unanswered poll 00:03:01Z = 12632.2 s (`run_suite.json kiyo_onset…first_failure_utc`). |
| TS9 | confirmed | The ratio of fitted STC Hz to fitted PTS Hz is 30000.115 (offline fit against QPC). PTS +74.9 ppm (σ 23), STC +79.5 ppm (σ 25.7). |
| TS10 | **weakened** | The measured part is robust, and stronger than the correlation shown: from frame 30, std(sample time − PTS·1000/f) = **4.613 ms**, which is the 4.619 ms quantisation floor. A 7-frame-shifted control gives 5.27 ms. std(QPC − PTS) = 4.62 ms. So the PTS explains *all* host-visible non-quantisation timing. That does **not** show the *exposure* cadence jitters. See V2.2. |
| TS11 | weakened | Numbers reproduce if frame 0 is excluded: C922 0.00, generic 0.14, C930e 0.475, Kiyo 1.645 ms. The estimator detects host-visible delivery jitter, which is not necessarily exposure jitter (V2.2), so "the frame-index model will fail" does not follow from it. |
| TS12 | confirmed | C930e DS: incremental slotting lowers the residual from 10.46 to 4.63 ms, which is a real one-frame gap. The Kiyo MF "incremental rejected" result is correct, but all four of its gaps are start-up gaps (V2.3). |
| TS13 | confirmed, refined | Within run 2, W-CYC `opencv_inproc` gives 17.19 fps and `opencv_skellycam` (sets exposure) gives 25.70. W-CTRL-EFFECT restores the *original* value (`w_ctrl_effect.py:564-567`), so the generic was already in auto. Run 1, however, measured 25.7 in W-MJPEG at 13:20 local, *before* W-CYC. So run 1's rate was not a manual exposure left behind by skellycam. Most likely it was auto exposure in daylight: run 1 W-TS was at 14:45 local, run 2 at 18:51 (inferred). Read: rate = min(25.7, exposure-limited rate). |
| TS15 | confirmed, upgraded to measured | LS drift of the segments before and after the frame-247 step: −0.768 and −0.741 ms/s. The whole-run −0.345 is the step artefact. |
| TS17 | confirmed, wording | "Constant 342.8 ms" is loose: mode std 8.45 ms and drift −0.72 ms/s, about 22 ms over the run. The 349.95 ms gap at interval 0 is confirmed. |
| TS19 | **weakened** (classification) | Two items listed as camera changes are not camera changes. (a) C930e DS pts corrections 327 → 18: the 333283 steps begin at frame 778, every 12 frames (run 1: from frame 242). This is the DS graph's correction onset; the analyst's own §3.5 says so. (b) Generic 17 fps: lighting and exposure state, confounded by the new test order (W-TS ran 4 h later in the day, after W-CTRL-EFFECT). |

### V2. Details

1. **The C922 PTS alternates even/odd.** Offline from `mf/frames.jsonl`:
   - PTS steps fall in two clusters: 33.00–33.10 ms (450) and 33.50–33.65 ms (450);
   - the residual has lag-1 autocorrelation −0.999, and the FFT peak is at 0.5 cycles/frame;
   - the 0.145 ms rms is a ±0.145 ms odd/even offset, not random stamp noise.

   corr(PTS residual, sample-time residual) = −0.146 is 4.4σ from 0 (SE 0.033). It comes from the 6th harmonic (0.5 cycles/frame) of the 12-frame 32/48 ms quantisation sawtooth lining up with the alternation, so it is not evidence of independence. "Run 1 0.347 → run 2 0.145 ms" is therefore a change in the alternation amplitude, possibly exposure-dependent (inferred).
2. **Kiyo: what the PTS tracks.** The PTS residual (from frame 30) has lag-1 autocorrelation **−0.32** (mean-reverting), and corr(PTS residual, JPEG bytes) = 0.00. Mean-reverting jitter fits two pictures equally well:
   - (a) a frame period that varies (the analyst's reading);
   - (b) a regular sensor clock, with the PTS latched at a firmware event (hand-off or scheduling) whose jitter also drives host delivery.

   Under (b), the frame-index model would be the *better* exposure estimate, and the PTS would be 1.6 ms rms wrong. Without the rig, TS10's consequences cannot be decided: "a constant-period model cannot reach 0.5 ms on the Kiyo" and "the PTS is its best stamp" both depend on which picture holds.
3. **Kiyo MF start-up transient.**
   - All 4 long QPC gaps (80.7, 80.4, 64.2, 62.0 ms) are at intervals 0, 2, 8 and 16. Frames 1–17 arrive 30–48 ms late, in bunches.
   - `frame_index_fit_arrival.whole_run.residual_stats_ms.std` = **6.29 ms** (the cell's causal value, 5.01, skips frames < 30). From frame 30 the whole-run std is 4.99 ms.
   - The Kiyo's causal excess over the floor is 5.01² − 4.62² = 3.8 ms², not 2.7. About 2.7 ms² is PTS-tracked jitter; about 1.1 ms² comes from the 3 % of frames that arrive 16 or 32 ms late.
4. **Cell-table corrections.**
   - Kiyo `mf:uvc_pts`: steps 27–43.
   - Kiyo `mf:frame_index_fit`: whole-run 6.29 ms, start-up dominated.
   - The 8 `no` host-stamp cells (`mf:mf_sample_time`, `ds:pyav_pts`) also carry the criterion "device timestamps monotonic and self-consistent: met false", with `evidence.device_ts_self_consistent = false`. It is set at w_ts.py:316 and :327, although these are host timestamps. The rating is unaffected because (d) fires first, but the evidence is misleading.
   - Kiyo aggregate `mf`: "(tier 1)" is a tie-break artefact. `max()` (w_ts.py:436) keeps the first untested source, the tier-1 `uvc_pts`, over the tier-0 `frame_index_fit` with the same rank. That is not "by design" in any documented sense.
5. **Harness findings.**
   - H1: the diagnosis holds (w_ts.py:270 and tsanalysis.py:803 fold the units check and regularity together), but the proposed fix is **unsafe**. A device residual that correlates positively with the host residual is exactly what a delivery-time stamp produces (V2.2), so the fix would promote the Kiyo PTS to `partial` on evidence that does not tell exposure from delivery. Safer: report the units defect as its own flag, keep the device-clock cell `untested` until the rig is run, and record "PTS tracks host delivery (std(host − PTS) = quantisation floor)" as evidence.
   - H2: confirmed, but the C922 "true ≈ 1.0000005" is wrong. f_est / p_hz = 299997746 / 299997754 = 0.99999997. The note's clause "tick at different rates" is correct; only "no common offset" is wrong.
   - H3: confirmed; `transfer_sof_counts` is at :838, not within :832–836.
   - H4: confirmed, and it should cover MF too (V2.3).
   - H5–H10: confirmed against the code and JSON.

### V3. Missed harness issues

| ID | Severity | File:line | Issue | Fix |
| --- | --- | --- | --- | --- |
| HV1 | low | w_ts.py:436 | The best-of tie-break does not prefer tier 0. The Kiyo `mf` aggregate shows "untested (tier 1)" although a tier-0 route has the same rank. | Use the key `(_ORDER[rating], tier == 0)`. |
| HV2 | low | w_ts.py:316, :327 | Host stamps pass `device_ts_self_consistent=False`, which adds a false "device timestamps" criterion to `no` cells. | Pass None for host-stamp sources. |
| HV3 | low | w_ts.py:77-83 (`_fits`) → tsanalysis.py:267-333 | Frame-index fits and slotting include the start-up transient. The Kiyo MF whole-run residual is 6.29 ms instead of 4.99, and its 4 "gaps" are all start-up. | Drop leading frames until arrival − sample time settles (or the first 1 s) before slotting and fitting; report the start-up separately, as `_drops_measured` does. |
| HV4 | low | tsanalysis.py:538-549 | The least-squares drift is biased by a single step: C930e whole-run −0.345 against −0.77 / −0.74 ms/s for the segments. | Report a robust slope (median of segment slopes, or Theil–Sen) next to the LS slope. |
| HV5 | cosmetic | tsanalysis.py:579-582 | `arrival_interval_std_ms` includes the start-up interval: Kiyo DS 12.33 ms, 6.28 without it. | Skip interval 0. |
| HV6 | low | w_ts.py:547 (`ck.pyav_capture`) | DS uses the PyAV engine, although pyav_ds itself reports the silent fallback and says "use --engine ffmpeg". As a result, the Kiyo DS cells describe YUY2 rather than MJPG. | Retry once with the ffmpeg engine when `capture_error.stage == "format"`. |
