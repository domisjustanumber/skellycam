"""Gerald's USB layout on 2026-11-06 as a topology snapshot (test data, no device access).

Source: results/agent_reports/plan_20261106/topology_windows.md sections 2.1-2.4 (probe_20261106.json):
- chipset xHCI 8086:7A60: HS01-HS16 + SS01-SS09; HS07 = Logitech C930e; HS13 = Genesys 05E3:0610 (USB 2.0 half of
  the GL3523 dock hub) -> inner 05E3:0610 -> p2 generic USB Camera 4C4A:4A55, p4 C922 (serial C922SN01);
  outer p2 PreSonus Revelator, p3 Microchip 0424:2137 hub (Logitech receiver on p2); HS10 internal 05E3:0608 hub
  with 4 empty user ports; HS14 Intel Bluetooth (internal); HS15/16 USB 2.0-only.
- Thunderbolt 4 xHCI 8086:1138: ports 1-2 not used, port 3 (USB-C, companion HS12) empty, port 4 (companion HS13)
  = GL3523 SuperSpeed half 05E3:0625 -> p4 Razer Kiyo Pro 1532:0E05 at SuperSpeed.
Alt tables: bandwidth/domain_model_compare.py (read from topology_idle_0307Z.json). Mode -> alt: r02-r06 of
bw_concurrency_rerun_20261027 (bandwidth_domain_model.md section 3).
Instance ids here are synthetic labels, not the machine's.
"""
from __future__ import annotations

PCH = "PCI\\VEN_8086&DEV_7A60\\3&11583659&0&A0"
TB = "PCI\\VEN_8086&DEV_1138\\TB4"

C922_ALTS = {1: (192, 1), 2: (384, 1), 3: (512, 1), 4: (640, 1), 5: (800, 1), 6: (944, 1), 7: (640, 2), 8: (800, 2),
             9: (992, 2), 10: (896, 3), 11: (1020, 3)}
C930E_ALTS = dict(C922_ALTS) | {11: (1024, 3)}
GENERIC_ALTS = {1: (1023, 3)}

C922_KEY = "046d:085c:sn=C922SN01"
GENERIC_KEY = "4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2"
C930E_KEY = "046d:0843:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/7"
KIYO_KEY = "1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4"


def _alt_table(alts: dict) -> list[dict]:
    return [{"alt": a, "max_packet": mp, "mult": m} for a, (mp, m) in sorted(alts.items())]


def _port(pid, ctrl, num, *, hub=None, root=False, half="usb2", comp=None, conn="unknown", connectable="user",
          occ=None, acpi=None, type_c=False):
    lp = {}
    if acpi:
        lp["acpi_name"] = acpi
    if type_c:
        lp["type_c"] = True
    return {"id": pid, "controller_id": ctrl, "hub_device_id": hub, "port_number": num,
            "path": f"{ctrl}/{pid}", "is_root_port": root, "half": half, "companion_id": comp,
            "connectable": connectable, "connector": "C" if type_c else conn, "label_parts": lp,
            "occupant_device_id": occ, "speed_max": "HS" if half == "usb2" else "SS"}


def _dev(did, vid, pid, name, speed, port_id, parent, ctrl, root_port, *, hub=False, tt=None, serial=None,
         bcd=None, pipes=None):
    return {"id": did, "vid": vid, "pid": pid, "serial": serial, "name": name, "speed": speed, "port_id": port_id,
            "parent_device_id": parent, "is_hub": hub, "hub_tt": tt, "controller_id": ctrl,
            "root_port_id": root_port, "bcd_device": bcd, "periodic_pipes": pipes or []}


