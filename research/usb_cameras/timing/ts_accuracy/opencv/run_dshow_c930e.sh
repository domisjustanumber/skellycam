#!/usr/bin/env bash
# Runs under camlock: set C930e AE priority 0 (was 1), run the DSHOW probe, restore AE priority 1, read controls back.
S=C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/d7b5ebd7-23e2-4038-b89c-9e7af70dd7af/scratchpad
W=C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/suite/windows/native/build/wincam.exe
OUT=$S/opencv_results/$1
mkdir -p $OUT
"$W" controls --api ds --device "vid_046d&pid_0843" --set auto_exposure_priority=0 --timeout-ms 10000 --out $OUT/controls_set.json
timeout 240 uv run --script $S/opencv_scripts/dshow_timing.py --index 3 --expect-name "Logitech Webcam C930e" --out $OUT --work-ms 0,20,50 > $OUT/stdout.txt 2>&1
echo "probe rc=$?"
"$W" controls --api ds --device "vid_046d&pid_0843" --set auto_exposure_priority=1 --timeout-ms 10000 --out $OUT/controls_restore.json
"$W" controls --api ds --device "vid_046d&pid_0843" --read-only --timeout-ms 10000 --out $OUT/controls_after.json
