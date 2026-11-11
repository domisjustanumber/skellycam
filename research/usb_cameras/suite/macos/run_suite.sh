#!/usr/bin/env bash
# macOS UVC test suite entry point (docs/xplat_capture_plan.md sections 2.5 and 6).
#
#   bash research/usb_cameras/suite/macos/run_suite.sh [run_suite.py flags]      e.g. --quick, --ep0, --dry-run
#
# What this wrapper does before handing over to run_suite.py:
#   1. finds uv (installs it into ~/.local/bin with the official installer if it is missing, after saying so);
#   2. records sw_vers, uname -m, hw.model, CPU, Rosetta translation, the launching terminal app, and whether this
#      is an SSH session, into a prelude JSON that run_suite.py copies into every result;
#   3. reminds about camera permission (TCC): it belongs to the app that launched this script (Terminal, iTerm2,
#      VS Code, ...). Without it every capture silently delivers zero frames. Grant it in System Settings >
#      Privacy & Security > Camera, then quit and reopen the terminal app. Over SSH there is no prompt.
#   4. reminds to close apps that hold or change cameras (Photo Booth, FaceTime, Zoom, Logi Tune, browsers) and to
#      turn Edge Light off (Control Center > Video Effects); pass --edge-light-off once checked.
# Nothing here opens a camera, needs sudo, or changes any system setting.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_VERSION="${SKELLYCAM_SUITE_PYTHON:-3.12}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "note: not macOS; only --help / --dry-run / --list-tests are useful here" >&2
fi

if ! command -v uv >/dev/null 2>&1; then
  if [[ -x "$HOME/.local/bin/uv" ]]; then
    export PATH="$HOME/.local/bin:$PATH"
  else
    echo "uv not found: installing it to ~/.local/bin with the official installer (https://astral.sh/uv)" >&2
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
fi

PRELUDE_DIR="${TMPDIR:-/tmp}"
PRELUDE="$(mktemp "${PRELUDE_DIR%/}/skellycam_mac_prelude.XXXXXX")"
trap 'rm -f "$PRELUDE"' EXIT

val() { "$@" 2>/dev/null | head -n 1 | tr -d '"\\' || true; }
PRODUCT_VERSION="$(val sw_vers -productVersion)"
BUILD_VERSION="$(val sw_vers -buildVersion)"
PRODUCT_NAME="$(val sw_vers -productName)"
ARCH="$(val uname -m)"
HW_MODEL="$(val sysctl -n hw.model)"
CPU="$(val sysctl -n machdep.cpu.brand_string)"
TRANSLATED="$(val sysctl -n sysctl.proc_translated)"
UV_VERSION="$(val uv --version)"
cat >"$PRELUDE" <<EOF
{"product_name": "${PRODUCT_NAME}", "product_version": "${PRODUCT_VERSION}", "build_version": "${BUILD_VERSION}",
 "arch": "${ARCH}", "hw_model": "${HW_MODEL}", "cpu": "${CPU}", "proc_translated": "${TRANSLATED:-0}",
 "term_program": "${TERM_PROGRAM:-}", "bundle_id": "${__CFBundleIdentifier:-}", "ssh": "${SSH_CONNECTION:+yes}",
 "uv": "${UV_VERSION}", "wrapper": "run_suite.sh"}
EOF
export SKELLYCAM_MAC_PRELUDE="$PRELUDE"

echo "macOS ${PRODUCT_VERSION:-?} (${BUILD_VERSION:-?}) on ${ARCH:-?} ${HW_MODEL:-?}; ${UV_VERSION:-uv ?}" >&2
if [[ "${TRANSLATED:-0}" == "1" ]]; then
  echo "WARNING: this shell runs under Rosetta; use a native arm64 terminal" >&2
fi
echo "Camera permission belongs to: ${TERM_PROGRAM:-${__CFBundleIdentifier:-the launching app}}." >&2
if [[ -n "${SSH_CONNECTION:-}" ]]; then
  echo "WARNING: SSH session: no permission prompt can appear; grant Camera to a local terminal first." >&2
fi
echo "Close Photo Booth / FaceTime / Zoom / Logi Tune / browsers using a camera; turn Edge Light off." >&2

# The trap removes the prelude when the runner returns, so do not exec.
uv run --python "$PY_VERSION" --script "$HERE/run_suite.py" "$@"
