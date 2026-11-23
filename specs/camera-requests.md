# Camera requests of 2026-11-20: exposure, one frame rate, USB link label

Status: proposed by an agent on 2026-11-20, then revised on the same day with the answers of the
user to its 14 questions (section 5). Revised again on the same day with the decisions G1 to G9 of
the user (section 5a): Auto now searches at each open. The decisions of the user are in
[ADR-JK79](../decisions/entries/JK79-exposure-search-at-each-open-and-camera-requests.md), which
supersedes [ADR-C4FZ](../decisions/entries/C4FZ-camera-requests.md) and keeps each item of C4FZ that
G1 to G9 do not change. The choices of the agent that are still open are in
[ADR-Y6F6](../decisions/entries/Y6F6-camera-request-choices.md) and
[ADR-4Z7T](../decisions/entries/4Z7T-choices-after-the-search-at-each-open.md). The answers of the user
on some choices of 4Z7T are in
[ADR-379P](../decisions/entries/379P-answers-on-the-choices-after-the-search-at-each-open.md)
(section 5b). [ADR-6QFG](../decisions/entries/6QFG-pause-in-the-ui-search-on-native-sources-and-restore-at-close.md)
supersedes 379P: it keeps H1 to H7 and adds K1 to K4 (section 5c).
This spec is the one definition of the exposure search (its algorithm, its states, its names and its
time limits), of the fall back to 30 fps (2.4) and of the USB link lookup (part 3).
`unix-capture.md` and `certify.md` point to it. This file holds the spec
text and the test list only. The user accepts them before any code is written. The changes of this
spec to [`windows-capture.md`](windows-capture.md) and [`recorder.md`](recorder.md) are applied in
those specs (1.10, 2.9, 3.7, 8.2) [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md).

## 0. How to read this spec

Marks:

- **[En]**, **[Fn]**, **[Ln]**: decision n of the user on 2026-11-20 on exposure (E), the frame rate
  (F) and the USB link label (L) ([ADR-C4FZ](../decisions/entries/C4FZ-camera-requests.md)).
- **[Qn]**: the answer of the user to question n of the first draft, 2026-11-20 (section 5,
  [ADR-C4FZ](../decisions/entries/C4FZ-camera-requests.md)). It is a decision.
- [ADR-JK79](../decisions/entries/JK79-exposure-search-at-each-open-and-camera-requests.md) keeps
  each [En], [Fn], [Ln] and [Qn] with its ID, except these: E3 (the search runs only when the user
  asks), E5, the text of E7, Q3 and Q8. [Gn] changes them.
- **[Gn]**: decision n of the user of 2026-11-20, second set (section 5a,
  [ADR-JK79](../decisions/entries/JK79-exposure-search-at-each-open-and-camera-requests.md)).
- **[An]**: choice n of the agent (section 4). The user decides it.
- **[Bn]**: choice n of the agent after the decisions [Gn] (section 4,
  [ADR-4Z7T](../decisions/entries/4Z7T-choices-after-the-search-at-each-open.md)). The user decides
  it.
- **[Hn]**: answer n of the user on the choices [Bn], 2026-11-20 (section 5b,
  [ADR-379P](../decisions/entries/379P-answers-on-the-choices-after-the-search-at-each-open.md)).
  [ADR-6QFG](../decisions/entries/6QFG-pause-in-the-ui-search-on-native-sources-and-restore-at-close.md)
  keeps H1 to H7. K1 replaces H8.
- **[Kn]**: decision n of the user of 2026-11-20, third set (section 5c,
  [ADR-6QFG](../decisions/entries/6QFG-pause-in-the-ui-search-on-native-sources-and-restore-at-close.md)).
- **[ux x.y]**: section x.y of [`unix-capture.md`](unix-capture.md). **[cert x.y]**: section x.y of
  [`certify.md`](certify.md).
- **[UI 11-20]**: a decision of the user of 2026-11-20 on the UI, relayed by the supervisor, that
  this spec must agree with. [ADR-F2KY](../decisions/entries/F2KY-rulings-of-the-user-after-the-third-consistency-check.md) holds it, or cites the entry that holds it (section 6).
- **[cap x.y]**: section x.y of [`windows-capture.md`](windows-capture.md). **[Dn]**, **[Un]**,
  **[Wn]**: the marks of that spec.
- **[M file]**: measured; the file holds the result. Each such file is on branch `dom/research` at
  commit 56d2b907d. It is not on this branch.
- **[sfn26 file]**: the file on the branch `sfn26` of the upstream repository, read on 2026-11-20.
- **[NV]**: not verified on a camera.

The tests have the IDs T-REQ-nn. The kinds are those of [cap 16.1], plus **ui-unit**: a test of a
pure TypeScript function that runs with `node --experimental-strip-types --test`, as the script
`test:recording-shutdown` of `skellycam-ui/package.json`. Step 1 adds the script `test:cameras`:
`node --experimental-strip-types --test "src/store/slices/**/*.test.ts"`. It runs each ui-unit test of
this spec and the existing `camera-labels.test.ts`, which runs nowhere today. Step 1 also adds a CI
step `npm run test:cameras` to each job of `.github/workflows/player.yml` that runs
`npm run test:player:unit`, and adds `skellycam-ui/src/store/slices/**` and
`specs/camera-requests.md` to the paths of its `push` and `pull_request` triggers [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md). **ui-manual** is a check that a person makes
in the running app.

In the UI, each text that names a camera uses the form `Camera <list number> · <name>`
[UI 11-20]. The texts of the server name a camera by its ID, as today. Section 1.8 gives the rule
that joins the two.

This spec uses British spelling.

## 1. Part 1: exposure

### 1.1 The rule

- The UI and the API have two exposure modes: `MANUAL` and `AUTO` [E1].
- `MANUAL`: the camera uses the value of the config. It never searches [G1]. The unit stays log2 of
  seconds (-7 = 1/128 s) [D35].
- A route with no time unit (a macOS route whose `exposure_unit` is `ev`, `native` or `native-data`
  [ux 4.4.6]): `exposure` holds the step index 0 to 7, 0 the darkest and 7 the brightest. Manual then
  shows eight plain steps with no time label, for now (item 10 of [ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)). A value below 0 in a request
  is a log2 value: the source sets the step `v + 12`, clamped to 0 to 7, and the config stores that
  step. The status reports `exposure_unit`, so that a client knows the scale [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md).
- The `MANUAL` clamp: a `MANUAL` value above -5 becomes -5 (`MAX_MANUAL_EXPOSURE` of
  `camera_config.py`, applied in `CameraGroupManager.create_or_update_camera_group`; item 5 of
  [ADR-6T78](../decisions/entries/6T78-choices-of-the-sfn26-integration.md)). It applies only to a
  route whose unit is a time. Until step 7b no route without a time unit exists, so the clamp of the
  main process stays as it is. Step 7b moves the clamp into the source, which knows its route, and a
  step value 0 to 7 is then never clamped [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).
  Each clamp gives the warning `exposure_clamped` of 1.5 in the response of the apply request and in
  the status of the camera [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md).
- `AUTO`: SkellyCam finds a manual value with the exposure search of 1.3. The search runs at each
  open of the camera, at a change of the frame rate and when the user asks (1.2) [G1]. Each search is
  one shot on the open stream. SkellyCam holds its value until the next search. The camera control
  stays in its manual setting at all times [E1, E3, G4].
- The auto exposure of the camera is never a mode. On a native source (Media Foundation, V4L2,
  AVFoundation), SkellyCam never turns it on, also not at the start-up [E1, Q1, K2].
- One exception: the restore of the controls at the close of a camera [ux 4.7] can turn the auto
  exposure of the camera on again. It is not a mode, because the camera is then closed [K4].
- Exception for now: on Linux and macOS, the OpenCV source leaves the exposure to the camera. This is
  an exception to the rule above [Q11], accepted for now as a known limit of the OpenCV path (item 9
  of [ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)). Section 1.7 gives the detail. The native sources of Linux and macOS search as on Windows [K2].
- A camera with no working exposure control has no mode: no `MANUAL` and no `AUTO` (1.9) [K3].
- The sfn26 label "Recommend" and the sfn26 `AUTO` (the auto exposure of the camera) go away [E1].
- The exposure of a camera never changes during a take [E3, G4]. Each request that changes it during
  a take is refused (1.5).
- A new camera starts in `AUTO` [G1]. Its first value is -7, the value of the open before its first
  search (1.3a) [A7]. This replaces the default `MANUAL` -7 of E5.

### 1.2 When the search runs

A camera in `AUTO` runs the search in these cases [G1]:

1. (a) At each open of the camera: a connect; "Update Cameras" when it adds or reopens the camera; a
   reopen for a change of size; "apply again" of a `failed` or `dead` camera; the reopen of the fall
   back to 30 fps of 2.4. The search runs after the warm-up, in the gate (1.3b).
2. (b) When the user changes the frame rate. The camera reopens at the new rate, and the search runs
   before the rate check judges the camera (1.3b, 2.3).
3. (c) When the user asks, on the open stream:
   - The user presses the button "Auto-set exposure (all cameras)" [E4]. Each selected camera that
     streams goes to `AUTO`, and each one runs the search.
   - The user presses the link "Search again" in the settings of one camera [Q2]. That camera runs
     the search.
   - The user switches a camera that streams from `MANUAL` to `AUTO` (an apply request). That camera
     runs the search.

A camera in `MANUAL` never searches [G1]. The search itself never reopens a camera. These events do
not run it:

- an apply request with the same config (`AUTO` with `AUTO`), which has no effect [cap 8.3];
- a live change of another control;
- the read of the controls each second.

A switch to `AUTO` while the camera does not stream only changes the stored config. The next open
searches (a).

### 1.3 The search

The search replicates `recommend_exposure` of [sfn26 `skellycam/core/camera_group/tasks/recommend_exposure.py`],
with the guard of the frame rate [E2]:

1. The values are -12 to -5, in that order [E6]. On a route with no time unit (1.1), the values are
   the steps 0 to 7, in that order: the step k takes the place of the value k - 12. The offset of item
   4 is then one step down, and the result is a step.
   The search tries only the values that are in the exposure range of the camera, in the same order.
   The source reads the range before the first set of the open (`exposure_range()`, which gives
   `(min, max, step)` or None on each source; on Media Foundation
   `IAMCameraControl::GetRange`). A value that is not on the step grid of the range (min plus a multiple
   of the step) is left out. A source that gives no range gets each value, with the rule of item 6. Reason: each test camera
   is outside -12 (the C922, the C930e and the Kiyo Pro have -11 to -2; the generic camera has -7 to 3), and
   Media Foundation gives the value to the camera as it is: the set fails, or the camera clamps it [ADR-GEH0](../decisions/entries/GEH0-choices-of-code-step-3.md).
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
   7. A borderline value is measured again one time before the search drops it (Q522 of the user,
      "re-measure a borderline value"). A value is borderline when it does not keep the rate (item 5
      or item 6) and its measured rate is not more than 10 % below the mode rate (`measured >= 0.90 x r`).
      The window then grows to 60 intervals from frame a, with no new set and no new frames to settle:
      the rate from frame a to frame `s_a + 60` decides, with the early decision of item 6 for 60
      frames (`now - t_a > 60 / (0.97 x r)`). The frame that ended the first window (frame b, the last
      frame before the deadline, or a frame that came after the deadline) stays in the longer window.
      The rate of the whole window is the `measured_fps` of the trial, and the rate of the first window
      is its `first_fps` (1.5). A miss of the longer window drops the value. The search logs each
      measurement again. Reason: on real cameras one trial read 28.1 fps at
      a value that kept 30 fps at the next open (the C922 at -7 in one of five opens; the Kiyo Pro at -8
      in four of five), so the chosen value changed between opens. 28.1 fps is the reading of the early
      decision when frame `s_a + 30` comes a little late (29 intervals in `30 / (0.97 x 30)` s). The
      margin of 10 %, the one repeat and the window of 60 intervals are proposed
      [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md). The longer window keeps a value
      that holds 30 fps after one late frame, and it does not give a slow value a second chance: with
      the arrival jitter of T-REQ-80, a value at 29.0 fps is kept in 11.8 % of the runs, 11.3 % with no
      repeat (a second window that decides alone gave 23.8 %). A value whose window missed two frames
      (28.1 fps over 30 intervals, 29.0 fps over 60) is dropped.
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
6. The search fails in these cases. A failed search sets the old value and the old
   `exposure_found_at_fps` again [E6]. The mode stays `AUTO`: `AUTO` is the stored mode, also after a
   failed switch from `MANUAL` [ADR-GEH0](../decisions/entries/GEH0-choices-of-code-step-3.md):
   - no value of item 1 is in the range of the camera, or, with no range, no value could be set
     (`no-value-in-range`) [ADR-GEH0](../decisions/entries/GEH0-choices-of-code-step-3.md);
   - with no range (a source that gives none, for example OpenCV): a value whose set returns an error
     or whose read-back differs is not a failure. The search skips it as not supported by the camera,
     logs it, lists it in `skipped` of its result, and goes on with the next value. With a range, such a
     set inside the range fails the search as below [ADR-GEH0](../decisions/entries/GEH0-choices-of-code-step-3.md) (a choice of the supervisor);
   - no value kept the rate;
   - a set call returned an error, or its read-back differed from the value (with a range);
   - the last set (the result, or the held value again) gave no reply within the limit of a bounded call
     and 1 s (`set-failed`) [ADR-GEH0](../decisions/entries/GEH0-choices-of-code-step-3.md);
   - the search took more than its limit of 20 s [A2];
   - the group closed the camera, or the camera was unselected. Then the camera closes, and the
     search sets no value: the restore of the close sets the controls [ux 4.7] (1.9).
7. A hang of a set call is a hang of [cap 6.6]: the camera fails or dies, and the process ends hard.
   A stall of 2 s is a stall of [cap 9.5]. The search then has no restore step.

   This replaces the restore of `_recommend` that came from sfn26 (`camera_loop.py`, about lines 298
   to 324; [ADR-EQY4](../decisions/entries/EQY4-base-the-work-on-upstream-sfn26-without-rust.md)). That
   code set back the read state, with `before.auto`, on each exception, also on `_Stop`. The new
   rule: a failed search sets the held value again as a manual value (item 6); a camera that closes
   gets no set from the search; no exposure call of the search or of an open has `auto=True`. Only the
   restore at the close may set `auto=True` [ux 4.7] [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).
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
- A measurement again (1.3 item 2.7) adds about 1.0 s at 30 fps (about 0.5 s at 60 fps) for each
  borderline value; a 15 fps value is not borderline, so the worst case above does not change.
  On the lab cameras a search of 7 values took about 16 s, so a search with more than about three
  borderline values can pass 20 s and fail with `timed-out`. The limit stays 20 s. A camera run
  records how often a value is measured again (T-REQ-23, T-REQ-26)
  [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md).

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
  the UI (the desired config of each camera). After each response that carries configs (the button,
  "Search again"), the UI copies `exposure` and `exposure_found_at_fps` of each camera in `AUTO` into
  its desired config [A6]. For a search at an open, no response carries the result: the UI copies
  it from the live state (1.3b) [H1, B14]. Thus the held value is kept across a close and across a
  restart of the app.
- At an open, a camera in `AUTO` sets its held value as a manual value at step 5 of [cap 9.1]. Then
  it searches after the warm-up (1.3b) [G1]. The held value is set inside the search values: the values of
  1.3 item 1 that are in the exposure range of the camera. A held value that is not one of them is set at
  the nearest of them. When the range has no search value, a held value outside the range is set at the
  nearest end of the range. The config stores the read-back value. Examples: a new camera (-7) on a camera
  whose range starts at -6 opens at -6, then searches -6 and -5 [ADR-GEH0](../decisions/entries/GEH0-choices-of-code-step-3.md).
  A held value of -1 on a camera with the range -11 to -2 opens at -5, not at -2: -2 is a 250 ms exposure
  (4 fps), and the warm-up fails (seen on a real camera) [ADR-QJH6](../decisions/entries/QJH6-choices-of-the-fix-lane.md).
- The held value is not a start point of the search: the search tries -12 to -5 in order [E6]. The
  held value has two uses [B2]:
  - the warm-up and the first frames of the preview are near the last result;
  - a failed search sets it again (1.3 item 6).
