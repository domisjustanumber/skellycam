# (c) record path: real VideoRecorder.record_frame, one spawned process per camera

| size | N | mode | min cam fps | record_frame median ms | worst p99 ms | worst max ms | max lateness ms | frames >16.7ms | sum proc CPU% (100=1 core) | system CPU% | writer | file frames == written | MB on disk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 720p | 5 | paced60 | 60.0 | 0.99 | 1.38 | 2.93 | 3.50 | 0 | 476 | 25 | X264/MSMF | True | 694.3 |
| 720p | 5 | unthrottled | 359.2 | 1.69 | 3.94 | 35.16 | nan | 7 | 2410 | 100 | X264/MSMF | True | 2078.5 |
| 720p | 1 | unthrottled | 1260.0 | 0.50 | 0.79 | 1.16 | nan | 0 | 975 | 41 | X264/MSMF | True | 1452.3 |
| 1080p | 5 | paced60 | 60.0 | 2.17 | 4.05 | 6.47 | 8.90 | 0 | 1207 | 54 | X264/MSMF | True | 1561.9 |
| 1080p | 5 | unthrottled | 175.8 | 3.28 | 6.66 | 11.82 | nan | 0 | 2507 | 100 | X264/MSMF | True | 2307.9 |
| 1080p | 1 | unthrottled | 675.8 | 0.79 | 1.27 | 1.93 | nan | 0 | 1495 | 61 | X264/MSMF | True | 1752.7 |
