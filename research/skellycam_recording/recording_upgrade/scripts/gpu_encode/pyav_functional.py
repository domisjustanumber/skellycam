# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Functional test of hardware encoders/decoders through PyAV (FUNCTIONAL ONLY, no timing).

Runs under whichever PyAV is importing it:
  PyAV 18.0.0 (skellycam venv, read-only use):
    .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/pyav_functional.py
  PyAV 19.0.2 (isolated, PEP 723 header above):
    uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/pyav_functional.py
Writes results/gpu_encode/pyav_functional_<avversion>.json/.md; media under skellycam-raw/.../gpu_encode/pyav_<ver>/.

Per encoder: encode 32 NV12 frames (8 real 1080p frames, looped) from numpy via VideoFrame.from_ndarray,
variants intra / gop15 (no B-frames), feeding software frames; where a hw device type applies, also with
add_stream(..., hwaccel=HWAccel(<type>)) so PyAV builds the hw frames context and uploads. ffprobe checks output.
Decoders: corpus JPEGs through mjpeg (CPU), mjpeg_cuvid, and mjpeg + HWAccel('cuda'); output format and
max |diff| of the Y plane vs the CPU decoder.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import av
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import CORPUS, MEDIA, RESULTS, nvidia_smi, prepare_inputs, probe_stream  # noqa: E402

try:
    from av.codec.hwaccel import HWAccel, hwdevices_available
except Exception:  # noqa: BLE001
    HWAccel = None
    hwdevices_available = lambda: []  # noqa: E731

VER = av.__version__
OUT = MEDIA / f"pyav_{VER}"
W, H, N_SRC, LOOPS = 1920, 1080, 8, 4

# encoder -> (options, hwaccel device type or None, container ext)
ENCODERS = {
    "h264_nvenc": ({"preset": "p4"}, "cuda", "mkv"),
    "hevc_nvenc": ({"preset": "p4"}, "cuda", "mkv"),
    "av1_nvenc": ({"preset": "p4"}, "cuda", "mkv"),
    "h264_qsv": ({}, "qsv", "mkv"),
    "hevc_qsv": ({}, "qsv", "mkv"),
    "av1_qsv": ({}, "qsv", "mkv"),
    "vp9_qsv": ({}, "qsv", "mkv"),
    "mjpeg_qsv": ({}, "qsv", "mkv"),
    "h264_amf": ({}, "amf", "mkv"),
    "hevc_amf": ({}, "amf", "mkv"),
    "av1_amf": ({}, "amf", "mkv"),
    "h264_mf": ({"hw_encoding": "1"}, None, "mkv"),
    "hevc_mf": ({"hw_encoding": "1"}, None, "mkv"),
    "av1_mf": ({"hw_encoding": "1"}, None, "mkv"),
    "h264_d3d12va": ({}, "d3d12va", "mp4"),
    "hevc_d3d12va": ({}, "d3d12va", "mp4"),
    "av1_d3d12va": ({}, "d3d12va", "mp4"),
    "h264_vulkan": ({}, "vulkan", "mkv"),
    "hevc_vulkan": ({}, "vulkan", "mkv"),
    "av1_vulkan": ({}, "vulkan", "mkv"),
    "ffv1_vulkan": ({"level": "4", "strict": "-2"}, "vulkan", "mkv"),
}
# nvenc: gop_size 0 = intra-only in ffmpeg's nvenc wrapper; 1 is rejected by the driver (see ff_functional)
INTRA_GOP = {"h264_nvenc": 0, "hevc_nvenc": 0, "av1_nvenc": 0}


