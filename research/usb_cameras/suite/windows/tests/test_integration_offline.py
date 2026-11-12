"""Cross-owner integration tests (no camera): the pieces the five 2026-11-06 fixers wrote must agree with each other.

    uv run --isolated --python 3.12 --no-project --with pytest --with numpy --with pillow --with simplejpeg \
        pytest suite/windows/tests/test_integration_offline.py -c suite/common/tests/pytest.ini

Covers: the suite gate's synthetic result is a device fault for every test owner's detector; a wedged camera's
``wincam controls`` answer (rc 4, device_not_answering, 0x8007001F) marks the fault through ctx.camcmd's scan and is
"not answering" for W-CTRL-EFFECT and W-KIYO; W-MULTI's event shape (device_not_ready as a camera LIST) against
rating.rate_bw; the shared raw-label rule; the runner's W-POLICY re-rate after W-FMT and --mjpeg-recapture-s.
"""
from __future__ import annotations

import json
import shutil
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

import suitectx  # noqa: E402
from common import rating, topology_model  # noqa: E402

RUN = RESEARCH / "results" / "windows" / "Gerald" / "suite_20261106T181941Z"
KIYO_MF = r"\\?\usb#vid_1532&pid_0e05&mi_00#a&1#{e5323777-f976-4f5b-9b55-b94699c46e44}\global"
KIYO_DS = r"\\?\usb#vid_1532&pid_0e05&mi_00#a&1#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
WINCAM = r"C:\x\wincam.exe"

#: what the rebuilt wincam prints for a camera whose every device-backed GET fails (rc 4)
DNA_CONTROLS = {
    "tool": "wincam", "subcommand": "controls", "read_only": True, "supported_count": 2, "get_ok_count": 0,
    "get_failed_count": 2, "get_failed_controls": ["exposure", "gain"], "device_not_answering": True,
    "error": {"stage": "control_get", "hr": "0x8007001F", "hr_name": "ERROR_GEN_FAILURE", "class": "device_error"},
    "controls": [
        {"key": "cc.exposure", "name": "exposure", "supported": True, "via": "IAMCameraControl", "get_ok": False,
         "get_hr": "0x8007001F", "get_hr_name": "ERROR_GEN_FAILURE",
         "hr": {"iam_get_range": "0x00000000", "iam_get": "0x8007001F", "ks_basicsupport": "0x00000000",
                "ks_get": None}},
        {"key": "pa.gain", "name": "gain", "supported": True, "via": "IAMVideoProcAmp", "get_ok": False,
         "get_hr": "0x8007001F", "get_hr_name": "ERROR_GEN_FAILURE",
         "hr": {"iam_get_range": "0x00000000", "iam_get": "0x8007001F", "ks_basicsupport": "0x00000000",
                "ks_get": None}},
        {"key": "ks.focal_length", "name": "focal_length", "supported": True, "via": "IKsControl", "get_ok": True,
         "get_hr": "0x00000000", "hr": {"iam_get_range": "0x80070490", "iam_get": None,
                                        "ks_basicsupport": "0x00000000", "ks_get": "0x00000000"}}]}


def _ctx(tmp_path):
    cams = [{"key": "kiyo", "name": "USB Video Device", "is_kiyo": True, "vid": "1532", "pid": "0e05",
             "mf_symlink": KIYO_MF, "ds_path": KIYO_DS, "last_arrival": "2026-11-06T14:59:24Z"}]
    ctx = suitectx.build_ctx(suitectx.default_args(), out_dir=tmp_path / "out", raw_dir=tmp_path / "raw",
                             wincam=WINCAM, cameras=cams)
    ctx.arrival_fn = lambda cs: {"cameras": {c["key"]: {"present": True, "last_arrival": c.get("last_arrival")}
                                             for c in cs}}
    return ctx


def _run(obj, rc=0):
    return {"argv": [], "rc": rc, "stdout": json.dumps(obj), "stderr": "", "elapsed_s": 0.05, "timed_out": False,
            "killed": False, "lock_wait_s": 0.0, "lock_timed_out": False}


