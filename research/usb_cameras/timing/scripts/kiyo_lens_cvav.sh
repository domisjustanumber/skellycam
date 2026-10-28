#!/usr/bin/env bash
# OpenCV MSMF/DSHOW + PyAV dshow attempts (Kiyo two modes, C922 control). Run under camlock. UV=<path to uv> if not on PATH.
o="$1"; h="$(dirname "$0")"; mkdir -p "$o"; UV="${UV:-uv}"
"$UV" run --script "$h/kiyo_lens_cv_av.py" --out "$o/cv_av_kiyo.json" --cam 'vid_1532&pid_0e05' --mode 1280x720@30 --mode 640x480@30 --seconds 2 2> "$o/cv_av_kiyo.stderr.txt"
"$UV" run --script "$h/kiyo_lens_cv_av.py" --out "$o/cv_av_c922.json" --cam 'vid_046d&pid_085c' --mode 1280x720@30 --seconds 2 2> "$o/cv_av_c922.stderr.txt"
