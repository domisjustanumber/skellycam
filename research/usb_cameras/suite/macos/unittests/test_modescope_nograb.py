"""Mode scope (plan 6, Dom 2026-11-08: exactly 720 lines at >= 30 fps) in the macOS streaming tests, M-FMT-NOGRAB (analysis and end to end against
the fake child runner), and G-CTRL criterion 1 fed from M-CTRL-LIST. Any OS; no device access."""
import json
import time

import pytest

import childutil
import fake_children
import fake_mac
import mac_modescope
import nograb
import run_suite
import suitectx

F = fake_mac.avf_format


def args(*flags):
    return run_suite.apply_defaults(run_suite.build_parser().parse_args(["--quick", *flags]))


def make_ctx(tmp_path, *flags, avf=None, runner=None):
    a = args(*flags)
    runner = runner or fake_children.FakeRunner(avf=avf)
    ctx = suitectx.SuiteCtx(out_dir=tmp_path / "out", raw_dir=tmp_path / "raw", args=a, cache_dir=tmp_path / "cache",
                            runner=runner, log_fn=lambda m: None, prelude={"product_version": "27.2", "arch": "arm64"})
    ctx.out_dir.mkdir(parents=True)
    ctx.args.hold_ms, ctx.args.nograb_baseline_s = 60.0, 0.15
    run_suite.discover(ctx)
    return ctx, runner


def cam_with(formats, uvc_frames=None):
    c = {"key": "k", "avf_formats": formats}
    if uvc_frames is not None:
        c["uvc"] = {"frames": uvc_frames}
    return c


# ---------------------------------------------------------------------------------------------- mode scope
@pytest.mark.parametrize("shim", [False, True])
def test_in_scope_rule_and_flags(monkeypatch, shim):
    if shim:  # the local copy behaves like common.modescope
        monkeypatch.setattr(mac_modescope, "_common", None)
    assert mac_modescope.in_scope(1280, 720, 30) and mac_modescope.in_scope(1280, 720, 29.97)
    # Dom 2026-11-08: exactly 720 lines; 1080p is out of scope by default and back in with max_height 0
    assert not mac_modescope.in_scope(1920, 1080, 29.97)
    assert mac_modescope.in_scope(1920, 1080, 29.97, max_height=0)
    assert not mac_modescope.in_scope(640, 480, 30) and not mac_modescope.in_scope(1280, 720, 25)
    a = args()
    assert (a.min_fps, a.min_height, a.max_height, a.all_modes) == (30.0, 720, 720, False)
    assert not mac_modescope.mode_ok(1920, 1080, 30, a) and mac_modescope.mode_ok(1920, 1080, 30, args("--max-height", "0"))
    assert "exactly 720 lines at >= 30 fps" in mac_modescope.text(a)
    a2 = args("--min-fps", "15", "--min-height", "480", "--all-modes")
    assert (a2.min_fps, a2.min_height, a2.all_modes) == (15.0, 480, True)
    assert mac_modescope.mode_ok(320, 240, 5, a2)


@pytest.mark.parametrize("shim", [False, True])
def test_scope_record_counts(monkeypatch, shim):
    if shim:  # the local copy behaves like common.modescope
        monkeypatch.setattr(mac_modescope, "_common", None)
    rec = mac_modescope.record_for_formats(args(), fake_mac.STD_FORMATS)
    # 420v 640x480@30, dmb1 640x480@15/@30, dmb1 1280x720@30, dmb1 1920x1080@30 -> 5 advertised, 1 in scope
    # (exactly 720 lines at >= 30 fps, Dom 2026-11-08)
    assert (rec["advertised"], rec["in_scope"], rec["excluded"]) == (5, 1, 4)
    assert (rec["n_advertised"], rec["n_excluded"]) == (5, 4)
    assert rec["scope"]["min_fps"] == 30 and rec["scope"]["min_height"] == 720 and rec["scope"]["max_height"] == 720
    assert rec["scope_source"] == ("macos local shim" if shim else "common.modescope")
    assert rec["in_scope_modes"] == ["dmb1 1280x720@30"]
    # --max-height 0: the old >= 720-line rule
    old = mac_modescope.record_for_formats(args("--max-height", "0"), fake_mac.STD_FORMATS)
    assert (old["advertised"], old["in_scope"], old["excluded"]) == (5, 2, 3)
    assert sorted(old["in_scope_modes"]) == ["dmb1 1280x720@30", "dmb1 1920x1080@30"]
    full = mac_modescope.record_for_formats(args("--all-modes"), fake_mac.STD_FORMATS)
    assert (full["advertised"], full["in_scope"], full["excluded"]) == (5, 5, 0)


