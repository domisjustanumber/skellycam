# Free-running cameras: a log of every frame, and pairing rules replayed over it (2026-11-20)

This is the first step of the study "cameras free-run, pairing by time". A sub-agent (opus) made one
measurement on three real cameras. The logger logged every frame of each camera with its times. Then a
script replayed several pairing rules over the logs, offline. No product code was changed.

- Scripts: `research/usb_cameras/free_run/free_run_log.py` (logger) and `free_run_replay.py` (replay,
  with a self-check on synthetic data: `--selftest`).
- Raw logs: a temp folder on the test machine, outside the repositories. They are not kept in git.
- No image was decoded or stored.

## Summary

| Rule (720p30, 5 min, two runs) | Spread by arrival, median / p95 / max (ms) | Spread by sample time, median / p95 / max (ms) | Frames in no group C922 / C930e / Kiyo Pro |
|---|---|---|---|
| b. Gate of today (D26), model | 43.1-46.1 / 59.7-62.0 / 77-79 | 58.5-62.5 / 83-88 / 92-95 | 0 / 13 / 4-5 |
| c. Amendment (A-3) | 15.0-15.5 / 27.2-30.3 / 43-46 | 26.7-28.9 / 43.6-47.5 / 65-67 | 1 / 15 / 6-7 |
| d'. Offline best, by arrival (full groups only) | 15.0-15.4 / 25.7-27.4 / 37 | 31.0-33.9 / 50-51 / 59-64 | 6-11 / 20-25 / 11-17 |
| d'. Offline best, by sample time (full groups only) | 29.2-31.1 / 46-49 / 62-63 | 15.0-15.4 / 25.9-26.8 / 36-37 | 8-35 / 22-49 / 14-41 |
| e. Causal by sample time, D = 33 ms, H = 16 ms | 31.7-36.4 / 50-55 / 62-64 | 15.0-15.7 / 28.2-31.0 / 40-45 | 2-5 / 16-19 / 8-11 |

- By arrival time, the amendment already reaches the offline best at the median (15 ms against 15 ms).
  Its p95 is only 1.5 to 3 ms above the offline best. A look-ahead (D > 0) does not improve the arrival
  spread unless the rule drops many frames.
- The gate of today is about 28 to 31 ms worse at the median. This agrees with the earlier analysis.
- The two clocks pair different Kiyo Pro frames. The Kiyo Pro's sample time is about 32 ms (one frame)
  before its arrival. A pairing that is good on one clock has a spread of about 30 ms on the other clock.
  Which clock is closer to the moment of exposure is not known. This run cannot settle it.
- The drift case: the lockstep rules lose the extra frames of the faster cameras (C930e about 14 frames,
  Kiyo Pro about 5 frames in 5 min). Free-run pairing keeps them as frames in no group, or as groups that
  lack one camera.
- 60 fps: the C922 delivers 60 fps at 1280x720 with manual exposure -7 (repeated 3 times). It does NOT
  at -8, -9 and -10 (29.7 fps). The Kiyo Pro delivers 30 fps in its 60 fps mode at every tested exposure
  and with auto exposure. See section 9.

## 1. Method

### The run

| Item | Value |
|---|---|
| Cameras | Logitech C922 (046d:085c), Logitech C930e (046d:0843), Razer Kiyo Pro (1532:0e05). Picked by USB ID. |
| Mode | 1280x720, 30 fps, MJPG (the mode read back: 1280x720 30/1 MJPG on all three) |
| Exposure | Manual -7 on all three. Each camera read back manual -7. The product sets the configured value on every camera (camera loop, 9.1), with no special value for the Kiyo Pro, so the Kiyo Pro also got -7. |
| Source | The product's `MediaFoundationSource`, used read-only from the skellycam-connect worktree |
| Processes | One process for each camera. Each process reads every frame (`read_frame(0.5)` in a tight loop). No gate. No process waits for another. |
| Per frame | One tuple in memory: `arrival_ns`, `sample_ns`, `source_frame_number`, discontinuity flag, JPEG length, driver-error flag, and the time the process took the frame. The CSV is written after the window. |
| Window | 5 min (300 s) for each run, from a common start time. The logging starts 3 s before the window, after the controls were set. |
| Runs | Run 1: 18:24-18:29 UTC. Run 2: 18:29-18:34 UTC. |
| CPU of the machine (other sessions work on it) | Run 1: mean 11.2 %, max 27.8 % of 28 logical CPUs. Run 2: mean 10.5 %, max 36.1 %. The three logger processes used 0.007 to 0.015 cores each. |
| Light | The user added light at about 13:22 local time. The lights check (13:23) and all runs (13:24 to 13:40) were after that change. No run straddles it. |