def build_snapshot(streaming: dict | None = None) -> dict:
    """The 2026-11-06 layout with every camera idle. ``streaming`` = {camera_key: alt} adds that camera's open
    isochronous pipe (as the hub IOCTL would show while it streams)."""
    ports, devices = [], []
    # ---- chipset root ports
    occupants = {3: "dymo", 7: "c930e", 8: "mstx", 10: "hub0608", 11: "aura", 13: "hub0610o", 14: "bt"}
    internal = {10, 11, 14}
    for n in range(1, 17):
        comp = f"pch:SS{n:02d}" if n <= 9 else ({12: "tb:4p3", 13: "tb:4p4"}.get(n))
        ports.append(_port(f"pch:HS{n:02d}", PCH, n, root=True, comp=comp, acpi=f"HS{n:02d}",
                           connectable="internal" if n in internal else "user", occ=occupants.get(n),
                           type_c=n in (9, 12, 13)))
    for k in range(1, 10):
        ports.append(_port(f"pch:SS{k:02d}", PCH, 16 + k, root=True, half="usb3", comp=f"pch:HS{k:02d}",
                           acpi=f"SS{k:02d}", type_c=k == 9))
    # ---- Thunderbolt root ports
    ports.append(_port("tb:4p1", TB, 1, root=True, connectable="not_used"))
    ports.append(_port("tb:4p2", TB, 2, root=True, connectable="not_used"))
    ports.append(_port("tb:4p3", TB, 3, root=True, half="usb3", comp="pch:HS12", type_c=True, acpi="SS03"))
    ports.append(_port("tb:4p4", TB, 4, root=True, half="usb3", comp="pch:HS13", type_c=True, acpi="SS04",
                       occ="hub0625"))
    # ---- devices on the chipset root ports
    devices += [
        _dev("dymo", "0922", "001f", "DYMO LabelWriter 4XL", "FS", "pch:HS03", None, PCH, "pch:HS03"),
        _dev("c930e", "046d", "0843", "Logitech Webcam C930e", "HS", "pch:HS07", None, PCH, "pch:HS07",
             bcd="0013"),
        _dev("mstx", "045e", "07a5", "Microsoft 2.4GHz Transceiver", "FS", "pch:HS08", None, PCH, "pch:HS08",
             pipes=[{"ep": "0x81", "type": "int", "max_packet": 8, "mult": 1, "interval": 4}]),
        _dev("hub0608", "05e3", "0608", "USB2.0 Hub", "HS", "pch:HS10", None, PCH, "pch:HS10", hub=True,
             tt="single"),
        _dev("aura", "0b05", "19af", "AURA LED Controller", "FS", "pch:HS11", None, PCH, "pch:HS11"),
        _dev("bt", "8087", "0033", "Intel Wireless Bluetooth", "FS", "pch:HS14", None, PCH, "pch:HS14",
             pipes=[{"ep": "0x83", "type": "iso", "max_packet": 0, "mult": 1, "interval": 1}]),
        _dev("hub0610o", "05e3", "0610", "USB2.1 Hub", "HS", "pch:HS13", None, PCH, "pch:HS13", hub=True,
             tt="multi"),
    ]
    for p in range(1, 5):  # front-panel style internal hub: 4 empty user ports
        ports.append(_port(f"hub0608:p{p}", PCH, p, hub="hub0608"))
    # outer dock hub (USB 2.0 half)
    outer_occ = {1: "hub0610i", 2: "revelator", 3: "hub2137"}
    for p in range(1, 5):
        ports.append(_port(f"hub0610o:p{p}", PCH, p, hub="hub0610o", occ=outer_occ.get(p),
                           comp=f"hub0625:p{p}"))
    devices += [
        _dev("hub0610i", "05e3", "0610", "USB2.1 Hub", "HS", "hub0610o:p1", "hub0610o", PCH, "pch:HS13", hub=True,
             tt="multi"),
        _dev("revelator", "194f", "0422", "Revelator IO 24", "HS", "hub0610o:p2", "hub0610o", PCH, "pch:HS13"),
        _dev("hub2137", "0424", "2137", "USB2137B", "HS", "hub0610o:p3", "hub0610o", PCH, "pch:HS13", hub=True,
             tt="multi"),
    ]
    inner_occ = {2: "generic", 4: "c922"}
    for p in range(1, 5):
        ports.append(_port(f"hub0610i:p{p}", PCH, p, hub="hub0610i", occ=inner_occ.get(p)))
    devices += [
        _dev("generic", "4c4a", "4a55", "USB Camera", "HS", "hub0610i:p2", "hub0610i", PCH, "pch:HS13"),
        _dev("c922", "046d", "085c", "C922 Pro Stream Webcam", "HS", "hub0610i:p4", "hub0610i", PCH, "pch:HS13",
             serial="C922SN01", bcd="0016"),
    ]
    for p in range(1, 8):
        ports.append(_port(f"hub2137:p{p}", PCH, p, hub="hub2137",
                           connectable="internal" if p in (5, 6, 7) else "user",
                           occ={2: "unifying", 5: "dellhub"}.get(p)))
    devices += [
        _dev("unifying", "046d", "c52b", "USB Receiver", "FS", "hub2137:p2", "hub2137", PCH, "pch:HS13",
             pipes=[{"ep": "0x81", "type": "int", "max_packet": 8, "mult": 1, "interval": 8}]),
        _dev("dellhub", "0424", "2840", "Dell U2717D hub controller", "FS", "hub2137:p5", "hub2137", PCH,
             "pch:HS13"),
    ]
    # SuperSpeed half of the dock on the Thunderbolt controller
    devices.append(_dev("hub0625", "05e3", "0625", "USB3.2 Hub", "SS", "tb:4p4", None, TB, "tb:4p4", hub=True))
    for p in range(1, 5):
        ports.append(_port(f"hub0625:p{p}", TB, p, hub="hub0625", half="usb3", comp=f"hub0610o:p{p}",
                           occ="kiyo" if p == 4 else None))
    devices.append(_dev("kiyo", "1532", "0e05", "Razer Kiyo Pro", "SS", "hub0625:p4", "hub0625", TB, "tb:4p4"))

    cameras = [
        {"key": C922_KEY, "device_id": "c922", "name": "C922 Pro Stream Webcam", "is_kiyo": False,
         "alt_table": _alt_table(C922_ALTS), "current_alt": 0},
        {"key": GENERIC_KEY, "device_id": "generic", "name": "USB Camera", "is_kiyo": False,
         "alt_table": _alt_table(GENERIC_ALTS), "current_alt": 0},
        {"key": C930E_KEY, "device_id": "c930e", "name": "Logitech Webcam C930e", "is_kiyo": False,
         "alt_table": _alt_table(C930E_ALTS), "current_alt": 0},
        {"key": KIYO_KEY, "device_id": "kiyo", "name": "Razer Kiyo Pro", "is_kiyo": True, "alt_table": None,
         "current_alt": None},
    ]
    snap = {"os": "windows", "collected_utc": "2026-11-06T15:23:37Z",
            "controllers": [
                {"id": PCH, "name": "Intel(R) USB 3.20 eXtensible Host Controller - 1.20 (Microsoft)",
                 "pci_id": "8086:7A60", "vendor": "Intel", "kind": "xhci", "policy_hint": None},
                {"id": TB, "name": "Intel(R) USB 3.10 eXtensible Host Controller - 1.10 (Microsoft)",
                 "pci_id": "8086:1138", "vendor": "Intel", "kind": "tb-xhci", "policy_hint": None}],
            "ports": ports, "devices": devices, "cameras": cameras}
    if streaming:
        alts = {C922_KEY: C922_ALTS, GENERIC_KEY: GENERIC_ALTS, C930E_KEY: C930E_ALTS}
        by_key = {c["key"]: c for c in cameras}
        for key, alt in streaming.items():
            mp, m = alts[key][alt]
            dev = next(d for d in devices if d["id"] == by_key[key]["device_id"])
            dev["periodic_pipes"].append({"ep": "0x81", "type": "iso", "max_packet": mp, "mult": m, "interval": 1})
            by_key[key]["current_alt"] = alt
    return snap


