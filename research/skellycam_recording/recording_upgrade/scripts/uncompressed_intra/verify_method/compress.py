import sys, numpy as np, av
from fractions import Fraction
from pathlib import Path
sys.path.insert(0, r"C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra")
import uintra_frames as uf
MED = Path(r"C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/verify_method")
def ffv1_size(frames422, w, h):
    out = MED / "c.mkv"
    tot = n = 0
    with av.open(str(out), "w") as oc:
        st = oc.add_stream("ffv1", rate=30, options={"level": "3", "slices": "24", "slicecrc": "1"})
        st.width, st.height, st.pix_fmt = w, h, "yuv422p"; st.codec_context.gop_size = 1
        for i, pl in enumerate(frames422):
            fr = uf.make_frame(pl, "yuv422p", w, h); fr.pts = i; fr.time_base = Fraction(1, 30)
            for p in st.encode(fr): tot += p.size; n += 1; oc.mux(p)
        for p in st.encode(None): tot += p.size; n += 1; oc.mux(p)
    out.unlink()
    return tot / n / 1000
def stats(frames422):
    y = np.stack([f[0] for f in frames422]).astype(np.float32)
    # high-frequency energy: mean abs horizontal Laplacian of Y
    lap = np.abs(2*y[:, :, 1:-1] - y[:, :, :-2] - y[:, :, 2:]).mean()
    return round(float(y.mean()), 1), round(float(lap), 2)
for s in ("c930e_1080p_yuy2", "c922_1080p_yuy2"):
    yuy, w, h = uf.load_yuy2(s, 8)
    fr = [list(uf.yuyv_split(f)) for f in yuy]
    print(s, "real YUY2", w, h, "FFV1 KB/f", round(ffv1_size(fr, w, h), 1), "Ymean,|lapY|", stats(fr))
for s in ("c930e_1080p", "c922_1080p", "c930e_720p_flash", "c922_720p_flash"):
    yuy, w, h = uf.load_jpeg_as_yuy2(s, 8)
    fr = [list(uf.yuyv_split(f)) for f in yuy]
    print(s, "JPEG->YUY2", w, h, "FFV1 KB/f", round(ffv1_size(fr, w, h), 1), "Ymean,|lapY|", stats(fr))
