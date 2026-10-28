#!/usr/bin/env bash
# run_linux_timing.sh -- UNVERIFIED DRAFT (written on Windows, never run on Linux).
#
# Runs v4l2_uvc_timing.py on every UVC camera at once, first with the current uvcvideo hwtimestamps setting and, if
# passwordless sudo is available, a second time with hwtimestamps=1 (then restores the original value). Each run is
# analysed with tools/analyze_frames.py. Never prompts: sudo is only tried with -n.
#
# Usage (from the repo root):  bash research/usb_cameras/timing/linux/run_linux_timing.sh [SECONDS] [WxH] [FPS]
# Optional env: EXPOSURE_ABS=100 (100 us units -> 10 ms), WB_K=4500, NO_HWTS=1 (skip the hwtimestamps=1 pass)
# Results: research/usb_cameras/results/linux/<hostname>/timing/v4l2_uvc_timing/<tag>/
set -u
SECONDS_RUN=${1:-30}
SIZE=${2:-1280x720}
FPS=${3:-30}
HERE=$(cd "$(dirname "$0")" && pwd)
TOOLS="$HERE/../../tools"
SCRIPT="$HERE/v4l2_uvc_timing.py"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

uv run --script "$SCRIPT" --self-test || { echo "self-test failed; not capturing" >&2; exit 1; }

LIST_JSON=$(uv run --script "$SCRIPT" --list) || { echo "--list failed" >&2; exit 1; }
mapfile -t DEVICES < <(printf '%s' "$LIST_JSON" | python3 -c '
import json, sys
for c in json.load(sys.stdin)["cameras"]:
    if c.get("device") and not c.get("error") and c.get("mjpeg_modes"):
        print(c["device"])')
if [ ${#DEVICES[@]} -eq 0 ]; then echo "no UVC MJPEG cameras found" >&2; exit 1; fi
echo "cameras: ${DEVICES[*]}" >&2

EXTRA=()
[ -n "${EXPOSURE_ABS:-}" ] && EXTRA+=(--exposure-abs "$EXPOSURE_ABS")
[ -n "${WB_K:-}" ] && EXTRA+=(--wb-k "$WB_K")
DEVARGS=()
for d in "${DEVICES[@]}"; do DEVARGS+=(--device "$d"); done

run_pass() {  # $1 = tag
  local out
  out=$(uv run --script "$SCRIPT" "${DEVARGS[@]}" --size "$SIZE" --fps "$FPS" --seconds "$SECONDS_RUN" \
        --tag "$1" "${EXTRA[@]}" | tail -n 1) || echo "capture pass $1 reported errors" >&2
  if [ -n "$out" ] && [ -d "$out" ]; then
    printf '%s' "$LIST_JSON" > "$out/list.json"
    uv run --script "$TOOLS/analyze_frames.py" "$out"/*.frames.jsonl --out "$out/analysis.json" \
      || echo "analysis failed for $out" >&2
  fi
}

HWTS_PARAM=/sys/module/uvcvideo/parameters/hwtimestamps
ORIG_HWTS=$(cat "$HWTS_PARAM" 2>/dev/null || echo unknown)
run_pass "${STAMP}_hwts${ORIG_HWTS}"

if [ -z "${NO_HWTS:-}" ] && [ "$ORIG_HWTS" != "1" ] && [ "$ORIG_HWTS" != "Y" ] && [ -w "$HWTS_PARAM" -o -e "$HWTS_PARAM" ]; then
  if echo 1 | sudo -n tee "$HWTS_PARAM" >/dev/null 2>&1; then
    run_pass "${STAMP}_hwts1"
    echo "$ORIG_HWTS" | sudo -n tee "$HWTS_PARAM" >/dev/null 2>&1 || echo "WARNING: could not restore hwtimestamps=$ORIG_HWTS" >&2
  else
    echo "no passwordless sudo: skipped the hwtimestamps=1 pass (run 'echo 1 | sudo tee $HWTS_PARAM' and re-run to get it)" >&2
  fi
fi
echo "done; results under research/usb_cameras/results/linux/$(hostname)/timing/v4l2_uvc_timing/" >&2
