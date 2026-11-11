"""Side finding check: frames decoded from camera JPEGs carry pict_type=I; do encoders treat that as a forced key frame?

Encodes 60 frames of c930e_720p_flash (decoded by PyAV's mjpeg decoder) with gop 30, once passing the decoded frames
as they are and once with frame.pict_type = NONE, and counts key-flagged packets.
usage: python pict_type_check.py   -> results/crash_resilience/pict_type_check.json
"""
from __future__ import annotations

import json
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_cr as cc  # noqa: E402


def run(codec: str, opts: dict, clear: bool) -> dict:
    import av
    from av.video.frame import PictureType
    jp = cc.load_jpegs(cc.DEFAULT_SET, 60)
    dec = av.CodecContext.create("mjpeg", "r")
    w, h = cc.corpus_dims()
    enc = av.CodecContext.create(codec, "w")
    enc.width, enc.height, enc.pix_fmt = w, h, "yuv420p"
    enc.time_base = Fraction(1, cc.FPS)
    enc.framerate = Fraction(cc.FPS, 1)
    enc.gop_size = 30
    enc.options = opts
    keys = pk = 0
    first_type = None
    for i, b in enumerate(jp):
        fr = dec.decode(av.Packet(b))[0]
        if first_type is None:
            first_type = str(fr.pict_type)
        f2 = fr.reformat(format="yuv420p")
        if clear:
            f2.pict_type = PictureType.NONE
        f2.pts = i
        for p in enc.encode(f2):
            pk += 1
            keys += int(p.is_keyframe)
    for p in enc.encode(None):
        pk += 1
        keys += int(p.is_keyframe)
    return {"codec": codec, "pict_type_cleared": clear, "packets": pk, "key_packets": keys,
            "decoded_jpeg_pict_type": first_type}


def main():
    res = {"env": cc.env_versions(), "nvidia_smi_before": cc.nvidia_smi(), "runs": []}
    for codec, opts in (("libsvtav1", {"preset": "10", "crf": "35"}), ("h264_nvenc", {"preset": "p4", "bf": "0"}),
                        ("libx264", {"preset": "ultrafast"})):
        for clear in (False, True):
            try:
                r = run(codec, opts, clear)
            except Exception as e:
                r = {"codec": codec, "pict_type_cleared": clear, "error": repr(e)}
            res["runs"].append(r)
            print(r, flush=True)
    res["nvidia_smi_after"] = cc.nvidia_smi()
    (cc.RES / "pict_type_check.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
