"""Functional test of every hardware video encoder in the ffmpeg CLI on PATH (FUNCTIONAL ONLY, no timing).

For each encoder x {intra (g=1), gop15 (g=15, no B-frames)}: encode 32 frames of real-camera-derived input
(8 NV12 1080p frames looped 4x; see common.py), record exit code + last stderr lines, then ffprobe the
output: packets, keyframe-flagged packets, decoded frames, pict_type counts.
ffv1_vulkan additionally gets a byte-exact round-trip check (framemd5 of decoded output == framemd5 of input).

Run (repo root):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/ff_functional.py
Writes results/gpu_encode/ff_functional.json and .md; media to skellycam-raw/.../gpu_encode/ff_functional/.
"""
from __future__ import annotations

import json
import re
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import FFMPEG, MEDIA, RESULTS, nvidia_smi, prepare_inputs, probe_stream, run  # noqa: E402

OUT = MEDIA / "ff_functional"
LOOP = 3  # -stream_loop 3 -> 4 passes over the 8-frame input = 32 frames

QSV = ["-init_hw_device", "qsv=hw:hw_any", "-filter_hw_device", "hw"]
D3D12 = ["-init_hw_device", "d3d12va=d3d", "-filter_hw_device", "d3d"]
VK = ["-init_hw_device", "vulkan=vk", "-filter_hw_device", "vk"]
VAAPI = ["-init_hw_device", "vaapi=va", "-filter_hw_device", "va"]

# encoder: (pre-input hw args, input name, -vf chain or None, extra encoder args, container ext)
ENCODERS: dict[str, tuple[list[str], str, str | None, list[str], str]] = {
    "av1_nvenc": ([], "nv12_1080p", None, ["-preset", "p4"], "mkv"),
    "hevc_nvenc": ([], "nv12_1080p", None, ["-preset", "p4", "-bf", "0"], "mkv"),
    "h264_nvenc": ([], "nv12_1080p", None, ["-preset", "p4", "-bf", "0"], "mkv"),
    # nvenc with -g 1 is rejected by the driver (see NOTES); these rows keep that on record
    "hevc_nvenc_g1": ([], "nv12_1080p", None, ["-preset", "p4", "-bf", "0"], "mkv"),
    "h264_nvenc_g1": ([], "nv12_1080p", None, ["-preset", "p4", "-bf", "0"], "mkv"),
    "av1_qsv": (QSV, "nv12_1080p", None, [], "mkv"),
    "hevc_qsv": (QSV, "nv12_1080p", None, ["-bf", "0"], "mkv"),
    "h264_qsv": (QSV, "nv12_1080p", None, ["-bf", "0"], "mkv"),
    "vp9_qsv": (QSV, "nv12_1080p", None, [], "mkv"),
    "mjpeg_qsv": (QSV, "nv12_1080p", None, [], "mkv"),
    "av1_amf": ([], "nv12_1080p", None, [], "mkv"),
    "hevc_amf": ([], "nv12_1080p", None, [], "mkv"),
    "h264_amf": ([], "nv12_1080p", None, ["-bf", "0"], "mkv"),
    "av1_mf": ([], "nv12_1080p", None, ["-hw_encoding", "1"], "mkv"),
    "hevc_mf": ([], "nv12_1080p", None, ["-hw_encoding", "1"], "mkv"),
    "h264_mf": ([], "nv12_1080p", None, ["-hw_encoding", "1"], "mkv"),
    "av1_d3d12va": (D3D12, "nv12_1080p", "format=nv12,hwupload", [], "mkv"),
    # d3d12va h264/hevc: MKV header write fails in ffmpeg 9.0.2 ("Invalid data"), so MP4 is used; _mkv rows record it
    # default B-frames make h264_d3d12va fail mid-stream ("Encode failed") on this NVIDIA driver; -bf 0 used,
    # h264_d3d12va_bf keeps the default on record
    "hevc_d3d12va": (D3D12, "nv12_1080p", "format=nv12,hwupload", ["-bf", "0"], "mp4"),
    "h264_d3d12va": (D3D12, "nv12_1080p", "format=nv12,hwupload", ["-bf", "0"], "mp4"),
    "h264_d3d12va_bf": (D3D12, "nv12_1080p", "format=nv12,hwupload", [], "mp4"),
    "h264_d3d12va_mkv": (D3D12, "nv12_1080p", "format=nv12,hwupload", [], "mkv"),
    "av1_vulkan": (VK, "nv12_1080p", "format=nv12,hwupload", [], "mkv"),
    "hevc_vulkan": (VK, "nv12_1080p", "format=nv12,hwupload", ["-bf", "0"], "mkv"),
    "h264_vulkan": (VK, "nv12_1080p", "format=nv12,hwupload", ["-bf", "0"], "mkv"),
    # 4:2:0 at 1080p needs FFV1 version 4 (experimental) in ffv1_vulkan (ffv1enc_vulkan.c:1343-1350 @ n9.0.2)
    "ffv1_vulkan": (VK, "yuv420p_1080p", "format=yuv420p,hwupload", ["-level", "4", "-strict", "-2"], "mkv"),
    "ffv1_vulkan_l3": (VK, "yuv420p_1080p", "format=yuv420p,hwupload", [], "mkv"),
    "ffv1_vulkan_rgb": (VK, "bgr0_1080p", "format=bgr0,hwupload", [], "mkv"),
    # FFV1 Bayer is version 4.10 (experimental), only bayer_rggb16le (ffv1enc.c:921-928 @ n9.0.2)
    "ffv1_vulkan_bayer": (VK, "bayer_rggb16le_1080p", "format=bayer_rggb16le,hwupload", ["-level", "4", "-strict", "-2"], "mkv"),
    "prores_ks_vulkan": (VK, "yuv422p10le_1080p", "format=yuv422p10le,hwupload", [], "mov"),
    # VAAPI is Linux-only; tried for completeness so the error is on record
    "av1_vaapi": (VAAPI, "nv12_1080p", "format=nv12,hwupload", [], "mkv"),
    "h264_vaapi": (VAAPI, "nv12_1080p", "format=nv12,hwupload", [], "mkv"),
}
DIAG = re.compile(r"(failed|not supported|does not support|Failed to|could not|Codec not|No capable|"
                  r"Driver does not|requires|not yet implemented|only supported|Could not write header)", re.I)
