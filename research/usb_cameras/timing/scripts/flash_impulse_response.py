# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Temporal impulse response of a camera ROI to the flash display (no box-exposure assumption): least squares
y_k = c + sum_j h_j * mean(s over [X_k + L_j, X_k + L_j + dL]) with X = seq_env (frame index + host-arrival lower
envelope, no device timestamp) and lag bins L_j spanning -LMAX..+LMAX. A box exposure gives a single block of width E;
temporal noise filtering (frame blending) shows as weight in bins one or more frame periods earlier.
Usage: flash_impulse_response.py RUN_DIR COL ROW [--cam c922] [--bin-ms 2] [--lmax-ms 200] [--out json]"""
import sys, json, argparse
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flash_libuvc_scr as m  # noqa: E402
ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("col", type=float); ap.add_argument("row", type=float)
ap.add_argument("--cam", default="c930e"); ap.add_argument("--bin-ms", type=float, default=2.0); ap.add_argument("--lmax-ms", type=float, default=200)
ap.add_argument("--out")
ap.add_argument("--mf-glob", help="use the MF capture (RUN/capture/<glob>.frames.jsonl + .mjpeg) of any camera, e.g. '*0843*'; --cam is then only the label")
a = ap.parse_args()
run = Path(a.run); disp = m.load_display_robust(run / "display_m0")
if a.cam == "c922" or a.mf_glob:
    cj = sorted((run / "capture").glob((a.mf_glob or "*085c*") + ".frames.jsonl"))[0]
    rows = m.af.load(cj)[15:]; stack = m.decode_mjpeg(rows, cj.with_name(cj.name.replace(".frames.jsonl", ".mjpeg")))
    srcs, _ = m.c922_sources(rows)
else:
    ud = run / "c930e_libuvc"; rows = m.load_jsonl(ud / "frames.jsonl")[15:]
    stack = m.decode_dir([ud / f"frame_{r['seq']:05d}.jpg" for r in rows])
    srcs, _ = m.c930e_sources(rows, m.frame_clock(ud / "usb_frame_qpc.jsonl"))
y, box = m.roi_series(stack, a.row, a.col)
y = (y - np.percentile(y, 2)) / (np.percentile(y, 98) - np.percentile(y, 2))
X = srcs["seq_env"]; dc = m.fa.cumulative(disp); dL = a.bin_ms * 1e6
lags = np.arange(-a.lmax_ms * 1e6, a.lmax_ms * 1e6, dL)
A = np.stack([m.fa.window_mean(dc, X + L, dL) for L in lags] + [np.ones_like(X)], 1)
ok = (X + lags[0] > dc[0][0]) & (X + lags[-1] + dL < dc[0][-1])
for gname, yy in (("gamma1", y), ("gamma2.2", np.clip(y, 0, 1) ** 2.2)):
    h, *_ = np.linalg.lstsq(A[ok], yy[ok], rcond=None)
    hh = h[:-1]; pred = A[ok] @ h; r2 = 1 - np.var(yy[ok] - pred) / np.var(yy[ok])
    tot = hh.sum(); c = np.cumsum(hh) / tot
    i10, i50, i90 = [int(np.searchsorted(c, q)) for q in (0.1, 0.5, 0.9)]
    pk = int(np.argmax(hh))
    res = {"tone": gname, "r2": float(r2), "sum_h": float(tot), "peak_lag_ms": float(lags[pk] / 1e6),
           "lag_10_50_90_ms": [float(lags[i] / 1e6) for i in (i10, i50, i90)],
           "width_10_90_ms": float((lags[i90] - lags[i10]) / 1e6),
           "h_by_lag_ms": {f"{L/1e6:.0f}": round(float(v / tot), 4) for L, v in zip(lags, hh) if abs(v / tot) > 0.01}}
    print(a.cam, json.dumps(res))
    if a.out:
        p = Path(a.out); d = json.loads(p.read_text()) if p.exists() else {}
        d[f"{a.cam}_{gname}_row{a.row}_col{a.col}"] = res; p.write_text(json.dumps(d, indent=1))
