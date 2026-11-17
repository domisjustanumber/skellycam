"""Census of quantization tables over every stored frame: does any camera switch tables (rate control)?"""
import json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jpeg_inspect import inspect, ijg_quality, IJG_LUMA, IJG_CHROMA
HERE = os.path.dirname(os.path.abspath(__file__))
rows = [json.loads(l) for l in open(os.path.join(HERE, 'scan_files.jsonl'))]
tab = collections.defaultdict(lambda: collections.defaultdict(list))  # (cam,res) -> qkey -> sizes
qcache = {}
for r in rows:
    if not r['cam'] or not r['w'] or not r['path'].endswith(('frames.jsonl', 'cells.jsonl')):
        continue
    d = os.path.dirname(r['path'])
    mj = os.path.join(d, 'frames.mjpeg' if r['path'].endswith('frames.jsonl') else 'cells.mjpeg')
    if not os.path.exists(mj) or os.path.getsize(mj) == 0:
        continue
    with open(mj, 'rb') as f:
        for line in open(r['path']):
            try:
                x = json.loads(line)
            except Exception:
                continue
            if 'mjpeg_offset' not in x or not x.get('mjpeg_len'):
                continue
            f.seek(x['mjpeg_offset'])
            b = f.read(min(x['mjpeg_len'], 1200))
            if b[:2] != b'\xff\xd8':
                continue
            try:
                h = inspect(b + b'\xff\xd9')
            except Exception:
                continue
            key = json.dumps(h['dqt'], sort_keys=True)
            if key not in qcache:
                qcache[key] = tuple(ijg_quality(v, IJG_LUMA if t == '0' or t == 0 else IJG_CHROMA)[0] for t, v in sorted(h['dqt'].items()))
            sw = h['sof']['W'] if h['sof'] else r['w']
            sh = h['sof']['H'] if h['sof'] else r['h']
            tab[(r['cam'], f'{sw}x{sh}')][qcache[key]].append(x['mjpeg_len'])
out = {}
for k in sorted(tab):
    for q, s in sorted(tab[k].items(), key=lambda kv: -len(kv[1])):
        print(f'{k[0]:9s} {k[1]:10s} q={q} frames={len(s):6d} size min={min(s):7d} med={sorted(s)[len(s)//2]:7d} max={max(s):7d}')
        out.setdefault(f'{k[0]} {k[1]}', {})[str(q)] = dict(n=len(s), min=min(s), max=max(s))
json.dump(out, open(os.path.join(HERE, 'dqt_census.json'), 'w'), indent=1)
