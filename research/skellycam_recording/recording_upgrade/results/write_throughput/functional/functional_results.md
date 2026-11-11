# write_throughput functional tests

Environment: `{"python": "3.12.13", "platform": "Windows-11-10.0.26300-SP0", "machine": "Gerald", "av": "18.0.0", "libavformat": [62, 12, 102], "libavcodec": [62, 28, 102], "numpy": "2.2.6", "cv2": "4.12.0", "psutil": "7.2.2"}`

## T1 round trip (clean close)

| payload | variant | frames_written | units | byte_exact | idx_records | files | av_decoded | frame0_decode_equals_reference | cv2_frames | ffprobe_packets | ffprobe_keyframes | time_base | pts_max_abs_err_us | container_overhead_bytes_per_frame | first_boxes | boxes | write_error | av_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mjpeg | files | 300 | 300 | 300 | 300 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| mjpeg | files_subdirs | 300 | 300 | 300 | 300 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| mjpeg | files_fsync | 300 | 300 | 300 | 300 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| mjpeg | files_subdirs_fsync | 300 | 300 | 300 | 300 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| mjpeg | append | 300 | 300 | 300 | 300 |  |  |  | 300 |  |  |  |  |  |  |  |  |  |
| mjpeg | append_fsync1s | 300 | 300 | 300 | 300 |  |  |  | 300 |  |  |  |  |  |  |  |  |  |
| mjpeg | mkv | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/1000 | 498.916 | 45.6 |  |  |  | [] |
| mjpeg | mkv_flush | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/1000 | 498.916 | 45.6 |  |  |  | [] |
| mjpeg | mkv_flush_cluster1 | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/1000 | 498.916 | 45.6 |  |  |  | [] |
| mjpeg | fmp4_frame | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/90000 | 6.434 | 133.7 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 300, 'mdat': 300, 'mfra': 1} |  | [] |
| mjpeg | fmp4_1s | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/90000 | 6.434 | 14.9 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 10, 'mdat': 10, 'mfra': 1} |  | [] |
| mjpeg | fmp4_hybrid | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/90000 | 6.434 | 140.8 | ['ftyp', 'free', 'mdat', 'moov'] | {'ftyp': 1, 'free': 1, 'mdat': 1, 'moov': 1} |  | [] |
| mjpeg | mkvseg10 | 300 | 300 | 300 | 300 | 5 | 300 | True | 300 | 300 | 300 | 1/1000 |  | 52.2 |  |  |  | [] |
| ffv1 | files | 64 | 64 | 64 | 64 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ffv1 | files_subdirs | 64 | 64 | 64 | 64 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ffv1 | files_fsync | 64 | 64 | 64 | 64 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ffv1 | files_subdirs_fsync | 64 | 64 | 64 | 64 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ffv1 | append | 64 | 64 | 64 | 64 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ffv1 | append_fsync1s | 64 | 64 | 64 | 64 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ffv1 | mkv | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/1000 | 493.727 | 54.9 |  |  |  | [] |
| ffv1 | mkv_flush | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/1000 | 493.727 | 54.9 |  |  |  | [] |
| ffv1 | mkv_flush_cluster1 | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/1000 | 493.727 | 54.9 |  |  |  | [] |
| ffv1 | fmp4_frame | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/90000 | 6.434 | 145.9 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 64, 'mdat': 64, 'mfra': 1} |  | [] |
| ffv1 | fmp4_1s | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/90000 | 6.434 | 28.9 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 3, 'mdat': 3, 'mfra': 1} |  | [] |
| ffv1 | fmp4_hybrid | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/90000 | 6.434 | 163.6 | ['ftyp', 'free', 'mdat', 'moov'] | {'ftyp': 1, 'free': 1, 'mdat': 1, 'moov': 1} |  | [] |
| ffv1 | mkvseg10 | 64 | 64 | 64 | 64 | 2 | 64 | True | 64 | 64 | 64 | 1/1000 |  | 65.6 |  |  |  | [] |

## T2/T3 JPEG folder as an image sequence