Lights check: the C922 alone, 1280x720 30 fps MJPG, manual -7, 5 s: 30.04 fps (frames 6 to 90: 30.17
fps). Not dark.

The logger did not disturb the capture:

- Frames replaced in the waiting place (the reader was too slow): 0 for each camera in each run.
- The time from arrival to the moment the process took the frame: median 0.09 to 0.11 ms, p99 0.22 to
  0.30 ms, max 4.8 ms.
- All three cameras were alive at the end of each run. The Kiyo Pro did not wedge. Close took 0.33 s
  (Logitech) and 1.1 to 1.2 s (Kiyo Pro). No process was left.

### The clocks

- "Arrival" is `arrival_ns`: `perf_counter_ns()` at the start of `OnReadSample`, as the product stamps it.
- "Sample" is `sample_ns`: the driver's sample time, converted by the product to the same base (100 ns
  units times 100). The sample time was valid for every frame of every camera.
- Neither clock is the moment of exposure. This report does not claim which clock is true.

### The rules (definitions used by the replay)

All rules use only the frames inside the 5-min window. "Frames in no group" counts the frames of a
camera between its first and its last frame in a group. For b and c these frames are lost (replaced).
For d and e the recorder keeps every frame, so these frames are only unpaired.

| Rule | Definition |
|---|---|
| b. Gate of today (D26) | A round opens 1.2 ms after the previous round closed. At the open, each camera takes its newest frame that it has not taken, if one arrived by the open. Else it waits for its next frame. The round closes when the last camera has taken its frame. This is a model of the product's gate, not the product. |
| c. Amendment (A-3) | The close time is the latest arrival of the first fresh frames (a fresh frame arrived after the previous close time). Each camera gives its newest frame that arrived by the close time. Wake delay 0. |
| d. Free run, offline best | All frames of all cameras in one time order. A group is a run of consecutive frames in that order; it holds at most one frame of each camera, and its two end frames belong to it. Dynamic programming finds the global minimum of: the sum of the group spreads + one period (33.3 ms) for each frame in no group + one period for each camera that a group lacks. Thus a group of three is kept unless its spread is above about two periods. Variant d' allows only full groups. |
| e. Free run, causal, look-ahead D | When each camera has a frame newer than its last paired frame (at time T), the window ends at T + D. The candidate cuts are: these frames; then the oldest frame swapped for the next frame of that camera; then the next oldest swapped; at most two swaps, and only with frames that arrived by T + D. The rule picks the cut with the smallest spread + H for each swapped frame. Then each camera moves to a newer frame that arrived by the decision and does not raise the spread. |

Why these definitions:

- d is the global optimum of its cost among order-keeping pairings of this form, so it serves as the
  offline floor. It is not proven to be the lowest possible spread under every other definition. It does not depend on a chosen reference camera. An anchor-camera method (match each
  camera to one reference camera) was considered and not used: on phases 0, 10, 20 ms it gives 23.3 ms
  where 20 ms is possible.
- e at D = 0, H = 0, by arrival, is the amendment. The replay checks this: the groups are equal on both
  runs.
