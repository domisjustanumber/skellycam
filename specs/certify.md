# Certify specification: what a certify run of skellycam measures (draft 2)

Status: draft 2 for the user, 2026-11-20. Spec and test list only: no product code and no test code
exist for it. The decisions of the user that it builds on are in
[ADR-GVC0](../decisions/entries/GVC0-certify-decisions-of-the-user.md). The choices of the agent are
in [ADR-KY81](../decisions/entries/KY81-certify-spec-choices-of-the-agent.md). Section 14 holds the
questions for the user. Draft 2 adds the answers of the user of 2026-11-20 to each question of draft
1, his decision that the native sources for Linux and macOS are built now and that certify validates
their assumptions, and his two new requests (a disk benchmark, and a list of what skellycam tests for
the other modules).

## 0. How to read this spec

- **The contract** is `report-format.md` of the repository `skellycertify` (sibling folder
  `../skellycertify/`), format `skellycertify.report/1.2.0`, commit `5fa9233`, with its `review.md`.
  "[C x.y]" cites section x.y of `report-format.md`. This spec does not repeat it.
- **[cap x.y]** is a section of [`windows-capture.md`](windows-capture.md). **[rec x.y]** is a section
  of [`recorder.md`](recorder.md). **[P §n]** is section n of `research/NATIVE_JPEG_CAPTURE_PLAN.md`.
- **[U]** marks a decision of the user ([ADR-GVC0](../decisions/entries/GVC0-certify-decisions-of-the-user.md)).
  **[S]** marks a reading of the supervisor that the user must confirm. **[A]** marks a choice of the
  agent ([ADR-KY81](../decisions/entries/KY81-certify-spec-choices-of-the-agent.md)).
- **[M file]** is a measurement. The files under `research/` are on branch `dom/research` of this
  repository, not on this branch. **[M run 11-20]** is the real-camera run of 2026-11-20 that the
  supervisor relayed. **[NV]** is not verified.
- A value that is marked "not calibrated" is a starting value. The user can change it.

## 1. Purpose and the start question

A person that we do not know runs certify on a system that we do not know, with cameras that we do
not know. The report must answer one question:

> Does the native capture of skellycam work on this system with these cameras? If not, what is the
> cause: the camera, the USB connection, the system, the light, or another program?

The user stated the aim: "the aim of this is to use certify to test out the native capture features
and see if they work. OpenCV is already fairly proven to work, so no need to test here." [U] Thus
certify tests native capture only. It has no check of the OpenCV source [U].

Each check answers one part of the start question. A check that cannot judge (a camera with no 1080p
mode, a dark room) says so with `not-run` or `record-only` and a reason. It never gives `fail` for a
feature that the camera does not have [A].

Scope:

- skellycam gives the two Python functions `skellycam.certify(level, progress=None, cancel=None, *,
  cameras=None, recording_folder=None)` and `skellycam.certify_plan(level, *, cameras=None,
  recording_folder=None)` [C 2.1]. The HTTP routes that start a run in the app stay in freemocap [U].
- The levels `quick` and `full` [C 2.7].
- The product path on all three systems: Media Foundation on Windows, and the native V4L2 (Linux) and
  AVFoundation (macOS) sources, which the user decided to build now [U]. On Linux and macOS, certify
  validates the assumptions of those sources (section 10).
- The known systems and cameras, and the flow from a report to the next release: section 11.

## 2. The run

### 2.1 Processes [A]

| Process | What it does | What it must not do |
|---|---|---|
| Caller process: `certify()` | The plan, the progress, the cancel, the time limits, the report, the privacy scrub. | Import `comtypes`, load a camera driver, open a camera. |
| Detection child | The native detection of the product (`detect_media_foundation_cameras()` on Windows, which has its own child, cap 7.1; the V4L2 and AVFoundation detection of the new sources). | Stay alive after its limit. |
| Session child | One `CameraGroupManager` of the product with the native source (or fake sources for a self-check). Its camera processes are its children [cap 6.6]. | Run HTTP. It never opens a port, and never port 53117. |
| Probe child | A probe of section 10.4: a fact that the product path cannot see. Record-only. | Open a camera; write outside the work folder. |

- Each child starts with the `spawn` method of `multiprocessing` [C 2.5].
- Certify always uses the native source. The Windows setting `SKELLYCAM_WINDOWS_CAPTURE` (cap 14.2)
  does not change it [U: native only].
- The caller ends a child after its time limit or a cancel in the order of 9.3, and at last kills the
  whole process tree (`psutil`, pinned `==7.2.2`) [C 2.4, C 2.5].
- Each session child gets the detection result of the run (`CameraGroupManager.detected_cameras`).
  Thus an apply request never runs the detection again (cap 7.1), and never activates a camera that
  hung before.

### 2.2 The product path [A]

A certificate must test the product, not a copy. Each check on Windows uses only these product calls:

| Need | Product call |
|---|---|
| Cameras and modes | `detect_media_foundation_cameras`, `supported_modes`, `capture_modes` (3c) |
| Open, mode, warm-up, rate check, states | `CameraGroupManager.create_or_update_camera_group` with `CameraConfigs` (apply, cap 8.3), the camera status (cap 8.4), `camera_failures` |
| Live exposure, gain, focus | An apply with a changed control: the check of cap 10.2 |
| SkellyCam Auto | An apply with SkellyCam Auto exposure (`RECOMMEND` in today's code, cap 11.1) |
| A take | `CameraGroup.start_recording`, `stop_recording`, `TakeSummary`; the files of rec 6 |
| File checks | `sidecar.read_strict`, the manifest, `stop_stats.stop_response_fields` |
| Frames | `FrameRingReader` of the JPEG ring; `cv2.imdecode` in memory (`IMREAD_REDUCED_GRAYSCALE_8` for the brightness) |
| A plain open, the controls before the run, the restore, the cycles | `MediaFoundationSource.open`, `set_controls`, `close` in the session child |
| Disk | `start_take`, `CameraTakeWriter`, `finish` with synthetic JPEG frames; `folder_files.file_system` |

The certify code adds no other capture path. On Linux and macOS the same calls go to the native V4L2
and AVFoundation sources. A test checks this (T-CERT-32).

### 2.3 Order of a run [U, A]

The user decided: "Do the stuff that's likely to break the cameras at the end of the run. Ensure
anything that gets broken during a run is fixed or flagged to the user" [U]. Thus a run has these
phases, in this order:

| Phase | Level | Content |
|---|---|---|
| A. Before | both | Plan facts; detection; for each camera a plain open that reads its controls before any change (the "before" values); then close. |
| B. Quick | both | The checks of section 4. |
| C. Safe camera checks | full | Section 5, one camera at a time: the 30 fps modes, the exposure sweep, Auto, the controls, the timestamps. |
| D. Group and system | full | Section 6: the group take at 30 fps, the contention, the disk check and the disk benchmark, the system facts. |
| E. Self-checks | quick: `self:hang-100ms` [U]; full: all | Section 7. They use fake cameras and do not touch a real camera. |
| F. Risky checks | full | Section 8, in order of rising risk: the in-use check, the 60 fps modes and sweeps, the group take at 60 fps, the open and close cycles, and on macOS the endpoint-0 controls (section 10). |
| G. Restore and re-check | both | Section 8.3: each camera gets its "before" values back, and a plain open checks it. The phase runs also after a cancel or a crash of an earlier phase. |
| H. Cleanup | both | Section 9.5. Then the report. |

A camera that hung, crashed its camera process or was removed is never opened again in that run
[U: the Kiyo Pro wedge rule, cap 8.2]. Its later checks are `not-run` with `prior-failure`, and phase G
gives it the state `replug` (8.3).

### 2.4 Package options [A]

| Option | Default | Meaning |
|---|---|---|
| `cameras` | `None` (each real camera) | A list of labels of section 3.1. Only these cameras are checked. A run of a part of the cameras is complete for each camera that it checks, so it is not `partial-run`. |
| `recording_folder` | `None` (the temporary folder of the system) | The folder where the person records. The app passes its data folder. The quick take, the disk check and the disk benchmark write in a new work folder inside it, and certify deletes it (9.5). No path is in the report. |

## 3. Names, results, numbers

### 3.1 Check names [A]

The backend strings are `media-foundation`, `v4l2` and `avfoundation` [U: names, A: strings]. The
label of a camera is
`cam.<backend>.<vid>-<pid>.<n>`:

- `<vid>-<pid>`: the USB vendor and product IDs, four lower-case hex digits each. A camera with no
  USB IDs gets `nousb-nousb`.
- `<n>`: 0, 1, 2 ... for each camera with the same backend and IDs, in the detection order. It never
  holds a serial number, a path or the `camera_id`.

Example: `cam.media-foundation.046d-085c.0`. The evidence key of the contract is the model, the
backend and the OS [C 7.4]. The label holds the first two; `host.os` holds the third.

| Name form | Meaning |
|---|---|
| `<label>` | The camera row. Its result is the result of the summary item (3.3). |
| `<label>:<claim>` | A claim check of 3.3: `opens`, `rate`, `settings-stick`, `native-jpeg`, `records`. |
| `<label>:<check>[:<mode>]` | Another check of the camera. `<mode>` is `<w>x<h>@<rate>`, with the rate rounded as cap 7.3 rounds it: `1280x720@30`, `1920x1080@30`, `1280x720@60`, `640x480@29.97`. |
| `detect` | The detection. |
| `group:<check>`, `system:<check>` | A check of the cameras together; a fact or a check of the system. |
| `self:<check>` | A self-check with fake cameras (section 7). It is never a camera row [U]. |
| `probe:<check>` | A probe of 10.4: record-only, outside the product path. |
| `<name>:exit` | The `exit` check of the contract [C 2.5]. |
| cleanup `release:<label>` | Phase G: a camera that is not healthy after the run (8.3). |

Each name matches `^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$` [C 3.4]. The longest form,
`cam.media-foundation.nousb-nousb.9:exposure:1920x1080@29.97`, has 59 characters. The report has no
sections: the "Failed checks" table then shows each failed check [C 4.2 part 6].

### 3.2 Numbers [A]

`numbers` is flat [C 3.4]: a number, a boolean, `null`, a reason code, a list of reason codes, or a
string from a fixed vocabulary of `skellycam/REASON_CODES.md`. A list of numbers is not allowed. Thus
a sweep gives one key for each step, for example `fps_at_m7` for exposure -7 (`m` for minus).

### 3.3 The camera row, the claims, "partial" and "in use"

The user asked: "Quick test must include applying settings and if they stick or not, can you jpegs
... This might necessitate a "partial" result in the summary table." [U] He also asked for "in use"
as a reported status of its own [U].

The supervisor reads "can you jpegs" as: does the camera give JPEG frames natively in the product's
capture path, that is MJPG passthrough with no decode and no re-encode [S]. Question 2 asks the user
to confirm this.

**The five claims.** Each real camera has five claim checks. Each is `pass`, `fail` or `not-run`,
with a reason code:

| Claim check | Claim | Section |
|---|---|---|
| `<label>:opens` | The camera opens at `<base>` and reaches `ready`. | 4.2 |
| `<label>:rate` | It holds the mode rate at `<base>` (the product rate check). | 4.2 |
| `<label>:settings-stick` | Each control that the product sets reads back the set value, still reads it 1 s later, and changes the image. | 4.3 |
| `<label>:native-jpeg` | It gives its own JPEG frames, passed through unchanged. | 4.4 |
| `<label>:records` | It records a take with good files. | 4.5 |

`<base>` is `1280x720@30`. A camera with no 1280x720 MJPG mode at the floor uses the largest MJPG
size below 1280x720 in area that has a rate at the floor, for example `640x480@30` [A].

**The row.** The row `<label>` gives the result of the summary item [C 3.7]. Two ways exist, because
the contract allows only `pass`, `fail` and `record-only` in a summary item today, and the relay
refuses any other value (HTTP 422):

| | Way 1: one format change (1.3.0) [A, recommended] | Way 2: no change of the format |
|---|---|---|
| `pass` | Each of the five claims passes. | Each of the five claims passes. |
| `partial` | `opens`, `rate` and `records` pass, and `settings-stick` or `native-jpeg` fails. The camera works at the base setting, with a known limit. A declared mode of `full` that does not deliver never changes the row: it is a `fail` of that mode check, and the row stays at its base result [U]. | Not possible. The row is `pass` (the base claim), and each failed claim check shows in the "Failed checks" table under the camera table. |
| `fail` | `opens`, `rate` or `records` fails for a reason of the camera. | The same. |
| `in use` | `opens` is `not-run` with `camera-in-use`: another program holds the camera. | Not possible as a status. The row is `record-only` with the reason `camera-in-use`; the Markdown shows `record`. |
| `record` | Nothing judged the camera: too dark, USB bandwidth also alone, cancelled, time budget. | The same. |

Way 1 needs one change of the contract, in one step for both values, as the certify session advises:
a summary item of the group `camera` gets the results `partial` and `not-run`, and an optional
`reason` (a reason code). The Markdown shows `partial`, and `not run: camera-in-use` or the short
form `in use`. The change touches section 3.7 of the contract, `relay/src/report.js`,
`relay/src/issue.js` and their tests, and the Markdown writer of freemocap: three repositories.
Strictly, a new value of a field is a major change [C 8]. It can be 1.3.0 with the word of the owner,
because no file with `summary` was handed in yet. Question 1 asks the user to choose.

A virtual camera gets no claim, no row and no summary item [A]. `system:virtual-cameras` records the
count. The app shows it but cannot select it [U].

## 4. Level `quick`

### 4.1 The rules [U]

The user decided: "Quick must be: No more than 2 minutes total. Not require downloading any files
not included with the installer ... Be enough to verify a recording, a realtime pipeline session,
and a post-hoc session can at least start and run (whichever is relevant to that module)." For
skellycam: each real camera is detected with its modes, opens and passes the rate check at 30 fps at
720p; then all cameras that passed record one take of 3 seconds with the new recorder; certify checks
the files and deletes them; the target is under 30 seconds for four cameras. Draft 2 adds the
settings check and the JPEG check [U].

The 2 minutes are for all packages together [C 2.7 rule 1]. Thus skellycam keeps its own hard limit
of 45 s [A, not calibrated]. A check that cannot start before that limit is `not-run` with
`time-budget`.

### 4.2 The open and the rate

| Check | Measured, and how | Numbers | Result rule |
|---|---|---|---|
| `detect` | The detection child. Limit 20 s. | `seconds`, `cameras`, `virtual`, `modes_read` | `pass`; `fail` with `timed-out`, `crashed`, `backend-missing` |
| `<label>:detect` | The modes (cap 7.3). | `mjpg_sizes`, `has_720p30`, `has_1080p30`, `has_60`, `max_fps`, `largest_w`, `largest_h`, `modes_read` | `record-only`; `fail` with `no-mjpg-mode` when no MJPG mode is at the floor (before 3b) |
| `<label>:opens` | One apply opens each real camera at `<base>`, manual exposure -7 (the product default), MJPG, rate 30. | `seconds_to_first_frame`, `seconds_to_ready`, `stage` | `pass` at `ready`; `not-run` with `camera-in-use`; `fail` with the reason of the product failure (section 15) |
| `<label>:rate` | The start-up rate check of the product (cap 10.1): frames 6 to 90, ±3 %. Then the brightness of 3 ring frames. | `mode_fps`, `measured_fps`, `luma_mean`, `jpeg_kb_mean` | `pass`; `fail` with `rate-low` or `rate-high`; `record-only` with `too-dark` (4.6) |
| `group:open` | Did each camera that passes alone also pass in the group? | `cameras`, `passed`, `refused_bandwidth`, `failed_in_group_only` | `pass`; `fail` with `usb-bandwidth` or `rate-under-contention`; `not-run` with `one-camera` |

One apply, then a retry alone [U: question 3 of draft 1, "yes"]:

1. One apply opens all real cameras at `<base>`. The product opens them in parallel: 5.8 s for three
   cameras [M `research/usb_cameras/docs/hardware_run_3a_20261120.md`].
2. A camera that failed in the group with `usb-bandwidth` or `rate-low` gets one retry alone. The
   retry decides its claims. `group:open` records the difference.
3. No retry for `hung`, `camera-in-use`, `device-removed` or `not-found`.

Reason: a bandwidth refusal is a fact of the USB topology. The C922 and the generic camera on one USB
2 root port were refused at 81 % of a microframe on every API; each alone worked
[M `research/usb_cameras/docs/windows_results_20261112.md` §6].

### 4.3 Settings stick [U, A]

The product sets the controls after the first frame and reads them back (cap 9.1). The check:

1. At the open of 4.2, the requested exposure is manual -7. The read-back of the product (the config
   stores it, cap 9.1 step 6) gives `readback_open`.
2. One live apply changes all cameras together to manual -8 (one step darker; each test camera holds
   30 fps there [M cap 10.5]). The product runs the check of cap 10.2 (about 2.5 s). After 3c, the same
   apply sets gain and focus to manual at the values that the camera reported, so that the image does
   not change.
3. The status read of the control thread 1 s later gives `readback_later` (cap 11.4).
4. The brightness at -8 against -7: `luma_ratio`. A step of one in log2 seconds halves the exposure
   time, so the ratio must be below 0.85 [A, not calibrated].

| Numbers | Result |
|---|---|
| `exposure_set`, `exposure_readback`, `exposure_later`, `luma_at_m7`, `luma_at_m8`, `luma_ratio`; after 3c `gain_ok`, `focus_ok` | `pass` when each read-back equals the set value, the later read equals it, and `luma_ratio < 0.85`; `fail` with `readback-differs`, `setting-reverted` (the later read differs) or `no-image-effect`; `record-only` with `too-dark` or `too-bright` when `luma_at_m7` is below 24 or above 230; `not-run` with `prior-check-failed` |

Measured: the C930e read manual exposure -5 at the stream start when -7 was set last, and its gain
fell over three opens; the product sets the controls after the first frame, so the configured values
held [M `research/usb_cameras/docs/hardware_run_3a_20261120.md`]. This check finds such a camera.

The take of 4.5 runs at -8. Phase G puts back the "before" values.

### 4.4 Native JPEG [S, A]

The check uses frames that the run already has. It needs no extra time.

| Numbers | Result |
|---|---|
| `format` (`MJPG`, `YUY2`, `NV12`), `frames_checked`, `soi_eoi_ok`, `strict_decode_ok`, `sof_matches_mode`, `encoded_by_skellycam` (count; from the product, section 13), `dht_inserted` (count), `quant_tables_distinct` (count), `bytes_equal_ring_mkv` | `pass` when the mode format is MJPG, skellycam encoded no frame, each checked frame has SOI and EOI, decodes strictly, has the SOF size of the mode, and its MKV block equals its ring slot byte for byte; `fail` with `no-native-jpeg` (an uncompressed mode that skellycam encodes, after 3b), `jpeg-damaged` or `jpeg-size-differs` |

- The frames: 30 frames of the JPEG ring after the rate check, and each block of the take of 4.5.
- A JPEG with no DHT gets the standard table from the capture check (`DHT_INSERTED`, rec 4.1). That is
  still native. `dht_inserted` records it.
- Measured on Windows: MJPG passthrough is byte-equal on the three good test cameras
  [M `research/usb_cameras/docs/hardware_run_3a_20261120.md`, T-CAP-52].

### 4.5 The take and its files

- The take starts through `CameraGroup.start_recording` in the work folder (9.5), runs 3 s and stops
  through `stop_recording`. Limit: 30 s from the start request.
- `group:take` passes when all of these are true:
  - the manifest has `state` `"finished"` and no `take_error` (rec 6.6);
  - each CSV reads with `sidecar.read_strict`, and each has the frame count of the take as its row
    count (rec 7.6);
  - no live camera has a `missing` row, and the warnings hold no `camera_dead` and no
    `camera_file_short`;
  - the frame count is at least 80 % of 3 s times the mode rate [A, not calibrated];
  - the frame rate of the take summary is within 1 % of the mode rate. This rate is the frames
    divided by the elapsed time [U]. The mean of 1/interval is not used: the 16 ms arrival grid
    biases it high [M `research/usb_cameras/docs/hardware_run_3a_20261120.md`, T-CAP-60].
- `<label>:records` passes when its rows have no `missing` row, each block of its MKV decodes (at 1/8
  size, in memory), and the sum of its gaps of `source_frame_number` equals its `replaced_count`
  (cap 5.2). A normal take of three cameras had equal rows, and each frame decoded [M run 11-20].
- A gap in the last three rows is recorded in `end_gaps` and does not fail the claim [A]. In 6 of 7
  takes of the run of 2026-11-20, one source frame was skipped two rows before the end, and the cause
  is under study [M run 11-20]. When the cause is fixed, this exception goes.
- Numbers of `<label>:records`: `rows`, `missing`, `gaps`, `replaced`, `end_gaps`, `decode_failures`,
  `arrival_minus_sample_p50_ms`, `arrival_minus_sample_p95_ms`, `sample_time_kept`,
  `grid_16ms_share`, `long_intervals`. The timestamp numbers are record-only facts: they never decide
  the result.
- Numbers of `group:take`: `cameras`, `frame_count`, `seconds`, `rate`, `file_system`,
  `spread_p50_ms`, `spread_p95_ms`. The spread is record-only [U]: the lockstep gate of today gives a
  median of about 36 ms [M `research/usb_cameras/docs/hardware_run_3a_20261120.md`] to 40 to 50 ms
  [M run 11-20].
- Fail reasons: `take-not-finished`, `take-error`, `rows-differ`, `missing-rows`, `gaps-unexplained`,
  `group-rate-off`, `too-few-frames`, `frame-not-decodable`, `fat-disk`, `disk-stall`, `write-error`.
- After the checks, certify deletes the take folder (9.5). No file of the take is in the report.

### 4.6 Light: "too dark to judge" [A]

At manual exposure the frame rate depends on the exposure time, not on the light: at -7 (7.8 ms)
each good test camera gave 29.9 to 30.1 fps [M cap 10.5]. Thus each rate check of certify runs at a
manual exposure. Light still matters in four cases: a camera whose firmware lengthens the exposure in
low light also in manual mode [NV], SkellyCam Auto (5.3), the settings check (4.3) and the focus check
(5.4).

- `luma_mean` is the mean grey value (0 to 255) of 3 frames of the JPEG ring, decoded at 1/8 size in
  memory. No frame is kept.
- `DARK_LUMA = 24` [A, not calibrated]. A light-dependent check that fails while the mean is below it
  is `record-only` with `too-dark`. The same check with a brighter frame is `fail`. A check that
  passes in the dark stays `pass`.
- A covered lens gives the same result as a dark room. The report does not need to tell them apart.
- The plan asks after the run: "Was the room lit as it is when you record?" (9.1).

### 4.7 Time of `quick` [A]

Windows, Media Foundation, from the 3a hardware run:

| Step | Seconds |
|---|---|
| Session child start and imports | 2 [NV] |
| Detection (0.83 s for 8 devices [M]) | 1 |
| Phase A: plain open of each camera, in parallel, to read the "before" values | 2 [NV] |
| One apply of all cameras (5.8 s for 3 [M]) | 6 + 0.25 per camera [NV] |
| Settings check (one live change, cap 10.2) | 3 |
| Take: start, 3 s, stop, `finish` | 5 |
| File checks, JPEG check, deletion | 1.5 |
| Close of the group (0.27 to 1.18 s per camera, in parallel [M]) | 1.5 |
| Phase G: restore, in parallel | 2 [NV] |
| `self:hang-100ms` [U] | 10 |
| Each retry alone (4.2) | 6 |

Sum with no retry: about 25 s for 4 cameras and 26 s for 8 cameras; with the hang self-check, 35 s
and 36 s. This is above the target of 30 s for four cameras. The user decided that the hang
self-check stays in quick [U]. So the product should restore the "before" values at its own close
(section 13): phases A and G then cost nothing, and quick is about 31 s for four cameras (question 4).
`certify_plan("quick")` gives `seconds_estimate = 35 + N/4`, or `31 + N/4` with the restore in the
product, rounded up.

## 5. Level `full`: safe checks of each camera (phase C)

### 5.1 Selection rule [A]

A full run cannot test each mode of each camera. The C930e declares 17 MJPG sizes
[M `research/usb_cameras/docs/hardware_run_3a_20261120.md`]. For each camera whose `opens` and `rate`
passed, the run selects:

1. `<base>` (from quick; no new open).
2. `1920x1080@30`, when the camera declares it.
3. The largest MJPG size at the floor, when it is larger than 1920x1080, once, at 30.
4. The exposure sweep at `<base>`; SkellyCam Auto; the controls; the timestamps.
5. Phase F: each size that declares 60, at most two (1280x720 first, then the largest other size),
   with the sweep at the first one; the in-use check; five open and close cycles.
6. After step 3b: one uncompressed mode (YUY2, else NV12) at 30 at the largest size that has it.
   Before 3b: `not-run` with `not-built`.

A mode that the camera does not declare gives `not-run` with `no-mode`, never `fail` [A]. Rates above
60 are recorded in `<label>:detect` (`max_fps`) and not opened: skellycam offers 30 and 60.

### 5.2 Rate checks of other 30 fps modes, and the exposure sweep

| Check | How | Numbers | Result |
|---|---|---|---|
| `<label>:rate:1920x1080@30` | An apply of this camera alone at the mode, manual -7. The product start-up check. | `mode_fps`, `measured_fps`, `luma_mean`, `jpeg_kb_mean`, `seconds_to_ready` | `pass`; `fail` with `rate-low`, `rate-high`, `usb-bandwidth`, `not-ready`; `record-only` with `too-dark`; `not-run` with `no-mode` |
| `<label>:rate:<largest>` | The same at the largest size. | the same | the same |
| `<label>:exposure:<base>` | Live changes through apply, manual, from -11 to -3. Each step is the check of cap 10.2. Stop after two steps in a row that end `too_slow`. | `fps_at_m11` ... `fps_at_m3`, `state_at_m11` ..., `luma_at_m11` ..., `cliff` (the longest exposure that ends `ready`), `readback_ok` | `record-only`; `fail` with `exposure-not-applied` when a set value does not read back |

- The sweep answers "where is the 30 fps cliff?" Logitech: 30 fps to -5, 16 fps at -4; Kiyo Pro:
  28.7 fps at -6, 23.1 at -5 [M cap 10.5].
- The sweep needs `measured_fps` after `too_slow`. The 3a run found that it keeps the old passing
  value [M `research/usb_cameras/docs/hardware_run_3a_20261120.md`]. That fault must be fixed first
  (section 13).

### 5.3 SkellyCam Auto [U]

Exposure modes are Manual and Auto. Auto means that SkellyCam finds a manual value. The camera's own
auto exposure is never a mode [U].

| Check | How | Numbers | Result |
|---|---|---|---|
| `<label>:auto-exposure` | An apply at `<base>` with SkellyCam Auto (cap 11.1: -12 to -5, offset -1). The status gives the found manual value; then the product rate check. | `found`, `at_range_end`, `luma_mean`, `measured_fps` | `pass` when the found value passes the rate check; `record-only` with `too-dark` when `at_range_end` and `luma_mean < 64` [A, not calibrated], or when the check fails with `luma_mean < DARK_LUMA`; `fail` with `rate-low` otherwise |

### 5.4 Controls

| Check | How | Numbers | Result |
|---|---|---|---|
| `<label>:controls` | The status (cap 8.4, 11.4): which controls exist. After 3c, also the ranges. | `exposure`, `gain`, `focus`, `white_balance`, `power_line` (present); after 3c `<name>_min`, `_max`, `_step`, `_default` | `record-only` |
| `<label>:control:gain` | After 3c: set the minimum and the default, manual; read back. | `set_ok`, `readback`, `rate_ok` | `pass`; `fail` with `readback-differs` or `control-failed`; `not-run` with `control-absent` or `not-built` |
| `<label>:control:focus` | After 3c: manual focus at two values; read back; the sharpness (variance of a Laplacian of the 1/8 frame). | `set_ok`, `readback`, `sharpness_a`, `sharpness_b`, `luma_mean` | `pass` on read-back; sharpness record-only; `not-run` with `control-absent` or `not-built` |
| `<label>:control:autofocus` | After 3c: auto focus on, then off at the value that it reported; read back. | `reported`, `readback` | `record-only` (M-CAP-7 is open) |
| `<label>:control:white-balance`, `<label>:control:power-line` | After 3c: read only (cap 11.5). | `value`, `auto` | `record-only`; `not-run` with `control-absent` |

### 5.5 Start-up times and timestamps

| Check | How | Numbers | Result |
|---|---|---|---|
| `<label>:timings` | The times of each open of the run. | `open_ms_p50`, `open_ms_max`, `ready_s_p50`, `close_ms_max` | `record-only` |
| `<label>:timestamps` | The CSV of this camera in `group:take-30` (6.1), 30 s. | as `<label>:records`, and `period_ms`, `drift_ppm_against_first` | `record-only` |

## 6. Level `full`: cameras together and the system (phase D)

### 6.1 Group checks

| Check | How | Numbers | Result |
|---|---|---|---|
| `group:take-30` | Each camera that passed `rate:1920x1080@30` alone (else `<base>`), one apply, a take of 30 s. The CPU of the process tree during the take (`psutil`). | as `group:take`, and `mode`, `cpu_cores_used`, `cpu_logical`, `cpu_share_p95` | 4.5 rules |
| `<label>:group-open` | Did this camera open in that group? | `measured_fps`, `alone_fps`, `stage` | `pass`; `fail` with `usb-bandwidth` (the camera that loses) or `rate-under-contention` |
| `group:contention` | The start-up rate of each camera in the group against alone. | `c<i>_group_fps`, `c<i>_alone_fps` (`<i>` is the detection index) | `record-only` |

### 6.2 System checks

| Check | How | Numbers | Result |
|---|---|---|---|
| `system:backend` | The source of each camera. | `backend` | `record-only` |
| `system:usb` | After the USB label is ported (section 13): the link of each camera. | counts `usb3`, `usb2`, `usb1`, `unknown`; `usb_link` in `<label>:detect` | `record-only`; `not-run` with `not-built` before the port |
| `system:disk` | The product recorder with synthetic JPEG frames (rec 11) in the work folder: N camera writers, N = the count of cameras that passed, each at the size and the mean JPEG size of its camera at its largest passed 30 fps mode, 20 s. | `file_system`, `free_gb`, `cameras`, `need_mb_per_s`, `give_waits`, `give_wait_ms_max`, `queue_high_water_s`, `threshold_give_wait_ms` (500) | `pass` when no `give` waits longer than 500 ms [A, not calibrated] and no stall; `fail` with `disk-slow`, `disk-stall`, `fat-disk` |
| `system:disk-benchmark` | Section 6.3. | `write_mb_per_s`, `block_ms_p99`, `fsync_ms_max`, `bytes`, `seconds`, `cameras_1080p30_typical`, `cameras_1080p30_worst` | `record-only` |
| `system:camera-apps` | Windows: a fixed allow-list of process names of programs that hold or change cameras, for example LogiTune and Razer Synapse [M `research/usb_cameras/docs/windows_results_20261113.md` §0]. | one boolean for each item of the list | `record-only` |
| `system:virtual-cameras` | The count from detection. | `count` | `record-only` |

### 6.3 The disk benchmark [U, A]

The user asked: "ensure a disk performance benchmark is run to get a MB/s figure as well as the "disk
is fast enough" test when running the full suite." [U]

- The folder: a new file in the work folder inside `recording_folder` (2.4). No path is in the report.
- Before the write: when the free space is less than 3 times the file size, the benchmark is `not-run`
  with `disk-full`.
- The write: one file of 1 GiB [A, not calibrated], in blocks of 4 MiB, through an unbuffered file
  object, with `os.fsync` once a second (the rhythm of the recorder, rec 5.6) and once at the end.
  The benchmark stops at 1 GiB or after 30 s, whichever comes first.
- The figure: `write_mb_per_s` = the bytes written divided by the time from the first write to the
  return of the last `fsync` (MB = 10^6 bytes). `block_ms_p99` and `fsync_ms_max` show the stalls.
- What N cameras need: one camera at 1920x1080@30 MJPG writes about 6 MB/s with frames of 200 kB
  (rec 11), and 18 MB/s in the worst case of rec 5.1 (600 kB). Thus `cameras_1080p30_typical` =
  ⌊`write_mb_per_s` / 6⌋ and `cameras_1080p30_worst` = ⌊`write_mb_per_s` / 18⌋.
- Then certify deletes the file. A cache of the OS can make a short write look fast: the fsync of each
  second and the size of 1 GiB limit that, but do not remove it [NV].
- `system:disk` (the pass/fail check) and the benchmark measure two different things: the recorder at
  the real load, and the raw speed of the disk.

## 7. Self-checks with fake cameras (phase E) [U, A]

A check on a fake camera proves nothing about a camera model. It is a self-check with its own name,
never a camera row [U]. The self-checks run the product: the session child, `CameraGroupManager` with
`source_factory` (ADR-HP7D item 10), real camera processes, the shared loop and the recorder. Only the
source is fake. The fake source must move from the tests into the package for this (section 13).

| Check | Level | What it does | Pass rule | What it proves | What it does not prove |
|---|---|---|---|---|---|
| `self:hang-100ms` | quick [U], full | Three fakes at 720p30 are `ready`; the control read of one hangs past the bounded-call limit, on its control thread (T-CAP-82). | The two others have no gap of taken frames above 100 ms [U], and the hung process ends within the limit plus 2 s. | The rule of the software holds at the speed of this CPU, scheduler and OS [U: "so we can catch if rules are still valid on older/slower systems"]. | That a real driver hang does not block the USB stack of the other cameras. |
| `self:crash-take` | full | Three fakes record; the process of one ends with `os._exit(3)` at frame 100 (T-CAP-109 case 2). | The take finishes with `camera_dead` or `camera_file_short` as rec 7.3 and 7.4, equal rows, the others record to the stop. `others_gap_ms_max` is recorded and does not decide [A]: the 100 ms rule is for a hung camera, and a killed camera process cost the others 1 and 3 frames (a hole of 128 ms on one camera) [M run 11-20]. | The take survives a camera crash on this system. | A real driver crash. |
| `self:server-gone` | full | Two fakes record; the main process of the session child ends with `os._exit`. | Each camera process ends within 10 s plus 5 s [A, not calibrated], with its files finished and its source closed [U: a dead server is noticed after 10 s, not 300]. | A crash of the app or of certify releases the cameras on this system. | A real camera. |
| `self:stall` | full | Two fakes record; the MKV file object of one blocks past the stall limit (10 s, rec 5.3). | `take_error` "disk stall on camera <id>"; the other camera's files are finished; the stalled camera is `failed`; no healthy camera is `dead`. | The stall rule holds on this system. | A real disk. |
| `self:idle-cpu` | full | One paused fake camera process, 10 s (T-CAP-49). | Under 2 % of one core. | No thread spins on this OS. | — |
| `self:ring` | full | The torn-read and lapped-read checks of the JPEG ring with two processes (T-RING-05 to 14, 28, 30, as product calls). | Each torn or lapped read is refused. | The ring is safe on this CPU and its memory model, for example Apple Silicon (T-RING-34). | — |
| `self:scale-4`, `self:scale-8` | full | 4 and 8 fakes at 1920x1080@30 with JPEGs of 200 kB, recording, 15 s each. | `record-only` | The CPU that the software needs for N cameras: the headroom for more cameras than are attached. | USB bandwidth, a real driver. |

## 8. Risky checks last, restore, and the message to the person

### 8.1 Why the order [U, M]

The user decided: "Do the stuff that's likely to break the cameras at the end of the run." [U] The
notes show which steps wedged a camera:

- The Kiyo Pro died at its first sample at 1280x720@60 [M `research/usb_cameras/docs/windows_results_20261113.md` §0].
- It wedged at a stream start (one time at the first start after a replug) and in a round that opened
  four cameras at once [M `research/usb_cameras/docs/windows_results_20261110.md` §9].
- Each open is a stream start. The cycles have the most of them.

### 8.2 Phase F, in this order

| Check | How | Numbers | Result |
|---|---|---|---|
| `<label>:in-use` | A second session child holds the camera through the product source. Then an apply of the camera in the first session child. | `outcome` (`refused`, `shared`, `hung`), `stage`, `seconds` | `pass` when the outcome is `refused` with the product reason "in use by another program" (cap 6.7), or `shared`; `fail` with `hung` or `wrong-reason` |
| `<label>:rate:<w>x<h>@60` | An apply of this camera alone at the 60 mode, manual -7 (7.8 ms is shorter than one period of 16.7 ms). | `mode_fps`, `measured_fps`, `luma_mean`, `ok_at_m7`, `ok_at_any_exposure` | `pass` when the check passes at -7, or when the sweep finds an exposure that holds 60; `fail` with `rate-low` when no tested exposure holds 60; `not-run` with `no-mode` |
| `<label>:exposure:<w>x<h>@60` | The sweep from -10 to -5 at the first 60 mode. | `fps_at_m10` ... `fps_at_m5`, `ok_exposures`, `shortest_ok`, `longest_ok` | `record-only` |
| `group:take-60` | Each camera whose 60 mode passed, at 60, with the exposure that held 60 for it, a take of 15 s. Needs two cameras. | as `group:take` | 4.5 rules; `not-run` with `one-camera` or `no-mode` |
| `<label>:cycles` | Five cycles of `MediaFoundationSource.open` at `<base>` (to the first frame) and `close`. | `cycles`, `ok`, `open_ms_max`, `first_frame_ms_max`, `close_ms_max`, `stage` | `pass`; `fail` with `hung` or `first-frame-timeout` at the first fault, and no more opens of that camera |

A declared 60 mode that never delivers 60 fails its mode check, and the camera row stays at its base result [U]. Measured: the Kiyo Pro
declares 60 at each of its 4 sizes and delivered 29.7 to 30.4 fps at each exposure from -7 to -10; the
C922 delivered 60 at 1280x720 only at -7, 29.7 fps at -8 to -10, and 56.5 fps at -6
[M `research/usb_cameras/docs/free_run_log_20261120.md` §9]. The product offers 60 only when each
ticked camera passed a real 60 fps check [U]. Certify reports at which exposures 60 held.

The C922 at 60 with the Kiyo Pro open gave 46.5 fps over frames 6 to 90, then 58.7 fps over 10 s
[M same file]. Thus `group:take-60` can find `rate-under-contention` where each camera alone passes.

### 8.3 Phase G: restore and re-check [U, A]

The user decided: "Ensure anything that gets broken during a run is fixed or flagged to the user "e.g.
camera <camera name> wedged, please replug"" [U].

1. Phase A read the "before" values of each control of each camera: the value and the auto flag.
2. Phase G opens each camera that did not hang (a plain open of the product source, to the first
   frame), sets the "before" values, reads them back, and closes. The open is bounded (cap 6.6). A
   camera that hung earlier is not opened again [U].
3. Each camera gets one after-run state:

| State | Meaning | Where the report holds it |
|---|---|---|
| `healthy` | The plain open worked, and certify changed no control that stays in the camera. | No cleanup row. |
| `restored` | The plain open worked, and the "before" values were set and read back. | No cleanup row. |
| `not-restored` | The plain open worked, but a "before" value did not read back. | Cleanup row `release:<label>`, `fail`, reason `camera-not-restored`. |
| `replug` | The camera hung during the run, or the plain open of phase G failed. | Cleanup row `release:<label>`, `fail`, reason `camera-wedged`. |

The phase also runs after a cancel or a crash of an earlier phase, with its own limit of 20 s for each
camera [A].

**How the message reaches the person.** The report format forbids free text in `numbers`, and it has
no field for a message to the person [C 3.4]. The fitting place today is `cleanup`: a list of check
objects for cleanup steps that failed [C 3.1]. Thus [A]:

- skellycam writes the cleanup row `release:<label>` with a fixed reason code. `skellycam/REASON_CODES.md`
  gives each code with one sentence: `camera-wedged`: "The camera stopped answering during the run.
  Unplug it and plug it in again." `camera-not-restored`: "A setting of the camera is not as it was
  before the run. Open the camera in SkellyCam and set it again."
- The app shows each such row as a notice at the end of the run, also when the person does not send
  the report: "Camera <name>: wedged, please replug." The app finds the cleaned name through the summary
  item with the same `device` (and the same order for two cameras of one model). This is an agreement
  between skellycam and freemocap. It needs no change of the contract.
- A form that each package can use would be a contract addition: a list of notices with a fixed code
  and named parameters (a minor change). Question 7 asks the user.
- During the run, the progress message shows only the running check [C 2.3]. It cannot carry the
  message.

### 8.4 One consent before a full run [U]

The user decided: "yes, single accept before full run" [U]. `certify_plan("full")` gives the fixed
sentence of the risk in `system_changes` [C 2.6]. The app shows the plans of all packages and asks one
time before `certify()`:

> The full run opens each camera many times and at each of its modes. A camera can stop answering
> until it is unplugged and plugged in again. The run puts back the settings of each camera at the end.

`system_changes` is defined as "one fixed sentence for each change outside the work folder" [C 2.6].
A risk to a device is not named there. The sentence fits, because it is a change outside the work
folder that can happen; the contract text could name it (question 7).

## 9. The plan, cancel, privacy, cleanup

### 9.1 `certify_plan(level)` [A]

It opens no camera and does not activate a device. It uses only the enumeration of cap 6.2 step 1
(`MFEnumDeviceSources` and two attributes), which the research found safe also with a wedged Kiyo Pro
[M `research/usb_cameras/docs/windows_results_20261110.md` §13]. It loads `comtypes` only in a child.

```json
{
 "package": "skellycam",
 "kind": "full",
 "seconds_estimate": 600,
 "downloads": [],
 "system_changes": ["The full run opens each camera many times and at each of its modes. A camera can stop answering until it is unplugged and plugged in again. The run puts back the settings of each camera at the end."],
 "questions": [
  {"section": null, "id": "lit-as-usual", "text": "Was the room lit as it is when you record?"},
  {"section": null, "id": "all-cameras", "text": "Were all the cameras that you record with attached?"},
  {"section": null, "id": "camera-ok-after", "text": "Do all the cameras still work in other programs after the run?"}
 ],
 "details": {
  "cameras": [{"label": "cam.media-foundation.046d-085c.0", "name": "Logitech C922", "device": "046d:085c", "evidence": "verified"}],
  "system_evidence": "unknown",
  "virtual": 4,
  "checks": ["detect", "cam.media-foundation.046d-085c.0:opens", "..."]
 }
}
```

- `downloads` is empty in both levels: the full level makes its synthetic frames.
- `system_changes` is empty for `quick` (the restore of phase G puts back what quick changes).
- `questions` holds `camera-ok-after` only for `full`.
- `details.cameras[].evidence` and `details.system_evidence` come from the known-systems file
  (section 11): `verified`, `known-bad` or `unknown`.

### 9.2 Seconds estimate

Quick: section 4.7. Full: section 16.

### 9.3 Cancel and time limits [A]

- The caller reads `cancel.is_set()` at least two times each second [C 2.4].
- On a cancel or a time-out of a session child, the caller first ends the main process of the child
  only. Its camera processes notice the dead server after 10 s [U], finish their files and release the
  cameras. The caller waits for them at most 12 s, then kills the rest of the tree. Then phase G runs
  for the cameras that did not hang (8.3), and phase H. A cancel then returns in about 13 s plus phase
  G, not in 1 s [U: question 12 of draft 1, "yes"].
- Each check that did not end is `not-run` with `cancelled` [C 2.4].
- Time limits: detection 20 s; the quick session child 45 s; a camera block of `full` 240 s; a group
  take its length plus 30 s; a self-check 40 s; `system:disk` 60 s; the benchmark 45 s; phase G 20 s
  for each camera. A child over its limit gives `fail` with `timed-out` [C 2.5].

### 9.4 Privacy and camera names [U, A]

The contract rules 1 to 16 apply [C 6]. In addition:

- Never in the report: a serial number, a device path or symbolic link, the `camera_id` (a hash of the
  link, so of the unit), a host name, a user name, a file name or a folder of a take or of the disk
  checks, a frame.
- The camera name: the model string of the device. On Windows today this is the friendly name of
  Media Foundation, which can be generic: the Kiyo Pro shows as "USB Video Device"
  [M `research/usb_cameras/docs/hardware_run_3a_20261120.md`]. Step 5d gives the USB product string
  (section 13).
- Name cleaning, in this order, before the report exists [U, A]:
  1. Remove a possessive head: the text up to and with `'s ` or `’s ` (`Alex's iPhone Camera` gives
     `iPhone Camera`) [C 6 rule 16].
  2. Remove each word that is the user name or the host name of the run (rule 12). If a word was
     removed, the name becomes `Camera vvvv:pppp`, or `Camera` with no USB IDs.
  3. Remove a group of 8 or more letters and digits that has at least 4 digits (a serial number), and
     brackets that become empty.
  4. Remove `(R)`, `(TM)` and double spaces; cut to 64 characters.
- The failure text of the product (cap 12) is mapped to a reason code and never copied.

### 9.5 Cleanup [A]

- The work folder is `skellycam-certify-<uuid4>/` in `recording_folder`, or in the temporary folder of
  the system. The take, the disk check and the benchmark write only there.
- Certify deletes the work folder at the end, also after a cancel, a crash or a time-out [C 2.5]. A
  folder that does not go gives the cleanup row `delete-work-folder` with `not-deleted`.
- At the start, certify deletes earlier `skellycam-certify-*` folders that hold the marker file
  `.skellycam-certify`. It deletes nothing else.
- The report holds no media and no file name of a take [C 6 rule 7].

## 10. Linux and macOS: certify validates the assumptions of the new native sources

### 10.1 The decision and the state

The user decided: "certify runs to validate assumptions about linux and mac code. Ideally as much real
code is implemented as possible now so a single test run provides as much information as possible and
can be used there and then if the tests pass." [U]

Thus:

- The real native sources for Linux (V4L2 through `ctypes`) and macOS (AVFoundation through PyObjC,
  controls through IOKit endpoint-0 requests [P §3]) are built in the product now. Phase 7 moves up. A
  separate spec job writes their spec [U].
- They are written from what we know and assume: the research suites of
  `research/usb_cameras/suite/linux/` and `suite/macos/` with their runbooks, and the cross-platform
  plan (`research/usb_cameras/docs/xplat_capture_plan.md` §2.5, §2.6). Neither suite has run on
  hardware [P §7].
- Certify tests the product path on all three systems. On Linux and macOS, each assumption of a source
  is a named check whose numbers show **how** it failed, not only that it failed. One run must tell
  which assumption broke [U].
- When a system passes, native capture can be used there at once [U] (11.3).
- The Windows hardware tests T-CAP-92 to T-CAP-98 were planned for Linux and macOS through the OpenCV
  source. With "no OpenCV checks" [U], the checks of this section replace them. Hot-unplug (T-CAP-95)
  is not tested [U].

### 10.2 The assumptions as checks

Each check is a camera check `<label>:<name>` or a group or system check. Each check runs when the
camera opens, also when another assumption check of that camera failed: a failed `native-jpeg` does
not stop `clock`, `sequence` or `controls` [A]. Only a failed `opens` stops the others. "D-n" is a
diagnostic that the source must give (10.3). "W" means that the same check also runs on Windows.

| Check | Assumption of the source | Numbers (how it failed) | Pass rule | Notes and sources | D |
|---|---|---|---|---|---|
| `<label>:native-jpeg` (claim, W) | Linux: the camera gives its own MJPG bytes through `VIDIOC_DQBUF` on mmap buffers, with no re-encode. macOS: AVFoundation hands over the camera's JPEG in a block buffer (`'dmb1'`), not only decoded pixels. | `requested_fourcc`, `granted_fourcc`, `granted_w`, `granted_h` (`S_FMT` picks the nearest size with no error), `delivered` (`jpeg`, `decoded`, `none`), `video_settings` (macOS: the variant that gave JPEG: `nil`, `empty`, `dmb1`), `bytesused_equals_payload`, `error_flag_frames` (`V4L2_BUF_FLAG_ERROR`), the numbers of 4.4 | 4.4 | xplat §2.5 item 1, §2.6 G-MJPEG; L-MJPEG, M-MJPEG. One third-party run on macOS saw MJPEG only as decoded `420v`. | D-1, D-3, D-10, D-11 |
| `<label>:clock` (W) | The driver time of a frame is on the clock of `arrival_ns` (Linux `CLOCK_MONOTONIC`, the clock of `perf_counter_ns`; macOS host time), before the arrival, and near it. | `clock` (`monotonic`, `realtime`, `host`, `device`, `unknown`), `tstamp_src` (`soe`, `eof`, `unknown`), `sample_minus_arrival_p5_ms`, `_p50_ms`, `_p95_ms`, `later_than_arrival` (count), `grain_ms`, `jitter_p95_ms` (against the fitted period), `sample_time_kept` | `pass` when the clock is the arrival clock, no sample is later than its arrival, and p95 is within 200 ms (cap 4.2); `fail` with `clock-base-differs`, `sample-after-arrival` or `sample-too-early` | Linux: the buffer time is taken at the first payload, in steps of URB completions (up to about 4 ms). macOS: Apple documents only the `synchronizationClock`. Windows: arrival minus sample 0.33 ms (Logitech) and 32 ms (Kiyo Pro) [M hardware_run_3a]. | D-2 |
| `<label>:sequence` (W where the driver gives a count) | The driver sequence number counts each frame that the camera sent, so that a drop shows as a gap. | `sequence_available`, `sequence_gaps`, `long_intervals` (over 1.5 periods), `gaps_explain_intervals` (long intervals that have a sequence gap), `discontinuity_flags` | `pass` when each long interval has a sequence gap; `fail` with `sequence-unreliable`; `not-run` with `no-sequence` when the driver gives none | Linux `v4l2_buffer.sequence`; macOS `CMIOSampleBufferGetSequenceNumber`. Windows: a dropped C930e frame showed only as a 64 ms gap and the discontinuity flag [M free_run_log §2]. | D-3 |
| `<label>:controls` (W) | The source lists each control with its native unit and range, and maps the skellycam exposure unit (log2 s) to it. | for exposure, gain, focus, white balance: `present`, `min`, `max`, `step`, `default`, `auto_supported`; `exposure_unit` (`log2-s`, `100us`, `none`); `exposure_native_at_m7` (Linux: 78 expected); `control_path` (`v4l2`, `avf-lock`, `ep0`, `iam`, `ks`) | `pass` when -7 maps to the expected native value within one step; `fail` with `unit-mapping`; the ranges are record-only | Linux: `exposure_time_absolute` in 100 µs. macOS: AVFoundation has only auto or locked; absolute values only through endpoint 0. | D-4 |
| `<label>:auto-off` | Auto exposure, auto focus and auto white balance can be turned off, and they stay off. | `ae_off_ok`, `af_off_ok`, `awb_off_ok`, `ae_back_on_after_s` (`null` when it stays off), `set_while_auto_errno` (Linux `EACCES`) | `pass`; `fail` with `auto-not-off` or `auto-came-back`; `not-run` with `control-absent` | xplat §2.6 G-CTRL | D-4, D-5 |
| `<label>:settings-stick` (claim, W) | A set value reads back, stays, changes the image, and is still set after a close and a reopen. | the numbers of 4.3, and `kept_after_idle_5s`, `kept_after_reopen` | 4.3; `fail` also with `setting-lost-on-reopen` | Linux 6.16 and later: an idle camera can autosuspend and lose its controls. The read-back can be cached, so the image decides. | D-4 |
| `<label>:modes` (W) | The listed modes are the modes that the camera delivers. | `declared`, `opened`, `granted_equals_request`, `delivered_within_3pct` (counts over the modes that the run opened) | `pass` when each opened mode was granted as requested; `fail` with `mode-not-granted`; the rates are in the rate checks | `S_FMT` changes a size with no error; the Kiyo Pro declares 60 and gives 30. | D-1 |
| `<label>:identity` (W) | The `camera_id` of the source is stable and unique: the same over two detections, and different for two cameras of one model. | `id_stable`, `id_unique`, `id_source` (`serial`, `id-path`, `unique-id`, `mf-link`), `has_serial` | `pass`; `fail` with `id-unstable` or `id-collision` | Linux: by-id names collide for identical cameras with no serial. macOS: `uniqueID` holds the port. | D-7 |
| `<label>:timings` (W) | Open, first frame and close stay under the limits of cap 6.4 and 6.6. | `open_ms_p50`, `open_ms_max`, `first_frame_ms_max`, `close_ms_max` | `record-only` | L-CYC, M-CYC | D-6 |
| `<label>:in-use` (W, phase F) | A camera that another program holds gives a clear in-use failure at a known call. | `outcome` (`refused`, `shared`, `hung`), `call` (`open`, `s-fmt`, `reqbufs`, `streamon`, `session-start`, `first-frame`), `native_code` (a number) | 8.2 | Linux: `EBUSY`, but `S_FMT` sends a PROBE to the camera before it. macOS: two programs can share a camera [NV]. | D-5 |
| `group:open` (W) | A USB bandwidth refusal gives a known error. | `refusal_signal` (`error`, `zero-frames`, `low-rate`, `none`), `native_code`, `call`, the camera that loses | 4.2 | Linux: `ENOSPC` at `STREAMON`, also `ENOMEM`, `EIO`, `EPIPE`, `ETIMEDOUT`. macOS: no documented error. | D-5, D-9 |
| `system:camera-access` | The process can open cameras: Linux through the seat ACL or the `video` group; macOS with the camera permission of the app. | `access` (`seat-acl`, `video-group`, `none`), `tcc` (`granted`, `denied`, `restricted`, `not-determined`) | `pass`; with no access, each camera is `not-run` with `no-access` or `no-permission`, not `fail` | macOS: a process with no permission gets zero frames and no error. The permission belongs to the app that starts the process (question 9). | D-8 |
| `system:video-effects` (macOS) | No system effect changes the frames. | `center_stage`, `portrait`, `studio_light`, `reactions`, `edge_light` (booleans, `null` when the source cannot read one) | `record-only` | M-FX | D-8 |
| `<label>:control-ep0` (macOS, phase F) | UVC requests on endpoint 0 set an absolute exposure, gain and focus with no claim of the interface, and read back. | `range_read`, `set_ok`, `readback_ok`, `image_effect`, `restore_ok`, `ioreturn` (a number) | `pass`; `fail` with `ep0-refused` or `readback-differs` | Outside the documented contract of Apple. A Kiyo Pro had greyed controls on an M4 and not on an M2. | D-4, D-5 |
| `group:take`, `<label>:records`, the rate checks, the exposure sweep (W) | The rest of the product works on the native source. | sections 4 to 8 | as there | T-CAP-92 to 94, 96 to 98 | — |

### 10.3 Diagnostics that the native sources must give (requirements for the phase 7 spec) [A]

The product path can show only what the source reports. Thus each source gives these fixed-key
diagnostics (Media Foundation too, where it can), through a call `diagnostics() -> dict` that the
camera status carries. They hold no path, no serial and no free text.

| ID | Diagnostic |
|---|---|
| D-1 | The requested and the granted format: fourcc, width, height, rate (Linux: after `S_FMT` and `S_PARM`; macOS: the active format and the delivered media subtype). |
| D-2 | For each frame: the raw driver time in its own unit, the clock of that time (Linux: the `V4L2_BUF_FLAG_TIMESTAMP_*` and `TSTAMP_SRC_*` flags; macOS: the timescale and whether the clock is the host clock), and the conversion that made `sample_ns`. |
| D-3 | For each frame: the driver sequence number, the driver error flag (`V4L2_BUF_FLAG_ERROR`) and `bytesused`. |
| D-4 | For each control: the native id, the native value and unit, the range (min, max, step, default), the auto flag, the path used (V4L2 control, AVFoundation lock, endpoint 0, `IAMCameraControl`, `IKsControl`), and the native return code of each set and get. |
| D-5 | For each failed call: the fixed failure code [U], the native code (errno, `IOReturn`, `NSError` code, HRESULT) as a number with a fixed domain string, and the call. |
| D-6 | The time of each open step and of the close. |
| D-7 | The kind of the identity input (`serial`, `id-path`, `unique-id`, `mf-link`) and whether a serial exists. The strings stay in the product; the report gets only the kind. |
| D-8 | macOS: the camera authorization status and the effect flags of the device. Linux: how the process reached the node (seat ACL or group). |
| D-9 | Linux: the granted USB alternate setting at the stream start (sysfs, readable by each user), for the bandwidth domain. |
| D-10 | A count of frames that skellycam decoded or encoded in the capture path: 0 for passthrough. |
| D-11 | A SHA-256 of each of the first 30 raw buffers, so that certify compares them with the ring and the MKV. No bytes go into the report. |

### 10.4 Probes [U, A]

A probe is allowed only where the product path cannot see the fact [U]. It is named `probe:<check>`,
is record-only, and runs in its own child. It never opens a camera.

| Probe | What the product cannot see |
|---|---|
| `probe:camera-holders` (Linux) | The processes that hold the video nodes before any open (`/proc/*/fd`), as a fixed list `pipewire`, `wireplumber`, `other`. Certify then does not open a held camera, because `S_FMT` sends a PROBE to the camera before it returns `EBUSY`. |
| `probe:kernel` (Linux) | The kernel version as a number, and which `uvcvideo` quirks are expected: the Kiyo Pro `NO_LPM` quirk (7.0, and the stable 6.12.81, 6.18.34, 6.19.12), the C922 SOF quirk (6.11), `nodrop` (6.14). |
| `probe:usb-alt` (Linux) | The granted alternate setting of each camera from sysfs, when the source does not give D-9. |

### 10.5 A failing native source must not break the run or the system [U, A]

The code of the new sources is unproven. Thus:

- Each camera runs in its own camera process [P §3], and the session child runs the group. A crash in
  `ctypes` or PyObjC ends only that camera process. The product reports "camera process ended (exit
  code n)" (cap 6.6); certify gives the running assumption check `fail` with `crashed` and
  `numbers.exit_code`, and goes on with the other checks and the other cameras.
