# Analysis: controls, identity and environment (W-CTRL-LIST, W-CTRL-EFFECT, W-ID, W-ENV, W-POLICY)

Run: Gerald, Windows 11 build 26300.9711, suite `suite_20261106T181941Z`, 2026-11-06 13:19-15:06 local (18:19-20:06Z; local = UTC-5). Analysed from the result JSONs, `suite_log.txt`, `discovery.json`, the raw frames folder and the suite code. No camera was opened and no suite or result file was changed.

Labels: **measured** = read from a result file (file + field given); **inferred** = my reasoning from measured facts; **code** = confirmed by reading the suite source.

Cameras: C922 `046d:085c:sn=C922SN01` (serial key), Kiyo `1532:0e05:port=…/4.4`, generic `4c4a:4a55:port=…/13.1.2`, C930e `046d:0843:port=…/7`.

---

## 1. Every rating cell, and what produced it

### 1.1 G-CTRL (W-CTRL-EFFECT, one cell per camera and control path)

`rating.rate_ctrl` (common/rating.py:186-221) returns yes only if all six criteria are True: (1) listed with the descriptor's range, (2) set + readback agree, (3) effect visible for exposure/gain/WB/focus, (4) works before and after stream start, (5) 3/3 runs, (6) no workaround. Otherwise it returns partial. It returns untested if no control was measured (w_ctrl_effect.py:431).

| Camera | Path | Cell | Deciding criterion (W-CTRL-EFFECT.json `verdicts["G-CTRL|<key>|<api>"]`) | Real or artefact |
| --- | --- | --- | --- | --- |
| C922 | mf | **yes** | All six criteria met. Exposure, gain, WB and focus all 3/3 `runs_ok`; `persisted_after_reopen` true; `restore` true | real |
| C922 | ds | **yes** | Same as mf | real |
| Kiyo | mf | **untested** | `criteria[0]` = "no settable control on this path". Every control was skipped with `"no manual mode"` (`measurements.cameras[kiyo].paths.mf.controls.*.skipped`) | **artefact**: the Kiyo was in its failure state (see 2.1). A misread caps field was logged as "no manual mode" |
| Kiyo | ds | **untested** | Same as mf | **artefact**, same cause |
| generic | mf | partial | (3) effect False: gain `effect_ok` False 0/3, WB `effect_ok` False 0/3. (4) False because `after_start_ok` needs the effect. (5) False because gain and WB `runs_ok` = 0/3. Exposure passed 3/3 | **real**: the camera accepts gain and WB values but the image does not change (2.2) |
| generic | ds | partial | Same as mf: gain and WB 0/3, exposure 3/3 | **real** |
| C930e | mf | partial | (4) False and (6) False. Exposure `before_start_ok` False; `workaround` = "a value set before the stream starts reads back but does not reach the image; re-apply it after the first frame". (5) False because exposure `runs_ok` = 0/3. Gain, WB and focus 3/3 | **real**: the camera or its host stack resets the exposure set before the stream starts (2.3) |
| C930e | ds | partial | Same as mf, but exposure `runs_ok` = 1/3 (run 3 held the set made before start) | **real** |

### 1.2 Other cells in this group

| Table / cell | Source | Why | Real or artefact |
| --- | --- | --- | --- |
| G-CTRL, row "all", **untested** | W-CTRL-LIST.json `verdicts.G-CTRL` | Always `rating.untested("listing only…")` (w_ctrl_list.py:196) | **artefact** (presentation): a listing test should not emit a G-CTRL cell. It reads like a failed cell |
| ctrl_list_equivalence, all, **yes** | W-CTRL-LIST.json `verdicts.ctrl_list_equivalence` | All 4 cameras `met` true: 0 missing descriptor controls in MF and DS, 0 MF-vs-DS field differences | real |
| G-ID, all, **partial** | W-ID.json `verdicts.G-ID` | Criterion 1 (1:1, 6/6 APIs) true. Criterion 2 (20 identical repeats) true. Criterion 3 (persistence) `null`: `reboot` null, `same_port_replug` null, `port_move_serial` true. `note`: "provisional yes: attended persistence steps (A1…) not run yet" | **artefact (missing data)**: no API or camera failed. `rate_id` (rating.py:92-97) maps "not measured" to partial, the same label the plan uses for "key changes on replug" |
| G-ID_per_api, 6 x **partial** | W-ID.json `verdicts.G-ID_per_api` | Each is `rate_id({api: runs}, …)` with the same null persistence, so partial. The values are bare strings, with no criteria stored (w_id.py:224-225) | **artefact (missing data)**. Every API is 1:1 and stable |
| key_source_stability, **yes** | W-ID.json `verdicts.key_source_stability` | `per_api.pnp_discovery`: 20 runs, `order_stable` true, `one_to_one_every_run` true | real |
| policy_traps, **yes** | W-POLICY.json `verdicts.policy_traps` | All 6 criteria `met` true. Pseudo-rating, not a plan goal | real, but weak for rotation and multi-app: the result only says nothing was found (3.2) |
| W-ENV | none | No verdict by design (w_env.py:182). Its `flags` are context | n/a |

---

## 2. Non-yes cells: camera or harness?

### 2.1 Kiyo untested: harness artefact on top of a real Kiyo failure

