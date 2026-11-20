# Camera requests of 2026-11-20: exposure, one frame rate, USB link label

Status: proposed by an agent on 2026-11-20, then revised on the same day with the answers of the
user to its 14 questions (section 5). The decisions of the user are in
[ADR-C4FZ](../decisions/entries/C4FZ-camera-requests.md). The choices of the agent that are still
open are in [ADR-Y6F6](../decisions/entries/Y6F6-camera-request-choices.md). This file holds the spec
text and the test list only. The user accepts them before any code is written. This file does not
change [`windows-capture.md`](windows-capture.md) yet. Each part gives the text of each change to
that spec as "Change to section N".

## 0. How to read this spec

Marks:

- **[En]**, **[Fn]**, **[Ln]**: decision n of the user on 2026-11-20 on exposure (E), the frame rate
  (F) and the USB link label (L) ([ADR-C4FZ](../decisions/entries/C4FZ-camera-requests.md)).
- **[Qn]**: the answer of the user to question n of the first draft, 2026-11-20 (section 5,
  [ADR-C4FZ](../decisions/entries/C4FZ-camera-requests.md)). It is a decision.
- **[An]**: choice n of the agent (section 4). The user decides it.
- **[UI 11-20]**: a decision of the user of 2026-11-20 on the UI, relayed by the supervisor, that
  this spec must agree with. No entry on this branch holds it yet (section 6).
- **[cap x.y]**: section x.y of [`windows-capture.md`](windows-capture.md). **[Dn]**, **[Un]**,
  **[Wn]**: the marks of that spec.
- **[M file]**: measured; the file holds the result. Each such file is on branch `dom/research` at
  commit 56d2b907d. It is not on this branch.
- **[sfn26 file]**: the file on the branch `sfn26` of the upstream repository, read on 2026-11-20.
- **[NV]**: not verified on a camera.

The tests have the IDs T-REQ-nn. The kinds are those of [cap 16.1], plus **ui-unit**: a test of a
pure TypeScript function that runs with `node --experimental-strip-types --test`, as the script
`test:recording-shutdown` of `skellycam-ui/package.json`. **ui-manual** is a check that a person makes
in the running app.

In the UI, each text that names a camera uses the form `Camera <list number> · <name>`
[UI 11-20]. The texts of the server name a camera by its ID, as today. Section 1.8 gives the rule
that joins the two.

This spec uses British spelling.

## 1. Part 1: exposure

### 1.1 The rule

- The UI and the API have two exposure modes: `MANUAL` and `AUTO` [E1].
- `MANUAL`: the camera uses the value of the config. The unit stays log2 of seconds (-7 = 1/128 s)
  [D35].
- `AUTO`: SkellyCam finds the value with the exposure search of 1.3, one time, when the user asks.
  Then SkellyCam holds that value. The camera control stays in its manual setting at all times
  [E1, E3, Q3].
- The auto exposure of the camera is never a mode. On Windows, SkellyCam never turns it on, also not
  at the start-up [E1, Q1].
- Exception until phase 7: on Linux and macOS, the OpenCV source of today forces the auto exposure of
  the camera. This is an exception to the rule above. It stays until phase 7 [Q11]. Section 1.7
  gives the detail.
- The sfn26 label "Recommend" and the sfn26 `AUTO` (the auto exposure of the camera) go away [E1].
- The exposure of a camera never changes during a take [E3]. Each request that changes it during a
  take is refused (1.5).
- The default for a new camera stays `MANUAL` -7 [E5].

### 1.2 When the search runs

The search runs only when the user asks [E3, Q3]:

1. The user presses the button "Auto-set exposure (all cameras)" [E4]. Each selected camera that
   streams goes to `AUTO`, and each one runs the search on its open stream.
2. The user presses the link "Search again" in the settings of one camera [Q2]. That camera runs the
   search on its open stream.
3. The user switches a camera that streams from `MANUAL` to `AUTO` (an apply request) [Q3]. That
   camera runs the search on its open stream.

The search never reopens a camera. It never runs by itself. These events do not run it, and the
camera uses its held value [Q3]:

- a connect;
- a reopen for a change of size or rate, also the fall back to 30 fps of 2.4;
- "apply again" of a `failed` or `dead` camera;
- an apply request with the same config (`AUTO` with `AUTO`), which has no effect [cap 8.3].

A switch to `AUTO` while the camera does not stream only changes the stored config. The next connect
does not search (1.3a).

### 1.3 The search

The search replicates `recommend_exposure` of [sfn26 `skellycam/core/camera_group/tasks/recommend_exposure.py`],
with the guard of the frame rate [E2]:

1. The values are -12 to -5, in that order [E6].
2. For each value:
   1. Set the value (a bounded call of [cap 6.6]).
   2. Wait for 10 delivered frames that arrived after the set call returned, as sfn26 [Q4].
   3. Brightness: the mean of all pixels of the decoded image of the 10th frame, as sfn26
      (`np.mean`, all channels). A JPEG frame is decoded for this one time.
   4. Rate: the formula of [cap 10.1], `(s_b - s_a) / (t_b - t_a)`, from the 10th frame (a) to the
      40th delivered frame (b) after the set: 30 intervals [Q4].
   5. The value keeps the rate when the rate is not more than 3 % below the mode rate
      (`rate_check.is_slow` is false) [E7].
   6. Early decision, as [cap 10.2]: the value does not keep the rate as soon as frame `s_a + 30`
      cannot arrive in time: `now - t_a > 30 / (0.97 x r)`. The search then goes to the next value at
      once [A1].
3. The search measures the rate at each value. It does not assume that a shorter exposure gives a
   higher rate [E8]. Measured: in its 60 fps mode, the C922 gave 59.7 fps at -7, 29.7 fps at -8, -9
   and -10, and 56.5 fps at -6 [M `research/usb_cameras/docs/free_run_log_20261120.md` §9].
4. The choice: of the values that kept the rate, take the value whose brightness is nearest to 127.5.
   Then go one step darker (offset -1), as sfn26 and the old helper [E6]. The darker value must also
   have kept the rate, and it must be -12 or more. Else the search keeps the nearest value [Q5].
   Example (the C922 at 60 fps): only -7 kept the rate, so the result is -7, not -8.
5. "Add light" [E7, Q6]: when the brightness at the brightest value that kept the rate is below 64 of
   255, the result carries the flag `add_light`. The search still holds its result, and it still
   applies the offset of item 4. 64 is a starting value. A camera run in a dim room sets the limit
   (T-REQ-25).
6. The search fails in these cases. A failed search sets the old exposure (mode, value and
   `exposure_found_at_fps`) again [E6]:
   - no value kept the rate;
   - a set call returned an error, or its read-back differed from the value;
   - the search took more than its limit of 20 s [A2];
   - the group closed the camera.
7. A hang of a set call is a hang of [cap 6.6]: the camera fails or dies, and the process ends hard.
   A stall of 2 s is a stall of [cap 9.5]. The search then has no restore step.
8. The search ends with the result value set. The config stores `exposure_mode: "AUTO"`,
   `exposure: <result>` and `exposure_found_at_fps: <the mode rate>` [E3] [A3].

The frames and the time:

- 10 frames to settle and a rate window of 30 frames are starting values. A camera run confirms them
  (T-REQ-23) [Q4]. [cap 10.5] gives the evidence for the rate: a skip of 3 or more frames with a
  window of 30 to 90 frames gave 0 false alarms in 119 changes and caught 31 of 31 slower ones.
