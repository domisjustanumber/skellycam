# G-TS analysis: W-TS on Gerald, suite_20261106T181941Z

Scope: test W-TS (19:45:05–19:48:13Z, 30 s per camera × API, MJPG 1280x720@30), plus timestamp fields in the W-MJPEG and W-CYC `frames.jsonl` files. Sources:

- result JSON: `W-TS.json`
- raw frames: `C:/Users/Dom/Documents/skellycam-raw/results/windows/Gerald/suite_20261106T181941Z/W-TS/<cam>/<api>/frames.jsonl`
- code: `suite/windows/tests/w_ts.py`, `suite/common/tsanalysis.py`, `suite/common/rating.py`

No cameras were opened and no suite or result file was changed. "Measured" means read from a named file and field. "Measured (offline)" means I recomputed it from the saved `frames.jsonl` with throwaway scripts in the scratchpad. "Inferred" means a reasoned conclusion that no direct measurement shows.

## 1. Short answer: why most G-TS cells say "untested"

14 of the 21 G-TS cells are `untested`. The log line `W-TS ok … ratings {'partial': 2, 'no': 5, 'untested': 14}` confirms the count. They break down into four groups:

| # cells | Cells | Cause | Camera/API or harness? |
| --- | --- | --- | --- |
| 6 | `*:frame_index_fit` (C922, generic and C930e; ds and mf) | `rate_sources` always calls `rating.rate_ts(None, None, False)` for the frame-index model (w_ts.py:176). That path always returns `untested` ("no ground truth and no device timestamps evaluated"). The analysis **did** run: `detail.causal_residual_ms` is filled in. | By design: a frame-index model can only be scored against a ground truth (flash/rig, not run). Not a defect in itself, but the residuals it reports are wrong for 2 of the 6 cells (bug B2). |
| 5 | Aggregate `ds` (C922, generic, C930e) and aggregate `mf` (generic, C930e) | The aggregate is "the best source" by `_ORDER = {"yes":3,"partial":2,"untested":1,"no":0}` (w_ts.py:33, :242). `untested` outranks `no`, so the always-untested frame-index cell beats the measured `no` of `pyav_pts` / `mf_sample_time`. | **Harness reporting defect (B1).** It hides five measured "no" results for the native timestamps. |
| 1 | C930e `ds:pyav_pts` | The synthesized-timestamp test needs interval std < 0.001 ms (w_ts.py:170). The C930e DS pts intervals are 333333 or 333283 × 100 ns (std 0.0024 ms), so they are not flagged and the cell falls through to untested. | **Harness threshold artefact (B3).** The pts are synthesized; the cell should say `no`. |
| 2 | Kiyo `mf`, Kiyo `ds` | No frames. MF: `first_sample` `0x8007001F` ERROR_GEN_FAILURE after 0.063 s. DS: `OSError(5)` at open (W-TS.json `verdicts[...1532...|mf/ds].evidence.capture_error`). | **Camera state, not W-TS.** The Kiyo delivered exactly 1 frame in the whole run (W-MJPEG `mf_640x360_5`, 13:44:00 local) and nothing afterwards: W-MJPEG 0 fps on all 28 modes, W-CYC 0/50, W-TS 0, W-KIYO 0/61 control polls. Its devnode stayed healthy (no problem code, no re-arrival), so the wedge never showed in PnP. |

So the DS analysis was not skipped: grid, frame-index fit, drop count and latency are all present for DS (`measurements.cameras.*.apis.ds`). DS cannot carry UVC PTS by construction: `fields.uvc_pts: 0` is hard-coded at w_ts.py:119, and the plan (§2.2) says DirectShow has no metadata consumer.

## 2. Every G-TS cell

The criteria list in each verdict is (a) causal error ≤ 0.5 ms vs ground truth, (b) drops detectable, (c) tier 0, (d) not synthesized and not on a host grid. A `no` comes from (d), or from (a) > 2 ms. A `partial` comes from `device_ts_self_consistent` being true when there is no ground truth. All fields cited are under `W-TS.json → verdicts["G-TS|<key>|<cell>"]`.

