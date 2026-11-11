# W-CYC and W-KIYO analysis: suite run 20261106T181941Z on Gerald

Scope: the 28 `reliability` cells (W-CYC) and the one `kiyo` cell (W-KIYO) in [summary.md](../summary.md). Sources: [W-CYC.json](../W-CYC.json), the per-cycle rows in `W-CYC/<camera>/<variant>_cycles.json`, [W-KIYO.json](../W-KIYO.json), [suite_log.txt](../suite_log.txt), [W-MJPEG.json](../W-MJPEG.json), [W-CTRL-LIST/](../W-CTRL-LIST), the raw W-MJPEG Kiyo summary at `C:/Users/Dom/Documents/skellycam-raw/results/windows/Gerald/suite_20261106T181941Z/W-MJPEG/usbvideodevice_1532-0e05_4/mf_640x360_5/summary.json`, and the quick self-test from earlier the same day, `../../suite_build_selftest_20261106/quick/`. Cameras were not opened. Suite code and result files were not changed.

Labels: **measured** means the value was read from the file and field named; **inferred** means it is an interpretation.

Times: local is UTC−5 (13:19 local = 18:19Z). The Kiyo's `last_arrival` is 2026-11-06T14:59:24Z, which is 09:59:24 local. The quick self-test's plug-in age agrees with that.

## 1. Summary

- **MF and DirectShow (PyAV) both passed open/close/open/close on every healthy camera.** The healthy cameras are the C922, the generic camera and the C930e.
  - 90/90 MF cycles per camera (50 in-process, 15 in new processes, 25 mode-switch) and 90/90 DS cycles per camera.
  - No hangs, no failures, no recovery needed. Pooled over the three cameras: 270/270 per API, Wilson 95% lower bound 0.986 (computed from n_ok/n). **Measured.**
  - The difference between the two is latency. MF reaches the first frame 255–290 ms sooner than DS on every camera. Close takes about the same time with both (265–405 ms).
- **OpenCV CAP_DSHOW is "no" on all four cameras, for two different reasons:**
  - **On the three healthy cameras, the open and close never failed, but the first frame was always late.** 15/15 cycles opened and delivered frames, yet 0/15 reached the first frame within 2 s.
    - Almost all of the delay is the property-set phase, 1.7–3.3 s. It is slow because each set rebuilds the DirectShow graph.
    - skellycam's set order (FOURCC first) also ended in **YUY2 at 10 fps** on both Logitech cameras, not the MJPG 30 fps that was asked for.
  - **On the Kiyo, every open failed,** because the device was already faulted.
- **The Kiyo cells are all "no" because the Kiyo was already faulted when W-CYC started.** W-CYC did not cause the fault.
  - The fault began at 13:43:39–13:43:50 local (18:43:39Z), plug-in age about 224 min. That was during the Kiyo's **first stream of the run**, in W-MJPEG at MJPG 640x360@5 through MF:
    - one valid JPEG arrived at 2170 ms;
    - no further frame arrived;
    - `reader_release` hung for more than 5 s and the watchdog killed the process.
  - From then on, every streaming open failed, fast and the same way on every attempt: MF with `0x8007001F` at the first ReadSample, DS with `OSError(5)` at open.
  - The controls stopped answering too (W-KIYO).
  - The device itself was not the problem in the sense of a missing device: its devnode stayed healthy throughout (problem code 0, no re-arrival).
  - **The cause is the device, not the harness** (inferred). Timeouts, the default mode and the SuperSpeed path are ruled out (section 4).
- **The W-KIYO "no" is real, but it measures nothing about when the Kiyo stops answering.** It ran last, 72 min after the fault began, and its first poll already failed.
  - The code it reports, `0x80004002`, is most likely wincam's initial "never called" value, not an error the device returned (section 5).
- **New re-arrival, not mentioned in the brief: the generic camera also re-arrived at 14:24:27 local (19:24:27Z), during W-CYC.** This is in addition to the W-MULTI re-arrival.
  - The time falls inside OpenCV cycle 13. That cycle's `cap.set()` took 11.35 s and fell back to YUY2 640x480. **Measured.**
  - No W-CYC verdict uses this re-arrival.

## 2. Every W-CYC cell

### 2.1 How the rating is decided

The rating comes from `common/rating.py:225-249` (`rate_reliability`), applied to the summary that `common/cycstats.py:58-105` builds from the cycle rows:

- **"yes":** `first_frame_within_rate ≥ 0.99`, no hangs, no unreleasable cycles, and `replug_needed` not True.
- **"no":** `first_frame_within_rate < 0.95`, or `replug_needed` is True.
- **"partial":** everything else.

A cycle counts as "within" when `ok` is true **and** `first_frame_ms ≤ 2000`. Here `first_frame_ms` is overwritten with `open_to_first_frame_ms` (`w_cyc.py:68-70`), so the 2 s is measured from the start of the open call.

`replug_needed` is the variant's `replug_suspected`. It is True when the variant ended in failures and a one-capture health probe through the same API family then also failed (`w_cyc.py:254-259`).

### 2.2 Table (all values measured)

Sources: `W-CYC.json` → `measurements.cameras.<key>.variants.<v>.summary` (`n_ok`, `wilson95`, `n_first_frame_within`, `first_frame_within_wilson95`, `timings_ms.open_to_first_frame_ms`, `timings_ms.close_ms`, `failure_classes`, `recovery_after_failure`) and `.health_after`. The rating is from `verdicts["reliability|<key>|<v>"].rating`.

