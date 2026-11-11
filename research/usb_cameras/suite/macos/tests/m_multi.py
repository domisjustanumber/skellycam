"""M-MULTI: the skellycam pattern, all cameras at once (one process per camera, started together, then staggered
1 s), repeated; then each topology-predicted group (cameras sharing a USB 2.0 domain) in a predicted-over mode
and, when one exists, a predicted-fits mode. Detects the three possible macOS bandwidth signals
(an AVCaptureSessionRuntimeError, a silent zero-frame session, reduced fps), classifies each refusal, runs the
mapper's message builder on it, retries the loser alone, and reads the alt macOS granted from the
IOUSBHostInterface bAlternateSetting (no touch) and, with --ep0, GET_INTERFACE (plan 6.2 MULTI; macos.md 2.5.6;
topology_macos section 6).

Mode scope (plan 6, Dom 2026-11-06): every run uses in-scope modes only (>= 30 fps, >= 720 lines). The all-at-once
runs use each camera's scoped default (MJPEG 1280x720@30, else the nearest in-scope MJPEG mode). For a shared
domain, the over side is each camera's largest in-scope mode; the fits side is the cheapest in-scope combination
that topology_model.predict says fits. When no in-scope combination is predicted to fit, the group records
'fits-side not testable under mode scope' and only the over side runs (the fits side is then covered by cameras in
different domains in the all-at-once runs). When the prediction is incomplete (no alt table or cached cost), the
cheapest in-scope combination also runs, labelled 'unpredicted'. --all-modes adds the smallest modes back."""
from __future__ import annotations

import threading
import time

import suitectx
import macanalysis
import mac_modescope
from common import rating, results, topology_model

NAME = "M-MULTI"


def plan(ctx) -> list[str]:
    a = ctx.args
    return [mac_modescope.text(a),
            f"{a.multi_repeats} x all cameras together (one mac_avf.py capture per camera, {a.multi_seconds} s, scoped "
            "default mode), then the same staggered 1 s",
            "each shared-domain group: largest in-scope mode per camera (over side); cheapest in-scope combination "
            "predicted to fit (fits side), else 'fits-side not testable under mode scope'",
            "per capture: 1500:probe:ioreg_alt" + (" + 1700:probe:ep0_stream_state" if ctx.ep0_enabled else ""),
            "refusal -> classify_failure + explain() message; retry the loser alone",
            "scoped defaults: " + "; ".join(
                f"{c['key']}: " + ((suitectx.pick_scoped_default(c, a)[0] or {}).get("mode_text") or "untested (scope)")
                for c in ctx.openable())]


def _launch(ctx, cams_modes: list[tuple[dict, dict]], stagger_s: float, seconds: float, tag: str) -> list[dict]:
    out: list[dict | None] = [None] * len(cams_modes)

    def one(i, cam, mode):
        try:
            _one(i, cam, mode)
        except Exception as e:  # a launcher bug must show up as a result, not vanish in a thread
            out[i] = {"camera": cam["key"], "mode": mode, "t_launch": time.time(),
                      "res": {"json": None, "timed_out": False, "rc": None, "launcher_error": repr(e)}}

    def _one(i, cam, mode):
        sched = ["1500:probe:ioreg_alt"] + (["1700:probe:ep0_stream_state"] if ctx.ep0_enabled else [])
        od = ctx.subdir("multi", suitectx.slug(tag), f"{i}_{suitectx.cam_tag(cam)}")
        args = ["capture", "--device", cam["unique_id"], "--seconds", seconds, "--jpeg-check", "none",
                "--first-frame-timeout-s", 4, "--schedule", ";".join(sched), "--out-dir", od,
                "--location", cam.get("location_hex") or "", "--vs-if", ",".join(map(str, cam.get("vs_interfaces") or []))]
        args += suitectx.avf_mode_args(mode) + ctx.ep0_capture_args(cam)
        t0 = time.time()
        r = ctx.avf(args, seconds + 40, label=f"multi {tag} {cam['key']}")
        out[i] = {"camera": cam["key"], "mode": mode, "t_launch": t0, "res": r}

    threads = []
    for i, (cam, mode) in enumerate(cams_modes):
        th = threading.Thread(target=one, args=(i, cam, mode), daemon=True)
        th.start()
        threads.append(th)
        if stagger_s:
            time.sleep(stagger_s)
    for th in threads:
        th.join()
    return [x for x in out if x]