- A camera in `AUTO` with no held value (`exposure_found_at_fps` is `None`) opens at its `exposure`
  value: -7 for a new camera [A7]. Then it searches, as each camera in `AUTO` [G1]. Until a search
  finds a value, its row says "Auto: no value found yet" (1.8) [B9].
- A reopen of a running camera (size or rate) uses the held value of its current config, not the
  `exposure` of the request, so that an old value in a request cannot replace it [A8]. With [G1],
  this value is only the value at the open and the value after a failed search.
- A held value found at another rate: each change of the rate searches again at the new rate, before
  the rate check judges the camera (1.3b) [G1]. After each search that finds a value,
  `exposure_found_at_fps` is the mode rate. It differs from the mode rate only after a failed search
  at a new rate. The row then shows the chip of `exposure_search_failed` (1.8). The row text "Found
  at 30 fps: search again" of the earlier draft goes [B9].

### 1.3b The search at an open

The order of an open of a camera in `AUTO` [G1, G2, B1]:

1. `starting`: the steps 1 to 7 of [cap 9.1] with the held value set at step 5, and the 90 warm-up
   frames of [cap 9.2]. A camera in `AUTO` has no start-up rate check of [cap 10.1].
2. `waiting`: the warm-up is done. The camera waits for the other selected cameras [cap 9.4].
3. `adjusting`: when no selected camera is `starting`, the camera goes into the gate and runs the
   search of 1.3 on its open stream. All cameras that open together search at the same time [G2].
   The preview shows [G2].
4. `checking`: the search has set its result, or the held value again after a failure. The check of
   [cap 10.2] judges the camera. This is the rate check of (b) in 1.2: it judges the value that the
   search found.
5. `ready` or `too_slow`, as after a live change.

A camera in `MANUAL` keeps the order of [cap 9.1] and its start-up rate check of [cap 10.1]: it goes
from `waiting` to `ready`.

Why: a camera in `starting` has no preview and is not in the gate [cap 8.1]. A start-up rate check at
the held value would judge the camera before the search, and fail it (stage `rate check`, closed)
before the search can find a value that keeps the rate [B1].

The limits [B3]:

- For a camera in `AUTO`, the ready limit of 15 s of [cap 9.3] counts from the open to the end of the
  warm-up.
- The search keeps its own limit of 20 s from its first set (1.3 item 6) [A2].
- The check after the search has the early decision of [cap 10.2].
- The apply request does not wait for the search (below) [H1]. It answers when each camera in `AUTO`
  is `adjusting`, `ready`, `too_slow`, `failed` or `dead`, and each other camera is in a state of
  `SETTLED_STATES` (`camera_status.py`), as today. Today the wait ends at `waiting`; for a camera in
  `AUTO` it now goes on until the camera is `adjusting`, which comes when no selected camera is
  `starting` [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md). That is about 1 s to open and 3 s of warm-up at 30 fps, so about 4 s for one
  camera. With more cameras it is longer: certify measured 5.8 s for three cameras [cert 4.7].
- Each wait of the main process uses `PARENT_WAIT_LIMIT_S` (30 s, `camera_group.py`): the wait of
  the apply above and the waits of the reopen of the fall back of 2.4, which waits as an apply. A camera
  process that gives no answer in that time is `failed` by `_give_up`, as today [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).
  The wait of the endpoint of 1.5 for the end of each search uses `SEARCH_WAIT_LIMIT_S` (35 s: the search
  limit of 20 s, two bounded set calls of 5 s and 5 s of margin). At that limit, a camera whose process is
  alive and still `adjusting` is not marked `failed`; its result comes through the live status [ADR-GEH0](../decisions/entries/GEH0-choices-of-code-step-3.md).
- A client that waits for the end of a search waits until no camera is `adjusting` or `checking`. It
  must allow 25 s from the apply response, at 30 fps and at 60 fps: the search limit of 20 s holds at
  each rate, and the check takes about 2.5 s at 30 fps and 1.3 s at 60 fps. The clock starts at the
  response, because the warm-up (about 4 s, up to 15 s) comes before the response [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md).
- After a fall back of 2.4 that a search starts, the client must allow 45 s more from the time when
  the live state first holds the `rate_fallback` item: the ready limit of 15 s of the reopen at 30 fps,
  then 25 s for the search and its check, with margin. A usual fall back takes about 18 s (2.4).
- The search and the check then take, for each camera at 30 fps, about 10.7 s and 2.5 s. Thus a
  record start can come about 17 s after the apply. The worst case: 15 s, then 20 s, then about 3 s,
  so about 38 s. At 60 fps: about 1 s, 1.5 s, 5.3 s and 1.3 s, so about 9 s. The cameras of one apply
  search at the same time, so the group takes about as long as its slowest camera.

What a client sees [H1]:

- An apply request, or another request that opens cameras, does not wait for the searches. It
  answers when each camera is open and streaming. Each camera in `AUTO` is then `adjusting` (or
  already `ready` or `too_slow`, or `failed` or `dead`), by the wait rule above. Its config in the response holds the value of the open (the held value, or -7) and its
  old `exposure_found_at_fps`.
- The found values and the warnings arrive through the live status: the `app_state` message of the
  websocket, which the server sends each second when the state changes. The state holds `configs`
  and the status of each camera (`state`, `exposure_search`, `warnings`).
- During the search, the status of the camera has `state: "adjusting"` and
  `exposure_search.state: "running"` (1.5). The preview of each camera shows [G2].
- When `exposure_search.state` of a camera becomes `"done"`, the UI copies `exposure` and
  `exposure_found_at_fps` of that camera from `configs` of the state into its stored settings [B14].
  This replaces [A6] for a search that a response does not carry.
- A client with no websocket reads the same state from the new route `GET /camera/group/state`
  (1.5) [B15]. It reads it again until no camera is `adjusting` or `checking`.
- A recording cannot start until each camera has left `adjusting` [H1, G2]: a record start gets
  HTTP 409 until each camera is `ready` [cap 8.3]. The UI disables the record button while a camera
  is `adjusting`, with the tooltip "Setting exposure…" (1.8) [B14].

The other cameras [H2]:

- Only a camera that opens searches. When "Update Cameras" adds a camera, or reopens a camera for a
  changed size, only that camera searches. The other cameras get no set call. They keep running with
  their state, their values and their preview.
- The new camera joins the gate in `adjusting`. Thus at a value at which it is slow, it slows the
  rounds of the gate and the preview of each camera, for about 1 s for each slow value [E9].
- A record start waits for it: HTTP 409 until it is `ready` [G2].

A failed search at an open [H3]:

- The search sets the previous value again (the held value, or -7 with no held value), and the
  warning `exposure_search_failed` comes (1.5). `exposure_found_at_fps` keeps its old value. The
  camera keeps running. Then the check of [cap 10.2] judges the camera: `ready` or `too_slow`.
- A search that finds too little light holds its result with the flag `add_light` (1.3 item 5)
  [Q6]. The check then judges the result.
- A search never makes a camera `failed` [H3]. A camera that is `too_slow` keeps its preview and
  counts as streaming (Q10 of [ADR-VYS7](../decisions/entries/VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)). Its row shows the text of 1.5a.
- A hang, a stall or a removed device during the search: 1.3 item 7.

Pause [K1]:

- The pause is a display freeze in the UI only: the pause button, the menu item and Shift+Space
  freeze the image on the screen. It works at all times, also while a camera is `adjusting` and
  during a recording. It sends no request, and it does not touch the cameras [K1].
- Thus a search goes on while the display is frozen, and it ends as usual.
- The public pause route `PUT /camera/group/all/pause` (and the older
  `GET /camera/group/all/pause_unpause`) is removed [K1] ([ADR-V8RS](../decisions/entries/V8RS-pause-freezes-the-ui-display-only.md)). The internal pause that the record start
  uses stays [cap 9.4].

### 1.4 States and the other cameras

- The searching camera stays in the gate, with its preview. The other cameras keep streaming, with
  their preview. The gate still waits for each camera [E9]. Thus a value at which one camera is slow
  also slows the rounds of the gate, and the preview of each camera, for that value (about 1 s).
- A new state `adjusting` holds a camera while its search runs [Q7, G2]: preview yes, in the gate
  yes, as `ready`. A recording cannot start until each camera is done [G2], and a changed config of
  that camera is refused (HTTP 409).
- At an open, all cameras in `AUTO` that open together search at the same time (1.3b) [G2].
- After the search, the camera sets its result value. Its state goes to `checking`, and the check of
  [cap 10.2] decides `ready` or `too_slow`, as after a live change.
- A `too_slow` camera keeps its tile and counts as streaming (Q10 of [ADR-VYS7](../decisions/entries/VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)). This agrees with
  [cap 8.1] (`too_slow`: preview yes, in the gate yes).
- Code: `STATES` and `GATE_STATES` of `camera_status.py` have no `adjusting` today. Step 3 adds it to
  both, and not to `SETTLED_STATES`.
- Known weak point: the OpenCV source is a pull source. Its `source_frame_number` counts only the
  frames that the loop grabs. Thus with the OpenCV source (the temporary source of [cap 14.2] on
  Windows), a slow camera of the group can make the measured rate of another camera low, and that
  camera then does not keep a value that it can keep. The Media Foundation source does not have this
  fault. The OpenCV source on Windows goes at the end of phase 3 [D8].

### 1.5 API

Config:

- `CameraConfig.exposure_mode`: `"MANUAL"` or `"AUTO"`. A request with `"RECOMMEND"` is read as
  `"AUTO"`, so that old saved configs keep working. Thus it searches at the open [G6]. Each other
  value gets HTTP 422.
- The default of `CameraConfig()` is `exposure_mode: "AUTO"`, `exposure: -7` and
  `exposure_found_at_fps: None` [G1, H7]. A consumer that sends no mode (freemocap) then gets the
  search at each open. It sends `MANUAL` to keep its value.
- `exposure`: for `MANUAL` the value to set. For `AUTO` the held value (1.3a).
- `exposure_found_at_fps`: 1.3a. The name is a decision [G5].
- `same_config` (`camera_group.py`) compares the configs with `CameraConfig.__eq__` over all fields.
  It ignores `exposure_found_at_fps`, `camera_index` and `camera_name`: a request that differs only
  in them is the same config (no effect on the camera, not refused in a state of [cap 8.3]). An
  accepted request still stores the `camera_index` and `camera_name` of the request [H6] [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).

New endpoint. Its path is a decision [G5]. Its body, its response and its codes are [A11]:

```
POST /camera/group/exposure/auto
```

- With no body, it applies to each selected camera of the group (the button). The body
  `{"camera_ids": ["a1b2"]}` limits it to those cameras ("Search again"). A camera ID that is not
  selected gets HTTP 422.
- It sets each camera to `AUTO` and runs the search on each, at the same time. It returns when each
  search has ended, and it waits at most `SEARCH_WAIT_LIMIT_S` (35 s) for that (1.3b) [ADR-GEH0](../decisions/entries/GEH0-choices-of-code-step-3.md).
- Response 200:

  ```json
  {"camera_configs": {"a1b2": {"exposure_mode": "AUTO", "exposure": -8, "exposure_found_at_fps": 30.0, "...": "..."}},
   "results": {"a1b2": {"state": "done", "chosen": -8, "add_light": false, "reason": null,
                        "trials": [{"value": -12, "brightness": 22.4, "measured_fps": 30.01, "kept_rate": true,
                                    "first_fps": null}]}},
   "camera_failures": {},
   "warnings": []}
  ```

- Each trial has `value`, `brightness`, `measured_fps`, `kept_rate` and `first_fps`: the rate of the
  first window of a value that the search measured again (1.3 item 2.7), else null. The status
  `exposure_search` has the same trials [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md).
- HTTP 409: no camera group runs; a recording runs [D36]; a search runs; a camera is `starting`,
  `waiting` or `adjusting`. The detail names each camera and its state [cap 8.3].
- A camera in `checking` is allowed: its check stops, and the search starts [A11].
- HTTP 422 for a camera whose source is OpenCV on Linux or macOS: `the exposure search does not run
  on the OpenCV source of this system` (1.7) [K2]. On Windows, the temporary OpenCV source searches
  (1.7). A camera with no working exposure control is not searched, and it gets no
  422: the warning `no_manual_exposure` names it (1.9) [K3].
- `CameraGroupManager.search_exposure(camera_ids=None)` does the work of the endpoint, and it
  returns the same response. A program that runs the manager in its own process (certify) calls it
  with `await` [B18].
- The switch from `MANUAL` to `AUTO` in an apply request runs the same search for that camera. Its
  result arrives in the status `warnings` and `exposure_search` of the live state [H1].
- An apply request that opens a camera in `AUTO` runs the search at the open. It does not wait for
  the search: it answers when the cameras are open and streaming, and the result arrives through the
  live status (1.3b) [G1, H1]. The same holds for an apply that switches a camera that streams from
  `MANUAL` to `AUTO`: its response has the camera in `adjusting`.
- New route `GET /camera/group/state` [B15]: it returns `CameraGroupManager.to_state_dict()`, the
  object that the `app_state` message of the websocket sends as `state` (`camera_groups`, with
  `id`, `configs`, `cameras`, `alive`, `recording_in_progress` and the fields of [recorder.md](recorder.md)
  8.4 of each group). `alive` is true while the group runs and at least one selected camera lives: its
  camera process runs, and it is not `failed` or `dead`, not closing and not closed. Thus a group whose
  other cameras still record when one camera dies stays `alive`. The UI reads no field `alive`; it is
  not a filter for the tiles ([preview-4b.md](preview-4b.md) 4.5) [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md).
  A client with no websocket reads the result of a search there (1.3b). The state
  has no field `paused`: [ADR-V8RS](../decisions/entries/V8RS-pause-freezes-the-ui-display-only.md) removed it, and `CameraGroupState` has none. The display freeze
  of the UI is not in the state [K1].

Status ([cap 8.4]) adds `exposure_search` (the name is a decision [G5]): null before the first
search, else the `results` object of one camera above. `"state"` is `"running"`, `"done"` or
`"failed"`. It also has `count`: the number of searches that the camera started since the group
started (1 after the search at its first open). The main process keeps it for each camera ID for the
life of the group [B20] (changed on 2026-11-20, [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md)). A reopen for a size or rate change runs
inside the same camera process (`CameraLoop._reopen`); only "apply again" starts a new camera
process [cap 8.2]. Both keep the count. The store [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md): the shared counter `search_count`
(`multiprocessing.Value("q", 0)`) of `CameraStatus`, which the main process creates with the status.
The camera process adds one at the start of each search. `reset_for_start` does not clear it, and the
status of an unselected camera is kept (`removed_statuses` of `camera_manager.py`), so a reselect
keeps it too. A new group starts at 0. A client counts the searches with it.

`reason` of `exposure_search` has a fixed vocabulary [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md): `null` (the search found a value), or,
with `state` `"failed"`, one of `no-value-in-range` (no value of 1.3 item 1 is in the exposure range of
the camera) [ADR-GEH0](../decisions/entries/GEH0-choices-of-code-step-3.md), `no-value-kept-rate` (no value kept the rate; at 60 fps this value
starts the fall back of 2.4), `set-failed` (a set call returned an error), `readback-differs` (the
read-back differed from the value), `timed-out` (the limit of 20 s from the first set) and `camera-closed`
(the group closed the camera, or it was unselected). A camera that fails or dies during its search gives
its failure code ([ux 4.6.3]) as the reason [ADR-GEH0](../decisions/entries/GEH0-choices-of-code-step-3.md).

Warnings ([cap 11.3] form: `kind`, `camera_ids`, `text`, `control`). The kinds `add_light` and
`exposure_search_failed` are a decision [G5]. Their texts are [A11]. They are not texts of a slow
camera, so they stay [H5]:

- `add_light`, control `exposure`:
  `Camera a1b2: add light. At 30 fps the brightest exposure that keeps the rate is -6, and the image is too dark (mean 41 of 255).`
- `exposure_search_failed`, control `exposure`:
  `Camera a1b2: the exposure search failed: no exposure from -12 to -5 keeps 30 fps. The exposure is -7 again.`
- `no_manual_exposure`, control `exposure` [K3]:
  `Camera a1b2 has no manual exposure. SkellyCam does not set its exposure.` The kind is a decision
  [K3]. The text is [B21]. Certify records the same case with its reason code `no-manual-exposure`.
- `exposure_clamped`, control `exposure` (1.1):
  `Camera a1b2: manual exposure -2 is above the limit -5. The exposure is -5.` The kind and the text
  are proposed [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md).

