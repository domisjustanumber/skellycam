# Evidence: frame timestamp accuracy on Windows (USB camera study)

Collected 2026-11-09 from `research/usb_cameras/` (skellycam repo, `dom/research` working tree). Paths are relative to the skellycam repo root unless absolute. No camera was opened. One new offline number (§1, OpenCV row) was computed from existing result files with `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/d7b5ebd7-23e2-4038-b89c-9e7af70dd7af/scratchpad/notes/tools/ocv_grid.py` (run: `python -I ocv_grid.py <frames.jsonl ...>` from `research/usb_cameras/results/windows/Gerald/`).

Labels: **measured** (a result file supports it), **code** (read from source), **inferred**. "Tier 1 reference" marks UVC PTS/SCR used only as the camera's own clock to judge host stamps; it is never part of a tier-0 method.

Flash ground truth (GT) conventions, needed to read every number below (`research/usb_cameras/timing/VERIFY_method.md`, `research/usb_cameras/timing/scripts/flash_analyze.py:15-25,129-190`):
- Error = std of (GT exposure start − stamp) after removing one median offset per source. "Offset" = that median; negative means the stamp is later than the exposure start of the ROI rows.
- **Method floor ≈ 0.5 ms** on real data. A perfectly periodic frame counter scores the same as PTS, so every sub-ms number is an upper bound, not an accuracy (VERIFY_method.md:163-171, 200-215).
- The GT assumes an instantaneous display step at vblank. Display scan-out, LCD response, DWM delay, rolling-shutter row and exposure start vs midpoint all fold into the offset. The offset moves **35 ms across image blocks** for one camera and one stamp (VERIFY_method.md:143-151). So **absolute offsets and cross-camera offsets are not measured**.
- `flash_analyze` picks the best-scoring source as the GT reference (partly circular). VERIFY_method.md §1 rebuilt it non-circularly (`seq_periodic_env`, gamma 2.2) for the 10-25 run only.
- C930e exposure is unreliable: MF manual exposure set before streaming took effect in 1 of 5 valid −7 runs (REPORT.md:36). C930e GT built with E = 7.8 ms may be wrong in the other runs ("long state", luma 119–137).

## 1. Every timestamp source measured

All at 1280x720@30 MJPEG unless stated. Flash runs: 30 s, monitor at 59.95 Hz, cameras at manual exposure (−7 = 2^-7 s = 7.8 ms unless stated), AE priority 0 so fps is not exposure-limited.

