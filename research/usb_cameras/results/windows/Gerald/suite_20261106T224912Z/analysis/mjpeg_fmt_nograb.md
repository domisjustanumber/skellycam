# W-MJPEG, W-FMT and W-FMT-NOGRAB analysis: suite run 20261106T224912Z on Gerald (run 2)

Scope: W-MJPEG (G-MJPEG, 12 cells, in-scope modes only), W-FMT (`fmt_equivalence`, 1 cell) and W-FMT-NOGRAB
(`fmt_nograb`, 18 cells), plus `mjpeg_modes.json` and `mode_alt_cache.json`. Windows 11 build 26300, 2026-11-06.

- W-FMT ran at 22:49:27Z (17:49 local).
- W-FMT-NOGRAB ran from 22:49:29Z to 22:52:14Z (165 s, hold 2500 ms).
- W-MJPEG ran last, from 00:11:01Z to 00:13:20Z (139 s, 3 s per mode, 10 s for each camera's default mode).

Labels: **measured** means the value comes from a named file and field. **Inferred** means it is my reading of measured
data or code. Paths are relative to the results folder unless they start with `suite/` (the suite code) or `raw/`
(`C:/Users/Dom/Documents/skellycam-raw/results/windows/Gerald/suite_20261106T224912Z`). No camera was opened. No suite file
or result file was changed.

## 1. Short answers

- **Native MJPEG at every in-scope resolution?** **Yes, through MF and through PyAV DirectShow, on the C922 (5 modes),
  the C930e (3 modes) and the generic camera (2 modes)** (measured, `W-MJPEG.json` verdicts, 9 × yes).
  - Every mode negotiated MJPG with a verified MF readback.
  - 100% of frames have SOI, EOI and the requested SOF0 size.
  - Strict decode is 100%, except the generic camera's 1080p mode, which passes only under lenient decode with its known
    quirk.
  - The MF and DS header SHA-1 is equal in 10/10 modes.
  - The Kiyo is **untested** in W-MJPEG. The device-fault gate held it from W-MULTI on (00:04:02Z, 0x8007001F, plug-in age
    211.6 min).
- **What changed against run 1 (12 × partial)?**
  - **Mostly the mode scope.** Every failing mode in run 1 was below 30 fps (C922 @5 corruption, C922 30 fps at sub-30
    requests, C930e drift, generic @25). In run 1 the same in-scope modes already passed on all three working cameras.
  - **The fixes:**
    - The UVC PTS reference and the symmetric reference let the C922's 720p@60 mode (30.55 fps) and the generic
      camera's 17.15 fps pass on their real rate.
    - The fault gate turns the Kiyo cells into untested instead of partial.
    - The DS H.264 parse (H7) makes MF equal DS on every C930e format.
  - **The cameras:** one real change. The generic camera now runs at **17.15 fps instead of 25.7** (measured). This
    happened in the evening, under lamplight, and is inferred to come from auto-exposure.
- **Do MF and DS list the same modes (W-FMT)?** Yes, on all four cameras, for every format. That now includes the
  C930e's 238 H.264 modes on DS (run 1: 14 modes of size 0x0).
- **FMT-NOGRAB: which method identifies formats without grabbing the camera?**
  - **The hub IOCTL** is the only method that is complete against the descriptors on 4/4 cameras, in ~80 ms.
  - **MF, with ActivateObject and no Start**, is complete on 3/4 cameras and is the best "what Windows will open" list.
    It misses only the C930e's two YUY2 2 fps modes, which no Windows API exposes.
  - All of them (hub IOCTL, MF, DS, ffmpeg):
    - start no stream (the pipe sampler is validated);
    - disturb neither another MF stream nor another DS stream;
    - do not block a third process's open.
  - **ffmpeg `-list_options`** is incomplete wherever a size has more than two rates. It prints only the minimum and
    maximum rate per caps entry, so on the C922 it hides 1280x720@30 MJPEG.

## 2. Every rating cell

### 2.1 W-MJPEG (G-MJPEG): 9 × yes, 3 × untested

Source: `W-MJPEG.json` `verdicts["G-MJPEG|<key>|<api>"]`, with `.criteria` and `.evidence.modes[]` (fields `negotiated`,
`valid_ok`, `sof_matches`, `fps_ok`, `fps_reference_source`, `header_equal_across_apis`, `ok`).

The ratings come from `suite/common/rating.py:232-319` (`rate_mjpeg`) plus `suite/windows/tests/w_mjpeg.py:292-345`, which adds
the scope criterion and the "(in-scope modes)" label. "Yes" needs every mode `ok`, an fps reference and a cross-API hash.

The `ds` column is identical to `pyav_ds` in every cell. `routes` = `["pyav_ds"]`, and `pyav_format_fallback_modes` = [] on
all three working cameras. No in-scope mode has a raw format at the same size and rate on these cameras, so PyAV never fell
back and the ffmpeg CLI route was never used (measured; inferred cause).

| Camera | API | Rating | Criteria and values (measured) | Real or artefact |
| --- | --- | --- | --- | --- |
| C922 | mf | yes (in-scope) | negotiates 5/5; valid 5/5 (strict 1.0); SOF0 1.0; fps: reference = UVC PTS in 5/5 (`reference_sources {"uvc_pts": 5}`); header SHA-1 equal; 5/5 in-scope modes captured (115 of 120 excluded) | **Real** |
| C922 | ds | yes (in-scope) | same as mf (route pyav_ds) | **Real** |
| C922 | pyav_ds | yes (in-scope) | same | **Real** |
| Kiyo | mf | untested (device fault) | criteria `measured` null, `camera answered` false (0x8007001F since 00:04:02Z); all 4 modes `skipped: untested: device fault since ...`; start-of-test re-probe failed 0x8007001F at `first_sample` (`measurements.device_faults.probes_by_test["W-MJPEG"]`) | **Real** device fault. The scope criterion "met: true, 4/4 modes" in the same cell is a **harness bug** (B1). |
| Kiyo | ds | untested (device fault) | same | same |
| Kiyo | pyav_ds | untested (device fault) | same | same |
| Generic | mf | yes (in-scope) | negotiates 2/2; valid 2/2 (1080p strict 0.0, lenient 1.0, `known_quirk` "extraneous bytes before EOI"); SOF0 1.0; fps reference `both_apis_agree` 17.15 (nominal 30) in 2/2; header equal | **Real** for the API. The camera delivers 57% of the requested rate (`rate_honoured_camera.not_honoured` = both modes). The summary label hides that (B4). |
| Generic | ds | yes (in-scope) | same | same |
| Generic | pyav_ds | yes (in-scope) | same | same |
| C930e | mf | yes (in-scope) | negotiates 3/3; valid 3/3; SOF0 1.0; fps reference `both_apis_agree` (30.02, 29.94, 30.04); header equal; rate honoured 3/3 | **Real** |
| C930e | ds | yes (in-scope) | same; DS 1600x896@30 is 29.84 fps (within 2% of 29.94) | **Real** |
| C930e | pyav_ds | yes (in-scope) | same | **Real** |

### 2.2 W-FMT (`fmt_equivalence`): yes

Source: `W-FMT.json` `verdicts.fmt_equivalence.criteria`.

- MJPEG sizes and discrete rates are equal in the descriptors, MF and DS: C922 120 (17 sizes), Kiyo 28 (4), generic 10
  (5), C930e 119 (17).
- `mf_missing` and `ds_missing` hold no MJPEG mode on any camera.
- `errors` = [].
- **Real.**

The informational criterion "every format equal" is false, but only on the C930e:

- `mf_missing` = `ds_missing` = YUY2 2304x1536@2 and 2304x1296@2.
- 238 H.264 modes are listed as `extra`. They are not in the standard descriptors.
- `diff.mf_vs_ds` = `{only_mf: [], only_ds: []}`: MF and DS now agree on every format.

### 2.3 W-FMT-NOGRAB (`fmt_nograb`): 11 × yes, 7 × no

Source: `W-FMT-NOGRAB.json` `verdicts["fmt_nograb|<key>|<method>"]`, with per-condition data in
`measurements.cameras[key].results[method][condition]`. The ratings come from `suite/common/rating.py:587-679`
(`rate_fmt_nograb`):

- **no** = incomplete when idle, or a stream started;
- **yes** = complete in all 3 conditions, with no disturbance, no stream and no block, all measured.

Every condition was tested on every camera. `pipe_sampler_validated` = true on 4/4 cameras.

| Camera | hub_ioctl | mf | ds | ffmpeg |
| --- | --- | --- | --- | --- |
| C922 | **yes** | **yes** | **yes** | **no (incomplete)**: MJPEG 34/120, raw 35/98 |
| Kiyo | **yes** | **yes** | **yes** | **no (incomplete)**: MJPEG 8/28, raw 16/56 |
| Generic | **yes** | **yes** | **yes** | **yes**: 10/10 and 4/4 (every size has at most 2 rates) |
| C930e | **yes** | **no (incomplete)**: raw 97/99 | **no (incomplete)**: raw 97/99 | **no (incomplete)**: MJPEG 34/119, raw 33/99 |
| all | opencv: **no (cannot list without opening capture)** | winrt: **no (cannot list without opening capture)** | | |

Per criterion (measured, every camera and condition unless noted):

- **Complete:**
  - hub_ioctl, MF and DS list exactly the descriptor set (`comparison.exact` true).
  - The C930e is the exception for MF and DS: both miss the 2 YUY2 2304-wide modes, in all 3 conditions.
  - ffmpeg misses every rate between each caps entry's minimum and maximum (`comparison.per_class.*.rates_only_missing`).
    On the C930e it also misses the two 2304-wide sizes.
- **Disturbance:**
  - `disturbed` = false in all 32 streaming windows.
  - Window max interval: C922, C930e and Kiyo ≤ 49.04 ms (baseline max 47.97–80.27 ms, threshold ~96 ms); generic
    ≤ 65.29 ms (17.15 fps, threshold ~191 ms).
  - The alternate setting never changed during a listing (`pipe_change.changed` false; alts: C922 9, C930e 11, Kiyo 1,
    generic 1).
- **Stream started (idle):** false for every method. For example, the MF hold had 3–9 samples inside the hold, all with
  `active` false and `current_alt` 0.
- **Blocking (idle):** `blocked` false for every method. Third-process open to first frame during the MF/DS hold vs the
  control open:
  - C922 322/331 vs 330 ms;
  - C930e 501/515 vs 516 ms;
  - generic 109/131 vs 133 ms;
  - Kiyo 906/912 vs 914 ms.
- **opencv and winrt:** rated "no" by assertion (`NOT_IMPLEMENTED` text in `suite/windows/tests/w_fmt_nograb.py:55-61`). They
  were **not measured** (B10).

Real or artefact:

- hub_ioctl, MF and DS "yes": **real**.
- ffmpeg "no": **real**. It is a limitation of ffmpeg's dshow `-list_options` (raw stderr shows
  `vcodec=mjpeg min s=1280x720 fps=5 max s=1280x720 fps=60.0002`), not of the parser.
