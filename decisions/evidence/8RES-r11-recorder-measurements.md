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
