#!/usr/bin/env bash
# Windows (Git Bash) runner for the nokhwa probe on the shared test machine.
# Each step takes the camera lock separately (each hold is < 1 min).
# Prereq: cd research/usb_cameras/rust && cargo build --release -p nokhwa_probe
# Run from repo root:  bash research/usb_cameras/rust/run_windows_nokhwa.sh
set -u
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO"
EXE="$(cygpath -w "$REPO/research/usb_cameras/rust/build/release/nokhwa_probe.exe")"
LOCK=(uv run --script research/usb_cameras/tools/camlock.py --timeout-s 3000 --)
COMMON=(--width 1280 --height 720 --fps 30 --seconds 20 --exposure -7 --wb 4000 --decode-every 30 --save-samples 1)
"${LOCK[@]}" "$EXE" list
for m in "vid_1532&pid_0e05" "vid_046d&pid_085c" "vid_046d&pid_0843"; do
  "${LOCK[@]}" "$EXE" capture --cameras "match:$m" "${COMMON[@]}"
done
"${LOCK[@]}" "$EXE" capture --cameras "match:vid_1532&pid_0e05,vid_046d&pid_085c,vid_046d&pid_0843" "${COMMON[@]}"
# Same thing with frame_raw() (no Buffer/timestamp path) for the Razer, as a cross-check
"${LOCK[@]}" "$EXE" capture --cameras "match:vid_1532&pid_0e05" "${COMMON[@]}" --frame-raw
