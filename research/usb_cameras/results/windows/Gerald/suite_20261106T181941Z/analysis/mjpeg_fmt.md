# W-MJPEG and W-FMT analysis: suite run 20261106T181941Z on Gerald

Scope: the tests W-MJPEG (G-MJPEG, 12 rating cells) and W-FMT (fmt_equivalence, 1 cell), plus `mjpeg_modes.json` and
`mode_alt_cache.json`. Run: Windows 11 build 26300, 2026-11-06. W-FMT ran at 13:19 local and W-MJPEG from 13:20 to 14:10
local (`W-MJPEG.json` `elapsed_s` 3048), at 3.0 s per mode and API, in a full run (`measurements.quick` false).

Labels: **measured** means the value comes from a named file and field. **Inferred** means it is my reading of measured
data. Paths are relative to the results folder unless they start with `suite/` (the suite code) or `raw/`
(`C:/Users/Dom/Documents/skellycam-raw/results/windows/Gerald/suite_20261106T181941Z`).

## 1. Short answers

- **Why is every G-MJPEG cell partial?** Different reasons for different cells. Only some of them are real.
  - **C922, MF and DS:** real camera findings. Two modes deliver about 15% corrupt frames. The camera streams 30 fps
    whatever lower rate is requested.
  - **C930e, MF and DS:** the only failing criterion is fps. In 9 to 10 modes the camera's frame rate drifts above
    nominal during the 3 s capture. That is camera behaviour, but the test conditions were not controlled (section 4).
  - **pyav_ds column, C922 and C930e:** real API limitation. PyAV cannot make FFmpeg's dshow demuxer pick MJPEG when a
    raw format has the same size and rate, so it gets YUY2 in 95 of 120 (C922) and 96 of 119 (C930e) modes.
  - **Generic 4c4a:4a55, all three APIs:** harness artefact. The only failures are the five @25 modes, where the camera
    runs 25.7 fps (+2.8%). The rule that sets the fps reference only accepts a real rate below nominal. With a symmetric
    rule, all three generic cells re-rate to **yes** using the existing data.
  - **Kiyo Pro, all three APIs:** the Kiyo faulted on the first mode, and 0 of 28 modes delivered on any API. "Partial" is
    a rating bug here. The cells should read **no** (DS, PyAV) or **untested: device fault** (all three).
- **Do MF and DS list the same MJPEG modes (W-FMT)?** Yes, on all four cameras, and both match the USB descriptors exactly:
  C922 120, C930e 119, generic 10, Kiyo 28 (frame size × interval). The `fmt_equivalence` = yes cell is correct.
- **Native MJPEG at all resolutions on Windows?** **Yes through Media Foundation** on the three working cameras.
  - Every advertised MJPEG mode (249 modes: 120 + 119 + 10) negotiated MJPG with a verified readback.
  - SOF0 size equals the request on 100% of frames.
  - The JPEG header SHA-1 is identical to DirectShow's in 249 of 249 modes.
  - Process CPU is about 0.5–2% of one core.
  - **DirectShow** gives the same bytes, but only through the ffmpeg CLI (`-vcodec mjpeg`), not through PyAV.
  - Caveats: two C922 modes with corrupt frames (camera), Logitech frame-rate requests not honoured (camera, under
    auto-exposure priority), and the Kiyo is untested (device fault).

## 2. Every rating cell explained

All criteria come from `W-MJPEG.json` `verdicts["G-MJPEG|<camera key>|<api>"].criteria`. Per-mode reasons come from
`.evidence.modes[]` (`negotiated`, `valid_ok`, `sof_matches`, `fps_ok`, `header_equal_across_apis`, `ok`). The rating
function is `suite/common/rating.py:132-179` (`rate_mjpeg`):

- **yes** needs every mode `ok`, plus an fps reference and a cross-API hash for every mode.
- **no** only when every mode has `is_jpeg` False.
- **partial** otherwise.

`ds` means DirectShow through PyAV, or through the ffmpeg CLI where PyAV fell back to raw video. `pyav_ds` means PyAV
alone. The criterion "every advertised MJPEG mode was captured" is met in all 12 cells (C922 120/120, Kiyo 28/28,
generic 10/10, C930e 119/119).

