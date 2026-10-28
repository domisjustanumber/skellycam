# P9 - real cameras (DSHOW, MJPG requested, BUFFERSIZE=1), one at a time

10.0s per mode. FOURCC set before AND after the size, as SkellyCam does. retrieve+pub = retrieve() (+ np.copyto into the shm slot for the private mode) + seq commit.

| index | requested | actual WxH @ fps (fourcc) | mode | delivered fps | grab median / p99 ms | retrieve+publish median / p99 ms | CPU ms/frame | in-place verified |
|---|---|---|---|---|---|---|---|---|
| 0 | 1280x720@60 | 1280x720 @ 60 (MJPG) | grab_retrieve_private | 29.7 | 0.00 / 0.01 | 32.00 / 51.94 | 7.63 | - |
| 0 | 1280x720@60 | 1280x720 @ 60 (MJPG) | grab_retrieve_slot | 29.7 | 0.00 / 0.00 | 32.00 / 53.70 | 7.18 | True |
| 0 | 1920x1080@60 | 1920x1080 @ 60 (MJPG) | grab_retrieve_private | 30.0 | 0.00 / 0.01 | 31.99 / 53.21 | 12.66 | - |
| 0 | 1920x1080@60 | 1920x1080 @ 60 (MJPG) | grab_retrieve_slot | 30.0 | 0.00 / 0.01 | 32.01 / 50.58 | 11.42 | True |
| 1 | 1280x720@60 | 1280x720 @ 60 (MJPG) | grab_retrieve_private | 25.8 | 0.00 / 0.01 | 34.55 / 54.59 | 7.93 | - |
| 1 | 1280x720@60 | 1280x720 @ 60 (MJPG) | grab_retrieve_slot | 25.7 | 0.00 / 0.00 | 33.76 / 54.72 | 7.63 | True |
| 1 | 1920x1080@60 | 1920x1080 @ 60 (MJPG) | grab_retrieve_private | 25.8 | 0.00 / 0.01 | 32.51 / 63.63 | 13.44 | - |
| 1 | 1920x1080@60 | 1920x1080 @ 60 (MJPG) | grab_retrieve_slot | 25.8 | 0.00 / 0.00 | 32.73 / 57.20 | 12.29 | True |
| 2 | 1280x720@60 | 1280x720 @ 60 (MJPG) | grab_retrieve_private | 30.1 | 0.00 / 0.01 | 32.00 / 54.33 | 8.31 | - |
| 2 | 1280x720@60 | 1280x720 @ 60 (MJPG) | grab_retrieve_slot | 30.1 | 0.00 / 0.01 | 31.99 / 53.47 | 7.94 | True |
| 2 | 1920x1080@60 | 1920x1080 @ 60 (MJPG) | grab_retrieve_private | 30.1 | 0.00 / 0.01 | 32.00 / 56.94 | 14.69 | - |
| 2 | 1920x1080@60 | 1920x1080 @ 60 (MJPG) | grab_retrieve_slot | 30.0 | 0.00 / 0.00 | 32.05 / 50.86 | 13.44 | True |
| 3 | 1280x720@60 | 1280x720 @ 60 (MJPG) | grab_retrieve_private | 30.1 | 0.00 / 0.01 | 31.97 / 63.96 | 8.25 | - |
| 3 | 1280x720@60 | 1280x720 @ 60 (MJPG) | grab_retrieve_slot | 30.0 | 0.00 / 0.01 | 32.03 / 53.04 | 7.79 | True |
| 3 | 1920x1080@60 | 1920x1080 @ 60 (MJPG) | grab_retrieve_private | 29.9 | 0.00 / 0.01 | 32.02 / 64.04 | 12.33 | - |
| 3 | 1920x1080@60 | 1920x1080 @ 60 (MJPG) | grab_retrieve_slot | 30.0 | 0.00 / 0.01 | 32.00 / 54.34 | 10.95 | True |

## Camera JPEG bytes via PyAV FFmpeg dshow input (vcodec=mjpeg, demux only, no decode), 5 s each

| device | requested | opened | negotiated WxH @ rate | delivered fps | packets starting FF D8 / packets | median bytes/frame | CPU ms per packet |
|---|---|---|---|---|---|---|---|
| c922 Pro Stream Webcam | 1280x720@60 | yes (mjpeg) | 1280x720 @ 60.0 | 30.1 | 151 / 151 | 26451.0 | 0.621 |
| c922 Pro Stream Webcam | 1920x1080@60 | no: OSError(5, 'I/O error', 'video=c922 Pro Stream Webcam') | - | - | - | - | - |
| Logitech Webcam C930e | 1280x720@60 | no: OSError(5, 'I/O error', 'video=Logitech Webcam C930e') | - | - | - | - | - |
| Logitech Webcam C930e | 1920x1080@60 | no: OSError(5, 'I/O error', 'video=Logitech Webcam C930e') | - | - | - | - | - |
| Razer Kiyo Pro | 1280x720@60 | no: OSError(5, 'I/O error', 'video=Razer Kiyo Pro') | - | - | - | - | - |
| Razer Kiyo Pro | 1920x1080@60 | no: OSError(5, 'I/O error', 'video=Razer Kiyo Pro') | - | - | - | - | - |
| USB Camera | 1280x720@60 | no: OSError(5, 'I/O error', 'video=USB Camera') | - | - | - | - | - |
| USB Camera | 1920x1080@60 | no: OSError(5, 'I/O error', 'video=USB Camera') | - | - | - | - | - |

## Raw MJPEG byte access through OpenCV (3 s each)

| index | size | probe | result |
|---|---|---|---|
| 0 | 1280x720 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 87, 'fps': 29.0, 'first': {'shape': [720, 1280, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 2764800.0, 'width': 1280.0, 'height': 720.0} |
| 0 | 1280x720 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 0 | 1920x1080 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 87, 'fps': 29.0, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
| 0 | 1920x1080 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 1 | 1280x720 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 77, 'fps': 25.666666666666668, 'first': {'shape': [720, 1280, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 2764800.0, 'width': 1280.0, 'height': 720.0} |
| 1 | 1280x720 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 1 | 1920x1080 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 77, 'fps': 25.666666666666668, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
| 1 | 1920x1080 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 2 | 1280x720 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 90, 'fps': 30.0, 'first': {'shape': [720, 1280, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 2764800.0, 'width': 1280.0, 'height': 720.0} |
| 2 | 1280x720 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 2 | 1920x1080 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 90, 'fps': 30.0, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
| 2 | 1920x1080 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 3 | 1280x720 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 72, 'fps': 24.0, 'first': {'shape': [720, 1280, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 2764800.0, 'width': 1280.0, 'height': 720.0} |
| 3 | 1280x720 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
| 3 | 1920x1080 | dshow_convert_rgb_0 | {'set_returned': True, 'frames': 69, 'fps': 23.0, 'first': {'shape': [1080, 1920, 3], 'dtype': 'uint8', 'starts_ffd8': False}, 'median_bytes': 6220800.0, 'width': 1920.0, 'height': 1080.0} |
| 3 | 1920x1080 | msmf_format_minus1 | {'set_returned': False, 'frames': 0, 'fps': 0.0, 'first': None, 'median_bytes': None, 'width': 1920.0, 'height': 1080.0} |