- C930e MF/DS "no": **real per the rule, but the rule blames the method for an OS behaviour** (B8; section 3.6).

## 3. Quantitative findings

### 3.1 MJPEG per camera (measured, `W-MJPEG.json` `measurements.cameras[key].modes[].apis.{mf,pyav_ds}`)

| | C922 | C930e | Generic | Kiyo |
| --- | --- | --- | --- | --- |
| In-scope / advertised MJPEG modes | 5 / 120 | 3 / 119 | 2 / 10 | 4 / 28 (gated) |
| MF negotiated + readback ok | 5 | 3 | 2 | – |
| SOI, EOI, SOF0 = request, all frames | 1.0 | 1.0 | 1.0 | – |
| Strict decode, 8 frames spread across the capture (`checked_seq`) | 1.0 | 1.0 | 720p 1.0; 1080p 0.0 (lenient 1.0, quirk) | – |
| MF == DS header SHA-1 | 5/5 | 3/3 | 2/2 | – |
| Delivered fps, MF / DS | 30.00 (×4); 720p@60: 30.54 / 30.57 | 30.02–30.05 / 29.84–30.03 | 17.15 / 17.15 | – |
| Device UVC PTS rate (tier 1) | 30.00 (×4), 30.55 at @60 | – (metadata off) | – (metadata off) | – |
| `rate_honoured` false | 720p@60 | none | both modes | – |
| MF CPU, 10 s default mode (resolution 0.16%) | 2.49% | 1.72% | 0.94% | – |
| PyAV CPU, 10 s default mode | 1.25% | 1.87% | 0.78% | – |
| CPU, 3 s modes (resolution 0.52%) | MF 0–3.6, PyAV 0.5–2.1 | MF 0.5–3.1, PyAV 1.0 | MF 1.0, PyAV 0.5 | – |
| MF open to first frame | 298–333 ms | 498–515 ms | 83–99 ms | – |
| PyAV open to first frame | 596–620 ms | 803–814 ms | 397–401 ms | – |
| MF reader release (close) | 292–350 ms | 353–354 ms | 260–264 ms | – |
| Recaptures (H5) | 0 | 0 | 0 | – |