- **Measured.** At 13:20 W-CTRL-LIST read all 16 Kiyo controls normally through both APIs. For example, exposure −11..−2 default −6 caps auto+manual (`W-CTRL-LIST.json measurements.cameras[1].ranges`).
- **Measured.** The Kiyo's first failed camera command was at 13:43:49, in W-MJPEG (`suite_log.txt:506`: `wincam capture … vid_1532 … rc=5 10.266s`). Every later Kiyo capture returned rc=4 (log lines 1124-1167, 1428-1430).
- **Measured.** By 14:56 W-KIYO had 0/61 OK polls per API (`W-KIYO.json verdicts…criteria[0].detail`). Each poll showed `supported` 16, but `exposure` was null and the GETs failed (`evidence.first_failure.mf.controls_with_failed_get`).
- **Code.** `capkit.control_table` keeps only `supported` controls (capkit.py:236-242). In `wincam read_ctl`, when IAM GetRange fails, the control still counts as supported if KS BASICSUPPORT succeeds, but `caps` is filled only by a successful KS GET (wincam.cpp:1200-1204, 1155-1162). So `caps_flags_names` is empty, `manual_capable()` is False, and the skip reads "no manual mode" (w_ctrl_effect.py:341-343).
- **Measured.** The Kiyo's two initial reads took 0.265 s, against 0.047-0.063 s for the other cameras (`paths.*.initial_read.elapsed_s`). Their JSON was never saved, only `run_brief`.
- **Verdict.** The plan says a Kiyo failure is a result. The Kiyo could not be controlled at 14:51. That is real Kiyo behaviour, about 3 h 44 min after plug-in (arrival 09:59:24 local, first failure 13:43:49). The cell says untested with a misleading reason ("no manual mode") because of the harness. The run order (W-CTRL-EFFECT after W-MJPEG, W-CYC, W-MULTI and W-TS) also guaranteed that the Kiyo was already dead when this test reached it.

### 2.2 Generic partial: real camera behaviour (gain and WB have no visible effect)

- **Measured** (`cameras[4c4a…].paths.mf.controls`):
  - **Gain** 1..7, values 2/4/6, exposure held manual at −2. Luma per run: [86.9, 86.4, 86.8], [87.9, 87.5, 88.0], [89.3, 89.2, 89.9]. `ratio_last_first` 0.999-1.006 against 1.15 required. DS gave the same: 83.7-84.7, ratios 0.996-1.005.
  - **WB** 0..6500 (manual only, no AUTO cap), values 2800/4650/6500. R/B per run 0.871/0.868/0.863 (MF) and 0.859/0.858/0.859 (DS). Ratio 0.99-1.004 against 1.10 required.
  - **Exposure** works: luma 23.6 → 85.7 → 208.2, ratio 8.7-8.9.
- **Why it is not a harness artefact (inferred, strong).**
  - The same metric code measured R/B 0.98 → 2.60 on the C922 and gain luma 38 → 102.
  - The generic's luma (~87) is mid-scale, not saturated or dark.
  - Every set read back correctly (`before_start_readback`/`after_start_readback` true).
  - The flat response holds between segments set during streaming (4 → 6), so it is not a stream-start issue.
  - The descriptor has no WB-auto bit (PU bmControls 0x077b, W-CTRL-LIST), which fits a sensor that runs its own fixed or automatic white balance and ignores the temperature value. Inferred.
- **New, measured.** The generic also resets **gain** at stream start. A gain of 2 set before start read back 2, but the first in-stream event saw `before_value` 4 (the default) in all 3 MF runs (`runs[*].schedule[0].before_value`). Exposure and WB set before start held. This does not change the rating because gain has no effect anyway, but control code must not assume that values set before start survive.

### 2.3 C930e partial: real behaviour (values set before start revert at stream start)

- **Measured** (`cameras[046d:0843…].paths.mf.controls.exposure.runs[*]`):
  - Exposure −9 set before start: hr S_OK, read back −9 manual (`controls_before[0]`).
  - At the first in-stream event (+1000 ms, about 30 frames) the camera reported `before_value` **−5**, flags manual, in all 3 MF runs (`schedule[0].before_value`). This happened even when the previous value was −4.
  - Luma per segment: 109.8 (meant to be −9) → 37.4 (−7) → 155.1 (−4).
  - Values set during streaming work: `ratio_after_start` 4.15-4.23 (1.125 required), 3/3 on MF and 3/3 on DS.
  - DS exposure failed the same way in runs 1-2 (luma 114.6 and 108.6 at −9). Run 3 held (luma 6.2 → 37.1 → 154.9). I could not explain run 3 from the data: the DS set records keep only `matches`, not the value read before the next set.
- **New, measured.** **Gain** set before start also did not hold on the C930e. 26 was set and read back, but the first in-stream event saw 18, 15 and 14 (`gain.runs[*].schedule[0].before_value`). The gain run's first segment had luma 111, about the −5 exposure level, not the −7 the harness fixed. So the fixed exposure for the gain test also reverted (inferred from luma). WB (2800) and focus (0) held through start.
- **Matches the prior work.** REPORT finding 11 and RERUN_20261027 line 148 say C930e manual exposure set before streaming is not applied and reads back −5. Today's run pins down when it happens (at stream start) and shows that re-applying after the first frame works. That answers REPORT's next step 6 ("re-apply exposure after stream start"). LogiTune was still running, so a LogiTune-free check is still open.
- **Inferred cause, open.** C930e firmware, or LogiTune reapplying a profile when the stream starts. The C930e is a LogiTune device; the C922 is not, and the C922 held every value. Also, the C930e's composite devnode uses Logitech's driver package 1.2.75.34 in configuration 2 (`discovery.json cameras[3].driver_provider/driver_version/port_connection.current_configuration`); the other three use Microsoft 10.0.26100.9711. To tell these apart: attended run with LogiTune and its updater stopped.
- **Rating impact.** partial is correct under the plan ("needs a workaround"). The C930e is not "ignoring manual exposure via MF": manual exposure works through both MF and DS once streaming.

