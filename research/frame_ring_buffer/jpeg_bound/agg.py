import json, os, collections, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
rows = [json.loads(l) for l in open(os.path.join(HERE, 'scan_files.jsonl'))]
STD = [5, 7.5, 10, 15, 20, 24, 25, 30, 60, 90, 120]


def snap(f):
    if not f:
        return None
    return min(STD, key=lambda s: abs(s - f))


groups = collections.defaultdict(list)
srcs = collections.defaultdict(list)
miss = collections.Counter()
for r in rows:
    if not r['cam'] or not r['w']:
        miss[(r['cam'], r['w'], r['path'][:90])] += r['n']
        continue
    fps = r['fps_nom'] or snap(r['fps_meas'])
    k = (r['cam'], r['w'], r['h'], fps)
    s = np.asarray(r['sizes'])
    # drop uncompressed (YUY2/NV12) frames that slipped in
    nonjpeg = int((s >= r['w'] * r['h']).sum())
    if nonjpeg: print('drop', nonjpeg, 'frames >= W*H bytes (uncompressed/decoded) in', r['path'][-100:])
    s = s[s < r['w'] * r['h']]
    groups[k].append(s)
    srcs[k].append((int(s.max()) if len(s) else 0, r['path']))
print('unattributed frames:', sum(miss.values()))
for k, v in miss.most_common(12):
    print('  ', v, k)
tot = 0
out = []
for k in sorted(groups, key=lambda k: (k[0], k[1] * k[2], k[3] or 0)):
    s = np.concatenate(groups[k])
    if not len(s):
        continue
    tot += len(s)
    px = k[1] * k[2]
    row = dict(cam=k[0], w=k[1], h=k[2], fps=k[3], n=int(len(s)), files=len(groups[k]), max=int(s.max()),
               p999=float(np.percentile(s, 99.9)), p99=float(np.percentile(s, 99)), med=float(np.median(s)),
               bpp_max=s.max() / px, max_src=max(srcs[k])[1])
    out.append(row)
print('total frames', tot)
print(f"{'cam':9s} {'mode':>14s} {'n':>8s} {'max':>8s} {'p99.9':>8s} {'p99':>8s} {'med':>8s} {'bpp_max':>7s} {'bpp_med':>7s}")
for r in out:
    px = r['w'] * r['h']
    print(f"{r['cam']:9s} {str(r['w'])+'x'+str(r['h'])+'@'+str(r['fps']):>14s} {r['n']:8d} {r['max']:8d} {r['p999']:8.0f} {r['p99']:8.0f} {r['med']:8.0f} {r['bpp_max']:7.4f} {r['med']/px:7.4f}")
json.dump(out, open(os.path.join(HERE, 'agg.json'), 'w'), indent=1)