# ======================================================================================= gate <-> test owners
def test_gate_synthetic_result_is_a_fault_for_every_owner(tmp_path, monkeypatch):
    import capkit as ck
    import w_ts
    import run_suite as rs
    ctx = _ctx(tmp_path)
    calls = []
    monkeypatch.setattr(suitectx, "camcmd_run", lambda argv, t, **kw: calls.append(argv) or _run({"ok": True}))
    ctx.mark_fault("kiyo", test="W-CTRL-LIST", code="0x8007001F", stage="control_get", source="test")
    monkeypatch.setattr(ctx, "health_probe", lambda *a, **k: {"ok": False})     # re-probe: still dead
    ctx.begin_test("W-TS", probe=False)
    assert ctx.camera_gated("kiyo")
    r = ctx.camcmd([WINCAM, "capture", "--api", "mf", "--device", KIYO_MF, "--width", 1280, "--height", 720],
                   timeout_s=10)
    assert not calls and r["gate_skipped"] and r["rc"] == 4          # never reached the camera
    obj = json.loads(r["stdout"])
    # capkit (W-MJPEG / W-CTRL-EFFECT) and W-TS both see a device fault, never a 'no' for the API
    assert ck.fault_from_result("mf", obj, r)["kind"] == "gated"
    f = w_ts._fault_of(obj, r, "MJPG 1280x720@30")
    assert f["device_fault"] and f["first_fault_utc"] == ctx.camera_faulted("kiyo")["since_utc"]
    # the capkit adapters read the same registry
    assert ck.device_gated(ctx, ctx.camera("kiyo"))["utc"] == ctx.camera_faulted("kiyo")["since_utc"]
    # the gate's verdict and rating.device_fault_untested agree on the contract evidence
    v1 = ctx.fault_untested("kiyo")
    v2 = rating.device_fault_untested(ctx.camera_faulted("kiyo"))
    for v in (v1, v2):
        assert v["rating"] == "untested" and v["evidence"]["device_fault"] is True
        assert v["evidence"]["first_fault_utc"] == ctx.camera_faulted("kiyo")["since_utc"]
        assert v["evidence"]["fault_code"] == "0x8007001F"
    assert "device fault since" in v1["note"] and "device fault since" in v2["note"]
    assert rs.rating_label("G-TS", v2).startswith("untested")
    # 2026-11-11 dead rule: a dead Kiyo Pro gets no command at all, controls included
    r2 = ctx.camcmd([WINCAM, "controls", "--api", "mf", "--device", KIYO_MF, "--read-only"], timeout_s=10)
    assert not calls and r2["gate_skipped"]
    ctx.end_test("W-TS")


def test_wedged_controls_answer_marks_fault_and_is_not_answering(tmp_path, monkeypatch):
    import w_ctrl_effect
    import w_kiyo
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(suitectx, "camcmd_run", lambda argv, t, **kw: _run(DNA_CONTROLS, rc=4))
    r = ctx.camcmd([WINCAM, "controls", "--api", "mf", "--device", KIYO_MF, "--read-only"], timeout_s=10)
    rec = ctx.camera_faulted("kiyo")
    assert rec and rec["code"] == "0x8007001F" and rec["source"] == "camcmd_scan"
    assert ctx.first_failure["kiyo"]["code"] == "0x8007001F"
    j = json.loads(r["stdout"])
    assert w_ctrl_effect.not_answering(j, r) == (True, "0x8007001F")
    a = w_kiyo.analyse_controls(j, {"rc": 4})
    assert not a["ok"] and a["device_error"] and a["device_not_answering"]
    assert [c["name"] for c in a["failing_controls"]] == ["exposure", "gain"]      # focal_length answered
    assert a["failing_controls"][0]["get_hr"] == "0x8007001F" and a["real_codes"] == ["0x8007001F"]
    assert a["get_ok_count"] == 0 and a["get_failed_count"] == 2


def test_wkiyo_new_wincam_null_hr_is_not_a_failure():
    """The rebuilt wincam emits null for calls never made (ks_get on an IAM control): an answering control must not
    be counted as failing, and no 'not called' sentinel appears."""
    import w_kiyo
    j = json.loads(json.dumps(DNA_CONTROLS))
    j.update(device_not_answering=False, error=None, get_ok_count=2, get_failed_count=0)
    for c in j["controls"]:
        c.update(get_ok=True, get_hr="0x00000000")
        c["hr"]["iam_get"] = "0x00000000" if c["hr"]["iam_get"] is not None else None
    a = w_kiyo.analyse_controls(j, {"rc": 0})
    assert a["ok"] and not a["failing_controls"] and not a["not_called_codes"] and len(a["answered_controls"]) == 3


