"""Mode scope (linuxlib/scope.py over common/modescope.py), L-FMT-NOGRAB's parsers / completeness / disturbance /
rating, and G-CTRL criterion 1 fed from L-CTRL-LIST (analysis.ctrl_per_control)."""
import argparse
import json
import subprocess
import sys

import pytest

import analysis
import run_suite
import scope
from common import rating, topology_model as tm

NOGRAB = run_suite.load_module("L-FMT-NOGRAB")
LINUX = run_suite.LINUX_DIR


def _args(*extra):
    return run_suite.finalize_args(run_suite.build_parser().parse_args(list(extra)))


# ------------------------------------------------------------------------------------------- scope rule
def test_scope_rule_and_flags():
    a = _args()
    assert (a.min_fps, a.min_height, a.max_height, a.all_modes) == (30.0, 720, 720, False)
    assert scope.in_scope_whf(1280, 720, 30.0) and not scope.in_scope_whf(1920, 1080, 60.0)   # exactly 720 lines
    assert scope.in_scope_whf(1920, 1080, 60.0, max_height=0)                                  # 2026-11-06 rule
    assert scope.in_scope({"w": 1920, "h": 1080, "fps": 30.0}, _args("--max-height", "0"))
    assert not scope.in_scope({"w": 1920, "h": 1080, "fps": 30.0}, a)
    assert not scope.in_scope_whf(640, 480, 30.0) and not scope.in_scope_whf(1280, 720, 24.0)
    assert scope.in_scope_whf(1280, 720, 29.97) and not scope.in_scope_whf(1280, 720, 25.0)   # 0.5 % tolerance
    assert scope._shim_in_scope(1280, 720, 29.97, 30.0, 720) and not scope._shim_in_scope(960, 540, 30.0, 30.0, 720)
    assert not scope._shim_in_scope(1920, 1080, 30.0, 30.0, 720) and scope._shim_in_scope(1920, 1080, 30.0, 30.0, 720, 0)
    assert scope.in_scope({"w": 640, "h": 480, "fps": 5.0}, _args("--all-modes"))
    assert scope.in_scope({"w": 640, "h": 480, "fps": 15.0}, _args("--min-fps", "15", "--min-height", "480"))
    rec = scope.record(a, 10, 3)
    assert rec["n_excluded"] == 7 and rec["min_fps"] == 30.0 and rec["source"] == scope.SOURCE
    u = scope.untested_scope(rec)
    assert u["rating"] == "untested" and u["summary_label"] == "untested (scope)"


class _Ctx:
    def __init__(self, args):
        self.args, self.shared = args, {}


