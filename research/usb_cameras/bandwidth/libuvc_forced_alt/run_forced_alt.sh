#!/usr/bin/env bash
# run_forced_alt.sh -- goal 3 DRAFT (Linux + macOS), UNVERIFIED until run.
# Builds upstream libuvc d07de4fa (LIBUVC_NUM_TRANSFER_BUFS=10) + uvc_multi_forced_alt.c, then for the UVC cameras
# you list runs: default alt (camera's request) with 1..N cameras, and forced smaller alts (0.5x, 0.25x of the request),
# recording which cameras start and whether MJPEG frames stay valid.
#
#   bash research/usb_cameras/bandwidth/libuvc_forced_alt/run_forced_alt.sh [--size 1280x720] [--fps 30] [--seconds 8] VID:PID [VID:PID ...]
#   e.g.  ... run_forced_alt.sh 046d:0843 046d:085c 4c4a:4a55
#
# Hardware: put ALL listed cameras behind ONE USB 2.0 hub (one root port) -- otherwise each camera has its own
#           root-port bandwidth budget and nothing is stressed.
# Linux:  needs build-essential cmake git pkg-config libusb-1.0-0-dev; as a NORMAL user, after installing once:
#           sudo install -m644 research/usb_cameras/libusb/linux/70-skellycam-uvc.rules /etc/udev/rules.d/ && sudo udevadm control --reload && sudo udevadm trigger
#         (replug the cameras). The script does NOT use sudo. Close any app using the cameras (uvcvideo gets detached
#         while the test runs and re-attached afterwards by libuvc).
# macOS:  brew install libusb cmake pkg-config. Runs once as your user (expected: LIBUSB_ERROR_ACCESS / "Access denied")
#         and, if you pass --also-sudo, once more with sudo (expected to work) -- that is the comparison the report needs.
# Output: research/usb_cameras/results/<linux|macos>/<hostname>/bw_forced_alt/*.json  + run.log
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
SIZE=1280x720; FPS=30; SECS=8; ALSO_SUDO=0; DEVS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --size) SIZE="$2"; shift ;; --fps) FPS="$2"; shift ;; --seconds) SECS="$2"; shift ;;
    --also-sudo) ALSO_SUDO=1 ;;
    -*) echo "unknown option $1" >&2; exit 1 ;;
    *) DEVS+=("$1") ;;
  esac; shift
done
[ ${#DEVS[@]} -ge 1 ] || { echo "list at least one VID:PID (see lsusb)" >&2; exit 1; }
case "$(uname -s)" in Linux) PLAT=linux ;; Darwin) PLAT=macos ;; *) echo "Linux/macOS only" >&2; exit 1 ;; esac
OUT="$REPO/research/usb_cameras/results/$PLAT/$(hostname -s)/bw_forced_alt"; mkdir -p "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1
echo "== $(date -u +%FT%TZ) $0 ${DEVS[*]} size=$SIZE fps=$FPS"
BUILD="${XDG_CACHE_HOME:-$HOME/.cache}/skellycam-bw-libuvc"; PREFIX="$BUILD/prefix"
if [ ! -f "$PREFIX/include/libuvc/libuvc.h" ]; then
  rm -rf "$BUILD/src"; git clone -q https://github.com/libuvc/libuvc "$BUILD/src" || exit 1
  git -C "$BUILD/src" checkout -q d07de4fa23905ee8cac06f5d24b2a03d42a3b363 || exit 1
  cmake -S "$BUILD/src" -B "$BUILD/b" -DCMAKE_BUILD_TYPE=Release -DLIBUVC_NUM_TRANSFER_BUFS=10 -DCMAKE_INSTALL_PREFIX="$PREFIX" >/dev/null || exit 1
  cmake --build "$BUILD/b" -j4 >/dev/null && cmake --install "$BUILD/b" >/dev/null || exit 1
fi
LIBDIR="$PREFIX/lib"; [ -d "$PREFIX/lib64" ] && LIBDIR="$PREFIX/lib64"
EXTRA=""; [ "$PLAT" = linux ] && EXTRA="-lpthread"
cc -O2 -std=c11 -o "$BUILD/uvc_multi_forced_alt" "$HERE/uvc_multi_forced_alt.c" -I"$PREFIX/include" \
   $(pkg-config --cflags --libs libusb-1.0) -L"$LIBDIR" -luvc $EXTRA -Wl,-rpath,"$LIBDIR" || exit 1
BIN="$BUILD/uvc_multi_forced_alt"
{ uname -a; id; echo "usbfs_memory_mb=$(cat /sys/module/usbcore/parameters/usbfs_memory_mb 2>/dev/null || echo n/a)";
  command -v lsusb >/dev/null && lsusb -t; } > "$OUT/environment.txt" 2>&1

run() {  # name, args...
  local name="$1"; shift
  echo "-- $name: $*"
  "$BIN" --size "$SIZE" --fps "$FPS" --seconds "$SECS" --out "$OUT/$name.json" "$@" || echo "   exit $?"
  sleep 2
}
# 1) default (camera's own request), ramp 1..N
for k in $(seq 1 ${#DEVS[@]}); do run "default_n$k" "${DEVS[@]:0:$k}"; done
# 2) forced smaller alts, all cameras
run "frac0.5_all" --override-frac 0.5 "${DEVS[@]}"
run "frac0.25_all" --override-frac 0.25 "${DEVS[@]}"
run "bytes1024_all" --override-bytes 1024 "${DEVS[@]}"
if [ "$PLAT" = macos ] && [ "$ALSO_SUDO" = 1 ]; then
  echo "-- macOS with sudo"; sudo "$BIN" --size "$SIZE" --fps "$FPS" --seconds "$SECS" --out "$OUT/sudo_default_all.json" "${DEVS[@]}"
  sudo "$BIN" --size "$SIZE" --fps "$FPS" --seconds "$SECS" --out "$OUT/sudo_frac0.5_all.json" --override-frac 0.5 "${DEVS[@]}"
  sudo chown "$(id -u)" "$OUT"/sudo_*.json
fi
echo "results in $OUT"
