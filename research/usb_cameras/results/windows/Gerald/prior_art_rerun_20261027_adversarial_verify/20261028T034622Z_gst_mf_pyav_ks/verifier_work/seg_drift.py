import json,sys
import numpy as np
for fn in sys.argv[1:]:
    fr=[json.loads(l) for l in open(fn) if l.strip()][5:]
    a=np.array([x['host_arrival_ns'] for x in fr],dtype=np.int64); o=np.array([x['os_timestamp_ns'] for x in fr],dtype=np.int64)
    d=np.diff(o)//100
    steps=[i for i,v in enumerate(d) if abs(v-333333)>100]
    off=(a-o)/1e6; t=(a-a[0])/1e9
    print(fn.split('Gerald/')[-1], 'n',len(fr),'steps(idx,delta)',[(i,int(d[i])) for i in steps][:12])
    # segments split at big steps (>1ms off nominal)
    big=[i+1 for i,v in enumerate(d) if abs(v-333333)>10000]
    bounds=[0]+big+[len(fr)]
    for s,e in zip(bounds[:-1],bounds[1:]):
        if e-s>10:
            sl,_=np.polyfit(t[s:e],off[s:e],1); print('   seg',s,e,'drift ms/s %.3f'%sl,'median off %.2f'%np.median(off[s:e]))
    print('   whole drift %.3f'%np.polyfit(t,off,1)[0], 'arrival fps %.4f'%((len(a)-1)/((a[-1]-a[0])/1e9)), 'pts fps %.4f'%((len(o)-1)/((o[-1]-o[0])/1e9)))
