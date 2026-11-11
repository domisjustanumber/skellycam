# /// script
# requires-python = ">=3.12"
# dependencies = ["nvidia-nvimgcodec-cu12[nvjpeg]==0.10.0.9", "numpy==2.2.6"]
# ///
"""GPU JPEG decode/encode from Python with NVIDIA nvImageCodec (FUNCTIONAL ONLY, no timing).

Run (repo root), isolated env from the PEP 723 header:
  uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvimgcodec_jpeg.py
Writes results/gpu_encode/nvimgcodec_jpeg.{json,md}; JPEGs to skellycam-raw/.../gpu_encode/nvimgcodec/.

Tests
 1. decode real 4:2:2 camera JPEGs (c930e_1080p, c922_720p_flash) per backend (GPU_ONLY, HW_GPU_ONLY,
    HYBRID_CPU_GPU, CPU_ONLY); compare RGB with ffmpeg's CPU decode (independent reference).
 2. encode on GPU (GPU_ONLY encoder backend) from a host numpy RGB array, CSS_422 and CSS_420, q=90;
    verify each output with ffprobe (codec, pix_fmt) and decode it back with ffmpeg; PSNR vs the source RGB.
 3. GPU-resident path: GPU-decoded image (device buffer) -> GPU encode, without a host round trip.
 4. planar/interleaved YUV input acceptance (I_YUV / P_YUV) - records exact error if rejected.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from nvidia import nvimgcodec as nv

sys.path.insert(0, str(Path(__file__).parent))
from common import CORPUS, FFMPEG, FFPROBE, MEDIA, RESULTS, nvidia_smi  # noqa: E402

OUT = MEDIA / "nvimgcodec"


def ff_rgb(jpeg: bytes) -> np.ndarray:
    r = subprocess.run([FFMPEG, "-v", "error", "-f", "mjpeg", "-i", "-", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                       input=jpeg, capture_output=True, check=True)
    p = subprocess.run([FFPROBE, "-v", "error", "-f", "mjpeg", "-i", "-", "-show_entries", "stream=width,height,pix_fmt",
                        "-of", "json"], input=jpeg, capture_output=True, check=True)
    s = json.loads(p.stdout)["streams"][0]
    return np.frombuffer(r.stdout, np.uint8).reshape(s["height"], s["width"], 3), s


# selectors: "backend:<BackendKind>" uses backends=[Backend(kind)]; "id:<impl>" uses decoder_ids/encoder_ids.
# backends=[Backend(GPU_ONLY)] alone fails with "Could not create decoder/encoder. Code: 7" in 0.10.0 on this
# machine (kept on record); selecting the implementation id works.
DEC_SEL = ["backend:GPU_ONLY", "backend:HW_GPU_ONLY", "backend:HYBRID_CPU_GPU", "id:nvjpeg_cuda_decoder",
           "id:libjpeg_turbo_decoder"]
ENC_SEL = ["backend:GPU_ONLY", "id:nvjpeg_cuda_encoder", "id:opencv_jpeg_encoder"]


def make(cls, sel: str):
    how, val = sel.split(":", 1)
    if how == "backend":
        return cls(backends=[nv.Backend(getattr(nv.BackendKind, val))])
    key = "decoder_ids" if cls is nv.Decoder else "encoder_ids"
    return cls(**{key: [val]})


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return float("inf") if mse == 0 else 10 * np.log10(255 ** 2 / mse)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    rep: dict = {"nvimgcodec": getattr(nv, "__version__", "?"), "decoder_ids": list(nv.get_decoder_ids()),
                 "encoder_ids": list(nv.get_encoder_ids()), "nvidia_smi_before": nvidia_smi(),
                 "decode": [], "encode": [], "gpu_resident": [], "yuv_input": []}
    srcs = {k: sorted((CORPUS / k).glob("frame_*.jpg"))[0] for k in ("c930e_1080p", "c922_720p_flash")}
    # 1. decode per backend
    for setname, path in srcs.items():
        jb = path.read_bytes()
        ref, s = ff_rgb(jb)
        for kind in DEC_SEL:
            rec = {"set": setname, "src_pix_fmt": s["pix_fmt"], "backend": kind}
            try:
                dec = make(nv.Decoder, kind)
                img = dec.decode(jb)
                if img is None:
                    raise RuntimeError("decode returned None (no decoder for this backend accepted the stream)")
                rec["buffer_kind"] = str(img.buffer_kind)
                arr = np.asarray(img.cpu())
                rec["shape"] = list(arr.shape)
                d = np.abs(arr.astype(int) - ref.astype(int))
                rec.update(ok=True, max_abs_diff_vs_ffmpeg=int(d.max()), mean_abs_diff_vs_ffmpeg=round(float(d.mean()), 3),
                           psnr_vs_ffmpeg_db=float(round(psnr(arr, ref), 2)))
            except Exception as e:  # noqa: BLE001
                rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
            rep["decode"].append(rec)
            print("decode", rec)
    # 2. encode from host RGB
    rgb, _ = ff_rgb(srcs["c930e_1080p"].read_bytes())
    for css in ("CSS_422", "CSS_420"):
        for kind in ENC_SEL:
            rec = {"input": "host numpy RGB 1920x1080", "chroma": css, "backend": kind, "quality": 90}
            try:
                enc = make(nv.Encoder, kind)
                params = nv.EncodeParams(quality_type=nv.QualityType.QUALITY, quality_value=90,
                                         chroma_subsampling=getattr(nv.ChromaSubsampling, css))
                cs = enc.encode(rgb, "jpeg", params=params)
                if cs is None:
                    raise RuntimeError("encode returned None")
                data = bytes(cs)
                f = OUT / f"enc_{kind}_{css}.jpg"
                f.write_bytes(data)
                back, s2 = ff_rgb(data)
                rec.update(ok=True, bytes=len(data), ffprobe_pix_fmt=s2["pix_fmt"], psnr_db=float(round(psnr(back, rgb), 2)),
                           file=str(f))
            except Exception as e:  # noqa: BLE001
                rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
            rep["encode"].append(rec)
            print("encode", rec)
    # 3. GPU-resident decode -> encode
    try:
        dec = nv.Decoder(decoder_ids=["nvjpeg_cuda_decoder"])
        enc = nv.Encoder(encoder_ids=["nvjpeg_cuda_encoder"])
        img = dec.decode(srcs["c930e_1080p"].read_bytes())
        cs = enc.encode(img, "jpeg", params=nv.EncodeParams(quality_type=nv.QualityType.QUALITY, quality_value=90,
                                                            chroma_subsampling=nv.ChromaSubsampling.CSS_422))
        data = bytes(cs)
        back, s2 = ff_rgb(data)
        rep["gpu_resident"].append({"ok": True, "decoded_buffer_kind": str(img.buffer_kind), "bytes": len(data),
                                    "ffprobe_pix_fmt": s2["pix_fmt"], "psnr_vs_ffmpeg_decode_db": float(round(psnr(back, rgb), 2))})
    except Exception as e:  # noqa: BLE001
        rep["gpu_resident"].append({"ok": False, "error": f"{type(e).__name__}: {e}"[:300]})
    print("gpu_resident", rep["gpu_resident"])
    # 4. YUV input acceptance (planar 4:4:4 YUV made from the RGB via BT.601 full range; shape tests only)
    y = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.uint8)
    for fmt, arr in (("P_YUV", np.stack([y, y, y])), ("I_YUV", np.dstack([y, y, y])), ("P_Y", y[None]), ("I_Y", y[..., None])):
        rec = {"sample_format": fmt, "shape": list(arr.shape)}
        try:
            enc = nv.Encoder(encoder_ids=["nvjpeg_cuda_encoder"])
            im = nv.as_image(np.ascontiguousarray(arr), sample_format=getattr(nv.SampleFormat, fmt))
            cs = enc.encode(im, "jpeg", params=nv.EncodeParams(quality_type=nv.QualityType.QUALITY, quality_value=90))
            if cs is None:
                raise RuntimeError("encode returned None")
            data = bytes(cs)
            _, s2 = ff_rgb(data)
            rec.update(ok=True, bytes=len(data), ffprobe_pix_fmt=s2["pix_fmt"])
        except Exception as e:  # noqa: BLE001
            rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
        rep["yuv_input"].append(rec)
        print("yuv", rec)
    rep["nvidia_smi_after"] = nvidia_smi()
    (RESULTS / "nvimgcodec_jpeg.json").write_text(json.dumps(rep, indent=1))
    L = [f"# nvImageCodec {rep['nvimgcodec']} GPU JPEG functional test", "",
         f"nvidia-smi before `{rep['nvidia_smi_before']}` after `{rep['nvidia_smi_after']}`", "",
         f"decoder ids: {rep['decoder_ids']}", "", f"encoder ids: {rep['encoder_ids']}", "",
         "## Decode of real camera JPEGs (vs ffmpeg CPU decode)", "",
         "| set | src | backend | ok | max/mean abs diff | PSNR dB | error |", "|---|---|---|---|---|---|---|"]
    for r in rep["decode"]:
        L.append(f"| {r['set']} | {r['src_pix_fmt']} | {r['backend']} | {r['ok']} | "
                 f"{r.get('max_abs_diff_vs_ffmpeg', '')}/{r.get('mean_abs_diff_vs_ffmpeg', '')} | "
                 f"{r.get('psnr_vs_ffmpeg_db', '')} | {r.get('error', '')} |")
    L += ["", "## Encode from host RGB (q=90)", "", "| chroma | backend | ok | bytes | ffprobe pix_fmt | PSNR dB | error |",
          "|---|---|---|---|---|---|---|"]
    for r in rep["encode"]:
        L.append(f"| {r['chroma']} | {r['backend']} | {r['ok']} | {r.get('bytes', '')} | {r.get('ffprobe_pix_fmt', '')} | "
                 f"{r.get('psnr_db', '')} | {r.get('error', '')} |")
    L += ["", f"GPU-resident decode->encode: `{rep['gpu_resident']}`", "", "## YUV/gray input acceptance", "",
          "| sample_format | ok | ffprobe pix_fmt | error |", "|---|---|---|---|"]
    for r in rep["yuv_input"]:
        L.append(f"| {r['sample_format']} | {r['ok']} | {r.get('ffprobe_pix_fmt', '')} | {r.get('error', '')} |")
    (RESULTS / "nvimgcodec_jpeg.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
