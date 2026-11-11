"""IOKit (IOUSBLib) endpoint-0 transport through ctypes, WITHOUT opening or seizing anything.

UNTESTED: written on Windows from the IOUSBLib.h API; never run on a Mac. Every call is guarded and the caller
runs it in a child process that the runner kills on a hang or crash.

What it does (and the risk reasoning, macos.md section 5 and topology_macos.md verifier note 8):
- Finds the IOUSBHostDevice / IOUSBHostInterface service with a given locationID in the IORegistry.
- Creates the IOUSBLib user-client plug-in for it (IOCreatePlugInInterfaceForService) and QueryInterface's the
  device or interface COM interface. This attaches a user client next to Apple's UVC extension; that is what
  CameraController (macOS 12+ path, PR #26) and uvc-util do for UVC controls.
- **Never calls** USBDeviceOpen / USBDeviceOpenSeize / USBInterfaceOpen / USBInterfaceOpenSeize (the IOKit
  equivalents of claiming), SetConfiguration, SetAlternateInterface, ResetDevice or USBDeviceReEnumerate.
  Only these vtable slots are ever called, each listed in ALLOWED_* below:
    device:    QueryInterface, Release, GetDeviceClass..GetLocationID (getters), GetConfigurationDescriptorPtr,
               DeviceRequest / DeviceRequestTO (only with backend 'iokit-dev').
    interface: QueryInterface, Release, GetInterfaceClass..GetLocationID (getters), ControlRequest /
               ControlRequestTO.
- Before any request it verifies the vtable layout by calling getters and comparing them with the IORegistry
  (VID, PID, locationID, interface class/number). A mismatch aborts with 'vtable_mismatch'.
- An unopened ControlRequest/DeviceRequest is outside Apple's documented contract (libusb darwin_usb.c comment,
  "Apple's USB Prober doesn't bother"); CameraController and uvc-util rely on it on macOS 12+. Hence opt-in.

vtable indices (IOUSBLib.h; IUNKNOWN_C_GUTS = _reserved, QueryInterface, AddRef, Release occupy 0-3):
  IOUSBDeviceInterface(182): 10 GetDeviceClass, 11 GetDeviceSubClass, 12 GetDeviceProtocol, 13 GetDeviceVendor,
    14 GetDeviceProduct, 15 GetDeviceReleaseNumber, 16 GetDeviceAddress, 17 GetDeviceBusPowerAvailable,
    18 GetDeviceSpeed, 19 GetNumberOfConfigurations, 20 GetLocationID, 21 GetConfigurationDescriptorPtr,
    22 GetConfiguration, 23 SetConfiguration (never), 24 GetBusFrameNumber, 25 ResetDevice (never),
    26 DeviceRequest, 27 DeviceRequestAsync, 28 CreateInterfaceIterator, 29 USBDeviceOpenSeize (never),
    30 DeviceRequestTO.
  IOUSBInterfaceInterface(182/190): 8 USBInterfaceOpen (never), 10 GetInterfaceClass, 11 GetInterfaceSubClass,
    12 GetInterfaceProtocol, 13 GetDeviceVendor, 14 GetDeviceProduct, 15 GetDeviceReleaseNumber,
    16 GetConfigurationValue, 17 GetInterfaceNumber, 18 GetAlternateSetting, 19 GetNumEndpoints,
    20 GetLocationID, 21 GetDevice, 22 SetAlternateInterface (never), 23 GetBusFrameNumber, 24 ControlRequest,
    37 ControlRequestTO.
Layout check: the getters 10-20 must all return kIOReturnSuccess and match the IORegistry; a layout error that
would move ControlRequest onto SetAlternateInterface needs two phantom slots between 20 and 24, which the header
does not have. The device route (DeviceRequest at 26 next to ResetDevice at 25) is used only on explicit request.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import sys
import uuid
from typing import Any

IS_MAC = sys.platform == "darwin"

# UUIDs (IOUSBLib.h / IOCFPlugIn.h); CFUUIDBytes are the bytes in string order.
UUIDS = {
    "kIOUSBDeviceUserClientTypeID": "9dc7b780-9ec0-11d4-a54f-000a27052861",
    "kIOUSBInterfaceUserClientTypeID": "2d9786c6-9ef3-11d4-ad51-000a27052861",
    "kIOCFPlugInInterfaceID": "c244e858-109c-11d4-91d4-0050e4c6426f",
    "kIOUSBDeviceInterfaceID": "5c8187d0-9ef3-11d4-8b45-000a27052861",
    "kIOUSBDeviceInterfaceID182": "152fc496-4891-11d5-9d52-000a27052861",
    "kIOUSBInterfaceInterfaceID": "73c97ae8-9ef3-11d4-b1d0-000a27052861",
    "kIOUSBInterfaceInterfaceID182": "4923ac4c-4896-11d5-9208-000a27052861",
    "kIOUSBInterfaceInterfaceID190": "8fdb8455-74a6-11d6-97b1-003065d3608e",
}
DEVICE_IIDS = [("kIOUSBDeviceInterfaceID182", True), ("kIOUSBDeviceInterfaceID", False)]
INTERFACE_IIDS = [("kIOUSBInterfaceInterfaceID190", True), ("kIOUSBInterfaceInterfaceID182", True),
                  ("kIOUSBInterfaceInterfaceID", False)]

ALLOWED_DEVICE_SLOTS = {1: "QueryInterface", 3: "Release", 10: "GetDeviceClass", 11: "GetDeviceSubClass",
                        12: "GetDeviceProtocol", 13: "GetDeviceVendor", 14: "GetDeviceProduct",
                        15: "GetDeviceReleaseNumber", 18: "GetDeviceSpeed", 20: "GetLocationID",
                        21: "GetConfigurationDescriptorPtr", 26: "DeviceRequest", 30: "DeviceRequestTO"}
ALLOWED_INTERFACE_SLOTS = {1: "QueryInterface", 3: "Release", 10: "GetInterfaceClass", 11: "GetInterfaceSubClass",
                           12: "GetInterfaceProtocol", 13: "GetDeviceVendor", 14: "GetDeviceProduct",
                           17: "GetInterfaceNumber", 18: "GetAlternateSetting", 19: "GetNumEndpoints",
                           20: "GetLocationID", 24: "ControlRequest", 37: "ControlRequestTO"}
FORBIDDEN = {"USBDeviceOpen", "USBDeviceOpenSeize", "USBInterfaceOpen", "USBInterfaceOpenSeize", "SetConfiguration",
             "SetAlternateInterface", "ResetDevice", "USBDeviceReEnumerate"}
assert not FORBIDDEN & set(ALLOWED_DEVICE_SLOTS.values()) and not FORBIDDEN & set(ALLOWED_INTERFACE_SLOTS.values())

kCFStringEncodingUTF8 = 0x08000100
kCFNumberSInt64Type = 4


class CFUUIDBytes(ctypes.Structure):
    _fields_ = [("b", ctypes.c_uint8 * 16)]


def uuid_bytes(name: str) -> CFUUIDBytes:
    u = CFUUIDBytes()
    raw = uuid.UUID(UUIDS[name]).bytes
    for i in range(16):
        u.b[i] = raw[i]
    return u


class IOUSBDevRequest(ctypes.Structure):
    _fields_ = [("bmRequestType", ctypes.c_uint8), ("bRequest", ctypes.c_uint8), ("wValue", ctypes.c_uint16),
                ("wIndex", ctypes.c_uint16), ("wLength", ctypes.c_uint16), ("pData", ctypes.c_void_p),
                ("wLenDone", ctypes.c_uint32)]


class IOUSBDevRequestTO(ctypes.Structure):
    _fields_ = [("bmRequestType", ctypes.c_uint8), ("bRequest", ctypes.c_uint8), ("wValue", ctypes.c_uint16),
                ("wIndex", ctypes.c_uint16), ("wLength", ctypes.c_uint16), ("pData", ctypes.c_void_p),
                ("wLenDone", ctypes.c_uint32), ("noDataTimeout", ctypes.c_uint32),
                ("completionTimeout", ctypes.c_uint32)]


class _Libs:
    _inst = None

    def __init__(self) -> None:
        self.iokit = ctypes.CDLL(ctypes.util.find_library("IOKit") or "/System/Library/Frameworks/IOKit.framework/IOKit")
        self.cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation")
                              or "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        io, cf = self.iokit, self.cf
        io.IOServiceMatching.argtypes = [ctypes.c_char_p]
        io.IOServiceMatching.restype = ctypes.c_void_p
        io.IOServiceGetMatchingServices.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        io.IOServiceGetMatchingServices.restype = ctypes.c_int
        io.IOIteratorNext.argtypes = [ctypes.c_uint32]
        io.IOIteratorNext.restype = ctypes.c_uint32
        io.IOObjectRelease.argtypes = [ctypes.c_uint32]
        io.IOObjectRelease.restype = ctypes.c_int
        io.IORegistryEntryCreateCFProperty.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
        io.IORegistryEntryCreateCFProperty.restype = ctypes.c_void_p
        io.IORegistryEntryGetRegistryEntryID.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint64)]
        io.IORegistryEntryGetRegistryEntryID.restype = ctypes.c_int
        io.IORegistryEntryGetChildIterator.argtypes = [ctypes.c_uint32, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32)]
        io.IORegistryEntryGetChildIterator.restype = ctypes.c_int
        io.IOObjectConformsTo.argtypes = [ctypes.c_uint32, ctypes.c_char_p]
        io.IOObjectConformsTo.restype = ctypes.c_uint32
        io.IOCreatePlugInInterfaceForService.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p,
                                                         ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int32)]
        io.IOCreatePlugInInterfaceForService.restype = ctypes.c_int
        io.IODestroyPlugInInterface.argtypes = [ctypes.c_void_p]
        io.IODestroyPlugInInterface.restype = ctypes.c_int
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        cf.CFNumberGetValue.restype = ctypes.c_bool
        cf.CFGetTypeID.argtypes = [ctypes.c_void_p]
        cf.CFGetTypeID.restype = ctypes.c_ulong
        cf.CFNumberGetTypeID.restype = ctypes.c_ulong
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFUUIDCreateFromString.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cf.CFUUIDCreateFromString.restype = ctypes.c_void_p
        self._cfstr_cache: dict[str, int] = {}

    @classmethod
    def get(cls) -> "_Libs":
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    def cfstr(self, s: str) -> int:
        if s not in self._cfstr_cache:
            self._cfstr_cache[s] = self.cf.CFStringCreateWithCString(None, s.encode(), kCFStringEncodingUTF8)
        return self._cfstr_cache[s]

    def cfuuid(self, name: str) -> int:
        return self.cf.CFUUIDCreateFromString(None, self.cfstr(UUIDS[name].upper()))

    def int_prop(self, service: int, key: str) -> int | None:
        ref = self.iokit.IORegistryEntryCreateCFProperty(service, self.cfstr(key), None, 0)
        if not ref:
            return None
        try:
            if self.cf.CFGetTypeID(ref) != self.cf.CFNumberGetTypeID():
                return None
            v = ctypes.c_int64()
            ok = self.cf.CFNumberGetValue(ref, kCFNumberSInt64Type, ctypes.byref(v))
            return int(v.value) if ok else None
        finally:
            self.cf.CFRelease(ref)


def find_services(class_name: str, location_id: int, extra: dict[str, int] | None = None) -> list[int]:
    """io_service_t handles of class_name with this locationID (and extra int props). Caller releases them."""
    L = _Libs.get()
    matching = L.iokit.IOServiceMatching(class_name.encode())
    it = ctypes.c_uint32(0)
    kr = L.iokit.IOServiceGetMatchingServices(0, matching, ctypes.byref(it))  # consumes `matching`
    if kr != 0:
        return []
    out = []
    while True:
        s = L.iokit.IOIteratorNext(it.value)
        if not s:
            break
        keep = L.int_prop(s, "locationID") == location_id
        if keep and extra:
            for k, v in extra.items():
                if L.int_prop(s, k) != v:
                    keep = False
                    break
        if keep:
            out.append(s)
        else:
            L.iokit.IOObjectRelease(s)
    L.iokit.IOObjectRelease(it.value)
    return out


def find_interface_services(location_id: int, interface_number: int) -> tuple[list[int], str]:
    """IOUSBHostInterface services of the device at location_id with bInterfaceNumber. Tries the interface's own
    locationID property first, then walks the device's IOService children (in case interfaces carry no locationID)."""
    svcs = find_services("IOUSBHostInterface", location_id, {"bInterfaceNumber": interface_number})
    if svcs:
        return svcs, "interface locationID"
    L = _Libs.get()
    out = []
    for dev in find_services("IOUSBHostDevice", location_id):
        it = ctypes.c_uint32(0)
        if L.iokit.IORegistryEntryGetChildIterator(dev, b"IOService", ctypes.byref(it)) == 0:
            while True:
                ch = L.iokit.IOIteratorNext(it.value)
                if not ch:
                    break
                if L.iokit.IOObjectConformsTo(ch, b"IOUSBHostInterface") and                         L.int_prop(ch, "bInterfaceNumber") == interface_number:
                    out.append(ch)
                else:
                    L.iokit.IOObjectRelease(ch)
            L.iokit.IOObjectRelease(it.value)
        L.iokit.IOObjectRelease(dev)
    return out, "device children"


