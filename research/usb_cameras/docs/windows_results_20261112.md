# Windows results, Gerald, 2026-11-11/12

Write-up of the overnight `suite/windows` run started from
[HANDOFF_OVERNIGHT_20261111.md](../suite/windows/HANDOFF_OVERNIGHT_20261111.md). It answers the questions in that
handoff's §1, one section per plan decision. The previous run's write-up is
[windows_results_20261110.md](windows_results_20261110.md) ("11-10" below).

**Labels:**
- [M] measured: a result file and field support it.
- [C] code: read from the source.
- [I] inferred: reasoning.
- [NV] not verified.

**Conventions:**
- Times are local (UTC−5), with UTC in brackets where it matters.
- `R/` = [`results/windows/Gerald/suite_20261112T025937Z/`](../results/windows/Gerald/suite_20261112T025937Z/).
- Camera keys are shortened: Kiyo Pro `1532:0e05`, C930e `046d:0843`, C922 `046d:085c`, generic `4c4a:4a55`.

**The results were redacted** with `tools/redact_run.py --apply` (7 serials, 1,943 replacements, 52 paths renamed). The 11 sample JPEGs were moved to `skellycam-raw` (mirrored paths). A re-check finds 0 serials and 0 media files left.

## 0. Summary

| Decision | Verdict tonight | Short reason |
|---|---|---|
| 1.3 pymf as the Windows backend | **Supported, with one qualification** | pymf = wincam on all 4 cameras. One process carried 3 cameras at 720p30 for 10 min with 0 lost frames, with ms-level control sets mid-stream and in-use detection. The 4th camera (C922) was refused for **USB bandwidth** (its hub, shared with the generic camera). Every API gets the same refusal, so it's the topology, not pymf. |
| 1.3 reliability (≥ 381 failure-free cycles) | **MF in-process: yes on all 3 cameras tested.** MF new-process: yes on the C930e and C922; **no on the generic** (397/400, the device dropped off the bus once) | The Kiyo Pro was dead before its cycling test, so it is **untested** tonight. |
| D10–D12 controls lock | **Yes on all 4 cameras** | 10-min soak + 3 restarts. Every readback stayed at its locked value; luma and R/B stayed inside limits. The C922's R/B worst case was +1.44 % (smoke: −3.4 %). |
| D9 / §5.2a gain limit | **The rule works and repeats on the C930e and C922. Two assumptions need changing; thresholds need Dom's choice** | Noise ratio (rho) **falls** with gain, so the "rho rises" check is wrong. The detail-loss criterion (D) is what binds (0.850–0.857 in 20/20 runs). g_lim spread: 20–23 (C930e), 28–30 (C922) over 10 runs. The Kiyo Pro is inconclusive. |
| Exposure ceiling at 30 fps | C930e −5, C922 −5, **Kiyo Pro −7** (not −5), generic 1 (its units) | The Kiyo Pro *starts* at −6, which is past its ceiling (28.7 fps). |
| 1.0 package bump (T-BUMP) | **Untested: neither recording ran** | skellycam (baseline *and* HEAD) failed to open the generic camera through OpenCV DSHOW with all 4 cameras connected, then failed the whole group with HTTP 500. Same failure on both, so it is not a bump regression [M]. Probably the same hub bandwidth limit [I]. |
| 1.3/1.11 multi-camera, MF vs DS | **MF classifies refusals exactly** (`0x800718CF`); DS only as "probable" | The C922+generic pair at 720p30 (81 % of a microframe) was refused on every API, every time. 960×720 streamed. |
| Kiyo Pro | **Died at 00:46:24 (05:46:24Z) in W-MULTI**, the DS all-at-once round 029, plug-in age 379 min | The suite's dead rule held. No diagnosis (Dom's rule). |

The run itself: 21:59:38 → 03:10:33 local (02:59:38Z → 08:10:33Z), 5 h 10 min against a 9 h 31 min estimate, `interrupted` false [M] (`R/run_suite.json` `elapsed_s` 18,655). Every test ended `ok`, with two exceptions: W-TBUMP was "ok (with errors)" (2 errors, §5), and W-PYAV-LIST was skipped because the Kiyo Pro was dead [M] (`run_suite.json status[]`). The early finish is mostly the Kiyo Pro's skipped work: W-CYC-KIYO (1 h 45 min estimated) and the Kiyo Pro's share of W-CYC [I].

**Machine state** [M] (`R/W-ENV.json`):
- Windows 10.0.26300 (26H2), Python 3.12.13, numpy 2.5.4.
- Balanced power plan, USB selective suspend on, USB 3 LPM "Moderate power savings".
- All 4 cameras on `usbvideo`, problem code 0. Frame Server running.
- Before the run Dom closed Firefox, LogiTune, Logi Options+ and Razer Synapse. W-ENV's process scan matched nothing.
- 6 `msedgewebview2` processes remained (checked at 21:59). W-ENV's patterns don't include it, so it isn't in the JSON [C] (`suite/windows/tests/w_env.py:54`).
- **The scene** was a static target with room lights on, set up by Dom. W-GAIN's forced short exposures ran very dark: luma 2–28 at gain minimum [M] (`W-GAIN.json per_mode.*.rule_plan.forced.why`).

