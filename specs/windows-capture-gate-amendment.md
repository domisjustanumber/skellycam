# Amendment to the capture spec: the rule of the gate

Status: proposed by an agent on 2026-11-21; waits for the decision of the user
([ADR-44NW](../decisions/entries/44NW-proposed-gate-rule-newest-frame-at-the-close-of-a-round.md)).
Revised on 2026-11-21 after an independent review: the close time of A-3.5, ranges from four real
runs, the rate class 30 on the delivery grid, more wake sources, the pull source, a pause rule and
two more tests.

This file does not change [`windows-capture.md`](windows-capture.md). That spec stays accepted, and
D26 stays in force until the user decides. Section A-7 gives each sentence that the amendment would
change, with the old text and the new text. Marks in square brackets (for example [D26], [W4],
[agent 49]) are the marks of `windows-capture.md`. "Section x.y" means a section of that spec, and
"A-x" means a section of this file.

## A-1 Terms

| Term | Meaning |
|---|---|
| round | The making of one group frame: one frame of each camera in the gate, with one gate count. |
| fresh frame | A frame of a camera that is newer than the frame that the camera gave last. |
| first fresh frame | The first fresh frame that a camera takes (or keeps) for a round. |
| close | The moment at which each camera in the gate has a first fresh frame for the round. |
| close time | The latest arrival time of the first fresh frames of the round, or the time of a gate change if that is later (A-3.5). |
| give | The loop gives a frame to the round: it writes the frame to the recorder and the rings (5.1 steps 4 to 9). |
| wake delay | The time from the close to the moment at which a waiting camera sees it. |
| spread | The latest minus the earliest arrival time (`arrival_ns`) of the frames of one group frame. |
| lost frame | A frame that a camera delivered and did not give: a replaced frame (1.5). |

## A-2 The problem and the trade, in numbers

Evidence (research checkout, branch `dom/research`; not committed on 2026-11-21):

- `research/usb_cameras/docs/hardware_run_3a_20261120.md`: the first hardware run of step 3a. Three
  cameras (C922, C930e, Kiyo Pro), 1280x720 MJPG 30 fps, 60 s.
- `research/usb_cameras/docs/camera_spread_analysis_20261120.md`: an offline analysis of the arrival
  times of that run. No camera was used.
- An independent review replayed the rule on the real arrival times of four runs of that session
  (runs 1 and 2, the four-camera run and the T-CAP-60 run), with phase sweeps, wake delays and a
  model of the protocol. Its scripts are scratch files. They are not kept.

Summary, by arrival time, on the real arrival times of four runs (ranges over the runs):

| Item | Gate of today (D26) | Proposed rule with the close time |
|---|---|---|
| Spread, median | 35.0 to 39.1 ms (measured) | 13.0 to 18.9 ms |
| Spread, p95 | 51.1 to 55.4 ms | 24.5 to 30.3 ms |
| Spread, max | 66 to 71 ms | 34 to 46 ms |
| Group frames above one period (33.3 ms) | 60 to 77 % | 0.17 to 0.72 % (up to 0.9 % over all phase offsets) |
| Lost frames per camera per 1,800 | 0 to 3 (model: at most 4) | 0 to 3; at most 6 over all phase offsets; at most 10 at exact ties |
| Lost frames with wake delays up to 10 ms | 2 to 4 | at most 6 (the first wording of this amendment: 27 to 33 at 5 ms, 62 to 68 at 10 ms) |
| Group latency, median (A-4.10) | 33.6 to 40.5 ms (model) | 16.5 to 22.4 ms |

The trade in plain words: the spread falls by about 20 ms at the median. The cost is 1 to 3 more
lost frames per camera per minute, and up to about 10 in the worst phase. In the worst case, about
0.3 % of the frames are lost (0.55 % at exact ties), against about 0.2 % today.

- About 13 ms of the spread is the phase offset between free-running cameras. No pairing removes it.
- The cause of the rest: under D26, a camera takes its newest frame when a round opens. It cannot
  change that frame while it waits for the slowest camera. In 61 to 73 % of the rounds, a held frame
  arrived before the previous round closed. D26 allows this. It is not a code fault.
- For a hand that moves at 5 m/s, the position difference between cameras is 18 cm at the median
  today, and 6.5 cm with the rule (the analysis).

What the review ruled out:

- The cameras do NOT share one delivery grid. Each camera delivers on its own exact 16.000 ms grid,
  with a fixed phase in each run. The phases were 2.5 to 8 ms apart. The 16 to 19 extra lost frames
  of a common-grid model in the first version of this amendment do not apply. Exact ties of the
  real arrival patterns gave 3 to 10 lost frames.
- A simpler rule with no shared state (the protocol of today, but a frame that arrived before the
  gate opened is dropped) needs a tuned back-off constant. With wake delays up to 5 ms it lost 26 to
  52 frames per camera per 1,800. It is not recommended. This amendment proposes no tunable.
- The model of the cross-process protocol (random schedules with stalls, a death, a kill, an
  unselect and a pause) found no deadlock, no lost wake-up, no frame given two times or out of order,
  and gate counts never more than one apart. That model covered the protocol before the close time
  of A-3.5 was added.

## A-3 The proposed rule

### A-3.1 Open and close of a round

1. A round opens for a camera when the camera gave its frame of the previous round.
2. The camera then waits for a fresh frame, unless it kept one at its last give (A-3.2). When a fresh
   frame arrives, the loop takes it, and it publishes the round and the arrival time of that first
   fresh frame (A-3.5).
3. The round closes when each camera in the gate (the states of 5.2) has published a first fresh
   frame for the round. A camera that leaves the gate does not hold the round (A-4.2, A-4.3).
4. The close time is the latest arrival time of the first fresh frames of the round. A gate change
   during the round (a camera leaves the gate, or an unpause) moves the close time to the time of
   that change (A-3.5).
5. One close time is stored for each round. Each camera uses that one stored value.

### A-3.2 What each camera gives

- At the close, each camera gives its newest frame that arrived by the close time.
- A frame that the camera takes after the close and that arrived after the close time is not given.
  The camera keeps it as its first fresh frame of the next round. The frames between the given frame
  and the kept frame are lost.
- The loop keeps the frames that it took since its last give. In practice these are one or two
  frames. The close time is never earlier than an arrival time in a published pair of the round.
  Thus the loop can drop a taken frame when a newer taken frame arrived by the latest arrival time in
  the pairs that it read. A dropped frame is lost.
- Each group frame holds exactly one frame of each camera in the gate.
- A camera never gives a frame that is older than a frame that it gave before. It never gives a
  frame two times.
- Each given frame arrived after the close time of the previous round.
- Why this matters: a waiting camera sees the close after a wake delay. A frame that arrives in that
  delay must not replace the frame of the round. Without the close time, each such frame moves the
  camera one grid step later in the next round, and frames are lost (A-2).

### A-3.3 Replaced (lost) frames

- A frame that the camera does not give is a replaced frame. There are two kinds:
  - A newer frame replaced it in the waiting place. The source counts it in `replaced_count` (4.1).
  - The loop took it and did not give it. The loop counts it.
- The camera reports the sum of the two counts. The decision of the user stays: the count starts at
  the first frame that the camera gives in the gate [agent 49, W4].
- Thus `replaced_count` equals the sum of the gaps of `source_frame_number` between given frames,
  for each camera (D27). T-CAP-60 checks this on the cameras, and the check stays valid.
- The status sets `replaced_count` at each given frame and at the stop (8.4).
- The count of the source alone no longer holds all replaced frames. A test must count the gaps of
  `source_frame_number` over the given frames (T-CAP-91, A-7.4).

### A-3.4 Time of a group frame

- Each frame keeps its arrival time `arrival_ns` as its frame time [D28].
- The multi-frame timing row keeps the mean of the times of the cameras, as today (T-CAP-35).
- The close time is the latest arrival time in the group frame, except after a gate change.

### A-3.5 Across the camera processes

Each camera is in its own process. These shared fields do the work:

| Field | Where | Type | Writer | Content |
|---|---|---|---|---|
| `fresh` | `CameraStatus` of each camera | `multiprocessing.Array("q", 2)` | Only the camera process of that camera | `[round, arrival_ns]`: the round for which the camera has a first fresh frame, and the arrival time of that frame. |
| `wake` | `CameraStatus` of each camera | `multiprocessing.Event` | Set by the other camera processes and by the main process; cleared only by the owner | It wakes a camera that waits for the close. |
| `round_close` | `CameraOrchestrator` | `multiprocessing.Array("q", 2)` | The first camera process that finds the round closed | `[round, close_ns]`: the close time of the latest closed round. |
| `gate_changed_ns` | `CameraOrchestrator` | `multiprocessing.Value("q")` | The process that makes a gate change | The time of the latest gate change. |

