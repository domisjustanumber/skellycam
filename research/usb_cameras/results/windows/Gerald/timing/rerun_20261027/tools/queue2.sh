#!/bin/bash
cd /c/Users/Dom/GitHub/freemocap/skellycam
T="/c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad/tools/flashrun.sh"
SPW='C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad/runs/timing_rerun'
EXE='C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\timing\build\mf_uvc_timing.exe'
"$T" flash_c922_c930e_exp-9 'vid_046d&pid_085c,1280,720,30,-9,4500;vid_046d&pid_0843,1280,720,30,-9,4500'
"$T" flash_c922_c930e_exp-6 'vid_046d&pid_085c,1280,720,30,-6,4500;vid_046d&pid_0843,1280,720,30,-6,4500'
# order test: auto-exposure session on the C930e, then two manual -7 flash runs
TS=$(date -u +%Y%m%dT%H%M%SZ); D="$SPW/${TS}_order_ae_c930e"
timeout 900 uv run --script research/usb_cameras/tools/camlock.py --timeout-s 800 -- "$EXE" --out "$D" --seconds 6 --save-mjpeg --cam "vid_046d&pid_0843,1280,720,30" > "$D.stdout.txt" 2>&1; echo "exit=$?" >> "$D.stdout.txt"
"$T" flash_c922_c930e_exp-7_c_afterAE 'vid_046d&pid_085c,1280,720,30,-7,4500;vid_046d&pid_0843,1280,720,30,-7,4500'
"$T" flash_c922_c930e_exp-7_d 'vid_046d&pid_085c,1280,720,30,-7,4500;vid_046d&pid_0843,1280,720,30,-7,4500'
TS=$(date -u +%Y%m%dT%H%M%SZ); D="$SPW/${TS}_dshow_probe"
timeout 900 uv run --script research/usb_cameras/tools/camlock.py --timeout-s 800 -- pwsh -NoProfile -File 'C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\timing\rerun_20261027\tools\dshow_probe_all.ps1' -Out "$D.jsonl" > "$D.stdout.txt" 2>&1; echo "exit=$?" >> "$D.stdout.txt"
echo queue2 done
