# Setting camera focus for motion capture: options and recommendation

Written 2026-11-11. Desk research plus re-analysis of stored result files. No camera was opened, no setting was changed.

**Rules this is built on:**
- During a mocap session the cameras must not change exposure or focus by themselves. Autofocus (AF), auto-exposure and auto gain are off (plan §1, `research/CAPTURE_AND_RECORDING_PLAN.md`).
- **New direction (Dom, 2026-11-11, relayed during this study):** the product has **no manual focus control**. Focus is set automatically. The idea to evaluate is to use the ChArUco board, held where the subject will stand during calibration, as the focus target.

**Labels:**
- **[M]** measured: a result file in this repo, linked, or a re-analysis of the stored frames named in §3.4.
- **[C]** code, file:line.
- **[S]** primary source, with URL; all accessed 2026-11-11.
- **[W]** forum or user report.
- **[I]** inferred.
- **[NV]** not verified.

Measured data is from one Windows 11 machine (Gerald), suite run `suite_20261111T040003Z`, on a desk scene (distance not recorded). Nothing was measured at mocap distance, with a ChArUco board, on Linux or on macOS.

---

## Recommendation

1. **skellycam sets focus itself with a host-driven contrast autofocus aimed at the ChArUco board (option B, §7.2).** The camera's AF stays off the whole time. skellycam steps the absolute focus value (coarse, then fine) and scores sharpness only inside the detected board. It then sets the best value with the manual flag. The user presses no focus control; it runs as one step of calibration setup. It does not depend on the camera's AF or on reading back where AF left the lens. On our cameras both of those fail [M] (§3).
2. **Do not rely on "let the camera's AF settle, then turn AF off and keep its value" (option A), or on a hybrid seeded by it (option C).**
   - The C922 reads back a stale value while streaming, and the Kiyo Pro's readback never follows its AF [M]. So "read the value, then set it with the manual flag" would move the lens to the wrong place on two of our three focusing cameras.
   - The C930e reads back correctly, but its AF settled on a focus 4.4× less sharp in the frame centre than a fixed value it was given [M].
   - UVC 1.0 has no AF region control, so camera AF cannot be aimed at the board [S].
   - The hybrid is worth keeping only as a later speed-up for cameras on a tested allow-list (§7.3).
3. **Workflow:** exposure step (AE and auto gain off, values pinned) → board held still at the subject position → host autofocus on all cameras in parallel → lock → ChArUco calibration → record. **Any change of focus value means recalibrating.** The locked value is saved with the calibration, keyed by camera identity, and restored and verified on every open (§8).
4. **Special cases:**
   - **Fixed-focus cameras** (the generic 4c4a:4a55 has no focus control [M]) are skipped and shown as "fixed focus".
   - **Kiyo Pro:** option B never turns its AF on, so its AF search never happens. Two steps are needed:
     - Wait about 1.5 s after each stream start before scoring or calibrating. Its lens reaches the commanded value only about 1 s after the first frame [M].
     - Run a full fine sweep in TP1 first, so the coarse step can be set. Its sharpness peak is narrow and has not been mapped [M/I].
5. **Estimated time** (from measured settle times, §7.2):
   - C922 and C930e: about 7–12 s each.
   - Kiyo Pro: about 15–30 s.
   - All cameras run in parallel, so the step takes as long as the slowest camera, plus about 2 s.
   - These are estimates. TP1 measures them (tests F1–F3, §9).

**Answer to the owner's question:** skellycam today sets focus **not at all**, on every branch the plan builds on. It neither assumes AF has focused nor turns AF off (§2). The product needs a focus step. Given the new direction, that step is an automatic "focus on the board" step inside calibration, not a button beside a manual slider, and it does not use the camera's AF.

---

## 1. What skellycam and freemocap do today