def test_scoped_default_and_alt_modes():
    a = args()
    std = cam_with(fake_mac.STD_FORMATS)
    m, info = suitectx.pick_scoped_default(std, a)
    assert (m["w"], m["h"], m["fps"], m["subtype"]) == (1280, 720, 30.0, "dmb1") and "untested" not in info
    alt, why = suitectx.pick_scoped_alt(std, a, m)
    # exactly 720 lines: the only in-scope mode is 720p30, so no mode switch (never 640x480 or 1080p)
    assert alt is None
    a0 = args("--max-height", "0")  # the old >= 720-line rule
    alt0, _ = suitectx.pick_scoped_alt(std, a0, suitectx.pick_scoped_default(std, a0)[0])
    assert (alt0["w"], alt0["h"], alt0["fps"]) == (1920, 1080, 30.0)
    # no 720-line mode: untested (scope); under --max-height 0 the nearest in-scope MJPEG mode
    big = cam_with([F(0, "dmb1", 640, 480, [30.0]), F(1, "dmb1", 1920, 1080, [30.0]), F(2, "dmb1", 3840, 2160, [30.0])])
    m1, info1 = suitectx.pick_scoped_default(big, a)
    assert m1 is None and info1["untested"] == "scope"
    m2, info2 = suitectx.pick_scoped_default(big, a0)
    assert (m2["w"], m2["h"]) == (1920, 1080) and "nearest" in info2["why"]
    # 720p at 60 and 30 only: the mode switch uses 720p60
    c60 = cam_with([F(0, "dmb1", 1280, 720, [60.0, 30.0])])
    d60, _ = suitectx.pick_scoped_default(c60, a)
    a60, why60 = suitectx.pick_scoped_alt(c60, a, d60)
    assert d60["fps"] == 30.0 and a60["fps"] == 60.0 and "60 fps" in why60
    # nothing in scope: untested (scope); one in-scope mode only: no mode switch
    m3, info3 = suitectx.pick_scoped_default(cam_with([F(0, "dmb1", 640, 480, [30.0]), F(1, "dmb1", 1280, 720, [10.0])]), a)
    assert m3 is None and info3["untested"] == "scope"
    one = cam_with([F(0, "dmb1", 1280, 720, [30.0])])
    assert suitectx.pick_scoped_alt(one, a, suitectx.pick_scoped_default(one, a)[0])[0] is None
    # MJPEG offered only decoded (420v) at the descriptor's MJPEG sizes still counts as the MJPEG mode
    dec = cam_with([F(0, "420v", 1280, 720, [30.0]), F(1, "420v", 640, 480, [30.0])],
                   uvc_frames=[{"format": "MJPEG", "w": 1280, "h": 720, "fps": [30.0]}])
    m4, info4 = suitectx.pick_scoped_default(dec, a)
    assert (m4["w"], m4["subtype"]) == (1280, "420v") and "descriptor" in info4["why"]
    # --all-modes: the pre-scope choices
    aa = args("--all-modes")
    alt_all, _ = suitectx.pick_scoped_alt(std, aa, suitectx.pick_scoped_default(std, aa)[0])
    assert alt_all["w"] == 640


def scoped_out_avf():
    d = fake_mac.apple_silicon_avf()
    small = [F(0, "dmb1", 640, 480, [30.0, 15.0]), F(1, "420v", 1280, 720, [10.0])]
    d["devices"][1]["formats"] = small  # the generic camera: nothing at >= 30 fps and >= 720 lines
    return d


