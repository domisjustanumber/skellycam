# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26"]
# ///
"""Cross-run summary of flash_libuvc_scr.py outputs (phase 2, goal 2).

Usage: uv run --script research/usb_cameras/timing/scripts/flash_libuvc_summary.py A.json B.json ... --out summary.json

Reports, per run and across runs:
  * C930e (libuvc) and C922 (MF) per-source error vs the flash GT (std, MAD; median over the fixed ROI rows)
  * cross-camera offset  delta = offset_C930e(src1) - offset_C922(src2)  at the SAME image row (offset = GT exposure
    start of the ROI minus the timestamp); its run-to-run spread is the sync stability of that source pair
  * GT-free pairwise checks (device STC vs back-dated host transfer time), STC rate vs QPC, quantisation grids
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np

PAIRS = [("scr_first_stc", "uvc_pts_mapped_direct"), ("pts_via_stc", "uvc_pts_mapped_direct"),
         ("host_first_payload_backdated", "uvc_pts_mapped_direct"), ("scr_first_stc", "uvc_pts_via_scr_lsq_envelope"),
         ("seq_env", "seq_env"), ("host_arrival", "host_arrival"), ("host_arrival", "os_timestamp"),
         ("host_first_payload", "os_timestamp")]


def main() -> int:
    args = sys.argv[1:]; out = None
    if "--out" in args:
        i = args.index("--out"); out = args[i + 1]; del args[i:i + 2]
    runs = {Path(p).stem: json.loads(Path(p).read_text()) for p in args}
    res = {"test": "flash_libuvc_summary", "inputs": args, "runs": {}, "across_runs": {}}
    cross = {}
    for name, d in runs.items():
        r = {"display": {k: d["display"].get(k) for k in ("refresh_glitches", "bad_refresh_pairs", "unreliable_presents", "presents")}}
        for cam, c in d["cameras"].items():
            srcs = sorted({s for row in c["rows"] for s in row["sources"]})
            tab = {}
            for s in srcs:
                v = [row["sources"][s] for row in c["rows"] if row["sources"][s].get("n", 0) >= 20]
                if v:
                    tab[s] = {"std_us_median_over_rows": float(np.median([x["err_std_us"] for x in v])),
                              "mad_us_median_over_rows": float(np.median([x["err_mad_sigma_us"] for x in v])),
                              "std_us_by_row": {str(row["row_frac"]): round(row["sources"][s]["err_std_us"], 1)
                                                for row in c["rows"] if row["sources"][s].get("n", 0) >= 20},
                              "n_by_row": [row["sources"][s].get("n") for row in c["rows"]]}
            r[cam] = {"vs_gt": tab, "gt_corr_by_row": [round(row["gt_corr"], 4) for row in c["rows"]],
                      "quantization": {s: {k: q[k] for k in ("residual_std_us", "best_grid_ms", "grid_phase_concentration", "conc_at_1ms", "conc_at_4ms", "conc_at_16ms")}
                                       for s, q in c["quantization"].items()},
                      "pairwise_gt_free": c.get("pairwise_gt_free")}
            if cam == "c930e_libuvc":
                k = c["clock"]
                r[cam]["clock"] = {"stc_ppm_vs_qpc": k["stc_ppm_vs_nominal_30MHz_qpc_timebase"],
                                   "stc_line_residual_range_us": k["stc_line_residual_range_us"],
                                   "stc_chunks_5s_ppm": [round(x["ppm"], 1) for x in k["stc_chunks_5s"]],
                                   "stc_first_step_ms": k["stc_first_step_ms"], "pts_steps_not_1x": k["pts_steps_not_1x"],
                                   "stc_first_minus_pts_ms": k["stc_first_minus_pts_ms"],
                                   "callback_minus_sof_frame_ms": k["callback_minus_sof_frame_ms"]}
                r["usb_frame_vs_qpc_ppm"] = d["usb_frame_clock"]["usb_frame_vs_qpc_ppm"]
        if "c930e_libuvc" in d["cameras"] and "c922_mf" in d["cameras"]:
            a, b = d["cameras"]["c930e_libuvc"], d["cameras"]["c922_mf"]
            for ra, rb in zip(a["rows"], b["rows"]):
                assert ra["row_frac"] == rb["row_frac"]
                for s1, s2 in PAIRS:
                    x, y = ra["sources"].get(s1, {}), rb["sources"].get(s2, {})
                    if x.get("n", 0) >= 20 and y.get("n", 0) >= 20:
                        delta = x["offset_ms"] - y["offset_ms"]
                        se = np.hypot(x["err_std_us"] / np.sqrt(x["n"]), y["err_std_us"] / np.sqrt(y["n"])) / 1e3
                        cross.setdefault(f"{s1} | {s2}", {}).setdefault(str(ra["row_frac"]), {})[name] = {"delta_ms": delta, "se_ms": float(se)}
        res["runs"][name] = r
    acr = {}
    for pair, byrow in cross.items():
        acr[pair] = {}
        for row, byrun in byrow.items():
            v = np.array([x["delta_ms"] for x in byrun.values()])
            acr[pair][row] = {"runs": {k: round(x["delta_ms"], 3) for k, x in byrun.items()},
                              "mean_ms": float(v.mean()), "std_ms": float(v.std(ddof=1)) if len(v) > 1 else None,
                              "range_ms": float(v.max() - v.min()), "typical_se_ms": float(np.median([x["se_ms"] for x in byrun.values()]))}
    res["across_runs"]["cross_camera_offset_delta"] = acr
    for pair, byrow in acr.items():
        print(pair)
        for row, e in byrow.items():
            print(f"   row {row}: runs={e['runs']} std={e['std_ms'] if e['std_ms'] is None else round(e['std_ms'], 3)} ms range={e['range_ms']:.3f} se~{e['typical_se_ms']:.3f}")
    if out:
        Path(out).write_text(json.dumps(res, indent=2, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
