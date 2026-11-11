"""W-CTRL-LIST: every control and range per API vs the descriptors' bmControls (plan sections 2.1, 6.2).

Per camera (the Kiyo included), READ-ONLY:
  * descriptors: Camera Terminal and Processing Unit bmControls (naming/usbdesc.py names; shared descriptor cache);
  * ``wincam controls --api mf --read-only`` (IAMCameraControl / IAMVideoProcAmp QI'd from the activated
    IMFMediaSource, IKsControl fallback and cross-check) and ``wincam controls --api ds --read-only`` (same on the
    bound DirectShow filter): every KSPROPERTY_VIDCAP_CAMERACONTROL id 0..23 and VIDEOPROCAMP id 0..15, with
    min/max/step/default, caps flags, current value/flags and every HRESULT. Under camlock, timeouts inside and out.
Diffs per camera:
  * descriptor control -> KS id(s) (e.g. auto_exposure_mode -> exposure AUTO flag, pantilt_absolute -> pan, tilt,
    pantilt): listed through MF? through DS? missing / extra (e.g. focal_length comes from the terminal's
    wObjectiveFocalLength fields, color_enable has no UVC bit);
  * auto-capable controls: does caps_flags include AUTO where the descriptor has the auto bit?
  * MF vs DS: min / max / step / default / caps flags / current value and flags per supported control;
  * wincam's IAM-vs-KS range agreement and degenerate ranges (e.g. auto_exposure_priority 0..0).
Verdict: "ctrl_list_equivalence" (answers "same controls in DS and MF?"): yes = every descriptor control listed in
both APIs with identical ranges/defaults/flags; G-CTRL itself (set, readback, image effect) is W-CTRL-EFFECT's, which
reads ``per_control`` from this result for its criterion 1 (listed with descriptor support, MF and DS ranges equal).
No G-CTRL cell is emitted here (it read as a failed "G-CTRL / all / untested" row; ctrl_id_env B7): the listing counts
are in measurements.listed_counts. A camera whose every device-backed GET fails (wincam ``device_not_answering``,
rc 4) cannot be compared (its equivalence is None, not False) and is recorded in measurements.not_answering.
Offline: ``python w_ctrl_list.py --reanalyze <run_dir>`` rebuilds per_control and the verdicts (without the G-CTRL
cell) from a stored W-CTRL-LIST.json into <run_dir>/reanalysis/W-CTRL-LIST.json.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _enum_util as U  # noqa: E402
from common import results  # noqa: E402
from w_fmt import slug  # noqa: E402

TEST_ID = "W-CTRL-LIST"

# descriptor control name -> [(KS key, aspect)]; aspect "value" (the control itself) or "auto" (its AUTO flag)
CT_MAP = {
    "scanning_mode": [("cc.scanmode", "value")], "auto_exposure_mode": [("cc.exposure", "auto")],
    "auto_exposure_priority": [("cc.auto_exposure_priority", "value")],
    "exposure_time_absolute": [("cc.exposure", "value")], "exposure_time_relative": [("cc.exposure_relative", "value")],
    "focus_absolute": [("cc.focus", "value")], "focus_relative": [("cc.focus_relative", "value")],
    "iris_absolute": [("cc.iris", "value")], "iris_relative": [("cc.iris_relative", "value")],
    "zoom_absolute": [("cc.zoom", "value")], "zoom_relative": [("cc.zoom_relative", "value")],
    "pantilt_absolute": [("cc.pan", "value"), ("cc.tilt", "value"), ("cc.pantilt", "value")],
    "pantilt_relative": [("cc.pan_relative", "value"), ("cc.tilt_relative", "value"), ("cc.pantilt_relative", "value")],
    "roll_absolute": [("cc.roll", "value")], "roll_relative": [("cc.roll_relative", "value")],
    "focus_auto": [("cc.focus", "auto")], "privacy": [("cc.privacy", "value")],
    "focus_simple": [], "window": [], "region_of_interest": [],
}
PU_MAP = {
    "brightness": [("pa.brightness", "value")], "contrast": [("pa.contrast", "value")], "hue": [("pa.hue", "value")],
    "saturation": [("pa.saturation", "value")], "sharpness": [("pa.sharpness", "value")],
    "gamma": [("pa.gamma", "value")], "white_balance_temperature": [("pa.white_balance", "value")],
    "white_balance_component": [("pa.white_balance_component", "value")],
    "backlight_compensation": [("pa.backlight_compensation", "value")], "gain": [("pa.gain", "value")],
    "power_line_frequency": [("pa.powerline_frequency", "value")], "hue_auto": [("pa.hue", "auto")],
    "white_balance_temperature_auto": [("pa.white_balance", "auto")],
    "white_balance_component_auto": [("pa.white_balance_component", "auto")],
    "digital_multiplier": [("pa.digital_multiplier", "value")],
    "digital_multiplier_limit": [("pa.digital_multiplier_limit", "value")],
    "analog_video_standard": [], "analog_video_lock_status": [], "contrast_auto": [("pa.contrast", "auto")],
}
COMPARE_FIELDS = ("min", "max", "step", "default", "caps_flags", "value", "flags", "value2")
RANGE_FIELDS = ("min", "max", "step", "default", "caps_flags")   # the range part (value/flags are current state)


def per_control_listing(mapping: list[dict], ix: dict, diffs: list[dict]) -> dict:
    """{ks key: {listed_mf, listed_ds, descriptor_backed, descriptor_listed_ok, ranges_equal_mf_ds}} for every control
    supported through either API: the input W-CTRL-EFFECT's criterion 1 needs (instead of a hard-coded True)."""
    out = {}
    keys = {k for a in ("mf", "ds") for k, c in (ix.get(a) or {}).items() if c.get("supported")}
    for k in sorted(keys):
        rows = [r for r in mapping if r["ks"] == k and r["aspect"] == "value"]
        a, b = (ix.get("mf") or {}).get(k) or {}, (ix.get("ds") or {}).get(k) or {}
        rdiff = [d for d in diffs if d["control"] == k and d["field"] in RANGE_FIELDS + ("supported",)]
        out[k] = {"listed_mf": bool(a.get("supported")), "listed_ds": bool(b.get("supported")),
                  "descriptor_backed": bool(rows),
                  "descriptor_listed_ok": (all(r.get("mf") and r.get("ds") for r in rows) if rows else None),
                  "ranges_equal_mf_ds": (not rdiff) if (a and b) else None,
                  "range_differences": rdiff or None}
    return out


