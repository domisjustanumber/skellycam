# W-CYC analysis: suite run 20261106T224912Z on Gerald (run 2)

Scope: the 32 `reliability` cells in [summary.md](../summary.md), which are 4 cameras x 8 variants. Sources:

- [W-CYC.json](../W-CYC.json): `verdicts`, and per camera `measurements.cameras.<key>` with `variants.<v>.summary`, `.info.tool_summary`, `.final`, `.re_arrival`, `activity_at_first_stream`, `pre_probe` and `exposure_restore`.
- The per-cycle rows in `W-CYC/<camera>/<variant>_cycles.json`.
- The raw tool output under `C:/Users/Dom/Documents/skellycam-raw/results/windows/Gerald/suite_20261106T224912Z/W-CYC/` (`cycles.jsonl`, and `p*/summary.json` for the new-process variants).
- [suite_log.txt](../suite_log.txt) lines 108-398, and the [W-KIYO.json](../W-KIYO.json) polls in the W-CYC window.
- The W-FMT listings, for which formats each camera advertises.

For comparison: run 1 at `../../suite_20261106T181941Z/` (`analysis/cyc_kiyo.md` and `reanalysis/W-CYC.json`), plus skellycam's own source.

No camera was opened, and no suite code or result file was changed.

Labels: **measured** = read from the named file and field. **derived** = computed from measured fields, with the method stated. **inferred** = interpretation.

Times: local is UTC-5. W-CYC ran 17:52:17-18:36:47 local (22:52:17Z-23:36:47Z).

## 1. Summary

- **All 1,080 W-CYC cycles opened, delivered a first frame and closed.** That is 4 cameras x (90 MF + 90 PyAV-DS + 30 OpenCV). There were no failures, hangs, unreleasable readers, recoveries needed, device resets or re-arrivals. **Measured:** every `summary.n_ok == n`, `hangs` 0, `unreleasable` 0, `device_reset_count` 0, `re_arrival` null, and `measurements.arrivals.changes` [].
- **Ratings: 21 yes, 3 partial (format mismatch), 8 no (latency).** The suite log line 398 agrees.
  - The 3 partials are all the Kiyo's PyAV-DS variants. They opened and closed in 90/90 cycles, but every cycle was YUY2, not MJPEG.
  - The 8 "no" are all the OpenCV variants. They opened in 120/120 cycles, but 0/120 reached the first frame within 2 s.
- **The Kiyo cycled cleanly this time.**
  - **Measured:** MF 90/90 in MJPEG at about 29.7 fps, PyAV-DS 90/90 opened (all YUY2), OpenCV 30/30. The 1-frame MF pre-probe was ok (913 ms), and its 34/34 W-KIYO control polls between 23:04Z and 23:19Z were answered.
  - Its variants ran from 23:01:19Z to 23:16:45Z, at plug-in age 148.8-164.3 min.
  - It faulted 47 min later, in W-MULTI: the first unanswered poll was at 210.5 min and 0x8007001F at 211.6 min.
  - So W-CYC did not trigger the fault directly (**inferred**).
- **skellycam's real OpenCV open sequence ends in MJPG 1280x720 at about 30 fps on the three cameras that can do it, and the generic camera's measured rate is also normal for it.** **Measured** in `variants.opencv_skellycam.final`:
  - C922: 30.0 fps after 4.76 s.
  - C930e: 30.2 fps after 6.39 s.
  - Kiyo: 29.8 fps after 11.50 s.
  - Generic: 25.7 fps after 2.71 s, the only one under 30.
  - The create step alone leaves the C922 and C930e in **YUY2 at 10 fps** and the Kiyo in **YUY2 at 22.6 fps**. Only the FOURCC set at the end of the apply step brings MJPG back. Run 1 could not say this (its V2.4 was open).
  - `CAP_PROP_BUFFERSIZE = 1` is refused by CAP_DSHOW on every camera.
  - Caveat: the harness gives skellycam framerate = 30, but skellycam's default config uses -1, which skips the FPS set (bug H5).
