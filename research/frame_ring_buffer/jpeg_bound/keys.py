import json, os, collections, sys
roots=[r'C:\Users\Dom\Documents\skellycam-raw', r'C:\Users\Dom\GitHub\freemocap\skellycam\research']
ks=collections.Counter(); ex={}
for root in roots:
  for dp,dn,fn in os.walk(root):
    for f in fn:
      if f.endswith('.jsonl'):
        p=os.path.join(dp,f)
        try:
          with open(p) as fh: line=fh.readline()
          k=tuple(sorted(json.loads(line).keys()))
        except Exception as e: k=('ERR',)
        ks[(f if f in('frames.jsonl','cells.jsonl','probes.jsonl') else 'other',k)]+=1; ex.setdefault((f if f in('frames.jsonl','cells.jsonl','probes.jsonl') else 'other',k),p)
for (f,k),n in ks.most_common(): print(n,f,k[:30], ex[(f,k)][-110:])
