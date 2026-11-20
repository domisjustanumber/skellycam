# Amendment to the capture spec: the rule of the gate

Status: proposed by an agent on 2026-11-21; waits for the decision of the user
([ADR-44NW](../decisions/entries/44NW-proposed-gate-rule-newest-frame-at-the-close-of-a-round.md)).

This file does not change [`windows-capture.md`](windows-capture.md). That spec stays accepted, and
D26 stays in force until the user decides. Section 7 gives each sentence that the amendment would
change, with the old text and the new text. Numbers in square brackets (for example [D26], [W4],
[agent 49]) are the marks of `windows-capture.md`. "Section x.y" means a section of that spec, and
"A-x" means a section of this file.

## A-1 Terms

| Term | Meaning |
|---|---|
| round | The making of one group frame: one frame of each camera in the gate, with one gate count. |
| fresh frame | A frame of a camera that is newer than the frame that the camera gave last. |
| hold | The one frame that the loop of a camera took and keeps for the next round. |
| give | The loop gives a frame to the round: it writes the frame to the recorder and the rings (5.1 steps 4 to 9). |
| close | The moment at which a round can be given: each camera in the gate has a fresh frame. |
| spread | The latest minus the earliest arrival time (`arrival_ns`) of the frames of one group frame. |

## A-2 The problem in numbers

Evidence (research checkout, branch `dom/research`; the two files were not committed on 2026-11-21):

- `research/usb_cameras/docs/hardware_run_3a_20261120.md`: the first hardware run of step 3a. Three
  cameras (C922, C930e, Kiyo Pro), 1280x720 MJPG 30 fps, 60 s, two runs.
- `research/usb_cameras/docs/camera_spread_analysis_20261120.md`: an offline analysis of the
  arrival times of that run. No camera was used.

Measured spread by arrival time (median / p95 / max, and the share of group frames above one frame
period of 33.3 ms):

| Run | Gate of today (D26) | Causal rule of A-3, offline |
|---|---|---|
| 1 | 35.8 / 55.4 / 71.3 ms, 70 % | 13.1 / 24.5 / 40 ms |
| 2 | 35.0 / 51.1 / 67.1 ms, 77 % | 13.0 / 25.1 / 41 ms |
| 4-camera run | 39.1 / 54.8 / 66.1 ms, 65 % | 14.0 / 25.1 / 34 ms |

- The best offline pairing (the floor) gave a median of 12.8 to 14.0 ms. The causal rule reaches it.
  Fewer than 0.5 % of its group frames are above 33.3 ms.
- About 13 ms of the median is the phase offset between free-running cameras. No pairing removes it.
- The cause of the other 22 to 25 ms: when a round opens, a camera takes its newest frame at once.
  It cannot change that frame while it waits for the slowest camera. In 61 to 73 % of the rounds, a
  held frame arrived before the previous round closed. D26 allows this. It is not a code fault.
- For a hand that moves at 5 m/s, the position difference between cameras is 18 cm at the median
  today, and 6.5 cm with the causal rule.

The fake-source model of the tests of A-8 gives the same picture. The rule of today gives 38.0 /
54.0 / 70.0 ms with 64.5 % above one period. A throwaway implementation of the rule (not committed)
gives 11.0 / 27.0 / 38.0 ms with 0.3 % above one period (6 of 1,779 group frames).

## A-3 The proposed rule

### A-3.1 Open and close of a round

1. A round opens for a camera when the camera gave its frame of the previous round.
2. At once, the camera waits for a fresh frame. When one arrives, the loop takes it into the hold.
3. A round closes when each camera in the gate (the states of 5.2) has a fresh frame in its hold.
   A camera that leaves the gate does not hold the round (A-4.2, A-4.3).
4. At the close, each camera gives its newest frame. The newest frame is the frame in the hold, or a
   newer frame that waits in the waiting place.

### A-3.2 What each camera gives

- Each group frame holds exactly one frame of each camera in the gate.
- A camera never gives a frame that is older than a frame that it gave before.
- Each given frame arrived after the previous round closed. Thus a camera never gives a frame that
  it held while the previous round waited.
- A camera whose newest frame was already given must wait for a new arrival. It cannot give the same
  frame two times.
