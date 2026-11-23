"""Probe for ADR-H7PX: can certify learn on macOS that a USB video device is USB 3 capable, also when it runs on a
USB 2 link, without disturbing the camera?

Run on a Mac, from the repository root, with no camera app open and no stream running:
    python3 decisions/scripts/probe_usb3_capability_macos.py            # each method
    python3 decisions/scripts/probe_usb3_capability_macos.py --no-bos-request

It prints one JSON object for each attached USB video device (a device with an interface of class 14). It uses
the Python standard library only (Python 3.9 or later, the system `python3` is enough). It opens no video stream,
claims no interface, and never calls `USBDeviceOpen` or `USBDeviceOpenSeize`. The output holds no serial number,
no location id, no registry path and no host name; an error is its class name only.

The methods (specs/certify.md 3.6.13):
  ioreg            the IORegistry properties of the IOUSBHostDevice (`ioreg -a -l -r -c IOUSBHostDevice`): the
                   running speed, `bcdUSB`, and the names of any key that could hold a capability.
  system_profiler  `system_profiler -json SPUSBDataType` (absent on some new macOS versions): its "speed" text.
  bcd_usb          the three-state fact from `bcdUSB` and the running speed: "no", "possible" or "yes".
  bos_request      one standard GET_DESCRIPTOR(BOS) request on the default pipe through IOUSBLib, with no open of
                   the device. Before the request, the script checks the function table of the interface: the
                   vendor id, the product id and the release number that it reads must equal the registry values,
                   else it sends nothing. A read of 5 bytes, then of the total length; it changes no state.
"""
import argparse
import json
import plistlib
import subprocess
import sys

VIDEO_CLASS = 14
SUPERSPEED_CAPABILITY = 0x03
SUPERSPEED_PLUS_CAPABILITY = 0x0A
CAPABILITY_WORDS = ("bos", "superspeed", "capab", "linkspeed", "usb3")
PRIVATE_KEYS = {"usb serial number", "kusbserialnumberstring", "locationid", "iopath", "ioregistryentrylocation",
                "usb address", "sessionid", "kusbaddress"}


# ----- parsers (tested with synthetic samples in decisions/scripts/tests/) -----

def usb_link_from_speed(speed):
    """`USBSpeed` of IOUSBHost: 1 full, 2 low, 3 high, 4 super, 5 super+, 6 super+ x2."""
    if not isinstance(speed, int) or speed <= 0:
        return "unknown"
    return "USB 3" if speed >= 4 else "USB 2" if speed == 3 else "USB 1"


def bcd_three_state(bcd_usb, usb_link):
    """3.6.13: 0x0200 or 0x0201 proves "no"; a SuperSpeed link proves "yes"; 0x0210 or higher on a USB 2 link only
    says "possible" (a USB 3 device on a high-speed link presents 0x0210, and so do many USB 2 devices)."""
    if not isinstance(bcd_usb, int):
        return None
    if usb_link == "USB 3":
        return "yes"
    if bcd_usb < 0x0210:
        return "no"
    return "possible"


def bos_is_usb3_capable(data):
    """True when a BOS descriptor holds a SuperSpeed or SuperSpeedPlus device capability; False when it is a valid
    BOS with neither; None when the bytes are not a BOS."""
    if len(data) < 5 or data[1] != 0x0F or data[0] < 5:
        return None
    total = data[2] | data[3] << 8
    end, i = min(total, len(data)), data[0]
    found = False
    while i + 3 <= end:
        length, kind, capability = data[i], data[i + 1], data[i + 2]
        if length < 3 or kind != 0x10:
            return None
        if capability in (SUPERSPEED_CAPABILITY, SUPERSPEED_PLUS_CAPABILITY):
            found = True
        i += length
    return found


def _interfaces(entry):
    for child in entry.get("IORegistryEntryChildren", []) or []:
        yield child
        yield from _interfaces(child)


