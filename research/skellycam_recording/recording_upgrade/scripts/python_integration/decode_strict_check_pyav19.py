# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "opencv-python==4.12.0.88", "simplejpeg==1.9.0", "PyTurboJPEG==2.6.1"]
# ///
"""Functional check (no timing): which decoders accept every corpus MJPEG set, and do they agree?

For the first 60 frames (all frames of the short sets) of every MJPEG corpus set: cv2.imdecode, simplejpeg.decode_jpeg with its DEFAULT strict
setting and with strict=False, PyTurboJPEG (if a DLL path is given) and PyAV 19.0.2 libavcodec mjpeg -> bgr24.
Records per set: frames accepted / rejected per method, the first error text, and max abs diff vs cv2 on the
first frame. Settles the NOTES claim that simplejpeg's default strict mode rejects the generic camera's frames,
which the bench smoke JSON does not record (the bench uses strict=False).

  uv run --script research/skellycam_recording/recording_upgrade/scripts/python_integration/decode_strict_check_pyav19.py \
      <out.json> [<turbojpeg.dll>]
"""
from __future__ import annotations

import inspect
import json
import sys
import warnings
from pathlib import Path

import av
import cv2
import numpy as np
import simplejpeg

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")


def main():
    dst = Path(sys.argv[1])
    tj = None
    if len(sys.argv) > 2 and Path(sys.argv[2]).exists():
        from turbojpeg import TJPF_BGR, TurboJPEG
        tj = (TurboJPEG(lib_path=sys.argv[2]), TJPF_BGR)
    sig = inspect.signature(simplejpeg.decode_jpeg)
    out = {"what": "decoder acceptance + agreement on corpus MJPEG frames; functional, no timing",
           "date": "2026-11-09", "pyav": av.__version__, "ffmpeg": av.ffmpeg_version_info, "opencv": cv2.__version__,
           "simplejpeg": simplejpeg.__version__,
           "simplejpeg_strict_default": str(sig.parameters["strict"].default) if "strict" in sig.parameters else None,
           "turbojpeg_dll": sys.argv[2] if tj else None, "sets": {}}
    index = json.loads((CORPUS / "index.json").read_text())
    for name, meta in index.items():
        if meta["kind"] != "mjpeg":
            continue
        frames = [f.read_bytes() for f in sorted((CORPUS / name).glob("frame_*.jpg"))][:60]  # first 60 per set (CPU cap)
        r = {"frames": len(frames)}
        meth = {
            "cv2_imdecode": lambda b: cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR),
            "simplejpeg_default_strict": lambda b: simplejpeg.decode_jpeg(b, colorspace="BGR"),
            "simplejpeg_strict_false": lambda b: simplejpeg.decode_jpeg(b, colorspace="BGR", strict=False),
        }
        if tj:
            meth["turbojpeg"] = lambda b: tj[0].decode(b, pixel_format=tj[1])
        cc = av.CodecContext.create("mjpeg", "r")

        def pyav(b):
            fr = list(cc.decode(av.Packet(b)))
            return fr[0].to_ndarray(format="bgr24") if fr else None
        meth["pyav_mjpeg_bgr24"] = pyav
        ref0 = None
        for m, fn in meth.items():
            ok, bad, first_err, warn_n, first_warn, img0 = 0, 0, None, 0, None, None
            for i, b in enumerate(frames):
                try:
                    with warnings.catch_warnings(record=True) as w:
                        warnings.simplefilter("always")
                        img = fn(b)
                    if w:
                        warn_n += 1
                        first_warn = first_warn or str(w[0].message)[:160]
                    if img is None:
                        raise ValueError("decoder returned None")
                    ok += 1
                    if i == 0:
                        img0 = img
                except Exception as e:  # noqa: BLE001
                    bad += 1
                    first_err = first_err or repr(e)[:200]
            if m == "cv2_imdecode":
                ref0 = img0
            d = {"accepted": ok, "rejected": bad, "first_error": first_err, "frames_with_warning": warn_n,
                 "first_warning": first_warn}
            if img0 is not None and ref0 is not None and img0.shape == ref0.shape:
                d["frame0_max_abs_diff_vs_cv2"] = int(np.abs(img0.astype(np.int16) - ref0.astype(np.int16)).max())
            r[m] = d
        out["sets"][name] = r
        print(name, {m: (r[m]["accepted"], r[m]["rejected"], r[m].get("frame0_max_abs_diff_vs_cv2")) for m in meth},
              flush=True)
    dst.write_text(json.dumps(out, indent=1))
    print("wrote", dst)


if __name__ == "__main__":
    main()
