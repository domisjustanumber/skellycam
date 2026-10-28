#!/usr/bin/env bash
# =====================================================================================
# Phase-2 runner (Windows, Git Bash) for uvc_iso once the C930e is bound to WinUSB.
# First run 2026-10-25 (phase 2) with the C930e parent bound to inbox WinUSB; each camera step takes the camlock.
#
# Prereqs:
#   - C930e (VID 046D PID 0843) bound to WinUSB: either the whole device (parent
#     USB\VID_046D&PID_0843\7&7DCC7CE&0&4, what results/windows/Gerald/winusb_install dry-run targets)
#     or its video function (USB\VID_046D&PID_0843&MI_00\8&39DEC205&0&0000).
#     Pass the instance that has WinUSB as INSTANCE (used to find its DeviceInterfaceGUIDs for SOF calibration).
#   - cd research/usb_cameras/rust && cargo build --release -p uvc_iso --features libusb
# Steps:
#   1. uvc_iso list (rawusb, libusb)       -> is the C930e visible/openable now; alt-setting table
#   2. sof-calib                           -> WinUsb_GetCurrentFrameNumber vs QPC fit (frames/s should be ~1000)
#   3. stream alt=device, rawusb + libusb   -> MJPEG validity, fps, PTS/SCR, latency
#   4. stream alt=payload:N for N in 3060,1984,1024,640,384 (both backends) -> the smallest bandwidth that still gives full fps
#   5. stream with --sof-instance (calibration before/after) -> drift of the USB frame clock vs QPC
# Usage (repo root):  bash research/usb_cameras/rust/platform/run_windows_phase2.sh ['USB\VID_046D&PID_0843\7&7DCC7CE&0&4']
#   6. tools/analyze_frames_rust.py + tools/decode_mjpeg_check.py (full Pillow decode of every frame)
# Env: OUT (result dir), RAW_DIR (where raw .mjpeg go; keep it outside the repo, frames show the room)
# Output: research/usb_cameras/results/windows/<host>/phase2_rust_uvc_iso/<ts>/...
# =====================================================================================
set -u
INSTANCE="${1:-USB\VID_046D&PID_0843\7&7DCC7CE&0&4}"
REPO="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$REPO" || exit 1
HOST="$(hostname)"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${OUT:-research/usb_cameras/results/windows/$HOST/phase2_rust_uvc_iso/$TS}"
RAW_DIR="${RAW_DIR:-$OUT/raw}"
mkdir -p "$OUT" "$RAW_DIR"
exec > >(tee -a "$OUT/run.log") 2>&1
EXE="$(cygpath -w "$REPO/research/usb_cameras/rust/build/release/uvc_iso.exe")"
LOCK=(uv run --script research/usb_cameras/tools/camlock.py --timeout-s 3000 --)
COMMON=(--vid 046d --pid 0843 --width 1280 --height 720 --fps 30 --seconds 15 --exposure-100us 78 --wb 4000 --save-samples 0)
w() { cygpath -w "$1"; }
echo "== phase2 $TS instance=$INSTANCE out=$OUT raw=$RAW_DIR"
for be in rawusb libusb; do "${LOCK[@]}" "$EXE" list --backend "$be" --out "$(w "$OUT/list_$be")"; done
"${LOCK[@]}" "$EXE" sof-calib --instance "$INSTANCE" --out "$(w "$OUT/sof_calib")"
for be in rawusb libusb; do
  "${LOCK[@]}" "$EXE" stream --backend "$be" "${COMMON[@]}" --alt device --out "$(w "$OUT/stream_${be}_device")" --raw-mjpeg "$(w "$RAW_DIR/stream_${be}_device.mjpeg")"
done
for be in rawusb libusb; do
  for n in 3060 1984 1024 640 384; do
    "${LOCK[@]}" "$EXE" stream --backend "$be" "${COMMON[@]}" --alt "payload:$n" --out "$(w "$OUT/stream_${be}_payload$n")" --raw-mjpeg "$(w "$RAW_DIR/stream_${be}_payload$n.mjpeg")"
  done
done
"${LOCK[@]}" "$EXE" stream --backend rawusb "${COMMON[@]}" --alt device --seconds 60 --sof-instance "$INSTANCE" --out "$(w "$OUT/stream_rawusb_sof60s")" --raw-mjpeg "$(w "$RAW_DIR/stream_rawusb_sof60s.mjpeg")"
uv run --script research/usb_cameras/rust/tools/analyze_frames_rust.py "$OUT"/stream_*/
args=(); for d in "$OUT"/stream_*/; do n="$(basename "$d")"; [ -f "$RAW_DIR/$n.mjpeg" ] && args+=("$d" "$RAW_DIR/$n.mjpeg"); done
uv run --script research/usb_cameras/rust/tools/decode_mjpeg_check.py "${args[@]}"
echo "== done: $OUT"
