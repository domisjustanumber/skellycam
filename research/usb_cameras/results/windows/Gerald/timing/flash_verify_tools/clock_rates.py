# Per-camera frame period measured by host arrival, SCR STC and PTS (ticks at the nominal device clock).
import sys,numpy as np
from pathlib import Path
sys.path.insert(0,r'C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/tools')
import analyze_frames as af
for f in sys.argv[1:]:
    rows=af.load(Path(f))[5:]
    if len(rows)<20: continue
    pts=af.unwrap(np.array([r['uvc_pts'] for r in rows]),32).astype(float)
    stc=af.unwrap(np.array([r['uvc_scr_stc'] for r in rows]),32).astype(float)
    host=np.array([r['host_arrival_ns'] for r in rows],float)
    n=np.arange(len(rows))
    hz=30e6 if np.median(np.diff(pts))<2e6 else 300e6
    Ph=np.polyfit(n,host,1)[0]/1e6
    Ps=np.polyfit(n,stc,1)[0]/hz*1e3
    Pp=np.median(np.diff(pts))/hz*1e3
    # STC rate vs host (ticks per host second)
    fs=np.polyfit(host/1e9,stc,1)[0]
    print(f'{Path(f).name[:17]} frames={len(rows)} period host={Ph:.4f}ms  stc={Ps:.4f}ms(@{hz/1e6:.0f}MHz nominal)  pts_median_step={Pp:.4f}ms  stc_rate_vs_host={fs/1e6:.6f}MHz  => pts step / true period = {(np.median(np.diff(pts))/fs*1e3)/Ph:.6f}')
