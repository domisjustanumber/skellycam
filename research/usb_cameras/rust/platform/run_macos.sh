#!/usr/bin/env bash
# =====================================================================================
# Rust candidates — macOS runner (DRAFTED ON WINDOWS, NOT YET RUN ON macOS: unverified)
#
# Answers, on macOS:
#   A. nokhwa 0.10.11 AVFoundation backend: are frames raw MJPEG? Source reading says NO: the
#      capture callback copies CMSampleBufferGetImageBuffer (a decoded CVPixelBuffer) and tags it
#      FrameFormat::GRAY (nokhwa-bindings-macos-0.2.4 src/lib.rs capture_out_callback). This test
#      checks the bytes (summary.json: frames_with_soi / decode_ok) and what uniqueID looks like.
#   B. uvc_iso (raw USB iso via IOKit, rawusb + libusb backends): can a user-space app claim the
#      UVC interfaces at all on this macOS version, with and without sudo? If yes: MJPEG bytes,
#      PTS/SCR, alt-setting control as on Linux.
# Hardware: 1..N UVC webcams with MJPEG.
# Permissions: Terminal (or your shell app) needs Camera permission for A (System Settings >
#   Privacy & Security > Camera; first run triggers the prompt — accept it and re-run).
#   B is run twice: as the user, then with sudo (you will be asked for your password once).
# Build deps: Xcode command line tools (xcode-select --install), rustup stable.
# Output: research/usb_cameras/results/macos/<hostname>/rust_*/<ts>/summary.json (+ frames_*.jsonl)
#         and results/macos/<hostname>/rust_run_macos/<ts>/run.log
# Usage:  bash research/usb_cameras/rust/platform/run_macos.sh [--seconds 15] [--skip-build] [--no-sudo]
# =====================================================================================
set -u
SECONDS_RUN=15; W=1280; H=720; FPS=30; SKIP_BUILD=0; USE_SUDO=1
while [ $# -gt 0 ]; do
  case "$1" in
    --seconds) SECONDS_RUN="$2"; shift ;;
    --width) W="$2"; shift ;;
    --height) H="$2"; shift ;;
    --fps) FPS="$2"; shift ;;
    --skip-build) SKIP_BUILD=1 ;;
    --no-sudo) USE_SUDO=0 ;;
    *) echo "unknown arg $1"; exit 2 ;;
  esac; shift
done
REPO="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$REPO" || exit 1
HOST="$(hostname -s)"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOGDIR="research/usb_cameras/results/macos/$HOST/rust_run_macos/$TS"
mkdir -p "$LOGDIR"
exec > >(tee -a "$LOGDIR/run.log") 2>&1
echo "== run_macos.sh $TS host=$HOST $(sw_vers 2>/dev/null | tr '\n' ' ')"
command -v cargo >/dev/null || { echo "cargo not found: install rustup from https://rustup.rs"; exit 3; }
RUST="research/usb_cameras/rust"
BIN="$RUST/build/release"
{ cargo --version; rustc --version; system_profiler SPCameraDataType SPUSBDataType 2>/dev/null; ioreg -p IOUSB -l -w0 2>/dev/null | grep -E '"(USB Product Name|idVendor|idProduct|locationID|USB Serial Number)"'; } > "$LOGDIR/env.txt" 2>&1

if [ "$SKIP_BUILD" = 0 ]; then
  ( cd "$RUST" && /usr/bin/time -l cargo build --release -p nokhwa_probe ) > "$LOGDIR/build_nokhwa.log" 2>&1 || echo "!! nokhwa_probe build failed"
  ( cd "$RUST" && /usr/bin/time -l cargo build --release -p uvc_iso --features libusb ) > "$LOGDIR/build_uvc_iso.log" 2>&1 || {
    echo "!! uvc_iso with libusb failed, trying rawusb only"; ( cd "$RUST" && cargo build --release -p uvc_iso ) >> "$LOGDIR/build_uvc_iso.log" 2>&1; }
  ls -l "$BIN"/nokhwa_probe "$BIN"/uvc_iso > "$LOGDIR/binary_sizes.txt" 2>&1
fi

# --- A: nokhwa AVFoundation ---
if [ -x "$BIN/nokhwa_probe" ]; then
  "$BIN/nokhwa_probe" list || echo "!! nokhwa list failed (camera permission?)"
  N=$(system_profiler SPCameraDataType 2>/dev/null | grep -c "Unique ID")
  for ((i=0; i<N; i++)); do
    echo "== nokhwa capture index $i"
    "$BIN/nokhwa_probe" capture --cameras "$i" --width "$W" --height "$H" --fps "$FPS" --seconds "$SECONDS_RUN" --decode-every 30 --save-samples 1 || echo "!! nokhwa capture $i failed"
  done
fi

# --- B: uvc_iso over IOKit ---
if [ -x "$BIN/uvc_iso" ]; then
  for be in rawusb libusb; do "$BIN/uvc_iso" list --backend "$be" || echo "!! uvc_iso list $be failed"; done
  # VID/PID of UVC cameras from the libusb listing just written
  LIST=$(ls -t research/usb_cameras/results/macos/"$HOST"/rust_uvc_iso_list*/*/summary.json 2>/dev/null | head -1)
  CAMS=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(' '.join(u['vid']+':'+u['pid'] for u in d.get('uvc_devices',[])))" "$LIST" 2>/dev/null)
  echo "UVC cameras: ${CAMS:-none}"
  for vp in $CAMS; do
    for who in user root; do
      [ "$who" = root ] && [ "$USE_SUDO" = 0 ] && continue
      PRE=""; [ "$who" = root ] && PRE="sudo -E"
      for be in rawusb libusb; do
        echo "== uvc_iso stream $vp as $who backend=$be"
        $PRE "$BIN/uvc_iso" stream --backend "$be" --vid "${vp%:*}" --pid "${vp#*:}" --width "$W" --height "$H" --fps "$FPS" \
          --alt device --seconds "$SECONDS_RUN" --exposure-100us 78 --wb 4000 \
          --out "research/usb_cameras/results/macos/$HOST/rust_uvc_iso_single/${TS}/${vp/:/_}_${who}_${be}" || echo "!! stream $vp $who $be failed (claim failure here IS the finding)"
        sleep 2
      done
    done
  done
fi
echo "== done. Results under research/usb_cameras/results/macos/$HOST/"
