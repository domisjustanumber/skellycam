# /// script
# requires-python = ">=3.10"
# ///
"""Windows USB topology collector -> common.topology_model snapshot (plan section 5; contract 1 snapshot schema).

    python win_topology.py [--descriptors DESCRIPTORS.json] [--out SNAPSHOT.json] [--raw]

Stdlib + ctypes, no admin, and NO request to any device (topology_windows.md section 3.1):
  * controllers: CM interface list GUID_DEVINTERFACE_USB_HOST_CONTROLLER, devnode FriendlyName / LocationPaths /
    parent, HCD IOCTL_USB_GET_ROOT_HUB_NAME and USB_USER_REQUEST(GET_CONTROLLER_INFO_0) (read codes only);
  * every hub (GUID_DEVINTERFACE_USB_HUB) and EVERY port, empty ones included:
    IOCTL_USB_GET_NODE_INFORMATION / GET_HUB_INFORMATION_EX / GET_HUB_CAPABILITIES_EX,
    GET_NODE_CONNECTION_INFORMATION_EX (status, cached device descriptor, OPEN PIPES = current periodic load),
    GET_NODE_CONNECTION_INFORMATION_EX_V2 (port protocols, SuperSpeed / SuperSpeedPlus flags; the legacy Speed field
    says "high" for SuperSpeed devices), GET_PORT_CONNECTOR_PROPERTIES (user-connectable, Type-C, USB2<->USB3
    companion, including companions on another controller: Gerald's Thunderbolt USB-C ports);
  * devices: hub devnode children (Address = port), LocationPaths (PCI and ACPI forms), BusReportedDeviceDesc,
    DEVPKEY_Device_PhysicalDeviceLocation (_PLD), ContainerId; phantom devnodes for past-occupant history and
    ACPI port names of empty ports.
Code borrowed from results/agent_reports/plan_20261106/topology_windows_run/win_topology_probe.py and
bandwidth/win_usb_topology.py (via helpers/winpnp.py).

Camera alt tables need the configuration descriptor, which only a device request returns: helpers/win_descriptors.py
reads it (in a child process under camlock); pass its JSON with --descriptors to fill ``alt_table`` and
``current_alt``. Without it ``alt_table`` is None.

Verifier corrections applied (topology_windows.md / bandwidth_domain_model.md verifier notes):
  * halves are paired by the companion IOCTL, never by ContainerId (Genesys hubs share a fixed ContainerId);
  * all-zero _PLD panel/position defaults are dropped (C16); _PLD is trusted only from a devnode whose LocationPaths
    end at an ACPI(HSnn|SSnn) element (stale _PLD on serial devices, section 5);
  * TypeC=0 is never called "Type-A": connector "unknown" (section 5, missed item 5);
  * socket evidence = phantom history at the port, USB-C geometry in _PLD, or a _PLD user_visible bit (missed item 4);
    phantoms of internal-header devices (PSU, AIO, RGB/fan controllers, radios: topology_model.HEADER_DEVICE_PATTERNS)
    are header evidence and rank last, a hub port's _PLD user_visible and the _UPC Type-C flag are weak
    (label_parts.socket_evidence_level from topology_model.socket_evidence; multi_topo.md B14).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUITE_DIR = HERE.parents[1]
for _p in (str(HERE), str(SUITE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import winpnp as wp  # noqa: E402
from common import identity  # noqa: E402
from common import topology_model as tm  # noqa: E402

KIYO = ("1532", "0e05")


def _norm_link(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    s = re.sub(r"^\\\\[?.]\\", "", s)
    return s.lower()


def _pci_ids(iid: str) -> tuple[str | None, str | None]:
    u = (iid or "").upper()
    ven = u.split("VEN_")[1][:4].lower() if "VEN_" in u else None
    dev = u.split("DEV_")[1][:4].lower() if "DEV_" in u else None
    return ven, dev


def _speed_label(conn: dict) -> str:
    v2 = conn.get("v2_flags") or {}
    if v2.get("op_ssp"):
        return "SS+"
    if v2.get("op_ss"):
        return "SS"
    return {"low": "LS", "full": "FS", "high": "HS", "super": "SS"}.get(conn.get("legacy_speed"), "unknown")


def _half(conn: dict) -> str:
    pr = conn.get("port_protocols")
    if not pr:
        return "unknown"
    if "usb3" in pr and not any(p.startswith(("usb2", "usb1")) for p in pr):
        return "usb3"
    if "usb3" not in pr:
        return "usb2"
    return "unknown"


def _is_video_function(compat) -> bool:
    return any(str(c).upper().startswith(("USB\\CLASS_0E&SUBCLASS_01", "USB\\CLASS_0E&SUBCLASS_03"))
               for c in compat or [])


def _acpi_tail(acpi_path: str | None) -> list[str]:
    if not acpi_path:
        return []
    return re.findall(r"ACPI\(([^)]+)\)", acpi_path)


# =========================================================================================================== collect
def collect(descriptor_file: str | Path | None = None, descriptors: dict | None = None,
            include_raw: bool = False) -> dict:
    """Build the topology snapshot. ``descriptors`` (or the JSON in ``descriptor_file``) is win_descriptors.py's
    output and only feeds camera alt tables. Never raises on a single hub/port failure (recorded in errors)."""
    t0 = time.perf_counter()
    errors: list[str] = []
    if descriptors is None and descriptor_file:
        try:
            descriptors = json.loads(Path(descriptor_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            errors.append(f"descriptor file: {e}")
    desc_by_iid = {str(d.get("instance_id", "")).upper(): d for d in (descriptors or {}).get("devices", [])}

    # ---------------------------------------------------------------- controllers
    controllers, ctrl_raw = [], []
    root_hub_to_ctrl: dict[str, str] = {}
    for path in wp.iface_list(wp.GUIDS["USB_HOST_CONTROLLER"]):
        iid = wp.iface_instance(path)
        dn = wp.locate(iid) if iid else None
        props = wp.devnode_props(dn, ["DeviceDesc", "FriendlyName", "Manufacturer", "LocationInfo", "LocationPaths",
                                      "Service"]) if dn else {}
        pdn = wp.parent(dn) if dn else None
        parent_desc = wp.devnode_prop(pdn, "DeviceDesc") if pdn else None
        ven, dev = _pci_ids(iid or "")
        rec = {"interface": path, "instance_id": iid, "props": props, "parent_desc": parent_desc}
        h, err = wp.open_path(path)
        root_hub = None
        if h is not None:
            try:
                root_hub = wp.usb_name(h, 258, b"", 4)   # IOCTL_USB_GET_ROOT_HUB_NAME (HCD)
                r = wp.user_request(h, 1, 24)
                if r.get("payload") is not None and r.get("status") == "UsbUserSuccess":
                    import struct
                    v, d, rev, nports, flavor, feat = struct.unpack_from("<IIIIII", r["payload"])
                    rec["controller_info_0"] = {"PciVendorId": f"{v:04x}", "PciDeviceId": f"{d:04x}",
                                                "PciRevision": rev, "NumberOfRootPorts": nports,
                                                "ControllerFlavor": flavor, "HcFeatureFlags": hex(feat)}
            finally:
                wp.close(h)
        else:
            rec["open_error"] = err
        rec["root_hub_name"] = root_hub
        if root_hub:
            root_hub_to_ctrl[_norm_link(root_hub)] = iid
        name = props.get("FriendlyName") or props.get("DeviceDesc")
        nm = (name or "").lower()
        kind = "ehci" if "enhanced" in nm or "ehci" in nm else ("xhci" if "extensible" in nm or
                                                                props.get("Service", "").upper() == "USBXHCI"
                                                                else "unknown")
        controllers.append({
            "id": iid, "name": name, "pci_id": f"{ven}:{dev}" if ven and dev else None, "vendor": ven,
            "kind": kind, "policy_hint": None,
            "location_info": props.get("LocationInfo"),
            "location_paths": props.get("LocationPaths"),
            "parent_desc": parent_desc,
            "behind_pcie_switch": bool(parent_desc and "switch" in parent_desc.lower()),
            "number_of_root_ports_info0": (rec.get("controller_info_0") or {}).get("NumberOfRootPorts"),
            "root_hub_interface": root_hub,
        })
        ctrl_raw.append(rec)

    # ---------------------------------------------------------------- hubs and ports
    hubs = []
    hub_by_link: dict[str, dict] = {}
    hub_by_iid: dict[str, dict] = {}
    for path in wp.iface_list(wp.GUIDS["USB_HUB"]):
        iid = wp.iface_instance(path)
        dn = wp.locate(iid) if iid else None
        if dn:  # the devnode's own InstanceId (interface properties may differ in case from device IDs)
            iid = wp.instance_id(dn) or iid
        hub = {"interface": path, "instance_id": iid, "dn": dn, "is_root": bool(iid and "ROOT_HUB" in iid.upper())}
        if dn:
            hub["props"] = wp.devnode_props(dn, ["LocationPaths", "BusReportedDeviceDesc", "DeviceDesc", "Address",
                                                 "PhysicalDeviceLocation", "ContainerId"], status=False)
            # controller: walk parents to the PCI/ACPI host controller
            cur, ctrl = dn, None
            for _ in range(16):
                cur = wp.parent(cur)
                if cur is None:
                    break
                pid = wp.instance_id(cur) or ""
                if pid.upper().startswith(("PCI\\", "ACPI\\")):
                    ctrl = pid
                    break
            hub["controller_id"] = ctrl
            # children devnodes by Address
            kids = {}
            for c in wp.children(dn):
                a = wp.devnode_prop(c, "Address")
                if a is not None:
                    kids[int(a)] = c
            hub["children_by_port"] = kids
        h, err = wp.open_path(path)
        if h is None:
            hub["open_error"] = err
            errors.append(f"open hub {iid}: winerror {err}")
            hub["ports"] = []
        else:
            try:
                hub.update(wp.hub_node_info(h))
                ports = []
                for p in range(1, int(hub.get("n_ports") or 0) + 1):
                    try:
                        ci = wp.connection_info(h, p)
                        ci["connector"] = wp.port_connector(h, p)
                    except Exception as e:  # noqa: BLE001
                        ci = {"port": p, "error": repr(e)}
                        errors.append(f"hub {iid} port {p}: {e!r}")
                    ports.append(ci)
                hub["ports"] = ports
            finally:
                wp.close(h)
        hubs.append(hub)
        hub_by_link[_norm_link(path)] = hub
        if iid:
            hub_by_iid[iid.upper()] = hub

    # ---------------------------------------------------------------- phantom history + ACPI port names
    present_or_phantom = []
    for iid in wp.id_list("USB", present_only=False):
        if "&MI_" in iid.upper():
            continue
        dn = wp.locate(iid, phantom=True)
        if dn is None:
            continue
        pr = wp.devnode_props(dn, ["LocationPaths", "IsPresent", "BusReportedDeviceDesc", "DeviceDesc",
                                   "PhysicalDeviceLocation", "LastArrivalDate"], status=False)
        present_or_phantom.append({"instance_id": iid, **pr})
    loc_to_acpi: dict[str, str] = {}      # PCI-form location path of a root port -> ACPI name (HS13)
    history: dict[str, list] = {}         # PCI-form port location path -> past occupants (phantoms)
    pld_by_loc: dict[str, dict] = {}      # trusted _PLD per port location path
    for d in present_or_phantom:
        locs = d.get("LocationPaths") or []
        pci = next((x for x in locs if x.upper().startswith("PCIROOT")), None)
        acpi = next((x for x in locs if x.upper().startswith("ACPI(")), None)
        if pci and acpi:
            m = re.match(r"^(.*?#USBROOT\(\d+\))#USB\((\d+)\)", pci)
            tail = _acpi_tail(acpi)
            if m and "RHUB" in [t.upper() for t in tail]:
                i = [t.upper() for t in tail].index("RHUB")
                if i + 1 < len(tail):
                    loc_to_acpi[f"{m.group(1)}#USB({m.group(2)})".upper()] = tail[i + 1]
            pld = d.get("PhysicalDeviceLocation")
            if isinstance(pld, dict) and acpi.rstrip().endswith(")") and re.search(r"ACPI\([^)]+\)$", acpi):
                dec = wp.decode_pld(pld.get("hex"))
                if dec:
                    pld_by_loc[pci.upper()] = dec
        if pci and not d.get("IsPresent"):
            nm = d.get("BusReportedDeviceDesc") or d.get("DeviceDesc")
            # header_device: a PSU / AIO / RGB / radio phantom marks an internal header, not a socket (B14)
            history.setdefault(pci.upper(), []).append(
                {"instance_id": d["instance_id"], "name": nm, "header_device": tm.is_header_device_name(nm)})

    # ---------------------------------------------------------------- build ports/devices
    ports, devices = [], []
    port_by_key: dict[tuple, dict] = {}
    dev_by_iid: dict[str, dict] = {}
    hub_locs: dict[str, str] = {}
    for hub in hubs:
        locs = (hub.get("props") or {}).get("LocationPaths") or []
        hub_locs[(hub.get("instance_id") or "").upper()] = next(
            (x for x in locs if x.upper().startswith("PCIROOT")), None)

    def port_id(hub_iid: str, n: int) -> str:
        return f"{hub_iid}#{n}"

    for hub in hubs:
        hiid = hub.get("instance_id") or hub["interface"]
        ctrl = hub.get("controller_id")
        hloc = hub_locs.get(hiid.upper())
        for ci in hub.get("ports", []):
            n = ci.get("port")
            con = ci.get("connector") or {}
            pid = port_id(hiid, n)
            ploc = f"{hloc}#USB({n})" if hloc else None
            half = _half(ci)
            uc = con.get("user_connectable")
            type_c = bool(con.get("type_c"))
            lp: dict = {}
            acpi = loc_to_acpi.get(ploc.upper()) if (ploc and hub["is_root"]) else None
            if acpi:
                lp["acpi_name"] = acpi
            if type_c:
                lp["type_c"] = True
            if ploc:
                lp["location_path"] = ploc
            pld = pld_by_loc.get(ploc.upper()) if ploc else None
            ev = []
            if pld:
                lp["pld"] = {k: pld.get(k) for k in ("panel", "vertical_position", "horizontal_position", "shape",
                                                     "group_token", "group_position", "user_visible", "width_mm",
                                                     "height_mm", "color_rgb", "ignore_color", "all_zero_defaults",
                                                     "position_all_zero")}
                if not pld.get("position_all_zero"):
                    lp["panel"] = pld.get("panel")
                    lp["vpos"] = pld.get("vertical_position")
                    lp["hpos"] = pld.get("horizontal_position")
                if pld.get("user_visible"):
                    lp["user_visible"] = True
                    # a hub port has no ACPI socket of its own: its _PLD user_visible is weak (verifier note 9)
                    ev.append("_PLD user_visible" if hub["is_root"] else "_PLD user_visible on a hub port (weak)")
                if pld.get("width_mm") and pld.get("height_mm") and pld.get("shape") == 1:
                    ev.append(f"_PLD receptacle {pld['width_mm']}x{pld['height_mm']} mm oval (USB-C geometry)")
            hist = history.get(ploc.upper(), []) if ploc else []
            user_h = sorted({h.get('name') or h['instance_id'] for h in hist if not h.get("header_device")})
            head_h = sorted({h.get('name') or h['instance_id'] for h in hist if h.get("header_device")})
            if user_h:
                ev.append("phantom history: " + ", ".join(user_h)[:200])
            if head_h:
                ev.append("phantom history of internal-header devices: " + ", ".join(head_h)[:200])
            if type_c:
                ev.append("Type-C connector flag (_UPC)")
            if ev:
                lp["socket_evidence"] = "; ".join(ev)
            occupied = ci.get("status") not in (None, "NoDeviceConnected")
            occ_iid = None
            if occupied:
                kdn = (hub.get("children_by_port") or {}).get(n)
                occ_iid = wp.instance_id(kdn) if kdn else None
                if not occ_iid:
                    occ_iid = f"unknown-device@{pid}"
            rec = {"id": pid, "controller_id": ctrl, "hub_device_id": None if hub["is_root"] else hiid,
                   "port_number": n,
                   "path": identity.port_path_from_windows_location_paths(ploc) if ploc else pid,
                   "is_root_port": hub["is_root"], "half": half, "companion_id": None,
                   "connectable": "user" if uc else ("internal" if uc is False else "unknown"),
                   "connector": "C" if type_c else ("internal" if uc is False else "unknown"),
                   "label_parts": lp, "occupant_device_id": occ_iid,
                   "speed_max": ("SS+" if (ci.get("v2_flags") or {}).get("ssp_capable") else "SS") if half == "usb3"
                   else ("HS" if half == "usb2" else None),
                   # extras
                   "connection_status": ci.get("status"), "hub_instance_id": hiid,
                   "port_protocols": ci.get("port_protocols"), "phantom_history": hist or None,
                   "_companion": (con.get("companion_hub"), con.get("companion_port"))}
            lp["socket_evidence_level"] = tm.socket_evidence(rec)["level"]  # strong / weak / header / None
            ports.append(rec)
            port_by_key[(hiid.upper(), n)] = rec
            if occupied:
                kdn = (hub.get("children_by_port") or {}).get(n)
                dprops = wp.devnode_props(kdn, ["LocationPaths", "BusReportedDeviceDesc", "DeviceDesc",
                                                "FriendlyName", "ContainerId", "Service",
                                                "LastArrivalDate"]) if kdn else {}
                is_hub = bool(ci.get("device_is_hub"))
                child_hub = hub_by_iid.get(occ_iid.upper()) if is_hub and occ_iid else None
                tt = None
                if child_hub is not None:
                    caps = child_hub.get("hub_caps_ex") or {}
                    tt = "multi" if caps.get("HubIsMultiTt") else "single"
                suffix = occ_iid.split("\\")[-1]
                pipes = []
                for pp in ci.get("open_pipes") or []:
                    if pp["type"] in ("iso", "interrupt"):
                        pipes.append({"ep": pp["ep"], "type": "iso" if pp["type"] == "iso" else "int",
                                      "max_packet": pp["max_packet"], "mult": pp["mult"],
                                      "interval": pp["bInterval"], "wMaxPacketSize": pp["wMaxPacketSize"]})
                dlocs = dprops.get("LocationPaths") or []
                drec = {"id": occ_iid, "vid": ci.get("vid"), "pid": ci.get("pid"),
                        "serial": suffix if ("&" not in suffix and ci.get("i_serial")) else None,
                        "name": dprops.get("BusReportedDeviceDesc") or dprops.get("FriendlyName") or
                        dprops.get("DeviceDesc"),
                        "speed": _speed_label(ci), "port_id": pid,
                        "parent_device_id": None if hub["is_root"] else hiid,
                        "is_hub": is_hub, "hub_tt": tt, "controller_id": ctrl, "root_port_id": None,
                        "bcd_device": ci.get("bcd_device"), "periodic_pipes": pipes,
                        # extras
                        "location_path": next((x for x in dlocs if x.upper().startswith("PCIROOT")), None),
                        "container_id": dprops.get("ContainerId"), "service": dprops.get("Service"),
                        "connection_status": ci.get("status"), "legacy_speed": ci.get("legacy_speed"),
                        "address": ci.get("address"), "last_arrival": dprops.get("LastArrivalDate"),
                        "problem_code": dprops.get("ProblemCode"), "dn_warn": dprops.get("warn"),
                        "all_open_pipes": ci.get("open_pipes"), "i_serial": ci.get("i_serial"),
                        "_dn": kdn}
                devices.append(drec)
                dev_by_iid[occ_iid.upper()] = drec

    # companions
    for p in ports:
        chub, cport = p.pop("_companion")
        if chub and cport:
            h = hub_by_link.get(_norm_link(chub))
            if h is not None:
                comp = port_by_key.get(((h.get("instance_id") or "").upper(), cport))
                if comp is not None:
                    p["companion_id"] = comp["id"]
                    if comp["half"] == "usb3":
                        p["label_parts"]["usb3_capable"] = True
    # infer ACPI names for root ports without history when the controller's known mapping is a constant offset
    by_ctrl: dict = {}
    for p in ports:
        if p["is_root_port"]:
            by_ctrl.setdefault(p["controller_id"], []).append(p)
    for ctrl, ps in by_ctrl.items():
        for half, prefix in (("usb2", "HS"), ("usb3", "SS")):
            offs = set()
            for p in ps:
                a = p["label_parts"].get("acpi_name")
                if p["half"] == half and a and a.upper().startswith(prefix) and a[2:].isdigit():
                    offs.add(p["port_number"] - int(a[2:]))
            if len(offs) == 1:
                off = offs.pop()
                for p in ps:
                    if p["half"] == half and not p["label_parts"].get("acpi_name") and p["port_number"] - off > 0:
                        p["label_parts"]["acpi_name"] = f"{prefix}{p['port_number'] - off:02d}"
                        p["label_parts"]["acpi_name_inferred"] = True
    # root port of every device
    port_idx = {p["id"]: p for p in ports}
    for d in devices:
        cur = port_idx.get(d["port_id"])
        seen = set()
        while cur is not None and not cur["is_root_port"] and cur["id"] not in seen:
            seen.add(cur["id"])
            hubdev = dev_by_iid.get((cur.get("hub_device_id") or "").upper())
            cur = port_idx.get(hubdev["port_id"]) if hubdev else None
        d["root_port_id"] = cur["id"] if cur else None

    # ---------------------------------------------------------------- cameras
    cam_devs = []
    for d in devices:
        dn = d.pop("_dn", None)
        if dn is None or d["is_hub"]:
            continue
        compat_all = []
        func, fname = None, None
        for c in [dn] + wp.children(dn):
            cp = wp.devnode_props(c, ["CompatibleIds", "InstanceId", "FriendlyName"], status=False)
            if _is_video_function(cp.get("CompatibleIds")):
                compat_all.append(cp.get("InstanceId"))
                if func is None:
                    func = cp.get("InstanceId")
                    fname = cp.get("FriendlyName")
        if func:
            cam_devs.append((d, func, fname))
    for d in devices:
        d.pop("_dn", None)
    cams = []
    for d, func, fname in cam_devs:
        cams.append({"vid": d["vid"], "pid": d["pid"], "serial": d["serial"],
                     "port_path": identity.port_path_from_windows_location_paths(d.get("location_path")),
                     "device_id": d["id"], "function_instance_id": func, "name": fname or d.get("name")})
    identity.assign_keys(cams)
    cameras = []
    for c in cams:
        d = dev_by_iid[c["device_id"].upper()]
        desc = desc_by_iid.get(c["device_id"].upper())
        alt_table = desc.get("alt_table") if desc else None
        cur_alt = None
        matched = None
        if alt_table is not None:
            cur_alt = 0
            for pp in d.get("all_open_pipes") or []:
                if pp["type"] != "iso":
                    continue
                raw = int(pp["wMaxPacketSize"], 16)
                for a in alt_table:
                    if a.get("ep") == pp["ep"] and a.get("wMaxPacketSize_raw") == raw and \
                            a.get("bInterval") == pp["bInterval"]:
                        cur_alt, matched = a["alt"], a
                        break
            if matched and d["speed"] in ("SS", "SS+"):
                # SuperSpeed open pipes carry only wMaxPacketSize; take bursts x mult from the matched alt
                for pipe in d["periodic_pipes"]:
                    if pipe["ep"] == matched.get("ep") and pipe["type"] == "iso":
                        pipe["mult"] = matched["mult"]
        cameras.append({"key": c["key"], "device_id": c["device_id"], "name": c.get("name"),
                        "is_kiyo": (d["vid"], d["pid"]) == KIYO,
                        "alt_table": [{k: a[k] for k in ("alt", "max_packet", "mult", "ep", "bInterval",
                                                         "bytes_per_interval", "interface") if k in a}
                                      for a in alt_table] if alt_table else None,
                        "current_alt": cur_alt, "function_instance_id": c["function_instance_id"],
                        "key_kind": c["key_kind"], "port_path": c["port_path"],
                        "alt_source": "descriptor" if alt_table else None,
                        "descriptor_errors": (desc or {}).get("errors")})
    snap = {"os": "windows", "collected_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "controllers": controllers, "ports": ports, "devices": devices, "cameras": cameras,
            "collector": {"tool": "suite/windows/helpers/win_topology.py", "elapsed_s":
                          round(time.perf_counter() - t0, 4), "elevated": wp.is_elevated(),
                          "n_hubs": len(hubs), "n_ports": len(ports), "n_devices": len(devices),
                          "n_phantom_or_present_devnodes": len(present_or_phantom),
                          "descriptors_used": bool(desc_by_iid), "errors": errors,
                          "requests_to_devices": 0,
                          "note": "cached hub-driver state and CfgMgr only; alt tables come from a separate "
                                  "descriptor read (win_descriptors.py) when given"}}
    if include_raw:
        snap["raw"] = {"controllers": ctrl_raw,
                       "hubs": [{k: v for k, v in h.items() if k not in ("dn", "children_by_port")} for h in hubs]}
    return snap


def observed_alts(snapshot: dict) -> dict:
    """{camera_key: {"current_alt", "device_id", "iso_pipes": [...]}} from a snapshot (alt needs descriptors)."""
    devs = {d["id"]: d for d in snapshot.get("devices", [])}
    out = {}
    for c in snapshot.get("cameras", []):
        d = devs.get(c["device_id"], {})
        out[c["key"]] = {"current_alt": c.get("current_alt"), "device_id": c["device_id"],
                         "iso_pipes": [p for p in d.get("periodic_pipes", []) if p.get("type") == "iso"]}
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Windows USB topology snapshot (no device requests)")
    ap.add_argument("--descriptors", default=None, help="win_descriptors.py JSON (camera alt tables)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--raw", action="store_true", help="also include raw controller/hub IOCTL data")
    a = ap.parse_args(argv)
    snap = collect(descriptor_file=a.descriptors, include_raw=a.raw)
    text = json.dumps(snap, indent=1, default=str)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
