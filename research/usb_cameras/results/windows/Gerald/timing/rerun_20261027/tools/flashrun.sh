#!/bin/bash
# flashrun.sh <label> <cams ;-joined> [seconds]  -- waits for camlock, names the run dir by the UTC time the lock was requested
cd /c/Users/Dom/GitHub/freemocap/skellycam
SPW='C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad/runs/timing_rerun'
TS=$(date -u +%Y%m%dT%H%M%SZ); D="$SPW/${TS}_$1"
echo "$D"
timeout 900 uv run --script research/usb_cameras/tools/camlock.py --timeout-s 800 -- pwsh -NoProfile -File 'C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\timing\rerun_20261027\tools\run_flash_rerun.ps1' -RunDir "$D" -Cams "$2" -Seconds "${3:-30}" -Monitor 0 > "$D.stdout.txt" 2>&1
echo "exit=$?" >> "$D.stdout.txt"
date -u +%FT%TZ >> "$D.stdout.txt"
