"""L-MULTI: cameras at once, bandwidth contention, refusal classification and the user message (plan 5 and 6.2
MULTI, G-BW). Bandwidth contention is a test case here, not something to avoid.

A. The skellycam pattern: every camera at its default mode, one process each, started together, then staggered
   in domain order; repeated --multi-reps times.
B. Predicted pairs from the topology: for each high-speed domain holding two or more cameras, camera A streams,
   camera B starts while A runs, in a predicted-'over' mode pair and a predicted-'fits' pair (from the
   ModeAltCache learned in L-MJPEG/L-CYC, else the largest alt). A refused start of B is classified
   (ENOSPC = certain; ENOMEM/EIO/EPIPE/ETIMEDOUT per common.topology_model.classify_failure), retried once while A
   still streams, then B is opened alone after A stops (recovery). For every real refusal the mapper's message is
   built from a snapshot taken while A streams (granted alts read from sysfs), and checked to list only ports in
   other domains. One cross-domain pair (two cameras on different root ports at their largest modes) checks that
   separate domains do not compete.

Mode scope (plan 6, Dom 2026-11-06): every stream here uses in-scope modes only (>= --min-fps, >= --min-height;
linuxlib/scope.py). Phase A runs each camera at its in-scope default; the pair variants are chosen among in-scope
mode pairs by prediction. When no in-scope pair is predicted to fit in a shared domain (Gerald's C922 + generic hub:
every 720p+ pair is over budget), the pair records "fits-side not testable under mode scope" and only the
predicted-over side runs; the cross-domain pair and phase A still run. --all-modes restores the earlier candidates
(640x480 and the other default/small/large modes).
"""
from __future__ import annotations

import threading
import time
from typing import Any

from common import rating, results, topology_model as tm
import apis
import scope
import topology
from suitectx import child_outcome
from tutil import gate, mode_args, mode_text, worker_error

TEST = "L-MULTI"
INFO = {"goal": "G-BW", "summary": "all cameras together + staggered; predicted over/fits pairs; refusal class, "
                                   "retry, recovery, user message", "opens_cameras": True}
SECS = 5.0


def plan(ctx) -> dict[str, Any]:
    pairs = len(domain_pairs(ctx, ctx.topology or {}))
    reps = ctx.args.multi_reps
    return {"child_runs": reps * 2 * len(ctx.cameras) + pairs * 2 * 4 + 2,
            "est_seconds": round(reps * 2 * (SECS + 8) + pairs * 2 * 22 + 25),
            "steps": [f"{reps} x all-at-once + staggered", f"{pairs} same-domain pair(s) x (over, fits)",
                      "cross-domain pair", "messages"],
            "mode_scope": scope.settings(ctx.args),
            "per_camera_default": {c["key"]: mode_text(scope.picks(ctx, c)["default"]) for c in ctx.cameras}}


def _cap_job(ctx, cam, mode, seconds, out_dir, delay=0.0) -> dict[str, Any]:
    fps = float(mode["fps"])
    return {"argv": ctx.worker_cmd("capture", "--device", cam["node"], *mode_args(mode), "--seconds", seconds,
                                   "--out-dir", out_dir, "--save", "none", "--timeout-ms", apis.frame_timeout_ms(fps),
                                   "--first-frame-timeout-ms", 4000),
            "timeout_s": apis.capture_timeout(seconds, fps) + delay, "delay_s": delay}


def _summ(r: dict[str, Any], cam: dict[str, Any], mode: dict[str, Any]) -> dict[str, Any]:
    j = r.get("json") or {}
    st = j.get("stream") or {}
    frames = (st.get("counts") or {}).get("frames", 0)
    return {"camera": cam["key"], "name": cam["name"], "mode": mode_text(mode), "ok": bool(frames),
            "frames": frames, "fps": st.get("fps_host"), "error": worker_error(r),
            "first_frame_ms": (j.get("timings") or {}).get("first_frame_ms"),
            "streamon_ms": (j.get("timings") or {}).get("streamon_ms"),
            "granted_alt": (((st.get("granted") or {}).get("alts") or [{}])[0]).get("alt"),
            "granted_after_failure": j.get("granted_after_failure"), "started_at_s": r.get("started_at_s"),
            "child": child_outcome(r)}


