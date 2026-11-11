# write_throughput functional tests

Environment: `{"python": "3.12.13", "platform": "Windows-11-10.0.26300-SP0", "machine": "Gerald", "av": "19.0.2", "libavformat": [63, 1, 102], "libavcodec": [63, 1, 102], "numpy": "2.2.6", "cv2": "4.12.0", "psutil": "7.2.2"}`

## T1 round trip (clean close)

| payload | variant | frames_written | units | byte_exact | idx_records | files | av_decoded | frame0_decode_equals_reference | cv2_frames | ffprobe_packets | ffprobe_keyframes | time_base | pts_max_abs_err_us | container_overhead_bytes_per_frame | first_boxes | boxes | write_error | av_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mjpeg | files | 300 | 300 | 300 | 300 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| mjpeg | append | 300 | 300 | 300 | 300 |  |  |  | 300 |  |  |  |  |  |  |  |  |  |
| mjpeg | mkv | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/1000 | 498.916 | 45.6 |  |  |  | [] |
| mjpeg | mkv_flush | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/1000 | 498.916 | 45.6 |  |  |  | [] |
| mjpeg | fmp4_frame | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/90000 | 6.434 | 133.7 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 300, 'mdat': 300, 'mfra': 1} |  | [] |
| mjpeg | fmp4_frame_flush | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/90000 | 6.434 | 133.7 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 300, 'mdat': 300, 'mfra': 1} |  | [] |
| mjpeg | fmp4_1s | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/90000 | 6.434 | 14.9 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 10, 'mdat': 10, 'mfra': 1} |  | [] |
| mjpeg | fmp4_hybrid | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/90000 | 6.434 | 140.8 | ['ftyp', 'free', 'mdat', 'moov'] | {'ftyp': 1, 'free': 1, 'mdat': 1, 'moov': 1} |  | [] |
| mjpeg | mkvseg10 | 300 | 300 | 300 | 300 | 5 | 300 | True | 300 | 300 | 300 | 1/1000 |  | 52.2 |  |  |  | [] |
| ffv1 | files | 64 | 64 | 64 | 64 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ffv1 | append | 64 | 64 | 64 | 64 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| ffv1 | mkv | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/1000 | 493.727 | 54.9 |  |  |  | [] |
| ffv1 | mkv_flush | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/1000 | 493.727 | 54.9 |  |  |  | [] |
| ffv1 | fmp4_frame | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/90000 | 6.434 | 145.9 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 64, 'mdat': 64, 'mfra': 1} |  | [] |
| ffv1 | fmp4_frame_flush | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/90000 | 6.434 | 145.9 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 64, 'mdat': 64, 'mfra': 1} |  | [] |
| ffv1 | fmp4_1s | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/90000 | 6.434 | 28.9 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 3, 'mdat': 3, 'mfra': 1} |  | [] |
| ffv1 | fmp4_hybrid | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/90000 | 6.434 | 163.5 | ['ftyp', 'free', 'mdat', 'moov'] | {'ftyp': 1, 'free': 1, 'mdat': 1, 'moov': 1} |  | [] |
| ffv1 | mkvseg10 | 64 | 64 | 64 | 64 | 2 | 64 | True | 64 | 64 | 64 | 1/1000 |  | 65.5 |  |  |  | [] |

## T2/T3 JPEG folder as an image sequence

| test | layout | reader | api | pattern | opened | backend | files_on_disk | frames_read | packets_read | prop_frame_count | first_frame_max_abs_diff_vs_cv2_imdecode | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

## T4 hard kill of the writer process (TerminateProcess) at >= 300 acknowledged frames, 60 fps paced

Summary per variant over repeats (acked_lost = acknowledged frames not readable byte-exact):

| variant | kills | acked_lost_per_kill | acked_lost_max | partial_units_per_kill |
|---|---|---|---|---|
| files | 2 | [0, 0] | 0 | [0, 0] |
| append | 2 | [0, 0] | 0 | [0, 0] |
| mkv | 2 | [3, 4] | 4 | [0, 0] |
| mkv_flush | 2 | [1, 1] | 1 | [0, 0] |
| fmp4_frame | 2 | [5, 5] | 5 | [1, 1] |
| fmp4_frame_flush | 2 | [1, 1] | 1 | [0, 0] |
| fmp4_1s | 2 | [33, 62] | 62 | [1, 1] |
| fmp4_hybrid | 2 | [1, 4] | 4 | [1, 1] |
| mkvseg10 | 2 | [4, 5] | 5 | [0, 0] |

All kills:

| variant | repeat | acked_at_kill | acked_lost | partial_or_corrupt_units | units | byte_exact | acked_frames_all_readable | idx_records | byte_exact_without_index_soi_scan | files | av_decoded | cv2_frames | ffprobe_packets | av_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| files | 0 | 323 | 0 | 0 | 323 | 323 | True | 323 |  |  |  |  |  |  |
| files | 1 | 311 | 0 | 0 | 311 | 311 | True | 311 |  |  |  |  |  |  |
| append | 0 | 347 | 0 | 0 | 347 | 347 | True | 347 | 347 |  |  | 347 |  |  |
| append | 1 | 305 | 0 | 0 | 305 | 305 | True | 305 | 305 |  |  | 305 |  |  |
| mkv | 0 | 339 | 3 | 0 | 336 | 336 | False | 339 |  | 1 | 336 | 336 | 336 | [] |
| mkv | 1 | 326 | 4 | 0 | 322 | 322 | False | 326 |  | 1 | 322 | 322 | 322 | [] |
| mkv_flush | 0 | 304 | 1 | 0 | 303 | 303 | False | 304 |  | 1 | 303 | 303 | 303 | [] |
| mkv_flush | 1 | 336 | 1 | 0 | 335 | 335 | False | 336 |  | 1 | 335 | 335 | 335 | [] |
| fmp4_frame | 0 | 303 | 5 | 1 | 299 | 298 | False | 303 |  | 1 | 298 | 298 | 299 | ["InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'avcodec_send_packet()'"] |
| fmp4_frame | 1 | 331 | 5 | 1 | 327 | 326 | False | 331 |  | 1 | 327 | 327 | 327 | [] |
| fmp4_frame_flush | 0 | 305 | 1 | 0 | 304 | 304 | False | 305 |  | 1 | 304 | 304 | 304 | [] |
| fmp4_frame_flush | 1 | 306 | 1 | 0 | 305 | 305 | False | 306 |  | 1 | 305 | 305 | 305 | [] |
| fmp4_1s | 0 | 331 | 33 | 1 | 299 | 298 | False | 331 |  | 1 | 299 | 299 | 299 | [] |
| fmp4_1s | 1 | 360 | 62 | 1 | 299 | 298 | False | 360 |  | 1 | 299 | 299 | 299 | [] |
| fmp4_hybrid | 0 | 308 | 1 | 1 | 308 | 307 | False | 308 |  | 1 | 308 | 308 | 308 | [] |
| fmp4_hybrid | 1 | 316 | 4 | 1 | 313 | 312 | False | 316 |  | 1 | 313 | 313 | 313 | [] |
| mkvseg10 | 0 | 345 | 4 | 0 | 341 | 341 | False | 345 |  | 3 | 341 | 341 | 341 | [] |
| mkvseg10 | 1 | 368 | 5 | 0 | 363 | 363 | False | 368 |  | 4 | 363 | 363 | 363 | ["InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'C:\\\\Users\\\\Dom\\\\Documents\\\\skellycam-raw\\\\skellycam_recording\\\\recording_upgrade_20261109\\\\write_throughput\\\\functional\\\\t4\\\\mkvseg10\\\\cam00_seg0003.mkv'"] |

## T5 clean file truncated to 50 %

| variant | original_bytes | kept_bytes | units | byte_exact | av_decoded | cv2_frames | ffprobe_packets | av_errors |
|---|---|---|---|---|---|---|---|---|
| append | 16592276 | 8296138 | 149 | 149 |  | 150 |  |  |
| mkv | 16605956 | 8302978 | 149 | 149 | 149 | 149 | 149 | [] |
| mkv_flush | 16605956 | 8302978 | 149 | 149 | 149 | 149 | 149 | [] |
| fmp4_frame | 16632376 | 8316188 | 150 | 149 | 150 | 150 | 150 | [] |
| fmp4_frame_flush | 16632376 | 8316188 | 150 | 149 | 150 | 150 | 150 | [] |
| fmp4_1s | 16596746 | 8298373 | 150 | 149 | 150 | 150 | 150 | [] |
| fmp4_hybrid | 16634528 | 8317264 | 0 | 0 | 0 | 0 | 0 | ["InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'C:\\\\Users\\\\Dom\\\\Documents\\\\skellycam-raw\\\\skellycam_recording\\\\recording_upgrade_20261109\\\\write_throughput\\\\functional\\\\t5\\\\fmp4_hybrid\\\\cam00.mp4'"] |

## T6 FFmpeg segment muxer via PyAV

| what | files | packets | byte_exact | stream_time_base | error |
|---|---|---|---|---|---|
