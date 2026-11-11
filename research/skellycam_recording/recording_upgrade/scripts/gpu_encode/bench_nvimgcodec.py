# /// script
# requires-python = ">=3.12"
# dependencies = ["nvidia-nvimgcodec-cu12[nvjpeg]==0.10.0.9", "numpy==2.2.6"]
# ///
"""BENCHMARK (timing): GPU JPEG encode/decode throughput from Python with nvImageCodec 0.10.0.9 (nvJPEG CUDA).

  decode: real 4:2:2 camera JPEGs (c922_720p_flash, c930e_1080p; looped) with nvjpeg_cuda_decoder (output in
          GPU memory; .cpu() download timed separately) vs libjpeg_turbo_decoder; batch sizes --batches.
  encode: RGB frames (decoded from the same camera JPEGs) -> JPEG q=90 CSS_422 with nvjpeg_cuda_encoder from
          (a) host numpy (includes upload) and (b) device-resident images (from the GPU decoder), vs opencv_jpeg_encoder.
Reports images/s (median over --reps), per-call ms.

Run (repo root, quiet machine):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/bench_nvimgcodec.py --n 300 --reps 3
Smoke: ... --n 8 --reps 1 --batches 1 --smoke
Writes results/gpu_encode/bench/nvimgcodec_<UTC>.json.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from nvidia import nvimgcodec as nv

sys.path.insert(0, str(Path(__file__).parent))
from benchlib import GpuSampler, snapshot, write  # noqa: E402
from common import CORPUS  # noqa: E402

SETS = {"720p": "c922_720p_flash", "1080p": "c930e_1080p"}


def timed(fn, n_items: int, reps: int) -> dict:
    fn()  # warmup
    rates = []
    for _ in range(reps):
        a = time.perf_counter()
        fn()
        rates.append(n_items / (time.perf_counter() - a))
    return {"images_per_s_median": round(statistics.median(rates), 2), "reps": [round(r, 2) for r in rates]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--batches", default="1,8")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    out = {"bench": "nvimgcodec", "nvimgcodec": nv.__version__, "args": vars(a), "system_before": snapshot(), "results": {}}
    params = nv.EncodeParams(quality_type=nv.QualityType.QUALITY, quality_value=90,
                             chroma_subsampling=nv.ChromaSubsampling.CSS_422)
    for size, setname in SETS.items():
        files = sorted((CORPUS / setname).glob("frame_*.jpg"))
        jpgs = [files[i % len(files)].read_bytes() for i in range(a.n)]
        res: dict = {}
        gdec = nv.Decoder(decoder_ids=["nvjpeg_cuda_decoder"])
        cdec = nv.Decoder(decoder_ids=["libjpeg_turbo_decoder"])
        genc = nv.Encoder(encoder_ids=["nvjpeg_cuda_encoder"])
        cenc = nv.Encoder(encoder_ids=["opencv_jpeg_encoder"])
        # device-resident source images come from a decoder instance that is never called again, so later
        # batched decodes cannot recycle their buffers (a shared decoder crashed with CUDA error 700 at batch 4)
        keep_dec = nv.Decoder(decoder_ids=["nvjpeg_cuda_decoder"])
        dev_imgs = keep_dec.decode(jpgs[: min(a.n, 32)])
        host_rgb = [np.asarray(im.cpu()) for im in dev_imgs]
        for b in map(int, a.batches.split(",")):
            def batched(fn, items):
                def go():
                    for i in range(0, len(items), b):
                        fn(items[i:i + b])
                return go
            def gpu_decode_synced():
                # GPU decode is asynchronous; dropping un-synchronised results caused CUDA error 700
                # (nvimgcodec_lifetime_probe.py). Keep results, then sync once via .cpu() of the last image.
                keep = []
                for i in range(0, len(jpgs), b):
                    keep.extend(gdec.decode(jpgs[i:i + b]))
                keep[-1].cpu()
                del keep
            with GpuSampler() as gs:
                res[f"decode_gpu_b{b}"] = timed(gpu_decode_synced, a.n, a.reps)
            res[f"decode_gpu_b{b}"]["gpu"] = gs.summary()
            res[f"decode_gpu_plus_download_b{b}"] = timed(
                batched(lambda x: [im.cpu() for im in gdec.decode(x)], jpgs), a.n, a.reps)
            res[f"decode_cpu_turbo_b{b}"] = timed(batched(lambda x: cdec.decode(x), jpgs), a.n, a.reps)
            host_items = [host_rgb[i % len(host_rgb)] for i in range(a.n)]
            dev_items = [dev_imgs[i % len(dev_imgs)] for i in range(a.n)]
            with GpuSampler() as gs:
                res[f"encode_gpu_from_host_b{b}"] = timed(
                    batched(lambda x: [bytes(c) for c in genc.encode(x, "jpeg", params=params)], host_items), a.n, a.reps)
            res[f"encode_gpu_from_host_b{b}"]["gpu"] = gs.summary()
            res[f"encode_gpu_from_device_b{b}"] = timed(
                batched(lambda x: [bytes(c) for c in genc.encode(x, "jpeg", params=params)], dev_items), a.n, a.reps)
            res[f"encode_cpu_opencv_b{b}"] = timed(
                batched(lambda x: [bytes(c) for c in cenc.encode(x, "jpeg", params=params)], host_items), a.n, a.reps)
        out["results"][size] = res
        print(size, "done")
    out["system_after"] = snapshot()
    write(f"nvimgcodec{'_smoke' if a.smoke else ''}", out)


if __name__ == "__main__":
    main()
