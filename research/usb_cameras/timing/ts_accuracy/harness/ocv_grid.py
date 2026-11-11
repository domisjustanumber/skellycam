"""Offline: are OpenCV CAP_DSHOW read()-return host times on the 16 ms grid? Reads existing frames.jsonl only."""
import json, sys, math, statistics as st
for f in sys.argv[1:]:
    rows = [json.loads(l) for l in open(f)]
    by = {}
    for r in rows:
        by.setdefault(r.get("camera_key"), []).append(r)
    for cam, rs in by.items():
        rs = [r for r in rs if r.get("in_window", True)]
        t = [r["host_arrival_ns"] for r in rs if r.get("host_arrival_ns")]
        iv = [(b - a) / 1e6 for a, b in zip(t, t[1:])]
        if len(iv) < 10: continue
        # phase concentration on 16 ms
        z = sum(complex(math.cos(2*math.pi*x/16.0), math.sin(2*math.pi*x/16.0)) for x in iv) / len(iv)
        near = sum(1 for x in iv if abs(x - 16*round(x/16)) < 0.5) / len(iv)
        # whole-run frame-index residual (sequence slots)
        n = len(t); xs = list(range(n)); mx = sum(xs)/n; my = sum(t)/n
        b = sum((x-mx)*(y-my) for x, y in zip(xs, t)) / sum((x-mx)**2 for x in xs); a = my - b*mx
        res = [(y - a - b*x)/1e6 for x, y in zip(xs, t)]
        print(f"{f.split('Gerald/')[-1]} | {cam} | n={n} fps={1e9/b:.3f} | iv mean={st.mean(iv):.2f} std={st.pstdev(iv):.2f} min={min(iv):.2f} max={max(iv):.2f} | 16ms phase R={abs(z):.3f} within0.5ms={near:.2f} | seq-fit resid std={st.pstdev(res):.2f} ms")
