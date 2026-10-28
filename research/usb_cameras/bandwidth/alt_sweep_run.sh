#!/bin/bash
# alt_sweep_run.sh -- goal 3 phase 2: C930e (WinUSB, libuvc) MJPEG alt-setting sweep, one mode, several forced alts.
# Run UNDER camlock (opens the camera); keep each invocation < ~3 min (about 6 alts x 20 s):
#   uv run --script research/usb_cameras/tools/camlock.py -- "C:/Program Files/Git/bin/bash.exe" \
#       research/usb_cameras/bandwidth/alt_sweep_run.sh EXE RAWDIR W H FPS SECONDS "ALTS" [extra uvc_capture_test args]
#   ALTS: space separated forced alts; 0 = libuvc's own choice (camera's dwMaxPayloadTransferSize)
#   env TAG=<suffix> is appended to each run directory name (e.g. TAG=_noise)
# Each run: EXE --vid 046d --pid 0843 --width W --height H --fps FPS --seconds SECONDS --alt A
#           --exposure-abs 156 --wb-temp 4000 --save-jpeg 5000 --save-jpeg-deferred --out-dir RAWDIR/<W>x<H>_alt<A><TAG>
# then analyse with bandwidth/alt_sweep_analyze.py (decodes every saved JPEG, writes the results JSON).
EXE="$1"; RAW="$2"; W="$3"; H="$4"; FPS="$5"; SEC="$6"; ALTS="$7"; shift 7
mkdir -p "$RAW"
for A in $ALTS; do
  D="$RAW/${W}x${H}_alt${A}${TAG}"
  rm -rf "$D"; mkdir -p "$D"
  AA=(); [ "$A" != "0" ] && AA=(--alt "$A")
  date -u +%FT%TZ > "$D/utc_start.txt"
  "$EXE" --vid 046d --pid 0843 --width "$W" --height "$H" --fps "$FPS" --seconds "$SEC" "${AA[@]}" \
     --exposure-abs 156 --wb-temp 4000 --save-jpeg 5000 --save-jpeg-deferred --out-dir "$D" "$@" > "$D/stdout.log" 2> "$D/stderr.log"
  rc=$?
  echo "${W}x${H} alt=$A rc=$rc $(grep -h -e 'frames=' -e 'streaming:' -e 'rror' "$D/stderr.log" | tr '\n' ' ' | head -c 300)"
done
