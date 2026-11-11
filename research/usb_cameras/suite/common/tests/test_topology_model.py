"""Topology model: cost formula, Gerald fixture predictions (bandwidth_domain_model.md section 3), domains,
policies, learned escalation, classification, suggestions and the user message."""
import json

import pytest

from common import topology_model as tm
from gerald_fixture import (C922_KEY, C930E_KEY, GENERIC_KEY, KIYO_KEY, PCH, TB, build_cache, build_snapshot)


# ------------------------------------------------------------------------------------------------ cost formula
def test_cost_matches_hs_budget_model():
    # hs_budget_model.t_iso_in_ns(n) = 38*8*2.083 + 2.083*floor(3.167 + 1.1667*8*n)
    import math
    for n in (192, 640, 800, 992, 1020, 1023, 1024):
        exp = 38 * 8 * 2.083 + 2.083 * math.floor(3.167 + 1.1667 * 8 * n)
        assert tm.t_hs_ns(n) == pytest.approx(exp)
    # bandwidth_domain_model.md 2.1 worked values: 3x1024 = 61.6 us = 49.3% of a microframe
    assert tm.cost_us(1024, 3) == pytest.approx(61.6, abs=0.05)
    assert 100 * tm.cost_us(1023, 3) / 125 == pytest.approx(49.3, abs=0.05)
    assert 100 * tm.cost_us(992, 2) / 125 == pytest.approx(31.9, abs=0.05)  # C922 alt 9


def test_verdict_thresholds():
    assert tm.verdict_for(93.0) == "fits"
    assert tm.verdict_for(94.0) == "marginal"     # Gerald: 75.2% passed, so it is "marginal", not "over"
    assert tm.verdict_for(100.0) == "marginal"
    assert tm.verdict_for(101.1) == "over"        # 80.9% refused
    br = {"max_pass_us": 94.0, "min_fail_us": 101.1}
    assert tm.verdict_for(94.0, bracket=br) == "fits"
    assert tm.verdict_for(98.0, bracket=br) == "marginal"
    assert tm.verdict_for(101.4, bracket=br) == "over"


# ------------------------------------------------------------------------------------------------ Gerald fixture
def _predict(c922_mode, generic_mode="MJPG 1280x720@30", **kw):
    snap = build_snapshot()
    reqs = [{"camera_key": C922_KEY, "mode": c922_mode}, {"camera_key": GENERIC_KEY, "mode": generic_mode}]
    return snap, tm.predict(snap, reqs, build_cache(), **kw)


@pytest.mark.parametrize("mode,pct,verdict", [
    ("MJPG 1280x720@30", 81.1, "over"),      # C922 alt 9 (2x992 = 1984 B) + generic 3x1023
    ("MJPG 640x480@30", 59.7, "fits"),       # C922 alt 4 (640 B)
    ("MJPG 1920x1080@5", 62.2, "fits"),      # C922 alt 5 (800 B)
])
def test_gerald_hs13_predictions(mode, pct, verdict):
    _, pred = _predict(mode)
    dom = [d for d in pred["domains"] if d["key"] == f"hs|{PCH}|pch:HS13"]
    assert len(dom) == 1
    d = dom[0]
    assert d["pct_microframe"] == pytest.approx(pct, abs=0.05)
    assert d["verdict"] == verdict
    assert set(d["members"]) == {C922_KEY, GENERIC_KEY}
    assert d["cost_sources"][C922_KEY] == "cache"
    assert bool(pred["conflicts"]) == (verdict == "over")


def test_gerald_c922_max_alt_worst_case_without_cache():
    snap = build_snapshot()
    pred = tm.predict(snap, [{"camera_key": C922_KEY, "mode": "MJPG 1280x720@30"},
                             {"camera_key": GENERIC_KEY, "mode": "MJPG 1280x720@30"}], None)
    r = {x["camera_key"]: x for x in pred["requests"]}
    assert r[C922_KEY]["cost_source"] == "worst_case" and r[C922_KEY]["alt"] == 11
    assert pred["domains"][0]["verdict"] == "over"


