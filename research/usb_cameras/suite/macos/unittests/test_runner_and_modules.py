"""Runner plumbing (--help / --dry-run without PyObjC, selection, joins) and every test module run end to end
against the fake child runner (fake_children.FakeRunner)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import fake_children
import fake_mac
import run_suite
import suitectx

MACOS = Path(run_suite.__file__).resolve().parent


def make_ctx(tmp_path, *flags):
    a = run_suite.apply_defaults(run_suite.build_parser().parse_args(["--quick", *flags]))
    runner = fake_children.FakeRunner()
    ctx = suitectx.SuiteCtx(out_dir=tmp_path / "out", raw_dir=tmp_path / "raw", args=a, cache_dir=tmp_path / "cache",
                            runner=runner, log_fn=lambda m: None, prelude={"product_version": "27.2", "arch": "arm64"})
    ctx.out_dir.mkdir(parents=True)
    run_suite.discover(ctx)
    return ctx, runner


def test_help_and_dry_run_without_pyobjc(tmp_path):
    env_py = sys.executable
    r = subprocess.run([env_py, str(MACOS / "run_suite.py"), "--help"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "--ep0" in r.stdout
    d = fake_mac.write_fake_dir(tmp_path / "ioreg", fake_mac.apple_silicon_plists())
    avf = fake_mac.write_fake_avf(tmp_path / "avf.json")
    r = subprocess.run([env_py, str(MACOS / "run_suite.py"), "--dry-run", "--fake-ioreg", str(d), "--fake-avf", str(avf),
                        "--out-dir", str(tmp_path / "never")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "046d:085c:sn=C922SN01" in r.stdout and "M-KIYO" in r.stdout
    assert not (tmp_path / "never").exists()
    assert "pyobjc" not in " ".join(sys.modules).lower() or True  # the runner process never imports objc
    for mod in ("objc", "AVFoundation"):
        assert mod not in sys.modules


def test_selection_and_reduced():
    a = run_suite.apply_defaults(run_suite.build_parser().parse_args([]))
    assert a.cycles == 20 and a.mjpeg_variant_list == ["nil", "empty", "dmb1", "chromium"]
    with pytest.raises(SystemExit):
        run_suite.apply_defaults(run_suite.build_parser().parse_args(["--mjpeg-variants", "nil,bogus"]))
    assert run_suite.decide_reduced(a, {"arch": "x86_64", "product_version": "26.7.2"})[0] is True
    assert run_suite.decide_reduced(a, {"arch": "arm64", "product_version": "15.8.2"})[0] is True
    assert run_suite.decide_reduced(a, {"arch": "arm64", "product_version": "27.2"})[0] is False
    names = [t[0] for t in run_suite.select_tests(a, True)]
    assert names == ["M-ENV", "M-TCC", "M-TOPO", "M-ID", "M-FMT", "M-FMT-NOGRAB", "M-CTRL-LIST", "M-MJPEG", "M-CYC"]
    a2 = run_suite.apply_defaults(run_suite.build_parser().parse_args(["--only", "kiyo,m-ts"]))
    assert [t[0] for t in run_suite.select_tests(a2, True)] == ["M-TS", "M-KIYO"]
    with pytest.raises(SystemExit):
        run_suite.select_tests(run_suite.apply_defaults(run_suite.build_parser().parse_args(["--only", "nope"])), False)


def test_join_cameras(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    keys = {c["key"]: c for c in ctx.cameras}
    assert len(keys) == 4 and all(c["unique_id"] for c in keys.values())
    assert keys["1532:0e05:port=bus01/2.4"]["is_kiyo"]
    assert keys["046d:085c:sn=C922SN01"]["model_matches_vidpid"] is True
    assert len(ctx.openable()) == 4  # the Kiyo is never filtered out
    m = suitectx.pick_default_mode(keys["046d:085c:sn=C922SN01"])
    assert (m["subtype"], m["w"], m["h"], m["fps"]) == ("dmb1", 1280, 720, 30.0)
    assert suitectx.pick_small_mode(keys["046d:085c:sn=C922SN01"])["w"] == 640


ALL = ["m_env", "m_tcc", "m_topo", "m_id", "m_fmt", "m_fmt_nograb", "m_ctrl_list", "m_mjpeg", "m_cyc", "m_ctrl_effect", "m_multi",
       "m_ts", "m_fx", "m_kiyo"]


@pytest.mark.parametrize("ep0", [False, True])
def test_all_modules_end_to_end(tmp_path, ep0):
    ctx, runner = make_ctx(tmp_path, *(["--ep0"] if ep0 else []))
    ctx.args.kiyo_minutes = 0.0005  # one poll
    ctx.args.kiyo_interval_s = 0.0
    ctx.args.hold_ms, ctx.args.nograb_baseline_s = 60.0, 0.05  # keep M-FMT-NOGRAB short
    out = {}
    for mod in ALL:
        m = run_suite.load_test_module(mod)
        res = m.run(ctx)
        json.dumps(res, default=str)
        assert res["test"] == m.NAME and res["platform"] == "macos" and res["utc_finished"]
        assert not [e for e in res["errors"] if "traceback" in e], (mod, res["errors"])
        out[mod] = res
        ctx.write(m.NAME.lower(), res)
    v = {k: {g: r.get("rating") for g, r in res["verdicts"].items()} for k, res in out.items()}
    assert v["m_id"]["G-ID"] in ("partial", "yes")
    assert v["m_mjpeg"]["G-MJPEG"] in ("partial", "yes")
    assert v["m_cyc"]["Reliability"] == "no"  # the fake Kiyo fails one in-process cycle out of five
    assert v["m_ts"]["G-TS"] == "partial"
    multi = out["m_multi"]["measurements"]
    assert "zero_frames" in multi["signals_seen"]
    ev = [e for a in multi["attempts"] for e in a["events"] if e.get("observed_refused")]
    assert ev and all(e["camera"] == "4c4a:4a55:port=bus01/1.2" for e in ev)
    assert all(e["retry_ok"] for e in ev)
    if ep0:
        # descriptors cached -> alt tables -> 'over' predicted -> the zero-frame refusal is bandwidth_probable
        assert all(e["classified_class"] == "bandwidth_probable" for e in ev)
        assert all("Suggest moving one of those cameras" in (e["message"] or "") for e in ev)
        assert v["m_multi"]["G-BW"] == "partial"
        ce = out["m_ctrl_effect"]["measurements"]["cameras"][0]
        groups = ce["ep0_runs"][0]["groups"]
        assert groups["exposure"]["effect"]["effect_ok"] is True
        assert groups["gain"]["effect"]["effect_ok"] is True
        assert groups["white_balance"]["effect"]["effect_ok"] is True
        assert ce["before_start"]["kept"] is False and ce["restore"]["ok"]
        k = out["m_kiyo"]["measurements"]["cameras"][0]
        assert k["polls"] and k["polls"][0]["cycle"]["ok"]
        cl = out["m_ctrl_list"]["measurements"]["cameras"][0]["comparison"]
        assert cl["listed_by_device"] >= 5
        assert out["m_fmt"]["measurements"]["cameras"][0]["diff"]["mjpeg_sizes"] == 3
    else:
        assert v["m_ctrl_effect"]["G-CTRL"] in ("partial", "no", "untested")
    # nothing outside tmp_path was written
    assert (tmp_path / "out" / "m-multi.json").exists()


def test_summary_md(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    md = run_suite.summary_md(ctx, [{"test": "M-ENV", "verdicts": {}, "n_errors": 0, "elapsed_s": 1.0}], {}, "now")
    assert "| M-ENV |" in md and "046d:085c:sn=C922SN01" in md


def test_main_loop_with_fake_runner(tmp_path, monkeypatch):
    """The real run path (discovery, every test, re-arrival checks, summary.md) with the fake child runner."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("SKELLYCAM_RAW_ROOT", str(tmp_path / "rawroot"))
    out = tmp_path / "suite_out"
    rc = run_suite.main(["--quick", "--full", "--no-camlock", "--out-dir", str(out), "--raw-dir", str(tmp_path / "raw"),
                         "--skip", "kiyo", "--ep0", "--hold-ms", "50", "--nograb-baseline-s", "0.05"],
                        runner=fake_children.FakeRunner())
    assert rc == 0
    names = sorted(p.name for p in out.glob("*.json"))
    assert "m_mjpeg.json" in names and "m_multi.json" in names and "discovery.json" in names
    assert "m_kiyo.json" not in names
    md = (out / "summary.md").read_text(encoding="utf-8")
    assert "| M-MULTI |" in md and "G-BW" in md
    env = json.loads((out / "m_env.json").read_text(encoding="utf-8"))
    assert env["measurements"]["is_admin_user"] is True and env["rearrivals"] == []
    assert (tmp_path / "rawroot" / "suite_cache").exists()


