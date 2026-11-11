# QSV / MF re-check, PyAV 19.0.2 (libavcodec (63, 1, 102)), functional only, 2026-11-09T16:42:40.735574-05:00

Script: `scripts/gpu_encode/qsv_recheck.py` (run: `uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/qsv_recheck.py`).

Display adapters (Get-PnpDevice Status Present Name): OK True Parsec Virtual Display Adapter; OK True Intel(R) UHD Graphics 770; OK True NVIDIA GeForce RTX 3070

hwdevices_available: ['cuda', 'dxva2', 'qsv', 'd3d11va', 'd3d12va', 'amf']

nvidia-smi before `0, 37 %, 610.88` after `0, 6 %, 610.88`

| encoder | variant | input | ok | packets | key pkts | decoded | pict_types | codec/profile/pix_fmt | MFT | error / last log |
|---|---|---|---|---|---|---|---|---|---|---|
| h264_qsv | intra | sw frames | yes | 32 | 32 | 32 | {'I': 32} | h264/High/yuv420p |  |  |
| h264_qsv | intra | hwaccel ctx | NO |  |  |  |  | // |  | UnknownError: [Errno 1313558101] Unknown error occurred; last error log: [AVHWFramesContext] Error creating an internal frame pool / log: AVHWFramesContext: Error initializing a child frames context / AVHWFramesContext: Error creating an internal frame pool |
| h264_qsv | gop15 | sw frames | yes | 32 | 3 | 32 | {'I': 3, 'P': 29} | h264/High/yuv420p |  |  |
| h264_qsv | gop15 | hwaccel ctx | NO |  |  |  |  | // |  | UnknownError: [Errno 1313558101] Unknown error occurred; last error log: [AVHWFramesContext] Error creating an internal frame pool / log: AVHWFramesContext: Error initializing a child frames context / AVHWFramesContext: Error creating an internal frame pool |
| hevc_qsv | intra | sw frames | yes | 32 | 32 | 32 | {'I': 32} | hevc/Main/yuv420p |  |  |
| hevc_qsv | intra | hwaccel ctx | NO |  |  |  |  | // |  | UnknownError: [Errno 1313558101] Unknown error occurred; last error log: [AVHWFramesContext] Error creating an internal frame pool / log: AVHWFramesContext: Error initializing a child frames context / AVHWFramesContext: Error creating an internal frame pool |
| hevc_qsv | gop15 | sw frames | yes | 32 | 3 | 32 | {'I': 3, 'B': 29} | hevc/Main/yuv420p |  |  |
| hevc_qsv | gop15 | hwaccel ctx | NO |  |  |  |  | // |  | UnknownError: [Errno 1313558101] Unknown error occurred; last error log: [AVHWFramesContext] Error creating an internal frame pool / log: AVHWFramesContext: Error initializing a child frames context / AVHWFramesContext: Error creating an internal frame pool |
| av1_qsv | intra | sw frames | NO |  |  |  |  | // |  | NotImplementedError: [Errno 40] Function not implemented: 'avcodec_open2("av1_qsv", {})'; last error log: [av1_qsv] some encoding parameters are not supported by the QSV runtime. Please double check the input parameters. / log: av1_qsv: Current codec type is unsupported / av1_qsv: some encoding parameters are not supported by the QSV runtime. Please double check the input parameters. |
| av1_qsv | intra | hwaccel ctx | NO |  |  |  |  | // |  | UnknownError: [Errno 1313558101] Unknown error occurred; last error log: [AVHWFramesContext] Error creating an internal frame pool / log: AVHWFramesContext: Error initializing a child frames context / AVHWFramesContext: Error creating an internal frame pool |
| av1_qsv | gop15 | sw frames | NO |  |  |  |  | // |  | NotImplementedError: [Errno 40] Function not implemented: 'avcodec_open2("av1_qsv", {})'; last error log: [av1_qsv] some encoding parameters are not supported by the QSV runtime. Please double check the input parameters. / log: av1_qsv: Current codec type is unsupported / av1_qsv: some encoding parameters are not supported by the QSV runtime. Please double check the input parameters. |
| av1_qsv | gop15 | hwaccel ctx | NO |  |  |  |  | // |  | UnknownError: [Errno 1313558101] Unknown error occurred; last error log: [AVHWFramesContext] Error creating an internal frame pool / log: AVHWFramesContext: Error initializing a child frames context / AVHWFramesContext: Error creating an internal frame pool |
| vp9_qsv | intra | sw frames | yes | 32 | 32 | 32 | {'I': 32} | vp9/Profile 0/yuv420p |  |  |
| vp9_qsv | intra | hwaccel ctx | NO |  |  |  |  | // |  | UnknownError: [Errno 1313558101] Unknown error occurred; last error log: [AVHWFramesContext] Error creating an internal frame pool / log: AVHWFramesContext: Error initializing a child frames context / AVHWFramesContext: Error creating an internal frame pool |
| vp9_qsv | gop15 | sw frames | yes | 32 | 3 | 32 | {'I': 3, 'P': 29} | vp9/Profile 0/yuv420p |  |  |
| vp9_qsv | gop15 | hwaccel ctx | NO |  |  |  |  | // |  | UnknownError: [Errno 1313558101] Unknown error occurred; last error log: [AVHWFramesContext] Error creating an internal frame pool / log: AVHWFramesContext: Error initializing a child frames context / AVHWFramesContext: Error creating an internal frame pool |
| mjpeg_qsv | intra | sw frames | yes | 32 | 32 | 32 | {'I': 32} | mjpeg/Baseline/yuvj420p |  |  |
| mjpeg_qsv | intra | hwaccel ctx | NO |  |  |  |  | // |  | UnknownError: [Errno 1313558101] Unknown error occurred; last error log: [AVHWFramesContext] Error creating an internal frame pool / log: AVHWFramesContext: Error initializing a child frames context / AVHWFramesContext: Error creating an internal frame pool |
| mjpeg_qsv | gop15 | sw frames | yes | 32 | 32 | 32 | {'I': 32} | mjpeg/Baseline/yuvj420p |  |  |
| mjpeg_qsv | gop15 | hwaccel ctx | NO |  |  |  |  | // |  | UnknownError: [Errno 1313558101] Unknown error occurred; last error log: [AVHWFramesContext] Error creating an internal frame pool / log: AVHWFramesContext: Error initializing a child frames context / AVHWFramesContext: Error creating an internal frame pool |
| av1_mf | intra | sw frames | NO |  |  |  |  | // | MFT_FRIENDLY_NAME_Attribute='Intel\xae Hardware Accelerated AV1 Encoder MFT' | InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'C:\\Users\\Dom\\Documents\\skellycam-raw\\skellycam_recording\\recording_upgrade_20261109\\gpu_encode\\qsv_recheck_19.0.2\\av1_mf_intra_sw.mkv' / log:  |
| av1_mf | gop15 | sw frames | NO |  |  |  |  | // | MFT_FRIENDLY_NAME_Attribute='Intel\xae Hardware Accelerated AV1 Encoder MFT' | InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'C:\\Users\\Dom\\Documents\\skellycam-raw\\skellycam_recording\\recording_upgrade_20261109\\gpu_encode\\qsv_recheck_19.0.2\\av1_mf_gop15_sw.mkv' / log:  |
| h264_mf | intra | sw frames | yes | 32 | 32 | 32 | {'I': 32} | h264/Constrained Baseline/yuv420p | MFT_FRIENDLY_NAME_Attribute='Intel\xae Quick Sync Video H.264 Encoder MFT'; MFT_FRIENDLY_NAME_Attribute='NVIDIA H.264 Encoder MFT' |  |
| h264_mf | gop15 | sw frames | yes | 32 | 3 | 32 | {'I': 3, 'P': 29} | h264/Constrained Baseline/yuv420p | MFT_FRIENDLY_NAME_Attribute='Intel\xae Quick Sync Video H.264 Encoder MFT'; MFT_FRIENDLY_NAME_Attribute='NVIDIA H.264 Encoder MFT' |  |

| set | decoder | ok | frames (of 5) | output formats | error / last log |
|---|---|---|---|---|---|
| c930e_1080p | mjpeg | True | 5 | ['yuvj422p'] |  |
| c930e_1080p | mjpeg_qsv | True | 5 | ['nv12'] | mjpeg_qsv: Invalid pkt_timebase, passing timestamps as-is. |
| c930e_1080p | mjpeg+hwaccel_qsv | True | 5 | ['yuvj422p'] |  |
| c930e_720p_flash | mjpeg | True | 5 | ['yuvj422p'] |  |
| c930e_720p_flash | mjpeg_qsv | True | 5 | ['nv12'] | mjpeg_qsv: Invalid pkt_timebase, passing timestamps as-is. |
| c930e_720p_flash | mjpeg+hwaccel_qsv | True | 5 | ['yuvj422p'] |  |