def test_gerald_domains_and_kiyo_separate():
    snap = build_snapshot(streaming={C922_KEY: 9, GENERIC_KEY: 1, C930E_KEY: 11})
    doms = {d["key"]: d for d in tm.compute_domains(snap)}
    hs13 = doms[f"hs|{PCH}|pch:HS13"]
    assert hs13["pct_microframe"] == pytest.approx(81.1, abs=0.05)
    assert hs13["verdict"] == "over"
    assert set(hs13["cameras"]) == {C922_KEY, GENERIC_KEY}
    assert "revelator" in hs13["members"] and "unifying" in hs13["members"]
    hs07 = doms[f"hs|{PCH}|pch:HS07"]
    assert hs07["cameras"] == [C930E_KEY] and hs07["pct_microframe"] == pytest.approx(49.3, abs=0.05)
    # the Kiyo is SuperSpeed on the Thunderbolt xHCI: its own domain, never with the HS13 cameras
    assert tm.domain_key(snap, "kiyo") == f"ss|{TB}|tb:4p4"
    assert KIYO_KEY in doms[f"ss|{TB}|tb:4p4"]["cameras"]
    # FS devices directly on root ports: full-speed domains
    assert tm.domain_key(snap, "mstx") == f"fs|{PCH}|pch:HS08"


def test_full_accounting_counts_interrupts_and_tts():
    snap = build_snapshot(streaming={C922_KEY: 9, GENERIC_KEY: 1})
    cal = {d["key"]: d for d in tm.compute_domains(snap)}[f"hs|{PCH}|pch:HS13"]
    full = {d["key"]: d for d in tm.compute_domains(snap, accounting="full")}[f"hs|{PCH}|pch:HS13"]
    assert full["active_tts"] == 1          # Unifying receiver (FS, interrupt) behind the multi-TT 2137
    assert full["load_us"] > cal["load_us"] + 7.0


def test_usb3_half_root_port_is_mapped_to_usb2_companion():
    snap = build_snapshot()
    c922 = next(d for d in snap["devices"] if d["id"] == "c922")
    c922["root_port_id"] = "tb:4p4"     # a collector that wrongly took the SuperSpeed parent chain
    c922["controller_id"] = TB
    assert tm.domain_key(snap, "c922") == f"hs|{PCH}|pch:HS13"


# ------------------------------------------------------------------------------------------------ policies
def test_policy_table():
    assert tm.policy_for({"pci_id": "8086:7A60", "kind": "xhci"})["hs_domain"] == "root_port"
    assert tm.policy_for({"pci_id": "8086:7A60"})["uncertain"] is False
    amd = tm.policy_for({"pci_id": "1022:15B6", "vendor": "AMD"})
    assert amd["hs_domain"] == "controller" and amd["uncertain"] is True     # verifier V1
    asm = tm.policy_for({"pci_id": "1B21:2142"})
    assert asm["hs_domain"] == "root_port" and asm["uncertain"] is True
    assert tm.policy_for({"kind": "ehci", "pci_id": "8086:1E2D"})["hs_domain"] == "controller"
    assert tm.policy_for({"pci_id": "8086:1E31"})["budget_kind"] == "intel_sw_blocks"
    assert tm.policy_for({"pci_id": "14C3:0000"})["budget_kind"] == "mtk_payload"
    assert tm.policy_for({"pci_id": "1B21:2142", "policy_hint": "controller"})["hs_domain"] == "controller"


def _two_port_snapshot(pci_id="1022:15B6", vendor="AMD"):
    """One controller, two cameras on two different root ports."""
    ctrl = "ctrl0"
    ports = [{"id": f"rp{n}", "controller_id": ctrl, "hub_device_id": None, "port_number": n, "path": f"rp{n}",
              "is_root_port": True, "half": "usb2", "companion_id": None, "connectable": "user",
              "connector": "A", "label_parts": {}, "occupant_device_id": {1: "camA", 2: "camB"}.get(n),
              "speed_max": "HS"} for n in (1, 2, 3)]
    devs = [{"id": d, "vid": "046d", "pid": "0843", "serial": None, "name": d, "speed": "HS", "port_id": f"rp{n}",
             "parent_device_id": None, "is_hub": False, "hub_tt": None, "controller_id": ctrl,
             "root_port_id": f"rp{n}", "bcd_device": None, "periodic_pipes": []} for d, n in (("camA", 1), ("camB", 2))]
    cams = [{"key": d, "device_id": d, "name": d, "is_kiyo": False,
             "alt_table": [{"alt": 11, "max_packet": 1024, "mult": 3}], "current_alt": 0} for d in ("camA", "camB")]
    return {"os": "linux", "collected_utc": "x", "controllers": [{"id": ctrl, "name": "AMD xHCI", "pci_id": pci_id,
                                                                  "vendor": vendor, "kind": "xhci"}],
            "ports": ports, "devices": devs, "cameras": cams}


