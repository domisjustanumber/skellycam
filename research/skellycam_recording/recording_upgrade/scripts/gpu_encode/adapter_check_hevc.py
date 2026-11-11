# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""FUNCTIONAL ONLY (no timing), PyAV 19.0.2, with the Intel UHD 770 present.
Which adapter / MFT do hevc_d3d12va (HWAccel d3d12va, default device) and hevc_mf (hw_encoding=1) use? (revision check, copy of adapter_check.py with hevc)
Captures FFmpeg VERBOSE/DEBUG log lines mentioning adapters/MFTs. Writes results/gpu_encode/adapter_check_hevc_19.0.2.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import av
import av.logging
import numpy as np
from av.codec.hwaccel import HWAccel

sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/gpu_encode")
from common import MEDIA, RESULTS, nvidia_smi, prepare_inputs, probe_stream  # noqa: E402

W, H, N = 1920, 1080, 8
OUT = MEDIA / "qsv_recheck_19.0.2"
raw = Path(prepare_inputs()["nv12_1080p"]).read_bytes()
fs = W * H * 3 // 2
fr = [np.frombuffer(raw[i * fs:(i + 1) * fs], np.uint8).reshape(H * 3 // 2, W) for i in range(N)]
KEYS = ("adapter", "Adapter", "device", "Device", "MFT", "vendor", "Vendor", "Intel", "NVIDIA", "selected", "Using")
rep: dict = {"pyav": av.__version__, "runs": []}
for name, opts, hw in (("hevc_d3d12va", {}, "d3d12va"), ("hevc_mf", {"hw_encoding": "1"}, None)):
    dst = OUT / f"adapter_{name}.mp4"
    rec: dict = {"encoder": name}
    av.logging.set_level(av.logging.DEBUG)
    smi_mid = None
    with av.logging.Capture() as logs:
        try:
            with av.open(str(dst), "w") as c:
                kw = {"hwaccel": HWAccel(hw)} if hw else {}
                s = c.add_stream(name, rate=30, options=dict(opts), **kw)
                s.width, s.height, s.pix_fmt = W, H, "nv12"
                s.codec_context.gop_size = 1
                s.codec_context.max_b_frames = 0
                for i in range(N):
                    vf = av.VideoFrame.from_ndarray(fr[i], format="nv12")
                    vf.pts = i
                    for p in s.encode(vf):
                        c.mux(p)
                    if i == 4:
                        smi_mid = nvidia_smi()
                for p in s.encode(None):
                    c.mux(p)
            rec.update(ok=True, probe={k: v for k, v in probe_stream(dst).items() if k != "decode_stderr"})
        except Exception as e:  # noqa: BLE001
            rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
    av.logging.set_level(None)
    rec["nvidia_smi_mid_encode"] = smi_mid
    rec["log_matches"] = [f"{lv[1]}: {lv[2].strip()}" for lv in logs if any(k in lv[2] for k in KEYS)][:60]
    rep["runs"].append(rec)
(RESULTS / "adapter_check_hevc_19.0.2.json").write_text(json.dumps(rep, indent=1, default=str))
print(json.dumps(rep, indent=1, default=str))
