# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Fixed-ROI, fixed-gamma, device-timestamp-free flash ground truth for ANY MF capture (incl. cameras without UVC
metadata, e.g. the generic 4C4A:4A55). Re-uses timing/scripts/flash_libuvc_scr.py (gt_fixed, score, roi_series,
c922_sources -> analyze_frames sources + seq_env) unchanged.

GT reference = seq_env (host-arrival lower envelope vs MF frame index; no device timestamp), gamma fixed (2.2), E nominal.
Every available source (host_arrival, os_timestamp, mf_undoc_d06f8a46, seq_env, uvc_* if present) is scored vs that GT.
Usage: mf_fixed_gt.py RUN_DIR --glob '*4a55*' --col 0.456 --rows 0.4,0.57,0.7 [--e-ms 7.8125] [--gamma 2.2] [--out json]"""
import argparse, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\timing\scripts")
import flash_libuvc_scr as m  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("--glob", required=True); ap.add_argument("--col", type=float, required=True)
ap.add_argument("--rows", default="0.5"); ap.add_argument("--e-ms", type=float, default=7.8125); ap.add_argument("--gamma", type=float, default=2.2)
ap.add_argument("--skip-first", type=int, default=15); ap.add_argument("--out")
a = ap.parse_args()
run = Path(a.run); disp = m.load_display_robust(run / "display_m0")
cj = sorted((run / "capture").glob(a.glob + ".frames.jsonl"))[0]
rows = m.af.load(cj)[a.skip_first:]
stack = m.decode_mjpeg(rows, cj.with_name(cj.name.replace(".frames.jsonl", ".mjpeg")))
srcs, clk = m.c922_sources(rows)
seq = np.array([r["seq"] for r in rows], float); host = np.array([r["host_arrival_ns"] for r in rows], float)
per = np.polyfit(seq, host, 1)[0]
res = {"test": "mf_fixed_gt", "run": str(run), "capture": cj.name, "E_ms": a.e_ms, "gamma": a.gamma, "col": a.col,
       "frames": len(rows), "frame_period_ms_lsq": per / 1e6, "fps_lsq": 1e9 / per,
       "seq_gaps": int(np.sum(np.diff(seq) != 1)), "display_unreliable_presents": disp.get("unreliable_presents"), "rows": {}}
for rf in [float(v) for v in a.rows.split(",")]:
    y, box = m.roi_series(stack, rf, a.col)
    gt = m.gt_fixed(srcs["seq_env"], y, disp, a.e_ms * 1e6, a.gamma)
    e = {"roi_box": box, "gt_corr": gt["corr"], "gt_n": int(len(gt["k"])), "sources": {}}
    for k, X in srcs.items():
        e["sources"][k] = m.score(X, gt)
    res["rows"][str(rf)] = e
    print(cj.name[:17], f"row {rf}", "corr", round(gt["corr"], 4), "n", e["gt_n"],
          " ".join(f"{k}={v.get('err_std_us', float('nan')):.0f}/{v.get('err_mad_sigma_us', float('nan')):.0f}@{v.get('offset_ms', float('nan')):.2f}"
                   for k, v in e["sources"].items()))
print("fps_lsq", res["fps_lsq"], "seq_gaps", res["seq_gaps"])
if a.out:
    Path(a.out).write_text(json.dumps(res, indent=1, default=float))