The text of `exposure_search_failed` names the reason: `no exposure from -12 to -5 is in the range of
the camera (-4 to 3)` or `no exposure from -12 to -5 could be set on the camera` (`no-value-in-range`) [ADR-GEH0](../decisions/entries/GEH0-choices-of-code-step-3.md), `no exposure from -11 to -5 keeps 30 fps` with the first and
the last value that the search tried (`no-value-kept-rate`), `the camera refused exposure -9 (<error text>)` (`set-failed`), `exposure -9
read back as -8` (`readback-differs`), `it took more than 20 s` (`timed-out`). `camera-closed` gives
no warning, because the camera closes [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).

The search response carries them. For a search that an apply starts, the live state carries them
[H1].

The owners and the lifetimes of the status `warnings` [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md):

- The camera process owns `add_light`, `exposure_search_failed` and `no_manual_exposure`. It writes
  them into a new array `CameraStatus.camera_warnings`. `add_light` and `exposure_search_failed`
  clear at the next search or the next exposure change of that camera. `no_manual_exposure` comes
  again at each open.
- The main process owns `rate_fallback`, `start_failure` and `exposure_clamped`. It writes them into a
  new array `CameraStatus.group_warnings`. `rate_fallback` clears at the next apply request of the user, not
  at the reopen or the "apply again" of the fall back itself (2.4). `start_failure` clears at the next
  apply request of the user too. `exposure_clamped` clears at the next apply request of the user, and
  that request writes it again when it clamps again. It also clears when the main process copies the held
  value of a search into the config (the camera is then in `AUTO`) [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md).
- The array `CameraStatus.warnings` keeps its job: the items of the recording that runs, written by
  the main process at the record start and cleared at the stop [cap 8.4, 11.3].
- `serialize()` joins the three arrays into the one list `warnings`. A record start, a stop and
  "apply again" (`reset_for_start`) clear neither `camera_warnings` nor `group_warnings`.

Failure codes are decided. [ux 4.6.3] holds the list. A camera that fails the start-up rate check
has the code `rate-low`. A failed search, too little light and a camera with no manual exposure are
warnings, not failures, so they have no failure code.

### 1.5a The texts of a slow camera

In every case, the text of a slow camera is exactly `Camera is slow. Try adding more light` [G3].
A slow camera is one whose rate is below the limit (code `rate-low`). A camera whose rate is above
the limit (code `rate-high`) is not slow. It keeps its own text: the server reason
`declared 30.00 fps, measured 31.42 fps. The camera delivers more frames than its mode rate`, and in
the row `The camera delivers more frames than its mode rate` [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md). `slow_reason` of
`rate_check.py` serves both directions today (`camera_loop.py` start-up rate check); the code
chooses the text by the direction.
It replaces the texts of [Q8], the `too_slow` row text of [UI 11-20] and the texts of [A12]: "Add
light or lower the exposure, or set the exposure to Auto.", "Add light, then run the exposure search
again.", "Too slow at this exposure: lower the exposure" and "Too slow at this exposure: add light,
then search again".

| Where | `MANUAL` and `AUTO` |
|---|---|
| Reason of a camera that fails the start-up rate check ([cap 10.4], server) | `declared 30.00 fps, measured 25.76 fps. Camera is slow. Try adding more light` [H5] |
| Row of a `too_slow` camera (UI) | `Camera is slow. Try adding more light` [G3] |

- The server reason keeps the declared and the measured rates of D25 before the text. The numbers
  stay in the detail of the API and in the log, not in the row of the UI [H5]. The text
  replaces the hints of D25.
- The addition ` Or choose 30 fps.` of [Q8] goes, because the fall back of 2.4 is automatic at
  60 fps. This removal is not ruled by the user: it stays proposed ([B8], [ADR-4Z7T](../decisions/entries/4Z7T-choices-after-the-search-at-each-open.md)).
- A camera in `AUTO` has no start-up rate check (1.3b). Thus in practice only a camera in `MANUAL`
  gets the server reason. A camera in `AUTO` that is slow is `too_slow` after its search and its
  check, and its row has the text.
- The text names no exposure value. A shorter exposure is not always faster: the C922 at 60 fps is
  slower at -8 than at -7 (1.3 item 3).

### 1.6 The auto exposure of the camera

SkellyCam never uses it on a native source, also not at the start-up [Q1, K2]. The restore at the
close is the one call that can turn it on again [K4, ux 4.7]. The reasons:

- The search tries each value from -12 to -5 anyway. A start point from the camera does not make the
  search shorter.
- The value that a camera reports in auto may not be its real exposure. Both cameras of the 60 fps
  test read back "auto, -10" [M `research/usb_cameras/docs/free_run_log_20261120.md` §9].
  [cap 17.3] also gives this as not known.
- The auto exposure of the camera changes the frame rate. The C922 in auto at 60 fps gave 37 fps at
  the start and 54 fps over 10 s (same file).

### 1.7 Linux and macOS (the OpenCV source)

The rule for a camera whose source is OpenCV [Q11, K2]:

- The native sources of Linux (V4L2) and macOS (AVFoundation) search as on Windows [K2] [ux 4.5].
  The rule below applies only to a camera whose source is OpenCV on Linux or macOS. The native
  sources end the exception of [Q11] for a native camera; the OpenCV source keeps it for now (item 9
  of [ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)).
- On the OpenCV source of Linux and macOS, the OpenCV source leaves the exposure to the camera. This
  is an exception to the rule of the user that the camera never sets its own exposure [E1]. The user
  knows it is an exception.
- The code changes for this [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md). Today `_apply_exposure` of `opencv_apply_config.py` forces
  the auto exposure of the camera only on Linux. On macOS it sets the camera's auto exposure for
  `AUTO` and a manual value for `MANUAL`. The new rule: the Linux branch covers macOS too
  (`sys.platform` `linux` or `darwin`), for each mode.
- On Windows, `_apply_exposure` makes no exposure call for `AUTO`, as for `RECOMMEND` today; it no
  longer sets the camera's own auto exposure. The loop sets the held value as a manual value at step
  5 of [cap 9.1], and the search runs (1.3b). This is case 1 of T-CAP-104 on Windows.
- For such a camera, the UI shows the exposure row as exactly "Exposure is set by the camera on this
  system" (item 9 of [ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)) and hides
  the mode choice and the link "Search again". The endpoint of 1.5 gives HTTP 422 for it. A config
  with `AUTO` opens with no search, and the state `adjusting` never comes. A new camera starts in
  `AUTO` there too [G1]. The warning of [cap 11.3] comes at each record start (T-CAP-104).
- The button for all cameras stays when at least one camera can search. It searches only those.

What the OpenCV source can do:

- Linux: OpenCV V4L2 writes `CAP_PROP_EXPOSURE` to `V4L2_CID_EXPOSURE_ABSOLUTE`, in units of 100 µs,
  with `CAP_PROP_AUTO_EXPOSURE` set to 1 (manual) [NV]. Thus a value v of this spec is `2^v x 10,000`
  units, rounded with `floor(x + 0.5)` [ux A-18]: -12 is 2, -7 is 78, -5 is 313. Cameras round to
  their own steps [NV]. sfn26 skips the search on Linux,
  because its values are log2 seconds, not V4L2 units
  [sfn26 `skellycam/core/camera_group/camera_backend_manager.py`].
- macOS: the OpenCV AVFoundation backend does not set exposure, to the knowledge of the agent [NV].
  sfn26 runs its search on macOS; whether a set has an effect there is not known.
- On Windows the search runs with both sources (Media Foundation and the temporary OpenCV source of
  [cap 14.2]), because DirectShow and Media Foundation use the same log2 unit.

### 1.8 UI

- Camera settings (`CameraGridSettingsModal.tsx`): the row "Exposure" keeps the two choices Manual
  and Auto. Manual shows the value selector, as today. On a route with no time unit (1.1), Manual
  shows eight plain steps from darkest to brightest, with no time label (item 10 of [ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)); Auto
  shows "Auto: step 6 of 8" (the step index plus 1), Manual shows "step 6 of 8", and the chip is
  `E:6/8` [ADR-F2KY](../decisions/entries/F2KY-rulings-of-the-user-after-the-third-consistency-check.md). Auto shows the held value as text, "Auto: -8",
  and the link "Search again", which runs the search for this camera only [Q2]. With no held value,
  the text is "Auto: no value found yet" [B9], and the link reads "Search". The link is disabled
  while the camera does not stream or a recording runs.
- `CameraConfigExposure.tsx` (the panel): the third choice "Recommend" goes. `isDisabled` becomes
  `exposureMode === 'AUTO'`.
- `cameras-types.ts`: `EXPOSURE_MODES = ['MANUAL', 'AUTO']`; `CameraConfigSchema` gets
  `exposure_found_at_fps` (number or null). A saved config with `RECOMMEND` becomes `AUTO` when the
  store loads it, by the pure function `normalizeExposureMode(config)` [G6]. The i18n key `recommend` stays unused until a cleanup of the locale files.
  `createDefaultCameraConfig` sets `exposure_mode: 'AUTO'`, `exposure: -7` and
  `exposure_found_at_fps: null` [G1].
- The camera list (`CameraConfigSidebarPanel.tsx`): a button "Auto-set exposure (all cameras)" in
  the header, next to the stream buttons. It is enabled when at least one selected camera streams
  and no recording runs, as the "Update Cameras" button is disabled during a recording [UI 11-20].
  Else its tooltip says why (`stopRecordingFirst`, or "Connect the cameras first"). While it runs, it
  shows the loader icon and the text "Setting exposure…".
- Each camera row (`CameraTreeItem.tsx`):
  - the chip `E:-8` for `MANUAL` as today, and `E:-8 auto` for `AUTO`;
  - "Auto: no value found yet" for `AUTO` with no held value [B9];
  - the chip "Add light" in the warning colour for an `add_light` warning, and "Exposure search
    failed" for `exposure_search_failed`, each with its text as the tooltip;
  - the text of 1.5a for a `too_slow` camera, in each mode [G3];
  - "Setting exposure…" for a camera in `adjusting`.
  - the line "The longest manual exposure is -5. The camera uses -5." for an `exposure_clamped`
    warning of a camera in `MANUAL` [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md).
  - the `rate-high` text of 1.5a for a `too_slow` camera whose `measured_fps` is above its mode rate.
  A pure function `exposureRowText(config, modeRate, state, warnings, measuredFps)` in
  `skellycam-ui/src/store/slices/cameras/exposure-row.ts` gives these texts. The row text "Found at
  30 fps: search again" of the earlier draft goes, because each change of the rate searches again
  (1.3a) [B9].
- A camera in `adjusting` shows "Setting exposure…" over its preview [G2].
- The record button is disabled while a camera is `adjusting`, with the tooltip "Setting exposure…"
  [G2, B14].
- Pause [K1]: the pause button, the menu item and Shift+Space freeze the image of each tile. They
  work at all times, also while a camera is `adjusting` and during a recording, and they send no
  request. The code does this already: `MainTabPanel.tsx` calls `setStreamPaused` of
  `ServerContextProvider.tsx` with `selectIsPaused`, and the guard "Stop Recording & Pause Cameras"
  is already gone. No new function `displayedFrame` comes; the freeze stays `setStreamPaused` [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).
  The store keeps the live state while the display is frozen.
- The UI reads each search result from the live state, not from a response [H1]. A pure function
  `copyHeldValues(desired, state)` in `skellycam-ui/src/store/slices/cameras/exposure-row.ts` copies
  `exposure` and `exposure_found_at_fps` of each camera whose `exposure_search.state` is `"done"`
  into its desired config [B14].
- The camera row shows the text of 1.5a only, not the measured numbers. The numbers stay in the
  detail of the API and in the log [H5].
- Camera names in the UI: a tooltip or a line that shows a text of the server replaces each camera ID
  of the item's `camera_ids` with `Camera <list number> · <name>`, and drops the word "Camera" or
  "camera" just before the ID. A pure function `labelText(text, cameras)` does it [A13]. It replaces
  `withCameraLabels` of `skellycam-ui/src/store/slices/cameras/camera-labels.ts` (today the form
  `Camera 5 (USB Camera)`) in its three callers: `CameraConfigSidebarPanel.tsx`, `CameraTreeItem.tsx`
  and `RecordingInfoPanel.tsx`. `camera-labels.test.ts` changes to the new form [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md). The form
  `Camera <n> · <name>` is the ruling Q13 of [ADR-VYS7](../decisions/entries/VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md).
- "Update Cameras" [ADR-F2KY](../decisions/entries/F2KY-rulings-of-the-user-after-the-third-consistency-check.md): one button at the top of the camera list adds the ticked cameras, closes
  the unticked cameras and retries the failed cameras, and does not reopen the other cameras. It
  names the failed cameras in `retry_camera_ids` of the apply request: only that list opens a `failed`
  or `dead` camera again [cap 8.3]. Each other apply of the UI (a settings change, the rate selector,
  Connect) sends no retry list (a decision of the user of 2026-11-21) [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md).
  After such an apply, a failed camera stays at "error" (the answer gives its failure [cap 8.3]): the
  "Update Cameras" button stays, and the answer does not replace the desired config of a camera that it
  reports as failed, so the edit of the user stays (`replacesDesired`). It is
  disabled during a recording, with the text "Stop the recording first" (the English text of the key
  `stopRecordingFirst`, which reads "Stop recording first" today).
- A camera on the OpenCV source of Linux or macOS: 1.7. A camera with no working exposure control:
  its exposure row says "No manual exposure on this camera" and has no mode choice (1.9) [K3, B21].

### 1.9 Edge cases

- A camera with no working exposure control (`present: false`; on macOS no route that sets the
  exposure [ux 4.4.6]; or, outside certify, a model whose evidence gives each exposure route the
  result `no` [cert 2.5]; an `unproven` route still gives the control, a proposed choice, item 12 of
  [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md)) [K3]:
  - it has no `MANUAL` and no `AUTO`; its search is skipped, and it is never `adjusting`;
  - at each open, the warning `no_manual_exposure` comes (1.5), and the camera goes from `waiting`
    to `ready` with its start-up rate check, as a camera in `MANUAL` [B21];
  - a request that names an exposure (a mode or a value) for it is not refused: the server ignores
    the value, and the warning comes. This replaces, for exposure only, the HTTP 422 of [cap 11.5];
  - the button and "Search again" skip it, and the response names it with the warning.
- A camera dies during the search: it is `dead` [cap 8.2]. The other searches go on. The response
  of the button has its failure in `camera_failures`. For a search at an open, the live state shows
  the camera `dead` with its failure [H1].
- A second press of the button, or "Search again", while a search runs: HTTP 409.
- An apply request for a camera in `adjusting`: HTTP 409, as for `starting` [agent 45 of cap].
- Unselect of a camera in `adjusting`: allowed. The search stops, and the camera closes. The search
  sets no value again: the close restores the controls [ux 4.7]. The same holds when the group
  closes the camera (1.3 item 6).
- The 60 fps mode where only one value keeps the rate (the C922): 1.3 item 4.
- A camera whose rate falls only for a time after a set: the 10 frames to settle cover the change.
  A camera that needs longer can fail a value that it can keep. T-REQ-23 records this.
- The button when some selected cameras do not stream (`failed`, `dead`): only the cameras that
  stream search. The response names the others in its detail as "not streaming".
- A camera in `AUTO` held at a value found at 30 fps, when the user picks 60 fps: it reopens at 60 fps
  and searches there before its check (1.3b, 2.4) [G1].
- "Update Cameras" adds a camera while the others run: only the new camera searches (1.3b) [H2].
- A camera is unselected while the other cameras search at an open: the others go on. A record
  start waits for each selected camera only [cap 9.4].

### 1.10 Changes to windows-capture.md

Applied on 2026-11-20 in [`windows-capture.md`](windows-capture.md) sections 1.3, 3, 4.3, 8.1 to 8.4,
9.1, 9.3, 9.4, 10.1, 10.4, 11.1 to 11.3, 11.5, 12, 14.1, 16.2, 16.3 and 20 (the note at its top).
The text below is the record of the change.

Change to section 1.3 (the item of D44): "A change of the UVC power line frequency control and a
flicker measurement [D44]. The "Add light" text of the exposure search is in
[`camera-requests.md`](camera-requests.md) 1.5 (2026-11-20)."

