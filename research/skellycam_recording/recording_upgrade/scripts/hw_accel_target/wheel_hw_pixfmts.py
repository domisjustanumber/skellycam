# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2"]
# ///
"""Static query: input pixel formats each hardware encoder in the PyAV 19.0.2 wheel advertises.
No device is opened; this only reads the codec descriptors compiled into the bundled FFmpeg."""
import json, sys
import av

names = ["h264_nvenc", "hevc_nvenc", "av1_nvenc",
         "h264_qsv", "hevc_qsv", "av1_qsv", "vp9_qsv", "mjpeg_qsv",
         "h264_amf", "hevc_amf", "av1_amf",
         "h264_d3d12va", "hevc_d3d12va", "av1_d3d12va",
         "h264_mf", "hevc_mf", "av1_mf",
         "mjpeg_cuvid", "mjpeg_qsv"]
out = {"av": av.__version__, "libavcodec": av.library_versions.get("libavcodec"), "encoders": {}, "decoders": {}}
for n in names:
    for mode, key in (("w", "encoders"), ("r", "decoders")):
        try:
            c = av.codec.Codec(n, mode)
        except Exception as e:
            continue
        fmts = [f.name for f in (c.video_formats or [])]
        out[key][n] = fmts
json.dump(out, sys.stdout, indent=1)