| Camera | Cell | Rating | Criterion that decided it (JSON field) | Real or artefact |
| --- | --- | --- | --- | --- |
| C922 | ds | untested | Best-of picked `frame_index_fit` (untested) over `pyav_pts` (no): `source_ratings = {pyav_pts: no, frame_index_fit: untested}`, `source = frame_index_fit` | artefact (B1); true native answer is **no** |
| C922 | ds:frame_index_fit | untested | `criteria[0]` "measured" null; `evidence.causal_error_ms_1sigma = null`, `ground_truth = false` | real limitation (no GT); residual 4.61 ms is the arrival grid only |
| C922 | ds:pyav_pts | **no** | `criteria[3].met = false`, `evidence.synthesized = true`, `detail.interval_std_ms = 0.0` (every interval 333333 × 100 ns) | real: DS pts are nominal-rate synthesized |
| C922 | mf | partial (tier 1) | `source = uvc_pts`, `evidence.device_ts_self_consistent = true`, `evidence.tier = 1`; note "no ground truth yet; device timestamps self-consistent" | real (correct by plan §3: tier 1 + self-consistent, no GT) |
| C922 | mf:frame_index_fit | untested | as ds:frame_index_fit; `detail.causal_residual_ms.std = 4.60` | real limitation (no GT) |
| C922 | mf:mf_sample_time | **no** | `criteria[3].met = false`, `evidence.host_grid_ms = 16.0` (`grid_sample_time.on_grid_fraction = 1.0`, `phase_concentration = 1.0`) | real: 16 ms host grid |
| C922 | mf:uvc_pts | partial (tier 1) | `device_ts_self_consistent = true` from `detail.monotonic = true`, `pts_step_std_ms = 0.587` (< 1), `ppm_vs_dwClockFrequency = −2.05` (< 1000); `criteria[2].met = false` (tier 1) | real |
| Kiyo | ds | untested | `criteria[0].detail = "no frames captured"`; `evidence.capture_error.errno = 5`, stage `open` | real (Kiyo wedged since 13:44) |
| Kiyo | mf | untested | `"no frames captured"`; `capture_error.hr = 0x8007001F`, stage `first_sample` | real (Kiyo wedged) |
| generic | ds | untested | best-of: `source_ratings = {pyav_pts: no, frame_index_fit: untested}` | artefact (B1); true native answer **no** |
| generic | ds:frame_index_fit | untested | no GT. Its `causal_residual_ms.std = 9.74` comes from a mis-slotted fit (B2): fit fps 29.58 against a real 25.70, 136 phantom skipped slots | real limitation + wrong numbers (B2) |
| generic | ds:pyav_pts | **no** | `evidence.synthesized = true`, `interval_std_ms = 0.0` (every interval 333383 × 100 ns) | real |
| generic | mf | untested | best-of: `source_ratings = {mf_sample_time: no, frame_index_fit: untested}` | artefact (B1); true native answer **no** |
| generic | mf:frame_index_fit | untested | no GT; `causal_residual_ms.std = 9.42` from a mis-slotted fit (B2): fit fps 30.72, `slots_skipped = 159`, `duplicate_slots = 8` | real limitation + wrong numbers (B2) |
| generic | mf:mf_sample_time | **no** | `evidence.host_grid_ms = 16.0` | real |
| C930e | ds | untested | best-of: `source_ratings = {pyav_pts: untested, frame_index_fit: untested}` | artefact (B1 + B3) |
| C930e | ds:frame_index_fit | untested | no GT; `causal_residual_ms.std = 9.64` from a mis-slotted fit (B2): fit fps 29.92 against a real 30.02, 31 skipped and 35 duplicate slots | real limitation + wrong numbers (B2) |
| C930e | ds:pyav_pts | untested | `evidence.synthesized = false` because `detail.interval_std_ms = 0.0024` ≥ 0.001; `host_grid_ms = null` → `device_ts_self_consistent = null` → untested | **artefact (B3)**; should be **no** |
| C930e | mf | untested | best-of: `source_ratings = {mf_sample_time: no, frame_index_fit: untested}` | artefact (B1); true native answer **no** |
| C930e | mf:frame_index_fit | untested | no GT; `causal_residual_ms.std = 4.71` (fit is sane: 30.022 fps, 0 skipped) | real limitation (no GT) |
| C930e | mf:mf_sample_time | **no** | `evidence.host_grid_ms = 16.0` | real |

There is no `mf:uvc_pts` cell for the generic or the C930e because `uvc_pts_present = false` (0 frames with PTS). That is the expected tier-0 result (see §3.2). The Kiyo has no per-source cells at all because it delivered no rows, so `rate_sources` was never called (w_ts.py:239).

## 3. Quantitative findings

### 3.1 Which timestamp fields exist (per camera × API)

| Camera (tier-1 flag) | MF: `qpc_ns` | MF: `sample_time_100ns` | MF: UVC PTS / SCR STC / SOF | MF: `mf_device_timestamp` | DS: `qpc_ns` | DS: `pts_ns` |
| --- | --- | --- | --- | --- | --- | --- |
| C922 (ON) | 902/902 | 902/902, 16 ms grid | **902/902** (also EOF PTS/STC/SOF) | = sample time in 902/902 | 902/902 | 902/902, synthesized 33.3333 ms |
| Kiyo (ON) | 0 (no frames) | 0 | 0 this run (selftest 12:47 local: 242/242) | — | 0 | 0 |
| generic (OFF) | 772/772 | 772/772, 16 ms grid | **0/772** | = sample time 772/772 | 773/773 | 773/773, synthesized 33.3383 ms |
| C930e (OFF) | 902/902 | 902/902, 16 ms grid | **0/902** | = sample time 902/902 | 903/903 | 903/903, ≈ synthesized (333333/333283) |

Measured: W-TS.json `measurements.cameras.*.apis.*.fields`; the `mf_device_timestamp` equality is measured offline from frames.jsonl. `MFSampleExtension_DeviceTimestamp` is therefore just the host sample time, not a camera clock.

### 3.2 Tier-1 / tier-0 split: exact for every camera that streamed

- W-TS: `pts_matches_tier1_flag = true` for the C922 (PTS in 902/902 frames), the generic (0/772) and the C930e (0/902). Measured, W-TS.json `apis.mf.pts_matches_tier1_flag`.
- The split holds in every MF capture of the run (measured offline):
  - W-MJPEG: C922 10,875/10,875 frames with PTS over 120 modes; C930e 0/5,903 over 119 files; generic 0/788.
  - W-CYC: C922 450/450, C930e 0/450, generic 0/450.
- Kiyo: `pts_matches_tier1_flag = false` in W-TS, but only because it delivered 0 frames (B6). Its single W-MJPEG frame carried metadata (`uvc_pts = 574724`, `uvc_scr_stc = 12830816`, `uvc_scr_sof = 0`), and the selftest run 3 hours earlier had PTS in 242/242 frames. So the Kiyo also follows its flag (measured, two sources).
- Conclusion: PTS presence follows the per-instance `MetadataBufferSizeInKB0` value exactly. The C930e had PTS on 10-27 (REPORT finding 8), when its old instance carried the value, and has none now on its new instance. That confirms plan §2.2: the value is per instance and was lost when the port changed (inferred from the two runs).

