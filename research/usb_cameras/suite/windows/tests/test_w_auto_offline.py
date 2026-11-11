"""W-AUTO offline tests (no camera): the recovery analysis, the rating, the MF/DS event parsing, the restore, and a
simulated end-to-end run against a fake camera model (capkit's camera calls patched; frames are fake payloads whose
metric the patched ``w_ctrl_effect.metric_value`` reads back).

    uv run --isolated --python 3.12 --no-project --with pytest pytest suite/windows/tests/test_w_auto_offline.py \
        -c suite/common/tests/pytest.ini
"""
from __future__ import annotations

import pytest

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
WIN = HERE.parent
for p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import capkit as ck  # noqa: E402
import w_auto as wa  # noqa: E402
from common import modescope  # noqa: E402


# ------------------------------------------------------------------------------------------------ pure analysis
def _pts(fn, t_end_ms, step=66.7):
    t, out = 0.0, []
    while t <= t_end_ms:
        out.append([round(t, 1), fn(t)])
        t += step
    return out


def test_in_band_and_recovery():
    assert wa.in_band("luma_mean", 110, 100) and not wa.in_band("luma_mean", 120, 100)
    assert wa.in_band("sharpness", 0.009, 0.01) and not wa.in_band("sharpness", 0.007, 0.01)
    assert wa.in_band("sharpness", 0.05, 0.01)          # sharper than the AF baseline is fine
    pts = _pts(lambda t: 10.0 if t < 900 else 100.0, 3000)
    r = wa.recovery_ms(pts, 0, 3000, "luma_mean", 100.0)
    assert 900 <= r <= 1000
    # one in-band frame that does not stay there does not count
    pts = _pts(lambda t: 100.0 if 500 <= t < 560 else 10.0, 3000)
    assert wa.recovery_ms(pts, 0, 3000, "luma_mean", 100.0) is None


def test_baseline_scene_flags():
    assert wa.baseline_from(_pts(lambda t: 100.0, 5000), "luma_mean")["conclusive"]
    dark = wa.baseline_from(_pts(lambda t: 12.0, 5000), "luma_mean")
    assert not dark["conclusive"] and "dark" in dark["reason"]
    low = wa.baseline_from(_pts(lambda t: 1e-4, 5000), "sharpness")
    assert not low["conclusive"] and "low-texture" in low["reason"]
    unstable = wa.baseline_from(_pts(lambda t: 60.0 if int(t / 66.7) % 2 else 140.0, 5000), "luma_mean")
    assert not unstable["conclusive"] and "unstable" in unstable["reason"]


def test_plan_timeline_and_extremes():
    p = wa.plan("exposure", [-11, -2, -11], 3)
    assert p["toggles"][0]["manual_ms"] == 4500 >= 1000          # C930e rule: >= 1 s after the first frame
    assert [t["value"] for t in p["toggles"]] == [-11, -2, -11]
    assert p["toggles"][1]["manual_ms"] - p["toggles"][0]["auto_ms"] == wa.RECOVER_MS["exposure"] + wa.MARGIN_MS
    before, sched = wa.mf_schedule("exposure", p)
    assert before == "exposure=-11,exposure=auto"
    assert sched.split(";")[:2] == ["4500:exposure=-11", "6500:exposure=auto"]
    c = {"min": 0, "max": 250}
    assert wa.extremes("focus", c, af_pos=0)[0] == [250]          # C922: focus 0 was the sharpest position
    assert wa.extremes("focus", c, af_pos=240)[0] == [0]
    assert wa.extremes("focus", c, af_pos=None)[0] == [0]         # unknown: "focus 0"
    # exposure: the bright extreme must fit the frame interval (log2 seconds), not the range max (-2 = 250 ms)
    e = {"min": -11, "max": -2, "step": 1}
    assert wa.extremes("exposure", e, fps=30.0)[0] == [-11, -5, -11]   # 2**-5 = 31.3 ms <= 33.3 ms < 2**-4
    assert wa.extremes("exposure", e, fps=60.0)[0] == [-11, -6, -11]   # 2**-6 = 15.6 ms <= 16.7 ms
    assert wa.extremes("exposure", e, fps=15.0)[0] == [-11, -4, -11]
    assert wa.extremes("exposure", {"min": 1, "max": 10001, "step": 1}, fps=30.0)[0][1] == 7501   # not log2: 75 %


