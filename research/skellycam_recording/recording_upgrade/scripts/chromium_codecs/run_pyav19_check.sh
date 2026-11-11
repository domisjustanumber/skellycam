#!/usr/bin/env bash
# Play/seek check of the PyAV 19.0.2-encoded clips (make_pyav19_clips.py) in Electron 45.2.3 and Chrome 156.
# (The Electron 35 rerun picks them up automatically because they are in manifest.json.) Functional only.
set -u
REPO=/c/Users/Dom/GitHub/freemocap/skellycam
H=$REPO/research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/harness
OUT=$REPO/research/skellycam_recording/recording_upgrade/results/chromium_codecs/raw
E45=/c/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe
NODE="/c/Program Files/nodejs/node.exe"
cd "$H" || exit 1
mkdir -p "$OUT/pyav19" "$OUT/chrome156"
env -u ELECTRON_RUN_AS_NODE timeout 1200 "$E45" electron_main.js --out "$OUT/pyav19/electron45_main_pyav19.json" --suite main --only pyav19 > "$OUT/pyav19/electron45_main_pyav19.stdout.txt" 2>&1
echo "electron45 pyav19 rc=$?"
timeout 1200 "$NODE" run_chrome.js --out "$OUT/chrome156/chrome156_main_pyav19.json" --suite main --only pyav19 > "$OUT/chrome156/chrome156_main_pyav19.stdout.txt" 2>&1
echo "chrome156 pyav19 rc=$?"
