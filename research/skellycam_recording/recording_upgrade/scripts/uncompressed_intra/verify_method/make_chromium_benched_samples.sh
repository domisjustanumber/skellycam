#!/usr/bin/env bash
# Samples matching the BENCHED archive configs (8 real C930e 1080p YUY2 frames), then the study's harness:
#   env -u ELECTRON_RUN_AS_NODE <electron.exe> scripts/uncompressed_intra/chromium_check/main.js $D/manifest.json <out.json>
# The manifest is results/uncompressed_intra/verify_method/chromium_benched_configs_manifest.json (copy it to $D).
D=C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/verify_method
C=C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus/c930e_1080p_yuy2
cd "$D" && cat $C/frame_*.yuy2 > in8.yuy2
I="-f rawvideo -pix_fmt yuyv422 -s 1920x1080 -r 30 -i in8.yuy2"
ffmpeg -hide_banner -loglevel error -y $I -c:v libx264 -g 1 -qp 0 -pix_fmt yuv422p x264_qp0_422.mkv
ffmpeg -hide_banner -loglevel error -y $I -c:v libx264 -g 1 -qp 0 -pix_fmt yuv422p x264_qp0_422.mp4
ffmpeg -hide_banner -loglevel error -y $I -c:v libx264 -g 1 -qp 0 -pix_fmt yuv420p x264_qp0_420.mkv
ffmpeg -hide_banner -loglevel error -y $I -c:v libx265 -x265-params keyint=1:lossless=1:log-level=error -pix_fmt yuv422p -tag:v hvc1 x265_lossless_422.mp4
ffmpeg -hide_banner -loglevel error -y $I -c:v libx265 -x265-params keyint=1:lossless=1:log-level=error -pix_fmt yuv420p -tag:v hvc1 x265_lossless_420.mp4
ffmpeg -hide_banner -loglevel error -y $I -c:v libsvtav1 -preset 10 -svtav1-params keyint=1:lossless=1 -pix_fmt yuv420p svt_lossless_420.mkv
ffmpeg -hide_banner -loglevel error -y $I -c:v libvpx-vp9 -lossless 1 -g 1 -deadline realtime -cpu-used 8 -pix_fmt yuv422p vp9_lossless_422.mkv
ffmpeg -hide_banner -loglevel error -y $I -c:v libx264 -g 1 -qp 0 -pix_fmt yuv420p -color_range tv -colorspace bt470bg -color_primaries bt470bg -color_trc smpte170m x264_qp0_420_bt601tag.mp4
for f in x264_qp0_422.mkv x264_qp0_422.mp4 x264_qp0_420.mkv x265_lossless_422.mp4 x265_lossless_420.mp4 svt_lossless_420.mkv vp9_lossless_422.mkv x264_qp0_420_bt601tag.mp4; do
  echo "$f $(ffprobe -v error -select_streams v -show_entries stream=codec_name,profile,pix_fmt,color_space -of csv=p=0 $f)"; done