def _granted_alt(j: dict) -> dict:
    out = {}
    for ev in j.get("schedule_events") or []:
        r = ev.get("result") or {}
        if ev.get("name") == "ioreg_alt":
            vs = [x for x in r.get("interfaces") or [] if x.get("subclass") == 2]
            out["ioreg_alt"] = max((x.get("alt") or 0 for x in vs), default=None) if vs else None
        if ev.get("name") == "ep0_stream_state":
            out["ep0"] = [{"get_interface": (s.get("get_interface") or {}).get("alt"),
                           "commit": s.get("commit")} for s in r.get("streams") or []]
    return out


def _attempt(ctx, label: str, cams_modes: list[tuple[dict, dict]], stagger_s: float, topo: dict) -> dict:
    a = ctx.args
    runs = _launch(ctx, cams_modes, stagger_s, a.multi_seconds, label)
    cam_dom = (topo or {}).get("camera_domains") or {}
    snap = ctx.snapshot or {}
    reqs = [{"camera_key": c["key"], "mode": m.get("mode_text"), "alt": None, "max_packet": None, "mult": None}
            for c, m in cams_modes]
    cache = ctx.mode_alt_cache()
    try:
        pred = topology_model.predict(snap, reqs, cache)
    except Exception as e:
        pred = {"error": repr(e), "domains": [], "conflicts": []}
    dom_verdict = {d["key"]: d.get("verdict") for d in pred.get("domains") or []}
    dom_incomplete = {d["key"]: bool(d.get("incomplete")) for d in pred.get("domains") or []}
    per = []
    for x in runs:
        j = x["res"].get("json") or {}
        sig = macanalysis.refusal_signal(j, x["mode"].get("fps"), x["res"].get("timed_out"))
        per.append({"camera": x["camera"], "mode": x["mode"].get("mode_text"), "frames": j.get("frames"),
                    "fps": j.get("fps_measured"), "first_frame_ms": j.get("first_frame_ms"),
                    "runtime_errors": j.get("runtime_errors"), "signal": sig, "granted": _granted_alt(j),
                    "domain": cam_dom.get(x["camera"]), "rc": x["res"].get("rc")})
    events = []
    non_bw = []
    for p in per:
        if not p["signal"]["refused"]:
            continue
        dom = p["domain"]
        others = [q for q in per if q is not p and q["domain"] == dom and dom is not None]
        other_streaming = any((q["frames"] or 0) > 0 for q in others)
        verdict = dom_verdict.get(dom)
        cls = topology_model.classify_failure("macos", p["signal"]["code"], {
            "api": "avf", "stage": "first_frame" if not p["frames"] else "streaming", "frames": p["frames"],
            "other_streaming_in_domain": other_streaming, "predicted_verdict": verdict,
            "timed_out": p["signal"]["signal"] == "hang"})
        if dom is not None and not others and cls["class"] not in ("bandwidth_certain", "bandwidth_probable"):
            # alone in its domain and not a bandwidth code (e.g. the Kiyo hanging, in-use, permission): a camera
            # failure, not a bandwidth refusal. Counting it in G-BW would score a correct 'fits' as a false fit.
            non_bw.append({"label": label, "camera": p["camera"], "signal": p["signal"], "classification": cls,
                           "predicted_verdict": verdict})
            continue
        failure = dict(cls, loser=p["camera"])
        msg = None
        ports_ok = None
        try:
            ex = topology_model.explain(snap, reqs, cache, failure=failure)
            mm = [x for x in ex["messages"] if x.get("moving_camera_key") == p["camera"]] or ex["messages"]
            if mm:
                msg = mm[0]["message"]
                ports_ok = macanalysis.ports_in_other_domains(snap, mm[0]["suggestions"], mm[0]["domain_key"])
        except Exception as e:
            msg = f"(message builder failed: {e!r})"
        # retry once, alone, after everything stopped
        cam = next(c for c, _ in cams_modes if c["key"] == p["camera"])
        mode = next(m for c, m in cams_modes if c["key"] == p["camera"])
        rr = ctx.avf(["capture", "--device", cam["unique_id"], "--seconds", 3, "--jpeg-check", "none",
                      "--first-frame-timeout-s", 4] + suitectx.avf_mode_args(mode), 45, label=f"multi retry {cam['key']}")
        retry_ok = bool((rr.get("json") or {}).get("frames"))
        events.append({"label": label, "camera": p["camera"], "api": "avf", "predicted_verdict": verdict,
                       "observed_refused": True, "signal": p["signal"]["signal"], "classified_class": cls["class"],
                       "classification": cls, "expected_bandwidth": bool(others) and verdict in ("over", "marginal"),
                       "message": msg, "message_ports_other_domains": ports_ok, "retry_ok": retry_ok,
                       "shares_domain_with": [q["camera"] for q in others],
                       "prediction_incomplete": dom_incomplete.get(dom),
                       "note": None if not dom_incomplete.get(dom) else
                       "camera cost unknown (no descriptors cached: run once with --ep0, or the mode->alt cache is "
                       "empty for this mode), so the prediction could not say 'over'"})
    # attempts with no bandwidth refusal still count for "no false fits" bookkeeping
    if not events:
        for d, v in dom_verdict.items():
            events.append({"label": label, "domain": d, "api": "avf", "predicted_verdict": v,
                           "observed_refused": False, "classified_class": None})
    return {"label": label, "stagger_s": stagger_s, "cameras": per, "prediction": {
        "domains": [{k: d.get(k) for k in ("key", "predicted_load_us", "pct_microframe", "verdict", "members",
                                                 "incomplete")}
                    for d in pred.get("domains") or []], "conflicts": len(pred.get("conflicts") or [])},
            "events": events, "non_bandwidth_failures": non_bw}