def test_pooled_controller_puts_ports_in_one_domain():
    snap = _two_port_snapshot()
    assert tm.domain_key(snap, "camA") == tm.domain_key(snap, "camB") == "hs|ctrl0|*"
    pred = tm.predict(snap, [{"camera_key": "camA", "mode": "MJPG 1920x1080@30"},
                             {"camera_key": "camB", "mode": "MJPG 1920x1080@30"}])
    assert pred["conflicts"] and pred["conflicts"][0]["domain_key"] == "hs|ctrl0|*"
    # Intel: separate domains, both fit (98.4% cross-port case)
    snap_i = _two_port_snapshot("8086:7A60", "Intel")
    pred_i = tm.predict(snap_i, [{"camera_key": "camA", "mode": "x"}, {"camera_key": "camB", "mode": "x"}])
    assert not pred_i["conflicts"] and len(pred_i["domains"]) == 2
    # pooled controller: no port on the same controller may be suggested; nothing else exists
    sugg = tm.suggest_ports(snap, pred["conflicts"][0], "camB")
    assert sugg == []
    msg = tm.build_message(pred["conflicts"][0], None, sugg, [])
    assert "add a USB controller card with one controller per port" in msg


def test_learned_escalation_needs_two_events(tmp_path):
    lp = tm.LearnedPolicies(path=tmp_path / "learned.json")
    ctrl = {"pci_id": "1B21:2142", "name": "ASMedia"}
    lp.record("1b21:2142", "refused", domain_load_us=50.0, controller_load_us=110.0, cls="bandwidth_certain")
    assert tm.policy_for(ctrl, lp)["hs_domain"] == "root_port"
    lp.record("1b21:2142", "refused", domain_load_us=55.0, controller_load_us=120.0, cls="bandwidth_certain")
    pol = tm.policy_for(ctrl, lp)
    assert pol["hs_domain"] == "controller" and pol["source"] == "learned"
    lp.save()
    lp2 = tm.LearnedPolicies.load(tmp_path / "learned.json")
    assert tm.policy_for(ctrl, lp2)["hs_domain"] == "controller"


def test_learned_bracket():
    lp = tm.LearnedPolicies()
    lp.record("8086:7a60", "pass", domain_load_us=94.0)
    lp.record("8086:7a60", "refused", domain_load_us=101.1, cls="bandwidth_certain")
    lp.record("8086:7a60", "refused", domain_load_us=40.0, cls="in_use")  # not bandwidth: ignored
    pol = tm.policy_for({"pci_id": "8086:7A60"}, lp)
    assert pol["bracket"] == {"max_pass_us": 94.0, "min_fail_us": 101.1}
    assert pol["hs_domain"] == "root_port"


def test_panther_point_blocks_model():
    snap = _two_port_snapshot("8086:1E31", "Intel")
    # move camB onto camA's root port via a hub-less trick: same root port id
    pred = tm.predict(snap, [{"camera_key": "camA", "max_packet": 800, "mult": 2}])
    d = pred["domains"][0]
    # (ceil(1600/4) + 2*26) blocks out of 1285 usable -> 35.2% of budget
    assert d["pct_budget"] == pytest.approx(100 * (400 + 52) / 1285, abs=0.05)
    assert d["pct_microframe"] is None


# ------------------------------------------------------------------------------------------------ mode cache
def test_mode_alt_cache_roundtrip(tmp_path):
    c = build_cache()
    p = c.save(tmp_path / "cache.json")
    c2 = tm.ModeAltCache.load(p)
    assert len(c2) == len(c)
    hit = c2.get("046D", "085C", "0016", "MJPEG", 1280, 720, 30)
    assert hit["alt"] == 9 and hit["other_firmware"] is False
    other = c2.get_mode("046d", "085c", "0099", "MJPG 640x480@30")
    assert other["alt"] == 4 and other["other_firmware"] is True
    assert tm.ModeAltCache.make_key(0x46D, 0x85C, 0x16, "MJPG", 640, 480, 7.5) == "046d:085c:0016:MJPG:640x480@7.5"
    modes = c2.modes_for("046d", "085c", "0016")
    assert {m["mode"]["width"] for m in modes} >= {640, 1280, 1920}
    json.loads(p.read_text())


def test_parse_mode():
    assert tm.parse_mode("MJPG 1280x720@30") == {"format": "MJPG", "width": 1280, "height": 720, "fps": 30.0}
    assert tm.parse_mode("MJPEG 640x480@29.97fps")["fps"] == pytest.approx(29.97)
    assert tm.parse_mode("1920x1080@5")["format"] == "MJPG"
    assert tm.parse_mode({"subtype": "yuyv", "w": 640, "h": 480, "fps": 30})["format"] == "YUY2"
    assert tm.parse_mode("garbage") is None
    assert tm.mode_text("MJPG 1280x720@30") == "1280x720 MJPEG 30 fps"