def build_cache():
    """ModeAltCache with the measured mode -> alt of bandwidth_domain_model.md section 3."""
    from common.topology_model import ModeAltCache
    c = ModeAltCache()
    for mode, alt in {"MJPG 640x480@30": 4, "MJPG 1280x720@30": 9, "MJPG 1920x1080@30": 11,
                      "MJPG 1920x1080@5": 5, "YUY2 640x480@30": 10}.items():
        fmt, rest = mode.split(" ")
        wh, fps = rest.split("@")
        w, h = wh.split("x")
        mp, m = C922_ALTS[alt]
        c.put("046d", "085c", "0016", fmt, int(w), int(h), float(fps), alt, mp, m, source="measured 2026-10-27")
    for mode, alt in {"MJPG 1280x720@30": 11, "MJPG 640x480@30": 10, "MJPG 320x240@30": 5}.items():
        fmt, rest = mode.split(" ")
        wh, fps = rest.split("@")
        w, h = wh.split("x")
        mp, m = C930E_ALTS[alt]
        c.put("046d", "0843", "0013", fmt, int(w), int(h), float(fps), alt, mp, m, source="measured 2026-10-27")
    for mode in ("MJPG 1280x720@30", "MJPG 640x480@30", "MJPG 1920x1080@30"):
        fmt, rest = mode.split(" ")
        wh, fps = rest.split("@")
        w, h = wh.split("x")
        c.put("4c4a", "4a55", None, fmt, int(w), int(h), float(fps), 1, 1023, 3, source="only streaming alt")
    return c