Notes (measured unless labelled):

- **CPU scope differs between the APIs.** MF is `GetProcessTimes` of the wincam child. PyAV is `time.process_time` of the
  whole Python helper (`cpu_method`). Neither includes the Frame Server service (inferred), so MF vs DS differences below
  ~1% are not meaningful. One 3 s MF mode reads exactly 0 (C922 960x720, below one 15.6 ms tick).
- **C922 1280x720@60:**
  - It delivers 30.55 fps on both APIs. The device PTS gives the same rate, so this is the camera, not the host.
  - `auto_exposure_priority` = 1 before and after the sweep (`control_state.before/after`). Nothing was set (H4 policy).
  - The run-1 hypothesis "60 fps needs RightLight off" is still untested.
- **Generic at 17.15 fps** (run 1: 25.7):
  - Already at 17.15 at 22:49Z in W-FMT-NOGRAB, in both streamers (`fps_measured` 17.149 MF, 17.134 PyAV). So it is not
    caused by its 00:10:45Z re-arrival (during W-MULTI, 16 s before W-MJPEG).
  - The sample image shows warm lamplight in run 2 against cool daylight in run 1, at the same output mean luma (145 vs
    144; computed from `W-MJPEG/samples/usbcamera_*_mf_1280x720_30.jpg` of both runs).
  - Exposure is in auto mode and `powerline_frequency` = 0.
  - **Inferred:** auto-exposure lengthened the frame period (~58 ms) in the darker scene.
- **The header SHA-1 per mode is identical to run 1** on all 10 working modes. Examples: C922 720p `89d46b19`, C930e 1080p
  `08187199`, generic 1080p `08fda7f6`. The C922 720p@30 and 720p@60 share the same header. So the JPEG headers are
  deterministic per camera and size, across APIs and across runs.

### 3.2 Bus utilisation (C922 only: tier 1 with SCR; the C930e and generic have metadata off, and the Kiyo was gated)

Measured: `measurements.cameras["046d:085c..."].bus_utilisation_top`, and `mode_alt_cache.json` for the alternate setting.

| Mode | Alt (cache, W-MULTI learn) | Bus ms per frame (p90) | Utilisation at delivered fps |
| --- | --- | --- | --- |
| 1280x720@30 | 9 (992×2) | 6 (6) | 0.18 |
| 960x720@30 | 8 (800×2) | 6 (6) | 0.18 |
| 1280x720@60 | 11 (1020×3) | 3 (3) | 0.09 (at 30.55 fps) |
| 1600x896@30 | – | 6 (7) | 0.18 |
| 1920x1080@30 | 11 (1020×3) | 7 (7) | 0.21 |

Inferred:

- Every in-scope C922 mode uses at most ~21% of its isochronous reservation (1 ms resolution, so ±1 ms per frame).
- The run-1 corruption mechanism (96–99% utilisation at @5) cannot occur at ≥ 30 fps on this camera.
- At @60, usbvideo reserves alt 11 although the camera sends 30 fps, so half of that reservation is unused bandwidth.
  This is relevant to G-BW: a 720p@60 request reserves for 60 and gets 30.