def test_exposure_extremes_leave_the_ae_value():
    """Gerald 2026-11-06 AE values (W-CTRL-LIST): a fixed extreme equal to AE's own value cannot leave the band."""
    e = {"min": -11, "max": -2, "step": 1}
    assert wa.extremes("exposure", e, fps=30.0, ae_value=-8)[0] == [-10, -6, -10]   # room on both sides
    assert wa.extremes("exposure", e, fps=30.0, ae_value=-5)[0] == [-7, -8, -7]     # C930e: AE = the 30 fps cap
    assert wa.extremes("exposure", e, fps=30.0, ae_value=-4)[0] == [-6, -7, -6]     # C922 / Kiyo: AE above the cap
    g = {"min": -7, "max": 3, "step": 1}
    assert wa.extremes("exposure", g, fps=30.0, ae_value=-7)[0] == [-5, -6, -5]     # generic: AE = the range min
    assert wa.extremes("exposure", {"min": -7, "max": -5, "step": 1}, fps=30.0, ae_value=-6)[0] == [-7, -5, -7]
    for ae, rng in ((-5, e), (-4, e), (-7, g), (-8, e)):
        vals = wa.extremes("exposure", rng, fps=30.0, ae_value=ae)[0]
        assert all(abs(v - ae) >= 1 for v in vals) and all(v <= -5 for v in vals)   # never AE, never past 1/fps
    # unknown AE value or a range that is not log2 seconds: the fixed-point fallback
    assert wa.extremes("exposure", e, fps=30.0, ae_value=None)[0] == [-11, -5, -11]
    assert wa.extremes("exposure", {"min": 1, "max": 10001, "step": 1}, fps=30.0, ae_value=500)[0][1] == 7501


def _cap(points, events, name="exposure", n=1, vals=(-11,)):
    p = wa.plan(name, list(vals), n)
    return {"control": name, "points": points, "events": events, "plan": p}


def _ev(k, kind, t, end=None, matches=True):
    return {"k": k, "kind": kind, "t_ms": t, "t_end_ms": end if end is not None else t + 5, "matches": matches}


def test_analyse_transitions_pass_fail_inconclusive():
    base = wa.baseline_from(_pts(lambda t: 100.0, 5000), "luma_mean")
    p = wa.plan("exposure", [-11, -2, -11], 3)
    tg = p["toggles"]

    def luma(t):
        if t < 600:
            return 20.0                                   # before start: auto converges within 600 ms
        if tg[0]["manual_ms"] <= t < tg[0]["auto_ms"] + 800:
            return 5.0                                    # toggle 0: dark, back after 800 ms
        if tg[1]["manual_ms"] <= t:
            if t < tg[2]["manual_ms"]:
                return 240.0                              # toggle 1: bright and never back (flag only)
            return 240.0
        return 100.0
    pts = _pts(luma, p["end_ms"])
    evs = []
    for t in tg:
        evs += [_ev(t["k"], "manual", t["manual_ms"]), _ev(t["k"], "auto", t["auto_ms"])]
    out = wa.analyse_transitions({"control": "exposure", "points": pts, "events": evs, "plan": p}, base)
    assert out["before_start"]["result"] == "pass" and out["before_start"]["recovery_ms"] <= 700
    r = [t["result"] for t in out["toggles"]]
    assert r[0] == "pass" and 750 <= out["toggles"][0]["recovery_ms"] <= 900
    assert r[1] == "fail" and out["toggles"][1].get("flag_only")
    assert r[2] == "fail"            # still 240 when the third (dark) extreme is set: the image never moved
    # the manual extreme did not move the image: inconclusive
    pts2 = _pts(lambda t: 100.0, p["end_ms"])
    out2 = wa.analyse_transitions({"control": "exposure", "points": pts2, "events": evs, "plan": p}, base)
    assert {t["result"] for t in out2["toggles"]} == {"inconclusive"}
    # dark scene: inconclusive with the reason
    dark = wa.baseline_from(_pts(lambda t: 10.0, 5000), "luma_mean")
    out3 = wa.analyse_transitions({"control": "exposure", "points": pts, "events": evs, "plan": p}, dark)
    assert out3["before_start"]["result"] == "inconclusive" and "dark" in out3["before_start"]["reason"]
    # a missing event (set timed out) is unmeasured
    out4 = wa.analyse_transitions({"control": "exposure", "points": pts, "events": evs[:1], "plan": p}, base)
    assert out4["toggles"][0]["result"] == "unmeasured"