Change to section 3: add the row "`skellycam/core/camera/capture/exposure_search.py` | The exposure
search of `camera-requests.md` 1.3: the values, the choice, the flag `add_light`. Pure functions,
with the frame feed of the loop."

Change to section 4.3, row "Control thread": add "During an exposure search, it does each set of the
search, and it holds its read each second (`camera-requests.md` 1.3)."

Change to section 8.1: add the row "| `adjusting` | The exposure search runs on the open stream: at
an open of a camera in `AUTO`, after a change of the rate, or on request (`camera-requests.md` 1.2,
1.4). | yes | yes |". In the row `starting`, add "A camera in `AUTO` has no rate check here
(`camera-requests.md` 1.3b)." In the row `waiting`, write "Warm-up done and rate check passed (a
camera in `AUTO`: warm-up done)."

Change to section 8.2: the row "| `waiting` | no selected camera is in `starting` | `ready` |" becomes
two rows: "| `waiting` (a camera in `MANUAL`) | no selected camera is in `starting` | `ready` [D21]
|" and "| `waiting` (a camera in `AUTO`) | no selected camera is in `starting` | `adjusting`
(`camera-requests.md` 1.3b) |". Add the rows "| `ready`, `too_slow`, `checking` | the button,
"Search again", or a change of the mode from `MANUAL` to `AUTO` | `adjusting` |" and "| `adjusting` |
the search ended (with its result, or with the old setting after a failure) | `checking` |". Add
`adjusting` to the "From" cells of the rows "device removed; 2 s without a frame", "a bounded call
times out" and "unselect".

Change to section 8.3: add the row "| `adjusting` | blocked | refused | no effect | allowed |".

Change to section 8.4: add "`exposure_search` is null or the result object of `camera-requests.md`
1.5. `warnings` also holds the items of the camera process (`add_light`, `exposure_search_failed`,
`no_manual_exposure`) and of the main process (`rate_fallback`, `start_failure`), with the owners and
lifetimes of `camera-requests.md` 1.5. The route `GET /camera/group/state` returns the same state as
the `app_state` message of the websocket (`camera-requests.md` 1.5)." (Changed on 2026-11-20,
[ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).)

Change to section 9.1, step 5: "Set every control of the config (section 11). A camera in `AUTO`
sets its held value as a manual value. Its exposure search runs after the warm-up, in the state
`adjusting` (`camera-requests.md` 1.3b)."

Change to section 9.3: add "For a camera in `AUTO`, the 15 s count from the open to the end of the
warm-up. The exposure search has its own limit (`camera-requests.md` 1.3b)."

Change to section 10.1: add "A camera in `AUTO` has no start-up rate check. The check of 10.2 after
its exposure search judges it (`camera-requests.md` 1.3b)."

Change to section 10.4: replace the text with the server reason of `camera-requests.md` 1.5a:
`declared 30.00 fps, measured 25.76 fps. Camera is slow. Try adding more light`.

Change to section 11.1: replace the section with:

"- Modes: `MANUAL` and `AUTO` (`camera-requests.md` 1.1). `AUTO` is the exposure search of
  SkellyCam. It runs at each open, at a change of the rate and when the user asks, and it holds its
  result. A camera in `MANUAL` never searches. The auto exposure of the camera is never set on a
  native source, except by the restore at the close (`unix-capture.md` 4.7). This replaces the modes
  of D29 for exposure.
- The value keeps the unit of today: a power of two in seconds (-7 = 1/128 s) [D35].
- The search, its values, its frames and its rate guard: `camera-requests.md` 1.3. The held value:
  1.3a. The search at an open: 1.3b."

Change to section 11.2: add "A change of the mode from `MANUAL` to `AUTO` of a camera that streams
starts the exposure search on the open stream (`camera-requests.md` 1.2). A change from `AUTO` to
`MANUAL` is a live set of the value. A reopen of a camera in `AUTO` for a change of resolution or
rate runs the exposure search after the warm-up, in place of the start-up rate check
(`camera-requests.md` 1.3b)."

Change to section 11.3: the kinds are `auto_control`, `mixed_rate`, `control_change_failed`,
`add_light`, `exposure_search_failed`, `no_manual_exposure` and `rate_fallback`. On a native source,
`auto_control` no longer comes for exposure.

Change to section 11.5: add "A request that names an exposure for a camera with no working exposure
control is not refused. The value is ignored, and the warning `no_manual_exposure` comes
(`camera-requests.md` 1.9). The HTTP 422 stays for gain and focus."

Change to section 9.4: add "This pause is internal. The public pause route
`PUT /camera/group/all/pause` (and the older `GET /camera/group/all/pause_unpause`) is removed. The pause of the UI is a display freeze and does not
touch the cameras (`camera-requests.md` 1.3b)."

Change to section 12, row `set controls`: "each control set and read-back at start". The example
reason becomes the server reason of `camera-requests.md` 1.5a.

Change to section 14.1: add "On the OpenCV source of Linux and macOS, the forced auto exposure stays
as an exception to the rule of `camera-requests.md` 1.1, and the exposure mode choice and the
exposure search are not offered for such a camera (`camera-requests.md` 1.7). The native sources
search."

Change to section 16.2:

- Each test that does not name an exposure mode uses `MANUAL -7`, so that the new default `AUTO` does
  not change its result [B12].
- T-CAP-18: the reason is the server reason of `camera-requests.md` 1.5a.
- T-CAP-34: the fake camera reports its exposure in auto (a script value), with the config in
  `MANUAL`; the rest stays. The reason: a config cannot ask for the camera auto exposure now.
- T-CAP-41: `MANUAL -7` and `AUTO` held at -9 with a brightness model in the fake. `MANUAL` opens
  with one manual set and no search. `AUTO` opens with one set of -9, then searches after the warm-up
  [G1]. `RECOMMEND` is read as `AUTO`, and it searches [G6].
- T-CAP-42: the fake reports its exposure in auto with no set through the config; the rest stays.
- T-CAP-53, T-CAP-94: the reason is the server reason of 1.5a.
- T-CAP-55: "in `AUTO`, with the exposure search at the open" in place of "with auto exposure".
  T-CAP-96 is retired with T-CAP-92 to T-CAP-98 (item 10 of ADR-22EJ): no change.
- T-CAP-104 case 1: on Windows the OpenCV source searches (1.7), so no `auto_control` comes; on Linux
  and macOS the warning comes (1.7).
- T-CAP-77: exposure leaves the test; it reads the auto focus only.
- `skellycam/tests/capture/capture_hardware.py` `SLOW_REASON`: the new forms.

Change to section 16.3: T-CAP-55 is "a dark room with the exposure search".

Change to section 20: add a note after D29: "Note: for exposure, JK79 of 2026-11-20 (which
supersedes C4FZ) replaces the modes of D29
([ADR-JK79](../decisions/entries/JK79-exposure-search-at-each-open-and-camera-requests.md))." Add the
same note after D44 for the "exposure advice", after D45 for the USB link display, and after D25 for
the text of a slow camera.

### 1.11 Tests