| test | layout | reader | api | pattern | opened | backend | files_on_disk | frames_read | packets_read | prop_frame_count | first_frame_max_abs_diff_vs_cv2_imdecode | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T2 | contiguous_0..29 | cv2.VideoCapture | CAP_IMAGES | frame_%06d.jpg | True | CV_IMAGES | 30 | 30 |  | 30.0 | 0 |  |
| T2 | contiguous_0..29 | cv2.VideoCapture | CAP_FFMPEG | frame_%06d.jpg | True | FFMPEG | 30 | 30 |  | 30.0 | 6 |  |
| T2 | contiguous_0..29 | cv2.VideoCapture | CAP_ANY | frame_%06d.jpg | True | FFMPEG | 30 | 30 |  | 30.0 | 6 |  |
| T3 | contiguous_0..29 | PyAV image2 | sequence | frame_%06d.jpg |  |  | 30 |  | 30 |  |  | None |
| T3 | contiguous_0..29 | PyAV image2 | glob | frame_*.jpg |  |  | 30 |  | 0 |  |  | NotImplementedError: [Errno 40] Function not implemented: 'C:\\Users\\Dom\\Documents\\skellycam-raw\\skellycam_recording\\recording_upgrade_20261109\\write_throughput\\functional\\t2\\contiguous\\frame_*.jpg' |
| T3 | contiguous_0..29 | PyAV image2 | glob_recursive | frame_*.jpg |  |  | 30 |  | 0 |  |  | NotImplementedError: [Errno 40] Function not implemented: 'C:\\Users\\Dom\\Documents\\skellycam-raw\\skellycam_recording\\recording_upgrade_20261109\\write_throughput\\functional\\t2\\contiguous\\*\\frame_*.jpg' |
| T2 | gap_at_10 | cv2.VideoCapture | CAP_IMAGES | frame_%06d.jpg | True | CV_IMAGES | 29 | 10 |  | 10.0 | 0 |  |
| T2 | gap_at_10 | cv2.VideoCapture | CAP_FFMPEG | frame_%06d.jpg | True | FFMPEG | 29 | 10 |  | 30.0 | 6 |  |
| T2 | gap_at_10 | cv2.VideoCapture | CAP_ANY | frame_%06d.jpg | True | FFMPEG | 29 | 10 |  | 30.0 | 6 |  |
| T3 | gap_at_10 | PyAV image2 | sequence | frame_%06d.jpg |  |  | 29 |  | 10 |  |  | FileNotFoundError: [Errno 2] No such file or directory: 'C:\\Users\\Dom\\Documents\\skellycam-raw\\skellycam_recording\\recording_upgrade_20261109\\write_throughput\\functional\\t2\\gap_at_10\\frame_%06d.jpg' |
| T3 | gap_at_10 | PyAV image2 | glob | frame_*.jpg |  |  | 29 |  | 0 |  |  | NotImplementedError: [Errno 40] Function not implemented: 'C:\\Users\\Dom\\Documents\\skellycam-raw\\skellycam_recording\\recording_upgrade_20261109\\write_throughput\\functional\\t2\\gap_at_10\\frame_*.jpg' |
| T3 | gap_at_10 | PyAV image2 | glob_recursive | frame_*.jpg |  |  | 29 |  | 0 |  |  | NotImplementedError: [Errno 40] Function not implemented: 'C:\\Users\\Dom\\Documents\\skellycam-raw\\skellycam_recording\\recording_upgrade_20261109\\write_throughput\\functional\\t2\\gap_at_10\\*\\frame_*.jpg' |
| T2 | subdirs_of_10 | cv2.VideoCapture | CAP_IMAGES | frame_%06d.jpg | False | None | 30 | 0 |  | None | None |  |
| T2 | subdirs_of_10 | cv2.VideoCapture | CAP_FFMPEG | frame_%06d.jpg | False | None | 30 | 0 |  | None | None |  |
| T2 | subdirs_of_10 | cv2.VideoCapture | CAP_ANY | frame_%06d.jpg | False | None | 30 | 0 |  | None | None |  |
| T3 | subdirs_of_10 | PyAV image2 | sequence | frame_%06d.jpg |  |  | 30 |  | 0 |  |  | FileNotFoundError: [Errno 2] No such file or directory: 'C:\\Users\\Dom\\Documents\\skellycam-raw\\skellycam_recording\\recording_upgrade_20261109\\write_throughput\\functional\\t2\\subdirs\\frame_%06d.jpg' |
| T3 | subdirs_of_10 | PyAV image2 | glob | frame_*.jpg |  |  | 30 |  | 0 |  |  | NotImplementedError: [Errno 40] Function not implemented: 'C:\\Users\\Dom\\Documents\\skellycam-raw\\skellycam_recording\\recording_upgrade_20261109\\write_throughput\\functional\\t2\\subdirs\\frame_*.jpg' |
| T3 | subdirs_of_10 | PyAV image2 | glob_recursive | frame_*.jpg |  |  | 30 |  | 0 |  |  | NotImplementedError: [Errno 40] Function not implemented: 'C:\\Users\\Dom\\Documents\\skellycam-raw\\skellycam_recording\\recording_upgrade_20261109\\write_throughput\\functional\\t2\\subdirs\\*\\frame_*.jpg' |