| Camera | Variant | Rating | open+first frame ok (Wilson 95%) | first frame ≤ 2 s (Wilson 95%) | open→first frame p50 / p95 / max ms | close p50 / p95 / max ms | Failure class (stage, code, n) | Recovery | Health after |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C922 | mf_inproc | yes | 50/50 (0.929-1.000) | 50/50 (0.929-1.000) | 329 / 335 / 337 | 352 / 356 / 359 | - | - | - |
| C922 | mf_newproc | yes | 15/15 (0.796-1.000) | 15/15 (0.796-1.000) | 332 / 337 / 338 | 351 / 355 / 355 | - | - | - |
| C922 | ds_inproc | yes | 50/50 (0.929-1.000) | 50/50 (0.929-1.000) | 585 / 596 / 619 | 345 / 353 / 357 | - | - | - |
| C922 | ds_newproc | yes | 15/15 (0.796-1.000) | 15/15 (0.796-1.000) | 613 / 623 / 630 | 345 / 353 / 354 | - | - | - |
| C922 | opencv_inproc | **no** | 15/15 (0.796-1.000) | 0/15 (0.000-0.204) | 3040 / 3069 / 3083 | 333 / 336 / 338 | - | - | - |
| C922 | mf_modeswitch | yes | 25/25 (0.867-1.000) | 25/25 (0.867-1.000) | 327 / 331 / 333 | 349 / 354 / 354 | - | - | - |
| C922 | ds_modeswitch | yes | 25/25 (0.867-1.000) | 25/25 (0.867-1.000) | 577 / 597 / 618 | 343 / 350 / 351 | - | - | - |
| Kiyo | mf_inproc | **no** | 0/50 (0.000-0.071) | 0/50 (0.000-0.071) | - | 1 / 2 / 2 | first_sample 0x8007001F x50 | 0/49 | FAILED 0x8007001F |
| Kiyo | mf_newproc | **no** | 0/15 (0.000-0.204) | 0/15 (0.000-0.204) | - | 1 / 1 / 1 | first_sample 0x8007001F x15 | 0/14 | FAILED 0x8007001F |
| Kiyo | ds_inproc | **no** | 0/50 (0.000-0.071) | 0/50 (0.000-0.071) | - | - | open errno 5 x50 | 0/49 | FAILED errno 5 |
| Kiyo | ds_newproc | **no** | 0/15 (0.000-0.204) | 0/15 (0.000-0.204) | - | - | open errno 5 x15 | 0/14 | FAILED errno 5 |
| Kiyo | opencv_inproc | **no** | 0/15 (0.000-0.204) | 0/15 (0.000-0.204) | - | - | open (isOpened False) x15 | 0/14 | FAILED errno 5 (DS probe) |
| Kiyo | mf_modeswitch | **no** | 0/25 (0.000-0.133) | 0/25 (0.000-0.133) | - | 1 / 1 / 2 | first_sample 0x8007001F x25 | 0/24 | FAILED 0x8007001F |
| Kiyo | ds_modeswitch | **no** | 0/25 (0.000-0.133) | 0/25 (0.000-0.133) | - | - | open errno 5 x25 | 0/24 | FAILED errno 5 |
| generic | mf_inproc | yes | 50/50 (0.929-1.000) | 50/50 (0.929-1.000) | 98 / 177 / 179 | 267 / 271 / 272 | - | - | - |
| generic | mf_newproc | yes | 15/15 (0.796-1.000) | 15/15 (0.796-1.000) | 115 / 185 / 197 | 267 / 271 / 272 | - | - | - |
| generic | ds_inproc | yes | 50/50 (0.929-1.000) | 50/50 (0.929-1.000) | 370 / 443 / 452 | 268 / 273 / 276 | - | - | - |
| generic | ds_newproc | yes | 15/15 (0.796-1.000) | 15/15 (0.796-1.000) | 396 / 467 / 471 | 270 / 272 / 273 | - | - | - |
| generic | opencv_inproc | **no** | 15/15 (0.796-1.000) | 0/15 (0.000-0.204) | 2060 / 11768 / 11793 | 263 / 391 / 394 | - | - | - |
| generic | mf_modeswitch | yes | 25/25 (0.867-1.000) | 25/25 (0.867-1.000) | 96 / 111 / 125 | 268 / 274 / 277 | - | - | - |
| generic | ds_modeswitch | yes | 25/25 (0.867-1.000) | 25/25 (0.867-1.000) | 368 / 377 / 380 | 269 / 274 / 274 | - | - | - |
| C930e | mf_inproc | yes | 50/50 (0.929-1.000) | 50/50 (0.929-1.000) | 481 / 521 / 528 | 337 / 375 / 379 | - | - | - |
| C930e | mf_newproc | yes | 15/15 (0.796-1.000) | 15/15 (0.796-1.000) | 523 / 527 / 527 | 338 / 357 / 369 | - | - | - |
| C930e | ds_inproc | yes | 50/50 (0.929-1.000) | 50/50 (0.929-1.000) | 771 / 789 / 809 | 364 / 404 / 405 | - | - | - |
| C930e | ds_newproc | yes | 15/15 (0.796-1.000) | 15/15 (0.796-1.000) | 802 / 816 / 816 | 366 / 384 / 397 | - | - | - |
| C930e | opencv_inproc | **no** | 15/15 (0.796-1.000) | 0/15 (0.000-0.204) | 4229 / 4274 / 4300 | 358 / 379 / 381 | - | - | - |
| C930e | mf_modeswitch | yes | 25/25 (0.867-1.000) | 25/25 (0.867-1.000) | 508 / 518 / 521 | 356 / 392 / 395 | - | - | - |
| C930e | ds_modeswitch | yes | 25/25 (0.867-1.000) | 25/25 (0.867-1.000) | 813 / 841 / 843 | 366 / 396 / 407 | - | - | - |

Kiyo timings for the failed cycles, which `timings_ms` leaves out (`timings_ms_all_cycles`, measured):

- MF `activate_ms` p50 22.5 ms, then the failure at the first ReadSample.
- DS `open_ms` p50 311 ms (ds_inproc), 336 ms (ds_newproc).
- OpenCV `open_ms` p50 329 ms.

All three are fast, definitive failures. None of them is a timeout.

### 2.3 Why each group of cells has its rating

