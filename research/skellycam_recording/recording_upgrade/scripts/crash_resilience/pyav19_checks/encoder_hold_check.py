# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""Encoder hold-back at a live 30 fps feed (PyAV 19.0.2): feed 75 decoded camera frames paced at 30 fps, count the
packets the encoder has returned before the drain (= what a crash at that moment could have muxed at best).
Functional only: counts, no timing reported. Compares SVT-AV1 defaults (random access) with svtav1-params
pred-struct=1 (low delay), and h264_nvenc as in the kill matrix.
usage: uv run --script encoder_hold_check.py <out_json>
"""
from __future__ import annotations

import json
import sys
import time
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/crash_resilience")
import common_cr as cc  # noqa: E402

FED = 75


def run(codec: str, opts: dict) -> dict:
    import av
    from av.video.frame import PictureType
    jp = cc.load_jpegs(cc.DEFAULT_SET, FED)
    dec = av.CodecContext.create("mjpeg", "r")
    frames = []
    for b in jp:
        f2 = dec.decode(av.Packet(b))[0].reformat(format="yuv420p")
        f2.pict_type = PictureType.NONE
        frames.append(f2)
    w, h = cc.corpus_dims()
    enc = av.CodecContext.create(codec, "w")
    enc.width, enc.height, enc.pix_fmt = w, h, "yuv420p"
    enc.time_base = Fraction(1, cc.FPS)
    enc.framerate = Fraction(cc.FPS, 1)
    enc.gop_size = 30
    enc.options = opts
    got = 0
    t0 = time.perf_counter()
    for i, f in enumerate(frames):
        dt = t0 + i / cc.FPS - time.perf_counter()
        if dt > 0:
            time.sleep(dt)
        f.pts = i
        got += len(enc.encode(f))
    before_drain = got
    after = len(enc.encode(None))
    return {"codec": codec, "options": opts, "fed": FED, "packets_before_drain": before_drain,
            "held_by_encoder": FED - before_drain, "packets_from_drain": after}


def main():
    import av
    res = {"env": {"pyav": av.__version__, "libavcodec": ".".join(map(str, av.library_versions["libavcodec"]))},
           "nvidia_smi_before": cc.nvidia_smi(), "runs": []}
    cases = [("libsvtav1", {"preset": "10", "crf": "35"}),
             ("libsvtav1", {"preset": "10", "crf": "35", "svtav1-params": "pred-struct=1"}),
             ("libsvtav1", {"preset": "10", "crf": "35"}),
             ("libsvtav1", {"preset": "10", "crf": "35", "svtav1-params": "pred-struct=1"}),
             ("h264_nvenc", {"preset": "p4", "bf": "0", "rc": "vbr", "cq": "23"}),
             ("h264_nvenc", {"preset": "p4", "bf": "0", "rc": "vbr", "cq": "23", "delay": "0"})]
    for codec, opts in cases:
        try:
            r = run(codec, opts)
        except Exception as e:
            r = {"codec": codec, "options": opts, "error": repr(e)}
        res["runs"].append(r)
        print(r, flush=True)
    res["nvidia_smi_after"] = cc.nvidia_smi()
    Path(sys.argv[1]).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
