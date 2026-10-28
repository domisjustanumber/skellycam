#!/bin/bash
# Adversarial verifier, ONE camlock hold: does a refused C930e stream start (alt 9 next to the generic via MF)
# cause the NEXT C930e stream start to deliver zero frames?  Sequence of steps, each logged with frames=.
UVC="$1"; RAW="$2"; HERE="$3"; mkdir -p "$RAW"; N=0
solo() { N=$((N+1)); D="$RAW/step$(printf %02d $N)_solo_alt$1"; rm -rf "$D"; mkdir -p "$D"; date -u +%FT%TZ > "$D/utc_start.txt"
  "$UVC" --vid 046d --pid 0843 --width 1280 --height 720 --fps 30 --seconds 6 --alt $1 --exposure-abs 156 --wb-temp 4000 \
    --out-dir "$D" > "$D/stdout.log" 2> "$D/stderr.log"; echo "step$N solo alt=$1 rc=$? $(grep -h 'frames=' "$D/stderr.log")"; }
fail9() { N=$((N+1)); "C:/Program Files/Git/bin/bash.exe" "$HERE/coexist_hold.sh" "$UVC" "$RAW/step$(printf %02d $N)_fail" gen_first "9"; echo "step$N (gen_first alt9)"; }
solo 8
fail9
solo 8
solo 8
fail9
solo 6
solo 6
