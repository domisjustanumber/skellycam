# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""FUNCTIONAL ONLY (no timing). Re-check Intel QSV (+ MF AV1/H.264) through PyAV 19.0.2 now that the UHD 770 is present.
Same inputs/method as scripts/gpu_encode/pyav_functional.py (32 NV12 1080p frames = 8 real frames looped 4x,
intra/gop15, max_b_frames 0, sw frames and HWAccel('qsv')), plus mjpeg_qsv decode of real 4:2:2 camera JPEGs.
Writes results/gpu_encode/qsv_recheck_19.0.2.{json,md}; media under skellycam-raw/.../gpu_encode/qsv_recheck_19.0.2/.
Run from the repo root:  uv run --script <this file>
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

import av
import av.logging
import numpy as np

sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/gpu_encode")
from common import CORPUS, MEDIA, RESULTS, nvidia_smi, prepare_inputs, probe_stream  # noqa: E402
from av.codec.hwaccel import HWAccel, hwdevices_available  # noqa: E402

W, H, N_SRC, LOOPS = 1920, 1080, 8, 4
OUT = MEDIA / "qsv_recheck_19.0.2"
OUT.mkdir(parents=True, exist_ok=True)
# name -> (options, hw device type or None, container ext, intra gop_size)
ENC = {
    "h264_qsv": ({}, "qsv", "mkv", 1),
    "hevc_qsv": ({}, "qsv", "mkv", 1),
    "av1_qsv": ({}, "qsv", "mkv", 1),
    "vp9_qsv": ({}, "qsv", "mkv", 1),
    "mjpeg_qsv": ({}, "qsv", "mkv", 1),
    "av1_mf": ({"hw_encoding": "1"}, None, "mkv", 1),
    "h264_mf": ({"hw_encoding": "1"}, None, "mkv", 1),
}


