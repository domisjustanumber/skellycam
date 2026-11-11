Versions: cv2_4.12_venv: OpenCV 4.12.0, numpy 2.2.6; cv2_5.0.0.93_uv: OpenCV 5.0.0, numpy 2.2.6

| clip | cv2_4.12_venv CAP_ANY | cv2_5.0.0.93_uv CAP_ANY | cv2_4.12_venv CAP_FFMPEG | cv2_5.0.0.93_uv CAP_FFMPEG |
|---|---|---|---|---|
| mjpeg_mkv | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok |
| mjpeg_mkv_vfr | FFMPEG; count 122; fps 30.0; read 120; seq ok; seek BAD | FFMPEG; count 122; fps 30.0; read 120; seq ok; seek BAD | FFMPEG; count 122; fps 30.0; read 120; seq ok; seek BAD | FFMPEG; count 122; fps 30.0; read 120; seq ok; seek BAD |
| mjpeg_avi | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok |
| mjpeg_mp4frag_vfr | FFMPEG; count 120; fps 29.5035; read 120; seq ok; seek BAD | FFMPEG; count 120; fps 29.5035; read 120; seq ok; seek BAD | FFMPEG; count 120; fps 29.5035; read 120; seq ok; seek BAD | FFMPEG; count 120; fps 29.5035; read 120; seq ok; seek BAD |
| ffv1_mkv | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok |
| ffv1_avi | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok |
| vp9_webm | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok |
| vp9_mkv | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok |
| vp9_mp4 | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok |
| vp9_intra_webm | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok |
| av1svt_webm | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok |
| av1svt_mkv | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok |
| av1svt_mp4 | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok |
| av1svt_mp4_vfr | FFMPEG; count 120; fps 29.5035; read 119; seq BAD; seek BAD | FFMPEG; count 120; fps 29.5035; read 119; seq BAD; seek BAD | FFMPEG; count 120; fps 29.5035; read 119; seq BAD; seek BAD | FFMPEG; count 120; fps 29.5035; read 119; seq BAD; seek BAD |
| h264_x264_mp4 | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok | FFMPEG; count 120; fps 30.0; read 120; seq ok; seek ok |
| camera_bytes:c930e_720p_flash.avi.index.avi | FFMPEG; count 891; fps 30.0; read 891 | FFMPEG; count 891; fps 30.0; read 891 | FFMPEG; count 891; fps 30.0; read 891 | FFMPEG; count 891; fps 30.0; read 891 |
| camera_bytes:c930e_720p_flash.avi.real.avi | FFMPEG; count 17761; fps 600.0; read 891 | FFMPEG; count 17761; fps 600.0; read 891 | FFMPEG; count 17761; fps 600.0; read 891 | FFMPEG; count 17761; fps 600.0; read 891 |
| camera_bytes:c930e_720p_flash.mkv.index.mkv | FFMPEG; count 891; fps 30.0; read 891 | FFMPEG; count 891; fps 30.0; read 891 | FFMPEG; count 891; fps 30.0; read 891 | FFMPEG; count 891; fps 30.0; read 891 |
| camera_bytes:c930e_720p_flash.mkv.real.mkv | FFMPEG; count 888; fps 30.0; read 891 | FFMPEG; count 888; fps 30.0; read 891 | FFMPEG; count 888; fps 30.0; read 891 | FFMPEG; count 888; fps 30.0; read 891 |
| camera_bytes:c930e_720p_flash.mp4f.real.mp4 | FFMPEG; count 891; fps 30.0999; read 891 | FFMPEG; count 891; fps 30.0999; read 891 | FFMPEG; count 891; fps 30.0999; read 891 | FFMPEG; count 891; fps 30.0999; read 891 |

Differences 4.12 -> 5.0.0.93 (any API):
- none
