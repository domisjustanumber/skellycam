"""Offline tests for the device-fault gate, W-CYC / W-KIYO / opencv_ds / cycstats fixes and the runner (no camera).

    uv run --isolated --python 3.12 --no-project --with pytest pytest suite/windows/tests/test_faultgate_offline.py

Nothing here opens a camera: suitectx.camcmd_run and capkit.get_controls are replaced by fakes, arrivals by a stub.
The re-analysis tests read the 2026-11-06 Gerald run when it is present (skipped otherwise).
"""
from __future__ import annotations

import json
import sys
import types
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

import suitectx  # noqa: E402
from common import cycstats  # noqa: E402

RUN = RESEARCH / "results" / "windows" / "Gerald" / "suite_20261106T181941Z"
KIYO_MF = r"\\?\usb#vid_1532&pid_0e05&mi_00#a&1#{e5323777-f976-4f5b-9b55-b94699c46e44}\global"
KIYO_DS = r"\\?\usb#vid_1532&pid_0e05&mi_00#a&1#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
C922_MF = r"\\?\usb#vid_046d&pid_085c&mi_00#8&2#{e5323777-f976-4f5b-9b55-b94699c46e44}\global"
C922_DS = r"\\?\usb#vid_046d&pid_085c&mi_00#8&2#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"


def _cams():
    return [{"key": "kiyo", "name": "USB Video Device", "is_kiyo": True, "vid": "1532", "pid": "0e05",
             "mf_symlink": KIYO_MF, "ds_path": KIYO_DS, "last_arrival": "2026-11-06T14:59:24Z"},
            {"key": "c922", "name": "c922", "is_kiyo": False, "vid": "046d", "pid": "085c",
             "mf_symlink": C922_MF, "ds_path": C922_DS, "last_arrival": "2026-11-06T13:00:00Z"}]


def _ctx(tmp_path, cams=None):
    ctx = suitectx.build_ctx(suitectx.default_args(), out_dir=tmp_path / "out", raw_dir=tmp_path / "raw",
                             cameras=cams if cams is not None else _cams())
    ctx.arrival_fn = lambda cs: {"cameras": {c["key"]: {"present": True, "last_arrival": c.get("last_arrival")}
                                             for c in cs}}
    return ctx


def _run(stdout_obj=None, rc=0, timed_out=False):
    return {"argv": [], "rc": rc, "stdout": json.dumps(stdout_obj) if stdout_obj is not None else "", "stderr": "",
            "elapsed_s": 0.1, "timed_out": timed_out, "killed": timed_out, "lock_wait_s": 0.0,
            "lock_timed_out": False}


ONSET = {"tool": "wincam", "subcommand": "capture", "ok": False, "unreleasable": True, "utc_started": "2026-11-06T18:43:39Z",
         "error": {"stage": "reader_release", "hr": None, "hr_name": "timeout", "class": "timeout"}}
DEVERR = {"tool": "wincam", "ok": False, "error": {"stage": "first_sample", "hr": "0x8007001F",
                                                    "class": "device_error"}}
GOOD = {"tool": "wincam", "ok": True, "frames": {"total": 1}, "timings": {"open_to_first_frame_ms": 330.0}}


# ================================================================================================ cycstats (N4)
def test_cycstats_drops_sentinels_and_counts_mismatches():
    rows = [{"i": 0, "ok": False, "first_frame_ms": -1, "open_to_first_frame_ms": -1, "close_ms": 1.2},
            {"i": 1, "ok": True, "first_frame_ms": 300, "open_to_first_frame_ms": 300, "close_ms": 2.0,
             "format_mismatch": True, "fps_mismatch": True},
            {"i": 2, "ok": True, "first_frame_ms": 310, "open_to_first_frame_ms": 310, "close_ms": 2.0,
             "size_mismatch": True, "shutdown_ms": -1}]
    s = cycstats.summarize_cycles(rows)
    assert s["timings_ms_all_cycles"]["first_frame_ms"]["n"] == 2          # -1 dropped
    assert s["timings_ms_all_cycles"]["first_frame_ms"]["min"] == 300
    assert s["timings_ms"]["shutdown_ms"] == {"n": 0}
    assert s["format_mismatch_count"] == 1 and s["size_mismatch_count"] == 1 and s["fps_mismatch_count"] == 1
    assert s["n_ok_as_requested"] == 0 and s["open_to_first_frame_ms_p50"] == 305
    assert cycstats.percentiles([-1, 5]) ["n"] == 2                          # default unchanged for other callers


# ================================================================================================ suitectx gate
def test_fault_signature_cases():
    assert suitectx.fault_signature(ONSET)["class"] == "unreleasable"
    assert suitectx.fault_signature(DEVERR)["code"] == "0x8007001F"
    cyc = {"summary": {"ok": 0, "failed": 50, "failures_by_class": {"device_error": 50},
                       "failures_by_stage": {"first_sample": 50}}}
    assert suitectx.fault_signature(cyc)["class"] == "device_error"
    mixed = {"summary": {"ok": 3, "failures_by_class": {"device_error": 2}}}
    assert suitectx.fault_signature(mixed) is None
    assert suitectx.fault_signature(None, {"timed_out": True}, streaming=True)["class"] == "hung_process"
    assert suitectx.fault_signature(None, {"timed_out": True}, streaming=False) is None
    assert suitectx.fault_signature(None, {"timed_out": True, "lock_timed_out": True}) is None
    assert suitectx.fault_signature({"ok": False, "error": {"stage": "open", "errno": 5, "class": "other"}}) is None
    assert suitectx.fault_signature({"ok": False, "gate_skipped": True, "error": {"class": "device_error"}}) is None


