#!/usr/bin/env bash
# run_libusb_macos.sh - DRAFTED, UNVERIFIED until run on a Mac (macOS 12+) with UVC webcams.
#
# Question: can libusb/libuvc claim a UVC camera's interfaces on macOS 12+ WITHOUT root or a
# restricted entitlement? Source facts this test checks (libusb 1.0.30 libusb/os/darwin_usb.c):
#   darwin_detach_kernel_driver(): if the process lacks the boolean entitlement
#   "com.apple.vm.device-access" and geteuid() != 0 -> warns "USB device capture requires either an
#   entitlement (com.apple.vm.device-access) or root privilege" and returns LIBUSB_ERROR_ACCESS.
#   libuvc's uvc_claim_if() calls libusb_detach_kernel_driver() first and does NOT claim if that
#   returns ACCESS, so uvc_open() is expected to fail for a normal user.
#   pupil-labs/pyuvc README: "Running as a non-root user ... Unfortunately, this is currently not
#   possible" (libusb issue #1014, closed as a known limitation).
#
# Steps (each recorded with exit code + LIBUSB_DEBUG=3 log):
#   1. environment: sw_vers, uname -m, libusb version, system_profiler SPCameraDataType (names only)
#   2. build patched libuvc + uvc_capture_test (../build_unix.sh, needs: brew install libusb cmake pkg-config)
#   3. as the current user: uvc_capture_test --list  (enumeration; libusb_open per UVC device)
#   4. as the current user: --probe-only on each UVC camera (expect: ACCESS / claim failure)
#   5. as the current user: py-libusb1 claimInterface WITHOUT detach (expect kIOReturnExclusiveAccess
#      -> LIBUSB_ERROR_ACCESS/BUSY) -- via a tiny inline python using python-libusb1 (needs uv)
#   6. ONLY with --with-sudo: repeat 4 + a 5 s MJPEG stream under sudo (prompts for your password),
#      then check the camera is usable by macOS again (system_profiler before/after)
# Run from the repo root:
#   bash research/usb_cameras/libusb/macos/run_libusb_macos.sh [--with-sudo] [--seconds 5]
# Writes: research/usb_cameras/results/macos/<hostname>/libusb_macos/ (summary.json + logs)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$LIB/../../.." && pwd)"
SUDO=0; SECS=5
while [ $# -gt 0 ]; do
  case "$1" in
    --with-sudo) SUDO=1 ;;
    --seconds) SECS="$2"; shift ;;
    *) echo "unknown option $1" >&2; exit 1 ;;
  esac
  shift
done
[ "$(uname -s)" = Darwin ] || { echo "macOS only" >&2; exit 1; }
HOST="$(hostname -s)"
OUT="$REPO/research/usb_cameras/results/macos/$HOST/libusb_macos"
mkdir -p "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1
echo "== $(date -u +%FT%TZ) $0 $*"
{
  sw_vers
  echo "arch: $(uname -m)"
  echo "uid: $(id -u) user: $(id -un)"
  echo "libusb: $(pkg-config --modversion libusb-1.0 2>/dev/null || echo missing)"
  echo "--- cameras (system_profiler SPCameraDataType)"
  system_profiler SPCameraDataType 2>/dev/null | grep -E "^\s{4}[^ ].*:$|Model ID|Unique ID" || true
  echo "--- UVCAssistant"; pgrep -lf UVCAssistant || echo "(not running)"
} > "$OUT/environment.txt"
cat "$OUT/environment.txt"
system_profiler SPCameraDataType > "$OUT/cameras_before.txt" 2>/dev/null

if [ -z "$(pkg-config --modversion libusb-1.0 2>/dev/null)" ]; then
  echo "ERROR: libusb not found. Run: brew install libusb cmake pkg-config" >&2; exit 2
fi
bash "$LIB/build_unix.sh" || { echo "build failed" >&2; exit 2; }
EXE="$LIB/build/unix/bin/uvc_capture_test"

export LIBUSB_DEBUG=3
"$EXE" --list --json-out "$OUT/list_user.json" > "$OUT/list_user.txt" 2> "$OUT/list_user.stderr"
echo "list(user) exit=$?" | tee "$OUT/list_user.exit"
cat "$OUT/list_user.txt"

python3 - "$OUT/list_user.json" > "$OUT/cams.tsv" <<'PY'
import json, sys
for x in json.load(open(sys.argv[1]))["devices"]:
    if x["is_uvc"]:
        print(x["vid"], x["pid"], x["port_path"], sep="\t")
PY

while IFS=$'\t' read -r vid pid pp; do
  tag="${vid}_${pid}_${pp//[.-]/_}"
  "$EXE" --vid "$vid" --pid "$pid" --port-path "$pp" --probe-only --out-dir "$OUT/${tag}_probe_user" \
      > "$OUT/${tag}_probe_user.txt" 2> "$OUT/${tag}_probe_user.stderr"
  echo "probe(user) $vid:$pid exit=$?" | tee "$OUT/${tag}_probe_user.exit"
  grep -iE "entitlement|root privilege|exclusive|access|uvc_open" "$OUT/${tag}_probe_user.stderr" | head -5
