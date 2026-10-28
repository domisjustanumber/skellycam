import json,sys,hashlib
def raws(p):
    d=json.load(open(p,encoding='utf-8'))
    found={}
    def walk(o):
        if isinstance(o,dict):
            r=o.get('raw_hex')
            if isinstance(r,dict) and 'device' in r:
                dv=bytes.fromhex(r['device']); vp=f"{dv[9]:02x}{dv[8]:02x}:{dv[11]:02x}{dv[10]:02x}"
                found[vp]={k:hashlib.sha1(str(v).encode()).hexdigest()[:10] for k,v in r.items()}
            for v in o.values(): walk(v)
        elif isinstance(o,list):
            for v in o: walk(v)
    walk(d); return found
for p in sys.argv[1:]:
    print(p.split('/')[-3:], json.dumps(raws(p), sort_keys=True))
