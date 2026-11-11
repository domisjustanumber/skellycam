#!/usr/bin/env bash
# Live timestamp-accuracy runs on Gerald (2026-11-09). Every camera-opening command goes through camlock and a hard
# `timeout`. No registry or device changes. Usage (Git Bash, from research/usb_cameras):
#   bash timing/ts_accuracy/live/run_all.sh [results_dir] [seconds]
set -u
cd "$(dirname "$0")/../../.."   # research/usb_cameras
OUT=${1:-results/windows/Gerald/ts_accuracy_20261109/live}
SECS=${2:-75}
mkdir -p "$OUT"
LOG="$OUT/run_log.txt"
VID=${VIDEO_DIR:-$TEMP}
EXE="$(cygpath -w "$PWD/timing/build/mf_uvc_timing.exe")"
CL="uv run --script tools/camlock.py --timeout-s 1800 --"
C922=046D:085C; C930=046D:0843; KIYO=1532:0E05; GEN=4C4A:4A55
M922="vid_046d&pid_085c,1280,720,30,-7,auto"; M930="vid_046d&pid_0843,1280,720,30,-7,auto"
MKIYO="vid_1532&pid_0e05,1280,720,30,-7,auto"; MGEN="vid_4c4a&pid_4a55,1280,720,30,-7,auto"
HARD=$((SECS + 120))

dshow() {  # label mode cams
  echo "=== $(date -u +%FT%TZ) DSHOW $1 mode=$2 cams=$3" | tee -a "$LOG"
  timeout "$HARD" $CL uv run --script timing/ts_accuracy/live/dshow_capture.py --mode "$2" --cams "$3" \
    --seconds "$SECS" --record --video-dir "$VID" --label "$1" --out "$OUT" 2>&1 | grep -v '^\s*$' | tail -4 | tee -a "$LOG"
  echo "exit=${PIPESTATUS[0]}" | tee -a "$LOG"
}
mf() {  # label cam-spec...
  local label=$1; shift
  local d="$OUT/mf_$label"; mkdir -p "$d"
  local args=(); for c in "$@"; do args+=(--cam "$c"); done
  echo "=== $(date -u +%FT%TZ) MF $label $*" | tee -a "$LOG"
  timeout "$HARD" $CL "$EXE" --out "$(cygpath -w "$d")" --seconds "$SECS" --exposure-schedule "-7" \
    --exposure-dwell-s 1000 --exposure-first-s 1.5 "${args[@]}" 2>&1 | tail -6 | tee -a "$LOG"
  echo "exit=${PIPESTATUS[0]}" | tee -a "$LOG"
}

STEPS=${STEPS:-"C_kiyo A2 B2 C_c930e_kiyo A4 A1_c930e A1_c922 B1_c930e B1_c922 A3 B3 C_c922 C_c930e C_generic C_c930e_generic"}
for s in $STEPS; do
  case $s in
    A1_c930e) dshow A1_c930e skellycam $C930 ;;
    A1_c922)  dshow A1_c922 skellycam $C922 ;;
    A2) dshow A2 skellycam $C930,$KIYO ;;
    A3) dshow A3 skellycam $C930,$GEN ;;
    A4) dshow A4 skellycam $C930,$KIYO,$C922 ;;
    B1_c930e) dshow B1_c930e free $C930 ;;
    B1_c922)  dshow B1_c922 free $C922 ;;
    B2) dshow B2 free $C930,$KIYO ;;
    B3) dshow B3 free $C930,$GEN ;;
    C_kiyo) mf kiyo "$MKIYO" ;;
    C_c922) mf c922 "$M922" ;;
    C_c930e) mf c930e "$M930" ;;
    C_generic) mf generic "$MGEN" ;;
    C_c930e_kiyo) mf c930e_kiyo "$M930" "$MKIYO" ;;
    C_c930e_generic) mf c930e_generic "$M930" "$MGEN" ;;
  esac
done
echo "=== $(date -u +%FT%TZ) done" | tee -a "$LOG"
