# /// script
# requires-python = ">=3.10"
# ///
"""Windows USB topology + UVC VideoStreaming alt-setting budget + live open-pipe snapshot.

Goal 3 (USB bandwidth) harness for the skellycam USB camera investigation.
Stdlib only (ctypes). No admin rights needed. Does NOT open any camera, so it does not need
camlock by itself; to see which alt setting Windows selected, run it (with --pipes-only) while a
stream is running (see run_concurrency.py, which does exactly that).

What it does
  * enumerates every USB hub (GUID_DEVINTERFACE_USB_HUB) and its parent chain up to the PCI
    host controller (CfgMgr32 CM_Get_Parent),
  * for every hub port: IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX (device descriptor, speed,
    address, and the list of currently OPEN pipes = endpoints of the currently selected alt
    settings), IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX_V2 (SuperSpeed capability),
    IOCTL_USB_GET_NODE_CONNECTION_DRIVERKEY_NAME,
  * for UVC devices (an interface with class 0x0E) reads the full configuration descriptor via
    IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION and lists every VideoStreaming alternate setting
    with its isochronous bytes per service interval, plus formats/frames (dwMaxBitRate etc.).

Usage
  uv run --script research/usb_cameras/bandwidth/win_usb_topology.py [--out FILE.json]
  uv run --script research/usb_cameras/bandwidth/win_usb_topology.py --pipes-only   (prints JSON)

Output: results/windows/<hostname>/bw_topology/topology.json by default.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import datetime as _dt
import json
import platform
import socket
import struct
import sys
from pathlib import Path

if sys.platform != "win32":
    sys.exit("win_usb_topology.py is Windows-only")

setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
cfgmgr = ctypes.WinDLL("cfgmgr32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# ---------------------------------------------------------------- IOCTLs (usbiodef.h / usbioctl.h, SDK 10.0.22621)
FILE_DEVICE_USB = 0x22  # FILE_DEVICE_UNKNOWN


def _ctl(fn: int) -> int:  # CTL_CODE(FILE_DEVICE_USB, fn, METHOD_BUFFERED, FILE_ANY_ACCESS)
    return (FILE_DEVICE_USB << 16) | (fn << 2)


IOCTL_USB_GET_NODE_INFORMATION = _ctl(258)
IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION = _ctl(260)
IOCTL_USB_GET_NODE_CONNECTION_DRIVERKEY_NAME = _ctl(264)
IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX = _ctl(274)
IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX_V2 = _ctl(279)

SPEED = {0: "low", 1: "full", 2: "high", 3: "super"}
CONN_STATUS = {0: "NoDeviceConnected", 1: "DeviceConnected", 2: "DeviceFailedEnumeration",
               3: "DeviceGeneralFailure", 4: "DeviceCausedOvercurrent", 5: "DeviceNotEnoughPower",
               6: "DeviceNotEnoughBandwidth", 7: "DeviceHubNestedTooDeeply", 8: "DeviceInLegacyHub",
               9: "DeviceEnumerating", 10: "DeviceReset"}
EP_TYPES = {0: "control", 1: "isochronous", 2: "bulk", 3: "interrupt"}

GUID_DEVINTERFACE_USB_HUB = "{F18A0E88-C30C-11D0-8815-00A0C906BED8}"
DIGCF_PRESENT, DIGCF_ALLCLASSES, DIGCF_DEVICEINTERFACE = 0x2, 0x4, 0x10
SPDRP_DRIVER = 0x9
GENERIC_WRITE, FILE_SHARE_WRITE, FILE_SHARE_READ, OPEN_EXISTING = 0x40000000, 0x2, 0x1, 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]


def _guid(s: str) -> GUID:
    g = GUID()
    ctypes.OleDLL("ole32").CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
    return g


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("ClassGuid", GUID), ("DevInst", wt.DWORD), ("Reserved", ctypes.c_void_p)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("InterfaceClassGuid", GUID), ("Flags", wt.DWORD), ("Reserved", ctypes.c_void_p)]


setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wt.LPCWSTR, wt.HWND, wt.DWORD]
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), wt.DWORD,
                                                 ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
                                                      ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD),
                                                      ctypes.POINTER(SP_DEVINFO_DATA)]
setupapi.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.POINTER(SP_DEVINFO_DATA)]
setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA), wt.DWORD,
                                                       ctypes.POINTER(wt.DWORD), ctypes.c_void_p, wt.DWORD,
                                                       ctypes.POINTER(wt.DWORD)]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
kernel32.CreateFileW.restype = ctypes.c_void_p
kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.c_void_p]
kernel32.DeviceIoControl.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD,
                                     ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]


def _dev_id(devinst: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    cfgmgr.CM_Get_Device_IDW(devinst, buf, 512, 0)
    return buf.value


def _parent_chain(devinst: int) -> list[str]:
    chain = []
    cur = wt.DWORD(devinst)
    for _ in range(16):
        parent = wt.DWORD()
        if cfgmgr.CM_Get_Parent(ctypes.byref(parent), cur, 0) != 0:
            break
        pid = _dev_id(parent.value)
        chain.append(pid)
        if pid.upper().startswith("PCI\\") or pid.upper().startswith("HTREE"):
            break
        cur = parent
    return chain


def _driverkey_to_instance() -> dict[str, str]:
    """Map SPDRP_DRIVER (e.g. '{36fc9e60-...}\\0012') -> device instance id for all present devices."""
    out = {}
    h = setupapi.SetupDiGetClassDevsW(None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
    try:
        i = 0
        while True:
            did = SP_DEVINFO_DATA(cbSize=ctypes.sizeof(SP_DEVINFO_DATA))
            if not setupapi.SetupDiEnumDeviceInfo(h, i, ctypes.byref(did)):
                break
            i += 1
            buf = ctypes.create_unicode_buffer(512)
            if setupapi.SetupDiGetDeviceRegistryPropertyW(h, ctypes.byref(did), SPDRP_DRIVER, None, buf, 1024, None):
                out[buf.value.lower()] = _dev_id(did.DevInst)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(h)
    return out


def _hubs() -> list[dict]:
    g = _guid(GUID_DEVINTERFACE_USB_HUB)
    h = setupapi.SetupDiGetClassDevsW(ctypes.byref(g), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    hubs = []
    try:
        i = 0
        while True:
            ifd = SP_DEVICE_INTERFACE_DATA(cbSize=ctypes.sizeof(SP_DEVICE_INTERFACE_DATA))
            if not setupapi.SetupDiEnumDeviceInterfaces(h, None, ctypes.byref(g), i, ctypes.byref(ifd)):
                break
            i += 1
            need = wt.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(h, ctypes.byref(ifd), None, 0, ctypes.byref(need), None)
            buf = ctypes.create_string_buffer(need.value)
            struct.pack_into("<I", buf, 0, 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6)
            did = SP_DEVINFO_DATA(cbSize=ctypes.sizeof(SP_DEVINFO_DATA))
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(h, ctypes.byref(ifd), buf, need, None, ctypes.byref(did)):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            hubs.append({"device_path": path, "instance_id": _dev_id(did.DevInst),
                         "parent_chain": _parent_chain(did.DevInst)})
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(h)
    return hubs


def _ioctl(handle, code: int, inbuf: bytes, outlen: int) -> bytes | None:
    ib = ctypes.create_string_buffer(inbuf, max(len(inbuf), outlen))
    ret = wt.DWORD()
    ok = kernel32.DeviceIoControl(handle, code, ib, len(inbuf), ib, max(len(inbuf), outlen), ctypes.byref(ret), None)
    if not ok:
        return None
    return ib.raw[: ret.value]


def _get_descriptor(handle, port: int, dtype: int, index: int, lang: int, length: int) -> bytes | None:
    # USB_DESCRIPTOR_REQUEST: ULONG ConnectionIndex; {bmRequest,bRequest,wValue,wIndex,wLength}; Data[]
    req = struct.pack("<IBBHHH", port, 0x80, 6, (dtype << 8) | index, lang, length)
    out = _ioctl(handle, IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION, req + bytes(length), 12 + length)
    return None if out is None else out[12:]


def _string(handle, port: int, idx: int) -> str | None:
    if not idx:
        return None
    d = _get_descriptor(handle, port, 3, idx, 0x0409, 255)
    if not d or len(d) < 2:
        return None
    return d[2:d[0]].decode("utf-16-le", "replace")


# ---------------------------------------------------------------- descriptor parsing (VS-focused)
def _fourcc(guid16: bytes) -> str:
    fcc = guid16[:4]
    return fcc.decode("ascii", "replace") if all(32 <= c < 127 for c in fcc) else fcc.hex()


def parse_uvc_config(cfg: bytes, speed: str) -> dict:
    """Return VC clock + per-VS-interface alt settings (bytes/interval) and formats/frames."""
    res = {"vc": {}, "vs_interfaces": {}}
    i, cur_if, cur_alt, cur_cls, cur_sub = 0, None, None, None, None
    cur_ep = None
    cur_fmt = None
    while i + 2 <= len(cfg):
        ln, typ = cfg[i], cfg[i + 1]
        if ln < 2:
            break
        d = cfg[i:i + ln]
        if typ == 4 and ln >= 9:  # interface
            cur_if, cur_alt, cur_cls, cur_sub = d[2], d[3], d[5], d[6]
            cur_ep = None
            if cur_cls == 0x0E and cur_sub == 2:
                vs = res["vs_interfaces"].setdefault(str(cur_if), {"alt_settings": [], "formats": []})
                vs["alt_settings"].append({"bAlternateSetting": cur_alt, "endpoints": []})
        elif typ == 5 and ln >= 7 and cur_cls == 0x0E and cur_sub == 2:
            addr, attr, wmps, binterval = d[2], d[3], struct.unpack_from("<H", d, 4)[0], d[6]
            base, mult = wmps & 0x7FF, ((wmps >> 11) & 3) + 1
            ep = {"bEndpointAddress": f"0x{addr:02x}", "type": EP_TYPES[attr & 3], "wMaxPacketSize": f"0x{wmps:04x}",
                  "base_packet_bytes": base, "transactions_per_microframe": mult, "bInterval": binterval}
            if speed in ("high", "super", "super_plus"):
                interval_uframes = 2 ** (binterval - 1) if binterval else 1
                ep["service_interval_us"] = 125 * interval_uframes
            else:
                interval_uframes = None
                ep["service_interval_us"] = 1000 * (2 ** (binterval - 1) if (attr & 3) == 1 and binterval else 1)
            ep["bytes_per_interval"] = base * mult if speed == "high" else base
            res["vs_interfaces"][str(cur_if)]["alt_settings"][-1]["endpoints"].append(ep)
            cur_ep = ep
        elif typ == 0x30 and ln >= 6 and cur_ep is not None:  # SS endpoint companion
            cur_ep["ss_bMaxBurst"] = d[2]
            cur_ep["ss_bmAttributes"] = d[3]
            cur_ep["ss_wBytesPerInterval"] = struct.unpack_from("<H", d, 4)[0]
            cur_ep["bytes_per_interval"] = cur_ep["ss_wBytesPerInterval"]
        elif typ == 0x24 and cur_cls == 0x0E and cur_sub == 1 and ln >= 3 and d[2] == 1 and ln >= 12:
            res["vc"] = {"bcdUVC": f"{struct.unpack_from('<H', d, 3)[0]:04x}",
                         "dwClockFrequency": struct.unpack_from("<I", d, 7)[0]}
        elif typ == 0x24 and cur_cls == 0x0E and cur_sub == 2 and ln >= 3:
            vs = res["vs_interfaces"][str(cur_if)]
            st = d[2]
            if st == 1 and ln >= 7:
                vs["input_header_bEndpointAddress"] = f"0x{d[6]:02x}"
            elif st in (4, 6, 0x10):
                name = {4: "UNCOMPRESSED", 6: "MJPEG", 0x10: "FRAME_BASED"}[st]
                fmt = {"bFormatIndex": d[3], "type": name, "frames": []}
                if st in (4, 0x10) and ln >= 21:
                    fmt["fourcc"] = _fourcc(d[5:21])
                    fmt["bBitsPerPixel"] = d[21] if ln > 21 else None
                vs["formats"].append(fmt)
                cur_fmt = fmt
            elif st in (5, 7, 0x11) and cur_fmt is not None and ln >= 26:
                w, h = struct.unpack_from("<HH", d, 5)
                minbr, maxbr = struct.unpack_from("<II", d, 9)
                fr = {"bFrameIndex": d[3], "width": w, "height": h, "dwMinBitRate": minbr, "dwMaxBitRate": maxbr}
                if st in (5, 7):
                    fr["dwMaxVideoFrameBufferSize"] = struct.unpack_from("<I", d, 17)[0]
                    fr["dwDefaultFrameInterval"], ntype = struct.unpack_from("<IB", d, 21)
                    off = 26
                else:
                    fr["dwDefaultFrameInterval"], ntype = struct.unpack_from("<IB", d, 17)
                    off = 26
                if ntype == 0:
                    fr["interval_continuous"] = list(struct.unpack_from("<III", d, off)) if ln >= off + 12 else None
                    ivals = []
                else:
                    ivals = [struct.unpack_from("<I", d, off + 4 * k)[0] for k in range(ntype) if off + 4 * k + 4 <= ln]
                fr["fps"] = [round(1e7 / v, 3) for v in ivals if v]
                cur_fmt["frames"].append(fr)
        i += ln
    return res


def _conn_info(handle, port: int) -> dict | None:
    hdr = 35
    out = _ioctl(handle, IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX, struct.pack("<I", port) + bytes(hdr - 4 + 11 * 32),
                 hdr + 11 * 32)
    if out is None or len(out) < hdr:
        return None
    dd = out[4:22]
    (cfgval, speed, is_hub) = out[22], out[23], out[24]
    addr, npipes, status = struct.unpack_from("<HII", out, 25)
    pipes = []
    for k in range(npipes):
        off = hdr + 11 * k
        if off + 11 > len(out):
            break
        ln, typ, ea, attr, wmps, binterval, sched = struct.unpack_from("<BBBBHBI", out, off)
        base, mult = wmps & 0x7FF, ((wmps >> 11) & 3) + 1
        pipes.append({"bEndpointAddress": f"0x{ea:02x}", "type": EP_TYPES[attr & 3], "wMaxPacketSize": f"0x{wmps:04x}",
                      "base_packet_bytes": base, "transactions_per_microframe": mult, "bInterval": binterval,
                      "ScheduleOffset": sched})
    vid, pid, bcd = struct.unpack_from("<HHH", dd, 8)
    info = {"port": port, "status": CONN_STATUS.get(status, status), "speed": SPEED.get(speed, speed),
            "device_is_hub": bool(is_hub), "address": addr, "current_configuration": cfgval,
            "idVendor": f"{vid:04x}", "idProduct": f"{pid:04x}", "bcdDevice": f"{bcd:04x}", "bcdUSB": f"{struct.unpack_from('<H', dd, 2)[0]:04x}",
            "iManufacturer": dd[14], "iProduct": dd[15], "iSerialNumber": dd[16], "open_pipes": pipes}
    v2 = _ioctl(handle, IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX_V2, struct.pack("<IIII", port, 16, 0x7, 0), 16)
    if v2 and len(v2) >= 16:
        protos, flags = struct.unpack_from("<II", v2, 8)
        info["v2_supported_protocols"] = {"usb110": bool(protos & 1), "usb200": bool(protos & 2), "usb300": bool(protos & 4)}
        info["v2_flags"] = {"operating_at_superspeed_or_higher": bool(flags & 1), "superspeed_capable_or_higher": bool(flags & 2),
                            "operating_at_superspeed_plus": bool(flags & 4), "superspeed_plus_capable": bool(flags & 8)}
        # The legacy Speed field cannot express SuperSpeed (it reports UsbHighSpeed for SS devices);
        # the V2 flags are authoritative.
        info["legacy_speed_field"] = info["speed"]
        if flags & 1:
            info["speed"] = "super_plus" if flags & 4 else "super"
    dk = _ioctl(handle, IOCTL_USB_GET_NODE_CONNECTION_DRIVERKEY_NAME, struct.pack("<II", port, 0) + bytes(512), 520)
    if dk and len(dk) > 8:
        info["driver_key"] = dk[8:].decode("utf-16-le", "replace").rstrip("\x00")
    return info


def scan(read_descriptors: bool = True, exclude: set[str] | None = None) -> dict:
    """exclude: {"vvvv:pppp", ...} lower-case. Excluded devices get NO descriptor/string requests (no EP0 traffic to the
    device); only the hub driver's cached connection info (device descriptor, open pipes) is recorded for them."""
    exclude = exclude or set()
    dk_map = _driverkey_to_instance()
    hubs_out = []
    cameras = []
    for hub in _hubs():
        h = kernel32.CreateFileW(hub["device_path"], GENERIC_WRITE, FILE_SHARE_WRITE | FILE_SHARE_READ, None, OPEN_EXISTING, 0, None)
        if h in (None, INVALID_HANDLE_VALUE):
            hub["error"] = f"CreateFile failed, winerror {ctypes.get_last_error()}"
            hubs_out.append(hub)
            continue
        try:
            ni = _ioctl(h, IOCTL_USB_GET_NODE_INFORMATION, bytes(76), 76)
            nports = ni[6] if ni and len(ni) > 6 else 0
            hub["num_ports"] = nports
            controller = next((p for p in hub["parent_chain"] if p.upper().startswith("PCI\\")), None)
            hub["controller"] = controller
            hub["ports"] = []
            for port in range(1, nports + 1):
                ci = _conn_info(h, port)
                if ci is None or ci["status"] == "NoDeviceConnected":
                    continue
                ci["instance_id"] = dk_map.get(ci.get("driver_key", "").lower())
                hub["ports"].append(ci)
                if f'{ci["idVendor"]}:{ci["idProduct"]}' in exclude:
                    ci["excluded_no_descriptor_requests"] = True
                    continue
                if read_descriptors and not ci["device_is_hub"] and ci["status"] == "DeviceConnected":
                    c9 = _get_descriptor(h, port, 2, 0, 0, 9)
                    if c9 and len(c9) >= 4:
                        total = struct.unpack_from("<H", c9, 2)[0]
                        cfg = _get_descriptor(h, port, 2, 0, 0, total)
                        has_video = cfg is not None and any(
                            cfg[k + 1] == 4 and cfg[k + 5] == 0x0E for k in _desc_offsets(cfg))
                        if has_video:
                            ci["product"] = _string(h, port, ci["iProduct"])
                            ci["manufacturer"] = _string(h, port, ci["iManufacturer"])
                            ci["serial"] = _string(h, port, ci["iSerialNumber"])
                            ci["uvc"] = parse_uvc_config(cfg, ci["speed"])
                            ci["config_descriptor_hex"] = cfg.hex()
                            cameras.append({"hub_instance_id": hub["instance_id"], "controller": controller,
                                            "hub_parent_chain": hub["parent_chain"], **ci})
        finally:
            kernel32.CloseHandle(h)
        hubs_out.append(hub)
    return {"hubs": hubs_out, "cameras": cameras}