def domain_of(snap: dict[str, Any], key: str) -> str | None:
    cam = next((c for c in snap.get("cameras") or [] if c["key"] == key), None)
    if not cam or not cam.get("device_id"):
        return None
    try:
        return tm.domain_key(snap, cam["device_id"])
    except KeyError:
        return None


def domain_pairs(ctx, snap: dict[str, Any]) -> list[tuple[dict, dict]]:
    if not snap or not snap.get("cameras"):
        return []
    by_dom: dict[str, list[dict]] = {}
    for c in ctx.cameras:
        d = domain_of(snap, c["key"])
        if d and d.startswith("hs|"):
            by_dom.setdefault(d, []).append(c)
    out = []
    for cams in by_dom.values():
        for i in range(len(cams)):
            for j in range(i + 1, len(cams)):
                out.append((cams[i], cams[j]))
    return out


def cross_pair(ctx, snap) -> tuple[dict, dict] | None:
    seen: dict[str, dict] = {}
    for c in ctx.cameras:
        d = domain_of(snap, c["key"])
        if d and d.startswith("hs|") and d not in seen:
            seen[d] = c
    v = list(seen.values())
    return (v[0], v[1]) if len(v) >= 2 else None


def predicted(snap, cache, reqs: list[tuple[dict, dict]]) -> dict[str, Any]:
    return tm.predict(snap, [{"camera_key": c["key"], "mode": mode_text(m)} for c, m in reqs], cache)


def classify_ctx(snap, pred, key: str, others_streaming: list[str]) -> dict[str, Any]:
    d = domain_of(snap, key)
    dv = next((x["verdict"] for x in pred.get("domains", []) if x["key"] == d), None)
    same = [k for k in others_streaming if domain_of(snap, k) == d]
    return {"api": "v4l2", "other_streaming_in_domain": bool(same), "predicted_verdict": dv,
            "domain": d, "others_in_domain_streaming": same}


def phase_a(ctx, snap, cache, errors) -> tuple[list[dict], list[dict]]:
    dm = {c["key"]: scope.picks(ctx, c)["default"] for c in ctx.cameras}
    cams = [c for c in ctx.cameras if not gate(ctx, c, TEST) and dm[c["key"]]]
    reqs = [(c, dm[c["key"]]) for c in cams]
    pred = predicted(snap, cache, reqs) if reqs else {"domains": []}
    order = sorted(cams, key=lambda c: (domain_of(snap, c["key"]) or "", c["key"]))
    runs, events = [], []
    for rep in range(ctx.args.multi_reps):
        for kind, seq in (("together", cams), ("staggered", order)):
            jobs = []
            for i, c in enumerate(seq):
                od = ctx.test_dir(TEST, f"A_{kind}_{rep}", ctx.slug(c))
                jobs.append(_cap_job(ctx, c, dm[c["key"]], SECS, od,
                                     delay=0.0 if kind == "together" else 1.5 * i))
            ctx.log(f"phase A rep {rep + 1} {kind}: {len(jobs)} camera(s)")
            rs = ctx.camcmd_parallel(jobs)
            out = [_summ(r, c, dm[c["key"]]) for r, c in zip(rs, seq)]
            streamed = [o["camera"] for o in out if o["ok"]]
            for o in out:
                if not o["ok"]:
                    cc = classify_ctx(snap, pred, o["camera"], [k for k in streamed if k != o["camera"]])
                    o["classification"] = apis.classify(o["error"] or {"stage": "first_frame"}, cc)
                    o["classification_context"] = cc
                    cls = (o["classification"] or {}).get("class") or ""
                    if not (cc["other_streaming_in_domain"] or cls.startswith("bandwidth")):
                        continue  # not a contention event (e.g. a Kiyo device error): reported, not a G-BW event
                    events.append({"pair": f"A:{kind}:{rep}:{o['name']}", "api": "v4l2",
                                   "predicted_verdict": cc["predicted_verdict"], "observed_refused": True,
                                   "classified_class": (o["classification"] or {}).get("class"),
                                   "expected_bandwidth": bool(cc["other_streaming_in_domain"]),
                                   "message_ports_other_domains": None, "retry_ok": None})
            runs.append({"rep": rep, "kind": kind, "results": out,
                         "prediction": [{k: d.get(k) for k in ("key", "pct_microframe", "verdict", "members")}
                                        for d in pred.get("domains", [])]})
    return runs, events


