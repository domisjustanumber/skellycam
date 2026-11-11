#!/usr/bin/env bash
# Variant run with hardware video decode disabled (--disable-accelerated-video-decode), to see which SOFTWARE
# decoder each browser falls back to - in particular whether Electron's bundled FFmpeg decodes H.264 / HEVC.
# Functional only. Usage: bash research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/run_swdecode.sh
set -u
REPO=/c/Users/Dom/GitHub/freemocap/skellycam
H=$REPO/research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/harness
OUT=$REPO/research/skellycam_recording/recording_upgrade/results/chromium_codecs/raw
E35=$REPO/skellycam-ui/node_modules/electron/dist/electron.exe
E45=/c/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe
NODE="/c/Program Files/nodejs/node.exe"
ONLY=h264_high_420__mp4,h264_high422__mp4,hevc_main_420__mp4,hevc_main10_420__mp4,av1_main8_420__mp4,av1_main10_420__mp4,vp9_p0_420__webm,vp9_p2_420_10__webm,vp8__webm
SW=disable-accelerated-video-decode
cd "$H" || exit 1
env -u ELECTRON_RUN_AS_NODE timeout 1800 "$E35" electron_main.js --out "$OUT/electron35_swdecode.json" --suite main --only "$ONLY" --switch $SW > "$OUT/electron35_swdecode.stdout.txt" 2>&1; echo "e35 rc=$?"
env -u ELECTRON_RUN_AS_NODE timeout 1800 "$E45" electron_main.js --out "$OUT/electron45_swdecode.json" --suite main --only "$ONLY" --switch $SW > "$OUT/electron45_swdecode.stdout.txt" 2>&1; echo "e45 rc=$?"
timeout 1800 "$NODE" run_chrome.js --out "$OUT/chrome156_swdecode.json" --suite main --only "$ONLY" --switch $SW > "$OUT/chrome156_swdecode.stdout.txt" 2>&1; echo "c156 rc=$?"
