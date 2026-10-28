import json,sys
for p in sys.argv[1:]:
    d=json.load(open(p,encoding='utf-8'))
    apis=d['apis']
    mf=apis.get('media_foundation',{}); ds=apis.get('directshow',{})
    def lst(x):
        devs=x.get('devices',x) if isinstance(x,dict) else x
        return [(e.get('index'),(e.get('symbolic_link') or e.get('device_path') or '')[12:33]) for e in devs] if isinstance(devs,list) else str(type(devs))
    print(p.split('/')[-3:]); print(' MF',len(mf.get('devices',[])) if isinstance(mf,dict) else '?', lst(mf)); print(' DS',len(ds.get('devices',[])) if isinstance(ds,dict) else '?', [t for t in lst(ds) if 'vid' in t[1].lower()])
    print(' mapping', json.dumps({k:(v.get('mf_index'),v.get('dshow_index')) for k,v in (d.get('mapping') or {}).items()} if isinstance(d.get('mapping'),dict) else d.get('mapping'))[:600])