- H (the cost of one swapped frame) is needed. With H = 0 and D > 0, the rule follows the 16 ms jitter
  of the arrival times: it changes the cut often, and each change loses one frame of each camera (590 to
  770 frames per camera in 5 min). H = 16 ms (half a period) stops this. Table 6 shows the effect.
- The amendment and the causal rule are replayed with no wake delay. The gate model gave the same
  numbers with a wake delay of 0 and of 1.2 ms in run 1, and medians 1.1 ms apart in run 2.

### Self-check

`free_run_replay.py --selftest` checks the rules on synthetic data whose answer is known:

- Three cameras with equal periods and phases 0, 10, 30 ms: the amendment gives 30 ms; the causal rule
  at D = 0 equals the amendment; the causal rule at D = 17 ms and the offline best give 13.33 ms (one
  period minus the largest phase gap).
- Phases 0, 10, 20 ms: the offline best gives 20 ms.
- A hand-made case with 4, 4 and 3 frames: the gate of today gives spreads 25, 28, 31 ms; the
  amendment gives 25, 28, 26 ms (it gives the newer frame of the first camera).
- Drift (periods 33.30, 33.33, 33.37 ms, 300 s): the extra frames of the fastest camera end in no group,
  and the frames of the middle camera that have no partner of the slowest camera form groups that lack
  that camera; the amendment loses the extra frames.

## 2. Per camera (a)

The period is the arrival time span divided by the span of `source_frame_number`.

| Run | Camera | Frames | Period (ms) | Driver-dropped frames | Arrival intervals 32 / 48 / 64 / 16 ms | Position on a 16 ms grid, p5 / p50 / p95 (ms) | Arrival minus sample, p5 / p50 / p95 (ms) | Share of frames that arrive 16 ms or more after the sample time | JPEG (kB) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | C922 | 9000 | 33.3335 | 0 | 8244 / 749 / 0 / 0 | 10.7 / 10.8 / 11.1 | 0.2 / 16.2 / 16.5 | 60 % | 150 |
| 1 | C930e | 9014 | 33.2817 | 1 | 8291 / 719 / 2 / 0 | 9.7 / 9.9 / 10.1 | 0.2 / 0.4 / 16.4 | 32 % | 125 |
| 1 | Kiyo Pro | 9005 | 33.3120 | 0 | 7557 / 1093 / 0 / 354 | 0.5 / 5.2 / 15.5 | 32.0 / 32.3 / 48.3 | 100 % (all 16 to 49 ms) | 200 |
| 2 | C922 | 9000 | 33.3335 | 0 | 8249 / 750 / 0 / 0 | 14.4 / 14.6 / 15.0 | 0.2 / 16.2 / 16.5 | 61 % | 153 |
| 2 | C930e | 9014 | 33.2817 | 1 | 8292 / 720 / 1 / 0 | 13.4 / 13.6 / 14.0 | 0.2 / 0.4 / 16.4 | 33 % | 126 |
| 2 | Kiyo Pro | 9006 | 33.3119 | 0 | 7590 / 1077 / 0 / 338 | 0.6 / 10.8 / 15.5 | 32.1 / 32.3 / 48.3 | 100 % (all 16 to 49 ms) | 199 |

Notes:

- Missing source frame numbers: none. But `source_frame_number` is the source's own count of the
  frames it got (D27), so it cannot show a frame that the driver dropped.
- Driver-dropped frames: the C930e had one gap of 64 ms in each run, in both clocks, and the next frame
  had the discontinuity flag. This is one frame that the driver or the camera dropped. Its period above
  (from the frame numbers) is therefore slightly short. A straight-line fit over the sample times, with
  that frame counted, gives 33.2785 ms. The other cameras had no gap and no discontinuity flag.
- The arrival grid: each Logitech camera arrives on its own exact 16.000 ms grid of `perf_counter`. Its
  position on the grid stays inside 0.4 ms for 5 min. The position differs between the runs (10.8 and
  14.6 ms for the C922). The Kiyo Pro arrivals are on no fixed 16 ms grid. They spread over the full
  16 ms. 3.8 % of its intervals are 16 ms.