# ======================================================================================= W-MULTI <-> rate_bw
def test_wmulti_event_shape_against_rate_bw():
    """W-MULTI emits device_not_ready as a LIST of cameras; a not-ready-only event carries classified_class
    'device_not_ready' (excluded, also from false 'over'); a real refusal next to a not-ready camera keeps its
    class and still counts."""
    dnr_only = {"label": "#30", "api": "ds", "predicted_verdict": "over", "observed_refused": False,
                "classified_class": "device_not_ready", "device_not_ready": ["4c4a:4a55"], "retry_ok": True}
    mixed = {"label": "#31", "api": "ds", "predicted_verdict": "over", "observed_refused": True,
             "classified_class": "bandwidth_certain", "device_not_ready": ["046d:085c"], "retry_ok": True,
             "retry_first_try_ok": False, "message_ports_other_domains": True}
    v = rating.rate_bw([dnr_only, mixed], labels_raw=False)
    assert v["evidence"]["device_not_ready"]["count"] == 1 and v["evidence"]["false_over"] == []
    assert v["rating"] == "yes"
    assert v["evidence"]["retry"] == {"final_try_failed": 0, "first_try_failed_final_ok": 1}


def test_shared_raw_label_rule():
    labels = ["port 3 (HS10, Intel USB 3.20 eXtensible Host Controller)", "HS10", r"\_SB.PC00.XHCI.RHUB.HS10",
              "PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(10)", "rear I/O, top USB-A (panel position)", "c922 Pro Stream"]
    for lb in labels:
        assert rating.label_is_raw(lb) == topology_model.label_is_raw(lb), lb
    assert not rating.label_is_raw(labels[0])           # controller + port number is not raw
    assert rating.label_is_raw(labels[3])


# ======================================================================================= runner
def test_parser_has_mjpeg_recapture_flag():
    import run_suite as rs
    a = rs.resolve_args(rs.build_parser().parse_args(["--quick", "--mjpeg-recapture-s", "0"]))
    assert a.mjpeg_recapture_s == 0.0
    assert rs.resolve_args(rs.build_parser().parse_args([])).mjpeg_recapture_s is None   # w_mjpeg default rules


@pytest.mark.skipif(not ((RUN / "W-POLICY.json").exists() and (RUN / "W-FMT.json").exists()),
                    reason="Gerald run not present")
def test_rerate_policy_after_fmt(tmp_path):
    import run_suite as rs
    import w_policy
    ctx = _ctx(tmp_path)
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(RUN / "W-POLICY.json", ctx.out_dir / "W-POLICY.json")
    status = [{"test": "W-POLICY", "verdicts": {}}]
    mods = {"W-POLICY": (w_policy, None)}
    assert rs.rerate_policy_after_fmt(ctx, mods, status) is None          # no W-FMT.json yet: nothing done
    shutil.copy(RUN / "W-FMT.json", ctx.out_dir / "W-FMT.json")
    rr = rs.rerate_policy_after_fmt(ctx, mods, status)
    assert rr is not None
    doc = json.loads((ctx.out_dir / "W-POLICY.json").read_text(encoding="utf-8"))
    assert doc["verdicts"]["policy_traps"]["rating"] == "yes"            # corroborated by the run's W-FMT
    assert "policy_traps_at_run_time" in doc["verdicts"] and doc["rerated_after"]["test"] == "W-FMT"
    assert status[0]["verdicts"]["policy_traps"]["rating"] == "yes"
    assert "policy_traps_at_run_time" not in status[0]["verdicts"]
    assert (RUN / "W-POLICY.json").read_bytes() != (ctx.out_dir / "W-POLICY.json").read_bytes()   # copy edited


