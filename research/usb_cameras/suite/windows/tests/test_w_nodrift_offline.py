"""W-NODRIFT offline tests (no camera): a fake ctx whose ``camcmd`` answers like wincam (controls --read-only /
--set, formats, capture with --schedule writing frames.jsonl + frames.mjpeg) for a fake camera model. Frame payloads
are fake; the patched ``w_nodrift.frame_metrics`` reads their metrics back (one test decodes a real JPEG when
Pillow and numpy are installed).

    uv run --isolated --python 3.12 --no-project --with pytest pytest suite/windows/tests/test_w_nodrift_offline.py \
        -c suite/common/tests/pytest.ini
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
WIN = HERE.parent
for p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import w_nodrift as wn  # noqa: E402

REAL_FRAME_METRICS = wn.frame_metrics     # before the autouse fixture patches it

CC = {"exposure", "focus", "zoom", "pan", "tilt", "auto_exposure_priority"}


def _c(value, flags, caps, lo, hi, step, default):
    return {"value": value, "flags": flags, "caps": caps, "min": lo, "max": hi, "step": step, "default": default}


def c930e_like():
    """As found: AE on (-6), gain 5 manual, AF on (30), AWB on (4600 K), AE priority 1 (range 0..0), 50 Hz."""
    return {"exposure": _c(-6, 1, ["auto", "manual"], -11, -2, 1, -5),
            "gain": _c(5, 2, ["manual"], 0, 255, 1, 0),
            "focus": _c(30, 1, ["auto", "manual"], 0, 255, 5, 0),
            "white_balance": _c(4600, 1, ["auto", "manual"], 2000, 7500, 1, 4000),
            "auto_exposure_priority": _c(1, 0, [], 0, 0, 0, 0),
            "powerline_frequency": _c(1, 0, [], 1, 2, 1, 2),
            "zoom": _c(100, 2, ["manual"], 100, 400, 1, 100),
            "brightness": _c(140, 2, ["manual"], 0, 255, 1, 128),
            "backlight_compensation": _c(1, 2, ["manual"], 0, 1, 1, 0)}


def generic_like():
    """No focus, power-line range 0..0, WB manual only, gain 1..7."""
    return {"exposure": _c(-7, 1, ["auto", "manual"], -7, 3, 1, -7),
            "gain": _c(4, 2, ["manual"], 1, 7, 1, 4),
            "white_balance": _c(4500, 2, ["manual"], 0, 6500, 1, 4500),
            "powerline_frequency": _c(0, 0, [], 0, 0, 0, 0),
            "gamma": _c(22, 2, ["manual"], 10, 30, 10, 20)}


class FakeCam:
    """Image model: luma = 100 * 2**(exposure + 6) * (1 + gain / 255); R = luma * WB / 5000, B = luma * 5000 / WB;
    sharpness 0.01 within 5 of focus 30, else 0.004. ``resets_at_start``: {control: value} applied at every stream
    start (the C930e resets exposure and gain). ``drift``: [(ms after first frame of the soak, control, value,
    flags)]. ``fail_capture``: segment name -> wincam error dict."""

    def __init__(self, key, name, vid, pid, controls, resets_at_start=None, drift=(), drop_frames=(),
                 fail_capture=None, is_kiyo=False, reject=()):
        self.key, self.name = key, name
        self.dev = f"\\\\?\\usb#vid_{vid}&pid_{pid}#{key[-4:]}#{{mf}}"
        self.cam = {"key": key, "name": name, "vid": vid, "pid": pid, "serial": key[-4:], "is_kiyo": is_kiyo,
                    "mf_symlink": self.dev, "ds_path": self.dev.replace("{mf}", "{ds}"), "metadata_tier1": False}
        self.st = controls
        self.as_found = json.loads(json.dumps(controls))
        self.resets = resets_at_start or {}
        self.drift = list(drift)
        self.drop_frames = set(drop_frames)
        self.fail_capture = fail_capture or {}
        self.reject = set(reject)               # controls whose integer sets the camera ignores

    # ---- controls
    def table(self):
        out = []
        for n, c in self.st.items():
            out.append({"name": n, "supported": True, "get_ok": True, "value": c["value"], "flags": c["flags"],
                        "flags_names": wn._fnames(c["flags"]), "caps_flags_names": c["caps"], "min": c["min"],
                        "max": c["max"], "step": c["step"], "default": c["default"]})
        return {"controls": out, "device_not_answering": False, "sets": []}

    def apply(self, n, raw, set_flags="manual"):
        c = self.st[n]
        before = dict(c)
        if raw == "auto":
            c["flags"] = 1
        elif raw == "manual":
            c["flags"] = 2 if "manual" in c["caps"] else c["flags"]
        elif n not in self.reject:
            c["value"] = int(raw)
            c["flags"] = 1 if set_flags == "auto" else (2 if "manual" in c["caps"] else 0)
        want_auto = raw == "auto" or (set_flags == "auto" and raw != "manual")
        m = bool(c["flags"] & 1) if want_auto else (c["value"] == (before["value"] if raw == "manual" else int(raw))
                                                    and bool(c["flags"] & 2))
        return {"control": ("cc." if n in CC else "pa.") + n, "requested": str(raw), "before_value": before["value"],
                "before_flags": before["flags"], "set_value": c["value"], "readback_value": c["value"],
                "readback_flags": c["flags"], "readback_flags_names": wn._fnames(c["flags"]), "matches": m,
                "hr_set_name": "S_OK", "timed_out": False}

    def image(self):
        e = self.st["exposure"]["value"]
        g = self.st.get("gain", {"value": 0})["value"]
        wb = self.st.get("white_balance", {"value": 5000})["value"] or 5000
        luma = min(250.0, 100.0 * 2 ** (e + 6) * (1 + g / 255.0))
        f = self.st.get("focus", {"value": 30})["value"]
        return luma, luma * wb / 5000.0, luma, luma * 5000.0 / wb, (0.01 if abs(f - 30) <= 5 else 0.004)


CLOCK = {"t": 10_000_000_000}


def _arg(a, flag, default=None):
    return a[a.index(flag) + 1] if flag in a else default


class FakeCtx:
    """SuiteCtx stand-in: camcmd emulates wincam; gate methods like suitectx (camera_gated / camera_faulted /
    mark_fault / clear_fault) plus camera_dead."""

    def __init__(self, tmp: Path, cams: list, quick=True, **args):
        self.out_dir, self.raw_dir = tmp / "out", tmp / "raw"
        self.out_dir.mkdir(parents=True)
        self.args = SimpleNamespace(**{"quick": quick, "min_fps": 30.0, "min_height": 720, "max_height": 720,
                                       "all_modes": False, "nodrift_soak_s": None, "nodrift_restarts": None, **args})
        self.fcams = cams
        self.cameras = [c.cam for c in cams]
        self.wincam = Path("wincam.exe")
        self.logs, self.calls = [], []
        self.gated, self.dead, self.faults = {}, {}, {}
        self.dead_after = {}          # key -> segment label after whose capture the camera is declared dead

    def log(self, m):
        self.logs.append(m)

    def test_dir(self, name):
        d = self.out_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def raw_test_dir(self, name):
        d = self.raw_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def arrivals(self):
        raise RuntimeError("no PnP offline")

    # ---- gate
    def camera_gated(self, cam):
        return self.gated.get(cam["key"] if isinstance(cam, dict) else cam)

    def camera_dead(self, cam):
        return self.dead.get(cam["key"] if isinstance(cam, dict) else cam)

    def camera_faulted(self, key):
        r = self.faults.get(key)
        return dict(r) if r and r.get("faulted") else None

    def mark_fault(self, key, **kw):
        self.faults.setdefault(key, {"faulted": True, "since_utc": "2026-11-11T23:00:00Z", **kw})
        return dict(self.faults[key])

    def clear_fault(self, key, **kw):
        self.faults.pop(key, None)

    # ---- wincam emulation
    def _cam_for(self, a):
        dev = _arg(a, "--device")
        return next(c for c in self.fcams if c.dev == dev)

    def camcmd(self, argv, timeout_s, **k):
        a = [str(x) for x in argv]
        fc = self._cam_for(a)
        self.calls.append((fc.key, a[1], _arg(a, "--out-dir"), _arg(a, "--schedule")))
        CLOCK["t"] += 300_000_000
        if a[1] == "formats":
            out = {"reader_streams": [{"types": [{"subtype": "MJPG", "width": w, "height": h, "fps_num": f,
                                                  "fps_den": 1} for w, h, f in ((640, 480, 30), (1280, 720, 30),
                                                                                (1280, 720, 60), (1920, 1080, 30))]}]}
        elif a[1] == "controls" and "--read-only" in a:
            out = fc.table()
        elif a[1] == "controls":
            out = fc.table()
            fl = _arg(a, "--set-flags", "manual")
            out["sets"] = [fc.apply(n, v, fl) for n, v in (x.split("=") for x in _arg(a, "--set").split(","))]
        elif a[1] == "capture":
            out = self._capture(fc, a)
        else:
            raise AssertionError(a)
        return {"rc": 0, "stdout": json.dumps(out), "stderr": "", "elapsed_s": 0.3, "timed_out": False}

    def _capture(self, fc: FakeCam, a):
        od = Path(_arg(a, "--out-dir"))
        seg = od.name
        od.mkdir(parents=True, exist_ok=True)
        if seg in fc.fail_capture:
            (od / "frames.jsonl").write_text("", encoding="utf-8")
            return {"ok": False, "frames": {"total": 0}, "error": fc.fail_capture[seg], "schedule": []}
        secs = float(_arg(a, "--seconds"))
        every = int(_arg(a, "--save").split(":")[1])
        t_first = CLOCK["t"] + 500_000_000
        for n, v in fc.resets.items():          # stream start (C930e: exposure and gain reset)
            fc.st[n]["value"] = v
        todo = []
        for item in (_arg(a, "--schedule") or "").split(";"):
            if item:
                at, kv = item.split(":")
                n, v = kv.split("=")
                todo.append((float(at), "sched", n, v, item))
        if seg == "soak":
            todo += [(float(at), "drift", n, (v, f), None) for at, n, v, f in fc.drift]
        todo.sort(key=lambda x: x[0])
        sched, ti = [], 0
        with (od / "frames.mjpeg").open("wb") as fm, (od / "frames.jsonl").open("w", encoding="utf-8") as fj:
            seq = 0
            for i in range(int(secs * 30)):
                t = t_first + int(i * 33_333_333)
                while ti < len(todo) and t_first + todo[ti][0] * 1e6 <= t:
                    at, kind, n, v, item = todo[ti]
                    ti += 1
                    if kind == "drift":
                        fc.st[n]["value"], fc.st[n]["flags"] = v
                        continue
                    ta = t_first + int(at * 1e6)
                    sched.append({**fc.apply(n, v), "at_ms": at, "item": item, "applied_qpc_ns": ta,
                                  "done_qpc_ns": ta + 8_000_000})
                if seg == "soak" and i in fc.drop_frames:
                    continue
                row = {"seq": seq, "qpc_ns": t, "sample_time_100ns": (t - t_first) // 100}
                seq += 1
                if i % every == 0:
                    luma, r, g, b, s = fc.image()
                    payload = f"FAKE l={luma:.4f};r={r:.4f};g={g:.4f};b={b:.4f};s={s:.6f}".encode()
                    row["mjpeg_offset"], row["mjpeg_len"] = fm.tell(), len(payload)
                    fm.write(payload)
                fj.write(json.dumps(row) + "\n")
        CLOCK["t"] = t_first + int(secs * 1e9)
        if self.dead_after.get(fc.key) == seg:
            self.dead[fc.key] = {"dead": True, "utc": "2026-11-11T23:30:00Z", "reason": "wedged"}
        return {"ok": True, "frames": {"total": seq, "discontinuities": 0, "null_samples": 0}, "fps_measured": 30.0,
                "schedule": sched, "controls_before": [], "error": None}


def _fake_metrics(data, w, h):
    m = re.match(rb"FAKE l=([\d.]+);r=([\d.]+);g=([\d.]+);b=([\d.]+);s=([\d.]+)", data)
    luma, r, g, b, s = (float(x) for x in m.groups())
    return {"luma_median": luma, "luma_mean": luma, "r": r, "g": g, "b": b, "rb_ratio": r / b, "sharpness": s}


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(wn, "frame_metrics", _fake_metrics)
    monkeypatch.setattr(wn, "_sleep", lambda s: None)


def _c930e(**kw):
    return FakeCam("046d:0843:sn=AAAA", "Logitech Webcam C930e", "046d", "0843", c930e_like(),
                   resets_at_start={"exposure": -5, "gain": 0}, **kw)


def _kiyo(**kw):
    return FakeCam("1532:0e05:sn=KKKK", "USB Video Device", "1532", "0e05", c930e_like(), is_kiyo=True, **kw)


def _no_bare_kiyo(texts):
    for t in texts:
        assert not re.search(r"Kiyo(?! Pro)", t), t


# ------------------------------------------------------------------------------------------------ pure parts
def test_timeline_and_estimate():
    assert wn.soak_sample_ms(600) == [3000 + 30000 * k for k in range(21)]
    assert wn.soak_sample_ms(60) == [3000, 33000, 63000]
    assert wn.restart_sample_ms() == [3000, 8000, 13000, 18000]
    assert wn.REAPPLY_MS >= 1000 and wn.REAPPLY_MS < wn.FIRST_SAMPLE_MS
    full = SimpleNamespace(args=SimpleNamespace(quick=False), cameras=[{}])
    quick = SimpleNamespace(args=SimpleNamespace(quick=True), cameras=[{}, {}])
    assert 11 * 60 <= wn.estimate_s(full) <= 13 * 60          # ~12 min per camera
    assert wn.estimate_s(quick) < 2 * 3 * 60
    assert wn.n_restarts(full) == 3 and wn.n_restarts(quick) == 1 and wn.soak_s(quick) == 60
    assert wn.kiyo_stream_starts(full) == 4


def test_plan_lock_targets_and_skips():
    tab = {n: {"name": n, "supported": True, "get_ok": True, "value": c["value"], "flags": c["flags"],
               "flags_names": wn._fnames(c["flags"]), "caps_flags_names": c["caps"], "min": c["min"],
               "max": c["max"], "step": c["step"]} for n, c in c930e_like().items()}
    lock, skipped = wn.plan_lock(tab)
    assert lock["exposure"]["requested"] == -6 and lock["exposure"]["group"] == "auto_off"
    assert lock["white_balance"]["requested"] == 4600            # AWB off holding its current value
    assert lock["auto_exposure_priority"]["requested"] == 0 and lock["auto_exposure_priority"]["tolerance"] == 0
    assert lock["powerline_frequency"]["requested"] == 2
    assert lock["zoom"]["group"] == "start_value" and lock["brightness"]["requested"] == 140
    assert skipped["pan"] == "n/a: not supported"
    g = {n: {"name": n, "supported": True, "get_ok": True, "value": c["value"], "flags": c["flags"],
             "flags_names": wn._fnames(c["flags"]), "caps_flags_names": c["caps"], "min": c["min"], "max": c["max"],
             "step": c["step"]} for n, c in generic_like().items()}
    lock2, skipped2 = wn.plan_lock(g)
    assert "powerline_frequency" not in lock2 and "outside the range 0..0" in skipped2["powerline_frequency"]
    assert skipped2["focus"] == "n/a: not supported" and lock2["gamma"]["tolerance"] == 10


def test_frame_metrics_on_a_real_jpeg():
    pytest.importorskip("numpy")
    PIL = pytest.importorskip("PIL.Image")
    import io
    img = PIL.new("RGB", (1280, 720), (200, 100, 50))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    m = REAL_FRAME_METRICS(buf.getvalue(), 1280, 720)
    assert abs(m["r"] - 200) < 4 and abs(m["b"] - 50) < 4 and abs(m["rb_ratio"] - 4.0) < 0.3
    assert abs(m["luma_median"] - (0.299 * 200 + 0.587 * 100 + 0.114 * 50)) < 3
    assert m["sharpness"] < 1e-3
    assert REAL_FRAME_METRICS(b"not a jpeg", 1280, 720) is None


# ------------------------------------------------------------------------------------------------ end to end
def test_pass_path_reapply_restore(tmp_path):
    cam = _c930e(drop_frames=range(100, 105))
    ctx = FakeCtx(tmp_path, [cam], quick=False, nodrift_soak_s=90, nodrift_restarts=3)
    res = wn.run(ctx)
    key = cam.key
    v = res["verdicts"][f"G-CTRL-NODRIFT|{key}|mf"]
    m = res["measurements"]["cameras"][key]
    # AE priority 1 -> 0 is accepted by this fake; everything holds -> yes
    assert v["rating"] == "yes", (v.get("note"), [c for c in v["criteria"] if c["met"] is not True])
    assert m["mode"] == "MJPG 1280x720@30"
    assert [s["label"] for s in m["segments"]] == ["soak", "restart1", "restart2", "restart3"]
    assert len(m["segments"][0]["samples"]) == 4 and len(m["segments"][1]["samples"]) == 4
    # lock: requested vs read back, AWB held at its start value, 60 Hz, AE priority 0
    lr = m["lock_result"]["controls"]
    assert lr["white_balance"]["readback_value"] == 4600 and lr["white_balance"]["readback_flags_names"] == ["manual"]
    assert lr["powerline_frequency"]["readback_value"] == 2 and lr["auto_exposure_priority"]["readback_value"] == 0
    assert all(x["ok"] for x in lr.values())
    # C930e: exposure and gain reset at every stream start, re-applied 1.2 s after the first frame
    assert all(sorted(s["needed_reapply"]) == ["exposure", "gain"] for s in m["segments"])
    assert m["segments"][0]["reapply"]["exposure"]["before_value"] == -5
    assert m["segments"][0]["reapply"]["exposure"]["readback_value"] == -6
    # samples read exposure / gain / focus / WB with flags; image metrics and stream stats recorded
    s0 = m["segments"][0]["samples"][0]
    assert set(s0["controls"]) == {"exposure", "gain", "focus", "white_balance"}
    assert s0["controls"]["exposure"]["auto"] is False and s0["image"]["n"] >= 3
    st = m["segments"][0]["stream"]
    assert st["drop_events"] == 1 and st["est_dropped_frames"] == 5 and abs(st["fps_measured"] - 30.0) < 0.2
    wd = v["evidence"]["worst_deviations"]
    assert wd["luma"]["max_rel_dev"] == 0 and wd["controls"]["exposure"]["max_abs_dev"] == 0
    # restore: every touched control back to its as-found value and flag (AE / AF / AWB on again)
    assert m["restore"]["restored"] is True and v["restore"] is True
    for n, c in cam.as_found.items():
        assert (cam.st[n]["value"], cam.st[n]["flags"]) == (c["value"], c["flags"]), n
    # raw frames under raw_test_dir, nothing in the results folder
    assert (tmp_path / "raw" / "W-NODRIFT").is_dir() and not list((tmp_path / "out").rglob("*.mjpeg"))
    # re-rating the stored result gives the same rating
    assert wn.rerate(json.loads(json.dumps(res, default=str)))["changes"] == []


def test_drift_fail_auto_flag_and_luma(tmp_path):
    # 40 s into the soak the camera switches AE back on and AE picks -5 (twice the light)
    cam = _c930e(drift=[(40000, "exposure", -5, 1)])
    ctx = FakeCtx(tmp_path, [cam], quick=True)
    res = wn.run(ctx)
    v = res["verdicts"][f"G-CTRL-NODRIFT|{cam.key}|mf"]
    assert v["rating"] == "no" and v["summary_label"] == "no (drift)"
    crit = {c["criterion"][:20]: c["met"] for c in v["criteria"]}
    assert crit["auto flags stay off "] is False and crit["exposure, gain, focu"] is True   # -5 is within one step
    assert "auto flag came back on (exposure)" in v["note"] and "luma left" in v["note"]
    ev = res["measurements"]["cameras"][cam.key]["evaluation"]
    assert ev["auto_flag_events"][0]["at"].startswith("soak sample 2")
    assert ev["worst_deviations"]["luma"]["max_rel_dev"] > 0.9
    # the restart re-applies the lock, so the camera holds again there; the restore still ran
    assert res["measurements"]["cameras"][cam.key]["restore"]["restored"] is True


def test_drift_fail_white_balance_value(tmp_path):
    cam = _c930e(drift=[(20000, "white_balance", 4900, 2)])        # manual flag kept, value moved 300 K
    res = wn.run(FakeCtx(tmp_path, [cam], quick=True))
    v = res["verdicts"][f"G-CTRL-NODRIFT|{cam.key}|mf"]
    assert v["rating"] == "no"
    assert "readback left its tolerance (white_balance)" in v["note"] and "R/B left" in v["note"]
    assert v["evidence"]["worst_deviations"]["controls"]["white_balance"]["max_abs_dev"] == 300


def test_gated_at_start_and_dead_mid_test_send_no_further_commands(tmp_path):
    kiyo, c930 = _kiyo(), _c930e()
    gen = FakeCam("4c4a:4a55:port=1/2", "USB Camera", "4c4a", "4a55", generic_like())
    ctx = FakeCtx(tmp_path, [kiyo, c930, gen], quick=False, nodrift_soak_s=60, nodrift_restarts=3)
    ctx.dead_after[kiyo.key] = "soak"                                    # the Kiyo Pro dies during the soak
    ctx.gated[gen.key] = {"since_utc": "2026-11-11T20:00:00Z", "code": "0x8007001F"}
    res = wn.run(ctx)
    v = res["verdicts"]
    # the Kiyo Pro: soak captured, then nothing: no restart, no restore
    kc = [c for c in ctx.calls if c[0] == kiyo.key]
    assert kc[-1][1] == "capture" and kc[-1][2].endswith("soak")
    assert sum(1 for c in kc if c[1] == "capture") == 1
    kv = v[f"G-CTRL-NODRIFT|{kiyo.key}|mf"]
    assert kv["rating"] == "untested" and kv["summary_label"] == "untested (device fault/dead)"
    assert "Kiyo Pro" in kv["note"] and "camera_dead" in kv["note"] and "restart1" in kv["note"]
    km = res["measurements"]["cameras"][kiyo.key]
    assert km["restore"]["restored"] is None and "skipped" in km["restore"] and kv["restore"] is None
    # the gated camera: no command at all
    assert not [c for c in ctx.calls if c[0] == gen.key]
    gv = v[f"G-CTRL-NODRIFT|{gen.key}|mf"]
    assert gv["rating"] == "untested" and "camera_gated" in gv["note"]
    # the C930e still ran in full after the dead Kiyo Pro
    cv = v[f"G-CTRL-NODRIFT|{c930.key}|mf"]
    assert cv["rating"] == "yes" and cv["restore"] is True
    _no_bare_kiyo(ctx.logs + [json.dumps(x.get("note")) for x in v.values()])


def test_device_error_capture_marks_fault_and_stops(tmp_path):
    cam = _c930e(fail_capture={"restart1": {"class": "device_error", "hr": "0x8007001F", "stage": "first_sample"}})
    ctx = FakeCtx(tmp_path, [cam], quick=False, nodrift_soak_s=60, nodrift_restarts=3)
    res = wn.run(ctx)
    v = res["verdicts"][f"G-CTRL-NODRIFT|{cam.key}|mf"]
    assert v["rating"] == "untested" and ctx.faults[cam.key]["faulted"]
    caps = [c for c in ctx.calls if c[1] == "capture"]
    assert [Path(c[2]).name for c in caps] == ["soak", "restart1"]
    assert ctx.calls[-1][1] == "capture"                                 # no restore after the fault
    assert res["measurements"]["cameras"][cam.key]["halted"]["by"] == "capture_fault"


def test_kiyo_pro_failed_capture_gets_no_restore(tmp_path):
    kiyo = _kiyo(fail_capture={"soak": {"class": "timeout", "stage": "first_sample"}})
    ctx = FakeCtx(tmp_path, [kiyo], quick=True)
    res = wn.run(ctx)
    v = res["verdicts"][f"G-CTRL-NODRIFT|{kiyo.key}|mf"]
    assert v["summary_label"] == "untested (capture failed)" and "Kiyo Pro" in v["note"]
    assert ctx.calls[-1][1] == "capture"
    assert "Kiyo Pro" in res["measurements"]["cameras"][kiyo.key]["restore"]["skipped"]
    _no_bare_kiyo(ctx.logs)


def test_plan_mode_runs_nothing(tmp_path):
    ctx = FakeCtx(tmp_path, [_c930e()])
    ctx.dry_run = True
    res = wn.run(ctx)
    assert not ctx.calls and {x["rating"] for x in res["verdicts"].values()} == {"untested"}


def test_lock_not_read_back_is_partial_and_not_set_in_stream(tmp_path):
    cam = _c930e(reject={"auto_exposure_priority"})                     # AE priority stays 1 (range 0..0)
    ctx = FakeCtx(tmp_path, [cam], quick=True)
    res = wn.run(ctx)
    v = res["verdicts"][f"G-CTRL-NODRIFT|{cam.key}|mf"]
    assert v["rating"] == "partial", v.get("note")
    m = res["measurements"]["cameras"][cam.key]
    assert m["lock_result"]["controls"]["auto_exposure_priority"]["ok"] is False
    assert "excluded" in m["segments"][0]["reapply"]["auto_exposure_priority"]
    sched = [c[3] for c in ctx.calls if c[1] == "capture"]
    assert sched and all("auto_exposure_priority" not in x and "1200:exposure=-6" in x for x in sched)
    assert m["restore"]["restored"] is True