Writes:

- A camera writes both values of `fresh` in one write, under the lock of that array. It writes
  `[n + 1, arrival]` when it takes or keeps the first fresh frame for round n + 1 (n is its gate
  count). Then it sets `wake` of each other camera.
- At a join (9.4, and after "apply again" or a mode change), the camera writes `[n, 0]` (no fresh
  frame) BEFORE its state becomes `ready`.
- A gate change sets `gate_changed_ns` to the larger of its value and the time now, under its lock,
  and then sets `wake` of each camera. The gate changes are: a camera becomes `dead` or `failed`; a
  camera leaves the gate for a reopen; the main process unselects a camera; the main process marks
  an ended (killed) camera process; the main process ends a pause.

The close test of camera i with gate count n. It runs under the lock of `round_close`, and it never
waits:

1. If `round_close` holds round n + 1, the round is closed. The close time is the stored value. This
   also applies during a pause (A-4.4).
2. Else, if a camera in the gate has `should_pause`, the round is open.
3. Else the test reads `fresh` of each camera in the gate, each under the lock of that array (one
   consistent pair). If each round is above n, the close time is the largest of the arrival times of
   the pairs with round n + 1 and of `gate_changed_ns`. The test writes `[n + 1, close time]` to
   `round_close`. The round is closed.
4. Else the round is open.

Locks and waits:

- The lock order is always `round_close`, then the lock of one `fresh`. An owner takes only the lock
  of its own `fresh`. Thus no deadlock can occur.
- No lock is held across a wait. Each lock is held for a few reads or writes only.
- This keeps the lockstep of today: no camera can be more than one round ahead of another. A camera
  that gave round n + 1 and holds a fresh frame for round n + 2 has round n + 2 in its pair. Round
  n + 1 is then already in `round_close`, so a later camera uses the stored close time.

The wait:

- A camera that waits for the close clears its own `wake`, does the close test, and if the round is
  open, waits on `wake` for at most 50 ms. Then it takes a newer frame from the waiting place with no
  wait (`read_frame(0)`), if one is there.
- No wake-up is lost. A writer writes its field before it sets `wake`. The owner clears `wake`
  before the close test. Thus a change after the test sets `wake`, and the wait returns at once.
- No busy loop exists. The step of 50 ms equals the sleep of a paused loop. Each event that can
  close a round sets `wake`, so the step is only a bound for an own stream error and for a missed
  event.
- The gate of today polls each 1 ms. With a camera that waits for a slow camera, GA-07 measured 3.6
  to 4.8 % of one core for the waiting camera process, above the 2 % of T-CAP-49. A throwaway
  implementation of this rule measured 0.16 to 1.09 %. T-CAP-49 tests only a paused process, so it
  did not find this.

### A-3.6 A pull source (OpenCV)

- The OpenCV source has no waiting place (4.4). Each `read_frame` calls `grab()`, which waits for
  the next frame.
- With a pull source, the loop reads one frame after its own give, holds it, publishes its pair and
  gives that frame at the close. It never reads a pull source while it holds a frame. Thus
  `replaced_count` stays 0 for OpenCV, as today.
- The rule for a pull source is "the first frame after my own give", not "the newest frame by the
  close time". Thus Linux and macOS do not get the spread of Windows. This is a known limit until
  native capture exists there (phase 7). GA-09 guards the rule.
- The source tells the loop its kind with a new read-only attribute `pushes_frames`: true for Media
  Foundation and the fake source, false for OpenCV. This is a change of the interface of 4.1.

## A-4 Interactions

### A-4.1 Cameras at different rates

- A camera at 25.76 fps in a 30 fps group cannot occur. It fails the start-up rate check (10.1, D24).
- A camera that slows down later (`too_slow`, or a slow block during a recording) stays in the gate.
  The rounds then follow the slowest camera, as today.
- The rate class 30 of U15 (29.97 fps with 30 fps) stays allowed. The group runs at the lower rate.
  With exact periods, a 30 fps camera loses one frame about each 1001/30 s = 33.4 s, as the warning
  text says (3 in 100 s), and the 29.97 fps camera loses none.
