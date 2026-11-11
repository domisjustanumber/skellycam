"""M-CTRL-LIST: every control and range per path vs the descriptors' bmControls (plan 6.2 CTRL-LIST; macos.md
MX4a/b). AVFoundation path: is*ModeSupported flags and current modes (macOS has only auto/locked modes, no
absolute values). Endpoint-0 path (only with --ep0): GET_INFO/MIN/MAX/RES/DEF/CUR to the VideoControl interface
with no claim (helpers/mac_ep0.py). Extension-unit controls (Kiyo HDR/FoV, Logitech XUs) are listed from the
descriptor only and never read or set blind. Opens no stream.

per_control (for M-CTRL-EFFECT's G-CTRL criterion 1, common/rating.py rate_ctrl contract): per camera,
{"avf": {exposure|wb|focus: {listed, descriptor_control, advertised_in_descriptor, range_matches_descriptor}},
 "ep0": {name: {listed, advertised_in_descriptor, listed_by_device, ok, range_well_formed,
                range_matches_descriptor, min, max, res, def}}, "descriptor_controls": [...] | None}.
macOS reading of "listed with the descriptor's range": UVC descriptors carry only bmControls (support), no ranges,
so an ep0 control is 'listed' when the descriptor advertises it AND GET_INFO says the device implements it AND
every GET_* answered; its range 'matches' when GET_MIN/MAX/RES/DEF form a valid range (min <= def <= max,
res >= 1). AVFoundation has no ranges: its exposure/WB/focus lock is 'listed' when supported, and 'matches the
descriptor' when the descriptor advertises the matching auto control (auto_exposure_mode,
white_balance_temperature_auto, focus_auto); without descriptors that is None (not fed, blocks 'yes')."""
from __future__ import annotations

import suitectx  # noqa: F401
from common import rating, results

NAME = "M-CTRL-LIST"
AVF_TO_UVC = {"exposure": "auto_exposure_mode", "wb": "white_balance_temperature_auto", "focus": "focus_auto"}
RANGE_KINDS = ("range",)


def descriptor_controls(entities: dict | None) -> list[str] | None:
    """CT + PU control names the descriptor's bmControls advertise (None when no descriptor is known)."""
    if not entities or (entities.get("camera_terminal") is None and entities.get("processing_unit") is None):
        return None
    out = []
    for unit in ("camera_terminal", "processing_unit"):
        out += list((entities.get(unit) or {}).get("controls") or [])
    return out


def range_well_formed(row: dict) -> bool | None:
    """min <= def <= max and res >= 1 for a 'range' control; None for other kinds or when not read."""
    if row.get("kind") not in RANGE_KINDS:
        return None
    mn, mx, rs, df = (row.get(k) for k in ("min", "max", "res", "def"))
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (mn, mx, rs, df)):
        return False if row.get("ok") is False or any(v is None for v in (mn, mx, rs, df)) else None
    return bool(mn <= df <= mx and rs >= 1)


def per_control_record(avf_flags: dict | None, ep0_rows: list[dict] | None, desc_ctrls: list[str] | None) -> dict:
    """Pure: the per-control listing inputs of G-CTRL criterion 1 (module docstring)."""
    out: dict = {"descriptor_controls": desc_ctrls, "avf": {}, "ep0": {} if ep0_rows is not None else None}
    adv_set = set(desc_ctrls) if desc_ctrls is not None else None
    for which, uvc_name in AVF_TO_UVC.items():
        sup = ((avf_flags or {}).get(f"{which}_modes_supported") or {}).get("locked") if isinstance(avf_flags, dict) \
            else None
        adv = (uvc_name in adv_set) if adv_set is not None else None
        out["avf"][which] = {"listed": (sup is True) if sup is not None else None, "descriptor_control": uvc_name,
                             "advertised_in_descriptor": adv,
                             "range_matches_descriptor": (True if (adv and sup is True) else
                                                          (False if adv and sup is not True else None)),
                             "note": "AVFoundation offers a lock mode, no range"}
    for r in ep0_rows or []:
        rf = range_well_formed(r)
        listed = bool(r.get("advertised_in_descriptor") and r.get("listed_by_device") and r.get("ok"))
        out["ep0"][r["name"]] = {"listed": listed, "advertised_in_descriptor": r.get("advertised_in_descriptor"),
                                 "listed_by_device": r.get("listed_by_device"), "ok": r.get("ok"), "kind": r.get("kind"),
                                 "range_well_formed": rf,
                                 "range_matches_descriptor": (bool(r.get("advertised_in_descriptor")) and rf)
                                 if rf is not None else None,
                                 **{k: r.get(k) for k in ("min", "max", "res", "def")}}
    return out