| Camera | API | Rating | Criteria not met (measured) | Real or artefact |
| --- | --- | --- | --- | --- |
| C922 | mf | partial | valid 118/120: `1280x720@5` and `1600x896@5` have strict 0.75 and EOI fraction 0.848. fps fails in 102 modes: 100 modes at nominal 5–24 deliver 29.97–30.03, and the 2 @5 modes above deliver 15.0. Negotiates 120/120, SOF0 met, header SHA-1 met. | **Real** (camera). See 3.1. |
| C922 | ds | partial | Same as mf: valid 118/120, fps fails in 102 modes (DS 29.87–30.11 and 14.99). Route: 95 modes ffmpeg CLI, 25 PyAV. | **Real** (camera) |
| C922 | pyav_ds | partial | Negotiates 25/120: 95 modes were `format_fallback` to raw `yuyv422` (note in the verdict). Those 95 also fail valid and SOF0. 17 PyAV-MJPEG modes fail fps (the camera runs 30). | **Real** (PyAV limitation) plus the camera fps finding |
| Kiyo | mf | partial | Negotiates 0/28, valid 1/28, SOF0 not met, fps and header `met: null`. Mode 1 (`640x360@5`) delivered 1 frame at 2170 ms, then `reader_release` hung for 5 s (`error.stage` `reader_release`, class timeout). Modes 2–28 failed at `first_sample` with 0x8007001F (`classification.class` `device_error`). | **Real** device fault (Kiyo signature). The **rating is an artefact**: it should be untested (device fault). |
| Kiyo | ds | partial | Negotiates 0/28, valid 0/28. `frames` = 0 in every mode: mode 1 `av.open` timed out, modes 2–28 got OSError 5 ("Could not run graph"). | Real fault. **Rating artefact**: 0 frames everywhere should be "no" or untested, never partial. |
| Kiyo | pyav_ds | partial | Same as ds (the PyAV route was used for all 28 modes). | Same as ds |
| Generic | mf | partial | Only fps: the 5 modes at nominal 25 deliver 25.69–25.71 (+2.8%). The 5 modes at nominal 30 deliver 25.7 and pass, because the reference was moved to the measured rate (`fps_reference_note`). Valid 10/10, of which the two 1080p modes count through the known quirk (strict 0.0, lenient 1.0). | **Harness artefact**: the fps reference rule is asymmetric (bug H1). The camera really runs 25.7 at both settings. |
| Generic | ds | partial | Same: fps fails only at the 5 @25 modes. | **Harness artefact** (H1) |
| Generic | pyav_ds | partial | Same: fps fails only at the 5 @25 modes. | **Harness artefact** (H1) |
| C930e | mf | partial | Only fps, 10 of 119 modes: `800x448@10/15/20/24`, `848x480@5/7.5`, `1280x720@7.5/15/20/24`. All deviations are above nominal, +2.5% to +14.6%. Negotiates 119/119, valid 119/119, SOF0 and header met. | **Mixed**: the camera's rate really drifts upward, but AE priority was not controlled and 3 s is too short to see a steady rate. See 3.4. |
| C930e | ds | partial | Only fps, 9 modes: `800x448@10/15/20/24`, `848x480@20` (−2.3%), `1280x720@5` (+14.2%), `@7.5`, `@20`, `@24`. Different modes from MF, because the two runs are separate captures. Route: 96 modes ffmpeg CLI, 23 PyAV. | **Mixed** |
| C930e | pyav_ds | partial | Negotiates 23/119: 96 modes fell back to raw. Also 6 fps fails, 4 of which are raw-fallback modes at 18 fps. | **Real** (PyAV limitation) |

**Re-rated offline (inferred: my re-computation from the existing JSON with `rating.rate_mjpeg`).** I applied the fixes for
H1 (symmetric fps reference) and H2 (0 frames counts as not JPEG):

| Camera | mf | ds | pyav_ds |
| --- | --- | --- | --- |
| C922 | partial: 118/120 ok, the 2 corrupt modes only | partial: 118/120 | partial: 25/120 |
| Kiyo | partial: should become untested with fix H3 | **no** | **no** |
| Generic | **yes** | **yes** | **yes** |
| C930e | partial: 113/119, 6 modes where MF and DS disagree | partial: 113/119 | partial: 22/119 |

Caution: the symmetric reference also makes the C922's sub-30 modes pass, because both APIs deliver 30. That hides a
real camera finding (the requested rate is not honoured). Report "rate honoured" as its own camera measurement outside
G-MJPEG (fix H1).

### W-FMT: `fmt_equivalence` = yes

`W-FMT.json` `verdicts.fmt_equivalence`:

- The criterion "MJPEG sizes and discrete rates equal in descriptors, MF and DS" is met on all four cameras.
- `counts.descriptor_mjpeg_modes` = `mf_mjpeg_types` = `ds_mjpeg_modes`: C922 120 (17 sizes), Kiyo 28 (4 sizes), generic
  10 (5 sizes), C930e 119 (17 sizes).
- `diff.mf_vs_ds` has no MJPEG entries, and `diff.{mf,ds}.mjpeg_missing` and `mjpeg_extra` are empty everywhere.
- `errors` = [], and every `wincam formats` call returned rc 0.

**Real; the rating is correct.** The informational criterion "every format equal" is false, for these reasons:

- **C930e YUY2 `2304x1296@2` and `2304x1536@2`.** Both are in the descriptors and absent from both MF and DS
  (`diff.mf.missing_vs_descriptor`; the MF list has no 2304-wide type at all). **Real** Windows behaviour. Inferred cause:
  their `dwMaxBitRate` (238.9 and 283.1 Mbit/s, `descriptors/descriptors.json`) exceeds the largest High-Speed
  isochronous allocation (3×1024 B × 8000/s ≈ 196.6 Mbit/s), so usbvideo drops them.
