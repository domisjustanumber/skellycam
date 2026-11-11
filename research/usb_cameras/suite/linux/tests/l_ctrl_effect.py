"""L-CTRL-EFFECT: set -> readback -> effect in the image, before vs after STREAMON, persistence across
close/reopen, for exposure, gain, white-balance temperature and focus (plan 6.2 CTRL-EFFECT, G-CTRL).

Each experiment is one capture (raw V4L2): controls set before STREAMON (step 0), then changed twice while
streaming (steps 1 and 2, camworker --schedule), frames saved and measured per step (common.imgmetrics: luma,
R/B ratio, Laplacian sharpness). Auto modes are switched to manual first (uvcvideo returns EACCES for a slave while
its master is auto; that case is checked explicitly). Readback alone is not trusted (first read after a set of an
AUTO_UPDATE control re-queries the camera, later reads are cached), so the image decides. The original values and
auto modes are restored at the end, always. Repeated --ctrl-runs times (3). Scene-dependent: a static, lit scene
with some texture gives meaningful focus and WB numbers.

G-CTRL criterion 1 ("every control in the descriptors is listed with the descriptor's range") is fed from
L-CTRL-LIST's ``per_control`` (ctx.shared["ctrl_list"]): ``listed`` = the walk lists the descriptor control,
``range_matches_descriptor`` = the camera answered a consistent GET_MIN/MAX/RES/DEF range (UVC descriptors carry no
ranges). When L-CTRL-LIST did not run in this session, the same comparison runs on this test's own walk and the
row says so (``criterion1_source``).

Mode scope (plan 6, Dom 2026-11-06): captures use the in-scope default (MJPG 1280x720@30, else the nearest in-scope
MJPEG mode); --all-modes restores the earlier 640x480@30. No in-scope MJPEG mode -> 'untested (scope)'.
"""
from __future__ import annotations

import time
from typing import Any

from common import rating, results
import analysis
import apis
import scope
import sysfs
import v4l2
from suitectx import child_outcome, combine
from tutil import gate, mode_text, worker_error

TEST = "L-CTRL-EFFECT"
INFO = {"goal": "G-CTRL", "summary": "exposure / gain / WB / focus: set, readback, image effect, before vs after "
                                     "STREAMON, persistence, restore", "opens_cameras": True}
CID = v4l2.CID
SECONDS = 4.5
SCHED = (1500, 3000)


def plan(ctx) -> dict[str, Any]:
    n = len(ctx.cameras) * 4 * ctx.args.ctrl_runs
    return {"child_runs": n + 4 * len(ctx.cameras), "est_seconds": round(n * (SECONDS + 4) + 20 * len(ctx.cameras)),
            "steps": ["EACCES check", f"{ctx.args.ctrl_runs} x (exposure, gain, WB, focus) captures",
                      "persistence read + capture", "restore originals"],
            "mode_scope": scope.settings(ctx.args),
            "per_camera_mode": {c["key"]: mode_text(scope.picks(ctx, c)["ctrl_mode"]) for c in ctx.cameras}}


def snap(v: float, c: dict[str, Any]) -> int:
    lo, hi, st = int(c["min"]), int(c["max"]), int(c.get("step") or 1) or 1
    v = min(max(v, lo), hi)
    return int(min(max(lo + round((v - lo) / st) * st, lo), hi))


def sets_text(pairs: list[tuple[int, int]]) -> str:
    return ",".join(f"0x{k:08x}={v}" for k, v in pairs)


