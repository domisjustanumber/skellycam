# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Per-second mean frame luma (and p5/p95 over the second) for every camera in a capture dir: shows whether exposure /
brightness changed during a run. Usage: luma_timeline.py CAPTURE_DIR [--out json]"""
import json, sys
from pathlib import Path
import numpy as np, cv2
args = sys.argv[1:]; out = None
if "--out" in args:
    i = args.index("--out"); out = args[i + 1]; del args[i:i + 2]
cap = Path(args[0]); res = {}
for fj in sorted(cap.glob("*.frames.jsonl")):
    key = fj.name[: -len(".frames.jsonl")]; mj = fj.with_name(key + ".mjpeg")
    rows = [json.loads(l) for l in fj.open() if l.strip()]
    if not rows or not mj.exists():
        continue
    data = mj.read_bytes(); lum = []
    for r in rows[::3]:
        im = cv2.imdecode(np.frombuffer(data, np.uint8, r["payload_bytes"], r["mjpeg_offset"]), cv2.IMREAD_GRAYSCALE)
        lum.append(float(im.mean()) if im is not None else np.nan)
    lum = np.array(lum); per = []
    for s in range(0, len(lum), 10):
        w = lum[s:s + 10]
        per.append([round(float(np.nanmean(w)), 1), round(float(np.nanpercentile(w, 5)), 1), round(float(np.nanpercentile(w, 95)), 1)])
    res[key] = {"per_second_mean_p5_p95": per}
    print(key[:17], " ".join(f"{p[0]:.0f}" for p in per))
if out:
    Path(out).write_text(json.dumps(res, indent=1))
