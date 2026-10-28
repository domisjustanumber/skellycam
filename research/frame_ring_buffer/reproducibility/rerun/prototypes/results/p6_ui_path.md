# P6 - UI tap server-side build (5 cameras, 60 fps writers, relay-shaped 10 ms loop, instant ack, no browser)

10.0s per variant. `event-loop blocked` = build time minus time spent awaiting the thread pool (the loop also serves HTTP recording start/stop). CPU = main process only.

| size | variant | venv | payloads/s | distinct/s | build median / p99 ms | event-loop blocked per payload median / p99 / max ms | payload KB | seqlock invalid | main CPU % | copies |
|---|---|---|---|---|---|---|---|---|---|---|
| 1080p | cur_copy_real | skellycamvenv | 51.6 | 51.6 | 8.32 / 9.73 | 8.32 / 9.73 / 13.18 | 337 | 0 | 90 | 5 full frames out of shm + 5 resize outputs (alloc) + JPEG x3 (tobytes, assemble, slice) |
| 1080p | view_real | skellycamvenv | 57.7 | 57.6 | 6.38 / 7.56 | 6.38 / 7.56 / 10.59 | 337 | 0 | 89 | 0 out of shm; 5 resize outputs (alloc); JPEG x3 |
| 1080p | view_proto | skellycamvenv | 53.9 | 53.9 | 4.87 / 6.85 | 4.87 / 6.85 / 9.78 | 311 | 0 | 60 | 0 out of shm; resize into preallocated dst; JPEG x1 (assemble) |
| 1080p | view_proto_640x360 | skellycamvenv | 45.1 | 45.1 | 3.01 / 4.81 | 3.01 / 4.81 / 7.74 | 203 | 0 | 33 | same as view_proto |
| 1080p | view_proto_threads | skellycamvenv | 46.6 | 46.6 | 2.35 / 4.41 | 0.05 / 0.08 / 0.12 | 305 | 0 | 46 | same as view_proto |
| 1080p | view_proto_threads_poll2ms | skellycamvenv | 60.1 | 60.1 | 1.99 / 3.56 | 0.04 / 0.06 / 0.11 | 305 | 0 | 64 | same as view_proto |
| 1080p | jpeg_forward | skellycamvenv | 51.8 | 51.8 | 0.25 / 0.58 | 0.25 / 0.58 / 1.57 | 2720 | 0 | 1 | 0 pixel copies; camera JPEG x1 (assemble) |
| 1080p | jpeg_reduced_reencode | skellycamvenv | 27.0 | 27.0 | 26.06 / 28.64 | 26.06 / 28.64 / 30.67 | 310 | 0 | 70 | 0 full-res frames; reduced decode + encode; JPEG x1 |
| 1080p | jpeg_reduced_reencode_threads | skellycamvenv | 58.3 | 58.3 | 5.90 / 7.30 | 0.05 / 0.06 / 0.09 | 310 | 0 | 158 | same as jpeg_reduced_reencode |
| 720p | cur_copy_real | skellycamvenv | 66.3 | 60.1 | 4.17 / 5.48 | 4.17 / 5.48 / 6.52 | 132 | 0 | 50 | 5 full frames out of shm + 5 resize outputs (alloc) + JPEG x3 (tobytes, assemble, slice) |
| 720p | view_real | skellycamvenv | 69.8 | 60.0 | 3.28 / 4.62 | 3.28 / 4.62 / 6.25 | 132 | 0 | 43 | 0 out of shm; 5 resize outputs (alloc); JPEG x3 |
| 720p | view_proto | skellycamvenv | 44.3 | 44.3 | 2.43 / 5.16 | 2.43 / 5.16 / 6.34 | 141 | 0 | 25 | 0 out of shm; resize into preallocated dst; JPEG x1 (assemble) |
| 720p | view_proto_640x360 | skellycamvenv | 44.4 | 44.4 | 2.45 / 5.00 | 2.45 / 5.00 / 8.56 | 141 | 0 | 20 | same as view_proto |
| 720p | view_proto_threads | skellycamvenv | 45.4 | 45.4 | 1.36 / 12.31 | 0.04 / 0.10 / 0.13 | 141 | 0 | 37 | same as view_proto |
| 720p | view_proto_threads_poll2ms | skellycamvenv | 60.1 | 60.1 | 1.23 / 11.13 | 0.03 / 0.07 / 0.09 | 153 | 0 | 44 | same as view_proto |
| 720p | jpeg_forward | skellycamvenv | 45.6 | 45.6 | 0.13 / 0.31 | 0.13 / 0.31 / 0.64 | 1211 | 0 | 1 | 0 pixel copies; camera JPEG x1 (assemble) |
| 720p | jpeg_reduced_reencode | skellycamvenv | 43.2 | 43.2 | 12.07 / 13.20 | 12.07 / 13.20 / 15.88 | 141 | 0 | 52 | 0 full-res frames; reduced decode + encode; JPEG x1 |
| 720p | jpeg_reduced_reencode_threads | skellycamvenv | 43.9 | 43.9 | 3.11 / 5.51 | 0.03 / 0.06 / 0.10 | 141 | 0 | 50 | same as jpeg_reduced_reencode |
| 1080p | view_proto | benchvenv | 53.3 | 53.3 | 4.90 / 6.97 | 4.90 / 6.97 / 8.49 | 309 | 0 | 71 | 0 out of shm; resize into preallocated dst; JPEG x1 (assemble) |
| 1080p | view_simplejpeg | benchvenv | 56.0 | 56.0 | 6.81 / 7.88 | 6.81 / 7.88 / 11.23 | 492 | 0 | 74 | same as view_proto |
| 720p | view_proto | benchvenv | 43.9 | 43.9 | 2.39 / 4.81 | 2.39 / 4.81 / 6.59 | 141 | 0 | 22 | 0 out of shm; resize into preallocated dst; JPEG x1 (assemble) |
| 720p | view_simplejpeg | benchvenv | 45.3 | 45.3 | 3.30 / 5.59 | 3.30 / 5.59 / 6.48 | 213 | 0 | 26 | same as view_proto |

Baseline (baseline/results/d_ui.md, idle 20261027 re-run, real SkellyCam ring + get_latest_multiframe + create_frontend_payload): 1080p 46.0 payloads/s, total 9.39 ms median / 17.43 p99, main CPU 106%; 720p 60.5 payloads/s, 4.70 ms. FreeMoCap by-number path 1080p 41.7/s, 12.87 ms. No-sleep maximum: 1080p 110.3 payloads/s (60.0 distinct), 8.84 ms.
Note: jpeg_forward payload size reflects the synthetic q90 JPEGs (~540 KB at 1080p); real cameras measured ~160-167 KB/frame (research: c922 720p60, C930e 1080p30).
