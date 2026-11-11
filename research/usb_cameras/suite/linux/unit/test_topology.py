"""sysfs topology collector -> common snapshot schema -> topology_model (domains, prediction, message)."""
import pytest

import sysfs
import topology
from common import topology_model as tm

pytestmark = pytest.mark.linux_only
PCH, TB = "0000:00:14.0", "0000:3a:00.0"


def P(half, chain, ctrl=PCH):
    return f"port:{ctrl}|{half}|{chain}"


def snap_of():
    return topology.collect_snapshot(sysfs.discover_cameras())


def test_controllers_grouped_by_pci_parent(fake_root):
    s = snap_of()
    c = {x["id"]: x for x in s["controllers"]}
    assert set(c) == {PCH, TB}
    assert c[PCH]["pci_id"] == "8086:7A60" and c[PCH]["buses"] == {"usb2": 1, "usb3": 2}
    assert c[TB]["pci_id"] == "8086:1138" and c[TB]["behind_bridge"] is True
    assert c[PCH]["kind"] == "xhci" and c[PCH]["vendor"] == "Intel"


def test_ports_peers_location_labels(fake_root):
    s = snap_of()
    p = {x["id"]: x for x in s["ports"]}
    assert len(p) == 16 + 9 + 2 + 2 + 4 * 4
    assert p[P("usb2", "1")]["companion_id"] == P("usb3", "1")
    assert p[P("usb2", "1")]["companion_source"] == "peer"
    # cross-controller USB-C: USB 2.0 half on the PCH, SuperSpeed half on the Thunderbolt xHCI (merged by location)
    assert p[P("usb2", "13")]["companion_id"] == P("usb3", "2", TB)
    assert p[P("usb3", "2", TB)]["companion_id"] == P("usb2", "13")
    assert p[P("usb2", "13")]["connector"] == "C"
    assert p[P("usb2", "1")]["label_parts"]["panel"] == "back"
    assert p[P("usb2", "2")]["label_parts"].get("pld_all_zero") and "panel" not in p[P("usb2", "2")]["label_parts"]
    assert p[P("usb2", "10")]["connectable"] == "internal" and p[P("usb2", "9")]["label_parts"]["type_c"]
    assert p[P("usb2", "2", TB)]["connectable"] == "not_used"
    assert p[P("usb2", "13")]["label_parts"]["acpi_name"] == "HS13"
    assert p[P("usb2", "13.1.4")]["occupant_device_id"] == f"dev:{PCH}|usb2|13.1.4"


def test_devices_speed_hubs_and_pipes(fake_root_streaming):
    s = snap_of()
    d = {x["id"]: x for x in s["devices"]}
    c922 = d[f"dev:{PCH}|usb2|13.1.4"]
    assert c922["speed"] == "HS" and c922["root_port_id"] == P("usb2", "13")
    assert c922["parent_device_id"] == f"dev:{PCH}|usb2|13.1"
    iso = [x for x in c922["periodic_pipes"] if x["type"] == "iso"]
    assert len(iso) == 1 and (iso[0]["max_packet"], iso[0]["mult"]) == (992, 2)  # alt 9, multiplier kept
    assert d[f"dev:{PCH}|usb2|13"]["is_hub"] and d[f"dev:{PCH}|usb2|13"]["hub_tt"] == "multi"
    assert d[f"dev:{TB}|usb3|2.4"]["speed"] == "SS"
    cam = {c["key"]: c for c in s["cameras"]}["046d:085c:sn=C922SN01"]
    assert cam["current_alt"] == 9 and len(cam["alt_table"]) == 11


def test_domains_and_gerald_predictions(fake_root):
    s = snap_of()
    keys = {c["key"]: c for c in s["cameras"]}
    c922, gen = "046d:085c:sn=C922SN01", "4c4a:4a55:port=pci-0000:00:14.0/13.1.2"
    c930e, kiyo = "046d:0843:port=pci-0000:00:14.0/7", "1532:0e05:port=pci-0000:3a:00.0/2.4"
    dk = {k: tm.domain_key(s, keys[k]["device_id"]) for k in keys}
    assert dk[c922] == dk[gen] == f"hs|{PCH}|{P('usb2', '13')}"
    assert dk[c930e] == f"hs|{PCH}|{P('usb2', '7')}"
    assert dk[kiyo].startswith("ss|")
    over = tm.predict(s, [{"camera_key": c922, "mode": "MJPG 1280x720@30", "alt": 9},
                          {"camera_key": gen, "mode": "MJPG 1280x720@30"}])
    d13 = next(x for x in over["domains"] if x["key"] == dk[c922])
    assert d13["verdict"] == "over" and abs(d13["pct_microframe"] - 81.1) < 0.15
    fits = tm.predict(s, [{"camera_key": c922, "mode": "MJPG 640x480@30", "alt": 4},
                          {"camera_key": gen, "mode": "MJPG 640x480@30"}])
    d13 = next(x for x in fits["domains"] if x["key"] == dk[c922])
    assert d13["verdict"] == "fits" and abs(d13["pct_microframe"] - 59.7) < 0.15


