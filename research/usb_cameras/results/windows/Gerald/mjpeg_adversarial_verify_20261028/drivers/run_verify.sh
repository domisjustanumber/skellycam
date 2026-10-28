#!/usr/bin/env bash
# Adversarial verification of the mjpeg 20261027 rerun (Kiyo excluded: explicit --cams everywhere).
cd /c/Users/Dom/GitHub/freemocap/skellycam
export MJPEG_SCRATCH="C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad/runs"
ROOT=research/usb_cameras/results/windows/Gerald/mjpeg_adversarial_verify_20261028
RM="uv run --script research/usb_cameras/mjpeg/run_matrix.py --root $ROOT"
date -u; $RM --backend msmf --backend pyav-dshow --modes common --sets single --cams c922,usbcam
date -u; $RM --backend msmf --modes common --sets all --cams c922,c930e,usbcam
date -u; $RM --backend opencv-msmf-decode --modes common --sets single --cams usbcam --label-suffix _duphash --capture-timeout-s 150
date -u; $RM --backend opencv-dshow-raw --modes common --sets single --cams c922 --opencv-order fourcc-first --label-suffix _fourccfirst
date -u; echo VERIFY_DONE
