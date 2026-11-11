#!/usr/bin/env bash
# Re-run of the 'main' suite for Electron 45.2.3 (the 12:30 run was cut off at task 156/205) and the first
# complete Chrome 156 'main' run. Functional only; no timing numbers are taken from these runs.
set -u
REPO=/c/Users/Dom/GitHub/freemocap/skellycam
H=$REPO/research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/harness
OUT=$REPO/research/skellycam_recording/recording_upgrade/results/chromium_codecs/raw
E45=/c/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe
NODE="/c/Program Files/nodejs/node.exe"
cd "$H" || exit 1
gpu() { echo "$(date -u +%FT%TZ) $1 $(nvidia-smi --query-gpu=encoder.stats.sessionCount,utilization.gpu,utilization.decoder --format=csv,noheader 2>&1)" >> "$OUT/nvidia_smi.log"; }
gpu "before electron45 main (rerun)"
env -u ELECTRON_RUN_AS_NODE timeout 3600 "$E45" electron_main.js --out "$OUT/electron45_main.json" --suite main > "$OUT/electron45_main.stdout.txt" 2>&1
echo "electron45 main rc=$?"
gpu "after electron45 main (rerun)"
mkdir -p "$OUT/chrome156"
gpu "before chrome156 main"
timeout 3600 "$NODE" run_chrome.js --out "$OUT/chrome156/chrome156_main.json" --suite main > "$OUT/chrome156/chrome156_main.stdout.txt" 2>&1
echo "chrome156 main rc=$?"
gpu "after chrome156 main"
