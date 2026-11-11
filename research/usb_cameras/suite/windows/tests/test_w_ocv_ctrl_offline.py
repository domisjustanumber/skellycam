"""W-OCV-CTRL offline tests (no camera, no OpenCV): the convention derivation, and an end-to-end run in which the
REAL helpers/opencv_ctrl.py main() runs in-process against a fake ``cv2`` module and an emulated DirectShow side
channel (test_w_auto_offline.FakeCam is the camera model), with the segment lengths shortened.

    uv run --isolated --python 3.12 --no-project --with pytest pytest suite/windows/tests/test_w_ocv_ctrl_offline.py \
        -c suite/common/tests/pytest.ini
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIN = HERE.parent
for p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import capkit as ck  # noqa: E402
import opencv_ctrl as oc  # noqa: E402
import test_w_auto_offline as TA  # noqa: E402
import w_ocv_ctrl as wo  # noqa: E402


def test_meaning_and_derive_convention():
    assert oc.meaning("manual", "manual") == "manual"
    assert oc.meaning("auto", "auto") == "auto"
    assert oc.meaning("auto", "manual") == "ignored"
    assert oc.meaning("manual", "auto") == "toggles"
    rows = [{"value": 0.25, "from_auto": "manual", "from_manual": "manual"},
            {"value": 0.75, "from_auto": "auto", "from_manual": "auto"},
            {"value": 1.0, "from_auto": "auto", "from_manual": "manual"},
            {"value": 3.0, "from_auto": "manual", "from_manual": "manual"}]
    c = oc.derive_convention(rows)
    assert c["manual_value"] == 0.25 and c["auto_value"] == 0.75 and c["meanings"]["1.0"] == "ignored"
    assert oc.derive_convention([{"value": 0, "from_auto": None, "from_manual": "manual"}])["manual_value"] is None


# ------------------------------------------------------------------------------------------------ fake OpenCV
class FakeFrame:
    def __init__(self, payload: bytes):
        self.shape = (720, 1280, 3)
        self.payload = payload


class FakeBuf:
    def __init__(self, b: bytes):
        self.b = b

    def tobytes(self) -> bytes:
        return self.b


class FakeCV2:
    CAP_DSHOW, CAP_MSMF = 700, 1400
    CAP_PROP_FRAME_WIDTH, CAP_PROP_FRAME_HEIGHT, CAP_PROP_FPS, CAP_PROP_FOURCC = 3, 4, 5, 6
    CAP_PROP_EXPOSURE, CAP_PROP_AUTO_EXPOSURE, CAP_PROP_FOCUS, CAP_PROP_AUTOFOCUS = 15, 21, 28, 39
    IMWRITE_JPEG_QUALITY = 1
    __version__ = "4.12.0-fake"

    def __init__(self, cam, ae_map, af_map):
        self.cam, self.ae_map, self.af_map = cam, ae_map, af_map

    def VideoCapture(self, idx, api):  # noqa: N802 - cv2 API
        return FakeCap(self)

    @staticmethod
    def VideoWriter_fourcc(*c):  # noqa: N802
        return sum(ord(ch) << (8 * i) for i, ch in enumerate(c))

    @staticmethod
    def imencode(ext, frame, params):
        return True, FakeBuf(frame.payload)


class FakeCap:
    def __init__(self, cv):
        self.cv, self.props = cv, {3: 640, 4: 480, 5: 30, 6: FakeCV2.VideoWriter_fourcc(*"YUY2")}
        self.ae = 0.75

    def isOpened(self):  # noqa: N802
        return True

    def set(self, prop, v):
        cam, now = self.cv.cam, time.perf_counter_ns()
        if prop == FakeCV2.CAP_PROP_AUTO_EXPOSURE:
            m = self.cv.ae_map.get(round(v, 2))
            if m:
                cam.apply("exposure", m, now)
            self.ae = v
            return m is not None
        if prop == FakeCV2.CAP_PROP_AUTOFOCUS:
            m = self.cv.af_map.get(round(v, 2))
            if m:
                cam.apply("focus", m, now)
            return m is not None
        if prop == FakeCV2.CAP_PROP_EXPOSURE:
            cam.apply("exposure", int(v), now)
            return True
        if prop == FakeCV2.CAP_PROP_FOCUS:
            cam.apply("focus", int(v), now)
            return True
        self.props[prop] = v if prop != FakeCV2.CAP_PROP_FOURCC else int(v)
        return True

    def get(self, prop):
        cam = self.cv.cam
        if prop == FakeCV2.CAP_PROP_EXPOSURE:
            stale = getattr(self.cv, "stale_exposure_get", None)      # MSMF: get() returns a stale value
            return float(stale if stale is not None else cam.st["exposure"]["value"])
        if prop == FakeCV2.CAP_PROP_FOCUS:
            return float(cam.st["focus"]["value"])
        if prop == FakeCV2.CAP_PROP_AUTO_EXPOSURE:
            return self.ae
        if prop == FakeCV2.CAP_PROP_AUTOFOCUS:
            return 1.0 if cam.st["focus"]["flags"] == 1 else 0.0
        return float(self.props.get(prop, 0))

    def read(self):
        time.sleep(0.004)
        luma, sharp = self.cv.cam.metric(time.perf_counter_ns())
        return True, FakeFrame(f"FAKE luma={luma:.4f};sharp={sharp:.6f}".encode())

    def release(self):
        return None


def _side_run(cam):
    def run(self, extra):
        t0 = time.perf_counter_ns()
        if "--set" in extra:
            for n, v in TA._parse_sets(extra[extra.index("--set") + 1]):
                cam.apply(n, v, t0)
        st = {n: {"value": cam.st[n]["value"], "flags": cam.st[n]["flags"], "mode": oc.mode_of(cam.st[n]["flags"])}
              for n in ("exposure", "focus")}
        self.calls += 1
        return {"t_start_ns": t0, "t_end_ns": time.perf_counter_ns(), "rc": 0, "timed_out": False, "ok": True,
                "state": st}
    return run


class OcvCtx(TA.FakeCtx):
    def __init__(self, tmp, cam, cv):
        super().__init__(tmp, cam)
        self.cv = cv
        self.args.ctrl_runs = 3
        self.cameras[0].update(opencv_dshow_index=1, opencv_msmf_index=2)
        self.helper_calls = []

    def camcmd(self, argv, timeout_s, **k):
        a = [str(x) for x in argv]
        script = next((i for i, x in enumerate(a) if x.endswith("opencv_ctrl.py")), None)
        if script is None:
            return super().camcmd(argv, timeout_s, **k)
        self.helper_calls.append(a)
        out = io.StringIO()
        old_argv, rc = sys.argv, None
        sys.argv = ["opencv_ctrl.py", *a[script + 1:]]
        try:
            with contextlib.redirect_stdout(out):
                oc.main()
        except SystemExit as e:
            rc = e.code
        finally:
            sys.argv = old_argv
        return {"rc": rc, "stdout": out.getvalue(), "stderr": "", "elapsed_s": 1.0, "timed_out": False}


def _install(monkeypatch, cam, cv):
    TA._install(monkeypatch, cam)
    monkeypatch.setitem(sys.modules, "cv2", cv)
    monkeypatch.setattr(oc.Side, "_run", _side_run(cam))
    monkeypatch.setattr(oc.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no wincam offline")))
    for name, v in (("SEG_S", 0.08), ("FOCUS_SEG_S", 0.08), ("BASELINE_S", 0.3), ("AE_ON_S", 0.3), ("AF_ON_S", 0.3)):
        monkeypatch.setattr(wo, name, v)


def _fast_cam(**kw):
    cam = TA.FakeCam(**kw)
    cam.ae_delay_ns, cam.af_delay_ns = 15e6, 25e6
    return cam


def test_end_to_end_fake_opencv(tmp_path, monkeypatch):
    cam = _fast_cam()
    cv = FakeCV2(cam, ae_map={0.25: "manual", 0.75: "auto"}, af_map={0.0: "manual", 1.0: "auto"})
    _install(monkeypatch, cam, cv)
    ctx = OcvCtx(tmp_path, cam, cv)
    res = wo.run(ctx)
    key = ctx.cameras[0]["key"]
    v = res["verdicts"]
    assert set(v) == {f"G-CTRL|{key}|opencv_dshow", f"G-CTRL|{key}|opencv_msmf"} | \
        {f"G-CTRL-AUTO|{key}|opencv_{b}-{c}" for b in ("dshow", "msmf") for c in ("ae", "af")}
    for k, x in v.items():
        assert x["rating"] == "yes", (k, x.get("note"), [c for c in x["criteria"] if c["met"] is not True])
    assert len(ctx.helper_calls) == 2 * 3 * 2                     # backends x runs x phases
    b = res["measurements"]["cameras"][key]["backends"]["dshow"]
    conv = b["conventions"]
    assert conv["auto_exposure"]["manual_value"] == 0.25 and conv["auto_exposure"]["auto_value"] == 0.75
    assert conv["exposure_get_equals_camera"] is True
    assert b["restore"]["restored"] is True
    assert cam.st["exposure"] == {"value": -7, "flags": 2} and cam.st["focus"]["flags"] == 1
    r0 = b["runs"][0]
    assert r0["before"]["values"]["focus_before"] != 0             # the most defocused value, not the sharp one
    assert r0["before"]["exposure"]["held_through_start"] is True
    assert (tmp_path / "out" / r0["after_detail_file"]).exists()
    assert "auto_on_points" not in r0["after"]["exposure"]          # kept in the detail file, not the result
    (tmp_path / "out" / "W-OCV-CTRL.json").write_text(json.dumps(res), encoding="utf-8")
    assert wo.reanalyze(tmp_path / "out")["changes"] == []


def test_pre_ae_exposure_moves_away_from_the_ae_value():
    ev = [-9.0, -7.0, -4.0]                      # 25/50/75% of -11..-2
    assert oc.pre_ae_exposure(ev, -4, 1) == -7.0   # C922 / Kiyo AE -4: the nearest sweep value >= 2 steps darker
    assert oc.pre_ae_exposure(ev, -5, 1) == -7.0
    assert oc.pre_ae_exposure(ev, -7, 1) is None   # the last value is already 3 steps away
    assert oc.pre_ae_exposure(ev, None, 1) is None
    assert oc.pre_ae_exposure([-6.0, -5.0, -4.0], -5, 1) is None   # no sweep value 2 steps away
    assert oc.pre_ae_exposure([-3.0, -2.0, -1.0], -2, 1) is None
    assert oc.pre_ae_exposure([0.0, 2.0, 1.0], 0, 1) == 2.0         # nothing darker: the nearest far value


def test_ae_on_starts_from_a_value_away_from_the_ae_value(tmp_path, monkeypatch):
    cam = _fast_cam()
    cam.st["exposure"]["value"] = -4                # AE reports the sweep's last value (75% of -11..-2)
    cv = FakeCV2(cam, ae_map={0.25: "manual", 0.75: "auto"}, af_map={0.0: "manual", 1.0: "auto"})
    _install(monkeypatch, cam, cv)
    ctx = OcvCtx(tmp_path, cam, cv)
    ctx.args.ctrl_runs = 1
    res = wo.run(ctx)
    key = ctx.cameras[0]["key"]
    after = res["measurements"]["cameras"][key]["backends"]["dshow"]["runs"][0]["after"]["exposure"]
    assert after["values"][-1] == -4
    pre = after["pre_ae_on_event"]
    assert pre and pre["tag"] == "exp_pre_ae" and abs(pre["value"] - -4) >= 2
    assert after["auto_on"]["toggles"][0]["value"] == pre["value"]
    assert res["verdicts"][f"G-CTRL-AUTO|{key}|opencv_dshow-ae"]["rating"] == "yes"


def test_backend_without_an_auto_value(tmp_path, monkeypatch):
    cam = _fast_cam()
    cv = FakeCV2(cam, ae_map={0.25: "manual"}, af_map={0.0: "manual", 1.0: "auto"})
    _install(monkeypatch, cam, cv)
    ctx = OcvCtx(tmp_path, cam, cv)
    ctx.args.ctrl_runs = 1
    res = wo.run(ctx)
    key = ctx.cameras[0]["key"]
    ae = res["verdicts"][f"G-CTRL-AUTO|{key}|opencv_dshow-ae"]
    assert ae["rating"] == "no" and ae["summary_label"] == "no (OpenCV cannot switch auto on)"
    assert res["verdicts"][f"G-CTRL-AUTO|{key}|opencv_dshow-af"]["rating"] == "yes"
    # OpenCV could not turn AE back on, the wincam restore still did
    assert cam.st["exposure"] == {"value": -7, "flags": 2}


def _hanging_helper(ctx, cam, calls):
    """Every opencv_ctrl run hangs (killed at its timeout) after leaving manual exposure 0 on the camera."""
    def camcmd(argv, timeout_s, **k):
        a = [str(x) for x in argv]
        if any(x.endswith("opencv_ctrl.py") for x in a):
            calls.append(a)
            cam.apply("exposure", 0, time.perf_counter_ns())
            return {"rc": None, "stdout": "", "stderr": "", "timed_out": True, "elapsed_s": timeout_s}
        return TA.FakeCtx.camcmd(ctx, argv, timeout_s, **k)
    return camcmd


def test_hung_helper_camera_still_dead_restore_still_attempted(tmp_path, monkeypatch):
    cam = _fast_cam()
    cv = FakeCV2(cam, ae_map={0.25: "manual", 0.75: "auto"}, af_map={0.0: "manual", 1.0: "auto"})
    _install(monkeypatch, cam, cv)
    ctx = OcvCtx(tmp_path, cam, cv)
    calls, probes = [], []
    ctx.camcmd = _hanging_helper(ctx, cam, calls)
    monkeypatch.setattr(ck, "health_check", lambda *a, **k: probes.append(k) or {
        "ok": False, "fault_like": True, "code": "timeout"})
    res = wo.run(ctx)
    key = ctx.cameras[0]["key"]
    assert len(calls) == 1 and len(probes) == 1                      # nothing more after the hang
    assert ck.device_fault(ctx, ctx.cameras[0]) is not None
    assert res["verdicts"][f"G-CTRL|{key}|opencv_dshow"]["rating"] == "untested"
    assert res["verdicts"][f"G-CTRL|{key}|opencv_msmf"]["rating"] == "untested"
    b = res["measurements"]["cameras"][key]["backends"]["dshow"]
    # the bounded wincam restore ran although the camera did not answer the probe, and it is recorded
    assert b["restore"]["after_hang"] is True and b["restore"]["camera_answered_probe"] is False
    assert b["restore"]["restored"] is True and cam.st["exposure"] == {"value": -7, "flags": 2}
    assert b["health_probe_after_hang"]["ok"] is False


def test_hung_helper_camera_answers_fault_cleared_next_backend_runs(tmp_path, monkeypatch):
    """Smoke 2026-11-09: both Logitech cameras answered the health probe 1 s after an MSMF 'hang'; the restore was
    skipped ('device fault'). Now: probe, clear the fault, restore, and the next backend runs."""
    cam = _fast_cam()
    cv = FakeCV2(cam, ae_map={0.25: "manual", 0.75: "auto"}, af_map={0.0: "manual", 1.0: "auto"})
    _install(monkeypatch, cam, cv)
    ctx = OcvCtx(tmp_path, cam, cv)
    calls = []
    ctx.camcmd = _hanging_helper(ctx, cam, calls)
    monkeypatch.setattr(ck, "health_check", lambda *a, **k: {"ok": True, "frames": 1})
    res = wo.run(ctx)
    key = ctx.cameras[0]["key"]
    assert len(calls) == 2                                           # dshow hung, msmf still ran (and hung)
    assert ck.device_fault(ctx, ctx.cameras[0]) is None              # cleared by the answering probe
    for b in ("dshow", "msmf"):
        rec = res["measurements"]["cameras"][key]["backends"][b]
        assert rec["restore"]["restored"] is True and rec["restore"]["camera_answered_probe"] is True
        assert rec["device_fault"] and res["verdicts"][f"G-CTRL|{key}|opencv_{b}"]["rating"] == "untested"
    assert cam.st["exposure"] == {"value": -7, "flags": 2}


def test_stale_opencv_get_is_its_own_criterion(tmp_path, monkeypatch):
    """Smoke 2026-11-09: MSMF get() returned -6.0 for every exposure set while the camera held -9 / -7 / -4 and
    the image changed. The set counts; 'OpenCV get() reflects the camera' caps the cell at partial."""
    cam = _fast_cam()
    cv = FakeCV2(cam, ae_map={0.25: "manual", 0.75: "auto"}, af_map={0.0: "manual", 1.0: "auto"})
    cv.stale_exposure_get = -6.0
    _install(monkeypatch, cam, cv)
    ctx = OcvCtx(tmp_path, cam, cv)
    res = wo.run(ctx)
    key = ctx.cameras[0]["key"]
    v = res["verdicts"][f"G-CTRL|{key}|opencv_msmf"]
    crit = {c["criterion"]: c["met"] for c in v["criteria"]}
    assert v["rating"] == "partial", v.get("note")
    assert crit["set + readback agree"] is True
    assert crit["OpenCV get() reflects the camera (else read through DirectShow / MF)"] is False
    rows = {r["name"]: r for r in v["evidence"]["controls"]}
    assert rows["exposure"]["opencv_get_reflects_camera"] is False and rows["focus"]["opencv_get_reflects_camera"]
    assert "read it through DirectShow / MF" in rows["exposure"]["workaround"]
    assert res["measurements"]["cameras"][key]["backends"]["msmf"]["conventions"]["exposure_get_equals_camera"] is False


def test_msmf_format_sets_are_bounded_by_the_open_timeout(tmp_path, monkeypatch):
    """Smoke 2026-11-09: the three MSMF format sets took > 30 s on the C930e / C922 (the reader is rebuilt per
    set); they are bounded by --open-timeout-ms (DSHOW keeps max(T, 30 s)) and each set is timed."""
    cam = _fast_cam()
    cv = FakeCV2(cam, ae_map={0.25: "manual", 0.75: "auto"}, af_map={0.0: "manual", 1.0: "auto"})
    _install(monkeypatch, cam, cv)
    ctx = OcvCtx(tmp_path, cam, cv)
    ctx.args.ctrl_runs = 1
    wo.run(ctx)
    slug = ck.cam_slug(ctx.cameras[0])
    for b, bound in (("msmf", wo.OPEN_TIMEOUT_S["msmf"]), ("dshow", 30.0)):
        doc = json.loads((tmp_path / "raw" / wo.TEST / slug / f"{b}_r0_after" / "summary.json").read_text("utf-8"))
        assert doc["format_bound_s"] == bound
        want = {"w", "h", "fps"} | ({"fourcc"} if b == "dshow" else set())
        assert set(doc["format"]["per_set_ms"]) == want
        assert all(isinstance(x, float) for x in doc["format"]["per_set_ms"].values())


def test_helper_timeout_budget_covers_msmf_open():
    ctx = TA.FakeCtx.__new__(TA.FakeCtx)
    ctx.wincam = Path("wincam.exe")
    ctx.python = "3.12"
    cam = {"opencv_msmf_index": 2, "mf_symlink": "x", "ds_path": "y"}
    mode = ck.Mode(1280, 720, 30, 1)
    argv, tmo = wo.helper_args(ctx, cam, "msmf", mode, Path("od"), "after", [-9, -7, -4], [0, 60, 125, 190, 250], None)
    assert tmo > 120 + 30 and "--open-timeout-ms" in argv and "120000" in argv
