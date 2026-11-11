"""W-OCV-CTRL: OpenCV's camera controls through CAP_DSHOW and CAP_MSMF, set -> get -> real state -> image (G-CTRL).

Plan docs/capture_stack_options_plan.md section 6.1 (W-OCV-CTRL; fills the OpenCV column of rows 5-8: exposure,
AE on/off, focus, AF on/off). Per camera (the Kiyo included) and backend, each run is two OpenCV opens through
``helpers/opencv_ctrl.py`` (one camera lock each, generous child timeouts: MSMF opens took 39-41 s on the
Logitech cameras; ``open_ms`` is recorded):

- phase ``after``: auto set first (``wincam controls --api ds``, camera closed), open, format sets, first frame,
  ``baseline`` segment in auto; then the CAP_PROP_AUTO_EXPOSURE / CAP_PROP_AUTOFOCUS convention probe (which OpenCV
  value turns the camera's auto mode off / on, from a known auto state and from a known manual state, read through
  a DirectShow side channel); then CAP_PROP_EXPOSURE at 25/50/75% of the range (AE off), AE on, CAP_PROP_FOCUS at
  0/25/50/75/100% (AF off), AF on, each followed by a segment. When the last exposure value is < 2 steps from AE's
  own value (read through the side channel after the baseline), the helper sets one more sweep value >= 2 steps
  away before AE on (``exp_pre_ae``), so the AE-on transition can leave the luma band (Gerald 2026-11-06: 75% of
  -11..-2 = -4 was the C922's and the Kiyo's AE value);
- phase ``before``: auto set first, open, and BEFORE the first read() AE off + EXPOSURE (the 50% value) and AF off
  + FOCUS (the value that defocused most in phase ``after``); then the first frame, a segment, the real state, a
  second segment.

Every set records OpenCV's return value (accepted / refused), OpenCV's own get() readback and the camera's real
value and flag (``wincam controls --api ds --read-only`` through a second filter instance while OpenCV streams).
Images: every 2nd frame JPEG-encoded by the helper and measured with common.imgmetrics through the same code as
W-CTRL-EFFECT (``w_ctrl_effect._segment_metrics`` / ``judge``: second half of each segment; exposure monotonic
with last/first >= 1.25, focus max/min >= 1.30). AE / AF back on: W-AUTO's recovery analysis (luma within +/-15%
of the baseline segment within 3 s; sharpness >= 80% within 5 s), inconclusive on unsuitable scenes.

Value conventions (``measurements.cameras.<key>.backends.<b>.conventions``): what each probed AUTO_EXPOSURE /
AUTOFOCUS value did ("manual", "auto", "ignored", "toggles"), what get() returns in each state, and whether
EXPOSURE / FOCUS get() equals the camera's value (DSHOW passes IAMCameraControl units through: log2 seconds).

Before/after first frame: OpenCV DSHOW builds and runs the DirectShow graph inside VideoCapture(), so its "before
the first read()" sets may already land on a running stream; MSMF creates the source reader at open and starts
streaming at the first read(). The result records this as is.

Identity: OpenCV opens by index (``opencv_dshow_index`` / ``opencv_msmf_index`` from discovery). With MSMF the helper
runs ``wincam activity`` after the first frame; a different device streamed by the helper makes the backend
"untested (wrong device)". DSHOW clients are invisible to the activity monitor (frame size checked only).

Restore: OpenCV's own restore resets only flags (W-CYC, 2026-11-06), so after each backend the original values AND
flags read at the start are put back with ``wincam controls`` and verified (w_auto.restore_verified). After a hung
OpenCV call the camera gets a 1-frame MF health probe first: if it answers, the fault is cleared and the next backend
runs; the restore is attempted (bounded) either way and its result recorded.

Ratings: ``G-CTRL|<camera>|opencv_dshow`` / ``opencv_msmf`` via common.rating.rate_ctrl (W-CTRL-EFFECT's thresholds,
3/3 runs); a set counts when OpenCV accepted it and the camera holds the value (side channel). OpenCV's get() echo
is its own criterion ("OpenCV get() reflects the camera"): False caps the cell at partial with the workaround "read
it through DirectShow / MF" (MSMF get() returned stale values on 2026-11-09 while the camera held every value).
``G-CTRL-AUTO|<camera>|opencv_<b>-ae`` / ``-af`` via w_auto.rate_auto (no before-start transition).
A backend whose AUTO value is never found rates "no (OpenCV cannot switch auto on)". Tier 0 only (frame content).

Offline: ``python w_ocv_ctrl.py --reanalyze <run_dir>`` re-rates the stored per-run records.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
import suitectx  # noqa: E402
import w_auto as wa  # noqa: E402
import w_ctrl_effect as ce  # noqa: E402
from common import rating, results  # noqa: E402

TEST = "W-OCV-CTRL"
OPENCV_CTRL = WIN / "helpers" / "opencv_ctrl.py"
BACKENDS = ("dshow", "msmf")
CONTROLS = ("exposure", "focus")
OPEN_TIMEOUT_S = {"dshow": 45.0, "msmf": 120.0}
CALL_TIMEOUT_MS = 8000
SEG_S, FOCUS_SEG_S, BASELINE_S = 2.0, 1.5, 3.0
AE_ON_S, AF_ON_S = 4.5, 6.5
BEFORE_SHARP_TOL = 0.7          # before-start focus image: sharpness ratio vs the phase-after segment in [0.7, 1/0.7]


def runs_per(ctx) -> int:
    return int(ck.arg(ctx, "ctrl_runs", 3, 1))


def estimate_s(ctx) -> float:
    """Per run and backend: open (DSHOW ~5 s, MSMF ~40 s on Logitech) x 2, probes (~24 side calls ~0.5 s), segments
    ~33 s, plus restores."""
    r = runs_per(ctx)
    per_run = {"dshow": 2 * 6 + 14 + 33 + 6, "msmf": 2 * 40 + 14 + 33 + 6}
    return len(ctx.cameras) * (r * sum(per_run.values()) + 2 * 10 + 10)


# ------------------------------------------------------------------------------------------------------- helper argv
def helper_args(ctx, cam: dict, backend: str, mode, od: Path, phase: str, exp_vals, foc_vals, before: dict | None,
                exp_step=1) -> tuple[list[str], float]:
    idx = cam.get(f"opencv_{backend}_index")
    expect = cam.get("ds_path") if backend == "dshow" else cam.get("mf_symlink")
    args = ["run", "--backend", backend, "--index", idx, "--expect-path", expect, "--width", mode.w, "--height",
            mode.h, "--fps", f"{mode.fps:.6g}", "--timeout-ms", CALL_TIMEOUT_MS, "--open-timeout-ms",
            int(OPEN_TIMEOUT_S[backend] * 1000), "--out-dir", od, "--wincam", ctx.wincam, "--ds-device",
            cam.get("ds_path"), "--phase", phase, "--baseline-s", BASELINE_S, "--seg-s", SEG_S, "--focus-seg-s",
            FOCUS_SEG_S, "--ae-on-s", AE_ON_S, "--af-on-s", AF_ON_S]
    if phase == "after":
        # "--flag=value": argparse would read a value starting with "-" ("-9,-7,-4") as an option
        args += ["--exp-values=" + ",".join(str(v) for v in exp_vals or []),
                 "--focus-values=" + ",".join(str(v) for v in foc_vals or []), "--exp-step", exp_step or 1]
        # + 1 exposure segment: the optional exp_pre_ae set (a value >= 2 steps from AE's own before AE on)
        segs = BASELINE_S + SEG_S * (len(exp_vals or []) + 1) + AE_ON_S + FOCUS_SEG_S * len(foc_vals or []) + AF_ON_S
        side_calls = 2 + 4 * 5 + 4 * 2 + len(exp_vals or []) + 1 + len(foc_vals or []) + 4
    else:
        for k, flag in (("exp_before", "--exp-before"), ("focus_before", "--focus-before"),
                        ("ae_manual", "--ae-manual"), ("af_off", "--af-off")):
            if (before or {}).get(k) is not None:
                args += [f"{flag}={before[k]}"]
        segs = 2 * SEG_S + 1
        side_calls = 8
    # MSMF: the format sets share the open bound (opencv_ctrl 1.2: the reader is rebuilt per set), so twice it
    timeout = OPEN_TIMEOUT_S[backend] * (2 if backend == "msmf" else 1) + segs + side_calls * 6 + 60
    return ck.helper_argv(ctx, OPENCV_CTRL, *args), timeout


# ------------------------------------------------------------------------------------------------------- analysis
def seg_by_label(doc: dict) -> dict:
    return {s.get("label"): s for s in (doc or {}).get("segments") or []}


def ev_by_tag(doc: dict) -> dict:
    out = {}
    for e in (doc or {}).get("events") or []:
        out.setdefault(e.get("tag"), e)
    return out


def side_state(ev: dict | None, name: str) -> dict:
    return (((ev or {}).get("side") or {}).get("state") or {}).get(name) or {}


def seg_metrics(od: Path, doc: dict, labels: list[str], metric: str, mode) -> list[dict]:
    segs = seg_by_label(doc)
    bounds = [(segs[lb]["t_start_ns"], segs[lb]["t_end_ns"]) for lb in labels if lb in segs]
    if len(bounds) != len(labels):
        return []
    return ce._segment_metrics(od, bounds, metric, mode)


def points_since(od: Path, origin_ns: int, metric: str, mode) -> list:
    rows = ck.load_frames(od)
    pts = []
    for r, data in ck.saved_frame_bytes(od, rows):
        t = r.get("qpc_ns")
        if t is None:
            continue
        try:
            v = ce.metric_value(data, mode.w, mode.h, metric)
        except Exception:  # noqa: BLE001
            v = None
        if v is not None:
            pts.append([round((int(t) - origin_ns) / 1e6, 1), round(float(v), 6)])
    return pts


def set_ok(ev: dict | None, name: str, want, step) -> dict:
    """OpenCV accepted the set and the camera holds the value in manual mode (its real state through the DirectShow
    side channel). OpenCV's own get() echo is recorded separately (``get_matches``): MSMF get() returns stale
    values while the camera holds every value (smoke 2026-11-09), which is a readback defect of OpenCV, not a
    failed set."""
    if not ev:
        return {"ok": None, "why": "not set"}
    st = side_state(ev, name)
    got = ev.get("got")
    get_match = isinstance(got, (int, float)) and not (isinstance(got, float) and math.isnan(got)) \
        and abs(float(got) - float(want)) <= ce.step_tol(step)
    real = ce.held(st.get("value"), st.get("flags"), want, step)
    return {"ok": bool(ev.get("ret")) and real is True, "ret": ev.get("ret"), "got": got,
            "get_matches": bool(get_match), "real_value": st.get("value"), "real_mode": st.get("mode"),
            "real_held": real}


def auto_capture(doc: dict, od: Path, name: str, mode, manual_tag: str, auto_tag: str, auto_seg: str) -> dict:
    """W-AUTO-style capture record for the auto-on segment: the last manual set -> the auto set -> recovery."""
    metric = wa.METRIC[name]
    rows = ck.load_frames(od)
    if not rows:
        return {"control": name, "points": [], "events": [], "plan": {"toggles": []}}
    t0 = int(rows[0]["qpc_ns"])
    ev = ev_by_tag(doc)
    man, aut = ev.get(manual_tag), ev.get(auto_tag)
    events = []
    if man:
        events.append({"k": 0, "kind": "manual", "value": man.get("value"), "t_ms": wa._ms(man.get("t_ns"), t0),
                       "t_end_ms": wa._ms(man.get("t_end_ns"), t0), "matches": bool(man.get("ret"))})
    if aut and aut.get("op") == "set":
        events.append({"k": 0, "kind": "auto", "value": "auto", "t_ms": wa._ms(aut.get("t_ns"), t0),
                       "t_end_ms": wa._ms(aut.get("t_end_ns"), t0),
                       "matches": side_state(aut, name).get("mode") == "auto", "opencv_ret": aut.get("ret"),
                       "readback_flags": side_state(aut, name).get("flags")})
    return {"control": name, "points": points_since(od, t0, metric, mode), "events": events,
            "plan": {"toggles": [{"k": 0, "value": (man or {}).get("value")}]}}


def baseline_of(doc: dict, od: Path, name: str, mode) -> dict:
    s = seg_by_label(doc).get("baseline")
    if not s:
        return {"median": None, "conclusive": False, "reason": "no baseline segment"}
    metric = wa.METRIC[name]
    pts = points_since(od, int(s["t_start_ns"]), metric, mode)
    dur = (s["t_end_ns"] - s["t_start_ns"]) / 1e6
    return wa.baseline_from(pts, metric, (dur / 2.0, dur + 1))


def analyse_after(doc: dict, od: Path, mode, exp_vals: list, foc_vals: list, ranges: dict) -> dict:
    ev = ev_by_tag(doc)
    out: dict = {"open_ms": doc.get("open_ms"), "close_ms": doc.get("close_ms"), "format": doc.get("format"),
                 "convention": doc.get("convention"), "error": doc.get("error"), "hung": doc.get("hung")}
    rows = ck.load_frames(od)
    if rows and doc.get("t_open_ns"):
        out["open_to_first_frame_ms"] = round((int(rows[0]["qpc_ns"]) - int(doc["t_open_ns"])) / 1e6, 1)
    out["fps_measured"] = ck.fps_from_rows([r for r in rows if r.get("segment") == "baseline"])
    shapes = sorted({tuple(r.get("shape") or [])[:2] for r in rows})
    out["frame_shapes"] = [list(s) for s in shapes]
    out["size_ok"] = bool(shapes) and all(list(s) == [mode.h, mode.w] for s in shapes)
    if exp_vals:
        seg = seg_metrics(od, doc, [f"exp{i}" for i in range(len(exp_vals))], "luma_mean", mode)
        j = ce.judge("exposure", exp_vals, seg) if seg else {"effect_ok": None, "reason": "no segments"}
        sets = [set_ok(ev.get(f"exp{i}"), "exposure", v, ranges.get("exposure") or 1) for i, v in enumerate(exp_vals)]
        out["exposure"] = {"values": exp_vals, "segments": seg, **j, "sets": sets,
                           "set_readback_ok": all(s.get("ok") for s in sets),
                           "get_matches_camera": all(s.get("get_matches") for s in sets),
                           "ae_off_event": ev.get("ae_off"), "ae_on_event": ev.get("ae_on"),
                           "baseline": baseline_of(doc, od, "exposure", mode)}
        # the helper adds exp_pre_ae when the last sweep value was < 2 steps from AE's own value (opencv_ctrl 1.1)
        man_tag = "exp_pre_ae" if "exp_pre_ae" in ev else f"exp{len(exp_vals) - 1}"
        out["exposure"]["pre_ae_on_event"] = ev.get("exp_pre_ae")
        cap = auto_capture(doc, od, "exposure", mode, man_tag, "ae_on", "ae_on")
        out["exposure"]["auto_on"] = wa.analyse_transitions(cap, out["exposure"]["baseline"], pre_ref=False)
        out["exposure"]["auto_on_points"] = cap["points"]
    if foc_vals:
        seg = seg_metrics(od, doc, [f"focus{i}" for i in range(len(foc_vals))], "sharpness", mode)
        j = ce.judge("focus", foc_vals, seg) if seg else {"effect_ok": None, "reason": "no segments"}
        sets = [set_ok(ev.get(f"focus{i}"), "focus", v, ranges.get("focus") or 1) for i, v in enumerate(foc_vals)]
        out["focus"] = {"values": foc_vals, "segments": seg, **j, "sets": sets,
                        "set_readback_ok": all(s.get("ok") for s in sets),
                        "get_matches_camera": all(s.get("get_matches") for s in sets),
                        "af_off_event": ev.get("af_off"), "af_on_event": ev.get("af_on"),
                        "baseline": baseline_of(doc, od, "focus", mode)}
        cap = auto_capture(doc, od, "focus", mode, f"focus{len(foc_vals) - 1}", "af_on", "af_on")
        out["focus"]["auto_on"] = wa.analyse_transitions(cap, out["focus"]["baseline"], pre_ref=False)
        out["focus"]["auto_on_points"] = cap["points"]
    return out


def before_values(after: dict, exp_vals: list, foc_vals: list) -> dict:
    """Phase-before values: exposure = the middle value; focus = the value whose phase-after sharpness is lowest
    relative to the AF baseline (most defocused: an AF that stays on or a reset value shows)."""
    conv = after.get("convention") or {}
    out = {"exp_before": exp_vals[len(exp_vals) // 2] if exp_vals else None,
           "ae_manual": (conv.get("auto_exposure") or {}).get("manual_value"),
           "af_off": (conv.get("autofocus") or {}).get("manual_value"), "focus_before": None}
    if foc_vals:
        seg = (after.get("focus") or {}).get("segments") or []
        vals = [s.get("value") for s in seg]
        if len(vals) == len(foc_vals) and all(isinstance(v, (int, float)) for v in vals):
            out["focus_before"] = foc_vals[vals.index(min(vals))]
        else:
            out["focus_before"] = foc_vals[-1]
    return out


def analyse_before(doc: dict, od: Path, mode, bv: dict, after: dict, ranges: dict) -> dict:
    ev = ev_by_tag(doc)
    out: dict = {"open_ms": doc.get("open_ms"), "error": doc.get("error"), "hung": doc.get("hung"),
                 "values": bv, "first_frame_ms_after_sets": doc.get("first_frame_ms_after_sets")}
    held_ev = ev.get("after_first_frame")
    for name, tag, metric, key in (("exposure", "before_exp", "luma_mean", "exp_before"),
                                   ("focus", "before_focus", "sharpness", "focus_before")):
        want = bv.get(key)
        if want is None or name not in after:
            continue
        st_set = set_ok(ev.get(tag), name, want, ranges.get(name) or 1)
        st_after = side_state(held_ev, name)
        held = ce.held(st_after.get("value"), st_after.get("flags"), want, ranges.get(name) or 1)
        seg = seg_metrics(od, doc, ["before0", "before1"], metric, mode)
        vb = [s.get("value") for s in seg if s.get("value") is not None]
        a = after[name]
        idx = a["values"].index(want) if want in a["values"] else None
        va = ((a.get("segments") or [])[idx] or {}).get("value") if idx is not None and a.get("segments") else None
        img = None
        if vb and va:
            ratio = (sum(vb) / len(vb)) / va
            img = {"ratio_vs_phase_after": round(ratio, 4),
                   "ok": abs(ratio - 1.0) <= wa.LUMA_BAND if metric == "luma_mean"
                   else BEFORE_SHARP_TOL <= ratio <= 1.0 / BEFORE_SHARP_TOL}
        out[name] = {"set": st_set, "real_after_first_frame": st_after, "held_through_start": held,
                     "segments": seg, "image": img,
                     "ok": bool(st_set.get("ok") and held is True and (img or {}).get("ok"))}
    return out


def conventions(runs: list[dict]) -> dict:
    """Value conventions seen in the first run with a probe (OpenCV get() vs the camera's real value)."""
    out: dict = {}
    for r in runs:
        a = r.get("after") or {}
        conv = a.get("convention") or {}
        if not conv:
            continue
        for k in ("auto_exposure", "autofocus"):
            c = conv.get(k) or {}
            out[k] = {"manual_value": c.get("manual_value"), "auto_value": c.get("auto_value"),
                      "meanings": c.get("meanings"),
                      "get_when_auto": sorted({str(p.get("from_manual_got")) for p in c.get("probe") or []
                                               if p.get("from_manual") == "auto"}
                                              | {str(p.get("from_auto_got")) for p in c.get("probe") or []
                                                 if p.get("from_auto") == "auto"}),
                      "get_when_manual": sorted({str(p.get("from_auto_got")) for p in c.get("probe") or []
                                                 if p.get("from_auto") == "manual"}
                                                | {str(p.get("from_manual_got")) for p in c.get("probe") or []
                                                   if p.get("from_manual") == "manual"}),
                      "set_return_values": sorted({str(p.get("from_auto_ret")) for p in c.get("probe") or []})}
        for name in ("exposure", "focus"):
            sets = (a.get(name) or {}).get("sets") or []
            if sets:
                out[f"{name}_get_vs_camera"] = [{"set": v, "opencv_get": s.get("got"), "camera": s.get("real_value"),
                                                 "accepted": s.get("ret")}
                                                for v, s in zip((a.get(name) or {}).get("values") or [], sets)]
                out[f"{name}_get_equals_camera"] = all(s.get("get_matches") for s in sets)
        break
    return out


GET_WORKAROUND = "OpenCV get() does not reflect the camera's value: read it through DirectShow / MF (IAMCameraControl)"


def _get_reflects(a: dict) -> bool | None:
    """Did OpenCV's get() echo every set value? Old stored analyses (before 2026-11-09) have no
    ``get_matches_camera``: derived from the per-set rows."""
    if "get_matches_camera" in a:
        return a.get("get_matches_camera")
    sets = a.get("sets") or []
    return all(s.get("get_matches") for s in sets) if sets else None


def control_row(name: str, runs: list[dict], listing: dict) -> dict:
    eff, rb, bef, gm = [], [], [], []
    for r in runs:
        a = (r.get("after") or {}).get(name) or {}
        b = (r.get("before") or {}).get(name) or {}
        eff.append(a.get("effect_ok"))
        rb.append(_set_held(a))
        bef.append(_before_ok(b) if b else None)
        gm.append(_get_reflects(a) if a else None)
    after_ok = [bool(e and k) for e, k in zip(eff, rb)]
    runs_ok = sum(1 for x, b in zip(after_ok, bef) if x and b)
    workaround = None
    if runs and all(after_ok) and not all(bef):
        workaround = "a value set before the first frame did not hold or did not reach the image: set it after the " \
                     "first frame"
    get_ok = (all(x is True for x in gm) if gm and all(x is not None for x in gm) else None)
    if get_ok is False:
        workaround = f"{workaround}; {GET_WORKAROUND}" if workaround else GET_WORKAROUND
    return {"name": name, "listed": listing.get("listed"), "range_matches_descriptor": listing.get("range_matches_descriptor"),
            "listing_source": listing.get("source"),
            "set_readback_ok": (all(x is True for x in rb) if rb and all(x is not None for x in rb) else None),
            "effect_ok": (all(x is True for x in eff) if eff and all(x is not None for x in eff) else None),
            "before_start_ok": (all(x is True for x in bef) if bef and all(x is not None for x in bef) else None),
            "after_start_ok": all(after_ok) if runs else None, "runs_ok": runs_ok, "runs_total": len(runs),
            "opencv_get_reflects_camera": get_ok, "workaround": workaround}


def _before_ok(b: dict) -> bool | None:
    """Phase-before result with the set judged by the camera's state (``ret`` and ``real_held``), not OpenCV's get()
    echo; re-derived so stored analyses from before 2026-11-09 rate the same way as new ones."""
    st = b.get("set") or {}
    if "real_held" not in st:
        return b.get("ok")
    return bool(st.get("ret") and st.get("real_held") is True and b.get("held_through_start") is True
                and (b.get("image") or {}).get("ok"))


def _set_held(a: dict) -> bool | None:
    """Every set accepted and held by the camera. Stored analyses from before 2026-11-09 folded OpenCV's get()
    echo into ``set_readback_ok``; re-derived from the per-set rows (``ret`` and ``real_held``) when present."""
    sets = a.get("sets") or []
    if sets and all("real_held" in s for s in sets):
        return all(bool(s.get("ret")) and s.get("real_held") is True for s in sets)
    return a.get("set_readback_ok")


def backend_verdicts(key: str, b: str, brec: dict, listing_for, n_runs: int) -> dict:
    out = {}
    vk = f"G-CTRL|{key}|opencv_{b}"
    if brec.get("verdict_override"):
        out[vk] = dict(brec["verdict_override"])
        for n in CONTROLS:
            out[f"{wa.GOAL}|{key}|opencv_{b}-{wa.SHORT[n]}"] = dict(brec["verdict_override"])
        return out
    runs = brec.get("runs") or []
    names = [n for n in CONTROLS if n in (brec.get("testable") or [])]
    rows = [control_row(n, runs, listing_for(n)) for n in names]
    v = rating.rate_ctrl(rows, runs_required=3) if rows else rating.untested("no testable control")
    if rows and v.get("rating") in ("yes", "partial"):
        gets = [r.get("opencv_get_reflects_camera") for r in rows]
        met = None if any(g is None for g in gets) else all(gets)
        v["criteria"].append(rating._crit("OpenCV get() reflects the camera (else read through DirectShow / MF)", met,
                                          {r["name"]: r.get("opencv_get_reflects_camera") for r in rows}))
        if met is False and v["rating"] == "yes":
            v["rating"] = "partial"
    if rows and n_runs < 3:
        v["note"] = ((v.get("note") or "") + f" only {n_runs} run(s) (quick)").strip()
    v["restore"] = (brec.get("restore") or {}).get("restored")
    v["conventions"] = brec.get("conventions")
    out[vk] = v
    for n in CONTROLS:
        ak = f"{wa.GOAL}|{key}|opencv_{b}-{wa.SHORT[n]}"
        if n not in names:
            r = rating.untested((brec.get("na") or {}).get(n) or "n/a")
            r["summary_label"] = "untested (n/a)"
            out[ak] = r
            continue
        conv = (brec.get("conventions") or {}).get("auto_exposure" if n == "exposure" else "autofocus") or {}
        if runs and conv and conv.get("auto_value") is None:
            prop = "CAP_PROP_AUTO_EXPOSURE" if n == "exposure" else "CAP_PROP_AUTOFOCUS"
            r = rating._result("no", [rating._crit(f"an OpenCV {prop} value turns the camera's auto mode on", False,
                                                   conv.get("meanings"))], {"conventions": conv},
                               f"no {prop} value turned auto on (probed {sorted((conv.get('meanings') or {}))})")
            r["summary_label"] = "no (OpenCV cannot switch auto on)"
            out[ak] = r
            continue
        rec = {"baseline": None, "runs": [{"analysis": ((r.get("after") or {}).get(n) or {}).get("auto_on") or {}}
                                          for r in runs]}
        out[ak] = wa.rate_auto(n, rec, n_runs, 1, with_before_start=False)
    return out


# ------------------------------------------------------------------------------------------------------- run
def _identity(doc: dict | None, cam: dict) -> dict:
    """MSMF only: did THIS helper process stream the expected device (wincam activity after the first frame)?"""
    act = (doc or {}).get("activity")
    if not isinstance(act, list):
        return {"checked": False, "why": "no activity record (DSHOW clients are invisible to the monitor)"}
    pid = (doc or {}).get("pid")
    want = ck.norm_link(cam.get("mf_symlink"))
    mine = [d for d in act if any(p.get("pid") == pid and p.get("streaming") for p in d.get("processes") or [])]
    keys = [d.get("match_key") for d in mine]
    if not mine:
        return {"checked": True, "confirmed": None, "why": "the helper was not seen streaming any device"}
    return {"checked": True, "confirmed": want in keys, "streamed_by_helper": keys, "expected": want}


def run(ctx) -> dict:
    res = ck.new_result(ctx, TEST)
    arr0 = ck.arrivals_before(ctx)
    n_runs = runs_per(ctx)
    errors: list = []
    verdicts: dict = {}
    per_cam: dict = {}
    fcache: dict = {}
    raw = Path(ctx.raw_dir) / TEST
    tdir = ctx.test_dir(TEST)
    ctrl_list = ce.load_ctrl_list(Path(ctx.out_dir) / "W-CTRL-LIST.json")
    for cam in ctx.cameras:
        key, slug = cam["key"], ck.cam_slug(cam)
        cres: dict = {"name": cam.get("name"), "is_kiyo": cam.get("is_kiyo"), "backends": {},
                      "indices": {b: cam.get(f"opencv_{b}_index") for b in BACKENDS}}
        per_cam[key] = cres

        def all_cells(v: dict) -> None:
            for b in BACKENDS:
                verdicts.update(backend_verdicts(key, b, {"verdict_override": v}, lambda n: {}, n_runs))

        gf = ce.gate_fault(ctx, cam)
        if gf:
            cres["gate_fault"] = gf
            all_cells(ce.gate_untested(ctx, cam, gf))
            continue
        if not cam.get("ds_path"):
            all_cells(rating.untested("no DirectShow path: the real-state side channel needs it"))
            continue
        fm, fread = ck.formats_checked(ctx, cam, fcache, TEST)
        if fread:
            # format read failed (not a scope exclusion); a hang / 0x8007001F is a device fault via the probe
            cres["format_read"] = fread
            all_cells(ck.format_failed_untested(fread))
            continue
        mode, scope = wa.scoped_720(ctx, ck.mjpeg_modes(fm))
        cres["mode"], cres["mode_scope"] = (mode.text if mode else None), scope
        if mode is None:
            all_cells(ck.scope_untested(ctx, scope))
            continue
        initial, run0 = ck.get_controls(ctx, cam, "ds")
        mf_read, _ = ck.get_controls(ctx, cam, "mf") if cam.get("mf_symlink") else (None, None)
        na, hr = ce.not_answering(initial, run0)
        if na:
            ce.gate_report(ctx, cam, mode.text, hr, "ds control GETs failed", "ds")
            r = rating.rate_ctrl([], device_not_answering=True, not_answering_hr=hr)
            all_cells(r)
            cres["device_not_answering"] = {"hr": hr, "run": run0}
            continue
        tab = ck.control_table(initial)
        tabs = {"ds": tab, "mf": ck.control_table(mf_read)}
        ranges = {n: {k: (tab.get(n) or {}).get(k) for k in ("min", "max", "step", "default")} for n in CONTROLS}
        testable, na_why = [], {}
        for n in CONTROLS:
            c = tab.get(n)
            if c is None:
                na_why[n] = f"n/a: the camera has no {n} control"
            elif not ce.manual_capable(c) or not ce.values_for(n, c):
                na_why[n] = f"n/a: {n} has no manual mode / usable range"
            else:
                testable.append(n)
        exp_vals = ce.values_for("exposure", tab["exposure"]) if "exposure" in testable else []
        foc_vals = ce.values_for("focus", tab["focus"]) if "focus" in testable else []
        orig = wa.state_of(tab, testable)
        cres.update(ranges=ranges, testable=testable, n_a=na_why, original_state=orig, exposure_values=exp_vals,
                    focus_values=foc_vals)
        listing_for = (lambda n, _cl=ctrl_list.get(key): ce.listing_inputs(_cl, n, tabs))
        cres["listing"] = {n: listing_for(n) for n in testable}      # G-CTRL criterion 1 inputs (kept for --reanalyze)
        dead = None
        faults_seen: list = []
        for b in BACKENDS:
            brec: dict = {"testable": testable, "na": na_why, "runs": []}
            cres["backends"][b] = brec
            if not testable:
                continue
            if cam.get(f"opencv_{b}_index") is None:
                brec["verdict_override"] = rating.untested(f"no OpenCV {b} index from discovery")
                continue
            if dead:
                brec["verdict_override"] = rating.device_fault_untested(dead)
                continue
            try:
                for k in range(n_runs):
                    rrec: dict = {"run_index": k}
                    brec["runs"].append(rrec)
                    for phase in ("after", "before"):
                        if phase == "before" and not rrec.get("after"):
                            break
                        ck.set_controls(ctx, cam, "ds", {n: "auto" for n in testable})
                        od = raw / slug / f"{b}_r{k}_{phase}"
                        bv = before_values(rrec["after"], exp_vals, foc_vals) if phase == "before" else None
                        argv, tmo = helper_args(ctx, cam, b, mode, od, phase, exp_vals, foc_vals, bv,
                                                exp_step=(ranges.get("exposure") or {}).get("step"))
                        ctx.log(f"{TEST}: {cam.get('name')} {b} run {k} phase {phase} (timeout {tmo:.0f} s)")
                        r = ctx.camcmd(argv, timeout_s=tmo)
                        doc, perr = suitectx.parse_json_stdout(r)
                        if doc is None and (od / "summary.json").exists():
                            try:
                                doc = json.loads((od / "summary.json").read_text(encoding="utf-8"))
                            except ValueError:
                                doc = None
                        rrec[f"{phase}_run"] = ck.run_brief(r)
                        if doc is None:
                            rrec[f"{phase}_error"] = perr
                            errors.append({"camera": key, "backend": b, "run": k, "phase": phase, "error": perr,
                                           "timed_out": r.get("timed_out")})
                        if b == "msmf" and doc is not None:
                            rrec[f"{phase}_identity"] = _identity(doc, cam)
                        hung = (doc or {}).get("hung") or (r.get("timed_out") and {"call": "process timeout"})
                        if hung:
                            flt = {"kind": "hung_process" if r.get("timed_out") else "unreleasable", "code": "timeout",
                                   "stage": (hung or {}).get("call"),
                                   "reason": f"OpenCV {b} call {(hung or {}).get('call')!r} did not return"}
                            dead = ck.mark_device_fault(ctx, cam, TEST, mode.text, f"opencv_{b}", flt) or flt
                            rrec[f"{phase}_hung"] = hung
                            ctx.log(f"{TEST}: {cam.get('name')} {b}: OpenCV call hung; remaining work skipped")
                            break
                        if doc is None:
                            break
                        pts = {}
                        if phase == "after":
                            rrec["after"] = analyse_after(doc, od, mode, exp_vals, foc_vals, ranges)
                            pts = {n: rrec["after"][n].pop("auto_on_points", None) for n in CONTROLS
                                   if n in rrec["after"]}
                        else:
                            rrec["before"] = analyse_before(doc, od, mode, bv, rrec["after"], ranges)
                        det = {k2: doc.get(k2) for k2 in ("events", "segments", "convention", "format", "open_ms",
                                                          "close_ms", "error", "hung", "activity", "pid", "opencv",
                                                          "backend")}
                        det["metric_points_ms_after_first_frame"] = pts
                        dp = results.write_json(tdir / f"{slug}_{b}_r{k}_{phase}.json", det)
                        rrec[f"{phase}_detail_file"] = str(dp.relative_to(ctx.out_dir)).replace("\\", "/")
                    a = rrec.get("after") or {}
                    ctx.log(f"{TEST}: {cam.get('name')} {b} run {k}: open {a.get('open_ms')} ms; exposure effect "
                            f"{(a.get('exposure') or {}).get('effect_ok')} readback "
                            f"{(a.get('exposure') or {}).get('set_readback_ok')}; focus effect "
                            f"{(a.get('focus') or {}).get('effect_ok')}; conv "
                            f"{ {kk: (v or {}).get('meanings') for kk, v in (a.get('convention') or {}).items()} }")
                    if dead:
                        break
                    ident = rrec.get("after_identity") or {}
                    if ident.get("confirmed") is False:
                        brec["verdict_override"] = rating.untested(
                            f"OpenCV MSMF index {cam.get('opencv_msmf_index')} opened a different device "
                            f"({ident.get('streamed_by_helper')})", ident)
                        brec["verdict_override"]["summary_label"] = "untested (wrong device)"
                        break
            finally:
                bfault = dead
                if dead:
                    # a hung OpenCV call: does the camera answer now (1-frame MF probe; success clears the fault)?
                    # The restore runs either way (every wincam call is bounded), so a hang late in phase "after"
                    # never leaves manual exposure / focus on the camera unrecorded
                    hp = ck.health_check(ctx, cam, mode, raw / slug / f"_health_{b}", test=TEST,
                                         reason=f"after the OpenCV {b} hang")
                    brec["health_probe_after_hang"] = {k: hp.get(k) for k in (
                        "ok", "utc", "code", "stage", "class", "recovered", "faulted_after", "elapsed_s", "error")}
                    if hp.get("ok"):
                        ck.clear_device_fault(ctx, cam, TEST, brec["health_probe_after_hang"])
                        ctx.log(f"{TEST}: {cam.get('name')} answered the probe after the {b} hang; restoring and "
                                "continuing with the next backend")
                        dead = None
                try:
                    brec["restore"] = wa.restore_verified(ctx, cam, "ds", orig, ranges, errors)
                    if bfault:
                        brec["restore"]["after_hang"] = True
                        brec["restore"]["camera_answered_probe"] = dead is None
                except Exception as e:  # noqa: BLE001
                    errors.append({"camera": key, "backend": b, "restore_exception": repr(e)})
                    brec["restore"] = {"error": repr(e), "restored": None, "after_hang": bool(bfault)}
            brec["conventions"] = conventions(brec["runs"])
            if bfault:
                brec["device_fault"] = bfault
                faults_seen.append(bfault)
            if bfault and not brec.get("verdict_override") and not any(r.get("after") for r in brec["runs"]):
                brec["verdict_override"] = rating.device_fault_untested(bfault)
        cres["device_fault"] = dead or (faults_seen[-1] if faults_seen else None)
        for b in BACKENDS:
            verdicts.update(backend_verdicts(key, b, cres["backends"].get(b) or {"testable": []}, listing_for, n_runs))
    meas = {"runs": n_runs, "quick": ck.quick(ctx), "cameras": per_cam, "arrivals": ck.arrivals_after(ctx, arr0),
            "open_timeouts_s": OPEN_TIMEOUT_S, "call_timeout_ms": CALL_TIMEOUT_MS,
            "segments_s": {"baseline": BASELINE_S, "exposure": SEG_S, "focus": FOCUS_SEG_S, "ae_on": AE_ON_S,
                           "af_on": AF_ON_S},
            "scene_assumptions": wa.SCENE_NOTE,
            "note": "real camera state through wincam controls --api ds (second DirectShow filter instance); frames "
                    "are OpenCV's decoded BGR re-encoded as JPEG q95 by the helper; restore through wincam controls"}
    return results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)


