# /// script
# requires-python = ">=3.12"
# dependencies = ["nvidia-nvimgcodec-cu12[nvjpeg]==0.10.0.9", "numpy==2.2.6"]
# ///
"""FUNCTIONAL probe: does dropping GPU-decoded nvImageCodec images without synchronising break? (no timing)

Sequences (comma list, run in order on one Decoder): d1 = decode 16 camera JPEGs one by one and drop results;
d8 = decode in batches of 8 and drop; dl1 = decode one by one and download each with .cpu();
eh1/ed1/ec1 = encode 16 frames from host / device images on GPU, or on CPU (opencv).
Run: uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvimg_life.py d1
The script counts "CUDA error #700" lines itself when run via nvimgcodec_lifetime_run.py.
"""
import glob
import sys

import numpy as np
from nvidia import nvimgcodec as nv

seq = sys.argv[1].split(",")
files = sorted(glob.glob(r"C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus/c930e_1080p/*.jpg"))
j = [open(files[i % len(files)], "rb").read() for i in range(16)]
p = nv.EncodeParams(quality_type=nv.QualityType.QUALITY, quality_value=90, chroma_subsampling=nv.ChromaSubsampling.CSS_422)
gdec = nv.Decoder(decoder_ids=["nvjpeg_cuda_decoder"])
keep = nv.Decoder(decoder_ids=["nvjpeg_cuda_decoder"])
genc = nv.Encoder(encoder_ids=["nvjpeg_cuda_encoder"])
cenc = nv.Encoder(encoder_ids=["opencv_jpeg_encoder"])
dev = keep.decode(j[:8])
host = [np.asarray(x.cpu()) for x in dev]
for s in seq:
    if s == "d1":
        [gdec.decode(j[i:i + 1]) for i in range(16)]
    if s == "d8":
        [gdec.decode(j[i:i + 8]) for i in range(0, 16, 8)]
    if s == "dl1":
        [[x.cpu() for x in gdec.decode(j[i:i + 1])] for i in range(16)]
    if s == "eh1":
        [[bytes(c) for c in genc.encode([host[i % 8]], "jpeg", params=p)] for i in range(16)]
    if s == "ed1":
        [[bytes(c) for c in genc.encode([dev[i % 8]], "jpeg", params=p)] for i in range(16)]
    if s == "ec1":
        [[bytes(c) for c in cenc.encode([host[i % 8]], "jpeg", params=p)] for i in range(16)]
    print("ok", s, flush=True)