def _ports_other_domains(msg: dict[str, Any], dom: str) -> bool | None:
    ports = [p for g in msg.get("suggestions") or [] for p in g.get("ports") or []]
    if not ports:
        return None
    return all(p.get("domain_key") != dom for p in ports)


def pair_variants(snap, cache, a_cam, b_cam, ctx=None) -> list[tuple[str, dict | None, dict | None]]:
    """The predicted-'over' and predicted-'fits' mode pairs for one same-domain pair (plan 6.2 MULTI).

    With ``ctx`` and the mode scope on (the default), candidates are the cameras' in-scope MJPEG modes (see
    ``scoped_pair_variants``; a missing 'fits' entry means no in-scope pair fits). Without ``ctx`` or with
    --all-modes: the earlier candidates, each camera's default/small/large modes; the first whose prediction
    (ModeAltCache learned in L-MJPEG / L-CYC, else the largest alt) gives the wanted verdict is used. Lowering B is
    preferred for 'fits' (the message's "lower {B}" alternative), then lowering A (e.g. when B is the generic
    camera, 3069 B at every mode)."""
    if ctx is not None and not scope.settings(ctx.args)["all_modes"]:
        return scoped_pair_variants(ctx, snap, cache, a_cam, b_cam)[0]
    dom = domain_of(snap, b_cam["key"])
    ma = a_cam["modes"]
    mb = b_cam["modes"]

    def verdict(x, y):
        if not x or not y:
            return None
        pr = predicted(snap, cache, [(a_cam, x), (b_cam, y)])
        return next((d["verdict"] for d in pr["domains"] if d["key"] == dom), None)

    def first(cands, want):
        seen = set()
        for x, y in cands:
            k = (mode_text(x), mode_text(y))
            if not x or not y or k in seen:
                continue
            seen.add(k)
            if verdict(x, y) == want:
                return x, y, True
        return None
    over = first([(ma["default"], mb["default"]), (ma["large"], mb["default"]), (ma["default"], mb["large"]),
                  (ma["large"], mb["large"])], "over")
    fits = first([(ma["default"], mb["small"]), (ma["small"], mb["default"]), (ma["small"], mb["small"])], "fits")
    out = [("over",) + (over[:2] if over else (ma["default"], mb["default"])),
           ("fits",) + (fits[:2] if fits else (ma["default"], mb["small"] or mb["default"]))]
    return out


MAX_SCOPED_MODES = 12   # per camera, for the in-scope pair search (C922: 4 modes at the default scope)