## 1. Decision 1.3: pymf as skellycam's Windows capture backend

### 1.1 pymf = wincam (W-PYMF, 03:14–03:26Z)

pymf (the pure-Python comtypes MF reader) is equivalent to wincam (C++) on all 4 cameras, with every criterion met [M] (`R/W-PYMF.json verdicts["pymf_equivalence|*|pymf"]`).

| | Kiyo Pro | C930e | generic | C922 |
|---|---|---|---|---|
| fps ratio pymf/wincam | 0.9996 | 0.9998 | 1.0001 | 1.0000 |
| open-to-first-frame delta, ms | −0.87 | +1.58 | −2.08 | +1.42 |
| arrival-delay std wincam / pymf, ms | 0.282 / 0.298 | 0.295 / 0.298 | 0.322 / 0.390 | 0.271 / 0.301 |
| drops | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

Source: `measurements.cameras[*].capture_compare` [M].
- **pymf_inproc cycles:** 60/60 on every camera, 0 hangs, Wilson lower 0.940 [M].
- The generic camera was untested on 11-10 (it fell off the bus). It is 60/60 now.
- **The "all: partial" rating is out of date** [C]. It says "control sets on a streaming source not tested through pymf". That is a fixed cap in `tests/w_pymf.py:578, 592-593`, and W-PYMF-ALL now tests exactly that (§1.2).

### 1.2 One pymf process, all cameras (W-PYMF-ALL, 03:26–03:40Z)

**720p30, one 600 s session** [M] (`R/W-PYMF-ALL.json measurements.cameras[*].all_720p30`):

| | Kiyo Pro | C930e | generic | C922 |
|---|---|---|---|---|
| fps (fit) | 29.38 | 30.05 | 25.76 | **refused** |
| frames, all valid JPEG | 17,626 | 18,041 | 15,478 | 0 |
| lost frames (MF sample-time slots) | 0 | 0 | 0 | – |
| arrival gaps > 1.5 periods: count / max | 10 / 79 ms | 0 | 2 / 50 ms | – |
| first frame, ms | 888 | 474 | 88 | – |
| stop → released, ms | 1,117 | 374 | 305 | – |

- **CPU:** 7.3 % of one core for the whole process, about 2.4 % per camera, without JPEG decode [M] (`parts.all_720p30.cpu`).
- **Frame writer:** 402 written, 0 dropped [M].
- **The C922 refusal is bandwidth:**
  - `0x800718CF` (USB_INSUFFICIENT_BANDWIDTH), class `bandwidth_certain`, 351 ms after the session started. The generic camera was streaming on the same hub [M] (`cam[C922].all_720p30.error`, `.same_hub_streaming`).
  - W-MULTI gets the same refusal on every API (§6). So it's the HS13 hub, not pymf [I].
  - The 3-camera smoke run on 11-11 didn't include the C922, which is why it passed.
- **Why the Kiyo Pro and generic are "partial":** neither lost a frame [C].
  - Both deliver below 30 fps. The generic camera's own rate is 25.76 on every API [M] (`W-MJPEG.json`).
  - The rating exempts "a lower rate that is the camera's own" only when the arrival-gap count is 0 (`tests/w_pymf_all.py:414-421`). The Kiyo Pro's 10 gaps and the generic's 2 remove the exemption, although both pass the gap criterion itself.
  - The generic's two gaps (50.0, 50.3 ms) are what the 16 ms host clock grid produces [I].
- **Answer to the handoff's question:** one pymf process did *not* carry all four cameras at 720p30, but only because of the topology. Everything it was allowed to stream, it carried without loss [M].

**720p60, 180 s** (the Kiyo Pro and C922; the C930e and generic have no MJPG 60 fps mode at 720p):

| | Kiyo Pro | C922 |
|---|---|---|
| negotiated | 60/1, read back ok | 60/1, read back ok |
| delivered fps | **30.02** | **59.21** (fit 59.27) |
| sample period | 33.3 ms | 16.9 ms |

Source: `cam[*].all_720p60.metrics` [M].
- **pymf gets about 60 from the C922.** This confirms the handoff §7 caveat: wincam's 30–35 fps there is a wincam effect.
- **The Kiyo Pro gives 30 even through pymf**, so its 30 fps in the 60 fps mode is *not* the wincam effect [M]. Its exposure was in auto [M]. Whether the camera itself limits it is [NV].
- W-MJPEG agrees (Kiyo Pro 1280×720@60: 30.09 MF, 30.02 DS) [M] (`W-MJPEG.json modes[1].apis.*.fps_steady`).
- **New, against §7:** W-MJPEG's MF route got 59.52 fps (180 frames) from the C922 at 720p60 tonight. On 11-10 it got 40.2 (slow start) [M]. So wincam doesn't *always* stall at 30–35 [I]. W-GAIN's grid cells also reached 59.3–59.45 partway through some captures (§4.2).

