"""--plan preset: argument preset, the plan tests end to end on the simulated camera with the short summary, the
Kiyo Pro dead rule, and the privacy scrub."""
import json
import socket
from pathlib import Path

import pytest

import run_suite
from common import results
from test_runner import make_ctx


def test_plan_args():
    a = run_suite.finalize_args(run_suite.build_parser().parse_args(["--plan"]))
    assert a.selected == run_suite.PLAN_TESTS and a.wrapper_list == []
    assert (a.cycles, a.frames, a.mjpeg_modes, a.multi_reps, a.ctrl_runs) == (20, 10, "all", 1, 1)
    assert a.ts_meta is False and a.multi_pairs is False and a.cyc_inprocess_only is True
    b = run_suite.finalize_args(run_suite.build_parser().parse_args(["--plan", "--cycles", "7", "--only", "CYC"]))
    assert b.cycles == 7 and b.selected == ["L-CYC"]
    c = run_suite.finalize_args(run_suite.build_parser().parse_args([]))
    assert c.wrapper_list == ["pyav", "opencv", "gst"] and not hasattr(c, "ts_meta")


@pytest.mark.linux_only
def test_plan_run_on_simulated_cameras(fake_root, tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    pytest.importorskip("numpy")
    import time as _time
    import plansummary
    import simcam
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, "notfound")
    ctx.args = run_suite.finalize_args(run_suite.build_parser().parse_args(["--plan", "--hold-ms", "100"]))
    ctx.args.multi_seconds = 2.0
    simcam.apply(ctx, simcam.SimCam())
    done = {}
    for t in run_suite.PLAN_TESTS:
        ctx.current_test = t
        done[t] = run_suite.load_module(t).run(ctx)
        json.loads(results.to_json_text(done[t]))
    ts = done["L-TS"]
    assert "G-TS:uvc_metadata_pts" not in ts["verdicts"]
    main = next(iter(ts["measurements"]["cameras"].values()))["runs"]["main"]
    assert "meta" not in main and main["clock"]["clock_name"] == "linux_monotonic"
    cyc = next(iter(done["L-CYC"]["measurements"]["cameras"].values()))
    assert set(cyc["batches"]) == {"v4l2_inprocess"}
    eff = next(iter(done["L-CTRL-EFFECT"]["measurements"]["cameras"].values()))
    assert set(eff["experiments"]) <= {"exposure", "focus"} and "eacces_check" not in eff
    assert done["L-MULTI"]["measurements"]["pairs"] == [] and len(done["L-MULTI"]["measurements"]["phase_a"]) == 1
    mj = next(iter(done["L-MJPEG"]["measurements"]["cameras"].values()))["modes"][0]["v4l2"]["check"]
    assert mj["bytes_per_frame"]["n"] > 0 and mj["n_distinct_header_sha1"] >= 1
    run_info = {"stamp": "T", "environment": results.env_info()}
    text = plansummary.build(ctx, done, run_info)
    for c in ctx.cameras:
        assert f"## {c['name']}" in text
    assert "native JPEG" in text and "linux_monotonic" in text and "bytes/frame" in text
    assert "sn=" not in text or "chars>" in text  # serial-based keys masked


def _fail(argv, timeout_s, env=None):
    return {"argv": argv, "rc": 4, "stdout": "", "stderr": "", "elapsed_s": 1, "timed_out": False, "killed": False,
            "spawn_error": None, "json": {"error": {"stage": "first_frame", "errno": None, "errno_name": None}}}


@pytest.mark.linux_only
def test_kiyo_pro_dead_rule(fake_root, tmp_path):
    from suitectx import LinuxCtx
    from tutil import gate
    ctx = make_ctx(tmp_path, "notfound")
    del ctx.camcmd  # use the real LinuxCtx.camcmd (lock disabled) with a failing child
    ctx.run_child = _fail
    kiyo = next(c for c in ctx.cameras if c["is_kiyo"])
    other = next(c for c in ctx.cameras if not c["is_kiyo"])
    cap = ["python", "camworker.py", "capture", "--device", kiyo["node"]]
    refused = {"argv": cap, "rc": 4, "timed_out": False, "json": {"error": {"stage": "streamon", "errno_name": "ENOSPC"}}}
    ctx.current_test = "L-MJPEG"
    LinuxCtx._kiyo_watch(ctx, cap, refused)              # bandwidth refusal: not a wedge
    assert not ctx.suspect and not ctx.dead
    ctx.camcmd(cap, 10)
    assert kiyo["key"] in ctx.suspect and not ctx.dead
    ctx.camcmd(["python", "camworker.py", "controls", "--device", kiyo["node"]], 10)  # not a stream command
    assert not ctx.dead
    ctx.camcmd(cap, 10)
    assert kiyo["key"] in ctx.dead and ctx.dead[kiyo["key"]]["since_test"] == "L-MJPEG"
    assert len(ctx.dead[kiyo["key"]]["failures"]) == 2 and ctx.stream_starts[kiyo["key"]] == 3  # the refused start counts
    r = ctx.camcmd(["python", "camworker.py", "controls", "--device", kiyo["node"]], 10)
    assert r["skipped"].startswith("skipped: Kiyo Pro dead since L-MJPEG")
    assert gate(ctx, kiyo, "L-CYC")["kiyo_pro_dead"] is True
    ctx.camcmd(["python", "camworker.py", "capture", "--device", other["node"]], 10)
    ctx.camcmd(["python", "camworker.py", "capture", "--device", other["node"]], 10)
    assert list(ctx.dead) == [kiyo["key"]]               # the rule is for the Kiyo Pro only


def test_scrub_private(tmp_path):
    host = socket.gethostname()
    home = str(Path.home())
    f = tmp_path / "x.json"
    f.write_text(json.dumps({"hostname": host, "exe": home + "/bin/python", "ip": "192.168.1.23",
                             "os": "Ubuntu 26.04", "mail": "someone@example.net"}), encoding="utf-8")
    counts = results.scrub_private(tmp_path)
    t = f.read_text(encoding="utf-8")
    assert home not in t.replace("\\\\", "\\") and "192.168.1.x" in t and "Ubuntu 26.04" in t
    assert "[email removed]" in t and counts
    if len(host) >= 3 and host.lower() not in ("localhost", "ubuntu"):
        assert host not in t