- The sample times are also on the 16 ms grid: sample intervals are 32 or 48 ms (p1 to p99) for the
  Logitech cameras, and 16, 32 or 48 ms for the Kiyo Pro. A straight line through the times of each
  camera leaves a residual of about +/-8 ms (standard deviation 4.6 ms Logitech, 5.0 ms Kiyo Pro) on
  both clocks. So neither clock is a smooth device clock.

Drift (straight-line fit; the C930e dropped frame counted):

| Camera | Period (ms) | Against the C922 | Extra frames in 5 min against the C922 |
|---|---|---|---|
| C922 | 33.3328 | - | - |
| Kiyo Pro | 33.3125 | -0.061 % | +5 (run 1), +6 (run 2) |
| C930e | 33.2785 | -0.163 % | +14 (+15 with the dropped frame) |

The periods are the same in both runs to 0.0001 ms. They agree with the earlier analysis (C922 33.333,
Kiyo Pro 33.313, C930e 33.279 ms).

## 3. Spread inside each group frame (b to e)

Median / p95 / max (ms), and the share of groups above one period (33.3 ms).

### Run 1

| Rule | Groups | Groups lacking a camera | By arrival | By sample time | No group C922 / C930e / Kiyo Pro | Latency, median / p95 (ms) |
|---|---|---|---|---|---|---|
| b. Gate of today, wake 1.2 ms | 9000 | 0 | 43.1 / 59.7 / 76.5 / 72.6 % | 58.5 / 87.6 / 92.2 / 93.2 % | 0 / 13 / 4 | oldest frame at the close 43.1 / 59.7 |
| c. Amendment | 8999 | 0 | 15.0 / 27.2 / 43.1 / 0.1 % | 26.7 / 43.6 / 67.0 / 40.7 % | 1 / 15 / 6 | oldest frame at the close 15.0 / 27.2 |
| d. Offline best, by arrival | 9011 | 74 | 14.9 / 24.7 / 36.6 / 0.1 % | 34.0 / 50.7 / 59.4 / 52.6 % | 10 / 34 / 16 | - |
| d'. Offline best, by arrival, full groups | 8994 | 0 | 15.0 / 25.7 / 36.6 / 0.1 % | 33.9 / 50.7 / 59.4 / 51.9 % | 6 / 20 / 11 | - |
| d. Offline best, by sample | 9011 | 94 | 29.3 / 45.8 / 61.7 / 45.6 % | 15.0 / 25.0 / 36.8 / 0.0 % | 22 / 26 / 32 | - |
| d'. Offline best, by sample, full groups | 8991 | 0 | 29.2 / 45.9 / 61.7 / 45.0 % | 15.0 / 25.9 / 36.8 / 0.0 % | 8 / 22 / 14 | - |
| e. Causal by arrival, D 0 | 8999 | 0 | 15.0 / 27.2 / 43.1 / 0.1 % | 26.7 / 43.6 / 67.0 / 40.7 % | 1 / 15 / 6 | added 0; oldest 15.0 / 27.2 |
| e. Causal by arrival, D 17, H 16 | 8993 | 0 | 15.0 / 27.2 / 41.2 / 0.1 % | 26.7 / 43.6 / 69.0 / 40.9 % | 7 / 21 / 12 | added 17.0 / 17.0; oldest 32.0 / 43.4 |
| e. Causal by arrival, D 33, H 16 | 8993 | 0 | 15.0 / 27.2 / 41.2 / 0.1 % | 26.7 / 43.6 / 69.0 / 40.9 % | 7 / 21 / 12 | added 26.1 / 33.0; oldest 40.3 / 49.3 |
| e. Causal by arrival, D 50, H 16 | 8993 | 0 | 15.0 / 27.2 / 41.2 / 0.1 % | 26.7 / 43.6 / 69.0 / 40.9 % | 7 / 21 / 12 | added 26.1 / 41.5; oldest 41.4 / 51.9 |
| e. Causal by sample, D 0 | 9000 | 0 | 17.2 / 33.0 / 47.0 / 2.8 % | 27.0 / 51.9 / 59.9 / 39.9 % | 0 / 14 / 5 | added 0; oldest 17.2 / 33.0 |
| e. Causal by sample, D 17, H 16 | 8998 | 0 | 25.9 / 45.7 / 61.8 / 29.0 % | 17.0 / 28.5 / 54.0 / 3.6 % | 1 / 15 / 7 | added 17.0 / 17.0; oldest 41.7 / 60.6 |
| e. Causal by sample, D 33, H 16 | 8994 | 0 | 36.4 / 55.0 / 61.8 / 51.7 % | 15.0 / 28.2 / 40.0 / 0.3 % | 5 / 19 / 11 | added 31.7 / 33.0; oldest 53.7 / 74.7 |
| e. Causal by sample, D 50, H 16 | 8991 | 0 | 36.9 / 55.2 / 72.8 / 53.0 % | 15.0 / 28.2 / 40.0 / 0.1 % | 8 / 22 / 14 | added 31.6 / 47.9; oldest 54.5 / 75.8 |

