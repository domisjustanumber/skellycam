# 8RES — Full tables of the R11 recorder measurements

These are the tables of [ADR-8RES](../entries/8RES-r11-measurements-of-the-5a-recorder.md), as
`decisions/scripts/recorder_bench.py table` prints them from the JSON summaries of the benchmarks.
Synthetic frames only. Times are in ms.

- T-REC-STALL: the values of the camera whose MKV file object stalls (camera 0). "Lateness of the
  other cameras" is the largest value over the other camera processes. `stalled` is the index of the
  camera that raised `RecorderStalled`, or `None`.
- T-REC-KILL: "lost frames" is the frames that the parent saw given minus the rows on disk. A
  negative value means that the child gave more frames than the parent saw before the kill.
- T-REC-FSYNC and T-REC-GIL: p50 is the median over the camera processes; p99, p99.9 and max are the
  largest value over the camera processes. "MKV write" is one `write` call of the MKV file object.
  "fsync" is one `os.fsync` call (the MKV or the CSV). The `t_rec_fsync` rows (`on_60s`, `off_60s`,
  `on_600s`) are 16 processes at 1080p60; the `fsync_matrix` rows are `<n>cam_<fps>_<on|off>` at
  1080p. "CPU s" includes the start of the process.

## T-REC-STALL

| cameras | mode | stall s | stalled | frame count | high-water items (s) | give waits | longest wait ms | replaced | lateness of the other cameras p50 / p99 / max ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1280x720 30/1 | 0.5 | None | 1799 | 15 (0.50) | 0 | 0 | 0 | - |
| 1 | 1280x720 30/1 | 10.0 | None | 1591 | 90 (3.00) | 2 | 6968 | 208 | - |
| 1 | 1280x720 30/1 | 15.0 | 0 | 391 | 90 (3.00) | 1 | 10000 | 300 | - |
| 1 | 1280x720 30/1 | 2.0 | None | 1799 | 60 (2.00) | 0 | 0 | 0 | - |
| 1 | 1920x1080 60/1 | 0.5 | None | 3597 | 30 (0.50) | 0 | 0 | 1 | - |
| 1 | 1920x1080 60/1 | 10.0 | None | 3179 | 180 (3.00) | 2 | 6987 | 418 | - |
| 1 | 1920x1080 60/1 | 15.0 | 0 | 481 | 180 (3.00) | 1 | 10001 | 600 | - |
| 1 | 1920x1080 60/1 | 2.0 | None | 3597 | 120 (2.00) | 0 | 0 | 0 | - |
| 4 | 1280x720 30/1 | 0.5 | None | 1799 | 15 (0.50) | 0 | 0 | 0 | 0.35 / 0.63 / 1.23 |
| 4 | 1280x720 30/1 | 10.0 | None | 1799 | 90 (3.00) | 2 | 6970 | 208 | 0.35 / 0.65 / 3.96 |
| 4 | 1280x720 30/1 | 15.0 | 0 | 696 | 90 (3.00) | 1 | 10000 | 300 | 0.35 / 0.63 / 0.78 |
| 4 | 1280x720 30/1 | 2.0 | None | 1799 | 60 (2.00) | 0 | 0 | 0 | 0.35 / 0.63 / 1.30 |
| 4 | 1920x1080 60/1 | 0.5 | None | 3598 | 30 (0.50) | 0 | 0 | 0 | 0.36 / 0.64 / 1.15 |
| 4 | 1920x1080 60/1 | 10.0 | None | 3597 | 180 (3.00) | 2 | 6987 | 418 | 0.38 / 0.68 / 1.08 |
| 4 | 1920x1080 60/1 | 15.0 | 0 | 1087 | 180 (3.00) | 1 | 10002 | 600 | 0.36 / 0.60 / 0.73 |
| 4 | 1920x1080 60/1 | 2.0 | None | 3597 | 120 (2.00) | 0 | 0 | 0 | 0.35 / 0.63 / 1.04 |

## T-REC-KILL