### 3.3 Grid and quantisation: 16.0 ms, on every host timestamp, at tier 0 and tier 1 alike

- MF sample time sits on an exact 16.0 ms grid for all three streaming cameras (measured, `grid_sample_time`):
  - `step_ms = 16.0`, `on_grid_fraction = 1.0`, phase concentration 1.0 / 1.0 / 0.9999.
  - Phase concentration for 15.625 ms is ≤ 0.003, so this is **16.0 ms, not the 15.625 ms timer tick**.
- QPC arrival is on the same grid in both APIs (measured, `grid_qpc_arrival`):
  - phase concentration 0.992–0.9996;
  - intervals cluster at 32.0 ms and 48.0 ms (C922 MF: 826 at 31.999, 75 at 48.004);
  - interval std 4.36–7.95 ms.
- All 198 W-MJPEG MF captures with ≥ 40 frames (C922 120, C930e 68, generic 10) (5–60 fps, every size) have a sample-time phase concentration ≥ 0.999 on 16 ms. That covers the C922 at 720p60 too, where sample-time intervals are 32/48 ms (measured offline).
- Metadata ON changes nothing here: the C922's sample time is just as gridded as the tier-0 cameras'. MF does **not** derive its sample time from PTS/SCR. Sample time vs PTS residual std is 4.54 ms (measured offline).
- Arrival minus sample time (measured, `arrival_minus_sample_time_ms`):
  - C922: median 0.37 ms, p95 16.4 ms (bimodal);
  - C930e: median 0.65 ms, p95 16.8 ms;
  - generic: median 32.3 ms, i.e. the frame reaches the app two grid ticks after its sample time.
  - So the C922's ~0.3 ms mode also appears on the tier-0 C930e. The registry value is not what puts the C922 into the sub-ms mode, which supports REPORT's "beat-phase" reading (inferred).
- The Kiyo (SuperSpeed, separate Thunderbolt xHCI) was also on the 16 ms grid in the selftest (sample-time phase concentration 0.9995). The grid is not specific to the HS root port. It is consistent with a 128-(micro)frame isochronous transfer completion (128 × 125 µs = 16 ms), but that is a hypothesis (inferred).

### 3.4 DirectShow pts: synthesized from the nominal rate; drift equals the camera's rate error

Measured offline: pts span vs arrival span over the 30 s run.

| Camera | DS pts step | Real rate (arrival, both APIs) | pts drift vs arrival |
| --- | --- | --- | --- |
| C922 | 333333 × 100 ns, all 901 | 29.9999 / 30.0001 fps | −0.13 ms/s |
| C930e | 333333 (575) or 333283 (327); the shorter steps start at frame 242, about every 12 frames | 30.0220 / 30.0226 fps | −1.25 ms/s |
| generic | 333383, all 772 | 25.6999 / 25.7003 fps | **+142.9 ms/s** (pts fall 4.3 s behind in 30 s; `arrival_minus_pts_ms` 132 → 4430 ms) |

- The generic camera's +143 ms/s reproduces REPORT finding 7 (+141 ms/s).
- The C930e's 50 × 100 ns corrections look like a slow drift adjustment in the DirectShow graph, not a camera clock: pts still run 1.25 ms/s fast against arrival (inferred).
- DS `drops_pts = 0` for every camera means nothing, because counter-generated pts cannot show a gap (B7).

### 3.5 UVC PTS clock fits (C922, the only PTS this run)

Measured from W-TS.json `apis.mf.device_clock_fit`:

- Device clock vs QPC:
  - `freq_hz_est` = 299,999,384.5 Hz, against `dwClockFrequency` 300,000,000: **−2.05 ppm**, the same causal and whole-run.
  - The SCR STC, fitted offline, gives −2.18 ppm, consistent.
  - The slope's 1σ uncertainty from 16 ms-quantised arrivals over 30 s is about ±18 ppm (inferred: σ/(√N·std(t)) = 4.6 ms / (30 × 8.66 s)), so −2 ppm agrees with zero.
- PTS steps:
  - mean 10,000,098 ticks (33.3337 ms), std 176,054 ticks = **0.587 ms**, monotonic, no wrap problems (the 32-bit counter wraps every 14.3 s at 300 MHz and is unwrapped correctly).
  - The steps are discrete: clusters at 32.05, 33.03–33.06, 33.61–33.64 and 34.62 ms (measured offline).
- Residual against arrival:
  - causal std 4.597 ms, whole-run 4.604 ms;
  - this is entirely the 16 ms arrival grid (16/√12 = 4.62 ms), so it says nothing about PTS quality.
- Measured offline:
  - **Causal PTS mapping** vs the whole-run mapping: std 0.19 ms once 30 frames are in; the first frames are off by up to 1.7 ms (−0.88, −1.70, −0.70 ms at frames 30–32). Causal start-up costs about 1 s.
  - **PTS vs an ideal frame clock** (linear fit of PTS to the frame sequence number): period 33.33333 ms, residual std **0.347 ms**, range −1.07 … +0.25 ms.
  - **SCR STC at the first payload** vs the frame sequence number: residual std **0.002 ms** (±6 µs). The first-payload STC is a near-perfect frame clock, while PTS carries about 0.35 ms rms of jitter.
  - EOF STC: residual std 0.18 ms, because the transfer time varies with JPEG size.
  - First-payload STC − PTS = 33.06 ± 0.35 ms. EOF STC − PTS = 40.05 ± 0.48 ms. So the transfer starts about one frame period after PTS and lasts about 7 ms (6.05 SOF counts).
