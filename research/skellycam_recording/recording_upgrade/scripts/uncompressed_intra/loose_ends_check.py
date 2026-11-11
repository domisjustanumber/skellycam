"""Quick functional checks (no timing) that back claims in FINDINGS.md which
were previously only in a session log.

1. YUY2 luma/chroma range over the corpus YUY2 frames (limited vs full range).
2. Read-only display adapter listing (Get-PnpDevice -Class Display, Win32_VideoController).
3. ffmpeg -init_hw_device qsv (does a QSV device open?).
4. NVENC: 4:2:2 (nv16) and av1_nvenc open errors on a 1-frame lavfi clip.
5. libjxl / libsvtjpegxs mux into mkv / nut / mov (container acceptance).

Writes results/uncompressed_intra/loose_ends_check.json. Media goes to the
skellycam-raw folder and is deleted. Run with the skellycam venv python.
"""
import json
import pathlib
import subprocess
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[5]
STUDY = REPO / "research/skellycam_recording/recording_upgrade"
OUT = STUDY / "results/uncompressed_intra/loose_ends_check.json"
CORPUS = pathlib.Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
MEDIA = pathlib.Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/loose_ends")


def run(cmd, timeout=60):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return {"cmd": " ".join(cmd), "rc": p.returncode,
            "stdout_head": p.stdout.strip()[:300], "stdout_tail": p.stdout.strip()[-1500:],
            "stderr_head": p.stderr.strip()[:800], "stderr_tail": p.stderr.strip()[-1500:]}


def nvsmi():
    try:
        return run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu",
                    "--format=csv,noheader"])["stdout_tail"]
    except Exception as e:  # noqa: BLE001
        return repr(e)


def main():
    res = {"python": sys.version, "numpy": np.__version__}
    ff = run(["ffmpeg", "-hide_banner", "-version"])
    res["ffmpeg_version"] = ff["stdout_head"].splitlines()[0] if ff["stdout_head"] else ff
    # 1. YUY2 range
    rng = {}
    for cam in ("c930e_1080p_yuy2", "c922_1080p_yuy2"):
        ys, cs = [], []
        for f in sorted((CORPUS / cam).glob("frame_*.yuy2")):
            a = np.frombuffer(f.read_bytes(), np.uint8)
            ys.append(a[0::2]); cs.append(a[1::2])
        y = np.concatenate(ys); c = np.concatenate(cs)
        rng[cam] = {"frames": len(ys), "Y_min": int(y.min()), "Y_max": int(y.max()),
                    "C_min": int(c.min()), "C_max": int(c.max()),
                    "Y_frac_below_16": float((y < 16).mean()), "Y_frac_above_235": float((y > 235).mean())}
    res["yuy2_range"] = rng
    # 2. adapters (read-only)
    res["pnp_display"] = run(["powershell", "-NoProfile", "-Command",
                              "Get-PnpDevice -Class Display | Select-Object Status,FriendlyName | Format-Table -HideTableHeaders | Out-String -Width 200"])
    res["win32_videocontroller"] = run(["powershell", "-NoProfile", "-Command",
                                        "Get-CimInstance Win32_VideoController | Select-Object Name,Status | Format-Table -HideTableHeaders | Out-String -Width 200"])
    # 3. QSV device
    res["qsv_init"] = run(["ffmpeg", "-hide_banner", "-init_hw_device", "qsv=q", "-f", "lavfi",
                           "-i", "nullsrc=s=64x64:d=0.04", "-f", "null", "-"])
    MEDIA.mkdir(parents=True, exist_ok=True)
    # 4. NVENC open errors (1 frame)
    res["nvidia_smi_before"] = nvsmi()
    nv = {}
    for name, args in {
        "h264_nvenc_nv16": ["-pix_fmt", "nv16", "-c:v", "h264_nvenc"],
        "hevc_nvenc_nv16": ["-pix_fmt", "nv16", "-c:v", "hevc_nvenc"],
        "av1_nvenc_nv12": ["-pix_fmt", "nv12", "-c:v", "av1_nvenc"],
        "hevc_nvenc_nv12_control": ["-pix_fmt", "nv12", "-c:v", "hevc_nvenc"],
    }.items():
        nv[name] = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", "testsrc2=s=256x256:d=0.04:r=25", *args, "-frames:v", "1",
                        "-f", "null", "-"])
    res["nvenc_open"] = nv
    res["nvidia_smi_after"] = nvsmi()
    # 5. JXL / JPEG XS mux acceptance
    mux = {}
    for enc, extra in {"libjxl": ["-pix_fmt", "rgb24"], "libsvtjpegxs": ["-pix_fmt", "yuv422p", "-b:v", "50M"]}.items():
        for ext in ("mkv", "nut", "mov"):
            out = MEDIA / f"{enc}.{ext}"
            r = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                     "-i", "testsrc2=s=256x256:d=0.08:r=25", *extra, "-c:v", enc, str(out)])
            r["file_written"] = out.exists() and out.stat().st_size > 0
            mux[f"{enc}.{ext}"] = r
            if out.exists():
                out.unlink()
    res["mux_acceptance"] = mux
    try:
        MEDIA.rmdir()
    except OSError:
        pass
    OUT.write_text(json.dumps(res, indent=1))
    print(OUT)


if __name__ == "__main__":
    main()