FITS_NOT_TESTABLE = "fits-side not testable under mode scope"


def _predict_group(ctx, combo: list[tuple[dict, dict]]) -> dict:
    """Prediction for one combination of (camera, mode): the verdict of the busiest domain that holds them."""
    reqs = [{"camera_key": c["key"], "mode": m.get("mode_text"), "alt": None, "max_packet": None, "mult": None}
            for c, m in combo]
    try:
        pred = topology_model.predict(ctx.snapshot or {}, reqs, ctx.mode_alt_cache())
    except Exception as e:
        return {"verdict": None, "incomplete": True, "error": repr(e)}
    keys = {c["key"] for c, _ in combo}
    doms = [d for d in pred.get("domains") or [] if keys & set(d.get("members") or [])]
    if not doms:
        return {"verdict": None, "incomplete": True, "error": "no domain holds these cameras"}
    d = max(doms, key=lambda d: d.get("predicted_load_us") or 0)
    return {"verdict": d.get("verdict"), "incomplete": bool(d.get("incomplete")), "domain": d.get("key"),
            "pct_microframe": d.get("pct_microframe")}


def plan_group(ctx, grp: list[dict], max_combos: int = 64) -> dict:
    """Modes for one shared-domain group under the mode scope.
    over: each camera's largest in-scope mode. fits: the cheapest in-scope combination predicted 'fits'
    (combinations tried cheapest first, at most max_combos). Returns {cameras, over, fits, fits_label, fits_side,
    over_prediction, fits_prediction, tried}."""
    import itertools
    per = []
    for c in grp:
        ms = suitectx.scoped_mjpeg_modes(c, ctx.args)
        if mac_modescope.params(ctx.args)["all_modes"]:
            sm = suitectx.pick_small_mode(c)
            if sm and all((sm["format_index"], sm["fps"]) != (m["format_index"], m["fps"]) for m in ms):
                ms = [sm] + ms
        per.append(ms)
    out: dict = {"cameras": [c["key"] for c in grp], "over": None, "fits": None, "fits_label": None, "tried": 0}
    if not all(per):
        out["fits_side"] = out["over_side"] = "a camera has no in-scope mode"
        return out
    over = [(c, max(ms, key=lambda m: (m["w"] * m["h"], m["fps"] or 0))) for c, ms in zip(grp, per)]
    out["over"] = over
    out["over_prediction"] = _predict_group(ctx, over)
    combos = sorted(itertools.product(*per), key=lambda cm: sum(m["w"] * m["h"] * (m["fps"] or 30) for m in cm))
    unknown = None
    for cm in combos[:max_combos]:
        out["tried"] += 1
        combo = list(zip(grp, cm))
        pr = _predict_group(ctx, combo)
        if pr.get("verdict") == "fits" and not pr.get("incomplete"):
            out.update(fits=combo, fits_label="fits", fits_prediction=pr, fits_side="predicted fits")
            return out
        if pr.get("incomplete") and unknown is None:
            unknown = (combo, pr)
    if unknown is not None:
        combo, pr = unknown
        out["fits_prediction"] = pr
        if [m["mode_text"] for _, m in combo] == [m["mode_text"] for _, m in over]:
            out["fits_side"] = "prediction incomplete; the cheapest in-scope combination is the over side (not rerun)"
        else:
            out.update(fits=combo, fits_label="unpredicted",
                       fits_side="prediction incomplete: cheapest in-scope combination run, verdict unknown")
        return out
    out["fits_side"] = FITS_NOT_TESTABLE
    return out