**Control sets mid-stream** (exposure, set at 120 s) [M] (`verdicts["pymf_streaming_set|*|exposure"]`):

| | call, ms | frames to change | ms to change | rating |
|---|---|---|---|---|
| Kiyo Pro | 1.7, 2.2 | 3, 5 | 176, 191 | yes |
| C930e | 3.3, 5.6 | 2, 2 | 94, 92 | yes |
| generic | 2.9, 2.0 | 2, 2 | 109, 111 | partial |
| C922 | – | – | – | untested (refused in part 1) |

- **The generic camera is partial on direction only.** The first set went from auto (reading −6) to manual −4. Luma *fell* (152.9 → 103.4), although a longer exposure should brighten [M].
- The −6 read in auto is probably not the exposure AE was really using [I]. Read-back in auto mode can't be trusted on this camera.

**In-use detection: yes** [M] (`verdicts["pymf_in_use|046d:0843..."]`):
- Target C930e, held by the pymf session.
- A second wincam open and a second pymf open were both refused with `0xC00D3704` (MF_E_HW_MFT_FAILED_START_STREAMING) at `first_sample`, class `in_use`.
- The running session was not disturbed.
- IMFSensorActivityMonitor listed the camera.
- That HRESULT's text says "lack of hardware resources". Classing it as in-use relies on context [I].

### 1.3 Verdict for 1.3

- **pymf is fit to be skellycam's Windows backend** [M+I]:
  - equal to wincam;
  - 0 lost frames;
  - about 2.4 % of a core per camera;
  - ms-level control sets mid-stream;
  - bounded release (≤ 1.1 s);
  - in-use detection.
- **Still open:**
  1. A refused camera must be handled per camera. Classify `0x800718CF` as bandwidth, keep the other cameras streaming, and tell the user which port to move it to. That is package 1.11, and today skellycam fails the whole group (§5).
  2. The Kiyo Pro's 30 fps cap at 720p60 [NV cause].
  3. `0xC00D3704` as an in-use signal needs a second case (a different holder process) [I].
  4. The W-PYMF "all" cap and the W-PYMF-ALL low-rate exemption need fixing in the suite (§9).

## 2. Decision 1.3: reliability (W-CYC, 00:52–03:10)

**The bar:** ≥ 381 failure-free open/close cycles, i.e. Wilson lower bound ≥ 0.99 on "first frame within 2 s" [M] (`R/W-CYC.json verdicts["reliability|*|*"]`). Hangs were 0 in every cell.

| Camera | MF in-process | DS-ffmpeg in-process | MF new-process | open → first frame p50 / p95 (MF in-proc) |
|---|---|---|---|---|
| C930e | 400/400, LB 0.9905, **yes** | 400/400, **yes** | 400/400, **yes** | 515 / 523 ms |
| generic | 400/400, **yes** | 400/400, **yes** | **397/400, LB 0.9782, partial: no** | 99 / 180 ms |
| C922 | 400/400, **yes** | 400/400, **yes** | 400/400, **yes** | 331 / 337 ms |
| Kiyo Pro | untested (dead) | untested (dead) | untested (dead) | – |

Source: `measurements.cameras[*].variants[*].summary`, `verdicts[*].evidence.wilson95_lower_first_frame_within` [M].
- **Small variants:** ds_inproc 50/50, ds_newproc 15/15, and on the C922 mf/ds_modeswitch 25/25. All pass, but n < 381 [M].
- **The generic camera's "rate < 90 % of requested" note** is its own 25.76–25.9 fps (30/1 negotiated), the same as on 11-10 [M].

**The generic camera's 3 failures** (MF new-process, cycles 95–97, 02:09:23–02:09:38 [07:09Z]) [M] (`W-CYC/usbcamera_4c4a-4a55_2/mf_newproc_cycles.json`; raw summaries in skellycam-raw):

| cycle | what happened |
|---|---|
| 95 | Activate ok; first sample timed out after 5.0 s (no HRESULT); release took 4.9 s |
| 96 | the camera was missing from MF's device list ("no MF device matches") |
| 97 | Activate timed out after 5.0 s; the device **re-arrived** at 07:09:33.31Z |

- Cycle 98 onwards was ok (first frame 244 ms).
- The health probe passed at 02:18:38 and the fault was cleared [M].
- The `0x8007001F` in the fault record is the suite's label for class `device_error`, not a returned HRESULT [C] (`suite/windows/suitectx.py:736`).
- The fault record's plug-in age (1,018 min) is stale. The camera had re-arrived at 05:50Z during W-MULTI, so its real age was about 79 min [M/I].
- **This is the generic camera dropping off the bus again.** It also re-enumerated twice in W-MULTI (05:40Z, 05:45:47Z) [M], and on 11-10 it dropped off in W-PYMF [M]. No diagnosis here [NV].

