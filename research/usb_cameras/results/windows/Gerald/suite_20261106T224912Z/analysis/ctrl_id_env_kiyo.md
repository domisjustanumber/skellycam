# Analysis: controls, identity, environment and the Kiyo onset (run 2)

Tests: W-CTRL-LIST, W-CTRL-EFFECT, W-ID, W-ENV, W-POLICY and the W-KIYO background poller.

Run: Gerald, Windows 11 build 26300.9711, suite `suite_20261106T224912Z`, 2026-11-06 17:49-19:13 local (22:49Z-00:13Z; local = UTC-5). This analysis used the result JSONs, `suite_log.txt`, `run_suite.json`, `discovery.json`, the raw folder `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_20261106T224912Z` and the suite code. I opened no camera and changed no suite or result file.

Labels used below:
- **measured**: read from a result file. The file and field are given.
- **inferred**: my reasoning from measured facts.
- **code**: confirmed by reading the suite source.

Unless stated otherwise, times are UTC.

Cameras:

| Camera | Key | Plug-in time (`last_arrival`) | Tier-1 metadata |
| --- | --- | --- | --- |
| C922 | `046d:085c:sn=C922SN01` | 15:04:37Z | ON |
| Kiyo Pro | `1532:0e05:port=…/4.4` | 20:32:29.065Z (Dom's replug) | ON |
| Generic | `4c4a:4a55:port=…/13.1.2` | 22:26:45Z (also re-arrived at 00:10:45Z, during the run) | OFF |
| C930e | `046d:0843:port=…/7` | 15:00:22Z | OFF |

---

## 1. Every rating cell in this group

### 1.1 G-CTRL (W-CTRL-EFFECT.json `verdicts["G-CTRL|<key>|<api>"]`)

**Code.** `rating.rate_ctrl` (common/rating.py:322-373) returns yes only if all six criteria are True:

1. The control is listed with the descriptor's range. This now comes from W-CTRL-LIST `per_control` (B6 fixed: `listing_source` "W-CTRL-LIST per_control").
2. Set and readback agree.
3. The effect shows in the image, judged on the segments set while streaming (`control_rating_row` effect_ok = all `effect_after_ok`, w_ctrl_effect.py:662).
4. It works before and after stream start. Before start now includes "held through start" (B3).
5. 3/3 runs pass. A run counts through `run_counts_ok`, which uses the all-segment `effect_ok` (w_ctrl_effect.py:635-638).
6. No workaround is needed.

If any criterion fails, the cell is partial.

| Camera | Path | Cell | Deciding criteria and fields (measured) | Real or artefact |
| --- | --- | --- | --- | --- |
| C922 | mf | **yes** | All 6 True. Exposure, gain, WB and focus each 3/3. `held_through_start` True. Persistence by capture `persisted` True for all 4. `restore` True | real |
| C922 | ds | **yes** | Same as mf | real |
| Kiyo | mf | partial | (3) False and (4) False, both from **gain** only: `ratio_after_start` 1.009/1.012/1.012 against 1.075 required (`effect_after_ok` False). (5) True because the all-segment ratio 1.21 ≥ 1.15 makes each run count. Exposure, WB and focus pass 3/3, held through start, persisted | **mixed**: a real compressive response (gain 128→230 adds 1% luma), made worse by the harness: the gain test fixes exposure at mid-range (−7), so the base luma is already 123 (H7). Also, (5) contradicts (3) (H6) |
| Kiyo | ds | partial | Same gain failure: `ratio_after_start` 1.004-1.006. Also **focus** run r1: segments 4-5 have `n` 0, so `effect_ok` is None and `runs_ok` is 2/3. That makes (5) False, and (4) False for focus (`after_start_ok` False) | **mixed**: gain as on mf. The focus r1 failure is a **harness artefact**: the DS sets for 450 and 600 took 1.03 s and 1.48 s (`sets[3..4].t_end_ns - t_start_ns`; about 50 ms in r0), and the fixed schedule left no frames in those segments (H5) |
| Generic | mf | partial | (3) False: gain `ratio_after_start` 0.999-1.0 and WB 0.987-1.0. (4) False: gain `held_through_start` False (2 → 4 at the first frame) and `after_start_ok` False. (5) False: gain 0/3, WB 0/3. Exposure 3/3 | real |
| Generic | ds | partial | Same as mf: gain 1.0-1.001, WB 0.998-0.999. Gain `value_before_first_set` 4 in 3/3 runs | real |
| C930e | mf | partial | (4), (5) and (6) False. Exposure: `value_at_first_frame` −5 (flags 2 = manual) after −9 was set, 3/3. Gain: 50/51/50 after 26 was set, 3/3. `runs_ok` 0/3 for both. `workaround` = "reset at stream start … re-apply". WB and focus 3/3 and held | real |
| C930e | ds | partial | Same as mf: exposure `value_before_first_set` −5 (3/3), gain 49/50/49 (3/3) | real |

### 1.2 Other cells in this group

| Table / cell | Source | Why | Real or artefact |
| --- | --- | --- | --- |
| ctrl_list_equivalence, all, **yes** | W-CTRL-LIST.json `verdicts.ctrl_list_equivalence` | 4/4 cameras `met` True. Counts MF = DS: 16/16/11/16. `missing_mf`/`missing_ds` 0, `mf_vs_ds_diffs` 0, `iam_ks_disagree` [] | real |
| (run 1's "G-CTRL / all / untested" row) | gone | B7 fixed: W-CTRL-LIST no longer emits a G-CTRL key | n/a |
| G-ID, all, **partial (provisional)** | W-ID.json `verdicts.G-ID` | Criterion 1: `6/6 APIs`, True. Criterion 2: 20 runs each, True. Criterion 3: `reboot` null, `same_port_replug` null, `port_move_serial` true, so `met` null. `provisional` true | **missing data**. No API failed. Attended item A1 has not been run. Natural same-port evidence exists but is unused (H8) |
| G-ID_per_api, 6 × partial (JSON only) | `verdicts.G-ID_per_api.*` | Each per-API cell is a full `rate_id` dict now (B9 fixed). Same null persistence | missing data |
| key_source_stability, **yes** | `verdicts.key_source_stability` | `pnp_discovery` stable and 1:1 over 20 runs | real |
| policy_traps, **yes** | W-POLICY.json `verdicts.policy_traps` | All 6 criteria `met` True. The rotation and multi-app criteria are `met` True through W-FMT corroboration (MF lists 120/28/10/119 native MJPG types). The run-time cell `policy_traps_at_run_time` was partial (rotation and multi-app `met` null), then re-rated after W-FMT (`suite_log.txt` line 42) | real (B10/V2 fixed). Rotation and multi-app remain **inferred** from corroboration |
| kiyo, Kiyo, **no** | W-KIYO.json `verdicts["kiyo|…|all"]` | Criterion 1 "answers every control poll" False: `ok` 190/294 per API. Criterion 2 "onset observed inside the window" True (`failed_from_first_poll` mf/ds false) | **real**. The Kiyo stopped answering at plug-in age 210.5 min. The onset timestamps are skewed by the harness (H1) |
| W-ENV | no verdict by design | context only | n/a |

---

## 2. The Kiyo onset (W-KIYO poller, W-MULTI raw, run_suite.json)

### 2.1 Exact timeline (measured)

| UTC | Plug-in age | Event | Source |
| --- | --- | --- | --- |
| 22:49:12.96 | 136.7 min | Poller starts. First poll OK on MF and DS (16 controls, exposure −4) | W-KIYO `polls[0]` |
| 23:40-23:45 | 188-192 min | W-CTRL-EFFECT sets exposure, gain, WB and focus on the Kiyo through MF and DS. Everything answers | W-CTRL-EFFECT.json |
| 00:02:47.80 → 00:02:59.95 | 210.3 → 210.51 min | **Last good Kiyo stream**: W-MULTI `ds_staggered_036` (stagger 3/5), ffmpeg-cli dshow MJPG 1280x720@30, 300/300 frames, first frame 1.23 s | raw `W-MULTI/ds_staggered_036/usbvideodevice…/summary.json` |
| ≈00:03:00.0-00:03:00.54 | 210.52 min | **Last good control polls**: MF poll 189 (scheduled 00:02:41.98, waited 18 s for the lock), then DS poll 189 at 00:03:00.261, rc 0, 16 answered | W-KIYO `polls[i=189]`; `suite_log.txt` 19:03:00 |
| 00:03:01.45 | | `ds_staggered_037` (stagger 4/5) starts the C922 | raw summary |
| **00:03:03.94** | **210.58 min** | **Kiyo DS open (ffmpeg dshow, same mode and command as 4 s earlier) never delivers a frame.** `error` {stage open, class timeout, "ffmpeg timed out"}, `open_duration_ms` 35272, `timed_out` true, exit 5, ended 00:03:39.21 | raw `ds_staggered_037/usbvideodevice…/summary.json`; W-MULTI `runs[36]` |
| 00:03:06.43 / 00:03:08.94 | | Generic fails as in every staggered run ("device already in use"). C930e streams OK. C922 streams OK | raw summaries |
| 00:03:39.45 → 00:03:42.48 | 211.2 min | First failed control query. MF `wincam controls` IAM query does not return within 3 s (`error` class timeout, stage control_query, `abandoned_threads` 1). The poll was *stamped* 00:03:01.219, before its 38 s lock wait | raw `W-KIYO/…/poll_00190_mf_change.json` `utc_started`; W-KIYO `first_failure.mf.lock_wait_s` 38.0 |
| 00:03:42.70 → 00:03:45.73 | | DS control query also times out (3 s) | `poll_00190_ds_change.json` |
| 00:04:01.9 onward | 211.6 min | Fast failure, about 0.25 s per call. KS GET returns **0x8007001F** on all 15 device-backed controls. `focal_length` answers (driver-side). IAM GetRange returns 0x80070490. KS BASICSUPPORT/DEFAULTVALUES return S_OK (driver cache). camcmd_scan marks the fault at 00:04:02.35 | `poll_00220_mf_fail.json`; run_suite.json `faults` |
| to 00:13:20 | 220.9 min | 104 failing polls per API, all 0x8007001F. No re-arrival. `problem_code` 0. The W-MJPEG health probe also returns 0x8007001F | W-KIYO `failure_codes`, `arrivals_seen` (1 entry); run_suite `status[W-MJPEG].probes` |

**What was running at the onset (measured).** W-MULTI, DS family (pyav_ds `--engine ffmpeg`), staggered launch 4/5. All four cameras started 2.5 s apart, MJPG 1280x720@30. The Kiyo was the second camera, launched at +2.5 s.

**Software at the onset (measured).**
- `tasklist`: 9 × LogiTune.exe, LogiTuneAgent, LogiTuneUpdater, 9 × RazerAppEngine, razer_elevation_service, 3 × Logi Options+. There was one `vendor_process_changes` entry for the whole run (at i=0), so no vendor process started or stopped near the onset.
- `wincam activity` (IMFSensorActivityMonitor): **LogiTuneAgent.exe:3296 and RazerAppEngine.exe:37240 held the Kiyo, not streaming.** They held it for the whole 84 min, with no `activity_changes` entry between 00:01:22 and 00:12:04.
- At 00:12:04, after the onset, LogiTune.exe:26388 and Signal.exe:22688 also attached.

**Two-phase signature (measured).** The failure went in two phases:
1. Calls hang: the stream open hung for 35 s, then control queries hung for over 3 s, on both MF and DS.
2. About 20 s later, calls fail fast with 0x8007001F.

Run 1 showed the same shape: one frame, then a stall, then `reader_release` hung for 5 s, then fast failures. B2 is fixed, so the real KS GET code (0x8007001F) is now recorded instead of 0x80004002.

### 2.2 Comparison with run 1, and time since plug-in versus trigger

| | Run 1 (`suite_20261106T181941Z`) | Run 2 |
| --- | --- | --- |
| Plug-in | 14:59:24.58Z | 20:32:29.07Z (replugged by Dom after run 1's failure) |
| Last good Kiyo command | 18:19:58Z, control read, **200.6 min** | 00:03:00.5Z, control poll, **210.52 min** (stream 210.51 min) |
| Failing command | 18:43:39.70Z, **224.3 min**. MF 640x360@5, the first stream of the run: 1 frame, then a stall and a `reader_release` hang (run 1 `analysis/cyc_kiyo.md` §4.1) | 00:03:03.94Z, **210.58 min**. DS/ffmpeg 1280x720@30, staggered with 3 other cameras: no frame, 35 s hang |
| Kiyo stream starts in the suite before the failure | **0** (the run 1 quick self-test streamed it at 171-200 min) | **About 270** (inferred count: W-CYC 210 cycle opens per `variants.*.summary.n`, W-CTRL-EFFECT about 32 captures, W-MULTI 28, plus W-TS and FMT-NOGRAB). About 190 control polls per API |
| Idle before the failing open | 23.7 min | 3.8 s |
| API, mode, concurrency | MF, 5 fps, single camera | DS (ffmpeg), 30 fps, 4 cameras |
| Vendor software | LogiTune and Razer running. Razer was attached (from a cycle row) | Same. LogiTuneAgent and RazerAppEngine attached for the whole window |

**Reading (inferred).**

**For a time-since-plug-in mechanism, moderately strong:**
- The two onsets agree on plug-in age, 210.6 min against a 200.6-224.3 min window. They agree even though the workloads before them differed completely: 0 suite streams against about 270 starts and about 380 polls. The API, mode, fps, concurrency and idle time also all differed.
- In run 2, the *identical* command (same API, mode and stagger slot) succeeded 4 s earlier. So no particular command and no plausible cumulative-use count explains the onset.
- Host uptime does not explain it either. Gerald booted at 14:26Z, so uptime at the onsets was about 4.3 h and about 9.6 h.
- Together with run 2's clean streams at 200.6-210.5 min, which overlap run 1's window, the onset sits at roughly **210-224 min (about 3.5-3.75 h) after plug-in**.

**For a stream start as the proximate event:**
- In both runs the failure first showed at a stream start (run 2) or within the first 2 s of a stream (run 1).
- In run 2 the control plane answered 3.4 s before the failing open.

So the data fit a two-factor model better than either factor alone: an age-dependent device state at about 3.5 h, exposed by the next stream start, which may also be what trips it. The suite cannot tell whether the Kiyo would also have wedged with no stream, because in run 2 it streamed every 10-20 s.

Other observations:
- **LPM.** USB 3 LPM is "Moderate power savings" and selective suspend is enabled (W-ENV `power`). An LPM mechanism is not excluded, because both runs had an idle gap before the failing start. But only a 4 s gap was needed in run 2, and about 270 earlier starts after similar gaps succeeded.
- **Vendor software.** It was attached throughout and did not change at the onset. It cannot be excluded as a periodic requester; the suite cannot see EP0 traffic.
- **The 10-25 claim.** "A few minutes after each plug-in" (REPORT.md:138, PROGRESS.md:31) is contradicted again: the Kiyo answered at 136.7-210.5 min.

**Experiment that separates the two (attended, after a replug).** Run the background poller only (1 poll per 10 s, no streams) beyond 4 h:
- If the polls fail at about 3.5 h with no stream, the failure is time-based.
- If the polls keep answering, start one stream every 10 min after 3 h, to see whether a stream start is required.

Then repeat with LPM Off (A4) and with Razer Synapse quit.

---

## 3. Quantitative answers to the plan's questions

### 3.1 Same controls through MF and DS? Yes, unchanged from run 1 (measured, W-CTRL-LIST.json)

- Counts MF = DS: C922 16, Kiyo 16, generic 11, C930e 16.
- 0 missing descriptor controls. 0 MF-vs-DS differences. `iam_ks_disagree` [].
- Degenerate ranges: `cc.auto_exposure_priority` is 0..0 on the C922, Kiyo and C930e, and `pa.powerline_frequency` is 0..0 on the generic.
- Extra control: `cc.focal_length` appears on every camera.
- The listing JSONs are **identical to run 1** except for auto-driven values (C922 focus/gain/WB; C930e exposure/focus/gain).
- **The Kiyo's non-default values survived Dom's replug.** Brightness 205, contrast 201, saturation 110 and backlight 1 are the same at 13:19 (run 1) and 17:52 (run 2). The generic's contrast 250, saturation 475, sharpness 180 and gamma 22 also survived its re-arrivals. Inferred cause: values stored in the camera's non-volatile memory, or re-applied by vendor software on arrival (RazerAppEngine holds the Kiyo).
- Listing time: 47-63 ms per API per camera (`mf_run`/`ds_run.elapsed_s`, including process start).

### 3.2 Which controls have a visible effect? (W-CTRL-EFFECT, MJPG 1280x720@30, 3 runs per control and path, measured)

| Camera | Exposure luma (values), last/first ratio | Gain luma (values) | WB R/B | Focus sharpness max/min | Held through start | Persisted (new stream, first frame + metric) |
| --- | --- | --- | --- | --- | --- | --- |
| C922 mf/ds | −9/−7/−4: 5.0 → 18 → 90, 17.7-18.2 | 26/128/230: 30.7 → 66 → 87, 2.82-2.87 | 2800/4650/6500: 1.29 → 2.46 → 3.54, 2.74-2.78 | 0/60/125/190/250: 57.8-58.8 | all 4 controls, 6/6 | all True (ratio 0.99-1.003) |
| Kiyo mf/ds | −9/−7/−4: 34 → 101 → 126, 3.62-3.70 (after-start 1.23-1.25, barely above 1.125) | 123 → 148 → 150. 26→128 +20%, 128→230 +1% | 1.10 → 1.75 → 2.43, 2.20-2.22 | 0/150/300/450/600: peak at 450, 7.9-11.3 | all, 6/6 | all True |
| Generic mf/ds | −5/−2/1: 20 → 68 → 189, 9.24-9.34 | 2/4/6: 68.5 → 67.6 → 67.6 (none) | 2800/4650/6500: 0.97-1.0 (none) | not supported | gain **reverts to the default 4** (6/6); exposure and WB held | gain False (reopen readback 6, first frame 4); others True |
| C930e mf/ds | 109 (reverted to −5) → 40 → 152; after-start 3.66-3.85 | 43 → 73 → 100 (segment 1 actually at about 50); after-start 1.36-1.37 | 1.15 → 1.44 → 1.60, 1.37-1.39; after-start 1.105-1.114 | 0..255: 6.8-7.2 | exposure → **−5 manual** at 14/14 starts (incl. the fixed exposure of the gain runs); gain → **49-51** at 6/6; WB and focus held | exposure False (first frame −5, luma 0.73×); gain False (first frame 50/51, luma 1.15×); WB and focus True |

Sources: `measurements.cameras.<key>.paths.<api>.controls.<name>.runs[*].{metric_values, ratio_last_first, ratio_after_start, ratio_max_min, value_at_first_frame, value_before_first_set, fixed_controls}` and `.persistence`.

**Before vs after start, per camera:**
- **C922:** everything holds.
- **Kiyo:** everything holds.
- **Generic:** gain resets to 4 at every stream start. Gain and WB have no visible effect at all.
- **C930e:** manual exposure resets to its default −5 (still flagged manual) at every stream start. Gain jumps to about 50, which is neither the default 0 nor the previous value; that looks like a one-shot AE result (inferred). Values set ≥1 s after the first frame work. WB and focus hold.

The C930e reset is **deterministic in run 2** (14/14). In run 1, DS run 3 held, and the WB runs had gain carry-over. Whether it comes from the firmware or from LogiTune is still open: LogiTune was running, and the C930e uses Logitech driver 1.2.75.34 (W-ENV `cameras_health`).

**MF vs DS equivalence (measured).**
- Same reverts and holds on both paths.
- Metric values agree within about 2%. For example, Kiyo exposure is 34.3/100.7/125.8 on MF (JPEG) against 34.5/101.4/125.5 on DS. The DS path delivered **raw YUY2** (PyAV silent format fallback, `error.stage` format), so this also validates the raw-plane metric path.
- Control behaviour is API-independent (same KS property sets; inferred).

**Persistence (B5 fixed).** The new capture-based check now catches what run 1's readback missed. The C930e exposure reads back −4 manual after reopening, but the next stream starts at −5, and luma drops to 0.73×.

### 3.3 End-state restore (measured, `paths.*.restore` and `controls.*.restore`)

- `restored` True on all 8 paths and after every control. No `first_attempt` retry was needed. `errors` [].
- Path-end state, flags compared with W-CTRL-LIST at 17:52:
  - C922 and Kiyo: exposure, WB and focus auto; gain 0 manual (the C922's gain is AE-driven: 38 at 17:52, 0 at 18:36).
  - Generic: exposure auto, gain 4, WB 4500 manual.
  - C930e: exposure, WB and focus auto; gain 43 manual (43 at 17:52 too).
- Every flag matches the suite-start state.
- V1 is fixed: per-control restores remove the carry-over. C930e WB now passes cleanly (after-start 1.105-1.114, against run 1's 1.053, which came from gain 230 left behind).
- B4 is fixed: the gain test's fixed exposure is re-applied at 0 ms, so the C930e gain test's first segment ran at luma 43 instead of run 1's 111.

### 3.4 G-ID (measured, W-ID.json)

- MF, DS, PyAV-dshow, FFmpeg CLI, OpenCV MSMF and OpenCV DSHOW each map 20/20 runs 1:1 to the 4 keys, in a stable order. The indices equal run 1's: MF C922 4 / Kiyo 5 / generic 6 / C930e 7; DS 0 / 1 / 6 / 7. The NDI/OBS/NVIDIA/SpoutCam virtual cameras occupy MF 0-3 and DS 2-5 and 8-14.
- Enumeration time p50 (`timing_ms`), with run 1 in brackets:

| API | p50 now (run 1) |
| --- | --- |
| MF | 2.19 ms (2.10) |
| DS | 4.81 ms (4.57) |
| OpenCV MSMF | 2.21 ms (1.98) |
| OpenCV DSHOW | 2.96 ms (2.77) |
| PyAV | 157 ms (154) |
| FFmpeg CLI | 219 ms (213) |
| Suite discovery | 133 ms (120) |

- **Unattended same-port replug evidence (measured, not used by the rating).** The Kiyo (physically replugged by Dom at 20:32:29Z) and the generic (re-arrived at 22:26:45Z) kept the same key, composite instance ID, function instance ID and MF symlink between run 1's and run 2's `discovery.json` (`run_suite.json arrivals_since_previous_run.re_arrived_since` true). The C922 serial key survived a reboot (`serial_keys_kept_over_reboot` [true]) and a port move (`port_move_serial` true).

### 3.5 W-ENV / W-POLICY (measured)

- **Power:** Balanced scheme. Selective suspend enabled on AC and DC. USB 3 LPM "Moderate" on AC and DC. Hub timeout 50 ms. No global `DisableSelectiveSuspend`.
- **Health:** all 4 cameras at problem code 0, devnode status 0x0180600a. The Kiyo is behind the PCIe switch on the Thunderbolt xHCI 8086:1138.
- **Frame Server:** running (new PID 46428; 48280 in run 1, so it restarted between runs). 8 sensor groups. DS bypasses Frame Server on all 4 cameras. EnableFrameServerMode not set. The DshowBridge list holds only Logitech `Launcher_Main.exe`. No Studio Effects or NPU device. Privacy Allow/Allow. The Kiyo's DMFT/plugin values are empty strings.
- **Flags, now including run 1's missing ones (B11 and V3 fixed):**
  - LPM moderate.
  - Selective suspend.
  - Logitech software.
  - Razer software.
  - Virtual cameras (MF 4 at 0-3, DS 11 at 2-5 and 8-14).
  - **C930e silently on tier 0**: `MetadataBufferSizeInKB0`=5 sits on the old instance `8&39DEC205&1&0000`, not on the current `6&2206973f&0&0000`.
- **Processes:** LogiTune ×9 plus agent and updater, Logi Options+ ×3, RazerAppEngine ×9 plus the elevation service, Discord ×6, Firefox. Conferencing apps and browsers are matched but not flagged.

---

## 4. What changed from run 1, and why

| Item | Run 1 | Run 2 | Cause |
| --- | --- | --- | --- |
| Kiyo G-CTRL | untested ("no manual mode"; re-rated "no" offline) | partial, measured: exposure, WB and focus work | **camera state**: W-CTRL-EFFECT reached the Kiyo at 188-192 min, before its onset (run 1: 291 min, already failed) |
| C930e WB | marginal 1.053 | 1.105-1.114 | **fix V1** (carry-over removed) |
| C930e gain test exposure | ran at −5 (luma 111) | re-applied to −7 (luma 43) | **fix B4** |
| C930e and generic held-through-start | passed wrongly (gain reverts unseen) | caught: `held_through_start` False | **fix B3** |
| C930e persistence | `persisted_after_reopen` True (misleading) | False (capture-based) | **fix B5** |
| C930e exposure reset | MF 3/3, DS 2/3 | 14/14 | camera (more deterministic), or the cleaner state from V1 (inferred) |
| W-CTRL-LIST G-CTRL row | "untested" | removed | **fix B7** |
| W-KIYO codes | 0x80004002 ("not called") | 0x8007001F (real KS GET) | **fix B2** |
| W-KIYO onset | invisible (ran last, failed from poll 0) | caught live, with test, age and holders | **fix B7 (background) + N3 (activity)** |
| W-POLICY multi-app found → None | bug | `met` False when on; None when unknown; corroborated by W-FMT | **fix B10/V2** |
| W-ENV virtual cameras / stale tier-1 flags | missing | present | **fix B11/V3** |
| Scene luma (e.g. C922 gain 38→102 against 31→87; focus ratio 30 against 58) | daytime | evening | **lighting** (inferred) |

---

## 5. Remaining harness bugs

| # | File:line | Bug (measured effect) | Fix | Severity |
| --- | --- | --- | --- | --- |
| H1 | windows/tests/w_kiyo.py:178-185 (and :301-303 for age, test and activity) | A poll's `utc`, plug-in age and activity sample are taken **before** `ck.get_controls` waits for the camera lock. The onset was stamped 00:03:01.219, but the query ran at 00:03:39.45 (lock wait 38 s). Waits reach 455.9 s, so `first_failure_utc`, the summary.md onset line and the "activity at onset" can all be off by minutes | Stamp the poll from the wincam JSON `utc_started` (fall back to `t_utc + lock_wait_s`), compute the plug-in age at that time, keep `scheduled_utc` separately, and take the activity sample after the lock is acquired | high (onset timing is the test's purpose) |
| H2 | windows/tests/w_kiyo.py:242-257 | The poller catches up on missed slots: `wait = t_start + i*interval - now` goes negative after a long lock wait, so rounds run back to back. Measured: 63 MF gaps of about 2 s and 49 of about 1 s (MF+DS at about 1 Hz) between blind gaps of up to 463 s. `sched_t_s` lags `t_s` by about 2,500 s. "Every 10 s" is false, and the Kiyo gets bursts of control traffic | `next_due = max(next_due + interval, time.monotonic())`. Record `skipped_slots`. Optionally cap the rate | medium |
| H3 | windows/suitectx.py:493-499 (`_scan_camcmd`) | A failure is recorded only when the JSON has `"ok": false`, but `wincam controls` emits no `ok` key (raw `poll_00190_mf_change.json`). The Kiyo's control-query timeouts at 00:03:39 and 00:03:42 (rc 5) never became its first failure. run_suite.json `first_failure` and summary.md say 00:04:02 control_get instead | Count as failed when `obj.error` is a dict (class timeout/device_error, or any stage) or rc ∉ {0, None}, not only when `ok` is False | medium |
| H4 (cross-group, W-MULTI) | windows/tests/w_multi.py:354-359 (`_outcome`) with :689-695 and the class override near :26 | `timed_out` is taken from the launcher record (False), not from the child JSON (`timed_out` true, "ffmpeg timed out" after 35.3 s). So the health check after a hang is skipped, the Kiyo's real onset is labelled `device_not_ready` "re-enumerating" although no arrival or removal happened (`device_gone` null), no fault is marked, and the suite-wide first failure misses it | `timed_out = cmd.timed_out or s.timed_out or err.class == "timeout"`. Require an observed arrival or removal before saying "re-enumerating". Call `ctx.record_failure` for every failed child with the child's `utc_started` | medium |
| H5 | windows/tests/w_ctrl_effect.py:463-472, 505-516 (`run_ds`) | DS sets run at fixed offsets and the capture length is fixed. When a set is slow (Kiyo focus r1: 1.03 s and 1.48 s), the next segment window is empty (`n` 0), the run's effect is None, and it counts as a failed run. Kiyo DS focus went to 2/3, which set criteria (4) and (5) False | Chain each set to the previous set's completion plus `gap`, and extend the capture to the last set plus settle time. Or, when a segment has `n` 0, mark the run "unmeasured" and retry it once, without counting it as failed | medium |
| H6 | windows/tests/w_ctrl_effect.py:635-638 against :662 | `run_counts_ok` uses the all-segment `effect_ok`, but criterion 3 uses the after-start effect. Kiyo gain: `runs_ok` 3/3 while `effect_ok` is False | Use the same effect definition in both: `effect_after_ok`, with `effect_before_ok` not False | low |
| H7 | windows/tests/w_ctrl_effect.py:814 (gain fix) and :331-336 (`judge` labels segments with `vals`) | The gain test fixes exposure at mid-range whatever the luma. On the Kiyo the base luma is 123, so high gain hits a ceiling (128→230 adds 1%). Separately, on the C930e the 0 ms manual-keep re-applies the *reverted* gain (about 50), so segment 1 is judged as 26 | Choose the fixed exposure from the exposure test's measured luma (target first-segment luma 30-60). Label segment 1 with `value_at_first_frame` when `held_through_start` is False | low (affects the Kiyo gain criterion) |
| H8 | windows/tests/w_id.py:270-271 | `same_port_replug` stays None although run_suite.json `arrivals_since_previous_run` and the previous `discovery.json` show the Kiyo (a real replug) and the generic re-arriving with key, instance and symlink unchanged | Derive `same_port_replug` from the previous suite run when a camera re-arrived and its identity is unchanged (source "unattended, previous run"). Keep the cell provisional until A1 | low |
| H9 | common/rating.py:140 | The note text says "provisional yes" on a **partial** cell | Change it to "partial (provisional): attended persistence steps not run" | cosmetic |
| H10 | windows/tests/w_kiyo.py:426-427 | Criterion 2's `detail` is the `failed_from_first_poll` dict ({mf: false, ds: false}) under `met` True, which reads as a contradiction | Use detail `{"first_ok_poll": …, "first_failed_poll": …}` | cosmetic |
| H11 | windows/tests/w_env.py:49 (patterns), :204-235 (flags) | Processes in the conferencing and browsers categories (Discord, Firefox) are matched but not flagged. Signal.exe, which attached to the Kiyo at 00:12, is not in any pattern | Flag any non-suite process that the activity monitor shows holding a camera at W-ENV time, and add Signal to the conferencing pattern | low |

The B1 path (device not answering → G-CTRL `no`) was not exercised live in run 2, because the Kiyo answered during W-CTRL-EFFECT. Only the offline tests cover it.

**Re-runs.**
- H1-H4: no camera needed to fix them, but the onset needs a new Kiyo window (replug, then 4 h or more).
- H5-H7: W-CTRL-EFFECT on the Kiyo before 3.5 h of plug-in age.
- H8-H10: re-rate only.
- Attended experiments: the idle-poll-only Kiyo window past 4 h (time against trigger), A4 (LPM Off), Razer Synapse quit, and a LogiTune-free C930e exposure test.

---

## Verifier notes

Adversarial check of the sections above. I recomputed every figure from the result JSONs, the raw per-run `summary.json`/`frames.jsonl`/`frames.mjpeg` and `run_suite.json`, and I re-read the cited code. I opened no camera and changed no suite or result file. Labels: **measured** (file + field), **code** (source line), **inferred**.

### V-A. Rating cells: all 15 reproduce

- **G-CTRL, all 8 cells reproduce exactly** (measured: `W-CTRL-EFFECT.json verdicts[*].criteria[*].met` against `control_rating_row`/`rate_ctrl`, code w_ctrl_effect.py:635-670 and rating.py:322-372).
  - Kiyo MF fails (3) and (4) on gain alone: `ratio_after_start` 1.009/1.012/1.012, against the half threshold 1.075 (w_ctrl_effect.py:327-328).
  - Kiyo DS also fails (5): focus r1 has segments `n` [10,5,5,0,0].
  - Generic fails (3), (4) and (5): gain and WB.
  - C930e fails (4), (5) and (6).
  - C922 passes all six.
- **Two corrections to the cell explanations:**
  - **C930e criterion (5).** It is False for reasons other than the effect. Exposure runs have `effect_ok` (all segments) False, because segment 1 is really at −5. Gain runs have `effect_ok` **True** in 3/3 but `held_through_start` False (`run_counts_ok`, :635-637). So (5) counts the same stream-start reset that (4) and (6) already count. H6 therefore applies in both directions: it inflates (5) on the Kiyo and duplicates (4) on the C930e. `runs_ok_after_start_only` is computed (:867-870) but no criterion uses it.
  - **Kiyo DS cell.** All 24 Kiyo DS captures ran in **raw YUY2**, not MJPG (`runs[*].capture_error.stage` "format", `segments[*].frame_kinds` ["raw"]). No other camera or path had a fallback. The cell is labelled with the MJPG mode and does not say this.
- **ctrl_list_equivalence, G-ID, key_source_stability, policy_traps and kiyo reproduce** (measured). `policy_traps` was re-rated at suite_log.txt:42. G-ID is `provisional` true with note "provisional yes", as H9 says. Kiyo `ok` is 190/294 per API.

### V-B. Finding-by-finding

| ID | Verdict | Verifier evidence / correction |
| --- | --- | --- |
| K1 | confirmed | Raw `ds_staggered_036` Kiyo: 300 frames, 00:02:47.80→00:02:59.95. `_037`: start 00:03:03.935, `error.open_duration_ms` 35271.8, `timed_out` true, exit 5. **Missed:** ffmpeg used **98% of one core** for the whole hang (`cpu.process_cpu_s` 29.5 over `lifetime_s` 30.0). So the dshow open was spinning in user mode, not blocked in a kernel call (inferred). |
| K2 | weakened | **Phase 2 started on the stream path before the controls.** `ds_staggered_038` (Kiyo started 00:03:50.68) failed in 3.1 s with "Could not RenderStream to connect pins" / I/O error, 11 s before the first 0x8007001F GET (00:04:01.9). So the hang→fast-fail boundary is between 00:03:45.7 and 00:03:50.7. The fast KS GET takes 0.24 s inside wincam (`poll_00220_mf_fail.json` utc_started→utc_finished) and 0.44-0.48 s per poll (`elapsed_s`). "problem_code stayed 0 through 00:13:20" is **not measured by W-KIYO**: `arrivals_seen` gets a row only when `last_arrival` changes, so problem_code was sampled once, at i=0 (w_kiyo.py:285-288). The only later evidence is W-MJPEG's camera list at about 00:11 (`problem_code` 0). |
| K3 | weakened | Vendor-process facts are correct: one `vendor_process_changes` row, at i=0. But the activity monitor is **aliased by the camlock**. Each round samples activity once, *before* the MF lock wait (w_kiyo.py:270). So it never saw the W-MULTI ffmpeg holds of `ds_staggered_034`-`037` (00:01:53-00:03:39). "No activity change 00:01:22→00:12:04" therefore does not show that nothing else touched the Kiyo near the onset. |
| K4 | weakened | The arithmetic holds: run 1 bracket 200.6-224.3 min, run 2 210.58 min, uptime 4.3 h and 9.6 h. But n=2, and run 1 is only a 24-min bracket. "0 suite streams" in run 1 leaves out the quick self-test that streamed it at 171-200 min. The same LogiTune and Razer agents ran in both windows and could hold a timer that starts at plug-in. Read it as "consistent with an age-dependent state at about 210-224 min". "Moderately strong" overstates two coinciding points. |
| K5 | confirmed | `first_failure.mf.lock_wait_s` 38.0. Raw `utc_started` 00:03:39.454691Z. run_suite `faults.first_failure[kiyo].utc` 00:04:02.348704, `stage` control_get. **Extra skew:** DS rows inherit the round's MF-time plug-in age (w_kiyo.py:293, 301). summary.md gives "00:03:42 ds → not_answering, plug-in age 210.5 min", but the true age is 211.2 min. |
| C1 | weakened | The numbers reproduce: ages 188.0-192.4 min (raw `utc_started` of `mf_exposure_r0` and `ds_focus_persist`). Gain luma 123.4→148.3→149.6 on MF and 123.4→148.8→149.5 on DS. **"Compressive gain response" is not shown to be the sensor gain.** I decoded `mf_gain_r0` frames: luma 118-121 at gain 26, 146.5-147.6 at 128, 150.2-151.2 at 230, with **0% of pixels ≥250 and p95 228-235**, so nothing clips. Exposure is also compressed above luma about 100 (−7→−4: 97→123, +27%, against 18→90 on the C922). The Kiyo runs with non-default brightness 205, contrast 201 and backlight_compensation 1 (W-CTRL-LIST `ranges`), which is a likely ISP tone-curve confounder (inferred). Also, the Kiyo "persisted" result on the DS path is an MF measurement (see N1). |
| C2 | weakened | 14/14 exposure resets confirmed: 6 exposure runs, 6 gain-run `fixed_controls`, 2 persistence. Gain 49-51 at 6/6 runs plus 50/51 at persistence, so 8/8. **"Regardless of the value set" was not tested:** only 26 was ever set before start. In run 1 the same reset landed on **14-18** (run 1 `gain.runs[*].schedule[0].before_value`). Run 1's W-CTRL-LIST gain was 8 (daytime); run 2's was 43 (evening). So the post-start gain follows the camera's AE gain. That supports the "one-shot AE at stream start" reading (inferred). |
| C3 | confirmed | Gain `value_at_first_frame`/`value_before_first_set` is 4 in 6/6 runs. Persistence `value_at_first_frame` is 4 although the reopen readback is 6. Gain 4→6: 67.6→67.6. WB 0.97-1.0. Exposure 9.24-9.34. |
| C4 | weakened | Luma and WB agree MF vs DS within about 2% (C930e exposure segment 1 within about 4%). **Sharpness does not:** Kiyo focus `ratio_max_min` is 7.85-8.20 on DS (raw YUY2) against 10.73-11.26 on MF (JPEG), about 27% lower. The raw-plane path is validated for luma and R/B, not for the Laplacian sharpness metric. |
| C5 | confirmed | `paths.*.restore.restored` True on 8/8 paths. Per-control `restore.restored` True, `first_attempt`/`retried` None, `errors` []. C930e WB `ratio_after_start` 1.105-1.114. C930e gain segment 1 luma 42.7-43.8. The match is on flags: C922 gain is restored to 0, the value read at W-CTRL-EFFECT start; W-CTRL-LIST had 38, which is AE-driven although flagged manual. |
| C6 | confirmed | The run 1 vs run 2 W-CTRL-LIST `ranges` differ only in `value` (C922 focus/gain/WB; C930e exposure/focus/gain). The Kiyo has no difference at all. The C930e's non-default saturation 53 and WB value 6500 were also unchanged (no C930e replug). |
| I1 | confirmed | `timing_ms` p50 values reproduce. `discovery.json`: instance, parent, function instance, MF symlink, DS path and MF/DS index are all equal between runs for all 4 cameras. `arrivals_since_previous_run.re_arrived_since` is true for the Kiyo and the generic. |
| E1 | confirmed (nits) | `ds_bypasses_frameserver` is in **W-POLICY**, not W-ENV. FrameServer is DEMAND_START, so a new PID (48280→46428) is the normal idle stop/start, not a fault. C930e stale tier-1 flag and driver 1.2.75.34 (Logitech) confirmed. |

Other small corrections:
- §2.1 row "MF poll 189 (scheduled 00:02:41.98 …)": 00:02:41.98 is the *pre-lock stamp*. The schedule slot (`sched_t_s` 1890) was 23:20:42Z, 42 min earlier.
- §3.2 "Kiyo exposure after-start 1.23-1.25, barely above 1.125": a 9-11% margin is not "barely".
- §4: the C930e focus `ratio_max_min` also dropped from 10.2-10.9 (run 1) to 6.8-7.2 (run 2). That is lighting or scene, like the C922 rows.

### V-C. Harness bugs

| ID | Verdict | Note |
| --- | --- | --- |
| H1 | confirmed | `t_utc` at w_kiyo.py:178 (pre-lock). Activity at :270 and age at :293 are taken once per round. Max `lock_wait_s` is 455.9 s on MF and 153.6 s on DS. Extend the fix so each API's row carries its own post-lock age. |
| H2 | confirmed (numbers) | Catch-up at :249. Recomputed from `t_s`: MF gaps <1.5 s: 48, 1.5-2.5 s: 63, >30 s: 29. **Max gap 514 s on MF** and 463 s on DS. `t_s − sched_t_s` is 2123 s at the end and 2838 s at its peak, not "about 2,500". |
| H3 | confirmed | suitectx.py:493. The raw timeout JSON has no `ok` key (`ok` None). |
| H4 | confirmed + extended | w_multi.py:354-359 reads `cmd.timed_out` (False). The child JSON says `timed_out` true. `class_before_override` "timeout" was overridden to `device_not_ready` with `device_gone` null, and `health_check_after_hang` is null (branch at :689 not taken). `ds_staggered_038` (RenderStream, 3.1 s) was also classed `device_not_ready` ("re-enumerating") with no arrival. **Also:** the fault gate applies only from the next test, so W-MULTI launched the faulted Kiyo **15 more times** (`pyav_ds_*_047`-`061`, 00:05:45-00:09:09, all RenderStream failures in 0.34-0.5 s). Multi-launch children are not passed through `_scan_camcmd` (only `run_camcmd` calls it, suitectx.py:176). The generic's 00:00:28 first failure came from a single-command run. |
| H5 | confirmed | Kiyo DS focus r1: set 450 took 1.030 s and set 600 took 1.483 s (r0 and r2: 0.041-0.066 s). The 450 segment window was 27 ms. The 600 segment began 10 ms *after* the last frame (33515.579 s against `t_last` 33515.569 s). Even normally the capture ends only about 1.6 s after the last set, so any set slower than about 1.4 s empties the last segment. |
| H6 | confirmed + extended | See V-A: on the C930e it double-counts the reset in (5). |
| H7 | weakened | **Label half confirmed** (code :414 `0:{name}=manual` keeps the reverted value; on DS the camera reverts by itself, giving `value_before_first_set` 49-50). **Causal half not shown:** nothing clips (C1), so a darker fixed exposure is a test, not a known fix. Keep it low severity and phrase it as "try a darker fixed exposure (luma 30-60) to separate the ISP tone curve from the gain". |
| H8 | confirmed | w_id.py:270-271. |
| H9 | confirmed | rating.py:140. |
| H10 | confirmed | w_kiyo.py:425-427. |
| H11 | confirmed | w_env.py:49 has no Signal pattern. The flag block (:204-235) flags only Logitech and Razer. |

### V-D. Missed (new)

- **N1 (harness, medium): the DS-path persistence check is an MF capture.**
  - Code: `persistence_check` (w_ctrl_effect.py:538-545) always calls `ck.wincam_capture`, which is MF (the stderr shows `wincam.exe capture --api mf` in `ds_*_persist`). It compares the result with the DS run's last segment.
  - Effect: on the Kiyo that comparison is MF JPEG against DS raw YUY2. Kiyo DS focus `metric_ratio` is 0.739, and passes only because the sharpness tolerance is ±0.35. The DS "persisted" column never measures DS.
  - Fix: capture through the DS path (`pyav_capture_argv`, as in `run_ds`) on the DS leg, or compare against the MF run's metric and label the result "MF".
- **N2 (harness, low): the gain persistence capture does not re-apply the fixed exposure.**
  - Effect: on the C930e, exposure resets to −5 at that start, so luma *rises* 1.15× although gain fell from 230 to 50. `persisted` False is still right, because it comes from `value_at_first_frame`, but the metric conflates two resets.
  - Fix: add `0:exposure=<fix>` to the persistence schedule for gain.
- **N3 (onset, measured): the stream-path signature after the hang.** "Could not RenderStream to connect pins" appeared at 00:03:50 (W-MULTI 038), then in all 15 later PyAV runs. Together with the 98% CPU spin during the 30 s hang (K1), this is the DirectShow face of the failure. It belongs in the onset timeline between 00:03:45.7 and 00:04:01.9.
- **N4 (W-KIYO, cosmetic):** poll rows record `timed_out` false for the rc 5 control-query timeouts (launcher field, w_kiyo.py:182). This is the same launcher-vs-child pattern as H4.
- **N5 (cell labelling, low):** the G-CTRL Kiyo DS cell (and its JSON `mode`) should note "DS frames were YUY2 (PyAV format fallback)". The rating ignores `capture_error.stage == "format"`.