| ID | Kind | Set-up | Pass criterion |
|---|---|---|---|
| T-REQ-01 | fake | One fake at 30 fps, `ready` in `MANUAL -7`, `brightness` = (-12, 10), (-11, 20), (-10, 40), (-9, 70), (-8, 110), (-7, 150), (-6, 190), (-5, 230); rate 30 at each value; apply `AUTO`. | The fake gets the sets -12 to -5 in order, then -9 (-8 is nearest to 127.5, then one darker). The config holds `AUTO`, -9, `exposure_found_at_fps` 30. No `add_light`. State `adjusting`, `checking`, `ready`. |
| T-REQ-02 | fake | As T-REQ-01, with a new script field `rate_by_exposure` = (-6, 15), (-5, 15); press the button. | Open count stays 1; the JPEG ring name does not change; the ring gets frames during the search; state `ready` → `adjusting` → `checking` → `ready`; result -9: -6 and -5 are never kept; the trials of -6 and -5 have `kept_rate: false`. |
| T-REQ-03 | fake | The C922 pattern: mode 60 fps; `rate_by_exposure` 60 at -7 only, 29.7 at each other value; brightness nearest to 127.5 at -6; press the button. | Result -7 (-6 did not keep the rate; -8 did not keep it, so no offset). A rate is measured at each of the 8 values. |
| T-REQ-04 | fake | Brightness 50 at -5, darker below; rate 30 at each value; press the button. | Result -6; `add_light` true; the response and the status `warnings` hold `add_light` with the text of 1.5; the camera is `ready`. |
| T-REQ-05 | fake | The generic camera: 25.76 fps at each value; `ready` with `MANUAL -7`; press the button. | The search fails; the last set is `MANUAL -7`; the warning `exposure_search_failed` with its text; the camera then runs the check of [cap 10.2] and is `too_slow`, and it stays in the gate with its preview. |
| T-REQ-06 | fake | Connect one fake with `AUTO`, `exposure` -7 and `exposure_found_at_fps` `None`, with the brightness and the rates of T-REQ-01. | One set of -7 at step 5; no start-up rate check; the states `starting`, `waiting`, `adjusting`, `checking`, `ready`; the apply answers only when the camera is `adjusting` (or later), not at `waiting`; the fake holds its frames after the first set of the search until the response is read, so the response has the camera in `adjusting`, with `exposure` -7 and `exposure_found_at_fps` `None` in its config; then the sets -12 to -5, then -9; open count 1; the ring gets frames during the search; at the end, the live state holds `AUTO`, -9, `exposure_found_at_fps` 30 and `exposure_search.count` 1 [G1, G2, B1, H1, B20]. |
| T-REQ-07 | fake | The image follows a new exposure only from the 3rd frame after the set; frames that arrived before the set returned have the old brightness; press the button. | Result as in T-REQ-01; the brightness of each trial is the value of the 10th frame that arrived after the set returned. |
| T-REQ-08 | fake | One value at 10 fps, the others at 30, on the virtual clock; press the button. | The search leaves the slow value at `t_a + 30 / (0.97 x 30)` s, ±25 ms; that trial has `kept_rate: false`. |
| T-REQ-09 | fake | Each value at 5 fps (the fake still delivers); press the button. | The search fails at 20 s (±0.25 s) of the virtual clock; the old setting is set again. |
| T-REQ-77 | fake | The model of T-REQ-01; at -8 the frame `s_a + 30` comes 50 ms late, and the camera keeps 30 fps. Then -8 at 28.1 fps for each frame; then -8 at 25 fps. | No case without a repeat has a `first_fps`. First case: the early decision reads 28.1 fps; -8 is measured again over 60 intervals (30 fps) and kept, so the result is -9, not -7; `first_fps` is 28.1; the search takes about 1.0 s more than with no borderline value. Second case: -8 is measured again and dropped, with a `first_fps`. Third case: -8 is measured one time (25 fps is more than 10 % below 30), dropped, `first_fps` null. Each value is set one time (1.3 item 2.7). |
| T-REQ-80 | fake | One value, mode 30 fps, 600 runs with seeds; arrival jitter: gaussian with sd 2 ms, and 3 % of the frames 10 to 30 ms late, with the cadence kept. The value at 29.0 fps with and with no repeat; at 30.0 fps with the repeat. | At 29.0 fps the repeat keeps the value at most 1 point more often than no repeat; at 30.0 fps each run keeps it (1.3 item 2.7). |
| T-REQ-78 | fake | One fake with the brightness of T-REQ-01; apply `MANUAL -2`; press the button; apply `MANUAL -2` again; then apply `MANUAL -7`. | The first response has `warnings` with the item `exposure_clamped` (control `exposure`, the text of 1.5); the config holds -5; the status `warnings` hold the same item; after the button the camera is in `AUTO` and the status has no `exposure_clamped`; the third response and the status have it again; after the last apply the status has no `exposure_clamped` (1.1, 1.5). |
| T-REQ-79 | fake | Two fakes `ready`; one stops delivering and its camera process ends; then the other stops. | `alive` of `GET /camera/group/state` is true at the start and after the first death; false when both are `dead` (1.5) [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md). |
| T-REQ-10 | fake | Two fakes `ready`, A and B in `MANUAL`; apply B with `AUTO` only. During the search of B: a record start; an apply that changes the size of B. | Only B searches; A gets no set call; the rings of A and B get frames at each gate round during the search; the record start gets 409 that names B and `adjusting`; the apply gets 409. |
| T-REQ-11 | fake | A recording runs with two fakes. Press the button; send "Search again" for one camera; send an apply with `AUTO` for one camera. | Each gets 409; the fakes get no set call; the configs do not change. |
| T-REQ-12 | fake | Connect, reopen by a size change, reopen by a rate change, and "apply again" after a fail, each with one fake in `AUTO` held at -9 (`exposure_found_at_fps` 30) and the brightness of T-REQ-01 at each rate. In the reopens, the request holds `exposure` -5. | Each open gives one set of -9 at step 5, not -5 [A8], then a search after the warm-up [G1]; each ends with -9 and `exposure_found_at_fps` at the mode rate of that open. |
| T-REQ-13 | fake | Three fakes `ready`: two `MANUAL`, one `AUTO`; press the button; then press it again while it runs. | Each camera searches one time and ends in `AUTO` with its own value; the response has `results` for the three; the second press gets 409; `exposure_search.count` of each camera is one more than before the press [B20]. |
| T-REQ-14 | fake | Apply requests with `RECOMMEND`, `AUTO`, `MANUAL`, `CAMERA`; a connect with `RECOMMEND`; a new `CameraConfig()`. | `RECOMMEND` is stored as `AUTO`, and the connect searches [G6]; `CAMERA` gets 422; the default is `AUTO`, -7, `exposure_found_at_fps` `None` [G1, H7]; an apply of the current config with another `exposure_found_at_fps`, `camera_index` and `camera_name` while the camera is `adjusting` gets no 409 and no set call, and the new `camera_index` and `camera_name` are stored (1.5). |
| T-REQ-15 | fake | A spy on `set_controls` of the fake in each test of this table and in T-CAP-41. | No call with `ControlSetting(auto=True)` for exposure, except the restore at the close of [ux 4.7], which comes after the last frame is taken and only for a camera whose exposure was in auto before the open [K4]. |
| T-REQ-16 | fake | `ready` with `AUTO -9`, found at 30; apply `MANUAL -7`. | One live set of -7; no search; state `checking`, then `ready`; `exposure_found_at_fps` is `None`. |
| T-REQ-17 | fake | `live_set_faults`: the set of -9 returns an error; then the set of -9 reads back -8; then each value is slow so that the search passes 20 s (virtual clock); press the button each time. | The search fails each time; the last set is the old setting; `exposure_search.reason` is `set-failed`, `readback-differs`, `timed-out`; `exposure_search_failed` has the text of 1.5 for each reason; the camera stays open. |
| T-REQ-18 | fake | Three fakes search; one gives device removed during its search. | That camera is `dead`, with no restore set; the two others end their searches; `camera_failures` holds it. |
| T-REQ-19 | fake | Cameras in `MANUAL` that fail the start-up rate check at 30 and at 60; one camera in `AUTO` at 30 that delivers 25.76 fps at each value. | The two reasons have the form `declared 30.00 fps, measured 25.76 fps. Camera is slow. Try adding more light`, to the character, with no ` Or choose 30 fps.` [G3, H5, B8]; the `AUTO` camera gets no start-up reason, and it is `too_slow` after its search and its check (1.3b). At 60 the fall back of 2.4 follows, so the reason at 60 is read in the log line of the failure (2.4a item 8). |
| T-REQ-20 | fake | A fake with no exposure control (`present: false`); connect it in `AUTO`; press the button; apply `MANUAL -7` for it. | No search and no `adjusting` at the connect; the start-up rate check judges it as for `MANUAL`; the warning `no_manual_exposure` with the text of 1.5 at the open; the button skips it and names it with the warning; the apply gets no 422, and the fake gets no exposure set [K3, B21]. |
| T-REQ-21 | fake | (1) The OpenCV fake with the platform read as Linux, then as macOS: press the button; send "Search again"; apply `AUTO` on a running camera; connect a fake in `AUTO`. (2) A native fake source with the platform read as Linux, then as macOS: connect in `AUTO`. | (1) The button and "Search again" get 422 with the text of 1.5; the apply sets no value through a search; `_apply_exposure` sets the camera's auto exposure for `MANUAL` and `AUTO` on both systems (1.7); the connect runs no search, and no camera is `adjusting` (1.7). (2) The camera searches at the open as on Windows, with the same states [K2]. |
| T-REQ-22 | fake | "Search again" for one of three `ready` fakes; then the body with a camera ID that is not selected. | Only that camera searches; the others get no set call; the second request gets 422. |
| T-REQ-42 | fake | Three fakes connect in `AUTO` at 30 (a new group), each with its own brightness model; one fake takes 1 s longer to open. During the searches, a record start. | No camera is `adjusting` before the last camera leaves `starting`; then the three are `adjusting` together; the apply answers only after each camera is `adjusting` (the fakes hold their frames after the first set of each search until the response is read), with the three in `adjusting`, and not after the searches; the record start gets 409 that names each camera and `adjusting`; during its search, the status of each camera has `exposure_search.state` `"running"`; the rings get frames; the live state holds the three results after the last search [G2, B1, H1]. |
| T-REQ-43 | fake | Two fakes `ready` in `AUTO`, held at -9 and -8. An apply adds a third fake in `AUTO` ("Update Cameras"). | Only the third camera searches; the two others get no set call and stay `ready` at -9 and -8; their rings get frames during the search; a record start during the search gets 409 that names the third camera [H2]. |
| T-REQ-44 | fake | The generic camera (25.76 fps at each value) connects in `AUTO` held at -7, found at 30. | No `failed` state and no start-up reason; the search fails with `exposure_search_failed`; the last set is -7; `exposure_found_at_fps` stays 30; the check gives `too_slow`; the camera stays in the gate with its preview [H3]. |
| T-REQ-45 | fake | One fake in `MANUAL -6`: connect; a reopen by a rate change; "apply again" after a fail. | No search in any case; one set of -6 at each open; the start-up rate check of [cap 10.1] judges each open; `waiting`, then `ready` [G1]. |
| T-REQ-46 | fake | On the virtual clock: one fake in `AUTO` whose warm-up ends 4 s after the open, and whose search takes 13 s (one value kept, each other value slow). | The camera does not fail with "not ready in 15 s"; the search ends with the kept value; the limit of 20 s of the search counts from its first set [B3]. |
| T-REQ-47 | fake | One fake connects in `AUTO` with the model of T-REQ-01. A client with no websocket reads `GET /camera/group/state` each 0.5 s from the apply to the end of the check. A hook calls `CameraGroupManager.to_state_dict()` in the same handler as each read. | Each body equals the dict of the hook of the same read; the camera is `adjusting` with `exposure_search.state` `"running"`, then `checking`, then `ready`; the last read holds `configs` with -9 and `exposure_found_at_fps` 30; no body has a field `paused` [H1, B15, K1]. |
| T-REQ-48 | fake | A group runs. Send `GET`, `PUT` and `POST` to `/camera/group/all/pause`, and `GET` to `/camera/group/all/pause_unpause`. | No pause route exists: each request gets 404 or 405, and no camera pauses [K1]. The tests of `skellycam/tests/test_camera_control_contract.py` and `test_camera_router.py` hold these cases already; T-REQ-48 cites them. |
| T-REQ-49 | ui-unit | `copyHeldValues(desired, state)`: a camera with `exposure_search.state` `"running"`; the same camera with `"done"`, `exposure` -9 and `exposure_found_at_fps` 30 in `configs`; a camera with `"failed"`; a camera in `MANUAL`. | Only the `"done"` camera changes its desired config: -9 and 30; the others do not change [B14]. |
| T-REQ-62 | fake | Two fakes `adjusting` at an open. Unselect one; then close the group while the other searches. | The unselected camera closes, its search stops, and it gets no set of the old value: only the restore of the close [ux 4.7]; the other search goes on until the group closes; then that search fails with no restore set of its own; no camera is `failed` [H3]. |
| T-REQ-63 | fake | A set call of the search hangs (`live_set_faults` hang). | The camera fails or dies by [cap 6.6], the process ends hard, and no restore set comes (1.3 item 7). |
| T-REQ-64 | fake | A spy on the read each second (`set_controls({})`) during a search. | No read from the first set of the search to its end; the reads come again after the search (1.3, A4). |
| T-REQ-65 | fake | Two fakes at 30 fps, push sources, on the virtual clock; B delivers 15 fps at -5 and -6. A searches while B is at -6 (a new search on B at the same time). | The trials of A keep the rate at each value; A gets no early decision for a frame that arrived in time and waited at the gate [cap 10.2 agent 88]. |
| T-REQ-66 | fake | One fake `starting`, then `waiting`; press the button and send "Search again" in each state. | 409 each time; the detail names the camera and its state (1.5). |
| T-REQ-67 | fake | One fake `starting`, then `waiting`; apply 60 in each state. | 409 each time; nothing reopens (2.7). |
| T-REQ-68 | fake | A search ends with `add_light`. Then a live change of gain (3c), an apply with the same config, a record start and stop, and an apply with `MANUAL -7`. Then a fall back of 2.4 writes `rate_fallback`; its reopen and its "apply again" run; then a new apply request. | `add_light` stays in the status `warnings` after the first three; it goes after the apply with `MANUAL -7`; `rate_fallback` survives the reopen and the "apply again" of the fall back, and goes at the new apply request; the record items of `warnings` still clear at the stop (1.5). |
| T-REQ-69 | fake | Three fakes: one `ready`, one `failed`, one `dead`; press the button. | Only the `ready` camera searches; the response detail names the two others as "not streaming" (1.9). |
| T-REQ-70 | ui-unit | `normalizeExposureMode(config)` with `RECOMMEND`, `AUTO` and `MANUAL`, as the store loads saved settings. | `AUTO`, `AUTO`, `MANUAL`; the other fields do not change [G6]. |
| T-REQ-71 | ui-manual | The pause button while the cameras stream, while a camera is `adjusting`, and during a recording. | The tiles keep the shown frame (`setStreamPaused` of `MainTabPanel.tsx`); no request goes to the server; the camera rows still change when a new live state arrives; un-pause shows the current frame [K1]. |
| T-REQ-72 | fake | Run `await CameraGroupManager.search_exposure(camera_ids=None)` with no HTTP server, then `POST /camera/group/exposure/auto` on a second group with the same fakes. | The two responses are equal, apart from the measured times; the states and the `count` move in the same way [B18]. |
| T-REQ-27 | ui-unit | `exposureRowText`: `MANUAL -8`; `AUTO -8` found at 30 with mode rate 30; `AUTO` with no held value; a camera in `adjusting`; `too_slow` in `MANUAL` and in `AUTO`; an `add_light` warning; an `exposure_clamped` warning in `MANUAL` and in `AUTO`; `MANUAL` step 2 and `AUTO` step 5 on a route with `exposure_unit` `ev`; `too_slow` with `measuredFps` 31.42 at mode rate 30. | `E:-8`; `E:-8 auto`; "Auto: no value found yet"; "Setting exposure…"; `Camera is slow. Try adding more light` for both `too_slow` cases, to the character [G3]; "Add light"; "The longest manual exposure is -5. The camera uses -5." in `MANUAL` only; `E:3/8` and "Auto: step 6 of 8", with no time label; `The camera delivers more frames than its mode rate` for the fast camera. No case gives a "Found at" text [B9]. |
| T-REQ-74 | fake | One fake in `AUTO` at 30 fps; connect; then a reopen by a size change and a reopen by a rate change (each in the same camera process), "apply again" after a fail (a new camera process), and an unselect and a reselect. | `exposure_search.count` is 1, 2, 3, 4, 5 after each search; it never goes back to 1 while the group runs; a new group starts at 1 (1.5). |
| T-REQ-75 | fake | Step 7b (it needs the clamp in the source, 1.1). A native fake whose exposure route has no time unit (`exposure_unit` `native`), with a brightness model; connect in `AUTO`; then apply `MANUAL` with `exposure` -7, then with 2. | The search sets the steps 0 to 7 in order and stores a step; the status reports `exposure_unit` `native`; `MANUAL -7` stores the step 5; `MANUAL 2` stores the step 2 (1.1, 1.3). |
| T-REQ-28 | ui-unit | `labelText` with the text `Camera a1b2: add light. ...` and the list where a1b2 is number 2, "Logitech C922"; a text with two IDs; the cases of today's `camera-labels.test.ts`. | `Camera 2 · Logitech C922: add light. ...`; each ID replaced; an unknown ID stays; no file imports `withCameraLabels` (1.8). |
| T-REQ-29 | ui-manual | The app with three cameras in `AUTO`: a connect; the button; "Search again"; a switch to Auto while not streaming, then a connect; a restart of the app, then a connect. | At each connect, "Setting exposure…" shows over each preview, and the record button is disabled with that tooltip until each search ends [G2]; the button and link states and tooltips of 1.8; after the restart, the held value comes back from the stored settings, and the connect sets it first and then searches [B2]. |
| T-REQ-23 | hardware | Windows. The C922, the C930e and the Kiyo Pro at 1280x720 30 fps, `ready` in `MANUAL -7`; press the button. Then close, and connect the three in `AUTO`. | Each camera ends `ready` with its 10.2 check passed; no reopen during a search (open count 1); each search under 20 s. At the connect, the apply answers in about 4 s with the three `adjusting`; the three search at the same time after their warm-up; the time from the apply to its response, and to the end of each search in the live state, is recorded (1.3b) [H1]. The trials of each camera are recorded, so that the 10 frames to settle and the 30-frame window can be confirmed [Q4]; each trial with a `first_fps` (a value measured again, 1.3 item 2.7) is counted. |
| T-REQ-24 | hardware | Windows. The C922 alone at 1280x720 60 fps in `MANUAL -7`; press the button. | The result keeps 58.2 fps or more, or the search fails with its text. The trials are recorded (the notes predict -7). |
| T-REQ-25 | hardware | Windows, `SKELLYCAM_HARDWARE_DARK=1`. Each camera at 30 fps; press the button. | No camera holds a value at which its 10.2 check fails; the flag `add_light` and the brightness at the brightest kept value are recorded, so that the user can set the limit of 64 [Q6]. |
| T-REQ-26 | hardware | Windows. The Kiyo Pro alone in `AUTO`; connect and close five times; then press the button. | Each connect searches and reaches `ready` with its value, or records its diagnostics; the trials of each search are recorded, with the `first_fps` of each value measured again (1.3 item 2.7); the Kiyo Pro wedge rule applies [cap 16.1]. |

## 2. Part 2: one frame rate for all cameras

### 2.1 The rule

- The camera list has one frame rate choice for all cameras, at the top [F1].
- It offers 30 fps and 60 fps. Nothing below 30 fps is offered [F3]; 29.97 fps counts as 30 (2.6,
  item 8 of [ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)). A rate above 60 fps is not offered [A14].
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
- A camera in `AUTO` reopens with its held value. After the warm-up, it searches at the new rate,
  before the check of [cap 10.2] judges it (1.3b) [G1]. It has no start-up rate check.
- A camera in `MANUAL` reopens with its value, and the start-up rate check of [cap 10.1] judges it.

### 2.4 The real 60 fps check and the fall back

This section is the one definition of the fall back to 30 fps. [ux 4.5] and [cert 8.2, 5.3] point
to it. In short:

1. When: the group rate of the request is 60 fps, and one selected camera fails at 60 fps: a camera in
   `MANUAL` (or with no working exposure control) at the stage `set mode` or `rate check`; a camera
   in `AUTO` whose search finds no value that holds 60 fps [H4]; or a camera in `AUTO` whose check
   after its search fails [B7]. The last case is decided by [F2] and [Q10]: the group runs at 60 fps
   only when each selected camera passes a real 60 fps rate check, and the server falls the group
   back to 30 fps one time [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).
2. What: the main process applies the configs from before the request, at 30 fps, to each selected
   camera, one time for the group. Each camera reopens at 30 fps, and each camera in `AUTO` searches
   again.
3. What a client sees: no camera stays `failed` for that failure, and `camera_failures` does not hold
   it. The configs are at 30 fps, and one `rate_fallback` item names each camera that failed at
   60 fps: in the apply response for a failure at the start-up, else in the status `warnings` of the
   live state [B17]. Thus a client that asked for 60 fps reads `framerate` 30 and the
   `rate_fallback` item, not a `rate-low` failure. The time limits of a client that waits are in
   1.3b: 25 s from the apply response, and 45 s more after the `rate_fallback` item appears.
4. No fall back: a failure at another stage (`open`, for example), a request at 30 fps, or a second
   failure at 30 fps (that camera stays `failed`).

The detail:

- When the user picks 60 fps while cameras stream, the UI sends the apply request at once. When no
  camera streams, the UI keeps the choice, and the next connect sends it.
- For a camera in `MANUAL`, the check is the start-up rate check of [cap 10.1] at 60 fps, over the
  warm-up frames 6 to 90 of each camera, with the exposure of its config. No other probe runs [A16].
- For a camera in `AUTO`, the check at 60 fps is its search at 60 fps and the check of [cap 10.2]
  after it (1.3b) [G1].
- The fall back [Q10]: when the group rate of a request is 60 fps, the main process applies the
  configs from before the request to each selected camera [A17] in these cases:
  - a selected camera fails at the stage `set mode` or `rate check` [A17];
  - the search of a camera in `AUTO` finds no value that keeps 60 fps [H4]. The fall back then starts
    at once, with no check of that camera;
  - the check of [cap 10.2] after the search of a camera in `AUTO` fails [B7], decided by [F2] and
    [Q10] (item 1 above). The fall back then starts when the check fails.

  For a new group, the configs from before the request are the configs of the request with
  `framerate` 30. Each camera then reopens at 30 fps (`failed` cameras by "apply again" [cap 8.3]),
  with its held value. Each camera in `AUTO` searches again at 30 fps (1.2 item 1) [G1].
- The fall back runs one time. A camera that also fails at 30 fps stays `failed`.
- A failure at another stage (`open`, for example "in use by another program") gives no fall back.
  That camera is `failed`, and the others run at 60 fps [A17].
- The fall back runs in the main process. It is one fall back for the group: a second camera that
  fails at 60 fps does not start a second one [H4].
- A fall back at the start-up (a camera in `MANUAL`, stage `set mode` or `rate check`) comes before
  the apply answers. A fall back that the search of a camera in `AUTO` starts comes after the apply
  has answered [H1]. It runs with no new request. Its `rate_fallback` items go into the status
  `warnings` of each camera that failed at 60 fps, and the configs at 30 fps go into the live state
  (1.3b) [B17].
- The result has the configs at 30 fps and one warning item of the kind `rate_fallback` for each
  camera that failed at 60 fps: in the apply response for a fall back at the start-up, else in the
  live state:
  `The group runs at 30 fps. Camera a1b2 measured 29.66 fps in its 60 fps mode at exposure -7.`
  The UI shows it with the label form, for example `Camera 2 · Razer Kiyo Pro measured ...` (1.8).
  `camera_failures` does not hold these failures, because the cameras run again.
- For a camera in `AUTO` whose search found no value, the measured rate and the exposure of the text
  are those of the trial with the highest measured rate [B7].
- The extra sentence of the earlier draft for a value found at another rate goes [B9]: a camera in
  `AUTO` searches at each rate (1.3a) [G1].
- Measured: the Kiyo Pro gave 29.7 to 30.4 fps in its 60 fps mode at each exposure from -7 to -10
  [M `research/usb_cameras/docs/free_run_log_20261120.md` §9]. Thus a group with the Kiyo Pro falls
  back to 30 fps.

The cost: each camera closes (272 to 1,122 ms [cap 6.9]), opens (about 0.9 s on the Kiyo Pro, same
file), and counts 90 warm-up frames (1.5 s at 60 fps). That is about 3 to 4 s for a group in
`MANUAL`. A fall back adds about 5 s more (warm-up of 3 s at 30 fps). The worst case is about 9 s.

With cameras in `AUTO`, each open also has a search and a check (1.3b) [G1]:

- At 60 fps: about 5.3 s of search and 1.3 s of check, so about 10 s in total. A camera that is slow
  at each value but one (the C922 pattern of 1.3 item 3) takes about 0.85 s for each slow value, so
  about 7 s of search.
- A fall back after a failed search at 60 fps (about 7 s): about 2 s to close and open, 3 s of
  warm-up, 10.7 s of search and 2.5 s of check at 30 fps, so about 18 s more.
- The worst case of a usual group is then about 30 s.

During this time, the selector shows "Checking 60 fps…": the UI reads the live state, and the text
stays until no selected camera is `starting`, `waiting`, `adjusting` or `checking` [H1]. Each camera
tile shows its state:
`starting` and `waiting` with no preview, then `adjusting` and `checking` with the preview.

