# rerun20261027 helper: per frames_*.jsonl, histogram of (host_arrival_ns - implied_sample_time_ns) and of
# sample-time intervals, after skipping 30 frames. Usage: python lat_grid.py <run_dir> [...]
import json, sys, glob, os, statistics as st
from collections import Counter
for d in sys.argv[1:]:
    for f in sorted(glob.glob(os.path.join(d, 'frames_*.jsonl'))):
        rows = [json.loads(l) for l in open(f, encoding='utf-8') if l.strip()][30:]
        if not rows: print(os.path.basename(d), os.path.basename(f), 'no frames'); continue
        k = 'implied_sample_time_ns' if 'implied_sample_time_ns' in rows[0] else 'os_timestamp_ns'
        lat = [(r['host_arrival_ns'] - r[k]) / 1e6 for r in rows if r.get(k)]
        iv = [(b[k] - a[k]) / 1e6 for a, b in zip(rows, rows[1:]) if a.get(k) and b.get(k)]
        lb = Counter(f"{int(x // 8) * 8}-{int(x // 8) * 8 + 8}" for x in lat)
        ib = Counter(round(x) for x in iv)
        print(os.path.basename(d), os.path.basename(f)[7:30], 'field', k, 'n', len(lat), 'lat_p50 %.2f' % st.median(lat),
              'lat_bins_ms', dict(sorted(lb.items(), key=lambda t: int(t[0].split('-')[0]))), 'interval_ms', dict(sorted(ib.items())))