- At 30 fps with no slow value: 8 values x 40 frames = 320 frames, about 10.7 s. At 60 fps: about
  5.3 s.
- The worst case at 30 fps, with each value slow at 15 fps: 10 frames take 0.67 s, and the early
  decision comes 1.03 s after `t_a`. That is 8 x 1.7 s = 13.6 s. The limit of 20 s holds it, with
  margin for the eight set calls (1 to 3 ms each [cap 6.8]).

Who does what:

- The control thread does each set, because the loop thread never calls `set_controls` after the
  start-up [U16]. The loop thread takes the frames and measures. The two threads pass one value at a
  time. The read of the controls each second waits while the search runs [A4].
- Each camera searches on its own, in its own process, at its own pace. sfn26 sets one value on all
  cameras at the same time and waits for all; this spec does not, because the cameras of one group
  can need different times for one value [A5].
- The loop takes frames only at the rounds of the gate. "The 10th delivered frame" is then the first
  taken frame whose `source_frame_number` is 10 or more after the set. The same applies to the 40th
  frame. The formula counts delivered frames, so the gate does not change the rate of a push source
  [cap 10.1]. A frame that arrived in time and waits at the gate gives no early decision (agent 88
  of [cap 10.2]).

### 1.3a The held value

- The held value is `exposure` of a camera config in `AUTO`. The new config field
  `exposure_found_at_fps: float | None = None` tells where it came from [A3]:
  - a number: the mode rate at which a search found the value;
  - `None`: no search found a value yet.
- The search sets both fields. A switch to `MANUAL` sets `exposure_found_at_fps` to `None` and keeps
  `exposure` as the manual value.
- Where it is kept: in the config of the server while the group runs, and in the stored settings of
  the UI (the desired config of each camera). After each response that carries configs (apply, the
  button, "Search again"), the UI copies `exposure` and `exposure_found_at_fps` of each camera in
  `AUTO` into its desired config. Thus the held value is kept across a close and across a restart of
  the app [A6].
- At the start-up, a camera in `AUTO` sets `exposure` as a manual value at step 5 of [cap 9.1]. No
  search runs [Q3].
- A camera in `AUTO` with no held value (`exposure_found_at_fps` is `None`) starts at its `exposure`
  value: -7 for a new camera. It does not search by itself. Its row says "Auto: not searched yet" and
  offers the search (1.8) [A7].
- A reopen of a running camera (size or rate) uses the held value of its current config, not the
  `exposure` of the request, so that an old value in a request cannot replace it [A8].
- A held value found at another rate: the value keeps its brightness at the new rate, because the
  exposure time does not change. Its rate guard does not hold at the new rate. The start-up rate check
  at the new rate is the only check (2.4). When the rate class of `exposure_found_at_fps` differs from
  the mode rate, the row says "Found at 30 fps: search again" (or "at 60 fps") [A9].

### 1.4 States and the other cameras

- The searching camera stays in the gate, with its preview. The other cameras keep streaming, with
  their preview. The gate still waits for each camera [E9]. Thus a value at which one camera is slow
  also slows the rounds of the gate, and the preview of each camera, for that value (about 1 s).
- A new state `adjusting` holds a camera while its search runs [Q7]: preview yes, in the gate yes,
  as `ready`. A recording cannot start, and a changed config of that camera is refused (HTTP 409).
- After the search, the camera sets its result value. Its state goes to `checking`, and the check of
  [cap 10.2] decides `ready` or `too_slow`, as after a live change.
- A `too_slow` camera keeps its tile and counts as streaming [UI 11-20]. This agrees with
  [cap 8.1] (`too_slow`: preview yes, in the gate yes).
- Known weak point: the OpenCV source is a pull source. Its `source_frame_number` counts only the
  frames that the loop grabs. Thus with the OpenCV source (the temporary source of [cap 14.2] on
  Windows), a slow camera of the group can make the measured rate of another camera low, and that
  camera then does not keep a value that it can keep. The Media Foundation source does not have this
  fault. The OpenCV source on Windows goes at the end of phase 3 [D8].

### 1.5 API

Config:

- `CameraConfig.exposure_mode`: `"MANUAL"` or `"AUTO"`. A request with `"RECOMMEND"` is read as
  `"AUTO"`, so that old saved configs keep working [A10]. Each other value gets HTTP 422.
- `exposure`: for `MANUAL` the value to set. For `AUTO` the held value (1.3a).
- `exposure_found_at_fps`: 1.3a.

New endpoint [A11]:

```
POST /camera/group/exposure/auto
```

- With no body, it applies to each selected camera of the group (the button). The body
  `{"camera_ids": ["a1b2"]}` limits it to those cameras ("Search again"). A camera ID that is not
  selected gets HTTP 422.
- It sets each camera to `AUTO` and runs the search on each, at the same time. It returns when each
  search has ended.
- Response 200:

  ```json
  {"camera_configs": {"a1b2": {"exposure_mode": "AUTO", "exposure": -8, "exposure_found_at_fps": 30.0, "...": "..."}},
   "results": {"a1b2": {"state": "done", "chosen": -8, "add_light": false, "reason": null,
                        "trials": [{"value": -12, "brightness": 22.4, "measured_fps": 30.01, "kept_rate": true}]}},
   "camera_failures": {},
   "warnings": []}
  ```

- HTTP 409: no camera group runs; a recording runs [D36]; a search runs; a camera is `starting`,
  `waiting` or `adjusting`. The detail names each camera and its state [cap 8.3].
- HTTP 422 on Linux and macOS: `the exposure search runs only on Windows until phase 7` (1.7).
- The switch from `MANUAL` to `AUTO` in an apply request runs the same search for that camera. The
  apply response then carries its result in `warnings` and in the status.

Status ([cap 8.4]) adds `exposure_search`: null before the first search, else the `results` object
of one camera above. `"state"` is `"running"`, `"done"` or `"failed"`.

Warnings ([cap 11.3] form: `kind`, `camera_ids`, `text`, `control`) [A11]:

- `add_light`, control `exposure`:
  `Camera a1b2: add light. At 30 fps the brightest exposure that keeps the rate is -6, and the image is too dark (mean 41 of 255).`
- `exposure_search_failed`, control `exposure`:
  `Camera a1b2: the exposure search failed: no exposure from -12 to -5 keeps 30 fps. The exposure is -7 again.`

The apply response and the search response carry them. The status `warnings` of the camera keeps
them until the next exposure change of that camera.

Pending (not accepted yet, 2026-11-20): each camera failure reason gets a fixed failure code beside
its text [UI 11-20]. When that decision is accepted, the search failure and the reasons of 1.5a get
codes. This spec does not name them.

### 1.5a The texts of a slow camera

One set of texts [Q8] [A12]. The texts of [Q8] stay. The text of the user for a `too_slow` row
[UI 11-20] is added. For one camera in `MANUAL`, the server reason and the row then give the same
hint ("lower the exposure"), so the `MANUAL` reason adds it:

| Where | `MANUAL` | `AUTO` |
|---|---|---|
| Reason of a camera that fails the start-up rate check ([cap 10.4], server) | `declared 30.00 fps, measured 25.76 fps. Add light or lower the exposure, or set the exposure to Auto.` | `declared 30.00 fps, measured 25.76 fps. Add light, then run the exposure search again.` |
| Row of a `too_slow` camera (UI) | `Too slow at this exposure: lower the exposure` [UI 11-20] | `Too slow at this exposure: add light, then search again` |