# ======================================================================================= W-ID and --camera
def test_wid_maps_every_discovered_camera_under_the_camera_filter(tmp_path, monkeypatch):
    """W-ID opens no camera: with the runner's --camera debugging filter it must still map the filtered-out cameras
    (else every API list has an unmappable entry and G-ID reads 'no'); ctx.cameras is restored afterwards."""
    import _enum_util as U
    import w_id
    c922_mf = r"\\?\usb#vid_046d&pid_085c&mi_00#8&2#{e5323777-f976-4f5b-9b55-b94699c46e44}\global"
    c922_ds = r"\\?\usb#vid_046d&pid_085c&mi_00#8&2#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
    ctx = _ctx(tmp_path)
    kiyo = ctx.cameras[0]
    kiyo.update(instance_id=r"USB\VID_1532&PID_0E05\a&1", serial=None)
    c922 = {"key": "c922", "name": "c922", "is_kiyo": False, "vid": "046d", "pid": "085c", "mf_symlink": c922_mf,
            "ds_path": c922_ds, "instance_id": r"USB\VID_046D&PID_085C\C922SN01", "serial": "C922SN01"}
    ctx.discovery = {"cameras": [kiyo, c922]}
    ctx.cameras = [c922]                                   # what run_suite --camera 085c leaves
    ctx.args.quick, ctx.args.repeats = True, 2
    links = {kiyo["mf_symlink"]: "kiyo", kiyo["ds_path"]: "kiyo", c922_mf: "c922", c922_ds: "c922"}
    lst = {"mf": {"devices": [{"index": 0, "symlink": kiyo["mf_symlink"]}, {"index": 1, "symlink": c922_mf}]},
           "ds": {"devices": [{"index": 0, "device_path": kiyo["ds_path"]}, {"index": 1, "device_path": c922_ds}]}}
    monkeypatch.setattr(U, "run_json", lambda c, argv, timeout_s, cam: (lst, {"rc": 0}) if "list" in argv
                        else (None, {"rc": 1, "error": "helper not run offline"}))
    monkeypatch.setattr(U, "key_for_link", lambda c, link: links.get(link) if any(
        x.get("key") == links.get(link) for x in c.cameras) else None)
    monkeypatch.setattr(U.suitectx, "discover", lambda *a, **k: {"cameras": [kiyo, c922]})
    monkeypatch.setattr(U.suitectx, "arrival_snapshot", lambda cams: {"cameras": {}})
    res = w_id.run(ctx)
    assert ctx.cameras == [c922]                           # restored
    m = res["measurements"]
    assert set(m["expected_keys"]) == {"kiyo", "c922"} and m["camera_filter"]["filtered_keys"] == ["kiyo"]
    assert m["per_api"]["mf"]["one_to_one_every_run"] and m["per_api"]["ds"]["all_mappable"]
    assert res["verdicts"]["key_source_stability"]["rating"] == "yes"


# ======================================================================================= wedged Kiyo end to end
def test_wedged_kiyo_is_faulted_once_and_later_tests_skip_it(tmp_path, monkeypatch):
    """The Kiyo of 2026-11-06 (every stream start -> 0x8007001F, control plane still answering), driven through the
    runner's run_one hooks and the real W-CTRL-LIST / W-CYC / W-CTRL-EFFECT / W-TS / W-MJPEG modules: the first
    streaming call (W-CYC's 1-frame probe) marks it faulted; each later test re-probes it ONCE and then makes no
    other streaming call; its cells are 'untested' with the fault timestamp, never 'no'."""
    import capkit as ck
    import run_suite as rs
    import w_ctrl_effect
    import w_ctrl_list
    import w_cyc
    import w_mjpeg
    import w_ts
    ctx = _ctx(tmp_path)
    ctx.args.quick = True
    streaming_calls: list = []
    healthy = json.loads(json.dumps(DNA_CONTROLS))
    healthy.update(device_not_answering=False, error=None, get_ok_count=2, get_failed_count=0)
    for c in healthy["controls"]:
        c.update(get_ok=True, get_hr="0x00000000", value=-4, min=-11, max=-2, step=1, flags_names=["auto"])

    def fake_run(argv, t, **kw):
        a = [str(x) for x in argv]
        if suitectx.is_streaming_argv(a):
            streaming_calls.append((ctx.current_test, a[1] if len(a) > 1 else a[0]))
            return _run({"tool": "wincam", "ok": False, "utc_started": "2026-11-06T21:30:00Z",
                         "error": {"stage": "first_sample", "hr": "0x8007001F", "hr_name": "ERROR_GEN_FAILURE",
                                   "class": "device_error"}}, rc=4)
        if "controls" in a:
            return _run(healthy)
        return _run({"tool": "wincam", "ok": True})

    monkeypatch.setattr(suitectx, "camcmd_run", fake_run)
    # two in-scope modes (mode scope: >= 30 fps, >= 720 lines), so W-CYC plans its mode-switch variants
    modes = [ck.Mode(1280, 720, 30, 1), ck.Mode(1920, 1080, 30, 1)]
    monkeypatch.setattr(ck, "get_formats", lambda c, cam, cache=None: ({"x": 1}, {}))
    monkeypatch.setattr(ck, "mjpeg_modes", lambda fm: modes)
    status = []
    for t, mod in (("W-CTRL-LIST", w_ctrl_list), ("W-CYC", w_cyc), ("W-CTRL-EFFECT", w_ctrl_effect),
                   ("W-TS", w_ts), ("W-MJPEG", w_mjpeg)):
        n0 = len(streaming_calls)
        st, res, _ = rs.run_one(ctx, t, mod, None, 1.0)
        status.append((t, st, res, len(streaming_calls) - n0))
    rec = ctx.faults["kiyo"]
    assert rec["test"] == "W-CYC" and rec["code"] == "0x8007001F"
    since = rec["since_utc"]
    by = {t: (st, res, n) for t, st, res, n in status}
    assert by["W-CTRL-LIST"][2] == 0 and by["W-CYC"][2] == 1          # only W-CYC's 1-frame probe streamed
    for t in ("W-CTRL-EFFECT", "W-TS", "W-MJPEG"):
        st, res, n = by[t]
        assert st["status"] == "ok", (t, st, res.get("errors"))
        assert n == 0, (t, n)                                          # dead rule: no re-probe, nothing else
        assert st["gated"] == {"kiyo": since}
        cells = {k: v for k, v in (res.get("verdicts") or {}).items()
                 if isinstance(v, dict) and "rating" in v and "kiyo" in k}
        assert cells, t
        for k, v in cells.items():
            assert v["rating"] == "untested", (t, k, v["rating"], v.get("note"))
            ev = v.get("evidence") or {}
            assert ev.get("device_fault") is True and ev.get("first_fault_utc") == since, (t, k, ev)
    cyc = {k: v for k, v in by["W-CYC"][1]["verdicts"].items() if "kiyo" in k}
    assert len(cyc) == 5 and all(v["rating"] == "untested" for v in cyc.values())   # 2026-11-12: no OpenCV variants
    assert ctx.first_failure["kiyo"]["test"] == "W-CYC"
    # the summary marks the gated cells
    p = rs.write_summary(ctx, [st for _, st, _, _ in status], 0.0, [t for t, *_ in status])
    assert "(gated)" in p.read_text(encoding="utf-8")


