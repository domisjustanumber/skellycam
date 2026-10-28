import json,sys
def load(p):
    d=json.load(open(p,encoding='utf-8'))
    out={}
    for c in d.get('cameras',d if isinstance(d,list) else []):
        key=None; raw=None
        s=json.dumps(c)
        # find raw descriptors
        def walk(o,path=''):
            if isinstance(o,dict):
                if 'raw' in o and isinstance(o['raw'],dict) and 'device' in o['raw']:
                    yield o['raw']
                for k,v in o.items(): yield from walk(v,path+'/'+k)
            elif isinstance(o,list):
                for v in o: yield from walk(v,path)
        raws=list(walk(c))
        vp=None
        for r in raws:
            dv=bytes.fromhex(r['device']); vp=f"{dv[9]:02x}{dv[8]:02x}:{dv[11]:02x}{dv[10]:02x}"
            out[vp]=r
    return out
a=load(sys.argv[1]); b=load(sys.argv[2]); c=load(sys.argv[3])
for vp in sorted(set(a)|set(b)|set(c)):
    ra,rb,rc=a.get(vp),b.get(vp),c.get(vp)
    print(vp, 'keys', sorted(rb.keys()) if rb else None,
      'verify==rerun:', {k:(ra or {}).get(k)==(rb or {}).get(k) for k in (rb or {}) },
      'verify==phase1:', {k:(rc or {}).get(k)==(rb or {}).get(k) for k in (rb or {}) if k in (rc or {})})
