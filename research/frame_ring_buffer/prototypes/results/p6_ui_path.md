# P6 - UI tap server-side build (5 cameras, 60 fps writers, relay-shaped 10 ms loop, instant ack, no browser)

10.0s per variant. `event-loop blocked` = build time minus time spent awaiting the thread pool (the loop also serves HTTP recording start/stop). CPU = main process only.

| size | variant | venv | payloads/s | distinct/s | build median / p99 ms | event-loop blocked per payload median / p99 / max ms | payload KB | seqlock invalid | main CPU % | copies |
|---|---|---|---|---|---|---|---|---|---|---|
| 1080p | cur_copy_real | skellycamvenv | 51.8 | 51.8 | 8.28 / 10.11 | 8.28 / 10.11 / 13.59 | 290 | 0 | 89 | 5 full frames out of shm + 5 resize outputs (alloc) + JPEG x3 (tobytes, assemble, slice) |
| 1080p | view_real | skellycamvenv | 57.8 | 56.8 | 6.31 / 7.38 | 6.31 / 7.38 / 8.73 | 290 | 0 | 76 | 0 out of shm; 5 resize outputs (alloc); JPEG x3 |
| 1080p | view_proto | skellycamvenv | 53.0 | 53.0 | 4.84 / 7.20 | 4.84 / 7.20 / 9.77 | 304 | 0 | 59 | 0 out of shm; resize into preallocated dst; JPEG x1 (assemble) |
| 1080p | view_proto_640x360 | skellycamvenv | 43.7 | 43.7 | 2.93 / 4.55 | 2.93 / 4.55 / 6.79 | 203 | 0 | 31 | same as view_proto |
| 1080p | view_proto_threads | skellycamvenv | 46.4 | 46.4 | 2.20 / 3.94 | 0.05 / 0.08 / 0.10 | 309 | 0 | 50 | same as view_proto |
| 1080p | view_proto_threads_poll2ms | skellycamvenv | 60.1 | 60.1 | 1.96 / 3.03 | 0.04 / 0.07 / 0.14 | 309 | 0 | 58 | same as view_proto |
| 1080p | jpeg_forward | skellycamvenv | 51.0 | 51.0 | 0.25 / 0.56 | 0.25 / 0.56 / 0.65 | 2685 | 0 | 2 | 0 pixel copies; camera JPEG x1 (assemble) |
| 1080p | jpeg_reduced_reencode | skellycamvenv | 26.7 | 26.7 | 26.46 / 28.70 | 26.46 / 28.70 / 32.82 | 304 | 0 | 69 | 0 full-res frames; reduced decode + encode; JPEG x1 |
| 1080p | jpeg_reduced_reencode_threads | skellycamvenv | 58.4 | 58.4 | 5.91 / 7.23 | 0.04 / 0.08 / 0.11 | 309 | 0 | 159 | same as jpeg_reduced_reencode |
| 720p | cur_copy_real | skellycamvenv | 65.0 | 59.6 | 4.29 / 6.89 | 4.29 / 6.89 / 10.67 | 153 | 0 | 39 | 5 full frames out of shm + 5 resize outputs (alloc) + JPEG x3 (tobytes, assemble, slice) |
| 720p | view_real | skellycamvenv | 68.1 | 59.7 | 3.37 / 6.53 | 3.37 / 6.53 / 8.13 | 132 | 0 | 48 | 0 out of shm; 5 resize outputs (alloc); JPEG x3 |
| 720p | view_proto | skellycamvenv | 60.0 | 60.0 | 2.45 / 5.08 | 2.45 / 5.08 / 5.95 | 141 | 0 | 33 | 0 out of shm; resize into preallocated dst; JPEG x1 (assemble) |
| 720p | view_proto_640x360 | skellycamvenv | 60.0 | 60.0 | 2.44 / 5.11 | 2.44 / 5.11 / 5.99 | 141 | 0 | 34 | same as view_proto |
| 720p | view_proto_threads | skellycamvenv | 59.7 | 59.7 | 1.42 / 4.50 | 0.04 / 0.10 / 0.14 | 141 | 0 | 45 | same as view_proto |
| 720p | view_proto_threads_poll2ms | skellycamvenv | 60.1 | 60.1 | 1.32 / 3.04 | 0.03 / 0.09 / 0.15 | 141 | 0 | 52 | same as view_proto |
| 720p | jpeg_forward | skellycamvenv | 60.1 | 60.1 | 0.13 / 0.32 | 0.13 / 0.32 / 0.60 | 1195 | 0 | 2 | 0 pixel copies; camera JPEG x1 (assemble) |
| 720p | jpeg_reduced_reencode | skellycamvenv | 43.5 | 43.5 | 11.99 / 13.26 | 11.99 / 13.26 / 15.89 | 141 | 0 | 53 | 0 full-res frames; reduced decode + encode; JPEG x1 |
| 720p | jpeg_reduced_reencode_threads | skellycamvenv | 59.4 | 59.4 | 3.03 / 13.22 | 0.03 / 0.06 / 0.16 | 141 | 0 | 79 | same as jpeg_reduced_reencode |
| 1080p | view_proto | benchvenv | 57.8 | 57.8 | 4.99 / 7.19 | 4.99 / 7.19 / 8.66 | 306 | 0 | 75 | 0 out of shm; resize into preallocated dst; JPEG x1 (assemble) |
| 1080p | view_simplejpeg | benchvenv | 56.1 | 56.1 | 6.80 / 8.07 | 6.80 / 8.07 / 11.62 | 492 | 0 | 71 | same as view_proto |
| 720p | view_proto | benchvenv | 42.6 | 42.6 | 2.40 / 4.39 | 2.40 / 4.39 / 4.73 | 141 | 0 | 23 | 0 out of shm; resize into preallocated dst; JPEG x1 (assemble) |
| 720p | view_simplejpeg | benchvenv | 44.5 | 44.5 | 3.33 / 5.78 | 3.33 / 5.78 / 6.42 | 213 | 0 | 26 | same as view_proto |

Baseline (baseline/results/d_ui.md, idle 20261027 re-run, real SkellyCam ring + get_latest_multiframe + create_frontend_payload): 1080p 46.0 payloads/s, total 9.39 ms median / 17.43 p99, main CPU 106%; 720p 60.5 payloads/s, 4.70 ms. FreeMoCap by-number path 1080p 41.7/s, 12.87 ms. No-sleep maximum: 1080p 110.3 payloads/s (60.0 distinct), 8.84 ms.
Note: jpeg_forward payload size reflects the synthetic q90 JPEGs (~540 KB at 1080p); real cameras measured ~160-167 KB/frame (research: c922 720p60, C930e 1080p30).