How the result is kept [A18]:

- The main process keeps nothing new. The `rate_fallback` items of the response, or of the status
  `warnings`, are the result. The status keeps them until the next apply request of the user [B17].
  The reopen and the "apply again" of the fall back itself do not clear them: they are in
  `CameraStatus.group_warnings`, which `reset_for_start` does not clear (1.5) [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).
- The main process tells "no value kept 60 fps" from other failures by `exposure_search.reason`
  `no-value-kept-rate` (1.5) [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).
- The UI keeps the last `rate_fallback` text for the app run and shows it under the selector. It
  clears the text at the next pick of the rate or at a new detection.
- The 60 fps choice stays available after a fall back. A new pick runs the check again, for example
  after the user adds light or changes an exposure [Q9].

### 2.4a The fall back in the code

The rules above do not give these points. Each item is a proposed choice of the agent of step 4
[ADR-1T0S](../decisions/entries/1T0S-choices-of-step-4-one-frame-rate-and-the-fall-back.md):

1. The group rate of a request is 60 fps when the request selects a camera whose `framerate` is
   within 0.5 fps of 60, the tolerance of 2.5.
2. The configs from before the request: each camera of the group after the apply gets its config from
   before the request. A camera that the request adds, and each camera of a new group, gets the config
   of the request. Each config gets `framerate` 30. A camera that the request unselects stays closed.
3. The main process runs the fall back as an apply of these configs (`CameraGroup.apply`). The fall back
   has no whole-request check of [cap 8.3], and it does not clear the group warnings. Its retry list
   (`retry_camera_ids`, [cap 8.3]) holds each camera that failed at 60 fps, except a camera whose failure
   code (at the request, and again when the fall back runs) is a wedge code (`WEDGE_CODES`: `stalled`,
   `hung`, `device-removed`, `process-ended`); no other `failed` or `dead` camera opens again [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md). Before the reopen,
   it writes one `rate_fallback` item into `group_warnings` of each camera that failed at 60 fps. A fall
   back at the start-up also puts these items in `warnings` of the apply response. The item has `kind`,
   `camera_ids` (one camera) and `text`. It has no `control`, as `start_failure`.
4. The text gives the measured rate with two decimals, the mode rate as the shortest number (`60`,
   `59.94`) and the exposure as an integer. A camera in `MANUAL` gives the rate of its start-up rate
   check and the exposure of its config. A camera in `AUTO` whose check after its search failed gives
   the rate of that check and its held value. A camera that failed at the stage `set mode` has no
   measured rate. Its text is `The group runs at 30 fps. Camera a1b2 could not set its 60 fps mode.`
   A text with a measured rate and no exposure value ends after the mode: `... in its 60 fps mode.`
   A camera in `AUTO` whose search ran but gave no measured rate has the text
   `The group runs at 30 fps. Camera a1b2 found no exposure that keeps 60 fps.` The main process reads
   the mode rate, the measured rate and the exposure when it sees the failure, not when the fall back
   runs.
5. A fall back that a search starts: after an apply request at 60 fps, the watch thread of the group
   examines each camera in `AUTO` each 0.1 s (`WATCH_INTERVAL_S`). It starts the fall back when the last
   ended search of a camera came after the request and has the reason `no-value-kept-rate`, or when the
   camera is `too_slow` after such a search. The status field `held.count` (the search count of the
   ended search) is more than the search count before the request for such a search. The watch stops
   when the fall back starts, when no camera of the group is `starting`, `waiting`, `adjusting` or
   `checking`, at the next apply request of the user, at a search of the button or of "Search again",
   and at the close. Thus a search on request starts no fall back: it is not a request at 60 fps.
6. The watch thread starts the fall back on the event loop of the group, as the end of a take after an
   error. The log gets a failure of the fall back.
7. One flag of the group (`request_runs`) tells that a change of the cameras runs: an apply request of
   the user from its whole-request check to its end, with its fall back at the start-up, and each fall
   back. The check of the flag and its set have no wait between them. While the flag is set, an apply
   request, a record start, the button and "Search again" get HTTP 409 with the reason
   `Another change of the cameras runs now. Send the request again when the cameras are ready.` Each
   apply request of the user also adds one to a request count of the group. The watch keeps the count
   of the request at 60 fps with its configs. On the event loop, a fall back of the watch does not run
   when its count is not the current count, or while the flag is set, and the log tells why. The watch
   clears its configs only when they are still the configs that it read. Thus two changes of the
   cameras never run at the same time, a fall back never replaces a later request of the user, and the
   `rate_fallback` items keep the lifetimes of 1.5. The close is not refused: it ends a change that
   runs. With no camera group, the flag `creating` of `CameraGroupManager` does the same job: an apply
   request that would make a group sets it with no wait after it found no group, and clears it at its
   end. A second apply request that finds no group while the flag is set gets the same HTTP 409 with the
   same reason. A close of all groups adds one to the count `closes` of the manager; a request that makes
   a group and finds the count changed after its detection gets HTTP 409 with the reason `The cameras
   were closed while the request ran. Send the request again.` and makes no group. Thus two requests never make two groups [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md).
8. T-REQ-19 at 60 fps: the fall back comes after the failure, so the status then holds the result at
   30 fps. The test reads the reason at 60 fps in the log line of the failure.
9. A recording is never changed by a change of the rate (a decision of the user). A fall back does not
   run during a take, during a record start (`take_busy`) or during a close. The log tells why. A
   record start that passes its check clears the configs of the watch.

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
  tooltip `stopRecordingFirst` ("Stop the recording first"), as the "Update Cameras" button
  [UI 11-20] (1.8).
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

The rules above do not give these points. Each item is a proposed choice of
[ADR-1T0S](../decisions/entries/1T0S-choices-of-step-4-one-frame-rate-and-the-fall-back.md):

- The selector shows 60 fps when the desired `framerate` of the first selected camera (else of the
  first camera) is within 0.5 fps of 60. Else it shows 30 fps. A pure function `chosenRate(cameras)` in
  `rate-choice.ts` gives the choice.
- A pick sets the choice (the action `frameRateChosen`) and clears the note under the selector. When
  a camera streams, the UI then sends one apply request at once. It holds each camera of the group with
  its applied config (the config of the server) and the new rate. It holds no edit that the user did not
  apply, and no camera that is not in the group: "Update Cameras" adds it. A pure function
  `rateRequestConfigs(groupConfigs, rate)` in `rate-choice.ts` gives the configs. The response of a
  pick does not replace the desired configs: an edit that the user did not apply stays. When the
  request fails, the choice goes to the rate of the group in the live state at that time, else to the
  rate before the pick (`groupRate` in `rate-choice.ts`).
- The selector is disabled during a recording ("Stop the recording first"), and while a camera is
  `starting`, `waiting` or `adjusting` (2.7, "Setting exposure…", as the button of 1.8). Each option is
  then a disabled button, also for the keyboard. The option 60 fps is a disabled button when `can60` is
  false. The reason is a visible text under the selector, and the selector names it with
  `aria-describedby`. `SegmentedControl` gets an optional field `disabled` for each option and an
  optional `describedBy`.
- "Update Cameras" also sends a camera of the group whose desired rate differs by more than 0.5 fps
  from the rate of the group in the live state (`pendingCameraChanges`, the list `renumber`, which sends a camera again). A detection gives each camera the
  current choice: the rate of `chosenRate` of the camera list before the detection, else of the new
  list (`withChosenRate` in `rate-choice.ts`). Thus the tick of 2.5 and a new camera never give a
  request with two rates.
- `rateChoice`: a camera with an empty `supported_modes` has no 60 fps mode at its size. A camera with
  59.94 fps at its size, when another camera has 60, gets the reason
  `Camera 3 · Logitech C930e has 59.94 fps, not 60 fps, at 1280x720`. The UI keeps `supported_modes` of
  the detection result (`Camera.deviceInfo.supportedModes`). The reasons are in English only, as the
  texts of the server.
- The note under the selector: when a live state holds a `rate_fallback` item whose text the last live
  state did not hold, the UI sets `framerate` 30 in the desired config of each camera. It keeps the text of the
  item, in the label form of 1.8, as the note. A pure function `rateFallbackText(groups)` gives the text
  of the first `rate_fallback` item, or null. The note stays for the app run. A pick or a detection
  clears it. The tick of 2.5 puts its reason in the same note.
- "Checking 60 fps…" shows under the selector in place of the note from a pick of 60 fps that the UI
  sends, or from a new `rate_fallback` item in a live state where a camera is busy. It ends at a live
  state with no camera that is `starting`, `waiting`, `adjusting` or `checking`, while no apply request
  of the UI runs. A failed request also ends it. At the response of a pick that holds a camera in
  `AUTO`, the text stays until the next live state, because the cameras search after the response. At
  the response of another pick, the last live state decides. The pure functions
  `nextRateChecking(checking, busy, applying, newFallback)` and
  `rateCheckingAtResponse(checking, autoSent, busy)` in `rate-choice.ts` give the next value. Thus a
  later search on request or a restart does not show the text, and the text does not stay on when no
  camera is busy.

### 2.9 Changes to windows-capture.md

Applied on 2026-11-20 in [`windows-capture.md`](windows-capture.md) sections 7.5, 8.2, 11.3 and 16.2.
The text below is the record of the change.

Change to section 7.5, item "Auto rate": add "The UI does not send the auto rate. It writes one rate,
30 or 60, to each camera (`camera-requests.md` 2.2). The API keeps -1 and 0 for other consumers."

Change to section 7.5: add the item "**Fall back to 30 fps**: a request whose group rate is 60 fps
falls back to the configs from before the request, one time, when a selected camera fails at
`set mode` or `rate check`, or when a camera in `AUTO` finds no exposure that keeps 60 fps or fails
the check after its search (`camera-requests.md` 2.4)." The last case is decided by [F2] and [Q10]
(2.4 item 1); W 7.5 and W 8.2 state it [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).

Change to section 8.2: add the rows "| `failed` at 60 fps (stage `set mode` or `rate check`) | the
fall back of `camera-requests.md` 2.4 | `starting` at 30 fps |" and "| `adjusting`, `checking` or
`too_slow` at 60 fps (a camera in `AUTO`) | the fall back of `camera-requests.md` 2.4 | `starting` at
30 fps |".

Change to section 11.3: the kind `rate_fallback` (see 1.10).

Change to section 16.2, T-CAP-20 item (3): "apply a request that gives all three cameras the rate
60, where each fake delivers 60."

### 2.10 Tests

| ID | Kind | Set-up | Pass criterion |
|---|---|---|---|
| T-REQ-30 | fake | Three fakes `ready` at 30 in `MANUAL -7`, each with 60 in its modes and delivering 60; apply 60 for each. | Each camera reopens one time; the group rate is 60; no `rate_fallback`; each is `ready`. |
| T-REQ-31 | fake | As T-REQ-30, but one fake delivers 29.66 fps in its 60 mode. | Each camera reopens two times (60, then 30); the response has configs at 30 and one `rate_fallback` item for that camera with "29.66"; `camera_failures` is empty; each is `ready`. |
| T-REQ-32 | fake | Three fakes `ready` at 30 in `AUTO`, each with 60 in its modes and the brightness of T-REQ-01; one delivers 29.66 fps at each value in its 60 mode; apply 60 for each. | The apply answers with the three at 60 in `adjusting`; each camera searches at 60; the search of the slow camera fails because no value keeps 60 fps, and the one fall back of the group starts with no check of that camera and with no new request [H4, B17]; each camera reopens at 30 and searches again [G1]; the live state then has the configs at 30 with `exposure_found_at_fps` 30, and the status `warnings` of the slow camera hold one `rate_fallback` item, with no sentence on a value found at another rate [B9]. Second case: the slow camera keeps 60 fps at -7 in its search, then delivers 29.66 fps in the check of [cap 10.2]: the same one fall back starts when the check fails [B7, F2, Q10]. |
| T-REQ-33 | fake | As T-REQ-30, but one fake is in use at the reopen. | No fall back; that camera is `failed`, stage `open`; the two others run at 60. |
| T-REQ-34 | fake | As T-REQ-31, and the slow fake also fails at 30. | One fall back only; that camera is `failed`, stage `rate check`, at 30; the others run at 30. |
| T-REQ-35 | fake | A new group (no group runs) connects at 60 in `MANUAL -7`; one fake delivers 29.66 at 60. | The group runs at 30; the response has `rate_fallback`. |
| T-REQ-36 | fake | A recording runs at 30; apply 60. | 409; nothing reopens. |
| T-REQ-37 | fake | A camera is `adjusting`; apply 60. | 409; the detail names the camera and `adjusting`. |
| T-REQ-41 | fake | A fake in `AUTO` held at -7, found at 30, delivering 60 at -7 and 30 at each other value at 60 fps; apply 60. | The apply answers with the camera `adjusting` at 60; the camera searches before its check judges it [G1]: the result is -7, and `exposure_found_at_fps` is 60 in the live state; then the check of [cap 10.2] passes, and the camera is `ready` at 60 [H1]. |
| T-REQ-38 | ui-unit | `rateChoice`: (1) all with 60 at their sizes; (2) one with 60 at 1280x720 only and set to 1920x1080; (3) one with 59.94 and one with 60; (4) no selected camera. | (1) `can60` true; (2) false, the reason has the label form and 1920x1080; (3) false; (4) false. |
| T-REQ-39 | ui-manual | The app with the C922 and the Kiyo Pro streaming at 30 in `AUTO`; pick 60; pick 60 again. | "Checking 60 fps…" shows; the previews show while the cameras search at 60, then at 30; then 30 fps is the choice, with the `rate_fallback` text for `Camera n · Razer Kiyo Pro` under the selector; 60 stays available, and the second pick runs the check again. |
| T-REQ-40 | hardware | Windows. The C922 and the C930e at 1280x720 in `MANUAL -7`; pick 60, then 30. Then the same in `AUTO`. | The result (60 or the fall back) and the time of each change are recorded; no camera stays `failed`. In `AUTO`, the time of each search at 60 fps and at 30 fps is recorded. |
| T-REQ-84 | fake | One fake in `AUTO` with 30 and 60 in its modes and the brightness of T-REQ-01, `ready` at 60 after an apply of 60. The watch of the group makes no round from the apply until the end of the search below. Then the fake delivers 29.66 fps after each later set (`rate_after_change`); press the button; then the watch makes its rounds again. | The search fails with `no-value-kept-rate`; no fall back: the camera stays at 60 with no new open, and no status has a `rate_fallback` item (2.4a item 5). The test fails when the button search does not stop the watch, at each thread timing. |
| T-REQ-85 | fake | Three fakes in `MANUAL -7` with 30 and 60 in their modes; C delivers 29.66 fps. All three `ready` at 30; unselect C; apply 60 for A and B; then a request that names only C, at 60. | A and B run at 60 before the last request. After it: one fall back; A, B and C run at 30 and are `ready`; C has one `rate_fallback` item; A and B have none (2.4a item 2). |
| T-REQ-86 | fake | One fake whose detection lists 60 fps (`detected_modes`), but whose source has 30 fps only; `MANUAL -7`; connect at 60. | The apply answers 200 with the config at 30 and one `rate_fallback` item with the text `The group runs at 30 fps. Camera <id> could not set its 60 fps mode.`; `camera_failures` is empty; the camera is `ready` (2.4a item 4). |
| T-REQ-87 | ui-unit | `rateChoice`: (1) a selected camera with an empty `supported_modes`; (2) one camera with 59.94 only and one with 60 at 1280x720. | (1) `can60` false, the reason `Camera 1 · Cam A has no 60 fps mode at 1280x720`; (2) false, the reason `Camera 1 · Cam A has 59.94 fps, not 60 fps, at 1280x720` (2.8). |
| T-REQ-88 | ui-unit | `chosenRate`: the first selected camera at 60, at 59.94, at 30, at 29.97; no selected camera; no camera. | 60, 60, 30, 30, the rate of the first camera, 30 (2.8). |
| T-REQ-89 | ui-unit | `rateRequestConfigs` with the applied configs of A and B (B unticked in the list, still in the group), A with a pending edit in the list, and C ticked but not in the group; rate 60. | A and B with their applied configs, `framerate` 60 and `use_this_camera` true; no pending edit; no C (2.8). |
| T-REQ-90 | ui-unit | `rateFallbackText` with no item, with a `rate_fallback` item and with an `add_light` item; `nextRateChecking` with a new fall back item; while checking with a busy camera, with no busy camera while an apply runs, and with no busy camera and no apply; not checking with a busy camera (a later search on request, with an old item); a new item with no busy camera. `rateCheckingAtResponse` with a camera in `AUTO` and no busy camera, and with no camera in `AUTO` and no busy camera. `groupRate` with a group at 30, with a group at 60, and with no group. | null, the text, null; true, true, true, false, false, false; true, false; 30, 60, the rate before the pick (2.8). |
| T-REQ-91 | fake | One fake in `AUTO` at 30, then an apply of 60 where the search keeps no value but the check passes (`ready`). The watch of the group makes no round until a take runs; then it makes its rounds. During the take, `CameraGroup.fall_back` is also called on the event loop. | The take keeps running at 60 with no new open; no status has a `rate_fallback` item; the log has a line that the fall back did not run; the record start cleared the configs of the watch (2.4a item 9). |
| T-REQ-92 | fake | One fake in `AUTO` at 30 delivers 29.66 fps; apply 60. The fall back that the search starts waits on the event loop until a request of the user (`MANUAL -9` at 30) has answered. | The request of the user answers 200; the fall back does not run, and the log tells why; the camera runs `MANUAL -9` at 30; no status has a `rate_fallback` item (2.4a item 7). |
| T-REQ-93 | fake | As T-REQ-92, but the apply of the fall back waits until a request of the user (`MANUAL -9` at 30) has answered; then the fall back ends; then a new request of the user. | The first request of the user gets 409 with the reason of 2.4a item 7; the camera then runs the configs of the fall back, with its `rate_fallback` item; the new request clears the item (2.4a item 7, 1.5). |
| T-REQ-94 | fake | One camera `ready` at 30. On the event loop, `CameraGroup.fall_back` with a camera that has no measured rate after a search, then with a camera whose mode rate at the failure was 60, then with a measured rate and no exposure value. | The texts `The group runs at 30 fps. Camera <id> found no exposure that keeps 60 fps.`, `... measured 29.66 fps in its 60 fps mode at exposure -7.` and `... measured 29.66 fps in its 60 fps mode.` (2.4a item 4). |
| T-REQ-98 | ui-unit | `replacesDesired` for the response of a pick, of a settings request and for a camera that the request did not send. | false, true, false: the response of a pick keeps the unapplied edits of the list (2.8). |
| T-REQ-96 | fake | Two fakes `ready` at 30 in `MANUAL -7`; B delivers 29.66 fps. A request at 60 for both; its apply waits after it returned. During the wait: a request at 30 with `exposure` -9, a press of the button and "Search again" for A. | Each gets 409 with the reason of 2.4a item 7. Then the first request falls back: both cameras run at 30 with -7; B has one `rate_fallback` item (2.4a item 7). Also: two apply requests while no group exists, the detection of the first one slow: the second gets the same 409 (the flag `creating`), and one group is made [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md). |
| T-REQ-97 | fake | As T-REQ-96, but with no wait in the product code: the reopen of A at 60 waits in its open (`hold_opens`), so B fails at 60 while A is `starting`. Then a request for B alone at 30 with -9. | That request gets 409. After the release of A, the first request falls back: A and B run at 30 and are `ready`; no camera is `dead` (2.4a item 7). |
| T-REQ-95 | ui-unit | `pendingCameraChanges` with a group camera whose desired rate is 30 and applied rate 60, one at 30 and 29.97, and one ticked camera not in the group; `withChosenRate` with an old list at 60 and a new list at 30, and with an empty old list. | The first camera is in `renumber`, the second is not, the third is in `add`; each new camera gets 60, then the rate of the first selected camera of the new list (2.8). |

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