@pytest.mark.linux_only
def test_scope_picks_on_fake_tree(fake_root):
    import sysfs
    cams = {c["key"]: c for c in sysfs.discover_cameras()}
    c922, kiyo = cams["046d:085c:sn=C922SN01"], next(c for c in cams.values() if c["is_kiyo"])
    gen = cams["4c4a:4a55:port=pci-0000:00:14.0/13.1.2"]
    t = lambda m: (m["w"], m["h"], m["fps"])  # noqa: E731
    # default scope (Dom 2026-11-08): exactly 720 lines at >= 30 fps
    ctx = _Ctx(_args())
    p = scope.picks(ctx, c922)
    assert t(p["default"]) == (1280, 720, 30.0) and t(p["alt"]) == (1280, 720, 60.0)
    assert t(p["large"]) == (1280, 720, 60.0) and t(p["low"]) == (960, 720, 30.0)
    assert {t(m) for m in p["modes"]} == {(960, 720, 30.0), (1280, 720, 30.0), (1280, 720, 60.0)}
    assert p["record"]["n_excluded"] == p["record"]["n_advertised"] - 3
    assert all(m["h"] == 720 and m["fps"] >= 30 for c in cams.values() for m in scope.picks(ctx, c)["modes"])
    # --max-height 0: the 2026-11-06 rule (>= 720 lines)
    ctx = _Ctx(_args("--max-height", "0"))
    p = scope.picks(ctx, c922)
    assert t(p["default"]) == (1280, 720, 30.0) and t(p["alt"]) == (1920, 1080, 30.0)
    assert t(p["large"]) == (1920, 1080, 30.0) and t(p["low"]) == (960, 720, 30.0)   # 720 lines, so in scope
    assert {t(m) for m in p["modes"]} == {(960, 720, 30.0), (1280, 720, 30.0), (1280, 720, 60.0),
                                          (1600, 896, 30.0), (1920, 1080, 30.0)}
    assert p["record"]["n_advertised"] == len(c922["modes"]["all_mjpeg"])
    assert p["record"]["n_excluded"] == p["record"]["n_advertised"] - 5
    assert all(m["h"] >= 720 and m["fps"] >= 30 for c in cams.values() for m in scope.picks(ctx, c)["modes"])
    assert t(scope.picks(ctx, kiyo)["large"]) == (1920, 1080, 60.0)
    assert t(scope.picks(ctx, gen)["alt"]) == (1920, 1080, 30.0)
    # --all-modes: the earlier choices (L-CYC 640x480 <-> 720p, L-CTRL-EFFECT 640x480)
    q = scope.picks(_Ctx(_args("--all-modes")), c922)
    assert [t(m) for m in q["cyc_pair"]] == [(640, 480, 30.0), (1280, 720, 30.0)]
    assert t(q["ctrl_mode"]) == (640, 480, 30.0) and q["record"]["n_excluded"] == 0
    # nothing in scope: no picks, recorded
    z = scope.picks(_Ctx(_args("--min-height", "4000")), c922)
    assert z["default"] is None and z["record"]["no_in_scope_mjpeg_mode"] is True


@pytest.mark.linux_only
def test_no_in_scope_mode_is_untested_scope(fake_root, tmp_path, monkeypatch):
    import time as _time
    from test_runner import make_ctx
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, "notfound")
    ctx.args.min_height = 4000
    for t in ("L-MJPEG", "L-CYC", "L-CTRL-EFFECT", "L-TS"):
        res = run_suite.load_module(t).run(ctx)
        cams = res["measurements"]["cameras"]
        assert len(cams) == 4 and all(v.get("skipped") for v in cams.values()), t
        assert all("in-scope" in v["reason"] for v in cams.values()), t
        assert json.dumps(res["verdicts"]).count("untested (scope)") >= 4, t
    m = run_suite.load_module("L-MULTI").run(ctx)
    assert m["measurements"]["phase_a"][0]["results"] == []
    assert all(p.get("skipped", "").startswith("untested (scope)") for p in m["measurements"]["pairs"])


@pytest.mark.linux_only
def test_multi_scoped_pairs_fits_side_not_testable(fake_root):
    """Gerald's hub: C922 MJPEG 720p30 (alt 9) + generic (3069 B) is over budget, and every other in-scope pair
    is larger, so the fits side is recorded as not testable under the mode scope (plan 6, Mode scope)."""
    import sysfs
    import topology
    lm = run_suite.load_module("L-MULTI")
    cams = {c["key"]: c for c in sysfs.discover_cameras()}
    c922, gen = cams["046d:085c:sn=C922SN01"], cams["4c4a:4a55:port=pci-0000:00:14.0/13.1.2"]
    s = topology.collect_snapshot(list(cams.values()))
    cache = tm.ModeAltCache()
    tab = {a["alt"]: a for a in c922["descriptors"]["streams"][0]["alt_table"]}
    cache.put(c922["vid"], c922["pid"], c922["bcd_device"], "MJPG", 1280, 720, 30, 9, tab[9]["max_packet"],
              tab[9]["mult"])
    ctx = _Ctx(_args())
    for a_cam, b_cam in ((gen, c922), (c922, gen)):
        variants, notes = lm.scoped_pair_variants(ctx, s, cache, a_cam, b_cam)
        kinds = {k: (ma, mb) for k, ma, mb in variants}
        assert "over" in kinds and "fits" not in kinds
        assert notes["fits"].startswith("fits-side not testable under mode scope")
        ma, mb = kinds["over"]
        assert ma["h"] >= 720 and mb["h"] >= 720
        pr = lm.predicted(s, cache, [(a_cam, ma), (b_cam, mb)])
        assert next(d["verdict"] for d in pr["domains"] if d["key"] == lm.domain_of(s, b_cam["key"])) == "over"
    # --all-modes keeps the earlier behaviour (a predicted-fits pair at 640x480 exists)
    v = {k: (ma, mb) for k, ma, mb in lm.pair_variants(s, cache, gen, c922, ctx=_Ctx(_args("--all-modes")))}
    assert "fits" in v


