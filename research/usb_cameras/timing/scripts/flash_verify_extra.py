# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Skeptic add-on to flash_analyze.py (does not modify it): evaluates extra timestamp sources against the SAME
flash ground truth that flash_analyze.py uses (GT reference source = original sources' best per-frame std), and
characterises UVC PTS steps.

Extra sources:
  seq_envelope              host_arrival lower-envelope fitted against the MF frame index (no UVC metadata needed)
  uvc_pts_destepped_direct  PTS with every step that is ~k x the median step (k>=2) reduced to one median step,
                            then mapped like uvc_pts_mapped_direct (lower envelope vs host arrival)
  uvc_stc_mapped_direct     SCR STC (first-payload bus time) mapped like uvc_pts_mapped_direct
  uvc_pts_via_stc_line      PTS mapped with the STC->host lower-envelope line (PTS assumed on the STC clock)
Also reports PTS step anomalies (index, ratio, host-arrival gap) and the STC-PTS range.

Usage: uv run --script flash_verify_extra.py --display DIR --capture DIR [--out json]
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
    ap.add_argument("--display", required=True); ap.add_argument("--capture", required=True); ap.add_argument("--out")
    ap.add_argument("--skip-first", type=int, default=5)
    a = ap.parse_args()
    disp = fa.load_display(Path(a.display))
    out = {"test": "flash_verify_extra", "display": a.display, "capture": a.capture, "cameras": []}
    for fj in sorted(Path(a.capture).glob("*.frames.jsonl")):
        key = fj.name[: -len(".frames.jsonl")]
        mj = fj.with_name(key + ".mjpeg")
        rows = af.load(fj)[a.skip_first:]
        if len(rows) < 20 or not mj.exists():
            continue
        ses = json.loads(fj.with_name(key + ".session.json").read_text())
        E = 2.0 ** ses["controls"]["exposure_log2"]["value"] * 1e9
        ana = af.analyze(rows, None, 0, 32); arr = ana.pop("_arrays")
        srcs = {}
        for name, X in arr["sources"].items():
            Xf = X.astype(float); m = arr["masks"].get(name)
            if m is not None: Xf[~m] = np.nan
            srcs[name] = Xf
        y, info = fa.roi_signal(rows, mj)
        host = arr["host"].astype(float)
        seq = np.array([r.get("seq", i) for i, r in enumerate(rows)], float)
        extra = {}
        a2, b2 = af.lower_envelope_fit(seq, host); extra["seq_envelope"] = a2 + b2 * seq
        pts = af.unwrap(np.array([r["uvc_pts"] for r in rows], dtype=np.int64), 32).astype(float)
        dp = np.diff(pts); med = np.median(dp)
        steps = [{"idx": int(i), "ratio": float(dp[i] / med), "host_gap_ms": float((host[i + 1] - host[i]) / 1e6)}
                 for i in np.flatnonzero(np.abs(dp - med) > 0.5 * med)]
        dpc = np.where(np.abs(dp / med - np.round(dp / med)) < 0.05, np.where(dp > 1.5 * med, med, dp), dp)
        ptsd = np.concatenate([[pts[0]], pts[0] + np.cumsum(dpc)])
        a2, b2 = af.lower_envelope_fit(ptsd, host); extra["uvc_pts_destepped_direct"] = a2 + b2 * ptsd
        stc = af.unwrap(np.array([r["uvc_scr_stc"] for r in rows], dtype=np.int64), 32).astype(float)
        a2, b2 = af.lower_envelope_fit(stc, host); extra["uvc_stc_mapped_direct"] = a2 + b2 * stc
        # PTS read on the STC clock: map with the STC->host line (assumes PTS and STC count the same device clock)
        extra["uvc_pts_via_stc_line"] = a2 + b2 * pts
        stc_minus_pts_ms = (stc - pts) / (1.0 / b2) / 1e6 if b2 else None
        res = {}; gts = {}
        for name, X in srcs.items():
            res[name] = fa.fit_source(X, y, disp, E); gts[name] = res[name].pop("_gt", None)
        ok = [n for n in srcs if res[n].get("per_frame") and gts[n] is not None]
        ref = min(ok, key=lambda n: res[n]["per_frame"]["err_std_us"])
        for name, X in extra.items():
            res[name] = fa.fit_source(X, y, disp, E); res[name].pop("_gt", None)
        for name in res:
            X = srcs.get(name, extra.get(name))
            res[name]["vs_ground_truth"] = fa.vs_ground_truth(X, gts[ref])
        cam = {"camera_key": key, "E_ms": E / 1e6, "roi": info, "gt_reference": ref, "pts_median_step": float(med),
               "pts_steps": steps, "sources": res,
               "stc_minus_pts_ms": {"min": float(np.min(stc_minus_pts_ms)), "max": float(np.max(stc_minus_pts_ms))}}
        out["cameras"].append(cam)
        print(f"== {key[:17]} E={E/1e6:.2f} ms ref={ref} roi_rows={info['roi_rows']} pts_steps={steps}")
        for n, r in res.items():
            g = r["vs_ground_truth"]; pf = r.get("per_frame") or {}
            print(f"   {n:30s} corr={r['corr']:.3f} fitoff={r['offset_ms']:8.2f}  pf_std={pf.get('err_std_us', float('nan')):7.0f}"
                  f"  | GT off={g['offset_ms']:8.3f} ms std={g['err_std_us']:7.0f} us mad={g['err_mad_sigma_us']:7.0f} n={g['n']}")
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=2, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
