import json,sys,glob
import numpy as np
for f in sys.argv[1:]:
    seq=[];stc=[];pts=[]
    for l in open(f):
        d=json.loads(l)
        mi=d.get('meta_items') or []
        if not mi: continue
        t=mi[0]['_top']; seq.append(d['seq']); stc.append(t['uvc_scr_stc']); pts.append(t['uvc_pts'])
    if len(seq)<10: print(f, 'no meta'); continue
    seq=np.array(seq,float); stc=np.unwrap(np.array(stc,float),period=2**32) if False else np.array(stc,float)
    # unwrap 32-bit
    s=np.array(stc); d=np.diff(s); d[d<-2**31]+=2**32; s=np.concatenate([[0],np.cumsum(d)])
    p=np.array(pts,float); dp=np.diff(p); dp[dp<-2**31]+=2**32; p=np.concatenate([[0],np.cumsum(dp)])
    a=np.polyfit(seq,s,1)[0]; b=np.polyfit(seq,p,1)[0]
    sm=(s-p+ (stc[0]-pts[0]))/30e6*1e3  # ms at 30MHz? 
    print('/'.join(f.split('/')[-4:-2])[-70:], f.split('/')[-1][:18], 'n',len(seq),'stc/frame %.0f'%a,'pts/frame %.0f'%b, 'stc-pts ms min %.1f max %.1f'%(sm.min(),sm.max()))
