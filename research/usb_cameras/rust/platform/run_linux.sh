#!/usr/bin/env bash
# =====================================================================================
# Rust candidates — Linux runner (DRAFTED ON WINDOWS, NOT YET RUN ON LINUX: unverified)
#
# What it runs (from the repo root):
#   1. builds nokhwa_probe (nokhwa 0.10.11, V4L2 backend) and uvc_iso (from-scratch UVC over
#      raw iso transfers; rawusb + libusb backends)
#   2. nokhwa_probe list                       -> what nokhwa exposes (name / "misc" id / formats)
#   3. nokhwa_probe capture per V4L2 index     -> raw MJPEG? per-frame timestamps (V4L2 buffer ts)
#   4. uvc_iso list (rawusb, libusb)           -> UVC descriptors, iso alt-setting bandwidths, port paths
#   5. uvc_iso stream per UVC camera, alt=device and alt=payload:<smaller> -> bandwidth under app control
#   6. uvc_iso stream on ALL cameras at once, alt=device then alt=payload:1024 -> how many fit on one bus
#
# Hardware: 1..N UVC webcams with MJPEG (ideally >=3 on ONE USB2 hub/controller for step 6).
# Permissions:
#   - steps 2-3: user in group `video` (ls -l /dev/video*)
#   - steps 5-6: write access to /dev/bus/usb/BBB/DDD. Either run with sudo -E, or install a udev rule:
#       echo 'SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{bDeviceClass}=="ef", MODE="0666"' | \
#         sudo tee /etc/udev/rules.d/70-uvc-raw.rules && sudo udevadm control --reload && sudo udevadm trigger
#     (0xEF = misc/IAD class used by UVC webcams; narrow it with ATTR{idVendor}=="046d" etc. if you prefer)
#     uvc_iso detaches uvcvideo from the camera's interfaces while streaming (the /dev/videoN node
#     disappears) and libusb/rawusb re-attach it on release; if a camera stays missing, replug it.
# Build deps: rustup (stable), a C compiler, pkg-config; nokhwa's v4l2-sys-mit uses bindgen, so
#   clang/libclang + linux headers are needed:  sudo apt install build-essential pkg-config clang libclang-dev linux-libc-dev libudev-dev
# Output: research/usb_cameras/results/linux/<hostname>/rust_*/<timestamp>/summary.json (+ frames_*.jsonl, a sample JPEG)
#         plus a log of this script at results/linux/<hostname>/rust_run_linux/<ts>/run.log
# Usage:  bash research/usb_cameras/rust/platform/run_linux.sh [--seconds 15] [--width 1280 --height 720 --fps 30] [--skip-build] [--sudo]
# =====================================================================================
set -u
SECONDS_RUN=15; W=1280; H=720; FPS=30; SKIP_BUILD=0; SUDO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --seconds) SECONDS_RUN="$2"; shift ;;
    --width) W="$2"; shift ;;
    --height) H="$2"; shift ;;
    --fps) FPS="$2"; shift ;;
    --skip-build) SKIP_BUILD=1 ;;
    --sudo) SUDO="sudo -E" ;;
    *) echo "unknown arg $1"; exit 2 ;;
  esac; shift
done
REPO="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$REPO" || exit 1
HOST="$(hostname | cut -d. -f1)"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOGDIR="research/usb_cameras/results/linux/$HOST/rust_run_linux/$TS"
mkdir -p "$LOGDIR"
exec > >(tee -a "$LOGDIR/run.log") 2>&1
echo "== run_linux.sh $TS host=$HOST uname=$(uname -a)"
command -v cargo >/dev/null || { echo "cargo not found: install rustup from https://rustup.rs"; exit 3; }
RUST="research/usb_cameras/rust"
BIN="$RUST/build/release"
{ cargo --version; rustc --version; lsusb 2>/dev/null; lsusb -t 2>/dev/null; v4l2-ctl --list-devices 2>/dev/null; } > "$LOGDIR/env.txt" 2>&1