`CameraDeviceInfo` gets one field. Its name and its values are a decision [G8] (they were [A19]):

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
- The name is `usb_link`, not the sfn26 `usb_version` [G8]: the value is the speed of the link now,
  not the USB version of the device. The values are the sfn26 values, with `unknown` in place of `None`, so
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

- The sfn26 module is ported as `skellycam/core/device_detection/usb_connection.py`, with the
  values of 3.2: its function `usb_link(path)` gives the label of one camera
  ([ADR-EQY4](../decisions/entries/EQY4-base-the-work-on-upstream-sfn26-without-rust.md); this
  replaces the module name of [A22]).
- Windows: the lookup runs in the detection child of [cap 7.1], as a bounded call with a limit of
  1 s for each camera. Today `_add_usb_links` of `detect_cameras_devices.py` calls it after the
  detection child returns, with no limit; the code changes to this rule. A call past the limit gives `unknown`, and the child ends hard at its end as
  [cap 7.1] says for a hang [A23]. The hub calls are a seam (one function for each IOCTL), so that a
  test can give the bytes.
- Linux and macOS: the functions of sfn26, called in `detect_available_cameras` (as today).
- The UI label is built in step 5 [L1] (3.5 and 3.6 give the label).
- A virtual camera gets `unknown` with no lookup. Today the lookup runs for virtual cameras too
  (`_add_usb_links` of `detect_cameras_devices.py`); the code changes to this rule.

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
  no USB link" [Q12]. Its row is greyed [G9], and its tick box is disabled, because a request that
  names it gets HTTP 422 [W5] [B11].
- Which camera is virtual: the detection decides it, by the name or by the device link [G9]. The rule
  is in [`windows-capture.md`](windows-capture.md) 7.1 (the change of 3.7). This spec has no second
  definition [B11]. Thus an NDI camera, whose link is under `\\?\root#`, shows greyed as `virtual`.
- A pure function `linkChip(deviceInfo)` gives the chip text and the tooltip.

### 3.6 API and UI changes

- `CameraDeviceInfo.usb_link` (3.2). `POST /camera/detect` returns it. No other endpoint changes.
- `cameras-types.ts`: `DetectCamerasResponse.cameras[]` gets `usb_link` and `virtual`;
  `Camera.deviceInfo` gets `usbLink` (it has `virtual` already).
- `CameraTreeItem.tsx`: the chip of 3.5 after the name, in the "Camera info row".

### 3.7 Changes to windows-capture.md

Applied on 2026-11-20 in [`windows-capture.md`](windows-capture.md) sections 1.3, 7.1, 16.2 (T-CAP-105)
and 16.5. Where this text and that spec differ, that spec holds the facts of the code: the USB link and
the event-log check are ported from sfn26, so section 1.3 keeps the event-log check as ported, and
section 7.1 names `usb_connection.py`. The text below is the record of the change.

Change to section 1.3: delete the item "The USB link display" from the D45 item. The item becomes
"The Windows event-log check [D45]. The USB link label is in `camera-requests.md` part 3
(2026-11-20)."

Change to section 7.1: add "`usb_link` is the speed of the USB link now (`camera-requests.md` 3.2).
The lookup runs in the detection child, bounded at 1 s for each camera."

Change to section 7.1, the item of W5 [G9]: "Detection marks a camera virtual (`virtual: true`) when
its friendly name contains "virtual", on each OS, or, on Windows, when its link starts with
`\\?\root#` (a root-enumerated device with no hardware bus, for example an NDI camera) or
`\\?\swd#vcamdevapi#` (the virtual camera API of Windows 11). Each other link stays real. A request
that names a virtual camera gets HTTP 422 [W5]." This is the rule that item 6 of
[ADR-FTC3](../decisions/entries/FTC3-fixes-of-the-second-capture-ci-run-and-the-first-hardware-run.md)
proposes, and that `media_foundation/detect.py` has. Change to section 16.2, T-CAP-105: add a fake
whose link starts with `\\?\root#` and whose name does not contain "virtual"; it is virtual too.

Change to section 16.5, row D45: "T-REQ-50 to T-REQ-59 (the USB link label of `camera-requests.md`)".

### 3.8 Future work (not now)

