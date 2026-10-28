import json,sys,glob,os
short={'046d&pid_085c':'C922','046d&pid_0843':'C930e','4c4a&pid_4a55':'GEN','1532&pid_0e05':'KIYO'}
def nm(spec):
    for k,v in short.items():
        if k in spec.lower(): return v
    return spec
for f in sys.argv[1:]:
    d=json.load(open(f))
    print('=====',os.path.basename(f),d.get('utc_started'),'cpu',d.get('machine_cpu_pct_start'),d.get('machine_cpu_pct_end'),'stagger',d.get('settings'))
    for c in d['combos']:
        mf=c.get('mf') or {}
        alts={}
        for p in c.get('pipes_while_streaming') or []:
            key=(p.get('idVendor','')+'&pid_'+p.get('idProduct','')).lower()
            alts[short.get(key,key)]=[m.get('bAlternateSetting') for m in p.get('matched_alt_settings',[])]
        parts=[]
        for cam in mf.get('cameras',[]):
            n=nm(cam['spec'])
            ex=cam.get('exposure') or {}
            parts.append(f"{n}[{cam['spec'].split(':',1)[1]}] st={cam.get('streamed')} hr={cam.get('error_hr')} fs={cam.get('failed_stage')} fps={cam.get('steady_fps')} Bps={cam.get('steady_bytes_per_s')} exp={ex.get('set_ok')}/{ex.get('prev')}/{ex.get('prev_flags')} alt={alts.get(n)}")
        print(' ',c['label'],'exit',c.get('exit_code'))
        for p in parts: print('     ',p)
