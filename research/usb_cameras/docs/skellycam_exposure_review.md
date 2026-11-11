# How skellycam sets exposure today, and whether it guards against motion blur

Written 2026-11-09. Code read at `dom/research` @ `55f851e4`. Upstream fetched 2026-11-09: `upstream/sfn26` @ `765bf82d` and `upstream/cleanup-camera-api` (same exposure code as `sfn26`). Paths are relative to the repo root.
Labels as elsewhere in this study: **measured** (a result file supports it), **code** (read from the source), **inferred** (reasoned, not tested).
OpenCV behaviour was read from the 4.12.0 source (`modules/videoio/src/cap_dshow.cpp`, `cap_avfoundation_mac.mm`), the version both checkouts pin (`uv.lock`: `opencv-contrib-python` 4.12.0.88).

## 1. Summary

**Short answer: no.** Neither this checkout nor the newest upstream branches set an exposure-time limit based on motion blur, frame rate or subject speed, and none warns the user that an exposure is long enough to blur. The newest upstream branches add one fixed cap: manual exposure is limited to 2⁻⁵ s (31.25 ms).

A note on direction: blur grows with exposure *time*, so a blur guard is a **ceiling on exposure time**. In skellycam's log2 units a ceiling on time is an upper bound on the setting (e.g. "≤ −7"), because more negative means shorter.

| | This checkout (`dom/research`, same as `upstream/development-streaming`) | Upstream `sfn26` / `cleanup-camera-api` (2026-10-30 to 11-07) |
| --- | --- | --- |
| Exposure-time ceiling in MANUAL | None in the backend. The UI slider stops at −4 (62.5 ms, longer than a 30 fps frame). | Clamped to −5 (31.25 ms) with a server-log warning; UI slider stops at −5 |
| RECOMMEND | Picks the setting whose whole-frame mean brightness is closest to 127.5, then one stop shorter. Result range −13…−5 | Same rule, run on all chosen cameras at once. Result range −12…−6 (≤ 15.6 ms) |
| AUTO on Windows | **Broken: locks exposure at its current value, not auto** (§3.2) | Fixed: really enables the camera's auto exposure |
| Limits on the camera's own AE | None. AE priority is never touched | None. AE priority is never touched |
| Linux | Always forced to camera AE, whatever was asked | Same |
| macOS | Exposure settings silently do nothing (OpenCV backend has no exposure support) | Same for the Python backend |
| Motion-aware or fps-aware logic | None | None |
| Exposure recorded per frame | No (requested config saved once per recording) | No |

The only blur-related nudges are:
- RECOMMEND's −1 offset, which halves the exposure it would otherwise pick;
- the `exposure` field description in `camera_config.py:104-105`: "Set this as low as possible to avoid blur. Mocap likes BRIGHT environments and FAST/LOW exposure settings!";
- upstream's −5 cap. That is about one frame period at 30 fps, so it mainly protects the frame rate. It is still a lot of blur for fast motion (§5).

## 2. Units

On Windows (DirectShow `IAMCameraControl`, which OpenCV `CAP_DSHOW` passes straight through), an exposure value *v* means 2^*v* seconds. Real cameras round this to their own steps, and the actual time has not yet been measured on the rig (test plan M1, `test_gap_plan.md`).

| Setting | −13 | −12 | −11 | −10 | −9 | −8 | −7 | −6 | −5 | −4 | −3 | −2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Nominal time (ms) | 0.12 | 0.24 | 0.49 | 0.98 | 1.95 | 3.91 | 7.81 | 15.6 | 31.3 | 62.5 | 125 | 250 |

- The `exposure` field description in `camera_config.py:102` says "the number is the exposure time in ms, raised to the power of -2". **That is wrong**: the value is log2 of seconds.
- **Device ranges on Gerald** (*measured*, `results/windows/Gerald/suite_20261106T224912Z/W-CTRL-LIST.json`, `ranges.cc.exposure`):
  - C922, C930e and Kiyo: −11 to −2;
  - generic "USB Camera" (4c4a:4a55): −7 to 3, so its shortest exposure is 7.8 ms.
- The UI minimum of −13 is below every camera tested.
- Auto-exposure priority (UVC `CT_AE_PRIORITY_CONTROL`, which lets the camera lower the frame rate so it can lengthen exposure) was **1 on the C922 and C930e** and 0 on the Kiyo. The generic camera has no such control (same file, `ranges.cc.auto_exposure_priority`).

