import sys,numpy as np
from pathlib import Path
sys.path.insert(0,r'C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/tools')
import analyze_frames as af
f=Path(sys.argv[1]); rows=af.load(f)[5:]
host=np.array([r['host_arrival_ns'] for r in rows],float)/1e6
stc=af.unwrap(np.array([r['uvc_scr_stc'] for r in rows]),32)/30e3 if 'pid_0843' in f.name else af.unwrap(np.array([r['uvc_scr_stc'] for r in rows]),32)/300e3
pts=af.unwrap(np.array([r['uvc_pts'] for r in rows]),32)/(30e3 if 'pid_0843' in f.name else 300e3)
dsof=af.unwrap(np.array([r['uvc_scr_sof'] for r in rows]),11).astype(float)
n=np.arange(len(rows))
def res(x):
    p=np.polyfit(n,x,1); return x-np.polyval(p,n), p[0]
rh,ph=res(host); rs,ps=res(stc); rp,pp=res(pts); rsof,psof=res(dsof)
print('slopes ms/frame host %.4f stc %.4f pts %.4f sof %.4f'%(ph,ps,pp,psof))
for a in range(0,len(n),60):
    b=a+60
    print(f'{a:4d}-{b:4d} host_res_min={rh[a:b].min():8.2f} stc_res={np.median(rs[a:b]):8.2f} pts_res={np.median(rp[a:b]):8.2f} sof_res={np.median(rsof[a:b]):8.2f} stc-host_min={np.min(stc[a:b]-host[a:b]-(stc[0]-host[0])):8.2f}')
