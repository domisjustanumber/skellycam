# /// script
# requires-python = ">=3.10"
# dependencies = ["av==19.0.2"]
# ///
"""GF06 static query: which AMF / VideoToolbox (and, for comparison, NVENC / QSV) H.264/HEVC encoders
the PyAV 19.0.2 wheel on this machine exposes, with their private AVOption names and defaults, plus the
generic AVCodecContext fields that matter for all-intra + constant-QP (gop_size, max_b_frames, qmin, qmax)
as set by the codec's own defaults table.

No device is opened: av.codec.Codec(...) and CodecContext.create(...) only allocate an AVCodecContext
(avcodec_alloc_context3 + codec defaults); open() is never called. No timing.
Usage: uv run --script gf06_pyav_amf_vt_options.py <out.json>"""
import json
import platform
import sys

import av

ENCODERS = ["h264_amf", "hevc_amf", "av1_amf", "h264_videotoolbox", "hevc_videotoolbox",
            "prores_videotoolbox", "h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv"]
CTX_FIELDS = ["gop_size", "max_b_frames", "qmin", "qmax", "global_quality", "bit_rate", "flags"]
# generic AVCodecContext options whose table entry is recorded (table default, not the codec's defaults)
GENERIC = ["g", "bf", "i_qfactor", "i_qoffset", "b_qfactor", "qmin", "qmax", "global_quality", "flags", "forced_idr"]


def opt_rec(o):
    rec = {"name": o.name}
    for attr in ("type", "default", "help", "min", "max", "flags", "is_array"):
        try:
            v = getattr(o, attr)
        except Exception as e:  # noqa: BLE001
            v = f"<{type(e).__name__}>"
        if v is None or isinstance(v, (int, float, str, bool)):
            rec[attr] = v
        else:
            rec[attr] = str(v)
    try:
        rec["choices"] = [{"name": c.name, "value": c.value, "help": c.help} for c in (o.choices or [])]
    except Exception:  # noqa: BLE001
        pass
    return rec


out = {
    "av_version": av.__version__,
    "ffmpeg_version_info": getattr(av, "ffmpeg_version_info", None),
    "library_versions": {k: list(v) for k, v in av.library_versions.items()},
    "platform": platform.platform(),
    "python": sys.version,
    "note": "static query only; no encoder opened, no device touched",
    "encoders": {},
}
avail = av.codecs_available
for name in ENCODERS:
    rec = {"in_codecs_available": name in avail}
    try:
        c = av.codec.Codec(name, "w")
        rec["long_name"] = c.long_name
        rec["pix_fmts"] = [f.name for f in (c.video_formats or [])]
        try:
            rec["capabilities"] = str(c.capabilities)
        except Exception as e:  # noqa: BLE001
            rec["capabilities"] = f"<{type(e).__name__}>"
        ctx = av.codec.CodecContext.create(c)  # alloc only, never opened
        so = ctx.supported_options
        rec["private_options"] = [opt_rec(o) for o in so.private]
        rec["generic_options_subset"] = [opt_rec(o) for o in so.generic if o.name in GENERIC]
        rec["reads_i_qfactor_note"] = ("i_qfactor/i_qoffset are generic AVCodecContext options and are listed for every "
                                       "encoder; whether the wrapper reads them is a code question (see GF06_amf_vt_intra.md)")
        cf = {}
        for f in CTX_FIELDS:
            try:
                v = getattr(ctx, f)
                cf[f] = v if isinstance(v, (int, float, str, bool, type(None))) else str(v)
            except Exception as e:  # noqa: BLE001
                cf[f] = f"<{type(e).__name__}: {e}>"
        rec["context_defaults_after_alloc"] = cf
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"
    out["encoders"][name] = rec

json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), indent=1)
for k, v in out["encoders"].items():
    print(k, "PRESENT" if "long_name" in v else "ABSENT", v.get("context_defaults_after_alloc", v.get("error", "")))