- When the mode rate is above 31 fps, the reason adds ` Or choose 30 fps.` [Q8].
- "Lower the exposure" is the usual help at 30 fps: the Logitech cameras give 16 fps at -4 and 30 fps
  at -5 [cap 10.5]. It is not always right: the C922 at 60 fps is slower at -8 than at -7 (1.3 item
  3). The `AUTO` search finds such a value; the `MANUAL` text does not try to.

### 1.6 The auto exposure of the camera

SkellyCam never uses it on Windows, also not at the start-up [Q1]. The reasons:

- The search tries each value from -12 to -5 anyway. A start point from the camera does not make the
  search shorter.
- The value that a camera reports in auto may not be its real exposure. Both cameras of the 60 fps
  test read back "auto, -10" [M `research/usb_cameras/docs/free_run_log_20261120.md` §9].
  [cap 17.3] also gives this as not known.
- The auto exposure of the camera changes the frame rate. The C922 in auto at 60 fps gave 37 fps at
  the start and 54 fps over 10 s (same file).

### 1.7 Linux and macOS (the OpenCV source)

The rule until phase 7 [Q11]:

- On Linux and macOS, the forced auto exposure of the camera of today stays. This is an exception to
  the rule of the user that the camera never sets its own exposure [E1]. The user knows it is an
  exception. Phase 7 ends it.
- The UI shows the exposure row as "Set by the camera on this system" and hides the mode choice, the
  link "Search again" and the button. The endpoint of 1.5 gives HTTP 422. A config with `AUTO` opens
  with no search. The warning of [cap 11.3] comes at each record start (T-CAP-104).
- Phase 7 adds the search on Linux with the conversion below.

What the OpenCV source can do:

- Linux: OpenCV V4L2 writes `CAP_PROP_EXPOSURE` to `V4L2_CID_EXPOSURE_ABSOLUTE`, in units of 100 µs,
  with `CAP_PROP_AUTO_EXPOSURE` set to 1 (manual) [NV]. Thus a value v of this spec is `2^v x 10,000`
  units: -7 is 78, -5 is 312. Cameras round to their own steps [NV]. sfn26 skips the search on Linux,
  because its values are log2 seconds, not V4L2 units
  [sfn26 `skellycam/core/camera_group/camera_backend_manager.py`].
- macOS: the OpenCV AVFoundation backend does not set exposure, to the knowledge of the agent [NV].
  sfn26 runs its search on macOS; whether a set has an effect there is not known.
- On Windows the search runs with both sources (Media Foundation and the temporary OpenCV source of
  [cap 14.2]), because DirectShow and Media Foundation use the same log2 unit.

### 1.8 UI

- Camera settings (`CameraGridSettingsModal.tsx`): the row "Exposure" keeps the two choices Manual
  and Auto. Manual shows the value selector, as today. Auto shows the held value as text, "Auto: -8",
  and the link "Search again", which runs the search for this camera only [Q2]. With no held value,
  the text is "Auto: not searched yet", and the link reads "Search". The link is disabled while the
  camera does not stream or a recording runs.
- `CameraConfigExposure.tsx` (the panel): the third choice "Recommend" goes. `isDisabled` becomes
  `exposureMode === 'AUTO'`.
- `cameras-types.ts`: `EXPOSURE_MODES = ['MANUAL', 'AUTO']`; `CameraConfigSchema` gets
  `exposure_found_at_fps` (number or null). A saved config with `RECOMMEND` becomes `AUTO` when the
  store loads it. The i18n key `recommend` stays unused until a cleanup of the locale files.
- The camera list (`CameraConfigSidebarPanel.tsx`): a button "Auto-set exposure (all cameras)" in
  the header, next to the stream buttons. It is enabled when at least one selected camera streams
  and no recording runs, as the "Update Cameras" button is disabled during a recording [UI 11-20].
  Else its tooltip says why (`stopRecordingFirst`, or "Connect the cameras first"). While it runs, it
  shows the loader icon and the text "Setting exposure…".
- Each camera row (`CameraTreeItem.tsx`):
  - the chip `E:-8` for `MANUAL` as today, and `E:-8 auto` for `AUTO`;
  - "Auto: not searched yet" for `AUTO` with no held value;
  - "Found at 30 fps: search again" for a held value found at another rate class (1.3a);
  - the chip "Add light" in the warning colour for an `add_light` warning, and "Exposure search
    failed" for `exposure_search_failed`, each with its text as the tooltip;
  - the texts of 1.5a for a `too_slow` camera.
  A pure function `exposureRowText(config, modeRate, state, warnings)` in
  `skellycam-ui/src/store/slices/cameras/exposure-row.ts` gives these texts.
- A camera in `adjusting` shows "Setting exposure…" over its preview.
- Camera names in the UI: a tooltip or a line that shows a text of the server replaces each camera ID
  of the item's `camera_ids` with `Camera <list number> · <name>`, and drops the word "Camera" or
  "camera" just before the ID. A pure function `labelText(text, cameras)` does it [A13].
- On Linux and macOS: 1.7.

### 1.9 Edge cases

- A camera without an exposure control (`present: false`): the search fails at once with
  `Camera a1b2 has no exposure control` (the text of [cap 11.5]). Its mode stays as it was.
- A camera dies during the search: it is `dead` [cap 8.2]. The other searches go on. The response
  has its failure in `camera_failures`.
- A second press of the button, or "Search again", while a search runs: HTTP 409.
- An apply request for a camera in `adjusting`: HTTP 409, as for `starting` [agent 45 of cap].
- Unselect of a camera in `adjusting`: allowed. The search stops, and the camera closes.
- The 60 fps mode where only one value keeps the rate (the C922): 1.3 item 4.
- A camera whose rate falls only for a time after a set: the 10 frames to settle cover the change.
  A camera that needs longer can fail a value that it can keep. T-REQ-23 records this.
- The button when some selected cameras do not stream (`failed`, `dead`): only the cameras that
  stream search. The response names the others in its detail as "not streaming".
- A camera in `AUTO` held at a value found at 30 fps, when the user picks 60 fps: 2.4.

### 1.10 Changes to windows-capture.md

Change to section 1.3 (the item of D44): "A change of the UVC power line frequency control and a
flicker measurement [D44]. The "Add light" text of the exposure search is in
[`camera-requests.md`](camera-requests.md) 1.5 (2026-11-20)."

Change to section 3: add the row "`skellycam/core/camera/capture/exposure_search.py` | The exposure
search of `camera-requests.md` 1.3: the values, the choice, the flag `add_light`. Pure functions,
with the frame feed of the loop."

Change to section 4.3, row "Control thread": add "During an exposure search, it does each set of the
search, and it holds its read each second (`camera-requests.md` 1.3)."

Change to section 8.1: add the row "| `adjusting` | The exposure search runs on the open stream
(`camera-requests.md` 1.4). | yes | yes |".

Change to section 8.2: add the rows "| `ready`, `too_slow`, `checking` | the button, "Search again",
or a change of the mode from `MANUAL` to `AUTO` | `adjusting` |" and "| `adjusting` | the search
ended (with its result, or with the old setting after a failure) | `checking` |". Add `adjusting` to
the "From" cells of the rows "device removed; 2 s without a frame", "a bounded call times out" and
"unselect".

Change to section 8.3: add the row "| `adjusting` | blocked | refused | no effect | allowed |".

Change to section 8.4: add "`exposure_search` is null or the result object of `camera-requests.md`
1.5. `warnings` also holds the items `add_light` and `exposure_search_failed` until the next
exposure change of the camera."

Change to section 9.1, step 5: "Set every control of the config (section 11). A camera in `AUTO`
sets its held value as a manual value. No exposure search runs at the start-up
(`camera-requests.md` 1.3a)."