| case | queue | kills | lost frames min / median / max | blocks - rows | torn CSV bytes max |
|---|---|---|---|---|---|
| 1280x720, normal writing | 90 | 20 | 0 / 1 / 1 | [0] | 0 |
| 1280x720, full queue | 90 | 20 | 39 / 92 / 92 | [0] | 0 |
| 640x480 placeholders, normal writing | 90 | 20 | -3 / 1 / 1 | [0] | 0 |
| 640x480 placeholders, full queue | 90 | 20 | 92 / 92 / 92 | [0] | 0 |

## T-REC-FSYNC

| run | MKV write p50 / p99 / p99.9 / max ms | fsync p50 / max ms | high-water items | lateness p50 / p99 / max ms | CPU s per process |
|---|---|---|---|---|---|
| 16cam_30_off #1 | 0.01 / 0.08 / 0.20 / 10.03 | 0.00 / 0.00 | 1 | 0.33 / 0.78 / 3.97 | 9.6 |
| 16cam_30_on #1 | 0.01 / 0.09 / 0.19 / 21.47 | 1.12 / 69.88 | 2 | 0.32 / 0.64 / 1.14 | 9.4 |
| 16cam_60_off #1 | 0.01 / 0.09 / 0.18 / 3.70 | 0.00 / 0.02 | 1 | 0.31 / 0.77 / 5.29 | 10.7 |
| 16cam_60_on #1 | 0.01 / 0.10 / 0.21 / 12.04 | 2.06 / 104.90 | 6 | 0.31 / 0.66 / 1.71 | 10.8 |
| 1cam_30_off #1 | 0.01 / 0.09 / 0.15 / 1.87 | 0.00 / 0.00 | 1 | 0.34 / 0.60 / 0.83 | 3.1 |
| 1cam_30_on #1 | 0.01 / 0.08 / 0.15 / 1.85 | 0.46 / 3.63 | 1 | 0.34 / 0.61 / 1.37 | 2.7 |
| 1cam_60_off #1 | 0.01 / 0.09 / 0.17 / 1.02 | 0.00 / 0.00 | 1 | 0.35 / 0.62 / 0.92 | 5.5 |
| 1cam_60_on #1 | 0.01 / 0.09 / 0.15 / 1.77 | 0.54 / 9.26 | 1 | 0.34 / 0.61 / 0.69 | 5.6 |
| 4cam_30_off #1 | 0.01 / 0.09 / 0.16 / 0.37 | 0.00 / 0.00 | 1 | 0.35 / 0.62 / 0.84 | 3.9 |
| 4cam_30_on #1 | 0.01 / 0.08 / 0.15 / 0.35 | 1.12 / 19.77 | 1 | 0.34 / 0.62 / 0.75 | 4.0 |
| 4cam_60_off #1 | 0.01 / 0.09 / 0.18 / 92.05 | 0.00 / 0.00 | 5 | 0.35 / 0.63 / 0.95 | 4.6 |
| 4cam_60_on #1 | 0.01 / 0.09 / 0.17 / 0.91 | 1.54 / 105.08 | 6 | 0.33 / 0.64 / 1.02 | 4.6 |
| 8cam_30_off #1 | 0.01 / 0.09 / 0.17 / 1.38 | 0.00 / 0.00 | 1 | 0.34 / 0.63 / 1.35 | 5.4 |
| 8cam_30_on #1 | 0.01 / 0.09 / 0.22 / 1.50 | 1.14 / 77.25 | 2 | 0.34 / 0.62 / 1.49 | 5.9 |
| 8cam_60_off #1 | 0.01 / 0.07 / 0.14 / 2.04 | 0.00 / 0.00 | 1 | 0.36 / 0.64 / 10.63 | 5.5 |
| 8cam_60_on #1 | 0.01 / 0.08 / 0.18 / 1.50 | 1.95 / 49.66 | 5 | 0.33 / 0.64 / 1.49 | 6.6 |
| off_60s #1 | 0.01 / 0.13 / 0.29 / 10.59 | 0.00 / 0.00 | 1 | 0.34 / 0.75 / 1.90 | 10.1 |
| off_60s #2 | 0.01 / 0.13 / 0.34 / 46.03 | 0.00 / 0.01 | 2 | 0.33 / 0.65 / 3.20 | 10.5 |
| off_60s #3 | 0.01 / 0.15 / 0.27 / 19.34 | 0.00 / 0.00 | 1 | 0.31 / 0.63 / 1.09 | 10.7 |
| on_600s #1 | 0.01 / 0.12 / 0.21 / 33.20 | 2.03 / 166.73 | 11 | 0.31 / 0.69 / 10.33 | 26.5 |
| on_60s #1 | 0.01 / 0.14 / 0.26 / 19.67 | 2.07 / 155.46 | 9 | 0.31 / 0.97 / 16.22 | 11.1 |
| on_60s #2 | 0.01 / 0.11 / 0.23 / 21.23 | 2.13 / 162.72 | 9 | 0.31 / 0.64 / 1.64 | 10.5 |
| on_60s #3 | 0.01 / 0.12 / 0.21 / 8.86 | 2.02 / 36.08 | 2 | 0.29 / 0.72 / 1.32 | 10.6 |