- Each call of the source is bounded, as on Windows (cap 6.6). A hang gives `fail` with `hung` and the
  `call` of D-5.
- A Linux process in an uninterruptible kernel wait (`D` state) cannot be killed. Certify then stops
  the wait at its limit, reports `hung` with `numbers.unkillable` true, gives the camera the after-run
  state `replug` (8.3) and returns its report. The process ends when the kernel call returns.
- The detection child is bounded (20 s). A crash there gives `detect` `fail` with `crashed`; the
  self-checks and the system checks still run.
- A camera whose source failed is never opened again in that run (2.3).

### 10.6 Quick on Linux and macOS

Quick on Linux and macOS is the quick of section 4 through the native source: `opens`, `rate`,
`settings-stick`, `native-jpeg`, `records`, and also `clock` and `sequence`, which come from the same
frames at no extra time [A]. Thus quick meets the contract rule that a recording can start
[C 2.7 rule 3]. `controls`, `auto-off`, `modes`, `identity` and `control-ep0` are in `full`.

## 11. Known systems and cameras, and the flow from a report to a release

The user stated the goal: "The goal is for certify reports to feed into that repo. When we have
sufficient evidence to say "yup, native capture works on this OS, or with these cameras" then that
gets bundled into the code build for the next release. Certify should prompt for new OS versions and
cameras it hasn't encountered before." [U]