# ------------------------------------------------------------------------------------------------ classify
@pytest.mark.parametrize("osn,code,ctx,cls", [
    ("windows", 0x800718CF, None, "bandwidth_certain"),
    ("windows", "0x800718CF", None, "bandwidth_certain"),
    ("windows", -2147018545, None, "bandwidth_certain"),            # signed 0x800718CF
    ("windows", "OSError(5)", {"api": "pyav_ds", "other_streaming_in_domain": True, "predicted_verdict": "over"},
     "bandwidth_probable"),
    ("windows", 0x80070005, {"other_streaming_in_domain": True, "predicted_verdict": "over"}, "bandwidth_probable"),
    ("windows", 0x80070005, {"other_streaming_in_domain": False}, "other"),
    ("windows", 0x80070005, {"in_use_by_other": True}, "in_use"),
    ("windows", 0x8007001F, None, "device_error"),
    ("windows", -2147024865, None, "device_error"),                 # signed 0x8007001F (Kiyo)
    ("windows", 0xC00D7167, None, "device_error"),
    ("windows", 0xC00D3704, None, "in_use"),
    ("windows", 0xC00D3EA3, None, "in_use"),
    ("windows", 0xC00D3EA2, None, "device_error"),
    ("windows", "MF_E_INVALIDREQUEST", None, "other"),
    ("windows", None, {"timed_out": True}, "timeout"),
    ("windows", "timeout", None, "timeout"),
    ("windows", None, {"frames": 0, "other_streaming_in_domain": True, "predicted_verdict": "over"},
     "bandwidth_probable"),
    ("linux", 28, None, "bandwidth_certain"),
    ("linux", "ENOSPC", None, "bandwidth_certain"),
    ("linux", -28, None, "bandwidth_certain"),
    ("linux", "ENOMEM", None, "other"),
    ("linux", "ENOMEM", {"controller_pci_id": "8086:1E31", "other_streaming_in_domain": True,
                         "predicted_verdict": "over"}, "bandwidth_probable"),
    ("linux", "EBUSY", None, "in_use"),
    ("linux", "EIO", {"stage": "streamon"}, "other"),
    ("linux", "ETIMEDOUT", None, "device_error"),
    ("linux", "EACCES", {"stage": "open"}, "permission"),
    ("macos", 0xE00002EC, None, "bandwidth_certain"),
    ("macos", "kIOReturnExclusiveAccess", None, "in_use"),
    ("macos", -11852, None, "permission"),
    ("linux", -1, {"api": "libusb", "other_streaming_in_domain": True, "predicted_verdict": "over"},
     "bandwidth_probable"),
])
def test_classify_failure(osn, code, ctx, cls):
    r = tm.classify_failure(osn, code, ctx)
    assert r["class"] == cls, r
    assert r["reason"]


def test_hresult_names():
    assert tm.hresult_name(0xC00D7167) == "MF_E_REBOOT_REQUIRED"
    assert tm.hresult_name(-2147024891) == "E_ACCESSDENIED"
    assert tm.hresult_name(0x80070420) == "HRESULT_FROM_WIN32(1056)"


# ------------------------------------------------------------------------------------------------ suggestions
def test_gerald_suggestions_and_message():
    snap, pred = _predict("MJPG 1280x720@30")
    conflict = pred["conflicts"][0]
    assert conflict["pct_microframe"] == pytest.approx(81.1, abs=0.05)
    assert "05E3:0610" in conflict["shared_hop"] and "port 13" in conflict["shared_hop"]
    sugg = tm.suggest_ports(snap, conflict, GENERIC_KEY, build_cache(), prediction=pred)
    ports = {p["port_id"]: p for g in sugg for p in g["ports"]}
    hs13_domain = {d["id"] for d in snap["devices"] if d.get("root_port_id") == "pch:HS13"}
    # never the same hub/dock (HS13 domain), the SS twin, internal or not-used ports, or occupied ports
    for pid in ports:
        port = next(p for p in snap["ports"] if p["id"] == pid)
        assert port["hub_device_id"] not in hs13_domain
        assert port["half"] == "usb2" and port["connectable"] == "user" and port["occupant_device_id"] is None
    assert not {"pch:HS13", "tb:4p4", "tb:4p3", "tb:4p1", "pch:HS07", "pch:HS10", "pch:HS14"} & set(ports)
    expected_root = {f"pch:HS{n:02d}" for n in (1, 2, 4, 5, 6, 9, 12, 15, 16)}
    assert expected_root <= set(ports)
    assert {f"hub0608:p{n}" for n in (1, 2, 3, 4)} <= set(ports)          # internal hub with user ports (V4.3)
    assert all(p["rank"] == 1 for p in ports.values())                    # Intel per-root-port, empty domains
    # root ports before hub ports, USB 3-capable before USB 2.0-only
    order = [p["port_id"] for g in sugg for p in g["ports"]]
    assert order.index("pch:HS01") < order.index("pch:HS15") < order.index("hub0608:p1")
    assert sugg[0]["group_label"] == "Intel(R) USB 3.20 eXtensible Host Controller"

    alts = tm.stay_here_alternatives(snap, conflict, build_cache())
    assert alts and alts[0]["camera_key"] == C922_KEY
    # B13: keep format and fps, then maximise w*h (1080p@5 has more pixels per second but drops to 5 fps)
    assert alts[0]["mode_text"] == "640x480 MJPEG 30 fps" and alts[0]["keeps_fps"]

    failure = dict(tm.classify_failure("windows", 0x800718CF, {"api": "mf"}), loser=GENERIC_KEY)
    msg = tm.build_message(conflict, failure, sugg, alts)
    assert msg.startswith("C922 Pro Stream Webcam and USB Camera share USB bandwidth: both connect through ")
    assert "When I tried to open them both at the same time, USB Camera failed with a USB bandwidth error " \
           "(0x800718CF: not enough USB bandwidth)." in msg
    assert "At these settings they need about 101% of what that USB 2.0 link allows (C922 Pro Stream Webcam " \
           "1280x720 MJPEG 30 fps: 40%, USB Camera 1280x720 MJPEG 30 fps: 62%)." in msg
    assert "Suggest moving one of those cameras to any of the following controller ports:" in msg
    assert "\n  Intel(R) USB 3.20 eXtensible Host Controller: port 1 (HS01" in msg
    assert "Or, to keep both where they are, lower C922 Pro Stream Webcam to " in msg
    assert "HS13" not in msg.split("controller ports:")[1].split("Or, to keep")[0]


