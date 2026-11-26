# Certify specification: what a certify run of skellycam measures (draft 3)

Status: draft 3 for the user, 2026-11-20; the first code step on 2026-11-21. The code is in
`skellycam/core/certify/`, the tests are in `skellycam/tests/certify/`, and section 19 states the choices of the code
([ADR-VG5F](../decisions/entries/VG5F-choices-of-the-first-certify-code.md) and [ADR-X8XE](../decisions/entries/X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md)). The code builds these checks: `detect`; for each camera `<label>:detect`,
`:detect:mjpg-mode`, `:opens`, `:rate`, `:modes:granted:<base>`, `:native-jpeg:format`, `:native-jpeg:not-reencoded`,
`:native-jpeg:valid`, `:native-jpeg:size`, `:native-jpeg:ring-equals-mkv`, `:native-jpeg:source-equals-ring`,
`:settings-stick:readback`, `:settings-stick:holds`, `:settings-stick:image-effect`, `:records:rows-complete`,
`:records:blocks-decode`, `:records:gaps-explained`, and on Linux and macOS in quick and on each system in full
`:clock:base`, `:clock:before-arrival`, `:clock:near-arrival`, `:sequence`, `:time-gaps`, and `:live-at-close`
(3.6.1, Q646 [ADR-056Z](../decisions/entries/056Z-decisions-of-the-user-on-a-late-camera-failure-the-release-build-file-and-the-open-rows.md)); `group:take:finished`,
`:csv-rows`, `:no-missing`, `:frame-count`, `:rate`; `<model>:units`; in full the roll-up checks
`<model>:gate:<step>` and `<model>:gate` and the check `<model>:gate:no-hang`; the cleanup rows `release:<label>`,
`delete-work-folder` and `write-record`; and `session:exit`. Steps 1 to 4 of 3.6.7 are built [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md): each other
check of this spec is not in `checks`, and `details.not_built` names it: `group:open` with the retry alone (4.2), `self:hang-100ms:gap` and `:hard-end`, the camera block of
`full` (5, 8.2, 10.2), and the group, system and self checks of `full` (6, 7). The checks of a mode above `<base>`
and the macOS probes (10.7) are not in the report yet. On Linux and macOS the native detection is not built:
`detect` is `not-run` `not-built` (the check has code; the product value is missing). The decisions of the user that it builds on are in
[ADR-GVC0](../decisions/entries/GVC0-certify-decisions-of-the-user.md) and
[ADR-KG00](../decisions/entries/KG00-certify-decisions-of-the-user-on-draft-2.md). The choices of the
agent are in [ADR-KY81](../decisions/entries/KY81-certify-spec-choices-of-the-agent.md) (draft 2) and
[ADR-8CP7](../decisions/entries/8CP7-certify-spec-draft-3-choices-of-the-agent.md) (draft 3). Section
14 holds the questions for the user. Section 18 answers the Linux and macOS capture spec and lists the
differences to it. Section 10.7 holds the macOS approach probes.

On 2026-11-23 the user decided the report shape of quick and full (Q591 to Q599,
[ADR-H2A0](../decisions/entries/H2A0-decisions-of-the-user-on-the-certify-report-shape.md); Q608 to Q618,
[ADR-BW5M](../decisions/entries/BW5M-decisions-of-the-user-on-the-two-verdicts-and-the-certify-test-set.md)). Section 3.6 states
it, with the choices of the agent ([ADR-MEE1](../decisions/entries/MEE1-choices-of-the-certify-report-shape.md)).
Steps 1 to 4 of its build order (3.6.7) are built, and the code writes the schema 1.7.0 [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md). The other steps are
not built. The list of built checks above tells what the code gives today. Where an older section and 3.6
differ, 3.6 is the rule.

Draft 3 puts in the decisions of the user of 2026-11-20 on draft 2: the answers C1 to C9 (questions 1
to 9 of draft 2), the "for now" rule of the OpenCV fallback, the check of a camera model one time on a
system, the cancel and progress rules, the order of the full run, the exposure rule of the product,
and "native capture only". It was written against format 1.4.0 of the contract: one test is one
check, a busy camera is `skipped` with `busy`, there is one summary item for each camera model, the
plan has `risks` and `total`, the report has `notices`, and `cameras-busy`, `interrupted` and
`over-budget` are common codes. The cross-spec review of 2026-11-20 and the rulings of the user of
that day ([ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)) are
put in. The spec integration of 2026-11-20 puts in the later rulings of the user ([ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md)), the choices
of the supervisor and of the agent ([ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md)), and the contract change of commit `9e6d575` of
`skellycertify` (the `gate` of a summary item).

Note of 2026-11-25: section 20 is accepted by the user, with the choices of ADR-FR2J (Q813, [ADR-5PAR](../decisions/entries/5PAR-decisions-of-the-user-on-the-control-read-the-holder-and-the-exclusive-access-drafts.md)). It puts in the rule that
skellycam needs exclusive control of each camera ([ADR-AA4X](../decisions/entries/AA4X-decisions-of-the-user-on-exclusive-access-of-a-camera.md)):
`shared` fails `<label>:in-use`, a camera in use at the run start is `not-run` `camera-in-use`, and the new checks
`<label>:in-use:other-program`, `<label>:in-use-mid-take` and `probe:<model>:hog-mode`. It also puts in the public
calls and the progress state that freemocap needs, the light data for `DARK_LUMA`, and the host facts and the
privacy rule ([ADR-13BB](../decisions/entries/13BB-decisions-of-the-user-on-the-dark-rule-the-light-data-and-the-phase-7-items.md),
[ADR-CQ2X](../decisions/entries/CQ2X-decisions-of-the-user-on-the-overlaps-with-freemocap.md)). Section 12 holds
the overlaps with freemocap as settled. Where section 20 and an older section differ, section 20 is the rule.

## 0. How to read this spec

- **The contract** is `report-format.md` of the repository `skellycertify` (sibling folder
  `../skellycertify/`), format `skellycertify.report/1.6.0`, commit `ba9a071` of `main` (read on
  2026-11-21; skellycertify ADR-9FHP), with its `review.md`. The user moved this spec and the code to 1.6.0 on
  2026-11-21 [ADR-X8XE](../decisions/entries/X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md). Format 1.6.0 adds the keyword-only option `abandon` of `certify()` [C 2.4] (9.3), the
  optional field `test_media` [C 3.9] (skellycam uses no test media, so its reports have no such field), the
  field `shared_memory_bytes` of a GPU [C 3.3] (skellycam writes no `gpus`), and the summary group `component`
  with the reason `not-installed` (format 1.5.0 and 1.6.0; skellycam gives no `component` item). The text below
  that cites 1.4.0 stays true in 1.6.0. "[C x.y]" cites section x.y of `report-format.md`. This spec does
  not repeat it. Format 1.3.0 (skellycertify ADR-D1PW) gave the summary results `partial` and
  `skipped` with `busy` and the code `cameras-busy`. Format 1.4.0
  ([ADR-V1TR of skellycertify](https://github.com/domisjustanumber/skellycertify/blob/1c9c1917d8524931ff43ffae52051a529a875a3b/decisions/entries/V1TR-format-1-4-0.md))
  gives one check for each test, the roll-up check, `notices`, the plan fields `risks` and `total`,
  the table of the checks that did not pass, and `over-budget`. Each module report of skellycam had
  the schema `skellycertify.report/1.6.0` until step 2 of 3.6.7; it now has `skellycertify.report/1.7.0`
  (3.6.1). Commit `9e6d575` of `main` (skellycertify ADR-T191 and
  ADR-MM1F, still format 1.4.0) adds the optional `gate` of a summary item [C 3.7], the reviewed row of
  a `partial` item whose `gate` check is `pass` [C 7.2], the forms of `host` [C 3.3] and the privacy
  rules 17 to 20 [C 6]. "[C x.y]" cites that commit.
  Section 3.6 was written against format 1.7.0 (commit `e569c29` of `main`, read on 2026-11-23). The user
  decided that the code writes the schema `skellycertify.report/1.7.0` (3.6.1; built in step 2 of 3.6.7 [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md)). Commit `cf9c7a2` of the contract allows a local unit id of a camera [C 6]. skellycam does not use it
  [U Q595].
- **[cap x.y]** is a section of [`windows-capture.md`](windows-capture.md). **[rec x.y]** is a section
  of [`recorder.md`](recorder.md). **[P §n]** is section n of `research/NATIVE_JPEG_CAPTURE_PLAN.md`.
- **[ux x.y]** is section x.y of [`unix-capture.md`](unix-capture.md). It owns the diagnostics keys
  and the failure codes. Section 18 answers its section 4.6.4.
- **[req x.y]** is section x.y of [`camera-requests.md`](camera-requests.md). It owns the exposure
  search, its states, its names and its limits, the 60 fps fall back and the USB link lookup. This
  spec owns the check names and the local record `camera_checks.json`.
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
  cameras=None, recording_folder=None, test_media_dir=None, abandon=None)` and `skellycam.certify_plan(level, *,
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
| Probe child | A probe of section 10.4: a fact that the product path cannot see. A camera probe (10.7) opens one camera, with the product session closed for that camera. | Open a camera that hung or is dead; claim, detach or seize a device; write outside the work folder. |

The caller also reads and writes the local record `camera_checks.json` (2.5) in the skellycam base
folder. It opens no camera for this.

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
| SkellyCam Auto | An apply with `exposure_mode` `AUTO` (`RECOMMEND` reads as `AUTO` [req 1.5]); the status `exposure_search` |
| A take | `CameraGroup.start_recording`, `stop_recording`, `TakeSummary`; the files of rec 6 |
| File checks | `sidecar.read_strict`, the manifest, `stop_stats.stop_response_fields` |
| Frames | `FrameRingReader` of the JPEG ring; `cv2.imdecode` in memory (`IMREAD_REDUCED_GRAYSCALE_8` for the brightness) |
| Source facts | The full `diagnostics` dict from `CameraGroupManager.diagnostics()`, with the keys of [ux 4.6.2] (section 10.3, [ux 4.2 item 2]) |
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
| C. Identity, modes, rates | full | One camera at a time: `<label>:identity:*`, `<label>:controls`, `<label>:controls:exposure-scale`, and the 30 fps rate checks of 5.2 with their `<label>:modes:granted:<mode>`. On macOS also the safe JPEG probes of 10.7 (steps 1 to 3). |
| D. Long sweeps | full | One camera at a time: the exposure sweep at `<base>`, SkellyCam Auto, the control sets of 5.4, `<label>:auto-off:*` (10.2). On macOS also the safe probes of 10.7 (steps 4 to 6). |
| E. Group, system, self-checks | full; quick: `self:hang-100ms` only, when the budget allows (4.1) [U] | Section 6: the group take at 30 fps, the contention, the disk check, the disk benchmark, the system facts. Section 7: the self-checks. They use fake cameras and do not touch a real camera. |
| F. Risky checks | full | Section 8, in order of rising risk: the in-use check, the 60 fps modes, the sweeps and the Auto search at 60, the group take at 60 fps, the open and close cycles, and on macOS the endpoint-0 and device-open probes of 10.7 (steps 7 to 9), last. |
| G. Re-check | both | Section 8.3. Quick: the state of each camera comes from the restore of its last close. Full: a plain open of each camera that did not hang. The phase runs also after a crash of an earlier phase. After a cancel it re-checks only the cameras that the run touched, at most 5 s each, and it gives only cleanup rows (8.3). |
| G2. USB 3 trial | full, macOS and Linux | `<label>:usb3-trial` of 3.6.13: each method, the request to the camera last, then a new listing [U Q629]. |
| H. Cleanup and record | both | Section 9.5; the record of checked models (2.5). Then the report. |

The user accepts a full run of skellycam of 6 to 11 minutes [U]. Section 16 gives the estimates.

A camera that hung, crashed its camera process or was removed is never opened again in that run
[U: the Kiyo Pro wedge rule, cap 8.2]. Its later checks are `not-run` with `prior-failure`, and phase G
gives it the state `replug` (8.3).

### 2.4 Package options [A]

| Option | Default | Meaning |
|---|---|---|
| `cameras` | `None` (each real camera) | A list of labels of section 3.1. Only these cameras are checked. A run of a part of the cameras is complete for each camera that it checks, so it is not `partial-run`. The run lists the cameras with no activation first and reads the modes only of these cameras, so a camera that the list leaves out is never activated (3.6.6 item 9) [U Q627, MEE1 25]. |
| `test_media_dir` | `None` | The shared test media folder of the app [C 2.8]. Both functions accept it. skellycam needs no test media: the full level makes its synthetic frames. Thus skellycam reads and writes nothing in this folder [A]. The disk checks write in the work folder inside `recording_folder`, because the user decided that the benchmark runs in the recording folder [U]. |
| `long_take` | `False` | `full` only: add the take of 5 minutes of 3.6.11 [U Q618]. |
| `recording_folder` | `None` (the temporary folder of the system) | The folder where the person records. The app passes its data folder. The quick take, the disk check and the disk benchmark write in a new work folder inside it, and certify deletes it (9.5). No path is in the report. |

The record of checked models (2.5) does not change which cameras `certify()` checks. Without the
option `cameras`, a run checks each detected real camera, also a camera of a model that is already
checked [A].

### 2.5 Checked camera models and the local record [U, A]

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
- A new OS version makes each model unchecked again [U]
  ([ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)).

This spec owns the local record. The details [A]:

- **The file.** `camera_checks.json` in the skellycam base folder
  (`get_default_skellycam_base_folder_path()`). It holds the checked models and the local pass of
  11.3. The local certify reports are in the same folder. The contract allows a package to record its
  own results in its own store [C 2.5]. This file is not in the work folder, and certify never
  deletes it.
- **The key of a row.** The USB id `vvvv:pppp`, the backend (3.1), the ABI (`lp64`, `ilp32`) and the
  OS key of 11.2, and the level. A camera with no USB ids has `device` `nousb:<raw name>`, with the raw OS
  display name [U Q627, DBF8 15, review]. The local record never leaves the system and is never in a report, so the raw name
  can stand there; the fixed `Camera (no USB id)` would put each such model in one row.
  A newer row for the same key replaces the older one. A `quick` row marks the model as checked; a
  `full` row also gives the local pass of 11.3.
- **The container** [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md). The file is one JSON object `{"format": 1, "rows": [ ... ]}`, with
  one object of the form below for each row. A missing file or a file that cannot be read means "no
  rows". The reader logs that one time; it never raises for the file.
- **A row.**

  ```json
  {"device": "046d:085c", "backend": "v4l2", "os_key": "7.0", "abi": "lp64", "level": "full",
   "item": "partial", "skellycam": "2.0.0a6", "date": "2026-11-20",
   "gate": {"opens": "pass", "mode": "pass", "rate": "pass", "native-jpeg": "pass",
            "timestamps": "pass", "sequence": "pass", "records": "pass", "no-hang": "pass"},
   "controls": {"exposure": {"v4l2": "works"},
                "gain": {"v4l2": "unproven"},
                "focus": {"v4l2": "no"}}}
  ```

  - `item` is the summary item of the model (3.4). It plays no part in the turn-on rule [U].
  - `gate` holds the result of each roll-up check of the gate of 11.3 (`pass`, `fail` or `not-run`),
    for a `full` row only. The step roll-up rows leave the report (3.6.2) [U Q597], but the record keeps the step
    values: certify computes them from the required checks. Until the sign-off checks are built, `gate` also holds
    `"sign-off": "not-built"`, so the row is no local pass (3.6.4) [U Q610].
  - A run also writes one row with `device` `"pipeline"` for the pipeline item (3.6.10) [U Q611].
  - `control_read` (a `full` row only): `ok` or `harms`, the result of `<label>:control-read:gaps` (20.9, Q811). With
    `harms`, the product pauses its one-second control read during a take for that model [cap 21.6].
  - `controls` holds, for each of exposure, gain and focus, the result of each route that the run
    tried, keyed by its `control_path` value of 10.2 (`v4l2`, `iam`, `ks`, `cmio-native`,
    `cmio-absolute`, `cmio-native-data`) [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md):
    - The route that the product used in the run gets the result of its checks: for exposure
      `settings-stick:readback`, `settings-stick:holds` and `settings-stick:image-effect`; for gain
      `control:gain`; for focus `control:focus`.
    - On macOS each other route gets the result of its probe of 10.7 for that control.
    - `works`: the read-back, the hold and the image check passed. `unproven`: the read-back and the
      hold passed, and the image check is `not-run` (for example `too-dark`), or not in the level: quick has no
      image check (Q593), so a quick row gives `unproven` at most [U Q627, MEE1 20]. `no`: a check failed.
      A route whose checks did not run for another reason (`not-applicable`, `prior-failure`) is
      left out.
    - The product chooses the route of the local row first: a route whose result is `works` in the
      local row of the model wins [ux 4.4.6]. Else it chooses among the routes whose result is
      `works` in the shipped file; when several work, the one that works on the most models of the
      shipped file; with no `works` route, an `unproven` route by the
      same rule. An `unproven` control is offered in the UI. Only a control whose routes are all `no`
      is absent [U] [ux 4.4.6, 4.9].
  - Certify never applies the record to itself: in a certify run, each control is tried again,
    whatever the record says [ux 4.4.6] [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md).
  - A row holds no serial number, no path and no `camera_id`.
- **A skellycam upgrade.** It does not make a row stale [A, question 2]. Only a new OS key, a new ABI
  or another backend makes a new key. The field `skellycam` records the version for a later rule.
- **When a model counts as checked.** At the end of a run (also after a cancel), certify writes one
  row for each model whose summary item ended `pass` or `fail`, and for each model whose item ended
  `partial` with at least one unit whose `<label>:opens` is `pass` or `fail`. An item `skipped`
  (busy), and a `partial` item where no unit judged `opens` (cancelled, over budget, no access),
  write nothing, so the app checks that model again at its next open. An interrupted run writes
  nothing [A] [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md).
- **A reviewed model.** A model with a `verified` row in the shipped file for this OS key, backend
  and ABI (11.2) has a reviewed pass. The quick run does not check it: its summary item is `skipped`
  with the reason `reviewed` [C 2.7], and it counts as checked. It gets no pop-up.
- **A failed model.** The app does not check it again at each open. The person can run certify from
  the certify page of the app at any time.
- **A damaged file.** A file that does not parse, or a row with a missing field, counts as no row.
  Certify then writes a new file. It never raises for the file.
- **The plan.** `certify_plan("quick")` and `certify_plan("full")` give `details.cameras[].checked`
  for each detected camera and `details.unchecked`: one item `{label, name, device}` for each model
  that is not checked and not reviewed, with the label of the first camera of that model (9.1).
- **The pop-up flow of freemocap.** freemocap closes its camera groups [U], then calls
  `certify("quick", cameras=[<labels of details.unchecked>])`, then opens the cameras. A run of a part
  of the cameras is complete for each camera that it checks (2.4), so the report can count as a local
  quick pass [C 7.2]. A quick row never turns on native capture (11.3): on Linux and macOS the model
  then stays on OpenCV until a full run passes; the pop-up only stops the next pop-up.
- **No camera.** `detect` passes with `cameras` 0. Each check that needs a camera is `not-run` with
  `no-camera`. No check is `fail`. The summary has no `camera` item, so the camera part of the report
  reads `Cameras: not checked on this system.` [C 3.7, C 4.2 part 6]. Certify writes no row.

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
| `<model>:units` | `<model>` is `cam.<backend>.<vid>-<pid>`: the count of units of the model (3.4). Removed by 3.6.2 [U Q591 to Q599]: `details.cameras` holds the units. `<model>` stays the prefix of the gate checks. |
| `<label>:not-reached` | One `not-run` row in place of the rows of a camera that could not go on (3.6.1) [U Q592]. |
| `<label>:<group>:<condition>` | One condition of a group of checks of the camera (3.3, 3.4), for example `<label>:native-jpeg:valid`. |
| `<label>:<check>[:<mode>]` | Another check of the camera. `<mode>` is `<w>x<h>@<rate>`, with the rate rounded as cap 7.3 rounds it: `1280x720@30`, `1920x1080@30`, `1280x720@60`, `640x480@29.97`. |
| `detect` | The detection. |
| `player-legacy-decode` | The decode check of the v1 player (3.6.2; [`player-legacy.md`](player-legacy.md) 10.5) [U Q735, Q766, Q803]. |
| `group:<check>`, `system:<check>` | A check of the cameras together; a fact or a check of the system. |
| `self:<check>` | A self-check with fake cameras (section 7). It never counts toward a camera item [U]. |
| `probe:<check>`, `probe:<model>:<approach>[:<control>]` | A probe of 10.4: code of certify, outside the product path. |
| `<name>:exit` | The `exit` check of the contract [C 2.5]. |
| cleanup `release:<label>` | Phase G: a camera that is not healthy after the run (8.3). |

Each name matches `^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$` [C 3.4]. The longest forms,
`cam.media-foundation.nousb-nousb.9:auto-exposure:holds-rate:1920x1080@29.97` (75 characters) and
`probe:cam.avfoundation.nousb-nousb:a3-cmio-native-data:white-balance` (68 characters), are within
the limit. The report has no
sections: the table `Checks that did not pass:` then names each check, with its `module` [C 4.2 part
7].

`module` [C 3.4] [A]: each camera check has the `name` of the summary item of its model. Each probe
check `probe:<model>:...` of 10.7 has the `module` `macOS probes`, so that the rows of the probes
that did not pass stand apart from the checks of a camera model [ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md). The checks `system:disk` and
`system:disk-benchmark` have `Disk`. The other checks have no `module`. The two verdicts of 3.6.10 [U Q611]
change this: each system check, and each pipeline check that the rule of 3.6.10 does not give to a model, has
`module` = the name of the pipeline item; `Disk` goes, because the contract needs a `module` equal to the `name`
of a summary item [C 3.4].

### 3.2 Numbers [A]

`numbers` is flat [C 3.4]: a number, a boolean, `null`, a reason code, a list of reason codes, or a
string from a fixed vocabulary of `skellycam/REASON_CODES.md`. A list of numbers is not allowed. Thus
a sweep gives one key for each step, for example `fps_at_m7` for exposure -7 (`m` for minus).

### 3.3 One test, one row [U]

The user decided: "each test must have it's own row, so a test either passes or fails so it's clear
what exactly failed." [U] ([ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md))
Thus:

- Each check is one test with one pass rule. A check whose pass rule has two or more conditions is
  split: one check for each condition, named `<group>:<condition>`.
- A check is `pass` or `fail` when it judged. A test that could not run is `not-run` with a reason,
  for example `too-dark`, `no-mode` or `prior-check-failed`. It is never `record-only` [U].
- `record-only` is only for a check that records facts and has no pass rule (for example
  `<label>:timings` and the sweeps; `<label>:detect` and `<model>:units` go in 3.6.2).
- No check carries an outcome in `numbers`. The row check `<label>` and the reason code `partial` of
  draft 3 are gone.
- The contract states the same rule: one test, one check; a check has one result and is never
  `partial`; `partial` is a result of a summary item only [C 3.4, C 3.7].
- A roll-up check runs no test of its own. It is `pass` only when each check that it requires is
  `pass` [C 3.4]. This spec names the checks that each roll-up check requires (11.3). A roll-up check
  that is not `pass` is `fail` with `gate-check-failed` when a required check is `fail`, else
  `not-run` with `gate-check-not-run` [C 3.4: a reason for each `fail` and `not-run`] [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md).
  `details.gates` names the first required check that did not pass (3.6.3) [U Q597].

### 3.4 The check groups of a camera, and the summary item [U, C 3.7]

The user asked: "Quick test must include applying settings and if they stick or not, can you jpegs
... This might necessitate a "partial" result in the summary table." [U] He accepted the result
`partial`, and the meaning of "can you jpegs": the camera's own JPEG frames, passed through unchanged
in the capture path of the product (MJPG passthrough, no decode and no re-encode) [U]. In the session
of the contract he said: "in-use shouldn't be it's own status here just for cameras. skipped (busy)
will do for both" [U, as the contract reports it].

**The five groups.** Each real camera has these checks [A]. The column "Level" is the decision of the user of
2026-11-23 [U Q593]: quick is a smoke test, and six checks of each camera move to full (3.6.2).

| Group | Checks | Level | Section |
|---|---|---|---|
| Open | `<label>:opens` | both | 4.2 |
| Rate | `<label>:rate`, `<label>:modes:granted:<base>` | both | 4.2 |
| Settings stick | `<label>:settings-stick:readback`, `<label>:settings-stick:holds` | both | 4.3 |
| | `<label>:settings-stick:image-effect` | full | 4.3 |
| Native JPEG | `<label>:native-jpeg:format`, `:native-jpeg:valid` | both | 4.4 |
| | `:native-jpeg:not-reencoded`, `:native-jpeg:size`, `:native-jpeg:ring-equals-mkv`, `:native-jpeg:source-equals-ring` | full | 4.4 |
| Records | `<label>:records:rows-complete`, `:records:blocks-decode` | both | 4.5 |
| | `:records:gaps-explained` | full | 4.5 |

On Linux and macOS, quick also has `<label>:clock:base`, `<label>:clock:before-arrival`,
`<label>:clock:near-arrival` and `<label>:sequence` (10.6). Where the source gives no sequence number,
`<label>:time-gaps` takes the place of `<label>:sequence` in the groups of the item, and
`<label>:sequence` stays in the report as `not-run` with `no-sequence` (10.2).

`<base>` is `1280x720@30`. A camera with no 1280x720 MJPG mode at the floor uses the largest MJPG
size below 1280x720 in area that has a rate at the floor, for example `640x480@30` [A].

**The summary item of a model** [C 3.7]. The summary has one `camera` item for each camera model on
the system (the USB vendor id and product id), not for each unit. `name` is the cleaned name (9.4,
1 to 80 characters), `device` is `vvvv:pppp` (`null` with no USB ids). Certify computes the item from
the checks of the groups above that the level has, of all units of the model. No check holds the item. The user decided
the rule [ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md). The first rule that applies gives the item:

1. `skipped`, reason `busy`: each unit is held by another program (`<label>:opens` of each unit is
   `not-run` with `camera-in-use`).
2. `fail`: an open, rate or recording check (the groups Open, Rate or Records) of a unit that is not
   busy is `fail`.
3. `pass`: each check of the groups (on Linux and macOS also `clock` and `sequence` or `time-gaps`) of
   each unit is `pass`, and no unit is busy.
4. `partial`: each other case. Examples: a settings or JPEG check failed; a check could not run
   (`too-dark`, `no-manual-exposure`, `over-budget`, `cancelled`); one unit is busy and one passed.
   This is the `partial` of [C 3.7]: "some checks of the item passed. Other checks could not run, or
   failed in a way that is not fatal."

The table `Checks that did not pass:` of the report lists each `fail` check, and each `not-run` check
whose `module` equals the `name` of a `partial` or `fail` item [C 4.2 part 7]. Thus a `partial` item
shows each check that kept it from `pass`.

With the two verdicts of 3.6.10 [U Q611], the four rules apply to the checks whose `module` is the name of the
model; a pipeline check that 3.6.10 gives to the pipeline does not change a model item.

A check of a `full` camera block (a declared mode at 1080p or 60 that does not deliver, a control
check, a probe) never changes the item: it is its own row [U]. The item also does not decide native
capture: 11.3 names the checks that do [U].

The check `<model>:units` is removed (3.6.2) [U Q591 to Q599]: `details.cameras` has one item for each unit,
with its verdict (3.6.3). Each check
of a camera has `module` = the `name` of its summary item [C 3.4], so that the table of the failed
checks names the camera [C 4.2 part 7].

- A `camera` item of a `full` report has the field `gate`: the name of the roll-up check
  `<model>:gate` of 11.3 [C 3.7]. A `quick` report has no gate, so its items leave the field out (not
  `null`). The `gate` does not change the result of the item: a `partial` item stays `partial`.
- A `skipped` item never gives a reviewed row. A `partial` item gives a reviewed row only when its
  `gate` check is `pass` [C 7.2] (11.5).
- With no camera detected, the summary has no `camera` item [C 3.7]. The Markdown then shows
  `Cameras: not checked on this system.` [C 4.2 part 6]. This is the "not checked" of the user [U].

A virtual camera gets no check and no summary item [A]. `detect` records the count (`virtual`, Q624b).
The app shows it but cannot select it [U].

### 3.5 Report fields that say why a check failed [U]

A person that we do not know runs certify, and a developer with no access to that system reads the
report. The report must tell the developer why a check failed, not only which check failed. On
2026-11-23 the user decided [U] ([ADR-F6C3](../decisions/entries/F6C3-decisions-of-the-user-on-the-certify-report-fields.md)):

- Q557: the report gets eight additions: (1) the commit and the tree state; (2) the failure facts of
  the product on each failed or hung camera row; (3) a start time and a duration for each check; (4) a
  camera inventory; (5) frame timing on each row that measures a rate, on each operating system; (6)
  the warning codes of the take, the position of the first gap and the exit codes; (7) the CPU load
  during the open and the take; (8) the exposure and gain context on the settings rows.
- Q558: a salted local hash is a stable id of a camera unit (3.5.10). The `camera_id` stays forbidden
  in a report.
- Q559: certify keeps the camera logs of the last run on the system of the person (3.5.11). Certify
  never sends them.

The names, the places, the vocabularies and the bounds of this section are choices of the agent
([ADR-NQ77](../decisions/entries/NQ77-choices-of-the-certify-report-fields.md)). The user accepted them
as a set on 2026-11-23 [U Q572]
([ADR-10HT](../decisions/entries/10HT-acceptance-of-the-certify-report-field-choices-and-the-build-order.md)).
"[U Q572]" marks them in this section. Of this section,
only 3.5.2 and the failure facts of a B1 row of 3.6.1 are built [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md). Each field fits format 1.6.0 and format 1.7.0 of the contract as they are:
flat values in `numbers` [C 3.4], structured values in the module `details` [C 3.1]. No field needs a
`details` object on a check, a list of numbers in `numbers`, or an attached file.

**The slim form [U Q594, Q595].** On 2026-11-23, before the build, the user changed this section
([ADR-H2A0](../decisions/entries/H2A0-decisions-of-the-user-on-the-certify-report-shape.md)):

- The time and the CPU stand one time for each step in `details.steps[]`, not on each row (3.6.3).
- A key of a failure fact is in the row only when it has a value (3.5.3).
- These keys are dropped as noise: `failed_calls`, `window_frames`, `interval_p95_ms` and `exposure` of the rate
  row, `grid_16ms_share`, `grain_ms`, `has_serial`.
- There is no unit id: `unit_id`, `unit_ids_new` and the key file `certify_unit_key` are removed (3.5.10).
- Each number stands on one row only. A limit stands one time in `details.limits`. The exposure range and the
  "before" values stand in `details.cameras` [U Q627, MEE1 14] ([ADR-MEE1](../decisions/entries/MEE1-choices-of-the-certify-report-shape.md)).

The tables below give the slim form. A text in a table that names a removed key or another place is replaced by
the bullets above and by 3.6.

#### 3.5.1 Common rules [U Q572, Q573]

- **Source marks.** The column "Source" of each table says where the value comes from: **run time**
  (the product or certify has the value today), **small code** (a small change of certify or of the
  product; 3.5.15 gives the order) or **new** (a new measurement).
- **One name for one fact.** A key of this section has the same name in each place. A number that
  comes straight from a diagnostics key has the name of that key (10.2). The exceptions are the keys
  of the rate window (3.5.6), which have one report name for each window, and the reads at -7 and -8
  (`_at_m7`, `_at_m8`, as `luma_at_m7`).
- **No free text.** Each string value is from the closed vocabulary of its row, or matches the pattern
  of its row. The failure text of the product is never copied (9.4).
- **`null` and absent.** `null` means that the value is not known. "Absent" means that the key is not
  in the object.
- **A row from a step.** A row from a step is a check whose result a step of the run gave: `pass`,
  `fail`, `record-only`, or `not-run` with a reason that the session gave from a measurement (for
  example `too-dark`, `camera-in-use`, `no-manual-exposure`, `ring-lapped`). A **filled row** is a
  `not-run` row that the caller writes because no step reached the check (`not-built`, `same-model`,
  `prior-failure`, `prior-check-failed`, `cancelled`, `over-budget`, `cameras-busy`, `interrupted`). A
  filled row has no key of this section. In the slim form, a check with no code and a `same-model` check give no
  row, and the filled rows of one camera become one row `<label>:not-reached` (3.6.1) [U Q591, Q592].
- **The run clock.** `t0` is `time.perf_counter_ns()` of the caller at the start of the `certify()`
  call. The session child gets `t0`. Each key that ends in `_at_s`, and `t_start_s` of `details.steps`, counts seconds
  from `t0`. `perf_counter_ns` is one clock for all the processes of a system: the product already
  compares the `arrival_ns` of different camera processes (the spread of 4.5).
- **A counter in a window.** On a row that measures a window, a D-3 counter (`long_intervals`,
  `long_intervals_with_seq_gap`, `discontinuity_flags`, `sequence_gaps`, `sequence_lost`,
  `drops_reported`, `zero_bytes`, `error_flag_frames`, `format_changes`, `frames`) is the change of
  that counter in the window, not the count since the open. The window of the `records`, `clock`,
  `sequence` and `time-gaps` rows is the take window: from the read before the record start to the
  read after the stop, as for `replaced` (4.5). The pass rules of 10.2 do not change: `time-gaps`
  passes when `long_intervals` is 0, and `sequence` passes when `long_intervals` equals
  `long_intervals_with_seq_gap`.
- **One number, one row [U Q594, A].** Today the three `settings-stick` rows, the three `records` rows and the
  five `group:take` rows each share one `numbers` object. In the slim form no `numbers` object repeats another:
  each key stands on the one row whose rule reads it, and 3.6.2 names that row. A `pass` row has `numbers` only
  when it measured something; it does not repeat the request.
- **`seconds`.** A row has no `seconds` in the slim form: the time of each step is in `details.steps` (3.5.4)
  [U Q594]. Another time that a table of this spec calls `seconds` keeps its own name: the length of the take is
  `take_seconds` (4.5), and the write time of the disk benchmark is `write_seconds` (6.2).

The names that the analysis of 2026-11-21 proposed and that this section changes:

| Proposed name | Name here | Reason |
|---|---|---|
| `first_code` | `first_fail_code` | It is a new diagnostics key (D-5), and the D-5 keys of a failure start with `fail_`; the report uses the key name (10.2). |
| `fail_stage` | `stage` | `opens` has had `stage` since the first code. The diagnostics `fail_stage` says `close` for a hang in the close after a failed open, so it would differ from the stage of the failure object. |
| `cpu_total_p95`, `cpu_tree_p95` | `cpu_share_p95`, `cpu_cores_used` | 6.1 already lists these names for the group take. |
| `t_open_ms` and the other `t_*_ms` on `opens` | not copied | They belong to `<label>:timings` (5.5); a failed open has `stage`, `call` and the times of 3.5.4. |
| `details.cameras.<label>` (an object keyed by label) | `details.cameras` (a list of objects with `label`) | The plan (9.1) has `details.cameras` as a list of objects with `label`. The same name keeps the same form. |
| `driver_provider` | `driver_kind` | The provider is free text. `driver_kind` is a closed vocabulary. |

#### 3.5.2 Addition 1: the commit and the tree state [U Q557]

| Key | Place | Type and values | Present (else) | Example | Source | Privacy |
|---|---|---|---|---|---|---|
| `package.commit` | `package` [C 3.2] | 40 lower-case hex digits, or `null` | always; `null` when the package has no valid build file | `"0123456789abcdef0123456789abcdef01234567"` | small code: each build writes `skellycam/build_info.json` (the bullets below), `{"commit": "<40 hex>", "tree_modified": <bool>}`, from git at build time; certify reads it; no git at run time [C 2.5] | a commit of the public repository; no rule applies |
| `package.tree_modified` | `package` [C 3.2] | `true`, `false`, `null` | always; `null` with no valid build file | `false` | small code: the same file; `true` when `git status --porcelain` was not empty at build time | none |

- A build file that does not parse, or that has another form, counts as no file.
- Each build carries the file [U Q647] [ADR-056Z](../decisions/entries/056Z-decisions-of-the-user-on-a-late-camera-failure-the-release-build-file-and-the-open-rows.md). A wheel from a checkout writes it from git. The sdist carries it,
  and a wheel built from the sdist copies it. The installer build of CI writes it from git before a step changes
  the tree, and `skellycam.spec` puts it into `datas`. Only a source root that is the top of its git work tree
  gives a commit; a source tree inside another repository gives none [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md). An error of git gives no commit and
  never fails the build.
- A run from a source checkout (a `.git` folder or file beside the package folder, as in an editable install)
  ignores the build file and writes `null` and `null` [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) item 17: no build made it, and it can be stale.
- With a valid commit, `evidence.reasons` has no `no-commit`. With `tree_modified` `false`, it has no
  `modified-tree` [C 7.1]. The code must stop to add the two codes in all cases (today `run.py` adds them to each
  report). It adds `no-commit` only when `commit` is `null` or not 40 hex digits, and `modified-tree` only when
  `tree_modified` is not `false`. These are the common codes of [C 5.3], with their meaning there.
- Build order: this addition is step 1 of 3.6.7, with the fix of B1 (3.6.1). The order of 3.6.7 differs from
  Q575; the user agreed to it (Q626).
- Size: about 80 bytes more than today.

#### 3.5.3 Addition 2: the failure facts [U Q557]

A **failure row** is a camera row (`<label>:...`) from a step whose reason is a failure code of the
product [ux 4.6.3] (also `rate-low`, `rate-high`, `not-ready`, `first-frame-timeout`, `hung`), or
`crashed` that comes from `process-ended` (10.5), or `not-run` with `camera-in-use`. The B1 row of 3.6.1 is a
failure row too. A failure row has each key of this table that has a value [U Q594]. No other row has these keys,
with one exception: each row with the reason `crashed` has `exit_code`, also `null` when it is not known [C 2.5]
[U Q627, MEE1 11]. The values come from the newest diagnostics dict of the camera (`CameraGroupManager.diagnostics()`, live or
closed), read after the failure, and from the failure object of the camera status (cap 12).

| Key | Place | Type and values | Present (else absent) | Example | Source | Privacy |
|---|---|---|---|---|---|---|
| `native_code` | `numbers` | integer: the HRESULT (unsigned 32 bit), the errno, the NSError code, the OSStatus or the IOReturn | a failure row whose failure had a native code | `2147942405` (0x80070005, `E_ACCESSDENIED`) | run time: D-5 `native_code`; small code: the source keeps the native code of the first failure that had one (3.5.15 P2) | a code of the OS |
| `native_domain` | `numbers` | `hresult`, `errno`, `nserror`, `osstatus`, `ioreturn` | only beside `native_code` | `"hresult"` | run time: D-5 | closed name |
| `call` | `numbers` | a call name of [ux 4.6.3], with `reader-release`, `control-release` and `set-controls` (3.5.15 P1) | a failure row where a bounded call failed or hung | `"reader-release"` | run time: D-5 `call`; small code for the three new names | closed name |
| `stage` | `numbers` | a stage of cap 12 with `-` for each space: `detection`, `open`, `set-mode`, `start-stream`, `first-frame`, `set-controls`, `warm-up`, `rate-check`, `streaming`, `close`, `recording` | a failure row whose failure object has a stage; never on a `pass` row | `"first-frame"` | run time: `stage` of the failure object of the status | closed name |
| `first_fail_code` | `numbers` | a failure code of [ux 4.6.3] | a failure row whose first failure code differs from its reason | `"first-frame-timeout"` | small code: new D-5 key (3.5.15 P2) | closed name |
| `exit_code` | `numbers` | integer: the exit code of the camera process, of the session child or of the detection child (on Windows unsigned 32 bit, for example `3221225477` for 0xC0000005); `null` only on a `crashed` row | each row with the reason `crashed` [C 2.5]; a failure row with the reason `hung` when the hard end gave a code | `1` | small code: the main process puts the exit code of a camera process that ended into the kept diagnostics (D-5 `exit_code`, 3.5.15 P4); the session child and the detection child: the exit code of `multiprocessing` (run time) | number |

- `failed_calls` is dropped [U Q594].
- A failure row of a `rate` check has the failure keys only when they have a value. Usually it has none: its
  reason `rate-low` and the rate numbers of 3.5.6 say what failed.
- Size: about 30 to 150 bytes on each failure row. Other rows: none.

#### 3.5.4 Addition 3: the time of each step [U Q557, Q594]

The user decided [U Q594]: the time and the CPU stand one time for each step, in `details.steps[]` (3.6.3), not
on each row. A row has no `t_start_s` and no `seconds`.

| Key | Place | Type and values | Present (else) | Example | Source | Privacy |
|---|---|---|---|---|---|---|
| `step` | item of `details.steps` | a step name of 3.6.3 | always | `"open"` | small code | closed name |
| `t_start_s` | item of `details.steps` | seconds from `t0`, 2 decimals, 0 or more: the progress message of the first check of the step (9.6) | always | `1.02` | small code: the caller reads the run clock when it sends that message | number |
| `seconds` | item of `details.steps` | seconds, 2 decimals, 0 or more: from `t_start_s` to the result of the last check of the step | always; `null` when the step did not end | `12.31` | small code | number |

- A developer can order the failures of different cameras in time by the step of each failed check and by the
  `_at_s` keys of 3.5.6.
- Size: about 60 bytes for each step, about 0.5 kB for a run.

#### 3.5.5 Addition 4: the camera inventory [U Q557]

`details.cameras` is a list with one object for each unit of the run (each unit that the run checks,
also a busy unit), in the detection order. 3.6.3 adds the verdict keys (`result`, `failed`, `reason`), the name
keys of 9.4 and the exposure facts of 3.5.9. The module `details` also gets `cpu_logical` (3.5.8) and
`logs_kept` (3.5.11).

| Key | Place | Type and values | Present (else) | Example | Source | Privacy |
|---|---|---|---|---|---|---|
| `label` | item | the label of 3.1 | always | `"cam.media-foundation.1532-0e05.0"` | run time | model and detection order only |
| `usb_link` | item | `USB 1`, `USB 2`, `USB 3`, `unknown` [req 3.2] | always | `"USB 3"` | run time in the product: `usb_connection.usb_link(path)`; small code: certify calls it after the detection, with a limit of 2 s for each camera (`unknown` at the limit) | closed name |
| `bcd_usb` | item | 4 lower-case hex digits: `bcdUSB` of the device descriptor (the USB version that the camera declares); or `null` | each system where the lookup is built (Windows first); `null` when not known | `"0320"` | small code: offset 6 of the `USB_NODE_CONNECTION_INFORMATION_EX` buffer that `_windows_usb_link` already reads; Linux: sysfs `version`; macOS: IORegistry `bcdUSB` [NV] | a model fact |
| `bcd_device` | item | 4 lower-case hex digits: `bcdDevice` (the firmware revision); or `null` | as `bcd_usb` | `"0105"` | small code: offset 16 of the same buffer; Linux: sysfs `bcdDevice`; macOS: IORegistry `bcdDevice` [NV] | a model and firmware fact |
| `controller` | item | integer, 0 or more: the index of the USB host controller in this report, in the order in which the units of the run first name it; or `null` | as `bcd_usb` | `0` | small code: the `CM_Get_Parent` walk of `_windows_usb_link`, on from the hub to the host controller; Linux: the PCI parent of the USB bus in sysfs; macOS: the parent chain of the IOUSBHostDevice [NV] | anonymous index; never an instance id or a location path |
| `controller_id` | item | `vvvv:dddd`, lower-case hex: the PCI vendor id and device id of the host controller; or `null` (not PCI, or not known) | as `bcd_usb` | `"8086:7ae0"` | small code: `VEN_` and `DEV_` of the hardware id; certify keeps only these two values | PCI ids are allowed facts [C 6]; never a bus address (rule 3) |
| `hub_depth` | item | integer, 0 or more: the hubs between the root port and the camera (0 is a root port); or `null` | as `bcd_usb` | `1` | small code: the count of hubs that the same walk passes, without the root hub | count; no port number, no hub chain |
| `driver_kind` | item | `uvc-inbox` (Windows `usbvideo.inf`; Linux `uvcvideo`), `inbox-other` (another INF that Windows ships), `third-party` (an `oem<n>.inf`), `unknown`; or `null` | Windows; Linux when its detection is built; `null` on macOS | `"uvc-inbox"` | small code: cfgmgr32 `DEVPKEY_Device_DriverInfPath` of the camera device; Linux: the diagnostics key `driver` | closed name; no provider name |
| `driver_version` | item | 1 to 4 integers with dots, at most 40 characters; or `null` | Windows; `null` elsewhere | `"10.0.26100.1150"` | small code: `DEVPKEY_Device_DriverVersion` | a version |
| `modes` | item | a list of at most 32 strings, each at most 48 characters, of the pattern `^(MJPG\|YUY2\|NV12) [1-9][0-9]{1,4}x[1-9][0-9]{1,4}@[0-9.]+(,[0-9.]+)*$`; the rates as 3.1 rounds them; ordered by area, then by format; `[]` when the modes were not read | always | `["MJPG 1280x720@30,60", "MJPG 1920x1080@30,60"]` | run time: `supported_modes` of the detection (MJPG at the floor; after 3c `capture_modes` with each format) | model facts |
| `modes_cut` | item | integer, 1 or more: the count of modes that the bound of 3.6.5 cut | only when the bound cut a mode | `3` | small code | count |
| `sample_time_kept` | item | `true`, `false`, `null` | each unit that opened | `true` | run time: D-2 | boolean |

- `unit_id`, `unit_ids_new` and `has_serial` are removed [U Q594, Q595].
- `modes` replaces the numbers of `<label>:detect` (3.6.2).
- Privacy: the report never holds an instance id (`USB\VID_...`, `PCI\VEN_...`), a location path
  (`PCIROOT(...)#USBROOT(...)`), a symbolic link (`\\?\usb#...`), a device path (`/dev/video<n>`), a
  serial, a port number or a hub chain (9.4). The controller is an anonymous index and PCI ids. No key has a
  name of rule 2 of [C 6], also not deep in `details`.
- The USB id of a unit is in its label, and its name is in its summary item (9.4), so the item does not repeat
  them. The name key of 9.4 (`name_usb`) is the one exception: it is only for a new USB id.
- Size: about 300 bytes for each unit, plus 25 bytes for each mode, at most about 1.5 kB for the mode list.

#### 3.5.6 Addition 5: frame timing [U Q557, Q594]

The timing comes from the product rate check and from the timing sidecar of the take. Both exist on
each system, so Windows quick has timing also without the `clock`, `sequence` and `time-gaps` rows.

**The rate rows.** A rate row is `<label>:rate`, and, when they are built, `<label>:rate:<mode>`,
`<label>:rate:<w>x<h>@60`, `<label>:auto-exposure:holds-rate:<mode>` and `<label>:group-open`.

| Key | Place | Type and values | Present (else) | Example | Source | Privacy |
|---|---|---|---|---|---|---|
| `interval_max_ms` | `numbers` of a rate row | ms, 1 decimal: the longest arrival interval of the window | each rate row from a step; `null` when the window did not end | `7004.2` | small code: `rate_interval_max_ms` | number |
| `interval_max_at_s` | `numbers` of a rate row | seconds from `t0`, 2 decimals: the end of the longest interval | as `interval_max_ms` | `13.95` | small code: `rate_interval_max_end_ns` (`perf_counter_ns`); certify subtracts `t0` | number |
| `long_intervals` | `numbers` of a rate row | integer: the intervals of the window over 1.5 periods | as `interval_max_ms` | `1` | small code: `rate_long_intervals` | count |
| `luma_mean` | `numbers` of a rate row (4.2) | as 4.2 | also on a rate row `fail`: from `rate_luma_mean` when the ring has no frame (19.1 item 7) | `141.3` | small code: the D-3 key `rate_luma_mean`, the mean grey value of the last frame of the window at 1/8 size (3.5.15 P5) | number |

- `window_frames` and `interval_p95_ms` of the rate row are dropped [U Q594]: the window is fixed (frames 6 to
  90), and the p95 sits on the 16 ms grid.
- `measured_fps` has 2 decimals [U Q627, MEE1 10]. The 16 ms arrival grid makes it good to about 0.5 % over the window of
  about 2.8 s [M review pass 2 of 2026-11-23: the C922 gave 29.84 and 30.00 fps in two runs 34 s apart]. The
  limit of 3 % is six times that error.

**The `records` rows**, from the timing sidecar that certify already reads. Each key stands on
`<label>:records:rows-complete` only [U Q627, MEE1 21]:

| Key | Place | Type and values | Present (else) | Example | Source | Privacy |
|---|---|---|---|---|---|---|
| `take_fps` | `numbers` of `rows-complete` | fps, 2 decimals: (n - 1) divided by the time from the first to the last arrival, over the n rows of the camera that are not `missing` | each such row from a step; `null` with fewer than 2 such rows | `29.97` | small code: sidecar `arrival_ns` | number |
| `interval_p95_ms`, `interval_max_ms`, `interval_max_at_s` | `numbers` of `rows-complete` | as on a rate row, over the arrival intervals of consecutive rows that are not `missing` | as `take_fps` | `48.0`, `64.1`, `17.87` | small code: sidecar `arrival_ns` and `t0` | numbers |
| `long_intervals` | `numbers` of `rows-complete` | the change of D-3 `long_intervals` in the take window (3.5.1) | each such row from a step; `null` when the source gives no value | `0` | run time: the diagnostics reads before and after the take | count |
| `discontinuity_flags` | `numbers` of `rows-complete` | the change of D-3 `discontinuity_flags` in the take window | as `long_intervals` | `0` | run time | count |

- `grid_16ms_share` is dropped [U Q594].
- `sample_time_kept` is a fact of the source: it stands one time in `details.cameras` [U Q627, MEE1 14].
- `sample_minus_arrival_p50_ms` and `sample_minus_arrival_p95_ms` leave the `records` rows. The clock rows hold
  the sample-minus-arrival numbers, one time (10.2) [U Q627, MEE1 21] [review pass 2, finding 2].
- A counter on a take row is always the change in the take window [U Q573]. The real full run of 2026-11-23 wrote
  counts since the open (`discontinuity_flags` 1 on two passing cameras, `frames` 396 for a take of 90 rows)
  [M review pass 2, finding 4]. This is a fault of the code (3.6.6).

**The `clock:near-arrival` row** (10.2). `jitter_p95_ms` comes from the 64 rows of `frame_log` that certify reads
after the stop. d is an arrival interval in ms, and P is the period of the mode.

| Key | Place | Type and values | Present (else) | Example | Source | Privacy |
|---|---|---|---|---|---|---|
| `jitter_p95_ms` | `numbers` of `<label>:clock:near-arrival` | ms, 2 decimals: the 95th percentile of the absolute value of d - P, over each d of 1.5 P or less | each such row from a step; `null` with fewer than 10 intervals | `14.67` | small code: `frame_log` | number |

- `grain_ms` is dropped [U Q594].
- Size: about 80 bytes on a rate row and about 120 bytes on `rows-complete`: about 0.8 kB for four cameras.

#### 3.5.7 Addition 6: the warnings of the take, the first gap, the exit codes [U Q557]

The exit codes are in 3.5.3 (`exit_code`). The take keys stand on `group:take:finished` only, and the gap keys on
`<label>:records:rows-complete` only [U Q627, MEE1 21].

| Key | Place | Type and values | Present (else) | Example | Source | Privacy |
|---|---|---|---|---|---|---|
| `take_warnings` | `numbers` of `group:take:finished` | a list of the codes of the manifest warnings (rec 6.6), each one time, sorted: `camera_dead`, `camera_file_short`, `camera_gap`, `take_error`; `[]` with no warning | each such row from a step; `null` when the manifest cannot be read | `["camera_gap"]` | run time: `warnings[].code` of the manifest that certify already reads | codes; `skellycam/REASON_CODES.md` must list each one, because `numbers` allows a list of reason codes only [C 3.4] |
| `take_error_kind` | `numbers` of `group:take:finished` | `disk-stall`, `write-error`, `files-not-completed`, `rows-differ`, `process-running`, `other` | only with a `take_error` | `"disk-stall"` | small code: from the fixed start of the `detail` of the first `take_error` (`take.py`): "disk stall" gives `disk-stall`, "write" gives `write-error`, "the files could not be completed" gives `files-not-completed`, "rows, expected" gives `rows-differ`, "its process still runs" gives `process-running`, else `other`. The detail is never copied: it holds the `camera_id` | closed name |
| `take_error_camera` (not written, review finding 7) | not in the report: a label is no value of a fixed vocabulary [C 3.4]; certify uses it for the rule of Q621 (3.6.10), and the `module` of the take row names the model | the label (3.1) of the camera of the first `take_error`, from its `camera_key` | only with a `take_error` that names a camera | `"cam.media-foundation.046d-085c.0"` | small code | a label |
| `free_gb` | `numbers` of `system:recording-space` (3.6.11) [U Q613] | GB (10^9 bytes), an integer: the free space of the volume of the recording folder | each such row from a step | `412` | new: `shutil.disk_usage` | number |
| `take_seconds` | `numbers` of `group:take:finished` | the length of the take (the old `seconds` of 4.5) | as today | `3.14` | run time | number |
| `first_gap_row`, `first_gap_from`, `first_gap_to` | `numbers` of `rows-complete` | integers from the `camera_gap` warning of this camera, `row=<k> from=<a> to=<b>` (the first gap, decision F of the user) | only with a `camera_gap` for this camera | `47`, `1188`, `1190` | run time: the fixed form of `take.py` | numbers |
| `dead_last_frame` | `numbers` of `rows-complete` | integer: `last_frame=<n>` of the `camera_dead` warning of this camera; `null` for `last_frame=none` | the row of a camera with `camera_dead`, also when it is the `fail` row of a wedge; absent otherwise | `212` | run time | number |

- Size: about 80 bytes on `group:take:finished` and about 40 bytes on a `rows-complete` row with a gap.

#### 3.5.8 Addition 7: the CPU during the open and the take [U Q557, Q594]

| Key | Place | Type and values | Present (else) | Example | Source | Privacy |
|---|---|---|---|---|---|---|
| `cpu_cores_used` | the items `open` and `take` of `details.steps` (3.6.3) | cores, 2 decimals: the CPU seconds of the session child and of each of its child processes in the window, divided by the length of the window | each such item; `null` when `psutil` fails | `1.42` | new: a sampler thread in the session child reads `psutil` `cpu_times` of the process tree at the start and at the end of the window (a process that starts in the window counts from its start) | number |
| `cpu_share_p95` | the same items | percent of all logical CPUs, 1 decimal, 0 to 100: the 95th percentile of the CPU use of the system, sampled each 0.25 s in the window | as `cpu_cores_used` | `37.5` | new: `psutil.cpu_percent(interval=None)` | number |
| `cpu_logical` | `details` | integer: the logical CPUs | always | `28` | run time: `psutil.cpu_count(logical=True)` | number |

- The open window is from the apply request to the end of the wait for the states (4.2). The take
  window is from `start_recording` to the return of `stop_recording` (4.5). The open window is one window for all
  cameras, so the values stand one time [U Q594].
- `cpu_share_p95` shows a load of other programs; `cpu_cores_used` shows the load of skellycam.
- 6.1 uses the same keys with the same meaning, in its own step item, and `cpu_logical` is in `details` only.
- Size: about 50 bytes on each of the two items.

#### 3.5.9 Addition 8: the exposure and gain context [U Q557, Q572, Q594]

| Key | Place | Type and values | Present (else) | Example | Source | Privacy |
|---|---|---|---|---|---|---|
| `exposure_before`, `exposure_before_auto` | item of `details.cameras` [U Q627, MEE1 14] | integer in the unit of `exposure_unit` / boolean; or `null` | each unit that opened; `null` when the source read no "before" value | `-6`, `true` | run time: D-4 `exposure_before`, `exposure_before_auto` (the first read of the open, before any set, ux 4.7) | numbers |
| `exposure_min`, `exposure_max`, `exposure_step`, `exposure_default` | item of `details.cameras` [U Q594] | integers in the unit of `exposure_unit`; or `null` (the KS route has no range) | each unit that opened | `-11`, `-2`, `1`, `-6` | run time: D-4 | numbers |
| `gain_value_at_m7`, `gain_auto_at_m7` | `numbers` of `<label>:settings-stick:image-effect` only (full) | native gain value (integer) / boolean; or `null` (no gain control) | each such row from a step | `32`, `true` | run time: D-4 `gain_value`, `gain_auto` of the dict that certify reads with `luma_at_m7` | numbers |
| `gain_value_at_m8`, `gain_auto_at_m8` | the same row | as above, from the dict that certify reads with `luma_at_m8` | each such row from a step | `61`, `true` | run time | numbers |

- `exposure` of the rate row is dropped [U Q594]. The exposure of the open is `exposure_open` of
  `details.limits` (3.6.3).
- On a route with no time unit, certify sets the steps 5 and 4 in place of -7 and -8 (4.3). The
  suffixes stay `_at_m7` and `_at_m8`, as for `luma_at_m7`.
- The "before" values explain `camera-not-restored`: a camera that fails its rate check is not restored
  (19.2 item 4), and the values tell what the camera had before the run.
- Size: about 150 bytes in each item of `details.cameras` and about 80 bytes on the `image-effect` row.

#### 3.5.10 The unit id: removed [U Q595]

The user removed the unit id on 2026-11-23 [U Q595]
([ADR-H2A0](../decisions/entries/H2A0-decisions-of-the-user-on-the-certify-report-shape.md)): a report only needs
to say if a camera model works. A unit gets a plain label (3.1). The label can differ between two runs. The
report has no `unit_id` and no `unit_ids_new`, and certify writes no key file `certify_unit_key`. The contract
allows a local unit id [C 6, commit `cf9c7a2`]; skellycam does not use that permission. This replaces Q558 of
[ADR-F6C3](../decisions/entries/F6C3-decisions-of-the-user-on-the-certify-report-fields.md) and item 9 of
[ADR-NQ77](../decisions/entries/NQ77-choices-of-the-certify-report-fields.md).

#### 3.5.11 The logs of the last run [U Q559, Q572]

- **The folder.** `certify_logs/` in the skellycam base folder, beside `camera_checks.json`. It is
  not in the work folder, so the cleanup of 9.5 does not delete it.
- **What it holds.** The log files that skellylogs writes for the session child and for each of its
  camera processes (and the re-check child of phase G), in the form of the product. Certify sets
  `SKELLYLOGS_LOG_DIR` to this folder in the session child, also when the caller set another folder:
  the variable changes only in the environment of the session child. The session child writes a log
  file too (today it writes none). This replaces the log folder `logs` of the work folder (9.5, 19.2
  item 13).
- **When it is replaced.** At the start of each run that holds the run lock (9.5), certify deletes the
  files of the folder. A run that the lock refuses does not touch them, because another run writes
  them. A cancel, a crash, a time-out or an abandon keeps the files: a log is no result [C 2.4].
- **The size bound.** At the end of the run (phase H), certify cuts each file over 1 MiB to its last
  1 MiB, and keeps the 64 newest files. Thus the folder holds at most 64 MiB [U Q572, not calibrated]. A
  quick run of four cameras wrote about 30 kB [M run 11-21].
- **Never sent.** Certify never sends a log, never copies a log line into the report, and never puts
  the path of the folder in the report. The logs hold symbolic links, `camera_id` values and paths.
  They stay on the system. The person or the app can send them by another way; certify does not.
- **What the person sees [U Q627, MEE1 26].** The text of the app that offers the logs tells what they hold: "These files can
  hold the names of folders on this computer, which can hold your user name, and the ids of your cameras. Read
  them before you send them." A product log line prints the full path of the evidence file with the text of a
  `FileNotFoundError` [M review pass 2 of 2026-11-23]. That line is a product fault (open work).
- **The one line in the report.** `details.logs_kept`: an integer, the count of files in the folder
  at the end of the run (0 with none). It holds no path and no file name.
- The folder is the own store of skellycam [C 2.5], as `camera_checks.json` is. It is no item of
  `system_changes` (9.1). The key file of the unit id is removed (3.5.10).

#### 3.5.12 Size of the report [U Q572; changed by Q594 and 3.6.5]

- The relay refuses a file over 262,144 bytes (256 KiB), with each module report and the Markdown in
  it (`relay/README.md` of the contract). skellytracker shares the file: its full module was about 90 kB on
  2026-11-20 [M review of 2026-11-23].
- The bound of 128 KiB and 48 KiB of Q572 is replaced by the bound of 3.6.5 [U Q627, MEE1 19].

#### 3.5.13 Worked example [U Q572; slim form of Q594]

The values are examples, made up but near the real runs. They hold no real serial, path, host name or
user name. Each example shows only the rows that the case needs, in the slim form (3.6). The names come from
the list of known cameras (9.4).

**Case 1: a Kiyo Pro wedges at the open.** The Kiyo Pro gives no frame in 5 s. The close after the
failed open then hangs in the release of the source reader. The C922 and the C930e give no frame for
7 s.

```json
{"checks": [
 {"name": "cam.media-foundation.1532-0e05.0:opens", "result": "fail", "reason": "hung", "module": "Razer Kiyo Pro",
  "numbers": {"stage": "first-frame", "call": "reader-release", "first_fail_code": "first-frame-timeout", "exit_code": 1}},
 {"name": "cam.media-foundation.1532-0e05.0:not-reached", "result": "not-run", "reason": "prior-failure",
  "module": "Razer Kiyo Pro", "numbers": {"checks": 8}},
 {"name": "cam.media-foundation.046d-085c.0:rate", "result": "fail", "reason": "rate-low", "module": "Logitech C922",
  "numbers": {"measured_fps": 8.61, "luma_mean": 118.2, "interval_max_ms": 7004.2, "interval_max_at_s": 13.95,
   "long_intervals": 1}},
 {"name": "cam.media-foundation.046d-0843.0:rate", "result": "pass", "reason": null, "module": "Logitech C930e",
  "numbers": {"measured_fps": 30.0, "luma_mean": 106.4, "jpeg_kb_mean": 129.6, "interval_max_ms": 48.1,
   "interval_max_at_s": 6.71}}],
 "cleanup": [
 {"name": "release:cam.media-foundation.1532-0e05.0", "result": "fail", "reason": "camera-wedged", "module": "Razer Kiyo Pro"}],
 "details": {"steps": [{"step": "open", "t_start_s": 1.02, "seconds": 12.31, "cpu_cores_used": 0.61, "cpu_share_p95": 9.8}],
  "cameras": [
  {"label": "cam.media-foundation.046d-0843.0", "result": "pass", "failed": null, "reason": null, "usb_link": "USB 2",
   "bcd_usb": "0200", "bcd_device": "0013", "controller": 0, "controller_id": "8086:7ae0", "hub_depth": 1,
   "driver_kind": "uvc-inbox", "driver_version": "10.0.26100.1150", "modes": ["MJPG 1280x720@30", "MJPG 1920x1080@30"]},
  {"label": "cam.media-foundation.046d-085c.0", "result": "partial", "failed": "rate", "reason": "rate-low",
   "blocked_by": "cam.media-foundation.1532-0e05.0", "usb_link": "USB 2",
   "bcd_usb": "0200", "bcd_device": "0016", "controller": 0, "controller_id": "8086:7ae0", "hub_depth": 1,
   "driver_kind": "uvc-inbox", "driver_version": "10.0.26100.1150", "exposure_before": -5, "exposure_before_auto": true,
   "modes": ["MJPG 1280x720@30,60", "MJPG 1920x1080@30"]},
  {"label": "cam.media-foundation.1532-0e05.0", "result": "fail", "failed": "opens", "reason": "hung", "usb_link": "USB 3",
   "bcd_usb": "0320", "bcd_device": "0105", "controller": 0, "controller_id": "8086:7ae0", "hub_depth": 0,
   "driver_kind": "uvc-inbox", "driver_version": "10.0.26100.1150", "modes": ["MJPG 1280x720@30,60", "MJPG 1920x1080@30,60"]}]}}
```

What a developer can now conclude: the Kiyo Pro failed first with `first-frame-timeout`, and the hang
came after, in the reader release of the close (`call`), so the process ended hard (`exit_code` 1).
The 7 s stall of the C922 ends at 13.95 s, near the end of the open step (1.02 s to 13.33 s), and
its light and its other intervals are normal: the C922 failure is a result of the Kiyo Pro, not of the
C922. The wedge rule of 3.6.10 tells it: the C922 item is `partial` with `blocked_by`, not `fail`. All three
cameras are on one controller, so that controller or its driver stack is the first suspect. How often this wedge comes needs `<label>:cycles` (3.5.14).

**Case 2: a generic camera gives 25.7 fps in a 30 fps mode.** It stays in manual exposure after the
run. Its USB id `4c4a:4a55` is not in the list of known cameras, so its name comes from the device (9.4).

```json
{"checks": [
 {"name": "cam.media-foundation.4c4a-4a55.0:opens", "result": "pass", "reason": null, "module": "USB Camera",
  "numbers": {"seconds_to_first_frame": 0.088}},
 {"name": "cam.media-foundation.4c4a-4a55.0:rate", "result": "fail", "reason": "rate-low", "module": "USB Camera",
  "numbers": {"measured_fps": 25.74, "luma_mean": 141.3, "interval_max_ms": 48.2, "interval_max_at_s": 6.12,
   "long_intervals": 0}}],
 "cleanup": [
 {"name": "release:cam.media-foundation.4c4a-4a55.0", "result": "fail", "reason": "camera-not-restored", "module": "USB Camera"}],
 "details": {"limits": {"rate_tolerance": 0.03, "exposure_open": -7},
  "cameras": [
  {"label": "cam.media-foundation.4c4a-4a55.0", "result": "fail", "failed": "rate", "reason": "rate-low",
   "name_usb": "USB Camera", "usb_link": "USB 2", "bcd_usb": "0200", "bcd_device": "0100",
   "controller": 0, "controller_id": "8086:7ae0", "hub_depth": 0, "driver_kind": "uvc-inbox",
   "driver_version": "10.0.26100.1150", "exposure_before": -6, "exposure_before_auto": true,
   "exposure_min": -11, "exposure_max": -2, "exposure_step": 1, "exposure_default": -6,
   "modes": ["MJPG 640x480@30", "MJPG 1280x720@30", "MJPG 1920x1080@30"]}]}}
```

What a developer can now conclude: no interval is longer than 1.5 periods, so the camera loses no frame
and does not stall: it gives a steady rate below its declared rate. At -7 (7.8 ms) the exposure cannot
limit 30 fps, and the image is bright (141.3), so more light does not help: the camera is slower than
its mode (the limit `rate-below-declared` of 11.2). It was in auto exposure before the run
(`exposure_before_auto` `true`). The product does not restore a camera whose loop failed (19.2 item 4),
so the camera stays in manual. The reopen of phase G (8.3, decided, not built) is the fix.

**Case 3: a Kiyo Pro whose change from -7 to -8 barely changes the image (full).**

```json
{"checks": [
 {"name": "cam.media-foundation.1532-0e05.0:settings-stick:readback", "result": "pass", "reason": null,
  "module": "Razer Kiyo Pro",
  "numbers": {"exposure_readback_open": -7, "exposure_readback": -8, "exposure_unit": "log2-s",
   "control_path": "iam"}},
 {"name": "cam.media-foundation.1532-0e05.0:settings-stick:holds", "result": "pass", "reason": null,
  "module": "Razer Kiyo Pro", "numbers": {"exposure_later": -8}},
 {"name": "cam.media-foundation.1532-0e05.0:settings-stick:image-effect", "result": "fail", "reason": "no-image-effect",
  "module": "Razer Kiyo Pro",
  "numbers": {"luma_at_m8": 130.8, "luma_ratio": 0.962, "gain_value_at_m7": 32,
   "gain_auto_at_m7": true, "gain_value_at_m8": 61, "gain_auto_at_m8": true}}],
 "details": {"limits": {"luma_ratio_time_unit": 0.85},
  "cameras": [{"label": "cam.media-foundation.1532-0e05.0", "result": "partial", "failed": "settings-stick:image-effect",
   "reason": "no-image-effect", "exposure_min": -11, "exposure_max": -2, "exposure_step": 1, "exposure_default": -6}]}}
```

What a developer can now conclude: the camera took -8 and kept it (the read-back and the later read),
and -8 is inside its range, so the set works. Its gain was on auto and rose from 32 to 61 when the
exposure halved: the camera's own auto gain made up most of the change. The check then measures the
auto gain, not the exposure. After 3c the same apply sets gain to manual (4.3 step 2). With an equal
gain at -7 and -8, the reading would be different: the firmware would ignore the step.

**Case 4: one lost frame in a take (`camera_gap`, full).**

```json
{"checks": [
 {"name": "group:take:finished", "result": "pass", "reason": null,
  "numbers": {"cameras": 3, "take_seconds": 3.14, "file_system": "ntfs", "take_warnings": ["camera_gap"]}},
 {"name": "cam.media-foundation.046d-0843.0:records:rows-complete", "result": "pass", "reason": null,
  "module": "Logitech C930e",
  "numbers": {"rows": 90, "take_fps": 29.97, "interval_p95_ms": 48.0, "interval_max_ms": 64.1,
   "interval_max_at_s": 17.87, "first_gap_row": 47,
   "first_gap_from": 1188, "first_gap_to": 1190}},
 {"name": "cam.media-foundation.046d-0843.0:records:gaps-explained", "result": "pass", "reason": null,
  "module": "Logitech C930e", "numbers": {"gaps": 1, "replaced": 1}}],
 "details": {"steps": [{"step": "take", "t_start_s": 16.20, "seconds": 4.71, "cpu_cores_used": 1.31, "cpu_share_p95": 18.4}]}}
```

What a developer can now conclude: the camera skipped source frame 1189 at row 47, at 17.87 s, in the
middle of the take and not at its end. The source counted no long interval and no discontinuity, so
the camera gave each frame on time. The waiting place replaced one frame (`replaced` 1), so the loop of
skellycam was late one time. The system was not busy (`cpu_share_p95` 18.4 %), so the next place to
look is the loop at 17.87 s in the kept logs (3.5.11).

#### 3.5.14 What these fields still cannot answer [U Q572]

- How often a wedge comes (one open in 10 to 30): `<label>:cycles` (8.2, not built).
- An exposure that a camera loses at a reopen: `<label>:settings-stick:each-open` (5.2, not built).
- An exposure cliff (28.1 fps at -6, 22.3 fps at -5) and noisy windows: the sweep
  `<label>:exposure:<base>` with two windows for each step (5.2, not built).
- A 60 fps mode that gives 30: the 60 fps checks of phase F (8.2, not built).
- Why each camera slows down in one long exposure: `group:contention` and `group:open` with the retry
  alone (4.2, 6.1, not built). `controller` only shows which cameras share a controller.
- Which program holds a camera: `system:camera-apps` (6.2, not built). `native_code` only tells "in
  use" from "access denied".
- Which control a camera did not get back at the end: the cleanup facts are not decided.
- Where a session crash came from, and which device hung the detection: not decided.
- Where a driver call blocks inside Media Foundation or the kernel: a trace on request (WPR, usbmon).
  The kept logs show only the order of the calls.
- The physical port, the cable and the hub model: only the person knows them.

#### 3.5.15 Build order [U Q572, Q575]

The product changes come first, because without them the failure facts of a wedge stay `null`. Each
change has its tests.

| # | Change | Kind | Needed for |
|---|---|---|---|
| P1 | `CALLS` of `media_foundation/source.py` gets `the reader release` (`reader-release`) and `the control interface release` (`control-release`). A hung `a control call` records `set-controls`; a control call that returns an error still records nothing (U14). [ux 4.6.3] lists the three names. | product | `call` of case 1 |
| P2 | The source keeps `first_fail_code`: the code of the first failure of the open, also when a later hang (for example in the close after a failed open) gives the code `hung`. It keeps the native code of the first failure that had one in `native_code`. | product | `first_fail_code` of case 1 |
| P3 | The dict of a hung camera reaches the main process: before `os._exit(1)`, `hard_end` publishes the dict with the failure and waits for the pipe at most 1 s, as `_flush_diagnostics` does. Check first that the failure state is set before the hard end, so that `_mark_ended` does not replace a `hung` failure with `process-ended`; `_mark_ended` keeps a code that is already set. | product | each failure fact of a hang |
| P4 | `exit_code` (D-5): the main process puts the exit code of a camera process that ended into the kept diagnostics (the form of `_note_failure`). | product | `exit_code` |
| P5 | The rate window keys (D-3) of the start-up rate check: `rate_interval_max_ms`, `rate_interval_max_end_ns`, `rate_long_intervals`, `rate_luma_mean` (`rate_window_frames` and `rate_interval_p95_ms` are dropped, Q594). | product | the rate rows of 3.5.6 |
| P6 | `usb_connection.py`: `usb_facts(path)` gives `usb_link`, `bcd_usb`, `bcd_device`, `controller_id`, `hub_depth`, `driver_kind` and `driver_version` from the walk of `_windows_usb_link` (Windows first). | product | 3.5.5 |
| P7 | Each build writes or carries `skellycam/build_info.json`: the wheel, the sdist, a wheel from the sdist and the installer (3.5.2) [U Q647]. | build | 3.5.2 |
| C1 | The run clock and `details.steps` (3.5.4, 3.6.3); `take_seconds`. | certify | each `_at_s` key |
| C2 | The failure facts of 3.5.3. It can land before P1 to P4, with `null` values. | certify | 3.5.3 |
| C3 | `details.cameras` with the verdict and the names of 3.6.3 and 9.4 (needs P6 for the USB keys). No unit id (Q595). | certify | 3.5.5, 3.6.3 |
| C4 | The take timing, the warnings and the first gap of 3.5.6 and 3.5.7. | certify | cases 4 and 5 of the lab |
| C5 | The exposure and gain context of 3.5.9. | certify | case 3 |
| C6 | The CPU sampler of 3.5.8, into the `open` and `take` steps. | certify | 3.5.8 |
| C7 | The log folder of 3.5.11. | certify | 3.5.11 |
| C8 | The rate rows of 3.5.6 (needs P5). | certify | cases 1 and 2 |
| C9 | The validator `skellycam/tests/certify/report_rules.py` and the tests T-CERT-77 to T-CERT-90 and T-CERT-91 to T-CERT-111 (17); `skellycam/REASON_CODES.md` lists the warning codes of `take_warnings` and the vocabularies of this section. | certify | each field |

Order [U Q575]: P3, P1, P2 and P4; then C1, C2, P6 with C3, C4, C5, C6, C7, then P5 with C8. C9
comes with each step. P7 can come at any time. 3.6.7 puts the fix of B1, P7 and the steps of the report shape
(steps 1 to 9) before P3, P1, P2 and P4 (step 10). This replaces the order of Q575 [U Q626] (3.6.7). The build starts only after the branch of the third
fix lane (`dom/fix-lane-3`) is merged into `dom/integration` [U Q575].

### 3.6 The report shape of quick and full [U Q591 to Q599, Q608 to Q624]

The user asked for an independent review of the report, with four aims: quick is a smoke test ("do things even
work at all"); full gives the performance, the gaps in the logic and the captured errors, and either a sign-off
for production or the facts that let a developer fix the issue; no user data leaks; the report is short, with no
noise and no duplicates. The review of 2026-11-23 and its second pass on the real quick and full reports of that
day measured the reports, and a gap review read the test set. On 2026-11-23 the user decided Q591 to Q599
([ADR-H2A0](../decisions/entries/H2A0-decisions-of-the-user-on-the-certify-report-shape.md)) and Q608 to Q618
([ADR-BW5M](../decisions/entries/BW5M-decisions-of-the-user-on-the-two-verdicts-and-the-certify-test-set.md)). The choices of the
agent were marked [A] ([ADR-MEE1](../decisions/entries/MEE1-choices-of-the-certify-report-shape.md)); the user accepted
them as a set (Q627), so they are marked [U Q627, MEE1 n] or [U Q627, DBF8 n] with the item number of the entry,
except the choices that Q628 changes (the camera names and the USB link notice), which stay [A]. The contract
owner confirmed on 2026-11-23 that format 1.7.0 carries the two verdicts of Q611 and the "gate not complete" of
Q610 with no change of the format [C 3.4, 3.7, 4.2, 5.3, 7.2]. Steps 1 to 4 of 3.6.7 are built [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md); the other
steps are not built.

#### 3.6.1 Rules of the rows

- **Schema.** Each module report has the schema `skellycertify.report/1.7.0` [U, earlier decision restated in
  ADR-H2A0].
- **Not built [U Q591].** A check that has no code in this version is not in `checks`. Its name stands one time in
  `details.not_built` (3.6.3). The plan does not count it.
  - Only a check with no code leaves `checks`. A check that has code, but whose product value is missing at run
    time (for example a diagnostics key that is `null`), keeps its row `not-run` with `not-built` [U Q627, MEE1 3]. The plan
    counts it.
  - A check of the camera block of `full` for a second unit of a model (5.1) is not planned and gives no row,
    in place of `not-run` with `same-model` [U Q627, MEE1 4]. The label of the unit (`.1`, `.2`) tells the reader that the
    first unit of the model had the block.
- **One row for a camera that could not go on [U Q592].** When a camera cannot go on, the checks of that camera
  that no progress message named yet give one row `<label>:not-reached` in place of their filled `not-run` rows.
  - `result` is `not-run`. `reason` is the reason of the first check that it stands for: `prior-check-failed`,
    `prior-failure`, `camera-in-use`, `no-mjpg-mode`, `cancelled`, `over-budget` or `interrupted` [U Q627, MEE1 6].
  - `module` is the `name` of the summary item of the camera [C 3.4, 4.2 part 8].
  - `numbers` holds `checks`: the count of the checks that the row stands for [U Q627, MEE1 6].
  - A check that a progress message named keeps its own row, with its own result.
  - `prior-failure` and `prior-check-failed` are codes of skellycam. `skellycam/REASON_CODES.md` lists both
    [C 5.4].
- **B1: a camera that leaves the run between two steps [fault fix].** Today a camera that stalls, whose process
  ends, or that has a stream error between two steps gets no `fail` row: the scan of the session runs with no
  running check, and the take step gives only `prior-check-failed`. The cause is nowhere in the report, and
  `gate:no-hang` passes [M review of 2026-11-23, fake cameras]. The fix:
  - Such a camera gets one `fail` row with the product failure code (`stalled`, `stream-error`,
    `device-removed`, `hung`; `process-ended` gives `crashed`, 10.5) and the failure facts of 3.5.3 that have a
    value.
  - The row is the first check of that camera that has no result yet, in the order of the plan [U Q627, MEE1 1]. In the take
    and after it, the row is `<label>:records:rows-complete` [U Q627, DBF8 14, review finding 5], while it has no
    result. Certify looks once more after the take rows and after the close [U Q646]. A camera that leaves there
    gets its row on `<label>:live-at-close` (3.6.2), the last check of the camera [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md). For
    example, a camera that stalls after `ready` and before the settings change gives
    `<label>:settings-stick:readback` `fail` `stalled`. Its other checks give one `<label>:not-reached` row.
  - The row has `module` = the name of the model, also when its check is a pipeline check, and the model item is
    `fail`, whatever the group of the check (3.4): a product failure code of a camera tells a fault of that
    camera [U Q627, DBF8 12]. Rule (c) of 3.6.10 applies when each model gives such a row.
  - `<model>:gate:no-hang` reads each `fail` row of the model. It fails with the reason `hung`, `crashed` or
    `stalled` [U Q627, MEE1 2]. A `device-removed` row does not fail it: the person removed the camera.
  - `details.cameras[]` of that unit names the row in `failed` (3.6.3).
- **A camera that fails at the open [U Q648].** The open names `opens`, `rate` and `modes:granted:<base>` in its
  progress messages before the one apply, so each of the three keeps its own row. The camera has these three rows
  and one `<label>:not-reached` row.
- **No zero counts on a `pass` row [U Q627, DBF8 16, review].** On a `pass` row, a count whose value is 0 is absent (for example
  `frames_damaged`, `decode_failures`, `missing`, `gaps`, `end_gaps`, `long_intervals`, `discontinuity_flags`,
  `frames_differ`, `frames_wrong_size`, `later_than_arrival`, `problems`). A reader reads an absent count of a
  `pass` row as 0. A `fail` row writes each count of its rule.
- **One number, one row [U Q594, A].** No `numbers` object repeats another. Each key stands on the one row whose
  rule reads it (3.6.2). A `pass` row has `numbers` only when it measured something, and it does not echo the
  request [U Q627, MEE1 9]. A key of a failure fact is in a row only when it has a value (3.5.3) [U Q594].
- **Rounding [U Q627, MEE1 10].** `measured_fps`, `take_fps` and the take `rate`: 2 decimals. `free_gb`: an integer. A time in
  ms: 1 decimal, and 2 decimals for the clock keys.
- **The plan total [U Q627, MEE1 7].** `total` of the plan [C 2.6] is the count of the rows of a run in which each planned
  check gives its own row. It counts `session:exit` [review pass 2, finding 5]. In the progress messages,
  `done` counts a `<label>:not-reached` row as the count of the checks that it stands for, and counts the end
  of the session child as one ended check, with or without a `session:exit` row. Thus `done` equals `total` at
  `state` `done`, and `done` is never above `total`.
- **Checks that never judge on a backend [U Q627, MEE1 8].** On Media Foundation, `clock:base` is not planned: the source can
  never tell its clock (`clock-unknown`, ADR-Z7F3). The gate then requires the two measured clock checks [U Q585].
  Of the pair `sequence` and `time-gaps`, the run writes only the check that judges, and the plan counts one
  check for the pair.

#### 3.6.2 The check catalogue for each level

`<label>` is the label of one camera (3.1), `<model>` its `cam.<backend>.<vid>-<pid>`. "Numbers" names the keys
of the row. A key with "fail" is on a `fail` row only. The failure facts of 3.5.3 are on each failure row and are
not repeated here. 3.6.10 gives the kind of each check (camera, pipeline or system) and its `module`.

**Quick, each camera [U Q593, Q624i, Q646; the row [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) item 15]: twelve checks.**

| Check | Numbers | Fail and not-run reasons |
|---|---|---|
| `<label>:detect:mjpg-mode` | none | `no-mjpg-mode` |
| `<label>:opens` | `seconds_to_first_frame` | the product failure codes (section 15); `not-run` `camera-in-use` |
| `<label>:rate` | `measured_fps`, `luma_mean`, `jpeg_kb_mean`, `interval_max_ms`, `interval_max_at_s`, `long_intervals` | `rate-low`, `rate-high`; `not-run` `too-dark` |
| `<label>:modes:granted:<base>` | fail: `requested_fourcc`, `granted_fourcc`, `granted_w`, `granted_h`, `granted_fps_num`, `granted_fps_den` | `mode-not-granted` |
| `<label>:settings-stick:readback` | `exposure_readback_open`, `exposure_readback`, `exposure_unit`, `control_path` (the set value is `exposure_changed` of `details.limits`) | `readback-differs`; `not-run` `no-manual-exposure` |
| `<label>:settings-stick:holds` | `exposure_later` | `setting-reverted`; `not-run` `no-manual-exposure`, `prior-check-failed` |
| `<label>:native-jpeg:format` | `dht_inserted`, `dqt_distinct`, `dqt_sha256`; fail: `format`, `delivered` | `no-native-jpeg` |
| `<label>:native-jpeg:valid` | `frames_checked`, `frames_damaged` | `jpeg-damaged` |
| `<label>:records:rows-complete` | `rows`, `missing`, `take_fps`, `interval_p95_ms`, `interval_max_ms`, `interval_max_at_s`, `long_intervals`, `discontinuity_flags`, the gap keys of 3.5.7 | `rows-differ`, `missing-rows` |
| `<label>:records:blocks-decode` | `decode_failures` | `frame-not-decodable` |
| `<label>:records:mkv-opens` [U Q624i] | fail: `mkv_frames`, `frame_count` | `mkv-not-readable`, `mkv-frames-differ` |
| `<label>:live-at-close` [U Q646: a fail row; the check: [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) item 15] | fail: the failure facts of 3.5.3 | `pass` when the camera gives no product failure code from the end of its take checks to the end of the close; else `fail` with the product code (B1, 3.6.1); it is in the group Open of 3.4, so a `fail` makes the item `fail` ([ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) item 15) |

On Linux and macOS, quick also has `clock:base`, `clock:before-arrival`, `clock:near-arrival` and one of
`sequence` and `time-gaps` (10.6). They stay in quick [U Q620] ([ADR-G0AC](../decisions/entries/G0AC-decisions-of-the-user-on-the-certify-verdict-questions.md)).

**Quick, the run: eight checks, and `session:exit` only after a fault of the exit.**

| Check | Numbers | Fail reasons |
|---|---|---|
| `detect` | `cameras`, `virtual`, `modes_read` | `timed-out`, `crashed`, `backend-missing` |
| `system:recording-space` [U Q613] | `volume_kind`, `free_gb`, `minutes_free` | `disk-full` (3.6.11) |
| `system:memory` [U Q624l] | `memory_free_mib`, `rings_need_mib`, `shm_size_mib` | `memory-low`, `shm-too-small` (3.6.12) |
| `system:camera-access` [U Q624m] | `access` | none: `record-only`; with `denied` each camera is `not-run` `no-access` (3.6.12) |
| `group:take:finished` | `cameras`, `take_seconds`, `file_system`, `take_warnings`, `take_error_kind` | `take-not-finished`, `take-error`, `fat-disk`, `disk-stall`, `write-error` |
| `group:take:rate` | `frame_count`, `rate` | `too-few-frames`, `group-rate-off` |
| `group:in-step` [U Q616] | `spread_p50_ms`, `spread_p95_ms`, `spread_source` | none: `record-only` (3.6.11) |
| `report:rules` [U Q624m] | `problems` | `report-rules` (3.6.12) |
| `session:exit` | none | `record-only` `hung-at-exit`, `crashed`, `timed-out` [C 2.5] |

**Full, each camera: the twelve of quick ([ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) item 15) and these six [U Q593], with the clock checks.**

| Check | Numbers | Fail reasons |
|---|---|---|
| `<label>:native-jpeg:not-reencoded` | fail: `encoded_by_skellycam` | `no-native-jpeg` |
| `<label>:native-jpeg:size` | `frames_wrong_size` | `jpeg-size-differs` |
| `<label>:native-jpeg:source-equals-ring` | `frames_compared`, `frames_differ` | `jpeg-damaged`; `not-run` `ring-lapped` |
| `<label>:native-jpeg:ring-equals-mkv` | the count of blocks compared and the count that differ | `jpeg-damaged`; `not-run` `ring-lapped` |
| `<label>:settings-stick:image-effect` | `luma_at_m8`, `luma_ratio`, the gain keys of 3.5.9 (the value at -7 is `luma_mean` of the `rate` row) | `no-image-effect`; `not-run` `too-dark`, `too-bright`, `no-frame`, `no-manual-exposure`, `prior-check-failed` |
| `<label>:records:gaps-explained` | `gaps`, `replaced`, `end_gaps` | `gaps-unexplained` |
| `<label>:clock:base` (not on Media Foundation) | `clock`, `tstamp_src`, `ts_conversion` | `clock-base-differs`; `not-run` `clock-unknown` |
| `<label>:clock:before-arrival` | `later_than_arrival` | `sample-after-arrival` |
| `<label>:clock:near-arrival` | `sample_minus_arrival_p5_ms`, `sample_minus_arrival_p50_ms`, `jitter_p95_ms` | `sample-too-early` |
| `<label>:sequence` or `<label>:time-gaps` | the counters of 10.2, each the change in the take window; `time-gaps` writes no `frames` (`rows-complete` has `rows`) [U Q627, DBF8 18] | `sequence-unreliable` or `frame-gaps` |
| `<label>:bursts` [U Q624j] | `burst_share`, `intervals` | none: `record-only` (3.6.12) |

The six checks that move are the six that the review names in its sections 3.3 and 6. The list of the user and
the list of the review are the same.

**Full, each model: two checks [U Q597].** `<model>:gate:no-hang` (an ordinary check, 3.6.1) and `<model>:gate`
(a roll-up check, 11.3). The seven roll-up checks `<model>:gate:<step>` are removed. The two verdicts of Q611
(3.6.10) split the old gate in two. Each gate requires only rows whose `module` is the `name` of its own item
[U Q627, DBF8 13, review finding 3]. Thus a row that the rule of 3.6.10 gives to a model (for example a take row by Q621)
blocks the gate of that model, not `pipeline:gate`. `<model>:gate` requires, for each unit of the model whose
`opens` judged, each row of this list whose `module` is the name of the model:

- the camera checks `opens`, `modes:granted:<base>`, `rate`, `native-jpeg:format`, `native-jpeg:valid`,
  `native-jpeg:size` and `live-at-close` ([ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) item 15: the check and its place in the gate);
- each pipeline and system check of 3.6.10 that the rule gives to the model, by its name: the pipeline checks of
  the list of `pipeline:gate` below, `group:take:finished`, `group:take:rate` and `group:cycles`;
- `<model>:gate:no-hang`;
- `<label>:cycles` of the first unit of the model, because the cycles run for that unit only (3.6.11)
  [U Q599, Q610, Q614]. It is not built, so today `<model>:gate` is `not-run` with `not-built` (3.6.4).

**Full, the pipeline: one roll-up check [U Q611].** `pipeline:gate` requires each row of this list whose
`module` is the pipeline name:

- the run checks `detect`, `group:take:finished` and `group:take:rate`;
- each pipeline check whose `module` is the name of the pipeline item (3.6.10): `native-jpeg:not-reencoded`,
  `native-jpeg:source-equals-ring`, `native-jpeg:ring-equals-mkv`, `records:rows-complete`,
  `records:blocks-decode`, `records:gaps-explained`, `clock:before-arrival`, `clock:near-arrival`, `clock:base`
  where the backend plans it and it is not `not-run` with `clock-unknown` [U Q585], and `sequence` where the
  source gives a sequence number, else `time-gaps`;
- `group:take-30:finished`, `group:take-30:rate`, `group:contention` and `group:open` [U Q599, Q610]. They are
  not built, so today `pipeline:gate` is `not-run` with `not-built` (3.6.4);
- `group:restore-after-kill` [U Q615] and `group:cycles` [U Q627, MEE1 30] (3.6.11), when they are built;
- `system:recording-space` and, when they are built, `system:disk` [U Q612] and the self-checks of section 7 that
  have a pass rule.

With one model only, `pipeline:gate` cannot pass when a pipeline check failed (3.6.10 rule e).

**The result of a roll-up check [U Q627, MEE1 17].** `fail` with `gate-check-failed` when a required check is `fail`; else
`not-run` with `not-built` when a required check is not built [U Q610, C 5.3]; else `not-run` with
`gate-check-not-run` when a required check is `not-run`; else `pass` (3.3). A check with no code is not in
`checks` (Q591), but the gate row itself stays in `checks`: it is `not-run` with `not-built` while a check that it
requires is not built. `details.gates` names the first required check that did not pass, or the first one that is
not built (3.6.3), never `numbers` and never a key `reason` [C 3.4, C 6 rule 9].

**Full, the run.** The run checks of quick, `group:take-again`, `system:power` and `system:timer` (3.6.12), and
`session:exit`. The group, system and self checks of
sections 6 and 7 are not built: their names are in `details.not_built`.

**Full, each camera: the checks of section 20 (accepted on 2026-11-25, not built).**

| Check | Numbers | Fail and not-run reasons |
|---|---|---|
| `<label>:in-use` | `outcome`, `stage`, `seconds` | `not-refused`, `hung`, `wrong-reason` (20.2) |
| `<label>:in-use:other-program` | `outcome`, `fail_code`, `holder_seen`, `first_report_ms` | `not-refused`, `hung`, `wrong-reason`; `not-run` `holder-failed` (20.3, Q812) |
| `<label>:in-use-mid-take` | `warned_s`, `marked`, `control_marked`, `control_blocked`, `frames_lost` | `not-warned`, `not-marked`; `not-run` `no-shared-mode` (20.3) |
| `probe:<model>:hog-mode` (macOS) | `hog_set`, `second_refused`, `hog_released` | `hog-not-settable`, `hog-not-exclusive` (20.4) |
| `<label>:control-read:gaps` (phase D, the first unit of each model) | `reads`, `read_ms_p50`, `read_ms_max`, `gap_at_read_max_ms`, `gap_no_read_max_ms`, `reads_over_limit` | `read-gap`, `hung` (20.9) |

**Full, the v1 player decoder: one check [U Q735, Q766, Q803] [ADR-2Z2D](../decisions/entries/2Z2D-answers-of-the-owner-q800-to-q803-and-acceptance-of-the-v1-playback-spec.md).** `player-legacy-decode`
decodes the generated `mp4v` and H.264 sets of [`player-legacy.md`](player-legacy.md) section 10.5 in the page of the app, with the
routes of the product, and reports for each tile the values that 10.5 lists (the route and its reason,
`decoderInfo`, the seek, step and play times, `lateShare` at 12 s and 22 s, and the switch with
`switchAt`). The row is `record-only`: no target until the owner sets one. Its values are in
`details.player_legacy_decode`, not in `numbers`. Its `module` is the name of the pipeline item
(3.6.10). It needs the page of the app: a run with no app page gives `not-run` `no-ui`. Until the code
of the v1 player exists, its name is in `details.not_built` [A].

**The take: five rows become two [U Q598].** The contract keeps one check for each test that can fail [C 3.4].
Each test of the five old rows keeps a check that carries its failure:

| Old row | Its test | The check that carries its failure now |
|---|---|---|
| `group:take:finished` | The manifest has `state` `"finished"` and no `take_error`. | `group:take:finished`, no change |
| `group:take:csv-rows` | Each CSV reads with `sidecar.read_strict` and has the frame count of the take as its row count. | `<label>:records:rows-complete` of that camera, `fail` `rows-differ` [U Q627, MEE1 16] |
| `group:take:no-missing` | No live camera has a `missing` row; no `camera_dead`, no `camera_file_short`. | `<label>:records:rows-complete` of that camera, `fail` `missing-rows` (a dead camera and a short file give `missing` rows) |
| `group:take:frame-count` | The frame count is at least 80 % of 3 s times the mode rate. | `group:take:rate`, `fail` `too-few-frames`: the rate needs enough frames to judge [U Q627, MEE1 16] |
| `group:take:rate` | The take rate is within the limit of the mode rate. | `group:take:rate`, `fail` `group-rate-off` |

`<label>:records:rows-complete` is one test: each frame of the take has a present row in the CSV of that camera.
The same two rows replace the five rows of `group:take-30` and `group:take-60` (6.1, 8.2) [U Q627, MEE1 16].

**Rows that go [U Q591 to Q599].** `<label>:detect` (its facts are in `details.cameras[].modes`; it is
`record-only`, so it carries no test, and `<label>:detect:mjpg-mode` carries the one detect test of a named
camera); `<model>:units` (`details.cameras` gives the units); the seven `<model>:gate:<step>`; the three take rows
above; each `not-built` row of a check with no code; each `same-model` row; the filled `not-run` rows that
`<label>:not-reached` replaces.

#### 3.6.3 The `details` objects

| Key | Form | Content |
|---|---|---|
| `details.cameras` | list, one item for each unit of the run, in the detection order | The verdict, the names, the inventory of 3.5.5 and the exposure facts of 3.5.9. |
| `details.steps` | list, one item for each step that started | The time line and the CPU (3.5.4, 3.5.8). |
| `details.limits` | object | Each limit of a pass rule of the level, one time. |
| `details.not_built` | object `{"camera": [...], "run": [...]}` | The names of the checks with no code [U Q591]. |
| `details.gates` | list, one item for each `<model>:gate` and `pipeline:gate` that is not `pass` (full only) | The first required check that did not pass [U Q597]. |
| `details.pipeline` | object `{"failed", "reason"}` | The cause of the pipeline verdict (3.6.10) [U Q627, MEE1 27]. The result is in the summary item only. |
| `details.backend`, `os_key`, `abi`, `cpu_logical`, `logs_kept` | as today, 3.5.8, 3.5.11 | |

**`details.cameras[]`, the verdict of a unit.** The contract owner requires each `reason` to be a reason code
or `null` [C 6 rule 9]. A result in `details` gives no evidence [C 7].

| Key | Values | Rule |
|---|---|---|
| `result` | `pass`, `fail`, `partial`, `skipped` | The four rules of the summary item (3.4), applied to the checks of this unit only [U Q627, MEE1 14]. |
| `failed` | a check name without `<label>:`, or `null` | The first check of the unit, in the order of `checks`, whose result is not `pass` and not `record-only` [U Q627, MEE1 14]. `null` when the result is `pass`. |
| `reason` | a reason code, or `null` | The reason of the check that `failed` names. |
| `name_usb` | a string of the name rule of 9.4, or `null` | Only for a unit whose USB id is not in the list of known cameras and whose firmware text has no Apple word (9.4) [U Q596]. The display name of the OS is not copied [U Q628]. |
| `usb3_capable` | see 3.6.13 | 3.6.13. |

The other keys are in 3.5.5 and 3.5.9. A unit that the run did not check (a `reviewed` model) has no item.

**`details.steps[]`.** Each item has `step`, `t_start_s` and `seconds` (3.5.4). The items `open` and `take` also
have `cpu_cores_used` and `cpu_share_p95` (3.5.8). The step names [U Q627, MEE1 12]: `detect`, `open`, `retry`, `ready`,
`settings`, `take`, `checks` (the checks that only compute), `close`, `recheck` (phase G); in `full` also one item
for each later phase that started (`full-c`, `full-d`, `full-e`, `full-f`). The sum of `seconds` shows the time of
the run against its budget of 30 s (4.1).

**`details.limits` [U Q627, MEE1 13].** The keys and the values of today:

| Level | Keys and values |
|---|---|
| both | `rate_tolerance` 0.03 (4.2); `exposure_open` -7 and `exposure_changed` -8 (4.3), and on a route with no time unit `exposure_open_steps` 5 and `exposure_changed_steps` 4; `take_frames_min` 0.8 (4.5); `take_rate_tolerance` 0.02 for a take under 10 s, else 0.01 (3.6.6); `dark_luma` 24, `bright_luma` 230 (4.6); `long_interval_periods` 1.5 (3.5.6); `minutes_free_min` 5 [U Q613]; `in_step_ms` one frame period of `<base>`, 33.3 at 30 fps, not calibrated [U Q616] |
| full | `luma_ratio_time_unit` 0.85, `luma_ratio_unitless` 0.97 (4.3); `near_arrival_p5_ms` -50 (10.2, not calibrated) |

A row holds its value, and `details.limits` holds its limit. A limit that is "not calibrated" in this spec stays
"not calibrated" here.

**`details.not_built` [U Q591; Q627, MEE1 5].** `camera` holds the camera checks with no code, each without `<label>:` and
with the word `base` in place of the mode of `<base>` (for example `exposure:base`), each name one time. `run`
holds the group, system and self checks with no code. Both lists are sorted. A list with no name is `[]`.

**`details.gates[]` [U Q597; Q627, MEE1 15].** One item for each gate that is `fail`, or `not-run` for a reason other than
`not-built` (a gate that only waits for a check with no code has no item: `details.not_built` tells it). Each
item: `gate` (the name `<model>:gate` or `pipeline:gate`), `failed` (the
full name of the first required check, in the order of `checks`, that is `fail`; else the first one that is not
built, as in `details.not_built`; else the first one that is `not-run`) and `reason` (its reason code, `not-built`
for a check with no code).

#### 3.6.4 The full report is not a production sign-off yet [U Q599, Q610]

The user decided: the full gate is not a production sign-off until three checks are built and in the gates: the
open and close cycles (`<label>:cycles`), a take of 30 s (`group:take-30`), and all cameras together under USB
contention (`group:contention` and `group:open`) [U Q599]. The full pass of a model needs the cycles; the full
pass of the pipeline needs the take of 30 s and the check of all cameras together [U Q610]. Until then:

- **Gate not complete [U Q610; the form is A, from the contract owner].** `<model>:gate` and `pipeline:gate` are
  `not-run` with the common code `not-built` [C 5.3] while a check that they require is not built (3.6.2). In
  `full`, an item whose checks all passed is `partial`, never `pass`: certify never writes `pass` on an item of a
  full report while its sign-off checks are missing. An item with a failed check stays `fail`. A `partial` item
  whose `gate` is not `pass` gives no reviewed row [C 7.2]. No new code and no new field is needed.
- **The local record [U Q610, A].** The row of a model and the row of the pipeline (3.6.10) of a full run get
  the `item` of the report (`partial`) and the `gate` object of 2.5, with one more key `"sign-off": "not-built"`.
  The local pass of 11.3 needs each value of `gate` `pass`, so such a row is no local pass. When the three checks
  are built, the key holds the result of the gate.
- **The plan [U Q610].** The plan of full states what the run does today: `seconds_estimate` from the built
  checks (about 30 s: the quick estimate and 5 s), and `risks` holds no sentence of a check that is not built.
  Today no built check of full opens a camera more than one time, so `risks` is empty [U Q627, MEE1 17]. The sentences of 8.4
  come back with the checks of phase F. The review saw a plan of 565 s with the text "opens each camera many
  times" for a run of 28 s with one open [M review pass 2, finding 1].
- **Quick does not change [U Q610].** A quick pass stays a smoke-test pass: a valid quick report makes an item
  usable on that system [C 7.2].
- When the three checks are built and in the gates, a gate can be `pass`, and the full item can be `pass`.

#### 3.6.5 The size bound [U Q627, MEE1 19]

- The contract owner asks for a hard bound of the `modes` list, in code, with a test. The bound: at most 32
  strings, each at most 48 characters (3.5.5). With more modes, the code keeps the 32 of the largest area and
  writes `modes_cut`. A mode string over 48 characters is left out and counted in `modes_cut`.
- The review proposed 64 KiB for the module. Its arithmetic: its estimate for a full report of eight cameras is
  63.4 kB, which is 97 % of 65,536 bytes. That estimate uses fake cameras with one mode each and no failure facts.
  With the gate cut, the second pass gives about 52 kB [M + J]. Thus 64 KiB holds a typical report, but not a
  report with each field at its longest form: 32 modes of 48 characters add about 1.6 kB for each camera, so
  about 13 kB for eight cameras.
- The bound: a module report written with `json.dumps(report, indent=1)`, with eight cameras and each field at
  its longest form (32 modes of 48 characters, each failure key, each warning, each camera failed), is at most
  96 KiB (98,304 bytes) for full and at most 64 KiB (65,536 bytes) for quick [U Q627, MEE1 19, not calibrated]. With the
  skellytracker full module of about 90 kB, the file stays under the relay limit of 256 KiB.
- The bound of 3.5.12 (128 KiB and 48 KiB for four cameras) is replaced.

#### 3.6.6 Fixes of the code that the reviews found

Each fix has its test in section 17. They are faults of the built code, so they need no decision of the user,
except where a mark says so.

1. **B1** (3.6.1): the `fail` row of a camera that leaves the run between two steps, and `gate:no-hang` that
   reads it.
2. **The commit and the tree state** (3.5.2): write `package.commit` and `package.tree_modified`, and add
   `no-commit` and `modified-tree` only when they apply. Today the code adds both to each report.
3. **The schema id**: `skellycertify.report/1.7.0` (3.6.1).
4. **Counters since the open on take rows** [U Q573]: each counter of the `records`, `clock`, `sequence` and
   `time-gaps` rows is the change in the take window, also `frames` and `discontinuity_flags` (3.5.1).
5. **`clock:near-arrival` cannot fail** [U Q627, MEE1 22]: the sample time is always before the arrival, so each value is
   negative, and the check reads `abs(p95) <= 200 ms`, which is the value nearest to zero [M review pass 2: p5
   about -16.5 ms, p95 about -0.25 ms on two cameras]. The new rule judges the far side:
   `sample_minus_arrival_p5_ms >= near_arrival_p5_ms` (-50 ms, 1.5 frame periods at 30 fps, not calibrated);
   else `fail` `sample-too-early`. `clock:before-arrival` keeps `later_than_arrival` 0. Q585 does not change.
6. **The take rate limit** [U Q627, MEE1 23]: the take rate is the frame count divided by the elapsed time [U Q609]. The
   arrival grid of 16 ms gives an error of up to one step at each end: about 1.1 % at most, about 0.5 % in
   practice, over a take of 3 s [M review pass 2: 29.92 and 29.99 fps for the same cameras]. The limit of 1 % is
   the size of that error, so a false `group-rate-off` is possible. The limit becomes 2 % for a take under
   10 s and stays 1 % for a take of 10 s or more (`group:take-30` has an error of about 0.1 %). A longer quick
   take would cost the budget of 30 s, so the limit changes, not the window.
7. **The spread** [U Q616]: `spread_p50_ms` and `spread_p95_ms` jump by whole grid steps between runs (44.5, 15.05
   and 7.96 ms for the same cameras) [M review pass 2], and no limit judges them. They move from
   `group:take:finished` to the `record-only` check `group:in-step` of 3.6.11, with their limit shown in
   `details.limits`.
8. **The plan total and `session:exit`** (3.6.1): the plan counts `session:exit`; the progress said 64 of 63.
9. **Leave a camera out before the detection touches it** [U Q627, MEE1 25]: today the detection of the run reads the modes of
   each attached camera, and that read activates each camera, also a camera that is known dead. The option
   `cameras` (2.4) filters only after the detection (`run.py` `_detect` with `modes=True`). The fix: the run
   first lists the cameras with no activation, as the plan does (`detect_media_foundation_cameras(modes=False)`,
   9.1). It then applies `cameras`, and it reads the modes only of the selected cameras. The labels of the plan
   and of the run come from the same list, so a caller leaves a camera out by its label from
   `certify_plan(...)`. The product detection needs a way to read the modes of a part of the devices [NV].
10. **The product log line with a path** (3.5.11): a fault of the product, open work.

The product decisions of the user of 2026-11-23 that certify reads: the restore record of the camera settings is
kept on disk, so a restore survives a kill of the server [U Q608] (a later fix round; the rule of
`camera-not-restored` in 8.3 does not change here); the headline frame rate of a take is the frame count divided
by the elapsed time, and the median is only for the figures of each frame interval [U Q609] (4.5).

#### 3.6.7 Build order [U Q627, DBF8 17]

The steps are small. Each step passes its own tests: a test of the list below runs in its new form from its
step on, and a part of a test that needs a later step joins at that step (the column "Parts that join later")
[U Q627, DBF8 17, review finding 4].

| Step | Change | Tests | Parts that join later |
|---|---|---|---|
| 1 | B1 (3.6.6 item 1): the `fail` row, its reason and `module`, and `gate:no-hang` with `stalled`; P7 and the commit, the tree state and the two evidence codes (3.5.2) | T-CERT-93, T-CERT-77, T-CERT-27 | T-CERT-93: the `not-reached` row of the other checks at step 4; `details.cameras[].failed` at step 8; the model item `fail` of a B1 row at step 6; `exit_code` 3 from the failure of the status now, from D-5 after P4 (step 10) [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) |
| 2 | The schema id 1.7.0, also in the validator | T-CERT-03 (schema), the validator tests | T-CERT-03 pipeline item: step 6 |
| 3 | `details.not_built` and the plan with no not-built check; no `same-model` rows; the plan total with `session:exit` | T-CERT-91, T-CERT-01, T-CERT-103 | |
| 4 | `<label>:not-reached` and the `done` count | T-CERT-92, T-CERT-17 | |
| 5 | Quick with eleven checks for each camera (with `live-at-close`, Q646, [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) item 15), full with the six; `group:take` with two rows; `system:recording-space` and `group:in-step`; no `<label>:detect`, no `<model>:units` | T-CERT-07, T-CERT-99, T-CERT-26, T-CERT-110, T-CERT-111 | T-CERT-07: the pipeline item at step 6; T-CERT-26: `details.cameras` at step 8; T-CERT-99: the cases of a rate 1.5 % off at step 11; T-CERT-111: `details.limits.in_step_ms` at step 9 [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) |
| 6 | The two verdicts of 3.6.10: the pipeline item, the kind and the `module` of each check, the count of the models, the B1 and wedge rules, no `module` with no item, `details.pipeline`, the pipeline row of the record | T-CERT-105 to T-CERT-109, T-CERT-123, T-CERT-125, T-CERT-126, T-CERT-44 | |
| 7 | The gates: two rows for each model and `pipeline:gate`, each wired by `module`; `details.gates`; "gate not complete" with `not-built`, `partial` items and `"sign-off": "not-built"` in the record; the plan of full | T-CERT-65, T-CERT-98, T-CERT-47, T-CERT-124 | |
| 8 | `details.cameras` with the verdict and the names of 9.4; the list of known cameras; the record key with no USB id | T-CERT-94, T-CERT-95, T-CERT-100, T-CERT-127 | |
| 9 | One number, one row; no zero counts on a `pass` row; `details.limits`; the rounding; no `clock:base` on Media Foundation; one row of the sequence pair; `report:rules` with the validator in the package | T-CERT-96, T-CERT-87, T-CERT-128, T-CERT-117 | |
| 10 | The product changes P3, P1, P2, P4 of 3.5.15, then the rest of 3.5.15 in its order, in the slim form | the tests of 3.5.15 | |
| 11 | The fixes 3.6.6 items 4 to 7 and 9 | T-CERT-82, T-CERT-101 to T-CERT-104 | |
| 12 | The size bound and the bound of `modes` | T-CERT-89, T-CERT-97 | |
| 13 | The quick additions of Q624: `records:mkv-opens`, `system:memory`, `system:camera-access`, the notice of the USB link; `bursts`; the drops (a) to (g) | T-CERT-112 to T-CERT-115, T-CERT-118, T-CERT-121 | |
| 14 | The full additions of Q624: `group:take-again`, `system:power`, `system:timer` | T-CERT-116, T-CERT-119, T-CERT-120 | |

**The validator.** `skellycam/tests/certify/report_rules.py` changes with the steps: `SCHEMA` becomes
`skellycertify.report/1.7.0` (step 2); `ROLL_UP_REASONS` gets `not-built` (step 7), and a roll-up row `not-run`
`not-built` is valid only when a check that it requires is in `details.not_built`; the rules of 3.6 join at step
9 (T-CERT-87), when the validator moves into the package (3.6.12).

**The order replaces Q575 [U Q626].** The user decided on 2026-11-23 (Q575 of
[ADR-10HT](../decisions/entries/10HT-acceptance-of-the-certify-report-field-choices-and-the-build-order.md)):
"build order: product changes first (P3, P1, P2, P4), then C1 and later". This order puts the product changes at
step 10. The recommendation: keep this order. Reason: steps 1 to 9 make every report valid as evidence (the
commit), stop the hidden fault B1, and change the shape that the product changes then fill; with P3 to P4
first, each later step of the shape changes the new fields again. The user agreed (Q626, [ADR-63D9](../decisions/entries/63D9-decisions-of-the-user-on-the-processors-the-build-order-and-the-certify-choices.md)):
this order replaces the order of Q575.

**The tests of today that change.** The test files `skellycam/tests/certify/` hold 52 test functions. A scan of
their names and assertions [NV] shows that about 25 of them test a row or a key that 3.6 changes, so they change
at the step of that row: `test_t_cert_01_the_plan`, `test_t_cert_03_07_17_26_a_quick_run_with_good_fakes`,
`test_t_cert_05_and_70_camera_names`, `test_t_cert_08_and_17_a_slow_camera_and_a_progress_that_raises`,
`test_t_cert_10_a_camera_in_use`, `test_t_cert_12_a_camera_that_hangs_at_the_open`, `test_t_cert_13_settings_stick`,
`test_t_cert_14_native_jpeg`, `test_t_cert_16_a_cancel_during_the_take`, `test_t_cert_24_over_budget`,
`test_t_cert_44_the_summary_item_rule`, `test_t_cert_47_a_full_run_and_the_local_pass`,
`test_t_cert_65_and_68_the_gate_roll_ups`, `test_the_timestamps_gate_of_a_source_that_cannot_tell_its_clock`,
`test_clock_base_of_a_source_that_cannot_tell_its_clock`, `test_review_1_a_hang_after_the_open_gives_camera_wedged`,
`test_review_2_and_5_a_cancel_during_the_open_in_a_session_child`,
`test_review_5_and_6_the_end_of_the_budget_during_the_open`, `test_review_7_a_cancel_keeps_the_checks_that_had_ended`,
`test_review_13_only_the_base_mode_counts_for_the_item_and_the_gate`, `test_format_1_6_0_abandon`,
`test_the_validator_rules_of_the_review_and_of_1_6_0`,
`test_review2_n1_the_live_change_never_reopens_a_wedged_camera`,
`test_review2_n2_a_camera_with_a_running_step_at_a_cancel_is_not_reopened`,
`test_review2_n5_an_abandon_that_comes_late_stores_no_row`.

#### 3.6.8 Rows and bytes, today and after

Media Foundation, one model for each camera. "Today" is the code at `54d915c59`. "After" is this section.

| Rows | Quick today | Quick after | Full today | Full after |
|---|---|---|---|---|
| Each camera | 17 | 12 | 45 (23 of them `not-built`) | 22 |
| Each model | 1 (`units`) | 0 | 10 (`units`, 9 gate rows) | 2 |
| The run | 9 | 8 | 41 (35 of them `not-built`) | 12 (with `pipeline:gate`) |
| `session:exit` | 1 after a hang at exit | the same | the same | the same |
| 3 cameras | 63 (64 measured, with `session:exit`) | 44 | 206 (207 measured, with `session:exit`) | 84 |
| 4 cameras | 81 | 56 | 261 | 108 |
| 8 cameras | 153 | 104 | 481 | 204 |
| Rows of a camera that failed at the open in the Markdown table [C 4.2 part 8] | 13 | 4 | 47 | about 6 |

| Bytes (`indent=1`) | Quick today | Quick after | Full today | Full after |
|---|---|---|---|---|
| 1 camera | 8 kB | 7 kB | 17 kB | 12 kB |
| 3 cameras, measured | 18,496 | 14.4 kB | 40,059 | 22.7 kB |
| 4 cameras | 24 kB | 18 kB | 52 kB | 30 kB |
| 8 cameras | 46 kB | 33 kB | 98 kB | 56 kB |

- The row counts are computed from the plan, with no `session:exit`: quick 18 N + 9 today and 12 N + 8 after; full
  55 N + 41 today and 24 N + 12 after, for N cameras of N models. The real reports of 2026-11-23 (3 cameras) had 64
  and 207 rows with `session:exit`, which agrees [M review pass 2]. "After" has the row `<label>:live-at-close`
  ([U Q646]; the row: [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) item 15). A camera that fails at the open has four rows in the table: `opens`, `rate`, `modes:granted:<base>` and
  `not-reached` (3.6.1) [U Q648]; in full also `<model>:gate:no-hang` and `<model>:gate`.
- The bytes "today" for 3 cameras are measured; the others are the first-pass measurements on fake cameras,
  scaled by the real-to-fake ratio (0.90 quick, 0.94 full) [M review pass 2]. The bytes "after" are estimates of
  the review (`slim.py` on the real reports, plus an estimate of the slim fields of 3.5, without the gate step
  rows) [estimate, NV]. They do not count the names of 9.4 (about 60 bytes for each new USB id) and the pipeline
  item and its longer `module` on the pipeline rows (about 0.1 kB for each camera and 0.2 kB for the run).
- "After" counts the checks of 3.6.12 as built, and the checks of sections 5 to 8 as not built. They add about
  0.15 kB for each camera in quick and 0.3 kB in full, and about 0.6 kB (quick) and 1.2 kB (full) for the run
  [estimate].
- The examples of 3.6.9 show the shape before Q624 and Q646: they do not show the rows of 3.6.12. Each camera also
  has the row `<label>:live-at-close` ([ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) item 15), and each `not-reached` count of a camera is one higher.
- With the fields of 3.5 as first specified, the review estimated 38.6 kB for quick and 74.8 kB for full with four
  cameras [estimate].

#### 3.6.9 Examples

Made-up values near the real runs; no real serial, path, host name or user name. `"...": "..."` marks a part
that is left out. `P` stands for the pipeline name `Windows, Media Foundation, native JPEG` (3.6.10); a real report
writes the name in full.

**Quick, four cameras, the generic camera fails its rate check.**

```json
{"schema": "skellycertify.report/1.7.0", "kind": "quick", "created_utc": "2026-11-23T18:13:51Z",
 "package": {"name": "skellycam", "version": "2.0.0-alpha.6", "commit": "0123456789abcdef0123456789abcdef01234567", "tree_modified": false},
 "host": {"...": "..."},
 "summary": [{"group": "component", "name": "P", "device": null, "result": "pass"},
             {"group": "camera", "name": "Logitech C930e", "device": "046d:0843", "result": "pass"},
             {"group": "camera", "name": "Logitech C922", "device": "046d:085c", "result": "pass"},
             {"group": "camera", "name": "Razer Kiyo Pro", "device": "1532:0e05", "result": "pass"},
             {"group": "camera", "name": "USB Camera", "device": "4c4a:4a55", "result": "fail"}],
 "checks": [
  {"name": "detect", "result": "pass", "reason": null, "module": "P", "numbers": {"cameras": 4, "virtual": 4, "modes_read": true}},
  {"name": "cam.media-foundation.046d-0843.0:detect:mjpg-mode", "result": "pass", "reason": null, "module": "Logitech C930e"},
  {"name": "cam.media-foundation.046d-0843.0:opens", "result": "pass", "reason": null, "module": "Logitech C930e",
   "numbers": {"seconds_to_first_frame": 0.447}},
  {"name": "cam.media-foundation.046d-0843.0:rate", "result": "pass", "reason": null, "module": "Logitech C930e",
   "numbers": {"measured_fps": 30.0, "luma_mean": 106.4, "jpeg_kb_mean": 129.6, "interval_max_ms": 48.1,
    "interval_max_at_s": 6.71}},
  {"name": "cam.media-foundation.046d-0843.0:modes:granted:1280x720@30", "result": "pass", "reason": null, "module": "Logitech C930e"},
  {"name": "cam.media-foundation.046d-0843.0:settings-stick:readback", "result": "pass", "reason": null, "module": "Logitech C930e",
   "numbers": {"exposure_readback_open": -7, "exposure_readback": -8, "exposure_unit": "log2-s", "control_path": "iam"}},
  {"name": "cam.media-foundation.046d-0843.0:settings-stick:holds", "result": "pass", "reason": null, "module": "Logitech C930e",
   "numbers": {"exposure_later": -8}},
  {"name": "cam.media-foundation.046d-0843.0:native-jpeg:format", "result": "pass", "reason": null, "module": "Logitech C930e",
   "numbers": {"dht_inserted": 0, "dqt_distinct": 1, "dqt_sha256": "<64 hex>"}},
  {"name": "cam.media-foundation.046d-0843.0:native-jpeg:valid", "result": "pass", "reason": null, "module": "Logitech C930e",
   "numbers": {"frames_checked": 120}},
  {"name": "cam.media-foundation.046d-0843.0:records:rows-complete", "result": "pass", "reason": null, "module": "P",
   "numbers": {"rows": 90, "take_fps": 29.97, "interval_p95_ms": 48.0, "interval_max_ms": 64.1,
    "interval_max_at_s": 17.87}},
  {"name": "cam.media-foundation.046d-0843.0:records:blocks-decode", "result": "pass", "reason": null, "module": "P"},
  {"...": "the ten rows of the C922 and of the Kiyo Pro"},
  {"name": "cam.media-foundation.4c4a-4a55.0:detect:mjpg-mode", "result": "pass", "reason": null, "module": "USB Camera"},
  {"name": "cam.media-foundation.4c4a-4a55.0:opens", "result": "pass", "reason": null, "module": "USB Camera",
   "numbers": {"seconds_to_first_frame": 0.088}},
  {"name": "cam.media-foundation.4c4a-4a55.0:rate", "result": "fail", "reason": "rate-low", "module": "USB Camera",
   "numbers": {"measured_fps": 25.74, "luma_mean": 141.3, "interval_max_ms": 48.2, "interval_max_at_s": 6.12, "long_intervals": 0}},
  {"name": "cam.media-foundation.4c4a-4a55.0:modes:granted:1280x720@30", "result": "pass", "reason": null, "module": "USB Camera"},
  {"name": "cam.media-foundation.4c4a-4a55.0:not-reached", "result": "not-run", "reason": "prior-check-failed",
   "module": "USB Camera", "numbers": {"checks": 6}},
  {"name": "system:recording-space", "result": "pass", "reason": null, "module": "P",
   "numbers": {"volume_kind": "fixed", "free_gb": 412, "minutes_free": 6870}},
  {"name": "group:take:finished", "result": "pass", "reason": null, "module": "P",
   "numbers": {"cameras": 3, "take_seconds": 3.14, "file_system": "ntfs", "take_warnings": []}},
  {"name": "group:take:rate", "result": "pass", "reason": null, "module": "P", "numbers": {"frame_count": 90, "rate": 29.96}},
  {"name": "group:in-step", "result": "record-only", "reason": null, "module": "P",
   "numbers": {"spread_p50_ms": 8.0, "spread_p95_ms": 8.1, "spread_source": "arrival"}}],
 "cleanup": [{"name": "release:cam.media-foundation.4c4a-4a55.0", "result": "fail", "reason": "camera-not-restored", "module": "USB Camera"}],
 "notices": [{"code": "camera-not-restored", "values": {"camera": "USB Camera"}}],
 "details": {"backend": "media-foundation", "os_key": "11 26H2", "abi": "lp64", "cpu_logical": 28, "logs_kept": 4,
  "pipeline": {"failed": null, "reason": null},
  "limits": {"rate_tolerance": 0.03, "exposure_open": -7, "exposure_changed": -8, "exposure_open_steps": 5,
   "exposure_changed_steps": 4, "take_frames_min": 0.8, "take_rate_tolerance": 0.02, "dark_luma": 24,
   "bright_luma": 230, "long_interval_periods": 1.5, "minutes_free_min": 5, "in_step_ms": 33.3},
  "steps": [{"step": "detect", "t_start_s": 0.0, "seconds": 0.9},
            {"step": "open", "t_start_s": 1.0, "seconds": 6.59, "cpu_cores_used": 0.84, "cpu_share_p95": 11.2},
            {"step": "ready", "t_start_s": 7.6, "seconds": 1.2},
            {"step": "settings", "t_start_s": 8.8, "seconds": 3.62},
            {"step": "take", "t_start_s": 12.5, "seconds": 4.71, "cpu_cores_used": 1.31, "cpu_share_p95": 18.4},
            {"step": "checks", "t_start_s": 17.2, "seconds": 1.4},
            {"step": "close", "t_start_s": 18.6, "seconds": 1.2}],
  "cameras": [
   {"label": "cam.media-foundation.046d-0843.0", "result": "pass", "failed": null, "reason": null, "usb_link": "USB 2", "...": "..."},
   {"...": "the C922 and the Kiyo Pro"},
   {"label": "cam.media-foundation.4c4a-4a55.0", "result": "fail", "failed": "rate", "reason": "rate-low",
    "name_usb": "USB Camera", "usb_link": "USB 2", "bcd_usb": "0200", "bcd_device": "0100",
    "controller": 0, "controller_id": "8086:7ae0", "hub_depth": 0, "driver_kind": "uvc-inbox",
    "driver_version": "10.0.26100.1150", "exposure_before": -6, "exposure_before_auto": true,
    "exposure_min": -11, "exposure_max": -2, "exposure_step": 1, "exposure_default": -6, "sample_time_kept": true,
    "modes": ["MJPG 640x480@30", "MJPG 1280x720@30", "MJPG 1920x1080@30"]}],
  "not_built": {"camera": [], "run": ["group:open", "self:hang-100ms:gap", "self:hang-100ms:hard-end"]}},
 "evidence": {"valid": true, "reasons": []}}
```

Notes:

- The summary has two verdicts (3.6.10): the pipeline item `pass` (three models recorded), and one item for each
  model. The generic model fails on its own camera check (`rate`); the pipeline is not blamed.
- A passing camera has ten rows. The failed camera has its rows up to the cause, the `modes:granted` row of the
  same apply, and one `not-reached` row for its six other checks.
- The Markdown table "Checks that did not pass" holds two rows: the `rate` row and the `not-reached` row
  [C 4.2 part 8]. The summary and its tables show only the item results; the cause of a failed model shows only
  through the reason code of its failed check in that table [C 4.2].
- The generic camera has no entry in the list of known cameras (9.4), so its name comes from the device, and
  `details.cameras` holds both strings.

**Full, the same four cameras.** The report holds the rows of quick and these rows for each camera, two rows for
each model and `pipeline:gate`. Only the new parts are shown.

```json
{"kind": "full",
 "summary": [{"group": "component", "name": "P", "device": null, "result": "partial", "gate": "pipeline:gate"},
             {"group": "camera", "name": "Logitech C930e", "device": "046d:0843", "result": "partial",
              "gate": "cam.media-foundation.046d-0843:gate"},
             {"...": "..."},
             {"group": "camera", "name": "USB Camera", "device": "4c4a:4a55", "result": "fail",
              "gate": "cam.media-foundation.4c4a-4a55:gate"}],
 "checks": [
  {"...": "the rows of quick"},
  {"name": "cam.media-foundation.046d-0843.0:native-jpeg:not-reencoded", "result": "pass", "reason": null, "module": "P"},
  {"name": "cam.media-foundation.046d-0843.0:native-jpeg:size", "result": "pass", "reason": null, "module": "Logitech C930e"},
  {"name": "cam.media-foundation.046d-0843.0:native-jpeg:source-equals-ring", "result": "pass", "reason": null,
   "module": "P", "numbers": {"frames_compared": 30}},
  {"name": "cam.media-foundation.046d-0843.0:settings-stick:image-effect", "result": "pass", "reason": null,
   "module": "Logitech C930e", "numbers": {"luma_at_m8": 69.2, "luma_ratio": 0.65,
    "gain_value_at_m7": 32, "gain_auto_at_m7": false, "gain_value_at_m8": 32, "gain_auto_at_m8": false}},
  {"name": "cam.media-foundation.046d-0843.0:records:gaps-explained", "result": "pass", "reason": null,
   "module": "P", "numbers": {"replaced": 2}},
  {"name": "cam.media-foundation.046d-0843.0:clock:before-arrival", "result": "pass", "reason": null,
   "module": "P"},
  {"name": "cam.media-foundation.046d-0843.0:clock:near-arrival", "result": "pass", "reason": null,
   "module": "P", "numbers": {"sample_minus_arrival_p5_ms": -16.47, "sample_minus_arrival_p50_ms": -0.35, "jitter_p95_ms": 14.67}},
  {"name": "cam.media-foundation.046d-0843.0:time-gaps", "result": "pass", "reason": null, "module": "P"},
  {"name": "cam.media-foundation.046d-0843:gate:no-hang", "result": "pass", "reason": null, "module": "Logitech C930e"},
  {"name": "cam.media-foundation.046d-0843:gate", "result": "not-run", "reason": "not-built", "module": "Logitech C930e"},
  {"...": "the same for the C922 and the Kiyo Pro"},
  {"name": "cam.media-foundation.4c4a-4a55.0:not-reached", "result": "not-run", "reason": "prior-check-failed",
   "module": "USB Camera", "numbers": {"checks": 15}},
  {"name": "cam.media-foundation.4c4a-4a55:gate:no-hang", "result": "pass", "reason": null, "module": "USB Camera"},
  {"name": "cam.media-foundation.4c4a-4a55:gate", "result": "fail", "reason": "gate-check-failed", "module": "USB Camera"},
  {"name": "pipeline:gate", "result": "not-run", "reason": "not-built", "module": "P"}],
 "details": {"pipeline": {"failed": "group:take-30:finished", "reason": "not-built"},
  "limits": {"...": "the limits of quick", "luma_ratio_time_unit": 0.85, "luma_ratio_unitless": 0.97,
   "near_arrival_p5_ms": -50},
  "gates": [{"gate": "cam.media-foundation.4c4a-4a55:gate", "failed": "cam.media-foundation.4c4a-4a55.0:rate", "reason": "rate-low"}],
  "not_built": {"camera": ["auto-exposure:holds-rate:base", "auto-exposure:searched:base", "auto-off:ae", "...": "...",
                           "cycles", "exposure:base", "in-use", "settings-stick:each-open", "timestamps"],
                "run": ["group:contention", "group:open", "group:take-30:finished", "group:take-30:rate", "...": "...",
                        "system:usb"]}},
 "evidence": {"valid": true, "reasons": []}}
```

Notes:

- Each passing camera has 19 rows: the ten of quick, the six of 3.6.2, two clock rows (no `clock:base` on Media
  Foundation) and `time-gaps` (the source gives no sequence number). Each model has two gate rows; the run has
  `pipeline:gate`.
- Each item that passed its checks is `partial`, and each gate is `not-run` with `not-built`, until the sign-off
  checks of 3.6.4 are built [U Q610]. The report is valid as evidence, but no item gives a reviewed row
  [C 7.2].
- The `not-reached` row of the generic camera stands for its six quick checks, its six full checks, its two clock
  checks and `time-gaps` after the rate (15). Its gate is `fail`, and `details.gates` names the cause.
- The `"...": "..."` items in the lists of `not_built` are only for this example: a real list holds strings only.

#### 3.6.10 Two verdicts: the pipeline and each camera model [U Q611]

The user decided: "there are two things that can pass - the pipeline itself, and specific camera models ... if a
pipeline works for say 3 models of camera connected, but 1 camera model fails ... I would deem that as the
pipeline works and is good for use with 3 cameras, and the 4th camera may need special attention, or just isn't up
to the task" [U Q611].

**The pipeline item.** The pipeline is the capture path of skellycam on this system: the OS, the capture backend,
the native JPEG path, the ring and the recorder. The summary gets one item for it, before the camera items. The
contract owner confirmed its form [C 3.7]:

- `{"group": "component", "name": "<pipeline name>", "device": null, "result": ...}`. `device` is present and
  `null`. A group `pipeline` is not allowed: the relay refuses it. The allowed groups are `ep`, `gpu-jpeg`,
  `camera`, `benchmark` and `component`.
- The name [U Q627, MEE1 27]: `<OS>, <backend>, native JPEG`, with `<OS>` from `host.os.name` (`Windows`, `Linux`, `macOS`) and
  `<backend>` one of `Media Foundation`, `V4L2`, `AVFoundation`. Example: `Windows, Media Foundation, native
  JPEG` (38 characters; the limit is 80).
- In `full` the item has `"gate": "pipeline:gate"` [C 3.7]. [C 7.2] applies as for a camera item.
- The Markdown prints the item in the component table `| Module | Result |`, before the camera table
  [C 4.2 part 6].
- The item has no `reason` (the contract allows a reason only for `skipped`). `details.pipeline` gives the cause:
  `result`, `failed` (the full name of the first check that the rule below gives to the pipeline and that did not
  pass) and `reason` (its reason code, or `not-decided-one-model` for rule e) [U Q627, MEE1 27].
- A run with no camera to check, and a refused run, have no pipeline item [U Q627, MEE1 27].

**The kind of each check.** Each check has one kind. The kind decides who the check counts against.

| Kind | Checks |
|---|---|
| camera | `detect:mjpg-mode`, `opens`, `rate`, `modes:granted:<mode>`, `native-jpeg:format`, `native-jpeg:valid`, `native-jpeg:size`, `settings-stick:readback`, `:holds`, `:image-effect`, `:each-open`, `live-at-close` ([ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) item 15); in full when built: `rate:<mode>`, `rate:<w>x<h>@60`, `exposure:<base>:readback`, `control:gain`, `control:focus`, `auto-off:*`, `group-open`, `cycles`; `<model>:gate:no-hang`; `<label>:not-reached`; the cleanup rows `release:<label>` |
| pipeline | `native-jpeg:not-reencoded`, `native-jpeg:source-equals-ring`, `native-jpeg:ring-equals-mkv`, `records:rows-complete`, `records:blocks-decode`, `records:gaps-explained`, `records:mkv-opens`, `clock:base`, `clock:before-arrival`, `clock:near-arrival`, `sequence`, `time-gaps`; the run checks `group:take-again` and `group:preview-during-take`, which count against the pipeline as a system check does, unless the rule below gives them to a model; in full when built: `identity:*`, `controls`, `controls:exposure-scale`, `auto-exposure:*`, `in-use` |
| system | `detect`, `system:recording-space`, `system:memory`, `group:take:finished`, `group:take:rate`, `session:exit`; in full when built: `group:cycles`, `group:restore-after-kill`, `group:take-30:*`, `group:take-60:*`, `group:open`, `group:contention`, `system:*`, `self:*`; the cleanup rows `delete-work-folder` and `write-record` |
| no verdict | the `record-only` checks (`group:in-step` [U Q616], `<label>:bursts` with the `module` of its model, `system:camera-access`, `system:power`, `system:timer`, `timestamps`, the sweeps); `report:rules` (its failure goes into `evidence.reasons`) and the macOS probes of 10.7, which keep the `module` `macOS probes` and count toward no item (10.4) |

**The rule [U Q611].** A check has one `module` [C 3.4]. The rule gives it. For one pipeline check (one name
without the label), the models that count are the models with at least one unit where that check judged
(`pass` or `fail`); a unit where the check is `not-run` or in a `not-reached` row does not count [U Q627, DBF8 11, review
finding 2]. A model "fails" the check when the check is `fail` on one of its units, and "passes" it when the
check is `pass` on each of its units that judged.

- (a) A camera check counts against the model of its camera: `module` = the name of the model item.
- (b) A pipeline check that fails on some models and passes on at least one other model counts against each
  failing model: the pipeline has shown that it works [U Q611, A: "each"]. Its `module` is the name of that
  model.
- (c) A pipeline check that fails on each model that counts, with two or more such models, counts against the
  pipeline: its `module` is the pipeline name, and it does not change the model items [U Q622].
- (d) A system check counts against the pipeline: its `module` is the pipeline name. A hang of the app, a fault of
  the disk, `session:exit` and each `self:*` and `system:*` check are system checks.
- (e) With one model that counts (one or more units of it), a pipeline check that fails cannot be given to
  either part. This is also the case of two models when the other model stopped early and did not judge the
  check. The model item fails (the row has `module` = the name of the model), the pipeline item is `partial`,
  and `details.pipeline.reason` is `not-decided-one-model` [U Q627, MEE1 27]. `pipeline:gate` cannot pass.
- A pipeline check that passes, or that is `not-run` for a reason of the pipeline, has `module` = the pipeline
  name [U Q627, MEE1 27]. A `not-run` pipeline check of a camera that could not go on is in its `<label>:not-reached` row.
- A B1 row (3.6.1: a product failure code of a camera, also on a pipeline check) counts against the model of
  its camera, and the model item is `fail` [U Q627, DBF8 12, review finding 5]. Rule (c) applies to B1 rows too: when each
  model that counts gives a B1 row in the same step, the rows have the pipeline name as `module`, and the
  pipeline item fails.
- A wedge of one camera does not fail another model [U Q627, DBF8 12, review finding 6]. When a camera wedges (`hung`,
  `crashed`, `stalled`, `device-removed`) in a step, a check of a camera of another model that fails in the same
  step keeps the `module` of its model, but it does not make that model `fail`: the model item is `partial`,
  and its item of `details.cameras` gets `"blocked_by": "<label of the wedged camera>"`. Example: case 1 of
  3.5.13, where the C922 fails `rate` during the wedge of the Kiyo Pro.
  - "The same step" is one item of `details.steps`: the checks that one progress message of a step started, from
    its `t_start_s` to the result of its last check. For the open, this is the one apply of all cameras, from the
    apply request to the end of the wait for the states (about 12 s with a wedge) [U Q627, DBF8 18].
  - A unit with `blocked_by` writes no row into the local record (2.5), so the app checks that model again at
    its next open. When each unit of a model is blocked, the model writes no row.
  - A failed row of a blocked unit counts neither for `<model>:gate` nor for the known-bad rule of 11.5: the gate
    reads it as `not-run`, so the gate is `not-run` with `gate-check-not-run`, never `fail`, and
    `details.gates` names no blocked row. Two systems with a wedge of a Kiyo Pro thus never make a C922
    known-bad.
- A row has `module` only when a summary item of that `name` exists in the report [C 3.4] [U Q627, DBF8 13, review finding
  7]. With no camera to check, and in a refused run, there is no pipeline item, so the run rows have no
  `module`.
- A check given to a model keeps its group of 3.4 for the model item: a failed `records` check makes the model
  `fail`.

**The pipeline item result [U Q627, MEE1 27].** The first rule that applies:

1. `fail`: a check whose `module` is the pipeline name is `fail`.
2. `partial`: rule (e) applied; or a check whose `module` is the pipeline name is `not-run` (except
   `self:hang-100ms:*` with `over-budget` in quick, 4.1); or in `full` the sign-off checks are not built (3.6.4).
3. `pass`: each other case.

**The model item.** The four rules of 3.4 apply to the checks whose `module` is the name of the model. A check
given to the pipeline does not change a model item [U Q622]. In `full`, 3.6.4 applies.

**The take when one camera stalls.** The stalled camera gets its B1 row or `<label>:records:rows-complete` `fail`
(`missing-rows` or `stalled`): rule (b) or the product code gives it to its model. `group:take:finished` and
`group:take:rate` are system checks. When one of them fails in the same take, it counts against that model, with
the `module` of that model, when the take error names the camera (`take_error_camera`) or when exactly one camera
of the take failed its `rows-complete`, and another model passed its `rows-complete` [U Q621]. Else it counts against
the pipeline.

**Example: three models pass, one model fails.** Four cameras of four models. The Kiyo Pro gives JPEG frames
whose MKV blocks differ from the ring (`native-jpeg:ring-equals-mkv` `fail` `jpeg-damaged`); the C922, the C930e
and the generic camera pass that check.

- Rule (b): the row has `module` `Razer Kiyo Pro`. The Kiyo Pro item is `partial` (a native JPEG check, not an
  open, rate or records check, 3.4). `<model>:gate` of the Kiyo Pro is `fail`.
- The pipeline item is `pass` in quick (the check is in full only, so quick does not see it) and `partial` in full
  today (3.6.4). The person reads: the pipeline works with three models, and the Kiyo Pro needs attention.
- If the same check failed on all four, rule (c) gives it to the pipeline: the pipeline item is `fail`, and the
  four model items keep the results of their own checks.

**Example: one model.** One C922. Its `records:rows-complete` fails with `missing-rows`.

- Rule (e): the row has `module` `Logitech C922`, the C922 item is `fail`, the pipeline item is `partial`, and
  `details.pipeline` is `{"result": "partial", "failed": "cam.media-foundation.046d-085c.0:records:rows-complete",
  "reason": "not-decided-one-model"}`. A second model in a later run can tell the two apart.

**The local record [U Q611, A].** A run writes one row for the pipeline beside the rows of the models (2.5):
`device` `"pipeline"`, with the backend, the OS key, the ABI, the level, `item` (the pipeline item) and, for
`full`, `gate`. It turns nothing on by itself (11.3). The local pass of a model on Linux and macOS also needs a
pipeline row of the same key with each `gate` value `pass` [U Q623].

#### 3.6.11 Changes to the test set [U Q612 to Q618]

The gap review of 2026-11-23 read the test set, not the report fields. The user decided seven of its proposals
on 2026-11-23 [U Q612 to Q618]. Each check below is not built, except where it says so.

- **One disk check [U Q612].** `system:disk-benchmark` merges into `system:disk` (6.2, 6.3). The check runs the
  real recorder with synthetic JPEG frames: 20 s at the real load, then 10 s at twice the load. It judges the
  write and hand-over delays (the rule of 6.2). There is no separate file of 1 GiB: this replaces the decision of
  the user of 2026-11-20 that the disk benchmark writes 1 GiB (6.3). The counts of cameras come from the measured
  JPEG size of each camera (`jpeg_kb_mean` and `measured_fps` of its `rate` row), not from fixed numbers.
- **The recording space, in quick [U Q613].** `system:recording-space` reads the kind of the volume of the
  recording folder and its free space, after the open and before the take.
  - `volume_kind`: `fixed`, `removable`, `network` or `unknown` (Windows `GetDriveType`; Linux and macOS from the
    mount table [NV]). The report holds the kind only: never a path, a share name or a volume label.
  - `minutes_free`: the free bytes divided by the sum of the bytes per second of the cameras that passed `rate`
    (`jpeg_kb_mean` x 1000 x `measured_fps`), in whole minutes. `free_gb` moves to this row.
  - `fail` with `disk-full` when `minutes_free` is less than `minutes_free_min` (5) of `details.limits`.
  - A `removable` or `network` volume does not fail the check. It gives the notice `recording-volume-not-fixed`
    with `{"kind": "<volume_kind>"}` [U Q627, MEE1 29]. Its text: "The recording folder is on a removable or network drive. A
    recording can lose frames there. Choose a folder on an internal drive."
- **Cycles [U Q614].** `<label>:cycles` runs 30 opens and closes of the product source for the first unit of
  each model, alone. `group:cycles` runs 10 opens and closes of the whole group [U Q627, MEE1 30: the name]. Together about
  one minute for each model. Known cost: on some runs this wedges a camera that is prone to wedges. The run then
  gives the notice `camera-wedged` ("please replug"), and the camera is not touched again in the run (2.3).
  `<model>:gate` requires `<label>:cycles`. `group:cycles` is a system check in `pipeline:gate`; when a camera
  wedges in it, it counts against the model of that camera, as for the take (3.6.10) [U Q627, MEE1 30].
- **The restore after a kill of the server [U Q615].** `group:restore-after-kill`: a kill of the main process
  during a stream, a new start, and a read of the controls of each camera: each control has its "before" value
  again. It is a pipeline check in `pipeline:gate`. It needs the "before" values on disk (Q608, product work of a
  later fix round). Until then it is in `details.not_built`.
- **Cameras in step [U Q616].** `group:in-step` reports the spread of the frames of one row across the cameras of
  the take (`spread_p50_ms`, `spread_p95_ms`, 1 decimal), from the sample times where `sample_time_kept` is true,
  else from the arrival times (`spread_source` `sample` or `arrival`). It is `record-only` for now: it fails
  nothing and is in no gate. Its limit stands in `details.limits` (`in_step_ms`, one frame period, not
  calibrated). It is in quick and in full, from the take, at no cost [U Q627, MEE1 24]. More runs on the test system calibrate
  the limit (open work).
- **60 fps [U Q617].** `<label>:exposure:<w>x<h>@60`, `<label>:auto-exposure:searched:<w>x<h>@60` and
  `<label>:auto-exposure:holds-rate:<w>x<h>@60` are removed (5.3, 8.2). `<label>:rate:<w>x<h>@60` stays.
- **The long take [U Q618].** A take of 5 minutes is an option of full, not part of the default run: the package
  option `long_take=False` of `certify()` and `certify_plan()` [C 2.2] [U Q627, MEE1 30: the name]. With `long_take=True`, the
  run adds `group:take-300:finished` and `group:take-300:rate` (the two rows of Q598) and the facts of 5.5 over
  5 minutes. The default full keeps the take of 30 s. The option changes which checks run, so the plan counts
  them; a run without the option is complete for its level [C 2.2].

The other proposals of the gap review are not decided. Section 14 holds them as questions.

#### 3.6.12 Drops and additions of Q624 [U Q624a to Q624m]

The user decided the proposals of the gap review on 2026-11-23 (Q624a to Q624m,
[ADR-493E](../decisions/entries/493E-decisions-of-the-user-on-the-certify-check-drops-and-additions.md)). His
words: "Q624f - use 3 as the lower value, and 12 as the upper value. otherwise yes to all of Q624". None of these
checks is built. Each one stands in `details.not_built` until its step of 3.6.7 lands (Q591). The choices of
the agent are in [ADR-DBF8](../decisions/entries/DBF8-choices-of-the-certify-names-verdicts-and-checks.md).

**Drops and merges.**

- (a) `system:backend` is dropped: `details.backend` holds the backend one time.
- (b) `system:virtual-cameras` is dropped: `detect` holds the count (`virtual`).
- (c) `control:white-balance` and `control:power-line` are not checks. Their values are facts of
  `details.cameras[]`: `white_balance`, `white_balance_auto` and `power_line` (the native values, or `null`)
  [U Q627, DBF8 1: the key names].
- (d) `control:focus:sharpness` and `control:autofocus` are dropped until a pass rule exists. Focus matters for
  calibration boards, so they come back with a pass rule (open work).
- (e) `<label>:timings` merges into `<label>:cycles` and `details.steps`: `cycles` gets `open_ms_p50`,
  `open_ms_max`, `first_frame_ms_max` and `close_ms_max` over its opens.
- (f) The scale self-check runs at two points, 3 and 12 cameras: `self:scale-3` and `self:scale-12` replace
  `self:scale-4` and `self:scale-8` (7). The proposal of one check at 8 is refused.
- (g) Replaced by a later answer of the user [U, [ADR-63D9](../decisions/entries/63D9-decisions-of-the-user-on-the-processors-the-build-order-and-the-certify-choices.md)]: `self:idle-cpu`, `self:ring:torn` and
  `self:ring:lapped` run on every processor, not on ARM only. The first answer (ARM only) does not apply.
- (h) [U Q624h: read the rule, and drop them if they only served the unit id.] The outcome is a choice of the
  agent [U Q627, DBF8 8] (ADR-DBF8 item 8): `identity:stable` and `identity:unique` stay. Their rule (10.2) is about the
  `camera_id` of the product,
  not about the unit id of the report: the product keys the settings of a camera, its restore record and the
  selection of the UI by `camera_id`, so an id that changes between two detections, or two units of one model
  with one id, breaks the product. Q595 does not touch them.

**Additions.** "Kind" is the verdict side of 3.6.10.

| Check | Level | Kind | Pass rule | Numbers | Test | Build step |
|---|---|---|---|---|---|---|
| `<label>:records:mkv-opens` (i) | both | pipeline | The MKV of the camera opens through the reader of the product, with its index, and its frame count equals the frame count of the take (not the rows of the CSV: a short CSV then fails only `rows-complete`) [U Q627, DBF8 18, review]; `fail` `mkv-not-readable` or `mkv-frames-differ`. Today certify reads each block at its byte offset from the sidecar, so a broken index passes. | fail: `mkv_frames`, `frame_count`; none on a `pass` | T-CERT-112 | 13 |
| `<label>:bursts` (j) | full | no verdict | `record-only` for now, as `group:in-step`, with the `module` of its model: the share of the arrival intervals of the take that are shorter than half a frame period. | `burst_share` (3 decimals), `intervals` | T-CERT-113 | 13 |
| the notice `camera-usb3-on-usb2-link` (k) | quick | system | No check row [A]. It fires only on a fact of the system, never on `bcd_usb` alone: `usb3_capable` `true` and `usb_link` `USB 2`. 3.6.13 gives the fact on each system. Its values: `{"camera": "<name>"}`. Its text: "Camera <name> is a USB 3 camera on a USB 2 port. Plug it into a USB 3 port (often blue) if the computer has one." The summed need of the cameras on one controller waits for `group:contention`. | `usb3_capable` and `usb_link` of `details.cameras` | T-CERT-114 | 13 |
| `system:memory` (l) | quick | system | Before the open: the free memory is at least the need of the rings of the cameras to open; on Linux also the size of the shared-memory mount (`/dev/shm`) is at least that need; `fail` `memory-low` or `shm-too-small`. The need of a camera is the sum of `ring_total_size(slot_count(history_s, fps), slot_capacity)` of `skellycam/core/ipc/frame_ring/layout.py` for each ring that the product makes for it (about 26.5 MiB for the JPEG ring at 720p30 [M log]). The open still runs after a `fail`. | `memory_free_mib`, `rings_need_mib`, `shm_size_mib` (Linux; else `null`) | T-CERT-115 | 13 |
| `group:take-again` (m) | full | pipeline | A second take of 2 s right after the first finishes, and each camera has its rows; `fail` with the reasons of `group:take:finished` and `missing-rows`. One test: "a second take works". | `cameras`, `take_seconds`, `frame_count` | T-CERT-116 | 14 |
| `group:preview-during-take` (m) | full | pipeline | A reader decodes the preview frames of each camera during `group:take-30`; the take loses no frame because of it. Planned only: it is built when the preview UI of step 4b exists, and it stays in `details.not_built` until then. | `preview_fps`, `preview_skipped_share` | T-CERT-122 | later |
| `report:rules` (m) | both | no verdict | Before `certify()` returns, the report meets the privacy and form rules of the validator (today `skellycam/tests/certify/report_rules.py`; it moves into the package, `skellycam/core/certify/report_rules.py` [U Q627, DBF8 5]). It checks the report without its own row. A failure is a fault of the writer of skellycam, not of the pipeline of the person: `fail` `report-rules` with the count, and the code `report-rules` goes into `evidence.reasons` [C 7.1 statement 7: the package adds its own codes] [U Q627, DBF8 5, review]. The row gives no verdict to the pipeline item and is not in `pipeline:gate`. The problems are never copied as text. | `problems` | T-CERT-117 | 9 |
| `system:camera-access` on Windows (m) | quick | system | `record-only` with the fact `access` [U Q627, DBF8 6, review]: the check reads a setting and judges nothing of its own. Before the opens: the privacy setting of Windows lets desktop programs use the camera, or not. With `denied`, each camera is `not-run` `no-access`, not `fail` (10.2). Windows reads the consent store of `webcam` for desktop programs [NV]. | `access` (`allowed`, `denied`, `unknown`) | T-CERT-118 | 13 |
| `system:power` (m) | full | system | `record-only`. | `on_battery`, `power_plan` (`balanced`, `high-performance`, `power-saver`, `other`; never the name of a plan of the person), `usb_selective_suspend`, `usb3_link_power_saving` (booleans or `null`) | T-CERT-119 | 14 |
| `system:timer` (m) | full | system | `record-only`, about 1 s: the real length of a sleep of 1 ms, and the step of the clock. | `sleep_1ms_p50_ms`, `sleep_1ms_p99_ms`, `clock_step_us` | T-CERT-120 | 14 |

- The new reason codes: `mkv-not-readable`, `memory-low`, `shm-too-small`, `report-rules`; the new notice code
  `camera-usb3-on-usb2-link` (section 15).
- `pipeline:gate` also requires `<label>:records:mkv-opens` of the units whose row has the pipeline `module`, and
  `group:take-again` and `system:memory`. `report:rules` is in no gate. `<model>:gate` also requires a row of
  this list that the rule of 3.6.10 gives to the model.
- The catalogue of 3.6.2 gets these rows at their levels. 3.6.8 counts them.

#### 3.6.13 The USB 3 capability on each system [U Q624k, 63D9, Q628, Q629]

The user asked for the notice of a USB 3 camera on a USB 2 link on macOS and Linux too [U, ADR-63D9]. The notice
needs two facts: the operating speed of the link (`usb_link`, read today by
`skellycam/core/device_detection/usb_connection.py` on the three systems) and the USB 3 capability of the
device. `bcd_usb` alone is not a fact: a USB 3 device on a USB 2 link presents `bcdUSB` 0x0210 there, and many
pure USB 2 cameras also declare 0x0210. `details.cameras[]` gets one key [U Q628]:

| Key | Type and values | Present (else) | Privacy |
|---|---|---|---|
| `usb3_capable` | `yes`, `no`, `possible`, `null` [U Q629; was `true`, `false`, `null` in Q628] | always; `null` when no source below tells | a model fact |
| `usb3_capable_source` | `os`, `list`, `bcd`, or `null` with `usb3_capable` `null` [U Q629] | always | a closed name |

**The order of the sources [U Q629].** The first source that gives an answer sets the fact:

1. `os`: the fact of the system (the table below): `yes` or `no`.
2. `list`: the field `usb3_capable` of the model in the list of known cameras (9.4): `yes` or `no`. Thus the
   fact is exact for a known model on each system.
3. `bcd`: `bcdUSB` of the device descriptor with the running link. On a SuperSpeed link the answer is `yes`. On a
   USB 2 link, `bcdUSB` 0x0200 or 0x0201 gives `no`: a USB 3 device that runs at high speed presents 0x0210 or
   higher, and the host asks a BOS only from a device above 0x0200 [NV: the USB 3.x specification is not read
   here; Microsoft, "USB 2.1, 2.0, 1.1 device enumeration changes in Windows 8", describes the BOS request above
   0x0200]. 0x0210 or higher gives only `possible`, because many pure USB 2 cameras declare 0x0210 with LPM. The
   lab cameras of 2026-11-23 [M, relayed]: the C922, the C930e and the generic camera present 2.00 (`no`); the
   Kiyo Pro presents 3.20 on its USB 3 link (`yes`). This source also serves Linux with no `bos_descriptors`.

**The notice rule (each system) [U Q628, Q629].** `camera-usb3-on-usb2-link` fires when
`usb3_capable` is `yes` and `usb_link` is `USB 2`. With `possible` on a USB 2 link, the milder notice
`camera-maybe-faster-usb-port` fires, with the text "Camera <name> may support a faster USB port. If the
computer has a USB 3 port (often blue), try it there." [U Q629]. With `no` or `null`, no notice. A
guess never gives the text of a fact.

| System | Operating speed (today) | USB 3 capability | Uncertain |
|---|---|---|---|
| Windows | the connection information of the hub, `IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX_V2`, bit 0 of its flags (`DeviceIsOperatingAtSuperSpeedOrHigher`) | bit 1 of the same flags (`DeviceIsSuperSpeedCapableOrHigher`); `usb_connection.py` already reads the flags word at offset 12 | [NV]: a check on hardware is open (a Kiyo Pro on a USB 2 port) |
| Linux | sysfs `speed` of the USB device (Mbit/s: 480 is USB 2, 5000 or more is USB 3) | sysfs `bos_descriptors` of the USB device: the cached BOS of the device, a binary file, read-only for each user (`BIN_ATTR_RO`, mode 0444), present only when the device has a BOS. `usb3_capable` is `true` when it holds a SuperSpeed USB Device Capability (`bDevCapabilityType` 0x03) or a SuperSpeedPlus capability (0x0A), `false` when the file exists with neither, `null` when the file does not exist | The attribute came in 2024 (the ABI file says "March 2024"; probably kernel 6.9) [NV: the first release]. On an older kernel the BOS is not in sysfs: the `descriptors` file holds only the device and configuration descriptors, and a BOS request through usbfs (`/dev/bus/usb/BBB/DDD`) needs a control request and so write access to the node, which a normal user usually does not have [NV]. Then `usb3_capable` is `null`. The kernel reads the BOS only from a device with `bcdUSB` 0x0201 or higher, which each USB 3 device on a USB 2 link has. |
| macOS | IORegistry property `USBSpeed` of the `IOUSBHostDevice` (`ioreg -a -r -c IOUSBHostDevice`); 3 is high speed, 4 or more is SuperSpeed | At detection none: the known list, then `bcd` (no request to the camera). The trial of the end of a full run tries the BOS request (method 2 below) [U Q629] | [NV] on each point, until the reports of the trial show it |

**The methods on macOS, ranked [U Q629].** The user asked: "try a little harder to build a test we can include into
certify to find out this information" [U, ADR-BG8P]. He refused a stand-alone probe: "the certify process is the
only way any tests are ever run on machines other than this one" [U Q629]. Each method must not disturb the
camera: no stream, no claim of an interface, no exclusive open. Everything below is [NV] until the reports of
the trial show it.

| Rank | Method | What it tells | Rights and risk |
|---|---|---|---|
| 1 | The known list (`usb3_capable` of the model, 9.4) | exact for a listed model, on each system | none |
| 2 | GET_DESCRIPTOR(BOS) on the default pipe through `IOUSBDeviceInterface::DeviceRequest`, with no `USBDeviceOpen` and no `USBDeviceOpenSeize`: a read of 5 bytes, then of the total length; it changes no state | exact (a SuperSpeed or SuperSpeedPlus device capability in the BOS) | No root. No entitlement for a program outside the App Sandbox; a sandboxed app needs `com.apple.security.device.usb` [NV]. Apple's documentation says that the device must be open for a device request, but libusb notes that Apple's USB Prober sends a descriptor request with no open; the request can fail with `kIOReturnNotOpen` [NV]. libusb itself calls `USBDeviceOpenSeize` before its descriptor request; certify must not, because a seize asks the driver of the camera to let go. The IOUSBLib interface is old but still works on Apple Silicon and Intel through libusb [NV]. |
| 3 | `bcdUSB` with the running link (`ioreg`) | `no` (0x0200, 0x0201) or `possible` (0x0210 and higher) on a USB 2 link; `yes` on a SuperSpeed link | none (a registry read) |
| 4 | The IORegistry keys of the `IOUSBHostDevice` (`ioreg -a -l -r -c IOUSBHostDevice`): `USBSpeed`, `UsbLinkSpeed`, `bcdUSB`, and any key with "BOS", "SuperSpeed" or "Capab" in its name | today only the running speed; no documented key gives the capability; the trial records if such a key exists | none |
| 5 | `system_profiler -json SPUSBDataType` | its "speed" ("Up to 480 Mb/s") follows the running link, not the capability (an iPhone shows 10 Gb/s with a USB 3 cable and 480 Mb/s with a USB 2 cable); new macOS versions may lack `SPUSBDataType` | none; about 1 s to 10 s |

At detection, macOS uses the known list, then `bcd` (no request to the camera). Linux uses `bos_descriptors`, then
the list, then `bcd`. The trial below tries each method.

**The trial: `<label>:usb3-trial` [U Q629].** The user agreed: "The method trial runs inside certify: The
three-state fact (yes, no, possible) and the milder notice for "possible" as before. On macOS and Linux, a
record-only check at the end of a full run tries every method and reports each answer. The request to the camera
runs last, followed by a check that the camera is still listed." [U Q629]

- **Level and system.** `full` only, never `quick`. macOS and Linux only; Windows has the exact hub flag and no
  trial. One row for the first unit of each model, as the camera block of 5.1 [A].
- **Its place.** The very end of a full run: after phase G (each other check of the cameras has ended, and each
  camera is released and restored), before phase H (2.3) [U Q629]. A camera that hung or wedged earlier in the run
  gets no trial (2.3); its row is in `<label>:not-reached`.
- **Its order inside.** First each method that sends nothing to the camera (macOS: the known list, `bcd`, the
  IORegistry keys, `system_profiler`; Linux: `bos_descriptors`, the known list, `bcd` from sysfs `version`). Then,
  as the last action of the trial, the request to the camera: on macOS method 2; on Linux one GET_DESCRIPTOR(BOS)
  through usbfs (`USBDEVFS_CONTROL` on the node of the device, which needs write access; a normal user often has
  none, and then the row has `PermissionError`) [U Q629; A: the Linux request].
- **The guard.** Before the request, the code reads the vendor id, the product id and the release number of the
  device through the same interface (macOS: the function table of `IOUSBDeviceInterface`; Linux: the cached device
  descriptor that a read of the usbfs node gives with no request) and compares them with the registry (macOS) or
  sysfs (Linux). On any difference it sends nothing and writes `FunctionTableNotVerified` [U Q629].
- **The listing after.** After the request, one new device listing (macOS `ioreg`; Linux sysfs) records if the
  camera is still listed with the same USB id at the same place [U Q629]. When it is not, the row has
  `still_listed` `false`, and the notice `camera-gone-after-usb-trial` tells the person: "Camera <name> stopped
  answering after the last check of the run. Unplug it and plug it in again." [A: the text].
- **It fails nothing [U Q629].** The row is `record-only`, with the `module` of its model, in no gate, and it
  feeds no verdict: `usb3_capable` and the notices of detection do not change in the run.
- **Its numbers [A].** `os_fact` (`yes`, `no` or `null`; Linux `bos_descriptors`), `list` (`yes`, `no`,
  `null`), `bcd` (`yes`, `no`, `possible`, `null`), `ioreg_capability_key` (macOS; `true` when a key name of
  method 4 exists, else `false`), `system_profiler_mbps` (macOS; 480, 5000, 10000, 20000 or `null`),
  `bos_request` (`yes`, `no`, `null`), `still_listed` (`true`, `false`), and for each method that failed
  `<method>_error` with the class name of the error from a fixed list (`PermissionError`, `TimeoutError`,
  `OSError`, `NotOpen`, `FunctionTableNotVerified`, `NoBosDescriptor`, `PlugInNotCreated`, `InterfaceNotFound`,
  `NotSupported`). No free text, no serial number, no location id, no path, no product text.
- **Its future.** When the reports of the trial show that the request is safe (each camera still listed, no
  fault) or not, the user decides in a later decision whether the request moves to the detection, or whether the
  trial goes [U Q629].
- **No stand-alone probe [U Q629].** The script `decisions/scripts/probe_usb3_capability_macos.py` of the
  previous commit and its tests are removed [A]: the rules of `AGENTS.md` put code that a test runs in `tools/`,
  and the certify code will own these parsers. The synthetic samples of its tests are the samples of T-CERT-114.
- **Time.** About 2 s for each model on Linux and up to 15 s on macOS (with `system_profiler`) [NV].

Sources for macOS (read on 2026-11-23, as data): the libusb darwin backend
(`https://github.com/libusb/libusb/blob/master/libusb/os/darwin_usb.c`: "According to Apple's documentation the
device must be open for DeviceRequest but we may not be able to open some devices and Apple's USB Prober doesn't
bother to open the device before issuing a descriptor request", and the call of `USBDeviceOpenSeize` before it);
Apple IOUSBLib documentation in the IOUSBFamily sources (`https://opensource.apple.com/source/IOUSBFamily/`);
a Japanese blog that compares the `system_profiler` speed of one iPhone with two cables
(`https://dev.classmethod.jp/articles/20250110-check-the-data-transfer-speed-of-usbc-cable-with-system_profiler/`).

Sources for Linux and Windows (read on 2026-11-23, as data): the Linux USB sysfs ABI file
(`https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-bus-usb`, entries `bos_descriptors` and `speed`); the
patch "usb: Export BOS descriptor to sysfs" (`https://lkml.iu.edu/hypermail/linux/kernel/2403.0/03549.html`:
`BIN_ATTR_RO(bos_descriptors, 65535)`, visible only when `udev->bos` is set); Apple `IOUSBHostObject`
(`https://developer.apple.com/documentation/iousbhost/iousbhostobject`: "Creates a USB host object and sets up a
communication channel to the kernel", property `capabilityDescriptors`); Apple `IOUSBHostDevicePropertyKey`
(`https://developer.apple.com/documentation/iousbhost/iousbhostdevicepropertykey`: no speed or capability key);
an Apple Community thread on the missing `SPUSBDataType` (`https://discussions.apple.com/thread/256180514`).

**Tests (T-CERT-114) with sample data.** No recording on hardware exists yet, so the samples are made from the
layouts of the specifications and are marked as such [NV until a recording replaces them]:

- Windows: a flags word `0x2` (capable, not operating) with `usb_link` `USB 2`: notice; `0x3`: no notice; `0x0`
  with `bcd_usb` `0210`: no notice.
- Linux: a fake sysfs tree with `speed` `480` and a `bos_descriptors` file of the bytes `05 0F 16 00 02`, then a
  USB 2.0 Extension capability `07 10 02 06 00 00 00`, then a SuperSpeed capability `0A 10 03 00 0E 00 01 0A FF
  07`: `usb3_capable` `true` and the notice; the same with only the USB 2.0 Extension (the header set to its length): `false`, no notice; no
  `bos_descriptors` file: `null`, no notice.
- macOS, synthetic: an `ioreg -a -l` plist with a Kiyo Pro (`idVendor` 0x1532, `idProduct` 0x0E05, `bcdUSB`
  0x0210, `USBSpeed` 3, `UsbLinkSpeed` 480000000, a child of `bInterfaceClass` 14, a serial and a `locationID`),
  a C922 (`bcdUSB` 0x0200, `USBSpeed` 3) and a keyboard (class 3): two video devices; the Kiyo Pro gives
  `possible` and the milder notice at detection; the C922 gives `no`; no serial and no location is in the report.
  A `system_profiler -json` sample with `"speed": "Up to 480 Mb/s"` gives `system_profiler_mbps` 480. The BOS
  bytes of the Linux bullet give `bos_request` `yes`; the bytes `05 0F 08 00 01 03 10 0A` (SuperSpeedPlus only,
  shortened) give `yes`; a device descriptor in place of a BOS gives `null` with `NoBosDescriptor`.
- Each system: a known model with `usb3_capable` `true` in the list and no system fact: `yes` (`list`).

**A wider USB speed test? [U Q628, M7JC 11].** The recommendation: no streaming throughput test. The inventory already holds
the negotiated link of each camera (`usb_link`), its capability (`usb3_capable`), its host controller and its hub
depth (`controller`, `controller_id`, `hub_depth`, 3.5.5), so a developer sees how many cameras share one
controller. The effect that matters, cameras that lose frames or fail to open when they share a controller, is
measured by `group:contention` and `group:open` with the real modes (Q599). A separate throughput test would
stream each camera at each mode, cost minutes, and add opens, which is the main cause of a wedge. A summed
bandwidth figure for each controller can come later from the same inventory facts, beside `group:contention`.

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

The 2 minutes are for all packages together [C 2.7 rule 1]. The user decided the shares: skellycam
30 s, skellytracker 75 s, freemocap 15 s (format 1.6.0 gives the quick run of skellytracker a limit of 65 s
[C 3.6], and the contract does not split the 2 minutes between the packages; reported by the freemocap session and
confirmed by the user,
[ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md)). Thus the quick part of skellycam stops at 30 s:

- A check that cannot start before the end of the 30 s is `not-run` with the common code
  `over-budget` [C 5.3].
- A check that runs at the end of the 30 s is stopped: its child process is killed with its process
  tree, as for a cancel. It is `not-run` with `over-budget`. `over-budget` is never a failure.
- The order puts the most useful checks first [C 2.7]: the run must show that a recording starts,
  that a setting sticks and that the camera's own JPEG frames arrive [U]. The order is: (1) `detect`;
  (2) the one apply of 4.2 (`opens`, `rate`, `modes:granted`); (3) the retries alone of 4.2; (4) the
  settings change of 4.3; (5) the take of 4.5 and its checks; the JPEG checks of 4.4 use the frames of
  steps 2 to 5; (6) the close and phase G; (7) `self:hang-100ms`.
- What is cut first when the time runs out [A] [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md): `self:hang-100ms` starts only when at least 10 s
  of the budget remain. Then the retries: a retry starts only when at least 14 s remain (6 s for the
  retry and 8 s for the settings change, the take, its checks and the close); else it is `not-run`
  with `over-budget`, and the group result of that camera stands. Steps 1, 2, 4, 5 and 6 take about
  `20 + N/4` s (4.7), so they fit for up to 8 cameras.
- On the estimates of 4.7, `self:hang-100ms` does not fit when a camera is checked, so in quick it is
  usually `not-run` with `over-budget`. It always runs in `full` (phase E).

### 4.2 The open and the rate

| Check | Measured, and how | Numbers | Result rule |
|---|---|---|---|
| `detect` | The detection child. Limit 20 s. | `seconds`, `cameras`, `virtual`, `modes_read` | `pass`; `fail` with `timed-out`, `crashed`, `backend-missing` |
| `<label>:detect` (removed by 3.6.2: `details.cameras[].modes` holds the modes) | The modes (cap 7.3). Record only. | `mjpg_sizes`, `has_720p30`, `has_1080p30`, `has_60`, `max_fps`, `largest_w`, `largest_h`, `modes_read` | `record-only` |
| `<label>:detect:mjpg-mode` | A MJPG mode exists at the floor (before 3b). | `mjpg_sizes` | `pass`; `fail` with `no-mjpg-mode` |
| `<label>:opens` | One apply opens each real camera at `<base>`, in `MANUAL` at -7 (certify sets it; the product default is `AUTO` [req 1.5]), MJPG, rate 30. A camera in `MANUAL` has the start-up rate check of cap 10.1 [req 1.3b]. | `seconds_to_first_frame`; the failure facts of 3.5.3 (3.6.2: `seconds_to_ready` and the CPU go to `details.steps`) | `pass` at `ready`; `not-run` with `camera-in-use`; `fail` with the reason of the product failure (section 15) |
| `<label>:rate` | The start-up rate check of the product (cap 10.1): frames 6 to 90, ±3 %. Then the brightness of 3 ring frames. | `measured_fps`, `luma_mean`, `jpeg_kb_mean`; the rate window of 3.5.6 (3.6.2) | `pass`; `fail` with `rate-low` or `rate-high`; `not-run` with `too-dark` (4.6) |
| `<label>:modes:granted:<base>` | The granted format, size and rate equal the request (D-1). | `requested_fourcc`, `granted_fourcc`, `granted_w`, `granted_h`, `granted_fps_num`, `granted_fps_den` | `pass`; `fail` with `mode-not-granted` |
| `group:open` | Did each camera that passes alone also pass in the group? | `cameras`, `passed`, `refused_bandwidth`, `failed_in_group_only` | `pass`; `fail` with `usb-bandwidth` or `rate-under-contention`; `not-run` with `one-camera` |

One apply, then a retry alone [U: question 3 of draft 1, "yes"]:

1. One apply opens all real cameras at `<base>`. The product opens them in parallel: 5.8 s for three
   cameras [M `research/usb_cameras/docs/hardware_run_3a_20261120.md`].
2. A camera that failed in the group with `usb-bandwidth` or `rate-low` gets one retry alone. The
   retry decides its checks. `group:open` records the difference.
3. No retry for `hung`, `camera-in-use`, `device-removed` or `not-found`.

Reason: a bandwidth refusal is a fact of the USB topology. The C922 and the generic camera on one USB
2 root port were refused at 81 % of a microframe on every API; each alone worked
[M `research/usb_cameras/docs/windows_results_20261112.md` §6].

### 4.3 Settings stick [U]

The user accepted this check [U]. The product sets the controls after the first frame and reads them
back (cap 9.1). The steps:

1. At the open of 4.2, the requested exposure is manual -7. The read-back of the product (the config
   stores it, cap 9.1 step 6) gives `exposure_readback_open`. On a route with no time unit
   ([req 1.1]: `exposure` is a step index), certify sets the step 5 in place of -7 and the step 4 in
   place of -8.
2. One live apply changes all cameras together to manual -8 (one step darker; each test camera holds
   30 fps there [M cap 10.5]). The product runs the check of cap 10.2 (about 2.5 s). After 3c, the same
   apply sets gain and focus to manual at the values that the camera reported, so that the image does
   not change.
3. The status read of the control thread 1 s later gives `exposure_later` (cap 11.4).
4. The brightness at -8 against -7 gives `luma_ratio`.

| Check | Pass rule | Result |
|---|---|---|
| `<label>:settings-stick:readback` | The read-back at the open equals -7, and the read-back after the change equals -8. | `pass`; `fail` with `readback-differs`; `not-run` with `no-manual-exposure` for a camera with no manual exposure: it opens with the warning `no_manual_exposure`, and the product ignores the value [ux 4.5 item 3]; never `fail` for a feature that the camera does not have (section 1) |
| `<label>:settings-stick:holds` | The read 1 s later equals -8. | `pass`; `fail` with `setting-reverted`; `not-run` with `no-manual-exposure`; `not-run` with `prior-check-failed` when `readback` did not pass |
| `<label>:settings-stick:image-effect` (full only, Q593) | The image gets darker. With a time-unit exposure route (`exposure_unit` `log2-s`, `100us` or `seconds`), one step halves the exposure time, so `luma_ratio < 0.85` [A, not calibrated]. With a unitless route (`ev`, `native`, `native-data`, 10.2), only the direction counts: `luma_ratio < 0.97` [A, not calibrated] [U: macOS route ruling]. | `pass`; `fail` with `no-image-effect`; `not-run` with `too-dark` or `too-bright` in place of a `fail` when `luma_at_m7` is below 24 or above 230 (4.6) [U Q773, Q819]; `not-run` with `no-frame` when it has no frame at -7 or at -8 [U Q818]; `not-run` with `no-manual-exposure`; `not-run` with `prior-check-failed` |

Numbers of the three checks: `exposure_set`, `exposure_readback_open`, `exposure_readback`,
`exposure_later`, `luma_at_m7`, `luma_at_m8`, `luma_ratio`, `exposure_unit`, `control_path`, and the
exposure and gain context of 3.5.9. 3.6.2 gives the one row of each key. After 3c, gain and focus have their own checks (5.4).

Measured: the C930e read manual exposure -5 at the stream start when -7 was set last, and its gain
fell over three opens; the product sets the controls after the first frame, so the configured values
held [M `research/usb_cameras/docs/hardware_run_3a_20261120.md`]. This check finds such a camera.

The take of 4.5 runs at -8. The product puts back the "before" values at the close of the group [U].

### 4.4 Native JPEG [U, A]

The checks use frames that the run already has. They need no extra time.

| Check | Pass rule | Result |
|---|---|---|
| `<label>:native-jpeg:format` | The mode format is MJPG, and the source gives JPEG frames (`delivered` `jpeg`). | `pass`; `fail` with `no-native-jpeg` |
| `<label>:native-jpeg:not-reencoded` (full only, Q593) | skellycam decoded and encoded no frame in the capture path (`encoded_by_skellycam` 0, D-10). | `pass`; `fail` with `no-native-jpeg` |
| `<label>:native-jpeg:valid` | Each checked frame has SOI and EOI and decodes strictly. | `pass`; `fail` with `jpeg-damaged` |
| `<label>:native-jpeg:size` (full only, Q593) | Each checked frame has the SOF size of the mode. | `pass`; `fail` with `jpeg-size-differs` |
| `<label>:native-jpeg:ring-equals-mkv` (full only, Q593) | Each MKV block of the take equals its ring slot byte for byte. | `pass`; `fail` with `jpeg-damaged`; `not-run` with `prior-check-failed` when the take did not run |
| `<label>:native-jpeg:source-equals-ring` (full only, Q593) | Each hash of D-11 equals the hash of the ring slot of the same `source_frame_number`. | `pass`; `fail` with `jpeg-damaged`; `not-run` with `ring-lapped` when the ring no longer holds the frame |

Numbers: `format` (`MJPG`, `YUY2`, `NV12`), `delivered`, `frames_checked`, `encoded_by_skellycam`,
`decoded_by_skellycam`, `dht_inserted` (count), `dqt_distinct` (count), `dqt_sha256`. 3.6.2 gives the one row of
each key; `decoded_by_skellycam` is read by no check and is not written [U Q627, MEE1 9].

- The frames: 30 frames of the JPEG ring after the rate check, and each block of the take of 4.5.
- A JPEG with no DHT gets the standard table from the capture check (`DHT_INSERTED`, rec 4.1). That is
  still native. `dht_inserted` records it.
- The shared loop hashes the bytes that it gives to the ring and the recorder, after a DHT insertion,
  for the first 30 frames after the first move to `ready` of each open and after each record start
  (`sha256_00` to `sha256_29`, `sha256_frame_00` to `sha256_frame_29`, `sha256_trigger`, [ux 4.6.2]
  D-11). A live change does not re-arm the set [ux 4.6.2]. Thus `source-equals-ring` uses the set of
  the first `ready`: certify reads the set and the 30 ring slots of the same frame numbers right after
  that `ready`, before the live change to -8 of 4.3 and before the ring laps them. The set of the
  record start is compared with the MKV blocks of the same frame numbers, beside `ring-equals-mkv`
  [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md).
- Measured on Windows: MJPG passthrough is byte-equal on the three good test cameras
  [M `research/usb_cameras/docs/hardware_run_3a_20261120.md`, T-CAP-52].

### 4.5 The take and its files

- The take starts through `CameraGroup.start_recording` in the work folder (9.5), runs 3 s and stops
  through `stop_recording`. Limit: 30 s from the start request.

| Check | Pass rule | Fail reason |
|---|---|---|
| `group:take:finished` | The manifest has `state` `"finished"` and no `take_error` (rec 6.6). | `take-not-finished`, `take-error`, `fat-disk`, `disk-stall`, `write-error` |
| `group:take:csv-rows` (merged into `records:rows-complete` by Q598, 3.6.2) | Each CSV reads with `sidecar.read_strict`, and each has the frame count of the take as its row count (rec 7.6). | `rows-differ` |
| `group:take:no-missing` (merged into `records:rows-complete` by Q598) | No live camera has a `missing` row, and the warnings hold no `camera_dead` and no `camera_file_short`. | `missing-rows` |
| `group:take:frame-count` (merged into `group:take:rate` by Q598) | The frame count is at least 80 % of 3 s times the mode rate [A, not calibrated]. | `too-few-frames` |
| `group:take:rate` | The frame rate of the take summary is within 1 % of the mode rate (2 % for a take under 10 s, 3.6.6 item 6). This rate is the frames divided by the elapsed time [U, Q609]; with fewer frames than 80 % of 3 s times the mode rate it fails with `too-few-frames` (Q598). The mean of 1/interval is not used: the 16 ms arrival grid biases it high [M `research/usb_cameras/docs/hardware_run_3a_20261120.md`, T-CAP-60]. | `group-rate-off` |
| `<label>:records:rows-complete` | Each frame of the take has a present row in the CSV of this camera: the CSV reads with `sidecar.read_strict`, it has the frame count of the take as its row count, and no row is `missing` (Q598). | `rows-differ`, `missing-rows` |
| `<label>:records:blocks-decode` | Each block of its MKV decodes (at 1/8 size, in memory). | `frame-not-decodable` |
| `<label>:records:gaps-explained` (full only, Q593) | The sum of its gaps of `source_frame_number` is not more than the change of its `replaced_count` (cap 5.2) from before the record start to after the stop: each gap needs a replaced frame. The window holds each row of the take and some frames more [A] [ADR-X8XE](../decisions/entries/X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md). | `gaps-unexplained` |

- A normal take of three cameras had equal rows, and each frame decoded [M run 11-20].
- A gap in the last three rows is recorded in `end_gaps` and does not fail `gaps-explained` [A]. In 6
  of 7 takes of the run of 2026-11-20, one source frame was skipped two rows before the end, and the
  cause is under study [M run 11-20]. When the cause is fixed, this exception goes.
- Numbers of the `records` checks: `rows`, `missing`, `gaps`, `replaced`, `end_gaps`,
  `decode_failures`, `sample_minus_arrival_p50_ms`, `sample_minus_arrival_p95_ms`,
  `sample_time_kept`, `grid_16ms_share`, `long_intervals`, and the timing and the first gap of 3.5.6
  and 3.5.7. The timestamp numbers are facts: no check judges them here.
- Numbers of the `group:take` checks: `cameras`, `frame_count`, `take_seconds` (the length of the
  take; `seconds` is the time of the check, 3.5.1), `rate`, `file_system`, `spread_p50_ms`,
  `spread_p95_ms`, and the warnings and the CPU of 3.5.7 and 3.5.8. The spread is not judged [U]: the lockstep gate of today gives a
  median of about 36 ms [M `research/usb_cameras/docs/hardware_run_3a_20261120.md`] to 40 to 50 ms
  [M run 11-20].
- When the take does not start, each take check is `not-run` with `prior-check-failed`.
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
  is `not-run` with `too-dark` [U: one test, one row]. The same check with a brighter frame is
  `fail`. A check that passes in the dark stays `pass` [U Q773].
- `BRIGHT_LUMA = 230` [A, not calibrated] follows the same rule: a check that fails while the mean is above it is
  `not-run` with `too-bright`, and a check that passes stays `pass` [U Q819].
- A check with no frame to measure is `not-run` with `no-frame`, never `too-dark` [U Q818].
- A covered lens gives the same result as a dark room. The report does not need to tell them apart.
- The plan asks after the run: "Was the room lit as it is when you record?" (9.1).
- Each report records `luma_mean` for each camera, and `DARK_LUMA` is marked as not calibrated in the report
  (20.7, Q774). A check with no frame or no ratio to judge is `not-run` with `no-frame`, not `too-dark` (Q773).

### 4.7 Time of `quick` [A]

Windows, Media Foundation, from the 3a hardware run:

| Step | Seconds |
|---|---|
| Session child start and imports | 2 [NV] |
| Detection (0.83 s for 8 devices [M]) | 1 |
| One apply of all cameras (5.8 s for 3 [M]) | 6 + 0.25 per camera [NV] |
| Settings check (one live change, cap 10.2) | 3 |
| Take: start, 3 s, stop, `finish` | 5 |
| File checks, JPEG checks, deletion | 1.5 |
| Close of the group (0.27 to 1.18 s per camera, in parallel [M]) | 1.5 |
| Phase G: the state of each camera from its last close | 0 |
| `self:hang-100ms` [U] | 10 |
| Each retry alone (4.2) | 6 |

The product reads the "before" values at the first open and restores them at each close [U]. Thus
phase A needs no separate open, and phase G of quick needs no open. Sum with no retry and with no hang
self-check: `20 + N/4` s, so about 21 s for one camera and 22 s for eight cameras. The hang
self-check adds 10 s, and runs only when the budget of 30 s allows it (4.1). `certify_plan("quick")`
gives `seconds_estimate` = min(30, ⌈20 + N/4⌉ + 10) when the run checks at least one camera model,
else 0 [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md). Each retry alone adds 6 s, within the budget; the plan cannot know the retries, so it
does not count them. The pop-up check of one new model (2.5) takes at most 30 s.

## 5. Level `full`: safe checks of each camera (phases C and D)

### 5.1 Selection rule [A]

A full run cannot test each mode of each camera. The C930e declares 17 MJPG sizes
[M `research/usb_cameras/docs/hardware_run_3a_20261120.md`]. For each camera whose `opens` and `rate`
passed, the run selects:

1. `<base>` (from quick; no new open).
2. Phase C: `identity`, `modes`, `controls`; `1920x1080@30`, when the camera declares it; the largest
   MJPG size at the floor, when it is larger than 1920x1080, once, at 30. After step 3b: one
   uncompressed mode (YUY2, else NV12) at 30 at the largest size that has it. Before 3b: `not-run`
   with `not-built`.
3. Phase D: the exposure sweep at `<base>`; SkellyCam Auto; the control sets; `readback-each-open`;
   the timestamps come later from `group:take-30` of phase E.
4. Phase F: the in-use check; each size that declares 60, at most two (1280x720 first, then the
   largest other size), with the sweep and the Auto search at the first one; five open and close
   cycles.

One camera of each model [A, question 4]: the camera blocks of phases C, D and F run for the first
camera of each model (USB id and backend) only. Each other camera of that model has its quick checks,
takes part in the group checks, and gets `not-run` with `same-model` for the camera block checks. In the report
shape of 3.6 the block is not planned for such a camera, and it gives no row [U Q627, MEE1 4]. This
follows the rule that a model is checked one time on a system [U] (2.5), and it keeps a full run with
two cameras of one model near the time of one camera.

29.97 fps counts as 30 [U]: "for the purposes of '30fps and above are the only modes I want to know
about' - yes 29.97 counts". Nothing below that class is listed or tested. A mode that the camera
does not declare gives `not-run` with `no-mode`, never `fail` [A]. Rates above
60 are recorded in `<label>:detect` (`max_fps`) and not opened: skellycam offers 30 and 60.

### 5.2 Rate checks of other 30 fps modes, and the exposure sweep

| Check | How | Numbers | Result |
|---|---|---|---|
| `<label>:rate:1920x1080@30` | An apply of this camera alone at the mode, manual -7. The product start-up check. | `mode_fps`, `measured_fps`, `luma_mean`, `jpeg_kb_mean`, `seconds_to_ready` | `pass`; `fail` with `rate-low`, `rate-high`, `usb-bandwidth`, `not-ready`; `not-run` with `too-dark` or `no-mode` |
| `<label>:modes:granted:1920x1080@30` | The granted mode equals the request (D-1). | as 4.2 | `pass`; `fail` with `mode-not-granted`; `not-run` with `no-mode` |
| `<label>:rate:<largest>`, `<label>:modes:granted:<largest>` | The same at the largest size. | the same | the same |
| `<label>:exposure:<base>` | Live changes through apply, manual, from -11 to -5. Each step is the check of cap 10.2. Stop after two steps in a row that end `too_slow`. | `fps_at_m11` ... `fps_at_m5`, `state_at_m11` ..., `luma_at_m11` ..., `cliff` (the longest exposure up to -5 that ends `ready`) | `record-only` |
| `<label>:exposure:<base>:readback` | Each set value of the sweep reads back. | `readback_failures` | `pass`; `fail` with `exposure-not-applied`; `not-run` with `no-manual-exposure` |
| `<label>:settings-stick:each-open` | At each open of the run, the configured exposure reads back (`full` only). | `opens`, `readback_failures` | `pass`; `fail` with `setting-lost-on-reopen` |

- The sweep answers "where is the 30 fps cliff?" Logitech: 30 fps to -5, 16 fps at -4; Kiyo Pro:
  28.7 fps at -6, 23.1 at -5 [M cap 10.5].
- The sweep ends at -5 because of the `MANUAL` clamp of the product: a `MANUAL` value above -5
  becomes -5 on a route with a time unit [req 1.1]. Thus -4 and -3 would test -5 again, and the sweep
  cannot see a cliff above -5 [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).
- The sweep needs `measured_fps` after `too_slow`. The 3a run found that it keeps the old passing
  value [M `research/usb_cameras/docs/hardware_run_3a_20261120.md`]. That fault must be fixed first
  (section 13).

### 5.3 SkellyCam Auto [U, A 1.3]

The exposure rule of the product, which the certify checks must match [U]:

- The exposure modes are Manual and Auto.
- "Auto" always means that SkellyCam finds a manual value by a one-shot search.
- A camera in Auto searches at every open, and when the person changes the frame rate.
- The camera's own auto exposure is never a mode. No certify check turns it on as a mode.
- The text for a slow camera is "Camera is slow. Try adding more light".
- Nothing below 30 fps is offered.

The camera requests spec owns the search [req 1.3, 1.3a, 1.3b]: the names `exposure` and
`exposure_found_at_fps` in the config, the status object `exposure_search` with `state`
(`running`, `done`, `failed`), `chosen`, `add_light` and the integer `count`, the limit of 20 s, and
the 60 fps fall back with the warning `rate_fallback` [req 2.4]. Certify starts a search through the
product with no HTTP: an apply of `CameraGroupManager` that opens the camera in `AUTO`, or
`await CameraGroupManager.search_exposure(camera_ids=[...])` for a camera that streams [req 1.5].
`exposure_search.count` is the number of searches of the camera since the group started; the main
process keeps it for each camera ID, also across a reopen for a size or rate change (inside the same
camera process) and across "apply again" (a new camera process) [req 1.5]. Certify never calls the pause
route (it is removed [U]).

Certify waits until the state of the camera is neither `adjusting` nor `checking`, at most 25 s from
the apply response at 30 fps and at 60 fps, and 45 s more after a fall back starts (when the live
state first holds the `rate_fallback` item) [req 1.3b, 2.4]. It reads `exposure` from the config and
`exposure_search.state`, `chosen`, `add_light` and `count` from the status.

| Check | Phase | Pass rule | Result |
|---|---|---|---|
| `<label>:auto-exposure:searched:<base>` | D | An apply that opens the camera at `<base>` in `AUTO`: `exposure_search.count` is 1 more than before the open (1 for the first open of the camera in the group), and `exposure_search.state` is `done`. | `pass`; `fail` with `auto-not-searched` (the count did not rise) or `auto-search-failed` (`state` `failed`); `fail` with `timed-out` when the state did not leave `adjusting` or `checking` in 25 s from the apply response; `not-run` with `no-manual-exposure` |
| `<label>:auto-exposure:holds-rate:<base>` | D | After the search, the camera is `ready` (the check of cap 10.2 at the chosen value). | `pass`; `fail` with `rate-low` (`too_slow`); `not-run` with `too-dark` when `too_slow` and `add_light` is true; `not-run` with `prior-check-failed` |
| `<label>:auto-exposure:searched:<w>x<h>@60` (removed by Q617, 3.6.11) | F | After `<label>:rate:<w>x<h>@60` passed: an apply in `AUTO` at `<base>`, then an apply that changes only the frame rate to 60 at the first 60 mode. The rate change started one new search (`count` rose by one). | as the base check; `not-run` with `prior-check-failed` when the group fell back from 60 (8.2); `not-run` with `no-mode` |
| `<label>:auto-exposure:holds-rate:<w>x<h>@60` (removed by Q617, 3.6.11) | F | The camera is `ready` at 60 fps after the search. | `pass`; `fail` with `rate-low`; `not-run` with `too-dark`; `not-run` with `prior-check-failed` when the group fell back from 60 |

When the group fell back from 60 fps, for any cause (the start-up check of a camera in `MANUAL`, or a
search at 60 that kept no value [req 2.4]), both Auto checks at 60 are `not-run` with
`prior-check-failed`, and `numbers.fell_back` is true [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md).

Numbers: `exposure` (the chosen value), `exposure_found_at_fps`, `add_light`, `count_before`,
`count_after`, `search_state`, `seconds_to_ready`, `luma_mean`, `measured_fps`, `fell_back`.

No product source sets the camera's own auto exposure [ux 4.5 item 1], except the restore at the
close [ux 4.7]. A camera with no manual exposure (on macOS, no working route) has no Manual and no
Auto in native capture; it opens with the warning `no_manual_exposure` [ux 4.5 item 3], and its Auto
checks are `not-run` with `no-manual-exposure`, never `fail`. Only the probe A9 of 10.7 runs the camera's own auto, as a probe and never
as a mode.

### 5.4 Controls

| Check | How | Numbers | Result |
|---|---|---|---|
| `<label>:controls` | Phase C. The diagnostics D-4 and the status (cap 8.4, 11.4): which controls exist, their ranges, the route and the scale. Record only. | as 10.2 | `record-only` |
| `<label>:controls:exposure-scale` | Phase C. The rule is in 10.2. | as 10.2 | as 10.2 |
| `<label>:control:gain` | After 3c: set the minimum and the default, manual; read back. | `set_ok`, `readback`, `rate_ok` | `pass`; `fail` with `readback-differs` or `control-failed`; `not-run` with `control-absent` or `not-built` |
| `<label>:control:focus` | After 3c: manual focus at two values; read back. | `set_ok`, `readback` | `pass`; `fail` with `readback-differs`; `not-run` with `control-absent` or `not-built` |
| `<label>:control:focus:sharpness` (dropped by Q624d, 3.6.12) | After 3c: the sharpness (variance of a Laplacian of the 1/8 frame) at the two values. | `sharpness_a`, `sharpness_b`, `luma_mean` | `record-only` |
| `<label>:control:autofocus` (dropped by Q624d) | After 3c: auto focus on, then off at the value that it reported; read back. | `reported`, `readback` | `record-only` (M-CAP-7 is open) |
| `<label>:control:white-balance`, `<label>:control:power-line` (facts of `details.cameras` by Q624c) | After 3c: read only (cap 11.5). | `value`, `auto` | `record-only`; `not-run` with `control-absent` |

### 5.5 Start-up times and timestamps

| Check | How | Numbers | Result |
|---|---|---|---|
| `<label>:timings` (merged into `cycles` by Q624e) | The times of each open of the run, from the diagnostics D-6. One check on the three systems (10.2). | `open_ms_p50`, `open_ms_max`, `first_frame_ms_max`, `ready_s_p50`, `close_ms_max` | `record-only` |
| `<label>:timestamps` | The CSV of this camera in `group:take-30` (6.1), 30 s. | as the `records` checks, and `period_ms`, `drift_ppm_against_first` | `record-only` |

## 6. Level `full`: cameras together and the system (phase E)

### 6.1 Group checks

| Check | How | Numbers | Result |
|---|---|---|---|
| `group:take-30:finished`, `:csv-rows`, `:no-missing`, `:frame-count`, `:rate` | Each camera that passed `rate:1920x1080@30` alone (else `<base>`), one apply, a take of 30 s. The CPU of the process tree during the take (`psutil`). | as the `group:take` checks, and `mode`, `cpu_cores_used`, `cpu_share_p95` (3.5.8; `cpu_logical` is in `details`) | one check for each rule of 4.5 |
| `<label>:group-open` | Did this camera open in that group? | `measured_fps`, `alone_fps`, `stage` | `pass`; `fail` with `usb-bandwidth` (the camera that loses) or `rate-under-contention` |
| `group:contention` | The start-up rate of each camera in the group against alone. | `c<i>_group_fps`, `c<i>_alone_fps` (`<i>` is the detection index) | `record-only` |

### 6.2 System checks

| Check | How | Numbers | Result |
|---|---|---|---|
| `system:backend` (dropped by Q624a) | The source of each camera. | `backend` | `record-only` |
| `system:usb` | After the USB label is ported (section 13): the link of each camera, from `CameraDeviceInfo.usb_link` [req 3.2, 3.4] and the diagnostics D-9 (`usb_alt`) [ux 4.2 item 8, 4.6.2]. | counts `usb3`, `usb2`, `usb1`, `unknown` (key names); in `<label>:detect` the product value of `usb_link` (`"USB 1"`, `"USB 2"`, `"USB 3"`, `"unknown"` [req 3.2]) and `usb_alt` | `record-only`; `not-run` with `not-built` before the port |
| `system:kernel` | Linux: the kernel facts from the diagnostics (`kernel`, `driver`, `nodrop_param`, `clock_param`) [ux 4.6.2], and which `uvcvideo` quirks are expected: the Kiyo Pro `NO_LPM` quirk (7.0, and the stable 6.12.81, 6.18.34, 6.19.12), the C922 SOF quirk (6.11), `nodrop` (6.14). | `nodrop_param`, `clock_param`, `quirk_kiyo_pro_no_lpm`, `quirk_c922_sof` (`kernel_major` and `kernel_minor` are dropped: the host block of freemocap has the release, 20.8, Q793) | `record-only` (facts only); not in the report on Windows and macOS |
| `system:disk` | The product recorder with synthetic JPEG frames (rec 11) in the work folder: N camera writers, N = the count of cameras that passed, each at the size and the mean JPEG size of its camera at its largest passed 30 fps mode, 20 s; then 10 s at twice that load [U Q612]. | `file_system`, `cameras`, `need_mb_per_s`, `write_mb_per_s` (reached), `fsync_ms_max`, `give_waits`, `give_wait_ms_max`, `queue_high_water_s`, `cameras_supported` (from the measured JPEG size of the cameras) [U Q612]; the limit 500 ms in `details.limits` | `pass` when no `give` waits longer than 500 ms [A, not calibrated] and no stall; `fail` with `disk-slow`, `disk-stall`, `fat-disk` |
| `system:disk-benchmark` (merged into `system:disk` by Q612, 3.6.11) | Section 6.3. | `write_mb_per_s`, `block_ms_p99`, `fsync_ms_max`, `bytes`, `write_seconds` (3.5.1), `cameras_1080p30_typical`, `cameras_1080p30_worst` | `record-only` |
| `system:camera-apps` | Windows: a fixed allow-list of process names of programs that hold or change cameras, for example LogiTune and Razer Synapse [M `research/usb_cameras/docs/windows_results_20261113.md` §0]. | one boolean for each item of the list | `record-only` |
| `system:virtual-cameras` (dropped by Q624b) | The count from detection. | `count` | `record-only` |

### 6.3 The disk benchmark [U]

Replaced on 2026-11-23 [U Q612]: one disk check, `system:disk`, with 20 s at the real load and 10 s at twice
the load, and no file of 1 GiB (3.6.11). The text below is the earlier decision of 2026-11-20. It does not apply.

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
never a camera check [U]. The self-checks run the product: the session child, `CameraGroupManager` with
`source_factory` (ADR-HP7D item 10), real camera processes, the shared loop and the recorder. Only the
source is fake. The fake source must move from the tests into the package for this (section 13).

| Check | Level | What it does | Pass rule | What it proves | What it does not prove |
|---|---|---|---|---|---|
| `self:hang-100ms:gap`, `self:hang-100ms:hard-end` | quick [U], full | Three fakes at 720p30 are `ready`; the control read of one hangs past the bounded-call limit, on its control thread (T-CAP-82). | `gap`: the two others have no gap of taken frames above 100 ms [U]. `hard-end`: the hung process ends within the limit plus 2 s. | The rule of the software holds at the speed of this CPU, scheduler and OS [U: "so we can catch if rules are still valid on older/slower systems"]. | That a real driver hang does not block the USB stack of the other cameras. |
| `self:crash-take:finishes`, `:equal-rows`, `:others-record` | full | Three fakes record; the process of one ends with `os._exit(3)` at frame 100 (T-CAP-109 case 2). | `finishes`: the take finishes with `camera_dead` or `camera_file_short` as rec 7.3 and 7.4. `equal-rows`: the rows are equal. `others-record`: the others record to the stop. `others_gap_ms_max` is a number and decides nothing [A]: the 100 ms rule is for a hung camera, and a killed camera process cost the others 1 and 3 frames (a hole of 128 ms on one camera) [M run 11-20]. | The take survives a camera crash on this system. | A real driver crash. |
| `self:server-gone:ends`, `:files-finished`, `:source-closed` | full | Two fakes record; the main process of the session child ends with `os._exit`. | `ends`: each camera process ends within 10 s plus 5 s [A, not calibrated] [U: a dead server is noticed after 10 s, not 300]. `files-finished`: its files are finished. `source-closed`: its source is closed. | A crash of the app or of certify releases the cameras on this system. | A real camera. |
| `self:stall:take-error`, `:others-finished`, `:stalled-failed`, `:no-healthy-dead` | full | Two fakes record; the MKV file object of one blocks past the stall limit (10 s, rec 5.3). | `take-error`: `take_error` "disk stall on camera <id>". `others-finished`: the other camera's files are finished. `stalled-failed`: the stalled camera is `failed`. `no-healthy-dead`: no healthy camera is `dead`. | The stall rule holds on this system. | A real disk. |
| `self:idle-cpu` (every processor, ADR-63D9) | full | One paused fake camera process, 10 s (T-CAP-49). | Under 2 % of one core. | No thread spins on this OS. | — |
| `self:ring:torn`, `self:ring:lapped` (every processor, ADR-63D9) | full | The torn-read and lapped-read checks of the JPEG ring with two processes (T-RING-05 to 14, 28, 30, as product calls). | `torn`: each torn read is refused. `lapped`: each lapped read is refused. | The ring is safe on this CPU and its memory model, for example Apple Silicon (T-RING-34). | — |
| `self:scale-3`, `self:scale-12` (Q624f; were `self:scale-4`, `self:scale-8`) | full | 3 and 12 fakes at 1920x1080@30 with JPEGs of 200 kB, recording, 15 s each. | `record-only` (facts only, no pass rule) | The CPU that the software needs for N cameras: the headroom for more cameras than are attached. | USB bandwidth, a real driver. |

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
| `<label>:in-use` | A second session child holds the camera through the product source. Then an apply of the camera in the first session child. | `outcome` (`refused`, `shared`, `hung`), `stage`, `seconds` | `pass` only when the outcome is `refused` with the product code `camera-in-use` (cap 6.7, cap 21); `fail` with `not-refused` when the outcome is `shared`, and with `hung` or `wrong-reason` (20.2, Q788) |
| `<label>:rate:<w>x<h>@60` | An apply of this camera alone at the 60 mode, in `MANUAL` at -7 (7.8 ms is shorter than one period of 16.7 ms). A failed start-up rate check at 60 starts the fall back of the group [req 2.4]: the product answers with the configs at 30 and a warning `rate_fallback`, before the apply response, so no wait is needed. | `mode_fps`, `measured_fps`, `luma_mean`, `fell_back` | `pass` at -7; `fail` with `rate-low` and `fell_back` true after a fall back; `not-run` with `no-mode` |
| `<label>:modes:granted:<w>x<h>@60` | The granted mode equals the request (D-1). | as 4.2 | `pass`; `fail` with `mode-not-granted`; `not-run` with `no-mode` |
| `<label>:exposure:<w>x<h>@60` (removed by Q617, 3.6.11) | Only when `<label>:rate:<w>x<h>@60` passed: the sweep from -10 to -5 at the first 60 mode, live changes. | `fps_at_m10` ... `fps_at_m5`, `ok_exposures`, `shortest_ok`, `longest_ok` | `record-only`; `not-run` with `prior-check-failed` after a fall back |
| `<label>:auto-exposure:searched:<w>x<h>@60`, `<label>:auto-exposure:holds-rate:<w>x<h>@60` (removed by Q617, 3.6.11) | The Auto search after a change of the frame rate (5.3), at the first 60 mode. | as 5.3 | as 5.3; `not-run` with `prior-check-failed` after a fall back |
| `group:take-60:finished`, `:csv-rows`, `:no-missing`, `:frame-count`, `:rate` | Each camera whose 60 mode passed, at 60, with the exposure that held 60 for it, a take of 15 s. Needs two cameras. | as the `group:take` checks | one check for each rule of 4.5; `not-run` with `one-camera` or `no-mode` |
| `<label>:cycles` (30 cycles, and `group:cycles` with 10 opens of the group, by Q614, 3.6.11) | Five cycles of the product source `open` (on Windows `MediaFoundationSource.open`) at `<base>` (to the first frame) and `close`. | `cycles`, `ok`, `open_ms_max`, `first_frame_ms_max`, `close_ms_max`, `stage` | `pass`; `fail` with `hung` or `first-frame-timeout` at the first fault, and no more opens of that camera |

A declared 60 mode that never delivers 60 fails its own check, and the summary item stays at its base result [U]. Measured: the Kiyo Pro
declares 60 at each of its 4 sizes and delivered 29.7 to 30.4 fps at each exposure from -7 to -10; the
C922 delivered 60 at 1280x720 only at -7, 29.7 fps at -8 to -10, and 56.5 fps at -6
[M `research/usb_cameras/docs/free_run_log_20261120.md` §9]. The product offers 60 only when each
ticked camera passed a real 60 fps check [U]. Certify reports at which exposures 60 held. For the
Kiyo Pro, no exposure holds 60, so the fall back always comes, and the sweep and the Auto checks at 60
are `not-run` [cross-spec review C8].

The C922 at 60 with the Kiyo Pro open gave 46.5 fps over frames 6 to 90, then 58.7 fps over 10 s
[M same file]. Thus `group:take-60` can find `rate-under-contention` where each camera alone passes.

### 8.3 Phase G: re-check [U, A]

The user decided: "Ensure anything that gets broken during a run is fixed or flagged to the user "e.g.
camera <camera name> wedged, please replug"" [U]. He also decided that the product restores the
"before" values of each camera at its own close [U]. Thus:

1. The product keeps the "before" values of each control at the first control read of each open, and
   sets them back at each close, with a read-back [ux 4.7]. The diagnostics carry the values
   (`c_before`, `c_before_auto`) and the result of the restore (`restore_ok`,
   `restore_failed`, D-4). This holds on the three systems.
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

After a stop of the caller, the end of the budget, a time-out or a crash, the rules of phase G are [U] [ADR-X8XE](../decisions/entries/X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md):

- A camera that hung, whose process ended or that was removed (after any step) is `replug`. It is never opened
  again.
- A camera whose `opens` has no result was in the middle of its open. It is never opened again. Its settings are
  not known, so it is `not-restored`, never `healthy`. A camera that had a step running at the stop is the same,
  because the product needs 5 s to declare a hang [U, question 6 of ADR-X8XE]. This costs the restore of each camera
  after a cancel during the take.
- When the session closed its camera group itself (the close ran to its end), the close restored each camera:
  phase G takes the result of that close, as in quick with no stop, and opens no camera.
- A camera that another program holds, or whose first "before" values are not known (no control was set), gets no
  open and no row.
- Each other touched camera gets the plain open below. The session sends the "before" values of a camera as soon as
  its diagnostics hold them.

In quick with no stop, a camera whose loop failed with a wedge code that certify does not already count as a wedge
(`stalled`) after its controls were set is `not-restored`: the product does not restore it [ux 4.7]. A camera whose
loop failed for another reason (for example `rate-low`) gets the restore of the product at its close; its close dict
decides (`restore_ok` false is `not-restored`) [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md). This also holds after a
stream error of the source with a code that is no wedge: the source restores then [ux 4.7]. Certify keeps the
failure code of the status of the camera when it sees the failure (the main process writes it), so a later close dict
with another `fail_code` does not change the judgement.

Decided, not built [U, question 4 of [ADR-X8XE](../decisions/entries/X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md), 2026-11-21]: in quick, phase G opens a camera whose loop
failed and that is not wedged, and sets its "before" values back, in place of only the notice. When it is built,
this rule replaces the rule above in quick.

Decided, product work of a later fix round [U Q608]: the product keeps the restore record of the camera settings
on disk, so a restore survives a kill of the server. This spec does not change the rule of `camera-not-restored`
for it. The check `group:restore-after-kill` of 3.6.11 [U Q615] tests it when it is built.

The phase also runs after a crash of an earlier phase, with its own limit of 20 s for each camera
[A]. After a cancel, the user decided [ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md): phase G re-checks only the cameras that the run touched
(opened), with a plain open of at most 5 s for each camera, and it sets a control back when it differs
from its first "before" value. No new check starts after a cancel [C 2.4]: the re-check gives only
cleanup rows `release:<label>` and their notices.

**How the message reaches the person** [U, C 3.8]. A cleanup check records the fact; a notice tells
the person what to do [C 3.8]. Thus:

- skellycam writes the cleanup row `release:<label>` with a fixed reason code and `module` = the name
  of the summary item of the model [C 3.4].
- skellycam also writes one notice in `notices` [C 3.8] for each such camera:
  `{"code": "camera-wedged", "values": {"camera": "<cleaned name>"}}` or
  `{"code": "camera-not-restored", "values": {"camera": "<cleaned name>"}}`.
- `skellycam/REASON_CODES.md` gives each notice code with its meaning and its text for the person
  [C 5.4]: `camera-wedged`: "Camera <name>: wedged, please replug" [U]. `camera-not-restored`:
  "Camera <name>: a setting is not as it was before the run. Open the camera in SkellyCam and set it
  again."
- The app shows each notice at the end of the run, also when the person does not send the report.
- During the run, the progress message shows only the running check [C 2.3]. It cannot carry the
  message.

### 8.4 One consent before a full run [U]

The user decided: "yes, single accept before full run" [U]. `certify_plan("full")` gives the fixed
sentences of the risks in `risks` [C 2.6]. The app shows them at the one consent before `certify()`:

> The full run opens each camera many times and at each of its modes. A camera can stop answering
> until it is unplugged and plugged in again. The run puts back the settings of each camera at the end.

On macOS, `risks` also holds: "The last part of the full run sends direct USB requests to each camera
model and can make a camera stop until it is replugged." (the probes A5 to A8 of 10.7). The plan of a
quick run has an empty `risks` list [C 2.6].

## 9. The plan, cancel, privacy, cleanup

### 9.1 `certify_plan(level)` [A]

The function is `certify_plan(level, *, cameras=None, recording_folder=None, test_media_dir=None)`.
The keyword options are an extension of `certify_plan(level)` of [C 2.6], as [C 2.8] shows for
`test_media_dir`: an app that calls `certify_plan(level)` gets the defaults, and the options have the
meaning of 2.4.

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
 "total": 140,
 "risks": ["The full run opens each camera many times and at each of its modes. A camera can stop answering until it is unplugged and plugged in again. The run puts back the settings of each camera at the end."],
 "downloads": [],
 "system_changes": [],
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
- `system_changes` is empty in both levels: the product restores each camera at its close (8.3), and
  certify changes nothing else outside the work folder.
- `risks` is empty for `quick` and holds the sentences of 8.4 for `full` [C 2.6]. Changed by Q610 (3.6.4):
  `risks` of `full` holds only the sentences of checks that are built, so it is empty today, and
  `seconds_estimate` of `full` comes from the built checks (about 30 s).
- `total` is the count of checks that the run will do [C 2.6]. In the shape of 3.6.1 it counts no check with no
  code, and it counts `session:exit`; `details.checks` lists the same checks. A quick run with no camera model to
  check (for example, each model is reviewed, 2.5) has `total` 0: it checks nothing, and the app does
  not ask the person [C 2.7]. A model that the record holds as checked does not give `total` 0: a
  quick run with no option `cameras` checks it again (2.4). The app gives the option `cameras` from
  `details.unchecked`, so the pop-up run checks only the unchecked models (2.5) [U, question 1 of
  [ADR-X8XE](../decisions/entries/X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md)].
  With no camera to check, the run still reports `detect`, one check more than `total`: the user
  accepts this difference of one [U, question 2 of ADR-X8XE]. The quick self-check `self:hang-100ms`
  runs only when the run checks at least one camera model [A, question 8].
- `questions` holds `camera-ok-after` only for `full`.
- `details.cameras[].evidence` and `details.system_evidence` come from the known-systems file
  (section 11): `verified`, `known-bad` or `unknown`.
- `details.cameras[].checked` and `details.unchecked` come from the record of checked models (2.5)
  [U]. The app uses `details.unchecked` of `certify_plan("quick")` for the pop-up check.

### 9.2 Seconds estimate

Quick: section 4.7. Full: section 16.

### 9.3 Cancel and time limits [A]

- The caller reads `cancel.is_set()` and `abandon.is_set()` at least two times each second [C 2.4].
- `abandon` [C 1.6.0 2.4]: the run stops as for a cancel, and the checks that did not end are `not-run` with
  `cancelled`. Certify then writes no row to `camera_checks.json` and no report file, and it returns the module
  report. When `cancel` and `abandon` are both set, the rules of `abandon` apply.
- On a cancel, the caller stops the running check at once: it kills the child process of that check
  with its process tree (`psutil`) [C 2.4]. After a cancel no new check starts [C 2.4]. Then phase G
  re-checks the cameras that the run touched (8.3), with cleanup rows only, and phase H. A cancel
  then returns in about 1 s plus 5 s for each touched camera.
- On a time-out of a session child, the caller first ends the main process of the child only. Its
  camera processes notice the dead server after 10 s [U], finish their files and release the
  cameras. The caller waits for them at most 12 s, then kills the rest of the tree. Then phase G runs
  for the cameras that did not hang (8.3), and phase H [U: question 12 of draft 1, "yes"].
- `certify()` returns the finished checks with their results. Each check that did not end is
  `not-run` with `cancelled` [U] [C 2.4].
- Time limits: detection 20 s; the quick part 30 s (4.1); a camera block of `full` 240 s; a group
  take its length plus 30 s; a self-check 40 s; `system:disk` 60 s; the benchmark 45 s; phase G 20 s
  for each camera; a probe child of 10.7: the listing 15 s, a JPEG probe 60 s, a control probe 60 s,
  an endpoint-0 probe 90 s, the device-open probes 20 s each [A, not calibrated]. A child over its
  limit gives `fail` with `timed-out` [C 2.5].
- A check that cannot start because the time limit of the level was used up is `not-run` with the
  common code `over-budget` [C 5.3].
- The bound of the call [U] [ADR-X8XE](../decisions/entries/X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md). The budget of quick starts at the call, so it holds the detection: the
  detection ends at its limit of 20 s or at the end of the budget, whichever comes first. After the budget, the
  call can still take phase G (at most 5 s and about 1.5 s to start and end the child, for each touched camera
  that is opened again) and the wait for the end of the session child (`EXIT_LIMIT_S`, 5 s). Thus `certify("quick")`
  returns within 30 s + N x 6.5 s + 5 s, which is about 55 s for three cameras. After a crash or a time-out the
  wait of 12 s of the camera processes and 20 s for each camera in phase G apply: about 112 s for three cameras.
- The close of the group is never cut [A]. When the session starts the close of its camera group, it tells the
  caller. From then on the caller applies no budget stop and no cancel kill until the close ended or the close limit
  passed: 5 s + 8 s for each camera, from the bounds of the product close (a join of 3 s, a terminate and 3 s, a
  kill and 2 s, one camera process after the other). A stop that came in the close stays a stop for the report.
- The bound above assumes that each process ends when it is killed. A process in a driver call that does not
  return can add about 27 s (the waits of the kill, the grace and the exit). The worst case for three cameras is
  then about 77 s.
- The grace of 12 s at a time-out is 2 s more than the heartbeat limit of 10 s of a camera process: a camera
  process sees the dead server after 10 s and has about 2 s to finish its files and restore its camera before the
  rest of the tree is killed. Phase G then judges that camera again.
- Ctrl+C in a console reaches each process of the console. The camera processes ignore it; the session child ends,
  and the camera processes restore their cameras through the heartbeat path within about 12 s. The caller then
  stops the session and gives no report.
- The session child ends when its caller dies: it sets the kill flag, closes its camera group (the close restores
  each camera) within 15 s, and ends. Each wait of the child for its caller has a time limit. The caller stops the
  session child also when the progress callable or the cancel object raises an exception that is not an
  `Exception`.

### 9.4 Privacy and camera names [U, A]

The contract rules 1 to 16 apply [C 6]. In addition:

- Never in the report: a serial number, a device path or symbolic link, a device instance id, a
  location path, a port number or a hub chain, the `camera_id` (a hash of the link, so of the unit), a
  unit id (3.5.10) [U Q595], a host name, a user name, a file name or a folder of a take or of the disk checks, a
  frame, a log line.
- The failure text of the product (cap 12) is mapped to a reason code and never copied.
- `host` [C 3.3]: a field whose value skellycam does not know is left out or `null`. The module report
  has no key two times in one object [C 6 rule 19].

**Camera names [U Q596; point 5 withdrawn; the any-language rule U Q628].** The user decided the rule on
2026-11-23. His reason: "we need to know the names of the cameras, so if we find one that does or does not work,
we can tell end-users". He refused a rule for Latin letters only (Q625): "this needs to work for any language,
latin letters only is not sufficient" [U, ADR-63D9]. The rule below works for any script. The parts that he did
not say were choices of the agent ([ADR-M7JC](../decisions/entries/M7JC-choices-of-the-any-language-camera-name-and-the-usb-capability.md));
the user agreed to the rule as written (Q628, [ADR-BG8P](../decisions/entries/BG8P-decision-of-the-user-on-the-any-language-camera-name.md)), so they are marked [U Q628]. The rule uses no language model and no name recognition. It replaces the name cleaning of draft 3
(the steps 1 to 5 of `clean_name`). Each name of a summary item, a `module`, a notice and the plan comes from it.
The first rule that applies gives the name:

1. **No USB id**: `Camera (no USB id)` [U Q596]. The text of such a camera is never copied. This protects a
   phone or a computer that a person named in any script, for example a Continuity camera.
2. **An Apple device word** in the firmware product text, after NFKC and case folding: `iPhone`, `iPad`,
   `MacBook`, `iMac`, `FaceTime`, `Continuity`, as a whole word. A word is a run of letters or a run of digits, so
   `Annas-iPhone`, `iPhone15` and a fullwidth `ｉＰｈｏｎｅ` hold the word, and `Primacam` does not hold `iMac` [U Q628].
   The text is never copied. The name is a fixed class [U Q596; the map U Q628]: `iPad` gives `iPad used as
   camera`; `iPhone` or `Continuity` gives `iPhone used as camera`; `MacBook`, `iMac` or `FaceTime` gives `Mac
   built-in camera`. The words are tested in this order.
3. **A USB id in the list of known cameras**: the name of the list.
4. **A real USB camera with a USB id that is not in the list**: the product text of the firmware (the iProduct
   string of the device), through the filter below [U Q596, Q628]. The display name of the
   OS is not copied, because a person or the OS can set or translate it [U Q628]. When the firmware text cannot be
   read, or the filter refuses it: `Camera vvvv:pppp`. `details.cameras[].name_usb` holds the filtered text, or
   `null` (3.6.3).
   - Windows: the device property "bus reported device description"
     (`DEVPKEY_Device_BusReportedDeviceDesc`), read with no open of the camera. A check of 2026-11-23 on the four
     lab cameras [M, relayed by the supervisor]: it was readable for all four; it equals the display name for the
     two Logitech cameras; it gives `Razer Kiyo Pro` where the display name is only `USB Video Device`; it gives
     `USB Camera` for the generic camera.
   - Linux: the sysfs file `product` of the USB device [NV].
   - macOS: the IORegistry property `USB Product Name` of the `IOUSBHostDevice` [NV].

The relay publishes a report before a person of the project reads it [C 4.1, `relay/README.md` of the contract].
The protection is the filter below, and the person who sends the report sees the exact file and gives a clear
"send" [C 4.1]. The contract owner confirmed on 2026-11-23 that the relay keeps a name in any script and that the
format needs no change.

**The filter [U Q596, Q628].** It works on one string, in this order:

1. Normalise with Unicode NFKC.
2. Remove the direction control characters U+200E, U+200F, U+202A to U+202E and U+2066 to U+2069, so that a name
   cannot reorder the text around it in the Markdown part. When another character of the categories Cf, Cc, Co,
   Cs or Cn is left, the result is `Camera vvvv:pppp`.
3. Keep exactly the set that the relay keeps in an issue [C 6 rule 18, the answer of the contract owner]: each
   letter (category L) and each mark (category M, with Mn and Mc, so that Devanagari, Thai and decomposed accents
   keep their characters) and each number (category N) of any script, the space, and `.` `,` `:` `;` `_` `+` `=`
   `(` `)` `'` `%` `/` `?` `·` `-`. Each other character becomes a space. The earlier stricter set (with no `:`
   `/` `;` `=` `%` `?`) is not needed: step 8 refuses each path, URL and email form [U Q628].
4. Join each run of spaces into one space, and remove the spaces at the ends.
5. Remove a possessive head: the text up to and with `'s ` (`Bob's Webcam` gives `Webcam`) [C 6 rule 16].
6. Remove a group of 8 or more letters and digits that has at least 4 digits (a serial number), and brackets that
   become empty.
7. Cut to at most 60 code points (as Python `len`; the limit of a summary `name` is 80 [C 3.7]). The cut never
   falls between a base character and its marks: it moves back to the start of that base character. Thus a name
   has at most 240 bytes in UTF-8, and at most 720 bytes in the JSON of `json.dumps` with its `\u` escapes [U Q628].
8. Test the result with the ASCII patterns of the contract rules 1, 3, 4, 5, 7, 17 and 20 [C 6]: a path, a PCI
   bus address, a MAC address (also with `-`), an email address, a final extension of a media file, `<`, `](`,
   `]:`, `://`, `www.` (any case), an IPv4 address. On any hit, the result is `Camera vvvv:pppp`. Nothing is
   removed to pass a test.
9. A word that mixes letters of two scripts (a spoof, for example a Latin word with one Cyrillic letter) gives
   `Camera vvvv:pppp`. The script of a letter is the first word of its Unicode name in `unicodedata` (`LATIN`,
   `CYRILLIC`, `CJK`, `ARABIC`, ...), so no extra library is needed; digits, marks and signs belong to no script
   [U Q628].
10. The user name and the host name of the run, in any script: both sides get NFKC and case folding. A user name
    or host name of 3 code points or more is refused when it stands anywhere in the raw string or in the result.
    One of 1 or 2 code points is refused only when it is a whole word of the result, so that a short user name
    does not blank real names; in a script with no spaces (for example CJK) a whole word is the whole result [U Q628].
    A refusal gives `Camera vvvv:pppp`.
11. An empty result gives `Camera vvvv:pppp`.

When the filter gives `Camera vvvv:pppp`, `name_usb` is `null`. A name of a person in any script, for example
`Kamera von Jürgen`, can pass the filter. Only the person who sends the report sees it there, in the exact file
[C 4.1]. The firmware text of a USB camera rarely holds such a name, and a camera with no USB id never has its
text copied. Rule 16 of the contract says today that the package takes the name from the model string of the
device; the contract owner decides a change of its wording for the list name, the fixed class texts and any
script (open work).

**The list of known cameras [U Q596; the path and the form are A; the seed list is U Q627, DBF8 10].** One small data file in the
package:
`skellycam/core/camera/known_cameras.json`.

```json
{"format": 1,
 "cameras": {"046d:085c": {"name": "Logitech C922", "usb3_capable": false},
             "046d:0843": {"name": "Logitech C930e", "usb3_capable": false},
             "1532:0e05": {"name": "Razer Kiyo Pro", "usb3_capable": true}}}
```

- A key is a USB id `vvvv:pppp` in lower-case hex. A name passes the filter and has at most 60 characters. The
  optional field `usb3_capable` (`true` or `false`) gives the USB 3 capability of the model for 3.6.13 [U
  Q629]: the seed is the Kiyo Pro `true`, the C922 and the C930e `false` [M, lab data of 2026-11-23,
  relayed]. A test checks the file (T-CERT-100).
- The generic id `4c4a:4a55` has no entry, because many different cameras share it. A camera with such a shared
  generic id gets the name of rule 3. A pass of one camera with a shared generic id never proves that another
  camera with the same id works.
- A maintainer adds an entry in a pull request, for example from a reviewed report.
- Later work, not in this spec: an optional question to the person, "What make and model is this?" (open work).
- The local record (2.5) keys a camera with no USB id by its raw OS display name, not by `Camera (no USB id)`.
  The record never leaves the system.

### 9.5 Cleanup [A]

- The work folder is `skellycam-certify-<uuid4>/` in `recording_folder`, or in the temporary folder of
  the system. The take, the disk check and the benchmark write only there.
- Certify deletes the work folder at the end, also after a cancel, a crash or a time-out [C 2.5]. A
  folder that does not go gives the cleanup row `delete-work-folder` with `not-deleted`.
- At the start, certify deletes earlier `skellycam-certify-*` folders that hold the marker file
  `.skellycam-certify`. It deletes nothing else.
- One run at a time [U] [ADR-X8XE](../decisions/entries/X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md). A run holds the OS file lock of `certify.lock` beside `camera_checks.json` in the
  skellycam base folder for its whole time. A second run is refused as in 9.7, with `cameras-busy`, and makes no
  work folder. The OS frees the lock when the process ends. Another error of the lock file refuses the run with
  the class name of the error.
- The work folder can outlive a caller that died. It then holds the take, which is a recording of real frames.
  The next run in the same recording folder deletes it (it has the marker file).
- The log files: today the session child gives its camera processes the log folder `logs` in the work folder
  (`SKELLYLOGS_LOG_DIR`), unless the caller set that folder, and the session child itself writes no log file.
  Decided, not built [U Q559]: the logs of the last run stay in `certify_logs/` of the skellycam base folder
  (3.5.11). The cleanup never deletes them. There is no key file of a unit id (3.5.10) [U Q595].
- A record write that fails gives the cleanup row `write-record` with the class name of the error; the report
  still returns [C 2.5].
- The report holds no media and no file name of a take [C 6 rule 7].

### 9.6 Progress before each step [U, A]

The user decided: the progress callback is called with the name of a check before that check starts
[U]. freemocap writes that name to a file for crash reports. Thus:

- Before each check starts, certify calls `progress` with a message whose `step` names that check
  and whose `result` for it is `null` [C 2.3]. This holds for each check, also a computed check and a
  roll-up check of 11.3 [ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md). Certify starts the check only after `progress` returns.
- The report of skellycam has no sections, so `step` is `{"section": null, "name": "<check>"}` and
  each item of `checks` has `section` `null` [C 2.3, C 3.4].
- The contract allows at most 10 messages each second [C 2.3]. When a step would start less than
  100 ms after the last message, certify waits until 100 ms have passed [A]. It never drops a
  message before a step.
- If `progress` raises, certify stops calling it and continues the run [C 2.3].
- Each message holds the complete state of the run: each ended check with its full row (20.6 item 2, Q790).
- Decided, not built [U, question 3 of [ADR-X8XE](../decisions/entries/X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md), 2026-11-21]: the checks that only compute
  from data that the run already has (the JPEG, record and clock checks) share one progress message.
  A quick run then sends about 20 progress messages. Before, a quick run of three cameras sent 63
  messages, and the gap of 100 ms cost about 6 s of the 30 s. When it is built, this rule replaces the
  rule of one message before each computed check.

### 9.7 Cameras busy [U, A, C 2.5]

The app must close its own camera groups before a certify run [U]. When certify finds a camera group
of skellycam open in the calling process (the app state of the skellycam server), it cannot get the
cameras, so it refuses the run [C 2.5 "Cameras in use"]. It opens no camera. It returns the report
with each camera check `not-run` with the common code `cameras-busy`, and `evidence.reasons` holds
`cameras-busy` [C 5.3]. The other checks also do not run: they are `not-run` with `cameras-busy` [A].

One camera that another program holds, while the other cameras work, is not a refused run [C 2.5].
Its checks are `not-run` with `camera-in-use`, and its summary item is `skipped` with `busy` when
each unit of its model is held (3.3). A camera that a skellycam server in another process holds is
such a camera [U Q796]: only the processes of the same camera group are own processes, and the failed open
or, on Windows, the activity monitor finds the holder (20.5).

Replaced on 2026-11-25 (Q796, 20.5): the item "not built: a check for a camera group that another process holds
(review finding 11)" and its `certify.lock` idea. A group of `CameraGroup.create_without_cameras` (20.6 item 3)
does not count as an open group.

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
- Decided on 2026-11-25 (Q777, [ADR-13BB](../decisions/entries/13BB-decisions-of-the-user-on-the-dark-rule-the-light-data-and-the-phase-7-items.md)):
  the Linux and macOS checks and tests that need the native V4L2 and AVFoundation sources wait for phase 7. They
  are T-CERT-37, 40, 46, 52 to 57, 60, 62 and 63, and the fake layers. Until then they stay `not-built` in the
  report. On Linux and macOS the certify child would today fall back to the OpenCV source; phase 7 fixes this when
  it sets the capture choice of each OS. The checks of section 20 for Linux and macOS land with phase 7 too.

### 10.2 The assumptions as checks

Each check is a camera check `<label>:<name>` or a group or system check, one test each (3.3). Each
check runs when the camera opens, also when another assumption check of that camera failed: a failed
`native-jpeg` check does not stop `clock`, `sequence` or `controls` [A]. Only a failed `opens` stops
the others. "D-n" is a requirement of 10.3. "W" means that the same check also runs on Windows. Each
number that comes straight from the diagnostics has the name of its diagnostics key in [ux 4.6.2]
[A]; a number that certify computes has its own name. [ux] owns the keys and their values.

| Check | Assumption of the source | Pass rule | Numbers (how it failed) | Notes and sources | D |
|---|---|---|---|---|---|
| `<label>:native-jpeg:*` (W) | Linux: the camera gives its own MJPG bytes through `VIDIOC_DQBUF` on mmap buffers, with no re-encode. macOS: AVFoundation hands over the camera's JPEG in a block buffer (`'dmb1'`), not only decoded pixels. | the six checks of 4.4 | `requested_fourcc`, `granted_fourcc`, `granted_w`, `granted_h`, `delivered` (`jpeg`, `decoded`, `none`), `video_settings` (macOS: `nil`, `empty`, `dmb1`, `null`), `bytesused_equals_payload`, `error_flag_frames`, `zero_bytes`, `dqt_sha256`, the numbers of 4.4 | xplat §2.5 item 1, §2.6 G-MJPEG; L-MJPEG, M-MJPEG. One third-party run on macOS saw MJPEG only as decoded `420v`. On macOS the probes of 10.7 try each other way. | D-1, D-3, D-10, D-11 |
| `<label>:clock:base` (W; not planned on Media Foundation, 3.6.1) | The driver time of a frame is on the clock of `arrival_ns` (Linux `CLOCK_MONOTONIC`, the clock of `perf_counter_ns`; macOS host time). | `clock` is the arrival clock; `not-run` with `clock-unknown` when `clock` is `unknown` (the source cannot tell; Media Foundation), with `not-built` when it is null [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md) | `clock` (`monotonic`, `realtime`, `host`, `device`, `unknown`), `tstamp_src` (`soe`, `eof`, `unknown`), `ts_conversion`, `sample_time_kept` | Apple documents only the `synchronizationClock`. | D-2 |
| `<label>:clock:before-arrival` (W) | Each sample time is before its arrival. | `later_than_arrival` is 0 | `later_than_arrival` (`sample_minus_arrival_p5_ms` moves to `near-arrival`, 3.6.2) | — | D-2 |
| `<label>:clock:near-arrival` (W) | Each sample time is near its arrival. | `sample_minus_arrival_p5_ms` is `near_arrival_p5_ms` (-50 ms) or more, not calibrated; `fail` with `sample-too-early` (3.6.6 item 5) [U Q627, MEE1 22]. Before: p95 within 200 ms (cap 4.2), which cannot fail because each value is negative | `sample_minus_arrival_p5_ms`, `sample_minus_arrival_p50_ms`, `jitter_p95_ms` (certify computes it from `frame_log`); `grain_ms` and `sample_minus_arrival_p95_ms` are dropped (Q594, 3.6.2) | Linux: the buffer time is taken at the first payload, in steps of URB completions (up to about 4 ms). Windows: arrival minus sample 0.33 ms (Logitech) and 32 ms (Kiyo Pro) [M hardware_run_3a]. | D-2 |
| `<label>:time-gaps` (Linux, macOS, and W in `full`, only where `sequence_available` is false) | With no sequence number, a lost frame shows as a long interval between arrivals. | `long_intervals` (D-3, intervals over 1.5 periods of the mode rate) does not rise from the start to the stop of the take of 4.5; `fail` with `frame-gaps` [A, not calibrated] [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md) | `long_intervals`, `drops_reported`, `frames` | The user decided that the sequence check does not block the gate where the source gives no sequence number; the gaps are then judged from the timestamps [ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md). | D-3 |
| `<label>:sequence` (W where the driver gives a count) | The driver sequence number counts each frame that the camera sent, so that a drop shows as a gap. | each long interval has a sequence gap; `fail` with `sequence-unreliable`; `not-run` with `no-sequence` | `sequence_available`, `sequence_gaps`, `sequence_lost`, `long_intervals`, `long_intervals_with_seq_gap` (D-3), `discontinuity_flags`, `drops_reported` | Linux `v4l2_buffer.sequence`; macOS `CMIOSampleBufferGetSequenceNumber`. Windows: a dropped C930e frame showed only as a 64 ms gap and the discontinuity flag [M free_run_log §2]. | D-3 |
| `<label>:controls` (W, phase C) | The source lists each control with its range, its route and its scale. | record only | for each control `c` of exposure, gain, focus, white balance, power line: `c_present`, `c_min`, `c_max`, `c_step`, `c_default`, `c_auto_supported`; `exposure_unit`, `control_path` | macOS: the widest supported route wins over the unit [U, ADR-BVK7] [ux 4.4.6, 4.4.10]. | D-4 |
| `<label>:controls:exposure-scale` (W, phase C) | The source maps the skellycam exposure scale to the route. | Time-unit route (`exposure_unit` `log2-s`, `100us`, `seconds`): -7 maps to the expected native value within one step (Linux 100 µs: 78); `fail` with `unit-mapping`. Unitless route (`native`, `ev`, `native-data`): the route gives an ordered range of at least 8 distinct steps; `fail` with `scale-too-short`. `not-run` with `no-manual-exposure` | `exposure_unit` (`log2-s`, `100us`, `seconds`, `native`, `ev`, `native-data`, `none`), `exposure_native_at_m7`, `steps`, `control_path` (`v4l2`, `cmio-native`, `cmio-absolute`, `cmio-native-data`, `avf-lock`, `ep0`, `iam`, `ks`, `none`) | [ux] D-4 owns these values. The image direction is judged by `settings-stick:image-effect` (4.3). | D-4 |
| `<label>:auto-off:ae` (phase D) | Auto exposure can be turned off. | `ae_off_ok`; `fail` with `auto-not-off`; `not-run` with `control-absent` | `ae_off_ok` | xplat §2.6 G-CTRL | D-4 |
| `<label>:auto-off:af` (phase D) | Auto focus can be turned off. | `af_off_ok`; `fail` with `auto-not-off`; `not-run` with `control-absent` | `af_off_ok` | White balance is read only [cap D43]. | D-4 |
| `<label>:auto-off:ae-stays` (phase D) | Auto exposure stays off. | `ae_back_on_after_s` is `null`; `fail` with `auto-came-back`; `not-run` with `prior-check-failed` | `ae_back_on_after_s` | The source never sets an absolute value in auto (A-17). | D-4 |
| `<label>:settings-stick:*` (W) | A set value reads back, stays, and changes the image; at each later open the product sets the config value again. | the checks of 4.3 and 5.2 | the numbers of 4.3 | With the restore at each close [U], a value is not expected to stay after a close. Linux 6.16 and later: an idle camera can autosuspend and lose its controls; the product sets them at each open. The read-back can be cached, so the image decides. | D-4 |
| `<label>:modes:granted:<mode>` (W, phases B, C, F) | The listed modes are the modes that the camera delivers. | the granted format, size and rate equal the request; `fail` with `mode-not-granted` | `requested_*`, `granted_*`, `format_changes`, `modes_listed`, `mjpg_sizes` | `S_FMT` changes a size with no error; the Kiyo Pro declares 60 and gives 30. | D-1 |
| `<label>:identity:stable` (W, phase C) | The `camera_id` of the source is the same over two detections. | `fail` with `id-unstable` | `id_stable`, `id_source` (`serial`, `id-path`, `unique-id`, `mf-link`), `has_serial` | macOS: `uniqueID` holds the port. | D-7 |
| `<label>:identity:unique` (W, phase C) | Two cameras of one model have two `camera_id` values. | `fail` with `id-collision`; `not-run` with `one-camera` | `id_unique`, `id_source`, `has_serial` | Linux: by-id names collide for identical cameras with no serial. | D-7 |
| `<label>:timings` (W) | Open, first frame and close times. | record only | 5.5, computed from `t_open_ms`, `t_first_frame_ms`, `t_close_ms` and the other `t_*_ms` keys | L-CYC, M-CYC | D-6 |
| `<label>:in-use` (W, phase F) | A camera that another program holds gives a clear in-use failure at a known call. | 8.2 | `outcome` (`refused`, `shared`, `hung`), `fail_code`, `call` and `busy_call` (the call names of [ux 4.6.3]: `open`, `s-fmt`, `reqbufs`, `streamon`, `session-start`, `first-frame`, `querycap`, `s-parm`, `qbuf`, `dqbuf`, `poll`, `streamoff`, `close`, `s-ext-ctrls`, `g-ext-ctrls`, `add-input`, `lock-config`, `stop-running`, `cmio-set`, `cmio-get`, `activate`, `set-mode`, `read-sample`, `flush`, `shutdown`), `native_code` (a number), `native_domain` (`errno`, `hresult`, `nserror`, `osstatus`, `ioreturn`) | Linux: `EBUSY`, but `S_FMT` sends a PROBE to the camera before it. macOS: two programs can share a camera [NV]; under the rule of 20.2, `shared` fails. | D-5 |
| `group:open` (W) | A USB bandwidth refusal gives a known error. | 4.2 | `refusal_signal` (`error`, `zero-frames`, `low-rate`, `none`), `native_code`, `native_domain`, `call`, the camera that loses | Linux: `ENOSPC` at `STREAMON`, also `EIO`, `ENOMEM`, `EFBIG` (the map of [ux] A-15). macOS: no documented error. | D-5, D-9 |
| `system:camera-access` | The process can open cameras: Linux through the seat ACL or the `video` group; macOS with the camera permission of the app. | `pass`; with no access, each camera is `not-run` with `no-access` or `no-permission`, not `fail` | `access` (`seat-acl`, `video-group`, `root`, `none`), `tcc` (`granted`, `denied`, `restricted`, `not-determined`) | macOS: a process with no permission gets zero frames and no error. The app asks the camera permission before a run; certify shows no dialog [U]. | D-8 |
| `system:video-effects` (macOS) | Which system effects are on. | record only | `center_stage`, `portrait`, `studio_light`, `reactions`, `edge_light` (booleans, `null` when the source cannot read one) | M-FX | D-8 |
| the `group:take` checks, the `records` checks, the rate checks, the exposure sweep (W) | The rest of the product works on the native source. | as in sections 4 to 8 | sections 4 to 8 | T-CAP-92 to 94, 96 to 98 | — |

The endpoint-0 check of draft 2 (`<label>:control-ep0`) is now the probes A5 to A8 of 10.7, owned and
coded by certify [ux 4.4.10, 4.6.4] [U].

### 10.3 Diagnostics that certify reads [A]

The product path can show only what the source reports. Each source gives `diagnostics() -> dict`.
The camera process sends the full dict to the main process, and certify reads it with
`CameraGroupManager.diagnostics()`; the camera status carries only the counter subset [ux 4.2 item 2]. The keys are the keys of [ux 4.6.2], with the IDs
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
| D-3 | `sequence`, `native-jpeg` (`error_flag_frames`, `zero_bytes`) |
| D-4 | `controls`, `auto-off`, `settings-stick`, the "before" values and the re-check of phase G (`c_before`, `c_before_auto`) |
| D-5 | The reason of a failed check (`fail_code`), and the call and native code of the failure |
| D-6 | `timings`, `cycles` |
| D-7 | `identity` |
| D-8 | `system:camera-access`, `system:video-effects` |
| D-9 | `system:usb`, `group:open` |
| D-10 | `native-jpeg` (`encoded_by_skellycam`, `decoded_by_skellycam`) |
| D-11 | `native-jpeg` (the hashes after each trigger, compared with the ring slot and the MKV block of the same `source_frame_number`; `dqt_sha256` for the macOS JPEG proof of 10.7) |
| Linux, macOS rows | `system:kernel`; `native-jpeg` (`subtypes`), `clock` (`sync_clock_is_host`) |

Certify also reads `restore_ok` and `restore_failed` (D-4, the result of the restore at the last
close) and `long_intervals` and `long_intervals_with_seq_gap` (D-3). The search count is `exposure_search.count` of the status
[req 1.5].

### 10.4 Probes [U, A]

A probe is allowed only where the product path cannot see the fact [U]. It is named `probe:...` and
is code of certify, not of the product [ux 4.4.10]. GVC0 says that a probe is record-only. With the
rule "one test, one row" [U], each approach probe of 10.7 for one control is its own pass or fail
check; a probe that only lists facts stays `record-only`. No probe counts toward the summary item of
the camera. The user ruled this change of GVC0 [U]
([ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)). Two kinds
exist:

- A **system probe** runs in its own probe child and never opens a camera.
- A **camera probe** (only the macOS approach probes of 10.7) opens one camera at a time in its own
  probe child, with the session child of the product closed for that camera. It runs in phase D when
  it is safe and in phase F when it can change or block the camera (10.7). It never runs on a camera
  that hung or was marked dead, and the product never uses its result in the same run.

| Probe | Kind | What the product cannot see |
|---|---|---|
| `probe:camera-holders` (Linux) | system | The processes that hold the video nodes before any open (`/proc/*/fd`), as a fixed list `pipewire`, `wireplumber`, `other`. Certify then does not open a held camera, because `S_FMT` sends a PROBE to the camera before it returns `EBUSY`. |
| `probe:<model>:<approach>[:<control>]` (macOS) | camera | The approaches for camera control and for the camera's own JPEG that the product does not use, or that the product may choose for a control (10.7). |

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

Quick on Linux and macOS is the quick of section 4 through the native source (the five groups of
3.4), and also the three `clock` checks and `sequence`, which come from the same frames at no extra
time [A]. Thus quick meets the contract rule that a recording can start [C 2.7 rule 3]. `controls`,
`auto-off`, the other modes, `identity` and the macOS probes of 10.7 are in `full`. A quick row never
turns on native capture (11.3).

### 10.7 macOS: the approach probes for exposure and for the camera's JPEG [U, A]

The user ruled: on macOS, a certify run tries every approach that might work for exposure control and
for the delivery of the camera's own JPEG, for now. The test is trimmed when a working approach is
found [U] ([ADR-C5BR](../decisions/entries/C5BR-macos-approach-probes-in-certify.md)). The product
uses only the approaches that [ux 4.4.10] allows: for the JPEG `videoSettings = {}`, then
`kCVPixelBufferPixelFormatTypeKey = 'dmb1'`; for exposure, gain and focus a CoreMediaIO feature
control route (A1 `fcnv`, A2 `fcav` or A3 `fcnd`). The user decided: "I want to use the widest/best
supported route for camera control and prefer that over the measurement units for exposure. So if the
method that uses EV is better than the one that uses seconds, I'd take that." [U]
([ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)) Thus the unit
of a route does not decide; the count of models on which it works decides. [ux] owns the choice of
the route in the product. Certify tries each approach as a camera probe (10.4), and the probes of A1
to A3 are the evidence for that choice.

The list of the approaches, their steps, their sources and the approaches rejected without a trial
come from a desk research of 2026-11-20 that the supervisor gave to the agent [NV until a run]. This
section gives the checks. Each control probe is one check for each approach and each control:
`probe:<model>:<approach>:<control>`, with `<control>` one of `exposure`, `gain`, `focus`,
`white-balance`, `power-line`. Each JPEG probe is one check: `probe:<model>:<approach>`. A probe is
`pass` when the approach `works` by the proof rules below, `fail` when it only `appears` to work or
does not work (reason `no-image-effect`, `readback-differs`, `not-camera-jpeg`, `ep0-refused`,
`frame-gap`), and `not-run` when it could not run (`not-applicable`, `no-reference`, `too-dark`,
`too-bright`, `prior-check-failed`, `prior-failure`). `numbers.works` keeps the fact `works`,
`appears` or `no`. The listing `s0-listing` is `record-only`. Each probe check has the `module`
`macOS probes` (3.1) [ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md). The user accepts the many rows of the probes that do not pass on a healthy
camera: that module keeps them apart from the checks of the camera model.

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

**The proof rule for a control** [A]. A control `works` only when the image changes in the expected
direction: the mean luma of the centre 50 % of the decoded frame rises from the low to the high value
of exposure or gain, when the luma is 10 to 240. The size of the change does not count, because a
route can have a unitless scale [U: the route ruling]; the luma must change more than its noise (the
ratio of the high to the low value at least 1.1 [A, not calibrated]). For a route with a time unit,
the frame rate that falls at 62.5 ms (log2 s = -4) at 30 fps with `CT_AE_PRIORITY` = 1 also proves
it. Focus and white balance are judged by their read-back through the other path and by the
sharpness or the colour ratio moving in the expected direction. A read-back that equals the set value with
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

A model with no reference in the evidence file gets `not-run` with `no-reference` for its JPEG
probes; the fact `appears` stays in `numbers.works`.

**The probes, in run order** [A]:

| Step | Phase | Probe `probe:<model>:...` | What it does | Runs when | Time per model |
|---|---|---|---|---|---|
| 1 | C | `s0-listing` | No stream. The AVFoundation formats and the UVC descriptors from the IORegistry (no open); the codec types of a data output and a movie file output; the CoreMediaIO objects of the device and its streams, with their classes and the `HasProperty` and `IsPropertySettable` flags of each feature property; the supported AVFoundation modes; `respondsToSelector:` for the selectors of A10. | always | 5 s |
| 2 | C | `b3-nil`, `b1-empty`, `b2-dmb1`, `b2-jpeg4cc`, `b2-dmb1-sized`, `b2-chromium`, `b4-apple-jpeg` | The `videoSettings` variants of the data output at 720p30 and 1080p30 (B3 is the decoded control; B1 empty; B2 four variants; B4 the Apple JPEG encoder at quality 0.5 and 0.9, the re-encode reference). | the listing found a `'dmb1'` format, else `not-applicable` | 75 s |
| 3 | C | `b5-movie-file` | A movie file output with empty output settings and its file-output delegate, 5 s at 720p30; the delegate samples and the `.mov` samples (`stsd`, `stsz`, `stco`). | as step 2 | 15 s |
| 4 | D | `a9-avf-lock:exposure`, `a10-avf-custom:exposure` | A9: the camera's own auto for at most 2 s, then locked; luma drift over 60 frames; the mode after a restart. A10: only when the listing found an iOS-only selector: one guarded call. A9 is never a product mode [U: exposure rule]. | always; A10 only with a selector | 10 s |
| 5 | D | `a1-cmio-native:<control>`, `a2-cmio-absolute:<control>`, `a3-cmio-native-data:<control>`, `a4-cmio-tune:exposure` | CoreMediaIO feature controls: A1 `fcnv`, A2 `fcna`/`fcav` with the unit `fcun` and `fa2n` at -7, A3 `fcnd` on the `uc**` classes, A4 the one-shot Tune `fctn`. Exposure, gain, focus (sharpness record only), white balance, power line (read only). | each when the listing found its object; A4 only when A1 or A3 gave a manual path | 70 s |
| 6 | D (end) | `b6-cmio-stream` | A CoreMediaIO stream with no AVFoundation session: the MJPEG format description, `CMIOStreamCopyBufferQueue`, `CMIODeviceStartStream`, 3 s, then the stop in a `finally`, then one AVFoundation open and close as a check. | the stream lists an MJPEG format | 10 s |
| 7 | F (after the in-use and 60 fps checks) | `a6-ep0-device:<control>`, `a5-ep0-interface:<control>` | Endpoint-0 UVC class requests with no open: A6 `DeviceRequestTO` on the device plug-in, A5 `ControlRequestTO` on the interface plug-in. First read only (`GET_INFO`, `GET_MIN`, `GET_MAX`, `GET_RES`, `GET_DEF`, `GET_CUR`, 1000 ms timeout, at least 4 ms between requests) and the `VS_COMMIT` `GET_CUR`; then writes of exposure, gain, focus, white balance, power line; then the survival of a value over an AVFoundation mode toggle and a session restart. | always (a write only after its read passed) | 45 s |
| 8 | F (end) | `a7-device-open:exposure` | `USBDeviceOpen` with no seize, one `GET_CUR` and one `SET_CUR` of the same value, `USBDeviceClose`; hold time at most 100 ms. | only when A5 and A6 both failed | 10 s |
| 9 | F (last) | `a8-iousbhost:exposure` | `IOUSBHostDevice` with `options: []`, one `GET_CUR`, destroyed at once. | only when A5 and A6 both failed (as A7) | 10 s |

`b3-nil` (the decoded control) and `b4-apple-jpeg` (the re-encode reference) run no test of their
own: they are `record-only`. Steps 1 to 6 are the safe part. Steps 7 to 9 can change or block the camera, so they run in the risky
phase F, after the other risky checks, as the user decided for the risky checks [U]. Step 2 skips the
top-rate cells when B1 or B2 proves the camera's own bytes; B5 and B6 still run one time, to know the
fallback.

A7 and A8 run only when A5 and A6 both failed, because they are exclusive opens. A8 has no other
condition: it also runs when A7 worked. The user accepted this as the one exception to "every
approach is tried" (item 7 of [ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)).

Numbers for each probe [A]: `works`; the counts and codes of rule 6; for a control probe `set_ok`,
`readback_ok`, `luma_ratio_hi_lo`, `fps_effect`, `survives_restart`, `restore_ok`, `cmio_after_ep0`,
and `max_interval_ms` against the baseline (a probe with a frame gap over 2 times the baseline is
`fail` with `frame-gap`); for a JPEG probe `delivered`, `has_block_buffer`, `has_image_buffer`, `frames`, `fps`,
`soi_eoi_ok`, `strict_decode_ok`, `sof_matches_mode`, `dqt_sha256`, `dqt_distinct`, `dht_present`,
`dht_added_by_os`, `dqt_equals_reference` (or `no-reference`), `dqt_differs_from_apple_q50`,
`dqt_differs_from_apple_q90`, `apple_dqt_changes_with_quality`, the frame sizes, `cpu_pct`. Each
numeric code is a number; each name is a string of a fixed list. No raw bytes and no path.

**Drop rules** [U, A]. "Trimmed once a working one is found" [U]. A drop applies only through a row
that a maintainer accepted into `camera_evidence.json` (11.2): the row of the OS key and the model
gets a field `approaches` with the result of each probe for each control (for example
`"a1-cmio-native:exposure": "pass"`). A local run never drops a probe by itself. Until such a row
exists, each probe of the table runs. The control rows are per control [U: the route ruling]: keep
each route that works on any model; the product prefers the route that works on the most models of
the file; a route is dropped only for a model whose chosen route for that control is proven. With a
row:

| Result in the row | Keep | Drop |
|---|---|---|
| B1 `works` on each tested model | B1 | the B2 variants except `b2-dmb1`, B4, B5, B6 |
| B1 not, `b2-dmb1` `works` | `b2-dmb1` | the other B2 variants unless a model needs one; B5, B6 |
| No data-output variant works, B5 or B6 `works` | the one that works; a spec change of [ux] is then needed | B1, B2 |
| Nothing `works`, and `VS_COMMIT` says MJPEG | the product fallback (decode and re-encode) | B1 to B6 for that OS key; `b2-dmb1` again once for each new macOS major version |
| The MJPEG modes are listed only as `'420v'` | the fallback | B1, B2, B5; B6 only when the stream lists MJPEG |
| A control of a model has a proven route (A1, A2 or A3 `pass`) | each route of that control that passed on any model in the file | for that model and control: the routes that did not pass, and A5 to A8; A6 read only for one more run |
| A control of a model has no proven CoreMediaIO route, and A5 or A6 passes with no frame gap | A6 when both work, else A5 (a probe only; the product does not use endpoint 0 [ux 4.4.10]) | A7, A8 for that model |
| A5 and A6 refused, A7 `works` | A7 waits for a decision of the user (an exclusive open) | A8 |
| No route changes exposure | no Manual and no Auto on macOS for that model [ux 4.5 item 3] | A4, A10 |
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
The user accepted the longer macOS full run for now [U] ([ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)).

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
   "os_key": "11 26H2", "abi": "lp64", "state": "verified", "source": "maintainer", "limits": ["rate-60-at-m7-only"],
   "jpeg_reference": {"dqt_sha256": "<hex>", "dqt_distinct": 1, "dht_present": false},
   "reports": ["<report id>"]},
  {"device": "046d:085c", "model": "Logitech C922", "backend": "avfoundation", "os": "macOS",
   "os_key": "26", "abi": "lp64", "state": "verified", "source": "maintainer",
   "controls": {"exposure": {"cmio-native": "works", "cmio-absolute": "no"},
                "gain": {"cmio-native": "works"},
                "focus": {"cmio-native": "no"}},
   "not_passed": [{"check": "control:focus", "result": "fail", "reason": "readback-differs"}],
   "approaches": {"b1-empty": "pass", "a1-cmio-native:exposure": "pass", "a2-cmio-absolute:exposure": "fail",
                  "a1-cmio-native:gain": "pass", "a6-ep0-device:exposure": "pass"},
   "reports": ["<report id>"]},
  {"device": "1532:0e05", "model": "Razer Kiyo Pro", "backend": "media-foundation", "os": "Windows",
   "os_key": "11 26H2", "abi": "lp64", "state": "verified", "source": "maintainer", "limits": ["rate-60-not-delivered", "wedge-risk", "name-generic"],
   "reports": ["<report id>"]},
  {"device": "4c4a:4a55", "model": "USB Camera", "backend": "media-foundation", "os": "Windows",
   "os_key": "11 26H2", "abi": "lp64", "state": "known-bad", "source": "maintainer", "limits": ["rate-below-declared"], "reports": ["<report id>"]}
 ]
}
```

- `state`: `verified`, `known-bad`. A key with no row is `unknown`.
- `abi`: `lp64` or `ilp32`, beside the OS key [ux 4.6.4, A-23]. Each key of this file and of the
  local record (2.5) holds it.
- `jpeg_reference`: the DQT hash, the count of distinct DQT hashes and the DHT flag of the model (USB
  VID:PID) from a Windows or Linux passthrough run. The macOS JPEG proof of 10.7 compares with it.
  [ux] keys the reference by VID:PID with no `bcdDevice` [ux 4.6.4 item 10] [cross-spec review C14].
- `controls`: for each of exposure, gain and focus, the result of each route that was tried, keyed by
  its `control_path` value of 10.2 (`works`, `unproven`, `no`), as in the local row (2.5); a control
  whose routes are all `no` is absent in the UI [U].
- `not_passed`: for a row that comes from a `partial` item [C 7.2], each check of the item that did
  not pass, as `check` (the check name without the label of the unit), `result` and `reason`. The
  form is the rule of skellycam that [C 7.2] asks for (skellycertify ADR-T191).
- `approaches`: for a macOS row, the result of each probe of 10.7 for each control (`pass`, `fail`,
  `not-run`). Only this field trims the probes (the drop rules of 10.7).
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
- Linux and macOS: "when a system passes, native capture can be used there at once" [U]. Native
  capture turns on for a camera model (model, backend, OS key, ABI), never for a whole system or OS
  key [ADR-F2KY](../decisions/entries/F2KY-rulings-of-the-user-after-the-third-consistency-check.md): it is the default for a model only with a `verified` row of the model in the file, or
  with a local pass of the model (below, [C 7.2]). An OS key that is `verified` in `systems` turns no
  model on by itself. Each other model keeps OpenCV, and the app prompts the person to run certify
  for an unknown camera or OS version (11.4) [ux 4.9].
- **The gate** [U] ([ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)).
  Native capture turns on for a model on Linux and macOS through a fixed list of named checks of a
  `full` run at the base mode only (`<base>`, 720p at 30) [U]. The summary item plays no part.
  Failed exposure, gain and focus checks do not block: the control is then absent in the UI [U]. Each
  gate step is a roll-up check of the model [C 3.4], `<model>:gate:<step>`, with `module` = the model
  name. It runs no test of its own. It is `pass` only when each check that it requires is `pass` for
  each unit of the model that ran:

  | Roll-up check | Requires (at `<base>`) |
  |---|---|
  | `<model>:gate:opens` | `<label>:opens` |
  | `<model>:gate:mode` | `<label>:modes:granted:<base>` |
  | `<model>:gate:rate` | `<label>:rate` |
  | `<model>:gate:native-jpeg` | each `<label>:native-jpeg:*` check |
  | `<model>:gate:timestamps` | `<label>:clock:base`, `<label>:clock:before-arrival`, `<label>:clock:near-arrival`; when `clock:base` is `not-run` with `clock-unknown`, only the two others (Q585 of the user, 2026-11-23) [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md) |
  | `<model>:gate:sequence` | `<label>:sequence` for each unit whose source gives a sequence number; else `<label>:time-gaps` |
  | `<model>:gate:records` | each `<label>:records:*` check (a short recording through the native source) |
  | `<model>:gate` | each of the seven roll-up checks above and the check `<model>:gate:no-hang` |

  `<model>:gate:no-hang` is an ordinary check, not a roll-up check [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md): it scans each check of the
  model (also `cycles` and `in-use`) and is `pass` when no check has the reason `hung`, `crashed` or `stalled`
  (3.6.1),
  else `fail` with `hung`, `crashed` or `stalled`. A roll-up check that is not `pass` has the reason
  `gate-check-failed` or `gate-check-not-run` (3.3).

  The other modes and the 60 fps checks are not in the gate: the product rate check judges each mode
  at each open, and a 60 fps failure has the fall back [req 2.4]. `timestamps` stays required [U].
  The sequence check is required where the source gives a sequence number. Where it gives none (for
  example macOS, if AVFoundation gives no sequence number [ux M-10]), `<label>:sequence` is `not-run`
  with `no-sequence` and does not block the gate; `<label>:time-gaps` judges the gaps from the
  timestamps [ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md).

  **Replaced in the report [U Q597, Q611].** The seven roll-up checks `<model>:gate:<step>` leave the report.
  `<model>:gate` requires the checks of 3.6.2 directly, and `pipeline:gate` requires the pipeline and system
  checks of 3.6.2. The table above stays the meaning of the step values of the local record (2.5), which certify
  computes from the same checks. Until the sign-off checks are built, both gates are `not-run` with `not-built`
  (3.6.4) [U Q610].
- The `camera` summary item of a `full` report has `gate` = `<model>:gate` [C 3.7] (3.4). The pipeline item has
  `gate` = `pipeline:gate` (3.6.10).
- **The local pass** is for each camera model: a row of the local record (2.5) with the model, the
  backend, the ABI and the current OS key, the level `full`, and each value of `gate` `pass`, and a pipeline row
  (3.6.10) of the same key with each value of `gate` `pass` [U Q623]. A row with `"sign-off": "not-built"` is no local
  pass (3.6.4) [U Q610]. A `quick` row never turns on native capture [A]. The source selection of [ux 4.9] reads this row, and
  it reads `controls` for the route of each control (2.5). Inside certify, the source reads no row
  (2.5).
- On Linux and macOS the OpenCV source leaves the exposure to the camera. The user accepted this for
  now as a known limit of the temporary OpenCV path; the UI says "Exposure is set by the camera on
  this system" [U]. Certify does not test OpenCV.
- On a macOS control route with no time unit, Manual shows eight plain steps from darkest to
  brightest, with no time label, for now (item 10 of [ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)). `exposure` then holds the step index 0 to
  7 [req 1.1]. Thus `<label>:controls:exposure-scale` needs at least 8 distinct steps on such a route
  (10.2).
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
   - **Camera verified** for (device, backend, OS key, ABI): 3 valid `full` reports from 2 different
     systems in which `<model>:gate` is `pass`; or 1 valid `full` report of a maintainer
     (`source: maintainer`) in which `<model>:gate` is `pass` [U: the same gate as 11.3], and `pipeline:gate` is
     `pass` in the same report (3.6.10) [U Q623]. The row
     also holds the result of each route of each control (`controls`). A `partial` item whose `gate`
     check is `pass` gives the row, with `not_passed` (11.2) [C 7.2]; a `skipped` item never does.
   - **Camera known-bad**: 2 valid reports from 2 systems whose `details.gates[]` item of the model names the
     same `failed` check (without the label) with the same `reason`; or 1 maintainer report [U Q627, DBF8 15, review finding
     8]. The reason of the gate row is always `gate-check-failed`, so the cause comes from `details.gates`. A
     row of a unit with `blocked_by` (3.6.10) never counts.
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
- Done in commit `9e6d575` of the contract (skellycertify ADR-T191): a `partial` item whose `gate`
  check is `pass` gives a reviewed row, and the row keeps each check that did not pass (11.2,
  11.5).

Format 1.3.0 and 1.4.0 settled the summary results `partial` and `skipped`, one `camera` item for
each model, one check for each test, the roll-up check, `notices`, `risks`, `total` and the common
codes `cameras-busy`, `interrupted` and `over-budget`. The requests of 8.3 and 8.4 were sent [U] and
are in 1.4.0 (`notices`, `risks`). The `benchmark` group is for a GPU stage (`device` is a GPU id,
with `ms_per_frame` and `fps`): the disk figure does not fit it, so `write_mb_per_s` stays in
`numbers` of `system:disk` (Q612; `system:disk-benchmark` is merged into it) [A].
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

**The overlaps with freemocap, as settled on 2026-11-25** (Q778, Q779, Q789 to Q796,
[ADR-CQ2X](../decisions/entries/CQ2X-decisions-of-the-user-on-the-overlaps-with-freemocap.md)). freemocap-e7
agreed to overlaps 1, 2, 3 and 5, and countered on overlap 4; the user decided each one:

1. **Disk.** freemocap keeps its `data-folder` check: it writes, reads back and deletes a probe file, and records the
   free space. skellycam owns the disk speed and the take load (`system:disk`), and it records no free space.
2. **CPU.** No whole-system CPU benchmark in any module (freemocap ADR-4TK3). skellycam measures only its own
   processes.
3. **Recording.** freemocap makes no recording of its own. Its `full` check named `recording` downloads and cuts the
   sample recording; it is not a camera take. The two specs note this clash of names. The post-processing checks of
   freemocap use known-good media only, never a skellycam take, because a take holds private frames.
4. **Open camera groups** (the counter of freemocap, Q796). freemocap closes its own camera groups before a run, and
   its gate on camera starts during a check is built. freemocap runs the certify of each package in its own spawn
   child, so the groups of the app are in another process for certify. A camera that another process holds, also a
   skellycam group of freemocap, is `not-run` `camera-in-use` (20.5). `cameras-busy` stays only for an open group in
   the calling process (9.7).
5. **The new-model pop-up.** freemocap owns the pop-up, the crash progress file (built) and the notice
   "Camera <name>: wedged, please replug" (8.3). skellycam owns the checks and the record (2.5).

What freemocap needs from skellycam (Q790, Q792): the public call `is_model_checked`, the complete state in each
progress message (20.6), and the public constructor `CameraGroup.create_without_cameras` for its `realtime-session`
check. Host facts: skellycam writes no third copy (20.8, Q793). The privacy list of a merged report moves into the
contract (20.8, Q794). The macOS permission: freemocap asks when certify runs inside it (20.8, Q791).

Not settled here (Q795): freemocap's certify child still uses `fork` on Linux, and skellycam refuses `fork`
(`start-method-fork`, [ux 4.12]). The candidate fix, sent to freemocap-e7, is that `ManagedProcess` of skellycam
takes a multiprocessing context, so that freemocap can pass `spawn` without a global setting. It stays in the wider
review of freemocap on Linux ([ADR-T34M](../decisions/entries/T34M-decision-of-the-user-on-the-start-method-of-camera-processes.md)).

## 13. What the product is missing

The "Today" column states the code of 2026-11-25 (Q772). Rows 2, 3, 12, 15 and 16 hold for
Media Foundation only: the OpenCV source gives `null` for each diagnostics key except `backend`.

| Need | Today | Step that delivers it |
|---|---|---|
| A fixed failure code (`camera-in-use`, `usb-bandwidth`, `hung`, ...) in the failure object of cap 12 | Built: `CaptureFailure.code` with the codes of `failure_codes.py`. Media Foundation maps its HRESULTs (`errors.py` `hresult_code`). | Step 7s: `CaptureFailure.code` with the codes of [ux 4.6.3], also for Media Foundation [ux 4.2 item 1]. The user decided the code [U]. |
| The controls before the first set, in the diagnostics (`c_before`, `c_before_auto`) | Built for Media Foundation: `ControlRestore.fill` writes `<control>_before` and `<control>_before_auto`. | Step 7s [ux 4.6.2, 4.7]; the Media Foundation source in the same step |
| A restore of the "before" values at each close, on by default, on the three systems, with its result in the diagnostics (`restore_ok`, `restore_failed`) | Built on Windows (Media Foundation, `ControlRestore.restore`), with the record on disk (`restore_store.py`). No restore on Linux and macOS: the OpenCV source has none. | Step 7s for Windows (done). Linux and macOS: the native sources of phase 7. The user decided that the product restores at its own close [U]; [ux 4.7] has it on by default, with the keys `restore_ok` and `restore_failed`. |
| The state `adjusting`, `exposure_search` in the status, and a new search when the frame rate changes | Built: `camera_loop.py` `_start_search`; a reopen for a rate change searches again. The OpenCV source searches on Windows only (`searches`). | Step 7s and the Media Foundation change of [ux 4.5]; the rule is a decision of the user [U] (5.3) |
| A count of frames that skellycam encoded and decoded (`encoded_by_skellycam`, `decoded_by_skellycam`) | Built: the loop counts `encoded_by_skellycam` (`_process`), and the decode stage counts `decoded_by_skellycam` (`decode.py`). | Step 7s, the shared loop [ux 4.2 item 3]; 3b for the encoder |
| The diagnostics dict of [ux 4.6.2], sent to the main process (`CameraGroupManager.diagnostics()`) | Built: `CameraGroupManager.diagnostics()`; a closed group keeps its last dicts (`closed_diagnostics`). The dict of a hung camera can still be lost (last row, P3). | Step 7s [ux 4.2 item 2] |
| The local record `camera_checks.json` in the skellycam base folder, with the gate and the routes of each model (2.5, 11.3) | Built: the reader `camera_checks.py`, the writer `catalog.write_record`. | The certify step |
| A public enumeration with no activation, bounded, for the plan | Built on Windows: `detect_media_foundation_cameras(modes=False)` in the detection child. Linux and macOS: no list for the plan (`run.py` `_enumerate`). | The certify step (done for Windows); Linux and macOS: the native detection of phase 7 |
| The full mode list with formats (`capture_modes`) | MJPG only | 3c |
| Uncompressed modes | Partly: the ring and the decode take YUY2 and NV12. No source captures them, and the mode list is MJPG only. | 3b |
| Gain and focus through the config; white balance and power line read | The config sets exposure only. Media Foundation reads gain and focus. White balance and power line are not read. | 3c |
| Control ranges (min, max, step, default: `GetRange`) | Media Foundation reads the ranges of exposure, gain and focus into the diagnostics. Detection does not carry them. | Not in the 3c spec. Add to 3c. |
| USB link per camera | Built: `usb_connection.py` is ported from upstream `sfn26`, and `_add_usb_links` of `detect_cameras_devices.py` fills `usb_link` after detection. The UI label is built. The lookup runs in the main process with no time limit. | Step 5: the bounded lookup in the detection child [req 3.4, 3.5] |
| The model name (USB product string) | Friendly name only | 5d (`device.model`, rec 6.7) |
| Stage times (open, first frame, ready, close) in the status | Media Foundation: the open, first-frame and close times are in the diagnostics dict (D-6), not in the status. No ready time. | The certify step |
| A discontinuity count in the status or `CameraTakeResult` | In the status: `diagnostics.discontinuity_flags`. Not in `CameraTakeResult`. | The certify step |
| `measured_fps` after `too_slow` | Fixed: `_too_slow` sets `measured_fps`. | Done |
| The fake source and a synthetic frame source in the package | In `skellycam/tests/` | The certify step |
| A SemVer version and the build commit with no git (C 2.5) | Built: `2.0.0-alpha.6` (`_version`), and the commit from `build_info.json` (`tools/build_info.py`, `read_build_info`). An editable install has no commit. | The certify step (done) |
| The evidence file, its checker, the `evidence` field of detection | The `evidence` field and its reader are built (`camera_checks.py`). No evidence file and no checker. | The file and its checker: the certify step (section 11). The `evidence` field of `CameraDeviceInfo`: step 7s (done) |
| The native V4L2 and AVFoundation sources, with the diagnostics D-1 to D-11 of 10.3 | Research code only | Phase 7, moved up [U]; spec [ux] |
| The facts of 3.5: the call names of the close, `first_fail_code`, `exit_code`, the rate window keys, the dict of a hung camera in the main process, `usb_facts`, the build file | P7 (the build file) is built. P1 to P6 are not: `CALLS` lacks the release names, the first code is lost, the dict of a hung camera is not sent at the hard end, and there is no `exit_code`, no rate window keys and no `usb_facts`. | 3.5.15, P1 to P7 |

## 14. Questions for the user

The user answered each question of draft 1 and of draft 2, and the questions 2, 7 to 10, 12 and 13 of the
earlier forms of draft 3, on 2026-11-20
([ADR-GVC0](../decisions/entries/GVC0-certify-decisions-of-the-user.md),
[ADR-KG00](../decisions/entries/KG00-certify-decisions-of-the-user-on-draft-2.md),
[ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)). These
questions are the open ones. Each is worded so that "yes" accepts the recommendation. The most
important is first.

1. Decided by the user on 2026-11-20 ([ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md)): `skipped` (busy) when each unit is held by another
   program; `fail` when an open, rate or recording check fails; `pass` when each check passes;
   otherwise `partial` (3.4).
2. A skellycam upgrade does not make a row of `camera_checks.json` stale; only a new OS key, ABI or
   backend does (2.5). Yes?
3. A model counts as checked only when its summary item ended `pass` or `fail`, or `partial` with at
   least one unit whose `<label>:opens` is `pass` or `fail` (2.5); an item `skipped` (busy), a
   `partial` item where no unit judged `opens`, and an interrupted run write nothing, so the app checks
   that model again at its next open. Yes?
4. A full run checks the camera block (phases C, D and F) of one camera for each model; each other
   camera of that model gets its quick checks, the group checks, and `not-run` with `same-model` for
   the block. A run with more than four different models then goes above 11 minutes (about 18
   minutes for eight models on Windows). Yes to both?
5. For an interrupted run (9.8), each check item of a progress message also carries its `reason`,
   `module` and `numbers` after it ends, so that freemocap can write the interrupted module report from
   its progress file. Yes?
6. Decided: commit `9e6d575` of the contract gives the `gate` of a summary item; a `partial` item
   whose `gate` check is `pass` gives a reviewed row (11.5, 11.6).
7. Decided by the user on 2026-11-20 ([ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md)): after a cancelled run, only the cameras that the run
    touched are re-checked, 5 s each (8.3).
8. The quick self-check `self:hang-100ms` runs only when the quick run checks at least one camera
    model, so that a system whose models are each checked or reviewed has `total` 0 and gets no
    prompt (9.1) [C 2.7]. Yes?
9. Decided by the user on 2026-11-20 ([ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md)): the progress callback names each check before it
    starts, also a computed check and a roll-up check (9.6).
10. `cameras-busy` (9.7): certify refuses the run only when it finds an open camera group of
    skellycam in the calling process, and then also the checks that do not touch a camera are
    `not-run` with `cameras-busy`. Decided by the user on 2026-11-25 (Q796, 20.5): yes; a camera that
    another process holds, also another skellycam group, is `not-run` `camera-in-use`.
11. A full run checks the Auto rule "search again when the frame rate changes" at 60 fps (5.3), and
    the 60 fps fall back makes those checks `not-run` (8.2). Yes?
12. With the quick budget of 30 s (4.1), `self:hang-100ms` starts only when 10 s of the budget remain,
    so a quick run that checks a camera usually gives it `not-run` with `over-budget`; it always runs
    in `full`. Yes?
13. Decided by the user on 2026-11-23 ([ADR-G0AC](../decisions/entries/G0AC-decisions-of-the-user-on-the-certify-verdict-questions.md)): Linux and macOS quick keeps its clock rows (Q620); a
    failed group take counts against one model when one camera caused it (Q621); a pipeline check that fails on
    each model leaves the model items unchanged (Q622); the local pass and the verified row of a model also need
    `pipeline:gate` `pass` (Q623).
14. Decided: Q621 (item 13).
15. Decided: Q622 (item 13).
16. Decided: Q623 (item 13).
17. Decided by the user on 2026-11-23 as Q624a to Q624m (3.6.12,
    [ADR-493E](../decisions/entries/493E-decisions-of-the-user-on-the-certify-check-drops-and-additions.md)), with
    the scale points 3 and 12 in place of item 5. The proposals were:
    1. Drop `system:backend` (`details.backend` holds it) and `system:virtual-cameras` (`detect` holds the count).
    2. Move `control:white-balance` and `control:power-line` to the inventory of `details.cameras` (read only, no
       rule).
    3. Drop `control:focus:sharpness` and `control:autofocus` until a pass rule exists.
    4. Merge `<label>:timings` into `cycles` and `details.steps` (the same open and close times).
    5. One `self:scale-8` in place of `self:scale-4` and `self:scale-8`.
    6. Run `self:idle-cpu`, `self:ring:torn` and `self:ring:lapped` on arm64 only (the test suite covers x86).
    7. Look again at `identity:stable` and `identity:unique`; with no unit id their use may be gone.
    8. Add a check that the recorded MKV opens through the reader of the product (pipeline, quick, under 1 s).
    9. Add a burst check: the share of arrival intervals under half a period (model, full, from the take).
    10. Judge the USB link: a camera that declares USB 3 on a USB 2 link, and the sum of the need on one
        controller (system, quick, no cost).
    11. Read the free memory and, on Linux, the size of the shared-memory mount against the need of the rings
        before the open (system, quick).
18. Refused by the user (Q625, ADR-63D9): a name rule for Latin letters only is not sufficient.
19. Decided (Q626, [ADR-63D9](../decisions/entries/63D9-decisions-of-the-user-on-the-processors-the-build-order-and-the-certify-choices.md)): the build order of 3.6.7 replaces the order of Q575.
20. Decided (Q628, [ADR-BG8P](../decisions/entries/BG8P-decision-of-the-user-on-the-any-language-camera-name.md)), except the macOS part, which Q629 replaces: the any-language name rule of 9.4 (the firmware text only, the filter of the relay set with the direction
    marks removed, the cut at 60 code points, the spoof and short-name rules) and the USB 3 capability of 3.6.13
    (the hub flags on Windows, `bos_descriptors` on Linux).
21. Decided (Q629, revised): the three-state fact, the source order, the known-list field, the milder notice,
    and the trial `<label>:usb3-trial` at the end of a full run on macOS and Linux (3.6.13). The user refused a
    stand-alone probe.

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
| `same-model` | camera block checks of `full` | Another camera of the same model had these checks in this run (5.1). Not given in the shape of 3.6: such a check gives no row. |
| `scale-too-short`, `auto-search-failed`, `not-camera-jpeg`, `frame-gap`, `ring-lapped` | 10.2, 5.3, 10.7, 4.4 | The unitless exposure route has fewer than 8 steps; the search ended `failed`; the JPEG is not the camera's own by the proof rules; a probe made a frame gap over 2 times the baseline; the ring no longer holds the hashed frame. |
| `auto-not-searched` | `auto-exposure` checks | SkellyCam Auto did not search at the open, or after a change of the frame rate (5.3). |
| `one-camera` | group checks | The check needs two cameras. |
| `no-ui` | `player-legacy-decode` | The run has no page of the app, so the decode check of the v1 player cannot run (3.6.2) [A]. |
| `no-mode` | mode checks | The camera does not declare this mode. |
| `no-mjpg-mode` | `<label>:detect` | No MJPG mode at 30 fps or more (before 3b). |
| `below-floor` | `opens` | The nearest mode is below 30 fps (cap 7.5). |
| `camera-in-use` | `opens` and each check of that camera | Another program holds the camera. Its summary item is `skipped` with `busy` [C 3.7]. |
| `usb-bandwidth` | `opens`, `group:open`, `<label>:group-open` | The USB controller refused the stream for bandwidth. |
| `not-found` | `opens` | The camera was gone at the open. |
| `open-failed` | `opens` | Another open failure; `numbers.native_code` and `numbers.native_domain` hold the code. |
| `first-frame-timeout` | `opens`, `cycles` | No first frame in 5 s (cap 6.4). |
| `hung` | any camera check | A bounded call hung; the camera process ended hard (cap 6.6). |
| `not-ready` | `opens` | Not ready in 15 s (cap 9.3). |
| `rate-low`, `rate-high` | rate checks | More than 3 % below or above the mode rate. The sentence of `rate-low` is the product text: "Camera is slow. Try adding more light" [U]. |
| `rate-under-contention` | group | The camera passes alone and fails in the group. |
| `too-dark`, `too-bright` | light-dependent checks | The frame is too dark or too bright to judge (4.6). |
| `no-frame` | light-dependent checks | The check got no frame to measure its brightness, so it cannot judge (4.6) [U Q818]. |
| `readback-differs`, `setting-reverted`, `no-image-effect`, `control-failed`, `exposure-not-applied` | settings and control checks | A set value reads back different; it changed back later; the image did not change; the set call failed; a set exposure did not apply. |
| `control-absent` | control checks | The camera has no such control. |
| `no-native-jpeg`, `jpeg-damaged`, `jpeg-size-differs` | `native-jpeg` | skellycam encoded the frames; a frame is damaged; its size is not the size of the mode. |
| `wrong-reason` | `<label>:in-use` | The product gave a failure that is not "in use". |
| `not-refused` | `<label>:in-use`, `<label>:in-use:other-program` | The product opened a camera that another process holds (`shared`). The product did not stop the sharing (20.2). |
| `holder-failed` | `<label>:in-use:other-program` | The holder child got no frame, so the check cannot judge (20.3). |
| `not-warned`, `not-marked` | `<label>:in-use-mid-take` | No warning within 2 s of the join; no take mark of the interval (20.3). |
| `no-shared-mode` | `<label>:in-use-mid-take` | Windows before build 26100: certify cannot start a shared reader (20.3). |
| `hog-not-settable`, `hog-not-exclusive` | `probe:<model>:hog-mode` | Hog mode does not read back; a second session still starts (20.4). |
| `no-frame` | light-dependent checks | No frame or no ratio to judge (20.7). |
| `read-gap` | `<label>:control-read:gaps` | The one-second control read made a frame gap above 100 ms that the stream with no read does not have (20.9). |
| `device-removed`, `stalled` | any camera check | Removed; no frame for 2 s (cap 6.7). |
| `previous-process-alive`, `stream-error`, `format-changed`, `process-ended` | any camera check | Product failure codes of [ux 4.6.3]: an earlier camera process still holds the camera; the stream gave an error; the format changed during the stream; the camera process ended (certify reports `crashed`). |
| `take-not-finished`, `take-error`, `rows-differ`, `missing-rows`, `gaps-unexplained`, `group-rate-off`, `too-few-frames`, `frame-not-decodable` | take checks | Section 4.5. |
| `fat-disk`, `disk-stall`, `write-error`, `disk-slow`, `disk-full` | take checks, `system:disk`, `system:recording-space` | rec 4.2, 5.3, 5.4; section 6. `disk-full`: less than `minutes_free_min` minutes of recording are free (3.6.11). |
| `gap-over-limit` | `self:` checks | A healthy fake camera had a gap above 100 ms. |
| `clock-base-differs`, `clock-unknown`, `sample-after-arrival`, `sample-too-early` | `clock` | 10.2. `sample-too-early`: `sample_minus_arrival_p5_ms` is below `near_arrival_p5_ms` (3.6.6 item 5). `clock-unknown`: the source cannot tell the clock of its frame times. |
| `sequence-unreliable`, `no-sequence` | `sequence` | 10.2. |
| `frame-gaps` | `time-gaps` | A long interval between arrivals on a source with no sequence number (10.2). |
| `gate-check-failed`, `gate-check-not-run` | roll-up checks of 11.3 | A required check is `fail`; else a required check is `not-run` (3.3). |
| `unit-mapping`, `auto-not-off`, `auto-came-back`, `setting-lost-on-reopen`, `mode-not-granted`, `id-unstable`, `id-collision` | assumption checks | 10.2. `setting-lost-on-reopen`: the config value did not read back at a later open. |
| `ep0-refused` | probes A5 to A8 (10.7) | The camera or the system refused an endpoint-0 request. |
| `no-access`, `no-permission` | camera checks | Linux: no access to the video node; macOS: no camera permission for the app. |
| `no-manual-exposure` | `controls`, `settings-stick`, `auto-exposure`, `exposure` | A camera with no manual exposure: it opens with a warning, and SkellyCam cannot set its exposure [ux 4.5 item 3]. Always `not-run`, never `fail`. It is not a failure code of the product [ux 4.6.3]. |
| `not-applicable`, `no-reference` | macOS probes (10.7) | The listing found no object or format for this approach; the evidence file has no JPEG reference for the model. |
| `prior-failure`, `prior-check-failed` | any, `<label>:not-reached` | The camera hung or failed earlier; a check that this check needs did not pass. Both are in `skellycam/REASON_CODES.md` (3.6.1). |
| `mkv-not-readable`, `mkv-frames-differ`, `memory-low`, `shm-too-small`, `report-rules` | checks of 3.6.12; `report-rules` also in `evidence.reasons` | The MKV does not open through the reader of the product; its frame count is not the frame count of the take; the free memory, or the shared-memory mount on Linux, is below the need of the rings; the report breaks a privacy or form rule. |
| `camera-gone-after-usb-trial` | notice [C 3.8] | 3.6.13: the camera is not listed after the request of the trial. Text: "Camera <name> stopped answering after the last check of the run. Unplug it and plug it in again." |
| `PermissionError`, `TimeoutError`, `OSError`, `NotOpen`, `FunctionTableNotVerified`, `NoBosDescriptor`, `PlugInNotCreated`, `InterfaceNotFound`, `NotSupported` | `numbers` of `<label>:usb3-trial` (`<method>_error`) | The class of the error of one method of the trial (3.6.13). |
| `camera-maybe-faster-usb-port` | notice [C 3.8] | 3.6.13, `usb3_capable` `possible` on a USB 2 link. Text: "Camera <name> may support a faster USB port. If the computer has a USB 3 port (often blue), try it there." |
| `camera-usb3-on-usb2-link` | notice [C 3.8] | Text: "Camera <name> is a USB 3 camera on a USB 2 port. Plug it into a USB 3 port (often blue) if the computer has one." |
| `not-decided-one-model` | `details.pipeline.reason` | A pipeline check failed, and with one model only the run cannot tell the pipeline from the camera (3.6.10). |
| `recording-volume-not-fixed` | notice [C 3.8] | The recording folder is on a removable or network drive (3.6.11). Text: "The recording folder is on a removable or network drive. A recording can lose frames there. Choose a folder on an internal drive." |
| `camera-wedged`, `camera-not-restored` | cleanup `release:<label>`; notice codes [C 3.8] | 8.3. Notice texts: "Camera <name>: wedged, please replug"; "Camera <name>: a setting is not as it was before the run. Open the camera in SkellyCam and set it again." |
| `not-deleted` | cleanup | The work folder did not go. |
| `<ExceptionClass>` | any, cleanup | A step raised this class. Never the message. |

Fixed values in `numbers`: `backend` (3.1), `stage` (cap 12, `-` for a space), `state` (cap 8.1),
`outcome` (8.2), `format`, `file_system` (`ntfs`, `refs`, `exfat`, `fat32`, `apfs`, `hfs`, `ext4`,
`btrfs`, `xfs`, `other`), `usb_link` (the product values `USB 1`, `USB 2`, `USB 3`, `unknown`
[req 3.2]), the values of 10.2, the
`limits` codes of 11.2, and the vocabularies of 3.5: `native_domain`, `call` and `stage` (3.5.3),
`take_error_kind` (3.5.7), `volume_kind` and `spread_source` (3.6.11), `access` and `power_plan` (3.6.12). The
codes of `take_warnings` (`camera_dead`, `camera_file_short`,
`camera_gap`, `take_error`) are in a list, so `skellycam/REASON_CODES.md` lists them as codes [C 3.4].

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
| 1 (1) | 30 s at most (4.1) | about 6 min (265 + 100 s) |
| 4 (4) | 30 s at most | about 11 min (265 + 400 s) |
| 4 (2) | 30 s at most | about 8 min (265 + 200 s), with one camera block for each model (5.1) |
| 8 (8) | 30 s at most | about 18 min (275 + 800 s) |

The user accepts a full run of 6 to 11 minutes [U]. A run with more than four models goes above 11
minutes (question 4). The quick figures are the budget of 4.1, with the restore in the product
[U]. The camera blocks run one camera at a time: two
cameras at once would share a USB domain and change each other's results. On Linux and macOS the
assumption checks of 10.2 come mostly from the same opens; they add about 10 s for each camera, from
the 12 to 15 and 20 to 30 minutes of the research runbooks for four cameras [M `research/usb_cameras/suite/linux/RUNBOOK_PLAN.md`,
`suite/macos/RUNBOOK_PLAN.md`]. On macOS the approach probes of 10.7 add about 230 s for each model
(10.7 gives the full times on macOS). All figures are [NV] until the first run.

## 17. Test list of the certify code

Each test uses fake sources or fake backends, unless it says "hardware". No test opens port 53117.
Draft 3 changes T-CERT-01, 03, 06 to 10, 12 to 14, 16, 17, 19, 20, 22 to 26, 30, 31, 32, 34 and 37, and
adds T-CERT-41 to 67. The spec integration of 2026-11-20 changes T-CERT-01, 11, 13, 16, 17, 24, 38,
41, 44, 45, 47, 48, 52 and 65, and adds T-CERT-68 to 71. The report fields of 3.5 add T-CERT-77 to
T-CERT-90 (not built). The report shape of 3.6 adds T-CERT-91 to T-CERT-111 and changes the tests in the list
after the table (not built). Each
of these says where it runs: "3 OS" means with fakes on Windows, Linux and macOS, in the three CI
jobs.

One owner for each rule [cross-spec review section 6]: this test list owns the local record
(T-CERT-41, T-CERT-47) and the check names; the tests of [ux] (T-UNX-61, T-UNX-62) cite them. The
exposure search and "no source sets the camera's own auto" belong to [req] (T-REQ-15 and the T-REQ
search tests); T-CERT-45 cites them. The 100 ms rule of the product belongs to T-CAP-82; T-CERT-25
tests only the self-check.

| ID | What it does | Pass criterion |
|---|---|---|
| T-CERT-01 | 3 OS. `certify_plan("quick")` and `("full")` with a fake enumeration of 0, 1, 4 and 8 cameras and 4 virtual cameras, a fake evidence file with one `verified` model, and a fake `camera_checks.json` that holds one other model. | The fields of C 2.6; empty `downloads` and `system_changes`; `risks` empty for `quick` and the sentences of 8.4 for `full`; `total` equal to the count of checks that the run then reports (with no camera to check, the run also reports `detect`, 9.1); `seconds_estimate` = min(30, ⌈20 + N/4⌉ + 10) for quick (0 with no model to check) and by 16 for full; `evidence` and `checked` of each camera; `details.unchecked` holds neither the checked nor the reviewed model; the checked model counts in `total` (2.4); with each model reviewed, quick has `total` 0; no activate call; `comtypes` not imported in the caller. |
| T-CERT-02 | `certify("slow")`, `certify_plan("")`. | `ValueError` [C 2.2]. |
| T-CERT-03 | 3 OS. Quick with 4 fake cameras of 3 models. Validate the report. | Each required field of C 3.1; the schema id `skellycertify.report/1.6.0`; `kind` = level; each name matches C 3.4 and is unique; each check has one result, never `partial`; each `fail` and `not-run` has a reason of C 5.2; each `numbers` value has an allowed type; each summary item has a `group` of C 3.7, a `name` of 1 to 80 characters, a `device` of at most 40 characters or `null`, a `reason` only for `skipped`; the `module` of each camera check equals the `name` of its summary item [C 3.4]. |
| T-CERT-04 | Fakes with planted values: a host name and a user name in a camera name, a path, a MAC-like string, a serial, `take.mkv`, a long string. | C 6 rules 1 to 11 hold; the planted values are gone. |
| T-CERT-05 | Camera names: `Alex's iPhone Camera`, `Kamera’s Webcam`, a name with the host name, `HD Webcam (SN 12AB34CD56)`, `USB Video Device`. | `iPhone Camera`, `Webcam`, `Camera vvvv:pppp`, `HD Webcam`, `USB Video Device`. |
| T-CERT-06 | 3 OS. No camera attached. | `detect` `pass` with `cameras` 0; each check that needs a camera `not-run` `no-camera`; no `fail` in the report; the self-checks run; no `camera` summary item; `no-camera` in `evidence.reasons`; no row written to the record of checked models. |
| T-CERT-07 | 3 OS. Quick with 4 good fakes of 4 models. | Each check of the five groups (3.4) `pass`; 4 summary items `pass` in detection order; no row in `Checks that did not pass:`; the work folder is gone; each camera is `healthy` or `restored` with no cleanup row and no notice. |
| T-CERT-08 | 3 OS. The generic-camera pattern (T-CAP-17), bright frames. | `rate` `fail` `rate-low`; summary item `fail`. |
| T-CERT-09 | 3 OS. The same with dark frames (mean 10). | `rate` `not-run` `too-dark`; summary item `partial`. |
| T-CERT-10 | 3 OS. A fake in use at the open, beside two good fakes of other models. | `opens` `not-run` `camera-in-use`; its checks `not-run`; its summary item `skipped` with `reason` `busy`; the run is not refused (no `cameras-busy`); no retry (open count 1); no row of that model written to the record of checked models. |
| T-CERT-11 | A fake refused for bandwidth in the group that opens alone. | `<label>:opens` and `<label>:rate` `pass` (the retry decides them); `group:open` `fail` `usb-bandwidth`. |
| T-CERT-12 | 3 OS. A fake that hangs at the open. | `opens` `fail` `hung`; later checks `not-run` `prior-failure`; never opened again (phase G included); cleanup `release:<label>` `camera-wedged`; one notice `camera-wedged` with the cleaned name [C 3.8]; `<model>:gate:no-hang` `fail` in `full`; the others complete. |
| T-CERT-13 | 3 OS. Settings: a fake whose exposure reads back -5 for a set -7; one that reverts after 0.5 s; one whose image does not change; one with a mean of 240; one macOS fake with no manual exposure. | `settings-stick:readback` `fail` `readback-differs`; `:holds` `fail` `setting-reverted`; `:image-effect` `fail` `no-image-effect`; `:image-effect` `not-run` `too-bright`; `:readback` `not-run` `no-manual-exposure` with the warning `no_manual_exposure`, `:holds` and `:image-effect` `not-run` `no-manual-exposure`, no `fail`; each summary item `partial`. |
| T-CERT-14 | 3 OS. Native JPEG: a fake that gives YUY2 encoded by skellycam (after 3b); a fake with a cut JPEG; a fake with a SOF of another size; a fake with no DHT. | `native-jpeg:format` or `:not-reencoded` `fail` `no-native-jpeg`; `:valid` `fail` `jpeg-damaged`; `:size` `fail` `jpeg-size-differs`; each check of the last fake `pass` with `dht_inserted` > 0; each other check of each fake keeps its own result. |
| T-CERT-15 | The session child ends with `os._exit(5)`; sleeps past its limit with a grandchild; gives its result and does not end; gives bytes that are not a result. | the running check `not-run` `crashed` with `exit_code` 5 (a crash blames no check, 19.2 items 8 and 13) [U Q817]; `fail` `timed-out` and no process left; `<name>:exit` `record-only` `hung-at-exit`; `fail` `bad-output`. |
| T-CERT-16 | 3 OS. Cancel during the quick apply, during the quick take and during phase F of a full run with three fakes, one not yet opened. | The checks that ended keep their results; the running and later checks `not-run` `cancelled`; the child of the running check is killed with its process tree within 1 s of the cancel; no new check starts; phase G re-checks only the touched fakes, at most 5 s each, sets a changed control back, and gives only cleanup rows; the fake that was not opened gets no open; no process left; the work folder is gone; `cancelled` in `evidence.reasons`; the record of checked models gets rows only by the rule of 2.5. |
| T-CERT-17 | 3 OS. A progress spy that logs each message and each fake source call in one ordered list; checks that last 10 ms; a progress callable that raises. | `starting` first, `done` last; before each check, also each computed check and each roll-up check, a message whose `step` is `{"section": null, "name": <that check>}` comes before the first source call of that check; each item of `checks` has `section` `null`; at most 10 messages each second, and no step message dropped; each is JSON; after the raise, no more calls and the run completes [C 2.3]. |
| T-CERT-18 | `sys.stdout` and `sys.stderr` `None`, `sys.frozen` true, in a spawn child. | The report is complete; no read of stdin [C 2.5]. |
| T-CERT-19 | 3 OS. The selection rule with the mode lists of the C930e, the C922, the Kiyo Pro, a 4K camera, a 640x480-only camera, a YUY2-only camera, and two C922 fakes. | The exact checks for each, in the phase order of 2.3: identity, modes and rates (C) before the sweeps (D), the group and self-checks (E) before the risky checks (F); the 60 fps checks, the Auto search at 60 and the cycles in phase F; `<base>` `640x480@30` for the 640x480 camera; `no-mjpg-mode` for the YUY2 camera; the second C922 gets its quick claims and `not-run` `same-model` for the camera block (if question 4 is yes). |
| T-CERT-20 | 3 OS. A fake with no 1080p, no 60 and no focus control. | `rate:1920x1080@30` and `rate:1280x720@60` `not-run` `no-mode`; `control:focus` `not-run` `control-absent`; no `fail`; `controls.focus` of the row is absent. |
| T-CERT-21 | A fake with the rates of table cap 10.5. | `cliff` -5 for the Logitech table and -7 for the Kiyo Pro table; the sweep stops after two `too_slow` steps. |
| T-CERT-22 | 3 OS. A fake that declares 60 and delivers 30 at each exposure; one that delivers 60 only at -7. | First: the product falls back [req 2.4]; `rate:<w>x<h>@60` `fail` `rate-low` with `fell_back` true; the sweep and the Auto checks at 60 `not-run` `prior-check-failed`; the summary item stays at its base result. Second: `pass`. |
| T-CERT-23 | 3 OS. SkellyCam Auto in a dark scene: the search holds its result with `add_light`, and the check ends `too_slow`. | `auto-exposure:searched:<base>` `pass`; `auto-exposure:holds-rate:<base>` `not-run` `too-dark`. |
| T-CERT-24 | 3 OS. Quick with 4 fakes and with 1 fake on the virtual clock of the product (ADR-HP7D); then a 50 s delay planted in the apply; then two retries alone with 20 s used. | The quick part ends within 30 s plus phase G; with 4 fakes the checks of 4.2 to 4.5 complete, in the order of 4.1, and `self:hang-100ms` is `not-run` `over-budget` when less than 10 s remain; with the delay, the apply is stopped at 30 s, its child killed with its tree, and its checks and each later check are `not-run` `over-budget` [C 5.3], never `fail`; with 20 s used, the retries are `not-run` `over-budget` and the take runs. The wall-clock form has the marker `certify_timing` and runs only on a local system. |
| T-CERT-25 | 3 OS. Each self-check with fakes, and each with a planted fault of one of its checks (a 150 ms gap; a hung process that does not end; a take that does not finish; unequal rows; a camera process that does not end in 15 s; a source not closed; a healthy camera marked `dead`; a torn read that passes; a lapped read that passes). The spin case of `self:idle-cpu` has the marker `certify_timing`. | Each check `pass`; with a planted fault only the check of that fault `fail`. |
| T-CERT-26 | 3 OS. Two fakes of one model. | Labels `.0` and `.1`; one summary item for the model [C 3.7]; `<model>:units` with `units` 2; a cleanup row of `.1` has the `module` of that item. |
| T-CERT-27 | Versions `2.0.0a6` and `2.0.0-a6`; `tree_modified` true; the option `cameras` with one of four labels. | `no-version` only for the first; `modified-tree`; no `partial-run` for the part. |
| T-CERT-28 | Cleanup after a pass, a crash, a time-out and a cancel; a locked file in the work folder; an old work folder with and without the marker; a file of the person in `recording_folder`. | The work folder is gone, or `not-deleted`; the marked old folder is gone; the rest stays. |
| T-CERT-29 | Search the report, and the files that the run wrote outside the work folder. | No media file, no string that ends with a media extension, no frame bytes, no path. |
| T-CERT-30 | 3 OS. Each reason code, each notice code and each `limits` code that the code can emit, against `skellycam/REASON_CODES.md`. | Each is in the file with one sentence; each notice code also has its text for the person [C 5.4]. |
| T-CERT-31 | 3 OS. Each check name that the code can emit, with the longest backend, `nousb-nousb`, index 9, rate 29.97, the longest group and condition, and the longest probe and control; also the names of section 20 (`<label>:in-use:other-program`, `<label>:in-use-mid-take`, `probe:<model>:hog-mode`, `<label>:control-read:gaps`). | Each matches the pattern; the longest has 75 characters. |
| T-CERT-32 | 3 OS. Patch the rate limit of `rate_check.py` and the stall limit of the take; spy on `CameraGroupManager`, `start_take` and the source factory; set `SKELLYCAM_WINDOWS_CAPTURE`, `SKELLYCAM_LINUX_CAPTURE` and `SKELLYCAM_MACOS_CAPTURE` to `opencv`. | The result follows the patched product limits; each open goes through the calls of 2.2; the native source is used; the OpenCV source is never created. |
| T-CERT-33 | Quick and full with fakes; list the sockets of the process tree. | No listening socket. |
| T-CERT-34 | 3 OS. Phase G with fake sources that keep the "before" values and restore them at each close: a fake whose controls were manual -6 and auto focus before the run; a fake whose restore at the close reports `restore_ok` false; a fake whose second open reports other "before" values than the first; a fake that fails the plain open of `full`; each case at `quick` and at `full`. | Quick: `healthy`, `camera-not-restored`, `camera-not-restored`, and no extra open in phase G. Full: `healthy`; `camera-not-restored`, or `restored` when the plain open sets the value back with a good read-back; `restored`; `camera-wedged`. |
| T-CERT-35 | The disk benchmark with a fake file object at 50 MB/s, one that stalls 2 s, and a folder with too little space. | `write_mb_per_s` 50 ±5 %, `cameras_1080p30_typical` 8, `worst` 2; `fsync_ms_max` ≥ 2000; `not-run` `disk-full`; the file is gone. |
| T-CERT-36 | The evidence file: rows with a missing field, a wrong state, an unknown limit code; the proposal tool with reviewed fake reports (3 from 2 systems; 3 from 1 system; 1 maintainer). | The checker refuses the bad rows; the tool proposes `verified` for the first and third, not for the second. |
| T-CERT-37 | 3 OS: the native sources with the fake layers of [ux 6.2] (`FakeV4L2System`, `FakeAVLayer`) that break one assumption each (decoded buffers only; a clock that is not the arrival clock; samples after arrival; no sequence; a wrong exposure unit; auto that comes back; a config value that does not read back at a later open; a granted size that differs; an id that changes; `EBUSY` at `S_FMT`; `ENOSPC` at `STREAMON`; no permission; a segfault in the camera process; a call that never returns). | Each breaks only its own checks, with the reason and the numbers of 10.2; the other checks of that camera still run; the crash gives `crashed` with `exit_code` (product code `process-ended`); the hang gives `hung` with the `call`; no permission gives `not-run` `no-permission`; the run ends in its limits. |
| T-CERT-38 | Hardware, Windows: quick on the four test cameras (C922, C930e, Kiyo Pro, generic). | Three summary items `pass` (or `partial` with the reason), the generic `fail` with `<label>:rate` `fail` `rate-low`, each `group:take` check `pass`; the quick part within 30 s; each camera `healthy` or `restored`. |
| T-CERT-39 | Hardware, Windows: full on the four test cameras. | The facts agree with the measurements of sections 5 and 8 (the Kiyo Pro 60 mode `fail` `rate-low`, the C922 60 mode `pass` with `ok_at_m7`); the risky checks run last; each camera ends `healthy`, `restored` or with `camera-wedged`. |
| T-CERT-40 | Hardware, Linux and macOS: full on the test cameras through the native sources. | Each check of 10.2 has a result and its numbers; the report agrees with the `--plan` runs of the research suites on the same system. |
| T-CERT-41 | 3 OS. `camera_checks.json`: quick runs with fakes whose items end `pass`, `partial` (too dark), `fail`, `skipped` (busy) and `partial` with no unit that judged `opens` (cancelled; no access); two fakes of one model; a fake with no USB ids; then a change of the OS key; then a new skellycam version; a file that does not parse; a row with a missing field. | One row for each model by the rule of 2.5 (`pass`, `fail`, and `partial` with a judged `opens`), with the fields of 2.5 and `controls` keyed by `control_path`; `device` `nousb:<cleaned name>`; after the OS key change, each model in `details.unchecked`; after the new version, no model in it; the bad file and the bad row count as no row, certify writes a new file and does not raise; no row holds a serial, a path or a `camera_id`; the file is not in the work folder and stays after the cleanup. |
| T-CERT-42 | 3 OS. The pop-up flow: a fake enumeration with three cameras, two of one model; the record holds the third model; `certify_plan("quick")`, then `certify("quick", cameras=details.unchecked labels)`. | `details.unchecked` has one item (the first camera of the unchecked model); the run checks only that camera; no `partial-run` in `evidence.reasons`; after the run, `certify_plan("quick")` gives an empty `details.unchecked`. |
| T-CERT-43 | 3 OS. Cameras busy: an open camera group in the app state of skellycam in the calling process; then a fake camera that a second process holds. | First case: each check `not-run` `cameras-busy`, `cameras-busy` in `evidence.reasons`, no source created. Second case: only that camera is busy (its checks `not-run` `camera-in-use`); the run continues and is not refused. |
| T-CERT-44 | 3 OS. The summary item rule of 3.4, as a table test over the results and reasons of the checks of the five groups for one and two units of a model; a model with no sequence number; a failed check of the full camera block; a failed probe; a `full` and a `quick` report. | Each case gives the item of the first of the four rules that applies (`skipped`, `fail`, `pass`, `partial`); no item is `record-only`; `time-gaps` takes the place of `sequence` for the model with no sequence number; a failed full block check or probe never changes the item; no check holds the item; the `full` items have `gate` `<model>:gate`, and the `quick` items have no `gate` field. |
| T-CERT-45 | 3 OS. SkellyCam Auto with a fake status that has `exposure_search` and `count` [req 1.5]: a fake that searches at the open and after the change to 60; one whose `count` does not rise after the change; one that does not search at the open; one whose search ends `failed`; one that stays `adjusting` for 30 s; one that reopens at the rate change inside the same camera process; one whose camera process is replaced by "apply again"; `search_exposure()` called in process. | `pass`; `fail` `auto-not-searched` for the two; `fail` `auto-search-failed`; `fail` `timed-out` 25 s after the apply response; the reopened camera and the replaced process `pass` (each `count` rose by one); certify reads `exposure`, `exposure_found_at_fps` and `exposure_search`, and never calls HTTP or the pause route. The rule that no source sets the camera's own auto is tested by its owner (T-REQ-15); this test cites it. |
| T-CERT-46 | 3 OS. The diagnostics reader: the fake Media Foundation, V4L2 and AVFoundation sources give `diagnostics()` with the keys of [ux 4.6.2], one with a missing key and one with a value outside the vocabulary; `frame_log` with 64 rows. | Each number of 10.2 that has a diagnostics key comes from that key; a missing key gives `null`, never a crash; a value outside the vocabulary is not copied: the number is `null`; `frame_log` is never copied into `numbers`. |
| T-CERT-47 | 3 OS. The local pass: `full` runs with fakes where each gate check passes; where `native-jpeg:valid` fails; where `settings-stick:readback` fails only; where `settings-stick:image-effect` is `not-run` `too-dark` only; where a `cycles` check hangs; a `quick` run where each check passes. | The `full` row of the first run has each `gate` value `pass` and is a local pass for the model, OS key, backend and ABI; the second and fifth rows have a `gate` value `fail` and are no local pass; the third row is a local pass with `controls.exposure` `{"v4l2": "no"}`; the fourth is a local pass with `{"v4l2": "unproven"}`; the quick row is no local pass. |
| T-CERT-48 | 3 OS. Native JPEG hash compare: a fake source whose frames have no DHT, so the shared loop inserts one; a fake whose ring slot differs in one byte from the hashed bytes of the same `source_frame_number`; hashes after the first `ready`, then a live change to -8, then a record start. | The first passes with `dht_inserted` > 0 and `hash_equal_source_ring` true; the second fails with `jpeg-damaged`; `source-equals-ring` uses the set of the first `ready`, read before the live change; the live change does not re-arm the set; the set of the record start is compared with the MKV blocks; each hash is compared with the slot of its own frame number. |
| T-CERT-49 | 3 OS. `certify("quick", test_media_dir=<a temporary folder>)` and `certify_plan("full", test_media_dir=...)`. | Both accept the option; the run writes and deletes nothing in that folder; its path is in no report and no progress message. |
| T-CERT-50 | 3 OS. Interrupted run: a progress spy; the session child is killed during `group:take`. | Each item of `checks` of each message carries `reason`, `module` and `numbers` after its check ended; a module report built from the last message by C 2.5 has `group:take` `fail` `crashed`, the checks that did not end `not-run` `interrupted`, and `interrupted` in `evidence.reasons`; it validates as T-CERT-03. |
| T-CERT-51 | 3 OS. Report file layout with the freemocap writer fake: a run with a `partial` model that has a `not-run` check, a `skipped` (busy) model, a failed camera check and a wedged camera. | The camera table shows `partial` and `skipped (busy)`; `Checks that did not pass:` lists the `fail` check and the `not-run` check of the `partial` model with its camera name in `Module`, and no `not-run` check of a `pass` item [C 4.2 part 7]; `notices` holds `camera-wedged`; the disk figure is in `numbers` of `system:disk-benchmark`, not in a `benchmark` item (11.6). |
| T-CERT-52 | 3 OS. macOS probe sequence with `FakeAVLayer`, a fake CoreMediaIO and a fake IOKit layer: two C922 units, one Kiyo Pro, one C930e; each approach available. | The probes run for one unit of each model only; the steps in the order of 10.7, with steps 1 to 6 in phases C and D and steps 7 to 9 last in phase F; the Kiyo Pro last in each step; one camera at a time; the product session of a camera is closed while its probe runs; A4 runs only after A1 or A3 gave a manual path; A7 and A8 only when A5 and A6 failed, and A8 also when A7 worked; each probe check has the `module` `macOS probes`; no call of `USBDeviceOpenSeize`, `USBInterfaceOpen` or `.deviceCapture`. |
| T-CERT-53 | 3 OS. The proof rule for a control with the fake layers: a read-back equal to the set value with no luma change; the luma rising with the value (ratio 1.5) on an `ev` route; the luma falling as the value rises; a frame rate that falls to 15 fps at 62.5 ms on a time-unit route; a luma of 5; a frame gap of 3 times the baseline during an endpoint-0 write. | `fail` (`appears`, `no-image-effect`); `pass`; `fail` `no-image-effect`; `pass`; `not-run` `too-dark`; `fail` `frame-gap`. Each check is `probe:<model>:<approach>:<control>`. |
| T-CERT-54 | 3 OS. The proof rule for a JPEG: block buffers whose DQT equals the reference of the model (VID:PID); whose DQT equals the B4 reference at quality 0.9; a model with no reference; no DHT for a model whose reference has none; a DHT with a matching DQT; only decoded image buffers. | `pass`; `fail` `not-camera-jpeg`; `not-run` `no-reference`; `pass`; `pass` with `dht_added_by_os` true; `fail` `not-camera-jpeg`. `b3-nil` and `b4-apple-jpeg` are `record-only`. |
| T-CERT-55 | 3 OS. Drop rules: no evidence row; a maintainer-accepted row with `b1-empty` `pass`, `a1-cmio-native:exposure` `pass` on two models and `a2-cmio-absolute:exposure` `pass` on one; a local `full` row with the same results; a row of another OS key. | Each probe runs; B2 except `b2-dmb1`, B4, B5, B6 do not run; for exposure both A1 and A2 stay (each works on a model), and A5 to A8 for exposure do not run for the models with a proven route; each probe runs with the local row; each probe runs with the other OS key. |
| T-CERT-56 | 3 OS. Wedge and restore: the fake Kiyo Pro gives no frame for 2 s during A5; a fake C922 whose exposure is changed by A1 and by A6; the B5 movie file. | The Kiyo Pro is marked dead: no later probe, no later check (`prior-failure`), no open in phase G, cleanup `camera-wedged`; the C922 values go back through CoreMediaIO after A1 and through endpoint 0 after A6, and phase G reads the "before" values; the `.mov` is gone after B5 and no file name of it is in the report. |
| T-CERT-57 | 3 OS. The plan and the estimate on a fake macOS with one, two and four models. | `seconds_estimate` follows 10.7 and 16 (about 10, 16 and 27 min); no probe row on Windows and Linux. |
| T-CERT-58 | 3 OS. The 60 fps fall back [req 2.4] on a group of two fakes: one holds 60 at -7, one does not. | The product answers with configs at 30 and `rate_fallback`; the failing camera's `rate:<w>x<h>@60` `fail` `rate-low` with `fell_back` true; `group:take-60` checks `not-run` `prior-check-failed` or `one-camera`; no `camera_failures` entry. |
| T-CERT-59 | 3 OS. Each time limit of 9.3 beyond quick with a planted sleep: a camera block, a group take, a self-check, `system:disk`, the benchmark, phase G, and each kind of probe child. | Each gives `fail` `timed-out` at its limit; no process is left; the next check starts. |
| T-CERT-60 | Linux. A fake camera process that stays in an uninterruptible wait (a stand-in that ignores the kill). | `hung` with `numbers.unkillable` true; the camera state `replug`; the report returns within the limit. |
| T-CERT-61 | Windows (fakes). `system:camera-apps` with a fake process list that holds two names of the allow-list and one other name. | Two booleans true, the others false; no process name outside the list is in the report. |
| T-CERT-62 | 3 OS. `system:kernel` with fake diagnostics of the kernels 6.10, 6.12.81, 6.14 and 7.0. | The quirk numbers of 6.2 for each; on Windows and macOS no `system:kernel` row. |
| T-CERT-63 | 3 OS. `probe:camera-holders` with a fake `/proc` where `pipewire` holds one node and another process holds a second. | `pipewire` and `other` true; certify does not open the held cameras; their checks `not-run` `camera-in-use`. |
| T-CERT-64 | 3 OS. `self:scale-3` and `self:scale-12` (Q624f) with fakes on the virtual clock. | `record-only` with the CPU numbers; no pass rule. |
| T-CERT-65 | 3 OS. The check catalog of the certify code: each check that the code can emit, with its pass rule. | Each check has one pass rule or none (`record-only`); no check name is reused for two tests; each roll-up check `<model>:gate:<step>` and `<model>:gate` requires exactly the checks of 11.3, is `pass` only when each of them is `pass`, else `fail` `gate-check-failed` or `not-run` `gate-check-not-run`; `<model>:gate:no-hang` is an ordinary check with its own pass rule. |
| T-CERT-66 | 3 OS. A model with a `verified` row for this OS key, backend and ABI, beside an unchecked model. | Quick runs no check of the verified model; its summary item is `skipped` with `reviewed` [C 2.7]; it counts as checked; with only the verified model, quick has `total` 0 and runs nothing, also no `self:hang-100ms`. |
| T-CERT-67 | 3 OS. `notices` [C 3.8]: two wedged cameras and one camera not restored. | Three notices with the codes and `values.camera` the cleaned names; at most 8 keys each; no free text; each code is in `skellycam/REASON_CODES.md` with its text. |
| T-CERT-68 | 3 OS. The gate on a fake source with no sequence number (`sequence_available` false): a run with no long interval; a run with one interval of 3 periods; a fake with sequence numbers and a gap with no sequence gap. | First: `<label>:sequence` `not-run` `no-sequence`, `<label>:time-gaps` `pass`, `<model>:gate:sequence` and `<model>:gate` `pass`; second: `time-gaps` `fail` `frame-gaps`, the gate `fail` `gate-check-failed`; third: `sequence` `fail` `sequence-unreliable`, the gate does not pass. |
| T-CERT-69 | 3 OS. Certify and the record: a fake model with a local `full` row whose exposure is `{"v4l2": "no"}` and a shipped row that says the same; a full run. | Certify tries exposure again: the settings checks run and judge; no check is `not-run` because of the row; the new row holds the new results. |
| T-CERT-70 | 3 OS. Report privacy for the Markdown part: camera names `Cam <x>`, `See https://x`, `www.cam.example`, `Cam 192.0.2.7` (a documentation address); a `host` with unknown fields. | The cleaned names hold no `<`, `>`, `](`, `]:`, `://`, `www.` or IPv4 address; the unknown `host` fields are left out or `null`; no object has a key two times [C 6 rules 17, 19, 20, C 3.3]. |
| T-CERT-71 | 3 OS. A `full` run with a fake model whose `settings-stick:image-effect` fails and whose gate passes; the proposal tool of 11.5 with that report from a maintainer. | The summary item is `partial` with `gate` `<model>:gate`; the tool proposes `verified` with `not_passed` holding `settings-stick:image-effect`, `fail`, `no-image-effect`; a `skipped` item gives no row [C 7.2]. |
| T-CERT-72 | 3 OS. Two models with one cleaned name, one `fail` and one `pass`. | Each model gets the row of its own summary item (2.5). |
| T-CERT-73 | 3 OS. A fake that hangs at the live change (8.3), in a full run. | The running check `fail` `hung`; the later checks of that camera `not-run` `prior-failure`; `<model>:gate:no-hang` `fail`; `release:<label>` `camera-wedged` and its notice; no second open. |
| T-CERT-74 | 3 OS, session child. A cancel, and the end of the budget, while a camera is in the middle of its open. | `cancelled` or `over-budget`; the camera is never opened again; `camera-not-restored` with its notice; the call returns within the bound of 9.3; no process is left. |
| T-CERT-75 | 3 OS, session child. The caller dies during a run; a time-out of a full run. | The session child closes its cameras (each source is closed) and ends with its camera processes; at the time-out each camera process closes its source before the rest of the tree is killed; no record row after a time-out. |
| T-CERT-76 | 3 OS. A second run while the lock of 9.5 is held; a record file that cannot be written; `abandon` with `cancel` [C 1.6.0 2.4]. | `cameras-busy` and no work folder; the cleanup row `write-record` and a returned report; after `abandon`, `cancelled` rows and no record row. |
| T-CERT-77 | 3 OS. The build file of 3.5.2: a valid file (40 hex, `false`); no file; a commit of 39 hex digits; a `tree_modified` that is a string. | The first gives the commit, `false`, and no `no-commit` or `modified-tree`; each other case gives `null`, `null` and both reasons; no run reads git. |
| T-CERT-78 | 3 OS, session child. The failure facts of 3.5.3 with fake sources: an `IN_USE` HRESULT at the open; `E_ACCESSDENIED` at `ActivateObject`; a first-frame time-out, then a hang in the reader release; a hang in a live control change; a camera process that ends with 0xC0000005; a rate of 25.7 fps in a 30 fps mode. | Each failure row has each key of 3.5.3 with the values of the fake (for the third: `stage` `first-frame`, `call` `reader-release`, `first_fail_code` `first-frame-timeout`, `exit_code` 1, so the dict reached the main process before the hard end; for the fourth: `call` `set-controls`; for the fifth: `crashed` with `exit_code` 3221225477); a pass row and a filled row have none of the keys; each `opens` row has `stage`. |
| T-CERT-79 | 3 OS, virtual clock. The times of 3.5.4: a quick run of three fakes and a full run; a cancel. | Each row from a step in `checks` and `cleanup` has `t_start_s` and `seconds` (0 or more, 2 decimals); `t_start_s` does not fall in the order of the progress messages; the checks of one message share `t_start_s`; a filled row has neither key; `group:take` rows have `take_seconds` and their `seconds` is the check time. |
| T-CERT-80 | 3 OS. The inventory of 3.5.5 with a fake detection and a fake `usb_facts`: two units on one controller, one on a second controller, one behind a hub, one non-PCI controller; a `usb_facts` that sleeps 10 s; a camera with 17 modes. | `details.cameras` has one item for each unit in the detection order, with each key, its type and its vocabulary; `controller` 0, 0, 1 in the order of first use; `hub_depth` 1 behind the hub; `controller_id` `null` for the non-PCI controller; the slow lookup gives `unknown` and `null` after 2 s and the run goes on; each mode matches the pattern; at most 64 modes. |
| T-CERT-81 (removed by Q595: no unit id) | 3 OS. The unit id of 3.5.10: a fixed key file and a fixed identity string (a test vector); two runs with one key; a deleted key; a key of 63 hex digits; a key file that cannot be written; two fake systems with two keys and one identity string. | The id equals the test vector; two runs give equal ids and `unit_ids_new` `false`; a deleted or bad key gives a new key file, other ids and `unit_ids_new` `true`; a file that cannot be written gives `null` ids and a complete run; the two systems give two ids; the key is in no report, no progress message and no record row; no id equals a `camera_id` of the run. |
| T-CERT-82 | 3 OS. The timing of 3.5.6: fake sidecar rows with a 7 s gap at a known time, arrivals on a 32 and 48 ms grid, a `missing` row; fake rate window keys; a rate check that fails with no ring frame; fake D-3 counters before and after the take; a `frame_log` of 64 rows. | `take_fps`, `interval_p95_ms`, `interval_max_ms`, `interval_max_at_s` (from `t0`), `grid_16ms_share` and the window changes of the D-3 counters have the expected values; the rate row has the window keys and `luma_mean` from `rate_luma_mean`; `grain_ms` 16 and `jitter_p95_ms` as computed; `time-gaps` and `sequence` judge the changes. |
| T-CERT-83 | 3 OS. The take facts of 3.5.7: manifests with each warning code twice; each `take_error` detail form of `take.py`; a `camera_dead` with `last_frame=none` and with a number; a manifest that cannot be read. | `take_warnings` is sorted, each code one time; `take_error_kind` and `take_error_camera` as the table; `first_gap_row`, `first_gap_from`, `first_gap_to` from the `camera_gap` detail; `dead_last_frame` only on the `rows-complete` row of the dead camera; `null` values with no manifest; no detail text is in the report. |
| T-CERT-84 | 3 OS. The CPU of 3.5.8 with a fake `psutil`: a known CPU time of the tree, known system samples, a process that starts in the window; a `psutil` that raises. | `cpu_cores_used` and `cpu_share_p95` on each `opens` row and each `group:take` row have the expected values; the late process counts from its start; the raise gives `null` and a complete run; `details.cpu_logical` is the fake count. |
| T-CERT-85 | 3 OS. The exposure and gain context of 3.5.9: fake diagnostics with "before" values, a range, an auto gain that rises from -7 to -8; a KS route with no range; a camera with no gain; a rate failure. | The keys of 3.5.9 have the values of the fake on the `settings-stick` rows and on the `rate` row; the KS route gives a `null` range; no gain gives `null` gain keys; the failed `rate` row has `exposure_before` and `exposure_before_auto`. |
| T-CERT-86 | 3 OS. The logs of 3.5.11: a caller that set `SKELLYLOGS_LOG_DIR`; a second run; a run that the lock refuses; a cancel and a crash; a file of 3 MiB; 70 files. | Each log file of the session child and of its camera processes is in `certify_logs/` of the base folder; the caller's folder gets none; the second run deletes the files of the first at its start; the refused run deletes nothing; a cancel and a crash keep the files; the big file keeps its last 1 MiB; 64 files stay; `details.logs_kept` is the count; no log line, file name or path is in the report; the work folder is gone. |
| T-CERT-87 | The validator `report_rules.py` gets one rule for each key of 3.5: its place, its type, its vocabulary or pattern, and its presence (the failure set exactly on the failure rows; `t_start_s` and `seconds` exactly on the rows from a step; one item of `details.cameras` for each unit). Reports with one planted fault each. | A report of T-CERT-07 and of T-CERT-78 has no problem; each planted fault gives exactly one problem. |
| T-CERT-88 | 3 OS. Privacy of 3.5: fakes with planted symbolic links (`\\?\usb#vid_...`), instance ids (`USB\VID_...`, `PCI\VEN_...&DEV_...`), location paths (`PCIROOT(0)#PCI(1400)#USBROOT(0)`), `/dev/video0`, a serial, the `camera_id` of each unit, and a failure text that holds a link. | None of the planted values, and no key `camera_id`, is in the report, the progress messages or the record; the validator gets patterns for `\\?\`, `usb#`, `USB\VID_`, `PCI\VEN_`, `PCIROOT(` and `/dev/video`, and a rule that no value equals a `camera_id` of the run. |
| T-CERT-89 | 3 OS. Size of 3.5.12: a full run of four fake cameras with each field at its longest form (64 modes of 80 characters, each failure key, each warning, each camera failed); a quick run of four fakes in the same form. | `json.dumps(report, indent=1)` has at most 131,072 bytes for the full run and at most 49,152 bytes for the quick run. |
| T-CERT-90 | Hardware, Windows: quick on the four test cameras, then a second quick run. | Each field of 3.5 that is built has a value of its vocabulary; `controller_id` and `usb_link` agree with the device manager; the two runs give the same `unit_id` for each camera that did not move; the report passes T-CERT-87 and T-CERT-88. |
| T-CERT-91 | 3 OS. Quick and full plans and runs with 4 fakes of 3 models, two of one model. | No row has the reason `not-built` for a check with no code, and no row has `same-model`; `details.not_built.camera` and `.run` hold each such name one time, sorted, with `base` for the mode of `<base>`; the plan `total` and `details.checks` count no such check; a check with code whose diagnostics key is `null` keeps `not-run` `not-built` and counts in `total` (3.6.1). |
| T-CERT-92 | 3 OS. Fakes that stop at each step: no MJPG mode; in use; a hang at the open; a rate failure; a cancel during the take; the end of the budget before the take. | Each such camera has one `<label>:not-reached` row with `not-run`, the reason of the first check that it stands for, `module` = the name of its summary item and `numbers.checks` equal to the count of the checks it stands for; each check that a progress message named keeps its own row; the last progress message has `done` equal to `total`, and no message has `done` above `total` (3.6.1). |
| T-CERT-93 | 3 OS, session child. B1: a fake that stalls after `ready` and before the settings change; one whose camera process ends there with `os._exit(3)`; one with a stream error in the take; one removed in the take [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md). | Each gets one `fail` row on the first check that has no result (`settings-stick:readback` `fail` `stalled`; `crashed` with `exit_code` 3; `stream-error`; `device-removed`), with the failure facts that have a value and `module` = its model; its other checks are one `not-reached` row; `<model>:gate:no-hang` is `fail` for the stall and the crash, `pass` for the removal; `details.cameras[].failed` names the row (3.6.1). |
| T-CERT-94 | 3 OS. Camera names of 9.4 with made-up firmware texts: `Caméra HD Pro`; `Kamera von Jürgen`; `Bob's Webcam`; `HD Webcam SN12AB34CD56`; `Logitech® C920`; `Primacam`; CJK `网络摄像头 HD`; Cyrillic `Веб-камера Logi`; Arabic, right to left, `كاميرا ويب`; Devanagari `वेबकैम`; decomposed `Came\u0301ra`; a name with U+202E inside; a name with U+200B (Cf, not a direction mark); a mixed-script spoof `Logitеch` (Cyrillic `е`); `Cam <x>`; `See https://x`; `www.cam.example`; `Cam 192.0.2.7`; `Cam 00-1A-2B-3C-4D-5E`; `Webcam.jpg`; a string of 70 letters with a mark at code point 60; the user name `李明` inside the text; a one-letter user name `a` with the text `HD Camera A1` and with `Camera a`; the host name inside a word; the Apple texts `Annas-iPhone`, `iPhone15`, a fullwidth `ｉＰｈｏｎｅ`, `iPad von Jürgen`, `FaceTime HD Camera`, `iMac Kamera`, `Continuity Camera`; a camera with no USB id and the text `李明的 iPhone`; the ids `046d:085c` and `4c4a:4a55` with the text `USB Camera`; a camera whose firmware text cannot be read. | `Caméra HD Pro`, `Kamera von Jürgen`, `Webcam`, `HD Webcam`, `Logitech C920`, `Primacam`, `网络摄像头 HD`, `Веб-камера Logi`, the Arabic and the Devanagari texts unchanged (each mark kept), `Caméra` (NFKC composes it); the U+202E name without U+202E; `Camera vvvv:pppp` for U+200B, the spoof, `Cam <x>`, the URL, `www.`, the IPv4 and MAC forms, the media extension, `李明` and the host name; the 70-letter string cut before the base of the mark; `HD Camera A1` kept and `Camera a` refused for the user name `a`; the Apple texts give their fixed classes; no USB id gives `Camera (no USB id)`; `046d:085c` gives `Logitech C922`; `4c4a:4a55` gives `USB Camera` with `name_usb`; the unreadable text gives `Camera vvvv:pppp`; no report holds a display name of the OS. |
| T-CERT-95 | 3 OS. `details.cameras[]` with fakes: a pass; a rate failure; a `too-dark` image check (full); a busy unit; two units of one model with different results. | Each unit has `result`, `failed` and `reason` by the rules of 3.6.3 (`pass`/`null`/`null`; `fail`/`rate`/`rate-low`; `partial`/`settings-stick:image-effect`/`too-dark`; `skipped`/`opens`/`camera-in-use`); `reason` is a reason code or `null`; the summary item of the model with two units follows 3.4. |
| T-CERT-96 | 3 OS. One number, one row: a quick and a full report of 4 fakes. | No two rows hold an equal `numbers` object; each key stands only on the row that 3.6.2 names; a `pass` row of `modes:granted` and of `detect:mjpg-mode` has no `numbers`; no row has `t_start_s`, `seconds` (except `detect` with no key), `failed_calls`, `window_frames`, `grid_16ms_share`, `grain_ms`, `exposure` on a rate row, `has_serial`, `unit_id`; `details.limits` holds each limit of 3.6.3; `measured_fps`, `take_fps` and `rate` have at most 2 decimals; no `clock:base` row on Media Foundation; one row of the pair `sequence` and `time-gaps`. |
| T-CERT-97 | 3 OS. A fake with 40 modes, one mode string of 50 characters. | `modes` has 32 strings of the largest area, each at most 48 characters; `modes_cut` is 8 (the long string and the 7 modes of the smallest area) (3.6.5); a camera with 32 modes or fewer has no `modes_cut`. |
| T-CERT-98 | 3 OS. Full with 4 good fakes of 4 models; with one model whose rate fails; with the sign-off checks faked as built and passing. | Today: each item `partial` (never `pass`), each `<model>:gate` and `pipeline:gate` `not-run` `not-built`, `details.gates` names `cycles` and `group:take-30:finished` with `not-built`; each record row has `"sign-off": "not-built"` and is no local pass; the plan has `risks` empty and `seconds_estimate` near 30; the failed model has `<model>:gate` `fail` and `details.gates` names its `rate`. With the checks faked as built: items `pass` and gates `pass` (3.6.4). |
| T-CERT-99 | 3 OS. The take with fakes: a CSV that does not read; a CSV with one row less; a `missing` row; a dead camera; a take of 2 s; a rate 1.5 % off in a take of 3 s and in a take of 30 s. | `rows-complete` `fail` `rows-differ` (two cases), `missing-rows` (two cases); `group:take:rate` `fail` `too-few-frames`; the 1.5 % case `pass` for 3 s and `fail` `group-rate-off` for 30 s; the report has no row `group:take:csv-rows`, `:no-missing` or `:frame-count` (3.6.2). |
| T-CERT-100 | 3 OS. The file `known_cameras.json`: the shipped file; a file with a key `46d:85c`, a name of 61 characters, a name with `<`, an entry with `usb3_capable` `"yes"`. | The shipped file has the three entries of 9.4 with their `usb3_capable` (Kiyo Pro `true`, C922 and C930e `false`) and no `4c4a:4a55`; the checker refuses each bad entry. |
| T-CERT-101 | 3 OS. `clock:near-arrival` with fake `frame_log` rows: each sample 0 to 16.5 ms before its arrival; one with p5 at -60 ms. | The first `pass`, the second `fail` `sample-too-early`; the limit is read from `details.limits`; with `clock:base` `not-run` `clock-unknown` the gate needs only `before-arrival` and `near-arrival` (Q585). |
| T-CERT-102 | 3 OS. Counters in the take window: fake D-3 counters with `discontinuity_flags` 1 and `frames` 300 before the take, and 1 and 390 after. | The take rows hold `discontinuity_flags` 0 and `frames` 90 (3.6.6 item 4). |
| T-CERT-103 | 3 OS. The plan total with a clean exit and with a hang at exit. | The plan counts `session:exit`; with a clean exit no `session:exit` row and the last `done` equals `total`; with a hang, the row `record-only` `hung-at-exit` and `done` equals `total`. |
| T-CERT-104 | Windows, fake detection. Four fake cameras, one marked as dead; `certify_plan("quick")`, then `certify("quick", cameras=<the three other labels>)`. | The run lists the cameras with no activation; it reads the modes and activates only the three; the dead one gets no activate call, no row and no item; the labels of the plan and of the run agree (3.6.6 item 9). |
| T-CERT-105 | 3 OS. The two verdicts, rule (a) and (b): 4 fakes of 4 models; one fails `rate`; then one fails `ring-equals-mkv` while the others pass. | First: the model `fail`, the pipeline `pass`, the `rate` row `module` = the model. Second: the row `module` = that model, the model `partial`, the pipeline `pass` (quick) or `partial` (full today); each passing pipeline row has `module` = the pipeline name (3.6.10). |
| T-CERT-106 | 3 OS. Rule (c): 3 fakes of 3 models whose `records:blocks-decode` all fail. | Each row `module` = the pipeline name; the pipeline item `fail`; `details.pipeline.failed` names the first such row; the model items keep the results of their own checks. |
| T-CERT-107 | 3 OS. Rule (d): a `group:take:finished` that fails with `disk-stall` and no camera; `session:exit` `hung-at-exit`; a self-check that fails. | Each has `module` = the pipeline name and makes the pipeline item `fail` (the `record-only` exit row makes no `fail`); no model item changes. |
| T-CERT-108 | 3 OS. Rule (e): one model with two units; its `rows-complete` fails on one unit. | The row `module` = the model; the model `fail`; the pipeline `partial` with `details.pipeline.reason` `not-decided-one-model`; `pipeline:gate` not `pass`. |
| T-CERT-109 | 3 OS. The take with one stalled camera of four models: the take error names the camera; then no take error and one failed `rows-complete`; then two cameras fail. | The first two: the failed take row has `module` = the model of that camera, and the pipeline item does not fail; the third: the take row has `module` = the pipeline name; the summary has the pipeline item first, `group` `component`, `device` `null`, the name `<OS>, <backend>, native JPEG`; the record has a row with `device` `pipeline`. |
| T-CERT-110 | 3 OS. `system:recording-space` with fake volume facts: fixed with 412 GB; removable; network; 2 minutes free; a path, a share name and a volume label planted in the fake. | `volume_kind` and `minutes_free` as computed from `jpeg_kb_mean` and `measured_fps`; `pass`, `pass` with the notice `recording-volume-not-fixed`, the same, `fail` `disk-full`; none of the planted strings is in the report (3.6.11). |
| T-CERT-111 | 3 OS. `group:in-step` with fake sample times and arrival times. | `record-only`, never `fail`; `spread_source` `sample` when `sample_time_kept` is true, else `arrival`; `details.limits.in_step_ms` is one frame period; no gate requires it (3.6.11). |
| T-CERT-112 | 3 OS. `records:mkv-opens` with fake takes: a good MKV; an MKV with a broken index whose blocks still read at their sidecar offsets; an MKV with one frame less than the take; a good MKV with a CSV one row short. | `pass` with no `numbers`; `fail` `mkv-not-readable` (the byte-offset read alone would pass); `fail` `mkv-frames-differ`; `pass` (only `rows-complete` fails, `rows-differ`) (3.6.12). |
| T-CERT-113 | 3 OS. `bursts` with fake arrival times: even intervals; one camera that gives frames in pairs. | `record-only`; `burst_share` 0 and about 0.5; no gate requires it. |
| T-CERT-114 | 3 OS. The USB 3 capability and the notices with the sample data of 3.6.13 for Windows, Linux and macOS, the known list and `bcdUSB`. | `usb3_capable` and `usb3_capable_source` follow the order `os`, `list`, `bcd`; the notice only with `yes` on a `USB 2` link; the milder notice only with `possible`; no notice with `no` or `null`; no check row. |
| T-CERT-115 | 3 OS. `system:memory` with fake memory facts: enough; less free memory than the need; on Linux a `/dev/shm` of 64 MiB for four cameras. | `pass`; `fail` `memory-low`; `fail` `shm-too-small`; the need equals the sum of `ring_total_size` of the rings of the product; the open still runs. |
| T-CERT-116 | 3 OS. `group:take-again` with fakes: a good second take; a second take whose writer is not released. | `pass`; `fail` with the reason of the take; the first take keeps its own rows. |
| T-CERT-117 | 3 OS. `report:rules` with a good report and with planted faults (a path in a value, a bad reason code). | `pass` with no `numbers`; `fail` `report-rules` with `problems`, `report-rules` in `evidence.reasons`, the pipeline item unchanged; no text of a problem is in the report; the validator is in the package. |
| T-CERT-118 | Windows, fakes. `system:camera-access` with the fake setting allowed, denied and unreadable. | Each case `record-only` with `access` `allowed`, `denied` or `unknown`; `denied` makes each camera `not-run` `no-access` and no `fail`; with `unknown` the opens run. |
| T-CERT-119 | 3 OS. `system:power` with fake facts, and a power plan with a name of the person. | `record-only`; `power_plan` from the closed list, `other` for the named plan, and the name is not in the report. |
| T-CERT-120 | 3 OS. `system:timer` on the virtual clock and with a fake sleep of 15.6 ms. | `record-only`; `sleep_1ms_p50_ms` 15.6; the check ends within 2 s. |
| T-CERT-121 | 3 OS. The catalogue after Q624 on an x86-64 and an ARM fake system. | No `system:backend`, `system:virtual-cameras`, `control:focus:sharpness`, `control:autofocus`, `control:white-balance`, `control:power-line` or `timings` in the plan or in `details.not_built`; `details.cameras` has `white_balance`, `white_balance_auto` and `power_line`; `self:scale-3` and `self:scale-12`; `self:idle-cpu` and the two ring self-checks on both systems; `identity:stable` and `identity:unique` stay. |
| T-CERT-122 | 3 OS. A full plan before the preview UI of step 4b exists. | `group:preview-during-take` is in `details.not_built.run` and not in `total`. |
| T-CERT-123 | 3 OS. Rule (b) and the count of the models: 3 models where one pipeline check fails on two and passes on one; 2 models where one stops before the take and the other fails `rows-complete`. | First: each of the two failing rows has the `module` of its model, the pipeline item does not fail. Second: rule (e): the failing model `fail`, the pipeline `partial` with `not-decided-one-model` (3.6.10). |
| T-CERT-124 | 3 OS. The gates by `module`: a take whose error names one camera of 4 models (Q621), with the sign-off checks faked as built. | `<model>:gate` of that model `fail`; `pipeline:gate` `pass`; each gate requires only rows with its own `module`. |
| T-CERT-125 | 3 OS. B1 and wedges: each camera of 3 models stalls after `ready`; one Kiyo Pro fake hangs in the open while a C922 fake fails `rate` in the same open. | First: each B1 row has the pipeline `module` (rule c), the pipeline item `fail`, the model items unchanged. Second: the Kiyo Pro item `fail`; the C922 `rate` row keeps its `module`, the C922 item `partial`, its `details.cameras` item has `blocked_by` = the label of the Kiyo Pro. |
| T-CERT-126 | 3 OS. No camera; a refused run (`cameras-busy`). | No pipeline item, and no row has a `module` (3.6.10). |
| T-CERT-127 | 3 OS. The record key of two cameras with no USB id and two OS display names, one of them in CJK. | Two rows `nousb:<raw name>`; no row is keyed by `Camera (no USB id)`; neither raw name is in the report (2.5). |
| T-CERT-128 | 3 OS. A quick and a full report of 4 good fakes. | No `pass` row holds a count of 0; no `exposure_set`; no `luma_at_m7`; `details.pipeline` has no `result`; `details.gates` has no item for a gate that is `not-run` only with `not-built`. |
| T-CERT-129 | macOS and Linux fakes. A full run with two models and a spy on each call of the source and system layer. | `<label>:usb3-trial` runs after phase G and before phase H; the BOS request is the last call of the trial and of the camera checks; the trial is not in quick and not on Windows; one row for the first unit of each model. |
| T-CERT-130 | macOS and Linux fakes. The guard: a fake interface whose vendor id, product id or release number differs from the registry or sysfs. | No request is sent; `bos_request` `null` and `bos_request_error` `FunctionTableNotVerified`. |
| T-CERT-131 | macOS and Linux fakes. The listing after: a camera that stays listed; one that is gone after the request. | `still_listed` `true` and no notice; `still_listed` `false` and the notice `camera-gone-after-usb-trial` with the camera name; the row stays `record-only`; no gate and no item changes. |
| T-CERT-132 | macOS and Linux fakes. The rows of the trial with each method answering, and with each method failing (no write access to usbfs, `kIOReturnNotOpen`, a missing `system_profiler`). | Each row is `record-only` with the `module` of its model and the keys of 3.6.13; each failure gives its class name in `<method>_error`; no row holds free text, a serial, a location id, a path or the product text; `usb3_capable` of `details.cameras` is the value of detection. |
| T-CERT-133 | 3 OS, session child [U Q646; the row: [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) item 15]. Fakes that leave after their take checks: a process exit and a stall; a hang at the close; a process exit at the close. | Each gets `<label>:live-at-close` `fail` with the product code (`crashed` with `exit_code` 3, `stalled`, `hung`, `crashed`) and the failure facts that have a value; no written result changes; the model item, `<model>:gate:no-hang` and `<model>:gate` are not `pass`; a good camera has `live-at-close` `pass`. |
| T-CERT-134 | The build file of 3.5.2 [U Q647]: a wheel from a checkout; the sdist and a wheel from the sdist; a source tree inside another git repository; a git that fails or gives text that does not decode; the `datas` of `skellycam.spec`; the CI step of the installer. | The commit and the tree state in the wheel, in the sdist and in the wheel from the sdist; no commit for the tree inside another repository; no commit and no failed build for a git error; `skellycam.spec` takes the file into `datas`; the CI step writes the file before a step changes the tree. |
| T-CERT-135 | 3 OS; the Linux and macOS cases land with phase 7. `<label>:in-use` (20.2) with a fake holder in a second session child: the product refuses with `camera-in-use`; the product opens the camera (shared); the apply hangs. | `pass`; `fail` `not-refused` with `outcome` `shared`; `fail` `hung`. |
| T-CERT-136 | 3 OS; the Linux and macOS cases land with phase 7; the holder is an OpenCV holder child (Q812). `<label>:in-use:other-program` (20.3) with a fake holder child of the backend of the OS: a refusal; a shared open; a holder that gets no frame. On Windows, a fake activity report with and without the holder. | `pass`; `fail` `not-refused`; `not-run` `holder-failed`; `holder_seen` true and false on Windows, `null` on Linux and macOS. |
| T-CERT-137 | 3 OS; the macOS and Linux cases land with phase 7. `<label>:in-use-mid-take` (20.3) with fakes: Windows build 26100 where the product warns 1 s after the join and marks the rows; the same with no mark; build 22000; macOS with the in-use flag; Linux where the holder gets `EBUSY` at `VIDIOC_S_CTRL`. | `pass` with `warned_s` 1 and `marked` true; `fail` `not-marked`; `not-run` `no-shared-mode`; `pass`; `pass` with `control_blocked` true; `frames_lost` 0 in each case. |
| T-CERT-138 | 3 OS; the Linux and macOS cases land with phase 7, and the attached case is Windows only (the activity monitor). The run start (20.1): one fake camera with a streaming other process, one with an attached other process named `LogiTuneAgent.exe`, one free. | The first: `opens` `not-run` `camera-in-use` and each later check `not-run` `camera-in-use`; the second runs, with `others_attached` 1; no row, `details` or log line of the report holds `LogiTuneAgent`; `details.before_run` of the plan holds the line of 20.1. |
| T-CERT-139 | 3 OS. `probe:<model>:hog-mode` (20.4) with the fake AVFoundation layer: hog mode settable and the second session refused; not settable; settable and not exclusive; the set back to -1 fails. | `pass`; `fail` `hog-not-settable`; `fail` `hog-not-exclusive`; the camera state `replug`. On Windows and Linux no such row. |
| T-CERT-140 | 3 OS; the Linux and macOS cases of the held camera land with phase 7. Own processes (20.5): a camera that a skellycam group of another process holds; an open group in the calling process; a group of `CameraGroup.create_without_cameras` in the calling process. | The first: `not-run` `camera-in-use` for that camera, the run is not refused; the second: `cameras-busy`; the third: the run is not refused. |
| T-CERT-141 | 3 OS. `is_model_checked` (20.6 item 1): a record with a row of the model; a row of another OS key; a reviewed pass in the known-systems file; a damaged record; no file. A spy on the capture libraries and on process starts. | True, false, true, false, false; no exception; no camera, child or capture library is touched. |
| T-CERT-142 | 3 OS. The complete state (20.6 item 2): a quick run of 2 fakes whose process ends during `group:take:finished`; a rebuild of the report from the last progress message by the rule of 9.8. | Each message holds each ended check with its full row; its `step` is the running check; the rebuilt report equals the report of a run that ends at that step, with `group:take:finished` `fail` `crashed` and the other planned checks `not-run` `interrupted`. |
| T-CERT-143 | 3 OS. `CameraGroup.create_without_cameras` (20.6 item 3) with two configs. | A group with no `CameraManager`; no process starts; no device is enumerated or activated; the attributes that freemocap names exist. |
| T-CERT-144 | 3 OS. The light data (20.7): a rate check that fails in the dark; a row `not-run` `too-dark`; a camera with no frame; quick and full plans. | `luma_mean` on each `rate` row from the ring or from `rate_luma_mean`; `null` with no frame; each plan has `lit-as-usual`; `details.limits.dark_luma` is 24 and `details.limits_uncalibrated` holds `dark_luma`. |
| T-CERT-145 | 3 OS. Host facts (20.8): a full report on a fake Linux system. | No row and no `details` key repeats a field of the host block of freemocap; `system:kernel` has no `kernel_major` and no `kernel_minor`, and it keeps `nodrop_param`, `clock_param` and the quirk numbers. |
| T-CERT-146 | 3 OS. The privacy list of the contract (20.8): the camera rows of a report with a planted key of each kind that the list of the contract forbids. Written after the contract has the list. | Each planted key or value is refused by the check that reads the list of the contract; the test holds no copy of the list. |
| T-CERT-147 | macOS fake, 3 OS. The permission (20.8): a quick run with the status `not-determined`. | Certify makes no request for the permission; `system:camera-access` gives the status, and each camera is `not-run` `no-permission`. |
| T-CERT-148 | 3 OS. The reason codes of section 20 (`not-refused`, `holder-failed`, `not-marked`, `not-warned`, `no-shared-mode`, `hog-not-settable`, `hog-not-exclusive`, `no-frame`, `read-gap`). | Each is in the list of section 15, and each reason that the checks of section 20 give is in it (the rule of T-CERT-30). |
| T-CERT-149 | 3 OS; the Linux and macOS cases land with phase 7. `<label>:control-read:gaps` (20.9) with fakes: (1) each read takes 3 ms and delays no frame; (2) each read holds the frames for 150 ms; (3) the fake has gaps of 150 ms also with the read off; (4) a read hangs. Then the local record and a product open of each model. | (1) `pass`, `reads_over_limit` 0, the row `control_read` `ok`; (2) `fail` `read-gap`, the row `control_read` `harms`, and a later take of that model has no read during the take (T-CAP-146); (3) `pass`: the gaps come from the camera; (4) `fail` `hung`, the camera state `replug`, `control_read` `harms`. `details.limits.control_read_gap_ms` is 100. |
| T-CERT-150 | 3 OS, fakes of the app page [U Q735, Q766, Q803]. A full run with a fake page result for the check `player-legacy-decode`: an `mp4v` tile, a WebCodecs tile, a tile switched by F6 and a tile that the core rule stopped; then a run with no app page; then a run before the v1 player code exists. | The row `player-legacy-decode` is `record-only` with the `module` of the pipeline item and blocks no gate; `details.player_legacy_decode` holds for each tile the fields of `player-legacy.md` 10.5 (T-LEG-79 checks their shape); with no app page: `not-run` `no-ui`; before the code: the name is in `details.not_built`. |

**The changes of 3.6 to the tests above [U Q591 to Q599, Q610 to Q618, A].** Where a row above and this list
differ, this list is the rule. T-CERT-91 to T-CERT-132 are new. Q624 also changes T-CERT-61 to T-CERT-64:
`self:scale-3` and `self:scale-12`; no `system:backend` and no `system:virtual-cameras`.

- T-CERT-01: `total` counts no check with no code and counts `session:exit`; full: `risks` empty and the estimate
  from the built checks (Q610).
- T-CERT-03: the schema id `skellycertify.report/1.7.0`; the pipeline item of `group` `component` (3.6.10).
- T-CERT-05 and T-CERT-70: replaced by T-CERT-94 (the name rule of 9.4).
- T-CERT-07: each camera has the eleven quick checks of 3.6.2 (with `live-at-close`, [ADR-0Z6Q](../decisions/entries/0Z6Q-choices-of-the-certify-report-shape-build.md) item 15); the run has five checks; the pipeline item `pass`.
- T-CERT-12 and T-CERT-73: the later checks are one `not-reached` row; a camera that fails at the open keeps
  `opens`, `rate` and `modes:granted:<base>` and has one `not-reached` row [U Q648].
- T-CERT-13: `image-effect` cases run at `full`. A dark case (Q773, 20.7): a pass in the dark stays `pass`; a fail
  in the dark is `not-run` `too-dark`; no frame or no ratio is `not-run` `no-frame`.
- T-CERT-14: `not-reencoded` and `size` cases run at `full`.
- T-CERT-17: `done` counts a `not-reached` row as its checks (T-CERT-92).
- T-CERT-19: the second C922 gets no row for the camera block, not `same-model`.
- T-CERT-22, T-CERT-45 and T-CERT-58: the checks `exposure:<w>x<h>@60` and the two Auto checks at 60 are removed
  (Q617); `rate:<w>x<h>@60` stays.
- T-CERT-26: no `<model>:units`; `details.cameras` has two items.
- T-CERT-35: the disk benchmark is part of `system:disk` (Q612): 20 s at the real load and 10 s at twice the
  load; `cameras_supported` from the measured JPEG size; no file of 1 GiB.
- T-CERT-44: the items come from the checks whose `module` is the model (3.6.10); full items are `partial` at most
  today (Q610).
- T-CERT-47: no full row is a local pass today (`"sign-off": "not-built"`); with the sign-off checks faked as
  built, the cases of the row apply, and the pipeline row is needed too.
- T-CERT-65 and T-CERT-68: no `<model>:gate:<step>` rows; `<model>:gate` and `pipeline:gate` require the checks of
  3.6.2.
- T-CERT-78: a failure key only with a value; no `failed_calls`; `exit_code` on each `crashed` row.
- T-CERT-79: the times are in `details.steps`, not on the rows.
- T-CERT-80: no `unit_id` and no `has_serial`; at most 32 modes (T-CERT-97).
- T-CERT-81: removed (no unit id, Q595).
- T-CERT-82: no `window_frames`, `interval_p95_ms` on the rate row, `grid_16ms_share` or `grain_ms`.
- T-CERT-84: the CPU keys are in the `open` and `take` items of `details.steps`.
- T-CERT-85: the range and the "before" values are in `details.cameras`; the gain keys on `image-effect` only.
- T-CERT-87: the validator checks the rules of 3.6 (one number one row, `not-reached`, `details.*`, `module` by
  3.6.10).
- T-CERT-89: the bound of 3.6.5: eight cameras at the longest form, at most 98,304 bytes for full and 65,536 for
  quick.
- T-CERT-90: no unit id: the second run compares the labels and the inventory only.

## 18. The other specs: answers and differences [A]

The agent compared this spec with [ux] and [req] and applied the cross-spec review of 2026-11-20 for
each item that names this spec. The three specs are now in one repository state; the second
cross-spec review and its fixes are in [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md). [ux] owns the diagnostics keys
and the failure codes; [req] owns the exposure search and the fall back; this spec owns the check
names and `camera_checks.json`.

### 18.1 Answers to "What certify must still add or change" [ux 4.6.4]

| # | Item of [ux 4.6.4] | Answer in this spec |
|---|---|---|
| 1 | macOS control routes: `exposure_unit` adds `ev`, `native`, `native-data`; `control_path` splits `cmio`; the -7 rule only for a time unit; no seconds sentence | Applied: 10.2 `<label>:controls:exposure-scale`, 10.1, 10.7. |
| 2 | Drop rules and `approaches` per control | Applied: 10.7, 11.2. |
| 3 | The `full` row holds each turn-on check and, for exposure, gain and focus, the route and its result | Applied: 2.5 (`gate`, `controls` with `route` and `result`). |
| 4 | Named turn-on checks | Applied: 11.3, roll-up checks `<model>:gate:<step>`. |
| 5 | `exposure`, `exposure_found_at_fps`, `exposure_search`; wait through `adjusting` and `checking` | Applied: 5.3, with `exposure_search.count`, `search_exposure()` and 25 s [req 1.3b, 1.5]. |
| 6 | Restore keys | Applied: 8.3, 10.3 read `restore_ok`, `restore_failed`. |
| 7 | Long-interval counters | Applied: 10.2 `<label>:sequence` reads `long_intervals`, `long_intervals_with_seq_gap`. |
| 8 | Warning kind `no_manual_exposure` | Applied: 4.3, 5.3 read the snake_case kind; the reason code stays `no-manual-exposure`. |
| 9 | Product `usb_link` value | Applied: 6.2. |
| 10 | JPEG reference keyed by VID:PID | Applied: 11.2, 10.7 proof 1; no `bcd_device`. |
| 11 | Citation | Applied: section 0 cites sections of the specs of this repository, not commit ids. |

### 18.2 The items of the cross-spec review for this spec

| Item | What the review asked | Done |
|---|---|---|
| C2 | Read `exposure` and `exposure_search` (`state`, `chosen`, `add_light`); `at_range_end` becomes `add_light` | Applied (5.3). |
| C3 | Wait until neither `adjusting` nor `checking`, 25 s; the search count | Applied (5.3) with `exposure_search.count` [req 1.5]. |
| C4 | One file name and key; say whether an upgrade makes a row stale | Applied (2.5, 13, T-CERT-41, T-CERT-47); an upgrade does not, question 2. |
| C8 | The 60 fps fall back | Applied (8.2, 5.3, T-CERT-58). |
| C9 | A camera with no manual exposure gets the value ignored and the warning | Applied (4.3, 5.3). |
| C11 | Product `usb_link` values; the cite of [ux 4.2 item 8] | Applied (6.2). |
| C13 | Stale names | Applied: `dqt_distinct` (4.4), `error_flag_frames` (10.3), `call` (T-CERT-37), `native_code`/`native_domain` (15), `ep0-refused` emitted by A5 to A8 (15), the errnos of A-15 (10.2), `AUTO` (2.2), the default `AUTO` (4.2). |
| C14 | JPEG reference key | Applied as [ux] decided: VID:PID only. |
| 2a | The macOS route ruling | Applied (4.3 direction rule, 10.2, 10.7, 11.2). |
| 2b | One test, one row; the gate in named checks | Applied (3.3, 3.4, 4 to 8, 10.2, 10.7, 11.3, 11.5). |
| 6 | Missing tests; probe child limits; flaky tests | Applied (9.3 limits; T-CERT-59 to 65; T-CERT-24 and T-CERT-25 on a virtual clock or with the marker `certify_timing`). |
| 7 | Search start with no HTTP; the hash set that re-arms; the probe child limit; the stale row; the local row content; `rate_fallback` | Applied (5.3, 4.4, 9.3, 2.5, 8.2). |

The second cross-spec review of 2026-11-20 found more differences. The fixes are applied in this
spec, [ux] and [req] ([ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md)); the rulings of the user that they need are in [ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md).

## 19. Choices of the first certify code [U]

The first code step (Windows first) and the fixes of its two independent reviews made these choices
where this spec was silent or unclear. The user accepted them on 2026-11-21
([ADR-VG5F](../decisions/entries/VG5F-choices-of-the-first-certify-code.md),
[ADR-X8XE](../decisions/entries/X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md)). The
sections above state some of them. This section states each one.

### 19.1 The first code [U]

1. Not built: `group:open` with the retry alone (4.2), `self:hang-100ms:*`, the camera block of
   `full`, and the group, system and self checks of `full`. Each such check is `not-run` with
   `not-built`. The `full` list has no check of a mode above `<base>`.
2. The plan reads no modes, so its check names use `<base>` `1280x720@30`. `total` is the count of the
   planned checks. A quick plan with no camera model to check has `total` 0.
3. A run with no option `cameras` checks each camera that is not reviewed, also a camera of a model
   that is in the record (2.4, [C 2.7]). The user kept this rule (9.1).
4. `<label>:time-gaps` is in each list that has `<label>:sequence`. With a sequence number, it is
   `not-run` with `has-sequence`, a new reason code.
5. A `clock`, `sequence` or `time-gaps` check whose diagnostics key is null or `unknown` is `not-run`
   with `not-built`. The Media Foundation source gives `clock` `unknown` and no `long_intervals`, so
   the gate cannot pass on Windows yet.
6. `<label>:clock:near-arrival` passes when the absolute p95 of sample minus arrival is 200 ms or
   less.
7. A failure of the product rate check at the open gives `opens` `pass` and `rate` `fail` with the
   product code. A camera that fails its rate check gives no ring frame, so `too-dark` for `rate` reads the
   D-3 key `rate_luma_mean` (3.5.15 P5). P5 is not built, so today `rate` stays `fail` [U Q773, Q821].
8. In the summary item, `sequence` `not-run` with `no-sequence` counts as passed when `time-gaps`
   passed, and the reverse.
9. A camera that is not `ready` before the take leaves the group, because a record start needs each
   camera `ready`.
10. The session child clears its parent mark (`multiprocessing.process._parent_process`), because the
    pubsub of the product refuses a camera group in a process with a parent. It keeps its parent
    handle before it clears the mark (19.2 item 5). It sets up logging as a camera process does.
    Decided, not built [U, question 5 of ADR-X8XE]: `managed_worker` sets an explicit role flag in
    each camera process, and the `parent_process()` guards read it. Certify then drops this
    workaround
    ([ADR-TFD7](../decisions/entries/TFD7-search-limit-stop-rate-median-role-flag-and-restore-after-a-failed-loop.md)
    item 3).
11. A ring watch keeps the SHA-256 of each ring frame by source frame number. A frame that the
    capture check flagged counts as damaged in `native-jpeg:valid`. `ring-equals-mkv` compares each
    MKV block that is not `missing` with the ring hash and with the hash set of the record start.
    With no compared frame, it is `not-run` with `ring-lapped`.
12. `gaps-explained`: 19.2 item 11.
13. A refused run (`cameras-busy`) has no summary item, so its checks have no `module`.
14. Phase G after a stop, a time-out or a crash: 8.3 and 19.2. The plain open closes with
    `restore=False`.
15. After a time-out or a crash: 9.3 and 19.2. `full` has one session limit of 240 s in this step.
16. The report has no `id`, and `commit` and `tree_modified` are null, so it is not yet valid as
    evidence. The schema is in 19.2 item 12. The exit check of the session child is `session:exit`,
    with no `module`.
17. The record holds `controls.exposure` for the route of the settings checks only.
18. `details.system_evidence` comes from the `systems` rows of the evidence file.

The report shape of 3.6 (decided 2026-11-23, not built) changes these items: item 1 (a check with no code leaves
`checks` and stands in `details.not_built`); item 4 (only the check of the pair that judges is written, so
`has-sequence` is not given); item 6 (`near-arrival` judges p5, 3.6.6 item 5); item 13 (a refused run still has no
summary item); item 16 (the commit, the tree state and the schema 1.7.0 are written; `session:exit` has
`module` = the pipeline name, 3.6.10).

### 19.2 The review fixes and format 1.6.0 [U]

1. The record row of a model comes from the summary item of that model, never from its name
   (T-CERT-72).
2. A wedge code (`hung`, `process-ended`, `device-removed`) after any step makes the running check
   `fail` (`hung`, `crashed` or `device-removed`), each later check of that camera `not-run` with
   `prior-failure`, and the camera `camera-wedged`. `<model>:gate:no-hang` counts only `fail` rows.
3. The session sends the "before" values as soon as the diagnostics hold them. Phase G never opens a
   wedged camera or a camera with no `opens` result; the second one is `camera-not-restored`. A camera
   with no known "before" values gets no open (8.3).
4. A camera whose loop failed after its controls were set is `camera-not-restored`, because the
   product does not restore it (`camera_loop.py`, `close(restore=not self.failed ...)`). In quick,
   question 4 of ADR-X8XE replaces this rule when it is built (8.3).
5. The session child keeps its parent handle before it clears the mark. A thread waits on the
   caller. At the death of the caller, it sets the kill flag, closes the group within 15 s and ends.
   The wait for an answer has a limit of 1 s in a loop. The caller stops the child in a `finally`,
   also after a `BaseException` from the progress callable (9.3).
6. A time-out ends the main process of the child, waits up to 12 s, then kills the rest. A cancel, an
   abandon and the end of the budget kill the tree. After a crash, the caller waits up to 12 s for the
   camera processes that it saw (9.3).
7. At a stop, the events already in the queue keep their results.
8. After a crash or a time-out, a running check is `fail` only when the checks that ran belong to one
   camera; else each is `not-run` with the cause. A refused apply gives `opens` `not-run` with the
   class name. A crash, a time-out or an abandon writes no record row.
9. `certify.lock` beside the record holds one run at a time. A second run is refused with
   `cameras-busy` and makes no work folder. A failed record write gives the cleanup row
   `write-record` (9.5).
10. The budget of quick starts at the call and holds the detection. The bound is in 9.3.
11. `gaps-explained` passes when the gaps are not more than the replaced frames of a window from
    before the record start to after the stop (4.5). Only the mode check of `<base>` counts for the
    summary item and for `gate:mode`.
12. Format 1.6.0: the schema id `skellycertify.report/1.6.0`; `abandon` stops as a cancel
    (`cancelled`) and writes no record row; no `test_media` and no `gpus`; `session:exit` has no
    `module`. The local contract clone is at 1.7.0, which changes only the `name` of a `test_media`
    item; skellycam writes 1.6.0, as the user decided (section 0).
13. Second review: the live change skips a wedged or not-ready camera. After the session starts its
    close, the caller kills nothing before 5 s + 8 s for each camera (9.3). A clean close means no
    reopen in phase G (8.3). A crash never blames a camera. A late abandon stops the record write.
    Camera logs go to `logs` of the work folder (9.5).
14. A camera with a step running at a stop is not opened again and gets `camera-not-restored`,
    because the product needs 5 s to declare a hang (8.3). Cost: no restore after a cancel during the
    take. The coordinator chose it, and the user accepted it (question 6 of ADR-X8XE).

The user answered "yes" to the six questions of ADR-X8XE on 2026-11-21: (1) keep 2.4 (9.1); (2) the
difference of one between `total` and the reported checks with no camera to check (9.1); (3) one
progress message for the computed checks (9.6, decided, not built); (4) the restore of a camera whose
loop failed, in phase G of quick (8.3, decided, not built); (5) the role flag (19.1 item 10, decided,
not built); (6) item 14. Not built: the check for a camera group that another process holds (9.7).

## 20. Exclusive access, the public calls for freemocap, and the light data

Status: accepted by the user on 2026-11-25 (Q813, [ADR-5PAR](../decisions/entries/5PAR-decisions-of-the-user-on-the-control-read-the-holder-and-the-exclusive-access-drafts.md)). The rules come from the decisions
of the user of 2026-11-25: exclusive access
([ADR-AA4X](../decisions/entries/AA4X-decisions-of-the-user-on-exclusive-access-of-a-camera.md)), the certify
fixes ([ADR-13BB](../decisions/entries/13BB-decisions-of-the-user-on-the-dark-rule-the-light-data-and-the-phase-7-items.md))
and the overlaps with freemocap
([ADR-CQ2X](../decisions/entries/CQ2X-decisions-of-the-user-on-the-overlaps-with-freemocap.md)). The details that
the user did not decide are choices of the agent
([ADR-FR2J](../decisions/entries/FR2J-choices-of-the-exclusive-access-and-overlap-specs.md)). Marks:
**[Qn]** is decision Qn of those entries; **[X n]** is item n of ADR-FR2J. The failing tests come before the code
(Q799). The Windows checks can be built; the Linux and macOS checks land with phase 7 (Q777). The tests are
T-CERT-135 to T-CERT-149 (section 17).

The product rule is [cap 21] and [ux 4.13]: skellycam needs exclusive control of each camera (Q771). Certify
follows it: "if we don't get exclusive use, it's an in-use result and we don't run the test" (the user, Q769).

### 20.1 Before a run, and a camera in use at the run start [Q768, Q788]

- The app shows one line before a run (Q768): "Close other camera apps (for example LogiTune, Razer Synapse, Teams,
  browser tabs)". `certify_plan` gives it in `details.before_run`, a list of texts [X 17]. The contract has no field
  for it.
- At the run start, before phase A opens a camera, the session child asks the product rule of [cap 21.4] (on
  Linux and macOS [ux 4.13]) for each camera: a camera with a streaming other process, or a refused open, is
  `<label>:opens` `not-run` `camera-in-use`, and each later check of that camera is `not-run` `camera-in-use`
  (Q788). Its summary item is `skipped` with `busy` when each unit of its model is held (9.7).
- An attached other process (Q782) is not "in use". `<label>:opens` gets the number `others_attached` (a count)
  [X 18]. The report never holds the name of a program, except the booleans of the fixed allow-list of
  `system:camera-apps` (6.2) [X 18].

### 20.2 `<label>:in-use` under the rule [Q769, Q788]

The check of 8.2 stays: a second session child holds the camera through the product source, then the first
session child applies the camera. The result changes (Q788):

- `pass` only when the product refuses the apply with the code `camera-in-use`.
- `fail` with `not-refused` when the outcome is `shared`: the product did not stop the sharing.
- `fail` with `hung` or `wrong-reason`, as before.

### 20.3 The other holders, and a loss during a take [Q785, Q788]

| Check | How | Numbers | Result |
|---|---|---|---|
| `<label>:in-use:other-program` (phase F) | A holder child that does not use the product source holds the camera (Q785): an OpenCV holder child (`CAP_DSHOW` on Windows, `CAP_V4L2` on Linux, `CAP_AVFOUNDATION` on macOS; Q812 below). Then the first session child applies the camera. | `outcome` (`refused`, `shared`, `hung`), `fail_code`, `holder_seen` (Windows: the activity monitor showed the holder; else `null`), `first_report_ms` (Windows: the time to the first report of the monitor, [cap 21.4]) | `pass` when the product refuses with `camera-in-use`; `fail` with `not-refused`, `hung` or `wrong-reason`; `not-run` with `holder-failed` when the holder child gets no frame |
| `<label>:in-use-mid-take` (phase F) | A take of 10 s in the first session child. At 3 s a holder child joins [X 20]. Windows: a Media Foundation source with the share-mode attribute of [S1] (build 26100 or later) streams, and at 5 s it sets exposure through `IAMCameraControl`; it leaves at 7 s. macOS: a second capture session starts on the camera, and it leaves at 7 s. Linux: the holder opens the node and at 5 s calls `VIDIOC_S_CTRL` for exposure. | `warned_s` (the seconds from the join to the warning), `marked` (the manifest has the mark of [cap 21.7]), `control_marked`, `control_blocked` (Linux: the holder got `EBUSY`), `frames_lost` | `pass` when the product warns within 2 s and marks the interval [X 20]; on Windows 11 22621 or later also the control mark [X 34]; on Linux, where no second stream can start, when the holder got `EBUSY` at `VIDIOC_S_CTRL` or the change is marked [X 35]; `fail` with `not-marked` or `not-warned`; `not-run` with `no-shared-mode` on Windows before build 26100 |

These two checks verify the facts that the research did not verify: that the activity monitor sees a reader that
joins later, that a shared reader can change exposure, that a DirectShow client goes through Frame Server, and the
RECORD priority on a real Linux kernel ([cap 21.9]). They run after `<label>:in-use` and before the 60 fps checks
[X 36].

**QX-2, decided by the user on 2026-11-25 (Q812, answer (a)): the holder of `<label>:in-use:other-program`.** The
holder child opens the camera with OpenCV; certify never judges OpenCV. The question was: the user ruled "no OpenCV
checks" (10.1; ADR-KG00 item 8: "Certify tests native capture only. OpenCV needs no test"). The holder must be a
program that is not the product source. The options:

- **(a)** The holder child opens the camera with OpenCV (`CAP_DSHOW` on Windows, `CAP_V4L2` on Linux,
  `CAP_AVFOUNDATION` on macOS). OpenCV is a dependency already. The check judges only the product, never OpenCV,
  and on Windows the DirectShow path also shows whether the activity monitor sees a DirectShow client [cap 21.9].
- **(b)** The holder child uses a small stand-alone open of the OS (Windows: a Media Foundation source of its own
  with no product code; Linux: `open` and `REQBUFS` through the `ctypes` layer of certify; macOS: a plain
  `AVCaptureSession`). No OpenCV, but more certify code, and on Windows it does not test the DirectShow path.
- **(c)** No such check: only the skellycam holder of `<label>:in-use`.

The recommendation is (a): the rule is about what certify judges, and here OpenCV is only the other program, not a
thing under test. The user chose (a) (Q812). The check is specified; it is `not-built` only until its code exists, as
each check of this section.

### 20.4 macOS: hog mode [Q787]

| Check | How | Numbers | Result |
|---|---|---|---|
| `probe:<model>:hog-mode` (camera probe, phase F) | In a probe child (10.4): set `kCMIODevicePropertyHogMode` of the device to the own process id, read it back, then start a second capture session in another probe child; at the end set it back to -1 [X 21]. | `hog_set` (the read-back is the own process id), `second_refused`, `hog_released` | `pass` when `hog_set`, `second_refused` and `hog_released` are true; `fail` with `hog-not-settable` or `hog-not-exclusive`; a camera with `hog_released` false gets the state `replug` (8.3) |

If the probe passes on the models of the shipped file (11.2), phase 7 sets hog mode at the open [ux 4.13.2 item 5].

### 20.5 Own processes, `cameras-busy` and the counter of freemocap on overlap 4 [Q796]

freemocap runs the certify of each package in its own spawn child. Thus "an open group in the calling process"
never sees the groups of the app, which are in the server process (the counter of freemocap). The rule (Q796):

- **Each camera.** A camera that any other process holds, also another skellycam group such as the one of
  freemocap, is `not-run` `camera-in-use` (20.1). The failed open finds it, or on Windows the activity monitor that
  shows another streaming process. The certify session child is another group, so the groups of the server of
  freemocap are other processes for it.
- **The whole run.** `cameras-busy` stays only for an open camera group in the calling process (9.7).
- **freemocap.** It still closes its own groups before a run. Its gate on camera starts during a check is built.

This replaces the "not built" item of 9.7 (the check for a group that another process holds) and question 10 of
section 14.

### 20.6 Public calls for freemocap [Q790, Q792]

1. **`is_model_checked(device, *, os_key=None) -> bool`** [X 22] (Q790). `device` is `vvvv:pppp`. True when the
   record of checked models (2.5) holds a row of this model for this system (OS key, backend, ABI), or when the
   known-systems file has a reviewed pass for it (2.5 "reviewed"). It reads the two files only. It opens no camera,
   activates no device, starts no child and loads no capture library. A damaged file counts as no row. It never
   raises for a file.
2. **The complete state in each progress message** (Q790). Each `progress` message holds in `checks` each check of
   the run that has ended, with its full row (`result`, `reason`, `module`, `numbers`), not only the last one, and
   `details` as far as the run has it [X 23]. Its `step` names the check that runs now (9.6). freemocap's crash
   record then rebuilds the module report of skellycam from the last message with no new code (9.8): the check of
   `step` is `fail` `crashed`, and each planned check with no row is `not-run` `interrupted`.
3. **A camera group with no camera** (Q792). freemocap's check `realtime-session` builds a group with no device.
   Today it subclasses `CameraGroup` and sets its internals. skellycam gives a public constructor
   `CameraGroup.create_without_cameras(camera_configs, *, rings=None)` [X 24]: a group with no `CameraManager`, no
   camera process and no device. The busy check of 9.7 ignores such a group: a group counts as open only when it
   has a `CameraManager`. [NV] which attributes freemocap's check reads; freemocap names them before the code
   (open work). The close path of `CameraGroup` belongs to another lane today; the code waits for it.

### 20.7 The light data for `DARK_LUMA` [Q773, Q774]

- Each report records `luma_mean` for each camera on its `<label>:rate` row, also when the rate check fails and
  when the row is `not-run` `too-dark` (Q774): from the ring frames, else from the rate window key `rate_luma_mean`.
  It is `null` only when the camera gave no frame.
- Each plan of each level has the question `lit-as-usual` (9.1). The app puts the answer in `answers` [C 3]. The
  report with its answer is the data of the calibration.
- `DARK_LUMA` stays 24 until a later decision sets it from the pooled reports (Q774). Each report marks it as not
  calibrated: `details.limits_uncalibrated` lists `dark_luma` [X 25], beside its value in `details.limits`.
- The rule of 4.6 (Q773): a check that passes stays `pass`, also in the dark; `too-dark` replaces only a `fail`; a
  check with no frame or no ratio to judge is `not-run` with `no-frame` [X 26].

### 20.8 Host facts, the privacy rule and the macOS permission [Q791, Q793, Q794]

- **No third copy of host facts** (Q793). freemocap writes the host block, and skellytracker owns the hardware
  facts. The report of skellycam keeps only camera, USB and backend facts. A field that those two already have is
  dropped. The first such field is the kernel release on Linux: freemocap's host block has `os.release`
  [NV: that it is `platform.release()`]. Thus `system:kernel` drops `kernel_major` and `kernel_minor` and keeps the
  driver facts (`nodrop_param`, `clock_param`, the expected quirks) [X 27]. skellycam still uses the release inside
  the run, for the quirks and for the key of `camera_checks.json`.
- **The privacy rule** (Q794). The list of forbidden content of a merged report (paths, media file names, keys such
  as `serial`, `hostname` or `user`) moves from freemocap's `report_file.py` into the certify contract
  (`report-format.md` of skellycertify). The owner of the contract decides the wording. The tests of skellycam then
  check the camera rows against the list of the contract (T-CERT-146), not against a copy.
- **The macOS camera permission** (Q791). When certify runs inside freemocap, freemocap asks for the permission,
  and the certify of skellycam never asks again. The stand-alone skellycam app asks for itself, as decided on
  2026-11-20. Certify itself never shows the dialog (10.3, `system:camera-access`).

### 20.9 The control read during a take [Q811]

The user decided (Q811) that the read of [cap 11.4], one time each second, stays during a take and finds a change of
exposure, gain or focus by another program on a build with no control monitor [cap 21.6]. The reason: the four Kiyo
Pro wedges all began at a stream start or stop, "never mid-stream and never during control polling alone"
[M `research/usb_cameras/docs/kiyo_pro_wedge_research.md` §1]. Q811 supersedes the words "no poll during a take" of
Q784 for this read. Certify checks for each camera model that the read does no harm. The details of the check are
choices of the agent, marked **[R n]**: item n of [ADR-J1HD](../decisions/entries/J1HD-choices-of-the-control-read-check.md) (proposed). The user decides them before the code.


| Check | How | Numbers | Result |
|---|---|---|---|
| `<label>:control-read:gaps` (full, phase D, the first unit of each model) | The camera streams alone at `<base>` in `MANUAL` at -7 for 30 s with the product read of 11.4 on, then 30 s with it off (the setting `SKELLYCAM_CONTROL_READ=0` of the session child [R 1]). Certify takes the time of each read from the diagnostics of the control thread (start and end of each `set_controls({})`) and the arrival time of each frame. A read "overlaps" a frame interval when the interval holds a part of the read, or ends less than one frame period after the read ends. | `reads`, `read_ms_p50`, `read_ms_max`, `gap_at_read_max_ms` (the largest interval that overlaps a read), `gap_no_read_max_ms` (the largest interval of the 30 s with the read off), `reads_over_limit` (the reads with an overlapping interval above `control_read_gap_ms`) | `pass` when `reads_over_limit` is 0, or when `gap_no_read_max_ms` is also above the limit (the gaps then come from the camera, not from the read) [R 2]; `fail` with `read-gap` otherwise; `fail` with `hung` when a read hangs (the camera then gets the state `replug`, 8.3) |

- The limit `control_read_gap_ms` is 100 ms, the gap rule of U16 [cap 6.6, T-CAP-82]. It stands in `details.limits`.
- The result goes to the local row of the model as `control_read` (2.5): `ok` after a `pass`, `harms` after a `fail`
  [R 3].
  A reviewed report can add the limit code `control-read-harms` to the shipped row of the model (11.2).
- The rule that follows (Q811): for a model whose local row has `control_read` `harms`, or whose shipped row has
  `control-read-harms`, the product pauses the read during a take on each build [cap 21.6] [R 4]. T-CAP-146 tests the rule,
  and T-CERT-149 tests the check.
- The check runs in phase D because the read is normal product behaviour [R 5]. It adds about 60 s for each model to a full
  run (section 16).