- **C930e H.264.** It has a second capture stream or pin. MF lists 238 types (`H264` + `MFVIDEOFORMAT_H264_ES`, with real
  sizes). DS lists 14, all with size `0x0` (`ds_pins.1.header_kinds` = `other`). The 0x0 is a **harness gap**
  (`suite/windows/native/wincam.cpp:945-952` only parses VIH, VIH2 and MPEG2VIDEOINFO format blocks; see H7). H.264 is
  not in the standard UVC descriptors (inferred: Logitech's extension-unit H.264), so it shows as "extra".

Other W-FMT facts (measured, `W-FMT.json`):

- **NV12 types that MF synthesizes** (Trap 1): C922 120, C930e 119, generic 13 (10 capture + 3 still), Kiyo 0
  (`counts.mf_synthesized`). The Kiyo has native NV12, H264 and YUY2 as well as MJPG (112 modes in total).
- **The generic camera has a still pin.** MJPEG 1280x720, 640x480 and 320x240 and YUY2 640x480 and 320x240, equal in the
  descriptors, the MF still stream and the DS still pin (`still.sizes_equal` true). The DS still pin has no rate list
  (5 `range_only` modes).
- **Identity cross-check** (serial string descriptor against the discovery key) agrees on all four cameras.

## 3. Quantitative findings per camera

Common facts (measured):

- Every mode was captured one camera at a time and one mode at a time.
- `measurements.decoders`: simplejpeg (libjpeg-turbo) True, PIL True.
- W-MJPEG `measurements.arrivals.changes` = [] (no camera re-arrived during W-MJPEG). The generic camera's 14:44:44
  re-arrival came later, during W-MULTI.
- `mjpeg_modes.json` (W-FMT) lists the same (size, rate) sets that W-MJPEG captured, for all four cameras, all with
  `in_mf` and `in_ds` true.

| | C922 | Kiyo | Generic | C930e |
| --- | --- | --- | --- | --- |
| Advertised MJPEG modes (sizes) | 120 (17) | 28 (4) | 10 (5) | 119 (17) |
| MF negotiated MJPG, readback ok | 120 | 0 | 10 | 119 |
| DS delivered MJPEG (`ds` route) | 120 (25 PyAV + 95 ffmpeg CLI) | 0 | 10 (PyAV) | 119 (23 PyAV + 96 ffmpeg CLI) |
| PyAV alone delivered MJPEG | 25 | 0 | 10 | 23 |
| Strict decode ≥ 99%, MF and DS | 118 | – | 8 (1080p: strict 0%, lenient 100%, known quirk) | 119 |
| SOF0 = request (all frames) | 120 | – | 10 | 119 |
| fps within 2% of nominal, MF | 17 (all @30) + 720p60 by reference adjustment | – | 0 (always 25.7) | 109 |
| MF == DS header SHA-1 | 120/120 | – (none) | 10/10 | 119/119 |
| MF process CPU, median (max), % of one core | 1.6 (4.7) | – | 1.8 (4.1) | 0.5 (3.6) |
| PyAV process CPU, median (max) | 1.0 (4.7) | – | 1.6 (3.1) | 0.5 (3.6) |
| MF open to first frame, median | 331 ms | – | 92 ms | 500 ms |
| PyAV open to first frame, median | 625 ms | – | 399 ms | 807 ms |

Sources: `measurements.cameras[key].modes[].apis.{mf,pyav_ds,ffmpeg_ds,ds}`, fields `negotiated`,
`strict_ok_fraction`, `sof_match_fraction`, `fps_steady`, `cpu_pct_one_core`, `timings.open_to_first_frame_ms`,
`header_sha1_equal`, `route`.

CPU caveat (measured): the CPU values are multiples of about 0.52% (for example 0.517, 1.0, 1.5, 2.1, 2.6, 3.1). That is
the 15.6 ms process-time tick divided by 3 s, so treat every value as ±0.5%. The ffmpeg CLI route has no CPU value
(`cpu_pct_one_core` null, `suite/windows/helpers/pyav_ds.py:625` "not measured (separate process)").

### 3.1 C922: the requested frame rate is ignored, and two modes have corrupt frames

- **Measured: the camera produces 30 fps whatever lower rate is requested.**
  - Every sub-30 mode (5, 7.5, 10, 15, 20, 24) delivers 29.97–30.03 fps on MF (`fps_steady`, QPC arrival) and
    29.87–30.11 on DS. There are two exceptions, listed below.
  - The MF readback still says the requested rate (for example `negotiated_detail.fps` 5 for `640x480@5`).
  - The device's own UVC PTS confirms it is the camera, not the host (`raw/W-MJPEG/c922prostreamw_046d-085c_C922SN01/
    mf_640x480_5/frames.jsonl` `uvc_pts`): the median step is 10.07 M ticks, the same as at `@30` (10.07 M). Inferred: a
    300 MHz clock, so 33.3 ms.
- **Measured: `1280x720@60` delivers 30.53 (MF) and 30.57 (DS)** (UVC PTS step 9.82 M ticks). The rule that moves the
  reference when both APIs agree accepted 30.55 as the real rate, so this mode passes.
- **Inferred cause: Logitech RightLight, i.e. UVC auto-exposure priority.**
  - W-CTRL-LIST read the C922 at run start as `cc.auto_exposure_priority` value 1 and exposure in auto mode
    (`W-CTRL-LIST.json` `measurements.cameras[0].ranges`).
  - With priority 1 the camera chooses its own frame rate. The C922 is widely reported to reach 60 fps only with
    RightLight off.
  - The scene was daylit (sample `W-MJPEG/samples/c922prostreamw_046d-085c_C922SN01_mf_1280x720_30.jpg`), so this is not
    a too-dark artefact.
- **Measured: `1280x720@5` and `1600x896@5` run at 15.0 fps with corrupt frames, identically on MF and DS.**
  - The frames: EOI present on 84.8% (MF) and 84.4–88.9% (DS); strict decode 6 of 8 checked frames. Decoder errors:
    "N extraneous bytes before marker 0xd2/0xd4/0xd6" (restart markers, so corruption inside the scan) and "premature end
    of data segment".
  - Frame sizes are normal (p50 108 kB at 720p, the same as at @30), so the frames are not truncated.
  - The UVC PTS steps alternate between 33 ms and 133 ms. The sensor runs at 30 and the camera drops frames.
  - Inferred: a firmware fault in these two modes, independent of the API.
- Measured: header SHA-1 is identical across MF and DS in 120/120 modes, with 1 distinct header per mode
  (`header_sha1_distinct`).

### 3.2 Kiyo Pro: device fault on the first stream

- Measured:
  - W-FMT and W-CTRL-LIST (13:19) talked to the Kiyo normally.
  - In W-MJPEG (13:43:39) the first MF capture got 1 valid frame after 2.17 s. Then `IMFSourceReader` release hung past
    the 5 s timeout (`modes[0].apis.mf.error.stage` `reader_release`).
  - Every later call failed: MF at `first_sample` with 0x8007001F (ERROR_GEN_FAILURE), PyAV with OSError 5.
  - The camera did not re-arrive (`arrivals.changes` []).
- Inferred: this is the known Kiyo failure signature (REPORT.md: "stops answering control requests ... every API then
  fails with 0x8007001F"). It is a real camera result, but it means the Kiyo's MJPEG behaviour, including its 60 fps
  modes, is **untested** in this run.
- The 10-25 claim that "PyAV falls back to YUY2 on the Kiyo" (REPORT.md line 22) could not be re-checked here. The
  ffmpeg CLI route was never tried, because PyAV never opened the device, so `format_fallback` was never set.

### 3.3 Generic 4c4a:4a55: about 25.7 fps at both 25 and 30, and a strict-decode quirk at 1080p

- **Measured: 25.69–25.71 fps** in all 10 modes, on MF (QPC) and DS (PyAV, QPC). This matches mjpeg/RESULTS.md finding
  3 (25.74–25.78 at @30 on 10-25 and 10-27). Now also shown at the @25 setting, where the camera is 2.8% fast.
- **Measured: 1080p strict decode 0% at both rates, lenient 100%.** The cause is `extraneous_bytes_before_eoi` on every
  checked frame (548–1494 bytes). That is the known quirk (RESULTS.md finding 1; REPORT finding 6), and it is noted, so
  it passes under the plan's "lenient with a known quirk" rule. All other sizes pass strict decode on 100%.
- Measured: 2–4 distinct headers per 8 checked frames (the camera changes its quantisation tables), yet the dominant
  header is identical on MF and DS in 10/10 modes.
- Answer: on this camera everything in G-MJPEG passes. The only failure is the harness's fps reference (H1).

### 3.4 C930e: frame rate drifts above nominal in some modes

- Measured: the requested rate is honoured within 2% in 109 of 119 modes (MF) and 110 of 119 (DS).
- The misses are all at 800x448, 848x480 and 1280x720, and almost all are fast. The worst are `800x448@20` (+14.6% MF,
  +18.5% DS), `1280x720@20` (+12.3% MF) and `1280x720@5` (+14.2% DS only).
- Measured from per-frame data: `raw/W-MJPEG/logitechwebcam_046d-0843_7/mf_800x448_20/frames.jsonl`.
  - The intervals sit at 48 or 64 ms (20 fps) for about 2 s, then switch to 32 ms (30 fps).
  - Frame sizes ramp during the first about 25 frames (auto-exposure converging) and then stay flat.
  - So the camera changes its own frame rate partway through the capture.
- Inferred cause: as on the C922, the camera chose its own rate (W-CTRL-LIST: `cc.auto_exposure_priority` value 1,
  exposure in auto mode). A 3 s capture with a separate run per API cannot settle on a steady "real rate", so MF and DS
  disagree and the reference rule falls back to nominal.
- Earlier runs measured only @30 (RESULTS.md: 30.04–30.05), so sub-30 behaviour is new.

### 3.5 Which modes fail, and why

| Failure | Cameras and modes | Cause |
| --- | --- | --- |
| 15 fps with about 15% corrupt frames | C922 `1280x720@5`, `1600x896@5`, on MF and DS | **Camera** firmware (inferred). Device PTS shows dropped frames. |
| 30 fps delivered at a lower requested rate | C922: all 100 sub-30 modes except the two above | **Camera** under AE priority 1 (inferred). The test did not control it (H4). |
| 60 fps not reached | C922 `1280x720@60` → 30.55 | **Camera** under AE priority 1 (inferred). Passes the rating by reference adjustment. |
| Rate drifts fast within 3 s | C930e: 9–10 modes at 800x448, 848x480, 1280x720 | **Camera**, plus **harness** (AE not controlled, 3 s too short, separate runs per API) |
| 25.7 fps at @25 (+2.8%) | Generic, all 5 @25 modes | **Camera** rate. The **rating failure is harness** (H1). |
| Strict decode fails | Generic 1080p (both rates) | **Camera** quirk, known and accepted (lenient 100%) |
| Raw YUY2 instead of MJPEG | PyAV: 95 C922 modes, 96 C930e modes | **API** (PyAV cannot set `video_codec_id`). The ffmpeg CLI route fixes it. |
| Nothing delivered | Kiyo, all 28 modes, all APIs | **Camera** fault. The rating should be no or untested (H2, H3). |

Explanations that do **not** apply in this run:

- **Bandwidth:** cameras ran one at a time, and none was refused for bandwidth.
- **fps tolerance or 16 ms grid:** `fps_from_rows` is a least-squares fit, and the C922 reads 30.00 ± 0.03 on a 16 ms
  arrival grid.
- **First-frame warm-up:** the fit skips 15% of frames, and the C922's corrupt frames are spread through the capture
  (seq 1, 19, 25, 28, 31, 34, 37).
- **Scene too dark:** the samples are daylit.

### 3.6 mode_alt_cache.json

- Measured: 19 entries, all `source` `seed_measured_20261027` with `utc` null. W-MJPEG added none (it does not measure
  alternate settings).
- For the C922 it covers only `640x480@30` (alt 4), `1280x720@30` (alt 9), `1920x1080@30` (alt 11) and `1920x1080@5`
  (alt 5, 800 B × 1).
- Inferred: alt 5 carries 6.4 MB/s, and 1080p at 30 fps with 197 kB frames needs about 5.9 MB/s. That fits why
  `1920x1080@5` streaming at 30 fps still delivered clean frames.
- The cache has no entry for `1280x720@5` or `1600x896@5`, so it cannot confirm or rule out a bandwidth explanation for
  the corrupt frames there.

## 4. Harness bugs and gaps

| ID | Severity | File:line | Bug | Concrete fix | Re-run needed |
| --- | --- | --- | --- | --- | --- |
| H1 | medium (wrong ratings) | `suite/windows/tests/w_mjpeg.py:153-161` | The rule that sets the fps reference only accepts a measured rate below nominal (`min(fm_, fd_) < m.fps * 0.98`). A camera that agrees with itself on both APIs but runs fast (generic 25.7 at @25) fails "within 2% of the camera's real rate". | Accept agreement in both directions: `abs(fm_-fd_)/max(fm_,fd_) <= 0.02 and abs(ref-m.fps)/m.fps > 0.02`. Prefer the device UVC PTS rate (tier 1) as the reference when present. Separately, record `rate_honoured` (measured vs nominal) per mode as a camera finding outside G-MJPEG, so the C922 30-fps-at-5 result stays visible. | None: re-rate offline from `W-MJPEG.json` (the generic becomes yes on all 3 APIs). |
| H2 | medium (wrong rating) | `suite/windows/tests/w_mjpeg.py:191` with `suite/common/rating.py:157` | `is_jpeg` is `None` when `frames` is 0, and `rate_mjpeg` returns "no" only when every mode has `is_jpeg is False`. So an API that delivered 0 frames in 28/28 modes (Kiyo ds and pyav_ds) rates **partial**. | In w_mjpeg, set `is_jpeg = False` when there are no frames. In `rate_mjpeg`, return "no" when `n_ok == 0` and no mode delivered a JPEG frame. | None: re-rate offline. |
| H3 | medium (wasted time, misleading cell) | `suite/windows/tests/w_mjpeg.py:115-143` | No per-camera stop after a fault that needs a replug. After 0x8007001F (`classification.class` `device_error`, "needs a replug") or a `reader_release` hang, the test still made 27 × 2–3 more calls on the dead Kiyo. The cells read partial instead of "untested: device fault". | After a `device_error` or an unreleasable or timeout result, mark the remaining modes `skipped: device fault (replug needed)`, and have the verdict return `rating.untested(...)` with the fault as evidence. Also consider running the Kiyo last, or soon after plug-in. | W-MJPEG on the Kiyo only (`--camera 1532:0e05`), after an **attended replug** (no pnputil restart). |
| H4 | medium (uncontrolled condition behind most fps failures) | `suite/windows/tests/w_mjpeg.py:109-128` (no control handling) | Auto-exposure priority and exposure mode are neither recorded nor pinned. On both Logitech cameras priority was 1 (W-CTRL-LIST), which lets the camera choose its frame rate. So the fps criterion measured the camera's AE policy, not API delivery. | Read controls before each camera (`ck.get_controls`) and store them in the result. For the fps criterion, set `auto_exposure_priority=0` (keep AE on) through `ck.set_controls` and restore it afterwards. Optionally run a second pass with priority 1, to document the C922 "60 fps needs RightLight off" behaviour. | W-MJPEG on the C922 and C930e (at least all sub-30 and 60 fps modes). |
| H5 | low–medium | `suite/windows/tests/w_mjpeg.py:102`, the `mjpeg_seconds` default of 3.0 | 3 s per mode, with separate MF and DS captures, cannot show a steady rate when the camera changes rate within the capture (C930e: switch at about 2 s). | For any mode whose fps is outside 2% on either API, recapture for 10 s, or fit only the last 50%. Report the rate over the last 1.5 s alongside the full fit. | Part of the H4 re-run (`--mjpeg-seconds 10` on the failing modes) |
| H6 | low (biased sample) | `suite/windows/tests/w_mjpeg.py:121-122` and `:63`; `suite/windows/capkit.py:338-341` | Frames are saved `every:N`, with N taken from the **nominal** fps, and `check_saved` decodes only the first `SAVED_PER_MODE+2` = 8 saved frames. When the camera runs faster than nominal (C922 at 30 instead of 5), those 8 frames cover only the first about 0.5 s. The strict and lenient fractions have 12.5% resolution and are biased to start-up. (The SOI and EOI flags on every frame limit the damage, so no rating changed in this run.) | Pick checked frames evenly across all saved frames (stride `len(saved)//8`), or decode every saved frame (cheap at these sizes). Base `every` on the modes' maximum rate, or on frames received. | Not needed for this run's verdicts. Fix before the H4 re-run. |
| H7 | low (W-FMT informational only) | `suite/windows/native/wincam.cpp:945-952` | DS caps parsing handles only VIH, VIH2 and MPEG2VIDEOINFO. The C930e's H.264 pin (`header_kinds` `other`) is reported as 14 modes of size `0x0`, so MF and DS H264 lists can't be compared. | Parse the format block's `KS_H264VIDEOINFO` (`FORMAT_UVCH264Video`) and log the unknown `formattype` GUID. | W-FMT (2 s, any time). It does not affect `fmt_equivalence`. |
| H8 | low (missing data) | `suite/windows/helpers/pyav_ds.py:625` | No CPU measurement on the ffmpeg CLI route. The `ds` column has no CPU value for 95 C922 and 96 C930e modes. | Measure the child's CPU with `GetProcessTimes` (procutil, or psutil `cpu_times` at exit) and report it as `pct_of_one_core`. | Optional: with the H4 re-run. |
| H9 | low (misleading summary field) | `suite/windows/tests/w_mjpeg.py:214-215` | `failed_modes` uses the tool's `ok` flag, not the rating, so the C922 MF list is empty although 102 modes failed the rating. | Add `rating_failed_modes` from `v["evidence"]["modes"][i]["ok"]`, or rename the field `tool_failed_modes`. | None |
| H10 | low (CPU resolution) | wincam and `pyav_ds.py:340/375` (process times over 3 s) | CPU is quantised at about 0.52%, so sub-2% differences between APIs are noise. | Use longer captures for the CPU figure, or measure CPU over a fixed 10 s window in a separate cell. | Optional |

### Re-run plan

1. **Offline, no camera:** apply H1, H2 and H9 and re-rate `W-MJPEG.json`. Expected: generic yes, yes, yes; Kiyo ds and
   pyav_ds no; C922 mf and ds still partial (2 corrupt modes, real); C930e partial, pending the re-run in step 3.
2. **Kiyo:** ask Dom for a replug, then `run_suite.py --camera 1532:0e05` with W-MJPEG only, soon after plug-in, with H3
   in place.
3. **C922 and C930e:** W-MJPEG with H4 to H6 and H8, AE priority 0, 10 s on the modes that missed fps. This answers
   whether the C922 honours 5–24 fps and reaches 60 at 720p with RightLight off, whether the C930e's drift disappears,
   and whether the C922's two corrupt @5 modes persist (if they do, it is the camera).
4. W-FMT: only after H7, for completeness. Its MJPEG verdict stands.

## 5. Comparison with earlier results

- MJPEG sizes and modes are identical to the 10-25 listing and the plan's table (C922 120, C930e 119, generic 10,
  Kiyo 28: `xplat_capture_plan.md` §2.1).