def descriptor_controls(desc: dict | None) -> dict:
    cfg = (desc or {}).get("configuration") or {}
    units = ((cfg.get("uvc") or {}).get("units")) or []
    out = {"camera_terminal": [], "processing_unit": [], "extension_units": [], "focal_length_fields": None,
           "bcdUVC": (cfg.get("uvc") or {}).get("bcdUVC")}
    for u in units:
        st = u.get("subtype")
        if st == "VC_INPUT_TERMINAL" and u.get("wTerminalType") == "ITT_CAMERA":
            out["camera_terminal"] += u.get("controls") or []
            out["camera_terminal_bmControls"] = u.get("bmControls")
            out["focal_length_fields"] = {k: u.get(k) for k in ("wObjectiveFocalLengthMin", "wObjectiveFocalLengthMax",
                                                                "wOcularFocalLength")}
        elif st == "VC_PROCESSING_UNIT":
            out["processing_unit"] += u.get("controls") or []
            out["processing_unit_bmControls"] = u.get("bmControls")
        elif st == "VC_EXTENSION_UNIT":
            out["extension_units"].append({k: u.get(k) for k in ("bUnitID", "guidExtensionCode", "known_as",
                                                                 "bNumControls", "bmControls")})
    return out


def _ctl_index(obj: dict | None) -> dict:
    return {c.get("key"): c for c in (obj or {}).get("controls") or []}


def _has_auto(c: dict | None) -> bool | None:
    if not c or not c.get("supported"):
        return None
    names = [str(x).lower() for x in (c.get("caps_flags_names") or [])]
    if names:
        return any("auto" in n for n in names)
    cf = c.get("caps_flags")
    return bool(cf & 0x1) if isinstance(cf, int) else None


