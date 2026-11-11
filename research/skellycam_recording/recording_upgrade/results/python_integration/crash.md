# Crash tolerance of recwriter files (functional, no timing)

PyAV 18.0.0, OpenCV 4.12.0. Script `scripts/python_integration/test_crash.py`.

## A. Writer process killed (TerminateProcess) after the sidecar held >= 300 records

| container | pts_mode | sidecar_valid_records | sidecar_torn_tail_bytes | killed_pyav_packets | killed_pyav_decoded | killed_cv2_opened | killed_cv2_frame_count_prop | killed_cv2_read_frames | find_unfinished_lists_it | recover_matched_prefix | recovered_cv2_frame_count_prop | recovered_cv2_read_frames | recover_first_mismatch | killed_pyav_demux_error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mkv | real | 300 | 0 | 297 | 297 | True | -2.7670116110564326e+17 | 297 | True | 297 | 297.0 | 297 | None | None |
| mkv | index | 300 | 0 | 297 | 297 | True | -2.7670116110564326e+17 | 297 | True | 297 | 297.0 | 297 | None | None |
| mp4f | real | 300 | 0 | 298 | 298 | True | 298.0 | 298 | True | 297 | 297.0 | 297 | {'index': 297, 'packet_bytes': 22582, 'sidecar_bytes': 82954, 'crc_equal': False, 'pts': 9901073, 'sidecar_pts': 9901073} | None |
| avi | index | 301 | 0 | 301 | 301 | True | 0.0 | 301 | True | 300 | 300.0 | 300 | {'index': 300, 'packet_bytes': 68228, 'sidecar_bytes': 75691, 'crc_equal': False, 'pts': 300, 'sidecar_pts': 300} | None |

## B. Cleanly closed 300-frame file truncated

| container | pts_mode | cut | exact_prefix_packets | first_non_exact_packet | pyav_packets | pyav_decoded | pyav_corrupt_flagged | cv2_opened | cv2_frame_count_prop | cv2_read_frames | pyav_demux_error | pyav_decode_error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mkv | real | 50% | 149 | None | 149 | 149 | 0 | True | 300.0 | 149 | None | None |
| mkv | real | 90% | 270 | None | 270 | 270 | 0 | True | 300.0 | 270 | None | None |
| mkv | real | 99.9% | 299 | None | 299 | 299 | 0 | True | 300.0 | 299 | None | None |
| mkv | real | minus_1_byte | 300 | None | 300 | 300 | 0 | True | 300.0 | 300 | None | None |
| mkv | index | 50% | 149 | None | 149 | 149 | 0 | True | 300.0 | 149 | None | None |
| mkv | index | 90% | 270 | None | 270 | 270 | 0 | True | 300.0 | 270 | None | None |
| mkv | index | 99.9% | 299 | None | 299 | 299 | 0 | True | 300.0 | 299 | None | None |
| mkv | index | minus_1_byte | 300 | None | 300 | 300 | 0 | True | 300.0 | 300 | None | None |
| mp4f | real | 50% | 149 | {'index': 149, 'bytes': 47178, 'expected': 73984} | 150 | 150 | 0 | True | 150.0 | 150 | None | None |
| mp4f | real | 90% | 270 | {'index': 270, 'bytes': 17355, 'expected': 80320} | 271 | 271 | 0 | True | 271.0 | 271 | None | None |
| mp4f | real | 99.9% | 299 | {'index': 299, 'bytes': 63595, 'expected': 81142} | 300 | 300 | 0 | True | 300.0 | 300 | None | None |
| mp4f | real | minus_1_byte | 300 | None | 300 | 300 | 0 | True | 300.0 | 300 | None | None |
| avi | index | 50% | 149 | {'index': 149, 'bytes': 44240, 'expected': 73984} | 150 | 150 | 0 | True | 300.0 | 150 | None | None |
| avi | index | 90% | 270 | {'index': 270, 'bytes': 16117, 'expected': 80320} | 271 | 271 | 0 | True | 300.0 | 271 | None | None |
| avi | index | 99.9% | 299 | {'index': 299, 'bytes': 62682, 'expected': 81142} | 300 | 300 | 0 | True | 300.0 | 300 | None | None |
| avi | index | minus_1_byte | 300 | None | 300 | 300 | 0 | True | 300.0 | 300 | None | None |