### 3.3 FMT-NOGRAB per method (measured, `W-FMT-NOGRAB.json`)

| Method | Complete vs descriptors | Listing time | Holds the device | Stream / alt during the hold | Disturbs another stream | Blocks a third open |
| --- | --- | --- | --- | --- | --- | --- |
| hub_ioctl | 4/4 cameras, all formats incl. H.264 on the Kiyo; not the C930e's XU H.264 (not in the descriptors) | 70–87 ms (`elapsed_s`; 5–8 EP0 requests, `info.requests`) | no | none (back-to-back samples) | no | no |
| mf (ActivateObject + GetNativeMediaType, no Start) | 3/4 (C930e −2 YUY2) | 34–61 ms to HOLD_BEGIN (`listing_ms_before_hold`, includes process start) | source + reader for 2.5 s | none, alt 0 | no | no (delay −24 to −8 ms) |
| ds (BindToObject + IAMStreamConfig + GetFrameRateList) | 3/4 (C930e −2 YUY2) | 29–47 ms to HOLD_BEGIN | bound filter for 2.5 s | none, alt 0 | no | no (delay −3 to +1 ms) |
| ffmpeg -list_options | 1/4 (generic only) | 348–374 ms | – | none | no | no (not delayed; B6) |

Other measured facts:

- **MF and DS list completely while another process streams the camera through MF or through DS** (complete = true in the
  streaming conditions). This holds on all four cameras for MF and DS on three. The C930e lists its 97 OS-exposed raw
  modes in every condition.
- **Pipe sampler:**
  - It was validated by a positive control. `conditions.streaming_*.baseline_pipe_active` = true on every camera: the same
    `win_topology` sample saw the streamer's pipe (C922 alt 9, C930e alt 11, Kiyo alt 1, generic alt 1).
  - So "no pipe during the MF/DS hold" is evidence, not a blind spot.
  - Sample spacing during holds is ~175 ms (120 ms wait plus a ~55 ms collect). The 30–60 ms listing phase before the
    hold is not resolvable (inferred, B11).
- **A concurrent MF open slowed the hub IOCTL**:
  - process time with the open (`methods[*].tag == "blocking"` in `raw/W-FMT-NOGRAB/*/idle/session.json`): C922 208 ms,
    C930e 511 ms, Kiyo 313 ms;
  - process time alone: 74–84 ms.
  - Inferred: EP0 GET_DESCRIPTOR requests serialise behind usbvideo's control transfers during stream start. No camera
    was disturbed.
- **ffmpeg incompleteness:**
  - C922: 17 sizes × {min, max} = 34 of 120 MJPEG modes.
  - Kiyo: 4 × 2 = 8 of 28.
  - C930e: 34 of 119.
  - On the C922 and Kiyo, 1280x720 is printed as "fps=5 … fps=60.0002", so **720p30 MJPEG never appears**. A UI built on
    ffmpeg would not offer the default mode.
- **C930e YUY2 2304x1296@2 and 2304x1536@2** (`descriptors/descriptors.json`):
  - Both are absent from MF, DS and ffmpeg. Only the hub IOCTL sees them.
  - Their `dwMaxBitRate` is 238.9 and 283.1 Mbit/s, which equals w×h×16×**5** fps. Yet their only interval is 4999998
    (2 fps), which needs 95.6 and 113.2 Mbit/s.
  - YUY2 1920x1080@5 (165.9 Mbit/s) is exposed.
  - Inferred: usbvideo drops a frame whose `dwMaxBitRate` exceeds the High-Speed isochronous maximum (3×1024 B × 8000/s
    = 196.6 Mbit/s). The descriptor is inconsistent; the modes would fit at 2 fps.
- **Kiyo coverage before its fault:**
  - W-FMT and the whole of W-FMT-NOGRAB ran at plug-in age 137–140 min, with no error: 112 modes (MJPG, YUY2, NV12, H264,
    28 each).
  - Its MF streamer delivered MJPEG 1280x720@30 at 30.00 fps over 11.6 s: 349 frames, SOI/EOI/SOF0 100%
    (`raw/.../usbvideodevice_1532-0e05_4/streaming_native/streamer_1/frames.jsonl`). That is MJPEG evidence outside the
    W-MJPEG rating.
  - **Its PyAV DirectShow streamer got raw `yuyv422` instead of MJPEG** (`format_fallback` true, 29.1 fps). This
    reconfirms REPORT.md line 22 for the in-scope default mode.
  - Kiyo control-open first frame: 914 ms (others 133–516 ms).

### 3.4 Which method best identifies formats without grabbing the camera

Inferred from 3.3:

- **For the descriptor truth and the bandwidth cache, use the hub IOCTL.**
  - It is complete everywhere, ~80 ms, with no camera-driver involvement, no hold, no stream and no blocking.
  - It also gives `dwMaxBitRate` and the alternate settings.
  - It does send standard EP0 requests (`suite/windows/helpers/win_descriptors.py:8`).
  - It over-reports modes Windows cannot open (C930e 2304-wide YUY2), and it does not see vendor XU formats (C930e H.264).
- **For the list a user can actually open, use MF with ActivateObject + GetNativeMediaType and no Start.**
  - It is exact against the OS-exposed set, and it works while another process streams the camera.
  - It holds no pipe, and it does not delay another open.
  - DS is equivalent.