Change to section 10.4: replace the text with the two reasons and the 60 fps addition of
`camera-requests.md` 1.5a.

Change to section 11.1: replace the section with:

"- Modes: `MANUAL` and `AUTO` (`camera-requests.md` 1.1). `AUTO` is the exposure search of
  SkellyCam. It runs only when the user asks and holds its result. The auto exposure of the camera is
  never set on Windows. This replaces the modes of D29 for exposure.
- The value keeps the unit of today: a power of two in seconds (-7 = 1/128 s) [D35].
- The search, its values, its frames and its rate guard: `camera-requests.md` 1.3. The held value:
  1.3a."

Change to section 11.2: add "A change of the mode from `MANUAL` to `AUTO` of a camera that streams
starts the exposure search on the open stream (`camera-requests.md` 1.2). A change from `AUTO` to
`MANUAL` is a live set of the value."

Change to section 11.3: the kinds are `auto_control`, `mixed_rate`, `control_change_failed`,
`add_light`, `exposure_search_failed` and `rate_fallback`. On Windows, `auto_control` no longer comes
for exposure.

Change to section 12, row `set controls`: "each control set and read-back at start". The example
reason becomes the `MANUAL` reason of `camera-requests.md` 1.5a.

Change to section 14.1: add "Until phase 7, the forced auto exposure of Linux stays as an exception to
the rule of `camera-requests.md` 1.1, and the exposure mode choice and the exposure search are not
offered on Linux and macOS (`camera-requests.md` 1.7)."

Change to section 16.2:

- T-CAP-18: the reason is the `MANUAL` reason of `camera-requests.md` 1.5a.
- T-CAP-34: the fake camera reports its exposure in auto (a script value), with the config in
  `MANUAL`; the rest stays. The reason: a config cannot ask for the camera auto exposure now.
- T-CAP-41: `MANUAL -7` and `AUTO` held at -9 with a brightness model in the fake: both open with
  one manual set, and no search runs. `RECOMMEND` is read as `AUTO`.
- T-CAP-42: the fake reports its exposure in auto with no set through the config; the rest stays.
- T-CAP-53, T-CAP-94: the reason is the `MANUAL` reason.
- T-CAP-55, T-CAP-96: "with the exposure search (the button) after the open" in place of "with auto
  exposure".
- T-CAP-77: exposure leaves the test; it reads the auto focus only.
- `skellycam/tests/capture/capture_hardware.py` `SLOW_REASON`: the new forms.

Change to section 16.3: T-CAP-55 is "a dark room with the exposure search".

Change to section 20: add a note after D29: "Note: for exposure, C4FZ of 2026-11-20 replaces the
modes of D29 ([ADR-C4FZ](../decisions/entries/C4FZ-camera-requests.md))." Add the same note after
D44 for the "exposure advice", and after D45 for the USB link display.

### 1.11 Tests

| ID | Kind | Set-up | Pass criterion |
|---|---|---|---|
| T-REQ-01 | fake | One fake at 30 fps, `ready` in `MANUAL -7`, `brightness` = (-12, 10), (-11, 20), (-10, 40), (-9, 70), (-8, 110), (-7, 150), (-6, 190), (-5, 230); rate 30 at each value; apply `AUTO`. | The fake gets the sets -12 to -5 in order, then -9 (-8 is nearest to 127.5, then one darker). The config holds `AUTO`, -9, `exposure_found_at_fps` 30. No `add_light`. State `adjusting`, `checking`, `ready`. |
| T-REQ-02 | fake | As T-REQ-01, with a new script field `rate_by_exposure` = (-6, 15), (-5, 15); press the button. | Open count stays 1; the JPEG ring name does not change; the ring gets frames during the search; state `ready` → `adjusting` → `checking` → `ready`; result -9: -6 and -5 are never kept; the trials of -6 and -5 have `kept_rate: false`. |
| T-REQ-03 | fake | The C922 pattern: mode 60 fps; `rate_by_exposure` 60 at -7 only, 29.7 at each other value; brightness nearest to 127.5 at -6; press the button. | Result -7 (-6 did not keep the rate; -8 did not keep it, so no offset). A rate is measured at each of the 8 values. |
| T-REQ-04 | fake | Brightness 50 at -5, darker below; rate 30 at each value; press the button. | Result -6; `add_light` true; the response and the status `warnings` hold `add_light` with the text of 1.5; the camera is `ready`. |
| T-REQ-05 | fake | The generic camera: 25.76 fps at each value; `ready` with `MANUAL -7`; press the button. | The search fails; the last set is `MANUAL -7`; the warning `exposure_search_failed` with its text; the camera then runs the check of [cap 10.2] and is `too_slow`, and it stays in the gate with its preview. |
| T-REQ-06 | fake | Connect one fake with `AUTO`, `exposure` -7 and `exposure_found_at_fps` `None`. | One set of -7 at step 5; no search; `ready`; the config keeps `exposure_found_at_fps` `None`. |
| T-REQ-07 | fake | The image follows a new exposure only from the 3rd frame after the set; frames that arrived before the set returned have the old brightness; press the button. | Result as in T-REQ-01; the brightness of each trial is the value of the 10th frame that arrived after the set returned. |
| T-REQ-08 | fake | One value at 10 fps, the others at 30, on the virtual clock; press the button. | The search leaves the slow value at `t_a + 30 / (0.97 x 30)` s, ±25 ms; that trial has `kept_rate: false`. |
| T-REQ-09 | fake | Each value at 5 fps (the fake still delivers); press the button. | The search fails at 20 s (±0.25 s) of the virtual clock; the old setting is set again. |
| T-REQ-10 | fake | Two fakes `ready`, A and B in `MANUAL`; apply B with `AUTO` only. During the search of B: a record start; an apply that changes the size of B. | Only B searches; A gets no set call; the rings of A and B get frames at each gate round during the search; the record start gets 409 that names B and `adjusting`; the apply gets 409. |
| T-REQ-11 | fake | A recording runs with two fakes. Press the button; send "Search again" for one camera; send an apply with `AUTO` for one camera. | Each gets 409; the fakes get no set call; the configs do not change. |
| T-REQ-12 | fake | Connect, reopen by a size change, reopen by a rate change, and "apply again" after a fail, each with one fake in `AUTO` held at -9 (`exposure_found_at_fps` 30). In the reopens, the request holds `exposure` -5. | Each start-up gives one set of -9 and no search; the reopens keep -9, not -5. |
| T-REQ-13 | fake | Three fakes `ready`: two `MANUAL`, one `AUTO`; press the button; then press it again while it runs. | Each camera searches one time and ends in `AUTO` with its own value; the response has `results` for the three; the second press gets 409. |
| T-REQ-14 | fake | Apply requests with `RECOMMEND`, `AUTO`, `MANUAL`, `CAMERA`; a new `CameraConfig()`. | `RECOMMEND` is stored as `AUTO`; `CAMERA` gets 422; the default is `MANUAL`, -7, `exposure_found_at_fps` `None`. |
| T-REQ-15 | fake | A spy on `set_controls` of the fake in each test of this table and in T-CAP-41. | No call with `ControlSetting(auto=True)` for exposure. |
| T-REQ-16 | fake | `ready` with `AUTO -9`, found at 30; apply `MANUAL -7`. | One live set of -7; no search; state `checking`, then `ready`; `exposure_found_at_fps` is `None`. |
| T-REQ-17 | fake | `live_set_faults`: the set of -9 returns an error; press the button. | The search fails; the last set is the old setting; `exposure_search_failed` names the error; the camera stays open. |
| T-REQ-18 | fake | Three fakes search; one gives device removed during its search. | That camera is `dead`, with no restore set; the two others end their searches; `camera_failures` holds it. |
| T-REQ-19 | fake | Cameras that fail the start-up rate check: `MANUAL` at 30, `AUTO` at 30, `MANUAL` at 60. | The reasons of 1.5a, to the character. |
| T-REQ-20 | fake | A fake without an exposure control; press the button. | The search fails at once with `Camera a1b2 has no exposure control`; the mode does not change. |
| T-REQ-21 | fake | OpenCV fake with the platform read as Linux, then as macOS; press the button; send "Search again"; apply `AUTO` on a running camera. | The button and "Search again" get 422 with the text of 1.5; the apply sets no value through a search. |
| T-REQ-22 | fake | "Search again" for one of three `ready` fakes; then the body with a camera ID that is not selected. | Only that camera searches; the others get no set call; the second request gets 422. |
| T-REQ-27 | ui-unit | `exposureRowText`: `MANUAL -8`; `AUTO -8` found at 30 with mode rate 30; `AUTO` with no held value; `AUTO` found at 30 with mode rate 60; found at 30 with mode rate 29.97; `too_slow` in `MANUAL` and in `AUTO`; an `add_light` warning. | `E:-8`; `E:-8 auto`; "Auto: not searched yet"; "Found at 30 fps: search again"; no "found at" text (one rate class); the two row texts of 1.5a, to the character; "Add light". |
| T-REQ-28 | ui-unit | `labelText` with the text `Camera a1b2: add light. ...` and the list where a1b2 is number 2, "Logitech C922"; a text with two IDs. | `Camera 2 · Logitech C922: add light. ...`; each ID replaced. |
| T-REQ-29 | ui-manual | The app with three cameras: the button, "Search again", a switch to Auto while not streaming, then a connect, then a restart of the app. | The button and link states and tooltips of 1.8; no search at the connect; "Auto: not searched yet"; after a search and a restart, the held value comes back from the stored settings and a connect sets it with no search. |
| T-REQ-23 | hardware | Windows. The C922, the C930e and the Kiyo Pro at 1280x720 30 fps, `ready` in `MANUAL -7`; press the button. | Each camera ends `ready` with its 10.2 check passed; no reopen (open count 1); each search under 20 s. The trials of each camera are recorded, so that the 10 frames to settle and the 30-frame window can be confirmed [Q4]. |
| T-REQ-24 | hardware | Windows. The C922 alone at 1280x720 60 fps in `MANUAL -7`; press the button. | The result keeps 58.2 fps or more, or the search fails with its text. The trials are recorded (the notes predict -7). |
| T-REQ-25 | hardware | Windows, `SKELLYCAM_HARDWARE_DARK=1`. Each camera at 30 fps; press the button. | No camera holds a value at which its 10.2 check fails; the flag `add_light` and the brightness at the brightest kept value are recorded, so that the user can set the limit of 64 [Q6]. |
| T-REQ-26 | hardware | Windows. The Kiyo Pro alone; press the button five times, with a close and a connect between. | Each search ends, and each connect reaches `ready` with the held value, or records its diagnostics; the Kiyo Pro wedge rule applies [cap 16.1]. |