def test_camera_without_in_scope_mjpeg_is_untested_scope(tmp_path):
    ctx, _ = make_ctx(tmp_path, avf=scoped_out_avf())
    gen = "4c4a:4a55:port=bus01/1.2"
    out = {}
    for mod in ("m_topo", "m_fmt", "m_mjpeg", "m_cyc", "m_ts", "m_ctrl_effect", "m_multi"):
        out[mod] = run_suite.load_test_module(mod).run(ctx)
        assert not [e for e in out[mod]["errors"] if "traceback" in e], (mod, out[mod]["errors"])
    mj = {c["key"]: c for c in out["m_mjpeg"]["measurements"]["cameras"]}
    assert mj[gen]["rating"]["rating"] == "untested" and mj[gen]["rating"]["summary_label"] == "untested (scope)"
    assert mj[gen]["mode_scope"]["in_scope"] == 0 and mj[gen]["mode_scope"]["excluded"] == 3
    assert out["m_mjpeg"]["verdicts"]["G-MJPEG"]["per_camera"][gen] == "untested"
    cy = {c["key"]: c for c in out["m_cyc"]["measurements"]["cameras"]}
    assert cy[gen]["untested"] == "scope" and out["m_cyc"]["verdicts"]["Reliability"]["evidence"][gen] == "untested (scope)"
    assert {p["key"]: p.get("untested") for p in out["m_ts"]["measurements"]["cameras"]}[gen] == "scope"
    assert {p["key"]: p.get("untested") for p in out["m_ctrl_effect"]["measurements"]["cameras"]}[gen] == "scope"
    assert [x["camera"] for x in out["m_multi"]["measurements"]["scoped_out_cameras"]] == [gen]
    # every streaming test records the scope and the excluded count
    for mod in ("m_mjpeg", "m_cyc", "m_ts", "m_ctrl_effect", "m_multi"):
        sc = out[mod]["measurements"]["mode_scope"]
        assert sc["scope"]["min_fps"] == 30 and sc["excluded"] > 0 and gen in sc["per_camera"], mod
    # no capture ever asked for an out-of-scope mode (640x480 or 10 fps)
    for call in ctx.runner.calls:
        if "capture" in call or "cycle" in call:
            if "--format-index" in call:
                dev = next(d for d in ctx.avf_devices if d["unique_id"] == call[call.index("--device") + 1])
                f = dev["formats"][int(call[call.index("--format-index") + 1])]
                assert f["h"] >= 720, call


def test_multi_fits_side_under_scope_and_all_modes(tmp_path):
    order = ("m_topo", "m_fmt", "m_mjpeg", "m_multi")
    ctx, _ = make_ctx(tmp_path / "a", "--ep0")
    for mod in order:
        res = run_suite.load_test_module(mod).run(ctx)
    m = res["measurements"]
    gp = m["group_plans"]
    assert gp and gp[0]["fits_side"] == "fits-side not testable under mode scope"
    assert gp[0]["over_prediction"]["verdict"] == "over"
    labels = [x["label"] for x in m["attempts"]]
    assert any(lb.startswith("pair_over_") for lb in labels) and not any(lb.startswith("pair_fits_") for lb in labels)
    assert any(lb.startswith("all_together_") for lb in labels)  # cross-domain all-at-once runs still happen
    assert "not testable" in res["verdicts"]["G-BW"]["note_scope"]
    # --all-modes: the smallest mode is back, and C922 640x480 (alt 4) + generic is predicted to fit
    ctx2, _ = make_ctx(tmp_path / "b", "--ep0", "--all-modes")
    for mod in order:
        res2 = run_suite.load_test_module(mod).run(ctx2)
    gp2 = res2["measurements"]["group_plans"][0]
    assert gp2["fits_side"] == "predicted fits" and all("640x480" in t for t in gp2["fits_modes"])
    assert any(x["label"].startswith("pair_fits_") for x in res2["measurements"]["attempts"])


# ---------------------------------------------------------------------------------------------- nograb analysis
DESC = [{"format": "MJPEG", "w": 1280, "h": 720, "fps": [30.0, 15.0]},
        {"format": "MJPEG", "w": 640, "h": 480, "fps": [30.0]},
        {"format": "UNCOMPRESSED", "w": 640, "h": 480, "fps_range": [5.0, 30.0]}]


