#!/usr/bin/env bash
# build_unix.sh - build patched libuvc + uvc_capture_test on Linux or macOS against the SYSTEM libusb.
#
#   bash research/usb_cameras/libusb/build_unix.sh            # -> research/usb_cameras/libusb/build/unix/bin/
# Needs: git, cmake >= 3.18, a C compiler, pkg-config, libusb-1.0 development files
#   Debian/Ubuntu: sudo apt-get install -y git cmake build-essential pkg-config libusb-1.0-0-dev
#   Fedora:        sudo dnf install -y git cmake gcc pkgconf-pkg-config libusb1-devel
#   macOS:         brew install libusb cmake pkg-config
# No root needed to build. Pins the same libuvc commit + patch as build_windows.ps1.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBUVC_URL=https://github.com/libuvc/libuvc.git
LIBUVC_COMMIT=d07de4fa23905ee8cac06f5d24b2a03d42a3b363
BUILD="${BUILD_DIR:-$HERE/build/unix}"
DEPS="$BUILD/deps"
mkdir -p "$DEPS"

for t in git cmake pkg-config cc; do
  command -v "$t" >/dev/null || { echo "ERROR: '$t' not found (see header for install command)" >&2; exit 2; }
done
pkg-config --exists libusb-1.0 || { echo "ERROR: libusb-1.0 development files not found by pkg-config" >&2; exit 2; }

if [ ! -d "$DEPS/libuvc/.git" ]; then
  git clone -q "$LIBUVC_URL" "$DEPS/libuvc"
fi
git -C "$DEPS/libuvc" fetch -q origin || true
git -C "$DEPS/libuvc" checkout -q --force "$LIBUVC_COMMIT"
git -C "$DEPS/libuvc" reset -q --hard "$LIBUVC_COMMIT"
git -C "$DEPS/libuvc" clean -qfdx
for p in "$HERE"/patches/*.patch; do
  echo "applying $(basename "$p")"
  git -C "$DEPS/libuvc" apply --whitespace=nowarn "$p"
done

cmake -S "$HERE" -B "$BUILD/cmake" -DCMAKE_BUILD_TYPE=Release \
  -DLIBUVC_SOURCE_DIR="$DEPS/libuvc" -DCMAKE_C_FLAGS="-DLIBUVC_GIT_COMMIT=\\\"$LIBUVC_COMMIT\\\""
cmake --build "$BUILD/cmake" -j
mkdir -p "$BUILD/bin"
cp "$BUILD/cmake/bin/uvc_capture_test" "$BUILD/cmake/bin/example" "$BUILD/bin/" 2>/dev/null || \
  find "$BUILD/cmake" -type f \( -name uvc_capture_test -o -name example \) -perm -u+x -exec cp {} "$BUILD/bin/" \;
echo "libusb: $(pkg-config --modversion libusb-1.0)"
echo "OK: $BUILD/bin/uvc_capture_test"