def test_predicted_message_without_failure():
    snap, pred = _predict("MJPG 1280x720@30")
    out = tm.explain(snap, [{"camera_key": C922_KEY, "mode": "MJPG 1280x720@30"},
                            {"camera_key": GENERIC_KEY, "mode": "MJPG 1280x720@30"}], build_cache())
    assert len(out["messages"]) == 1
    msg = out["messages"][0]["message"]
    assert "share USB bandwidth" in msg and "predicted from the USB layout" in msg
    assert tm.MESSAGE_SUGGEST_LINE in msg


def _fake_two_controllers(load_rp3_us_packet=None):
    """Intel controller A: rp1 holds a hub with two cameras (+ an empty hub port), rp2 empty, rp3 holds a hub with
    an audio device (optionally streaming) and one empty port, rp4 internal; rp1's USB 3 twin ss1.
    ASMedia controller B (uncertain): rp1 empty."""
    A, B = "ctlA", "ctlB"

    def port(pid, ctrl, n, hub=None, half="usb2", comp=None, occ=None, connectable="user", panel=None):
        return {"id": pid, "controller_id": ctrl, "hub_device_id": hub, "port_number": n, "path": pid,
                "is_root_port": hub is None, "half": half, "companion_id": comp, "connectable": connectable,
                "connector": "A", "label_parts": ({"panel": panel} if panel else {}), "occupant_device_id": occ,
                "speed_max": None}

    def dev(did, port_id, rp, ctrl, parent=None, hub=False, pipes=None, name=None):
        return {"id": did, "vid": "1234", "pid": did[-4:].rjust(4, "0"), "serial": None, "name": name or did,
                "speed": "HS", "port_id": port_id, "parent_device_id": parent, "is_hub": hub, "hub_tt": "single",
                "controller_id": ctrl, "root_port_id": rp, "bcd_device": None, "periodic_pipes": pipes or []}

    ports = [port("A1", A, 1, comp="Ass1", occ="hub", panel="rear"), port("Ass1", A, 5, half="usb3", comp="A1"),
             port("A2", A, 2, panel="rear"), port("A3", A, 3, occ="hub2", panel="front"),
             port("A4", A, 4, connectable="internal"),
             port("H1", A, 1, hub="hub", occ="cam1"), port("H2", A, 2, hub="hub", occ="cam2"),
             port("H3", A, 3, hub="hub"), port("B1", B, 1),
             port("G1", A, 1, hub="hub2", occ="other"), port("G2", A, 2, hub="hub2")]
    pipes = [{"ep": "0x81", "type": "iso", "max_packet": load_rp3_us_packet, "mult": 1, "interval": 1}] \
        if load_rp3_us_packet else []
    devs = [dev("hub", "A1", "A1", A, hub=True, name="Some Hub"), dev("cam1", "H1", "A1", A, parent="hub"),
            dev("cam2", "H2", "A1", A, parent="hub"), dev("hub2", "A3", "A3", A, hub=True, name="Desk Hub"),
            dev("other", "G1", "A3", A, parent="hub2", pipes=pipes, name="Audio thing")]
    cams = [{"key": k, "device_id": k, "name": k.upper(), "is_kiyo": False,
             "alt_table": [{"alt": 1, "max_packet": 1024, "mult": 3}], "current_alt": None} for k in ("cam1", "cam2")]
    return {"os": "linux", "collected_utc": "x",
            "controllers": [{"id": A, "name": "Intel xHCI", "pci_id": "8086:A0ED", "vendor": "Intel", "kind": "xhci"},
                            {"id": B, "name": "ASMedia USB 3.1 xHCI", "pci_id": "1B21:2142", "vendor": "ASMedia",
                             "kind": "xhci"}],
            "ports": ports, "devices": devs, "cameras": cams}