- MF == DS header SHA-1, earlier shown for 720p30 and 1080p30 only (RESULTS.md finding 2), now holds for **every**
  advertised mode on three cameras (249/249).
- C922 30.0, C930e about 30, generic 25.7 at @30 are reconfirmed. Behaviour at lower rates (C922 always 30, C930e
  drifting, generic always 25.7) is new.
- Generic 1080p strict-decode quirk: reconfirmed at 25 and 30 fps.
- PyAV fallback to raw: earlier seen only on the Kiyo (REPORT.md line 22). Now shown on the C922 (95 modes) and C930e
  (96 modes) wherever a YUY2 mode shares the size and rate. The ffmpeg CLI `-vcodec mjpeg` route fixes it in all of
  them, with the same header bytes as MF.
- Kiyo: excluded from the 10-27 re-run as faulty; faulted again here on its first stream.

## Verifier notes

Adversarial check, 2026-11-06. I recomputed every number from `W-MJPEG.json`, `W-FMT.json`, `W-CTRL-LIST.json`,
`mode_alt_cache.json`, `descriptors/descriptors.json` and the raw `frames.jsonl` files, using scratch scripts (not kept in the
repo). I re-ran `rating.rate_mjpeg` on the stored mode rows: without changes it reproduces the stored
`evidence.modes` exactly (asserted for all 12 cells), so the per-cell explanations above are correct. No camera was opened and
no suite or result file was changed.