- With the real 16 ms delivery grid, this is not true. A model of the review stretches the real
  arrival pattern of one camera of the 60 s runs by 1.001 and scales the counts to 100 s:

  | Per 100 s (model) | Gate of today | Proposed rule |
  |---|---|---|
  | 29.97 fps camera, mean / max | 0.2 / 1.7 | 0.9 / 6.7 |
  | Worst 30 fps camera, mean / max | 4.1 / 8.3 | 5.7 / 10.0 |

- Thus "the 29.97 fps camera gives each frame" is false with the grid, and the warning text "one
  frame about every 33 s" is less true with the rule than today. It is already approximate today.
  Question 7 of A-9 proposes a corrected text.
- GA-05 runs this case on the grid model with one phase set, and compares with the rule replayed
  offline on the same arrival times. For that set: today 0, 2 and 2 lost frames in 100 s; the rule 0,
  3 and 3.

### A-4.2 A camera that stalls or dies

- Device removed, a stream error or the end of the stream: the camera is `dead` at once (6.7, D38).
  This is a gate change: the close time moves to the time of the death. The others see it at once
  (`wake`) and give their newest frames by that time.
- A camera that has an error while it holds a frame is `dead` at once. It does not give the held
  frame, because that frame is not in a closed round.
- Stall (no frame for 2 s, 9.5). Timeline, with the last arrival of camera C at t:

  | Time | What happens |
  |---|---|
  | t | C gave its frame, or holds it. It waits for a fresh frame. |
  | t to t + 2 s | The other cameras have first fresh frames. They take newer frames as they arrive (about 60 lost frames for each camera, as today). The round stays open. |
  | t + 2 s | The `read_frame` of C times out. C is `dead`. This is a gate change at t + 2 s. |
  | t + 2 s, plus the wake delay | The round closes with the close time t + 2 s. Each other camera gives its newest frame by then, which arrived at most one period plus one grid step before. |

- Thus a round that never closes cannot occur. Only a stall stops a camera from getting a fresh
  frame, and the stall rule ends it after 2 s, as today.
- GA-03 and GA-04 check these cases.

### A-4.3 `failed`, `starting`, `waiting`, unselected and killed cameras

The gate counts the same states as today (5.2, agent 47). A camera in `starting`, `waiting`,
`failed` or `dead`, and an unselected camera, does not hold a round. An unselect and the end of a
killed camera process are gate changes, and the main process sets `wake` of each camera. Thus a
kill costs the time of the process watch of the main process, with no added wait step.

### A-4.4 Pause

- While a camera of the gate has `should_pause`, no round closes, as today.
- If another camera already gave the round (it is in `round_close`), a camera gives it also during
  a pause. Thus a round never spans the whole pause because one camera gave before the pause and the
  others after it. (The rule of today allows that.)
- A camera that holds a frame keeps it. New frames replace frames in the waiting place and are
  counted, as today.
- The end of a pause is a gate change. The first round after the pause closes with the time of the
  unpause as its close time, so each camera gives its newest frame, not the frame that it held
  before the pause.

### A-4.5 The start of a take, and a camera that joins again

- The cameras in `waiting` join the gate together (9.4), as today. Each writes `fresh` = `[n, 0]`
  before it becomes `ready`. The first group frame closes at the first fresh frame of the last
  camera, at most one period plus one grid step after the join.
- A camera that joins again starts with the largest gate count of the group [agent 5], and with no
  fresh frame.
- A recording starts at a gate count (`first_recording_frame_number`), as today.

### A-4.6 The rate checks

- The formula of 10.1 counts delivered frames by `source_frame_number`. A lost frame does not change
  it [agent 26].
- After a live change (10.2): each frame that the loop takes counts in the check, also a frame that
  it does not give. A frame that arrived in time and waits in the loop or in the waiting place gives
  no decision [agent 88].
- During a recording (10.3): the blocks of 60 delivered frames do not change.

### A-4.7 The interim decode and the old recorder

- Only the given frame is decoded (5.5), and only when it is recorded or the camera has a BGR ring.
- The decode runs on the loop thread after the close. The waiting place keeps the newest frame in
  that time.
- The old recorder gets the given frame, with the gate count as its frame number, as today.

### A-4.8 The ring writes

