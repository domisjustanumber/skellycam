# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""FUNCTIONAL ONLY (no timing), PyAV 19.0.2. Follow-ups to qsv_recheck_19.0.2:
 a) hevc_qsv gop15 gave pict_type B with max_b_frames=0: list the encoder's 'gpb' option and re-encode with gpb=0.
 b) mjpeg_qsv decode of real 4:2:2 camera JPEGs: Y-plane max |diff| vs CPU mjpeg decode.
Writes results/gpu_encode/qsv_recheck2_19.0.2.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import av
import numpy as np

sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/gpu_encode")
from common import CORPUS, MEDIA, RESULTS, prepare_inputs, probe_stream  # noqa: E402

W, H, N_SRC, LOOPS = 1920, 1080, 8, 4
OUT = MEDIA / "qsv_recheck_19.0.2"
rep: dict = {"pyav": av.__version__}

# a) options
raw = Path(prepare_inputs()["nv12_1080p"]).read_bytes()
fs = W * H * 3 // 2
fr = [np.frombuffer(raw[i * fs:(i + 1) * fs], np.uint8).reshape(H * 3 // 2, W) for i in range(N_SRC)]
rep["hevc_qsv_gpb"] = []
for gpb in ("1", "0"):
    dst = OUT / f"hevc_qsv_gop15_gpb{gpb}.mkv"
    rec: dict = {"gpb": gpb}
    try:
        with av.open(str(dst), "w") as c:
            s = c.add_stream("hevc_qsv", rate=30, options={"gpb": gpb})
            s.width, s.height, s.pix_fmt = W, H, "nv12"
            s.codec_context.gop_size = 15
            s.codec_context.max_b_frames = 0
            for i in range(N_SRC * LOOPS):
                vf = av.VideoFrame.from_ndarray(fr[i % N_SRC], format="nv12")
                vf.pts = i
                for p in s.encode(vf):
                    c.mux(p)
            for p in s.encode(None):
                c.mux(p)
        rec.update(ok=True, probe=probe_stream(dst))
    except Exception as e:  # noqa: BLE001
        rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
    rep["hevc_qsv_gpb"].append(rec)

# b) decode accuracy
rep["mjpeg_qsv_decode"] = []
for setname in ("c930e_1080p", "c930e_720p_flash"):
    jpgs = sorted((CORPUS / setname).glob("frame_*.jpg"))[:5]
    res = {}
    for mode in ("mjpeg", "mjpeg_qsv"):
        cc = av.CodecContext.create(mode, "r")
        ys, fmts = [], set()
        for j in jpgs:
            for f in cc.decode(av.Packet(j.read_bytes())):
                fmts.add(f.format.name)
                ys.append(f.to_ndarray(format="gray"))
        for f in cc.decode(None):
            fmts.add(f.format.name)
            ys.append(f.to_ndarray(format="gray"))
        res[mode] = (ys, sorted(fmts))
    a, b = res["mjpeg"][0], res["mjpeg_qsv"][0]
    n = min(len(a), len(b))
    d = [np.abs(a[k].astype(int) - b[k].astype(int)) for k in range(n)]
    rep["mjpeg_qsv_decode"].append({"set": setname, "cpu_formats": res["mjpeg"][1], "qsv_formats": res["mjpeg_qsv"][1],
                                    "frames_compared": n, "shape": list(a[0].shape) if a else None,
                                    "y_max_abs_diff": int(max(x.max() for x in d)) if d else None,
                                    "y_mean_abs_diff": float(round(np.mean([x.mean() for x in d]), 3)) if d else None,
                                    "note": "Y via to_ndarray(format='gray') (swscale), compared per pixel"})
(RESULTS / "qsv_recheck2_19.0.2.json").write_text(json.dumps(rep, indent=1, default=str))
print(json.dumps(rep, indent=1, default=str))