## 2. Part 2: one frame rate for all cameras

### 2.1 The rule

- The camera list has one frame rate choice for all cameras, at the top [F1].
- It offers 30 fps and 60 fps. Nothing below 30 fps is offered [F3]. A rate above 60 fps is not
  offered [A14].
- The group runs at 60 fps only when each selected camera passed a real 60 fps rate check. Else the
  group runs at 30 fps, and the camera list says which camera could not [F2].
- A change of the rate is refused during a take [F4].

### 2.2 Where the value lives

- The UI writes the same value to `framerate` of each camera config in the apply request. The API
  keeps its field for each camera. No group field [Q13].
- The capture layer reads `config.framerate` of each camera, and the one-rate rule of D18
  ([cap 7.5]) already refuses a request with two rates (HTTP 422). Thus a consumer that sends its own
  configs (freemocap) gets the same rule, with no change of the API.
- The UI never sends -1 or 0. The API keeps -1 and 0 ("auto", D16) for other consumers, with no UI
  [A15]. The auto rate of D16 can give 60 to a camera that has no 30; the one-rate rule then refuses
  a mixed group, as today.

### 2.3 What an apply does when the rate changes

- A change of the rate reopens each camera whose rate changes, because `needs_reopen` gives true
  for a rate change [D31]. A reopen recreates the rings of that camera and repeats the warm-up and
  the rate check [cap 11.2]. Thus each selected camera reopens. A camera that is not selected does
  not open.
- A camera in `AUTO` reopens with its held value. No search runs [Q3]. A value found at another rate
  gets only the start-up rate check at the new rate (1.3a).

### 2.4 The real 60 fps check and the fall back

- When the user picks 60 fps while cameras stream, the UI sends the apply request at once. When no
  camera streams, the UI keeps the choice, and the next connect sends it.
- The check is the start-up rate check of [cap 10.1] at 60 fps, over the warm-up frames 6 to 90 of
  each camera, with the exposure of its config. No other probe runs [A16].
- The fall back [Q10]: when the group rate of a request is 60 fps, and a selected camera fails at the
  stage `set mode` or `rate check`, the main process applies the configs from before the request to
  each selected camera [A17]. For a new group, these are the configs of the request with `framerate`
  30. Each camera then reopens at 30 fps (`failed` cameras by "apply again" [cap 8.3]), with its held
  value and no search [Q3].
- The fall back runs one time. A camera that also fails at 30 fps stays `failed`.
- A failure at another stage (`open`, for example "in use by another program") gives no fall back.
  That camera is `failed`, and the others run at 60 fps [A17].
- The response is HTTP 200 with the configs at 30 fps and one warning item of the kind
  `rate_fallback`, for each camera that failed at 60 fps:
  `The group runs at 30 fps. Camera a1b2 measured 29.66 fps in its 60 fps mode at exposure -7.`
  The UI shows it with the label form, for example `Camera 2 · Razer Kiyo Pro measured ...` (1.8).
  `camera_failures` does not hold these failures, because the cameras run again.
- A camera in `AUTO` whose held value was found at another rate gets one more sentence [A9]:
  ` Its exposure -9 was found at 30 fps. To try 60 fps: set it to Manual with a shorter exposure, pick 60 fps, then switch it to Auto.`
  The switch to `AUTO` then runs the search at 60 fps (1.2 item 3). The search cannot run at 60 fps
  before the camera runs at 60 fps, because it needs the open stream at that rate.
- Measured: the Kiyo Pro gave 29.7 to 30.4 fps in its 60 fps mode at each exposure from -7 to -10
  [M `research/usb_cameras/docs/free_run_log_20261120.md` §9]. Thus a group with the Kiyo Pro falls
  back to 30 fps.

The cost: each camera closes (272 to 1,122 ms [cap 6.9]), opens (about 0.9 s on the Kiyo Pro, same
file), and counts 90 warm-up frames (1.5 s at 60 fps). That is about 3 to 4 s. A fall back adds about
5 s more (warm-up of 3 s at 30 fps). No search runs in either. The worst case is about 9 s. During
this time, the selector shows "Checking 60 fps…", and each camera tile shows its state (`starting`)
with no preview.

How the result is kept [A18]:

- The main process keeps nothing new. The `rate_fallback` items of the response are the result.
- The UI keeps the last `rate_fallback` text for the app run and shows it under the selector. It
  clears the text at the next pick of the rate or at a new detection.
