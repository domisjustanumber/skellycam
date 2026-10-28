# P11 - is the recording readable after the writer process is killed without release()?

300 frames written before the parent's signal; killed_mid keeps writing at 60 fps for about 1 s more before Process.terminate() (TerminateProcess). Files are deleted after probing.

| size | writer / container | mode | exit code | bytes | cv2 frames decoded | PyAV frames decoded (or error) | >= 300 readable | child error |
|---|---|---|---|---|---|---|---|---|
| 720p | msmf_mp4 | clean | -15 | 35072080 | 300 | 300 | True |  |
| 720p | msmf_mp4 | killed_idle | -15 | 33802206 | 0 | InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'C:\\Users\\Dom\\AppData\\Local\\Temp\\skellycam_frame_pipeline_tmp\\bench_tmp\\p11_crash\\msmf_mp4_720p_killed_idle.mp4' | False |  |
| 720p | msmf_mp4 | killed_mid | -15 | 39787411 | 0 | InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'C:\\Users\\Dom\\AppData\\Local\\Temp\\skellycam_frame_pipeline_tmp\\bench_tmp\\p11_crash\\msmf_mp4_720p_killed_mid.mp4' | False |  |
| 720p | mjpeg_mkv | clean | -15 | 72193863 | 300 | 300 | True |  |
| 720p | mjpeg_mkv | killed_idle | -15 | 71827456 | 298 | 298 | False |  |
| 720p | mjpeg_mkv | killed_mid | -15 | 86507520 | 359 | 359 | True |  |
| 720p | nvenc_fmp4 | clean | -15 | 7795845 | 300 | 300 | True |  |
| 720p | nvenc_fmp4 | killed_idle | -15 | 6029348 | 233 | InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'avcodec_send_packet()' | False |  |
| 720p | nvenc_fmp4 | killed_mid | -15 | 7602212 | 291 | InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'avcodec_send_packet()' | False |  |
| 720p | nvenc_mkv | clean | -15 | 7796251 | 300 | 300 | True |  |
| 720p | nvenc_mkv | killed_idle | -15 | 6029312 | 233 | 233 | False |  |
| 720p | nvenc_mkv | killed_mid | -15 | 7602176 | 291 | 291 | False |  |
| 1080p | msmf_mp4 | clean | -15 | 78919702 | 300 | 300 | True |  |
| 1080p | msmf_mp4 | killed_idle | -15 | 75834396 | 0 | InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'C:\\Users\\Dom\\AppData\\Local\\Temp\\skellycam_frame_pipeline_tmp\\bench_tmp\\p11_crash\\msmf_mp4_1080p_killed_idle.mp4' | False |  |
| 1080p | msmf_mp4 | killed_mid | -15 | 90097420 | 0 | InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'C:\\Users\\Dom\\AppData\\Local\\Temp\\skellycam_frame_pipeline_tmp\\bench_tmp\\p11_crash\\msmf_mp4_1080p_killed_mid.mp4' | False |  |
| 1080p | mjpeg_mkv | clean | -15 | 162155751 | 300 | 300 | True |  |
| 1080p | mjpeg_mkv | killed_idle | -15 | 161480704 | 298 | 298 | False |  |
| 1080p | mjpeg_mkv | killed_mid | -15 | 194510848 | 359 | 359 | True |  |
| 1080p | nvenc_fmp4 | clean | -15 | 18259159 | 300 | 300 | True |  |
| 1080p | nvenc_fmp4 | killed_idle | -15 | 14417956 | 237 | InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'avcodec_send_packet()' | False |  |
| 1080p | nvenc_fmp4 | killed_mid | -15 | 18087972 | 297 | InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'avcodec_send_packet()' | False |  |
| 1080p | nvenc_mkv | clean | -15 | 18259583 | 300 | 300 | True |  |
| 1080p | nvenc_mkv | killed_idle | -15 | 14417920 | 237 | 237 | False |  |
| 1080p | nvenc_mkv | killed_mid | -15 | 18087936 | 297 | 297 | False |  |