### 11.1 What the contract has today

- The app sends a report to the relay only after the person chose "send" [C 4.1]. The relay commits it
  to the branch `inbox` of the repository `skellycertify` and opens an issue there. Test mode is on
  now: label `relay-test`, never evidence.
- A reviewer checks the form, the privacy, and the validity [C 7.1]: a SemVer version, a commit of 40
  hex digits in the **public repository of the package** [C 9], a clean tree, a complete run, the kind.
  Then the reviewer commits the file to `reports/` of `skellycertify` and writes the evidence row
  (`review.md`).
- A valid quick module makes the item usable on that system only. Only a valid full module can give a
  reviewed row [C 7.2].
- Accepted evidence lives in the package, as a data file that it ships: "The app reads evidence rows
  only from the packages that it ships with. Each package gives the format of its rows." The model is
  `skellytracker/core/eps/ep_evidence.yaml` of skellytracker: one row for each EP, OS and GPU model,
  `source: maintainer` or `field`, checked by a tool of that repository.
- The key of camera evidence is the camera model (USB VID:PID), the capture backend and the OS [C 7.4].
- skellycam has no row format, no file, no checker and no public repository yet [C 9].

So "that repo" in the words of the user is the public repository of skellycam: the place of the
commits that a report can name, and of the evidence file that a release ships.

