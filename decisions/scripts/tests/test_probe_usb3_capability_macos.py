"""Tests of the parsers of decisions/scripts/probe_usb3_capability_macos.py (ADR-H7PX).

Each sample below is SYNTHETIC: written from the documentation (the USB 3.2 BOS layout, the documented IORegistry
key names, the JSON form of `system_profiler`), not recorded on a Mac. A recording of the probe on a Mac replaces
them (open work). Run: `python -I decisions/scripts/tests/test_probe_usb3_capability_macos.py`, or with pytest.
"""
import importlib.util
import json
import plistlib
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "probe_usb3_capability_macos.py"
_SPEC = importlib.util.spec_from_file_location("probe_usb3_capability_macos", _PATH)
probe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(probe)

# SYNTHETIC: BOS header, USB 2.0 Extension, SuperSpeed USB Device Capability (USB 3.2 spec 9.6.2)
BOS_USB3 = bytes([0x05, 0x0F, 0x16, 0x00, 0x02,
                  0x07, 0x10, 0x02, 0x06, 0x00, 0x00, 0x00,
                  0x0A, 0x10, 0x03, 0x00, 0x0E, 0x00, 0x01, 0x0A, 0xFF, 0x07])
# SYNTHETIC: a USB 2.1 device with LPM only
BOS_USB2 = bytes([0x05, 0x0F, 0x0C, 0x00, 0x01, 0x07, 0x10, 0x02, 0x06, 0x00, 0x00, 0x00])
# SYNTHETIC: a SuperSpeedPlus capability only (type 0x0A)
BOS_PLUS = bytes([0x05, 0x0F, 0x08, 0x00, 0x01, 0x03, 0x10, 0x0A])


def _ioreg_sample():
    """SYNTHETIC `ioreg -a -l -r -c IOUSBHostDevice` output: a USB 3 camera on a USB 2 link, a USB 2 camera, and a
    keyboard. The serial and the location are present, as on a Mac, so that the test sees that they are not printed."""
    camera3 = {"idVendor": 0x1532, "idProduct": 0x0E05, "bcdDevice": 0x0105, "bcdUSB": 0x0210, "USBSpeed": 3,
               "UsbLinkSpeed": 480000000, "USB Product Name": "Razer Kiyo Pro", "USB Serial Number": "SYNTH123",
               "locationID": 0x14100000,
               "IORegistryEntryChildren": [{"bInterfaceClass": 14, "bInterfaceSubClass": 1}]}
    camera2 = {"idVendor": 0x046D, "idProduct": 0x085C, "bcdDevice": 0x0016, "bcdUSB": 0x0200, "USBSpeed": 3,
               "USB Product Name": "C922 Pro Stream Webcam", "locationID": 0x14200000,
               "IORegistryEntryChildren": [{"bInterfaceClass": 1}, {"bInterfaceClass": 14}]}
    keyboard = {"idVendor": 0x05AC, "idProduct": 0x0250, "bcdUSB": 0x0200, "USBSpeed": 2,
                "IORegistryEntryChildren": [{"bInterfaceClass": 3}]}
    return plistlib.dumps([camera3, camera2, keyboard], fmt=plistlib.FMT_XML)


def test_bos_parser():
    assert probe.bos_is_usb3_capable(BOS_USB3) is True
    assert probe.bos_is_usb3_capable(BOS_USB2) is False
    assert probe.bos_is_usb3_capable(BOS_PLUS) is True
    assert probe.bos_is_usb3_capable(b"\x12\x01\x00\x02\x00") is None  # a device descriptor, not a BOS
    assert probe.bos_is_usb3_capable(b"") is None


def test_bcd_three_state():
    assert probe.bcd_three_state(0x0200, "USB 2") == "no"
    assert probe.bcd_three_state(0x0201, "USB 2") == "no"
    assert probe.bcd_three_state(0x0210, "USB 2") == "possible"
    assert probe.bcd_three_state(0x0320, "USB 3") == "yes"
    assert probe.bcd_three_state(None, "USB 2") is None


def test_ioreg_parser_keeps_video_devices_and_no_private_facts():
    devices = probe.devices_from_ioreg(_ioreg_sample())
    assert [(d["vendor"], d["product"]) for d in devices] == [(0x1532, 0x0E05), (0x046D, 0x085C)]
    first = devices[0]
    assert first["bcd_usb"] == 0x0210 and first["usb_speed"] == 3 and first["link_speed"] == 480000000
    assert first["capability_keys"] == ["UsbLinkSpeed"]
    assert probe.usb_link_from_speed(first["usb_speed"]) == "USB 2"
    printed = json.dumps({k: v for k, v in first.items() if not k.startswith("_")})
    assert "SYNTH123" not in printed and str(0x14100000) not in printed


def test_system_profiler_parser():
    sample = json.dumps({"SPUSBDataType": [{"_name": "USB31Bus", "_items": [
        {"_name": "Razer Kiyo Pro", "vendor_id": "0x1532  (Razer)", "product_id": "0x0e05", "speed": "Up to 480 Mb/s",
         "serial_num": "SYNTH123", "location_id": "0x14100000 / 2"}]}]}).encode()  # SYNTHETIC
    assert probe.speeds_from_system_profiler(sample) == {(0x1532, 0x0E05): "Up to 480 Mb/s"}
    assert probe.speeds_from_system_profiler(b"{}") == {}


if __name__ == "__main__":
    for name, function in list(globals().items()):
        if name.startswith("test_"):
            function()
    print("ok")
    sys.exit(0)