### What holds (measured, recomputed)

- **Cell table, section 2:** confirmed for all 13 cells. Counts per cell:
  - C922: mf and ds each have ok 18/120, valid 118/120 and 102 fps failures.
  - Kiyo: mf has valid 1/28. ds and pyav_ds have 0 frames in every mode.
  - Generic: 5/10 ok on all three APIs, and every failure is a @25 mode.
  - C930e: mf 109/119 and ds 110/119.
  - W-FMT: the counts and `diff` fields match exactly.
- **Offline re-rate table:** reproduced exactly with the H1 and H2 changes applied:
  - C922: 118, 118 and 25 modes ok.
  - Kiyo: partial, no, no.
  - Generic: yes on all three APIs.
  - C930e: 113, 113 and 22 modes ok.
- **F1 and F2:** 498/498 (mode, API) pairs on the three working cameras have `sof_match_fraction` 1.0. All 249 MF modes have
  `readback_ok`, and `header_sha1_equal` is True in 249/249. Caveat on F2: the comparison uses the most common header per mode.
  The generic camera has 2–4 distinct headers per mode (`header_sha1_distinct`).
- **F8, F9, F10, F11, F13, F14 and F16:** confirmed. Small corrections:
  - F9: the generic 1080p modes had 7 (@25) and 6 (@30) checked frames, not 8. The save stride comes from the nominal rate and
    the camera is slower than nominal.
  - F10: the first Kiyo PyAV call timed out in `av.open`. The 27 later PyAV calls got OSError 5. The ffmpeg CLI was never run,
    so the Kiyo had 2 calls per mode, not 2–3.
  - F16: the cache has 5 C922 entries, the 4 MJPEG ones listed plus YUY2 640x480@30.
