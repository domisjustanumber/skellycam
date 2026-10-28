#!/usr/bin/env bash
# Phase 3 of the 2026-10-27 rerun: after phase 2 finishes, re-run the OpenCV MSMF single-camera cells whose 10 s window
# started mid-open (old fixed 30 s open wait; opens take ~40 s), with --open-wait 90 (new label suffix, earlier cells kept),
# then WinRT reader variants on the C930e and the generic camera (10-25 covered only the C922).
cd /c/Users/Dom/GitHub/freemocap/skellycam
export MJPEG_SCRATCH="C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad/runs"
until grep -aq MATRIX_DONE "C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad/matrix2_log.txt"; do sleep 5; done
echo PHASE2_DONE $(date)
ROOT=research/usb_cameras/results/windows/Gerald/mjpeg_rerun_20261027
uv run --script research/usb_cameras/mjpeg/run_matrix.py --root $ROOT --backend opencv-msmf-decode --backend opencv-msmf-raw --modes common --sets single --cams c922,c930e --label-suffix _openwait90 --capture-timeout-s 150
for d in "vid_046d&pid_0843" "vid_4c4a&pid_4a55"; do bash research/usb_cameras/mjpeg/winrt/run_winrt_variants.sh "$d" 4 $ROOT; done
echo PHASE3_DONE $(date)
