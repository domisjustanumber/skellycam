"""Which hardware codecs do the PyPI PyAV wheels ship, per OS? (static inspection, no import)

Downloads the cp312 abi3 wheels of a PyAV version from PyPI (URL + sha256 from the PyPI JSON API, verified),
opens each wheel as a zip, and searches the bundled libavcodec binary for FFmpeg codec-name strings
(e.g. b"\\0h264_vaapi\\0"). A name present as a NUL-terminated string in libavcodec = that AVCodec is compiled in.
Cross-checked on win_amd64 against av.codecs_available (pyav_functional.py), so the method is validated.

Run (repo root; system or venv python, stdlib only):
  python research/skellycam_recording/recording_upgrade/scripts/gpu_encode/wheel_hw_codecs.py 19.0.2 18.0.0
Downloads go to the gpu_encode scratchpad (temp); results to results/gpu_encode/wheel_hw_codecs.{json,md}.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2] / "results/gpu_encode"
TMP = Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/"
           "scratchpad/gpu_encode/wheels")
PLATS = ["win_amd64", "win_arm64", "manylinux_2_28_x86_64", "manylinux_2_28_aarch64", "macosx_14_0_arm64",
         "macosx_11_0_x86_64"]
NAMES = [f"{c}_{h}" for h in ("nvenc", "qsv", "amf", "mf", "d3d12va", "vulkan", "vaapi", "videotoolbox",
                               "v4l2m2m", "mediacodec", "cuvid")
         for c in ("h264", "hevc", "av1", "vp9", "vp8", "mjpeg", "prores", "ffv1")]
NAMES += ["prores_ks_vulkan", "ffv1_vulkan", "libsvtav1", "libvpx-vp9", "libaom-av1", "librav1e", "libdav1d"]
# Short names like "h264_videotoolbox" / "vp9_d3d12va" are shared by hwaccel DECODERS, so encoder presence is
# confirmed by the encoder's CODEC_LONG_NAME string (ffmpeg n9.0.2: videotoolboxenc.c:2853/2894/2935,
# vulkan_encode_h264.c:1652, vulkan_encode_av1.c:1448, d3d12va_encode_hevc.c:825, nvenc/qsv/amf/mf files).
ENCODER_LONG_NAMES = ["VideoToolbox H.264 Encoder", "VideoToolbox H.265 Encoder", "VideoToolbox ProRes Encoder",
                      "H.264/AVC (Vulkan)", "H.265/HEVC (Vulkan)", "AV1 (Vulkan)", "D3D12VA h264 encoder",
                      "D3D12VA hevc encoder", "D3D12VA av1 encoder", "NVIDIA NVENC av1 encoder",
                      "NVIDIA NVENC H.264 encoder", "NVIDIA NVENC hevc encoder", "AMD AMF AV1 encoder",
                      "AV1 (Intel Quick Sync Video acceleration)", "VP9 video (Intel Quick Sync Video acceleration)",
                      "AV1 via MediaFoundation", "AV1 (VAAPI)", "H.264/AVC (VAAPI)", "VP9 (VAAPI)", "MJPEG (VAAPI)",
                      "V4L2 mem2mem H.264 encoder wrapper", "V4L2 mem2mem VP9 encoder wrapper"]


def main(versions: list[str]) -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    report = {}
    for ver in versions:
        meta = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/av/{ver}/json"))
        for u in meta["urls"]:
            fn = u["filename"]
            plat = next((p for p in PLATS if fn.endswith(f"{p}.whl")), None)
            if plat is None or ("abi3" not in fn and "cp312" not in fn):
                continue
            if "cp314t" in fn:
                continue
            dst = TMP / fn
            if not dst.exists():
                urllib.request.urlretrieve(u["url"], dst)
            sha = hashlib.sha256(dst.read_bytes()).hexdigest()
            assert sha == u["digests"]["sha256"], f"sha256 mismatch {fn}"
            with zipfile.ZipFile(dst) as z:
                libs = [n for n in z.namelist() if re.search(r"(avcodec[-.].*\.(dll|so[.\d]*|dylib)$)", n.split("/")[-1])]
                blob = b"".join(z.read(n) for n in libs)
            found = sorted(n for n in NAMES if b"\0" + n.encode() + b"\0" in blob)
            enc_long = sorted(n for n in ENCODER_LONG_NAMES if n.encode() + b"\0" in blob)
            report[f"{ver}/{plat}"] = {"wheel": fn, "url": u["url"], "sha256": sha, "libavcodec_files": libs,
                                       "hw_and_ref_codecs": found, "encoder_long_names": enc_long}
            print(ver, plat, enc_long)
    (RESULTS / "wheel_hw_codecs.json").write_text(json.dumps(report, indent=1))
    L = ["# Hardware codec names compiled into PyPI PyAV wheels (static string search of bundled libavcodec)", "",
         "Column 3: codec short names (shared with hwaccel decoders). Column 4: encoder long names (encoder-only).", "",
         "| PyAV / platform | wheel | codec names found | hardware ENCODER long names found |", "|---|---|---|---|"]
    for k, v in report.items():
        L.append(f"| {k} | {v['wheel']} | {', '.join(v['hw_and_ref_codecs'])} | {'; '.join(v['encoder_long_names'])} |")
    (RESULTS / "wheel_hw_codecs.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] or ["19.0.2"])
