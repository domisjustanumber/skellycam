# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2"]
# ///
"""Static (no device, no timing): pixel formats each encoder advertises in PyAV 19.0.2."""
import json, av
out = {"pyav": av.__version__, "libavcodec": list(av.library_versions["libavcodec"]), "video_formats": {}}
for n in ["h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv", "mjpeg_qsv"]:
    c = av.codec.Codec(n, "w")
    out["video_formats"][n] = [f.name for f in (c.video_formats or [])]
print(json.dumps(out, indent=1))
