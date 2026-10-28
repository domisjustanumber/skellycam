#!/usr/bin/env bash
# UNVERIFIED DRAFT -- written on Windows, never run on Linux (bash -n / py_compile / --selftest only; see results/windows/Gerald/mjpeg_drafts_check/). Review the first run's output before trusting it.
#
# Goal-1 (native MJPEG extraction) matrix on Linux: pure-Python V4L2 mmap capture + PyAV/FFmpeg v4l2 passthrough.
#
# WHAT TO RUN (from anywhere; paths are resolved from this file's location):
#     bash research/usb_cameras/mjpeg/drafts/linux/run_linux_mjpeg.sh
#   env overrides: SECONDS_PER_RUN (default 10), WARMUP (default 2), EXTRA_V4L2_ARGS (e.g. "--exposure-abs 78 --manual-wb 4500")
#
# NEEDS: 64-bit Linux, `uv` on PATH, one or more UVC cameras offering MJPG, the user in the 'video' group
#   (no sudo is used; the script checks and explains). v4l2-ctl (package v4l-utils) is optional: if present it is
#   used to enumerate MJPG capture nodes and its --list-formats-ext output is saved; otherwise the Python --list mode is used.
#   No other program may have the cameras open.
#
# RUNS, per MJPG camera:  1280x720@30 (if the camera offers it) with both backends, one camera at a time;
#   then all cameras together at 1280x720@30; then each camera alone at its max MJPEG mode (largest WxH, highest fps).
#
# WRITES  research/usb_cameras/results/linux/<hostname>/mjpeg_run_<UTC stamp>/   (a new directory per invocation)
#     mjpeg_v4l2_list/devices.json                       (enumeration; + v4l2-ctl_<videoN>.txt when v4l2-ctl exists)
#     mjpeg_v4l2_mmap/<label>/summary.json, frames.jsonl  (pure-Python V4L2)
#     mjpeg_pyav_v4l2/<label>/summary.json, frames.jsonl  (PyAV demux, via summarize.py)
#     <test>/<label>/run.log for every attempt, and <test>/<label>/failure.json when an attempt fails
#   labels: 1280x720at30_<videoN>, 1280x720at30_all_<videoN+videoM...>, max_<W>x<H>at<fps>_<videoN>
#     table.json, table.md                                  (aggregate.py --root <run root> --ref-test mjpeg_v4l2_mmap:
#                                                            pyav-v4l2 bytes vs. the pure-V4L2 bytes -> native yes/NO)
#   Raw run dirs (frames_*.bin) go under $MJPEG_SCRATCH (default /tmp/usb_cameras_mjpeg_scratch) and can be deleted.
set -uo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MJPEG_DIR="$(cd "$HERE/../.." && pwd)"            # research/usb_cameras/mjpeg
USB_ROOT="$(cd "$MJPEG_DIR/.." && pwd)"            # research/usb_cameras
V4L2_PY="$HERE/v4l2_mmap_mjpeg.py"
PYAV_PY="$MJPEG_DIR/pyav/pyav_capture.py"
SUMMARIZE_PY="$MJPEG_DIR/summarize.py"
AGGREGATE_PY="$MJPEG_DIR/aggregate.py"
SECS="${SECONDS_PER_RUN:-10}"
WARMUP="${WARMUP:-2}"
# shellcheck disable=SC2206
EXTRA_V4L2=(${EXTRA_V4L2_ARGS:-})
export MJPEG_SCRATCH="${MJPEG_SCRATCH:-/tmp/usb_cameras_mjpeg_scratch}"
mkdir -p "$MJPEG_SCRATCH"