- A camera that has a fresh frame holds it. If a newer frame arrives before the close, the newer
  frame replaces the held frame.
- The loop must see a closed round within one wait step (A-3.5). Thus a camera can give a frame that
  arrived up to one wait step after the close. GA-02 accepts 1 ms. The throwaway implementation saw
  the close at once on the virtual clock.

### A-3.3 Replaced frames

- A frame that the camera does not give is a replaced frame. There are two kinds:
  - A newer frame replaced it in the waiting place. The source counts it in `replaced_count` (4.1),
    as today.
  - The loop took it into the hold, and the loop gave a newer frame of the same round. The loop
    counts it.
- The camera reports the sum of the two counts. The decision of the user stays: the count starts at
  the first frame that the camera gives in the gate [agent 49, W4]. The loop reads both counts at
  that frame and reports the increase from then on.
- Thus `replaced_count` equals the sum of the gaps of `source_frame_number` between given frames,
  for each camera (D27). T-CAP-60 checks this on the cameras, and the check stays valid.
- The status sets `replaced_count` at each given frame and at the stop (8.4). The stop line of 5.2
  stays.
- The count of the source alone no longer holds all replaced frames. A test that needs the count
  must read the status or the stop line (T-CAP-91, A-7.4).

### A-3.4 Time of a group frame

- Each frame keeps its arrival time `arrival_ns` as its frame time [D28]. The rule does not change it.
- The multi-frame timing row keeps the mean of the times of the cameras, as today (T-CAP-35).
- The close time of a round is the latest arrival in its group frame, within one wait step.

### A-3.5 Across the camera processes

Each camera is in its own process. Each camera must know that each other camera in the gate has a
fresh frame. Two new fields in `CameraStatus` (shared memory) do this:

| Field | Type | Writer | Content |
|---|---|---|---|
| `fresh_round` | `multiprocessing.Value("q")` | Only the camera process of that camera | The gate count plus 1 while the camera holds a fresh frame for the next round. It equals the gate count when the camera joins the gate (5.2, agent 5). It never falls while the camera stays in the gate. |
| `wake` | `multiprocessing.Event` | Set by each other camera process and by the main process; cleared only by the owner | It wakes a camera that waits for the close. |

- The close test (`should_grab_by_id`): for camera i with gate count n, the round closes when
  `fresh_round > n` for each camera in the gate, camera i included. It reads only shared values.
  This keeps the lockstep of today: no camera can be more than one round ahead of another.
- When a camera writes `fresh_round`, it then sets `wake` of each other camera. When a camera leaves
  the gate (`dead`, `failed`, a reopen), it sets `wake` of each other camera. The main process sets
  `wake` of each camera after an unselect.
- A camera that waits for the close does these steps: it clears its own `wake`; it does the close
  test; if the round is not closed, it waits on `wake` for at most 50 ms. Then it takes a newer frame
  from the waiting place with no wait (`read_frame(0)`), if one is there.
- No wake-up is lost. The writer writes the counter before it sets `wake`. The owner clears `wake`
  before the close test. Thus a change after the test sets `wake`, and the wait returns at once.
- No lock is held across a wait. Each read and each write of a shared value takes the lock of that
  value for a moment only. The wait is `Event.wait` with a timeout.
- No busy loop exists. The wait step of 50 ms equals the sleep of a paused loop. It also bounds the
  time to see an own stream error, a pause, a close or a missed wake.
- The gate wait of today polls each 1 ms. With a camera that waits for a slow camera, GA-07 measured
  3.6 to 3.7 % of one core for the waiting camera process, above the 2 % of T-CAP-49. The
  throwaway implementation measured 0.16 to 0.47 % with a step of 50 ms, and 1.4 to 2.2 % with a step
  of 10 ms. T-CAP-49 tests only a paused process, so it did not find this.

### A-3.6 A pull source

- The OpenCV source has no waiting place (4.4). Each `read_frame` calls `grab()`, which waits for
  the next frame.
- With a pull source, the loop reads one frame, holds it, and gives it at the close. It does not read
  again while it holds. Thus `replaced_count` stays 0 for OpenCV, as today.