### 2.4 Marginal pass to watch (threshold, not a bug)

- **Measured.** C930e WB on MF, runs 1-2: `ratio_after_start` 1.0531 and 1.0531, against 1.05 required (half of 1.10). Run 3: 1.129. DS: 1.115-1.131. All three are counted as passing, but a small change in the scene could flip runs 1-2.

---

## 3. Quantitative answers to the plan's questions

### 3.1 Do MF and DS expose the same controls and ranges, and do they match bmControls? Yes, on all 4 cameras

- **Measured** (`W-CTRL-LIST/*_controls_{mf,ds}.json`):
  - Both APIs queried every CAMERACONTROL id 0-23 and VIDEOPROCAMP id 0-15 (a superset of the plan's 0-13).
  - All three interfaces were present on every camera (IAMCameraControl, IAMVideoProcAmp, IKsControl).
  - Every unsupported id returned `iam_get_range` 0x80070490 (ERROR_NOT_FOUND) on every camera and both APIs.
- **Supported counts** MF = DS (`measurements.cameras[*].counts`): C922 16, Kiyo 16, C930e 16, generic 11.
  - Missing descriptor controls: 0 on MF and 0 on DS.
  - MF-vs-DS differences over min/max/step/default/caps/value/flags: 0.
  - IAM-vs-KS range disagreements: 0.
- **bmControls** (`descriptor.*_bmControls`):
  - C922, C930e and Kiyo all have CT 0x020a2e (AE mode, AE priority, exposure abs, focus abs, zoom abs, pan/tilt abs, focus auto) and PU 0x175b (brightness, contrast, saturation, sharpness, WB temp, backlight, gain, power line, WB auto).
  - Generic: CT 0x00000a (AE mode, exposure abs); PU 0x077b (adds gamma; no WB auto). Every bit maps to a supported KS id. Where the descriptor has an auto bit, the control's caps include AUTO.
  - The AE mode bitmap (UVC modes 1/2/4/8) collapses to KS auto/manual (inferred from the KS API).
- **Extras and degenerate ranges** (measured):
  - `cc.focal_length` is listed through IKsControl on every camera with value 0, but every descriptor has wObjectiveFocalLength fields of 0.
  - `cc.auto_exposure_priority` has range 0..0 step 0 on both IAM and KS for the C922, C930e and Kiyo, while its current value is 1 on the C922 and C930e. The range is unusable, so code must treat this control as boolean.
  - Generic `pa.powerline_frequency` is 0..0.
- **Ranges per camera** (measured, `ranges`):
  - C922: exposure −11..−2 (def −5), focus 0..250 step 5, zoom 100..500, WB 2000..6500, gain 0..255.
  - C930e: exposure −11..−2 (def −5), focus 0..255 step 5, zoom 100..400, WB 2000..7500, gain 0..255.
  - Kiyo: exposure −11..−2 (def −6), focus 0..600 step 1, zoom 100..400, WB 2000..7500 step 10.
  - Generic: exposure −7..3 (def −7), gain 1..7, WB 0..6500 manual only, brightness −127..127, contrast and saturation 0..511, gamma 10..30 step 10, sharpness 0..256.
  - Per-camera range tables are required.
- **Vendor XUs** are not reachable through these property sets: C922 has 6, C930e 7, Kiyo 2, generic 1 (`descriptor.extension_units`). Plan §8 question 3 is still open.
- **Timing** (measured): a read-only control listing takes 24-30 ms through DS and 37-54 ms through MF (`elapsed_ms`). MF activation alone is 23-38 ms.
- **Inferred.** Equality is expected: both APIs reach the same usbvideo KS property sets. The result confirms there is no API-specific filtering on build 26300.

### 3.2 Which controls had a visible effect? (W-CTRL-EFFECT, mode MJPG 1280x720@30, 3 runs per control and path)

| Camera | Exposure luma, last/first (after start) | Gain luma | WB R/B | Focus sharpness max/min | Before start | Read back | Persisted after reopen |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C922 mf/ds | −9/−7/−4: ~6 → 23 → 105, ratio 16.9-17.9 (4.57-4.63) | 26/128/230: 38 → 78 → 102, ratio 2.68-2.71 (1.30-1.31) | 2800/4650/6500: 0.98 → 1.84 → 2.62, ratio 2.63-2.72 | 0/60/125/190/250: 0.0165 → 0.0005, ratio 29.9-31.1 (sharpest at focus 0: distant scene) | all held (first in-stream readback = value set before start) | 24/24 runs | all true |
| C930e mf/ds | 110 (reverted to −5) → 37 → 155, ratio 1.38-1.43 (4.0-4.2). DS run 3: 6 → 37 → 155, ratio 25.1 | 111 → 184 → 208, ratio 1.73-1.94 (1.125-1.129). The gain set before start reverted to 14-18 | 1.01-1.05 → 1.10-1.32 → 1.15-1.49, ratio 1.14-1.42 (1.053-1.131) | 0/65/130/190/255: peak 0.0006 at 65, ratio 10.2-10.9 | exposure and gain revert at stream start; WB and focus held | 24/24 runs | all true (but exposure −4 would revert at the next stream start) |
| generic mf/ds | −5/−2/1: 23.6 → 85.7 → 208, ratio 8.7-8.9 (2.40-2.46) | none: ratio 0.996-1.006 | none: ratio 0.99-1.004 | not supported | gain reverts to the default 4; exposure and WB held | 18/18 runs | all true |
| Kiyo | not measured (device not answering) | | | | | | |

All values are measured from W-CTRL-EFFECT.json `measurements.cameras.<key>.paths.<api>.controls.<name>.runs[*].{metric_values, ratio_last_first, ratio_after_start, ratio_max_min, schedule[0].before_value}` and `persisted_after_reopen`.

### 3.3 Were all controls restored? Yes

- **Measured** (`paths.*.restore.restored` true on all 6 tested paths; no retry needed, since `first_attempt` is absent). End-state readback from a fresh process (`restore.after`):
  - C922: exposure auto, WB auto, focus auto, gain 0 manual.
  - C930e: exposure auto, WB auto, focus auto, gain 15 manual.
  - Generic: exposure auto, gain 4, WB 4500 manual.
- These flags equal the suite-start state read at 13:20 by W-CTRL-LIST (`ranges.*.flags_names`). The only difference is the C930e's gain value (8 at 13:20, 15 at restore), and auto-exposure drives that value anyway (inferred).
- The Kiyo was never touched. W-CTRL-EFFECT recorded `errors` = [].

### 3.4 W-ID: identity, indices, timing

- **1:1 and stable** (measured, `W-ID.json measurements.per_api`): MF, DS, PyAV-dshow, FFmpeg CLI, OpenCV MSMF and OpenCV DSHOW each mapped 20/20 runs 1:1 to the 4 keys, with `distinct_orders` = 1 and 0 errors. The key source itself (`pnp_discovery`) was also stable over 20 runs.
- **Enumeration time** (measured, `timing_ms`, p50 / max):

  | API | p50 | max |
  | --- | --- | --- |
  | MF (`wincam list`) | 2.10 ms | 2.74 ms |
  | DS | 4.57 ms | 5.03 ms |
  | OpenCV MSMF | 1.98 ms | 3.71 ms |
  | OpenCV DSHOW | 2.77 ms | 5.49 ms |
  | PyAV `list_devices` | 154 ms | 192 ms |
  | FFmpeg CLI | 213 ms | 236 ms |
  | Suite discovery (incl. child process) | 120 ms | 130 ms |

  PyAV and FFmpeg bind every DS filter, including virtual ones; the NVIDIA Broadcast VCAMDS DLL logs into PyAV's stderr (`helper_runs.pyav.stderr_tail`).
- **Index order** (measured, `first_run_entries`, `discovery.json virtual_devices`):
  - MF: indices 0-3 are NDI Webcam Video 1-4; then C922 4, Kiyo 5, generic 6, C930e 7.
  - DS: C922 0, Kiyo 1, NDI 2-5, generic 6, C930e 7, then OBS-Camera 1-4, NVIDIA Broadcast, SpoutCam and OBS Virtual Camera at 8-14.
  - OpenCV indices equal the wincam enumeration order (`opencv_index_vs_enumeration_order.*.equal` true).
  - So `VideoCapture(2, CAP_DSHOW)` opens an NDI virtual camera, not a USB camera.
  - Against 10-27 (`natural_evidence.earlier_api_order`: C930e MF 6 / DS 2, generic MF 5 / DS 1), every index has moved.
- **Port moves today** (measured, `natural_evidence.cameras`, `discovery.json first_install`):
  - **C922** (serial): moved from root port 1 (10-27) to 13.1.4. Key, composite instance ID, function instance ID and MF symlink all unchanged (`key_same`, `function_instance_same`, `mf_symlink_same` true). Windows builds the instance ID from the serial.
  - **C930e** (no iSerial): moved from 13.1.4 to root port HS07. New devnode first installed 10:00:22 local today. Key, instance IDs and symlinks all changed (`key_same` false). It also **lost tier-1 metadata**: the old instance `8&39DEC205&1&0000` still carries `MetadataBufferSizeInKB0` = 5, and the current `6&2206973F&0&0000` has none (`W-ENV.json tier1_metadata.all_instances_with_keys`). The registry value is per interface instance, so moving a serial-less camera to another port silently drops it back to tier 0.
  - **Generic** (no iSerial): moved from 13.1.3 to 13.1.2. New devnode first installed 09:58:37 local. Key and symlinks changed, as the design expects for port keys.
- **Reboot and same-port re-arrival** (measured, not used by the rating):
  - Gerald booted at 09:26 local today (`persistence_inputs.boot_time_utc`), after the 10-27 run. The C922's serial key survived (`serial_keys_kept_over_reboot` [true]).
  - The generic re-arrived on the same port at 13:17:09 local, before the run (`discovery.json last_arrival`). It re-arrived again at 14:44:44, during W-MULTI (`W-CTRL-EFFECT.json measurements.arrivals.before`). Afterwards its instance ID `7&7DCC7CE&0&2` and function ID `8&232e60d4` were unchanged, and W-CTRL-EFFECT opened it by the same symlink (suite_log.txt:1497ff).
  - This is unattended evidence that a port key and its symlink survive a same-port re-arrival. It is not the controlled A1 test.

### 3.5 W-ENV / W-POLICY: environment and traps

- **Power** (measured, `W-ENV.json power.settings`, Balanced scheme):

  | Setting | AC | DC |
  | --- | --- | --- |
  | USB selective suspend | Enabled | Enabled |
  | USB 3 link power management | Moderate power savings (index 2) | Moderate power savings (index 2) |
  | Hub selective suspend timeout | 50 ms | 50 ms |
  | IOC on all TDs | Enabled | Disabled |

  The global `DisableSelectiveSuspend` key is absent (`usb_service_registry` null). Every camera's function key has `DeviceSelectiveSuspended`=1 (`discovery.json function_device_parameters`). So the LPM hypothesis for the Kiyo (A4) is live: the Kiyo sits on the Thunderbolt xHCI (8086:1138, behind a PCIe switch) at SuperSpeed.
- **Frame Server** (measured, W-ENV `services`, W-POLICY):
  - FrameServer (PID 48280) and FrameServerMonitor (PID 46000) are RUNNING, start type DEMAND_START. 8 sensor groups.
  - Every camera's sensor group was published at 13:17:09 local, the moment the generic re-arrived. Inferred: Frame Server republishes all groups on any camera arrival.
  - DS bypasses Frame Server on all 4 cameras (ksproxy CLSID, no EnableDshowRedirection). EnableFrameServerMode is not set.
  - The DshowBridge per-app list has one entry: Logitech's `Launcher_Main.exe`. It does not affect the suite's processes.
- **Rotation and multi-app traps** (measured, W-POLICY `settings_page`):
  - Neither value was found. The HKCU/HKLM `CameraSettings` and `HKCU\Software\Microsoft\Camera` keys do not exist (`keys_visited` 1), so "not found" means default or an unknown location.
  - Corroborated: W-FMT/W-MJPEG negotiated native MJPG on MF for every camera (inferred from those cells). A rotation would strip compressed types.
  - Build 26300 has both the share-mode and the multi-app features (`feature_availability`).
  - No Studio Effects or NPU device. Camera privacy is Allow (HKCU and HKLM).
  - The Kiyo's DMFT and plugin values exist but are empty strings, so they are inactive.
- **Processes** (measured, W-ENV `processes.matches`):
  - LogiTune.exe (9 processes), LogiTuneAgent, LogiTuneUpdater (service), and Logi Options+ agent, broker and updater.
  - RazerAppEngine (9 processes) and razer_elevation_service.
  - Discord and Firefox.
  - No OBS, NVIDIA Broadcast app, Teams or Zoom process.
  - W-ENV flags: LPM moderate, selective suspend enabled, Logitech software running, Razer software running.
  - Registered virtual cameras (NDI x4, OBS x5, NVIDIA Broadcast, SpoutCam) are not flagged, but their DS filters load into every process that enumerates DS.
- **Health** (measured, `cameras_health`): problem code 0, devnode status 0x0180600a and no `dn_warn` on all 4 cameras. Tier-1 metadata is on for the C922 and Kiyo and off for the generic and C930e.
- **Kiyo control values at 13:20, the last good read** (measured, W-CTRL-LIST): brightness 205, contrast 201, saturation 110, backlight 1. These are non-default, probably written by Razer software or earlier tests (inferred).

---

## 4. Harness bugs and fixes

| # | File:line | Bug | Fix | Re-run | Severity |
| --- | --- | --- | --- | --- | --- |
| B1 | windows/tests/w_ctrl_effect.py:333-343 (with capkit.py:236-242) | When a control's GET fails (the Kiyo's failure state), `caps` is 0, so the control is skipped as "no manual mode" and the path is rated untested. The initial read JSON is not saved, only `run_brief`. | After `get_controls`, if supported controls have `value` null or a failed `hr.ks_get`/`hr.iam_get`, record `skipped: "device not answering: <hr>"`. Save the JSON to the test dir. Rate the path `no` ("cannot set") with that evidence, as plan §1 requires for Kiyo failures. | W-CTRL-EFFECT on the Kiyo after a replug (ask Dom). Run it before any streaming test (standalone, or move the Kiyo leg early in run_suite.py:56-58). | high |
| B2 | windows/native/wincam.cpp:1087, 1243-1246; windows/tests/w_kiyo.py:97-98,106 | HRESULT fields default to E_NOINTERFACE (0x80004002) and are emitted even when the call was never made, e.g. `iam_get` 0x80004002 on unsupported ids. `w_kiyo` reports `failed_get_hr` from `iam_get` only, so the Kiyo's real KS GET HRESULT (probably 0x8007001F) is hidden behind 0x80004002. | Initialise to a "not called" sentinel and emit `null`. In w_kiyo, take the HRESULT from `ks_get` when `via` == "IKsControl". | Rebuild wincam. Re-run W-KIYO; W-CTRL-LIST for clean HRESULTs (no rating change). | medium |
| B3 | windows/tests/w_ctrl_effect.py:234-236, 287-289 | The before-start check uses only the readback right after the set. The value seen at the first in-stream event (`schedule[0].before_value`) is ignored, so the C930e gain (26 → 18/15/14) and generic gain (2 → 4) reverts passed as `before_start_ok`. For gain/WB the trend check cannot catch a revert towards a lower value. | Add `held_through_start = ev[0]["before_value"] == vals[0]` (MF). For DS, parse `before_value` from set1's JSON. AND it into `before_start_readback`/`before_start_ok`. | W-CTRL-EFFECT (C930e, generic, C922). Ratings unchanged (already partial / yes). | medium |
| B4 | windows/tests/w_ctrl_effect.py:354-357, 218 | The fixed exposure for the gain test is set only before start. On the C930e it reverted to −5, so the gain test ran at the wrong exposure (first-segment luma 111). | Re-apply the `fix` controls in the schedule at 0 ms (MF) or with set1 (DS), and assert the readback. | W-CTRL-EFFECT (C930e) | low |
| B5 | windows/tests/w_ctrl_effect.py:368-371 | "Persistence" is a readback after reopen without streaming. The C930e exposure reads back −4 manual but reverts on the next stream start, so `persisted_after_reopen` true is misleading. | Make the persistence step a short capture: readback at the first frame plus a metric comparison against the last segment. | W-CTRL-EFFECT | medium |
| B6 | windows/tests/w_ctrl_effect.py:421 | `listed: True` and `range_matches_descriptor: None` are hard-coded, so rate_ctrl criterion 1 always passes. Only 4 controls are exercised, against the plan's "and the rest the camera offers". | Feed `listed` and range agreement from W-CTRL-LIST's per-camera `missing`/`mf_vs_ds_differences` (ctx results or the JSON). Optionally add set+readback for every other manual control (brightness, contrast, zoom, pan/tilt…). | Re-rate only (+ W-CTRL-EFFECT if controls are added) | low |
| B7 | windows/tests/w_ctrl_list.py:196-197 | Emits `v["G-CTRL"]` = untested, which summary.md shows as a "G-CTRL / all / untested" row. | Drop it, or rename it to a non-goal key such as `ctrl_listing_counts`. | Regenerate summary.md only | cosmetic |
| B8 | common/rating.py:92-97; windows/tests/w_id.py:211-212 | Persistence that was not measured gives "partial", the label the plan reserves for "key changes on reboot/replug". w_id also ignores evidence it already has (`serial_keys_kept_over_reboot` [true] after the 09:26 boot) and the generic's same-port re-arrivals. | Return yes with a `provisional` flag (or a separate "yes-provisional" state) when criteria 1-2 pass and persistence is null. Set `reboot` true for serial cameras when `rebooted_since_earlier_run` is true and their keys held. | Re-rate W-ID from the JSON; the controlled A1 steps are still needed | low |
| B9 | windows/tests/w_id.py:224-225 | `G-ID_per_api` values are bare strings with no criteria or evidence, though summary.md links them as rated cells. | Store the full `rate_id` dict per API. | Re-rate only | cosmetic |
| B10 | windows/tests/w_policy.py:200-201 | Rotation `met` is True when no value is found, even though the storage location is undocumented and the searched keys do not exist. | Set `met` to None ("not found; location unknown") unless corroborated, e.g. by checking W-FMT for MF MJPG types. | Re-rate only | low |
| B11 | windows/tests/w_env.py:160-179 | Flags cover processes only. Registered virtual DS filters (NVIDIA Broadcast, OBS, SpoutCam, NDI), which load into every process that enumerates DS and shift OpenCV indices, are not flagged. | Add a flag from `ctx.discovery["virtual_devices"]` with the MF/DS index ranges they occupy. | W-ENV (instant) | low |