- The 60 fps choice stays available after a fall back. A new pick runs the check again, for example
  after the user adds light or changes an exposure [Q9].

### 2.5 When the UI offers 60 fps

- 60 fps is enabled when each selected camera has a rate within 0.5 fps of 60 at its size in
  `supported_modes` (the mode choice of [cap 7.5]), and those rates are equal by D17.
- Else 60 fps is disabled. Its tooltip names each camera that has no 60 fps mode at its size, for
  example `Camera 3 · Logitech C930e has no 60 fps mode at 1920x1080`.
- A camera with 59.94 fps only at the size makes 60 fps disabled when another camera has 60, because
  D18 refuses 59.94 with 60. No new rate class for 59.94 and 60 [Q14].
- When 60 fps is the choice and the user ticks a camera that has no 60 fps mode, the UI sets 30 fps
  and shows the reason under the selector.

### 2.6 The one-rate rule and the warning `mixed_rate`

- The rule of D18 stays. It is the enforcement in the API.
- With the choice 30 fps, a camera that has 29.97 and no 30 gets 29.97 [D15]. The group can then mix
  29.97 and 30. The warning `mixed_rate` of U15 stays as it is.
- The selector shows "30 fps" for a group at 29.97 fps.

### 2.7 Refusals

- During a take: HTTP 409 by D36 [F4]. The UI disables the selector while a recording runs, with the
  tooltip `stopRecordingFirst`, as the "Update Cameras" button [UI 11-20].
- While a camera is `starting`, `waiting` or `adjusting`: HTTP 409 [agent 45 of cap]. The UI disables
  the selector in that time.

### 2.8 UI

- `CameraConfigSidebarPanel.tsx`: a `SegmentedControl` "30 fps | 60 fps" in the header, before the
  stream buttons. It uses the house components of the header.
- The store slice gets one action that sets `framerate` of each camera config (desired) to the
  choice. The default choice is 30. `createDefaultCameraConfig` sets `framerate: 30` [A15].
- A pure function `rateChoice(cameras)` in a new file `skellycam-ui/src/store/slices/cameras/rate-choice.ts`
  gives `{can60: boolean, reasons: string[]}` from the selected cameras, their sizes and their
  `supported_modes`. The reasons use the label form.
- The per-camera rate control `CameraConfigFramerate.tsx` is not used by any rendered component. It
  goes [A15].

### 2.9 Changes to windows-capture.md

Change to section 7.5, item "Auto rate": add "The UI does not send the auto rate. It writes one rate,
30 or 60, to each camera (`camera-requests.md` 2.2). The API keeps -1 and 0 for other consumers."

Change to section 7.5: add the item "**Fall back to 30 fps**: a request whose group rate is 60 fps,
in which a selected camera fails at `set mode` or `rate check`, falls back to the configs from before
the request, one time (`camera-requests.md` 2.4)."

Change to section 8.2: add the row "| `failed` at 60 fps (stage `set mode` or `rate check`) | the
fall back of `camera-requests.md` 2.4 | `starting` at 30 fps |".

Change to section 11.3: the kind `rate_fallback` (see 1.10).

Change to section 16.2, T-CAP-20 item (3): "apply a request that gives all three cameras the rate
60, where each fake delivers 60."

### 2.10 Tests

| ID | Kind | Set-up | Pass criterion |
|---|---|---|---|
| T-REQ-30 | fake | Three fakes `ready` at 30, each with 60 in its modes and delivering 60; apply 60 for each. | Each camera reopens one time; the group rate is 60; no `rate_fallback`; each is `ready`. |
| T-REQ-31 | fake | As T-REQ-30, but one fake delivers 29.66 fps in its 60 mode. | Each camera reopens two times (60, then 30); the response has configs at 30 and one `rate_fallback` item for that camera with "29.66"; `camera_failures` is empty; each is `ready`. |
| T-REQ-32 | fake | As T-REQ-31, with the slow camera in `AUTO` held at -9, found at 30. | At 60 it gets one set of -9 and no search; in the fall back, one set of -9 and no search; its `rate_fallback` text has the sentence of 2.4 with "-9" and "30 fps". |
| T-REQ-33 | fake | As T-REQ-30, but one fake is in use at the reopen. | No fall back; that camera is `failed`, stage `open`; the two others run at 60. |
| T-REQ-34 | fake | As T-REQ-31, and the slow fake also fails at 30. | One fall back only; that camera is `failed`, stage `rate check`, at 30; the others run at 30. |
| T-REQ-35 | fake | A new group (no group runs) connects at 60; one fake delivers 29.66 at 60. | The group runs at 30; the response has `rate_fallback`. |
| T-REQ-36 | fake | A recording runs at 30; apply 60. | 409; nothing reopens. |
| T-REQ-37 | fake | A camera is `adjusting`; apply 60. | 409; the detail names the camera and `adjusting`. |
| T-REQ-41 | fake | A fake in `AUTO` held at -7, found at 30, delivering 60 at -7; apply 60; then press the button. | The 60 check passes with no search; the config keeps `exposure_found_at_fps` 30 until the search; after the search it is 60. |
| T-REQ-38 | ui-unit | `rateChoice`: (1) all with 60 at their sizes; (2) one with 60 at 1280x720 only and set to 1920x1080; (3) one with 59.94 and one with 60; (4) no selected camera. | (1) `can60` true; (2) false, the reason has the label form and 1920x1080; (3) false; (4) false. |
| T-REQ-39 | ui-manual | The app with the C922 and the Kiyo Pro streaming at 30; pick 60; pick 60 again. | "Checking 60 fps…" shows; then 30 fps is the choice, with the `rate_fallback` text for `Camera n · Razer Kiyo Pro` under the selector; 60 stays available, and the second pick runs the check again. |
| T-REQ-40 | hardware | Windows. The C922 and the C930e at 1280x720 in `MANUAL -7`; pick 60, then 30. | The result (60 or the fall back) and the time of each change are recorded; no camera stays `failed`. |

## 3. Part 3: USB link label

### 3.1 The rule

- Each camera in the camera list has a label `USB 2` or `USB 3` next to its name [L1].
- The label shows the speed of the link of the camera now. A USB 3 camera in a USB 2 port shows
  `USB 2` [L2].
- The value is a new field of the detection result [L3]. Each operating system has a test [L4].
- A link speed that cannot be read shows `USB ?`. A virtual camera shows the label `virtual` [Q12].
- Later, not now: a click on the label opens a diagram of the cameras on their USB controllers [L5].
  Section 3.8 names it as future work only.

### 3.2 The field

`CameraDeviceInfo` gets [A19]:

```python
usb_link: Literal["USB 1", "USB 2", "USB 3", "unknown"] = "unknown"
```

- `USB 3` covers each SuperSpeed link (5, 10 and 20 Gbit/s). `USB 2` is high speed (480 Mbit/s).
  `USB 1` is low or full speed (1.5 or 12 Mbit/s).
- `unknown`: not a USB camera (a built-in PCI or MIPI camera, a network camera), a virtual camera, a
  lookup that failed, or a system with no lookup. A failed lookup never fails the detection.
- A virtual camera keeps `usb_link: "unknown"`. The field gets no value `virtual`, because the
  detection result already has `virtual: true` [W5], and the UI reads that flag. This is the smallest
  change [A20].
- The name is `usb_link`, not the sfn26 `usb_version`: the value is the speed of the link now, not the
  USB version of the device. The values are the sfn26 values, with `unknown` in place of `None`, so
  that the UI shows the value as it comes.
