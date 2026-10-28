import json,sys,collections,glob,os
import numpy as np
for d in sys.argv[1:]:
    for fn in sorted(glob.glob(os.path.join(d,'frames_*.jsonl'))):
        fr=[json.loads(l) for l in open(fn) if l.strip()][5:]
        if len(fr)<10: continue
        out=[]
        for key in ('host_arrival_ns','os_timestamp_ns'):
            v=np.array([x[key] for x in fr if x.get(key) is not None],dtype=np.int64)
            ph=(v%16_000_000)/1e6
            # circular spread
            ang=ph/16*2*np.pi; R=abs(np.mean(np.exp(1j*ang)))
            circ_sd=np.sqrt(-2*np.log(R))*16/(2*np.pi) if R<1 else 0
            modal=collections.Counter((ph//1).astype(int).tolist()).most_common(1)[0][1]/len(ph)
            # drift of phase: slope of unwrapped phase
            out.append(f"{key[:7]} modal1ms={modal:.2f} circSD={circ_sd:.2f}ms")
        a=np.array([x['host_arrival_ns'] for x in fr]); o=np.array([x['os_timestamp_ns'] for x in fr])
        r=(a-o)/1e6
        print(os.path.basename(d)[-40:], os.path.basename(fn), ' | '.join(out), f"arr-os p50={np.median(r):.3f} p95={np.percentile(r,95):.3f} max={r.max():.3f}")
