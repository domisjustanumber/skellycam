#!/bin/bash
B=/c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/runs/phase2/bin
O=/c/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/results/windows/Gerald/phase2_bw_alt/probe_quality
for m in "1280 720" "1920 1080" "640 480"; do set -- $m
  $B/uvc_probe_quality.exe --vid 046d --pid 0843 --width $1 --height $2 --fps 30 --exposure-abs 156 --wb-temp 4000     --quality-list 0,1,10,30,50,61,100,1000,5000,9999,10000,65535 --payload-list 192,512,944,1600,1984,3072 --out $O/probe_${1}x${2}.json; echo "probe $1x$2 rc=$?"
done
$B/uvc_probe_quality.exe --vid 046d --pid 0843 --width 1280 --height 720 --fps 30 --exposure-abs 156 --wb-temp 4000 --stream-q 61,1,10000,61 --seconds 6 --out $O/stream_q_1280x720.json; echo "stream rc=$?"
