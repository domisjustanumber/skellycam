"""Runner: --help / --list-tests / --dry-run (no /dev access, nothing written), and every test module's run(ctx)
on the fake tree with the camera children stubbed out (device-not-found, then hangs): each must return a result
with the standard fields, serialisable as strict JSON. A failure or hang is a result, never a crash."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

import run_suite
from common import results
from suitectx import CamLock, LinuxCtx

LINUX = Path(run_suite.__file__).resolve().parent
STANDARD = {"test", "platform", "hostname", "utc_started", "utc_finished", "command", "environment", "cameras",
            "measurements", "verdicts", "errors"}


def test_help_and_list_tests():
    p = subprocess.run([sys.executable, str(LINUX / "run_suite.py"), "--help"], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0 and "--dry-run" in p.stdout and "--quick" in p.stdout
    p = subprocess.run([sys.executable, str(LINUX / "run_suite.py"), "--list-tests"], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0
    assert [ln.split()[0] for ln in p.stdout.splitlines()] == run_suite.TESTS


@pytest.mark.linux_only
def test_dry_run_on_fake_tree_writes_nothing(fake_root, tmp_path):
    out = tmp_path / "would_be_results"
    p = subprocess.run([sys.executable, str(LINUX / "run_suite.py"), "--dry-run", "--out-dir", str(out),
                        "--raw-dir", str(tmp_path / "raw")], capture_output=True, text=True, timeout=120,
                       env={**__import__("os").environ, "SKELLYCAM_LINUX_ROOT": str(fake_root)})
    assert p.returncode == 0, p.stderr
    plan = json.loads(p.stdout)
    assert [t["test"] for t in plan["tests"]] == run_suite.TESTS
    assert len(plan["cameras"]) == 4 and any(c["is_kiyo"] for c in plan["cameras"])
    assert not out.exists() and not (tmp_path / "raw").exists()
    assert all("error" not in t for t in plan["tests"]), [t for t in plan["tests"] if "error" in t]


def test_only_skip_parsing():
    a = run_suite.finalize_args(run_suite.build_parser().parse_args(["--only", "env,MJPEG", "--skip", "mjpeg"]))
    assert a.selected == ["L-ENV"]
    q = run_suite.finalize_args(run_suite.build_parser().parse_args(["--quick"]))
    assert q.cycles == 5 and q.mjpeg_modes == "sizes"
    with pytest.raises(SystemExit):
        run_suite.norm_tests("L-NOPE")


def _stub_factory(mode: str):
    def stub(argv, timeout_s, env=None):
        if mode == "hang":
            return {"argv": argv, "rc": -9, "stdout": "", "stderr": "", "elapsed_s": timeout_s, "timed_out": True,
                    "killed": True, "spawn_error": None, "json": None}
        err = {"stage": "open", "errno": 2, "errno_name": "ENOENT", "message": "stub: device not found"}
        return {"argv": argv, "rc": 3, "stdout": "", "stderr": "stub", "elapsed_s": 0.01, "timed_out": False,
                "killed": False, "spawn_error": None, "json": {"error": err, "exit_code": 3}}
    return stub


def make_ctx(tmp_path, mode):
    import sysfs
    import topology
    a = run_suite.finalize_args(run_suite.build_parser().parse_args(
        ["--quick", "--kiyo-minutes", "0.002", "--kiyo-interval-s", "0.05", "--mjpeg-modes", "common",
         "--hold-ms", "100"]))
    cams = sysfs.discover_cameras()
    ctx = LinuxCtx(out_dir=tmp_path / "out", raw_dir=tmp_path / "raw", args=a, cameras=cams,
                   worker=[sys.executable, "camworker.py"], helpers_dir=LINUX / "helpers",
                   topology=topology.collect_snapshot(cams), lock=CamLock(enabled=False))
    ctx.out_dir.mkdir(parents=True)
    ctx.raw_dir.mkdir(parents=True)
    ctx.run_child = _stub_factory(mode)
    ctx.camcmd = _stub_factory(mode)
    return ctx


@pytest.mark.linux_only
@pytest.mark.parametrize("mode", ["notfound", "hang"])
def test_every_module_survives_failing_children(fake_root, tmp_path, monkeypatch, mode):
    import time as _time
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, mode)
    for t in run_suite.TESTS:
        ctx.current_test = t
        res = run_suite.load_module(t).run(ctx)
        assert STANDARD <= set(res), (t, STANDARD - set(res))
        assert res["test"] == t and res["platform"] == "linux"
        json.loads(results.to_json_text(res))  # strict JSON (no NaN)
        if t in ("L-MJPEG", "L-CYC", "L-CTRL-EFFECT", "L-TS", "L-FMT", "L-CTRL-LIST", "L-MULTI"):
            assert res["verdicts"], t


@pytest.mark.linux_only
def test_kiyo_included_and_cycle_hang_is_recorded(fake_root, tmp_path, monkeypatch):
    import time as _time
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, "hang")
    res = run_suite.load_module("L-CYC").run(ctx)
    kiyo = next(k for k in res["measurements"]["cameras"] if k.startswith("1532:0e05"))
    b = res["measurements"]["cameras"][kiyo]["batches"]["v4l2_inprocess"]
    assert b["summary"]["hangs"] >= 1
    assert b["rating"]["rating"] in ("no", "partial")
    ctx2 = make_ctx(tmp_path / "k", "notfound")
    r2 = run_suite.load_module("L-KIYO").run(ctx2)
    assert r2["measurements"]["cameras"] and r2["verdicts"]["KIYO"]["rating"] == "no"


def test_combine_and_ctx_helpers(tmp_path):
    from suitectx import combine, errno_from_text, parse_json_stdout
    v = combine({"a": {"rating": "yes"}, "b": {"rating": "partial", "note": "x"}}, "t")
    assert v["rating"] == "partial" and len(v["criteria"]) == 2
    assert parse_json_stdout('log\n{"x": 1}\n') == {"x": 1}
    assert errno_from_text("[DEBUG] VIDEOIO(V4L2:/dev/video2): failed VIDIOC_STREAMON: errno=28 (No space)") == 28
    ns = argparse.Namespace(quick=True)
    ctx = LinuxCtx(out_dir=tmp_path, raw_dir=tmp_path, args=ns, cameras=[], worker=["x"], helpers_dir=tmp_path,
                   lock=CamLock(enabled=False))
    assert ctx.scaled(10, 2) == 2 and ctx.slug("046d:085c:sn=B7/x") == "046d_085c_sn_B7_x"