**Re-run list:** W-CTRL-EFFECT (after B1 and B3-B5; the Kiyo only after a replug and before streaming tests), W-KIYO (after B2). W-ID, W-POLICY, W-CTRL-LIST and summary.md only need re-rating or regeneration. The attended items that would turn the W-ID cells to yes are A1 (reboot, same-port replug, port move). For the C930e, a LogiTune-stopped repeat of the exposure test would tell whether the reset at stream start comes from the firmware or from LogiTune.

---

## Verifier notes

Adversarial check, 2026-11-06. Every number above was recomputed with Python from W-CTRL-EFFECT.json, W-CTRL-LIST.json (plus `W-CTRL-LIST/*_controls_*.json`), W-ID.json, W-ENV.json, W-POLICY.json, W-KIYO.json, discovery.json and suite_log.txt. Where the result JSON filters out a field, I also used the per-run `summary.json` and `frames.jsonl`/`frames.mjpeg` under the raw folder `W-CTRL-EFFECT/<cam>/<api>_<control>_r<k>/`. Luma was recomputed with `common.imgmetrics.luma_mean`, ROI 0.1-0.9. No camera was opened, and no suite or result file was changed.

### Cells

- **All 15 cell ratings and their deciding criteria are reproduced exactly** (`verdicts["G-CTRL|…"]`, `criteria[*].met`, `evidence.controls[*]`). Generic criterion 4 fails only through `after_start_ok`. Gain `before_start_ok` is True, because `effect_before_ok` is None when `effect_after_ok` is False (w_ctrl_effect.py:202, 426-427). This matches the analyst's knock-on reading.
- **Kiyo cells.** Section 1.1 calls these "artefact", but the structured output calls them "mixed". "Mixed" is the right call. The device failure is real; the label "untested" with the reason "no manual mode" is the harness artefact. Under the plan, the cell should be **no** with the reason "device not answering", or at least untested with the correct reason.
- **C930e mf.** The partial is real. But the white-balance pass in runs 1-2 rests on a harness artefact (state carried over; see V1 below), not on a marginal scene.
- **C922 yes.** Real. Criterion 1 is True only because it is hard-coded (B6). The WB and focus tests ran with gain left at 230 manual and exposure at −7 manual from earlier tests (V1). The rating still holds: luma ~100, not clipped.