- **Do not use ffmpeg** for discovery. **OpenCV and WinRT cannot list without opening a capture** (asserted, not
  measured).

## 4. Comparison with run 1 (suite_20261106T181941Z)

| Item | Run 1 | Run 2 | Why it changed |
| --- | --- | --- | --- |
| G-MJPEG cells | 12 × partial | 9 × yes, 3 × untested | **Scope:** every run-1 failure was a sub-30 mode (C922 2 corrupt @5 modes and 100 sub-30 modes at 30 fps, C930e 9–10 drifting modes, generic 5 @25 modes). The same in-scope modes passed in run 1 (computed from run-1 `W-MJPEG.json`). **Fixes:** UVC PTS reference (C922 @60), symmetric reference, fault gate (Kiyo). |
| Kiyo in W-MJPEG | 0/28 delivered: the first stream hung at `reader_release`, then 0x8007001F; plug-in age ~224 min | gated: faulted in W-MULTI at 211.6 min, before W-MJPEG | **Camera:** the same signature at the same age (~3.5 h after plug-in) in both runs. Fix H3 turned it into untested. |
| Generic fps | 25.7 at @30 (and @25) | 17.15 at @30 | **Camera/scene** (inferred: evening lamplight, AE). Not a harness change. |
| C922 720p@60 | 30.53/30.57 (passed by the downward rule) | 30.54/30.57, reference UVC PTS 30.55 | Same camera behaviour. Rule now explicit (`rate_honoured` false). |
| C930e in-scope modes | 30.04–30.12 | 29.84–30.05 | Same. |
| Header SHA-1, MF == DS | 249/249 | 10/10, identical hashes to run 1 | Same. |
| MF / PyAV first frame | C922 332 / 616–632, C930e 521–524 / 795–807, generic 82–86 / 396–403 | 298–333 / 596–620, 498–515 / 803–814, 83–99 / 397–401 | Same. |
| Decode sample | first 8 saved frames (H6) | 8 spread across the capture (`checked_seq`) | Fix H6. |
| Bus time per mode | not recorded | C922 per mode (3.2) | Fix M1. |
| Control state | not recorded | read before and after per camera | Fix H4 (read only). |
| ffmpeg-route CPU (H8), recapture (H5), raw-fallback control (M3) | – | **not exercised** (0 fallbacks, 0 recaptures in scope) | Scope. The Kiyo is the only camera with raw formats in scope, and it was gated. |
| W-FMT C930e DS H.264 | 14 modes of 0x0 (`header_kinds` other) | 238 modes, `H264VI`, MF == DS | Fix H7. |
| FMT-NOGRAB | did not exist | 18 cells | New test. |

Not re-checked in run 2 (out of scope by design): the C922's corrupt @5 modes, the C922's 30 fps at sub-30 requests, the
C930e's sub-30 drift, and the generic camera at @25. Those findings stand from run 1 only.

## 5. Harness bugs and gaps (remaining)

