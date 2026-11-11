# /// script
# requires-python = ">=3.10"
# ///
"""Read-only Windows PnP / USB hub helpers for the Windows suite (stdlib + ctypes only, no admin).

Shared by suitectx.py (camera discovery), helpers/win_topology.py (topology collector) and the enumeration tests
(W-ENV, W-ID, W-FMT, W-CTRL-LIST). Code borrowed from:
  * results/agent_reports/plan_20261106/topology_windows_run/win_topology_probe.py (CfgMgr reads, hub IOCTLs, _PLD)
  * naming/win_identity_dump.py (property table incl. LastArrivalDate, DevNode status, descriptor reads)
  * bandwidth/win_usb_topology.py (connection info / open pipes)

Safety (plan section 6.1): everything here is a READ.
  * CfgMgr32 property reads (present and phantom devnodes); winreg reads with KEY_READ only (no write API is used
    anywhere in this module).
  * Hub IOCTLs answered from hub-driver state, allow-listed in ``SAFE_IOCTLS``: GET_NODE_INFORMATION(258),
    GET_NODE_CONNECTION_NAME(261), GET_NODE_CONNECTION_DRIVERKEY_NAME(264), GET_HCD_DRIVERKEY_NAME(265),
    USB_USER_REQUEST(270, only read codes 1/2/5/6/7/8), GET_NODE_CONNECTION_ATTRIBUTES(272),
    GET_NODE_CONNECTION_INFORMATION_EX(274), GET_HUB_CAPABILITIES_EX(276), GET_HUB_INFORMATION_EX(277),
    GET_PORT_CONNECTOR_PROPERTIES(278), GET_NODE_CONNECTION_INFORMATION_EX_V2(279).
  * ``get_descriptor()`` (IOCTL 260, GET_DESCRIPTOR on EP0 of the device) is the ONLY call that reaches a device.
    It is a standard read request, never opens a stream, and is used only by the descriptor reader that the tests
    run in a child process under camlock with a timeout. CYCLE_PORT(273), RESET_HUB(275), DIAG(262/263) and every
    USBUSER_OP_* code are never sent.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import datetime as _dt
import struct
import sys
import uuid

if sys.platform != "win32":  # importable on other OSes for linting, but useless there
    raise ImportError("winpnp is Windows-only")

cfg = ctypes.WinDLL("cfgmgr32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

CR_SUCCESS, CR_BUFFER_SMALL, CR_NO_SUCH_VALUE = 0, 0x1A, 0x25
CM_LOCATE_DEVNODE_NORMAL, CM_LOCATE_DEVNODE_PHANTOM = 0, 1
CM_GETIDLIST_FILTER_ENUMERATOR, CM_GETIDLIST_FILTER_PRESENT = 0x1, 0x100
CM_GET_DEVICE_INTERFACE_LIST_PRESENT, CM_GET_DEVICE_INTERFACE_LIST_ALL_DEVICES = 0, 1


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_str(cls, s: str) -> "GUID":
        g = cls()
        ctypes.memmove(ctypes.byref(g), uuid.UUID(s.strip("{}")).bytes_le, 16)
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
PROPS: dict[str, DEVPROPKEY] = {
    "DeviceDesc": _key(_DEV, 2), "HardwareIds": _key(_DEV, 3), "CompatibleIds": _key(_DEV, 4),
    "Service": _key(_DEV, 6), "Class": _key(_DEV, 9), "ClassGuid": _key(_DEV, 10), "Driver": _key(_DEV, 11),
    "Manufacturer": _key(_DEV, 13), "FriendlyName": _key(_DEV, 14), "LocationInfo": _key(_DEV, 15),
    "PDOName": _key(_DEV, 16), "Capabilities": _key(_DEV, 17), "UINumber": _key(_DEV, 18),
    "BusNumber": _key(_DEV, 23), "EnumeratorName": _key(_DEV, 24), "Address": _key(_DEV, 30),
    "RemovalPolicy": _key(_DEV, 33), "LocationPaths": _key(_DEV, 37),
    "InstanceId": _key("78c34fc8-104a-4aca-9ea4-524d52996e57", 256),
    "ContainerId": _key("8c7ed206-3f8a-4827-b3ab-ae9e1faefc6c", 2),
    "BusReportedDeviceDesc": _key(_BUS, 4), "IsPresent": _key(_BUS, 5), "PhysicalDeviceLocation": _key(_BUS, 9),
    "Parent": _key(_REL, 8), "Children": _key(_REL, 9), "Siblings": _key(_REL, 10),
    "DriverDate": _key(_DRV, 2), "DriverVersion": _key(_DRV, 3), "DriverInfPath": _key(_DRV, 5),
    "DriverProvider": _key(_DRV, 9),
    "InstallDate": _key(_DATES, 100), "FirstInstallDate": _key(_DATES, 101),
    "LastArrivalDate": _key(_DATES, 102), "LastRemovalDate": _key(_DATES, 103),
}
IFACE_KEYS = {
    "InstanceId": PROPS["InstanceId"],
    "FriendlyName": _key("026e516e-b814-414b-83cd-856d6fef4822", 2),
    "Enabled": _key("026e516e-b814-414b-83cd-856d6fef4822", 3),
}
GUIDS = {
    "USB_HUB": "{f18a0e88-c30c-11d0-8815-00a0c906bed8}",
    "USB_HOST_CONTROLLER": "{3abf6f2d-71c4-462a-8a92-1e6861e6af27}",
    "USB_DEVICE": "{a5dcbf10-6530-11d2-901f-00c04fb951ed}",
    "KSCATEGORY_VIDEO_CAMERA": "{e5323777-f976-4f5b-9b55-b94699c46e44}",   # MF symbolic links
    "KSCATEGORY_CAPTURE": "{65e8773d-8f56-11d0-a3b9-00a0c9223196}",        # DirectShow DevicePath (ksproxy)
    "KSCATEGORY_VIDEO": "{6994ad05-93ef-11d0-a3cc-00a0c9223196}",
    "KSCATEGORY_SENSOR_CAMERA": "{24e552d7-6523-47f7-a647-d3465bf1f5ca}",
}

# cfg.h DN_* flags (DN_NEED_RESTART is an alias of DN_LIAR = 0x100)
DN_FLAGS = {0x1: "DN_ROOT_ENUMERATED", 0x2: "DN_DRIVER_LOADED", 0x4: "DN_ENUM_LOADED", 0x8: "DN_STARTED",
            0x10: "DN_MANUAL", 0x20: "DN_NEED_TO_ENUM", 0x40: "DN_NOT_FIRST_TIME", 0x80: "DN_HARDWARE_ENUM",
            0x100: "DN_NEED_RESTART", 0x200: "DN_HAS_MARK", 0x400: "DN_HAS_PROBLEM", 0x800: "DN_FILTERED",
            0x1000: "DN_MOVED", 0x2000: "DN_DISABLEABLE", 0x4000: "DN_REMOVABLE", 0x8000: "DN_PRIVATE_PROBLEM",
            0x10000: "DN_MF_PARENT", 0x20000: "DN_MF_CHILD", 0x40000: "DN_WILL_BE_REMOVED",
            0x80000: "DN_NOT_FIRST_TIMEE", 0x100000: "DN_STOP_FREE_RES", 0x200000: "DN_REBAL_CANDIDATE",
            0x400000: "DN_BAD_PARTIAL", 0x800000: "DN_NT_ENUMERATOR", 0x1000000: "DN_NT_DRIVER",
            0x2000000: "DN_NEEDS_LOCKING", 0x4000000: "DN_ARM_WAKEUP", 0x8000000: "DN_APM_ENUMERATOR",
            0x10000000: "DN_APM_DRIVER", 0x20000000: "DN_SILENT_INSTALL", 0x40000000: "DN_NO_SHOW_IN_DM",
            0x80000000: "DN_BOOT_LOG_PROB"}
WARN_DN = ("DN_HAS_PROBLEM", "DN_NEED_RESTART", "DN_PRIVATE_PROBLEM", "DN_WILL_BE_REMOVED")


def dn_flag_names(status: int) -> list[str]:
    return [n for b, n in DN_FLAGS.items() if status & b]


# ------------------------------------------------------------------------------------------------ property decode
def _filetime_iso(ft: int) -> str | None:
    if not ft:
        return None
    return (_dt.datetime(1601, 1, 1, tzinfo=_dt.timezone.utc) + _dt.timedelta(microseconds=ft // 10)).isoformat()


def decode_prop(ptype: int, raw: bytes):
    base, is_list, is_array = ptype & 0xFFF, ptype & 0x2000, ptype & 0x1000
    if is_array and base == 0x03:  # DEVPROP_TYPE_BINARY
        return {"hex": raw.hex()}
    if base == 0x12 and is_list:  # STRING_LIST
        return [s for s in raw.decode("utf-16-le", "replace").split("\0") if s]
    if base == 0x12:
        return raw.decode("utf-16-le", "replace").rstrip("\0")
    if base == 0x0D:  # GUID
        return "{" + str(uuid.UUID(bytes_le=raw[:16])) + "}"
    if base == 0x07:  # UINT32
        return struct.unpack("<I", raw[:4])[0]
    if base == 0x05:
        return struct.unpack("<H", raw[:2])[0]
    if base == 0x03:
        return raw[0]
    if base == 0x11:  # BOOLEAN
        return raw[:1] != b"\0"
    if base == 0x10:  # FILETIME
        return _filetime_iso(struct.unpack("<Q", raw[:8])[0])
    return {"devprop_type": f"0x{ptype:x}", "hex": raw.hex()}


def devnode_prop(dn: int, name: str):
    key = PROPS[name]
    ptype, size = wt.ULONG(), wt.ULONG(0)
    cr = cfg.CM_Get_DevNode_PropertyW(dn, ctypes.byref(key), ctypes.byref(ptype), None, ctypes.byref(size), 0)
    if cr != CR_BUFFER_SMALL or not size.value:
        return None
    buf = (ctypes.c_ubyte * size.value)()
    if cfg.CM_Get_DevNode_PropertyW(dn, ctypes.byref(key), ctypes.byref(ptype), buf, ctypes.byref(size), 0):
        return None
    return decode_prop(ptype.value, bytes(buf))


def devnode_status(dn: int) -> dict:
    st, prob = wt.ULONG(), wt.ULONG()
    cr = cfg.CM_Get_DevNode_Status(ctypes.byref(st), ctypes.byref(prob), dn, 0)
    if cr != CR_SUCCESS:
        return {"cr": f"0x{cr:x}", "DevNodeStatus": None, "ProblemCode": None, "flags": [], "warn": []}
    names = dn_flag_names(st.value)
    return {"DevNodeStatus": f"0x{st.value:08x}", "ProblemCode": prob.value, "flags": names,
            "warn": [n for n in names if n in WARN_DN]}


def devnode_props(dn: int, names=None, status: bool = True) -> dict:
    out = {}
    for n in (names or PROPS):
        v = devnode_prop(dn, n)
        if v is not None:
            out[n] = v
    if status:
        out.update(devnode_status(dn))
    return out


def locate(iid: str, phantom: bool = False) -> int | None:
    dn = wt.DWORD()
    r = cfg.CM_Locate_DevNodeW(ctypes.byref(dn), iid, CM_LOCATE_DEVNODE_PHANTOM if phantom else 0)
    return dn.value if r == CR_SUCCESS else None


def parent(dn: int) -> int | None:
    p = wt.DWORD()
    return p.value if cfg.CM_Get_Parent(ctypes.byref(p), dn, 0) == CR_SUCCESS else None


def children(dn: int) -> list[int]:
    out = []
    c = wt.DWORD()
    if cfg.CM_Get_Child(ctypes.byref(c), dn, 0) != CR_SUCCESS:
        return out
    cur = c.value
    for _ in range(64):
        out.append(cur)
        s = wt.DWORD()
        if cfg.CM_Get_Sibling(ctypes.byref(s), cur, 0) != CR_SUCCESS:
            break
        cur = s.value
    return out


def instance_id(dn: int) -> str | None:
    return devnode_prop(dn, "InstanceId")


def id_list(enumerator: str | None = "USB", present_only: bool = True) -> list[str]:
    """Device instance IDs; ``enumerator=None`` lists every device (all enumerators)."""
    n = wt.ULONG()
    flags = (CM_GETIDLIST_FILTER_ENUMERATOR if enumerator else 0) | (CM_GETIDLIST_FILTER_PRESENT if present_only
                                                                      else 0)
    if cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(n), enumerator, flags) != CR_SUCCESS:
        return []
    buf = ctypes.create_unicode_buffer(max(n.value, 1))
    if cfg.CM_Get_Device_ID_ListW(enumerator, buf, n.value, flags) != CR_SUCCESS:
        return []
    return [s for s in ctypes.wstring_at(buf, n.value).split("\0") if s]


def iface_list(guid: str, iid: str | None = None, all_devices: bool = False) -> list[str]:
    g, n = GUID.from_str(guid), wt.ULONG()
    fl = CM_GET_DEVICE_INTERFACE_LIST_ALL_DEVICES if all_devices else CM_GET_DEVICE_INTERFACE_LIST_PRESENT
    if cfg.CM_Get_Device_Interface_List_SizeW(ctypes.byref(n), ctypes.byref(g), iid, fl) != CR_SUCCESS:
        return []
    buf = ctypes.create_unicode_buffer(max(n.value, 1))
    if cfg.CM_Get_Device_Interface_ListW(ctypes.byref(g), iid, buf, n.value, fl) != CR_SUCCESS:
        return []
    return [s for s in ctypes.wstring_at(buf, n.value).split("\0") if s]


def iface_prop(path: str, name: str):
    key = IFACE_KEYS[name]
    ptype, size = wt.ULONG(), wt.ULONG(0)
    cr = cfg.CM_Get_Device_Interface_PropertyW(path, ctypes.byref(key), ctypes.byref(ptype), None,
                                               ctypes.byref(size), 0)
    if cr != CR_BUFFER_SMALL or not size.value:
        return None
    buf = (ctypes.c_ubyte * size.value)()
    if cfg.CM_Get_Device_Interface_PropertyW(path, ctypes.byref(key), ctypes.byref(ptype), buf, ctypes.byref(size), 0):
        return None
    return decode_prop(ptype.value, bytes(buf))


def iface_instance(path: str) -> str | None:
    """Device instance ID behind an interface symbolic link (MF symlink / DS DevicePath). Falls back to parsing."""
    v = iface_prop(path, "InstanceId")
    if isinstance(v, str) and v:
        return v
    return link_to_instance_id(path)


def link_to_instance_id(link: str | None) -> str | None:
    """'\\\\?\\usb#vid_046d&pid_085c&mi_00#8&268da596&0&0000#{guid}\\global' -> 'USB\\VID_046D&PID_085C&MI_00\\8&268DA596&0&0000'
    (also accepts '@device_pnp_' / '@device:pnp:' prefixes). Upper-cased, like PnP instance IDs."""
    if not link:
        return None
    import re
    s = re.sub(r"^@device[:_]pnp[:_]", "", link, flags=re.I)
    s = re.sub(r"^\\\\\?\\", "", s)
    s = s.split("#{")[0]
    return s.replace("#", "\\").upper()


def parse_usb_ids(iid: str | None) -> tuple[str | None, str | None, str | None]:
    """(vid, pid, mi) lower-case hex from an instance ID or symlink; None where absent."""
    if not iid:
        return None, None, None
    u = iid.upper()
    vid = u.split("VID_")[1][:4].lower() if "VID_" in u else None
    pid = u.split("PID_")[1][:4].lower() if "PID_" in u else None
    mi = u.split("&MI_")[1][:2].lower() if "&MI_" in u else None
    return vid, pid, mi


def decode_pld(h: str | None) -> dict | None:
    """ACPI 6.5 section 6.1.8 _PLD buffer (revision 1/2). From win_topology_probe.py. Returns None for no data.
    'position_all_zero' is True when panel/vertical/horizontal bits are all 0 (topology_windows verifier C16: the
    zero values then mean 'unspecified', not 'top / upper / left'); 'all_zero_defaults' also requires shape 0."""
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
           "width_mm": bits(32, 16), "height_mm": bits(48, 16), "user_visible": bool(bits(64, 1)),
           "dock": bool(bits(65, 1)), "lid": bool(bits(66, 1)),
           "panel": panel[bits(67, 3)] if bits(67, 3) < 7 else bits(67, 3),
           "vertical_position": ["upper", "center", "lower", "?"][bits(70, 2)],
           "horizontal_position": ["left", "center", "right", "?"][bits(72, 2)],
           "shape": bits(74, 4), "group_orientation": bits(78, 1), "group_token": bits(79, 8),
           "group_position": bits(87, 8), "bay": bool(bits(95, 1)), "ejectable": bool(bits(96, 1)),
           "cabinet": bits(98, 8), "card_cage": bits(106, 8), "reference": bits(114, 1), "rotation": bits(115, 4),
           "order": bits(119, 5)}
    if len(b) >= 20:
        out["vertical_offset"], out["horizontal_offset"] = bits(128, 16), bits(144, 16)
    # panel 0 / vertical 0 / horizontal 0 are the zero defaults ("top, upper, left"): treat them as unspecified
    out["position_all_zero"] = bits(67, 3) == 0 and bits(70, 2) == 0 and bits(72, 2) == 0
    out["all_zero_defaults"] = out["position_all_zero"] and bits(74, 4) == 0
    return out


PLD_SHAPES = {0: "round", 1: "oval", 2: "square", 3: "vertical_rectangle", 4: "horizontal_rectangle",
              5: "vertical_trapezoid", 6: "horizontal_trapezoid", 7: "unknown", 8: "chamfered"}


# ------------------------------------------------------------------------------------------------ registry (read)
def reg_values(path: str, hive=None) -> dict | None:
    """All values of an HKLM (default) key, read-only. None if the key does not exist or cannot be read."""
    import winreg
    hive = winreg.HKEY_LOCAL_MACHINE if hive is None else hive
    out: dict = {}
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ) as k:
            i = 0
            while True:
                try:
                    name, val, typ = winreg.EnumValue(k, i)
                except OSError:
                    break
                out[name] = val.hex() if isinstance(val, bytes) else val
                i += 1
    except OSError:
        return None
    return out


def reg_subkeys(path: str, hive=None) -> list[str] | None:
    import winreg
    hive = winreg.HKEY_LOCAL_MACHINE if hive is None else hive
    out = []
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ) as k:
            i = 0
            while True:
                try:
                    out.append(winreg.EnumKey(k, i))
                except OSError:
                    break
                i += 1
    except OSError:
        return None
    return out


def reg_value(path: str, name: str, hive=None):
    vals = reg_values(path, hive)
    return None if vals is None else vals.get(name)


def metadata_registry(function_instance_id: str | None) -> dict:
    """MetadataBufferSizeInKB<n> on the CURRENT interface instance's DeviceClasses keys (read-only), for
    KSCATEGORY_CAPTURE and KSCATEGORY_VIDEO_CAMERA. Plan section 2.2 / windows_mf_vs_ds.md section 2: this is the
    value that makes usbvideo deliver UVC PTS/SCR. Read as environment context only (W-ENV); the suite is tier 0 only
    since 2026-11-09 and rates nothing on it. Returns {tier1: bool, per_category: {...}}."""
    out: dict = {"function_instance_id": function_instance_id, "per_category": {}, "tier1": False,
                 "values_kb": {}}
    if not function_instance_id:
        return out
    inst = function_instance_id.replace("\\", "#")
    for cat in ("KSCATEGORY_CAPTURE", "KSCATEGORY_VIDEO_CAMERA"):
        g = GUIDS[cat].upper()
        base = f"SYSTEM\\CurrentControlSet\\Control\\DeviceClasses\\{g}"
        sub = f"##?#{inst}#{g}"
        found = None
        names = reg_subkeys(base) or []
        for n in names:  # case-insensitive match of the interface key name
            if n.upper() == sub.upper():
                found = n
                break
        rec: dict = {"interface_key": f"HKLM\\{base}\\{found or sub}", "exists": found is not None}
        if found:
            dp = reg_values(f"{base}\\{found}\\#GLOBAL\\Device Parameters")
            rec["device_parameters_exists"] = dp is not None
            md = {k: v for k, v in (dp or {}).items() if k.lower().startswith("metadatabuffersizeinkb")}
            rec["metadata_values"] = md
            rec["other_values"] = sorted(k for k in (dp or {}) if k not in md)
            for k, v in md.items():
                try:
                    if int(v) > 0:
                        out["tier1"] = True
                        out["values_kb"][f"{cat}:{k}"] = int(v)
                except (TypeError, ValueError):
                    pass
        out["per_category"][cat] = rec
    return out


# ------------------------------------------------------------------------------------------------ hub IOCTLs
GENERIC_WRITE, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING = 0x40000000, 1, 2, 3
INVALID_HANDLE = ctypes.c_void_p(-1).value
k32.CreateFileW.restype = wt.HANDLE
k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE]
k32.DeviceIoControl.argtypes = [wt.HANDLE, wt.DWORD, wt.LPVOID, wt.DWORD, wt.LPVOID, wt.DWORD,
                                ctypes.POINTER(wt.DWORD), wt.LPVOID]
k32.CloseHandle.argtypes = [wt.HANDLE]

SAFE_IOCTLS = {258, 261, 264, 265, 270, 272, 274, 276, 277, 278, 279}
DESCRIPTOR_IOCTL = 260
USBUSER_READ_CODES = {1, 2, 5, 6, 7, 8}


def _ctl(fn: int) -> int:  # CTL_CODE(FILE_DEVICE_USB=0x22, fn, METHOD_BUFFERED, FILE_ANY_ACCESS)
    return (0x22 << 16) | (fn << 2)


def open_path(path: str):
    """(handle, 0) or (None, winerror). GENERIC_WRITE + share read/write, as usbview does for hub queries."""
    h = k32.CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
    return (None, ctypes.get_last_error()) if h in (None, INVALID_HANDLE) else (h, 0)


def close(h) -> None:
    if h:
        k32.CloseHandle(h)


def ioctl(h, fn: int, inbuf: bytes, outsize: int, _allow_descriptor: bool = False):
    """(bytes, 0) or (None, winerror). Only allow-listed read-only function codes."""
    if fn not in SAFE_IOCTLS and not (_allow_descriptor and fn == DESCRIPTOR_IOCTL):
        raise PermissionError(f"IOCTL function {fn} is not on the read-only allow-list")
    if fn == 270:  # IOCTL_USB_USER_REQUEST: the USBUSER code is the first ULONG; only read codes, never USBUSER_OP_*
        code = struct.unpack_from("<I", inbuf)[0] if len(inbuf) >= 4 else None
        if code not in USBUSER_READ_CODES:
            raise PermissionError(f"USBUSER code {code} is not a read code")
    size = max(len(inbuf), outsize)
    buf = ctypes.create_string_buffer(inbuf, size)
    ret = wt.DWORD()
    if not k32.DeviceIoControl(h, _ctl(fn), buf, len(inbuf), buf, size, ctypes.byref(ret), None):
        return None, ctypes.get_last_error()
    return buf.raw[:ret.value], 0


def usb_name(h, fn: int, inbuf: bytes, off: int) -> str | None:
    raw, _ = ioctl(h, fn, inbuf + bytes(1024), len(inbuf) + 1024)
    if raw is None or len(raw) <= off:
        return None
    return raw[off:].decode("utf-16-le", "replace").split("\0")[0] or None


CONN = ["NoDeviceConnected", "DeviceConnected", "DeviceFailedEnumeration", "DeviceGeneralFailure",
        "DeviceCausedOvercurrent", "DeviceNotEnoughPower", "DeviceNotEnoughBandwidth", "DeviceHubNestedTooDeeply",
        "DeviceInLegacyHub", "DeviceEnumerating", "DeviceReset"]
LEGACY_SPEED = {0: "low", 1: "full", 2: "high", 3: "super"}
EP_TYPES = ["control", "iso", "bulk", "interrupt"]


def connection_info(h, port: int) -> dict:
    """IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX (274) + _V2 (279) + DRIVERKEY (264) for one hub port.
    All answered from the hub driver's cached state (no request to the device)."""
    e: dict = {"port": port}
    raw, err = ioctl(h, 274, struct.pack("<I", port) + bytes(31 + 11 * 32), 35 + 11 * 32)
    if raw is not None and len(raw) >= 35:
        dd = raw[4:22]
        vid, pid, bcd_dev = struct.unpack_from("<HHH", dd, 8)
        cur_cfg, spd, is_hub = raw[22], raw[23], raw[24]
        addr, npipes, st = struct.unpack_from("<HII", raw, 25)
        e.update(status=CONN[st] if st < len(CONN) else st, legacy_speed=LEGACY_SPEED.get(spd, spd),
                 device_is_hub=bool(is_hub))
        if st != 0:
            e.update(vid=f"{vid:04x}", pid=f"{pid:04x}", bcd_device=f"{bcd_dev:04x}",
                     bcd_usb=f"{struct.unpack_from('<H', dd, 2)[0]:04x}", device_class=dd[4],
                     i_manufacturer=dd[14], i_product=dd[15], i_serial=dd[16], address=addr,
                     current_configuration=cur_cfg, open_pipes=[])
            for k in range(npipes):
                o = 35 + 11 * k
                if o + 11 > len(raw):
                    break
                _l, _t, ea, attr, wmps, bint, sched = struct.unpack_from("<BBBBHBI", raw, o)
                e["open_pipes"].append({"ep": f"0x{ea:02x}", "type": EP_TYPES[attr & 3],
                                        "wMaxPacketSize": f"0x{wmps:04x}", "max_packet": wmps & 0x7FF,
                                        "mult": ((wmps >> 11) & 3) + 1, "bInterval": bint,
                                        "schedule_offset": sched})
    else:
        e["conn_info_error"] = err
    raw, err = ioctl(h, 279, struct.pack("<IIII", port, 16, 0x7, 0), 16)
    if raw and len(raw) >= 16:
        protos, flags = struct.unpack_from("<II", raw, 8)
        e["port_protocols"] = [n for b, n in ((1, "usb1.1"), (2, "usb2.0"), (4, "usb3")) if protos & b]
        e["v2_flags"] = {"op_ss": bool(flags & 1), "ss_capable": bool(flags & 2), "op_ssp": bool(flags & 4),
                         "ssp_capable": bool(flags & 8)}
    else:
        e["v2_error"] = err
    if e.get("status") not in (None, "NoDeviceConnected"):
        e["driver_key"] = usb_name(h, 264, struct.pack("<II", port, 0), 8)
        if e.get("device_is_hub"):
            e["child_hub_name"] = usb_name(h, 261, struct.pack("<II", port, 0), 8)
    return e