class _ComObject:
    """A COM-style IOUSBLib interface pointer (pointer to pointer to vtable) with an allow-list of slots."""

    def __init__(self, ptr: int, allowed: dict[int, str]):
        self.ptr = ctypes.c_void_p(ptr)
        self.allowed = allowed
        self._vt = ctypes.cast(ctypes.cast(self.ptr, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))

    def fn(self, slot: int, restype, *argtypes):
        if slot not in self.allowed:
            raise PermissionError(f"vtable slot {slot} is not on the allow-list")
        addr = self._vt[slot]
        if not addr:
            raise OSError(f"vtable slot {slot} ({self.allowed[slot]}) is NULL")
        return ctypes.CFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(addr)

    def get_u8(self, slot: int) -> tuple[int, int | None]:
        v = ctypes.c_uint8()
        kr = self.fn(slot, ctypes.c_int32, ctypes.POINTER(ctypes.c_uint8))(self.ptr, ctypes.byref(v))
        return kr, (v.value if kr == 0 else None)

    def get_u16(self, slot: int) -> tuple[int, int | None]:
        v = ctypes.c_uint16()
        kr = self.fn(slot, ctypes.c_int32, ctypes.POINTER(ctypes.c_uint16))(self.ptr, ctypes.byref(v))
        return kr, (v.value if kr == 0 else None)

    def get_u32(self, slot: int) -> tuple[int, int | None]:
        v = ctypes.c_uint32()
        kr = self.fn(slot, ctypes.c_int32, ctypes.POINTER(ctypes.c_uint32))(self.ptr, ctypes.byref(v))
        return kr, (v.value if kr == 0 else None)

    def release(self) -> None:
        try:
            self.fn(3, ctypes.c_uint32)(self.ptr)
        except Exception:
            pass