| ID | Severity | File:line | Bug | Fix |
| --- | --- | --- | --- | --- |
| B1 | low (wrong criterion text) | `suite/windows/tests/w_mjpeg.py:303-313` | "every in-scope MJPEG mode was captured" uses `info["selected"] >= target`, which counts planned modes, not captured ones. The 3 gated Kiyo cells say `met: true, "4/4 modes"` with 0 modes captured. | `n_cap = sum(1 for r in mode_rows if not r.get("skipped") and any((a or {}).get("frames") for a in r["apis"].values()))`; `met = n_cap >= target > 0`; detail `f"{n_cap}/{target}"`. |
| B2 | low (misleading evidence) | `suite/windows/tests/w_mjpeg.py:229-243` | Skipped (gated) modes go through `_rate_rows` with empty `apis`, so `evidence.modes[]` shows `negotiated: false, is_jpeg: false` and `fps_reference_sources {"nominal": 4}` for modes never attempted. The rating is unaffected because the fault check comes first. | When `row.get("skipped")`, emit `negotiated/is_jpeg/fps_ok: None` plus `skipped`, or leave those rows out of `rate_mjpeg` and list them under `evidence.skipped_modes`. |
| B3 | medium (reporting) | `suite/windows/tests/w_mjpeg.py:322-323` (label); `summary.md` G-MJPEG table | The label is "yes (in-scope modes)" even when the camera delivers 57% of the requested rate (generic 17.15 of 30) or 51% (C922 @60). `rate_honoured_camera` holds this, but the summary never shows it. With the `both_apis_agree` reference on tier-0 cameras, any rate that both APIs share passes. | When `rate_honoured_camera.not_honoured` is not empty, label "yes (in-scope modes; rate not honoured in N)". On tier-0 cameras with an `apis_agree` reference more than 2% off nominal, add the reason to `note` (camera AE, or a host cause common to both APIs: it cannot be told apart without device PTS). |
| B4 | low (CPU comparability) | `suite/windows/tests/w_mjpeg.py:524`; `suite/windows/helpers/pyav_ds.py` (process_time) | 3 s modes have a 0.52% CPU resolution (one mode reads 0), and the MF and PyAV scopes differ. With ≤ 5 in-scope modes per camera, the time saving is no longer needed. | Capture every in-scope mode for `CPU_WINDOW_S` (10 s; ~+3 min per run). Optionally add the Frame Server service CPU delta (GetProcessTimes on the FrameServer svchost PID) to both APIs. |
| B5 | low (doc) | `suite/windows/tests/w_mjpeg.py:24-25` vs `suite/windows/capkit.py:586-607` | The docstring says the reference is "both APIs agree, else UVC PTS". The code prefers UVC PTS first. | Fix the docstring. |
| B6 | low (unmeasured part of a "false") | `suite/windows/tests/w_fmt_nograb.py:266-274` | For no-hold methods (hub_ioctl, ffmpeg), `delay_vs_control_ms` and the overlap with the method are computed only when a hold exists. `blocked` false comes from `during_ok` alone. The raw session shows a real overlap and no delay (ffmpeg: blocker start +3 ms, first frame +349 ms, ffmpeg end +367 ms; first frame 333 vs 330 ms control), so no rating changes. | Always compute `late = blk.o2ff - control.o2ff`. Record `overlap = blk.t_start_ns < proc.t_end_ns`. If there is no overlap, return `blocked: None`. Apply `DELAYED_OPEN_MS` to `late` for no-hold methods too. |
| B7 | low (misnamed field) | `suite/common/nograb.py:121` | `sizes_missing` lists sizes with at least one missing rate, even when the size is listed (ffmpeg C922: `sizes_listed` 17/17, but `sizes_missing` = 1024x576, 1280x720, …). | Rename it to `sizes_with_missing_rates`, and add `sizes_missing = ref_sizes - listed_sizes`. |
| B8 | medium (rating semantics) | `suite/common/rating.py:644-649` (idle incomplete → no) with `suite/windows/tests/w_fmt_nograb.py:437` (reference = raw descriptors) | C930e MF and DS rate "no (incomplete)" for 2 YUY2 modes that usbvideo exposes to **no** API (MF, DS and ffmpeg all miss them). The deficit belongs to the OS, not to the method, and the plan's purpose ("formats for the UI") is better served by MF's list. | Build an "OS-exposed reference" = descriptor modes ∩ (MF ∪ DS listing). Rate MF/DS completeness against it, and report `descriptor_only_modes` (with `dwMaxBitRate` against the bus maximum) as a separate camera/OS finding. Keep hub_ioctl rated against the full descriptors. |
| B9 | low (sensitivity) | `suite/common/nograb.py:37-39`, `:167-171` | The gap threshold max(3×p50, 1.5×max, max+25 ms) is ~96 ms at 30 fps, so one dropped frame (64–80 ms on the 16 ms grid) is not a disturbance. The measured window maxima are ≤ 49 ms, so nothing was missed in this run. | Add `single_drop` = any interval > max(1.6×p50, baseline max + 8 ms). On tier-1 cameras, use device-PTS steps > 1.5 periods. |
| B10 | low (claim not measured) | `suite/windows/tests/w_fmt_nograb.py:55-61`, `:558-559` | OpenCV and WinRT are rated "no" by assertion. WinRT has the static `MediaCapture.IsVideoProfileSupported` / `FindAllVideoProfiles(deviceId)`, which needs no InitializeAsync, although most UVC cameras expose no profiles (inferred). | Label these cells "no (asserted, not measured)". Optionally add a profile probe that records `IsVideoProfileSupported` per camera. |
| B11 | low (resolution) | `suite/windows/helpers/nograb_session.py:289`, `:125-137` | During hold methods the sampler period is ~175 ms. The pre-hold listing phase (30–60 ms) is not sampled. | Sample back to back (interval 0) for the first 300 ms of every method too, as for no-hold methods. |

## 6. What to re-run (no harness re-run needed for the ratings above)

1. **Kiyo W-MJPEG:** after an attended replug, early in the session (< ~3 h of plug-in age; both runs faulted at ~3.5 h).
   Use `run_suite.py --only W-MJPEG --camera 1532:0e05`. This is also the only in-scope case that exercises the ffmpeg CLI
   route and its CPU (Kiyo PyAV falls back to YUY2 at 720p30).
2. **Generic camera:** repeat W-MJPEG under daylight, or with manual exposure, to confirm that 17.15 against 25.7 is
   auto-exposure (record exposure while streaming).
3. **Offline re-rate** after B1, B3 and B8 (no camera): Kiyo cells unchanged (untested); generic labelled "rate not
   honoured"; C930e MF/DS FMT-NOGRAB becomes yes against the OS-exposed set, with 2 descriptor-only modes reported.


## Verifier notes

Adversarial check, 2026-11-06. I recomputed every number above from `W-MJPEG.json`, `W-FMT.json`, `W-FMT-NOGRAB.json`,
`descriptors/descriptors.json`, `mode_alt_cache.json`, `run_suite.json`, run 1's `W-MJPEG.json`/`W-FMT.json`/`reanalysis/W-MJPEG.json`
and the raw `W-FMT-NOGRAB/*/*/session.json` and `streamer_1/frames.jsonl`, using scripts. I also read the cited code. No camera
was opened and no suite or result file was changed (this section is the only edit).

### Verdicts on the findings

