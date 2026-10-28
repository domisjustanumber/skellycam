#!/usr/bin/env bash
# rerun20261027: short, non-streaming camera steps for the libusb/libuvc/Rust area, run under ONE camlock hold.
# The Razer Kiyo Pro 1532:0e05 is never opened (see per-step notes). Usage: bash batch_libusb_list.sh <TS>
set -u
TS="$1"
SP=/c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad
REPO=/c/Users/Dom/GitHub/freemocap/skellycam
G=$REPO/research/usb_cameras/results/windows/Gerald
T="/usr/bin/timeout -k 5"
B=$SP/b/build/cmake/bin/Release      # faithful libuvc build
B2=$SP/b2/build/cmake/bin/Release    # Kiyo-safe variant
RREL=$SP/r/build/release             # faithful rust build
R2REL=$SP/r2/build/release           # Kiyo-safe nokhwa_probe / mf_native_types
log() { echo "[$(date -u +%FT%TZ)] $*"; }
cpu() { powershell.exe -NoProfile -Command "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average" | tr -d '\r'; }
cd $REPO
log "batch start"
log "cpu_start=$(cpu)"

# 1 libuvc list (b2 variant: UVC_LIST_SKIP_OPEN)
D=$G/libuvc_list/${TS}_rerun20261027; mkdir -p $D
cp $SP/runs/libusb_rust_20261027/uvc_capture_test_skip_open.diff $D/
echo "UVC_LIST_SKIP_OPEN=1532:0e05 <scratchpad>/b2/build/cmake/bin/Release/uvc_capture_test.exe --list --json-out $D/list.json   (inside batch_libusb_list.sh under camlock)" > $D/command.txt
UVC_LIST_SKIP_OPEN=1532:0e05 $T 60 "$B2/uvc_capture_test.exe" --list --json-out "$(cygpath -m $D/list.json)" > $D/stdout.txt 2> $D/stderr.txt; echo "exit=$?" > $D/exit_code.txt
log "libuvc list $(cat $D/exit_code.txt)"
ORDER=$(grep -oE '^(1532:0e05|046d:085c|046d:0843|4c4a:4a55)' $D/stdout.txt | tr '\n' ' ')
log "uvc order: $ORDER"
echo "$ORDER" > $D/uvc_enumeration_order.txt
kiyo_before() { # $1 = vid:pid ; true if 1532:0e05 appears before it in libusb order (or order unknown)
  local seen=0
  for x in $ORDER; do
    [ "$x" = "1532:0e05" ] && seen=1
    if [ "$x" = "$1" ]; then [ $seen = 1 ] && return 0 || return 1; fi
  done
  return 0
}

