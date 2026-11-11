"""NVENC concurrent-session limit with the installed driver (FUNCTIONAL; sensitive to other NVENC users).

1. Opens h264_nvenc encoders one by one in this process (PyAV, 1280x720 NV12, each fed one frame so the
   session is live) until one fails or --max is reached; records the first error and nvidia-smi
   encoder.stats.sessionCount while all are open.
2. While those sessions are held, tries ONE extra encode through each other NVIDIA-backed API in a separate
   ffmpeg process (hevc_nvenc, h264_vulkan, h264_d3d12va, h264_mf) to see whether they share the same limit.
Other processes that use NVENC (Parsec, Sunshine, other agents) reduce the count - the nvidia-smi
sessionCount before the test is recorded; run on a quiet machine for the definitive number.

Run (repo root):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvenc_sessions.py --max 24
Writes results/gpu_encode/nvenc_sessions.json (or bench/nvenc_sessions_<stamp>.json with --bench).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import av
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import BENCH, FFMPEG, RESULTS, nvidia_smi, prepare_inputs, run  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=24)
    ap.add_argument("--codec", default="h264_nvenc")
    ap.add_argument("--bench", action="store_true", help="write into results/gpu_encode/bench/")
    a = ap.parse_args()
    inputs = prepare_inputs()
    w, h = 1280, 720
    frame_np = np.frombuffer(Path(inputs["nv12_720p"]).read_bytes()[: w * h * 3 // 2], np.uint8).reshape(h * 3 // 2, w)
    rep = {"pyav": av.__version__, "codec": a.codec, "nvidia_smi_before": nvidia_smi(), "opened": 0}
    ctxs = []
    for i in range(a.max):
        try:
            cc = av.CodecContext.create(a.codec, "w")
            cc.width, cc.height, cc.pix_fmt = w, h, "nv12"
            cc.time_base = av.time_base and __import__("fractions").Fraction(1, 30)
            cc.options = {"preset": "p4"}
            cc.open()
            f = av.VideoFrame.from_ndarray(frame_np, format="nv12")
            f.pts = 0
            cc.encode(f)
            ctxs.append(cc)
            rep["opened"] = i + 1
        except Exception as e:  # noqa: BLE001
            rep["first_error_at_session"] = i + 1
            rep["first_error"] = f"{type(e).__name__}: {e}"[:300]
            break
    time.sleep(0.5)
    rep["nvidia_smi_while_open"] = nvidia_smi()
    extra = {}
    src = ["-f", "rawvideo", "-pix_fmt", "nv12", "-s", "1280x720", "-framerate", "30", "-i", str(inputs["nv12_720p"]),
           "-frames:v", "5"]
    for name, pre, vf in (("hevc_nvenc", [], None),
                          ("h264_vulkan", ["-init_hw_device", "vulkan=vk", "-filter_hw_device", "vk"], "format=nv12,hwupload"),
                          ("h264_d3d12va", ["-init_hw_device", "d3d12va=d3d", "-filter_hw_device", "d3d"], "format=nv12,hwupload"),
                          ("h264_mf", [], None)):
        cmd = [FFMPEG, "-hide_banner", "-v", "verbose", *pre, *src] + (["-vf", vf] if vf else []) + \
              ["-c:v", name] + (["-hw_encoding", "1"] if name.endswith("_mf") else []) + (["-bf", "0"] if "d3d12" in name else []) + \
              ["-f", "null", "-"]
        r = run(cmd, timeout=60)
        diag = [ln.split("] ")[-1] for ln in r.stderr.splitlines()
                if re.search(r"(fail|limit|session|not support|error)", ln, re.I) and "Terminating" not in ln][:4]
        extra[name] = {"returncode": r.returncode, "ok": r.returncode == 0, "diagnosis": diag}
    rep["extra_api_while_held"] = extra
    for cc in ctxs:
        try:
            cc.encode(None)
        except Exception:  # noqa: BLE001
            pass
    del ctxs
    rep["nvidia_smi_after_close"] = nvidia_smi()
    out_dir = BENCH if a.bench else RESULTS
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"nvenc_sessions_{time.strftime('%Y%m%dT%H%M%S')}.json" if a.bench else "nvenc_sessions.json"
    (out_dir / name).write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