VARIANTS = {"intra": ["-g", "1"], "gop15": ["-g", "15"]}
# nvenc: gop_size 0 is ffmpeg's intra-only switch (nvenc.c:1764-1767 @ n9.0.2); -g 1 is kept in the *_g1 rows
INTRA_OVERRIDE = {"h264_nvenc": ["-g", "0"], "hevc_nvenc": ["-g", "0"], "av1_nvenc": ["-g", "0"]}


def encode(name: str, variant: str, inputs: dict) -> dict:
    pre, inp, vf, extra, ext = ENCODERS[name]
    codec = name
    for sfx in ("_rgb", "_g1", "_mkv", "_l3", "_bf", "_bayer"):
        codec = codec.replace(sfx, "")
    from common import INPUT_SPECS  # noqa: PLC0415
    pf, w, h, _ = INPUT_SPECS[inp]
    dst = OUT / f"{name}_{variant}.{ext}"
    cmd = [FFMPEG, "-hide_banner", "-y", "-v", "verbose", *pre, "-f", "rawvideo", "-pix_fmt", pf, "-s", f"{w}x{h}",
           "-framerate", "30", "-stream_loop", str(LOOP), "-i", str(inputs[inp])]
    if vf:
        cmd += ["-vf", vf]
    gop = INTRA_OVERRIDE.get(name, VARIANTS[variant]) if variant == "intra" else VARIANTS[variant]
    cmd += ["-c:v", codec, *extra, *gop, str(dst)]
    rec: dict = {"encoder": name, "variant": variant, "cmd": " ".join(cmd)}
    try:
        r = run(cmd, timeout=180)
        rec["returncode"] = r.returncode
        lines = r.stderr.strip().splitlines()
        rec["stderr_tail"] = "\n".join(lines[-6:])
        rec["diagnosis"] = [ln for ln in lines if DIAG.search(ln)][:4]
    except Exception as e:  # noqa: BLE001
        rec["returncode"] = None
        rec["stderr_tail"] = repr(e)
    rec["ok"] = rec["returncode"] == 0 and dst.exists() and dst.stat().st_size > 0
    if rec["ok"]:
        rec["bytes"] = dst.stat().st_size
        rec["probe"] = probe_stream(dst)
    elif dst.exists():
        rec["bytes_partial"] = dst.stat().st_size
    return rec


