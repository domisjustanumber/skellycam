import sys,json,cv2,numpy as np
from pathlib import Path
for fj in sorted(Path(sys.argv[1]).glob('*.frames.jsonl')):
    key=fj.name.split('.')[0]; mj=fj.with_name(key+'.mjpeg')
    if not mj.exists() or mj.stat().st_size==0: continue
    rows=[json.loads(l) for l in open(fj)]; data=mj.read_bytes()
    v=[]
    for r in rows[50::20]:
        im=cv2.imdecode(np.frombuffer(data,np.uint8,r['payload_bytes'],r['mjpeg_offset']),cv2.IMREAD_REDUCED_GRAYSCALE_8)
        v.append((im.mean(), np.percentile(im,99)))
    v=np.array(v); print(key[:17],'frame mean min/med/max %.1f %.1f %.1f  p99 med %.1f'%(v[:,0].min(),np.median(v[:,0]),v[:,0].max(),np.median(v[:,1])))
