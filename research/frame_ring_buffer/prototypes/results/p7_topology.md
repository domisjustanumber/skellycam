# P7 - topology: 5 workers as threads in one process vs 5 spawned processes (1920x1080, unthrottled)

Median of 5 repetitions per cell (ranges in the JSON). scaling = aggregate fps / single-worker fps (5.0 = perfect). CPU % = process CPU time / wall (100 = 1 logical CPU).

| workload | frames/worker | 1 worker fps | 5 threads: aggregate / slowest fps (scaling) | 5 threads CPU % | 5 processes: aggregate / slowest fps (scaling) | 5 processes CPU % |
|---|---|---|---|---|---|---|
| imdecode | 300 | 146 | 673 / 134 (x4.60) | 488 | 718 / 142 (x4.90) | 493 |
| msmf_write | 300 | 307 | 503 / 100 (x1.64) | 721 | 468 / 93 (x1.53) | 664 |
| h264_nvenc | 300 | 375 | 407 / 79 (x1.08) | 110 | 426 / 84 (x1.13) | 125 |
| mjpeg_mux | 3000 | 3949 | 8101 / 1574 (x2.05) | 346 | 7473 / 1453 (x1.89) | 312 |
| py_overhead | 20000 | 15090 | 15522 / 3015 (x1.03) | 99 | 74947 / 14881 (x4.97) | 493 |
| simplejpeg | 300 | 212 | 1062 / 212 (x5.00) | 491 | 1072 / 213 (x5.05) | 493 |
