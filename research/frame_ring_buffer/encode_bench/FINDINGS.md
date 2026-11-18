# cv2.imencode JPEG encode benchmark (2026-11-18)

Question: what do time and size look like if skellycam encodes the frames of an uncompressed camera mode
(YUY2, NV12) with `cv2.imencode`, once per frame in the camera process?

Run by a sub-agent; the main session saved this text and did not rerun it. Script: `bench.py`. Numbers:
`results.json` (also p95 and max for every row, the 4:4:4 rows for q80 and q85, and the noisy-frame timings).

## Setup

- i7-14700K, 28 threads, Windows 11. CPU load before the run: 7.9 %.
- Python 3.13.18, opencv-contrib-python 5.1.0.95, numpy 2.5.5, psutil 7.2.2.
- Sources: 8 real frames at 1280x720 and 8 at 1920x1080 (C922, C930e, Kiyo Pro and the generic camera; the
  median and the largest frame of each), read in place from `../jpeg_bound/frames/` and decoded in memory.
- Limitation: these frames already went through a camera's JPEG pass, so sizes may be a little low.
- Ring slots: 925,696 B (720p) and 2,080,768 B (1080p).
- OpenCV's default chroma subsampling is 4:2:0.
- Every output has 4 DHT segments and 2 DQT segments, no DRI and no restart marker.
- One encode does not use more threads: 1.86 ms with the default 28 threads against 1.79 ms with one.

## Encode time and size, one thread

Time is median / p99 in ms. "Real max %" is the largest output from a real frame as a share of the slot.

| Setting | 720p ms | 720p median B | 720p real max % | 1080p ms | 1080p median B | 1080p real max % |
|---|---|---|---|---|---|---|
| q80 4:2:0 | 1.44 / 1.88 | 108k | 22 | 2.83 / 3.50 | 137k | 14 |
| q80 4:2:2 | 1.73 / 2.22 | 114k | 23 | 3.55 / 4.68 | 153k | 14 |
| q85 4:2:0 | 1.48 / 2.00 | 130k | 27 | 2.88 / 3.78 | 155k | 17 |
| q85 4:2:2 | 1.78 / 2.29 | 137k | 28 | 3.52 / 4.67 | 171k | 17 |
| q90 4:2:0 | 1.53 / 2.06 | 150k | 30 | 2.97 / 3.86 | 184k | 19 |
| q90 4:2:2 | 1.79 / 2.37 | 157k | 32 | 3.63 / 4.99 | 198k | 19 |
| q90 4:4:4 | 2.35 / 2.89 | 175k | 35 | 4.83 / 6.01 | 226k | 21 |
| q95 4:2:0 | 1.62 / 2.11 | 204k | 41 | 3.24 / 4.30 | 256k | 26 |
| q95 4:2:2 | 1.92 / 2.57 | 214k | 44 | 3.74 / 4.81 | 270k | 27 |
| q95 4:4:4 | 2.60 / 5.78 | 235k | 49 | 5.02 / 6.12 | 309k | 29 |

At q90 4:2:2: 0.17 bytes per pixel at 720p and 0.10 at 1080p; the slowest single encode was 2.86 ms (720p)
and 5.65 ms (1080p).

## Slot check

- Real frames: none passes 50 % of the slot at any setting. The highest is 49 % (720p, q95 4:4:4).
- Real frames plus Gaussian noise, sigma 5: above 50 % only at q95 (720p 4:2:2 57 %, 720p 4:4:4 82 %, 1080p
  4:4:4 71 %).
- Real frames plus Gaussian noise, sigma 15:

  | Resolution | q90 4:2:0 | q90 4:2:2 | Above 100 % |
  |---|---|---|---|
  | 720p | 48 % | 61 % | only q95 4:4:4 (134 %) |
  | 1080p | 44 % | 56 % | only q95 4:4:4 (129 %) |

- Uniform random noise (synthetic, the worst case): above 50 % at every setting; above 100 % for 4:4:4 at
  every quality, for 4:2:2 from q85, and for 4:2:0 only at q95 (117 %).
- Encode time on the sigma 15 frames at q90 4:2:2: about 3.1 ms (720p) and 7.3 ms (1080p), median.

## Other measurements

`IMWRITE_JPEG_OPTIMIZE` at q90 4:2:2: 1.81 to 4.66 ms at 720p for 6.7 % fewer bytes; 3.61 to 8.38 ms at 1080p
for 3.7 % fewer bytes. Not worth its time.

Colour conversion before the encode, one thread, median / p99 ms:

| Conversion | 720p | 1080p |
|---|---|---|
| YUY2 to BGR | 0.64 / 0.86 | 1.45 / 2.05 |
| NV12 to BGR | 0.59 / 1.04 | 1.61 / 2.04 |

The test buffers were built with numpy, because OpenCV has no direct BGR to YUY2 conversion.

The cameras' own JPEGs of the same frames, for size only (not image quality):

| Resolution | Median bytes | Bytes per pixel | cv2 quality of similar size (4:2:0 / 4:2:2) |
|---|---|---|---|
| 720p | 143,484 | 0.156 | q89 / q87 |
| 1080p | 188,469 | 0.091 | q91 / q89 |

Eight processes encoding at once, q90 4:2:2:

| Resolution | Per-process median ms | p99: median / worst ms |
|---|---|---|
| 720p | 2.29 | 4.27 / 4.60 |
| 1080p | 3.87 | 8.07 / 9.12 |

## Converting straight into a ring slot (main session, 2026-11-18, a scratch test, not kept)

- `cv2.cvtColor(yuy2, cv2.COLOR_YUV2BGR_YUY2, dst=slot)` with `slot` a numpy view of a
  `multiprocessing.shared_memory` block writes in place (`np.shares_memory` is true, pixels equal to the
  reference). Median: 0.34 ms at 720p and 0.78 ms at 1080p, against 0.78 and 1.97 ms for a conversion into a
  new array followed by a copy into the slot.
- `cv2.imdecode(jpeg, flags, slot)` is refused by the Python binding of OpenCV 5.1.0, so a decoded frame
  needs one copy into its slot. The copy alone takes 0.07 ms at 720p and 0.21 ms at 1080p.

## Not verified

- True raw YUY2 or NV12 frames from a camera. Noise only imitates a sensor.
- Image quality (PSNR, SSIM) per setting.
- Other CPUs, Linux and macOS.
