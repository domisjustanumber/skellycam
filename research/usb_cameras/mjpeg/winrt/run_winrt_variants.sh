#!/usr/bin/env bash
# WinRT MediaFrameReader variants on one camera: which (outputSubtype, memory preference, acquisition mode)
# combination, if any, hands over the camera's compressed MJPG buffers? Source format is always MJPG 1280x720@30.
# usage: bash research/usb_cameras/mjpeg/winrt/run_winrt_variants.sh [vidpid] [seconds] [results root]
# results: <results root>/mjpeg_winrt_variants/<variant>_<vidpid>/summary.json; the root defaults to a NEW
#          research/usb_cameras/results/windows/<host>/mjpeg_run_<UTC stamp>/ (earlier results are never overwritten).
# Each variant is its own camlock hold (~10 s).
set -u
DEV=${1:-vid_046d&pid_085c}; SEC=${2:-4}
HOST=$(hostname)
ROOT=${3:-research/usb_cameras/results/windows/$HOST/mjpeg_run_$(date -u +%Y%m%dT%H%M%SZ)}
SCR=${MJPEG_SCRATCH:-${TEMP:-/tmp}/usb_cameras_mjpeg_scratch}/$(basename "$ROOT")/mjpeg_winrt_variants
for v in "MJPG cpu buffered" "MJPG cpu realtime" "MJPG auto buffered" "none cpu buffered" "none auto buffered" "NV12 cpu buffered"; do
  set -- $v; RS=$1; MEM=$2; ACQ=$3; L="${RS}_${MEM}_${ACQ}_${DEV//&/_}"
  RD="$SCR/$L"; rm -rf "$RD"
  CMD=(uv run --script research/usb_cameras/mjpeg/winrt/winrt_capture.py --dev "$DEV" --size 1280x720 --fps 30 --seconds "$SEC" --warmup 1 --reader-subtype "$RS" --memory "$MEM" --acq "$ACQ" --run-dir "$RD")
  echo "=== $L"
  uv run --script research/usb_cameras/tools/camlock.py --timeout-s 3600 -- "${CMD[@]}" 2>&1 | grep -v VCAMDS | tail -2
  [ -f "$RD/meta.json" ] && uv run --script research/usb_cameras/mjpeg/summarize.py "$RD" --test mjpeg_winrt_variants --label "$L" --keep-samples 1 --root "$ROOT" --command "uv run --script research/usb_cameras/tools/camlock.py -- ${CMD[*]}" | tail -2
done