| Source (what it is) | Camera | Metric, ground truth | Value | File | Caveats |
| --- | --- | --- | --- | --- | --- |
| **MF sample time** (`IMFSample::GetSampleTime` = `MFSampleExtension_DeviceTimestamp` = `ReadSample` timestamp; usbvideo KS presentation time in QPC 100 ns) | C922 | std vs flash GT (best-source reference), 6 valid −7 runs 10-27/28 | **4.40–4.52 ms**; all 7 C922 runs incl. −6/−9: 4.40–4.56 ms | `research/usb_cameras/results/windows/Gerald/timing/rerun_20261027/compact_table_all_runs.txt` (field `os_timestamp` = [std µs, n, offset ms]); REPORT.md:32 | 16 ms grid; 16/√12 = 4.62 ms predicted |
| same | C922 | std vs **independent** GT (seq_periodic_env, gamma 2.2), 10-25 run 1 | 4.75 ms std / 6.08 MAD | VERIFY_method.md:211 | |
| same | C922 | 10-25, 6 runs | 4.0–4.8 ms | `research/usb_cameras/docs/usb_camera_report.md:38` | |
| same | C930e | one valid short-exposure-state run (run b) | 4.7 ms (n = 101) | compact table run `..._exp-7_b`; `results/windows/Gerald/RERUN_20261027.md:149` | rests on 1 run; 10-25 later runs 8.1–11.4 ms, tied to a C930e frame-period mode (REPORT.md:35) |
| same | C930e | independent GT, 10-25 run 1 | 5.13 ms | VERIFY_method.md:211 | C930e E assumed |
| same | all 4 (incl. Kiyo SuperSpeed on Thunderbolt xHCI) | grid check, R2 suite W-TS, 30 s | exact 16.0 ms grid; on-grid 0.998–1.0; phase concentration 0.994–0.9999 | `results/windows/Gerald/suite_20261106T224912Z/analysis/ts.md:99-112`; `W-TS.json` `apis.mf.grid_sample_time` | no GT in this run |
| **MF QPC arrival** (QPC when sync `ReadSample` returns in `mf_uvc_timing`, `timing/src/mf_uvc_timing.cpp:348`; or at `OnReadSample` entry in wincam, `suite/windows/native/wincam.cpp:1680-1681`) | C922 | std vs flash GT, 10-27/28 | **4.59–4.98 ms** (−6/−9 runs: 4.36–4.84) | compact table `host_arrival`; REPORT.md:32 | arrival = sample time + 0.4–0.6 ms, or + k×16 ms (bimodal, see §4) |
| same | C922 / C930e | independent GT, 10-25 | 4.66 / 5.06 ms | VERIFY_method.md:210 | |
| same | C930e | run b | 4.82 ms | compact table | |
| same | generic | flash, 2 runs | 2.3 / 3.6 ms | compact table | **circular** (GT built from this source); verifier: generic accuracy unmeasured (RERUN_20261027.md:152) |
| same | all 4 | R2 W-TS | QPC arrival on 16 ms grid, phase 0.989–0.995 | ts.md:103 | |
| MF undocumented attr `D06F8A46` | C922, C930e | grid; flash | on 16 ms grid, 45–49 µs spread; flash ≈ host arrival (e.g. C930e 4.62 ms, n = 9) | `docs/windows_timer_resolution.md:66`; `timing/rerun_20261027/flash/..._exp-7_a/verify_method.json` `B_gt_variants` | |
| `MFSampleExtension_DeviceReferenceSystemTime` | C922, C930e, generic, Kiyo | presence | null in all 15,005 frames | windows_timer_resolution.md:67 | never set by usbvideo |
| **Frame-index fit to arrival, whole run** (`seq_envelope` / `seq_periodic_env`: lower-envelope line arrival = a + b·seq; non-causal) | C922 | std vs flash GT (best-source ref), 7 runs | **0.43–0.66 ms** (568, 662, 450, 433, 441, 479 µs; n = 17–214) | compact table `seq_envelope` | = method floor; non-causal; no drops in these runs (PTS slot = seq) |
| same | C922 / C930e | independent GT, 10-25 | 0.58 / 0.53 ms std (MAD 0.32 / 0.53) | VERIFY_method.md:207 | equal to PTS: method floor |
| same | C930e | flash 10-27/28 | 0.19–0.44 ms in 4 runs (n = 8–101); **8.36 ms (exp −9) and 6.38 ms (exp −6)** | compact table | exp −9 run had a 2-period PTS step (period-mode change); exp −6 GT reference was `mf_undoc_d06f8a46` (bad GT); n tiny in most C930e runs |
| same | C922 / C930e | 10-25 | 0.41–0.51 ms / 0.52 ms (run 1) | usb_camera_report.md:41 | |
| **Frame-index fit, causal** (tsanalysis `fit_frame_index(causal=True)`) | all 4 | residual vs its own fit (no GT), R2 W-TS | C922 4.61, generic 4.63, C930e 4.66, Kiyo 5.01 ms (MF); DS 4.58–5.04 | ts.md:178-200; W-TS.json `frame_index_fit_arrival.causal.residual_stats_ms` | residual = quantisation, not accuracy. **Never scored against a GT** (§3) |
| Tier-0 cadence-jitter estimate √(σ²_sampletime − 16²/12) | C922 / generic / C930e / Kiyo | offline, R2 | 0.00 / 0.14 / 0.475 / 1.645 ms | ts.md:167-176 and verifier TS11 (ts.md:319) | detects host-visible delivery jitter, not necessarily exposure jitter |
| **UVC PTS via MF metadata, whole-run lower-envelope map to arrival** (tier 1 reference) | C922 | flash, 6 valid −7 runs | 0.47–0.68 ms; 0.40 ms at −9 | compact table `uvc_pts_mapped_direct`; REPORT.md:34 | method floor; non-causal |
| same, causal variants | C922 / C930e | flash, 10-25 run 1 | plain causal 0.59 / 2.7 ms; first-half holdout 1.13 / 3.6 ms; robust causal (per-second minima, start-up rejected) 0.60 / 0.61 ms | VERIFY_method.md:185-191, 209 | PTS mappings, not frame-index fits (`timing/scripts/flash_verify_method.py:19-23,115-158`) |
| PTS at nominal clock, offset only | C930e / C922 | independent GT | 0.55 / 0.59 ms | VERIFY_method.md:192, 208 | slope fit is not what makes PTS score well |
| UVC PTS via SCR (STC/SOF window then SOF→host envelope) | C922 / C930e | flash | 0.45–0.67 / 0.27–0.57 ms (C930e n small) | compact table `uvc_pts_via_scr_lsq_envelope` | non-causal |
| C922 PTS, C922 first-payload STC | C922 | vs ideal frame clock (no GT), R2 | PTS 0.145 ms rms (deterministic even/odd alternation, lag-1 autocorr −0.999); STC **2.2 µs** | ts.md:118-138, 328-333 | tier 1 reference: C922 cadence jitter ≈ 0 |
| C930e PTS | C930e | regularity | synthetic counter (997,222 ticks/frame) with ±1 ms corrections; two period modes 998,400 vs ~997,230 STC ticks/frame | REPORT.md:35; `docs/skellycam_timestamps_review.md:119` | use STC, not PTS |
| Kiyo PTS (1 kHz counter, descriptor says 30 MHz) | Kiyo | std(MF sample time − PTS) | 4.613 ms = 4.619 ms quantisation floor (shifted control 5.27 ms); PTS 1.6 ms rms vs ideal clock | ts.md:142-166, 318 | tier 1 reference; whether PTS marks exposure or a jittery firmware event is open |
| **DS sample time** (PyAV/FFmpeg dshow `pkt.pts` = `IMediaSample::GetTime`) | C922, C930e, generic, Kiyo | regularity vs arrival | synthesized: constant 33.3333 / 33.3383 ms; drift vs arrival: generic +141 ms/s (10-27), +428 ms/s (R2, 17 fps); C930e −1.5 to −1.8 ms/s (−0.74 to −0.77 per segment in R2) | `prior_art/SURVEY.md:50`; ts.md:208-225; REPORT.md:32 | carries no per-frame measurement; C930e pts jumped 56.37 ms at a real 65 ms gap |
| **DS QPC arrival** (PyAV, after demux) | all 4 | grid, R2 | 16 ms grid, phase 0.959–0.999 | ts.md:103 | never scored vs GT; Kiyo DS was a YUY2 fallback |
| PyAV dshow graph-clock mode (`use_video_device_timestamps=0`) | C922, C930e, generic | regularity | 1 ms resolution; arrival − pts ≈ 30 ms (10-25), 36.2 ms (10-27): a cross-clock offset | SURVEY.md:50 | on the ~16 ms arrival grid (SURVEY.md:58-63) |
| GStreamer `mfvideosrc` PTS (running time at reader-thread arrival) | C922, C930e, generic, Kiyo | arrival − PTS | 0.10–0.31 ms; on 16 ms grid | SURVEY.md:48, 56-63; RERUN_20261027.md:217 | not scored vs GT |
| GStreamer `ksvideosrc` PTS (arrival − one frame) | C922, C930e, Kiyo | arrival − PTS | 33.35–33.83 ms; on 16 ms grid | SURVEY.md:49 | proves the grid is below MF (KS path) |
| SDL3 3.4.18 (MF) `timestampNS` | 4 cameras (10-25) | grid | on 16 ms grid | SURVEY.md:58-63; windows_timer_resolution.md:66 | |
| WinRT `MediaFrameReader` (NV12; MJPG subtype delivers nothing) | C922 etc. | grid | on 16 ms grid | windows_timer_resolution.md:66; REPORT.md:24 | |
| nokhwa 0.10.11 `capture_timestamp` (wall clock at stream start + MF sample time) | C922, C930e, generic | grid | on 16 ms grid | windows_timer_resolution.md:66; SURVEY.md:83 | |
| **OpenCV `CAP_DSHOW`** `CAP_PROP_POS_MSEC` | C922, C930e, generic, Kiyo | value | −1 on every frame (`pos_msec` field) | `results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-*/*/frames.jsonl`; skellycam_timestamps_review.md:79 (`cap_dshow.cpp` has no POS_MSEC case) | no device/driver time available |
| OpenCV `CAP_DSHOW` host stamp taken right after `grab()` in a tight single-camera `grab()`/`retrieve()` loop (`mjpeg/opencv/opencv_capture.py:103-104`) | C922 / C930e / generic / Kiyo | **measured (offline, this note)**: residual std of a whole-run sequence fit; 16 ms phase concentration R | 10-25 (idle): C922 4.63 ms, R 0.985; Kiyo 4.71, R 0.906. 10-27 (6 agents loading the machine): C922 4.74–5.67, C930e 5.13–7.81, generic 6.03–6.64 ms; R 0.19–0.82 | the frames.jsonl files above and `mjpeg_resummarized_20261025_data/mjpeg_opencv-dshow-*/` | no GT. Since DS `grab()` is a no-op (code), the stamp of frame k is ≈ the `retrieve()` return of frame k−1 plus loop work, i.e. the 16 ms grid plus decode/scheduling jitter (inferred). Two 10-25 runs were YUY2 at 10 fps |
| libusb/WinUSB host first payload, back-dated by packet index | C930e | flash MAD | 0.39–0.78 ms; libusb arrival 1.0–1.7 ms MAD vs C922 MF OS 5.8–6.1 ms MAD in same runs | REPORT.md:38; `results/windows/Gerald/phase2_libusb_scr_timing/summary_runs2-6.json` | **driver swap: out of scope**. Shown only because it locates the grid in transfer size |
| libusb SCR → QPC via xHCI frame-number IOCTL | C930e | agreement with back-dated arrival | 46–66 µs robust sigma; median offset +0.31 to +0.35 ms | REPORT.md:38-39 | driver swap; IOCTL mapping exact only ~2–3.5 s |
| libusb host-arrival jitter vs packets per transfer | C930e | RMS | 0.43 / 1.2 / 4.6 ms at 8 / 32 / 128 packets | windows_timer_resolution.md:60; `results/agent_reports/phase2_reports_and_verifications.json` | 128 × 125 µs = 16.0 ms; 4.6 ms = 16/√12 |
| `timeBeginPeriod(1)` effect | C922, C930e, generic (GStreamer probes) | arrival-phase jitter | 0.3–0.5 → 0.05–0.08 ms; 16 ms grid unchanged | RERUN_20261027.md:220; windows_timer_resolution.md:76; `results/windows/Gerald/verify_prior_art/gst_capture-*-timeBeginPeriod1/` | global timer already 0.5 ms on Gerald |

