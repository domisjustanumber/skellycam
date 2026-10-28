# P4 - MJPEG passthrough recording vs decode + MSMF H.264 re-encode (5 cameras, decoupled gated recorders)

Paced rows: 60 fps FakeSensor, 3.0s. Unthrottled rows: 1500 frames per camera (or 5 s), camera publishes as fast as the gated recorder consumes. CPU %: psutil mean per process over the run, 100 = one logical CPU; ms/frame from process_time.

| size | mode | per-cam fps (min) | sensor frames never grabbed | files decode == produced | disk MB/s (5 cams) | CPU % cameras / recorders (sum) | camera CPU ms/frame | recorder CPU ms/frame | tick->written median / p99 ms (worst cam) | recorder release s | full-frame copies | unthrottled recorder fps (sum over cams, recorded/(loop+release)) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1080p | passthrough | 60.05 | 0 | True | 162.1 | 34 / 39 | 1.036 | 1.036 | 1.0 / 4.1 | 0.00 | 0 (2 compressed copies) |  |
| 1080p | decode_msmf | 58.78 | 6 | True | 78.5 | 395 / 1070 | 12.744 | 37.326 | 17.8 / 35.8 | 0.10 | 1 after decode (+ encoder-internal, unknown) |  |
| 1080p | passthrough_unthrottled | 4248.12 | 0 | True | 4352.6 | nan / nan | 0.229 | 0.510 | 291.8 / 500.6 | 0.11 | 0 (2 compressed copies) | 8272 |
| 720p | passthrough | 60.05 | 0 | True | 72.2 | 37 / 16 | 1.036 | 0.518 | 0.7 / 5.7 | 0.00 | 0 (2 compressed copies) |  |
| 720p | decode_msmf | 59.93 | 0 | True | 35.0 | 185 / 420 | 6.215 | 13.208 | 5.9 / 10.6 | 0.09 | 1 after decode (+ encoder-internal, unknown) |  |
| 720p | passthrough_unthrottled | 9814.79 | 0 | True | 5471.3 | nan / nan | 0.094 | 0.188 | 102.8 / 175.5 | 0.00 | 0 (2 compressed copies) | 24208 |

Baseline (baseline/results/c_record.md): real VideoRecorder in the camera loop, 5x1080p paced 60: summed process CPU 1169%; 5x720p: 380%. Unthrottled cv2 X264->MSMF throughput (derived) about 116 fps/camera at 5x1080p.