## T4 hard kill of the writer process (TerminateProcess) at >= 300 acknowledged frames, 60 fps paced

Summary per variant over repeats (acked_lost = acknowledged frames not readable byte-exact):

| variant | kills | acked_lost_per_kill | acked_lost_max | partial_units_per_kill |
|---|---|---|---|---|
| files | 5 | [0, 0, 0, 0, 0] | 0 | [0, 1, 0, 0, 0] |
| files_subdirs | 5 | [0, 0, 0, 0, 0] | 0 | [0, 0, 0, 0, 0] |
| append | 5 | [0, 0, 0, 0, 0] | 0 | [0, 0, 0, 0, 0] |
| append_fsync1s | 5 | [0, 0, 0, 0, 0] | 0 | [0, 0, 0, 0, 0] |
| mkv | 5 | [6, 5, 3, 4, 2] | 6 | [0, 0, 0, 0, 0] |
| mkv_flush | 5 | [1, 1, 1, 1, 1] | 1 | [0, 0, 0, 0, 0] |
| mkv_flush_cluster1 | 5 | [1, 1, 1, 1, 1] | 1 | [0, 0, 0, 0, 0] |
| fmp4_frame | 5 | [3, 4, 5, 2, 2] | 5 | [1, 1, 1, 1, 1] |
| fmp4_1s | 5 | [35, 23, 59, 52, 19] | 59 | [1, 1, 1, 1, 1] |
| fmp4_hybrid | 5 | [6, 3, 4, 3, 5] | 6 | [1, 1, 1, 1, 1] |
| mkvseg10 | 5 | [3, 5, 3, 4, 3] | 5 | [0, 0, 0, 0, 0] |

All kills:

| variant | repeat | acked_at_kill | acked_lost | partial_or_corrupt_units | units | byte_exact | acked_frames_all_readable | idx_records | byte_exact_without_index_soi_scan | files | av_decoded | cv2_frames | ffprobe_packets | av_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| files | 0 | 323 | 0 | 0 | 323 | 323 | True | 323 |  |  |  |  |  |  |
| files | 1 | 310 | 0 | 1 | 311 | 310 | True | 310 |  |  |  |  |  |  |
| files | 2 | 347 | 0 | 0 | 347 | 347 | True | 347 |  |  |  |  |  |  |
| files | 3 | 305 | 0 | 0 | 305 | 305 | True | 305 |  |  |  |  |  |  |
| files | 4 | 339 | 0 | 0 | 339 | 339 | True | 339 |  |  |  |  |  |  |
| files_subdirs | 0 | 326 | 0 | 0 | 326 | 326 | True | 326 |  |  |  |  |  |  |
| files_subdirs | 1 | 304 | 0 | 0 | 304 | 304 | True | 304 |  |  |  |  |  |  |
| files_subdirs | 2 | 336 | 0 | 0 | 336 | 336 | True | 336 |  |  |  |  |  |  |
| files_subdirs | 3 | 303 | 0 | 0 | 303 | 303 | True | 303 |  |  |  |  |  |  |
| files_subdirs | 4 | 331 | 0 | 0 | 331 | 331 | True | 331 |  |  |  |  |  |  |
| append | 0 | 305 | 0 | 0 | 305 | 305 | True | 305 | 305 |  |  | 305 |  |  |
| append | 1 | 306 | 0 | 0 | 306 | 306 | True | 306 | 306 |  |  | 306 |  |  |
| append | 2 | 331 | 0 | 0 | 331 | 331 | True | 331 | 331 |  |  | 331 |  |  |
| append | 3 | 360 | 0 | 0 | 360 | 360 | True | 360 | 360 |  |  | 360 |  |  |
| append | 4 | 309 | 0 | 0 | 309 | 309 | True | 309 | 309 |  |  | 309 |  |  |
| append_fsync1s | 0 | 316 | 0 | 0 | 316 | 316 | True | 316 | 316 |  |  | 316 |  |  |
| append_fsync1s | 1 | 345 | 0 | 0 | 345 | 345 | True | 345 | 345 |  |  | 345 |  |  |
| append_fsync1s | 2 | 368 | 0 | 0 | 368 | 368 | True | 368 | 368 |  |  | 368 |  |  |
| append_fsync1s | 3 | 342 | 0 | 0 | 342 | 342 | True | 342 | 342 |  |  | 342 |  |  |
| append_fsync1s | 4 | 328 | 0 | 0 | 328 | 328 | True | 328 | 328 |  |  | 328 |  |  |
| mkv | 0 | 370 | 6 | 0 | 364 | 364 | False | 370 |  | 1 | 364 | 364 | 364 | [] |
| mkv | 1 | 303 | 5 | 0 | 298 | 298 | False | 303 |  | 1 | 298 | 298 | 298 | [] |
| mkv | 2 | 362 | 3 | 0 | 359 | 359 | False | 362 |  | 1 | 359 | 359 | 359 | [] |
| mkv | 3 | 321 | 4 | 0 | 317 | 317 | False | 321 |  | 1 | 317 | 317 | 317 | [] |
| mkv | 4 | 310 | 2 | 0 | 308 | 308 | False | 310 |  | 1 | 308 | 308 | 308 | [] |
| mkv_flush | 0 | 308 | 1 | 0 | 307 | 307 | False | 308 |  | 1 | 307 | 307 | 307 | [] |
| mkv_flush | 1 | 322 | 1 | 0 | 321 | 321 | False | 322 |  | 1 | 321 | 321 | 321 | [] |
| mkv_flush | 2 | 358 | 1 | 0 | 357 | 357 | False | 358 |  | 1 | 357 | 357 | 357 | [] |
| mkv_flush | 3 | 313 | 1 | 0 | 312 | 312 | False | 313 |  | 1 | 312 | 312 | 312 | [] |
| mkv_flush | 4 | 342 | 1 | 0 | 341 | 341 | False | 342 |  | 1 | 341 | 341 | 341 | [] |
| mkv_flush_cluster1 | 0 | 346 | 1 | 0 | 345 | 345 | False | 346 |  | 1 | 345 | 345 | 345 | [] |
| mkv_flush_cluster1 | 1 | 327 | 1 | 0 | 326 | 326 | False | 327 |  | 1 | 326 | 326 | 326 | [] |
| mkv_flush_cluster1 | 2 | 339 | 1 | 0 | 338 | 338 | False | 339 |  | 1 | 338 | 338 | 338 | [] |
| mkv_flush_cluster1 | 3 | 304 | 1 | 0 | 303 | 303 | False | 304 |  | 1 | 303 | 303 | 303 | [] |
| mkv_flush_cluster1 | 4 | 304 | 1 | 0 | 303 | 303 | False | 304 |  | 1 | 303 | 303 | 303 | [] |
| fmp4_frame | 0 | 315 | 3 | 1 | 313 | 312 | False | 315 |  | 1 | 313 | 313 | 313 | [] |
| fmp4_frame | 1 | 349 | 4 | 1 | 346 | 345 | False | 349 |  | 1 | 346 | 346 | 346 | [] |
| fmp4_frame | 2 | 331 | 5 | 1 | 327 | 326 | False | 331 |  | 1 | 327 | 327 | 327 | [] |
| fmp4_frame | 3 | 323 | 2 | 1 | 322 | 321 | False | 323 |  | 1 | 322 | 322 | 322 | [] |
| fmp4_frame | 4 | 342 | 2 | 1 | 341 | 340 | False | 342 |  | 1 | 341 | 341 | 341 | [] |
| fmp4_1s | 0 | 333 | 35 | 1 | 299 | 298 | False | 333 |  | 1 | 299 | 299 | 299 | [] |
| fmp4_1s | 1 | 321 | 23 | 1 | 299 | 298 | False | 321 |  | 1 | 299 | 299 | 299 | [] |
| fmp4_1s | 2 | 357 | 59 | 1 | 299 | 298 | False | 357 |  | 1 | 299 | 299 | 299 | [] |
| fmp4_1s | 3 | 350 | 52 | 1 | 299 | 298 | False | 350 |  | 1 | 299 | 299 | 299 | [] |
| fmp4_1s | 4 | 317 | 19 | 1 | 299 | 298 | False | 317 |  | 1 | 299 | 299 | 299 | [] |
| fmp4_hybrid | 0 | 341 | 6 | 1 | 336 | 335 | False | 341 |  | 1 | 336 | 336 | 336 | [] |
| fmp4_hybrid | 1 | 338 | 3 | 1 | 336 | 335 | False | 338 |  | 1 | 336 | 336 | 336 | [] |
| fmp4_hybrid | 2 | 363 | 4 | 1 | 360 | 359 | False | 363 |  | 1 | 360 | 360 | 360 | [] |
| fmp4_hybrid | 3 | 352 | 3 | 1 | 350 | 349 | False | 352 |  | 1 | 350 | 350 | 350 | [] |
| fmp4_hybrid | 4 | 321 | 5 | 1 | 317 | 316 | False | 321 |  | 1 | 317 | 317 | 317 | [] |
| mkvseg10 | 0 | 370 | 3 | 0 | 367 | 367 | False | 370 |  | 4 | 367 | 367 | 367 | [] |
| mkvseg10 | 1 | 308 | 5 | 0 | 303 | 303 | False | 308 |  | 3 | 303 | 303 | 303 | [] |
| mkvseg10 | 2 | 330 | 3 | 0 | 327 | 327 | False | 330 |  | 3 | 327 | 327 | 327 | [] |
| mkvseg10 | 3 | 354 | 4 | 0 | 350 | 350 | False | 354 |  | 3 | 350 | 350 | 350 | [] |
| mkvseg10 | 4 | 311 | 3 | 0 | 308 | 308 | False | 311 |  | 3 | 308 | 308 | 308 | [] |

