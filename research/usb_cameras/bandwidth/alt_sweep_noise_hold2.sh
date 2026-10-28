#!/bin/bash
# alt_sweep_noise_hold2.sh -- goal 3 phase 2, ONE camlock hold, focus pinned (autofocus off at its current position):
#  (1) wCompQuality streams 61, 2, 30 on the static scene, ONE quality per process (5 s each, alt 11)
#  (2) noise_display.exe on monitor 0 (viewed by the C930e) + alt_sweep_run.sh TAG=_noise_fixedfocus
#  (3) autofocus restored (--focus-auto 1)
#   uv run --script research/usb_cameras/tools/camlock.py -- "C:/Program Files/Git/bin/bash.exe" \
#       research/usb_cameras/bandwidth/alt_sweep_noise_hold2.sh BINDIR RAWDIR RESULTDIR
BIN="$1"; RAW="$2"; RES="$3"; HERE="$(cd "$(dirname "$0")" && pwd)"; P="$BIN/uvc_probe_quality.exe"; mkdir -p "$RAW"
"$P" --controls-only --out "$RES/probe_quality/focus_before.json"
"$P" --controls-only --focus-auto 0 --out "$RES/probe_quality/focus_pinned.json"
for q in 61 2 30; do
  "$P" --width 1280 --height 720 --fps 30 --exposure-abs 156 --wb-temp 4000 --stream-q $q --seconds 5 --out "$RES/probe_quality/stream_q${q}_fixedfocus_1280x720.json"; echo "q=$q rc=$?"
done
TAG=_static_fixedfocus "$HERE/alt_sweep_run.sh" "$BIN/uvc_capture_test.exe" "$RAW" 1280 720 30 10 "11"
"$BIN/noise_display.exe" --monitor 0 --seconds 120 --block 2 > "$RAW/noise_display2.json" &
NP=$!
sleep 3
TAG=_noise_fixedfocus "$HERE/alt_sweep_run.sh" "$BIN/uvc_capture_test.exe" "$RAW" 1280 720 30 20 "11 6"
TAG=_noise_fixedfocus "$HERE/alt_sweep_run.sh" "$BIN/uvc_capture_test.exe" "$RAW" 1920 1080 30 20 "11 8"
wait $NP; cat "$RAW/noise_display2.json"
"$P" --controls-only --focus-auto 1 --out "$RES/probe_quality/focus_restored.json"