def devices_from_ioreg(plist_bytes):
    """The USB video devices of `ioreg -a -l -r -c IOUSBHostDevice`, with only the facts that the probe prints."""
    out = []
    for entry in plistlib.loads(plist_bytes):
        if not any(child.get("bInterfaceClass") == VIDEO_CLASS for child in _interfaces(entry)):
            continue
        vendor, product = entry.get("idVendor"), entry.get("idProduct")
        keys = [key for key in entry if isinstance(key, str) and key.lower() not in PRIVATE_KEYS
                and any(word in key.lower().replace(" ", "") for word in CAPABILITY_WORDS)]
        out.append({
            "vendor": vendor, "product": product, "release": entry.get("bcdDevice"),
            "product_text": entry.get("USB Product Name") or entry.get("kUSBProductString"),
            "bcd_usb": entry.get("bcdUSB"), "usb_speed": entry.get("USBSpeed", entry.get("Device Speed")),
            "link_speed": entry.get("UsbLinkSpeed"), "capability_keys": sorted(keys),
            "_location": entry.get("locationID"),
        })
    return out


def speeds_from_system_profiler(json_bytes):
    """{(vendor, product): speed text} from `system_profiler -json SPUSBDataType`."""
    out = {}

    def walk(items):
        for item in items or []:
            vendor, product = _hex_id(item.get("vendor_id")), _hex_id(item.get("product_id"))
            if vendor is not None and product is not None and item.get("speed"):
                out[(vendor, product)] = item["speed"]
            walk(item.get("_items"))

    data = json.loads(json_bytes)
    for key in ("SPUSBDataType", "SPUSBHostDataType"):
        walk(data.get(key))
    return out


def _hex_id(text):
    if isinstance(text, int):
        return text
    if not isinstance(text, str):
        return None
    word = text.strip().split()[0] if text.strip() else ""
    try:
        return int(word, 16)
    except ValueError:
        return None


# ----- the BOS request through IOUSBLib (macOS only) -----