# ------------------------------------------------------------------------------------------------------- offline
def reanalyze(run_dir: Path) -> dict:
    """Re-rate a stored W-OCV-CTRL.json (per-run analyses as stored; rating rules as now). Criterion 1 comes from
    <run_dir>/W-CTRL-LIST.json, else from the listing inputs stored at run time."""
    run_dir = Path(run_dir)
    d = json.loads((run_dir / f"{TEST}.json").read_text(encoding="utf-8"))
    m = d.get("measurements") or {}
    cl = ce.load_ctrl_list(run_dir / "W-CTRL-LIST.json")
    n_runs = m.get("runs") or 3
    out_v, changes = {}, []
    for key, cres in (m.get("cameras") or {}).items():
        for b in BACKENDS:
            brec = (cres.get("backends") or {}).get(b)
            if brec is None:
                continue
            stored = cres.get("listing") or {}
            vv = backend_verdicts(key, b, brec, lambda n, _c=cl.get(key), _s=stored: (
                ce.listing_inputs(_c, n) if _c else (_s.get(n) or ce.listing_inputs(None, n))), n_runs)
            for vk, v in vv.items():
                old = ((d.get("verdicts") or {}).get(vk) or {}).get("rating")
                out_v[vk] = v
                if old != v["rating"]:
                    changes.append({"cell": vk, "from": old, "to": v["rating"]})
    return {"test": TEST, "reanalysis_of": str(run_dir / f"{TEST}.json"), "utc": results.utc_now_iso(),
            "verdicts": out_v, "changes": changes}


def _main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "--reanalyze":
        rd = Path(argv[1])
        out = reanalyze(rd)
        p = results.write_json(rd / "reanalysis" / f"{TEST}.json", out)
        print(json.dumps({"written": str(p), "changes": out["changes"]}, indent=1))
        return 0
    print("usage: w_ocv_ctrl.py --reanalyze <run_dir>   (live runs go through run_suite.py)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
