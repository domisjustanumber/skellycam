#!/bin/bash
cd /c/Users/Dom/GitHub/freemocap/skellycam
R=research/usb_cameras/results/windows/Gerald/phase2_python_verify
O=$R/r3b_pyuvc_pypi_720_bf2_faulthandler; mkdir -p $O
PYTHONFAULTHANDLER=1 uv run --script research/usb_cameras/libusb/pyuvc/pyuvc_winusb_stream.py --vid 046d --pid 0843 --width 1280 --height 720 --fps 30 --seconds 3 --bandwidth-factors 2.0 --out-dir $O > $O/stdout.txt 2> $O/stderr.txt
echo $? > $O/exit_code.txt
O=$R/r4_libusb_identity; mkdir -p $O
uv run --script research/usb_cameras/naming/libusb_identity.py --compare research/usb_cameras/results/windows/Gerald/naming/snapshots/final_with_4th_camera.json --out-dir $O > $O/stdout.txt 2> $O/stderr.txt
echo $? > $O/exit_code.txt