def test_completeness_mjpeg_and_raw_separately():
    full = [F(0, "dmb1", 1280, 720, [30.0, 15.0]), F(1, "dmb1", 640, 480, [30.0]),
            {"index": 2, "subtype": "yuvs", "w": 640, "h": 480, "ranges": [{"min_fps": 5.0, "max_fps": 30.0}]}]
    c = nograb.completeness(DESC, nograb.modes_from_avf(full))
    assert c["complete"] is True and c["per_kind"]["mjpeg"]["n"] == 3 and c["per_kind"]["raw"]["n"] == 1
    # 15 fps missing, and the raw mode offered only as a narrower range
    part = [F(0, "dmb1", 1280, 720, [30.0]), F(1, "dmb1", 640, 480, [30.0]),
            {"index": 2, "subtype": "yuvs", "w": 640, "h": 480, "ranges": [{"min_fps": 15.0, "max_fps": 30.0}]}]
    c2 = nograb.completeness(DESC, nograb.modes_from_avf(part))
    assert c2["complete"] is False and c2["per_kind"]["mjpeg"]["missing"] == ["mjpeg 1280x720@15"]
    assert c2["per_kind"]["raw"]["complete"] is False
    # MJPEG offered only decoded (420v): MJPEG incomplete, the decoded sizes show up as extras of kind raw
    dec = [F(0, "420v", 1280, 720, [30.0, 15.0]), F(1, "420v", 640, 480, [30.0])]
    c3 = nograb.completeness(DESC[:2], nograb.modes_from_avf(dec))
    assert c3["complete"] is False and "420v 1280x720" in c3["extra_in_method"]
    assert nograb.completeness(None, [])["complete"] is None
    assert nograb.completeness(DESC, None)["complete"] is None


def test_stream_disturbance_blocking_alt():
    step = int(1e9 / 30)
    frames = [i * step for i in range(60)] + [60 * step + int(0.4e9) + i * step for i in range(30)]
    d = nograb.stream_disturbance(frames, (55 * step, 62 * step), (0, 50 * step))
    assert d["disturbed"] is True and d["window_max_interval_ms"] > 400
    calm = nograb.stream_disturbance(frames, (10 * step, 20 * step), (0, 9 * step))
    assert calm["disturbed"] is False
    err = nograb.stream_disturbance(frames, (10 * step, 20 * step), (0, 9 * step),
                                    notes=[{"name": "AVCaptureSessionRuntimeErrorNotification", "host_ns": 15 * step}])
    assert err["disturbed"] is True
    assert nograb.stream_disturbance(frames, (10 * step, 20 * step), None)["disturbed"] is None
    assert nograb.blocking({"ok": True}, None)["blocks"] is False
    assert nograb.blocking({"ok": False}, {"ok": True})["blocks"] is True
    assert nograb.blocking({"ok": False}, {"ok": False})["blocks"] is None
    assert nograb.blocking({"not_applicable": "registry read"}, None)["blocks"] is False
    assert nograb.alt_evidence([0, 0], 0, False)["starts_stream"] is False
    assert nograb.alt_evidence([0, 3], 0, False)["starts_stream"] is True
    assert nograb.alt_evidence([9, 9], 9, True)["starts_stream"] is False
    assert nograb.alt_evidence([9, 11], 9, True)["starts_stream"] is True
    assert nograb.alt_evidence([None], 0, False)["starts_stream"] is None


def cond(**kw):
    base = {"ok": True, "complete": True, "starts_stream": False, "disturbed": None, "blocks": False,
            "streaming_elsewhere": False}
    return base | kw


def test_rate_method():
    good = {"idle": cond(), "stream_avf": cond(streaming_elsewhere=True, disturbed=False),
            "stream_api2": {"skipped": "no second API", "streaming_elsewhere": True}}
    assert nograb.rate_method(good)["rating"] == "yes"
    assert nograb.rate_method(good | {"stream_avf": cond(streaming_elsewhere=True, disturbed=True)})["rating"] == "partial"
    assert nograb.rate_method(good | {"stream_avf": cond(streaming_elsewhere=True, disturbed=False, complete=False)}
                              )["rating"] == "partial"  # complete when idle only
    assert nograb.rate_method(good | {"idle": cond(blocks=True)})["rating"] == "partial"
    assert nograb.rate_method(good | {"idle": cond(complete=False)})["rating"] == "no"
    assert nograb.rate_method(good | {"idle": cond(starts_stream=True)})["rating"] == "no"
    assert nograb.rate_method(good | {"idle": cond(ok=False, complete=None)})["rating"] == "no"
    assert nograb.rate_method(good | {"idle": cond(complete=None)})["rating"] == "untested"
    r = nograb.rate_method({}, not_implementable="cannot list without opening capture")
    assert r["rating"] == "no" and "cannot list" in r["summary_label"]


def test_ioreg_format_info_finds_only_a_config_descriptor():
    cfg = fake_mac.uvc_config(fake_mac.C922_ALTS, [(1280, 720, [30.0])])
    node = {"IORegistryEntryName": "cam", "idVendor": 1133, "IORegistryEntryChildren": [
        {"IORegistryEntryName": "IOUSBHostInterface@1", "bInterfaceClass": 14, "bAlternateSetting": 0}]}
    info = nograb.ioreg_format_info(node)
    assert info["config_descriptor_hex"] is None
    node["IORegistryEntryChildren"][0]["Configuration Descriptor"] = cfg
    info2 = nograb.ioreg_format_info(node)
    assert info2["config_descriptor_hex"] == cfg.hex() and "Configuration Descriptor" in info2["config_descriptor_at"]


