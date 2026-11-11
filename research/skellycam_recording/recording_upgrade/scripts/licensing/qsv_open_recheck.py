# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.3.4"]
# ///
"""Revise-step functional re-check (no timing): do the QSV encoders open and emit packets in PyAV 19.0.2 now
that the Intel UHD 770 iGPU is present (the 10:55 probe_pyav_19.0.2.json run predates that)?
8 synthetic 640x480 frames per encoder, default options except pix_fmt. Output written to an in-memory mkv.
Usage: uv run --script qsv_open_recheck.py <out.json>"""
import io, json, sys, traceback, av, numpy as np

ENCODERS = [("h264_qsv", "nv12"), ("hevc_qsv", "nv12"), ("vp9_qsv", "nv12"), ("av1_qsv", "nv12"),
            ("mjpeg_qsv", "nv12"), ("libsvtav1", "yuv420p")]
res = {"av": av.__version__, "ffmpeg": av.library_versions.get("libavcodec"), "encoders": {}}
for name, pix in ENCODERS:
    r = {"pix_fmt": pix}
    try:
        buf = io.BytesIO()
        with av.open(buf, "w", format="matroska") as out:
            s = out.add_stream(name, rate=30)
            s.width, s.height, s.pix_fmt = 640, 480, pix
            n = 0
            for i in range(8):
                img = np.full((480, 640, 3), (i * 30) % 256, np.uint8)
                fr = av.VideoFrame.from_ndarray(img, format="rgb24").reformat(format=pix)
                for p in s.encode(fr):
                    out.mux(p); n += 1
            for p in s.encode(None):
                out.mux(p); n += 1
        r.update(opened=True, packets=n, bytes=len(buf.getvalue()))
    except Exception as e:  # noqa: BLE001
        r.update(opened=False, error=f"{type(e).__name__}: {e}"[:300])
    res["encoders"][name] = r
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
