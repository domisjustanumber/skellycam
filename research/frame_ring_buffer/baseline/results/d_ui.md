# (d) UI path: shm read + create_frontend_payload (resize 0.5, JPEG q60, pack) for 5 cameras

| size | path | 10ms relay sleep | payloads/s | distinct frames/s | dup payloads | shm copy median ms | resize+jpeg+pack median ms | p99 ms | total median ms | payload KB | main-proc CPU% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 720p | skellycam_ui | True | 60.5 | 57.8 | 40 | 1.33 | 3.23 | 7.90 | 4.70 | 153 | 51 |
| 720p | freemocap_ui_by_number | True | 58.3 | 58.1 | 3 | 2.99 | 3.18 | 7.45 | 6.21 | 132 | 51 |
| 720p | skellycam_ui | False | 250.2 | 60.1 | 2852 | 1.08 | 2.92 | 4.73 | 3.98 | 132 | 161 |
| 1080p | skellycam_ui | True | 46.0 | 46.0 | 0 | 2.74 | 6.59 | 17.43 | 9.39 | 337 | 106 |
| 1080p | freemocap_ui_by_number | True | 41.7 | 41.7 | 0 | 6.12 | 6.75 | 15.58 | 12.87 | 337 | 94 |
| 1080p | skellycam_ui | False | 110.3 | 60.0 | 755 | 2.40 | 6.37 | 12.16 | 8.84 | 337 | 217 |

No browser attached: ack is instant, so these are upper bounds on server-side UI work/rate.
dup payloads = payloads whose frame_number was already sent (if_newer_than is ignored, camera_group.py L133-146).
