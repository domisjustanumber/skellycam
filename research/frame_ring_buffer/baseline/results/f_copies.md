# (f) bytes copied per frame (instrumented real calls)

## 720p, rotation=NO_ROTATION (image 2,764,800 B, shm record 2,765,432 B)

Record path, per camera per frame (put_frame + record_frame):

| step | calls | bytes | x image |
|---|---|---|---|
| copy(frame_metadata) in record_frame (L108) | 1.0 | 632 | 0.00 |
| copy.copy in put_data (L132) | 1.0 | 2,765,432 | 1.00 |
| np.copy (flag reads) | 4.0 | 4 | 0.00 |
| np.copyto tiny (<1KiB: index/flag) | 1.0 | 8 | 0.00 |
| shm_slot_assignment (put_data L132) | 1.0 | 2,765,432 | 1.00 |
| heap allocated (tracemalloc peak) put_frame / record_frame | | 2,767,845 / 3,416 | |
| encoder handoff is a view of the private frame (no copy) | True | | |

UI path `skellycam_ui`, per 5-camera multiframe:

| step | calls | bytes | x one image |
|---|---|---|---|
| (analytic) jpeg_data.tobytes() copy L147 | 5.0 | 139,340 | 0.05 |
| (analytic) return _reusable_bytes_payload[:current_pos] slice copy L197 | 1.0 | 139,668 | 0.05 |
| (analytic) slice-assign into _reusable_bytes_payload L176 (+headers) | 5.0 | 139,668 | 0.05 |
| JPEG bytes (imencode) | 5.0 | 139,340 | 0.05 |
| cv2.imencode output | 5.0 | 139,340 | 0.05 |
| cv2.resize output | 5.0 | 3,456,000 | 1.25 |
| np.copy (flag reads) | 60.0 | 60 | 0.00 |
| np.copyto frame-sized (>=1KiB) | 5.0 | 13,827,160 | 5.00 |
| heap allocated (tracemalloc peak) | | 1,443,074 | 0.52 |

UI path `freemocap_ui_by_number`, per 5-camera multiframe:

| step | calls | bytes | x one image |
|---|---|---|---|
| (analytic) jpeg_data.tobytes() copy L147 | 5.0 | 139,340 | 0.05 |
| (analytic) return _reusable_bytes_payload[:current_pos] slice copy L197 | 1.0 | 139,668 | 0.05 |
| (analytic) slice-assign into _reusable_bytes_payload L176 (+headers) | 5.0 | 139,668 | 0.05 |
| JPEG bytes (imencode) | 5.0 | 139,340 | 0.05 |
| cv2.imencode output | 5.0 | 139,340 | 0.05 |
| cv2.resize output | 5.0 | 3,456,000 | 1.25 |
| np.copy (flag reads) | 75.0 | 75 | 0.00 |
| np.copyto frame-sized (>=1KiB) | 5.0 | 13,827,160 | 5.00 |
| heap allocated (tracemalloc peak) | | 13,831,210 | 5.00 |

## 720p, rotation=CLOCKWISE_90 (image 2,764,800 B, shm record 2,765,432 B)

Record path, per camera per frame (put_frame + record_frame):

| step | calls | bytes | x image |
|---|---|---|---|
| copy(frame_metadata) in record_frame (L108) | 1.0 | 632 | 0.00 |
| copy.copy in put_data (L132) | 1.0 | 2,765,432 | 1.00 |
| cv2.rotate output | 1.0 | 2,764,800 | 1.00 |
| np.copy (flag reads) | 4.0 | 4 | 0.00 |
| np.copyto tiny (<1KiB: index/flag) | 1.0 | 8 | 0.00 |
| shm_slot_assignment (put_data L132) | 1.0 | 2,765,432 | 1.00 |
| heap allocated (tracemalloc peak) put_frame / record_frame | | 2,767,819 / 2,767,992 | |
| encoder handoff is a view of the private frame (no copy) | rotated: cv2.rotate output | | |

UI path `skellycam_ui`, per 5-camera multiframe:

| step | calls | bytes | x one image |
|---|---|---|---|
| (analytic) jpeg_data.tobytes() copy L147 | 5.0 | 145,065 | 0.05 |
| (analytic) return _reusable_bytes_payload[:current_pos] slice copy L197 | 1.0 | 145,393 | 0.05 |
| (analytic) slice-assign into _reusable_bytes_payload L176 (+headers) | 5.0 | 145,393 | 0.05 |
| JPEG bytes (imencode) | 5.0 | 145,065 | 0.05 |
| cv2.imencode output | 5.0 | 145,065 | 0.05 |
| cv2.resize output | 5.0 | 3,456,000 | 1.25 |
| cv2.rotate output | 5.0 | 13,824,000 | 5.00 |
| np.copy (flag reads) | 60.0 | 60 | 0.00 |
| np.copyto frame-sized (>=1KiB) | 5.0 | 13,827,160 | 5.00 |
| heap allocated (tracemalloc peak) | | 6,283,859 | 2.27 |

UI path `freemocap_ui_by_number`, per 5-camera multiframe:

| step | calls | bytes | x one image |
|---|---|---|---|
| (analytic) jpeg_data.tobytes() copy L147 | 5.0 | 145,065 | 0.05 |
| (analytic) return _reusable_bytes_payload[:current_pos] slice copy L197 | 1.0 | 145,393 | 0.05 |
| (analytic) slice-assign into _reusable_bytes_payload L176 (+headers) | 5.0 | 145,393 | 0.05 |
| JPEG bytes (imencode) | 5.0 | 145,065 | 0.05 |
| cv2.imencode output | 5.0 | 145,065 | 0.05 |
| cv2.resize output | 5.0 | 3,456,000 | 1.25 |
| cv2.rotate output | 5.0 | 13,824,000 | 5.00 |
| np.copy (flag reads) | 75.0 | 75 | 0.00 |
| np.copyto frame-sized (>=1KiB) | 5.0 | 13,827,160 | 5.00 |
| heap allocated (tracemalloc peak) | | 13,831,210 | 5.00 |

## 1080p, rotation=NO_ROTATION (image 6,220,800 B, shm record 6,221,432 B)

Record path, per camera per frame (put_frame + record_frame):

| step | calls | bytes | x image |
|---|---|---|---|
| copy(frame_metadata) in record_frame (L108) | 1.0 | 632 | 0.00 |
| copy.copy in put_data (L132) | 1.0 | 6,221,432 | 1.00 |
| np.copy (flag reads) | 4.0 | 4 | 0.00 |
| np.copyto tiny (<1KiB: index/flag) | 1.0 | 8 | 0.00 |
| shm_slot_assignment (put_data L132) | 1.0 | 6,221,432 | 1.00 |
| heap allocated (tracemalloc peak) put_frame / record_frame | | 6,223,818 / 3,416 | |
| encoder handoff is a view of the private frame (no copy) | True | | |

UI path `skellycam_ui`, per 5-camera multiframe:

| step | calls | bytes | x one image |
|---|---|---|---|
| (analytic) jpeg_data.tobytes() copy L147 | 5.0 | 307,931 | 0.05 |
| (analytic) return _reusable_bytes_payload[:current_pos] slice copy L197 | 1.0 | 308,259 | 0.05 |
| (analytic) slice-assign into _reusable_bytes_payload L176 (+headers) | 5.0 | 308,259 | 0.05 |
| JPEG bytes (imencode) | 5.0 | 307,931 | 0.05 |
| cv2.imencode output | 5.0 | 307,931 | 0.05 |
| cv2.resize output | 5.0 | 7,776,000 | 1.25 |
| np.copy (flag reads) | 60.0 | 60 | 0.00 |
| np.copyto frame-sized (>=1KiB) | 5.0 | 31,107,160 | 5.00 |
| heap allocated (tracemalloc peak) | | 3,239,284 | 0.52 |

UI path `freemocap_ui_by_number`, per 5-camera multiframe:

| step | calls | bytes | x one image |
|---|---|---|---|
| (analytic) jpeg_data.tobytes() copy L147 | 5.0 | 307,931 | 0.05 |
| (analytic) return _reusable_bytes_payload[:current_pos] slice copy L197 | 1.0 | 308,259 | 0.05 |
| (analytic) slice-assign into _reusable_bytes_payload L176 (+headers) | 5.0 | 308,259 | 0.05 |
| JPEG bytes (imencode) | 5.0 | 307,931 | 0.05 |
| cv2.imencode output | 5.0 | 307,931 | 0.05 |
| cv2.resize output | 5.0 | 7,776,000 | 1.25 |
| np.copy (flag reads) | 75.0 | 75 | 0.00 |
| np.copyto frame-sized (>=1KiB) | 5.0 | 31,107,160 | 5.00 |
| heap allocated (tracemalloc peak) | | 31,111,208 | 5.00 |

## 1080p, rotation=CLOCKWISE_90 (image 6,220,800 B, shm record 6,221,432 B)

Record path, per camera per frame (put_frame + record_frame):

| step | calls | bytes | x image |
|---|---|---|---|
| copy(frame_metadata) in record_frame (L108) | 1.0 | 632 | 0.00 |
| copy.copy in put_data (L132) | 1.0 | 6,221,432 | 1.00 |
| cv2.rotate output | 1.0 | 6,220,800 | 1.00 |
| np.copy (flag reads) | 4.0 | 4 | 0.00 |
| np.copyto tiny (<1KiB: index/flag) | 1.0 | 8 | 0.00 |
| shm_slot_assignment (put_data L132) | 1.0 | 6,221,432 | 1.00 |
| heap allocated (tracemalloc peak) put_frame / record_frame | | 6,223,819 / 6,223,992 | |
| encoder handoff is a view of the private frame (no copy) | rotated: cv2.rotate output | | |

UI path `skellycam_ui`, per 5-camera multiframe:

| step | calls | bytes | x one image |
|---|---|---|---|
| (analytic) jpeg_data.tobytes() copy L147 | 5.0 | 321,506 | 0.05 |
| (analytic) return _reusable_bytes_payload[:current_pos] slice copy L197 | 1.0 | 321,834 | 0.05 |
| (analytic) slice-assign into _reusable_bytes_payload L176 (+headers) | 5.0 | 321,834 | 0.05 |
| JPEG bytes (imencode) | 5.0 | 321,506 | 0.05 |
| cv2.imencode output | 5.0 | 321,506 | 0.05 |
| cv2.resize output | 5.0 | 7,776,000 | 1.25 |
| cv2.rotate output | 5.0 | 31,104,000 | 5.00 |
| np.copy (flag reads) | 60.0 | 60 | 0.00 |
| np.copyto frame-sized (>=1KiB) | 5.0 | 31,107,160 | 5.00 |
| heap allocated (tracemalloc peak) | | 14,131,445 | 2.27 |

UI path `freemocap_ui_by_number`, per 5-camera multiframe:

| step | calls | bytes | x one image |
|---|---|---|---|
| (analytic) jpeg_data.tobytes() copy L147 | 5.0 | 321,506 | 0.05 |
| (analytic) return _reusable_bytes_payload[:current_pos] slice copy L197 | 1.0 | 321,834 | 0.05 |
| (analytic) slice-assign into _reusable_bytes_payload L176 (+headers) | 5.0 | 321,834 | 0.05 |
| JPEG bytes (imencode) | 5.0 | 321,506 | 0.05 |
| cv2.imencode output | 5.0 | 321,506 | 0.05 |
| cv2.resize output | 5.0 | 7,776,000 | 1.25 |
| cv2.rotate output | 5.0 | 31,104,000 | 5.00 |
| np.copy (flag reads) | 75.0 | 75 | 0.00 |
| np.copyto frame-sized (>=1KiB) | 5.0 | 31,107,160 | 5.00 |
| heap allocated (tracemalloc peak) | | 31,111,213 | 5.00 |