def scoped_pair_variants(ctx, snap, cache, a_cam, b_cam) -> tuple[list[tuple[str, dict, dict]], dict[str, Any]]:
    """(variants, notes) among in-scope modes only. 'over': (default, default), (large, default), (default, large),
    (large, large), then every other in-scope pair in falling predicted load, first predicted 'over'; when none is,
    the defaults run anyway and their real prediction labels the event. 'fits': lowering B first, then A, then every
    other in-scope pair in rising predicted load, first predicted 'fits'; when none is, there is no 'fits' variant
    and notes['fits'] says 'fits-side not testable under mode scope'."""
    dom = domain_of(snap, b_cam["key"])
    pa, pb = scope.picks(ctx, a_cam), scope.picks(ctx, b_cam)
    notes: dict[str, Any] = {"mode_scope": {a_cam["key"]: pa["record"], b_cam["key"]: pb["record"]}}
    if not pa["default"] or not pb["default"]:
        notes["skipped"] = "untested (scope): " + ", ".join(
            c["name"] for c, p in ((a_cam, pa), (b_cam, pb)) if not p["default"]) + " has no in-scope MJPEG mode"
        return [], notes
    la, lb = pa["modes"][:MAX_SCOPED_MODES], pb["modes"][:MAX_SCOPED_MODES]
    memo: dict[tuple, tuple] = {}

    def pred(x, y):
        k = (mode_text(x), mode_text(y))
        if k not in memo:
            pr = predicted(snap, cache, [(a_cam, x), (b_cam, y)])
            d = next((d for d in pr["domains"] if d["key"] == dom), {})
            memo[k] = (d.get("verdict"), d.get("pct_microframe") or 0.0)
        return memo[k]
    every = [(x, y) for x in la for y in lb]
    over_c = [(pa["default"], pb["default"]), (pa["large"], pb["default"]), (pa["default"], pb["large"]),
              (pa["large"], pb["large"])] + sorted(every, key=lambda xy: -pred(*xy)[1])
    fits_c = [(pa["default"], pb["low"]), (pa["low"], pb["default"]), (pa["low"], pb["low"])] + \
        sorted(every, key=lambda xy: pred(*xy)[1])
    over = next(((x, y) for x, y in over_c if x and y and pred(x, y)[0] == "over"), None)
    fits = next(((x, y) for x, y in fits_c if x and y and pred(x, y)[0] == "fits"), None)
    notes["n_pairs_considered"] = len(every)
    notes["predictions"] = [{"A": a, "B": b, "verdict": v, "pct_microframe": pct} for (a, b), (v, pct) in memo.items()]
    out: list[tuple[str, dict, dict]] = []
    if over:
        out.append(("over", *over))
    else:
        out.append(("over", pa["default"], pb["default"]))
        notes["over"] = "no in-scope pair is predicted over: the defaults run, labelled by their prediction"
    if fits:
        out.append(("fits", *fits))
    else:
        notes["fits"] = ("fits-side not testable under mode scope: no in-scope mode pair is predicted to fit in this "
                         "shared domain (the predicted-over pairs, phase A and the cross-domain pair still run)")
    return out, notes