- C922 SOF counter: it advances 29 or 30 per frame, i.e. **884 counts/s instead of 1000** (measured offline). This is the defect the Linux kernel works around with `UVC_QUIRK_INVALID_DEVICE_SOF` for 046d:085c (agent_reports/plan_20261106/linux.md, §6.11). The C922's SOF in the SCR cannot be used to map the device clock to the USB frame number.
- The harness analyses PTS only and ignores the STC and SOF it records (B5).

### 3.6 The Kiyo PTS oddity (from the selftest, not this run)

Measured offline from `C:/Users/Dom/Documents/skellycam-raw/results/windows/Gerald/suite_build_selftest_20261106/quick/W-TS/usbvideodevice_1532-0e05_4/mf/frames.jsonl` and `suite_build_selftest_20261106/quick/W-TS.json`:

- PTS counts in milliseconds:
  - fitted rate 1001.19 Hz (`freq_hz_est`), `ppm_vs_dwClockFrequency = −999,966`, against `dwClockFrequency = 30,000,000`;
  - steps of 27–42 ticks with median 33, step std 2.77 ms.
- SCR STC is in 30 MHz units (fit 30.07 MHz vs QPC), but it moves in whole-millisecond steps: STC ms per PTS tick = 1.00006, and the values are multiples of 10,000 ticks. So PTS and STC are the same 1 ms clock, scaled differently.
- SOF is always 0.
- Both PTS and STC deviate from an ideal frame clock by std 1.66–1.75 ms (range ±3.5 ms). Their correlation with arrival residuals is 0.05, so arrivals (16 ms rms noise on the Kiyo) cannot tell whether the frame timing really jitters or only the stamp does.
- `w_ts.py` correctly attaches the note "PTS not in the descriptor's units" and sets `device_ts_self_consistent = false`. But `rating.rate_ts` still returned `partial` (bug B4), so a working Kiyo would have shown a misleading `partial` in this run.
- No Kiyo PTS was captured in this run (1 frame only). The 1 kHz finding is from one 8 s selftest capture and needs a re-run after a replug.

### 3.7 Frame-index fit errors

- Fit as reported (W-TS.json `apis.*.frame_index_fit_arrival`):
  - C922: MF 29.99994 fps, residual std 4.60 ms causal / 4.60 whole-run, 0 skipped, 0 duplicate. DS: 30.00006 fps, 4.61 / 4.60.
  - C930e MF: 30.0220 fps, 4.71 / 4.66, 0 / 0.
  - These match pure 16 ms quantisation.
- Wrong fits (bug B2):

  | Cell | Fit fps | Real fps | Skipped / duplicate slots | Residual std (causal) |
  | --- | --- | --- | --- | --- |
  | generic MF | 30.724 | 25.70 | 159 / 8 | 9.42 ms |
  | generic DS | 29.577 | 25.70 | 136 / 20 | 9.74 ms |
  | C930e DS | 29.923 | 30.02 | 31 / 35 | 9.64 ms |

  - The phantom skips are not drops: the MF sample-time drop count is 0 or 1, the frame counts equal fps × duration, and fitting against the sequence number gives residual std 4.62 / 4.64 / 4.62 ms with 25.6999 / 25.7003 / 30.0226 fps (measured offline).
  - Reproduced offline by calling `tsanalysis.fit_frame_index` on the saved arrivals. For the generic camera, removing `nominal_period_ns` fixes the fit (25.6999 fps, 0/0). The C930e DS fit fails with or without the nominal, because slot rounding locks onto 33.43 ms early under the 32/48 ms sawtooth.
- Frame-index model vs the C922's own clocks (measured offline):
  - whole-run index model minus PTS mapping: std 0.347 ms, peak to peak 1.31 ms;
  - causal index model (fitted to arrivals from frame 30) minus whole-run PTS: std 0.40 ms, mean 0.04 ms.
  - Since the first-payload STC is linear in the frame index to 2 µs, the frame-index model and the STC differ only by a constant offset plus the slope error, which is about ±18 ppm, i.e. at most 0.5 ms over 30 s (inferred).

### 3.8 Drop detection

- No drops anywhere in W-TS:
  - C922 `drops_pts.drops = 0` (32-bit unwrap, period = median step);
  - `drops_sample_time.drops = 0` for the C922 and C930e;
  - generic `drops = 1` at `index 1`: the first interval is 64 ms, at start-up (frame 0 has `discontinuity = true`). This is a start-up artefact, not a dropped frame (inferred).
- Only the PTS/STC route detects drops independently of host timing. Sample-time gaps work at 30 fps (a missing frame gives 64–80 ms against 32/48 ms), but not near 60 fps, where the 16 ms grid makes one and two periods ambiguous (inferred; B7). DS cannot detect drops from pts at all.

### 3.9 Real frame rates exposed by the timestamps

These are camera findings for other groups:

- The generic camera runs at **25.70 fps** in the 30 fps mode (both APIs, 772 frames in 30.03 s), while MF `sample_duration` still says 333333 and DS pts say 33.3383 ms. Only arrival/sample-time spacing or a device clock reveals this. REPORT lists the same 25.7 fps. Low light / auto-exposure is the likely cause (inferred; REPORT lists "a brighter-scene run for the generic camera" as still to do).
- The C930e runs at 30.022 fps (+730 ppm against QPC). Without its PTS this run cannot tell its period mode (REPORT finding 10).
- The C922 at 720p60 delivered 30.6 fps in W-MJPEG, with PTS steps of 32.7 ms (90 of 92), so the camera, not the host, set the rate (measured offline, `W-MJPEG/c922…/mf_1280x720_60/frames.jsonl`). A dim scene is the probable cause (inferred).

## 4. What can be concluded about tier 0 vs tier 1 without a ground truth

1. **Every tier-0 Windows timestamp is a host timestamp on a 16 ms grid, or synthesized.** This covers MF sample time, the MF device-timestamp attribute, QPC arrival in MF and in DS, and DS pts. Raw, each gives ±8 ms per frame (4.6 ms rms), so each is `no` by plan §3. This is a property of usbvideo/MF/DS on this machine, independent of camera and of the registry value (measured: 3 cameras, both APIs, 198 MF captures, tier 0 and tier 1).
2. **The tier-0 frame-index model is the only tier-0 candidate.** Its accuracy is bounded by the camera's frame-clock stability, which tier 0 cannot observe. Without a ground truth we can say:
   - for the C922 it agrees with the camera's own STC frame clock up to an offset and a ~±18 ppm slope (inferred);
   - it agrees with PTS to 0.35 ms rms;
   - it cannot detect drops;
   - it assumes a constant frame period. That assumption fails silently on the generic camera if the frame rate changes under auto-exposure, and on the C930e if its period mode switches (REPORT finding 10).
   - The current harness implementation also mis-slots two of six streams (B2), so these numbers need the fix before they mean anything.
3. **Tier 1 adds a device clock.** This run measured it only on the C922. It is self-consistent:
   - rate within −2 ppm of `dwClockFrequency`, monotonic, no drops;
   - first-payload STC regular to 2 µs;
   - PTS regular to 0.35 ms.

   It gives host-independent drop detection and the true frame period. The C922's PTS is the noisier of its two device stamps. Which one (PTS, STC or neither) marks exposure time can only be settled with the flash or ESP32 rig: REPORT's 0.5 ms flash floor cannot separate 0.35 ms PTS jitter from a 2 µs STC.
4. **Tier 1 is camera-dependent, not uniformly good.**
   - Kiyo (selftest): PTS and STC tick at 1 kHz despite a 30 MHz descriptor, with ±3.5 ms jitter.
   - C930e (REPORT finding 10): PTS is a synthetic counter.
   - C922: SOF is invalid (884/s).

   A tier-1 implementation needs per-camera validation: rate vs `dwClockFrequency`, step std, and a SOF rate check, falling back to STC or to the frame-index model.
5. **The causal (live) mapping costs about 30 frames to converge** (offsets up to 1.7 ms, then 0.19 ms std) for PTS→QPC on the C922. A live system should back-fill or flag the first second.

## 5. Harness bugs and fixes

| ID | Severity | File:line | Bug | Fix | Re-run |
| --- | --- | --- | --- | --- | --- |
| B1 | high (reporting) | w_ts.py:33, :242 | The camera × API aggregate ranks `untested` above `no`, so the always-untested `frame_index_fit` hides measured `no` results (5 cells). | Pick the aggregate from the measured sources only (`yes` > `partial` > `no`). Use `untested` only if nothing was measured. Keep `frame_index_fit` as its own column labelled "needs GT", or make the aggregate "best native timestamp". | Re-analysis of the existing W-TS frames is enough. With no re-analysis entry point (B10), re-run W-TS (about 3 min). |
| B2 | high (analysis) | tsanalysis.py:235–261 (`_estimate_period` seeded with nominal), :283–290 (re-slot); called with the nominal at w_ts.py:53 | Slots are assigned by rounding (t − t0)/p with p seeded from the nominal period. This fails when the real rate differs from nominal (generic 25.70 fps → fit 30.72, 159 phantom skips) or under the 32/48 ms beat (C930e DS → 33.43 ms, 31 skips / 35 duplicates). Residuals double (9.4–9.7 ms instead of 4.6). | When no interval exceeds 1.5 × the clean median interval (or the MF sample-time / PTS drop count is 0), use the sequence number as the slot. Otherwise seed p from (t_last − t_first)/(N − 1 + gaps) over gap-free stretches, never from the nominal. Flag `fit_unreliable` when skipped + duplicate slots > 1 % of N. Add unit tests: 16 ms-quantised arrivals at 25.7 fps with nominal 33.3 ms, and 900 frames at +730 ppm. | W-TS re-analysis (or re-run). The same function feeds any other test that calls `fit_frame_index`. |
| B3 | medium | w_ts.py:170 | The synthesized test (`std < 0.001 ms`) misses DS pts with occasional 5 µs corrections (C930e: std 0.0024 ms) → `untested` instead of `no`. | Call pts synthesized when ≥ 90 % of the intervals equal one value exactly, or the intervals take ≤ 3 distinct values, while the arrival interval std is > 1 ms. Also record pts-vs-arrival drift (ms/s). | W-TS re-analysis. |
| B4 | medium | rating.py:124–128 | `rate_ts` returns `partial` ("self-consistency not shown") when `device_ts_self_consistent is False`. That contradicts plan §3, where partial requires self-consistent device timestamps. The selftest Kiyo (1 kHz PTS, step std 2.77 ms) got `partial`. | `if device_ts_self_consistent is False: return untested("device timestamps present but not self-consistent", ev)` (or `no` if non-monotonic). Add a unit test. | W-TS for the Kiyo after a replug. |
| B5 | medium (coverage gap) | w_ts.py:100–111 | The SCR STC, SOF and EOF fields are recorded but never analysed. On the C922 the first-payload STC is the cleanest stamp (2 µs vs PTS 0.35 ms), and the C922's SOF is invalid (884/s). | Add an `uvc_scr_stc` source: unwrap, fit against the sequence number and against arrival, STC − PTS offset, EOF − first STC (transfer time). Add a SOF rate check against 1000/s (HS frame) and a "PTS units vs `dwClockFrequency`" check. Rate STC as its own source. | W-TS re-analysis; Kiyo after a replug. |
| B6 | low | w_ts.py:88–90 | `pts_matches_tier1_flag = False` when 0 frames were captured (Kiyo), which reads as a tier-split violation. | Set `uvc_pts_present` and `pts_matches_tier1_flag` to `None` when `frames == 0`. | Re-analysis. |
| B7 | low | w_ts.py:163, :125 | `mf_sample_time` `drops_detectable` is hard-coded `True`, although a 16 ms grid cannot separate 1 and 2 periods near 60 fps. The DS `drops_pts` count on synthesized pts is reported as 0 drops when it cannot see drops at all. | `drops_detectable = period_ms > 2 × grid_ms`. Set the DS drop count to `None`, with a note, when pts are synthesized. Ignore the interval after a `discontinuity` frame. | Re-analysis. |
| B8 | low | tsanalysis.py:221–229 | In the fallback path `ambiguous_with_period` uses the median interval (already gridded, 32 ms), not `nominal_period_ns`, so the arrival grids of the generic and C930e are flagged ambiguous. Ratings are not affected. | Use `nominal_period_ns` when given. | Re-analysis. |
| B9 | low (process) | run_suite.py (no Kiyo gate) | The Kiyo wedged at its first W-MJPEG stream (13:44 local) and every later Kiyo capture failed. The suite never paused. | After a Kiyo `ERROR_GEN_FAILURE`, mark the Kiyo dead for the rest of the run and ask for a replug (no pnputil restart, per the machine notes). Record `kiyo_dead_since` in each JSON. | n/a |
| B10 | low (tooling) | w_ts.py (no entry point) | Analysis cannot be re-run on the saved `frames.jsonl`, so analysis-only fixes force a camera re-run. | Add `--reanalyse <run_dir>`: load `<raw>/W-TS/*/*/frames.jsonl` and recompute `measurements` and `verdicts`. | — |

