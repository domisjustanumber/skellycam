#!/bin/bash
# Verifier rerun R1: python-libusb1 720p30 forced alt 5 / 4 / 5 back-to-back, live pipe snapshot 6 s into each stream.
cd /c/Users/Dom/GitHub/freemocap/skellycam
R=research/usb_cameras/results/windows/Gerald/phase2_python_verify
S=/c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/runs/phase2/python_verify
mkdir -p $S
i=0
for alt in 5 4 5; do
  i=$((i+1)); n=r1_${i}_720_alt$alt; mkdir -p $R/$n
  uv run --script research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py --vid 046d --pid 0843 --fps 30 --seconds 20 --decode-check --raw-dump $S/$n.bin --out-dir $R/$n --width 1280 --height 720 --alt $alt > $R/$n/stdout.txt 2> $R/$n/stderr.txt &
  P=$!
  sleep 7
  uv run --script research/usb_cameras/bandwidth/win_usb_topology.py --pipes-only > $R/$n/pipes_during_stream.json 2> $R/$n/pipes_stderr.txt
  wait $P; echo $? > $R/$n/exit_code.txt
  echo "$n rc=$(cat $R/$n/exit_code.txt) $(date -u +%H:%M:%S)"
done
