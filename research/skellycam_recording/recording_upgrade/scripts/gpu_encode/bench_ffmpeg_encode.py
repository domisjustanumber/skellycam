"""BENCHMARK (timing): single-stream, unpaced encode throughput + CPU cost through the ffmpeg CLI.

Matrix: encoder x size {720p,1080p} x GOP {intra, gop15} x input {nv12 raw, mjpeg (CPU mjpeg decode)}.
Input: real camera frames (see common.py) looped with -stream_loop to --frames frames; output -f null (no disk).
Per run: ffmpeg -benchmark utime/stime/rtime -> fps = frames / rtime, cpu_cores = (utime+stime)/rtime;
nvidia-smi sampled every 500 ms (encoder util, sessions). Each config repeated --reps times; median reported.
GPU encoders here use NVENC (h264/hevc_nvenc), Vulkan Video (h264/hevc_vulkan), D3D12 (h264/hevc_d3d12va),
MediaFoundation->NVIDIA MFT (h264/hevc_mf), Vulkan compute (ffv1_vulkan, prores_ks_vulkan); CPU references:
libsvtav1, libvpx-vp9, mjpeg, ffv1. AV1/VP9 hardware encode is unavailable on this machine (see NOTES.md).

Run (repo root, quiet machine, ~25 min full):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/bench_ffmpeg_encode.py --frames 900 --reps 3
Smoke: ... bench_ffmpeg_encode.py --frames 30 --reps 1 --only h264_nvenc,ffv1_vulkan --sizes 720p --smoke
Writes results/gpu_encode/bench/ffmpeg_encode_<UTC>.json (smoke runs: ffmpeg_encode_smoke_<UTC>.json).
"""
from __future__ import annotations

import argparse
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from benchlib import GpuSampler, snapshot, write  # noqa: E402
from common import FFMPEG, INPUTS, prepare_inputs, run  # noqa: E402

VK = ["-init_hw_device", "vulkan=vk", "-filter_hw_device", "vk"]
D3D = ["-init_hw_device", "d3d12va=d3d", "-filter_hw_device", "d3d"]
# name: (hw init args, upload sw format or None, encoder args, intra gop args, gop15 args)
ENC = {
    "h264_nvenc": ([], None, ["-c:v", "h264_nvenc", "-preset", "p4", "-bf", "0"], ["-g", "0"], ["-g", "15"]),
    "hevc_nvenc": ([], None, ["-c:v", "hevc_nvenc", "-preset", "p4", "-bf", "0"], ["-g", "0"], ["-g", "15"]),
    "h264_vulkan": (VK, "nv12", ["-c:v", "h264_vulkan", "-bf", "0"], ["-g", "1"], ["-g", "15"]),
    "hevc_vulkan": (VK, "nv12", ["-c:v", "hevc_vulkan", "-bf", "0"], ["-g", "1"], ["-g", "15"]),
    "h264_d3d12va": (D3D, "nv12", ["-c:v", "h264_d3d12va", "-bf", "0"], ["-g", "1"], ["-g", "15"]),
    "hevc_d3d12va": (D3D, "nv12", ["-c:v", "hevc_d3d12va", "-bf", "0"], ["-g", "1"], ["-g", "15"]),
    "h264_mf": ([], None, ["-c:v", "h264_mf", "-hw_encoding", "1"], ["-g", "1"], ["-g", "15"]),
    "hevc_mf": ([], None, ["-c:v", "hevc_mf", "-hw_encoding", "1"], ["-g", "1"], ["-g", "15"]),
    "ffv1_vulkan": (VK, "yuv420p", ["-c:v", "ffv1_vulkan", "-level", "4", "-strict", "-2"], ["-g", "1"], None),
    "prores_ks_vulkan": (VK, "yuv422p10le", ["-c:v", "prores_ks_vulkan"], [], None),
    # CPU references
    "libsvtav1": ([], "", ["-c:v", "libsvtav1", "-preset", "10", "-pix_fmt", "yuv420p"], ["-g", "1"], ["-g", "15"]),
    "libvpx-vp9": ([], "", ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1",
                            "-b:v", "0", "-crf", "32", "-pix_fmt", "yuv420p"], ["-g", "1"], ["-g", "15"]),
    "mjpeg": ([], "", ["-c:v", "mjpeg", "-q:v", "3", "-pix_fmt", "yuvj422p"], [], None),
    "ffv1": ([], "", ["-c:v", "ffv1", "-level", "3", "-slices", "24", "-threads", "0", "-pix_fmt", "yuv420p"],
             ["-g", "1"], None),
    # baseline: no compression (input read + MJPEG CPU decode + NV12 conversion only); subtract to isolate encode
    "none_rawvideo": ([], "", ["-c:v", "rawvideo", "-pix_fmt", "nv12"], [], None),
}
SIZES = {"720p": ("nv12_720p", "mjpeg_720p", 1280, 720), "1080p": ("nv12_1080p", "mjpeg_1080p", 1920, 1080)}
BENCH_RE = re.compile(r"bench: utime=([\d.]+)s stime=([\d.]+)s rtime=([\d.]+)s")
RSS_RE = re.compile(r"bench: maxrss=(\d+)")