## 2. The 16 ms delivery grid

**What it is.**
- Every host-visible frame time on Gerald falls on multiples of exactly 16.0 ms (not the 15.625 ms timer tick). At 30 fps the intervals are 32 ms (≈92%) and 48 ms (≈8%) (ts.md:104-108). **Measured**: `timing/scripts/quantization_check.py` picks 16.0 ms for every field in every run (windows_timer_resolution.md:50).
- **Each stream has its own phase**: C922 at 14.45 ms and C930e at 8.45 ms on the same QPC clock, each with 23–25 µs spread, and 98% of intervals within 100 µs of a 16 ms multiple (windows_timer_resolution.md:51-59, `results/windows/Gerald/timing/verify_rerun_vflash1/grid_phase_check.json`). A global timer would give one phase. **Measured**, one run.
- It holds at SuperSpeed (the Kiyo on the Thunderbolt xHCI) and with or without the metadata registry value (ts.md:101-103). **Measured.**
- Mechanism: `usbvideo.sys` very likely queues isochronous transfers of 128 microframes (16 ms) and stamps a frame when the transfer holding its end completes. libusb with 128 packets per transfer reproduces the 4.6 ms jitter exactly (windows_timer_resolution.md:60-62). **Inferred** (no USB trace yet).

**Sources it affects** (all **measured**): MF sample time / DeviceTimestamp, MF QPC arrival (sync or async), `D06F8A46`, DS QPC arrival, PyAV graph clock, GStreamer mfvideosrc and ksvideosrc, SDL3, WinRT, nokhwa. Not on the grid, but synthesized and useless: DS device sample time. Not on the grid: UVC PTS/SCR (camera clock, tier 1) and libusb with ≤ 32 packets per transfer (driver swap).

