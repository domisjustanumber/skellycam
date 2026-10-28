# (d) UI path: shm read + create_frontend_payload (resize 0.5, JPEG q60, pack) for 5 cameras

| size | path | 10ms relay sleep | payloads/s | distinct frames/s | dup payloads | shm copy median ms | resize+jpeg+pack median ms | p99 ms | total median ms | payload KB | main-proc CPU% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 720p | skellycam_ui | True | 59.9 | 56.8 | 47 | 2.21 | 3.59 | 11.20 | 6.28 | 153 | 59 |
| 720p | freemocap_ui_by_number | True | 58.1 | 57.3 | 13 | 3.26 | 3.53 | 11.41 | 6.85 | 153 | 58 |
| 720p | skellycam_ui | False | 216.8 | 60.1 | 2352 | 1.20 | 3.12 | 7.96 | 4.35 | 132 | 160 |
| 1080p | skellycam_ui | True | 43.7 | 43.7 | 0 | 3.39 | 7.24 | 23.76 | 10.90 | 337 | 103 |
| 1080p | freemocap_ui_by_number | True | 37.9 | 37.9 | 0 | 7.29 | 8.07 | 27.82 | 15.43 | 337 | 115 |
| 1080p | skellycam_ui | False | 70.7 | 58.2 | 187 | 3.96 | 9.67 | 21.88 | 13.81 | 337 | 183 |

No browser attached: ack is instant, so these are upper bounds on server-side UI work/rate.
dup payloads = payloads whose frame_number was already sent (if_newer_than is ignored, camera_group.py L133-146).
