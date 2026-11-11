#!/usr/bin/env bash
# Generate tiny synthetic (testsrc2, no camera content) sample files, one per codec/container,
# for the Electron/Chrome playback-capability probe. Requires ffmpeg on PATH (tested: 9.0.2 gyan full).
# Usage: bash make_codec_samples.sh <out_dir>
set -u
OUT="${1:?out dir}"; mkdir -p "$OUT"
SRC="-f lavfi -i testsrc2=size=320x240:rate=30 -t 2"
AUD="-f lavfi -i sine=frequency=440:sample_rate=48000 -t 2"
run() { local name="$1"; shift; if ffmpeg -hide_banner -loglevel error -y "$@" "$OUT/$name"; then echo "ok   $name"; else echo "FAIL $name"; fi; }
run h264_libx264.mp4        $SRC -c:v libx264 -pix_fmt yuv420p
run hevc_libx265.mp4        $SRC -c:v libx265 -pix_fmt yuv420p -tag:v hvc1
run av1_svt.mp4             $SRC -c:v libsvtav1 -pix_fmt yuv420p
run av1_svt.webm            $SRC -c:v libsvtav1 -pix_fmt yuv420p
run av1_svt.mkv             $SRC -c:v libsvtav1 -pix_fmt yuv420p
run vp9.webm                $SRC -c:v libvpx-vp9 -pix_fmt yuv420p
run vp9.mp4                 $SRC -c:v libvpx-vp9 -pix_fmt yuv420p
run vp8.webm                $SRC -c:v libvpx -pix_fmt yuv420p
run mjpeg.mkv               $SRC -c:v mjpeg -pix_fmt yuvj422p
run mjpeg.avi               $SRC -c:v mjpeg -pix_fmt yuvj422p
run mjpeg.mp4               $SRC -c:v mjpeg -pix_fmt yuvj422p
run ffv1.mkv                $SRC -c:v ffv1 -pix_fmt yuv420p
run prores.mov              $SRC -c:v prores_ks -pix_fmt yuv422p10le
run utvideo.avi             $SRC -c:v utvideo -pix_fmt yuv422p
run opus.webm               $AUD -c:a libopus
run opus.mp4                $AUD -c:a libopus
run flac.flac               $AUD -c:a flac
run flac.mp4                $AUD -c:a flac
run aac.m4a                 $AUD -c:a aac
run pcm.wav                 $AUD -c:a pcm_s16le
run mp3.mp3                 $AUD -c:a libmp3lame
# still images for ImageDecoder / <img>
run still.jpg  -f lavfi -i testsrc2=size=320x240 -frames:v 1 -c:v mjpeg -pix_fmt yuvj422p
run still.jxl  -f lavfi -i testsrc2=size=320x240 -frames:v 1 -c:v libjxl
run still.avif -f lavfi -i testsrc2=size=320x240 -frames:v 1 -c:v libsvtav1 -pix_fmt yuv420p
run still.webp -f lavfi -i testsrc2=size=320x240 -frames:v 1 -c:v libwebp
run still.png  -f lavfi -i testsrc2=size=320x240 -frames:v 1
run still.jp2  -f lavfi -i testsrc2=size=320x240 -frames:v 1 -c:v jpeg2000