def frames() -> list[np.ndarray]:
    raw = Path(prepare_inputs()["nv12_1080p"]).read_bytes()
    fs = W * H * 3 // 2
    return [np.frombuffer(raw[i * fs:(i + 1) * fs], np.uint8).reshape(H * 3 // 2, W) for i in range(N_SRC)]


def logtail(logs, n: int = 4) -> list[str]:
    return [f"{lv[1]}: {lv[2].strip()}" for lv in logs if lv[0] <= av.logging.WARNING][-n:]


def mft_names(logs) -> list[str]:
    return sorted({lv[2].strip() for lv in logs if "MFT_FRIENDLY_NAME" in lv[2]})


def encode(name: str, variant: str, fr: list[np.ndarray], use_hw: bool) -> dict:
    opts, hw, ext, ig = ENC[name]
    dst = OUT / f"{name}_{variant}_{'hwctx' if use_hw else 'sw'}.{ext}"
    rec: dict = {"encoder": name, "variant": variant, "input": "hwaccel ctx" if use_hw else "sw frames"}
    av.logging.set_level(av.logging.VERBOSE)
    with av.logging.Capture() as logs:
        try:
            with av.open(str(dst), "w") as c:
                kw = {"hwaccel": HWAccel(hw)} if use_hw else {}
                s = c.add_stream(name, rate=30, options=dict(opts), **kw)
                s.width, s.height, s.pix_fmt = W, H, "nv12"
                s.codec_context.gop_size = ig if variant == "intra" else 15
                s.codec_context.max_b_frames = 0
                for i in range(N_SRC * LOOPS):
                    vf = av.VideoFrame.from_ndarray(fr[i % N_SRC], format="nv12")
                    vf.pts = i
                    for p in s.encode(vf):
                        c.mux(p)
                for p in s.encode(None):
                    c.mux(p)
            rec["ok"] = dst.exists() and dst.stat().st_size > 0
            rec["file"] = str(dst)
            rec["probe"] = probe_stream(dst)
        except Exception as e:  # noqa: BLE001
            rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
    av.logging.set_level(None)
    rec["log_tail"] = logtail(logs)
    rec["mft"] = mft_names(logs)
    return rec


def decode_qsv() -> list[dict]:
    out = []
    for setname in ("c930e_1080p", "c930e_720p_flash"):
        jpgs = sorted((CORPUS / setname).glob("frame_*.jpg"))[:5]
        for mode in ("mjpeg", "mjpeg_qsv", "mjpeg+hwaccel_qsv"):
            rec: dict = {"set": setname, "decoder": mode, "inputs": len(jpgs)}
            av.logging.set_level(av.logging.VERBOSE)
            with av.logging.Capture() as logs:
                try:
                    if mode == "mjpeg+hwaccel_qsv":
                        cc = av.CodecContext.create("mjpeg", "r", hwaccel=HWAccel("qsv", allow_software_fallback=False))
                    else:
                        cc = av.CodecContext.create(mode, "r")
                    n, fmts = 0, set()
                    for j in jpgs:
                        for f in cc.decode(av.Packet(j.read_bytes())):
                            n += 1
                            fmts.add(f.format.name)
                    for f in cc.decode(None):
                        n += 1
                        fmts.add(f.format.name)
                    rec.update(ok=n > 0, frames=n, formats=sorted(fmts))
                except Exception as e:  # noqa: BLE001
                    rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
            av.logging.set_level(None)
            rec["log_tail"] = logtail(logs)
            out.append(rec)
    return out


def pnp() -> list[str]:
    cmd = "Get-PnpDevice -Class Display | ForEach-Object { '{0} {1} {2}' -f $_.Status, $_.Present, $_.FriendlyName }"
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=60)
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def main() -> None:
    rep: dict = {"when": datetime.datetime.now().astimezone().isoformat(), "pyav": av.__version__,
                 "libavcodec": str(av.library_versions.get("libavcodec")),
                 "hwdevices_available": list(hwdevices_available()), "display_adapters": pnp(),
                 "nvidia_smi_before": nvidia_smi(), "encode": [], "decode": []}
    fr = frames()
    for name in ENC:
        for variant in ("intra", "gop15"):
            for use_hw in (False, True):
                if use_hw and ENC[name][1] is None:
                    continue
                r = encode(name, variant, fr, use_hw)
                rep["encode"].append(r)
                print(json.dumps(r, default=str)[:300], flush=True)
    rep["decode"] = decode_qsv()
    rep["nvidia_smi_after"] = nvidia_smi()
    (RESULTS / "qsv_recheck_19.0.2.json").write_text(json.dumps(rep, indent=1, default=str))
    L = [f"# QSV / MF re-check, PyAV {rep['pyav']} (libavcodec {rep['libavcodec']}), functional only, {rep['when']}", "",
         "Script: scratchpad copy `qsv_recheck.py` (saved alongside as `qsv_recheck_19.0.2.py`).", "",
         "Display adapters (Get-PnpDevice Status Present Name): " + "; ".join(rep["display_adapters"]), "",
         f"hwdevices_available: {rep['hwdevices_available']}", "",
         f"nvidia-smi before `{rep['nvidia_smi_before']}` after `{rep['nvidia_smi_after']}`", "",
         "| encoder | variant | input | ok | packets | key pkts | decoded | pict_types | codec/profile/pix_fmt | MFT | error / last log |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep["encode"]:
        p = r.get("probe", {})
        err = r.get("error", "")
        if not r["ok"]:
            err += " | log: " + " / ".join(r["log_tail"][-2:])
        L.append(f"| {r['encoder']} | {r['variant']} | {r['input']} | {'yes' if r['ok'] else 'NO'} | {p.get('packets', '')} | "
                 f"{p.get('key_packets', '')} | {p.get('decoded_frames', '')} | {p.get('pict_types', '')} | "
                 f"{p.get('codec_name', '')}/{p.get('profile', '')}/{p.get('pix_fmt', '')} | {'; '.join(r['mft'])} | "
                 f"{err.replace('|', '/')} |")
    L += ["", "| set | decoder | ok | frames (of 5) | output formats | error / last log |", "|---|---|---|---|---|---|"]
    for r in rep["decode"]:
        tail = (r.get("error", "") + " " + " / ".join(r["log_tail"][-2:])).strip()
        L.append(f"| {r['set']} | {r['decoder']} | {r['ok']} | {r.get('frames', '')} | {r.get('formats', '')} | "
                 f"{tail.replace('|', '/')} |")
    (RESULTS / "qsv_recheck_19.0.2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
