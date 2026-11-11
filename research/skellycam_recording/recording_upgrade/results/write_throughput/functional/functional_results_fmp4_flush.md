# write_throughput functional tests

Environment: `{"python": "3.12.13", "platform": "Windows-11-10.0.26300-SP0", "machine": "Gerald", "av": "18.0.0", "libavformat": [62, 12, 102], "libavcodec": [62, 28, 102], "numpy": "2.2.6", "cv2": "4.12.0", "psutil": "7.2.2"}`

## T1 round trip (clean close)

| payload | variant | frames_written | units | byte_exact | idx_records | files | av_decoded | frame0_decode_equals_reference | cv2_frames | ffprobe_packets | ffprobe_keyframes | time_base | pts_max_abs_err_us | container_overhead_bytes_per_frame | first_boxes | boxes | write_error | av_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mjpeg | fmp4_frame_flush | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/90000 | 6.434 | 133.7 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 300, 'mdat': 300, 'mfra': 1} |  | [] |
| mjpeg | fmp4_1s_flush | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/90000 | 6.434 | 14.9 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 10, 'mdat': 10, 'mfra': 1} |  | [] |
| ffv1 | fmp4_frame_flush | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/90000 | 6.434 | 145.9 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 64, 'mdat': 64, 'mfra': 1} |  | [] |
| ffv1 | fmp4_1s_flush | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/90000 | 6.434 | 28.9 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 3, 'mdat': 3, 'mfra': 1} |  | [] |

## T2/T3 JPEG folder as an image sequence

| test | layout | reader | api | pattern | opened | backend | files_on_disk | frames_read | packets_read | prop_frame_count | first_frame_max_abs_diff_vs_cv2_imdecode | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

## T4 hard kill of the writer process (TerminateProcess) at >= 300 acknowledged frames, 60 fps paced

Summary per variant over repeats (acked_lost = acknowledged frames not readable byte-exact):

| variant | kills | acked_lost_per_kill | acked_lost_max | partial_units_per_kill |
|---|---|---|---|---|
| fmp4_frame_flush | 5 | [1, 1, 1, 1, 0] | 1 | [0, 0, 0, 0, 0] |
| fmp4_1s_flush | 5 | [26, 4, 36, 2, 31] | 36 | [0, 0, 0, 0, 0] |

All kills:

| variant | repeat | acked_at_kill | acked_lost | partial_or_corrupt_units | units | byte_exact | acked_frames_all_readable | idx_records | byte_exact_without_index_soi_scan | files | av_decoded | cv2_frames | ffprobe_packets | av_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fmp4_frame_flush | 0 | 323 | 1 | 0 | 322 | 322 | False | 323 |  | 1 | 322 | 322 | 322 | [] |
| fmp4_frame_flush | 1 | 311 | 1 | 0 | 310 | 310 | False | 311 |  | 1 | 310 | 310 | 310 | [] |
| fmp4_frame_flush | 2 | 347 | 1 | 0 | 346 | 346 | False | 347 |  | 1 | 346 | 346 | 346 | [] |
| fmp4_frame_flush | 3 | 305 | 1 | 0 | 304 | 304 | False | 305 |  | 1 | 304 | 304 | 304 | [] |
| fmp4_frame_flush | 4 | 338 | 0 | 0 | 338 | 338 | True | 338 |  | 1 | 338 | 338 | 338 | [] |
| fmp4_1s_flush | 0 | 326 | 26 | 0 | 300 | 300 | False | 326 |  | 1 | 300 | 300 | 300 | [] |
| fmp4_1s_flush | 1 | 304 | 4 | 0 | 300 | 300 | False | 304 |  | 1 | 300 | 300 | 300 | [] |
| fmp4_1s_flush | 2 | 336 | 36 | 0 | 300 | 300 | False | 336 |  | 1 | 300 | 300 | 300 | [] |
| fmp4_1s_flush | 3 | 302 | 2 | 0 | 300 | 300 | False | 302 |  | 1 | 300 | 300 | 300 | [] |
| fmp4_1s_flush | 4 | 331 | 31 | 0 | 300 | 300 | False | 331 |  | 1 | 300 | 300 | 300 | [] |

## T5 clean file truncated to 50 %

| variant | original_bytes | kept_bytes | units | byte_exact | av_decoded | cv2_frames | ffprobe_packets | av_errors |
|---|---|---|---|---|---|---|---|---|

## T6 FFmpeg segment muxer via PyAV

| what | files | packets | byte_exact | stream_time_base | error |
|---|---|---|---|---|---|
