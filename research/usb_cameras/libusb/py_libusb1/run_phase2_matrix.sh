#!/bin/bash
# Phase-2 python-libusb1 matrix runner (Windows/GERALD, C930e on WinUSB). Each run: one camlock hold, 20 s stream, Pillow decode
# check, raw frames to the scratchpad (S=..., change for another machine). Run from the repo root.
# usage: run_py_matrix.sh name "extra args" [name "extra args" ...]   (run from repo root)
R=research/usb_cameras/results/windows/Gerald/phase2_python_libusb
# The 2026-10-25 runs wrote to a session temp scratchpad (deleted 2026-10-28). Override S to choose another folder.
S=${S:-${TMP:-/tmp}/skellycam_usb_phase2/python_libusb}
mkdir -p $S
while [ $# -ge 2 ]; do
  n=$1; x=$2; shift 2
  mkdir -p $R/$n
  CMD="uv run --script research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py --vid 046d --pid 0843 --fps 30 --seconds 20 --decode-check --raw-dump $S/$n.bin --out-dir $R/$n $x"
  echo "uv run --script research/usb_cameras/tools/camlock.py --timeout-s 170 -- $CMD" > $R/$n/command.txt
  timeout 230 uv run --script research/usb_cameras/tools/camlock.py --timeout-s 170 -- $CMD > $R/$n/stdout.txt 2> $R/$n/stderr.txt
  echo $? > $R/$n/exit_code.txt
  echo "$n rc=$(cat $R/$n/exit_code.txt) $(date -u +%H:%M:%S)"
done
