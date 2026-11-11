| res | kind | format | bytes/frame | MB/hour @30fps | round trip | truncation: cuts fully recovered | notes |
|---|---|---|---|---|---|---|---|
| 1280x720 | text | jsonl | 45.9 | 5.0 | True | 28/28 |  |
| 1280x720 | text | msgpack | 31.4 | 3.4 | True | 28/28 |  |
| 1280x720 | text | bin | 42.3 | 4.6 | True | 28/28 |  |
| 1280x720 | text | vtt | 77.2 | 8.3 | True | 28/28 |  |
| 1280x720 | text | svg_per_frame | 289.1 | 31.2 | n/a |  | 300 files, 300 parse |
| 1280x720 | text | svg_single | 167.7 | 18.1 | n/a | strict XML parse fails 25/25 | lenient regex recovers 10-288 groups |
| 1280x720 | text | ass | 95.4 | 10.3 | n/a |  |  |
| 1280x720 | skeleton | jsonl | 666.9 | 72.0 | True | 28/28 |  |
| 1280x720 | skeleton | msgpack | 928.5 | 100.3 | True | 28/28 |  |
| 1280x720 | skeleton | bin | 445.3 | 48.1 | True | 28/28 |  |
| 1280x720 | skeleton | vtt | 698.2 | 75.4 | True | 28/28 |  |
| 1280x720 | skeleton | svg_per_frame | 5161.4 | 557.4 | n/a |  | 300 files, 300 parse |
| 1280x720 | skeleton | svg_single | 5040.0 | 544.3 | n/a | strict XML parse fails 25/25 | lenient regex recovers 11-288 groups |
| 1280x720 | skeleton | ass | 2628.0 | 283.8 | n/a |  |  |
| 1280x720 | charuco | jsonl | 5091.5 | 549.9 | True | 28/28 |  |
| 1280x720 | charuco | msgpack | 6008.9 | 649.0 | True | 28/28 |  |
| 1280x720 | charuco | bin | 2889.4 | 312.1 | True | 28/28 |  |
| 1280x720 | charuco | vtt | 5122.8 | 553.3 | True | 28/28 |  |
| 1280x720 | charuco | svg_per_frame | 30430.4 | 3286.5 | n/a |  | 300 files, 300 parse |
| 1280x720 | charuco | svg_single | 30309.0 | 3273.4 | n/a | strict XML parse fails 25/25 | lenient regex recovers 11-288 groups |
| 1280x720 | charuco | ass | 14621.6 | 1579.1 | n/a |  |  |
| 1280x720 | all | jsonl | 5704.3 | 616.1 | True | 28/28 |  |
| 1280x720 | all | msgpack | 6895.6 | 744.7 | True | 28/28 |  |
| 1280x720 | all | bin | 3287.6 | 355.1 | True | 28/28 |  |
| 1280x720 | all | vtt | 5735.6 | 619.4 | True | 28/28 |  |
| 1280x720 | all | svg_per_frame | 35283.3 | 3810.6 | n/a |  | 300 files, 300 parse |
| 1280x720 | all | svg_single | 35161.9 | 3797.5 | n/a | strict XML parse fails 25/25 | lenient regex recovers 11-288 groups |
| 1280x720 | all | ass | 17056.0 | 1842.0 | n/a |  |  |
| 1920x1080 | text | jsonl | 45.9 | 5.0 | True | 28/28 |  |
| 1920x1080 | text | msgpack | 31.4 | 3.4 | True | 28/28 |  |
| 1920x1080 | text | bin | 42.3 | 4.6 | True | 28/28 |  |
| 1920x1080 | text | vtt | 77.2 | 8.3 | True | 28/28 |  |
| 1920x1080 | text | svg_per_frame | 291.1 | 31.4 | n/a |  | 300 files, 300 parse |
| 1920x1080 | text | svg_single | 167.7 | 18.1 | n/a | strict XML parse fails 25/25 | lenient regex recovers 10-288 groups |
| 1920x1080 | text | ass | 95.4 | 10.3 | n/a |  |  |
| 1920x1080 | skeleton | jsonl | 683.3 | 73.8 | True | 28/28 |  |
| 1920x1080 | skeleton | msgpack | 928.5 | 100.3 | True | 28/28 |  |
| 1920x1080 | skeleton | bin | 445.3 | 48.1 | True | 28/28 |  |
| 1920x1080 | skeleton | vtt | 714.6 | 77.2 | True | 28/28 |  |
| 1920x1080 | skeleton | svg_per_frame | 5213.7 | 563.1 | n/a |  | 300 files, 300 parse |
| 1920x1080 | skeleton | svg_single | 5090.2 | 549.7 | n/a | strict XML parse fails 25/25 | lenient regex recovers 11-288 groups |
| 1920x1080 | skeleton | ass | 2770.2 | 299.2 | n/a |  |  |
| 1920x1080 | charuco | jsonl | 5221.3 | 563.9 | True | 28/28 |  |
| 1920x1080 | charuco | msgpack | 6008.9 | 649.0 | True | 28/28 |  |
| 1920x1080 | charuco | bin | 2889.4 | 312.1 | True | 28/28 |  |
| 1920x1080 | charuco | vtt | 5252.6 | 567.3 | True | 28/28 |  |
| 1920x1080 | charuco | svg_per_frame | 30720.7 | 3317.8 | n/a |  | 300 files, 300 parse |
| 1920x1080 | charuco | svg_single | 30597.3 | 3304.5 | n/a | strict XML parse fails 25/25 | lenient regex recovers 11-288 groups |
| 1920x1080 | charuco | ass | 14909.9 | 1610.3 | n/a |  |  |
| 1920x1080 | all | jsonl | 5850.3 | 631.8 | True | 28/28 |  |
| 1920x1080 | all | msgpack | 6895.6 | 744.7 | True | 28/28 |  |
| 1920x1080 | all | bin | 3287.6 | 355.1 | True | 28/28 |  |
| 1920x1080 | all | vtt | 5881.6 | 635.2 | True | 28/28 |  |
| 1920x1080 | all | svg_per_frame | 35622.5 | 3847.2 | n/a |  | 300 files, 300 parse |
| 1920x1080 | all | svg_single | 35499.1 | 3833.9 | n/a | strict XML parse fails 25/25 | lenient regex recovers 11-288 groups |
| 1920x1080 | all | ass | 17485.1 | 1888.4 | n/a |  |  |