| Cells | Criterion that decided it (JSON field) | Real or artefact |
| --- | --- | --- |
| 18 × **yes** (C922, generic, C930e × mf_inproc / mf_newproc / ds_inproc / ds_newproc / mf_modeswitch / ds_modeswitch) | `first_frame_within_rate` = 1.0 ≥ 0.99, `hangs` 0, `unreleasable` 0, `replug_needed` False | **Real**, with three caveats. (a) n = 15–50, so the Wilson lower bounds (0.796–0.929) cannot show the plan's ≥ 99% statistically; "yes" here means the point estimate is ≥ 99%. (b) In ds_modeswitch on the C922 and the C930e, **12/25 cycles streamed rawvideo (YUY2), not MJPEG**: `variants.ds_modeswitch.format_fallbacks` = 12, rows `codec: rawvideo, frames_ok: 0` on every 640x480 cycle. pyav_ds `cycle` counts these as ok by design (`pyav_ds.py:26-28`). The cell is right for open/close but hides a format failure; see bug B6. (c) The generic camera re-arrived during its own opencv_inproc variant, before its mf_modeswitch and ds_modeswitch ran; those two still passed 25/25. |
| 3 × **no**: opencv_inproc on C922, generic, C930e | `first_frame_within_rate` = 0.0 < 0.95. `success_rate` = 1.0 and `hangs` 0 | **Real** (OpenCV CAP_DSHOW latency with skellycam's set order), but presented badly. The camera opened, streamed and closed in 15/15 cycles; only the 2 s latency criterion failed. Section 3. |
| 7 × **no**: every Kiyo variant | `first_frame_within_rate` = 0.0 **and** `replug_needed` True (the health probe after the variant failed) | **Mixed.** The device state is real: the Kiyo was wedged. The cells do not measure any API's open/close reliability, because the camera was faulted before W-CYC began (section 4). The "no state that needs a replug" criterion (`criteria[2].met` = False) is correct about the state but blames the variant; the harness has no pre-test probe (bug B1). |

## 3. Why OpenCV CAP_DSHOW is "no" on every camera

**Measured** from the rows in `W-CYC/<cam>/opencv_inproc_cycles.json` (fields `open_ms`, `set_ms`, `open_to_first_frame_ms`, `sets.got_fourcc`, `fps_measured`, `frame_shape`, `size_mismatch`):

| Camera | `VideoCapture()` open p50 | `cap.set()` ×4 p50 | open→first frame p50 | Negotiated | `fps_measured` |
| --- | --- | --- | --- | --- | --- |
| C922 | 457 ms | 2289–2306 ms | 3040 ms | **YUY2** 1280x720 in 15/15 | **10.0** |
| C930e | 754 ms | 3204–3343 ms | 4229 ms | **YUY2** 1280x720 in 15/15 | **10.0** |
| generic | 308 ms | 1655–1700 ms (13 cycles); **11366 / 11348 ms** (cycles 0 and 13) | 2060 ms (11.8 s for cycles 0 and 13) | MJPG 1280x720 in 13/15; **YUY2 640x480** in cycles 0 and 13 (`sets.h` False, `size_mismatch` True) | 25.6–26.1 (MJPG); 29.8–30.2 (YUY2 VGA) |
| Kiyo | 329 ms | - | - | `isOpened()` False in 15/15 | - |

Notes:

- **Why the latency criterion fails.** On every healthy camera the property sets alone take longer than the 2 s budget, or nearly all of it.
  - The open alone (0.3–0.75 s) is comparable to the DS open.
  - The 4 sets (FOURCC, width, height, fps) cost 1.7–3.3 s. The test's docstring attributes this to each set restarting the DirectShow graph (`w_cyc.py:16-17, 40-42`). That explanation is **inferred**, consistent with set time ≈ 4 × (open time).
  - The generic camera misses 2 s by only 17–110 ms on its MJPG cycles (2017–2110 ms).
  - This is **real API behaviour** of OpenCV CAP_DSHOW with set-after-open, not a harness timeout. The tool bound was 15 s (`OPENCV_TIMEOUT_MS`), and no call timed out (`hangs` 0).
- **Wrong format with skellycam's set order** (real, and arguably the more important finding):
  - The helper uses skellycam's `create_cv2_video_capture` order, FOURCC first, then width/height/fps (`opencv_ds.py:115-120`; skellycam `skellycam/core/camera/opencv/opencv_helpers/create_cv2_video_capture.py:53-58`).
  - With that order, both Logitech cameras ended in YUY2 1280x720 at 10 fps (`sets.got_fourcc` = "YUY2", `fps_measured` = 10.0), even though every `set()` returned True and `CAP_PROP_FPS` read back 30.
  - On the generic camera, 2 of 15 cycles (13%) fell back to YUY2 640x480 after an 11.3 s set.
  - The harness rows still say `ok: True` (`opencv_ds.py:165-167` checks only the frame shape), so neither the rating nor the summary shows the wrong format (bug B3).
  - skellycam's `opencv_apply_config.py:75-85` uses the other order (size, then fps, then FOURCC). The suite never ran it, although the helper supports `--set-order size-first` (`opencv_ds.py:120`) (bug B4).
- **A device re-arrival tied to OpenCV** (measured; cause inferred).
  - `W-CYC.json` → `measurements.arrivals.changes[0]`: the generic camera's `last_arrival` went from 18:17:09Z to **19:24:27.05Z**, and `measurements.arrivals.unexplained_re_arrival` = true.
  - The generic's opencv_inproc cycle 13 started at 19:24:15.90Z (row `utc`). Its 11.35 s `set_ms` therefore ends at about 19:24:27.3Z, the same moment as the re-arrival.
  - Cycle 0 had the same 11.4 s set with a YUY2 640x480 fallback. Only the last arrival is recorded, so whether cycle 0 also caused a re-enumeration is unknown.
  - **Inferred:** OpenCV's graph rebuilds made this camera reset or re-enumerate on its shared HS13 hub. This should be reproduced with a per-cycle arrival check (bug B5).

## 4. The Kiyo: what failed, where, when, and whose fault

### 4.1 Timeline (measured)

| Local time (UTC−5) | Plug-in age | Event | Source |
| --- | --- | --- | --- |
| 09:59:24 | 0 | Kiyo last arrival | `W-KIYO.json` `measurements.cameras.<kiyo>.last_arrival` = 14:59:24Z |
| 12:39:28–12:42:14 | ~160–163 min | **Quick self-test: the Kiyo streams fine.** W-MJPEG 640x360@60, 1280x720@30, 1920x1080@60 all MF/DS ok at about 30 fps. W-CYC quick: 18/18 ok on MF and DS; open→first frame MF 912–921 ms, DS 832–1603 ms; OpenCV 7.6–8.3 s | `suite_build_selftest_20261106/quick/suite_log.txt` lines 60-128; `quick/W-CYC.json` |
| 12:50:43–12:52:44 | 171–173 min | Quick W-KIYO: 13/13 MF and 13/13 DS control polls ok, exposure −4 | `quick/W-KIYO.json` polls |
| 13:19:41 | 200 min | Full run discovery: Kiyo SS, metadata_tier1 True, no dn_warn | `suite_log.txt` line 3; `W-ENV.json` `minutes_since_arrival` 199.3 |
| 13:19:58 | 200.6 min | W-CTRL-LIST: all 16 controls read fine through MF and DS (`iam_get` 0x00000000, exposure −4) | `W-CTRL-LIST/usb_video_device_1532-0e05_controls_{mf,ds}.json` `utc_started` 18:19:58Z |
| 13:19:58 → 13:43:39 | | No Kiyo access for 23.7 min (W-MJPEG runs the C922's modes) | `suite_log.txt` |
| **13:43:39.70** | **224.3 min** | **First Kiyo stream of the run: MF MJPG 640x360@5** (the first of its 28 modes; modes are sorted by size, then rate). enumerate 1.8 ms, activate 25 ms, SetCurrentMediaType ok, **first sample after 2170 ms** (a valid JPEG, strict decode ok). **No second frame** in the 3 s window (`frames` 1). `flush` ok, then **`reader_release` timed out at 5000 ms**; the watchdog killed wincam (exit 5, `abandoned_threads` 1) | `W-MJPEG.json` Kiyo `modes[0].apis.mf`; raw `mf_640x360_5/summary.json` `steps` |
| 13:43:49.9–13:44:00 | | PyAV DS, same mode: `av.open` did not return within the timeout (rc 5, 10.2 s) | `W-MJPEG.json` `modes[0].apis.pyav_ds.error` |
| 13:44:00–13:44:26 | | The other 27 modes: MF `first_sample` **0x8007001F** after 0.05–0.06 s; DS `open` **errno 5** after 0.5 s. 27/27 each | `W-MJPEG.json` (counted over `modes[*].apis`) |
| 14:18:12–14:19:22 | 259–260 min | W-CYC: 180/180 Kiyo cycles fail (MF 0x8007001F at first_sample; DS errno 5 at open; OpenCV isOpened False); 7/7 health probes fail | `W-CYC.json`; `suite_log.txt` lines 1122-1168 |
| 14:56:18–15:06:19 | 297–307 min | W-KIYO: 0/61 MF and 0/61 DS control polls answered, from the first poll (t = 0.45 s) | `W-KIYO.json` |
| End of run | | Devnode `0x0180600a`, problem code 0, no re-arrival of the Kiyo | `W-KIYO.json` `measurements.arrivals` |

### 4.2 Answers

- **Did it ever work in this run? Barely.**
  - The control plane worked at the start: the W-CTRL-LIST reads at 13:19:58, and format listing throughout.
  - Streaming produced exactly **one frame**, at 13:43:41.9, and then stopped. Nothing else succeeded. **Measured.**
- **What failed, and at which stage.**
  - At the onset: the stream stalled after its first frame, and the MF reader release hung.
  - After the onset, on every attempt:
    - MF: activate, reader creation and SetCurrentMediaType all succeed (`negotiated_ok` True in the rows), then the first `ReadSample` returns `0x8007001F` (ERROR_GEN_FAILURE) about 25 ms after activate. Close takes 1.2 ms.
    - DS (PyAV): `av.open` fails with `OSError(5)` after about 310 ms.
    - OpenCV: `isOpened()` is False after about 330 ms, with the warning "backend is generally available but can't be used to capture by index".
  - The control GETs fail as well (W-KIYO). **Measured.**
- **When, relative to plug-in age and the run.** The onset was at plug-in age 224 min, at the first stream start of the full run. It was not "a few minutes after plug-in", which is what REPORT.md (Constraints section) and PROGRESS.md line 31 say.
  - This session contradicts that claim: the Kiyo streamed at 160–163 min and answered controls at 171–200 min.
  - **Inferred:** in this session the trigger was tied to starting a stream, possibly the 5 fps mode, after a 24 min idle period, rather than to time since plug-in.
- **Device or harness? The device** (inferred, strongly supported):
  - **Timeouts are not the cause.** The healthy Kiyo needs about 0.9 s to its first frame on MF and 0.8–1.6 s on DS (quick self-test), well inside `TIMEOUT_MS` = 5000 (`w_cyc.py:39`), and 7.6–8.3 s on OpenCV, inside 15000 (`w_cyc.py:42`). After the onset every failure returned in 25–500 ms with a definite code. A longer timeout would not change any W-CYC cell.
    - The one timeout, the 5 s `reader_release` at the onset, came after the stream had already stalled: one frame in a 3 s window at 5 fps.
    - **Inferred:** the watchdog kill is unlikely to have caused the wedge, but it cannot be ruled out.
  - **The default mode is not the cause.** W-CYC used MJPG 1280x720@30 (`measurements.cameras.<kiyo>.mode`), the same mode that passed 4/4 MF and 4/4 DS cycles in the quick self-test.
  - **The 28 MJPG modes matter only through ordering.** W-MJPEG sorts modes so the full run starts with 640x360@5, while the quick run started with 640x360@60. The first full-run stream was therefore the lowest-rate mode.
    - **Inferred hypothesis:** a 5 fps stream leaves long idle gaps on the SuperSpeed link, where USB 3 LPM U1/U2 can engage. The power plan has USB 3 LPM at "Moderate power savings" and selective suspend Enabled (`W-KIYO.json` `measurements.power`), and the function shows `DeviceSelectiveSuspended` 1 (`function_device_parameters`). This matches the Linux NO_LPM quirk for this VID:PID (plan section 4).
  - **The SuperSpeed path is not the cause through bandwidth.** The Kiyo is alone on the Thunderbolt xHCI. The MF code is 0x8007001F, not the bandwidth refusal 0x800718CF. W-MJPEG streams one camera at a time.
  - **Possible confounder (inferred):** RazerAppEngine.exe was running (`W-ENV.json` processes.matches.razer).
- **Recovery.** 180 Kiyo cycles failed in W-CYC, and none of the 188 failure-to-next-cycle transitions recovered (`recovery_after_failure`: `recovered` 0 of `failures_followed`, summed over the 7 variants). The health probe after every variant failed. The suite never restarts devices, and on this machine a pnputil restart is vetoed by LogiTune/Razer anyway. **A physical replug is needed.**
  - A healthy devnode (problem code 0) did not mean a working device. A PnP-only health check cannot detect this state. **Measured.**

## 5. W-KIYO: the single "no" cell

- **What decided it.** `verdicts["kiyo|<kiyo>|all"]`, criterion "answers every control poll (MF and DS) during the window": `met` False, `detail.ok` = {mf: 0, ds: 0} of {mf: 61, ds: 61}. `first_failure` is poll 0 for both APIs (t = 0.45 s and 0.91 s, plug-in age 17814 s = 296.9 min). **Measured.**
- **Real or artefact.** The fact is real: the Kiyo answered no control GET. The measurement is an artefact: it cannot answer the plan's KIYO question of when and how the Kiyo stops answering.
  1. **W-KIYO runs last** (`run_suite.py:56-58`), 72 min after the onset found in W-MJPEG, so the "first failure" is just the first poll.
  2. **The reported code `0x80004002` (E_NOINTERFACE) is probably not what the device returned.**
     - The wincam initialiser sets every per-control HRESULT to E_NOINTERFACE (`wincam.cpp:1087`), and `iam_get` is assigned only when `IAMCameraControl/IAMVideoProcAmp::GetRange` succeeds (`wincam.cpp:1172-1183`).
     - In the healthy W-CTRL-LIST output, `ks_get` is 0x80004002 for all 14 IAM-read controls (never called on the listing path), and `iam_get` is 0x80004002 for pantilt and focal_length (never called, because GetRange failed with 0x80070490).
     - W-KIYO's `failed_get_hr` collects only `iam_get` (`w_kiyo.py:106`). The faulted polls therefore most likely mean "GetRange failed, so Get was never called". The real `iam_get_range` and `ks_get` codes, probably 0x8007001F, are not recorded. **Inferred** from the code; the per-control `hr` dict of the faulted polls was not saved.
  3. The polls themselves exit 0 with 16 controls "supported", and the "supported" flag survives the fault. Presumably KS BASICSUPPORT is answered from driver-cached descriptor data (inferred). So `supported` cannot be used as a health signal.
- **Prior results.** REPORT.md and PROGRESS.md say the Kiyo "stops answering EP0 a few minutes after each plug-in". This run and the quick self-test contradict "a few minutes": it answered at 171–200 min and failed at 224 min, at a stream start. The failure signature does match the earlier one: 0x8007001F on every API (mjpeg/RESULTS.md, "Earlier results marked invalid", 10-25 incidents).

## 6. MF vs DirectShow: open/close reliability (Dom's criterion)

- **Both pass "open/close/open/close consistently works" on all three healthy cameras.** **Measured:**
  - in one process: 50/50 per API per camera;
  - in a new process per cycle: 15/15;
  - alternating 1280x720 and 640x480: 25/25.
  - No failure, hang or unreleasable cycle in 540 healthy-camera MF+DS cycles.
- **Latency, measured (p50, open→first frame):**
  - MF: 98 ms (generic), 329 ms (C922), 481 ms (C930e).
  - DS (PyAV): 370, 585, 771 ms. That is MF + 255–290 ms on every camera; p95 shows the same gap.
  - New-process cycles add 3–42 ms to the open (p50 newproc − inproc). A whole MF process costs 1.5–1.8 s and a whole PyAV process 2.0–2.3 s (`process_elapsed_s` p50, which includes the `uv` start for PyAV).
- **Close, measured:**
  - MF 267–352 ms, almost all of it `reader_release_ms`;
  - DS 268–366 ms;
  - OpenCV 263–358 ms.
  - Close cost is about the same for all three; per camera, the close time follows the camera, not the API.
- **On a faulted device both fail fast and the same way every time; neither hangs** once the fault exists. MF's code (0x8007001F, class `device_error`) identifies the cause. DS's `OSError(5)` is ambiguous: the same errno is the plan's bandwidth-refusal signature (plan section 2.3), and `classify` leaves it as class `other`. **Measured.**
  - **Inferred:** MF gives the better diagnosis; DS needs the topology or an MF cross-check to tell a fault from a refusal.
- **At the onset both APIs hung**: MF in `reader_release` (>5 s), DS in `av.open` (>10 s). Both were bounded only by the harness watchdog. This supports the plan's safe pattern (a watchdog, or the async reader).
- **Format integrity differs.** MF negotiated MJPG on every MF cycle (`negotiated_ok` True). PyAV DS fell back to YUY2 on every 640x480 cycle of both Logitech cameras (12/25 cycles), because PyAV cannot force MJPEG. OpenCV CAP_DSHOW gave YUY2 at 10 fps on both Logitech cameras at 720p.
  - For skellycam this is the larger reliability difference: **DS opens and closes reliably, but does not reliably give the format that was asked for.**
- **Plan question "MF or DS?"** (inferred): on this evidence MF is at least as reliable as DS at open/close and is faster to the first frame. The statistical bound is weak (0.929 per 50-cycle cell; 0.986 pooled per API). Confirming ≥ 99% per camera needs about 300 or more failure-free cycles (n/(n+3.84) ≥ 0.99 means n ≥ 380).

## 7. Harness bugs and fixes

| # | File:line | Bug | Fix | Re-run | Severity |
| --- | --- | --- | --- | --- | --- |
| B1 | `suite/windows/tests/w_cyc.py:208-265` | No health probe **before** a camera's first variant. A camera that is already faulted (the Kiyo, since W-MJPEG) gets 7 per-API "no" cells with `replug_needed` True, which reads as if the API cycles caused the state | Probe each camera once before its variants (one MF frame, with the same `_health`). If it fails, mark the variants `untested: camera faulted before test (first failure <ts>, test <id>)`, or keep "no" with `cause: pre_existing_fault`; skip the 180 cycles | W-CYC (Kiyo) after a replug | high |
| B2 | `suite/windows/tests/w_kiyo.py:106` (plus `suite/windows/native/wincam.cpp:1087`) | `failed_get_hr` records only `iam_get`. When GetRange fails, that is wincam's "not called" default, E_NOINTERFACE 0x80004002, so the real `iam_get_range`/`ks_get` HRESULTs are lost and the report shows a misleading code. No raw controls JSON is saved | In `poll_once`, keep the full `hr` dict of each failing control (iam_get_range, iam_get, ks_basicsupport, ks_get) and save the wincam JSON to raw. In wincam, initialise the per-control HRESULTs to a "not called" sentinel (e.g. emit `null`) instead of E_NOINTERFACE | W-KIYO now (the Kiyo is presumably still faulted, so this captures the fault code), then again after a replug | high |
| B3 | `suite/windows/helpers/opencv_ds.py:165-167` | A cycle is `ok` when any frame of the right shape arrives. YUY2 instead of MJPG (`sets.got_fourcc`) and 10 fps instead of 30 (`fps_measured`) do not count. W-CYC (`w_cyc.py:249-250`) only lists the fourccs | Add `format_mismatch` (got_fourcc ≠ MJPG) and `fps_mismatch` (fps_measured < 0.9 × requested) to each row. Report their counts in the variant and in the verdict evidence; add a "negotiated what was asked" criterion | W-CYC opencv_inproc on C922, C930e, generic | medium |
| B4 | `suite/windows/tests/w_cyc.py:138-140` | Only skellycam's `create_cv2_video_capture` order (FOURCC first) is tested. skellycam's `opencv_apply_config.py:75-85` (size, fps, then FOURCC) and `CAP_PROP_BUFFERSIZE` are not modelled, although `--set-order size-first` exists | Add an `opencv_sizefirst` variant (`--set-order size-first`). Optionally set CAP_PROP_BUFFERSIZE as skellycam does | W-CYC opencv variants, 3 healthy cameras | medium |
| B5 | `suite/windows/tests/w_cyc.py:199, 274` | Arrivals are snapshotted only once around the whole test. The generic's re-arrival at 19:24:27Z (in opencv cycle 13) is reported only as a test-level `unexplained_re_arrival` and affects no verdict | Snapshot `LastArrivalDate` before and after each variant (cheap: enumeration only), and for OpenCV after each cycle. Attach the result to the variant; treat a re-arrival as a cycle failure ("device reset"), rated at most "partial" | W-CYC generic (opencv_inproc, then the other variants) | medium |
| B6 | `suite/windows/helpers/pyav_ds.py:26-28` + `suite/windows/tests/w_cyc.py:248` | `pyav_ds cycle` counts silent YUY2 fallbacks as ok. ds_modeswitch on the C922 and C930e rates "yes" with 12/25 rawvideo cycles | Count `format_fallback` rows as not meeting a "negotiated MJPEG" criterion, or run the DS cycles with `--engine ffmpeg` (`-vcodec mjpeg`). At least add `format_fallbacks` to the verdict evidence and summary | W-CYC ds_modeswitch, C922 and C930e | low |
| B7 | `suite/windows/run_suite.py:56-58` (order) + `suite/windows/tests/w_kiyo.py:121-149` | W-KIYO runs last and starts at whatever state earlier tests left; it cannot see the onset. No suite-wide record of the first Kiyo failure exists | Run W-KIYO immediately after discovery, or keep a background poll for the whole suite. Also have every test report the first Kiyo failure (timestamp, test, mode, code) into `run_suite.json` and the summary. Add `failed_from_first_poll` to the W-KIYO verdict | W-KIYO after a fresh replug (attended A4 for the LPM arm) | medium |
| B8 | `suite/common/rating.py:236-249` | The evidence in the reliability verdict omits `success_rate`/`n_ok`, so a "no" for latency (OpenCV: 15/15 opened) looks the same as a "no" for failure (Kiyo: 0/15) in summary.md | Add `n_ok`, `success_rate`, `wilson95` (open success) and `p50 open_to_first_frame_ms` to `ev`; have summary.md show "no (latency)" vs "no (failures)" | None (re-summarise only) | low |
| B9 | `suite/windows/tests/w_cyc.py:46-49` (counts) / plan section 3 | K = 50 cannot show ≥ 99% (Wilson lower bound 0.929 at 50/50) | Report pooled per-API bounds; for a claim about each camera, raise K to about 300 or more on one camera per API overnight | W-CYC (long, optional) | low |
| B10 (cross-group, W-MJPEG) | `suite/windows/capkit.py:96` (`mjpeg_modes` sorts by area, then width, then fps; `w_mjpeg.py:42,115` sweeps in that order) | The Kiyo's first stream is its 5 fps mode, which may be the trigger. Also, the Kiyo G-MJPEG cells are "partial" with 0/28 negotiated (`W-MJPEG.json` verdicts) when they should be "no" | For the Kiyo, sweep the default mode first, then the rest, and log the onset. Fix the G-MJPEG rating so that 0 modes negotiated gives "no" | W-MJPEG Kiyo after a replug | medium (for the G-MJPEG group) |

### 7.1 What must be re-run, and what each re-run needs

- **Now, with no replug:**
  - W-KIYO, after B2, to record the real faulted-state HRESULTs.
  - W-CYC opencv variants on the C922, C930e and generic, after B3, B4 and B5, to confirm the YUY2/10 fps result and the generic re-enumeration and to test the size-first order.
- **After a physical replug of the Kiyo:**
  - W-KIYO first, from plug-in age about 0, polling for at least 60 min.
  - Then W-CYC on the Kiyo only (MF, DS, OpenCV, at 720p30).
  - Then W-MJPEG on the Kiyo with 640x360@5 first, and then with it last, to test the low-rate-trigger hypothesis.
  - Attended A4: the same with USB 3 LPM Off, or with the Kiyo on a USB 2.0 port.

## Verifier notes

Adversarial check, 2026-11-06. Every number above was recomputed with scripts from `W-CYC.json`, `W-CYC/<cam>/<variant>_cycles.json`, `W-KIYO.json`, `W-MJPEG.json`, `W-CTRL-LIST/*.json`, `W-ENV.json`, `W-MULTI.json`, `suite_log.txt`, the raw W-MJPEG Kiyo `mf_640x360_5/summary.json` and `pyav_ds_640x360_5/summary.json`, the raw W-CYC `*/mf_inproc/summary.json` (`pid`), and `../suite_build_selftest_20261106/quick/`. I read the code each bug claim cites, plus skellycam's `create_cv2_video_capture.py` and `opencv_apply_config.py`. No camera was opened. No suite or result file was changed apart from this appended section.

### V1. What holds (confirmed by recomputation)

- **The table in 2.2 and the 28 ratings.** Every n_ok, Wilson interval, p50/p95/max, failure class, recovery count, `format_fallbacks` and `replug_suspected` value matches `W-CYC.json`. The suite log reports `ratings {'yes': 18, 'no': 10}`.
- **The criteria.** The healthy-camera OpenCV cells fail only criterion 0 (`first_frame_within_rate` 0.0). The Kiyo cells fail criteria 0 and 2 (replug). **Measured.**
- **Pooled bound.** 270/270 per API gives a Wilson lower bound of 0.986.
- **MF − DS p50 gap:** 256 ms (C922), 272 ms (generic), 290 ms (C930e).
- **New process minus in-process p50:** MF 3.0 / 16.5 / 42.4 ms and DS 28.3 / 26.5 / 31.0 ms. Process p50: MF 1.53–1.83 s, PyAV 1.97–2.28 s.
- **Close.** `reader_release_ms` p50 is 265–350 ms and accounts for almost all of the MF close.
- **ds_modeswitch fallbacks.** On the C922 and the C930e, cycles 1, 3, …, 23 (12/25, every 640x480 cycle) have `codec` rawvideo and `frames_ok` 0. The generic camera has none. MF has `negotiated_ok` True on every row, the Kiyo's included.
- **OpenCV rows.** The C922 and C930e are YUY2 1280x720 with `fps_measured` 10.0 in 15/15 cycles, with all four sets True and `got_fps` 30. On the generic camera, cycles 0 and 13 are YUY2 640x480 with `sets.h` False and `set_ms` 11366 / 11348.
- **Recovery.** 0 of 188 failure-to-next-cycle transitions recovered (49+14+49+14+14+24+24).
- **Kiyo failure timings** (`timings_ms_all_cycles`): MF `activate_ms` p50 22.5 ms, DS `open_ms` p50 311 / 336 / 308 ms, OpenCV `open_ms` p50 329 ms.
- **No suite access to the Kiyo before the onset.** Between 13:19:59 and 13:43:39 local, no suite command names the Kiyo (`suite_log.txt` lines 42–504 touch only the C922).
- **W-MJPEG Kiyo counts.** 27/27 MF modes failed at `first_sample` with 0x8007001F, and 27/27 DS modes at `open` with errno 5.
- **Devnode.** It stayed 0x0180600a with problem code 0 and no re-arrival.
- **REPORT.md:138 and PROGRESS.md:31** do say "a few minutes after each plug-in", which this session contradicts.

### V2. Corrections

1. **Onset (F8 and the 4.1 timeline).**
   - wincam was not killed by a watchdog. Its own per-call timeout made it exit by itself (`exit_code` 5, `abandoned_threads` 1), with the `reader_release` thread still stuck. W-MJPEG `mf.timed_out` is False, so timed_run did not intervene.
   - The MF summary also shows `stream_ticks` 1 and `null_samples` 1. After its one frame, the source signalled a gap. **Measured.**
   - PyAV's `av.open` did not "hang for 10.2 s". It hit its 5.0 s bound (`timeout_ms` 5000; the tool ran from 18:43:50.31 to 18:43:56.31Z). The 10.2 s is the wall time of the whole camcmd, including uv start and teardown. Read "DS in av.open (>10 s)" in section 6 as **≥ 5 s**.
2. **The quick self-test did not show a healthy DirectShow MJPEG stream on the Kiyo (F10, F11, 4.1 row 12:39).**
   - Every Kiyo PyAV-DS cycle in `quick/W-CYC.json` was a format fallback: ds_inproc 4/4, ds_newproc 2/2, ds_modeswitch 2/2.
   - In `quick/W-MJPEG.json`, `pyav_ds` has `ok` False and `format_fallback` True in all 3 Kiyo modes. Only `ffmpeg_ds` (the ffmpeg CLI with `-vcodec mjpeg`) delivered MJPEG.
   - So "all MF/DS ok" and "DS 0.83–1.6 s" describe non-MJPEG streams. "720p30 worked in the self-test" holds for MF only.
   - Even on a healthy Kiyo, W-CYC's DS cells would have rated "yes" on fallback streams. B6 therefore applies to the Kiyo at its default mode too, not only to the Logitech cameras at 640x480.
3. **The generic camera's re-arrival (F6).**
   - The timing is exact. Cycle 13 starts at 19:24:15.903Z (row `utc` is taken before the open, `opencv_ds.py:96`). Its set phase runs from about 19:24:16.21 to 19:24:27.56Z. The re-arrival at 19:24:27.05Z falls inside it, and `sets.h` is False.
   - But this camera also re-arrived at **18:17:09Z**. The quick self-test's `discovery.json` has its `last_arrival` as 17:32:01Z, so this was between the self-test and the full run's start (the full run's `before` snapshot shows 18:17:09Z). It re-arrived again at 19:44:44Z in W-MULTI (`W-MULTI.json` `arrivals.changes`), where OpenCV is not used. That makes 3 re-arrivals in about 2.5 h, at least one of them without OpenCV.
   - The direction of cause is therefore open (**inferred**). A spontaneous device reset during the set would explain the 11 s set, the failed height set, and the fall-back to the pin default 640x480 YUY2 just as well as "OpenCV's rebuild reset the device" does. Cycle 0 shows the same signature and probably re-arrived as well, but only the last arrival is recorded.
   - The 18:17:09Z event is not in the brief's health summary. It may have been a manual replug; that is unknown.
4. **"skellycam's set order gives YUY2 at 10 fps" (F5, section 3, section 6) overstates what was measured.**
   - skellycam's real open does both sequences, one after the other:
     - `create_cv2_video_capture.py:53-58`: FOURCC, W, H, FPS, then `CAP_PROP_BUFFERSIZE` = 1 (`:62`), then `read()` (`:71`);
     - then `apply_camera_configuration(prior_config=None)` (`:84`). That sets exposure, then W and H (`opencv_apply_config.py:75-76`), skips FPS (`should_apply_framerate = False`, `:62`), and sets FOURCC last (`:83-85`).
   - The harness models only the first block. The measured result is "after skellycam's create-step sets, before its apply step, the Logitech cameras are in YUY2 at 10 fps". skellycam's final format is untested: the FOURCC-last apply step may restore MJPG at 30 fps.
   - The section 3 description of `opencv_apply_config` as "size, then fps, then FOURCC" is wrong: fps is disabled.
5. **The opencv_ds `ok` (B3) does not check the frame shape at all.** `opencv_ds.py:167` is `ok = stage_failed is None and frames >= 1`. `size_mismatch` (`:165-166`) is only a flag. Generic cycles 0 and 13 are `ok: True` with `size_mismatch: True` (the tool summary has `size_mismatches` 2). The bug covers size as well as FOURCC and fps.
6. **Cycle count for a ≥ 99% claim (F16, B9).** With all cycles passing, the Wilson lower bound is n/(n+3.8416). It reaches 0.99 at **n ≥ 381** (380 gives 0.98999). The text also says "about 300 or more" in section 6 and in B9; both should read 381.
7. **MF timing on the Kiyo.** ReadSample does not fail "about 25 ms after activate". Activate itself takes about 22–25 ms. Reader creation (0.8 ms) and SetCurrentMediaType (0.5 ms) follow, and the first ReadSample fails within a few ms. The whole failed cycle takes about 30 ms, and the health process 62 ms.
8. **The `plug_in_age_at_start_s` field in W-KIYO is the age at the end of polling.** It reads 18415 s (306.9 min) because `w_kiyo.py:160` calls `_age_s()` (wall clock now) after the 10-minute loop. The first poll's `plug_in_age_s` is 17814 s (296.9 min). The text uses the right value (296.9); the field is mislabelled (new bug N1).

### V3. Real-or-artefact calls

- **18 "yes" cells: real.** The caveats stand. Add that the ds_modeswitch latency p50 on the C922 and C930e mixes MJPEG and YUY2 cycles.
- **3 OpenCV "no" cells on healthy cameras: real API latency, with a weaker attribution.**
  - The 2 s from the open start is what the plan specifies, so the rating is not a threshold artefact.
  - "skellycam behaviour" is only half modelled (V2.4). The real skellycam open adds BUFFERSIZE before the first read and three or more graph-rebuilding sets after it. The time to the configured stream is longer than W-CYC measures.
- **7 Kiyo W-CYC "no" cells: mixed, agreed.** The device fault is real and pre-existing. The per-API attribution is an artefact.
  - **New, measured confounder:** `RazerAppEngine.exe` (pid 37240, `W-ENV.json` `processes.matches.razer`) held an open, non-streaming camera session on the Kiyo during W-CYC. See the Kiyo `mf_inproc` row `activity_pids`: [3296 LogiTuneAgent, 37240 RazerAppEngine, 50356]. 50356 is wincam itself (raw summary `pid`).
  - On the healthy cameras, only LogiTuneAgent plus wincam appear.
  - So Razer software was not just running: it was attached to the Kiyo. Vendor software sending control requests is a candidate trigger at least as plausible as the LPM hypothesis (**inferred**). It is not known whether it was attached at the onset, because W-MJPEG does not record `activity_pids` (`controls_before` is empty).
- **W-KIYO "no": real, agreed.** Refinement: cc.focal_length is missing from `first_failure.*.controls_with_failed_get` while the controls on both sides of it in list order are present. Its KS GET therefore still succeeded on the faulted device (focal length is descriptor data, so the driver answers it without the device; **inferred**). "Answered no control GET" should read "answered no device-backed control GET".
  - The 0x80004002 inference holds, and more strongly. pantilt has `iam_get` 0x80004002 even when healthy (GetRange 0x80070490 in W-CTRL-LIST), so that code appears in `failed_get_hr` whenever pantilt fails. If GetRange had succeeded on any IAM control and Get had then failed, that control's real code would also be in the set, and none is.

### V4. The claimed harness bugs

| # | Verdict | Note |
| --- | --- | --- |
| B1 | real | Fix correct. `rate_reliability` (`rating.py:225-249`) also needs a `pre_existing_fault` → untested/no path. The pre-probe should be one short MF capture, and its result should go into the verdict. |
| B2 | real | `wincam.cpp:1087` sets every per-control HRESULT to E_NOINTERFACE, confirmed. Extend it: `w_kiyo.py:105-106` also truncates `controls_with_failed_get[:10]` and `failed_get_hr[:5]`, so the number of failing controls is unknown. Save the full `hr` dict and `via` per control. With a null sentinel, `w_kiyo.py:97-98` still treats null as not-ok, which is correct. |
| B3 | real, mis-described | `ok` ignores the shape too (V2.5). Fix: `ok_as_requested = not size_mismatch and got_fourcc == MJPG and fps_measured ≥ 0.9 × requested`, counted per variant and in the verdict. |
| B4 | real, wrong fix | A size-first variant is not skellycam either. Model the full sequence: an `--set-order skellycam-full` that does the create sets, BUFFERSIZE, `read()`, then exposure, W, H, FOURCC. Record the fourcc and fps after the apply step, and the time to the first frame after it. |
| B5 | real | Fix fine. Also snapshot arrivals at suite start against the previous run or self-test, which would have caught 18:17:09Z. |
| B6 | real | The Kiyo also falls back at 720p30 through PyAV (V2.2), so this is not low severity for the Kiyo. Use `--engine ffmpeg` for the DS cycles, or rate fallback cycles as failing. |
| B7 | real | Agreed. Also record `activity_pids` at the onset (see N3). |
| B8 | real | Agreed. |
| B9 | methodology, not a bug | Use n ≥ 381. |
| B10 | plausible (cross-group) | The sort at `capkit.py:96` (area, width, fps ascending) is confirmed. Whether the G-MJPEG rule should give "no" is for the W-MJPEG verifier. Note that W-MJPEG's `negotiated` is False for MF mode 0 although `readback_ok` is True, so "0/28 negotiated" means "0/28 streamed". |

### V5. New harness bugs

- **N1** `suite/windows/tests/w_kiyo.py:160`: `plug_in_age_at_start_s` is computed after the poll loop, so it reports the age at the end. Fix: compute it before the loop (at line 128). Re-run: none (re-summarise only).
- **N2** `suite/windows/tests/w_kiyo.py:105-106`: the `[:10]` and `[:5]` truncation hide which controls failed and which answered (focal_length). Fix: keep the full list and the per-control `hr` dict. Re-run: W-KIYO.
- **N3** `suite/windows/helpers/capkit.py` / `w_mjpeg.py`: other processes attached to the camera (`activity_pids`) are recorded only in wincam cycle rows. They are not in captures or W-KIYO polls, so the Razer attachment at the onset cannot be checked. Fix: log `activity_pids` with every Kiyo capture and poll. Re-run: W-MJPEG and W-KIYO on the Kiyo after a replug, with and without RazerAppEngine running.
- **N4** `suite/common/cycstats.py:73-74`: `timings_ms_all_cycles` takes percentiles over wincam's −1 sentinels (the Kiyo's `first_frame_ms` and `open_to_first_frame_ms` have p50 −1). Fix: drop negative values. Low; re-summarise only.
- **N5** `suite/windows/helpers/opencv_ds.py:115-121`: the harness does not model skellycam's full open (V2.4). This is the fix for B4.

### V6. Re-runs, revised

- **Now, no replug:**
  - W-KIYO after B2 and N2, to capture the real faulted-state codes.
  - W-CYC OpenCV on the 3 healthy cameras after B3 and N5.
  - The generic camera with per-cycle arrival snapshots (B5), to settle the cause of the re-arrival.
- **After a Kiyo replug:**
  - As in 7.1, but run each arm twice: once with Razer Synapse (RazerAppEngine) closed and once with it running. Log `activity_pids`.
  - DS cycles on the Kiyo through `--engine ffmpeg`, so they measure MJPEG.
