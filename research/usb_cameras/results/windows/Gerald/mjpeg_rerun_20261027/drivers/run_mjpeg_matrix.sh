#!/usr/bin/env bash
# 2026-10-27 overnight rerun of the goal-1 Windows matrix (C922, C930e, generic 4C4A:4A55; Kiyo excluded).
cd /c/Users/Dom/GitHub/freemocap/skellycam
export MJPEG_SCRATCH="C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad/runs"
ROOT=research/usb_cameras/results/windows/Gerald/mjpeg_rerun_20261027
RM="uv run --script research/usb_cameras/mjpeg/run_matrix.py --root $ROOT"
$RM --backend msmf --backend pyav-dshow --modes common,max --sets single,all
$RM --backend winrt --backend opencv-dshow-decode --backend opencv-msmf-decode --modes common,max --sets single,all
$RM --backend opencv-msmf-raw --backend opencv-dshow-raw --modes common --sets single,all
$RM --backend msmf-decoded-nv12 --modes common --sets single
echo MATRIX_DONE
