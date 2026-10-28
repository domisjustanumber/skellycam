import sys, os, tempfile, numpy as np, cv2
img=np.random.randint(0,255,(48,64,1),np.uint8)
ok,j=cv2.imencode('.jpg',img); print("imencode mono ok:",ok, "decoded shape", cv2.imdecode(j,cv2.IMREAD_UNCHANGED).shape)
print("resize (48,64,1) ->", cv2.resize(img,(32,24)).shape)
d=tempfile.mkdtemp(); p=os.path.join(d,"m.mp4")
w=cv2.VideoWriter(p,cv2.VideoWriter.fourcc(*"mp4v"),30,(64,48))
print("writer opened", w.isOpened())
for _ in range(10): w.write(img)
w.release()
cap=cv2.VideoCapture(p); print("frames", cap.get(cv2.CAP_PROP_FRAME_COUNT)); ok,f=cap.read(); print("read ok",ok, None if f is None else f.shape)
try:
    import av
    av.VideoFrame.from_ndarray(img,format='bgr24'); print("pyav bgr24 mono accepted")
except ImportError: print("no av")
except Exception as e: print("pyav bgr24 mono rejected:", type(e).__name__, e)
img3=np.random.randint(0,255,(48,64,3),np.uint8)
p3=os.path.join(d,"c.mp4"); w=cv2.VideoWriter(p3,cv2.VideoWriter.fourcc(*"mp4v"),30,(64,48))
for _ in range(10): w.write(img3)
w.release(); cap=cv2.VideoCapture(p3); ok,f=cap.read(); print("color read", ok, f.shape)