def bos_request_all(devices):
    """{location: (answer, error)} for each device. Runs only on macOS."""
    import ctypes
    import ctypes.util

    cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
    iokit = ctypes.CDLL(ctypes.util.find_library("IOKit"))
    c_void_p, c_uint32, c_int32 = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int32

    class CFUUIDBytes(ctypes.Structure):
        _fields_ = [("b", ctypes.c_ubyte * 16)]

    class IOUSBDevRequest(ctypes.Structure):
        _fields_ = [("bmRequestType", ctypes.c_uint8), ("bRequest", ctypes.c_uint8), ("wValue", ctypes.c_uint16),
                    ("wIndex", ctypes.c_uint16), ("wLength", ctypes.c_uint16), ("pData", c_void_p),
                    ("wLenDone", c_uint32)]

    cf.CFUUIDGetConstantUUIDWithBytes.restype = c_void_p
    cf.CFUUIDGetConstantUUIDWithBytes.argtypes = [c_void_p] + [ctypes.c_ubyte] * 16
    cf.CFUUIDGetUUIDBytes.restype = CFUUIDBytes
    cf.CFUUIDGetUUIDBytes.argtypes = [c_void_p]
    cf.CFStringCreateWithCString.restype = c_void_p
    cf.CFStringCreateWithCString.argtypes = [c_void_p, ctypes.c_char_p, c_uint32]
    cf.CFNumberGetValue.argtypes = [c_void_p, ctypes.c_int, c_void_p]
    cf.CFRelease.argtypes = [c_void_p]
    iokit.IOServiceMatching.restype = c_void_p
    iokit.IOServiceMatching.argtypes = [ctypes.c_char_p]
    iokit.IOServiceGetMatchingServices.argtypes = [c_uint32, c_void_p, ctypes.POINTER(c_uint32)]
    iokit.IOIteratorNext.restype = c_uint32
    iokit.IOIteratorNext.argtypes = [c_uint32]
    iokit.IOObjectRelease.argtypes = [c_uint32]
    iokit.IORegistryEntryCreateCFProperty.restype = c_void_p
    iokit.IORegistryEntryCreateCFProperty.argtypes = [c_uint32, c_void_p, c_void_p, c_uint32]
    iokit.IOCreatePlugInInterfaceForService.argtypes = [c_uint32, c_void_p, c_void_p, ctypes.POINTER(c_void_p),
                                                        ctypes.POINTER(c_int32)]

    def uuid(*b):
        return cf.CFUUIDGetConstantUUIDWithBytes(None, *b)

    # IOUSBLib.h [NV: from the header of IOUSBFamily, not read on this macOS]
    device_user_client = uuid(0x9D, 0xC7, 0xB7, 0x80, 0x9E, 0xC0, 0x11, 0xD4, 0xA5, 0x4F, 0x00, 0x0A, 0x27, 0x05, 0x28, 0x61)
    plugin_interface = uuid(0xC2, 0x44, 0xE8, 0x58, 0x10, 0x9C, 0x11, 0xD4, 0x91, 0xD4, 0x00, 0x50, 0xE4, 0xC6, 0x42, 0x6F)
    device_interface = uuid(0x5C, 0x81, 0x87, 0xD0, 0x9E, 0xF3, 0x11, 0xD4, 0x8B, 0x45, 0x00, 0x0A, 0x27, 0x05, 0x28, 0x61)

    def number(service, name):
        key = cf.CFStringCreateWithCString(None, name.encode(), 0x08000100)
        ref = iokit.IORegistryEntryCreateCFProperty(service, key, None, 0)
        cf.CFRelease(key)
        if not ref:
            return None
        value = ctypes.c_int64()
        ok = cf.CFNumberGetValue(ref, 4, ctypes.byref(value))  # kCFNumberSInt64Type
        cf.CFRelease(ref)
        return value.value if ok else None

    HRESULT = c_int32
    QUERY = ctypes.CFUNCTYPE(HRESULT, c_void_p, CFUUIDBytes, ctypes.POINTER(c_void_p))
    RELEASE = ctypes.CFUNCTYPE(c_uint32, c_void_p)
    GET16 = ctypes.CFUNCTYPE(c_int32, c_void_p, ctypes.POINTER(ctypes.c_uint16))
    REQUEST = ctypes.CFUNCTYPE(c_int32, c_void_p, ctypes.POINTER(IOUSBDevRequest))
    # the slots of IOUSBDeviceInterface (IOUSBDeviceStruct100): 0 _reserved, 1 QueryInterface, 2 AddRef,
    # 3 Release, ..., 13 GetDeviceVendor, 14 GetDeviceProduct, 15 GetDeviceReleaseNumber, ..., 26 DeviceRequest
    SLOT_VENDOR, SLOT_PRODUCT, SLOT_RELEASE, SLOT_REQUEST = 13, 14, 15, 26

    wanted = {d["_location"]: d for d in devices}
    results = {}
    matching = iokit.IOServiceMatching(b"IOUSBHostDevice")
    iterator = c_uint32()
    if iokit.IOServiceGetMatchingServices(0, matching, ctypes.byref(iterator)) != 0:
        return {loc: (None, "IOServiceGetMatchingServicesError") for loc in wanted}
    while True:
        service = iokit.IOIteratorNext(iterator)
        if not service:
            break
        try:
            location = number(service, "locationID")
            device = wanted.get(location)
            if device is None:
                continue
            results[location] = _bos_one(ctypes, iokit, cf, service, device, device_user_client, plugin_interface,
                                         device_interface, QUERY, RELEASE, GET16, REQUEST, IOUSBDevRequest,
                                         (SLOT_VENDOR, SLOT_PRODUCT, SLOT_RELEASE, SLOT_REQUEST))
        except Exception as error:  # a fault of one device must not stop the probe
            results[location] = (None, type(error).__name__)
        finally:
            iokit.IOObjectRelease(service)
    iokit.IOObjectRelease(iterator.value)
    return results


