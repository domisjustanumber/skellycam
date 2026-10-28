# /// script
# requires-python = ">=3.10"
# ///
"""Windows (no admin): dump every identity-relevant fact about each UVC camera.

Run (from repo root, camera lock held because it sends GET_DESCRIPTOR control requests to EP0):
    uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/naming/win_identity_dump.py
Options:
    --out-dir DIR      default research/usb_cameras/results/windows/<hostname>/naming
    --label NAME       also write snapshots/<NAME>.json (flat identifier snapshot used by identity_diff.py)
    --no-descriptors   skip hub IOCTLs (pure PnP data only)

Writes:
    <out-dir>/identity_dump.json   everything (PnP properties, interfaces, hub chain, parsed+raw descriptors)
    <out-dir>/descriptors.json     descriptor-focused view reused by the bandwidth/timing work (schema: naming/README.md)

Data sources (all user-mode, no elevation):
  * cfgmgr32 CM_Get_Device_ID_ListW / CM_Get_DevNode_PropertyW  -> instance IDs, hardware/compatible IDs,
    DEVPKEY_Device_LocationPaths, LocationInfo, ContainerId, BusReportedDeviceDesc, Address (=port), parents.
  * CM_Get_Device_Interface_ListW for KSCATEGORY_VIDEO_CAMERA / KSCATEGORY_CAPTURE / KSCATEGORY_VIDEO /
    KSCATEGORY_SENSOR_CAMERA / GUID_DEVINTERFACE_USB_DEVICE -> symbolic links used by MF / DirectShow.
  * Parent hub opened via GUID_DEVINTERFACE_USB_HUB, then
    IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX(_V2), IOCTL_USB_GET_NODE_CONNECTION_DRIVERKEY_NAME,
    IOCTL_USB_GET_PORT_CONNECTOR_PROPERTIES, IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION
    (device, configuration, BOS, string descriptors).
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import datetime as _dt
import json
import os
import platform
import socket
import struct
import sys
import uuid
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import usbdesc  # noqa: E402

cfg = ctypes.WinDLL("cfgmgr32")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_str(cls, s: str) -> "GUID":
        g = cls()
        ctypes.memmove(ctypes.byref(g), uuid.UUID(s).bytes_le, 16)
        return g


class DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wt.ULONG)]


def _key(fmtid: str, pid: int) -> DEVPROPKEY:
    return DEVPROPKEY(GUID.from_str(fmtid), pid)


_DEV = "a45c254e-df1c-4efd-8020-67d146a850e0"
_REL = "4340a6c5-93fa-4706-972c-7b648008a5a7"
_BUS = "540b947e-8b40-45bc-a8a2-6a0b894cbda2"
_DRV = "a8b865dd-2e3d-4094-ad97-e593a70c75d6"
_DATES = "83da6326-97a6-4088-9453-a1923f573b29"
PROPS = {
    "DeviceDesc": _key(_DEV, 2), "HardwareIds": _key(_DEV, 3), "CompatibleIds": _key(_DEV, 4),
    "Service": _key(_DEV, 6), "Class": _key(_DEV, 9), "ClassGuid": _key(_DEV, 10), "Driver": _key(_DEV, 11),
    "Manufacturer": _key(_DEV, 13), "FriendlyName": _key(_DEV, 14), "LocationInfo": _key(_DEV, 15),
    "PDOName": _key(_DEV, 16), "UINumber": _key(_DEV, 18), "BusNumber": _key(_DEV, 23),
    "EnumeratorName": _key(_DEV, 24), "Address": _key(_DEV, 30), "LocationPaths": _key(_DEV, 37),
    "InstanceId": _key("78c34fc8-104a-4aca-9ea4-524d52996e57", 256),
    "ContainerId": _key("8c7ed206-3f8a-4827-b3ab-ae9e1faefc6c", 2),
    "BusReportedDeviceDesc": _key(_BUS, 4), "IsPresent": _key(_BUS, 5),
    "Parent": _key(_REL, 8), "Children": _key(_REL, 9), "Siblings": _key(_REL, 10),
    "DriverDate": _key(_DRV, 2), "DriverVersion": _key(_DRV, 3), "DriverInfPath": _key(_DRV, 5),
    "DriverProvider": _key(_DRV, 9),
    "InstallDate": _key(_DATES, 100), "FirstInstallDate": _key(_DATES, 101),
    "LastArrivalDate": _key(_DATES, 102), "LastRemovalDate": _key(_DATES, 103),
}
IFACE_FRIENDLY = _key("026e516e-b814-414b-83cd-856d6fef4822", 2)
IFACE_ENABLED = _key("026e516e-b814-414b-83cd-856d6fef4822", 3)
IFACE_CLASSES = {
    "KSCATEGORY_VIDEO_CAMERA": "e5323777-f976-4f5b-9b55-b94699c46e44",
    "KSCATEGORY_CAPTURE": "65e8773d-8f56-11d0-a3b9-00a0c9223196",
    "KSCATEGORY_VIDEO": "6994ad05-93ef-11d0-a3cc-00a0c9223196",
    "KSCATEGORY_SENSOR_CAMERA": "24e552d7-6523-47f7-a647-d3465bf1f5ca",
    "GUID_DEVINTERFACE_USB_DEVICE": "a5dcbf10-6530-11d2-901f-00c04fb951ed",
}
GUID_DEVINTERFACE_USB_HUB = "f18a0e88-c30c-11d0-8815-00a0c906bed8"

CR_SUCCESS, CR_BUFFER_SMALL = 0, 0x1A
CM_GETIDLIST_FILTER_ENUMERATOR, CM_GETIDLIST_FILTER_PRESENT = 0x1, 0x100


def _cm_check(cr: int, what: str) -> None:
    if cr != CR_SUCCESS:
        raise OSError(f"{what} failed CR=0x{cr:x}")


def list_device_ids(enumerator: str = "USB") -> list[str]:
    n = wt.ULONG()
    flags = CM_GETIDLIST_FILTER_ENUMERATOR | CM_GETIDLIST_FILTER_PRESENT
    _cm_check(cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(n), enumerator, flags), "CM_Get_Device_ID_List_Size")
    buf = ctypes.create_unicode_buffer(n.value)
    _cm_check(cfg.CM_Get_Device_ID_ListW(enumerator, buf, n.value, flags), "CM_Get_Device_ID_List")
    return [s for s in buf[:n.value].split("\0") if s]


def locate(instance_id: str, phantom: bool = False) -> int:
    dn = wt.DWORD()
    _cm_check(cfg.CM_Locate_DevNodeW(ctypes.byref(dn), instance_id, 1 if phantom else 0),  # CM_LOCATE_DEVNODE_PHANTOM
              f"CM_Locate_DevNode({instance_id})")
    return dn.value


def device_history(vid: str, pid: str) -> list[dict]:
    """Every instance (present or not) PnP has ever created for this VID:PID composite device on this machine.

    Non-present ('phantom') instances are what Windows remembers from earlier plug-ins at other ports, so they
    show directly whether a camera got a new instance id / ContainerId when it was moved.
    """
    n = wt.ULONG()
    _cm_check(cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(n), "USB", CM_GETIDLIST_FILTER_ENUMERATOR), "size")
    buf = ctypes.create_unicode_buffer(n.value)
    _cm_check(cfg.CM_Get_Device_ID_ListW("USB", buf, n.value, CM_GETIDLIST_FILTER_ENUMERATOR), "list")
    prefix = f"USB\\VID_{vid}&PID_{pid}\\".upper()
    out = []
    for iid in (s for s in buf[:n.value].split("\0") if s):
        if not iid.upper().startswith(prefix):
            continue
        try:
            p = devnode_props(locate(iid, phantom=True))
        except OSError as e:
            out.append(dict(instance_id=iid, error=str(e)))
            continue
        out.append(dict(instance_id=p.get("InstanceId", iid), present=bool(p.get("IsPresent")),
                        **{k: p.get(k) for k in ("LocationPaths", "LocationInfo", "ContainerId", "Address",
                                                 "FirstInstallDate", "LastArrivalDate", "LastRemovalDate")}))
    return out


def _decode_prop(ptype: int, raw: bytes):
    base, is_list, is_array = ptype & 0xFFF, ptype & 0x2000, ptype & 0x1000
    if is_array and base == 0x03:  # BINARY
        return raw.hex()
    if base == 0x12 and is_list:  # STRING_LIST
        return [s for s in raw.decode("utf-16-le").split("\0") if s]
    if base == 0x12:
        return raw.decode("utf-16-le").rstrip("\0")
    if base == 0x0D:
        return "{" + str(uuid.UUID(bytes_le=raw[:16])) + "}"
    if base == 0x07:
        return struct.unpack("<I", raw[:4])[0]
    if base == 0x05:
        return struct.unpack("<H", raw[:2])[0]
    if base == 0x03:
        return raw[0]
    if base == 0x11:
        return raw[0] != 0
    if base == 0x10:  # FILETIME
        ft = struct.unpack("<Q", raw[:8])[0]
        return (_dt.datetime(1601, 1, 1, tzinfo=_dt.timezone.utc) + _dt.timedelta(microseconds=ft // 10)).isoformat()
    return {"devprop_type": f"0x{ptype:x}", "hex": raw.hex()}


def devnode_prop(dn: int, key: DEVPROPKEY):
    ptype, size = wt.ULONG(), wt.ULONG(0)
    cr = cfg.CM_Get_DevNode_PropertyW(dn, ctypes.byref(key), ctypes.byref(ptype), None, ctypes.byref(size), 0)
    if cr != CR_BUFFER_SMALL:
        return None
    buf = (ctypes.c_ubyte * size.value)()
    cr = cfg.CM_Get_DevNode_PropertyW(dn, ctypes.byref(key), ctypes.byref(ptype), buf, ctypes.byref(size), 0)
    if cr != CR_SUCCESS:
        return None
    return _decode_prop(ptype.value, bytes(buf))


def devnode_props(dn: int) -> dict:
    out = {}
    for name, key in PROPS.items():
        v = devnode_prop(dn, key)
        if v is not None:
            out[name] = v
    st, prob = wt.ULONG(), wt.ULONG()
    if cfg.CM_Get_DevNode_Status(ctypes.byref(st), ctypes.byref(prob), dn, 0) == CR_SUCCESS:
        out["DevNodeStatus"] = f"0x{st.value:08x}"
        out["ProblemCode"] = prob.value
    return out


def interface_list(guid: str, instance_id: str | None) -> list[str]:
    g = GUID.from_str(guid)
    n = wt.ULONG()
    _cm_check(cfg.CM_Get_Device_Interface_List_SizeW(ctypes.byref(n), ctypes.byref(g), instance_id, 0),
              "CM_Get_Device_Interface_List_Size")
    buf = ctypes.create_unicode_buffer(n.value)
    _cm_check(cfg.CM_Get_Device_Interface_ListW(ctypes.byref(g), instance_id, buf, n.value, 0),
              "CM_Get_Device_Interface_List")
    return [s for s in buf[:n.value].split("\0") if s]


def interface_prop(path: str, key: DEVPROPKEY):
    ptype, size = wt.ULONG(), wt.ULONG(0)
    cr = cfg.CM_Get_Device_Interface_PropertyW(path, ctypes.byref(key), ctypes.byref(ptype), None, ctypes.byref(size), 0)
    if cr != CR_BUFFER_SMALL:
        return None
    buf = (ctypes.c_ubyte * size.value)()
    if cfg.CM_Get_Device_Interface_PropertyW(path, ctypes.byref(key), ctypes.byref(ptype), buf, ctypes.byref(size), 0):
        return None
    return _decode_prop(ptype.value, bytes(buf))


def registry_values(path: str) -> dict:
    out = {}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            i = 0
            while True:
                try:
                    name, val, typ = winreg.EnumValue(k, i)
                except OSError:
                    break
                out[name] = val.hex() if isinstance(val, bytes) else val
                i += 1
    except OSError:
        return {}
    return out


# ---------------------------------------------------------------- hub IOCTLs
GENERIC_WRITE, FILE_SHARE_WRITE, OPEN_EXISTING = 0x40000000, 0x2, 3
INVALID_HANDLE = ctypes.c_void_p(-1).value
k32.CreateFileW.restype = wt.HANDLE
k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE]
k32.DeviceIoControl.argtypes = [wt.HANDLE, wt.DWORD, wt.LPVOID, wt.DWORD, wt.LPVOID, wt.DWORD,
                                ctypes.POINTER(wt.DWORD), wt.LPVOID]
k32.CloseHandle.argtypes = [wt.HANDLE]


def _ctl(fn: int) -> int:  # CTL_CODE(FILE_DEVICE_USB=0x22, fn, METHOD_BUFFERED, FILE_ANY_ACCESS)
    return (0x22 << 16) | (fn << 2)


IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX = _ctl(274)
IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX_V2 = _ctl(279)
IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION = _ctl(260)
IOCTL_USB_GET_NODE_CONNECTION_DRIVERKEY_NAME = _ctl(264)
IOCTL_USB_GET_PORT_CONNECTOR_PROPERTIES = _ctl(278)
IOCTL_USB_GET_HUB_INFORMATION_EX = _ctl(277)
CONNECTION_STATUS = ["NoDeviceConnected", "DeviceConnected", "DeviceFailedEnumeration", "DeviceGeneralFailure",
                     "DeviceCausedOvercurrent", "DeviceNotEnoughPower", "DeviceNotEnoughBandwidth",
                     "DeviceHubNestedTooDeeply", "DeviceInLegacyHub", "DeviceEnumerating", "DeviceReset"]


class Hub:
    def __init__(self, path: str):
        self.path = path
        h = k32.CreateFileW(path, GENERIC_WRITE, FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
        if h in (None, INVALID_HANDLE):
            raise OSError(ctypes.get_last_error(), f"CreateFile({path})")
        self.h = h

    def close(self):
        k32.CloseHandle(self.h)

    def ioctl(self, code: int, inbuf: bytes, outsize: int) -> bytes:
        size = max(len(inbuf), outsize)
        buf = ctypes.create_string_buffer(inbuf, size)
        ret = wt.DWORD()
        if not k32.DeviceIoControl(self.h, code, buf, len(inbuf), buf, size, ctypes.byref(ret), None):
            raise OSError(ctypes.get_last_error(), f"DeviceIoControl(0x{code:x})")
        return buf.raw[:ret.value]

    def connection_info_ex(self, port: int) -> dict:
        raw = self.ioctl(IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX, struct.pack("<I", port), 35 + 32 * 11)
        dev = usbdesc.parse_device_descriptor(raw[4:22])
        cur_cfg, speed, is_hub, addr, npipes, status = struct.unpack_from("<BBBHII", raw, 22)
        pipes = []
        for i in range(npipes):
            o = 35 + i * 11
            if o + 11 > len(raw):
                break
            ep = usbdesc._parse_endpoint(bytes([7, 5]) + raw[o + 2:o + 7])
            pipes.append(dict(endpoint=ep["bEndpointAddress"], type=ep["transfer_type"],
                              wMaxPacketSize_raw=ep["wMaxPacketSize_raw"], bInterval=ep["bInterval"],
                              ScheduleOffset=struct.unpack_from("<I", raw, o + 7)[0]))
        return dict(ConnectionIndex=port, device_descriptor_cached=dev, CurrentConfigurationValue=cur_cfg,
                    Speed=usbdesc.SPEEDS.get(speed, speed), Speed_raw=speed, DeviceIsHub=bool(is_hub),
                    DeviceAddress=addr, NumberOfOpenPipes=npipes,
                    ConnectionStatus=CONNECTION_STATUS[status] if status < len(CONNECTION_STATUS) else status,
                    open_pipes=pipes)

    def connection_info_v2(self, port: int) -> dict:
        raw = self.ioctl(IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX_V2, struct.pack("<IIII", port, 16, 0x7, 0), 16)
        _, _, protos, flags = struct.unpack_from("<IIII", raw)
        return dict(SupportedUsbProtocols=dict(Usb110=bool(protos & 1), Usb200=bool(protos & 2), Usb300=bool(protos & 4)),
                    DeviceIsOperatingAtSuperSpeedOrHigher=bool(flags & 1),
                    DeviceIsSuperSpeedCapableOrHigher=bool(flags & 2),
                    DeviceIsOperatingAtSuperSpeedPlusOrHigher=bool(flags & 4),
                    DeviceIsSuperSpeedPlusCapableOrHigher=bool(flags & 8))

    def driverkey(self, port: int) -> str:
        raw = self.ioctl(IOCTL_USB_GET_NODE_CONNECTION_DRIVERKEY_NAME, struct.pack("<II", port, 0), 8 + 1024)
        return raw[8:].decode("utf-16-le").split("\0")[0]

    def port_connector(self, port: int) -> dict:
        # sizeof(USB_PORT_CONNECTOR_PROPERTIES) == 20; first call returns ActualLength, second the full struct
        first = self.ioctl(IOCTL_USB_GET_PORT_CONNECTOR_PROPERTIES, struct.pack("<II", port, 0) + b"\0" * 12, 20)
        actual = max(struct.unpack_from("<I", first, 4)[0], 20)
        raw = self.ioctl(IOCTL_USB_GET_PORT_CONNECTOR_PROPERTIES, struct.pack("<II", port, 0) + b"\0" * (actual - 8),
                         actual)
        _, _, props, cidx, cport = struct.unpack_from("<IIIHH", raw)
        name = raw[16:].decode("utf-16-le", errors="replace").split("\0")[0]
        return dict(PortIsUserConnectable=bool(props & 1), PortIsDebugCapable=bool(props & 2),
                    PortHasMultipleCompanions=bool(props & 4), PortConnectorIsTypeC=bool(props & 8),
                    CompanionIndex=cidx, CompanionPortNumber=cport, CompanionHubSymbolicLinkName=name or None)

    def hub_info_ex(self) -> dict:
        raw = self.ioctl(IOCTL_USB_GET_HUB_INFORMATION_EX, b"", 4 + 2 + 71)
        htype, high_port = struct.unpack_from("<IH", raw)
        return dict(HubType={1: "UsbRootHub", 2: "Usb20Hub", 3: "Usb30Hub"}.get(htype, htype), HighestPortNumber=high_port)

    def get_descriptor(self, port: int, dtype: int, index: int = 0, lang: int = 0, length: int = 4096) -> bytes:
        setup = struct.pack("<IBBHHH", port, 0x80, 6, (dtype << 8) | index, lang, length)
        raw = self.ioctl(IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION, setup, 12 + length)
        return raw[12:]


def read_usb_descriptors(hub: Hub, port: int, speed: str | None) -> dict:
    out: dict = {}
    dev_raw = hub.get_descriptor(port, usbdesc.DT_DEVICE, length=18)
    dev = usbdesc.parse_device_descriptor(dev_raw)
    out["device"] = dev
    out["raw"] = {"device": dev_raw.hex()}
    head = hub.get_descriptor(port, usbdesc.DT_CONFIG, 0, length=9)
    total = struct.unpack_from("<H", head, 2)[0]
    cfg_raw = hub.get_descriptor(port, usbdesc.DT_CONFIG, 0, length=total)
    out["raw"]["configuration"] = cfg_raw.hex()
    out["configuration"] = usbdesc.parse_configuration(cfg_raw, speed)
    if dev["bcdUSB_raw"] >= 0x0201:
        try:
            bh = hub.get_descriptor(port, usbdesc.DT_BOS, 0, length=5)
            btotal = struct.unpack_from("<H", bh, 2)[0]
            braw = hub.get_descriptor(port, usbdesc.DT_BOS, 0, length=btotal)
            out["raw"]["bos"] = braw.hex()
            out["bos"] = usbdesc.parse_bos(braw)
        except OSError as e:
            out["bos_error"] = str(e)
    # strings
    strings: dict = {}
    try:
        l0 = hub.get_descriptor(port, usbdesc.DT_STRING, 0, 0, 255)
        langs = [struct.unpack_from("<H", l0, 2 + 2 * i)[0] for i in range((l0[0] - 2) // 2)] if l0 else []
    except OSError as e:
        langs, strings["error_lang"] = [], str(e)
    out["string_languages"] = [f"0x{x:04x}" for x in langs]
    lang = 0x0409 if 0x0409 in langs else (langs[0] if langs else 0x0409)
    idx = {dev["iManufacturer"], dev["iProduct"], dev["iSerialNumber"], out["configuration"]["iConfiguration"]}
    for itf in out["configuration"]["interfaces"]:
        idx.add(itf["iInterface"])
        for cs in itf["class_specific"]:
            for k in ("iTerminal", "iProcessing", "iExtension", "iEncoding"):
                if cs.get(k):
                    idx.add(cs[k])
    for a in out["configuration"]["interface_associations"]:
        idx.add(a["iFunction"])
    for i in sorted(x for x in idx if x):
        try:
            strings[str(i)] = usbdesc.decode_string_descriptor(hub.get_descriptor(port, usbdesc.DT_STRING, i, lang, 255))
        except (OSError, ValueError) as e:
            strings[str(i)] = {"error": str(e)}
    out["strings"] = strings
    out["manufacturer"] = strings.get(str(dev["iManufacturer"])) if dev["iManufacturer"] else None
    out["product"] = strings.get(str(dev["iProduct"])) if dev["iProduct"] else None
    out["serial_number"] = strings.get(str(dev["iSerialNumber"])) if dev["iSerialNumber"] else None
    return out


# ---------------------------------------------------------------- camera discovery
def is_video_function(props: dict) -> bool:
    # UVC function: compatible ID USB\Class_0E&SubClass_01 (VideoControl) or SubClass_03 (video interface
    # collection, reported when the device groups its interfaces with an IAD, e.g. Logitech C922).
    return any(c.upper().startswith(("USB\\CLASS_0E&SUBCLASS_01", "USB\\CLASS_0E&SUBCLASS_03"))
               for c in props.get("CompatibleIds", []))


def ancestry(dn: int) -> list[dict]:
    """Walk from a USB device devnode up to (and including) the PCI host controller."""
    chain = []
    cur = dn
    for _ in range(12):
        p = devnode_props(cur)
        chain.append({k: p.get(k) for k in ("InstanceId", "Service", "Address", "LocationInfo", "LocationPaths",
                                            "BusReportedDeviceDesc", "DeviceDesc", "Driver")})
        if not str(p.get("InstanceId", "")).upper().startswith("USB\\"):
            break
        parent = wt.DWORD()
        if cfg.CM_Get_Parent(ctypes.byref(parent), cur, 0) != CR_SUCCESS:
            break
        cur = parent.value
    return chain


def collect(read_descriptors: bool = True) -> list[dict]:
    ids = list_device_ids("USB")
    cams = []
    for iid in ids:
        dn = locate(iid)
        p = devnode_props(dn)
        if not is_video_function(p):
            continue
        # composite parent: the USB device node (not an MI_xx function).
        if "&MI_" in iid.upper():
            parent = wt.DWORD()
            _cm_check(cfg.CM_Get_Parent(ctypes.byref(parent), dn, 0), "CM_Get_Parent")
            usb_dn = parent.value
        else:
            usb_dn = dn
        usb_props = devnode_props(usb_dn)
        usb_iid = usb_props["InstanceId"]
        cam = dict(usb_device=dict(instance_id=usb_iid, properties=usb_props), video_function=None, functions=[])
        # all functions = children of the USB device
        child = wt.DWORD()
        funcs = []
        if usb_dn != dn and cfg.CM_Get_Child(ctypes.byref(child), usb_dn, 0) == CR_SUCCESS:
            c = child.value
            while True:
                funcs.append(c)
                sib = wt.DWORD()
                if cfg.CM_Get_Sibling(ctypes.byref(sib), c, 0) != CR_SUCCESS:
                    break
                c = sib.value
        else:
            funcs = [dn]
        for f in funcs:
            fp = devnode_props(f)
            fid = fp["InstanceId"]
            ifaces = {}
            for name, g in IFACE_CLASSES.items():
                lst = interface_list(g, fid)
                if lst:
                    ifaces[name] = [dict(symbolic_link=s, friendly_name=interface_prop(s, IFACE_FRIENDLY),
                                         enabled=interface_prop(s, IFACE_ENABLED)) for s in lst]
            entry = dict(instance_id=fid, properties=fp, interfaces=ifaces,
                         device_parameters=registry_values(f"SYSTEM\\CurrentControlSet\\Enum\\{fid}\\Device Parameters"))
            cam["functions"].append(entry)
            if fid.upper() == iid.upper():
                cam["video_function"] = entry
        cam["usb_device"]["interfaces"] = {"GUID_DEVINTERFACE_USB_DEVICE": interface_list(IFACE_CLASSES["GUID_DEVINTERFACE_USB_DEVICE"], usb_iid)}
        cam["usb_device"]["device_parameters"] = registry_values(f"SYSTEM\\CurrentControlSet\\Enum\\{usb_iid}\\Device Parameters")
        cam["port_chain"] = ancestry(usb_dn)
        # hub IOCTLs
        hub_dn = wt.DWORD()
        cfg.CM_Get_Parent(ctypes.byref(hub_dn), usb_dn, 0)
        hub_iid = devnode_props(hub_dn.value).get("InstanceId")
        port = usb_props.get("Address")
        hub_info: dict = dict(hub_instance_id=hub_iid, port=port)
        if read_descriptors and hub_iid and port is not None:
            try:
                paths = interface_list(GUID_DEVINTERFACE_USB_HUB, hub_iid)
                hub_info["hub_interface"] = paths[0] if paths else None
                hub = Hub(paths[0])
                try:
                    hub_info["hub_info_ex"] = _try(hub.hub_info_ex)
                    hub_info["connection_info_ex"] = hub.connection_info_ex(port)
                    hub_info["connection_info_v2"] = _try(hub.connection_info_v2, port)
                    hub_info["port_connector"] = _try(hub.port_connector, port)
                    dk = hub.driverkey(port)
                    hub_info["driverkey_name"] = dk
                    hub_info["driverkey_matches_devnode"] = dk.lower() == str(usb_props.get("Driver", "")).lower()
                    speed = hub_info["connection_info_ex"]["Speed"]
                    if hub_info.get("connection_info_v2", {}).get("DeviceIsOperatingAtSuperSpeedOrHigher"):
                        speed = "super"
                    cam["descriptors"] = read_usb_descriptors(hub, port, speed)
                    cam["descriptors"]["speed"] = speed
                finally:
                    hub.close()
            except OSError as e:
                hub_info["error"] = str(e)
        cam["hub"] = hub_info
        cams.append(cam)
    return cams


def _try(fn, *a):
    try:
        return fn(*a)
    except OSError as e:
        return {"error": str(e)}


# ---------------------------------------------------------------- usbflags
def usbflags(vid: str, pid: str, bcd: str) -> dict:
    base = "SYSTEM\\CurrentControlSet\\Control\\UsbFlags"
    top = registry_values(base)
    name = f"IgnoreHWSerNum{vid.lower()}{pid.lower()}"
    return dict(global_IgnoreHWSerNum_for_vidpid={k: v for k, v in top.items() if k.lower() == name.lower()},
                global_IgnoreHWSerNum_count=sum(1 for k in top if k.lower().startswith("ignorehwsernum")),
                device_key=f"HKLM\\{base}\\{vid.upper()}{pid.upper()}{bcd.upper()}",
                device_key_values=registry_values(f"{base}\\{vid.upper()}{pid.upper()}{bcd.upper()}"))


# ---------------------------------------------------------------- flat identity (for diffs)
def instance_suffix(iid: str) -> str:
    return iid.split("\\")[-1]


def serial_used_in_instance_id(iid: str, serial: str | None) -> bool | None:
    if not serial:
        return False
    return instance_suffix(iid).upper() == serial.upper()


def hub_port_chain(chain: list[dict]) -> str:
    """'<root hub instance>:p1.p2.p3' using only USB (non root hub) nodes' port numbers, outermost first."""
    usb = [n for n in reversed(chain) if str(n.get("InstanceId", "")).upper().startswith("USB\\")]
    root = next((n for n in usb if "ROOT_HUB" in n["InstanceId"].upper()), None)
    ports = [str(n.get("Address")) for n in usb if "ROOT_HUB" not in n["InstanceId"].upper()]
    return f"{root['InstanceId'] if root else '?'}:{'.'.join(ports)}"


