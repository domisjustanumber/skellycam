# write_throughput functional tests

Environment: `{"python": "3.12.13", "platform": "Windows-11-10.0.26300-SP0", "machine": "Gerald", "av": "19.0.2", "libavformat": [63, 1, 102], "libavcodec": [63, 1, 102], "numpy": "2.2.6", "cv2": "4.12.0", "psutil": "7.2.2"}`

## T1 round trip (clean close)

| payload | variant | frames_written | units | byte_exact | idx_records | files | av_decoded | frame0_decode_equals_reference | cv2_frames | ffprobe_packets | ffprobe_keyframes | time_base | pts_max_abs_err_us | container_overhead_bytes_per_frame | first_boxes | boxes | write_error | av_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

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

All kills:

| variant | repeat | acked_at_kill | acked_lost | partial_or_corrupt_units | units | byte_exact | acked_frames_all_readable | idx_records | byte_exact_without_index_soi_scan | files | av_decoded | cv2_frames | ffprobe_packets | av_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## T5 clean file truncated to 50 %

| variant | original_bytes | kept_bytes | units | byte_exact | av_decoded | cv2_frames | ffprobe_packets | av_errors |
|---|---|---|---|---|---|---|---|---|

## T6 FFmpeg segment muxer via PyAV

| what | files | packets | byte_exact | stream_time_base | error |
|---|---|---|---|---|---|
| PyAV format='segment', segment_format=matroska, segment_time=2, 300 frames @30 | 5 | 300 | 300 | 1/1000 |  |
