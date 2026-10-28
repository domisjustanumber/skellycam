# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Rolling-shutter / PTS-semantics analysis of a screen-flash run.

For one timestamp source, measures the exposure-start offset d (flash_analyze.fit_source) separately for small ROI
blocks at many image rows that see the flashing screen, then fits d(row) = d0 + T_ro * row/H:
  * T_ro  = rolling-shutter readout time over the full image height (ms) (plus any display scan-out gradient along
            the same direction -- the display scans its own rows in 16.68 ms; report notes the geometry),
  * d0    = offset of the exposure start of image row 0 relative to the timestamp source.
Comparing d0 across runs with different exposure times E tells what the UVC PTS marks: d0 constant -> PTS ~ start of
exposure (of row 0); d0 shifting by -dE -> PTS ~ end of exposure.

Run: uv run --script research/usb_cameras/timing/scripts/flash_rows.py --display RUN/display_m0 --capture RUN/capture
         [--source uvc_pts_via_scr_lsq_envelope] [--out rows.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flash_analyze as fa  # noqa: E402

af = fa.af


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--display", required=True); ap.add_argument("--capture", required=True)
    ap.add_argument("--source", default="uvc_pts_via_scr_lsq_envelope"); ap.add_argument("--out")
    ap.add_argument("--min-std-frac", type=float, default=0.5)
    a = ap.parse_args()
    disp = fa.load_display(Path(a.display))
    out = {"test": "flash_rows", "command": " ".join(sys.argv), "source": a.source, "cameras": []}
    for fj in sorted(Path(a.capture).glob("*.frames.jsonl")):
        key = fj.name[:-len(".frames.jsonl")]
        mj = fj.with_name(key + ".mjpeg")
        rows = af.load(fj)[5:]
        if len(rows) < 50 or not mj.exists():
            continue
        ses = json.loads(fj.with_name(key + ".session.json").read_text())
        E = 2.0 ** ses["controls"]["exposure_log2"]["value"] * 1e9
        ana = af.analyze(rows, None, 0, 32); arr = ana.pop("_arrays")
        X = arr["sources"][a.source].astype(float); m = arr["masks"].get(a.source)
        if m is not None:
            X[~m] = np.nan
        data = mj.read_bytes()
        stack = np.stack([cv2.imdecode(np.frombuffer(data, np.uint8, r["payload_bytes"], r["mjpeg_offset"]), cv2.IMREAD_REDUCED_GRAYSCALE_8).astype(np.float32) for r in rows])
        sd = stack.std(0); H, W = sd.shape
        bw = max(2, W // 24)
        thr = a.min_std_frac * sd.max()
        res = []
        for r in range(0, H - 1, 2):
            band = sd[r:r + 2]
            cs = np.convolve(band.mean(0), np.ones(bw) / bw, mode="valid")
            c0 = int(np.argmax(cs))
            if cs[c0] < thr:
                continue
            mask = np.zeros_like(sd, bool); mask[r:r + 2, c0:c0 + bw] = True
            y = stack[:, mask].mean(1)
            f = fa.fit_source(X, y, disp, E)
            pf = f.get("per_frame") or {}
            if f["corr"] < 0.8:
                continue
            res.append({"row": r + 1, "col": c0 + bw / 2, "corr": f["corr"], "offset_ms": f["offset_ms"],
                        "per_frame_offset_ms": pf.get("offset_median_ms"), "per_frame_n": pf.get("n"), "per_frame_std_us": pf.get("err_std_us")})
        cam = {"camera_key": key, "E_ms": E / 1e6, "decoded_H": H, "blocks": res}
        if len(res) >= 3:
            rr = np.array([b["row"] for b in res]) / H
            dd = np.array([b["per_frame_offset_ms"] if b["per_frame_offset_ms"] is not None and (b["per_frame_n"] or 0) >= 8 else b["offset_ms"] for b in res])
            a0, slope, resid = af.linfit(rr, dd)
            cam.update({"d0_ms_row0": float(a0), "readout_ms_full_height": float(slope), "fit_resid_ms_std": float(resid.std()),
                        "row_frac_range": [float(rr.min()), float(rr.max())], "n_blocks": len(res)})
        out["cameras"].append(cam)
        print(key[:18], f"E={E/1e6:.2f}ms", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in cam.items() if k not in ("blocks", "camera_key")})
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=2, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
