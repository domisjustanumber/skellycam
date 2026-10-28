#!/usr/bin/env bash
# UNVERIFIED DRAFT -- written on Windows, never run on macOS (bash -n / py_compile only; see results/windows/Gerald/mjpeg_drafts_check/). Review the first run's output before trusting it.
#
# Goal-1 (native MJPEG extraction) matrix on macOS:
#   A. AVFoundation AVCaptureVideoDataOutput probe (avf_mjpeg_probe.py): list devices/formats, then capture each
#      camera at 1280x720@30 with videoSettings=nil and videoSettings={} -> does it ever hand over compressed
#      'dmb1'/'jpeg' CMBlockBuffers, or always decoded CVPixelBuffers?
#   B. PyAV/FFmpeg avfoundation (mjpeg/pyav/pyav_capture.py --input-format avfoundation): (a) default options,
#      (b) each pixel_format FFmpeg's avfoundation demuxer accepts, (c) vcodec=mjpeg. FFmpeg's avfoundation demuxer is
#      documented to output raw pixels; this records the delivered codec (rawvideo vs mjpeg) for every attempt and
#      whether FFmpeg rejects the option.
#
# WHAT TO RUN (from a LOCAL Terminal/iTerm2 window, not SSH, the first time -- see permissions):
#     bash research/usb_cameras/mjpeg/drafts/macos/run_macos_mjpeg.sh
#   env overrides: SECONDS_PER_RUN (default 10, AVF probe), PYAV_SECONDS (default 5: raw-pixel attempts buffer every
#   frame in RAM, ~1.8 MB/frame at 720p), WARMUP (default 2)
#
# NEEDS: macOS 12+, `uv` on PATH, USB (UVC) camera(s), camera permission for the terminal app
#   (System Settings > Privacy & Security > Camera; the probe asks once and waits 30 s; after enabling, quit and
#   reopen the terminal). No sudo. Close other apps using the cameras. ffmpeg CLI optional (only to save its device list).
#
# WRITES  research/usb_cameras/results/macos/<hostname>/mjpeg_run_<UTC stamp>/   (a new directory per invocation)
#     mjpeg_avf_list/devices.json
#     mjpeg_avf_videodataoutput/1280x720at30_<none|empty>_cam<i>/summary.json, frames.jsonl, run.log
#     mjpeg_pyav_avfoundation/1280x720at30_<attempt>_cam<i>/summary.json, frames.jsonl, run.log
#        attempts: default, pixfmt_<fmt>, vcodec_mjpeg; summary.json has delivered_codec, ffmpeg_option, avfoundation_attempt
#     mjpeg_pyav_avfoundation/ffmpeg_list_devices.txt  (if the ffmpeg CLI exists)
#     <test>/<label>/failure.json for every attempt that failed (error text, command, return code)
#     table.json, table.md  (aggregate.py --root <run root> --ref-test mjpeg_avf_videodataoutput)
#   Raw run dirs (frames_*.bin) go under $MJPEG_SCRATCH (default $TMPDIR/usb_cameras_mjpeg_scratch) and can be deleted.
set -uo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MJPEG_DIR="$(cd "$HERE/../.." && pwd)"
USB_ROOT="$(cd "$MJPEG_DIR/.." && pwd)"
PROBE_PY="$HERE/avf_mjpeg_probe.py"
PYAV_PY="$MJPEG_DIR/pyav/pyav_capture.py"
SUMMARIZE_PY="$MJPEG_DIR/summarize.py"
AGGREGATE_PY="$MJPEG_DIR/aggregate.py"
SECS="${SECONDS_PER_RUN:-10}"
PYAV_SECS="${PYAV_SECONDS:-5}"
WARMUP="${WARMUP:-2}"
export MJPEG_SCRATCH="${MJPEG_SCRATCH:-${TMPDIR:-/tmp}/usb_cameras_mjpeg_scratch}"
mkdir -p "$MJPEG_SCRATCH"
# pixel formats accepted by FFmpeg's avfoundation demuxer (libavdevice/avfoundation.m avf_pixel_formats) that
# UVC cameras plausibly offer; anything else is rejected with "Selected pixel format (...) is not supported".
PIXFMTS=(uyvy422 yuyv422 nv12 0rgb bgr0)