A click on the label opens a diagram of the cameras on their USB controllers and hubs [L5]. The
research script finds the controller of each hub from the parent chain (the first `PCI\` parent).
No spec and no test now.

### 3.9 Tests

| ID | Kind | Set-up | Pass criterion |
|---|---|---|---|
| T-REQ-50 | fake | Extends `skellycam/tests/test_usb_connection.py`. Linux function with a `sysfs` tree in a temporary folder: `speed` 1.5, 12, 480, 5000, 10000, 20000; a camera with no `speed`; `/dev/video9` with no folder. Runs on each OS. | `USB 1`, `USB 1`, `USB 2`, `USB 3`, `USB 3`, `USB 3`, `unknown`, `unknown`. |
| T-REQ-51 | fake | Extends `skellycam/tests/test_usb_connection.py`. macOS function with a stand-in `ioreg` plist: location IDs with `USBSpeed` 4 and 3; the unique ID `FaceTime HD Camera`; an `ioreg` call that times out. Runs on each OS. | `USB 3`, `USB 2`, `unknown`, `unknown`. |
| T-REQ-52 | fake | Extends `skellycam/tests/test_usb_connection.py` (the parse is the regex `WINDOWS_DEVICE_PATH` of `usb_connection.py`). Windows parse: a Media Foundation link with `#{e5323777-f976-4f5b-9b55-b94699c46e44}\global`; a `root#image#` link. Runs on each OS (pure). | The instance, `vid` and `pid` of the link; the second gives `unknown`. |
| T-REQ-53 | fake | Windows decode with the IOCTL seam: V2 flag 1 set; flag clear and speed byte 2; speed byte 0; USB IDs at the port that differ from the camera. Runs on each OS (pure). | `USB 3`, `USB 2`, `USB 1`, `unknown`. Only the two connection-information codes are sent; no descriptor request. |
| T-REQ-54 | fake | Extends `skellycam/tests/test_usb_connection.py`. Detection with a lookup that raises, with a virtual camera by its name, and with a camera whose link starts with `\\?\root#` and whose name does not contain "virtual". | The detection returns each camera; the field is `unknown` for each; the two virtual cameras have `virtual: true` and get no lookup call [G9]. |
| T-REQ-55 | fake | Windows only [U18]: the detection child with a lookup that hangs. | That camera has `unknown`; the detection returns within 9 s: `STEP_LIMIT_S` (7 s, `media_foundation/detect.py`) plus 2 s. |
| T-REQ-59 | ui-unit | `linkChip` with `USB 3`, `USB 2`, `USB 1`, `unknown`, and `unknown` with `virtual: true`. | The chips `USB 3`, `USB 2`, `USB 1`, `USB ?`, `virtual`, with the tooltips of 3.5. |
| T-REQ-56 | hardware | Windows. The Kiyo Pro in a USB 3 port, then the same Kiyo Pro in a USB 2 port (or behind a USB 2 hub); the C922 and the C930e. Compare with the output of the research script. | `USB 3`, then `USB 2`; `USB 2` for the C922 and the C930e; each value agrees with the speed of the research script. |
| T-REQ-57 | hardware | Linux and macOS (phase 0, the user): the same cameras and ports as T-REQ-56. Compare with `lsusb -t` (Linux) or `system_profiler SPUSBDataType` (macOS). | Each value agrees with the speed that the system tool gives. |
| T-REQ-58 | ui-manual | The app after a detection, and during a second detection, with a virtual camera present and an NDI camera (Windows). | The chips and tooltips of 3.5; the chip `virtual` on the virtual camera and on the NDI camera; their rows are greyed and their tick boxes are disabled [G9, B11]; old chips stay during the second detection. |

## 4. Choices of the agent

Each choice is [An]. [ADR-Y6F6](../decisions/entries/Y6F6-camera-request-choices.md) holds the same
list. The choices of the first draft that the user decided are in section 5. The decisions [Gn] of
section 5a decided or replaced some choices. Each such choice has its mark below.

1. The early decision of 10.2 for each value, with 30 frames (1.3).
2. The time limit of a search is 20 s (1.3).
3. The config keeps `exposure_mode: "AUTO"` with the held value in `exposure`, and the new field
   `exposure_found_at_fps` (1.3, 1.3a). **Decided by [G5].**
4. The control thread does the sets and the loop measures; the read each second waits (1.3).
5. Each camera searches on its own, not one value on all cameras at a time; in the gate, the 10th and
   40th frames are the first taken frames at or after those counts (1.3).
6. The UI copies the held value from each response into its stored settings (1.3a).
7. A camera in `AUTO` with no held value starts at its `exposure` value (-7 for a new camera); its
   row offers the search (1.3a). **The part "it does not search by itself" is replaced by [G1]: it
   searches at the open. The start value -7 stays proposed.**
8. A reopen of a running camera keeps the held value of its current config, not the value of the
   request (1.3a).
9. A held value found at another rate: the row says "Found at N fps: search again"; the
   `rate_fallback` text tells how to reach 60 fps (1.3a, 2.4). **Replaced by [G1] and [B9].**
10. `RECOMMEND` in a request is read as `AUTO` (1.5). **Decided by [G6].**
11. The endpoint `POST /camera/group/exposure/auto` with the optional body `camera_ids`, its
    response, its codes, the status field `exposure_search`, and the warning kinds `add_light` and
    `exposure_search_failed` with their texts (1.5). **The names are decided by [G5]. The body, the
    response, the codes and the texts stay proposed.** A camera in `checking` is allowed: its check stops,
    and the search starts (1.5).
12. The one set of texts of a slow camera: the `MANUAL` reason adds "or lower the exposure", and the
    `AUTO` row text "Too slow at this exposure: add light, then search again" (1.5a). **Replaced by
    [G3] and [B8].**
13. Server texts keep camera IDs; the UI replaces each listed ID with the label form (1.8).
14. No rate above 60 fps is offered (2.1).
15. The UI never sends -1 or 0; the API keeps them; `CameraConfigFramerate.tsx` goes; the UI default
    is 30 (2.2, 2.8).
16. The real 60 fps check is the start-up rate check at 60 fps; no other probe (2.4). **Now for a
    camera in `MANUAL` only; a camera in `AUTO`: [G1], [B1].**
17. The fall back runs only for the stages `set mode` and `rate check`, with the warning
    `rate_fallback` (2.4). **[B7] adds the cases of a camera in `AUTO`.**
18. Only the UI keeps the last fall back text, for the app run (2.4).
19. The field `usb_link` with the values `USB 1`, `USB 2`, `USB 3`, `unknown` (3.2). **Decided by
    [G8].**
20. A virtual camera keeps `usb_link: "unknown"`; the UI shows `virtual` from the flag `virtual`
    (3.2, 3.5).
21. The label sends no request to the camera: only the connection-information calls at the hub
    (3.3).
22. Port the sfn26 module as `skellycam/core/device_detection/usb_link.py` (3.4). **The code ports it
    as `usb_connection.py` (ADR-EQY4); 3.4 uses that name.**
23. On Windows, a bounded lookup of 1 s for each camera in the detection child (3.4).

Choices after the decisions [Gn]. Each choice is [Bn].
[ADR-4Z7T](../decisions/entries/4Z7T-choices-after-the-search-at-each-open.md) holds the same list.
The answers [Hn] of section 5b decided some of them. Each such choice has its mark below.

1. A camera in `AUTO` has no start-up rate check: `starting` to the end of the warm-up, `waiting`,
   `adjusting` when no selected camera is `starting`, then the check of 10.2 (1.3b).
2. The held value is not a start point of the search. It is the value at the open and the value
   after a failed search (1.3a).
3. For a camera in `AUTO`, the ready limit of 15 s ends at the end of the warm-up; the search keeps
   its limit of 20 s (1.3b).
4. An apply request that opens a camera in `AUTO` returns when each search has ended (1.3b).
   **Rejected by [H1]: the apply answers when the cameras are open and streaming.**
5. Only a camera that opens searches; "Update Cameras" does not touch the other cameras (1.3b).
   **Accepted by [H2].**
6. A failed search at an open sets the held value again and goes on to the check; a search never
   makes a camera `failed` (1.3b). **Accepted by [H3].**
7. At 60 fps, the fall back also runs when a camera in `AUTO` finds no value that keeps 60 fps, or
   fails the check after its search; the text then uses its trial with the highest rate (2.4).
   **The first case is accepted by [H4]. The second case is decided by [F2] and [Q10] (2.4). The
   text stays proposed.**
8. The server reason keeps the declared and measured rates before the text of [G3]; " Or choose
   30 fps." goes; the warnings keep their own texts (1.5, 1.5a). **Accepted by [H5], except the
   removal of " Or choose 30 fps.", which stays proposed.**
9. The row text "Found at N fps", and the `rate_fallback` sentence for a value found at another
   rate, go; "Auto: no value found yet" (1.3a, 1.8, 2.4).
10. The UI fills `camera_index` and `camera_name` from the current detection; the recorder uses the
    `camera_index` of the request for the order of `group_position`; no new field in the take files
    (section 8). **Accepted by [H6].**
11. The rule of [G9] stays in the capture spec (a change to its 7.1); the UI greys the row of a
    virtual camera and disables its tick box (3.5, 3.7).
12. Each T-CAP, T-UNX and T-REQ test that does not name an exposure mode uses `MANUAL -7` (1.10,
    1.11, 2.10).
13. The default of `CameraConfig()` in the API is also `AUTO` (1.5). **Accepted by [H7].**
14. The UI takes the result of a search at an open from the live state (`copyHeldValues`); the tile
    and the record button show "Setting exposure…" while a camera is `adjusting` (1.3b, 1.8).
15. A client with no websocket reads the same state from the new route `GET /camera/group/state`
    (1.3b, 1.5).
16. Withdrawn: the pause rules during a search. [K1] makes them moot.
17. A fall back that a camera in `AUTO` starts after the apply has answered runs with no new request;
    its `rate_fallback` items go into the status `warnings` until the next apply request, and the
    configs at 30 fps into the live state (2.4).
18. `CameraGroupManager.search_exposure(camera_ids=None)` starts a search in the process of the
    manager (certify); the endpoint calls it (1.5).
19. The field `paused` of the state means the internal pause of a record start only; the display
    freeze of the UI is the pure function `displayedFrame` (1.5, 1.8). **Withdrawn:
    [ADR-V8RS](../decisions/entries/V8RS-pause-freezes-the-ui-display-only.md) removed the field, and the freeze stays `setStreamPaused` (1.8) [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).**
20. `exposure_search.count`: the number of searches since the camera process started (1.5).
    **Changed by [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md): since the group started, kept by the main process for each camera ID.**
21. A camera with no working exposure control: the text of `no_manual_exposure`, the row text "No
    manual exposure on this camera", and the start-up rate check as for `MANUAL` (1.5, 1.8, 1.9).

## 5. Decisions of the user of 2026-11-20

The user answered the 14 questions of the first draft on 2026-11-20
([ADR-C4FZ](../decisions/entries/C4FZ-camera-requests.md)). The body of this spec applies each one,
except Q3 and Q8, which the decisions of section 5a replace.

1. **Q1.** SkellyCam never turns on the auto exposure of the camera, also not at the start-up (1.1,
   1.6).
2. **Q2.** A link "Search again" in the camera settings runs the search for that one camera, beside
   the button for all cameras (1.2, 1.8).
3. **Q3.** The search runs only when the user asks: the button for all cameras, "Search again" for
   one camera, or a switch of a camera to Auto. A connect, a reopen for a size or rate change, and
   "apply again" use the held value and do not search. The user accepted the recommendation of the
   supervisor, not of the first draft (1.2, 1.3a, 2.3, 2.4). **Replaced by [G1]: Auto searches at
   each open, at a change of the rate and when the user asks.**
4. **Q4.** The search waits 10 frames after each set, takes the brightness from the 10th frame, and
   measures the rate over the next 30 frames. These are starting values; a camera run confirms them
   (1.3, T-REQ-23).
5. **Q5.** The one-step-darker offset is skipped when the darker value did not keep the rate (1.3).
6. **Q6.** "Add light" shows when the brightest value that kept the rate gives a mean below 64 of
   255. The search still holds its result. A camera run in a dim room sets the limit (1.3,
   T-REQ-25).
7. **Q7.** The new state `adjusting` (1.4).
8. **Q8.** The texts of a slow camera of the first draft (1.5a). **Replaced by [G3]: "Camera is
   slow. Try adding more light".**
9. **Q9.** After a fall back to 30 fps, the 60 fps choice stays available, and a new pick runs the
   check again (2.4).
10. **Q10.** The main process returns the whole group to 30 fps, one time, and says which camera
    could not hold 60 fps (2.4).
11. **Q11.** On Linux and macOS, the forced camera auto exposure of today stays until phase 7, and
    the mode choice and the button are not offered there. The user was told that this is an
    exception to his rule until phase 7 (1.1, 1.7). **Changed by item 9 of [ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md): "for now", not
    "until phase 7"; the UI text is "Exposure is set by the camera on this system".**
12. **Q12.** A link speed that cannot be read shows `USB ?`. A virtual camera shows `virtual` (3.5).
13. **Q13.** The UI writes the one rate into each camera config; no new group field (2.2).
14. **Q14.** A group with 59.94 fps against 60 fps is not offered 60 fps (2.5).

## 5a. Decisions of the user of 2026-11-20, second set

The user decided G1 to G9 on 2026-11-20
([ADR-JK79](../decisions/entries/JK79-exposure-search-at-each-open-and-camera-requests.md), which
supersedes ADR-C4FZ). The body of this spec applies each one.

1. **G1.** A camera in Auto runs the search (a) at each open, (b) when the user changes the frame
   rate, before the rate check judges the camera, and (c) when the user asks. A camera in Manual
   never searches. A new camera starts in Auto. This reverses Q3 and the "one time, when the user
   asks" of E3, and it replaces E5 (1.1, 1.2, 1.3a, 1.3b, 2.3, 2.4).
2. **G2.** During the search (about 10 s for each camera at 30 fps; all cameras search at the same
   time), the preview shows, the state is `adjusting`, and a recording cannot start until each
   camera is done (1.3b, 1.4, 1.8).
3. **G3.** The text of a slow camera is exactly "Camera is slow. Try adding more light", in every
   case (1.5a).
4. **G4.** No change: the exposure does not change during a take; Auto is the one-shot search of
   SkellyCam on the open stream; the auto exposure of the camera is never a mode (1.1).
5. **G5.** The names `exposure_found_at_fps`, `POST /camera/group/exposure/auto`,
   `exposure_search`, `add_light` and `exposure_search_failed` (1.5). Items 3 and 11 of section 4,
   for the names only.
6. **G6.** An old `RECOMMEND` is read as Auto, and so it searches at the open (1.5). Item 10 of
   section 4.
7. **G7.** A take uses the camera number of the camera list. The UI sends the number and the name
   of the current detection with each apply request, and the recorder writes the number of the
   request (section 8).
8. **G8.** One field `usb_link` with `USB 1`, `USB 2`, `USB 3`, `unknown` (3.2). Item 19 of
   section 4.
9. **G9.** A camera is virtual also by its device link (on Windows, `\\?\root#` or
   `\\?\swd#vcamdevapi#`), so that NDI cameras show greyed as "virtual". The rule belongs to the
   detection of `windows-capture.md` 7.1 (3.5, 3.7).

## 5b. Answers of the user on the choices [Bn], 2026-11-20

The user answered on 2026-11-20
([ADR-379P](../decisions/entries/379P-answers-on-the-choices-after-the-search-at-each-open.md)). The
body of this spec applies each one.

1. **H1.** B4 is rejected. An apply or open request does not wait for the searches. It answers when
   the cameras are open and streaming (about 4 s), with the cameras in `adjusting`. The found values
   and the warnings arrive through the live status. A recording cannot start until each camera has
   left `adjusting` (1.3b, 1.5, 2.4).
2. **H2.** B5 is accepted: "Update Cameras" searches only the new or the reopened camera (1.3b).
3. **H3.** B6 is accepted: a failed search at an open leaves the camera running at its previous
   value, judged `ready` or `too_slow`, never `failed` (1.3b).
4. **H4.** B7 is accepted for this case: at 60 fps, a camera in `AUTO` that finds no value that
   holds 60 fps starts the one fall back of the group to 30 fps (2.4).
5. **H5.** The camera row shows exactly "Camera is slow. Try adding more light". The measured
   numbers stay in the detail of the API and in the log. The warnings keep their own texts (1.5,
   1.5a, 1.8).
6. **H6.** B10 is accepted: the camera number decides only the order in the take (section 8).
7. **H7.** B13 is accepted: the default exposure mode of `CameraConfig()` is Auto (1.5).
8. **H8.** The public pause route and the pause button of the UI stay (1.3b, 1.8). **Replaced by
   [K1]: the pause is a display freeze in the UI only, and the public route goes.**

The user also confirmed that [G9] decides item 6 of
[ADR-FTC3](../decisions/entries/FTC3-fixes-of-the-second-capture-ci-run-and-the-first-hardware-run.md)
(3.7).

## 5c. Decisions of the user of 2026-11-20, third set

The user decided K1 to K4 on 2026-11-20
([ADR-6QFG](../decisions/entries/6QFG-pause-in-the-ui-search-on-native-sources-and-restore-at-close.md),
which supersedes ADR-379P and keeps H1 to H7). The body of this spec applies each one.

1. **K1.** The pause is a display freeze in the UI only (the button, the menu item and Shift+Space).
   It works at all times, also during `adjusting` and during a recording, and it does not touch the
   cameras. The public pause route goes. The internal pause of the record start stays (1.3b, 1.5,
   1.8, 1.10).
2. **K2.** The search also runs on the native sources of Linux and macOS. The HTTP 422 and "no
   `adjusting`" apply only to a camera on the OpenCV source and to a camera of K3 (1.1, 1.5, 1.7).
3. **K3.** A camera with no working exposure control gets no Manual and no Auto: no search, no
   `adjusting`, the warning `no_manual_exposure`, and a request that names an exposure for it is not
   refused (1.5, 1.9, 1.10).
4. **K4.** The restore of the controls at the close is the one call that can turn the auto exposure
   of the camera on again (1.1, 1.6, T-REQ-15).

## 6. Other decisions of the same day that this spec must agree with

These decisions of the user of 2026-11-20 on the UI were relayed by the supervisor. [ADR-F2KY](../decisions/entries/F2KY-rulings-of-the-user-after-the-third-consistency-check.md) holds
them, or cites the entry that holds them. This spec agrees with them:

- A `too_slow` camera keeps its tile and counts as streaming (Q10 of [ADR-VYS7](../decisions/entries/VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)). Its row says
  "Too slow at this exposure: lower the exposure" (1.4, 1.5a). **The row text is replaced by [G3]:
  "Camera is slow. Try adding more light".**
- The "Update Cameras" button is disabled during a recording, with the text "Stop the recording
  first" (1.8, 2.7) [ADR-F2KY](../decisions/entries/F2KY-rulings-of-the-user-after-the-third-consistency-check.md). One "Update Cameras" button at the top adds, closes and retries
  cameras and does not reopen the others (1.8).
- A virtual camera shows greyed with the label `virtual`, and it cannot be selected ([G9], [Q12],
  3.5).
- On a control route with no time unit, the exposure shows as "step k of 8", the chip `E:k/8`, and
  in Auto "Auto: step k of 8" (1.8).
- Camera failure reasons will get a fixed failure code beside the text. Not accepted yet (1.5).
  **Now decided: [ux 4.6.3] holds the codes (1.5).**
- The label form for a camera everywhere in the UI is `Camera <list number> · <name>` (0, 1.8;
  Q13 of [ADR-VYS7](../decisions/entries/VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)).

## 7. What must be tried on real cameras before the code is trusted

1. The 10 frames to settle and the rate window of 30 frames, on each camera (T-REQ-23) [Q4].
2. The limit of 64 for "Add light", in a dim room (T-REQ-25) [Q6].
3. The C922 at 60 fps through the search: the notes measured -6 to -10 only; -12, -11 and -5 are not
   known (T-REQ-24).
4. The search at 60 fps after a pick of 60 fps, and the fall back of 2.4 with cameras in `AUTO`
   (T-REQ-40).
5. The C922 with the Kiyo Pro open at 60 fps: one test gave 46.5 fps over frames 6 to 90 and 58.7 fps
   over 10 s (not repeated). The start-up check can then fail a camera that reaches 60 fps later.
6. The Kiyo Pro under five searches at five connects (T-REQ-26, the wedge rule).
7. The USB link of each test camera through its Media Foundation link, and the Kiyo Pro in a USB 2
   port (T-REQ-56).
8. The Linux and macOS link lookups (phase 0, T-REQ-57).
9. The search on the native sources of Linux and macOS: the V4L2 exposure units [ux A-18] and the
   macOS exposure routes [ux 4.5], on real cameras [K2].
10. The time of a connect with three cameras in `AUTO`, with the search at the open (T-REQ-23,
    1.3b).

## 8. Part 4: the camera number of a take

### 8.1 The rule

- A take uses the camera number of the camera list [G7]. The camera list shows `Camera <n>`, where n
  is `index` of the detection result of the camera (`CameraTreeItem.tsx`).
- The UI sends the number and the name of the current detection with each apply request [G7]: it
  sets `camera_index` and `camera_name` of each config from the current detection result. A stored
  desired config can hold the values of an earlier detection. The request never sends them [H6].
- The server keeps the `camera_index` of the request. It does not replace it with a value of its
  own detection or of the source [H6]. `camera_index` stays unique in a group, as today.
- The recorder writes the number of the request [G7]: `group_position` follows the order of the
  `camera_index` of the request (item 19 of section 16 of [`recorder.md`](recorder.md), a choice of
  its agent). No new
  field goes into the take files [H6]. A new field needs a change of the file format.
- A pure function `withDetectionNumbers(configs, cameras)` in
  `skellycam-ui/src/store/slices/cameras/camera-number.ts` sets the two fields [H6].

### 8.2 Changes to recorder.md

Applied on 2026-11-20 in item 19 of section 16 of [`recorder.md`](recorder.md). The text below is the
record of the change.

Change to item 19 of section 16: "`group_position` is the order of the cameras in the take:
the order of the `camera_index` of the apply request, which is the camera number of the camera list
of the UI (`camera-requests.md` 8.1)."

### 8.3 Tests

| ID | Kind | Set-up | Pass criterion |
|---|---|---|---|
| T-REQ-60 | ui-unit | `withDetectionNumbers`: a stored config of camera a1b2 with `camera_index` 0 and the name "Old name"; a detection result that lists a1b2 with `index` 2 and the name "Logitech C922". | The request config has `camera_index` 2 and `camera_name` "Logitech C922"; each other field does not change [G7]. |
| T-REQ-61 | fake | Two fakes; the apply request gives camera A `camera_index` 2 and camera B `camera_index` 0; the source order is A, then B. Start a take. | The configs of the response keep 2 and 0; in the manifest, B has `group_position` 0 and A has 1 [G7, H6]. |

### 8.4 The UI when a take ends by itself with an error

The user decided: when a take ends by itself with an error, the record button returns to "Start",
and the error and the summary of the take show at once, with no click on "Stop" [ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md). The server side
is [`recorder.md`](recorder.md) 8.4: the live state gets `take_state` `"ended_with_error"` and
`ended_take_summary`. The behaviour is the ruling of the user; the two fields are a proposed design
(item 16 of [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md)).

- The recording slice reads `take_state` of each group from each live state. A change to
  `"ended_with_error"` sets `isRecording` false, clears `recordingName`, `startedAt` and `duration`,
  and sets `completionData` from `ended_take_summary.summary`, as a stop response does.
- The UI shows the error text of `ended_take_summary.take_error` with the camera label of 1.8, and the summary
  dialog of a stop.
- It shows them one time for each take: a pure function `endedTakeNotice(previous, state)` in
  `skellycam-ui/src/store/slices/recording/ended-take.ts` gives the notice only when the group is in
  `"ended_with_error"` with a take (its folder, else its name) that no notice showed yet. It gives `null`
  while the state stays there, and when a record start that fails gives the old take again. A record
  start that succeeds (`"recording"`) clears the shown take, so a later take in the same folder shows its
  notice [ADR-QJH6](../decisions/entries/QJH6-choices-of-the-fix-lane.md).
- The UI sends no stop request for such a take.

| ID | Kind | Set-up | Pass criterion |
|---|---|---|---|
| T-REQ-73 | ui-unit | `endedTakeNotice`: a state with `take_state` `"recording"`; then `"ended_with_error"` with `ended_take_summary`; the same state again; then `"none"`. | `null`; the notice with the error text, the camera label and the summary; `null`; `null` (8.4). |
| T-REQ-76 | ui-manual | The app with two cameras records; the writer of one is held past the stall limit (a test build), or the disk is removed. | Within about 1 s, the record button shows "Start", and the error and the summary show with no click on "Stop" (8.4). |
