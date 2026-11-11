"""M-CTRL-EFFECT: set -> readback -> effect in the image, before vs after stream start, restore (plan 6.2
CTRL-EFFECT; macos.md MX4).

Path A, AVFoundation (always): the only macOS controls are modes (exposure/focus/WB locked vs auto). A capture
switches each supported mode at fixed times and records the readback; image metrics are logged so a frozen
exposure can be seen, but no absolute value exists to test an effect against.
Path B, endpoint 0 (only with --ep0): one capture per run with an ep0 schedule: AE manual, three exposure values
(luma), three gain values (luma), WB auto off + three temperatures (R/B), focus auto off + three positions
(sharpness), each auto mode restored. A second short capture sets exposure BEFORE the session starts and reads it
back after the first frame (does Apple's UVC extension overwrite controls at stream start?). Every touched
control is put back to its value from before the test, in a finally block.
Metrics come from the JPEG bytes when AVFoundation delivers them, else from the CVPixelBuffer (420v/2vuy/...).

G-CTRL criterion 1 (common/rating.py rate_ctrl contract): ``listed`` and ``range_matches_descriptor`` come from
M-CTRL-LIST's per_control (ctx.store, else <out_dir>/m_ctrl_list.json), with the macOS reading given in
tests/m_ctrl_list.py; without an M-CTRL-LIST result, from this test's own reads (source recorded). An AVFoundation
lock that neither AVFoundation supports nor the descriptor advertises is not a control of that camera and is left
out of the rating.
Mode scope (plan 6): MJPEG 1280x720@30, else the nearest in-scope MJPEG mode; none -> untested (scope)."""
from __future__ import annotations

import json

import suitectx
import macanalysis
import mac_modescope
from common import rating, results

NAME = "M-CTRL-EFFECT"
RESTORE_ORDER = ("gain", "exposure_time_absolute", "auto_exposure_mode", "white_balance_temperature",
                 "white_balance_temperature_auto", "focus_absolute", "focus_auto")


def ctrl_list_per_control(ctx, cam: dict) -> tuple[dict | None, str]:
    """M-CTRL-LIST's per_control record for this camera: ctx.store, else the result file in out_dir."""
    pc = (ctx.store.get("ctrl_list_per_control") or {}).get(cam["key"])
    if pc is not None:
        return pc, "M-CTRL-LIST per_control (this run)"
    for name in ("m_ctrl_list.json", "m-ctrl-list.json"):
        p = ctx.out_dir / name
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            for c in (d.get("measurements") or {}).get("cameras") or []:
                if c.get("key") == cam["key"] and c.get("per_control"):
                    return c["per_control"], f"M-CTRL-LIST per_control ({name})"
    return None, "no M-CTRL-LIST result"


def own_per_control(ctx, cam: dict, flags: dict | None, ep0_rows: list[dict] | None) -> dict:
    """Fallback listing inputs from this test's own reads (descriptor from the cache when known)."""
    ctrl_list = _ctrl_list_module()
    desc = ctx.cam_desc(cam) or {}
    return ctrl_list.per_control_record(flags, ep0_rows, ctrl_list.descriptor_controls(desc.get("entities")))


def _ctrl_list_module():
    """tests/m_ctrl_list.py, loaded by path under the runner's module name (run_suite.load_test_module)."""
    import importlib.util
    import sys
    from pathlib import Path
    name = "skellycam_macos_suite_m_ctrl_list"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / "m_ctrl_list.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def listing_inputs(pc: dict | None, path: str, name: str, source: str) -> dict | None:
    """{listed, range_matches_descriptor, listing_source} for one rating row; None = leave the row out (an AVF lock
    neither supported nor advertised)."""
    if pc is None:
        return {"listed": None, "range_matches_descriptor": None, "listing_source": source}
    if path == "avf":
        a = (pc.get("avf") or {}).get(name) or {}
        if a.get("listed") is not True and a.get("advertised_in_descriptor") is not True:
            return None
        return {"listed": a.get("listed"), "range_matches_descriptor": a.get("range_matches_descriptor"),
                "listing_source": source, "descriptor_control": a.get("descriptor_control"),
                "advertised_in_descriptor": a.get("advertised_in_descriptor")}
    e0 = pc.get("ep0")
    if e0 is None:
        return {"listed": None, "range_matches_descriptor": None,
                "listing_source": source + " (ep0 not run in M-CTRL-LIST)"}
    r = e0.get(name)
    if r is None:
        return {"listed": False, "range_matches_descriptor": None, "listing_source": source + " (not listed)"}
    return {"listed": r.get("listed"), "range_matches_descriptor": r.get("range_matches_descriptor"),
            "listing_source": source}