- **Kiyo timeline:** the camera arrived at 14:59:24Z (09:59 local), 3.7 h before W-MJPEG. Its first MF capture
  (13:43:39 local) got 1 frame at 2170 ms in a 3 s window. Then `reader_release` hung for 5000 ms and the child was killed.
  So the device was already unhealthy when the stream started, not after a long stream.

### Refuted or weakened

- **F5 (auto-exposure priority explains the C922 and C930e rates): refuted as the main cause.** Three pieces of evidence:
  1. **Measured: YUY2 on the same camera, at the same priority, follows the requested rate.** PyAV's raw fallback ran YUY2
     in the same session, one mode after MF. Fields: `modes[].apis.pyav_ds.fps_steady` with `format_fallback` true.
     - C922 at 640x480 and larger, YUY2 delivers 6.00 at @5, 7.50 at @7.5, 10.0 at @10 and 15.0 at @15, while MJPEG
       delivers 30.0 in every one of these modes. (YUY2 at sizes up to 432x240 also runs 30, and YUY2 at @20 and @24 often
       gives 15.)
     - C930e: YUY2 holds 5.00, 7.50, 10.00, 14.99 and 20.00 in the same 800x448, 848x480 and 1280x720 modes where MJPEG
       drifts fast.
  2. **Priority 1 lets a camera lower its frame rate, not raise it.** Both cameras run faster than requested.
  3. **Earlier verifier result:** REPORT.md finding 20 and RERUN_20261027.md line 179 record the C922 at 1080p@5 giving 30.0
     fps in 5 of 5 runs with manual exposure −7, where AE priority has no effect.

  Inferred: the C922's MJPEG path ignores frame intervals below 30, and the C930e's MJPEG path speeds up on its own (bursts
  at 30 fps). Both are MJPEG firmware behaviour, not AE policy.
