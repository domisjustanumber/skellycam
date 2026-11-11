# write_throughput functional tests

Environment: `{"python": "3.12.13", "platform": "Windows-11-10.0.26300-SP0", "machine": "Gerald", "av": "19.0.2", "libavformat": [63, 1, 102], "libavcodec": [63, 1, 102], "numpy": "2.2.6", "cv2": "4.12.0", "psutil": "7.2.2"}`

## T1 round trip (clean close)

| payload | variant | frames_written | units | byte_exact | idx_records | files | av_decoded | frame0_decode_equals_reference | cv2_frames | ffprobe_packets | ffprobe_keyframes | time_base | pts_max_abs_err_us | container_overhead_bytes_per_frame | first_boxes | boxes | write_error | av_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mjpeg | mkv_flush_cluster1 | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/1000 | 498.916 | 45.6 |  |  |  | [] |
| mjpeg | fmp4_1s_flush | 300 | 300 | 300 | 300 | 1 | 300 | True | 300 | 300 | 300 | 1/90000 | 6.434 | 14.9 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 10, 'mdat': 10, 'mfra': 1} |  | [] |
| ffv1 | mkv_flush_cluster1 | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/1000 | 493.727 | 54.9 |  |  |  | [] |
| ffv1 | fmp4_1s_flush | 64 | 64 | 64 | 64 | 1 | 64 | True | 64 | 64 | 64 | 1/90000 | 6.434 | 28.9 | ['ftyp', 'moov', 'moof', 'mdat', 'moof', 'mdat'] | {'ftyp': 1, 'moov': 1, 'moof': 3, 'mdat': 3, 'mfra': 1} |  | [] |

## T2/T3 JPEG folder as an image sequence

| test | layout | reader | api | pattern | opened | backend | files_on_disk | frames_read | packets_read | prop_frame_count | first_frame_max_abs_diff_vs_cv2_imdecode | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

## T4 hard kill of the writer process (TerminateProcess) at >= 300 acknowledged frames, 60 fps paced

Summary per variant over repeats (acked_lost = acknowledged frames not readable byte-exact):

| variant | kills | acked_lost_per_kill | acked_lost_max | partial_units_per_kill |
|---|---|---|---|---|
| mkv_flush_cluster1 | 2 | [1, 1] | 1 | [0, 0] |
| fmp4_1s_flush | 2 | [46, 5] | 46 | [0, 0] |

All kills:

| variant | repeat | acked_at_kill | acked_lost | partial_or_corrupt_units | units | byte_exact | acked_frames_all_readable | idx_records | byte_exact_without_index_soi_scan | files | av_decoded | cv2_frames | ffprobe_packets | av_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mkv_flush_cluster1 | 0 | 323 | 1 | 0 | 322 | 322 | False | 323 |  | 1 | 322 | 322 | 322 | [] |
| mkv_flush_cluster1 | 1 | 311 | 1 | 0 | 310 | 310 | False | 311 |  | 1 | 310 | 310 | 310 | [] |
| fmp4_1s_flush | 0 | 346 | 46 | 0 | 300 | 300 | False | 346 |  | 1 | 300 | 300 | 300 | [] |
| fmp4_1s_flush | 1 | 305 | 5 | 0 | 300 | 300 | False | 305 |  | 1 | 300 | 300 | 300 | [] |

## T5 clean file truncated to 50 %

| variant | original_bytes | kept_bytes | units | byte_exact | av_decoded | cv2_frames | ffprobe_packets | av_errors |
|---|---|---|---|---|---|---|---|---|

## T6 FFmpeg segment muxer via PyAV

| what | files | packets | byte_exact | stream_time_base | error |
|---|---|---|---|---|---|
