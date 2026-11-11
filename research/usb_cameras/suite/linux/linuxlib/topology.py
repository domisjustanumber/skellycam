"""Linux USB topology collector: sysfs -> the OS-neutral snapshot of common/topology_model.py.

No root, no device open, no USB traffic: everything is read from /sys (all attributes used are mode 0444).
Design: results/agent_reports/plan_20261106/topology_linux.md section 9, with its verifier's corrections:

- buses are grouped by their PCI (or platform) parent: an xHCI controller registers a USB 2.0 root hub and a USB 3
  root hub (the shared HCD), so one controller has two 'halves';
- ports come from ``<hub>/<hub>:1.0/<hub>-portK``: connect_type, peer (USB 2.0 <-> USB 3 companion), location,
  connector (USB-C, 5.17+), physical_location (5.19+), firmware_node/path (ACPI HSnn/SSnn), state, disable;
- the kernel never peers ports across controllers, so USB 2.0 and USB 3 halves with the same non-zero
  ``location`` are merged here (Intel TCSS / Thunderbolt USB-C: SS lanes on one xHCI, USB 2.0 pins on the PCH);
- the observed load of a device is each interface's CURRENT ``bAlternateSetting`` looked up in the cached
  ``descriptors`` blob, NOT ``ep_XX/wMaxPacketSize`` (that attribute drops the high-bandwidth multiplier bits and
  ``ep_XX/interval`` is a decoded string; verifier errors 1 and 2);
- an all-zero ACPI _PLD reads back as panel=top, vertical=upper, horizontal=left: treated as 'no label'.

IDs (stable across boots: bus numbers are not used):
    controller  PCI address or platform device name, e.g. '0000:00:14.0'
    port        'port:<controller>|<usb2|usb3>|<chain>', chain = '13' (root port) or '13.1.4' (hub port)
    device      'dev:<controller>|<usb2|usb3>|<devpath>'
"""
from __future__ import annotations

import datetime as _dt
import os
import re
from pathlib import Path
from typing import Any

from sysfs import (P, SPEED_NAMES, descriptor_summary, discover_cameras, link_name, rd, rd_int, unroot)

VENDORS = {"8086": "Intel", "1022": "AMD", "1b21": "ASMedia", "1912": "Renesas", "1106": "VIA", "1b73": "Fresco",
           "1b6f": "Etron", "14c3": "MediaTek", "106b": "Apple", "10de": "NVIDIA", "1d6a": "Aquantia",
           "17a0": "Genesys", "1033": "NEC"}
CONNECT_TYPE = {"hotplug": "user", "hardwired": "internal", "not used": "not_used", "unknown": "unknown"}
PCI_IDS_PATHS = ("/usr/share/hwdata/pci.ids", "/usr/share/misc/pci.ids", "/usr/share/pci.ids")


def _half(speed: str | None) -> str:
    try:
        return "usb3" if float(speed or 0) >= 5000 else "usb2"
    except ValueError:
        return "unknown"


