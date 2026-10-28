#!/usr/bin/env bash
# MF Source Reader per-stage HRESULT matrix (timing/build/kiyo_ks_mf_probe.exe). Run under camlock; ~60 s total.
# usage: bash kiyo_lens_mf.sh <out.jsonl> [seconds_per_attempt]
E="$(dirname "$0")/../build/kiyo_ks_mf_probe.exe"; out="$1"; s="${2:-2}"
K='vid_1532&pid_0e05'
for m in "MJPG 1280 720 30" "MJPG 1280 720 60" "MJPG 640 480 30" "MJPG 640 360 30" "MJPG 1920 1080 30" "MJPG 1920 1080 60" "YUY2 640 480 30" "NV12 640 480 30" "H264 1280 720 30"; do
  set -- $m; "$E" --dev "$K" --sub $1 --w $2 --h $3 --fps $4 --seconds "$s" --mf-only >> "$out"
done
"$E" --dev "$K" --sub MJPG --w 1280 --h 720 --fps 30 --seconds "$s" --mf-only --no-controls >> "$out"
for d in 'vid_046d&pid_085c' 'vid_046d&pid_0843'; do "$E" --dev "$d" --sub MJPG --w 1280 --h 720 --fps 30 --seconds 3 >> "$out"; done
"$E" --dev "$K" --ks-only >> "$out"