[ "$(uname -s)" = "Darwin" ] || die "this runner is for macOS (uname -s = $(uname -s))"
command -v uv >/dev/null 2>&1 || die "uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh  (then open a new terminal)"
for f in "$PROBE_PY" "$PYAV_PY" "$SUMMARIZE_PY" "$AGGREGATE_PY"; do [ -f "$f" ] || die "missing $f"; done
HOST="$(uv run --no-project --quiet python -c 'import socket; print(socket.gethostname())' 2>/dev/null || hostname)"
RES="$USB_ROOT/results/macos/$HOST/mjpeg_run_$(date -u +%Y%m%dT%H%M%SZ)"   # never reuse/overwrite an earlier run
mkdir -p "$RES/mjpeg_avf_list" "$RES/mjpeg_pyav_avfoundation"
echo "results -> $RES"

write_failure() {  # test label rc log cmd...
  local test="$1" label="$2" rc="$3" log="$4"; shift 4
  uv run --no-project --quiet python - "$RES/$test/$label/failure.json" "$test" "$label" "$rc" "$log" "$@" <<'PY'
import json, sys, socket, platform, datetime, pathlib
out, test, label, rc, log, *cmd = sys.argv[1:]
p = pathlib.Path(log)
txt = p.read_text(errors="replace") if p.exists() else ""
doc = {"test": test, "label": label, "platform": "macos", "hostname": socket.gethostname(),
       "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "os": platform.platform(),
       "command": cmd, "returncode": int(rc), "error_text": txt[-8000:]}
pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
pathlib.Path(out).write_text(json.dumps(doc, indent=1))
print("wrote", out)
PY
}

# ------------------------------------------------------------------ list (also triggers/validates camera permission)
echo "== listing AVFoundation devices"
uv run --script "$PROBE_PY" --list --root "$RES" > /dev/null 2> "$RES/mjpeg_avf_list/list.log"; rc=$?
if [ $rc -eq 3 ]; then cat "$RES/mjpeg_avf_list/list.log" >&2; die "camera permission not granted (see above)"; fi
[ $rc -eq 0 ] || { cat "$RES/mjpeg_avf_list/list.log" >&2; die "avf_mjpeg_probe.py --list failed (rc=$rc)"; }
TSV="$(uv run --script "$PROBE_PY" --list-tsv)" || die "avf_mjpeg_probe.py --list-tsv failed"
[ -n "$TSV" ] || die "AVFoundation reports no video devices"
echo "devices (index, uniqueID, name, compressed subtypes, has 1280x720@30):"
printf '%s\n' "$TSV" | sed 's/^/  /'
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -hide_banner -f avfoundation -list_devices true -i "" > "$RES/mjpeg_pyav_avfoundation/ffmpeg_list_devices.txt" 2>&1 || true
  echo "ffmpeg device order saved (compare with the AVF index order above; they can differ)"
fi

FAILS=0
# ------------------------------------------------------------------ A. AVF probe
run_probe() {  # idx variant
  local idx="$1" variant="$2" label="1280x720at30_${2}_cam${1}"
  local dir="$RES/mjpeg_avf_videodataoutput/$label"; mkdir -p "$dir"
  local cmd=(uv run --script "$PROBE_PY" --device "$idx" --size 1280x720 --fps 30 --variant "$variant" --seconds "$SECS" --warmup "$WARMUP" --label "$label" --keep-samples 1 --root "$RES")
  echo "== [avf probe] $label"
  "${cmd[@]}" < /dev/null > "$dir/run.log" 2>&1; local rc=$?
  tail -n 4 "$dir/run.log"
  if [ $rc -ne 0 ]; then write_failure mjpeg_avf_videodataoutput "$label" "$rc" "$dir/run.log" "${cmd[@]}"; FAILS=$((FAILS+1)); fi
  sleep 1
}

