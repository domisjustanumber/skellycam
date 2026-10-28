#!/usr/bin/env bash
# Phase 2 of the 2026-10-27 rerun, re-prioritized because the camera lock is shared by ~5 agents.
# Waits for the phase-1 run_matrix (msmf + pyav-dshow) to finish, then runs the remaining cells most-important first.
cd /c/Users/Dom/GitHub/freemocap/skellycam
export MJPEG_SCRATCH="C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad/runs"
while tasklist //FI "PID eq 45288" | grep -q 45288; do sleep 5; done
echo PHASE1_DONE $(date)
ROOT=research/usb_cameras/results/windows/Gerald/mjpeg_rerun_20261027
RM="uv run --script research/usb_cameras/mjpeg/run_matrix.py --root $ROOT"
$RM --backend winrt --backend opencv-dshow-decode --modes common --sets single,all
$RM --backend opencv-msmf-raw --backend opencv-msmf-decode --backend opencv-dshow-raw --modes common --sets single
$RM --backend opencv-dshow-decode --backend winrt --modes max --sets single,all
$RM --backend opencv-msmf-raw --backend opencv-msmf-decode --modes common --sets all
$RM --backend msmf-decoded-nv12 --modes common --sets single
$RM --backend opencv-msmf-decode --modes max --sets single,all
echo MATRIX_DONE $(date)