### Findings: verdicts

| ID | Verdict | Note (measured unless marked) |
| --- | --- | --- |
| F1 | confirmed | counts 16/16/11/16, `missing_*` 0, `mf_vs_ds_diffs` 0, `iam_ks_disagree` [] on all 4; every unsupported id gave `iam_get_range` 0x80070490 (24 on C922/Kiyo/C930e, 29 on the generic) |
| F2 | confirmed | AE priority is 0..0 on IAM **and** KS BASICSUPPORT (`ks_basicsupport.min/max` 0), value 1 on C922/C930e and 0 on Kiyo. Not mentioned: the generic's gamma reads 22, which is off its 10..30 step-10 grid. The C930e's saturation was 53 at 13:20 (default 128), another non-default value besides the Kiyo's |
| F3 | confirmed | exposure 16.92-17.92, gain 2.683-2.712, WB 2.635-2.723, focus 29.9-31.1 (MF+DS) |
| F4 | weakened | MF 3/3 and DS 2/3 revert to −5, confirmed. But "re-apply after the first frame" was tested only at +1000 ms (30 frames, `frames_before_apply` 30). A set right after frame 1 is untested. The reset is also not deterministic: DS run 3 held −9, and in WB runs 1-2 a gain of 230 left over from earlier held through stream start. So the workaround is "re-apply ≥1 s after start" until a shorter delay is tested |
| F5 | confirmed | 26 → 18/15/14 at +1000 ms. Not mentioned: the values are not the default (0) and not the previous value (15, 230, 230 in runs 1-3 per raw `controls_before.before_value`). They look like a one-shot auto-exposure result at stream start (inferred). The C930e also reads gain 127 after a set of 128 that read back 128 |
| F6 | weakened | WB has no effect: confirmed (2800/4650/6500, ratio 0.991-1.004). Gain: because 2 reverts to 4 at start, the MF runs only compared gain 4 against 6 (segments 1-2 were both at 4). DS cannot show whether 2 held. Stated precisely: no luma change for gain 4→6 at exposure −2. The 1..7 range was not covered |
| F7 | confirmed | reverts to the default 4 even when the previous value was 6 (raw runs 2-3 `before_value` 6, then 4 at +1000 ms) |
| F8 | weakened | The last successful Kiyo command was 13:19:59 (W-CTRL-LIST read, log line 41). There were no Kiyo commands until 13:43:49, which was the Kiyo's **first stream attempt of the whole run** (line 506) and it failed. The Kiyo never streamed in this run. Onset lies between 13:20 and 13:43:49 (3 h 20 min to 3 h 44 min after the 09:59:24 arrival), so "3 h 44 min" is an upper bound. W-KIYO's 0/61 polls span 14:56-15:06, every one coded `get 0x80004002` (see B2) |
| F9 | confirmed (correction) | restored true on all 6 paths, no `first_attempt`. C930e gain 15 is the value restore itself wrote: `cam_orig` was read at 14:53 (gain 15, manual). The change from 8 (13:20) to 15 happened during the streaming tests in between. "Auto-exposure drives it" is an inference |
| F10 | **refuted** | Not a threshold effect. C930e MF WB runs 1-2 ran at luma **209** (near clipping), while run 3 and DS ran at 106-108: recomputed from frames.mjpeg. Gain was still 230 manual from the gain test, because w_ctrl_effect restores only once per path (V1). In run 3 the camera dropped the gain on its own at stream start. The 1.0531 ratio comes from the leftover state, not from the scene |
| F11 | confirmed (caveat) | 6/6 APIs 20/20, `distinct_orders` 1. Caveat: the two OpenCV rows come from `cv2_enumerate_cameras` 1.4.0 (helpers/enum_apis.py:100-124), not from OpenCV itself. `opencv_index_vs_enumeration_order.equal` compares two lists built from the same Windows enumeration, and no `VideoCapture(i)` was opened to confirm which device an index opens |
| F12 | confirmed | p50 2.10 / 4.57 / 1.98 / 2.77 / 154.4 / 212.6 / 119.6 ms. The OpenCV figures time cv2_enumerate_cameras |
| F13 | **partly refuted** | "Every index differs from 10-27" is wrong. The C922 is at **MF 4 / DS 0 both days** (`natural_evidence.earlier_api_order`). Only the generic (MF 5→6, DS 1→6) and the C930e (MF 6→7, DS 2→7) moved, partly because the Kiyo, excluded on 10-27, now sits at MF 5 / DS 1. The rest of F13 is confirmed |
| F14 | confirmed | C922 port /1 → 13.1.4 with key, instance and symlink the same. Generic 13.1.3 → 13.1.2, first install 14:58:37Z. C930e 13.1.4 → /7, first install 15:00:22Z |
| F15 | confirmed | `8&39DEC205&1&0000` has MetadataBufferSizeInKB0=5; the current `6&2206973F&0&0000` has null. W-ENV does not flag this (V3) |
| F16 | confirmed | `serial_keys_kept_over_reboot` [true], boot 14:26:00Z. The generic's instance `7&7DCC7CE&0&2` and symlink `8&232e60d4` are the same before and after its 19:44:44Z re-arrival |
| F17 | confirmed | Balanced; selective suspend 1/1; LPM 2/2; hub timeout 50; IOC 1/0; `HKLM…\Services\USB` null; Kiyo on 8086:1138 `behind_pcie_switch` true |
| F18 | confirmed | 8 sensor groups; DS bypass true ×4; DMFT values present only on the Kiyo, all empty strings; privacy Allow/Allow; EnableFrameServerMode null ×2. I did not re-verify the 13:17:09 republish time |
| F19 | confirmed | 9 × LogiTune.exe, agent and updater, 3 Logi Options+ processes, RazerAppEngine and the elevation service |
| F20 | confirmed | C930e: `current_configuration` 2, Logitech 1.2.75.34 on the usbccgp composite. The other three use configuration 1 and Microsoft 10.0.26100.9711. Cause still inferred |

