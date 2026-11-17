"""Per camera x resolution envelope (all fps pooled), scaling fit, and evaluation of candidate estimators."""
import json, os, collections, math
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
rows = [json.loads(l) for l in open(os.path.join(HERE, 'scan_files.jsonl'))]
env = collections.defaultdict(list)
for r in rows:
    if not r['cam'] or not r['w'] or r['w'] < 100 or not r['h'] or r['h'] < 50:
        continue
    s = np.asarray(r['sizes'])
    s = s[s < r['w'] * r['h']]          # uncompressed/decoded stragglers
    if len(s):
        env[(r['cam'], r['w'], r['h'])].append(s)
E = []
for (cam, w, h), L in env.items():
    s = np.concatenate(L)
    E.append(dict(cam=cam, w=w, h=h, px=w * h, n=len(s), max=int(s.max()), p999=float(np.percentile(s, 99.9)),
                  p99=float(np.percentile(s, 99)), med=float(np.median(s)), all=s))
E.sort(key=lambda e: (e['cam'], e['px']))
print(f"{'cam':9s} {'res':>10s} {'frames':>7s} {'max':>8s} {'p99.9':>8s} {'p99':>8s} {'median':>8s} {'max B/px':>8s} {'(max-hdr)/px':>12s}")
HDR = {'C922': 702, 'C930e': 702, 'Kiyo Pro': 640, 'generic': 624}
for e in E:
    print(f"{e['cam']:9s} {str(e['w'])+'x'+str(e['h']):>10s} {e['n']:7d} {e['max']:8d} {e['p999']:8.0f} {e['p99']:8.0f} {e['med']:8.0f} {e['max']/e['px']:8.3f} {(e['max']-HDR[e['cam']])/e['px']:12.3f}")
print('total frames attributed:', sum(e['n'] for e in E))

# scaling fit per camera: log(max) vs log(px), and linear a + b px (least squares on the per-resolution maxima)
print('\n# scaling of per-resolution max with pixel count')
for cam in sorted({e['cam'] for e in E}):
    pts = [(e['px'], e['max']) for e in E if e['cam'] == cam and e['n'] >= 20]
    if len(pts) < 3:
        continue
    x = np.array([p[0] for p in pts], float)
    y = np.array([p[1] for p in pts], float)
    slope = np.polyfit(np.log(x), np.log(y), 1)[0]
    b, a = np.polyfit(x, y, 1)
    print(f'{cam:9s} modes={len(pts):3d} log-log slope={slope:.3f}  linear fit max ~ {a:8.0f} + {b:.4f}*px   max (max-702)/px={max((yy - 702) / xx for xx, yy in pts):.3f}')


def page(n):
    return int(math.ceil(n / 4096) * 4096)


def tjbufsize(w, h, samp):   # libjpeg-turbo turbojpeg.c tj3JPEGBufSize / tjBufSize (no ICC)
    mcuw, mcuh = {'444': (8, 8), '422': (16, 8), '420': (16, 16)}[samp]
    chromasf = 4 * 64 // (mcuw * mcuh)
    return ((w + mcuw - 1) // mcuw * mcuw) * ((h + mcuh - 1) // mcuh * mcuh) * (2 + chromasf) + 2048


RULES = {
    'A: 2 KiB + 0.5 B/px (recommended)': lambda w, h: 2048 + 0.5 * w * h,
    'B: 1 KiB + 0.375 B/px': lambda w, h: 1024 + 0.375 * w * h,
    'C: 1 KiB + 0.30 B/px (fit to max observed)': lambda w, h: 1024 + 0.30 * w * h,
    'W*H*2 (camera-advertised, rejected)': lambda w, h: 2 * w * h,
    'tjBufSize 4:2:2 (libjpeg-turbo guarantee)': lambda w, h: tjbufsize(w, h, '422'),
}
print('\n# candidate estimators vs all frames (est = rule; slot = page(2*est))')
for name, f in RULES.items():
    over_est = over_slot = 0
    worst = (9e9, None)
    worst_slot = (9e9, None)
    for e in E:
        est = f(e['w'], e['h'])
        slot = page(2 * est)
        over_est += int((e['all'] > est).sum())
        over_slot += int((e['all'] > slot).sum())
        if est / e['max'] < worst[0]:
            worst = (est / e['max'], f"{e['cam']} {e['w']}x{e['h']}")
        if slot / e['max'] < worst_slot[0]:
            worst_slot = (slot / e['max'], f"{e['cam']} {e['w']}x{e['h']}")
    print(f'{name:45s} frames>est={over_est:6d} frames>slot={over_slot:3d}  min est/max={worst[0]:.2f} ({worst[1]})  min slot/max={worst_slot[0]:.2f} ({worst_slot[1]})')

# transport: high-speed isochronous ceiling per nominal frame period, vs data
print('\n# HS isochronous ceiling 3072 B/uframe * 8000 / fps vs largest frames (HS cameras only)')
for fps in (30, 60):
    cap = 3072 * 8000 / fps
    print(f'  {fps} fps: {cap:,.0f} B/frame')
json.dump([{k: v for k, v in e.items() if k != 'all'} for e in E], open(os.path.join(HERE, 'envelope.json'), 'w'), indent=1)