def test_toggle_reference_is_the_pre_set_window_of_the_same_capture():
    """Smoke 2026-11-09, C922 ds-af: AF settled at 0.0148 in the baseline capture but at 0.0116 in the transitions
    capture, before the manual set and again ~550 ms after auto ON. Judged against its own pre-set window the
    recovery passes; the recovery against the path baseline stays recorded."""
    base = wa.baseline_from(_pts(lambda t: 0.01476, 5000), "sharpness")
    p = wa.plan("focus", [250], 1)
    tg = p["toggles"][0]

    def sharp(t):
        if tg["manual_ms"] <= t < tg["auto_ms"] + 550:
            return 0.00015
        return 0.0116
    pts = _pts(sharp, p["end_ms"])
    evs = [_ev(0, "manual", tg["manual_ms"]), _ev(0, "auto", tg["auto_ms"])]
    cap = {"control": "focus", "points": pts, "events": evs, "plan": p}
    out = wa.analyse_transitions(cap, base)
    t0 = out["toggles"][0]
    assert t0["result"] == "pass" and t0["reference"]["source"].startswith("pre-set window")
    assert t0["reference"]["path_baseline"] == pytest.approx(0.01476)
    assert t0["vs_path_baseline"]["recovered"] is False          # 0.0116 / 0.01476 = 0.79 < 0.8
    # the old behaviour (path baseline only) is what W-OCV-CTRL asks for: a 'fail' here
    assert wa.analyse_transitions(cap, base, pre_ref=False)["toggles"][0]["result"] == "fail"
    # a pre-set window that does not look like auto (a manual extreme) is not used as the reference
    pts2 = _pts(lambda t: 0.00015 if t >= tg["manual_ms"] - 2000 and t < tg["auto_ms"] + 550 else 0.0146,
                p["end_ms"])
    t2 = wa.analyse_transitions({**cap, "points": pts2}, base)["toggles"][0]
    assert t2["reference"]["source"] == "path baseline" and t2["pre_set_window"]["used"] is False


def test_pre_set_window_after_a_failed_toggle_is_not_used():
    base = wa.baseline_from(_pts(lambda t: 100.0, 5000), "luma_mean")
    p = wa.plan("exposure", [-11, -11], 2)
    tg = p["toggles"]

    def luma(t):
        if t >= tg[0]["manual_ms"]:
            return 75.0 if t < tg[1]["manual_ms"] else (20.0 if t < tg[1]["auto_ms"] else 75.0)
        return 100.0
    pts = _pts(luma, p["end_ms"])
    evs = []
    for t in tg:
        evs += [_ev(t["k"], "manual", t["manual_ms"]), _ev(t["k"], "auto", t["auto_ms"])]
    out = wa.analyse_transitions({"control": "exposure", "points": pts, "events": evs, "plan": p}, base)
    assert out["toggles"][0]["result"] == "fail"                 # 75 is outside +/-15 % of 100 and never recovers
    t1 = out["toggles"][1]
    assert t1["pre_set_window"]["used"] is False and "previous toggle" in t1["pre_set_window"]["reason"]
    assert t1["result"] == "fail"                                # judged against the path baseline


def _run(bs="pass", toggles=("pass",), rb=True):
    return {"analysis": {"before_start": {"result": bs, "recovery_ms": 300},
                         "toggles": [{"result": x, "auto_readback_ok": rb, "recovery_ms": 500,
                                      "flag_only": x == "fail" and rb, "reason": "r" if x != "pass" else None}
                                     for x in toggles]},
            "before_start_readback": {"auto_readback_ok": rb}}


