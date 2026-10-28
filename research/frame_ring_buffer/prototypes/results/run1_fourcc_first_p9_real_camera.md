# P9 - real cameras (DSHOW, MJPG requested, BUFFERSIZE=1), one at a time

10.0s per mode, each mode run twice (alternating). retrieve+pub = retrieve() (+ np.copyto into the shm slot for the private mode) + seq commit.

| index | requested | actual WxH @ fps (fourcc) | mode | delivered fps | grab median / p99 ms | retrieve+publish median / p99 ms | CPU ms/frame | in-place verified |
|---|---|---|---|---|---|---|---|---|
| 0 | 1280x720@60 | 1280x720 @ 60 (YUY2) | grab_retrieve_private | 10.0 | 0.01 / 0.01 | 96.08 / 115.83 | 5.16 | - |
| 0 | 1280x720@60 | 1280x720 @ 60 (YUY2) | grab_retrieve_slot | 10.0 | 0.00 / 0.01 | 96.10 / 113.75 | 4.02 | True |
| 0 | 1280x720@60 | 1280x720 @ 60 (YUY2) | grab_retrieve_private | 10.0 | 0.01 / 0.01 | 96.13 / 115.69 | 4.95 | - |
| 0 | 1280x720@60 | 1280x720 @ 60 (YUY2) | grab_retrieve_slot | 10.0 | 0.01 / 0.01 | 96.22 / 113.63 | 4.33 | True |
| 0 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_private | 5.0 | 0.01 / 0.01 | 196.07 / 216.96 | 8.88 | - |
| 0 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_slot | 5.0 | 0.00 / 0.01 | 201.76 / 216.38 | 7.05 | True |
| 0 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_private | 5.0 | 0.01 / 0.01 | 199.80 / 213.35 | 9.50 | - |
| 0 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_slot | 5.0 | 0.00 / 0.01 | 199.54 / 210.88 | 7.05 | True |
| 1 | 1280x720@60 | 1280x720 @ 60 (MJPG) | grab_retrieve_private | 25.7 | 0.00 / 0.01 | 33.58 / 56.77 | 8.72 | - |
| 1 | 1280x720@60 | 1280x720 @ 60 (MJPG) | grab_retrieve_slot | 25.7 | 0.00 / 0.00 | 33.84 / 56.27 | 7.75 | True |
| 1 | 1280x720@60 | 1280x720 @ 60 (MJPG) | grab_retrieve_private | 25.8 | 0.00 / 0.01 | 34.05 / 57.71 | 7.69 | - |
| 1 | 1280x720@60 | 1280x720 @ 60 (MJPG) | grab_retrieve_slot | 25.8 | 0.00 / 0.00 | 33.36 / 55.80 | 7.99 | True |
| 1 | 1920x1080@60 | 1920x1080 @ 60 (MJPG) | grab_retrieve_private | 25.8 | 0.00 / 0.01 | 32.51 / 59.89 | 13.75 | - |
| 1 | 1920x1080@60 | 1920x1080 @ 60 (MJPG) | grab_retrieve_slot | 25.8 | 0.00 / 0.00 | 33.03 / 59.72 | 12.11 | True |
| 1 | 1920x1080@60 | 1920x1080 @ 60 (MJPG) | grab_retrieve_private | 25.8 | 0.00 / 0.01 | 32.73 / 59.71 | 13.44 | - |
| 1 | 1920x1080@60 | 1920x1080 @ 60 (MJPG) | grab_retrieve_slot | 25.8 | 0.00 / 0.00 | 32.54 / 58.58 | 12.17 | True |
| 2 | 1280x720@60 | 1280x720 @ 60 (YUY2) | grab_retrieve_private | 10.0 | 0.01 / 0.01 | 96.12 / 117.88 | 5.00 | - |
| 2 | 1280x720@60 | 1280x720 @ 60 (YUY2) | grab_retrieve_slot | 10.0 | 0.00 / 0.01 | 96.02 / 116.36 | 3.09 | True |
| 2 | 1280x720@60 | 1280x720 @ 60 (YUY2) | grab_retrieve_private | 10.0 | 0.01 / 0.02 | 96.10 / 117.72 | 5.16 | - |
| 2 | 1280x720@60 | 1280x720 @ 60 (YUY2) | grab_retrieve_slot | 10.0 | 0.00 / 0.01 | 96.16 / 115.77 | 3.87 | True |
| 2 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_private | 5.0 | 0.01 / 0.02 | 201.87 / 214.40 | 7.35 | - |
| 2 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_slot | 5.0 | 0.00 / 0.01 | 195.76 / 214.37 | 8.27 | True |
| 2 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_private | 5.0 | 0.01 / 0.03 | 199.36 / 219.43 | 8.44 | - |
| 2 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_slot | 5.0 | 0.00 / 0.01 | 200.48 / 215.96 | 5.82 | True |
| 3 | 1280x720@60 | 1280x720 @ 60 (YUY2) | grab_retrieve_private | 30.0 | 0.01 / 0.01 | 32.04 / 50.58 | 4.69 | - |
| 3 | 1280x720@60 | 1280x720 @ 60 (YUY2) | grab_retrieve_slot | 30.0 | 0.00 / 0.01 | 32.00 / 49.24 | 3.58 | True |
| 3 | 1280x720@60 | 1280x720 @ 60 (YUY2) | grab_retrieve_private | 30.0 | 0.01 / 0.01 | 32.02 / 50.51 | 3.89 | - |
| 3 | 1280x720@60 | 1280x720 @ 60 (YUY2) | grab_retrieve_slot | 30.1 | 0.00 / 0.01 | 32.02 / 48.35 | 3.58 | True |
| 3 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_private | 30.0 | 0.01 / 0.01 | 32.04 / 51.60 | 6.88 | - |
| 3 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_slot | 30.0 | 0.00 / 0.01 | 32.01 / 54.14 | 5.19 | True |
| 3 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_private | 30.1 | 0.01 / 0.01 | 32.01 / 52.31 | 6.38 | - |
| 3 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_slot | 30.0 | 0.00 / 0.01 | 32.03 / 52.56 | 5.76 | True |
| 4 | 1280x720@60 | 1920x1080 @ 60 (}ë6ä) | grab_retrieve_private | 1.0 | 0.01 / 0.01 | 1000.22 / 1001.16 | 0.00 | - |
| 4 | 1280x720@60 | 1920x1080 @ 60 (}ë6ä) | grab_retrieve_slot | 1.0 | 0.01 / 0.02 | 1000.56 / 1000.88 | 0.00 | False |
| 4 | 1280x720@60 | 1920x1080 @ 60 (}ë6ä) | grab_retrieve_private | 1.0 | 0.01 / 0.01 | 1000.39 / 1001.03 | 0.00 | - |
| 4 | 1280x720@60 | 1920x1080 @ 60 (}ë6ä) | grab_retrieve_slot | 1.0 | 0.01 / 0.01 | 1000.49 / 1000.96 | 1.56 | False |
| 4 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_private | 1.0 | 0.01 / 0.02 | 1000.64 / 1001.20 | 0.00 | - |
| 4 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_slot | 1.0 | 0.01 / 0.01 | 1000.65 / 1001.19 | 0.00 | False |
| 4 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_private | 1.0 | 0.01 / 0.01 | 1000.79 / 1001.27 | 0.00 | - |
| 4 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_slot | 1.0 | 0.01 / 0.01 | 1000.33 / 1001.20 | 0.00 | False |
| 5 | 1280x720@60 | 1920x1080 @ 60 (}ë6ä) | grab_retrieve_private | 1.0 | 0.01 / 0.01 | 1000.77 / 1001.22 | 0.00 | - |
| 5 | 1280x720@60 | 1920x1080 @ 60 (}ë6ä) | grab_retrieve_slot | 1.0 | 0.01 / 0.01 | 1000.43 / 1000.79 | 0.00 | False |
| 5 | 1280x720@60 | 1920x1080 @ 60 (}ë6ä) | grab_retrieve_private | 1.0 | 0.01 / 0.01 | 1000.60 / 1001.11 | 0.00 | - |
| 5 | 1280x720@60 | 1920x1080 @ 60 (}ë6ä) | grab_retrieve_slot | 1.0 | 0.01 / 0.01 | 1000.36 / 1000.56 | 0.00 | False |
| 5 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_private | 1.0 | 0.01 / 0.06 | 1000.65 / 1001.06 | 0.00 | - |
| 5 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_slot | 1.0 | 0.01 / 0.02 | 1000.33 / 1001.12 | 1.56 | False |
| 5 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_private | 1.0 | 0.01 / 0.02 | 1000.65 / 1001.23 | 0.00 | - |
| 5 | 1920x1080@60 | 1920x1080 @ 60 (YUY2) | grab_retrieve_slot | 1.0 | 0.01 / 0.02 | 1000.62 / 1001.54 | 0.00 | False |

