# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Verifier (method): PyAV 19.0.2 re-checks of settings the draft took from the ffmpeg CLI only. FUNCTIONAL, no timing.
1) h264_nvenc gop_size=1, max_b_frames=0 (CLI: rejected).
2) h264_d3d12va (HWAccel d3d12va) gop15 with max_b_frames left at the PyAV default (CLI: failed with default B-frames).
3) h264_d3d12va intra into .mkv (CLI: header write failed; PyAV untested).
Each writes 16 frames from the 1080p NV12 input; output probed by PyAV decode (frame count, key flags, pict types).
"""
import json
import sys
from pathlib import Path

import av
import av.logging
import numpy as np
from av.codec.hwaccel import HWAccel

G = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode")
OUT = G / "verify_method"
OUT.mkdir(exist_ok=True)
W, H = 1920, 1080
raw = (G / "inputs/nv12_1080p.yuv").read_bytes()
fs = W * H * 3 // 2
FR = [np.frombuffer(raw[i * fs:(i + 1) * fs], np.uint8).reshape(H * 3 // 2, W) for i in range(8)]
CASES = [
    ("nvenc_gop1_bf0", "h264_nvenc", {"preset": "p4"}, None, 1, 0, "mkv"),
    ("d3d12_gop15_default_bf", "h264_d3d12va", {}, "d3d12va", 15, None, "mp4"),
    ("d3d12_intra_mkv", "h264_d3d12va", {}, "d3d12va", 1, 0, "mkv"),
]
res = {"pyav": av.__version__, "cases": []}
for label, name, opts, hw, gop, bf, ext in CASES:
    dst = OUT / f"{label}.{ext}"
    rec = {"case": label}
    av.logging.set_level(av.logging.VERBOSE)
    with av.logging.Capture() as logs:
        try:
            with av.open(str(dst), "w") as c:
                kw = {"hwaccel": HWAccel(hw)} if hw else {}
                s = c.add_stream(name, rate=30, options=dict(opts), **kw)
                s.width, s.height, s.pix_fmt = W, H, "nv12"
                s.codec_context.gop_size = gop
                if bf is not None:
                    s.codec_context.max_b_frames = bf
                rec["max_b_frames_effective"] = s.codec_context.max_b_frames
                for i in range(16):
                    vf = av.VideoFrame.from_ndarray(FR[i % 8], format="nv12")
                    vf.pts = i
                    for p in s.encode(vf):
                        c.mux(p)
                for p in s.encode(None):
                    c.mux(p)
            with av.open(str(dst)) as c:
                frames = list(c.decode(video=0))
                pk = None
            with av.open(str(dst)) as c:
                keys = [p.is_keyframe for p in c.demux(video=0) if p.size]
            rec.update(ok=True, decoded=len(frames), key_packets=sum(keys), packets=len(keys),
                       pict_types=sorted({str(f.pict_type) for f in frames}))
        except Exception as e:  # noqa: BLE001
            rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
    av.logging.set_level(None)
    rec["log_tail"] = [l[2].strip() for l in logs if l[0] <= av.logging.WARNING][-3:]
    rec["log_bframes"] = [l[2].strip() for l in logs if "B-frame" in l[2] or "b-frame" in l[2].lower()][:4]
    res["cases"].append(rec)
Path(sys.argv[1]).write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