def uuid_version(s: str | None) -> dict | None:
    if not s:
        return None
    u = uuid.UUID(s.strip("{}"))
    out = dict(version=u.version)
    if u.version == 1:
        t = _dt.datetime(1582, 10, 15, tzinfo=_dt.timezone.utc) + _dt.timedelta(microseconds=u.time // 10)
        out.update(v1_timestamp=t.isoformat(), v1_node=f"{u.node:012x}")
    return out


def flat_identity(cam: dict) -> dict:
    up = cam["usb_device"]["properties"]
    vf = cam["video_function"] or {}
    vfp = vf.get("properties", {})
    d = cam.get("descriptors", {})
    hw = up.get("HardwareIds", [""])[0]
    vid = hw.upper().split("VID_")[1][:4] if "VID_" in hw.upper() else None
    pid = hw.upper().split("PID_")[1][:4] if "PID_" in hw.upper() else None
    ifs = vf.get("interfaces", {})
    # serial: the USB string if it could be read; if iSerialNumber==0 there is none; if the string read failed
    # (e.g. ERROR_GEN_FAILURE while the device is suspended/busy) fall back to the instance-id suffix when Windows
    # used the serial there (a generated suffix always contains '&').
    i_ser = d.get("device", {}).get("iSerialNumber")
    sfx = instance_suffix(cam["usb_device"]["instance_id"])
    if isinstance(d.get("serial_number"), str):
        serial, serial_src = d["serial_number"], "string_descriptor"
    elif i_ser == 0:
        serial, serial_src = None, "iSerialNumber=0"
    elif "&" not in sfx:
        serial, serial_src = sfx, "instance_id_suffix"
    else:
        serial, serial_src = None, "unread" if i_ser else "no_descriptors"
    product = d.get("product") if isinstance(d.get("product"), str) else None
    return {
        "vid": vid.lower() if vid else None, "pid": pid.lower() if pid else None,
        "bcdDevice": d.get("device", {}).get("bcdDevice"),
        "usb_serial": serial, "usb_serial_source": serial_src,
        "usb_manufacturer": d.get("manufacturer") if isinstance(d.get("manufacturer"), str) else None,
        "usb_product": product or up.get("BusReportedDeviceDesc"),
        "composite_instance_id": cam["usb_device"]["instance_id"],
        "video_function_instance_id": vf.get("instance_id"),
        "serial_used_in_instance_id": serial_used_in_instance_id(cam["usb_device"]["instance_id"], serial),
        "container_id": up.get("ContainerId"),
        "location_paths": (up.get("LocationPaths") or [None])[0],
        "location_info": up.get("LocationInfo"),
        "port_number": up.get("Address"),
        "hub_port_chain": hub_port_chain(cam.get("port_chain", [])),
        "container_id_uuid_version": uuid_version(up.get("ContainerId")),
        "usb_device_address": cam.get("hub", {}).get("connection_info_ex", {}).get("DeviceAddress"),
        "friendly_name": vfp.get("FriendlyName") or vfp.get("DeviceDesc"),
        "bus_reported_device_desc": up.get("BusReportedDeviceDesc"),
        "ks_video_camera_symlink": next((x["symbolic_link"] for x in ifs.get("KSCATEGORY_VIDEO_CAMERA", [])), None),
        "ks_capture_symlink": next((x["symbolic_link"] for x in ifs.get("KSCATEGORY_CAPTURE", [])), None),
        "speed": d.get("speed"),
    }


def environment() -> dict:
    return dict(os=platform.platform(), windows_version=platform.version(), python=sys.version.split()[0],
                machine=platform.machine())


def default_out_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "results" / "windows" / socket.gethostname() / "naming"


def descriptors_view(cams: list[dict]) -> list[dict]:
    out = []
    for cam in cams:
        fi = flat_identity(cam)
        d = cam.get("descriptors")
        out.append(dict(
            camera=dict(vid=fi["vid"], pid=fi["pid"], product=fi["usb_product"], manufacturer=fi["usb_manufacturer"],
                        serial=fi["usb_serial"], composite_instance_id=fi["composite_instance_id"],
                        location_paths=fi["location_paths"], friendly_name=fi["friendly_name"]),
            speed=d.get("speed") if d else None,
            device=d.get("device") if d else None,
            string_languages=d.get("string_languages") if d else None,
            strings=d.get("strings") if d else None,
            bos=d.get("bos") if d else None,
            configuration_summary=({k: v for k, v in d["configuration"].items() if k not in ("interfaces", "uvc")}
                                   if d else None),
            uvc=d["configuration"]["uvc"] if d else None,
            interfaces=d["configuration"]["interfaces"] if d else None,
            raw_hex=d.get("raw") if d else None,
            error=cam.get("hub", {}).get("error"),
        ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--no-descriptors", action="store_true")
    a = ap.parse_args()
    out_dir = a.out_dir or default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    started = _dt.datetime.now(_dt.timezone.utc).isoformat()
    cams = collect(read_descriptors=not a.no_descriptors)
    for cam in cams:
        fi = flat_identity(cam)
        cam["flat_identity"] = fi
        if fi["vid"] and fi["pid"]:
            cam["usbflags"] = usbflags(fi["vid"], fi["pid"], fi.get("bcdDevice") or "")
            cam["device_history"] = device_history(fi["vid"], fi["pid"])
    base = dict(platform="windows", hostname=socket.gethostname(), utc_started=started,
                command=" ".join([Path(sys.executable).name] + sys.argv), environment=environment())
    dump = dict(test="naming.win_identity_dump", **base, cameras=cams)
    (out_dir / "identity_dump.json").write_text(json.dumps(dump, indent=1, default=str), encoding="utf-8")
    if a.label:  # keep the full dump that belongs to each labelled snapshot
        (out_dir / "dumps").mkdir(exist_ok=True)
        (out_dir / "dumps" / f"identity_dump_{a.label}.json").write_text(json.dumps(dump, indent=1, default=str),
                                                                       encoding="utf-8")
    if not a.no_descriptors:
        desc = dict(test="naming.descriptors", **base,
                    schema="see research/usb_cameras/naming/README.md#descriptorsjson-schema",
                    cameras=descriptors_view(cams))
        (out_dir / "descriptors.json").write_text(json.dumps(desc, indent=1, default=str), encoding="utf-8")
    if a.label:
        snap_dir = out_dir / "snapshots"
        snap_dir.mkdir(exist_ok=True)
        import win_api_names  # stdlib-only part: MF + DirectShow enumeration (no stream is opened)
        api = win_api_names.api_identity_fields(cams)
        for c in cams:
            c["flat_identity"].update(api.get(c["usb_device"]["instance_id"], {}))
            try:
                from camera_identity import windows_key_for_flat  # scheme from naming/camera_identity.py
                c["flat_identity"]["camera_key"] = windows_key_for_flat(c["flat_identity"], [x["flat_identity"] for x in cams])
            except ImportError:
                pass
        snap = dict(test="naming.snapshot", label=a.label, **base, cameras=[c["flat_identity"] for c in cams])
        (snap_dir / f"{a.label}.json").write_text(json.dumps(snap, indent=1), encoding="utf-8")
    for cam in cams:
        fi = cam["flat_identity"]
        print(f"{fi['vid']}:{fi['pid']} {fi['usb_product']!r} serial={fi['usb_serial']!r} "
              f"inst={fi['composite_instance_id']} loc={fi['location_paths']} speed={fi['speed']}")
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
