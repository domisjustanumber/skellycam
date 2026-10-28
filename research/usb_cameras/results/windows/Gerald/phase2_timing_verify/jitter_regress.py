# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Adversarial check: is the C930e SCR frame-start jitter (scr_first_stc - periodic fit) visible in the flash GT?
Regress e_seq = w - X_periodic on d = X_scr - X_periodic per GT frame (pooled over rows). slope ~1 => exposure
follows the SCR jitter; slope ~0 => SCR jitter is not exposure jitter. Also a sensitivity test: add synthetic
gaussian noise to seq_env and check that the GT std rises in quadrature.
Usage: jitter_regress.py RUN_DIR [RUN_DIR ...]"""
import sys, json
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/timing/scripts")
import flash_libuvc_scr as m  # noqa: E402

out = {}
for run in map(Path, sys.argv[1:]):
    disp = m.load_display_robust(run / "display_m0")
    ud = run / "c930e_libuvc"
    rows = m.load_jsonl(ud / "frames.jsonl")[30:]
    files = [ud / f"frame_{r['seq']:05d}.jpg" for r in rows]
    keep = [i for i, p in enumerate(files) if p.exists()]
    rows = [rows[i] for i in keep]; files = [files[i] for i in keep]
    stack = m.decode_dir(files)
    fc = m.frame_clock(ud / "usb_frame_qpc.jsonl")
    srcs, clk = m.c930e_sources(rows, fc)
    per = srcs["seq_fit_to_scr_first"]; scr = srcs["scr_first_stc"]; seqenv = srcs["seq_env"]
    d = scr - per
    E_all, D_all = [], []
    rng = np.random.default_rng(1)
    sens = {}
    for rf in (0.2, 0.35, 0.5, 0.65, 0.8):
        y, _ = m.roi_series(stack, rf, 0.5)
        gt = m.gt_fixed(seqenv, y, disp, 7.8e6, 2.2)
        k = gt["k"]
        e = gt["w"] - per[k]; e = e - np.median(e)
        E_all.append(e); D_all.append(d[k] - np.median(d[k]))
        for s_us in (300, 500):
            Xn = seqenv + rng.normal(0, s_us * 1e3, seqenv.size)
            sc = m.score(Xn, gt); sc0 = m.score(seqenv, gt)
            sens.setdefault(str(s_us), []).append([round(sc0["err_std_us"]), round(sc["err_std_us"]),
                                                   round(float(np.hypot(sc0["err_std_us"], s_us)))])
    E = np.concatenate(E_all); D = np.concatenate(D_all)
    A = np.vstack([D, np.ones_like(D)]).T
    coef, res, *_ = np.linalg.lstsq(A, E, rcond=None)
    resid = E - A @ coef
    se = np.sqrt(np.sum(resid ** 2) / (len(E) - 2) / np.sum((D - D.mean()) ** 2))
    # robust: drop |e| > 3 ms
    mk = np.abs(E) < 3e6
    c2 = np.polyfit(D[mk], E[mk], 1)
    out[run.name] = {"n": int(E.size), "d_std_us": float(np.std(D) / 1e3), "e_std_us": float(np.std(E) / 1e3),
                     "slope_e_periodic_on_scr_jitter": float(coef[0]), "slope_se": float(se),
                     "slope_robust_abs_e_lt_3ms": float(c2[0]),
                     "std_e_periodic_us": float(np.std(E) / 1e3), "std_e_scr_us": float(np.std(E - D) / 1e3),
                     "sensitivity_seq_env_plus_noise[base,with_noise,expected_quadrature]": sens,
                     "stc_first_step_std_us": clk["stc_first_step_ms"]["std"] * 1e3}
    print(run.name, json.dumps(out[run.name]))
if len(sys.argv) > 1:
    Path(__file__).with_name("jitter_regress_out.json").write_text(json.dumps(out, indent=1))