def port_connector(h, port: int) -> dict:
    """IOCTL_USB_GET_PORT_CONNECTOR_PROPERTIES (278), two-call pattern; loops CompanionIndex when the port has
    several companions."""
    first, err = ioctl(h, 278, struct.pack("<II", port, 0) + bytes(12), 20)
    if not first:
        return {"error": err}
    out: dict = {}
    companions = []
    for cidx in range(4):
        actual = max(struct.unpack_from("<I", first, 4)[0], 20)
        raw, err = ioctl(h, 278, struct.pack("<IIIH", port, 0, 0, cidx) + bytes(max(actual - 14, 6)), actual)
        if not raw:
            break
        _, _, pr, ci, cport = struct.unpack_from("<IIIHH", raw)
        name = raw[16:].decode("utf-16-le", "replace").split("\0")[0] or None
        if cidx == 0:
            out = {"user_connectable": bool(pr & 1), "debug_capable": bool(pr & 2),
                   "multiple_companions": bool(pr & 4), "type_c": bool(pr & 8)}
        if cport or name:
            companions.append({"companion_index": ci, "companion_port": cport, "companion_hub": name})
        if not (pr & 4):
            break
    out["companions"] = companions
    out["companion_port"] = companions[0]["companion_port"] if companions else 0
    out["companion_hub"] = companions[0]["companion_hub"] if companions else None
    return out


