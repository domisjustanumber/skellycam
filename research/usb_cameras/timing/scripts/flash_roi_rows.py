# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Skeptic check for flash_analyze.py: the auto-ROI moves between runs, and with a rolling shutter (and display
scan-out) the fitted offset depends on WHICH image rows the ROI covers. This refits one timestamp source with the
ROI forced to fixed blocks at a fixed column band and several row positions, so offsets can be compared between
runs/exposures at the same rows, and the offset-vs-row slope (rolling-shutter + scan-out time across the frame)
is measured.

Usage: uv run --script flash_roi_rows.py --display DIR --capture DIR --cam SUBSTR --col-frac F
         [--rows-frac 0.2,0.3,...] [--source NAME] [--skip-first N] [--out json]
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flash_analyze as fa  # noqa: E402
af = fa.af


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--display", required=True); ap.add_argument("--capture", required=True)
    ap.add_argument("--cam", required=True); ap.add_argument("--col-frac", type=float, required=True)
    ap.add_argument("--rows-frac", default="0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9")
    ap.add_argument("--source", default="uvc_pts_mapped_direct"); ap.add_argument("--skip-first", type=int, default=5)
    ap.add_argument("--out")
    a = ap.parse_args()
    disp = fa.load_display(Path(a.display))
    fj = next(p for p in sorted(Path(a.capture).glob("*.frames.jsonl")) if a.cam.lower() in p.name.lower())
    key = fj.name[: -len(".frames.jsonl")]; mj = fj.with_name(key + ".mjpeg")
    rows = af.load(fj)[a.skip_first:]
    ses = json.loads(fj.with_name(key + ".session.json").read_text())
    E = 2.0 ** ses["controls"]["exposure_log2"]["value"] * 1e9
    ana = af.analyze(rows, None, 0, 32); arr = ana.pop("_arrays")
    X = arr["sources"][a.source].astype(float); m = arr["masks"].get(a.source)
    if m is not None: X[~m] = np.nan
    data = mj.read_bytes()
    stack = np.stack([cv2.imdecode(np.frombuffer(data, np.uint8, r["payload_bytes"], r["mjpeg_offset"]),
                                   cv2.IMREAD_REDUCED_GRAYSCALE_8).astype(np.float32) for r in rows])
    N, H, W = stack.shape
    bh, bw = max(2, H // 24), max(2, W // 24)
    c0 = int(np.clip(round(a.col_frac * W - bw / 2), 0, W - bw))
    out = {"test": "flash_roi_rows", "capture": a.capture, "camera_key": key, "source": a.source, "E_ms": E / 1e6,
           "decoded_shape": [H, W], "cols": [c0, c0 + bw], "rows": []}
    print(f"== {key[:17]} E={E/1e6:.3f} ms source={a.source} cols={c0}-{c0+bw} of {W}")
    for rf in [float(v) for v in a.rows_frac.split(",")]:
        r0 = int(np.clip(round(rf * H - bh / 2), 0, H - bh))
        y = stack[:, r0:r0 + bh, c0:c0 + bw].reshape(N, -1).mean(1)
        res = fa.fit_source(X, y, disp, E); res.pop("_gt", None); pf = res.get("per_frame") or {}
        ent = {"row_center_frac": (r0 + bh / 2) / H, "temporal_std": float(np.std(y)), "corr": res["corr"],
               "fit_offset_ms": res["offset_ms"], "pf_offset_ms": pf.get("offset_median_ms"), "pf_std_us": pf.get("err_std_us"),
               "n": pf.get("n")}
        out["rows"].append(ent)
        print(f"   row={ent['row_center_frac']:.3f} tstd={ent['temporal_std']:6.1f} corr={ent['corr']:.4f} fitoff={ent['fit_offset_ms']:8.2f} "
              f"pf_off={ent['pf_offset_ms'] if ent['pf_offset_ms'] is None else round(ent['pf_offset_ms'],3)} "
              f"std={ent['pf_std_us'] if ent['pf_std_us'] is None else round(ent['pf_std_us'])} n={ent['n']}")
    good = [e for e in out["rows"] if e["corr"] > 0.95 and e["pf_offset_ms"] is not None]
    if len(good) >= 3:
        p = np.polyfit([e["row_center_frac"] for e in good], [e["pf_offset_ms"] for e in good], 1)
        out["offset_vs_row_slope_ms_per_frame_height"] = float(p[0]); out["offset_at_row_0p5_ms"] = float(np.polyval(p, 0.5))
        print(f"   slope d(offset)/d(row frac) = {p[0]:.2f} ms per frame height; offset at row 0.5 = {np.polyval(p, 0.5):.3f} ms (rows with corr>0.95: {len(good)})")
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=2, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