def run_pair(ctx, label: str, a_cam, a_mode, b_cam, b_mode, cache) -> dict[str, Any]:
    """A streams; B starts while A runs; if B fails: retry once while A runs, then B alone after A stops."""
    base = ctx.test_dir(TEST, label)
    snap0 = ctx.topology or topology.collect_snapshot(ctx.cameras)
    pred = predicted(snap0, cache, [(a_cam, a_mode), (b_cam, b_mode)])
    dom = domain_of(snap0, b_cam["key"])
    pv = next((d for d in pred["domains"] if d["key"] == dom), {})
    out: dict[str, Any] = {"label": label, "A": mode_text(a_mode), "B": mode_text(b_mode), "domain": dom,
                           "predicted": {"verdict": pv.get("verdict"), "pct_microframe": pv.get("pct_microframe"),
                                         "load_us": pv.get("predicted_load_us"), "requests": pred.get("requests")}}
    a_job = _cap_job(ctx, a_cam, a_mode, 12.0, base / "A")
    res_a: dict[str, Any] = {}
    with ctx.camera_lock() as ok:
        if not ok:
            out["error"] = "camera lock not acquired"
            return out
        th = threading.Thread(target=lambda: res_a.update(ctx.run_child(a_job["argv"], a_job["timeout_s"])),
                              daemon=True)
        th.start()
        time.sleep(3.0)
        snap_mid = topology.collect_snapshot(ctx.cameras)   # A's granted alt is visible in sysfs now
        b1 = ctx.run_child(_cap_job(ctx, b_cam, b_mode, 2.0, base / "B1")["argv"], 25)
        s_b1 = _summ(b1, b_cam, b_mode)
        s_b2 = s_b3 = None
        if not s_b1["ok"]:
            time.sleep(0.5)
            b2 = ctx.run_child(_cap_job(ctx, b_cam, b_mode, 2.0, base / "B2_retry_while_A")["argv"], 25)
            s_b2 = _summ(b2, b_cam, b_mode)
        th.join(timeout=60)
        s_b4 = None
        if not s_b1["ok"]:
            b3 = ctx.run_child(_cap_job(ctx, b_cam, b_mode, 2.0, base / "B3_alone_after_A")["argv"], 25)
            s_b3 = _summ(b3, b_cam, b_mode)
            if not s_b3["ok"]:
                # "retry once": a refused start can be followed by one zero-frame start (REPORT finding 19)
                time.sleep(0.5)
                b4 = ctx.run_child(_cap_job(ctx, b_cam, b_mode, 2.0, base / "B4_alone_retry")["argv"], 25)
                s_b4 = _summ(b4, b_cam, b_mode)
    s_a = _summ(res_a, a_cam, a_mode) if res_a else {"ok": False, "error": "A did not finish"}
    a_alt = next((c.get("current_alt") for c in snap_mid["cameras"] if c["key"] == a_cam["key"]), None)
    retry_ok = None if s_b3 is None else bool(s_b3["ok"] or (s_b4 or {}).get("ok"))
    out.update({"A_result": s_a, "B_first": s_b1, "B_retry_while_A": s_b2, "B_alone_after_A": s_b3,
                "B_alone_retry": s_b4, "retry_ok": retry_ok,
                "zero_frame_start_after_refusal": bool(s_b3 is not None and not s_b3["ok"] and (s_b4 or {}).get("ok")),
                "A_alt_midstream": a_alt, "midstream_domains": [
                    {k: d.get(k) for k in ("key", "cameras", "load_us", "pct_microframe", "verdict")}
                    for d in tm.compute_domains(snap_mid) if d["key"] == dom]})
    refused = not s_b1["ok"]
    out["observed_refused"] = refused
    if refused:
        cc = {"api": "v4l2", "other_streaming_in_domain": bool(s_a.get("ok")) and domain_of(snap0, a_cam["key"]) == dom,
              "predicted_verdict": pv.get("verdict"), "stage": (s_b1.get("error") or {}).get("stage")}
        failure = apis.classify(s_b1.get("error") or {"stage": "first_frame"}, cc) or {}
        out["classification"] = failure
        failure = {**failure, "loser": b_cam["key"]}
        # message from the midstream snapshot: A's open pipes plus B's requested cost
        ex = tm.explain(snap_mid, [{"camera_key": a_cam["key"], "mode": mode_text(a_mode)},
                                   {"camera_key": b_cam["key"], "mode": mode_text(b_mode)}], cache, failure)
        out["messages"] = [{"message": m["message"], "moving_camera_key": m["moving_camera_key"],
                            "suggestions": m["suggestions"], "alternatives": m["alternatives"],
                            "ports_only_other_domains": _ports_other_domains(m, m["domain_key"])}
                           for m in ex["messages"]]
        if not ex["messages"]:
            # the prediction did not call this domain 'over': still show what the builder says for the domain
            out["message_note"] = "prediction did not flag the domain 'over' (a false 'fits' if this was bandwidth)"
    return out