- The source tells the loop its kind with a new read-only attribute `pushes_frames`: true for Media
  Foundation and the fake source, false for OpenCV. This is a change of the interface of 4.1.

## A-4 Interactions

### A-4.1 Cameras at different rates

- A camera at 25.76 fps in a 30 fps group cannot occur. It fails the start-up rate check (10.1, D24)
  and is `failed`, so it is never in the gate.
- A camera that slows down later (`too_slow` after a live change, or a slow block during a recording)
  stays in the gate. The rounds then follow the slowest camera, as today. The faster cameras get more
  replaced frames.
- The rate class 30 of U15 (29.97 fps with 30 fps) stays allowed. Each round needs one fresh frame of
  each camera, so the group runs at the lower rate. The 29.97 fps camera has a fresh frame in each
  round and gives each frame. A 30 fps camera has one extra frame about each 1001/30 s = 33.4 s. That
  frame is replaced. Thus the count of U15 does not change: 3 frames in 100 s for each 30 fps camera.
- GA-05 checks this with exact periods (no grid), over 100 s from the first gate frame. Today: 2
  and 2 replaced frames for the two 30 fps cameras; the throwaway implementation: 3 and 3. The
  29.97 fps camera: 0 in both. Both are within the 3 (+/-1) of T-CAP-91. The text of the
  `mixed_rate` warning (7.5) stays.
- With a 16 ms delivery grid, a camera can get one more replaced frame when the last camera of a
  round has a 48 ms interval. A-6 gives the cost.

### A-4.2 A camera that stalls or dies

- Device removed, a stream error or the end of the stream: the camera is `dead` at once (6.7, D38).
  It sets `wake` of the others. The others see it within one wait step. The round closes for them at
  once, if each of them has a fresh frame, or at their next fresh frame.
- A camera that has an error while it holds a frame is `dead` at once. It does not give the held
  frame, because that frame is not in a closed round. Its last given frame is its last frame in the
  recording (5.7, U4).
- Stall (no frame for 2 s, 9.5). Timeline, with the last arrival of camera C at t:

  | Time | What happens |
  |---|---|
  | t | C gave its frame, or holds it. It waits for a fresh frame. |
  | t to t + 2 s | The other cameras take fresh frames and hold them. Each newer arrival replaces the held frame (about 60 replaced frames for each camera, as today). The round stays open. |
  | t + 2 s | The `read_frame` of C times out. C is `dead` and leaves the gate. It sets `wake` of the others. |
  | t + 2 s, plus at most one wait step | Each other camera sees that C is out of the gate. The round closes. Each gives its newest frame, which arrived at most one period plus one grid step before. |

- Thus a round that never closes cannot occur. Only a stall stops a camera from getting a fresh
  frame, and the stall rule ends it after 2 s. This is the same wait as today.
- GA-03 and GA-04 check these cases. In the throwaway implementation, the round closed at the
  error of the dead camera, and within 100 ms after it (the limit of T-CAP-108).

### A-4.3 `failed`, `starting`, `waiting` and unselected cameras

The gate counts the same states as today (5.2, agent 47). A camera in `starting`, `waiting`,
`failed` or `dead`, and an unselected camera, does not hold a round. The warm-up and the start-up
rate check do not use the gate (9.2). No change.

### A-4.4 Pause

- While a camera of the gate has `should_pause`, no round closes, as today.
- A camera that holds a frame keeps it. New frames replace frames in the waiting place and are
  counted, as today.
- After the pause, the round closes when each camera has a fresh frame. At the close, each camera
  gives its newest frame, not the frame that it held before the pause.

### A-4.5 The start of a take, and a camera that joins again

- The cameras in `waiting` join the gate together (9.4), as today. At the join, each camera sets
  `fresh_round` to its gate count and empties its hold. Thus the first group frame closes at the
  first fresh frame of the last camera, at most one period plus one grid step after the join.
- A camera that joins again after "apply again" or a mode change starts with the largest gate count
  of the group [agent 5], and with no fresh frame. A camera one round behind is not held by it.
- A recording starts at a gate count (`first_recording_frame_number`), as today. The rule does not
  change this.

### A-4.6 The rate checks

- The formula of 10.1 counts delivered frames by `source_frame_number`. A replaced frame does not
  change it [agent 26].
