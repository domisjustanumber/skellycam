# (a) ring-buffer write: put_frame unthrottled, N spawned writer processes
steady state 10.0s per config after one full first lap; times are per put_frame call

| size | N cams | mode | per-cam fps (min) | aggregate fps | aggregate GB/s | median ms | worst-cam p99 ms | first-lap median ms | 60fps budget used by put_frame (median) |
|---|---|---|---|---|---|---|---|---|---|
| 720p | 1 | production | 1539 | 1539 | 4.25 | 0.629 | 0.827 | 1.159 | 3.8% |
| 720p | 2 | production | 1370 | 2743 | 7.59 | 0.697 | 1.090 | 1.362 | 4.2% |
| 720p | 3 | production | 1137 | 3421 | 9.46 | 0.835 | 1.370 | 1.327 | 5.0% |
| 720p | 4 | production | 926 | 3775 | 10.44 | 0.999 | 1.874 | 1.504 | 6.0% |
| 720p | 5 | production | 819 | 4155 | 11.49 | 1.167 | 1.891 | 2.247 | 7.0% |
| 720p | 1 | single_copy_reference | 9649 | 9649 | 26.68 | 0.089 | 0.177 | 0.696 | 0.5% |
| 720p | 2 | single_copy_reference | 7913 | 15869 | 43.89 | 0.112 | 0.202 | 0.698 | 0.7% |
| 720p | 3 | single_copy_reference | 5916 | 17769 | 49.14 | 0.154 | 0.273 | 0.682 | 0.9% |
| 720p | 4 | single_copy_reference | 4462 | 17911 | 49.53 | 0.203 | 0.420 | 0.710 | 1.2% |
| 720p | 5 | single_copy_reference | 3318 | 16768 | 46.37 | 0.263 | 0.601 | 0.792 | 1.6% |
| 1080p | 1 | production | 717 | 717 | 4.46 | 1.352 | 1.825 | 2.898 | 8.1% |
| 1080p | 2 | production | 609 | 1221 | 7.60 | 1.573 | 2.347 | 3.090 | 9.4% |
| 1080p | 3 | production | 475 | 1434 | 8.92 | 2.010 | 3.265 | 3.161 | 12.1% |
| 1080p | 4 | production | 357 | 1437 | 8.94 | 2.661 | 4.543 | 3.146 | 16.0% |
| 1080p | 5 | production | 337 | 1700 | 10.57 | 2.936 | 4.412 | 3.215 | 17.6% |
| 1080p | 1 | single_copy_reference | 5160 | 5160 | 32.10 | 0.174 | 0.300 | 1.526 | 1.0% |
| 1080p | 2 | single_copy_reference | 3803 | 7612 | 47.36 | 0.242 | 0.415 | 1.532 | 1.5% |
| 1080p | 3 | single_copy_reference | 2539 | 7803 | 48.55 | 0.355 | 0.766 | 1.545 | 2.1% |
| 1080p | 4 | single_copy_reference | 1751 | 7315 | 45.51 | 0.495 | 1.273 | 1.737 | 3.0% |
| 1080p | 5 | single_copy_reference | 1122 | 6159 | 38.32 | 0.644 | 2.482 | 1.907 | 3.9% |
