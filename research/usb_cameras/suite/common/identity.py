"""Stable camera identity key: serial if present, usable and unique, else the physical port path (stdlib only).

The scheme and rules are COPIED (not imported) from research/usb_cameras/naming/camera_identity.py, so the suite
runs without the naming/ folder on sys.path; tests/test_identity.py cross-checks this copy against the original
``derive()`` whenever naming/camera_identity.py is present. Keys are byte-identical to that module's keys:

    "<vid>:<pid>:sn=<serial>"        serial usable and unique among connected cameras with the same VID:PID
    "<vid>:<pid>:port=<port_path>"   otherwise; port_path = "<controller>/<p1.p2...>":
        windows: DEVPKEY_Device_LocationPaths[0] split at USBROOT(n): "PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.4"
        linux:   "pci-<PCI address of the host controller>/<kernel port chain>" e.g. "pci-0000:00:14.0/13.1.4"
        macos:   "bus<bus byte hex>/<port nibbles>" from IOKit locationID, e.g. 0x14130000 -> "bus14/1.3"

VID/PID are lower-case 4-digit hex. A serial is *usable* when it is non-empty, every character is in 0x21..0x7F
and not ',', it is not a known placeholder (all zero, '0123456789', ...) and not one repeated character.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

PLACEHOLDER_SERIALS = {
    "0", "00", "000", "0000", "00000000", "000000000000", "0000000000000000", "1", "01", "0001",
    "0123456789", "123456789", "1234567890", "12345678", "123456", "0123456789abcdef", "0123456789ABCDEF",
    "sn0001", "sn12345678", "none", "null", "default", "serial", "unknown", "n/a", "na", "123", "200901010001",
}


def _hex4(v: Any) -> str:
    """Normalise a VID/PID given as int, '046D', '0x046d' or '046d' to '046d'; '????' if unknown."""
    if v is None or v == "":
        return "????"
    if isinstance(v, int):
        return f"{v:04x}"
    s = str(v).strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    return s.zfill(4) if re.fullmatch(r"[0-9a-f]{1,4}", s) else s


def serial_is_valid_for_os(serial: str | None) -> bool:
    """Windows' rule (stricter than udev's): no char <= 0x20, > 0x7F, or ','. Applied on every OS."""
    if not serial:
        return False
    return all(0x20 < ord(c) <= 0x7F and c != "," for c in serial)


def serial_is_usable(serial: str | None) -> tuple[bool, str]:
    """(usable, reason) for a USB iSerialNumber string, ignoring uniqueness."""
    if not serial or not serial.strip():
        return False, "no serial"
    if not serial_is_valid_for_os(serial):
        return False, "invalid characters (OS ignores it)"
    s = serial.strip()
    if s.lower() in PLACEHOLDER_SERIALS:
        return False, "placeholder serial"
    if len(set(s)) == 1:
        return False, "single repeated character"
    return True, "ok"


def port_path_from_windows_location_paths(loc: str | None) -> str | None:
    """'PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(13)#USB(1)#USB(4)' -> 'PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.4'."""
    if not loc:
        return None
    m = re.match(r"^(.*?#USBROOT\(\d+\))((?:#USB\(\d+\))+)", loc)
    if not m:
        return loc
    ports = re.findall(r"#USB\((\d+)\)", m.group(2))
    return f"{m.group(1)}/{'.'.join(ports)}"


def port_path_from_linux(pci_controller: str | None, kernel_name: str | None) -> str | None:
    """('0000:00:14.0', '3-13.1.4') -> 'pci-0000:00:14.0/13.1.4' (bus number dropped: not boot-stable)."""
    if not kernel_name or "-" not in kernel_name:
        return None
    return f"pci-{pci_controller or '?'}/{kernel_name.split('-', 1)[1]}"


def port_path_from_mac_location_id(location_id: int | None) -> str | None:
    """IOKit locationID 0xBBPPPPPP: top byte = bus, then one nibble per hub tier (port number), 0 terminates."""
    if location_id is None:
        return None
    bus = (location_id >> 24) & 0xFF
    ports = []
    for shift in range(20, -1, -4):
        n = (location_id >> shift) & 0xF
        if n == 0:
            break
        ports.append(str(n))
    return f"bus{bus:02x}/{'.'.join(ports)}"


def _peer_serials(vid: str, pid: str, all_serials: Iterable[Any] | None) -> list[str] | None:
    """Serials of currently connected cameras with this VID:PID. ``all_serials`` items may be
    (vid, pid, serial) tuples, dicts with vid/pid and serial (or usb_serial), or bare serial strings
    (bare strings are taken to be cameras of the same VID:PID)."""
    if all_serials is None:
        return None
    out = []
    for item in all_serials:
        if isinstance(item, (tuple, list)) and len(item) == 3:
            v, p, s = item
        elif isinstance(item, dict):
            v, p = item.get("vid"), item.get("pid")
            s = item.get("serial", item.get("usb_serial"))
        else:
            v, p, s = vid, pid, item
        if _hex4(v) == vid and _hex4(p) == pid:
            out.append(s or "")
    return out


def camera_identity(vid: Any, pid: Any, serial: str | None, port_path: str | None,
                    all_serials: Iterable[Any] | None = None) -> dict[str, Any]:
    """Full identity record: {key, key_kind ('serial'|'port'), vid, pid, serial, serial_usable, reason, port_path}.
    Same decision as naming/camera_identity.py ``derive()``."""
    v, p = _hex4(vid), _hex4(pid)
    ok, reason = serial_is_usable(serial)
    peers = _peer_serials(v, p, all_serials)
    if ok and peers:
        same = [s for s in peers if s == serial]
        if len(same) > 1:
            ok, reason = False, f"serial shared by {len(same)} connected cameras"
    if ok:
        key, kind = f"{v}:{p}:sn={serial}", "serial"
    else:
        key, kind = f"{v}:{p}:port={port_path}", "port"
    return {"key": key, "key_kind": kind, "vid": v, "pid": p, "serial": serial, "serial_usable": ok,
            "reason": reason, "port_path": port_path}


def camera_key(vid: Any, pid: Any, serial: str | None, port_path: str | None,
               all_serials: Iterable[Any] | None = None) -> str:
    """The identity key string: serial if present, usable and unique among ``all_serials`` (the cameras connected
    now; include this camera itself), else the port path. See the module docstring for the formats."""
    return camera_identity(vid, pid, serial, port_path, all_serials)["key"]


def assign_keys(cams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add ``key``/``key_kind``/``serial_reason`` to a list of camera dicts having vid, pid, serial, port_path.
    Uniqueness of serials is judged across the whole list."""
    trip = [(c.get("vid"), c.get("pid"), c.get("serial")) for c in cams]
    for c in cams:
        ident = camera_identity(c.get("vid"), c.get("pid"), c.get("serial"), c.get("port_path"), trip)
        c["key"], c["key_kind"], c["serial_reason"] = ident["key"], ident["key_kind"], ident["reason"]
    return cams