- After a live change (10.2): each frame that the loop takes counts in the check, also a held frame
  that a newer frame replaces later. The early decision uses the newest frame that the loop took. A
  frame that arrived in time and waits in the hold or in the waiting place gives no decision
  [agent 88]. A read with no newer frame after the deadline means that frame s_a + 59 did not arrive.
- During a recording (10.3): the blocks of 60 delivered frames do not change.

### A-4.7 The interim decode and the old recorder

- Only the given frame is decoded (5.5), and only when it is recorded or the camera has a BGR ring.
  A held frame that is replaced is never decoded.
- The decode runs on the loop thread after the close. It delays only the wait for the next fresh
  frame. The waiting place keeps the newest frame in that time.
- The old recorder gets the given frame, with the gate count as its frame number, as today.

### A-4.8 The ring writes

Only the given frame reaches the JPEG ring, the BGR ring and the recorder (5.1 steps 6 to 8). A held
frame that is replaced reaches none of them. The ring `frame_number` counts the given frames (5.3).
Thus the frame numbers of the cameras of a group stay equal.

### A-4.9 The preview relay

The interim relay sends the newest ring frame of each camera on its own (5.8, U13). No change. The
frames of one round are closer in time, so the preview of the cameras agrees better.

### A-4.10 Latency

- The latency of a group frame is the age of its oldest frame when its last camera has written it.
- Today: the camera that is first takes its frame at the open and holds it until the last camera
  arrives. The oldest frame is one spread old at the last arrival (36 ms at the median), plus the
  time to give the last frame (one wake and the ring write, a few ms). This is about 40 ms.
- With the rule: the round closes at the last arrival, and the spread is 13 ms at the median. The
  give adds the same few ms. This is about 17 ms.
- With a recording, the interim decode adds 2.6 ms at 720p to both (5.5).

## A-5 The clock: pairing by arrival time or by sample time (optional second step)

This amendment pairs by arrival time (`arrival_ns`, D28). A second, separate step could pair by the
sample time of the camera (`sample_ns`). The user decides it later, after a measurement.

- What is known (T-CAP-59): the sample time of the C922 and the C930e is 0.33 ms before arrival at
  the median. Their driver stamps at delivery, not at exposure. The sample time of the Kiyo Pro is
  about 32 ms before arrival (16 to 48 ms). Arrival times are on a 16 ms grid. Neither clock gives the
  moment of exposure.
- With the Kiyo Pro sample time as a constant offset of 32.3 ms (a model), the analysis found a
  spread of 27.0 / 52.9 ms (median / p95) in run 1, but 58.9 / 75.7 ms in run 2. The data cannot tell
  which clock is true.
- A rule by sample time cannot close a round earlier than the arrival of the frames. It needs a small
  queue of frames for each camera, not one held frame. The waiting place holds one frame (4.3).
- Measure first:
  1. Film one flashing LED, or a board that moves fast, with all cameras of the group. Find the frame
     of each camera that first shows the change. Compare the arrival times and the sample times of
     those frames.
  2. The timing file must carry `sample_ns` and `source_frame_number` for each frame.
- The timing file of the old recorder on this branch has neither field. They are only in the ring
  slots (analysis, "Data").
- The new recorder writes both. Section 6.5 of `specs/recorder.md` (branch `dom/recorder`, accepted
  on 2026-11-20) has one CSV row for each group frame with `source_frame_number`, `arrival_ns` and
  `sample_ns` (empty for `NO_SAMPLE_NS`). That is enough for the LED test, which uses given frames.
- It is not enough to replay another pairing offline. A replay needs the times of each delivered
  frame, also of each replaced frame. No file holds them today. A diagnostic log of each delivered
  frame would be a new item.

## A-6 Costs and risks

- More shared state between the camera processes: two fields for each camera (A-3.5). Each camera
  reads the fields of each other camera at each close test. Each camera process writes into the
  `wake` of each other camera.
- A round that never closes: only a stall can cause it, and the 2 s rule ends it (A-4.2). A camera in
  `too_slow` makes the rounds slow, as today.
