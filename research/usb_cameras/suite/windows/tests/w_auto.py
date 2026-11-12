"""W-AUTO: turning auto-exposure and autofocus back ON, verified on the image (G-CTRL rows 6 and 8).

Plan docs/capture_stack_options_plan.md section 6.1 (W-AUTO; extends W-CTRL-EFFECT). W-CTRL-EFFECT proved that
auto-exposure (AE) and autofocus (AF) can be turned OFF (a manual value reaches the image). Turning them back ON
was only checked by reading the auto flag back. This test checks it on the image.

Per camera (the Kiyo included) and control path, for each of exposure and focus that the camera supports with both
an auto and a manual mode (a camera without the control, or without its auto mode, is "n/a"):

- ``mf``: sets on the MF source inside the capture process: ``wincam capture --controls-before ... --schedule ...``
  (the same IMFMediaSource that streams; each event records the readback and its QPC time);
- ``ds``: sets through the DirectShow capture filter: ``wincam controls --api ds --set`` in concurrent processes
  (helpers/multi_launch.py, one camera lock) while ``wincam capture`` streams through MF. The frames therefore come
  from the same MJPEG stream on both paths (PyAV's own DirectShow stream falls back to YUY2 below 30 fps on the Kiyo
  at 720p, which is out of the mode scope). What differs between the paths is the control interface: IAMCameraControl
  on the MF source vs on a bound DirectShow filter.

Steps per camera:
1. read the control state (values AND flags) once; it is restored at the end;
2. ``as_found``: a short MF capture with no set: luma and sharpness of the camera as found (the image the restore
   must give back);
3. per path, ``baseline``: auto set before the stream starts (MF: --controls-before; DS: a DS set with the camera
   closed), a BASELINE_S capture; the AE baseline is the median luma and the AF baseline the median sharpness over
   BASE_WIN. The MF baseline also reads the AF lens position at its end (``focus=auto`` re-applied late, its
   before_value), which picks the defocus extreme (below);
4. per path, ``runs`` x 2 captures (one for exposure, one for focus), each with:
   - before-start: ``<c>=<extreme>,<c>=auto`` set before the stream starts (auto switched on with the camera closed
     or not yet streaming, from a manual extreme): the image must reach the band within the recovery time of the
     first frame;
   - ``toggles`` transitions while streaming, the first one >= 4.5 s after the first frame (so the C930e's
     "set >= 1 s after the first frame" rule is met for every transition): manual extreme for HOLD_MS (the image
     must leave the band, otherwise the transition is inconclusive), then auto ON: the image must come back into
     the band within RECOVER_MS and stay there for STAY_MS;
   - exposure extremes are placed relative to AE's own value read in the MF baseline (``exposure=auto`` re-applied
     late, its before_value; the DS path re-uses the MF read): darker = AE - 2 steps, brighter = AE + 2 (or + 1)
     steps capped at the longest exposure the frame interval allows (2**v <= 1/fps in log2 seconds, -5 at 30 fps;
     the range max, -2 = 250 ms, would drop the stream to ~4 fps); the toggles alternate darker / brighter /
     darker, or AE - 2 / AE - 3 / AE - 2 when AE already sits at that cap (or brighter values only when AE sits at
     the range min). A fixed extreme can equal what AE chooses (Gerald 2026-11-06: C930e AE -5 = the 30 fps cap,
     generic AE -7 = the range min) and then never leaves the band. With no AE value read (or a range that is not
     log2 seconds) the extremes fall back to range min / bright / range min. Focus uses the
     range end farther from the AF lens position read in the baseline (the range min, "focus 0", when unknown).
     Gerald 2026-11-06: C922 focus 0 was the SHARPEST position for its scene, so a fixed "focus 0" does not
     defocus every camera;
5. after each path, restore the state read in step 1 (manual controls: value + manual flag; auto controls: the
   original value + the auto flag; so the next path starts from the state as found), verify by a read-only read
   (value within one step for manual controls, auto flag for auto ones); at the end a ``restore_check`` capture is
   compared with ``as_found``.

Bands: luma within +/-15% of the AE baseline within 3 s; sharpness >= 80% of the AF baseline within 5 s. Each
in-stream toggle uses as its reference the auto window (PRE_MS) just before its manual set in the same capture when
that window is conclusive, follows a toggle that did not fail and agrees loosely with the path baseline (AF / AE can
settle at a different level in each capture: smoke 2026-11-09, C922 AF); otherwise the path baseline. Both
references and the recovery against the path baseline are stored per toggle.

Scene assumptions (stated in the result): a static scene under steady light, with texture in the centre of the
frame (sharpness ROI = the centre 50%). Lighting changes or motion during a run move the metrics too. The test does
not fail a camera for its scene: a dark (luma < 30) or bright (> 225) baseline, an unstable baseline (luma CV > 10%
or sharpness CV > 35%), a low-texture centre (AF baseline sharpness < 5e-4) or a manual extreme that did not move
the metric out of the band makes that transition ``inconclusive`` with the reason, and a control with no conclusive
transition rates ``untested (inconclusive)``.

Ratings (verdict keys ``G-CTRL-AUTO|<camera>|<path>-ae`` and ``...-af``):
- yes: every planned transition conclusive and recovered (before start and while streaming), auto flag read back;
- partial: every conclusive in-stream transition recovered, but some were inconclusive, or the before-start switch
  did not reach the image (workaround: turn auto on after the stream has started);
- no: a conclusive in-stream transition did not recover ("flag only" when the auto flag read back anyway), or the
  device did not answer;
- untested: device fault (dead-device gate), no in-scope mode (exactly 720 lines at >= 30 fps), or inconclusive.
Tier 0 only (Dom 2026-11-09): frame content only; UVC metadata and the registry value play no part.

Offline: ``python w_auto.py --reanalyze <run_dir>`` re-analyses the stored per-frame metric timelines
(<run_dir>/W-AUTO/<camera>_<path>.json) with the current thresholds into <run_dir>/reanalysis/W-AUTO.json.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
import suitectx  # noqa: E402
import w_ctrl_effect as ce  # noqa: E402
from common import rating, results  # noqa: E402

TEST = "W-AUTO"
GOAL = "G-CTRL-AUTO"
CONTROLS = ("exposure", "focus")
SHORT = {"exposure": "ae", "focus": "af"}
METRIC = {"exposure": "luma_mean", "focus": "sharpness"}
RECOVER_MS = {"exposure": 3000, "focus": 5000}
HOLD_MS = {"exposure": 2000, "focus": 2500}
MARGIN_MS = 1000            # after each recovery window (stay-in-band evidence, and AE/AF settle before the next)
PRE_MS = 1500               # auto window before the first in-stream toggle (and each toggle's pre-set reference)
PRE_LUMA_TOL = 0.35         # a pre-set reference must look like auto: luma within +/-35% of the path baseline ...
PRE_SHARP_MIN = 0.5         # ... or sharpness >= 50% of it (a manual extreme / unrecovered toggle is far outside)
LUMA_BAND = 0.15
SHARP_FRAC = 0.80
STAY_MS = 500               # the metric must stay in the band this long ...
MIN_STAY_FRAMES = 3         # ... over at least this many saved frames
MANUAL_TAIL = 0.4           # manual-extreme effect: the last 40% of the hold
AE_STEPS = 2                # exposure extremes this many steps (x4 in log2 seconds) from AE's own value
SAVE_EVERY = 2
BASELINE_S = 5.0
BASE_WIN_MS = (2500, 5000)
ASFOUND_S = 4.0
ASFOUND_WIN_MS = (2000, 4000)
DARK_LUMA, BRIGHT_LUMA = 30.0, 225.0
LOW_TEXTURE = 5e-4
UNSTABLE_CV = {"luma_mean": 0.10, "sharpness": 0.35}
DS_LEAD_S = 2.0             # DS path: planned first-frame lead after the launcher starts the capture
SCENE_NOTE = ("The image checks assume a static scene under steady light with texture in the centre of the frame "
              "(sharpness ROI: centre 50%; luma ROI: centre 80%). A dark (luma < 30), bright (> 225) or unstable "
              "baseline, a low-texture centre (AF baseline sharpness < 5e-4), or a manual extreme that does not move "
              "the metric out of the band makes a transition inconclusive, never a failure.")


def runs_per(ctx) -> int:
    return int(ck.arg(ctx, "ctrl_runs", 3, 1))


def toggles_per(ctx) -> int:
    return int(ck.arg(ctx, "auto_toggles", 3, 1))


# ------------------------------------------------------------------------------------------------------- mode
def scoped_720(ctx, advertised: list) -> tuple:
    """The streaming mode: MJPEG with EXACTLY 720 lines at >= the scope's min fps (Dom 2026-11-08), 1280x720@30
    preferred; (None, record) when the camera has none (rated 'untested (scope)'). --all-modes keeps capkit's
    scoped default. A modescope with ``max_height`` (the 2026-11-08 version: exactly 720 by default) decides alone,
    so its --min-height / --max-height flags are honoured; with the older modescope (>= 720 lines) the 720-line
    filter is applied here."""
    mode, scope = ck.scoped_default(ctx, advertised)
    sc = ck.mode_scope(ctx)
    if sc.all_modes:
        return mode, scope
    exact_here = not hasattr(sc, "max_height")
    kept = [m for m in advertised if sc.contains(m.w, m.h, m.fps) and (m.h == 720 or not exact_here)]
    d = ck.default_mode(kept) if kept else None
    scope["rule"] = ("exactly 720 lines and >= min fps (Dom 2026-11-08)" if exact_here
                     else f"common.modescope: {sc.text}")
    scope["in_scope_streaming"] = [m.text for m in kept]
    scope["default_mode"] = d.text if d else None
    if d is None:
        scope["untested_reason"] = scope.get("untested_reason") or (
            f"no MJPEG mode in scope ({'exactly 720 lines at >= ' + format(sc.min_fps, 'g') + ' fps' if exact_here else sc.text}; "
            f"{len(advertised)} advertised)")
    return d, scope


# ------------------------------------------------------------------------------------------------------- plan
def bright_exposure(c: dict, fps: float | None) -> tuple[int, str]:
    """The 'brighter' manual exposure: the longest one the frame interval allows. MF / DirectShow exposure is in
    log2 seconds, so value v is 2**v s; the largest v (on the control's step grid) with 2**v <= 1/fps keeps the
    stream at its rate (the range max, -2 = 250 ms on every Gerald camera, drops it to ~4 fps and leaves too few
    frames in the manual window). A range that is not log2 seconds (min >= 0) or an unknown rate uses 75 % of the
    range, as W-CTRL-EFFECT does."""
    lo, hi = c.get("min"), c.get("max")
    st = c.get("step") or 1
    if lo is None or hi is None:
        return hi, "range max (range incomplete)"
    if lo < 0 and fps and fps > 0:
        v = lo
        while v + st <= hi and 2.0 ** (v + st) <= 1.0 / fps:
            v += st
        return int(v), f"largest log2-seconds value with 2**v <= 1/{fps:g} s (frame interval)"
    q = lo + 0.75 * (hi - lo)
    return int(lo + round((q - lo) / st) * st), "75% of the range (not log2 seconds, or rate unknown)"


def ae_relative_exposures(c: dict, fps: float | None, ae_value) -> tuple[list[int] | None, str]:
    """Exposure extremes AE_STEPS (or more) away from AE's own value, so every toggle can leave the luma band; None
    when the AE value is unknown or the range is not log2 seconds (the caller falls back to fixed points)."""
    lo, hi = c.get("min"), c.get("max")
    st = c.get("step") or 1
    if not isinstance(ae_value, (int, float)) or lo is None or hi is None or lo >= 0:
        return None, "AE value unknown or range not log2 seconds"
    ae = lo + round((ae_value - lo) / st) * st
    cap, _ = bright_exposure(c, fps)
    top = min(hi, cap) if cap is not None else hi

    def away(sign: int, ks: tuple) -> list[int]:
        return [int(ae + sign * k * st) for k in ks if lo <= ae + sign * k * st <= top]

    dark = away(-1, (AE_STEPS, AE_STEPS + 1)) or away(-1, (1,))
    bright = away(1, (AE_STEPS, 1))
    if dark and bright:
        return [dark[0], bright[0], dark[0]], "AE -2 / AE +2 (or +1, capped at the frame interval) / AE -2 steps"
    if dark:
        return [dark[0], dark[-1], dark[0]], "AE at the frame-interval cap or range max: darker values only"
    if bright:
        return [bright[0], bright[-1], bright[0]], "AE at the range min: brighter values only (frame-interval cap)"
    return None, "no value >= 1 step from the AE value within range and frame interval"


def extremes(name: str, c: dict, af_pos=None, fps: float | None = None, ae_value=None) -> tuple[list[int], dict]:
    """Manual extremes for the toggles and how they were chosen. Exposure: relative to AE's own value
    (``ae_value``, read in the baseline) when known, else range min / bright / range min."""
    lo, hi = c.get("min"), c.get("max")
    if name == "exposure":
        bright, why = bright_exposure(c, fps)
        rel, rel_why = ae_relative_exposures(c, fps, ae_value)
        if rel is not None:
            return rel, {"rule": rel_why, "ae_value": ae_value, "bright_cap": bright, "bright_rule": why,
                         "range": [lo, hi], "fps": fps}
        return [lo, bright, lo], {"rule": "range min / bright / min (darker, brighter, darker than auto)",
                                  "ae_relative": rel_why, "ae_value": ae_value, "bright_rule": why,
                                  "range": [lo, hi], "fps": fps}
    if isinstance(af_pos, (int, float)) and lo is not None and hi is not None:
        far = hi if (af_pos - lo) < (hi - af_pos) else lo
        return [far], {"rule": "range end farther from the AF lens position", "af_position": af_pos}
    return [lo], {"rule": "range min ('focus 0'): AF lens position unknown", "af_position": af_pos}


def plan(name: str, vals: list[int], n_toggles: int) -> dict:
    """Timeline in ms after the first frame."""
    rec, hold = RECOVER_MS[name], HOLD_MS[name]
    t = rec + PRE_MS
    tg = []
    for k in range(n_toggles):
        tg.append({"k": k, "manual_ms": t, "auto_ms": t + hold, "value": vals[k % len(vals)]})
        t += hold + rec + MARGIN_MS
    return {"control": name, "before_start_value": vals[0], "before_start_window_ms": rec, "toggles": tg,
            "end_ms": t, "recover_ms": rec, "hold_ms": hold, "margin_ms": MARGIN_MS, "pre_ms": PRE_MS}


def mf_schedule(name: str, p: dict) -> tuple[str, str]:
    """(--controls-before, --schedule) for the MF path."""
    before = f"{name}={p['before_start_value']},{name}=auto"
    items = []
    for t in p["toggles"]:
        items += [f"{t['manual_ms']}:{name}={t['value']}", f"{t['auto_ms']}:{name}=auto"]
    return before, ";".join(items)


# ------------------------------------------------------------------------------------------------------- metrics
def in_band(metric: str, v: float, base: float) -> bool:
    if metric == "luma_mean":
        return abs(v / base - 1.0) <= LUMA_BAND if base else False
    return v >= SHARP_FRAC * base


def recovery_ms(points: list, t_from: float, t_to: float, metric: str, base: float) -> float | None:
    """ms from ``t_from`` to the first saved frame from which the metric stays in the band for STAY_MS (at least
    MIN_STAY_FRAMES frames); frames in [t_from, t_to]. None = never."""
    pts = [(t, v) for t, v in points if t_from <= t <= t_to and v is not None]
    for i, (t, v) in enumerate(pts):
        if not in_band(metric, v, base):
            continue
        stretch = [p for p in pts[i:] if p[0] <= t + STAY_MS]
        if len(stretch) >= MIN_STAY_FRAMES and all(in_band(metric, x, base) for _, x in stretch):
            return round(t - t_from, 1)
    return None


def window_stats(points: list, a: float, b: float) -> dict:
    vals = [v for t, v in points if a <= t < b and v is not None]
    if not vals:
        return {"n": 0, "median": None, "cv": None}
    med = statistics.median(vals)
    cv = (statistics.pstdev(vals) / statistics.fmean(vals)) if len(vals) >= 2 and statistics.fmean(vals) else None
    return {"n": len(vals), "median": med, "cv": None if cv is None else round(cv, 4)}


def baseline_from(points: list, metric: str, win: tuple = BASE_WIN_MS) -> dict:
    """Median of the window and whether the scene allows a verdict (``conclusive`` + ``reason``)."""
    st = window_stats(points, *win)
    st["window_ms"] = list(win)
    v, cv = st["median"], st["cv"]
    why = None
    if v is None or st["n"] < 3:
        why = "too few frames in the baseline window"
    elif metric == "luma_mean" and v < DARK_LUMA:
        why = f"dark scene (baseline luma {v:.1f} < {DARK_LUMA:g})"
    elif metric == "luma_mean" and v > BRIGHT_LUMA:
        why = f"bright scene (baseline luma {v:.1f} > {BRIGHT_LUMA:g})"
    elif metric == "sharpness" and v < LOW_TEXTURE:
        why = f"low-texture scene (AF baseline sharpness {v:.2e} < {LOW_TEXTURE:g})"
    elif cv is not None and cv > UNSTABLE_CV[metric]:
        why = f"unstable baseline ({metric} CV {cv:.2f} > {UNSTABLE_CV[metric]:g}: lighting change, motion or AE/AF hunting)"
    st["conclusive"] = why is None
    st["reason"] = why
    return st


def frame_points(out_dir: Path, mode, metric: str) -> tuple[list, int | None]:
    """([[ms after first frame, metric], ...] of the saved frames, first frame qpc_ns)."""
    rows = ck.load_frames(out_dir)
    if not rows or rows[0].get("qpc_ns") is None:
        return [], None
    t0 = int(rows[0]["qpc_ns"])
    pts = []
    for r, data in ck.saved_frame_bytes(out_dir, rows):
        t = r.get("qpc_ns")
        if t is None:
            continue
        try:
            v = ce.metric_value(data, mode.w, mode.h, metric)
        except Exception:  # noqa: BLE001 - an undecodable frame is skipped
            v = None
        if v is not None:
            pts.append([round((int(t) - t0) / 1e6, 1), round(float(v), 6)])
    return pts, t0


def _ms(t_ns, t0) -> float | None:
    return None if t_ns is None or t0 is None else round((int(t_ns) - int(t0)) / 1e6, 1)


def pre_reference(pts: list, metric: str, man_ms: float, bval: float | None, prev_result: str | None) -> dict:
    """The auto image just before a toggle's manual set, in the SAME capture: the band reference for that toggle's
    recovery. The path baseline comes from a separate capture, and AF / AE can settle at a different level in each
    capture (smoke 2026-11-09: C922 AF sharpness 0.0148 in the baseline capture, 0.0116 before the set and again
    0.0116 after auto ON). Used only when the PRE_MS window is conclusive (baseline_from's scene checks), the
    previous toggle did not fail (its tail would still show the manual extreme) and it agrees loosely with the path
    baseline (it must look like auto, not like a manual extreme): luma within +/-PRE_LUMA_TOL, sharpness >=
    PRE_SHARP_MIN of the baseline."""
    st = baseline_from(pts, metric, (man_ms - PRE_MS, man_ms))
    v = st.get("median")
    why = st.get("reason")
    if why is None and prev_result in ("fail", "unmeasured"):
        why = f"the previous toggle's result is {prev_result}"
    if why is None and bval:
        ratio = v / bval
        loose = abs(ratio - 1.0) <= PRE_LUMA_TOL if metric == "luma_mean" else ratio >= PRE_SHARP_MIN
        st["ratio_vs_baseline"] = round(ratio, 4)
        if not loose:
            why = f"pre-set window {v:.4g} is too far from the path baseline {bval:.4g} to be the auto state"
    st["used"] = why is None
    st["reason"] = why
    return st


def analyse_transitions(cap: dict, base: dict, pre_ref: bool = True) -> dict:
    """Pure analysis of one transitions capture (``cap`` as stored: points, events, plan, control) against the
    path's baseline. Returns {before_start, toggles}. ``pre_ref``: each in-stream toggle is judged against the
    auto window just before its manual set in the same capture when that window qualifies (``pre_reference``),
    else against the path baseline; both references are stored. W-OCV-CTRL passes False (its manual set follows
    other manual sets, and its baseline segment is already in the same capture)."""
    name = cap["control"]
    metric = METRIC[name]
    rec_ms = RECOVER_MS[name]
    pts = cap.get("points") or []
    bval = base.get("median")
    bok = bool(base.get("conclusive"))
    out: dict = {"baseline": bval, "baseline_conclusive": bok, "baseline_reason": base.get("reason")}
    # before start: auto switched on before the first frame (from a manual extreme)
    bs = {"window_ms": rec_ms, "readback": cap.get("before_start_readback")}
    if not pts:
        bs.update(result="unmeasured", reason="no frames")
    elif not bok:
        bs.update(result="inconclusive", reason=base.get("reason"))
    else:
        r = recovery_ms(pts, 0.0, rec_ms + MARGIN_MS, metric, bval)
        bs.update(recovery_ms=r, first_frames=window_stats(pts, 0, 500))
        bs["result"] = "pass" if (r is not None and r <= rec_ms) else "fail"
        if bs["result"] == "fail":
            bs["reason"] = (f"{metric} not within the band {rec_ms} ms after the first frame"
                            + (f" (in band only after {r} ms)" if r is not None else ""))
    out["before_start"] = bs
    tgs = []
    evs = cap.get("events") or []
    prev = None
    for t in cap.get("plan", {}).get("toggles") or []:
        k = t["k"]
        man = next((e for e in evs if e.get("k") == k and e.get("kind") == "manual"), None)
        aut = next((e for e in evs if e.get("k") == k and e.get("kind") == "auto"), None)
        rec: dict = {"k": k, "value": t.get("value"), "manual": man, "auto": aut,
                     "auto_readback_ok": None if aut is None else aut.get("matches"),
                     "manual_readback_ok": None if man is None else man.get("matches")}
        if man is None or aut is None or man.get("t_ms") is None or aut.get("t_ms") is None:
            rec.update(result="unmeasured", reason="a control event is missing (set timed out or capture ended)")
            tgs.append(rec)
            prev = rec["result"]
            continue
        m_end = man.get("t_end_ms") if man.get("t_end_ms") is not None else man["t_ms"]
        a0 = aut["t_ms"]
        tail0 = m_end + (1.0 - MANUAL_TAIL) * max(0.0, a0 - m_end)
        mw = window_stats(pts, tail0, a0)
        rec["manual_window"] = {"from_ms": round(tail0, 1), "to_ms": a0, **mw}
        after = [p for p in pts if a0 <= p[0] <= a0 + rec_ms + MARGIN_MS]
        ref, ref_src = bval, "path baseline"
        if pre_ref and bok:
            pr = pre_reference(pts, metric, man["t_ms"], bval, prev)
            rec["pre_set_window"] = pr
            if pr["used"]:
                ref, ref_src = pr["median"], "pre-set window (same capture)"
        rec["reference"] = {"source": ref_src, "value": ref, "path_baseline": bval}
        if not bok:
            rec.update(result="inconclusive", reason=base.get("reason"))
        elif mw["n"] < 2 or len(after) < MIN_STAY_FRAMES:
            rec.update(result="unmeasured", reason="too few saved frames around the switch")
        elif in_band(metric, mw["median"], ref):
            rec.update(result="inconclusive",
                       reason=(f"the manual extreme {t.get('value')} did not move {metric} out of the band "
                               f"({mw['median']:.4g} vs {ref_src} {ref:.4g})"))
        else:
            r = recovery_ms(pts, a0, a0 + rec_ms + MARGIN_MS, metric, ref)
            rec["recovery_ms"] = r
            rec["result"] = "pass" if (r is not None and r <= rec_ms) else "fail"
            if rec["result"] == "fail":
                rec["reason"] = (f"{metric} not back in the band within {rec_ms} ms of auto ON"
                                 + (f" (only after {r} ms)" if r is not None else ""))
                if aut.get("matches"):
                    rec["flag_only"] = True
            if ref_src != "path baseline":
                # recovery against the path baseline too: AE / AF settling at another level than in the baseline
                # capture (e.g. the C922's AE re-converging ~16% darker) stays visible as a camera property
                rb = recovery_ms(pts, a0, a0 + rec_ms + MARGIN_MS, metric, bval)
                rec["vs_path_baseline"] = {"recovery_ms": rb, "recovered": rb is not None and rb <= rec_ms}
        tgs.append(rec)
        prev = rec["result"]
    out["toggles"] = tgs
    return out


# ------------------------------------------------------------------------------------------------------- events
def mf_events(summary: dict | None, p: dict, first_ns: int | None) -> tuple[list, dict | None]:
    """Schedule records of a wincam capture -> toggle events (ms after the first frame) + before-start readback."""
    s = summary or {}
    name = p["control"]
    out = []
    sched = [e for e in s.get("schedule") or [] if str(e.get("control", "")).endswith(name)]
    for t in p["toggles"]:
        for kind, at in (("manual", t["manual_ms"]), ("auto", t["auto_ms"])):
            e = next((x for x in sched if abs(float(x.get("at_ms") or -1) - at) < 0.5), None)
            if e is None:
                continue
            out.append({"k": t["k"], "kind": kind, "value": t["value"] if kind == "manual" else "auto",
                        "t_ms": _ms(e.get("applied_qpc_ns"), first_ns), "t_end_ms": _ms(e.get("done_qpc_ns"), first_ns),
                        "matches": e.get("matches"), "readback_value": e.get("readback_value"),
                        "readback_flags": e.get("readback_flags"), "before_value": e.get("before_value"),
                        "before_flags": e.get("before_flags"), "timed_out": e.get("timed_out"),
                        "skipped": e.get("skipped")})
    cb = [x for x in s.get("controls_before") or [] if str(x.get("control", "")).endswith(name)]
    bsr = None
    if cb:
        last = cb[-1]
        bsr = {"sets": [{k: x.get(k) for k in ("requested", "matches", "readback_value", "readback_flags")} for x in cb],
               "auto_readback_ok": bool(last.get("requested") == "auto" and last.get("matches"))}
    return out, bsr


def _parse_set(stdout: str, name: str) -> dict:
    sj, _ = suitectx.parse_json_stdout({"stdout": stdout or ""})
    mine = [x for x in (sj or {}).get("sets") or [] if str(x.get("control", "")).endswith(name)]
    last = mine[-1] if mine else {}
    return {"matches": bool(mine) and all(x.get("matches") for x in mine), "readback_value": last.get("readback_value"),
            "readback_flags": last.get("readback_flags"), "before_value": mine[0].get("before_value") if mine else None,
            "before_flags": mine[0].get("before_flags") if mine else None,
            "error": (sj or {}).get("error"), "device_not_answering": (sj or {}).get("device_not_answering")}


def ds_events(launch: dict | None, p: dict, first_ns: int | None) -> list:
    """multi_launch setter records -> toggle events. A DS set happens somewhere inside its process window, so the
    switch time is the process START (recovery times are upper bounds) and the manual window ends after the
    process END."""
    cmds = {c.get("label"): c for c in (launch or {}).get("commands") or []}
    out = []
    for t in p["toggles"]:
        for kind in ("manual", "auto"):
            c = cmds.get(f"{kind}{t['k']}")
            if not c:
                continue
            ps = _parse_set(c.get("stdout") or "", p["control"])
            out.append({"k": t["k"], "kind": kind, "value": t["value"] if kind == "manual" else "auto",
                        "t_ms": _ms(c.get("t_start_ns"), first_ns), "t_end_ms": _ms(c.get("t_end_ns"), first_ns),
                        "rc": c.get("rc"), "timed_out": c.get("timed_out"), **ps})
    return out


# ------------------------------------------------------------------------------------------------------- captures
def capture_points(ctx, cam, mode, od: Path, seconds: float, metric_names: tuple, extra=()) -> dict:
    s, r = ck.wincam_capture(ctx, cam, mode, od, seconds=seconds, save=f"every:{SAVE_EVERY}", extra=list(extra))
    s = s or {}
    rec = {"capture_ok": bool(s.get("ok")), "run": r, "error": s.get("error"), "summary": s,
           "capture_fault": ck.fault_from_result("mf", s, r)}
    for mn in metric_names:
        pts, t0 = frame_points(od, mode, mn)
        rec[f"points_{mn}"] = pts
        rec["first_frame_ns"] = t0
    return rec


def run_baseline(ctx, cam, api: str, mode, od: Path, names: list[str]) -> dict:
    """Auto set before the stream starts, then BASELINE_S of streaming. MF also reads the AF lens position and the
    AE exposure value just after the baseline window (``<c>=auto`` re-applied; its before_value)."""
    pre = None
    extra: list = []
    if api == "mf":
        if names:
            extra += ["--controls-before", ",".join(f"{n}=auto" for n in names)]
            # after the baseline window, so a camera that restarts AE/AF on a redundant auto set cannot bias it
            extra += ["--schedule", ";".join(f"{int(BASELINE_S * 1000 + 100)}:{n}=auto" for n in names)]
    else:
        spec = ",".join(f"{n}=auto" for n in names)
        r = ctx.camcmd(ck.wincam_argv(ctx, "controls", "--api", "ds", "--device", cam["ds_path"], "--set", spec,
                                      "--timeout-ms", 5000), timeout_s=40)
        pre = {"run": ck.run_brief(r), **_parse_set(r.get("stdout") or "", names[0] if names else "")}
    rec = capture_points(ctx, cam, mode, od, BASELINE_S + 0.6, ("luma_mean", "sharpness"), extra)
    s = rec.pop("summary")
    auto_read = {}
    for e in s.get("schedule") or []:
        n = str(e.get("control", "")).split(".")[-1]
        auto_read[n] = {"value_while_auto": e.get("before_value"), "flags": e.get("before_flags")}
    rec["auto_values_read"] = auto_read
    rec["ds_pre_set"] = pre
    rec["luma"] = baseline_from(rec["points_luma_mean"], "luma_mean")
    rec["sharpness"] = baseline_from(rec["points_sharpness"], "sharpness")
    return rec


def run_transitions(ctx, cam, api: str, mode, name: str, p: dict, od: Path) -> dict:
    metric = METRIC[name]
    secs = p["end_ms"] / 1000.0 + 0.3
    if api == "mf":
        before, sched = mf_schedule(name, p)
        s, r = ck.wincam_capture(ctx, cam, mode, od, seconds=secs, save=f"every:{SAVE_EVERY}",
                                 extra=["--controls-before", before, "--schedule", sched])
        s = s or {}
        pts, t0 = frame_points(od, mode, metric)
        evs, bsr = mf_events(s, p, t0)
        return {"control": name, "path": api, "plan": p, "points": pts, "first_frame_ns": t0, "events": evs,
                "before_start_readback": bsr, "capture_ok": bool(s.get("ok")), "frames": len(ck.load_frames(od)),
                "run": r, "error": s.get("error"), "capture_fault": ck.fault_from_result("mf", s, r)}
    # DS: before-start sets through the DS filter with the camera closed, then the launcher
    dev = cam["ds_path"]
    r0 = ctx.camcmd(ck.wincam_argv(ctx, "controls", "--api", "ds", "--device", dev, "--set",
                                   f"{name}={p['before_start_value']},{name}=auto", "--timeout-ms", 5000), timeout_s=40)
    ps0 = _parse_set(r0.get("stdout") or "", name)
    bsr = {"run": ck.run_brief(r0), "auto_readback_ok": ps0["matches"], **ps0}
    cap_secs = secs + DS_LEAD_S
    items = [("capture", ck.wincam_capture_argv(ctx, cam, mode, od, cap_secs, save=f"every:{SAVE_EVERY}"), 0.0,
              cap_secs + 45)]
    for t in p["toggles"]:
        for kind, at, v in (("manual", t["manual_ms"], t["value"]), ("auto", t["auto_ms"], "auto")):
            items.append((f"{kind}{t['k']}", ck.wincam_argv(ctx, "controls", "--api", "ds", "--device", dev, "--set",
                                                          f"{name}={v}", "--timeout-ms", 4000),
                          DS_LEAD_S + at / 1000.0, 25))
    spec = {"commands": [{"label": a, "argv": b, "start_at_s": c, "timeout_s": d} for a, b, c, d in items],
            "snapshots_at_s": []}
    od.mkdir(parents=True, exist_ok=True)
    out, run = ck.multi_launch(ctx, spec, od.parent / f"{od.name}_spec.json", timeout_s=cap_secs + 120)
    cmds = {c.get("label"): c for c in (out or {}).get("commands", [])}
    cs, _ = suitectx.parse_json_stdout({"stdout": (cmds.get("capture") or {}).get("stdout") or ""})
    cs = cs or {}
    pts, t0 = frame_points(od, mode, metric)
    evs = ds_events(out, p, t0)
    # the launcher's argv names no device, so ctx.camcmd's fault scan cannot see the capture child: judge it here
    # (a capture killed at its own timeout, or the whole launcher killed, is a hung camera command)
    cap_timed_out = bool((cmds.get("capture") or {}).get("timed_out") or (run or {}).get("timed_out"))
    return {"control": name, "path": api, "plan": p, "points": pts, "first_frame_ns": t0, "events": evs,
            "before_start_readback": bsr, "capture_ok": bool(cs.get("ok")), "frames": len(ck.load_frames(od)),
            "launcher": run, "error": cs.get("error"),
            "capture_stderr": None if cs else (cmds.get("capture") or {}).get("stderr_tail"),
            "capture_timed_out": cap_timed_out,
            "capture_fault": ck.fault_from_result("mf", cs, {"timed_out": cap_timed_out})}


# ------------------------------------------------------------------------------------------------------- restore
def state_of(tab: dict, names) -> dict:
    return {n: {"value": (tab.get(n) or {}).get("value"), "flags": (tab.get(n) or {}).get("flags"),
                "flags_names": (tab.get(n) or {}).get("flags_names")} for n in names if n in tab}


def restore_state(ctx, cam, api: str, orig: dict, ranges: dict) -> dict:
    """Put back each control's original value AND flag: manual controls -> value with the manual flag; auto
    controls -> the original value with the auto flag (the camera then moves it). Verified by a read-only read:
    manual controls by value (one range step, w_ctrl_effect.step_tol) and the manual flag, auto controls by the
    auto flag (their value is recorded; under auto the camera owns it)."""
    auto = {n: o["value"] for n, o in orig.items() if "auto" in (o.get("flags_names") or []) and o.get("value") is not None}
    manual = {n: o["value"] for n, o in orig.items() if n not in auto and o.get("value") is not None}
    out: dict = {"auto": auto, "manual": manual, "steps": []}
    for sets, flags in ((manual, "manual"), (auto, "auto")):
        if not sets:
            continue
        j, r = ck.set_controls(ctx, cam, api, sets, flags=flags)
        out["steps"].append({"sets": sets, "flags": flags, "run": r,
                             "ok": bool(j) and all(x.get("matches") for x in (j or {}).get("sets", [])),
                             "detail": (j or {}).get("sets")})
    chk, r = ck.get_controls(ctx, cam, api)
    tab = ck.control_table(chk)
    after = state_of(tab, orig)
    by_value, ok = {}, {}
    for n in orig:
        a = after.get(n) or {}
        if n in manual:
            # a control with no auto/manual mode flag at all (e.g. AE priority: flags 0, caps none) can never read
            # back the manual flag: verify it by value only (2026-11-11 smoke: false "restore not verified")
            modeless = not (orig[n].get("flags_names") or []) and not (a.get("flags_names") or [])
            by_value[n] = ce.held(a.get("value"), None if modeless else a.get("flags"), manual[n],
                                  ranges.get(n) or 1)
            ok[n] = by_value[n]
        elif n in auto:
            by_value[n] = None if a.get("value") is None else (a.get("value") == auto[n])
            ok[n] = "auto" in (a.get("flags_names") or [])
        else:
            ok[n] = None
    out.update(after=after, read=ck.run_brief(r), verified_by_value=by_value, verified=ok,
               restored=(all(v is True for v in ok.values()) if chk and ok else None),
               note="manual controls verified by value (one step) + manual flag; auto controls by the auto flag "
                    "(the camera owns the value under auto: verified_by_value is informational there)")
    return out


def restore_verified(ctx, cam, api: str, orig: dict, ranges: dict, errors: list) -> dict:
    rs = restore_state(ctx, cam, api, orig, ranges)
    if rs.get("restored") is not True:
        ctx.log(f"{TEST}: {cam.get('name')} {api}: restore not verified; retrying once")
        time.sleep(2.0)
        rs2 = restore_state(ctx, cam, api, orig, ranges)
        rs2["first_attempt"] = rs
        rs = rs2
        if rs.get("restored") is not True:
            errors.append({"camera": cam["key"], "api": api, "restore_not_verified": rs.get("after"),
                           "wanted": {"auto": rs.get("auto"), "manual": rs.get("manual")}})
    return rs


def image_restore_check(asfound: dict, after: dict) -> dict:
    """The camera's image after the restore vs as found: luma within +/-15%, sharpness ratio within 0.8-1.25.
    Inconclusive when either side has too few frames or the as-found scene is dark / bright / low-texture."""
    out = {}
    for mn, a, b in (("luma_mean", asfound.get("luma") or {}, after.get("luma") or {}),
                     ("sharpness", asfound.get("sharpness") or {}, after.get("sharpness") or {})):
        va, vb = a.get("median"), b.get("median")
        if va is None or vb is None or not va:
            out[mn] = {"ok": None, "reason": "unmeasured"}
            continue
        ratio = vb / va
        ok = abs(ratio - 1.0) <= LUMA_BAND if mn == "luma_mean" else (SHARP_FRAC <= ratio <= 1.0 / SHARP_FRAC)
        out[mn] = {"as_found": va, "after_restore": vb, "ratio": round(ratio, 4),
                   "ok": ok if a.get("conclusive") else None,
                   "reason": None if a.get("conclusive") else a.get("reason")}
    vals = [x.get("ok") for x in out.values()]
    out["ok"] = None if all(v is None for v in vals) else all(v is not False for v in vals)
    return out


# ------------------------------------------------------------------------------------------------------- rating
def rate_auto(name: str, rec: dict, n_runs: int, n_toggles: int, with_before_start: bool = True) -> dict:
    """G-CTRL-AUTO rating of one control on one path (see the module docstring). ``with_before_start`` False:
    no before-start transition was planned (W-OCV-CTRL's auto-on segment); its criterion is left out."""
    if rec.get("gate_verdict"):
        return dict(rec["gate_verdict"])
    if rec.get("scope_verdict"):
        return dict(rec["scope_verdict"])
    if rec.get("na"):
        r = rating.untested(rec["na"], {"control": name})
        r["summary_label"] = "untested (n/a)"
        return r
    if rec.get("device_not_answering"):
        dna = rec["device_not_answering"]
        r = rating._result("no", [rating._crit("auto mode can be switched on", False, dna)], {"control": name, **dna},
                           f"cannot set: device not answering ({dna.get('hr')})")
        r["summary_label"] = "no (device not answering)"
        return r
    runs = rec.get("runs") or []
    tg = [t for r in runs for t in (r.get("analysis") or {}).get("toggles") or []]
    bs = [(r.get("analysis") or {}).get("before_start") or {} for r in runs] if with_before_start else []
    concl = [t for t in tg if t.get("result") in ("pass", "fail")]
    fails = [t for t in concl if t["result"] == "fail"]
    bs_c = [b for b in bs if b.get("result") in ("pass", "fail")]
    bs_fail = [b for b in bs_c if b["result"] == "fail"]
    rb = [t.get("auto_readback_ok") for t in tg] + ([(r.get("before_start_readback") or {}).get("auto_readback_ok")
                                                    for r in runs] if with_before_start else [])
    rb_known = [x for x in rb if x is not None]
    crit = [rating._crit("auto flag set and read back at every switch", (all(rb_known) if rb_known else None),
                         {"n": len(rb_known), "failed": sum(1 for x in rb_known if not x)}),
            rating._crit(f"image recovers after auto ON while streaming ({'luma +/-15% of baseline within 3 s' if name == 'exposure' else 'sharpness >= 80% of the AF baseline within 5 s'})",
                         None if not concl else not fails,
                         {"conclusive": len(concl), "failed": len(fails),
                          "recovery_ms": [t.get("recovery_ms") for t in concl]}),
            rating._crit("auto switched on before the stream starts reaches the image",
                         None if not bs_c else not bs_fail,
                         {"conclusive": len(bs_c), "failed": len(bs_fail),
                          "recovery_ms": [b.get("recovery_ms") for b in bs_c]}),
            rating._crit(f"{n_toggles} in-stream toggles x {n_runs} runs{' (+ before start)' if with_before_start else ''}"
                         " all conclusive",
                         len(concl) == n_toggles * n_runs and len(tg) == n_toggles * n_runs
                         and (len(bs_c) == n_runs or not with_before_start) and len(runs) == n_runs,
                         {"toggles_conclusive": len(concl), "toggles_planned": n_toggles * n_runs,
                          "before_start_conclusive": len(bs_c), "runs": len(runs),
                          "inconclusive_reasons": sorted({str(t.get("reason")) for t in tg + bs
                                                          if t.get("result") in ("inconclusive", "unmeasured")})})]
    if not with_before_start:
        crit = [c for c in crit if "before the stream starts" not in c["criterion"]]
    ev = {"control": name, "baseline": rec.get("baseline"), "first_toggle_ms_after_first_frame":
          (plan(name, [0], 1)["toggles"][0]["manual_ms"])}
    if fails:
        flag_only = all(t.get("flag_only") for t in fails)
        r = rating._result("no", crit, ev, "auto flag reads back but the image did not recover" if flag_only
                           else "the image did not recover after auto ON")
        r["summary_label"] = "no (flag only)" if flag_only else "no (no recovery)"
        return r
    if not concl and not bs_c:
        reasons = crit[-1]["detail"]["inconclusive_reasons"]
        r = rating.untested("inconclusive: " + "; ".join(reasons)[:300], ev)
        r["criteria"] = crit
        r["summary_label"] = "untested (inconclusive)"
        return r
    if bs_fail and concl:
        r = rating._result("partial", crit, ev, "workaround: turn auto on after the stream has started (an auto "
                                                "switch made before the stream starts did not reach the image)")
        r["workaround"] = "turn auto on after the stream has started"
        return r
    if all(c["met"] is True for c in crit):
        return rating._result("yes", crit, ev)
    return rating._result("partial", crit, ev, "some transitions inconclusive or unmeasured (see criteria)")


# ------------------------------------------------------------------------------------------------------- run
def estimate_s(ctx) -> float:
    r, k = runs_per(ctx), toggles_per(ctx)
    per_ctrl = {n: (RECOVER_MS[n] + PRE_MS + k * (HOLD_MS[n] + RECOVER_MS[n] + MARGIN_MS)) / 1000.0 + 9 for n in CONTROLS}
    per_path = BASELINE_S + 8 + r * sum(per_ctrl.values()) + 12
    return len(ctx.cameras) * (2 * per_path + 2 * (ASFOUND_S + 6) + 8)


def _capture_fault(ctx, cam, rec: dict, mode_text: str | None = None) -> dict | None:
    """The camera's device fault after a capture: the suite gate's record, else a fault in the capture itself
    (capkit.fault_from_result: 0x8007001F, an unreleasable reader, abandoned threads, a killed capture), which is then
    reported to the suite gate (the DS path's capture runs under multi_launch, out of reach of ctx.camcmd's scan)."""
    f = ce.gate_fault(ctx, cam, gated_only=False)
    if f:
        return f
    flt = rec.get("capture_fault")
    err = rec.get("error") or {}
    if not flt and err.get("class") == "device_error":
        flt = {"kind": "device_error", "code": err.get("hr"), "stage": err.get("stage"),
               "reason": "capture reported device_error"}
    if not flt:
        return None
    marked = ck.mark_device_fault(ctx, cam, TEST, mode_text, "mf", flt) or {}
    return {"utc": marked.get("utc") or results.utc_now_iso(), "test": marked.get("test") or TEST,
            "mode": marked.get("mode") or mode_text, "code": marked.get("code") or flt.get("code"),
            "kind": marked.get("kind") or flt.get("kind"), "stage": flt.get("stage"), "reason": flt.get("reason")}


def run(ctx) -> dict:
    res = ck.new_result(ctx, TEST)
    arr0 = ck.arrivals_before(ctx)
    n_runs, n_tg = runs_per(ctx), toggles_per(ctx)
    errors: list = []
    verdicts: dict = {}
    per_cam: dict = {}
    fcache: dict = {}
    raw = Path(ctx.raw_dir) / TEST
    tdir = ctx.test_dir(TEST)
    for cam in ctx.cameras:
        slug = ck.cam_slug(cam)
        cres: dict = {"name": cam.get("name"), "is_kiyo": cam.get("is_kiyo"), "paths": {}}
        per_cam[cam["key"]] = cres
        paths = [a for a in ("mf", "ds") if (cam.get("mf_symlink") if a == "mf" else cam.get("ds_path"))]
        gf = ce.gate_fault(ctx, cam)
        if gf:
            gv = ce.gate_untested(ctx, cam, gf)
            for api in paths:
                for n in CONTROLS:
                    verdicts[f"{GOAL}|{cam['key']}|{api}-{SHORT[n]}"] = dict(gv)
            cres["gate_fault"] = gf
            ctx.log(f"{TEST}: {cam.get('name')}: skipped, device fault since {gf.get('utc')}")
            continue
        fm, fread = ck.formats_checked(ctx, cam, fcache, TEST)
        if fread:
            # format read failed (not a scope exclusion); a hang / 0x8007001F is a device fault via the probe
            cres["format_read"] = fread
            fv = ck.format_failed_untested(fread)
            for api in paths:
                for n in CONTROLS:
                    verdicts[f"{GOAL}|{cam['key']}|{api}-{SHORT[n]}"] = dict(fv)
            ctx.log(f"{TEST}: {cam.get('name')}: {fread['untested_reason']}")
            continue
        mode, scope = scoped_720(ctx, ck.mjpeg_modes(fm))
        cres["mode"], cres["mode_scope"] = (mode.text if mode else None), scope
        if mode is None:
            sv = ck.scope_untested(ctx, scope)
            for api in paths:
                for n in CONTROLS:
                    verdicts[f"{GOAL}|{cam['key']}|{api}-{SHORT[n]}"] = dict(sv)
            continue
        api0 = paths[0] if paths else None
        if api0 is None or not cam.get("mf_symlink"):
            # both paths read the image from an MF capture
            why = "no MF symlink: the image is read from an MF capture on both paths"
            errors.append({"camera": cam["key"], "error": why})
            for api in paths:
                for n in CONTROLS:
                    verdicts[f"{GOAL}|{cam['key']}|{api}-{SHORT[n]}"] = rating.untested(why)
            continue
        initial, run0 = ck.get_controls(ctx, cam, api0)
        cres["initial_read"] = run0
        na, hr = ce.not_answering(initial, run0)
        if na:
            dna = {"hr": hr, "utc": results.utc_now_iso(), "api": api0, "at": "initial_read"}
            cres["device_not_answering"] = dna
            ce.gate_report(ctx, cam, mode.text, hr, f"{api0} control GETs failed", api0)
            for api in paths:
                for n in CONTROLS:
                    verdicts[f"{GOAL}|{cam['key']}|{api}-{SHORT[n]}"] = rate_auto(n, {"device_not_answering": dna}, n_runs, n_tg)
            continue
        tab = ck.control_table(initial)
        ranges = {n: {k: (tab.get(n) or {}).get(k) for k in ("min", "max", "step", "default")} for n in CONTROLS}
        cres["ranges"] = ranges
        testable, na_why = [], {}
        for n in CONTROLS:
            c = tab.get(n)
            flags = (c or {}).get("caps_flags_names") or []
            if c is None:
                na_why[n] = f"n/a: the camera has no {n} control"
            elif not ce.control_answered(c):
                na_why[n] = f"device did not answer the {n} GET ({ce._get_hr(c)})"
            elif not ("auto" in flags and "manual" in flags) or c.get("min") is None or c.get("max") is None \
                    or c["max"] <= c["min"]:
                na_why[n] = f"n/a: {n} has no auto + manual mode (caps {flags}, range {c.get('min')}..{c.get('max')})"
            else:
                testable.append(n)
        orig = state_of(tab, testable)
        cres["original_state"] = orig
        cres["n_a"] = na_why
        detail_paths: dict = {}
        dead = None
        try:
            if testable:
                af0 = capture_points(ctx, cam, mode, raw / slug / "as_found", ASFOUND_S + 0.3, ("luma_mean", "sharpness"))
                af0.pop("summary", None)
                cres["as_found"] = {"capture_ok": af0["capture_ok"], "error": af0.get("error"),
                                    "luma": baseline_from(af0["points_luma_mean"], "luma_mean", ASFOUND_WIN_MS),
                                    "sharpness": baseline_from(af0["points_sharpness"], "sharpness", ASFOUND_WIN_MS)}
                dead = _capture_fault(ctx, cam, af0, mode.text)
            af_pos = ae_val = None
            for api in paths:
                pres: dict = {"controls": {}}
                cres["paths"][api] = pres
                det: dict = {"camera": cam["key"], "path": api, "mode": mode.text, "baseline": None, "captures": []}
                detail_paths[api] = det
                for n in CONTROLS:
                    if n in na_why:
                        pres["controls"][n] = {"na": na_why[n]}
                if not testable:
                    continue
                if dead:
                    for n in testable:
                        pres["controls"][n] = {"gate_verdict": rating.device_fault_untested(dead)}
                    continue
                base = run_baseline(ctx, cam, api, mode, raw / slug / f"{api}_baseline", testable)
                det["baseline"] = {"points_luma_mean": base["points_luma_mean"],
                                   "points_sharpness": base["points_sharpness"]}
                pres["baseline"] = {k: base.get(k) for k in ("capture_ok", "error", "luma", "sharpness",
                                                              "auto_values_read", "ds_pre_set", "run")}
                if api == "mf" or af_pos is None:
                    af_pos = (base.get("auto_values_read", {}).get("focus") or {}).get("value_while_auto", af_pos)
                    ae_read = (base.get("auto_values_read", {}).get("exposure") or {}).get("value_while_auto")
                    ae_val = ae_read if ae_read is not None else ae_val
                dead = _capture_fault(ctx, cam, base, mode.text)
                for n in testable:
                    if dead:
                        pres["controls"][n] = {"gate_verdict": rating.device_fault_untested(dead)}
                        continue
                    vals, why = extremes(n, tab[n], af_pos if n == "focus" else None, fps=mode.fps,
                                         ae_value=ae_val if n == "exposure" else None)
                    p = plan(n, vals, n_tg)
                    bkey = "luma" if n == "exposure" else "sharpness"
                    crec: dict = {"baseline": base[bkey], "extremes": vals, "extreme_rule": why, "plan": p, "runs": []}
                    pres["controls"][n] = crec
                    for k in range(n_runs):
                        od = raw / slug / f"{api}_{n}_r{k}"
                        try:
                            cap = run_transitions(ctx, cam, api, mode, n, p, od)
                        except Exception as e:  # noqa: BLE001
                            cap = {"control": n, "path": api, "plan": p, "points": [], "events": [],
                                   "exception": repr(e)}
                            errors.append({"camera": cam["key"], "api": api, "control": n, "exception": repr(e)})
                        cap["run_index"] = k
                        det["captures"].append({kk: cap.get(kk) for kk in ("control", "run_index", "plan", "points",
                                                                           "events", "before_start_readback",
                                                                           "first_frame_ns")})
                        ana = analyse_transitions(cap, base[bkey])
                        crec["runs"].append({"run_index": k, "capture_ok": cap.get("capture_ok"),
                                             "frames": cap.get("frames"), "error": cap.get("error"),
                                             "exception": cap.get("exception"),
                                             "before_start_readback": cap.get("before_start_readback"),
                                             "analysis": ana, "run": cap.get("run") or cap.get("launcher")})
                        ctx.log(f"{TEST}: {cam.get('name')} {api} {n} run {k}: before-start "
                                f"{ana['before_start'].get('result')} toggles "
                                f"{[t.get('result') for t in ana['toggles']]} recovery "
                                f"{[t.get('recovery_ms') for t in ana['toggles']]}")
                        dead = _capture_fault(ctx, cam, cap, mode.text)
                        if dead:
                            ctx.log(f"{TEST}: {cam.get('name')}: device fault during {api} {n} run {k}; "
                                    "remaining work on this camera skipped")
                            break
                # each path ends with the state as found, so the next path's baseline starts from it too
                if not dead:
                    pres["restore"] = restore_verified(ctx, cam, api, orig, ranges, errors)
        finally:
            if testable and not dead:
                for api in paths:      # only after an exception: every finished path restored itself
                    if "restore" in (cres["paths"].get(api) or {}):
                        continue
                    try:
                        cres["paths"].setdefault(api, {"controls": {}})["restore"] = restore_verified(
                            ctx, cam, api, orig, ranges, errors)
                    except Exception as e:  # noqa: BLE001
                        errors.append({"camera": cam["key"], "api": api, "restore_exception": repr(e)})
                try:
                    rc = capture_points(ctx, cam, mode, raw / slug / "restore_check", ASFOUND_S + 0.3,
                                        ("luma_mean", "sharpness"))
                    rc.pop("summary", None)
                    after = {"luma": baseline_from(rc["points_luma_mean"], "luma_mean", ASFOUND_WIN_MS),
                             "sharpness": baseline_from(rc["points_sharpness"], "sharpness", ASFOUND_WIN_MS)}
                    cres["restore_image_check"] = {"capture_ok": rc["capture_ok"], **image_restore_check(
                        cres.get("as_found") or {}, after)}
                except Exception as e:  # noqa: BLE001
                    errors.append({"camera": cam["key"], "restore_check_exception": repr(e)})
            elif testable and dead:
                cres["restore"] = {"skipped": f"device fault since {dead.get('utc')}", "restored": None}
            for api, det in detail_paths.items():
                p = results.write_json(tdir / f"{slug}_{api}.json", det)
                cres["paths"].setdefault(api, {"controls": {}})["detail_file"] = \
                    str(p.relative_to(ctx.out_dir)).replace("\\", "/")
        if dead:
            cres["device_fault"] = dead
        for api in paths:
            pres = cres["paths"].get(api) or {"controls": {}}
            for n in CONTROLS:
                crec = pres["controls"].get(n)
                if not crec:
                    crec = {"gate_verdict": rating.device_fault_untested(dead)} if dead else \
                        {"na": na_why.get(n, "not run")}
                v = rate_auto(n, crec, n_runs, n_tg)
                v["restore"] = (pres.get("restore") or {}).get("restored")
                v["restore_image_ok"] = (cres.get("restore_image_check") or {}).get("ok")
                verdicts[f"{GOAL}|{cam['key']}|{api}-{SHORT[n]}"] = v
    meas = {"runs": n_runs, "toggles_per_run": n_tg, "quick": ck.quick(ctx), "save_every": SAVE_EVERY,
            "cameras": per_cam, "arrivals": ck.arrivals_after(ctx, arr0), "scene_assumptions": SCENE_NOTE,
            "thresholds": {"luma_band": LUMA_BAND, "sharpness_fraction": SHARP_FRAC, "recover_ms": RECOVER_MS,
                           "hold_ms": HOLD_MS, "stay_ms": STAY_MS, "min_stay_frames": MIN_STAY_FRAMES,
                           "dark_luma": DARK_LUMA, "bright_luma": BRIGHT_LUMA, "low_texture": LOW_TEXTURE,
                           "unstable_cv": UNSTABLE_CV, "baseline_window_ms": BASE_WIN_MS},
            "paths": {"mf": "wincam capture --controls-before / --schedule (sets on the streaming MF source)",
                      "ds": "wincam controls --api ds in concurrent processes (DirectShow filter) while wincam "
                            "capture streams through MF; switch time = setter process start (upper bound)"},
            "first_in_stream_switch_ms_after_first_frame": {n: RECOVER_MS[n] + PRE_MS for n in CONTROLS},
            "c930e_note": "every in-stream switch is >= 4.5 s after the first frame, so the C930e rule (sets made "
                          ">= 1 s after the first frame work; it resets exposure at stream start) holds for every "
                          "toggle; the before-start transition shows whether an auto switch made before the start "
                          "survives it"}
    return results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)


# ------------------------------------------------------------------------------------------------------- offline
def reanalyze(run_dir: Path) -> dict:
    """Re-analyse the stored timelines (<run_dir>/W-AUTO/<slug>_<path>.json) with the current thresholds."""
    run_dir = Path(run_dir)
    d = json.loads((run_dir / f"{TEST}.json").read_text(encoding="utf-8"))
    m = d.get("measurements") or {}
    n_runs, n_tg = m.get("runs") or 3, m.get("toggles_per_run") or 3
    out_v, changes = {}, []
    for key, cres in (m.get("cameras") or {}).items():
        for api, pres in (cres.get("paths") or {}).items():
            det = None
            if pres.get("detail_file"):
                try:
                    det = json.loads((run_dir / pres["detail_file"]).read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    det = None
            ctrls = json.loads(json.dumps(pres.get("controls") or {}))
            if det and det.get("baseline"):
                bl = det["baseline"]
                bases = {"exposure": baseline_from(bl.get("points_luma_mean") or [], "luma_mean"),
                         "focus": baseline_from(bl.get("points_sharpness") or [], "sharpness")}
                for n, crec in ctrls.items():
                    if "runs" not in crec:
                        continue
                    crec["baseline"] = bases[n]
                    caps = [c for c in det.get("captures") or [] if c.get("control") == n]
                    for r in crec["runs"]:
                        cap = next((c for c in caps if c.get("run_index") == r.get("run_index")), None)
                        if cap:
                            r["analysis"] = analyse_transitions(cap, bases[n])
            for n in CONTROLS:
                vk = f"{GOAL}|{key}|{api}-{SHORT[n]}"
                v = rate_auto(n, ctrls.get(n) or {"na": "not run"}, n_runs, n_tg)
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
    print("usage: w_auto.py --reanalyze <run_dir>   (live runs go through run_suite.py)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
