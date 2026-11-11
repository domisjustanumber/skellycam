# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2"]
# ///
"""GF09 step 1b: static query (no encoder open, no encode, no timing) of the private AVOptions of h264_qsv,
hevc_qsv, h264_nvenc and hevc_nvenc as compiled into the PyAV 19.0.2 wheel, plus the wheel's hardware decoders.

PyAV 19 exposes no option list, so this calls the wheel's own bundled libavcodec / libavutil DLLs (av.libs) via
ctypes: avcodec_find_encoder_by_name -> avcodec_alloc_context3 (allocates priv_data with defaults; no session is
created) -> av_opt_child_next(avctx) = priv_data -> av_opt_next(priv) over the AVOption table; defaults read back as
strings with av_opt_get. AVOption field offsets (x64): name 0, help 8, offset 16, type 20, default 24, min 32,
max 40, flags 48, unit 56 (libavutil/opt.h).

Run from the repo root:
  uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/gapfill/GF09/probe_opts.py
Writes results/uncompressed_intra/gapfill/GF09_avoptions_pyav19.0.2.json
"""
from __future__ import annotations

import ctypes as C
import glob
import json
import os
from pathlib import Path

import av

OUT = Path(__file__).resolve().parents[4] / "results" / "uncompressed_intra" / "gapfill" / "GF09_avoptions_pyav19.0.2.json"
LIBS = Path(av.__file__).resolve().parents[1] / "av.libs"
# enum AVOptionType in FFmpeg n9.0.2 libavutil/opt.h:254-334 starts at AV_OPT_TYPE_FLAGS = 1
OPT_TYPES = {1: "flags", 2: "int", 3: "int64", 4: "double", 5: "float", 6: "string", 7: "rational", 8: "binary",
             9: "dict", 10: "uint64", 11: "const", 12: "image_size", 13: "pixel_fmt", 14: "sample_fmt",
             15: "video_rate", 16: "duration", 17: "color", 18: "bool", 19: "chlayout", 20: "uint"}


class AVOption(C.Structure):
    _fields_ = [("name", C.c_char_p), ("help", C.c_char_p), ("offset", C.c_int), ("type", C.c_int),
                ("default_val", C.c_int64), ("min", C.c_double), ("max", C.c_double), ("flags", C.c_int),
                ("unit", C.c_char_p)]


def dll(prefix: str) -> C.CDLL:
    return C.CDLL(glob.glob(str(LIBS / f"{prefix}-*.dll"))[0])


def main() -> None:
    os.add_dll_directory(str(LIBS))
    avc, avu = dll("avcodec"), dll("avutil")
    avc.avcodec_find_encoder_by_name.restype = C.c_void_p
    avc.avcodec_find_encoder_by_name.argtypes = [C.c_char_p]
    avc.avcodec_alloc_context3.restype = C.c_void_p
    avc.avcodec_alloc_context3.argtypes = [C.c_void_p]
    avc.avcodec_free_context.argtypes = [C.POINTER(C.c_void_p)]
    avu.av_opt_child_next.restype = C.c_void_p
    avu.av_opt_child_next.argtypes = [C.c_void_p, C.c_void_p]
    avu.av_opt_next.restype = C.POINTER(AVOption)
    avu.av_opt_next.argtypes = [C.c_void_p, C.c_void_p]
    avu.av_opt_get.argtypes = [C.c_void_p, C.c_char_p, C.c_int, C.POINTER(C.c_char_p)]
    avu.av_opt_get.restype = C.c_int
    avu.av_free.argtypes = [C.c_void_p]
    out = {"av_version": av.__version__,
           "library_versions": {k: list(v) for k, v in av.library_versions.items()},
           "method": "ctypes on the wheel's av.libs avcodec/avutil: avcodec_alloc_context3 + av_opt_next on priv_data",
           "encoders": {}}
    for name in ("h264_qsv", "hevc_qsv", "h264_nvenc", "hevc_nvenc"):
        codec = avc.avcodec_find_encoder_by_name(name.encode())
        if not codec:
            out["encoders"][name] = {"error": "not found"}
            continue
        ctx = C.c_void_p(avc.avcodec_alloc_context3(codec))
        priv = avu.av_opt_child_next(ctx, None)
        rows, consts = [], {}
        prev = None
        while True:
            o = avu.av_opt_next(priv, prev)
            if not o:
                break
            op = o.contents
            t = OPT_TYPES.get(op.type, str(op.type))
            nm = op.name.decode()
            unit = op.unit.decode() if op.unit else None
            if t == "const":
                consts.setdefault(unit, []).append({"name": nm, "value": op.default_val})
            else:
                s = C.c_char_p()
                rc = avu.av_opt_get(priv, op.name, 0, C.byref(s))
                dflt = s.value.decode(errors="replace") if rc >= 0 and s.value is not None else None
                if s:
                    avu.av_free(s)
                rows.append({"name": nm, "type": t, "default": dflt, "min": op.min, "max": op.max, "unit": unit,
                             "help": op.help.decode(errors="replace") if op.help else None})
            prev = C.cast(o, C.c_void_p)
        for r in rows:
            if r["unit"] in consts:
                r["choices"] = consts[r["unit"]]
        avc.avcodec_free_context(C.byref(ctx))
        out["encoders"][name] = {"n_options": len(rows), "options": rows}
    avail = sorted(av.codecs_available)
    out["hw_decoders_in_wheel"] = [n for n in avail if any(s in n for s in ("cuvid", "_qsv"))]
    try:
        from av.codec.hwaccel import hwdevices_available
        out["hwdevices_available"] = list(hwdevices_available())
    except Exception as e:  # noqa: BLE001
        out["hwdevices_available"] = f"error {type(e).__name__}: {e}"
    kw = ("lossless", "qp", "transform", "low_power", "profile", "tune", "rc", "bypass", "quant")
    out["keyword_hits"] = {n: [o["name"] for o in v.get("options", [])
                               if any(k in (o["name"] + " " + (o["help"] or "")).lower() for k in kw)]
                           for n, v in out["encoders"].items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"n_options": {k: v.get("n_options") for k, v in out["encoders"].items()},
                      "hw_decoders_in_wheel": out["hw_decoders_in_wheel"], "hwdevices": out["hwdevices_available"],
                      "keyword_hits": out["keyword_hits"]}, indent=1))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
