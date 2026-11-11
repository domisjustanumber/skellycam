"""Stats of CAP_PROP_POS_MSEC vs host stamp in the 10-27 OpenCV cells (read-only)."""
import json, glob, os, sys, statistics as st
root = sys.argv[1]
for f in sorted(glob.glob(os.path.join(root, 'mjpeg_opencv-*', '*', 'frames.jsonl'))):
    p = f.replace(os.sep, '/').split('/')
    rows = [json.loads(l) for l in open(f)]
    by = {}
    for r in rows:
        by.setdefault(r['camera_key'], []).append(r)
    for cam, rs in by.items():
        rs = [r for r in rs if r.get('in_window', True)] or rs
        pm = [r['pos_msec'] for r in rs]
        ha = [r['host_arrival_ns'] / 1e6 for r in rs]
        if len(rs) < 10:
            continue
        neg = sum(1 for v in pm if v is None or v < 0)
        line = f"{p[-3][13:]:13s} {p[-2][:40]:40s} {cam:6s} n={len(rs):4d} posmsec<0:{neg}"
        if neg == 0:
            lat = [h - v for h, v in zip(ha, pm)]
            d = [b - a for a, b in zip(pm, pm[1:])]
            dh = [b - a for a, b in zip(ha, ha[1:])]
            zero = sum(1 for x in d if abs(x) < 1e-6)
            q = st.quantiles(lat, n=20)
            line += (f" host-pos ms: p5={q[0]:.2f} med={st.median(lat):.2f} p95={q[-1]:.2f} max={max(lat):.2f}"
                     f" | pos step med={st.median(d):.3f} min={min(d):.3f} max={max(d):.3f} sd={st.pstdev(d):.3f} zero-steps={zero}"
                     f" | host step sd={st.pstdev(dh):.3f} | gaps>1.5P={sum(1 for x in d if x > 1.5*st.median(d))}")
        print(line)