Only the given frame reaches the JPEG ring, the BGR ring and the recorder (5.1 steps 6 to 8). A frame
that the loop does not give reaches none of them. The ring `frame_number` counts the given frames.

### A-4.9 The preview relay

The interim relay sends the newest ring frame of each camera on its own (5.8, U13). No change.

### A-4.10 Latency

- The latency of a group frame is the age of its oldest frame when its last camera has written it.
- Today: the first camera takes its frame at the open and holds it until the last camera arrives.
  The review model gives 33.6 to 40.5 ms at the median (four runs).
- With the rule: the round closes at the last first fresh frame. The oldest frame is one spread old
  then, plus the give (one wake and the ring write). The review replay gives 16.5 to 22.4 ms.
- With a recording, the interim decode adds 2.6 ms at 720p to both (5.5).

## A-5 The clock: pairing by arrival time or by sample time (optional second step)

This amendment pairs by arrival time (`arrival_ns`, D28). A second, separate step could pair by the
sample time of the camera (`sample_ns`). The user decides it later, after a measurement.

- What is known (T-CAP-59): the sample time of the C922 and the C930e is 0.33 ms before arrival at
  the median. Their driver stamps at delivery. The sample time of the Kiyo Pro is about 32 ms before
  arrival (16 to 48 ms). Neither clock gives the moment of exposure.
- With the Kiyo Pro sample time as a constant offset of 32.3 ms (a model), the analysis found a
  spread of 27.0 / 52.9 ms (median / p95) in run 1, but 58.9 / 75.7 ms in run 2.
- A rule by sample time cannot close a round before the frames arrive. It needs a small queue of
  frames for each camera.
- Measure first:
  1. Film one flashing LED, or a board that moves fast, with all cameras of the group. Find the frame
     of each camera that first shows the change. Compare the arrival times and the sample times.
  2. The timing file must carry `sample_ns` and `source_frame_number` for each frame.
- The timing file of the old recorder on this branch has neither field. They are only in the ring
  slots.
- The new recorder writes both. Section 6.5 of `specs/recorder.md` (branch `dom/recorder`, accepted
  on 2026-11-20) has one CSV row for each group frame with `source_frame_number`, `arrival_ns` and
  `sample_ns`. That is enough for the LED test, which uses given frames.
- It is not enough to replay another pairing offline. A replay needs the times of each delivered
  frame, also of each lost frame. A log of each delivered frame is needed (also for the trial of
  question 4 of A-9).

## A-6 Costs and risks

- More shared state: two fields for each camera and two for the group (A-3.5), and one group lock
  for each close test.
- A round that never closes: only a stall can cause it, and the 2 s rule ends it (A-4.2).
- More lost frames: A-2 gives the ranges. A lost frame is missing from the recording.
- The rate class 30: more lost frames than the warning text says (A-4.1).
- A camera with an error while it holds loses its held frame (A-4.2).
- The wait step of 50 ms: an own stream error of a holding camera is seen up to 50 ms late. That is
  under the 100 ms of T-CAP-108.
- The interface changes by one attribute, `pushes_frames` (A-3.6). Linux and macOS keep a spread
  like today until phase 7.
- Not settled:
  - Which clock is true (A-5).
  - Where the 25 to 32 replaced frames of each camera in the first hardware run fell. Only 0 to 3
    double-period gaps were inside the recorded span. A log of each delivered frame can show it.
  - The rule was never run on cameras. The throwaway implementation ran only on fake sources. It did
    not set `wake` from the main process at a kill.
  - The protocol model of the review did not include the close-time fields.

## A-7 What the amendment would change

### A-7.1 Decisions