## T5 clean file truncated to 50 %

| variant | original_bytes | kept_bytes | units | byte_exact | av_decoded | cv2_frames | ffprobe_packets | av_errors |
|---|---|---|---|---|---|---|---|---|
| append | 16592276 | 8296138 | 149 | 149 |  | 150 |  |  |
| append_fsync1s | 16592276 | 8296138 | 149 | 149 |  | 150 |  |  |
| mkv | 16605959 | 8302979 | 149 | 149 | 149 | 149 | 149 | [] |
| mkv_flush | 16605959 | 8302979 | 149 | 149 | 149 | 149 | 149 | [] |
| mkv_flush_cluster1 | 16605959 | 8302979 | 149 | 149 | 149 | 149 | 149 | [] |
| fmp4_frame | 16632377 | 8316188 | 150 | 149 | 150 | 150 | 150 | [] |
| fmp4_1s | 16596747 | 8298373 | 150 | 149 | 150 | 150 | 150 | [] |
| fmp4_hybrid | 16634530 | 8317265 | 0 | 0 | 0 | 0 | 0 | ["InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'C:\\\\Users\\\\Dom\\\\Documents\\\\skellycam-raw\\\\skellycam_recording\\\\recording_upgrade_20261109\\\\write_throughput\\\\functional\\\\t5\\\\fmp4_hybrid\\\\cam00.mp4'"] |

## T6 FFmpeg segment muxer via PyAV

| what | files | packets | byte_exact | stream_time_base | error |
|---|---|---|---|---|---|
| PyAV format='segment', segment_format=matroska, segment_time=2, 300 frames @30 | 5 | 300 | 300 | 1/1000 |  |
