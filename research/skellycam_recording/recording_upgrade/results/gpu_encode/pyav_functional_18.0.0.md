# PyAV 18.0.0 hardware encode/decode functional test

libavcodec 62.28.102; hwdevices_available: ['cuda', 'dxva2', 'qsv', 'd3d11va', 'd3d12va', 'amf']

hw codecs in wheel: aac_mf, ac3_mf, av1_amf, av1_cuvid, av1_d3d12va, av1_mf, av1_nvenc, av1_qsv, h264_amf, h264_cuvid, h264_d3d12va, h264_mf, h264_nvenc, h264_qsv, hevc_amf, hevc_cuvid, hevc_d3d12va, hevc_mf, hevc_nvenc, hevc_qsv, mjpeg_cuvid, mjpeg_qsv, mp3_mf, mpeg1_cuvid, mpeg2_cuvid, mpeg2_qsv, mpeg4_cuvid, vc1_cuvid, vc1_qsv, vp8_cuvid, vp8_qsv, vp9_amf, vp9_cuvid, vp9_qsv, vvc_qsv

nvidia-smi before `0, 4 %, 610.88` after `0, 6 %, 610.88`

| encoder | variant | input | ok | packets | key pkts | pict_types | codec/profile/pix_fmt | error |
|---|---|---|---|---|---|---|---|---|
| h264_nvenc | intra | sw frames | yes | 32 | 32 | {'I': 32} | h264/Main/yuv420p |  |
| h264_nvenc | intra | hwaccel ctx | yes | 32 | 32 | {'I': 32} | h264/Main/yuv420p |  |
| h264_nvenc | gop15 | sw frames | yes | 32 | 3 | {'I': 3, 'P': 29} | h264/Main/yuv420p |  |
| h264_nvenc | gop15 | hwaccel ctx | yes | 32 | 3 | {'I': 3, 'P': 29} | h264/Main/yuv420p |  |
| hevc_nvenc | intra | sw frames | yes | 32 | 32 | {'I': 32} | hevc/Main/yuv420p |  |
| hevc_nvenc | intra | hwaccel ctx | yes | 32 | 32 | {'I': 32} | hevc/Main/yuv420p |  |
| hevc_nvenc | gop15 | sw frames | yes | 32 | 3 | {'I': 3, 'P': 29} | hevc/Main/yuv420p |  |
| hevc_nvenc | gop15 | hwaccel ctx | yes | 32 | 3 | {'I': 3, 'P': 29} | hevc/Main/yuv420p |  |
| av1_nvenc | intra | sw frames | NO |  |  |  | // | ExternalError: [Errno 542398533] Generic error in an external library: 'avcodec_open2("av1_nvenc", {\'preset\': \'p4\'})' |
| av1_nvenc | intra | hwaccel ctx | NO |  |  |  | // | NotImplementedError: [Errno 40] Function not implemented: 'avcodec_open2("av1_nvenc", {\'preset\': \'p4\'})' |
| av1_nvenc | gop15 | sw frames | NO |  |  |  | // | ExternalError: [Errno 542398533] Generic error in an external library: 'avcodec_open2("av1_nvenc", {\'preset\': \'p4\'})' |
| av1_nvenc | gop15 | hwaccel ctx | NO |  |  |  | // | NotImplementedError: [Errno 40] Function not implemented: 'avcodec_open2("av1_nvenc", {\'preset\': \'p4\'})' |
| h264_qsv | intra | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("h264_qsv", {})' |
| h264_qsv | intra | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| h264_qsv | gop15 | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("h264_qsv", {})' |
| h264_qsv | gop15 | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| hevc_qsv | intra | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("hevc_qsv", {})' |
| hevc_qsv | intra | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| hevc_qsv | gop15 | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("hevc_qsv", {})' |
| hevc_qsv | gop15 | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| av1_qsv | intra | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("av1_qsv", {})' |
| av1_qsv | intra | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| av1_qsv | gop15 | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("av1_qsv", {})' |
| av1_qsv | gop15 | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| vp9_qsv | intra | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("vp9_qsv", {})' |
| vp9_qsv | intra | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| vp9_qsv | gop15 | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("vp9_qsv", {})' |
| vp9_qsv | gop15 | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| mjpeg_qsv | intra | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("mjpeg_qsv", {})' |
| mjpeg_qsv | intra | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| mjpeg_qsv | gop15 | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("mjpeg_qsv", {})' |
| mjpeg_qsv | gop15 | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| h264_amf | intra | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("h264_amf", {})' |
| h264_amf | intra | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| h264_amf | gop15 | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("h264_amf", {})' |
| h264_amf | gop15 | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| hevc_amf | intra | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("hevc_amf", {})' |
| hevc_amf | intra | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| hevc_amf | gop15 | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("hevc_amf", {})' |
| hevc_amf | gop15 | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| av1_amf | intra | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("av1_amf", {})' |
| av1_amf | intra | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| av1_amf | gop15 | sw frames | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred: 'avcodec_open2("av1_amf", {})' |
| av1_amf | gop15 | hwaccel ctx | NO |  |  |  | // | UnknownError: [Errno 1313558101] Unknown error occurred |
| h264_mf | intra | sw frames | yes | 32 | 32 | {'I': 32} | h264/Constrained Baseline/yuv420p |  |
| h264_mf | gop15 | sw frames | yes | 32 | 3 | {'I': 3, 'P': 29} | h264/Constrained Baseline/yuv420p |  |
| hevc_mf | intra | sw frames | yes | 32 | 32 | {'I': 32} | hevc/Main/yuv420p |  |
| hevc_mf | gop15 | sw frames | yes | 32 | 3 | {'I': 3, 'P': 29} | hevc/Main/yuv420p |  |
| av1_mf | intra | sw frames | NO |  |  |  | // | OSError: [Errno 104] Error number -104 occurred: 'avcodec_send_frame()' |
| av1_mf | gop15 | sw frames | NO |  |  |  | // | OSError: [Errno 104] Error number -104 occurred: 'avcodec_send_frame()' |
| h264_d3d12va | intra | sw frames | NO |  |  |  | // | ArgumentError: Invalid argument: 'avcodec_open2("h264_d3d12va", {})' returned 22 |
| h264_d3d12va | intra | hwaccel ctx | yes | 32 | 32 | {'I': 32} | h264/Main/yuv420p |  |
| h264_d3d12va | gop15 | sw frames | NO |  |  |  | // | ArgumentError: Invalid argument: 'avcodec_open2("h264_d3d12va", {})' returned 22 |
| h264_d3d12va | gop15 | hwaccel ctx | yes | 32 | 3 | {'I': 3, 'P': 29} | h264/Main/yuv420p |  |
| hevc_d3d12va | intra | sw frames | NO |  |  |  | // | ArgumentError: Invalid argument: 'avcodec_open2("hevc_d3d12va", {})' returned 22 |
| hevc_d3d12va | intra | hwaccel ctx | yes | 32 | 32 | {'I': 32} | hevc/Main/yuv420p |  |
| hevc_d3d12va | gop15 | sw frames | NO |  |  |  | // | ArgumentError: Invalid argument: 'avcodec_open2("hevc_d3d12va", {})' returned 22 |
| hevc_d3d12va | gop15 | hwaccel ctx | yes | 32 | 3 | {'I': 3, 'P': 29} | hevc/Main/yuv420p |  |
| av1_d3d12va | intra | sw frames | NO |  |  |  | // | ArgumentError: Invalid argument: 'avcodec_open2("av1_d3d12va", {})' returned 22 |
| av1_d3d12va | intra | hwaccel ctx | NO |  |  |  | // | ArgumentError: Invalid argument: 'avcodec_open2("av1_d3d12va", {})' returned 22 |
| av1_d3d12va | gop15 | sw frames | NO |  |  |  | // | ArgumentError: Invalid argument: 'avcodec_open2("av1_d3d12va", {})' returned 22 |
| av1_d3d12va | gop15 | hwaccel ctx | NO |  |  |  | // | ArgumentError: Invalid argument: 'avcodec_open2("av1_d3d12va", {})' returned 22 |
| h264_vulkan | intra | sw frames | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| h264_vulkan | intra | hwaccel ctx | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| h264_vulkan | gop15 | sw frames | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| h264_vulkan | gop15 | hwaccel ctx | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| hevc_vulkan | intra | sw frames | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| hevc_vulkan | intra | hwaccel ctx | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| hevc_vulkan | gop15 | sw frames | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| hevc_vulkan | gop15 | hwaccel ctx | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| av1_vulkan | intra | sw frames | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| av1_vulkan | intra | hwaccel ctx | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| av1_vulkan | gop15 | sw frames | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| av1_vulkan | gop15 | hwaccel ctx | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| ffv1_vulkan | intra | sw frames | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| ffv1_vulkan | intra | hwaccel ctx | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| ffv1_vulkan | gop15 | sw frames | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |
| ffv1_vulkan | gop15 | hwaccel ctx | NO |  |  |  | // | codec not in av.codecs_available (not built into this wheel) |

| set | decoder | ok | frames | output formats | max abs diff Y vs CPU mjpeg | error |
|---|---|---|---|---|---|---|
| c930e_1080p | mjpeg | True | 5 | ['yuvj422p'] |  |  |
| c930e_1080p | mjpeg_cuvid | False |  |  |  | ExternalError: [Errno 542398533] Generic error in an external library: 'avcodec_send_packet()' |
| c930e_1080p | mjpeg+hwaccel_cuda | False |  |  |  | ArgumentError: Invalid argument: 'avcodec_send_packet()' returned 22 |
| c930e_720p_flash | mjpeg | True | 5 | ['yuvj422p'] |  |  |
| c930e_720p_flash | mjpeg_cuvid | False |  |  |  | ExternalError: [Errno 542398533] Generic error in an external library: 'avcodec_send_packet()' |
| c930e_720p_flash | mjpeg+hwaccel_cuda | False |  |  |  | ArgumentError: Invalid argument: 'avcodec_send_packet()' returned 22 |