def plan(ctx) -> list[str]:
    out = ["mac_avf.py ctrl-avf per camera (flags only; no lock, no set)"]
    out.append("mac_ep0.py descriptors (if not cached) + ctrl-list per camera" if ctx.ep0_enabled
               else "ep0 off: UVC ranges not read (add --ep0)")
    return out


def run(ctx) -> dict:
    res = ctx.new_result(NAME)
    errors: list = []
    per = []
    store = ctx.store.setdefault("ctrl_list", {})
    pc_store = ctx.store.setdefault("ctrl_list_per_control", {})
    for cam in ctx.cameras:
        rec: dict = {"key": cam["key"], "is_kiyo": cam.get("is_kiyo")}
        if cam.get("unique_id"):
            r = ctx.avf(["ctrl-avf", "--device", cam["unique_id"]], 30, label=f"ctrl-avf {cam['key']}")
            j = r.get("json") or {}
            rec["avf"] = j.get("flags") if j.get("ok") else {"error": j.get("error"), "timed_out": r.get("timed_out"),
                                                              "rc": r.get("rc")}
        else:
            rec["avf"] = "not listed by AVFoundation"
        if ctx.ep0_enabled and cam.get("location_hex"):
            if not ctx.cam_desc(cam):
                d = ctx.ep0(cam, "descriptors", timeout_s=30)
                dj = d.get("json") or {}
                if dj.get("ok"):
                    ctx.save_desc(cam, dj)
                else:
                    rec["descriptor_error"] = {"error": dj.get("error"), "timed_out": d.get("timed_out")}
            extra = ["--all-selectors"] if not ctx.args.quick else []
            c = ctx.ep0(cam, "ctrl-list", extra, timeout_s=90)
            cj = c.get("json") or {}
            rec["ep0"] = {"ok": cj.get("ok"), "setup": cj.get("setup"), "error": cj.get("error"),
                          "timed_out": c.get("timed_out"), "rc": c.get("rc"), "controls": cj.get("controls"),
                          "extension_units": cj.get("extension_units"), "n_advertised": cj.get("n_advertised"),
                          "n_ok": cj.get("n_ok")}
            rows = cj.get("controls") or []
            adv = [x for x in rows if x.get("advertised_in_descriptor")]
            rec["comparison"] = {
                "advertised": len(adv), "listed_by_device": sum(1 for x in adv if x.get("listed_by_device")),
                "advertised_but_failing": [x["name"] for x in adv if not x.get("ok")],
                "unadvertised_but_answering": [x["name"] for x in rows if not x.get("advertised_in_descriptor")
                                               and x.get("listed_by_device")],
                "rc_names": sorted({cl.get("rc_name") for x in rows for cl in x.get("calls") or [] if cl.get("rc_name")})}
            store[cam["key"]] = {x["name"]: {k: x.get(k) for k in ("min", "max", "res", "def", "cur", "info",
                                                                   "modes_supported", "ok")}
                                 for x in rows if x.get("ok")}
            if c.get("timed_out"):
                errors.append({"camera": cam["key"], "warning": "ep0 ctrl-list timed out (recorded; the Kiyo is "
                                                                 "known to stop answering control requests)"})
        else:
            rec["ep0"] = "not run (ep0 off)" if not ctx.ep0_enabled else "no locationID"
        ep0_rows = (rec["ep0"].get("controls") or []) if isinstance(rec["ep0"], dict) else None
        desc = ctx.cam_desc(cam) or {}
        rec["per_control"] = per_control_record(rec["avf"] if isinstance(rec.get("avf"), dict) and
                                                "error" not in rec["avf"] else None, ep0_rows,
                                                descriptor_controls(desc.get("entities")))
        pc_store[cam["key"]] = rec["per_control"]
        per.append(rec)
    m = {"cameras": per}
    listed = sum((p.get("comparison") or {}).get("listed_by_device", 0) for p in per)
    v = {"G-CTRL": rating.untested("listing only; set/readback/effect is M-CTRL-EFFECT",
                                   {"ep0": ctx.ep0_enabled, "ep0_controls_listed": listed})}
    return results.finish_result(res, m, v, errors)
