#!/usr/bin/env bash
# adversarial verifier rerun (libusb_rust area, 20261027): same COMMON args as run_nokhwa_rerun.sh; Kiyo never selected.
set -u
SP=/c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad
REPO=/c/Users/Dom/GitHub/freemocap/skellycam
OUTROOT=$SP/runs/verify_libusb_rust_20261027/nokhwa
EXE="$(cygpath -w $SP/r/build/release/nokhwa_probe.exe)"
LOCK=(uv run --script research/usb_cameras/tools/camlock.py --timeout-s 1500 --)
TO=("C:/Program Files/Git/usr/bin/timeout.exe" -k 5 90)
COMMON=(--width 1280 --height 720 --fps 30 --seconds 20 --exposure -7 --wb 4000 --decode-every 30 --save-samples 1)
cpu() { powershell.exe -NoProfile -Command "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average" | tr -d '\r'; }
cd "$REPO"; mkdir -p "$OUTROOT"
run() {
  local ts; ts=$(date -u +%Y%m%dT%H%M%SZ); local out="$OUTROOT/${ts}_$1"
  echo "[$(date -u +%FT%TZ)] start $1 cpu_before=$(cpu)"
  "${LOCK[@]}" "${TO[@]}" "$EXE" capture --cameras "match:$2" "${COMMON[@]}" --out "$(cygpath -w "$out")" > "$out.stdout.txt" 2> "$out.stderr.txt"
  echo "exit=$?" > "$out.exit_code.txt"
  echo "[$(date -u +%FT%TZ)] end $1 $(cat "$out.exit_code.txt") cpu_after=$(cpu)"
}
for t in "$@"; do
  case $t in
    c922) run c922 "vid_046d&pid_085c";;
    pairA) run pair_c930e_generic_A "vid_046d&pid_0843,vid_4c4a&pid_4a55";;
    pairB) run pair_generic_c930e_B "vid_4c4a&pid_4a55,vid_046d&pid_0843";;
    all3) run all3 "vid_046d&pid_085c,vid_046d&pid_0843,vid_4c4a&pid_4a55";;
  esac
done
echo "[$(date -u +%FT%TZ)] done"