def plan(ctx) -> list[str]:
    out = [mac_modescope.text(ctx.args), f"per camera x {ctx.args.ctrl_runs} run(s): AVF mode schedule capture (exposure/WB/focus locked<->auto, "
           "metrics every 2nd frame)",
           "finally: mac_avf.py ctrl-avf --set-modes <original exposure/WB/focus modes> (restore)"]
    if ctx.ep0_enabled:
        out += ["per camera x run: ep0 schedule capture (exposure x3, gain x3, WB x3, focus x3; autos restored)",
                "per camera: controls-before capture (exposure set before start, read back after first frame), then "
                "GET_CUR with no session (persistence across close)",
                "finally: mac_ep0.py set --set <initial values> (restore)"]
    else:
        out += ["ep0 off: absolute exposure/gain/WB/focus not testable on macOS without --ep0"]
    return out


def avf_schedule(flags: dict) -> str:
    parts = []
    t = 1500
    for key, which in (("exposure_modes_supported", "exposure"), ("wb_modes_supported", "wb"),
                       ("focus_modes_supported", "focus")):
        sup = flags.get(key) or {}
        if sup.get("locked") is True:
            parts.append(f"{t}:avf:{which}=locked")
            t += 2000
            back = "auto" if any(sup.get(n) is True for n in sup if n.startswith("continuous")) else "once"
            parts.append(f"{t}:avf:{which}={back}")
            t += 1500
    return ";".join(parts)


def restore_avf_modes(ctx, cam: dict, flags: dict, errors: list) -> dict | None:
    """Set exposure/WB/focus back to the modes read before the test (AVCaptureDevice exposureMode etc.)."""
    orig = {"exposure": flags.get("exposureMode"), "wb": flags.get("whiteBalanceMode"), "focus": flags.get("focusMode")}
    spec = ",".join(f"{k}={int(v)}" for k, v in orig.items() if isinstance(v, (int, float)) and not isinstance(v, bool))
    if not spec:
        return {"skipped": "original modes unknown", "orig": orig}
    r = ctx.avf(["ctrl-avf", "--device", cam["unique_id"], "--set-modes", spec], 30, label=f"ctrl avf restore {cam['key']}")
    j = r.get("json") or {}
    out = {"set": spec, "ok": j.get("ok"), "timed_out": r.get("timed_out"), "results": j.get("set_modes")}
    if not j.get("ok"):
        errors.append({"camera": cam["key"], "warning": "restoring the AVFoundation exposure/WB/focus modes failed",
                       "detail": out})
    return out


