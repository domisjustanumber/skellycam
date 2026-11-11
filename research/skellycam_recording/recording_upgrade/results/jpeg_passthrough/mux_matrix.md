# mux_matrix results (mux_matrix.json)

Generated from `mux_matrix.json`; meta: `{"date": "2026-11-09T11:03:51", "python": "3.12.13 (main, Apr 14 2026, 14:31:26) [MSC v.1944 64 bit (AMD64)]", "pyav": "18.0.0", "pyav_ffmpeg_libs": {"libavutil": "60.26.102", "libavcodec": "62.28.102", "libavformat": "62.12.102", "libavdevice": "62.3.102", "libavfilter": "11.14.102", "libswscale": "9.5.102", "libswresample": "6.3.102"}, "opencv": "4.12.0"}`

Columns: write = writer result; bytes pyav / ffx = PyAV demux packets / `ffmpeg -c:v copy -f image2` files SHA-256-equal to input, in order;
cv2 n = CAP_FFMPEG frames read (FRAME_COUNT prop); seek = CAP_PROP_POS_FRAMES+read equal to sequential frame k;
ANY = backend chosen by cv2.VideoCapture(path) and its FRAME_COUNT; MSMF = frames read via CAP_MSMF; FMC = FreeMoCap VideoHelper frame_count / reads ok;
ts err = max |reported - input| timestamp in us after aligning first frame (pyav pts, ffprobe pts_time, cv2 POS_MSEC).

## Across all sets

| writer/mode | container | sets written / tried | byte-exact pyav / ffx (sets) | cv2 FRAME_COUNT == frames (sets) | cv2 frames read == frames (sets) | cv2 seek exact (sum) | FMC count == frames (sets) | MSMF read all (sets) | max ts err us pyav / ffprobe / cv2 | pyav decode errors |
|---|---|---|---|---|---|---|---|---|---|---|
| pyav/vfr | mkv | 7/7 | 7 / 7 | 6 | 7 | 65/70 | 6 | 6 | 470 / 470 / 470 | 0 |
| pyav/cfr | mkv | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 7 | 333 / 333 / 333 | 0 |
| ffmpeg/cfr | mkv | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 7 | 333 / 333 / 333 | 0 |
| pyav/vfr | webm | 0/7 | 0 / 0 | 0 | 0 | 0/0 | 0 | 0 | - / - / - | 0 |
| pyav/cfr | webm | 0/7 | 0 / 0 | 0 | 0 | 0/0 | 0 | 0 | - / - / - | 0 |
| ffmpeg/cfr | webm | 0/7 | 0 / 0 | 0 | 0 | 0/0 | 0 | 0 | - / - / - | 0 |
| pyav/vfr | mp4 | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 0 | 6 / 6 / 6 | 0 |
| pyav/cfr | mp4 | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 0 | 0 / 0 / 0 | 0 |
| ffmpeg/cfr | mp4 | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 0 | 0 / 0 / 0 | 0 |
| pyav/vfr | fmp4_1s | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 0 | 6 / 6 / 6 | 0 |
| pyav/cfr | fmp4_1s | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 0 | 0 / 0 / 0 | 0 |
| ffmpeg/cfr | fmp4_1s | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 0 | 0 / 0 / 0 | 0 |
| pyav/vfr | fmp4_perframe | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 0 | 6 / 6 / 6 | 0 |
| pyav/cfr | fmp4_perframe | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 0 | 0 / 0 / 0 | 0 |
| ffmpeg/cfr | fmp4_perframe | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 0 | 0 / 0 / 0 | 0 |
| pyav/vfr | mov | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 7 | 6 / 6 / 6 | 0 |
| pyav/cfr | mov | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 7 | 0 / 0 / 0 | 0 |
| ffmpeg/cfr | mov | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 7 | 0 / 0 / 0 | 0 |
| pyav/vfr | avi | 6/7 | 6 / 6 | 0 | 6 | 55/60 | 0 | 0 | 830 / 830 / 830 | 0 |
| pyav/cfr | avi | 7/7 | 7 / 7 | 0 | 7 | 60/70 | 0 | 0 | 0 / 0 / 0 | 0 |
| ffmpeg/cfr | avi | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 7 | 0 / 0 / 0 | 0 |
| pyav/vfr | nut | 7/7 | 7 / 7 | 0 | 7 | 66/70 | 0 | 0 | 6 / 6 / 6 | 0 |
| pyav/cfr | nut | 7/7 | 7 / 7 | 0 | 7 | 70/70 | 0 | 0 | 0 / 0 / 0 | 0 |
| ffmpeg/cfr | nut | 7/7 | 7 / 7 | 0 | 7 | 70/70 | 0 | 0 | 0 / 0 / 0 | 0 |
| pyav/vfr | mjpeg_raw_mux | 7/7 | 7 / 7 | 0 | 7 | 0/70 | 0 | 0 | 6031976 / 6031976 / 6032562 | 0 |
| pyav/cfr | mjpeg_raw_mux | 7/7 | 7 / 7 | 0 | 7 | 0/70 | 0 | 0 | 5946667 / 5946667 / 5946354 | 0 |
| ffmpeg/cfr | mjpeg_raw_mux | 7/7 | 7 / 7 | 0 | 7 | 0/70 | 0 | 0 | 5946667 / 5946667 / 5946354 | 0 |
| pyav/vfr | avi_tb_rate | 6/7 | 6 / 6 | 6 | 6 | 60/60 | 6 | 6 | 14672 / 14672 / 14672 | 0 |
| pyav/cfr | avi_tb_rate | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 7 | 0 / 0 / 0 | 0 |
| pyav/vfr | mp4_tb_us | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 0 | 0 / 0 / 0 | 0 |
| pyav/cfr | mp4_tb_us | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 0 | 0 / 0 / 0 | 0 |
| pyav/vfr | mov_tb_us | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 7 | 0 / 0 / 0 | 0 |
| pyav/cfr | mov_tb_us | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 7 | 7 | 0 / 0 / 0 | 0 |
| pyav/vfr | nut_tb_us | 7/7 | 7 / 7 | 0 | 7 | 66/70 | 0 | 0 | 0 / 0 / 0 | 0 |
| pyav/cfr | nut_tb_us | 7/7 | 7 / 7 | 0 | 7 | 70/70 | 0 | 0 | 0 / 0 / 0 | 0 |
| python/vfr | raw_sidecar | 7/7 | 7 / 7 | 0 | 7 | 0/70 | 0 | 0 | 6031976 / 6031976 / 6032562 | 0 |
| python/vfr | jpg_folder | 7/7 | 7 / 7 | 7 | 7 | 70/70 | 0 | 7 | 6031976 / 6031976 / 6031976 | 0 |

