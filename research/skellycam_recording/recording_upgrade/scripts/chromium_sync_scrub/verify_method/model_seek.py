# Model of the F9 mechanism: target truncated to us, container pts rounded to us, show last frame with ts<=target.
# Compares predicted exact counts to measured seek_batch.json (video path). No timing.
import json, math, sys, ast
MAN = r"C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/clips/manifest.json"
RES = r"C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub/functional"
def u32(x): return x & 0xFFFFFFFF
def s32(x):
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x & 0x80000000 else x
def imul(a, b): return s32((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF))
def mulberry32(a):
    st = [a]
    def f():
        a = s32(st[0]); a = s32(a + 0x6D2B79F5); st[0] = a
        t = imul(a ^ (u32(a) >> 15), 1 | a)
        t = s32(t + imul(t ^ (u32(t) >> 7), 61 | t)) ^ t
        return (u32(t ^ (u32(t) >> 14))) / 4294967296
    return f
def lst(v): return v if isinstance(v, list) else ast.literal_eval(v)
man = json.load(open(MAN))['clips']
def predict(clip, mode, seq):
    c = man[clip]; pts = lst(c['pts_s']); fps = float(c['nominal_fps']); den = int(c['time_base'].split('/')[1])
    ticks = [round(p * den) for p in pts]
    ts = [(t * 1000000 + den // 2) // den for t in ticks]  # av_rescale_q round-near-inf (positive)
    out = []
    for k in seq:
        if mode == 'ui': t = k / fps
        elif mode == 'cfrmid': t = (k + 0.5) / fps
        elif mode == 'ptsexact': t = pts[k]
        else:
            nx = pts[k + 1] if k + 1 < len(pts) else pts[k] + 1 / fps; t = (pts[k] + nx) / 2
        T = math.trunc(t * 1e6)
        i = 0
        for j, x in enumerate(ts):
            if x <= T: i = j
            else: break
        out.append(i)
    return out
rows = []
for e in ['e35', 'e45']:
    d = json.load(open(f"{RES}/{e}/seek_batch.json"))
    for x in d['result']:
        cf = x['config']
        if cf['path'] != 'video': continue
        clip = cf['clip']; mode = cf['mode']; n = int(cf['n']); F = int(man[clip]['frames'])
        rnd = mulberry32(int(cf['seed'])); seq = [math.floor(rnd() * F) for _ in range(n)]
        wr = x['result'].get('wrong_rows', [])
        wk = sorted(r['k'] for r in wr)
        # sanity: wrong_rows k must be in seq
        assert all(k in seq for k in wk), (clip, mode)
        pr = predict(clip, mode, seq)
        pexact = sum(1 for k, p in zip(seq, pr) if p == k)
        meas = x['result']['summary']['exact']
        intra = 'intra' in clip
        rows.append((e, clip, mode, meas, pexact, intra))
for r in rows:
    flag = '' if r[3] == r[4] else '  <-- differs'
    print(f"{r[0]} {r[1]:28s} {r[2]:8s} measured {r[3]:3d} model {r[4]:3d}{' (intra: model is GOP rule)' if r[5] else ''}{flag}")