- The lookup runs in the detection, one time for each camera. The value is the speed at the time of
  the detection. A camera that moves to another port is a new device at the next detection [cap 7.2].

### 3.3 What sfn26 does, and its limits

[sfn26 `skellycam/core/device_detection/usb_connection.py`], called by `detect_available_cameras` for
each camera:

- Windows: it parses the device path (`\\?\usb#vid_xxxx&pid_xxxx...#<instance>#{guid}`) to the device
  instance and the USB IDs. It finds the device node (`CM_Locate_DevNodeW`) and walks up at most four
  parents (`CM_Get_Parent`). At each parent, it tries to open the hub interface
  (`GUID_DEVINTERFACE_USB_HUB`) with `CreateFileW`. At the hub, it reads the port number of the child
  (`CM_DRP_ADDRESS`) and sends `IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX` for the port. It checks
  that the USB IDs at the port are those of the camera. Then it sends
  `IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX_V2`: the flag "operating at SuperSpeed or higher"
  gives `USB 3`; else the legacy speed byte gives `USB 1` (0, 1), `USB 2` (2) or `USB 3` (3).
  - Limits: a path that is not `usb#...` gives `None` (built-in, virtual). The port number comes from
    `CM_DRP_ADDRESS`; the USB ID check catches a wrong address but then gives `None`. No admin rights
    are needed. The research script [M `research/usb_cameras/bandwidth/win_usb_topology.py`] finds
    the same speed in another way: it enumerates each hub and maps the driver key of each port to
    the device instance. It also notes that the legacy speed byte cannot express SuperSpeed, so the V2
    flags decide. These connection-information calls go to the hub driver only. The research script
    also reads descriptors (traffic to the camera); the label must not [A21].
  - The Media Foundation link of this branch has the same form as the DirectShow path, so the parse
    applies [NV for the four test cameras].
- Linux: from `/sys/class/video4linux/videoN/device`, it resolves the link and walks up the parents
  to the first folder with a file `speed` (Mbit/s). 5000 or more gives `USB 3`, 480 or more `USB 2`,
  else `USB 1`. Limits: a non-USB camera has no `speed`, so `None`. Not run on hardware by this team
  [NV].
- macOS: the AVFoundation unique ID of a USB camera starts with `0x` and the 8 hex digits of its USB
  location ID. It runs `ioreg -a -r -c IOUSBHostDevice -d 1` (time limit 5 s) and finds the device
  with that `locationID`. `USBSpeed` 4 or more gives `USB 3`, 3 gives `USB 2`, 1 or 2 gives `USB 1`.
  Limits: sfn26 states "Not yet verified on Mac hardware"; a built-in or Continuity camera gives
  `None`. On this branch, `cv2_enumerate_cameras` gives the unique ID as `path` on macOS
  (`macos_backend.py`), so the parse applies [NV].
- On each system, an exception gives `None`, and the detection goes on.

### 3.4 The rule of this spec

- Port the sfn26 module as `skellycam/core/device_detection/usb_link.py`, with the values of 3.2
  [A22].
- Windows: the lookup runs in the detection child of [cap 7.1], as a bounded call with a limit of
  1 s for each camera. A call past the limit gives `unknown`, and the child ends hard at its end as
  [cap 7.1] says for a hang [A23]. The hub calls are a seam (one function for each IOCTL), so that a
  test can give the bytes.
- Linux and macOS: the functions of sfn26, called in `detect_available_cameras`.
- A virtual camera gets `unknown` with no lookup.

### 3.5 What the label shows

- The camera list shows a camera only after a detection returns. The label is part of that row. Thus
  before the first detection ends there is no row and no label.
- While a new detection runs, each row keeps its old label. The new result replaces it.
- `USB 3`, `USB 2`, `USB 1`: the value, as a chip after the name, with the tooltip "Connected at USB 3
  speed (5 Gbit/s or more)", "Connected at USB 2 speed (480 Mbit/s)" or "Connected at USB 1 speed
  (12 Mbit/s or less)".
- `unknown` on a camera that is not virtual: the chip `USB ?`, with the tooltip "SkellyCam could not
  read the USB link of this camera" [Q12].
- A virtual camera (`virtual: true`): the chip `virtual`, with the tooltip "A virtual camera: it has
  no USB link" [Q12].
- A pure function `linkChip(deviceInfo)` gives the chip text and the tooltip.

### 3.6 API and UI changes

- `CameraDeviceInfo.usb_link` (3.2). `POST /camera/detect` returns it. No other endpoint changes.
- `cameras-types.ts`: `DetectCamerasResponse.cameras[]` gets `usb_link` and `virtual`;
  `Camera.deviceInfo` gets `usbLink` (it has `virtual` already).
- `CameraTreeItem.tsx`: the chip of 3.5 after the name, in the "Camera info row".

### 3.7 Changes to windows-capture.md

Change to section 1.3: delete the item "The USB link display" from the D45 item. The item becomes
"The Windows event-log check [D45]. The USB link label is in `camera-requests.md` part 3
(2026-11-20)."

Change to section 7.1: add "`usb_link` is the speed of the USB link now (`camera-requests.md` 3.2).
The lookup runs in the detection child, bounded at 1 s for each camera."

Change to section 16.5, row D45: "T-REQ-50 to T-REQ-59 (the USB link label of `camera-requests.md`)".

### 3.8 Future work (not now)

