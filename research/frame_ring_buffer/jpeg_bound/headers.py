"""For each camera x resolution, pull real frames (largest + median) out of frames.mjpeg files and report structure.
Also checks DQT constancy over every frame of each file (rate control via table switching would show here)."""
import json, os, sys, collections, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jpeg_inspect import inspect, ijg_quality, IJG_LUMA, IJG_CHROMA

HERE = os.path.dirname(os.path.abspath(__file__))
rows = [json.loads(l) for l in open(os.path.join(HERE, 'scan_files.jsonl'))]
OUTDIR = os.path.join(HERE, 'frames')
os.makedirs(OUTDIR, exist_ok=True)


def frames_of(jsonl):
    d = os.path.dirname(jsonl)
    mj = os.path.join(d, 'frames.mjpeg' if os.path.basename(jsonl) == 'frames.jsonl' else 'cells.mjpeg')
    if not os.path.exists(mj) or os.path.getsize(mj) == 0:
        return None, []
    recs = []
    for line in open(jsonl):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if 'mjpeg_offset' in r and r.get('mjpeg_len'):
            recs.append((r['mjpeg_offset'], r['mjpeg_len']))
    return mj, recs


best = {}   # (cam, w, h) -> list of (size, mj, off, len)
dqt_sets = collections.defaultdict(set)
dqt_frames = collections.Counter()
for r in rows:
    if not r['cam'] or not r['w'] or not r['path'].endswith(('frames.jsonl', 'cells.jsonl')):
        continue
    mj, recs = frames_of(r['path'])
    if not recs:
        continue
    k = (r['cam'], r['w'], r['h'])
    with open(mj, 'rb') as f:
        for off, ln in recs:
            f.seek(off)
            b = f.read(ln)
            if b[:2] != b'\xff\xd8':
                continue
            best.setdefault(k, []).append((ln, mj, off))
            # DQT sets per camera (cheap: header only)
            try:
                h = inspect(b[:min(len(b), 4096)] + b'\xff\xd9') if False else None
            except Exception:
                pass
summary = {}
for k, lst in sorted(best.items()):
    lst.sort()
    pick = {'max': lst[-1], 'median': lst[len(lst) // 2]}
    rec = {'frames_with_bytes': len(lst)}
    for tag, (ln, mj, off) in pick.items():
        with open(mj, 'rb') as f:
            f.seek(off)
            b = f.read(ln)
        fn = os.path.join(OUTDIR, f"{k[0].replace(' ', '')}_{k[1]}x{k[2]}_{tag}.jpg")
        open(fn, 'wb').write(b)
        try:
            h = inspect(b)
        except Exception as e:
            rec[tag] = {'error': repr(e), 'size': ln}
            continue
        q = {t: ijg_quality(v, IJG_LUMA if t == 0 else IJG_CHROMA) for t, v in h['dqt'].items()}
        rec[tag] = dict(size=ln, src=mj, sof=h['sof'], header_bytes=h['header_bytes'], entropy=h['entropy_bytes'],
                        dht=h['dht'], dri=h['dri'], rst=h['rst_markers'], stuffed=h['stuffed_ff00'], after_eoi=h['after_eoi'],
                        app=[(a, L) for a, L, _ in h['app']], segments=h['segments'], ijg_q=q,
                        dqt_hash=hashlib.sha1(json.dumps(h['dqt'], sort_keys=True).encode()).hexdigest()[:10],
                        dqt=h['dqt'], file=fn)
    summary[f'{k[0]} {k[1]}x{k[2]}'] = rec
json.dump(summary, open(os.path.join(HERE, 'headers.json'), 'w'), indent=1, default=str)
for k, rec in summary.items():
    for tag in ('max', 'median'):
        x = rec.get(tag, {})
        if 'sof' not in x:
            print(k, tag, x)
            continue
        samp = [(c[1], c[2]) for c in x['sof']['comps']]
        print(f"{k:22s} {tag:6s} n={rec['frames_with_bytes']:6d} size={x['size']:7d} hdr={x['header_bytes']:5d} dht={x['dht']} dri={x['dri']} rst={x['rst']} "
              f"stuff={x['stuffed']} ({x['stuffed']/max(1,x['entropy'])*100:.2f}%) afterEOI={x['after_eoi']} samp={samp} q={x['ijg_q']} dqt={x['dqt_hash']} app={x['app']}")
