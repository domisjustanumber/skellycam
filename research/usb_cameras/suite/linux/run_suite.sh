#!/usr/bin/env bash
# Linux UVC test suite entry point (docs/xplat_capture_plan.md sections 2.6 and 6).
#
#   bash research/usb_cameras/suite/linux/run_suite.sh [run_suite.py flags]     e.g. --quick, --only MJPEG,CYC
#   bash research/usb_cameras/suite/linux/run_suite.sh --dry-run                plan only; opens no /dev node
#   bash research/usb_cameras/suite/linux/run_suite.sh --help
#
# What it does:
#   1. installs uv into ~/.local/bin if it is missing (official installer, user-level, no sudo);
#      set SKELLYCAM_NO_BOOTSTRAP=1 to refuse, or SKELLYCAM_PYTHON_ONLY=1 to run with the system python3
#      (then strict JPEG decode and image metrics are unavailable unless pillow/numpy/simplejpeg are installed);
#   2. prints distro, kernel and session to stderr (run_suite.py records them in run.json too);
#   3. runs: uv run --python 3.12 --script run_suite.py "$@"
#
# Never uses sudo. Run it from the desktop session (logind gives the active seat an ACL on /dev/video*); over SSH
# the user needs the 'video' group (tier 1, reported by L-ENV / L-DESK).
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_VERSION="${SKELLYCAM_PYTHON:-3.12}"
say() { echo "$@" >&2; }   # banner on stderr: stdout stays the runner's (pure JSON for --dry-run)

say "== skellycam Linux UVC suite =="
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  say "distro:  ${PRETTY_NAME:-unknown} (${ID:-?} ${VERSION_ID:-?})"
fi
say "kernel:  $(uname -r) $(uname -m)"
say "session: XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-none} XDG_CURRENT_DESKTOP=${XDG_CURRENT_DESKTOP:-none} SSH=${SSH_CONNECTION:+yes}"
say "groups:  $(id -nG 2>/dev/null)"
if [ -d /sys/module/uvcvideo ]; then
  say "uvcvideo: loaded; quirks=$(cat /sys/module/uvcvideo/parameters/quirks 2>/dev/null) hwtimestamps=$(cat /sys/module/uvcvideo/parameters/hwtimestamps 2>/dev/null) nodrop=$(cat /sys/module/uvcvideo/parameters/nodrop 2>/dev/null)"
else
  say "uvcvideo: not loaded"
fi

if [ "${SKELLYCAM_PYTHON_ONLY:-0}" = "1" ]; then
  say "running with system python3 (SKELLYCAM_PYTHON_ONLY=1)"
  exec python3 "$HERE/run_suite.py" "$@"
fi

if ! command -v uv >/dev/null 2>&1; then
  if [ -x "$HOME/.local/bin/uv" ]; then
    export PATH="$HOME/.local/bin:$PATH"
  elif [ "${SKELLYCAM_NO_BOOTSTRAP:-0}" = "1" ]; then
    echo "uv not found and SKELLYCAM_NO_BOOTSTRAP=1; install uv (https://docs.astral.sh/uv/) or set SKELLYCAM_PYTHON_ONLY=1" >&2
    exit 2
  else
    say "uv not found: installing it for this user into ~/.local/bin (no sudo)"
    if command -v curl >/dev/null 2>&1; then
      curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >&2 || { echo "uv install failed" >&2; exit 2; }
    elif command -v wget >/dev/null 2>&1; then
      wget -qO- https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >&2 || { echo "uv install failed" >&2; exit 2; }
    else
      echo "neither curl nor wget available to fetch uv" >&2
      exit 2
    fi
    export PATH="$HOME/.local/bin:$PATH"
  fi
fi
say "uv:      $(uv --version 2>/dev/null)"
say ""

exec uv run --python "$PY_VERSION" --script "$HERE/run_suite.py" "$@"
