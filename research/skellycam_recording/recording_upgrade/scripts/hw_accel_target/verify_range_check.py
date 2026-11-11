# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Functional re-check for VERIFY_method.md (no timing, < 1 min, Intel QSV only).

Question: what Y range ends up in the JPEG when mjpeg_qsv is fed the NV12 that the hw_accel_target bench builds
for non-yuvj encoders (bench_encode_stream.py:112 for yuy2 sources, :120-124 with dst_color_range=1 for MJPEG sources)?
Input: a synthetic full-range luma ramp 0..255 in a yuvj420p frame (stands in for a decoded camera JPEG).
Output: JSON on stdout (Y min/max fed, Y min/max after decoding the JPEG with FFmpeg mjpeg).
"""
import json
from fractions import Fraction

import av
import numpy as np

W, H = 1280, 720
y = np.tile(np.linspace(0, 255, W).round().astype(np.uint8), (H, 1))
f = av.VideoFrame(W, H, "yuvj420p")
f.planes[0].update(y.tobytes())
f.planes[1].update(np.full((H // 2, W // 2), 128, np.uint8).tobytes())
f.planes[2].update(np.full((H // 2, W // 2), 128, np.uint8).tobytes())
out = {"av": av.__version__, "input": "yuvj420p ramp Y 0..255, 1280x720"}
for label, kw in (("reformat_nv12_dst_color_range_1 (bench MJPEG-source path)", {"dst_color_range": 1}),
                  ("reformat_nv12_no_range_arg", {})):
    g = f.reformat(format="nv12", **kw)
    gy = np.frombuffer(bytes(g.planes[0]), np.uint8).reshape(H, -1)[:, :W]
    rec = {"fed_Y_min": int(gy.min()), "fed_Y_max": int(gy.max())}
    try:
        cc = av.CodecContext.create("mjpeg_qsv", "w")
        cc.width, cc.height, cc.pix_fmt = W, H, "nv12"
        cc.time_base = Fraction(1, 30)
        cc.open()
        pk = list(cc.encode(g)) + list(cc.encode(None))
        d = av.CodecContext.create("mjpeg", "r")
        fr = list(d.decode(av.Packet(bytes(pk[0]))))[0]
        dy = np.frombuffer(bytes(fr.planes[0]), np.uint8).reshape(H, -1)[:, :W]
        rec["mjpeg_qsv_jpeg"] = {"decoded_fmt": fr.format.name, "decoded_Y_min": int(dy.min()),
                                 "decoded_Y_max": int(dy.max())}
    except Exception as e:  # noqa: BLE001
        rec["mjpeg_qsv_jpeg"] = {"error": repr(e)[:300]}
    out[label] = rec
print(json.dumps(out, indent=1))