| Mark | Old text (accepted) | New text (proposed) |
|---|---|---|
| D26 | "Lockstep with a camera that pushes frames: when the gate opens for a camera, it gives the newest frame that has not been taken yet; if there is none, it waits for the next one. Frames that arrive while the gate is closed are replaced by newer ones and counted." | "Lockstep with a camera that pushes frames: a round closes when each camera in the gate has a frame newer than the frame that it gave last. The close time is the latest arrival time of those first fresh frames, or the time of a gate change. Each camera then gives its newest frame that arrived by the close time and keeps a later frame for the next round. The other frames count as replaced." |
| D27 | "(a gap shows frames that lockstep did not take)" | "(a gap shows frames that lockstep did not give)" |
| W4 | "counted from the first frame that the camera takes in the gate" | "counted from the first frame that the camera gives in the gate" |
| agent 49 | "`replaced_count` is reported from the first frame that the camera takes in the gate" | "`replaced_count` is the count of the source plus the frames that the loop took and did not give, reported from the first frame that the camera gives in the gate" |
| agent 5 | "a camera that joins the gate again takes the largest gate count of the group" | Add: "and it joins with no fresh frame (`fresh` = `[n, 0]`, written before `ready`)" |
| U15 | The warning text of 7.5 | Unchanged, or the corrected text of question 7 of A-9 |
| new agent items | none | The fields and the close test of A-3.5; the wait step of 50 ms and the wake sources; the pull-source rule and `pushes_frames` (A-3.6); no give of a held frame after an error (A-4.2); a round already given is given also during a pause (A-4.4) |

D28, D38, U4, U13, agent 47 and agent 88 stay as they are.

### A-7.2 Spec sentences

| Section | Old text (accepted) | New text (proposed) |
|---|---|---|
| 1.5, "replaced frame" | "A delivered frame that a newer frame replaced before the loop took it [D26]." | "A delivered frame that the loop did not give: a newer frame replaced it in the waiting place, or the loop took it and did not give it." |
| 1.5, new term | none | "given frame: the frame that the loop gives to a group frame: to the recorder and the rings." |
| 2.1 item 3 | "Both counts start at the first frame that the camera takes in the gate (5.2)." | "Both counts start at the first frame that the camera gives in the gate (5.2)." |
| 4.1 | "The loop reads it at the first frame that the camera takes in the gate, and it reports the difference from then on (5.2) [agent 49]." | "The loop adds the frames that it took and did not give. It reads both counts at the first frame that the camera gives in the gate, and it reports the increase from then on (5.2)." |
| 4.1, new sentence | none | "A source has the read-only attribute `pushes_frames`: true for Media Foundation and the fake source, false for OpenCV." |
| 4.3, camera loop thread | "Waits only in `read_frame`, on the condition of the waiting place, with a timeout [ring 8.10]." | "Waits in `read_frame`, on the condition of the waiting place, with a timeout, or on the `wake` event of its camera for at most 50 ms (5.2) [ring 8.10]. It does not poll the gate each 1 ms." |
| 5.1 step 1 | "**Gate.** Wait until `should_grab_by_id` is true for this camera (5.2)." | "**Fresh frame.** Take a frame newer than the frame that the camera gave last, or use the frame kept at the last give, and publish its pair (5.2)." |
| 5.1 step 2 | "**Read.** `read_frame` gives the newest frame [D26]." | "**Close.** Wait until the round closes. Give the newest taken frame that arrived by the close time, and keep a later frame for the next round (5.2)." |
| 5.2 bullet 1 | "When the gate opens for a camera, the loop takes the newest frame that it has not taken yet. If there is none, it waits for the next one [D26]." | The rule of A-3.1, A-3.2 and A-3.5. |
| 5.2 bullet 2 | "Frames that arrive while the gate is closed are replaced by newer frames and counted in `replaced_count` [D26]." | "Frames that the camera does not give are replaced, in the waiting place or in the loop, and counted in `replaced_count` (A-3.3)." |
| 5.2 bullet 3 | "the number of frames replaced since the first frame that the camera took in the gate" | "the number of frames replaced since the first frame that the camera gave in the gate" |
| 5.2 bullet 5 | "starts with the largest gate count of the group [agent 5]" | "starts with the largest gate count of the group and with no fresh frame [agent 5]" |
| 5.2, new bullets | none | The pause rule of A-4.4 and the gate changes of A-3.5. |
| 5.3 bullet 1 | "the count of frames that the loop took since the ring was created" | "the count of frames that the loop gave since the ring was created" |
| 7.5, rate class 30 | "No frame is repeated, because the gate waits for the next frame." | "No frame is repeated, because a round waits for a fresh frame of each camera. With the delivery grid, each camera can lose more frames than the interval gives (A-4.1)." |
| 8.4 | "the frames replaced since the first frame that the camera took in the gate" | "the frames replaced since the first frame that the camera gave in the gate" |
| 10.2, new sentence | none | "Each frame that the loop takes counts in the check, also a frame that it does not give." |
| 14.1, new sentence | none | "With the OpenCV source, the gate gives the first frame after the own give of each camera (A-3.6). The spread stays as before until phase 7." |
| 16.4 | "both from the first frame that the camera takes in the gate (5.2)" | "both from the first frame that the camera gives in the gate (5.2)" |
| 17.3, new item | none | "The gate pairs by arrival time. Which clock is true is not known (A-5). The rule loses 1 to 3 more frames per camera per minute than D26 (A-2)." |