### Harness bugs: verdicts

| Bug | Verdict | Note |
| --- | --- | --- |
| B1 | confirmed | Mechanism verified. In the KS fallback, wincam.cpp:1198-1201 marks the control supported on a successful BASICSUPPORT, but `caps` is set only by a successful KS GET (:1151-1162). `capkit.control_table` lives at **windows/capkit.py**:236-242, not under helpers/. `manual_capable` is at w_ctrl_effect.py:89-90, and the skip is at :341-343. `wincam controls --read-only` also returns rc 0 when every GET fails (log line 1490), so `get_controls` cannot see the failure. To make the path **no**, also pass `can_set_any=False` to `rate_ctrl` (rating.py:194-196); with an empty `rc` the code returns untested at :431 |
| B2 | confirmed | `CtlRead` HRESULT defaults are E_NOINTERFACE (wincam.cpp:1087). `ctl_json` emits them unconditionally (:1243-1246), and `w_kiyo` reads only `iam_get` (w_kiyo.py:97-98, 106). W-KIYO's `codes` is exactly `get 0x80004002` 61/61 per API. The real KS GET code is unknown; 0x8007001F is a plausible inference from W-CYC |
| B3 | confirmed, fix needs care | A strict `==` would misfire on firmware rounding (the C930e reports 127 after a set of 128). Compare with a tolerance of one step (or ±1), and record `value_at_first_frame` for every control set before start, not only the one under test |
| B4 | confirmed | C930e gain runs 2-3: raw `controls_before` shows exposure −5 before the set to −7, and the first segment's luma is 107-121 (MF and DS), the −5 level |
| B5 | confirmed | design gap rather than a code bug; the plan only asks for "persistence across close/reopen" |
| B6 | confirmed | w_ctrl_effect.py:421 |
| B7 | confirmed | w_ctrl_list.py:196-197 |
| B8 | **weakened** | The labelling complaint is fair, but both parts of the fix are wrong. (a) Returning yes while persistence is unmeasured contradicts the plan's yes definition. Better: keep partial, or add a distinct "provisional" state, and have summary.md print `rate_id`'s note. (b) Setting `reboot=True` from `serial_keys_kept_over_reboot` over-claims. Only the serial C922 has reboot evidence. The generic and C930e got new devnodes after the boot, and the Kiyo was not in the 10-27 runs, so the port-keyed cameras have none |
| B9 | confirmed | w_id.py:224-225 |
| B10 | confirmed; missed sibling | w_policy.py:200-201. The worse bug is next to it at **w_policy.py:202-203**: `"met": True if not multi else None`. A multi-app value that is found gives None, and `bad` counts only False (:212), so an active multi-app mode would still rate **yes**. Fix: `met=False` when a value meaning "on" is found (None if its meaning is unknown), and treat None as not-yes |
| B11 | confirmed | low |