def test_fake_snapshot_suggestions_ranking():
    snap = _fake_two_controllers(load_rp3_us_packet=192)   # rp3 carries a small iso pipe -> room left
    pred = tm.predict(snap, [{"camera_key": "cam1", "mode": "MJPG 1920x1080@30"},
                             {"camera_key": "cam2", "mode": "MJPG 1920x1080@30"}])
    assert pred["conflicts"] and pred["conflicts"][0]["domain_key"] == "hs|ctlA|A1"
    c = pred["conflicts"][0]
    assert c["shared_hop"].startswith("the same USB hub (Some Hub 1234:0HUB)") or "Some Hub" in c["shared_hop"]
    sugg = tm.suggest_ports(snap, c, "cam2")
    flat = [(p["port_id"], p["rank"], tuple(p["shares_with"])) for g in sugg for p in g["ports"]]
    ids = [f[0] for f in flat]
    assert "H3" not in ids          # same hub
    assert "Ass1" not in ids        # SuperSpeed twin of the conflicting connector
    assert "A4" not in ids          # internal
    assert ids[0] == "A2"           # rank 1: empty root port, known per-root-port controller, same (rear) panel
    ranks = {f[0]: f[1] for f in flat}
    assert ranks["A2"] == 1 and ranks["B1"] == 2 and ranks["G2"] == 4
    assert dict((f[0], f[2]) for f in flat)["G2"] == ("Audio thing",)
    assert "G1" not in ids and "A3" not in ids   # occupied
    labels = [g["group_label"] for g in sugg]
    assert labels[0] == "Rear panel, Intel xHCI"
    assert "ASMedia USB 3.1 xHCI" in labels
    msg = tm.build_message(c, None, sugg, [])
    assert "Rear panel, Intel xHCI: port 2" in msg
    assert "(shares with Audio thing)" in msg


def test_fake_snapshot_full_domain_excluded():
    snap = _fake_two_controllers(load_rp3_us_packet=1024)   # rp3 busy: 1024 B iso (~20 us) + 61.6 -> still fits
    pred = tm.predict(snap, [{"camera_key": "cam1", "mode": "x"}, {"camera_key": "cam2", "mode": "x"}])
    sugg = tm.suggest_ports(snap, pred["conflicts"][0], "cam2")
    assert "G2" in [p["port_id"] for g in sugg for p in g["ports"]]
    # make rp3 nearly full: 3x1024 already there -> 61.6 + 61.6 > 100 -> excluded
    for d in snap["devices"]:
        if d["id"] == "other":
            d["periodic_pipes"][0]["mult"] = 3
    sugg = tm.suggest_ports(snap, pred["conflicts"][0], "cam2")
    assert "G2" not in [p["port_id"] for g in sugg for p in g["ports"]]


def test_uncertain_controller_message_adds_other_controller_hint():
    snap = _fake_two_controllers()
    snap["controllers"][0].update(pci_id="1B21:1242", vendor="ASMedia", name="ASMedia A")
    pred = tm.predict(snap, [{"camera_key": "cam1", "mode": "x"}, {"camera_key": "cam2", "mode": "x"}])
    c = pred["conflicts"][0]
    assert c["uncertain"]
    sugg = tm.suggest_ports(snap, c, "cam2")
    ranks = {p["port_id"]: p["rank"] for g in sugg for p in g["ports"]}
    assert ranks["B1"] == 2 and ranks["A2"] == 3     # different controller beats same uncertain controller
    msg = tm.build_message(c, None, sugg, [])
    assert "try a port on a different controller (ASMedia USB 3.1 xHCI)" in msg


# ------------------------------------------------------------------------------------------------ multi_topo fixes
LOG_RENDER = [{"msg": "[in#0 @ 0000] Could not RenderStream to connect pins"},
              {"msg": "[in#0 @ 0000] Error opening input: I/O error"}]