| ID | Verdict | Note |
| --- | --- | --- |
| F1 | confirmed | 9 yes and 3 untested. SOI, EOI and SOF0 are 1.0, and header SHA-1 is equal in 10/10 modes. MF readback `readback_hr` is 0 in 10/10. |
| F2 | **weakened** | Run 1 in-scope modes: 0 failures on the C922, C930e and generic (run-1 `W-MJPEG.json` `evidence.modes[].ok`). Both in-scope sub-nominal rates (C922 @60 at 30.55, generic at 17.15) are *below* nominal, so run 1's downward rule would already accept them (inferred from the capkit docstring "the old rule accepted only below", and run 1 passed C922 @60). **No fix changed an in-scope outcome.** Partial became yes only because of the mode scope, and the Kiyo became untested only because of the fault gate. The UVC PTS and symmetric references change the `fps_reference_source` label, not the result. |
| F3 | **weakened** | The fps numbers are right. FMT-NOGRAB streamers: MF 17.149 and PyAV 17.134 fps, but at 22:51:08Z and 22:51:21Z, not 22:49Z. The analyst missed that the generic camera **also re-arrived at 22:26:45Z, before run 2 started** (`run_suite.json` `arrivals_since_previous_run`; in run 1 it re-arrived at 18:17:09Z, 2.5 min before that run). The timing argument therefore excludes only the 00:10:45Z re-arrival. Mean luma is 145.4 (run 1) and 144.0 (run 2), but the generic camera's mean RGB is almost neutral in both runs (145/145/149 against 144/143/148; WB manual 4500). The warmer scene shows mainly on the auto-WB C922 and C930e samples. The exposure readback is -7 (the minimum) in auto mode before and after; this is probably not the live value and neither supports nor refutes the AE hypothesis. The cause stays inferred. |
| F4 | confirmed | `fps_reference` is 30.5545 (uvc_pts). AE priority is 1 before and after. Cache: 720p@60 alt 11 (1020x3), and 1080p30 also alt 11. Utilisation at @60 is 0.092, so ~91% of that reservation is idle, not "half". |
| F5 | confirmed (reason incomplete) | Bus ms are 6/6/3/6/7 (p90 6/6/3/7/7) and utilisation 0.18–0.21. **The Kiyo has no bus data even when ungated:** its metadata is on, but `uvc_scr_sof` = 0 in all 349 frames of its FMT-NOGRAB MF streamer (`raw/.../usbvideodevice_1532-0e05_4/streaming_native/streamer_1/frames.jsonl`). |
| F6 | confirmed | MF 2.49/1.72/0.94%, PyAV 1.25/1.87/0.78%. In the 3 s modes the resolution is 0.517–0.525% and C922 960x720 MF reads 0. `cpu_method`: MF uses GetProcessTimes on the child, PyAV uses process_time on the whole Python process. |
| F7 | confirmed | Header SHA-1 is identical to run 1 in all 10 modes. Minor: run 1's C922 MF first frame is 314–333 ms, not 332. |
| F8 | **weakened** | MF == DS (`mf_vs_ds` empty, DS pin 1 `H264VI`, 454 = 454) is correct. But "238 H.264 modes" are **119 size/rate modes listed under two subtypes** (`H264` 119 + `MFVIDEOFORMAT_H264_ES` 119). |
| F9 | **weakened** | The 70–87 ms and 5–8 requests are correct. But the hub IOCTL completeness is **circular**: the FMT-NOGRAB reference *is* the W-FMT hub IOCTL descriptor cache (`measurements.cameras[*].reference.source` = "USB descriptors (W-FMT shared cache, hub IOCTL)"; `w_fmt_nograb.py:437`; the same `win_descriptors.py`). "Complete on 4/4" only shows that it repeats under load. The informative parts are works-while-streaming, no disturbance and no stream. |
| F10 | confirmed | Listing time before the hold: MF 34–61 ms, DS 29–47 ms. Delay: MF −24.2 to −8.3 ms, DS −2.7 to +0.8 ms. Caveat in the new finding V3: the "no pipe during the hold" evidence covers only part of the hold. |
| F11 | confirmed | There is also a positive control in the idle condition: raw samples flagged `blocker_running` see the third-process open's pipe (C922 alt 9, C930e alt 11, Kiyo and generic alt 1) in every idle session. |
| F12 | confirmed | 32/32 windows undisturbed. Window max ≤ 49.04 ms (generic ≤ 65.29 ms). Baseline max 47.97–80.27 ms. Alt unchanged. |
| F13 | confirmed | 34/120, 8/28, 34/119 and 10/10. Raw stderr: `vcodec=mjpeg min s=1280x720 fps=5 max s=1280x720 fps=60.0002` on the C922 and Kiyo. |
| F14 | **refuted (cause)** | The C922 has **byte-identical** frame descriptors for YUY2 2304x1296 and 2304x1536 (bFrameIndex 18/19, dwMaxBitRate 238,878,720 and 283,115,520, a single interval 4999998, `descriptors/descriptors.json`). On the C922, **MF, DS and ffmpeg all list them**: W-FMT `mf_missing` [], FMT-NOGRAB raw 98/98, and C922 `ffmpeg_main.err` lines 37–40 `pixel_format=yuyv422 min s=2304x1296 fps=2`. MJPEG frames with dwMaxBitRate up to 995 Mbit/s are also exposed on every camera. So usbvideo does not drop modes above 196.6 Mbit/s. The gap is **specific to the C930e** (possibly its second, H.264 pin or a Logitech device MFT; unknown). Run 1's verifier also missed this counterexample. |
| F15 | confirmed | Kiyo age 137–138 min during W-FMT and FMT-NOGRAB. The MF streamer delivered 349 frames, SOI/EOI/SOF0 349/349, at 30.004 fps. The PyAV streamer has `format_fallback` true, yuyv422, 29.14 fps. |
| F16 | **weakened** | Ages: 211.6 min (run 2) against ~200–224 min (run 1). That is 2 samples. In run 2 the fault was first *observed* at a control_get; the wedge time is unknown. Plug-in age cannot be separated from accumulated streaming workload. The practical advice (test the Kiyo soon after a replug) stands. |
| F17 | confirmed | The hub IOCTL with a concurrent open takes C922 208, C930e 511 and Kiyo 313 ms, against 78–84 ms alone (main runs). The generic camera was not slowed (74 ms). The C930e run ended 20 ms before the blocker's first frame, which fits the serialisation explanation (inferred). |