### 11.2 The data file [A]

`skellycam/core/camera/camera_evidence.json`, shipped in the package. JSON, because skellycam has no
YAML library and must not add one for this. The app never downloads it.

```json
{
 "schema": 1,
 "systems": [
  {"os": "Windows", "os_key": "11 26H2", "backend": "media-foundation", "state": "verified",
   "source": "maintainer", "reports": ["<report id>"]}
 ],
 "cameras": [
  {"device": "046d:085c", "model": "Logitech C922", "backend": "media-foundation", "os": "Windows",
   "state": "verified", "source": "maintainer", "limits": ["rate-60-at-m7-only"], "reports": ["<report id>"]},
  {"device": "1532:0e05", "model": "Razer Kiyo Pro", "backend": "media-foundation", "os": "Windows",
   "state": "verified", "source": "maintainer", "limits": ["rate-60-not-delivered", "wedge-risk", "name-generic"],
   "reports": ["<report id>"]},
  {"device": "4c4a:4a55", "model": "USB Camera", "backend": "media-foundation", "os": "Windows",
   "state": "known-bad", "source": "maintainer", "limits": ["rate-below-declared"], "reports": ["<report id>"]}
 ]
}
```

- `state`: `verified`, `known-bad`. A key with no row is `unknown`.
- `os_key`: Windows: the release and the feature version from `os.label` (`11 26H2`); macOS: the major
  version (`26`); Linux: the kernel major and minor version (`7.0`), because `uvcvideo` changes by
  kernel (X-14).