LOG_RUN = [{"msg": "[in#0 @ 0000] Could not run graph (sometimes caused by a device already in use by other "
                   "application)"}, {"msg": "Error opening input: I/O error"}]
CONTENTION = {"api": "pyav_ds", "other_streaming_in_domain": True, "predicted_verdict": "over"}


@pytest.mark.parametrize("code,ctx,cls", [
    ("OSError(5)", dict(CONTENTION, log=LOG_RUN, open_duration_s=0.6), "bandwidth_probable"),   # refusal
    ("OSError(5)", dict(CONTENTION, log=LOG_RENDER, open_duration_s=0.6), "device_not_ready"),  # RenderStream
    ("OSError(5)", dict(CONTENTION, log=LOG_RUN, open_duration_s=10.36), "device_not_ready"),   # #34: slow run-graph
    ("OSError(5)", dict(CONTENTION, open_duration_s=0.5, device_gone=True), "device_not_ready"),
    ("OSError(5)", {"api": "pyav_ds", "log": LOG_RENDER}, "device_not_ready"),                 # no contention
    ("timeout", dict(CONTENTION, open_duration_s=10.33), "device_not_ready"),                   # #53 hang
    (0x800718CF, {"api": "mf", "device_gone": True, "open_duration_s": 5.0}, "bandwidth_certain"),  # never overridden
    (0x8007001F, {"api": "mf", "log": LOG_RENDER, "open_duration_s": 3}, "device_error"),     # dead-device gate
])
def test_classify_device_not_ready(code, ctx, cls):
    r = tm.classify_failure("windows", code, ctx)
    assert r["class"] == cls, r
    if cls == "device_not_ready":
        assert r["class_before_override"] in ("bandwidth_probable", "other", "timeout")
        assert "not a bandwidth refusal" in r["reason"]


def test_eio_reason_not_access_denied():
    r = tm.classify_failure("windows", "OSError(5)", dict(CONTENTION, log=LOG_RUN))
    assert "EIO" in r["reason"] and "access denied" not in r["reason"].lower()
    assert "'Could not run graph'" in r["reason"]


@pytest.mark.parametrize("label,tier", [
    ("port 1 (HS01, USB 3, not USB-C, user-accessible)", "controller_port_number"),
    ("port 3 of the hub 'USB2.0 Hub' 05E3:0608 (on port 10 (HS10))", "controller_port_number"),
    ("USB-C, second from top (red) [HS12]", "panel_position"),
    ("Front USB 3.2 Gen 1", "friendly_name"),
    ("HS07", "acpi_or_location_path"),
    ("HS07 / PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(7)", "acpi_or_location_path"),
    ("PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(7)", "acpi_or_location_path"),
    ("an empty USB port", "location_unknown"),
])
def test_label_tier(label, tier):
    assert tm.label_tier(label) == tier
    assert tm.label_is_raw(label) == (tier in tm.RAW_LABEL_TIERS)


def test_labels_raw_shared_rule():
    assert tm.labels_raw([]) is None
    assert tm.labels_raw(["port 1 (HS01)", "port 2 (HS02)"]) is False          # tier 3 is NOT raw
    assert tm.labels_raw(["HS01", "PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(2)"]) is True
    assert tm.labels_raw(["HS01", "port 2 (HS02)"]) is False


def test_header_device_names():
    for n in ("HX1500i Power Supply", "Corsair Commander Pro", "AURA LED Controller", "Intel(R) Wireless Bluetooth(R)",
              "NZXT Kraken X63", "iCUE H150i"):
        assert tm.is_header_device_name(n), n
    for n in ("USB Receiver", "Logitech Webcam C930e", "MX Vertical Advanced Ergonomic Mouse", "Cruzer", None, ""):
        assert not tm.is_header_device_name(n), n


def _gerald_with_evidence():
    snap = build_snapshot()
    ports = {p["id"]: p for p in snap["ports"]}
    # HS01: _PLD user_visible + phantom of a receiver (strong); HS10 hub port 3: hub _PLD + PSU phantom (header)
    ports["pch:HS01"]["label_parts"]["user_visible"] = True
    ports["pch:HS01"]["phantom_history"] = [{"instance_id": "x", "name": "USB Receiver"}]
    ports["hub0608:p3"]["label_parts"]["user_visible"] = True
    ports["hub0608:p3"]["phantom_history"] = [{"instance_id": "y", "name": "HX1500i Power Supply"}]
    return snap, ports


