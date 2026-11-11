#!/usr/bin/env bash
# Functional Chromium codec tests (no timing numbers are taken from these runs).
# Prereq: make_clips.py and make_extras.py have been run (media + manifest under the skellycam-raw topic folder).
# Usage (Git Bash, from anywhere):  bash research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/run_functional.sh [main|serving|all]
set -u
REPO=/c/Users/Dom/GitHub/freemocap/skellycam
H=$REPO/research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/harness
OUT=$REPO/research/skellycam_recording/recording_upgrade/results/chromium_codecs/raw
E35=$REPO/skellycam-ui/node_modules/electron/dist/electron.exe
E45=/c/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe
NODE="/c/Program Files/nodejs/node.exe"
WHAT=${1:-all}
mkdir -p "$OUT"
cd "$H" || exit 1
gpu() { echo "$(date -u +%FT%TZ) $1 $(nvidia-smi --query-gpu=encoder.stats.sessionCount,utilization.gpu,utilization.decoder --format=csv,noheader 2>&1)" >> "$OUT/nvidia_smi.log"; }
run_e() { # $1 exe, $2 tag, $3 suite
  gpu "before $2 $3"
  env -u ELECTRON_RUN_AS_NODE timeout 3600 "$1" electron_main.js --out "$OUT/$2_$3.json" --suite "$3" > "$OUT/$2_$3.stdout.txt" 2>&1
  echo "$2 $3 rc=$?"
  gpu "after $2 $3"
}
run_c() {
  gpu "before chrome156 $1"
  timeout 3600 "$NODE" run_chrome.js --out "$OUT/chrome156_$1.json" --suite "$1" > "$OUT/chrome156_$1.stdout.txt" 2>&1
  echo "chrome156 $1 rc=$?"
  gpu "after chrome156 $1"
}
if [ "$WHAT" = main ] || [ "$WHAT" = all ]; then
  run_e "$E35" electron35 main; run_e "$E45" electron45 main; run_c main
fi
if [ "$WHAT" = serving ] || [ "$WHAT" = all ]; then
  run_e "$E35" electron35 serving; run_e "$E45" electron45 serving; run_c serving
fi
