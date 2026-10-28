# (b) ring-buffer read styles (5 cameras written at 60 fps by 5 spawned writer processes)
cold = first read after the writer published the slot; warm = immediate re-read of the same slot

| size | style | cams per read | n | cold median ms | range of 5 round medians ms | cold p99 ms | warm median ms | per-camera cold median ms | cold GB/s | frame_number mismatches |
|---|---|---|---|---|---|---|---|---|---|---|
| 720p | latest_reused | 1 | 606 | 0.2965 | 0.218-0.829 | 1.3521 | 0.1679 | 0.2965 | 9.33 | 0 |
| 720p | latest_alloc | 1 | 598 | 0.6035 | 0.569-1.263 | 2.4922 | 0.5402 | 0.6035 | 4.58 | 0 |
| 720p | by_index_reused | 1 | 605 | 0.4216 | 0.228-1.064 | 1.5128 | 0.2157 | 0.4216 | 6.56 | 0 |
| 720p | next_consuming | 1 | 604 | 0.6978 | 0.286-0.953 | 1.3562 | 0.0000 | 0.6978 | 3.96 | 0 |
| 720p | view_no_copy(REFERENCE) | 1 | 605 | 0.0237 | 0.022-0.027 | 0.0575 | 0.0072 | 0.0237 | 116.68 | 0 |
| 720p | multiframe_latest | 5 | 605 | 1.5126 | 1.144-3.512 | 4.9319 | 1.0762 | 0.3025 | 9.14 | 0 |
| 720p | multiframe_by_number | 5 | 601 | 4.0650 | 2.989-5.150 | 5.9110 | 3.0664 | 0.8130 | 3.4 | 0 |
| 720p | multiframe_views(REFERENCE) | 5 | 605 | 0.0667 | 0.060-0.106 | 0.2372 | 0.0497 | 0.0133 | 207.3 | 0 |
| 1080p | latest_reused | 1 | 602 | 0.5343 | 0.471-1.960 | 2.5585 | 0.3933 | 0.5343 | 11.64 | 0 |
| 1080p | latest_alloc | 1 | 600 | 1.2105 | 1.154-1.671 | 3.3070 | 1.1484 | 1.2105 | 5.14 | 0 |
| 1080p | by_index_reused | 1 | 605 | 0.4979 | 0.472-0.897 | 1.6125 | 0.3883 | 0.4979 | 12.5 | 0 |
| 1080p | next_consuming | 1 | 604 | 0.5586 | 0.515-2.037 | 2.8095 | 0.0000 | 0.5586 | 11.14 | 0 |
| 1080p | view_no_copy(REFERENCE) | 1 | 605 | 0.0317 | 0.030-0.037 | 0.0721 | 0.0080 | 0.0317 | 196.26 | 0 |
| 1080p | multiframe_latest | 5 | 600 | 2.4154 | 2.228-8.473 | 11.3414 | 2.3422 | 0.4831 | 12.88 | 0 |
| 1080p | multiframe_by_number | 5 | 576 | 6.1469 | 5.760-8.002 | 15.3647 | 6.6845 | 1.2294 | 5.06 | 0 |
| 1080p | multiframe_views(REFERENCE) | 5 | 605 | 0.0625 | 0.058-0.071 | 0.1570 | 0.0481 | 0.0125 | 497.71 | 0 |

Notes: 'view' rows only build numpy views (no bytes moved) - the GB/s figure is not a copy rate.
multiframe_* rows read 5 cameras per call; per-camera column divides by 5.