def ffv1_roundtrip(inputs: dict, name: str, inp: str) -> dict:
    """framemd5 of the 8 source frames vs the first 8 decoded frames of the ffv1_vulkan intra file."""
    from common import INPUT_SPECS  # noqa: PLC0415
    pf, w, h, n = INPUT_SPECS[inp]
    cmp_pf = "gbrp" if pf == "bgr0" else pf  # bgr0's padding byte is not coded; compare the 3 colour planes
    src = run([FFMPEG, "-v", "error", "-f", "rawvideo", "-pix_fmt", pf, "-s", f"{w}x{h}", "-i", str(inputs[inp]),
               "-pix_fmt", cmp_pf, "-f", "framemd5", "-"])
    f = OUT / f"{name}_intra.mkv"
    dec = run([FFMPEG, "-v", "error", "-i", str(f), "-frames:v", str(n), "-pix_fmt", cmp_pf, "-f", "framemd5", "-"])

    def md5s(t: str) -> list[str]:
        return [ln.split(",")[-1].strip() for ln in t.splitlines() if ln and not ln.startswith("#")]

    a, b = md5s(src.stdout), md5s(dec.stdout)
    return {"file": str(f), "compare_pix_fmt": cmp_pf, "src_frames": len(a), "dec_frames": len(b), "byte_exact": bool(a) and a == b,
            "stderr": (src.stderr + dec.stderr).strip()[-300:]}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    inputs = prepare_inputs()
    ver = run([FFMPEG, "-hide_banner", "-version"]).stdout.splitlines()[0]
    report = {"ffmpeg": ver, "machine": platform.node(), "nvidia_smi_before": nvidia_smi(), "results": []}
    only = set(sys.argv[1:])
    for name in ENCODERS:
        if only and name not in only:
            continue
        for v in VARIANTS:
            rec = encode(name, v, inputs)
            print(name, v, "OK" if rec["ok"] else "FAIL", rec.get("probe", {}).get("pict_types", ""),
                  rec.get("diagnosis", [])[:2] if not rec["ok"] else "")
            report["results"].append(rec)
    report["nvidia_smi_after"] = nvidia_smi()
    report["roundtrip"] = {}
    for name, inp in (("ffv1_vulkan", "yuv420p_1080p"), ("ffv1_vulkan_rgb", "bgr0_1080p"),
                      ("ffv1_vulkan_bayer", "bayer_rggb16le_1080p")):
        if (OUT / f"{name}_intra.mkv").exists():
            report["roundtrip"][name] = ffv1_roundtrip(inputs, name, inp)
    suffix = "" if not only else "_subset"
    (RESULTS / f"ff_functional{suffix}.json").write_text(json.dumps(report, indent=1))
    lines = [f"# ffmpeg hardware encoder functional test ({ver})", "",
             f"nvidia-smi sessionCount,util,driver before: `{report['nvidia_smi_before']}` after: "
             f"`{report['nvidia_smi_after']}`", "",
             "| encoder | variant | opens+encodes | packets | key pkts | decoded | pict_types | codec/profile/pix_fmt | error (last line) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in report["results"]:
        p = r.get("probe", {})
        d = r.get("diagnosis") or r["stderr_tail"].splitlines()[-1:]
        err = "" if r["ok"] else " / ".join(x.split("] ")[-1] for x in d[:2]).replace("|", "/")
        lines.append(f"| {r['encoder']} | {r['variant']} | {'yes' if r['ok'] else 'NO'} | {p.get('packets', '')} | "
                     f"{p.get('key_packets', '')} | {p.get('decoded_frames', '')} | {p.get('pict_types', '')} | "
                     f"{p.get('codec_name', '')}/{p.get('profile', '')}/{p.get('pix_fmt', '')} | {err[:220]} |")
    lines += ["", "## ffv1_vulkan lossless round-trip", "", "| file | src frames | decoded | byte-exact |", "|---|---|---|---|"]
    for k, v in report["roundtrip"].items():
        lines.append(f"| {k} | {v['src_frames']} | {v['dec_frames']} | {v['byte_exact']} |")
    (RESULTS / f"ff_functional{suffix}.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