def run(ctx) -> dict[str, Any]:
    res = ctx.new_result(TEST)
    errors: list[dict] = []
    snap = ctx.topology if ctx.topology and not ctx.topology.get("error") else topology.collect_snapshot(ctx.cameras)
    ctx.topology = snap
    cache = ctx.mode_alt_cache
    meas: dict[str, Any] = {"mode_alt_cache": cache.entries,
                            "mode_scope": scope.test_record(ctx, ctx.cameras)}
    runs_a, events = phase_a(ctx, snap, cache, errors)
    meas["phase_a"] = runs_a
    pairs_out = []
    for a_cam, b_cam in domain_pairs(ctx, snap):
        if gate(ctx, a_cam, TEST) or gate(ctx, b_cam, TEST):
            pairs_out.append({"pair": [a_cam["key"], b_cam["key"]], "skipped": "camera busy"})
            continue
        if scope.settings(ctx.args)["all_modes"]:
            variants, vnotes = pair_variants(snap, cache, a_cam, b_cam), {"mode_scope": "--all-modes"}
        else:
            variants, vnotes = scoped_pair_variants(ctx, snap, cache, a_cam, b_cam)
        pair_rec = {"pair": [a_cam["key"], b_cam["key"]], "variant_selection": vnotes}
        if vnotes.get("skipped"):
            pairs_out.append({**pair_rec, "skipped": vnotes["skipped"]})
            continue
        if vnotes.get("fits"):
            pairs_out.append({**pair_rec, "variant": "fits", "skipped": vnotes["fits"], "not_testable": True})
        for kind, ma, mb in variants:
            if not ma or not mb:
                continue
            label = f"B_{kind}_{ctx.slug(a_cam)[:24]}__{ctx.slug(b_cam)[:24]}"
            ctx.log(f"pair {kind}: {a_cam['name']} {mode_text(ma)} + {b_cam['name']} {mode_text(mb)}")
            p = run_pair(ctx, label, a_cam, ma, b_cam, mb, cache)
            p["variant"] = kind
            p["variant_selection"] = {k: v for k, v in vnotes.items() if k != "predictions"}
            pairs_out.append(p)
            if p.get("observed_refused"):
                msgs = p.get("messages") or []
                events.append({"pair": label, "api": "v4l2", "predicted_verdict": p["predicted"]["verdict"],
                               "observed_refused": True,
                               "classified_class": (p.get("classification") or {}).get("class"),
                               "expected_bandwidth": True,
                               "message_ports_other_domains": (all(m["ports_only_other_domains"] is not False
                                                                   for m in msgs) if msgs else None),
                               "retry_ok": p.get("retry_ok")})
            else:
                events.append({"pair": label, "api": "v4l2", "predicted_verdict": p["predicted"]["verdict"],
                               "observed_refused": False, "classified_class": None, "expected_bandwidth": False})
    meas["pairs"] = pairs_out
    cp = cross_pair(ctx, snap)
    if cp and not (gate(ctx, cp[0], TEST) or gate(ctx, cp[1], TEST)):
        if scope.settings(ctx.args)["all_modes"]:
            ma, mb = cp[0]["modes"]["large"], cp[1]["modes"]["large"]
        else:
            ma, mb = scope.picks(ctx, cp[0])["large"], scope.picks(ctx, cp[1])["large"]
        if not (ma and mb):
            meas["cross_domain_pair"] = {"skipped": "untested (scope): no in-scope MJPEG mode on " + ", ".join(
                c["name"] for c, m in ((cp[0], ma), (cp[1], mb)) if not m)}
        if ma and mb:
            ctx.log(f"cross-domain pair: {cp[0]['name']} {mode_text(ma)} + {cp[1]['name']} {mode_text(mb)}")
            p = run_pair(ctx, "C_cross_domain", cp[0], ma, cp[1], mb, cache)
            meas["cross_domain_pair"] = p
            events.append({"pair": "cross_domain", "api": "v4l2", "predicted_verdict": p["predicted"]["verdict"],
                           "observed_refused": bool(p.get("observed_refused")),
                           "classified_class": (p.get("classification") or {}).get("class"),
                           "expected_bandwidth": False})
    meas["events"] = events
    labels_raw = None
    if snap.get("ports"):
        labels_raw = not any(p["label_parts"].get("panel") for p in snap["ports"])
    v = rating.rate_bw(events, labels_raw=labels_raw)
    results.finish_result(res, measurements=meas, verdicts={"G-BW": v}, errors=errors)
    return res
