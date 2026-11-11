# nvImageCodec 0.10.0 GPU JPEG functional test

nvidia-smi before `0, 27 %, 610.88` after `0, 13 %, 610.88`

decoder ids: ['nvjpeg_cuda_decoder', 'nvjpeg_lossless_decoder', 'libjpeg_turbo_decoder', 'opencv_jpeg_decoder', 'opencv_bmp_decoder', 'nvbmp_decoder', 'opencv_jpeg2k_decoder', 'opencv_png_decoder', 'opencv_pnm_decoder', 'libtiff_decoder', 'opencv_tiff_decoder', 'opencv_webp_decoder']

encoder ids: ['nvjpeg_cuda_encoder', 'opencv_jpeg_encoder', 'opencv_bmp_encoder', 'nvbmp_encoder', 'opencv_jpeg2k_encoder', 'opencv_png_encoder', 'opencv_pnm_encoder', 'nvpnm_encoder', 'opencv_tiff_encoder', 'opencv_webp_encoder']

## Decode of real camera JPEGs (vs ffmpeg CPU decode)

| set | src | backend | ok | max/mean abs diff | PSNR dB | error |
|---|---|---|---|---|---|---|
| c930e_1080p | yuvj422p | backend:GPU_ONLY | False | / |  | RuntimeError: Internal error - Could not create decoder. Code: 7 |
| c930e_1080p | yuvj422p | backend:HW_GPU_ONLY | False | / |  | RuntimeError: Internal error - Could not create decoder. Code: 7 |
| c930e_1080p | yuvj422p | backend:HYBRID_CPU_GPU | True | 8/0.245 | 53.14 |  |
| c930e_1080p | yuvj422p | id:nvjpeg_cuda_decoder | True | 8/0.245 | 53.14 |  |
| c930e_1080p | yuvj422p | id:libjpeg_turbo_decoder | True | 8/0.668 | 48.75 |  |
| c922_720p_flash | yuvj422p | backend:GPU_ONLY | False | / |  | RuntimeError: Internal error - Could not create decoder. Code: 7 |
| c922_720p_flash | yuvj422p | backend:HW_GPU_ONLY | False | / |  | RuntimeError: Internal error - Could not create decoder. Code: 7 |
| c922_720p_flash | yuvj422p | backend:HYBRID_CPU_GPU | True | 25/0.179 | 54.18 |  |
| c922_720p_flash | yuvj422p | id:nvjpeg_cuda_decoder | True | 25/0.179 | 54.18 |  |
| c922_720p_flash | yuvj422p | id:libjpeg_turbo_decoder | True | 24/0.574 | 49.15 |  |

## Encode from host RGB (q=90)

| chroma | backend | ok | bytes | ffprobe pix_fmt | PSNR dB | error |
|---|---|---|---|---|---|---|
| CSS_422 | backend:GPU_ONLY | False |  |  |  | RuntimeError: Internal error - Could not create encoder. Code: 7 |
| CSS_422 | id:nvjpeg_cuda_encoder | True | 144880 | yuvj422p | 44.42 |  |
| CSS_422 | id:opencv_jpeg_encoder | True | 145207 | yuvj422p | 47.25 |  |
| CSS_420 | backend:GPU_ONLY | False |  |  |  | RuntimeError: Internal error - Could not create encoder. Code: 7 |
| CSS_420 | id:nvjpeg_cuda_encoder | True | 133516 | yuvj420p | 43.74 |  |
| CSS_420 | id:opencv_jpeg_encoder | True | 133742 | yuvj420p | 46.16 |  |

GPU-resident decode->encode: `[{'ok': True, 'decoded_buffer_kind': 'ImageBufferKind.STRIDED_DEVICE', 'bytes': 144363, 'ffprobe_pix_fmt': 'yuvj422p', 'psnr_vs_ffmpeg_decode_db': 43.5}]`

## YUV/gray input acceptance

| sample_format | ok | ffprobe pix_fmt | error |
|---|---|---|---|
| P_YUV | False |  | RuntimeError: encode returned None |
| I_YUV | False |  | RuntimeError: encode returned None |
| P_Y | True | gray |  |
| I_Y | True | gray |  |