def test_rate_auto_cases():
    yes = wa.rate_auto("exposure", {"runs": [_run(toggles=("pass",) * 3)] * 3}, 3, 3)
    assert yes["rating"] == "yes"
    some = wa.rate_auto("exposure", {"runs": [_run(toggles=("pass", "inconclusive", "pass"))] * 3}, 3, 3)
    assert some["rating"] == "partial"
    flag = wa.rate_auto("focus", {"runs": [_run(toggles=("pass", "fail", "pass"))] * 3}, 3, 3)
    assert flag["rating"] == "no" and flag["summary_label"] == "no (flag only)"
    bsf = wa.rate_auto("exposure", {"runs": [_run(bs="fail", toggles=("pass",) * 3)] * 3}, 3, 3)
    assert bsf["rating"] == "partial" and "after the stream has started" in bsf["workaround"]
    inc = wa.rate_auto("focus", {"runs": [_run(bs="inconclusive", toggles=("inconclusive",) * 3)] * 3}, 3, 3)
    assert inc["rating"] == "untested" and inc["summary_label"] == "untested (inconclusive)"
    na = wa.rate_auto("focus", {"na": "n/a: the camera has no focus control"}, 3, 3)
    assert na["rating"] == "untested" and na["summary_label"] == "untested (n/a)"
    dna = wa.rate_auto("exposure", {"device_not_answering": {"hr": "0x8007001F"}}, 3, 3)
    assert dna["rating"] == "no" and dna["summary_label"] == "no (device not answering)"
    # OpenCV variant: no before-start transition planned
    ocv = wa.rate_auto("exposure", {"runs": [{"analysis": {"before_start": {"result": "fail"},
                                                           "toggles": [{"result": "pass", "auto_readback_ok": True}]}}]},
                       1, 1, with_before_start=False)
    assert ocv["rating"] == "yes"
    assert not any("before the stream starts" in c["criterion"] for c in ocv["criteria"])


def test_mf_and_ds_event_parsing():
    p = wa.plan("focus", [250], 1)
    t0 = 1_000_000_000
    summ = {"controls_before": [{"control": "cc.focus", "requested": "250", "matches": True},
                                {"control": "cc.focus", "requested": "auto", "matches": True, "readback_flags": 1}],
            "schedule": [{"control": "cc.focus", "at_ms": 6500.0, "applied_qpc_ns": t0 + 6_501_000_000,
                          "done_qpc_ns": t0 + 6_520_000_000, "matches": True, "readback_flags": 2},
                         {"control": "cc.focus", "at_ms": 9000.0, "applied_qpc_ns": t0 + 9_001_000_000,
                          "done_qpc_ns": t0 + 9_010_000_000, "matches": True, "readback_flags": 1}]}
    evs, bsr = wa.mf_events(summ, p, t0)
    assert [(e["kind"], e["t_ms"]) for e in evs] == [("manual", 6501.0), ("auto", 9001.0)]
    assert bsr["auto_readback_ok"] is True
    launch = {"commands": [{"label": "manual0", "t_start_ns": t0 + 6_400_000_000, "t_end_ns": t0 + 6_700_000_000,
                            "rc": 0, "stdout": json.dumps({"sets": [{"control": "cc.focus", "matches": True,
                                                                     "readback_value": 250, "readback_flags": 2}]})},
                           {"label": "auto0", "t_start_ns": t0 + 8_900_000_000, "t_end_ns": t0 + 9_200_000_000,
                            "rc": 0, "stdout": json.dumps({"sets": [{"control": "cc.focus", "matches": True,
                                                                     "readback_flags": 1}]})}]}
    dev = wa.ds_events(launch, p, t0)
    assert dev[0]["t_ms"] == 6400.0 and dev[0]["t_end_ms"] == 6700.0 and dev[1]["matches"]


def test_image_restore_check():
    a = {"luma": {"median": 100.0, "conclusive": True}, "sharpness": {"median": 0.01, "conclusive": True}}
    assert wa.image_restore_check(a, {"luma": {"median": 105.0}, "sharpness": {"median": 0.011}})["ok"] is True
    assert wa.image_restore_check(a, {"luma": {"median": 70.0}, "sharpness": {"median": 0.011}})["ok"] is False
    dark = {"luma": {"median": 5.0, "conclusive": False, "reason": "dark"}, "sharpness": {"median": None}}
    assert wa.image_restore_check(dark, {"luma": {"median": 6.0}, "sharpness": {"median": None}})["ok"] is None


