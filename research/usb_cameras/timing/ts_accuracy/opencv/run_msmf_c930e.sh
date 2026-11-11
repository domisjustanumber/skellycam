#!/usr/bin/env bash
# Runs under camlock: C930e AE priority 0, OpenCV MSMF probe with HW transforms off then default, then restore
# AE priority 1 and exposure -7 manual (the state read on 2026-11-09 before any change), read controls back.
S=C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/d7b5ebd7-23e2-4038-b89c-9e7af70dd7af/scratchpad
W=C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/suite/windows/native/build/wincam.exe
OUT=$S/opencv_results/$1
mkdir -p $OUT
"$W" controls --api ds --device "vid_046d&pid_0843" --read-only --timeout-ms 10000 --out $OUT/controls_before.json
"$W" controls --api ds --device "vid_046d&pid_0843" --set auto_exposure_priority=0 --timeout-ms 10000 --out $OUT/controls_set.json
timeout 200 uv run --script $S/opencv_scripts/msmf_timing.py --index 0 --hw-transforms 0 --out $OUT/hwT0 > $OUT/hwT0_stdout.txt 2>&1; echo "hwT0 rc=$?"
timeout 200 uv run --script $S/opencv_scripts/msmf_timing.py --index 0 --hw-transforms unset --out $OUT/hwT_default > $OUT/hwT_default_stdout.txt 2>&1; echo "hwT_default rc=$?"
"$W" controls --api ds --device "vid_046d&pid_0843" --set auto_exposure_priority=1 --timeout-ms 10000 --out $OUT/controls_restore_aep.json
"$W" controls --api ds --device "vid_046d&pid_0843" --set exposure=-7 --set-flags manual --timeout-ms 10000 --out $OUT/controls_restore_exposure.json
"$W" controls --api ds --device "vid_046d&pid_0843" --read-only --timeout-ms 10000 --out $OUT/controls_after.json
