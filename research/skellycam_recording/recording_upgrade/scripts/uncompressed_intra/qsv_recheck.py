# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""Functional QSV re-check (no timing) after the Intel UHD 770 iGPU became present (16:36, 2026-11-09).

The 11:19 functional matrix saw every *_qsv encoder fail with "Error creating a MFX session: -9" while the
iGPU was phantom. This re-opens hevc_qsv / h264_qsv / av1_qsv with PyAV 19.0.2 on 4 real C930e YUY2 1080p
frames, gop_size=1, and records: open/encode result, libav log, decoded pix_fmt, keyframe flags, Y PSNR.

Run from repo root:
  uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/qsv_recheck.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import av
import av.logging
import numpy as np

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus/c930e_1080p_yuy2")
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/qsv_recheck")
OUT = Path(__file__).resolve().parents[2] / "results" / "uncompressed_intra" / "qsv_recheck_pyav19.0.2.json"
W, H, N = 1920, 1080, 4

CASES = [
    # (codec, input pix_fmt, options)
    ("hevc_qsv", "yuyv422", {}),
    ("hevc_qsv", "nv12", {}),
    ("h264_qsv", "nv12", {}),
    ("av1_qsv", "nv12", {}),
]


def nvsmi() -> str:
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu",
                            "--format=csv,noheader"], capture_output=True, text=True, timeout=20)
        return r.stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"error {e}"


def yuyv_frames() -> list[np.ndarray]:
    files = sorted(CORPUS.glob("frame_*.yuy2"))[:N]
    return [np.frombuffer(f.read_bytes(), np.uint8).reshape(H, W * 2) for f in files]


def to_input(yuyv: np.ndarray, pix_fmt: str) -> av.VideoFrame:
    fr = av.VideoFrame(W, H, "yuyv422")
    if fr.planes[0].line_size != W * 2:
        raise RuntimeError("unexpected linesize")
    fr.planes[0].update(yuyv.tobytes())
    if pix_fmt == "yuyv422":
        return fr
    return fr.reformat(format=pix_fmt)


def y_plane(fr: av.VideoFrame) -> np.ndarray:
    p = fr.planes[0]
    a = np.frombuffer(bytes(p), np.uint8).reshape(fr.height, p.line_size)
    if fr.format.name in ("yuyv422",):
        return a[:, : fr.width * 2 : 2]
    return a[:, : fr.width]


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    m = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return 99.0 if m == 0 else 10 * np.log10(255.0 ** 2 / m)


def run_case(codec: str, pix: str, opts: dict, src: list[np.ndarray]) -> dict:
    MEDIA.mkdir(parents=True, exist_ok=True)
    path = MEDIA / f"{codec}_{pix}.mkv"
    res: dict = {"codec": codec, "input_pix_fmt": pix, "options": opts, "path": str(path)}
    logs: list[str] = []
    try:
        with av.logging.Capture() as cap:
            try:
                with av.open(str(path), "w") as c:
                    st = c.add_stream(codec, rate=30, options=opts)
                    st.width, st.height, st.pix_fmt = W, H, pix
                    st.codec_context.gop_size = 1
                    kf = []
                    for i, y in enumerate(src):
                        fr = to_input(y, pix)
                        fr.pts = i
                        for pkt in st.encode(fr):
                            kf.append(bool(pkt.is_keyframe)); c.mux(pkt)
                    for pkt in st.encode(None):
                        kf.append(bool(pkt.is_keyframe)); c.mux(pkt)
                res["stage"] = "ok"
                res["packets"] = len(kf)
                res["keyframe_flags"] = kf
            finally:
                logs = [f"{name}: {msg.strip()}" for (lvl, name, msg) in cap if lvl <= av.logging.WARNING]
    except Exception as e:  # noqa: BLE001
        res["stage"] = "encode_failed"
        res["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    res["libav_log"] = logs[:12]
    if res.get("stage") == "ok":
        with av.open(str(path)) as c:
            vs = c.streams.video[0]
            res["coded_profile"] = vs.codec_context.profile
            dec = list(c.decode(vs))
        res["frames_decoded"] = len(dec)
        res["decoded_pix_fmt"] = dec[0].format.name if dec else None
        ps = [psnr(y_plane(d), src[i][:, 0::2]) for i, d in enumerate(dec)]
        res["y_psnr_db_min"] = round(min(ps), 2) if ps else None
        res["file_bytes"] = path.stat().st_size
    return res


def main() -> int:
    src = yuyv_frames()
    out = {"av_version": av.__version__, "ffmpeg": av.library_versions.get("libavcodec"),
           "frames": len(src), "source": str(CORPUS), "note": "functional only, no timing",
           "nvidia_smi_before": nvsmi(), "cases": []}
    for codec, pix, opts in CASES:
        r = run_case(codec, pix, opts, src)
        print(json.dumps({k: r.get(k) for k in ("codec", "input_pix_fmt", "stage", "decoded_pix_fmt",
                                                 "coded_profile", "keyframe_flags", "y_psnr_db_min", "error")}))
        out["cases"].append(r)
    out["nvidia_smi_after"] = nvsmi()
    OUT.write_text(json.dumps(out, indent=1))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
