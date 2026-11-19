# Start-up frame rate check: which statistic and window (2026-11-19)

Question: the planned start-up check of native capture fails a camera that delivers more than 5 % less
than the rate its mode declares. The first plan was the median interval between arrival times over
warm-up frames 6 to 30. Is that enough?

A sub-agent (sonnet) analysed existing results. No camera was used. Scratch scripts are not kept.

## Data

Media Foundation only (wincam "mf" and pymf), 1280x720 MJPG, declared 30 fps, arrival time (QPC) of each
frame from the first frame after open. Source: the raw `frames.jsonl` files of the Windows suites
(outside the repository). Pooled: 1432 opens of the three good cameras (C922, C930e, Kiyo Pro) and 564
opens of the generic camera in its 25.8 fps state.

## Findings

- Arrival times sit on a grid of about 16 ms. Intervals are about 32 ms or 48 ms, never 33.3 ms.
- Good cameras: 8 % of the intervals are 48 ms. The median interval is 32 ms, so a rate from the median
  reads 31.2 fps (4 % high). Frames divided by elapsed time reads 30.0.
- Generic camera: 43 % of the intervals are 48 ms and 56 % are 32 ms. Median 32.3 ms (31 fps), mean
  38.8 ms (25.8 fps).
- **The median rule passed the generic camera in 564 of 564 opens.** The elapsed-time rate caught it in
  all of them.

Elapsed-time rate, fail below 28.5 fps (5 % below 30):

| Window (frames) | Good cameras, lowest rate | Good cameras failed | Generic camera, range | Generic caught |
|---|---|---|---|---|
| 6 to 30 | 28.82 | 0 % | 25.40 to 25.90 | 100 % |
| 6 to 60 | 29.35 | 0 % | 25.57 to 25.78 | 100 % |
| 6 to 90 | 29.64 | 0 % | 25.61 to 25.87 | 100 % |

- Frames 6 to 30 leave a margin of 0.3 fps on the good side (Kiyo Pro, irregular first frames).
  Frames 6 to 90 leave 1.1 fps on the good side and 2.9 fps on the generic side.
- The generic camera shows no ramp-up: its first-30 rate equals its long-run rate (25.70 to 25.77).

## Recommendation

Rate = (frames - 1) / (last arrival - first arrival), over frames 6 to 90. Fail below 95 % of the
declared rate. Do not use the median interval.

## Not answered

- A dim room with auto exposure (8 fps was seen once): no such open is in the data.
- Other declared rates. In W-MJPEG (about 1 open for each mode), requests for 5 to 20 fps delivered
  30 fps, and a request for 60 fps delivered 30 fps. So the check must compare with the rate that Media
  Foundation negotiated, and a camera can also be faster than its mode declares. Not tested further.
- Opens during control changes (W-CTRL-EFFECT, W-AUTO) had dips to 20 to 25 fps on the C930e and the
  Kiyo Pro in 1.7 % and 6.2 % of those opens. The cause is not known.
- One machine and one generic camera.

## Camera test: the rate after a live control change (2026-11-19, 12:39 to 13:07)

A sub-agent (opus) ran this on the four cameras, one at a time, 1280x720 MJPG at 30 fps, through
`pymf multi` under the camera lock. Only arrival times were kept; no frame was written. The room had room
light and daylight. Per camera: 5 blocks of changes (exposure steps between -8 and -3, gain high and low,
focus far and near, auto exposure on and off), 6 to 14 s apart. 194 control sets in total; each returned
S_OK in 1.0 to 3.0 ms and read back correctly. All controls were restored and verified. Scratch files
are not kept.

- **How long the rate is disturbed** (first 15-frame window within 5 % of the final rate): C922 and
  C930e 0 frames for most changes, at worst 1 to 2 frames (about 250 ms, after exposure -3 to -7).
  Kiyo Pro 3 to 6 frames for gain and auto exposure, at worst 16 frames (559 ms, focus far). Generic
  camera 0 frames, at worst 16 frames (895 ms, one auto exposure change).
- **Skip 15, then 90 frames:** 0 false alarms in 119 changes that ended at the normal rate, and 31 of 31
  changes that ended slower were caught (generic camera left out: it is always slow).
- **Skip 3 or more with any window from 30 to 90 frames** gave the same result. Skip 0 to 2 gave false
  alarms.
- **The wait with a 90-frame window** is 3.5 s at 30 fps, but 13 s at 8 fps.
- **Steady rates by exposure value (fps):**

  | Exposure | C922 | C930e | Kiyo Pro | Generic |
  |---|---|---|---|---|
  | -7 | 30.0 | 30.1 | 29.9 | 25.74 |
  | -6 | 30 | 30 | 28.7 | 25.74 |
  | -5 | 30 | 30 | 23.1 | 25.74 |
  | -4 | 16.0 | 16.0 | 19.5 | 25.74 |
  | -3 | 8.0 | 8.0 | 14.7 | 25.74 |

- **The Kiyo Pro at exposure -6 delivers 28.7 fps**, 0.2 fps above a 5 % limit (28.5). A rule with that
  limit can flap there. This rests on 2 changes.
- The lower rate is steady at once (Logitech) or within 3 frames (Kiyo Pro).
- No gap over 500 ms. The Kiyo Pro gave 5 discontinuity flags with one dropped frame each (auto exposure
  off, focus, one exposure step). The Kiyo Pro stayed alive.
- **The gain of the C930e read 6 before the stream started and 0 after it started.** A control value
  can reset when the stream starts.
- Not tested: four cameras together, white balance, other modes, a dim room, DirectShow.