done < "$OUT/cams.tsv"

# claim WITHOUT detach, as the user, using python-libusb1 (records the raw libusb error)
if command -v uv >/dev/null; then
  cat > "$OUT/claim_probe.py" <<'PY'
# /// script
# dependencies = ["libusb1==3.4.0"]
# ///
import json, sys, usb1
res = []
with usb1.USBContext() as ctx:
    for dev in ctx.getDeviceIterator(skip_on_error=True):
        uvc = [s for s in dev.iterSettings() if s.getClass() == 0x0E]
        if not uvc:
            continue
        r = {"vid": f"{dev.getVendorID():04x}", "pid": f"{dev.getProductID():04x}"}
        try:
            h = dev.open(); r["open"] = "OK"
        except usb1.USBError as e:
            r["open"] = repr(e); res.append(r); continue
        for itf in sorted({s.getNumber() for s in uvc}):
            try:
                r[f"kernel_driver_active_{itf}"] = h.kernelDriverActive(itf)
            except usb1.USBError as e:
                r[f"kernel_driver_active_{itf}"] = repr(e)
            try:
                h.claimInterface(itf); r[f"claim_no_detach_{itf}"] = "OK"; h.releaseInterface(itf)
            except usb1.USBError as e:
                r[f"claim_no_detach_{itf}"] = repr(e)
            try:
                h.detachKernelDriver(itf); r[f"detach_{itf}"] = "OK"
            except usb1.USBError as e:
                r[f"detach_{itf}"] = repr(e)
        h.close()
        res.append(r)
json.dump(res, open(sys.argv[1], "w"), indent=1)
print(json.dumps(res, indent=1))
PY
  uv run --script "$OUT/claim_probe.py" "$OUT/claim_probe_user.json" > "$OUT/claim_probe_user.txt" 2>&1
  echo "claim_probe(user) exit=$?"; cat "$OUT/claim_probe_user.txt"
fi

if [ "$SUDO" = 1 ]; then
  echo "--- repeating with sudo (you will be asked for your password)"
  while IFS=$'\t' read -r vid pid pp; do
    tag="${vid}_${pid}_${pp//[.-]/_}"
    sudo -E "$EXE" --vid "$vid" --pid "$pid" --port-path "$pp" --seconds "$SECS" --save-jpeg 1 \
        --out-dir "$OUT/${tag}_stream_sudo" > "$OUT/${tag}_stream_sudo.txt" 2> "$OUT/${tag}_stream_sudo.stderr"
    echo "stream(sudo) $vid:$pid exit=$?" | tee "$OUT/${tag}_stream_sudo.exit"
  done < "$OUT/cams.tsv"
  sudo chown -R "$(id -u):$(id -g)" "$OUT"
  sleep 3
  system_profiler SPCameraDataType > "$OUT/cameras_after.txt" 2>/dev/null
  if diff -q "$OUT/cameras_before.txt" "$OUT/cameras_after.txt" >/dev/null; then echo "cameras visible to macOS after sudo run: unchanged"; else echo "cameras list CHANGED after sudo run (see cameras_before/after.txt)"; fi
fi

python3 - "$OUT" "$SUDO" <<'PY'
import json, sys, glob, os, socket, datetime
out, sudo = sys.argv[1], sys.argv[2] == "1"
def rd(p):
    try:
        return open(p).read().strip()
    except OSError:
        return None
s = {"test": "libusb_macos", "platform": "macos", "hostname": socket.gethostname(),
     "utc_finished": datetime.datetime.now(datetime.timezone.utc).isoformat(),
     "command": "bash research/usb_cameras/libusb/macos/run_libusb_macos.sh" + (" --with-sudo" if sudo else ""),
     "environment": rd(os.path.join(out, "environment.txt")),
     "list_user_exit": rd(os.path.join(out, "list_user.exit")),
     "probe_user": {os.path.basename(p): rd(p) for p in glob.glob(os.path.join(out, "*_probe_user.exit"))},
     "probe_user_stderr_excerpt": {os.path.basename(p): (rd(p) or "")[-800:] for p in glob.glob(os.path.join(out, "*_probe_user.stderr"))},
     "claim_probe_user": json.load(open(os.path.join(out, "claim_probe_user.json"))) if os.path.exists(os.path.join(out, "claim_probe_user.json")) else None,
     "stream_sudo": {}}
for p in glob.glob(os.path.join(out, "*_stream_sudo", "result.json")):
    r = json.load(open(p))
    s["stream_sudo"][os.path.basename(os.path.dirname(p))] = r.get("measurements")
json.dump(s, open(os.path.join(out, "summary.json"), "w"), indent=2)
print(json.dumps(s, indent=1)[:4000])
PY
echo "wrote $OUT/summary.json"
