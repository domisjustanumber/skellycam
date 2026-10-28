# /// script
# requires-python = ">=3.10"
# ///
"""Compact table over run dirs: summarize_runs output + fixed-ROI (roi_rows_*) + step/impulse 10-90 from the profile.
Usage: compact_table.py RUN_DIR [...] [--out json]"""
import json, subprocess, sys
from pathlib import Path
args = sys.argv[1:]; out = None
if "--out" in args:
    i = args.index("--out"); out = args[i + 1]; del args[i:i + 2]
here = Path(__file__).resolve().parent
summ = json.loads(subprocess.run(["uv", "run", "--script", str(here / "summarize_runs.py"), *args], capture_output=True, text=True).stdout)
def lj(p):
    try: return json.loads(Path(p).read_text())
    except Exception: return None
def rise(prof):
    ks = sorted(prof, key=int); v = [prof[k][0] for k in ks]
    lo = next((int(k) for k, x in zip(ks, v) if int(k) > -20 and x > 0.1), None); hi = next((int(k) for k, x in zip(ks, v) if int(k) > -20 and x > 0.9), None)
    return [lo, hi]
table = {}
for r in args:
    s = summ[str(Path(r))] if str(Path(r)) in summ else summ[r]
    name = Path(r).name; t = {"cover": s.get("cover"), "cpu": s.get("cpu"), "display": {k: (s.get("display") or {}).get(k) for k in ("presents", "refresh_glitches", "unreliable_presents", "global_line_resid_us_std")}}
    for cam in ("C922", "C930e", "generic"):
        e = s.get(cam)
        if not e: continue
        row = {"roi": [round(x, 2) for x in e["roi_row_col"]], "gt_ref": e["gt_ref"]}
        for k in ("host_arrival", "os_timestamp", "uvc_pts_mapped_direct", "uvc_pts_via_scr_lsq_envelope", "seq_envelope"):
            if k in e: row[k] = [e[k]["gt_std_us"], e[k]["gt_n"], e[k].get("gt_offset_ms")]
        row["pts_steps"] = e.get("pts_steps"); row["stc_minus_pts_ms"] = e.get("stc_minus_pts_ms")
        row["escan_scr_lsq"] = e.get("exposure_scan_scr_lsq"); row["flash_rows"] = {k: v for k, v in (e.get("flash_rows") or {}).items() if k in ("readout_ms_full_height", "d0_ms_row0", "fit_resid_ms_std")}
        row["cond"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in (e.get("conditions") or {}).items() if k != "exposure"}
        row["exposure_readback"] = ((e.get("conditions") or {}).get("exposure") or {}).get("value")
        tag = {"C922": "c922", "C930e": "c930e", "generic": "generic"}[cam]
        for f in Path(r).glob(f"roi_rows_{tag}_*.json"):
            d = lj(f); row["fixed_roi_" + f.stem] = {"slope_ms": d.get("offset_vs_row_slope_ms_per_frame_height"), "off_at_0p5_ms": d.get("offset_at_row_0p5_ms")}
        st = lj(Path(r) / "step_response.json") or {}
        for k, v in st.items():
            if k.startswith(tag): row["step_10_90_bins"] = rise(v["profile_rel_ms_mean_n"])
        im = lj(Path(r) / "impulse_response.json") or {}
        for k, v in im.items():
            if k.startswith(tag) and "gamma2.2" in k: row["impulse_g22"] = {"r2": round(v["r2"], 3), "lag_10_50_90_ms": v["lag_10_50_90_ms"], "width_10_90_ms": v["width_10_90_ms"]}
        t[cam] = row
    table[name] = t
    print("==", name, "cover non-flash t:", (t["cover"] or {}).get("non_flash_sample_t"), "display:", t["display"], "cpu:", {k: (v or {}).get("counter_total_pct_2s") for k, v in (t["cpu"] or {}).items()})
    for cam in ("C922", "C930e", "generic"):
        if cam in t: print("  ", cam, json.dumps(t[cam]))
if out:
    Path(out).write_text(json.dumps(table, indent=1))