def _plugin_query(service: int, client_type: str, iids: list[tuple[str, bool]], allowed: dict[int, str]) -> dict:
    """Create the plug-in for service and QueryInterface the first IID that answers."""
    L = _Libs.get()
    plugin = ctypes.c_void_p()
    score = ctypes.c_int32()
    kr = L.iokit.IOCreatePlugInInterfaceForService(service, L.cfuuid(client_type), L.cfuuid("kIOCFPlugInInterfaceID"),
                                                   ctypes.byref(plugin), ctypes.byref(score))
    out: dict[str, Any] = {"create_plugin_kr": kr & 0xFFFFFFFF, "obj": None, "iid": None, "has_to": False, "qi": []}
    if kr != 0 or not plugin.value:
        return out
    pvt = ctypes.cast(ctypes.cast(plugin, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    qi = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, CFUUIDBytes, ctypes.POINTER(ctypes.c_void_p))(pvt[1])
    try:
        for name, has_to in iids:
            obj = ctypes.c_void_p()
            hr = qi(plugin, uuid_bytes(name), ctypes.byref(obj))
            out["qi"].append({"iid": name, "hr": hr & 0xFFFFFFFF})
            if hr == 0 and obj.value:
                out.update(obj=_ComObject(obj.value, allowed), iid=name, has_to=has_to)
                break
    finally:
        L.iokit.IODestroyPlugInInterface(plugin)
    return out


class IOKitInterfaceTransport:
    """ep0 requests through the camera's VideoControl IOUSBHostInterface (CameraController / uvc-util pattern),
    without USBInterfaceOpen. Requests addressed to another interface (GET_INTERFACE / VS_COMMIT on a
    VideoStreaming interface) are sent through that interface's own transport (see for_interface)."""
    name = "iokit-intf"

    def __init__(self, location_id: int, interface_number: int, vid: str | None = None, pid: str | None = None):
        self.location_id, self.interface_number = int(location_id), int(interface_number)
        self.vid, self.pid = vid, pid
        self.obj: _ComObject | None = None
        self.info: dict[str, Any] = {"backend": self.name, "location_id": f"0x{self.location_id:08x}",
                                     "interface": self.interface_number, "opened_interface": False,
                                     "seize": False}

    def setup(self) -> dict:
        L = _Libs.get()
        svcs, how = find_interface_services(self.location_id, self.interface_number)
        self.info["services_found"], self.info["service_lookup"] = len(svcs), how
        if not svcs:
            self.info["error"] = "interface service not found"
            return self.info
        svc = svcs[0]
        try:
            q = _plugin_query(svc, "kIOUSBInterfaceUserClientTypeID", INTERFACE_IIDS, ALLOWED_INTERFACE_SLOTS)
        finally:
            for s in svcs:
                L.iokit.IOObjectRelease(s)
        self.info.update({k: v for k, v in q.items() if k != "obj"})
        self.obj = q["obj"]
        if self.obj is None:
            self.info["error"] = "plug-in or QueryInterface failed"
            return self.info
        self.info["verify"] = self._verify()
        if not self.info["verify"]["ok"]:
            self.info["error"] = "vtable_mismatch"
            self.obj.release()
            self.obj = None
        return self.info

    def _verify(self) -> dict:
        o = self.obj
        v: dict[str, Any] = {}
        checks = [("interface_class", 10, o.get_u8), ("interface_subclass", 11, o.get_u8),
                  ("vendor", 13, o.get_u16), ("product", 14, o.get_u16), ("interface_number", 17, o.get_u8),
                  ("alt_cached", 18, o.get_u8), ("num_endpoints", 19, o.get_u8), ("location_id", 20, o.get_u32)]
        ok = True
        for key, slot, getter in checks:
            try:
                kr, val = getter(slot)
            except Exception as e:
                kr, val = f"exception {e!r}", None
            v[key] = val
            v[key + "_kr"] = kr if isinstance(kr, str) else kr & 0xFFFFFFFF
            if kr != 0:
                ok = False
        if v.get("location_id") != self.location_id or v.get("interface_number") != self.interface_number \
                or v.get("interface_class") != 14:
            ok = False
        if self.vid and v.get("vendor") is not None and f"{v['vendor']:04x}" != self.vid.lower():
            ok = False
        if self.pid and v.get("product") is not None and f"{v['product']:04x}" != self.pid.lower():
            ok = False
        v["ok"] = ok
        return v

    def cached_alt(self) -> dict:
        if self.obj is None:
            return {"ok": False}
        kr, val = self.obj.get_u8(18)
        return {"ok": kr == 0, "kr": kr & 0xFFFFFFFF, "alt": val, "note": "IOUSBLib GetAlternateSetting (user-space "
                "cached value; whether it tracks the live alt is untested)"}

    def _request(self, bm: int, req: int, wv: int, wi: int, buf, length: int, timeout_ms: int) -> tuple[int, int]:
        o = self.obj
        if o is None:
            return (0xE00002CD, 0)  # kIOReturnNotOpen: no transport
        if self.info.get("has_to"):
            r = IOUSBDevRequestTO(bm, req, wv, wi, length, (ctypes.addressof(buf) if buf is not None else None),
                                  0, int(timeout_ms), int(timeout_ms))
            f = o.fn(37, ctypes.c_int32, ctypes.c_uint8, ctypes.POINTER(IOUSBDevRequestTO))
            kr = f(o.ptr, 0, ctypes.byref(r))
        else:
            r = IOUSBDevRequest(bm, req, wv, wi, length, (ctypes.addressof(buf) if buf is not None else None), 0)
            f = o.fn(24, ctypes.c_int32, ctypes.c_uint8, ctypes.POINTER(IOUSBDevRequest))
            kr = f(o.ptr, 0, ctypes.byref(r))
        return kr, r.wLenDone

    def ctrl_in(self, bm, req, wv, wi, length, timeout_ms):
        buf = ctypes.create_string_buffer(max(1, int(length)))
        kr, done = self._request(bm, req, wv, wi, buf, int(length), timeout_ms)
        return (kr & 0xFFFFFFFF if kr else 0), (buf.raw[:done] if kr == 0 else b"")

    def ctrl_out(self, bm, req, wv, wi, data, timeout_ms):
        buf = ctypes.create_string_buffer(bytes(data), len(data)) if data else None
        kr, _ = self._request(bm, req, wv, wi, buf, len(data or b""), timeout_ms)
        return kr & 0xFFFFFFFF if kr else 0

    def close(self) -> None:
        if self.obj is not None:
            self.obj.release()
            self.obj = None


class IOKitDeviceTransport:
    """The camera's IOUSBHostDevice user client without USBDeviceOpen. Used for GetConfigurationDescriptorPtr (the
    OS's cached copy; whether it causes bus traffic is unverified: topology_macos verifier note 8) and, only with
    backend 'iokit-dev', DeviceRequest (libusb / USB Prober pattern)."""
    name = "iokit-dev"

    def __init__(self, location_id: int, vid: str | None = None, pid: str | None = None, allow_requests: bool = False):
        self.location_id, self.vid, self.pid = int(location_id), vid, pid
        self.allow_requests = allow_requests
        self.obj: _ComObject | None = None
        self.info: dict[str, Any] = {"backend": self.name, "location_id": f"0x{self.location_id:08x}",
                                     "opened_device": False, "seize": False}

    def setup(self) -> dict:
        L = _Libs.get()
        svcs = find_services("IOUSBHostDevice", self.location_id)
        self.info["services_found"] = len(svcs)
        if not svcs:
            self.info["error"] = "device service not found"
            return self.info
        try:
            q = _plugin_query(svcs[0], "kIOUSBDeviceUserClientTypeID", DEVICE_IIDS, ALLOWED_DEVICE_SLOTS)
        finally:
            for s in svcs:
                L.iokit.IOObjectRelease(s)
        self.info.update({k: v for k, v in q.items() if k != "obj"})
        self.obj = q["obj"]
        if self.obj is None:
            self.info["error"] = "plug-in or QueryInterface failed"
            return self.info
        o = self.obj
        v: dict[str, Any] = {}
        ok = True
        for key, slot, getter in [("device_class", 10, o.get_u8), ("vendor", 13, o.get_u16), ("product", 14, o.get_u16),
                                  ("release", 15, o.get_u16), ("speed", 18, o.get_u8), ("location_id", 20, o.get_u32)]:
            try:
                kr, val = getter(slot)
            except Exception as e:
                kr, val = f"exception {e!r}", None
            v[key], v[key + "_kr"] = val, (kr if isinstance(kr, str) else kr & 0xFFFFFFFF)
            ok &= kr == 0
        ok &= v.get("location_id") == self.location_id
        if self.vid and v.get("vendor") is not None:
            ok &= f"{v['vendor']:04x}" == self.vid.lower()
        if self.pid and v.get("product") is not None:
            ok &= f"{v['product']:04x}" == self.pid.lower()
        v["ok"] = bool(ok)
        self.info["verify"] = v
        if not ok:
            self.info["error"] = "vtable_mismatch"
            o.release()
            self.obj = None
        return self.info

    def config_descriptor(self, index: int = 0) -> tuple[int, bytes]:
        if self.obj is None:
            return 0xE00002CD, b""
        p = ctypes.c_void_p()
        f = self.obj.fn(21, ctypes.c_int32, ctypes.c_uint8, ctypes.POINTER(ctypes.c_void_p))
        kr = f(self.obj.ptr, int(index), ctypes.byref(p))
        if kr != 0 or not p.value:
            return kr & 0xFFFFFFFF, b""
        head = ctypes.string_at(p.value, 4)
        if len(head) < 4 or head[1] != 2:
            return 0xE00002C2, head
        total = int.from_bytes(head[2:4], "little")
        if total < 9 or total > 65535:
            return 0xE00002C2, head
        return 0, ctypes.string_at(p.value, total)

    def _request(self, bm, req, wv, wi, buf, length, timeout_ms):
        if self.obj is None or not self.allow_requests:
            return 0xE00002C7, 0  # kIOReturnUnsupported: device requests not enabled
        pdata = ctypes.addressof(buf) if buf is not None else None
        if self.info.get("has_to"):
            r = IOUSBDevRequestTO(bm, req, wv, wi, length, pdata, 0, int(timeout_ms), int(timeout_ms))
            kr = self.obj.fn(30, ctypes.c_int32, ctypes.POINTER(IOUSBDevRequestTO))(self.obj.ptr, ctypes.byref(r))
            return kr, r.wLenDone
        r0 = IOUSBDevRequest(bm, req, wv, wi, length, pdata, 0)
        kr = self.obj.fn(26, ctypes.c_int32, ctypes.POINTER(IOUSBDevRequest))(self.obj.ptr, ctypes.byref(r0))
        return kr, r0.wLenDone

    def ctrl_in(self, bm, req, wv, wi, length, timeout_ms):
        buf = ctypes.create_string_buffer(max(1, int(length)))
        kr, done = self._request(bm, req, wv, wi, buf, int(length), timeout_ms)
        return (kr & 0xFFFFFFFF if kr else 0), (buf.raw[:done] if kr == 0 else b"")

    def ctrl_out(self, bm, req, wv, wi, data, timeout_ms):
        buf = ctypes.create_string_buffer(bytes(data), len(data)) if data else None
        kr, _ = self._request(bm, req, wv, wi, buf, len(data or b""), timeout_ms)
        return kr & 0xFFFFFFFF if kr else 0

    def close(self) -> None:
        if self.obj is not None:
            self.obj.release()
            self.obj = None
