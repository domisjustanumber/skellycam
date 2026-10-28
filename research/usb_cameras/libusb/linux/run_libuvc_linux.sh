#!/usr/bin/env bash
# run_libuvc_linux.sh - DRAFTED, UNVERIFIED until run on a Linux machine with UVC webcams.
#
# What it tests (goals 1-3, 5 on Linux, all as a NORMAL USER at run time):
#   A. can a non-root user (with the udev rule from 70-skellycam-uvc.rules) open each UVC camera
#      through libusb, detach uvcvideo, negotiate PROBE/COMMIT and stream MJPEG with libuvc?
#   B. per-frame PTS/SCR/host timing from the patched libuvc (frames.jsonl, README schema)
#   C. application-chosen isochronous alt settings (bandwidth) per camera: default, and smaller alts
#   D. (--multi) all cameras streaming at once: default alts vs. reduced alts / --bandwidth-factor
#   E. whether /dev/videoN comes back after libuvc releases the camera (uvcvideo re-attach)
#
# Run from the repo root:
#   bash research/usb_cameras/libusb/linux/run_libuvc_linux.sh [--install-udev-rule] [--multi]
#        [--width 1280 --height 720 --fps 30] [--seconds 5] [--bandwidth-factor 1.5]
# Needs: git cmake build-essential pkg-config libusb-1.0-0-dev python3 (see build_unix.sh header);
#        optional: uv (for the pure-Python py-libusb1 cross-check), v4l-utils (v4l2-ctl), usbutils (lsusb).
# Permissions: run as your normal user. --install-udev-rule uses sudo ONCE to copy the rule and
#        reload udev (then unplug/replug the cameras or it triggers them). Nothing else uses sudo.
# Writes: research/usb_cameras/results/linux/<hostname>/libuvc_linux/  (summary.json + per-run dirs)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$LIB/../../.." && pwd)"
W=1280; H=720; FPS=30; SECS=5; MULTI=0; INSTALL_RULE=0; BWF=1.5
while [ $# -gt 0 ]; do
  case "$1" in
    --install-udev-rule) INSTALL_RULE=1 ;;
    --multi) MULTI=1 ;;
    --width) W="$2"; shift ;;
    --height) H="$2"; shift ;;
    --fps) FPS="$2"; shift ;;
    --seconds) SECS="$2"; shift ;;
    --bandwidth-factor) BWF="$2"; shift ;;
    *) echo "unknown option $1" >&2; exit 1 ;;
  esac
  shift
done
HOST="$(hostname)"
OUT="$REPO/research/usb_cameras/results/linux/$HOST/libuvc_linux"
mkdir -p "$OUT"
LOG="$OUT/run.log"
exec > >(tee -a "$LOG") 2>&1
echo "== $(date -u +%FT%TZ) $0 $*"

# ---- environment -------------------------------------------------------------------------
{
  echo "uname: $(uname -a)"
  echo "user: $(id)"
  echo "libusb: $(pkg-config --modversion libusb-1.0 2>/dev/null || echo missing)"
  echo "uvcvideo quirks param: $(cat /sys/module/uvcvideo/parameters/quirks 2>/dev/null || echo n/a)"
  echo "--- lsusb -t"; lsusb -t 2>/dev/null || echo "(lsusb missing)"
  echo "--- /dev/video*"; ls -l /dev/video* 2>/dev/null || echo "(none)"
} > "$OUT/environment.txt"
cat "$OUT/environment.txt"

if [ "$INSTALL_RULE" = 1 ]; then
  echo "installing udev rule (one-time sudo)"
  sudo install -m 0644 "$HERE/70-skellycam-uvc.rules" /etc/udev/rules.d/70-skellycam-uvc.rules
  sudo udevadm control --reload-rules
  sudo udevadm trigger --subsystem-match=usb --action=change
  sleep 2
fi

bash "$LIB/build_unix.sh" || { echo "build failed" >&2; exit 2; }
EXE="$LIB/build/unix/bin/uvc_capture_test"

# ---- A: enumeration + access ---------------------------------------------------------------
"$EXE" --list --json-out "$OUT/list.json" | tee "$OUT/list.txt"
echo "list exit=$?"
python3 - "$OUT/list.json" > "$OUT/cams.tsv" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for x in d["devices"]:
    if x["is_uvc"]:
        print(x["vid"], x["pid"], x["port_path"], x["bus"], x["address"], x.get("open_result"), sep="\t")
PY
echo "--- usbfs permissions for UVC devices"
while IFS=$'\t' read -r vid pid pp bus addr openres; do
  node=$(printf "/dev/bus/usb/%03d/%03d" "$bus" "$addr")
  echo "$vid:$pid $pp $node $(stat -c '%A %U:%G' "$node" 2>/dev/null) getfacl=$(getfacl -p "$node" 2>/dev/null | grep -c "user:$USER") open=$openres"
done < "$OUT/cams.tsv" | tee "$OUT/permissions.txt"