@pytest.mark.linux_only
def test_dry_run_shows_scope_and_nograb(fake_root, tmp_path):
    import os
    env = {**os.environ, "SKELLYCAM_LINUX_ROOT": str(fake_root)}
    for extra, all_modes in (([], False), (["--all-modes"], True)):
        p = subprocess.run([sys.executable, str(LINUX / "run_suite.py"), "--dry-run", "--out-dir",
                            str(tmp_path / "o"), *extra], capture_output=True, text=True, timeout=120, env=env)
        assert p.returncode == 0, p.stderr
        plan = json.loads(p.stdout)
        assert plan["mode_scope"]["all_modes"] is all_modes and plan["mode_scope"]["min_fps"] == 30.0
        tests = {t["test"]: t for t in plan["tests"]}
        ng = tests["L-FMT-NOGRAB"]
        assert [t["test"] for t in plan["tests"]].index("L-FMT-NOGRAB") == \
            [t["test"] for t in plan["tests"]].index("L-FMT") + 1
        assert set(ng["methods"]) == set(NOGRAB.METHODS) and ng["hold_ms"] == 2000
        assert set(ng["conditions"]) == set(NOGRAB.CONDITIONS)
        for c in plan["cameras"]:
            assert "mode_scope" in c and c["scoped_default"]
            if not all_modes:
                assert c["mode_scope"]["n_excluded"] > 0
        for t in ("L-MJPEG", "L-CYC", "L-CTRL-EFFECT", "L-TS", "L-MULTI"):
            assert tests[t]["mode_scope"]["all_modes"] is all_modes, t
        if not all_modes:
            assert all(m == "MJPG 1280x720@30" for m in tests["L-CTRL-EFFECT"]["per_camera_mode"].values())
            assert all(r == [] or "lowfps_15" in r for r in tests["L-TS"]["excluded_runs"].values())


def test_camworker_formats_hold_flags():
    import camworker
    a = camworker.build_parser().parse_args(["formats", "--device", "/dev/video0", "--hold-ms", "2000",
                                             "--hold-signal", "/tmp/x"])
    assert a.hold_ms == 2000 and a.hold_signal == "/tmp/x"
    assert camworker.build_parser().parse_args(["formats", "--device", "/dev/video0"]).hold_ms == 0


# ------------------------------------------------------------------------------------------- NOGRAB pieces
V4L2CTL = """ioctl: VIDIOC_ENUM_FMT
\tType: Video Capture

\t[0]: 'YUYV' (YUYV 4:2:2)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\t\tInterval: Discrete 0.067s (15.000 fps)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.100s (10.000 fps)
\t[1]: 'MJPG' (Motion-JPEG, compressed)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.017s (60.000 fps)
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\tSize: Stepwise 16x16 - 1920x1080 with step 1/1
\t\t\tInterval: Continuous 0.033s - 1.000s (1.000-30.000 fps)
"""


def test_parse_v4l2_ctl():
    m = NOGRAB.parse_v4l2_ctl(V4L2CTL)
    assert m[("YUYV", 640, 480)]["fps"] == [30.0, 15.0] and m[("YUYV", 1280, 720)]["fps"] == [10.0]
    assert m[("MJPG", 1280, 720)] == {"fps": [60.0, 30.0], "continuous": False}
    assert m[("MJPG", -1, -1)]["continuous"] is True


