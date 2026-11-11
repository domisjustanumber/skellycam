import sys, numpy as np, cv2
sys.path.insert(0, r"C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra")
import uintra_frames as uf
yuy, w, h = uf.load_yuy2("c930e_1080p_yuy2", 8)
def conv(y, u, v, mat, full):
    y = y.astype(np.float32); u = u.astype(np.float32) - 128; v = v.astype(np.float32) - 128
    if full: ys, cs = 1.0, 1.0; y0 = 0
    else: ys, cs = 255/219, 255/224; y0 = 16
    kr, kb = {"601": (0.299, 0.114), "709": (0.2126, 0.0722)}[mat]
    kg = 1 - kr - kb
    Y = (y - y0) * ys; U = u * cs; V = v * cs
    r = Y + 2*(1-kr)*V; b = Y + 2*(1-kb)*U; g = (Y - kr*r - kb*b)/kg
    return np.clip(np.rint(np.stack([r, g, b], -1)), 0, 255).astype(np.uint8)
def wsum(rgb, interp):
    s = cv2.resize(rgb, (64, 36), interpolation=interp).astype(np.int64)
    return int((s[..., 0] + 3*s[..., 1] + 7*s[..., 2]).sum())
for fi in (0, 5):
    Y, U, V = uf.yuyv_split(yuy[fi])
    U2 = np.repeat(U, 2, 1); V2 = np.repeat(V, 2, 1)
    u4 = ((U[0::2].astype(np.uint16) + U[1::2] + 1) >> 1).astype(np.uint8); v4 = ((V[0::2].astype(np.uint16) + V[1::2] + 1) >> 1).astype(np.uint8)
    U4 = np.repeat(np.repeat(u4, 2, 0), 2, 1); V4 = np.repeat(np.repeat(v4, 2, 0), 2, 1)
    for chroma, (uu, vv) in (("422", (U2, V2)), ("420", (U4, V4))):
        for mat in ("601", "709"):
            for full in (False, True):
                rgb = conv(Y, uu, vv, mat, full)
                print(f"frame{fi} {chroma} BT{mat} {'full' if full else 'limited'}: area={wsum(rgb, cv2.INTER_AREA)} linear={wsum(rgb, cv2.INTER_LINEAR)}")
