# /// script
# requires-python = ">=3.10"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""List the CPU (software) encoders relevant to the hw_accel_target study that the PyAV 19.0.2 wheel
on this machine exposes, with their supported pixel formats. Functional inventory only: no timing.
Usage: uv run --script sw_encoders_pyav19.py <out.json>"""
import json, sys, platform
import av

CANDIDATES = ["libsvtav1", "libaom-av1", "librav1e", "libvpx-vp9", "libvpx", "libopenh264", "libx264",
              "libx265", "mjpeg", "ljpeg", "jpegls", "ffv1", "prores_ks", "libwebp", "png", "rawvideo",
              "libjxl", "libopenjpeg", "jpeg2000"]
out = {"av_version": av.__version__, "ffmpeg_version": av.ffmpeg_version_info if hasattr(av, "ffmpeg_version_info") else None,
       "libavcodec": list(av.library_versions.get("libavcodec", ())), "platform": platform.platform(), "encoders": {}}
avail = av.codecs_available
for name in CANDIDATES:
    rec = {"in_codecs_available": name in avail}
    try:
        c = av.codec.Codec(name, "w")
        rec["long_name"] = c.long_name
        rec["pix_fmts"] = [f.name for f in (c.video_formats or [])]
        rec["yuv422_input"] = [f for f in rec["pix_fmts"] if "422" in f or f in ("yuyv422", "uyvy422")]
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"
    out["encoders"][name] = rec
json.dump(out, open(sys.argv[1], "w"), indent=1)
for k, v in out["encoders"].items():
    print(k, "OK" if "long_name" in v else "MISSING", v.get("yuv422_input", ""))
