# ffmpeg hardware encoder functional test (ffmpeg version 9.0.2-full_build-www.gyan.dev Copyright (c) 2000-2026 the FFmpeg developers)

nvidia-smi sessionCount,util,driver before: `0, 22 %, 610.88` after: `0, 12 %, 610.88`

| encoder | variant | opens+encodes | packets | key pkts | decoded | pict_types | codec/profile/pix_fmt | error (last line) |
|---|---|---|---|---|---|---|---|---|
| av1_nvenc | intra | NO |  |  |  |  | // | Codec not supported / No capable devices found |
| av1_nvenc | gop15 | NO |  |  |  |  | // | Codec not supported / No capable devices found |
| hevc_nvenc | intra | yes | 32 | 32 | 32 | {'I': 32} | hevc/Main/yuv420p |  |
| hevc_nvenc | gop15 | yes | 32 | 3 | 32 | {'I': 3, 'P': 29} | hevc/Main/yuv420p |  |
| h264_nvenc | intra | yes | 32 | 32 | 32 | {'I': 32} | h264/High/yuv420p |  |
| h264_nvenc | gop15 | yes | 32 | 3 | 32 | {'I': 3, 'P': 29} | h264/High/yuv420p |  |
| hevc_nvenc_g1 | intra | NO |  |  |  |  | // | InitializeEncoder failed: invalid param (8): Gop Length should be greater than number of B frames + 1 / Could not open encoder before EOF |
| hevc_nvenc_g1 | gop15 | yes | 32 | 3 | 32 | {'I': 3, 'P': 29} | hevc/Main/yuv420p |  |
| h264_nvenc_g1 | intra | NO |  |  |  |  | // | InitializeEncoder failed: invalid param (8): Gop Length should be greater than number of B frames + 1 / Could not open encoder before EOF |
| h264_nvenc_g1 | gop15 | yes | 32 | 3 | 32 | {'I': 3, 'P': 29} | h264/High/yuv420p |  |
| av1_qsv | intra | NO |  |  |  |  | // | Failed to find d3d11va adapter by vendor id 0x8086 / Device creation failed: -1313558101. |
| av1_qsv | gop15 | NO |  |  |  |  | // | Failed to find d3d11va adapter by vendor id 0x8086 / Device creation failed: -1313558101. |
| hevc_qsv | intra | NO |  |  |  |  | // | Failed to find d3d11va adapter by vendor id 0x8086 / Device creation failed: -1313558101. |
| hevc_qsv | gop15 | NO |  |  |  |  | // | Failed to find d3d11va adapter by vendor id 0x8086 / Device creation failed: -1313558101. |
| h264_qsv | intra | NO |  |  |  |  | // | Failed to find d3d11va adapter by vendor id 0x8086 / Device creation failed: -1313558101. |
| h264_qsv | gop15 | NO |  |  |  |  | // | Failed to find d3d11va adapter by vendor id 0x8086 / Device creation failed: -1313558101. |
| vp9_qsv | intra | NO |  |  |  |  | // | Failed to find d3d11va adapter by vendor id 0x8086 / Device creation failed: -1313558101. |
| vp9_qsv | gop15 | NO |  |  |  |  | // | Failed to find d3d11va adapter by vendor id 0x8086 / Device creation failed: -1313558101. |
| mjpeg_qsv | intra | NO |  |  |  |  | // | Failed to find d3d11va adapter by vendor id 0x8086 / Device creation failed: -1313558101. |
| mjpeg_qsv | gop15 | NO |  |  |  |  | // | Failed to find d3d11va adapter by vendor id 0x8086 / Device creation failed: -1313558101. |
| av1_amf | intra | NO |  |  |  |  | // | DLL amfrt64.dll failed to open / Failed to create  hardware device context (AMF) : Unknown error occurred |
| av1_amf | gop15 | NO |  |  |  |  | // | DLL amfrt64.dll failed to open / Failed to create  hardware device context (AMF) : Unknown error occurred |
| hevc_amf | intra | NO |  |  |  |  | // | DLL amfrt64.dll failed to open / Failed to create  hardware device context (AMF) : Unknown error occurred |
| hevc_amf | gop15 | NO |  |  |  |  | // | DLL amfrt64.dll failed to open / Failed to create  hardware device context (AMF) : Unknown error occurred |
| h264_amf | intra | NO |  |  |  |  | // | DLL amfrt64.dll failed to open / Failed to create  hardware device context (AMF) : Unknown error occurred |
| h264_amf | gop15 | NO |  |  |  |  | // | DLL amfrt64.dll failed to open / Failed to create  hardware device context (AMF) : Unknown error occurred |
| av1_mf | intra | NO |  |  |  |  | // | could not start streaming (80004005) / Conversion failed! |
| av1_mf | gop15 | NO |  |  |  |  | // | could not start streaming (80004005) / Conversion failed! |
| hevc_mf | intra | yes | 32 | 32 | 32 | {'I': 32} | hevc/Main/yuv420p |  |
| hevc_mf | gop15 | yes | 32 | 3 | 32 | {'I': 3, 'P': 29} | hevc/Main/yuv420p |  |
| h264_mf | intra | yes | 32 | 32 | 32 | {'I': 32} | h264/Constrained Baseline/yuv420p |  |
| h264_mf | gop15 | yes | 32 | 3 | 32 | {'I': 3, 'P': 29} | h264/Constrained Baseline/yuv420p |  |
| av1_d3d12va | intra | NO |  |  |  |  | // | Driver does not support requested features. ValidationFlags: 0x10 /   - Codec configuration not supported |
| av1_d3d12va | gop15 | NO |  |  |  |  | // | Driver does not support requested features. ValidationFlags: 0x10 /   - Codec configuration not supported |
| hevc_d3d12va | intra | yes | 32 | 32 | 32 | {'I': 32} | hevc/Main/yuv420p |  |
| hevc_d3d12va | gop15 | yes | 32 | 3 | 32 | {'I': 3, 'P': 29} | hevc/Main/yuv420p |  |
| h264_d3d12va | intra | yes | 32 | 32 | 32 | {'I': 32} | h264/Main/yuv420p |  |
| h264_d3d12va | gop15 | yes | 32 | 3 | 32 | {'I': 3, 'P': 29} | h264/Main/yuv420p |  |
| h264_d3d12va_bf | intra | yes | 32 | 32 | 32 | {'I': 32} | h264/Main/yuv420p |  |
| h264_d3d12va_bf | gop15 | NO |  |  |  |  | // | Encode failed: Unknown error occurred. / Failed to upload frame: -22. |
| h264_d3d12va_mkv | intra | NO |  |  |  |  | // | Could not write header (incorrect codec parameters ?): Invalid data found when processing input |
| h264_d3d12va_mkv | gop15 | NO |  |  |  |  | // | Could not write header (incorrect codec parameters ?): Invalid data found when processing input |
| av1_vulkan | intra | NO |  |  |  |  | // | Device does not support encoding av1! / Could not open encoder before EOF |
| av1_vulkan | gop15 | NO |  |  |  |  | // | Device does not support encoding av1! / Could not open encoder before EOF |
| hevc_vulkan | intra | yes | 32 | 32 | 32 | {'I': 32} | hevc/Main/yuv420p |  |
| hevc_vulkan | gop15 | yes | 32 | 3 | 32 | {'I': 3, 'P': 29} | hevc/Main/yuv420p |  |
| h264_vulkan | intra | yes | 32 | 32 | 32 | {'I': 32} | h264/High/yuv420p |  |
| h264_vulkan | gop15 | yes | 32 | 3 | 32 | {'I': 3, 'P': 29} | h264/High/yuv420p |  |
| ffv1_vulkan | intra | yes | 32 | 32 | 32 | {'I': 32} | ffv1/None/yuv420p |  |
| ffv1_vulkan | gop15 | yes | 32 | 3 | 32 | {'I': 32} | ffv1/None/yuv420p |  |
| ffv1_vulkan_l3 | intra | NO |  |  |  |  | // | Encoding frames with subsampling and unaligned dimensions is only supported in version 4 (-level 4) / Error sending frames to consumers: Not yet implemented in FFmpeg, patches welcome |
| ffv1_vulkan_l3 | gop15 | NO |  |  |  |  | // | Using inter frames requires version 4 (-level 4) / Could not open encoder before EOF |
| ffv1_vulkan_rgb | intra | yes | 32 | 32 | 32 | {'I': 32} | ffv1/None/bgr0 |  |
| ffv1_vulkan_rgb | gop15 | NO |  |  |  |  | // | Using inter frames requires version 4 (-level 4) / Could not open encoder before EOF |
| ffv1_vulkan_bayer | intra | yes | 32 | 32 | 32 | {'I': 32} | ffv1/None/bayer_rggb16le |  |
| ffv1_vulkan_bayer | gop15 | yes | 32 | 3 | 32 | {'I': 32} | ffv1/None/bayer_rggb16le |  |
| prores_ks_vulkan | intra | yes | 32 | 32 | 32 | {'I': 32} | prores/HQ/yuv422p10le |  |
| prores_ks_vulkan | gop15 | yes | 32 | 32 | 32 | {'I': 32} | prores/HQ/yuv422p10le |  |
| av1_vaapi | intra | NO |  |  |  |  | // | Failed to initialise VAAPI connection: -1 (unknown libva error). / Device creation failed: -5. |
| av1_vaapi | gop15 | NO |  |  |  |  | // | Failed to initialise VAAPI connection: -1 (unknown libva error). / Device creation failed: -5. |
| h264_vaapi | intra | NO |  |  |  |  | // | Failed to initialise VAAPI connection: -1 (unknown libva error). / Device creation failed: -5. |
| h264_vaapi | gop15 | NO |  |  |  |  | // | Failed to initialise VAAPI connection: -1 (unknown libva error). / Device creation failed: -5. |

## ffv1_vulkan lossless round-trip

| file | src frames | decoded | byte-exact |
|---|---|---|---|
| ffv1_vulkan | 8 | 8 | True |
| ffv1_vulkan_rgb | 8 | 8 | True |
| ffv1_vulkan_bayer | 8 | 8 | True |
