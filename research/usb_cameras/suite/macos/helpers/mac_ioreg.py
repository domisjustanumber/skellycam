# /// script
# requires-python = ">=3.11"
# ///
"""macOS IORegistry USB topology collector -> the common topology snapshot (stdlib only; never opens a device).

Sources (topology_macos.md sections 2 and 4, with its verifier notes):
- ``ioreg -a -l -w0 -p IOService -r -c AppleUSBHostController``: every USB controller with its whole subtree
  (root ports -> IOUSBHostDevice -> hub driver -> hub ports -> devices -> IOUSBHostInterface). Plist, read with
  plistlib. Verifier design correction 1: enumerate controllers by the IOUSBHostFamily base class
  AppleUSBHostController (the AppleUSBXHCI name is unverified).
- Fallbacks when that query returns nothing: ``-r -c AppleUSBXHCI``, then ``-r -c AppleUSBHostPort`` +
  ``-r -c IOUSBHostDevice`` (controllers are then synthesised from the locationID bus byte).
- ``-r -c AppleHPM -d 1``: Apple-silicon physical port labels (``port-location`` such as "left-back",
  ``port-number``), joined to the controller's ``port-number`` (verifier refutation of C30; restorekit's method).
- ``-r -c IOPCIDevice -d 2``: the PCI vendor/device of PCIe xHCI controllers (Intel PCH, Thunderbolt, Fresco,
  ASMedia), found as the parent of an AppleUSBHostController-like child.

Facts used (doc/web, see topology_macos.md):
- locationID = 0xBBPPPPPP: BB controller ("bus") byte, then one nibble per hub tier, 0 terminates.
  The bus byte is NOT stable for hot-pluggable PCIe/Thunderbolt controllers (pitfall 3), so ``stable_port_path``
  names the controller by its registry name instead; the identity key keeps the common bus-byte form.
- USBSpeed (tIOUSBHostConnectionSpeed): 1 FS, 2 LS, 3 HS, 4 SS, 5 SS+ 10G, 6 SS+ 20G. Legacy "Device Speed":
  0 LS, 1 FS, 2 HS, 3 SS, 4 SS+, 5 SS+x2 (different numbering: pitfall 2).
- The port-number key changed in macOS 26 ("port" -> "usb-port-number" / "port-number"); the occupant's
  locationID nibble is the source of truth, the keys are fallbacks.
- port-status bits 0-3 = port type (0 standard, 1 captive, 2 internal, 3 accessory, 4 ExpressCard), bits 8-10 =
  connected speed. Not trusted alone on macOS 26+ (verifier correction 4): occupancy = has an IOUSBHostDevice child.
- UsbConnector = ACPI _UPC type (0 USB2 A, 3 USB3 A, 8/9/10 Type-C, 255 proprietary/internal).
- A USB-C connector that holds a charger or display has no USB child but is not free: messages must say
  "if nothing is plugged into it" (verifier correction 3); the snapshot marks Type-C ports ``maybe_occupied_by_non_usb``.
- The T2 iBridge bus (AppleUSBVHCIBCE) is virtual: its ports are marked internal and never suggested.

Usage (macOS): uv run --script mac_ioreg.py [--out snapshot.json] [--raw-dir DIR]
All functions that parse take already-loaded plist objects, so the unit tests run on any OS with fake trees.
"""
from __future__ import annotations

import argparse
import json
import plistlib
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
SUITE_DIR = HERE.parents[1]
if str(SUITE_DIR) not in sys.path:
    sys.path.insert(0, str(SUITE_DIR))

from common import identity  # noqa: E402

IOREG = "/usr/sbin/ioreg"
BASE = ["-a", "-l", "-w0", "-p", "IOService"]
QUERIES: dict[str, list[str]] = {
    "controllers": BASE + ["-r", "-c", "AppleUSBHostController"],
    "controllers_xhci": BASE + ["-r", "-c", "AppleUSBXHCI"],
    "ports": BASE + ["-r", "-c", "AppleUSBHostPort"],
    "devices": BASE + ["-r", "-c", "IOUSBHostDevice"],
    "interfaces": BASE + ["-r", "-c", "IOUSBHostInterface", "-d", "1"],
    "hpm": BASE + ["-r", "-c", "AppleHPM", "-d", "1"],
    "pci": BASE + ["-r", "-c", "IOPCIDevice", "-d", "2"],
}
KIYO_VIDPID = ("1532", "0e05")

USBSPEED_NEW = {0: "unknown", 1: "FS", 2: "LS", 3: "HS", 4: "SS", 5: "SS+", 6: "SS+"}
USBSPEED_LEGACY = {0: "LS", 1: "FS", 2: "HS", 3: "SS", 4: "SS+", 5: "SS+"}
PORT_STATUS_SPEED = {0: None, 1: "FS", 2: "LS", 3: "HS", 4: "SS", 5: "SS+", 6: "SS+"}
PORT_TYPES = {0: "standard", 1: "captive", 2: "internal", 3: "accessory", 4: "expresscard"}
UPC_CONNECTOR = {0: "A", 3: "A", 8: "C", 9: "C", 10: "C", 255: "internal"}
PCI_VENDORS = {"8086": "Intel", "1022": "AMD", "1b73": "Fresco Logic", "1b21": "ASMedia", "1912": "Renesas",
               "1106": "VIA", "106b": "Apple", "1033": "NEC/Renesas", "1b6f": "Etron"}

PORT_NUMBER_KEYS = ("port", "usb-port-number", "port-number", "PortNum")
CHILDREN = "IORegistryEntryChildren"


