# P12 - sustained writes to the physical disk (C:, the recording volume)

Volume 4000 GB, 224.9 GB free at start (94.38% used). Time to fill the free space: 54.3 min at 69 MB/s (HEAD MSMF, 5x1080p), 23.1 min at 162 MB/s (MJPEG passthrough, 5x1080p).

| phase | mode | target MB/s | achieved MB/s | GB written | write() median / p99 / p99.9 / max ms (worst stream) | writes > 100 ms / > 1 s | worst lag behind 60 Hz schedule ms | writes finishing > 16.7 ms late | flush at stop s | min per-GiB MB/s (A) |
|---|---|---|---|---|---|---|---|---|---|---|
| A | unbuffered+write-through, 4 MiB sequential | max | 1889 | 68.7 | 0.71 / 10.64 / 45.27 / 97.1 | 0 / 0 | - | - | - | 481 |
| B1 | unbuffered+write-through | 162 | 162 | 48.7 | 0.42 / 2.31 / 15.77 / 134.8 | 5 / 0 | 135.2 | 227 | - | - |
| B2 | unbuffered+write-through | 69 | 70 | 42.0 | 0.13 / 0.53 / 0.87 / 137.8 | 20 / 0 | 138.2 | 136 | - | - |
| C | buffered (OS cache), FlushFileBuffers at stop | 162 | 161 | 9.7 | 0.31 / 1.08 / 2.03 / 3.4 | 0 / 0 | 3.4 | 0 | 0.47895579999749316 | - |
