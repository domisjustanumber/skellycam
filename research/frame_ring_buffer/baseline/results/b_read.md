# (b) ring-buffer read styles (5 cameras written at 60 fps by 5 spawned writer processes)
cold = first read after the writer published the slot; warm = immediate re-read of the same slot

| size | style | cams per read | n | cold median ms | range of 5 round medians ms | cold p99 ms | warm median ms | per-camera cold median ms | cold GB/s | frame_number mismatches |
|---|---|---|---|---|---|---|---|---|---|---|
| 720p | latest_reused | 1 | 605 | 0.2081 | 0.191-0.788 | 0.8445 | 0.1437 | 0.2081 | 13.29 | 0 |
| 720p | latest_alloc | 1 | 600 | 0.6112 | 0.574-1.145 | 1.2415 | 0.5437 | 0.6112 | 4.52 | 0 |
| 720p | by_index_reused | 1 | 605 | 0.2150 | 0.201-0.779 | 0.8344 | 0.1555 | 0.2150 | 12.86 | 0 |
| 720p | next_consuming | 1 | 604 | 0.2852 | 0.246-0.833 | 0.9301 | 0.0000 | 0.2852 | 9.7 | 0 |
| 720p | view_no_copy(REFERENCE) | 1 | 605 | 0.0153 | 0.014-0.016 | 0.0253 | 0.0068 | 0.0153 | 180.75 | 0 |
| 720p | multiframe_latest | 5 | 605 | 1.0629 | 1.022-3.238 | 3.3956 | 0.9444 | 0.2126 | 13.01 | 0 |
| 720p | multiframe_by_number | 5 | 600 | 3.1533 | 2.774-5.048 | 5.5048 | 2.9033 | 0.6307 | 4.38 | 0 |
| 720p | multiframe_views(REFERENCE) | 5 | 605 | 0.0516 | 0.051-0.054 | 0.0845 | 0.0454 | 0.0103 | 267.97 | 0 |
| 1080p | latest_reused | 1 | 605 | 0.4213 | 0.391-1.685 | 1.7579 | 0.3372 | 0.4213 | 14.77 | 0 |
| 1080p | latest_alloc | 1 | 600 | 1.1791 | 1.125-1.349 | 2.4501 | 1.1006 | 1.1791 | 5.28 | 0 |
| 1080p | by_index_reused | 1 | 605 | 0.4226 | 0.390-0.437 | 0.5007 | 0.3467 | 0.4226 | 14.72 | 0 |
| 1080p | next_consuming | 1 | 604 | 0.4829 | 0.433-1.662 | 1.8478 | 0.0000 | 0.4829 | 12.88 | 0 |
| 1080p | view_no_copy(REFERENCE) | 1 | 605 | 0.0165 | 0.016-0.018 | 0.0273 | 0.0069 | 0.0165 | 377.06 | 0 |
| 1080p | multiframe_latest | 5 | 600 | 2.3533 | 2.260-6.984 | 7.2891 | 2.1380 | 0.4707 | 13.22 | 0 |
| 1080p | multiframe_by_number | 5 | 586 | 6.6275 | 6.234-7.582 | 13.5425 | 6.7033 | 1.3255 | 4.69 | 0 |
| 1080p | multiframe_views(REFERENCE) | 5 | 605 | 0.0518 | 0.051-0.052 | 0.0625 | 0.0455 | 0.0104 | 600.52 | 0 |

Notes: 'view' rows only build numpy views (no bytes moved) - the GB/s figure is not a copy rate.
multiframe_* rows read 5 cameras per call; per-camera column divides by 5.
