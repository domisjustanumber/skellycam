# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Skeptic check for flash_analyze.py: is the nominal exposure (2**exposure_log2 s) the exposure the camera used?
For one timestamp source per camera, refit the flash model with E scanned over a grid and report corr, fitted
offset, and the per-frame window-centre offset (offset + E/2). The E that maximises corr estimates the true
exposure; the window-centre offset is insensitive to a wrong E, the window-start offset is not.

Usage: uv run --script flash_exposure_scan.py --display DIR --capture DIR [--source NAME] [--skip-first N] [--out json]
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flash_analyze as fa  # noqa: E402
af = fa.af


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--display", required=True); ap.add_argument("--capture", required=True)
    ap.add_argument("--source", default="uvc_pts_mapped_direct"); ap.add_argument("--skip-first", type=int, default=5)
    ap.add_argument("--grid-ms", default="1,1.5,2,2.5,3,4,5,6,7,7.8125,8.5,10,12,14,15.625,17,20")
    ap.add_argument("--out")
    a = ap.parse_args()
    disp = fa.load_display(Path(a.display))
    out = {"test": "flash_exposure_scan", "display": a.display, "capture": a.capture, "source": a.source, "cameras": []}
    for fj in sorted(Path(a.capture).glob("*.frames.jsonl")):
        key = fj.name[: -len(".frames.jsonl")]; mj = fj.with_name(key + ".mjpeg")
        rows = af.load(fj)[a.skip_first:]
        if len(rows) < 20 or not mj.exists():
            continue
        ses = json.loads(fj.with_name(key + ".session.json").read_text())
        En = 2.0 ** ses["controls"]["exposure_log2"]["value"] * 1e3
        ana = af.analyze(rows, None, 0, 32); arr = ana.pop("_arrays")
        X = arr["sources"][a.source].astype(float); m = arr["masks"].get(a.source)
        if m is not None: X[~m] = np.nan
        y, _ = fa.roi_signal(rows, mj)
        scan = []
        for e in [float(v) for v in a.grid_ms.split(",")]:
            r = fa.fit_source(X, y, disp, e * 1e6); r.pop("_gt", None); pf = r.get("per_frame") or {}
            scan.append({"E_ms": e, "corr": r["corr"], "fit_offset_ms": r["offset_ms"],
                         "pf_offset_ms": pf.get("offset_median_ms"), "pf_std_us": pf.get("err_std_us"), "n": pf.get("n"),
                         "centre_offset_ms": (pf["offset_median_ms"] + e / 2) if pf else None})
        best = max(scan, key=lambda s: s["corr"])
        out["cameras"].append({"camera_key": key, "E_nominal_ms": En, "scan": scan, "E_best_corr_ms": best["E_ms"]})
        print(f"== {key[:17]} nominal E={En:.3f} ms  source={a.source}  best-corr E={best['E_ms']} ms")
        for s in scan:
            print(f"   E={s['E_ms']:7.3f} corr={s['corr']:.4f} fitoff={s['fit_offset_ms']:8.2f} pf_off={s['pf_offset_ms'] if s['pf_offset_ms'] is None else round(s['pf_offset_ms'],3)} "
                  f"centre={s['centre_offset_ms'] if s['centre_offset_ms'] is None else round(s['centre_offset_ms'],3)} std={s['pf_std_us'] if s['pf_std_us'] is None else round(s['pf_std_us'])} n={s['n']}")
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=2, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