**Re-runs needed:**

- **No camera re-run is needed for the C922, generic or C930e** once B10 exists: all W-TS frames are saved (MF 902/772/902, DS 902/773/903). Re-analyse after B1–B3 and B5–B8. Without B10, re-run W-TS alone (`--only W-TS`, about 3 min).
- **The Kiyo needs a replug, then `--only W-TS` on the Kiyo.** This gets its PTS/STC this run is missing and exercises B4.
- **The flash/rig run (`W-TS --flash`, attended) is still the only way** to turn any `frame_index_fit` or `uvc_pts` cell into yes/partial/no on accuracy. Score PTS **and** first-payload STC against it.

## 6. Other notes

- The camera table in `summary.md` shows a stale "Last arrival" for the generic camera (18:17:09Z). W-TS's own arrival snapshot shows 19:44:44Z: the re-arrival during W-MULTI, 21 s before W-TS started. W-TS `arrivals.changes = []`, `unexplained_re_arrival = false`, so nothing re-arrived during W-TS. All three streaming cameras captured cleanly (`capture_ok = true`, rc 0).
- A metadata-on/off A/B is not possible from this run: tier membership is confounded with camera model (plan §2.2). Frame rate and capture success did not differ by tier. The C922 (ON) and C930e (OFF) both delivered about 30 fps with identical grid behaviour (measured).


## Verifier notes

Adversarial check, 2026-11-06. I re-derived the numbers from `W-TS.json` and the raw `frames.jsonl` files, using the suite's own `common/tsanalysis.py` (throwaway scripts in the session scratchpad). I opened no camera and changed no suite or result file. Labels: **measured** means recomputed here; **inferred** means reasoning.

### V1. Confirmed as written (measured)

- **Rating cells.** All 21 cells and the verdict fields cited in §2 match `W-TS.json`. The suite_log tally `{'partial': 2, 'no': 5, 'untested': 14}` matches. One small correction: the C930e `ds` aggregate's `source` is `pyav_pts`, not `frame_index_fit`. Both sources are untested, and `max()` keeps the first.
- **Tier split (TS2, TS3).**
  - W-MJPEG MF frames with PTS: C922 10,875/10,875 (120 files); C930e 0/5,903 (119); generic 0/788 (10); Kiyo 1/1.
  - W-CYC: 450/450, 0/450, 0/450.
  - The Kiyo frame carries `uvc_pts 574724`, `stc 12830816`, `sof 0`.
  - The selftest Kiyo had PTS in 242/242 frames.
- **Grid (TS4, TS5).**
  - Sample-time phase on 16 ms: 1.0 / 0.9999 / 1.0. On 15.625 ms: ≤ 0.0022.
  - Arrival phase: 0.9922–0.9996.
  - The 198 W-MJPEG MF captures with ≥ 40 frames all have phase ≥ 0.9995.