### Missed by the analyst

- **V1 (harness bug, medium).** Control state carries over between control tests. `restore()` runs only in the `finally` that encloses the whole `for name in CONTROLS` loop (w_ctrl_effect.py:339-406). The gain test leaves gain at 230 manual and exposure fixed manual, and the WB and focus tests then run in that state.
  - Measured effect: C930e MF WB runs 1-2 at luma 209 against 106-108 otherwise, which produced the marginal 1.0531 (F10).
  - Fix: restore the touched controls (or set them to defaults) after each control's runs, and record the full control state at each run's start.
  - Re-run: W-CTRL-EFFECT (C930e WB at least; the C922 and generic for clean data).
- **V2 (harness bug, medium).** w_policy.py:202-203: the multi-app criterion is None when a value is found (see B10).
- **V3 (harness bug, low).** W-ENV gathers `tier1_metadata.all_instances_with_keys` (w_env.py:104, 156-157) but raises no flag when an old instance of a present camera carries MetadataBufferSizeInKB0 and the current one does not. That is exactly the silent drop of the C930e to tier 0 (F15). Fix: add that flag in w_env.py:160-179. Re-run: W-ENV only.
- **V4 (camera, measured).** The C930e changes values at stream start without any set from the harness. In MF WB run 3, the leftover gain of 230 dropped (luma 209 → 108); in runs 1-2 it held. Together with DS exposure run 3 holding, this shows the reset fires on some stream starts but not all. A LogiTune-free run is needed before blaming the firmware.
- **V5 (context).** The Kiyo never delivered a frame in this run (F8). Moving W-CTRL-EFFECT earlier only helps if the Kiyo's controls were still alive before its first stream open, which is unknown: the gap from 13:20 to 13:43 had no Kiyo commands.
- **V6 (G-ID caveat).** The OpenCV G-ID cells are only as good as cv2_enumerate_cameras' claim that its order equals what `VideoCapture(index)` opens (F11). A one-frame open per index under the camera lock would close this gap.