def test_format_fallback_is_not_a_first_failure(tmp_path, monkeypatch):
    """PyAV's raw-video fallback (rc 4, stage 'format', frames delivered) is rated by the tests; it must not become
    the camera's suite-wide first failure (seen on the replugged Kiyo, 2026-11-06 21:21Z)."""
    ctx = _ctx(tmp_path)
    fb = {"tool": "pyav_ds", "ok": False, "format_fallback": True, "frames": 30,
          "error": {"stage": "format", "class": "other", "message": "negotiated rawvideo, not mjpeg"}}
    monkeypatch.setattr(suitectx, "camcmd_run", lambda argv, t, **kw: _run(fb, rc=4))
    ctx.camcmd(["uv", "run", "--script", r"C:\h\pyav_ds.py", "capture", "--device", KIYO_DS], timeout_s=10)
    assert "kiyo" not in ctx.first_failure and not ctx.camera_faulted("kiyo")
    other = {"tool": "pyav_ds", "ok": False, "error": {"stage": "open", "errno": 5, "class": "other"}}
    monkeypatch.setattr(suitectx, "camcmd_run", lambda argv, t, **kw: _run(other, rc=4))
    ctx.camcmd(["uv", "run", "--script", r"C:\h\pyav_ds.py", "capture", "--device", KIYO_DS], timeout_s=10)
    assert ctx.first_failure["kiyo"]["stage"] == "open"


def test_bookkeeping_errors_never_stop_the_run(tmp_path, monkeypatch):
    """run_suite.json / summary.md writes after a test are guarded: an OSError or a formatting error is logged and
    the remaining tests still run."""
    import run_suite as rs
    ctx = _ctx(tmp_path)
    logs: list[str] = []
    monkeypatch.setattr(ctx, "log", logs.append)

    def locked(*a, **k):
        raise PermissionError("summary.md is locked by the indexer")
    monkeypatch.setattr(rs, "write_summary", locked)
    monkeypatch.setattr(ctx, "write", locked)
    meta: dict = {}
    assert rs._write_progress(ctx, meta, [{"test": "W-ENV", "verdicts": {}}], 0.0, ["W-ENV"], after="W-ENV") is None
    assert any("run_suite.json" in x for x in logs) and any("summary.md" in x for x in logs)
    assert meta["status"] == [{"test": "W-ENV"}]