### Run 2

| Rule | Groups | Groups lacking a camera | By arrival | By sample time | No group C922 / C930e / Kiyo Pro | Latency, median / p95 (ms) |
|---|---|---|---|---|---|---|
| b. Gate of today, wake 1.2 ms | 9000 | 0 | 46.1 / 62.0 / 78.8 / 70.2 % | 62.5 / 83.2 / 94.5 / 97.8 % | 0 / 13 / 5 | oldest frame at the close 46.1 / 62.0 |
| c. Amendment | 8999 | 0 | 15.5 / 30.3 / 46.0 / 0.2 % | 28.9 / 47.5 / 65.3 / 27.0 % | 1 / 15 / 7 | oldest frame at the close 15.5 / 30.3 |
| d. Offline best, by arrival | 9011 | 60 | 15.2 / 21.1 / 35.9 / 0.1 % | 31.1 / 49.0 / 64.2 / 37.8 % | 10 / 19 / 18 | - |
| d'. Offline best, by arrival, full groups | 8989 | 0 | 15.4 / 27.4 / 36.8 / 0.1 % | 31.0 / 49.5 / 64.1 / 37.6 % | 11 / 25 / 17 | - |
| d. Offline best, by sample | 9011 | 65 | 31.3 / 48.7 / 62.9 / 38.5 % | 15.4 / 21.4 / 36.1 / 0.1 % | 17 / 30 / 4 | - |
| d'. Offline best, by sample, full groups | 8964 | 0 | 31.1 / 48.6 / 62.9 / 37.7 % | 15.4 / 26.8 / 36.1 / 0.1 % | 35 / 49 / 41 | - |
| e. Causal by arrival, D 0 | 8999 | 0 | 15.5 / 30.3 / 46.0 / 0.2 % | 28.9 / 47.5 / 65.3 / 27.0 % | 1 / 15 / 7 | added 0; oldest 15.5 / 30.3 |
| e. Causal by arrival, D 17, H 16 | 8993 | 0 | 15.6 / 30.1 / 37.5 / 0.1 % | 29.5 / 47.7 / 68.3 / 29.5 % | 7 / 21 / 13 | added 17.0 / 17.0; oldest 32.5 / 46.3 |
| e. Causal by arrival, D 33, H 16 | 8993 | 0 | 15.6 / 30.1 / 37.5 / 0.1 % | 29.5 / 47.7 / 68.3 / 29.5 % | 7 / 21 / 13 | added 28.2 / 33.0; oldest 37.3 / 49.0 |
| e. Causal by arrival, D 50, H 16 | 8993 | 0 | 15.6 / 30.1 / 37.5 / 0.1 % | 29.5 / 47.7 / 68.3 / 29.5 % | 7 / 21 / 13 | added 28.2 / 43.7; oldest 43.6 / 49.2 |
| e. Causal by sample, D 0 | 8999 | 0 | 17.0 / 33.0 / 47.2 / 2.3 % | 33.0 / 52.0 / 65.3 / 45.1 % | 1 / 15 / 7 | added 0; oldest 17.0 / 33.0 |
| e. Causal by sample, D 17, H 16 | 9000 | 0 | 29.0 / 46.9 / 60.3 / 28.5 % | 17.0 / 31.0 / 50.9 / 1.1 % | 0 / 14 / 6 | added 17.0 / 17.0; oldest 44.6 / 61.3 |
| e. Causal by sample, D 33, H 16 | 8997 | 0 | 31.7 / 49.9 / 63.9 / 41.6 % | 15.7 / 31.0 / 45.3 / 0.3 % | 2 / 16 / 8 | added 31.9 / 33.0; oldest 50.9 / 75.8 |
| e. Causal by sample, D 50, H 16 | 8996 | 0 | 32.3 / 50.1 / 77.8 / 45.2 % | 15.6 / 30.5 / 36.1 / 0.1 % | 3 / 17 / 9 | added 31.9 / 47.9; oldest 51.1 / 78.4 |