# ------------------------------------------------------------------------------------------------- raw collection
def run_ioreg(args: list[str], timeout_s: float = 30.0, runner: Callable | None = None) -> dict:
    """Run ioreg with a timeout (procutil when available). Returns {argv, rc, elapsed_s, stdout_bytes, error}."""
    argv = [IOREG, *args]
    t0 = time.monotonic()
    if runner is not None:
        r = runner(argv, timeout_s)
        return {"argv": argv, "rc": r.get("rc"), "elapsed_s": r.get("elapsed_s"),
                "stdout_bytes": r.get("stdout_bytes") or (r.get("stdout") or "").encode("utf-8", "replace"),
                "error": r.get("spawn_error") or ("timeout" if r.get("timed_out") else None)}
    import subprocess
    try:
        p = subprocess.run(argv, capture_output=True, timeout=timeout_s)
        return {"argv": argv, "rc": p.returncode, "elapsed_s": round(time.monotonic() - t0, 3),
                "stdout_bytes": p.stdout, "error": None if p.returncode == 0 else p.stderr.decode("utf-8", "replace")[:500]}
    except subprocess.TimeoutExpired:
        return {"argv": argv, "rc": None, "elapsed_s": round(time.monotonic() - t0, 3), "stdout_bytes": b"",
                "error": "timeout"}
    except OSError as e:
        return {"argv": argv, "rc": None, "elapsed_s": round(time.monotonic() - t0, 3), "stdout_bytes": b"",
                "error": repr(e)}


def load_plist(data: bytes) -> list[dict]:
    """ioreg -a output -> list of root dicts ([] when empty or unparsable)."""
    if not data or not data.strip():
        return []
    try:
        obj = plistlib.loads(data)
    except Exception:
        return []
    if isinstance(obj, dict):
        return [obj]
    return [x for x in obj if isinstance(x, dict)] if isinstance(obj, list) else []


def collect_raw(names: tuple[str, ...] = ("controllers", "hpm", "pci"), timeout_s: float = 30.0,
                runner: Callable | None = None) -> dict:
    """Run the ioreg queries; falls back to the other controller/port/device queries when 'controllers' is empty.
    Returns {"queries": {name: meta}, "plists": {name: [roots]}, "raw": {name: bytes}}."""
    out: dict[str, Any] = {"queries": {}, "plists": {}, "raw": {}}

    def one(name: str) -> None:
        r = run_ioreg(QUERIES[name], timeout_s, runner)
        b = r.pop("stdout_bytes", b"") or b""
        r["bytes"] = len(b)
        out["queries"][name] = r
        out["raw"][name] = b
        out["plists"][name] = load_plist(b)

    for n in names:
        one(n)
    if "controllers" in names and not out["plists"].get("controllers"):
        one("controllers_xhci")
        if not out["plists"].get("controllers_xhci"):
            one("ports")
            one("devices")
    return out


# ------------------------------------------------------------------------------------------------- value helpers
def as_int(v: Any) -> int | None:
    """OSData little-endian bytes, int, bool, or a decimal/hex string -> int."""
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, (bytes, bytearray)):
        if not v:
            return None
        return int.from_bytes(bytes(v[:8]), "little")
    if isinstance(v, str):
        s = v.strip()
        try:
            return int(s, 16) if s.lower().startswith("0x") else int(s)
        except ValueError:
            return None
    return None


def as_str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        s = bytes(v).split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
        return s or None
    s = str(v).strip()
    return s or None


def hex4(v: Any) -> str | None:
    i = as_int(v)
    return None if i is None else f"{i & 0xFFFF:04x}"


def tier_count(loc: int) -> int:
    """Number of port nibbles in a locationID (0 for a controller/bus-only value)."""
    n = 0
    for shift in range(20, -1, -4):
        if (loc >> shift) & 0xF == 0:
            break
        n += 1
    return n


def loc_nibbles(loc: int) -> list[int]:
    out = []
    for shift in range(20, -1, -4):
        v = (loc >> shift) & 0xF
        if v == 0:
            break
        out.append(v)
    return out


def child_location(parent_loc: int, port_number: int) -> int | None:
    """locationID of the port ``port_number`` below a hub/controller at ``parent_loc``."""
    t = tier_count(parent_loc)
    if t >= 6 or not (0 < port_number <= 15):
        return None
    return parent_loc | (port_number << (20 - 4 * t))


def parse_unique_id(uid: str | None) -> dict | None:
    """AVCaptureDevice.uniqueID of a USB camera = hex(locationID<<32 | VID<<16 | PID) (Apple forum 803759; FFmpeg).
    Parsed numerically, so the un-padded form ('0x2000000fd9009b') works."""
    if not uid:
        return None
    s = str(uid).strip()
    try:
        v = int(s, 16) if s.lower().startswith("0x") else (int(s, 16) if re.fullmatch(r"[0-9a-fA-F]{9,16}", s) else None)
    except ValueError:
        v = None
    if v is None or v <= 0xFFFFFFFF:
        return None
    loc, vid, pid = (v >> 32) & 0xFFFFFFFF, (v >> 16) & 0xFFFF, v & 0xFFFF
    return {"location_id": loc, "location_hex": f"0x{loc:08x}", "vid": f"{vid:04x}", "pid": f"{pid:04x}"}


def parse_model_id(model: str | None) -> dict | None:
    """'UVC Camera VendorID_1133 ProductID_2140' -> {'vid': '046d', 'pid': '085c'} (decimal numbers)."""
    if not model:
        return None
    m = re.search(r"VendorID_(\d+)\s+ProductID_(\d+)", str(model))
    if not m:
        return None
    return {"vid": f"{int(m.group(1)) & 0xFFFF:04x}", "pid": f"{int(m.group(2)) & 0xFFFF:04x}"}


def _cls(node: dict) -> str:
    return str(node.get("IOObjectClass") or node.get("IOClass") or "")