def test_hold_handshake(tmp_path):
    rel = tmp_path / "release"
    t0 = time.monotonic()
    h = childutil.hold(30, str(tmp_path / "m.json"), None)
    assert h["released_by"] == "timer" and json.loads((tmp_path / "m.json").read_text())["hold_ms"] == 30
    h2 = childutil.hold(10, None, str(rel), cap_ms=80)
    assert h2["released_by"] == "cap" and h2["held_ms"] >= 79
    rel.write_text("x")
    assert childutil.hold(10, None, str(rel))["released_by"] == "release_file"
    assert time.monotonic() - t0 < 5


# ---------------------------------------------------------------------------------------------- M-FMT-NOGRAB
def nograb_run(tmp_path, *flags, setup=None):
    ctx, runner = make_ctx(tmp_path, *flags)
    if setup:
        setup(runner, ctx)
    run_suite.load_test_module("m_fmt").run(ctx)  # caches descriptors with --ep0
    res = run_suite.load_test_module("m_fmt_nograb").run(ctx)
    assert not [e for e in res["errors"] if "traceback" in e], res["errors"]
    json.dumps(res, default=str)
    return res, runner


def test_nograb_end_to_end_with_ep0(tmp_path):
    res, runner = nograb_run(tmp_path, "--ep0")
    v = {k: x["rating"] for k, x in res["verdicts"].items()}
    assert v == {"fmt_nograb:avf_formats": "yes", "fmt_nograb:ioreg": "no", "fmt_nograb:ep0_descriptors": "yes",
                 "fmt_nograb": "yes"}
    cams = res["measurements"]["cameras"]
    assert any(c["is_kiyo"] for c in cams) and len(cams) == 4  # every camera, the Kiyo included
    c = cams[0]
    avf = c["methods"]["avf_formats"]
    assert avf["idle"]["complete"] and avf["stream_avf"]["complete"] and avf["stream_avf"]["disturbed"] is False
    assert avf["stream_api2"]["skipped"].startswith("macOS has no second capture API")
    assert avf["idle"]["hold"]["held_ms"] >= 59 and avf["idle"]["probe"]["ok"] is True
    assert c["methods"]["ioreg"]["idle"]["completeness"]["reason"].startswith("IORegistry carries no format")
    assert c["conditions"]["stream_avf"]["stream"]["stopped_by"] == "stop_file"
    # the streamer and every hold ended: no child left waiting
    assert runner.holds_active == 0


def test_nograb_without_ep0_is_untested_not_guessed(tmp_path):
    res, _ = nograb_run(tmp_path)
    assert res["verdicts"]["fmt_nograb:avf_formats"]["rating"] == "untested"
    assert res["verdicts"]["fmt_nograb"]["not_tested_methods"] == {"ep0_descriptors": "needs --ep0 (opt-in)"}


@pytest.mark.parametrize("switch,field,expect", [("disturb_on_hold", "disturbed", "partial"),
                                                 ("block_on_hold", "blocks", "partial"),
                                                 ("vs_alt_on_hold", "starts_stream", "no")])
def test_nograb_detects_disturbance_blocking_and_streaming(tmp_path, switch, field, expect):
    def setup(runner, ctx):
        setattr(runner, switch, 3 if switch == "vs_alt_on_hold" else True)
        if switch == "disturb_on_hold":
            ctx.args.hold_ms = 400.0  # a gap well above the 100 ms threshold of a 33 ms stream
    res, _ = nograb_run(tmp_path, "--ep0", setup=setup)
    c = res["measurements"]["cameras"][0]
    rows = c["methods"]["avf_formats"]
    hit = rows["stream_avf"][field] if field == "disturbed" else (rows["idle"][field] or rows["stream_avf"][field])
    assert hit is True, rows
    assert c["ratings"]["avf_formats"]["rating"] == expect
    assert res["measurements"]["cameras"][0]["methods"]["ioreg"]["idle"]["blocks"] is False  # holds nothing


