# /// script
# requires-python = ">=3.10"
# dependencies = ["libusb1==3.4.0"]
# ///
"""A/B: libusb_get_active_config_descriptor vs libusb_get_config_descriptor(index 0) per UVC camera.
Never calls libusb_open (descriptor reads only). Prints JSON."""
import ctypes, json, usb1
from usb1 import libusb1 as L

want = {(0x1532, 0x0E05), (0x046D, 0x085C), (0x046D, 0x0843), (0x4C4A, 0x4A55)}
out = {"libusb": ".".join(map(str, tuple(usb1.getVersion())[:4])), "devices": []}
with usb1.USBContext() as ctx:
    for dev in ctx.getDeviceIterator(skip_on_error=True):
        k = (dev.getVendorID(), dev.getProductID())
        if k not in want:
            continue
        raw = dev.device_p
        p = ctypes.POINTER(L.libusb_config_descriptor)()
        rc_active = L.libusb_get_active_config_descriptor(raw, ctypes.byref(p))
        tl_a = p.contents.wTotalLength if rc_active == 0 else None
        if rc_active == 0:
            L.libusb_free_config_descriptor(p)
        p2 = ctypes.POINTER(L.libusb_config_descriptor)()
        rc_idx0 = L.libusb_get_config_descriptor(raw, 0, ctypes.byref(p2))
        tl_0 = p2.contents.wTotalLength if rc_idx0 == 0 else None
        if rc_idx0 == 0:
            L.libusb_free_config_descriptor(p2)
        out["devices"].append({"vid": "%04x" % k[0], "pid": "%04x" % k[1], "bus": dev.getBusNumber(), "ports": dev.getPortNumberList(),
                               "active_rc": rc_active, "active_wTotalLength": tl_a, "index0_rc": rc_idx0, "index0_wTotalLength": tl_0})
print(json.dumps(out, indent=1))