- `limits`: fixed codes, each with one sentence in `skellycam/REASON_CODES.md`, for example
  `rate-60-not-delivered`, `rate-60-at-m7-only`, `rate-below-declared`, `cliff-m6`, `wedge-risk`,
  `name-generic`, `no-native-jpeg`, `settings-revert`.
- `reports`: the report ids [C 3.1] in `reports/` of `skellycertify`.
- A tool `tools/check_camera_evidence.py` refuses a row with a missing or wrong field, as the checker
  of skellytracker does.

### 11.3 How the product uses it (question 6) [A]

- Detection gives each camera a field `evidence`: `verified`, `known-bad` or `unknown`, and the status
  gives `system_evidence` for the OS key and the backend.
- Windows: native capture is the only path after phase 3 (no fallback, cap 14.2). An `unknown` camera
  works as any camera; the UI shows "Not verified yet: run the camera check and send the report". A
  `known-bad` camera shows its limits as fixed texts (for example "This camera declares 60 fps and
  delivers 30").
- Linux and macOS: "when a system passes, native capture can be used there at once" [U]. Proposal
  (question 6): native capture is the default on an OS key that is `verified` in the file, and on a
  system where a local `full` run of certify passed (a local pass [C 7.2]); on each other system the
  product keeps its source of today (OpenCV) and the UI shows the prompt of 11.4. The plan says that
  OpenCV goes per OS once native capture passes there [P §3]; the file then decides "passes there".
- The limits never replace the checks of the product: the real 60 fps check still runs [U].

### 11.4 The prompt for a new OS version or camera [A]

- The contract has no prompt. The nearest mechanism: skellytracker's plan skips at level `quick` an
  item that has a reviewed row, and a package can say in the plan `details` which items have no row.
- skellycam: `certify_plan` gives `details.cameras[].evidence` and `details.system_evidence` (9.1).
  The product status gives the same fields (11.3).
- The app owns the prompt: when a camera or the OS key is `unknown`, the app offers "SkellyCam has not
  seen this camera (or this OS version) yet. Run the camera check and send the report?" The prompt
  comes at the first detection of the new item, and one more time at most after 7 days [A].

### 11.5 From a report to a release (question 5) [A]

1. The person runs certify and chooses "send". The relay files the report in `skellycertify`.
2. A reviewer checks it by `review.md`, with the rules that the certify session adds for skellycam rows.
3. A tool of skellycam, `tools/camera_evidence.py propose`, reads the reviewed reports of `reports/`
   and proposes rows by this rule:
   - **Camera verified** for (device, backend, OS): 3 valid `full` reports from 2 different systems,
     with the camera row `pass` (or `partial`, then its limits go into `limits`), and no `fail` of a
     pass/fail check of that camera; or 1 valid `full` report of a maintainer (`source: maintainer`).
   - **Camera known-bad**: 2 valid reports from 2 systems with the same failed claim and reason; or 1
     maintainer report.
   - **OS key verified** for (OS key, backend): 3 valid `full` reports from 2 different systems, each
     with at least one camera `pass` and each self-check `pass`.
   - "Different systems": a different value of (`cpu.name`, `os.build`, `memory_bytes`) [C 3.3]. Two
     systems of one model look the same; the rule then counts them as one, which is safe.
   - A `quick` report counts as "seen" only [C 7.2].
4. A maintainer accepts the proposed rows in a pull request to the public repository of skellycam.
5. The next release ships the file.

### 11.6 What the contract lacks for this

- The record type of camera evidence (7.4 says "comes later") and the row table of `review.md` for
  skellycam.
- The public repository of skellycam in section 9: the user decided `https://github.com/domisjustanumber/skellycam` [U].
- The fixed backend strings (`media-foundation`, `v4l2`, `avfoundation`).
- A rule for "different systems".
- The values `partial` and `not-run` of a summary item, with `reason` (question 1).
- A list of notices to the person (8.3, question 7).
- Labels of the relay for camera reports.

## 12. What skellycam tests and what it leaves to others

This section is for the freemocap session, which coordinates the checks of the modules.

**skellycam tests:**

- The cameras: detection, the modes, the open, the frame rate at each selected mode, the settings that
  stick, the native JPEG, the exposure sweep, SkellyCam Auto, the controls, the timestamps, the in-use
  case, the open and close cycles, and the restore of each camera at the end.
- The cameras together: the USB bandwidth at the open, the rate under contention, the spread between
  cameras (record-only).
- The recording of camera frames: a take through the skellycam recorder, its files (MKV, CSV,
  manifest), the take rate, the decode of each frame.
- The disk for takes: the recorder at the real load (`system:disk`) and the raw write speed in MB/s
  (`system:disk-benchmark`), both in the folder where the person records. freemocap gives that folder
  as `recording_folder`.
- The CPU of the capture and recording processes only, with fake cameras up to 8 at 1080p30.
- The USB link of each camera, and the programs that hold cameras (Windows allow-list, Linux holders).
- The rules of the skellycam software on this system: the hung camera (100 ms), the camera crash in a
  take, the dead server (10 s), the disk stall, no spin, the JPEG ring on this CPU.
- On Linux and macOS: the assumptions of the native sources (section 10).

**skellycam leaves to others:**

- The GPU, the execution providers, the pose pipeline, the model timing and the JPEG decode on the GPU:
  skellytracker.
- The realtime pipeline session that reads the skellycam rings, and the post-hoc session: freemocap
  and skellytracker. skellycam checks only that its rings take frames.
- The app: the build identity, the start of a child process, the imports of the bundle, the data
  folder and its write access, Blender, the install facts: freemocap.
- The audio recording (step 5b is not built): nothing today.
- The OS, the CPU, the memory and the GPU list: each module writes `host` [C 3.3]; the report file
  prints it one time [C 4.2]. skellycam adds no other system benchmark.

**Possible overlaps to agree:**

- A disk check in freemocap (for example the write test of its data folder) and the skellycam disk
  checks: skellycam proposes to own the speed and the take load, and freemocap to own only the access.
- A CPU benchmark: skellycam measures only its own processes. A whole-system CPU benchmark belongs to
  one module only, if any.
- A recording check in freemocap: the skellycam quick take already shows that a recording starts. A
  freemocap check should use a skellycam take, not a second one.
- The app must close its own camera groups before a certify run [U]; freemocap owns that rule
  in the app.

## 13. What the product is missing

| Need | Today | Step that delivers it |
|---|---|---|
| A fixed failure code (`camera-in-use`, `usb-bandwidth`, `hung`, ...) in the failure object of cap 12 | Free text only (`errors.py`) | None planned. The user decided it [U]. |
| The controls before the first set, in the status ("before" values of phase A) | `set_controls` reads before each set, but does not report it | The certify step |
| A restore of the "before" values at the close (saves phases A and G in quick) | None | The certify step (question 4) |
| A count of frames that skellycam encoded (`encoded_by_skellycam`) | None | 3b (the encoder counts its frames) |
| A public enumeration with no activation, bounded, for the plan | `MediaFoundationBackend.devices()` in the detection child only | The certify step |
| The full mode list with formats (`capture_modes`) | MJPG only | 3c |
| Uncompressed modes | Not built | 3b |
| Gain and focus through the config; white balance and power line read | Exposure only | 3c |
| Control ranges (min, max, step, default: `GetRange`) | Not read | Not in the 3c spec. Add to 3c. |
| USB link per camera | Not built (D45) | The port of `usb_connection.py` of upstream `sfn26` [P §14], with 5d |
| The model name (USB product string) | Friendly name only | 5d (`device.model`, rec 6.7) |
| Stage times (open, first frame, ready, close) in the status | Log only | The certify step |
| A discontinuity count in the status or `CameraTakeResult` | Not counted | The certify step |
| `measured_fps` after `too_slow` | Keeps the old value (3a fault) | A fix before 5.2 |
| The fake source and a synthetic frame source in the package | In `skellycam/tests/` | The certify step |
| A SemVer version and the build commit with no git (C 2.5) | `2.0.0a6`; no commit metadata | The certify step |
| The evidence file, its checker, the `evidence` field of detection | None | The certify step (section 11) |
| The native V4L2 and AVFoundation sources, with the diagnostics D-1 to D-11 of 10.3 | Research code only | Phase 7, moved up [U]; a separate spec |

## 14. Questions for the user

The user answered each question of draft 1 on 2026-11-20 ([ADR-GVC0](../decisions/entries/GVC0-certify-decisions-of-the-user.md)).
These questions are only the new ones that draft 2 opens. Each is worded so that "yes" accepts the
recommendation. The most important is first.

1. The camera row has five claims (opens, rate, settings stick, native JPEG, records). We ask the owner
   of the contract for one format change (1.3.0) that adds `partial` and `not-run` with a `reason` to a
   summary item. The camera table then shows `pass`, `partial` (works at the base setting, but a setting
   did not stick or there is no native JPEG), `fail`, `in use` and `record`. The alternative with no
   change: the row stays `pass`, `fail` or `record`, each failed claim shows in the "Failed checks" table
   under the camera table, and "in use" shows as `record` with the reason `camera-in-use`. Yes to the
   change?
2. The supervisor read "can you jpegs" as: does the camera give its own JPEG frames, passed through
   unchanged (MJPG passthrough, no decode and no re-encode), in the capture path of the product. Is this
   reading right?
3. The quick settings check: open at manual -7, one live change of all cameras to -8, read back at once
   and 1 s later, and the image must get darker; after 3c also gain and focus at their current values.
   Yes?
4. The product restores the "before" values of each camera at its own close, so that quick with the
   hang self-check stays near 30 s for four cameras (about 31 s, against 35 s with a separate restore).
   Yes?
5. The known-systems file `camera_evidence.json` in the package, keyed by OS key and backend, and by
   camera VID:PID, backend and OS, with the states `verified` and `known-bad` and fixed `limits` codes;
   `verified` needs 3 valid full reports from 2 different systems, or 1 maintainer report, and a
   maintainer accepts each row in a pull request. Yes?
6. On Linux and macOS, native capture is the default on a verified OS key and on a system with a local
   passed full run; elsewhere the product keeps its source of today, and the app prompts the person to
   run certify and send the report for an unknown camera or OS version. Yes?
7. A camera that is not well after the run gets a cleanup row `release:<label>` with `camera-wedged` or
   `camera-not-restored`, and the app shows "Camera <name>: wedged, please replug" (an agreement with
   freemocap, no contract change now). We also ask the owner of the contract for a list of notices, and
   to name a risk to a device in the text of `system_changes`. Yes?
8. The disk benchmark of 6.3: 1 GiB in 4 MiB blocks, fsync each second, at most 30 s, in the recording
   folder, deleted after, reported as MB/s with the count of 1080p30 cameras it carries. Yes?
9. On macOS, the app asks the camera permission before a certify run; without it, each camera is
   `not-run` with `no-permission`, and certify never shows a dialog itself. Yes?

## 15. Reason codes (proposed `skellycam/REASON_CODES.md`) [A]

Common codes that skellycam uses [C 5.3]: `timed-out`, `crashed`, `bad-output`, `hung-at-exit`,
`cancelled`, `not-built`, `not-selected`, `no-version`, `no-commit`, `modified-tree`.

| Code | Where | Meaning |
|---|---|---|
| `backend-missing` | `detect` | The capture backend is not on this system (for example no Media Foundation). |
| `no-camera` | `evidence.reasons`, group checks | The run found no real camera. |
| `one-camera` | group checks | The check needs two cameras. |
| `no-mode` | mode checks | The camera does not declare this mode. |
| `no-mjpg-mode` | `<label>:detect` | No MJPG mode at 30 fps or more (before 3b). |
| `below-floor` | `opens` | The nearest mode is below 30 fps (cap 7.5). |
| `camera-in-use` | `opens`, camera row | Another program holds the camera. |
| `usb-bandwidth` | `opens`, `group:open`, `<label>:group-open` | The USB controller refused the stream for bandwidth. |
| `not-found` | `opens` | The camera was gone at the open. |
| `open-failed` | `opens` | Another open failure; `numbers.hresult` holds the code. |
| `first-frame-timeout` | `opens`, `cycles` | No first frame in 5 s (cap 6.4). |
| `hung` | any camera check | A bounded call hung; the camera process ended hard (cap 6.6). |
| `not-ready` | `opens` | Not ready in 15 s (cap 9.3). |
| `rate-low`, `rate-high` | rate checks | More than 3 % below or above the mode rate. |
| `rate-under-contention` | group | The camera passes alone and fails in the group. |
| `too-dark`, `too-bright` | light-dependent checks | The frame is too dark or too bright to judge (4.6). |
| `readback-differs`, `setting-reverted`, `no-image-effect`, `control-failed`, `exposure-not-applied` | settings and control checks | A set value reads back different; it changed back later; the image did not change; the set call failed; a set exposure did not apply. |
| `control-absent` | control checks | The camera has no such control. |
| `no-native-jpeg`, `jpeg-damaged`, `jpeg-size-differs` | `native-jpeg` | skellycam encoded the frames; a frame is damaged; its size is not the size of the mode. |
| `wrong-reason` | `<label>:in-use` | The product gave a failure that is not "in use". |
| `device-removed`, `stalled` | any camera check | Removed; no frame for 2 s (cap 6.7). |
| `take-not-finished`, `take-error`, `rows-differ`, `missing-rows`, `gaps-unexplained`, `group-rate-off`, `too-few-frames`, `frame-not-decodable` | take checks | Section 4.5. |
| `fat-disk`, `disk-stall`, `write-error`, `disk-slow`, `disk-full` | take checks, `system:disk`, benchmark | rec 4.2, 5.3, 5.4; section 6. |
| `gap-over-limit` | `self:` checks | A healthy fake camera had a gap above 100 ms. |
| `clock-base-differs`, `sample-after-arrival`, `sample-too-early` | `clock` | 10.2. |
| `sequence-unreliable`, `no-sequence` | `sequence` | 10.2. |
| `unit-mapping`, `auto-not-off`, `auto-came-back`, `setting-lost-on-reopen`, `mode-not-granted`, `id-unstable`, `id-collision`, `ep0-refused` | assumption checks | 10.2. |
| `no-access`, `no-permission` | camera checks | Linux: no access to the video node; macOS: no camera permission for the app. |
| `prior-failure`, `prior-check-failed` | any | The camera hung or failed earlier; a check that this check needs did not pass. |
| `time-budget` | any | The quick limit of 45 s left no time for the check. |
| `camera-wedged`, `camera-not-restored` | cleanup `release:<label>` | 8.3, with the sentence for the person. |
| `not-deleted` | cleanup | The work folder did not go. |
| `<ExceptionClass>` | any, cleanup | A step raised this class. Never the message. |

Fixed values in `numbers`: `backend` (3.1), `stage` (cap 12, `-` for a space), `state` (cap 8.1),
`outcome` (8.2), `format`, `file_system` (`ntfs`, `refs`, `exfat`, `fat32`, `apfs`, `hfs`, `ext4`,
`btrfs`, `xfs`, `other`), `usb_link` (`usb3`, `usb2`, `usb1`, `unknown`), the values of 10.2, and the
`limits` codes of 11.2.

## 16. Time estimates [A]

The camera block of `full` on Windows (each apply of one camera about 6 s at 30 fps; each live step
of cap 10.2 about 2.5 s at 30 and 1.3 s at 60):

| Phase | Step | Seconds |
|---|---|---|
| C | `rate:1920x1080@30`; the largest size (often the same: 0) | 6 to 12 |
| C | Exposure sweep at `<base>` (at most 9 steps) | 23 |
| C | Auto, controls | 9 |
| F | In-use | 8 |
| F | Two 60 fps modes and the sweep at 60 | 18 |
| F | Five cycles | 10 |
| G | Restore and plain open | 2 |
| | Start and end of the camera block children | 6 |
| | Sum | about 90 |

The rest of `full`: quick 35 s, `group:take-30` 45 s, `group:take-60` 25 s, `system:disk` 35 s, the
benchmark 5 to 35 s, self-checks 110 s. About 270 s.

| Cameras | Quick | Full |
|---|---|---|
| 1 | 30 s | about 6 min (270 + 90 s) |
| 4 | 35 s | about 11 min (270 + 360 s) |
| 8 | 36 s | about 17 min (280 + 720 s) |

The quick figures include `self:hang-100ms` and phases A and G; without them, or with the restore in
the product, quick is about 23 s for four cameras. The camera blocks run one camera at a time: two
cameras at once would share a USB domain and change each other's results. On Linux and macOS the
assumption checks of 10.2 come mostly from the same opens; they add about 10 s for each camera, and
the endpoint-0 controls of macOS about 60 s more, from the 12 to 15 and 20 to 30 minutes of the
research runbooks for four cameras [M `research/usb_cameras/suite/linux/RUNBOOK_PLAN.md`,
`suite/macos/RUNBOOK_PLAN.md`]. All figures are [NV] until the first run.

## 17. Test list of the certify code

Each test uses fake sources or fake backends, unless it says "hardware". No test opens port 53117.

| ID | What it does | Pass criterion |
|---|---|---|
| T-CERT-01 | `certify_plan("quick")` and `("full")` with a fake enumeration of 0, 1, 4 and 8 cameras and 4 virtual cameras, and a fake evidence file. | The fields of C 2.6; empty `downloads`; the risk sentence in `system_changes` for `full` only; `seconds_estimate` by 4.7 and 16; `evidence` of each camera from the file; no activate call; `comtypes` not imported in the caller. |
| T-CERT-02 | `certify("slow")`, `certify_plan("")`. | `ValueError` [C 2.2]. |
| T-CERT-03 | Quick with 4 fake cameras. Validate the report. | Each required field of C 3.1; `kind` = level; each name matches C 3.4 and is unique; each `fail` and `not-run` has a reason of C 5.2; each `numbers` value has an allowed type; the schema id. |
| T-CERT-04 | Fakes with planted values: a host name and a user name in a camera name, a path, a MAC-like string, a serial, `take.mkv`, a long string. | C 6 rules 1 to 11 hold; the planted values are gone. |
| T-CERT-05 | Camera names: `Alex's iPhone Camera`, `Kamera’s Webcam`, a name with the host name, `HD Webcam (SN 12AB34CD56)`, `USB Video Device`. | `iPhone Camera`, `Webcam`, `Camera vvvv:pppp`, `HD Webcam`, `USB Video Device`. |
| T-CERT-06 | No camera attached. | Self-checks run; no camera row; `no-camera` in `evidence.reasons`. |
| T-CERT-07 | Quick with 4 good fakes. | Each claim `pass`; 4 rows `pass`; 4 summary items in detection order; the work folder is gone; each camera is `healthy` or `restored` with no cleanup row. |
| T-CERT-08 | The generic-camera pattern (T-CAP-17), bright frames. | `rate` `fail` `rate-low`; row `fail`. |
| T-CERT-09 | The same with dark frames (mean 10). | `rate` `record-only` `too-dark`; row `record`. |
| T-CERT-10 | A fake in use at the open. | `opens` `not-run` `camera-in-use`; the row by the way of question 1; no retry (open count 1). |
| T-CERT-11 | A fake refused for bandwidth in the group that opens alone. | Row `pass`; `group:open` `fail` `usb-bandwidth`. |
| T-CERT-12 | A fake that hangs at the open. | `opens` `fail` `hung`; later checks `not-run` `prior-failure`; never opened again (phase G included); cleanup `release:<label>` `camera-wedged`; the others complete. |
| T-CERT-13 | Settings: a fake whose exposure reads back -5 for a set -7; one that reverts after 0.5 s; one whose image does not change; one with a mean of 240. | `fail` `readback-differs`; `fail` `setting-reverted`; `fail` `no-image-effect`; `record-only` `too-bright`; each row `partial` (way 1) or `pass` with the claim in "Failed checks" (way 2). |
| T-CERT-14 | Native JPEG: a fake that gives YUY2 encoded by skellycam (after 3b); a fake with a cut JPEG; a fake with a SOF of another size; a fake with no DHT. | `fail` `no-native-jpeg`; `fail` `jpeg-damaged`; `fail` `jpeg-size-differs`; `pass` with `dht_inserted` > 0. |
| T-CERT-15 | The session child ends with `os._exit(5)`; sleeps past its limit with a grandchild; gives its result and does not end; gives bytes that are not a result. | `fail` `crashed` with `exit_code` 5; `fail` `timed-out` and no process left; `<name>:exit` `record-only` `hung-at-exit`; `fail` `bad-output`. |
| T-CERT-16 | Cancel during the quick apply and during phase F. | The running and later checks `not-run` `cancelled`; the main process of the child ends first and the fake cameras get `close` within 12 s; phase G runs; no process left; the work folder is gone; `cancelled` in `evidence.reasons`. |
| T-CERT-17 | A progress spy; a progress callable that raises. | `starting` first, `done` last; at most 10 messages each second; each is JSON; after the raise, no more calls [C 2.3]. |
| T-CERT-18 | `sys.stdout` and `sys.stderr` `None`, `sys.frozen` true, in a spawn child. | The report is complete; no read of stdin [C 2.5]. |
| T-CERT-19 | The selection rule with the mode lists of the C930e, the C922, the Kiyo Pro, a 4K camera, a 640x480-only camera and a YUY2-only camera. | The exact checks for each, in the phase order of 2.3; the 60 fps checks and the cycles in phase F; `<base>` `640x480@30` for the 640x480 camera; `no-mjpg-mode` for the YUY2 camera. |
| T-CERT-20 | A fake with no 1080p, no 60 and no focus control. | `not-run` with `no-mode`, `no-mode`, `control-absent`; no `fail`. |
| T-CERT-21 | A fake with the rates of table cap 10.5. | `cliff` -5 for the Logitech table and -7 for the Kiyo Pro table; the sweep stops after two `too_slow` steps. |
| T-CERT-22 | A fake that declares 60 and delivers 30 at each exposure; one that delivers 60 only at -7. | `fail` `rate-low`, and the row stays at its base result; `pass` with `ok_at_m7` true. |
| T-CERT-23 | SkellyCam Auto in a dark scene that hits the range end. | `record-only` `too-dark`, `at_range_end` true. |
| T-CERT-24 | Quick with 4 fakes, local wall clock; then a 50 s delay planted in a check. | Under the estimate of 4.7; with the delay, the next checks `not-run` `time-budget`, the run ends under 47 s plus phase G. |
| T-CERT-25 | Each self-check with fakes, and each with a planted fault of its rule (a 150 ms gap; a take that does not finish; a camera process that does not end in 15 s; a healthy camera marked `dead`; a spin; a torn read that passes). | `pass`; `fail` with the planted fault. |
| T-CERT-26 | Two fakes of one model. | Labels `.0` and `.1`; two summary items with one name; a cleanup row of `.1` maps to the second item. |
| T-CERT-27 | Versions `2.0.0a6` and `2.0.0-a6`; `tree_modified` true; the option `cameras` with one of four labels. | `no-version` only for the first; `modified-tree`; no `partial-run` for the part. |
| T-CERT-28 | Cleanup after a pass, a crash, a time-out and a cancel; a locked file in the work folder; an old work folder with and without the marker; a file of the person in `recording_folder`. | The work folder is gone, or `not-deleted`; the marked old folder is gone; the rest stays. |
| T-CERT-29 | Search the report, and the files that the run wrote outside the work folder. | No media file, no string that ends with a media extension, no frame bytes, no path. |
| T-CERT-30 | Each reason code and each `limits` code that the code can emit, against `skellycam/REASON_CODES.md`. | Each is in the file with one sentence [C 5.4]. |
| T-CERT-31 | Each check name that the code can emit, with the longest backend, `nousb-nousb`, index 9 and rate 29.97. | Each matches the pattern. |
| T-CERT-32 | Patch the rate limit of `rate_check.py` and the stall limit of the take; spy on `CameraGroupManager`, `start_take` and the source factory; set `SKELLYCAM_WINDOWS_CAPTURE=opencv`. | The result follows the patched product limits; each open goes through the calls of 2.2; the native source is used. |
| T-CERT-33 | Quick and full with fakes; list the sockets of the process tree. | No listening socket. |
| T-CERT-34 | Phase G: a fake whose controls were manual -6 and auto focus before the run; a fake whose restore does not read back; a fake that fails the plain open. | Restored to -6 and auto focus (`restored`); `camera-not-restored`; `camera-wedged`. |
| T-CERT-35 | The disk benchmark with a fake file object at 50 MB/s, one that stalls 2 s, and a folder with too little space. | `write_mb_per_s` 50 ±5 %, `cameras_1080p30_typical` 8, `worst` 2; `fsync_ms_max` ≥ 2000; `not-run` `disk-full`; the file is gone. |
| T-CERT-36 | The evidence file: rows with a missing field, a wrong state, an unknown limit code; the proposal tool with reviewed fake reports (3 from 2 systems; 3 from 1 system; 1 maintainer). | The checker refuses the bad rows; the tool proposes `verified` for the first and third, not for the second. |
| T-CERT-37 | Linux and macOS CI: the native sources with a fake `ioctl` and a fake AVFoundation that break one assumption each (decoded buffers only; a realtime clock; samples after arrival; no sequence; a wrong exposure unit; auto that comes back; a control lost on reopen; a granted size that differs; an id that changes; `EBUSY` at `S_FMT`; `ENOSPC` at `STREAMON`; no permission; a segfault in the camera process; a call that never returns). | Each breaks only its own check, with the reason and the numbers of 10.2; the other checks of that camera still run; the crash gives `crashed` with `exit_code`; the hang gives `hung` with the `call`; no permission gives `not-run` `no-permission`; the run ends in its limits. |
| T-CERT-38 | Hardware, Windows: quick on the four test cameras (C922, C930e, Kiyo Pro, generic). | Three rows `pass` (or `partial` with the reason), the generic `fail` `rate-low`, `group:take` `pass`; each camera `healthy` or `restored`. |
| T-CERT-39 | Hardware, Windows: full on the four test cameras. | The facts agree with the measurements of sections 5 and 8 (the Kiyo Pro 60 mode `fail` `rate-low`, the C922 60 mode `pass` with `ok_at_m7`); the risky checks run last; each camera ends `healthy`, `restored` or with `camera-wedged`. |
| T-CERT-40 | Hardware, Linux and macOS: full on the test cameras through the native sources. | Each check of 10.2 has a result and its numbers; the report agrees with the `--plan` runs of the research suites on the same system. |
