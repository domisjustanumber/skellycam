# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Verifier (method): is the PyAV 19.0.2 mjpeg_cuvid / mjpeg+HWAccel('cuda') failure specific to 4:2:2?
Control input: diag/j420.mjpeg (the same camera frames re-encoded 4:2:0 by the investigator; 3 frames).
Test input: inputs/mjpeg_1080p.mjpeg (c922 1080p, 4:2:2, first 5 frames). Packets from PyAV's mjpeg demuxer.
FUNCTIONAL, no timing. Writes JSON to argv[1].
"""
import json
import sys
from pathlib import Path

import av
import av.logging
from av.codec.hwaccel import HWAccel

G = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode")
inputs = {"j420 (4:2:0)": G / "diag/j420.mjpeg", "mjpeg_1080p (4:2:2)": G / "inputs/mjpeg_1080p.mjpeg"}
out = {"pyav": av.__version__, "runs": []}
for label, p in inputs.items():
    with av.open(str(p), format="mjpeg") as c:
        pkts = [bytes(pk) for pk, _ in zip(c.demux(video=0), range(5)) if pk.size]
        src_fmt = c.streams.video[0].codec_context.pix_fmt
    for mode in ("mjpeg_cuvid", "mjpeg+hwaccel_cuda"):
        rec = {"input": label, "src_pix_fmt": src_fmt, "mode": mode, "packets": len(pkts)}
        av.logging.set_level(av.logging.VERBOSE)
        with av.logging.Capture() as logs:
            try:
                if mode == "mjpeg_cuvid":
                    cc = av.CodecContext.create("mjpeg_cuvid", "r")
                else:
                    cc = av.CodecContext.create("mjpeg", "r", hwaccel=HWAccel("cuda", allow_software_fallback=False))
                n, fmts = 0, set()
                for b in pkts:
                    for f in cc.decode(av.Packet(b)):
                        n += 1
                        fmts.add(f.format.name)
                for f in cc.decode(None):
                    n += 1
                    fmts.add(f.format.name)
                rec.update(ok=n > 0, frames=n, formats=sorted(fmts))
            except Exception as e:  # noqa: BLE001
                rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:250])
        av.logging.set_level(None)
        rec["log_tail"] = [l[2].strip() for l in logs if l[0] <= av.logging.WARNING][-4:]
        out["runs"].append(rec)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