PW_ENUM = [
    {"mediaType": "video", "mediaSubtype": "raw", "format": "YUY2", "size": {"width": 640, "height": 480},
     "framerate": {"default": {"num": 30, "denom": 1}, "alt1": {"num": 30, "denom": 1},
                   "alt2": {"num": 15, "denom": 1}}},
    {"mediaType": "video", "mediaSubtype": "mjpg", "size": {"width": 1280, "height": 720},
     "framerate": {"num": 30, "denom": 1}},
    {"mediaType": "video", "mediaSubtype": "mjpg", "size": {"width": 1920, "height": 1080},
     "framerate": {"default": {"num": 30, "denom": 1}, "min": {"num": 1, "denom": 1}, "max": {"num": 30,
                                                                                            "denom": 1}}},
]


def test_parse_pw_formats_and_node_mapping():
    m = NOGRAB.parse_pw_formats(PW_ENUM)
    assert m[("YUYV", 640, 480)]["fps"] == [30.0, 15.0]
    assert m[("MJPG", 1280, 720)]["fps"] == [30.0] and m[("MJPG", 1920, 1080)]["continuous"] is True
    cam = {"node": "/dev/video2", "vid": "046d", "pid": "085c"}
    objs = [{"id": 40, "info": {"props": {"media.class": "Video/Source", "api.v4l2.path": "/dev/video2",
                                          "device.api": "v4l2"}, "params": {"EnumFormat": PW_ENUM}}},
            {"id": 41, "info": {"props": {"media.class": "Video/Source", "api.v4l2.path": "/dev/video4"}}},
            {"id": 42, "info": {"props": {"media.class": "Video/Source", "device.api": "libcamera",
                                          "api.libcamera.path": "\\\\_SB_.PCI0-13.1.4:1.0-046d:085c"}}}]
    nodes = NOGRAB.pw_nodes_for(objs, cam, [cam])
    assert [n["id"] for n in nodes] == [40, 42] and nodes[0]["has_enum_format"] and nodes[1]["api"] == "libcamera"


def _desc(modes):
    return {"streams": [{"modes": [{"fourcc": f, "w": w, "h": h, "interval_type": "discrete", "fps": fps}
                                   for f, w, h, fps in modes]}]}


@pytest.mark.parametrize("use_common", [True, False])
def test_completeness_mjpeg_raw_other(monkeypatch, use_common):
    if not use_common:
        monkeypatch.setattr(NOGRAB, "_ng", None)
    desc = _desc([("MJPG", 1280, 720, [30.0, 60.0, 7.5]), ("YUYV", 640, 480, [30.0, 24.0]),
                  ("H264", 1920, 1080, [30.0])])
    full = {("MJPG", 1280, 720): {"fps": [60.0, 30.0, 7.5], "continuous": False},
            ("YUYV", 640, 480): {"fps": [30.0, 24.0], "continuous": False}}
    c = NOGRAB.completeness(full, desc)
    pc = c["per_class"]
    assert c["complete"] and pc["mjpeg"]["complete"] and pc["raw"]["complete"] and not pc["other"]["complete"]
    part = {("MJPG", 1280, 720): {"fps": [30.0, 7.5], "continuous": False}}
    c2 = NOGRAB.completeness(part, desc)
    m2 = c2["per_class"]["mjpeg"]
    assert not c2["complete"] and m2["n_missing"] == 1 and "60" in m2["missing"][0]
    assert c2["per_class"]["raw"]["n_missing"] == 2
    assert NOGRAB.completeness(None, desc)["complete"] is False


def _rows(n, gap_at=None, gap_ms=0.0, t0=1_000_000_000):
    t, out = t0, []
    for i in range(n):
        out.append({"host_ns": int(t)})
        t += 33_333_333 + (gap_ms * 1e6 if gap_at is not None and i == gap_at else 0)
    return out