def _modes(*ms):
    return {"reader_streams": [{"types": [{"subtype": "MJPG", "width": w, "height": h, "fps_num": f, "fps_den": 1}
                                          for w, h, f in ms]}]}


def test_scoped_720_exact_lines():
    ctx = SimpleNamespace(args=SimpleNamespace(min_fps=30.0, min_height=720, max_height=720, all_modes=False))
    m, sc = wa.scoped_720(ctx, ck.mjpeg_modes(_modes((640, 480, 30), (1280, 720, 30), (1280, 720, 60),
                                                     (1920, 1080, 30))))
    assert m.text == "MJPG 1280x720@30"
    assert all("x720@" in t for t in sc["in_scope_streaming"])
    m2, sc2 = wa.scoped_720(ctx, ck.mjpeg_modes(_modes((1920, 1080, 30), (1280, 720, 15))))
    assert m2 is None and sc2["untested_reason"]


# ------------------------------------------------------------------------------------------------ fake camera
class FakeCam:
    """exposure: manual luma = 100 * 2**(v + 6) (clipped), auto -> 100 after 400 ms; focus: sharp (0.01) near 0 or
    in AF (after 1 s), blurred (0.001) elsewhere. ``flag_only``: the auto flag is accepted but nothing changes."""

    ae_delay_ns, af_delay_ns = 400e6, 1000e6

    def __init__(self, flag_only=False):
        self.st = {"exposure": {"value": -7, "flags": 2}, "focus": {"value": 0, "flags": 1}}
        self.auto_since = {"exposure": -10**12, "focus": -10**12}
        self.flag_only = flag_only
        self.eff = {"exposure": -7, "focus": 0}      # what the image follows

    def apply(self, name, val, t_ns, flags=None):
        before = dict(self.st[name])
        if val == "auto" or flags == "auto":
            if val not in ("auto", "manual") and val is not None:
                self.st[name]["value"] = int(val)          # value written, then the auto flag
                self.eff[name] = int(val)
            was_auto = self.st[name]["flags"] == 1
            self.st[name]["flags"] = 1
            if not self.flag_only and not was_auto:
                self.auto_since[name] = t_ns
        elif val == "manual":
            self.st[name]["flags"] = 2
            self.eff[name] = self.st[name]["value"]
        else:
            self.st[name] = {"value": int(val), "flags": 2}
            self.eff[name] = int(val)
            self.auto_since[name] = None
        want_auto = val == "auto" or flags == "auto"
        rb = dict(self.st[name])
        return {"control": f"cc.{name}", "requested": str(val), "before_value": before["value"],
                "before_flags": before["flags"], "readback_value": rb["value"], "readback_flags": rb["flags"],
                "matches": bool(rb["flags"] & 1) if want_auto else (rb["value"] == int(val) if val != "manual" else True)}

    def metric(self, t_ns):
        a = self.auto_since["exposure"]
        if a is not None and self.st["exposure"]["flags"] == 1 and t_ns - a > self.ae_delay_ns:
            luma = 100.0
        else:
            luma = min(250.0, max(1.0, 100.0 * 2 ** (self.eff["exposure"] + 6)))
        f = self.auto_since["focus"]
        if f is not None and self.st["focus"]["flags"] == 1 and t_ns - f > self.af_delay_ns:
            sharp = 0.01
        else:
            sharp = 0.01 if abs(self.eff["focus"]) < 30 else 0.001
        return luma, sharp

    def controls_json(self):
        return {"controls": [
            {"name": "exposure", "supported": True, "get_ok": True, "value": self.st["exposure"]["value"],
             "flags": self.st["exposure"]["flags"], "flags_names": ["auto"] if self.st["exposure"]["flags"] == 1
             else ["manual"], "caps_flags_names": ["auto", "manual"], "min": -11, "max": -2, "step": 1, "default": -5},
            {"name": "focus", "supported": True, "get_ok": True, "value": self.st["focus"]["value"],
             "flags": self.st["focus"]["flags"], "flags_names": ["auto"] if self.st["focus"]["flags"] == 1
             else ["manual"], "caps_flags_names": ["auto", "manual"], "min": 0, "max": 250, "step": 5, "default": 0}]}