A click on the label opens a diagram of the cameras on their USB controllers and hubs [L5]. The
research script finds the controller of each hub from the parent chain (the first `PCI\` parent).
No spec and no test now.

### 3.9 Tests

| ID | Kind | Set-up | Pass criterion |
|---|---|---|---|
| T-REQ-50 | fake | Linux function with a `sysfs` tree in a temporary folder: `speed` 1.5, 12, 480, 5000, 10000, 20000; a camera with no `speed`; `/dev/video9` with no folder. Runs on each OS. | `USB 1`, `USB 1`, `USB 2`, `USB 3`, `USB 3`, `USB 3`, `unknown`, `unknown`. |
| T-REQ-51 | fake | macOS function with a stand-in `ioreg` plist: location IDs with `USBSpeed` 4 and 3; the unique ID `FaceTime HD Camera`; an `ioreg` call that times out. Runs on each OS. | `USB 3`, `USB 2`, `unknown`, `unknown`. |
| T-REQ-52 | fake | Windows parse: a Media Foundation link with `#{e5323777-f976-4f5b-9b55-b94699c46e44}\global`; a `root#image#` link. Runs on each OS (pure). | The instance, `vid` and `pid` of the link; the second gives `unknown`. |
| T-REQ-53 | fake | Windows decode with the IOCTL seam: V2 flag 1 set; flag clear and speed byte 2; speed byte 0; USB IDs at the port that differ from the camera. Runs on each OS (pure). | `USB 3`, `USB 2`, `USB 1`, `unknown`. Only the two connection-information codes are sent; no descriptor request. |
| T-REQ-54 | fake | Detection with a lookup that raises, and with a virtual camera. | The detection returns each camera; the field is `unknown` for both; the virtual camera has `virtual: true` and gets no lookup call. |
| T-REQ-55 | fake | Windows only [U18]: the detection child with a lookup that hangs. | That camera has `unknown`; the detection returns within the limit of [cap 7.1] plus 2 s. |
| T-REQ-59 | ui-unit | `linkChip` with `USB 3`, `USB 2`, `USB 1`, `unknown`, and `unknown` with `virtual: true`. | The chips `USB 3`, `USB 2`, `USB 1`, `USB ?`, `virtual`, with the tooltips of 3.5. |
| T-REQ-56 | hardware | Windows. The Kiyo Pro in a USB 3 port, then the same Kiyo Pro in a USB 2 port (or behind a USB 2 hub); the C922 and the C930e. Compare with the output of the research script. | `USB 3`, then `USB 2`; `USB 2` for the C922 and the C930e; each value agrees with the speed of the research script. |
| T-REQ-57 | hardware | Linux and macOS (phase 0, the user): the same cameras and ports as T-REQ-56. Compare with `lsusb -t` (Linux) or `system_profiler SPUSBDataType` (macOS). | Each value agrees with the speed that the system tool gives. |
| T-REQ-58 | ui-manual | The app after a detection, and during a second detection, with a virtual camera present. | The chips and tooltips of 3.5; the chip `virtual` on the virtual camera; old chips stay during the second detection. |

## 4. Choices of the agent

Each choice is [An]. [ADR-Y6F6](../decisions/entries/Y6F6-camera-request-choices.md) holds the same
list. The choices of the first draft that the user decided are in section 5.

1. The early decision of 10.2 for each value, with 30 frames (1.3).
2. The time limit of a search is 20 s (1.3).
3. The config keeps `exposure_mode: "AUTO"` with the held value in `exposure`, and the new field
   `exposure_found_at_fps` (1.3, 1.3a).
4. The control thread does the sets and the loop measures; the read each second waits (1.3).
5. Each camera searches on its own, not one value on all cameras at a time; in the gate, the 10th and
   40th frames are the first taken frames at or after those counts (1.3).
6. The UI copies the held value from each response into its stored settings (1.3a).
7. A camera in `AUTO` with no held value starts at its `exposure` value (-7 for a new camera); its
   row offers the search (1.3a).
8. A reopen of a running camera keeps the held value of its current config, not the value of the
   request (1.3a).
9. A held value found at another rate: the row says "Found at N fps: search again"; the
   `rate_fallback` text tells how to reach 60 fps (1.3a, 2.4).
10. `RECOMMEND` in a request is read as `AUTO` (1.5).
11. The endpoint `POST /camera/group/exposure/auto` with the optional body `camera_ids`, its
    response, its codes, the status field `exposure_search`, and the warning kinds `add_light` and
    `exposure_search_failed` with their texts (1.5).
12. The one set of texts of a slow camera: the `MANUAL` reason adds "or lower the exposure", and the
    `AUTO` row text "Too slow at this exposure: add light, then search again" (1.5a).
13. Server texts keep camera IDs; the UI replaces each listed ID with the label form (1.8).
14. No rate above 60 fps is offered (2.1).
15. The UI never sends -1 or 0; the API keeps them; `CameraConfigFramerate.tsx` goes; the UI default
    is 30 (2.2, 2.8).
16. The real 60 fps check is the start-up rate check at 60 fps; no other probe (2.4).
17. The fall back runs only for the stages `set mode` and `rate check`, with the warning
    `rate_fallback` (2.4).
18. Only the UI keeps the last fall back text, for the app run (2.4).
19. The field `usb_link` with the values `USB 1`, `USB 2`, `USB 3`, `unknown` (3.2).
20. A virtual camera keeps `usb_link: "unknown"`; the UI shows `virtual` from the flag `virtual`
    (3.2, 3.5).
21. The label sends no request to the camera: only the connection-information calls at the hub
    (3.3).
22. Port the sfn26 module as `skellycam/core/device_detection/usb_link.py` (3.4).
23. On Windows, a bounded lookup of 1 s for each camera in the detection child (3.4).

## 5. Decisions of the user of 2026-11-20

The user answered the 14 questions of the first draft on 2026-11-20
([ADR-C4FZ](../decisions/entries/C4FZ-camera-requests.md)). The body of this spec applies each one.

1. **Q1.** SkellyCam never turns on the auto exposure of the camera, also not at the start-up (1.1,
   1.6).
2. **Q2.** A link "Search again" in the camera settings runs the search for that one camera, beside
   the button for all cameras (1.2, 1.8).
3. **Q3.** The search runs only when the user asks: the button for all cameras, "Search again" for
   one camera, or a switch of a camera to Auto. A connect, a reopen for a size or rate change, and
   "apply again" use the held value and do not search. The user accepted the recommendation of the
   supervisor, not of the first draft (1.2, 1.3a, 2.3, 2.4).
4. **Q4.** The search waits 10 frames after each set, takes the brightness from the 10th frame, and
   measures the rate over the next 30 frames. These are starting values; a camera run confirms them
   (1.3, T-REQ-23).
5. **Q5.** The one-step-darker offset is skipped when the darker value did not keep the rate (1.3).
6. **Q6.** "Add light" shows when the brightest value that kept the rate gives a mean below 64 of
   255. The search still holds its result. A camera run in a dim room sets the limit (1.3,
   T-REQ-25).
7. **Q7.** The new state `adjusting` (1.4).
8. **Q8.** The texts of a slow camera of the first draft (1.5a).
9. **Q9.** After a fall back to 30 fps, the 60 fps choice stays available, and a new pick runs the
   check again (2.4).
10. **Q10.** The main process returns the whole group to 30 fps, one time, and says which camera
    could not hold 60 fps (2.4).
11. **Q11.** On Linux and macOS, the forced camera auto exposure of today stays until phase 7, and
    the mode choice and the button are not offered there. The user was told that this is an
    exception to his rule until phase 7 (1.1, 1.7).
12. **Q12.** A link speed that cannot be read shows `USB ?`. A virtual camera shows `virtual` (3.5).
13. **Q13.** The UI writes the one rate into each camera config; no new group field (2.2).
14. **Q14.** A group with 59.94 fps against 60 fps is not offered 60 fps (2.5).

## 6. Other decisions of the same day that this spec must agree with

These decisions of the user of 2026-11-20 on the UI were relayed by the supervisor. No entry on this
branch holds them yet. This spec agrees with them:

- A `too_slow` camera keeps its tile and counts as streaming. Its row says "Too slow at this
  exposure: lower the exposure" (1.4, 1.5a).
- The "Update Cameras" button is disabled during a recording (1.8, 2.7).
- Camera failure reasons will get a fixed failure code beside the text. Not accepted yet (1.5).
- The label form for a camera everywhere in the UI is `Camera <list number> · <name>` (0, 1.8).

## 7. What must be tried on real cameras before the code is trusted

1. The 10 frames to settle and the rate window of 30 frames, on each camera (T-REQ-23) [Q4].
2. The limit of 64 for "Add light", in a dim room (T-REQ-25) [Q6].
3. The C922 at 60 fps through the search: the notes measured -6 to -10 only; -12, -11 and -5 are not
   known (T-REQ-24).
4. A held value found at 30 fps at a pick of 60 fps, and the way to 60 fps of 2.4 (T-REQ-40, with
   one camera in `AUTO`).
5. The C922 with the Kiyo Pro open at 60 fps: one test gave 46.5 fps over frames 6 to 90 and 58.7 fps
   over 10 s (not repeated). The start-up check can then fail a camera that reaches 60 fps later.
6. The Kiyo Pro under five searches with closes and connects between (T-REQ-26, the wedge rule).
7. The USB link of each test camera through its Media Foundation link, and the Kiyo Pro in a USB 2
   port (T-REQ-56).
8. The Linux and macOS link lookups (phase 0, T-REQ-57).
9. Phase 7, not before: the Linux V4L2 exposure units, and whether macOS sets exposure at all.