def hub_node_info(h) -> dict:
    out: dict = {}
    raw, err = ioctl(h, 258, bytes(76), 76)
    if raw:
        out["node_info"] = {"NodeType": raw[0], "bNumberOfPorts": raw[6],
                            "wHubCharacteristics": hex(struct.unpack_from("<H", raw, 7)[0])}
    raw, err = ioctl(h, 277, bytes(80), 80)
    if raw:
        ht, hp = struct.unpack_from("<IH", raw)
        out["hub_info_ex"] = {"HubType": {1: "UsbRootHub", 2: "Usb20Hub", 3: "Usb30Hub"}.get(ht, ht),
                              "HighestPortNumber": hp}
    else:
        out["hub_info_ex_error"] = err
    raw, err = ioctl(h, 276, bytes(4), 4)
    if raw:
        f = struct.unpack_from("<I", raw)[0]
        out["hub_caps_ex"] = {n: bool(f & (1 << i)) for i, n in enumerate(
            ["HubIsHighSpeedCapable", "HubIsHighSpeed", "HubIsMultiTtCapable", "HubIsMultiTt", "HubIsRoot",
             "HubIsArmedWakeOnConnect", "HubIsBusPowered"])}
    n = (out.get("hub_info_ex") or {}).get("HighestPortNumber") or (out.get("node_info") or {}).get("bNumberOfPorts")
    out["n_ports"] = n or 0
    return out


