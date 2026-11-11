"""L-CTRL-LIST: full VIDIOC_QUERY_EXT_CTRL walk (NEXT_CTRL | NEXT_COMPOUND) with menus and current values,
compared with the descriptors' Camera Terminal / Processing Unit bmControls (plan 6.2 CTRL-LIST, G-CTRL).

QUERY_EXT_CTRL makes uvcvideo ask the camera GET_INFO/MIN/MAX/RES/DEF the first time (control transfers): this is
where a Kiyo Pro in its bad state shows EPIPE/ETIMEDOUT, recorded per control with its time. Ranges come from the
camera (descriptors carry none): the range half of G-CTRL criterion 1 on Linux is "the camera answered a
consistent GET_MIN/MAX/RES/DEF range" (analysis.ctrl_per_control). ``measurements.cameras[key].per_control`` (also
ctx.shared["ctrl_list"]) is what L-CTRL-EFFECT feeds into rating.rate_ctrl criterion 1 (listed + range).
Extension-unit controls (Kiyo HDR/FoV, Logitech XUs) are recorded from the descriptors but not queried or set
(plan 2.6 G-CTRL).
"""
from __future__ import annotations

from typing import Any

from common import rating, results
import analysis
from suitectx import combine
from tutil import outcome, worker_error

TEST = "L-CTRL-LIST"
INFO = {"goal": "G-CTRL", "summary": "QUERY_EXT_CTRL walk + menus + values vs descriptor bmControls",
        "opens_cameras": "controls only (no streaming)"}


def plan(ctx) -> dict[str, Any]:
    return {"child_runs": len(ctx.cameras), "est_seconds": 10 * len(ctx.cameras),
            "steps": ["camworker controls (walk + G_EXT_CTRLS) per camera", "map descriptor bmControls -> CIDs"]}


def compare(walk: list[dict[str, Any]], desc: dict[str, Any]) -> dict[str, Any]:
    ids = {c["id"] for c in walk if c.get("id") is not None}
    rows = []
    for unit, names in (("CT", desc.get("ct_controls") or []), ("PU", desc.get("pu_controls") or [])):
        for n in names:
            cids = analysis.DESC_TO_CID.get(n)
            if cids is None:
                rows.append({"unit": unit, "descriptor_control": n, "v4l2_ids": None,
                             "listed": None, "note": "no standard uvcvideo mapping (expected absent)"
                             if n in analysis.DESC_UNMAPPED else "unknown mapping"})
                continue
            rows.append({"unit": unit, "descriptor_control": n, "v4l2_ids": [f"0x{x:08x}" for x in cids],
                         "listed": all(x in ids for x in cids)})
    mapped = {x for ids_ in analysis.DESC_TO_CID.values() for x in ids_}
    desc_ids = {x for r in rows if r["v4l2_ids"] for x in (int(i, 16) for i in r["v4l2_ids"])}
    extra = [{"id": c["id_hex"], "name": c["name"], "type": c["type"]} for c in walk
             if c.get("id") is not None and c["type"] != "ctrl_class" and c["id"] not in desc_ids]
    return {"rows": rows, "missing": [r for r in rows if r["listed"] is False],
            "extra_in_v4l2": extra, "n_descriptor_controls": len(rows),
            "n_listed": sum(1 for r in rows if r["listed"]), "unmapped": [r for r in rows if r["listed"] is None],
            "known_cids": len(mapped)}


def run(ctx) -> dict[str, Any]:
    res = ctx.new_result(TEST)
    errors: list[dict] = []
    per_cam: dict[str, Any] = {}
    verdicts: dict[str, Any] = {}
    for c in ctx.cameras:
        r = ctx.camcmd(ctx.worker_cmd("controls", "--device", c["node"], "--op-timeout-s", "12",
                                     "--total-timeout-s", "165"), timeout_s=180)
        j = r.get("json") or {}
        err = worker_error(r)
        walk = j.get("controls") or []
        entry: dict[str, Any] = {"child": outcome(r), "walk_ms": j.get("walk_ms"), "elapsed_ms": j.get("elapsed_ms")}
        if err:
            entry["error"] = err
            errors.append({"camera": c["key"], "stage": "controls", "error": err, "is_kiyo": c["is_kiyo"]})
        entry["controls"] = walk
        cmp_ = compare(walk, c["descriptors"])
        entry["descriptor_compare"] = cmp_
        entry["extension_units"] = c["descriptors"].get("extension_units")
        get_err = [{"id": x["id_hex"], "name": x["name"], "errno": x["get_errno"], "ms": x.get("get_ms")}
                   for x in walk if x.get("get_errno")]
        slow = [{"id": x["id_hex"], "name": x["name"], "ms": x.get("get_ms")} for x in walk
                if (x.get("get_ms") or 0) > 500]
        # QUERY_EXT_CTRL failures (the walk could not read GET_INFO/MIN/MAX of some control: Kiyo symptom)
        q_err = [{k: x.get(k) for k in ("after_id", "probe_id", "short", "query_errno", "fallback")}
                 for x in walk if x.get("query_errno")]
        entry["get_errors"], entry["slow_gets_over_500ms"] = get_err, slow
        entry["query_errors"], entry["walk_partial"] = q_err, j.get("walk_partial")
        per_control = analysis.ctrl_per_control(walk, c["descriptors"])
        entry["per_control"] = per_control
        ctx.shared.setdefault("ctrl_list", {})[c["key"]] = {"per_control": per_control,
                                                            "walk_partial": j.get("walk_partial"),
                                                            "query_errors": q_err, "error": err}
        if walk:
            ctx.shared.setdefault("controls", {})[c["key"]] = walk
        per_cam[c["key"]] = entry
        if not walk:
            verdicts[c["key"]] = rating.untested("no control listed", err)
            continue
        bad_range = [{"control": n, "problems": pc.get("problems")} for n, pc in per_control.items()
                     if pc.get("listed") and pc.get("range_ok") is False]
        crit = [{"criterion": "every descriptor control (with a uvcvideo mapping) is listed",
                 "met": not cmp_["missing"], "detail": [m["descriptor_control"] for m in cmp_["missing"]]},
                {"criterion": "every listed descriptor control has a consistent range from the camera "
                              "(GET_MIN/MAX/RES/DEF; UVC descriptors carry no ranges)",
                 "met": not bad_range, "detail": bad_range[:10]},
                {"criterion": "every readable control's current value read without error", "met": not get_err,
                 "detail": get_err[:10]},
                {"criterion": "QUERY_EXT_CTRL walk completed without a failing query", "met": not q_err
                 and not j.get("walk_partial"), "detail": q_err[:10]}]
        ok = not cmp_["missing"] and not get_err and not err and not q_err and not bad_range
        verdicts[c["key"]] = {"rating": "yes" if ok else "partial", "criteria": crit,
                              "evidence": {"n_listed": cmp_["n_listed"], "n_descriptor": cmp_["n_descriptor_controls"],
                                           "n_walk": len(walk)}}
    results.finish_result(res, measurements={"cameras": per_cam},
                          verdicts={"G-CTRL-LIST": combine(verdicts, "control listing") if verdicts
                                    else rating.untested("no camera")}, errors=errors)
    return res