def _desc_offsets(cfg: bytes):
    i = 0
    while i + 2 <= len(cfg) and cfg[i] >= 2:
        if i + 6 <= len(cfg):
            yield i
        i += cfg[i]


def pipes_snapshot(exclude: set[str] | None = None) -> list[dict]:
    """Compact: per UVC camera, its open isochronous/bulk pipes right now."""
    snap = scan(read_descriptors=True, exclude=exclude)
    out = []
    for c in snap["cameras"]:
        out.append({"idVendor": c["idVendor"], "idProduct": c["idProduct"], "product": c.get("product"),
                    "speed": c["speed"], "controller": c["controller"], "hub": c["hub_instance_id"], "port": c["port"],
                    "open_pipes": c["open_pipes"],
                    "matched_alt_settings": match_alt(c)})
    return out


def match_alt(cam: dict) -> list[dict]:
    """For each open pipe on a VS endpoint, which VS alt setting(s) have that exact endpoint descriptor."""
    res = []
    for p in cam["open_pipes"]:
        for ifn, vs in cam.get("uvc", {}).get("vs_interfaces", {}).items():
            for alt in vs["alt_settings"]:
                for ep in alt["endpoints"]:
                    if ep["bEndpointAddress"] == p["bEndpointAddress"] and ep["wMaxPacketSize"] == p["wMaxPacketSize"] \
                            and ep["bInterval"] == p["bInterval"]:
                        res.append({"interface": int(ifn), "bAlternateSetting": alt["bAlternateSetting"],
                                    "endpoint": p["bEndpointAddress"], "bytes_per_interval": ep["bytes_per_interval"],
                                    "service_interval_us": ep.get("service_interval_us")})
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--pipes-only", action="store_true")
    ap.add_argument("--exclude", action="append", default=[], metavar="VID:PID",
                    help="hex vid:pid to skip (no descriptor/string requests sent to it); repeatable")
    a = ap.parse_args()
    excl = {e.lower() for e in a.exclude}
    if a.pipes_only:
        print(json.dumps(pipes_snapshot(excl), indent=1))
        return 0
    host = socket.gethostname()
    out = a.out or Path(__file__).resolve().parent.parent / "results" / "windows" / host / "bw_topology" / "topology.json"
    started = _dt.datetime.now(_dt.timezone.utc).isoformat()
    snap = scan(exclude=excl)
    doc = {"test": "bw_topology", "platform": "windows", "hostname": host, "utc_started": started,
           "command": " ".join(["uv run --script"] + sys.argv),
           "environment": {"os": platform.platform(), "python": platform.python_version()},
           "excluded_vid_pid": sorted(excl),
           "cameras": [{"vid": c["idVendor"], "pid": c["idProduct"], "product": c.get("product"), "serial": c.get("serial"),
                        "speed": c["speed"], "controller": c["controller"], "hub": c["hub_instance_id"], "port": c["port"],
                        "instance_id": c.get("instance_id")} for c in snap["cameras"]],
           **snap}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1))
    print(f"wrote {out}")
    for c in snap["cameras"]:
        print(f"{c['idVendor']}:{c['idProduct']} {c.get('product')!r} speed={c['speed']} ctrl={c['controller']} "
              f"hub={c['hub_instance_id']} port={c['port']} open_pipes={len(c['open_pipes'])}")
        for ifn, vs in c["uvc"]["vs_interfaces"].items():
            alts = [(a['bAlternateSetting'], a['endpoints'][0]['bytes_per_interval'] if a['endpoints'] else 0) for a in vs['alt_settings']]
            print(f"   VS if {ifn}: alt->bytes/interval {alts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