def test_streaming_argv_and_camera_mapping():
    cams = _cams()
    assert suitectx.is_streaming_argv([r"C:\x\wincam.exe", "capture", "--api", "mf"])
    assert suitectx.is_streaming_argv([r"C:\x\wincam.exe", "cycle"])
    assert not suitectx.is_streaming_argv([r"C:\x\wincam.exe", "controls", "--read-only"])
    assert not suitectx.is_streaming_argv([r"C:\x\wincam.exe", "formats"])
    assert suitectx.is_streaming_argv(["uv", "run", "--script", r"C:\h\pyav_ds.py", "cycle"])
    assert suitectx.is_streaming_argv(["uv", "run", "--script", r"C:\h\opencv_ds.py", "cycle"])
    # 2026-11-08 helpers: raw_ds.py and opencv_ctrl.py stream; pymf capture/cycle stream, pymf list/formats do not;
    # pyav_list.py is never gated (W-PYAV-LIST must meet a faulted camera)
    assert suitectx.is_streaming_argv(["uv", "run", "--script", r"C:\h\raw_ds.py", "pyav", "--pixel-format", "nv12"])
    assert suitectx.is_streaming_argv(["uv", "run", "--script", r"C:\h\opencv_ctrl.py", "run"])
    assert suitectx.is_streaming_argv(["uv", "run", "--script", r"C:\w\pymf\cli.py", "cycle", "--device", "x"])
    assert not suitectx.is_streaming_argv(["uv", "run", "--script", r"C:\w\pymf\cli.py", "formats"])
    assert not suitectx.is_streaming_argv(["uv", "run", "--script", r"C:\h\pyav_list.py", "list_devices"])
    assert suitectx._argv_api(["uv", "run", "--script", r"C:\w\pymf\cli.py", "capture"]) == "pymf"
    assert suitectx._argv_api(["uv", "run", "--script", r"C:\h\opencv_ctrl.py", "run"]) == "opencv"
    assert suitectx._argv_mode(["w", "capture", "--subtype", "YUY2", "--width", "1280", "--height", "720",
                                "--fps", "30"]) == "YUY2 1280x720@30"
    assert suitectx._argv_mode(["w", "capture", "--width", "1280", "--height", "720", "--fps", "30"]) == \
        "MJPG 1280x720@30"
    assert suitectx.camera_for_argv(cams, ["wincam.exe", "capture", "--device", KIYO_MF])["key"] == "kiyo"
    assert suitectx.camera_for_argv(cams, ["x", "--expect-path", C922_DS.upper()])["key"] == "c922"
    assert suitectx.camera_for_argv(cams, ["multi_launch.py", "spec.json"]) is None


def test_probe_mode_stays_in_the_streaming_scope(tmp_path, monkeypatch):
    """The health probe streams only an in-scope mode (exactly 720 lines at >= 30 fps): no 640x480 fallback when
    the format list is missing, and no out-of-scope default; then nothing is streamed and the fault state stays."""
    import capkit as ck
    ctx = _ctx(tmp_path)
    cam = ctx.camera("kiyo")
    lists = {"fm": None, "modes": []}
    monkeypatch.setattr(ck, "get_formats", lambda c, cm, cache=None: (lists["fm"], {}))
    monkeypatch.setattr(ck, "mjpeg_modes", lambda fm: lists["modes"])
    assert suitectx._probe_mode(ctx, cam).startswith("probe untested (no format list")
    lists["fm"] = {"fixture": True}
    lists["modes"] = [ck.Mode(640, 480, 30, 1), ck.Mode(1280, 720, 15, 1), ck.Mode(1920, 1080, 30, 1)]
    assert suitectx._probe_mode(ctx, cam).startswith("probe untested (no in-scope mode)")
    lists["modes"].append(ck.Mode(1280, 720, 30, 1))
    assert suitectx._probe_mode(ctx, cam) == (1280, 720, 30.0)
    # health_probe with no in-scope mode: no camera command, ok None, fault state unchanged
    lists["modes"] = [ck.Mode(640, 480, 30, 1)]
    calls = []
    monkeypatch.setattr(suitectx, "camcmd_run", lambda *a, **k: calls.append(a) or _run(DEVERR, rc=4))
    out = ctx.health_probe("kiyo", test="start", reason="--probe-at-start")
    assert out["ok"] is None and out["skipped"].startswith("probe untested") and calls == []
    assert not ctx.camera_faulted("kiyo")


def test_gate_lifecycle(tmp_path, monkeypatch):
    """A non-Kiyo Pro camera keeps the original gate: fault -> gated + re-probed at each test -> recovered."""
    ctx = _ctx(tmp_path)
    calls = []
    answers = {"probe": DEVERR}

    def fake_run(argv, timeout_s, **kw):
        calls.append(argv)
        if "--frames" in argv and argv[argv.index("--frames") + 1] == "1":
            return _run(answers["probe"], rc=0 if answers["probe"].get("ok") else 4)
        if C922_MF in argv:
            return _run(DEVERR, rc=4)
        return _run(GOOD)

    monkeypatch.setattr(suitectx, "camcmd_run", fake_run)
    monkeypatch.setattr(suitectx, "_probe_mode", lambda c, cam, mode=None: (1280, 720, 30.0))
    ctx.begin_test("W-MJPEG")
    ctx.camcmd([str(ctx.wincam), "capture", "--api", "mf", "--device", C922_MF, "--width", "640", "--height", "360",
                "--fps", "5"], timeout_s=10)
    f = ctx.camera_faulted("c922")
    assert f and f["test"] == "W-MJPEG" and f["code"] == "0x8007001F" and f["source"] == "camcmd_scan"
    assert f["mode"] == "MJPG 640x360@5"
    assert ctx.camera_gated("c922") is None and ctx.camera_dead("c922") is None
    assert ctx.first_failure["c922"]["test"] == "W-MJPEG"
    ctx.end_test("W-MJPEG")
    n0 = len(calls)
    probes = ctx.begin_test("W-TS")
    assert probes["c922"]["ok"] is False and len(calls) == n0 + 1
    assert ctx.camera_gated("c922") and ctx.gated_by_test["W-TS"] == {"c922": f["since_utc"]}
    r = ctx.camcmd([str(ctx.wincam), "capture", "--device", C922_MF], timeout_s=10)
    obj = json.loads(r["stdout"])
    assert r["gate_skipped"] and obj["device_fault"] and obj["error"]["class"] == "device_fault"
    assert len(calls) == n0 + 1                                    # not run
    ctx.camcmd([str(ctx.wincam), "controls", "--api", "mf", "--device", C922_MF, "--read-only"], timeout_s=10)
    assert len(calls) == n0 + 2                                    # controls are not gated for a non-dead camera
    ctx.camcmd([str(ctx.wincam), "capture", "--device", KIYO_MF], timeout_s=10)
    assert len(calls) == n0 + 3                                    # other cameras unaffected
    u = ctx.fault_untested("c922")
    assert u["rating"] == "untested" and "device fault since" in u["note"] and u["evidence"]["device_fault"]
    ctx.end_test("W-TS")
    answers["probe"] = GOOD
    ctx.begin_test("W-MULTI")
    assert ctx.camera_faulted("c922") is None and ctx.camera_gated("c922") is None
    rep = ctx.fault_report()
    assert [e["type"] for e in rep["events"] if e["type"] in ("fault", "recovered") and e["key"] == "c922"] == \
        ["fault", "recovered"]
    assert rep["faults"]["c922"]["recovered_utc"] and not rep["dead"]
    json.dumps(rep)


