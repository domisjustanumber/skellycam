# (e) end-to-end: real SkellyCam CameraGroup stack, 5 synthetic 60 fps cameras, 30 s recording

Per-camera values: median across the 5 cameras of each camera's median, or worst camera for p99/max.

| file | size | retrieve stand-in | UI relay | achieved fps (min cam) | recorded frames / sensor frames (cam0) | sensor frames never grabbed (sum 5 cams) | frames in files == recorded | grab interval median / p99 / max ms | retrieve median ms | put_frame median / p99 ms | record_frame median / p99 ms | sensor tick -> written median / p99 / max ms | cross-cam grab spread p99 ms | UI payloads/s | UI build median / p99 ms | CPU% children / main / system | system CPU% before run |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| e2ev_cvthreads1_1080p_mjpeg_ui.json | 1080p | mjpeg | True | 54.74 | 1646 / 1804 | 788 | True | 17.57 / 24.37 / 34.6 | 8.88 | 2.97 / 5.16 | 2.75 / 4.89 | 22.5 / 35.7 / 40.6 | 1.29 | 37.8 | 14.2 / 22.4 | 713 / 129 / 38 | 9 |
| e2ev_dshowlike_1080p_mjpeg_ui_v2.json | 1080p | mjpeg | True | 54.17 | 1627 / 1802 | 874 | True | 18.44 / 22.26 / 34.4 | 10.19 | 3.69 / 5.95 | 1.14 / 2.56 | 23.8 / 34.5 / 37.2 | 2.82 | 36.9 | 15.1 / 23.5 | 1331 / 125 / 62 | 5 |
| e2ev_extracpu3_1080p_mjpeg_ui.json | 1080p | mjpeg | True | 48.46 | 1456 / 1802 | 1732 | True | 20.39 / 24.83 / 41.1 | 12.88 | 3.35 / 5.77 | 1.08 / 2.60 | 26.5 / 36.9 / 39.7 | 2.37 | 39.2 | 13.5 / 22.5 | 1230 / 121 / 59 | 4 |
| e2ev_head_1080p_mjpeg_noui_rep2.json | 1080p | mjpeg | False | 55.62 | 1670 / 1801 | 655 | True | 17.82 / 21.58 / 41.3 | 10.00 | 3.41 / 5.57 | 1.10 / 2.41 | 22.1 / 34.7 / 37.2 | 2.22 | 0.0 | 0.0 / 0.0 | 1399 / 1 / 61 | 4 |
| e2ev_head_1080p_mjpeg_ui.json | 1080p | mjpeg | True | 54.14 | 1628 / 1804 | 878 | True | 18.34 / 22.57 / 54.4 | 10.16 | 3.61 / 5.87 | 1.14 / 2.64 | 24.1 / 35.1 / 37.6 | 2.54 | 36.7 | 15.2 / 23.2 | 1338 / 130 / 63 | 5 |
| e2ev_nocopycopy+cvthreads1_1080p_mjpeg_ui.json | 1080p | mjpeg | True | 58.29 | 1750 / 1801 | 254 | True | 16.95 / 21.46 / 48.7 | 8.58 | 1.13 / 2.27 | 2.72 / 4.74 | 18.0 / 32.8 / 36.8 | 1.25 | 39.5 | 13.1 / 22.7 | 686 / 125 / 36 | 3 |
| e2ev_nocopycopy_1080p_mjpeg_ui.json | 1080p | mjpeg | True | 58.84 | 1767 / 1801 | 170 | True | 16.90 / 20.44 / 34.8 | 9.72 | 1.29 / 3.14 | 1.02 / 2.49 | 16.7 / 31.9 / 35.2 | 2.32 | 37.4 | 14.9 / 22.7 | 1392 / 121 / 64 | 5 |
| e2ev_nocopycopy_1080p_mjpeg_ui_rep2.json | 1080p | mjpeg | True | 58.98 | 1771 / 1801 | 150 | True | 16.88 / 19.78 / 52.5 | 9.99 | 1.38 / 3.32 | 1.06 / 2.68 | 17.4 / 31.8 / 35.3 | 1.98 | 37.4 | 14.6 / 23.2 | 1351 / 124 / 63 | 6 |

stop_recording/start_recording call durations, finalizer stats, per-camera CPU and capture logs are in each JSON.
