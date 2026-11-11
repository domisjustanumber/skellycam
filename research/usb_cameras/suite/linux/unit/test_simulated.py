"""Every test module against the simulated camera (simcam.py): the success paths of the analysis code run end to
end (JPEG strict decode, step metrics, PTS fit, refusal classification, the user message). Needs Pillow + numpy
(+ simplejpeg for strict decode); skipped without them."""
import json

import pytest

import run_suite
from common import results
from test_runner import make_ctx

pytestmark = pytest.mark.linux_only
pytest.importorskip("PIL")
pytest.importorskip("numpy")


@pytest.fixture
def sim_results(fake_root, tmp_path, monkeypatch):
    import time as _time
    import simcam
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, "notfound")
    simcam.apply(ctx, simcam.SimCam())
    out = {}
    for t in run_suite.TESTS:
        ctx.current_test = t
        res = run_suite.load_module(t).run(ctx)
        json.loads(results.to_json_text(res))
        out[t] = res
    out["_ctx"] = ctx
    return out


def test_simulated_suite(sim_results):
    r = sim_results
    # identity: sysfs, QUERYCAP bus_info, by-id, by-path all map 1:1 (5 quick repeats)
    assert r["L-ID"]["measurements"]["per_api_rating"]["v4l2_bus_info"] in ("partial", "yes")
    assert r["L-ID"]["verdicts"]["G-ID"]["rating"] == "partial"  # persistence (A1) not run
    # formats equal the descriptors
    assert r["L-FMT"]["verdicts"]["FMT"]["rating"] == "yes"
    # MJPEG raw V4L2: frames decode, SOF matches
    mj = r["L-MJPEG"]["verdicts"]["G-MJPEG:raw_v4l2"]
    assert mj["rating"] in ("yes", "partial")
    c922 = next(v for k, v in r["L-MJPEG"]["measurements"]["cameras"].items() if k.startswith("046d:085c"))
    first = c922["modes"][0]["v4l2"]["check"]
    assert first["n"] > 0 and first["sof_matches_request_fraction"] == 1.0 and first["lenient_ok_fraction"] == 1.0
    # controls: exposure / gain / WB / focus effects visible in the simulated image
    ce = r["L-CTRL-EFFECT"]["measurements"]["cameras"]
    c = next(v for k, v in ce.items() if k.startswith("046d:085c"))
    ex = c["experiments"]["exposure"]["trials"][0]
    assert ex["effect_ok"] is True and ex["set_readback_ok"] is True and ex["before_start_ok"] is True
    assert c["experiments"]["white_balance"]["trials"][0]["effect_ok"] is True
    assert c["experiments"]["gain"]["trials"][0]["effect_ok"] is True
    assert c["eacces_check"]["slave_errno"] == "EACCES"
    assert c["restore"]["sets"] and c["persistence"]["manual_kept"] is True
    # timestamps: metadata PTS fit runs, self-consistent
    ts = r["L-TS"]["measurements"]["cameras"]
    m = next(v for k, v in ts.items() if k.startswith("046d:085c"))["runs"]["main"]
    assert m["device_clock"]["frames_with_pts"] > 5 and m["device_clock"]["self_consistent"] is True
    assert r["L-TS"]["verdicts"]["G-TS:uvc_metadata_pts"]["rating"] == "partial"
    # cycles
    assert r["L-CYC"]["verdicts"]["reliability:v4l2_inprocess"]["rating"] == "yes"
    # multi: the C922 + generic 'over' pair is refused, classified, retried, recovers, and gets the message
    pairs = [p for p in r["L-MULTI"]["measurements"]["pairs"] if p.get("variant") == "over"]
    assert pairs and pairs[0]["observed_refused"]
    assert pairs[0]["classification"]["class"] == "bandwidth_certain"
    assert pairs[0]["B_alone_after_A"]["ok"] is True
    msg = pairs[0]["messages"][0]["message"]
    assert "share USB bandwidth" in msg and "Suggest moving one of those cameras" in msg and "ENOSPC" in msg
    assert pairs[0]["messages"][0]["ports_only_other_domains"] is True
    assert r["L-MULTI"]["verdicts"]["G-BW"]["rating"] in ("yes", "partial")
    # mode-alt cache learned from solo opens
    assert len(sim_results["_ctx"].mode_alt_cache) > 0
    # mode scope: streaming tests record it and use only >= 30 fps, >= 720-line modes
    for t in ("L-MJPEG", "L-CYC", "L-CTRL-EFFECT", "L-TS", "L-MULTI"):
        assert r[t]["measurements"]["mode_scope"]["min_fps"] == 30.0, t
    mjc = next(v for k, v in r["L-MJPEG"]["measurements"]["cameras"].items() if k.startswith("046d:085c"))
    assert mjc["mode_scope"]["n_excluded"] > 0
    assert all(int(e["mode"].split()[1].split("x")[1].split("@")[0]) >= 720 for e in mjc["modes"])
    cyc = next(v for k, v in r["L-CYC"]["measurements"]["cameras"].items() if k.startswith("046d:085c"))
    assert cyc["modes"] == ["MJPG 1280x720@30", "MJPG 1920x1080@30"]
    assert c["mode"] == "MJPG 1280x720@30"
    tsr = next(v for k, v in r["L-TS"]["measurements"]["cameras"].items() if k.startswith("046d:085c"))
    assert set(tsr["runs"]) == {"main"} and [x["label"] for x in tsr["excluded_runs"]] == ["lowfps_15"]
    # G-CTRL criterion 1 fed from L-CTRL-LIST (listed + consistent range), so 'yes' is reachable
    assert c["criterion1_source"] == "L-CTRL-LIST"
    assert all(x["listed"] is True and x["range_matches_descriptor"] is True for x in c["rating_rows"])
    assert r["L-CTRL-EFFECT"]["verdicts"]["G-CTRL"]["rating"] == "yes"
    assert all("per_control" in v for v in r["L-CTRL-LIST"]["measurements"]["cameras"].values())
    # L-MULTI: the over pair ran; the fits side is either run (predicted fits) or recorded as not testable
    fits = [p for p in r["L-MULTI"]["measurements"]["pairs"] if p.get("variant") == "fits"]
    assert fits and all(p.get("not_testable") or p.get("predicted", {}).get("verdict") == "fits" for p in fits)
    # L-FMT-NOGRAB: sysfs descriptors and V4L2 ENUM without STREAMON list everything, in all three conditions,
    # without disturbing the stream, starting one, or blocking a third process
    ng = r["L-FMT-NOGRAB"]
    assert ng["verdicts"]["FMT-NOGRAB:sysfs_descriptors"]["rating"] == "yes"
    assert ng["verdicts"]["FMT-NOGRAB:v4l2_enum_no_streamon"]["rating"] == "yes"
    for m in ("v4l2_ctl", "pipewire"):
        if not ng["measurements"]["methods"][m]["available"]:
            assert ng["verdicts"][f"FMT-NOGRAB:{m}"]["rating"] == "untested"
    c922n = next(v for k, v in ng["measurements"]["cameras"].items() if k.startswith("046d:085c"))
    v4 = c922n["conditions"]
    assert v4["idle"]["v4l2_enum_no_streamon"]["third_process"]["blocked"] is False
    assert v4["idle"]["v4l2_enum_no_streamon"]["alt"]["starts_stream"] is False
    assert v4["idle"]["v4l2_enum_no_streamon"]["hold_signal_seen"] is True
    for cond in ("streaming_native", "streaming_second_api"):
        assert v4[cond]["stream"]["started"], cond
        for m in ("v4l2_enum_no_streamon", "sysfs_descriptors"):
            d = v4[cond][m]["disturbance"]
            # time.sleep is patched out, so a window can be ~10 ms: shorter than one 33 ms frame interval; then
            # "no frame inside it" is expected and only frames after it prove the stream kept running
            assert d["disturbed"] is False, (cond, m, d)
            assert d["frames_in_window"] > 0 or (d["window_ms"] < 34 and d["frames_after_window"] > 0), (cond, m, d)
            assert v4[cond][m]["completeness"]["complete"] is True, (cond, m)
    assert v4["streaming_second_api"]["stream"]["api"] == "pyav"
    assert ng["measurements"]["table"] and ng["measurements"]["methods_rated_yes"]
    # Kiyo is in every camera test
    for t in ("L-MJPEG", "L-CYC", "L-TS", "L-CTRL-LIST", "L-FMT", "L-FMT-NOGRAB"):
        assert any(k.startswith("1532:0e05") for k in r[t]["measurements"]["cameras"]), t