def test_kiyo_pro_dead_rule(tmp_path, monkeypatch):
    """Dom 2026-11-11: a Kiyo Pro fault makes it dead for the run: no re-probe, no recovery, no command of any kind
    (streaming, controls, formats, probes, gate=False), diagnostics recorded once, other cameras unaffected."""
    ctx = _ctx(tmp_path)
    calls = []

    def fake_run(argv, timeout_s, **kw):
        calls.append(argv)
        return _run(DEVERR if KIYO_MF in argv else GOOD, rc=4 if KIYO_MF in argv else 0)

    monkeypatch.setattr(suitectx, "camcmd_run", fake_run)
    monkeypatch.setattr(suitectx, "_probe_mode", lambda c, cam, mode=None: (1280, 720, 30.0))
    ctx.begin_test("W-MJPEG")
    ctx.camcmd([str(ctx.wincam), "capture", "--api", "mf", "--device", KIYO_MF, "--width", "1280", "--height",
                "720", "--fps", "30"], timeout_s=10)
    d = ctx.camera_dead("kiyo")
    assert d and d["code"] == "0x8007001F" and d["test"] == "W-MJPEG"
    diag = d["diagnostics"]
    for k in ("utc", "test", "plug_in_age_s", "last_command", "fault_and_failure_events",
              "other_camera_commands_running", "stream_starts_this_run", "camera", "processes", "frame_server",
              "camera_activity"):
        assert k in diag, k
    assert diag["stream_starts_this_run"] == 1 and KIYO_MF in diag["last_command"]["argv"]
    assert list((tmp_path / "out").glob("KIYO_PRO_DEAD_*.json"))
    assert ctx.camera_gated("kiyo")                                # gated at once, also inside the same test
    n0 = sum(1 for a in calls if KIYO_MF in a)
    ctx.end_test("W-MJPEG")
    probes = ctx.begin_test("W-TS")
    assert "kiyo" not in probes                                    # never re-probed
    for argv in ([str(ctx.wincam), "capture", "--device", KIYO_MF],
                 [str(ctx.wincam), "controls", "--api", "mf", "--device", KIYO_MF, "--read-only"],
                 [str(ctx.wincam), "formats", "--api", "mf", "--device", KIYO_MF]):
        r = ctx.camcmd(argv, timeout_s=10, gate=False)
        assert r["gate_skipped"]
    hp = ctx.health_probe("kiyo", reason="test")
    assert hp["ok"] is False and hp["dead"] and hp["faulted_after"]
    assert ctx.clear_fault("kiyo") is None and ctx.camera_faulted("kiyo")
    assert sum(1 for a in calls if KIYO_MF in a) == n0             # nothing reached the dead Kiyo Pro
    ctx.camcmd([str(ctx.wincam), "capture", "--device", C922_MF], timeout_s=10)
    assert any(C922_MF in a for a in calls)                        # other cameras unaffected
    ctx.end_test("W-TS")
    rep = ctx.fault_report()
    assert rep["dead"]["kiyo"]["dead"] and rep["stream_starts"]["kiyo"] == 1
    json.dumps(rep, default=str)


def test_kiyo_pro_dead_poller_stops(tmp_path, monkeypatch):
    import w_kiyo
    ctx = _ctx(tmp_path)
    ctx.dead["kiyo"] = {"dead": True, "since_utc": "2026-11-12T03:00:00Z"}
    polled = []
    monkeypatch.setattr(w_kiyo, "poll_once", lambda c, cam, api, raw_path=None: polled.append(cam["key"]) or {})
    poller = w_kiyo.KiyoPoller.__new__(w_kiyo.KiyoPoller)
    poller.ctx, poller.cams = ctx, [c for c in ctx.cameras if c.get("is_kiyo")]
    import threading
    poller.stop_ev, poller.t_start, poller.max_s, poller.interval_s = threading.Event(), None, 3600.0, 1.0
    poller._loop()                                                  # returns at once: every Kiyo Pro is dead
    assert polled == []


