"""IORegistry collector on fake ioreg plists (plumbing only; real trees are recorded by M-TOPO on a Mac)."""
import plistlib

import fake_mac
import mac_ep0
import mac_ioreg
from common import topology_model as tm

C922_KEY = "046d:085c:sn=C922SN01"
GEN_KEY = "4c4a:4a55:port=bus01/1.2"
KIYO_KEY = "1532:0e05:port=bus01/2.4"
C930E_KEY = "046d:0843:port=bus02/1"


def alt_tables():
    c922 = mac_ep0.summarize_config(fake_mac.uvc_config(fake_mac.C922_ALTS, [(640, 480, [30]), (1280, 720, [30])]))
    gen = mac_ep0.summarize_config(fake_mac.uvc_config(fake_mac.GENERIC_ALTS, [(640, 480, [30])]))
    return {"046d:085c:0016": c922["alt_table"], "4c4a:4a55:0100": gen["alt_table"]}


def snap(**kw):
    return mac_ioreg.build_snapshot(fake_mac.apple_silicon_plists(**kw), alt_tables=alt_tables())


def test_location_and_uid_parsing():
    assert mac_ioreg.loc_nibbles(0x01140000) == [1, 4]
    assert mac_ioreg.tier_count(0x01000000) == 0
    assert mac_ioreg.child_location(0x01100000, 3) == 0x01130000
    assert mac_ioreg.child_location(0x02000000, 1) == 0x02100000
    u = mac_ioreg.parse_unique_id("0x2000000fd9009b")  # un-padded forum example
    assert u == {"location_id": 0x00200000, "location_hex": "0x00200000", "vid": "0fd9", "pid": "009b"}
    assert mac_ioreg.parse_unique_id("47B4B64B70674B9CAD2BAE273A71F4B5") is None  # built-in camera style
    assert mac_ioreg.parse_model_id("UVC Camera VendorID_1133 ProductID_2140") == {"vid": "046d", "pid": "085c"}
    assert mac_ioreg.as_int(b"\x01\x00\x00\x00") == 1
    assert mac_ioreg.as_str(b"left-back\x00") == "left-back"


def test_apple_silicon_tree():
    s = snap()
    rep = s["schema_report"]
    assert rep["n_controllers"] == 3 and rep["n_cameras"] == 4 and rep["n_ports"] == 16
    keys = {c["key"] for c in s["cameras"]}
    assert keys == {C922_KEY, GEN_KEY, KIYO_KEY, C930E_KEY}
    cams = {c["key"]: c for c in s["cameras"]}
    assert cams[KIYO_KEY]["is_kiyo"] and cams[KIYO_KEY]["speed"] == "SS"
    assert cams[C922_KEY]["key_kind"] == "serial" and cams[GEN_KEY]["key_kind"] == "port"
    assert cams[C922_KEY]["vc_interface"] == 0 and cams[C922_KEY]["vs_interfaces"] == [1]
    assert cams[C922_KEY]["stable_port_path"] == "usb-drd1/1.4"
    ctrls = {c["id"]: c for c in s["controllers"]}
    assert ctrls["usb-drd0"]["kind"] == "dwc3-apple" and ctrls["usb-drd0"]["label"] == "left-back"
    assert ctrls["xhci"]["pci_id"] == "1b73:1100" and ctrls["xhci"]["vendor"] == "Fresco Logic"
    devs = {d["id"]: d for d in s["devices"]}
    hub = devs["loc:01100000"]
    assert hub["is_hub"] and hub["hub_tt"] == "multi" and hub["companion_hub_id"] == "loc:01200000"
    assert devs["loc:01140000"]["root_port_id"].startswith("usb-drd1:root:usb-drd1-port-hs")


def test_ports_empty_companions_labels():
    s = snap()
    ports = {p["path"]: p for p in s["ports"]}
    assert ports["bus00/1"]["occupant_device_id"] is None and ports["bus00/1"]["half"] == "usb2"
    assert ports["bus00/1"]["companion_id"] == ports["bus00/2"]["id"]
    assert ports["bus00/1"]["maybe_occupied_by_non_usb"] is True  # USB-C: a charger leaves no USB child
    assert ports["bus02/1"]["companion_id"] == ports["bus02/3"]["id"]  # UsbCompanionPortNumber
    assert ports["bus01/1.1"]["companion_id"] == ports["bus01/2.1"]["id"]  # USB 3 hub halves paired
    assert "left-back" in tm.port_label(s, ports["bus00/1"]["id"])
    assert ports["bus02/2"]["connector"] == "A" and ports["bus02/2"]["connectable"] == "user"