def test_runner_main_end_to_end(fake_root, tmp_path, monkeypatch):
    """run_suite.main() with the camera children simulated: one JSON per test with the standard fields,
    summary.md / summary.json / run.json, the learned ModeAltCache; results land in --out-dir only."""
    import time as _time
    import simcam
    import suitectx
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    sim = simcam.SimCam()
    monkeypatch.setattr(suitectx.LinuxCtx, "run_child", lambda self, argv, timeout_s, env=None: sim(argv, timeout_s))
    monkeypatch.setattr(suitectx.LinuxCtx, "camcmd", lambda self, argv, timeout_s, env=None: sim(argv, timeout_s))
    out, raw = tmp_path / "res", tmp_path / "raw"
    rc = run_suite.main(["--quick", "--out-dir", str(out), "--raw-dir", str(raw), "--no-camlock",
                         "--kiyo-minutes", "0.002", "--kiyo-interval-s", "0.05", "--mjpeg-modes", "common",
                         "--hold-ms", "100"])
    assert rc == 0
    for t in run_suite.TESTS:
        d = json.loads((out / f"{t}.json").read_text())
        assert {"test", "platform", "hostname", "utc_started", "utc_finished", "command", "environment", "cameras",
                "measurements", "verdicts", "errors"} <= set(d) and "rearrivals" in d
    assert (out / "summary.md").read_text().startswith("# Linux suite run")
    assert json.loads((out / "run.json").read_text())["utc_finished"]
    assert json.loads((out / "mode_alt_cache.json").read_text())["entries"]
    assert (out / "l_topo" / "topology_snapshot.json").exists()
    # raw frames stay in the raw dir; results keep only JSON/JSONL
    assert not list(out.rglob("*.mjpeg")) and list(raw.rglob("samples.mjpeg"))
