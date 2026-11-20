# The spread between cameras inside one group frame (offline analysis, 2026-11-20)

Question: the first hardware run of native capture (`hardware_run_3a_20261120.md`) measured a spread of
arrival times inside one group frame of about 36 ms at the median, with 60 to 77 % of group frames above
one frame period (33.3 ms). How much of that can a better pairing rule remove?

A sub-agent (opus) analysed the recordings of that run offline. No camera was used. The main session saved
this text from its report. Scratch scripts are not kept. "(i)" marks a number that rests on a few
interpolated arrival times (at most 4 group frames in 1,800 touch one).

## Data

Per-camera timing files of the native runs 1 and 2 (three cameras: C922, C930e, Kiyo Pro; 720p30; 60 s)
and of the four-camera run after the generic camera was unselected. Columns: the arrival time
(`frame.pre_frame_grab.ns`), the time the loop took the frame (`frame.pre_copy_to_camera_shm.ns`), the
time the camera finished the frame (`frame.post_frame_record.ns`). For the old runs also
`duration.during_frame_retrieve.ns`.

Two limits of the data:

- The sample time and the camera's own frame number of each frame are not in the timing files (they exist
  only in the shared-memory ring). The sample-time figures below are a model: Kiyo Pro arrival minus a
  constant 32.3 ms (the median of T-CAP-59; the range there was 16 to 48 ms).
- Only 0 to 3 double-period gaps for each camera are visible inside a recording. The 25 to 32 replaced
  frames that the log reports must fall mostly outside the recorded span. This was not confirmed.

## 1. Measured spread (ms): median / p95 / max / share above 33.3 ms

| Run | By arrival time | With the Kiyo Pro's sample time (model) |
|---|---|---|
| 1 | 35.8 / 55.4 / 71.3 / 70 % | 27.0 / 52.9 / 53.2 / 30 % |
| 2 | 35.0 / 51.1 / 67.1 / 77 % | 58.9 / 75.7 / 91.9 / 100 % |
| 4-camera | 39.1 / 54.8 / 66.1 / 65 % | 71.4 / 87.1 / 91.0 / 100 % |

Which clock is right is not settled. The Logitech sample time is only 0.3 ms before arrival, so their
driver stamps at delivery, not at exposure. Arrival times sit on a 16 ms grid. Neither clock gives the
moment of exposure.

## 2. The floor, and a simple causal rule (by arrival; median / p95 / max, ms)

| Run | Ideal offline pairing (i) | Causal rule (i) |
|---|---|---|
| 1 | 12.8 / 27.0 / 39 | 13.1 / 24.5 / 40 |
| 2 | 13.0 / 26.2 / 40 | 13.0 / 25.1 / 41 |
| 4-camera | 14.0 / 25.0 / 38 | 14.0 / 25.1 / 34 |

The causal rule: the round closes at the last camera's fresh frame, and each camera then gives its newest
frame. It reaches the floor. Fewer than 0.5 % of its group frames exceed 33.3 ms.

Why the gate of today is about 22 ms worse: a camera takes its newest frame the moment the round opens
(about 1.2 ms after the slowest camera finished the last round) and may not swap that frame while it
waits for the slowest camera. In 61 to 73 % of the rounds a held frame arrived before the previous round
closed; those rounds have a median spread of 40 to 43 ms. This state lasts until the drift between the
cameras changes the order of arrivals. Spec decision D26 allows this behaviour; it is not a code fault.

## 3. Decomposition (median; p95 in brackets)

| Part | ms |
|---|---|
| Phase offset between free-running cameras (no pairing removes it) (i) | about 13 to 14 (18 to 22) |
| 32 ms / 48 ms delivery grid | about 0 (+4 to +9) |
| Kiyo Pro delivery delay of about 32 ms | about 0 (it is close to one period: it changes which Kiyo Pro frame is paired, not the spread) |
| The pairing rule (measured minus causal) | about 22 to 25 (+26 to +31) |

## 4. Over time

The spread runs in plateaus that last 10 to 20 s. The camera periods differ by 0.06 to 0.16 % (C922
33.333 ms, Kiyo Pro 33.313 ms, C930e 33.279 ms), so the order of arrivals cycles in about 20 to 55 s.
Runs 1, 2 and the four-camera run behave the same.

## 5. The old code

The 0.17 ms that the old loop reports is the spread of the grab calls. Under DirectShow the grab call
takes 0.02 to 0.05 ms and `retrieve` is the call that waits for a frame. The spread of the retrieve-end
times is a lower bound on the true spread: median 28.3 and 28.4 ms, p95 41 and 44 ms. No column gives the
exposure time. The old spread is unknown, but at least about 28 ms.

## 6. For motion capture (a hand that moves at 5 m/s)

| Pairing | Position disagreement between cameras, median / p95 |
|---|---|
| Gate of today | 18 cm / 28 cm |
| Causal rule (i) | 6.5 cm / 12.5 cm |
| Phase-only floor | about 7 cm |

## Conclusion

- About 23 of the 36 ms median can be removed (p95 from 55 to 25 ms). The other 13 ms is the phase offset.
- Proposed rule, for the decision of the user (it changes D26): "A round closes when every camera has a
  frame newer than the one it gave last. Each camera then gives its newest frame; frames it had taken
  earlier count as replaced." Each camera must see the others' latest arrival (for example a shared
  counter). Cost on this data: 0 to 3 more replaced frames for each camera; the group latency falls from
  about 40 to about 17 ms.
- Not settled: which clock is true; the Kiyo Pro's sample time of each frame; where the replaced frames
  fell. To settle it: write `sample_ns` and `source_frame_number` of each frame into the timing file, and
  film one flashing LED or a moving board with all cameras.