def reanalyze(run_dir: Path) -> dict:
    """Rebuild per_control (from supported / descriptor_to_ks / mf_vs_ds_differences) and the verdicts without the
    G-CTRL cell (B7) from a stored W-CTRL-LIST.json; no camera."""
    import json
    d = json.loads((Path(run_dir) / f"{TEST_ID}.json").read_text(encoding="utf-8"))
    cams = (d.get("measurements") or {}).get("cameras") or []
    per = {}
    for r in cams:
        ix = {a: {k: {"supported": bool(x.get(a))} for k, x in (r.get("supported") or {}).items()} for a in ("mf", "ds")}
        per[r["key"]] = per_control_listing(r.get("descriptor_to_ks") or [], ix, r.get("mf_vs_ds_differences") or [])
    v = {k: x for k, x in (d.get("verdicts") or {}).items() if k != "G-CTRL"}
    return {"test": TEST_ID, "reanalysis_of": str(Path(run_dir) / f"{TEST_ID}.json"), "verdicts": v,
            "per_control": per, "listed_counts": {r.get("name"): r.get("counts") for r in cams},
            "changes": [{"cell": "G-CTRL", "from": "untested", "to": "(removed: listing is not a G-CTRL cell)"}]
            if "G-CTRL" in (d.get("verdicts") or {}) else [],
            "fixes_applied": ["B7 G-CTRL cell dropped (counts in listed_counts)", "per_control for W-CTRL-EFFECT"]}


