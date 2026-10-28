# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26"]
# ///
"""Check whether per-frame host/OS timestamps are quantised to a fixed grid (e.g. usbvideo isochronous URB completion).
For each timestamp field, searches grid periods 0.5..40 ms for the strongest phase concentration |mean(exp(2 pi i t/G))|
and reports the histogram of intervals rounded to 0.5 ms.
Run: uv run --script research/usb_cameras/timing/scripts/quantization_check.py FRAMES.jsonl [...] [--out result.json]"""
import json, sys
from collections import Counter
from pathlib import Path
import numpy as np

def main():
    args = sys.argv[1:]; out = None
    if "--out" in args:
        i = args.index("--out"); out = args[i + 1]; del args[i:i + 2]
    res = {"test": "quantization_check", "inputs": args, "files": {}}
    for f in args:
        rows = [json.loads(l) for l in open(f)][5:]
        r = {}
        for fld, scale in (("host_arrival_ns", 1), ("os_timestamp_ns", 1), ("mf_sample_time_100ns", 100)):
            if rows and rows[0].get(fld) is not None:
                t = np.array([x[fld] for x in rows], dtype=np.float64) * scale
                t -= t[0]
                grid = np.arange(0.5e6, 40e6, 0.002e6)
                conc = np.array([abs(np.mean(np.exp(2j * np.pi * t / g))) for g in grid])
                # ignore multiples of the frame period by reporting the best grid > 5 ms and its concentration
                k = int(np.argmax(np.where(grid > 5e6, conc, 0)))
                d = np.diff(t) / 1e6
                hist = Counter(np.round(d * 2) / 2)
                r[fld] = {"best_grid_ms": grid[k] / 1e6, "phase_concentration": float(conc[k]),
                          "interval_hist_ms": {str(k2): v for k2, v in sorted(hist.items())}}
        res["files"][f] = r
        print(f, json.dumps({k: (v["best_grid_ms"], round(v["phase_concentration"], 3)) for k, v in r.items()}))
    if out:
        Path(out).write_text(json.dumps(res, indent=2))

main()