## 3. This checkout (`dom/research` @ `55f851e4`)

These exposure files are identical to `upstream/development-streaming`.

### 3.1 Modes and defaults
- `ExposureModes` (`recommend_camera_exposure_setting.py:15-18`): `AUTO = 0.75`, `MANUAL = 0.25`, `RECOMMEND = -1`.
- Defaults (`camera_config.py:24-25`): mode `MANUAL`, exposure −7 (7.8 ms). The UI default is the same (`cameras-types.ts:138-139`).
- UI bounds: −13 to −4 in both the config panel (`CameraConfigExposure.tsx:13`) and the grid settings modal (`CameraGridSettingsModal.tsx:27-28`). Only the config panel offers RECOMMEND.
- Nothing in the backend validates the value. `CameraConfig.exposure` is a plain `int` (`camera_config.py:100`).

### 3.2 Applying it: `_apply_exposure` (`opencv_apply_config.py:21-47`)
- **Linux:** always sets `CAP_PROP_AUTO_EXPOSURE = 3` and returns. The docstring says the log2 values from the UI do not match V4L2's absolute units (100 µs steps), so the mode the user asked for is ignored.
- **Windows (DirectShow) and macOS:**
  - MANUAL: `CAP_PROP_AUTO_EXPOSURE = 1`, then `CAP_PROP_EXPOSURE = value`;
  - AUTO: `CAP_PROP_AUTO_EXPOSURE = 3`;
  - RECOMMEND: runs the search (§3.3), then applies the result as MANUAL.

**How OpenCV 4.12 DirectShow reads those numbers** (*code*, `cap_dshow.cpp:3514-3524`, `1920-1960`):
- `CAP_PROP_AUTO_EXPOSURE` turns auto **on only if `cvRound(value) == 1`**. Otherwise it writes the current exposure back with `CameraControl_Flags_Manual`.
- `CAP_PROP_EXPOSURE` calls `IAMCameraControl::Set(value, Flags = 0)`.

So on Windows:
- **AUTO (3) turns auto exposure off** and locks the exposure at whatever value the camera had (*code*).
  - Cameras open in auto: the control list shows `flags: auto` at −4 or −5 on the Logitech cameras and the Kiyo.
  - So "AUTO" in this checkout probably freezes a long exposure, 31–62 ms, chosen by the camera at open time (*inferred*).
- **MANUAL (1) briefly turns auto exposure on** (DirectShow resets exposure to the device default with the auto flag). The following `CAP_PROP_EXPOSURE` set, with flags 0, then sets the value.
  - The value has been seen to take effect: the generic camera's fps changed under OpenCV manual −7 (*measured*, `windows_results_20261106.md` §2).
  - It works only because of the call order.

**Exposure is applied before the stream is reconfigured** (*code*: `opencv_apply_config.py:71-85` sets exposure, then width and height, then FOURCC).
- DirectShow FOURCC and size changes stop and re-create the device (`cap_dshow.cpp` `setProperty`).
- On the C930e the exposure read back −5 in 14 of 15 skellycam-sequence cycles after a −7 set (*measured*, `windows_results_20261106.md` §2, "Manual exposure −7").
- The C930e also resets exposure to −5 at every stream start (*measured*, same file, control-effect table).
- Net effect: on the C930e the user's exposure is usually replaced by 31 ms.

**macOS:** OpenCV's macOS AVFoundation backend handles no exposure properties at all (*code*: `cap_avfoundation_mac.mm` has no `CAP_PROP_EXPOSURE` or `CAP_PROP_AUTO_EXPOSURE` case). Every mode leaves the camera on its own AE.

### 3.3 RECOMMEND (`recommend_camera_exposure_setting.py:25-104`)
1. Try each value from −12 to −4 (`MIN_EXPOSURE`, `MAX_EXPOSURE`, lines 9–10). For each one:
   - set `CAP_PROP_AUTO_EXPOSURE = 0.25` (DirectShow reads it as 0, i.e. manual, so this part is correct);
   - set the value;
   - read and discard 10 frames;
   - take `np.mean` of the 11th frame over all pixels and channels.