## T-REC-GIL

| writer | rate | lateness p50 / p99 / max ms | interval jitter p50 / p99 / max ms | loop step p50 / p99 / max ms |
|---|---|---|---|---|
| off | 30 fps (4) | 0.34 / 0.62 / 9.21 | 0.22 / 0.46 / 8.68 | 0.00 / 0.00 / 0.10 |
| off | 60 fps (1) | 0.34 / 0.61 / 9.21 | 0.13 / 0.49 / 8.78 | 0.00 / 0.00 / 0.07 |
| on | 30 fps (4) | 0.33 / 0.61 / 9.62 | 0.24 / 0.45 / 9.35 | 0.02 / 0.05 / 0.30 |
| on | 60 fps (1) | 0.34 / 0.61 / 10.60 | 0.14 / 0.47 / 10.36 | 0.02 / 0.05 / 0.26 |

## Update of 2026-11-20: runs after the review fixes and D1

These runs were made on commit fb39e2f2f, after the review fixes
([ADR-T24F](../entries/T24F-choices-of-the-5a-recorder-code.md)) and D1 of
[ADR-C6DE](../entries/C6DE-stall-as-no-progress-limits-and-no-fat-disk.md), on the same machine. The
machine had a steady CPU load of about 20 % from other idle sessions. The fsync test and the fsync
matrix ran two times (run A and run B). [ADR-953T](../entries/953T-r11-measurements-after-the-review-fixes.md)
records this update.

T-REC-KILL, normal writing: two of 40 kills now lose 2 frames with blocks − rows = 1 (the first
runs had none in 40). The same random seed gives the same kill points, so the kills compare one to
one. For a frame k, the writer muxes block k (which writes block k − 1), then writes row k − 1. A
kill in that order gives:

- before the write of block k − 1 returns (also inside it): blocks = rows = k − 1;
- after the write of block k − 1 returns and before row k − 1 is written: blocks = k, rows = k − 1
  (block k − 1 has no row and is cut by the completion: one more lost frame);
- after row k − 1 is written: blocks = rows = k.

No window leaves a row whose block was not handed to the OS: row k − 1 is written only after the
write of block k − 1 returned with each byte. The second window was measured with a probe script
(not kept, 600 frames at 720p): p50 31 µs, p99 57 to 78 µs, with or without the review steps
(write wrapper, progress stamps). The review fixes did not widen it. 0 of 40 and 2 of 40 hits are
the same rate within chance. The window cannot close at no cost: a row needs the offset of its block,
which is known only after the write returns. Full queue: the first runs had one kill with 39 lost
frames, where the test stopped its wait for events early (`given` 47); the rows on disk were 8 in
every full-queue kill of both runs.

### T-REC-STALL

