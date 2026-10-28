# /// script
# requires-python = ">=3.10"
# dependencies = ["libusb1==3.4.0", "pillow>=10"]
# ///
"""rerun20261027 harness wrapper: run research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py UNMODIFIED,
but hide devices whose VID:PID is listed in SKIP_VIDPID (e.g. "1532:0e05") from every
usb1.USBContext.getDeviceIterator()/getDeviceList() call, so they are never opened.
Usage: SKIP_VIDPID=1532:0e05 uv run --script py_libusb1_skip.py <path to uvc_libusb1_stream.py> [its args...]"""
import os, runpy, sys
import usb1
skip = {s.strip().lower() for s in os.environ.get("SKIP_VIDPID", "").split(",") if s.strip()}
_orig_iter = usb1.USBContext.getDeviceIterator
def _filtered(self, *a, **k):
    for d in _orig_iter(self, *a, **k):
        if f"{d.getVendorID():04x}:{d.getProductID():04x}" in skip:
            print(f"[wrapper] hidden {d.getVendorID():04x}:{d.getProductID():04x}", file=sys.stderr)
            continue
        yield d
usb1.USBContext.getDeviceIterator = _filtered
usb1.USBContext.getDeviceList = lambda self, *a, **k: list(_filtered(self, *a, **k))
target = sys.argv[1]
sys.argv = [target] + sys.argv[2:]
runpy.run_path(target, run_name="__main__")