def run(ctx) -> dict:
    res = ctx.new_result(NAME)
    errors: list = []
    per = []
    controls_for_rating: list[dict] = []
    for cam in ctx.openable():
        mode, minfo = suitectx.pick_scoped_default(cam, ctx.args)
        crec: dict = {"key": cam["key"], "is_kiyo": cam.get("is_kiyo"), "mode": mode, "mode_choice": minfo,
                      "avf_runs": [], "ep0_runs": []}
        if not mode:
            crec["untested"] = "scope"
            crec["error"] = f"{minfo['why']}: untested (scope)"
            per.append(crec)
            continue
        pc, pc_src = ctrl_list_per_control(ctx, cam)
        fl = ctx.avf(["ctrl-avf", "--device", cam["unique_id"]], 30, label=f"ctrl-avf {cam['key']}")
        flags = ((fl.get("json") or {}).get("flags")) or {}
        crec["avf_flags"] = flags
        sched = avf_schedule(flags)
        avf_ok_runs = 0
        try:
            for run_i in range(ctx.args.ctrl_runs):
                if not sched:
                    break
                od = ctx.subdir("ctrl_effect", f"{suitectx.cam_tag(cam)}", f"avf_run{run_i}")
                r = ctx.avf(["capture", "--device", cam["unique_id"], "--seconds", 12, "--jpeg-check", "none",
                             "--metrics-every", 2, "--schedule", sched, "--out-dir", od] + suitectx.avf_mode_args(mode),
                            60, label=f"ctrl avf {cam['key']} {run_i}")
                j = r.get("json") or {}
                evs = j.get("schedule_events") or []
                ok = bool(evs) and all((e.get("result") or {}).get("readback_matches") for e in evs)
                avf_ok_runs += int(ok)
                crec["avf_runs"].append({"run": run_i, "frames": j.get("frames"), "events": evs, "all_readback_ok": ok,
                                         "timed_out": r.get("timed_out")})
        finally:
            # a killed / timed-out capture can leave a mode locked: put the original modes back explicitly
            crec["avf_restore"] = restore_avf_modes(ctx, cam, flags, errors) if sched else None
        if pc is None:
            pc = own_per_control(ctx, cam, flags or None, None)
            pc_src = "M-CTRL-EFFECT own reads (no M-CTRL-LIST result)"
        crec["listing_source"] = pc_src
        for which in ("exposure", "wb", "focus"):
            sup = (flags.get(f"{which}_modes_supported") or {}).get("locked")
            li = listing_inputs(pc, "avf", which, pc_src)
            if li is None:
                continue  # neither AVFoundation nor the descriptor offers this lock: not a control of this camera
            controls_for_rating.append({"name": f"avf_{which}_lock", "camera": cam["key"], **li,
                                        "set_readback_ok": (avf_ok_runs == len(crec["avf_runs"]) and avf_ok_runs > 0)
                                        if sup is True else None, "effect_ok": None,
                                        "runs_ok": avf_ok_runs if sup is True else 0,
                                        "runs_total": len(crec["avf_runs"]) if sup is True else 0,
                                        "workaround": None})
        if ctx.ep0_enabled:
            controls_for_rating += ep0_part(ctx, cam, mode, crec, errors, pc, pc_src)
        per.append(crec)
    m = {"cameras": per, "edge_light_confirmed_off": bool(ctx.args.edge_light_off),
         "mode_scope": suitectx.scope_for_test(ctx.openable(), ctx.args)}
    v = {"G-CTRL": rating.rate_ctrl(controls_for_rating, runs_required=3)}
    v["G-CTRL"]["tier"] = 0
    v["G-CTRL"]["mode_scope"] = mac_modescope.text(ctx.args)
    v["G-CTRL"]["criterion1_source"] = sorted({c.get("listing_source") for c in controls_for_rating
                                               if c.get("listing_source")})
    v["G-CTRL"]["note_macos"] = ("AVFoundation offers only locked/auto modes on macOS; absolute values need the "
                                 "endpoint-0 path" + ("" if ctx.ep0_enabled else " (not run: --ep0 off)"))
    return results.finish_result(res, m, v, errors)