### Verdicts on the harness bugs

| ID | Verdict | Note |
| --- | --- | --- |
| B1 | confirmed | `w_mjpeg.py:307` `all_modes = info["selected"] >= target > 0`. |
| B2 | confirmed, extend | The same artefact appears in `w_mjpeg.py:334` (`evidence.rating_failed_modes`) and `:364` (`tool_failed_modes`): both list the 4 skipped Kiyo modes as failures. |
| B3 | confirmed (medium) | Stronger: on tier-0 cameras (C930e, generic: 5 of 10 working modes) the fps criterion is **self-referential**. If MF and DS agree within 2%, the reference is their mean (`rating.py:207-222`), so each API is within ≤ 1% and the criterion cannot fail. It only detects API disagreement. |
| B4 | confirmed | Low. |
| B5 | confirmed | `w_mjpeg.py:23-25` against `capkit.py:586-607`. |
| B6 | confirmed, but the overlap evidence is weakened | No delay is computed for no-hold methods (`w_fmt_nograb.py:265-274`). The analyst's "real overlap" holds only for ffmpeg on the C922 and the generic camera. On the C930e and Kiyo (ffmpeg) and on all 4 hub IOCTL runs, the method **ended before the blocker's first frame** (for example hub IOCTL Kiyo 313 ms against first frame 930 ms; C930e ffmpeg 505 against 530 ms). The idle "does not block" result for no-hold methods mostly tests an open that *started* during the method. The fix stands. Also run the blocker 0–50 ms *before* the method so that the open phase overlaps the method. |
| B7 | confirmed | `nograb.py:121`. |
| B8 | **weakened** | The semantic point (an MF/DS deficit that no Windows API can fill) holds. The proposed `descriptor_only_modes` annotation "dwMaxBitRate against the bus maximum" rests on F14's refuted cause, and the C922 shows this is a C930e-specific behaviour, not an OS rule. Keep the OS-exposed reference, but drop the bit-rate explanation. |
| B9 | confirmed | thr = max(3×32, 1.5×48, 48+25) ≈ 96 ms. |
| B10 | confirmed (low) | Note that the plan itself (xplat_capture_plan.md:404) says WinRT and OpenCV are "noted", not measured, so the harness follows the spec. The label change is still right. |
| B11 | **refuted** | In all 24 hold runs, one ~45–55 ms snapshot spans the pre-hold listing phase: it starts 1–7 ms before the process starts and ends 44–53 ms after it (raw `session.json` `topology_samples` against `process.t_start_ns` and `hold.begin_ns`). The real coverage gap is elsewhere (V3). |

### Missed by the analyst

- **V1 (F14 counterexample):** the C922 exposes the same two 2304-wide YUY2 descriptors through MF, DS and ffmpeg. The C930e gap is device-specific (measured: descriptors.json, W-FMT, ffmpeg_main.err).
- **V2 (circular reference):** the hub IOCTL is rated against its own earlier output (`w_fmt_nograb.py:437`). Its "complete" cell is true by construction. Fix: label hub_ioctl as the reference method, rate it only on repeatability, disturbance, stream and blocking, or compare it against an independent source (for example a usbview or Linux sysfs dump of the same camera).
- **V3 (idle hold coverage):** `method_stream_samples` (`w_fmt_nograb.py:232-253`) drops every sample that overlaps the blocker run plus `BLOCKER_TAIL_NS` = 500 ms (`:229`). The idle "starts no stream" check therefore excludes 897–1414 ms of the 2500 ms MF/DS hold on the C922, C930e and generic, and **1898 ms on the Kiyo**: only 0.13–0.55 s of its hold were checked (4 samples, none after the blocker). The rating is unchanged, but the stated evidence covers 24–64% of the hold. Fix: hold for 2.5 s with no blocker, sample the whole hold, and only then start the blocker (or run a second hold); report `hold_coverage_fraction`.
- **V4:** the Kiyo has metadata but `uvc_scr_sof` = 0 on every frame. Bus utilisation (M1) can never be computed for it, gated or not.
- **V5:** "238 H.264 modes" means 119 modes × 2 subtypes (`H264`, `MFVIDEOFORMAT_H264_ES`).
- **V6:** the generic camera re-arrived at 22:26:45Z, before run 2 (and at 18:17:09Z, before run 1). It also had a first failure in W-MULTI at 00:00:28Z (DS open, code 5) before its 00:10:45Z re-arrival (`run_suite.json` `faults.first_failure`). Out of this group's ratings, but relevant to F3.
- **V7 (cosmetic):** the Kiyo verdict note prints `(W-MULTI, None, mf, 0x8007001F)`, because `fault_mode` is None for a control_get fault (`w_mjpeg.py:273`). Print "no mode (control request)".
- **V8:** the fps criterion on tier-0 cameras is self-referential (see B3). The yes ratings for the C930e and generic say that the APIs agree, not that the camera delivers the requested rate.
