# intra_compare: decode-back and intra-only verification (PyAV 19.0.2 software decode)

One row per (path, input class), aggregated over all knob values. H.264/HEVC: NAL types parsed from every encoder packet (Annex B); decode-back from a raw elementary-stream file with av.open(format=h264|hevc); decoder has_b_frames; decoded pict_type / key_frame per frame. JPEG: each JPEG decoded on its own with PyAV 'mjpeg' (every JPEG is an independent intra image).

| path | input | points | all ok | frames decoded == in | all intra | NAL types seen (IDR: H.264 5, HEVC 19/20) | param sets every packet | decoder has_b_frames | decoded pict types | decoded pix_fmt | profile | stats side data quality/118 per QP (nvenc = frameAvgQP-1) | ffprobe of saved sample (inspection) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ff_mjpeg_420 | yuy2_1080p | 12 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| ff_mjpeg_420 | yuy2_720p | 11 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| ff_mjpeg_420 | mjpeg_720p | 8 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| ff_mjpeg_420 | mjpeg_1080p | 10 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| ff_mjpeg_422 | yuy2_1080p | 12 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| ff_mjpeg_422 | yuy2_720p | 11 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| ff_mjpeg_422 | mjpeg_720p | 8 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| ff_mjpeg_422 | mjpeg_1080p | 10 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| h264_nvenc_420 | yuy2_1080p | 13 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['High'] | 12:[11.0]; 13:[12.0]; 14:[13.0]; 15:[14.0]; 16:[15.0]; 20:[19.0]; 24:[23.0]; 28:[27.0]; 29:[28.0]; 30:[29.0]; 31:[30.0]; 32:[31.0]; 36:[35.0] | 24: has_b_frames=0 frames=16 key=16 {'I': 16} High |
| h264_nvenc_420 | yuy2_720p | 13 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['High'] | 8:[7.0]; 10:[9.0]; 11:[10.0]; 12:[11.0]; 16:[15.0]; 20:[19.0]; 24:[23.0]; 28:[27.0]; 29:[28.0]; 30:[29.0]; 31:[30.0]; 32:[31.0]; 36:[35.0] | 24: has_b_frames=0 frames=16 key=16 {'I': 16} High |
| h264_nvenc_420 | mjpeg_720p | 13 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['High'] | 12:[11.0]; 13:[12.0]; 14:[13.0]; 15:[14.0]; 16:[15.0]; 20:[19.0]; 24:[23.0]; 28:[27.0]; 29:[28.0]; 30:[29.0]; 31:[30.0]; 32:[31.0]; 36:[35.0] | 24: has_b_frames=0 frames=240 key=240 {'I': 240} High |
| h264_nvenc_420 | mjpeg_1080p | 13 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['High'] | 12:[11.0]; 13:[12.0]; 14:[13.0]; 15:[14.0]; 16:[15.0]; 20:[19.0]; 24:[23.0]; 28:[27.0]; 29:[28.0]; 30:[29.0]; 31:[30.0]; 32:[31.0]; 36:[35.0] | 24: has_b_frames=0 frames=38 key=38 {'I': 38} High |
| h264_qsv_420 | yuy2_1080p | 14 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['High'] | 8:[8.0]; 10:[10.0]; 11:[11.0]; 12:[12.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 28:[28.0]; 29:[29.0]; 30:[30.0]; 31:[31.0]; 32:[32.0]; 36:[36.0]; 40:[40.0] | 24: has_b_frames=0 frames=16 key=16 {'I': 16} High |
| h264_qsv_420 | yuy2_720p | 14 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['High'] | 8:[8.0]; 10:[10.0]; 11:[11.0]; 12:[12.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 28:[28.0]; 29:[29.0]; 30:[30.0]; 31:[31.0]; 32:[32.0]; 36:[36.0]; 40:[40.0] | 24: has_b_frames=0 frames=16 key=16 {'I': 16} High |
| h264_qsv_420 | mjpeg_720p | 13 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['High'] | 12:[12.0]; 13:[13.0]; 14:[14.0]; 15:[15.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 28:[28.0]; 29:[29.0]; 30:[30.0]; 31:[31.0]; 32:[32.0]; 36:[36.0] | 24: has_b_frames=0 frames=240 key=240 {'I': 240} High |
| h264_qsv_420 | mjpeg_1080p | 13 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['High'] | 12:[12.0]; 13:[13.0]; 14:[14.0]; 15:[15.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 28:[28.0]; 29:[29.0]; 30:[30.0]; 31:[31.0]; 32:[32.0]; 36:[36.0] | 24: has_b_frames=0 frames=38 key=38 {'I': 38} High |
| hevc_nvenc_420 | yuy2_1080p | 13 | True | True | True | [19, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv420p'] | ['Main'] | 12:[11.0]; 13:[12.0]; 14:[13.0]; 15:[14.0]; 16:[15.0]; 20:[19.0]; 24:[23.0]; 28:[27.0]; 29:[28.0]; 30:[29.0]; 31:[30.0]; 32:[31.0]; 36:[35.0] | 24: has_b_frames=0 frames=16 key=16 {'I': 16} Main |
| hevc_nvenc_420 | yuy2_720p | 13 | True | True | True | [19, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv420p'] | ['Main'] | 12:[11.0]; 13:[12.0]; 14:[13.0]; 15:[14.0]; 16:[15.0]; 20:[19.0]; 24:[23.0]; 28:[27.0]; 29:[28.0]; 30:[29.0]; 31:[30.0]; 32:[31.0]; 36:[35.0] | 24: has_b_frames=0 frames=16 key=16 {'I': 16} Main |
| hevc_nvenc_420 | mjpeg_720p | 13 | True | True | True | [19, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv420p'] | ['Main'] | 8:[7.0]; 10:[9.0]; 11:[10.0]; 12:[11.0]; 16:[15.0]; 20:[19.0]; 24:[23.0]; 28:[27.0]; 29:[28.0]; 30:[29.0]; 31:[30.0]; 32:[31.0]; 36:[35.0] | 24: has_b_frames=0 frames=240 key=240 {'I': 240} Main |
| hevc_nvenc_420 | mjpeg_1080p | 13 | True | True | True | [19, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv420p'] | ['Main'] | 8:[7.0]; 10:[9.0]; 11:[10.0]; 12:[11.0]; 16:[15.0]; 20:[19.0]; 24:[23.0]; 28:[27.0]; 29:[28.0]; 30:[29.0]; 31:[30.0]; 32:[31.0]; 36:[35.0] | 24: has_b_frames=0 frames=38 key=38 {'I': 38} Main |
| hevc_qsv_420 | yuy2_1080p | 16 | True | True | True | [19, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv420p'] | ['Main'] |  | 24: has_b_frames=0 frames=16 key=16 {'I': 16} Main |
| hevc_qsv_420 | yuy2_720p | 16 | True | True | True | [19, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv420p'] | ['Main'] |  | 24: has_b_frames=0 frames=16 key=16 {'I': 16} Main |
| hevc_qsv_420 | mjpeg_720p | 13 | True | True | True | [19, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv420p'] | ['Main'] |  | 24: has_b_frames=0 frames=240 key=240 {'I': 240} Main |
| hevc_qsv_420 | mjpeg_1080p | 13 | True | True | True | [19, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv420p'] | ['Main'] |  | 24: has_b_frames=0 frames=38 key=38 {'I': 38} Main |
| hevc_qsv_422 | yuy2_1080p | 16 | True | True | True | [19, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv422p'] | ['Rext'] |  | 24: has_b_frames=0 frames=16 key=16 {'I': 16} Rext |
| hevc_qsv_422 | yuy2_720p | 16 | True | True | True | [19, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv422p'] | ['Rext'] |  | 24: has_b_frames=0 frames=16 key=16 {'I': 16} Rext |
| hevc_qsv_422 | mjpeg_720p | 13 | True | True | True | [19, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv422p'] | ['Rext'] |  | 24: has_b_frames=0 frames=240 key=240 {'I': 240} Rext |
| hevc_qsv_422 | mjpeg_1080p | 13 | True | True | True | [19, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv422p'] | ['Rext'] |  | 24: has_b_frames=0 frames=38 key=38 {'I': 38} Rext |
| jpeg_turbo_420 | yuy2_1080p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| jpeg_turbo_420 | yuy2_720p | 23 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| jpeg_turbo_420 | mjpeg_720p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| jpeg_turbo_420 | mjpeg_1080p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| jpeg_turbo_422 | yuy2_1080p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| jpeg_turbo_422 | yuy2_720p | 23 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| jpeg_turbo_422 | mjpeg_720p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| jpeg_turbo_422 | mjpeg_1080p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| libx264_ultrafast_420 | yuy2_1080p | 14 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['Constrained Baseline'] | 8:[8.0]; 10:[10.0]; 11:[11.0]; 12:[12.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 25:[25.0]; 26:[26.0]; 27:[27.0]; 28:[28.0]; 32:[32.0]; 36:[36.0]; 40:[40.0] | 24: has_b_frames=0 frames=16 key=16 {'I': 16} Constrained Baseline |
| libx264_ultrafast_420 | yuy2_720p | 14 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['Constrained Baseline'] | 8:[8.0]; 10:[10.0]; 11:[11.0]; 12:[12.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 25:[25.0]; 26:[26.0]; 27:[27.0]; 28:[28.0]; 32:[32.0]; 36:[36.0]; 40:[40.0] | 24: has_b_frames=0 frames=16 key=16 {'I': 16} Constrained Baseline |
| libx264_ultrafast_420 | mjpeg_720p | 13 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['Constrained Baseline'] | 8:[8.0]; 9:[9.0]; 10:[10.0]; 12:[12.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 25:[25.0]; 26:[26.0]; 27:[27.0]; 28:[28.0]; 32:[32.0]; 36:[36.0] | 24: has_b_frames=0 frames=240 key=240 {'I': 240} Constrained Baseline |
| libx264_ultrafast_420 | mjpeg_1080p | 13 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['Constrained Baseline'] | 8:[8.0]; 9:[9.0]; 10:[10.0]; 12:[12.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 25:[25.0]; 26:[26.0]; 27:[27.0]; 28:[28.0]; 32:[32.0]; 36:[36.0] | 24: has_b_frames=0 frames=38 key=38 {'I': 38} Constrained Baseline |
| libx264_veryfast_420 | yuy2_1080p | 14 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['High'] | 8:[8.0]; 10:[10.0]; 11:[11.0]; 12:[12.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 28:[28.0]; 29:[29.0]; 30:[30.0]; 31:[31.0]; 32:[32.0]; 36:[36.0]; 40:[40.0] | 24: has_b_frames=0 frames=16 key=16 {'I': 16} High |
| libx264_veryfast_420 | yuy2_720p | 14 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['High'] | 8:[8.0]; 10:[10.0]; 11:[11.0]; 12:[12.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 25:[25.0]; 26:[26.0]; 27:[27.0]; 28:[28.0]; 32:[32.0]; 36:[36.0]; 40:[40.0] | 24: has_b_frames=0 frames=16 key=16 {'I': 16} High |
| libx264_veryfast_420 | mjpeg_720p | 13 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['High'] | 12:[12.0]; 13:[13.0]; 14:[14.0]; 15:[15.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 28:[28.0]; 29:[29.0]; 30:[30.0]; 31:[31.0]; 32:[32.0]; 36:[36.0] | 24: has_b_frames=0 frames=240 key=240 {'I': 240} High |
| libx264_veryfast_420 | mjpeg_1080p | 13 | True | True | True | [5, 6, 7, 8] | True | [0] | ['I'] | ['yuv420p'] | ['High'] | 12:[12.0]; 13:[13.0]; 14:[14.0]; 15:[15.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 28:[28.0]; 29:[29.0]; 30:[30.0]; 31:[31.0]; 32:[32.0]; 36:[36.0] | 24: has_b_frames=0 frames=38 key=38 {'I': 38} High |
| libx265_ultrafast_420 | yuy2_1080p | 16 | True | True | True | [20, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv420p'] | ['Rext'] | 8:[8.0]; 10:[10.0]; 12:[12.0]; 13:[13.0]; 14:[14.0]; 15:[15.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 28:[28.0]; 29:[29.0]; 30:[30.0]; 31:[31.0]; 32:[32.0]; 36:[36.0]; 40:[40.0] | 24: has_b_frames=0 frames=16 key=16 {'I': 16} Rext |
| libx265_ultrafast_420 | yuy2_720p | 16 | True | True | True | [20, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv420p'] | ['Rext'] | 8:[8.0]; 10:[10.0]; 12:[12.0]; 13:[13.0]; 14:[14.0]; 15:[15.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 25:[25.0]; 26:[26.0]; 27:[27.0]; 28:[28.0]; 32:[32.0]; 36:[36.0]; 40:[40.0] | 24: has_b_frames=0 frames=16 key=16 {'I': 16} Rext |
| libx265_ultrafast_420 | mjpeg_720p | 13 | True | True | True | [20, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv420p'] | ['Rext'] | 8:[8.0]; 10:[10.0]; 11:[11.0]; 12:[12.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 28:[28.0]; 29:[29.0]; 30:[30.0]; 31:[31.0]; 32:[32.0]; 36:[36.0] | 24: has_b_frames=0 frames=240 key=240 {'I': 240} Rext |
| libx265_ultrafast_420 | mjpeg_1080p | 13 | True | True | True | [20, 32, 33, 34, 39] | True | [0] | ['I'] | ['yuv420p'] | ['Rext'] | 8:[8.0]; 10:[10.0]; 11:[11.0]; 12:[12.0]; 16:[16.0]; 20:[20.0]; 24:[24.0]; 28:[28.0]; 29:[29.0]; 30:[30.0]; 31:[31.0]; 32:[32.0]; 36:[36.0] | 24: has_b_frames=0 frames=38 key=38 {'I': 38} Rext |
| mjpeg_qsv_420 | yuy2_1080p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| mjpeg_qsv_420 | yuy2_720p | 23 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| mjpeg_qsv_420 | mjpeg_720p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| mjpeg_qsv_420 | mjpeg_1080p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| mjpeg_qsv_422 | yuy2_1080p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| mjpeg_qsv_422 | yuy2_720p | 23 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| mjpeg_qsv_422 | mjpeg_720p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| mjpeg_qsv_422 | mjpeg_1080p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| nvjpeg_420 | yuy2_1080p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| nvjpeg_420 | yuy2_720p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| nvjpeg_420 | mjpeg_720p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| nvjpeg_420 | mjpeg_1080p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj420p'] |  |  |  |
| nvjpeg_422 | yuy2_1080p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| nvjpeg_422 | yuy2_720p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| nvjpeg_422 | mjpeg_720p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |
| nvjpeg_422 | mjpeg_1080p | 19 | True | True | True | n/a (JPEG) | n/a | n/a | n/a | ['yuvj422p'] |  |  |  |

Failed points: 0