"Added" latency: the time from the arrival of the latest frame of the group to the decision. "Oldest":
the time from the arrival of the earliest frame of the group to the decision (or to the close).

## 4. The look-ahead and the hysteresis H (run 1, by arrival)

| D (ms) | H (ms) | Spread median / p95 / max (ms) | No group C922 / C930e / Kiyo Pro |
|---|---|---|---|
| 0 | any | 15.0 / 27.2 / 43.1 | 1 / 15 / 6 |
| 17 | 0 | 14.8 / 17.2 / 33.0 | 589 / 603 / 594 |
| 17 | 4 | 14.9 / 21.9 / 33.0 | 402 / 416 / 407 |
| 17 | 8 | 14.9 / 24.3 / 33.3 | 147 / 161 / 152 |
| 17 | 16 | 15.0 / 27.2 / 41.2 | 7 / 21 / 12 |
| 33 | 0 | 14.8 / 17.1 / 27.4 | 691 / 705 / 696 |
| 33 | 16 | 15.0 / 27.2 / 41.2 | 7 / 21 / 12 |

By sample time (run 1), the look-ahead does help, because the Kiyo Pro frame that fits best on the
sample clock arrives about one period later: D 0 gives 27.0 / 51.9 / 59.9 ms; D 17 (H 16) gives
17.0 / 28.5 / 54.0 ms; D 33 (H 16) gives 15.0 / 28.2 / 40.0 ms, at an added latency of about 32 ms.

What this shows: the p95 can fall from about 27 to 17 ms only by giving up about 7 % of the frames of
each camera into no group. The median does not move. Most of the p95 is the 16 ms arrival grid, not the
rule.

## 5. The drift case (f)

In 5 min the C930e delivers about 14 frames more than the C922, and the Kiyo Pro about 5 or 6 more.

| Rule | What happens to the extra frames |
|---|---|
| b. Gate of today | Lost (replaced): C930e 13, Kiyo Pro 4 to 5, C922 0. The number of groups equals the frames of the slowest camera (9000). |
| c. Amendment | Lost: C930e 15, Kiyo Pro 6 to 7, C922 1. One group fewer than the gate. |
| e. Causal, D 0 | As the amendment. With D > 0 and H 16: 6 more lost frames per camera in 5 min (cut changes). |
| d'. Offline best, full groups | The extra frames end in no group, plus a few frames of each camera where the cut changes: 6 to 35 (C922), 20 to 49 (C930e), 11 to 41 (Kiyo Pro). The recorder keeps them all. |
| d. Offline best, groups may lack a camera | The extra frames of the C930e and the Kiyo Pro pair with each other in 60 to 94 groups that lack the C922. The C922 has 10 to 22 frames in no group. |

So with lockstep rules the drift costs frames. With free-run recording it costs nothing in the record;
the pairing only marks the extra frames as unpaired or as groups with a missing camera.