- **TS6.** `mf_device_timestamp == sample_time_100ns` in 902/772/902 frames. Sample time vs C922 PTS: residual std 4.54 ms.
- **TS7.** Arrival minus sample time, medians: 0.371 / 0.650 / 32.34 ms. See V5: these medians hide a bimodal distribution.
- **TS10.** C922 PTS:
  - step std 0.587 ms;
  - clusters 33.62 / 33.03–33.05 / 32.05 / 34.62 ms;
  - vs sequence number: residual 0.347 ms, range −1.07 … +0.25 ms.
- **TS11, TS12.**
  - First-payload STC vs sequence number: 0.0022 ms rms, ±0.006 ms.
  - EOF STC: 0.183 ms.
  - STC − PTS = 33.06 ± 0.35 ms; EOF STC − PTS = 40.05 ± 0.48 ms.
  - Transfer time 6.99 ± 0.18 ms; 6.05 SOF counts.
  - `uvc_eof_pts == uvc_pts` in 902/902 frames.
- **TS13.** SOF steps are 29 (480×) or 30 (421×), i.e. 884.0 counts/s. The Linux quirk citation checks out: linux.md §6.11, commit 9183c6f1a21e.
- **TS14.** Reproduced with `fit_device_clock(..., envelope=False)`: −0.88 / −1.70 / −0.70 ms at frames 30–32, std 0.19 ms, max |Δ| 1.70 ms. With the harness default `envelope=True`, causal minus whole-run is mean +0.25 ms, std 0.40 ms (0.27 ms after frame 60). The envelope-free figure is the cleaner one, but it is not what `W-TS.json` stores.
- **TS15 (Kiyo selftest).**
  - PTS 1001.19 Hz, ppm −999,966.
  - STC is in 30 MHz units, every value a multiple of 30,000 (1 ms).
  - STC ms per PTS tick = 1.00006, but only once frame 0 is excluded (see the B5 row in V4).
- **TS17.** Reproduced exactly:

  | Cell | Fit fps | Skipped / duplicate slots |
  | --- | --- | --- |
  | generic MF | 30.7241 | 159 / 8 |
  | generic DS | 29.5772 | 136 / 20 |
  | C930e DS | 29.9229 | 31 / 35 |

  - Fitting against the sequence number instead gives 25.6999 / 25.7003 / 30.0226 fps with residuals of 4.62 / 4.64 / 4.62 ms. `seq` is contiguous in every file.
- **TS18.** Without `nominal_period_ns`, the generic camera fits cleanly (25.6999 fps, 0/0 slots). C930e DS is still wrong (29.9229 fps, 31/35 slots).
- **TS19.** The generic camera's one drop is at index 1 (sample-time interval 64.0 ms). Every other camera shows 0.
- **TS20.** C930e at 30.022 fps = +733 ppm.
- **TS21.** C922 `mf_1280x720_60`: 93 frames at 30.58 fps, PTS steps 32.7 ms in 90 of 92.
- **C930e DS corrections.** The 333283 steps start at frame 242 and repeat every 12–13 frames.

### V2. Corrections to numbers (measured)

- **TS8 / §3.4 drift is computed from the end points, which carry quantisation noise.** A least-squares slope of (arrival − pts) against arrival gives:
  - C922: **−0.001 ms/s**, not −0.13. The end-point figure of 129 ppm is inside the ±0.5 ms/s that two 16 ms-quantised end points allow.
  - C930e: **−0.70 ms/s**, not −1.25. The end-point figure is inflated by a 39 ms first-frame latency against 1.7 ms at the end.
  - generic: +143.2 ms/s (confirmed).

  So the C930e DS pts do **not** "still run 1.25 ms/s fast". The drift equals the camera's +733 ppm rate error less the 327 × 5 µs corrections (about 54 ppm). That fits the §3.4 heading ("drift equals the camera's rate error") better than the table does.
- **TS9.** The offline STC→QPC fit gives **−1.90 ppm**, not −2.18 (the EOF STC gives −1.91). This does not change the conclusion: the slope's 1σ is ±17.6 ppm (recomputed).

### V3. Disputed calls

1. **B1 is not a harness bug, and the 5 aggregate cells are not artefacts.**
   - `rate_sources` says "the camera x API verdict is the best of them" (w_ts.py:139). The module docstring (w_ts.py:13–14) says the frame-index model stays untested until the flash/rig run.
   - Plan §4 (xplat_capture_plan.md line 224) names "a frame-index fit to arrival (tier 0)" as the Windows timestamp route.
   - So "untested" for the MF and DS aggregates on the generic/C930e (and C922 DS) is the honest answer: the API's designated tier-0 route has not been scored. A measured `no` for one native stamp does not make the API `no`.
   - The measured `no` values are not hidden either. Each source has its own column, added for exactly this reason (w_ts.py:247–248, "review 2026-11-06"), and summary.md shows `**no**` in the `ds:pyav_pts` and `mf:mf_sample_time` columns.
   - The proposed fix ("measured sources only") would turn the generic and C930e MF aggregates into `no`. That contradicts plan §4 before the rig run.
   - Downgrade B1 to a low-severity presentation note: summary.md has no legend saying that the `mf`/`ds` columns are "best available route, including untested ones". Add one line to the legend, or rename the columns `mf (best route)`.
   - Effect on TS1: harness artefacts account for **1** cell (C930e `ds:pyav_pts`, B3), not 6. The C930e `ds` aggregate stays `untested` even after B3 is fixed, by the same best-route rule.
