# Per-second temporal std of the flash ROI (flash_analyze.roi_signal): shows when the flash was actually on screen.
import sys,json,numpy as np
from pathlib import Path
sys.path.insert(0,r'C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/timing/scripts')
import flash_analyze as fa
for fj in sorted(Path(sys.argv[1]).glob('*.frames.jsonl')):
    key=fj.name.split('.')[0]; mj=fj.with_name(key+'.mjpeg')
    rows=fa.af.load(fj)[5:]
    if len(rows)<20: continue
    y,info=fa.roi_signal(rows,mj)
    s=[np.std(y[i:i+30]) for i in range(0,len(y),30)]
    print(key[:17],'roi',info['roi_rows'],info['roi_cols'],'per-second ROI std:',' '.join(f'{v:.0f}' for v in s))
