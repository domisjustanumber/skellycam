#!/usr/bin/env sh
# macOS camera-identity stability workflow (USER-RUN DRAFT; unverified until you run it).
# Tests which identifiers (AVFoundation uniqueID / order / localizedName, IOKit locationID, USB serial, our
# camera_key) survive (a) reboot, (b) replug into the same port, (c) moving to a different port.
# Also records, per snapshot, whether uniqueID == 0x<locationID><vid><pid> (forum-reported, undocumented format).
# No sudo. Needs: uv on PATH (pyobjc is installed into the script env automatically).
#
#   sh research/usb_cameras/naming/macos_stability_workflow.sh baseline
#   (reboot)                       sh ... after_reboot
#   (unplug/replug, same ports)    sh ... after_replug_same_port
#   (move cameras to other ports)  sh ... after_move_port
#   sh ... diff        -> results/macos/<hostname>/naming/stability_*.json + printed table
#   sh ... snapshot <label>
set -eu
here=$(cd "$(dirname "$0")" && pwd)
snap="$here/../results/macos/$(hostname -s)/naming/snapshots"
step=${1:?usage: $0 baseline|after_reboot|after_replug_same_port|after_move_port|snapshot LABEL|diff}
case "$step" in
  diff)
    set --
    for l in baseline after_reboot after_replug_same_port after_move_port; do
      [ -f "$snap/$l.json" ] && set -- "$@" "$snap/$l.json"
    done
    [ "$#" -ge 2 ] || { echo "need >= 2 snapshots in $snap" >&2; exit 1; }
    first=$1
    uv run --script "$here/identity_diff.py" "$@"
    shift
    for f in "$@"; do uv run --script "$here/identity_diff.py" "$first" "$f"; done
    ;;
  snapshot) uv run --script "$here/macos_identity.py" --label "${2:?label}" ;;
  baseline|after_reboot|after_replug_same_port|after_move_port) uv run --script "$here/macos_identity.py" --label "$step" ;;
  *) echo "unknown step $step" >&2; exit 2 ;;
esac