@pytest.mark.parametrize("use_common", [True, False])
def test_disturbance(monkeypatch, use_common):
    if not use_common:
        monkeypatch.setattr(NOGRAB, "_ng", None)
    rows = _rows(300)
    base = (rows[15]["host_ns"], rows[90]["host_ns"])
    win = [rows[120]["host_ns"], rows[180]["host_ns"]]
    end = rows[-1]["host_ns"]
    d = NOGRAB.disturbance(rows, win, 30.0, base, end, None)
    assert d["disturbed"] is False and d["window_max_interval_ms"] < 40 and d["baseline_max_interval_ms"] < 40
    g = NOGRAB.disturbance(_rows(300, gap_at=150, gap_ms=250), win, 30.0, base, end + 250_000_000, None)
    assert g["disturbed"] is True and g["window_max_interval_ms"] > 250 and "gap" in g["why"]
    e = [dict(r) for r in rows]
    e[150]["error"] = True
    x = NOGRAB.disturbance(e, win, 30.0, base, end, None)
    assert x["bad_frames_in_window"] == 1 and x["disturbed"] is True
    short = rows[:150]   # stopped with an error inside the window
    s2 = NOGRAB.disturbance(short, win, 30.0, base, short[-1]["host_ns"], short[-1]["host_ns"])
    assert s2["disturbed"] is True and s2["stream_error_in_window"]


def _cond(ok=True, complete=True, disturbed=None, starts=None, blocked=None, changed=None):
    r = {"ok": ok, "completeness": {"complete": complete}, "elapsed_ms": 1.0, "alt": {"alts_seen": [0]}}
    if starts is not None:
        r["alt"]["starts_stream"] = starts
    if changed is not None:
        r["alt"]["alt_changed"] = changed
    if disturbed is not None:
        r["disturbance"] = {"disturbed": disturbed}
    if blocked is not None:
        r["third_process"] = {"blocked": blocked}
    return r


@pytest.mark.parametrize("use_common", [True, False])
def test_rate_method(monkeypatch, use_common):
    if not use_common:
        monkeypatch.delattr(rating, "rate_fmt_nograb", raising=False)
    assert NOGRAB.CONDITIONS == ("idle", "streaming_native", "streaming_second_api")
    avail = (True, None)
    good = {"idle": _cond(starts=False, blocked=False), "streaming_native": _cond(disturbed=False, changed=False),
            "streaming_second_api": _cond(disturbed=False, changed=False)}
    y = NOGRAB.rate_method("x", good, avail)
    assert y["rating"] == "yes" and y["rule"] == ("common.rating.rate_fmt_nograb" if use_common else
                                                  "linux fallback (same rule)")
    assert NOGRAB.rate_method("x", {**good, "streaming_native": _cond(disturbed=True)}, avail)["rating"] == "partial"
    assert NOGRAB.rate_method("x", {**good, "streaming_native": _cond(disturbed=False, changed=True)},
                              avail)["rating"] == "partial"
    assert NOGRAB.rate_method("x", {**good, "idle": _cond(starts=False, blocked=True)}, avail)["rating"] == "partial"
    assert NOGRAB.rate_method("x", {**good, "streaming_second_api": _cond(complete=False, disturbed=False)},
                              avail)["rating"] == "partial"
    assert NOGRAB.rate_method("x", {**good, "idle": _cond(starts=True, blocked=False)}, avail)["rating"] == "no"
    assert NOGRAB.rate_method("x", {**good, "idle": _cond(complete=False, starts=False)}, avail)["rating"] == "no"
    assert NOGRAB.rate_method("x", {**good, "idle": _cond(ok=False)}, avail)["rating"] == "no"
    prov = NOGRAB.rate_method("x", {**good, "streaming_second_api": None}, avail, {"streaming_second_api": "why"})
    assert prov["rating"] == "partial" and prov["provisional"] is True
    assert NOGRAB.rate_method("x", good, (False, "not installed"))["rating"] == "untested"


