import json, collections, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
rows = [json.loads(l) for l in open(os.path.join(HERE, 'scan_files.jsonl'))]
A = os.path.join(r'C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald', '')
B = os.path.join(r'C:\Users\Dom\Documents\skellycam-raw', '')
pat = sys.argv[1] if len(sys.argv) > 1 else None
miss = collections.Counter()
for r in rows:
    if pat is None and (not r['cam'] or not r['w']) or pat and pat in json.dumps([r['cam'], r['w'], r['h'], r['fps_nom']]):
        miss[(r['cam'], r['w'], r['h'], r['fps_nom'], round(r['fps_meas'] or 0, 1), r['path'].replace(A, 'R:').replace(B, 'RAW:'), max(r['sizes']))] += r['n']
for k, v in sorted(miss.items(), key=lambda kv: -kv[0][-1])[:int(sys.argv[2]) if len(sys.argv) > 2 else 45]:
    print(v, k)
print(len(miss))
