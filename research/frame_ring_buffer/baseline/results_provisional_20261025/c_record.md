# (c) record path: real VideoRecorder.record_frame, one spawned process per camera

| size | N | mode | min cam fps | record_frame median ms | worst p99 ms | worst max ms | max lateness ms | frames >16.7ms | sum proc CPU% (100=1 core) | system CPU% | writer | file frames == written | MB on disk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 720p | 5 | paced60 | 60.0 | 0.97 | 2.36 | 4.22 | 5.97 | 0 | 380 | 43 | X264/MSMF | True | 694.3 |
| 720p | 5 | unthrottled | 291.7 | 2.18 | 6.89 | 22.80 | nan | 1 | 1991 | 100 | X264/MSMF | True | 1695.1 |
| 720p | 1 | unthrottled | 1013.2 | 0.61 | 1.58 | 3.21 | nan | 0 | 934 | 65 | X264/MSMF | True | 1167.9 |
| 1080p | 5 | paced60 | 60.0 | 2.18 | 5.22 | 9.28 | 12.56 | 0 | 1169 | 72 | X264/MSMF | True | 1561.9 |
| 1080p | 5 | unthrottled | 140.3 | 4.66 | 12.44 | 23.86 | nan | 10 | 2014 | 100 | X264/MSMF | True | 1833.4 |
| 1080p | 1 | unthrottled | 522.3 | 0.93 | 2.37 | 12.45 | nan | 0 | 1333 | 85 | X264/MSMF | True | 1355.0 |