- More replaced frames:
  - On the measured data: 0 to 3 more for each camera in 1,800 frames (the analysis, section
    "Conclusion"). The model with each camera on its own 16 ms grid gives the same: 0, 1 and 3
    against 0, 0 and 2 today (about 1,810 rounds).
  - The model with all cameras on ONE common 16 ms grid (arrivals that tie) gives 16, 17 and 19
    against 0, 0 and 2 today, in about 1,800 rounds. The measured data do not show this, but only a
    hardware run of the rule can confirm it. A replaced frame is missing from the recording.
- The rate class 30: the count stays 3 in 100 s with exact periods. The grid can add frames as above.
- A camera with an error while it holds loses its held frame (A-4.2). That frame was never in a
  closed round.
- The wait step of 50 ms: an own stream error of a holding camera is seen up to 50 ms late. That is
  under the 100 ms of T-CAP-108.
- The interface changes by one attribute, `pushes_frames` (A-3.6).
- Not settled by the analysis:
  - Which clock is true (A-5).
  - Where the 25 to 32 replaced frames of each camera in the hardware run fell. Only 0 to 3
    double-period gaps were inside the recorded span. This was not confirmed.
  - A few arrival times of the analysis were interpolated (at most 4 group frames in 1,800).
  - The rule was never run on cameras. The throwaway implementation ran only on fake sources. It
    did not have the pull-source rule of A-3.6, and it did not set `wake` from the main process.

## A-7 What the amendment would change

### A-7.1 Decisions

| Mark | Old text (accepted) | New text (proposed) |
|---|---|---|
| D26 | "Lockstep with a camera that pushes frames: when the gate opens for a camera, it gives the newest frame that has not been taken yet; if there is none, it waits for the next one. Frames that arrive while the gate is closed are replaced by newer ones and counted." | "Lockstep with a camera that pushes frames: a round closes when each camera in the gate has a frame newer than the frame that it gave last. Each camera then gives its newest frame. Frames that it took or that arrived before that count as replaced." |
| D27 | "(a gap shows frames that lockstep did not take)" | "(a gap shows frames that lockstep did not give)" |
| W4 | "counted from the first frame that the camera takes in the gate" | "counted from the first frame that the camera gives in the gate" |
| agent 49 | "`replaced_count` is reported from the first frame that the camera takes in the gate" | "`replaced_count` is the count of the source plus the frames that the loop took and did not give, reported from the first frame that the camera gives in the gate" |
| agent 5 | "a camera that joins the gate again takes the largest gate count of the group" | Add: "and it joins with no fresh frame (`fresh_round` equals its gate count)" |
| new agent items | none | The shared fields `fresh_round` and `wake` and the wait of A-3.5; the wait step of 50 ms; the pull-source rule and `pushes_frames` (A-3.6); a camera with an error while it holds does not give the held frame (A-4.2) |

D28 (arrival time), D38 (dead camera), U4, U13, U15 (the count and the warning), agent 47 and
agent 88 stay as they are.

### A-7.2 Spec sentences

