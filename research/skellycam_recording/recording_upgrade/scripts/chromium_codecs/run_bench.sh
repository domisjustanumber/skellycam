#!/usr/bin/env bash
# Chromium decode / seek / multi-stream playback benchmarks. QUIET MACHINE ONLY (no other agents, no other GPU users).
# Prereq: .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/make_bench_clips.py   (full, NOT --quick)
# Usage (Git Bash, from anywhere):
#   bash research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/run_bench.sh <electron35|electron45|chrome156> [bench|bench-quick] [outdir]
# Writes <outdir>/<browser>_<suite>.json (default outdir: results/chromium_codecs/bench) plus nvidia_smi_bench.log.
# A visible 820x620 window opens at the top-left of the primary display for the duration; do not interact with it.
set -u
REPO=/c/Users/Dom/GitHub/freemocap/skellycam
H=$REPO/research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/harness
B=${1:?browser: electron35|electron45|chrome156}
SUITE=${2:-bench}
OUT=${3:-$REPO/research/skellycam_recording/recording_upgrade/results/chromium_codecs/bench}
E35=$REPO/skellycam-ui/node_modules/electron/dist/electron.exe
E45=/c/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe
NODE="/c/Program Files/nodejs/node.exe"
mkdir -p "$OUT"
cd "$H" || exit 1
gpu() { echo "$(date -u +%FT%TZ) $1 $(nvidia-smi --query-gpu=encoder.stats.sessionCount,utilization.gpu,utilization.decoder --format=csv,noheader 2>&1)" >> "$OUT/nvidia_smi_bench.log"; }
gpu "before $B $SUITE"
case "$B" in
  electron35) env -u ELECTRON_RUN_AS_NODE timeout 7200 "$E35" electron_main.js --out "$OUT/${B}_${SUITE}.json" --suite "$SUITE" > "$OUT/${B}_${SUITE}.stdout.txt" 2>&1 ;;
  electron45) env -u ELECTRON_RUN_AS_NODE timeout 7200 "$E45" electron_main.js --out "$OUT/${B}_${SUITE}.json" --suite "$SUITE" > "$OUT/${B}_${SUITE}.stdout.txt" 2>&1 ;;
  chrome156) timeout 7200 "$NODE" run_chrome.js --out "$OUT/${B}_${SUITE}.json" --suite "$SUITE" > "$OUT/${B}_${SUITE}.stdout.txt" 2>&1 ;;
  *) echo "unknown browser $B"; exit 2 ;;
esac
rc=$?
gpu "after $B $SUITE rc=$rc"
echo "$B $SUITE rc=$rc -> $OUT/${B}_${SUITE}.json"
exit $rc