## Raw MJPEG byte access probes (3 s each)

| index | size | probe | result |
|---|---|---|---|
| 0 | 1280x720 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 29, 'fps': 9.666666666666666, 'first': {'shape': [720, 1280, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 2764800.0, 'width': 1280.0, 'height': 720.0} |
| 0 | 1280x720 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 0 | 1920x1080 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 14, 'fps': 4.666666666666667, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
| 0 | 1920x1080 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 1 | 1280x720 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 77, 'fps': 25.666666666666668, 'first': {'shape': [720, 1280, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 2764800.0, 'width': 1280.0, 'height': 720.0} |
| 1 | 1280x720 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 1 | 1920x1080 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 77, 'fps': 25.666666666666668, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
| 1 | 1920x1080 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 2 | 1280x720 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 29, 'fps': 9.666666666666666, 'first': {'shape': [720, 1280, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 2764800.0, 'width': 1280.0, 'height': 720.0} |
| 2 | 1280x720 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 2 | 1920x1080 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 15, 'fps': 5.0, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
| 2 | 1920x1080 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 3 | 1280x720 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 74, 'fps': 24.666666666666668, 'first': {'shape': [720, 1280, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 2764800.0, 'width': 1280.0, 'height': 720.0} |
| 3 | 1280x720 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 3 | 1920x1080 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 73, 'fps': 24.333333333333332, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
| 3 | 1920x1080 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 4 | 1280x720 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 3, 'fps': 1.0, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
| 4 | 1280x720 | msmf_format_minus1 | {'set_returned': False, 'frames': 159, 'fps': 53.0, 'first': {'shape': [720, 1280, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 2764800.0, 'width': 1280.0, 'height': 720.0} |
| 4 | 1920x1080 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 3, 'fps': 1.0, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
| 4 | 1920x1080 | msmf_format_minus1 | {'set_returned': False, 'frames': 79, 'fps': 26.333333333333332, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
| 5 | 1280x720 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 3, 'fps': 1.0, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
| 5 | 1280x720 | msmf_format_minus1 | {'set_returned': False, 'frames': 86, 'fps': 28.666666666666668, 'first': {'shape': [720, 1280, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 2764800.0, 'width': 1280.0, 'height': 720.0} |
| 5 | 1920x1080 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 3, 'fps': 1.0, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
| 5 | 1920x1080 | msmf_format_minus1 | {'set_returned': False, 'frames': 86, 'fps': 28.666666666666668, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