### A-7.3 New tests

GA-01 to GA-09 of A-8 would become T-CAP-114 to T-CAP-122. T-CAP-120 (GA-07) is of the kind
"local", as T-CAP-49, because it measures process CPU. The others are of the kind "fake". The table
of 16.5 would add them to the row of D26. The counts of 16.6 would change by eight fake tests and one
local test in step 3a.

### A-7.4 Changed tests

| Test | Change |
|---|---|
| T-CAP-05 | Criterion text: "from the first frame taken in the gate" becomes "from the first frame given in the gate". The code needs no change. |
| T-CAP-91 | The test reads `replaced_count` of the fake source. With the rule, a lost frame of a 30 fps camera is often a frame that the loop drops, so the source count does not hold it. The test must count the gaps of `source_frame_number` over the given frames in the 100 s window, as GA-05 does. (The status is set only at given frames.) The criterion "3 (+/-1)" holds only for exact periods (A-4.1). |
| T-CAP-107, T-CAP-113, T-CAP-60, T-CAP-98 | No change of text or code. |

With the throwaway implementation, the accepted capture suite gave 133 passed, 1 failed (T-CAP-91,
for the reason above: "0 frames replaced in 100 s") and 47 skipped, with T-CAP-46 and the ten new
test cases deselected.

## A-8 The failing tests

`skellycam/tests/capture/test_gate_amendment.py` holds GA-01 to GA-09, with the marker
`gate_amendment`. `skellycam/tests/capture/conftest.py` deselects them unless
`SKELLYCAM_GATE_AMENDMENT=1` is set, also when the command line gives its own `-m`. The selections
of `.github/workflows/capture.yml` also leave them out. Run them with
`SKELLYCAM_GATE_AMENDMENT=1 uv run pytest skellycam/tests/capture -m gate_amendment`.

The arrival model: true periods of 33.333, 33.313 and 33.279 ms; each camera on its own 16 ms grid
(intervals of 32 or 48 ms); a fixed phase set (grid phases 0, 5 and 10 ms; GA-08: 0, 2.5 and 5 ms,
the smallest offset of the review); the second camera 32 ms late, with its sample time 32.3 ms before
its arrival. The bounds follow from the model of the rule for that phase set. They are not the
bounds for real cameras: question 5 of A-9 gives the pass rule of a hardware run.

"Throwaway" is an implementation of the rule with the close time, outside the repository, loaded by
an environment variable. "First wording" is the same implementation without the close time (the
first version of this amendment).

| Test | What it proves | Today (D26) | First wording | Throwaway |
|---|---|---|---|---|
| GA-01 | Spread for the phase set: median at most 12 ms, p95 at most 28 ms, max at most 40 ms, at most 0.5 % above one period | Fails: 38.0 / 54.0 / 70.0 ms, 64.5 % | Passes | Passes: 11.0 / 27.0 / 38.0 ms, 0.3 % |
| GA-02 | No wake delay: each camera gives its newest frame by the close time; `replaced_count` of the status equals the gaps at each given frame | Fails: 1,082 of 1,777 rounds | Passes | Passes; lost 0, 1 and 3 |
| GA-03 | A camera that dies: the round closes at its error, not before, within 100 ms | Fails (a live frame 11 ms before the error) | Passes | Passes |
| GA-04 | A stall: `dead` after 2.0 to 2.25 s; the round gives the newest frames by the death | Fails (frames 1,973 ms old) | Passes | Passes |
| GA-05 | 29.97 with two 30 fps cameras on the grid: lost frames in 100 s equal the rule replayed offline (+/-1); 2997 (+/-3) group frames; no held frames | Fails on held frames (2,560 of 3,027 rounds); lost 0, 2, 2 | Passes | Passes; lost 0, 3, 3 |
| GA-06 | One frame of each camera, order, each frame arrived after the previous close | Fails: 60 % of the rounds | Passes | Passes |
| GA-07 | A camera that waits for a 1 fps camera: process CPU under 2 %; its frame is within one period plus 16 ms of the slow frame | Fails: 3.6 to 4.8 % CPU, frames about 1 s apart | Passes | Passes: 0.16 to 1.09 % CPU |
| GA-08 | Wake delays up to 5 and 10 ms: lost frames at most 2 per 1,800 above the rule at zero delay, and at most 6; status count = gaps; at most 6 rounds per 1,800 give an older frame than the newest by the close | Fails: 108 to 1,010 rounds per 1,800 give an older frame | Fails: lost 4 to 7 (5 ms) and 18 to 22 (10 ms), against 0 to 3 at zero delay | Passes; lost 0, 1 and 3, as at zero delay |
| GA-09 | Two OpenCV fakes (pull): no gap in `source_frame_number`, `replaced_count` 0 | Passes (by design) | Passes | Passes; fails when the loop reads a pull source while it holds |