2. Pick the value whose mean is closest to 127.5.
3. Add `offset_from_midrange = -1` (one stop shorter, half the time). The result is **not** clamped to the device range, so it can be −13.
4. Store it as MANUAL.

What it does not do:
- It does not look at motion, frame rate or subject speed.
- It does not trade gain for exposure: gain is never set.
- It does not cap exposure at the frame period. In a dim room it will pick −4 (62.5 ms), and the −1 offset then gives −5 (31 ms).
- Values below the device minimum (−12 on every tested camera, and −12 to −8 on the generic one) are likely rejected by the driver. The frame measured for them then shows the previous setting (*inferred*).
- It runs one camera at a time, inside each camera's own configuration step: about 99 frames, or roughly 3.3 s at 30 fps per camera (*inferred*).

### 3.4 AUTO
AUTO hands control to the camera's AE: on Linux always, and on Windows in intent only (§3.2). skellycam sets no AE limits:
- No UVC exposure-time limits exist to set: UVC defines none. Vendor extension units may have some, but none is used.
- AE priority is never set. On the C922 and C930e it is 1, so in low light the camera may lengthen exposure and drop the frame rate.
- The generic camera ran at 17.15 fps under auto in evening light, against 25.7 fps under manual −7 (*measured*, `windows_results_20261106.md` §3). The report infers AE as the cause.

### 3.5 What gets recorded
- `extract_config_from_cv2_capture` reads `CAP_PROP_EXPOSURE` back once per configuration (`opencv_extract_config.py:23`). It raises an error if the readback is 0 on any platform except macOS.
- Recordings save the camera configs once (`recording_finalizer.py:55`).
- No per-frame exposure is stored, so under AUTO there is no record of what exposure each frame actually used.

## 4. Upstream branches

Fetched 2026-11-09. Branches newer than this checkout's base (`23ccbf20`, 2026-07-21):

| Branch | Last commit | Exposure changes |
| --- | --- | --- |
| `sfn26` | 2026-11-07 | Yes (below). Also has a Rust capture backend |
| `cleanup-camera-api` | 2026-11-01 | Same exposure code as `sfn26` |
| `development-streaming` | 2026-10-18 | None (identical to this checkout) |
| `jon/development-auto-framerate` (older, 2025-11-05) | – | Only changes the default exposure from −7 to −6 |

The `sfn26` / `cleanup-camera-api` exposure work is by Jon Matthis, commits `26c72bc2` "Share exposure recommendation across camera backends" and `43e2b968` "Fix camera orientation, exposure, and lifecycle regressions" (2026-10-30), plus `f1aefa95` (2026-11-01). What changed (*code*):

1. **Fixed manual ceiling of −5 (31.25 ms).**
   - `MAX_MANUAL_EXPOSURE = -5` (`camera_config.py:26`).
   - `CameraBackendManager._create_or_update` lowers any MANUAL exposure above −5 to −5 and logs a warning (`camera_backend_manager.py:49-53`).
   - Both UI sliders stop at −5.
   - It is not a pydantic validator: code that calls a camera group directly skips it, and the user sees the warning only in the server log.
   - No commit message, doc or comment gives a reason for −5. Its value is close to one 30 fps frame period (33.3 ms), so it reads as a frame-rate guard. It is not frame-rate aware: at 60 fps the period is 16.7 ms, and −5 is still allowed.
2. **RECOMMEND moved to a shared async task** (`core/camera_group/tasks/recommend_exposure.py`):
   - the same brightness-nearest-127.5 rule and −1 offset;
   - candidates from −12 to −5, with the result clamped to the candidate range, so **the result is −12 to −6 (at most 15.6 ms)**;
   - all chosen cameras are tested together;
   - it counts fresh frame numbers, not loop passes;
   - it restores the old settings on failure or cancellation;
   - it is skipped on Linux, where RECOMMEND becomes AUTO.
   - `docs/camera-group-tasks.md:15` still says the search goes to −4 (stale).
   - It does not trade gain for exposure and does not consider motion.
3. **DirectShow AUTO and MANUAL fixed** (`opencv_apply_config.py`):
   - sends 1.0 / 0.0 to `CAP_PROP_AUTO_EXPOSURE` on DirectShow, with a citation of the same OpenCV 4.12 source (`references.bib`, `opencv412DirectShowControls`);
   - tests in `test_opencv_exposure_contract.py`.