if [ "$SKIP_BUILD" = 0 ]; then
  ( cd "$RUST" && /usr/bin/time -v cargo build --release -p nokhwa_probe ) > "$LOGDIR/build_nokhwa.log" 2>&1 || echo "!! nokhwa_probe build failed (see build_nokhwa.log; usually missing clang/libclang-dev)"
  ( cd "$RUST" && /usr/bin/time -v cargo build --release -p uvc_iso --features libusb ) > "$LOGDIR/build_uvc_iso.log" 2>&1 || {
    echo "!! uvc_iso with libusb failed, trying rawusb only"; ( cd "$RUST" && cargo build --release -p uvc_iso ) >> "$LOGDIR/build_uvc_iso.log" 2>&1; }
  ls -l "$BIN"/nokhwa_probe "$BIN"/uvc_iso > "$LOGDIR/binary_sizes.txt" 2>&1
fi

# --- nokhwa (V4L2) ---
if [ -x "$BIN/nokhwa_probe" ]; then
  "$BIN/nokhwa_probe" list || echo "!! nokhwa list failed"
  for dev in /dev/video*; do
    idx="${dev#/dev/video}"
    # skip metadata nodes: they have no Video Capture capability
    if command -v v4l2-ctl >/dev/null && ! v4l2-ctl -d "$dev" --info 2>/dev/null | grep -q "Video Capture"; then continue; fi
    echo "== nokhwa capture $dev"
    timeout $((SECONDS_RUN + 30)) "$BIN/nokhwa_probe" capture --cameras "$idx" --width "$W" --height "$H" --fps "$FPS" --seconds "$SECONDS_RUN" --decode-every 30 --save-samples 1 || echo "!! nokhwa capture $dev failed"
  done
fi

# --- uvc_iso ---
if [ -x "$BIN/uvc_iso" ]; then
  for be in rawusb libusb; do $SUDO "$BIN/uvc_iso" list --backend "$be" || echo "!! uvc_iso list $be failed"; done
  # VID:PID list of UVC cameras (lsusb -v is slow but universal)
  mapfile -t CAMS < <(for d in /sys/bus/usb/devices/*; do
      [ -f "$d/bInterfaceClass" ] && [ "$(cat "$d/bInterfaceClass")" = "0e" ] && [ "$(cat "$d/bInterfaceSubClass")" = "01" ] || continue
      p="$(dirname "$d")/$(basename "$d" | cut -d: -f1)"; echo "$(cat "$p/idVendor"):$(cat "$p/idProduct")"; done | sort -u)
  echo "UVC cameras: ${CAMS[*]:-none}"
  for vp in "${CAMS[@]}"; do
    v="${vp%:*}"; p="${vp#*:}"
    for alt in device payload:1024; do
      for be in rawusb libusb; do
        echo "== uvc_iso stream $vp alt=$alt backend=$be"
        timeout $((SECONDS_RUN + 30)) $SUDO "$BIN/uvc_iso" stream --backend "$be" --vid "$v" --pid "$p" --width "$W" --height "$H" --fps "$FPS" \
          --alt "$alt" --seconds "$SECONDS_RUN" --exposure-100us 78 --wb 4000           --out "research/usb_cameras/results/linux/$HOST/rust_uvc_iso_single/${TS}/${vp/:/_}_${alt/:/-}_${be}" || echo "!! stream $vp $alt $be failed"
        sleep 2
      done
    done
  done
  # all at once (one process per camera), same bus is what matters: see lsusb -t in env.txt
  if [ "${#CAMS[@]}" -ge 2 ]; then
    for alt in device payload:1024; do
      echo "== uvc_iso stream ALL cameras concurrently alt=$alt"
      pids=()
      for vp in "${CAMS[@]}"; do
        timeout $((SECONDS_RUN + 30)) $SUDO "$BIN/uvc_iso" stream --backend libusb --vid "${vp%:*}" --pid "${vp#*:}" --width "$W" --height "$H" --fps "$FPS" \
          --alt "$alt" --seconds "$SECONDS_RUN" --exposure-100us 78 --wb 4000           --out "research/usb_cameras/results/linux/$HOST/rust_uvc_iso_concurrent/${TS}_${alt/:/-}/${vp/:/_}" & pids+=($!)
      done
      for pid in "${pids[@]}"; do wait "$pid" || echo "!! a concurrent stream failed (expected when bandwidth is exhausted: look for start_iso/set_alt errors)"; done
      sleep 2
    done
  fi
fi
echo "== done. Results under research/usb_cameras/results/linux/$HOST/ ; analyse with:"
echo "   uv run --script research/usb_cameras/rust/tools/analyze_frames_rust.py research/usb_cameras/results/linux/$HOST/rust_*/*/"
