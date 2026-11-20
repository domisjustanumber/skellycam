# Certify specification: what a certify run of skellycam measures (draft 3)

Status: draft 3 for the user, 2026-11-20. Spec and test list only: no product code and no test code
exist for it. The decisions of the user that it builds on are in
[ADR-GVC0](../decisions/entries/GVC0-certify-decisions-of-the-user.md) and
[ADR-KG00](../decisions/entries/KG00-certify-decisions-of-the-user-on-draft-2.md). The choices of the
agent are in [ADR-KY81](../decisions/entries/KY81-certify-spec-choices-of-the-agent.md) (draft 2) and
[ADR-8CP7](../decisions/entries/8CP7-certify-spec-draft-3-choices-of-the-agent.md) (draft 3). Section
14 holds the questions for the user. Section 18 answers the Linux and macOS capture spec and lists the
differences to it. Section 10.7 holds the macOS approach probes.

Draft 3 puts in the decisions of the user of 2026-11-20 on draft 2: the answers C1 to C9 (questions 1
to 9 of draft 2), the "for now" rule of the OpenCV fallback, the check of a camera model one time on a
system, the cancel and progress rules, the order of the full run, the exposure rule of the product,
and "native capture only". It is written against format 1.3.0 of the contract: a busy camera is
`skipped` with `busy`, there is one summary item for each camera model, and the codes `cameras-busy`
and `interrupted` are common codes.

## 0. How to read this spec