# ------------------------------------------------------------------------------------------- G-CTRL criterion 1
WALK = [
    {"id": 0x009A0901, "type": "menu", "min": 0, "max": 3, "step": 1, "default": 3, "menu": [{"index": 1}]},
    {"id": 0x009A0902, "type": "integer", "min": 3, "max": 2047, "step": 1, "default": 250},
    {"id": 0x00980913, "type": "integer", "min": 0, "max": 255, "step": 1, "default": 300},   # default out of range
    {"id": None, "probe_id": "0x009a090a", "query_errno": "EPIPE", "fallback": True},        # focus query failed
]


def test_ctrl_per_control_and_criterion1():
    desc = {"ct_controls": ["auto_exposure_mode", "exposure_time_absolute", "focus_absolute", "scanning_mode"],
            "pu_controls": ["gain"]}
    pc = analysis.ctrl_per_control(WALK, desc)
    assert pc["exposure_time_absolute"]["listed"] and pc["exposure_time_absolute"]["range_ok"]
    assert pc["gain"]["listed"] and pc["gain"]["range_ok"] is False and "outside" in pc["gain"]["problems"][0]
    assert pc["focus_absolute"]["listed"] is False and "EPIPE" in pc["focus_absolute"]["problems"][0]
    assert pc["scanning_mode"]["listed"] is None
    c = analysis.ctrl_criterion1(pc, "exposure", "L-CTRL-LIST")
    assert c["listed"] is True and c["range_matches_descriptor"] is True and c["source"] == "L-CTRL-LIST"
    assert analysis.ctrl_criterion1(pc, "gain", "L-CTRL-LIST")["range_matches_descriptor"] is False
    assert analysis.ctrl_criterion1(pc, "white_balance", "L-CTRL-LIST")["listed"] is False   # not in descriptors
    assert analysis.ctrl_criterion1(None, "exposure", "x")["listed"] is None
    rows = [{"name": n, **{k: v for k, v in analysis.ctrl_criterion1(pc, n, "L").items()
                           if k in ("listed", "range_matches_descriptor")},
             "set_readback_ok": True, "effect_ok": True, "before_start_ok": True, "after_start_ok": True,
             "runs_ok": 3, "runs_total": 3} for n in ("exposure",)]
    assert rating.rate_ctrl(rows)["rating"] == "yes"
    rows[0]["range_matches_descriptor"] = False
    r = rating.rate_ctrl(rows)
    assert r["rating"] == "partial" and r["criteria"][0]["met"] is False


@pytest.mark.linux_only
def test_ctrl_effect_without_ctrl_list_uses_own_walk(fake_root, tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    pytest.importorskip("numpy")
    import time as _time
    import simcam
    from test_runner import make_ctx
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, "notfound")
    ctx.args.cameras = None
    ctx.cameras = [c for c in ctx.cameras if c["key"].startswith("046d:085c")]
    simcam.apply(ctx, simcam.SimCam())
    res = run_suite.load_module("L-CTRL-EFFECT").run(ctx)
    ent = next(iter(res["measurements"]["cameras"].values()))
    assert "own walk" in ent["criterion1_source"] and ent["mode"] == "MJPG 1280x720@30"
    assert all(r["listed"] is True and r["range_matches_descriptor"] is True for r in ent["rating_rows"])
    key = next(iter(res["measurements"]["cameras"]))
    assert res["verdicts"]["G-CTRL"]["evidence"]["per_camera"][key]["criteria"][0]["met"] is True


def test_args_namespace_defaults_without_runner():
    """scope.settings works on a bare Namespace (other callers, e.g. the macOS/Windows shim tests)."""
    s = scope.settings(argparse.Namespace())
    assert s == {"min_fps": 30.0, "min_height": 720, "max_height": 720, "all_modes": False, "source": scope.SOURCE}
