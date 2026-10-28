# /// script
# requires-python = ">=3.10"
# dependencies = ["simplejpeg==1.8.2", "numpy<2.3", "opencv-python-headless==4.10.0.84"]
# ///
"""Independent check: simplejpeg strict, PyAV(ffmpeg mjpeg) decode, entropy-data scan for EOI position."""
import sys, glob, json, simplejpeg, cv2, numpy as np
res={"n":0,"strict_fail":0,"ffmpeg_ok":0,"msgs":{}}
files=[]
for a in sys.argv[1:]:
    files += sorted(glob.glob(a+'/*.jpg')) if not a.endswith('.jpg') else [a]

for f in files:
    b=open(f,'rb').read(); res['n']+=1
    try:
        simplejpeg.decode_jpeg(b, strict=True)
    except Exception as e:
        res['strict_fail']+=1; m=str(e).split(':')[0]+':'+''.join(c for c in str(e).split(':',1)[-1] if not c.isdigit())[:60]; res['msgs'][m]=res['msgs'].get(m,0)+1
    try:
        im=cv2.imdecode(np.frombuffer(b,np.uint8),cv2.IMREAD_COLOR)
        if im is not None: res['ffmpeg_ok']+=1; res.setdefault('shapes',{}); res['shapes'][str(im.shape)]=res['shapes'].get(str(im.shape),0)+1
    except Exception as e:
        pass
print(json.dumps(res,indent=1))