**The OpenCV variants all fail on latency** (first frame within 2 s) [M]:
- p50 open → first frame:
  - C930e: 4.2 / 5.3 / 6.4 s;
  - C922: 3.0 / 4.0 / 4.7 s;
  - generic: 2.0 / 2.1 / 2.7 s.
- opencv_inproc delivered YUY2 at about 10 fps on the C930e and C922 (a format mismatch).
- The C922 opencv_skellycam_fps30 ended at MJPG 29.88 fps.

**Verdict:**
- MF in-process meets the bar on all three cameras tested [M].
- MF new-process meets it on two. The generic's miss is a device dropout, not an MF error path [I].
- **DirectShow via the ffmpeg CLI is not needed for reliability.** It also passes, but it has no advantage [M].
- **Still open:** the Kiyo Pro has no cycling result tonight. Its 11-10 numbers stand.

## 3. Decisions D10–D12: controls locked at their start values (W-NODRIFT, 22:40–23:25)

What W-NODRIFT does, per camera:
- locks WB, exposure, focus and the image controls at their start values, with AE priority 0 and power-line frequency 60 Hz;
- soaks 10 min;
- then does 3 stop/starts.

**All 4 cameras are yes, 7/7 criteria** [M] (`R/W-NODRIFT.json verdicts["G-CTRL-NODRIFT|*|mf"]`).

| Camera | locked exp / gain / focus / WB | readback deviation | luma max dev (±5 %) | R/B max dev (±3 %, provisional) | fps per stream | lost frames |
|---|---|---|---|---|---|---|
| Kiyo Pro | −6 / 0 / 0 / 5000 | 0 | 0.0 % | −0.54 % | 28.6–28.7 | 4 events / 32 frames |
| C930e | −5 / 0 / 65 / 4001 | 0 | +2.35 % | +0.80 % | 30.05 | 0 |
| generic | −6 / 4 / – / 4500 | 0 | 0.0 % | +1.63 % | 25.76 | 3 events / 4 frames |
| C922 | −5 / 0 / 5 / 4000 | 0 | −0.82 % | **+1.44 %** | 30.00 | 0 |

Source: `evidence.worst_deviations` [M].
- **The C922's R/B** held at +1.44 % worst case (restart 3, sample 2) [M]. The smoke run's −3.0 / −3.4 % didn't recur, so ±3 % holds on tonight's data.
- **No camera needed a re-apply after a start** (`reapply.*.changed_at_stream_start` false everywhere) [M].
  - **This does not show the C930e is fixed.** Its locked values (−5, gain 0) equal its stream-start reset values, so a reset couldn't show [I].
  - W-GAIN shows the reset clearly: in 7/7 rows the C930e read exposure −5 at the first frame, whatever had been set before the stream [M] (`W-GAIN.json per_mode["1280x720_30"].grid.cells[gain=0].readback.before_set`).
  - The plan's "re-apply after the first frame" rule for the C930e stands.
- **The Kiyo Pro stall is still there: one per stream, 4/4** [M] (`segments[*].stream.max_arrival_stall_ms`, `.max_sample_step_ms`).
  - 303.5–304.6 ms, 8 frames each.
  - It always falls between frames 36 and 37, about 100 ms after the 1.2 s control re-apply, which set the same values again [M] (raw `frames.jsonl`).
  - Cause [NV]. A test with the re-apply skipped would tell whether it causes the stall.
- **The Kiyo Pro's start exposure (−6) is past its 30 fps ceiling** (§4.3). Locked at −6 it ran 28.6–28.7 fps [M]. The exposure step must set exposure itself, not keep the start value (D11 only covers the other controls) [I].

**Verdict:**
- The D10–D12 lock holds over 10 min and across restarts on all 4 cameras [M].
- **Still open:**
  - the C930e reset at stream start needs a W-NODRIFT case where the locked values differ from the reset values;
  - the Kiyo Pro stall [NV].

## 4. Decision D9 and §5.2a: gain limit from noise; exposure ceiling (W-GAIN, 23:25–23:58)

### 4.1 The grid

The grid is gain × exposure, 64 frames per cell. 49/49 cells were valid in every mode [M] (`R/W-GAIN.json verdicts["gain_grid|*"]`).

- **The noise ratio rho (σ/μ) falls as gain rises on the C930e and C922**, at every exposure: ρ_s −0.93 to −1.0 [M; ρ_s is a re-analysis of `per_mode.*.grid.cells[*].metrics.rho`].
  - The test's "rho rises monotonically" criterion therefore fails. Its dips have ratios of 0.66–0.97 (`rho_monotonic.per_exposure.*.dips`).
  - The assumption is wrong for these cameras [I]. W-GAIN doesn't record ρ_s itself [C].
