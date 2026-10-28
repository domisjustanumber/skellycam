# /// script
# requires-python = ">=3.10"
# ///
"""Plumbing test of macos_identity.py on a SYNTHETIC `ioreg -a` plist + fake AVFoundation list (any OS).

    uv run --script research/usb_cameras/naming/test_macos_fake_ioreg.py

Checks: hub-nested devices are found once, video devices are recognised by a bInterfaceClass 14 child, the
AVFoundation uniqueID <-> locationID/VID/PID numeric match (forum-reported format, including the un-padded form
"0x2000000fd9009b"), and the resulting camera keys. It does NOT show that real macOS behaves this way - that is
what macos_stability_workflow.sh measures on a Mac.
Writes results/<platform>/<hostname>/naming/test_macos_fake_ioreg.json
"""
from __future__ import annotations

import json
import plistlib
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import camera_identity  # noqa: E402
import macos_identity  # noqa: E402


def iface(cls):
    return {"IOObjectClass": "IOUSBHostInterface", "bInterfaceClass": cls, "idVendor": 0, "idProduct": 0}


def main() -> int:
    c922 = {"IOObjectClass": "IOUSBHostDevice", "idVendor": 0x046D, "idProduct": 0x085C, "bcdDevice": 0x16,
            "USB Serial Number": "B76395EF", "USB Product Name": "C922 Pro Stream Webcam", "locationID": 0x00200000,
            "sessionID": 111, "USB Address": 3, "IORegistryEntryChildren": [iface(14), iface(14), iface(1)]}
    c930 = {"IOObjectClass": "IOUSBHostDevice", "idVendor": 0x046D, "idProduct": 0x0843, "bcdDevice": 0x13,
            "USB Product Name": "Logitech Webcam C930e", "locationID": 0x14140000, "sessionID": 222, "USB Address": 7,
            "IORegistryEntryChildren": [iface(14), iface(1)]}
    hub = {"IOObjectClass": "IOUSBHostDevice", "idVendor": 0x05E3, "idProduct": 0x0610, "locationID": 0x14100000,
           "sessionID": 333, "IORegistryEntryChildren": [c930]}
    plist = plistlib.dumps([hub, c922, c930])   # c930 appears both nested and as its own root, like `ioreg -r -c`
    avf = [dict(order=0, uniqueID="0x200000046d085c", modelID="UVC Camera VendorID_1133 ProductID_2140", localizedName="C922"),
           dict(order=1, uniqueID="0x14140000046d0843", modelID="UVC Camera VendorID_1133 ProductID_2115", localizedName="C930e")]
    real_run = subprocess.run
    subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=plist, stderr=b"")
    macos_identity.avfoundation_devices = lambda: (json.loads(json.dumps(avf)), None)
    try:
        full = macos_identity.collect()
        flats = macos_identity.collect_flat()
    finally:
        subprocess.run = real_run
    for f in flats:
        f["port_path"] = camera_identity.port_path_from_mac_location_id(f["location_id"])
    keys = {f["pid"]: camera_identity.derive(f, flats)[0] for f in flats}
    checks, ok = [], True

    def check(n, c, detail=None):
        nonlocal ok
        ok &= bool(c)
        checks.append(dict(name=n, ok=bool(c), detail=detail))
        print(("PASS " if c else "FAIL ") + n, "" if c else detail)
    check("3 usb devices, deduped", len(full["usb_devices"]) == 3, len(full["usb_devices"]))
    check("2 video devices", len(flats) == 2, [f["pid"] for f in flats])
    check("uniqueID matched for both (incl. unpadded)", all(a["uniqueID_format_confirmed"] for a in full["avfoundation"]))
    check("C922 serial key", keys.get("085c") == "046d:085c:sn=B76395EF", keys.get("085c"))
    check("C930e port key", keys.get("0843") == "046d:0843:port=bus14/1.4", keys.get("0843"))
    out = HERE.parent / "results" / {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux") / socket.gethostname() / "naming"
    out.mkdir(parents=True, exist_ok=True)
    (out / "test_macos_fake_ioreg.json").write_text(json.dumps(dict(
        test="naming.test_macos_fake_ioreg", platform=sys.platform, hostname=socket.gethostname(),
        command=" ".join(sys.argv), keys=keys, checks=checks, all_ok=ok), indent=1))
    print("all_ok =", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
