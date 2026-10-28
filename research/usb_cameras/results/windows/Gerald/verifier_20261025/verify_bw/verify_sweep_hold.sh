#!/bin/bash
# Adversarial verifier, ONE camlock hold: C930e (WinUSB/libuvc) forced-alt runs, saving every JPEG, and
# win_usb_topology.py --pipes-only captured 6 s into each run (confirms the alt the host actually selected).
#   camlock -- bash verify_sweep_hold.sh EXE RAW TOPO_PY
EXE="$1"; RAW="$2"; TOPO="$3"; mkdir -p "$RAW"
run() { W=$1; H=$2; A=$3; S=$4
  D="$RAW/${W}x${H}_alt${A}"; rm -rf "$D"; mkdir -p "$D"; date -u +%FT%TZ > "$D/utc_start.txt"
  AA=(); [ "$A" != "0" ] && AA=(--alt "$A")
  "$EXE" --vid 046d --pid 0843 --width $W --height $H --fps 30 --seconds $S "${AA[@]}" --exposure-abs 156 --wb-temp 4000 \
     --save-jpeg 5000 --save-jpeg-deferred --out-dir "$D" > "$D/stdout.log" 2> "$D/stderr.log" &
  P=$!; sleep 6
  uv run --script "$TOPO" --pipes-only > "$D/pipes.json" 2> "$D/pipes.stderr.log"
  wait $P; echo "${W}x${H} alt=$A rc=$? $(grep -h -e 'frames=' "$D/stderr.log")"
}
run 1280 720 3 15
run 1280 720 4 15
run 1280 720 5 15
run 1280 720 0 12
run 1920 1080 6 12
run 1920 1080 8 12
