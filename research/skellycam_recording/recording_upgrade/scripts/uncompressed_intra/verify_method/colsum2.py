import sys, numpy as np, cv2
sys.path.insert(0, r"C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra")
import uintra_frames as uf
yuy, w, h = uf.load_yuy2("c930e_1080p_yuy2", 1)
Y, U, V = uf.yuyv_split(yuy[0]); U2 = np.repeat(U, 2, 1).astype(np.float32)-128; V2 = np.repeat(V, 2, 1).astype(np.float32)-128
def ws(rgb): s = cv2.resize(np.clip(np.rint(rgb),0,255).astype(np.uint8), (64,36), interpolation=cv2.INTER_LINEAR).astype(np.int64); return int((s[...,0]+3*s[...,1]+7*s[...,2]).sum())
for name,(kr,kb) in {"601":(0.299,0.114),"709":(0.2126,0.0722),"2020":(0.2627,0.0593),"240m":(0.212,0.087),"fcc":(0.30,0.11)}.items():
    kg=1-kr-kb; Yf=(Y.astype(np.float32)-16)*255/219; Uf=U2*255/224; Vf=V2*255/224
    r=Yf+2*(1-kr)*Vf; b=Yf+2*(1-kb)*Uf; g=(Yf-kr*r-kb*b)/kg
    print(name, ws(np.stack([r,g,b],-1)))
# GBR interpretation (Y=G,U=B,V=R) for 4:4:4 mislabel
print("gbr-as-is", ws(np.stack([V2+128, Y.astype(np.float32), U2+128], -1)))