## 6. What differs between the runs

- The phases. Each Logitech camera keeps a fixed position on its 16 ms grid in a run, but the position
  changes from one open to the next (C922: 10.8 ms in run 1, 14.6 ms in run 2). The spread numbers change
  only a little with this: amendment median 15.0 and 15.5 ms, p95 27.2 and 30.3 ms.
- The gate model: 43.1 and 46.1 ms at the median. The earlier product runs measured 35 to 39 ms. The
  model is not the product, and the phases were different. This run did not run the product's gate.
- Periods, drift, the arrival-minus-sample shape and the dropped C930e frame: the same in both runs.

## 7. Light

All runs were after the user added light (13:22 local). With manual exposure -7 the timing matched the
earlier runs: the same periods, the same 32 / 48 ms arrival intervals, the same 32 ms Kiyo Pro delay.

One difference from T-CAP-59 (earlier today): there the C922 and C930e had a median arrival minus
sample of 0.33 ms. Here 60 % of the C922 frames and 32 % of the C930e frames arrive 16 ms after their
sample time (the next grid step). This run cannot say why. The light, the JPEG size (C922 150 kB, C930e
125 kB) or a different exposure setting earlier are possible causes. It was not tested.

## 8. Limits

- Neither clock is the moment of exposure. The Logitech sample time is on the 16 ms delivery grid, 0 or
  16 ms before arrival. The Kiyo Pro sample time is 16 to 48 ms (median 32 ms) before arrival, and is
  not smooth either. The report does not claim which clock is true.
- The gate rules b and c are models. The wake delay of c and the cost of the cross-process protocol
  are not in the replay.
- The rule e is one causal rule. Its H was chosen after a sweep on run 1, and the same H was used on
  run 2.
- "Frames in no group" for d and e are not lost: in free-run recording, the recorder keeps every frame.
- Frames at the start and the end of the window are not counted in "no group".
- One machine, one session, three cameras, 30 fps, 5 min per run. Other sessions ran CPU and GPU work on
  the machine (CPU numbers in section 1). GPU load was not recorded.
- The driver-dropped frame of the C930e was found from a 64 ms gap and the discontinuity flag. The frame
  numbers of the source cannot show it.

## 9. Extra test: 60 fps with more light

Asked by the user after the light change: does the 1280x720 60 fps MJPG mode deliver 60 fps now? Run
13:34 to 13:40 local, through the product's Media Foundation source, the same logger. Each test: 10 s
after the controls were set. "6-90" is the rate over frames 6 to 90 after the controls were set, as the
product's rate check measures it. "Whole" is the rate over the 10 s. Pass: 60 fps +/- 3 % (58.2 to 61.8)
on frames 6 to 90, as the product. The mode read back was 1280x720 60/1 MJPG on both cameras.

The exposure values are in the units of the camera control (log2 of seconds by the DirectShow
convention): -6 = 15.6 ms, -7 = 7.8 ms, -8 = 3.9 ms, -9 = 1.95 ms, -10 = 0.98 ms. The source reads back
only the value, not a time in ms, so this conversion is the convention, not a measurement. With auto
exposure, both cameras read back "auto, -10"; the value under auto may not be the real exposure.