CLOCK = {"t": 50_000_000_000}


def _parse_sets(spec):
    out = []
    for item in spec.split(","):
        if item:
            k, v = item.split("=")
            out.append((k, v))
    return out


def _stream(cam: FakeCam, od: Path, seconds: float, changes: list, t_first: int) -> list[dict]:
    """Frames every 33.3 ms from t_first; ``changes`` = [(t_ns, name, value, label)] applied in time order."""
    od.mkdir(parents=True, exist_ok=True)
    changes = sorted(changes, key=lambda c: c[0])
    rows, recs, ci = [], [], 0
    with (od / "frames.mjpeg").open("wb") as fm, (od / "frames.jsonl").open("w") as fj:
        n = int(seconds * 30)
        for i in range(n):
            t = t_first + int(i * 33_333_333)
            while ci < len(changes) and changes[ci][0] <= t:
                tc, name, val, label = changes[ci]
                recs.append({**cam.apply(name, val, tc), "label": label, "t_ns": tc})
                ci += 1
            luma, sharp = cam.metric(t)
            row = {"seq": i, "qpc_ns": t}
            if i % 2 == 0:
                b = f"FAKE luma={luma:.4f};sharp={sharp:.6f}".encode()
                row["mjpeg_offset"], row["mjpeg_len"] = fm.tell(), len(b)
                fm.write(b)
            fj.write(json.dumps(row) + "\n")
            rows.append(row)
    while ci < len(changes):
        tc, name, val, label = changes[ci]
        recs.append({**cam.apply(name, val, tc), "label": label, "t_ns": tc})
        ci += 1
    return recs


def _fake_metric(data, w, h, metric):
    m = re.match(rb"FAKE luma=([\d.]+);sharp=([\d.]+)", data)
    return float(m.group(1)) if metric == "luma_mean" else float(m.group(2))


def _install(monkeypatch, cam: FakeCam):
    monkeypatch.setattr(wa.ce, "metric_value", _fake_metric)
    monkeypatch.setattr(ck, "get_formats", lambda ctx, c, cache=None: (_modes((1280, 720, 30), (1920, 1080, 30)), {}))
    monkeypatch.setattr(ck, "get_controls", lambda ctx, c, api="mf", **k: (cam.controls_json(), {"rc": 0}))

    def set_controls(ctx, c, api, sets, flags=None, **k):
        CLOCK["t"] += 200_000_000
        return {"sets": [cam.apply(n, v, CLOCK["t"], flags) for n, v in sets.items()]}, {"rc": 0}
    monkeypatch.setattr(ck, "set_controls", set_controls)

    def wincam_capture(ctx, c, mode, od, frames=None, seconds=None, save="none", timeout_ms=5000, extra=(),
                       timeout_s=None):
        ex = [str(x) for x in extra]
        CLOCK["t"] += 2_000_000_000
        t_first = CLOCK["t"]
        changes = []
        if "--controls-before" in ex:
            for k2, v in _parse_sets(ex[ex.index("--controls-before") + 1]):
                changes.append((t_first - 100_000_000, k2, v, "before"))
        if "--schedule" in ex:
            for item in ex[ex.index("--schedule") + 1].split(";"):
                at, kv = item.split(":")
                k2, v = kv.split("=")
                changes.append((t_first + int(float(at) * 1e6), k2, v, f"at:{at}"))
        recs = _stream(cam, Path(od), seconds, changes, t_first)
        CLOCK["t"] = t_first + int(seconds * 1e9)
        sched = [{"control": r["control"], "at_ms": float(r["label"][3:]), "applied_qpc_ns": r["t_ns"],
                  "done_qpc_ns": r["t_ns"] + 10_000_000, **{k: r[k] for k in ("matches", "readback_value",
                                                                             "readback_flags", "before_value",
                                                                             "before_flags")}}
                 for r in recs if r["label"].startswith("at:")]
        cb = [{**r, "control": r["control"]} for r in recs if r["label"] == "before"]
        return {"ok": True, "schedule": sched, "controls_before": cb}, {"rc": 0}
    monkeypatch.setattr(ck, "wincam_capture", wincam_capture)

    def multi_launch(ctx, spec, spec_path, timeout_s):
        CLOCK["t"] += 2_000_000_000
        t0 = CLOCK["t"]
        cap = next(c for c in spec["commands"] if c["label"] == "capture")
        a = [str(x) for x in cap["argv"]]
        od, secs = Path(a[a.index("--out-dir") + 1]), float(a[a.index("--seconds") + 1])
        t_first = t0 + 800_000_000
        changes, cmds = [], []
        for c in spec["commands"]:
            if c["label"] == "capture":
                continue
            s = [str(x) for x in c["argv"]]
            k2, v = s[s.index("--set") + 1].split("=")
            ts = t0 + int(c["start_at_s"] * 1e9)
            changes.append((ts + 100_000_000, k2, v, c["label"]))
            cmds.append({"label": c["label"], "t_start_ns": ts, "t_end_ns": ts + 150_000_000, "rc": 0})
        recs = _stream(cam, od, secs, changes, t_first)
        for c in cmds:
            r = next(x for x in recs if x["label"] == c["label"])
            c["stdout"] = json.dumps({"sets": [r]})
        cmds.append({"label": "capture", "t_start_ns": t0, "t_end_ns": t_first + int(secs * 1e9), "rc": 0,
                     "stdout": json.dumps({"ok": True})})
        CLOCK["t"] = t_first + int(secs * 1e9)
        return {"commands": cmds}, {"rc": 0}
    monkeypatch.setattr(ck, "multi_launch", multi_launch)


