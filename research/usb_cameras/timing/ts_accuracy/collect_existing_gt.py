# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26"]
# ///
"""Collect the per-source flash ground-truth (GT) scores that already exist for the 2026-10-27/28 re-run (their raw
MJPEG is gone, so per-frame GT cannot be rebuilt; only the stored aggregates remain) and derive inter-camera offset
differences within each two-camera run. Reads only; writes one JSON.

Inputs per run dir (results/windows/Gerald/timing/rerun_20261027/flash/<run>/):
  flash_verify_extra.json   auto ROI (most-flickering block per camera); GT frame selection by the best-scoring
                            source (circular for that source); gamma tuned on it. Fields vs_ground_truth.
  mf_fixed_gt_<cam>.json    fixed ROI (row 0.5 etc.), fixed gamma 2.2, GT selected by seq_env (no device timestamp).
Sign: the stored offset_ms is median(GT - stamp); here it is flipped to stamp - GT (positive = stamp later than the
exposure start of the ROI rows).
Tier-0-relevant sources: host_arrival (MF arrival), os_timestamp (MF sample time), seq_envelope / seq_env (frame
index + lower envelope of arrival = the robust whole-run lattice on arrival). uvc_* are tier 1 (reference only).

Usage:
  uv run --script research/usb_cameras/timing/ts_accuracy/collect_existing_gt.py \
     --flash-root research/usb_cameras/results/windows/Gerald/timing/rerun_20261027/flash \
     --out research/usb_cameras/results/windows/Gerald/ts_accuracy_20261109/existing_reanalysis/existing_gt_aggregates.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

CAM = {"085c": "C922", "0843": "C930e", "4a55": "generic"}
READOUT_MS = {"C922": 31.0, "C930e": 30.0}          # REPORT finding 12 / flash_rows; generic not measured
SOURCES = ("host_arrival", "os_timestamp", "seq_envelope", "seq_env", "uvc_pts_mapped_direct", "uvc_pts_via_scr_lsq_envelope")
INVALID = {"20261028T033232Z_flash_c922_c930e_exp-7_d": "display glitches (50 refresh glitches); GT invalid"}


def cam_of(key: str) -> str:
    return next((v for k, v in CAM.items() if f"pid_{k}" in key), key)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--flash-root", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = {"test": "ts_accuracy.collect_existing_gt", "command": " ".join(sys.argv),
           "sign": "stamp - GT (ms); std/MAD in us after removing the median", "runs": {}, "inter_camera": []}
    for rd in sorted(Path(a.flash_root).iterdir()):
        if not rd.is_dir():
            continue
        run = {"invalid": INVALID.get(rd.name), "auto_roi": {}, "fixed_roi": {}}
        fe = rd / "flash_verify_extra.json"
        if fe.exists():
            o = json.loads(fe.read_text())
            for c in o.get("cameras", []):
                cam = cam_of(c["camera_key"])
                srcs = {}
                for s in SOURCES:
                    v = (c.get("sources", {}).get(s) or {}).get("vs_ground_truth")
                    if v and v.get("n", 0) >= 5:
                        srcs[s] = {"n": v["n"], "stamp_minus_gt_ms": -v["offset_ms"], "std_us": v["err_std_us"],
                                   "mad_us": v["err_mad_sigma_us"]}
                run["auto_roi"][cam] = {"roi_row": c["roi"]["roi_row_center_frac"], "roi_col": c["roi"]["roi_col_center_frac"],
                                        "gt_reference": c.get("gt_reference"), "E_ms": c.get("E_ms"), "sources": srcs}
        for fj in sorted(rd.glob("mf_fixed_gt_*.json")):
            o = json.loads(fj.read_text())
            cam = cam_of(o["capture"])
            rows = {}
            for r, e in o["rows"].items():
                rows[r] = {"gt_n": e["gt_n"], "gt_corr": e["gt_corr"],
                           "sources": {s: {"n": v["n"], "stamp_minus_gt_ms": -v["offset_ms"], "std_us": v["err_std_us"],
                                           "mad_us": v["err_mad_sigma_us"]}
                                       for s, v in e["sources"].items() if s in SOURCES and v.get("n", 0) >= 5}}
            run["fixed_roi"][cam] = {"col": o["col"], "fps_lsq": o["fps_lsq"], "rows": rows}
        out["runs"][rd.name] = run
        # inter-camera differences within this run (same source)
        for kind in ("auto_roi", "fixed_roi"):
            cams = sorted(run[kind])
            for i in range(len(cams)):
                for j in range(i + 1, len(cams)):
                    A, B = cams[i], cams[j]
                    if kind == "auto_roi":
                        sa, sb = run[kind][A]["sources"], run[kind][B]["sources"]
                        ra, rb = run[kind][A]["roi_row"], run[kind][B]["roi_row"]
                        ca, cb = run[kind][A]["roi_col"], run[kind][B]["roi_col"]
                    else:
                        ka = "0.5" if "0.5" in run[kind][A]["rows"] else sorted(run[kind][A]["rows"])[len(run[kind][A]["rows"]) // 2]
                        kb = "0.5" if "0.5" in run[kind][B]["rows"] else sorted(run[kind][B]["rows"])[len(run[kind][B]["rows"]) // 2]
                        sa, sb = run[kind][A]["rows"][ka]["sources"], run[kind][B]["rows"][kb]["sources"]
                        ra, rb = float(ka), float(kb)
                        ca, cb = run[kind][A]["col"], run[kind][B]["col"]
                    for s in SOURCES:
                        if s in sa and s in sb:
                            d = sb[s]["stamp_minus_gt_ms"] - sa[s]["stamp_minus_gt_ms"]
                            rec = {"run": rd.name, "roi_kind": kind, "cam_a": A, "cam_b": B, "source": s,
                                   "b_minus_a_ms": d, "rows": [ra, rb], "cols": [ca, cb],
                                   "se_ms": float(np.hypot(sa[s]["std_us"] / np.sqrt(sa[s]["n"]), sb[s]["std_us"] / np.sqrt(sb[s]["n"])) / 1e3),
                                   "invalid": run["invalid"]}
                            if A in READOUT_MS and B in READOUT_MS:
                                rec["mid_row_corrected_ms"] = d - (0.5 - rb) * READOUT_MS[B] + (0.5 - ra) * READOUT_MS[A]
                            out["inter_camera"].append(rec)
    # summary across valid runs: per (cams, source, roi_kind) mean/std of the difference
    summ = {}
    for r in out["inter_camera"]:
        if r["invalid"]:
            continue
        k = f"{r['cam_b']}-{r['cam_a']}|{r['source']}|{r['roi_kind']}"
        summ.setdefault(k, []).append(r)
    out["inter_camera_summary"] = {
        k: {"runs": len(v), "b_minus_a_ms": [round(x["b_minus_a_ms"], 2) for x in v],
            "mean_ms": float(np.mean([x["b_minus_a_ms"] for x in v])),
            "sd_across_runs_ms": float(np.std([x["b_minus_a_ms"] for x in v], ddof=1)) if len(v) > 1 else None,
            "mid_row_corrected_ms": [round(x["mid_row_corrected_ms"], 2) for x in v if "mid_row_corrected_ms" in x]}
        for k, v in sorted(summ.items())}
    # per camera, per source, across valid runs (auto ROI): std and stamp-GT offset spread
    per = {}
    for name, run in out["runs"].items():
        if run["invalid"]:
            continue
        for cam, c in run["auto_roi"].items():
            for s, v in c["sources"].items():
                per.setdefault(f"{cam}|{s}", []).append((name, v["std_us"], v["stamp_minus_gt_ms"], v["n"], c["gt_reference"]))
    out["per_camera_source_auto_roi"] = {
        k: {"runs": len(v), "std_us": [round(x[1]) for x in v], "stamp_minus_gt_ms": [round(x[2], 2) for x in v],
            "n": [x[3] for x in v], "gt_reference": [x[4] for x in v]} for k, v in sorted(per.items())}
    Path(a.out).write_text(json.dumps(out, indent=1, default=float))
    for k, v in out["per_camera_source_auto_roi"].items():
        print(f"{k:40s} std_us {v['std_us']}  stamp-GT ms {v['stamp_minus_gt_ms']}")
    print()
    for k, v in out["inter_camera_summary"].items():
        print(f"{k:55s} runs {v['runs']} diffs {v['b_minus_a_ms']} mid-row {v['mid_row_corrected_ms']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
