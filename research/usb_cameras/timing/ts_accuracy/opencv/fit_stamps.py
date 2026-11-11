"""Frame-slot fit (suite/common/tsanalysis.fit_frame_index, non-causal, lower envelope) on the probe outputs.
    python -I fit_stamps.py <research/usb_cameras/suite dir> <opencv_results dir>   (no camera)"""
import json, sys, os
sys.path.insert(0, sys.argv[1])
from common import tsanalysis as T
R = sys.argv[2]
def load(p): return [json.loads(l) for l in open(p)]
cases = [("dshow work0 post-retrieve t2", "dshow_c930e_aep0/frames_work0.jsonl", lambda r: r["t2"]),
         ("dshow work0 pre-grab t0 (skellycam-style)", "dshow_c930e_aep0/frames_work0.jsonl", lambda r: r["t0"]),
         ("dshow work20 post-retrieve t2", "dshow_c930e_aep0/frames_work20.jsonl", lambda r: r["t2"]),
         ("dshow work50 post-retrieve t2 (stale)", "dshow_c930e_aep0/frames_work50.jsonl", lambda r: r["t2"]),
         ("msmf raw(NV12) work0 POS_MSEC", "msmf_c930e_rawfirst/hwT0_rawfirst/frames_raw_work0.jsonl", lambda r: r["pos_msec"] * 1e6),
         ("msmf raw(NV12) work0 post-grab", "msmf_c930e_rawfirst/hwT0_rawfirst/frames_raw_work0.jsonl", lambda r: r["t_post_grab"]),
         ("msmf raw(NV12) work50 POS_MSEC", "msmf_c930e_rawfirst/hwT0_rawfirst/frames_raw_work50.jsonl", lambda r: r["pos_msec"] * 1e6),
         ("msmf raw(NV12) work50 post-grab (stale)", "msmf_c930e_rawfirst/hwT0_rawfirst/frames_raw_work50.jsonl", lambda r: r["t_post_grab"])]
out = {}
for name, f, g in cases:
    rows = load(os.path.join(R, f))
    t = [g(r) for r in rows]
    fit = T.fit_frame_index(t, causal=False, nominal_period_ns=1e9 / 30)
    out[name] = {k: fit.get(k) for k in ("fps", "residual_stats_ms", "slots_skipped", "duplicate_slots", "drops_detectable", "grid_ms", "fit_unreliable", "unreliable_reasons")}
    # offset between the two stamp kinds of one run is printed separately below
    print(name, json.dumps(out[name], default=lambda x: round(x, 3) if isinstance(x, float) else str(x)))
# mean offset of DSHOW t0 vs t2 of the same frame and of the previous frame
rows = load(os.path.join(R, "dshow_c930e_aep0/frames_work0.jsonl"))
d_same = sorted((r["t2"] - r["t0"]) / 1e6 for r in rows)
d_prev = sorted((b["t0"] - a["t2"]) / 1e6 for a, b in zip(rows, rows[1:]))
print("dshow work0: t2 - t0 same frame p50/p95 ms", round(d_same[len(d_same)//2], 3), round(d_same[int(.95*len(d_same))], 3),
      "| t0(k) - t2(k-1) p50/max ms", round(d_prev[len(d_prev)//2], 4), round(d_prev[-1], 4))
json.dump(out, open(os.path.join(R, "fit_stamps.json"), "w"), indent=1, default=str)
