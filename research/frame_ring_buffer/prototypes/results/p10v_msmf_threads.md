# P10 - cv2.setNumThreads vs CPU of SkellyCam's real VideoRecorder (cv2 'X264' -> MSMF), 5 spawned processes

OpenCV parallel framework: ['Parallel framework:            Concurrency']; default cv2.getNumThreads() = 28. CPU % = process CPU time / (loop + release), summed over 5 processes, 100 = one logical CPU. encode fps = frames / (loop + release) (slowest camera).

| size | cv2 threads | mode | CPU % sum (5 cams) | CPU ms/frame | min fps written | encode fps (slowest) | record_frame median / worst p99 ms | writes late > 16.7 ms | files decode == written | Mbit/s per cam | release s (max) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1080p | default | unthrottled | 1826 | 31.30 | 172.4 | 115.8 | 3.22 / 6.30 | 0 | True | 124.8 | 4.92 |
| 1080p | 1 | unthrottled | 896 | 15.61 | 171.8 | 116.1 | 4.09 / 7.41 | 0 | True | 124.8 | 4.85 |
| 1080p | 2 | unthrottled | 1045 | 17.99 | 176.6 | 115.0 | 3.58 / 6.28 | 0 | True | 124.8 | 5.40 |
| 1080p | default | paced60_load | 1185 | 39.88 | 60.0 | 59.8 | 1.88 / 3.35 | 0 | True | 124.9 | 0.09 |
| 1080p | 1 | paced60_load | 481 | 15.72 | 60.0 | 59.8 | 2.67 / 5.23 | 0 | True | 124.9 | 0.07 |
| 1080p | 2 | paced60_load | 501 | 16.61 | 60.0 | 59.8 | 2.53 / 4.47 | 0 | True | 124.9 | 0.07 |

Baseline (baseline/results/c_record.md, same harness without setNumThreads): 5x1080p paced 1207% CPU, 5x720p 476%.