def test_message_after_enospc(fake_root):
    s = snap_of()
    c922, gen = "046d:085c:sn=C922SN01", "4c4a:4a55:port=pci-0000:00:14.0/13.1.2"
    fail = {**tm.classify_failure("linux", 28, {"stage": "streamon"}), "loser": gen}
    assert fail["class"] == "bandwidth_certain"
    ex = tm.explain(s, [{"camera_key": c922, "mode": "MJPG 1280x720@30", "alt": 9},
                        {"camera_key": gen, "mode": "MJPG 1280x720@30"}], failure=fail)
    assert len(ex["messages"]) == 1
    m = ex["messages"][0]
    assert "share USB bandwidth" in m["message"] and tm.MESSAGE_SUGGEST_LINE in m["message"]
    assert "ENOSPC" in m["message"]
    ports = [p["port_id"] for g in m["suggestions"] for p in g["ports"]]
    assert ports and P("usb2", "7") not in ports                     # C930e's root port is occupied
    assert not any(pid.startswith(P("usb2", "13")) for pid in ports)  # never the dock (same domain)
    assert not any(f"|{TB}|" in pid or pid.startswith(f"port:{TB}") for pid in ports)  # never the SS twins
    assert all(p["domain_key"] != m["domain_key"] for g in m["suggestions"] for p in g["ports"])


def test_ep_fallback_without_descriptors(fake_root):
    """A device whose descriptors are unreadable falls back to ep_XX (multiplier unknown, flagged)."""
    from pathlib import Path
    d = Path(str(fake_root)) / "sys/devices/pci0000:00/0000:00:14.0/usb1/1-7"
    (d / "descriptors").unlink()
    ep = d / "1-7:1.1" / "ep_81"
    ep.mkdir(parents=True)
    (ep / "type").write_text("Isoc\n")
    (ep / "wMaxPacketSize").write_text("0400\n")
    (ep / "bInterval").write_text("01\n")
    s = snap_of()
    dev = {x["id"]: x for x in s["devices"]}[f"dev:{PCH}|usb2|7"]
    assert dev["periodic_pipes"] and dev["periodic_pipes"][0]["mult_unknown"] is True
    assert dev["periodic_pipes"][0]["max_packet"] == 0x400 and dev["pipe_notes"]


def test_multi_pair_variants_pick_predicted_over_and_fits(fake_root):
    """L-MULTI chooses mode pairs by prediction: whichever camera is A, the 'fits' variant must predict 'fits'
    (lowering the C922 when the generic camera, 3069 B at every mode, is the other one)."""
    import run_suite
    lm = run_suite.load_module("L-MULTI")
    cams = {c["key"]: c for c in sysfs.discover_cameras()}
    c922, gen = cams["046d:085c:sn=C922SN01"], cams["4c4a:4a55:port=pci-0000:00:14.0/13.1.2"]
    s = topology.collect_snapshot(list(cams.values()))
    cache = tm.ModeAltCache()
    tab = {a["alt"]: a for a in c922["descriptors"]["streams"][0]["alt_table"]}
    for (w, h, fps), alt in (((640, 480, 30), 4), ((1280, 720, 30), 9)):
        cache.put(c922["vid"], c922["pid"], c922["bcd_device"], "MJPG", w, h, fps, alt, tab[alt]["max_packet"],
                  tab[alt]["mult"])
    for a_cam, b_cam in ((gen, c922), (c922, gen)):
        v = {k: (ma, mb) for k, ma, mb in lm.pair_variants(s, cache, a_cam, b_cam)}
        dom = lm.domain_of(s, b_cam["key"])
        for kind, want in (("over", "over"), ("fits", "fits")):
            ma, mb = v[kind]
            pr = lm.predicted(s, cache, [(a_cam, ma), (b_cam, mb)])
            got = next(d["verdict"] for d in pr["domains"] if d["key"] == dom)
            assert got == want, (a_cam["name"], kind, ma, mb, got)
