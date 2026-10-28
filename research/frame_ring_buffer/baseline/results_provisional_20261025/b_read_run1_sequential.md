# (b) ring-buffer read styles (5 cameras written at 60 fps by 5 spawned writer processes)
cold = first read after the writer published the slot; warm = immediate re-read of the same slot

| size | style | cams per read | n | cold median ms | cold p99 ms | warm median ms | per-camera cold median ms | cold GB/s | frame_number mismatches |
|---|---|---|---|---|---|---|---|---|---|
| 720p | latest_reused | 1 | 481 | 0.7509 | 1.1169 | 0.1644 | 0.7509 | 3.68 | 0 |
| 720p | latest_alloc | 1 | 481 | 0.5653 | 1.0281 | 0.5365 | 0.5653 | 4.89 | 0 |
| 720p | by_index_reused | 1 | 481 | 0.2077 | 0.4514 | 0.1553 | 0.2077 | 13.31 | 0 |
| 720p | next_consuming | 1 | 481 | 0.8009 | 0.9718 | 0.0000 | 0.8009 | 3.45 | 0 |
| 720p | view_no_copy(REFERENCE) | 1 | 481 | 0.0206 | 0.0345 | 0.0069 | 0.0206 | 134.24 | 0 |
| 720p | multiframe_latest | 5 | 480 | 3.3125 | 4.5691 | 1.0873 | 0.6625 | 4.17 | 0 |
| 720p | multiframe_by_number | 5 | 480 | 2.7758 | 4.0437 | 2.7831 | 0.5552 | 4.98 | 0 |
| 720p | multiframe_views(REFERENCE) | 5 | 481 | 0.0575 | 0.1295 | 0.0472 | 0.0115 | 240.47 | 0 |
| 1080p | latest_reused | 1 | 481 | 0.7840 | 2.2834 | 0.4559 | 0.7840 | 7.94 | 0 |
| 1080p | latest_alloc | 1 | 480 | 1.2862 | 2.0015 | 1.2124 | 1.2862 | 4.84 | 0 |
| 1080p | by_index_reused | 1 | 481 | 0.4822 | 1.2839 | 0.4946 | 0.4822 | 12.9 | 0 |
| 1080p | next_consuming | 1 | 481 | 0.5335 | 2.9056 | 0.0000 | 0.5335 | 11.66 | 0 |
| 1080p | view_no_copy(REFERENCE) | 1 | 481 | 0.0223 | 0.0498 | 0.0067 | 0.0223 | 278.99 | 0 |
| 1080p | multiframe_latest | 5 | 481 | 2.5492 | 9.7203 | 2.3001 | 0.5098 | 12.2 | 0 |
| 1080p | multiframe_by_number | 5 | 480 | 5.9221 | 8.5636 | 6.3821 | 1.1844 | 5.25 | 0 |
| 1080p | multiframe_views(REFERENCE) | 5 | 481 | 0.0936 | 0.2812 | 0.0706 | 0.0187 | 332.34 | 0 |

Notes: 'view' rows only build numpy views (no bytes moved) - the GB/s figure is not a copy rate.
multiframe_* rows read 5 cameras per call; per-camera column divides by 5.