def one(name: str, size: str, gop: str, src: str, frames: int) -> dict:
    pre, upl, encargs, g_intra, g15 = ENC[name]
    gargs = g_intra if gop == "intra" else g15
    nv12, mj, w, h = SIZES[size]
    if src == "nv12":
        inp = ["-f", "rawvideo", "-pix_fmt", "nv12", "-s", f"{w}x{h}", "-framerate", "30", "-stream_loop", "-1",
               "-i", str(INPUTS / f"{nv12}.yuv")]
    else:
        inp = ["-f", "mjpeg", "-framerate", "30", "-stream_loop", "-1", "-i", str(INPUTS / f"{mj}.mjpeg")]
    vf = []
    if upl:
        vf = ["-vf", f"format={upl},hwupload"]
    elif upl is None and src == "mjpeg":
        vf = ["-vf", "format=nv12"]  # hw encoders taking sw frames get NV12 (decoder outputs yuvj422p)
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-nostats", "-v", "info", "-benchmark", *pre, *inp, "-frames:v", str(frames),
           *vf, *encargs, *gargs, "-f", "null", "-"]
    with GpuSampler() as gs:
        r = run(cmd, timeout=1800)
    rec = {"encoder": name, "size": size, "gop": gop, "input": src, "frames": frames, "returncode": r.returncode,
           "cmd": " ".join(cmd), "gpu": gs.summary()}
    m = BENCH_RE.search(r.stderr)
    if r.returncode == 0 and m:
        ut, st, rt = map(float, m.groups())
        rec.update(utime_s=ut, stime_s=st, rtime_s=rt, fps=round(frames / rt, 2), cpu_cores=round((ut + st) / rt, 3),
                   cpu_ms_per_frame=round(1000 * (ut + st) / frames, 3))
        mr = RSS_RE.search(r.stderr)
        if mr:
            rec["maxrss_kb"] = int(mr.group(1))
    else:
        errs = [ln for ln in r.stderr.splitlines() if "rror" in ln or "ail" in ln]
        rec["error"] = (" / ".join(errs) or r.stderr.strip())[-400:]
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=900)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--only", default="", help="comma list of encoders")
    ap.add_argument("--sizes", default="720p,1080p")
    ap.add_argument("--inputs", default="nv12,mjpeg")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    prepare_inputs()
    names = [n for n in ENC if not a.only or n in a.only.split(",")]
    out = {"bench": "ffmpeg_encode", "args": vars(a), "system_before": snapshot(), "runs": [], "median": []}
    for name in names:
        for size in a.sizes.split(","):
            for gop in ("intra", "gop15"):
                if gop == "gop15" and ENC[name][4] is None:
                    continue
                for src in a.inputs.split(","):
                    reps = [one(name, size, gop, src, a.frames) for _ in range(a.reps)]
                    out["runs"] += reps
                    ok = [x for x in reps if "fps" in x]
                    med = {"encoder": name, "size": size, "gop": gop, "input": src, "ok_reps": len(ok)}
                    if ok:
                        for k in ("fps", "cpu_cores", "cpu_ms_per_frame"):
                            med[k] = statistics.median(x[k] for x in ok)
                    else:
                        med["error"] = reps[-1].get("error", "")[-200:]
                    out["median"].append(med)
                    print(med)
    out["system_after"] = snapshot()
    write("ffmpeg_encode_smoke" if a.smoke else "ffmpeg_encode", out)


if __name__ == "__main__":
    main()
