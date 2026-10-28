# /// script
# requires-python = ">=3.10"
# dependencies = ["pupil-labs-uvc==1.0.8", "numpy"]
# ///
"""rerun20261027 harness wrapper: run research/usb_cameras/libusb/pyuvc/pyuvc_probe.py UNMODIFIED, with
uvc.device_list() replaced.

NO_DEVICE_LIST=1 : uvc.device_list() returns [] WITHOUT calling the real one. pyuvc 1.0.8's device_list reads
                   the string descriptors through libuvc uvc_get_device_descriptor(), which calls libusb_open on
                   EVERY UVC device -- that would include the excluded Razer Kiyo Pro. With this, the probe still
                   records import, bundled libusb version and the clock check, but touches no camera.
SKIP_VIDPID=v:p  : otherwise, filter the real device_list() result (note: the real call has already opened all).
Usage: NO_DEVICE_LIST=1 uv run --script pyuvc_probe_skip.py <path to pyuvc_probe.py> [its args...]"""
import os
import runpy
import sys

import uvc

skip = {s.strip().lower() for s in os.environ.get("SKIP_VIDPID", "").split(",") if s.strip()}
_orig = uvc.device_list


def _filtered():
    out = []
    for d in _orig() or []:
        if f"{d['idVendor']:04x}:{d['idProduct']:04x}" in skip:
            continue
        out.append(d)
    return out


if os.environ.get("NO_DEVICE_LIST") == "1":
    uvc.device_list = lambda: []
    print("[wrapper] uvc.device_list() stubbed to [] (no camera touched)", file=sys.stderr)
else:
    uvc.device_list = _filtered
target = sys.argv[1]
sys.argv = [target] + sys.argv[2:]
runpy.run_path(target, run_name="__main__")
