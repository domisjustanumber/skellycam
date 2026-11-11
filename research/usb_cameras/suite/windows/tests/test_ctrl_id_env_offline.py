"""Offline unit tests for the W-CTRL-EFFECT / W-CTRL-LIST / W-ID / W-POLICY / W-ENV fixes of 2026-11-06
(analysis ctrl_id_env.md B1-B7, B9-B11, V1-V3 and its verifier notes). No camera, no registry write.

    uv run --isolated --python 3.12 --no-project --with pytest --with numpy pytest suite/windows/tests/test_ctrl_id_env_offline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
WIN = HERE.parent
SUITE = WIN.parent
RESEARCH = SUITE.parent
for p in (str(SUITE), str(WIN), str(WIN / "helpers"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows suite")
RUN = RESEARCH / "results" / "windows" / "Gerald" / "suite_20261106T181941Z"


# ------------------------------------------------------------------------------------------- W-CTRL-EFFECT
def _ctl(name, value=1, get_ok=True, via="IAMCameraControl", hr_get="0x00000000"):
    c = {"name": name, "key": f"cc.{name}", "supported": True, "via": via, "value": value if get_ok else None,
         "caps_flags_names": ["auto", "manual"] if get_ok else [], "min": -11, "max": -2,
         "hr": {"iam_get": hr_get if via != "IKsControl" else None, "ks_get": hr_get if via == "IKsControl" else None}}
    c["get_ok"] = get_ok
    return c


def test_not_answering_detection():
    import w_ctrl_effect as ce
    # new wincam flag
    na, hr = ce.not_answering({"device_not_answering": True, "error": {"hr": "0x8007001F", "stage": "control_get"},
                               "controls": []}, {"rc": 4})
    assert na and hr == "0x8007001F"
    # legacy JSON (no get_ok): every device-backed control without a value; focal_length still answers
    legacy = [dict(_ctl("exposure", get_ok=False, via="IKsControl", hr_get="0x8007001F")),
              dict(_ctl("focal_length", value=0, via="IKsControl"))]
    for c in legacy:
        c.pop("get_ok")
    na, hr = ce.not_answering({"controls": legacy}, {"rc": 0})
    assert na and hr == "0x8007001F"
    # healthy
    assert ce.not_answering({"controls": [_ctl("exposure")]}, {"rc": 0}) == (False, None)
    # control query timed out / no JSON
    assert ce.not_answering(None, {"rc": None, "timed_out": True}) == (True, "timeout")
    # camera in use by another app is not a device fault
    assert ce.not_answering({"error": {"class": "in_use", "stage": "activate", "hr": "0xC00D3704"}, "controls": []},
                            {"rc": 4})[0] is False


def test_held_tolerance_and_flags():
    import w_ctrl_effect as ce
    assert ce.held(127, 2, 128, 1) is True          # C930e firmware rounding
    assert ce.held(-5, 2, -9, 1) is False           # reset at stream start
    assert ce.held(-9, 1, -9, 1) is False           # value right but back in auto
    assert ce.held(55, 2, 60, 5) is True            # one step of a step-5 control
    assert ce.held(None, None, 3, 1) is None
    gain = {"min": 0, "max": 255, "step": 1}
    assert ce.held(228, 2, 230, gain) is True        # C922 gain at the next stream start (1% of the span)
    assert ce.held(18, 2, 26, gain) is False         # C930e gain reset at stream start
    assert ce.held(-5, 2, -9, {"min": -11, "max": -2, "step": 1}) is False
    assert ce.step_tol({"min": 2000, "max": 6500, "step": 10}) == 45


def test_mf_held_from_record_new_and_old():
    import w_ctrl_effect as ce
    new = {"values": [26, 128, 230], "schedule": [
        {"control": "pa.gain", "at_ms": 0, "before_value": 26, "before_flags": 2},
        {"control": "pa.gain", "at_ms": 1000, "before_value": 18, "before_flags": 2}]}
    h = ce.mf_held_from_record(new, "gain", 1)
    assert h["held_at_first_frame"] is True and h["held_until_first_set"] is False and h["held_through_start"] is False
    old = {"values": [-9, -7, -4], "schedule": [{"control": "cc.exposure", "at_ms": 1000, "before_value": -9,
                                                  "before_flags": 2}]}
    h2 = ce.mf_held_from_record(old, "exposure", 1)
    assert h2["value_at_first_frame"] is None and h2["held_through_start"] is True


def test_listing_inputs_sources():
    import w_ctrl_effect as ce
    pc = {"per_control": {"cc.exposure": {"listed_mf": True, "listed_ds": True, "descriptor_listed_ok": True,
                                          "ranges_equal_mf_ds": False, "descriptor_backed": True}}}
    li = ce.listing_inputs(pc, "exposure")
    assert li["listed"] is True and li["range_matches_descriptor"] is False and "per_control" in li["source"]
    legacy = {"supported": {"pa.gain": {"mf": True, "ds": True}},
              "descriptor_to_ks": [{"ks": "pa.gain", "aspect": "value", "mf": True, "ds": True}],
              "mf_vs_ds_differences": [{"control": "pa.gain", "field": "value", "mf": 1, "ds": 2}]}
    li = ce.listing_inputs(legacy, "gain")
    assert li["listed"] is True and li["range_matches_descriptor"] is True     # value is state, not range
    tabs = {"mf": {"focus": {"min": 0, "max": 250, "step": 5, "default": 0, "caps_flags": 3}},
            "ds": {"focus": {"min": 0, "max": 250, "step": 5, "default": 0, "caps_flags": 3}}}
    li = ce.listing_inputs(None, "focus", tabs)
    assert li["listed"] is True and li["range_matches_descriptor"] is True and "no W-CTRL-LIST" in li["source"]
    assert ce.listing_inputs({"supported": {}}, "focus")["listed"] is False


def _run(eff=True, held=True, before_rb=True):
    return {"effect_ok": eff, "effect_after_ok": eff, "effect_before_ok": eff if held else False,
            "before_start_readback": before_rb, "after_start_readback": True, "held_through_start": held}


def test_rating_row_held_workaround_and_runs():
    import w_ctrl_effect as ce
    d = {"runs": [_run(held=False)] * 3}
    row = ce.control_rating_row("gain", d, {"listed": True, "range_matches_descriptor": True})
    assert row["before_start_ok"] is False and row["runs_ok"] == 0 and "reset at stream start" in row["workaround"]
    good = ce.control_rating_row("gain", {"runs": [_run()] * 3}, {"listed": True, "range_matches_descriptor": True})
    assert good["before_start_ok"] is True and good["runs_ok"] == 3 and good["workaround"] is None


def test_path_verdicts():
    import w_ctrl_effect as ce
    dead = {"controls": {"exposure": {"skipped": "device not answering: 0x8007001F"}},
            "device_not_answering": {"at": "initial_read", "hr": "0x8007001F"}}
    v = ce.path_verdict(dead, lambda n: {}, 3)
    assert v["rating"] == "no" and v["evidence"]["not_answering_hr"] == "0x8007001F"
    gate = {"controls": {}, "gate_fault": {"first_fault_utc": "2026-11-06T18:43:49Z", "test": "W-MJPEG",
                                           "code": "0x8007001F"}}
    assert ce.path_verdict(gate, lambda n: {}, 3)["rating"] == "untested"
    ok = {"controls": {"exposure": {"runs": [_run()] * 3}}}
    assert ce.path_verdict(ok, lambda n: {"listed": True, "range_matches_descriptor": True}, 3)["rating"] == "yes"
    # criterion 1 not fed -> no yes
    assert ce.path_verdict(ok, lambda n: {"listed": None, "range_matches_descriptor": None}, 3)["rating"] == "partial"


def test_gate_uses_suite_gate_and_fallback():
    import w_ctrl_effect as ce

    class Gate:     # the suitectx SuiteCtx gate surface capkit uses
        def __init__(self):
            self.faults, self.gated, self.marked = {}, set(), []

        def camera_faulted(self, key):
            return self.faults.get(key)

        def camera_gated(self, key):
            return self.faults.get(key) if key in self.gated else None

        def mark_fault(self, key, **kw):
            self.marked.append((key, kw.get("test"), kw.get("code"), kw.get("stage")))
            self.faults.setdefault(key, {"faulted": True, "since_utc": "t0", "code": kw.get("code"),
                                         "test": kw.get("test")})
            return self.faults[key]

        def clear_fault(self, key, **kw):
            self.faults.pop(key, None)

        def log(self, msg):
            pass

    g = Gate()
    assert ce.gate_fault(g, {"key": "k"}) is None
    assert ce.gate_report(g, {"key": "k"}, "MJPG 1280x720@30", "0x8007001F", "x", "mf") is True
    assert g.marked == [("k", "W-CTRL-EFFECT", "0x8007001F", "control_get")]
    # faulted during this test: not gated for this test, but visible as a current fault
    assert ce.gate_fault(g, {"key": "k"}) is None
    assert ce.gate_fault(g, {"key": "k"}, gated_only=False)["code"] == "0x8007001F"
    g.gated.add("k")
    f = ce.gate_fault(g, {"key": "k"})
    assert f["utc"] == "t0" and ce.gate_untested(g, {"key": "k"}, f)["rating"] == "untested"

    class Plain:    # no gate: capkit's fallback registry ctx.device_faults
        def log(self, msg):
            pass

    pl = Plain()
    assert ce.gate_fault(pl, {"key": "k"}) is None
    assert ce.gate_report(pl, {"key": "k", "name": "cam", "vid": "1532", "pid": "0e05"}, None, "0x8007001F", "x")
    assert ce.gate_fault(pl, {"key": "k"})["code"] == "0x8007001F"


@pytest.mark.skipif(not (RUN / "W-CTRL-EFFECT.json").exists(), reason="Gerald run not present")
def test_ctrl_effect_reanalysis_of_gerald_run():
    import w_ctrl_effect as ce
    out = ce.reanalyze(RUN)
    v = out["verdicts"]
    assert v["G-CTRL|046d:085c:sn=C922SN01|mf"]["rating"] == "yes"
    kiyo = [k for k in v if k.startswith("G-CTRL|1532:0e05")]
    assert kiyo and all(v[k]["rating"] == "no" for k in kiyo)
    c930 = [k for k in v if k.startswith("G-CTRL|046d:0843")]
    assert all(v[k]["rating"] == "partial" for k in c930)
    gen_mf = next(k for k in v if k.startswith("G-CTRL|4c4a") and k.endswith("|mf"))
    assert out["cells"][gen_mf]["held_through_start"]["gain"] == [False, False, False]


# ------------------------------------------------------------------------------------------- W-CTRL-LIST
def test_per_control_listing():
    import w_ctrl_list as cl
    mapping = [{"ks": "cc.exposure", "aspect": "value", "mf": True, "ds": True},
               {"ks": "cc.exposure", "aspect": "auto", "mf": True, "ds": False}]
    ix = {"mf": {"cc.exposure": {"supported": True}, "cc.focal_length": {"supported": True}},
          "ds": {"cc.exposure": {"supported": True}, "cc.focal_length": {"supported": True}}}
    diffs = [{"control": "cc.exposure", "field": "max", "mf": -2, "ds": -1}]
    pc = cl.per_control_listing(mapping, ix, diffs)
    assert pc["cc.exposure"]["ranges_equal_mf_ds"] is False and pc["cc.exposure"]["descriptor_listed_ok"] is True
    assert pc["cc.focal_length"]["descriptor_backed"] is False and pc["cc.focal_length"]["ranges_equal_mf_ds"] is True


@pytest.mark.skipif(not (RUN / "W-CTRL-LIST.json").exists(), reason="Gerald run not present")
def test_ctrl_list_reanalysis_drops_gctrl():
    import w_ctrl_list as cl
    out = cl.reanalyze(RUN)
    assert "G-CTRL" not in out["verdicts"] and out["verdicts"]["ctrl_list_equivalence"]["rating"] == "yes"
    assert all(x["cc.exposure"]["ranges_equal_mf_ds"] for x in out["per_control"].values())


# ------------------------------------------------------------------------------------------- W-ID
def test_id_per_api_full_verdicts():
    import w_id
    keys = ["a", "b"]
    v = w_id.per_api_verdicts({"mf": [keys] * 20, "opencv_dshow": [keys] * 20}, keys,
                              {"reboot": None, "same_port_replug": None, "port_move_serial": True}, 20)
    assert v["mf"]["rating"] == "partial" and v["mf"]["criteria"] and v["mf"]["provisional"] is True
    assert "caveat" in v["opencv_dshow"]["evidence"]
    assert w_id._runs_from_summary({"runs": 3, "first_run_keys": ["a", "b"], "order_stable": False})[-1] == ["b", "a"]


# ------------------------------------------------------------------------------------------- W-POLICY
def test_policy_rotation_multi_app():
    import w_policy as wp
    t = wp.traps_rot_multi([], [], {"available": False})
    assert [x["met"] for x in t] == [None, None]
    assert wp.traps_verdict(t)["rating"] == "partial"
    t = wp.traps_rot_multi([], [{"key": "HKCU\\x", "value": "MultiAppEnabled", "data": 1}], {"all_ok": True})
    assert t[0]["met"] is True and t[1]["met"] is False
    assert wp.traps_verdict(t)["summary_label"] == "partial (trap active)"
    t = wp.traps_rot_multi([{"key": "HKCU\\y", "value": "Rotation", "data": 0}],
                           [{"key": "HKCU\\MultiApp", "match": "key name"}], {"all_ok": False})
    assert t[0]["met"] is True and t[1]["met"] is None
    t = wp.traps_rot_multi([{"key": "k", "value": "VideoRotation", "data": 180}], [], {"all_ok": True})
    assert t[0]["met"] is False
    corr = wp.fmt_corroboration({"measurements": {"cameras": [
        {"key": "a", "counts": {"mf_mjpeg_types": 10, "mf_native_capture_modes": 20}},
        {"key": "b", "counts": {"mf_mjpeg_types": 0, "mf_native_capture_modes": 1}}]}}, ["a", "b"])
    assert corr["all_ok"] is False and corr["per_camera"]["a"]["ok"] is True


# ------------------------------------------------------------------------------------------- W-ENV
def test_env_metadata_note_and_virtual_flags():
    import w_env
    cams = [{"key": "c930", "name": "C930e", "metadata_tier1": False,
             "function_instance_id": "USB\\VID_046D&PID_0843&MI_00\\6&2206973f&0&0000"},
            {"key": "c922", "name": "C922", "metadata_tier1": True,
             "function_instance_id": "USB\\VID_046D&PID_085C&MI_00\\8&268da596&0&0000"}]
    inst = [{"function_instance": "USB\\VID_046D&PID_0843&MI_00\\6&2206973F&0&0000", "is_current_instance": True,
             "metadata_values": None},
            {"function_instance": "USB\\VID_046D&PID_0843&MI_00\\8&39DEC205&1&0000", "is_current_instance": False,
             "metadata_values": {"MetadataBufferSizeInKB0": 5}},
            {"function_instance": "USB\\VID_046D&PID_0843&MI_03\\8&39DEC205&1&0003", "is_current_instance": False,
             "metadata_values": {"MetadataBufferSizeInKB0": 5}}]
    # tier 0 only (Dom 2026-11-09): the registry value is a read-only environment note, not a tier fallback flag
    md = w_env.metadata_registry_note(cams, inst)
    assert [x["key"] for x in md["present_on_current_instance"]] == ["c922"]
    assert md["other_instances_with_value"] == ["USB\\VID_046D&PID_0843&MI_00\\8&39DEC205&1&0000",
                                                "USB\\VID_046D&PID_0843&MI_03\\8&39DEC205&1&0003"]
    virt = [{"api": "mf", "index": i, "friendly_name": f"NDI Webcam Video {i + 1}"} for i in range(4)] + \
           [{"api": "ds", "index": 8, "friendly_name": "OBS-Camera"}, {"api": "ds", "index": 9,
                                                                     "friendly_name": "OBS-Camera2"},
            {"api": "ds", "index": 12, "friendly_name": "SpoutCam"}]
    vs = w_env.virtual_camera_summary(virt)
    assert vs["mf"]["indices"] == "0-3" and vs["ds"]["indices"] == "8-9, 12" and vs["ds"]["names"]["OBS-Camera"] == 2
    flags, det = w_env.env_flags(cams, {}, {}, virt, inst, 2)
    assert any(f.startswith("virtual cameras registered") for f in flags)
    assert not any("tier" in f for f in flags) and "stale_tier1_metadata" not in det
    assert any(f.startswith("MetadataBufferSizeInKB<n> is set on the current instance of: C922") for f in flags)
    assert det["metadata_registry"]["present_on_current_instance"][0]["name"] == "C922"