2. **§3.9 cause of the generic camera's 25.70 fps.** "Low light / auto-exposure is the likely cause" is contradicted by REPORT finding 6: 25.7 fps "at fixed manual exposure (so not light-limited)", on every path and both days. It is a camera property, not the scene. The C922 720p60 → 30.6 fps inference (TS21) stays plausible but unproven.
3. **B2's proposed fix would not trigger on this data.**
   - The rule "use seq as slot when no interval > 1.5 × the clean median" fails on every 16 ms-grid stream. The median is 31.999 ms, so 1.5 × median = 47.998 ms, and the 48.004 ms intervals (C922 MF: 75 of them) exceed it. The rule then falls to the "gap-free stretches" path, which every 48 ms interval would break.
   - The "or sample-time drop count is 0" route also fails for the generic camera: `drops_sample_time` = 1, from the start-up interval.
   - Corrected fix:
     - Base the gap threshold on the mean interval, (t_last − t_first)/(N − 1), not the median. Use ≈ 1.5 × mean: 50 ms at 30 fps, 58 ms for the generic camera; a 1-frame drop gives 64–80 ms.
     - Or slot incrementally, n_i = n_{i−1} + max(1, round(Δt_i / p_mean)), iterating p_mean = span / n_last. This uses local intervals, so a slope error cannot accumulate the way the global round((t − t0)/p) at tsanalysis.py:250, 283 and 288 does.
     - Note that at 60 fps on a 16 ms grid, Δt ∈ {16, 32} ms rounds 32/16.7 → 2. Incremental slotting is also wrong there and needs the whole-span method. Add a 60 fps unit test.
   - The diagnosis itself (global rounding with a 16 ms jitter leaves only about 8 ms of slot margin, so the doubling-window refit can lock onto a wrong period) stands.

### V4. Harness bugs: verification

| ID | Real? | Note |
| --- | --- | --- |
| B1 | **No** (design) | See V3.1. A legend tweak at most. |
| B2 | Yes | Lines correct (tsanalysis.py:235–261, 283–290; w_ts.py:53). The fix needs the correction in V3.3. |
| B3 | Yes | w_ts.py:170. The C930e has 2 distinct steps, 575/327 = 64 % modal. The "≥ 90 % identical" clause alone would miss it, so the "≤ 3 distinct values" clause is essential. Suggested addition: an absolute pts-vs-arrival drift above 5 ms/s also marks pts as not the camera's clock (generic: 143 ms/s). |
| B4 | Yes | rating.py:128 (the final `partial`), reached when `device_ts_self_consistent is False`. Selftest Kiyo: `partial`, "self-consistency not shown". **Missed second path:** `pyav_pts` on a grid finer than 4 ms gets `device_ts_self_consistent=False` (w_ts.py:172), so it would also come out `partial`. The same fix covers both. |
| B5 | Yes (coverage gap) | w_ts.py:100–111 analyse PTS only. An STC analyser must drop frame 0: the selftest Kiyo frame 0 STC is 357 ms older than frame 1, while PTS moved only 42 ticks (stale SCR). |
| B6 | Yes, low | w_ts.py:88–90. `bool([])` → `uvc_pts_present=False` ≠ tier-1 `True`. |
| B7 | Yes, low | w_ts.py:163 hard-codes `True`; w_ts.py:125 counts drops on synthesized pts. **Also missed:** w_ts.py:96 and :125 use the *nominal* period (1e9/fps) for drop detection. For the generic camera (real period 38.9 ms) the start-up 64 ms interval counts as 2 periods, and a real 2-frame gap (~117 ms = 3.5 nominal periods) would be counted ambiguously. Fix: use the measured period span/(N − 1). |
| B8 | Yes, low | Confirmed: the generic and C930e `grid_qpc_arrival` have `ambiguous_with_period=true` and `on_grid_fraction=null`. That means they came through the fallback branch (the cluster search fell below 95 % on-grid because of 31/33/47/49 ms outliers), which uses `median_iv` = 32 → ratio 2.0. No rating effect. |
| B9 | Plausible | No dead-device gate exists in `run_suite.py` (grep: no `dead`/`GEN_FAILURE` handling outside wincam.cpp's classifier). Outside this group, so not verified further. |
| B10 | Yes | No reanalyse entry point anywhere in `suite/` (grep). |

### V5. Missed findings

- **The arrival-minus-sample-time medians hide a bimodal split** that REPORT (line 133) says must be reported per mode, never as a median (measured, 4 ms bins):

  | Camera | Sub-ms mode | ~16 ms mode | ~32 ms mode |
  | --- | --- | --- | --- |
  | C922 | 526 (58 %) | 376 (42 %) | — |
  | C930e | 712 (79 %) | 190 (21 %) | — |
  | generic | — | 57 (7 %) | 714 (92 %) |

  TS7's conclusion (the sub-ms mode also appears at tier 0) holds.
- **The harness's stored causal device-clock mapping includes the lower-envelope shift** (mean +0.25 ms against whole-run). A live system using `fit_device_clock(causal=True)` as written inherits that offset during start-up (measured; see TS14 in V1).
- **This run's single Kiyo frame has `uvc_scr_stc` = 12,830,816,** which is not a multiple of 30,000. "Kiyo STC moves in whole ms" therefore rests on one selftest capture only (measured, one frame; it is a first frame, which the selftest shows can be stale).
- **Re-run list after the fixes is unchanged:**
  - re-analysis of the saved W-TS frames once B10 exists (otherwise `--only W-TS`);
  - the Kiyo after a replug;
  - `--flash` for any accuracy rating.

  Since B1 is not a bug, the fixes that change a rating cell are B3 (C930e `ds:pyav_pts` → `no`) and B4 (only with a working Kiyo). B2, B5, B7 and B8 change evidence, not ratings.