| Section | Old text (accepted) | New text (proposed) |
|---|---|---|
| 1.5, "replaced frame" | "A delivered frame that a newer frame replaced before the loop took it [D26]." | "A delivered frame that the loop did not give: a newer frame replaced it in the waiting place, or the loop held it and gave a newer frame of the same round." |
| 1.5, new term | none | "given frame: the frame that the loop gives to a group frame: to the recorder and the rings." |
| 2.1 item 3 | "Both counts start at the first frame that the camera takes in the gate (5.2)." | "Both counts start at the first frame that the camera gives in the gate (5.2)." |
| 4.1 | "The loop reads it at the first frame that the camera takes in the gate, and it reports the difference from then on (5.2) [agent 49]." | "The loop adds the frames that it took and did not give. It reads both counts at the first frame that the camera gives in the gate, and it reports the increase from then on (5.2)." |
| 4.1, new sentence | none | "A source has the read-only attribute `pushes_frames`: true for Media Foundation and the fake source, false for OpenCV." |
| 4.3, camera loop thread | "Waits only in `read_frame`, on the condition of the waiting place, with a timeout [ring 8.10]." | "Waits in `read_frame`, on the condition of the waiting place, with a timeout, or on the `wake` event of its camera for at most 50 ms (5.2) [ring 8.10]. It does not poll the gate each 1 ms." |
| 5.1 step 1 | "**Gate.** Wait until `should_grab_by_id` is true for this camera (5.2)." | "**Fresh frame.** `read_frame` gives a frame newer than the frame that the camera gave last. The loop holds it and sets `fresh_round` (5.2)." |
| 5.1 step 2 | "**Read.** `read_frame` gives the newest frame [D26]." | "**Close.** Wait until the round closes (`should_grab_by_id` is true). A newer frame replaces the held frame. At the close, the loop gives its newest frame (5.2)." |
| 5.2 bullet 1 | "When the gate opens for a camera, the loop takes the newest frame that it has not taken yet. If there is none, it waits for the next one [D26]." | The rule of A-3.1, A-3.2 and A-3.5. |
| 5.2 bullet 2 | "Frames that arrive while the gate is closed are replaced by newer frames and counted in `replaced_count` [D26]." | "Frames that the camera does not give are replaced, in the waiting place or in the hold, and counted in `replaced_count` (A-3.3)." |
| 5.2 bullet 3 | "the number of frames replaced since the first frame that the camera took in the gate" | "the number of frames replaced since the first frame that the camera gave in the gate" |
| 5.2 bullet 5 | "starts with the largest gate count of the group [agent 5]" | "starts with the largest gate count of the group and with no fresh frame [agent 5]" |
| 5.3 bullet 1 | "the count of frames that the loop took since the ring was created" | "the count of frames that the loop gave since the ring was created" |
| 7.5, rate class 30 | "No frame is repeated, because the gate waits for the next frame." | "No frame is repeated, because a round waits for a fresh frame of each camera." |
| 8.4 | "the frames replaced since the first frame that the camera took in the gate" | "the frames replaced since the first frame that the camera gave in the gate" |
| 10.2, new sentence | none | "Each frame that the loop takes counts in the check, also a held frame that a newer frame replaces later." |
| 16.4 | "both from the first frame that the camera takes in the gate (5.2)" | "both from the first frame that the camera gives in the gate (5.2)" |
| 17.3, new item | none | "The gate pairs by arrival time. Which clock is true is not known (A-5). On one common delivery grid, the rule can replace more frames (A-6)." |

### A-7.3 New tests

GA-01 to GA-07 of A-8 would become T-CAP-114 to T-CAP-120. T-CAP-114 to T-CAP-119 are of the kind
"fake". T-CAP-120 (GA-07) is of the kind "local", as T-CAP-49, because it measures process CPU. The
table of 16.5 would add them to the row of D26. The counts of 16.6 would change by six fake tests
and one local test in step 3a.

### A-7.4 Changed tests

| Test | Change |
|---|---|
| T-CAP-05 | Criterion text: "from the first frame taken in the gate" becomes "from the first frame given in the gate". The code needs no change. It passed with the throwaway implementation. |
| T-CAP-91 | The test reads `replaced_count` of the fake source. With the rule, a replaced frame of a 30 fps camera is a held frame that the loop drops, so the source count stays 0. The test must read the `replaced_count` of the status (8.4) or the stop line. It failed with the throwaway implementation only for this reason ("0 frames replaced in 100 s"). |
| T-CAP-107, T-CAP-113, T-CAP-60, T-CAP-98 | No change of text or code. T-CAP-107 and T-CAP-113 passed with the throwaway implementation. |

With the throwaway implementation, the capture suite gave 133 passed, 1 failed (T-CAP-91) and 47
skipped, with T-CAP-46 and the seven new tests deselected.

### A-7.5 What does not change

- The waiting place, `read_frame` and the replaced count of the source (4.1 to 4.3), except
  `pushes_frames`.
- The frame time (D28), `sample_ns` in the slot header, and the timing columns (5.4).
- The states, their transitions and the states that the gate counts (section 8, 5.2).
- Start-up, warm-up, the ready limit and the wait for the others (section 9).
- The rate checks and their limits (section 10).
- The stall rule of 2 s and the dead-camera rules (6.7, 9.5, D38, U4).
- The one-rate rule, the rate class 30 and its warning (7.5, D18, U15).
- The interim decode, the old recorder, the rings and the preview relay (5.5, 5.8).