# 2 libuvc capture on usbvideo (expected: no accessible device, exit 3)
D=$G/libuvc_capture_usbvideo/${TS}_rerun20261027; mkdir -p $D
cp $SP/runs/libusb_rust_20261027/uvc_capture_test_skip_open.diff $D/
: > $D/exit_codes.txt
for vp in 046d:085c 046d:0843 4c4a:4a55; do
  v=${vp%:*}; p=${vp#*:}; n=${v}_${p}
  $T 60 "$B2/uvc_capture_test.exe" --vid $v --pid $p --seconds 1 --out-dir "$(cygpath -m $D/$n)" > $D/$n.stdout.txt 2> $D/$n.stderr.txt
  echo "$vp variant_b2_prefilter exit=$?" >> $D/exit_codes.txt
  if kiyo_before $vp; then
    echo "$vp faithful_b SKIPPED (Kiyo precedes it in libusb order; uvc_get_device_descriptor would libusb_open it)" >> $D/exit_codes.txt
  else
    $T 60 "$B/uvc_capture_test.exe" --vid $v --pid $p --seconds 1 --out-dir "$(cygpath -m $D/${n}_faithful)" > $D/${n}_faithful.stdout.txt 2> $D/${n}_faithful.stderr.txt
    echo "$vp faithful_b exit=$?" >> $D/exit_codes.txt
  fi
done
echo "<scratchpad>/b2/build/cmake/bin/Release/uvc_capture_test.exe --vid V --pid P --seconds 1 --out-dir <this dir>/V_P  (b2 = VID/PID pre-filter variant, see uvc_capture_test_skip_open.diff); plus the faithful <scratchpad>/b/... binary only when the Kiyo is after the target in libusb order" > $D/command.txt
log "libuvc capture: $(tr '\n' ';' < $D/exit_codes.txt)"

# 3 libuvc example (b2: example.c vid/pid from env; upstream picks the first UVC device). Only when the Kiyo is after the target.
D=$G/libuvc_example_usbvideo/${TS}_rerun20261027; mkdir -p $D
cp $SP/b2/patches/0002-rerun-example-env-vidpid.patch $D/
: > $D/exit_codes.txt
for vp in 046d:085c 046d:0843 4c4a:4a55; do
  v=${vp%:*}; p=${vp#*:}; n=${v}_${p}
  if kiyo_before $vp; then
    echo "$vp SKIPPED (Kiyo precedes it in libusb order; uvc_find_device would libusb_open it via uvc_get_device_descriptor)" >> $D/exit_codes.txt
    continue
  fi
  UVC_EXAMPLE_VID=$v UVC_EXAMPLE_PID=$p $T 30 "$B2/example.exe" > $D/$n.stdout.txt 2> $D/$n.stderr.txt
  echo "$vp exit=$?" >> $D/exit_codes.txt
done
echo "UVC_EXAMPLE_VID=V UVC_EXAMPLE_PID=P <scratchpad>/b2/build/cmake/bin/Release/example.exe  (libuvc example + 0002-rerun-example-env-vidpid.patch)" > $D/command.txt
log "libuvc example: $(tr '\n' ';' < $D/exit_codes.txt)"

# 4 py_libusb1: full enumeration without open, then list with open for the 3 cameras (Kiyo hidden by wrapper)
D=$G/py_libusb1_list/${TS}_rerun20261027_no_open; mkdir -p $D
$T 90 uv run --script research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py --list --no-open --out-dir "$(cygpath -m $D)" > $D/stdout.txt 2> $D/stderr.txt; echo "exit=$?" > $D/exit_code.txt
echo "uv run --script research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py --list --no-open --out-dir $D" > $D/command.txt
log "py_libusb1 no-open $(cat $D/exit_code.txt)"
D=$G/py_libusb1_list/${TS}_rerun20261027_open_3cams; mkdir -p $D
cp $SP/wrappers/py_libusb1_skip.py $D/wrapper_py_libusb1_skip.py
SKIP_VIDPID=1532:0e05 $T 90 uv run --script $SP/wrappers/py_libusb1_skip.py research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py --list --out-dir "$(cygpath -m $D)" > $D/stdout.txt 2> $D/stderr.txt; echo "exit=$?" > $D/exit_code.txt
echo "SKIP_VIDPID=1532:0e05 uv run --script <scratchpad>/wrappers/py_libusb1_skip.py research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py --list --out-dir $D   (wrapper copy in this dir; target script unmodified)" > $D/command.txt
log "py_libusb1 open $(cat $D/exit_code.txt)"

# 5 Rust uvc_iso list (descriptors only; list never calls libusb_open)
for be in libusb rawusb; do
  D=$G/rust_uvc_iso_list_$be/${TS}_rerun20261027; mkdir -p $D
  $T 60 "$RREL/uvc_iso.exe" list --backend $be --out "$(cygpath -m $D)" > $D/stdout.txt 2> $D/stderr.txt; echo "exit=$?" > $D/exit_code.txt
  echo "<scratchpad>/r/build/release/uvc_iso.exe list --backend $be --out $D  (faithful build, rust_build/20261028T031415Z_rerun20261027)" > $D/command.txt
  log "uvc_iso list $be $(cat $D/exit_code.txt)"
done

# 6 mf_native_types (variant: MF_SKIP_MATCH)
D=$G/rust_mf_native_types/${TS}_rerun20261027; mkdir -p $D
cp $SP/runs/libusb_rust_20261027/nokhwa_probe_kiyo_skip.diff $D/
MF_SKIP_MATCH='vid_1532&pid_0e05' $T 90 "$R2REL/mf_native_types.exe" --out "$(cygpath -m $D)" > $D/stdout.txt 2> $D/stderr.txt; echo "exit=$?" > $D/exit_code.txt
echo "MF_SKIP_MATCH=vid_1532&pid_0e05 <scratchpad>/r2/build/release/mf_native_types.exe --out $D  (Kiyo-skip variant, diff nokhwa_probe_kiyo_skip.diff)" > $D/command.txt
log "mf_native_types $(cat $D/exit_code.txt)"

# 7 nokhwa list (variant honours match: in list mode)
D=$G/rust_nokhwa_list/${TS}_rerun20261027; mkdir -p $D
cp $SP/runs/libusb_rust_20261027/nokhwa_probe_kiyo_skip.diff $D/
$T 120 "$R2REL/nokhwa_probe.exe" list --cameras 'match:vid_046d&pid_085c,vid_046d&pid_0843,vid_4c4a&pid_4a55' --out "$(cygpath -m $D)" > $D/stdout.txt 2> $D/stderr.txt; echo "exit=$?" > $D/exit_code.txt
echo "<scratchpad>/r2/build/release/nokhwa_probe.exe list --cameras 'match:vid_046d&pid_085c,vid_046d&pid_0843,vid_4c4a&pid_4a55' --out $D  (variant: list honours match:, non-matching cameras are query-only, never opened)" > $D/command.txt
log "nokhwa list $(cat $D/exit_code.txt)"

log "cpu_end=$(cpu)"
log "batch end"
