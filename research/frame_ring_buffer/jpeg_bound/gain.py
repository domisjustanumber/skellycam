import json, os, glob, collections, re
R = r'C:\Users\Dom\Documents\skellycam-raw'
t = collections.defaultdict(list)
for p in glob.glob(os.path.join(R, '**', 'W-GAIN', '*', '*', 'cells.jsonl'), recursive=True):
    cam = os.path.basename(os.path.dirname(os.path.dirname(p)))
    mode = os.path.basename(os.path.dirname(p))
    run = p.split(os.sep)[-5] if 'suite' in p else p.split(os.sep)[-5]
    for line in open(p):
        r = json.loads(line)
        if r.get('bytes'):
            t[(cam[:14], mode.split('_e')[0], r['gain'])].append(r['bytes'])
for k in sorted(t):
    s = t[k]
    print(k, 'n=%d max=%d med=%d' % (len(s), max(s), sorted(s)[len(s)//2]))
