#!/usr/bin/env bash
# Phase 4: does OpenCV MSMF reach 30 fps on the generic 4C4A:4A55 camera (vs 25.7 fps on every native-MJPG path) by
# repeating frames? opencv_capture.py now logs a per-frame CRC of a 1/4-subsampled image (frames_identical_to_previous).
# Control: OpenCV DSHOW decode on the same camera.
cd /c/Users/Dom/GitHub/freemocap/skellycam
export MJPEG_SCRATCH="C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad/runs"
until grep -aq PHASE3_DONE "C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad/matrix3_log.txt"; do sleep 5; done
ROOT=research/usb_cameras/results/windows/Gerald/mjpeg_rerun_20261027
uv run --script research/usb_cameras/mjpeg/run_matrix.py --root $ROOT --backend opencv-msmf-decode --backend opencv-dshow-decode --modes common,max --sets single --cams usbcam --label-suffix _duphash --capture-timeout-s 150
echo PHASE4_DONE $(date)