def test_domains_prediction_and_message():
    s = snap()
    doms = {d["key"]: d for d in tm.compute_domains(s)}
    hs = [d for d in doms.values() if set(d["cameras"]) == {C922_KEY, GEN_KEY}]
    assert len(hs) == 1 and hs[0]["kind"] == "hs_link"
    assert any(d["kind"] == "ss_link" and d["cameras"] == [KIYO_KEY] for d in doms.values())
    reqs = [{"camera_key": C922_KEY, "mode": "MJPG 1280x720@30", "alt": 9},
            {"camera_key": GEN_KEY, "mode": "MJPG 640x480@30", "alt": 1}]
    ex = tm.explain(s, reqs)
    d = [x for x in ex["prediction"]["domains"] if x["key"] == hs[0]["key"]][0]
    assert d["verdict"] == "over" and abs(d["pct_microframe"] - 81.1) < 0.2
    msg = ex["messages"][0]["message"]
    assert tm.MESSAGE_SUGGEST_LINE in msg and "left-back" in msg
    ports = [p for g in ex["messages"][0]["suggestions"] for p in g["ports"]]
    assert ports and all(p["domain_key"] != hs[0]["key"] for p in ports)
    fits = tm.predict(s, [dict(reqs[0], alt=4), reqs[1]])
    assert [x for x in fits["domains"] if x["key"] == hs[0]["key"]][0]["verdict"] == "fits"


def test_streaming_alt_feeds_observed_load():
    plists = fake_mac.apple_silicon_plists()
    # C922 streaming at alt 9: its VS interface reports bAlternateSetting 9
    def bump(n):
        if n.get("IOObjectClass") == "IOUSBHostInterface" and n.get("locationID") == 0x01140000 and n.get("bInterfaceSubClass") == 2:
            n["bAlternateSetting"] = 9
        for c in n.get("IORegistryEntryChildren", []) or []:
            bump(c)
    for r in plists["controllers"]:
        bump(r)
    s = mac_ioreg.build_snapshot(plists, alt_tables=alt_tables())
    c = [x for x in s["cameras"] if x["key"] == C922_KEY][0]
    assert c["current_alt"] == 9
    dev = [d for d in s["devices"] if d["id"] == c["device_id"]][0]
    assert dev["periodic_pipes"] == [{"ep": "0x81", "type": "iso", "max_packet": 992, "mult": 2, "interval": 1}]
    load = [d for d in tm.compute_domains(s) if C922_KEY in d["cameras"]][0]["load_us"]
    assert 38 < load < 42  # ~40% of the 100 us budget


def test_macos26_port_keys():
    s = snap(macos26_keys=True)
    rep = s["schema_report"]
    assert rep["port_keys_seen"].get("usb-port-number")
    assert 5 in rep["port_status_out_of_layout"]  # flagged, not trusted (verifier correction 4)
    ports = {p["path"]: p for p in s["ports"]}
    assert ports["bus01/1"]["occupant_device_id"] == "loc:01100000"
    assert {c["key"] for c in s["cameras"]} == {C922_KEY, GEN_KEY, KIYO_KEY, C930E_KEY}


def test_intel_tree_and_t2():
    s = mac_ioreg.build_snapshot(fake_mac.intel_plists())
    ctrls = {c["id"]: c for c in s["controllers"]}
    assert ctrls["XHC1"]["pci_id"] == "8086:a36d" and ctrls["XHC1"]["vendor"] == "Intel"
    assert ctrls["VHC128"]["kind"] == "t2_virtual"
    ports = {p["path"]: p for p in s["ports"]}
    assert ports["bus14/2"]["label_parts"]["acpi_name"] == "HS02"
    assert ports["bus14/1"]["companion_id"] == ports["bus14/5"]["id"]
    assert all(p["connectable"] == "internal" for p in s["ports"] if p["controller_id"] == "VHC128")
    keys = {c["key"] for c in s["cameras"]}
    assert "046d:0843:port=bus14/2" in keys
    # moving the C930e never suggests the T2 bus
    c = [x for x in s["cameras"] if x["key"] == "046d:0843:port=bus14/2"][0]
    conflict = {"domain_key": tm.domain_key(s, c["device_id"]), "controller_id": "XHC1", "camera_info": []}
    sugg = tm.suggest_ports(s, conflict, c["key"])
    assert all(g["controller_id"] != "VHC128" for g in sugg)


def test_fallback_ports_devices_only():
    plists = fake_mac.apple_silicon_plists()
    devs = []
    for r in plists["controllers"]:
        for p in r["IORegistryEntryChildren"]:
            devs += p.get("IORegistryEntryChildren", [])
    s = mac_ioreg.build_snapshot({"devices": devs})
    assert s["warnings"] and len(s["cameras"]) == 4
    assert {c["id"] for c in s["controllers"]} >= {"bus01", "bus02"}


def test_interface_alts_and_device_states():
    plists = fake_mac.apple_silicon_plists()
    alts = mac_ioreg.interface_alts(plists["interfaces"], 0x01140000)
    assert {a["subclass"] for a in alts} == {1, 2}
    # fallback when IOUSBHostInterface has no locationID: interfaces from the device subtree
    alts2 = mac_ioreg.interface_alts_from_devices(plists["controllers"], 0x01140000)
    assert sorted((a["number"], a["subclass"]) for a in alts2) == sorted((a["number"], a["subclass"]) for a in alts)
    st = mac_ioreg.device_states(plists["controllers"])
    assert st["0x01240000"]["vid"] == "1532"
    assert mac_ioreg.load_plist(plistlib.dumps(plists["hpm"]))[0]["port-number"] == fake_mac.le32(1)
    assert mac_ioreg.load_plist(b"") == [] and mac_ioreg.load_plist(b"garbage") == []