- **The detail measure D falls monotonically with gain** (ρ_s −1.0 on the C930e and C922) [M, re-analysis].
- **Bytes per frame follow luma, not gain** (×1.1–3.6 across gain at a fixed exposure) [M].
- **At matched brightness (C922, 30 fps)** [M] (`per_mode["1280x720_30"].grid.cells`):

  | setting | luma | rho | D | bytes |
  |---|---|---|---|---|
  | −5, gain 0 | 123 | 0.0044 | 2.01 | 198 kB |
  | −7, gain 128 | 134 | 0.0036 | 0.97 | 199 kB |
  | −8, gain 255 | 125 | 0.0039 | 0.82 | 210 kB |

  So 8× shorter exposure plus maximum gain costs **59 % of D** for −12 % rho and +6 % bytes. On the C930e, −5/0 against −8/255 at luma 85 costs 31 % of D [M].
- **The Kiyo Pro is erratic** [M]:
  - luma jumps to about 140 at gain 128 on rows −11 to −9;
  - rho rises ×3.4 at −6, gain 128;
  - its 30 and 60 fps grids are nearly identical.
- **The generic camera's gain has no effect** (luma within ±1 %), as known [M].

### 4.2 The §5.2a rule, forced so gain is needed

| Camera / mode | forced exposure | g_lim per run | spread | D ratio at g_lim | rating |
|---|---|---|---|---|---|
| C930e 30 | −9 | 21, 23, 23, 21, 22, 23, 22, 21, 20, 20 | 20–23 | 0.851–0.857 | partial |
| C922 30 | −9 | 29, 30, 28, 30, 29, 30, 30, 29, 29, 29 | 28–30 | 0.850–0.854 | partial |
| C922 60 ⚠ | −9 | 57, 57, 57 | 0 | 0.89–0.90 | no |
| generic 30 | −7 | 1 × 10 (run 1 unverified) | 0 | 1.0 | partial |
| Kiyo Pro 30 / 60 | −11 | 0 (fallback) × 10 / × 3, all unverified | – | – | untested (inconclusive) |

Source: `per_mode.*.rule.forced_runs[*]`; `verdicts["gain_rule|*"]` [M].
- **D is the only limit that binds.** In all 20 C930e/C922 runs at 30 fps, the D ratio is 0.850–0.857 and the rho ratio is below 1 [M].
- **Why each rating comes out as it does** [C] (`tests/w_gain.py:1273-1292`):
  - **C930e and C922 at 30 are partial** only because of the wrong "rho rises" criterion. All 10 runs are inside the reference bracket.
  - **Generic is partial** because one run tripped the motion guard 3 times.
  - **C922 at 60 is no:** g_lim 57 sits 7 below the matched-luma bracket [64, 128]. Against the same-exposure bracket [26, 64] it would pass, and the grid is coarse (26 / 64 / 128). The rule capture also ran through wincam at 33.4 fps (⚠ the §7 caveat), so this cell measures little [M/I].
  - **The Kiyo Pro is inconclusive.** Its probes at gain 128 / 64 / 32 failed on D (ratio 0.30–0.43). Gain 16 then tripped the motion guard 3 times (motion fraction 0.10 against a 0.05 limit), so g_lim fell back to 0, unverified [M] (`W-GAIN/usbvideodevice_1532-0e05_4_1280x720_30_rule.json runs[*].probes`).
    - JPEG size was still falling more than 1 s after the gain set (132.8 → 106.8 kB over 32 frames) [M]. The image was still settling when the motion guard looked [I].
    - The Kiyo Pro's luma response to gain is not monotonic (24 → 29 → 37 → 140 at gain 26 / 64 / 128, exposure −11) [M].
- **As written** (not forced), the rule needed gain only twice: C930e 30 at −5 → gain 16, and C922 60 at −6 → gain 12 [M].

### 4.3 Exposure ceiling (T4): delivered fps per exposure step at gain minimum

Source: `per_mode.*.t4.steps[*].fps` [M]. Measured through wincam's MF path.

| exp | Kiyo Pro 30 | C930e 30 | C922 30 | C922 60 ⚠ |
|---|---|---|---|---|
| −11 … −7 | 30.01–30.02 | 30.05 | 30.00–30.02 | 29.7–33.1 |
| −6 | **28.72** | 30.06 | 29.99 | 29.72 |
| −5 | **23.17** | 30.06 | 30.00 | 32.66 |
| −4 | 19.43 | 16.01 | 16.08 | 16.32 |
| −3 | 14.71 | 8.00 | 8.04 | 8.17 |
| **ceiling** | **−7** | −5 | −5 | none measured |

- **The Kiyo Pro's ceiling at 30 fps is −7**, confirming the smoke result over all 10 steps [M]. Its 60 fps row equals its 30 fps row, because it runs at 30 in that mode (§1.2).
- **The generic camera:** 25.76 fps from −7 to 1, then 12.9 at 2 and 3. Ceiling 1, in its own units [M].
- ⚠ **There is no measured 60 fps ceiling for the C922.** wincam gave 29.7–33.1 where pymf gave 59.2 [M]. Some wincam grid cells switched to 59.3–59.45 partway through a capture [M]. Rerun the 60 fps T4 through pymf.