def run(ctx) -> dict:
    res = ctx.new_result(NAME)
    errors: list = []
    cams = ctx.openable()
    topo = ctx.store.get("topo") or {}
    attempts = []
    if len(cams) < 2:
        m = {"note": "fewer than two openable cameras", "cameras": [c["key"] for c in cams]}
        return results.finish_result(res, m, {"G-BW": rating.untested("fewer than two cameras")}, errors)
    default, scoped_out = [], []
    for c in cams:
        mo, info = suitectx.pick_scoped_default(c, ctx.args)
        if mo:
            default.append((c, mo))
        else:
            scoped_out.append({"camera": c["key"], "is_kiyo": c.get("is_kiyo"), "untested": "scope", "why": info["why"]})
    for k in range(ctx.args.multi_repeats):
        attempts.append(_attempt(ctx, f"all_together_{k}", default, 0.0, topo))
        attempts.append(_attempt(ctx, f"all_staggered_{k}", default, 1.0, topo))
    # predicted groups: cameras sharing a domain (each with at least one in-scope mode)
    in_scope_keys = {c["key"] for c, _ in default}
    by_dom: dict[str, list[dict]] = {}
    for c in cams:
        d = (topo.get("camera_domains") or {}).get(c["key"])
        if d and d.startswith("hs|") and c["key"] in in_scope_keys:
            by_dom.setdefault(d, []).append(c)
    groups = [v for v in by_dom.values() if len(v) >= 2]
    group_plans = []
    for grp in groups:
        gp = plan_group(ctx, grp)
        group_plans.append({k: v for k, v in gp.items() if k not in ("over", "fits")} |
                           {"over_modes": [m["mode_text"] for _, m in gp["over"]] if gp["over"] else None,
                            "fits_modes": [m["mode_text"] for _, m in gp["fits"]] if gp["fits"] else None})
        for k in range(ctx.args.multi_repeats):
            if gp["over"]:
                attempts.append(_attempt(ctx, f"pair_over_{k}_{grp[0]['key']}", gp["over"], 1.0, topo))
            if gp["fits"]:
                attempts.append(_attempt(ctx, f"pair_{gp['fits_label']}_{k}_{grp[0]['key']}", gp["fits"], 1.0, topo))
    events = [e for a in attempts for e in a["events"]]
    ambiguous = sorted({"avf"} if any(e.get("classified_class") == "bandwidth_probable" for e in events) else set())
    v = {"G-BW": rating.rate_bw(events, labels_raw=topo.get("labels_raw"), ambiguous_apis=ambiguous)}
    v["G-BW"]["tier"] = 0
    v["G-BW"]["mode_scope"] = mac_modescope.text(ctx.args)
    if any(g.get("fits_side") == FITS_NOT_TESTABLE for g in group_plans):
        v["G-BW"]["note_scope"] = (f"{FITS_NOT_TESTABLE} for some shared domain(s): the 'fits' side there is covered "
                                   "only by cameras in different domains (all-at-once runs)")
    m = {"attempts": attempts, "shared_domains": {d: [c["key"] for c in v_] for d, v_ in by_dom.items()},
         "group_plans": group_plans, "scoped_out_cameras": scoped_out,
         "mode_scope": suitectx.scope_for_test(cams, ctx.args),
         "signals_seen": sorted({e.get("signal") for e in events if e.get("signal")}),
         "non_bandwidth_failures": [x for a_ in attempts for x in a_.get("non_bandwidth_failures") or []],
         "note": "macOS documents no error code for a refused reservation; kIOReturnNoBandwidth (0xE00002EC) is the "
                 "likely code underneath (topology_macos 6.1)"}
    return results.finish_result(res, m, v, errors)
