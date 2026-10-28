import sys,json,cv2,numpy as np
from pathlib import Path
cap=Path(sys.argv[1]); out=Path(sys.argv[2]); out.mkdir(parents=True,exist_ok=True)
for fj in sorted(cap.glob('*.frames.jsonl')):
    key=fj.name.split('.')[0]; mj=fj.with_name(key+'.mjpeg')
    if not mj.exists() or mj.stat().st_size==0: continue
    rows=[json.loads(l) for l in open(fj)]; data=mj.read_bytes()
    ims=[]
    for k in (100,101,102,103):
        r=rows[k]; im=cv2.imdecode(np.frombuffer(data,np.uint8,r['payload_bytes'],r['mjpeg_offset']),cv2.IMREAD_COLOR)
        ims.append(cv2.resize(im,(640,360)))
    grid=np.vstack([np.hstack(ims[:2]),np.hstack(ims[2:])])
    cv2.imwrite(str(out/f'{key[:17]}_f100-103.jpg'),grid)
    print(out/f'{key[:17]}_f100-103.jpg')
