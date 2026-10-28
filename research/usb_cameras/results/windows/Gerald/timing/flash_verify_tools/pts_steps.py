# Locate C930e/C922 PTS discontinuities: per-frame PTS step, STC-PTS, host-arrival step.
import json,sys,numpy as np
from pathlib import Path
sys.path.insert(0,r'C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/tools')
import analyze_frames as af
for f in sys.argv[1:]:
    rows=af.load(Path(f))[5:]
    pts=np.unwrap(np.array([r['uvc_pts'] for r in rows],float),period=2**32)
    stc=np.unwrap(np.array([r['uvc_scr_stc'] for r in rows],float),period=2**32)
    host=np.array([r['host_arrival_ns'] for r in rows],float)
    seq=np.array([r['seq'] for r in rows])
    dp=np.diff(pts); med=np.median(dp)
    hz = 30e6 if med<2e6 else 300e6
    big=np.flatnonzero(np.abs(dp-med)>0.2*med)
    lat=(stc-pts)/hz*1e3
    print(f.split('/')[-1][:17],'n',len(rows),'median dPTS',med,'clk',hz,'seq gaps',int(np.sum(np.diff(seq)!=1)))
    for i in big[:10]:
        print(f'   step at idx {i}: dPTS={dp[i]:.0f} ({dp[i]/med:.2f}x) dHost={np.diff(host)[i]/1e6:.2f}ms stc-pts before {lat[max(0,i-3):i+1].round(2)} after {lat[i+1:i+4].round(2)}')
    # segments of stc-pts
    print('   stc-pts quartiles by segment:', [np.round(np.median(lat[a:b]),2) for a,b in zip([0]+list(big+1),list(big+1)+[len(lat)])])