def run(ctx) -> dict:
    def body(res, m, v, e):
        tdir = ctx.test_dir(TEST_ID)
        desc = U.get_descriptors(ctx)
        cams_out, crit, not_answering = [], [], []
        for c in ctx.cameras:
            rec: dict = {"key": c["key"], "name": c.get("name"), "is_kiyo": c.get("is_kiyo")}
            dc = descriptor_controls(U.descriptor_for(desc, c))
            rec["descriptor"] = dc
            apis = {}
            for api, dev in (("mf", c.get("mf_symlink")), ("ds", c.get("ds_path"))):
                if not dev:
                    rec[f"{api}_error"] = f"no {api} device path"
                    apis[api] = None
                    continue
                argv = [str(ctx.wincam), "controls", "--api", api, "--device", dev, "--read-only",
                        "--timeout-ms", "8000"]
                obj, run_rec = U.run_json(ctx, argv, 60, cam=True)
                rec[f"{api}_run"] = run_rec
                apis[api] = obj
                if obj is not None:
                    results.write_json(tdir / f"{slug(c)}_controls_{api}.json", obj)
                    if obj.get("device_not_answering"):
                        not_answering.append({"camera": c["key"], "name": c.get("name"), "api": api,
                                              "hr": ((obj.get("error") or {}).get("hr")),
                                              "failed_controls": obj.get("get_failed_controls")})
                if obj is None or run_rec["rc"] != 0 or (obj or {}).get("error"):
                    e.append({"camera": c["key"], "api": api, "rc": run_rec["rc"], "timed_out": run_rec["timed_out"],
                              "error": (obj or {}).get("error"),
                              "device_not_answering": (obj or {}).get("device_not_answering")})
            ix = {a: _ctl_index(o) for a, o in apis.items()}
            # ---- descriptor -> KS mapping
            mapping, missing, unmapped = [], {"mf": [], "ds": []}, []
            expected_keys = set()
            for unit, names, table in (("CT", dc["camera_terminal"], CT_MAP), ("PU", dc["processing_unit"], PU_MAP)):
                for n in names:
                    targets = table.get(n)
                    if targets is None or not targets:
                        unmapped.append(f"{unit}.{n}")
                        continue
                    for ks, aspect in targets:
                        if aspect == "value":
                            expected_keys.add(ks)
                        row = {"descriptor": f"{unit}.{n}", "ks": ks, "aspect": aspect}
                        for a in ("mf", "ds"):
                            if apis.get(a) is None:
                                row[a] = None
                                continue
                            ctl = ix[a].get(ks)
                            ok = bool(ctl and ctl.get("supported")) if aspect == "value" else _has_auto(ctl)
                            row[a] = ok
                            if not ok:
                                missing[a].append(f"{unit}.{n} -> {ks}{'' if aspect == 'value' else ' AUTO flag'}")
                        mapping.append(row)
            rec["descriptor_to_ks"] = mapping
            rec["descriptor_controls_without_ks_id"] = unmapped
            rec["missing"] = missing
            extra = {}
            for a in ("mf", "ds"):
                extra[a] = sorted(k for k, ctl in ix[a].items() if ctl.get("supported") and k not in expected_keys)
            rec["extra_supported_not_in_descriptor"] = extra
            # ---- MF vs DS per control
            diffs, sup = [], {}
            for k in sorted(set(ix.get("mf", {})) | set(ix.get("ds", {}))):
                a, b = ix.get("mf", {}).get(k), ix.get("ds", {}).get(k)
                sup[k] = {"mf": bool(a and a.get("supported")), "ds": bool(b and b.get("supported"))}
                if not (a and b):
                    continue
                if a.get("supported") != b.get("supported"):
                    diffs.append({"control": k, "field": "supported", "mf": a.get("supported"), "ds": b.get("supported")})
                    continue
                if not a.get("supported"):
                    continue
                for f in COMPARE_FIELDS:
                    if a.get(f) != b.get(f):
                        diffs.append({"control": k, "field": f, "mf": a.get(f), "ds": b.get(f)})
            rec["mf_vs_ds_differences"] = diffs
            rec["per_control"] = per_control_listing(mapping, ix, diffs)
            rec["supported"] = {k: x for k, x in sup.items() if x["mf"] or x["ds"]}
            rec["ranges"] = {k: {f: (ix.get("mf", {}).get(k) or ix.get("ds", {}).get(k) or {}).get(f)
                                 for f in ("min", "max", "step", "default", "caps_flags_names", "value", "flags_names",
                                           "via", "iam_ks_range_agree", "note")}
                             for k in rec["supported"]}
            rec["degenerate_ranges"] = [k for k, r in rec["ranges"].items()
                                        if r.get("min") is not None and r.get("min") == r.get("max")]
            rec["iam_ks_disagree"] = [k for k, r in rec["ranges"].items() if r.get("iam_ks_range_agree") is False]
            rec["counts"] = {"descriptor_ct": len(dc["camera_terminal"]), "descriptor_pu": len(dc["processing_unit"]),
                             "mf_supported": sum(1 for x in sup.values() if x["mf"]),
                             "ds_supported": sum(1 for x in sup.values() if x["ds"]),
                             "missing_mf": len(missing["mf"]), "missing_ds": len(missing["ds"]),
                             "mf_vs_ds_diffs": len(diffs)}
            dead = [a for a in ("mf", "ds") if (apis.get(a) or {}).get("device_not_answering")]
            ok = (apis.get("mf") is not None and apis.get("ds") is not None and not missing["mf"]
                  and not missing["ds"] and not diffs)
            if dead:
                ok = None   # values/caps of a camera that does not answer GETs cannot be compared
            rec["device_not_answering"] = dead or None
            rec["equivalent"] = ok
            crit.append({"criterion": f"{c.get('name')}: every descriptor control listed via MF and DS, identical "
                                      f"ranges/defaults/flags", "met": ok,
                         "detail": {"counts": rec["counts"], "missing": missing, "diffs": diffs[:10],
                                    "unmapped": unmapped, "device_not_answering": dead or None}})
            cams_out.append(rec)
        m["cameras"] = cams_out
        m["listed_counts"] = {r["name"]: r["counts"] for r in cams_out}
        m["not_answering"] = not_answering
        oks = [r["equivalent"] for r in cams_out if r["equivalent"] is not None]
        v["ctrl_list_equivalence"] = {
            "rating": "untested" if not oks else ("yes" if all(oks) else "partial" if any(oks) else "no"),
            "criteria": crit,
            "evidence": {"note": "answers plan Q 'same controls in DS and MF?'; descriptor bmControls carry no ranges, "
                                 "so ranges are compared MF vs DS; G-CTRL (set/readback/effect) is W-CTRL-EFFECT's"}}
    return U.guarded(ctx, TEST_ID, body)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--reanalyze":
        _out = reanalyze(Path(sys.argv[2]))
        print(results.write_json(Path(sys.argv[2]) / "reanalysis" / f"{TEST_ID}.json", _out), _out["changes"])
        sys.exit(0)
    sys.exit(U.standalone(run, TEST_ID))
