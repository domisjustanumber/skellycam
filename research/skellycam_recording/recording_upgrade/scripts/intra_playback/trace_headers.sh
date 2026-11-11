#!/usr/bin/env bash
# Inspection only (ffmpeg 9.0.2 CLI on PATH, trace_headers bitstream filter): the parameter-set fields that decide
# whether a decoder may hold a decoded intra frame back (H.264 VUI bitstream_restriction / max_num_reorder_frames /
# max_dec_frame_buffering; HEVC sps_max_num_reorder_pics / sps_max_dec_pic_buffering_minus1 / sps_max_latency_increase_plus1).
# Usage (repo root): bash research/skellycam_recording/recording_upgrade/scripts/intra_playback/trace_headers.sh > research/skellycam_recording/recording_upgrade/results/intra_playback/sps_vui_trace.txt
M=C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/intra_playback/clips
ffmpeg -hide_banner -version | head -1
for c in c720p30 c1080p30; do
  for e in h264_nvenc h264_qsv hevc_nvenc hevc_qsv; do
    f=$M/$c/${e}_intra.mp4
    echo "== $c/${e}_intra.mp4"
    ffmpeg -hide_banner -v info -i "$f" -frames:v 1 -c copy -bsf:v trace_headers -f null - 2>&1 \
      | grep -E " (profile_idc|general_profile_idc|level_idc|general_level_idc|vui_parameters_present_flag|bitstream_restriction_flag|max_num_reorder_frames|max_dec_frame_buffering|sps_max_dec_pic_buffering_minus1\[0\]|sps_max_num_reorder_pics\[0\]|sps_max_latency_increase_plus1\[0\]|vps_max_num_reorder_pics\[0\]|nal_unit_type) " \
      | sed -E 's/^\[trace_headers @ [0-9a-f]+\] *//' | awk '!seen[$0]++'
  done
done
