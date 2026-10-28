# P5 - NVENC (PyAV h264_nvenc / hevc_nvenc) vs cv2 'X264' (MSMF) as the decoupled recorder, fed from shm

## Session limit (one process, concurrent open encoders, 1280x720)

| codec | max concurrent sessions opened (probe limit) | first error | nvidia-smi sessionCount while open |
|---|---|---|---|
| h264_nvenc | 12 (20) | session 13: ExternalError(542398533, 'Generic error in an external library', 'avcodec_open2("h264_nvenc", {\'preset\': \'p4\', \'tune\': \'ll\', \'rc\': \'vbr\', \'cq\': \'23\'})') | 12 |
| hevc_nvenc | 12 (20) | session 13: ExternalError(542398533, 'Generic error in an external library', 'avcodec_open2("hevc_nvenc", {\'preset\': \'p4\', \'tune\': \'ll\', \'rc\': \'vbr\', \'cq\': \'25\'})') | 12 |

## 5 cameras x 60 fps (paced, 20.0s) and unthrottled (900 frames/camera); memcpy-into-slot cameras

CPU % = psutil mean per process (100 = 1 logical CPU). Recorder fps = recorded / (loop + release).

| size | encoder | paced | per-cam fps (min) | sensor frames never grabbed | files decode == produced | Mbit/s per cam | CPU % cameras / recorders | recorder CPU ms/frame | encode call median / p99 ms (worst cam) | BGR->I420 median ms | tick->written median / p99 ms | recorder fps sum / slowest | release s (max) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1080p | msmf | True | 60.0 | 0 | True | 124.9 | 51 / 283 | 9.99 | 1.47 / 3.08 | 0.00 | 2.6 / 5.6 | 299 / 60 | 0.07 |
| 1080p | msmf | False | 198.8 | 0 | True | 124.9 | 163 / 1315 | 22.17 | 5.50 / 9.58 | 0.00 | 866.0 / 1059.5 | 578 / 115 | 2.58 |
| 1080p | h264_nvenc | True | 60.0 | 0 | True | 29.7 | 62 / 105 | 3.64 | 2.80 / 17.06 | 0.57 | 3.8 / 189.0 | 300 / 60 | 0.01 |
| 1080p | h264_nvenc | False | 107.2 | 0 | True | 29.7 | 23 / 134 | 3.21 | 3.93 / 51.58 | 0.46 | 1852.5 / 2005.2 | 447 / 89 | 0.02 |
| 1080p | hevc_nvenc | True | 60.0 | 0 | True | 16.2 | 57 / 80 | 2.82 | 3.87 / 32.74 | 0.42 | 693.2 / 1116.6 | 285 / 57 | 0.04 |
| 1080p | hevc_nvenc | False | 69.6 | 0 | True | 16.3 | 15 / 86 | 3.23 | 7.05 / 32.49 | 0.43 | 3000.0 / 3039.9 | 283 / 56 | 0.03 |
| 1080p | pyav_libx264 | True | 56.4 | 319 | True | 8.4 | 44 / 2442 | 103.47 | 18.71 / 39.80 | 0.00 | 2202.3 / 3708.5 | 236 / 47 | 0.45 |
| 1080p | pyav_libx264 | False | 57.5 | 0 | True | 9.4 | 29 / 2443 | 105.90 | 19.08 / 40.68 | 0.00 | 3686.2 / 3831.1 | 230 / 46 | 0.42 |
| 720p | msmf | True | 60.0 | 0 | True | 55.5 | 50 / 127 | 4.25 | 0.65 / 1.14 | 0.00 | 1.4 / 2.4 | 299 / 60 | 0.07 |
| 720p | msmf | False | 532.1 | 0 | True | 55.6 | 0 / 1373 | 10.19 | 2.69 / 4.79 | 0.00 | 602.7 / 883.3 | 1219 / 243 | 1.23 |
| 720p | h264_nvenc | True | 60.0 | 0 | True | 13.3 | 53 / 59 | 2.03 | 1.22 / 2.11 | 0.25 | 1.8 / 103.4 | 300 / 60 | 0.01 |
| 720p | h264_nvenc | False | 306.0 | 0 | True | 13.3 | 8 / 145 | 1.67 | 1.81 / 36.05 | 0.24 | 1949.0 / 2066.1 | 947 / 187 | 0.01 |
| 720p | hevc_nvenc | True | 60.0 | 0 | True | 9.4 | 43 / 54 | 1.96 | 1.22 / 3.60 | 0.25 | 1.8 / 113.5 | 300 / 60 | 0.01 |
| 720p | hevc_nvenc | False | 195.6 | 0 | True | 9.4 | 12 / 91 | 1.72 | 3.29 / 29.92 | 0.23 | 3218.5 / 3291.6 | 581 / 115 | 0.01 |
| 720p | pyav_libx264 | True | 60.0 | 0 | True | 4.2 | 54 / 1273 | 42.56 | 7.17 / 15.30 | 0.00 | 8.1 / 17.8 | 297 / 59 | 0.20 |
| 720p | pyav_libx264 | False | 180.5 | 0 | True | 4.2 | 23 / 2308 | 44.76 | 8.36 / 18.89 | 0.00 | 3637.9 / 3815.5 | 512 / 102 | 0.18 |

Baseline (baseline/results/c_record.md, idle 20261027 re-run): VideoRecorder (MSMF), 5x1080p paced 60: 1207% summed CPU, record_frame median / p99 2.17 / 4.05 ms; 5x720p 476%; derived unthrottled encode throughput about 117 fps/camera at 1080p, 237 at 720p.
