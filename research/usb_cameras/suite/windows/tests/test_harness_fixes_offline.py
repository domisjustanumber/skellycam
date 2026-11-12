"""Offline tests for the 2026-11-08 harness pass (no camera): the "Harness bugs that affect conclusions" fixes of
docs/windows_results_20261106.md section 11, the W-CYC reliability profile, the USB link check, plan mode, the
tier-0-only summary and W-TS cells (Dom 2026-11-09) and the FIFO camera lock.

    uv run --isolated --python 3.12 --no-project --with pytest pytest \
        research/usb_cameras/suite/windows/tests/test_harness_fixes_offline.py -c research/usb_cameras/suite/common/tests/pytest.ini

Nothing here opens a camera: every camera command is a fake, the camera-lock tests use temporary lock files, and
the DS-leg runner test runs ``python -c`` children only.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
WIN = HERE.parent
SUITE = WIN.parent
RESEARCH = SUITE.parent
for p in (str(SUITE), str(WIN), str(WIN / "helpers"), str(HERE), str(RESEARCH / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows suite")

import capkit as ck  # noqa: E402
import suitectx  # noqa: E402
from common import rating, topology_model as tm  # noqa: E402

R2 = RESEARCH / "results" / "windows" / "Gerald" / "suite_20261106T224912Z"
KIYO_MF = r"\\?\usb#vid_1532&pid_0e05&mi_00#a&1#{e5323777-f976-4f5b-9b55-b94699c46e44}\global"
KIYO_DS = r"\\?\usb#vid_1532&pid_0e05&mi_00#a&1#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
C922_MF = r"\\?\usb#vid_046d&pid_085c&mi_00#8&2#{e5323777-f976-4f5b-9b55-b94699c46e44}\global"


def _cams():
    return [{"key": "c922", "name": "c922", "is_kiyo": False, "vid": "046d", "pid": "085c", "mf_symlink": C922_MF,
             "ds_path": C922_MF.replace("e5323777-f976-4f5b-9b55-b94699c46e44", "65e8773d-8f56-11d0-a3b9-00a0c9223196"),
             "last_arrival": "2026-11-08T10:00:00Z", "speed": "HS",
             "port_connection": {"legacy_speed": "high", "v2_flags": {"op_ss": False, "ss_capable": False},
                                 "port_protocols": ["usb1.1", "usb2.0"], "bcd_usb": "0200"}},
            {"key": "kiyo", "name": "USB Video Device", "is_kiyo": True, "vid": "1532", "pid": "0e05",
             "mf_symlink": KIYO_MF, "ds_path": KIYO_DS, "last_arrival": "2026-11-08T12:00:00Z", "speed": "HS",
             "port_path": "PCIROOT(0)#PCI(1400)#USBROOT(0)/3", "bcd_usb": "0320",
             "port_connection": {"legacy_speed": "high", "v2_flags": {"op_ss": False, "ss_capable": False},
                                 "port_protocols": ["usb1.1", "usb2.0"], "bcd_usb": "0320"}}]


def _ctx(tmp_path, cams=None, **args):
    ctx = suitectx.build_ctx(suitectx.default_args(**args), out_dir=tmp_path / "out", raw_dir=tmp_path / "raw",
                             cameras=cams if cams is not None else _cams())
    ctx.arrival_fn = lambda cs: {"cameras": {c["key"]: {"present": True, "last_arrival": c.get("last_arrival"),
                                                        "problem_code": 0} for c in cs}}
    return ctx


# ================================================================================================ mode scope
def test_capkit_scope_is_exactly_720_lines(tmp_path):
    ctx = _ctx(tmp_path)
    modes = [ck.Mode(1920, 1080, 30, 1), ck.Mode(1280, 720, 30, 1), ck.Mode(1280, 720, 60, 1), ck.Mode(960, 720, 30, 1),
             ck.Mode(1280, 720, 15, 1)]
    kept, rec = ck.scoped(ctx, modes)
    assert [m.text for m in kept] == ["MJPG 1280x720@30", "MJPG 1280x720@60", "MJPG 960x720@30"]
    assert rec["scope"]["max_height"] == 720 and rec["excluded"] == 2
    ctx.args.max_height = 0
    assert len(ck.scoped(ctx, modes)[0]) == 4


# ================================================================================================ suitectx
def test_command_failed_rules():
    ok_controls = {"tool": "wincam", "subcommand": "controls", "controls": [], "error": None}
    assert suitectx.command_failed(ok_controls, {"rc": 0})[0] is False
    # wincam controls timed out: no "ok" key, an error block and exit_code 5 (11-06 M1)
    to = {"tool": "wincam", "subcommand": "controls", "exit_code": 5,
          "error": {"stage": "controls", "class": "timeout", "hr_name": "timeout"}}
    failed, err = suitectx.command_failed(to, {"rc": 5})
    assert failed and err["class"] == "timeout"
    assert suitectx.command_failed(None, {"rc": None, "timed_out": True})[0] is True
    assert suitectx.command_failed({"ok": False, "error": {"stage": "open"}}, {"rc": 4})[0] is True
    assert suitectx.command_failed({"device_not_answering": True}, {"rc": 0})[0] is True
    # not failures: a PyAV format fallback, a camera-lock timeout, a plan-mode result
    assert suitectx.command_failed({"ok": False, "format_fallback": True, "error": {"stage": "format"}},
                                   {"rc": 4})[0] is False
    assert suitectx.command_failed(None, {"rc": None, "lock_timed_out": True})[0] is False
    assert suitectx.command_failed(None, {"rc": None, "dry_run": True})[0] is False


def test_scan_camcmd_records_a_controls_timeout_as_first_failure(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    obj = {"tool": "wincam", "subcommand": "controls", "exit_code": 5, "utc_started": "2026-11-08T12:30:00Z",
           "error": {"stage": "controls", "class": "timeout", "hr_name": "timeout"}}
    monkeypatch.setattr(suitectx, "camcmd_run", lambda argv, t, **kw: {
        "argv": argv, "rc": 5, "stdout": json.dumps(obj), "stderr": "", "timed_out": False, "lock_timed_out": False,
        "elapsed_s": 3.1, "lock_wait_s": 0.0})
    ctx.camcmd([str(ctx.wincam), "controls", "--api", "mf", "--device", KIYO_MF, "--read-only"], 20)
    ff = ctx.first_failure["kiyo"]
    assert ff["class"] == "timeout" and ff["utc"] == "2026-11-08T12:30:00Z" and ff["source"] == "camcmd_scan"


def test_dry_run_camcmd_never_runs(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    ctx.dry_run = True

    def boom(*a, **k):
        raise AssertionError("a camera command ran in plan mode")
    monkeypatch.setattr(suitectx, "camcmd_run", boom)
    r = ctx.camcmd([str(ctx.wincam), "capture", "--api", "mf", "--device", KIYO_MF], 30)
    assert r["dry_run"] is True and r["rc"] is None and ctx.dry_run_commands
    assert not ctx.first_failure and not ctx.faults


def test_usb_link_report_and_kiyo_warning():
    rep = suitectx.usb_link_report(_cams(), fresh=False,
                                   now=suitectx._dt.datetime(2026, 11, 8, 13, 0, tzinfo=suitectx._dt.timezone.utc))
    k = rep["kiyo"]["kiyo"]
    assert k["speed"] == "HS" and k["superspeed"] is False and k["device_usb3_capable"] is True
    assert k["plug_in_age_s"] == 3600.0
    assert len(rep["warnings"]) == 1 and "not SuperSpeed" in rep["warnings"][0] and "continues" in rep["warnings"][0]
    ss = _cams()
    ss[1]["port_connection"] = {"legacy_speed": "super", "v2_flags": {"op_ss": True, "ss_capable": True},
                                "port_protocols": ["usb3"], "bcd_usb": "0320"}
    rep2 = suitectx.usb_link_report(ss)
    assert rep2["kiyo"]["kiyo"]["speed"] == "SS" and rep2["warnings"] == []


@pytest.mark.skipif(not (R2 / "discovery.json").exists(), reason="Gerald 2026-11-06 run not present")
def test_usb_link_report_on_the_stored_discovery():
    cams = json.loads((R2 / "discovery.json").read_text(encoding="utf-8"))["cameras"]
    rep = suitectx.usb_link_report(cams)
    assert {r["speed"] for r in rep["cameras"].values()} <= {"HS", "SS", "SS+", "FS", "LS", "unknown"}
    assert len(rep["kiyo"]) == 1


# ================================================================================================ runner
def test_plan_mode_prints_order_and_total_without_running_anything(tmp_path, monkeypatch, capsys):
    import run_suite as rs

    def boom(*a, **k):
        raise AssertionError("plan mode ran a command")
    monkeypatch.setattr(suitectx, "camcmd_run", boom)
    monkeypatch.setattr(suitectx, "discover", boom)
    disc = tmp_path / "discovery.json"
    disc.write_text(json.dumps({"cameras": _cams()}), encoding="utf-8")
    rc = rs.main(["--plan", "--plan-cameras", str(disc), "--out-dir", str(tmp_path / "plan")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Total estimate:" in out and "W-CYC" in out and "exactly 720 lines at >= 30 fps" in out
    assert "W-CYC profile: reliability" in out and "not SuperSpeed" in out
    assert "(none executed)" in out
    order = [ln.split()[1] for ln in out.splitlines() if re.match(r"\s*\d+\s+W-", ln)]
    assert order[:3] == ["W-ENV", "W-POLICY", "W-TOPO"] and order[-1] == "W-CYC"    # the long cycle test last
    assert not (RESEARCH / "results" / "windows" / suitectx.socket.gethostname() / "plan").exists()


def test_plan_order_keeps_the_kiyo_sensitive_captures_inside_the_wedge_window(tmp_path, monkeypatch, capsys):
    """Kiyo replugged at the run start (no last_arrival): W-TS and W-PYMF run before W-CYC-KIYO, the cameras go Kiyo
    first, and no KIYO_EARLY test is projected past KIYO_WEDGE_WARN_S (an order that puts one there exits 3)."""
    import run_suite as rs

    def boom(*a, **k):
        raise AssertionError("plan mode ran a command")
    monkeypatch.setattr(suitectx, "camcmd_run", boom)
    monkeypatch.setattr(suitectx, "discover", boom)
    cams = [{k: v for k, v in c.items() if k != "last_arrival"} for c in _cams()]
    disc = tmp_path / "discovery.json"
    disc.write_text(json.dumps({"cameras": cams}), encoding="utf-8")
    argv = ["--plan", "--plan-cameras", str(disc), "--out-dir", str(tmp_path / "plan")]
    assert rs.main(argv) == 0
    out = capsys.readouterr().out
    order = [ln.split()[1] for ln in out.splitlines() if re.match(r"\s*\d+\s+W-", ln)]
    # review round 3: the Kiyo control tests before W-CYC-KIYO's ~1,060 Kiyo stream starts
    # 2026-11-11: W-CYC-KIYO's ~1,360 Kiyo Pro starts come after everything else that needs the Kiyo Pro
    assert order.index("W-RAW") < order.index("W-TS") < order.index("W-PYMF") < order.index("W-CTRL-EFFECT") \
        < order.index("W-OCV-CTRL") < order.index("W-MULTI") < order.index("W-CYC-KIYO")
    assert "ORDER ERROR" not in out
    assert "Kiyo starts" in out and "Kiyo stream starts (" not in out     # no control test after > 250 starts
    cam_lines = [ln for ln in out.splitlines() if "  key " in ln]
    assert "(Kiyo)" in cam_lines[0]                                  # Kiyo first in ctx.cameras
    # an order that puts a Kiyo-sensitive capture after the long tests fails the plan
    bad = [t for t in rs.TESTS if t[0] != "W-PYMF"]
    bad.insert(bad.index(("W-KIYO", "w_kiyo")), ("W-PYMF", "w_pymf"))      # after W-CYC
    monkeypatch.setattr(rs, "TESTS", bad)
    assert rs.main(argv) == 3
    assert "ORDER ERROR" in capsys.readouterr().out
    # the old order (W-CYC-KIYO before the control tests) warns: Kiyo control work after > 250 projected starts
    old = [t for t in rs.TESTS if t[0] != "W-CYC-KIYO"]
    old.insert(old.index(("W-CTRL-EFFECT", "w_ctrl_effect")), ("W-CYC-KIYO", "w_cyc_kiyo"))
    monkeypatch.setattr(rs, "TESTS", old)
    rs.main(argv)
    out = capsys.readouterr().out
    assert "Kiyo stream starts (" in out and "W-CTRL-EFFECT: its Kiyo control work starts after" in out


def test_quick_resolves_the_quick_cyc_profile():
    import run_suite as rs
    a = rs.resolve_args(rs.build_parser().parse_args(["--quick"]))
    assert a.cyc_profile == "quick"
    a = rs.resolve_args(rs.build_parser().parse_args([]))
    assert a.cyc_profile == "reliability" and a.max_height == 720


def test_missing_optional_modules_are_left_out(monkeypatch):
    import run_suite as rs
    monkeypatch.setattr(rs, "module_exists", lambda name: name != "w_raw")
    a = rs.resolve_args(rs.build_parser().parse_args([]))
    plan, out = rs.drop_missing_optional(a, rs.selected(a))
    assert ("W-RAW", "w_raw") in out and all(t != "W-RAW" for t, _ in plan)
    a = rs.resolve_args(rs.build_parser().parse_args(["--only", "W-RAW"]))
    plan, out = rs.drop_missing_optional(a, rs.selected(a))
    assert plan == [("W-RAW", "w_raw")] and not out         # named explicitly: an error result, not silence


def test_summary_has_no_tier1_label(tmp_path):
    # tier 0 only (Dom 2026-11-09): no cell is labelled as a tier-1 optional extra any more
    import run_suite as rs
    h = {"label": "partial", "rating": "partial", "test": "W-TS", "camera": "c922", "tier": 1}
    assert "tier 1" not in rs._cell(h, {}) and rs._cell(h, {}) == "[partial](W-TS.json)"
    lines = rs.usb_link_section(suitectx.usb_link_report(_cams()))
    assert any("not SuperSpeed" in ln for ln in lines) and any("Plug-in age" in ln for ln in lines)


# ================================================================================================ W-CYC
def test_wcyc_fps_is_judged_for_every_api():
    import w_cyc
    mf = w_cyc.format_flags({"ok": True, "mode": "MJPG 1280x720@30", "fps_measured": 17.2, "negotiated_ok": True},
                            "mf")
    assert mf["fps_mismatch"] is True
    ds = w_cyc.format_flags({"ok": True, "mode": "MJPG 1280x720@30000/1001", "fps_measured": 29.9, "codec": "mjpeg"},
                            "ds")
    assert ds["fps_mismatch"] is False
    assert w_cyc.format_flags({"ok": True, "mode": "MJPG 1280x720@30"}, "mf")["fps_mismatch"] is None
    row = w_cyc._newproc_row(0, "mf", ck.Mode(1280, 720, 30, 1), {"ok": True, "fps_measured": 29.8,
                                                                  "frames": {"total": 30},
                                                                  "timings": {"open_to_first_frame_ms": 450.0}},
                             {"rc": 0}, 30)
    assert row["fps_measured"] == 29.8
    rows = w_cyc._norm_rows([dict(row), {**row, "fps_measured": 12.0}], "mf")
    from common import cycstats
    s = cycstats.summarize_cycles(rows)
    assert s["n_fps_judged"] == 2 and s["fps_mismatch_count"] == 1
    rv = w_cyc.rate_variant(s, False)
    assert rv["evidence"]["n_fps_judged"] == 2
    assert rv["summary_label"].startswith(rv["rating"]) and "rate < 90% of requested in 1/2" in rv["summary_label"]


def test_wcyc_fps_not_judged_on_short_cycles():
    """Smoke 2026-11-09: a 10-frame quick cycle's rate includes the start-up interval (Kiyo 25.6 fps over 10
    frames, 29.6 steady): not judged under FPS_MIN_FRAMES; judged from 20 frames on."""
    import w_cyc
    short = {"ok": True, "mode": "MJPG 1280x720@30", "fps_measured": 25.6, "negotiated_ok": True, "frames": 10}
    assert w_cyc.format_flags(short, "mf")["fps_mismatch"] is None
    assert w_cyc.format_flags({**short, "frames": 30}, "mf")["fps_mismatch"] is True
    assert w_cyc.format_flags({**short, "frames": 30, "fps_measured": 28.8}, "mf")["fps_mismatch"] is False
    rows = w_cyc._norm_rows([dict(short), dict(short)], "mf")
    from common import cycstats
    summ = cycstats.summarize_cycles(rows)
    assert summ["n_fps_judged"] == 0 and summ["fps_mismatch_count"] == 0
    rv = w_cyc.rate_variant(summ, False)
    assert "rate <" not in (rv.get("summary_label") or "") and "N too small" in rv["evidence"]["fps_not_judged"]


def test_first_failure_is_device_level_only(tmp_path, monkeypatch):
    """Smoke 2026-11-09: opencv_ds cycle exit 4 (the Kiyo negotiated YUY2, every cycle streamed) became the Kiyo's
    'first failure'. It is kept as first_any_failure; first_failure waits for a device-level failure."""
    ctx = _ctx(tmp_path)
    mism = {"tool": "opencv_ds", "ok": False, "exit_code": 4, "error": None,
            "summary": {"cycles_run": 2, "streamed_ok": 2, "ok": 0, "failed": 2}}
    assert suitectx.command_failed(mism, {"rc": 4})[0] is True
    assert suitectx.device_level_failure(mism, {"rc": 4}, {}) is False
    assert suitectx.device_level_failure({**mism, "summary": {"cycles_run": 2, "streamed_ok": 1}}, {"rc": 4}, {})
    assert suitectx.device_level_failure({"ok": False, "error": {"stage": "open", "hr": "0x8007001F"}}, {"rc": 4},
                                         {"stage": "open", "hr": "0x8007001F"})
    assert suitectx.device_level_failure(None, {"rc": None, "timed_out": True}, {})
    monkeypatch.setattr(suitectx, "camcmd_run", lambda argv, t, **kw: {
        "argv": argv, "rc": 4, "stdout": json.dumps(mism), "stderr": "", "timed_out": False, "lock_timed_out": False,
        "elapsed_s": 3.1, "lock_wait_s": 0.0})
    ctx.camcmd(["uv", "run", "--script", r"C:\h\opencv_ds.py", "cycle", "--device", KIYO_DS], 20)
    assert "kiyo" not in ctx.first_failure
    assert ctx.first_any_failure["kiyo"]["device_level"] is False
    dev = {"tool": "wincam", "ok": False, "exit_code": 4, "error": {"stage": "open", "hr": "0x8007001F"}}
    monkeypatch.setattr(suitectx, "camcmd_run", lambda argv, t, **kw: {
        "argv": argv, "rc": 4, "stdout": json.dumps(dev), "stderr": "", "timed_out": False, "lock_timed_out": False,
        "elapsed_s": 3.1, "lock_wait_s": 0.0})
    ctx.camcmd([str(ctx.wincam), "controls", "--api", "mf", "--device", KIYO_MF, "--read-only"], 20)
    assert ctx.first_failure["kiyo"]["stage"] == "open" and ctx.first_failure["kiyo"]["device_level"] is True
    assert ctx.first_any_failure["kiyo"]["device_level"] is False         # the earlier one is kept
    rep_ = ctx.fault_report()
    assert rep_["first_any_failure"]["kiyo"] and rep_["first_failure"]["kiyo"]["stage"] == "open"


def test_wcyc_profiles_and_estimate(tmp_path):
    import w_cyc
    ctx = _ctx(tmp_path, cycles=50, proc_cycles=15, frames=30)
    ctx.args.cyc_profile = "reliability"
    vc = w_cyc.variant_counts(ctx)
    assert vc["mf_inproc"] >= 381 and vc["ds_ffmpeg_inproc"] >= 381
    assert vc["mf_newproc"] == 400 and vc["ds_inproc"] == 50 and vc["opencv_skellycam"] == 15
    rel = w_cyc.estimate_s(ctx)
    ctx.args.cyc_profile = "standard"
    assert w_cyc.variant_counts(ctx)["mf_inproc"] == 50 and w_cyc.estimate_s(ctx) < rel
    ctx.args.cyc_profile = "quick"
    assert w_cyc.variant_counts(ctx)["mf_inproc"] == 4
    ctx.args.cyc_profile, ctx.args.reliability_cycles = "reliability", 500
    assert w_cyc.variant_counts(ctx)["ds_ffmpeg_inproc"] == 500
    assert [c["key"] for c in w_cyc.camera_order(_cams())] == ["kiyo", "c922"]
    # honest: 400 MF + 400 ffmpeg cycles per camera are hours, not minutes
    assert rel > 3600


def test_wcyc_inproc_argv_ffmpeg_engine_and_skellycam_framerate(tmp_path, monkeypatch):
    import w_cyc
    ctx = _ctx(tmp_path)
    seen = []
    monkeypatch.setattr(ctx, "camcmd", lambda argv, timeout_s, **kw: seen.append([str(a) for a in argv]) or
                        {"rc": 0, "stdout": "{}", "stderr": ""})
    monkeypatch.setattr(w_cyc, "_opencv_index", lambda c, cam: (3, "test"))
    m = ck.Mode(1280, 720, 30, 1)
    w_cyc._inproc(ctx, _cams()[0], "ds", m, None, 5, 30, tmp_path / "a", engine="ffmpeg")
    assert seen[-1][-2:] == ["--engine", "ffmpeg"]
    w_cyc._inproc(ctx, _cams()[0], "opencv", m, None, 5, 30, tmp_path / "b", set_order="skellycam-full",
                  sk_fps=w_cyc.SKELLYCAM_DEFAULT_FRAMERATE)
    i = seen[-1].index("--skellycam-framerate")
    assert seen[-1][i + 1] == "-1"
    names = [p[0] for p in w_cyc._plan(w_cyc.variant_counts(ctx), None)]
    assert names[:2] == ["mf_inproc", "ds_ffmpeg_inproc"] and "opencv_skellycam_fps30" in names


# ================================================================================================ W-KIYO
def test_kiyo_poll_time_is_after_the_lock(tmp_path, monkeypatch):
    import w_kiyo
    ctx = _ctx(tmp_path)
    j = {"tool": "wincam", "subcommand": "controls", "utc_started": "2026-11-08T12:00:40+00:00",
         "controls": [{"supported": True, "name": "exposure", "key": "cc.exposure", "get_ok": True, "value": -5}]}
    monkeypatch.setattr(ck, "get_controls", lambda *a, **k: (j, {"rc": 0, "lock_wait_s": 38.0}))
    p = w_kiyo.poll_once(ctx, _cams()[1], "mf")
    assert p["utc"] == "2026-11-08T12:00:40+00:00" and p["time_basis"] == "wincam utc_started"
    j2 = dict(j)
    j2.pop("utc_started")
    monkeypatch.setattr(ck, "get_controls", lambda *a, **k: (j2, {"rc": 0, "lock_wait_s": 38.0}))
    p2 = w_kiyo.poll_once(ctx, _cams()[1], "mf")
    lag = (w_kiyo._parse_utc(p2["utc"]) - w_kiyo._parse_utc(p2["utc_requested"])).total_seconds()
    assert abs(lag - 38.0) < 0.01
    assert w_kiyo._age_s_at("2026-11-08T12:00:00Z", "2026-11-08T12:10:00+00:00") == 600.0


def test_kiyo_round_records_problem_code_and_age_at_poll_time(tmp_path, monkeypatch):
    import w_kiyo
    ctx = _ctx(tmp_path)
    j = {"tool": "wincam", "utc_started": "2026-11-08T12:30:00+00:00",
         "controls": [{"supported": True, "name": "exposure", "key": "cc.exposure", "get_ok": True, "value": -5}]}
    monkeypatch.setattr(ck, "get_controls", lambda *a, **k: (j, {"rc": 0, "lock_wait_s": 1.0}))
    monkeypatch.setattr(ck, "wincam_activity", lambda c: {"ok": True, "devices": []})
    monkeypatch.setattr(w_kiyo, "vendor_processes", lambda c: {})
    poller = w_kiyo.KiyoPoller(ctx, [_cams()[1]], interval_s=10)
    poller.t_start = time.monotonic()
    poller.poll_round(0, 0.0)
    polls = poller.state["kiyo"]["polls"]
    assert len(polls) == 2 and all(p["problem_code"] == 0 and p["present"] is True for p in polls)
    assert polls[0]["plug_in_age_s"] == 1800.0          # 12:00 arrival, poll ran 12:30


def test_kiyo_loop_does_not_catch_up_back_to_back(tmp_path):
    import w_kiyo
    ctx = _ctx(tmp_path)
    starts = []

    class P(w_kiyo.KiyoPoller):
        def poll_round(self, i, sched, late_s=0.0):
            starts.append(time.perf_counter())
            if i < 2:
                time.sleep(0.3)          # two slow rounds (lock waits)

    p = P(ctx, [_cams()[1]], interval_s=0.1, max_s=5)
    p.t_start = time.monotonic()
    p.th = threading.Thread(target=p._loop, daemon=True)
    p.th.start()
    time.sleep(0.95)
    p.stop_ev.set()
    p.th.join(2)
    gaps = [b - a for a, b in zip(starts[2:], starts[3:])]
    # the old schedule ran the missed slots back to back (gaps ~0); now every later round waits the interval. The
    # loop schedules on time.monotonic (about 15.6 ms resolution on Windows), so a gap can come out ~0.08 s: the
    # bound separates "back to back" from "one interval" with that tick to spare
    assert gaps and min(gaps) >= 0.05


# ================================================================================================ camlock
def test_camlock_ticket_queue_is_fifo_and_cleans_dead_tickets(tmp_path):
    import camlock
    q, cnt, disp, lock = tmp_path / "q", tmp_path / "ticket", tmp_path / "queue.lock", tmp_path / "cam.lock"
    first = camlock.Ticket(q, cnt, disp)
    assert first.take()
    dead = q / "000000000000.99999"                       # a waiter that died: nobody holds its file
    dead.write_text("")
    second = camlock.Ticket(q, cnt, disp)
    assert second.take() and second.number == first.number + 1
    ahead = second.ahead()
    assert [p.name for p in ahead] == [first.path.name] and not dead.exists()
    # the second waiter must not take the camera lock while the first ticket is live, even though it is free
    fd, _ = camlock.acquire(0.4, queue=True, lock_path=lock, ticket=second)
    assert fd is None
    first.release()
    third = camlock.Ticket(q, cnt, disp)
    fd, t = camlock.acquire(2.0, queue=True, lock_path=lock, ticket=third)
    assert fd is not None and not any(q.iterdir())        # tickets are gone once the lock is held
    camlock._unlock(fd)
    import os
    os.close(fd)


# ================================================================================================ W-TS
def test_ts_mf_cells_are_tier0_only():
    # tier 0 only (Dom 2026-11-09): no mf:uvc_metadata "n/a" cell, no tier-1 sources, every cell tier 0
    import w_ts
    a = {"frames": 100}
    cam = {"key": "gen", "metadata_tier1": True}
    v, cells = w_ts.verdicts_for(cam, "mf", a, 100)
    assert v["tier"] == 0 and v["source"] in ("frame_index_fit", "mf_sample_time")
    assert set(cells) == {"mf:mf_sample_time", "mf:frame_index_fit"}
    assert all(c["tier"] == 0 and "optional" not in c for c in cells.values())


def test_ts_ffmpeg_route_uses_wallclock_pts_as_arrival():
    import w_ts
    rows = [{"seq": i, "pts_ns": i * 33_333_333 + (i % 3) * 1_000_000, "qpc_ns": None} for i in range(60)]
    a = w_ts.analyse_ds(rows, types.SimpleNamespace(fps=30.0), wallclock_pts=True)
    assert a["arrival_basis"].startswith("ffmpeg CLI") and "frame_index_fit_arrival" in a
    s = w_ts.rate_sources("ds_ffmpeg", a, {"key": "kiyo"})
    assert "ffmpeg_pts" in s and "pyav_pts" not in s
    assert w_ts.APIS == ("mf", "ds", "ds_ffmpeg")


# ================================================================================================ W-MULTI
def test_multi_helper_timeout_counts_as_a_hang():
    import w_multi
    cmd = {"stdout": json.dumps({"ok": False, "timed_out": True, "error": {"class": "timeout", "reason": "ffmpeg timed out"},
                                 "frames": {"total": 0}}), "timed_out": False, "rc": 5}
    oc = w_multi._outcome("ds", cmd)
    assert oc["timed_out"] is True and oc["launcher_timed_out"] is False and oc["ok"] is False


class _MCtx:
    def __init__(self, faulted=None):
        self.cameras = _cams()
        self.logs, self.failures = [], []
        self._faulted = faulted or {}

    def log(self, m):
        self.logs.append(m)

    def arrivals(self):
        return {"utc": None, "cameras": {c["key"]: {"present": True} for c in self.cameras}}

    def camera_gated(self, key):
        return None

    def camera_faulted(self, key):
        return self._faulted.get(key)

    def fault_reason(self, key):
        return "device fault"

    def record_failure(self, cam, **kw):
        self.failures.append((cam["key"], kw))


def _multi(ctx):
    import w_multi
    m = w_multi.Multi.__new__(w_multi.Multi)
    m.ctx, m.faults, m.fault_log, m.timeline, m.reset_delays = ctx, {}, [], [], {}
    m.last_arrivals, m.last_fail_end, m.reenum, m.failures = ctx.arrivals(), {}, set(), []
    return m


def test_multi_faulted_sees_a_mid_test_fault():
    ctx = _MCtx(faulted={"kiyo": {"since_utc": "2026-11-08T12:04:02Z", "code": "0x8007001F", "source": "kiyo_poller"}})
    m = _multi(ctx)
    f = m.faulted(_cams()[1])
    assert f and f["since_utc"] == "2026-11-08T12:04:02Z" and "during" in f["source"]
    assert m.faulted(_cams()[0]) is None


def test_multi_rearrival_wait_uses_the_learned_delay(monkeypatch):
    import w_multi
    ctx = _MCtx()
    m = _multi(ctx)
    clock = {"t": 1000.0}
    monkeypatch.setattr(w_multi.time, "time", lambda: clock["t"])
    monkeypatch.setattr(w_multi.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    monkeypatch.setattr(m, "poll_arrivals", lambda tag: [])
    w = m.wait_rearrival("gen", 1000.0, "t")                     # no reset seen yet: the full 25 s
    assert w["timed_out"] and w["deadline_after_failure_s"] == 25.0
    m.reset_delays["gen"] = [10.05, 10.1]
    clock["t"] = 2000.0
    w = m.wait_rearrival("gen", 2000.0, "t")
    assert w["deadline_after_failure_s"] == pytest.approx(12.1) and 11.5 < w["waited_s"] < 13
    # seen absent during the wait: extended to 25 s
    clock["t"] = 3000.0
    m.timeline.append({"key": "gen", "kind": "absent", "t": 3000.5})
    w = m.wait_rearrival("gen", 3000.0, "t")
    assert w["extended_because_absent"] and w["deadline_after_failure_s"] == 25.0


def test_multi_child_failures_reach_the_first_failure_record(monkeypatch):
    ctx = _MCtx()
    m = _multi(ctx)
    monkeypatch.setattr(m, "health_check", lambda cam, mode, tag: {"ok": True})
    rec = {"api": "ds", "tag": "ds_all_together_001", "utc_end": None,
           "cameras": [{"camera": "c922", "ok": False, "frames": 0, "code": "OSError(5)", "stage": "open",
                        "timed_out": False, "domain": "d", "utc_start": "2026-11-08T12:00:00Z", "utc_end": None,
                        "mode": "MJPG 1280x720@30", "error": {}}]}
    m.classify_run(rec, {})
    assert ctx.failures and ctx.failures[0][0] == "c922" and ctx.failures[0][1]["utc"] == "2026-11-08T12:00:00Z"


# ================================================================================================ topology model
def test_intel_7a60_bracket_and_stay_here_score():
    pol = tm.policy_for({"pci_id": "8086:7A60", "name": "Intel xHCI"})
    assert pol["bracket"] == {"max_pass_us": 94.0, "min_fail_us": 101.1}
    assert tm.verdict_for(93.97, bracket=pol["bracket"]) == "fits"
    assert tm.verdict_for(101.4, bracket=pol["bracket"]) == "over"
    assert tm.policy_for({"pci_id": "8086:1138"}).get("bracket") is None
    cur = {"format": "MJPG", "fps": 60.0}
    five = {"format": "MJPG", "width": 1920, "height": 1080, "fps": 5.0}
    thirty = {"format": "MJPG", "width": 640, "height": 480, "fps": 30.0}
    assert tm._stay_score(thirty, cur) > tm._stay_score(five, cur)


# ================================================================================================ G-MJPEG
def test_mjpeg_counts_only_captured_modes_and_labels_rate():
    import w_mjpeg
    rows = [{"mode": "MJPG 1280x720@30", "skipped": "untested: device fault", "apis": {"mf": {"frames": 0}}},
            {"mode": "MJPG 1280x720@60", "apis": {"mf": {"frames": 90}}}]
    assert w_mjpeg.captured_modes(rows, "mf") == 1
    m = [{"mode": "MJPG 1280x720@30", "negotiated": True, "frames": 90, "strict_valid_fraction": 1.0,
          "sof_matches": True, "fps_measured": 17.2, "fps_other_api": 17.3, "fps_nominal": 30.0, "is_jpeg": True,
          "header_sha1_by_api": {"mf": "a", "ds": "a"}}]
    v = rating.rate_mjpeg(m)
    assert v["summary_label"].startswith(v["rating"]) and "rate not honoured in 1" in v["summary_label"]
    assert v["evidence"]["tier0_reference_off_nominal_modes"] == ["MJPG 1280x720@30"]
    assert "off nominal" in (v.get("note") or "")


# ================================================================================================ W-FMT-NOGRAB
def test_nograb_os_exposed_reference_and_hold_coverage():
    import w_fmt_nograb as N
    ref = {("MJPG", 1280, 720, 333333), ("YUY2", 2304, 1536, 5000000), ("YUY2", 640, 480, 333333)}
    listed = {("MJPG", 1280, 720, 333333), ("YUY2", 640, 480, 333333)}
    os_ref, only = N.os_exposed_reference(ref, listed)
    assert only == {("YUY2", 2304, 1536, 5000000)} and len(os_ref) == 2
    res = {"mf": {"idle": {"tested": True, "_listed": listed, "complete": False, "comparison": {}}},
           "hub_ioctl": {"idle": {"tested": True, "_listed": ref, "complete": True, "comparison": {"x": 1}}}}
    info = N.apply_os_reference(ref, res)
    assert info["applied"] and info["descriptor_only_modes"] == ["YUY2 2304x1536@2"]
    assert res["mf"]["idle"]["complete"] is True and res["mf"]["idle"]["reference"] == "OS-exposed"
    assert res["hub_ioctl"]["idle"]["complete"] is True and "_listed" not in res["hub_ioctl"]["idle"]
    rec = {"hold": {"begin_seen_ns": 1_000_000_000, "end_seen_ns": 3_500_000_000}}
    full = [{"t_ns": 1_000_000_000 + i * 120_000_000, "t_end_ns": 1_000_000_000 + i * 120_000_000 + 100_000_000}
            for i in range(22)]
    assert N.hold_coverage(rec, full) == pytest.approx(1.0, abs=0.02)
    early = full[:4]
    assert N.hold_coverage(rec, early) < 0.25
    assert N.combine_started(None, False) is False and N.combine_started(False, True) is True
    assert N.combine_started(None, None) is None


# ================================================================================================ W-ID
def test_id_natural_same_port_replug_and_port_move():
    import w_id
    prev = [{"key": "046d:085c:sn=B7", "vid": "046d", "pid": "085c", "serial": "B7", "port_path": "A/1",
             "last_arrival": "2026-11-06T10:00:00Z", "key_kind": "serial"},
            {"key": "4c4a:4a55:port=A/2", "vid": "4c4a", "pid": "4a55", "port_path": "A/2",
             "last_arrival": "2026-11-06T10:00:00Z"},
            {"key": "1532:0e05:port=A/3", "vid": "1532", "pid": "0e05", "port_path": "A/3",
             "last_arrival": "2026-11-06T10:00:00Z"}]
    now = [{**prev[0], "last_arrival": "2026-11-08T09:00:00Z"},
           {**prev[1], "last_arrival": "2026-11-08T09:00:00Z"},
           {"key": "1532:0e05:port=B/1", "vid": "1532", "pid": "0e05", "port_path": "B/1", "is_kiyo": True,
            "last_arrival": "2026-11-08T12:00:00Z"}]
    rep = w_id.compare_with_previous(now, prev)
    kinds = {r["key_now"]: r["kind"] for r in rep["cameras"]}
    assert kinds["1532:0e05:port=B/1"] == "port move" and kinds["4c4a:4a55:port=A/2"] == "same-port re-arrival"
    assert rep["same_port_replug"] is True and rep["port_move_serial"] is None
    r = rating.rate_id({"mf": [["a"]] * 20}, ["a"], {"reboot": None, "same_port_replug": True,
                                                     "port_move_serial": True})
    assert r["rating"] == "partial" and r["provisional"] is True        # provisional until A1


# ================================================================================================ W-ENV
def test_env_flags_a_kiyo_below_superspeed():
    import w_env
    cams = [{"name": "USB Video Device", "is_kiyo": True, "usb_speed_now": "HS", "plug_in_age_s": 600.0}]
    flags, _ = w_env.env_flags(cams, {}, {}, None, [], 1)
    assert any("not SuperSpeed" in f and "10.0 min" in f for f in flags)
    flags, _ = w_env.env_flags([{**cams[0], "usb_speed_now": "SS"}], {}, {}, None, [], 1)
    assert not any("SuperSpeed" in f for f in flags)


# ================================================================================================ W-CTRL-EFFECT
def test_ctrl_ds_leg_chains_sets_and_stops_the_capture(tmp_path):
    import w_ctrl_effect as ce
    py = sys.executable
    stop = tmp_path / "stop.flag"
    slow = [py, "-c", "import time; time.sleep(0.6)"]
    cap = [py, "-c", "import pathlib, time, sys\nwhile not pathlib.Path(sys.argv[1]).exists(): time.sleep(0.02)\n"
                     "print('{\"ok\": true}')", str(stop)]
    spec = {"before": [{"label": "set0", "argv": [py, "-c", "pass"], "timeout_s": 10}],
            "stream": [{"label": "set1", "argv": slow, "not_before_s": 0.1, "after_prev_s": 0.0, "timeout_s": 10},
                       {"label": "set2", "argv": slow, "not_before_s": 0.2, "after_prev_s": 0.4, "timeout_s": 10}],
            "capture": {"argv": cap, "start_delay_s": 0.05, "stdout": str(tmp_path / "cap.json"),
                        "stderr": str(tmp_path / "cap.err"), "stop_timeout_s": 10},
            "stop_file": str(stop), "tail_s": 0.2}
    sp = tmp_path / "leg.json"
    sp.write_text(json.dumps(spec), encoding="utf-8")
    import subprocess
    r = subprocess.run([py, str(Path(ce.__file__)), "--ds-leg", str(sp)], capture_output=True, text=True, timeout=60)
    doc = json.loads(r.stdout.strip().splitlines()[-1])
    st = {s["label"]: s for s in doc["steps"]}
    # set2 waited for set1 to RETURN plus its gap (set1 took ~0.6 s), not a fixed slot
    assert st["set2"]["t_start_ns"] >= st["set1"]["t_end_ns"] + 0.39e9
    assert st["set0"]["t_end_ns"] <= doc["capture"]["t_start_ns"]
    assert doc["capture"]["rc"] == 0 and stop.exists() and '"ok": true' in doc["capture"]["stdout"]


# ================================================================================================ safety
def test_nothing_in_the_harness_writes_the_registry_or_restarts_devices():
    files = list((SUITE / "common").glob("*.py")) + list(WIN.glob("*.py")) + list((WIN / "tests").glob("w_*.py")) + \
        list((WIN / "helpers").glob("*.py")) + [RESEARCH / "tools" / "camlock.py"]
    bad = re.compile(r"RegSetValue|SetValueEx|winreg\.(Set|Create|Delete)|reg(\.exe)?\s+(add|delete)|pnputil|"
                     r"Disable-PnpDevice|restart-device|remove-device|CM_Disable_DevNode|CM_Query_And_Remove",
                     re.I)
    hits = [f"{f.name}:{i + 1}" for f in files for i, line in enumerate(f.read_text(encoding="utf-8").splitlines())
            if bad.search(line) and not line.lstrip().startswith(("#", "-", "*")) and "No device restart" not in line
            and "never" not in line.lower() and "no `pnputil" not in line.lower()]
    assert hits == []