| cameras | mode | stall s | stalled | frame count | high-water items (s) | give waits | longest wait ms | replaced | lateness of the other cameras p50 / p99 / max ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1280x720 30/1 | 0.5 | None | 1799 | 15 (0.50) | 0 | 0 | 0 | - |
| 1 | 1280x720 30/1 | 10.0 | None | 1591 | 90 (3.00) | 2 | 6969 | 208 | - |
| 1 | 1280x720 30/1 | 15.0 | 0 | 391 | 90 (3.00) | 1 | 10001 | 300 | - |
| 1 | 1280x720 30/1 | 2.0 | None | 1799 | 60 (2.00) | 0 | 0 | 0 | - |
| 1 | 1920x1080 60/1 | 0.5 | None | 3597 | 30 (0.50) | 0 | 0 | 0 | - |
| 1 | 1920x1080 60/1 | 10.0 | None | 3179 | 180 (3.00) | 2 | 6986 | 419 | - |
| 1 | 1920x1080 60/1 | 15.0 | 0 | 481 | 180 (3.00) | 1 | 10000 | 600 | - |
| 1 | 1920x1080 60/1 | 2.0 | None | 3597 | 120 (2.00) | 0 | 0 | 0 | - |
| 4 | 1280x720 30/1 | 0.5 | None | 1799 | 15 (0.50) | 0 | 0 | 0 | 0.34 / 0.60 / 3.55 |
| 4 | 1280x720 30/1 | 10.0 | None | 1799 | 90 (3.00) | 2 | 6968 | 208 | 0.34 / 0.61 / 1.39 |
| 4 | 1280x720 30/1 | 15.0 | 0 | 691 | 90 (3.00) | 1 | 10000 | 300 | 0.34 / 0.62 / 0.79 |
| 4 | 1280x720 30/1 | 2.0 | None | 1799 | 60 (2.00) | 0 | 0 | 0 | 0.35 / 0.64 / 0.88 |
| 4 | 1920x1080 60/1 | 0.5 | None | 3597 | 30 (0.50) | 0 | 0 | 0 | 0.33 / 0.60 / 1.23 |
| 4 | 1920x1080 60/1 | 10.0 | None | 3597 | 180 (3.00) | 2 | 6986 | 418 | 0.33 / 0.60 / 1.03 |
| 4 | 1920x1080 60/1 | 15.0 | 0 | 1087 | 180 (3.00) | 1 | 10000 | 600 | 0.34 / 0.61 / 0.69 |
| 4 | 1920x1080 60/1 | 2.0 | None | 3597 | 120 (2.00) | 0 | 0 | 0 | 0.38 / 0.64 / 1.86 |

### T-REC-KILL

| case | queue | kills | lost frames min / median / max | blocks - rows | torn CSV bytes max |
|---|---|---|---|---|---|
| 1280x720, normal writing | 90 | 20 | 1 / 1 / 2 | [0, 1] | 0 |
| 1280x720, full queue | 90 | 20 | 92 / 92 / 92 | [0] | 0 |
| 640x480 placeholders, normal writing | 90 | 20 | 0 / 1 / 2 | [0, 1] | 0 |
| 640x480 placeholders, full queue | 90 | 20 | 92 / 92 / 92 | [0] | 0 |

### T-REC-GIL

| writer | rate | lateness p50 / p99 / max ms | interval jitter p50 / p99 / max ms | loop step p50 / p99 / max ms |
|---|---|---|---|---|
| off | 30 fps (4) | 0.33 / 0.64 / 1.76 | 0.25 / 0.49 / 1.61 | 0.00 / 0.00 / 0.05 |
| off | 60 fps (1) | 0.35 / 0.60 / 1.61 | 0.15 / 0.45 / 1.42 | 0.00 / 0.00 / 0.08 |
| on | 30 fps (4) | 0.34 / 0.64 / 2.10 | 0.24 / 0.48 / 1.66 | 0.02 / 0.05 / 0.21 |
| on | 60 fps (1) | 0.30 / 0.60 / 1.46 | 0.16 / 0.47 / 1.10 | 0.02 / 0.05 / 0.17 |

### T-REC-FSYNC, run A

