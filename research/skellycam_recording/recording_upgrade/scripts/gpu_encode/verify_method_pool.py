# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Verifier (method): NVENC session-pool sharing, PyAV 19.0.2 only, FUNCTIONAL, no timing.
Control: open each probe encoder with no sessions held (must succeed for the 'shared pool' inference to mean anything).
Then hold 12 h264_nvenc sessions and retry each probe. Probes: hevc_nvenc, h264_d3d12va (HWAccel d3d12va),
h264_mf (hw_encoding=1, records the MFT chosen), h264_qsv (sw frames). Aborts if nvidia-smi shows foreign sessions.
"""
import json
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

import av
import av.logging
import numpy as np
from av.codec.hwaccel import HWAccel

W, H = 1280, 720
raw = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode/inputs/nv12_720p.yuv").read_bytes()
FR = np.frombuffer(raw[: W * H * 3 // 2], np.uint8).reshape(H * 3 // 2, W)


def smi():
    return subprocess.run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount", "--format=csv,noheader"],
                          capture_output=True, text=True).stdout.strip()


def open_enc(name):
    kw, opts = {}, {}
    if name == "h264_d3d12va":
        kw["hwaccel"] = HWAccel("d3d12va")
    if name.endswith("_mf"):
        opts["hw_encoding"] = "1"
    if name.endswith("_nvenc"):
        opts["preset"] = "p4"
    cc = av.CodecContext.create(name, "w", **kw)
    cc.width, cc.height, cc.pix_fmt = W, H, "nv12"
    cc.time_base = Fraction(1, 30)
    cc.framerate = Fraction(30, 1)
    cc.gop_size = 0 if name.endswith("_nvenc") else 1
    cc.max_b_frames = 0
    cc.options = opts
    cc.open()
    pk = []
    for i in range(3):
        f = av.VideoFrame.from_ndarray(FR, format="nv12")
        f.pts = i
        pk += cc.encode(f)
    return cc, pk


def probe(name):
    av.logging.set_level(av.logging.VERBOSE)
    rec = {}
    with av.logging.Capture() as logs:
        try:
            cc, pk = open_enc(name)
            pk += cc.encode(None)
            rec.update(ok=True, packets=len(pk))
        except Exception as e:  # noqa: BLE001
            rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:250])
    av.logging.set_level(None)
    rec["mft"] = [l[2].strip() for l in logs if "MFT name" in l[2]]
    rec["log_tail"] = [l[2].strip() for l in logs if l[0] <= av.logging.WARNING][-3:]
    return rec


PROBES = ["hevc_nvenc", "h264_d3d12va", "h264_mf", "h264_qsv"]
rep = {"pyav": av.__version__, "smi_before": smi()}
if rep["smi_before"] != "0":
    rep["aborted"] = "foreign NVENC sessions present"
    Path(sys.argv[1]).write_text(json.dumps(rep, indent=1))
    sys.exit(0)
rep["control_no_sessions_held"] = {n: probe(n) for n in PROBES}
held = []
for i in range(16):
    try:
        cc, _ = open_enc("h264_nvenc")
        held.append(cc)
    except Exception as e:  # noqa: BLE001
        rep["first_h264_nvenc_error_at"] = i + 1
        rep["first_error"] = f"{type(e).__name__}: {e}"[:200]
        break
rep["held"] = len(held)
time.sleep(0.5)
rep["smi_while_held"] = smi()
rep["with_sessions_held"] = {n: probe(n) for n in PROBES}
for cc in held:
    try:
        cc.encode(None)
    except Exception:  # noqa: BLE001
        pass
del held
time.sleep(0.5)
rep["smi_after"] = smi()
Path(sys.argv[1]).write_text(json.dumps(rep, indent=1))
print(json.dumps(rep, indent=1))
