#!/bin/bash
# alt_sweep_noise_hold.sh -- goal 3 phase 2, one camlock hold: (1) wCompQuality streams on the static scene
# (uvc_probe_quality --stream-q), (2) worst-case scene: noise_display.exe fills monitor 0 (which the C930e views)
# with full-contrast random noise changing every refresh, then alt_sweep_run.sh runs with TAG=_noise.
#   uv run --script research/usb_cameras/tools/camlock.py -- "C:/Program Files/Git/bin/bash.exe" \
#       research/usb_cameras/bandwidth/alt_sweep_noise_hold.sh BINDIR RAWDIR RESULTDIR
BIN="$1"; RAW="$2"; RES="$3"; HERE="$(cd "$(dirname "$0")" && pwd)"
"$BIN/uvc_probe_quality.exe" --vid 046d --pid 0843 --width 1280 --height 720 --fps 30 --exposure-abs 156 --wb-temp 4000 \
   --stream-q 61,2,30,61 --seconds 5 --out "$RES/probe_quality/stream_q_valid_1280x720.json"; echo "stream-q rc=$?"
"$BIN/noise_display.exe" --monitor 0 --seconds 135 --block 2 > "$RAW/noise_display.json" &
NP=$!
sleep 3
TAG=_noise "$HERE/alt_sweep_run.sh" "$BIN/uvc_capture_test.exe" "$RAW" 1280 720 30 20 "11 7 6"
TAG=_noise "$HERE/alt_sweep_run.sh" "$BIN/uvc_capture_test.exe" "$RAW" 1920 1080 30 20 "11 9"
wait $NP; cat "$RAW/noise_display.json"