def pci_names(ids: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """Look up (vendor, device) names in pci.ids (no subprocess, no root). Missing file -> {}."""
    want_v = {v for v, _ in ids}
    out: dict[tuple[str, str], str] = {}
    for path in PCI_IDS_PATHS:
        p = P(path)
        if not p.exists():
            continue
        cur_v, vname = None, None
        try:
            with p.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip() or line.startswith("#"):
                        continue
                    if not line.startswith("\t"):
                        m = re.match(r"([0-9a-fA-F]{4})\s+(.*)", line)
                        if m:
                            cur_v = m.group(1).lower() if m.group(1).lower() in want_v else None
                            vname = m.group(2).strip()
                        elif line.startswith("C "):
                            break  # device classes section
                        continue
                    if cur_v and not line.startswith("\t\t"):
                        m = re.match(r"\t([0-9a-fA-F]{4})\s+(.*)", line)
                        if m and (cur_v, m.group(1).lower()) in ids:
                            out[(cur_v, m.group(1).lower())] = f"{vname} {m.group(2).strip()}"
        except OSError:
            continue
        break
    return out


def _controller_record(cdir: Path) -> dict[str, Any]:
    name = cdir.name
    ven = (rd(cdir / "vendor") or "").lower().replace("0x", "")
    dev = (rd(cdir / "device") or "").lower().replace("0x", "")
    cls = (rd(cdir / "class") or "").lower()
    driver = link_name(cdir / "driver")
    subsystem = link_name(cdir / "subsystem")
    kind = "unknown"
    if cls.startswith("0x0c0330") or (driver or "").startswith("xhci"):
        kind = "xhci"
    elif cls.startswith("0x0c0320") or "ehci" in (driver or ""):
        kind = "ehci"
    elif cls.startswith("0x0c0310") or "ohci" in (driver or ""):
        kind = "ohci"
    elif cls.startswith("0x0c0300") or "uhci" in (driver or ""):
        kind = "uhci"
    elif driver and "dwc2" in driver:
        kind = "dwc2"
    if driver and "mtk" in driver:
        kind = "xhci-mtk"
    vendor = VENDORS.get(ven) or ("MediaTek" if kind == "xhci-mtk" else None)
    pci_hops = sum(1 for part in cdir.parts if re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", part))
    return {"id": name, "name": None, "pci_id": (f"{ven.upper()}:{dev.upper()}" if ven and dev else None),
            "vendor": vendor or (ven or None), "kind": kind, "policy_hint": None, "driver": driver,
            "subsystem": subsystem, "pci_class": cls or None, "sysfs": unroot(cdir), "pci_hops": pci_hops,
            "behind_bridge": pci_hops > 1, "buses": {}}


def _pld_labels(port_dir: Path) -> dict[str, Any]:
    pl = port_dir / "physical_location"
    if not pl.is_dir():
        return {}
    v = {k: rd(pl / k) for k in ("panel", "vertical_position", "horizontal_position", "dock", "lid")}
    out: dict[str, Any] = {"pld_raw": v}
    all_zero = (v.get("panel") == "top" and v.get("vertical_position") == "upper"
                and v.get("horizontal_position") == "left" and v.get("dock") in ("no", None)
                and v.get("lid") in ("no", None))
    if all_zero:
        out["pld_all_zero"] = True
        return out
    if v.get("panel") and v["panel"] != "unknown":
        out["panel"] = v["panel"]
        pos = " ".join(x for x in (v.get("vertical_position"), v.get("horizontal_position"))
                       if x and x not in ("unknown",))
        if pos:
            out["position_text"] = pos
    if v.get("dock") == "yes":
        out["dock"] = True
    if v.get("lid") == "yes":
        out["lid"] = True
    return out


def collect_snapshot(cameras: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build the topology snapshot (common/topology_model.py schema) plus Linux extras. Never raises for a missing
    attribute: absent data becomes None/'unknown'."""
    warnings: list[str] = []
    controllers: dict[str, dict[str, Any]] = {}
    bus_map: dict[str, tuple[str, str, str]] = {}   # busnum -> (controller id, half, root hub dir)
    roots = []
    for rh in sorted(P("/sys/bus/usb/devices").glob("usb*"), key=lambda p: int(re.sub(r"\D", "", p.name) or 0)):
        try:
            rdir = rh.resolve(strict=True)
        except OSError:
            continue
        busnum = rd(rdir / "busnum") or re.sub(r"\D", "", rh.name)
        speed = rd(rdir / "speed")
        cdir = rdir.parent
        c = controllers.get(cdir.name) or _controller_record(cdir)
        controllers[cdir.name] = c
        half = _half(speed)
        c["buses"][half if half not in c["buses"] else f"{half}_{busnum}"] = int(busnum)
        bus_map[busnum] = (cdir.name, half, str(rdir))
        roots.append({"busnum": busnum, "dir": rdir, "speed": speed, "half": half, "controller": cdir.name,
                      "maxchild": rd_int(rdir / "maxchild"), "product": rd(rdir / "product"),
                      "version": (rd(rdir / "version") or "").strip()})
    names = pci_names({tuple(c["pci_id"].lower().split(":")) for c in controllers.values() if c.get("pci_id")})
    for c in controllers.values():
        if c.get("pci_id"):
            c["name"] = names.get(tuple(c["pci_id"].lower().split(":")))
        if not c["name"]:
            c["name"] = f"{c['vendor'] or 'unknown vendor'} {c['kind']} controller" + (
                f" {c['pci_id']}" if c.get("pci_id") else "") + f" ({c['id']})"

    # ---- devices
    dev_dirs: dict[str, Path] = {}
    for d in P("/sys/bus/usb/devices").iterdir() if P("/sys/bus/usb/devices").is_dir() else []:
        if re.fullmatch(r"\d+-[\d.]+", d.name):
            try:
                dev_dirs[d.name] = d.resolve(strict=True)
            except OSError:
                continue

    def dev_id(name: str) -> str | None:
        bus, devpath = name.split("-", 1)
        if bus not in bus_map:
            return None
        ctrl, half, _ = bus_map[bus]
        return f"dev:{ctrl}|{half}|{devpath}"

    def port_id_for(bus: str, chain: str) -> str | None:
        if bus not in bus_map:
            return None
        ctrl, half, _ = bus_map[bus]
        return f"port:{ctrl}|{half}|{chain}"

    devices: list[dict[str, Any]] = []
    dev_by_dir: dict[str, str] = {}
    for name, ddir in sorted(dev_dirs.items()):
        did = dev_id(name)
        if did is None:
            warnings.append(f"{name}: bus not found among root hubs")
            continue
        bus, devpath = name.split("-", 1)
        ctrl, half, _ = bus_map[bus]
        speed = SPEED_NAMES.get(rd(ddir / "speed") or "", "unknown")
        raw = None
        try:
            raw = (ddir / "descriptors").read_bytes()
        except OSError:
            pass
        desc = descriptor_summary(raw, speed)
        maxchild = rd_int(ddir / "maxchild") or 0
        dclass = rd(ddir / "bDeviceClass")
        is_hub = maxchild > 0 or dclass == "09"
        proto = rd(ddir / "bDeviceProtocol")
        hub_tt = None
        if is_hub and speed == "HS":
            hub_tt = {"01": "single", "02": "multi"}.get(proto or "", "single")
        pipes, pipe_notes = _periodic_pipes(ddir, desc)
        parent = None
        if "." in devpath:
            parent = f"dev:{ctrl}|{half}|{devpath.rsplit('.', 1)[0]}"
        rec = {"id": did, "vid": (rd(ddir / "idVendor") or "").lower(), "pid": (rd(ddir / "idProduct") or "").lower(),
               "serial": rd(ddir / "serial"), "name": rd(ddir / "product") or name, "speed": speed,
               "port_id": port_id_for(bus, devpath), "parent_device_id": parent, "is_hub": is_hub, "hub_tt": hub_tt,
               "controller_id": ctrl, "root_port_id": port_id_for(bus, devpath.split(".")[0]),
               "bcd_device": rd(ddir / "bcdDevice"), "periodic_pipes": pipes,
               # Linux extras
               "sysfs_name": name, "busnum": int(bus), "devnum": rd_int(ddir / "devnum"), "devpath": devpath,
               "bcd_usb": (rd(ddir / "version") or "").strip(), "removable": rd(ddir / "removable"),
               "manufacturer": rd(ddir / "manufacturer"), "maxchild": maxchild, "quirks": rd(ddir / "quirks"),
               "speed_downgraded": speed == "HS" and (rd(ddir / "version") or "").strip().startswith("3"),
               "pipe_notes": pipe_notes}
        devices.append(rec)
        dev_by_dir[str(ddir)] = did

    # ---- ports (root hubs and external hubs)
    ports: list[dict[str, Any]] = []
    port_by_dir: dict[str, str] = {}
    hubs: list[tuple[Path, str, str | None, str, str]] = []   # (hub dir, port name prefix, hub dev id, bus, chain0)
    for r in roots:
        hubs.append((r["dir"] / f"{r['busnum']}-0:1.0", f"usb{r['busnum']}-port", None, r["busnum"], ""))
    for name, ddir in sorted(dev_dirs.items()):
        if (rd_int(ddir / "maxchild") or 0) > 0:
            bus, devpath = name.split("-", 1)
            hubs.append((ddir / f"{name}:1.0", f"{name}-port", dev_id(name), bus, devpath))
    for idir, prefix, hub_id, bus, chain0 in hubs:
        if bus not in bus_map:
            continue
        ctrl, half, _ = bus_map[bus]
        pdirs = sorted(idir.glob(f"{prefix}*"), key=lambda p: int(re.sub(r"\D", "", p.name[len(prefix):]) or 0))
        for pdir in pdirs:
            try:
                k = int(pdir.name[len(prefix):])
            except ValueError:
                continue
            chain = f"{chain0}.{k}" if chain0 else str(k)
            pid = f"port:{ctrl}|{half}|{chain}"
            ct = rd(pdir / "connect_type")
            acpi = rd(pdir / "firmware_node" / "path")
            lp: dict[str, Any] = {}
            if acpi:
                lp["acpi_path"] = acpi
                lp["acpi_name"] = acpi.rsplit(".", 1)[-1]
            lp.update(_pld_labels(pdir))
            type_c = os.path.lexists(pdir / "connector")
            if type_c:
                lp["type_c"] = True
            ev = [e for e, ok in (("typec_connector", type_c), ("physical_location", "panel" in lp),
                                  ("acpi_name", bool(acpi))) if ok]
            if ev:
                lp["socket_evidence"] = ",".join(ev)
            lp["location_path"] = pdir.name
            loc = rd(pdir / "location")
            occ_dir = None
            if os.path.lexists(pdir / "device"):
                try:
                    occ_dir = str((pdir / "device").resolve(strict=True))
                except OSError:
                    occ_dir = None
            rec = {"id": pid, "controller_id": ctrl, "hub_device_id": hub_id, "port_number": k,
                   "path": unroot(pdir), "is_root_port": hub_id is None, "half": half, "companion_id": None,
                   "connectable": CONNECT_TYPE.get(ct or "", "unknown"),
                   "connector": "C" if type_c else ("internal" if ct == "hardwired" else "unknown"),
                   "label_parts": lp, "occupant_device_id": None, "_occ_dir": occ_dir,
                   "speed_max": "HS" if half == "usb2" else ("SS" if (bus_speed(roots, bus) or 0) <= 5000 else "SS+"),
                   # Linux extras
                   "sysfs_name": pdir.name, "connect_type": ct, "location": loc, "state": rd(pdir / "state"),
                   "disable": rd(pdir / "disable"), "over_current_count": rd_int(pdir / "over_current_count"),
                   "usb3_lpm_permit": rd(pdir / "usb3_lpm_permit"), "quirks": rd(pdir / "quirks"),
                   "_peer_dir": None}
            if os.path.lexists(pdir / "peer"):
                try:
                    rec["_peer_dir"] = str((pdir / "peer").resolve(strict=True))
                except OSError:
                    pass
            ports.append(rec)
            port_by_dir[str(pdir.resolve()) if pdir.exists() else str(pdir)] = pid
    for p in ports:
        if p["_occ_dir"]:
            p["occupant_device_id"] = dev_by_dir.get(p["_occ_dir"])
        if p["_peer_dir"]:
            p["companion_id"] = port_by_dir.get(p["_peer_dir"])
            if p["companion_id"]:
                p["companion_source"] = "peer"
    # merge USB 2.0 / USB 3 halves across controllers by equal non-zero ACPI location (verifier 'Missed' 1)
    by_loc: dict[str, list[dict[str, Any]]] = {}
    for p in ports:
        loc = (p.get("location") or "").lower()
        if loc and loc not in ("0x00000000", "0", "0x0"):
            by_loc.setdefault(loc, []).append(p)
    by_id = {p["id"]: p for p in ports}

    def unpaired_or_unused_peer(p: dict[str, Any]) -> bool:
        # A peer that is a 'not used' port (e.g. a Thunderbolt xHCI's empty USB 2.0 root hub, peered by port
        # number) is not the connector's real USB 2.0 half; the location match on another controller wins.
        c = by_id.get(p.get("companion_id"))
        return c is None or c.get("connectable") == "not_used"

    for loc, grp in by_loc.items():
        u2 = [p for p in grp if p["half"] == "usb2" and not p["companion_id"]]
        u3 = [p for p in grp if p["half"] == "usb3" and unpaired_or_unused_peer(p)]
        if len(u2) == 1 and len(u3) == 1:
            old = u3[0].get("companion_id")
            u2[0]["companion_id"], u3[0]["companion_id"] = u3[0]["id"], u2[0]["id"]
            u2[0]["companion_source"] = u3[0]["companion_source"] = "location" + (
                f" (replaces peer {old}, an unused port)" if old else "")
        elif u2 and u3:
            warnings.append(f"location {loc}: {len(u2)} USB 2.0 and {len(u3)} USB 3 ports unpaired (ambiguous)")
    for p in ports:
        comp = by_id.get(p.get("companion_id"))
        if comp is not None:
            p["label_parts"]["usb3_capable"] = True if p["half"] == "usb2" else p["label_parts"].get("usb3_capable")
            if comp["label_parts"].get("type_c") and not p["label_parts"].get("type_c"):
                p["label_parts"]["type_c"] = True
                p["connector"] = "C"
            for k in ("panel", "position_text"):
                if k in comp["label_parts"] and k not in p["label_parts"]:
                    p["label_parts"][k] = comp["label_parts"][k]
        p.pop("_occ_dir", None)
        p.pop("_peer_dir", None)

    cams = cameras if cameras is not None else discover_cameras()
    cam_recs = []
    dev_by_name = {d["sysfs_name"]: d["id"] for d in devices}
    for c in cams:
        streams = (c.get("descriptors") or {}).get("streams") or []
        alt_table = [{"alt": a["alt"], "max_packet": a["max_packet"], "mult": a["mult"]}
                     for a in (streams[0]["alt_table"] if streams else [])] or None
        vs = c.get("vs_interfaces") or []
        cam_recs.append({"key": c["key"], "device_id": dev_by_name.get(c["usb_name"]), "name": c["name"],
                         "is_kiyo": c["is_kiyo"], "alt_table": alt_table,
                         "current_alt": vs[0]["alt"] if vs else None,
                         "vid": c["vid"], "pid": c["pid"], "bcd_device": c.get("bcd_device"), "node": c["node"]})
    return {"os": "linux", "collected_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "controllers": sorted(controllers.values(), key=lambda c: c["id"]), "ports": ports,
            "devices": devices, "cameras": cam_recs,
            "buses": [{k: v for k, v in r.items() if k != "dir"} | {"sysfs": unroot(r["dir"])} for r in roots],
            "warnings": warnings,
            "notes": ["periodic_pipes = interfaces' current bAlternateSetting looked up in the cached descriptors "
                      "(ep_XX/wMaxPacketSize drops the multiplier bits)",
                      "root-only sources (debugfs port_bandwidth, ACPI tables) are not read"]}


def bus_speed(roots: list[dict[str, Any]], bus: str) -> float | None:
    for r in roots:
        if r["busnum"] == bus:
            try:
                return float(r["speed"])
            except (TypeError, ValueError):
                return None
    return None


def _periodic_pipes(ddir: Path, desc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Open periodic pipes now: for each interface, its current alt setting's iso/interrupt endpoints, taken from
    the parsed descriptors. Falls back to ep_XX attributes (multiplier unknown) when the descriptors don't parse."""
    pipes: list[dict[str, Any]] = []
    notes: list[str] = []
    table = {(i["number"], i["alt"]): i for i in (desc.get("interfaces") or [])}
    for itf in sorted(p for p in ddir.glob(f"{ddir.name}:*") if p.is_dir()):
        num = rd_int(itf / "bInterfaceNumber", 16)
        alt = rd_int(itf / "bAlternateSetting", 10)
        if num is None or alt is None:
            continue
        ent = table.get((num, alt))
        if ent is not None:
            for e in ent["endpoints"]:
                if e["type"] in ("iso", "int"):
                    pipes.append({"ep": e["ep"], "type": e["type"], "max_packet": e["max_packet"], "mult": e["mult"],
                                  "interval": e["interval"], "interface": num, "alt": alt})
            continue
        for ep in sorted(itf.glob("ep_*")):
            t = (rd(ep / "type") or "").lower()
            if not t.startswith(("isoc", "int")):
                continue
            mp = rd_int(ep / "wMaxPacketSize", 16) or 0
            pipes.append({"ep": f"0x{ep.name[3:]}", "type": "iso" if t.startswith("isoc") else "int",
                          "max_packet": mp & 0x7FF, "mult": 1, "interval": rd_int(ep / "bInterval", 16),
                          "interface": num, "alt": alt, "mult_unknown": True})
            notes.append(f"{itf.name}: descriptors unavailable for alt {alt}; ep_XX used (multiplier unknown)")
    return pipes, notes