## A-9 Questions for the user

Each question is worded so that "yes" accepts the recommendation.

1. Do you accept the rule of A-3 in place of D26: a round closes when each camera in the gate has a
   frame newer than the frame that it gave last, each camera then gives its newest frame by the close
   time, and the other frames count as replaced? Recommendation: yes, after the trial of question 4.
   The spread falls by about 20 ms at the median (to 13.0 to 18.9 ms). The cost is 1 to 3 more lost
   frames per camera per minute, and up to about 10 in the worst phase: in the worst case about
   0.3 % of the frames (0.55 % at exact ties), against about 0.2 % today.
2. Do you accept the close time of A-3.1 and A-3.5: the latest arrival time of the first fresh frames
   of the round (or the time of a gate change), stored one time for each round, with a later frame
   kept for the next round? Recommendation: yes. Without it, wake delays of 5 to 10 ms lose 27 to 68
   frames per camera per 1,800; with it, at most 6.
3. Do you accept the shared fields and the wait of A-3.5: `fresh`, `wake`, `round_close` and
   `gate_changed_ns`; a wait of at most 50 ms; `wake` set at each gate change, also by the main
   process at a kill and at an unpause; and no give of a held frame after an error (A-4.2)?
   Recommendation: yes. The gate of today used 3.6 to 4.8 % of one core in GA-07, above the 2 % of
   T-CAP-49.
4. Do you give the go-ahead for a trial before you decide questions 1 to 3: a product-code
   implementation of the rule on a branch that is not merged, with a log of each delivered frame
   (arrival time, sample time, `source_frame_number`, given or lost), and a three-camera run that
   compares it with the rule of today in the same session? Recommendation: yes. The log can also
   explain the 25 to 32 replaced frames per camera of the first hardware run.
5. Do you accept this pass rule for that trial: at most 6 more lost frames per camera per 1,800 than
   the rule of today in the same session, a spread median of at most 20 ms, and at most 1 % of the
   group frames above one period? Recommendation: yes. The real ranges of A-2 meet it with a margin.
6. Do you accept that the bounds of GA-01 to GA-08 hold only for the phase set of the fake model, and
   that the cameras are judged by the pass rule of question 5? Recommendation: yes.
7. Do you accept this corrected warning text of U15 for a group with 29.97 and 30 fps cameras:
   "Cameras a1b2 and c3d4 run at 29.97 fps, cameras e5f6 and a7b8 at 30 fps. The group runs at 29.97
   fps. The 30 fps cameras skip one frame about every 33 s, and each camera can skip more because of
   the timing of USB delivery (up to about 10 frames in 100 s); each skipped frame is counted and is
   missing from the recording."? Recommendation: yes. The text of today is already approximate (in
   the model, a 30 fps camera lost 4.1 frames in 100 s on average and 8.3 at most), and the rule makes
   the difference larger.
8. Do you accept that, with the OpenCV source on Linux and macOS, the gate gives the first frame
   after the own give (A-3.6), so that the spread there stays as today until phase 7?
   Recommendation: yes.
9. Do you accept the tests GA-01 to GA-09 as T-CAP-114 to T-CAP-122, the change of T-CAP-91 of
   A-7.4, and pairing by arrival time now, with pairing by sample time after the LED or board test of
   A-5? Recommendation: yes.