def _bos_one(ctypes, iokit, cf, service, device, user_client, plugin_id, device_id, QUERY, RELEASE, GET16, REQUEST,
             IOUSBDevRequest, slots):
    plugin = ctypes.c_void_p()
    score = ctypes.c_int32()
    if iokit.IOCreatePlugInInterfaceForService(service, user_client, plugin_id, ctypes.byref(plugin),
                                               ctypes.byref(score)) != 0 or not plugin:
        return None, "PlugInNotCreated"
    plugin_table = ctypes.cast(ctypes.cast(plugin, ctypes.POINTER(ctypes.c_void_p))[0],
                               ctypes.POINTER(ctypes.c_void_p))
    query = QUERY(plugin_table[1])
    release_plugin = RELEASE(plugin_table[3])
    interface = ctypes.c_void_p()
    try:
        if query(plugin, cf.CFUUIDGetUUIDBytes(device_id), ctypes.byref(interface)) != 0 or not interface:
            return None, "InterfaceNotFound"
    finally:
        release_plugin(plugin)
    table = ctypes.cast(ctypes.cast(interface, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    release = RELEASE(table[3])
    try:
        vendor, product, release_number = ctypes.c_uint16(), ctypes.c_uint16(), ctypes.c_uint16()
        GET16(table[slots[0]])(interface, ctypes.byref(vendor))
        GET16(table[slots[1]])(interface, ctypes.byref(product))
        GET16(table[slots[2]])(interface, ctypes.byref(release_number))
        if (vendor.value, product.value, release_number.value) != (device["vendor"], device["product"],
                                                                   device["release"]):
            return None, "FunctionTableNotVerified"  # a wrong slot could reset the device: send nothing
        request = REQUEST(table[slots[3]])

        def read(length):
            buffer = (ctypes.c_ubyte * length)()
            req = IOUSBDevRequest(0x80, 6, 0x0F00, 0, length, ctypes.cast(buffer, ctypes.c_void_p), 0)
            code = request(interface, ctypes.byref(req))
            if code != 0:
                raise OSError(code & 0xFFFFFFFF)
            return bytes(buffer[:req.wLenDone])

        head = read(5)
        if len(head) < 5 or head[1] != 0x0F:
            return None, "NoBosDescriptor"
        total = min(head[2] | head[3] << 8, 1024)
        return bos_is_usb3_capable(read(total)), None
    except OSError:
        return None, "OSError"  # the IOReturn code is not printed: the class name only
    finally:
        release(interface)


# ----- the probe -----

def known_list(path):
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except (OSError, ValueError) as error:
        return {}, type(error).__name__
    out = {}
    for key, value in (data.get("cameras") or {}).items():
        if isinstance(value, dict) and isinstance(value.get("usb3_capable"), bool):
            out[key] = value["usb3_capable"]
    return out, None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--no-bos-request", action="store_true", help="skip the GET_DESCRIPTOR(BOS) request")
    parser.add_argument("--known", default="skellycam/core/camera/known_cameras.json")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print(json.dumps({"error": "NotMacOS"}))
        return 2
    try:
        listing = subprocess.run(["ioreg", "-a", "-l", "-r", "-c", "IOUSBHostDevice"], capture_output=True,
                                 check=True, timeout=20).stdout
        devices = devices_from_ioreg(listing)
    except Exception as error:
        print(json.dumps({"error": type(error).__name__, "method": "ioreg"}))
        return 1
    speeds, profiler_error = {}, None
    try:
        out = subprocess.run(["system_profiler", "-json", "SPUSBDataType"], capture_output=True, timeout=60).stdout
        speeds = speeds_from_system_profiler(out or b"{}")
    except Exception as error:
        profiler_error = type(error).__name__
    bos = {}
    if not args.no_bos_request:
        try:
            bos = bos_request_all(devices)
        except Exception as error:
            bos = {d["_location"]: (None, type(error).__name__) for d in devices}
    known, known_error = known_list(args.known)
    for device in devices:
        ident = (f"{device['vendor']:04x}:{device['product']:04x}" if isinstance(device["vendor"], int)
                 and isinstance(device["product"], int) else None)
        link = usb_link_from_speed(device["usb_speed"])
        bos_answer, bos_error = bos.get(device["_location"], (None, "Skipped" if args.no_bos_request else "NotFound"))
        print(json.dumps({
            "device": ident, "product_text": device["product_text"], "running_link": link,
            "usb_speed": device["usb_speed"], "link_speed": device["link_speed"],
            "bcd_usb": f"{device['bcd_usb']:04x}" if isinstance(device["bcd_usb"], int) else None,
            "methods": {
                "ioreg": {"usb3_capable": None, "capability_keys": device["capability_keys"]},
                "system_profiler": {"usb3_capable": None, "speed": speeds.get((device["vendor"], device["product"])),
                                    "error": profiler_error},
                "bcd_usb": {"usb3_capable": bcd_three_state(device["bcd_usb"], link)},
                "bos_request": {"usb3_capable": bos_answer, "error": bos_error},
                "known_list": {"usb3_capable": known.get(ident), "error": known_error},
            },
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