### 4.4 Recommended §5.2a thresholds [I]

These are for Dom to decide; the plan is not changed.
1. **Measure the ceiling. Don't compute it.** Step exposure down until delivered fps ≥ 0.99 × nominal. The exposure step sets exposure and does not keep the start value: the Kiyo Pro starts past its ceiling.
2. **Drop "rho rises with gain" from the rule and from the test's pass criterion.** Keep rho ≤ 1.5 × rho(g_min) only as a guard. It never bound on the C930e or C922 (0.46–0.88), but would on the Kiyo Pro (×3.4). Test D for monotonic decrease instead.
3. **D ≥ 0.85 × D(g_min) is the limit that binds, and it repeats** (spread 2–3 gain units over 10 runs). But it allows only about 20–30 of 255 (under 1 stop). **D ≥ 0.70** would allow about 64 (D ratio at −9/64: C922 0.715, C930e 0.72), about 1.4 stops. **Dom's choice:** how much fine detail to trade for exposure time. At maximum gain the C922 loses 59 % of D at matched brightness.
4. **Keep the "luma rise ≥ 3 %" stop.** It stopped the generic camera at gain minimum in 9/9 verified runs [M].
5. **Settling:** 200 ms is not enough for the Kiyo Pro. Wait until mask luma changes by less than 1 % over 3 frames (up to about 1.5 s) before the motion guard. Probe the Kiyo Pro linearly upward, not by binary search (its luma response isn't monotonic).
6. **Validate:**
   - in a brighter scene (tonight's forced runs were at luma 2–28);
   - with grid gains between 26 and 64;
   - with the 60 fps legs judged through pymf.

## 5. Decision 1.0: the package bump (W-TBUMP, 00:38–00:40)

**Untested.** Neither recording ran [M] (`R/W-TBUMP.json errors`, `verdicts["T-BUMP|recording"]`).

What went right [M] (`comparison.*.phases_s`):
- the worktree preflight passed for both (baseline `2992e64f9`; HEAD `7d06ba2e1`);
- the servers started (health in 2.56 s and 2.53 s);
- detection took 0.03 s.

Where it failed:
- **Both runs failed at `connect` (POST `/camera/group/apply`) after 40.5 s**, with the same error [M]:
  > `group/apply failed: HTTP 500 Camera config for b395 must be an instance of CameraConfig, got <class 'NoneType'> instead.`
- **The sequence, the same in both runs** [M] (raw `server_stdout.log` / `server_stderr.log` in skellycam-raw):
  1. b395 is the generic camera, DirectShow index 0.
  2. skellycam opened it through OpenCV in about 11.6 s, then failed to read a frame, 5/5 times. Each failure matches OpenCV's "VIDEOIO(DSHOW): backend is generally available but can't be used to capture by index".
  3. The worker gave up ("Failed to create cv2.VideoCapture for camera b395").
  4. The other 3 cameras' shared memory then failed to initialize, the group was torn down, and the missing config surfaced as the TypeError → HTTP 500.
- **Not a bump regression:** baseline (OpenCV 4.12, Py 3.12) and HEAD (OpenCV 5.0, Py 3.13) fail identically [M].
- **Probable cause** [I]: the same hub bandwidth limit that refuses the C922+generic pair on every API (§6), surfacing through OpenCV as a vague error.
  - The smoke W-TBUMP on 11-11 used 3 cameras without the C922, and passed.
  - The generic camera opened alone through OpenCV DSHOW in about 330 ms 10 min earlier [M].
  - Cause [NV].
- **skellycam bug, independent of the cause** [M]: one camera failing to open takes the whole group down with an unhandled `None` config. Phase 1 should fail that camera, keep the rest, and report why (ties to 1.11).
- **Shutdown and controls:** both servers shut down cleanly (0 leftover processes), and the as-found controls were restored on all 4 cameras [M].
- **The "global_kill_flag is set (no worker death detected)" line** from the smoke run is not new in phase 1 [C].
  - It's in both trees at `skellycam/core/ipc/process_management/worker_registry.py:103-106`, and the files are identical.
  - It came in with commit `de5ba001e` (2026-06-20), which predates the baseline.
  - The smoke difference is timing at shutdown, not a changed message [I]. It didn't appear tonight [M].

**To do:** rerun T-BUMP with a camera set that fits the bandwidth. Either 3 cameras without the C922+generic pair, or move one of the pair to another root port. Dom's call: moving a camera is a physical change.

## 6. Decisions 1.3 / 1.11: several cameras at once, MF vs DirectShow (W-MULTI, 00:40–00:52)

**No API streamed all four cameras at 720p30 at once.** The C922+generic pair on the HS13 hub (81.1 % of a microframe predicted) was refused in every attempt on every API [M] (`R/W-MULTI.json measurements.events`, `summary_by_api`).

| API | events / refusals | 720p30 pair | 960×720 pair (75.2 %) | C922 720p60 pair (98.4 %) | refusal code | rating |
|---|---|---|---|---|---|---|
| MF (wincam) | 21 / 19 | refused every time; C922 always the one refused | streamed 2/2 | refused 2/2 | `0x800718CF`, bandwidth_certain | yes |
| DS (ffmpeg CLI) | 21 / 19 | refused; C922 lost 4×, generic 6× | streamed 2/2 | refused 2/2 | `OSError(5)`, bandwidth_probable | partial |
| PyAV DS | 21 / 19 | refused; C922 lost 6×, generic 4× | streamed 2/2 | refused 2/2 | `OSError(5)`, bandwidth_probable | partial |

- **DS and PyAV are partial** only on "classification unambiguous": `OSError(5)` can't be told apart from other failures [C] (`tests/w_multi.py:902`, `common/rating.py:590`).
- **MF names the cause exactly.** A product can tell the user to move a camera [I].
- **Changed from 11-10:** that night the 81.1 % pair eventually streamed on DS and PyAV. Tonight it never did (0/21 each) [M].
- The C930e and the Kiyo Pro (other bandwidth domains) streamed in every round they were in, except the Kiyo Pro at round 029 [M].
- The mapper's predictions matched (W-TOPO `mapper` yes) [M].

## 7. The Kiyo Pro

Facts only. No diagnosis (Dom's rule).

**Timeline (UTC)** [M] (`R/KIYO_PRO_DEAD_20261112T054624Z.json`, `R/W-KIYO.json`, `suite_log.txt`):

| UTC | event |
|---|---|
| 05:45:45 | last OK control polls (MF, DS) |
| 05:45:47.3 | W-MULTI `ds_all_together_029` starts all four cameras at once through the DS ffmpeg CLI. The Kiyo Pro's open times out after 30.3 s (class device_not_ready); the C930e and generic stream, and the C922 is refused (bandwidth) |
| 05:46:18.0 | W-KIYO MF poll fails (activate timeout) |
| 05:46:24.27 | the 1-frame health check fails (rc 5); **fault (watchdog/hang) and dead mark** |
| 05:46:24.47 | an already-queued W-KIYO DS poll reaches the camera and fails (bind_filter timeout) |
| 05:46:27 | the W-KIYO poller stops ("every polled Kiyo Pro is dead") |

**State at the dead mark** [M]:
- plug-in age 379.0 min (last arrival 23:27:22Z);
- `other_camera_commands_running` empty;
- no LogiTune, Logi Options+ or Razer process running (11-10: razer_elevation_service was);
- the camera still present, problem code 0;
- `stream_starts_this_run` 90. This counts streaming *commands*, not stream starts, so a 400-cycle command counts once [C] (`suitectx.py:213-214`). The Kiyo Pro's real stream starts were higher [I].

**After the dead mark** [M]:
- 0 commands to the Kiyo Pro from 00:46:27 local to the end of the run;
- W-MULTI rounds 030–063 left it out (0 of 34 later spec files name it);
- W-PYAV-LIST was skipped, and W-CYC-KIYO rated all 10 variants untested;
- the W-MULTI re-probe at 05:48:43Z was recorded as "dead (Kiyo Pro dead rule): not probed".

**W-KIYO** (360 polls per API) [M]:
- 359/360 answered on each API, so the verdict is no.
- The poller records only exposure and the count of controls answered (16/16 every time), so it can't show drift [NV].

**Compared with 11-10** [M]:

| | 11-10 | tonight |
|---|---|---|
| stage | W-MULTI `ds_all_together_028` | W-MULTI `ds_all_together_029` |
| first failure | DS open timeout, device_not_ready | the same |
| poller failure before the fault | yes | yes |
| plug-in age | 525.8 min | 379.0 min |
| vendor processes | razer_elevation_service | none |
| fault repeats | 4 (no dead rule then) | 0 |

**Pattern** [I]: both nights the Kiyo Pro died at the same step, four cameras opened together through the DS ffmpeg CLI, near the end of that loop. With Razer software absent tonight, that software is not needed for it to happen [I]. No further reading of this is offered.

## 8. The other tests: re-runs, same as 11-10 unless noted

Source: `R/<TEST>.json` [M].
- **W-FMT:** MJPEG mode counts are equal across descriptors, MF and DS (Kiyo Pro 28, C930e 119, generic 10, C922 120). Same as 11-10.
- **W-FMT-NOGRAB:** MF, DS and the hub IOCTL list everything without opening a camera.
  - The ffmpeg CLI is "incomplete" on 3 cameras because it prints only the minimum and maximum frame rate per caps entry. Every size is listed.
  - OpenCV and WinRT can't list without opening a capture [C].
  - Same as 11-10.
- **W-MJPEG:** real MJPEG bytes on MF and DS on all 4 cameras.
  - The Kiyo Pro through PyAV DS got YUY2, not MJPEG (PyAV can't set dshow's `video_codec_id`). The ffmpeg CLI got MJPEG.
  - **Changed:** the C922 720p60 MF capture got 59.5 fps (11-10: 40.2, slow start).
- **W-RAW:** Kiyo Pro raw NV12/YUY2 works on MF, PyAV and ffmpeg (60 fps requests run at about 30).
  - OpenCV DSHOW returns converted BGR in every mode (no).
  - OpenCV MSMF can't set NV12 (partial).
  - Same as 11-10, now on OpenCV 5.0.0.93.
- **W-TS:** MF sample times sit on a 16.0 ms host grid (on-grid 0.9989–1.000) with 0 drops; PyAV DS pts are synthesized. So both routes are "no" without ground truth (the strobe rig isn't built). Same as 11-10.
- **W-CTRL-EFFECT:** set and readback agree for every control.
  - **Changed:** the Kiyo Pro went from yes to partial on exposure only. The part of the sweep set after stream start (−7 to −4) moved luma ×1.09 against the 1.125 it needs. At −4 (longer than the frame period) the image didn't brighten [I: clamped by the frame period at AE priority 0].
  - The C930e is partial (exposure and gain reset at stream start; both work when re-applied).
  - The generic camera is partial (gain has no effect; WB moved the image in 1/6 runs).
  - The C922 is yes.
  - Both runs' JSON has `persisted_after_reopen` false for the C930e exposure and gain and the generic gain. The 11-10 write-up §6 said every control persisted, so that line is wrong.
- **W-OCV-CTRL:** OpenCV MSMF `get()` doesn't return the camera's value on any camera; OpenCV DSHOW sets made before the first frame don't hold.
  - **Changed:** the C922's DSHOW autofocus check went from no to yes.
  - **New:** one refused `set(EXPOSURE, −7)` on the Kiyo Pro DSHOW.
- **W-ID:** partial on persistence.
  - Same-port replug: the C922's key differs after its natural replug. The other 3 cameras' keys held [M]. The difference sits inside the redacted serial, so why is [NV].
  - Port move: the 10-27 comparison shows the serial key changed [M].
  - No reboot data.
- **W-POLICY:** partial (one item can't be checked; yes after W-FMT).
- **W-TOPO, W-CTRL-LIST:** yes.

## 9. Harness notes from this run (suite fixes to consider)

1. **Dead-rule gap: the gate is checked before camlock, not after** [M+C] (`suitectx.py:202-219`). A W-KIYO DS poll queued before the dead mark reached the Kiyo Pro 0.2 s after it. Fix: check `camera_dead()` again once the lock is taken.
2. **Multi-camera commands aren't mapped to a camera** [C] (`suitectx.camera_for_argv` returns None when several device paths appear). `multi_launch`, `pymf multi` and the skellycam recordings are therefore neither gated nor counted per camera. Tonight each test's own camera list kept the dead Kiyo Pro out [M], but the gate itself couldn't.
3. **`stream_starts` counts commands, not stream starts** (§7). The Kiyo Pro's "starts per wedge" figure needs per-cycle counting.
4. **W-PYMF's "all: partial" cap is out of date** (§1.1). W-PYMF-ALL now covers streaming sets, in-use detection and several cameras in one process.
5. **W-PYMF-ALL's low-rate exemption** should allow arrival gaps that are within the gap limit (§1.2).
6. **W-GAIN's "rho rises monotonically" criterion is wrong for these cameras** (§4). Test D instead. Add grid gains between 26 and 64, and lengthen settling for the Kiyo Pro.
7. **W-GAIN's 60 fps legs and T4 should use pymf**, not wincam.
8. **W-NODRIFT can't see the C930e reset** when the locked values equal the reset values (§3).
9. **W-ENV's process patterns miss `msedgewebview2`** (`w_env.py:54`).
10. **Fault records use a stale plug-in age** after an unexplained re-arrival (§2).
11. **Time:** the run took 54 % of its estimate (5 h 10 min vs 9 h 31 min). Most of the difference is the Kiyo Pro's skipped work [I].

## 10. What changes, and what's still open

**Plan decisions:** none changes. The evidence supports 1.3 as written (pymf; OpenCV out of the Windows path; DS-ffmpeg not needed) and D10–D12 [M+I].

**For Dom to decide:**
1. The §5.2a thresholds (§4.4), above all D ≥ 0.85 vs D ≥ 0.70.
2. Whether to move the C922 or the generic camera off the HS13 hub, so that all four cameras can stream at 720p30 and T-BUMP can run with all four.

**Still to run:**
- T-BUMP with a bandwidth-feasible set;
- the 60 fps T4 and gain rule through pymf;
- Kiyo Pro cycling (it needs a replug and a quiet night);
- W-NODRIFT with locked values that differ from the C930e's reset values;
- the gain rule in a brighter scene;
- whether skipping the re-apply removes the Kiyo Pro's 300 ms stall [NV].

**Not runnable unattended:** focus F1–F11, T3, T5, TP2–TP4 (unchanged from the handoff).