- **MF vs DirectShow (Dom's criterion: open/close/open/close works every time):**
  - **Both pass open/close on all four cameras.** MF 360/360, DS 360/360. The pooled Wilson 95% lower bound is 0.989 per API this run. With run 1's healthy cameras, MF is 630/630 with a lower bound of 0.994.
  - **MF wins on format and on latency:**
    - MF negotiated MJPG in 360/360 cycles. DS delivered MJPEG in only 270/360 (Wilson 0.70-0.79): every Kiyo cycle came out as YUY2, because PyAV cannot force MJPEG.
    - Where both give MJPEG, MF is 262-294 ms faster to the first frame.
  - Close cost is set by the camera, not by the API.
- **A real camera finding the harness does not surface: the generic 4c4a delivered only about 17.1 fps at "MJPG 1280x720@30" through MF and DS.** Its four MF/DS cells still say "yes", with `fps_mismatch_count` 0, because W-CYC checks fps only for OpenCV (bug H1).
  - **Measured:** `fps_measured` 17.1 in the mf_newproc and ds_newproc raw summaries and in the ds_inproc rows. **Derived:** 17.1 fps for mf_inproc, from the row timestamps.
  - In run 1 (daytime) the same camera gave 25.5 fps. The likely cause is auto exposure in the evening light (**inferred**).

## 2. How each cell is rated

`w_cyc.py:404-457` (`rate_variant`) wraps `common/rating.py:394-465` (`rate_reliability`). The rating is applied to `cycstats.summarize_cycles(rows)` after `_norm_rows` (`w_cyc.py:144-179`).

| Criterion (`verdicts[...].criteria[i]`) | JSON field | Effect |
| --- | --- | --- |
| 0: ≥ 99% of cycles deliver a first frame within 2 s | `evidence.first_frame_within_rate` (row `ok` and `open_to_first_frame_ms` ≤ 2000; `first_frame_ms` is overwritten with `open_to_first_frame_ms`, `w_cyc.py:155-156`) | < 0.95 gives **no**. The label is "no (latency)" when `success_rate` ≥ 0.95 (`rating.py:445-446`) |
| 1: no hang beyond the watchdog | `evidence.hangs`, `evidence.unreleasable` | any gives partial or no |
| 2: no state that needs a replug | `evidence.replug_needed` (= `variants.<v>.replug_suspected`; a health capture runs only after trailing failures, `w_cyc.py:629-634`) | True gives **no (replug needed)** |
| 3: negotiated the requested format | `evidence.format_mismatch_count` + `size_mismatch_count` (**fps is not counted**, `rating.py:428`) | > 0 caps at **partial (format mismatch)** |
| 4: no device reset (re-enumeration) | `evidence.device_reset_count`; unattributed re-arrival | > 0 caps at partial |

How a row is judged `format_mismatch`:

- **MF:** `negotiated_ok` is False.
- **DS:** `format_fallback` is set, or `codec` is not mjpeg.
- **OpenCV:** the FOURCC read back after the last set is not MJPG (`w_cyc.py:118-141`, `opencv_ds.py:247-264`).

## 3. Every cell

### 3.1 Table (measured)

Sources:

- `summary.n_ok/n` and `wilson95`.
- `n_first_frame_within/n` and `first_frame_within_wilson95`.
- `timings_ms.open_to_first_frame_ms` and `timings_ms.close_ms` (p50 / p95 / max).
- `format_mismatch_count`, `fps_mismatch_count`.
- Delivered fps: from the row `fps_measured` (DS, OpenCV), from the raw `p*/summary.json` `fps_measured` (newproc), or **derived** for MF in-process as 29 frames / (Δutc − 100 ms gap − open→first − close).
- The rating from `verdicts["reliability|<key>|<v>"]`.

Failures, recovery, health-after and re-arrivals were none or null in every cell.

| Camera | Variant | Rating | open+frame+close ok (Wilson 95%) | first frame ≤ 2 s | open→first frame ms p50/p95/max | close ms p50/p95/max | fmt / fps mismatch | delivered |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C922 | mf_inproc | yes | 50/50 (0.929-1) | 50/50 | 327/337/339 | 356/360/360 | 0/0 | MJPG 30.2 (derived) |
| C922 | mf_newproc | yes | 15/15 (0.796-1) | 15/15 | 330/332/333 | 355/359/359 | 0/0 | MJPG 30.2 |
| C922 | ds_inproc | yes | 50/50 (0.929-1) | 50/50 | 593/609/618 | 349/361/363 | 0/0 | mjpeg 30.2 |
| C922 | ds_newproc | yes | 15/15 (0.796-1) | 15/15 | 616/629/638 | 349/356/361 | 0/0 | 29.9 |
| C922 | opencv_inproc | **no (latency)** | 15/15 (0.796-1) | 0/15 (0-0.204) | 3047/3069/3074 | 332/340/341 | 15/15 | **YUY2 10.0** |
| C922 | opencv_skellycam | **no (latency)** | 15/15 | 0/15 | 4758/4795/4796 | 345/356/359 | 0/0 | MJPG 30.0 |
| C922 | mf_modeswitch | yes | 25/25 (0.867-1) | 25/25 | 331/337/339 | 356/361/366 | 0/0 | 720p and 1080p 30.2 (derived) |
| C922 | ds_modeswitch | yes | 25/25 (0.867-1) | 25/25 | 591/603/619 | 349/358/359 | 0/0 | mjpeg 29.7-29.8 |
| Kiyo | mf_inproc | yes | 50/50 | 50/50 | 910/920/924 | **1117/1320/1422** | 0/0 | MJPG 29.7 (derived) |
| Kiyo | mf_newproc | yes | 15/15 | 15/15 | 914/916/916 | 1022/1345/1411 | 0/0 | MJPG 29.7 |
| Kiyo | ds_inproc | **partial** | 50/50 | 50/50 | 821/838/849 | 939/1041/1146 | **50**/0 | **YUY2 (rawvideo) 22.4** |
| Kiyo | ds_newproc | **partial** | 15/15 | 15/15 | 855/863/863 | 936/1069/1136 | **15**/0 | YUY2 22.4 |
| Kiyo | opencv_inproc | **no (latency)** | 15/15 | 0/15 | 7449/7722/7880 | 913/1028/1101 | 15/15 | **YUY2 22.6** |
| Kiyo | opencv_skellycam | **no (latency)** | 15/15 | 0/15 | 11497/11729/11808 | 995/1183/1187 | 0/0 | MJPG 29.8 |
| Kiyo | mf_modeswitch | yes | 25/25 | 25/25 | 918/957/958 | 1089/1270/1412 | 0/0 | 29.7 / 30.2 (derived) |
| Kiyo | ds_modeswitch | **partial** | 25/25 | 25/25 | 827/844/853 | 927/1020/1137 | **25**/0 | YUY2 22.4 |
| generic | mf_inproc | yes | 50/50 | 50/50 | 98/111/209 | 270/275/278 | 0/0 (fps not judged) | **MJPG 17.1** (derived) |
| generic | mf_newproc | yes | 15/15 | 15/15 | 100/131/132 | 266/271/272 | 0/0 (not judged) | **17.1** (raw `fps_measured`) |
| generic | ds_inproc | yes | 50/50 | 50/50 | 392/474/516 | 267/272/277 | 0/0 (not judged) | **mjpeg 17.1** |
| generic | ds_newproc | yes | 15/15 | 15/15 | 414/1253/1303 | 267/578/798 | 0/0 (not judged) | **17.1** |
| generic | opencv_inproc | **no (latency)** | 15/15 | 0/15 | 2086/2111/2145 | 263/268/270 | 0/**15** | MJPG 17.2 |
| generic | opencv_skellycam | **no (latency)** | 15/15 | 0/15 | 2705/4256/6583 | 264/266/267 | 0/**15** | MJPG 25.7 |
| generic | mf_modeswitch | yes | 25/25 | 25/25 | 111/226/432 | 264/446/588 | 0/0 | 17.1-17.2 (derived) |
| generic | ds_modeswitch | yes | 25/25 | 25/25 | 392/505/507 | 268/273/277 | 0/0 | mjpeg 17.1 |
| C930e | mf_inproc | yes | 50/50 | 50/50 | 511/517/521 | 360/396/398 | 0/0 | MJPG 29.7 (derived) |
| C930e | mf_newproc | yes | 15/15 | 15/15 | 515/517/518 | 353/394/394 | 0/0 | 29.7 |
| C930e | ds_inproc | yes | 50/50 | 50/50 | 773/909/1588 | 369/447/590 | 0/0 | mjpeg 30.2 |
| C930e | ds_newproc | yes | 15/15 | 15/15 | 808/822/828 | 366/405/406 | 0/0 | 30.3 |
| C930e | opencv_inproc | **no (latency)** | 15/15 | 0/15 | 4245/4296/4312 | 340/371/372 | 15/15 | **YUY2 10.0** |
| C930e | opencv_skellycam | **no (latency)** | 15/15 | 0/15 | 6388/6495/6524 | 363/394/395 | 0/0 | MJPG 30.2 |
| C930e | mf_modeswitch | yes | 25/25 | 25/25 | 513/516/518 | 388/396/400 | 0/0 | 29.7 (derived) |
| C930e | ds_modeswitch | yes | 25/25 | 25/25 | 787/815/840 | 366/402/408 | 0/0 | mjpeg 30.2 |

Further measured timings:

- **MF `activate_ms` p50:** 21-27 ms on the C922, Kiyo and generic; 34-38 ms on the C930e.
- **MF close** is almost all `reader_release_ms`.
- **DS:** `open_ms` equals open→first frame, because `av.open` probes the stream.
- **Process wall time p50:** MF newproc 1.66 s (C922) / 2.94 s (Kiyo) / 2.08 s (generic) / 1.88 s (C930e). PyAV newproc 2.11 / 3.27 / 2.55 / 2.33 s, which includes `uv` start-up.
- **Mode switching:** latency barely differs by mode (MF 720p vs 1080p within 1-4 ms on the C922 and C930e; Kiyo 914 vs 955 ms).
- **Generic camera:** MF open→first frame is bimodal, about 100 ms or about 210 ms. That is about 2 vs 4 frame periods at 17 fps (**inferred**).

### 3.2 Why each group of cells has its rating

| Cells | Deciding criterion (field) | Real or artefact |
| --- | --- | --- |
| **21 yes**: MF x 3 variants on all 4 cameras (12); DS x 3 variants on the C922, generic and C930e (9) | crit 0 `first_frame_within_rate` 1.0; crit 1 `hangs` 0 / `unreleasable` 0; crit 2 `replug_needed` False (no failures, so no probe was needed); crit 3 `format_mismatch_count` 0 (MF `negotiated_ok` True in every row; DS `codec` mjpeg / `format_fallback` False); crit 4 `device_reset_count` 0 | **Real** for the plan's criterion (section 3: first frame within 2 s, no hang, no replug; format and fps are not part of it). Caveats: (a) n = 15-50 per cell, so the Wilson lower bounds are 0.796-0.929; "yes" is a point estimate. (b) The **generic camera's 6 MF/DS "yes" cells hide 17.1 fps delivered at "@30"**: `fps_mismatch_count` 0 means "not judged", not "ok" (bug H1). The fps is outside the plan's reliability criterion, so the rating itself stands. (c) ds_newproc `codec` is None in all 60 rows (bug H2). The format check there rests on `format_fallback` alone, which happened to be enough. |
| **3 partial (format mismatch)**: Kiyo ds_inproc / ds_newproc / ds_modeswitch | crit 3 met False: `format_mismatch_count` 50/15/25 (rows `codec` rawvideo, `pix_fmt` yuyv422, `format_fallback` True, `frames_ok` 0). Crit 0 = 1.0 | **Real, for PyAV.** PyAV's `vcodec=mjpeg` is ignored (`pyav_ds.py:25-33`), so dshow took the first caps match, YUY2 1280x720 (the Kiyo advertises YUY2 720p up to 60 fps in `W-FMT/usb_video_device_1532-0e05_formats_ds.json`). Open/close itself was 90/90. **It does not show that DirectShow cannot give the Kiyo MJPEG:** the ffmpeg-CLI route (`-vcodec mjpeg`) did deliver MJPEG on the Kiyo in the run 1 self-test (run 1 V2.2). W-CYC never runs that engine (bug H8). |
| **4 no (latency)**: opencv_inproc on all 4 cameras | crit 0 = 0.0 (`n_first_frame_within` 0/15), `success_rate` 1.0, so "latency". Crit 3 is also False on the C922, Kiyo and C930e (`format_mismatch_count` 15, final FOURCC YUY2) | **Real** API behaviour. `VideoCapture()` takes 0.31-0.75 s and the four `cap.set()` calls take 1.68-6.63 s (`set_ms` p50: generic 1678, C922 2300, C930e 3280, Kiyo 6631). No call came near the 15 s bound, and `hangs` is 0. The summary label shows only "latency" and hides the YUY2 10 fps result (bug H7). |
| **4 no (latency)**: opencv_skellycam on all 4 | crit 0 = 0.0, `success_rate` 1.0. Crit 3 met True (final FOURCC MJPG). On the generic camera `fps_mismatch_count` is 15 (25.7 fps) but does not count toward crit 3 | **Real** for the modelled sequence. The first configured frame arrives after open + create sets + read + apply (section 4). One modelling difference from skellycam's default config (bug H5). |

## 4. What skellycam's real OpenCV open ends up with (opencv_skellycam)

**Measured** from the rows `W-CYC/<cam>/opencv_skellycam_cycles.json` (p50 over 15 cycles) and `variants.opencv_skellycam.final`:

| Camera | `VideoCapture()` | create sets (FOURCC, W, H, FPS, BUFFERSIZE) | create read | after the create step | apply (exposure, W, H, FOURCC) | open → first configured frame | final format | fps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C922 | 456 ms | 2299 ms | 281 ms | **YUY2** 1280x720 (`sets.got_fourcc`), 3.04 s | 1580 ms | **4758 ms** | MJPG 1280x720 | 30.0 |
| C930e | 743 | 3272 | 215 | **YUY2**, 4.24 s | 2139 | **6388** | MJPG 1280x720 | 30.2 |
| Kiyo | 564 | 6549 | 264 | **YUY2**, 7.41 s | 3500 | **11497** | MJPG 1280x720 | 29.8 |
| generic | 318 | 1708 | 59 | MJPG, 2.08 s | 561 | **2705** | MJPG 1280x720 | **25.7** |

Notes:

- **The order of sets decides the format.** With FOURCC set first and then W/H/FPS (the create step), the C922, C930e and Kiyo end in YUY2. Their YUY2 720p rates are 10, 10 and 22.6 fps.
  - **Measured:** opencv_inproc `fps_measured`. Also from W-FMT: the C922 and C930e advertise YUY2 1280x720 only up to 10 fps.
  - skellycam's apply step sets FOURCC last, and that is what produces MJPG at 30 fps. **Measured:** `apply.got_fourcc` MJPG, `fps_measured` 29.8-30.2.
  - This settles run 1's open question V2.4: skellycam's final format is right, and it pays a second graph rebuild for it.
- **`CAP_PROP_BUFFERSIZE = 1` is a no-op on CAP_DSHOW.** On all 4 cameras `sets.buffersize` is False and `got_buffersize` is -1 (**measured**). skellycam logs this only at debug level (`create_cv2_video_capture.py:61-65`).
- **The exposure set does not always take.** `apply.got_exposure` is -7 on the C922, Kiyo and generic, but **-5 (unchanged) on the C930e**, even though both `set()` calls returned True (**measured**). The cause is not determined.
  - `exposure_restore.restored` is True for all 4 cameras. Each original was auto, and auto was restored (`w_cyc.py:317-331`).
- **Latency.** No camera reaches 2 s. Under this sequence a skellycam user waits 2.7 s (generic) to 11.5 s (Kiyo) per camera before the first configured frame.
  - The Kiyo's sets are about 1.6 s each, and its close is about 1 s.
  - With skellycam's default `framerate = -1` (`skellycam/core/camera/config/camera_config.py:26`), the create step would skip one set. That would save roughly one set's time, about 0.4-1.6 s (**inferred**).
  - The harness passed framerate 30 instead (bug H5), so the measured latency is an upper bound for the default config. With framerate -1, the camera may also end on its pin default rate.

## 5. The Kiyo in W-CYC

- **Health and timing (measured).** The pre-probe at 23:01:21.6Z was ok, with one MF frame at 913 ms (`pre_probe`). The variants ran 23:01:21Z-23:16:45Z (suite log lines 170-237), at plug-in age 148.8-164.3 min from LastArrivalDate 20:32:29Z.
- **No failure of any kind.** 210/210 cycles plus 1 probe. `probes_during_test` is absent, and `camera_faulted` was never set during W-CYC.
- **W-KIYO background polls inside the window: 34/34 answered** (17 MF, 17 DS, 23:04:10Z-23:19:13Z, `W-KIYO.json` polls).
- **Vendor software (measured).**
  - `activity_at_first_stream.other_processes` = LogiTuneAgent.exe 3296 and **RazerAppEngine.exe 37240**, both non-streaming. `consent_in_use` is empty.
  - Every Kiyo MF row's `activity_pids` contains 37240 (non-streaming). The other cameras show only 3296 plus wincam itself.
  - So Razer was attached to the Kiyo during 90 successful MF cycles. Its attachment alone does not break streaming. It may still matter for the later onset; that question belongs to the kiyo/multi groups.
- **Camera-specific costs (measured).**
  - MF close p50 is 1117 ms, against 270-360 ms on the other three. DS close is 939 ms and OpenCV close 913 ms, so the cost is the camera's, on every API.
  - The MF close values are quantised in about 100 ms steps (816, 919, 1019, 1119, 1220, 1320, 1422 ms in mf_inproc). That suggests a 100 ms poll inside the Kiyo's release path (**inferred**).
- **Compared with run 1.**
  - In run 1 the Kiyo was wedged before W-CYC began. Its 7 cells were "no" originally, and "untested (pre-existing fault)" after reanalysis.
  - This run produces its first measured W-CYC cells: MF yes x 3, PyAV-DS partial x 3, OpenCV no (latency) x 2.
  - That change is because of the camera (it was healthy, replugged at 15:32 local), not the fixes. The B1 pre-probe ran and passed, so it did not change a rating.
- **Plug-in age.** It faulted at 210.5-211.6 min, against about 224 min in run 1 (13:43:39 local after a 09:59 plug-in). Both runs fall in the 200-225 min window (**inferred** for the cause; the kiyo group owns that analysis).

## 6. Comparison with run 1 (what changed, and why)

| Change | Run 1 (`reanalysis/W-CYC.json`) | Run 2 | Cause |
| --- | --- | --- | --- |
| Kiyo, 7 to 8 cells | untested (pre-existing fault) | 3 yes / 3 partial / 2 no (latency) | **camera** (healthy this time) |
| C922 and C930e ds_modeswitch | partial: 12/25 cycles at 640x480 fell back to YUY2 | yes: 25/25 mjpeg | **fix** (mode scope: the switch partner is now MJPG 1920x1080@30, `mode_scope.switch_mode`) |
| Generic opencv_inproc | no (failures): 14/15, a device reset in cycle 13 (11.35 s set, YUY2 640x480) | no (latency): 15/15, `set_ms` max 1714, no 640x480, no re-arrival | **camera / chance** (inferred). B5's per-variant arrival snapshots are in place (`arrivals_changed` [] in all 32 variants) and saw nothing |
| opencv_skellycam | not run | 4 x no (latency), final MJPG | **fix** (B4/N5) |
| Format evidence | the OpenCV YUY2 was invisible | `format_mismatch_count` 15 on opencv_inproc (C922, Kiyo, C930e) | **fix** (B3/B6) |
| Rating labels | "no" | "no (latency)" | **fix** (B8) |

Latency is stable between the runs. p50 open→first frame, run 1 → run 2 (**measured**):

| Route | C922 | generic | C930e |
| --- | --- | --- | --- |
| MF | 329 → 327 | 98 → 98 | 481 → 511 |
| DS | 585 → 593 | 370 → 392 | 771 → 773 |
| OpenCV (create step only) | 3040 → 3047 | 2060 → 2086 | 4229 → 4245 |

- The MF-minus-DS gap was 256 / 272 / 290 ms in run 1 and is 266 / 294 / 262 ms now.
- Close is unchanged within about 25 ms.

**Generic camera fps.** It delivered 25.5 fps in run 1 (MF derived and DS `fps_measured`, about 14:19 local) and **17.1 fps** in run 2 (about 18:17 local), at the same mode on both APIs.

- The camera advertises MJPG 720p at only 30 and 25 fps.
- Manual exposure -7 through OpenCV raised it to 25.7 fps.
- This is consistent with auto exposure lengthening frames in the evening light (**inferred**). It is a camera effect, not an API effect.

## 7. MF vs DirectShow open/close reliability (Dom's criterion)

- **Open/close/open/close, as measured.**
  - **Run 2:** MF 360/360 and PyAV-DS 360/360 cycles opened, delivered frames and closed, across all four cameras. That is 50 in-process + 15 new-process + 25 mode-switch per camera. No hangs, no unreleasable readers, no re-arrivals.
  - Pooled Wilson 95% lower bound **0.989** per API.
  - **Runs 1 + 2 healthy cameras:** MF 630/630 (lower bound **0.994**) and DS 630/630 opened.
  - Per camera, a ≥ 99% lower bound needs n ≥ 381 failure-free cycles (run 1 V2.6). No cell is near that.
- **Format integrity.**
  - **MF** negotiated MJPG on 360/360 (`negotiated_ok`).
  - **PyAV-DS** delivered MJPEG on 270/360 (Wilson 0.703-0.792). All 90 misses are the Kiyo, which got YUY2 because PyAV cannot request MJPEG.
  - **Runs 1 + 2 together:** DS as requested 516/540 on the three non-Kiyo cameras, plus 0/90 on the Kiyo.
- **Latency.**
  - Where both give MJPEG, MF reaches the first frame sooner by 266 ms (C922), 294 ms (generic) and 262 ms (C930e).
  - On the Kiyo, MF's 910 ms is MJPEG while DS's 821 ms is YUY2, so the two are not comparable.
- **Close cost** follows the camera, not the API: 263-370 ms on the three cameras for MF, DS and OpenCV alike, and about 0.9-1.1 s on the Kiyo for all three.
- **Answer (inferred, on two runs):**
  - MF and DirectShow are equally reliable at open/close on this hardware. Neither failed once in 630 healthy-camera cycles per API across the two runs (1,260 MF + DS cycles in all).
  - MF is the better primary. It always delivers the requested MJPEG, is about 0.26-0.29 s faster to the first frame, and gives a diagnosable HRESULT when a device faults (run 1: 0x8007001F vs DS's ambiguous errno 5).
  - The DS route through PyAV is **not** reliable at delivering the requested format, which is part of "works" for skellycam.
  - OpenCV CAP_DSHOW, skellycam today, opens reliably (120/120) but never inside 2 s (2.1-11.5 s), and only reaches MJPEG because of its second FOURCC set.

## 8. Remaining harness bugs

| # | File:line | Bug | Fix | Severity |
| --- | --- | --- | --- | --- |
| H1 | `suite/windows/tests/w_cyc.py:141` (MF/DS `fps_mismatch` always None); `w_cyc.py:191-199` (`_newproc_row` drops `fps_measured`, which both `wincam capture` and `pyav_ds capture` report); `suite/windows/native/wincam.cpp:2335-2352` (the cycle row has no fps); `suite/common/cycstats.py:113-117` (None counts as 0) | fps is judged only for OpenCV. The generic camera's MF/DS cells report `fps_mismatch_count` 0 while it delivered 17.1 fps at "@30" in 210 cycles | Emit `fps_measured` in wincam cycle rows (first-to-last sample QPC, as `capture` does at `wincam.cpp:2255-2256`). Copy `fps_measured` in `_newproc_row`. Apply the 0.9 x requested rule for every API in `format_flags`. Add `n_fps_judged` to the summary so 0 is not read as "ok" | medium |
| H2 | `w_cyc.py:198` | `_newproc_row` reads `s["stream"]["codec"]`, but `pyav_ds capture` writes it to `negotiated.codec` (`pyav_ds.py:542`; raw `p000/summary.json` has `"stream": null`). The `codec` is None in all 60 ds_newproc rows, so a non-MJPEG stream that is not flagged as a fallback would pass | `(s.get("negotiated") or s.get("stream") or {}).get("codec")` | low |
| H3 | `w_cyc.py:81, 279, 378` | `UTC_IS_END` is keyed by API only. mf_newproc rows stamp `utc` at the cycle **start** (`:279`), but `apply_re_arrival` treats every MF row as end-stamped. A re-arrival in mf_newproc cycle j is pinned on j+1, and one in the last cycle stays unattributed (partial instead of a failure) | Key it by (api, kind): newproc rows are start-stamped, and only `wincam cycle` is end-stamped | low (no re-arrival this run) |
| H4 | `w_cyc.py:625` | `variants.<v>.fourccs` comes from `sets.got_fourcc`, the **create-step** readback. For opencv_skellycam it says ['YUY2'] while `final.fourccs` says ['MJPG'] | Use `final_fourcc`, or rename the field to `create_step_fourccs` and keep both | low |
| H5 | `w_cyc.py:236-239` with `suite/windows/helpers/opencv_ds.py:136` | opencv_skellycam does not pass `--skellycam-framerate`, so the create step sets FPS = 30. skellycam's default config has `framerate = -1` (`camera_config.py:26`), which skips that set. The variant therefore models a non-default config: one extra graph rebuild, and possibly a different final fps | Pass `--skellycam-framerate -1` (the default config). Optionally add a second variant with 30, and record which ran | medium |
| H6 | `suite/common/rating.py:428-433` | Criterion "negotiated the requested format" lists `fps_mismatch` in its detail but ignores it (generic opencv_skellycam: fps 15/15 mismatched, `met` True) | Either count fps (only if the plan wants it), or move fps into its own informational criterion with `met` None | low |
| H7 | `rating.py:442-452` | A "no (latency)" label hides a format mismatch on the same cell: opencv_inproc's YUY2 10 fps shows in summary.md only as "no (latency)" | Append the mismatch counts to `summary_label`, e.g. "no (latency; YUY2 15/15)" | low |
| H8 | `w_cyc.py:226-231` (no `--engine`) | The DS cells always use the PyAV engine, which cannot request MJPEG. On the Kiyo they measure PyAV's YUY2 fallback, not DirectShow MJPEG open/close. Run 1's B6 fix (`--engine ffmpeg`) was only half applied: the fallback is now counted, but no MJPEG DS route is cycled | Add a `ds_ffmpeg` variant (`pyav_ds cycle --engine ffmpeg`), at least for cameras whose PyAV rows fall back | medium |
| H9 (cross-group, W-KIYO) | camlock is global (suite log: Kiyo control poll `lock wait 455.9s` at 18:04:10 and `155.1s` at 18:07:24) | W-CYC's long single commands (`wincam cycle` up to 155 s) starve the background Kiyo poller, which leaves gaps of up to 7.6 min | Let read-only control polls of a camera that is not streaming bypass the lock, or split W-CYC's in-process runs into chunks | low here |

Fixed since run 1 and confirmed working in this run:

- **B1:** a pre-probe for every camera, all ok.
- **B3/B6:** format flags; the Kiyo's DS YUY2 is caught.
- **B5:** per-variant arrival snapshots, present in all 32 variants.
- **B8:** labels "no (latency)".
- **N4:** -1 sentinels dropped.
- **N5:** opencv_skellycam.
- **Mode scope:** a 1080p30 switch partner.

## Verifier notes

Adversarial check, 2026-11-06. Every number was recomputed with scripts from `W-CYC.json`, the 32 `W-CYC/<cam>/<variant>_cycles.json` row files, the raw `cycles.jsonl` and `p*/summary.json`, run 1's `W-CYC.json`, `reanalysis/W-CYC.json` and rows, `W-KIYO.json`, `W-FMT/*_formats_ds.json` and `suite_log.txt`. The code claims were checked against `suite/windows/tests/w_cyc.py`, `common/rating.py`, `common/cycstats.py`, `helpers/opencv_ds.py`, `helpers/pyav_ds.py`, `native/wincam.cpp`, `tools/camlock.py` and skellycam's own `camera_config.py`, `create_cv2_video_capture.py` and `opencv_apply_config.py`. No camera was opened, and no suite code or result file was changed.

### V1. What reproduced exactly (measured)

- **All 32 cells** match the analyst's table: rating, n_ok/n, Wilson bounds, n_first_frame_within, open→first p50/p95/max, close p50/p95/max, format/fps mismatch counts, `device_reset_count` 0, hangs/unreleasable 0, `re_arrival` null, `arrivals_changed` [] and `measurements.arrivals.changes` []. The totals are 21 yes, 3 partial (format mismatch) and 8 no (latency), as summary.md lines 55-58 show.
- **Delivered fps reproduces.**
  - MF fps, derived from `t_start_qpc_ns` spacing with 29 / (Δqpc − 100 ms − o2ff − close): C922 30.2, C930e 29.7, Kiyo 29.7 (30.2 at 1080p), generic **17.1** (720p and 1080p alike).
  - Raw `fps_measured` gives mf_newproc medians of 30.2 / 29.7 / 29.7 / 17.1 and ds_newproc medians of 29.9 / 30.3 / 22.4 / 17.1.
- **Wilson bounds reproduce:** 360/360 gives 0.9894, 630/630 gives 0.9939, 270/360 gives 0.703-0.792, and 516/540 gives 0.935-0.970. "n ≥ 381" is right: n/(n+1.96²) ≥ 0.99 holds from n = 381.
- **The MF−DS gap** is 266/294/262 ms now and was 256/272/290 ms in run 1. The run-1 → run-2 p50s in section 6 all reproduce.
- **OpenCV step timings (p50)** reproduce, and they add up: open + set + create_read ≈ create_first_frame, and that plus apply plus the first read ≈ o2ff.
- **Other items that reproduce:** `CAP_PROP_BUFFERSIZE` refused (`sets.buffersize` False, `got_buffersize` -1) on 4/4 cameras; process wall p50 of 1.66/1.88/2.08/2.94 s (MF) and 2.11/2.33/2.55/3.27 s (PyAV); the Kiyo pre-probe ok at 913 ms; plug-in ages 148.8-164.3 min; W-KIYO 34/34 polls answered (17 MF + 17 DS, 23:04:10Z-23:19:13Z), and 99/99 across the whole W-CYC window.

### V2. Verdicts on the findings

| Id | Verdict | Note |
| --- | --- | --- |
| F1 | confirmed | |
| F2 | confirmed | The causal part stays inferred. |
| F3 | confirmed | `pyav_ds.py:20-33` documents that PyAV ignores `vcodec`. Run 1's quick W-MJPEG had `ffmpeg_ds` delivering MJPEG on the Kiyo (run 1 `cyc_kiyo.md:266`). |
| F4 | **weakened** | pid 37240 appears in **75/75 in-process MF rows** (mf_inproc 50, mf_modeswitch 25). The 15 mf_newproc rows carry no `activity_pids` at all, because `_newproc_row` drops them (see N2). So "all 90" is measured for 75 cycles and assumed for 15. |
| F5 | confirmed, and stronger | The ~100 ms close quantisation is **not MF-specific**. Kiyo DS closes cluster at 740/940/1040/1150 ms, and OpenCV closes at 800/900/1000/1100 ms. The step is on the camera/driver side on every API (the cause is still inferred). |
| F6 | confirmed | |
| F7 | confirmed | |
| F8 | confirmed | It also contradicts skellycam's own comments: `create_cv2_video_capture.py:27` says "DSHOW on Windows does respect it", and `determine_backend.py:39` says "Functional CAP_PROP_BUFFERSIZE control". On these 4 cameras, BUFFERSIZE = 1 is a no-op. |
| F9 | **weakened** | (a) C930e: `got_exposure` is -5 in 14/15 cycles but **-7 in 1/15 (cycle 9)**, and `exposure_before` stays -5 in all 15. (b) The **generic's readback cannot show the set took**: `exposure_before` and `got_exposure` are both -7 in all 15 cycles, because its auto value was already -7 (`exposure_restore.original` = -7 auto). Only the fps change (17.1 → 25.7) suggests manual mode engaged. (c) `exposure_restore.restored` checks only the auto flag (`w_cyc.py:329`). The C922 and Kiyo were left at value -7 (original -4) with the auto flag set. That is harmless in auto mode, but "restored" overstates it. |
| F10 | confirmed | |
| F11 | confirmed, with a nuance | The generic's ceiling at "720p@30" is about 25.7 fps even with good light: run 1's opencv_inproc, daytime with no exposure set, gave 25.5-26.1 in 13 cycles, and run 1's DS gave 25.54. So it never reaches 0.9 x 30 = 27. If H1 is fixed as proposed, the generic's MF/DS cells get flagged as fps mismatch in **both** runs, not only in the evening. 17.1 fps at 1080p too fits an exposure-limited frame time (about 58 ms). The cause is still inferred. |
| F12 | confirmed | |
| F13 | confirmed, but the result depends on the mode scope | PyAV falls back to YUY2 whenever a YUY2 caps entry matches the size and rate. In run 1 that included 640x480@30 on the C922 and C930e. The 1080p30 partner has no YUY2 entry at 30 fps on the Logitechs (their YUY2 1080p tops out at 5 fps, per W-FMT DS), so "all misses on the Kiyo" holds only for this scope. |
| F14 | confirmed | |
| F15 | confirmed | |
| F16 | confirmed (inferred) | Caveat: the plan's reliability row (`xplat_capture_plan.md:240`) does not include format. The Kiyo DS "partial" is a harness policy (B3/B6). Under the literal section-3 row, those 3 cells would be "yes". The policy is defensible, because the plan's DS candidate (line 225) is "PyAV DirectShow vcodec=mjpeg", but the report should say the cap is harness policy. |
| F17 | **weakened** | C922/C930e ds_modeswitch went partial → yes because a **harness scope change removed the YUY2-matching partner**, not because DS behaviour improved. PyAV-DS would still fall back at 640x480@30, which is now out of scope. Also, run 1's original rating was "yes"; "partial" exists only in `reanalysis/W-CYC.json` (`verdict_changes`). |
| F18 | **weakened** | Run 1's generic opencv_inproc had **two** 640x480 YUY2 cycles with an ~11.35 s set: cycle 0 (`set_ms` 11366, `sets.h` False) and cycle 13 (11348). `format_mismatch_count` is 2. Only cycle 13 coincided with the re-arrival (19:24:27Z). So the 640x480 / 11 s set failure is not tied to the re-arrival. The generic also is not a clean camera across the runs. Its `last_arrival` was 18:17:09Z, 2 min before run 1 started; then 19:24:27Z (in W-CYC); then **22:26:45Z, 22 min before run 2 started** (`measurements.arrivals.before`). It faulted in run 2's W-MULTI at plug-in age 93.7 min (summary.md line 122). Whether Dom replugged it is not recorded. |
| F19 | confirmed | The largest shift is C930e MF, 481 → 511 ms (+6%). |
| F20 | confirmed | |
| F21 | **weakened** | Run 1's onset is bracketed, not a point. Nothing touched the Kiyo between 200 min (13:19:59) and 224.3 min (13:43:39), and 224.3 min is the first touch at which the fault was seen (run 1 `cyc_kiyo.md:139-142`). Run 2's 210.5 min falls inside that 200-224 bracket. That is two samples. |

### V3. Corrections to the cell table

- **Kiyo ds_modeswitch, "YUY2 at both modes":** the codec is rawvideo/yuyv422 in all 25 cycles, but the **size of the "1920x1080" cycles is unverified**. PyAV cycle rows carry no width/height (N1). Their fps (22.37) is the same as the 720p cycles (22.41).
- **C930e opencv_skellycam, "exposure -7 set did not take (got -5)":** that is true for 14/15 cycles. Cycle 9 read back -7.
- **Generic opencv_skellycam:** the exposure set "took" is inferred from fps only (see F9).
- **Generic mf_modeswitch:** the latency depends on the mode. p50 is **209 ms at 720p vs 109 ms at 1080p** (DS: 421 vs 387). So the "bimodal ~100/~210 ms" is partly a mode-switch effect: a 720p open that follows a 1080p session costs about 2 frame periods more at 17 fps. mf_inproc (720p only) is mostly 80-110 ms, with occasional ~210 ms opens.
- **Kiyo DS cells:** "partial" stands as harness policy. The cells pass the plan's section-3 row (F16).

### V4. Harness bugs: verdicts

| # | Verdict | Note |
| --- | --- | --- |
| H1 | confirmed | `w_cyc.py:141` sets `fps_mismatch` None for MF/DS. `cycstats.py:108-117` counts only `True`, so None reads as 0. The `wincam cycle` row (`wincam.cpp:2335-2352`) has no fps but does have `t_start_qpc_ns`, from which fps can be derived offline (V1). Caveat on the fix: the generic will be flagged in daylight too (F11). |
| H2 | confirmed | `w_cyc.py:198` reads `s["stream"]`. `pyav_ds.py:542` writes `"negotiated": r.get("stream")`, and the raw `p000/summary.json` has no `stream` key. |
| H3 | confirmed | `w_cyc.py:81` / `:279` / `:378`. The same bug is in `reanalyse` (`:728`). `wincam cycle` stamps `utc_now()` after `close_session` (`wincam.cpp:2352`), so end-stamped is right only for that tool. |
| H4 | confirmed | `w_cyc.py:625`. |
| H5 | confirmed | `w_cyc.py:236-239` passes no `--skellycam-framerate`, and `opencv_ds.py:136` falls back to `--fps`. skellycam's `DEFAULT_FRAMERATE = -1.0` is at `camera_config.py:26`. Not established: whether skellycam's UI normally sends 30. If it does, the harness models the common case. |
| H6 | confirmed | `rating.py:428` and `:432-433`. |
| H7 | confirmed | `rating.py:442-452`. |
| H8 | confirmed | `pyav_ds.py:856-871` supports `cycle --engine ffmpeg`, and `w_cyc.py:226-231` never passes it. |
| H9 | **corrected cause** | The poller is starved by **camlock non-fairness**, not by single long commands. `tools/camlock.py:50-54` polls with a non-blocking `msvcrt.locking` every 0.5 s. W-CYC's main thread re-takes the lock within its ~0.1 s inter-command gap, so a waiter loses every race. Evidence: the 455.9 s wait (suite_log line 177) spans about 6 consecutive commands (C922 opencv_inproc 97 s, opencv_skellycam 93 s, mf_modeswitch 44 s, ds_modeswitch 50 s, the Kiyo probe, Kiyo mf_inproc 155 s). Further waits of 359.8 s (line 238), 153.6 s and 107-163 s recur through W-CYC. Fix: a ticket/FIFO lock (a queue file, or a named mutex with a waiter flag that the main thread checks before re-acquiring). |

### V5. Missed by the analyst

- **N1 (bug, low-medium): DS size is never judged.** `pyav_ds.py:878-890` builds cycle rows without the negotiated width/height, although `run_session` has them (`:288`). `w_cyc.py:141` then sets `size_mismatch` None for MF and DS. MF's size is covered indirectly, because `negotiated_ok` compares subtype + size + rate (`wincam.cpp:1794`). DS has no size check at all, so a DS fallback to another size would pass criterion 3. Fix: emit `width`/`height` in the PyAV cycle rows and compare them in `format_flags`.
- **N2 (bug, low): `_newproc_row` drops `activity_pids` / `in_use_by_other`** (`w_cyc.py:191-206`), so the newproc variants have no attachment evidence (see F4). Fix: copy them from the capture summary, or record a `wincam activity` snapshot per process.
- **N3 (modelling, low):** opencv_skellycam does not call skellycam's `extract_config_from_cv2_capture` (`opencv_apply_config.py:87`), which only gets properties and probably costs a few ms. It also does not model the create step's retry loop, which this run never needed.
- **Kiyo YUY2 delivered 22.4 fps** although DS negotiated `average_rate` 10000000/333333 (30 fps) (raw `ds_newproc/p000/summary.json`), and YUY2 720p is advertised up to 60 fps. The same camera and scene gave MJPG at 29.7 fps, so lighting is an unlikely cause (**inferred**: a camera-side rate shortfall in YUY2). This matters if anyone reads the Kiyo DS cells as "YUY2 at 30".
- **The plan's reliability row excludes format** (F16). Taken together with F13 and F17, PyAV-DS's format reliability is a function of which modes are in scope, and the 270/360 figure should be quoted with that scope.
