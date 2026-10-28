# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Self-check: load_display_robust vs flash_analyze.load_display (global vblank line) on a run dir's display_m0.
On a glitch-free run they must agree to ~10 us. Usage: display_model_check.py RUN_DIR [...] [--out json]"""
import sys, json
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flash_libuvc_scr as m  # noqa: E402
args = sys.argv[1:]; out = None
if "--out" in args:
    i = args.index("--out"); out = args[i + 1]; del args[i:i + 2]
res = {}
for r in args:
    d0 = m.fa.load_display(Path(r) / "display_m0"); d1 = m.load_display_robust(Path(r) / "display_m0")
    n = min(len(d0["t_on"]), len(d1["t_on"]))
    diff = (d1["t_on"][:n] - d0["t_on"][:n]) / 1e3
    e = {"presents": d1["presents"], "stats_samples": d1["stats_samples"], "refresh_glitches": d1["refresh_glitches"],
         "bad_refresh_pairs": d1["bad_refresh_pairs"], "unreliable_presents": d1["unreliable_presents"],
         "global_line_resid_us_std": d0["vblank_fit_resid_us"]["std"],
         "robust_minus_global_us": {"median": float(np.median(diff)), "max_abs": float(np.max(np.abs(diff)))},
         "levels_equal": bool(np.array_equal(d0["level"][:n], d1["level"][:n]))}
    res[r] = e; print(Path(r).name, json.dumps(e))
if out:
    Path(out).write_text(json.dumps(res, indent=1))