def experiments(walk: dict[int, dict], fps: float) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    ae, ex = walk.get(CID["auto_exposure"]), walk.get(CID["exposure_time_absolute"])
    dyn = walk.get(CID["exposure_dynamic_framerate"])
    pre_manual: list[tuple[int, int]] = []
    ex_lo = None
    if ae and ex:
        manual_ok = any(m.get("index") == 1 for m in ae.get("menu") or [{"index": 1}])
        if manual_ok:
            pre_manual = [(CID["auto_exposure"], 1)] + ([(CID["exposure_dynamic_framerate"], 0)] if dyn else [])
            d = ex.get("default") or ex["min"]
            cap = 1e4 / max(fps, 1.0) * 0.9           # stay within the frame period (100 us units)
            ex_lo = snap(max(ex["min"], d * 0.35), ex)
            ex_hi = snap(min(ex["max"], cap, max(d * 2.5, ex_lo * 4)), ex)
            if ex_hi <= ex_lo:
                ex_lo, ex_hi = snap(ex["min"], ex), snap(min(ex["max"], cap), ex)
            out["exposure"] = {"before": pre_manual + [(ex["id"], ex_lo)],
                               "schedule": [(SCHED[0], [(ex["id"], ex_hi)]), (SCHED[1], [(ex["id"], ex_lo)])],
                               "values": [ex_lo, ex_hi, ex_lo], "metric": "luma", "direction": +1, "cid": ex["id"]}
    g = walk.get(CID["gain"])
    if g and g["max"] > g["min"]:
        g_lo, g_hi = snap(g["min"], g), snap(g["min"] + 0.8 * (g["max"] - g["min"]), g)
        before = list(pre_manual) + ([(ex["id"], ex_lo)] if ex_lo is not None else [])
        out["gain"] = {"before": before + [(g["id"], g_lo)],
                       "schedule": [(SCHED[0], [(g["id"], g_hi)]), (SCHED[1], [(g["id"], g_lo)])],
                       "values": [g_lo, g_hi, g_lo], "metric": "luma", "direction": +1, "cid": g["id"]}
    wa, wt = walk.get(CID["white_balance_automatic"]), walk.get(CID["white_balance_temperature"])
    if wt:
        lo, hi = snap(2800, wt), snap(6500, wt)
        if hi > lo:
            out["white_balance"] = {"before": ([(wa["id"], 0)] if wa else []) + [(wt["id"], lo)],
                                    "schedule": [(SCHED[0], [(wt["id"], hi)]), (SCHED[1], [(wt["id"], lo)])],
                                    "values": [lo, hi, lo], "metric": "rb_ratio", "direction": +1, "cid": wt["id"]}
    fa, fa_abs = walk.get(CID["focus_automatic_continuous"]), walk.get(CID["focus_absolute"])
    if fa_abs and fa_abs["max"] > fa_abs["min"]:
        lo, mid, hi = (snap(fa_abs["min"], fa_abs), snap((fa_abs["min"] + fa_abs["max"]) / 2, fa_abs),
                       snap(fa_abs["max"], fa_abs))
        out["focus"] = {"before": ([(fa["id"], 0)] if fa else []) + [(fa_abs["id"], lo)],
                        "schedule": [(SCHED[0], [(fa_abs["id"], mid)]), (SCHED[1], [(fa_abs["id"], hi)]),
                                     (SCHED[1] + 1500, [(fa_abs["id"], lo)])],
                        "values": [lo, mid, hi, lo], "metric": "sharpness", "direction": 0, "cid": fa_abs["id"],
                        "seconds": SECONDS + 1.5}
    return out


def judge(name: str, exp: dict[str, Any], win: dict[int, dict[str, Any]], cap: dict[str, Any]) -> dict[str, Any]:
    m = exp["metric"]
    v = [((win.get(s) or {}).get(m)) for s in range(len(exp["values"]))]
    sets = list(cap.get("controls_before") or [])
    for ev in cap.get("schedule_events") or []:
        sets += ev.get("sets") or []
    readback_ok = all(s.get("errno") is None and (s.get("readback") == s.get("value")) for s in sets) if sets else None
    out: dict[str, Any] = {"values": exp["values"], "metric": m, "per_step": v, "sets": sets,
                           "set_readback_ok": readback_ok, "frames": cap.get("frames"), "error": cap.get("error")}
    if None in v:
        out.update(effect_ok=None, before_start_ok=None, after_start_ok=None, note="metrics missing for a step")
        return out
    if exp["direction"] > 0:
        thr = 1.15 if m == "luma" else 1.05
        sat = m == "luma" and v[0] is not None and v[0] > 235
        after = v[1] > v[0] * thr and v[2] < v[1] / thr
        before = abs(v[0] - v[2]) <= 0.2 * max(v[1], 1e-9)
        out.update(effect_ok=None if sat else after, after_start_ok=None if sat else after,
                   before_start_ok=before, saturated=sat)
    else:
        scan = v[:3]
        spread = max(scan) / max(min(scan), 1e-12)
        out.update(effect_ok=spread > 1.25, after_start_ok=spread > 1.25,
                   before_start_ok=abs(v[0] - v[3]) <= 0.2 * max(max(scan), 1e-12), spread=spread,
                   note="focus: sharpness spread over min/mid/max focus, then back to min (scene-dependent)")
    return out