| Where | Focus handling | Evidence |
|---|---|---|
| `dom/research` @ `00f28fe1` (= the base for phase 1) | **None.** No focus or autofocus field in `CameraConfig`, no `CAP_PROP_FOCUS` / `CAP_PROP_AUTOFOCUS` call, no UI control. The camera keeps whatever mode it powered up in. Logitech and Razer report AF on as found [M] | [C] `git grep` over `skellycam/` and `skellycam-ui/src` finds only UI keyboard-focus code; config fields `skellycam/core/camera/config/camera_config.py:65-120`; controls applied are exposure only, `skellycam/core/camera/opencv/opencv_helpers/opencv_apply_config.py:36-47`. As found: `original.flags = ["auto"]` for focus on all three focusing cameras ([W-CTRL-EFFECT.json](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-EFFECT.json)) |
| `upstream/sfn26` @ `19ea17e7` (2026-11-10) | None | [C] same `git grep` with `git grep … upstream/sfn26` |
| `dom/openpnp-capture-mf` @ `d55f7690` (2026-05-19; the plan does not use the openpnp branches, §5) | AF turned off on every open. Focus is then set to the **device default** when the config holds the sentinel −1, which is the initial value. The UI has an "Autofocus" checkbox and a manual slider | [C] `openpnp_apply_config.py:30-52`, `camera_config.py:27-28,114-121`, `CameraConfigFocus.tsx:46-80` (tooltip line 49: "Autofocus is turned off whenever a camera is opened"). This branch moves the lens to the default (0 on all three of our focusing cameras [M], [W-CTRL-LIST.json](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-LIST.json) `ranges.cc.focus.default`), not to where AF had put it [I] |
| Recording metadata | `recording_info` JSON stores each camera's `CameraConfig`, so today it contains no focus field | [C] `skellycam/core/recorders/videos/recording_info.py:77-86` |
| freemocap @ `5632778a` | No focus handling in code. The user guide says "Focus: Manual, fixed on the capture volume" but gives no way to do it. The calibration TOML stores intrinsics but no camera settings. Each calibration is also saved as the "last successful calibration" | [C] `freemocap-docs/docs/guides/camera-setup.mdx:82,85`; `freemocap/core/tasks/calibration/shared/calibration_save.py:47-48`. Reuse of that file for later sessions is [I] from its name and was not traced |
| ChArUco detection | Not in skellycam. freemocap uses skellytracker. The default board is letter size, 5×3 squares of 54 mm | [C] no `aruco`/`charuco` in `skellycam/`; `freemocap/core/tasks/calibration/calibration_task_config.py:26`; skellytracker `charuco_board_definition.py:65-66` (in freemocap's `.venv`) |

---

## 2. Short answers to the questions

| # | Question | Answer |
|---|---|---|
| 1 | Per-camera behaviour | Table in §3.1. Only the C930e's readback follows its AF. Turning AF off *without* sending a value was never tested. The value is held through start and reopen by readback on all three. **By image, the Kiyo's lens lags about 1 s and the C930e's about 0.4 s after a reopen** [M] |
| 2 | Mechanisms | UVC: `CT_FOCUS_AUTO`, `CT_FOCUS_ABSOLUTE` (millimetres in the spec, arbitrary in practice), `CT_FOCUS_RELATIVE`, and `CT_FOCUS_SIMPLE` (1.5 only). The UVC spec has **no one-shot AF**. Windows has a one-shot (`AUTO|LOCK`) only through the extended focus property, which needs Microsoft's UVC 1.5 extension unit; our cameras lack it [M]. On Linux uvcvideo does not map one-shot; macOS AVFoundation has `.autoFocus` = one-shot then lock. §4 |
| 3 | Other tools | guvcview ships a host-side contrast AF (coarse/fine sweep, centre-weighted). Photogrammetry and eye-tracking guides say to focus at the working distance and then lock. OpenCap fixes focus in its app. §5 |
| 4 | Calibration impact | No published webcam numbers were found. A thin-lens estimate gives about 0.2 % focal-length change between focus at 2 m and at infinity, roughly 1 px at a 720p image edge [I]. So **focus → lock → calibrate → record, and any refocus means recalibrate.** Today neither skellycam nor freemocap records focus [C]. §6 |
| 5 | Options | B (host contrast AF on the board) plus D (store, restore and verify). A and C are not recommended; the manual slider (E) is dropped. §7 |
| 6 | Tests | F1–F11 in §9 |

---

## 3. What our four cameras do (measured)

### 3.1 Per-camera summary

All four cameras are UVC 1.00 [M] ([W-CTRL-LIST.json](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-LIST.json) `descriptor.bcdUVC`). MF and DirectShow list identical focus ranges [M] (same file, `per_control.cc.focus.ranges_equal_mf_ds`).

| | Razer Kiyo Pro 1532:0e05 | Logitech C930e 046d:0843 | Logitech C922 046d:085c | Generic 4c4a:4a55 |
|---|---|---|---|---|
| Focus controllable | Yes (`focus_absolute`, `focus_auto`) | Yes | Yes | **No**: the camera terminal has AE mode and exposure only (`bmControls 0x00000a`). Fixed focus |
| Range / step / default | 0–600 / 1 / 0 | 0–255 / 5 / 0 | 0–250 / 5 / 0 | – |
| Focus relative / simple | Not offered (`bmControls 0x020a2e` has no D6 or D19) | Not offered | Not offered | – |
| Visible effect with AF off | Yes. Sharpness max/min ×55.7 MF, ×11.4 DS, but see §3.3 | Yes, ×68–81 | Yes, ×286–292 | – |
| **Readback while AF is on follows the lens** | **No.** Never changed by itself: 1 in every MF read across 9 AF-on streams, 600 on DS and in W-AUTO (left from the last set). After a manual 0 it reads 0 while the AF image is 400× sharper than the manual-0 image | **Yes.** In-stream: reads 0 before each toggle, after 255 was just written with the auto flag. The AF image equals the manual-0 image (sharpness 0.0025 vs 0.00255). Closed-camera reads after AF streams vary (0, 30, 55, 65) | **Not while streaming.** It read 250 after more than 5 s of AF (the last value written) and 0 after each toggle, while the AF image was as sharp as a value near 30 should give. **With the camera closed** after AF streams it read 30 every time, matching the image [M/I] | – |
| AF-off keeps the lens where AF left it | **Not measured** on any camera. Every AF→manual switch in W-AUTO and W-CTRL-EFFECT sent an explicit value | same | same | – |
| Value held through stream start | Readback: yes, 3/3 per path. **Image: no for about 1 s.** For the first ~1 s after the first frame the lens sits at an unrelated position (sharpness 0.014) whatever value was set, then moves to the set value (§3.3) | Readback: yes. Image: a value set before start was in place from frame 0 (r0) | Yes, readback and image, from frame 0 | – |
| Kept across close/reopen | Readback: yes (600 held). **Image: the lens reached 600 only ~1 s into the new stream.** The harness rated `persisted = false` on both paths for this reason | Yes, readback and image. In the reopened stream the lens started near the 0 position and reached 255 within ~0.4 s | Yes, readback and image, from frame 0 | – |
| Camera AF quality on this scene | Converges in ~1.5–3 s with one dip (re-search), then steady at ~0.11. Better than any of the 5 sweep points (best 0.0029) | **Settles on a soft focus.** AF 0.0025 vs 0.011 at manual 65 (×4.4). A transient of 0.03–0.037 passes during each AF search | Good and fast: 0.090–0.10, ~1.8× the best sweep point (0.048 at 0) | – |
| AF recovery to ≥ 80 % of the AF baseline (W-AUTO) | Inconclusive in the harness (baseline CV 0.35 / 0.45, caused by the dip). OpenCV DirectShow: 2.2–2.4 s | 390–448 ms MF, 452–490 ms DS | 163–208 ms MF, 211–282 ms DS | – |
| Serial number (identity key) | none → port path | none → port path | `C922SN01` | none → port path |

Sources for the table [M]:
- Range, flags and descriptors: [W-CTRL-LIST.json](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-LIST.json) (`measurements.cameras[*].ranges.cc.focus`, `descriptor`, `cameras[*].serial`).
- Effect, held-through-start and persistence: [W-CTRL-EFFECT.json](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-EFFECT.json) (`paths.{mf,ds}.controls.focus.runs[*]`, `.persistence`, `runs[*].state_at_start.focus` for the closed-camera reads).
- AF readbacks, AF images and recovery: [W-AUTO.json](../results/windows/Gerald/suite_20261111T040003Z/W-AUTO.json) (`paths.mf.baseline.auto_values_read.focus`, `controls.focus.runs[*].analysis.toggles[*].manual.before_value`, `baseline.median`) and the per-frame timelines in [W-AUTO/](../results/windows/Gerald/suite_20261111T040003Z/W-AUTO/) `*_mf.json`.
- OpenCV recovery: [W-OCV-CTRL.json](../results/windows/Gerald/suite_20261111T040003Z/W-OCV-CTRL.json).

Caveat on the scene: W-CTRL-EFFECT (23:41) and W-AUTO (00:06) ran about 25 minutes apart on the same rig. The "AF quality" row compares sharpness across them, which assumes the scene and light did not change [I]. The C922's manual-0 value agrees between the two runs (0.048 vs 0.052), which supports that assumption.

### 3.2 What this means for "let AF settle, then lock its value"

- The UVC spec promises exactly this behaviour: "read requests will reflect the automatically set value", and on leaving auto "the control shall remain at the value that was in effect just before the transition" [S] (UVC 1.5 §2.3.3, quoted in §4.1).
- Our cameras do not all keep that promise. On Windows the only way to switch AF off through `IAMCameraControl` is `Set(value, Manual)`, which also sends a value [S] (§4.2).
  - **Kiyo:** the value it reports is stale. Sending it back would move the lens away from AF's position [M/I].
  - **C922:** same, as long as the read happens while streaming [M/I]. A read with the camera closed looked right (30). Using that would mean stop, read, reopen, which costs a stream start and is unverified as a method [I].
  - **C930e:** the readback is right, but its AF chose a soft focus for the frame centre [M].
- Whether Windows' UVC driver sends `SET_CUR(FOCUS_ABSOLUTE)` when only the flag changes is not documented [NV]. TP1 F5 tests it.

### 3.3 New findings from re-reading the stored frames

Method: the per-frame normalised Laplacian sharpness was recomputed with the suite's formula (`suite/common/imgmetrics.py:70-80`, centre 50 %). Frames came from the raw capture folders that W-CTRL-EFFECT left in `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_20261111T040003Z\W-CTRL-EFFECT\<camera>\mf_focus_r{0,1,2}` and `mf_focus_persist` (`frames.jsonl` + `frames.mjpeg`, every 3rd frame saved). The scripts ran from the session scratchpad. Copies are kept in [`tools/focus_rescore/`](../tools/focus_rescore/) (`sharp_timeline.py`, `settle.py`; 2026-11-11). They only read files, and their raw-frame paths point at the local `skellycam-raw` folder.

1. **The Kiyo ignores the commanded focus for about 1 s after a stream starts** [M].
   - r0 (focus 0 set before start, manual flag):
     - frames 0–800 ms: sharpness 0.007–0.014;
     - at 992 ms: drop to 0.0007, then 0.0016, the level for the next scheduled value (150).
   - Persistence run (600 held, nothing set except the 0 ms manual re-set):
     - 0.008–0.018 for 0–897 ms;
     - from 992 ms: 0.0007 → 0.0002, the 600 level.
   - So the "0 is sharpest" result for the Kiyo in W-CTRL-EFFECT (`best_value 0`) measures this start-up lens position, not focus 0. In W-AUTO a manual 0 set while streaming gives 0.00024, one of the softest values [M].
   - Corrected Kiyo sweep, scene of 23:41–00:06:

     | Focus value | 0 | 150 | 300 | 450 | 600 |
     |---|---|---|---|---|---|
     | Sharpness | ~0.0002 | 0.0016 | 0.0029 | 0.0003 | 0.0002 |

     AF reached ~0.11, so the true peak was not sampled and is narrow compared with a 150-step spacing [I].
   - **Correction to `windows_results_20261110.md` §6**, which says the Kiyo's focus "all persist": the readback persisted, but the JSON's `persistence.persisted` is `false` on both paths, for the reason above. Its ×55.7 MF ratio is also mostly the start-up position against value 600.
2. **The C930e's lens restarts near its 0 position on a reopen and needs ~0.4 s to reach the stored value** [M]. Persistence run: 0.0026 at frame 0, 0.0042 at 207 ms, then the 255 level (0.00014–0.00023) from 400 ms.
3. **The C922 is at the stored value from frame 0** [M]. Its persistence run is flat at 0.00017–0.00019.
4. **Settle time after an in-stream focus step** (large steps of ~25 % of the range; time from the set call to the first saved frame within 15 % of the new level; resolution ~100 ms because only every 3rd frame was saved) [M]:

   | Camera | Steps timed | Median | Max |
   |---|---|---|---|
   | C922 | 6 | 196 ms | 199 ms |
   | C930e | 9 | 207 ms | 408 ms |
   | Kiyo Pro | 12 | 322 ms | 764 ms |

   These include capture latency. Small steps are probably faster [I]: guvcview assumes 1.4 ms per focus unit [S] (§5).
5. **AF on the Kiyo does not hunt continuously on a static scene.** It searches, dips once and then holds steady for the rest of each 5–6 s window. Example: after auto-on at 9.0 s the timeline goes 0.054 (10.2 s), 0.014 (10.7 s), 0.101 (11.2 s), then 0.106–0.112 until 14.9 s [M] ([W-AUTO/usbvideodevice_1532-0e05_4_mf.json](../results/windows/Gerald/suite_20261111T040003Z/W-AUTO/usbvideodevice_1532-0e05_4_mf.json)). That dip is the "unstable baseline" the harness reported. Any "wait until AF settles" logic for the Kiyo needs ≥ 4 s plus a stability window [I].

---

## 4. Mechanisms by platform

### 4.1 UVC (USB Video Class)
Source: UVC 1.5 class specification (USB-IF, *USB Device Class Definition for Video Devices*, rev 1.5, 2012-08-09), in the zip at https://www.usb.org/sites/default/files/USB_Video_Class_1_5.zip [S]. Our cameras declare UVC 1.0. The 1.0/1.1 text was not read, so how far the 1.5 wording matches 1.0 is [NV].

| Control (selector) | What the spec says |
|---|---|
| `CT_FOCUS_ABSOLUTE_CONTROL` (0x06) | "used to specify the distance to the optimally focused target. This value is expressed in millimeters." Setting it while Auto-Focus is enabled "shall result in a protocol STALL … 'Wrong state'" (§4.2.2.1.6). Our cameras use 0–250/255/600 with step 1–5 and default 0 [M], which are not millimetres |
| `CT_FOCUS_RELATIVE_CONTROL` (0x07) | Move near (1), stop (0) or toward infinity (0xFF) at a speed (§4.2.2.1.7). None of our cameras offer it [M] |
| `CT_FOCUS_AUTO_CONTROL` (0x08) | Boolean; 1 = the device adjusts Focus Absolute/Relative automatically (§4.2.2.1.9) |
| `CT_FOCUS_SIMPLE_CONTROL` (0x12, UVC 1.5) | Coarse range: full, macro (< 0.3 m), people (0.3–3 m), scene (3 m–∞) (§4.2.2.1.8). Not on our cameras [M] |
| General rule (§2.3.3) | "If the auto setting is supported and set to the on state, the device will provide automatic focus adjustment, and read requests will reflect the automatically set value … When leaving Auto-Focus mode … the control shall remain at the value that was in effect just before the transition." |
| One-shot AF | **None** in the camera terminal. UVC 1.5's Region of Interest control has an `bmAutoControls` "D3: Auto Focus" bit, which says which auto functions use the region; it is not a trigger. It is UVC 1.5 only [S] |

### 4.2 Windows
- **`IAMCameraControl` / `KSPROPERTY_CAMERACONTROL_FOCUS`.** Get and Set carry a value and a flag: `CameraControl_Flags_Auto = 0x1` ("controlled automatically") or `_Manual = 0x2` [S] (https://learn.microsoft.com/en-us/windows/win32/api/strmif/ne-strmif-cameracontrolflags).
  - The focus value "is expressed in millimeters", with the caution that "some drivers define a custom range of focus values and custom step values that might not be based on typical units" [S] (https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/ksproperty-cameracontrol-focus).
  - Our suite sets focus this way through the MF source and through DirectShow [M].
- **`KSPROPERTY_CAMERACONTROL_EXTENDED_FOCUSMODE`** (Windows 8.1+) defines a real one-shot: AUTO combined with LOCK means the driver "will converge on auto-focus and lock the focus to that converged point and then trigger the completion event". It also has range flags (macro / normal / full / infinity / hyperfocal) [S] (https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/ksproperty-cameracontrol-extended-focusmode).
  - For UVC cameras this is reached through Microsoft's UVC 1.5 extension unit, `MSXU_CONTROL_FOCUS`, a cancelable control [S] (https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/uvc-extensions-1-5).
  - **None of our cameras has that extension unit.** Their extension-unit GUIDs are vendor ones [M] ([W-CTRL-LIST.json](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-LIST.json) `descriptor.extension_units[*].guidExtensionCode`). So no one-shot AF is available on Windows for our cameras [I].
  - The same extension's per-frame metadata could carry `LensPosition` [S]; not available here.

### 4.3 Linux (V4L2, uvcvideo)
- Kernel docs [S] (https://docs.kernel.org/userspace-api/media/v4l/ext-ctrls-camera.html):
  - `V4L2_CID_FOCUS_AUTO` "Enables continuous automatic focus adjustments. The effect of manual focus adjustments while this feature is enabled is undefined, drivers should ignore such requests."
  - `V4L2_CID_AUTO_FOCUS_START` "Starts single auto focus process", with `_STOP` and `_STATUS` (IDLE/BUSY/REACHED/FAILED).
  - `V4L2_CID_3A_LOCK` has a focus lock bit.
- uvcvideo source [S] (`drivers/media/usb/uvc/uvc_ctrl.c`, https://raw.githubusercontent.com/torvalds/linux/master/drivers/media/usb/uvc/uvc_ctrl.c):
  - `FOCUS_ABSOLUTE` is mapped with master `FOCUS_AUTO` (`master_manual = 0`). Setting it while AF is on returns `-EACCES`, and it shows as `INACTIVE`.
  - It carries the `AUTO_UPDATE` flag, so reads go to the device rather than a cache [I from the flag's meaning], and the `RESTORE` flag (re-applied on resume).
  - **`AUTO_FOCUS_START` is not mapped, `FOCUS_RELATIVE` has no mapping, and `FOCUS_SIMPLE` is absent.** So on Linux, too, a UVC webcam has no one-shot AF; only continuous AF on/off and absolute focus [S].
- On Linux, `FOCUS_AUTO = 0` can be sent alone, without a value, so "AF off keeps the lens" is testable there as the spec intends [I].

### 4.4 macOS
- AVFoundation `AVCaptureDevice.FocusMode` on macOS 10.7+ [S]:
  - `.locked`: "A mode that locks device focus" (https://developer.apple.com/documentation/avfoundation/avcapturedevice/focusmode-swift.enum/locked);
  - `.autoFocus`: "automatically adjusts the focus one time, and then locks focus" (…/autofocus);
  - `.continuousAutoFocus`;
  - `isAdjustingFocus` is observable (…/isadjustingfocus).
- macOS has no `lensPosition` setter [S] (per `macos_uvc_controls_review.md` R8). Whether Apple's UVC driver offers `.autoFocus` / `.locked` for external UVC webcams, and how it maps them to UVC requests, is [NV].
- Absolute focus on macOS goes through CoreMediaIO feature controls (`fcus` / `ucfa`) or endpoint-0 UVC requests, per `macos_uvc_controls_review.md` (R1, CE-CMIO-W). No hardware run yet.
- Option B needs only "AF off + write absolute focus". That makes it the most portable of the options [I].

---

## 5. What other tools and workflows do

| Tool / source | What it does about focus | Label |
|---|---|---|
| **guvcview** (Linux) | Ships a **host-side contrast autofocus**, `gview_v4l2core/soft_autofocus.c` ("autofocus - using dct"). It scores a centre-weighted region (8×8 DCT, AC energy). It does a coarse sweep at `2·(range/32)` steps, then a fine sweep of ±half a step around the best, then tracks. It waits `focus_wait` frames per move, based on "1.4 ms focus time - every 1 step" | [S] https://sourceforge.net/p/guvcview/git-master/ci/master/tree/gview_v4l2core/soft_autofocus.c |
| libv4l2 discussion (2017) | Software AF in user space was proposed, sweeping focus and scoring sharpness, on the grounds that the kernel is the wrong place | [W] lkml thread "support autofocus / autogain in libv4l2", https://lkml.iu.edu/hypermail/linux/kernel/1704.3/00228.html (not read in full) |
| OBS | Uses the driver's DirectShow property page for AF on/off. A user reports OBS switching AF back on after vendor software turned it off | [W] https://obsproject.com/forum/threads/is-there-a-way-to-turn-off-autofocus-using-obs.196633/ (title and summary only) |
| Logitech software (Logi Tune / G HUB) | AF toggle and manual focus slider; users disable AF there for 3D-printer webcams | [W] e.g. https://community.octoprint.org/t/disabling-auto-focus-on-logitech-c922-webcam/20564 (summary only). Logi Tune and Razer Synapse are installed on Gerald (study notes); whether they re-apply settings when a camera appears is [NV] |
| Pupil Labs (Pupil Capture) | "Make sure that the world camera is in focus for the distance at which you want to calibrate" | [S] https://docs.pupil-labs.com/core/software/pupil-capture/ |
| Agisoft Metashape (photogrammetry) | Calibration-board images "should be taken at the same distance from the camera as the planned distance to the object"; fixed lenses preferred | [S, via search summary] Agisoft knowledge base and manual 1.8 (https://www.agisoft.com/pdf/metashape_1_8_en.pdf), not read in full |
| Photogrammetry guides | "Use autofocus to set the focus distance and then switch to manual focus"; keep focus and zoom the same | [W] https://scholarslab.lib.virginia.edu/blog/documentation-photogrammetry/ (via search summary) |
| OpenCap | Developers say autofocus and zoom are fixed per camera in the app, because zoom changes the intrinsics | [W] SimTK forum, https://simtk.org/plugins/phpBB/viewtopic.php?p=51880 (via search summary) |
| Luxonis (OAK, autofocus modules) | Staff: intrinsics change with lens position; the factory calibration's lens position is stored in EEPROM; calibrate at a fixed manual lens position | [W] https://discuss.luxonis.com/d/5002-camera-not-focussing-correctly (via search summary) |
| FreeMoCap docs | "Focus: Manual, fixed on the capture volume" (no mechanism) | [C] `freemocap-docs/docs/guides/camera-setup.mdx:82` |
| Anipose, Theia | Nothing on webcam focus found in this search | – |

The pattern is the same everywhere: focus at the working distance, lock it, calibrate at that focus. guvcview shows a host-side contrast sweep is practical on UVC webcams.

---

## 6. Calibration impact

- **Why it matters.** Moving the lens group changes the image distance, so the effective focal length (fx, fy in pixels), and with it the distortion, changes with focus. Ricolfe-Viala and Esparza (2024) argue that "Real cameras change the focal length slightly to obtain sharp objects in the image", so a constant-focal-length pin-hole model skews calibration [S] (arXiv:2402.04686, https://arxiv.org/abs/2402.04686; magnitude not in the abstract). The InFlux benchmark maps lens focus to intrinsics for that reason [S] (arXiv:2510.23589, via search summary).
- **Webcam magnitude: no published measurement found.** A MATLAB Answers thread reports a C922 giving different focal lengths in two calibrations, with AF suspected [W] (https://au.mathworks.com/matlabcentral/answers/468057-change-in-intrinsic-parameters; no numbers).
- **Thin-lens estimate** [I]. Assumptions: f ≈ 3.7 mm, unit focusing, fx ≈ 1000 px at 720p.
  - The image distance is v = f·d/(d−f), so the relative change in effective focal length between focus at d and at infinity is about f/d.
  - 2 m vs infinity: ~0.19 %. fx changes by ~1.9 px, and a point 640 px from the centre moves ~1.2 px.
  - 2 m vs 3 m: ~0.06 %, about 0.4 px at the edge.
  - 1 m vs 3 m: ~0.25 %, about 1.6 px.
  - These are similar to or larger than a good ChArUco reprojection error, so a refocus after calibration matters. Hunting AF swings the lens much further than these examples.
  - TP1 F8 measures this on our cameras.
- **Depth of field** [I]. With f ≈ 3.7 mm, f/2 and a 3 µm circle of confusion, the hyperfocal distance is about 2.3 m. Focus at the subject position (2–4 m) leaves the whole volume roughly sharp. So a precise peak matters less for sharpness than for **keeping one fixed value** that the calibration was made at.
- **Gravity.** A voice-coil lens can shift when the camera is tilted, because gravity along the optical axis displaces the lens against its springs [S, patent] (e.g. US 10,473,884 and related VCM patents, via search summary). A stored value is therefore valid for the same mounting angle. Remounting a camera means recalibrating anyway.
- **Workflow order:** exposure locked → board at subject position → autofocus → lock → calibrate → record. Any change of the focus value, including a new autofocus, invalidates the intrinsics and needs a new calibration.
- **Recorded today:** nothing. skellycam's `recording_info` has no focus field [C], and freemocap's calibration TOML stores no camera settings [C]. freemocap also saves each calibration as the "last successful calibration" (`calibration_save.py:47`), so a refocus between sessions would silently pair new focus with old intrinsics if that file is reused [I].

---

## 7. Options

### 7.1 Option A: camera AF settles, then AF off and lock its value

**Product flow:** enable AF with the board in view, wait for it to settle, read the value, `Set(value, Manual)`, verify on the image.

| For | Against |
|---|---|
| Simple; the spec says it should work (§4.1) | **Readback fails on 2 of 3 focusing cameras** (Kiyo never, C922 while streaming) [M], so the "lock" would move the lens elsewhere |
| Fast on the C922 (~0.2 s) and C930e (~0.4 s) [M] | **No way to aim camera AF at the board**: UVC 1.0 has no region of interest [S]. Camera AF picks its own target. The C930e settled 4.4× softer in the frame centre than a fixed value allowed [M] |
| | The Kiyo needs ≥ 4 s including a re-search [M] |
| | Turns an auto mode on during setup (allowed by the rule, which covers the session, but it adds a state to verify) |

**Verdict:** not recommended. At most a diagnostic in TP1 (F4).

### 7.2 Option B: host-driven contrast autofocus on the ChArUco board (recommended)

**Product flow (per camera, all cameras in parallel):**
1. Preconditions:
   - the exposure step is done (AE and auto gain off, exposure and gain pinned), so brightness does not change the score;
   - the stream has run ≥ 1.5 s (the Kiyo's start-up lag [M]);
   - AF off is set and verified by readback.
2. **Find the board.** Detect ChArUco (OpenCV `aruco`; skellycam already depends on `opencv-contrib-python` [C]). If it is not detected at the current value, run the coarse sweep scoring the centre-weighted whole frame (as guvcview does) until the board is detected. If it is never detected, stop with "board not found".
3. **Coarse sweep** over the whole range. At each value: set with the manual flag → wait the camera's settle time (table below) → score the median of 3 frames.
4. **Fine sweep** of ±1 coarse step around the best value, at the fine step.
5. **Pick the value:** the middle of the run of values whose score is ≥ 97 % of the maximum, so that a flat top gives a repeatable choice [I].
6. **Lock.** Approach the chosen value from the same direction as the fine sweep (lens hysteresis is likely [I]), set it, re-score, and require ≥ 95 % of the sweep maximum. Read back the value and the manual flag.
7. **Save** (camera key → value; §8) and hand over to calibration.

**Score** (inside the board's convex hull, from detected marker corners):
- primary: normalised Laplacian variance (the suite's metric) or Tenengrad;
- secondary: number of ChArUco corners found and the edge width (10–90 % rise) across square edges, which depends less on board pose [I].

**Frame guards:**
- reject frames where the board moved more than ~2 px between consecutive frames (hand sway);
- re-score the top 3 candidates at the end, against a lucky frame.

**Time estimate** [I, using the measured settle times in §3.3]:

| Camera | Range / step | Coarse | Fine | Lock + verify | Moves | Wait per move | Estimate |
|---|---|---|---|---|---|---|---|
| C922 | 0–250 / 5 | every 20 → 13 | ±20 at 5 → 8 | 2 | 23 | 0.2 s settle + 0.1 s scoring = 0.3 s (0.4 s with margin) | **7–9 s** |
| C930e | 0–255 / 5 | every 20 → 13 | ±20 at 5 → 8 | 2 | 23 | 0.41 s max + 0.1 s = 0.5 s | **~12 s** |
| Kiyo Pro | 0–600 / 1 | every 40 → 16, then ±40 at 10 → 8 | ±10 at 2 → 10 | 2 | 36 | 0.32 s median to 0.76 s max + 0.1 s | **15–31 s** |
| Generic | – | – | – | – | – | – | skipped (fixed focus) |

- Parallel run: the total is the slowest camera plus stream start and board detection, about **20–35 s** with a Kiyo, **~15 s** without.
- Coarse spacing check, C922: sharpness halves over about 30 units near the peak (AF ~0.095 vs manual 0 → 0.052; manual 60 → 0.0016) [M/I], so a 20-unit coarse step always lands within 10 units of the peak.
- The Kiyo's peak width is unknown (§3.3). TP1 F1 must map it before the coarse step is fixed.
- Settling may be shorter for small steps, which would shorten the fine phase [I].

| For | Against / risks, with mitigation |
|---|---|
| Camera AF never runs. **No Kiyo hunting**, no dependence on AF readback; the value is the one skellycam wrote | Slower than camera AF: 7–30 s per camera, in parallel |
| **Aims at the board, which stands where the subject will be**, so it focuses at the subject distance, not the background | **Board too small or far.** Letter 5×3 board, 54 mm squares, at 3 m with a ~70° horizontal FOV at 1280 px: about 17 px per square and ~12 px markers [I]. OpenCV's default `minMarkerPerimeterRate` is 0.03 (38 px perimeter at 1280 px wide) [C] (OpenCV 4.12.0.88 `DetectorParameters()` read locally). At ~4 m the markers fall under that limit [I]. Mitigation: a bigger board for large volumes; whole-frame fallback; report "board too small" |
| Same code on Windows, Linux and macOS; needs only "AF off + absolute focus" (§4) | **Board motion.** A hand-held board sways, which moves the ROI and adds motion blur. Mitigation: ask the user to hold it still for ~15–30 s, or rest it on a stand; median of 3 frames; motion rejection; re-score at the end |
| Repeatable and checkable: the chosen value can be compared against the full-sweep best (F2) | **Steep curves** (the C922 drops ×30 over 60 units [M]). Mitigation: coarse step ≤ half the measured peak width per camera model (F1) |
| Matches existing practice (guvcview [S]) | The lens moves through its range while the user waits; frames from that time must not be calibration frames. Calibration starts only after the lock |
| | Many cameras: control writes are tiny, and detection runs on frames already decoded for the ring. CPU at 8–16 cameras is unmeasured [I] (TP3 can add it) |

### 7.3 Option C: hybrid (camera AF first, then host refine)
Camera AF with the board in view gives a start value; the host then runs only the fine phase (±2 coarse steps) and the lock.
- **Saves time only where the AF readback is right.** That is the C930e on Gerald [M]: about 0.5 s AF + 12 moves ≈ 6–7 s instead of 12 s.
- On the C922 and Kiyo the readback is wrong [M], so the refine would start from a wrong value. On the Kiyo the AF also takes ≥ 4 s [M].
- **Verdict:** not in the first version. Possibly later as a per-model speed-up, behind an allow-list filled from TP1 F4.

### 7.4 Option D: saved focus per camera, restored at session start
Part of the recommendation, not an alternative (§8). On its own it cannot set focus the first time, and it breaks when the camera key changes.

### 7.5 Option E: manual slider with a sharpness meter
**Dropped as a product feature** (Dom, 2026-11-11). The test harness keeps manual set and readback for TP1.

---

## 8. Product design around option B

| Topic | Design | Basis |
|---|---|---|
| Workflow | Calibration screen: (1) exposure step; (2) "Hold the board where the person will stand and keep it still"; (3) host autofocus on all cameras at once, with progress and a per-camera result (locked value, sharpness against the sweep peak, or the failure reason); (4) ChArUco calibration recording; (5) record sessions | §6, §7.2 |
| Lock | `Set(value, Manual)` on Windows, `FOCUS_AUTO=0` + `FOCUS_ABSOLUTE=value` on Linux, CMIO / endpoint 0 on macOS. Read back the value and the manual flag after the set, again after the first frame of every stream start, and again ≥ 1.5 s later (Kiyo) | [M] §3.3; plan 1.3 re-applies controls after the first frame |
| Storage | Per camera key: serial if the camera has one, else the USB port path (3 of our 4 cameras have no serial [M]). Store the focus value, the range/step/default (to catch a firmware change), board-ROI sharpness at lock, the sweep curve, the time, and the calibration ID. Write it into skellycam's per-camera settings and the `recording_info` `camera_configs` (new fields), and in phase 2 into freemocap's calibration TOML (no field today [C]) | §1, plan 2.6 |
| Session start | For each camera with a stored value: AF off and value set on every open (never trust what the device kept); check the readback; if the calibration's focus value differs from the camera's stored value, **block recording with "focus changed since calibration — recalibrate"** | [I] |
| Replug and reboot | Not measured. A camera that loses power probably comes back at its default (AF on, focus 0) [I]; the uvcvideo `RESTORE` flag covers only suspend/resume [S]. Since skellycam re-applies on every open, a replug on the **same port** restores the value. A replug on **another port** changes the key for serial-less cameras, so the camera counts as unknown: autofocus and recalibrate | F7 tests this |
| Focus-lost detection | Poll the focus readback and flags every ~1 s while streaming (cheap); log them into the recording sidecar; warn at once on any change, e.g. from Logi Tune, Razer Synapse, the Windows camera settings page or a second app. Optional image check: sharpness of static background regions against a reference taken at calibration time (warn only) [I] | F11 |
| Fixed-focus cameras | No `focus_absolute` in the descriptor (generic) → skip, show "fixed focus", store nothing | [M] §3.1 |
| Kiyo Pro | Never turn AF on. Discard frames for ≥ 1.5 s after each stream start for focus scoring and calibration. Use the Kiyo-specific coarse/fine steps from F1. Wedges are handled as in plan §3.3 TP1 | [M] §3.3 |
| Failure | On a timeout, a missing board or a lock-verify failure, keep the previous value, mark the camera "not focused", and do not start calibration for that camera | [I] |
| Other OS | Linux (V4L2) and macOS (CMIO) use the same algorithm; only the control calls differ. Untested | §4 |

---

## 9. Tests to add to TP1

All run with AE, auto gain and AF off unless the test says otherwise. Scene: a lit room, the ChArUco board (letter 5×3 and one larger board) on a stand at 1.5, 3 and 4.5 m, plus a hand-held variant. Cameras: Kiyo Pro, C922, C930e; the generic only for F9. Kiyo wedges handled as in TP1.

| ID | Test | Procedure | Measured | Pass |
|---|---|---|---|---|
| F1 | **Full focus map** | Per camera and distance: sweep every focus value (Kiyo every 2), low→high and high→low; after each move wait 1 s, then score 5 frames inside the board ROI and the centre 50 %. Also time the settle for single moves of 1, 5, 25 and 100 % of the range | Curve, peak value, peak width at 50 % and 90 %, hysteresis (peak up vs down), settle time against step size | Data test; sets each model's coarse/fine steps and settle waits |
| F2 | **Host autofocus: accuracy, repeatability, time** | The product algorithm, 10 runs per camera per distance, board on a stand; then 10 runs hand-held | Time to lock; chosen value vs the F1 peak; board-ROI sharpness at the chosen value / F1 maximum; spread of chosen values | Sharpness ≥ 95 % of the F1 maximum in 10/10 (stand) and ≥ 9/10 (hand-held); chosen values within ±2 fine steps; time ≤ the §7.2 estimate + 50 % |
| F3 | **Parallel** | F2 with all cameras at once, 5 runs | Total time, per-camera result vs F2, CPU per process | Same accuracy as F2; total ≤ slowest single camera + 3 s |
| F4 | **Camera AF as a reference** (diagnostic, not product) | Board in view; AF on; wait 6 s; read back in-stream; stop; read back closed; then set the readback value with the manual flag and score | AF settle time; AF board-ROI sharpness vs F1 peak; board vs background sharpness (what AF aimed at); readback in-stream and closed vs the F1-implied position; sharpness change after the "lock" | Records which models could use option C |
| F5 | **AF off without a value** | Windows: AF on and settled, then switch to manual with the current readback value; separately, KS property set with the manual flag only (if the driver accepts it). Linux: `FOCUS_AUTO=0` alone | Sharpness before and after the switch, readback | Lens stays (sharpness within ±5 %), or the result shows it jumps |
| F6 | **Lock held** | After F2: stream 10 min; then 10× stop/start in-process; 10× close/reopen in a new process | Readback value and flags every 1 s; board-ROI and static-scene sharpness every frame; per start, time from first frame to the settled level | Readback constant; sharpness within ±5 % after the settle time; settle time per model recorded (Kiyo expected ~1 s, C930e ~0.4 s, C922 0) |
| F7 | **Restore** | After a lock: (a) restart skellycam, (b) replug on the same port, (c) replug on another port, (d) reboot, (e) the same with Logi Tune and Razer Synapse running | Readback after open, sharpness at the board vs the lock-time value; key match | (a), (b), (d), (e): value restored, manual flag, sharpness within ±5 %. (c): serial-less cameras reported "unknown, re-focus"; the C922 restored by serial |
| F8 | **Calibration sensitivity** | Calibrate at the locked value v*, then at v* ± 1, 2, 5 fine steps and at the far end | fx, fy, cx, cy, k1, k2; reprojection error of v* board views using each other calibration | Gives the per-model "refocus means recalibrate" threshold (expected: any step [I]) |
| F9 | **Fixed focus** | Generic camera through the focus step | Status shown | "Fixed focus", no error, no stored value |
| F10 | **Failure handling** | Board absent; letter board at 5 m; board waved | Reported reason; value after failure | Clear reason; previous value kept; calibration not started for that camera |
| F11 | **Focus-lost detection** | During a stream, another process turns AF on or sets another value | Time to warning | Warning within 2 s; recording blocked if focus no longer matches the calibration |

Plan text to change when this is adopted (not edited here): TP1 "Manual control only" row → add the F tests, and the product note under TP1 ("How focus is set … under investigation") → option B.

---

## 10. Not determined

- Whether any camera keeps the lens in place when AF is switched off without sending a value (F5).
- The Kiyo's true sharpness peak and width; the 5-point sweep missed it (F1).
- Settle time for small focus steps; only 25 %-of-range steps were timed (F1).
- Focus persistence across replug and reboot, and whether Logi Tune or Razer Synapse re-apply settings (F7).
- Whether the C922's closed-camera reads (30) are its real lens position (F4).
- Any behaviour on Linux or macOS, including whether macOS offers `.autoFocus` / `.locked` for external UVC webcams.
- Focal-length change with focus on our cameras (F8); no published webcam numbers were found.
- ChArUco detection limits on these cameras at 3–5 m, with real defocus and sway (F2, F10).
- Whether the UVC 1.0 text matches the 1.5 wording quoted in §4.1.

## 11. Sources

- **Measured:**
  - [W-CTRL-LIST.json](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-LIST.json), [W-CTRL-EFFECT.json](../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-EFFECT.json), [W-AUTO.json](../results/windows/Gerald/suite_20261111T040003Z/W-AUTO.json) and [W-AUTO/](../results/windows/Gerald/suite_20261111T040003Z/W-AUTO/), [W-OCV-CTRL.json](../results/windows/Gerald/suite_20261111T040003Z/W-OCV-CTRL.json).
  - Raw frames in `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_20261111T040003Z\W-CTRL-EFFECT\` (local, not in the repo).
  - Write-up `windows_results_20261110.md` §5–6.
- **Code:**
  - skellycam `dom/research` @ `00f28fe1`, `upstream/sfn26` @ `19ea17e7`, `dom/openpnp-capture-mf` @ `d55f7690` (read with `git show` / `git grep`, no checkout).
  - freemocap `development` @ `5632778a`.
  - Suite code `suite/windows/tests/w_ctrl_effect.py`, `w_auto.py`, `suite/common/imgmetrics.py`.
- **Primary sources** (accessed 2026-11-11):
  - UVC 1.5 class specification (USB-IF zip above).
  - Microsoft Learn: CameraControlFlags, KSPROPERTY_CAMERACONTROL_FOCUS, KSPROPERTY_CAMERACONTROL_EXTENDED_FOCUSMODE, Microsoft extensions to UVC 1.5.
  - Linux kernel V4L2 camera-control docs and `uvc_ctrl.c`.
  - Apple AVFoundation FocusMode `.locked` / `.autoFocus` and `isAdjustingFocus` (documentation JSON).
  - guvcview `soft_autofocus.c`.
  - Pupil Capture docs.
  - arXiv:2402.04686.
- **Forum and search-summary sources:** OBS forum, OctoPrint community, MATLAB Answers, Luxonis forum, SimTK (OpenCap), UVA Scholars' Lab, Agisoft knowledge base, VCM patents (US 10,473,884 and others), arXiv:2510.23589.
- **Related study docs:** `macos_uvc_controls_review.md`, `capture_stack_options_plan.md`, `skellycam_exposure_review.md`, `xplat_capture_plan.md`.