## c930e_720p_flash

| writer/mode | container | write | file bytes | bytes pyav | bytes ffx | ffprobe nb_frames / pkts | cv2 n (prop) | seek | ANY backend (prop) | MSMF n | FMC count / reads ok | ts err pyav | ts err ffprobe | ts err cv2 | pyav decode errs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pyav/vfr | mkv | ok | 49354777 | yes | yes | None / 891 | 891 (888) | 5/10 | FFMPEG (888) | 888 | 888 / 4/4 | 470 non-mono | 470 non-mono | 470 non-mono | 0 |
| pyav/cfr | mkv | ok | 49354796 | yes | yes | None / 891 | 891 (891) | 10/10 | FFMPEG (891) | 891 | 891 / 4/4 | 333 | 333 | 333 | 0 |
| ffmpeg/cfr | mkv | ok | 49354812 | yes | yes | None / 891 | 891 (891) | 10/10 | FFMPEG (891) | 891 | 891 / 4/4 | 333 | 333 | 333 | 0 |
| pyav/vfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/cfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| ffmpeg/cfr | webm | FAIL: [out#0/webm @ 000002314b2e1a00] Could not write header (incorrect codec parameters ?): Inv | 262 | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/vfr | mp4 | ok | 49325754 | yes | yes | 891 / 891 | 891 (891) | 10/10 | FFMPEG (891) | 0 | 891 / 4/4 | 6 | 6 | 6 | 0 |
| pyav/cfr | mp4 | ok | 49319386 | yes | yes | 891 / 891 | 891 (891) | 10/10 | FFMPEG (891) | 0 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mp4 | ok | 49319385 | yes | yes | 891 / 891 | 891 (891) | 10/10 | FFMPEG (891) | 0 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_1s | ok | 49326260 | yes | yes | None / 891 | 891 (891) | 10/10 | FFMPEG (891) | 0 | 891 / 4/4 | 6 | 6 | 6 | 0 |
| pyav/cfr | fmp4_1s | ok | 49322696 | yes | yes | None / 891 | 891 (891) | 10/10 | FFMPEG (891) | 0 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_1s | ok | 49322695 | yes | yes | None / 891 | 891 (891) | 10/10 | FFMPEG (891) | 0 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_perframe | ok | 49432043 | yes | yes | None / 891 | 891 (891) | 10/10 | FFMPEG (891) | 0 | 891 / 4/4 | 6 | 6 | 6 | 0 |
| pyav/cfr | fmp4_perframe | ok | 49432043 | yes | yes | None / 891 | 891 (891) | 10/10 | FFMPEG (891) | 0 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_perframe | ok | 49432042 | yes | yes | None / 891 | 891 (891) | 10/10 | FFMPEG (891) | 0 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov | ok | 49325661 | yes | yes | 891 / 891 | 891 (891) | 10/10 | FFMPEG (891) | 891 | 891 / 4/4 | 6 | 6 | 6 | 0 |
| pyav/cfr | mov | ok | 49319293 | yes | yes | 891 / 891 | 891 (891) | 10/10 | FFMPEG (891) | 891 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mov | ok | 49319292 | yes | yes | 891 / 891 | 891 (891) | 10/10 | FFMPEG (891) | 891 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | avi | FAIL: ArgumentError: Invalid argument: 'C:\\Users\\Dom\\Documents\\skellycam-raw\\skellycam_reco | 4602544 | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/cfr | avi | ok | 49748332 | yes | yes | 17820 / 891 | 891 (17820) | 5/10 | FFMPEG (17820) | 17801 | 17820 / 2/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | avi | ok | 49342036 | yes | yes | 891 / 891 | 891 (891) | 10/10 | FFMPEG (891) | 891 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut | ok | 49339898 | yes | yes | None / 891 | 891 (887) | 6/10 | FFMPEG (887) | not opened | 887 / 4/4 | 6 | 6 | 6 | 0 |
| pyav/cfr | nut | ok | 49339897 | yes | yes | None / 891 | 891 (890) | 10/10 | FFMPEG (890) | not opened | 890 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | nut | ok | 49339603 | yes | yes | None / 891 | 891 (890) | 10/10 | FFMPEG (890) | not opened | 890 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mjpeg_raw_mux | ok | 49314521 | yes | yes | None / 891 | 891 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 6031976 | 6031976 | 6032562 | 0 |
| pyav/cfr | mjpeg_raw_mux | ok | 49314521 | yes | yes | None / 891 | 891 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 5933333 | 5933333 | 5933919 | 0 |
| ffmpeg/cfr | mjpeg_raw_mux | ok | 49314521 | yes | yes | None / 891 | 891 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 5933333 | 5933333 | 5933919 | 0 |
| pyav/vfr | avi_tb_rate | FAIL: ArgumentError: Invalid argument: 'C:\\Users\\Dom\\Documents\\skellycam-raw\\skellycam_reco | 4565104 | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/cfr | avi_tb_rate | ok | 49342036 | yes | yes | 891 / 891 | 891 (891) | 10/10 | FFMPEG (891) | 891 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mp4_tb_us | ok | 49326458 | yes | yes | 891 / 891 | 891 (891) | 10/10 | FFMPEG (891) | 0 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mp4_tb_us | ok | 49324138 | yes | yes | 891 / 891 | 891 (891) | 10/10 | FFMPEG (891) | 0 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov_tb_us | ok | 49326365 | yes | yes | 891 / 891 | 891 (891) | 10/10 | FFMPEG (891) | 891 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mov_tb_us | ok | 49324045 | yes | yes | 891 / 891 | 891 (891) | 10/10 | FFMPEG (891) | 891 | 891 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut_tb_us | ok | 49341430 | yes | yes | None / 891 | 891 (887) | 6/10 | FFMPEG (887) | not opened | 887 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | nut_tb_us | ok | 49341431 | yes | yes | None / 891 | 891 (890) | 10/10 | FFMPEG (890) | not opened | 890 / 4/4 | 0 | 0 | 0 | 0 |
| python/vfr | raw_sidecar | ok | 49314521 | yes | yes | None / 891 | 891 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | - | ERR ValidationError: 1 validation error for VideoMetad | 6031976 | 6031976 | 6032562 | 0 |
| python/vfr | jpg_folder | ok | 49314521 | yes | yes | None / 891 | 891 (891) | 10/10 | FFMPEG (891) | 891 | ERR FileNotFoundError: Video file not found: C:\Users\ | 6031976 | 6031976 | 6031976 | 0 |

## c922_720p_flash

| writer/mode | container | write | file bytes | bytes pyav | bytes ffx | ffprobe nb_frames / pkts | cv2 n (prop) | seek | ANY backend (prop) | MSMF n | FMC count / reads ok | ts err pyav | ts err ffprobe | ts err cv2 | pyav decode errs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pyav/vfr | mkv | ok | 69383629 | yes | yes | None / 893 | 893 (893) | 10/10 | FFMPEG (893) | 893 | 893 / 4/4 | 430 | 430 | 430 | 0 |
| pyav/cfr | mkv | ok | 69383629 | yes | yes | None / 893 | 893 (893) | 10/10 | FFMPEG (893) | 893 | 893 / 4/4 | 333 | 333 | 333 | 0 |
| ffmpeg/cfr | mkv | ok | 69383645 | yes | yes | None / 893 | 893 (893) | 10/10 | FFMPEG (893) | 893 | 893 / 4/4 | 333 | 333 | 333 | 0 |
| pyav/vfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/cfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| ffmpeg/cfr | webm | FAIL: [out#0/webm @ 0000021cde611040] Could not write header (incorrect codec parameters ?): Inv | 262 | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/vfr | mp4 | ok | 69354098 | yes | yes | 893 / 893 | 893 (893) | 10/10 | FFMPEG (893) | 0 | 893 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | mp4 | ok | 69347842 | yes | yes | 893 / 893 | 893 (893) | 10/10 | FFMPEG (893) | 0 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mp4 | ok | 69347841 | yes | yes | 893 / 893 | 893 (893) | 10/10 | FFMPEG (893) | 0 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_1s | ok | 69354932 | yes | yes | None / 893 | 893 (893) | 10/10 | FFMPEG (893) | 0 | 893 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | fmp4_1s | ok | 69351360 | yes | yes | None / 893 | 893 (893) | 10/10 | FFMPEG (893) | 0 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_1s | ok | 69351359 | yes | yes | None / 893 | 893 (893) | 10/10 | FFMPEG (893) | 0 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_perframe | ok | 69460961 | yes | yes | None / 893 | 893 (893) | 10/10 | FFMPEG (893) | 0 | 893 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | fmp4_perframe | ok | 69460961 | yes | yes | None / 893 | 893 (893) | 10/10 | FFMPEG (893) | 0 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_perframe | ok | 69460960 | yes | yes | None / 893 | 893 (893) | 10/10 | FFMPEG (893) | 0 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov | ok | 69354005 | yes | yes | 893 / 893 | 893 (893) | 10/10 | FFMPEG (893) | 893 | 893 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | mov | ok | 69347749 | yes | yes | 893 / 893 | 893 (893) | 10/10 | FFMPEG (893) | 893 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mov | ok | 69347748 | yes | yes | 893 / 893 | 893 (893) | 10/10 | FFMPEG (893) | 893 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | avi | ok | 69778092 | yes | yes | 17866 / 893 | 893 (17866) | 5/10 | FFMPEG (17866) | 17847 | 17866 / 2/4 | 830 | 830 | 830 | 0 |
| pyav/cfr | avi | ok | 69777948 | yes | yes | 17860 / 893 | 893 (17860) | 5/10 | FFMPEG (17860) | 17841 | 17860 / 2/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | avi | ok | 69370740 | yes | yes | 893 / 893 | 893 (893) | 10/10 | FFMPEG (893) | 893 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut | ok | 69373072 | yes | yes | None / 893 | 893 (892) | 10/10 | FFMPEG (892) | not opened | 892 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | nut | ok | 69373066 | yes | yes | None / 893 | 893 (892) | 10/10 | FFMPEG (892) | not opened | 892 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | nut | ok | 69372770 | yes | yes | None / 893 | 893 (892) | 10/10 | FFMPEG (892) | not opened | 892 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mjpeg_raw_mux | ok | 69343177 | yes | yes | None / 893 | 893 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 5936014 | 5936014 | 5935702 | 0 |
| pyav/cfr | mjpeg_raw_mux | ok | 69343177 | yes | yes | None / 893 | 893 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 5946667 | 5946667 | 5946354 | 0 |
| ffmpeg/cfr | mjpeg_raw_mux | ok | 69343177 | yes | yes | None / 893 | 893 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 5946667 | 5946667 | 5946354 | 0 |
| pyav/vfr | avi_tb_rate | ok | 69370740 | yes | yes | 893 / 893 | 893 (893) | 10/10 | FFMPEG (893) | 893 | 893 / 4/4 | 14672 | 14672 | 14672 | 0 |
| pyav/cfr | avi_tb_rate | ok | 69370740 | yes | yes | 893 / 893 | 893 (893) | 10/10 | FFMPEG (893) | 893 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mp4_tb_us | ok | 69354898 | yes | yes | 893 / 893 | 893 (893) | 10/10 | FFMPEG (893) | 0 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mp4_tb_us | ok | 69352594 | yes | yes | 893 / 893 | 893 (893) | 10/10 | FFMPEG (893) | 0 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov_tb_us | ok | 69354805 | yes | yes | 893 / 893 | 893 (893) | 10/10 | FFMPEG (893) | 893 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mov_tb_us | ok | 69352501 | yes | yes | 893 / 893 | 893 (893) | 10/10 | FFMPEG (893) | 893 | 893 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut_tb_us | ok | 69374607 | yes | yes | None / 893 | 893 (892) | 10/10 | FFMPEG (892) | not opened | 892 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | nut_tb_us | ok | 69374602 | yes | yes | None / 893 | 893 (892) | 10/10 | FFMPEG (892) | not opened | 892 / 4/4 | 0 | 0 | 0 | 0 |
| python/vfr | raw_sidecar | ok | 69343177 | yes | yes | None / 893 | 893 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | - | ERR ValidationError: 1 validation error for VideoMetad | 5936014 | 5936014 | 5935702 | 0 |
| python/vfr | jpg_folder | ok | 69343177 | yes | yes | None / 893 | 893 (893) | 10/10 | FFMPEG (893) | 893 | ERR FileNotFoundError: Video file not found: C:\Users\ | 5936014 | 5936014 | 5936014 | 0 |

## c922_1080p

| writer/mode | container | write | file bytes | bytes pyav | bytes ffx | ffprobe nb_frames / pkts | cv2 n (prop) | seek | ANY backend (prop) | MSMF n | FMC count / reads ok | ts err pyav | ts err ffprobe | ts err cv2 | pyav decode errs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pyav/vfr | mkv | ok | 3656573 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 53 | 53 | 53 | 0 |
| pyav/cfr | mkv | ok | 3656573 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 333 | 333 | 333 | 0 |
| ffmpeg/cfr | mkv | ok | 3656589 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 333 | 333 | 333 | 0 |
| pyav/vfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/cfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| ffmpeg/cfr | webm | FAIL: [out#0/webm @ 0000023d5d901340] Could not write header (incorrect codec parameters ?): Inv | 262 | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/vfr | mp4 | ok | 3656291 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | mp4 | ok | 3656163 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mp4 | ok | 3656162 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_1s | ok | 3656334 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | fmp4_1s | ok | 3656258 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_1s | ok | 3656257 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_perframe | ok | 3658544 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | fmp4_perframe | ok | 3658544 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_perframe | ok | 3658543 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov | ok | 3656198 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | mov | ok | 3656070 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mov | ok | 3656069 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | avi | ok | 3670194 | yes | yes | 385 / 19 | 19 (385) | 10/10 | FFMPEG (385) | 366 | 385 / 2/4 | 681 | 681 | 681 | 0 |
| pyav/cfr | avi | ok | 3670074 | yes | yes | 380 / 19 | 19 (380) | 10/10 | FFMPEG (380) | 361 | 380 / 2/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | avi | ok | 3661410 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut | ok | 3656116 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | nut | ok | 3656116 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | nut | ok | 3656111 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mjpeg_raw_mux | ok | 3655254 | yes | yes | None / 19 | 19 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 112022 | 112022 | 111749 | 0 |
| pyav/cfr | mjpeg_raw_mux | ok | 3655254 | yes | yes | None / 19 | 19 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 120000 | 120000 | 119727 | 0 |
| ffmpeg/cfr | mjpeg_raw_mux | ok | 3655254 | yes | yes | None / 19 | 19 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 120000 | 120000 | 119727 | 0 |
| pyav/vfr | avi_tb_rate | ok | 3661410 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 9346 | 9346 | 9346 | 0 |
| pyav/cfr | avi_tb_rate | ok | 3661410 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mp4_tb_us | ok | 3656307 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mp4_tb_us | ok | 3656259 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov_tb_us | ok | 3656214 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mov_tb_us | ok | 3656166 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut_tb_us | ok | 3656136 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | nut_tb_us | ok | 3656136 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 0 | 0 | 0 | 0 |
| python/vfr | raw_sidecar | ok | 3655254 | yes | yes | None / 19 | 19 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | - | ERR ValidationError: 1 validation error for VideoMetad | 112022 | 112022 | 111749 | 0 |
| python/vfr | jpg_folder | ok | 3655254 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | ERR FileNotFoundError: Video file not found: C:\Users\ | 112022 | 112022 | 112022 | 0 |

## c930e_1080p

| writer/mode | container | write | file bytes | bytes pyav | bytes ffx | ffprobe nb_frames / pkts | cv2 n (prop) | seek | ANY backend (prop) | MSMF n | FMC count / reads ok | ts err pyav | ts err ffprobe | ts err cv2 | pyav decode errs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pyav/vfr | mkv | ok | 2558233 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 53 | 53 | 53 | 0 |
| pyav/cfr | mkv | ok | 2558233 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 333 | 333 | 333 | 0 |
| ffmpeg/cfr | mkv | ok | 2558249 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 333 | 333 | 333 | 0 |
| pyav/vfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/cfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| ffmpeg/cfr | webm | FAIL: [out#0/webm @ 0000015325c750c0] Could not write header (incorrect codec parameters ?): Inv | 262 | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/vfr | mp4 | ok | 2557947 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | mp4 | ok | 2557819 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mp4 | ok | 2557818 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_1s | ok | 2557994 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | fmp4_1s | ok | 2557918 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_1s | ok | 2557917 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_perframe | ok | 2560204 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | fmp4_perframe | ok | 2560204 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_perframe | ok | 2560203 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov | ok | 2557854 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | mov | ok | 2557726 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mov | ok | 2557725 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | avi | ok | 2571848 | yes | yes | 385 / 19 | 19 (385) | 10/10 | FFMPEG (385) | 366 | 385 / 2/4 | 681 | 681 | 681 | 0 |
| pyav/cfr | avi | ok | 2571728 | yes | yes | 380 / 19 | 19 (380) | 10/10 | FFMPEG (380) | 361 | 380 / 2/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | avi | ok | 2563064 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut | ok | 2557776 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | nut | ok | 2557776 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | nut | ok | 2557771 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mjpeg_raw_mux | ok | 2556914 | yes | yes | None / 19 | 19 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 112022 | 112022 | 111749 | 0 |
| pyav/cfr | mjpeg_raw_mux | ok | 2556914 | yes | yes | None / 19 | 19 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 120000 | 120000 | 119727 | 0 |
| ffmpeg/cfr | mjpeg_raw_mux | ok | 2556914 | yes | yes | None / 19 | 19 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 120000 | 120000 | 119727 | 0 |
| pyav/vfr | avi_tb_rate | ok | 2563064 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 9346 | 9346 | 9346 | 0 |
| pyav/cfr | avi_tb_rate | ok | 2563064 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mp4_tb_us | ok | 2557963 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mp4_tb_us | ok | 2557915 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov_tb_us | ok | 2557870 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mov_tb_us | ok | 2557822 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut_tb_us | ok | 2557796 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | nut_tb_us | ok | 2557796 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 0 | 0 | 0 | 0 |
| python/vfr | raw_sidecar | ok | 2556914 | yes | yes | None / 19 | 19 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | - | ERR ValidationError: 1 validation error for VideoMetad | 112022 | 112022 | 111749 | 0 |
| python/vfr | jpg_folder | ok | 2556914 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | ERR FileNotFoundError: Video file not found: C:\Users\ | 112022 | 112022 | 112022 | 0 |

## c922_1600x896

| writer/mode | container | write | file bytes | bytes pyav | bytes ffx | ffprobe nb_frames / pkts | cv2 n (prop) | seek | ANY backend (prop) | MSMF n | FMC count / reads ok | ts err pyav | ts err ffprobe | ts err cv2 | pyav decode errs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pyav/vfr | mkv | ok | 2777359 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 53 | 53 | 53 | 0 |
| pyav/cfr | mkv | ok | 2777359 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 333 | 333 | 333 | 0 |
| ffmpeg/cfr | mkv | ok | 2777375 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 333 | 333 | 333 | 0 |
| pyav/vfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/cfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| ffmpeg/cfr | webm | FAIL: [out#0/webm @ 000002621d426600] Could not write header (incorrect codec parameters ?): Inv | 262 | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/vfr | mp4 | ok | 2777073 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | mp4 | ok | 2776945 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mp4 | ok | 2776944 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_1s | ok | 2777120 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | fmp4_1s | ok | 2777044 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_1s | ok | 2777043 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_perframe | ok | 2779330 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | fmp4_perframe | ok | 2779330 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_perframe | ok | 2779329 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov | ok | 2776980 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | mov | ok | 2776852 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mov | ok | 2776851 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | avi | ok | 2790972 | yes | yes | 385 / 19 | 19 (385) | 10/10 | FFMPEG (385) | 366 | 385 / 2/4 | 681 | 681 | 681 | 0 |
| pyav/cfr | avi | ok | 2790852 | yes | yes | 380 / 19 | 19 (380) | 10/10 | FFMPEG (380) | 361 | 380 / 2/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | avi | ok | 2782188 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut | ok | 2776902 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | nut | ok | 2776902 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | nut | ok | 2776897 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mjpeg_raw_mux | ok | 2776040 | yes | yes | None / 19 | 19 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 112022 | 112022 | 111749 | 0 |
| pyav/cfr | mjpeg_raw_mux | ok | 2776040 | yes | yes | None / 19 | 19 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 120000 | 120000 | 119727 | 0 |
| ffmpeg/cfr | mjpeg_raw_mux | ok | 2776040 | yes | yes | None / 19 | 19 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 120000 | 120000 | 119727 | 0 |
| pyav/vfr | avi_tb_rate | ok | 2782188 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 9346 | 9346 | 9346 | 0 |
| pyav/cfr | avi_tb_rate | ok | 2782188 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mp4_tb_us | ok | 2777089 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mp4_tb_us | ok | 2777041 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 0 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov_tb_us | ok | 2776996 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mov_tb_us | ok | 2776948 | yes | yes | 19 / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | 19 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut_tb_us | ok | 2776922 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | nut_tb_us | ok | 2776922 | yes | yes | None / 19 | 19 (18) | 10/10 | FFMPEG (18) | not opened | 18 / 4/4 | 0 | 0 | 0 | 0 |
| python/vfr | raw_sidecar | ok | 2776040 | yes | yes | None / 19 | 19 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | - | ERR ValidationError: 1 validation error for VideoMetad | 112022 | 112022 | 111749 | 0 |
| python/vfr | jpg_folder | ok | 2776040 | yes | yes | None / 19 | 19 (19) | 10/10 | FFMPEG (19) | 19 | ERR FileNotFoundError: Video file not found: C:\Users\ | 112022 | 112022 | 112022 | 0 |

## c922_720p60

| writer/mode | container | write | file bytes | bytes pyav | bytes ffx | ffprobe nb_frames / pkts | cv2 n (prop) | seek | ANY backend (prop) | MSMF n | FMC count / reads ok | ts err pyav | ts err ffprobe | ts err cv2 | pyav decode errs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pyav/vfr | mkv | ok | 807667 | yes | yes | None / 10 | 10 (10) | 10/10 | FFMPEG (10) | 10 | 10 / 4/4 | 26 | 26 | 26 | 0 |
| pyav/cfr | mkv | ok | 807667 | yes | yes | None / 10 | 10 (10) | 10/10 | FFMPEG (10) | 10 | 10 / 4/4 | 333 | 333 | 333 | 0 |
| ffmpeg/cfr | mkv | ok | 807683 | yes | yes | None / 10 | 10 (10) | 10/10 | FFMPEG (10) | 10 | 10 / 4/4 | 333 | 333 | 333 | 0 |
| pyav/vfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/cfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| ffmpeg/cfr | webm | FAIL: [out#0/webm @ 000001bd2cd52a00] Could not write header (incorrect codec parameters ?): Inv | 262 | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/vfr | mp4 | ok | 807662 | yes | yes | 10 / 10 | 10 (10) | 10/10 | FFMPEG (10) | 0 | 10 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | mp4 | ok | 807598 | yes | yes | 10 / 10 | 10 (10) | 10/10 | FFMPEG (10) | 0 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mp4 | ok | 807597 | yes | yes | 10 / 10 | 10 (10) | 10/10 | FFMPEG (10) | 0 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_1s | ok | 807757 | yes | yes | None / 10 | 10 (10) | 10/10 | FFMPEG (10) | 0 | 10 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | fmp4_1s | ok | 807717 | yes | yes | None / 10 | 10 (10) | 10/10 | FFMPEG (10) | 0 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_1s | ok | 807716 | yes | yes | None / 10 | 10 (10) | 10/10 | FFMPEG (10) | 0 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_perframe | ok | 808860 | yes | yes | None / 10 | 10 (10) | 10/10 | FFMPEG (10) | 0 | 10 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | fmp4_perframe | ok | 808860 | yes | yes | None / 10 | 10 (10) | 10/10 | FFMPEG (10) | 0 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_perframe | ok | 808859 | yes | yes | None / 10 | 10 (10) | 10/10 | FFMPEG (10) | 0 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov | ok | 807569 | yes | yes | 10 / 10 | 10 (10) | 10/10 | FFMPEG (10) | 10 | 10 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | mov | ok | 807505 | yes | yes | 10 / 10 | 10 (10) | 10/10 | FFMPEG (10) | 10 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mov | ok | 807504 | yes | yes | 10 / 10 | 10 (10) | 10/10 | FFMPEG (10) | 10 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | avi | ok | 814864 | yes | yes | 101 / 10 | 10 (101) | 10/10 | FFMPEG (101) | 92 | 101 / 2/4 | 668 | 668 | 668 | 0 |
| pyav/cfr | avi | ok | 814840 | yes | yes | 100 / 10 | 10 (100) | 10/10 | FFMPEG (100) | 91 | 100 / 2/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | avi | ok | 812680 | yes | yes | 10 / 10 | 10 (10) | 10/10 | FFMPEG (10) | 10 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut | ok | 807309 | yes | yes | None / 10 | 10 (9) | 10/10 | FFMPEG (9) | not opened | 9 / 4/4 | 5 | 5 | 5 | 0 |
| pyav/cfr | nut | ok | 807309 | yes | yes | None / 10 | 10 (9) | 10/10 | FFMPEG (9) | not opened | 9 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | nut | ok | 807308 | yes | yes | None / 10 | 10 (9) | 10/10 | FFMPEG (9) | not opened | 9 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mjpeg_raw_mux | ok | 806749 | yes | yes | None / 10 | 10 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 208012 | 208012 | 208364 | 0 |
| pyav/cfr | mjpeg_raw_mux | ok | 806749 | yes | yes | None / 10 | 10 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 210000 | 210000 | 210352 | 0 |
| ffmpeg/cfr | mjpeg_raw_mux | ok | 806749 | yes | yes | None / 10 | 10 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 210000 | 210000 | 210352 | 0 |
| pyav/vfr | avi_tb_rate | ok | 812680 | yes | yes | 10 / 10 | 10 (10) | 10/10 | FFMPEG (10) | 10 | 10 / 4/4 | 4660 | 4660 | 4660 | 0 |
| pyav/cfr | avi_tb_rate | ok | 812680 | yes | yes | 10 / 10 | 10 (10) | 10/10 | FFMPEG (10) | 10 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mp4_tb_us | ok | 807670 | yes | yes | 10 / 10 | 10 (10) | 10/10 | FFMPEG (10) | 0 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mp4_tb_us | ok | 807646 | yes | yes | 10 / 10 | 10 (10) | 10/10 | FFMPEG (10) | 0 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov_tb_us | ok | 807577 | yes | yes | 10 / 10 | 10 (10) | 10/10 | FFMPEG (10) | 10 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mov_tb_us | ok | 807553 | yes | yes | 10 / 10 | 10 (10) | 10/10 | FFMPEG (10) | 10 | 10 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut_tb_us | ok | 807317 | yes | yes | None / 10 | 10 (9) | 10/10 | FFMPEG (9) | not opened | 9 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | nut_tb_us | ok | 807325 | yes | yes | None / 10 | 10 (9) | 10/10 | FFMPEG (9) | not opened | 9 / 4/4 | 0 | 0 | 0 | 0 |
| python/vfr | raw_sidecar | ok | 806749 | yes | yes | None / 10 | 10 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | - | ERR ValidationError: 1 validation error for VideoMetad | 208012 | 208012 | 208364 | 0 |
| python/vfr | jpg_folder | ok | 806749 | yes | yes | None / 10 | 10 (10) | 10/10 | FFMPEG (10) | 10 | ERR FileNotFoundError: Video file not found: C:\Users\ | 208012 | 208012 | 208012 | 0 |

## generic_1080p

| writer/mode | container | write | file bytes | bytes pyav | bytes ffx | ffprobe nb_frames / pkts | cv2 n (prop) | seek | ANY backend (prop) | MSMF n | FMC count / reads ok | ts err pyav | ts err ffprobe | ts err cv2 | pyav decode errs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pyav/vfr | mkv | ok | 793447 | yes | yes | None / 11 | 11 (11) | 10/10 | FFMPEG (11) | 11 | 11 / 4/4 | 53 | 53 | 53 | 0 |
| pyav/cfr | mkv | ok | 793447 | yes | yes | None / 11 | 11 (11) | 10/10 | FFMPEG (11) | 11 | 11 / 4/4 | 333 | 333 | 333 | 0 |
| ffmpeg/cfr | mkv | ok | 793459 | yes | yes | None / 11 | 11 (11) | 10/10 | FFMPEG (11) | 11 | 11 / 4/4 | 333 | 333 | 333 | 0 |
| pyav/vfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/cfr | webm | FAIL: ValueError: 'webm' format does not support 'mjpeg' codec | None | - | - | - | - | - | - | - | - | - | - | - | - |
| ffmpeg/cfr | webm | FAIL: [out#0/webm @ 000001c3d41c1200] Could not write header (incorrect codec parameters ?): Inv | 262 | - | - | - | - | - | - | - | - | - | - | - | - |
| pyav/vfr | mp4 | ok | 793398 | yes | yes | 11 / 11 | 11 (11) | 10/10 | FFMPEG (11) | 0 | 11 / 4/4 | 4 | 4 | 4 | 0 |
| pyav/cfr | mp4 | ok | 793334 | yes | yes | 11 / 11 | 11 (11) | 10/10 | FFMPEG (11) | 0 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mp4 | ok | 793349 | yes | yes | 11 / 11 | 11 (11) | 10/10 | FFMPEG (11) | 0 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_1s | ok | 793497 | yes | yes | None / 11 | 11 (11) | 10/10 | FFMPEG (11) | 0 | 11 / 4/4 | 4 | 4 | 4 | 0 |
| pyav/cfr | fmp4_1s | ok | 793453 | yes | yes | None / 11 | 11 (11) | 10/10 | FFMPEG (11) | 0 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_1s | ok | 793468 | yes | yes | None / 11 | 11 (11) | 10/10 | FFMPEG (11) | 0 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | fmp4_perframe | ok | 794723 | yes | yes | None / 11 | 11 (11) | 10/10 | FFMPEG (11) | 0 | 11 / 4/4 | 4 | 4 | 4 | 0 |
| pyav/cfr | fmp4_perframe | ok | 794723 | yes | yes | None / 11 | 11 (11) | 10/10 | FFMPEG (11) | 0 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | fmp4_perframe | ok | 794738 | yes | yes | None / 11 | 11 (11) | 10/10 | FFMPEG (11) | 0 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov | ok | 793305 | yes | yes | 11 / 11 | 11 (11) | 10/10 | FFMPEG (11) | 11 | 11 / 4/4 | 4 | 4 | 4 | 0 |
| pyav/cfr | mov | ok | 793241 | yes | yes | 11 / 11 | 11 (11) | 10/10 | FFMPEG (11) | 11 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | mov | ok | 793256 | yes | yes | 11 / 11 | 11 (11) | 10/10 | FFMPEG (11) | 11 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | avi | ok | 803500 | yes | yes | 222 / 11 | 11 (222) | 10/10 | FFMPEG (222) | 203 | 222 / 2/4 | 681 | 681 | 681 | 0 |
| pyav/cfr | avi | ok | 803452 | yes | yes | 220 / 11 | 11 (220) | 10/10 | FFMPEG (220) | 201 | 220 / 2/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | avi | ok | 798512 | yes | yes | 11 / 11 | 11 (11) | 10/10 | FFMPEG (11) | 11 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut | ok | 793049 | yes | yes | None / 11 | 11 (10) | 10/10 | FFMPEG (10) | not opened | 10 / 4/4 | 4 | 4 | 4 | 0 |
| pyav/cfr | nut | ok | 793049 | yes | yes | None / 11 | 11 (10) | 10/10 | FFMPEG (10) | not opened | 10 / 4/4 | 0 | 0 | 0 | 0 |
| ffmpeg/cfr | nut | ok | 793045 | yes | yes | None / 11 | 11 (10) | 10/10 | FFMPEG (10) | not opened | 10 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mjpeg_raw_mux | ok | 792481 | yes | yes | None / 11 | 11 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 63992 | 63992 | 64383 | 0 |
| pyav/cfr | mjpeg_raw_mux | ok | 792481 | yes | yes | None / 11 | 11 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 66667 | 66667 | 67057 | 0 |
| ffmpeg/cfr | mjpeg_raw_mux | ok | 792481 | yes | yes | None / 11 | 11 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | not opened | ERR ValidationError: 1 validation error for VideoMetad | 66667 | 66667 | 67057 | 0 |
| pyav/vfr | avi_tb_rate | ok | 798436 | yes | yes | 11 / 11 | 11 (11) | 10/10 | FFMPEG (11) | 11 | 11 / 4/4 | 9319 | 9319 | 9319 | 0 |
| pyav/cfr | avi_tb_rate | ok | 798436 | yes | yes | 11 / 11 | 11 (11) | 10/10 | FFMPEG (11) | 11 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mp4_tb_us | ok | 793414 | yes | yes | 11 / 11 | 11 (11) | 10/10 | FFMPEG (11) | 0 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mp4_tb_us | ok | 793382 | yes | yes | 11 / 11 | 11 (11) | 10/10 | FFMPEG (11) | 0 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | mov_tb_us | ok | 793321 | yes | yes | 11 / 11 | 11 (11) | 10/10 | FFMPEG (11) | 11 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | mov_tb_us | ok | 793289 | yes | yes | 11 / 11 | 11 (11) | 10/10 | FFMPEG (11) | 11 | 11 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/vfr | nut_tb_us | ok | 793061 | yes | yes | None / 11 | 11 (10) | 10/10 | FFMPEG (10) | not opened | 10 / 4/4 | 0 | 0 | 0 | 0 |
| pyav/cfr | nut_tb_us | ok | 793061 | yes | yes | None / 11 | 11 (10) | 10/10 | FFMPEG (10) | not opened | 10 / 4/4 | 0 | 0 | 0 | 0 |
| python/vfr | raw_sidecar | ok | 792481 | yes | yes | None / 11 | 11 (-192153584101141) | 0/10 | FFMPEG (-192153584101141) | - | ERR ValidationError: 1 validation error for VideoMetad | 63992 | 63992 | 64383 | 0 |
| python/vfr | jpg_folder | ok | 792481 | yes | yes | None / 11 | 11 (11) | 10/10 | FFMPEG (11) | 11 | ERR FileNotFoundError: Video file not found: C:\Users\ | 63992 | 63992 | 63992 | 0 |