class FakeCtx:
    def __init__(self, tmp: Path, cam: FakeCam):
        self.out_dir, self.raw_dir = tmp / "out", tmp / "raw"
        self.out_dir.mkdir()
        self.args = SimpleNamespace(quick=True, ctrl_runs=None, auto_toggles=None, min_fps=30.0, min_height=720,
                                    max_height=720, all_modes=False)
        self.cameras = [{"key": "046d:085c:sn=X", "name": "c922", "vid": "046d", "pid": "085c", "serial": "X",
                         "mf_symlink": "\\\\?\\usb#vid_046d&pid_085c#x#{mf}", "ds_path": "\\\\?\\usb#vid_046d&pid_085c#x#{ds}",
                         "is_kiyo": False, "metadata_tier1": False}]
        self.wincam = Path("wincam.exe")
        self.cam = cam
        self.logs = []

    def log(self, m):
        self.logs.append(m)

    def test_dir(self, name):
        d = self.out_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def camcmd(self, argv, timeout_s, **k):
        a = [str(x) for x in argv]
        assert "controls" in a and "--set" in a, a          # the only direct camcmd W-AUTO makes
        CLOCK["t"] += 200_000_000
        sets = [self.cam.apply(n, v, CLOCK["t"]) for n, v in _parse_sets(a[a.index("--set") + 1])]
        return {"rc": 0, "stdout": json.dumps({"sets": sets}), "stderr": "", "elapsed_s": 0.2}

    def arrivals(self):
        raise RuntimeError("no PnP offline")


def test_end_to_end_fake_camera(tmp_path, monkeypatch):
    cam = FakeCam()
    _install(monkeypatch, cam)
    ctx = FakeCtx(tmp_path, cam)
    res = wa.run(ctx)
    v = res["verdicts"]
    key = ctx.cameras[0]["key"]
    assert set(v) == {f"G-CTRL-AUTO|{key}|{p}-{c}" for p in ("mf", "ds") for c in ("ae", "af")}
    for k, x in v.items():
        assert x["rating"] == "yes", (k, x.get("note"), x["criteria"])
        assert x["restore"] is True and x["restore_image_ok"] is True
    # the original state came back: exposure manual -7, focus auto
    assert cam.st["exposure"] == {"value": -7, "flags": 2} and cam.st["focus"]["flags"] == 1
    m = res["measurements"]["cameras"][key]
    assert m["mode"] == "MJPG 1280x720@30"
    assert m["paths"]["mf"]["controls"]["focus"]["extremes"] == [250]      # AF position 0 -> the far end
    assert (tmp_path / "out" / m["paths"]["mf"]["detail_file"]).exists()
    # offline re-analysis gives the same ratings
    (tmp_path / "out" / "W-AUTO.json").write_text(json.dumps(res), encoding="utf-8")
    ra = wa.reanalyze(tmp_path / "out")
    assert ra["changes"] == [] and all(x["rating"] == "yes" for x in ra["verdicts"].values())