# ---- B/C: per camera: probe, default stream, reduced alts --------------------------------
while IFS=$'\t' read -r vid pid pp bus addr openres; do
  tag="${vid}_${pid}_${pp//[.-]/_}"
  echo "=== camera $vid:$pid at $pp"
  ls /dev/video* > "$OUT/${tag}_video_nodes_before.txt" 2>/dev/null
  "$EXE" --vid "$vid" --pid "$pid" --port-path "$pp" --width "$W" --height "$H" --fps "$FPS" --probe-only \
      --out-dir "$OUT/${tag}_probe" ; echo "probe exit=$?"
  "$EXE" --vid "$vid" --pid "$pid" --port-path "$pp" --width "$W" --height "$H" --fps "$FPS" --seconds "$SECS" \
      --save-jpeg 2 --out-dir "$OUT/${tag}_default" ; echo "default exit=$?"
  # smaller alt settings: every 3rd iso alt below the default one (from the result json)
  alts=$(python3 - "$OUT/${tag}_default/result.json" <<'PY' 2>/dev/null
import json, sys
r = json.load(open(sys.argv[1]))
chosen = r["iso"]["chosen_altsetting"]
alts = sorted({a["alt"] for a in r["cameras"][0]["vs_altsettings"] if a["type"] == 1 and a["alt"] < chosen})
print(" ".join(map(str, alts[::-3][:4])))
PY
)
  for alt in $alts; do
    "$EXE" --vid "$vid" --pid "$pid" --port-path "$pp" --width "$W" --height "$H" --fps "$FPS" --seconds "$SECS" \
        --alt "$alt" --out-dir "$OUT/${tag}_alt$alt" ; echo "alt $alt exit=$?"
  done
  "$EXE" --vid "$vid" --pid "$pid" --port-path "$pp" --width "$W" --height "$H" --fps "$FPS" --seconds "$SECS" \
      --bandwidth-factor "$BWF" --out-dir "$OUT/${tag}_bwf$BWF" ; echo "bwf exit=$?"
  sleep 2
  ls /dev/video* > "$OUT/${tag}_video_nodes_after.txt" 2>/dev/null
done < "$OUT/cams.tsv"

# ---- D: all cameras at once ------------------------------------------------------------------
if [ "$MULTI" = 1 ]; then
  for mode in default bwf; do
    pids=()
    while IFS=$'\t' read -r vid pid pp bus addr openres; do
      tag="${vid}_${pid}_${pp//[.-]/_}"
      extra=(); [ "$mode" = bwf ] && extra=(--bandwidth-factor "$BWF")
      "$EXE" --vid "$vid" --pid "$pid" --port-path "$pp" --width "$W" --height "$H" --fps "$FPS" --seconds "$SECS" \
          "${extra[@]}" --out-dir "$OUT/multi_${mode}_${tag}" > "$OUT/multi_${mode}_${tag}.log" 2>&1 &
      pids+=($!)
    done < "$OUT/cams.tsv"
    for p in "${pids[@]}"; do wait "$p"; done
  done
fi

# ---- pure-Python cross-check (optional) --------------------------------------------------------
if command -v uv >/dev/null; then
  (cd "$REPO" && uv run --script research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py --list \
      --out-dir "$OUT/py_libusb1_list") ; echo "py_libusb1 list exit=$?"
fi

# ---- summary ---------------------------------------------------------------------------------
python3 - "$OUT" <<'PY'
import json, sys, glob, os, socket, datetime
out = sys.argv[1]
runs = {}
for f in sorted(glob.glob(os.path.join(out, "*", "result.json"))):
    try:
        r = json.load(open(f))
    except Exception as e:
        runs[os.path.basename(os.path.dirname(f))] = {"error": repr(e)}
        continue
    m, iso = r.get("measurements", {}), r.get("iso", {})
    runs[os.path.basename(os.path.dirname(f))] = {
        "frames": m.get("frames"), "fps": m.get("fps_from_arrivals"), "jpeg_ok": m.get("jpeg_soi_eoi_ok"),
        "error_payloads": m.get("error_payloads"), "with_pts": m.get("frames_with_pts"), "with_scr": m.get("frames_with_scr"),
        "alt": iso.get("chosen_altsetting"), "bytes_per_packet": iso.get("bytes_per_packet"),
        "start_error": iso.get("stream_start_error_name"),
        "dwMaxPayloadTransferSize": r.get("negotiation", {}).get("commit", {}).get("dwMaxPayloadTransferSize")}
s = {"test": "libuvc_linux", "platform": "linux", "hostname": socket.gethostname(),
     "utc_finished": datetime.datetime.now(datetime.timezone.utc).isoformat(),
     "command": "bash research/usb_cameras/libusb/linux/run_libuvc_linux.sh " + " ".join(sys.argv[2:]),
     "environment": open(os.path.join(out, "environment.txt")).read(), "runs": runs}
json.dump(s, open(os.path.join(out, "summary.json"), "w"), indent=2)
print(json.dumps(runs, indent=1))
PY
echo "wrote $OUT/summary.json"