4. **Exposure re-applied after size or FOURCC changes**, because those re-create the DirectShow stream. This addresses the C930e reset in §3.2, but only for the reconfigure itself: the C930e also resets at stream start (*measured*), and whether the new order fixes that has not been measured.
5. **Rust backend** (`skellycam-rust/src/camera/camera_thread.rs:688-713`, openpnp-capture over DirectShow):
   - MANUAL clamps the value to the limits the device reports, then sets it;
   - AUTO calls `Cap_setAutoProperty(…, 1)`;
   - it gets the same −5 cap and RECOMMEND task from `CameraBackendManager`.
   - No AE limits or AE-priority handling.

Nothing in either branch mentions blur, AE priority or subject speed (`git grep -i "blur\|priority"` over `skellycam/`, `skellycam-rust/src/` and `skellycam-ui/src/` finds only unrelated hits).

## 5. How much blur these settings allow (illustration)

*Estimate* with assumed numbers:
- **Geometry:** a 1280 px wide image, about 70° horizontal field of view (C922-like), subject 3 m away. The image is then about 4.2 m wide, or about 305 px per metre.
- **Motion:** a hand moving 2 m/s gives about 610 px/s; a fast limb at 5 m/s gives about 1525 px/s.
- **Blur** (length of the smear) = speed × exposure time.

| Setting (time) | Blur at 2 m/s | Blur at 5 m/s | Where skellycam can land here |
| --- | --- | --- | --- |
| −4 (62.5 ms) | 38 px | 95 px | This checkout: UI maximum; possible frozen value under "AUTO" on Windows |
| −5 (31.3 ms) | 19 px | 48 px | Upstream manual cap; this checkout's longest RECOMMEND result; C930e after the stream-start reset |
| −6 (15.6 ms) | 9.8 px | 24 px | Upstream's longest RECOMMEND result |
| −7 (7.8 ms) | 4.8 px | 12 px | Default; generic camera's shortest |
| −8 (3.9 ms) | 2.4 px | 6.0 px | |
| −9 (2.0 ms) | 1.2 px | 3.0 px | |
| −10 (1.0 ms) | 0.6 px | 1.5 px | |

Keeping blur to about 1–2 px for fast limbs at this distance needs roughly −9 to −10 (1–2 ms). Only bright light makes that usable, or gain (which skellycam never sets) with the extra noise it brings.

## 6. What a blur guard would need (not implemented anywhere)

- **A ceiling from the frame rate.** Exposure ≤ 1/fps at the least, so a 60 fps request caps at −6, not −5.
- **A ceiling from blur.** An exposure limit from a user-chosen speed and blur budget: E_max = blur_px / (speed × px_per_m). Use it in MANUAL validation and as the upper end of RECOMMEND's search.
- **RECOMMEND that searches inside that ceiling and raises gain** when the image is still too dark, rather than picking the brightest-mean exposure.
- **AE priority set to 0 wherever the camera has it**, so AUTO cannot lower the frame rate. Upstream does not do this. It needs a DirectShow or Media Foundation `IAMCameraControl` call (`CameraControl_AutoExposurePriority`), because OpenCV has no property for it.
- **A UI warning**, not just a server log line, when the chosen or resulting exposure exceeds the ceiling.
- **Per-camera limits read from the device** (as upstream's Rust path does), instead of fixed −13 / −4 / −5 bounds.
- **Linux and macOS:**
  - Linux: convert log2 seconds to V4L2 `exposure_time_absolute` (100 µs units) instead of forcing AE;
  - macOS: a control path outside OpenCV (`macos_uvc_controls_review.md`).
- **Recording what happened:** store the readback exposure per recording, ideally per frame, so blur can be checked afterwards.

## 7. Checks worth running

These are not run; they belong to tier 0.
1. On Gerald, DirectShow: put skellycam in AUTO on the C922 and read `IAMCameraControl` flags and value after configuration. This confirms §3.2's "AUTO locks exposure" on hardware.
2. Run the same with the `sfn26` order (exposure after FOURCC) on the C930e, and check whether −7 survives stream start.
3. Measure actual exposure times for −5 … −10 on the rig (test plan M1), so the table in §2 and §5 rests on measured times, not nominal ones.
