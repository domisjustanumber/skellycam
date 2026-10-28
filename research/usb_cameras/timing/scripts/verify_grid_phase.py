# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26"]
# ///
"""Independent check of OS-timestamp quantisation: absolute phase on a G-ms grid (common QPC), interval multiples."""
import json, sys, numpy as np
G = float(sys.argv[1]) * 1e6
out = {}
for f in sys.argv[2:]:
    rows = [json.loads(l) for l in open(f)][5:]
    if not rows: continue
    r = {}
    for fld, sc in (("host_arrival_ns", 1), ("os_timestamp_ns", 1), ("mf_undoc_d06f8a46_ns", 1)):
        if rows[0].get(fld) is None: continue
        t = np.array([x[fld] for x in rows], float) * sc
        ph = (t % G)
        z = np.exp(2j*np.pi*ph/G); m = np.mean(z)
        mean_ph = (np.angle(m) % (2*np.pi)) / (2*np.pi) * G
        dev = ((ph - mean_ph + G/2) % G) - G/2
        d = np.diff(t)
        mult = np.round(d / G); res = d - mult*G
        r[fld] = {"n": len(t), "phase_ms": round(mean_ph/1e6, 3), "phase_dev_std_us": round(float(np.std(dev))/1e3, 1),
                  "frac_intervals_within_100us_of_kG": round(float(np.mean(np.abs(res) < 1e5)), 4),
                  "interval_multiples": {int(k): int(v) for k, v in zip(*np.unique(mult, return_counts=True))},
                  "mean_interval_ms": round(float(np.mean(d))/1e6, 4)}
    import os; out[os.path.basename(f)[:30]] = r
print(json.dumps(out, indent=1))