- **F6 (the two corrupt C922 @5 modes are a firmware fault): weakened.** The corruption is measured, but the raw data point
  to a bandwidth mechanism.
  - Raw fields `uvc_scr_sof` and `uvc_eof_scr_sof` (USB 1 ms frame counter) give the bus time per frame at the
    reservation that usbvideo picked for the requested rate:
    - `mf_1280x720_5`: 32 ms for 108 kB.
    - `mf_1600x896_5`: 33 ms for 150 kB.
  - Multiplied by the 30 fps the camera actually sends, that is 96% and 99% of the reservation. These are the only two C922 MF
    modes above 84%. The next is `1920x1080@5` at 84%, which is clean at 30 fps; RERUN measured its headroom as ~1.17x.
  - So the camera sends 30 fps frames into an isochronous reservation sized for 5 fps. In the two modes where that does not
    fit, it drops to 15 fps and tears frames.
  - This matches REPORT finding 20 (C922 1080p@5 delivered 5.01, 15.76 or 30.0 fps, non-deterministically).
  - The fault is still the camera's, but it is predictable from frame size × 30 fps against the selected alternate setting.
    It is not a fault "in these two modes" at random.
  - Also the device PTS pattern is a repeating triplet of 10.1 M, 40.0 M and 9.9 M ticks at 300 MHz (33.6, 133 and 33 ms),
    not a strict 33/133 alternation.
  - Section 3.6's "cannot confirm or rule out bandwidth" is superseded by this evidence.
- **F7 (C930e misses are all fast, from one switch from 20 to 30 fps): weakened.**
  - DS `848x480@20` is 19.55 fps (−2.3%, slow).
  - The MF range is +2.4% (`848x480@5`, 5.12) to +14.6%.
  - `mf_800x448_20` does switch once, at about 2.1 s (intervals 48/64 ms, then 32 ms). But `pyav_ds_1280x720_20` shows a short
    burst at 30 fps in the middle and then returns to 20, so the drift is bursty, not one transition.
- **F3 (PyAV falls back wherever a raw format shares the size and rate): weakened.** This holds in 119/120 C922 modes,
  118/119 C930e modes and 7/10 generic modes (checked against `descriptors.json` uncompressed frames).
  - Exceptions where YUY2 exists at the same size and rate but PyAV still got MJPEG:
    - `1600x896@7.5` on both Logitech cameras.
    - The generic camera's `352x288@30`, `640x360@30` and `640x480@30`.
  - So the fallback depends on the order of the caps, not only on whether a raw format exists.
