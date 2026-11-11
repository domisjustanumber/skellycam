# Round trip: RecordingWriter -> RecordingReader (functional, no timing)

PyAV 18.0.0 (libavformat (62, 12, 102)), OpenCV 4.12.0. Script: `scripts/python_integration/test_roundtrip.py`. Timestamps: flash sets = real MF host arrival (QPC ns); other sets = synthetic lattice (see script).

| set | container | pts_mode | frames_in | container_time_base | packets | bytes_exact | sidecar_ts_exact | container_pts_eq_sidecar | pts_within_half_tick | pts_adjusted_frames | pyav_decoded | cv2_read_frames | cv2_frame_count_prop | cv2_fps_prop | cv2_fourcc | container_overhead_bytes_per_frame |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c930e_720p_flash | mkv | real | 891 | 1/1000 | 891 | True | True | True | True | 1 | 891 | 891 | 888.0 | 30.0 | MJPG | 45.2 |
| c930e_720p_flash | mp4f | real | 891 | 1/1000000 | 891 | True | True | True | True | 0 | 891 | 891 | 891.0 | 30.0999 | MJPG | 131.9 |
| c930e_720p_flash | avi | real | 891 | 1/600 | 891 | True | True | True | True | 1 | 891 | 891 | 17761.0 | 600.0 | MJPG | 485.3 |
| c930e_720p_flash | mkv | index | 891 | 1/1000 | 891 | True | True | True | True | 0 | 891 | 891 | 891.0 | 30.0 | MJPG | 45.2 |
| c930e_720p_flash | avi | index | 891 | 1/30 | 891 | True | True | True | True | 0 | 891 | 891 | 891.0 | 30.0 | MJPG | 30.9 |
| c922_720p_flash | mkv | real | 893 | 1/1000 | 893 | True | True | True | True | 0 | 893 | 893 | 893.0 | 30.0 | MJPG | 45.3 |
| c922_720p_flash | mp4f | real | 893 | 1/1000000 | 893 | True | True | True | True | 0 | 893 | 893 | 893.0 | 30.0055 | MJPG | 131.9 |
| c922_720p_flash | avi | real | 893 | 1/600 | 893 | True | True | True | True | 0 | 893 | 893 | 17857.0 | 600.0 | MJPG | 486.8 |
| c922_720p_flash | mkv | index | 893 | 1/1000 | 893 | True | True | True | True | 0 | 893 | 893 | 893.0 | 30.0 | MJPG | 45.3 |
| c922_720p_flash | avi | index | 893 | 1/30 | 893 | True | True | True | True | 0 | 893 | 893 | 893.0 | 30.0 | MJPG | 30.9 |
| c922_1080p | mkv | real | 19 | 1/1000 | 19 | True | True | True | True | 0 | 19 | 19 | 19.0 | 30.0 | MJPG | 69.8 |
| c922_1080p | mp4f | real | 19 | 1/1000000 | 19 | True | True | True | True | 0 | 19 | 19 | 19.0 | 29.8817 | MJPG | 173.2 |
| c922_1080p | avi | real | 19 | 1/600 | 19 | True | True | True | True | 0 | 19 | 19 | 382.0 | 600.0 | MJPG | 782.5 |
| c922_1080p | mkv | index | 19 | 1/1000 | 19 | True | True | True | True | 0 | 19 | 19 | 19.0 | 30.0 | MJPG | 69.8 |
| c922_1080p | avi | index | 19 | 1/30 | 19 | True | True | True | True | 0 | 19 | 19 | 19.0 | 30.0 | MJPG | 324.0 |
| c930e_1080p | mkv | real | 19 | 1/1000 | 19 | True | True | True | True | 0 | 19 | 19 | 19.0 | 30.0 | MJPG | 69.8 |
| c930e_1080p | mp4f | real | 19 | 1/1000000 | 19 | True | True | True | True | 0 | 19 | 19 | 19.0 | 29.8817 | MJPG | 173.2 |
| c930e_1080p | avi | real | 19 | 1/600 | 19 | True | True | True | True | 0 | 19 | 19 | 382.0 | 600.0 | MJPG | 782.2 |
| c930e_1080p | mkv | index | 19 | 1/1000 | 19 | True | True | True | True | 0 | 19 | 19 | 19.0 | 30.0 | MJPG | 69.8 |
| c930e_1080p | avi | index | 19 | 1/30 | 19 | True | True | True | True | 0 | 19 | 19 | 19.0 | 30.0 | MJPG | 323.7 |
| c922_1600x896 | mkv | real | 19 | 1/1000 | 19 | True | True | True | True | 0 | 19 | 19 | 19.0 | 30.0 | MJPG | 69.8 |
| c922_1600x896 | mp4f | real | 19 | 1/1000000 | 19 | True | True | True | True | 0 | 19 | 19 | 19.0 | 29.8817 | MJPG | 173.2 |
| c922_1600x896 | avi | real | 19 | 1/600 | 19 | True | True | True | True | 0 | 19 | 19 | 382.0 | 600.0 | MJPG | 782.1 |
| c922_1600x896 | mkv | index | 19 | 1/1000 | 19 | True | True | True | True | 0 | 19 | 19 | 19.0 | 30.0 | MJPG | 69.8 |
| c922_1600x896 | avi | index | 19 | 1/30 | 19 | True | True | True | True | 0 | 19 | 19 | 19.0 | 30.0 | MJPG | 323.6 |
| c922_720p60 | mkv | real | 10 | 1/1000 | 10 | True | True | True | True | 0 | 10 | 10 | 10.0 | 60.0 | MJPG | 92.5 |
| c922_720p60 | mp4f | real | 10 | 1/1000000 | 10 | True | True | True | True | 0 | 10 | 10 | 10.0 | 58.8509 | MJPG | 211.1 |
| c922_720p60 | avi | real | 10 | 1/600 | 10 | True | True | True | True | 0 | 10 | 10 | 102.0 | 600.0 | MJPG | 813.9 |
| c922_720p60 | mkv | index | 10 | 1/1000 | 10 | True | True | True | True | 0 | 10 | 10 | 10.0 | 60.0 | MJPG | 92.5 |
| c922_720p60 | avi | index | 10 | 1/60 | 10 | True | True | True | True | 0 | 10 | 10 | 10.0 | 60.0 | MJPG | 593.1 |
| generic_1080p | mkv | real | 11 | 1/1000 | 11 | True | True | True | True | 0 | 11 | 11 | 11.0 | 30.0 | MJPG | 88.5 |
| generic_1080p | mp4f | real | 11 | 1/1000000 | 11 | True | True | True | True | 0 | 11 | 11 | 11.0 | 29.7428 | MJPG | 203.8 |
| generic_1080p | avi | real | 11 | 1/600 | 11 | True | True | True | True | 0 | 11 | 11 | 222.0 | 600.0 | MJPG | 1001.7 |
| generic_1080p | mkv | index | 11 | 1/1000 | 11 | True | True | True | True | 0 | 11 | 11 | 11.0 | 30.0 | MJPG | 88.5 |
| generic_1080p | avi | index | 11 | 1/30 | 11 | True | True | True | True | 0 | 11 | 11 | 11.0 | 30.0 | MJPG | 541.4 |

Frame-gap flag test: flagged at [10] (expected [10]).
