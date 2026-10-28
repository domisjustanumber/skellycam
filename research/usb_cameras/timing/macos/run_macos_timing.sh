#!/usr/bin/env bash
# run_macos_timing.sh -- UNVERIFIED DRAFT (written on Windows, never run on macOS).
#
# Lists AVFoundation cameras, runs avf_timing.py on each one in turn (AVFoundation runs one session per process here),
# then analyses every frames log with tools/analyze_frames.py. The terminal app needs camera permission
# (System Settings > Privacy & Security > Camera); the first run may show a prompt.
#
# Usage (from the repo root):  bash research/usb_cameras/timing/macos/run_macos_timing.sh [SECONDS] [WxH] [FPS]
# Optional env: LOCK_EXPOSURE=1
set -u
SECONDS_RUN=${1:-30}
SIZE=${2:-1280x720}
FPS=${3:-30}
HERE=$(cd "$(dirname "$0")" && pwd)
TOOLS="$HERE/../../tools"
SCRIPT="$HERE/avf_timing.py"
HOST=$(scutil --get LocalHostName 2>/dev/null || hostname -s)
OUT_ROOT="$HERE/../../results/macos/$HOST/timing/avf_timing_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT_ROOT"

uv run --script "$SCRIPT" --list | tee "$OUT_ROOT/list.json" || { echo "--list failed" >&2; exit 1; }
N=$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$OUT_ROOT/list.json") || N=0
[ "${N:-0}" -gt 0 ] || { echo "no AVFoundation cameras listed" >&2; exit 1; }
EXTRA=()
[ -n "${LOCK_EXPOSURE:-}" ] && EXTRA+=(--lock-exposure)

for ((i = 0; i < N; i++)); do
  uv run --script "$SCRIPT" --device-index "$i" --size "$SIZE" --fps "$FPS" --seconds "$SECONDS_RUN" \
    --out "$OUT_ROOT/dev$i" "${EXTRA[@]}" || echo "capture failed for device $i" >&2
done

shopt -s nullglob
FILES=("$OUT_ROOT"/dev*/*.frames.jsonl)
if [ ${#FILES[@]} -gt 0 ]; then
  uv run --script "$TOOLS/analyze_frames.py" "${FILES[@]}" --out "$OUT_ROOT/analysis.json"
fi
echo "done; results in $OUT_ROOT" >&2
