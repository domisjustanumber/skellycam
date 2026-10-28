# P10 - cv2.setNumThreads vs CPU of SkellyCam's real VideoRecorder (cv2 'X264' -> MSMF), 5 spawned processes

OpenCV parallel framework: ['Parallel framework:            Concurrency']; default cv2.getNumThreads() = 28. CPU % = process CPU time / (loop + release), summed over 5 processes, 100 = one logical CPU. encode fps = frames / (loop + release) (slowest camera).

| size | cv2 threads | mode | CPU % sum (5 cams) | CPU ms/frame | min fps written | encode fps (slowest) | record_frame median / worst p99 ms | writes late > 16.7 ms | files decode == written | Mbit/s per cam | release s (max) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1080p | default | paced60 | 1187 | 39.19 | 60.0 | 59.9 | 2.16 / 4.86 | 0 | True | 124.9 | 0.06 |
| 1080p | 1 | paced60 | 359 | 11.87 | 60.0 | 59.9 | 2.42 / 4.26 | 0 | True | 124.9 | 0.06 |
| 1080p | 2 | paced60 | 563 | 18.68 | 60.0 | 59.9 | 2.28 / 3.61 | 0 | True | 124.9 | 0.06 |
| 1080p | 4 | paced60 | 619 | 20.46 | 60.0 | 59.9 | 2.23 / 3.19 | 0 | True | 124.9 | 0.06 |
| 1080p | 8 | paced60 | 750 | 25.21 | 60.0 | 59.9 | 2.07 / 2.87 | 0 | True | 124.9 | 0.06 |
| 720p | default | paced60 | 506 | 16.69 | 60.0 | 59.9 | 0.97 / 1.41 | 0 | True | 55.5 | 0.06 |
| 720p | 1 | paced60 | 227 | 7.61 | 60.0 | 59.8 | 1.17 / 1.77 | 0 | True | 55.5 | 0.07 |
| 720p | 2 | paced60 | 224 | 7.55 | 60.0 | 59.8 | 1.11 / 1.94 | 0 | True | 55.5 | 0.07 |
| 1080p | default | unthrottled | 1790 | 31.03 | 175.9 | 114.7 | 3.14 / 6.18 | 0 | True | 124.8 | 5.43 |
| 1080p | 2 | unthrottled | 1130 | 19.28 | 172.5 | 115.4 | 3.71 / 6.03 | 0 | True | 124.8 | 5.02 |

Baseline (baseline/results/c_record.md, same harness without setNumThreads): 5x1080p paced 1207% CPU, 5x720p 476%.