def _name(node: dict) -> str:
    return str(node.get("IORegistryEntryName") or node.get("IOName") or node.get("name") or _cls(node))


def _location_prop(node: dict) -> int | None:
    v = node.get("IORegistryEntryLocation")
    if isinstance(v, str):
        try:
            return int(v, 16)
        except ValueError:
            return None
    return as_int(v)


# ------------------------------------------------------------------------------------------------- classification
_PORT_CLASS_RE = re.compile(r"USB.*Port$")
_CTRL_CLASS_RE = re.compile(r"(XHCI|EHCI|OHCI|UHCI|VHCI)", re.I)


def classify(node: dict) -> str:
    """'interface' | 'device' | 'port' | 'controller' | 'other'."""
    c = _cls(node)
    has_vp = "idVendor" in node and "idProduct" in node
    if c in ("IOUSBHostInterface", "IOUSBInterface") or (has_vp and "bInterfaceNumber" in node
                                                         and "bDeviceClass" not in node):
        return "interface"
    if c in ("IOUSBHostDevice", "IOUSBDevice") or (has_vp and "locationID" in node and (
            "bDeviceClass" in node or "USBSpeed" in node or "Device Speed" in node)):
        return "device"
    if (_PORT_CLASS_RE.search(c) and "Controller" not in c) or ("port-status" in node and not has_vp):
        return "port"
    if "AppleUSBHostController" in c or (_CTRL_CLASS_RE.search(c) and "Port" not in c and not has_vp
                                         and "Hub" not in c):
        return "controller"
    return "other"


def controller_kind(cls: str, name: str) -> str:
    c, n = cls.lower(), name.lower()
    if "vhcibce" in c or "vhci" in c:
        return "t2_virtual"
    if re.match(r"applet\d+usbxhci", c) or n.startswith("usb-drd") or "drd" in n:
        return "dwc3-apple"
    if "ehci" in c:
        return "ehci"
    return "xhci"


