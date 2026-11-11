# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26"]
# ///
"""Print the README tables from the three result JSONs (flash_gt_perframe.json, camera_clock_scores.json,
existing_gt_aggregates.json) and write summary.json next to them. Reads only.

Usage:
  uv run --script research/usb_cameras/timing/ts_accuracy/summarize.py \
     --dir research/usb_cameras/results/windows/Gerald/ts_accuracy_20261109/existing_reanalysis
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def f0(x):
    return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.0f}"


def f2(x):
    return "-" if x is None else f"{x:.2f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    a = ap.parse_args()
    D = Path(a.dir)
    gt = json.loads((D / "flash_gt_perframe.json").read_text())
    cc = json.loads((D / "camera_clock_scores.json").read_text())
    summ: dict = {}

    # ---- T1: per-frame flash GT ----------------------------------------------------------------------------------
    rows = [("MF sample time, raw", "raw:mf_sample_time"), ("MF arrival, raw", "raw:mf_arrival"),
            ("lattice LSQ (sample time)", "t0:mf_sample_time:lsq_whole"), ("lattice LSQ (arrival)", "t0:mf_arrival:lsq_whole"),
            ("lattice robust whole-run (sample time)", "t0:mf_sample_time:rob_envq0.02_whole"),
            ("lattice robust whole-run (arrival)", "t0:mf_arrival:rob_envq0.02_whole"),
            ("lattice fixed-P, 10 s centred (sample time)", "t0:mf_sample_time:fixP_envq0.02_win10s_centred"),
            ("lattice fixed-P, 10 s centred (arrival)", "t0:mf_arrival:fixP_envq0.02_win10s_centred"),
            ("lattice fixed-P, 10 s causal (sample time)", "t0:mf_sample_time:fixP_envq0.02_win10s_causal"),
            ("lattice fixed-P, 10 s causal (arrival)", "t0:mf_arrival:fixP_envq0.02_win10s_causal"),
            ("tier 1 ref: PTS mapped to arrival envelope", "t1ref:uvc_pts_mapped_direct"),
            ("tier 1 ref: PTS via SCR (lsq)", "t1ref:uvc_pts_via_scr_lsq_envelope")]
    print("T1 flash GT per frame (flash_run1_repositioned), GT ref = seq_env; std / p95 / max in us, offset in ms")
    print("| Method | C922 offset | C922 std | p95 | max | C930e offset | C930e std | p95 | max | C930e std, t>=3 s |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    t1 = {}
    for lab, key in rows:
        c2 = gt["cameras"]["C922"]["gt"]["seq_env"]["sources"][key]
        c3 = gt["cameras"]["C930e"]["gt"]["seq_env"]["sources"][key]
        c3l = gt["cameras"]["C930e"]["gt"]["seq_env"]["sources_t_ge_3s"][key]
        t1[key] = {"C922": c2, "C930e": c3, "C930e_t_ge_3s": c3l}
        print(f"| {lab} | {f2(c2['mean_offset_ms'])} | {f0(c2['std_us'])} | {f0(c2['p95_abs_us'])} | {f0(c2['max_abs_us'])} | "
              f"{f2(c3['mean_offset_ms'])} | {f0(c3['std_us'])} | {f0(c3['p95_abs_us'])} | {f0(c3['max_abs_us'])} | {f0(c3l.get('std_us'))} |")
    for cam in ("C922", "C930e"):
        g = gt["cameras"][cam]["gt"]
        print(f"  {cam}: n={g['seq_env']['n']} (before 3 s: {g['seq_env']['n_before_3s']}), GT span {g['seq_env']['gt_time_span_s']}, "
              f"ref=pts gives raw arrival std {g['pts']['sources']['raw:mf_arrival']['std_us']:.0f}, robust arrival {g['pts']['sources']['t0:mf_arrival:rob_envq0.02_whole']['std_us']:.0f}")
    summ["flash_gt_T1"] = t1

    # ---- T2: window length sensitivity (flash GT) ------------------------------------------------------------------
    print("\nT2 window sensitivity vs flash GT (std us; GT ref seq_env)")
    print("| Fit | series | 2 s | 5 s | 10 s | 20 s | whole run |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    t2 = {}
    for cam in ("C922", "C930e"):
        S = gt["cameras"][cam]["gt"]["seq_env"]["sources"]
        for fam, whole in (("fixP_envq0.02", "rob_envq0.02_whole"), ("rob_envq0.02", "rob_envq0.02_whole")):
            for tag in ("centred", "causal"):
                for ser in ("mf_sample_time", "mf_arrival"):
                    vals = [S[f"t0:{ser}:{fam}_win{W}s_{tag}"]["std_us"] for W in (2, 5, 10, 20)]
                    w = S[f"t0:{ser}:{whole}"]["std_us"]
                    t2[f"{cam}|{fam}|{tag}|{ser}"] = vals + [w]
                    print(f"| {cam} {fam} {tag} | {ser} | " + " | ".join(f0(v) for v in vals) + f" | {f0(w)} |")
    summ["flash_gt_T2_window"] = t2

    # ---- T3: lower-envelope quantile sensitivity (flash GT) --------------------------------------------------------
    print("\nT3 quantile of the lower envelope, whole run (std us | mean offset ms), flash GT")
    print("| Fit | series | C922 q=0 | 0.02 | 0.05 | 0.10 | C930e q=0 | 0.02 | 0.05 | 0.10 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for fam in ("rob", "lsqP"):
        for ser in ("mf_sample_time", "mf_arrival"):
            cells = []
            for cam in ("C922", "C930e"):
                S = gt["cameras"][cam]["gt"]["seq_env"]["sources"]
                for q in ("0", "0.02", "0.05", "0.1"):
                    v = S[f"t0:{ser}:{fam}_envq{q}_whole"]
                    cells.append(f"{f0(v['std_us'])} / {v['mean_offset_ms']:.1f}")
            print(f"| {fam} | {ser} | " + " | ".join(cells) + " |")

    # ---- T4: camera clock (random error), fixed-slope reference, frames >= 3 s ------------------------------------
    keys = [("raw", None), ("LSQ lattice", "lsq_whole"), ("robust whole", "rob_envq0.02_whole"),
            ("fixP 2 s centred", "fixP_envq0.02_win2s_centred"), ("fixP 10 s centred", "fixP_envq0.02_win10s_centred"),
            ("fixP 20 s centred", "fixP_envq0.02_win20s_centred"), ("fixP 10 s causal", "fixP_envq0.02_win10s_causal"),
            ("rob 10 s causal", "rob_envq0.02_win10s_causal")]
    print("\nT4 vs camera clock (fixed per-camera slope), frames >= 3 s: median [min-max] over runs of std (us)")
    groups: dict = {}
    for e in cc["entries"]:
        if e.get("ref") not in ("pts", "stc") or "sources" not in e:
            continue
        groups.setdefault((e["camera"], e["ref"]), []).append(e)
    t4 = {}
    print("| Camera / ref | runs | series | " + " | ".join(k for k, _ in keys) + " |")
    print("| --- | --- | --- | " + " | ".join("---" for _ in keys) + " |")
    for (cam, ref), es in groups.items():
        for ser in ("mf_sample_time", "arrival"):
            cells = []
            for lab, vk in keys:
                vals = []
                for e in es:
                    so = e["sources"].get(ser)
                    if not so:
                        continue
                    st = so["raw_late_fixedslope"] if vk is None else so["fits_late_fixedslope"][vk]
                    if "std_us" in st:
                        vals.append(st["std_us"])
                if vals:
                    t4[f"{cam}|{ref}|{ser}|{lab}"] = vals
                    cells.append(f"{np.median(vals):.0f} [{min(vals):.0f}-{max(vals):.0f}]")
                else:
                    cells.append("-")
            print(f"| {cam} / {ref} | {len(es)} | {ser} | " + " | ".join(cells) + " |")
    summ["camera_clock_T4_std_us_per_run"] = t4

    # ppm and slope spread
    print("\nT4b camera clock rate vs QPC (ppm vs nominal): fixed slope used, per-run envelope values, slope-estimator spread")
    for k, v in cc["fixed_slope_ppm_per_camera"].items():
        cam, ref = k.split("|")
        spreads = [e["camera_clock"]["ppm_spread"] for e in groups.get((cam, ref), []) if "camera_clock" in e]
        print(f"  {k}: median {v['median_ppm']:.1f} ppm; runs {[round(x, 1) for x in v['runs']]}; estimator spread per run {[round(x) for x in spreads]}")
    # cadence
    print("\nT4c camera-clock cadence residual (std us, the camera's own frame timing vs a perfect lattice)")
    for (cam, ref), es in groups.items():
        print(f"  {cam}/{ref}: {[round(e['camera_clock']['cadence_residual_us']['std_us']) for e in es]}")

    # ---- T5: slots / drops -------------------------------------------------------------------------------------------
    print("\nT5 slot assignment: tier-0 drops detected, disagreements with camera-clock slots, camera-clock steps corrected")
    t5 = []
    for e in cc["entries"]:
        if "sources" not in e:
            continue
        if e.get("ref") == "stc":
            continue
        rec = {"label": e["label"], "camera": e["camera"], "ref": e["ref"]}
        for ser, so in e["sources"].items():
            rec[ser] = {"drops": so["slots"]["drops_detected"], "disagree": so["slots"].get("slot_step_disagreements_vs_camera_clock")}
        if "camera_clock" in e:
            rec["camera_clock_missing_slots"] = e["camera_clock"]["slots_missing_camera_clock"]
            rec["camera_clock_steps_corrected"] = len(e["camera_clock"]["steps_corrected_by_host_slots"])
        t5.append(rec)
        print("  ", json.dumps(rec))
    summ["slots_T5"] = t5

    # ---- T6: arrival - sample time (GT-free) ------------------------------------------------------------------------
    print("\nT6 MF arrival minus MF sample time (median ms), GT-free")
    t6 = {}
    for e in cc["entries"]:
        if "arrival_minus_sample_time_ms" in e and e.get("ref") != "stc":
            t6.setdefault(e["camera"], []).append(round(e["arrival_minus_sample_time_ms"]["median"], 2))
    for cam, v in t6.items():
        print(f"  {cam}: {v}")
    summ["arrival_minus_sample_time_T6"] = t6

    # ---- T7: regularity only (no reference) ---------------------------------------------------------------------
    print("\nT7 regularity only (no camera clock): residual std of the LSQ lattice to its own stamps (us), drops")
    for e in cc["entries"]:
        if e.get("ref") == "none" and "sources" in e:
            print("  ", e["label"], e["camera"], {s: (round(v["regularity_fit_minus_stamp"]["lsq_whole"]["std_us"]), v["slots"]["drops_detected"])
                                                 for s, v in e["sources"].items()})
    (D / "summary.json").write_text(json.dumps(summ, indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
