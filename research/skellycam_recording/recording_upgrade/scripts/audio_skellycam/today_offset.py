"""How wrong is skellycam's current audio sync anchor? It assumes sample 0 was captured at start_perf_ns,
taken just BEFORE stream.start(). Compare with the time of sample 0 from a fit (callback times, envelope,
after a 10 s start-up exclusion; and ADC times where the host API gives them). Timing only.
Usage: python -I today_offset.py <device_timing_dir> <raw_dir> <out_json>
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_timing import env, fit  # noqa: E402

out = {}
for f in sorted(os.listdir(sys.argv[1])):
    if not f.endswith(".json") or f == "analysis.json":
        continue
    j = json.load(open(os.path.join(sys.argv[1], f)))
    raw = os.path.join(sys.argv[2], f.replace(".json", ".npz"))
    if not os.path.exists(raw):
        continue
    z = np.load(raw); host, adc, frames, rate = z["host"], z["adc"], z["frames"], int(z["rate"])
    t_start_ns = host[0] - j["first_callback_after_start_ms"] * 1e6
    s0 = np.concatenate([[0], np.cumsum(frames)[:-1]]).astype(float); se = s0 + frames
    th = (host - t_start_ns) / 1e6  # ms since start_perf_ns
    m = th >= 10000 + th[0]
    a, b, _ = env(se[m], th[m])           # callback arrives after the block's last sample: lower envelope ~ capture + fixed latency
    row = dict(rate=rate, first_callback_after_start_ms=j["first_callback_after_start_ms"],
               sample0_from_callback_envelope_ms=round(float(a), 2))
    if np.all(adc > 1.0):
        ta = (adc * 1e9 - t_start_ns) / 1e6
        a2, b2, r2, _ = fit(s0[m], ta[m])
        row["sample0_from_adc_fit_ms"] = round(float(a2), 2)
    out[f] = row
    print(f, row)
json.dump(dict(note="ms after start_perf_ns (today's anchor). Positive = sample 0 was captured later than skellycam assumes, so today's offset puts audio that much early.", runs=out), open(sys.argv[3], "w"), indent=1)