## A-8 The failing tests

`skellycam/tests/capture/test_gate_amendment.py` holds GA-01 to GA-07. They have the marker
`gate_amendment`. The default selection (`addopts` in `pyproject.toml`) and the selections of
`.github/workflows/capture.yml` deselect them. Run them with
`uv run pytest skellycam/tests/capture -m gate_amendment`.

The arrival model of GA-01 to GA-06: true periods of 33.333, 33.313 and 33.279 ms (section 4 of the
analysis); each camera on its own 16 ms grid (intervals of 32 or 48 ms); the second camera 32 ms
late, with its sample time 32.3 ms before its arrival. GA-02 puts all cameras on one common grid.

| Test | What it proves | Today (D26) | Throwaway implementation |
|---|---|---|---|
| GA-01 | Spread: median under 17 ms; at most 0.5 % above one period; none above one period plus one grid step | Fails: 38.0 / 54.0 / 70.0 ms, 64.5 % above | Passes: 11.0 / 27.0 / 38.0 ms, 0.3 % above |
| GA-02 | `replaced_count` of the status equals the gaps at each given frame; each camera gives its newest frame at the close | Fails: 1,292 of 1,779 rounds give an older frame (the counts agree) | Passes; replaced 16, 17 and 19 |
| GA-03 | A camera that dies does not hold the round: the round closes at the error and within 100 ms | Fails: a live camera gave its frame of that round 11 ms before the error | Passes |
| GA-04 | A stalled camera is `dead` 2.0 to 2.25 s after its last arrival; the round then closes with the newest frames | Fails: the live frames of that round are 1,957 ms old | Passes |
| GA-05 | 29.97 fps with two 30 fps cameras: 3 (+/-1) replaced frames in 100 s for each 30 fps camera, 0 for the 29.97 fps camera, 2997 (+/-2) group frames; no held frame from before the previous close | Fails on the held frames only: 2,819 of 3,027 rounds; replaced 0, 2 and 2 | Passes; replaced 0, 3 and 3 |
| GA-06 | One frame of each camera in each group frame; no older frame; each frame arrived after the previous close | Fails: 1,162 of 1,803 rounds (64 %) | Passes |
| GA-07 | A camera that waits for a 1 fps camera: process CPU under 2 %; its frame is at most one period plus 16 ms from the frame of the slow camera | Fails: 3.6 % CPU; frames about 1,005 ms apart | Passes: 0.16 to 0.47 % CPU; frames 8 to 30 ms apart |

The first wording of GA-01 was "no group frame above one frame period". With a 16 ms delivery
grid, the causal rule of the analysis also had fewer than 0.5 % of group frames above one period.
Thus GA-01 uses that bound, and a hard bound of one period plus one grid step.

## A-9 Questions for the user

Each question is worded so that "yes" accepts the recommendation.

1. Do you accept the rule of A-3 in place of D26: a round closes when each camera in the gate has a
   frame newer than the frame that it gave last, each camera then gives its newest frame, and the
   frames that it took earlier count as replaced? Recommendation: yes. It removes about 23 ms of the
   36 ms median spread, at a cost of 0 to 3 more replaced frames in 1,800 on the measured data.
2. Do you accept the shared fields `fresh_round` and `wake` of A-3.5, with a wait of at most 50 ms
   and no poll of the gate each 1 ms? Recommendation: yes. The gate of today used 3.6 % of one core
   in GA-07, above the 2 % of T-CAP-49.
3. Do you accept that a camera with an error while it holds a frame is `dead` at once and does not
   give that frame? Recommendation: yes. The frame was never in a closed round.
4. Do you accept the seven tests of A-8 as T-CAP-114 to T-CAP-120, with the bound of 0.5 % in
   GA-01, and the change of T-CAP-91 of A-7.4? Recommendation: yes.
5. Do you accept that the gate keeps pairing by arrival time now, and that pairing by sample time
   waits for the LED or moving-board test of A-5? Recommendation: yes.
6. Do you want a three-camera hardware run of the rule (as `hardware_run_3a_20261120.md`, with the
   spread and the replaced counts) as a done item of the change? Recommendation: yes. Only a camera
   run can show whether the cameras share one delivery grid (A-6).
