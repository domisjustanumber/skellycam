# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Per-camera conditions of an mf_uvc_timing capture dir (20261027 overnight re-run).

For every <key>.frames.jsonl (+ optional <key>.mjpeg): frames, wall time, delivered fps (from host arrival), MF errors,
UVC metadata presence (meta_len, PTS/SCR non-null), exposure / WB / gain readback from session.json, and the mean
frame luma (BT.601 Y of decoded JPEG, every --step-th frame) plus the luma std over time (flash visible -> large).
Usage: capture_conditions.py CAPTURE_DIR [--step 15] [--out conditions_capture.json]
"""
import argparse, json
from pathlib import Path
import numpy as np, cv2

ap = argparse.ArgumentParser(); ap.add_argument("capture"); ap.add_argument("--step", type=int, default=15); ap.add_argument("--out")
a = ap.parse_args()
cap = Path(a.capture); res = {"capture": str(cap), "cameras": {}}
for fj in sorted(cap.glob("*.frames.jsonl")):
    key = fj.name[: -len(".frames.jsonl")]
    rows = [json.loads(l) for l in fj.open() if l.strip()]
    ses_p = fj.with_name(key + ".session.json"); ses = json.loads(ses_p.read_text()) if ses_p.exists() else {}
    e = {"friendly_name": ses.get("friendly_name"), "frames": len(rows), "errors": ses.get("errors"), "wall_s": ses.get("wall_s"),
         "controls": ses.get("controls")}
    if rows:
        h = np.array([r["host_arrival_ns"] for r in rows], float)
        e["fps_host_arrival"] = (len(h) - 1) / ((h[-1] - h[0]) / 1e9) if len(h) > 1 else None
        dt = np.diff(h) / 1e6
        e["host_interval_ms"] = {"median": float(np.median(dt)), "max": float(np.max(dt)), "n_gt_50ms": int((dt > 50).sum())} if dt.size else None
        ml = [r.get("meta_len") for r in rows]
        e["meta_len_values"] = {str(k): ml.count(k) for k in set(ml)}
        tops = [(r.get("meta_items") or [{}])[0].get("_top", {}) for r in rows]
        e["frames_with_uvc_pts"] = sum(1 for t in tops if t.get("uvc_pts") is not None)
        e["frames_with_uvc_scr"] = sum(1 for t in tops if t.get("uvc_scr_stc") is not None)
        e["jpeg_soi_eoi_ok"] = sum(1 for r in rows if r.get("jpeg_soi") and r.get("jpeg_eoi"))
        mj = fj.with_name(key + ".mjpeg")
        if mj.exists():
            data = mj.read_bytes(); lum = []
            for r in rows[:: a.step]:
                im = cv2.imdecode(np.frombuffer(data, np.uint8, r["payload_bytes"], r["mjpeg_offset"]), cv2.IMREAD_GRAYSCALE)
                if im is not None:
                    lum.append(float(im.mean()))
            if lum:
                e["luma_mean"] = float(np.mean(lum)); e["luma_min"] = float(np.min(lum)); e["luma_max"] = float(np.max(lum))
                e["luma_std_over_time"] = float(np.std(lum)); e["luma_samples"] = len(lum)
    res["cameras"][key] = e
txt = json.dumps(res, indent=1); print(txt)
if a.out:
    Path(a.out).write_text(txt)