def user_request(h, code: int, payload_len: int) -> dict:
    if code not in USBUSER_READ_CODES:
        raise PermissionError(f"USBUSER code {code} is not a read code")
    hdr = struct.pack("<IIII", code, 0, 16 + payload_len, 0)
    raw, err = ioctl(h, 270, hdr + bytes(payload_len), 16 + payload_len)
    if raw is None:
        return {"win32_error": err}
    req, status, rlen, alen = struct.unpack_from("<IIII", raw)
    st = ["UsbUserSuccess", "UsbUserNotSupported", "UsbUserInvalidRequestCode", "UsbUserFeatureDisabled",
          "UsbUserInvalidHeaderParameter", "UsbUserInvalidParameter", "UsbUserMiniportError",
          "UsbUserBufferTooSmall", "UsbUserErrorNotMapped", "UsbUserDeviceNotStarted", "UsbUserNoDeviceConnected"]
    return {"status": st[status] if status < len(st) else status, "actual_len": alen, "payload": raw[16:]}


def hub_interface_for_instance(hub_iid: str) -> str | None:
    paths = iface_list(GUIDS["USB_HUB"], hub_iid)
    return paths[0] if paths else None


def cached_port_info(hub_iid: str | None, port: int | None) -> dict | None:
    """Cached connection info (274/279) + connector properties (278) for the port a device sits on."""
    if not hub_iid or port is None:
        return None
    path = hub_interface_for_instance(hub_iid)
    if not path:
        return {"error": "no hub interface"}
    h, err = open_path(path)
    if h is None:
        return {"error": f"open hub failed, winerror {err}"}
    try:
        ci = connection_info(h, int(port))
        ci["connector"] = port_connector(h, int(port))
        return ci
    finally:
        close(h)


def get_descriptor(h, port: int, dtype: int, index: int = 0, lang: int = 0, length: int = 4096) -> bytes | None:
    """GET_DESCRIPTOR via IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION (260). THIS SENDS A REAL EP0 REQUEST to
    the device. Call it only from a child process under camlock (see helpers/win_descriptors.py)."""
    setup = struct.pack("<IBBHHH", port, 0x80, 6, (dtype << 8) | index, lang, length)
    raw, err = ioctl(h, DESCRIPTOR_IOCTL, setup + bytes(length), 12 + length, _allow_descriptor=True)
    if raw is None:
        raise OSError(err, f"GET_DESCRIPTOR(type {dtype}, index {index}) failed")
    return raw[12:]


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