def test_end_to_end_flag_only_camera(tmp_path, monkeypatch):
    cam = FakeCam(flag_only=True)
    _install(monkeypatch, cam)
    res = wa.run(FakeCtx(tmp_path, cam))
    labels = {k.split("|")[-1]: x.get("summary_label") or x["rating"] for k, x in res["verdicts"].items()}
    assert labels == {"mf-ae": "no (flag only)", "ds-ae": "no (flag only)", "mf-af": "no (flag only)",
                      "ds-af": "no (flag only)"}


def test_gated_camera_is_untested_and_opens_nothing(tmp_path, monkeypatch):
    cam = FakeCam()
    _install(monkeypatch, cam)
    ctx = FakeCtx(tmp_path, cam)
    ctx.device_faults = {ctx.cameras[0]["key"]: {"active": True, "utc": "2026-11-08T00:00:00Z", "code": "0x8007001F"}}
    monkeypatch.setattr(ck, "wincam_capture", lambda *a, **k: (_ for _ in ()).throw(AssertionError("opened")))
    res = wa.run(ctx)
    assert {x["rating"] for x in res["verdicts"].values()} == {"untested"}


def test_modescope_import_still_has_contains():
    assert hasattr(modescope.from_args(SimpleNamespace(min_fps=30.0, min_height=720)), "contains")


def test_ds_path_killed_capture_is_a_device_fault(tmp_path, monkeypatch):
    """Review round 3: the DS path's capture runs under multi_launch (out of reach of ctx.camcmd's fault scan). A
    capture killed at its timeout is a device fault: it is reported to the gate and the camera is not re-opened."""
    cam = FakeCam()
    _install(monkeypatch, cam)
    launches = []

    def multi_launch(ctx, spec, spec_path, timeout_s):
        launches.append(spec_path)
        return {"commands": [{"label": "capture", "timed_out": True, "rc": None, "stdout": ""}]}, {"rc": 0}
    monkeypatch.setattr(ck, "multi_launch", multi_launch)
    ctx = FakeCtx(tmp_path, cam)
    res = wa.run(ctx)
    key = ctx.cameras[0]["key"]
    assert len(launches) == 1                                   # the killed capture was the last DS launch
    assert ctx.device_faults[key]["kind"] == "hung_process"     # reported to the (fallback) gate
    v = res["verdicts"]
    for c in ("ae", "af"):
        assert v[f"G-CTRL-AUTO|{key}|ds-{c}"]["rating"] == "untested"
    assert "device fault" in json.dumps(v[f"G-CTRL-AUTO|{key}|ds-af"])
    assert res["measurements"]["cameras"][key]["restore"]["restored"] is None   # no restore on a faulted camera


def test_capture_fault_from_an_unreleasable_mf_reader():
    rec = {"capture_fault": ck.fault_from_result("mf", {"ok": False, "error": {"class": "timeout",
                                                                               "stage": "reader_release"}}, {})}
    ctx = SimpleNamespace(log=lambda m: None)
    cam = {"key": "k", "name": "cam", "vid": "1", "pid": "2"}
    f = wa._capture_fault(ctx, cam, rec, "MJPG 1280x720@30")
    assert f and f["kind"] == "unreleasable" and f["mode"] == "MJPG 1280x720@30"
    assert ctx.device_faults["k"]["active"] is True
    assert wa._capture_fault(SimpleNamespace(log=lambda m: None), cam, {"error": {"class": "timeout",
                                                                                  "stage": "first_frame"}}) is None
