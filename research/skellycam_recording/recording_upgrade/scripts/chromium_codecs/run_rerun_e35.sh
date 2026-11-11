#!/usr/bin/env bash
# Re-run of the Electron 35.7.5 'main' suite with the Intel UHD 770 present (the 12:19 run had it absent), so that
# E35, E45 and Chrome 156 main runs share one machine state. The 12:19 files are kept in raw/e35_main_1219_igpu_absent/.
set -u
REPO=/c/Users/Dom/GitHub/freemocap/skellycam
H=$REPO/research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/harness
OUT=$REPO/research/skellycam_recording/recording_upgrade/results/chromium_codecs/raw
E35=$REPO/skellycam-ui/node_modules/electron/dist/electron.exe
cd "$H" || exit 1
mkdir -p "$OUT/e35_main_1219_igpu_absent"
mv "$OUT"/electron35_main.json "$OUT"/electron35_main.json.log "$OUT"/electron35_main.json.stages "$OUT"/electron35_main.stdout.txt "$OUT/e35_main_1219_igpu_absent/"
gpu() { echo "$(date -u +%FT%TZ) $1 $(nvidia-smi --query-gpu=encoder.stats.sessionCount,utilization.gpu,utilization.decoder --format=csv,noheader 2>&1)" >> "$OUT/nvidia_smi.log"; }
gpu "before electron35 main (rerun)"
env -u ELECTRON_RUN_AS_NODE timeout 3600 "$E35" electron_main.js --out "$OUT/electron35_main.json" --suite main > "$OUT/electron35_main.stdout.txt" 2>&1
echo "electron35 main rc=$?"
gpu "after electron35 main (rerun)"