| run | MKV write p50 / p99 / p99.9 / max ms | fsync p50 / max ms | high-water items | lateness p50 / p99 / max ms | CPU s per process |
|---|---|---|---|---|---|
| off_60s #1 | 0.01 / 0.10 / 0.20 / 8.27 | 0.00 / 0.00 | 1 | 0.35 / 0.64 / 1.46 | 10.0 |
| off_60s #2 | 0.01 / 0.10 / 0.23 / 8.53 | 0.00 / 0.00 | 1 | 0.31 / 0.66 / 5.89 | 10.1 |
| off_60s #3 | 0.01 / 0.09 / 0.22 / 10.09 | 0.00 / 0.00 | 1 | 0.31 / 0.65 / 1.39 | 9.8 |
| on_600s #1 | 0.01 / 0.10 / 0.20 / 13.88 | 2.09 / 152.68 | 10 | 0.31 / 0.68 / 3.40 | 26.2 |
| on_60s #1 | 0.01 / 0.11 / 0.19 / 4.78 | 2.00 / 127.18 | 7 | 0.30 / 0.65 / 1.56 | 9.7 |
| on_60s #2 | 0.01 / 0.09 / 0.15 / 1.88 | 2.04 / 118.61 | 7 | 0.33 / 0.71 / 1.80 | 10.3 |
| on_60s #3 | 0.01 / 0.10 / 0.20 / 12.91 | 2.02 / 147.99 | 4 | 0.31 / 0.61 / 1.02 | 10.4 |
| 16cam_30_off #1 | 0.01 / 0.08 / 0.16 / 1.38 | 0.00 / 0.00 | 1 | 0.33 / 0.61 / 1.36 | 9.7 |
| 16cam_30_on #1 | 0.01 / 0.10 / 0.18 / 1.51 | 1.10 / 109.38 | 3 | 0.32 / 0.65 / 1.54 | 9.5 |
| 16cam_60_off #1 | 0.01 / 0.07 / 0.17 / 1.51 | 0.00 / 0.01 | 1 | 0.33 / 0.64 / 1.48 | 10.5 |
| 16cam_60_on #1 | 0.01 / 0.09 / 0.19 / 0.88 | 2.03 / 161.78 | 9 | 0.31 / 0.65 / 1.06 | 10.2 |
| 1cam_30_off #1 | 0.01 / 0.08 / 0.13 / 1.37 | 0.00 / 0.00 | 1 | 0.34 / 0.61 / 0.75 | 2.6 |
| 1cam_30_on #1 | 0.01 / 0.07 / 0.12 / 0.30 | 0.83 / 20.83 | 1 | 0.33 / 0.60 / 0.71 | 2.3 |
| 1cam_60_off #1 | 0.01 / 0.07 / 0.12 / 1.40 | 0.00 / 0.00 | 1 | 0.33 / 0.60 / 0.72 | 4.3 |
| 1cam_60_on #1 | 0.01 / 0.08 / 0.12 / 1.71 | 0.51 / 9.78 | 1 | 0.33 / 0.60 / 0.71 | 3.5 |
| 4cam_30_off #1 | 0.01 / 0.08 / 0.13 / 1.21 | 0.00 / 0.00 | 1 | 0.34 / 0.62 / 0.83 | 3.3 |
| 4cam_30_on #1 | 0.01 / 0.10 / 0.18 / 0.33 | 0.36 / 8.78 | 1 | 0.34 / 0.61 / 1.64 | 3.6 |
| 4cam_60_off #1 | 0.01 / 0.09 / 0.17 / 1.83 | 0.00 / 0.00 | 1 | 0.32 / 0.61 / 1.02 | 3.8 |
| 4cam_60_on #1 | 0.01 / 0.08 / 0.11 / 1.49 | 1.34 / 11.85 | 1 | 0.33 / 0.63 / 1.20 | 4.7 |
| 8cam_30_off #1 | 0.01 / 0.08 / 0.15 / 1.44 | 0.00 / 0.00 | 1 | 0.33 / 0.62 / 1.05 | 5.4 |
| 8cam_30_on #1 | 0.01 / 0.09 / 0.15 / 0.47 | 1.11 / 19.67 | 1 | 0.34 / 0.62 / 1.10 | 5.4 |
| 8cam_60_off #1 | 0.01 / 0.11 / 0.20 / 1.45 | 0.00 / 0.00 | 1 | 0.33 / 0.64 / 1.16 | 5.9 |
| 8cam_60_on #1 | 0.01 / 0.11 / 0.21 / 1.55 | 1.98 / 115.40 | 6 | 0.33 / 0.62 / 0.87 | 5.6 |

### T-REC-FSYNC, run B