# ------------------------------------------------------------------------------------------------- tree walk
class _Builder:
    def __init__(self) -> None:
        self.controllers: dict[str, dict] = {}
        self.ports: dict[str, dict] = {}
        self.devices: dict[str, dict] = {}
        self.interfaces: dict[str, list[dict]] = {}
        self.port_keys_seen: dict[str, int] = {}
        self.port_classes: dict[str, int] = {}
        self.port_status_values: list[int] = []
        self.warnings: list[str] = []

    # --- controllers
    def add_controller(self, node: dict, synthetic_bus: int | None = None) -> str:
        cls, name = _cls(node), _name(node)
        bus = None
        loc = as_int(node.get("locationID"))
        if loc is not None:
            bus = (loc >> 24) & 0xFF
        if bus is None:
            loc2 = _location_prop(node)
            if loc2 is not None and loc2 > 0xFFFFFF:
                bus = (loc2 >> 24) & 0xFF
        if bus is None:
            bus = synthetic_bus
        base = name if name and name != cls else cls or "controller"
        cid = base
        if cid in self.controllers:
            cid = f"{base}#{bus:02x}" if bus is not None else f"{base}#{len(self.controllers)}"
        kind = controller_kind(cls, name)
        self.controllers[cid] = {
            "id": cid, "name": None, "pci_id": None, "vendor": "Apple" if kind == "dwc3-apple" else None,
            "kind": kind, "policy_hint": None, "class": cls, "registry_name": name, "bus_byte": bus,
            "registry_entry_id": node.get("IORegistryEntryID"), "port_number_prop": as_int(node.get("port-number")),
            "revision": as_str(node.get("Revision")), "companion_controller": as_str(node.get("UsbCompanionControllerName")),
            "label": None,
        }
        return cid

    # --- ports
    def add_port(self, node: dict, ctrl_id: str, hub_dev_id: str | None, order: int) -> str:
        cls, name = _cls(node), _name(node)
        self.port_classes[cls] = self.port_classes.get(cls, 0) + 1
        for k in PORT_NUMBER_KEYS + ("UsbCPortNumber", "UsbCompanionPortNumber", "UsbConnector", "UsbConnectable",
                                     "port-status", "removable", "kUSBCompanionIndex", "usb-c-port-number"):
            if k in node:
                self.port_keys_seen[k] = self.port_keys_seen.get(k, 0) + 1
        num, num_src = None, None
        for k in PORT_NUMBER_KEYS:
            v = as_int(node.get(k))
            if v:
                num, num_src = v & 0xFF, k
                break
        status = as_int(node.get("port-status"))
        if status is not None:
            self.port_status_values.append(status)
        lc = _location_prop(node)
        pid = f"{ctrl_id}:{hub_dev_id or 'root'}:{name}#{order}"
        half = "unknown"
        low_c, low_n = cls.lower(), name.lower()
        if re.search(r"usb20|ehci|-hs\b|port-hs|^hs\d", low_c + " " + low_n) or "usb2" in low_c:
            half = "usb2"
        if re.search(r"usb30|usb40|usb3|-ss\b|port-ss|^ss\d", low_c + " " + low_n):
            half = "usb3"
        conn_raw = as_int(node.get("UsbConnector"))
        connector = UPC_CONNECTOR.get(conn_raw, "unknown") if conn_raw is not None else "unknown"
        if "typec" in low_c or "type-c" in low_n:
            connector = "C"
        connectable = "unknown"
        uc = node.get("UsbConnectable")
        if uc is not None:
            connectable = "user" if as_int(uc) else "not_used"
        ptype = None
        if status is not None and status <= 0xFFFF:
            t = status & 0xF
            ptype = PORT_TYPES.get(t)
            if ptype in ("internal", "captive") and connectable == "unknown":
                connectable = "internal"
        if conn_raw == 255:
            connectable = "internal"
        speed_now = PORT_STATUS_SPEED.get((status >> 8) & 0x7) if status is not None and status <= 0xFFFF else None
        acpi = name.upper() if re.fullmatch(r"(HS|SS|PR)\d{2}", name.upper()) else None
        self.ports[pid] = {
            "id": pid, "controller_id": ctrl_id, "hub_device_id": hub_dev_id, "port_number": num,
            "path": None, "is_root_port": hub_dev_id is None, "half": half, "companion_id": None,
            "connectable": connectable, "connector": connector,
            "label_parts": {k: v for k, v in {"acpi_name": acpi, "type_c": True if connector == "C" else None,
                                              "registry_name": name}.items() if v is not None},
            "occupant_device_id": None, "speed_max": {"usb2": "HS", "usb3": "SS"}.get(half),
            # extras (macOS specific)
            "class": cls, "registry_name": name, "port_number_source": num_src, "location_prop": lc,
            "port_status": status, "port_type": ptype, "status_speed": speed_now,
            "usbc_port_number": as_int(node.get("UsbCPortNumber")),
            "companion_port_number": as_int(node.get("UsbCompanionPortNumber")),
            "upc_connector": conn_raw, "removable": as_int(node.get("removable")),
            "location_id": None, "maybe_occupied_by_non_usb": None,
        }
        return pid

    # --- devices
    def add_device(self, node: dict, ctrl_id: str, port_id: str | None, parent_dev_id: str | None) -> str:
        loc = as_int(node.get("locationID"))
        did = f"loc:{loc:08x}" if loc is not None else f"dev:{node.get('IORegistryEntryID')}"
        if did in self.devices:
            return did  # ioreg -r can list a device twice (as its own root and nested); keep the first
        sp_new, sp_old = as_int(node.get("USBSpeed")), as_int(node.get("Device Speed"))
        speed = USBSPEED_NEW.get(sp_new) if sp_new is not None else (USBSPEED_LEGACY.get(sp_old) if sp_old is not None else "unknown")
        dclass, dproto = as_int(node.get("bDeviceClass")), as_int(node.get("bDeviceProtocol"))
        is_hub = dclass == 9
        serial = as_str(node.get("USB Serial Number")) or as_str(node.get("kUSBSerialNumberString"))
        product = as_str(node.get("USB Product Name")) or as_str(node.get("kUSBProductString")) or _name(node)
        vendor = as_str(node.get("USB Vendor Name")) or as_str(node.get("kUSBVendorString"))
        self.devices[did] = {
            "id": did, "vid": hex4(node.get("idVendor")), "pid": hex4(node.get("idProduct")), "serial": serial,
            "name": product, "speed": speed, "port_id": port_id, "parent_device_id": parent_dev_id,
            "is_hub": is_hub, "hub_tt": ({1: "single", 2: "multi"}.get(dproto) if is_hub else None),
            "controller_id": ctrl_id, "root_port_id": None,
            "bcd_device": hex4(node.get("bcdDevice")), "periodic_pipes": [],
            # extras
            "location_id": loc, "location_hex": f"0x{loc:08x}" if loc is not None else None,
            "port_path": identity.port_path_from_mac_location_id(loc) if loc is not None else None,
            "vendor_name": vendor, "usb_speed_raw": sp_new, "device_speed_raw": sp_old,
            "registry_entry_id": node.get("IORegistryEntryID"), "session_id": node.get("sessionID"),
            "usb_address": as_int(node.get("USB Address") or node.get("kUSBAddress")),
            "container_id": as_str(node.get("kUSBContainerID")) if not isinstance(node.get("kUSBContainerID"), bytes)
            else node["kUSBContainerID"].hex(),
            "current_configuration": as_int(node.get("kUSBCurrentConfiguration")),
            "busy_state": node.get("IOServiceBusyState"), "device_class": dclass, "device_protocol": dproto,
            "descriptor_props": {k: (v.hex() if isinstance(v, (bytes, bytearray)) else v)
                                 for k, v in node.items() if "escriptor" in k and isinstance(v, (bytes, bytearray))},
            "is_uvc": False, "interfaces": [],
        }
        return did

    def add_interface(self, node: dict, dev_id: str | None) -> None:
        if dev_id is None or dev_id not in self.devices:
            return
        itf = {"number": as_int(node.get("bInterfaceNumber")), "class": as_int(node.get("bInterfaceClass")),
               "subclass": as_int(node.get("bInterfaceSubClass")), "protocol": as_int(node.get("bInterfaceProtocol")),
               "alt": as_int(node.get("bAlternateSetting")), "num_endpoints": as_int(node.get("bNumEndpoints")),
               "registry_entry_id": node.get("IORegistryEntryID"),
               "clients": sorted({_cls(c) for c in node.get(CHILDREN, []) or [] if isinstance(c, dict)})}
        dev = self.devices[dev_id]
        if not any(i["number"] == itf["number"] and i["registry_entry_id"] == itf["registry_entry_id"]
                   for i in dev["interfaces"]):
            dev["interfaces"].append(itf)
        if itf["class"] == 14 and itf["subclass"] == 1:
            dev["is_uvc"] = True

    # --- walk
    def walk(self, node: dict, ctrl_id: str | None, port_id: str | None, dev_id: str | None, hub_dev_for_ports: str | None,
             order: int = 0) -> None:
        kind = classify(node)
        new_ctrl, new_port, new_dev, new_hub = ctrl_id, port_id, dev_id, hub_dev_for_ports
        if kind == "controller" and ctrl_id is None:
            new_ctrl = self.add_controller(node)
            new_port, new_dev, new_hub = None, None, None
        elif kind == "controller":
            # a controller nested under another (rare); treat as a new controller
            new_ctrl = self.add_controller(node)
            new_port, new_dev, new_hub = None, None, None
        elif kind == "port":
            if ctrl_id is None:
                ctrl_id = new_ctrl = self._synthetic_controller(node)
            new_port = self.add_port(node, ctrl_id, hub_dev_for_ports, order)
        elif kind == "device":
            if ctrl_id is None:
                ctrl_id = new_ctrl = self._synthetic_controller(node)
            new_dev = self.add_device(node, ctrl_id, port_id, dev_id)
            new_hub = new_dev  # ports found below a device belong to that device (hub)
            new_port = None
        elif kind == "interface":
            self.add_interface(node, dev_id)
        for i, ch in enumerate(node.get(CHILDREN, []) or []):
            if isinstance(ch, dict):
                self.walk(ch, new_ctrl, new_port, new_dev, new_hub, i)

    def _synthetic_controller(self, node: dict) -> str:
        loc = as_int(node.get("locationID"))
        if loc is None:
            loc = _location_prop(node) or 0
        bus = (loc >> 24) & 0xFF
        cid = f"bus{bus:02x}"
        if cid not in self.controllers:
            self.controllers[cid] = {"id": cid, "name": f"USB controller (bus {bus:02x})", "pci_id": None, "vendor": None,
                                     "kind": "unknown", "policy_hint": None, "class": None, "registry_name": None,
                                     "bus_byte": bus, "registry_entry_id": None, "port_number_prop": None,
                                     "revision": None, "companion_controller": None, "label": None, "synthetic": True}
        return cid