def ep0_part(ctx, cam: dict, mode: dict, crec: dict, errors: list, listing: dict | None = None,
             listing_src: str = "no M-CTRL-LIST result") -> list[dict]:
    ranges = ctx.store.get("ctrl_list", {}).get(cam["key"])
    if ranges is None:
        c = ctx.ep0(cam, "ctrl-list", timeout_s=90)
        rows = (c.get("json") or {}).get("controls") or []
        ranges = {x["name"]: {k: x.get(k) for k in ("min", "max", "res", "def", "cur", "info", "modes_supported", "ok")}
                  for x in rows if x.get("ok")}
        if listing is None or listing.get("ep0") is None:
            listing = own_per_control(ctx, cam, crec.get("avf_flags") or None, rows)
            listing_src = "M-CTRL-EFFECT own ep0 ctrl-list (no M-CTRL-LIST ep0 result)"
    crec["ep0_ranges"] = ranges
    if not ranges:
        crec["ep0_error"] = "no readable UVC control (ep0 failed or none advertised)"
        return []
    names = [n for n in RESTORE_ORDER if n in ranges]
    g = ctx.ep0(cam, "get", ["--controls", ",".join(names)], timeout_s=30)
    initial = {v["name"]: v["value"] for v in (g.get("json") or {}).get("values") or [] if v.get("ok")}
    crec["ep0_initial"] = dict(initial)
    # a control whose GET_CUR failed just now still gets restored: fall back to the CUR read by M-CTRL-LIST
    fallback = {n: ranges[n].get("cur") for n in names if n not in initial and isinstance(ranges[n].get("cur"), int)}
    if fallback:
        crec["ep0_initial_fallback_from_ctrl_list"] = fallback
        initial.update(fallback)
    schedule, groups, total_ms = macanalysis.build_effect_schedule(ranges, initial)
    crec["ep0_schedule"] = schedule
    out: list[dict] = []
    per_ctrl: dict[str, dict] = {}
    try:
        for run_i in range(ctx.args.ctrl_runs):
            od = ctx.subdir("ctrl_effect", f"{suitectx.cam_tag(cam)}", f"ep0_run{run_i}")
            secs = total_ms / 1000.0 + 2.0
            r = ctx.avf(["capture", "--device", cam["unique_id"], "--seconds", f"{secs:.1f}", "--jpeg-check", "none",
                         "--metrics-every", 2, "--schedule", schedule, "--out-dir", od]
                        + suitectx.avf_mode_args(mode) + ctx.ep0_capture_args(cam), secs + 60,
                        label=f"ctrl ep0 {cam['key']} {run_i}")
            j = r.get("json") or {}
            rows = results.read_jsonl(od / "frames.jsonl")
            evs = j.get("schedule_events") or []
            run_rec = {"run": run_i, "frames": j.get("frames"), "timed_out": r.get("timed_out"),
                       "ep0_setup": j.get("ep0_setup"), "groups": {}}
            for kind, name in groups:
                steps = macanalysis.step_medians(rows, evs, name, {"exposure": "luma", "gain": "luma",
                                                                    "white_balance": "rb", "focus": "sharp"}[kind])
                eff = macanalysis.effect_verdict(steps, kind)
                rb_ok = bool(steps) and all(s.get("readback_matches") for s in steps)
                run_rec["groups"][kind] = {"control": name, "steps": steps, "effect": eff, "readback_ok": rb_ok}
                pc = per_ctrl.setdefault(name, {"kind": kind, "runs": 0, "ok": 0, "readback": [], "effect": []})
                pc["runs"] += 1
                pc["readback"].append(rb_ok)
                pc["effect"].append(eff.get("effect_ok"))
                pc["ok"] += int(rb_ok and eff.get("effect_ok") is True)
            crec["ep0_runs"].append(run_rec)
        # before-start set, read back after the first frame
        before_ok = None
        if "exposure_time_absolute" in ranges and "auto_exposure_mode" in ranges:
            vals = [s for s in macanalysis.build_effect_schedule(ranges, initial)[0].split(";")
                    if ":ep0:exposure_time_absolute=" in s]
            target = vals[1].split("=")[1] if len(vals) > 1 else (vals[0].split("=")[1] if vals else None)
            if target:
                od = ctx.subdir("ctrl_effect", f"{suitectx.cam_tag(cam)}", "before_start")
                r = ctx.avf(["capture", "--device", cam["unique_id"], "--seconds", 3, "--jpeg-check", "none",
                             "--controls-before", f"auto_exposure_mode=1,exposure_time_absolute={target}",
                             "--out-dir", od] + suitectx.avf_mode_args(mode) + ctx.ep0_capture_args(cam), 60,
                            label=f"ctrl before-start {cam['key']}")
                j = r.get("json") or {}
                rb = {x["name"]: (x.get("result") or {}).get("value") for x in j.get("controls_readback_after_start") or []}
                before_ok = (rb.get("exposure_time_absolute") == int(target)) if rb else None
                crec["before_start"] = {"target": int(target), "readback_after_start": rb, "kept": before_ok,
                                        "controls_before": j.get("controls_before")}
                # persistence across close: read the same controls with no session open (plan 6.2 CTRL-EFFECT)
                pg = ctx.ep0(cam, "get", ["--controls", "auto_exposure_mode,exposure_time_absolute"], timeout_s=30)
                after_close = {v["name"]: v.get("value") for v in (pg.get("json") or {}).get("values") or []
                               if v.get("ok")}
                crec["before_start"]["after_close"] = after_close
                crec["before_start"]["persists_after_close"] = (
                    after_close.get("exposure_time_absolute") == int(target)) if after_close else None
    finally:
        restore = [f"{n}={initial[n]}" for n in RESTORE_ORDER if n in initial]
        if restore:
            rr = ctx.ep0(cam, "set", ["--set", ",".join(restore)], timeout_s=30)
            crec["restore"] = {"ok": (rr.get("json") or {}).get("ok"), "set": restore, "timed_out": rr.get("timed_out")}
            if not (rr.get("json") or {}).get("ok"):
                errors.append({"camera": cam["key"], "warning": "restoring the initial control values failed",
                               "detail": crec["restore"]})
    for name, pc in per_ctrl.items():
        li = listing_inputs(listing, "ep0", name, listing_src) or {}
        out.append({"name": name, "camera": cam["key"], "listed": li.get("listed"),
                    "range_matches_descriptor": li.get("range_matches_descriptor"),
                    "listing_source": li.get("listing_source"),
                    "set_readback_ok": all(pc["readback"]) if pc["readback"] else None,
                    "effect_ok": (all(e is True for e in pc["effect"]) if all(e is not None for e in pc["effect"]) else None),
                    "before_start_ok": crec.get("before_start", {}).get("kept") if name == "exposure_time_absolute" else None,
                    "after_start_ok": all(pc["readback"]) if pc["readback"] else None,
                    "runs_ok": pc["ok"], "runs_total": pc["runs"],
                    "workaround": "re-apply after start" if (name == "exposure_time_absolute" and
                                                             crec.get("before_start", {}).get("kept") is False) else None})
    return out
