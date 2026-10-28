# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Synthetic self-test of flash_analyze.fit_source: simulate a 59.95 Hz display with the flash_timecode hold pattern,
a camera at 30 fps with exposure E and a known start offset, add per-frame timestamp noise of known sigma, tone curve
y = f**(1/2.2) and pixel noise, and check that the recovered per-frame error std matches the injected sigma.
Run: uv run --script research/usb_cameras/timing/tests/selftest_flash_analyze.py [--out result.json]"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import flash_analyze as fa

rng = np.random.default_rng(0)
P = 1e9 / 59.951
n_ref = int(60 * 59.951)
lev, cur, rem = [], 0, 0
for i in range(n_ref):
    if rem <= 0:
        cur, rem = 1 - cur, rng.integers(2, 7)
    rem -= 1; lev.append(cur)
disp = {"t_on": np.arange(n_ref) * P + 1e9, "level": np.array(lev, float)}
results = []
for E_ms, sigma_us, true_off_ms in [(7.8125, 0, -20.0), (7.8125, 100, -20.0), (7.8125, 1000, -35.0), (15.625, 500, -10.0), (7.8125, 4600, -20.0)]:
    E = E_ms * 1e6
    nfr = 1700
    t_true = 1.5e9 + np.arange(nfr) * (1e9 / 30.0003)  # exposure start of ROI rows
    X = t_true - true_off_ms * 1e6 + rng.normal(0, sigma_us * 1e3, nfr)  # timestamp under test
    p = fa.window_mean(fa.cumulative(disp), t_true, E)
    y = 20 + 200 * p ** (1 / 2.2) + rng.normal(0, 1.0, nfr)
    r = fa.fit_source(X, y, disp, E)
    pf = r["per_frame"]
    ref = fa.fit_source(t_true - true_off_ms * 1e6 + rng.normal(0, 50e3, nfr), y, disp, E)  # precise reference source
    gt = fa.vs_ground_truth(X, ref["_gt"])
    results.append({"E_ms": E_ms, "injected_sigma_us": sigma_us, "true_offset_ms": true_off_ms, "fit_offset_ms": r["offset_ms"],
                    "per_frame_offset_ms": pf["offset_median_ms"], "recovered_std_us": pf["err_std_us"], "recovered_mad_us": pf["err_mad_sigma_us"],
                    "gamma": pf["gamma"], "n": pf["n"], "corr": r["corr"],
                    "vs_gt_std_us_with_50us_reference": gt["err_std_us"], "vs_gt_offset_ms": gt["offset_ms"], "vs_gt_n": gt["n"]})
    print(results[-1])
if len(sys.argv) > 2 and sys.argv[1] == "--out":
    Path(sys.argv[2]).write_text(json.dumps({"test": "selftest_flash_analyze", "results": results}, indent=2))
