#!/bin/bash
# coexist_hold.sh -- goal 3 phase 2, ONE camlock hold: shared-hub coexistence of the generic "USB Camera" 4C4A:4A55
# (usbvideo, streamed through Media Foundation by mf_multi_open.exe) and the Logitech C930e 046D:0843 (WinUSB,
# libuvc uvc_capture_test --alt A), both behind the Genesys 05e3:0610 hub on xHCI root port 13.
#   uv run --script research/usb_cameras/tools/camlock.py -- "C:/Program Files/Git/bin/bash.exe" \
#       research/usb_cameras/bandwidth/coexist_hold.sh UVC_EXE RAWDIR ORDER "ALTS" [MODE_W MODE_H]
#   ORDER = gen_first  : generic starts (waits for STREAMING), then C930e at each alt for 14 s
#         = c930e_first: C930e starts, 3 s later the generic starts
# Per alt, while both should be streaming, bandwidth/win_usb_topology.py --pipes-only is saved (open pipes =>
# the alt each device actually has selected). Output per alt: RAWDIR/coexist_<ORDER>_alt<A>/{gen_mf.json,
# c930e/(result.json,frames.jsonl), pipes.json, *.log}. Summarise with bandwidth/coexist_summarize.py.
UVC="$1"; RAW="$2"; ORDER="$3"; ALTS="$4"; W="${5:-1280}"; H="${6:-720}"
HERE="$(cd "$(dirname "$0")" && pwd)"
MF="$HERE/build/mf_multi_open.exe"
GEN="vid_4c4a&pid_4a55:MJPG:1280x720@30"
for A in $ALTS; do
  D="$RAW/coexist_${ORDER}_alt${A}"; rm -rf "$D"; mkdir -p "$D/c930e"
  date -u +%FT%TZ > "$D/utc_start.txt"
  AA=(); [ "$A" != "0" ] && AA=(--alt "$A")
  if [ "$ORDER" = "gen_first" ]; then
    "$MF" --cam "$GEN" --seconds 19 --out "$D/gen_mf.json" > "$D/gen_mf.stdout.log" 2> "$D/gen_mf.stderr.log" &
    GP=$!
    for i in $(seq 1 100); do grep -q STREAMING "$D/gen_mf.stdout.log" 2>/dev/null && break; sleep 0.1; done
    sleep 1
    "$UVC" --vid 046d --pid 0843 --width "$W" --height "$H" --fps 30 --seconds 14 "${AA[@]}" --exposure-abs 156 --wb-temp 4000 \
       --out-dir "$D/c930e" > "$D/c930e.stdout.log" 2> "$D/c930e.stderr.log" &
    CP=$!
  else
    "$UVC" --vid 046d --pid 0843 --width "$W" --height "$H" --fps 30 --seconds 19 "${AA[@]}" --exposure-abs 156 --wb-temp 4000 \
       --out-dir "$D/c930e" > "$D/c930e.stdout.log" 2> "$D/c930e.stderr.log" &
    CP=$!
    sleep 3
    "$MF" --cam "$GEN" --seconds 14 --out "$D/gen_mf.json" > "$D/gen_mf.stdout.log" 2> "$D/gen_mf.stderr.log" &
    GP=$!
  fi
  sleep 6
  uv run --script "$HERE/win_usb_topology.py" --pipes-only > "$D/pipes.json" 2> "$D/pipes.stderr.log"
  wait $CP; CRC=$?; wait $GP; GRC=$?
  echo "$ORDER alt=$A c930e_rc=$CRC gen_rc=$GRC $(grep -h -e 'frames=' -e 'streaming:' -e 'rror' "$D/c930e.stderr.log" | tr '\n' ' ' | head -c 250)"
  sleep 1
done