# ------------------------------------------------------------------------------------------------- post-processing
def _finish(b: _Builder, hpm: list[dict], pci: list[dict]) -> None:
    # devices on ports, occupants, port locations
    for d in b.devices.values():
        if d["port_id"] in b.ports:
            p = b.ports[d["port_id"]]
            if p["occupant_device_id"] is None:
                p["occupant_device_id"] = d["id"]
            loc = d.get("location_id")
            if loc is not None and loc_nibbles(loc):
                p["port_number"] = loc_nibbles(loc)[-1]
                p["port_number_source"] = "occupant locationID"
    # controller bus bytes from their devices when missing
    for c in b.controllers.values():
        if c.get("bus_byte") is None:
            locs = [d["location_id"] for d in b.devices.values() if d["controller_id"] == c["id"] and d.get("location_id")]
            if locs:
                c["bus_byte"] = (locs[0] >> 24) & 0xFF
    # port locationIDs and paths
    for p in b.ports.values():
        c = b.controllers.get(p["controller_id"]) or {}
        n = p["port_number"]
        loc = None
        if p["hub_device_id"] is None:
            if c.get("bus_byte") is not None and n:
                loc = (c["bus_byte"] << 24) | (n << 20)
        else:
            hub = b.devices.get(p["hub_device_id"])
            if hub and hub.get("location_id") is not None and n:
                loc = child_location(hub["location_id"], n)
        if loc is None and p.get("location_prop") and p["location_prop"] > 0xFFFFF:
            loc = p["location_prop"]
            if not n and loc_nibbles(loc):
                p["port_number"] = loc_nibbles(loc)[-1]
                p["port_number_source"] = "IORegistryEntryLocation"
        p["location_id"] = loc
        p["path"] = identity.port_path_from_mac_location_id(loc) if loc is not None else f"{p['controller_id']}/{p['registry_name']}"
        # half from the occupant's speed when the class/name did not say
        if p["half"] == "unknown" and p["occupant_device_id"]:
            sp = b.devices[p["occupant_device_id"]]["speed"]
            if sp in ("SS", "SS+"):
                p["half"] = "usb3"
            elif sp in ("HS", "FS", "LS"):
                p["half"] = "usb2"
        if p["connector"] == "C" and p["occupant_device_id"] is None:
            p["maybe_occupied_by_non_usb"] = True
        ctrl = b.controllers.get(p["controller_id"]) or {}
        if ctrl.get("kind") == "t2_virtual":
            p["connectable"] = "internal"
    # device root ports and periodic structure
    for d in b.devices.values():
        cur, seen = d, set()
        rp = None
        while cur is not None and cur["id"] not in seen:
            seen.add(cur["id"])
            port = b.ports.get(cur["port_id"])
            if port is None:
                break
            if port["is_root_port"]:
                rp = port["id"]
                break
            cur = b.devices.get(port["hub_device_id"])
        d["root_port_id"] = rp
    _pair_companions(b)
    _controller_labels(b, hpm, pci)


