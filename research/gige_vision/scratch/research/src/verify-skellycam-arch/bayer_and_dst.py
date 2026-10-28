import sys, time, numpy as np, cv2
sys.path.insert(0, sys.argv[1])
print("cv2", cv2.__version__, "numpy", np.__version__)
# RGGB mosaic of a pure-red scene: R at (0,0)
H,W=8,8
m=np.zeros((H,W),np.uint8); m[0::2,0::2]=255
for name in ["COLOR_BayerRG2BGR","COLOR_BayerBG2BGR","COLOR_BayerGR2BGR","COLOR_BayerGB2BGR"]:
    out=cv2.cvtColor(m,getattr(cv2,name)); print(name, "center BGR", tuple(int(x) for x in out[4,4]))
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.types.frame_dtype_factories import create_frame_dtype
for (w,h) in [(1280,720),(1920,1200),(2448,2048),(4096,3000)]:
    c=CameraConfig(resolution=ImageResolution(width=w,height=h))
    dt=create_frame_dtype(c); print((w,h),"itemsize",dt.itemsize,"slots",(1024**3)//dt.itemsize)
c=CameraConfig(resolution=ImageResolution(width=2448,height=2048))
rec=np.recarray(1,dtype=create_frame_dtype(c))
raw=np.random.randint(0,255,(2048,2448),np.uint8)
view=rec.image[0]
ret=cv2.cvtColor(raw,cv2.COLOR_BayerBG2BGR,dst=view)
print("dst shares memory with recarray:", np.shares_memory(ret, rec), "ret is view:", ret is view)
ts=[]
for _ in range(50):
    t=time.perf_counter(); cv2.cvtColor(raw,cv2.COLOR_BayerBG2BGR,dst=view); ts.append(time.perf_counter()-t)
print("median ms", np.median(ts)*1e3)
c1=CameraConfig(color_channels=1)
print("mono dtype image shape", create_frame_dtype(c1)['image'].shape, "image_shape", c1.image_shape)