def run(ctx) -> dict[str, Any]:
    res = ctx.new_result(TEST)
    errors: list[dict] = []
    per_cam: dict[str, Any] = {}
    verdicts: dict[str, Any] = {}
    runs = ctx.args.ctrl_runs
    for cam in ctx.cameras:
        skip = gate(ctx, cam, TEST)
        if skip:
            per_cam[cam["key"]] = skip
            verdicts[cam["key"]] = rating.untested(skip["reason"])
            continue
        pk = scope.picks(ctx, cam)
        sc = pk["record"]
        mode = pk["ctrl_mode"]
        if not mode:
            per_cam[cam["key"]] = {"skipped": True, "mode_scope": sc,
                                   "reason": "no in-scope MJPEG mode" if sc.get("no_in_scope_mjpeg_mode")
                                   else "no MJPEG mode"}
            verdicts[cam["key"]] = (scope.untested_scope(sc) if sc.get("no_in_scope_mjpeg_mode")
                                    else rating.untested("no MJPEG mode"))
            continue
        walk_list = ctx.shared.get("controls", {}).get(cam["key"])
        if not walk_list:
            r = ctx.camcmd(ctx.worker_cmd("controls", "--device", cam["node"], "--total-timeout-s", "165"),
                           timeout_s=180)
            walk_list = (r.get("json") or {}).get("controls") or []
        walk = {c["id"]: c for c in walk_list if c.get("id") is not None}
        listing = (ctx.shared.get("ctrl_list") or {}).get(cam["key"])
        if listing is not None:
            per_control, c1_source = listing.get("per_control"), "L-CTRL-LIST"
        elif walk_list:
            per_control = analysis.ctrl_per_control(walk_list, cam["descriptors"])
            c1_source = "L-CTRL-EFFECT's own walk (L-CTRL-LIST did not run in this session; same comparison)"
        else:
            per_control, c1_source = None, "no listing available"
        cs = ctx.slug(cam)
        ent: dict[str, Any] = {"mode": mode_text(mode), "mode_scope": sc, "experiments": {},
                               "criterion1_source": c1_source}
        orig = {cid: walk[cid].get("value") for cid in (CID["exposure_time_absolute"], CID["gain"],
                                                        CID["white_balance_temperature"], CID["focus_absolute"],
                                                        CID["auto_exposure"], CID["white_balance_automatic"],
                                                        CID["focus_automatic_continuous"],
                                                        CID["exposure_dynamic_framerate"]) if cid in walk}
        ent["originals"] = {f"0x{k:08x}": v for k, v in orig.items()}
        exps = experiments(walk, float(mode["fps"]))
        try:
            # EACCES check: a slave set while its master is auto
            ae, ex = walk.get(CID["auto_exposure"]), walk.get(CID["exposure_time_absolute"])
            if ae and ex:
                auto_idx = 3 if any(m.get("index") == 3 for m in ae.get("menu") or []) else 0
                r = ctx.camcmd(ctx.worker_cmd("controls", "--device", cam["node"], "--no-walk", "--total-timeout-s",
                                              "35", "--set",
                                              sets_text([(ae["id"], auto_idx), (ex["id"], snap(ex["default"], ex))])),
                               timeout_s=40)
                s = (r.get("json") or {}).get("sets") or []
                ent["eacces_check"] = {"sets": s, "slave_errno": s[1].get("errno") if len(s) > 1 else None,
                                       "expected": "EACCES", "child": child_outcome(r)}
            for name, exp in exps.items():
                trials = []
                for k in range(runs):
                    od = ctx.test_dir(TEST, cs, f"{name}_{k}")
                    rd = ctx.raw_test_dir(TEST, cs, f"{name}_{k}")
                    sched = ";".join(f"{t}:{sets_text(p)}" for t, p in exp["schedule"])
                    ctx.log(f"{cam['name']} {name} run {k + 1}/{runs}")
                    cap = apis.capture(ctx, "v4l2", cam, mode, exp.get("seconds", SECONDS), od, rd, save="all",
                                       analyse=False,
                                       extra=["--controls-before", sets_text(exp["before"]), "--schedule", sched])
                    rows = analysis.read_rows(od / "frames.jsonl")
                    win = analysis.window_metrics(rows, rd / "frames.mjpeg", settle_ms=600)
                    j = judge(name, exp, win, cap)
                    j["windows"] = win
                    j["child"] = cap.get("child")
                    trials.append(j)
                    if not getattr(ctx.args, "keep_raw", False):
                        apis.prune_raw(rd, od / "frames.jsonl")
                ent["experiments"][name] = {"trials": trials, "plan": {"before": exp["before"],
                                                                       "schedule": exp["schedule"]}}
            # persistence across close/reopen: read back, then capture without setting anything
            if "exposure" in exps:
                # Idle first for longer than the autosuspend delay: closing the node (and, from 6.16, an idle open
                # fd: granular PM) lets the camera runtime-suspend, so "persists" means it survived a suspend too.
                ud = sysfs.P(cam["sysfs_dir"]) if cam.get("sysfs_dir") else None
                delay_ms = sysfs.rd_int(ud / "power/autosuspend_delay_ms") if ud else None
                idle_s = min(10.0, max(0.0, (delay_ms or 2000) / 1000.0) + 1.5)
                time.sleep(idle_s)
                pm_before = {"idle_s": idle_s, "autosuspend_delay_ms": delay_ms,
                             "control": sysfs.rd(ud / "power/control") if ud else None,
                             "runtime_status_before_reopen": sysfs.rd(ud / "power/runtime_status") if ud else None,
                             "granular_pm_kernel": ctx.kernel() >= (6, 16)}
                ids = ",".join(f"0x{c:08x}" for c in (CID["auto_exposure"], CID["exposure_time_absolute"]))
                r = ctx.camcmd(ctx.worker_cmd("controls", "--device", cam["node"], "--ids", ids,
                                              "--total-timeout-s", "50"), timeout_s=60)
                vals = {c["id"]: c.get("value") for c in ((r.get("json") or {}).get("controls") or [])}
                od = ctx.test_dir(TEST, cs, "persist")
                rd = ctx.raw_test_dir(TEST, cs, "persist")
                cap = apis.capture(ctx, "v4l2", cam, mode, 2.0, od, rd, save="all", analyse=False)
                win = analysis.window_metrics(analysis.read_rows(od / "frames.jsonl"), rd / "frames.mjpeg", 600)
                last = ent["experiments"]["exposure"]["trials"][-1]
                ref = (last.get("per_step") or [None, None, None])[2]
                lum = (win.get(0) or {}).get("luma")
                ent["persistence"] = {
                    "power_before_reopen": pm_before,
                    "readback_after_reopen": {f"0x{k:08x}": v for k, v in vals.items()},
                    "manual_kept": vals.get(CID["auto_exposure"]) == 1,
                    "exposure_kept": vals.get(CID["exposure_time_absolute"]) == exps["exposure"]["values"][2],
                    "luma_reopen": lum, "luma_last_step": ref,
                    "image_consistent": (abs(lum - ref) <= 0.2 * max(ref, 1e-9)) if lum is not None and ref else None}
                if not getattr(ctx.args, "keep_raw", False):
                    apis.prune_raw(rd, od / "frames.jsonl")
        finally:
            # Slaves first (their masters are still manual from the experiments), then the auto/master controls.
            # A value that could not be read at the start (None, e.g. a Kiyo get error) falls back to the
            # control's default so auto exposure / AWB / AF are always switched back on.
            def value_for(cid: int) -> int | None:
                if orig.get(cid) is not None:
                    return orig[cid]
                return walk.get(cid, {}).get("default")
            slaves = (CID["gain"], CID["exposure_time_absolute"], CID["white_balance_temperature"],
                      CID["focus_absolute"])
            masters = (CID["auto_exposure"], CID["white_balance_automatic"], CID["focus_automatic_continuous"],
                       CID["exposure_dynamic_framerate"])
            restore = [(cid, value_for(cid)) for cid in slaves + masters
                       if cid in walk and value_for(cid) is not None]
            ent["restore_plan"] = {f"0x{k:08x}": {"value": v, "source": "original" if orig.get(k) is not None
                                                  else "default"} for k, v in restore}
            if restore:
                r = ctx.camcmd(ctx.worker_cmd("controls", "--device", cam["node"], "--no-walk", "--total-timeout-s",
                                              "50", "--set", sets_text(restore)), timeout_s=60)
                sets = (r.get("json") or {}).get("sets") or []
                ent["restore"] = {"sets": sets, "error": worker_error(r)}
                bad_master = any(s.get("errno") or "errno" not in s for s in sets if s.get("id") in masters) or \
                    len(sets) < len(restore) or bool(worker_error(r))
                if bad_master:
                    # second chance for the auto modes alone (a hung or failed slave set must not leave AE/AWB/AF
                    # off); a slave the camera rejects while its master is auto is harmless
                    m_only = [(k, v) for k, v in restore if k in masters]
                    if m_only:
                        r2 = ctx.camcmd(ctx.worker_cmd("controls", "--device", cam["node"], "--no-walk",
                                                       "--total-timeout-s", "35", "--set", sets_text(m_only)),
                                        timeout_s=45)
                        ent["restore_masters_retry"] = {"sets": (r2.get("json") or {}).get("sets"),
                                                        "error": worker_error(r2)}
                # EACCES on a slave whose master is (still) auto is expected, not a restore failure
                if worker_error(r) or any(s.get("errno") and not (s.get("errno") == "EACCES" and s.get("id") in slaves)
                                          for s in sets):
                    errors.append({"camera": cam["key"], "stage": "restore", "detail": ent["restore"],
                                   "masters_retry": ent.get("restore_masters_retry")})
        rows = []
        for name, e in ent["experiments"].items():
            tr = e["trials"]
            ok_runs = sum(1 for t in tr if t.get("effect_ok") and t.get("set_readback_ok"))
            pers = ent.get("persistence") or {}
            c1 = analysis.ctrl_criterion1(per_control, name, c1_source)
            rows.append({"name": name, "listed": c1["listed"], "range_matches_descriptor": c1["range_matches_descriptor"],
                         "criterion1": c1,
                         "set_readback_ok": all(t.get("set_readback_ok") for t in tr) if tr else None,
                         "effect_ok": all(t.get("effect_ok") for t in tr) if tr and all(
                             t.get("effect_ok") is not None for t in tr) else None,
                         "before_start_ok": all(t.get("before_start_ok") for t in tr)
                         if tr and all(t.get("before_start_ok") is not None for t in tr) else None,
                         "after_start_ok": all(t.get("after_start_ok") for t in tr)
                         if tr and all(t.get("after_start_ok") is not None for t in tr) else None,
                         "runs_ok": ok_runs, "runs_total": len(tr),
                         "workaround": None if name != "exposure" or pers.get("manual_kept") in (True, None)
                         else "manual exposure not kept across close/reopen: re-apply at every open"})
        ent["rating_rows"] = rows
        verdicts[cam["key"]] = rating.rate_ctrl(rows, runs_required=runs) if rows else \
            rating.untested("no exposure/gain/WB/focus control listed", list(walk))
        per_cam[cam["key"]] = ent
    results.finish_result(res, measurements={"cameras": per_cam, "runs": runs, "seconds": SECONDS,
                                             "schedule_ms": SCHED, "mode_scope": scope.settings(ctx.args)},
                          verdicts={"G-CTRL": combine(verdicts, "control effect") if verdicts
                                    else rating.untested("no camera")}, errors=errors)
    return res
