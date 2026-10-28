# P2 - zero-copy seqlock reads

## A. Torn-read safety, adversarial unthrottled writer, 720p, 1.0s per row (reader in parent process)

| L slots | target | reader | writer fps | reads | accepted | SILENT TEARS (accepted, mixed pixels) | accepted but wrong frame | rejected (seq / fn / stale) | accepted-read latency median ms |
|---|---|---|---|---|---|---|---|---|---|
| 2 | latest | copy_fncheck | 3526 | 3581 | 3581 | 32 | 0 | 0 / 0 / 0 | 0.261 |
| 2 | latest | seqlock_copy | 3576 | 3591 | 1041 | 0 | 0 | 2550 / 0 / 0 | 0.256 |
| 2 | latest | seqlock_view | 4730 | 4611 | 84 | 0 | 0 | 4527 / 0 / 0 | 0.208 |
| 2 | oldest | copy_fncheck | 3802 | 3754 | 3717 | 3528 | 131 | 0 / 27 / 10 | 0.252 |
| 2 | oldest | seqlock_copy | 3761 | 375990 | 0 | 0 | 0 | 375990 / 0 / 0 | nan |
| 2 | oldest | seqlock_view | 5068 | 840761 | 0 | 0 | 0 | 840761 / 0 / 0 | nan |
| 8 | latest | copy_fncheck | 3532 | 3787 | 3787 | 0 | 0 | 0 / 0 / 0 | 0.255 |
| 8 | latest | seqlock_copy | 3389 | 3307 | 3306 | 0 | 0 | 1 / 0 / 0 | 0.282 |
| 8 | latest | seqlock_view | 3666 | 3364 | 3363 | 0 | 0 | 1 / 0 / 0 | 0.274 |
| 8 | oldest | copy_fncheck | 3022 | 3009 | 2984 | 2800 | 119 | 0 / 17 / 8 | 0.309 |
| 8 | oldest | seqlock_copy | 3344 | 387801 | 0 | 0 | 0 | 387801 / 0 / 0 | nan |
| 8 | oldest | seqlock_view | 3771 | 653709 | 0 | 0 | 0 | 653709 / 0 / 0 | nan |
| 388 | latest | copy_fncheck | 3114 | 3499 | 3499 | 0 | 0 | 0 / 0 / 0 | 0.260 |
| 388 | latest | seqlock_copy | 3472 | 3841 | 3841 | 0 | 0 | 0 / 0 / 0 | 0.246 |
| 388 | latest | seqlock_view | 3691 | 3621 | 3621 | 0 | 0 | 0 / 0 / 0 | 0.249 |
| 388 | oldest | copy_fncheck | 2940 | 3231 | 3210 | 2996 | 141 | 0 / 17 / 4 | 0.284 |
| 388 | oldest | seqlock_copy | 2860 | 368518 | 0 | 0 | 0 | 368518 / 0 / 0 | nan |
| 388 | oldest | seqlock_view | 3375 | 637200 | 0 | 0 | 0 | 637200 / 0 / 0 | nan |

## B. Cold read cost, 5 spawned writers at 60 fps, newest frame, 5 interleaved rounds x 0.3s per style

| size | style | full-frame copies | median ms | p99 ms | max ms | n | validation failures |
|---|---|---|---|---|---|---|---|
| 1080p | seqlock_copy | 1 | 0.4248 | 1.1382 | 1.4487 | 90 | 0 |
| 1080p | seqlock_view | 0 | 0.0393 | 0.1129 | 0.1225 | 90 | 0 |
| 1080p | seqlock_view_resize | 0 | 0.5603 | 1.1956 | 1.5793 | 90 | 0 |
| 1080p | multi5_seqlock_copy | 5 | 2.5224 | 4.3431 | 4.9791 | 87 | 0 |
| 1080p | multi5_seqlock_view | 0 | 0.0553 | 0.1076 | 0.1210 | 88 | 0 |
| 1080p | multi5_seqlock_view_resize | 0 | 2.9668 | 4.9888 | 5.7952 | 92 | 0 |
| 720p | seqlock_copy | 1 | 0.2222 | 0.5705 | 0.6024 | 90 | 0 |
| 720p | seqlock_view | 0 | 0.0350 | 0.0618 | 0.0622 | 90 | 0 |
| 720p | seqlock_view_resize | 0 | 0.2863 | 0.4613 | 0.5443 | 90 | 0 |
| 720p | multi5_seqlock_copy | 5 | 1.0013 | 1.5792 | 2.1229 | 90 | 0 |
| 720p | multi5_seqlock_view | 0 | 0.0527 | 0.0903 | 0.0975 | 90 | 0 |
| 720p | multi5_seqlock_view_resize | 0 | 1.3022 | 3.6980 | 3.7659 | 90 | 0 |

Baseline for comparison (baseline/results/b_read.md, real SkellyCam, same harness shape): 1080p get_data_by_index 0.498 ms, view 0.032 ms, get_latest_multiframe (5 cams) 2.415 ms; 720p get_data_by_index 0.422 ms, get_latest_multiframe 1.513 ms.
