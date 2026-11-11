# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Functional only (no timing): does hevc_qsv / h264_qsv open and encode all-intra with low_power=1 and preset=veryfast?"""
import json, sys
import av, numpy as np
from av.video.frame import VideoFrame
out = {"pyav": av.__version__, "libavcodec": av.library_versions.get("libavcodec"), "cases": []}
w, h = 1920, 1080
rng = np.random.default_rng(0)
base = rng.integers(16, 235, size=(h * 3 // 2, w), dtype=np.uint8)
for enc_name in ["hevc_qsv"]:
    for opts in [{}, {"low_power": "1"}, {"preset": "veryfast"}, {"low_power": "1", "preset": "veryfast"}]:
        o = {"flags": "+qscale", "global_quality": "1534", "i_qfactor": "1", "i_qoffset": "0", **opts}
        rec = {"encoder": enc_name, "options": o}
        try:
            cc = av.CodecContext.create(enc_name, "w")
            cc.width, cc.height, cc.pix_fmt = w, h, "nv12"
            from fractions import Fraction
            cc.time_base, cc.framerate = Fraction(1, 30), Fraction(30, 1)
            cc.gop_size = 1
            cc.max_b_frames = 0
            cc.options = {k: str(v) for k, v in o.items()}
            cc.open()
            pk = []
            for i in range(8):
                f = VideoFrame.from_numpy_buffer(np.roll(base, i * 7, axis=1), format="nv12")
                f.pts = i
                pk += list(cc.encode(f))
            pk += list(cc.encode(None))
            rec.update(ok=True, packets=len(pk), keyframes=sum(1 for p in pk if p.is_keyframe), bytes=sum(p.size for p in pk))
        except Exception as ex:
            rec.update(ok=False, error=f"{type(ex).__name__}: {ex}"[:300])
        out["cases"].append(rec)
print(json.dumps(out, indent=1))