# ------------------------------------------------------------------ preflight
[ "$(uname -s)" = "Linux" ] || die "this runner is for Linux (uname -s = $(uname -s))"
command -v uv >/dev/null 2>&1 || die "uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh  (then open a new shell)"
for f in "$V4L2_PY" "$PYAV_PY" "$SUMMARIZE_PY" "$AGGREGATE_PY"; do [ -f "$f" ] || die "missing $f"; done
shopt -s nullglob
NODES=(/dev/video*)
[ ${#NODES[@]} -gt 0 ] || die "no /dev/video* nodes. Is a camera plugged in and is the uvcvideo module loaded? (lsmod | grep uvcvideo)"
if ! id -nG | tr ' ' '\n' | grep -qx video; then
  unreadable=0
  for n in "${NODES[@]}"; do [ -r "$n" ] && [ -w "$n" ] || unreadable=1; done
  if [ "$unreadable" = 1 ]; then
    die "user '$(id -un)' is not in the 'video' group and cannot open ${NODES[*]}.
  Fix (once, needs an admin):  sudo usermod -aG video $(id -un)
  then log out and back in (or reboot) and re-run. This script never uses sudo itself."
  fi
  echo "note: not in 'video' group, but /dev/video* are readable+writable (e.g. via logind seat ACLs); continuing."
fi
HOST="$(uv run --no-project --quiet python -c 'import socket; print(socket.gethostname())' 2>/dev/null || uname -n)"
RES="$USB_ROOT/results/linux/$HOST/mjpeg_run_$(date -u +%Y%m%dT%H%M%SZ)"   # never reuse/overwrite an earlier run
mkdir -p "$RES/mjpeg_v4l2_list"
echo "results -> $RES"

# write results/<test>/<label>/failure.json (uv's python does the JSON escaping)
write_failure() {  # test label rc log cmd...
  local test="$1" label="$2" rc="$3" log="$4"; shift 4
  uv run --no-project --quiet python - "$RES/$test/$label/failure.json" "$test" "$label" "$rc" "$log" "$@" <<'PY'
import json, sys, socket, platform, datetime, pathlib
out, test, label, rc, log, *cmd = sys.argv[1:]
p = pathlib.Path(log)
txt = p.read_text(errors="replace") if p.exists() else ""
doc = {"test": test, "label": label, "platform": "linux", "hostname": socket.gethostname(),
       "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "os": platform.platform(),
       "command": cmd, "returncode": int(rc), "error_text": txt[-8000:]}
pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
pathlib.Path(out).write_text(json.dumps(doc, indent=1))
print("wrote", out)
PY
}

# ------------------------------------------------------------------ enumerate MJPG capture nodes
echo "== enumerating (python --list -> $RES/mjpeg_v4l2_list/devices.json)"
uv run --script "$V4L2_PY" --list --root "$RES" > "$RES/mjpeg_v4l2_list/devices_stdout.json" 2> "$RES/mjpeg_v4l2_list/list.log" \
  || { cat "$RES/mjpeg_v4l2_list/list.log" >&2; die "v4l2_mmap_mjpeg.py --list failed (see $RES/mjpeg_v4l2_list/list.log)"; }
rm -f "$RES/mjpeg_v4l2_list/devices_stdout.json"   # same content as devices.json
TSV="$(uv run --script "$V4L2_PY" --list-tsv)" || die "v4l2_mmap_mjpeg.py --list-tsv failed"

declare -a CAMS=()
if command -v v4l2-ctl >/dev/null 2>&1; then
  echo "== v4l2-ctl present: using it to pick MJPG capture nodes"
  for n in "${NODES[@]}"; do
    out="$(v4l2-ctl -d "$n" --list-formats-ext 2>&1)" || continue
    printf '%s\n' "$out" > "$RES/mjpeg_v4l2_list/v4l2-ctl_$(basename "$n").txt"
    printf '%s\n' "$out" | grep -q "'MJPG'" && CAMS+=("$n")
  done
else
  echo "== v4l2-ctl not installed (optional: sudo apt install v4l-utils); using --list-tsv"
  while IFS=$'\t' read -r path _rest; do [ -n "$path" ] && CAMS+=("$path"); done <<< "$TSV"
fi
[ ${#CAMS[@]} -gt 0 ] || die "no capture node offers MJPG. See $RES/mjpeg_v4l2_list/devices.json"

tsv_field() {  # node fieldno  (1 path, 2 card, 3 has720p30, 4 maxWxH, 5 maxfps, 6 key)
  awk -F'\t' -v n="$1" -v f="$2" '$1==n {print $f}' <<< "$TSV"
}
echo "cameras with MJPG:"
for c in "${CAMS[@]}"; do
  echo "  $c  $(tsv_field "$c" 2)  720p30=$(tsv_field "$c" 3)  max=$(tsv_field "$c" 4)@$(tsv_field "$c" 5)  key=$(tsv_field "$c" 6)"
done

# ------------------------------------------------------------------ runners
FAILS=0
run_v4l2() {  # label size fps dev...
  local label="$1" size="$2" fps="$3"; shift 3
  local args=() d
  for d in "$@"; do args+=(--device "$d"); done
  local dir="$RES/mjpeg_v4l2_mmap/$label"; mkdir -p "$dir"
  local cmd=(uv run --script "$V4L2_PY" "${args[@]}" --size "$size" --fps "$fps" --seconds "$SECS" --warmup "$WARMUP" --label "$label" --keep-samples 1 --root "$RES" ${EXTRA_V4L2[@]+"${EXTRA_V4L2[@]}"})
  echo "== [v4l2-mmap] $label"
  "${cmd[@]}" < /dev/null > "$dir/run.log" 2>&1; local rc=$?
  tail -n 6 "$dir/run.log"
  if [ $rc -ne 0 ]; then
    echo "   -> rc=$rc (2 = driver substituted a non-MJPEG format; see summary.json silent_format_fallback)"
    write_failure mjpeg_v4l2_mmap "$label" "$rc" "$dir/run.log" "${cmd[@]}"; FAILS=$((FAILS+1))
  fi
  sleep 1
}

run_pyav() {  # label size fps dev...
  local label="$1" size="$2" fps="$3"; shift 3
  local args=() d
  for d in "$@"; do args+=(--device "$d"); done
  local dir="$RES/mjpeg_pyav_v4l2/$label"; mkdir -p "$dir"
  local rd; rd="$(mktemp -d "$MJPEG_SCRATCH/pyav_v4l2_XXXXXX")"
  local cmd=(uv run --script "$PYAV_PY" --input-format v4l2 "${args[@]}" --size "$size" --fps "$fps" --seconds "$SECS" --warmup "$WARMUP" --run-dir "$rd")
  echo "== [pyav-v4l2] $label"
  "${cmd[@]}" < /dev/null > "$dir/run.log" 2>&1; local rc=$?
  # pyav_capture writes meta.json even when every open fails, so also require at least one camera with a codec
  # in its final JSON line ({"cameras":[{"codec": ...}], "errors": [...]}).
  if [ $rc -ne 0 ] || [ ! -f "$rd/meta.json" ] || ! grep -q '"codec": "' "$dir/run.log"; then
    tail -n 6 "$dir/run.log"; write_failure mjpeg_pyav_v4l2 "$label" "$rc" "$dir/run.log" "${cmd[@]}"; FAILS=$((FAILS+1)); sleep 1; return
  fi
  # if FFmpeg silently fell back to rawvideo for every camera, summarize without JPEG validation
  # (summary.json silent_format_fallback / delivered_codecs record it either way).
  local notjpeg=()
  if ! grep -Eq '"codec": "(mjpeg|mjpg|jpeg)"' "$dir/run.log"; then notjpeg=(--not-jpeg); fi
  uv run --script "$SUMMARIZE_PY" "$rd" --test mjpeg_pyav_v4l2 --label "$label" --keep-samples 1 --root "$RES" ${notjpeg[@]+"${notjpeg[@]}"} \
      --command "${cmd[*]}" < /dev/null >> "$dir/run.log" 2>&1; rc=$?
  tail -n 6 "$dir/run.log"
  if [ $rc -ne 0 ]; then write_failure mjpeg_pyav_v4l2 "$label" "$rc" "$dir/run.log" "${cmd[@]}"; FAILS=$((FAILS+1)); fi
  if grep -q '"errors": \[[^]]' "$dir/run.log"; then echo "   -> pyav reported errors (see $dir/run.log and summary.json errors)"; fi
  sleep 1
}

# ------------------------------------------------------------------ 1. each camera alone at 1280x720@30
C720=()
for c in "${CAMS[@]}"; do
  n="$(basename "$c")"
  if [ "$(tsv_field "$c" 3)" != "1" ]; then echo "== skip 1280x720@30 for $c (not in its MJPG mode list)"; continue; fi
  C720+=("$c")
  run_v4l2 "1280x720at30_$n" 1280x720 30 "$c"
  run_pyav "1280x720at30_$n" 1280x720 30 "$c"
done

# ------------------------------------------------------------------ 2. all cameras together at 1280x720@30
if [ ${#C720[@]} -gt 1 ]; then
  names="$(for c in "${C720[@]}"; do basename "$c"; done | paste -sd+ -)"
  run_v4l2 "1280x720at30_all_$names" 1280x720 30 "${C720[@]}"
  run_pyav "1280x720at30_all_$names" 1280x720 30 "${C720[@]}"
fi

# ------------------------------------------------------------------ 3. each camera alone at its max MJPEG mode
for c in "${CAMS[@]}"; do
  n="$(basename "$c")"; sz="$(tsv_field "$c" 4)"; fps="$(tsv_field "$c" 5)"
  [ -n "$sz" ] && [ -n "$fps" ] || { echo "== no MJPEG mode list for $c; skipping max mode"; continue; }
  run_v4l2 "max_${sz}at${fps}_$n" "$sz" "$fps" "$c"
  run_pyav "max_${sz}at${fps}_$n" "$sz" "$fps" "$c"
done

# ------------------------------------------------------------------ 4. one table; pyav-v4l2 bytes compared with the V4L2 mmap bytes
uv run --script "$AGGREGATE_PY" --root "$RES" --ref-test mjpeg_v4l2_mmap --markdown < /dev/null > "$RES/aggregate.log" 2>&1   || echo "aggregate.py failed (see $RES/aggregate.log)"
echo "done. $FAILS failed attempt(s). Results under $RES (table: $RES/table.md)"
[ $FAILS -eq 0 ]