def _pair_companions(b: _Builder) -> None:
    """Pair USB 2.0 and USB 3 halves of one connector.

    Root ports: within one controller, by UsbCompanionPortNumber (either direction); on an Apple DRD controller
    with exactly one usb2 and one usb3 root port, those two. Across controllers (Intel TCSS / Thunderbolt) by
    UsbCompanionPortNumber + UsbCompanionControllerName when present. Hub ports: the two hub devices of one
    physical USB 3 hub are matched by kUSBContainerID, else by same VID and hub position (parent port path), and
    their ports by number (verifier design correction 5)."""
    by_parent: dict[tuple, list[dict]] = {}
    for p in b.ports.values():
        by_parent.setdefault((p["controller_id"], p["hub_device_id"]), []).append(p)
    for (cid, hub), plist in by_parent.items():
        u2 = [p for p in plist if p["half"] == "usb2"]
        u3 = [p for p in plist if p["half"] == "usb3"]
        for a in u2:
            for c in u3:
                if (a.get("companion_port_number") and a["companion_port_number"] == c.get("port_number")) or \
                        (c.get("companion_port_number") and c["companion_port_number"] == a.get("port_number")):
                    a["companion_id"], c["companion_id"] = c["id"], a["id"]
        ctrl = b.controllers.get(cid) or {}
        if hub is None and ctrl.get("kind") == "dwc3-apple" and len(u2) == 1 and len(u3) == 1 \
                and not u2[0]["companion_id"]:
            u2[0]["companion_id"], u3[0]["companion_id"] = u3[0]["id"], u2[0]["id"]
    # hub halves
    hubs = [d for d in b.devices.values() if d["is_hub"]]
    hs_hubs = [h for h in hubs if h["speed"] in ("HS", "FS", "unknown")]
    ss_hubs = [h for h in hubs if h["speed"] in ("SS", "SS+")]
    for h2 in hs_hubs:
        for h3 in ss_hubs:
            same = False
            if h2.get("container_id") and h2.get("container_id") == h3.get("container_id"):
                same = True
            elif h2.get("vid") == h3.get("vid"):
                p2, p3 = b.ports.get(h2["port_id"]), b.ports.get(h3["port_id"])
                if p2 and p3 and (p2.get("companion_id") == p3["id"] or p3.get("companion_id") == p2["id"]):
                    same = True
            if not same:
                continue
            h2.setdefault("companion_hub_id", h3["id"])
            h3.setdefault("companion_hub_id", h2["id"])
            ports2 = {p["port_number"]: p for p in b.ports.values() if p["hub_device_id"] == h2["id"]}
            ports3 = {p["port_number"]: p for p in b.ports.values() if p["hub_device_id"] == h3["id"]}
            for n, a in ports2.items():
                c = ports3.get(n)
                if c and not a["companion_id"] and not c["companion_id"]:
                    if a["half"] == "unknown":
                        a["half"] = "usb2"
                    if c["half"] == "unknown":
                        c["half"] = "usb3"
                    a["companion_id"], c["companion_id"] = c["id"], a["id"]


def _controller_labels(b: _Builder, hpm: list[dict], pci: list[dict]) -> None:
    # PCI parents: IOPCIDevice nodes whose child is one of our controllers (matched by registry name / class)
    pci_by_child: dict[str, dict] = {}
    for root in pci:
        for node in _iter_nodes(root):
            if classify(node) != "other" or "vendor-id" not in node:
                continue
            for ch in node.get(CHILDREN, []) or []:
                if isinstance(ch, dict) and classify(ch) == "controller":
                    pci_by_child[f"{_cls(ch)}|{_name(ch)}"] = node
                    pci_by_child.setdefault(f"id|{ch.get('IORegistryEntryID')}", node)
    for c in b.controllers.values():
        node = pci_by_child.get(f"id|{c.get('registry_entry_id')}") or pci_by_child.get(f"{c.get('class')}|{c.get('registry_name')}")
        if node is not None:
            ven, dev = as_int(node.get("vendor-id")), as_int(node.get("device-id"))
            if ven is not None and dev is not None:
                c["pci_id"] = f"{ven & 0xFFFF:04x}:{dev & 0xFFFF:04x}"
                c["vendor"] = PCI_VENDORS.get(f"{ven & 0xFFFF:04x}", c.get("vendor"))
                c["pci_name"] = _name(node)
        if c.get("vendor") is None:
            cl = (c.get("class") or "").lower()
            if "intel" in cl:
                c["vendor"] = "Intel"
            elif "fl1100" in cl or "fresco" in cl:
                c["vendor"] = "Fresco Logic"
            elif "asm" in cl:
                c["vendor"] = "ASMedia"
            elif cl.startswith("applet") or "apple" in cl and c.get("kind") == "dwc3-apple":
                c["vendor"] = "Apple"
        if c.get("kind") == "t2_virtual":
            c["policy_hint"] = "controller"
    # AppleHPM port-location labels (Apple silicon)
    hpm_by_num: dict[int, dict] = {}
    for root in hpm:
        for node in _iter_nodes(root):
            if "port-location" in node or "port-number" in node:
                n = as_int(node.get("port-number"))
                if n is not None:
                    hpm_by_num.setdefault(n, node)
    for c in b.controllers.values():
        n = c.get("port_number_prop")
        node = hpm_by_num.get(n) if n is not None else None
        if node is not None:
            c["label"] = as_str(node.get("port-location"))
            c["hpm_rid"] = as_int(node.get("RID"))
    for c in b.controllers.values():
        bits = []
        if c.get("kind") == "dwc3-apple":
            bits.append("Apple USB-C controller")
        elif c.get("kind") == "t2_virtual":
            bits.append("T2 internal (virtual) USB bus")
        elif c.get("vendor"):
            bits.append(f"{c['vendor']} USB controller")
        else:
            bits.append("USB controller")
        if c.get("registry_name"):
            bits.append(str(c["registry_name"]))
        extra = [x for x in (c.get("label") and f"port {c['label']}", c.get("pci_id") and c["pci_id"].upper()) if x]
        c["name"] = " ".join(bits) + (f" ({', '.join(extra)})" if extra else "")
        if c.get("label"):
            for p in b.ports.values():
                if p["controller_id"] == c["id"] and p["is_root_port"]:
                    p["label_parts"]["position_text"] = str(c["label"])
                    p["label_parts"]["friendly"] = f"USB-C port {c['label']}"


def _iter_nodes(root: dict):
    stack = [root]
    while stack:
        n = stack.pop()
        if not isinstance(n, dict):
            continue
        yield n
        stack.extend(x for x in (n.get(CHILDREN, []) or []) if isinstance(x, dict))