def test_nograb_without_permission_measures_idle_only(tmp_path):
    ctx, _ = make_ctx(tmp_path, "--ep0")
    ctx.tcc = "denied"
    run_suite.load_test_module("m_fmt").run(ctx)
    res = run_suite.load_test_module("m_fmt_nograb").run(ctx)
    c = res["measurements"]["cameras"][0]
    assert c["conditions"]["stream_avf"]["skipped"] == "camera permission is denied"
    assert c["methods"]["avf_formats"]["idle"]["complete"] is True
    assert c["ratings"]["avf_formats"]["rating"] == "partial"  # disturbance / blocking not measurable
    assert "M-FMT-NOGRAB" in run_suite.SELF_GATED


def test_nograb_gated_camera_is_untested(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    kiyo = next(c for c in ctx.cameras if c["is_kiyo"])
    ctx.camera_gated = lambda cam: ({"first_fault_utc": "2026-11-06T18:00:00Z", "code": "0x8007001F"}
                                    if cam["key"] == kiyo["key"] else None)
    res = run_suite.load_test_module("m_fmt_nograb").run(ctx)
    k = next(c for c in res["measurements"]["cameras"] if c["key"] == kiyo["key"])
    assert k["untested"] == "device fault" and k["ratings"]["avf_formats"]["rating"] == "untested"


# ---------------------------------------------------------------------------------------------- G-CTRL criterion 1
def test_ctrl_effect_criterion1_from_ctrl_list(tmp_path):
    ctx, _ = make_ctx(tmp_path, "--ep0")
    for mod in ("m_fmt", "m_ctrl_list"):
        cl = run_suite.load_test_module(mod).run(ctx)
    pc = cl["measurements"]["cameras"][0]["per_control"]
    assert pc["avf"]["exposure"]["listed"] is True and pc["avf"]["exposure"]["range_matches_descriptor"] is True
    assert pc["ep0"]["exposure_time_absolute"]["range_well_formed"] is True
    res = run_suite.load_test_module("m_ctrl_effect").run(ctx)
    g = res["verdicts"]["G-CTRL"]
    assert g["criteria"][0]["met"] is True and g["criterion1_source"] == ["M-CTRL-LIST per_control (this run)"]
    rows = g["evidence"]["controls"]
    assert not any(r["name"] == "avf_focus_lock" for r in rows)  # neither AVF nor the descriptor has focus
    # from the result file when the store is gone (test run alone after an earlier M-CTRL-LIST)
    ctx.write("m_ctrl_list", cl)
    ctx.store.clear()
    res2 = run_suite.load_test_module("m_ctrl_effect").run(ctx)
    assert any("m_ctrl_list.json" in s for s in res2["verdicts"]["G-CTRL"]["criterion1_source"])


def test_ctrl_effect_criterion1_without_ctrl_list(tmp_path):
    ctx, _ = make_ctx(tmp_path, "--ep0")
    res = run_suite.load_test_module("m_ctrl_effect").run(ctx)
    src = res["verdicts"]["G-CTRL"]["criterion1_source"]
    assert any("own" in s for s in src), src


def test_per_control_record_rules():
    cl = run_suite.load_test_module("m_ctrl_list")
    flags = {"exposure_modes_supported": {"locked": False}, "wb_modes_supported": {"locked": True},
             "focus_modes_supported": {"locked": False}}
    rows = [{"name": "gain", "kind": "range", "advertised_in_descriptor": True, "listed_by_device": True, "ok": True,
             "min": 0, "max": 255, "res": 1, "def": 300},
            {"name": "brightness", "kind": "range", "advertised_in_descriptor": True, "listed_by_device": True,
             "ok": True, "min": -64, "max": 64, "res": 1, "def": 0}]
    pc = cl.per_control_record(flags, rows, ["auto_exposure_mode", "gain", "brightness"])
    assert pc["avf"]["exposure"]["listed"] is False and pc["avf"]["exposure"]["range_matches_descriptor"] is False
    assert pc["avf"]["wb"]["listed"] is True and pc["avf"]["wb"]["range_matches_descriptor"] is None
    assert pc["ep0"]["gain"]["range_matches_descriptor"] is False  # def outside [min, max]
    assert pc["ep0"]["brightness"]["range_matches_descriptor"] is True
    eff = run_suite.load_test_module("m_ctrl_effect")
    assert eff.listing_inputs(pc, "avf", "focus", "s") is None
    assert eff.listing_inputs(pc, "avf", "exposure", "s")["listed"] is False
    assert eff.listing_inputs(pc, "ep0", "zoom_absolute", "s")["listed"] is False
