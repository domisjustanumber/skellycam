# Intel Quick Sync (mjpeg_qsv) against cv2.imencode for uncompressed camera modes (2026-11-18)

Question: for a camera that sends only YUY2 or NV12, which JPEG encoder should the camera process use?

- A: `mjpeg_qsv` through PyAV 19.0.2, fed YUY2 (yuyv422) or NV12 directly.
- B: `cv2.cvtColor` to BGR, then `cv2.imencode`.

Run by a sub-agent; the main session saved this text and did not rerun it. Script: `bench.py`. Numbers:
`results.json` (it also holds every 720p row).

## Setup

- i7-14700K, 28 threads, Windows 11. CPU load before the run: 11.5 %. cv2 ran with one thread.
- Python 3.13.18, av 19.0.2, opencv-contrib-python 5.1.0.95, numpy 2.5.5.
- Inputs: 8 real frames per resolution, read in place, made into full-range YUY2 and NV12 buffers in memory.
  They came from JPEGs, so sizes may be a little low.

## What the 2026-11-10 study already measured

(`skellycam_recording/recording_upgrade/results/encoder_pairing/FINDINGS.md`, `EVIDENCE_INDEX.md`)

1. It used `global_quality` 95 (720p) and 94 (1080p), chosen for an SSIM target. This run matched on bytes, so
   the values differ.
2. Hold-back is `async_depth` minus 1 calls: 3 at the default depth of 4, 0 at depth 1, where each call blocks
   about 17 ms. This run measured the same.
3. Chroma follows the input: YUY2 gives 4:2:2, NV12 gives 4:2:0. The encoder must be fed full range with
   `color_range=2`.
4. 16 cameras at 1080p30 were sustained. Its CPU measurement failed.
5. Not tested then: real limited-range camera frames, and CPU per frame.

## 1. Matched size (median bytes of 8 frames)

| Case | cv2 quality 90 | QSV `global_quality` of the same size | QSV at 90 |
|---|---|---|---|
| 720p YUY2 | 165,923 | 91 (164,657) | 159,266 |
| 720p NV12 | 156,510 | 91 (155,881) | 151,114 |
| 1080p YUY2 | 204,921 | 90 (202,329) | 202,329 |
| 1080p NV12 | 187,816 | 90 (188,995) | 188,995 |

## 2. Time per call (ms), not paced, 600 frames, one process

| 1080p | median | p95 | p99 | max |
|---|---|---|---|---|
| A, default depth, YUY2 | 2.13 | 2.34 | 2.83 | 3.91 |
| A, depth 1, YUY2 | 17.4 | 18.5 | 19.0 | 19.5 |
| B, YUY2 | 4.98 | 5.78 | 6.06 | 6.70 |
| A, default depth, NV12 | 1.64 | 1.88 | 2.42 | 3.04 |
| B, NV12 | 4.43 | 5.29 | 5.54 | 6.21 |

At 720p: A at default depth 1.06 ms (YUY2) and 0.88 ms (NV12); B 2.47 and 2.15 ms; A at depth 1 about 16.5 ms.

## 3. CPU per frame (process time over all threads) and cores used

| Case | A, default depth | B | A, depth 1 |
|---|---|---|---|
| 1080p YUY2, 30 fps | 1.64 ms, 0.049 cores | 6.41 ms, 0.192 cores | 1.74 ms, 0.052 cores |
| 1080p YUY2, 60 fps | 1.46 ms, 0.088 cores | 5.39 ms, 0.324 cores | 1.54 ms, 0.089 cores |
| 1080p NV12, 30 fps | 1.25 ms | 6.17 ms | 1.41 ms |
| 1080p NV12, 60 fps | 1.33 ms | 4.64 ms | 1.22 ms |

A costs about 3 to 4 times less CPU. The GPU engine counters could not be read, so it is not confirmed that
the work ran on the integrated GPU.

## 4. Hold-back of A

- Default depth (4): the packet of frame k comes out on call k+3. Three frames are inside the encoder, and
  frame in to packet out is about 100 ms at 30 fps.
- Depth 2 holds 1 frame; depth 1 holds none.
- At depth 1 each call blocks about 17 ms, which misses the 16.7 ms period at 60 fps (every 1080p frame late,
  58 frames/s).
- `low_power=1` made no difference; it is not known whether the option was accepted.
- B returns the JPEG in the same call.

## 5. Output check

- Both outputs decode with `cv2.imdecode`. Both are baseline, with 4 DHT segments, JFIF, no restart markers.
  A has 3 DQT segments, B has 2. Chroma follows the input in both.
- **Input range matters, and the two encoders assume opposite things.**

  | Input | A (`mjpeg_qsv`) | B (cv2) |
  |---|---|---|
  | Full range | PSNR-Y 52.8 dB (720p), 57.5 dB (1080p) | 28 to 29 dB: cv2's YUV to BGR conversion assumes limited range and stretches the levels |
  | Limited range | 28 dB if fed unchanged; 51.6 to 53.8 dB with a host-side table that expands the range first (0.4 ms at 720p, 1.1 ms at 1080p per frame) | 52 to 53 dB |

  Which range a real camera sends in YUY2 or NV12 is not verified.

## 6. Many processes at once, 1080p YUY2 at 30 fps, 300 frames per process

| Setup | Median ms | p99 ms | Missed periods | Total cores |
|---|---|---|---|---|
| 8 x B | 6.9 | 15.8 | 0 | 1.80 |
| 8 x A, depth 4 | 2.4 | 3.8 | 0 | 0.73 |
| 8 x A, depth 1 | 10.8 | 20.2 | 0 | 0.70 |
| 16 x B | 11.5 | 25.2 | 0 | 5.75 |
| 16 x A, depth 4 | 4.6 | 8.0 | 0 | 2.57 |
| 16 x A, depth 1 | 15.0 | 23.3 | 0 | 2.29 |

No Quick Sync session failed with 16 sessions open.

## 7. Start-up

- Creating one Quick Sync session takes 0.38 to 0.44 s; the first call takes 4 to 6 ms.
- With 8 or 16 sessions opened at once, each took about 1.0 to 1.25 s.
- B has no start-up cost.

## 8. Time per call against encoder depth (main session, 2026-11-18)

A scratch script that imports `bench.py`; YUY2 input, quality 90, 400 calls per cell, one process. Median /
p99 in ms, and the frames held inside the encoder.

| Depth | Held | 720p not paced | 720p at 60 fps | 1080p not paced | 1080p at 30 fps | 1080p at 60 fps |
|---|---|---|---|---|---|---|
| 4 (default) | 3 | 1.06 / 1.39 | 0.30 / 0.56 | 2.40 / 2.96 | 1.01 / 2.20 | 1.06 / 2.40 |
| 3 | 2 | 1.26 / 1.73 | 0.30 / 0.60 | 2.44 / 3.13 | 0.97 / 2.27 | 0.85 / 3.99 |
| 2 | 1 | 1.15 / 1.51 | 0.38 / 1.12 | 2.12 / 2.54 | 0.81 / 1.91 | 0.87 / 2.04 |
| 1 | 0 | 16.67 / 17.74 | 16.71 / 17.89 | 17.78 / 18.96 | 15.47 / 19.61 | 17.77 / 19.63 |

Depth 2 is as fast as depth 4 and holds one frame. Depth 1 blocks for about one 60 Hz period in every call,
paced or not.

## Not verified

- That the encode ran on the integrated GPU.
- Whether `low_power` did anything.
- The error path on a machine with no Quick Sync (not run).
- The range that a real camera sends.
