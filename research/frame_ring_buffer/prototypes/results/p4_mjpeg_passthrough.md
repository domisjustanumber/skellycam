# P4 - MJPEG passthrough recording vs decode + MSMF H.264 re-encode (5 cameras, decoupled gated recorders)

Paced rows: 60 fps FakeSensor, 20.0s. Unthrottled rows: 1500 frames per camera (or 5 s), camera publishes as fast as the gated recorder consumes. CPU %: psutil mean per process over the run, 100 = one logical CPU; ms/frame from process_time.

| size | mode | per-cam fps (min) | sensor frames never grabbed | files decode == produced | disk MB/s (5 cams) | CPU % cameras / recorders (sum) | camera CPU ms/frame | recorder CPU ms/frame | tick->written median / p99 ms (worst cam) | recorder release s | full-frame copies | unthrottled recorder fps (sum over cams, recorded/(loop+release)) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1080p | passthrough | 60.01 | 0 | True | 162.1 | 35 / 28 | 1.106 | 0.950 | 0.8 / 1.8 | 0.00 | 0 (2 compressed copies) |  |
| 1080p | decode_msmf | 59.98 | 0 | True | 77.9 | 302 / 939 | 10.156 | 32.096 | 10.8 / 15.0 | 0.07 | 1 after decode (+ encoder-internal, unknown) |  |
| 1080p | passthrough_unthrottled | 3890.66 | 0 | True | 5166.3 | nan / nan | 0.240 | 0.510 | 314.3 / 426.0 | 0.01 | 0 (2 compressed copies) | 9740 |
| 720p | passthrough | 60.01 | 0 | True | 72.2 | 45 / 16 | 1.743 | 0.533 | 0.5 / 1.4 | 0.00 | 0 (2 compressed copies) |  |
| 720p | decode_msmf | 60.00 | 0 | True | 34.6 | 149 / 292 | 4.983 | 9.818 | 4.2 / 6.1 | 0.07 | 1 after decode (+ encoder-internal, unknown) |  |
| 720p | passthrough_unthrottled | 11797.31 | 0 | True | 6603.2 | nan / nan | 0.083 | 0.177 | 84.6 / 164.2 | 0.00 | 0 (2 compressed copies) | 28008 |

Baseline (baseline/results/c_record.md, idle 20261027 re-run): real VideoRecorder, 5x1080p paced 60: summed process CPU 1207%; 5x720p: 476%. Unthrottled cv2 X264->MSMF throughput (derived, c_record.json) about 117 fps/camera at 5x1080p.