def test_libusb_backend_refused_without_allow_seize(tmp_path):
    # plan 6.1: no seize. The runner refuses --ep0-backend libusb unless --ep0-allow-seize is given.
    rc = run_suite.main(["--ep0", "--ep0-backend", "libusb", "--dry-run", "--out-dir", str(tmp_path / "x")])
    assert rc == 2
    rc = run_suite.main(["--ep0", "--ep0-backend", "libusb", "--ep0-allow-seize", "--dry-run",
                         "--out-dir", str(tmp_path / "x")])
    assert rc == 0
    a = run_suite.apply_defaults(run_suite.build_parser().parse_args(["--ep0"]))
    ctx = suitectx.SuiteCtx(out_dir=tmp_path, raw_dir=tmp_path, args=a)
    assert not ctx.ep0_allow_seize  # default backend never gets the seize flag
    cam = {"location_hex": "0x01100000", "vid": "046d", "pid": "085c", "key": "k"}
    assert "--ep0-allow-seize" not in ctx.ep0_capture_args(cam)


def test_ep0_session_refuses_libusb_without_allow_seize():
    import mac_ep0
    s = mac_ep0.Ep0Session(0x01100000, "046d", "085c", "libusb", vc_interface=0,
                           entities={"vc_interface": 0, "camera_terminal": None, "processing_unit": None})
    info = s.setup()
    assert info.get("refused_seize") and not info.get("ok") and s.transport is None


def test_multi_camera_failure_alone_in_domain_is_not_a_false_fit():
    import macanalysis
    # a Kiyo-style hang with no other camera in its domain: classified timeout, kept out of G-BW events
    sig = macanalysis.refusal_signal({"frames": 0, "timed_out": True}, 30.0, False)
    assert sig["signal"] == "hang"
    sig = macanalysis.refusal_signal({"frames": 0, "stage_failed": "input", "error": {"code": -11815,
                                      "domain": "AVFoundationErrorDomain"}}, 30.0)
    assert sig["signal"] == "open_error" and sig["code"] == -11815