def test_socket_evidence_levels_and_label():
    snap, ports = _gerald_with_evidence()
    assert tm.socket_evidence(ports["pch:HS01"])["level"] == "strong"
    assert tm.socket_evidence(ports["hub0608:p3"])["level"] == "header"
    assert tm.socket_evidence(ports["pch:HS05"])["level"] == "weak"          # _UPC connectable only
    assert tm.socket_evidence(ports["pch:HS09"])["level"] == "weak"          # _UPC Type-C flag only
    hub_only = dict(ports["hub0608:p3"], phantom_history=None)
    assert tm.socket_evidence(hub_only)["level"] == "weak"                    # hub-port _PLD user_visible is weak
    # 'user-accessible' only with evidence beyond _UPC
    assert tm.port_label(snap, "pch:HS01") == "port 1 (HS01, USB 3, not USB-C, user-accessible)"
    assert tm.port_label(snap, "pch:HS05") == "port 5 (HS05, USB 3, not USB-C)"
    assert tm.port_label(snap, "pch:HS15") == "port 15 (HS15, USB 2.0-only)"


def test_header_evidence_port_ranked_last():
    snap, ports = _gerald_with_evidence()
    pred = tm.predict(snap, [{"camera_key": C922_KEY, "mode": "MJPG 1280x720@30"},
                             {"camera_key": GENERIC_KEY, "mode": "MJPG 1280x720@30"}], build_cache())
    sugg = tm.suggest_ports(snap, pred["conflicts"][0], GENERIC_KEY, build_cache(), prediction=pred)
    order = [p["port_id"] for g in sugg for p in g["ports"]]
    assert order[0] == "pch:HS01"                                             # strong evidence first
    assert order[-1] == "hub0608:p3"                                          # PSU phantom: internal header, last
    assert order.index("pch:HS05") < order.index("pch:HS15") < order.index("hub0608:p1")


def _conflict_and_sugg():
    snap, pred = _predict("MJPG 1280x720@30")
    c = pred["conflicts"][0]
    sugg = tm.suggest_ports(snap, c, GENERIC_KEY, build_cache(), prediction=pred)
    return c, sugg, tm.stay_here_alternatives(snap, c, build_cache())


def test_message_eio_wording():
    c, sugg, alts = _conflict_and_sugg()
    f = dict(tm.classify_failure("windows", "OSError(5)", CONTENTION), loser=GENERIC_KEY)
    msg = tm.build_message(c, f, sugg, alts)
    assert "probably a USB bandwidth error (a DirectShow start error, FFmpeg: I/O error)." in msg
    assert "access denied" not in msg and "see details" not in msg


def test_message_timeout_not_called_bandwidth():
    c, sugg, alts = _conflict_and_sugg()
    f = dict(tm.classify_failure("windows", "timeout", {"api": "pyav_ds"}), loser=GENERIC_KEY)
    msg = tm.build_message(c, f, sugg, alts)
    assert "USB Camera did not start (timed out); this may be a USB bandwidth problem." in msg
    assert "failed with a USB bandwidth error" not in msg


def test_message_staggered_wording():
    c, sugg, alts = _conflict_and_sugg()
    f = dict(tm.classify_failure("windows", 0x800718CF, {"api": "mf"}), loser=GENERIC_KEY, stagger_s=2.5,
             loser_position="last")
    msg = tm.build_message(c, f, sugg, alts)
    want = ("When I opened them both one after another, 2.5 s apart, USB Camera (opened last) failed with a USB "
            "bandwidth error (0x800718CF: not enough USB bandwidth).")
    assert want in msg
    assert "at the same time" not in msg


def test_stay_here_falls_back_to_lower_fps_only_when_needed():
    snap, pred = _predict("MJPG 1280x720@30")
    c = pred["conflicts"][0]
    cache = build_cache()
    cache.entries = {k: v for k, v in cache.entries.items()
                     if not (k.startswith("046d:085c") and k.endswith("640x480@30"))}
    alts = tm.stay_here_alternatives(snap, c, cache)
    assert alts[0]["mode_text"] == "1920x1080 MJPEG 5 fps" and not alts[0]["keeps_fps"]


def test_mode_alt_cache_merge():
    a, b = tm.ModeAltCache(), tm.ModeAltCache()
    a.put("046d", "085c", "0016", "MJPG", 640, 480, 30, 4, 640, 1, source="seed")
    b.put("046d", "085c", "0016", "MJPG", 640, 480, 30, 4, 640, 1, source="observed")
    b.put("046d", "085c", "0016", "YUY2", 1920, 1080, 5, 11, 1020, 3, source="observed")
    assert a.merge(b, overwrite=False) == 1
    assert a.get_mode("046d", "085c", "0016", "MJPG 640x480@30")["source"] == "seed"
    assert a.merge(b) == 2
    assert a.get_mode("046d", "085c", "0016", "MJPG 640x480@30")["source"] == "observed"
