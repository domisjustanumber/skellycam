# /// script
# requires-python = ">=3.10"
# ///
"""Read-only Windows USB topology probe for the 2026-11-06 bandwidth-domain plan (topic topology_windows).

Stdlib + ctypes only. Sends NO request to any USB device: no GET_DESCRIPTOR, no camera open. It uses only
  * CfgMgr32 property reads (present and phantom devnodes),
  * hub query IOCTLs answered from hub-driver state: GET_NODE_INFORMATION(258), GET_NODE_CONNECTION_NAME(261),
    GET_NODE_CONNECTION_DRIVERKEY_NAME(264), GET_NODE_CONNECTION_ATTRIBUTES(272),
    GET_NODE_CONNECTION_INFORMATION_EX(274), GET_HUB_CAPABILITIES_EX(276), GET_HUB_INFORMATION_EX(277),
    GET_PORT_CONNECTOR_PROPERTIES(278), GET_NODE_CONNECTION_INFORMATION_EX_V2(279),
  * host-controller query IOCTLs: GET_ROOT_HUB_NAME, GET_HCD_DRIVERKEY_NAME, USB_USER_REQUEST with ONLY the
    always-enabled read codes 1 (controller info), 2 (driver key), 5 (bandwidth info), 6 (bus statistics),
    7 (root hub name), 8 (driver version). Never 0x1xxxxxxx / 0x2xxxxxxx (send packet, raw reset port ...),
    never CYCLE_PORT(273), RESET_HUB(275) or DIAG(262/263).
  * GetSystemFirmwareTable('ACPI') enumeration (read-only) to test whether ACPI tables are readable non-admin.

Usage: python win_topology_probe.py OUT.json
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import datetime as _dt
import json
import platform
import struct
import sys
import time

cfg = ctypes.WinDLL("cfgmgr32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
ole32 = ctypes.OleDLL("ole32")


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def s(cls, s: str) -> "GUID":
        g = cls()
        ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
        return g

    def __str__(self):
        b = bytes(self.Data4)
        return "{%08x-%04x-%04x-%s-%s}" % (self.Data1, self.Data2, self.Data3, b[:2].hex(), b[2:].hex())


class DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wt.ULONG)]


def K(fmt: str, pid: int) -> DEVPROPKEY:
    return DEVPROPKEY(GUID.s(fmt), pid)


D = "{a45c254e-df1c-4efd-8020-67d146a850e0}"
B = "{540b947e-8b40-45bc-a8a2-6a0b894cbda2}"
R = "{4340a6c5-93fa-4706-972c-7b648008a5a7}"
KEYS = {
    "InstanceId": K("{78c34fc8-104a-4aca-9ea4-524d52996e57}", 256),
    "DeviceDesc": K(D, 2), "Service": K(D, 6), "Class": K(D, 9), "Driver": K(D, 11), "Manufacturer": K(D, 13),
    "FriendlyName": K(D, 14), "LocationInfo": K(D, 15), "Capabilities": K(D, 17), "BusNumber": K(D, 23),
    "EnumeratorName": K(D, 24), "Address": K(D, 30), "RemovalPolicy": K(D, 33), "LocationPaths": K(D, 37),
    "BusReportedDeviceDesc": K(B, 4), "IsPresent": K(B, 5), "PhysicalDeviceLocation": K(B, 9),
    "ContainerId": K("{8c7ed206-3f8a-4827-b3ab-ae9e1faefc6c}", 2),
    "Parent": K(R, 8), "Children": K(R, 9),
}
DEVPROP_TYPE_STRING, DEVPROP_TYPE_STRING_LIST, DEVPROP_TYPE_UINT32, DEVPROP_TYPE_GUID = 0x12, 0x2012, 0x7, 0xD
DEVPROP_TYPE_BINARY, DEVPROP_TYPE_BOOLEAN = 0x1003, 0x11
CM_LOCATE_DEVNODE_NORMAL, CM_LOCATE_DEVNODE_PHANTOM = 0, 1
CM_GETIDLIST_FILTER_ENUMERATOR = 1
CM_GET_DEVICE_INTERFACE_LIST_PRESENT = 0

GUIDS = {
    "USB_HUB": "{f18a0e88-c30c-11d0-8815-00a0c906bed8}",
    "USB_HOST_CONTROLLER": "{3abf6f2d-71c4-462a-8a92-1e6861e6af27}",
    "USB_DEVICE": "{a5dcbf10-6530-11d2-901f-00c04fb951ed}",
    "KSCATEGORY_VIDEO_CAMERA": "{e5323777-f976-4f5b-9b55-b94699c46e44}",   # MF symbolic links
    "KSCATEGORY_VIDEO": "{6994ad05-93ef-11d0-a3cc-00a0c9223196}",          # DirectShow device paths
    "KSCATEGORY_CAPTURE": "{65e8773d-8f56-11d0-a3b9-00a0c9223196}",
}


def _decode(ptype: int, raw: bytes):
    if ptype == DEVPROP_TYPE_STRING:
        return raw.decode("utf-16-le").rstrip("\0")
    if ptype == DEVPROP_TYPE_STRING_LIST:
        return [s for s in raw.decode("utf-16-le").split("\0") if s]
    if ptype == DEVPROP_TYPE_UINT32:
        return struct.unpack("<I", raw[:4])[0]
    if ptype == DEVPROP_TYPE_BOOLEAN:
        return raw[:1] != b"\0"
    if ptype == DEVPROP_TYPE_GUID:
        g = GUID.from_buffer_copy(raw[:16])
        return str(g)
    return {"type": hex(ptype), "hex": raw.hex()}


def prop(dn: int, name: str):
    key = KEYS[name]
    pt, sz = wt.ULONG(), wt.ULONG(0)
    cfg.CM_Get_DevNode_PropertyW(dn, ctypes.byref(key), ctypes.byref(pt), None, ctypes.byref(sz), 0)
    if not sz.value:
        return None
    buf = ctypes.create_string_buffer(sz.value)
    if cfg.CM_Get_DevNode_PropertyW(dn, ctypes.byref(key), ctypes.byref(pt), buf, ctypes.byref(sz), 0) != 0:
        return None
    return _decode(pt.value, buf.raw[:sz.value])


def props(dn: int, names=None) -> dict:
    return {n: v for n in (names or KEYS) if (v := prop(dn, n)) is not None}


def locate(iid: str, phantom=False) -> int | None:
    dn = wt.DWORD()
    r = cfg.CM_Locate_DevNodeW(ctypes.byref(dn), iid, CM_LOCATE_DEVNODE_PHANTOM if phantom else 0)
    return dn.value if r == 0 else None


def parent(dn: int) -> int | None:
    p = wt.DWORD()
    return p.value if cfg.CM_Get_Parent(ctypes.byref(p), dn, 0) == 0 else None


def id_list(enumerator: str) -> list[str]:
    n = wt.ULONG()
    cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(n), enumerator, CM_GETIDLIST_FILTER_ENUMERATOR)
    buf = ctypes.create_unicode_buffer(n.value)
    cfg.CM_Get_Device_ID_ListW(enumerator, buf, n.value, CM_GETIDLIST_FILTER_ENUMERATOR)
    return [s for s in ctypes.wstring_at(buf, n.value).split("\0") if s]


def iface_list(guid: str, iid: str | None = None) -> list[str]:
    g, n = GUID.s(guid), wt.ULONG()
    cfg.CM_Get_Device_Interface_List_SizeW(ctypes.byref(n), ctypes.byref(g), iid, 0)
    buf = ctypes.create_unicode_buffer(max(n.value, 1))
    if cfg.CM_Get_Device_Interface_ListW(ctypes.byref(g), iid, buf, n.value, 0) != 0:
        return []
    return [s for s in ctypes.wstring_at(buf, n.value).split("\0") if s]


def iface_instance(path: str) -> str | None:
    key = KEYS["InstanceId"]
    pt, sz = wt.ULONG(), wt.ULONG(0)
    cfg.CM_Get_Device_Interface_PropertyW(path, ctypes.byref(key), ctypes.byref(pt), None, ctypes.byref(sz), 0)
    buf = ctypes.create_string_buffer(max(sz.value, 2))
    if cfg.CM_Get_Device_Interface_PropertyW(path, ctypes.byref(key), ctypes.byref(pt), buf, ctypes.byref(sz), 0):
        return None
    return _decode(pt.value, buf.raw[:sz.value])


def decode_pld(h: str | None) -> dict | None:
    """ACPI 6.5 section 6.1.8 _PLD buffer (revision 2, 20 bytes)."""
    if not h:
        return None
    b = bytes.fromhex(h)
    if len(b) < 16:
        return {"raw": h}
    v = int.from_bytes(b, "little")

    def bits(lo, n):
        return (v >> lo) & ((1 << n) - 1)
    panel = ["top", "bottom", "left", "right", "front", "back", "unknown"]
    out = {"raw": h, "revision": bits(0, 7), "ignore_color": bool(bits(7, 1)), "color_rgb": f"#{bits(8, 24):06x}",
           "width_mm": bits(32, 16), "height_mm": bits(48, 16), "user_visible": bool(bits(64, 1)), "dock": bool(bits(65, 1)),
           "lid": bool(bits(66, 1)), "panel": panel[bits(67, 3)] if bits(67, 3) < 7 else bits(67, 3),
           "vertical_position": ["upper", "center", "lower", "?"][bits(70, 2)],
           "horizontal_position": ["left", "center", "right", "?"][bits(72, 2)],
           "shape": bits(74, 4), "group_orientation": bits(78, 1), "group_token": bits(79, 8), "group_position": bits(87, 8),
           "bay": bool(bits(95, 1)), "ejectable": bool(bits(96, 1)), "cabinet": bits(98, 8), "card_cage": bits(106, 8),
           "reference": bits(114, 1), "rotation": bits(115, 4), "order": bits(119, 5)}
    if len(b) >= 20:
        out["vertical_offset"], out["horizontal_offset"] = bits(128, 16), bits(144, 16)
    return out


# ------------------------------------------------------------------ IOCTL plumbing
GENERIC_WRITE, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING = 0x40000000, 1, 2, 3
INVALID = ctypes.c_void_p(-1).value
k32.CreateFileW.restype = wt.HANDLE
k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE]
k32.DeviceIoControl.argtypes = [wt.HANDLE, wt.DWORD, wt.LPVOID, wt.DWORD, wt.LPVOID, wt.DWORD, ctypes.POINTER(wt.DWORD), wt.LPVOID]
k32.CloseHandle.argtypes = [wt.HANDLE]


def ctl(fn: int) -> int:
    return (0x22 << 16) | (fn << 2)


ALLOWED = {258, 261, 264, 265, 270, 272, 274, 276, 277, 278, 279}   # read-only query codes, nothing else


def ioctl(h, fn: int, inbuf: bytes, outsize: int):
    assert fn in ALLOWED, fn
    size = max(len(inbuf), outsize)
    buf = ctypes.create_string_buffer(inbuf, size)
    ret = wt.DWORD()
    if not k32.DeviceIoControl(h, ctl(fn), buf, len(inbuf), buf, size, ctypes.byref(ret), None):
        return None, ctypes.get_last_error()
    return buf.raw[:ret.value], 0


def open_path(path: str):
    h = k32.CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
    return (None, ctypes.get_last_error()) if h in (None, INVALID) else (h, 0)


CONN = ["NoDeviceConnected", "DeviceConnected", "DeviceFailedEnumeration", "DeviceGeneralFailure", "DeviceCausedOvercurrent",
        "DeviceNotEnoughPower", "DeviceNotEnoughBandwidth", "DeviceHubNestedTooDeeply", "DeviceInLegacyHub",
        "DeviceEnumerating", "DeviceReset"]
SPEED = {0: "low", 1: "full", 2: "high", 3: "super"}


def usb_name(h, fn: int, inbuf: bytes, off: int) -> str | None:
    raw, err = ioctl(h, fn, inbuf + bytes(1024), len(inbuf) + 1024)
    if raw is None or len(raw) <= off:
        return None
    return raw[off:].decode("utf-16-le", "replace").split("\0")[0] or None


def hub_ports(h, nports: int) -> list[dict]:
    ports = []
    for p in range(1, nports + 1):
        e: dict = {"port": p}
        raw, err = ioctl(h, 274, struct.pack("<I", p) + bytes(31 + 11 * 32), 35 + 11 * 32)
        if raw is not None and len(raw) >= 35:
            vid, pid = struct.unpack_from("<HH", raw, 12)
            cur_cfg, spd, is_hub = raw[22], raw[23], raw[24]
            addr, npipes, st = struct.unpack_from("<HII", raw, 25)
            e.update(status=CONN[st] if st < len(CONN) else st, legacy_speed=SPEED.get(spd, spd), device_is_hub=bool(is_hub))
            if st != 0:
                e.update(vid=f"{vid:04x}", pid=f"{pid:04x}", bcdUSB=f"{struct.unpack_from('<H', raw, 6)[0]:04x}",
                         address=addr, open_pipes=[])
                for k in range(npipes):
                    o = 35 + 11 * k
                    if o + 11 > len(raw):
                        break
                    _l, _t, ea, attr, wmps, bint, sched = struct.unpack_from("<BBBBHBI", raw, o)
                    e["open_pipes"].append({"ep": f"0x{ea:02x}", "type": ["control", "iso", "bulk", "interrupt"][attr & 3],
                                            "wMaxPacketSize": f"0x{wmps:04x}",
                                            "bytes_per_uframe_hs": (wmps & 0x7FF) * (((wmps >> 11) & 3) + 1), "bInterval": bint})
        else:
            e["conn_info_error"] = err
        raw, err = ioctl(h, 279, struct.pack("<IIII", p, 16, 0x7, 0), 16)
        if raw and len(raw) >= 16:
            protos, flags = struct.unpack_from("<II", raw, 8)
            e["port_protocols"] = [n for b, n in ((1, "usb1.1"), (2, "usb2.0"), (4, "usb3")) if protos & b]
            e["v2_flags"] = {"op_ss": bool(flags & 1), "ss_capable": bool(flags & 2), "op_ssp": bool(flags & 4), "ssp_capable": bool(flags & 8)}
        else:
            e["v2_error"] = err
        first, err = ioctl(h, 278, struct.pack("<II", p, 0) + bytes(12), 20)
        if first:
            actual = max(struct.unpack_from("<I", first, 4)[0], 20)
            raw, err = ioctl(h, 278, struct.pack("<II", p, 0) + bytes(actual - 8), actual)
            if raw:
                _, _, pr, cidx, cport = struct.unpack_from("<IIIHH", raw)
                e["connector"] = {"user_connectable": bool(pr & 1), "debug_capable": bool(pr & 2), "multiple_companions": bool(pr & 4),
                                  "type_c": bool(pr & 8), "companion_index": cidx, "companion_port": cport,
                                  "companion_hub": raw[16:].decode("utf-16-le", "replace").split("\0")[0] or None}
        else:
            e["connector_error"] = err
        raw, err = ioctl(h, 272, struct.pack("<III", p, 0, 0), 12)
        if raw and len(raw) >= 12:
            _, st, attr = struct.unpack_from("<III", raw)
            e["port_attributes"] = hex(attr)
        else:
            e["port_attributes_error"] = err
        if e.get("status") not in (None, "NoDeviceConnected"):
            e["driver_key"] = usb_name(h, 264, struct.pack("<II", p, 0), 8)
            if e.get("device_is_hub"):
                e["child_hub_name"] = usb_name(h, 261, struct.pack("<II", p, 0), 8)
        ports.append(e)
    return ports


def hubs() -> list[dict]:
    out = []
    for path in iface_list(GUIDS["USB_HUB"]):
        iid = iface_instance(path)
        dn = locate(iid) if iid else None
        hub: dict = {"interface": path, "instance_id": iid}
        if dn:
            hub["props"] = props(dn, ["DeviceDesc", "BusReportedDeviceDesc", "LocationInfo", "LocationPaths", "Address",
                                      "PhysicalDeviceLocation", "Service", "Driver"])
            chain, cur = [], dn
            for _ in range(12):
                cur = parent(cur)
                if cur is None:
                    break
                pid = prop(cur, "InstanceId")
                chain.append(pid)
                if str(pid).upper().startswith(("PCI\\", "ACPI\\", "HTREE")):
                    break
            hub["parent_chain"] = chain
        h, err = open_path(path)
        if h is None:
            hub["open_error"] = err
            out.append(hub)
            continue
        try:
            raw, err = ioctl(h, 258, bytes(76), 76)
            if raw:
                hub["node_info"] = {"NodeType": raw[0], "bNumberOfPorts": raw[6],
                                    "wHubCharacteristics": hex(struct.unpack_from("<H", raw, 7)[0]),
                                    "HubIsBusPowered": bool(raw[75]) if len(raw) > 75 else None}
            raw, err = ioctl(h, 277, bytes(80), 80)
            if raw:
                ht, hp = struct.unpack_from("<IH", raw)
                hub["hub_info_ex"] = {"HubType": {1: "UsbRootHub", 2: "Usb20Hub", 3: "Usb30Hub"}.get(ht, ht), "HighestPortNumber": hp}
            else:
                hub["hub_info_ex_error"] = err
            raw, err = ioctl(h, 276, bytes(4), 4)
            if raw:
                f = struct.unpack_from("<I", raw)[0]
                hub["hub_caps_ex"] = {n: bool(f & (1 << i)) for i, n in enumerate(
                    ["HubIsHighSpeedCapable", "HubIsHighSpeed", "HubIsMultiTtCapable", "HubIsMultiTt", "HubIsRoot",
                     "HubIsArmedWakeOnConnect", "HubIsBusPowered"])}
            else:
                hub["hub_caps_ex_error"] = err
            n = (hub.get("hub_info_ex") or {}).get("HighestPortNumber") or (hub.get("node_info") or {}).get("bNumberOfPorts") or 0
            hub["ports"] = hub_ports(h, n)
        finally:
            k32.CloseHandle(h)
        out.append(hub)
    return out


def user_request(h, code: int, payload_len: int) -> dict:
    assert code in (1, 2, 5, 6, 7, 8)
    hdr = struct.pack("<IIII", code, 0, 16 + payload_len, 0)
    raw, err = ioctl(h, 270, hdr + bytes(payload_len), 16 + payload_len)
    if raw is None:
        return {"win32_error": err}
    req, status, rlen, alen = struct.unpack_from("<IIII", raw)
    st = ["UsbUserSuccess", "UsbUserNotSupported", "UsbUserInvalidRequestCode", "UsbUserFeatureDisabled",
          "UsbUserInvalidHeaderParameter", "UsbUserInvalidParameter", "UsbUserMiniportError", "UsbUserBufferTooSmall",
          "UsbUserErrorNotMapped", "UsbUserDeviceNotStarted", "UsbUserNoDeviceConnected"]
    return {"status": st[status] if status < len(st) else status, "actual_len": alen, "payload": raw[16:]}


def controllers() -> list[dict]:
    out = []
    for path in iface_list(GUIDS["USB_HOST_CONTROLLER"]):
        iid = iface_instance(path)
        dn = locate(iid) if iid else None
        c: dict = {"interface": path, "instance_id": iid}
        if dn:
            c["props"] = props(dn, ["DeviceDesc", "FriendlyName", "Manufacturer", "LocationInfo", "LocationPaths", "Service",
                                    "BusReportedDeviceDesc", "PhysicalDeviceLocation"])
            pp = parent(dn)
            c["parent"] = prop(pp, "InstanceId") if pp else None
            c["parent_desc"] = prop(pp, "DeviceDesc") if pp else None
        h, err = open_path(path)
        if h is None:
            c["open_error"] = err
            out.append(c)
            continue
        try:
            c["root_hub_name"] = usb_name(h, 258, b"", 4)      # IOCTL_USB_GET_ROOT_HUB_NAME (HCD fn 258)
            c["hcd_driverkey"] = usb_name(h, 265, b"", 4)
            r = user_request(h, 1, 24)
            if r.get("payload") is not None and r["status"] == "UsbUserSuccess":
                ven, dev, rev, nports, flavor, feat = struct.unpack_from("<IIIIII", r["payload"])
                c["controller_info_0"] = {"PciVendorId": f"{ven:04x}", "PciDeviceId": f"{dev:04x}", "PciRevision": rev,
                                          "NumberOfRootPorts": nports, "ControllerFlavor": flavor, "HcFeatureFlags": hex(feat)}
            else:
                c["controller_info_0"] = {k: v for k, v in r.items() if k != "payload"}
            r = user_request(h, 5, 44)
            entry = {k: v for k, v in r.items() if k != "payload"}
            if r.get("payload") is not None and r.get("status") == "UsbUserSuccess":
                names = ["DeviceCount", "TotalBusBandwidth", "Total32secBandwidth", "AllocedBulkAndControl", "AllocedIso",
                         "AllocedInterrupt_1ms", "AllocedInterrupt_2ms", "AllocedInterrupt_4ms", "AllocedInterrupt_8ms",
                         "AllocedInterrupt_16ms", "AllocedInterrupt_32ms"]
                entry.update(dict(zip(names, struct.unpack_from("<11I", r["payload"]))))
            c["bandwidth_info"] = entry
            r = user_request(h, 6, 64)
            entry = {k: v for k, v in r.items() if k != "payload"}
            if r.get("payload") is not None and r.get("status") == "UsbUserSuccess":
                p = r["payload"]
                dc, = struct.unpack_from("<I", p, 0)
                t, = struct.unpack_from("<q", p, 4)
                vals = struct.unpack_from("<10I", p, 12)
                entry.update(DeviceCount=dc, CurrentSystemTime=t, **dict(zip(
                    ["CurrentUsbFrame", "BulkBytes", "IsoBytes", "InterruptBytes", "ControlDataBytes", "PciInterruptCount",
                     "HardResetCount", "WorkerSignalCount", "CommonBufferBytes", "WorkerIdleTimeMs"], vals)))
            c["bus_statistics_0"] = entry
            r = user_request(h, 8, 16)
            entry = {k: v for k, v in r.items() if k != "payload"}
            if r.get("payload") is not None and r.get("status") == "UsbUserSuccess":
                dtc, usbdi, uu = struct.unpack_from("<III", r["payload"])
                entry.update(DriverTrackingCode=dtc, USBDI_Version=hex(usbdi), USBUSER_Version=uu)
            c["driver_version"] = entry
        finally:
            k32.CloseHandle(h)
        out.append(c)
    return out


def usb_devnodes(phantom: bool) -> list[dict]:
    """All USB-enumerated devnodes (present, or all incl. phantom) with location + _PLD."""
    out = []
    for iid in id_list("USB"):
        dn = locate(iid, phantom=True)
        if dn is None:
            continue
        pr = props(dn, ["DeviceDesc", "BusReportedDeviceDesc", "LocationInfo", "LocationPaths", "Address", "IsPresent",
                        "PhysicalDeviceLocation", "Service", "Class"])
        if not phantom and not pr.get("IsPresent"):
            continue
        if "&MI_" in iid.upper():
            continue
        pld = pr.get("PhysicalDeviceLocation")
        if isinstance(pld, dict):
            pr["PhysicalDeviceLocation"] = decode_pld(pld.get("hex"))
        out.append({"instance_id": iid, **pr})
    return out


def camera_paths(exclude_vidpid: set[str]) -> list[dict]:
    """MF symbolic link (KSCATEGORY_VIDEO_CAMERA) and DirectShow path (KSCATEGORY_VIDEO) -> function -> USB device -> hub/port.
    Pure CfgMgr: nothing is opened."""
    out = []
    for cat in ("KSCATEGORY_VIDEO_CAMERA", "KSCATEGORY_VIDEO"):
        for path in iface_list(GUIDS[cat]):
            fid = iface_instance(path)
            if not fid or not fid.upper().startswith("USB\\"):
                out.append({"category": cat, "path": path, "function_instance": fid, "note": "not USB-enumerated"})
                continue
            fdn = locate(fid)
            udn = parent(fdn) if "&MI_" in fid.upper() else fdn
            hdn = parent(udn) if udn else None
            up = props(udn, ["InstanceId", "LocationPaths", "LocationInfo", "Address", "BusReportedDeviceDesc", "PhysicalDeviceLocation"])
            pld = up.get("PhysicalDeviceLocation")
            if isinstance(pld, dict):
                up["PhysicalDeviceLocation"] = decode_pld(pld.get("hex"))
            out.append({"category": cat, "path": path, "function_instance": fid, "usb_device": up,
                        "hub_instance": prop(hdn, "InstanceId") if hdn else None})
    return out


def acpi_tables() -> dict:
    fn = k32.EnumSystemFirmwareTables
    fn.argtypes = [wt.DWORD, ctypes.c_void_p, wt.DWORD]
    sig = struct.unpack(">I", b"ACPI")[0]
    n = fn(sig, None, 0)
    if not n:
        return {"error": ctypes.get_last_error()}
    buf = ctypes.create_string_buffer(n)
    fn(sig, buf, n)
    ids = [buf.raw[i:i + 4].decode("ascii", "replace") for i in range(0, n, 4)]
    g = k32.GetSystemFirmwareTable
    g.argtypes = [wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD]
    sizes = {}
    pld_hits = 0
    for t in sorted(set(ids)):
        tid = struct.unpack("<I", t.encode("ascii", "replace"))[0]
        sz = g(sig, tid, None, 0)
        sizes[t] = sz
        if t in ("DSDT", "SSDT") and sz:
            b = ctypes.create_string_buffer(sz)
            g(sig, tid, b, sz)
            pld_hits += b.raw.count(b"_PLD")
    return {"table_ids": ids, "sizes_first_instance": sizes, "count_of__PLD_names_in_DSDT_and_first_SSDT": pld_hits,
            "note": "GetSystemFirmwareTable returns only the FIRST table of a given signature; other SSDTs are not reachable this way"}


def main() -> int:
    out_path = sys.argv[1]
    t0 = time.perf_counter()
    excl = {"1532:0e05"}
    doc = {"test": "topology_windows_probe", "utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
           "os": platform.platform(), "python": platform.python_version(), "command": " ".join(sys.argv),
           "elevated": bool(ctypes.windll.shell32.IsUserAnAdmin())}
    tc = time.perf_counter()
    doc["controllers"] = controllers()
    doc["t_controllers_s"] = round(time.perf_counter() - tc, 4)
    th = time.perf_counter()
    doc["hubs"] = hubs()
    doc["t_hubs_s"] = round(time.perf_counter() - th, 4)
    doc["camera_paths"] = camera_paths(excl)
    doc["usb_devnodes_present"] = usb_devnodes(phantom=False)
    doc["usb_devnodes_all_incl_phantom"] = usb_devnodes(phantom=True)
    doc["acpi"] = acpi_tables()
    doc["t_total_s"] = round(time.perf_counter() - t0, 4)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, default=str)
    print("wrote", out_path, "total", doc["t_total_s"], "s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
