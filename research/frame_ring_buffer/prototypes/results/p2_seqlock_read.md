# P2 - zero-copy seqlock reads

## A. Torn-read safety, adversarial unthrottled writer, 720p, 10.0s per row (reader in parent process)

| L slots | target | reader | writer fps | reads | accepted | SILENT TEARS (accepted, mixed pixels) | accepted but wrong frame | rejected (seq / fn / stale) | accepted-read latency median ms |
|---|---|---|---|---|---|---|---|---|---|
| 2 | latest | copy_fncheck | 4293 | 44276 | 44276 | 15 | 0 | 0 / 0 / 0 | 0.215 |
| 2 | latest | seqlock_copy | 4259 | 45085 | 16953 | 0 | 0 | 28132 / 0 / 0 | 0.221 |
| 2 | latest | seqlock_view | 5285 | 50652 | 152 | 0 | 0 | 50500 / 0 / 0 | 0.190 |
| 2 | oldest | copy_fncheck | 4368 | 43482 | 43328 | 41834 | 1068 | 0 / 101 / 53 | 0.219 |
| 2 | oldest | seqlock_copy | 4283 | 3716410 | 0 | 0 | 0 | 3716410 / 0 / 0 | nan |
| 2 | oldest | seqlock_view | 5709 | 9484255 | 0 | 0 | 0 | 9484255 / 0 / 0 | nan |
| 8 | latest | copy_fncheck | 4401 | 43023 | 43023 | 0 | 0 | 0 / 0 / 0 | 0.221 |
| 8 | latest | seqlock_copy | 4373 | 42784 | 42784 | 0 | 0 | 0 / 0 / 0 | 0.223 |
| 8 | latest | seqlock_view | 5564 | 46598 | 46598 | 0 | 0 | 0 / 0 / 0 | 0.205 |
| 8 | oldest | copy_fncheck | 4382 | 43105 | 42757 | 40165 | 1846 | 0 / 249 / 99 | 0.221 |
| 8 | oldest | seqlock_copy | 4261 | 3452112 | 0 | 0 | 0 | 3452112 / 0 / 0 | nan |
| 8 | oldest | seqlock_view | 5747 | 10096636 | 0 | 0 | 0 | 10096636 / 0 / 0 | nan |
| 388 | latest | copy_fncheck | 4324 | 42694 | 42694 | 0 | 0 | 0 / 0 / 0 | 0.223 |
| 388 | latest | seqlock_copy | 4313 | 42655 | 42655 | 0 | 0 | 0 / 0 / 0 | 0.224 |
| 388 | latest | seqlock_view | 5485 | 46682 | 46682 | 0 | 0 | 0 / 0 / 0 | 0.204 |
| 388 | oldest | copy_fncheck | 4316 | 42712 | 42359 | 39854 | 1778 | 0 / 248 / 105 | 0.223 |
| 388 | oldest | seqlock_copy | 4199 | 3551326 | 0 | 0 | 0 | 3551326 / 0 / 0 | nan |
| 388 | oldest | seqlock_view | 5590 | 9860734 | 0 | 0 | 0 | 9860734 / 0 / 0 | nan |

## B. Cold read cost, 5 spawned writers at 60 fps, newest frame, 5 interleaved rounds x 2.0s per style

| size | style | full-frame copies | median ms | p99 ms | max ms | n | validation failures |
|---|---|---|---|---|---|---|---|
| 1080p | seqlock_copy | 1 | 0.3784 | 0.4547 | 0.8965 | 600 | 0 |
| 1080p | seqlock_view | 0 | 0.0204 | 0.0393 | 0.1107 | 600 | 0 |
| 1080p | seqlock_view_resize | 0 | 0.5062 | 0.6708 | 0.8915 | 600 | 0 |
| 1080p | multi5_seqlock_copy | 5 | 1.8365 | 2.0269 | 4.5907 | 600 | 0 |
| 1080p | multi5_seqlock_view | 0 | 0.0333 | 0.0569 | 0.0661 | 600 | 0 |
| 1080p | multi5_seqlock_view_resize | 0 | 2.5013 | 3.3719 | 4.1851 | 600 | 0 |
| 720p | seqlock_copy | 1 | 0.1837 | 0.2468 | 0.4556 | 600 | 0 |
| 720p | seqlock_view | 0 | 0.0209 | 0.0375 | 0.0392 | 600 | 0 |
| 720p | seqlock_view_resize | 0 | 0.2606 | 0.3426 | 0.3708 | 600 | 0 |
| 720p | multi5_seqlock_copy | 5 | 0.8540 | 0.9992 | 2.0362 | 600 | 0 |
| 720p | multi5_seqlock_view | 0 | 0.0334 | 0.0583 | 0.0722 | 600 | 0 |
| 720p | multi5_seqlock_view_resize | 0 | 1.2111 | 1.5478 | 1.5857 | 600 | 0 |

Baseline for comparison (baseline/results/b_read.md, idle 20261027 re-run, real SkellyCam, cold medians): 1080p by_index_reused 0.4226 ms (p99 0.5007), view_no_copy 0.0165 ms, multiframe_latest (5 cams) 2.3533 ms (p99 7.2891), multiframe_by_number 6.6275 ms; 720p by_index_reused 0.2150 ms, multiframe_latest 1.0629 ms.