- **F12 cause: weakened.** For C930e 2304x1296 and 2304x1536, `dwMaxBitRate` (238.9 and 283.1 Mbit/s) equals width × height ×
  16 bit × **5** fps, but the only frame interval is 4999998 (2 fps). At 2 fps the real rate is 95.6 and 113 Mbit/s, which
  fits High Speed. If usbvideo drops these modes on bit rate, it is reacting to an inconsistent descriptor field.
- **F15:** "PyAV" open-to-first-frame values 625 and 807 ms are the `ds` column, which holds only the PyAV MJPEG modes. PyAV on
  its own (`pyav_ds`, including the raw fallback modes) has medians of 647 (C922), 906 (C930e) and 399 ms (generic).
- **C922 pyav_ds cell:** 72 modes fail fps in total: the 17 PyAV MJPEG modes the analyst named, plus 55 raw-fallback modes.
  The cell is partial either way.
- **Real or artefact, C930e mf and ds:** I would call these **real** (MJPEG-specific rate drift, see F5), with the 3 s capture
  as the only harness factor. The AE-priority part of "mixed" does not hold.

### Harness bugs: verdicts on H1–H10

- **H1:** real. The code at `w_mjpeg.py:157` matches the description. The fix is right, and the offline re-rate confirms
  that the generic camera becomes yes. Keep the separate `rate_honoured` field: the existing downward rule already lets the C922
  720p@60 mode (30.55 fps, −49%) pass G-MJPEG.
- **H2:** real (`w_mjpeg.py:191`, `rating.py:157`). **The fix is partly wrong.** Under plan section 3, "no" means "no JPEG
  bytes", a property of the API. The Kiyo DS cells delivered nothing because of a device fault, so they should be **untested
  (device fault)**, not "no". Fold H2 into H3: 0 frames plus a device_error, timeout or OSError 5 after a device fault should
  rate untested, and "no" applies only when frames arrived and none were JPEG.
- **H3:** real, and the fix is right. The time wasted was 27 × 2 calls of 1–10 s each.
- **H4:** the bug is real: controls are neither recorded nor pinned (`w_mjpeg.py:109-128`), and `ck.get_controls` and
  `ck.set_controls` exist at `capkit.py:214` and `:223`. **The expected effect is weakened** (see F5): pinning priority to 0 is
  unlikely to change the C922 or C930e MJPEG rates. Also, W-CTRL-LIST reports the priority range as min 0, max 0 through
  IAMCameraControl with a value of 1, so setting it may fail. Record controls per camera anyway. Also record the camera's
  YUY2 rate as a control experiment.
- **H5, H6, H8, H9 and H10:** real, and the code is as described (`capkit.py:338-341` takes the first `limit` saved frames;
  `pyav_ds.py:625` has `"not measured (separate process)"`; `w_mjpeg.py:214-215` uses the tool's `ok` flag). The CPU values
  cluster at multiples of about 0.515 (0.513–0.521, 1.028–1.041, 1.54).
- **H7:** real (`wincam.cpp:945-952`). DS pin 1 has 68 caps entries that collapse to 2 modes of 0x0. A simpler and more robust
  fix: when the format block is not recognised, fall back to `VIDEO_STREAM_CONFIG_CAPS.InputSize` or `MaxOutputSize`, and log
  the `formattype` GUID. Parsing `KS_H264VIDEOINFO` can come on top.

### Missed by the analyst

- **M1 (harness gap, medium): W-MJPEG does not record the alternate setting or bus time per mode.** `frames.jsonl` already
  holds `uvc_scr_sof` and `uvc_eof_scr_sof` on tier-1 cameras. Fix: in `_api_summary` (`w_mjpeg.py:61-96`), add
  `bus_ms_per_frame` (median of eof_sof − sof, mod 2048) and `reservation_utilisation_at_measured_fps`, plus the open-pipe alt
  from the hub snapshot used by W-TOPO. This would have classified the two corrupt C922 modes automatically. Re-run: part
  of the C922 W-MJPEG re-run.
- **M2 (finding): in the corrupt C922 modes, host arrival times hide irregular capture times.** QPC arrivals are an even
  64 ms (`qpc_ns`), but the device PTS steps are 33/133/33 ms. Arrival time misplaces capture time by up to about 100 ms.
  This is relevant to G-TS, and it is a reason to prefer UVC PTS where it exists.
- **M3 (finding): the C922 YUY2 and MJPEG rate behaviour differs** (see F5). This is free data from the PyAV fallback.
  W-MJPEG should report it as a measured control experiment instead of discarding it as `format_fallback`.
- **M4:** the plan question "Native MJPEG at all resolutions?" should carry one more caveat. On the C922, requesting a rate
  below 30 at large sizes is unsafe: you get 30 fps, or 15 fps with torn frames. Request 30 and decimate on the host.

### Re-run plan, adjusted

1. **Offline:** apply H1, H9 and the corrected H2/H3 rule. Expected: generic yes ×3; Kiyo untested ×3.
2. **Kiyo:** replug (attended), then W-MJPEG on the Kiyo only.
3. **C922 and C930e:** W-MJPEG with M1 (bus time and alt), H4 (record controls; priority 0 is optional), H5 and H6.
   Prediction from this verification: the C922 sub-30 MJPEG modes still deliver 30 fps with priority 0, and the two @5
   modes stay corrupt for as long as the reservation is sized for 5 fps.