| Test | Camera | Exposure | 6-90 (fps) | Whole 10 s (fps) | Pass | Mean JPEG (kB) |
|---|---|---|---|---|---|---|
| alone | C922 | -7 | 59.66 | 59.40 | pass | 141 |
| alone | C922 | -8 | 29.66 | 29.80 | fail | 124 |
| alone | C922 | -9 | 29.66 | 29.74 | fail | 104 |
| alone | C922 | -10 | 29.66 | 29.74 | fail | 80 |
| alone | C922 | auto (comparison only) | 36.97 | 54.38 | fail | 142 |
| alone | Kiyo Pro | -7 | 29.66 | 30.04 | fail | 191 |
| alone | Kiyo Pro | -8 | 29.66 | 30.14 | fail | 136 |
| alone | Kiyo Pro | -9 | 30.35 | 30.04 | fail | 180 |
| alone | Kiyo Pro | -10 | 30.35 | 30.14 | fail | 205 |
| alone | Kiyo Pro | auto (comparison only) | 29.66 | 29.94 | fail | 183 |
| both | C922 | -7 | 46.46 | 58.69 | fail | 141 |
| both | Kiyo Pro | -7 | 30.01 | 29.94 | fail | 190 |
| both | C922 | -8 | 29.66 | 29.74 | fail | 124 |
| both | Kiyo Pro | -8 | 29.66 | 30.04 | fail | 137 |
| both | C922 | -9 | 29.66 | 29.75 | fail | 103 |
| both | Kiyo Pro | -9 | 30.35 | 30.14 | fail | 181 |
| both | C922 | -10 | 29.66 | 29.75 | fail | 80 |
| both | Kiyo Pro | -10 | 30.00 | 30.14 | fail | 199 |
| both | C922 | auto (comparison only) | 59.66 | 59.49 | pass | 142 |
| both | Kiyo Pro | auto (comparison only) | 29.66 | 29.94 | fail | 142 |

Repeat of the C922 alone, in a new order (13:39 local):

| Exposure | 6-90 (fps) | Whole 10 s (fps) | Pass | Mean JPEG (kB) |
|---|---|---|---|---|
| -9 | 29.66 | 29.80 | fail | 105 |
| -7 | 58.99 | 59.09 | pass | 140 |
| -8 | 29.66 | 29.80 | fail | 124 |
| -6 | 56.45 | 57.99 | fail (just below 58.2) | 150 |
| -7 | 59.66 | 59.40 | pass | 141 |

What this proves:

- C922: 60 fps works at 1280x720 MJPG with manual exposure -7 (3 of 3 tests alone). The order of the
  tests does not change this. Shorter exposures (-8, -9, -10) give 29.7 fps every time, alone and
  with the Kiyo Pro. -6 is just below the limit. So for the C922 the cause of the 29.7 fps is not only
  the light. The camera falls to 30 fps at short manual exposures. This run did not find why.
- C922 with the Kiyo Pro open, at -7: 46.5 fps over frames 6 to 90, then 58.7 fps over 10 s. It fails
  the product's check in this test; it reaches about 60 later. Not repeated.
- Kiyo Pro: 60 fps is NOT proven. It delivered 29.7 to 30.4 fps at each manual exposure from -7 to -10,
  with auto exposure, alone and with the C922. More light did not change this. The JPEG sizes do change
  with the exposure, so the control works, but the rate stays at 30.
- The Kiyo Pro stayed healthy in all 10 opens (open 0.91 to 0.92 s). No wedge.
- The C922 auto runs are only for comparison: alone 37 fps at the start, 54 fps over 10 s; with the
  Kiyo Pro 59.7 fps.

## 10. What a later LED or moving-board test needs to settle the clock question

- One event that all cameras see at one known moment: an LED that flashes with sharp edges (for example
  a 1 to 2 ms flash at a rate that is not a multiple of 30 Hz, so the flash moves through the frame
  phase), driven by a source whose time is on the `perf_counter` base (or logged against it).
- Short exposures on all cameras (for example -9 or -10), so that the exposure window is short against
  the 16 ms grid. Then the frame that shows the flash gives the exposure time to within the exposure
  plus the rolling-shutter time.
- The same logger (all three clocks per frame: exposure from the image, arrival, sample), at least
  several hundred flashes, so that the offset of each clock to the exposure can be measured with its
  spread, for each camera.
- A row position in the image for the rolling shutter: the LED in a known image row, or a moving board
  with a fast pattern, so that the readout time is known.
- The question to answer: is the Kiyo Pro exposure closer to its arrival or to its sample time (32 ms
  earlier)? And do the Logitech cameras expose one grid step (16 ms) before their sample time, or more?