**What removes it at tier 0: nothing found.**
- `timeBeginPeriod(1)` does not remove it. It only cut arrival-phase jitter from 0.3–0.5 to 0.05–0.08 ms (wake-up jitter of the reading thread). **Measured.**
- The global timer was already at 0.5 ms (held by another process), so the grid is not the timer. Python 3.13 changes no per-frame time, because QPC is used throughout (windows_timer_resolution.md:28-46, 79-99). **Measured.**
- MF, DS and KS all show it, so no capture API avoids it (REPORT.md:132). **Measured.**
- No usbvideo setting for transfer size was found; the search was not exhaustive (windows_timer_resolution.md:68).
- Untested: the xHCI frame-number IOCTL alongside usbvideo (windows_timer_resolution.md:75). It would map the SCR's SOF to QPC, but the SOF comes from the metadata, so it is tier 1 anyway. The C922's SOF is invalid (884/s), and the Kiyo's is always 0 (ts.md:128, 155).

**Implications.**
- **Per frame:** any raw host stamp has ≈ 4.6 ms rms error (uniform over 0–16 ms of extra latency, ±8 ms peak after offset removal). This is the floor for OpenCV DirectShow, MF and PyAV alike. skellycam's grab-midpoint stamp is at least this bad, plus loop and lockstep error (skellycam_timestamps_review.md P1–P3). Measured for MF/DS; inferred for skellycam.
- **Fitted:**
  - The frame period (33.33 ms) is not a multiple of 16 ms, so the quantisation phase walks: at exactly 30.000 fps it steps 1.333 ms per frame and repeats every 12 frames (12 × 33.33 = 400 = 25 × 16), and camera rate offsets (C930e +746 ppm, Kiyo +693 ppm, ts.md:201-206) fill in between (inferred). The "~12-frame beat" in arrival − sample time fits this (REPORT.md:133, measured).
  - A line through many frames therefore averages the quantisation away. Whole-run fits reached the 0.4–0.66 ms flash floor on the C922 and C930e (measured). The true accuracy is unknown and ≤ ~0.5 ms is only an upper bound.
  - Fits remove only zero-mean jitter. They do not remove a per-camera constant latency (§4).
- **Limits of a fit** (measured unless marked):
  - Start-up: on the C930e the minimum arrival latency was 22.9 ms higher for the first 2 s. A naive causal envelope scored 2.7 ms, a first-half holdout 3.6 ms, and a robust causal fit 0.6 ms (VERIFY_method.md:185-191).
  - Drops: on a 16 ms grid at 30 fps, one missed frame (66.7 ms) still separates from 32/48 ms jitter, but the margin is small (33.3 vs 32 ms). `slot_frames` therefore requires period > 2 × grid. At 60 fps drops are not detectable from host stamps at all (`suite/common/tsanalysis.py:271-277`, code).
  - A camera whose host-visible cadence itself jitters (Kiyo 1.6 ms rms) caps a constant-period fit at that jitter, unless that jitter is delivery-only (open; ts.md:157-166, 334-338).

## 3. Timestamp changes proposed in earlier sessions

