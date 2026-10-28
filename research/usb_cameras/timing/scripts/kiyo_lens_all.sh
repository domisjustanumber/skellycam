#!/usr/bin/env bash
# One camlock hold (~2.5 min): KS GET probe, MF per-stage matrix, OpenCV MSMF/DSHOW + PyAV dshow.
# usage (from repo root): uv run --script research/usb_cameras/tools/camlock.py -- bash research/usb_cameras/timing/scripts/kiyo_lens_all.sh <outdir>
o="$1"; h="$(dirname "$0")"; mkdir -p "$o"
date -Is > "$o/all.times.txt"
for d in 'vid_1532&pid_0e05' 'vid_046d&pid_085c'; do "$h/../build/kiyo_ks_mf_probe.exe" --dev "$d" --ks-only >> "$o/ks.jsonl"; done
bash "$h/kiyo_lens_mf.sh" "$o/mf.jsonl" 2
date -Is >> "$o/all.times.txt"
"${UV:-uv}" run --script "$h/kiyo_lens_cv_av.py" --out "$o/cv_av_kiyo.json" --cam 'vid_1532&pid_0e05' --mode 1280x720@30 --mode 640x480@30 --seconds 2 2> "$o/cv_av_kiyo.stderr.txt"
"${UV:-uv}" run --script "$h/kiyo_lens_cv_av.py" --out "$o/cv_av_c922.json" --cam 'vid_046d&pid_085c' --mode 1280x720@30 --seconds 2 2> "$o/cv_av_c922.stderr.txt"
date -Is >> "$o/all.times.txt"