- **The contract** is `report-format.md` of the repository `skellycertify` (sibling folder
  `../skellycertify/`), format `skellycertify.report/1.3.0`, commit `f7a1831` of `main` (read on
  2026-11-20), with its `review.md`. "[C x.y]" cites section x.y of `report-format.md`. This spec does
  not repeat it. Format 1.3.0 ([ADR-D1PW of skellycertify](https://github.com/domisjustanumber/skellycertify/blob/f7a18315afb5828da71c9154c2bf0f8cb79bae7f/decisions/entries/D1PW-format-1-3-0.md))
  settles the three points that draft 3 asked for: the summary result `partial`, a busy camera as
  `skipped` with the reason `busy` (no in-use result), and the common reason code `cameras-busy`.
  Each module report of skellycam has the schema `skellycertify.report/1.3.0`.
- **[cap x.y]** is a section of [`windows-capture.md`](windows-capture.md). **[rec x.y]** is a section
  of [`recorder.md`](recorder.md). **[P §n]** is section n of `research/NATIVE_JPEG_CAPTURE_PLAN.md`.
- **[ux x.y]** is section x.y of `specs/unix-capture.md`, draft 2 of 2026-11-20, on branch
  `dom/unix-capture-spec` (commit `d08de113a`). It is under review and can change. Section 18 answers
  its section 4.6.4 and lists each other difference.
- **[U]** marks a decision of the user
  ([ADR-GVC0](../decisions/entries/GVC0-certify-decisions-of-the-user.md),
  [ADR-KG00](../decisions/entries/KG00-certify-decisions-of-the-user-on-draft-2.md)). **[A]** marks a
  choice of the agent ([ADR-KY81](../decisions/entries/KY81-certify-spec-choices-of-the-agent.md),
  [ADR-8CP7](../decisions/entries/8CP7-certify-spec-draft-3-choices-of-the-agent.md)). Draft 3 changes
  [A] to [U] where the user accepted a choice of draft 2.
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
certify tests native capture only. OpenCV needs no test, and certify has no check of the OpenCV
source [U].

Each check answers one part of the start question. A check that cannot judge (a camera with no 1080p
mode, a dark room) says so with `not-run` or `record-only` and a reason. It never gives `fail` for a
feature that the camera does not have [A].

Scope:

- skellycam gives the two Python functions `skellycam.certify(level, progress=None, cancel=None, *,
  cameras=None, recording_folder=None, test_media_dir=None)` and `skellycam.certify_plan(level, *,
  cameras=None, recording_folder=None, test_media_dir=None)` [C 2.1, C 2.8]. The HTTP routes that start a run in the app stay in freemocap [U].
- The levels `quick` and `full` [C 2.7].
- The product path on all three systems: Media Foundation on Windows, and the native V4L2 (Linux) and
  AVFoundation (macOS) sources, which the user decided to build now [U]. On Linux and macOS, certify
  validates the assumptions of those sources (section 10).
- The known systems and cameras, and the flow from a report to the next release: section 11.
- The record of the camera models that are checked on this system, and the check of a new model when
  the person first opens it: section 2.5 [U].

## 2. The run

### 2.1 Processes [A]

| Process | What it does | What it must not do |
|---|---|---|
| Caller process: `certify()` | The plan, the progress, the cancel, the time limits, the report, the privacy scrub. | Import `comtypes`, load a camera driver, open a camera. |
| Detection child | The native detection of the product (`detect_media_foundation_cameras()` on Windows, which has its own child, cap 7.1; the V4L2 and AVFoundation detection of the new sources). | Stay alive after its limit. |
| Session child | One `CameraGroupManager` of the product with the native source (or fake sources for a self-check). Its camera processes are its children [cap 6.6]. | Run HTTP. It never opens a port, and never port 53117. |
| Probe child | A probe of section 10.4: a fact that the product path cannot see. Record-only. A camera probe (10.7) opens one camera, with the product session closed for that camera. | Open a camera that hung or is dead; claim, detach or seize a device; write outside the work folder. |

The caller also reads and writes the record of checked camera models (2.5) in the local certify store
of skellycam. It opens no camera for this.

- Each child starts with the `spawn` method of `multiprocessing` [C 2.5].
- Certify always uses the native source. The settings `SKELLYCAM_WINDOWS_CAPTURE` (cap 14.2),
  `SKELLYCAM_LINUX_CAPTURE` and `SKELLYCAM_MACOS_CAPTURE` [ux 4.9] do not change it [U: native only].
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
| Source facts | The `diagnostics` dict in the camera status, with the keys of [ux 4.6.2] (section 10.3) |
| The controls before the run, and their restore | The product: the source keeps the "before" values at its first control read (`c_before`, `c_before_auto`) and sets them back at its own close [U] [ux 4.7] |
| A plain open (phase G of `full`), the cycles | `MediaFoundationSource.open`, `set_controls`, `close` in the session child |
| Disk | `start_take`, `CameraTakeWriter`, `finish` with synthetic JPEG frames; `folder_files.file_system` |

The certify code adds no other capture path. On Linux and macOS the same calls go to the native V4L2
and AVFoundation sources. A test checks this (T-CERT-32).

### 2.3 Order of a run [U, A]

The user decided: "Do the stuff that's likely to break the cameras at the end of the run. Ensure
anything that gets broken during a run is fixed or flagged to the user" [U]. He also decided the order
inside the full run: camera identity, modes and frame rates first; long sweeps next; checks that can
break a camera last [U]. The product restores the "before" values of each camera at its own close
[U]. Thus a run has these phases, in this order:

| Phase | Level | Content |
|---|---|---|
| A. Start | both | Plan facts; the record of checked models (2.5); detection. No separate open: the first open of each camera gives its "before" values through the diagnostics (`c_before`, `c_before_auto`). Certify keeps these first values for phase G. |
| B. Quick | both | The checks of section 4. |
| C. Identity, modes, rates | full | One camera at a time: `<label>:identity`, `<label>:modes`, `<label>:controls` (the list), and the 30 fps rate checks of 5.2. On macOS also the safe JPEG probes of 10.7 (steps 1 to 3). |
| D. Long sweeps | full | One camera at a time: the exposure sweep at `<base>`, SkellyCam Auto, the control sets of 5.4, `<label>:auto-off` (10.2). On macOS also the safe probes of 10.7 (steps 4 to 6). |
| E. Group, system, self-checks | full; quick: `self:hang-100ms` only [U] | Section 6: the group take at 30 fps, the contention, the disk check, the disk benchmark, the system facts. Section 7: the self-checks. They use fake cameras and do not touch a real camera. |
| F. Risky checks | full | Section 8, in order of rising risk: the in-use check, the 60 fps modes, the sweeps and the Auto search at 60, the group take at 60 fps, the open and close cycles, and on macOS the endpoint-0 and device-open probes of 10.7 (steps 7 to 9), last. |
| G. Re-check | both | Section 8.3. Quick: the state of each camera comes from the restore of its last close. Full: a plain open of each camera that did not hang. The phase runs also after a cancel or a crash of an earlier phase. |
| H. Cleanup and record | both | Section 9.5; the record of checked models (2.5). Then the report. |

The user accepts a full run of skellycam of 6 to 11 minutes [U]. Section 16 gives the estimates.

A camera that hung, crashed its camera process or was removed is never opened again in that run
[U: the Kiyo Pro wedge rule, cap 8.2]. Its later checks are `not-run` with `prior-failure`, and phase G
gives it the state `replug` (8.3).

### 2.4 Package options [A]

| Option | Default | Meaning |
|---|---|---|
| `cameras` | `None` (each real camera) | A list of labels of section 3.1. Only these cameras are checked. A run of a part of the cameras is complete for each camera that it checks, so it is not `partial-run`. |
| `test_media_dir` | `None` | The shared test media folder of the app [C 2.8]. Both functions accept it. skellycam needs no test media: the full level makes its synthetic frames. Thus skellycam reads and writes nothing in this folder [A]. The disk checks write in the work folder inside `recording_folder`, because the user decided that the benchmark runs in the recording folder [U]. |
| `recording_folder` | `None` (the temporary folder of the system) | The folder where the person records. The app passes its data folder. The quick take, the disk check and the disk benchmark write in a new work folder inside it, and certify deletes it (9.5). No path is in the report. |

The record of checked models (2.5) does not change which cameras `certify()` checks. Without the
option `cameras`, a run checks each detected real camera, also a camera of a model that is already
checked [A].

### 2.5 Checked camera models [U, A]

The user decided [U]:

- A camera counts as checked one time for each model on this system. The model is the USB vendor id
  and product id. A second camera of the same model, or a camera that is unplugged and plugged in
  again, is not checked again.
- The app checks an unchecked model when the person first asks the app to open it. freemocap then
  shows a pop-up and runs the check (about 30 s). Plugging in a camera alone starts nothing.
- With no camera detected, the camera rows read "not checked", and nothing fails.
- skellycam keeps the record of checked models with its other local certify records.
  `certify_plan("quick")` returns, for the detected cameras, the models that are still unchecked.
  freemocap keeps no record.

The details [A]:

- **The store.** One file for the checked models and the local pass of 11.3: `camera_checks.json`
  in the skellycam base folder (`get_default_skellycam_base_folder_path()`), the file and format of
  [ux 4.9] [A]. The local certify reports are in the same folder. The contract allows a package to
  record its own results in its own store [C 2.5]. This file is not in the work folder, and certify
  never deletes it.
- **The key.** The USB id `vvvv:pppp`, the backend (3.1), the ABI and the OS key of 11.2. A new OS key (for
  example a new Windows feature version, macOS major version or Linux kernel minor version) makes
  each model unchecked again. A camera with no USB ids is keyed by `nousb` and its cleaned name (9.4). A row of each level is
  kept: a `quick` row marks the model as checked; a `full` row is also the local pass of 11.3.
- **A row.** The fields of [ux 4.9]: `device`, `backend`, `os_key`, `abi`, `level`, `result` (the
  summary item of the model, 3.3), `skellycam` (the version) and `date` (the UTC day). For a camera
  with no USB ids, `device` is `nousb:<cleaned name>`. A row holds no serial number, no path and no
  `camera_id`. A newer row for the same key and level replaces the older one.
- **When a model counts as checked.** At the end of a run (also after a cancel), certify writes one
  row for each model whose summary item ended `pass`, `partial` or `fail`. An item `skipped` (busy)
  or `record-only` (cancelled, time budget, no access) writes nothing, so the app checks that model
  again at its next open. The row holds the result of the summary item of the model (3.3).
- **A failed model.** The app does not check it again at each open. The person can run certify from
  the certify page of the app at any time.
- **A damaged store.** A file that does not parse, or a row with a missing field, counts as no row.
  Certify then writes a new file. It never raises for the store.
- **The plan.** `certify_plan("quick")` and `certify_plan("full")` give `details.cameras[].checked`
  for each detected camera and `details.unchecked`: one item `{label, name, device}` for each
  unchecked model, with the label of the first camera of that model (9.1).
- **The pop-up flow of freemocap.** freemocap closes its camera groups [U], then calls
  `certify("quick", cameras=[<labels of details.unchecked>])`, then opens the cameras. A run of a part
  of the cameras is complete for each camera that it checks (2.4), so the report can count as a local
  quick pass [C 7.2].
- **No camera.** `detect` passes with `cameras` 0. Each check that needs a camera is `not-run` with
  `no-camera`. No check is `fail`. The summary has no `camera` item, so the camera part of the report
  reads `Cameras: not checked on this system.` [C 3.7, C 4.2 part 6] (3.3). Certify writes no row to
  the store.

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
| `<label>` | The camera row of one unit (3.3). The summary item of its model comes from the rows of its units. |
| `<model>:units` | `<model>` is `cam.<backend>.<vid>-<pid>`: the count of units of the model (3.3). |
| `<label>:<claim>` | A claim check of 3.3: `opens`, `rate`, `settings-stick`, `native-jpeg`, `records`. |
| `<label>:<check>[:<mode>]` | Another check of the camera. `<mode>` is `<w>x<h>@<rate>`, with the rate rounded as cap 7.3 rounds it: `1280x720@30`, `1920x1080@30`, `1280x720@60`, `640x480@29.97`. |
| `detect` | The detection. |
| `group:<check>`, `system:<check>` | A check of the cameras together; a fact or a check of the system. |
| `self:<check>` | A self-check with fake cameras (section 7). It is never a camera row [U]. |
| `probe:<check>`, `probe:<model>:<approach>` | A probe of 10.4: record-only, code of certify, outside the product path. |
| `<name>:exit` | The `exit` check of the contract [C 2.5]. |
| cleanup `release:<label>` | Phase G: a camera that is not healthy after the run (8.3). |

Each name matches `^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$` [C 3.4]. The longest form,
`cam.media-foundation.nousb-nousb.9:exposure:1920x1080@29.97`, has 59 characters. The report has no
sections: the "Failed checks" table then shows each failed check, with its `module` [C 4.2 part 7].

`module` [C 3.4] [A]: each camera check has the `name` of the summary item of its model. The checks
`system:disk` and `system:disk-benchmark` have `Disk`. The other checks have no `module`.

### 3.2 Numbers [A]

`numbers` is flat [C 3.4]: a number, a boolean, `null`, a reason code, a list of reason codes, or a
string from a fixed vocabulary of `skellycam/REASON_CODES.md`. A list of numbers is not allowed. Thus
a sweep gives one key for each step, for example `fps_at_m7` for exposure -7 (`m` for minus).

### 3.3 The camera row, the claims, the summary item [U, C 3.7]

The user asked: "Quick test must include applying settings and if they stick or not, can you jpegs
... This might necessitate a "partial" result in the summary table." [U] He accepted the result
`partial`, and the meaning of "can you jpegs": the camera's own JPEG frames, passed through unchanged
in the capture path of the product (MJPG passthrough, no decode and no re-encode) [U]. He first asked
for "in use" as a status of its own. In the session of the contract he then said: "in-use shouldn't
be it's own status here just for cameras. skipped (busy) will do for both" [U, as the contract
reports it]. Format 1.3.0 has the summary results `pass`, `fail`, `record-only`, `partial` and
`skipped`, and `skipped` needs the reason `busy` or `reviewed` [C 3.7].

**The five claims.** Each real camera has five claim checks. Each is `pass`, `fail`, `not-run` or
`record-only`, with a reason code:

| Claim check | Claim | Section |
|---|---|---|
| `<label>:opens` | The camera opens at `<base>` and reaches `ready`. | 4.2 |
| `<label>:rate` | It holds the mode rate at `<base>` (the product rate check). | 4.2 |
| `<label>:settings-stick` | Each control that the product sets reads back the set value, still reads it 1 s later, and changes the image. | 4.3 |
| `<label>:native-jpeg` | It gives its own JPEG frames, passed through unchanged. | 4.4 |
| `<label>:records` | It records a take with good files. | 4.5 |

`<base>` is `1280x720@30`. A camera with no 1280x720 MJPG mode at the floor uses the largest MJPG
size below 1280x720 in area that has a rate at the floor, for example `640x480@30` [A].

**The row of a camera.** The check `<label>` holds the row of one camera (one unit). Its `result` is
a check result [C 3.4], and `numbers.row` holds the row value. The first rule that applies gives the
row [A]:

| Order | Row (`numbers.row`) | Check result | Rule |
|---|---|---|---|
| 1 | `skipped-busy` | `not-run`, reason `camera-in-use` | `opens` is `not-run` with `camera-in-use`: another program holds the camera. |
| 2 | `fail` | `fail` | `opens`, `rate` or `records` is `fail`. |
| 3 | `record-only` | `record-only` | `opens` is `record-only` or `not-run` for another reason (no access, cancelled, time budget, prior failure): nothing judged the camera. |
| 4 | `pass` | `pass` | Each of the five claims passes. |
| 5 | `partial` | `record-only`, reason `partial` | `opens` passed, and another claim did not pass: `settings-stick` or `native-jpeg` failed, or a claim could not run or judge (for example `too-dark`, or USB bandwidth also alone). This is the `partial` of [C 3.7]: "some checks of the item passed. Other checks could not run, or failed in a way that is not fatal." |

A declared mode of `full` that does not deliver never changes the row: it is a `fail` of that mode
check, and the row stays at its base result [U].

**The summary item of a model** [C 3.7]. The summary has one `camera` item for each camera model on
the system (the USB vendor id and product id), not for each unit. `name` is the cleaned name (9.4,
1 to 80 characters), `device` is `vvvv:pppp` (`null` with no USB ids). The rows of the units of the
model give the item [A]:

1. Each unit is `skipped-busy`: the item is `skipped` with the reason `busy`.
2. Else, take the units that are not `skipped-busy`. Any `fail` gives `fail`.
3. Else, when the rows are all `pass` and no unit is `skipped-busy`: `pass`.
4. Else, when the rows are all `record-only` and no unit is `skipped-busy`: `record-only`.
5. Else `partial` (for example one unit `pass` and one `skipped-busy`, or `pass` and `record-only`).

The check `<model>:units`, with `<model>` = `cam.<backend>.<vid>-<pid>`, is `record-only` and holds
`units`, `units_tested` and `units_busy` [C 3.7: "The count of units can be in `checks`"]. Each check
of a camera has `module` = the `name` of its summary item [C 3.4], so that the table of the failed
checks names the camera [C 4.2 part 7].

- skellycam never gives `skipped` with `reviewed` [A]: a reviewed pass of a model on another system
  says nothing about the USB connection of this system, and the user decided that each model is
  checked one time on each system (2.5).
- A `partial` or `skipped` item never gives a reviewed row [C 7.2] (11.5).
- With no camera detected, the summary has no `camera` item [C 3.7]. The Markdown then shows
  `Cameras: not checked on this system.` [C 4.2 part 6]. This is the "not checked" of the user [U].

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
settings check and the JPEG check [U]. The pop-up check of a new model (2.5) is this quick run for the
cameras of that model.

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

### 4.3 Settings stick [U]

The user accepted this check [U]. The product sets the controls after the first frame and reads them
back (cap 9.1). The check:

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

The take of 4.5 runs at -8. The product puts back the "before" values at the close of the group [U].

### 4.4 Native JPEG [U, A]

The check uses frames that the run already has. It needs no extra time.

| Numbers | Result |
|---|---|
| `format` (`MJPG`, `YUY2`, `NV12`), `frames_checked`, `soi_eoi_ok`, `strict_decode_ok`, `sof_matches_mode`, `encoded_by_skellycam` and `decoded_by_skellycam` (counts; diagnostics D-10), `dht_inserted` (count), `quant_tables_distinct` (count), `bytes_equal_ring_mkv`, `hash_equal_source_ring` | `pass` when the mode format is MJPG, skellycam encoded no frame, each checked frame has SOI and EOI, decodes strictly, has the SOF size of the mode, its MKV block equals its ring slot byte for byte, and the source hash of each of the first 30 frames equals the hash of its ring slot; `fail` with `no-native-jpeg` (an uncompressed mode that skellycam encodes, after 3b), `jpeg-damaged` or `jpeg-size-differs` |

- The frames: 30 frames of the JPEG ring after the rate check, and each block of the take of 4.5.
- A JPEG with no DHT gets the standard table from the capture check (`DHT_INSERTED`, rec 4.1). That is
  still native. `dht_inserted` records it.
- The shared loop hashes the bytes that it gives to the ring and the recorder, after a DHT insertion,
  for the first 30 frames after each move to `ready` and after each record start (`sha256_00` to
  `sha256_29`, `sha256_frame_00` to `sha256_frame_29`, `sha256_trigger`, [ux 4.6.2] D-11). Certify
  compares each hash with the ring slot and the MKV block of the same `source_frame_number`
  [ux 4.6.4].
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
| One apply of all cameras (5.8 s for 3 [M]) | 6 + 0.25 per camera [NV] |
| Settings check (one live change, cap 10.2) | 3 |
| Take: start, 3 s, stop, `finish` | 5 |
| File checks, JPEG check, deletion | 1.5 |
| Close of the group (0.27 to 1.18 s per camera, in parallel [M]) | 1.5 |
| Phase G: the state of each camera from its last close | 0 |
| `self:hang-100ms` [U] | 10 |
| Each retry alone (4.2) | 6 |

The product reads the "before" values at the first open and restores them at each close [U]. Thus
phase A needs no separate open, and phase G of quick needs no open. Sum with no retry and with the hang
self-check: `30 + N/4` s, so about 31 s for one camera, 31 s for four cameras and 32 s for eight
cameras. This is near the target of 30 s for four cameras; the user decided that the hang self-check
stays in quick [U]. `certify_plan("quick")` gives `seconds_estimate = 30 + N/4`, rounded up. Each retry
alone adds 6 s; the plan cannot know the retries, so it does not count them. The pop-up check of one new model (2.5) is about 31 s.

## 5. Level `full`: safe checks of each camera (phases C and D)

### 5.1 Selection rule [A]

A full run cannot test each mode of each camera. The C930e declares 17 MJPG sizes
[M `research/usb_cameras/docs/hardware_run_3a_20261120.md`]. For each camera whose `opens` and `rate`
passed, the run selects:

1. `<base>` (from quick; no new open).
2. Phase C: `identity`, `modes`, `controls` (the list); `1920x1080@30`, when the camera declares it;
   the largest MJPG size at the floor, when it is larger than 1920x1080, once, at 30. After step 3b:
   one uncompressed mode (YUY2, else NV12) at 30 at the largest size that has it. Before 3b:
   `not-run` with `not-built`.
3. Phase D: the exposure sweep at `<base>`; SkellyCam Auto; the control sets; the timestamps come
   later from `group:take-30` of phase E.
4. Phase F: the in-use check; each size that declares 60, at most two (1280x720 first, then the
   largest other size), with the sweep and the Auto search at the first one; five open and close
   cycles.

One camera of each model [A, question 4]: the camera blocks of phases C, D and F run for the first
camera of each model (USB id and backend) only. Each other camera of that model has its quick claims,
takes part in the group checks, and gets `not-run` with `same-model` for the camera block checks. This
follows the rule that a model is checked one time on a system [U] (2.5), and it keeps a full run with
two cameras of one model near the time of one camera.

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

The exposure rule of the product, which the certify checks must match [U]:

- The exposure modes are Manual and Auto.
- "Auto" always means that SkellyCam finds a manual value by a one-shot search.
- A camera in Auto searches at every open, and when the person changes the frame rate.
- The camera's own auto exposure is never a mode. No certify check turns it on as a mode.
- The text for a slow camera is "Camera is slow. Try adding more light".
- Nothing below 30 fps is offered.

| Check | Phase | How | Numbers | Result |
|---|---|---|---|---|
| `<label>:auto-exposure` | D | An apply at `<base>` with SkellyCam Auto (cap 11.1: -12 to -5, offset -1; [ux 4.5] items 5 to 8). Certify waits while the state is `adjusting` (at most 15 s), then reads `exposure_found` from the status [ux 4.6.4]. `searches` counts the moves into `adjusting`. | `found` (`exposure_found`), `at_range_end`, `searches`, `luma_mean`, `measured_fps` | `pass` when one search ran at the open and the found value passes the rate check; `record-only` with `too-dark` when `at_range_end` and `luma_mean < 64` [A, not calibrated], or when the check fails with `luma_mean < DARK_LUMA`; `fail` with `auto-not-searched` when no search ran, else with `rate-low` |
| `<label>:auto-exposure:<w>x<h>@60` | F | After `<label>:rate:<w>x<h>@60`: an apply in Auto at `<base>`, then a live apply that changes only the frame rate to 60 at the first 60 mode [A]. | `searches_at_open`, `searches_after_rate_change`, `found_at_30`, `found_at_60`, `luma_mean`, `measured_fps` | `pass` when the rate change started one new search and its found value passes the 60 rate check; `fail` with `auto-not-searched`, or with `rate-low`; `record-only` with `too-dark`; `not-run` with `no-mode` |

No product source sets the camera's own auto exposure [ux 4.5 item 1]. A macOS camera with no
manual exposure has no Manual and no Auto in native capture; it opens with the warning
`no-manual-exposure` [ux 4.5 item 12]. Only the probe A9 of 10.7 runs the camera's own auto, as a
probe and never as a mode.

### 5.4 Controls

| Check | How | Numbers | Result |
|---|---|---|---|
| `<label>:controls` | Phase C. The diagnostics D-4 and the status (cap 8.4, 11.4): which controls exist, their ranges, and the unit map. One check on the three systems: the rule is in 10.2. | as 10.2 | as 10.2 |
| `<label>:control:gain` | After 3c: set the minimum and the default, manual; read back. | `set_ok`, `readback`, `rate_ok` | `pass`; `fail` with `readback-differs` or `control-failed`; `not-run` with `control-absent` or `not-built` |
| `<label>:control:focus` | After 3c: manual focus at two values; read back; the sharpness (variance of a Laplacian of the 1/8 frame). | `set_ok`, `readback`, `sharpness_a`, `sharpness_b`, `luma_mean` | `pass` on read-back; sharpness record-only; `not-run` with `control-absent` or `not-built` |
| `<label>:control:autofocus` | After 3c: auto focus on, then off at the value that it reported; read back. | `reported`, `readback` | `record-only` (M-CAP-7 is open) |
| `<label>:control:white-balance`, `<label>:control:power-line` | After 3c: read only (cap 11.5). | `value`, `auto` | `record-only`; `not-run` with `control-absent` |

### 5.5 Start-up times and timestamps

| Check | How | Numbers | Result |
|---|---|---|---|
| `<label>:timings` | The times of each open of the run, from the diagnostics D-6. One check on the three systems (10.2). | `open_ms_p50`, `open_ms_max`, `first_frame_ms_max`, `ready_s_p50`, `close_ms_max` | `record-only` |
| `<label>:timestamps` | The CSV of this camera in `group:take-30` (6.1), 30 s. | as `<label>:records`, and `period_ms`, `drift_ppm_against_first` | `record-only` |

## 6. Level `full`: cameras together and the system (phase E)

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
| `system:usb` | After the USB label is ported (section 13): the link of each camera, from `CameraDeviceInfo.usb_link` and the diagnostics D-9 (`usb_link`, `usb_alt`) [ux 4.2 item 6, 4.6.2]. | counts `usb3`, `usb2`, `usb1`, `unknown`; `usb_link` and `usb_alt` in `<label>:detect` | `record-only`; `not-run` with `not-built` before the port |
| `system:kernel` | Linux: the kernel facts from the diagnostics (`kernel`, `driver`, `nodrop_param`, `clock_param`) [ux 4.6.2], and which `uvcvideo` quirks are expected: the Kiyo Pro `NO_LPM` quirk (7.0, and the stable 6.12.81, 6.18.34, 6.19.12), the C922 SOF quirk (6.11), `nodrop` (6.14). | `kernel_major`, `kernel_minor`, `nodrop_param`, `clock_param`, `quirk_kiyo_pro_no_lpm`, `quirk_c922_sof` | `record-only`; `not-run` with `not-linux` on Windows and macOS |
| `system:disk` | The product recorder with synthetic JPEG frames (rec 11) in the work folder: N camera writers, N = the count of cameras that passed, each at the size and the mean JPEG size of its camera at its largest passed 30 fps mode, 20 s. | `file_system`, `free_gb`, `cameras`, `need_mb_per_s`, `give_waits`, `give_wait_ms_max`, `queue_high_water_s`, `threshold_give_wait_ms` (500) | `pass` when no `give` waits longer than 500 ms [A, not calibrated] and no stall; `fail` with `disk-slow`, `disk-stall`, `fat-disk` |
| `system:disk-benchmark` | Section 6.3. | `write_mb_per_s`, `block_ms_p99`, `fsync_ms_max`, `bytes`, `seconds`, `cameras_1080p30_typical`, `cameras_1080p30_worst` | `record-only` |
| `system:camera-apps` | Windows: a fixed allow-list of process names of programs that hold or change cameras, for example LogiTune and Razer Synapse [M `research/usb_cameras/docs/windows_results_20261113.md` §0]. | one boolean for each item of the list | `record-only` |
| `system:virtual-cameras` | The count from detection. | `count` | `record-only` |

### 6.3 The disk benchmark [U]

The user asked: "ensure a disk performance benchmark is run to get a MB/s figure as well as the "disk
is fast enough" test when running the full suite." [U] He accepted this benchmark in full: 1 GiB, 4 MiB
blocks, fsync each second, at most 30 s, in the recording folder, deleted after, MB/s reported [U].

- The folder: a new file in the work folder inside `recording_folder` (2.4). No path is in the report.
- Before the write: when the free space is less than 3 times the file size, the benchmark is `not-run`
  with `disk-full`.
- The write: one file of 1 GiB [U, not calibrated], in blocks of 4 MiB, through an unbuffered file
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
| `<label>:auto-exposure:<w>x<h>@60` | The Auto search after a change of the frame rate (5.3), at the first 60 mode. | as 5.3 | as 5.3 |
| `group:take-60` | Each camera whose 60 mode passed, at 60, with the exposure that held 60 for it, a take of 15 s. Needs two cameras. | as `group:take` | 4.5 rules; `not-run` with `one-camera` or `no-mode` |
| `<label>:cycles` | Five cycles of the product source `open` (on Windows `MediaFoundationSource.open`) at `<base>` (to the first frame) and `close`. | `cycles`, `ok`, `open_ms_max`, `first_frame_ms_max`, `close_ms_max`, `stage` | `pass`; `fail` with `hung` or `first-frame-timeout` at the first fault, and no more opens of that camera |

A declared 60 mode that never delivers 60 fails its mode check, and the camera row stays at its base result [U]. Measured: the Kiyo Pro
declares 60 at each of its 4 sizes and delivered 29.7 to 30.4 fps at each exposure from -7 to -10; the
C922 delivered 60 at 1280x720 only at -7, 29.7 fps at -8 to -10, and 56.5 fps at -6
[M `research/usb_cameras/docs/free_run_log_20261120.md` §9]. The product offers 60 only when each
ticked camera passed a real 60 fps check [U]. Certify reports at which exposures 60 held.

The C922 at 60 with the Kiyo Pro open gave 46.5 fps over frames 6 to 90, then 58.7 fps over 10 s
[M same file]. Thus `group:take-60` can find `rate-under-contention` where each camera alone passes.

### 8.3 Phase G: re-check [U, A]

The user decided: "Ensure anything that gets broken during a run is fixed or flagged to the user "e.g.
camera <camera name> wedged, please replug"" [U]. He also decided that the product restores the
"before" values of each camera at its own close [U]. Thus:

1. The product keeps the "before" values of each control at the first control read of each open, and
   sets them back at each close, with a read-back [ux 4.7]. The diagnostics carry the values
   (`c_before`, `c_before_auto`) and the result of the restore (`restore_ok`,
   `restore_failed`; section 18.2 item 4). This holds on the three systems.
2. Certify keeps the "before" values of the first open of each camera in the run. A later open that
   reports other "before" values shows that an earlier restore did not hold.
3. Quick: phase G opens no camera. The state of each camera comes from the restore of the last close
   of the group and from the "before" values of its opens.
4. Full: phase G opens each camera that did not hang (a plain open of the product source, to the first
   frame). The open is bounded (cap 6.6). It reads the controls; when a value differs from the first
   "before" value, it sets that value, reads it back, and closes. A camera that hung earlier is not
   opened again [U].
5. Each camera gets one after-run state:

| State | Meaning | Where the report holds it |
|---|---|---|
| `healthy` | Each close worked, and each control has its first "before" value. | No cleanup row. |
| `restored` | A control differed from its first "before" value, and phase G of `full` set it back with a good read-back. | No cleanup row. |
| `not-restored` | A control does not have its first "before" value at the end of the run. | Cleanup row `release:<label>`, `fail`, reason `camera-not-restored`. |
| `replug` | The camera hung during the run, its camera process ended, or the plain open of phase G failed. | Cleanup row `release:<label>`, `fail`, reason `camera-wedged`. |

The phase also runs after a cancel or a crash of an earlier phase, with its own limit of 20 s for each
camera [A].

**How the message reaches the person** [U]. The report format forbids free text in `numbers`, and it
has no field for a message to the person [C 3.4]. The fitting place today is `cleanup`: a list of
check objects for cleanup steps that failed [C 3.1]. Thus:

- skellycam writes the cleanup row `release:<label>` with a fixed reason code. `skellycam/REASON_CODES.md`
  gives each code with one sentence: `camera-wedged`: "The camera stopped answering during the run.
  Unplug it and plug it in again." `camera-not-restored`: "A setting of the camera is not as it was
  before the run. Open the camera in SkellyCam and set it again."
- The app shows each such row as a notice at the end of the run, also when the person does not send
  the report: "Camera <name>: wedged, please replug" [U]. The cleanup row has `module` = the name of
  the summary item of the model [C 3.4], so the app needs no lookup. This is an agreement between
  skellycam and freemocap. It needs no change of the contract.
- skellycam asks the owner of the contract for a list of notices that each package can use: a fixed
  code and named parameters (a minor change) [U]. Format 1.3.0 does not hold it (11.6).
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
folder that can happen. skellycam asks the owner of the contract to name a risk to a device in the
text of `system_changes` [U]. Format 1.3.0 does not hold it (11.6).

## 9. The plan, cancel, privacy, cleanup

### 9.1 `certify_plan(level)` [A]

It opens no camera and does not activate a device. It uses only the enumeration of cap 6.2 step 1
(`MFEnumDeviceSources` and two attributes), which the research found safe also with a wedged Kiyo Pro
[M `research/usb_cameras/docs/windows_results_20261110.md` §13]. It loads `comtypes` only in a child.
On Linux and macOS it uses the native detection, which opens no stream [ux 4.3.1, 4.4.1]. It reads
the record of checked models (2.5) and the evidence file (11.2).

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
  "cameras": [{"label": "cam.media-foundation.046d-085c.0", "name": "Logitech C922", "device": "046d:085c", "evidence": "verified", "checked": false}],
  "unchecked": [{"label": "cam.media-foundation.046d-085c.0", "name": "Logitech C922", "device": "046d:085c"}],
  "system_evidence": "unknown",
  "virtual": 4,
  "checks": ["detect", "cam.media-foundation.046d-085c.0:opens", "..."]
 }
}
```

- `downloads` is empty in both levels: the full level makes its synthetic frames. A later download
  must have `name`, `bytes`, `source` and `sha256`, and certify must check the hash [C 2.6].
- `system_changes` is empty for `quick` (the restore of the product at each close puts back what
  quick changes).
- `questions` holds `camera-ok-after` only for `full`.
- `details.cameras[].evidence` and `details.system_evidence` come from the known-systems file
  (section 11): `verified`, `known-bad` or `unknown`.
- `details.cameras[].checked` and `details.unchecked` come from the record of checked models (2.5)
  [U]. The app uses `details.unchecked` of `certify_plan("quick")` for the pop-up check.

### 9.2 Seconds estimate

Quick: section 4.7. Full: section 16.

### 9.3 Cancel and time limits [A]

- The caller reads `cancel.is_set()` at least two times each second [C 2.4].
- On a cancel or a time-out of a session child, the caller first ends the main process of the child
  only. Its camera processes notice the dead server after 10 s [U], finish their files and release the
  cameras. The caller waits for them at most 12 s, then kills the rest of the tree. Then phase G runs
  for the cameras that did not hang (8.3), and phase H. A cancel then returns in about 13 s plus phase
  G, not in 1 s [U: question 12 of draft 1, "yes"].
- `certify()` returns the finished checks with their results. Each check that did not end is
  `not-run` with `cancelled` [U] [C 2.4].
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

### 9.6 Progress before each step [U, A]

The user decided: the progress callback is called with the name of a check before that check starts
[U]. freemocap writes that name to a file for crash reports. Thus:

- Before each step that runs in a child process or touches a camera, certify calls `progress` with a
  message whose `step` names that check and whose `result` for it is `null` [C 2.3]. Certify starts
  the step only after `progress` returns.
- A check that only computes from facts that the run already has (for example a claim check from the
  numbers of earlier steps) gives no message of its own [A]. It cannot crash the process.
- The contract allows at most 10 messages each second [C 2.3]. When a step would start less than
  100 ms after the last message, certify waits until 100 ms have passed [A]. It never drops a
  message before a step.
- If `progress` raises, certify stops calling it and continues the run [C 2.3].

### 9.7 Cameras busy [U, A, C 2.5]

The app must close its own camera groups before a certify run [U]. When certify finds a camera group
of skellycam open in the calling process (the app state of the skellycam server), it cannot get the
cameras, so it refuses the run [C 2.5 "Cameras in use"]. It opens no camera. It returns the report
with each camera check `not-run` with the common code `cameras-busy`, and `evidence.reasons` holds
`cameras-busy` [C 5.3]. The other checks also do not run: they are `not-run` with `cameras-busy` [A].

One camera that another program holds, while the other cameras work, is not a refused run [C 2.5].
Its checks are `not-run` with `camera-in-use`, and its summary item is `skipped` with `busy` when
each unit of its model is held (3.3). A camera that a skellycam server in another process holds is
such a camera [A].

### 9.8 Interrupted run [C 2.5, A]

The app or the process of certify can end before the run ends. The report is then written later from
the checks that finished [C 2.5 "Interrupted run"]: the check that ran when the process ended is
`fail` with `crashed`, each other check that did not end is `not-run` with `interrupted`, and
`evidence.reasons` holds `interrupted`.

- freemocap writes each progress message to a file for crash reports [U] (9.6). Thus skellycam puts
  into each item of `checks` of a progress message, after the check ended, also its `reason`, its
  `module` and its `numbers` [A, question 5]. The message then holds each fact that the report needs
  for that check.
- freemocap writes the interrupted module report from the last message: the `step` of that message is
  the check that ran. skellycam gives no other function for this [A].
- The record of checked models gets no row from an interrupted run [A].

## 10. Linux and macOS: certify validates the assumptions of the new native sources

### 10.1 The decision and the state

The user decided: "certify runs to validate assumptions about linux and mac code. Ideally as much real
code is implemented as possible now so a single test run provides as much information as possible and
can be used there and then if the tests pass." [U]

Thus:

- The real native sources for Linux (V4L2 through `ctypes`) and macOS (AVFoundation through PyObjC,
  controls through CoreMediaIO feature controls) are built in the product now. Phase 7 moves up. The
  spec of the sources is [ux] [U]. UVC requests on endpoint 0 run only as a certify check in phase F
  (the probes of 10.7) [ux 4.4.10] [U].
- They are written from what we know and assume: the research suites of
  `research/usb_cameras/suite/linux/` and `suite/macos/` with their runbooks, and the cross-platform
  plan (`research/usb_cameras/docs/xplat_capture_plan.md` §2.5, §2.6). Neither suite has run on
  hardware [P §7].
- Certify tests the product path on all three systems. On Linux and macOS, each assumption of a source
  is a named check whose numbers show **how** it failed, not only that it failed. One run must tell
  which assumption broke [U].
- When a system passes a full run, native capture can be used there at once [U] (11.3).
- The Windows hardware tests T-CAP-92 to T-CAP-98 were planned for Linux and macOS through the OpenCV
  source. With "no OpenCV checks" [U], the checks of this section replace them. Hot-unplug (T-CAP-95)
  is not tested [U].

### 10.2 The assumptions as checks

Each check is a camera check `<label>:<name>` or a group or system check. Each check runs when the
camera opens, also when another assumption check of that camera failed: a failed `native-jpeg` does
not stop `clock`, `sequence` or `controls` [A]. Only a failed `opens` stops the others. "D-n" is a
requirement of 10.3. "W" means that the same check also runs on Windows. Each number that comes
straight from the diagnostics has the name of its diagnostics key in [ux 4.6.2] (draft 2) [A]; a
number that certify computes has its own name.

| Check | Assumption of the source | Numbers (how it failed) | Pass rule | Notes and sources | D |
|---|---|---|---|---|---|
| `<label>:native-jpeg` (claim, W) | Linux: the camera gives its own MJPG bytes through `VIDIOC_DQBUF` on mmap buffers, with no re-encode. macOS: AVFoundation hands over the camera's JPEG in a block buffer (`'dmb1'`), not only decoded pixels. | `requested_fourcc`, `granted_fourcc`, `granted_w`, `granted_h` (`S_FMT` picks the nearest size with no error), `delivered` (`jpeg`, `decoded`, `none`), `video_settings` (macOS: `nil`, `empty`, `dmb1`, `null`), `bytesused_equals_payload`, `error_flag_frames`, `zero_bytes`, `dqt_sha256`, the numbers of 4.4 | 4.4 | xplat §2.5 item 1, §2.6 G-MJPEG; L-MJPEG, M-MJPEG. One third-party run on macOS saw MJPEG only as decoded `420v`. On macOS the probes of 10.7 try each other way. | D-1, D-3, D-10, D-11 |
| `<label>:clock` (W) | The driver time of a frame is on the clock of `arrival_ns` (Linux `CLOCK_MONOTONIC`, the clock of `perf_counter_ns`; macOS host time), before the arrival, and near it. | `clock` (`monotonic`, `realtime`, `host`, `device`, `unknown`), `tstamp_src` (`soe`, `eof`, `unknown`), `ts_conversion`, `sample_minus_arrival_p5_ms`, `sample_minus_arrival_p50_ms`, `sample_minus_arrival_p95_ms`, `later_than_arrival`, `grain_ms` and `jitter_p95_ms` (certify computes them from `frame_log`), `sample_time_kept` | `pass` when the clock is the arrival clock, `later_than_arrival` is 0, and p95 is within 200 ms (cap 4.2); `fail` with `clock-base-differs`, `sample-after-arrival` or `sample-too-early` | Linux: the buffer time is taken at the first payload, in steps of URB completions (up to about 4 ms). macOS: Apple documents only the `synchronizationClock`. Windows: arrival minus sample 0.33 ms (Logitech) and 32 ms (Kiyo Pro) [M hardware_run_3a]. | D-2 |
| `<label>:sequence` (W where the driver gives a count) | The driver sequence number counts each frame that the camera sent, so that a drop shows as a gap. | `sequence_available`, `sequence_gaps`, `sequence_lost`, `long_intervals` (over 1.5 periods, from `frame_log`), `gaps_explain_intervals` (long intervals that have a sequence gap, from `frame_log`), `discontinuity_flags`, `drops_reported` | `pass` when each long interval has a sequence gap; `fail` with `sequence-unreliable`; `not-run` with `no-sequence` when the driver gives none | Linux `v4l2_buffer.sequence`; macOS `CMIOSampleBufferGetSequenceNumber`. Windows: a dropped C930e frame showed only as a 64 ms gap and the discontinuity flag [M free_run_log §2]. | D-3 |
| `<label>:controls` (W, phase C) | The source lists each control with its native unit and range, and maps the skellycam exposure unit (log2 s) to it. | for each control `c` of exposure, gain, focus, white balance, power line: `c_present`, `c_min`, `c_max`, `c_step`, `c_default`, `c_auto_supported`; `exposure_unit` (`log2-s`, `100us`, `seconds`, `none`), `exposure_native_at_m7` (Linux: 78 expected), `control_path` (`v4l2`, `cmio`, `avf-lock`, `ep0`, `iam`, `ks`, `none`) | `pass` when -7 maps to the expected native value within one step; `fail` with `unit-mapping`; the ranges are record-only; `not-run` with `no-manual-exposure` for a macOS camera with no manual exposure [ux 4.5 item 12] | Linux: `exposure_time_absolute` in 100 µs. macOS: the CoreMediaIO exposure feature control with an absolute value in seconds in the product [ux 4.4.6, 4.4.10]; each other way is a probe of 10.7. | D-4 |
| `<label>:auto-off` (phase D) | Auto exposure and auto focus can be turned off, and they stay off. | `ae_off_ok`, `af_off_ok`, `ae_back_on_after_s` (`null` when it stays off) | `pass`; `fail` with `auto-not-off` or `auto-came-back`; `not-run` with `control-absent` | xplat §2.6 G-CTRL. White balance is read only [cap D43], and the source never sets an absolute value in auto (A-17) [ux 4.6.4]. | D-4 |
| `<label>:settings-stick` (claim, W) | A set value reads back, stays, and changes the image. At each later open, the product sets the config value again, and it reads back. | the numbers of 4.3; in `full` also `readback_each_open_ok` | 4.3; in `full`, `fail` also with `setting-lost-on-reopen`; `fail` with `no-manual-exposure` for a macOS camera with no manual exposure: the camera opens with the warning, and its item is `partial` [ux 4.5 item 12, 4.6.4] | With the restore at each close [U], a value is not expected to stay after a close. Linux 6.16 and later: an idle camera can autosuspend and lose its controls; the product sets them at each open. The read-back can be cached, so the image decides. | D-4 |
| `<label>:modes` (W, phase C) | The listed modes are the modes that the camera delivers. | `declared`, `opened`, `granted_equals_request`, `delivered_within_3pct` (counts over the modes that the run opened), `format_changes`, `modes_listed`, `mjpg_sizes` | `pass` when each opened mode was granted as requested; `fail` with `mode-not-granted`; the rates are in the rate checks | `S_FMT` changes a size with no error; the Kiyo Pro declares 60 and gives 30. | D-1 |
| `<label>:identity` (W, phase C) | The `camera_id` of the source is stable and unique: the same over two detections, and different for two cameras of one model. | `id_stable`, `id_unique`, `id_source` (`serial`, `id-path`, `unique-id`, `mf-link`), `has_serial` | `pass`; `fail` with `id-unstable` or `id-collision` | Linux: by-id names collide for identical cameras with no serial. macOS: `uniqueID` holds the port. | D-7 |
| `<label>:timings` (W) | Open, first frame and close stay under the limits of cap 6.4 and 6.6. | 5.5, computed from `t_open_ms`, `t_first_frame_ms`, `t_close_ms` and the other `t_*_ms` keys | `record-only` | L-CYC, M-CYC | D-6 |
| `<label>:in-use` (W, phase F) | A camera that another program holds gives a clear in-use failure at a known call. | `outcome` (`refused`, `shared`, `hung`), `fail_code`, `call` and `busy_call` (the call names of [ux 4.6.3]: `open`, `s-fmt`, `reqbufs`, `streamon`, `session-start`, `first-frame`, `querycap`, `s-parm`, `qbuf`, `dqbuf`, `poll`, `streamoff`, `close`, `s-ext-ctrls`, `g-ext-ctrls`, `add-input`, `lock-config`, `stop-running`, `cmio-set`, `cmio-get`, `activate`, `set-mode`, `read-sample`, `flush`, `shutdown`), `native_code` (a number), `native_domain` (`errno`, `hresult`, `nserror`, `osstatus`, `ioreturn`) | 8.2 | Linux: `EBUSY`, but `S_FMT` sends a PROBE to the camera before it. macOS: two programs can share a camera [NV]. | D-5 |
| `group:open` (W) | A USB bandwidth refusal gives a known error. | `refusal_signal` (`error`, `zero-frames`, `low-rate`, `none`), `native_code`, `native_domain`, `call`, the camera that loses | 4.2 | Linux: `ENOSPC` at `STREAMON`, also `ENOMEM`, `EIO`, `EPIPE`, `ETIMEDOUT`. macOS: no documented error. | D-5, D-9 |
| `system:camera-access` | The process can open cameras: Linux through the seat ACL or the `video` group; macOS with the camera permission of the app. | `access` (`seat-acl`, `video-group`, `root`, `none`), `tcc` (`granted`, `denied`, `restricted`, `not-determined`) | `pass`; with no access, each camera is `not-run` with `no-access` or `no-permission`, not `fail` | macOS: a process with no permission gets zero frames and no error. The app asks the camera permission before a run; certify shows no dialog [U]. | D-8 |
| `system:video-effects` (macOS) | No system effect changes the frames. | `center_stage`, `portrait`, `studio_light`, `reactions`, `edge_light` (booleans, `null` when the source cannot read one) | `record-only` | M-FX | D-8 |
| `group:take`, `<label>:records`, the rate checks, the exposure sweep (W) | The rest of the product works on the native source. | sections 4 to 8 | as there | T-CAP-92 to 94, 96 to 98 | — |

The endpoint-0 check of draft 2 (`<label>:control-ep0`) is now the probes A5 to A8 of 10.7, owned and
coded by certify [ux 4.4.10, 4.6.4] [U].

### 10.3 Diagnostics that certify reads [A]

The product path can show only what the source reports. Each source gives `diagnostics() -> dict`,
which the camera status carries [ux 4.2 item 2]. The keys are the keys of [ux 4.6.2], with the IDs
D-1 to D-11 of that table, and the rules of [ux 4.6.1]: fixed keys, `null` when a source cannot fill a
key, no path, no serial, no camera name and no free text. Media Foundation gives the same keys where it
can (parity column of [ux 4.6.2]).

Certify reads these keys. It copies a value into `numbers` only when the value is a number, a boolean,
`null` or a string of the fixed vocabulary of [ux 4.6.2]. It never copies `frame_log` itself: it
computes counts and percentiles from it.

| ID | What certify uses it for |
|---|---|
| D-1 | `native-jpeg`, `modes` |
| D-2 | `clock`, and the timestamp numbers of `records` and `timestamps` |
| D-3 | `sequence`, `native-jpeg` (`error_flags`, `zero_bytes`) |
| D-4 | `controls`, `auto-off`, `settings-stick`, the "before" values and the re-check of phase G (`c_before`, `c_before_auto`) |
| D-5 | The reason of a failed check (`fail_code`), and the call and native code of the failure |
| D-6 | `timings`, `cycles` |
| D-7 | `identity` |
| D-8 | `system:camera-access`, `system:video-effects` |
| D-9 | `system:usb`, `group:open` |
| D-10 | `native-jpeg` (`encoded_by_skellycam`, `decoded_by_skellycam`) |
| D-11 | `native-jpeg` (the hashes after each trigger, compared with the ring slot and the MKV block of the same `source_frame_number`; `dqt_sha256` for the macOS JPEG proof of 10.7) |
| Linux, macOS rows | `system:kernel`; `native-jpeg` (`subtypes`), `clock` (`sync_clock_is_host`) |

Certify needs two keys more than [ux 4.6.2] gives (section 18.2 item 4): `restore_ok` and
`restore_failed` (the result of the restore at the last close). It also needs the search count of
SkellyCam Auto in the camera status (section 13).

### 10.4 Probes [U, A]

A probe is allowed only where the product path cannot see the fact [U]. It is named `probe:...`, is
record-only, and is code of certify, not of the product [ux 4.4.10]. Two kinds exist:

- A **system probe** runs in its own probe child and never opens a camera.
- A **camera probe** (only the macOS approach probes of 10.7) opens one camera at a time in its own
  probe child, with the session child of the product closed for that camera. It runs in phase D when
  it is safe and in phase F when it can change or block the camera (10.7). It never runs on a camera
  that hung or was marked dead, and the product never uses its result in the same run.

| Probe | Kind | What the product cannot see |
|---|---|---|
| `probe:camera-holders` (Linux) | system | The processes that hold the video nodes before any open (`/proc/*/fd`), as a fixed list `pipewire`, `wireplumber`, `other`. Certify then does not open a held camera, because `S_FMT` sends a PROBE to the camera before it returns `EBUSY`. |
| `probe:<model>:<approach>` (macOS) | camera | The approaches for exposure control and for the camera's own JPEG that the product does not use (10.7). |

The kernel facts and the USB alternate setting are diagnostics keys (`kernel`, `usb_alt`
[ux 4.6.2]). Thus draft 3 has `system:kernel` (6.2) and `usb_alt` in `system:usb` in place of the
probes `probe:kernel` and `probe:usb-alt` of draft 2 [A].

### 10.5 A failing native source must not break the run or the system [U, A]

The code of the new sources is unproven. Thus:

- Each camera runs in its own camera process [P §3], and the session child runs the group. A crash in
  `ctypes` or PyObjC ends only that camera process. The product reports "camera process ended (exit
  code n)" (cap 6.6) with the failure code `process-ended` [ux 4.6.3]; certify gives the running
  assumption check `fail` with the common code `crashed` [C 5.3] and `numbers.exit_code`, and goes on
  with the other checks and the other cameras.
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
[C 2.7 rule 3]. `controls`, `auto-off`, `modes`, `identity` and the macOS probes of 10.7 are in
`full`.

### 10.7 macOS: the approach probes for exposure and for the camera's JPEG [U, A]

The user ruled: on macOS, a certify run tries every approach that might work for exposure control and
for the delivery of the camera's own JPEG, for now. The test is trimmed when a working approach is
found [U] ([ADR-C5BR](../decisions/entries/C5BR-macos-approach-probes-in-certify.md)). The product
uses only the approaches that [ux 4.4.10] allows: for the JPEG `videoSettings = {}`, then
`kCVPixelBufferPixelFormatTypeKey = 'dmb1'`; for exposure the CoreMediaIO exposure feature control
with an absolute value in seconds. Certify tries each other approach as a camera probe (10.4).

The list of the approaches, their steps, their sources and the approaches rejected without a trial
come from a desk research of 2026-11-20 that the supervisor gave to the agent [NV until a run]. This
section gives the checks. Each probe is `record-only`. Its `numbers.works` is one of `works`,
`appears`, `no` and `not-applicable` (fixed vocabulary).

**Rules for each probe** [A]:

1. **Once per model.** The probes run for the first camera of each model (USB id and backend) only,
   as the camera blocks of 5.1 [U: one check per model]. The other units get no probe row.
2. **Order.** One camera at a time inside each step. The Kiyo Pro runs last in each step (8.1).
3. **No claim.** A probe never claims a USB interface, never detaches a driver, never seizes a device
   (`USBDeviceOpenSeize`, IOUSBHost `.deviceCapture`), and never changes a system setting.
4. **Restore by the same path.** Before a probe changes a control, it reads the value and the auto
   state ("before"). At its end it writes the "before" value back through the same path that changed
   it, then sets the CoreMediaIO `fcam` and the AVFoundation modes back. Phase G reads the values
   again (8.3).
5. **Wedge.** A wedge is no frame for 2 s, a call that does not return in its limit, or a camera that
   is gone. On a wedge, the probe records the diagnostics, marks the camera dead for the rest of the
   run (`prior-failure` for each later check, `camera-wedged` in phase G), and never tries to revive
   it [U: the Kiyo Pro wedge rule].
6. **Records.** For each call: the `OSStatus`, `IOReturn` or `NSError` code as a number with its
   domain (`native_code`, `native_domain`), the call name and the time in ms. The codes
   `kIOReturnNotOpen` (0xe00002cd), `kIOReturnExclusiveAccess` (0xe00002c5),
   `kIOUSBTransactionTimeout` (0xe0004051) and `kIOUSBPipeStalled` (0xe000404f) also get a count of
   their own.
7. **No media in the report.** A probe keeps no frame. The movie file of B5 is a camera recording: it
   is written only in the work folder and deleted at the end of the probe (9.5).

**The proof rule for a control** [A]. A control `works` only when the image changes: the mean luma of
the centre 50 % of the decoded frame rises with the exposure or gain value (the ratio of the high to
the low value is at least 1.3, when the luma is 10 to 240), or the frame rate falls at an exposure of
62.5 ms (log2 s = -4) at 30 fps with `CT_AE_PRIORITY` = 1. A read-back that equals the set value with
no image or frame-rate change is `appears`: CoreMediaIO can return a cached value. Where two paths
exist, the probe also reads the value through the other path (`cmio_after_ep0`: `updated`, `stale`,
`absent`). A luma outside 10 to 240 gives `too-dark` or `too-bright` and no judgement.

**The proof rule for a JPEG** [A]. A JPEG `works` (it is the camera's own) only when the probe has
block buffers that pass proof 1 or proof 2, and, for B1 and B2, also proof 3. A block buffer that
starts with `FF D8` is only `appears`, because Apple's encoder (B4) gives that too.

1. `dqt_sha256` of the first frame, and the set of distinct DQT hashes over 30 frames, equal the
   reference of the same model from a Windows or Linux passthrough run in the evidence file (11.2).
2. No DHT, for a model whose reference frames have no DHT. When a DHT is present but the DQT matches,
   `dht_added_by_os` is true.
3. The DQT differs from both B4 references, and the B4 DQT changes with `AVVideoQualityKey`.
4. Record only: the APP markers and the SOF sampling against the reference; the `VS_COMMIT`
   `GET_CUR` format index (phase F only: it proves the wire format, not the passthrough); the frame
   sizes (`bytes_min`, `bytes_p50`, `bytes_p99`, `bytes_max`).

A model with no reference in the evidence file gets `no-reference`, and its JPEG probes give at most
`appears`.

**The probes, in run order** [A]:

| Step | Phase | Probe `probe:<model>:...` | What it does | Runs when | Time per model |
|---|---|---|---|---|---|
| 1 | C | `s0-listing` | No stream. The AVFoundation formats and the UVC descriptors from the IORegistry (no open); the codec types of a data output and a movie file output; the CoreMediaIO objects of the device and its streams, with their classes and the `HasProperty` and `IsPropertySettable` flags of each feature property; the supported AVFoundation modes; `respondsToSelector:` for the selectors of A10. | always | 5 s |
| 2 | C | `b3-nil`, `b1-empty`, `b2-dmb1`, `b2-jpeg4cc`, `b2-dmb1-sized`, `b2-chromium`, `b4-apple-jpeg` | The `videoSettings` variants of the data output at 720p30 and 1080p30 (B3 is the decoded control; B1 empty; B2 four variants; B4 the Apple JPEG encoder at quality 0.5 and 0.9, the re-encode reference). | the listing found a `'dmb1'` format, else `not-applicable` | 75 s |
| 3 | C | `b5-movie-file` | A movie file output with empty output settings and its file-output delegate, 5 s at 720p30; the delegate samples and the `.mov` samples (`stsd`, `stsz`, `stco`). | as step 2 | 15 s |
| 4 | D | `a9-avf-lock`, `a10-avf-custom` | A9: the camera's own auto for at most 2 s, then locked; luma drift over 60 frames; the mode after a restart. A10: only when the listing found an iOS-only selector: one guarded call. A9 is never a product mode [U: exposure rule]. | always; A10 only with a selector | 10 s |
| 5 | D | `a1-cmio-native`, `a2-cmio-absolute`, `a3-cmio-native-data`, `a4-cmio-tune` | CoreMediaIO feature controls: A1 `fcnv`, A2 `fcna`/`fcav` with the unit `fcun` and `fa2n` at -7, A3 `fcnd` on the `uc**` classes, A4 the one-shot Tune `fctn`. Exposure, gain, focus (sharpness record only), white balance, power line (read only). | each when the listing found its object; A4 only when A1 or A3 gave a manual path | 70 s |
| 6 | D (end) | `b6-cmio-stream` | A CoreMediaIO stream with no AVFoundation session: the MJPEG format description, `CMIOStreamCopyBufferQueue`, `CMIODeviceStartStream`, 3 s, then the stop in a `finally`, then one AVFoundation open and close as a check. | the stream lists an MJPEG format | 10 s |
| 7 | F (after the in-use and 60 fps checks) | `a6-ep0-device`, `a5-ep0-interface` | Endpoint-0 UVC class requests with no open: A6 `DeviceRequestTO` on the device plug-in, A5 `ControlRequestTO` on the interface plug-in. First read only (`GET_INFO`, `GET_MIN`, `GET_MAX`, `GET_RES`, `GET_DEF`, `GET_CUR`, 1000 ms timeout, at least 4 ms between requests) and the `VS_COMMIT` `GET_CUR`; then writes of exposure, gain, focus, white balance, power line; then the survival of a value over an AVFoundation mode toggle and a session restart. | always (a write only after its read passed) | 45 s |
| 8 | F (end) | `a7-device-open` | `USBDeviceOpen` with no seize, one `GET_CUR` and one `SET_CUR` of the same value, `USBDeviceClose`; hold time at most 100 ms. | only when A5 and A6 both failed | 10 s |
| 9 | F (last) | `a8-iousbhost` | `IOUSBHostDevice` with `options: []`, one `GET_CUR`, destroyed at once. | only when A7 failed | 10 s |

Steps 1 to 6 are the safe part. Steps 7 to 9 can change or block the camera, so they run in the risky
phase F, after the other risky checks, as the user decided for the risky checks [U]. Step 2 skips the
top-rate cells when B1 or B2 proves the camera's own bytes; B5 and B6 still run one time, to know the
fallback.

Numbers for each probe [A]: `works`; the counts and codes of rule 6; for a control probe `set_ok`,
`readback_ok`, `luma_ratio_hi_lo`, `fps_effect`, `survives_restart`, `restore_ok`, `cmio_after_ep0`,
and `max_interval_ms` against the baseline (a probe with a frame gap over 2 times the baseline is
`no`); for a JPEG probe `delivered`, `has_block_buffer`, `has_image_buffer`, `frames`, `fps`,
`soi_eoi_ok`, `strict_decode_ok`, `sof_matches_mode`, `dqt_sha256`, `dqt_distinct`, `dht_present`,
`dht_added_by_os`, `dqt_equals_reference` (or `no-reference`), `dqt_differs_from_apple_q50`,
`dqt_differs_from_apple_q90`, `apple_dqt_changes_with_quality`, the frame sizes, `cpu_pct`. Each
numeric code is a number; each name is a string of a fixed list. No raw bytes and no path.

**Drop rules** [U, A]. "Trimmed once a working one is found" [U]. A drop applies only through a row
that a maintainer accepted into `camera_evidence.json` (11.2): the row of the OS key and the model
gets a field `approaches` with the result of each probe. A local run never drops a probe by itself.
Until such a row exists, each probe of the table runs. With a row:

| Result in the row | Keep | Drop |
|---|---|---|
| B1 `works` on each tested model | B1 | the B2 variants except `b2-dmb1`, B4, B5, B6 |
| B1 not, `b2-dmb1` `works` | `b2-dmb1` | the other B2 variants unless a model needs one; B5, B6 |
| No data-output variant works, B5 or B6 `works` | the one that works; a spec change of [ux] is then needed | B1, B2 |
| Nothing `works`, and `VS_COMMIT` says MJPEG | the product fallback (decode and re-encode) | B1 to B6 for that OS key; `b2-dmb1` again once for each new macOS major version |
| The MJPEG modes are listed only as `'420v'` | the fallback | B1, B2, B5; B6 only when the stream lists MJPEG |
| A1 or A2 `works` for exposure on each tested model | that path | A3 to A8 for exposure; A6 read only for one more run |
| A3 `works` where A1 and A2 do not | A3 | A1, A2 for that class |
| A5 or A6 `works` for writes with no frame gap | A6 when both work, else A5 | A7, A8 |
| A5 and A6 refused, A7 `works` | A7 waits for a decision of the user (an exclusive open) | A8 |
| No path changes exposure | no Manual on macOS for that model [ux 4.5 item 12] | A4, A10 |
| A4 or A10 does nothing | — | A4, A10 |

**Rejected without a trial** [A]: libusb, libuvc, pyuvc and other isochronous streaming (they must
claim the interface or seize the device); `USBInterfaceOpen` before a request; `USBDeviceOpenSeize`;
IOUSBHost `.deviceCapture`; a DriverKit or CoreMediaIO camera extension of our own; a legacy DAL
plug-in; SIP off, a kernel extension or a root daemon; USB packet capture; FFmpeg, OpenCV, GStreamer
and the other libraries that give decoded pixels; OBS `mac-avcapture`; a compiled helper as a
subprocess (the same mechanism as A5); vendor extension units; steering the camera's own auto
(`eroi`, `etgt`, `eint`, `emax`, exposure point of interest; the listing records them only); the
iOS-only `exposureTargetBias` and `activeMaxExposureDuration`; a Mac Catalyst build.

**Time** [A, NV until a run]. Steps 1 to 7 take about 230 s for each model (about 4 min); steps 8 and
9 add about 20 s for each model only when they run. The probes replace the 60 s of the endpoint-0
check of draft 2. Thus a full run on macOS takes about (section 16):

| Models | Full run on macOS |
|---|---|
| 1 | about 10 min (265 s + 340 s for the model) |
| 2 | about 16 min (265 s + 680 s) |
| 4 | about 27 min (265 s + 1360 s) |

This is above the 6 to 11 minutes that the user accepted for a full run [U] for two models or more.
Question 13 asks the user whether the longer macOS full run is accepted while the probes run.

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

### 11.2 The data file [U]

`skellycam/core/camera/camera_evidence.json`, shipped in the package [U]. JSON, because skellycam has
no YAML library and must not add one for this [A]. The app never downloads it.

```json
{
 "schema": 1,
 "systems": [
  {"os": "Windows", "os_key": "11 26H2", "backend": "media-foundation", "state": "verified",
   "source": "maintainer", "reports": ["<report id>"]}
 ],
 "cameras": [
  {"device": "046d:085c", "model": "Logitech C922", "backend": "media-foundation", "os": "Windows",
   "abi": "lp64", "state": "verified", "source": "maintainer", "limits": ["rate-60-at-m7-only"],
   "jpeg_reference": {"dqt_sha256": "<hex>", "dqt_distinct": 1, "dht_present": false},
   "reports": ["<report id>"]},
  {"device": "046d:085c", "model": "Logitech C922", "backend": "avfoundation", "os": "macOS",
   "os_key": "26", "abi": "lp64", "state": "verified", "source": "maintainer",
   "approaches": {"b1-empty": "works", "a1-cmio-native": "appears", "a6-ep0-device": "works"},
   "reports": ["<report id>"]},
  {"device": "1532:0e05", "model": "Razer Kiyo Pro", "backend": "media-foundation", "os": "Windows",
   "state": "verified", "source": "maintainer", "limits": ["rate-60-not-delivered", "wedge-risk", "name-generic"],
   "reports": ["<report id>"]},
  {"device": "4c4a:4a55", "model": "USB Camera", "backend": "media-foundation", "os": "Windows",
   "state": "known-bad", "source": "maintainer", "limits": ["rate-below-declared"], "reports": ["<report id>"]}
 ]
}
```

- `state`: `verified`, `known-bad`. A key with no row is `unknown`.
- `abi`: `lp64` or `ilp32`, beside the OS key [ux 4.6.4, A-23]. Each key of this file and of the
  local record (2.5) holds it.
- `jpeg_reference`: the DQT hash, the count of distinct DQT hashes and the DHT flag of the model from
  a Windows or Linux passthrough run. The macOS JPEG proof of 10.7 compares with it.
- `approaches`: for a macOS row, the result of each probe of 10.7 (`works`, `appears`, `no`,
  `not-applicable`). Only this field trims the probes (the drop rules of 10.7).
- `os_key`: Windows: the release and the feature version from `os.label` (`11 26H2`); macOS: the major
  version (`26`); Linux: the kernel major and minor version (`7.0`), because `uvcvideo` changes by
  kernel.
- `limits`: fixed codes, each with one sentence in `skellycam/REASON_CODES.md`, for example
  `rate-60-not-delivered`, `rate-60-at-m7-only`, `rate-below-declared`, `cliff-m6`, `wedge-risk`,
  `name-generic`, `no-native-jpeg`, `settings-revert`.
- `reports`: the report ids [C 3.1] in `reports/` of `skellycertify`.
- A tool `tools/check_camera_evidence.py` refuses a row with a missing or wrong field, as the checker
  of skellytracker does.

### 11.3 How the product uses it [U]

- Detection gives each camera a field `evidence`: `verified`, `known-bad` or `unknown`, and the status
  gives `system_evidence` for the OS key and the backend.
- Windows: native capture is the only path after phase 3 (no fallback, cap 14.2). An `unknown` camera
  works as any camera; the UI shows "Not verified yet: run the camera check and send the report". A
  `known-bad` camera shows its limits as fixed texts (for example "This camera declares 60 fps and
  delivers 30").
- Linux and macOS: "when a system passes, native capture can be used there at once" [U]. The user
  decided [U]: native capture is the default only on an OS key that is `verified` in the file, or
  after a local passed `full` run of certify (a local pass [C 7.2]). On each other system the product
  keeps OpenCV, and the app prompts the person to run certify for an unknown camera or OS version
  (11.4).
- The local pass is for each camera model: a row of the local record (2.5) with the model, the
  backend, the ABI and the current OS key, the level `full`, and the result `pass` or `partial`
  [ux 4.9]. A `quick` row never turns on native capture [A]. The source selection of [ux 4.9] reads
  this row.
- The OpenCV fallback on Linux and macOS is "for now" [U]. The direction, not a requirement of this
  step: when enough runs of native capture pass, OpenCV goes, and each new OS version waits behind the
  certify test [U].
- The limits never replace the checks of the product: the real 60 fps check still runs [U].

### 11.4 The prompt for a new OS version or camera [A]

- The contract has no prompt. The nearest mechanism: skellytracker's plan skips at level `quick` an
  item that has a reviewed row, and a package can say in the plan `details` which items have no row.
- skellycam: `certify_plan` gives `details.cameras[].evidence` and `details.system_evidence` (9.1).
  The product status gives the same fields (11.3).
- The app owns the prompt [U]: when a camera or the OS key is `unknown`, the app offers "SkellyCam has
  not seen this camera (or this OS version) yet. Run the camera check and send the report?" The
  prompt comes after the pop-up check of a new model (2.5), or at the first detection of a new OS
  key, and one more time at most after 7 days [A]. Plugging in a camera alone shows no prompt [U].

### 11.5 From a report to a release [U, A]

1. The person runs certify and chooses "send". The relay files the report in `skellycertify`.
2. A reviewer checks it by `review.md`, with the rules that the certify session adds for skellycam rows.
3. A tool of skellycam, `tools/camera_evidence.py propose`, reads the reviewed reports of `reports/`
   and proposes rows by this rule:
   - **Camera verified** for (device, backend, OS): 3 valid `full` reports from 2 different systems,
     with the summary item of the model `pass`, and no `fail` of a
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
- A list of notices to the person (8.3) [U: to ask; not in format 1.3.0].
- A risk to a device in the text of `system_changes` (8.4) [U: to ask; not in format 1.3.0].

Format 1.3.0 settled the summary results `partial` and `skipped` with `busy`, one `camera` item for
each model, and the common codes `cameras-busy` and `interrupted`. A `partial` or `skipped` item never
gives a reviewed row [C 7.2]: thus only a `pass` item counts toward `verified` (11.5), and the limits
of a verified camera come from the failed mode checks of a `pass` report (for example a 60 mode that
does not deliver). The `benchmark` group of 1.3.0 is for a GPU stage (`device` is a GPU id, with
`ms_per_frame` and `fps`): the disk figure does not fit it, so `write_mb_per_s` stays in `numbers` of
`system:disk-benchmark` [A].
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
- The record of the camera models that are checked on this system (2.5), and the plan field
  `details.unchecked` that tells the app which models to check.

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
  in the app. skellycam refuses a run with `cameras-busy` when it finds an open group (9.7).
- The pop-up check of a new model when the person first opens it (2.5): freemocap owns the pop-up, the
  progress file for crash reports (9.6) and the notice "Camera <name>: wedged, please replug" (8.3);
  skellycam owns the checks and the record.

## 13. What the product is missing

| Need | Today | Step that delivers it |
|---|---|---|
| A fixed failure code (`camera-in-use`, `usb-bandwidth`, `hung`, ...) in the failure object of cap 12 | Free text only (`errors.py`) | Step 7s: `CaptureFailure.code` with the codes of [ux 4.6.3], also for Media Foundation [ux 4.2 item 1]. The user decided the code [U]. |
| The controls before the first set, in the diagnostics (`c_before`, `c_before_auto`) | `set_controls` reads before each set, but does not report it | Step 7s [ux 4.6.2, 4.7]; the Media Foundation source in the same step |
| A restore of the "before" values at each close, on by default, on the three systems, with its result in the diagnostics (`restore_ok`, `restore_failed`) | None | Step 7s [ux 4.7]. The user decided that the product restores at its own close [U]; [ux 4.7] draft 2 has it on by default. The result keys are open (section 18.2 item 4). |
| The state `adjusting`, `exposure_found` in the status, and a new search when the frame rate changes | No `adjusting` state; the search runs at an apply with `RECOMMEND` | Step 7s and the Media Foundation change of [ux 4.5]; the rule is a decision of the user [U] (5.3) |
| A count of frames that skellycam encoded and decoded (`encoded_by_skellycam`, `decoded_by_skellycam`) | None | Step 7s, the shared loop [ux 4.2 item 3]; 3b for the encoder |
| The diagnostics dict of [ux 4.6.2] in the camera status | None | Step 7s [ux 4.2 item 2] |
| The local certify store: `checked_models.json` and the local pass record | None | The certify step (2.5, 11.3) |
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
| The native V4L2 and AVFoundation sources, with the diagnostics D-1 to D-11 of 10.3 | Research code only | Phase 7, moved up [U]; spec [ux] |

## 14. Questions for the user

The user answered each question of draft 1 and of draft 2 on 2026-11-20
([ADR-GVC0](../decisions/entries/GVC0-certify-decisions-of-the-user.md),
[ADR-KG00](../decisions/entries/KG00-certify-decisions-of-the-user-on-draft-2.md)). These questions
are only the new ones that draft 3 opens. Each is worded so that "yes" accepts the recommendation.
The most important is first.

1. The summary item of a model (3.3): `skipped` with `busy` only when each unit of the model is held
   by another program; else any `fail` gives `fail`; all `pass` gives `pass`; all `record-only` gives
   `record-only`; each other mix gives `partial` (for example one unit `pass` and one unit busy). A
   camera whose base claims pass but whose settings or JPEG claim did not pass or could not judge (for
   example too dark) is `partial`, as the contract defines it. Yes?
2. The record of checked models (2.5) is keyed by the USB id, the backend and the OS key. After a new
   OS version (a Windows feature version, a macOS major version, a Linux kernel minor version), each
   model counts as unchecked again, and the app shows the pop-up check at its next open. Yes?
3. A model counts as checked only when its summary item ended `pass`, `partial` or `fail`. An item
   `skipped` (busy) or `record-only` (cancelled, no access, time budget), and an interrupted run, write
   nothing, so the app checks that model again at its next open. Yes?
4. A full run checks the camera block (phases C, D and F) of one camera for each model; each other
   camera of that model gets its quick claims, the group checks, and `not-run` with `same-model` for
   the block. A run with more than four different models then still goes above 11 minutes (about 18
   minutes for eight models), and the plan shows that estimate. Yes to both?
5. For an interrupted run (9.8), each check item of a progress message also carries its `reason`,
   `module` and `numbers` after it ends, so that freemocap can write the interrupted module report from
   its progress file, and skellycam needs no other function. Yes?
6. A full run checks the Auto rule "search again when the frame rate changes" with one more check in
   phase F (`<label>:auto-exposure:<w>x<h>@60`, about 8 s for each camera), and fails it with
   `auto-not-searched`. Yes?
7. Progress (9.6): only a step that runs in a child or touches a camera gets its own message before it
   starts; a check that only computes from earlier numbers does not. To keep the limit of 10 messages
   each second, certify waits up to 100 ms before a step and never drops a message. Yes?
8. `cameras-busy` (9.7): certify refuses the run only when it finds an open camera group of skellycam
   in the calling process, and then also the checks that do not touch a camera are `not-run` with
   `cameras-busy`. A camera that a skellycam server in another process holds is `camera-in-use` for
   that camera only. Yes?
9. One record file for the checked models and the local pass (`camera_checks.json` of [ux 4.9]):
   certify writes a row also after a `quick` run (the pop-up check), so that the model counts as
   checked, but only a `full` row with `pass` or `partial` turns on native capture on Linux and
   macOS. The Linux and macOS spec then reads the level in its rule 2. Yes?
10. Section 18 lists the differences that remain to the Linux and macOS spec draft 2. For each one
    the Linux and macOS spec changes to match certify: `probe:camera-holders`, the checks `clock` and
    `sequence` for A-9, A-10, M-9 and M-10, the keys `restore_ok` and `restore_failed`, a counter of
    long intervals that have a sequence gap, the rows of a `quick` run in the local record, and the
    names of the macOS probes of 10.7. Yes?
11. The macOS approach probes of 10.7 run for one camera of each model only, the safe ones in phases
    C and D and the endpoint-0 and device-open ones (A5 to A8) last in phase F, with the Kiyo Pro last
    in each step; a probe is trimmed only through the field `approaches` of a maintainer-accepted row
    of `camera_evidence.json`, never by a local run. Yes?
12. skellycam sends the two other requests to the owner of the contract now, as a minor change after
    format 1.3.0: a list of notices to the person (8.3), and a risk to a device in the text of
    `system_changes` (8.4). Yes?
13. While the macOS probes run, a full run on macOS takes about 10 minutes for one camera model, 16
    for two and 27 for four (10.7), above the 6 to 11 minutes accepted for a full run. Is the longer
    macOS full run accepted until the probes are trimmed?

## 15. Reason codes (proposed `skellycam/REASON_CODES.md`) [A]

Common codes that skellycam uses [C 5.3]: `timed-out`, `crashed`, `bad-output`, `hung-at-exit`,
`cancelled`, `not-built`, `not-selected`, `no-version`, `no-commit`, `modified-tree`, and the asked
codes `cameras-busy` (9.7) and `interrupted` (9.8). The summary reason `busy` is a value of the
contract [C 3.7], not a code of this list.

The failure codes of the product [ux 4.6.3] are reason codes of this list. A check that fails because
of a product failure gives the product code as its reason, with one exception: the product code
`process-ended` gives the common code `crashed` [C 5.3] and `numbers.exit_code` (10.5) [A].

| Code | Where | Meaning |
|---|---|---|
| `backend-missing` | `detect` | The capture backend is not on this system (for example no Media Foundation). |
| `no-camera` | `evidence.reasons`, camera and group checks | The run found no real camera. The camera part of the report reads "not checked" (3.3). |
| `same-model` | camera block checks of `full` | Another camera of the same model had these checks in this run (5.1). |
| `partial` | the row `<label>` | The camera works at the base setting, and a claim did not pass (3.3). |
| `not-linux` | `system:kernel` | The check is for Linux only. |
| `auto-not-searched` | `auto-exposure` checks | SkellyCam Auto did not search at the open, or after a change of the frame rate (5.3). |
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
| `rate-low`, `rate-high` | rate checks | More than 3 % below or above the mode rate. The sentence of `rate-low` is the product text: "Camera is slow. Try adding more light" [U]. |
| `rate-under-contention` | group | The camera passes alone and fails in the group. |
| `too-dark`, `too-bright` | light-dependent checks | The frame is too dark or too bright to judge (4.6). |
| `readback-differs`, `setting-reverted`, `no-image-effect`, `control-failed`, `exposure-not-applied` | settings and control checks | A set value reads back different; it changed back later; the image did not change; the set call failed; a set exposure did not apply. |
| `control-absent` | control checks | The camera has no such control. |
| `no-native-jpeg`, `jpeg-damaged`, `jpeg-size-differs` | `native-jpeg` | skellycam encoded the frames; a frame is damaged; its size is not the size of the mode. |
| `wrong-reason` | `<label>:in-use` | The product gave a failure that is not "in use". |
| `device-removed`, `stalled` | any camera check | Removed; no frame for 2 s (cap 6.7). |
| `previous-process-alive`, `stream-error`, `format-changed`, `process-ended` | any camera check | Product failure codes of [ux 4.6.3]: an earlier camera process still holds the camera; the stream gave an error; the format changed during the stream; the camera process ended (certify reports `crashed`). |
| `take-not-finished`, `take-error`, `rows-differ`, `missing-rows`, `gaps-unexplained`, `group-rate-off`, `too-few-frames`, `frame-not-decodable` | take checks | Section 4.5. |
| `fat-disk`, `disk-stall`, `write-error`, `disk-slow`, `disk-full` | take checks, `system:disk`, benchmark | rec 4.2, 5.3, 5.4; section 6. |
| `gap-over-limit` | `self:` checks | A healthy fake camera had a gap above 100 ms. |
| `clock-base-differs`, `sample-after-arrival`, `sample-too-early` | `clock` | 10.2. |
| `sequence-unreliable`, `no-sequence` | `sequence` | 10.2. |
| `unit-mapping`, `auto-not-off`, `auto-came-back`, `setting-lost-on-reopen`, `mode-not-granted`, `id-unstable`, `id-collision`, `ep0-refused` | assumption checks | 10.2. `setting-lost-on-reopen`: the config value did not read back at a later open. |
| `no-access`, `no-permission` | camera checks | Linux: no access to the video node; macOS: no camera permission for the app. |
| `no-manual-exposure` | `controls`, `settings-stick` | A macOS camera with no manual exposure: it opens with a warning, and SkellyCam cannot set its exposure [ux 4.5 item 12]. |
| `not-applicable`, `no-reference` | macOS probes (10.7) | The listing found no object or format for this approach; the evidence file has no JPEG reference for the model. |
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
| C | Identity, modes, the controls list (from the same opens) | 1 |
| C | `rate:1920x1080@30`; the largest size (often the same: 0) | 6 to 12 |
| D | Exposure sweep at `<base>` (at most 9 steps) | 23 |
| D | Auto, control sets | 9 |
| F | In-use | 8 |
| F | Two 60 fps modes and the sweep at 60 | 18 |
| F | The Auto search after the change to 60 | 8 [NV] |
| F | Five cycles | 10 |
| G | Plain open | 2 |
| | Start and end of the camera block children | 6 |
| | Sum | about 100 |

The rest of `full`: quick 31 s, `group:take-30` 45 s, `group:take-60` 25 s, `system:disk` 35 s, the
benchmark 5 to 35 s, self-checks 110 s. About 265 s.

| Cameras (models) | Quick | Full |
|---|---|---|
| 1 (1) | 31 s | about 6 min (265 + 100 s) |
| 4 (4) | 31 s | about 11 min (265 + 400 s) |
| 4 (2) | 31 s | about 8 min (265 + 200 s), with one camera block for each model (5.1) |
| 8 (8) | 32 s | about 18 min (275 + 800 s) |

The user accepts a full run of 6 to 11 minutes [U]. A run with more than four models goes above 11
minutes (question 4). The quick figures include `self:hang-100ms`, with the restore in the product
[U]. The camera blocks run one camera at a time: two
cameras at once would share a USB domain and change each other's results. On Linux and macOS the
assumption checks of 10.2 come mostly from the same opens; they add about 10 s for each camera, from
the 12 to 15 and 20 to 30 minutes of the research runbooks for four cameras [M `research/usb_cameras/suite/linux/RUNBOOK_PLAN.md`,
`suite/macos/RUNBOOK_PLAN.md`]. On macOS the approach probes of 10.7 add about 230 s for each model
(10.7 gives the full times on macOS). All figures are [NV] until the first run.

## 17. Test list of the certify code

Each test uses fake sources or fake backends, unless it says "hardware". No test opens port 53117.
Draft 3 changes T-CERT-01, 03, 06, 07, 10, 13, 16, 17, 19, 24, 26, 32, 34 and 37, and adds T-CERT-41
to 57. Each
of these says where it runs: "3 OS" means with fakes on Windows, Linux and macOS, in the three CI
jobs.

| ID | What it does | Pass criterion |
|---|---|---|
| T-CERT-01 | 3 OS. `certify_plan("quick")` and `("full")` with a fake enumeration of 0, 1, 4 and 8 cameras and 4 virtual cameras, a fake evidence file, and a fake record of checked models that holds one of the models. | The fields of C 2.6; empty `downloads`; the risk sentence in `system_changes` for `full` only; `seconds_estimate` = `30 + N/4` rounded up for quick and by 16 for full; `evidence` of each camera from the file; `checked` of each camera and `details.unchecked` (one item for each unchecked model) from the record; no activate call; `comtypes` not imported in the caller. |
| T-CERT-02 | `certify("slow")`, `certify_plan("")`. | `ValueError` [C 2.2]. |
| T-CERT-03 | 3 OS. Quick with 4 fake cameras of 3 models. Validate the report. | Each required field of C 3.1; `kind` = level; each name matches C 3.4 and is unique; each `fail` and `not-run` has a reason of C 5.2; each `numbers` value has an allowed type; the schema id `skellycertify.report/1.3.0`; each summary item has a `group` of C 3.7, a `name` of 1 to 80 characters, a `device` of at most 40 characters or `null`, a `reason` only for `skipped`; each camera check has `module` (3.1). |
| T-CERT-04 | Fakes with planted values: a host name and a user name in a camera name, a path, a MAC-like string, a serial, `take.mkv`, a long string. | C 6 rules 1 to 11 hold; the planted values are gone. |
| T-CERT-05 | Camera names: `Alex's iPhone Camera`, `Kamera’s Webcam`, a name with the host name, `HD Webcam (SN 12AB34CD56)`, `USB Video Device`. | `iPhone Camera`, `Webcam`, `Camera vvvv:pppp`, `HD Webcam`, `USB Video Device`. |
| T-CERT-06 | 3 OS. No camera attached. | `detect` `pass` with `cameras` 0; each check that needs a camera `not-run` `no-camera`; no `fail` in the report; the self-checks run; no `camera` summary item; `no-camera` in `evidence.reasons`; no row written to the record of checked models. |
| T-CERT-07 | 3 OS. Quick with 4 good fakes of 4 models. | Each claim `pass`; 4 rows `pass`; 4 summary items `pass` in detection order; the work folder is gone; each camera is `healthy` or `restored` with no cleanup row. |
| T-CERT-08 | The generic-camera pattern (T-CAP-17), bright frames. | `rate` `fail` `rate-low`; row `fail`. |
| T-CERT-09 | 3 OS. The same with dark frames (mean 10). | `rate` `record-only` `too-dark`; row `partial` (3.3 rule 5); summary item `partial`. |
| T-CERT-10 | 3 OS. A fake in use at the open, beside two good fakes of other models. | `opens` `not-run` `camera-in-use`; its row `skipped-busy`; its summary item `skipped` with `reason` `busy`; the run is not refused (no `cameras-busy`); no retry (open count 1); no row of that model written to the record of checked models. |
| T-CERT-11 | A fake refused for bandwidth in the group that opens alone. | Row `pass`; `group:open` `fail` `usb-bandwidth`. |
| T-CERT-12 | A fake that hangs at the open. | `opens` `fail` `hung`; later checks `not-run` `prior-failure`; never opened again (phase G included); cleanup `release:<label>` `camera-wedged`; the others complete. |
| T-CERT-13 | 3 OS. Settings: a fake whose exposure reads back -5 for a set -7; one that reverts after 0.5 s; one whose image does not change; one with a mean of 240. | `fail` `readback-differs`; `fail` `setting-reverted`; `fail` `no-image-effect`; `record-only` `too-bright`; each row `partial` by the row rule of 3.3, and each summary item `partial`. |
| T-CERT-14 | Native JPEG: a fake that gives YUY2 encoded by skellycam (after 3b); a fake with a cut JPEG; a fake with a SOF of another size; a fake with no DHT. | `fail` `no-native-jpeg`; `fail` `jpeg-damaged`; `fail` `jpeg-size-differs`; `pass` with `dht_inserted` > 0. |
| T-CERT-15 | The session child ends with `os._exit(5)`; sleeps past its limit with a grandchild; gives its result and does not end; gives bytes that are not a result. | `fail` `crashed` with `exit_code` 5; `fail` `timed-out` and no process left; `<name>:exit` `record-only` `hung-at-exit`; `fail` `bad-output`. |
| T-CERT-16 | 3 OS. Cancel during the quick apply, during the quick take and during phase F. | The checks that ended keep their results; the running and later checks `not-run` `cancelled`; the main process of the child ends first and the fake cameras get `close` (with the restore) within 12 s; phase G runs; no process left; the work folder is gone; `cancelled` in `evidence.reasons`; the record of checked models gets rows only for models whose camera row ended `pass`, `partial` or `fail` before the cancel. |
| T-CERT-17 | 3 OS. A progress spy that logs each message and each fake source call in one ordered list; checks that last 10 ms; a progress callable that raises. | `starting` first, `done` last; before each step that runs in a child or opens a fake camera, a message whose `step` names that check comes before the first source call of that step; no message for a computed claim check; at most 10 messages each second, and no step message dropped; each is JSON; after the raise, no more calls and the run completes [C 2.3]. |
| T-CERT-18 | `sys.stdout` and `sys.stderr` `None`, `sys.frozen` true, in a spawn child. | The report is complete; no read of stdin [C 2.5]. |
| T-CERT-19 | 3 OS. The selection rule with the mode lists of the C930e, the C922, the Kiyo Pro, a 4K camera, a 640x480-only camera, a YUY2-only camera, and two C922 fakes. | The exact checks for each, in the phase order of 2.3: identity, modes and rates (C) before the sweeps (D), the group and self-checks (E) before the risky checks (F); the 60 fps checks, the Auto search at 60 and the cycles in phase F; `<base>` `640x480@30` for the 640x480 camera; `no-mjpg-mode` for the YUY2 camera; the second C922 gets its quick claims and `not-run` `same-model` for the camera block (if question 4 is yes). |
| T-CERT-20 | A fake with no 1080p, no 60 and no focus control. | `not-run` with `no-mode`, `no-mode`, `control-absent`; no `fail`. |
| T-CERT-21 | A fake with the rates of table cap 10.5. | `cliff` -5 for the Logitech table and -7 for the Kiyo Pro table; the sweep stops after two `too_slow` steps. |
| T-CERT-22 | A fake that declares 60 and delivers 30 at each exposure; one that delivers 60 only at -7. | `fail` `rate-low`, and the row stays at its base result; `pass` with `ok_at_m7` true. |
| T-CERT-23 | SkellyCam Auto in a dark scene that hits the range end. | `record-only` `too-dark`, `at_range_end` true. |
| T-CERT-24 | 3 OS. Quick with 4 fakes and with 1 fake, local wall clock; then a 50 s delay planted in a check. | Under the estimate of 4.7 (31 s for 4 and for 1); with the delay, the next checks `not-run` `time-budget`, the run ends under 47 s plus phase G. |
| T-CERT-25 | Each self-check with fakes, and each with a planted fault of its rule (a 150 ms gap; a take that does not finish; a camera process that does not end in 15 s; a healthy camera marked `dead`; a spin; a torn read that passes). | `pass`; `fail` with the planted fault. |
| T-CERT-26 | 3 OS. Two fakes of one model. | Labels `.0` and `.1`; one summary item for the model [C 3.7]; `<model>:units` with `units` 2; a cleanup row of `.1` has the `module` of that item. |
| T-CERT-27 | Versions `2.0.0a6` and `2.0.0-a6`; `tree_modified` true; the option `cameras` with one of four labels. | `no-version` only for the first; `modified-tree`; no `partial-run` for the part. |
| T-CERT-28 | Cleanup after a pass, a crash, a time-out and a cancel; a locked file in the work folder; an old work folder with and without the marker; a file of the person in `recording_folder`. | The work folder is gone, or `not-deleted`; the marked old folder is gone; the rest stays. |
| T-CERT-29 | Search the report, and the files that the run wrote outside the work folder. | No media file, no string that ends with a media extension, no frame bytes, no path. |
| T-CERT-30 | Each reason code and each `limits` code that the code can emit, against `skellycam/REASON_CODES.md`. | Each is in the file with one sentence [C 5.4]. |
| T-CERT-31 | Each check name that the code can emit, with the longest backend, `nousb-nousb`, index 9 and rate 29.97. | Each matches the pattern. |
| T-CERT-32 | 3 OS. Patch the rate limit of `rate_check.py` and the stall limit of the take; spy on `CameraGroupManager`, `start_take` and the source factory; set `SKELLYCAM_WINDOWS_CAPTURE`, `SKELLYCAM_LINUX_CAPTURE` and `SKELLYCAM_MACOS_CAPTURE` to `opencv`. | The result follows the patched product limits; each open goes through the calls of 2.2; the native source is used; the OpenCV source is never created. |
| T-CERT-33 | Quick and full with fakes; list the sockets of the process tree. | No listening socket. |
| T-CERT-34 | 3 OS. Phase G with fake sources that keep the "before" values and restore them at each close: a fake whose controls were manual -6 and auto focus before the run; a fake whose restore at the close reports `restore_ok` false; a fake whose second open reports other "before" values than the first; a fake that fails the plain open of `full`; each case at `quick` and at `full`. | Quick: `healthy`, `camera-not-restored`, `camera-not-restored`, and no extra open in phase G. Full: `healthy`; `camera-not-restored`, or `restored` when the plain open sets the value back with a good read-back; `restored`; `camera-wedged`. |
| T-CERT-35 | The disk benchmark with a fake file object at 50 MB/s, one that stalls 2 s, and a folder with too little space. | `write_mb_per_s` 50 ±5 %, `cameras_1080p30_typical` 8, `worst` 2; `fsync_ms_max` ≥ 2000; `not-run` `disk-full`; the file is gone. |
| T-CERT-36 | The evidence file: rows with a missing field, a wrong state, an unknown limit code; the proposal tool with reviewed fake reports (3 from 2 systems; 3 from 1 system; 1 maintainer). | The checker refuses the bad rows; the tool proposes `verified` for the first and third, not for the second. |
| T-CERT-37 | 3 OS: the native sources with the fake layers of [ux 6.2] (draft 2: `FakeV4L2System`, `FakeAVLayer`) (a fake `ioctl` and a fake AVFoundation) that break one assumption each (decoded buffers only; a clock that is not the arrival clock; samples after arrival; no sequence; a wrong exposure unit; auto that comes back; a config value that does not read back at a later open; a granted size that differs; an id that changes; `EBUSY` at `S_FMT`; `ENOSPC` at `STREAMON`; no permission; a segfault in the camera process; a call that never returns). | Each breaks only its own check, with the reason and the numbers of 10.2; the other checks of that camera still run; the crash gives `crashed` with `exit_code` (product code `process-ended`); the hang gives `hung` with the `fail_call`; no permission gives `not-run` `no-permission`; the run ends in its limits. |
| T-CERT-38 | Hardware, Windows: quick on the four test cameras (C922, C930e, Kiyo Pro, generic). | Three rows `pass` (or `partial` with the reason), the generic `fail` `rate-low`, `group:take` `pass`; each camera `healthy` or `restored`. |
| T-CERT-39 | Hardware, Windows: full on the four test cameras. | The facts agree with the measurements of sections 5 and 8 (the Kiyo Pro 60 mode `fail` `rate-low`, the C922 60 mode `pass` with `ok_at_m7`); the risky checks run last; each camera ends `healthy`, `restored` or with `camera-wedged`. |
| T-CERT-40 | Hardware, Linux and macOS: full on the test cameras through the native sources. | Each check of 10.2 has a result and its numbers; the report agrees with the `--plan` runs of the research suites on the same system. |
| T-CERT-41 | 3 OS. The record of checked models: quick runs with fakes whose items end `pass`, `partial` (too dark), `fail`, `skipped` (busy) and `record-only` (cancelled; no access); two fakes of one model with `pass` and `fail`; a fake with no USB ids; then a change of the OS key; a store file that does not parse; a row with a missing field. | Rows for `pass`, `partial` and `fail` only; one row for the two fakes, with `fail`; the no-USB fake keyed by `nousb` and its cleaned name; after the OS key change, each model in `details.unchecked`; the bad file and the bad row count as no row, certify writes a new file and does not raise; no row holds a serial, a path or a `camera_id`; the store is not in the work folder and stays after the cleanup. |
| T-CERT-42 | 3 OS. The pop-up flow: a fake enumeration with three cameras, two of one model; the record holds the third model; `certify_plan("quick")`, then `certify("quick", cameras=details.unchecked labels)`. | `details.unchecked` has one item (the first camera of the unchecked model); the run checks only that camera; no `partial-run` in `evidence.reasons`; after the run, `certify_plan("quick")` gives an empty `details.unchecked`. |
| T-CERT-43 | 3 OS. Cameras busy: an open camera group in the app state of skellycam in the calling process; then a fake camera that a second process holds. | First case: each check `not-run` `cameras-busy`, `cameras-busy` in `evidence.reasons`, no source created. Second case: only that camera `skipped-busy`; the run continues and is not refused. |
| T-CERT-44 | 3 OS. The row rule and the model rule of 3.3, as table tests: each combination of the five claim results and reasons; each mix of unit rows of one model (`pass`, `fail`, `partial`, `record-only`, `skipped-busy`). | Each combination gives the row of the first rule that applies; each mix gives the item of 3.3; a failed declared 60 mode never changes the row. |
| T-CERT-45 | 3 OS. SkellyCam Auto: a fake product status with a search count; a fake that searches at the open and after the change to 60; one that does not search after the change; one that does not search at the open; a spy on each control set of the fake source. | `pass`; `fail` `auto-not-searched` for each of the two; no certify step sets the camera's own auto exposure as a mode (the spy sees no auto exposure set outside the product's own Auto search). |
| T-CERT-46 | 3 OS. The diagnostics reader: the fake Media Foundation, V4L2 and AVFoundation sources give `diagnostics()` with the keys of [ux 4.6.2], one with a missing key and one with a value outside the vocabulary; `frame_log` with 64 rows. | Each number of 10.2 that has a diagnostics key comes from that key; a missing key gives `null`, never a crash; a value outside the vocabulary is not copied: the number is `null`; `frame_log` is never copied into `numbers`. |
| T-CERT-47 | 3 OS. The local pass record: `full` runs with fakes that pass; one with a camera row `fail`; one with a self-check `fail`; a `quick` run that passes. | A pass record for the first run only, keyed by the OS key and the backend; none for the other runs. |
| T-CERT-48 | 3 OS. Native JPEG hash compare: a fake source whose frames have no DHT, so the shared loop inserts one; a fake whose ring slot differs in one byte from the hashed bytes of the same `source_frame_number`; hashes after `ready` and after a record start. | The first passes with `dht_inserted` > 0 and `hash_equal_source_ring` true; the second fails with `jpeg-damaged`; each hash is compared with the slot of its own frame number. |
| T-CERT-49 | 3 OS. `certify("quick", test_media_dir=<a temporary folder>)` and `certify_plan("full", test_media_dir=...)`. | Both accept the option; the run writes and deletes nothing in that folder; its path is in no report and no progress message. |
| T-CERT-50 | 3 OS. Interrupted run: a progress spy; the session child is killed during `group:take`. | Each item of `checks` of each message carries `reason`, `module` and `numbers` after its check ended; a module report built from the last message by C 2.5 has `group:take` `fail` `crashed`, the checks that did not end `not-run` `interrupted`, and `interrupted` in `evidence.reasons`; it validates as T-CERT-03. |
| T-CERT-51 | 3 OS. Report file layout with the freemocap writer fake: a run with a `partial` model, a `skipped` (busy) model and a failed camera check. | The camera table shows `partial` and `skipped (busy)`; the table of the failed checks shows the camera name in `Module` [C 4.2]; the disk figure is in `numbers` of `system:disk-benchmark`, not in a `benchmark` item (11.6). |
| T-CERT-52 | 3 OS. macOS probe sequence with `FakeAVLayer`, a fake CoreMediaIO and a fake IOKit layer: two C922 units, one Kiyo Pro, one C930e; each approach available. | The probes run for one unit of each model only; the steps in the order of 10.7, with steps 1 to 6 in phases C and D and steps 7 to 9 last in phase F; the Kiyo Pro last in each step; one camera at a time; the product session of a camera is closed while its probe runs; A4 runs only after A1 or A3 gave a manual path; A7 only when A5 and A6 failed; A8 only when A7 failed; no call of `USBDeviceOpenSeize`, `USBInterfaceOpen` or `.deviceCapture`. |
| T-CERT-53 | 3 OS. The proof rule for a control with the fake layers: a read-back equal to the set value with no luma change; a luma ratio of 1.5; a frame rate that falls to 15 fps at 62.5 ms; a luma of 5; a frame gap of 3 times the baseline during an endpoint-0 write. | `appears`; `works`; `works`; `too-dark` and no judgement; `no`. |
| T-CERT-54 | 3 OS. The proof rule for a JPEG: block buffers whose DQT equals the reference of the model; whose DQT equals the B4 reference at quality 0.9; a model with no reference; no DHT for a model whose reference has none; a DHT with a matching DQT; only decoded image buffers. | `works`; `appears`; `appears` with `no-reference`; `works`; `works` with `dht_added_by_os` true; `no`. |
| T-CERT-55 | 3 OS. Drop rules: no evidence row; a maintainer-accepted row with `b1-empty` `works` and `a6-ep0-device` `works`; a local `full` row with the same results; a row of another OS key. | Each probe runs; B2 except `b2-dmb1`, B4, B5, B6, A7 and A8 do not run and are not in the report; each probe runs (a local row never trims); each probe runs. |
| T-CERT-56 | 3 OS. Wedge and restore: the fake Kiyo Pro gives no frame for 2 s during A5; a fake C922 whose exposure is changed by A1 and by A6; the B5 movie file. | The Kiyo Pro is marked dead: no later probe, no later check (`prior-failure`), no open in phase G, cleanup `camera-wedged`; the C922 values go back through CoreMediaIO after A1 and through endpoint 0 after A6, and phase G reads the "before" values; the `.mov` is gone after B5 and no file name of it is in the report. |
| T-CERT-57 | 3 OS. The plan and the estimate on a fake macOS with one, two and four models. | `seconds_estimate` follows 10.7 and 16 (about 10, 16 and 27 min); no probe row on Windows and Linux. |

## 18. The Linux and macOS capture spec: answers and differences [A]

The agent compared this spec with [ux] draft 2 (commit `d08de113a`): its sections 4.4.10, 4.5,
4.6.2, 4.6.3, 4.6.4, 4.7, 4.9 and 6.7. Draft 2 of [ux] took most names of draft 2 of this spec; this
spec now takes the names of [ux 4.6.2] draft 2 (10.2, 10.3). Question 10 asks the user about the
differences that remain.

### 18.1 Answers to the table "What certify must add or change" [ux 4.6.4]

| # | Item of [ux 4.6.4] | Answer in this spec |
|---|---|---|
| 1 | Codes `previous-process-alive`, `stream-error`, `format-changed`, `process-ended`, `no-manual-exposure` | Applied (15). `process-ended` gives the check reason `crashed` [C 5.3] (10.5). |
| 2 | `call` values | Applied: each name of [ux 4.6.3] (10.2, `<label>:in-use`). |
| 3 | `native_domain` | Applied (10.2). |
| 4 | `access` adds `root` | Applied (10.2). |
| 5 | `control_path` adds `cmio` | Applied (10.2). |
| 6 | `exposure_unit` adds `seconds` | Applied (10.2). |
| 7 | Control keys `c_present`, `c_min`, ... | Applied (2.2, 8.3, 10.2, 10.3, 13). |
| 8 | `auto-off`: drop `awb_off_ok` and `set_while_auto_errno` | Applied: both dropped (10.2). |
| 9 | D-11 after the DHT insertion, by `source_frame_number` | Applied (4.4, 10.3). |
| 10 | `grain_ms`, `jitter_p95_ms` from `frame_log` | Applied (10.2). |
| 11 | `probe:usb-alt` | Dropped; `usb_alt` comes from the diagnostics (10.4). |
| 12 | `control-ep0` as a probe of certify; change 10.1 | Applied, with other names: the endpoint-0 approaches are the probes `probe:<model>:a5-ep0-interface`, `a6-ep0-device`, `a7-device-open`, `a8-iousbhost` of 10.7, not one `probe:control-ep0` (18.2 item 2). |
| 13 | A macOS camera with no manual exposure | Applied: it opens with the warning; `settings-stick` `fail` `no-manual-exposure`; the item is `partial` (3.3 rule 5, 10.2). |
| 14 | `camera-in-use` gives `skipped` with `busy` | Applied (3.3). |
| 15 | `abi` beside the OS key | Applied (2.5, 11.2). |
| 16 | One probe for each macOS approach | Applied: 10.7. |
| 17 | The local pass for each camera model | Applied (11.3). |
| 18 | Read `exposure_found`; wait while `adjusting` | Applied (5.3). |
| 19 | The slow text | No change needed: the sentence of `rate-low` is the product text (15). |
| 20 | No OpenCV fallback inside certify | No change: certify uses the native source only (2.1). |

### 18.2 Differences that remain

| # | Place in [ux] | Difference | This spec | Open |
|---|---|---|---|---|
| 1 | 6.7 (A-21, M-17) | It names `probe:kernel`. The kernel facts are diagnostics keys, so this spec has `system:kernel` (6.2): a probe is only for a fact that the product path cannot see [U: GVC0 item 8]. | `system:kernel` | The name in [ux 6.7]. |
| 2 | 4.4.10, 6.7 (M-15), 4.6.4 | It names one probe `probe:control-ep0`. 10.7 has one probe for each approach, `probe:<model>:<approach>`, run once for each model. | the names of 10.7 | The names in [ux]. |
| 3 | 4.9 | Only a `full` run writes a row of `camera_checks.json`, with each of the five item results. This spec also writes a `quick` row, because the pop-up check of a new model is a quick run and the model then counts as checked [U: KG00 items 3 and 4]; it writes a row only for `pass`, `partial` and `fail`. | 2.5 | [ux 4.9] rule 2 must read `level` `full` (question 9). |
| 4 | 4.6.2 D-4, 4.7 | A failed restore is "logged and recorded", but no key holds it. | requires `restore_ok` and `restore_failed` (10.3) | The keys in [ux 4.6.2]. |
| 5 | 4.6.2 D-2, D-3 | `frame_log` holds 64 rows. `gaps_explain_intervals` needs each long interval of a take of 90 frames or more with its sequence gap. | counts from `frame_log` only | A counter `long_intervals_with_seq_gap` in D-3, or a longer `frame_log`. |
| 6 | 0 | It cites draft 3 of this spec as not committed. Draft 3 is commit `dfde2c8ac` on `dom/certify-spec`. | — | The citation in [ux 0]. |
| 7 | 4.4.10 | It says that the list of the approaches did not exist yet. 10.7 now holds the probes. | 10.7 | The text of [ux 4.4.10]. |

