# /// script
# requires-python = ">=3.10"
# ///
"""Compact per-camera summary of flash runs (earlier results dirs and the 20261027 re-run dirs) for side-by-side comparison.
Reads, when present: flash_analysis.json, flash_verify_extra.json, exposure_scan_*.json, flash_rows.json, frames_analysis.json,
conditions_capture.json, conditions.json, cover.json, display_model_check.json, roi_rows_*.json.
Usage: summarize_runs.py RUN_DIR [RUN_DIR ...] [--out summary.json]"""
import json, sys
from pathlib import Path

args = sys.argv[1:]; out = None
if "--out" in args:
    i = args.index("--out"); out = args[i + 1]; del args[i:i + 2]


def lj(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


CAM = {"085c": "C922", "0843": "C930e", "4a55": "generic", "0e05": "kiyo"}
res = {}
for r in args:
    r = Path(r); runres = {}
    fa = lj(r / "flash_analysis.json") or {}
    fx = lj(r / "flash_verify_extra.json") or {}
    cc = (lj(r / "conditions_capture.json") or {}).get("cameras", {})
    cond = lj(r / "conditions.json") or {}
    cov = lj(r / "cover.json")
    dm = lj(r / "display_model_check.json")
    fr = lj(r / "flash_rows.json") or {}
    fan = lj(r / "frames_analysis.json") or {}
    runres["cpu"] = {k: cond.get(k) for k in ("cpu_start", "cpu_end")} if cond else None
    if cov:
        bad = [s["t"] for s in cov["samples"] if not all(o and o.startswith("flash_timecode.exe|") for o in s["owners"])]
        runres["cover"] = {"n_samples": cov["n_samples"], "non_flash_sample_t": bad}
    if dm:
        runres["display"] = list(dm.values())[0] if isinstance(dm, dict) else dm
    for cam in fa.get("cameras", []):
        key = cam["camera_key"]; name = next((v for k, v in CAM.items() if k in key), key)
        e = {"key": key, "roi_row_col": [cam.get("roi", {}).get("roi_row_center_frac"), cam.get("roi", {}).get("roi_col_center_frac")],
             "gt_ref": cam.get("ground_truth_reference_source"), "exposure_readback": (cam.get("exposure_control") or {}).get("value")}
        for s, v in cam.get("sources", {}).items():
            g = v.get("vs_ground_truth") or {}
            e[s] = {"corr": round(v.get("corr", 0), 4), "gt_std_us": round(g["err_std_us"]) if g.get("err_std_us") is not None else None,
                    "gt_mad_us": round(g["err_mad_sigma_us"]) if g.get("err_mad_sigma_us") is not None else None,
                    "gt_n": g.get("n"), "gt_offset_ms": round(g["offset_ms"], 2) if g.get("offset_ms") is not None else None}
        for c in fx.get("cameras", []):
            if c["camera_key"] == key:
                e["pts_steps"] = [(s.get("index"), s.get("ratio")) if isinstance(s, dict) else s for s in c.get("pts_steps", [])]
                e["stc_minus_pts_ms"] = c.get("stc_minus_pts_ms")
                for s in ("seq_envelope", "uvc_stc_mapped_direct", "uvc_pts_via_stc_line", "uvc_pts_destepped_direct"):
                    v = c.get("sources", {}).get(s)
                    if v:
                        g = v.get("vs_ground_truth") or {}
                        e[s] = {"corr": round(v.get("corr", 0), 4), "gt_std_us": round(g["err_std_us"]) if g.get("err_std_us") is not None else None,
                                "gt_n": g.get("n")}
        for fn in ("exposure_scan_mapped_direct.json", "exposure_scan_scr_lsq.json"):
            d = lj(r / fn)
            if d:
                for c in d["cameras"]:
                    if c["camera_key"] == key and c["scan"]:
                        b = max(c["scan"], key=lambda q: q["corr"])
                        e[fn.replace(".json", "")] = {"peak_E_ms": b["E_ms"], "peak_corr": round(b["corr"], 4),
                                                      "corr_at_nominal": [round(q["corr"], 4) for q in c["scan"] if abs(q["E_ms"] - c.get("E_nominal_ms", 7.8125)) < 1e-6]}
        for c in fr.get("cameras", []):
            if c["camera_key"] == key:
                e["flash_rows"] = {k: c.get(k) for k in c if k not in ("blocks", "camera_key")}
        for c in (fan.get("cameras") or fan.get("files") or []):
            pass
        if key in cc:
            q = cc[key]
            e["conditions"] = {k: q.get(k) for k in ("frames", "errors", "fps_host_arrival", "luma_mean", "luma_min", "luma_max", "frames_with_uvc_pts")}
            ctl = q.get("controls") or {}
            e["conditions"]["exposure"] = ctl.get("exposure_log2"); e["conditions"]["gain"] = (ctl.get("gain") or {}).get("value")
        runres[name] = e
    res[str(r)] = runres
txt = json.dumps(res, indent=1, default=str)
if out:
    Path(out).write_text(txt)
print(txt)