def load_nv12() -> list[np.ndarray]:
    raw = Path(prepare_inputs()["nv12_1080p"]).read_bytes()
    fs = W * H * 3 // 2
    return [np.frombuffer(raw[i * fs:(i + 1) * fs], np.uint8).reshape(H * 3 // 2, W) for i in range(N_SRC)]


def encode(name: str, variant: str, frames: list[np.ndarray], use_hw: bool) -> dict:
    opts, hwtype, ext = ENCODERS[name]
    tag = f"{name}_{variant}_{'hwctx' if use_hw else 'sw'}"
    dst = OUT / f"{tag}.{ext}"
    rec: dict = {"encoder": name, "variant": variant, "input": "hwaccel ctx" if use_hw else "sw frames",
                 "hwaccel": hwtype if use_hw else None}
    if name not in av.codecs_available:
        rec.update(ok=False, error="codec not in av.codecs_available (not built into this wheel)")
        return rec
    try:
        with av.open(str(dst), "w") as c:
            kw = {}
            if use_hw:
                kw["hwaccel"] = HWAccel(hwtype)
            s = c.add_stream(name, rate=30, options={k: str(v) for k, v in opts.items()}, **kw)
            s.width, s.height = W, H
            s.pix_fmt = "nv12"
            if variant == "intra":
                s.codec_context.gop_size = INTRA_GOP.get(name, 1)
            else:
                s.codec_context.gop_size = 15
            s.codec_context.max_b_frames = 0
            for i in range(N_SRC * LOOPS):
                vf = av.VideoFrame.from_ndarray(frames[i % N_SRC], format="nv12")
                vf.pts = i
                for p in s.encode(vf):
                    c.mux(p)
            for p in s.encode(None):
                c.mux(p)
        rec["ok"] = dst.exists() and dst.stat().st_size > 0
        rec["probe"] = probe_stream(dst)
    except Exception as e:  # noqa: BLE001
        rec["ok"] = False
        rec["error"] = f"{type(e).__name__}: {e}"[:400]
        rec["trace_last"] = traceback.format_exc().strip().splitlines()[-1][:300]
    return rec


def decode_tests() -> list[dict]:
    """mjpeg CPU vs mjpeg_cuvid vs mjpeg+HWAccel(cuda) on real 4:2:2 camera JPEGs."""
    out = []
    for setname in ("c930e_1080p", "c930e_720p_flash"):
        jpgs = sorted((CORPUS / setname).glob("frame_*.jpg"))[:5]
        ref = None
        for mode in ("mjpeg", "mjpeg_cuvid", "mjpeg+hwaccel_cuda"):
            rec: dict = {"set": setname, "decoder": mode}
            try:
                if mode == "mjpeg+hwaccel_cuda":
                    cc = av.CodecContext.create("mjpeg", "r", hwaccel=HWAccel("cuda", allow_software_fallback=False))
                else:
                    cc = av.CodecContext.create(mode, "r")
                ys, fmts = [], set()
                for j in jpgs:
                    for f in cc.decode(av.Packet(j.read_bytes())):
                        fmts.add(f.format.name)
                        if f.format.name in ("cuda",):
                            rec["hw_frame"] = True
                        g = f.to_ndarray(format="gray") if f.format.name != "cuda" else None
                        ys.append(g)
                for f in cc.decode(None):
                    fmts.add(f.format.name)
                    ys.append(f.to_ndarray(format="gray"))
                rec.update(ok=len(ys) > 0, frames=len(ys), formats=sorted(fmts))
                if mode == "mjpeg":
                    ref = ys
                elif ref and ys and all(y is not None for y in ys):
                    n = min(len(ref), len(ys))
                    rec["max_abs_diff_Y_vs_cpu"] = int(max(np.abs(ref[k].astype(int) - ys[k].astype(int)).max()
                                                           for k in range(n)))
                    rec["compared_frames"] = n
            except Exception as e:  # noqa: BLE001
                rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:400])
            out.append(rec)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    frames = load_nv12()
    rep = {"pyav": VER, "library_versions": {k: list(v) for k, v in av.library_versions.items()},
           "hwdevices_available": list(hwdevices_available()), "python": sys.version,
           "hw_encoders_in_wheel": sorted(n for n in av.codecs_available if any(
               k in n for k in ("nvenc", "qsv", "amf", "_mf", "d3d12va", "vulkan", "vaapi", "videotoolbox",
                                "cuvid", "mediacodec", "v4l2m2m"))),
           "nvidia_smi_before": nvidia_smi(), "encode": [], "decode": []}
    for name in ENCODERS:
        for variant in ("intra", "gop15"):
            for use_hw in (False, True):
                if use_hw and (ENCODERS[name][1] is None or HWAccel is None):
                    continue
                r = encode(name, variant, frames, use_hw)
                print(name, variant, r["input"], "OK" if r.get("ok") else "FAIL",
                      r.get("probe", {}).get("pict_types", ""), r.get("error", "")[:150])
                rep["encode"].append(r)
    rep["decode"] = decode_tests()
    for d in rep["decode"]:
        print(d)
    rep["nvidia_smi_after"] = nvidia_smi()
    (RESULTS / f"pyav_functional_{VER}.json").write_text(json.dumps(rep, indent=1))
    L = [f"# PyAV {VER} hardware encode/decode functional test", "",
         f"libavcodec {'.'.join(map(str, av.library_versions['libavcodec']))}; hwdevices_available: "
         f"{rep['hwdevices_available']}", "", f"hw codecs in wheel: {', '.join(rep['hw_encoders_in_wheel'])}", "",
         f"nvidia-smi before `{rep['nvidia_smi_before']}` after `{rep['nvidia_smi_after']}`", "",
         "| encoder | variant | input | ok | packets | key pkts | pict_types | codec/profile/pix_fmt | error |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rep["encode"]:
        p = r.get("probe", {})
        L.append(f"| {r['encoder']} | {r['variant']} | {r['input']} | {'yes' if r.get('ok') else 'NO'} | "
                 f"{p.get('packets', '')} | {p.get('key_packets', '')} | {p.get('pict_types', '')} | "
                 f"{p.get('codec_name', '')}/{p.get('profile', '')}/{p.get('pix_fmt', '')} | "
                 f"{r.get('error', '').replace('|', '/')[:200]} |")
    L += ["", "| set | decoder | ok | frames | output formats | max abs diff Y vs CPU mjpeg | error |",
          "|---|---|---|---|---|---|---|"]
    for d in rep["decode"]:
        L.append(f"| {d['set']} | {d['decoder']} | {d.get('ok')} | {d.get('frames', '')} | {d.get('formats', '')} | "
                 f"{d.get('max_abs_diff_Y_vs_cpu', '')} | {d.get('error', '').replace('|', '/')[:200]} |")
    (RESULTS / f"pyav_functional_{VER}.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
