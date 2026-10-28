# (e) end-to-end: real SkellyCam CameraGroup stack, 5 synthetic 60 fps cameras, 30 s recording

Per-camera values: median across the 5 cameras of each camera's median, or worst camera for p99/max.

| file | size | retrieve stand-in | UI relay | achieved fps (min cam) | recorded frames / sensor frames (cam0) | sensor frames never grabbed (sum 5 cams) | frames in files == recorded | grab interval median / p99 / max ms | retrieve median ms | put_frame median / p99 ms | record_frame median / p99 ms | sensor tick -> written median / p99 / max ms | cross-cam grab spread p99 ms | UI payloads/s | UI build median / p99 ms | CPU% children / main / system | system CPU% before run |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| e_e2e_1080p_memcpy_ui.json | 1080p | memcpy | True | 59.99 | 1801 / 1801 | 0 | True | 16.74 / 18.39 / 39.6 | 0.67 | 2.14 / 4.07 | 0.70 / 1.52 | 4.1 / 7.6 / 18.0 | 0.76 | 39.9 | 12.7 / 20.1 | 994 / 115 / 48 | 2 |
| e_e2e_1080p_memcpy_ui_rep2.json | 1080p | memcpy | True | 59.99 | 1802 / 1802 | 0 | True | 16.70 / 19.06 / 36.5 | 0.73 | 1.96 / 3.93 | 0.68 / 1.27 | 4.0 / 11.7 / 19.9 | 0.68 | 40.8 | 12.4 / 19.9 | 928 / 117 / 46 | 5 |
| e_e2e_1080p_memcpy_ui_repro.json | 1080p | memcpy | True | 59.97 | 1802 / 1803 | 3 | True | 16.69 / 18.44 / 45.1 | 0.54 | 2.19 / 4.05 | 0.71 / 1.32 | 3.9 / 14.5 / 23.4 | 0.71 | 40.9 | 12.4 / 19.3 | 1037 / 116 / 48 | 5 |
| e_e2e_1080p_mjpeg_noui.json | 1080p | mjpeg | False | 55.94 | 1680 / 1801 | 605 | True | 17.90 / 20.90 / 34.7 | 9.91 | 3.49 / 5.36 | 1.14 / 2.55 | 23.6 / 33.5 / 36.5 | 2.61 | 0.0 | 0.0 / 0.0 | 1392 / 1 / 61 | 4 |
| e_e2e_1080p_mjpeg_ui.json | 1080p | mjpeg | True | 53.56 | 1609 / 1801 | 964 | True | 18.69 / 22.23 / 42.8 | 10.12 | 3.64 / 5.76 | 1.12 / 2.63 | 23.9 / 34.4 / 37.4 | 2.74 | 36.9 | 15.2 / 22.3 | 1345 / 131 / 64 | 3 |
| e_e2e_1080p_mjpeg_ui_rep2.json | 1080p | mjpeg | True | 53.57 | 1610 / 1803 | 964 | True | 18.69 / 21.90 / 38.2 | 10.31 | 3.73 / 5.90 | 1.19 / 2.66 | 24.4 / 34.5 / 36.9 | 2.66 | 36.6 | 15.3 / 23.7 | 1361 / 134 / 65 | 5 |
| e_e2e_1080p_mjpeg_ui_repro.json | 1080p | mjpeg | True | 53.92 | 1620 / 1802 | 911 | True | 18.53 / 22.52 / 34.4 | 10.25 | 3.71 / 5.99 | 1.11 / 2.54 | 23.9 / 35.1 / 37.6 | 2.30 | 36.7 | 15.3 / 25.2 | 1311 / 128 / 62 | 6 |
| e_e2e_1080p_mjpeg_ui_repro_rep2.json | 1080p | mjpeg | True | 53.97 | 1622 / 1802 | 902 | True | 18.43 / 22.53 / 51.4 | 10.14 | 3.63 / 5.82 | 1.11 / 2.52 | 23.5 / 34.8 / 37.4 | 3.23 | 37.1 | 15.1 / 22.6 | 1324 / 130 / 63 | 4 |
| e_e2e_720p_memcpy_ui.json | 720p | memcpy | True | 60.00 | 1802 / 1802 | 0 | True | 16.66 / 17.67 / 41.4 | 0.23 | 0.91 / 2.56 | 0.46 / 0.82 | 2.1 / 4.2 / 14.7 | 0.72 | 57.5 | 5.7 / 9.7 | 417 / 48 / 22 | 5 |
| e_e2e_720p_memcpy_ui_rep2.json | 720p | memcpy | True | 60.00 | 1802 / 1802 | 0 | True | 16.67 / 17.51 / 32.0 | 0.20 | 0.79 / 1.57 | 0.43 / 0.71 | 1.9 / 3.2 / 6.2 | 0.92 | 58.9 | 5.0 / 8.3 | 346 / 60 / 20 | 5 |
| e_e2e_720p_mjpeg_ui.json | 720p | mjpeg | True | 60.00 | 1802 / 1802 | 0 | True | 16.68 / 18.03 / 30.5 | 3.50 | 0.93 / 1.79 | 0.46 / 0.85 | 5.5 / 7.7 / 10.9 | 0.62 | 57.0 | 5.8 / 9.4 | 478 / 55 / 25 | 4 |
| e_e2e_720p_mjpeg_ui_repro.json | 720p | mjpeg | True | 60.00 | 1803 / 1803 | 0 | True | 16.66 / 18.40 / 34.2 | 3.61 | 0.85 / 2.02 | 0.46 / 0.95 | 5.5 / 7.6 / 15.7 | 0.78 | 57.5 | 5.6 / 9.0 | 518 / 53 / 26 | 4 |

stop_recording/start_recording call durations, finalizer stats, per-camera CPU and capture logs are in each JSON.