**From `docs/skellycam_timestamps_review.md` §6 (lines 99-104), against the old skellycam code:**
1. Stop using the grab midpoint on DirectShow. Use `post_frame_retrieve_ns` (closer to arrival when `retrieve()` actually blocked; it includes DS's MJPEG→RGB24 decode). Run a **frame-slot fit `t_k = a + P·k`** (lower envelope, drop detection) on those post-retrieve stamps.
2. On Linux, store `CAP_PROP_POS_MSEC` (V4L2 buffer time).
3. Fix the local ISO 8601 double-offset bug (`timebase_mapping.py:31,42`) and the false `CAP_PROP_BUFFERSIZE` comments.
4. Move Windows capture to MF (sample time plus arrival, and UVC metadata for tier 1).

**From `docs/windows_timer_resolution.md` "Practical guidance" (lines 106-112):**
- Call `timeBeginPeriod(1)` in each camera worker process; better, block on the capture API instead of sleep-polling.
- Use the `PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION` opt-out if a window-owning process may be minimised.
- Never set `GlobalTimerResolutionRequests`.
- Move to Python 3.13+, or anchor UTC with `GetSystemTimePreciseAsFileTime`, because `time.time_ns()` on 3.12 lags up to one timer tick: a constant per-recording bias, the same for all cameras.
- Mind QPC-to-UTC drift on long recordings (±30–50 ppm). It does not matter between cameras on one PC.

**From REPORT.md (line 13, 128) and `docs/xplat_capture_plan.md` §3 (line 224):** MF native-MJPG passthrough. Timestamps come from a frame-index fit to arrival (tier 0) or UVC PTS (tier 1).
- G-TS pass criteria (xplat_capture_plan.md:237): **yes** = causal per-frame error ≤ 0.5 ms (1σ) vs a GT, with drops detectable; **partial** = ≤ 2 ms, or tier 1 only, or self-consistent device stamps without a GT; **no** = > 2 ms, synthesized, or a host grid.
- `capture_stack_options_plan.md:147` (C1): "one timestamp-fit and drop-detection module". Its §8 decisions (lines 249-260): native Python via ctypes/comtypes; the admin step is optional, so **tier 0 must stand on its own**.

**From `docs/windows_results_20261106.md` §4 and R2 `analysis/ts.md` §4–5:**
- Use the tier-0 cadence-jitter detector √(var − 16²/12) to flag cameras where a constant-period model fails.
- Tier 1 needs per-camera validation: clock units vs fitted rate, a SOF check, skipping frame 0 (stale SCR, 357 ms on the Kiyo), and a host-correlation check to pick PTS or STC.
- Harness fixes that also apply to a production fit:
  - HV3: drop the start-up transient before slotting and fitting. The Kiyo's whole-run residual was 6.29 ms instead of 4.99.
  - H6: on gridded series, count a duplicate only for identical stamps, and require period > 2·grid + 3σ jitter for drops to count as detectable.
  - HV4: use a robust drift slope.
  - H4: exclude interval 0 from the unreliability count (ts.md:262-273, 355-364).

**From `timing/rig/README.md:47-51, 194-205`:** the downstream formula once the anchor is known: `t_light(row y) = ts − K_alpha1 − E/2 + (y/H)·T_ro`. **K_rel** (one camera's K minus a reference camera's K in the same run) is the offset-free answer for cross-camera alignment.

**From `docs/xplat_capture_plan.md:87` and REPORT.md table (line 103):** the frame-index model "scored like PTS (~0.5 ms) only for the C922 and only with a whole-run fit… it cannot see dropped frames the way PTS can".
- Correction: the "causal 0.59–3.6 ms" quoted there is for **PTS→host mappings**, not frame-index fits (`flash_verify_method.py:19-23,126-158`).
- The C930e's PTS is a synthetic counter, so its causal PTS mapping behaves much like a causal frame-index fit (inferred).

### The tier-0 frame-slot (lattice) fit as implemented

Code: `research/usb_cameras/suite/common/tsanalysis.py` (stdlib only), derived from `tools/analyze_frames.py:107-157` and `timing/scripts/flash_verify_method.py:111-158`.

- **Slotting** (`slot_frames`, tsanalysis.py:267-333):
  1. p = span/(N−1).
  2. Find gaps > 1.5·p, trusted only if p > 2 × grid (grid auto-detected).
  3. With no trusted gap, slots are 0..N−1.
  4. Otherwise use incremental slots n_i = n_{i−1} + max(1, round(Δt_i/p)), with p re-estimated as span/n_last until the slots stop changing. These are kept only if they lower the whole-run residual against sequence slotting, which rejects phantom gaps from late/early arrivals.
  5. The nominal period is never used (the generic runs at 17–26 fps in a "30 fps" mode).
- **Fit** (`fit_frame_index`, tsanalysis.py:336-421): least-squares t_i = offset + period·n_i, then shifted onto the lower envelope (2nd-percentile residual, tsanalysis.py:125-129), because arrival = capture + positive latency.
  - Causal mode: running least squares over frames 0..i (optional window), no estimate before 30 frames, envelope = running minimum residual (tsanalysis.py:375-396).
  - `fit_unreliable` is set if skipped + duplicate slots exceed 1% of N, or gaps are undetectable.
  - `analyze_frames.lower_envelope_fit` (tools/analyze_frames.py:144-157) instead refits iteratively on the lowest 10% of residuals, then shifts to the 2nd percentile.
- **Drop detection** (`detect_drops`, tsanalysis.py:510-535): gaps of k periods in a counter or periodic clock count as k−1 drops.
- **Assumptions:**
  - A constant camera frame period for the whole fit window. That needs fixed exposure: auto exposure lowers fps (generic 17.15 fps under AE in evening light vs 25.7 fixed; ts.md:256; REPORT.md:26).
  - No period-mode switch: the C930e has two modes, 998,400 vs ~997,230 ticks per frame, about 0.12% apart, trigger unknown (REPORT.md:35).
  - A latency whose minimum is constant after start-up.
  - Zero-mean exposure cadence jitter.
- **Validation without GT** (measured):
  - R2 fits match the measured period on every camera (generic 58.32 ms, Kiyo and C930e 33.31 ms).
  - The incremental slotting found the one real C930e DS gap (65.34 ms; the DS pts jumped 56.37 ms there).
  - It correctly rejected 4 Kiyo start-up gaps, which PTS (tier 1 reference) showed were not drops (ts.md:193-200).
- **Scored against ground truth? No, for the causal tier-0 fit.** Confirmed:
  - W-TS hard-wires `frame_index_fit` to untested (`suite/windows/tests/w_ts.py:337`, per ts.md:29).
  - The docs say "unscored until A5": `docs/capture_stack_options_plan.md:247`; also windows_results_20261106.md:27, 176, 208, 408-411; xplat_capture_plan.md:461.
  - A5 needs the AtomS3/ESP32 strobe rig. The firmware compiles but was never flashed, nothing is built, and `timing/rig/` is synthetic-tested only (`sync_rig/README.md:15-22`, `timing/rig/README.md:3-5, 244-247`).
  - Only the **non-causal, whole-run, sequence-number** version (`seq_envelope`/`seq_periodic_env`) was scored on flash data: 0.43–0.66 ms on the C922, at the method floor.
  - Drop handling was never exercised in a GT-scored run: those runs had 0 drops.
  - The raw flash MJPEG was not kept, so the flash GT cannot be rebuilt to score a causal fit offline (§5).

## 4. Latency and bias from light on the sensor to each stamp

| Stage | Value | Per-camera difference | Source / label |
| --- | --- | --- | --- |
| Exposure start → exposure midpoint | E/2: 3.9 ms at −7; up to ~16 ms under AE at 30 fps | moves with each camera's exposure; AE changes it frame to frame | arithmetic; VERIFY_method.md:145 |
| Rolling-shutter readout, row 0 → last row | C922 30.1–31.5 ms per frame height (L ≈ 43 µs/row); C930e ~29.8–30.5 ms in the valid runs (other runs 14–43 ms with large fit residuals); libusb C930e ~29–30 ms | generic and Kiyo **unmeasured** | compact table `flash_rows.readout_ms_full_height`; RERUN_20261027.md:150; usb_camera_report.md:62. Upper bound: the 31 ms row term cannot be separated from display scan-out (VERIFY_method.md:150-151) |
| What the camera stamps (PTS) | C922 PTS near the end of exposure: offset moves −1.14× the exposure change (−50.97 / −58.83 / −67.64 ms at 1.95 / 7.81 / 15.63 ms) | C930e PTS synthetic; Kiyo PTS 1 kHz; generic none | REPORT.md:37; usb_camera_report.md:50 (provisional, one run per exposure) |
| PTS → first payload on USB | C922 STC − PTS = 32.98 ± 0.14 ms (one frame period); C930e 30.4–35.4 ms | camera-specific | ts.md:126; compact table `stc_minus_pts_ms` (tier 1 reference) |
| USB transfer of one MJPEG frame | C922 7.07 ± 0.23 ms (EOF STC − first STC, 720p) | Kiyo unmeasurable (EOF SCR = first); scales with JPEG size (inferred; frame size depends on scene and autofocus, REPORT.md:134) | ts.md:127 |
| Frame end → usbvideo completion (MF sample time) | 0–16 ms, uniform: the 16 ms grid | per-stream phase (C922 14.45 vs C930e 8.45 ms) | §2 |
| MF sample time → app QPC arrival | bimodal: +0.4–0.6 ms, or +16 / +32 ms. Shares of the sub-ms mode: C922 58%, C930e 80%, Kiyo 96%, generic 0% (91% at +32.5 ms) | strongly per camera, stable across runs; the generic is always 16–32 ms late | ts.md:228-241 (measured). The C922 median moved ~16 → ~1 ms when the metadata value was set (xplat_capture_plan.md:76) |
| Python callback overhead (pymf) | `qpc_ns` = callback entry + GIL wait; MF sample time is unaffected | n/a | `suite/windows/pymf/mf.py:10-16` (code); W-PYMF not yet run |
| DS (OpenCV) path | sample grabber forced to RGB24, so the MJPEG is decoded on DS's streaming thread before `SampleCB`; `retrieve()` returns the **oldest** unread frame and newer samples are discarded while one is unread | decode time scales with resolution | skellycam_timestamps_review.md:32-36 (code, `cap_dshow.cpp`) |
| **Total, exposure start (ROI rows) → stamp**, flash offsets | C922: arrival −56.3 to −64.1 ms, sample time −51.4 to −58.7 ms (−7 runs). C930e (short state, run b): arrival −68.5, sample time −66.0 ms; long-state runs −76 to −87 ms. Generic: arrival −59.4 / −61.5, sample time −27.6 / −29.4 ms | C922 vs C930e differ by ~5–12 ms in the same runs; generic sample time is ~30 ms "earlier" than the others' | compact table (offset = third number). **Not comparable as absolute latency**: ROI row and column (35 ms spread), display scan-out and the C930e exposure state are folded in, and the generic GT is circular |

What follows for cross-camera sync (inferred from the rows above):
- Removing per-frame jitter leaves a **per-camera constant latency** that differs between models. The 16/32 ms delivery modes, readout, PTS position, transfer size and stamp point all differ. Its size between models is unmeasured; the flash method cannot resolve it (VERIFY_method.md §6; REPORT.md:40 finding 15).
- With AE, E varies, so a readout-anchored stamp moves against the exposure midpoint by up to E/2.
- The rig's K_rel and alpha are the planned measurements (timing/rig/README.md:13-56). Never run.
- Best measured cross-camera figure: C930e (libusb SCR) − C922 (MF PTS) offset spread 0.54–0.79 ms across 5 runs with a fixed ROI, about the GT floor (REPORT.md:40). Both are tier-1 or driver-swap sources.

## 5. Raw per-frame data available for re-analysis

QPC ns throughout (10 MHz QPC, so ns = ticks × 100). Raw MJPEG/pixel data for the flash and libusb runs was **not kept** (`timing/rerun_20261027/COMMANDS.txt` "Raw .mjpeg stays in SCR", a scratchpad since deleted; `phase2_libusb_scr_timing/COMMANDS.txt:3`). So the flash GT exists only as aggregates (`flash_analysis.json`, `verify_method.json` per source/variant: n, offset, std, MAD, min/max). It cannot be rebuilt per frame, but host stamps can be re-fitted and compared with each other and with tier-1 PTS/STC.

Schema A, `mf_uvc_timing.exe` `<key>.frames.jsonl` (C++ MF, sync ReadSample): `seq, host_arrival_ns, readsample_call_ns, mf_sample_time_100ns, mf_device_timestamp, os_timestamp_ns, mf_undoc_d06f8a46_ns, mf_sample_duration_100ns, reader_flags, payload_bytes, jpeg_soi/eoi, mjpeg_offset, meta_len, meta_hex, meta_items[{id, size, sof:{pts, scr_stc, scr_token, scr_sof}, eof:{…}}], attrs{…}`. Display, `display.jsonl`: `{"type":"present", i, present_count, level, present_call_ns, present_return_ns}` and `{"type":"stats", present_count, present_refresh_count, sync_refresh_count, sync_qpc_ns, queried_ns}`. Session JSON has controls and exposure readback.

Schema B, wincam/pymf `frames.jsonl` (suite, async `OnReadSample`): `seq, qpc_ns, sample_time_100ns, readsample_ts_100ns, sample_duration, flags, discontinuity, bytes, soi, eoi, eoi_trailing_bytes, sof0_w/h, uvc_pts, uvc_scr_stc, uvc_scr_sof, uvc_eof_pts, uvc_eof_scr_stc, uvc_eof_scr_sof, has_metadata, capture_metadata_attr, mf_device_timestamp`. DS (PyAV) variant: `seq, qpc_ns, pts, dts, time_base, pts_ns, bytes, …`.

Schema C, common per-frame schema (`mjpeg/`, `prior_art/`): `camera_key, backend, seq, host_arrival_ns, os_timestamp_ns, os_timestamp_source, uvc_pts, uvc_scr_stc, uvc_scr_sof, device_clock_hz, payload_bytes, …`, plus backend extras: msmf `sample_time_hns, device_timestamp, readsample_ts_hns, mf_systime_at_arrival_hns, device_reference_system_time`; pyav `pkt_pts, pkt_dts`; gst `gst_pts_ns, gst_dts_ns, gst_duration_ns`; sdl3 `sdl_ts_ns`; opencv `pos_msec` (−1), `frame_crc`, `repeat_of_previous`.

Schema D, libuvc (libusb/WinUSB) `frames.jsonl`: `host_arrival_ns, os_timestamp_ns, uvc_pts, uvc_scr_stc, uvc_scr_sof, uvc_scr_stc_first, uvc_scr_sof_first, host_first_payload_ns, host_last_payload_ns, first/last_payload_packet_idx, packets_per_transfer, payload_count, error_payload_count, device_clock_hz`, plus `usb_frame_qpc.jsonl` (xHCI frame number ↔ QPC samples).

| Data set (under `research/usb_cameras/results/windows/Gerald/` unless absolute) | Schema | Cameras, mode, exposure | Frames | Host stamps | MF sample time | PTS/SCR | Flash GT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `timing/rerun_20261027/flash/<9 runs>/capture/*.frames.jsonl` + `display_m0/display.jsonl` (10-28) | A | C922 + C930e (7 runs: −7 ×5 incl. invalid run d, −9, −6), C922 + generic (2 runs, −7); 720p30 | C922 893, C930e 890–891, generic 772 per run | yes | yes | C922 and C930e yes; generic none | aggregates only (`flash_analysis.json`, `verify_method.json`, `compact_table_all_runs.txt`); run d INVALID (display glitches) |
| `timing/rerun_20261027_verify/flash/` (2 runs: C922+C930e −7, C922+generic −7) | A | same | 893 / 891 / 772 | yes | yes | C922, C930e | aggregates |
| `timing/flash_run1_repositioned/`, `flash_run2_exp-6/`, `flash_run2_exp-9/`, `flash_run2_expseries_capture/exp-6,-9/`, `flash_verify_0_c922only/`, `flash_verify_1/`, `flash_verify_2/`, `flash_verify_2a_c930eonly/`, `flash_verify_3_exp-9/`, `flash_verify_4_exp-6/`, `verify_rerun_vflash1/` (10-25 / 10-26) | A | C922 and/or C930e, 720p30, −7 / −6 / −9 | 889–893 each | yes | yes | yes | aggregates; `flash_run1_repositioned/verify_method.json` has the independent-GT tables; `verify_rerun_vflash1/grid_phase_check.json` |
| `timing/rerun_20261027/metadata_check/` (C922 292, C930e 287, generic 254), `timing/rerun_20261027_verify/metadata_check/` (293, 288), `timing/meta_check1/` (142, 138), `timing/metadata_check_c930e_after_rollback/` (138), `timing/rerun_20261027/order_ae_c930e/` (167) | A | 720p30, ~10 s, no flash | as listed | yes | yes | C922/C930e yes, generic none | none |
| `timing/baseline_nometa_auto/` (10-25) | A | C930e 290, C922 293, **Kiyo 275**; auto exposure; no metadata | as listed | yes | yes | none | none |
| `phase2_libusb_scr_timing/raw/{precheck,run1,run2_cas,run3_ppt8,run4_cas,run5_cas,run6_cas}/` and `phase2_timing_verify/raw/{vA_cas,vB_nocas,vC_nocas,vD_ppt8}/` | D (C930e libusb) + A (C922 MF) + display | C930e on WinUSB (driver swap) + C922 MF; 720p30; flash | C930e 604–923, C922 653–953 per run | yes | C922 yes | C930e SCR (libusb), C922 PTS (MF) | aggregates (`run*_analysis.json`, `summary_runs2-6.json`) |
| `C:/Users/Dom/Documents/skellycam-raw/results/windows/Gerald/suite_20261106T224912Z/W-TS/<cam>/{mf,ds}/frames.jsonl` (R2, 11-06, outside repo) | B | C922, C930e, generic, Kiyo; 720p30; 30 s per API; generic at AE (17.15 fps) | MF: 901 / 902 / 516 / 902; DS: 902 / 902 / 516 / 892 (Kiyo DS = YUY2 fallback) | yes | MF yes | MF: C922 + Kiyo (PTS, STC, SOF, EOF); C930e, generic none | none |
| `C:/Users/Dom/Documents/skellycam-raw/results/windows/Gerald/suite_20261106T181941Z/W-TS/...` (R1) | B | C922, C930e, generic (Kiyo 0 frames) | MF 902 / 902 / 772; DS 902 / 903 / 773 | yes | MF yes | C922 | none |
| `kiyo_overnight_20261106/final_stream/frames.jsonl` | B | Kiyo, 720p30 | 90 | yes | yes | PTS/STC (1 kHz) | none |
| `prior_art_gst_capture-{mfvideosrc,ksvideosrc}/`, `prior_art_sdl3_camera/`, `prior_art_pyav_dshow{,-wallclock,-kiyo-720p}/`, `prior_art_rerun_20261027/...`, `prior_art_rerun_20261027_adversarial_verify/20261028T034622Z_gst_mf_pyav_ks/`, `verify_prior_art/{gst_capture-*,gst_capture-*-timeBeginPeriod1,sdl3_camera,pyav_dshow-verify}/` | C | C922, C930e, Kiyo, generic (varies); 720p30; ~6 s | 148–183 per file | yes | backend pts (gst, sdl3, pyav) | none | none |
| `mjpeg_*/<mode>_<cams>/frames.jsonl` (`mjpeg_msmf`, `mjpeg_pyav-dshow`, `mjpeg_opencv-dshow-{decode,raw}`, `mjpeg_opencv-msmf-*`, `mjpeg_winrt*`; 10-25, `mjpeg_rerun_20261027/`, `mjpeg_resummarized_20261025_data{,_b}/`, `mjpeg_adversarial_verify_20261028/`) | C | all cameras, 720p30 and 1080p30/60, single and multi-camera; ~10 s | ~250–370 per camera | yes (OpenCV: after `grab()`) | msmf yes | msmf only header size, no PTS values | none |
| `rust_nokhwa_capture/*/frames_*.jsonl`, `verify_rust/*` | C | C922, C930e, generic | ~150–600 | yes | MF-derived | none | none |
| `results/windows/Gerald/rig_anchor_selftest/selftest_*.json` and scratchpad `anchor_work/` | rig | **synthetic** cameras A/B | — | synthetic | — | synthetic | synthetic truth only |

Analysis tools already in place:
- `tools/analyze_frames.py`: periodic fit, lower envelope, PTS→host map.
- `suite/common/tsanalysis.py`: slotting, causal/whole-run frame-index fit, drops, grid.
- `timing/scripts/quantization_check.py` and `verify_grid_phase.py`: grid and phase.
- `timing/scripts/flash_analyze.py` and `flash_verify_method.py`: these need the MJPEG, which is gone for past runs.
- `suite/windows/tests/w_ts.py --reanalyse`: re-rates the W-TS raw files.
