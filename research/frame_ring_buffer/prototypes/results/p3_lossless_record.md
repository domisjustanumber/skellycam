# P3 - lossless record path (decoupled recorder, gated cursor) vs current overwrite policy

## A. Stall-tolerance sweep: 5 cameras 1080p @60 fps, 5 recorders (2 ms synthetic work), one simultaneous stall at t=3 s, 8 s runs

Totals over 5 cameras. `recorder lost` = frames the recorder never got (lapped; overwrite policy). `ring-full drops` = frames the camera explicitly skipped (drop policy). `sensor skipped` = sensor ticks never grabbed (includes block-policy back-pressure; ~0-5 per run is scheduler noise).

| L (s @60) | stall ms | policy | produced | recorded | recorder lost (silent today) | ring-full drops (explicit) | sensor skipped | max blocked s | max lag slots | consecutive | lossless after ring |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 (0.27) | 200 | overwrite | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 12 | True | True |
| 16 (0.27) | 200 | block | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 12 | True | True |
| 16 (0.27) | 200 | drop | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 12 | True | True |
| 16 (0.27) | 1000 | overwrite | 2405 | 2180 | 225 | 0 | 0 | 0.00 | 60 | False | False |
| 16 (0.27) | 1000 | block | 2195 | 2195 | 0 | 0 | 210 | 0.73 | 16 | True | True |
| 16 (0.27) | 1000 | drop | 2185 | 2185 | 0 | 220 | 0 | 0.00 | 16 | True | True |
| 16 (0.27) | 2500 | overwrite | 2405 | 1730 | 675 | 0 | 0 | 0.00 | 150 | False | False |
| 16 (0.27) | 2500 | block | 1745 | 1745 | 0 | 0 | 660 | 2.23 | 16 | True | True |
| 16 (0.27) | 2500 | drop | 1735 | 1735 | 0 | 670 | 0 | 0.00 | 16 | True | True |
| 16 (0.27) | 3500 | overwrite | 2405 | 1430 | 975 | 0 | 0 | 0.00 | 210 | False | False |
| 16 (0.27) | 3500 | block | 1445 | 1445 | 0 | 0 | 960 | 3.23 | 16 | True | True |
| 16 (0.27) | 3500 | drop | 1435 | 1435 | 0 | 970 | 0 | 0.00 | 16 | True | True |
| 64 (1.07) | 200 | overwrite | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 12 | True | True |
| 64 (1.07) | 200 | block | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 12 | True | True |
| 64 (1.07) | 200 | drop | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 12 | True | True |
| 64 (1.07) | 1000 | overwrite | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 60 | True | True |
| 64 (1.07) | 1000 | block | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 60 | True | True |
| 64 (1.07) | 1000 | drop | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 60 | True | True |
| 64 (1.07) | 2500 | overwrite | 2405 | 1970 | 435 | 0 | 0 | 0.00 | 150 | False | False |
| 64 (1.07) | 2500 | block | 1985 | 1985 | 0 | 0 | 420 | 1.43 | 64 | True | True |
| 64 (1.07) | 2500 | drop | 1975 | 1975 | 0 | 430 | 0 | 0.00 | 64 | True | True |
| 64 (1.07) | 3500 | overwrite | 2405 | 1670 | 735 | 0 | 0 | 0.00 | 210 | False | False |
| 64 (1.07) | 3500 | block | 1685 | 1685 | 0 | 0 | 720 | 2.43 | 64 | True | True |
| 64 (1.07) | 3500 | drop | 1675 | 1675 | 0 | 730 | 0 | 0.00 | 64 | True | True |
| 172 (2.87) | 200 | overwrite | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 12 | True | True |
| 172 (2.87) | 200 | block | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 12 | True | True |
| 172 (2.87) | 200 | drop | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 12 | True | True |
| 172 (2.87) | 1000 | overwrite | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 60 | True | True |
| 172 (2.87) | 1000 | block | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 60 | True | True |
| 172 (2.87) | 1000 | drop | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 60 | True | True |
| 172 (2.87) | 2500 | overwrite | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 150 | True | True |
| 172 (2.87) | 2500 | block | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 150 | True | True |
| 172 (2.87) | 2500 | drop | 2405 | 2405 | 0 | 0 | 0 | 0.00 | 150 | True | True |
| 172 (2.87) | 3500 | overwrite | 2405 | 2210 | 195 | 0 | 0 | 0.00 | 210 | False | False |
| 172 (2.87) | 3500 | block | 2225 | 2225 | 0 | 0 | 180 | 0.63 | 172 | True | True |
| 172 (2.87) | 3500 | drop | 2215 | 2215 | 0 | 190 | 0 | 0.00 | 172 | True | True |

## B. Real encoder (cv2 'X264' -> MSMF H.264) as a decoupled recorder, block policy, 20 s, one 1500 ms stall at t=8 s

| size | L | produced | recorded | lost | sensor skipped | max lag slots | lag p99 (worst cam) | write() median / p99 / max ms (worst cam) | tick->written median / p99 ms | files decoded == produced | content mismatches (checked) | release s | CPU sum % (cams+recorders) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1080p | 172 | 6005 | 6005 | 0 | 0 | 90 | 81 | 0.67 / 3.98 / 5.41 | 1.9 / 1339.3 | True ([1201, 1201, 1201, 1201, 1201]) | 0 of 605 | 0.06 | 995 |
| 720p | 388 | 6005 | 6005 | 0 | 0 | 90 | 79 | 0.50 / 1.65 / 4.80 | 1.5 / 1310.1 | True ([1201, 1201, 1201, 1201, 1201]) | 0 of 605 | 0.07 | 330 |
