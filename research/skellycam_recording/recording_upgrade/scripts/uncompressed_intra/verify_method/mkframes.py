import sys
from pathlib import Path
sys.path.insert(0, r"C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra")
import uintra_frames as uf
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
yuy, w, h = uf.load_yuy2("c930e_1080p_yuy2", 2)
for key in ("bayer_rggb16le", "bayer16_quad", "bayer_rggb8", "yuyv422"):
    for nz in (True, False):
        try:
            planes, fmt, fw, fh = uf.derive(key, yuy[0], w, h, idx=0, noise=nz) if key != "yuyv422" else uf.derive(key, yuy[0], w, h, idx=0)
        except TypeError as e:
            planes, fmt, fw, fh = uf.derive(key, yuy[0], w, h, idx=0); nz = "na"
        p = out / f"{key}_noise{nz}.raw"
        p.write_bytes(b"".join(pl.tobytes() for pl in planes))
        print(p.name, fmt, fw, fh)
        if key == "yuyv422": break