# ------------------------------------------------------------------ B. PyAV avfoundation
run_pyav() {  # idx attempt_name [--option k=v]
  local idx="$1" attempt="$2"; shift 2
  local label="1280x720at30_${attempt}_cam${idx}"
  # FFmpeg's avfoundation device index can differ from the AVF devicesWithMediaType order used for <idx>, so pass the
  # device NAME when it is unique and has no ':' (FFmpeg's video:audio separator); otherwise fall back to the index.
  local fdev="$idx" nm
  nm="$(awk -F'\t' -v i="$idx" '$1==i {print $3}' <<< "$TSV")"
  if [ -n "$nm" ] && [[ "$nm" != *:* ]] && [ "$(awk -F'\t' -v n="$nm" '$3==n' <<< "$TSV" | wc -l)" -eq 1 ]; then fdev="$nm"; fi
  local dir="$RES/mjpeg_pyav_avfoundation/$label"; mkdir -p "$dir"
  local rd; rd="$(mktemp -d "$MJPEG_SCRATCH/pyav_avf_XXXXXX")"
  local opt="${2:-}"   # value after --option, for the summary
  local cmd=(uv run --script "$PYAV_PY" --input-format avfoundation --device "$fdev" --size 1280x720 --fps 30 --seconds "$PYAV_SECS" --warmup "$WARMUP" --run-dir "$rd" "$@")
  echo "== [pyav avfoundation] $label device='$fdev' ${opt:+(option $opt)}"
  "${cmd[@]}" < /dev/null > "$dir/run.log" 2>&1; local rc=$?
  # pyav_capture.py ends with one JSON line: {"cameras":[{"name","codec","pix_fmt",...}],"errors":[...]}
  local codec pixfmt
  codec="$(grep -o '"codec": "[^"]*"' "$dir/run.log" | head -n1 | cut -d'"' -f4)"
  pixfmt="$(grep -o '"pix_fmt": "[^"]*"' "$dir/run.log" | head -n1 | cut -d'"' -f4)"
  if [ $rc -ne 0 ] || [ -z "$codec" ] || [ ! -f "$rd/meta.json" ]; then
    echo "   -> failed / rejected (rc=$rc); see $dir/failure.json"
    tail -n 4 "$dir/run.log"
    write_failure mjpeg_pyav_avfoundation "$label" "$rc" "$dir/run.log" "${cmd[@]}"; FAILS=$((FAILS+1)); sleep 1; return
  fi
  local notjpeg=() passthrough=false decoded=null
  case "$codec" in
    mjpeg|mjpg|jpeg) passthrough=true; decoded=false ;;
    *) notjpeg=(--not-jpeg) ;;
  esac
  # extra keys are merged last into summary.json, so decoded_by_pipeline here overrides pyav_capture's FFmpeg-only 'false'
  local extra
  extra="$(printf '{"avfoundation_attempt": "%s", "ffmpeg_device": "%s", "ffmpeg_option": "%s", "delivered_codec": "%s", "delivered_pix_fmt": "%s", "mjpeg_passthrough": %s, "decoded_by_pipeline": %s, "decode_evidence": "FFmpeg never decodes (demux only). delivered_codec=%s: rawvideo means AVFoundation handed FFmpeg pixels, i.e. any MJPEG on the wire was decoded upstream of FFmpeg (null = wire format not determined here)"}' \
    "$attempt" "${fdev//\"/}" "${opt:-}" "$codec" "$pixfmt" "$passthrough" "$decoded" "$codec")"
  uv run --script "$SUMMARIZE_PY" "$rd" --test mjpeg_pyav_avfoundation --label "$label" --keep-samples 1 --root "$RES" ${notjpeg[@]+"${notjpeg[@]}"} \
      --command "${cmd[*]}" --extra "$extra" < /dev/null >> "$dir/run.log" 2>&1; rc=$?
  tail -n 4 "$dir/run.log"
  echo "   -> delivered codec: $codec ($pixfmt)"
  if [ $rc -ne 0 ]; then write_failure mjpeg_pyav_avfoundation "$label" "$rc" "$dir/run.log" "${cmd[@]}"; FAILS=$((FAILS+1)); fi
  sleep 1
}

while IFS=$'\t' read -r idx uid name comp has720; do
  [ -n "$idx" ] || continue
  echo "######## camera $idx: $name ($uid) compressed formats: $comp"
  if [ "$has720" = "1" ]; then
    run_probe "$idx" none
    run_probe "$idx" empty
  else
    echo "== skip AVF probe for cam$idx: no 1280x720@30 format (see devices.json; run the probe by hand with --size/--fps/--format-index)"
  fi
  run_pyav "$idx" default
  for pf in "${PIXFMTS[@]}"; do run_pyav "$idx" "pixfmt_$pf" --option "pixel_format=$pf"; done
  run_pyav "$idx" vcodec_mjpeg --option "vcodec=mjpeg"
done <<< "$TSV"

uv run --script "$AGGREGATE_PY" --root "$RES" --ref-test mjpeg_avf_videodataoutput --markdown < /dev/null > "$RES/aggregate.log" 2>&1   || echo "aggregate.py failed (see $RES/aggregate.log)"
echo "done. $FAILS failed attempt(s) (failures are expected for unsupported pixel formats). Results under $RES (table: $RES/table.md)"
exit 0