def test_no_fault_gate_flag(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    ctx.fault_gate = False
    monkeypatch.setattr(suitectx, "camcmd_run", lambda argv, t, **kw: _run(DEVERR, rc=4))
    ctx.mark_fault("c922", test="W-X", code="0x8007001F")
    ctx.begin_test("W-Y", probe=False)
    assert ctx.camera_faulted("c922") and ctx.camera_gated("c922") is None
    ctx.mark_fault("kiyo", test="W-X", code="0x8007001F")           # the dead rule ignores --no-fault-gate
    assert ctx.camera_gated("kiyo") and ctx.camera_dead("kiyo")


def test_scan_result_for_faults_finds_onset():
    res = {"measurements": {"cameras": {"kiyo": {"modes": [
        {"mode": "MJPG 640x360@5", "apis": {"mf": {"api": "mf", "ok": False, "error": ONSET["error"]}}},
        {"mode": "MJPG 640x360@10", "apis": {"mf": {"api": "mf", "ok": False, "error": DEVERR["error"]}}}]},
        "c922": {"modes": [{"mode": "x", "apis": {"mf": {"ok": True, "error": None}}}]}}}}
    hits = suitectx.scan_result_for_faults("W-MJPEG", res, _cams())
    assert set(hits) == {"kiyo"}
    assert hits["kiyo"]["class"] == "unreleasable" and hits["kiyo"]["mode"] == "MJPG 640x360@5"


# ================================================================================================ opencv_ds (B3)
def test_opencv_evaluate_row():
    import opencv_ds
    base = {"stage_failed": None, "frames": 31, "frame_shape": [720, 1280, 3], "fps_measured": 29.9,
            "sets": {"got_fourcc": "MJPG"}}
    assert opencv_ds.evaluate_row(dict(base), 1280, 720, 30)["ok"] is True
    r = opencv_ds.evaluate_row(dict(base, sets={"got_fourcc": "YUY2"}, fps_measured=10.0), 1280, 720, 30)
    assert r["streamed_ok"] and not r["ok"] and r["format_mismatch"] and r["fps_mismatch"]
    r = opencv_ds.evaluate_row(dict(base, frame_shape=[480, 640, 3]), 1280, 720, 30)
    assert r["size_mismatch"] and not r["ok"] and r["final_size"] == [640, 480]
    # skellycam-full: the format read back after the APPLY step counts
    r = opencv_ds.evaluate_row(dict(base, sets={"got_fourcc": "YUY2"}, apply={"got_fourcc": "MJPG"}), 1280, 720, 30)
    assert r["ok"] and r["final_fourcc"] == "MJPG"
    r = opencv_ds.evaluate_row({"stage_failed": "open", "frames": 0}, 1280, 720, 30)
    assert r["ok"] is False and r["format_mismatch"] is None


# ================================================================================================ W-CYC
def test_wcyc_format_flags_and_rearrival():
    import w_cyc
    ds = w_cyc._norm_rows([{"ok": True, "codec": "rawvideo", "format_fallback": True, "frames": 30},
                           {"ok": True, "codec": "mjpeg", "frames": 30}], "ds")
    assert ds[0]["ok"] and ds[0]["format_mismatch"] and not ds[0]["ok_as_requested"]
    assert ds[1]["format_mismatch"] is False
    ocv = w_cyc._norm_rows([{"mode": "MJPG 1280x720@30", "ok": True, "stage_failed": None, "frames": 31,
                             "frame_shape": [720, 1280, 3], "fps_measured": 10.0, "sets": {"got_fourcc": "YUY2"}}],
                           "opencv")
    assert ocv[0]["ok"] is True and ocv[0]["format_mismatch"] and ocv[0]["fps_mismatch"]
    # start-stamped rows: arrival inside cycle 1
    rows = [{"utc": "2026-11-06T19:24:00+00:00"}, {"utc": "2026-11-06T19:24:15.9+00:00"},
            {"utc": "2026-11-06T19:24:30+00:00", "frames": 30}]
    assert w_cyc.attribute_re_arrival(rows, "2026-11-06T19:24:27.05Z", utc_is_end=False) == 1
    assert w_cyc.attribute_re_arrival(rows, "2026-11-06T19:23:00Z", utc_is_end=False) is None
    assert w_cyc.attribute_re_arrival(rows, "2026-11-06T19:24:27.05Z", utc_is_end=True) == 2
    rr = [dict(r, ok=True) for r in rows]
    assert w_cyc.apply_re_arrival(rr, "2026-11-06T19:24:27.05Z", "opencv") == 1
    assert rr[1]["ok"] is False and rr[1]["device_reset"] and rr[1]["stage_failed"] == "device_reset"


def _summ(n, n_ok, within, **kw):
    rows = [{"i": i, "ok": i < n_ok, "first_frame_ms": 300 if i < within else (3000 if i < n_ok else None),
             "close_ms": 2} for i in range(n)]
    for k, v in kw.items():
        for r in rows[:v]:
            r[k] = True
    return cycstats.summarize_cycles(rows)


def test_wcyc_rate_variant():
    import w_cyc
    assert w_cyc.rate_variant(_summ(50, 50, 50), False)["rating"] == "yes"
    v = w_cyc.rate_variant(_summ(25, 25, 25, format_mismatch=12), False)
    assert v["rating"] == "partial"
    assert any(w_cyc.FORMAT_CRITERION in c["criterion"] and c["met"] is False for c in v["criteria"])
    v = w_cyc.rate_variant(_summ(15, 15, 0), False)
    assert v["rating"] == "no" and v["no_reason"] == "latency"
    assert v["evidence"]["n_ok"] == 15 and v["evidence"]["success_rate"] == 1.0
    v = w_cyc.rate_variant(_summ(15, 0, 0), True)
    assert v["rating"] == "no" and v["no_reason"] == "failures"
    v = w_cyc.rate_variant({"n": 0}, None, pre_existing_fault=True,
                           fault={"since_utc": "2026-11-06T18:43:39Z", "test": "W-MJPEG", "code": "timeout"})
    assert v["rating"] == "untested" and v["evidence"]["pre_existing_fault"] is True
    v = w_cyc.rate_variant(_summ(15, 15, 15), False, device_reset_unattributed=True)
    assert v["rating"] == "partial"


def test_wcyc_wilson_claim():
    """Plan 6.1 W-CYC-381: a claim variant (reliability profile) is 'yes' only at a Wilson lower bound >= 0.99;
    any other 'yes' below it is labelled a point estimate."""
    import w_cyc
    assert w_cyc.rate_variant(_summ(400, 400, 400), False, claim_99=True)["rating"] == "yes"
    v = w_cyc.rate_variant(_summ(400, 397, 397), False, claim_99=True)      # 99.25 %, Wilson lower ~0.978
    assert v["rating"] == "partial" and "99 % not shown" in v["summary_label"], v.get("summary_label")
    assert any("Wilson" in c["criterion"] and c["met"] is False for c in v["criteria"])
    assert any(">= 99% of cycles" in c["criterion"] and c["met"] is True for c in v["criteria"])   # XP 3 kept
    v = w_cyc.rate_variant(_summ(100, 100, 100), False, claim_99=True)      # mf_newproc: 100/100, lower ~0.963
    assert v["rating"] == "partial" and "n too small for a 99 % claim" in v["summary_label"]
    v = w_cyc.rate_variant(_summ(15, 15, 15), False)                        # opencv_inproc 15/15
    assert v["rating"] == "yes" and v["summary_label"].startswith("yes (point estimate; n=15")
    assert set(w_cyc.CLAIM_VARIANTS) == {"mf_inproc", "ds_ffmpeg_inproc", "mf_newproc"}
    # 2026-11-11: mf_newproc runs 400 cycles in the reliability profile, so the "smaller sample" caveat is gone
    assert "smaller sample" not in w_cyc.reliability_note("reliability", w_cyc.variant_counts(
        types.SimpleNamespace(args=types.SimpleNamespace(cyc_profile="reliability", quick=False, cycles=None,
                                                         proc_cycles=None, frames=None, reliability_cycles=None))))


class _FakeCtx:
    """Minimal ctx for w_cyc.run / the W-KIYO poller (no camera, no lock)."""

    def __init__(self, tmp_path, cams, probe_ok=True, faulted=False):
        self.cameras = cams
        self.out_dir = tmp_path / "out"
        self.raw_dir = tmp_path / "raw"
        self.args = types.SimpleNamespace(quick=True, cycles=2, proc_cycles=1, frames=2, kiyo_interval=0.05)
        self.wincam = Path("wincam.exe")
        self.logs, self.cmds, self.marked = [], [], []
        self.probe_ok = probe_ok
        self.current_test = "W-CYC"
        self._faulted = {c["key"]: {"since_utc": "2026-11-06T18:43:39Z", "test": "W-MJPEG", "code": "0x8007001F",
                                    "faulted": True} for c in cams} if faulted else {}
        self.kiyo_state = {}

    def log(self, m):
        self.logs.append(m)

    def camcmd(self, argv, timeout_s, **kw):
        self.cmds.append([str(a) for a in argv])
        return _run(None, rc=4)

    def run(self, argv, timeout_s):
        return {"stdout": '"RazerAppEngine.exe","37240","Console","1","10 K"\n"x.exe","1","C","1","1 K"\n', "rc": 0}

    def arrivals(self):
        return {"cameras": {c["key"]: {"present": True, "last_arrival": c.get("last_arrival")} for c in self.cameras}}

    def camera_gated(self, cam):
        return None

    def camera_faulted(self, cam):
        return self._faulted.get(cam["key"] if isinstance(cam, dict) else cam)

    def fault_reason(self, cam):
        f = self.camera_faulted(cam)
        return f and f"device fault since {f['since_utc']}"

    def health_probe(self, cam, test=None, mode=None, reason=""):
        if not self.probe_ok:
            self._faulted[cam["key"]] = {"since_utc": "2026-11-06T19:00:00Z", "test": test, "code": "0x8007001F",
                                         "faulted": True}
        return {"ok": self.probe_ok, "fault_like": not self.probe_ok, "code": None if self.probe_ok else "0x8007001F"}

    def mark_fault(self, cam, **kw):
        self.marked.append((cam["key"], kw))

    def _arrival_for(self, cam):
        return {"present": True, "last_arrival": cam.get("last_arrival")}


def test_wcyc_run_skips_a_camera_that_fails_the_pre_probe(tmp_path, monkeypatch):
    import w_cyc
    import capkit as ck
    # two in-scope modes (mode scope: exactly 720 lines at >= 30 fps), so W-CYC plans its mode-switch variants
    modes = [ck.Mode(1280, 720, 30, 1), ck.Mode(960, 720, 30, 1), ck.Mode(1920, 1080, 30, 1)]
    monkeypatch.setattr(ck, "get_formats", lambda ctx, cam, cache=None: ({"x": 1}, {}))
    monkeypatch.setattr(ck, "mjpeg_modes", lambda fm: modes)
    ctx = _FakeCtx(tmp_path, [_cams()[0]], probe_ok=False)
    res = w_cyc.run(ctx)
    v = res["verdicts"]
    # 8 variants (incl. ds_ffmpeg_inproc and both skellycam framerates) + 2 mode-switch variants
    assert len(v) == 10 and all(x["rating"] == "untested" for x in v.values())
    assert all(x["evidence"]["pre_existing_fault"] for x in v.values())
    assert ctx.cmds == []                                  # no cycle command ran
    variants = res["measurements"]["cameras"]["kiyo"]["variants"]
    assert {"opencv_skellycam", "opencv_skellycam_fps30", "ds_ffmpeg_inproc", "mf_modeswitch"} <= set(variants)


def test_wcyc_run_probes_a_camera_whose_format_read_fails(tmp_path, monkeypatch):
    """Integration (2026-11-06): a wedged camera whose format list comes back empty must still be probed and rated
    untested (pre-existing fault), not dropped with 'no MJPEG mode found' and no verdicts."""
    import w_cyc
    import capkit as ck
    monkeypatch.setattr(ck, "get_formats", lambda ctx, cam, cache=None: (None, {"rc": 5}))
    monkeypatch.setattr(ck, "mjpeg_modes", lambda fm: [])
    ctx = _FakeCtx(tmp_path, [_cams()[0]], probe_ok=False)
    res = w_cyc.run(ctx)
    v = res["verdicts"]
    assert len(v) == 8 and all(x["rating"] == "untested" for x in v.values())       # no alt mode: 8 variants
    assert all(x["evidence"]["pre_existing_fault"] for x in v.values())
    assert ctx.cmds == []
    ctx2 = _FakeCtx(tmp_path, [_cams()[0]], probe_ok=True)                              # healthy: old behaviour
    res2 = w_cyc.run(ctx2)
    assert not res2["verdicts"] and "no MJPEG mode" in res2["measurements"]["cameras"]["kiyo"]["error"]


# ================================================================================================ W-KIYO
def _controls_json(ok=True, code="0x8007001F"):
    def ctl(key, ok_):
        hr = {"iam_get_range": "0x00000000", "iam_get": "0x00000000", "ks_basicsupport": "0x00000000",
              "ks_get": "0x80004002"} if ok_ else {"iam_get_range": code, "iam_get": "0x80004002",
                                                   "ks_basicsupport": "0x00000000", "ks_get": code}
        return {"key": key, "name": key.split(".")[-1], "supported": True, "via": "iam", "value": -4, "hr": hr}
    return {"controls": [ctl("cc.exposure", ok), ctl("pa.gain", ok)], "activate_ms": 20}


def test_wkiyo_analyse_controls_keeps_full_hr():
    import w_kiyo
    a = w_kiyo.analyse_controls(_controls_json(False), {"rc": 0})
    assert not a["ok"] and len(a["failing_controls"]) == 2 and a["device_error"]
    assert a["failing_controls"][0]["hr"]["iam_get_range"] == "0x8007001F"
    assert a["not_called_codes"] and "0x8007001F" in a["real_codes"]
    assert w_kiyo.analyse_controls(_controls_json(True), {"rc": 0})["ok"]


def test_wkiyo_poller_onset_and_fault(tmp_path, monkeypatch):
    import w_kiyo
    import capkit as ck
    seq = {"n": 0}

    def fake_get(ctx, cam, api, timeout_ms=0, timeout_s=0):
        seq["n"] += 1
        return _controls_json(ok=seq["n"] <= 2), {"rc": 0, "lock_wait_s": 0.0}

    monkeypatch.setattr(ck, "get_controls", fake_get)
    cam = _cams()[0]
    ctx = _FakeCtx(tmp_path, [cam])
    ctx.current_test = "W-CYC"
    p = w_kiyo.KiyoPoller(ctx, [cam], interval_s=0.01, mode="background")
    p.t_start = 0.0
    for i in range(3):
        p.poll_round(i, i * 0.01)
    d = p.result_for(cam)
    assert d["polls_per_api"] == {"mf": 3, "ds": 3} and d["ok_per_api"] == {"mf": 1, "ds": 1}
    assert d["failed_from_first_poll"] == {"mf": False, "ds": False}
    ff = d["first_failure"]["mf"]
    assert ff["test"] == "W-CYC" and ff["failing_controls"][0]["hr"]["ks_get"] == "0x8007001F"
    assert ff["vendor_processes"] == ["RazerAppEngine.exe:37240"]
    assert d["plug_in_age_at_start_s"] > 0
    assert ctx.kiyo_state["kiyo"]["stopped_answering"] and len(ctx.marked) == 1
    assert ctx.marked[0][1]["source"] == "kiyo_poller"
    v = w_kiyo.verdict_for(d, 1.0)
    assert v["rating"] == "no" and v["criteria"][1]["met"] is True and "note" not in v
    # failing from the very first poll
    seq["n"] = 100
    p2 = w_kiyo.KiyoPoller(ctx, [cam], interval_s=0.01)
    p2.t_start = 0.0
    p2.poll_round(0, 0.0)
    d2 = p2.result_for(cam)
    assert d2["failed_from_first_poll"] == {"mf": True, "ds": True}
    assert "first poll" in w_kiyo.verdict_for(d2, 1.0)["note"]


def test_wkiyo_lock_timeout_is_not_an_onset(tmp_path, monkeypatch):
    """A poll whose camera-lock wait timed out (a 400-cycle W-CYC command holds the lock > 600 s) made no camera
    call: it is 'not polled', never a first failure, a transition, a device fault or a 'no' verdict."""
    import w_kiyo
    import capkit as ck
    seq = {"n": 0}

    def fake_get(ctx, cam, api, timeout_ms=0, timeout_s=0):
        seq["n"] += 1
        if 3 <= seq["n"] <= 6:                       # rounds 1-2: the lock is busy (camlock rc 75, no child)
            r = {"rc": None, "lock_timed_out": True, "camlock_rc": 75, "lock_wait_s": 600.0, "stderr": ""}
            return None, ck.run_brief(r)
        return _controls_json(ok=True), {"rc": 0, "lock_wait_s": 0.0}

    monkeypatch.setattr(ck, "get_controls", fake_get)
    cam = _cams()[0]
    ctx = _FakeCtx(tmp_path, [cam])
    ctx.current_test = "W-CYC"
    p = w_kiyo.KiyoPoller(ctx, [cam], interval_s=0.01, mode="background")
    p.t_start = 0.0
    for i in range(4):
        p.poll_round(i, i * 0.01)
    d = p.result_for(cam)
    assert d["first_failure"] is None and d["transitions"] == [] and not d["stopped_answering"]
    assert d["polls_per_api"] == {"mf": 2, "ds": 2} and d["ok_per_api"] == {"mf": 2, "ds": 2}
    assert d["lock_busy_per_api"] == {"mf": 2, "ds": 2} and d["failure_codes"] == {}
    assert not getattr(ctx, "marked", []) and not (ctx.kiyo_state.get("kiyo") or {}).get("stopped_answering")
    assert w_kiyo.verdict_for(d, 1.0)["rating"] == "yes"
    assert sum(1 for q in d["polls"] if q.get("lock_busy")) == 4


def test_wkiyo_background_thread_start_stop(tmp_path, monkeypatch):
    import w_kiyo
    import capkit as ck
    monkeypatch.setattr(ck, "get_controls", lambda ctx, cam, api, **kw: (_controls_json(True), {"rc": 0}))
    monkeypatch.setattr(w_kiyo, "power_settings", lambda: {"stub": True})
    monkeypatch.setattr(ck, "new_result", lambda ctx, test, cams=None: {"test": test, "measurements": {},
                                                                        "verdicts": {}, "errors": []})
    ctx = _FakeCtx(tmp_path, _cams())
    p = w_kiyo.start_background(ctx)
    assert p is not None and ctx.kiyo_poller is p
    import time as _t
    _t.sleep(0.3)
    res = w_kiyo.finish(ctx, p)
    assert not p.running()
    v = res["verdicts"]["kiyo|kiyo|all"]
    assert v["rating"] == "yes" and res["measurements"]["mode"] == "background"


# ================================================================================================ runner
def test_runner_order_and_labels():
    import run_suite as rs
    order = [t for t, _ in rs.TESTS]
    # W-FMT-NOGRAB runs right after W-FMT (plan 6.2, Dom 2026-11-06)
    assert order[:7] == ["W-ENV", "W-POLICY", "W-TOPO", "W-ID", "W-FMT", "W-FMT-NOGRAB", "W-CTRL-LIST"]
    # integrated 2026-11-09 (review round 3: stream-start hypothesis): the Kiyo-sensitive captures early (W-MJPEG,
    # W-RAW, the short W-TS and W-PYMF captures), then the control tests (Kiyo share first), then the Kiyo's ~1,060
    # W-CYC reliability cycles in W-CYC-KIYO, W-MULTI and W-PYAV-LIST after them (W-PYAV-LIST meets a wedged Kiyo),
    # the other cameras' W-CYC reliability cycles last (W-KIYO is the background poller)
    # 2026-11-11: product-path tests after W-PYMF; W-AUTO out of the order (W-NODRIFT replaces it); W-CYC-KIYO
    # second-last so a Kiyo Pro wedge there costs the other tests nothing
    assert order[7:] == ["W-MJPEG", "W-RAW", "W-TS", "W-PYMF", "W-PYMF-ALL", "W-TBUMP", "W-NODRIFT", "W-GAIN",
                         "W-CTRL-EFFECT", "W-OCV-CTRL", "W-MULTI", "W-PYAV-LIST", "W-CYC-KIYO", "W-CYC", "W-KIYO"]
    assert [t for t, _ in rs.EXTRA_TESTS] == ["W-AUTO"]
    assert set(rs.OPTIONAL_TESTS) <= set(order) | {t for t, _ in rs.EXTRA_TESTS}
    assert "W-KIYO" in rs.BACKGROUND_TESTS
    assert rs.rating_label("reliability", {"rating": "no", "evidence": {"success_rate": 1.0}}) == "no (latency)"
    assert rs.rating_label("reliability", {"rating": "no", "evidence": {"success_rate": 0.0}}) == "no (failures)"
    assert rs.rating_label("reliability", {"rating": "no", "summary_label": "no (replug needed)"}) == \
        "no (replug needed)"
    assert rs.rating_label("G-MJPEG", {"rating": "partial"}) == "partial"


def test_runner_run_one_and_summary(tmp_path, monkeypatch):
    import run_suite as rs
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(suitectx, "camcmd_run", lambda argv, t, **kw: _run(DEVERR, rc=4))
    monkeypatch.setattr(suitectx, "_probe_mode", lambda c, cam, mode=None: (1280, 720, 30.0))
    ctx.mark_fault("kiyo", test="W-CYC", code="0x8007001F", stage="first_sample", source="test")
    seen = {}

    class Mod:
        @staticmethod
        def run(c):
            seen["gated"] = bool(c.camera_gated("kiyo"))
            return {"test": "W-TS", "measurements": {"cameras": {}}, "errors": [],
                    "verdicts": {"G-TS|kiyo|mf": c.fault_untested("kiyo"),
                                 "reliability|c922|opencv": {"rating": "no", "evidence": {"success_rate": 1.0}}}}

    st, res, intr = rs.run_one(ctx, "W-TS", Mod, None, 10.0)
    assert seen["gated"] and st["gated"] == {"kiyo": ctx.faults["kiyo"]["since_utc"]} and not intr
    assert res["device_fault_gate"]["gated_at_start"]
    assert res["device_faults"]["kiyo_dead_since"] == ctx.faults["kiyo"]["since_utc"]
    ctx.args.cycles, ctx.args.proc_cycles, ctx.args.frames, ctx.args.mjpeg_seconds = 1, 1, 1, 1
    p = rs.write_summary(ctx, [st], 0.0, ["W-TS"])
    md = p.read_text(encoding="utf-8")
    assert "## Device faults, first failures and the Kiyo onset" in md
    assert "(gated)" in md and "**no (latency)**" in md
    meta = rs._fault_meta(ctx)
    assert meta["kiyo_onset"]["kiyo"]["first_device_fault"]["test"] == "W-CYC"
    json.dumps(meta)


def test_runner_backstop_scan(tmp_path):
    import run_suite as rs
    ctx = _ctx(tmp_path)
    res = {"measurements": {"cameras": {"kiyo": {"x": {"api": "mf", "error": DEVERR["error"]}}}}}
    out = rs.backstop_scan(ctx, "W-MULTI", res)
    assert out and ctx.camera_faulted("kiyo")["source"] == "result_scan"


# ================================================================================================ re-analysis
@pytest.mark.skipif(not (RUN / "W-CYC.json").exists(), reason="Gerald run not present")
def test_reanalysis_wcyc(tmp_path):
    import w_cyc
    d = w_cyc.reanalyse(RUN, tmp_path / "W-CYC.json")
    kiyo = [k for k in d["verdicts"] if k.split("|")[1].startswith("1532:0e05")]
    assert kiyo and all(d["verdicts"][k]["rating"] == "untested" for k in kiyo)
    pf = next(iter(d["pre_existing_faults"].values()))
    assert pf["test"] == "W-MJPEG" and pf["mode"] == "MJPG 640x360@5"
    gen = next(c for k, c in d["measurements"]["cameras"].items() if k.startswith("4c4a:4a55"))
    assert gen["variants"]["opencv_inproc"]["re_arrival_cycle"] == 13
    c922 = next(k for k in d["verdicts"] if k.startswith("reliability|046d:085c") and k.endswith("ds_modeswitch"))
    assert d["verdicts"][c922]["rating"] == "partial"
    assert d["verdicts"][c922.replace("ds_modeswitch", "opencv_inproc")]["no_reason"] == "latency"


@pytest.mark.skipif(not (RUN / "run_suite.json").exists(), reason="Gerald run not present")
def test_reanalysis_run_suite(tmp_path):
    import run_suite as rs
    d = rs.reanalyse(RUN, tmp_path / "run_suite.json")
    f = next(iter(d["faults"].values()))
    assert f["is_kiyo"] and f["test"] == "W-MJPEG" and round(f["plug_in_age_s"] / 60) == 224
    assert {"W-CYC", "W-MULTI", "W-TS", "W-CTRL-EFFECT", "W-KIYO"} <= set(d["would_have_been_gated"])


RUN2 = RESEARCH / "results" / "windows" / "Gerald" / "suite_20261106T224912Z"


@pytest.mark.skipif(not (RUN2 / "run_suite.json").exists(), reason="Gerald gated run not present")
def test_reanalysis_run_suite_starts_from_the_recorded_gate(tmp_path):
    """Review round 3: a run that recorded its gate (run_suite.json faults) keeps that record (the Kiyo 0x8007001F in
    W-MULTI at a plug-in age of ~212 min, W-MJPEG gated), the W-KIYO poll rows add earlier evidence, and the note
    says the background poller ran."""
    import shutil
    import run_suite as rs
    run = tmp_path / "run"
    run.mkdir()
    for f in RUN2.glob("*.json"):
        shutil.copy(f, run / f.name)
    d = rs.reanalyse(run)
    assert (run / "reanalysis" / "run_suite.json").exists()
    k, f = next(iter(d["faults"].items()))
    assert k.startswith("1532:0e05") and f["test"] == "W-MULTI" and f["code"] == "0x8007001F"
    assert round(f["plug_in_age_s"] / 60) == 212 and f["source"].startswith("run_suite.json fault record")
    assert f["earlier_evidence"]["stage"] == "control_poll"
    assert set(d["gated_by_test_recorded"]) == {"W-MJPEG"} and "W-MJPEG" in d["would_have_been_gated"]
    assert list(d["would_have_been_gated"]["W-MJPEG"]) == [k]
    assert "background" in d["kiyo_onset"][k]["note"] and d["kiyo_onset"][k]["control_polls"]


@pytest.mark.skipif(not (RUN / "W-KIYO.json").exists(), reason="Gerald run not present")
def test_reanalysis_wkiyo(tmp_path):
    import w_kiyo
    d = w_kiyo.reanalyse(RUN, tmp_path / "W-KIYO.json")
    m = next(iter(d["measurements"]["cameras"].values()))
    assert round(m["plug_in_age_at_start_s"] / 60, 1) == 296.9          # N1: age at the first poll
    assert m["onset"]["failed_from_first_poll"] and m["onset"]["earlier_device_fault"]["test"] == "W-MJPEG"
    assert round(m["onset"]["earlier_device_fault_plug_in_age_s"] / 60) == 224


# ================================================================================================ W-CYC segments
def _fake_cycles(calls, stop_after=None):
    def f(ctx, cam, api, mode, *a, **kw):
        calls.append((cam["key"], api))
        if stop_after is not None and len(calls) > stop_after:
            raise KeyboardInterrupt
        rows = [{"i": i, "ok": True, "first_frame_ms": 300, "open_to_first_frame_ms": 400, "close_ms": 2,
                 "mode": mode.text} for i in range(3)]
        return rows, {}
    return f


def _cyc_setup(monkeypatch, calls, stop_after=None):
    import w_cyc
    import capkit as ck
    modes = [ck.Mode(1280, 720, 30, 1)]
    monkeypatch.setattr(ck, "get_formats", lambda ctx, cam, cache=None: ({"x": 1}, {}))
    monkeypatch.setattr(ck, "mjpeg_modes", lambda fm: modes)
    monkeypatch.setattr(ck, "activity_for_camera", lambda ctx, cam, doc=None: {"ok": None})
    monkeypatch.setattr(w_cyc, "_inproc", _fake_cycles(calls, stop_after))
    monkeypatch.setattr(w_cyc, "_newproc", lambda ctx, cam, api, mode, kp, n, out: _fake_cycles(calls, stop_after)(
        ctx, cam, api, mode))
    monkeypatch.setattr(w_cyc, "_read_exposure", lambda ctx, cam: None)
    monkeypatch.setattr(w_cyc, "_restore_exposure", lambda ctx, cam, orig: {"restored": None})
    return w_cyc


def test_wcyc_kiyo_segment_runs_early_and_the_rest_skips_it(tmp_path, monkeypatch):
    import w_cyc_kiyo
    calls: list = []
    w_cyc = _cyc_setup(monkeypatch, calls)
    ctx = _FakeCtx(tmp_path, _cams())
    ctx.cyc_kiyo_first = True
    rk = w_cyc_kiyo.run(ctx)
    assert rk["test"] == "W-CYC-KIYO" and list(rk["measurements"]["cameras"]) == ["kiyo"]
    assert {k for k, _ in calls} == {"kiyo"} and all("|kiyo|" in vk for vk in rk["verdicts"])
    assert rk["measurements"]["cameras_in_other_segment"] == {"c922": "W-CYC"}
    assert (ctx.out_dir / "W-CYC-KIYO" / "usbvideodevice_1532-0e05" / "mf_inproc_cycles.json").exists()
    calls.clear()
    rr = w_cyc.run(ctx)
    assert rr["test"] == "W-CYC" and list(rr["measurements"]["cameras"]) == ["c922"]
    assert {k for k, _ in calls} == {"c922"}
    assert w_cyc.estimate_s(ctx) > 0 and w_cyc_kiyo.estimate_s(ctx) > 0
    ctx.cyc_kiyo_first = False                       # --only W-CYC: every camera, the Kiyo first
    calls.clear()
    ra = w_cyc.run(ctx)
    assert list(ra["measurements"]["cameras"]) == ["kiyo", "c922"]


def test_wcyc_ctrl_c_keeps_finished_variants_and_reanalyse_rebuilds(tmp_path, monkeypatch):
    import json as _json
    import run_suite as rs
    calls: list = []
    w_cyc = _cyc_setup(monkeypatch, calls, stop_after=3)
    ctx = _FakeCtx(tmp_path, _cams())
    res = w_cyc.run(ctx)
    assert res["interrupted"] is True and any("interrupted" in e for e in res["errors"])
    kept = {vk for vk in res["verdicts"] if vk.startswith("reliability|kiyo|")}
    assert len(kept) == 3, kept                       # the three variants that finished before Ctrl-C
    part = _json.loads((ctx.out_dir / "W-CYC.partial.json").read_text(encoding="utf-8"))
    assert part["partial"] is True and set(part["verdicts"]) == set(res["verdicts"])
    # the runner treats the returned result as a Ctrl-C: it keeps it and stops the run
    calls.clear()
    w_cyc2 = _cyc_setup(monkeypatch, calls, stop_after=3)
    # never the real camcmd_run (camlock + wincam.exe): the 1-frame probes answer from this fake
    monkeypatch.setattr(suitectx, "camcmd_run", lambda argv, t, **kw: _run({"tool": "wincam", "ok": True,
                                                                             "frames": {"total": 1}}))
    st, res2, interrupted = rs.run_one(_ctx(tmp_path / "rs", _cams()), "W-CYC", w_cyc2, None, 1.0)
    assert interrupted is True and st["status"] == "interrupted"
    # reanalyse: an error-stub W-CYC.json (no cameras) falls back to the partial file, then to the rows on disk
    run_dir = ctx.out_dir
    (run_dir / "W-CYC.json").write_text(_json.dumps({"test": "W-CYC", "measurements": {}, "verdicts": {},
                                                     "errors": [{"runner_error": "interrupted"}]}), encoding="utf-8")
    d = w_cyc.reanalyse(run_dir)
    assert d["reanalysis_of"].endswith("W-CYC.partial.json") and len(d["verdicts"]) == 3
    (run_dir / "W-CYC.partial.json").unlink()
    (run_dir / "run_suite.json").write_text(_json.dumps({"cameras": _cams(), "tests": ["W-CYC"]}), encoding="utf-8")
    d = w_cyc.reanalyse(run_dir)
    assert "rows files" in d["reanalysis_of"] and len(d["verdicts"]) == 3
    assert all(vk.startswith("reliability|kiyo|") for vk in d["verdicts"])