# ------------------------------------------------------------------------------------------------- public API
def build_snapshot(plists: dict[str, list[dict]], collected_utc: str | None = None,
                   alt_tables: dict[str, list[dict]] | None = None) -> dict:
    """Build the common topology snapshot from loaded ioreg plists.

    plists: {"controllers": [...]} (or "controllers_xhci", or "ports" + "devices"), optional "hpm", "pci".
    alt_tables: {"vid:pid:bcd": [{"alt","max_packet","mult"}]} from the descriptor cache (UVC VS alts), used for
    cameras' ``alt_table`` and their open periodic pipes (current alt from IOUSBHostInterface bAlternateSetting).
    Returns the snapshot with extra top-level keys "schema_report" and "warnings"."""
    b = _Builder()
    roots = plists.get("controllers") or plists.get("controllers_xhci") or []
    source = "controllers" if plists.get("controllers") else ("controllers_xhci" if roots else "ports+devices")
    for i, r in enumerate(roots):
        b.walk(r, None, None, None, None, i)
    if not roots:
        for i, r in enumerate(plists.get("ports") or []):
            b.walk(r, None, None, None, None, i)
        for i, r in enumerate(plists.get("devices") or []):
            b.walk(r, None, None, None, None, i)
        b.warnings.append("no AppleUSBHostController/AppleUSBXHCI objects found; controllers synthesised from the "
                          "locationID bus byte (labels and PCI vendor unavailable)")
    _finish(b, plists.get("hpm") or [], plists.get("pci") or [])
    cameras = []
    usb_cams = [d for d in b.devices.values() if d["is_uvc"]]
    trip = [(d["vid"], d["pid"], d["serial"]) for d in usb_cams]
    for d in usb_cams:
        ident = identity.camera_identity(d["vid"], d["pid"], d["serial"], d["port_path"], trip)
        vs = [i for i in d["interfaces"] if i["class"] == 14 and i["subclass"] == 2]
        vc = [i for i in d["interfaces"] if i["class"] == 14 and i["subclass"] == 1]
        cur_alt = max((i["alt"] for i in vs if i["alt"] is not None), default=None)
        akey = f"{d['vid']}:{d['pid']}:{d['bcd_device']}"
        table = None
        if alt_tables:
            table = alt_tables.get(akey) or next((v for k, v in alt_tables.items()
                                                   if k.startswith(f"{d['vid']}:{d['pid']}:")), None)
        if table and cur_alt:
            ent = next((a for a in table if a.get("alt") == cur_alt), None)
            if ent:
                d["periodic_pipes"] = [{"ep": ent.get("ep"), "type": "iso", "max_packet": ent["max_packet"],
                                        "mult": ent.get("mult") or 1, "interval": ent.get("interval", 1)}]
        cameras.append({"key": ident["key"], "device_id": d["id"], "name": d["name"],
                        "is_kiyo": (d["vid"], d["pid"]) == KIYO_VIDPID, "alt_table": table, "current_alt": cur_alt,
                        # extras
                        "key_kind": ident["key_kind"], "serial_reason": ident["reason"], "vid": d["vid"],
                        "pid": d["pid"], "serial": d["serial"], "bcd_device": d["bcd_device"],
                        "location_id": d["location_id"], "location_hex": d["location_hex"],
                        "port_path": d["port_path"], "speed": d["speed"],
                        "vc_interface": vc[0]["number"] if vc else None,
                        "vs_interfaces": sorted({i["number"] for i in vs if i["number"] is not None}),
                        "registry_entry_id": d["registry_entry_id"], "session_id": d["session_id"]})
    for d in b.devices.values():
        if d["periodic_pipes"] == [] and not d["is_hub"] and any(i["class"] == 1 and i["subclass"] == 2 and i.get("alt")
                                                                  for i in d["interfaces"]):
            d["periodic_pipes_unknown"] = "USB audio streaming interface active; its reservation is unknown (no descriptors)"
    ctrl_stable = {c["id"]: c["id"] for c in b.controllers.values()}
    for cam in cameras:
        d = b.devices[cam["device_id"]]
        nib = loc_nibbles(d["location_id"]) if d.get("location_id") is not None else []
        cam["stable_port_path"] = f"{ctrl_stable.get(d['controller_id'], d['controller_id'])}/{'.'.join(map(str, nib))}"
    report = {
        "source": source, "port_classes": b.port_classes, "port_keys_seen": b.port_keys_seen,
        "port_status_values": sorted(set(b.port_status_values))[:64],
        "port_status_out_of_layout": sorted({s for s in b.port_status_values if s > 0xFFFF or (s & 0xF) > 4}),
        "port_number_sources": _count(p.get("port_number_source") for p in b.ports.values()),
        "controller_classes": _count(c.get("class") for c in b.controllers.values()),
        "hpm_labels": {c["id"]: c.get("label") for c in b.controllers.values() if c.get("label")},
        "n_controllers": len(b.controllers), "n_ports": len(b.ports), "n_devices": len(b.devices),
        "n_cameras": len(cameras),
        "n_empty_ports": sum(1 for p in b.ports.values() if p["occupant_device_id"] is None),
        "interfaces_with_alt_key": sum(1 for d in b.devices.values() for i in d["interfaces"] if i["alt"] is not None),
    }
    return {"os": "macos", "collected_utc": collected_utc or _utc(),
            "controllers": list(b.controllers.values()), "ports": list(b.ports.values()),
            "devices": list(b.devices.values()), "cameras": cameras,
            "schema_report": report, "warnings": b.warnings}


def _count(vals) -> dict:
    out: dict[str, int] = {}
    for v in vals:
        k = str(v)
        out[k] = out.get(k, 0) + 1
    return out