| run | MKV write p50 / p99 / p99.9 / max ms | fsync p50 / max ms | high-water items | lateness p50 / p99 / max ms | CPU s per process |
|---|---|---|---|---|---|
| off_60s #1 | 0.01 / 0.08 / 0.16 / 14.17 | 0.00 / 0.01 | 1 | 0.36 / 0.65 / 1.65 | 9.9 |
| off_60s #2 | 0.01 / 0.07 / 0.12 / 25.32 | 0.00 / 0.00 | 1 | 0.29 / 0.64 / 1.21 | 10.2 |
| off_60s #3 | 0.01 / 0.11 / 0.21 / 2.95 | 0.00 / 0.00 | 1 | 0.32 / 0.64 / 3.20 | 9.6 |
| on_600s #1 | 0.01 / 0.11 / 0.19 / 27.84 | 2.07 / 182.35 | 11 | 0.28 / 0.66 / 15.00 | 25.7 |
| on_60s #1 | 0.01 / 0.11 / 0.20 / 4.08 | 2.08 / 117.96 | 7 | 0.36 / 0.65 / 1.21 | 10.2 |
| on_60s #2 | 0.01 / 0.10 / 0.20 / 6.50 | 2.04 / 157.77 | 9 | 0.37 / 0.79 / 1.35 | 9.5 |
| on_60s #3 | 0.01 / 0.10 / 0.21 / 38.42 | 2.02 / 29.11 | 2 | 0.26 / 0.65 / 1.26 | 9.9 |
| 16cam_30_off #1 | 0.01 / 0.08 / 0.16 / 1.51 | 0.00 / 0.00 | 1 | 0.32 / 0.64 / 1.36 | 9.5 |
| 16cam_30_on #1 | 0.01 / 0.08 / 0.24 / 2.96 | 1.11 / 13.39 | 1 | 0.34 / 0.64 / 1.32 | 9.5 |
| 16cam_60_off #1 | 0.01 / 0.08 / 0.16 / 7.11 | 0.00 / 0.00 | 1 | 0.32 / 0.68 / 1.77 | 10.2 |
| 16cam_60_on #1 | 0.01 / 0.08 / 0.17 / 2.29 | 2.00 / 133.25 | 8 | 0.32 / 0.63 / 0.91 | 9.9 |
| 1cam_30_off #1 | 0.01 / 0.07 / 0.10 / 1.77 | 0.00 / 0.00 | 1 | 0.34 / 0.61 / 0.66 | 2.3 |
| 1cam_30_on #1 | 0.01 / 0.07 / 0.10 / 0.15 | 1.18 / 6.21 | 1 | 0.34 / 0.61 / 1.63 | 2.9 |
| 1cam_60_off #1 | 0.01 / 0.07 / 0.11 / 1.74 | 0.00 / 0.00 | 1 | 0.34 / 0.62 / 0.74 | 5.2 |
| 1cam_60_on #1 | 0.01 / 0.07 / 0.10 / 1.37 | 0.41 / 11.16 | 1 | 0.33 / 0.60 / 1.63 | 4.7 |
| 4cam_30_off #1 | 0.01 / 0.10 / 0.18 / 0.91 | 0.00 / 0.00 | 1 | 0.34 / 0.62 / 1.37 | 3.0 |
| 4cam_30_on #1 | 0.01 / 0.07 / 0.12 / 6.38 | 0.47 / 10.58 | 1 | 0.34 / 0.62 / 1.71 | 3.8 |
| 4cam_60_off #1 | 0.01 / 0.07 / 0.11 / 1.37 | 0.00 / 0.00 | 1 | 0.33 / 0.61 / 1.76 | 4.5 |
| 4cam_60_on #1 | 0.01 / 0.07 / 0.10 / 1.42 | 1.62 / 13.10 | 1 | 0.33 / 0.60 / 1.40 | 4.4 |
| 8cam_30_off #1 | 0.01 / 0.10 / 0.17 / 1.57 | 0.00 / 0.00 | 1 | 0.34 / 0.62 / 0.80 | 5.7 |
| 8cam_30_on #1 | 0.01 / 0.07 / 0.12 / 1.54 | 1.10 / 10.54 | 1 | 0.34 / 0.63 / 1.00 | 5.0 |
| 8cam_60_off #1 | 0.01 / 0.07 / 0.13 / 1.45 | 0.00 / 0.00 | 1 | 0.35 / 0.64 / 0.99 | 6.4 |
| 8cam_60_on #1 | 0.01 / 0.07 / 0.12 / 1.57 | 1.96 / 115.15 | 7 | 0.33 / 0.63 / 1.24 | 5.4 |
