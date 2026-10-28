# (e) end-to-end: real SkellyCam CameraGroup stack, 5 synthetic 60 fps cameras, 30 s recording

Per-camera values: median across the 5 cameras of each camera's median, or worst camera for p99/max.

| file | size | retrieve stand-in | UI relay | achieved fps (min cam) | recorded frames / sensor frames (cam0) | sensor frames never grabbed (sum 5 cams) | frames in files == recorded | grab interval median / p99 / max ms | retrieve median ms | put_frame median / p99 ms | record_frame median / p99 ms | sensor tick -> written median / p99 / max ms | cross-cam grab spread p99 ms | UI payloads/s | UI build median / p99 ms | CPU% children / main / system | system CPU% before run |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| e_e2e_1080p_memcpy_ui.json | 1080p | memcpy | True | 59.99 | 1803 / 1803 | 0 | True | 16.68 / 18.70 / 37.8 | 0.78 | 2.76 / 5.65 | 0.81 / 2.21 | 5.0 / 10.4 / 29.7 | 0.84 | 41.0 | 13.3 / 21.0 | 1135 / 124 / 61 | 29 |
| e_e2e_1080p_memcpy_ui_rep2.json | 1080p | memcpy | True | 59.95 | 1801 / 1802 | 5 | True | 16.65 / 19.28 / 48.5 | 0.87 | 2.33 / 4.79 | 0.73 / 2.14 | 4.9 / 14.5 / 23.3 | 1.22 | 38.3 | 14.3 / 25.1 | 1090 / 131 / 70 | 29 |
| e_e2e_1080p_mjpeg_noui.json | 1080p | mjpeg | False | 46.11 | 1385 / 1802 | 2084 | True | 21.23 / 30.51 / 49.3 | 12.11 | 4.10 / 7.32 | 1.33 / 3.78 | 27.0 / 39.8 / 45.3 | 3.58 | 0.0 | 0.0 / 0.0 | 1209 / 2 / 73 | 34 |
| e_e2e_1080p_mjpeg_ui.json | 1080p | mjpeg | True | 44.01 | 1323 / 1803 | 2398 | True | 22.24 / 31.85 / 42.7 | 12.27 | 4.23 / 7.51 | 1.34 / 4.46 | 27.3 / 39.5 / 46.7 | 4.61 | 35.7 | 16.2 / 28.6 | 1184 / 132 / 76 | 64 |
| e_e2e_1080p_mjpeg_ui_rep2.json | 1080p | mjpeg | True | 46.78 | 1407 / 1803 | 1984 | True | 21.15 / 28.76 / 41.1 | 11.22 | 4.07 / 6.88 | 1.30 / 3.93 | 26.1 / 37.8 / 47.6 | 4.82 | 34.8 | 17.3 / 28.1 | 1193 / 145 / 80 | 34 |
| e_e2e_720p_memcpy_ui.json | 720p | memcpy | True | 58.76 | 1766 / 1803 | 186 | True | 16.66 / 28.51 / 130.2 | 0.27 | 1.06 / 2.25 | 0.52 / 3.72 | 2.5 / 17.3 / 63.7 | 10.77 | 55.0 | 6.3 / 12.4 | 479 / 53 / 53 | 28 |
| e_e2e_720p_memcpy_ui_rep2.json | 720p | memcpy | True | 60.00 | 1802 / 1802 | 0 | True | 16.67 / 17.91 / 33.8 | 0.26 | 0.90 / 1.79 | 0.42 / 0.60 | 2.1 / 3.6 / 9.1 | 0.84 | 60.4 | 5.7 / 9.0 | 375 / 58 / 35 | 46 |
| e_e2e_720p_mjpeg_ui.json | 720p | mjpeg | True | 59.99 | 1802 / 1802 | 0 | True | 16.69 / 20.03 / 35.6 | 4.04 | 1.41 / 3.08 | 0.55 / 1.28 | 6.7 / 12.9 / 20.0 | 1.08 | 56.1 | 6.9 / 13.1 | 593 / 62 / 57 | 35 |

stop_recording/start_recording call durations, finalizer stats, per-camera CPU and capture logs are in each JSON.