def _utc() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def interface_alts(plist_roots: list[dict], location_id: int) -> list[dict]:
    """From an ``ioreg -r -c IOUSBHostInterface -d 1`` dump: the VideoStreaming interfaces of the device with this
    locationID and their bAlternateSetting (whether this tracks the live alt is untested: topology_macos MT4)."""
    out = []
    for r in plist_roots:
        for node in _iter_nodes(r):
            if classify(node) != "interface":
                continue
            if as_int(node.get("locationID")) != location_id:
                continue
            if as_int(node.get("bInterfaceClass")) == 14:
                out.append({"number": as_int(node.get("bInterfaceNumber")),
                            "subclass": as_int(node.get("bInterfaceSubClass")),
                            "alt": as_int(node.get("bAlternateSetting")),
                            "num_endpoints": as_int(node.get("bNumEndpoints"))})
    return out


def interface_alts_from_devices(plist_roots: list[dict], location_id: int) -> list[dict]:
    """Same as interface_alts, but from an ``ioreg -r -c IOUSBHostDevice`` dump: the interfaces are the children of
    the device with this locationID (works even if IOUSBHostInterface carries no locationID property)."""
    for r in plist_roots:
        for node in _iter_nodes(r):
            if classify(node) != "device" or as_int(node.get("locationID")) != location_id:
                continue
            out = []
            kids = [c for c in node.get(CHILDREN, []) or [] if isinstance(c, dict)]
            # interfaces are normally direct children; also look one level below non-device nodes (driver nodes)
            kids += [g for c in kids if classify(c) == "other" for g in c.get(CHILDREN, []) or [] if isinstance(g, dict)]
            for ch in kids:
                if classify(ch) == "interface" and as_int(ch.get("bInterfaceClass")) == 14:
                    out.append({"number": as_int(ch.get("bInterfaceNumber")),
                                "subclass": as_int(ch.get("bInterfaceSubClass")),
                                "alt": as_int(ch.get("bAlternateSetting")),
                                "num_endpoints": as_int(ch.get("bNumEndpoints"))})
            return out
    return []


def read_interface_alts(location_id: int, timeout_s: float = 10.0, runner: Callable | None = None) -> dict:
    r = run_ioreg(QUERIES["interfaces"], timeout_s, runner)
    roots = load_plist(r.get("stdout_bytes") or b"")
    itfs = interface_alts(roots, location_id)
    out = {"elapsed_s": r.get("elapsed_s"), "error": r.get("error"), "interfaces": itfs, "source": "interfaces"}
    if not itfs:
        # IOUSBHostInterface may not carry locationID on every macOS version (unverified): use the device subtree
        r2 = run_ioreg(QUERIES["devices"], timeout_s, runner)
        out["interfaces"] = interface_alts_from_devices(load_plist(r2.get("stdout_bytes") or b""), location_id)
        out["source"] = "device subtree"
        out["error_devices_query"] = r2.get("error")
    return out


def device_states(plist_roots: list[dict]) -> dict[str, dict]:
    """locationID hex -> {registry_entry_id, session_id, vid, pid} for every IOUSBHostDevice (re-arrival check,
    plan 6.1: log the IORegistry entry ID per camera before and after each test)."""
    out = {}
    for r in plist_roots:
        for node in _iter_nodes(r):
            if classify(node) == "device":
                loc = as_int(node.get("locationID"))
                if loc is None:
                    continue
                out[f"0x{loc:08x}"] = {"registry_entry_id": node.get("IORegistryEntryID"),
                                       "session_id": node.get("sessionID"),
                                       "vid": hex4(node.get("idVendor")), "pid": hex4(node.get("idProduct"))}
    return out


def read_device_states(timeout_s: float = 15.0, runner: Callable | None = None) -> dict:
    r = run_ioreg(QUERIES["devices"], timeout_s, runner)
    return {"elapsed_s": r.get("elapsed_s"), "error": r.get("error"),
            "devices": device_states(load_plist(r.get("stdout_bytes") or b""))}


def collect_snapshot(timeout_s: float = 30.0, runner: Callable | None = None, raw_dir: Path | None = None,
                     alt_tables: dict | None = None) -> dict:
    """Run the queries and build the snapshot. Raw plists go to raw_dir (outside the repo) when given."""
    raw = collect_raw(("controllers", "hpm", "pci", "interfaces"), timeout_s, runner)
    plists = dict(raw["plists"])
    snap = build_snapshot(plists, alt_tables=alt_tables)
    # interface alts from the dedicated query are more reliable than the subtree (depth-limited clients)
    for cam in snap["cameras"]:
        if cam.get("location_id") is None:
            continue
        alts = interface_alts(plists.get("interfaces") or [], cam["location_id"])
        vs = [a for a in alts if a.get("subclass") == 2 and a.get("alt") is not None]
        if vs and cam.get("current_alt") is None:
            cam["current_alt"] = max(a["alt"] for a in vs)
    snap["ioreg_queries"] = raw["queries"]
    if raw_dir is not None:
        raw_dir = Path(raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
        for k, v in raw["raw"].items():
            if v:
                (raw_dir / f"ioreg_{k}.plist").write_bytes(v)
        snap["raw_plists_dir"] = str(raw_dir)
    return snap


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--raw-dir", type=Path, default=None)
    ap.add_argument("--from-dir", type=Path, default=None, help="build from saved ioreg_*.plist files instead")
    a = ap.parse_args()
    if a.from_dir:
        plists = {p.stem.replace("ioreg_", ""): load_plist(p.read_bytes()) for p in a.from_dir.glob("ioreg_*.plist")}
        snap = build_snapshot(plists)
    else:
        if sys.platform != "darwin":
            print(json.dumps({"ok": False, "error": "ioreg exists only on macOS; use --from-dir"}))
            return 2
        snap = collect_snapshot(raw_dir=a.raw_dir)
    text = json.dumps(snap, indent=1, default=str)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding="utf-8")
    print(json.dumps({"ok": True, "cameras": [c["key"] for c in snap["cameras"]], "report": snap["schema_report"]},
                     default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
