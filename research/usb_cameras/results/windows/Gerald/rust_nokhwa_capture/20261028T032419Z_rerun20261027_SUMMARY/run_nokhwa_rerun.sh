#!/usr/bin/env bash
# rerun20261027: research/usb_cameras/rust/run_windows_nokhwa.sh with the Razer Kiyo Pro (vid_1532&pid_0e05) removed
# (user exclusion) and the generic 4C4A:4A55 camera added; the Kiyo --frame-raw cross-check is dropped.
# Same COMMON args as the original runner. Each capture takes the camera lock separately (~25 s hold).
# Output goes to scratch (sample JPEGs stay there); the repo copy is made afterwards without the JPEGs.
set -u
SP=/c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad
REPO=/c/Users/Dom/GitHub/freemocap/skellycam
OUTROOT=$SP/runs/libusb_rust_20261027/nokhwa
EXE="$(cygpath -w $SP/r/build/release/nokhwa_probe.exe)"   # faithful build (rust_build/20261028T031415Z_rerun20261027)
LOCK=(uv run --script research/usb_cameras/tools/camlock.py --timeout-s 3000 --)
TO=(/usr/bin/timeout -k 5 120)
COMMON=(--width 1280 --height 720 --fps 30 --seconds 20 --exposure -7 --wb 4000 --decode-every 30 --save-samples 1)
cpu() { powershell.exe -NoProfile -Command "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average" | tr -d '\r'; }
cd "$REPO"
mkdir -p "$OUTROOT"
run() { # $1 tag, $2 match
  local ts; ts=$(date -u +%Y%m%dT%H%M%SZ)
  local out="$OUTROOT/${ts}_$1"
  echo "[$(date -u +%FT%TZ)] start $1 cpu_before=$(cpu)"
  "${LOCK[@]}" "${TO[@]}" "$EXE" capture --cameras "match:$2" "${COMMON[@]}" --out "$(cygpath -w "$out")" > "$out.stdout.txt" 2> "$out.stderr.txt"
  echo "exit=$?" > "$out.exit_code.txt"
  echo "[$(date -u +%FT%TZ)] end $1 $(cat "$out.exit_code.txt") cpu_after=$(cpu)"
}
run c922 "vid_046d&pid_085c"
run c930e "vid_046d&pid_0843"
run generic4c4a "vid_4c4a&pid_4a55"
run all3 "vid_046d&pid_085c,vid_046d&pid_0843,vid_4c4a&pid_4a55"
echo "[$(date -u +%FT%TZ)] all done"
